# Project Morning Briefing Agent Template

This agent template provides a simple, yet powerful, "morning briefing" generated from any RSS feed. It fetches recent news, summarizes it using AI, and prepares a markdown-formatted briefing.

## Features

- **RSS Feed Integration**: Connects to any standard RSS feed to pull in the latest articles.
- **AI-Powered Summarization**: Uses Google's Gemini model to create concise, easy-to-read summaries.
- **Customizable**: Easily change the RSS feed URL, lookback window, and timezone.
- **Schedulable**: Designed to be run on a schedule for automated daily briefings.

## How to Install

1.  **Using `machina-cli`**:
    ```bash
    machina template install agent-templates/project-morning-briefing
    ```

## How to Run

You can run the briefing generation process manually using the `machina-cli`.

1.  **Execute the workflow**:
    ```bash
    machina workflow run generate-briefing rss_url='<your-rss-feed-url>'
    ```
    For example, to get news from The Guardian:
    ```bash
    machina workflow run generate-briefing rss_url='https://www.theguardian.com/world/rss'
    ```

2.  **Check the output**: The workflow will return `briefing_markdown` with the summarized content and `items_considered` with the list of articles used.

## Scheduling with `crontab`

To get your morning briefing automatically, you can schedule it with `crontab`. The following example runs the briefing every weekday at 7:30 AM.

1.  **Open your crontab for editing**:
    ```bash
    crontab -e
    ```

2.  **Add the schedule line**:
    Make sure to replace `<your-machina-api-key>`, `<your-org-id>`, `<your-project-id>`, and the `rss_url` with your actual values.

    ```bash
    30 7 * * 1-5 /path/to/machina-cli/machina --api-key <your-machina-api-key> --project <your-project-id> workflow run generate-briefing rss_url='http://feeds.bbci.co.uk/news/rss.xml' > /var/log/morning-briefing.log 2>&1
    ```
    *Note: You may need to use the full path to your `machina` executable.*

This setup ensures you have a fresh briefing ready for you every morning.
