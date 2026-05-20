# Token Usage Report

Cron-driven token-consumption report for any Machina pod. ONE template,
TWO cadences — schedule it weekly (Monday 9am UTC, last completed
Mon-Sun) AND monthly (1st of month 9am UTC, last completed calendar
month). The `period_mode` input picks the window; the same workflow
handles both.

Reads the pod's own `/execution/workflow-search` and
`/execution/agent-search` endpoints, aggregates by name, renders a
PDF, ships to email + Slack.

## What you get

Each scheduled run:

- **Email** with the PDF attached and the headline numbers in the body.
- **Slack** message with a clickable "Open PDF" button.
- **PDF on GCS** — public URL valid as long as the bucket's object lives.

The PDF (rendered via `pdf-generator:metrics-report`) contains:

- Title — `<project> · <Weekly|Monthly> Token Report`
- Period range (e.g. `May 12 – May 18, 2026 (UTC)` weekly, or `April 2026 (UTC)` monthly)
- 4 summary KPI cards (total tokens, total runs, avg/run, success rate) with period-over-period delta
- **By workflow / agent** — table of top 15 consumers + an "others" row
- **By day** — token + run count per calendar day in the window
- **Distribution** — p50 / p95 / max tokens per run
- **Top consuming runs** — 5 most expensive bullets
- **Failures in window** — status breakdown when non-zero
- Footer with generation timestamp

## Install

```bash
machina template install agent-templates/pdf-generator        # prerequisite
machina connector install resend
machina connector install slack-webhook
machina template install agent-templates/token-usage-report
```

## Required vault keys

| Key | What |
|---|---|
| `TOKEN_REPORT_API_BASE_URL` | The pod's own public URL (e.g. `https://machina-reports-reports.org.machina.gg`) |
| `TOKEN_REPORT_API_KEY` | The pod's own API key |
| `TOKEN_REPORT_PROJECT_LABEL` | Display name (e.g. `Machina Reports`) |
| `TOKEN_REPORT_BRAND_COLOR` | Hex accent for the PDF (e.g. `#FE4000`) |
| `TOKEN_REPORT_EMAIL_FROM` | Sender (e.g. `Machina Reports <reports@yourdomain.com>`); use `onboarding@resend.dev` if you don't have a verified domain |
| `TOKEN_REPORT_EMAIL_TO` | Comma-separated recipient list |
| `RESEND_API_KEY` | From the Resend dashboard |
| `SLACK_WEBHOOK_URL` | Full webhook URL `https://hooks.slack.com/services/T.../B.../...` |
| `GOOGLE_STORAGE_API_KEY` | Service-account JSON (already present if pdf-generator is installed) |
| `GOOGLE_STORAGE_BUCKET_NAME` | GCS bucket where PDFs land |

## Recommended schedules — set both

Run the SAME workflow twice with different inputs:

### Weekly — every Monday at 9am UTC

Covers the last completed Mon-Sun (UTC). Lands the Monday after.

```bash
pod_mcp_call schedule_workflow_name \
  --name token-usage-report \
  --cron "0 9 * * MON" \
  --inputs '{"period_mode":"previous_week"}'
```

### Monthly — every 1st of the month at 9am UTC

Covers the last completed calendar month (1st 00:00 → last day 23:59 UTC).
Lands on the 1st.

```bash
pod_mcp_call schedule_workflow_name \
  --name token-usage-report \
  --cron "0 9 1 * *" \
  --inputs '{"period_mode":"previous_month"}'
```

### On-demand backfill / debug

```bash
# Default = previous week
machina workflow run token-usage-report

# Last calendar month
machina workflow run token-usage-report period_mode=previous_month

# Custom rolling window (e.g. last 30 days)
machina workflow run token-usage-report period_mode=rolling_days period_days=30
```

## period_mode reference

| Mode | Window | Use it for |
|---|---|---|
| `previous_week` (default) | Last completed Monday 00:00 → Sunday 23:59:59 UTC | Monday cron — captures the week that just ended |
| `previous_month` | 1st of last month 00:00 → last day 23:59:59 UTC | 1st-of-month cron — captures the month that just closed |
| `rolling_days` | `now - period_days` → now | Manual / ad-hoc debugging; defaults to 7 days |

## Disabling a channel per schedule

Set the toggle in the schedule's `--inputs`:

```bash
pod_mcp_call schedule_workflow_name \
  --name token-usage-report \
  --cron "0 9 1 * *" \
  --inputs '{"period_mode":"previous_month","notify_slack":false}'
```

Or skip the relevant vault key — the wrapper workflows condition on
the secret being non-empty so absence = silently skip.

## Customizing

The aggregator (`connectors/token-aggregator.py`) groups by
`execution.name`. To change the grouping (e.g. roll all
`wc-bracket-*` workflows into one row), edit `_row_name()`. The
metrics-report payload schema is in pdf-generator's README — add new
sections by extending the `sections` array in `invoke_aggregate()`.

## Multi-pod (centralized reports)

This template aggregates the pod IT'S INSTALLED ON by default. To
pull from multiple customer pods into one centralized reports pod:
install on the reports pod, then schedule one workflow per customer
pod, each overriding `api_base_url` + `api_key` per schedule:

```bash
pod_mcp_call schedule_workflow_name \
  --name token-usage-report \
  --cron "0 9 * * MON" \
  --inputs '{
    "period_mode":"previous_week",
    "api_base_url":"https://customer-pod-A.org.machina.gg",
    "api_key":"<customer A pod api key>",
    "project_label":"Customer A"
  }'
```

The aggregator is stateless — running it N times against N pods
produces N reports.
