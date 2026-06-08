# World Cup 2026 Intelligence Skill

This skill organizes and packages the real-time predictive analytics, market data aggregation, and social sentiment indexing capabilities of the FIFA World Cup 2026 pod into a cohesive, SDK-discoverable, and Studio-renderable capability.

## Overview

The `world-cup-intelligence` skill wraps low-level background workflows (ingestion, identity crosswalking, Dixon-Coles model solving) into high-level, client-facing methods exposed via the `@machina-sports/sdk` or the Machina Studio UI.

By bundling these workflows under a unified manifest, we provide Studio operators with real-time "hot cards" (such as Market Watch and Fan Pulse) and conversational agents with verified data retrieval primitives.

---

## Bundled Workflows

This skill exposes three primary executable workflows.

### 1. `worldcup-market-watch`

Generates a tournament-wide, composite market intelligence card showing odds movers, price spreads, and candidate arbitrage edges.

*   **Runtime Semantics:** Serves a cached card unless `force_regen` is true or the cache is older than 20 minutes (TTL).
*   **Inputs:**
    *   `force_regen` (boolean, optional): Forces re-execution of the aggregation connectors and Gemini-based summary authoring.
*   **Outputs:**
    *   `skill_card` (object): A structured JSON object containing compiled tournament-wide statistics, top movers, and anomalies.
    *   `served_from` (string): Either `'cache'` or `'generated'`.

### 2. `worldcup-fan-pulse`

Extracts real-time public sentiment, trending news storylines, and fan pulse for either a specific fixture or the tournament globally.

*   **Runtime Semantics:** Relies on xAI Grok search to query the live Web/X index, summarizing results into a structured card. Cache TTL is 1 hour.
*   **Inputs:**
    *   `event_urn` (string, optional): The canonical Machina URN of the event (e.g., `urn:machina:sport:soccer:event:scotland-vs-morocco:20260619:wor`). If omitted, generates a global tournament pulse.
    *   `query` (string, optional): Custom search parameters. Defaults to `"FIFA World Cup 2026"`.
*   **Outputs:**
    *   `skill_card` (object): The structured pulse card containing sentiment dials, key themes, and source attribution links.
    *   `served_from` (string): Either `'cache'` or `'generated'`.

### 3. `worldcup-get-signal`

Fuses our proprietary Dixon-Coles mathematical model's probabilities with the best real-time market prices across Kalshi and Polymarket.

*   **Runtime Semantics:** Strictly read-only, informational decision support. Evaluates the model-implied probabilities against the line-shopped price per 1X2 outcome, outputting edge, EV, and Kelly recommendations.
*   **Inputs:**
    *   `event_urn` (string, required): The target fixture's URN (e.g., `urn:machina:sport:soccer:event:scotland-vs-morocco:20260619:wor`).
    *   `bankroll` (string, optional): Simulated bankroll size; when supplied, each leg also returns a `stake_amount`.
    *   `kelly_fraction` (number, optional): Kelly criterion scaling factor. Defaults to `0.25` (quarter-Kelly).
    *   `min_edge_bps` (number, optional): Minimum net edge (basis points) for a leg to be flagged as value. Defaults to `200` (2%).
    *   `fee_bps` (number, optional): Venue fee/slippage in basis points; edge, EV, and Kelly are computed net of it. Defaults to `0`.
*   **Outputs:**
    *   `signal` (object): Per outcome — `model_prob`, fair odds (`fair_decimal`/`fair_american`), `best_price`+`best_venue`, `edge`/`edge_pct`, `ev_per_dollar`, `kelly_full`+`kelly_stake`, `confidence_tier`, and `risk_flags`.
    *   `recommendation` (string): Standardized plain-text directive — e.g. `"No actionable edge -- model and market broadly agree; pass."` or `"Value: back Draw at kalshi @0.28 -- model 35% vs market 28%, edge 7.1%, suggested stake 2.46% of bankroll (quarter-Kelly). Model confidence: low."`
    *   `top_pick` (object): The single highest-EV value leg (suppressed when flagged `edge_likely_model_noise`).

---

## Setup & Execution

### SDK Integration

To call these capabilities programmatically inside a fan app or service:

```typescript
import { MachinaClient } from "@machina-sports/sdk";

const sdk = new MachinaClient({ token: process.env.MACHINA_API_TOKEN });

// Retrieve the hot tournament-wide market watch card
const watchCard = await sdk.skills.run("world-cup-intelligence", "worldcup-market-watch");
console.log(watchCard.skill_card.title); // "World Cup Market Watch"
```

### CLI Execution

You can run these workflows directly via the Machina CLI:

```bash
# Force-regenerate the tournament market watch card
machina workflow run worldcup-market-watch force_regen=true

# Get betting signal for a specific match
machina workflow run worldcup-get-signal event_urn="urn:machina:sport:soccer:event:scotland-vs-morocco:20260619:wor"
```

---

## Architectural Separation of Duties

To maintain long-term reliability and isolation, the World Cup Pod separates duties into three strict layers:

```
┌────────────────────────────────────────────────────────┐
│                      AGENTS LAYER                      │
│     (Reasoning loops: Copilots, Cron Publishers)        │
└───────────────────────────┬────────────────────────────┘
                            │ (chooses / orchestrates)
                            ▼
┌────────────────────────────────────────────────────────┐
│                      SKILLS LAYER                      │
│        (Discovered capability package: skill.yml)       │
└───────────────────────────┬────────────────────────────┘
                            │ (invokes)
                            ▼
┌────────────────────────────────────────────────────────┐
│                    WORKFLOWS LAYER                     │
│    (programmatic pipelines, model-solvers, ingestion)  │
└────────────────────────────────────────────────────────┘
```

1.  **Workflows (programmatic DAGs):** Own raw data movement, calculations, and database state modifications (e.g., `worldcup-ingest-fixtures`, `worldcup-sync-model-forecasts`).
2.  **Skills (reusable packages):** Bind specific workflows with human-readable guidelines, strict schemas, and UI elements. They are product-facing.
3.  **Agents (guided personas):** Are non-deterministic reasoning loops that use Skills as tools to fulfill conversational goals.
