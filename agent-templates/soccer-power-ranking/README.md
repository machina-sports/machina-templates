# Soccer Power Ranking

AI-powered team power ranking system for soccer leagues using statistical performance analysis.

## Architecture

Simple pipeline for team evaluation:

1. **Data Collection**
   - Load team statistics from API Football
   - Aggregate performance metrics (goals, xG, form)
   
2. **Power Ranking Calculation**
   - Statistical modeling of team strength
   - Recent form weighting
   - Head-to-head adjustments

3. **Output**
   - Ranked team list with strength scores
   - Trend indicators (rising/falling)

## Installation

Using MCP to install from local templates:

```python
mcp_machina-client-dev_get_local_template(
    template="agent-templates/soccer-power-ranking",
    project_path="/app/machina-templates/agent-templates/soccer-power-ranking"
)
```

## Setup

After installation, configure leagues:

```python
# Development
mcp_machina-client-dev_executor_workflow_name(
    name="soccer-power-ranking-setup-leagues",
    context={"environment": "dev"}
)
```

## Features

- Multi-league support (EPL, Serie A, Bundesliga, La Liga)
- Statistical team strength modeling
- Dynamic ranking updates
- Performance trend tracking

