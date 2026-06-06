"""World Cup market-intelligence connector utilities.

This connector intentionally performs only read-only normalization/filtering. It
accepts payloads returned by the shared `sports-skills` connector and converts
Kalshi/Polymarket market records into a stable shape for API/MCP/x402 exposure.
"""

from __future__ import annotations

import difflib
import hashlib
import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any


WORLD_CUP_TERMS = (
    "world cup",
    "fifa",
    "2026 world cup",
    "fifa world cup",
    # Kalshi World Cup series tickers (e.g. KXWCGAME-26JUN27CODUZB-UZB,
    # KXMENWORLDCUP-...). Game titles like "Congo DR vs Uzbekistan Winner?"
    # carry no World Cup wording — the ticker in the haystack is the signal.
    "kxwc",
    "worldcup",
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
        _first(
            record,
            "yes_price",
            "yes_ask",
            "yes_bid",
            "last_price",
            "price",
            # Kalshi's current trade API returns dollar-string fields.
            "last_price_dollars",
            "yes_ask_dollars",
            "yes_bid_dollars",
        )
    )
    no_price = _normalize_probability(
        _first(record, "no_price", "no_ask", "no_bid", "no_ask_dollars", "no_bid_dollars")
    )
    if no_price is None and yes_price is not None:
        no_price = round(1 - yes_price, 6)
    # Kalshi binary markets describe the strike via yes_sub_title (e.g.
    # "Uzbekistan" for "Congo DR vs Uzbekistan Winner?"). no_sub_title repeats
    # the strike, so the No side keeps its literal name.
    yes_name = _text(record.get("yes_sub_title")) or "Yes"
    results = []
    if yes_price is not None:
        results.append({"name": yes_name, "price": yes_price, "token_id": None, "source_outcome_id": "yes"})
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
        "volume": _first(record, "volume", "volume_24h", "dollar_volume", "volume_fp"),
        "liquidity": _first(record, "liquidity", "open_interest", "liquidity_dollars", "open_interest_fp"),
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


# ── Market state (PR 3): market_id → current state + depth + history ─────────


def _book_side(levels: Any, *, descending: bool) -> list[dict[str, Any]]:
    """Normalize order-book levels into [{price, size}], best level first.

    Accepts Polymarket dicts ({price, size}) or Kalshi dollar-string pairs
    ([["0.1600", "42.55"], ...]). Sorting is done here because provider
    ordering is unreliable (Polymarket CLOB returns bids ascending, so naive
    first-element 'best bid' reads the WORST level).
    """
    normalized = []
    for level in _as_list(levels) if not isinstance(levels, dict) else []:
        if isinstance(level, dict):
            price, size = level.get("price"), level.get("size")
        elif isinstance(level, (list, tuple)) and len(level) >= 2:
            price, size = level[0], level[1]
        else:
            continue
        price_f, size_f = _to_float(price), _to_float(size)
        if 0 <= price_f <= 1:
            normalized.append({"price": round(price_f, 6), "size": round(size_f, 4)})
    normalized.sort(key=lambda lvl: lvl["price"], reverse=descending)
    return normalized


def _book_outcome(name: str, token_id: Any, bids: Any, asks: Any) -> dict[str, Any]:
    bid_levels = _book_side(bids, descending=True)
    ask_levels = _book_side(asks, descending=False)
    best_bid = bid_levels[0]["price"] if bid_levels else None
    best_ask = ask_levels[0]["price"] if ask_levels else None
    spread = round(best_ask - best_bid, 6) if best_bid is not None and best_ask is not None else None
    return {
        "name": name,
        "token_id": _text(token_id) or None,
        "bids": bid_levels,
        "asks": ask_levels,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
    }


def _kalshi_state_book(kalshi_book: Any, market: dict[str, Any]) -> list[dict[str, Any]]:
    """Kalshi orderbook_fp → per-outcome book.

    Kalshi exposes yes/no BID levels only; the ask side of YES is implied by
    the NO bids (ask_yes = 1 - bid_no) and vice versa.
    """
    book = _unwrap(kalshi_book)
    levels = book.get("orderbook") if isinstance(book, dict) else {}
    if not isinstance(levels, dict):
        return []
    yes_bids = _as_list(levels.get("yes_dollars") or levels.get("yes"))
    no_bids = _as_list(levels.get("no_dollars") or levels.get("no"))

    def _implied(side: list[Any]) -> list[list[float]]:
        out = []
        for level in side:
            if isinstance(level, (list, tuple)) and len(level) >= 2:
                price = _to_float(level[0])
                if price > 1:  # legacy integer cents
                    price = price / 100.0
                out.append([round(1 - price, 6), _to_float(level[1])])
        return out

    yes_name = "Yes"
    outcomes = market.get("outcomes") if isinstance(market, dict) else None
    if outcomes and isinstance(outcomes[0], dict):
        yes_name = outcomes[0].get("name") or "Yes"
    return [
        _book_outcome(yes_name, None, yes_bids, _implied(no_bids)),
        _book_outcome("No", None, no_bids, _implied(yes_bids)),
    ]


def _kalshi_state_history(kalshi_candles: Any) -> list[dict[str, Any]]:
    data = _unwrap(kalshi_candles)
    candles = _as_list(data.get("candlesticks")) if isinstance(data, dict) else []
    history = []
    for candle in candles:
        if not isinstance(candle, dict):
            continue
        price = candle.get("price") if isinstance(candle.get("price"), dict) else {}
        close = _first(price, "close_dollars", "close")
        if close is None:
            continue
        close_f = _to_float(close)
        if close_f > 1:  # legacy integer cents
            close_f = close_f / 100.0
        history.append(
            {
                "ts": candle.get("end_period_ts"),
                "price": round(close_f, 6),
                "volume": _to_float(_first(candle, "volume_fp", "volume")),
            }
        )
    return history


def _poly_state_book(poly_books: Any, market: dict[str, Any]) -> list[dict[str, Any]]:
    token_names = {}
    for outcome in market.get("outcomes", []) if isinstance(market, dict) else []:
        if isinstance(outcome, dict) and outcome.get("token_id"):
            token_names[_text(outcome["token_id"])] = outcome.get("name") or "unknown"
    outcomes = []
    for raw in _as_list(poly_books) if not isinstance(poly_books, dict) else [poly_books]:
        book = _unwrap(raw)
        if not isinstance(book, dict):
            continue
        token_id = _text(book.get("token_id") or book.get("asset_id"))
        outcomes.append(
            _book_outcome(token_names.get(token_id, "unknown"), token_id, book.get("bids"), book.get("asks"))
        )
    return outcomes


def _poly_state_history(poly_history: Any) -> list[dict[str, Any]]:
    data = _unwrap(poly_history)
    points = _as_list(data.get("history")) if isinstance(data, dict) else _as_list(data)
    return [
        {"ts": point.get("t"), "price": round(_to_float(point.get("p")), 6), "volume": None}
        for point in points
        if isinstance(point, dict) and point.get("t") is not None
    ]


def normalize_market_state(request_data: dict[str, Any]) -> dict[str, Any]:
    """Unify per-venue market state into one shape.

    Params accepted:
      - market_id: cache id ("kalshi:<ticker>" | "polymarket:<id>")
      - cached: the cached WorldCupMarket record (may be {})
      - kalshi_market, kalshi_book, kalshi_candles, kalshi_trades
      - poly_details, poly_books, poly_history, poly_last_trade
    """
    params = _params(request_data)
    market_id = _text(params.get("market_id"))
    cached = params.get("cached") if isinstance(params.get("cached"), dict) else {}
    source = market_id.split(":", 1)[0] if ":" in market_id else _text(cached.get("source"))
    fetched_at = _now_iso()
    warnings: list[str] = []

    # Refresh the market snapshot from the live record when available.
    market = cached
    if source == "kalshi":
        live = _unwrap(params.get("kalshi_market"))
        if isinstance(live, dict) and live:
            market = _normalize_record("kalshi", live, fetched_at) or cached
        book = _kalshi_state_book(params.get("kalshi_book"), market)
        history = _kalshi_state_history(params.get("kalshi_candles"))
        trades_data = _unwrap(params.get("kalshi_trades"))
        trades = _as_list(trades_data.get("trades")) if isinstance(trades_data, dict) else []
        last_trade = None
    elif source == "polymarket":
        live = _unwrap(params.get("poly_details"))
        if isinstance(live, dict) and live:
            market = _normalize_record("polymarket", live, fetched_at) or cached
        if not (isinstance(market, dict) and market.get("outcomes")) and cached.get("outcomes"):
            market = cached
        book = _poly_state_book(params.get("poly_books"), market)
        history = _poly_state_history(params.get("poly_history"))
        trades = []
        last = _unwrap(params.get("poly_last_trade"))
        last_trade = last if isinstance(last, dict) and last.get("price") is not None else None
    else:
        return {
            "status": False,
            "data": {},
            "message": f"market_id must be prefixed with a known source (kalshi:|polymarket:), got: {market_id!r}",
        }

    if not market:
        warnings.append("Market not found in cache and no live record returned.")
    if not book:
        warnings.append("No order-book depth available for this market.")
    if not history:
        warnings.append("No price history available for the requested window.")

    return {
        "status": True,
        "data": {
            "market_id": market_id,
            "source": source,
            "market": market or {},
            "book": {"outcomes": book},
            "history": history,
            "last_trade": last_trade,
            "trades": trades[:100],
            "fetched_at": fetched_at,
            "warnings": warnings,
        },
    }


# -- Edge detection + price-move (PR 5) --------------------------------------


def _yes_price(market):
    """Best YES-style probability for a normalized market (first outcome)."""
    outcomes = market.get("outcomes") if isinstance(market, dict) else None
    if outcomes and isinstance(outcomes[0], dict):
        price = outcomes[0].get("price")
        if price is not None:
            return _to_float(price)
    return None


def _outcome_price(market, name_contains):
    """Price of the first outcome whose name contains a substring (lowercased)."""
    for outcome in market.get("outcomes", []) if isinstance(market, dict) else []:
        if isinstance(outcome, dict) and name_contains in _lower(outcome.get("name")):
            price = outcome.get("price")
            return _to_float(price) if price is not None else None
    return None


def detect_market_edges(request_data):
    """Find informational market dislocations from cached markets + match pairs.

    Two detector families, both arithmetic over normalized 0-1 prices:

      1. within_venue_book_sum: a multi-outcome event (Kalshi home/away/tie)
         whose YES prices sum away from 1.0 is mispriced against itself.
         sum < 1 => buying every NO is a fee-blind lock; > 1 the reverse.
         edge_bps = |sum - 1| * 10000.

      2. cross_venue_draw: when match_markets pairs a game across venues, the
         draw/tie outcome is the cleanest line both venues price. Compare the
         Kalshi tie price (joined from cache by ticker) to the Polymarket draw
         price. edge_bps = |delta| * 10000.

      3. model_vs_market (optional): when `forecasts` (worldcup:model-forecast
         docs) are supplied, compare each event's model-implied 1X2 probability
         to the market price for that outcome. gap_bps = |model_prob - price| *
         10000. Informational ONLY — a gap is not a value/bet signal.

    Params:
      - cached_markets: normalized WorldCupMarket[] (worldcup:market-cache)
      - matches: match_markets output (optional; enables cross-venue)
      - forecasts: worldcup:model-forecast docs (optional; enables model_vs_market)
      - min_edge_bps: minimum edge to report (default 50)
      - limit: max candidates (default 50)
    """
    params = _params(request_data)
    cached = [m for m in _as_list(params.get("cached_markets")) if isinstance(m, dict)]
    try:
        min_edge_bps = int(params.get("min_edge_bps") or 50)
    except (TypeError, ValueError):
        min_edge_bps = 50
    try:
        limit = max(1, min(int(params.get("limit") or 50), 250))
    except (TypeError, ValueError):
        limit = 50

    by_cache_id = {m.get("cache_id"): m for m in cached if m.get("cache_id")}
    candidates = []

    # 1. Within-venue book-sum dislocations, grouped by source event.
    groups = {}
    for market in cached:
        event_id = market.get("source_event_id")
        if event_id:
            groups.setdefault((market.get("source"), event_id), []).append(market)
    for (source, event_id), legs in groups.items():
        # Dedup repeated cache_ids — overlapping sync generations can leave
        # two docs for one outcome, which would double-count a leg.
        seen_ids = set()
        unique_legs = []
        for leg in legs:
            cid = leg.get("cache_id")
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            unique_legs.append(leg)
        priced = [(leg, _yes_price(leg)) for leg in unique_legs]
        priced = [(leg, p) for leg, p in priced if p is not None]
        if len(priced) < 2:
            continue
        # A YES leg priced at exactly 0.0 has no bid (unpriced/illiquid), not
        # a real ~0 probability — it deflates the sum into a fake underround.
        if any(p == 0.0 for _, p in priced):
            continue
        # Book-sum == 1.0 only holds for SINGLE-WINNER mutually-exclusive
        # events (one match: home/away/tie). "Top 2 advance" group markets
        # sum to ~2.0 and outright-winner fields are independent binaries —
        # both would throw false edges. A draw/tie leg is the structural
        # signal of a single-winner match market, so gate on it.
        names = [_lower((leg.get("outcomes") or [{}])[0].get("name")) for leg, _ in priced]
        names += [_lower(leg.get("title")) for leg, _ in priced]
        has_draw = any("draw" in n or "tie" in n for n in names)
        if not has_draw:
            continue
        book_sum = round(sum(p for _, p in priced), 6)
        edge_bps = round(abs(book_sum - 1.0) * 10000)
        if edge_bps < min_edge_bps:
            continue
        candidates.append({
            "candidate_type": "within_venue_book_sum",
            "source": source,
            "event_id": event_id,
            "book_sum": book_sum,
            "edge_bps": edge_bps,
            "direction": "buy_all_no" if book_sum < 1 else "buy_all_yes",
            "legs": [
                {"cache_id": leg.get("cache_id"), "title": leg.get("title"),
                 "outcome": (leg.get("outcomes") or [{}])[0].get("name"), "yes_price": p}
                for leg, p in priced
            ],
            "caveats": [
                "Fee-, liquidity-, and resolution-rule-blind. Verify book depth and settlement terms before acting.",
                "A sum near 1.0 within the bid/ask spread is normal, not an edge.",
            ],
        })

    # 2. Cross-venue draw line, from match pairs.
    for match in _as_list(params.get("matches")):
        if not isinstance(match, dict):
            continue
        kalshi = match.get("kalshi") or {}
        poly = match.get("polymarket") or {}
        tie_ticker = next(
            (t for t in _as_list(kalshi.get("market_tickers")) if str(t).upper().endswith("-TIE")),
            None,
        )
        k_tie = _yes_price(by_cache_id.get("kalshi:" + _text(tie_ticker), {})) if tie_ticker else None
        p_draw = None
        for pm in _as_list(poly.get("markets")):
            if isinstance(pm, dict) and "draw" in _lower(pm.get("question")):
                p_draw = _outcome_price(pm, "yes")
                break
        # Exactly 0.0 means the venue has no bid on the tie (unpriced), not a
        # genuine ~0 draw probability — can't form a real cross-venue edge.
        if k_tie is None or p_draw is None or k_tie == 0.0 or p_draw == 0.0:
            continue
        delta = round(k_tie - p_draw, 6)
        edge_bps = round(abs(delta) * 10000)
        if edge_bps < min_edge_bps:
            continue
        candidates.append({
            "candidate_type": "cross_venue_draw",
            "title": match.get("title"),
            "match_method": match.get("match_method"),
            "kalshi_tie_price": k_tie,
            "polymarket_draw_price": p_draw,
            "delta": delta,
            "edge_bps": edge_bps,
            "cheaper_venue": "kalshi" if k_tie < p_draw else "polymarket",
            "caveats": [
                "Draw lines may differ in resolution rules (90-min vs incl. extra time). Verify both before acting.",
                "Fee- and liquidity-blind; cross-venue execution carries transfer/settlement risk.",
            ],
        })

    # 3. Model-vs-market gaps (only when forecasts are supplied). Appended to the
    # same list; when `forecasts` is absent this block is a no-op and the two
    # legacy detectors above are byte-identical.
    forecasts = _as_list(params.get("forecasts"))
    if forecasts:
        candidates.extend(_model_vs_market_candidates(cached, forecasts, min_edge_bps))

    candidates.sort(key=lambda c: c["edge_bps"], reverse=True)
    candidates = candidates[:limit]

    warnings = []
    if not cached:
        warnings.append("No cached markets supplied -- run worldcup-sync-market-sources first.")
    if not params.get("matches"):
        warnings.append("No match pairs supplied -- cross-venue draw detection skipped (within-venue only).")
    if not candidates:
        warnings.append("No dislocations >= " + str(min_edge_bps) + " bps found. Markets look efficiently priced.")

    return {
        "status": True,
        "data": {
            "edge_candidates": candidates,
            "count": len(candidates),
            "min_edge_bps": min_edge_bps,
            "warnings": warnings,
        },
    }


def detect_price_move(request_data):
    """Detect the largest price move in a normalized history window.

    Params:
      - history: normalized points [{ts|timestamp, price|p}] (0-1 prices)
      - window_hours: only consider points within the last N hours (optional)
      - min_move_bps: threshold to flag a move (default 200 = 2 cents)
    """
    params = _params(request_data)
    raw = _as_list(params.get("history"))
    try:
        min_move_bps = int(params.get("min_move_bps") or 200)
    except (TypeError, ValueError):
        min_move_bps = 200

    points = []
    for point in raw:
        if not isinstance(point, dict):
            continue
        ts = point.get("ts", point.get("timestamp"))
        price = point.get("price", point.get("p"))
        if ts is None or price is None:
            continue
        points.append({"ts": int(_to_float(ts)), "price": round(_to_float(price), 6)})
    points.sort(key=lambda pt: pt["ts"])

    window_hours = params.get("window_hours")
    if window_hours and points:
        try:
            cutoff = points[-1]["ts"] - int(window_hours) * 3600
            points = [pt for pt in points if pt["ts"] >= cutoff] or points
        except (TypeError, ValueError):
            pass

    if len(points) < 2:
        return {"status": True, "data": {
            "moved": False, "net_move_bps": 0, "swing_bps": 0, "points": len(points),
            "warnings": ["Not enough history points to detect a move."],
        }}

    start, end = points[0], points[-1]
    net_bps = round((end["price"] - start["price"]) * 10000)
    lo = min(points, key=lambda pt: pt["price"])
    hi = max(points, key=lambda pt: pt["price"])
    swing_bps = round((hi["price"] - lo["price"]) * 10000)

    return {
        "status": True,
        "data": {
            "moved": abs(net_bps) >= min_move_bps or swing_bps >= min_move_bps,
            "net_move_bps": net_bps,
            "swing_bps": swing_bps,
            "direction": "up" if net_bps > 0 else ("down" if net_bps < 0 else "flat"),
            "from_price": start["price"],
            "to_price": end["price"],
            "low": {"price": lo["price"], "ts": lo["ts"]},
            "high": {"price": hi["price"], "ts": hi["ts"]},
            "from_ts": start["ts"],
            "to_ts": end["ts"],
            "points": len(points),
            "min_move_bps": min_move_bps,
            "warnings": [],
        },
    }


# -- Standings + squads ------------------------------------------------------


def _std_rows_af(af: Any) -> list[dict[str, Any]]:
    """Group tables from an api-football /standings response."""
    data = _unwrap(af)
    response = data.get("response", []) if isinstance(data, dict) else []
    groups: list[dict[str, Any]] = []
    for entry in response if isinstance(response, list) else []:
        league = entry.get("league", {}) if isinstance(entry, dict) else {}
        for table in league.get("standings", []) or []:
            if not isinstance(table, list):
                continue
            group_name = ""
            rows: list[dict[str, Any]] = []
            for r in table:
                if not isinstance(r, dict):
                    continue
                group_name = group_name or _text(r.get("group"))
                team = r.get("team", {}) if isinstance(r.get("team"), dict) else {}
                allst = r.get("all", {}) if isinstance(r.get("all"), dict) else {}
                goals = allst.get("goals", {}) if isinstance(allst.get("goals"), dict) else {}
                rows.append({
                    "rank": r.get("rank"),
                    "team_id": team.get("id"),
                    "team": _text(team.get("name")),
                    "crest": _text(team.get("logo")) or None,
                    "played": allst.get("played"),
                    "win": allst.get("win"),
                    "draw": allst.get("draw"),
                    "lose": allst.get("lose"),
                    "goals_for": goals.get("for"),
                    "goals_against": goals.get("against"),
                    "goal_diff": r.get("goalsDiff"),
                    "points": r.get("points"),
                })
            if rows:
                groups.append({"group": group_name, "table": rows})
    return groups


def _std_rows_ss(ss: Any) -> list[dict[str, Any]]:
    """Group tables from a sports-skills get_season_standings response."""
    data = _unwrap(ss)
    standings = data.get("standings", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    groups: list[dict[str, Any]] = []
    for grp in standings if isinstance(standings, list) else []:
        if not isinstance(grp, dict):
            continue
        rows: list[dict[str, Any]] = []
        for e in grp.get("entries", []) or []:
            if not isinstance(e, dict):
                continue
            team = e.get("team", {}) if isinstance(e.get("team"), dict) else {}
            rows.append({
                "rank": _first(e, "position", "rank"),
                "team_id": team.get("id"),
                "team": _text(team.get("name")),
                "crest": _text(team.get("crest")) or None,
                "played": e.get("played"),
                "win": _first(e, "won", "win"),
                "draw": _first(e, "drawn", "draw"),
                "lose": _first(e, "lost", "lose"),
                "goals_for": _first(e, "goals_for"),
                "goals_against": _first(e, "goals_against"),
                "goal_diff": _first(e, "goal_difference", "goal_diff"),
                "points": e.get("points"),
            })
        if rows:
            groups.append({"group": _text(grp.get("name")), "table": rows})
    return groups


def normalize_standings(request_data: dict[str, Any]) -> dict[str, Any]:
    """Merge api-football and sports-skills standings into stable group tables.

    Params:
      - af: raw api-football /standings response
      - ss: raw sports-skills get_season_standings response
      - league_id, season: passthrough labels for the envelope
    """
    params = _params(request_data)
    warnings: list[str] = []
    groups = _std_rows_af(params.get("af"))
    source = "api-football"
    if not groups:
        groups = _std_rows_ss(params.get("ss"))
        source = "sports-skills" if groups else "none"
    elif params.get("ss") not in (None, "", {}, []):
        # Backfill missing crests from sports-skills by team name.
        crest_by_team = {
            _lower(row.get("team")): row.get("crest")
            for grp in _std_rows_ss(params.get("ss"))
            for row in grp.get("table", [])
            if row.get("crest")
        }
        for grp in groups:
            for row in grp["table"]:
                if not row.get("crest"):
                    row["crest"] = crest_by_team.get(_lower(row.get("team")))

    if not groups:
        warnings.append("No standings available from api-football or sports-skills.")
    for grp in groups:
        grp["table"].sort(key=lambda r: (r.get("rank") is None, r.get("rank") or 0))

    return {
        "status": True,
        "data": {
            "source": source,
            "season": params.get("season"),
            "league_id": _text(params.get("league_id")) or None,
            "group_count": len(groups),
            "groups": groups,
            "warnings": warnings,
        },
    }


def _squad_team_af(af: Any) -> dict[str, Any]:
    data = _unwrap(af)
    response = data.get("response", []) if isinstance(data, dict) else []
    if response and isinstance(response[0], dict):
        team = response[0].get("team", {})
        return team if isinstance(team, dict) else {}
    return {}


def _squad_players_af(af: Any) -> list[dict[str, Any]]:
    data = _unwrap(af)
    response = data.get("response", []) if isinstance(data, dict) else []
    players: list[dict[str, Any]] = []
    for entry in response if isinstance(response, list) else []:
        if not isinstance(entry, dict):
            continue
        for p in entry.get("players", []) or []:
            if not isinstance(p, dict):
                continue
            players.append({
                "id": p.get("id"),
                "name": _text(p.get("name")),
                "number": p.get("number"),
                "position": _text(p.get("position")),
                "age": p.get("age"),
                "photo": _text(p.get("photo")) or None,
            })
    return players


def _squad_team_ss(ss: Any) -> dict[str, Any]:
    data = _unwrap(ss)
    team = data.get("team") if isinstance(data, dict) else None
    return team if isinstance(team, dict) else {}


def _squad_players_ss(ss: Any) -> list[dict[str, Any]]:
    """Roster from a sports-skills get_team_profile response (full pool)."""
    data = _unwrap(ss)
    roster = data.get("players") if isinstance(data, dict) else None
    players: list[dict[str, Any]] = []
    for p in roster if isinstance(roster, list) else []:
        if not isinstance(p, dict):
            continue
        players.append({
            "id": _first(p, "id", "espn_athlete_id"),
            "name": _text(_first(p, "name", "full_name", "display_name")),
            "number": _first(p, "shirt_number", "number", "jersey"),
            "position": _text(_first(p, "position", "pos")),
            "age": _first(p, "age"),
            "photo": _text(_first(p, "photo", "headshot")) or None,
        })
    return players


def normalize_squads(request_data: dict[str, Any]) -> dict[str, Any]:
    """Merge api-football and sports-skills squads.

    Params per side ("home"/"away"):
      - {side}_af: raw api-football /players/squads response
      - {side}_ss: raw sports-skills get_team_profile response
      - {side}_team_id, {side}_team: resolved labels (optional; backfilled)
    """
    params = _params(request_data)
    teams: list[dict[str, Any]] = []
    warnings: list[str] = []
    for side in ("home", "away"):
        af = params.get(f"{side}_af")
        ss = params.get(f"{side}_ss")
        if af in (None, "", {}, []) and ss in (None, "", {}, []):
            continue
        players = _squad_players_af(af)
        source = "api-football" if players else "none"
        if not players:
            players = _squad_players_ss(ss)
            source = "sports-skills" if players else "none"
        team_id = params.get(f"{side}_team_id")
        team_name = _text(params.get(f"{side}_team"))
        if not team_id or not team_name:
            ident = _squad_team_af(af) or _squad_team_ss(ss)
            team_id = team_id or ident.get("id")
            team_name = team_name or _text(ident.get("name"))
        if not players:
            warnings.append(f"No squad returned for {team_name or team_id or side}.")
        teams.append({
            "side": side,
            "team_id": team_id,
            "team": team_name,
            "source": source,
            "count": len(players),
            "players": players,
        })
    if not teams:
        warnings.append("No squad payloads provided.")
    return {"status": True, "data": {"teams": teams, "warnings": warnings}}


def _injuries_items(af: Any) -> list[dict[str, Any]]:
    """Injury rows from an api-football /injuries response (body or list)."""
    data = _unwrap(af)
    if isinstance(data, dict):
        resp = data.get("response")
        return resp if isinstance(resp, list) else []
    return data if isinstance(data, list) else []


def normalize_injuries(request_data: dict[str, Any]) -> dict[str, Any]:
    """Per-team injuries/suspensions, filtered to a fixture's two teams.

    api-football /injuries returns league-wide rows of the shape
    {player:{id,name,photo,type,reason}, team:{id,name}, fixture:{id,date,timestamp}}.
    A player out for several upcoming fixtures appears once per fixture, so we
    dedup per player and keep the most recent fixture.

    Params:
      - af: api-football /injuries response (league-wide; body or list)
      - home_team_id, away_team_id, home_team, away_team
    """
    params = _params(request_data)
    items = _injuries_items(params.get("af"))
    teams: list[dict[str, Any]] = []
    warnings: list[str] = []
    for side in ("home", "away"):
        tid = params.get(f"{side}_team_id")
        tname = _text(params.get(f"{side}_team"))
        if tid in (None, "") and not tname:
            continue
        by_player: dict[Any, dict[str, Any]] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            team = it.get("team", {}) if isinstance(it.get("team"), dict) else {}
            if str(team.get("id")) != str(tid):
                continue
            player = it.get("player", {}) if isinstance(it.get("player"), dict) else {}
            fixture = it.get("fixture", {}) if isinstance(it.get("fixture"), dict) else {}
            entry = {
                "name": _text(player.get("name")),
                "player_id": player.get("id"),
                "photo": _text(player.get("photo")) or None,
                "type": _text(player.get("type")),
                "reason": _text(player.get("reason")),
                "fixture_id": fixture.get("id"),
                "fixture_date": _text(fixture.get("date")) or None,
            }
            key = player.get("id") if player.get("id") is not None else _lower(entry["name"])
            ts = _to_float(fixture.get("timestamp"))
            prev = by_player.get(key)
            if prev is None or ts >= prev["_ts"]:
                entry["_ts"] = ts
                by_player[key] = entry
        missing = [{k: v for k, v in e.items() if k != "_ts"} for e in by_player.values()]
        teams.append({
            "side": side,
            "team_id": tid,
            "team": tname,
            "source": "api-football",
            "count": len(missing),
            "missing": missing,
        })
    if not teams:
        warnings.append("No team identifiers provided; cannot resolve injuries.")
    elif not any(t["count"] for t in teams):
        warnings.append(
            "No injuries/suspensions reported for these teams yet (api-football). "
            "Expect data closer to matchday."
        )
    return {"status": True, "data": {"source": "api-football", "teams": teams, "warnings": warnings}}


def normalize_schedule(request_data: dict[str, Any]) -> dict[str, Any]:
    """Shape cached worldcup:event docs into a fixture-list (schedule) view.

    Serves our own normalized/IPTC-derived event data from the same-pod cache —
    not a raw upstream proxy. Filters by date range (YYYY-MM-DD, inclusive),
    team-name substring, and status.

    Params:
      - events: list of worldcup:event doc values
      - date_from, date_to, team, status, limit
    """
    params = _params(request_data)
    events = _as_list(params.get("events"))
    team = _lower(params.get("team"))
    status = _lower(params.get("status"))
    date_from = _text(params.get("date_from"))[:10]
    date_to = _text(params.get("date_to"))[:10]
    try:
        limit = max(1, min(int(params.get("limit") or 100), 500))
    except (TypeError, ValueError):
        limit = 100

    out: list[dict[str, Any]] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        start = _text(_first(ev, "start_date", "schema:startDate"))
        start_day = start[:10]
        st = _lower(_first(ev, "status", "sport:status"))
        competitors = ev.get("teams") or ev.get("sport:competitors") or []
        names = [_text(t.get("name")) for t in competitors if isinstance(t, dict)]

        if status and status != st:
            continue
        if team and not any(team in _lower(n) for n in names):
            continue
        if date_from and start_day and start_day < date_from:
            continue
        if date_to and start_day and start_day > date_to:
            continue

        venue = ev.get("venue") if isinstance(ev.get("venue"), dict) else (
            ev.get("sport:venue") if isinstance(ev.get("sport:venue"), dict) else {})
        competition = ev.get("sport:competition") if isinstance(ev.get("sport:competition"), dict) else {}
        out.append({
            "event_urn": _first(ev, "_id", "id", "event_urn"),
            "name": _text(ev.get("name")),
            "start_date": start,
            "status": st,
            "competition": _text(ev.get("competition")) or _text(competition.get("name")) or "World Cup",
            "teams": [
                {
                    "name": _text(t.get("name")),
                    "qualifier": _text(t.get("sport:qualifier")),
                    "crest": _text(_first(t, "schema:logo", "crest")) or None,
                }
                for t in competitors if isinstance(t, dict)
            ],
            "venue": _text(venue.get("name")) or None,
            "fixture_id": (ev.get("provider_ids") or {}).get("api_football"),
        })

    out.sort(key=lambda e: e.get("start_date") or "")
    out = out[:limit]
    warnings = [] if out else ["No events matched the schedule filters."]
    return {"status": True, "data": {"events": out, "count": len(out), "warnings": warnings}}


FIFA_POWER_SCORE_KEYS = ["attacking", "creativity", "defending", "in_possession", "defending_goal"]
OUTFIELD_POWER_CATEGORIES = ["attacking", "creativity", "defending"]
GOALKEEPER_POWER_CATEGORIES = ["in_possession", "defending_goal"]
FIFA_POWER_MIN_MINUTES = 20


def _clean_percent(value: Any) -> float:
    if isinstance(value, str) and value.strip().endswith("%"):
        return _to_float(value.strip().rstrip("%")) / 100
    numeric = _to_float(value)
    return numeric / 100 if numeric > 1 else numeric


def _stat_section(stat: dict[str, Any], name: str) -> dict[str, Any]:
    section = stat.get(name)
    return section if isinstance(section, dict) else {}


def _is_goalkeeper_position(position: Any) -> bool:
    p = _lower(position).replace(".", "")
    return p in {"g", "gk", "goalkeeper", "keeper", "portero", "guardameta"}


def _score(value: float, maximum: float) -> float:
    if maximum <= 0:
        return 0.0
    return round(max(0.0, min(10.0, (value / maximum) * 10)), 2)


def _empty_scores() -> dict[str, float | None]:
    return {key: None for key in FIFA_POWER_SCORE_KEYS}


def classify_fifa_power_categories(request_data: dict[str, Any]) -> dict[str, Any]:
    """Return FIFA public Power Ranking category set for a position.

    This mirrors FIFA's public taxonomy only: outfield players have attacking,
    creativity, defending; goalkeepers have in-possession and defending-goal.
    """
    params = _params(request_data)
    position = params.get("position") or params.get("player", {}).get("position")
    is_goalkeeper = bool(params.get("is_goalkeeper")) or _is_goalkeeper_position(position)
    categories = GOALKEEPER_POWER_CATEGORIES if is_goalkeeper else OUTFIELD_POWER_CATEGORIES
    return {
        "status": True,
        "data": {
            "is_goalkeeper": is_goalkeeper,
            "categories": categories,
            "score_scale": {"min": 0, "max": 10},
            "minimum_minutes": FIFA_POWER_MIN_MINUTES,
        },
    }


def apply_power_ranking_eligibility(request_data: dict[str, Any]) -> dict[str, Any]:
    """Apply FIFA's public 20-minute minimum eligibility rule."""
    params = _params(request_data)
    min_minutes = int(params.get("min_minutes") or FIFA_POWER_MIN_MINUTES)
    minutes = int(_to_float(params.get("minutes_played") or params.get("minutes") or 0))
    eligible = minutes >= min_minutes
    warnings = [] if eligible else [
        f"Player minutes ({minutes}) below FIFA minimum ({min_minutes}) for Power Ranking score eligibility."
    ]
    return {
        "status": True,
        "data": {
            "minutes_played": minutes,
            "minimum_minutes": min_minutes,
            "eligible_for_power_ranking": eligible,
            "warnings": warnings,
        },
    }


def normalize_player_match_stats(request_data: dict[str, Any]) -> dict[str, Any]:
    """Normalize provider player-match statistics into a stable API shape.

    Accepts API-Football-style player entries, optionally wrapped in response
    arrays. The output is deliberately provider-backed and does not infer FIFA
    official scores.
    """
    params = _params(request_data)
    requested_player_id = _text(params.get("player_id"))
    requested_team_id = _text(params.get("team_id"))
    event_urn = _text(params.get("event_urn") or params.get("fixture_id")) or None
    team = params.get("team") if isinstance(params.get("team"), dict) else {}
    team_id = _text(params.get("team_id") or team.get("id")) or None
    team_name = _text(params.get("team_name") or team.get("name")) or None

    raw_players = params.get("players")
    if raw_players is None:
        payload = _unwrap(params.get("player_stats") or params.get("api_football_player_stats"))
        raw_players = []
        if isinstance(payload, dict):
            response = payload.get("response", [])
            for entry in response if isinstance(response, list) else []:
                if isinstance(entry, dict):
                    entry_team = entry.get("team") if isinstance(entry.get("team"), dict) else {}
                    for player in entry.get("players", []) or []:
                        if isinstance(player, dict):
                            clone = dict(player)
                            clone.setdefault("team", entry_team)
                            raw_players.append(clone)

    players: list[dict[str, Any]] = []
    for raw in _as_list(raw_players):
        if not isinstance(raw, dict):
            continue
        player_info = raw.get("player") if isinstance(raw.get("player"), dict) else raw
        stat = {}
        stats = raw.get("statistics")
        if isinstance(stats, list) and stats:
            stat = stats[0] if isinstance(stats[0], dict) else {}
        elif isinstance(raw.get("stats"), dict):
            stat = raw.get("stats", {})

        raw_team = raw.get("team") if isinstance(raw.get("team"), dict) else team
        games = _stat_section(stat, "games")
        goals = _stat_section(stat, "goals")
        shots = _stat_section(stat, "shots")
        passes = _stat_section(stat, "passes")
        tackles = _stat_section(stat, "tackles")
        duels = _stat_section(stat, "duels")
        cards = _stat_section(stat, "cards")

        position = _text(games.get("position") or raw.get("position") or player_info.get("position"))
        minutes = int(_to_float(games.get("minutes") or raw.get("minutes") or 0))
        is_goalkeeper = _is_goalkeeper_position(position)
        player = {
            "player_id": _text(player_info.get("id") or raw.get("player_id")),
            "name": _text(player_info.get("name") or raw.get("name")),
            "team_id": _text(raw_team.get("id") or team_id) or None,
            "team_name": _text(raw_team.get("name") or team_name) or None,
            "event_urn": event_urn,
            "position": position,
            "is_goalkeeper": is_goalkeeper,
            "minutes_played": minutes,
            "eligible_for_power_ranking": minutes >= FIFA_POWER_MIN_MINUTES,
            "source_quality": "provider",
            "stats": {
                "rating": _to_float(games.get("rating")),
                "goals": int(_to_float(goals.get("total"))),
                "assists": int(_to_float(goals.get("assists"))),
                "saves": int(_to_float(goals.get("saves"))),
                "shots_total": int(_to_float(shots.get("total"))),
                "shots_on": int(_to_float(shots.get("on"))),
                "passes_total": int(_to_float(passes.get("total"))),
                "key_passes": int(_to_float(passes.get("key"))),
                "pass_accuracy": _clean_percent(passes.get("accuracy")),
                "tackles": int(_to_float(tackles.get("total"))),
                "interceptions": int(_to_float(tackles.get("interceptions"))),
                "duels_total": int(_to_float(duels.get("total"))),
                "duels_won": int(_to_float(duels.get("won"))),
                "yellow_cards": int(_to_float(cards.get("yellow"))),
                "red_cards": int(_to_float(cards.get("red"))),
            },
        }
        if requested_player_id and player["player_id"] != requested_player_id:
            continue
        if requested_team_id and _text(player.get("team_id")) != requested_team_id:
            continue
        player["warnings"] = [] if player["eligible_for_power_ranking"] else [
            f"Player minutes ({minutes}) below FIFA minimum ({FIFA_POWER_MIN_MINUTES}) for Power Ranking score eligibility."
        ]
        players.append(player)

    warnings = [] if players else ["No provider player match statistics supplied."]
    return {"status": True, "data": {"players": players, "count": len(players), "warnings": warnings}}


def score_provisional_player_performance(request_data: dict[str, Any]) -> dict[str, Any]:
    """Create a source-labeled Machina provisional 0-10 performance signal.

    These scores are not FIFA/Aramco rankings. They are transparent, provider-
    backed estimates with drivers, confidence, and warnings.
    """
    params = _params(request_data)
    player = params.get("player") if isinstance(params.get("player"), dict) else params
    stats = player.get("stats") if isinstance(player.get("stats"), dict) else {}
    minutes = int(_to_float(player.get("minutes_played")))
    eligibility = apply_power_ranking_eligibility({"params": {"minutes_played": minutes}})["data"]
    scores = _empty_scores()
    warnings = list(player.get("warnings") or []) + list(eligibility.get("warnings") or [])
    drivers: list[dict[str, Any]] = []

    if not eligibility["eligible_for_power_ranking"]:
        signal = {
            "status": "unavailable",
            "source_quality": player.get("source_quality") or "unavailable",
            "confidence": 0.0,
            "scores_0_10": scores,
            "drivers": drivers,
            "warnings": warnings,
            "disclaimer": "Machina provisional signal only; not an official FIFA Power Ranking.",
        }
        return {"status": True, "data": {"machina_provisional_performance_signal": signal}}

    source_quality = player.get("source_quality") or "provider"
    rating = stats.get("rating") or 0
    completeness = 0.35
    if rating:
        completeness += 0.15
    if stats:
        completeness += 0.25
    if minutes >= 60:
        completeness += 0.15
    confidence = round(max(0.2, min(0.9, completeness)), 2)

    if player.get("is_goalkeeper"):
        defending_goal_raw = (
            _to_float(stats.get("saves")) * 1.4
            + (1 if int(_to_float(stats.get("goals"))) == 0 else 0)
            + _to_float(rating) * 0.6
        )
        in_possession_raw = _clean_percent(stats.get("pass_accuracy")) * 6 + _to_float(stats.get("passes_total")) / 25
        scores["defending_goal"] = _score(defending_goal_raw, 10)
        scores["in_possession"] = _score(in_possession_raw, 8)
        drivers.extend([
            {"category": "defending_goal", "signal": "saves/rating", "direction": "positive", "weight": round(defending_goal_raw, 2), "source": source_quality},
            {"category": "in_possession", "signal": "distribution volume/accuracy", "direction": "positive", "weight": round(in_possession_raw, 2), "source": source_quality},
        ])
    else:
        attacking_raw = (
            _to_float(stats.get("goals")) * 3.0
            + _to_float(stats.get("assists")) * 1.8
            + _to_float(stats.get("shots_on")) * 0.7
            + _to_float(stats.get("shots_total")) * 0.25
            + _to_float(rating) * 0.35
        )
        creativity_raw = (
            _to_float(stats.get("assists")) * 2.0
            + _to_float(stats.get("key_passes")) * 0.9
            + _clean_percent(stats.get("pass_accuracy")) * 2
            + _to_float(rating) * 0.3
        )
        defending_raw = (
            _to_float(stats.get("tackles")) * 0.8
            + _to_float(stats.get("interceptions")) * 0.9
            + _to_float(stats.get("duels_won")) * 0.35
            - _to_float(stats.get("yellow_cards")) * 0.5
            - _to_float(stats.get("red_cards")) * 2.0
            + _to_float(rating) * 0.25
        )
        scores["attacking"] = _score(attacking_raw, 10)
        scores["creativity"] = _score(creativity_raw, 9)
        scores["defending"] = _score(defending_raw, 9)
        drivers.extend([
            {"category": "attacking", "signal": "goals/assists/shots/rating", "direction": "positive", "weight": round(attacking_raw, 2), "source": source_quality},
            {"category": "creativity", "signal": "assists/key passes/pass accuracy", "direction": "positive", "weight": round(creativity_raw, 2), "source": source_quality},
            {"category": "defending", "signal": "tackles/interceptions/duels/cards", "direction": "positive", "weight": round(defending_raw, 2), "source": source_quality},
        ])

    signal = {
        "status": "available" if drivers else "partial",
        "source_quality": source_quality,
        "confidence": confidence,
        "scores_0_10": scores,
        "drivers": drivers,
        "warnings": warnings,
        "disclaimer": "Machina provisional signal only; not an official FIFA Power Ranking.",
    }
    return {"status": True, "data": {"machina_provisional_performance_signal": signal}}


def merge_official_and_provisional_performance(request_data: dict[str, Any]) -> dict[str, Any]:
    """Merge official FIFA fields and Machina provisional signal without conflating them."""
    params = _params(request_data)
    event = params.get("event") if isinstance(params.get("event"), dict) else {}
    player = params.get("player") if isinstance(params.get("player"), dict) else {}
    provisional = params.get("provisional_signal") or params.get("machina_provisional_performance_signal") or {}
    official = params.get("official_fifa_power_ranking") if isinstance(params.get("official_fifa_power_ranking"), dict) else {}

    official_scores = _empty_scores()
    for key, value in (official.get("scores") or {}).items():
        if key in official_scores:
            official_scores[key] = value

    official_context = {
        "status": official.get("status") or "pending",
        "expected_available_at": official.get("expected_available_at"),
        "source": official.get("source") or "fifa.com",
        "scores": official_scores,
        "classification": official.get("classification") or {
            "match_rank": None,
            "tournament_rank": None,
            "category_rankings": [],
        },
    }
    fallback_path = params.get("fallback_path")
    if not fallback_path:
        quality = provisional.get("source_quality") or player.get("source_quality") or "unavailable"
        fallback_path = [] if quality == "unavailable" else [quality]

    context = {
        "event": event,
        "player": {
            "player_id": player.get("player_id"),
            "name": player.get("name"),
            "team_id": player.get("team_id"),
            "team_name": player.get("team_name"),
            "position": player.get("position"),
            "is_goalkeeper": bool(player.get("is_goalkeeper")),
            "minutes_played": int(_to_float(player.get("minutes_played"))),
            "eligible_for_power_ranking": bool(player.get("eligible_for_power_ranking", int(_to_float(player.get("minutes_played"))) >= FIFA_POWER_MIN_MINUTES)),
        },
        "official_fifa_power_ranking": official_context,
        "machina_provisional_performance_signal": provisional or {
            "status": "unavailable",
            "source_quality": "unavailable",
            "confidence": 0.0,
            "scores_0_10": _empty_scores(),
            "drivers": [],
            "warnings": ["No provisional signal supplied."],
        },
        "context_and_evidence": {
            "fallback_path": fallback_path,
            "citations": params.get("citations") or [],
            "missing_info_flags": params.get("missing_info_flags") or [],
            "freshness": params.get("freshness") or {},
        },
    }
    return {"status": True, "data": {"player_performance_context": context}}


def normalize_identity_crosswalk(request_data: dict[str, Any]) -> dict[str, Any]:
    """Normalize identity crosswalk rows into document-store values."""
    params = _params(request_data)
    items = _as_list(params.get("items"))
    normalized_items: list[dict[str, Any]] = []
    warnings: list[str] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        entity_type = _clean_text(item.get("type") or item.get("entity_type") or "team").lower()
        sport = _slugify(item.get("sport") or "soccer")
        name = _clean_text(item.get("name") or item.get("title"))
        provider_ids = dict(item.get("provider_ids") or {})
        disambiguator = _clean_text(item.get("disambiguator")) or _stable_disambiguator(provider_ids)

        if entity_type == "team":
            name_clean = re.sub(r"\b(FC|CF|SC|CD|Football Club)\b", "", name, flags=re.IGNORECASE).strip()
            urn = f"urn:machina:sport:{sport}:team:{_slugify(name_clean)}:{_to_iso3(item.get('country') or item.get('nationality'))}"
        elif entity_type == "player":
            urn = (
                f"urn:machina:sport:{sport}:player:{_slugify(name)}:"
                f"{_parse_birth_date(item.get('birth_date') or item.get('date_of_birth'))}:"
                f"{_to_iso3(item.get('country') or item.get('nationality'))}"
            )
        elif entity_type == "event":
            date_part = _event_date(item.get("date") or item.get("start_time") or item.get("year") or "2026")
            urn = (
                f"urn:machina:sport:{sport}:event:"
                f"{_slugify(item.get('home_team'))}-vs-{_slugify(item.get('away_team'))}:"
                f"{date_part}:wor"
            )
        elif entity_type == "competition":
            scope = _to_iso3(item.get("scope") or item.get("country") or "world")
            if scope == "wor" or _clean_text(item.get("scope")).lower() in {"world", "global"}:
                scope = "wor"
            urn = f"urn:machina:sport:{sport}:competition:{_slugify(name)}:{scope}"
        else:
            urn = _clean_text(item.get("urn") or item.get("@id"))
            if not urn:
                warnings.append(f"skipped item with unknown entity type and no urn: {entity_type}")
                continue

        # True same-name/DOB/country collisions can opt into a deterministic suffix.
        if item.get("force_disambiguator") and disambiguator and not urn.endswith(f":{disambiguator}"):
            urn = f"{urn}:{disambiguator}"

        metadata_key = "event_urn" if entity_type == "event" else "entity_urn"
        doc: dict[str, Any] = {
            "metadata": {metadata_key: urn},
            "@context": {
                "sport": "https://www.sportschema.org/ontologies/sport#",
                "schema": "https://schema.org/",
                "machina": "https://schema.machina.gg/sports#",
            },
            "@id": urn,
            "@type": ["sport:IdentityCrosswalk", f"sport:{entity_type.title()}"],
            "id": urn,
            "_id": urn,
            "name": name,
            "provider_ids": provider_ids,
            "machina_competition_slug": item.get("machina_competition_slug", "world-cup-2026"),
            "mapping_status": {
                "verified_ids_only": True,
                "notes": item.get("mapping_notes", []),
            },
        }
        for key in (
            "aliases", "birth_date", "nationality", "country", "source_evidence",
            "teams", "sport:competitors", "competition_urn", "start_time",
        ):
            if key in item and item[key] not in (None, "", [], {}):
                doc[key] = item[key]
        if entity_type == "competition" and "scope" not in doc:
            doc["scope"] = item.get("scope", "global")
        normalized_items.append(doc)

    return {
        "status": True,
        "data": {
            "normalized_items": normalized_items,
            "count": len(normalized_items),
            "warnings": warnings,
        },
    }


# -- Identity helpers --------------------------------------------------------

# Country name + ISO-3166 alpha-3 + common FIFA/IOC code variants -> canonical
# lowercase ISO-3166 alpha-3 (FIFA codes used for the UK home nations, which
# have no ISO alpha-3). Covers all 48 men's World Cup 2026 nations.
_ISO3_MAP = {
    # Argentina
    "ARG": "arg", "ARGENTINA": "arg",
    # Australia
    "AUS": "aus", "AUSTRALIA": "aus",
    # Austria
    "AUT": "aut", "AUSTRIA": "aut",
    # Belgium
    "BEL": "bel", "BELGIUM": "bel",
    # Bosnia & Herzegovina
    "BIH": "bih", "BOSNIA HERZEGOVINA": "bih", "BOSNIA AND HERZEGOVINA": "bih",
    # Brazil
    "BRA": "bra", "BRAZIL": "bra", "BRASIL": "bra",
    # Canada
    "CAN": "can", "CANADA": "can",
    # Cape Verde
    "CPV": "cpv", "CAPE VERDE": "cpv", "CAPE VERDE ISLANDS": "cpv", "CABO VERDE": "cpv",
    # Colombia
    "COL": "col", "COLOMBIA": "col",
    # Congo DR
    "COD": "cod", "CONGO DR": "cod", "DR CONGO": "cod", "DEMOCRATIC REPUBLIC OF THE CONGO": "cod",
    # Croatia
    "HRV": "hrv", "CRO": "hrv", "CROATIA": "hrv",
    # Curaçao
    "CUW": "cuw", "CURACAO": "cuw",
    # Czech Republic
    "CZE": "cze", "CZECH REPUBLIC": "cze", "CZECHIA": "cze",
    # Côte d'Ivoire
    "CIV": "civ", "COTE D IVOIRE": "civ", "IVORY COAST": "civ",
    # Ecuador
    "ECU": "ecu", "ECUADOR": "ecu",
    # Egypt
    "EGY": "egy", "EGYPT": "egy",
    # England (FIFA code; no ISO alpha-3)
    "ENG": "eng", "ENGLAND": "eng",
    # France
    "FRA": "fra", "FRANCE": "fra",
    # Germany
    "DEU": "deu", "GER": "deu", "GERMANY": "deu",
    # Ghana
    "GHA": "gha", "GHANA": "gha",
    # Haiti
    "HTI": "hti", "HAI": "hti", "HAITI": "hti",
    # Iran
    "IRN": "irn", "IR IRAN": "irn", "IRAN": "irn",
    # Iraq
    "IRQ": "irq", "IRAQ": "irq",
    # Japan
    "JPN": "jpn", "JAPAN": "jpn",
    # Jordan
    "JOR": "jor", "JORDAN": "jor",
    # Morocco
    "MAR": "mar", "MOROCCO": "mar",
    # Mexico
    "MEX": "mex", "MEXICO": "mex",
    # Netherlands
    "NLD": "nld", "NED": "nld", "NETHERLANDS": "nld",
    # New Zealand
    "NZL": "nzl", "NEW ZEALAND": "nzl",
    # Norway
    "NOR": "nor", "NORWAY": "nor",
    # Panama
    "PAN": "pan", "PANAMA": "pan",
    # Paraguay
    "PRY": "pry", "PAR": "pry", "PARAGUAY": "pry",
    # Portugal
    "PRT": "prt", "POR": "prt", "PORTUGAL": "prt",
    # Qatar
    "QAT": "qat", "QATAR": "qat",
    # Saudi Arabia
    "SAU": "sau", "KSA": "sau", "SAUDI ARABIA": "sau",
    # Scotland (FIFA code; no ISO alpha-3)
    "SCO": "sco", "SCOTLAND": "sco",
    # Senegal
    "SEN": "sen", "SENEGAL": "sen",
    # South Africa
    "ZAF": "zaf", "RSA": "zaf", "SOUTH AFRICA": "zaf",
    # South Korea
    "KOR": "kor", "KOREA REPUBLIC": "kor", "SOUTH KOREA": "kor",
    # Spain
    "ESP": "esp", "SPAIN": "esp",
    # Sweden
    "SWE": "swe", "SWEDEN": "swe",
    # Switzerland
    "CHE": "che", "SUI": "che", "SWITZERLAND": "che",
    # Tunisia
    "TUN": "tun", "TUNISIA": "tun",
    # Türkiye
    "TUR": "tur", "TURKIYE": "tur", "TURKEY": "tur",
    # Uruguay
    "URY": "ury", "URU": "ury", "URUGUAY": "ury",
    # USA
    "USA": "usa", "UNITED STATES": "usa", "UNITED STATES OF AMERICA": "usa",
    # Uzbekistan
    "UZB": "uzb", "UZBEKISTAN": "uzb",
    # Algeria
    "DZA": "dza", "ALG": "dza", "ALGERIA": "dza",
    # Non-WC but kept for cross-provider robustness
    "ITA": "ita", "ITALY": "ita", "SRB": "srb", "SERBIA": "srb", "WAL": "wal", "WALES": "wal",
}

# Backwards-compatible alias for normalize_identity_crosswalk's body.
iso_mapping = _ISO3_MAP


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _to_iso3(country: Any) -> str:
    # Strip accents first (NFKD) so cross-provider spellings converge:
    # "Côte d'Ivoire" -> "COTE D IVOIRE", "Türkiye" -> "TURKIYE".
    ascii_src = unicodedata.normalize("NFKD", _clean_text(country)).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Z ]", " ", ascii_src.upper())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned in _ISO3_MAP:
        return _ISO3_MAP[cleaned]
    compact = cleaned.replace(" ", "")
    if compact in _ISO3_MAP:
        return _ISO3_MAP[compact]
    fallback = re.sub(r"[^A-Z]", "", cleaned)[:3].lower()
    return fallback if len(fallback) == 3 else "unk"


def _slugify(name: Any) -> str:
    normalized = unicodedata.normalize("NFKD", _clean_text(name))
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii").lower()
    # Remove suffixes from the stable slug; keep suffix/alias metadata in input.
    ascii_str = re.sub(r"\b(jr|junior|sr|senior|neto|filho|ii|iii|iv|v)\b\.?", "", ascii_str)
    ascii_str = re.sub(r"[^a-z0-9\s-]", " ", ascii_str)
    slug = re.sub(r"[\s-]+", "-", ascii_str).strip("-")
    return slug or "unknown"


def _parse_birth_date(value: Any) -> str:
    raw = _clean_text(value)
    match = re.search(r"\b(\d{4})[-/.]?(\d{2})[-/.]?(\d{2})\b", raw)
    if match:
        return "".join(match.groups())
    year = re.search(r"\b(19\d{2}|20\d{2})\b", raw)
    return f"{year.group(1)}0000" if year else "00000000"


def _event_date(value: Any) -> str:
    raw = _clean_text(value)
    # No \b anchors: API-Football dates are full ISO ("2026-06-11T19:00:00+00:00"),
    # where the digits abut a "T" (no word boundary) — \b would drop the day/month.
    match = re.search(r"(\d{4})[-/.]?(\d{2})[-/.]?(\d{2})", raw)
    if match:
        return "".join(match.groups())
    year = re.search(r"(19\d{2}|20\d{2})", raw)
    return f"{year.group(1)}0000" if year else "00000000"


def _stable_disambiguator(provider_ids: dict[str, Any]) -> str:
    verified = [(k, str(v)) for k, v in sorted((provider_ids or {}).items()) if v not in (None, "", [], {})]
    if not verified:
        return ""
    seed = "|".join(f"{k}:{v}" for k, v in verified[:2])
    return hashlib.sha1(seed.encode()).hexdigest()[:8]


def _machina_team_urn(name: Any) -> str:
    return f"urn:machina:sport:soccer:team:{_slugify(name)}:{_to_iso3(name)}"


def mint_event_identity(request_data: dict[str, Any]) -> dict[str, Any]:
    """Build IPTC World Cup event docs with machina URNs from API-Football fixtures."""
    params = _params(request_data)
    fixtures = _as_list(params.get("fixtures"))
    comp_slug = _text(params.get("competition_slug")) or "world-cup-2026"
    events: list[dict[str, Any]] = []
    warnings: list[str] = []

    # Carry forward provider ids not produced by ingest (sportradar, opta, entain,
    # espn — added by the event crosswalk) from existing event docs, keyed by the
    # api-football fixture id, so a force-update re-ingest preserves them.
    event_alias = {"sportradar_event_id": "sportradar", "entain_event_id": "entain",
                   "opta_event_id": "opta", "espn_event_id": "espn"}
    event_providers = {"sportradar", "opta", "entain", "espn"}
    carry: dict[str, dict[str, str]] = {}
    for ev in _as_list(params.get("existing_events")):
        d = _unwrap(ev)
        pids = d.get("provider_ids") if isinstance(d, dict) else None
        if not isinstance(pids, dict):
            continue
        fid = _text(pids.get("api_football") or pids.get("api_football_fixture_id"))
        if not fid:
            continue
        keep = {}
        for k, v in pids.items():
            nk = event_alias.get(k, k)
            if nk in event_providers and _text(v):
                keep[nk] = _text(v)
        if keep:
            carry[fid] = keep

    for f in fixtures:
        if not isinstance(f, dict):
            continue
        fixture = f.get("fixture", {}) if isinstance(f.get("fixture"), dict) else {}
        teams = f.get("teams", {}) if isinstance(f.get("teams"), dict) else {}
        home = teams.get("home", {}) if isinstance(teams.get("home"), dict) else {}
        away = teams.get("away", {}) if isinstance(teams.get("away"), dict) else {}
        venue = fixture.get("venue", {}) if isinstance(fixture.get("venue"), dict) else {}

        fixture_id = _text(fixture.get("id"))
        home_name = _text(home.get("name"))
        away_name = _text(away.get("name"))
        if not fixture_id or not home_name or not away_name:
            warnings.append("skipped fixture missing id/home/away")
            continue

        date_iso = _text(fixture.get("date"))
        event_urn = (
            f"urn:machina:sport:soccer:event:"
            f"{_slugify(home_name)}-vs-{_slugify(away_name)}:{_event_date(date_iso)}:wor"
        )
        # Canonical competition URN — must match the competition crosswalk doc and
        # the market cache (api-football's league name "World Cup" would mint a
        # different, dangling slug).
        comp_name = "FIFA World Cup 2026"
        comp_urn = "urn:machina:sport:soccer:competition:fifa-world-cup-2026:wor"

        venue_name = _text(venue.get("name"))
        venue_block: dict[str, Any] = {
            "@type": "sport:Venue",
            "name": venue_name or None,
            "schema:addressLocality": _text(venue.get("city")) or None,
        }
        if venue_name:
            venue_block["@id"] = (
                f"urn:machina:sport:soccer:venue:{_slugify(venue_name)}:"
                f"{_to_iso3(venue.get('city') or venue.get('country') or '')}"
            )

        doc = {
            "metadata": {"event_urn": event_urn},
            "@context": {
                "sport": "https://www.sportschema.org/ontologies/sport#",
                "schema": "https://schema.org/",
                "machina": "https://schema.machina.gg/sports#",
            },
            "@id": event_urn,
            "id": event_urn,
            "_id": event_urn,
            "@type": ["sport:Event", "schema:SportsEvent"],
            "name": f"{home_name} vs {away_name} - {comp_name}",
            "schema:startDate": date_iso or None,
            "sport:status": _text((fixture.get("status") or {}).get("short")) or None,
            "sport:competition": {"@id": comp_urn, "@type": "sport:Competition", "name": comp_name},
            "sport:venue": venue_block,
            "sport:competitors": [
                {"@type": "sport:Team", "@id": _machina_team_urn(home_name), "name": home_name,
                 "sport:qualifier": "home", "schema:logo": _text(home.get("logo")) or None},
                {"@type": "sport:Team", "@id": _machina_team_urn(away_name), "name": away_name,
                 "sport:qualifier": "away", "schema:logo": _text(away.get("logo")) or None},
            ],
            # provider_ids holds ONLY each provider's id for THIS object (the event):
            # api_football = the fixture id. Team/league/venue ids are resolved
            # relationally (competitors -> team crosswalk, competition).
            "provider_ids": {
                "api_football": fixture_id,
            },
            "machina_competition_slug": comp_slug,
        }
        for k, v in carry.get(fixture_id, {}).items():
            doc["provider_ids"].setdefault(k, v)
        events.append(doc)

    if not events:
        warnings.append("No fixtures supplied.")
    return {
        "status": True,
        "data": {"sport_schema_events": events, "events": events, "count": len(events), "warnings": warnings},
    }


_CROSSWALK_PROVIDERS = ["api_football", "espn", "transfermarkt", "sportradar", "opta", "entain"]
_CANONICAL_CROSSWALK_PROVIDERS = {"api_football", "espn"}


def merge_provider_entities(request_data: dict[str, Any]) -> dict[str, Any]:
    """Merge per-provider national-team lists ({provider}_teams) into crosswalk items, joined by iso3."""
    params = _params(request_data)
    canon: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    summary: dict[str, int] = {}

    for provider in _CROSSWALK_PROVIDERS:
        teams = _as_list(params.get(f"{provider}_teams"))
        count = 0
        for t in teams:
            if not isinstance(t, dict):
                continue
            name = _text(t.get("name"))
            tid = _text(t.get("id"))
            if not name or not tid:
                continue
            iso = _to_iso3(name)
            key = iso if iso != "unk" else _slugify(name)
            if key not in canon:
                if provider not in _CANONICAL_CROSSWALK_PROVIDERS:
                    continue
                canon[key] = {"name": name, "provider_ids": {}}
                order.append(key)
            if provider == "api_football":
                canon[key]["name"] = name
            canon[key]["provider_ids"][provider] = tid
            count += 1
        if teams:
            summary[provider] = count

    items = [
        {"type": "team", "name": canon[k]["name"], "country": canon[k]["name"],
         "provider_ids": canon[k]["provider_ids"]}
        for k in order
    ]
    warnings = [] if items else ["No provider team lists supplied."]
    return {
        "status": True,
        "data": {"items": items, "count": len(items), "provider_summary": summary, "warnings": warnings},
    }


def _name_tokens(name: Any) -> tuple[str, str]:
    """(lastname_slug, first_initial) from a free-form player name."""
    toks = [t for t in _slugify(name).split("-") if t]
    if not toks:
        return ("", "")
    return (toks[-1], toks[0][:1])


def _is_full_name(name: Any) -> bool:
    """True if name reads as a full name, not an initial form like 'N. de la Cruz'."""
    parts = _text(name).split()
    return len(parts) >= 2 and "." not in parts[0] and len(parts[0]) > 1


def _team_maps(teams: list[Any]) -> dict[str, dict]:
    """provider key -> {provider_id: teaminfo} from team-crosswalk docs."""
    maps: dict[str, dict] = {"api_football": {}, "opta": {}, "espn": {}, "sportradar": {}}
    for t in teams:
        if not isinstance(t, dict):
            continue
        pids = t.get("provider_ids") or {}
        info = {
            "urn": _first(t, "_id", "@id", "id"),
            "name": _text(t.get("name")),
            "iso3": _to_iso3(t.get("country") or t.get("name")),
        }
        for prov in maps:
            if pids.get(prov):
                maps[prov][_text(pids[prov])] = info
    return maps


def _flatten_foreach(raw: Any) -> list[Any]:
    """Normalize a foreach output (single dict, list, or list-of-lists) to a flat list."""
    if isinstance(raw, dict):
        return [raw]
    out: list[Any] = []
    for r in raw or []:
        out.extend(r) if isinstance(r, list) else out.append(r)
    return out


def build_player_crosswalk(request_data: dict[str, Any]) -> dict[str, Any]:
    """Build WC squad-player crosswalk docs (api-football is the source; other providers add ids).

    Params:
      - teams: team-crosswalk docs (for team-id -> team URN/iso3 maps)
      - af_squads: list of api-football /players/squads responses (canonical player set)
      - af_players: list of api-football /players responses (birth date + nationality, joined by id)
      - opta_squads: opta squads response (opta ids by team + lastname + first-initial)
      - espn_rosters: list of sports-skills get_team_profile responses (espn ids, same match)
      - existing_players: existing crosswalk player docs; provider ids not produced here
        (entain, transfermarkt) are carried forward by api-football id across re-syncs
    """
    params = _params(request_data)
    maps = _team_maps(_as_list(params.get("teams")))
    by_af, by_opta, by_espn = maps["api_football"], maps["opta"], maps["espn"]
    by_sr = maps["sportradar"]
    canon: dict[tuple, dict[str, Any]] = {}
    order: list[tuple] = []
    summary = {"api_football": 0, "opta": 0, "espn": 0, "sportradar": 0,
               "with_dob": 0, "excluded_no_dob": 0}

    # Canonical set + team link from api-football squads.
    for resp in _flatten_foreach(params.get("af_squads")):
        data = _unwrap(resp)
        for entry in (data.get("response", []) if isinstance(data, dict) else []):
            if not isinstance(entry, dict):
                continue
            tinfo = by_af.get(_text((entry.get("team") or {}).get("id")))
            if not tinfo:
                continue
            for p in entry.get("players", []) or []:
                if not isinstance(p, dict):
                    continue
                name, pid = _text(p.get("name")), _text(p.get("id"))
                if not name or not pid:
                    continue
                last, fi = _name_tokens(name)
                key = (tinfo["iso3"], last, fi)
                if key not in canon:
                    canon[key] = {"name": name, "team": tinfo,
                                  "position": _text(p.get("position")), "provider_ids": {}}
                    order.append(key)
                canon[key]["provider_ids"]["api_football"] = pid
                summary["api_football"] += 1

    # Birth date + nationality + full name from api-football /players, joined by id.
    dob_by_id: dict[str, dict[str, Any]] = {}
    for resp in _flatten_foreach(params.get("af_players")):
        data = _unwrap(resp)
        for entry in (data.get("response", []) if isinstance(data, dict) else []):
            player = entry.get("player") if isinstance(entry, dict) else None
            if not isinstance(player, dict) or not player.get("id"):
                continue
            first, last = _text(player.get("firstname")), _text(player.get("lastname"))
            dob_by_id[_text(player["id"])] = {
                "dob": _text((player.get("birth") or {}).get("date")),
                "nationality": _text(player.get("nationality")),
                "name": _text(player.get("name")),
                "full": (first + " " + last).strip(),
            }

    # Opta ids by team + lastname + first-initial.
    opta = _unwrap(params.get("opta_squads"))
    for sq in (opta.get("squad", []) if isinstance(opta, dict) else []):
        if not isinstance(sq, dict):
            continue
        tinfo = by_opta.get(_text(sq.get("contestantId")))
        if not tinfo:
            continue
        for person in sq.get("person", []) or []:
            if not isinstance(person, dict) or _lower(person.get("type")) not in ("player", ""):
                continue
            key = (tinfo["iso3"], _slugify(person.get("lastName")), _slugify(person.get("firstName"))[:1])
            if key in canon and _text(person.get("id")):
                canon[key]["provider_ids"]["opta"] = _text(person.get("id"))
                summary["opta"] += 1

    # ESPN ids (sports-skills get_team_profile), same name match.
    for resp in _flatten_foreach(params.get("espn_rosters")):
        data = _unwrap(resp)
        tinfo = by_espn.get(_text((data.get("team") or {}).get("id"))) if isinstance(data, dict) else None
        if not tinfo:
            continue
        for p in data.get("players", []) or []:
            if not isinstance(p, dict):
                continue
            last, fi = _name_tokens(_first(p, "name", "full_name", "display_name"))
            key = (tinfo["iso3"], last, fi)
            if key in canon and _text(p.get("id")):
                canon[key]["provider_ids"]["espn"] = _text(p.get("id"))
                summary["espn"] += 1

    # Sportradar ids (competitor profile squads). Names are "Lastname, Firstname".
    for resp in _flatten_foreach(params.get("sportradar_rosters")):
        data = _unwrap(resp)
        tinfo = by_sr.get(_text((data.get("competitor") or {}).get("id"))) if isinstance(data, dict) else None
        if not tinfo:
            continue
        for p in data.get("players", []) or []:
            if not isinstance(p, dict):
                continue
            nm = _text(p.get("name"))
            if "," in nm:
                last_raw, first_raw = nm.split(",", 1)
                last, fi = _slugify(last_raw), _slugify(first_raw)[:1]
            else:
                last, fi = _name_tokens(nm)
            key = (tinfo["iso3"], last, fi)
            if key in canon and _text(p.get("id")):
                canon[key]["provider_ids"]["sportradar"] = _text(p.get("id"))
                summary["sportradar"] += 1

    # Carry forward provider ids this build does not itself produce (e.g. entain,
    # transfermarkt) from existing crosswalk docs, joined by api-football id, so a
    # force-update re-sync preserves them instead of dropping them.
    produced = {"api_football", "opta", "espn", "sportradar"}
    key_alias = {"api_football_player_id": "api_football",
                 "entain_player_id": "entain",
                 "transfermarkt_player_id": "transfermarkt"}
    carry: dict[str, dict[str, str]] = {}
    for doc in _flatten_foreach(params.get("existing_players")):
        d = _unwrap(doc)
        pids = d.get("provider_ids") if isinstance(d, dict) else None
        if not isinstance(pids, dict):
            continue
        af = _text(pids.get("api_football") or pids.get("api_football_player_id"))
        if not af:
            continue
        for k, v in pids.items():
            nk = key_alias.get(k, k)
            if nk not in produced and _text(v):
                carry.setdefault(af, {})[nk] = _text(v)

    items: list[dict[str, Any]] = []
    for k in order:
        c = canon[k]
        af_id = c["provider_ids"].get("api_football", "")
        for nk, v in carry.get(af_id, {}).items():
            c["provider_ids"].setdefault(nk, v)
        meta = dob_by_id.get(c["provider_ids"].get("api_football", ""), {})
        dob8 = _parse_birth_date(meta.get("dob"))
        # A player URN's disambiguator is the birth date — without one the URN is
        # ambiguous, so skip the player rather than mint a 00000000 placeholder.
        if dob8 == "00000000":
            summary["excluded_no_dob"] += 1
            continue
        summary["with_dob"] += 1
        # Pick the fullest available name: a non-abbreviated squad/profile name,
        # else firstname+lastname (profiles abbreviates the `name` field).
        display_name = next(
            (n for n in (c["name"], meta.get("name")) if _is_full_name(n)),
            meta.get("full") or meta.get("name") or c["name"],
        )
        urn = f"urn:machina:sport:soccer:player:{_slugify(display_name)}:{dob8}:{c['team']['iso3']}"
        items.append({
            "metadata": {"entity_urn": urn},
            "@context": {
                "sport": "https://www.sportschema.org/ontologies/sport#",
                "schema": "https://schema.org/",
                "machina": "https://schema.machina.gg/sports#",
            },
            "@id": urn,
            "id": urn,
            "_id": urn,
            "@type": ["sport:IdentityCrosswalk", "sport:Player"],
            "name": display_name,
            "position": c["position"] or None,
            "birth_date": meta.get("dob") or None,
            "nationality": meta.get("nationality") or None,
            "team": {"@id": c["team"]["urn"], "name": c["team"]["name"]},
            "provider_ids": c["provider_ids"],
            "machina_competition_slug": "world-cup-2026",
            "mapping_status": {"verified_ids_only": True},
        })

    warnings = [] if items else ["No api-football squad players supplied."]
    return {
        "status": True,
        "data": {"normalized_items": items, "count": len(items),
                 "provider_summary": summary, "warnings": warnings},
    }


def build_event_crosswalk(request_data: dict[str, Any]) -> dict[str, Any]:
    """Attach sportradar + entain event ids to canonical WC event docs (matched by team pair).

    Params:
      - events: canonical worldcup:event values (each has sport:competitors[].@id team URNs)
      - teams: team-crosswalk docs (for sportradar/entain/opta provider-id -> team URN maps)
      - sportradar_schedule: sportradar /seasons/{id}/schedules.json response(s)
      - entain_fixtures: bwin fixtures response(s)
      - opta_schedule: opta tournamentschedule response(s) (matchDate[].match[])
    """
    params = _params(request_data)
    by_sr: dict[str, str] = {}
    by_entain: dict[str, str] = {}
    by_opta: dict[str, str] = {}
    for t in _as_list(params.get("teams")):
        if not isinstance(t, dict):
            continue
        pids = t.get("provider_ids") or {}
        urn = _text(_first(t, "_id", "@id", "id"))
        if pids.get("sportradar"):
            by_sr[_text(pids["sportradar"])] = urn
        if pids.get("entain"):
            by_entain[_text(pids["entain"])] = urn
        if pids.get("opta"):
            by_opta[_text(pids["opta"])] = urn

    by_pair: dict[frozenset, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for ev in _as_list(params.get("events")):
        if not isinstance(ev, dict):
            continue
        ev.setdefault("metadata", {"event_urn": _text(_first(ev, "_id", "@id", "id"))})
        out.append(ev)
        urns = [_text(c.get("@id")) for c in (ev.get("sport:competitors") or [])
                if isinstance(c, dict) and c.get("@id")]
        if len(urns) == 2:
            by_pair[frozenset(urns)] = ev

    summary = {"events": len(out), "sportradar": 0, "entain": 0, "opta": 0}

    for resp in _flatten_foreach(params.get("opta_schedule")):
        data = _unwrap(resp)
        for md in (data.get("matchDate", []) if isinstance(data, dict) else []):
            for m in (md.get("match", []) if isinstance(md, dict) else []):
                if not isinstance(m, dict):
                    continue
                mid = _text(m.get("id"))
                urns = [by_opta.get(_text(m.get("homeContestantId"))),
                        by_opta.get(_text(m.get("awayContestantId")))]
                urns = [u for u in urns if u]
                if not mid or len(urns) != 2:
                    continue
                ev = by_pair.get(frozenset(urns))
                if ev is not None and "opta" not in (ev.get("provider_ids") or {}):
                    ev.setdefault("provider_ids", {})["opta"] = mid
                    summary["opta"] += 1

    for resp in _flatten_foreach(params.get("sportradar_schedule")):
        data = _unwrap(resp)
        for item in (data.get("schedules", []) if isinstance(data, dict) else []):
            se = item.get("sport_event", {}) if isinstance(item, dict) else {}
            sid = _text(se.get("id"))
            urns = [by_sr.get(_text(c.get("id"))) for c in (se.get("competitors") or [])]
            urns = [u for u in urns if u]
            if not sid or len(urns) != 2:
                continue
            ev = by_pair.get(frozenset(urns))
            if ev is not None and "sportradar" not in (ev.get("provider_ids") or {}):
                ev.setdefault("provider_ids", {})["sportradar"] = sid
                summary["sportradar"] += 1

    for resp in _flatten_foreach(params.get("entain_fixtures")):
        data = _unwrap(resp)
        for fx in (data.get("items", []) if isinstance(data, dict) else []):
            if not isinstance(fx, dict):
                continue
            fid = fx.get("id")
            eid = _text(fid.get("entityId") if isinstance(fid, dict) else fid)
            urns = [by_entain.get(_text(p.get("id"))) for p in (fx.get("participants") or [])]
            urns = [u for u in urns if u]
            if not eid or len(urns) != 2:
                continue
            ev = by_pair.get(frozenset(urns))
            if ev is not None and "entain" not in (ev.get("provider_ids") or {}):
                ev.setdefault("provider_ids", {})["entain"] = eid
                summary["entain"] += 1

    return {
        "status": True,
        "data": {"normalized_items": out, "count": len(out), "provider_summary": summary},
    }


WC_COMPETITION_URN = "urn:machina:sport:soccer:competition:fifa-world-cup-2026:wor"

# Market team-name variants -> canonical team name slug (as used in team URNs).
_MARKET_TEAM_ALIASES = {
    "czechia": "czech-republic",
    "korea": "south-korea", "korea-republic": "south-korea",
    "turkey": "turkiye",
    "cote-d-ivoire": "ivory-coast", "cote-divoire": "ivory-coast",
    "dr-congo": "congo-dr", "drc": "congo-dr", "democratic-republic-of-congo": "congo-dr",
    "united-states": "usa", "united-states-of-america": "usa",
    "bosnia": "bosnia-herzegovina", "bosnia-and-herzegovina": "bosnia-herzegovina",
    "cape-verde": "cape-verde-islands",
}


def _market_team_index(teams: list[Any]) -> list[tuple]:
    """(match_slug, team_urn) pairs, longest-first, including name aliases."""
    canon_to_urn: dict[str, str] = {}
    index: list[tuple] = []
    for t in teams:
        if not isinstance(t, dict):
            continue
        urn = _text(_first(t, "_id", "@id", "id"))
        name_slug = _slugify(t.get("name"))
        if not urn or not name_slug:
            continue
        canon_to_urn[name_slug] = urn
        index.append((name_slug, urn))
    for alias, canon in _MARKET_TEAM_ALIASES.items():
        if canon in canon_to_urn:
            index.append((alias, canon_to_urn[canon]))
    index.sort(key=lambda x: len(x[0]), reverse=True)
    return index


def _fuzzy_slug_in_text(slug: str, text_slug: str, threshold: float = 0.88) -> bool:
    """True if `slug` closely matches an n-gram window of the dashed text.

    Conservative (default 0.88) so near-but-distinct nations do NOT cross-match
    (iran/iraq=0.75, niger/nigeria=0.83) while real typos do (england/ngland=0.92).
    """
    words = [w for w in slug.split("-") if w]
    tokens = [t for t in text_slug.split("-") if t]
    n = len(words)
    if n == 0 or len(tokens) < n:
        return False
    best = 0.0
    for i in range(len(tokens) - n + 1):
        window = "-".join(tokens[i:i + n])
        ratio = difflib.SequenceMatcher(None, slug, window).ratio()
        if ratio > best:
            best = ratio
    return best >= threshold


def _match_team_urns(text_slug: str, index: list[tuple]) -> list[str]:
    found: list[str] = []
    # Primary: exact, word-boundary substring match (unchanged).
    for slug, urn in index:
        if slug and urn not in found and re.search(r"(^|-)" + re.escape(slug) + r"($|-)", text_slug):
            found.append(urn)
    # Fallback: only to fill a likely 2-team market the exact pass missed (e.g. a
    # minor spelling variant not in the alias map). Adds at most up to 2 total,
    # never removes, so existing exact matches are untouched.
    if len(found) < 2:
        for slug, urn in index:
            if urn in found:
                continue
            if _fuzzy_slug_in_text(slug, text_slug):
                found.append(urn)
                if len(found) >= 2:
                    break
    return found


def link_market_entities(request_data: dict[str, Any]) -> dict[str, Any]:
    """Attach competition_urn + related_team_urns + event_urn to normalized markets.

    Params:
      - markets: normalized market records (from normalize_market_sources)
      - teams: team-crosswalk docs (name -> URN, with aliases)
      - events: worldcup:event docs (team-pair -> event_urn)
    All markets here have already passed the World Cup relevance gate, so the
    competition is always the canonical WC competition.
    """
    params = _params(request_data)
    index = _market_team_index(_as_list(params.get("teams")))
    by_pair: dict[frozenset, str] = {}
    for ev in _as_list(params.get("events")):
        if not isinstance(ev, dict):
            continue
        urns = [_text(c.get("@id")) for c in (ev.get("sport:competitors") or [])
                if isinstance(c, dict) and c.get("@id")]
        if len(urns) == 2:
            by_pair[frozenset(urns)] = _text(_first(ev, "_id", "@id", "id"))

    markets = _as_list(params.get("markets"))
    summary = {"markets": len(markets), "with_team": 0, "with_event": 0}
    for m in markets:
        if not isinstance(m, dict):
            continue
        text = " ".join([
            _text(m.get("title")), _text(m.get("slug")),
            " ".join(_text(o.get("name")) for o in (m.get("outcomes") or []) if isinstance(o, dict)),
        ])
        related = _match_team_urns(_slugify(text), index)
        m["competition_urn"] = WC_COMPETITION_URN
        m["related_team_urns"] = related
        m["event_urn"] = by_pair.get(frozenset(related)) if len(related) == 2 else None
        if related:
            summary["with_team"] += 1
        if m["event_urn"]:
            summary["with_event"] += 1
    return {
        "status": True,
        "data": {"normalized_markets": markets, "count": len(markets), "provider_summary": summary},
    }


def build_market_snapshots(request_data: dict[str, Any]) -> dict[str, Any]:
    """Build append-only price snapshots from linked markets (one per market per hour).

    Snapshot id = "{cache_id}:{YYYY-MM-DDTHH}" so the 30-min market sync writes at
    most one row per market per hour (last write in the hour wins) — a bounded
    hourly price/volume time series for movement detection.
    """
    params = _params(request_data)
    snapshots: list[dict[str, Any]] = []
    for m in _as_list(params.get("markets")):
        if not isinstance(m, dict):
            continue
        cid = _text(m.get("cache_id") or m.get("id"))
        if not cid:
            continue
        ts = _text(m.get("fetched_at")) or _now_iso()
        hour = ts[:13]  # "2026-06-06T15"
        snap_id = f"{cid}:{hour}"
        outs = [{"name": _text(o.get("name")), "price": o.get("price")}
                for o in (m.get("outcomes") or []) if isinstance(o, dict)]
        primary = outs[0] if outs else {}
        snapshots.append({
            "metadata": {"snapshot_id": snap_id},
            "_id": snap_id, "id": snap_id,
            "cache_id": cid,
            "source": _text(m.get("source")),
            "title": _text(m.get("title")),
            "ts": ts,
            "hour": hour,
            "primary_name": primary.get("name"),
            "primary_price": primary.get("price"),
            "outcomes": outs,
            "volume": m.get("volume"),
            "liquidity": m.get("liquidity"),
            "event_urn": m.get("event_urn"),
            "competition_urn": m.get("competition_urn"),
            "related_team_urns": m.get("related_team_urns") or [],
        })
    return {"status": True, "data": {"snapshots": snapshots, "count": len(snapshots)}}


def compute_market_movers(request_data: dict[str, Any]) -> dict[str, Any]:
    """Rank markets by price movement vs the earliest snapshot in the window.

    Params:
      - markets: current market-cache records
      - snapshots: market-snapshot rows already filtered to the lookback window
      - limit: max movers to return
    Baseline = oldest snapshot per cache_id in the supplied window; delta =
    current primary-outcome price - baseline price.
    """
    params = _params(request_data)
    try:
        limit = int(params.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20

    baseline: dict[str, dict[str, Any]] = {}
    for s in _as_list(params.get("snapshots")):
        if not isinstance(s, dict):
            continue
        cid = _text(s.get("cache_id"))
        ts = _text(s.get("ts"))
        if not cid or s.get("primary_price") is None:
            continue
        cur = baseline.get(cid)
        if cur is None or (ts and ts < cur["ts"]):
            baseline[cid] = {"ts": ts, "price": _to_float(s.get("primary_price"))}

    movers: list[dict[str, Any]] = []
    for m in _as_list(params.get("markets")):
        if not isinstance(m, dict):
            continue
        cid = _text(m.get("cache_id") or m.get("id"))
        outs = m.get("outcomes") or []
        base = baseline.get(cid)
        if not cid or not outs or not base:
            continue
        price_now = _to_float((outs[0] or {}).get("price"))
        delta = round(price_now - base["price"], 4)
        movers.append({
            "cache_id": cid,
            "title": _text(m.get("title")),
            "source": _text(m.get("source")),
            "outcome": _text((outs[0] or {}).get("name")),
            "price_now": price_now,
            "price_then": base["price"],
            "delta": delta,
            "abs_delta": abs(delta),
            "since": base["ts"],
            "volume": m.get("volume"),
            "event_urn": m.get("event_urn"),
            "related_team_urns": m.get("related_team_urns") or [],
        })

    movers.sort(key=lambda x: x["abs_delta"], reverse=True)
    movers = movers[:limit]
    return {"status": True, "data": {"movers": movers, "count": len(movers)}}


# Live status set — fixtures considered in-play for coverage cadence.
_LIVE_STATUS = {"1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"}


def compute_coverage_signals(request_data: dict[str, Any]) -> dict[str, Any]:
    """Match-phase signals from event docs (no API calls) for the coverage cadence.

    Live is detected by the SCHEDULE window [kickoff, kickoff+150min] (robust even
    when stored sport:status is stale) OR an explicit in-play sport:status.

    Params: events (worldcup:event values)
    """
    params = _params(request_data)
    now = datetime.now(timezone.utc)
    live: list[str] = []
    upcoming_24h = 0
    recent_done = 0
    for ev in _as_list(params.get("events")):
        if not isinstance(ev, dict):
            continue
        urn = _text(_first(ev, "_id", "@id", "id"))
        sd = _text(ev.get("schema:startDate"))
        status = _text(ev.get("sport:status")).upper()
        ko = None
        if sd:
            try:
                ko = datetime.fromisoformat(sd.replace("Z", "+00:00"))
            except ValueError:
                ko = None
            if ko is not None and ko.tzinfo is None:
                ko = ko.replace(tzinfo=timezone.utc)
        in_window = ko is not None and ko <= now <= ko + timedelta(minutes=150)
        if status in _LIVE_STATUS or in_window:
            live.append(urn)
        elif ko is not None and now < ko <= now + timedelta(hours=24):
            upcoming_24h += 1
        elif ko is not None and ko + timedelta(minutes=150) < now <= ko + timedelta(hours=6):
            recent_done += 1
    return {
        "status": True,
        "data": {
            "has_live": len(live) > 0,
            "live_event_urns": live,
            "live_count": len(live),
            "upcoming_24h": upcoming_24h,
            "recent_done": recent_done,
        },
    }


def apply_live_status(request_data: dict[str, Any]) -> dict[str, Any]:
    """Merge live api-football fixture status + score onto matching event docs.

    Params: events (worldcup:event values), live_fixtures (api-football get-fixtures
    response(s), e.g. live=all). Returns only the events that have a live match,
    as full docs (status + live_score updated) ready for bulk-update.
    """
    params = _params(request_data)
    by_fid: dict[str, dict[str, Any]] = {}
    for resp in _flatten_foreach(params.get("live_fixtures")):
        data = _unwrap(resp)
        for f in (data.get("response", []) if isinstance(data, dict) else []):
            if not isinstance(f, dict):
                continue
            fixture = f.get("fixture") or {}
            fid = _text(fixture.get("id"))
            if not fid:
                continue
            goals = f.get("goals") or {}
            by_fid[fid] = {
                "status": _text((fixture.get("status") or {}).get("short")),
                "elapsed": (fixture.get("status") or {}).get("elapsed"),
                "home": goals.get("home"),
                "away": goals.get("away"),
            }
    out: list[dict[str, Any]] = []
    for ev in _as_list(params.get("events")):
        if not isinstance(ev, dict):
            continue
        fid = _text((ev.get("provider_ids") or {}).get("api_football"))
        info = by_fid.get(fid)
        if not info:
            continue
        ev.setdefault("metadata", {"event_urn": _text(_first(ev, "_id", "@id", "id"))})
        if info["status"]:
            ev["sport:status"] = info["status"]
        ev["live_score"] = {"home": info["home"], "away": info["away"], "elapsed": info["elapsed"]}
        out.append(ev)
    return {"status": True, "data": {"normalized_items": out, "count": len(out)}}


# -- Quantitative forecast layer ---------------------------------------------
# Pure-stdlib, deterministic statistical models. Read-only and INFORMATIONAL:
# probabilities are form-based estimates, gaps are not value/bet signals.

DISCLAIMER = (
    "Informational sports market intelligence only. "
    "Not betting, trading, financial, or investment advice."
)
MODEL_CAVEATS = [
    "Model probability is a form-based statistical estimate, not a market-calibrated forecast.",
    "Pre-tournament confidence is low: seeded from FIFA/qualifier form until group results land.",
]
GAP_CAVEATS = [
    "Gap is informational only, not a value or bet signal.",
    "Fee-, liquidity-, and resolution-rule-blind. Verify settlement terms before acting.",
]
_FINAL_STATUS = {"FT", "AET", "PEN"}
_DEFAULT_RANK_WEIGHTS = {
    "outcome": 0.40, "attack": 0.32, "defense": 0.28,
    "win_rate": 0.60, "points_per_game": 0.40,
    "goals_per_game_norm": 0.70, "scoring_rate": 0.30,
    "concede_rate_inverted": 0.60, "clean_sheet_rate": 0.40,
}
_DEFAULT_XG_PARAMS = {
    "power_score_multiplier": 2.5,
    "goals_per_game_weight": 0.7,
    "defensive_impact_factor": 0.4,
    "home_advantage": 0.15,  # neutral-site tournament: much lower than club ~0.3
    "xg_min": 0.3,
    "xg_max": 4.0,
}


def _num(value: Any, default: float) -> float:
    """Float coercion that honors a default when value is None/non-numeric."""
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def _dc_tau(h: int, a: int, lh: float, la: float, rho: float) -> float:
    """Dixon-Coles low-score correlation adjustment."""
    if rho == 0:
        return 1.0
    if h == 0 and a == 0:
        return 1 - lh * la * rho
    if h == 0 and a == 1:
        return 1 + lh * rho
    if h == 1 and a == 0:
        return 1 + la * rho
    if h == 1 and a == 1:
        return 1 - rho
    return 1.0


def compute_power_ranking(request_data: dict[str, Any]) -> dict[str, Any]:
    """Group-relative team power ranking (0-1) from finished fixtures + seed blend.

    Params:
      - finished_fixtures: api-football fixture objects (status FT/AET/PEN)
      - seed_ratings: [{team_urn, team_name, seed_rating(0-1)}] FIFA/qualifier prior
      - weights: optional override of _DEFAULT_RANK_WEIGHTS
      - min_games_full_confidence: games for full results confidence (default 5)
    Bootstrap blend: power = w*results + (1-w)*seed, w = games/min_games. With 0
    games a team is 100% seed (data_source "seed", low confidence).
    """
    params = _params(request_data)
    w = dict(_DEFAULT_RANK_WEIGHTS)
    w.update(params.get("weights") or {})
    try:
        min_games = max(1, int(params.get("min_games_full_confidence") or 5))
    except (TypeError, ValueError):
        min_games = 5

    seed_map: dict[str, float] = {}
    seed_names: dict[str, str] = {}
    for s in _as_list(params.get("seed_ratings")):
        if not isinstance(s, dict):
            continue
        urn = _text(s.get("team_urn")) or _machina_team_urn(s.get("team_name"))
        if not urn:
            continue
        seed_map[urn] = _num(s.get("seed_rating"), 0.5)
        if _text(s.get("team_name")):
            seed_names[urn] = _text(s.get("team_name"))

    stats: dict[str, dict[str, Any]] = {}
    names: dict[str, str] = {}
    for f in _as_list(params.get("finished_fixtures")):
        if not isinstance(f, dict):
            continue
        if _text(((f.get("fixture") or {}).get("status") or {}).get("short")).upper() not in _FINAL_STATUS:
            continue
        teams = f.get("teams") or {}
        goals = f.get("goals") or {}
        hg, ag = goals.get("home"), goals.get("away")
        if hg is None or ag is None:
            continue
        hg, ag = int(hg), int(ag)
        for side, own, opp in (("home", hg, ag), ("away", ag, hg)):
            team = (teams.get(side) or {})
            name = _text(team.get("name"))
            if not name:
                continue
            urn = _machina_team_urn(name)
            names[urn] = name
            s = stats.setdefault(urn, {"games": 0, "wins": 0, "draws": 0, "losses": 0,
                                       "gf": 0, "ga": 0, "clean": 0, "scored": 0})
            s["games"] += 1
            s["gf"] += own
            s["ga"] += opp
            if own > opp:
                s["wins"] += 1
            elif own == opp:
                s["draws"] += 1
            else:
                s["losses"] += 1
            if opp == 0:
                s["clean"] += 1
            if own > 0:
                s["scored"] += 1

    played = []
    for urn, s in stats.items():
        g = s["games"]
        played.append({
            "team_urn": urn, "team_name": names.get(urn, urn), "games": g,
            "win_rate": s["wins"] / g, "points_per_game": (s["wins"] * 3 + s["draws"]) / g,
            "goals_per_game": s["gf"] / g, "concede_rate": s["ga"] / g,
            "clean_sheet_rate": s["clean"] / g, "scoring_rate": s["scored"] / g,
            "_raw": s,
        })

    gpg_norm = _minmax([t["goals_per_game"] for t in played])
    concede_norm = _minmax([t["concede_rate"] for t in played])

    rankings: list[dict[str, Any]] = []
    for i, t in enumerate(played):
        outcome = w["win_rate"] * t["win_rate"] + w["points_per_game"] * (t["points_per_game"] / 3.0)
        attack = w["goals_per_game_norm"] * gpg_norm[i] + w["scoring_rate"] * t["scoring_rate"]
        defense = w["concede_rate_inverted"] * (1 - concede_norm[i]) + w["clean_sheet_rate"] * t["clean_sheet_rate"]
        results_score = w["outcome"] * outcome + w["attack"] * attack + w["defense"] * defense
        urn = t["team_urn"]
        g = t["games"]
        blend_w = min(1.0, g / min_games)
        seed = seed_map.get(urn, 0.5)
        power = blend_w * results_score + (1 - blend_w) * seed
        rankings.append({
            "team_urn": urn, "team_name": t["team_name"],
            "power_score": round(power, 4),
            "breakdown": {"outcome_score": round(outcome, 4), "attack_score": round(attack, 4),
                          "defense_score": round(defense, 4)},
            "metrics": {k: round(t[k], 4) for k in ("win_rate", "points_per_game", "goals_per_game",
                                                    "concede_rate", "clean_sheet_rate", "scoring_rate")},
            "games": g,
            "confidence": round(max(0.15, min(1.0, g / min_games)), 3),
            "data_source": "results" if g >= min_games else "blend",
        })

    ranked_urns = {r["team_urn"] for r in rankings}
    seeded_only = 0
    for urn, rating in seed_map.items():
        if urn in ranked_urns:
            continue
        seeded_only += 1
        rankings.append({
            "team_urn": urn, "team_name": seed_names.get(urn, urn),
            "power_score": round(rating, 4),
            "breakdown": {"outcome_score": round(rating, 4), "attack_score": round(rating, 4),
                          "defense_score": round(rating, 4)},
            "metrics": {"win_rate": 0.0, "points_per_game": 0.0, "goals_per_game": 0.0,
                        "concede_rate": 0.0, "clean_sheet_rate": 0.0, "scoring_rate": 0.0},
            "games": 0, "confidence": 0.15, "data_source": "seed",
        })

    rankings.sort(key=lambda r: r["power_score"], reverse=True)
    for idx, r in enumerate(rankings, 1):
        r["rank"] = idx
    team_index = {r["team_urn"]: r for r in rankings}

    warnings = []
    if not played:
        warnings.append("No finished fixtures -- ranking is 100% seed (pre-tournament cold start).")
    if not seed_map:
        warnings.append("No seed_ratings supplied -- teams without results default to 0.5.")

    return {
        "status": True,
        "data": {
            "rankings": rankings, "team_index": team_index,
            "field_size": len(rankings), "seeded_only": seeded_only,
            "min_games_full_confidence": min_games,
            "warnings": warnings, "disclaimer": DISCLAIMER,
        },
    }


def normalize_fifa_seed(request_data: dict[str, Any]) -> dict[str, Any]:
    """Normalize FIFA/qualifier ranking into 0-1 seed ratings per team URN.

    Params: rankings [{team_name, points?, rank?}]. Prefers `points` (higher =
    stronger); falls back to `rank` (1 = strongest, inverted) when points are
    mostly absent — ranking positions are far more reliably grounded than points.
    Scores are min-max normalized into a [0.2, 0.8] band (so the weakest team is
    not a degenerate 0.0 that would zero out xG).
    """
    params = _params(request_data)
    # Optional canonical team list ({name, team_urn}/{_id}) so seed URNs match the
    # event/crosswalk URNs exactly (avoids name-variant URN drift, e.g. "USA").
    team_urn_by_slug: dict[str, str] = {}
    for t in _as_list(params.get("teams")):
        if not isinstance(t, dict):
            continue
        turn = _text(t.get("team_urn") or t.get("_id") or t.get("@id"))
        tname = _text(t.get("team_name") or t.get("name"))
        if turn and tname:
            team_urn_by_slug[_slugify(tname)] = turn

    rows = []  # (name, points|None, rank|None)
    for r in _as_list(params.get("rankings")):
        if not isinstance(r, dict):
            continue
        name = _text(r.get("team_name") or r.get("name"))
        if not name:
            continue
        pts = r.get("points", r.get("fifa_points"))
        rnk = r.get("rank", r.get("position"))
        pts = _to_float(pts) if pts is not None else None
        try:
            rnk = int(rnk) if rnk is not None else None
        except (TypeError, ValueError):
            rnk = None
        if pts is None and rnk is None:
            continue
        rows.append((name, pts, rnk))
    if not rows:
        return {"status": True, "data": {"seed_ratings": [], "count": 0,
                                         "warnings": ["No rankings supplied."], "disclaimer": DISCLAIMER}}

    have_points = [r for r in rows if r[1] is not None]
    use_points = len(have_points) >= max(1, len(rows) // 2)
    scored = []  # (name, score) — higher score = stronger
    for name, pts, rnk in rows:
        if use_points:
            if pts is None:
                continue
            scored.append((name, pts))
        elif rnk is not None:
            scored.append((name, -float(rnk)))  # rank 1 -> highest score
    norm = _minmax([s for _, s in scored])
    seen: dict[str, dict[str, Any]] = {}
    for (name, _s), n in zip(scored, norm):
        urn = team_urn_by_slug.get(_slugify(name)) or _machina_team_urn(name)
        rating = round(0.2 + 0.6 * n, 4)
        prev = seen.get(urn)
        if prev is None or rating > prev["seed_rating"]:
            seen[urn] = {"team_urn": urn, "team_name": name, "seed_rating": rating}
    seeds = list(seen.values())
    return {"status": True, "data": {"seed_ratings": seeds, "count": len(seeds),
                                     "basis": "points" if use_points else "rank", "disclaimer": DISCLAIMER}}


def _match_probabilities(home_ranking: dict[str, Any], away_ranking: dict[str, Any],
                         xg_params: dict[str, Any] | None = None,
                         rho: float = -0.12, max_goals: int = 10) -> dict[str, Any]:
    """Analytic Dixon-Coles 1X2/O-U/scoreline probabilities (deterministic, no sampling)."""
    xg = dict(_DEFAULT_XG_PARAMS)
    xg.update(xg_params or {})
    try:
        rho = max(-0.20, min(0.0, float(rho)))
    except (TypeError, ValueError):
        rho = -0.12
    try:
        max_goals = max(4, min(int(max_goals), 15))
    except (TypeError, ValueError):
        max_goals = 10

    hp = _num((home_ranking or {}).get("power_score"), 0.5)
    ap = _num((away_ranking or {}).get("power_score"), 0.5)
    hb = (home_ranking or {}).get("breakdown") or {}
    ab = (away_ranking or {}).get("breakdown") or {}
    h_attack = _num(hb.get("attack_score"), hp)
    h_def = _num(hb.get("defense_score"), hp)
    a_attack = _num(ab.get("attack_score"), ap)
    a_def = _num(ab.get("defense_score"), ap)
    h_gpg = _num(((home_ranking or {}).get("metrics") or {}).get("goals_per_game"), 0.0)
    a_gpg = _num(((away_ranking or {}).get("metrics") or {}).get("goals_per_game"), 0.0)

    mult, gpgw, deffac = xg["power_score_multiplier"], xg["goals_per_game_weight"], xg["defensive_impact_factor"]
    home_xg = (hp * mult + h_gpg * gpgw) * max(h_attack, 0.2) * (1 - a_def * deffac) + xg["home_advantage"]
    away_xg = (ap * mult + a_gpg * gpgw) * max(a_attack, 0.2) * (1 - h_def * deffac)
    home_xg = max(xg["xg_min"], min(xg["xg_max"], home_xg))
    away_xg = max(xg["xg_min"], min(xg["xg_max"], away_xg))

    hp_probs = [_poisson_pmf(k, home_xg) for k in range(max_goals + 1)]
    ap_probs = [_poisson_pmf(k, away_xg) for k in range(max_goals + 1)]
    cells = []
    total = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = hp_probs[h] * ap_probs[a] * _dc_tau(h, a, home_xg, away_xg, rho)
            total += p
            cells.append((h, a, p))
    if total > 0:
        cells = [(h, a, p / total) for h, a, p in cells]

    hw = dw = aw = over = 0.0
    for h, a, p in cells:
        if h > a:
            hw += p
        elif h == a:
            dw += p
        else:
            aw += p
        if h + a > 2:  # integer goals: total > 2.5 == >= 3
            over += p

    top = sorted(cells, key=lambda c: c[2], reverse=True)
    most_likely = top[0]
    confidence = round(min(_num((home_ranking or {}).get("confidence"), 0.15),
                           _num((away_ranking or {}).get("confidence"), 0.15)), 3)
    return {
        "home_expected_goals": round(home_xg, 3),
        "away_expected_goals": round(away_xg, 3),
        "expected_total_goals": round(home_xg + away_xg, 3),
        "probabilities": {
            "home_win": round(hw, 4), "draw": round(dw, 4), "away_win": round(aw, 4),
            "over_2_5": round(over, 4), "under_2_5": round(1 - over, 4),
        },
        "most_likely_score": f"{most_likely[0]}-{most_likely[1]}",
        "exact_scorelines": {f"{h}-{a}": round(p, 4) for h, a, p in top[:8]},
        "confidence": confidence,
        "correlation_rho": rho,
        "method": "dixon_coles_analytic_stdlib",
    }


def compute_match_probabilities(request_data: dict[str, Any]) -> dict[str, Any]:
    """Command wrapper around _match_probabilities (one fixture).

    Params: home_ranking, away_ranking (compute_power_ranking entries), xg_params?,
    rho? (default -0.12), max_goals? (default 10).
    """
    params = _params(request_data)
    result = _match_probabilities(
        params.get("home_ranking") or {},
        params.get("away_ranking") or {},
        params.get("xg_params"),
        _num(params.get("rho"), -0.12),
        int(params.get("max_goals") or 10),
    )
    result["caveats"] = list(MODEL_CAVEATS)
    result["disclaimer"] = DISCLAIMER
    return {"status": True, "data": result}


def build_event_forecasts(request_data: dict[str, Any]) -> dict[str, Any]:
    """Build worldcup:model-forecast docs for upcoming events from a team_index.

    Params: events (worldcup:event docs), team_index ({team_urn: ranking} from
    compute_power_ranking), xg_params?, rho?, max_goals?.
    """
    params = _params(request_data)
    team_index = params.get("team_index") or {}
    xg_params = params.get("xg_params")
    rho = _num(params.get("rho"), -0.12)
    max_goals = int(params.get("max_goals") or 10)

    docs: list[dict[str, Any]] = []
    skipped: list[str] = []
    for ev in _as_list(params.get("events")):
        if not isinstance(ev, dict):
            continue
        event_urn = _text(_first(ev, "_id", "@id", "id"))
        home = away = None
        for c in ev.get("sport:competitors") or []:
            q = _lower(c.get("sport:qualifier"))
            if q == "home":
                home = c
            elif q == "away":
                away = c
        if not home or not away or not event_urn:
            skipped.append(event_urn or "unknown")
            continue
        hr = team_index.get(_text(home.get("@id")))
        ar = team_index.get(_text(away.get("@id")))
        if not hr or not ar:
            skipped.append(event_urn)
            continue
        probs = _match_probabilities(hr, ar, xg_params, rho, max_goals)
        sources = {hr.get("data_source"), ar.get("data_source")}
        data_source = "results" if sources == {"results"} else ("seed" if "seed" in sources else "blend")
        confidence = probs["confidence"]
        flags = []
        if data_source != "results":
            flags.append("bootstrap_seeded")
        if confidence < 0.5:
            flags.append("low_sample_size")
        docs.append({
            "metadata": {"event_urn": event_urn},
            "_id": event_urn, "@id": event_urn, "id": event_urn,
            "provider_ids": {"api_football": _text((ev.get("provider_ids") or {}).get("api_football"))},
            "schema:startDate": ev.get("schema:startDate"),
            "home_team": {"urn": _text(home.get("@id")), "name": _text(home.get("name"))},
            "away_team": {"urn": _text(away.get("@id")), "name": _text(away.get("name"))},
            "home_expected_goals": probs["home_expected_goals"],
            "away_expected_goals": probs["away_expected_goals"],
            "probabilities": probs["probabilities"],
            "most_likely_score": probs["most_likely_score"],
            "exact_scorelines": probs["exact_scorelines"],
            "confidence": confidence,
            "data_source": data_source,
            "flags": flags,
            "model": {"method": probs["method"], "rho": probs["correlation_rho"], "computed_at": _now_iso()},
            "caveats": list(MODEL_CAVEATS),
            "disclaimer": DISCLAIMER,
        })

    return {
        "status": True,
        "data": {"forecasts": docs, "count": len(docs), "skipped": skipped, "disclaimer": DISCLAIMER},
    }


def _gap_candidates(probs: dict[str, Any], outcomes: list[Any],
                    home_name: Any, away_name: Any, min_gap_bps: int) -> list[dict[str, Any]]:
    """Per-1X2-bucket model-vs-market gaps. Informational only."""
    home_slug = _slugify(home_name) if home_name else ""
    away_slug = _slugify(away_name) if away_name else ""
    buckets: dict[str, float] = {}
    for o in outcomes:
        if not isinstance(o, dict):
            continue
        name = _lower(o.get("outcome_name") or o.get("name"))
        if o.get("price") is None:
            continue
        price = _to_float(o.get("price"))
        if price == 0.0:
            continue
        name_slug = _slugify(name)
        if "draw" in name or "tie" in name:
            bucket = "draw"
        elif home_slug and home_slug in name_slug:
            bucket = "home_win"
        elif away_slug and away_slug in name_slug:
            bucket = "away_win"
        else:
            continue
        buckets.setdefault(bucket, price)

    gaps = []
    for bucket, price in buckets.items():
        model_prob = probs.get(bucket)
        if model_prob is None:
            continue
        model_prob = _to_float(model_prob)
        gap = round(model_prob - price, 4)
        gap_bps = round(abs(gap) * 10000)
        if gap_bps < min_gap_bps:
            continue
        gaps.append({
            "outcome": bucket, "model_prob": round(model_prob, 4), "market_price": round(price, 4),
            "gap": gap, "gap_bps": gap_bps, "model_richer": gap > 0,
        })
    gaps.sort(key=lambda g: g["gap_bps"], reverse=True)
    return gaps


def _model_vs_market_candidates(cached: list[dict[str, Any]], forecasts: list[Any],
                                min_edge_bps: int) -> list[dict[str, Any]]:
    """Build model_vs_market edge candidates for detect_market_edges.

    Markets are joined to forecasts by event_urn when present, and otherwise by the
    team-pair (related_team_urns) — so the gap works even when the market sync has
    not stamped an event_urn onto a cached market yet.
    """
    by_event: dict[str, list[Any]] = {}
    by_pair: dict[frozenset, list[Any]] = {}
    for m in cached:
        if not isinstance(m, dict):
            continue
        outs = m.get("outcomes") or []
        eu = _text(m.get("event_urn"))
        if eu:
            by_event.setdefault(eu, []).extend(outs)
        pair = frozenset(_text(u) for u in (m.get("related_team_urns") or []) if _text(u))
        if len(pair) == 2:
            by_pair.setdefault(pair, []).extend(outs)

    candidates = []
    for fc in forecasts:
        if not isinstance(fc, dict):
            continue
        eu = _text(_first(fc, "_id", "@id", "id")) or _text((fc.get("metadata") or {}).get("event_urn"))
        probs = fc.get("probabilities") or {}
        if not probs:
            continue
        home = (fc.get("home_team") or {})
        away = (fc.get("away_team") or {})
        outcomes = by_event.get(eu)
        if not outcomes:
            pair = frozenset(x for x in (_text(home.get("urn")), _text(away.get("urn"))) if x)
            if len(pair) == 2:
                outcomes = by_pair.get(pair)
        if not outcomes:
            continue
        for g in _gap_candidates(probs, outcomes, home.get("name"), away.get("name"), min_edge_bps):
            candidates.append({
                "candidate_type": "model_vs_market",
                "event_urn": eu,
                "outcome": g["outcome"],
                "model_prob": g["model_prob"],
                "market_price": g["market_price"],
                "gap": g["gap"],
                "edge_bps": g["gap_bps"],
                "model_richer": g["model_richer"],
                "caveats": MODEL_CAVEATS + GAP_CAVEATS,
            })
    return candidates


def compute_model_vs_market_edge(request_data: dict[str, Any]) -> dict[str, Any]:
    """Compare model 1X2 probabilities to market prices for ONE event.

    Params: model_probabilities {home_win,draw,away_win}, market_outcomes
    [{name|outcome_name, price}], home_team, away_team, min_gap_bps (default 100),
    event_urn.
    """
    params = _params(request_data)
    try:
        min_gap_bps = int(params.get("min_gap_bps") or 100)
    except (TypeError, ValueError):
        min_gap_bps = 100
    gaps = _gap_candidates(
        params.get("model_probabilities") or {},
        _as_list(params.get("market_outcomes")),
        params.get("home_team"), params.get("away_team"), min_gap_bps,
    )
    return {
        "status": True,
        "data": {
            "gaps": gaps,
            "max_gap_bps": max((g["gap_bps"] for g in gaps), default=0),
            "count": len(gaps),
            "event_urn": _text(params.get("event_urn")),
            "min_gap_bps": min_gap_bps,
            "caveats": MODEL_CAVEATS + GAP_CAVEATS,
            "disclaimer": DISCLAIMER,
        },
    }


def _single_audit(forecast: dict[str, Any], home_goals: int, away_goals: int) -> dict[str, Any]:
    probs = forecast.get("probabilities") or {}
    hw, dw, aw = _to_float(probs.get("home_win")), _to_float(probs.get("draw")), _to_float(probs.get("away_win"))
    ov, un = _to_float(probs.get("over_2_5")), _to_float(probs.get("under_2_5"))
    total = home_goals + away_goals
    a_home = 1 if home_goals > away_goals else 0
    a_draw = 1 if home_goals == away_goals else 0
    a_away = 1 if home_goals < away_goals else 0
    a_over = 1 if total > 2.5 else 0
    brier_home = (hw - a_home) ** 2
    brier_draw = (dw - a_draw) ** 2
    brier_away = (aw - a_away) ** 2
    brier_over = (ov - a_over) ** 2
    combined = (brier_home + brier_draw + brier_away) / 3
    probs3 = {"home_win": hw, "draw": dw, "away_win": aw}
    predicted = max(probs3, key=probs3.get)
    predicted_prob = probs3[predicted]
    actual_outcome = "home_win" if a_home else ("draw" if a_draw else "away_win")
    cbin = min(int(predicted_prob * 10), 9)
    return {
        "metadata": {"event_urn": _text(_first(forecast, "_id", "@id", "id"))},
        "_id": _text(_first(forecast, "_id", "@id", "id")),
        "event_urn": _text(_first(forecast, "_id", "@id", "id")),
        "fixture_id": _text((forecast.get("provider_ids") or {}).get("api_football")),
        "predicted_probabilities": {"home_win": round(hw, 4), "draw": round(dw, 4),
                                    "away_win": round(aw, 4), "over_2_5": round(ov, 4), "under_2_5": round(un, 4)},
        "actual_result": {"home_goals": home_goals, "away_goals": away_goals,
                          "total_goals": total, "outcome": actual_outcome},
        "brier_scores": {"home_win": round(brier_home, 4), "draw": round(brier_draw, 4),
                         "away_win": round(brier_away, 4), "combined_1x2": round(combined, 4),
                         "over_2_5": round(brier_over, 4)},
        "calibration": {"predicted_outcome": predicted, "predicted_probability": round(predicted_prob, 4),
                        "actual_outcome": actual_outcome, "prediction_correct": predicted == actual_outcome,
                        "calibration_bin": cbin, "calibration_bin_label": f"{cbin * 10}-{(cbin + 1) * 10}%"},
        "exact_score_correct": _text(forecast.get("most_likely_score")) == f"{home_goals}-{away_goals}",
        "audited_at": _now_iso(),
        "disclaimer": DISCLAIMER,
    }


def _aggregate_audit(audits: list[dict[str, Any]]) -> dict[str, Any]:
    audits = [a for a in audits if isinstance(a, dict) and a.get("brier_scores")]
    n = len(audits)
    if n == 0:
        return {"sample_size": 0, "sample_size_sufficient": False,
                "recommendation": "No audited forecasts yet.", "disclaimer": DISCLAIMER}
    avg_1x2 = sum(a["brier_scores"].get("combined_1x2", 0.25) for a in audits) / n
    avg_over = sum(a["brier_scores"].get("over_2_5", 0.25) for a in audits) / n
    correct = sum(1 for a in audits if (a.get("calibration") or {}).get("prediction_correct"))
    bins = [{"count": 0, "correct": 0, "sum_pred": 0.0} for _ in range(10)]
    for a in audits:
        cal = a.get("calibration") or {}
        b = int(cal.get("calibration_bin", 0))
        b = max(0, min(9, b))
        bins[b]["count"] += 1
        bins[b]["correct"] += 1 if cal.get("prediction_correct") else 0
        bins[b]["sum_pred"] += _to_float(cal.get("predicted_probability"))
    curve = []
    cal_error_num = 0.0
    for i, bk in enumerate(bins):
        if bk["count"] == 0:
            continue
        pred_avg = bk["sum_pred"] / bk["count"]
        actual_rate = bk["correct"] / bk["count"]
        curve.append({"bin": i, "label": f"{i * 10}-{(i + 1) * 10}%", "count": bk["count"],
                      "predicted_avg": round(pred_avg, 4), "actual_rate": round(actual_rate, 4)})
        cal_error_num += bk["count"] * abs(pred_avg - actual_rate)
    avg_cal_error = round(cal_error_num / n, 4)
    better = avg_1x2 < 0.25
    rec = ("Brier %.4f vs 0.25 random (%s); calibration error %.4f (target <0.05)."
           % (avg_1x2, "better than random" if better else "not better than random", avg_cal_error))
    return {
        "sample_size": n,
        "sample_size_sufficient": n >= 50,
        "brier_scores": {"avg_1x2": round(avg_1x2, 4), "avg_over_2_5": round(avg_over, 4),
                         "baseline_random": 0.25, "is_better_than_random": better},
        "accuracy": {"correct": correct, "total": n, "accuracy_percent": round(100 * correct / n, 2)},
        "calibration": {"avg_calibration_error": avg_cal_error, "curve": curve},
        "recommendation": rec,
        "disclaimer": DISCLAIMER,
    }


def compute_forecast_audit(request_data: dict[str, Any]) -> dict[str, Any]:
    """Brier + calibration audit. Modes: single | batch | aggregate (inferred if absent).

    single: forecast + actual_result {home_goals, away_goals}
    batch: forecasts[] + finished_fixtures[] (matched by api-football fixture id)
    aggregate: audit_results[] -> backtesting_report
    """
    params = _params(request_data)
    mode = _text(params.get("mode")).lower()
    if not mode:
        if params.get("audit_results") is not None:
            mode = "aggregate"
        elif params.get("forecasts") is not None:
            mode = "batch"
        else:
            mode = "single"

    if mode == "aggregate":
        report = _aggregate_audit(_as_list(params.get("audit_results")))
        return {"status": True, "data": {"backtesting_report": report,
                                         "_id": "worldcup:forecast-audit:aggregate",
                                         "metadata": {"event_urn": "worldcup:forecast-audit:aggregate"},
                                         "name_hint": "aggregate"}}

    if mode == "batch":
        by_fid: dict[str, tuple[int, int]] = {}
        for f in _as_list(params.get("finished_fixtures")):
            if not isinstance(f, dict):
                continue
            if _text(((f.get("fixture") or {}).get("status") or {}).get("short")).upper() not in _FINAL_STATUS:
                continue
            fid = _text((f.get("fixture") or {}).get("id"))
            goals = f.get("goals") or {}
            if fid and goals.get("home") is not None and goals.get("away") is not None:
                by_fid[fid] = (int(goals["home"]), int(goals["away"]))
        audits = []
        for fc in _as_list(params.get("forecasts")):
            if not isinstance(fc, dict):
                continue
            fid = _text((fc.get("provider_ids") or {}).get("api_football"))
            res = by_fid.get(fid)
            if not res:
                continue
            audits.append(_single_audit(fc, res[0], res[1]))
        return {"status": True, "data": {"audits": audits, "count": len(audits), "disclaimer": DISCLAIMER}}

    # single
    forecast = params.get("forecast") or {}
    actual = params.get("actual_result") or {}
    hg = actual.get("home_goals", (actual.get("goals") or {}).get("home"))
    ag = actual.get("away_goals", (actual.get("goals") or {}).get("away"))
    if not forecast or hg is None or ag is None:
        return {"status": False, "data": {"error": "single mode needs forecast + actual_result {home_goals, away_goals}"}}
    return {"status": True, "data": {"audit_result": _single_audit(forecast, int(hg), int(ag)), "disclaimer": DISCLAIMER}}


# -- Prematch enrichment scheduling ------------------------------------------
# Countdown-aware refresh tiers: (countdown < N hours) -> refresh every M hours.
# Closer to kickoff = fresher. Beyond the last tier -> 72h.
_PREMATCH_TIERS = [(24.0, 2.0), (72.0, 6.0), (168.0, 48.0)]


def _parse_iso(value: Any) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def select_prematch_fixtures(request_data: dict[str, Any]) -> dict[str, Any]:
    """Pick upcoming fixtures due for prematch enrichment, nearest kickoff first.

    Replaces the flat "first N events" selection with a countdown-aware staleness
    rule: a fixture is due when it has never been enriched OR its last enrichment
    is older than the tier interval for its kickoff countdown (see _PREMATCH_TIERS).
    Finished fixtures and those kicked off > 6h ago are skipped.

    Params: events (worldcup:event docs), limit (default 10), force (ignore
    staleness), now_iso (optional, for testing).
    """
    params = _params(request_data)
    try:
        limit = max(1, int(params.get("limit") or 10))
    except (TypeError, ValueError):
        limit = 10
    force = bool(params.get("force", False))
    now = _parse_iso(params.get("now_iso")) or datetime.now(timezone.utc)

    selected: list[tuple[datetime, dict[str, Any]]] = []
    for ev in _as_list(params.get("events")):
        if not isinstance(ev, dict):
            continue
        if _text(ev.get("sport:status")).upper() in _FINAL_STATUS:
            continue
        ko = _parse_iso(ev.get("schema:startDate"))
        if ko is None:
            continue
        countdown_h = (ko - now).total_seconds() / 3600.0
        if countdown_h < -6:  # already kicked off long ago (and not flagged final) — skip
            continue
        cd = countdown_h if countdown_h > 0 else 0.0
        interval_h = 72.0
        for max_h, iv in _PREMATCH_TIERS:
            if cd < max_h:
                interval_h = iv
                break
        last = _parse_iso(ev.get("prematch_research_at"))
        due = force or last is None or (now - last).total_seconds() / 3600.0 >= interval_h
        if due:
            selected.append((ko, ev))

    selected.sort(key=lambda x: x[0])
    fixtures = [ev for _, ev in selected[:limit]]
    return {
        "status": True,
        "data": {"fixtures": fixtures, "count": len(fixtures), "considered": len(_as_list(params.get("events")))},
    }
