"""Live Tennis API connector (pyscript) — read-only HTTP wrapper.

Vendor disclosure: this connector is contributed by the Live Tennis API
team (https://livetennisapi.com). It wraps our own public REST API.

Design:
- One `get_*` command per documented read endpoint plus a bounded
  generic `invoke_request` (GET only, allow-listed paths). Nothing here
  places an order, moves money or writes to the provider.
- The API key is never read from the repository or the environment. It
  arrives per call from the workflow's `context-variables` (a Machina
  vault secret, `$TEMP_CONTEXT_VARIABLE_LIVE_TENNIS_API_KEY`) as
  `params.api_key`, and is sent as the `X-API-Key` header.
- No retries. The FREE tier is 30 requests/minute and 100 requests/day;
  a retry loop on a 429 would burn the daily budget. A non-2xx answer is
  returned as `{"status": False, ...}` with the provider's stable error
  code and, on 429, the `Retry-After` / `resets_at` hints so a workflow
  can decide what to do.
- Provider payloads are returned unmodified under named keys
  (`matches`, `match`, `score`, `fixtures`, ...). The only derived data
  is the optional `derived` block `get_live_matches` attaches beside
  each match (break-point flag), which is also exposed on its own as the
  offline `derive_match_state` command.

API reference: https://docs.livetennisapi.com (OpenAPI:
https://docs.livetennisapi.com/openapi.yaml). Base URL verified against
that spec on 2026-09-12.
"""

import requests

BASE_URL = "https://api.livetennisapi.com/api/public/v1"
DEFAULT_TIMEOUT = 30
USER_AGENT = "machina-templates/live-tennis-api"

# Read-only paths `invoke_request` may call. Path templates use `{id}` for
# the single path parameter. Anything not listed is refused before any
# network call — the connector never reaches webhooks, ws-token or any
# non-GET route.
ALLOWED_PATHS = (
    "/health",
    "/matches",
    "/matches/{id}",
    "/matches/{id}/score",
    "/matches/{id}/events",
    "/matches/{id}/status-history",
    "/matches/{id}/analysis",
    "/matches/{id}/statistics",
    "/matches/{id}/points",
    "/players",
    "/players/{id}",
    "/tournaments",
    "/tournaments/{id}",
    "/fixtures",
    "/rankings",
    "/h2h",
    "/usage",
    "/history/matches",
    "/history/matches/{id}",
    "/history/coverage",
    "/history/archive/matches",
    "/history/archive/matches/{id}",
    "/history/archive/players",
    "/history/archive/career",
    "/markets",
    "/markets/{id}/prices",
    "/matches/{id}/prices",
)

TOURS = ("atp", "wta", "challenger", "itf", "juniors")
DRAWS = ("singles", "doubles")
MATCH_STATUSES = ("live", "upcoming", "completed", "cancelled")

# In-game point strings the provider uses outside a tiebreak.
_GAME_POINTS = ("0", "15", "30", "40", "AD")


# --------------------------------------------------------------------------
# Request plumbing
# --------------------------------------------------------------------------


def _params(request_data):
    """The `params` dict of a Machina pyscript call, tolerant of a bare dict."""
    if not isinstance(request_data, dict):
        return {}
    params = request_data.get("params")
    return params if isinstance(params, dict) else request_data


def _api_key(request_data):
    """Resolve the API key from params, then from the headers block.

    `context-variables` normally lands in `params` (`api_key: "$.get('api_key')"`
    in the task inputs); some runtimes forward the connector's
    context-variables as `headers`. Both are accepted; nothing else is.
    """
    params = _params(request_data)
    key = params.get("api_key")
    if not key and isinstance(request_data, dict):
        headers = request_data.get("headers")
        if isinstance(headers, dict):
            key = headers.get("api_key") or headers.get("X-API-Key") or headers.get("x-api-key")
    if isinstance(key, str):
        key = key.strip()
    return key or None


def _error(message, **data):
    return {"status": False, "message": message, "data": data}


def _clean_query(query):
    """Drop None / empty-string values; keep 0 and False; join lists as repeats."""
    out = {}
    for name, value in (query or {}).items():
        if value is None or value == "":
            continue
        if isinstance(value, (list, tuple)):
            items = [v for v in value if v is not None and v != ""]
            if items:
                out[name] = items
            continue
        out[name] = value
    return out


def _resolve_path(path, path_id=None):
    """Return the concrete path for an allow-listed template, or None."""
    if not isinstance(path, str) or not path.startswith("/"):
        return None
    path = path.rstrip("/") or "/"
    if path in ALLOWED_PATHS and "{id}" not in path:
        return path
    if path_id is None or path_id == "":
        return None
    for template in ALLOWED_PATHS:
        if template == path and "{id}" in template:
            return template.replace("{id}", str(path_id))
    return None


def _rate_limit_hints(response, body):
    hints = {}
    retry_after = response.headers.get("Retry-After") if getattr(response, "headers", None) else None
    if retry_after is not None:
        hints["retry_after"] = retry_after
    if isinstance(body, dict):
        for key in ("scope", "limit_per_day", "resets_at", "retry_at_epoch", "tier", "upgrade_url"):
            if body.get(key) is not None:
                hints[key] = body.get(key)
    return hints


def _request(api_key, path, query=None, timeout=DEFAULT_TIMEOUT):
    """One GET against the API. Never retries. Returns the connector envelope."""
    if not api_key:
        return _error(
            "api_key is required. Store it in the Machina vault as "
            "TEMP_CONTEXT_VARIABLE_LIVE_TENNIS_API_KEY and pass it through "
            "context-variables; never commit it.",
            error="missing_api_key",
        )

    url = f"{BASE_URL}{path}"
    headers = {"X-API-Key": api_key, "Accept": "application/json", "User-Agent": USER_AGENT}

    try:
        response = requests.get(url, params=_clean_query(query), headers=headers, timeout=timeout)
    except requests.exceptions.Timeout:
        return _error(f"Request timed out after {timeout}s", error="timeout", path=path)
    except requests.exceptions.RequestException as exc:
        return _error(f"Request failed: {exc}", error="request_failed", path=path)

    try:
        body = response.json()
    except ValueError:
        body = None

    status_code = response.status_code
    if 200 <= status_code < 300:
        if body is None:
            return _error("Non-JSON body on a 2xx response", error="bad_json", path=path,
                          status_code=status_code, raw_response=(response.text or "")[:500])
        return {"status": True, "data": body}

    code = body.get("error") if isinstance(body, dict) else None
    detail = body.get("detail") if isinstance(body, dict) else None
    data = {"status_code": status_code, "error": code, "detail": detail, "path": path}
    if isinstance(body, dict) and body.get("allowed") is not None:
        data["allowed"] = body.get("allowed")

    if status_code == 429:
        data.update(_rate_limit_hints(response, body))
        scope = data.get("scope")
        if code == "abuse_throttled":
            message = "Blocked for hammering past the cap (abuse_throttled). Fix the loop; do not retry."
        elif scope == "day":
            message = f"Daily quota exhausted; resets at {data.get('resets_at')}. Do not retry before then."
        else:
            message = f"Per-minute rate limit exceeded; Retry-After {data.get('retry_after')}s."
        return {"status": False, "message": message, "data": data}

    if status_code == 401:
        message = "Unauthorized: the API key is missing, unknown or disabled."
    elif status_code == 403:
        message = f"Your plan does not unlock this endpoint ({code or 'upgrade_required'})."
    elif status_code == 404:
        message = "No such resource, or no data yet."
    elif status_code == 410:
        message = "This match id was merged into another match record; read `merged_into` from the body."
        if isinstance(body, dict):
            data["body"] = body
    elif status_code == 400:
        message = f"Bad query parameter: {code or ''} {detail or ''}".strip()
    else:
        message = f"HTTP {status_code} from the Live Tennis API ({code or 'unknown_error'})."
        if not isinstance(body, dict):
            data["raw_response"] = (response.text or "")[:500]
    return {"status": False, "message": message, "data": data}


def _envelope(result, key):
    """Re-key a successful provider body under `key` (lists keep `meta`)."""
    if not result.get("status"):
        return result
    body = result["data"]
    if isinstance(body, dict) and isinstance(body.get("data"), list):
        return {"status": True, "data": {key: body["data"], "meta": body.get("meta") or {}}}
    return {"status": True, "data": {key: body}}


def _int_or_none(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _enum_or_none(value, allowed):
    if value is None or value == "":
        return None
    value = str(value).strip().lower()
    return value if value in allowed else None


# --------------------------------------------------------------------------
# Derivations (offline, pure)
# --------------------------------------------------------------------------


def is_break_point(score):
    """True when the receiver is one point from breaking serve.

    Returns None when the state is unknown: no score, no server, a
    missing / null / non-standard point string. A tiebreak is never a
    break point (there is no service game to break), so it returns False.
    Break point = receiver at AD, or receiver at 40 while the server is at
    0, 15 or 30. Deuce (40-40) and AD-server are not break points.
    """
    if not isinstance(score, dict):
        return None
    if score.get("is_tiebreak") is True:
        return False
    server = score.get("server")
    if server not in (1, 2):
        return None
    points = score.get("points")
    if not isinstance(points, (list, tuple)) or len(points) != 2:
        return None
    p_server = points[server - 1]
    p_receiver = points[2 - server]
    if p_server is None or p_receiver is None:
        return None
    p_server, p_receiver = str(p_server), str(p_receiver)
    if p_server not in _GAME_POINTS or p_receiver not in _GAME_POINTS:
        return None
    if p_receiver == "AD":
        return True
    if p_receiver == "40" and p_server in ("0", "15", "30"):
        return True
    return False


def derive_match_state(request_data):
    """Offline derivation over one Score object (no API call).

    Params:
        score (dict): a `score` object as returned on any match payload
            (`sets`, `games`, `points`, `server`, `is_tiebreak`).

    Returns `{"status": True, "data": {"state": {...}}}` where `state` has
    `break_point` (bool|None), `server`, `receiver`, `is_tiebreak`,
    `points_server`, `points_receiver`.
    """
    params = _params(request_data)
    score = params.get("score")
    if score is not None and not isinstance(score, dict):
        return _error("score must be an object", error="bad_score")
    return {"status": True, "data": {"state": _state(score)}}


def _state(score):
    server = score.get("server") if isinstance(score, dict) else None
    server = server if server in (1, 2) else None
    receiver = (3 - server) if server else None
    points = score.get("points") if isinstance(score, dict) else None
    if not isinstance(points, (list, tuple)) or len(points) != 2:
        points = [None, None]
    return {
        "break_point": is_break_point(score),
        "server": server,
        "receiver": receiver,
        "is_tiebreak": bool(score.get("is_tiebreak")) if isinstance(score, dict) else None,
        "points_server": points[server - 1] if server else None,
        "points_receiver": points[receiver - 1] if receiver else None,
    }


def _with_derived(match):
    if not isinstance(match, dict):
        return match
    enriched = dict(match)
    enriched["derived"] = _state(match.get("score"))
    return enriched


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def get_usage(request_data):
    """GET /usage — your own usage vs quota (FREE, any tier). One request.

    Params: api_key (str, required).
    Returns data.usage = {principal, tier, limits, today, ...}.
    """
    return _envelope(_request(_api_key(request_data), "/usage"), "usage")


def get_live_matches(request_data):
    """GET /matches?status=live — every match currently in play (FREE).

    Params:
        api_key (str, required)
        tour (str, optional): atp | wta | challenger | itf | juniors
        draw (str, optional): singles | doubles
        limit (int, optional, default 50, max 200), offset (int, optional)

    Returns data.matches (each match unmodified, plus a `derived` block with
    `break_point`), data.meta (limit/offset/count/total/has_more).
    """
    params = _params(request_data)
    query = {
        "status": "live",
        "tour": _enum_or_none(params.get("tour"), TOURS),
        "draw": _enum_or_none(params.get("draw"), DRAWS),
        "limit": _int_or_none(params.get("limit")),
        "offset": _int_or_none(params.get("offset")),
    }
    result = _envelope(_request(_api_key(request_data), "/matches", query), "matches")
    if result.get("status"):
        result["data"]["matches"] = [_with_derived(m) for m in result["data"]["matches"]]
    return result


def get_matches(request_data):
    """GET /matches — list matches by lifecycle status.

    Params:
        api_key (str, required)
        status (str, optional, default live): live | upcoming (FREE);
            completed | cancelled (BASIC+, history product)
        tour, draw, player (id or list of ids), country (3-letter lowercase),
        tournament_id, from, to (YYYY-MM-DD or ISO-8601 UTC),
        updated_since + cursor (change feed), limit, offset

    Returns data.matches (unmodified), data.meta.
    """
    params = _params(request_data)
    query = {
        "status": _enum_or_none(params.get("status"), MATCH_STATUSES) or "live",
        "tour": _enum_or_none(params.get("tour"), TOURS),
        "draw": _enum_or_none(params.get("draw"), DRAWS),
        "player": params.get("player"),
        "country": params.get("country"),
        "tournament_id": params.get("tournament_id"),
        "from": params.get("from"),
        "to": params.get("to"),
        "updated_since": params.get("updated_since"),
        "cursor": params.get("cursor"),
        "limit": _int_or_none(params.get("limit")),
        "offset": _int_or_none(params.get("offset")),
    }
    return _envelope(_request(_api_key(request_data), "/matches", query), "matches")


def get_match(request_data):
    """GET /matches/{matchId} — full match detail (FREE; embeds need PRO/ULTRA).

    Params: api_key (str, required), match_id (int, required).
    Returns data.match (unmodified) plus data.derived (break-point state).
    """
    params = _params(request_data)
    match_id = _int_or_none(params.get("match_id"))
    if match_id is None:
        return _error("match_id (integer) is required", error="missing_match_id")
    result = _envelope(_request(_api_key(request_data), f"/matches/{match_id}"), "match")
    if result.get("status"):
        match = result["data"]["match"]
        result["data"]["derived"] = _state(match.get("score") if isinstance(match, dict) else None)
    return result


def get_match_score(request_data):
    """GET /matches/{matchId}/score — current score only, lowest-latency read (FREE).

    Params: api_key (str, required), match_id (int, required).
    Returns data.score (unmodified) plus data.derived (break-point state).
    """
    params = _params(request_data)
    match_id = _int_or_none(params.get("match_id"))
    if match_id is None:
        return _error("match_id (integer) is required", error="missing_match_id")
    result = _envelope(_request(_api_key(request_data), f"/matches/{match_id}/score"), "score")
    if result.get("status"):
        result["data"]["derived"] = _state(result["data"]["score"])
    return result


def get_fixtures(request_data):
    """GET /fixtures — upcoming scheduled fixtures, earliest first (FREE).

    Params: api_key (required), tour, draw, limit, offset (optional).
    Returns data.fixtures, data.meta.
    """
    params = _params(request_data)
    query = {
        "tour": _enum_or_none(params.get("tour"), TOURS),
        "draw": _enum_or_none(params.get("draw"), DRAWS),
        "limit": _int_or_none(params.get("limit")),
        "offset": _int_or_none(params.get("offset")),
    }
    return _envelope(_request(_api_key(request_data), "/fixtures", query), "fixtures")


def search_players(request_data):
    """GET /players — search players by name (FREE).

    Params: api_key (required), search (str), limit, offset.
    Returns data.players, data.meta.
    """
    params = _params(request_data)
    query = {
        "search": params.get("search") or params.get("name"),
        "limit": _int_or_none(params.get("limit")),
        "offset": _int_or_none(params.get("offset")),
    }
    return _envelope(_request(_api_key(request_data), "/players", query), "players")


def get_player(request_data):
    """GET /players/{playerId} — one player's bio, ranking and cached stats (FREE).

    Params: api_key (required), player_id (int, required).
    Returns data.player.
    """
    params = _params(request_data)
    player_id = _int_or_none(params.get("player_id"))
    if player_id is None:
        return _error("player_id (integer) is required", error="missing_player_id")
    return _envelope(_request(_api_key(request_data), f"/players/{player_id}"), "player")


def get_tournaments(request_data):
    """GET /tournaments — the tournament catalogue `Match.tournament_id` joins (FREE).

    Params: api_key (required), search (substring), tour, draw, limit, offset.
    Returns data.tournaments, data.meta.
    """
    params = _params(request_data)
    query = {
        "search": params.get("search"),
        "tour": _enum_or_none(params.get("tour"), TOURS),
        "draw": _enum_or_none(params.get("draw"), DRAWS),
        "limit": _int_or_none(params.get("limit")),
        "offset": _int_or_none(params.get("offset")),
    }
    return _envelope(_request(_api_key(request_data), "/tournaments", query), "tournaments")


def get_rankings(request_data):
    """GET /rankings — rank-ordered listing (PRO) or per-player as-of records (ULTRA).

    Params:
        api_key (required)
        system (str or list): e.g. atp, wta, elo — listing mode needs exactly one
        tour (str): atp | wta — required for an elo listing
        player (id or list of ids): per-player mode (ULTRA)
        as_of (YYYY-MM-DD), surface, min_matches, activity_weeks, limit, offset

    Returns data.rankings, data.meta. A FREE key gets a 403 here — the
    connector reports it, it does not retry.
    """
    params = _params(request_data)
    query = {
        "system": params.get("system"),
        "tour": _enum_or_none(params.get("tour"), ("atp", "wta")),
        "player": params.get("player"),
        "as_of": params.get("as_of"),
        "surface": params.get("surface"),
        "min_matches": _int_or_none(params.get("min_matches")),
        "activity_weeks": _int_or_none(params.get("activity_weeks")),
        "limit": _int_or_none(params.get("limit")),
        "offset": _int_or_none(params.get("offset")),
    }
    return _envelope(_request(_api_key(request_data), "/rankings", query), "rankings")


def get_head_to_head(request_data):
    """GET /h2h — head-to-head record between two players (BASIC+).

    Params: api_key (required), p1 (name fragment, min 3 chars), p2 (same).
    Returns data.h2h = {players, totals, by_surface, meetings, stats}.
    """
    params = _params(request_data)
    p1, p2 = params.get("p1"), params.get("p2")
    if not p1 or not p2 or len(str(p1)) < 3 or len(str(p2)) < 3:
        return _error("p1 and p2 name fragments (min 3 characters each) are required", error="missing_players")
    return _envelope(_request(_api_key(request_data), "/h2h", {"p1": p1, "p2": p2}), "h2h")


def invoke_request(request_data):
    """Generic read-only GET against an allow-listed path.

    Params:
        api_key (str, required)
        path (str, required): one of ALLOWED_PATHS, e.g. "/matches/{id}/events"
        path_id (str|int): fills `{id}` when the path has one
        query (dict, optional): query parameters, passed through

    Returns data.response = the provider body, unmodified. Any path outside
    the allow-list (webhooks, ws-token, non-GET routes) is refused locally.
    """
    params = _params(request_data)
    path = _resolve_path(params.get("path"), params.get("path_id"))
    if path is None:
        return _error(
            "path must be one of the read-only allow-listed routes (with path_id when it has an {id})",
            error="path_not_allowed",
            allowed=list(ALLOWED_PATHS),
        )
    query = params.get("query")
    if query is not None and not isinstance(query, dict):
        return _error("query must be an object", error="bad_query")
    result = _request(_api_key(request_data), path, query)
    if not result.get("status"):
        return result
    return {"status": True, "data": {"response": result["data"]}}
