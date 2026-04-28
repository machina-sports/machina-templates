# News Monitor: Storylines Skill

This skill monitors news articles for a given entity and clusters them into distinct storylines.

## Use Cases

- Tracking media coverage for a specific player, team, or league.
- Identifying emerging narratives and trending topics.
- Summarizing key events over a specific time period.

## How to Use

Invoke the skill through its entry-point workflow, `news-monitor-workflow`, providing the following inputs:

- `entity` (string): The name of the entity to search for (e.g., "Kylian Mbappé").
- `entity_type` (string): The type of entity (e.g., "player", "team").
- `start_date` (string): The start date for the news search (e.g., "2023-10-27").

### Example

```bash
machina skills run news-monitor-storylines entity="Kylian Mbappé" entity_type="player" start_date="2024-05-01"
```

## Output

The skill returns a JSON object with two main keys:

- `storylines`: A list of identified storylines, each with a title, summary, timeline, sources, and a recommended action.
- `outliers`: A list of articles that did not fit into any specific storyline.
