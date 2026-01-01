# Soccer Power Ranking

AI-powered team power ranking system for soccer leagues using statistical performance analysis and dynamic league configuration.

## Architecture

Automated pipeline for team evaluation across multiple leagues:

### 1. **League Configuration**
   - Centralized league setup in `setup-leagues.yml`
   - Enable/disable leagues dynamically
   - Environment-specific configs (dev/prod)
   
### 2. **Data Collection** 
   - Load enabled leagues from configuration document
   - Fetch all teams per league via API Football
   - Collect comprehensive team statistics for each team
   - Aggregate performance metrics (goals, xG, possession, form)
   
### 3. **Power Ranking Calculation**
   - Statistical modeling of team strength across leagues
   - Recent form weighting and momentum analysis
   - Head-to-head adjustments
   - Cross-league normalization

### 4. **Output**
   - Ranked team list with strength scores per league
   - Trend indicators (rising/falling)
   - Performance comparison metrics

## Workflows

- **`load-power-ranking-leagues-config`**: Load and filter enabled leagues from configuration
- **`get-league-teams`**: Fetch all teams from a specific league via API Football
- **`update-team-stats`**: Update statistics for all teams across all enabled leagues
- **`calculate-power-rankings`**: Calculate power rankings based on collected statistics
- **`setup-leagues`**: Configure leagues for dev/prod environments

## Installation

Install from local templates using MCP:

```python
mcp_machina-client-dev_get_local_template(
    template="agent-templates/soccer-power-ranking",
    project_path="/app/machina-templates/agent-templates/soccer-power-ranking"
)
```

## Setup

### 1. Configure Leagues

After installation, run the setup workflow to create the league configuration:

```python
# Development environment
mcp_machina-client-dev_executor_workflow_name(
    name="soccer-power-ranking-setup-leagues",
    context={"environment": "dev"}
)

# Production environment
mcp_machina-client-dev_executor_workflow_name(
    name="soccer-power-ranking-setup-leagues",
    context={"environment": "prd"}
)
```

This creates a `power-ranking-leagues-config` document with enabled leagues.

### 2. Add/Remove Leagues

Edit `configs/setup-leagues.yml` to modify the leagues list:

```yaml
leagues: [
  {
    "league_id": "71",
    "league_name": "Brasileirão",
    "title": "Brazilian Brasileirão",
    "season": "2025",
    "enabled": true
  },
  {
    "league_id": "39",
    "league_name": "EPL",
    "title": "English Premier League",
    "season": "2025",
    "enabled": true
  }
]
```

Re-run the setup workflow to apply changes.

### 3. Update Team Statistics

Collect team statistics for all enabled leagues:

```python
mcp_machina-client-dev_executor_workflow_name(
    name="soccer-power-ranking-update-stats",
    context={"environment": "dev"}
)
```

This workflow:
- Loads enabled leagues from configuration
- Fetches teams for each league
- Collects statistics for each team
- Persists data in `team-statistics` documents

### 4. Calculate Power Rankings

Generate power rankings based on collected statistics:

```python
mcp_machina-client-dev_executor_workflow_name(
    name="soccer-power-ranking-calculate-rankings"
)
```

## Power Ranking Methodology

The power ranking system calculates a single **Power Score** (0-1) for each team based on 4 pillars of performance:

### 📊 Scoring Formula

```
Power Score = 40% × Outcome + 25% × Attack + 25% × Defense + 10% × Discipline
```

Each pillar is normalized to a 0-1 scale using **Min-Max normalization** across all teams in the league, ensuring fair comparison regardless of league characteristics.

---

### 1️⃣ Outcome Score (40%) - Winning Capability

Measures the team's ability to win matches and accumulate points.

**Formula:**
```python
win_rate = wins / games
points_per_game = (wins × 3 + draws) / games
outcome_score = 0.6 × win_rate + 0.4 × (points_per_game / 3)
```

**Components:**
- **Win Rate** (60%): Direct measure of victories
- **Points Per Game** (40%): Accounts for draws (normalized by dividing by 3, the max PPG)

**Example (Flamengo):**
- 23 wins, 10 draws in 38 games
- Win rate: 23/38 = 0.605
- PPG: (23×3 + 10)/38 = 2.08
- Outcome score: 0.6 × 0.605 + 0.4 × (2.08/3) = **0.6404**

---

### 2️⃣ Attack Score (25%) - Offensive Power

Measures goal-scoring ability and consistency.

**Formula:**
```python
goals_per_game = goals_for / games
scoring_rate = 1 - (failed_to_score / games)
attack_score = 0.7 × normalize(goals_per_game) + 0.3 × scoring_rate
```

**Components:**
- **Goals Per Game** (70%): Normalized volume of goals scored
- **Scoring Rate** (30%): Consistency (% of games where team scored)

**Why not 1.0?** Even the best attacking team needs to score in EVERY game AND have the highest GPG to reach 1.0.

**Example (Flamengo):**
- 78 goals in 38 games = 2.05 GPG (best in league → normalized = 1.0)
- Failed to score in 6 games → scoring rate = 1 - (6/38) = 0.842
- Attack score: 0.7 × 1.0 + 0.3 × 0.842 = **0.9526**

---

### 3️⃣ Defense Score (25%) - Defensive Solidity

Measures ability to prevent goals and keep clean sheets.

**Formula:**
```python
concede_rate = goals_against / games
clean_sheet_rate = clean_sheets / games
defense_score = 0.6 × (1 - normalize(concede_rate)) + 0.4 × clean_sheet_rate
```

**Components:**
- **Concede Rate** (60%): Normalized goals conceded (inverted: less = better)
- **Clean Sheet Rate** (40%): % of games without conceding

**Example (Flamengo):**
- 27 goals conceded in 38 games = 0.71 GPG (best → normalized = 0, inverted = 1.0)
- 18 clean sheets → rate = 18/38 = 0.474
- Defense score: 0.6 × 1.0 + 0.4 × 0.474 = **0.7895**

---

### 4️⃣ Discipline Score (10%) - Card Management

Measures team discipline and control.

**Formula:**
```python
cards_per_game = (yellow_cards + red_cards × 2) / games
discipline_score = 1 - normalize(cards_per_game)
```

**Components:**
- **Cards Per Game**: Red cards weighted 2× (more severe)
- **Normalized and inverted**: Fewer cards = better discipline

**Why can this reach 1.0?** Unlike attack/defense, discipline is a single metric. The team with the LOWEST cards_per_game gets 1.0.

**Example (Fluminense):**
- 77 yellows + 3 reds = (77 + 3×2)/38 = 2.18 cards/game
- **Lowest in the league** → normalized = 0 → score = **1.0000** ✅

---

## 📈 Interpreting Scores

### Score Ranges

| Range | Interpretation |
|-------|----------------|
| **0.70 - 1.00** | Elite tier - Championship contenders |
| **0.55 - 0.69** | Strong tier - Top 6 quality |
| **0.40 - 0.54** | Mid-table - Solid but not elite |
| **0.25 - 0.39** | Lower tier - Struggling teams |
| **0.00 - 0.24** | Relegation zone - Critical issues |

### Pillar Insights

- **High Outcome, Low Attack**: Defensive/counter-attacking team (efficient but not flashy)
- **High Attack, Low Defense**: Entertaining but vulnerable team
- **High Discipline**: Tactical, controlled play style
- **Low Discipline**: Aggressive, confrontational approach

---

## 🎯 Example: Brasileirão 2025 Top 3

### 1. Flamengo (0.7777) - Dominant All-Rounder
- 🏆 **Outcome**: 0.6404 (23 wins - joint best)
- ⚽ **Attack**: 0.9526 (78 goals - best in league)
- 🛡️ **Defense**: 0.7895 (27 conceded - best in league)
- 🟨 **Discipline**: 0.8605 (good control)
- **Profile**: Complete team, strongest in all areas

### 2. Palmeiras (0.7102) - Balanced Excellence
- 🏆 **Outcome**: 0.6298 (23 wins - joint best)
- ⚽ **Attack**: 0.7688 (66 goals)
- 🛡️ **Defense**: 0.6829 (33 conceded)
- 🟨 **Discipline**: 0.9535 (excellent - 2.24 cards/game)
- **Profile**: Well-rounded, very disciplined

### 3. Mirassol (0.6232) - Surprise Performer
- 🏆 **Outcome**: 0.5193 (18 wins)
- ⚽ **Attack**: 0.7426 (63 goals - 3rd best)
- 🛡️ **Defense**: 0.5658 (39 conceded)
- 🟨 **Discipline**: 0.8837 (good)
- **Profile**: Strong attack carrying the team

---

## ❓ FAQs

### Why doesn't the best team always score 1.0 in each pillar?

**Attack & Defense** use multiple metrics:
- You need to be #1 in BOTH volume AND consistency
- Example: Best attack still needs to score in every single game for 1.0

**Outcome** combines wins and points:
- Even undefeated teams might draw games, reducing the score

**Discipline** is the only pillar that CAN reach 1.0:
- Single metric (cards/game)
- Lowest value = 1.0

### How does normalization work?

**Min-Max Normalization:**
```python
normalized_value = (value - min_value) / (max_value - min_value)
```

This puts all teams on a 0-1 scale:
- **Best team** (min or max depending on metric) = 1.0
- **Worst team** = 0.0
- **Others** = proportional between 0 and 1

### Can scores change between calculations?

**Yes!** Scores are relative to the league:
- If a strong team joins, all other scores may decrease
- If teams improve/decline, relative positions shift
- Normalization ensures fair comparison within each league

---

## Features

✅ **4-Pillar scoring system** - Outcome (40%), Attack (25%), Defense (25%), Discipline (10%)  
✅ **Min-Max normalization** - Fair comparison across different league styles  
✅ **Transparent breakdowns** - See exact contribution of each pillar  
✅ **Dynamic league configuration** - Add/remove leagues without modifying workflows  
✅ **Multi-league support** - Brasileirão, EPL, Serie A, Bundesliga, La Liga, and more  
✅ **Automated data collection** - Fetch teams and stats for all enabled leagues  
✅ **Real-time recalculation** - Rankings update with latest statistics  
✅ **Detailed metrics export** - Full breakdown for analysis and debugging  

## Configuration

Current default configuration focuses on **Brasileirão (Brazilian Serie A)**:

- **League ID**: 71
- **Season**: 2025
- **Data Source**: API Football

To add more leagues, simply edit `configs/setup-leagues.yml` and re-run the setup workflow.

---

## 🚀 Quick Start Example

### Complete Workflow

```python
# 1. Install template
mcp_machina-client-dev_get_local_template(
    template="agent-templates/soccer-power-ranking",
    project_path="/app/machina-templates/agent-templates/soccer-power-ranking"
)

# 2. Setup league configuration
mcp_machina-client-dev_executor_workflow_name(
    name="soccer-power-ranking-setup-leagues",
    context={"environment": "dev"}
)

# 3. Collect team statistics (run collector agent)
mcp_machina-client-dev_execute_agent(
    agent_id="soccer-power-ranking-collector",
    messages=[]
)

# 4. Calculate power rankings
mcp_machina-client-dev_executor_workflow_name(
    name="soccer-power-ranking-calculate-rankings",
    context={"league_id": "71", "season": "2025"}
)
```

### Expected Output Structure

```json
{
  "rankings": [
    {
      "rank": 1,
      "team_id": "127",
      "team_name": "Flamengo",
      "power_score": 0.7777,
      "breakdown": {
        "outcome_score": 0.6404,
        "attack_score": 0.9526,
        "defense_score": 0.7895,
        "discipline_score": 0.8605
      },
      "metrics": {
        "games": 38,
        "wins": 23,
        "draws": 10,
        "win_rate": 0.6053,
        "points_per_game": 2.08,
        "goals_per_game": 2.05,
        "concede_rate": 0.71,
        "clean_sheets": 18,
        "clean_sheet_rate": 0.4737,
        "failed_to_score": 6,
        "scoring_rate": 0.8421,
        "cards_per_game": 2.34,
        "yellow_cards": 79,
        "red_cards": 5
      }
    }
  ],
  "league_stats": {
    "total_teams": 20,
    "avg_power_score": 0.4513,
    "league_id": "71",
    "season": "2025"
  }
}
```

---

## 📚 Use Cases

### 1. Pre-Match Analysis
Compare two teams' power scores and pillar breakdowns to predict match dynamics:
```
Team A: High attack (0.85), Low defense (0.40) → Expect goals
Team B: Low attack (0.35), High defense (0.75) → Defensive approach
→ Prediction: High-scoring game favoring Team A
```

### 2. Transfer Strategy
Identify teams punching above/below their weight:
```
High outcome, Low pillars → Overperforming (luck factor?)
Low outcome, High pillars → Underperforming (tactical issues?)
```

### 3. League Monitoring
Track power score trends over time:
- Rising scores → Improving form
- Falling scores → Performance decline
- Use for early warning of relegation risk

### 4. Cross-League Comparison
Compare average power scores across leagues:
```
League A avg: 0.52 → More competitive (tight scores)
League B avg: 0.45 → One or two dominant teams
```

---

## 🔧 Advanced Configuration

### Custom Weights

Edit `scripts/power_ranking_calculator.py` to adjust pillar weights:

```python
# Default weights
power_score = (
    0.40 * outcome_score +    # Winning capability
    0.25 * attack_score +     # Offensive power
    0.25 * defense_score +    # Defensive solidity
    0.10 * discipline_score   # Card management
)

# Example: Defensive-focused variant
power_score = (
    0.35 * outcome_score +
    0.20 * attack_score +
    0.35 * defense_score +    # Increased weight
    0.10 * discipline_score
)
```

### Multiple Seasons

Compare same league across seasons:
```python
# Season 2024
mcp_machina-client-dev_executor_workflow_name(
    name="soccer-power-ranking-calculate-rankings",
    context={"league_id": "71", "season": "2024"}
)

# Season 2025
mcp_machina-client-dev_executor_workflow_name(
    name="soccer-power-ranking-calculate-rankings",
    context={"league_id": "71", "season": "2025"}
)
```

---

## 📊 Data Sources

All statistics sourced from **API Football**:
- Team fixtures and results
- Goals scored/conceded
- Clean sheets and failed to score
- Yellow and red cards
- Updated in real-time via `update-team-stats` workflow

