# Match Stats Formatter Skill

This skill provides a workflow to format raw match statistics into a human-readable summary suitable for chat applications.

## Workflow: `format-match-stats`

This workflow takes a single input, `match_data`, which is expected to be a JSON object containing the raw statistics of a sports match. It uses an AI prompt to transform this data into a natural language summary.

### Inputs

- `match_data` (object): A JSON object containing the raw match data.

**Example Input:**

```json
{
  "match_id": "12345",
  "competition": "Super League",
  "home_team": {
    "name": "Dragons",
    "score": 3,
    "stats": {
      "possession": "62%",
      "shots_on_target": 8,
      "corners": 5
    }
  },
  "away_team": {
    "name": "Wizards",
    "score": 1,
    "stats": {
      "possession": "38%",
      "shots_on_target": 3,
      "corners": 2
    }
  },
  "venue": "Magic Stadium",
  "status": "FT"
}
```

### Outputs

- `formatted_stats` (string): A human-readable summary of the match.
- `workflow-status` (string): 'executed' if successful, 'skipped' otherwise.

### How to Use

You can run this workflow using the Machina CLI:

```bash
machina workflow run format-match-stats match_data='{"match_id": "...", ...}'
```

Or by calling the appropriate API endpoint.
