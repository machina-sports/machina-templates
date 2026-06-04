"""World Cup market-intelligence connector utilities.

This connector intentionally performs only read-only normalization/filtering. It
accepts payloads returned by the shared `sports-skills` connector and converts
Kalshi/Polymarket market records into a stable shape for API/MCP/x402 exposure.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


WORLD_CUP_TERMS = (
    "world cup",
    "fifa",
    "2026 world cup",
    "fifa world cup",
)


def _params(request_data: dict[str, Any]) -> dict[str, Any]:
    return dict(request_data.get("params") or {})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _unwrap(payload: Any) -> Any:
    """Unwrap connector envelopes and pydantic-ish objects."""
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    elif hasattr(payload, "dict"):
        payload = payload.dict()
    if isinstance(payload, dict) and "data" in payload and set(payload.keys()) & {"status", "message"}:
        return payload.get("data") or {}
    return payload or {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        # Common Sports Skills shape: {markets: [...]}.
        if isinstance(value.get("markets"), list):
            return value["markets"]
        if isinstance(value.get("events"), list):
            return value["events"]
    return []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _to_float(value: Any) -> float:
    """Coerce provider volume/liquidity values to float; non-numeric becomes 0.0."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_status(source: str, record: dict[str, Any]) -> str:
    raw = _lower(_first(record, "status", "state", "market_status"))
    if raw in {"active", "open", "live", "trading"}:
        return "open"
    if raw in {"closed", "settled", "resolved", "finalized"}:
        return "closed"
    if source == "polymarket":
        if record.get("closed") is True:
            return "closed"
        if record.get("active") is True:
            return "open"
    return raw or "unknown"


def _normalize_probability(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    # Kalshi often returns cents; Polymarket usually returns 0..1.
    if numeric > 1:
        numeric = numeric / 100.0
    if numeric < 0 or numeric > 1:
        return None
    return round(numeric, 6)


def _normalize_outcome(source: str, outcome: Any) -> dict[str, Any] | None:
    if isinstance(outcome, str):
        return {"name": outcome, "price": None, "token_id": None, "source_outcome_id": outcome}
    if not isinstance(outcome, dict):
        return None
    name = _first(outcome, "name", "outcome", "title", "side", "label")
    price = _normalize_probability(_first(outcome, "price", "probability", "last_price", "yes_price"))
    token_id = _first(outcome, "clob_token_id", "token_id", "token", "ticker", "id")
    return {
        "name": _text(name) or "unknown",
        "price": price,
        "token_id": _text(token_id) or None,
        "source_outcome_id": _text(_first(outcome, "id", "ticker", "token_id", "clob_token_id")) or None,
    }


def _kalshi_outcomes(record: dict[str, Any]) -> list[dict[str, Any]]:
    outcomes = _as_list(record.get("outcomes"))
    normalized = [_normalize_outcome("kalshi", outcome) for outcome in outcomes]
    normalized = [outcome for outcome in normalized if outcome]
    if normalized:
        return normalized

    yes_price = _normalize_probability(
        _first(record, "yes_price", "yes_ask", "yes_bid", "last_price", "price")
    )
    no_price = _normalize_probability(_first(record, "no_price", "no_ask", "no_bid"))
    if no_price is None and yes_price is not None:
        no_price = round(1 - yes_price, 6)
    results = []
    if yes_price is not None:
        results.append({"name": "Yes", "price": yes_price, "token_id": None, "source_outcome_id": "yes"})
    if no_price is not None:
        results.append({"name": "No", "price": no_price, "token_id": None, "source_outcome_id": "no"})
    return results


def _polymarket_outcomes(record: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = []
    outcomes = _as_list(record.get("outcomes"))
    raw_token_ids = record.get("clob_token_ids")
    token_ids: list[Any] = raw_token_ids if isinstance(raw_token_ids, list) else []
    for index, outcome in enumerate(outcomes):
        item = _normalize_outcome("polymarket", outcome)
        if item and not item.get("token_id") and index < len(token_ids):
            item["token_id"] = _text(token_ids[index])
        if item:
            normalized.append(item)
    return normalized


def _normalize_record(source: str, record: dict[str, Any], fetched_at: str) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    source_market_id = _first(
        record,
        "market_id",
        "id",
        "ticker",
        "market_ticker",
        "condition_id",
        "slug",
    )
    title = _first(record, "title", "question", "name", "subtitle", "event_title")
    if not source_market_id and not title:
        return None

    source_event_id = _first(record, "event_id", "event_ticker", "game_id", "series_ticker")
    outcomes = _polymarket_outcomes(record) if source == "polymarket" else _kalshi_outcomes(record)
    status = _normalize_status(source, record)
    if source_market_id:
        cache_key = _text(source_market_id)
    else:
        # Title fallback: include the event id so same-title markets don't collide.
        cache_key = _text(title).lower().replace(" ", "-")[:80]
        if source_event_id:
            cache_key = f"{cache_key}:{_text(source_event_id)}"
    cache_id = f"{source}:{cache_key}"

    return {
        # `metadata` is the document-store bulk-update upsert key (the engine
        # filters on {metadata, name}), so re-syncs overwrite the same cache
        # row instead of collapsing all items into one document.
        "metadata": {"cache_id": cache_id},
        "id": cache_id,
        "cache_id": cache_id,
        "source": source,
        "source_market_id": _text(source_market_id) or None,
        "source_event_id": _text(source_event_id) or None,
        "title": _text(title),
        "description": _text(_first(record, "description", "rules", "subtitle")) or None,
        "slug": _text(_first(record, "slug", "ticker", "market_ticker")) or None,
        "status": status,
        "market_type": _text(_first(record, "sports_market_type", "type", "category", "market_type")) or None,
        "outcomes": outcomes,
        "volume": _first(record, "volume", "volume_24h", "dollar_volume"),
        "liquidity": _first(record, "liquidity", "open_interest"),
        "spread": _first(record, "spread", "bid_ask_spread"),
        "start_time": _first(record, "start_date", "start_time", "open_time"),
        "end_time": _first(record, "end_date", "close_time", "expiration_time", "expected_expiration_time"),
        "updated_at": _first(record, "updated_at", "last_update_time", "last_updated") or fetched_at,
        "fetched_at": fetched_at,
        "resolution_risk_notes": [
            "Read-only market intelligence. Verify provider resolution rules, fees, liquidity, and freshness before acting."
        ],
        "source_payload_keys": sorted(record.keys()),
    }


def _extract_source_records(source: str, payloads: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for payload in payloads:
        data = _unwrap(payload)
        if isinstance(data, list):
            records.extend([item for item in data if isinstance(item, dict)])
            continue
        if not isinstance(data, dict):
            continue
        # Cross-source Sports Skills market orchestrator shape.
        if source == "polymarket":
            records.extend([item for item in _as_list(data.get("polymarket")) if isinstance(item, dict)])
        if source == "kalshi":
            records.extend([item for item in _as_list(data.get("kalshi")) if isinstance(item, dict)])
        # Direct module shapes.
        records.extend([item for item in _as_list(data.get("markets")) if isinstance(item, dict)])
        records.extend([item for item in _as_list(data.get("events")) if isinstance(item, dict)])
    return records


def _market_matches(market: dict[str, Any], *, query: str, team: str, source: str, status: str) -> bool:
    if source and source != "all" and market.get("source") != source:
        return False
    if status and status != "all" and market.get("status") not in {status, "unknown"}:
        return False

    haystack = " ".join(
        _lower(v)
        for v in (
            market.get("title"),
            market.get("description"),
            market.get("slug"),
            market.get("source_event_id"),
            market.get("market_type"),
        )
    )
    if team and _lower(team) not in haystack:
        return False
    # Relevance gate: keep only World Cup-related markets so broad sports
    # payloads don't pollute results.
    if not any(term in haystack for term in WORLD_CUP_TERMS):
        return False
    if query:
        normalized_query = _lower(query)
        # Generic World Cup words don't discriminate between markets; only
        # specific tokens (teams, players, "group h") narrow the results.
        generic_tokens = {"fifa", "world", "cup", "2026"}
        query_tokens = [
            token
            for token in normalized_query.split()
            if len(token) > 2 and token not in generic_tokens
        ]
        if query_tokens and normalized_query not in haystack:
            if not any(token in haystack for token in query_tokens):
                return False
    return True


def _filter_markets(markets: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    query = _text(params.get("query"))
    team = _text(params.get("team"))
    source = _lower(params.get("source") or "all")
    status = _lower(params.get("status") or "open")
    try:
        limit = int(params.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 250))

    filtered = [
        market
        for market in markets
        if _market_matches(market, query=query, team=team, source=source, status=status)
    ]
    # Prefer the most liquid / highest-volume candidates when providers return broad sports payloads.
    filtered.sort(key=lambda market: max(_to_float(market.get("volume")), _to_float(market.get("liquidity"))), reverse=True)
    return filtered[:limit]


def normalize_market_sources(request_data: dict[str, Any]) -> dict[str, Any]:
    """Normalize Sports Skills/Kalshi/Polymarket market payloads.

    Params accepted:
      - sports_skills_markets, polymarket_markets, kalshi_markets
      - query, team, source, status, limit
    """
    params = _params(request_data)
    fetched_at = _now_iso()

    poly_records = _extract_source_records(
        "polymarket",
        [params.get("sports_skills_markets"), params.get("polymarket_markets")],
    )
    kalshi_records = _extract_source_records(
        "kalshi",
        [params.get("sports_skills_markets"), params.get("kalshi_markets")],
    )

    normalized: list[dict[str, Any]] = []
    for source, records in (("polymarket", poly_records), ("kalshi", kalshi_records)):
        for record in records:
            market = _normalize_record(source, record, fetched_at)
            if market:
                normalized.append(market)

    deduped: dict[str, dict[str, Any]] = {}
    for market in normalized:
        deduped[market["cache_id"]] = market
    markets = _filter_markets(list(deduped.values()), params)

    warnings = []
    if not markets:
        warnings.append(
            "No matching World Cup markets found after source normalization/filtering. Try force_live=true, source=all, or a broader query."
        )
    if kalshi_records and not any(m.get("source") == "kalshi" for m in markets):
        warnings.append("Kalshi returned records, but none matched the World Cup/status/source filters.")
    if poly_records and not any(m.get("source") == "polymarket" for m in markets):
        warnings.append("Polymarket returned records, but none matched the World Cup/status/source filters.")

    return {
        "status": True,
        "data": {
            "markets": markets,
            "normalized_markets": markets,
            "count": len(markets),
            "sources": {
                "polymarket_records_seen": len(poly_records),
                "kalshi_records_seen": len(kalshi_records),
            },
            "warnings": warnings,
        },
    }


STALE_CACHE_SECONDS = 900  # 15 min — market prices move; warn consumers about cache age.


def _cache_age_warning(markets: list[dict[str, Any]]) -> str | None:
    """Return a staleness warning when the oldest served market is past the TTL."""
    oldest: datetime | None = None
    for market in markets:
        raw = _text(market.get("fetched_at"))
        if not raw:
            continue
        try:
            fetched = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if oldest is None or fetched < oldest:
            oldest = fetched
    if oldest is None:
        return "Cached markets have no fetched_at timestamp; freshness unknown. Use force_live=true for current prices."
    age = (datetime.now(timezone.utc) - oldest).total_seconds()
    if age > STALE_CACHE_SECONDS:
        return (
            f"Cached market data is up to {int(age // 60)} minutes old. "
            "Prices may have moved; use force_live=true for current prices."
        )
    return None


def filter_cached_markets(request_data: dict[str, Any]) -> dict[str, Any]:
    """Filter normalized markets already read from same-pod document storage."""
    params = _params(request_data)
    cached_markets = [item for item in _as_list(params.get("cached_markets")) if isinstance(item, dict)]
    markets = _filter_markets(cached_markets, params)
    warnings = [] if markets else ["No cached markets matched the request filters."]
    age_warning = _cache_age_warning(markets) if markets else None
    if age_warning:
        warnings.append(age_warning)
    return {
        "status": True,
        "data": {
            "markets": markets,
            "count": len(markets),
            "warnings": warnings,
        },
    }
