# Project Morning Briefing Agent Template

This agent template creates a "morning briefing" by fetching items from an RSS feed, filtering them for recent updates, and summarizing them into a concise 5-bullet point list.

## How it works

1.  **Fetches RSS Feed**: Uses a connector to get the latest items from a specified RSS feed URL.
2.  **Filters Recent Items**: A Python script filters the items to include only those published within a configurable lookback period (default: 24 hours). It's timezone-aware.
3.  **Summarizes Content**: Uses a Google GenAI prompt to generate a friendly, 5-bullet summary of the recent items, grouped by topic.

## Installation

You can install this template using the Machina CLI:

```bash
machina template install agent-templates/project-morning-briefing
```

## Usage

After installation, you can run the workflow directly. You will need to provide the `rss_url` as an input.

### Run via Machina CLI

```bash
machina workflow run project-morning-briefing rss_url="<your_rss_feed_url>"
```

**Optional Inputs:**

*   `timezone`: The timezone for calculating the lookback period. Defaults to `'America/Sao_Paulo'`.
*   `lookback_hours`: How many hours back to check for new items. Defaults to `24`.

Example:
```bash
machina workflow run project-morning-briefing \
  rss_url="https://feeds.bbci.co.uk/news/rss.xml" \
  timezone="'Europe/London'" \
  lookback_hours=12
```

## Scheduling with Cron

To run this briefing automatically every weekday at 7:30 AM, you can schedule it with `cron`.

1.  Open your crontab for editing:
    ```bash
    crontab -e
    ```

2.  Add the following line, replacing `<your_rss_feed_url>` and ensuring your `machina` CLI path is correct.

    ```cron
    30 7 * * 1-5 machina workflow run project-morning-briefing rss_url="<your_rss_feed_url>" --project <your-project-id>
    ```

This will trigger the workflow every Monday through Friday at 7:30 AM server time. You may need to configure authentication for the CLI to run in a non-interactive environment (e.g., using API keys).
