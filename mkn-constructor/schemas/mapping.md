# Mapping YAML Schema

Mappings define data transformation rules. They extract and reshape values from the workflow state without making external calls.

**Location**: `agent-templates/<template-name>/mappings/<mapping-name>.yml`

---

## Root Structure

```yaml
mappings:
  - type: mapping
    name: <string>           # Required. Unique identifier (kebab-case)
    title: <string>          # Required. Human-readable title
    description: <string>    # Optional. What this mapping does
    outputs: <object>        # Required. Transformation expressions
```

**Note**: The root key is `mappings:` (array), not `mapping:` (singular). A single file can contain multiple mapping definitions.

---

## Field Reference

### `name` (required)

Unique identifier. Must match the `name` field in the workflow's mapping task.

```yaml
name: api-football-mapping
```

### `title` (required)

```yaml
title: API Football Mapping
```

### `description` (optional)

```yaml
description: "Mapping data from api-football data"
```

### `outputs` (required)

Key-value pairs where each value is a Python expression evaluated against the workflow state. The results become available in the workflow's accumulated state.

```yaml
outputs:
  event_code: "$.get('event_selected', {}).get('fixture', {}).get('id')"
  season: "$.get('event_selected', {}).get('league', {}).get('season')"
  team_home_name: "$.get('event_selected', {}).get('teams', {}).get('home', {}).get('name')"
```

---

## Pattern Examples

### Field Extraction (flatten nested data)

Extract deeply nested values into flat, accessible keys.

```yaml
mappings:
  - type: mapping
    name: api-football-mapping
    title: API Football Mapping
    description: "Mapping data from api-football data"
    outputs:
      event_code: "$.get('event_selected', {}).get('fixture', {}).get('id')"
      season: "$.get('event_selected', {}).get('league', {}).get('season')"
      season_title: "$.get('event_selected', {}).get('league', {}).get('name')"
      team_home_name: "$.get('event_selected', {}).get('teams', {}).get('home', {}).get('name')"
      team_away_name: "$.get('event_selected', {}).get('teams', {}).get('away', {}).get('name')"
      team_home_id: "$.get('event_selected', {}).get('teams', {}).get('home', {}).get('id')"
      team_away_id: "$.get('event_selected', {}).get('teams', {}).get('away', {}).get('id')"
      title: "$.get('event_selected', {}).get('title')"
      article_count: "$.get('event_selected', {}).get('version_control', {}).get('article_count', 0)"
      research_stats_count: "$.get('event_selected', {}).get('version_control', {}).get('research_stats_count', 0)"
```

### Simple Passthrough

Pass a value through, sometimes with a transformation (e.g., slicing a list).

```yaml
mappings:
  - type: mapping
    name: assistant-find-markets-mapping
    title: Assistant - Mapping Markets
    description: Mapping data from markets
    outputs:
      markets-mapping: $.get('selected_markets_parsed')
```

### List Comprehension (transform arrays)

Transform arrays of objects into new shapes using Python list comprehensions.

```yaml
mappings:
  - type: mapping
    name: assistant-find-markets-odds-mapping
    title: Assistant - Market Odds Mapping
    description: Mapping data from market-runners
    outputs:
      mapped-odds: |
        [
          {
            'id': m.get('id'),
            'marketType': m.get('marketType'),
            'title': m.get('title'),
            'options': [
              {
                'id': option.get('id'),
                'name': option.get('name', {}).get('text', ''),
                'price': option.get('price', {}).get('odds', '')
              }
              for option in m.get('options', [])
              if option.get('isOpenForBetting', False)
            ],
            'period': m.get('period'),
            'subPeriod': m.get('subPeriod')
          }
          for m in $.get('market-odds', [])
        ]
      mapped-runners: |
        [
          {
            'event-id': m.get('metadata', {}).get('market_code', ''),
            'market-id': m.get('id'),
            'option-id': o.get('id'),
            'marketType': m.get('marketType'),
            'name': o.get('name', {}).get('text', ''),
            'price': o.get('price', {}).get('odds', ''),
            'title': f"{m.get('title')} {o.get('name', {}).get('text', '')}: {o.get('price', {}).get('odds', '')}",
          }
          for m in $.get('market-odds', [])
          for o in m.get('options', [])
          if o.get('isOpenForBetting', False)
        ]
      market-types: |
        list(set([
          m.get('marketType')
          for m in $.get('market-odds', [])
        ]))
```

### Multiple Mappings in One File

```yaml
mappings:
  - type: mapping
    name: assistant-find-markets-mapping
    title: Assistant - Mapping Markets
    description: Mapping data from markets
    outputs:
      markets-mapping: $.get('selected_markets_parsed')

  - type: mapping
    name: assistant-find-markets-odds-mapping
    title: Assistant - Market Odds Mapping
    description: Mapping data from market-runners
    outputs:
      mapped-odds: |
        [...]
```

---

## How Mappings Are Used in Workflows

A mapping task in a workflow references the mapping by `name`:

```yaml
# In workflow YAML
- type: mapping
  name: api-football-mapping
  description: Transform the match data
  condition: "$.get('event_exists') is True"
  inputs:
    event_selected: "$.get('event_selected')"
  outputs:
    event_code: "$.get('event_code')"
    season: "$.get('season')"
    team_home_name: "$.get('team_home_name')"
```

**Flow**:
1. Workflow task `inputs` set values in the mapping's execution context
2. Mapping `outputs` expressions are evaluated against that context
3. Workflow task `outputs` extract from the mapping result back into workflow state

**When to use mappings vs inline outputs**:
- **Use mappings** when the transformation is reused across multiple workflows
- **Use mappings** when the transformation is complex (list comprehensions, nested filtering)
- **Use inline outputs** (directly in a task's `outputs:`) for simple one-off extractions

---

## Expression Syntax

All mapping expressions are Python evaluated against the workflow state.

```yaml
# Simple field access
field: "$.get('source', {}).get('nested_field')"

# With defaults
field: "$.get('source', {}).get('field', 0)"

# List comprehension
items: |
  [item.get('name') for item in $.get('list', [])]

# Nested list comprehension
items: |
  [
    {
      'id': item.get('id'),
      'children': [c.get('value') for c in item.get('children', [])]
    }
    for item in $.get('list', [])
  ]

# Filtered list comprehension
items: |
  [
    item for item in $.get('list', [])
    if item.get('active', False)
  ]

# Deduplicated list
unique_types: |
  list(set([
    item.get('type')
    for item in $.get('list', [])
  ]))

# f-string formatting
title: |
  f"{m.get('title')} {o.get('name')}: {o.get('price')}"
```

---

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Mapping name | `<source>-mapping` or `<purpose>-mapping` | `api-football-mapping` |
| File name | `<descriptive-name>.yml` | `find-markets-odds.yml` |

---

## Common Mistakes

| Mistake | Correct |
|---------|---------|
| `mapping:` (singular root) | `mappings:` (array) |
| Missing `type: mapping` on each entry | Every entry needs `type: mapping` |
| `inputs:` in mapping YAML | Mappings only have `outputs:` — inputs come from the workflow task |
| No `outputs:` block | Required — the whole point of a mapping |
| Using mappings for API calls | Mappings are pure transformations — use `type: connector` for API calls |
