# Market Sector Tips Skill

This skill fetches active sports prediction markets from Polymarket, organizes them by sector (sport type and market type), and uses AI to generate actionable tips for each sector.

## Workflow: `market-sector-tips`

The workflow performs three main steps:
1. **Fetch Markets** — Loads active sports markets from the Polymarket connector.
2. **Group by Sector** — Uses a mapping to organize markets into sectors by sport and market type (moneyline, spreads, totals, props, etc.).
3. **Analyze & Generate Tips** — Sends each sector's data to a Google Gemini prompt that produces ranked tips, opportunity scores, and a summary.

### Inputs

- `tag_id` (number, default: `1`): Polymarket sports tag ID to filter markets.
- `limit` (number, default: `100`): Maximum number of markets to fetch.

**Example:**
```bash
machina workflow run market-sector-tips tag_id=1 limit=50
```

### Outputs

- `sector_tips` (array): List of sector objects, each containing grouped markets and AI-generated tips.
- `sectors_summary` (string): A brief overview of all sectors and top opportunities.
- `workflow-status` (string): `'executed'` if successful, `'skipped'` otherwise.

### Sectors

Markets are grouped by their `sportsMarketType` field into sectors such as:
- **Moneyline** — Winner / loser markets
- **Spreads** — Point spread markets
- **Totals** — Over/under markets
- **Player Props** — Individual player performance markets
- **Other** — Any remaining market types

### Tips Format

Each sector tip includes:
- Sector name and market count
- Top opportunities ranked by estimated value
- Risk level and confidence assessment
- Recommended action (enter, monitor, or pass)
