# Soccer Kalshi Analyst

AI-powered soccer forecasting agent that generates match predictions using Monte Carlo simulation and identifies tradable edges on Kalshi prediction markets.

## Architecture

Multi-phase pipeline with independent retry capability:

1. **Data Collection** - Event data, team statistics, news intelligence
2. **Feature Engineering** - Aggregate features and evidence
3. **Forecasting** - Multi-analyst pipeline + Monte Carlo simulation
4. **Kalshi Integration** - Market edge detection and trade recommendations

Each phase stores intermediate documents, enabling efficient retries without re-running successful stages.

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

## Quick Start

Execute analysis for a specific fixture:

```python
mcp_machina-client-dev_executor_workflow_name(
    name="soccer-kalshi-analysis-consumer",
    context={"eventCode": "12345678"}
)
```

The agent will automatically chain through all phases. Each workflow can be retried independently if failures occur.

## Features

- Multi-league support (EPL, Serie A, Bundesliga, La Liga, Liga Portugal)
- Statistical xG modeling from historical team performance
- Real-time news intelligence with multilingual queries
- Risk assessment with confidence calibration
- 10,000-iteration Poisson Monte Carlo simulation
- Tier-based Kalshi trading recommendations

