# Architecture

## LLM Provider

The prompts in this template use `google-genai` as the LLM provider, specifically with `provider: vertex_ai` and `location: global`. The model used is `gemini-2.5-flash`. This choice was made for its balance of performance, cost, and availability.

The connector is configured as follows in all prompt tasks:

```yaml
connector:
  name: google-genai
  command: invoke_prompt
  model: gemini-2.5-flash
  provider: vertex_ai
  location: global
```

This ensures consistency across all content generation workflows within the `machina-media` template.

## How it flows end-to-end

The template is orchestrated by a set of agents that trigger chains of workflows based on schedules or events.

### a) Scheduled Morning Briefing

This flow runs on a daily schedule to produce a morning sports news show.

1.  **Agent:** `desk-program-agent`
2.  **Trigger:** Schedule (e.g., daily at 6:00 AM) with `current_slot: 'morning_briefing'`
3.  **Workflow Chain:**
    *   `sync-sports-state`: Fetches the latest games, news, and market data.
    *   `detect-storylines`: Identifies narrative threads from the raw data.
    *   `rank-storylines`: Prioritizes storylines for the morning slot.
    *   `generate-morning-briefing`: Creates the main show script.
    *   `generate-clip-candidates`: Identifies viral moments for social media.
    *   `generate-social-derivatives`: Drafts posts for X, Instagram, etc.

### b) Postgame Recap

This flow is triggered after a major game or event concludes.

1.  **Agent:** `desk-program-agent`
2.  **Trigger:** Schedule (e.g., hourly checks) with `current_slot: 'postgame_recap'`
3.  **Workflow Chain:**
    *   `sync-sports-state`: Fetches final scores and post-game data.
    *   `detect-storylines`: Identifies key narratives from the game.
    *   `rank-storylines`: Prioritizes storylines for a recap context.
    *   `generate-postgame-recap`: Creates the recap script.
    *   `generate-social-derivatives`: Drafts recap posts.

### c) Breaking News Alert

This flow is designed for high-urgency, event-driven updates.

1.  **Agent:** `desk-reactive-agent`
2.  **Trigger:** High-frequency polling for breaking news events (e.g., trades, injuries).
3.  **Workflow Chain:**
    *   `sync-sports-state`: Fetches data from a very short time window.
    *   `detect-storylines`: Identifies new, urgent narratives.
    *   `rank-storylines`: Ranks with `current_slot: 'breaking_alert'`.
    *   `filter-breaking-storylines`: Selects only storylines with `urgency: 'breaking'`.
    *   `generate-breaking-news-alert`: Creates a short, immediate script.
    *   `generate-social-derivatives`: Drafts an instant post for X.

### d) Operator Override

This flow allows a human operator to manually trigger content generation.

1.  **Agent:** `desk-executor`
2.  **Trigger:** Manual API call or `machina agent run` command from an operator.
3.  **Workflow Chain:**
    *   The operator provides `operator_instruction`, `target_storyline_or_event`, and a `target_slot`.
    *   The agent directly invokes the appropriate generation workflow (e.g., `generate-live-desk-update`) based on the `target_slot`, bypassing the automated detection and ranking steps.

