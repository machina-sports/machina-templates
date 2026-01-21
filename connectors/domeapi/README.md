# DomeAPI Connector

## Overview

The DomeAPI connector provides comprehensive access to prediction market data across multiple platforms including Polymarket and Kalshi. Get real-time market prices, historical candlestick data, wallet analytics, order tracking, and cross-platform market matching.

## Features

- **Multi-Platform Support**: Access data from Polymarket, Kalshi, and more
- **Real-Time Market Data**: Get current prices and market information
- **Historical Data**: Access orderbook history, trade history, and candlestick/OHLCV data
- **Wallet Analytics**: Track wallet performance and profit/loss
- **Cross-Platform Matching**: Find matching markets across different platforms for sports events

## Configuration

### Environment Variables

The connector requires an API key from DomeAPI:

```bash
MACHINA_CONTEXT_VARIABLE_DOMEAPI_API_KEY=your-api-key-here
```

### Getting Your API Key

1. Sign up at [https://domeapi.io/](https://domeapi.io/)
2. Get your API key from the [dashboard](https://domeapi.io/dashboard)
3. Store it in your environment variables or secrets vault

### Rate Limits

Rate limits are tiered by subscription level:

| Tier | Queries Per Second | Queries Per 10 Seconds |
|------|-------------------|------------------------|
| Free | 1 | 10 |
| Dev | 100 | 500 |
| Enterprise | Custom | Custom |

## Available Commands

### Polymarket Endpoints

#### GetPolymarketMarkets
Find markets on Polymarket using various filters.

**Parameters:**
- `query` (string, optional): Search query to filter markets
- `limit` (integer, optional): Maximum number of markets to return (default: 20)
- `offset` (integer, optional): Offset for pagination (default: 0)

**Example:**
```yaml
- type: "connector"
  name: "fetch-markets"
  connector:
    name: "domeapi"
    command: "GetPolymarketMarkets"
  inputs:
    x-api-key: "$MACHINA_CONTEXT_VARIABLE_DOMEAPI_API_KEY"
    query: "NFL"
    limit: 10
```

#### GetPolymarketMarketPrice
Fetches the current or historical market price for a specific market.

**Parameters:**
- `token_id` (string, required): The unique token ID of the market
- `at_time` (integer, optional): Unix timestamp (in seconds) to fetch historical price

**Example:**
```yaml
- type: "connector"
  name: "get-price"
  connector:
    name: "domeapi"
    command: "GetPolymarketMarketPrice"
  inputs:
    x-api-key: "$MACHINA_CONTEXT_VARIABLE_DOMEAPI_API_KEY"
    token_id: "98250445447699368679516529207365255018790721464590833209064266254238063117329"
    at_time: 1762164600
```

#### GetPolymarketOrderbookHistory
Retrieve historical orderbook data.

**Parameters:**
- `token_id` (string, optional): Token ID to filter orderbooks
- `start_time` (integer, optional): Start time for historical data (Unix timestamp)
- `end_time` (integer, optional): End time for historical data (Unix timestamp)

#### GetPolymarketOrderHistory
Retrieve historical order/trade data.

**Parameters:**
- `token_id` (string, optional): Token ID to filter orders
- `start_time` (integer, optional): Start time for historical data
- `end_time` (integer, optional): End time for historical data

#### GetPolymarketCandlesticks
Get candlestick/OHLCV data for market price charts.

**Parameters:**
- `token_id` (string, required): Token ID for the market
- `interval` (string, optional): Candlestick interval (e.g., 1m, 5m, 15m, 1h, 1d) (default: 1h)
- `start_time` (integer, optional): Start time (Unix timestamp)
- `end_time` (integer, optional): End time (Unix timestamp)

**Example:**
```yaml
- type: "connector"
  name: "get-candlesticks"
  connector:
    name: "domeapi"
    command: "GetPolymarketCandlesticks"
  inputs:
    x-api-key: "$MACHINA_CONTEXT_VARIABLE_DOMEAPI_API_KEY"
    token_id: "98250445447699368679516529207365255018790721464590833209064266254238063117329"
    interval: "1h"
```

#### GetPolymarketWalletPnL
Retrieve profit and loss data for a specific wallet address.

**Parameters:**
- `wallet_address` (string, required): Wallet address to query

### Kalshi Endpoints

#### GetKalshiMarkets
Find markets on Kalshi using various filters.

**Parameters:**
- `query` (string, optional): Search query to filter markets
- `limit` (integer, optional): Maximum number of markets (default: 20)

#### GetKalshiOrderbookHistory
Retrieve historical orderbook data for Kalshi markets.

**Parameters:**
- `event_ticker` (string, optional): Event ticker to filter orderbooks
- `start_time` (integer, optional): Start time (Unix timestamp)
- `end_time` (integer, optional): End time (Unix timestamp)

#### GetKalshiOrderHistory
Retrieve historical order data for Kalshi markets.

**Parameters:**
- `event_ticker` (string, optional): Event ticker to filter orders
- `start_time` (integer, optional): Start time (Unix timestamp)

### Matching Markets Endpoints

#### GetMatchingMarketsSports
Get prediction markets across platforms that match the same sporting events.

**Example:**
```yaml
- type: "connector"
  name: "get-matching-sports"
  connector:
    name: "domeapi"
    command: "GetMatchingMarketsSports"
  inputs:
    x-api-key: "$MACHINA_CONTEXT_VARIABLE_DOMEAPI_API_KEY"
```

#### GetSportByDate
Get prediction markets for sports on a specific date.

**Parameters:**
- `date` (string, required): Date in YYYY-MM-DD format

**Example:**
```yaml
- type: "connector"
  name: "get-sports-by-date"
  connector:
    name: "domeapi"
    command: "GetSportByDate"
  inputs:
    x-api-key: "$MACHINA_CONTEXT_VARIABLE_DOMEAPI_API_KEY"
    date: "2025-01-25"
```

## Testing Credentials

After installation, test your API key with:

```python
# 1. Create secret with TEMP_ prefix for testing
mcp__machina_client_dev__create_secrets(
    data={
        "name": "TEMP_CONTEXT_VARIABLE_DOMEAPI_API_KEY",
        "key": "your-api-key-here"
    }
)

# 2. Execute the test workflow
mcp__machina_client_dev__execute_workflow(
    name="domeapi-test-credentials"
)

# 3. Check results - workflow-status should be 'executed'
```

## Complete Workflow Example

```yaml
workflow:
  name: "analyze-nfl-predictions"
  description: "Analyze NFL prediction markets across platforms"
  tasks:
    # Get matching markets for sports
    - type: "connector"
      name: "fetch-sports-markets"
      connector:
        name: "domeapi"
        command: "GetMatchingMarketsSports"
      inputs:
        x-api-key: "$MACHINA_CONTEXT_VARIABLE_DOMEAPI_API_KEY"
      outputs:
        markets: "$.get('markets', {})"
    
    # Search for specific NFL markets on Polymarket
    - type: "connector"
      name: "search-nfl-markets"
      connector:
        name: "domeapi"
        command: "GetPolymarketMarkets"
      inputs:
        x-api-key: "$MACHINA_CONTEXT_VARIABLE_DOMEAPI_API_KEY"
        query: "NFL"
        limit: 50
      outputs:
        nfl_markets: "$.get('markets', [])"
    
    # Get price for a specific market
    - type: "connector"
      name: "get-market-price"
      condition: "len($.get('nfl_markets', [])) > 0"
      connector:
        name: "domeapi"
        command: "GetPolymarketMarketPrice"
      inputs:
        x-api-key: "$MACHINA_CONTEXT_VARIABLE_DOMEAPI_API_KEY"
        token_id: "$.get('nfl_markets')[0].get('token_id')"
      outputs:
        current_price: "$.get('price')"
```

## Resources

- **Documentation**: [https://docs.domeapi.io/](https://docs.domeapi.io/)
- **API Reference**: [https://docs.domeapi.io/api-reference](https://docs.domeapi.io/api-reference)
- **Dashboard**: [https://domeapi.io/dashboard](https://domeapi.io/dashboard)
- **Discord Support**: [Join Discord](https://discord.gg/domeapi)
- **SDKs**: 
  - TypeScript: `npm install @dome-api/sdk`
  - Python: `pip install dome-api-sdk`

## Use Cases

1. **Sports Betting Analytics**: Track prediction markets across platforms for sports events
2. **Market Arbitrage**: Find price discrepancies between Polymarket and Kalshi
3. **Historical Analysis**: Analyze historical price movements and market sentiment
4. **Portfolio Tracking**: Monitor wallet performance and P&L
5. **Market Research**: Study prediction market behavior and patterns

## Notes

- All timestamps are in Unix format (seconds since epoch)
- API responses follow standard REST conventions
- Rate limiting is enforced based on your subscription tier
- Use the test-credentials workflow to verify your API key before production use

