def resolve_market_prices(request_data):
    """
    Resolve a single representative YES price per market and prepare markets_for_kelly.

    For past matches (is_past_match=True):
      - Prefer the most recent trade in the kickoff-filtered window (market_trade_prices[...].yes_price)
      - Fallback to the live snapshot yes_ask if trade price is missing

    For live matches (is_past_match=False):
      - Use the live snapshot yes_ask

    Returns in the standard pyscript pattern: {status, data, message}
    """
    try:
        import json

        # Parse request_data
        if isinstance(request_data, str):
            try:
                request_data = json.loads(request_data)
            except Exception:
                pass

        if not isinstance(request_data, dict):
            request_data = {}

        params = request_data.get("params", request_data)
        if not isinstance(params, dict):
            params = {}

        markets = params.get("markets", [])
        if not isinstance(markets, list):
            markets = []

        market_trade_prices = params.get("market_trade_prices", [])
        if not isinstance(market_trade_prices, list):
            market_trade_prices = []

        is_past_match = bool(params.get("is_past_match", False))

        # Build a lookup from trade list (best-effort: one element per ticker is expected)
        trade_by_ticker = {}
        for item in market_trade_prices:
            if not isinstance(item, dict):
                continue
            t = item.get("ticker")
            if not t:
                continue
            trade_by_ticker[t] = item

        market_prices = []
        markets_for_kelly = []

        for m in markets:
            if not isinstance(m, dict):
                continue

            ticker = m.get("ticker")
            yes_ask = m.get("yes_ask")
            yes_ask_dollars = m.get("yes_ask_dollars")

            price_cents = None
            price_dollars = None
            price_source = "unknown"

            if is_past_match:
                tr = trade_by_ticker.get(ticker, {})
                yes_price = tr.get("yes_price")
                yes_price_dollars = tr.get("yes_price_dollars")

                if yes_price is not None:
                    price_cents = yes_price
                    price_dollars = yes_price_dollars
                    price_source = "past_trades"
                else:
                    price_cents = yes_ask
                    price_dollars = yes_ask_dollars
                    price_source = "live_markets_fallback"
            else:
                price_cents = yes_ask
                price_dollars = yes_ask_dollars
                price_source = "live_markets"

            market_prices.append(
                {
                    "ticker": ticker,
                    "price_cents": price_cents,
                    "price_dollars": price_dollars,
                    "price_source": price_source,
                }
            )

            # Override yes_ask with computed price_cents so downstream Kelly uses it
            m2 = dict(m)
            if price_cents is not None:
                m2["yes_ask"] = price_cents
            if price_dollars is not None:
                m2["yes_ask_dollars"] = price_dollars
            markets_for_kelly.append(m2)

        # Summary (similar to mappings/kalshi-markets-summary.yml but based on markets_for_kelly)
        markets_summary = []
        for market in markets_for_kelly:
            if not isinstance(market, dict):
                continue
            parts = []
            if market.get("ticker"):
                parts.append(str(market.get("ticker")))
            if market.get("title"):
                parts.append(str(market.get("title")))
            if market.get("status"):
                parts.append(f"status: {market.get('status')}")

            parts.append(
                f"yes {market.get('yes_bid_dollars', market.get('yes_bid'))} / {market.get('yes_ask_dollars', market.get('yes_ask'))}"
            )
            parts.append(
                f"no {market.get('no_bid_dollars', market.get('no_bid'))} / {market.get('no_ask_dollars', market.get('no_ask'))}"
            )
            parts.append(f"liq: {market.get('liquidity_dollars', market.get('liquidity'))}")

            if market.get("volume_24h") is not None:
                parts.append(f"vol24h: {market.get('volume_24h')}")
            if market.get("expiration_time"):
                parts.append(f"exp: {market.get('expiration_time')}")

            markets_summary.append(" | ".join([p for p in parts if p]))

        # Top-level source label used (for doc metadata)
        prices_source = "past_trades" if is_past_match else "live_markets"

        data = {
            "prices_source": prices_source,
            "market_prices": market_prices,
            "markets_for_kelly": markets_for_kelly,
            "markets_count": len(markets),
            "markets_summary": markets_summary,
        }

        return {
            "status": True,
            "data": data,
            "message": f"Resolved {len(markets)} markets prices via {prices_source}",
        }

    except Exception as e:
        return {
            "status": False,
            "data": {"error": str(e)},
            "message": f"Price resolver error: {str(e)}",
        }


