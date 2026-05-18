# white-label-athlete-tracker

Daily athlete tracker. Takes a roster and emits one card per athlete with
latest performance, top 5 news headlines, and a short narrative pulse.

**White-label** — no brand references appear in the output copy. The
payload is structured JSON + a markdown rendering, ready for a CMS or
mobile-app to ingest.

---

## Inputs

```json
{
  "roster": [
    { "name": "Bukayo Saka",   "sport": "football" },
    { "name": "Jayson Tatum",  "sport": "nba"      },
    { "name": "Patrick Mahomes", "sport": "nfl"    },
    { "name": "Carlos Alcaraz", "sport": "tennis"  }
  ]
}
```

`sport` is optional. Supported values: `football`, `nba`, `nfl`, `mlb`,
`nhl`, `tennis`, `golf`, `f1`. Anything else (or missing) still produces
a news-only card; the performance line will read `"No match this week."`

---

## Output shape

```json
{
  "cards": [
    {
      "athlete": "Bukayo Saka",
      "sport": "football",
      "last_game": "2025-11-23: Arsenal vs Chelsea — 2-1 W, 1 goal & 1 assist over 90 minutes.",
      "form_summary": "Returned to the starting XI after a calf scare; involved in 4 goals across the last 3 league outings.",
      "headlines": [
        { "title": "...", "source": "BBC Sport", "url": "https://...", "published_at": "2025-11-24T08:00:00Z" }
      ],
      "pulse": "Coverage centres on his fitness recovery and Arsenal's renewed title push.",
      "markdown": "## Bukayo Saka\n_football_\n\n**Last game:** 2025-11-23: Arsenal vs Chelsea — 2-1 W...",
      "generated_at": "2025-11-26T14:00:00Z"
    }
  ],
  "roster_size": 4,
  "workflow-status": "executed"
}
```

---

## Architecture

```
roster: [{name, sport?}, ...]
    │
    ▼  (foreach over roster, concurrent)
fetch-news-per-athlete   →  sports-skills / invoke_news / fetch_items
    │
    ▼  (foreach per sport, conditional)
fetch-football-perf      →  sports-skills / invoke_football / search_player
fetch-nba-perf           →  sports-skills / invoke_nba      / get_scoreboard
fetch-nfl-perf           →  sports-skills / invoke_nfl      / get_scoreboard
fetch-mlb-perf           →  sports-skills / invoke_mlb      / get_scoreboard
fetch-nhl-perf           →  sports-skills / invoke_nhl      / get_scoreboard
fetch-tennis-perf        →  sports-skills / invoke_tennis   / get_scoreboard
fetch-golf-perf          →  sports-skills / invoke_golf     / get_scoreboard
fetch-f1-perf            →  sports-skills / invoke_f1       / get_scoreboard
    │
    ▼
assemble-athlete-cards   →  google-genai / gemini-2.5-pro
    │
    ▼
cards: [{athlete, sport, last_game, form_summary, headlines[≤5], pulse, markdown, generated_at}]
```

The assembler matches per-athlete news / performance payloads to the
roster by name (each payload carries its athlete + sport). Order in
the output `cards` array matches the input roster.

---

## Defensive defaults

- No news in the last 24h → `pulse: "Quiet news cycle in the last 24 hours."`, `headlines: []`
- No recent match / sport feed unreachable → `last_game: "No match this week."`, `form_summary: "No recent form data available."`
- Sport not in the supported list → news-only card, performance defaults as above
- Each section in the markdown is always rendered (even if empty-state) so the brand's renderer never has missing keys

A single source failing does not 500 the workflow — `foreach` outputs
accumulate independently and the assembler tolerates missing entries.

---

## Components installed

- **Connector:** `sports-skills` (single dispatcher over 19 sports / news modules)
- **Workflow:** `build-athlete-tracker`
- **Prompt:** `assemble-athlete-cards` (Gemini 2.5 Pro / Vertex AI)
- **Agent:** `white-label-athlete-tracker` (thin wrapper around the workflow)

---

## Run

```bash
# Sync — returns the cards array
machina workflow run build-athlete-tracker --sync \
  roster='[{"name":"Bukayo Saka","sport":"football"},{"name":"Jayson Tatum","sport":"nba"}]'

# Or via the agent
machina agent run white-label-athlete-tracker --sync \
  roster='[{"name":"Bukayo Saka","sport":"football"}]'

# Or REST
curl -X POST "https://<org>-<project>.org.machina.gg/workflow/execute/build-athlete-tracker" \
  -H "Content-Type: application/json" \
  -H "X-Session-Token: $SESSION" -H "X-Project-Token: $PROJECT" \
  -d '{"roster":[{"name":"Bukayo Saka","sport":"football"}]}'
```

---

## Required vault keys

- `TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL` — Vertex AI service-account JSON
- `TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID` — GCP project ID

Both are standard on any Machina project with `google-vertex` configured.
The `sports-skills` connector itself needs no API keys for the modules
this template uses (public-data feeds: ESPN / Understat / FPL / aggregated
news).
