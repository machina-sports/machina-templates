# Token Usage Report

Cron-driven token-consumption reports for Machina pods. Two workflows
ship in this template:

| Workflow | Scope | Use case |
|---|---|---|
| `token-usage-report` | One pod | Per-project weekly/monthly billing |
| `org-token-report` | N pods | End-of-month org-wide rollup that lands the customer invoice |

Both flow: query `/execution/*` → aggregate by name + day +
distribution → render PDF via the existing `pdf-generator` connector
→ upload to GCS → email (Resend) + Slack (incoming webhook).

## Cadence patterns

Schedule a wrapper agent per pod and per cadence — that's the
pattern proven on the `machina-reports` pod (11 agents covering all
Entain pods + an org-wide monthly rollup):

| Cron | Mode | What it covers |
|---|---|---|
| `0 9 * * MON` | `previous_week` | Last completed Monday → Sunday (UTC) |
| `0 9 1 * *` | `previous_month` | Last completed calendar month (e.g. April 2026) |

The `period_mode` input picks which window the aggregator computes —
not a separate workflow per cadence.

## Required vault keys (on the pod that RUNS the report — usually a dedicated reports pod)

| Key | What |
|---|---|
| `TEMP_CONTEXT_VARIABLE_RESEND_API_KEY` | Resend API key (NO "Bearer " prefix — the pyscript adds it) |
| `TEMP_CONTEXT_VARIABLE_SLACK_WEBHOOK_URL` | Full webhook URL `https://hooks.slack.com/services/T.../B.../...` |
| `TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY` | GCS service-account JSON (whole file content) |
| `TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME` | GCS bucket name |

Customer pod credentials (`api_base_url` + `api_key` per pod) are
passed INLINE in the cron schedule's inputs — they're NOT vault
entries on the reports pod. That keeps the reports pod stateless: the
list of pods it watches lives in its agent definitions, not in vault.

## Single-pod cron agent — full example

```bash
curl -X POST 'https://<reports-pod>.org.machina.gg/agent' \
  -H 'x-api-token: <reports-pod-key>' \
  -H 'content-type: application/json' \
  -d '{
    "name": "token-report-entain-sbot-prd-weekly",
    "title": "Token Report · Entain · SBOT Production · Weekly",
    "description": "Cron-scheduled token-usage-report wrapper.",
    "status": "active",
    "context": {},
    "context-variables": {},
    "workflows": [{
      "name": "token-usage-report",
      "inputs": {
        "period_mode": "previous_week",
        "period_days": 7,
        "api_base_url": "https://entain-organization-sbot-prd.org.machina.gg",
        "api_key": "<customer-pod-key>",
        "org_label": "Entain",
        "project_label": "SBOT Production",
        "brand_color": "#FE4000",
        "email_from": "Machina Reports <onboarding@resend.dev>",
        "email_to": "billing@yourdomain.com"
      },
      "outputs": {
        "email_message_id": "$.get(\"email_message_id\")",
        "pdf_url": "$.get(\"pdf_url\")"
      }
    }],
    "jobs": [{
      "name": "tick",
      "type": "agent",
      "target": "token-report-entain-sbot-prd-weekly",
      "cron": "0 9 * * MON",
      "enabled": true
    }]
  }'
```

The job is self-referencing (`type: agent, target: <its-own-name>`):
the cron tick dispatches THIS agent, which runs its `workflows[]`
with the inputs baked above.

## Org-wide rollup — full example

```bash
curl -X POST 'https://<reports-pod>.org.machina.gg/agent' \
  -H 'x-api-token: <reports-pod-key>' \
  -H 'content-type: application/json' \
  -d '{
    "name": "token-report-entain-org-monthly",
    "title": "Token Report · Entain · Org-wide · Monthly",
    "status": "active",
    "context": {},
    "context-variables": {},
    "workflows": [{
      "name": "org-token-report",
      "inputs": {
        "period_mode": "previous_month",
        "period_days": 30,
        "org_label": "Entain",
        "pods": [
          {"project_label": "SBOT Production",       "api_base_url": "https://entain-organization-sbot-prd.org.machina.gg",              "api_key": "..."},
          {"project_label": "SBOT Staging",          "api_base_url": "https://entain-organization-sbot-stg.org.machina.gg",              "api_key": "..."},
          {"project_label": "Sports Interaction v2", "api_base_url": "https://entain-organization-sports-interaction-v2.org.machina.gg", "api_key": "..."},
          {"project_label": "Botandwin Production",  "api_base_url": "https://entain-organization-botandwin-production.org.machina.gg", "api_key": "..."},
          {"project_label": "Botandwin Staging",     "api_base_url": "https://entain-organization-botandwin-stg.org.machina.gg",         "api_key": "..."},
          {"project_label": "SIA Dev",               "api_base_url": "https://entain-organization-sia-dev.org.machina.gg",               "api_key": "..."}
        ],
        "brand_color": "#FE4000",
        "email_from": "Machina Reports <onboarding@resend.dev>",
        "email_to": "billing@yourdomain.com"
      },
      "outputs": {
        "email_message_id": "$.get(\"email_message_id\")",
        "pdf_url": "$.get(\"pdf_url\")",
        "total_tokens": "$.get(\"total_tokens\")",
        "pods_reporting": "$.get(\"pods_reporting\")"
      }
    }],
    "jobs": [{
      "name": "tick",
      "type": "agent",
      "target": "token-report-entain-org-monthly",
      "cron": "0 9 1 * *",
      "enabled": true
    }]
  }'
```

The org-wide PDF contains:

- 4 KPI cards (total tokens, total runs, pods reporting, avg/pod)
- **"By project (billing breakdown)"** — runs / tokens / avg / share% per pod (billing-grade)
- "Top consuming workflows (org-wide)" — top 15 across all pods + an "others" bucket
- "By day (org-wide)" — daily timeseries
- "Distribution (org-wide)" — p50 / p95 / max
- "Top consuming runs" — 5 most expensive single executions
- Notes section flagging any pod that returned partial data + the source URLs

## Performance — high-volume pods

The pyscript aggregator hits the customer pod's `/execution/*` over
HTTPS. Tuned defaults that survive production pods (sbot-prd at
180k+ executions, 1500-3000 runs/day):

| Knob | Value | Why |
|---|---|---|
| `per_page` | 500 (token-usage-report) / 5000 (multi-pod path) | 5000 cuts round trips ~10x without inflating per-call latency much |
| `max_pages` | 20 | 100k rows per source ceiling — fits any pod's weekly window |
| Early-exit | when a full page is older than the window AND no rows matched | Stops as soon as we cross the lower bound. Without this, paginating sbot-prd would never finish. |
| Truncation flag | `max_pages_hit` returned as the `err` value | Surfaces in the report's intro + notes so billing reads never silently truncate |

Single sbot-prd weekly report runs end-to-end in ~30s. Org-wide
across 6 pods runs in ~2-3 min serial. Acceptable for cron.

## How to inspect / trigger a report on demand

```bash
# Manually trigger a scheduled agent (dispatch it once, immediately)
curl -X POST 'https://<reports-pod>.org.machina.gg/agent/execute/token-report-entain-sbot-prd-weekly' \
  -H 'x-api-token: <reports-pod-key>' \
  -H 'content-type: application/json' \
  -d '{}'

# Or invoke the workflow directly with custom inputs
curl -X POST 'https://<reports-pod>.org.machina.gg/workflow/execute/token-usage-report' \
  -H 'x-api-token: <reports-pod-key>' \
  -H 'content-type: application/json' \
  -d '{ "period_mode": "rolling_days", "period_days": 30, "api_base_url": "...", "api_key": "...", "org_label": "...", "project_label": "...", "email_from": "...", "email_to": "..." }'

# List recent executions
curl -X POST 'https://<reports-pod>.org.machina.gg/execution/workflow-search' \
  -H 'x-api-token: <reports-pod-key>' \
  -H 'content-type: application/json' \
  -d '{"filters":{"name":"token-usage-report"},"page_size":5}'
```

## Multi-tenant pattern (recommended)

Run ONE dedicated reports pod (the `machina-reports/reports` setup
proven in production). The reports pod:

- Stays small (1-2 active workflows + the connectors + a dozen
  scheduled wrapper agents)
- Never touches customer data beyond the read-only `/execution/*`
  fetch
- Has its own Slack channel + email destination — operators see all
  customer pods' usage in one place
- Each customer pod gets a dedicated cron-agent on the reports pod,
  with the customer pod's own API key baked in as input
- Compromise of the reports pod's key DOES NOT compromise customer
  pods — the customer keys are scoped to read execution history only

For ~10 customer pods × 2 cadences (weekly + monthly), that's 20
cron agents on the reports pod. Plus an N-th "org-wide" rollup per
org for billing handoff. The list above for Entain shows the pattern
in production.

## Customizing

| Knob | Where |
|---|---|
| Email recipients | `email_to` in agent's workflow inputs — comma-separated for multiple addresses |
| Slack channel | Different vault entry `TEMP_CONTEXT_VARIABLE_SLACK_WEBHOOK_URL` per channel; OR run multiple reports pods if you need fan-out across many channels |
| PDF accent color | `brand_color` input (defaults to `#FE4000` Sports Interaction orange) |
| Aggregation rules | Edit `_aggregate()` / `_row_name()` in `connectors/token-aggregator.py` — for example to roll all `wc-bracket-*` workflows into one row |
| Sections in the PDF | Edit `sections` list in `invoke_aggregate()` / `invoke_aggregate_multi()` — table / stats / bullets layouts available via the metrics-report template's schema |

## Known limitations + workarounds

| Issue | Mitigation |
|---|---|
| HTTPS self-call from inside the pod is flaky (DNS doesn't always resolve back to the pod's own ingress) | Single-pod reports use `http://localhost:5003` as the API base URL — pyscript runs in the same pod as the client-api |
| Customer pod API keys live outside the cluster (control plane), can't be auto-discovered | Provision keys via Studio UI per customer pod, bake them into the cron agent's inputs |
| Cron-agent inputs are visible in any `agent/search` response | Reports pod's `x-api-token` should be tightly scoped — anyone with it can read all customer keys baked in agent configs. Mint a read-only key for the reports pod's operators. |
| Email subject + Slack text combine `org_label` + `project_label` exactly once — the aggregate-tokens task rewrites `project_label` in workflow context to the combined form | Don't re-prepend `org_label` in downstream tasks; the combined form sits in `project_label` after aggregate-tokens runs |
| The pdf-generator template's own SUB-WORKFLOW (`pdf-generator.yml`) is buggy under the workflow engine's data-spread behavior — its internal `upload-pdf` step's condition reads `$.get('data', {}).get('data_uri')` which returns None | This template calls the `pdf-generator` and `google-storage` CONNECTORS DIRECTLY in its own workflow — bypassing the broken sub-workflow chain |
