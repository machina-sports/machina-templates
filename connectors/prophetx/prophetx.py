"""ProphetX Affiliate API connector — authenticated, read-only market data.

Implements the approved design log
(docs/plans/2026-08-13-001-feat-prophetx-affiliate-connector-design-log.md).

Surface: the External Affiliate API (Swagger 2.0, 10 GET endpoints, zero write
surface). Odds/liquidity exist ONLY here — the public catalog API exposes none
(verified live 2026-08-13). Wager placement lives in ProphetX's MM/ISV APIs and
is intentionally NOT implemented: the Direct Play demo hands off via official
Auto-Fill deep links (`build_autofill_link`), never executing a wager.

Environments (fixed allowlist — arbitrary endpoints are rejected by design):
- sandbox:    https://api.sandbox.prophetx.dev/partner
- production: https://cash.api.prophetx.co/partner

Auth (two documented modes, resolved per call from injected headers):
- mode A: single API key sent raw in the ``Authorization`` header
- mode B: access_key + secret_key -> POST /auth/login -> access_token
  (documented expiry: 10 minutes) + refresh_token; cached per
  (environment, access_key); one re-login on 401, then typed failure.
Upstream docs contradict each other on a ``Bearer`` prefix (spec says Bearer,
integration guide says raw). ``auth_scheme`` param ("raw" default | "bearer")
keeps both paths open until the sandbox smoke resolves it empirically.

Upstream limits honored: 50 req/s account budget (client stays far below and
backs off on 429), ``event_ids`` batches capped at 50, no pagination on this
API. The multiple-markets response schema is empty in the official spec; the
real shape is a dict keyed by event id that may occasionally arrive as a flat
list — both shapes are parsed defensively.

Odds format note: official examples disagree (American ``-470`` vs "decimal
price" ``1.95``). Until the sandbox smoke settles it per version, ``odds`` is
passed through verbatim (plus ``display_odds``) and NO implied probability is
derived here.

Credentials are injected by the workflow runtime from vault context variables
(MACHINA_CONTEXT_VARIABLE_PROPHETX_*). They are never logged, never echoed in
errors or receipts, and never stored beyond the in-process token cache.
"""

import threading
import time

import requests

BASE_URLS = {
    "sandbox": "https://api.sandbox.prophetx.dev/partner",
    "production": "https://cash.api.prophetx.co/partner",
}

MARKET_API_VERSIONS = ("v1", "v2", "v3", "v4")
DEFAULT_MARKET_VERSION = "v3"
MAX_EVENT_IDS = 50

_TIMEOUT_S = 30
_MAX_RETRIES = 2
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# Auto-Fill deep-link templates (official Auto-Fill Integration Guide).
_AUTOFILL_APP = "prophetx://addtobetslip"
_AUTOFILL_ONELINK = "https://prophetx.onelink.me/E5Yi/autofill"
_AUTOFILL_WEB = "https://www.prophetx.co/"

# Mode-B session cache: (environment, access_key) -> token record.
_token_cache = {}
_token_lock = threading.Lock()


# ============================================================
# Envelope helpers
# ============================================================


def _success(data, message=""):
    return {"status": True, "data": data, "message": message}


def _error(message, error_class="upstream_error", data=None):
    return {"status": False, "data": data, "message": message, "error_class": error_class}


def _sanitize_upstream(body_json, status_code):
    """Build a safe upstream error string — codes and upstream error/message
    fields only; never headers, never credentials."""
    if isinstance(body_json, dict):
        upstream_error = body_json.get("error")
        upstream_message = body_json.get("message")
        detail = " / ".join(str(part) for part in (upstream_error, upstream_message) if part)
        if detail:
            return f"HTTP {status_code}: {detail}"
    return f"HTTP {status_code}"


# ============================================================
# Auth
# ============================================================


def _resolve_environment(params):
    environment = str((params or {}).get("environment", "sandbox")).strip().lower()
    if environment not in BASE_URLS:
        return None, _error(
            f"Unknown environment '{environment}'. Allowed: {', '.join(sorted(BASE_URLS))}.",
            error_class="invalid_request",
        )
    return environment, None


def _auth_header_value(token, auth_scheme):
    if str(auth_scheme).strip().lower() == "bearer":
        return f"Bearer {token}"
    return token


def _login(base_url, access_key, secret_key):
    """POST /auth/login -> token record. Returns (record, error)."""
    try:
        response = requests.post(
            f"{base_url}/auth/login",
            json={"access_key": access_key, "secret_key": secret_key},
            headers={"Accept": "application/json"},
            timeout=_TIMEOUT_S,
        )
    except requests.RequestException as exc:
        return None, _error(f"Login request failed: {exc.__class__.__name__}", error_class="provider_unavailable")
    if response.status_code != 200:
        body = _safe_json(response)
        return None, _error(
            f"Login rejected ({_sanitize_upstream(body, response.status_code)})",
            error_class="credential_invalid",
        )
    body = _safe_json(response) or {}
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict) or not data.get("access_token"):
        return None, _error("Login response missing access_token", error_class="provider_bad_response")
    record = {
        "access_token": data.get("access_token"),
        "access_expire_time": _as_epoch_seconds(data.get("access_expire_time")),
        "refresh_token": data.get("refresh_token"),
        "refresh_expire_time": _as_epoch_seconds(data.get("refresh_expire_time")),
    }
    return record, None


def _refresh(base_url, record):
    """POST /auth/refresh -> updated record or None (caller falls back to login)."""
    refresh_token = (record or {}).get("refresh_token")
    if not refresh_token:
        return None
    try:
        response = requests.post(
            f"{base_url}/auth/refresh",
            json={"refresh_token": refresh_token},
            headers={"Accept": "application/json"},
            timeout=_TIMEOUT_S,
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    body = _safe_json(response) or {}
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict) or not data.get("access_token"):
        return None
    updated = dict(record)
    updated["access_token"] = data.get("access_token")
    updated["access_expire_time"] = _as_epoch_seconds(data.get("access_expire_time"))
    if data.get("refresh_token"):
        updated["refresh_token"] = data.get("refresh_token")
        updated["refresh_expire_time"] = _as_epoch_seconds(data.get("refresh_expire_time"))
    return updated


def _as_epoch_seconds(value):
    """Upstream timestamps have shown ns/ms/s variants — normalize to seconds."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1e17:  # nanoseconds
        return number / 1e9
    if number > 1e14:  # microseconds
        return number / 1e6
    if number > 1e11:  # milliseconds
        return number / 1e3
    return number


def _get_token(environment, base_url, access_key, secret_key):
    """Cached mode-B token with refresh-then-login fallback. Returns (token, error)."""
    cache_key = (environment, access_key)
    now = time.time()
    with _token_lock:
        record = _token_cache.get(cache_key)
    if record:
        expire = record.get("access_expire_time")
        if expire is None or now < expire - 30:
            return record["access_token"], None
        refreshed = _refresh(base_url, record)
        if refreshed:
            with _token_lock:
                _token_cache[cache_key] = refreshed
            return refreshed["access_token"], None
    record, err = _login(base_url, access_key, secret_key)
    if err:
        return None, err
    with _token_lock:
        _token_cache[cache_key] = record
    return record["access_token"], None


def _invalidate_token(environment, access_key):
    with _token_lock:
        _token_cache.pop((environment, access_key), None)


def _resolve_auth(request_data, environment, base_url):
    """Resolve the Authorization header from injected credentials.

    Returns (auth_value, mode, error). mode is 'api_key' or 'session'.
    """
    headers = request_data.get("headers") or {}
    auth_scheme = (request_data.get("params") or {}).get("auth_scheme", "raw")
    api_key = (headers.get("api_key") or "").strip()
    access_key = (headers.get("access_key") or "").strip()
    secret_key = (headers.get("secret_key") or "").strip()

    if api_key:
        return _auth_header_value(api_key, auth_scheme), "api_key", None
    if access_key and secret_key:
        token, err = _get_token(environment, base_url, access_key, secret_key)
        if err:
            return None, "session", err
        return _auth_header_value(token, auth_scheme), "session", None
    return None, None, _error(
        "Credentials missing: provide either 'api_key' or 'access_key'+'secret_key' "
        "(vault context variables MACHINA_CONTEXT_VARIABLE_PROPHETX_*).",
        error_class="credential_missing",
    )


# ============================================================
# HTTP
# ============================================================


def _safe_json(response):
    try:
        return response.json()
    except ValueError:
        return None


def _api_get(request_data, environment, base_url, path, query=None, extra_headers=None):
    """Authenticated GET with bounded retries/backoff and one 401 re-login.

    Returns (payload_json, error).
    """
    auth_value, mode, err = _resolve_auth(request_data, environment, base_url)
    if err:
        return None, err

    relogged = False
    attempt = 0
    while True:
        request_headers = {"Authorization": auth_value, "Accept": "application/json"}
        if extra_headers:
            request_headers.update(extra_headers)
        try:
            response = requests.get(
                f"{base_url}{path}",
                params={k: v for k, v in (query or {}).items() if v is not None and v != ""},
                headers=request_headers,
                timeout=_TIMEOUT_S,
            )
        except requests.RequestException as exc:
            if attempt < _MAX_RETRIES:
                attempt += 1
                time.sleep(min(5.0, 0.5 * (2**attempt)))
                continue
            return None, _error(f"Request failed: {exc.__class__.__name__}", error_class="provider_unavailable")

        if response.status_code == 200:
            body = _safe_json(response)
            if body is None:
                return None, _error("Malformed JSON from upstream", error_class="provider_bad_response")
            return body, None

        body = _safe_json(response)

        if response.status_code == 401 and mode == "session" and not relogged:
            headers = request_data.get("headers") or {}
            _invalidate_token(environment, (headers.get("access_key") or "").strip())
            auth_value, mode, err = _resolve_auth(request_data, environment, base_url)
            if err:
                return None, err
            relogged = True
            continue
        if response.status_code == 401:
            return None, _error(
                f"Unauthorized ({_sanitize_upstream(body, 401)})", error_class="credential_invalid"
            )
        if response.status_code == 403:
            return None, _error(
                f"Forbidden — key/session caps or blocked ({_sanitize_upstream(body, 403)})",
                error_class="credential_invalid",
            )
        if response.status_code in _RETRYABLE_STATUSES and attempt < _MAX_RETRIES:
            attempt += 1
            retry_after = response.headers.get("Retry-After")
            try:
                delay = min(10.0, float(retry_after))
            except (TypeError, ValueError):
                delay = min(10.0, 0.5 * (2**attempt))
            time.sleep(delay)
            continue
        if response.status_code == 429:
            return None, _error(
                f"Rate limited ({_sanitize_upstream(body, 429)})", error_class="provider_rate_limited"
            )
        if response.status_code == 404:
            return None, _error(
                f"Not found ({_sanitize_upstream(body, 404)})", error_class="data_not_found"
            )
        return None, _error(_sanitize_upstream(body, response.status_code))


# ============================================================
# Normalizers (provider-neutral + _raw; no invented fields)
# ============================================================


def _normalize_competitor(competitor):
    return {
        "id": competitor.get("id"),
        "name": competitor.get("display_name") or competitor.get("name", ""),
        "abbreviation": competitor.get("abbreviation", ""),
        "side": competitor.get("side", ""),
        "_raw": competitor,
    }


def _normalize_event(event):
    return {
        "event_id": event.get("event_id"),
        "name": event.get("display_name") or event.get("name", ""),
        "tournament_id": event.get("tournament_id"),
        "tournament": event.get("tournament_name", ""),
        "sport": event.get("sport_name", ""),
        "scheduled": event.get("scheduled", ""),
        "status": event.get("status", ""),
        "type": event.get("type", ""),
        "competitors": [_normalize_competitor(c) for c in event.get("competitors") or []],
        "_raw": event,
    }


def _normalize_selection(selection, api_version):
    """One selection/liquidity level. v4 uses CFTC names — mapped onto the
    same neutral fields; `line_id` is preserved verbatim (handoff currency)."""
    if not isinstance(selection, dict):
        return None
    if api_version == "v4":
        line_id = selection.get("strike_id")
        odds = selection.get("price")
        line = selection.get("strike")
        stake = selection.get("quantity")
        display_odds = selection.get("display_price", "")
        display_line = selection.get("display_strike", "")
    else:
        line_id = selection.get("line_id")
        odds = selection.get("odds")
        line = selection.get("line")
        stake = selection.get("stake")
        display_odds = selection.get("display_odds", "")
        display_line = selection.get("display_line", "")
    return {
        "line_id": line_id,
        "outcome_id": selection.get("outcome_id"),
        "competitor_id": selection.get("competitor_id"),
        "name": selection.get("display_name") or selection.get("name", ""),
        "odds": odds,
        "display_odds": display_odds,
        "line": line,
        "display_line": display_line,
        "stake": stake,
        "updated_at": selection.get("updated_at"),
        "_raw": selection,
    }


def _normalize_selections(raw_selections, api_version):
    """v1/v2: flat list of selections. v3/v4: list of side-groups, each group a
    list of liquidity levels (order-book depth). Output mirrors the input
    nesting so depth is never flattened away."""
    if not isinstance(raw_selections, list):
        return []
    normalized = []
    for item in raw_selections:
        if isinstance(item, list):
            group = [_normalize_selection(level, api_version) for level in item]
            normalized.append([level for level in group if level is not None])
        else:
            level = _normalize_selection(item, api_version)
            if level is not None:
                normalized.append(level)
    return normalized


def _normalize_market(market, event_id, api_version):
    line = market.get("strike") if api_version == "v4" else market.get("line")
    return {
        "id": market.get("id"),
        "market_key": f"{event_id}:{market.get('id')}",
        "event_id": event_id,
        "name": market.get("display_name") or market.get("name", ""),
        "group_name": market.get("group_name", ""),
        "type": market.get("type", ""),
        "sub_type": market.get("sub_type", ""),
        "category": market.get("category_name", ""),
        "player_id": market.get("player_id"),
        "favourite": bool(market.get("favourite")),
        "line": line,
        "selections": _normalize_selections(market.get("selections"), api_version),
        "api_version": api_version,
        "_raw": market,
    }


def _extract_markets_payload(payload):
    """Single-event markets: {"data": {"event_id": ..., "markets": [...]}}."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        markets = data.get("markets")
        if isinstance(markets, list):
            return data.get("event_id"), markets
        if markets is None:
            return data.get("event_id"), []
    if isinstance(data, list):
        return None, data
    return None, None


def _extract_multiple_markets_payload(payload, requested_ids):
    """Multiple-events markets: officially a dict keyed by event id, but 'a
    small number of responses may come back as a flat list' (official guide).
    The spec schema is empty, so both shapes are handled. Returns dict
    str(event_id) -> [raw markets] or None on drift."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        grouped = {}
        for key, value in data.items():
            if not isinstance(value, list):
                return None
            grouped[str(key)] = value
        return grouped
    if isinstance(data, list):
        grouped = {str(eid): [] for eid in requested_ids}
        orphans = []
        for market in data:
            event_id = market.get("sport_event_id") or market.get("sportEventId") or market.get("event_id")
            if event_id is not None and str(event_id) in grouped:
                grouped[str(event_id)].append(market)
            else:
                orphans.append(market)
        if orphans:
            grouped.setdefault("_unattributed", []).extend(orphans)
        return grouped
    return None


# ============================================================
# Commands — read-only Affiliate endpoints
# ============================================================


def get_tournaments(request_data):
    """List tournaments (leagues/competitions).

    headers: api_key OR access_key+secret_key (vault-injected)
    params:
        environment (str): 'sandbox' (default) or 'production'
        has_active_events (bool): only tournaments with active events
        auth_scheme (str): 'raw' (default) or 'bearer'
        normalize (bool): default True
    """
    try:
        params = request_data.get("params") or {}
        environment, err = _resolve_environment(params)
        if err:
            return err
        base_url = BASE_URLS[environment]
        query = {}
        if params.get("has_active_events") is not None:
            query["has_active_events"] = str(bool(params["has_active_events"])).lower()
        payload, err = _api_get(request_data, environment, base_url, "/affiliate/get_tournaments", query)
        if err:
            return err
        data = payload.get("data") if isinstance(payload, dict) else None
        tournaments = (data or {}).get("tournaments") if isinstance(data, dict) else None
        if tournaments is None:
            tournaments = data if isinstance(data, list) else []
        if not isinstance(tournaments, list):
            return _error("Unexpected tournaments payload shape", error_class="provider_bad_response")
        return _success(
            {"tournaments": tournaments, "count": len(tournaments), "environment": environment},
            f"Retrieved {len(tournaments)} tournaments",
        )
    except Exception as exc:  # noqa: BLE001 - connector must fail gracefully
        return _error(f"Error fetching tournaments: {exc.__class__.__name__}: {exc}")


def get_sport_events(request_data):
    """List sport events for a tournament (or explicit event ids).

    params:
        environment (str): 'sandbox' (default) or 'production'
        tournament_id (int): tournament filter (e.g. MLB=109, NFL=31, NBA=132)
        event_ids (list[int]): explicit event ids (alternative to tournament_id)
        normalize (bool): default True
    """
    try:
        params = request_data.get("params") or {}
        environment, err = _resolve_environment(params)
        if err:
            return err
        tournament_id = params.get("tournament_id")
        event_ids = params.get("event_ids") or []
        if tournament_id in (None, "") and not event_ids:
            return _error("tournament_id or event_ids is required", error_class="invalid_request")
        query = {}
        if tournament_id not in (None, ""):
            query["tournament_id"] = tournament_id
        if event_ids:
            query["event_ids"] = ",".join(str(eid) for eid in event_ids)
        payload, err = _api_get(
            request_data, environment, BASE_URLS[environment], "/affiliate/get_sport_events", query
        )
        if err:
            return err
        data = payload.get("data") if isinstance(payload, dict) else None
        events = (data or {}).get("sport_events") if isinstance(data, dict) else None
        if events is None:
            events = data if isinstance(data, list) else []
        if not isinstance(events, list):
            return _error("Unexpected sport_events payload shape", error_class="provider_bad_response")
        normalized = [_normalize_event(e) for e in events] if _want_normalize(params) else events
        return _success(
            {"sport_events": normalized, "count": len(normalized), "environment": environment},
            f"Retrieved {len(normalized)} sport events",
        )
    except Exception as exc:  # noqa: BLE001
        return _error(f"Error fetching sport events: {exc.__class__.__name__}: {exc}")


def _want_normalize(params):
    value = params.get("normalize", True)
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no")
    return bool(value)


def _resolve_market_version(params):
    api_version = str(params.get("api_version", DEFAULT_MARKET_VERSION)).strip().lower()
    if api_version not in MARKET_API_VERSIONS:
        return None, _error(
            f"api_version must be one of {', '.join(MARKET_API_VERSIONS)}", error_class="invalid_request"
        )
    return api_version, None


def _market_path(api_version, multiple=False):
    suffix = "get_multiple_markets" if multiple else "get_markets"
    if api_version == "v1":
        return f"/affiliate/{suffix}"
    return f"/{api_version}/affiliate/{suffix}"


def _market_query(params):
    query = {}
    if params.get("get_all_market") is not None:
        query["get_all_market"] = str(bool(params["get_all_market"])).lower()
    if params.get("market_types"):
        value = params["market_types"]
        query["market_types"] = ",".join(value) if isinstance(value, list) else str(value)
    if params.get("min_liquidity") is not None:
        query["min_liquidity"] = params["min_liquidity"]
    return query


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("", "false", "0", "no")
    return bool(value)


def _cftc_headers(params, api_version):
    """X-CFTC-Terminology opt-in is documented for v3 only."""
    if api_version == "v3" and _as_bool(params.get("cftc_terminology"), default=False):
        return {"X-CFTC-Terminology": "true"}
    return None


def get_markets(request_data):
    """Markets (with odds/liquidity) for one event.

    params:
        environment (str): 'sandbox' (default) or 'production'
        event_id (int): required
        api_version (str): v1|v2|v3|v4 (default v3 — liquidity levels;
            v4 = CFTC naming, normalized onto the same neutral fields)
        get_all_market (bool), market_types (csv|list), min_liquidity (number)
        cftc_terminology (bool): v3 only — sends X-CFTC-Terminology: true
        normalize (bool): default True (raw payload always kept under _raw)
    """
    try:
        params = request_data.get("params") or {}
        environment, err = _resolve_environment(params)
        if err:
            return err
        event_id = params.get("event_id")
        if event_id in (None, ""):
            return _error("event_id is required", error_class="invalid_request")
        api_version, err = _resolve_market_version(params)
        if err:
            return err
        query = {"event_id": event_id}
        query.update(_market_query(params))
        payload, err = _api_get(
            request_data,
            environment,
            BASE_URLS[environment],
            _market_path(api_version),
            query,
            extra_headers=_cftc_headers(params, api_version),
        )
        if err:
            return err
        payload_event_id, markets = _extract_markets_payload(payload)
        if markets is None:
            return _error("Unexpected markets payload shape", error_class="provider_bad_response")
        resolved_event_id = payload_event_id or event_id
        if _want_normalize(params):
            markets = [_normalize_market(m, resolved_event_id, api_version) for m in markets]
        return _success(
            {
                "markets": markets,
                "count": len(markets),
                "event_id": resolved_event_id,
                "api_version": api_version,
                "environment": environment,
            },
            f"Retrieved {len(markets)} markets",
        )
    except Exception as exc:  # noqa: BLE001
        return _error(f"Error fetching markets: {exc.__class__.__name__}: {exc}")


def get_multiple_markets(request_data):
    """Markets for up to 50 events in one call (dual-shape tolerant).

    params:
        environment (str): 'sandbox' (default) or 'production'
        event_ids (list[int]): required, 1..50 ids
        api_version (str): v1|v2|v3|v4 (default v3)
        get_all_market, market_types, min_liquidity, cftc_terminology, normalize
    """
    try:
        params = request_data.get("params") or {}
        environment, err = _resolve_environment(params)
        if err:
            return err
        event_ids = params.get("event_ids") or []
        if isinstance(event_ids, str):
            event_ids = [part.strip() for part in event_ids.split(",") if part.strip()]
        if not event_ids:
            return _error("event_ids is required (1..50 ids)", error_class="invalid_request")
        if len(event_ids) > MAX_EVENT_IDS:
            return _error(
                f"event_ids accepts at most {MAX_EVENT_IDS} ids per call (got {len(event_ids)}); "
                "split into batches",
                error_class="invalid_request",
            )
        api_version, err = _resolve_market_version(params)
        if err:
            return err
        query = {"event_ids": ",".join(str(eid) for eid in event_ids)}
        query.update(_market_query(params))
        payload, err = _api_get(
            request_data,
            environment,
            BASE_URLS[environment],
            _market_path(api_version, multiple=True),
            query,
            extra_headers=_cftc_headers(params, api_version),
        )
        if err:
            return err
        grouped = _extract_multiple_markets_payload(payload, event_ids)
        if grouped is None:
            return _error("Unexpected multiple-markets payload shape", error_class="provider_bad_response")
        if _want_normalize(params):
            grouped = {
                key: [_normalize_market(m, key, api_version) for m in markets]
                for key, markets in grouped.items()
            }
        total = sum(len(markets) for markets in grouped.values())
        return _success(
            {
                "markets_by_event": grouped,
                "event_count": len([k for k in grouped if k != "_unattributed"]),
                "market_count": total,
                "api_version": api_version,
                "environment": environment,
            },
            f"Retrieved {total} markets across {len(grouped)} events",
        )
    except Exception as exc:  # noqa: BLE001
        return _error(f"Error fetching multiple markets: {exc.__class__.__name__}: {exc}")


def build_autofill_link(request_data):
    """Build the official ProphetX Auto-Fill handoff links (pure — no network).

    Machina's involvement in bet placement ends at these links: account,
    geolocation, wallet, and wager execution are entirely ProphetX's.

    params:
        line_id (str): single selection line id (or use line_ids)
        line_ids (list[str]): multiple selections
        partner_id (str): required — attribution identifier
        odds: optional odds hint passed through to the betslip
    """
    try:
        params = request_data.get("params") or {}
        partner_id = str(params.get("partner_id") or "").strip()
        if not partner_id:
            return _error("partner_id is required for attribution", error_class="invalid_request")
        line_ids = params.get("line_ids") or []
        if isinstance(line_ids, str):
            line_ids = [part.strip() for part in line_ids.split(",") if part.strip()]
        single = str(params.get("line_id") or "").strip()
        if single and not line_ids:
            line_ids = [single]
        if not line_ids:
            return _error("line_id or line_ids is required", error_class="invalid_request")
        line_ids = [str(item) for item in line_ids]
        primary = line_ids[0]
        joined = ",".join(line_ids)
        odds = params.get("odds")

        app_query = f"line_id={primary}&line_ids={joined}&partner_id={partner_id}"
        web_query = f"action=addtobetslip&line_id={primary}&line_ids={joined}&partner_id={partner_id}"
        onelink_query = (
            f"deep_link_value=addtobetslip&deep_link_sub1={partner_id}"
            f"&deep_link_sub2={joined}"
        )
        if odds is not None:
            app_query += f"&odds={odds}"
            web_query += f"&odds={odds}"
            onelink_query += f"&deep_link_sub3={odds}"

        return _success(
            {
                "app_link": f"{_AUTOFILL_APP}?{app_query}",
                "onelink": f"{_AUTOFILL_ONELINK}?{onelink_query}",
                "web_link": f"{_AUTOFILL_WEB}?{web_query}",
                "line_ids": line_ids,
                "partner_id": partner_id,
            },
            "Auto-Fill links built (handoff only — no wager is executed by Machina)",
        )
    except Exception as exc:  # noqa: BLE001
        return _error(f"Error building Auto-Fill link: {exc.__class__.__name__}: {exc}")


def health(request_data):
    """Credential + reachability check: one bounded GET (tournaments).

    params:
        environment (str): 'sandbox' (default) or 'production'
        auth_scheme (str): 'raw' (default) or 'bearer'
    """
    result = get_tournaments(request_data)
    if not result.get("status"):
        return result
    data = result.get("data") or {}
    return _success(
        {
            "healthy": True,
            "environment": data.get("environment"),
            "tournament_count": data.get("count", 0),
        },
        "ProphetX Affiliate API reachable and credentials accepted",
    )
