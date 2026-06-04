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
        priced = [(leg, _yes_price(leg)) for leg in legs]
        priced = [(leg, p) for leg, p in priced if p is not None]
        if len(priced) < 2:
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
        if k_tie is None or p_draw is None:
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
