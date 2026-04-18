# Project Morning Briefing Agent

This agent template provides a simple way to get a daily morning briefing for your project.

## How it works

The agent consists of three workflows:

1.  **`fetch-recent`**: Fetches new items from the last 24 hours from a data source. You need to configure the URL for your project's data source in the workflow's input.
2.  **`summarize-items`**: Uses a Google Gemini model to summarize the fetched items into a concise 5-bullet list.
3.  **`deliver-briefing`**: Sends the summary via email to a list of recipients.

## Setup

1.  **Install the template**:
    ```bash
    machina template install agent-templates/project-morning-briefing
    ```

2.  **Configure secrets**: You need to set up two secrets in your project's vault:
    *   `BRIEFING_RECIPIENTS`: A comma-separated list of email addresses to send the briefing to.
    *   `SENDGRID_API_KEY`: Your SendGrid API key for sending emails.

3.  **Customize the data source**: In the `fetch-recent` workflow, change the default `url` input to point to your project's data source API endpoint for recent items.

## Scheduling

To run this agent every morning at 7:30 AM in your project's timezone, you can set up a cron job like this:

```
30 7 * * * machina agent run project-morning-briefing
```

You can also configure the timezone by passing it as an input to the agent:

```
30 7 * * * machina agent run project-morning-briefing timezone="America/New_York"
```
