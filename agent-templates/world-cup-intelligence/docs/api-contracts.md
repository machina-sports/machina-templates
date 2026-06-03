# World Cup Intelligence API Contracts

MCP/public gateway routes should call only allowlisted workflows from this template. Do not expose raw workflow or connector execution.

Launch workflow set:

- `worldcup-search-markets`
- `worldcup-get-event-context`
- `worldcup-get-iptc-event-context`
- `worldcup-compare-market-sources`
- `worldcup-find-market-edges`
- `worldcup-generate-market-brief`
- `worldcup-fan-sentiment-context`

All market-edge/arbitrage outputs are informational analysis only. Execution, betting placement, trading, and portfolio actions are out of scope.
