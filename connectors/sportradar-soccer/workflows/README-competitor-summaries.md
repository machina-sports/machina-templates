# Sportradar Soccer - Competitor Summaries Sync

## Overview

The `sync-competitor-summaries` workflow synchronizes competitor (team) summaries from the Sportradar Soccer API into the Machina platform as `competitor:Summarie` documents. This workflow is automatically invoked as part of the `sportradar-soccer-config-seasons` agent execution, ensuring competitor data is refreshed whenever season configuration runs.

## Workflow: `sportradar-soccer-sync-competitor-summaries`

### Purpose
Fetches detailed competitor summaries from Sportradar's `/competitors/{competitor_id}/summaries.json` endpoint and persists them as searchable documents with the metadata tag `competitor:Summarie`.

### Input Parameters
- `competitor_ids` (array): List of Sportradar competitor IDs (e.g., `["sr:competitor:44", "sr:competitor:45"]`)

### Output
- `competitor_summaries`: Array of competitor summary data
- `workflow-status`: Execution status (`'executed'` or `'skipped'`)

### Tasks

#### 1. load-competitor-summaries
- **Type**: connector
- **Description**: Fetches competitor summaries from Sportradar API for each competitor ID
- **Foreach**: Iterates over `competitor_ids` input
- **API Endpoint**: `GET /competitors/{competitor_id}/summaries.json`
- **Output Structure**:
```python
{
  'competitor_id': 'sr:competitor:44',
  'sr_competitor_id': '44',
  'summaries_data': {...}  # Raw API response
}
```

#### 2. check-existing-competitor-summaries
- **Type**: document (search)
- **Description**: Checks MongoDB for existing competitor summary documents
- **Filter**: `metadata.competitor_id` in provided competitor IDs
- **Purpose**: Enables idempotent upsert behavior

#### 3. bulk-save-competitor-summaries
- **Type**: document (bulk-update)
- **Description**: Creates or updates competitor summary documents
- **Action**: `bulk-update` (upsert semantics - safe to re-run)
- **Embedding**: Uses OpenAI `text-embedding-3-small` on document title
- **Document Name**: `'competitor:Summarie'`

### Document Schema

Each saved document follows this structure:

```python
{
  'name': 'competitor:Summarie',
  'metadata': {
    'competitor_id': 'sr:competitor:44',
    'sr_competitor_id': '44',
    'sport': 'soccer',
    'data_source': 'sportradar'
  },
  'competitor_info': {
    'id': 'sr:competitor:44',
    'name': 'Manchester United',
    'abbreviation': 'MUN',
    'country': 'England',
    'country_code': 'ENG',
    'gender': 'male'
  },
  'summaries': [...],  # Array of recent match summaries
  'total_summaries': 20,
  'last_modified': '2026-01-19T00:00:00Z',
  'title': 'Manchester United Summaries'
}
```

## Integration with Config Seasons

### How It Works

1. **Config Seasons Workflow** (`config-seasons.yml`):
   - Loads season configuration
   - Fetches competitors for each current season
   - Deduplicates competitor IDs across all seasons
   - Outputs `competitor-ids` array

2. **Config Seasons Agent** (`agents/config-seasons.yml`):
   - Executes `sportradar-soccer-config-seasons-workflow`
   - Receives `competitor-ids` from workflow output
   - Invokes `sportradar-soccer-sync-competitor-summaries` with those IDs
   - Logs execution status

### Execution Flow

```
sportradar-soccer-config-seasons (Agent)
  │
  ├─> sportradar-soccer-config-seasons-workflow
  │     └─> Collects competitor IDs from seasons
  │
  ├─> sportradar-soccer-sync-season-schedules
  │     └─> Syncs season schedules (existing)
  │
  └─> sportradar-soccer-sync-competitor-summaries (NEW)
        └─> Syncs competitor summaries
```

## Usage

### Automatic Execution
The workflow runs automatically when the `sportradar-soccer-config-seasons` agent executes (every 10 minutes by default via `config-frequency`).

### Manual Execution via MCP

```python
# Execute the workflow directly with specific competitor IDs
mcp__machina_client_dev__execute_workflow(
    name="sportradar-soccer-sync-competitor-summaries",
    context={
        "competitor_ids": ["sr:competitor:44", "sr:competitor:45"]
    }
)
```

### Querying Saved Documents

```python
# Search for all competitor summaries
mcp__machina_client_dev__search_documents(
    filters={"name": "competitor:Summarie"},
    sorters=["updated", -1],
    page_size=50
)

# Search for a specific competitor
mcp__machina_client_dev__search_documents(
    filters={
        "name": "competitor:Summarie",
        "metadata.competitor_id": "sr:competitor:44"
    }
)
```

## Idempotency

The workflow uses `bulk-update` with `force-update: true`, ensuring:
- ✅ **Safe to re-run**: Multiple executions update existing docs instead of creating duplicates
- ✅ **Automatic deduplication**: Competitor IDs are unique across multiple seasons
- ✅ **Consistent metadata**: All documents tagged with `competitor:Summarie`

## Error Handling

- **Empty competitor list**: Workflow skips execution (`workflow-status: 'skipped'`)
- **API failures**: Individual competitor failures don't block others (foreach iteration continues)
- **Missing API key**: Requires `$TEMP_CONTEXT_VARIABLE_SPORTRADAR_SOCCER_V4_API_KEY` in vault

## Dependencies

### Connectors
- `sportradar-soccer`: API client for Sportradar Soccer API
- `machina-ai`: OpenAI client for embeddings

### Environment Variables
- `$TEMP_CONTEXT_VARIABLE_SPORTRADAR_SOCCER_V4_API_KEY`: Sportradar API key
- `$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY`: OpenAI API key

## Testing

### Test Workflow Execution

```python
# 1. Ensure credentials are configured
mcp__machina_client_dev__execute_workflow(
    name="sportradar-soccer-test-credentials"
)

# 2. Run sync with test competitor (e.g., Manchester United)
mcp__machina_client_dev__execute_workflow(
    name="sportradar-soccer-sync-competitor-summaries",
    context={
        "competitor_ids": ["sr:competitor:44"]
    }
)

# 3. Verify document creation
mcp__machina_client_dev__search_documents(
    filters={
        "name": "competitor:Summarie",
        "metadata.sr_competitor_id": "44"
    }
)
```

### Validate via Config Seasons Agent

```python
# Execute the full agent workflow
mcp__machina_client_dev__execute_agent(
    agent_id="<config-seasons-agent-id>",
    messages=[{"role": "user", "content": "run"}],
    context={}
)

# Check agent execution history
mcp__machina_client_dev__search_agent_executions(
    filters={"agent_name": "sportradar-soccer-config-seasons"},
    sorters=["timestamp", -1],
    page_size=1
)
```

## Monitoring

### Success Indicators
- `workflow-status: 'executed'` in output
- `total_summaries > 0` in saved documents
- Recent `last_modified` timestamp

### Common Issues
- **Status: skipped**: No competitor IDs provided
- **Empty summaries array**: Competitor has no recent matches
- **Missing competitor_info**: API response structure changed

## Related Files

- **Workflow**: `workflows/sync-competitor-summaries.yml`
- **Agent Configuration**: `agents/config-seasons.yml`
- **Config Workflow**: `workflows/config-seasons.yml`
- **Installation Manifest**: `_install.yml`
- **Similar Pattern**: `workflows/sync-season-schedules.yml` (seasons analog)

## Changelog

### 2026-01-19 - Initial Implementation
- Created `sync-competitor-summaries.yml` workflow
- Integrated into `config-seasons` agent and workflow
- Added document schema with `competitor:Summarie` metadata
- Implemented idempotent upsert behavior
- Added README documentation

