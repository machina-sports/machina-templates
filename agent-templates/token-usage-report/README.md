# Weekly Token Report

Cron-driven weekly token-consumption report for any Machina pod. Reads
the pod's own `/execution/workflow-search` and `/execution/agent-search`
endpoints, aggregates by name, renders a PDF, ships to email + Slack.

## What you get

Every Monday 9 a.m. UTC (configurable):

- **Email** with the PDF attached and the headline numbers in the body.
- **Slack** message with a clickable "Open PDF" button.
- **PDF on GCS** — public URL valid as long as the bucket's object lives.

The PDF (using `pdf-generator:metrics-report`) carries:

- Title row + period range
- 4 summary KPI cards (total tokens, total runs, avg/run, success rate)
- **By workflow / agent** — table of top 15 + an "others" bucket
- **By day** — token + run count per calendar day in the window
- **Distribution** — p50 / p95 / max tokens per run
- **Top consuming runs** — 5 most expensive bullets
- **Failures in window** — status breakdown when non-zero
- Footer with generation timestamp

## Install

```bash
machina template install agent-templates/weekly-token-report
```

This pulls in two new connectors (`token-aggregator` is bundled
inline; `resend` and `slack-webhook` install separately if you don't
already have them):

```bash
machina connector install resend
machina connector install slack-webhook
# pdf-generator must also be present (existing template):
machina template install agent-templates/pdf-generator
```

## Required vault keys

| Key | What |
|---|---|
| `WEEKLY_TOKEN_REPORT_API_BASE_URL` | The pod's own public URL (e.g. `https://entain-organization-sports-interaction-v2.org.machina.gg`) |
| `WEEKLY_TOKEN_REPORT_API_KEY` | The pod's own API key (same as `x-api-token` you use from Studio) |
| `WEEKLY_TOKEN_REPORT_PROJECT_LABEL` | Display name (e.g. `Sports Interaction v2`) |
| `WEEKLY_TOKEN_REPORT_BRAND_COLOR` | Hex accent for the PDF (e.g. `#FE4000`) |
| `WEEKLY_TOKEN_REPORT_EMAIL_FROM` | Sender (e.g. `Machina Reports <reports@yourdomain.com>`); use `onboarding@resend.dev` if you don't have a verified domain |
| `WEEKLY_TOKEN_REPORT_EMAIL_TO` | Comma-separated recipient list |
| `RESEND_API_KEY` | From the Resend dashboard |
| `SLACK_WEBHOOK_URL` | Full webhook URL `https://hooks.slack.com/services/T.../B.../...` |
| `GOOGLE_STORAGE_API_KEY` | Service-account JSON (already present if pdf-generator is installed) |
| `GOOGLE_STORAGE_BUCKET_NAME` | GCS bucket where PDFs land |

## Schedule (recommended)

Run weekly on Monday 9 a.m. UTC via the pod's scheduler:

```bash
pod_mcp_call schedule_workflow_name --name weekly-token-report --cron "0 9 * * MON"
```

Or run on-demand from Studio / CLI:

```bash
machina workflow run weekly-token-report
```

Override the window for a one-off backfill:

```bash
machina workflow run weekly-token-report period_days=30
```

## Disabling a channel

Set the input on the cron invocation:

```bash
pod_mcp_call schedule_workflow_name --name weekly-token-report \
  --cron "0 9 * * MON" --inputs '{"notify_slack": false}'
```

Or skip the relevant vault key entirely — the wrapper workflows
condition on the secret being non-empty.

## Customizing

The aggregator (`connectors/token-aggregator.py`) groups by
`execution.name`. To change the grouping (e.g. roll all
`wc-bracket-*` workflows into one row), edit `_row_name()`. The
metrics-report payload schema is in pdf-generator's README — add new
sections by extending the `sections` array in `invoke_aggregate()`.
