# Basketball LLM Agent Template (Gemini 3 Pro Preview via google-genai)

## Overview

This template implements a league agnostic basketball forecasting pipeline for any league available in API-Basketball. All intelligence and decision steps are performed by Gemini 3 Pro Preview via the Machina `google-genai` connector.

Python is used only for deterministic work:
- data ingestion, normalization, aggregation
- feature computation
- numerical simulation
- backtesting metrics

Primary outputs per game:
- `P(home_win)`
- `fair_spread_home_minus`
- `fair_total_points`
- `confidence`, `risk_flags`, `abstain`
- compact rationale grounded in evidence when news is used

---

## Connector Standards (Mandatory)

### All LLM reasoning steps

```yaml
connector:
  command: invoke_prompt
  name: google-genai
  model: gemini-3-pro-preview
  location: global
  provider: vertex_ai
````

### All search steps

```yaml
connector:
  name: google-genai
  command: invoke_search
  model: gemini-3-pro-preview
```

---

## Design Principles

1. Evidence first, not vibes

   * Any claim from news must be tied to extracted evidence snippets.
   * If evidence is weak or contradictory, confidence must drop or the agent abstains.

2. Multi step forecasting

   * Separate baseline stats view, evidence adjustments, matchup view, risk control, then final pricing.
   * Python handles numeric mechanics, LLM handles interpretation and parameterization.

3. Uncertainty is a first class output

   * Produce both predictions and uncertainty drivers.
   * Explicit rules convert uncertainty to confidence.

4. League agnostic

   * Same workflow works for NBA, EuroLeague, CBA, domestic leagues, any league in API-Basketball.

---

## Architecture

Core components:

1. Data ingestion (API-Basketball connector)
2. ETL and aggregation (Python)
3. External evidence (Search via google-genai invoke_search)
4. LLM intelligence layer (Gemini 3 Pro Preview via invoke_prompt)
5. Numerical simulation (Python Monte Carlo)
6. Connector APIs for downstream trading agents and UIs
7. Backtesting and calibration loop

---

## Workflow Steps

### 0. League Discovery and Coverage Verification

Goal: confirm the target league has enough coverage.

Endpoints:

* `get-leagues.yml`

Checks:

* `coverage.fixtures.statistics_fixtures == true`
* `coverage.players == true`
* `coverage.standings == true`

If any are false, set `low_data_flag = true` and force conservative confidence downstream.

---

### 1. Game Schedule Build

Endpoint:

* `sync-games.yml`

Python output table: `Games`

* `game_id, league_id, season, timestamp, date`
* `home_team_id, away_team_id`
* `stage, week, status`

---

### 2. Teams and Canonical Naming

Endpoint:

* `sync-teams.yml`

Python output table: `Teams`

* `team_id, canonical_name, country, league_id, season`

Optional LLM step: Team Alias Resolver

```yaml
step: team_alias_resolver
connector:
  command: invoke_prompt
  name: google-genai
  model: gemini-3-pro-preview
  location: global
  provider: vertex_ai
prompt: prompts/team_alias_resolver.yml
inputs:
  league: "{{league_name}}"
  teams_raw: "{{teams_raw_list}}"
outputs_schema: schemas/team_alias_resolver.json
```

---

### 3. Standings and Season Strength Snapshots

Endpoint:

* `sync-standings.yml`

Python derived metrics:

* `win_pct`, `home_win_pct`, `away_win_pct`
* `point_diff`, `home_point_diff`, `away_point_diff`
* `rank`, `games_played`
* `form_last_5_numeric`

Snapshots:

* season start
* mid season
* current

---

### 4. Game Level Team Stats

Endpoint:

* `sync-games-statistics-teams.yml`

Python rollups:

* box score components
* derived:

  * `off_rating, def_rating, net_rating`
  * `pace`
  * `turnover_rate`
  * `rebound_rates`
  * `3p_rate`

---

### 5. Game Level Player Stats (Optional)

Endpoint:

* `sync-games-statistics-players.yml`

Python rollups:

* player season aggregates
* top K player impact summaries

If missing, set `player_depth_flag = false`.

---

### 6. Rolling Form Features

Python windows for last 3, 5, 10 games:

* `win_pct`
* `net_rating`
* `pace`
* `home_away_splits`
* schedule:

  * `days_rest`
  * `back_to_back_flag`

---

## Evidence and News Signals (Search + LLM)

### 7. LLM Query Generator (Per Matchup)

```yaml
step: news_query_generator
connector:
  command: invoke_prompt
  name: google-genai
  model: gemini-3-pro-preview
  location: global
  provider: vertex_ai
prompt: prompts/news_query_generator.yml
inputs:
  league: "{{league_name}}"
  season: "{{season}}"
  matchup: "{{home_team}} vs {{away_team}}"
  game_date: "{{game_date}}"
  recency_days: 3
  max_queries: 8
outputs_schema: schemas/news_queries.json
```

---

### 8. Search Execution

```yaml
step: news_search
connector:
  name: google-genai
  command: invoke_search
  model: gemini-3-pro-preview
inputs:
  queries: "{{news_queries}}"
  recency_days: 3
  language: "{{language_optional}}"
  location: "{{location_optional}}"
outputs_schema: schemas/search_results.json
```

Python filter:

* de duplicate by URL
* enforce recency
* drop irrelevant results

---

### 9. News Evidence Extraction (LLM)

Convert raw search results into structured evidence with explicit confidence.

```yaml
step: news_evidence_extractor
connector:
  command: invoke_prompt
  name: google-genai
  model: gemini-3-pro-preview
  location: global
  provider: vertex_ai
prompt: prompts/news_evidence_extractor.yml
inputs:
  league: "{{league_name}}"
  game_date: "{{game_date}}"
  home_team: "{{home_team}}"
  away_team: "{{away_team}}"
  search_results: "{{filtered_search_results}}"
outputs_schema: schemas/news_evidence.json
```

Expected output schema:

```json
{
  "evidence_items": [
    {
      "type": "injury|rotation|coach|travel|other",
      "team_side": "home|away",
      "entity": "string",
      "claim": "string",
      "confidence": 0.0,
      "support": {
        "source": "string",
        "timestamp": "ISO",
        "quote": "short excerpt"
      }
    }
  ],
  "team_level_deltas": {
    "home_offense_delta": 0.0,
    "home_defense_delta": 0.0,
    "away_offense_delta": 0.0,
    "away_defense_delta": 0.0,
    "pace_delta": 0.0
  },
  "news_reliability": 0.0,
  "missing_info_flags": []
}
```

Python stores:

* `NewsEvidence(game_id, evidence_items...)`
* `NewsDeltas(game_id, deltas..., news_reliability, flags...)`

---

## Feature Payload Construction

### 10. Build Compact Feature Payload (Python)

Python constructs a single canonical payload per game:

```json
{
  "meta": {
    "league": "string",
    "season": "string",
    "game_id": 0,
    "date": "YYYY-MM-DD",
    "low_data_flag": false,
    "player_depth_flag": true
  },
  "home": {
    "team_id": 0,
    "name": "string",
    "season_strength": { "win_pct": 0.0, "net_rating": 0.0, "home_win_pct": 0.0 },
    "rolling_form": { "last_5_net_rating": 0.0, "last_10_win_pct": 0.0, "pace": 0.0 },
    "schedule": { "days_rest": 0, "back_to_back": false }
  },
  "away": { "...": "..." },
  "matchup": {
    "style": {
      "home_3p_rate": 0.0,
      "away_3p_rate": 0.0,
      "rebound_edge_proxy": 0.0,
      "turnover_edge_proxy": 0.0
    }
  },
  "news": {
    "deltas": { "home_offense_delta": 0.0, "home_defense_delta": 0.0, "pace_delta": 0.0 },
    "reliability": 0.0,
    "evidence_count": 0,
    "missing_info_flags": []
  }
}
```

---

## LLM Intelligence Layer (Multi Step)

### 11. Forecast Decomposition (4 roles)

#### 11.1 Stats Analyst

```yaml
step: forecast_stats_analyst
connector:
  command: invoke_prompt
  name: google-genai
  model: gemini-3-pro-preview
  location: global
  provider: vertex_ai
prompt: prompts/forecast_stats_analyst.yml
inputs:
  feature_payload: "{{feature_payload_without_news}}"
outputs_schema: schemas/forecast_component.json
```

#### 11.2 Evidence Analyst

```yaml
step: forecast_evidence_analyst
connector:
  command: invoke_prompt
  name: google-genai
  model: gemini-3-pro-preview
  location: global
  provider: vertex_ai
prompt: prompts/forecast_evidence_analyst.yml
inputs:
  feature_payload: "{{feature_payload}}"
  news_evidence: "{{news_evidence}}"
outputs_schema: schemas/forecast_component.json
```

#### 11.3 Matchup Analyst

```yaml
step: forecast_matchup_analyst
connector:
  command: invoke_prompt
  name: google-genai
  model: gemini-3-pro-preview
  location: global
  provider: vertex_ai
prompt: prompts/forecast_matchup_analyst.yml
inputs:
  feature_payload: "{{feature_payload}}"
outputs_schema: schemas/forecast_component.json
```

#### 11.4 Risk Officer

```yaml
step: forecast_risk_officer
connector:
  command: invoke_prompt
  name: google-genai
  model: gemini-3-pro-preview
  location: global
  provider: vertex_ai
prompt: prompts/forecast_risk_officer.yml
inputs:
  components:
    stats: "{{stats_component}}"
    evidence: "{{evidence_component}}"
    matchup: "{{matchup_component}}"
  feature_payload: "{{feature_payload}}"
outputs_schema: schemas/risk_component.json
```

---

### 12. Parameterized Simulation Spec (LLM)

LLM outputs a simulation parameter spec. Python uses it to run Monte Carlo.

```yaml
step: simulation_parameterizer
connector:
  command: invoke_prompt
  name: google-genai
  model: gemini-3-pro-preview
  location: global
  provider: vertex_ai
prompt: prompts/simulation_parameterizer.yml
inputs:
  feature_payload: "{{feature_payload}}"
  components:
    stats: "{{stats_component}}"
    evidence: "{{evidence_component}}"
    matchup: "{{matchup_component}}"
  risk: "{{risk_component}}"
outputs_schema: schemas/sim_params.json
```

Output schema:

```json
{
  "latent_parameters": {
    "pace_mean": 0.0,
    "pace_sd": 0.0,
    "home_off_eff_mean": 0.0,
    "home_off_eff_sd": 0.0,
    "away_off_eff_mean": 0.0,
    "away_off_eff_sd": 0.0,
    "injury_variance_multiplier": 1.0
  },
  "correlations": {
    "pace_off_eff_corr": 0.0
  },
  "notes": []
}
```

---

### 13. Monte Carlo Simulation (Python)

Python runs N sims (configurable) and stores:

* `P(home_win)`
* spread and total distributions
* quantiles

Store:

* `SimResults(game_id, win_prob, spread_q50, total_q50, spread_q10_q90, total_q10_q90, ...)`

---

### 14. Final Pricing and Output Assembly (LLM)

Gemini assembles the final output combining all components and simulation results.

```yaml
step: final_pricing
connector:
  command: invoke_prompt
  name: google-genai
  model: gemini-3-pro-preview
  location: global
  provider: vertex_ai
prompt: prompts/final_pricing.yml
inputs:
  feature_payload: "{{feature_payload}}"
  components:
    stats: "{{stats_component}}"
    evidence: "{{evidence_component}}"
    matchup: "{{matchup_component}}"
    risk: "{{risk_component}}"
  sim_results: "{{sim_results}}"
  calibration_hints: "{{optional_calibration_hints}}"
outputs_schema: schemas/final_prediction.json
```

Final output schema:

```json
{
  "home_win_probability": 0.0,
  "away_win_probability": 0.0,
  "fair_spread_home_minus": 0.0,
  "fair_total_points": 0.0,
  "confidence": 0.0,
  "risk_flags": [],
  "abstain": false,
  "rationale_compact": [
    { "driver": "rolling_net_rating", "effect": "home_up", "magnitude": "medium" },
    { "driver": "injury_evidence", "effect": "home_down", "magnitude": "small", "support_quote": "short excerpt" }
  ]
}
```

Hard rules:

* probabilities sum to 1.0
* if `news.reliability` is low, `confidence` must be capped
* if uncertainty bands are too wide, `abstain` should flip true unless edge threshold is exceptional

---

## Backtesting and Calibration

### 15. Backtest Runner (Python)

For each historical game:

* rebuild the feature payload as it existed pre tipoff
* run the full workflow
* compute:

  * Brier score
  * log loss
  * calibration buckets
  * spread and total error
  * abstain rate

### 16. Calibration Report and Prompt Deltas (LLM)

Gemini reviews metrics and proposes prompt deltas and feature additions.

```yaml
step: calibration_report
connector:
  command: invoke_prompt
  name: google-genai
  model: gemini-3-pro-preview
  location: global
  provider: vertex_ai
prompt: prompts/calibration_report.yml
inputs:
  league: "{{league_name}}"
  season: "{{season}}"
  metrics: "{{backtest_metrics}}"
  prompt_hashes: "{{prompt_hashes_in_use}}"
outputs_schema: schemas/calibration_deltas.json
```

---

## Connector APIs (Machina)

### `basketball_feature_connector`

* `build_feature_payload(game_id) -> JSON`
* `get_team_profile(team_id, season) -> JSON`

### `basketball_news_connector`

* `generate_news_queries(game_id) -> list[string]`
* `search_news(queries) -> search_results`
* `extract_news_evidence(game_id, search_results) -> NewsEvidence + NewsDeltas`

### `basketball_forecast_connector`

* `forecast_game(game_id) -> FinalPrediction JSON`
* `forecast_games(batch_game_ids) -> list[FinalPrediction]`

### `basketball_backtest_connector`

* `run_backtest(league_id, season, date_range) -> metrics`
* `generate_calibration_deltas(metrics) -> prompt_change_proposal`

---

## Observability and Guardrails

Log per game:

* feature payload hash
* prompt hashes
* evidence sources used
* simulation parameters
* final prediction with schema validation result

Guardrails:

* if `news_reliability < threshold`, cap confidence
* if `low_data_flag == true`, increase variance and encourage abstain
* if spread or total uncertainty band is too wide, raise risk flags
* strict JSON schema enforcement for every LLM step

---

## Template Structure

```text
basketball-llm-agent/
├── _install.yml
├── _folders.yml
├── workflows/
│   ├── league-discovery.yml
│   ├── data-ingestion.yml
│   ├── feature-aggregation.yml
│   ├── news-queries.yml
│   ├── news-search.yml
│   ├── news-evidence-extraction.yml
│   ├── forecast-stats-analyst.yml
│   ├── forecast-evidence-analyst.yml
│   ├── forecast-matchup-analyst.yml
│   ├── forecast-risk-officer.yml
│   ├── simulation-parameterizer.yml
│   ├── python-monte-carlo.yml
│   ├── final-pricing.yml
│   ├── backtest-runner.yml
│   └── calibration-report.yml
├── scripts/
│   ├── etl_games.py
│   ├── etl_teams.py
│   ├── etl_standings.py
│   ├── aggregate_features.py
│   ├── monte_carlo.py
│   ├── backtest.py
│   └── metrics.py
├── prompts/
│   ├── team_alias_resolver.yml
│   ├── news_query_generator.yml
│   ├── news_evidence_extractor.yml
│   ├── forecast_stats_analyst.yml
│   ├── forecast_evidence_analyst.yml
│   ├── forecast_matchup_analyst.yml
│   ├── forecast_risk_officer.yml
│   ├── simulation_parameterizer.yml
│   ├── final_pricing.yml
│   └── calibration_report.yml
└── README.md
```

---

## Dependencies

Python:

* pandas
* numpy
* requests
* python-dotenv

Connectors:

* api-basketball.yml
* google-genai invoke_search
* google-genai invoke_prompt (Vertex AI, Gemini 3 Pro Preview)

No classical ML libraries required.

