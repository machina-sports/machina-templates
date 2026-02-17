# Document Task Schema

The `type: document` task is the interface to MongoDB. Used for searching, creating, updating, and bulk-updating documents within workflows.

**Used in**: `agent-templates/<template-name>/workflows/<workflow-name>.yml` (inside `tasks:`)

---

## Task Structure

```yaml
- type: document
  name: <string>              # Required. Unique task name
  description: <string>       # Optional. What this task does
  condition: <expression>     # Optional. Skip if False
  config:                     # Required. Action and behavior settings
    action: <string>          # Required. search, save, update, bulk-update, bulk-save
    search-limit: <int>       # Optional. Max documents to return (search)
    search-vector: <bool>     # Optional. Use vector similarity search
    search-sorters: <list>    # Optional. Sort results [field, direction]
    threshold-docs: <int>     # Optional. Max docs for vector search
    threshold-similarity: <f> # Optional. Min similarity score for vector search
    embed-vector: <bool>      # Optional. Generate embeddings on save/update
    force-update: <bool>      # Optional. Force update even if unchanged
  connector:                  # Optional. Embedding connector (for vector operations)
    name: <string>
    command: <string>
    model: <string>
  filters: <object>           # Optional. Query filters for search/update
  inputs: <object>            # Optional. Additional query parameters
  documents: <object>         # Optional. Data to save/update (for write actions)
  document_name: <string>     # Optional. Target collection name
  metadata: <object>          # Optional. Document metadata for upsert matching
  outputs: <object>           # Optional. Values extracted from results
```

---

## Actions

### `search`

Find documents in the database. Results are available in `$.get('documents')`.

```yaml
- type: document
  name: load-thread-document
  config:
    action: search
    search-limit: 1
    search-vector: false
  filters:
    name: "'thread'"
    document_id: $.get('thread_id')
  outputs:
    document_id: $.get('documents')[0].get('_id') if len($.get('documents', [])) > 0 else None
    document_exists: len($.get('documents', [])) > 0 if $.get('documents') else False
    document_value: $.get('documents')[0].get('value', {}) if len($.get('documents', [])) > 0 else {}
```

**Search with sorters**:

```yaml
- type: document
  name: load-event-by-schedule
  config:
    action: search
    search-limit: 1
    search-vector: false
    search-sorters: ["start_time", 1]    # 1 = ascending, -1 = descending
  filters:
    value.start_time: "{'$gt': datetime.utcnow() - timedelta(days=30), '$lt': datetime.utcnow() + timedelta(days=30)}"
    value.version_control.research_stats_status: "{'$ne': 'processed'}"
  inputs:
    name: "{'$in': ['soccer-game']}"
  outputs:
    event_exists: "len($.get('documents', [])) > 0"
    event_selected: "$.get('documents')[0].get('value', {}) if $.get('documents') else None"
```

**Vector similarity search**:

```yaml
- type: document
  name: load-similar-documents
  config:
    action: search
    threshold-docs: 5
    threshold-similarity: 0.01
    search-limit: 1000
    search-vector: true
  connector:
    name: machina-ai
    command: invoke_embedding
    model: text-embedding-3-small
  inputs:
    name: "'content-snippet'"
    search-limit: "'1000'"
    search-query: "$.get('messages')"
  outputs:
    parsed_documents: |
      [
        {
          **d.get('value', {}),
        }
        for d in $.get('documents', [])
      ]
```

### `save`

Create a new document. The document key becomes the `name` field in the database.

```yaml
- type: document
  name: create-thread-document
  condition: $.get('document_id') is None
  config:
    action: save
    embed-vector: false
    force-update: true
  documents:
    thread: |
      {
        'messages': [],
        'status': 'created',
        'status_message': 'Thread created',
        'context': 'machina-assistant'
      }
  metadata:
    agent_id: "'machina-assistant'"
    created_at: datetime.now().isoformat()
    source: "'machina-assistant'"
  outputs:
    document_id: $.get('documents')[0].get('_id') if len($.get('documents', [])) > 0 else None
```

**`documents` block**: Each key is the document `name`. The value is a Python expression that produces the document's `value` field.

### `update`

Update an existing document, identified by `filters`.

```yaml
- type: document
  name: update-thread-reasoning
  config:
    action: update
    embed-vector: false
    force-update: true
  condition: $.get('document_id') is not None
  documents:
    thread: |
      {
        **$.get('document_value'),
        'messages': [
          *$.get('document_value').get('messages', []),
          {
            'role': 'user',
            'content': $.get('input_message'),
            'timestamp': datetime.now().isoformat()
          }
        ],
        'status': 'reasoning',
        'reasoning': $.get('reasoning', {})
      }
  filters:
    document_id: $.get('document_id')
```

**Spread pattern** (`**` / `*`): Used to preserve existing fields while updating specific ones.

```yaml
# Merge existing dict with new fields
{**$.get('event_selected'), 'status': 'updated'}

# Append to existing list
[*$.get('document_value').get('messages', []), new_item]
```

**Update with version control** (common pattern):

```yaml
- type: document
  name: version-control-update
  config:
    action: update
    embed-vector: false
    force-update: true
  documents:
    soccer-game: |
      {
        **$.get('event_selected'),
        'version_control': {
          **$.get('event_selected').get('version_control', {}),
          'processing': True,
          'research_stats_status': 'processing'
        }
      }
  metadata:
    event_code: "$.get('event_code')"
```

**Update multiple named documents** in a single task:

```yaml
- type: document
  name: update-documents-standings
  config:
    action: update
    embed-vector: false
    force-update: true
  documents:
    standings-analysis: |
      {
        "execution": datetime.utcnow(),
        "content": $.get('research-standings'),
        "title": f"{$.get('title')} - Standings Analysis",
        "status": 'active'
      }
    comparison-analysis: |
      {
        "execution": datetime.utcnow(),
        "content": $.get('research-comparison'),
        "title": f"{$.get('title')} - Comparison Analysis",
        "status": 'active'
      }
  metadata:
    event_code: "$.get('event_code')"
```

### `bulk-update`

Upsert multiple documents from a list. Requires `document_name` to specify the collection.

```yaml
- type: document
  name: store-suggestions
  config:
    action: bulk-update
    force-update: true
  document_name: "social-media-suggestion"
  documents:
    items: |
      [
        {
          'title': $.get('home_team_name', '') + ' vs ' + $.get('away_team_name', ''),
          'event_id': str($.get('event_id')),
          'content_type': item.get('content_type', ''),
          'content': item,
          'has_image': False,
          'status': 'pending',
          'timestamp': datetime.utcnow().isoformat(),
          'metadata': {
            'event_id': str($.get('event_id')),
            'content_type': item.get('content_type', ''),
            'document_type': 'social-media-suggestion'
          }
        }
        for item in $.get('content_suggestions', [])
      ]
  outputs:
    suggestion_ids: |
      [
        str(item.get('_id', ''))
        for item in $.get('documents', [])
      ]
```

### `bulk-save`

Save multiple documents with optional embedding generation.

```yaml
- type: document
  name: update-snippets
  config:
    action: bulk-save
    embed-vector: true
    force-update: true
  connector:
    name: openai
    command: invoke_embedding
    model: text-embedding-3-small
  document_name: "content-snippet"
  documents:
    items: "$.get('parsed-items')"
  inputs:
    parsed-items: |
      [
        *$.get('research-standings-bulk', []),
        *$.get('research-comparison-bulk', []),
        *$.get('research-players-to-watch-bulk', [])
      ]
```

---

## Config Fields Reference

| Field | Actions | Type | Description |
|-------|---------|------|-------------|
| `action` | all | string | `search`, `save`, `update`, `bulk-update`, `bulk-save` |
| `search-limit` | search | int | Max documents returned (default varies) |
| `search-vector` | search | bool | Enable vector similarity search |
| `search-sorters` | search | list | Sort: `["field_name", 1]` (1=asc, -1=desc) |
| `threshold-docs` | search | int | Max docs for vector search results |
| `threshold-similarity` | search | float | Min similarity score (0.0–1.0) |
| `embed-vector` | save, update, bulk-save | bool | Generate vector embeddings |
| `force-update` | save, update, bulk-update, bulk-save | bool | Force write even if unchanged |

---

## Filters Reference

Filters target documents for search and update operations. Values are Python expressions.

```yaml
filters:
  # Match by document ID
  document_id: $.get('document_id')

  # Match by document name
  name: "'thread'"

  # Match by metadata field
  metadata.event_code: "$.get('event_code')"

  # MongoDB query operators
  value.start_time: "{'$gt': datetime.utcnow() - timedelta(days=30)}"
  value.status: "{'$ne': 'processed'}"
```

**Using `inputs` for name filtering** (MongoDB query syntax):

```yaml
inputs:
  name: "{'$in': ['sport:Event']}"
  name: "{'$in': ['soccer-game']}"
```

---

## Document Structure in MongoDB

Each document stored has this shape:

```json
{
  "_id": "ObjectId(...)",
  "name": "thread",
  "value": { ... },
  "metadata": { ... },
  "embedding": [0.01, 0.02, ...]
}
```

- `name` — comes from the key in `documents:` block (e.g., `thread`, `soccer-game`)
- `value` — the Python dict expression from `documents:` block
- `metadata` — from the `metadata:` block
- `embedding` — auto-generated when `embed-vector: true`

---

## Output Patterns

### Extracting from search results

```yaml
# Check if documents exist
document_exists: len($.get('documents', [])) > 0

# Safe check with guard
document_exists: len($.get('documents', [])) > 0 if $.get('documents') else False

# Get first document ID
document_id: $.get('documents')[0].get('_id') if len($.get('documents', [])) > 0 else None

# Get first document value
document_value: $.get('documents')[0].get('value', {}) if len($.get('documents', [])) > 0 else {}

# Get nested field from first document
event_code: $.get('documents')[0].get('metadata', {}).get('event_code') if len($.get('documents', [])) > 0 else None

# Get field from first document value
messages: $.get('documents')[0].get('value', {}).get('messages', []) if len($.get('documents', [])) > 0 else []

# Transform documents list
parsed_documents: |
  [
    {**d.get('value', {})}
    for d in $.get('documents', [])
  ]

# Extract IDs from bulk operation results
suggestion_ids: |
  [
    str(item.get('_id', ''))
    for item in $.get('documents', [])
  ]
```

### After save/update

```yaml
# Save returns the created document in documents array
document_id: $.get('documents')[0].get('_id') if len($.get('documents', [])) > 0 else None

# Set a success flag
success: True
workflow_executed_status: "'executed'"
```

---

## Common Mistakes

| Mistake | Correct |
|---------|---------|
| `action: find` | `action: search` |
| `action: upsert` | `action: update` with `force-update: true` |
| `action: insert` | `action: save` |
| Missing `config.action` | Every document task needs `config.action` |
| `search-vector: true` without connector | Need `connector:` block for embedding model |
| `documents:` on a search task | Search uses `filters:`, not `documents:` |
| `filters:` on a save task | Save uses `documents:`, not `filters:` |
| Forgetting safe access on search outputs | Always guard with `if len($.get('documents', [])) > 0 else` |
| `document_name` on non-bulk actions | Only used with `bulk-update` and `bulk-save` |
| `embed-vector: true` without connector | Need `connector:` for embedding generation |
