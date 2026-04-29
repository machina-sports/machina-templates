# Polymarket Pricing API (CLOB)

Reference for real-time pricing, order books, and trade history via the CLOB API.

## Getting Real-Time Prices

Use `clob_token_id` from market outcomes to fetch live prices.

```python
# Get midpoint + buy/sell prices for a token
mcp__docker-localhost__connector_executor(
    name="polymarket",
    command="get_market_prices",
    payload={"token_id": "<clob_token_id>"}
)
# Returns: {midpoint: 0.65, buy_price: 0.64, sell_price: 0.66}

# Batch prices for multiple tokens (max 20)
mcp__docker-localhost__connector_executor(
    name="polymarket",
    command="get_market_prices",
    payload={"token_ids": ["tok_1", "tok_2", "tok_3"]}
)
```

## Order Book

```python
mcp__docker-localhost__connector_executor(
    name="polymarket",
    command="get_order_book",
    payload={"token_id": "<clob_token_id>"}
)
# Returns: {bids: [...], asks: [...], best_bid, best_ask, spread, bid_depth, ask_depth}
```

## Price History

```python
mcp__docker-localhost__connector_executor(
    name="polymarket",
    command="get_price_history",
    payload={
        "token_id": "<clob_token_id>",
        "interval": "max",   # or "1d", "1w", "1m"
        "fidelity": 120      # data points
    }
)
```

## Last Trade Price

```python
mcp__docker-localhost__connector_executor(
    name="polymarket",
    command="get_last_trade_price",
    payload={"token_id": "<clob_token_id>"}
)
# Returns: {price: 0.65, side: "BUY"}
```

## API Endpoints

| Endpoint | Base URL | Description |
|----------|----------|-------------|
| `/midpoint` | `clob.polymarket.com` | Current midpoint price |
| `/price` | `clob.polymarket.com` | Buy/sell price by side |
| `/book` | `clob.polymarket.com` | Full order book |
| `/prices-history` | `clob.polymarket.com` | Historical price data |
| `/last-trade-price` | `clob.polymarket.com` | Last executed trade |

All CLOB endpoints are public and require no authentication.
