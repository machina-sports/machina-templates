# Soccer Kalshi Analyst

AI-powered soccer forecasting agent that generates match predictions using Monte Carlo simulation and identifies tradable edges on Kalshi prediction markets.

## Architecture

Multi-phase pipeline with independent retry capability:

1. **Data Collection** (`collect-match-data`)
   - Load event data from API Football
   - Fetch team statistics (form, goals, lineups)
   - Generate multilingual news queries
   - Extract injury/tactical evidence
   - **Output:** `soccer-match-data` document

2. **Feature Engineering** (`aggregate-match-features`)
   - Aggregate statistical features
   - Structure news evidence with impact scores
   - Calculate team-level deltas
   - **Output:** `soccer-match-features` document

3. **Forecasting** (5-stage granular pipeline for parallel execution)
   - **3A. Statistical Analyst** (`forecast-stats`) ~45s
     - Baseline xG from historical team performance
     - **Output:** `soccer-stats-analysis` document
   
   - **3B. Evidence Analyst** (`forecast-evidence`) ~39s
     - News-adjusted xG incorporating injury/tactical evidence
     - **Output:** `soccer-evidence-analysis` document
   
   - **3C. Matchup Analyst** (`forecast-matchup`) ~29s
     - Tactical matchup analysis and xG multipliers
     - **Output:** `soccer-matchup-analysis` document
   
   - **3D. Risk Officer** (`forecast-risk`) ~25s
     - Confidence calibration and abstention logic
     - **Output:** `soccer-analyst-report` document
   
   - **3E. Simulation & Pricing** (`forecast-simulation`) ~30s
     - Simulation Parameterizer: Convert analysis to λ parameters
     - Monte Carlo: 10,000-iteration Poisson simulation
     - Final Pricing: Calibrated probability distribution
     - **Output:** `soccer-prediction` document

4. **Kalshi Integration** (`analyze-kalshi-markets`)
   - Match prediction to Kalshi markets
   - Calculate expected value vs market prices
   - Generate tier-based trade recommendations
   - **Output:** `soccer-kalshi-analysis` document

Each phase stores intermediate documents, enabling efficient retries and analysis reuse without re-running successful stages.

## Installation

Using MCP to install from local templates:

```python
mcp_machina-client-dev_get_local_template(
    template="agent-templates/soccer-kalshi-analyst",
    project_path="/app/machina-templates/agent-templates/soccer-kalshi-analyst"
)
```

Using MCP to install from git:

```python
mcp_machina-client-dev_import_templates_from_git(
    repositories=[{
        "repo_url": "your-repo-url",
        "template": "agent-templates/soccer-kalshi-analyst",
        "repo_branch": "main"
    }]
)
```

## Features

### Data & Intelligence
- Multi-league support (EPL, Serie A, Bundesliga, La Liga, Liga Portugal)
- Statistical xG modeling from historical team performance
- Real-time news intelligence with multilingual query generation
- Quantified evidence extraction (injuries, tactics, motivation)

### Analysis & Forecasting
- **Granular 4-analyst pipeline** for parallel execution
  - Statistical Analyst (~45s): Baseline xG
  - Evidence Analyst (~39s): News-adjusted xG
  - Matchup Analyst (~29s): Tactical adjustments
  - Risk Officer (~25s): Confidence & abstention
- High-fidelity 10,000-iteration Poisson Monte Carlo simulation
- Full analytical audit trail with intermediate documents

### Trading Integration
- Kalshi market edge detection
- Expected value calculation vs market prices
- Tier-based trading recommendations (Tier 1-3)

### Performance & Reliability
- **8 independent workflows** for maximum granularity
- Intermediate document storage after each analyst
- Individual analyst execution (~25-45s each)
- Total pipeline: ~3 min (with retry capability at any stage)
- Rich metadata for querying and filtering

## MCP usage patterns (general)

This section documents the **reliable patterns** we used to interact with Machina MCP for:
- **Searching documents** (filters + sorters + schema discovery)
- **Finding `sport:Event` fixtures** (Premier League / EPL)
- **Executing agents** in batch and capturing `agents/execution/<id>` without repeating common errors

### Simulation (MCP)

See `simulation/README.md` for ready-to-copy MCP queries (ex: EPL 2025 events in chronological order where `forecasted != true`, using `page_size: 3` so you can keep increasing `page` to process more).

### 1) Start by inspecting the data shape

When a filter returns 0 results, it’s often because the field lives under `value` (not `metadata`) or uses namespaced keys like `schema:startDate`.

- **Pattern**: fetch a small sample with minimal filters, then adjust the query based on real keys.

Example (get a few `sport:Event` docs sorted by kickoff time):

```python
mcp_machina-client-dev_search_documents(
  page=1,
  page_size=5,
  filters={"name": "sport:Event"},
  sorters=["value.schema:startDate", 1],
)
```

### 2) Document search: filters + sorters

#### Filters
MCP supports MongoDB-style filters.

- **Exact match**:

```python
filters={"name": "sport:Event"}
```

- **Regex match**:

```python
filters={"name": {"$regex": "Premier League|EPL", "$options": "i"}}
```

- **Nested keys**: use dot-notation, even when keys contain `:` or `@id`.

Example (EPL fixtures): the league ID is under `value["sport:competition"]["@id"]`.

```python
filters={
  "name": "sport:Event",
  "value.sport:competition.@id": "urn:apifootball:league:39",
}
```

#### Sorters
Sorters use the same dot-path strings.

- **Ascending**:

```python
sorters=["value.schema:startDate", 1]
```

- **Descending**:

```python
sorters=["value.schema:startDate", -1]
```

Notes:
- Server-side limits may apply to `page_size` (some deployments cap at 100 even if the MCP helper defaults higher).
- Prefer narrow filters + sorters over fetching many pages.

### 3) Reliable EPL “Round 1” retrieval strategy

Not every dataset stores an explicit “round” field. The robust approach is:
- Filter EPL by league id (`urn:apifootball:league:39`)
- Sort by `value.schema:startDate`
- Take the earliest N fixtures (for EPL Round 1, typically N=10)

```python
mcp_machina-client-dev_search_documents(
  page=1,
  page_size=25,
  filters={
    "name": "sport:Event",
    "value.sport:competition.@id": "urn:apifootball:league:39",
  },
  sorters=["value.schema:startDate", 1],
)
```

### 4) Executing an agent: required `messages` + context

Even if your agent primarily uses `context-agent`, the **execute** endpoint expects a `messages` array.

- **Pattern**: pass `eventCode` in `context`, and include a minimal user message.

```python
mcp_machina-client-dev_execute_agent(
  agent_id="<soccer-kalshi-analyst agent_id>",
  context={"eventCode": "urn:apifootball:sport_event:1378969"},
  messages=[{"role": "user", "content": "Run soccer-kalshi-analyst for eventCode=urn:apifootball:sport_event:1378969"}],
)
```

### 5) Batch execution without losing the execution IDs

In some deployments, `execute_agent` can return an unhelpful response (e.g., `status: "error"` with an empty message) **even though the execution is created**.

Use this safe pattern:
- Call `execute_agent(...)`
- Immediately call `search_agent_executions` sorted by `date` desc
- Take the most recent `_id` as the execution reference

```python
# 1) Fire-and-forget
mcp_machina-client-dev_execute_agent(
  agent_id="<agent_id>",
  context={"eventCode": "<eventCode>"},
  messages=[{"role": "user", "content": f"Run soccer-kalshi-analyst for eventCode={eventCode}"}],
)

# 2) Confirm + capture execution id
latest = mcp_machina-client-dev_search_agent_executions(
  page=1,
  page_size=1,
  filters={"name": "soccer-kalshi-analyst"},
  sorters=["date", -1],
)

execution_id = latest["data"][0]["_id"]  # => agents/execution/<execution_id>
```

Practical tips:
- If multiple executions are being scheduled concurrently, run sequentially (enqueue 1 → capture `_id` → enqueue next) to avoid ambiguous “latest execution” mapping.
- For progress, poll `search_agent_executions` by `_id` and track `status` (`agent-scheduled`, `agent-executing`, `agent-executed`).


