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

