"""World Cup market-intelligence connector utilities.

This connector intentionally performs only read-only normalization/filtering. It
accepts payloads returned by the shared `sports-skills` connector and converts
Kalshi/Polymarket market records into a stable shape for API/MCP/x402 exposure.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
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

    Params:
      - cached_markets: normalized WorldCupMarket[] (worldcup:market-cache)
      - matches: match_markets output (optional; enables cross-venue)
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


# -- Canonical reads: standings + squads -------------------------------------
#
# These pair api-football (official, authoritative) with sports-skills (ESPN,
# crests, fallback) per the "both strengths where needed" split:
#   - standings: api-football primary, sports-skills fallback + crest backfill
#   - squads:    api-football only (official 26-man lists)


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
    """Unify api-football (primary) + sports-skills (fallback) WC standings.

    Params:
      - af: raw api-football /standings response
      - ss: raw sports-skills get_season_standings response
      - league_id, season: passthrough labels for the envelope
    api-football carries official points/GD; sports-skills is the fallback and
    backfills crests when api-football rows lack a logo.
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
    """Unify api-football (primary) + sports-skills (fallback) squads.

    Params per side ("home"/"away"):
      - {side}_af: raw api-football /players/squads response (official 26-man)
      - {side}_ss: raw sports-skills get_team_profile response (full pool fallback)
      - {side}_team_id, {side}_team: resolved labels (optional; backfilled)
    api-football is the official trimmed list; sports-skills is the fallback when
    api-football is empty (e.g. unauthenticated or squad not yet published).
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
    api-football is the only structured World Cup injury source — sports-skills
    get_missing_players is Premier-League-only — so this read is af-backed.
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
            "fixture_id": (ev.get("provider_ids") or {}).get("api_football_fixture_id"),
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
    """Normalize identity crosswalk rows into MCP document-store values.

    The connector only reshapes caller-provided provider ids; it never invents
    missing provider ids. Provider mappings must come from verified upstream
    payloads (API-Football, Entain, Sportradar, Opta, ESPN, Transfermarkt, etc.).
    """
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
            "raw_provider": item.get("raw_provider", "multi-provider"),
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


# -- Canonical machina identity helpers (shared by crosswalk + event minting) --
#
# These were lifted out of normalize_identity_crosswalk so mint_event_identity
# mints the SAME urn:machina:sport:soccer:... scheme from API-Football fixtures.

_ISO3_MAP = {
    "ARG": "arg", "ARGENTINA": "arg", "AUS": "aus", "AUSTRALIA": "aus",
    "AUT": "aut", "AUSTRIA": "aut", "BEL": "bel", "BELGIUM": "bel",
    "BRA": "bra", "BRASIL": "bra", "BRAZIL": "bra", "CAN": "can", "CANADA": "can",
    "CHE": "che", "SWITZERLAND": "che", "CH": "che", "COL": "col", "COLOMBIA": "col",
    "CIV": "civ", "COTE D IVOIRE": "civ", "CÔTE D’IVOIRE": "civ", "IVORY COAST": "civ",
    "DEU": "deu", "GERMANY": "deu", "ECU": "ecu", "ECUADOR": "ecu",
    "EGY": "egy", "EGYPT": "egy", "ENG": "eng", "ENGLAND": "eng",
    "ESP": "esp", "SPAIN": "esp", "FRA": "fra", "FRANCE": "fra",
    "GHA": "gha", "GHANA": "gha", "HRV": "hrv", "CROATIA": "hrv",
    "IRN": "irn", "IR IRAN": "irn", "IRAN": "irn", "IRQ": "irq", "IRAQ": "irq",
    "ITA": "ita", "ITALY": "ita", "JPN": "jpn", "JAPAN": "jpn",
    "KOR": "kor", "KOREA REPUBLIC": "kor", "SOUTH KOREA": "kor",
    "MAR": "mar", "MOROCCO": "mar", "MEX": "mex", "MEXICO": "mex",
    "NLD": "nld", "NETHERLANDS": "nld", "NZL": "nzl", "NEW ZEALAND": "nzl",
    "PRY": "pry", "PARAGUAY": "pry", "QAT": "qat", "QATAR": "qat",
    "SAU": "sau", "SAUDI ARABIA": "sau", "SCO": "sco", "SCOTLAND": "sco",
    "SEN": "sen", "SENEGAL": "sen", "TUN": "tun", "TUNISIA": "tun",
    "TUR": "tur", "TURKIYE": "tur", "TÜRKIYE": "tur", "TURKEY": "tur",
    "URY": "ury", "URUGUAY": "ury", "USA": "usa", "UNITED STATES": "usa",
    "WAL": "wal", "WALES": "wal", "ZAF": "zaf", "SOUTH AFRICA": "zaf",
    "CAPE VERDE": "cpv", "CAPE VERDE ISLANDS": "cpv", "CURACAO": "cuw", "CURAÇAO": "cuw",
    "UZBEKISTAN": "uzb", "CONGO DR": "cod", "DR CONGO": "cod", "JORDAN": "jor",
    "BOSNIA HERZEGOVINA": "bih", "BOSNIA AND HERZEGOVINA": "bih", "BOSNIA  HERZEGOVINA": "bih",
    "PANAMA": "pan", "NORWAY": "nor", "SWEDEN": "swe", "PORTUGAL": "por",
    "SERBIA": "srb", "SOUTH KOREA REPUBLIC": "kor",
}

# Backwards-compatible alias for normalize_identity_crosswalk's body.
iso_mapping = _ISO3_MAP


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _to_iso3(country: Any) -> str:
    cleaned = re.sub(r"[^A-Z ]", " ", _clean_text(country).upper())
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
    # National-team country == team name for the World Cup.
    return f"urn:machina:sport:soccer:team:{_slugify(name)}:{_to_iso3(name)}"


def mint_event_identity(request_data: dict[str, Any]) -> dict[str, Any]:
    """Mint canonical IPTC World Cup event docs with machina URNs from API-Football fixtures.

    API-Football is the data source; the canonical id is the machina URN
    (urn:machina:sport:soccer:event:{home}-vs-{away}:{YYYYMMDD}:wor) — the SAME
    scheme normalize_identity_crosswalk mints, so events and the crosswalk agree.
    provider_ids carry every provider key (incl. api_football_venue_id) so the
    exposed API can join by the api-football fixture id (provider_event_id) — the
    stable alternate key. Venue URN is null-safe (no urn:...:venue:None).
    """
    params = _params(request_data)
    fixtures = _as_list(params.get("fixtures"))
    comp_slug = _text(params.get("competition_slug")) or "world-cup-2026"
    events: list[dict[str, Any]] = []
    warnings: list[str] = []

    for f in fixtures:
        if not isinstance(f, dict):
            continue
        fixture = f.get("fixture", {}) if isinstance(f.get("fixture"), dict) else {}
        league = f.get("league", {}) if isinstance(f.get("league"), dict) else {}
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
        comp_name = _text(league.get("name")) or "World Cup"
        comp_urn = f"urn:machina:sport:soccer:competition:{_slugify(comp_name)}:wor"

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
            "provider_ids": {
                "api_football_fixture_id": fixture_id,
                "api_football_league_id": _text(league.get("id")),
                "api_football_home_team_id": _text(home.get("id")),
                "api_football_away_team_id": _text(away.get("id")),
                "api_football_venue_id": _text(venue.get("id")),
            },
            "machina_competition_slug": comp_slug,
            "raw_provider": "api-football",
        }
        events.append(doc)

    if not events:
        warnings.append("No fixtures supplied.")
    return {
        "status": True,
        "data": {"sport_schema_events": events, "events": events, "count": len(events), "warnings": warnings},
    }
