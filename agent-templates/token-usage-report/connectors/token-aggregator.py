"""Token-usage aggregator connector.

Queries the host pod's own /execution/workflow-search and
/execution/agent-search endpoints over a configurable window (default 7
days), groups the results by name, and returns a payload shaped EXACTLY
for pdf-generator's `metrics-report` template — title, period, intro,
summary_cards, sections (table / stats / bullets), notes, footer.

Why this exists as a separate connector instead of a workflow task
chain: the aggregation is non-trivial (windowed grouping, per-day
buckets, week-over-week deltas, percentile math). Doing it in yml via
mapping tasks would balloon into 20+ steps with brittle string
expressions. Python is the right tool, and a pyscript connector keeps
it self-contained — no pymongo, no direct DB access, just HTTP back
into the same pod that's running it.

Inputs (all optional except api_base_url + api_key):
    api_base_url     pod's own public URL (e.g.
                     https://entain-organization-sports-interaction-v2.org.machina.gg)
    api_key          x-api-token for the same pod
    period_mode      one of:
                       "previous_week"  — last completed Mon-Sun (UTC)
                                          [recommended for Monday cron]
                       "previous_month" — last completed calendar month
                                          [recommended for 1st-of-month cron]
                       "rolling_days"   — last N days from now
                                          [requires period_days]
                     default: "previous_week"
    period_days      window size when period_mode == "rolling_days",
                     default 7. Ignored for previous_week / previous_month.
    project_label    display name for the report header
    page_size_cap    max executions to scan per source (default 5000;
                     bumps over this paginate)
    include_failed   include failed executions in token totals? default True
    brand_color      hex accent color for downstream PDF render

Returns the metrics-report payload + a few raw fields callers might
want (total_tokens, total_runs, period_from, period_to) so the
calling workflow can branch on emptiness without re-parsing the
nested structure.

Defensive: if either endpoint 404s or returns a non-200 the aggregator
falls back to an empty-but-valid metrics-report payload — the downstream
PDF render still produces a one-page "no executions in window" report
instead of crashing the whole chain.
"""

from __future__ import annotations

import json
import statistics
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _http_post(url, headers, body, timeout=30):
    """POST JSON, return parsed dict. Never raises — wraps network
    errors as {'_error': '...'} so callers can branch on it."""
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode("utf-8", errors="replace")
        except Exception:
            body_text = ""
        return {"_error": f"HTTP {e.code}", "_body": body_text[:300]}
    except urllib.error.URLError as e:
        return {"_error": f"URL error: {e.reason}"}
    except json.JSONDecodeError as e:
        return {"_error": f"JSON decode: {e}"}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def _parse_row_date(row):
    """Best-effort parse of an execution row's timestamp. Returns a
    tz-aware UTC datetime or None."""
    raw = row.get("date") or row.get("finished_time") or ""
    if not raw:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(str(raw).split("+")[0].strip("Z"), fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (ValueError, AttributeError):
            continue
    return None


def _fetch_executions(base_url, api_key, endpoint, since_iso, until_iso, page_size_cap):
    """Page through one of /execution/workflow-search or
    /execution/agent-search.

    Critical perf note for high-volume pods (sbot-prd has 180k+ execs):
    pages are returned newest-first. Once a full page is OLDER than
    `since_iso` (i.e. all rows fall outside the window), we abort
    pagination — no point pulling every historical row just to filter
    it out client-side. This early-exit is what makes the aggregator
    usable against production pods.

    `page_size_cap` is a hard ceiling on COLLECTED matching rows; we
    stop accepting more once we've seen that many. Doesn't apply to
    skipped (pre-window) rows.
    """

    url = f"{base_url.rstrip('/')}/{endpoint}"
    headers = {
        "x-api-token": api_key,
        "content-type": "application/json",
    }

    try:
        since_dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
        until_dt = datetime.fromisoformat(until_iso.replace("Z", "+00:00"))
    except Exception:
        # Bad input window — fall back to last 7 days hard limit so we
        # don't paginate the whole table.
        since_dt = datetime.now(timezone.utc) - timedelta(days=7)
        until_dt = datetime.now(timezone.utc)

    collected = []
    page = 1
    # Big per_page is the most important perf knob — the search
    # endpoint is dominated by mongo-cursor + json-serialize overhead,
    # not network. Empirical sbot-prd timings:
    #   per_page=500   2.2s/call, 1.4d/call → 6 pages/week
    #   per_page=2000  1.7s/call, 6.8h/call → 25 pages/week
    #   per_page=5000  2.1s/call, 37h/call → 5 pages/week ← sweet spot
    # Using 5000 cuts the round trips by 10x.
    per_page = 5000
    # 20 pages × 5000 = 100k rows per source ceiling. Even
    # the busiest production pod weekly should fit. Early-exit on
    # date-window boundary bails earlier in the common case.
    max_pages = 20
    truncated_at_max_pages = False

    while len(collected) < page_size_cap and page <= max_pages:
        body = {
            "filters": {},
            "page": page,
            "page_size": per_page,
        }
        resp = _http_post(url, headers, body)
        if resp.get("_error"):
            return collected, resp["_error"]
        rows = resp.get("data") or []
        if not rows:
            break

        # Window filter + early-exit detection.
        last_row_date = None
        page_had_in_window = False
        for row in rows:
            parsed = _parse_row_date(row)
            if parsed is None:
                # Unparseable — keep it; we can't filter so don't filter.
                collected.append(row)
                continue
            if since_dt <= parsed <= until_dt:
                collected.append(row)
                page_had_in_window = True
            last_row_date = parsed if last_row_date is None else min(last_row_date, parsed)

        # If the OLDEST row on this page is already older than the
        # window AND none of the rows fell into the window, the rest
        # of the table is irrelevant — stop paginating.
        if last_row_date is not None and last_row_date < since_dt and not page_had_in_window:
            break

        # Last page reached.
        if len(rows) < per_page:
            break

        page += 1

    # Flag if we exited due to page ceiling rather than reaching the
    # end of the window — callers (the report payload) can surface
    # this so billing reads aren't silently truncated.
    if page > max_pages:
        truncated_at_max_pages = True

    return collected, ("max_pages_hit" if truncated_at_max_pages else None)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _row_tokens(row):
    """Extract total_tokens from an execution row. The shape is
    `execution_tokens: {prompt_tokens, completion_tokens, total_tokens}`
    but defensive against missing fields."""
    et = row.get("execution_tokens")
    if isinstance(et, dict):
        return int(et.get("total_tokens") or 0)
    if isinstance(et, (int, float)):
        return int(et)
    return 0


def _row_name(row):
    """Best effort to pull a readable identifier from the row."""
    return (
        row.get("name")
        or row.get("workflow_name")
        or row.get("agent_name")
        or row.get("_id", "")[:8]
        or "unnamed"
    )


# Alias _row_date → _parse_row_date for backward compat with the rest
# of the module (was a duplicate definition; consolidated).
_row_date = _parse_row_date


def _format_number(n):
    """Compact: 1.2K, 22.6M, 5B."""
    n = float(n)
    for unit, threshold in [("B", 1e9), ("M", 1e6), ("K", 1e3)]:
        if abs(n) >= threshold:
            return f"{n / threshold:.1f}{unit}".replace(".0", "")
    return f"{int(n):,}"


def _aggregate(rows, include_failed):
    """Group by name, sum tokens + counts. Returns a list of dicts
    sorted by total tokens descending."""
    by_name = {}
    for row in rows:
        if not include_failed and row.get("status") not in ("executed", "completed", "success"):
            continue
        name = _row_name(row)
        tokens = _row_tokens(row)
        if name not in by_name:
            by_name[name] = {"name": name, "runs": 0, "tokens": 0, "samples": []}
        by_name[name]["runs"] += 1
        by_name[name]["tokens"] += tokens
        by_name[name]["samples"].append(tokens)
    out = []
    for name, agg in by_name.items():
        avg = int(agg["tokens"] / agg["runs"]) if agg["runs"] > 0 else 0
        out.append({"name": name, "runs": agg["runs"], "tokens": agg["tokens"], "avg": avg, "samples": agg["samples"]})
    out.sort(key=lambda r: r["tokens"], reverse=True)
    return out


def _by_day(rows, since_dt, until_dt):
    """Bucket tokens per calendar day in UTC. Returns ordered list of
    {date, runs, tokens} for every day in the window — including zeros
    so the timeline doesn't have gaps."""
    days = {}
    cursor = since_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    end = until_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    while cursor <= end:
        days[cursor.strftime("%Y-%m-%d")] = {"runs": 0, "tokens": 0}
        cursor += timedelta(days=1)
    for row in rows:
        d = _row_date(row)
        if d is None:
            continue
        key = d.strftime("%Y-%m-%d")
        if key in days:
            days[key]["runs"] += 1
            days[key]["tokens"] += _row_tokens(row)
    return [{"date": k, "runs": v["runs"], "tokens": v["tokens"]} for k, v in sorted(days.items())]


# ---------------------------------------------------------------------------
# Window computation per period_mode
# ---------------------------------------------------------------------------


def _compute_window(period_mode, period_days, now):
    """Return (since, until, prev_since, prev_until, mode_label) for the
    given period_mode. All datetimes are UTC. The previous-window pair
    is used for week-over-week / month-over-month delta math — same
    length as the primary window, immediately preceding it."""

    if period_mode == "previous_month":
        # First day of THIS calendar month at 00:00:00 UTC
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Last day of PREVIOUS month at 23:59:59 UTC
        prev_month_end = this_month_start - timedelta(microseconds=1)
        # First day of PREVIOUS month
        prev_month_start = prev_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Month before THAT, for delta
        prev_prev_end = prev_month_start - timedelta(microseconds=1)
        prev_prev_start = prev_prev_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return prev_month_start, prev_month_end, prev_prev_start, prev_prev_end, "Monthly"

    if period_mode == "previous_week":
        # ISO weekday: Monday=1 ... Sunday=7. Last completed week is the
        # Monday-Sunday block strictly before this Monday.
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        days_since_monday = today_midnight.isoweekday() - 1
        this_monday = today_midnight - timedelta(days=days_since_monday)
        prev_sunday = this_monday - timedelta(microseconds=1)
        prev_monday = (prev_sunday - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        # Week before THAT, for delta
        prev_prev_sunday = prev_monday - timedelta(microseconds=1)
        prev_prev_monday = (prev_prev_sunday - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        return prev_monday, prev_sunday, prev_prev_monday, prev_prev_sunday, "Weekly"

    # rolling_days (default — backward compatible)
    since = now - timedelta(days=period_days)
    prev_since = since - timedelta(days=period_days)
    prev_until = since
    label = f"Last {period_days}d"
    return since, now, prev_since, prev_until, label


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def invoke_aggregate(request_data, *_, **__):
    """Connector entrypoint. The workflow engine calls
    `function(request_data)` where the actual workflow-level inputs live
    under request_data['params'] (or request_data['inputs'] in legacy
    callers). Mirror the unpack pattern from
    agent-templates/pdf-generator/connectors/pdf-generator.py:invoke_generate
    so workflow-style inputs reach us correctly.

    Falls back to top-level keys when called directly (e.g. from a
    Python smoke test that passes a flat dict). Returns the
    pdf-generator metrics-report payload PLUS the wrapper
    `status: True` the executor expects (see
    machina-client-api/core/connector/executor.py — `if not result or
    result.get("status") is not True` short-circuits to generic
    "Connector failed" with no message, which is what swallowed the
    real bug on first install)."""

    if isinstance(request_data, dict):
        inputs = request_data.get("params") or request_data.get("inputs") or request_data
    else:
        inputs = {}

    api_base_url = inputs.get("api_base_url") or ""
    api_key = inputs.get("api_key") or ""
    period_mode = inputs.get("period_mode") or "previous_week"
    period_days = int(inputs.get("period_days") or 7)
    project_label = inputs.get("project_label") or "Project"
    page_size_cap = int(inputs.get("page_size_cap") or 2000)
    include_failed = bool(inputs.get("include_failed", True))
    brand_color = inputs.get("brand_color") or "#0A2540"

    if not api_base_url or not api_key:
        return {
            "status": True,
            "data": {
                "data": _empty_payload(project_label, period_mode, period_days, brand_color, "Missing api_base_url or api_key — set TEMP_CONTEXT_VARIABLE_TOKEN_REPORT_API_BASE_URL and TEMP_CONTEXT_VARIABLE_TOKEN_REPORT_API_KEY in the vault."),
                "total_tokens": 0,
                "total_runs": 0,
                "total_tokens_prev": 0,
                "period_from": "",
                "period_to": "",
                "period_mode": period_mode,
                "mode_label": "Report",
                "brand_color": brand_color,
            },
        }

    now = datetime.now(timezone.utc)
    since, until, prev_since, prev_until, mode_label = _compute_window(period_mode, period_days, now)

    # --- Current window ------------------------------------------------
    wf_rows, wf_err = _fetch_executions(
        api_base_url, api_key, "execution/workflow-search",
        since.isoformat(), until.isoformat(), page_size_cap,
    )
    ag_rows, ag_err = _fetch_executions(
        api_base_url, api_key, "execution/agent-search",
        since.isoformat(), until.isoformat(), page_size_cap,
    )

    # --- Previous window (for period-over-period delta) ---------------
    wf_prev, _ = _fetch_executions(
        api_base_url, api_key, "execution/workflow-search",
        prev_since.isoformat(), prev_until.isoformat(), page_size_cap,
    )
    ag_prev, _ = _fetch_executions(
        api_base_url, api_key, "execution/agent-search",
        prev_since.isoformat(), prev_until.isoformat(), page_size_cap,
    )

    rows = wf_rows + ag_rows
    rows_prev = wf_prev + ag_prev

    total_tokens = sum(_row_tokens(r) for r in rows)
    total_runs = len(rows)
    total_tokens_prev = sum(_row_tokens(r) for r in rows_prev) or 0

    # Period-over-period delta. Avoid div-by-zero by printing absolute
    # when prev is 0. Delta noun matches the mode so the card reads
    # naturally ("vs prev week" / "vs prev month").
    delta_noun = {
        "previous_week": "prev week",
        "previous_month": "prev month",
        "rolling_days": "prev period",
    }.get(period_mode, "prev period")
    if total_tokens_prev > 0:
        delta_pct = ((total_tokens - total_tokens_prev) / total_tokens_prev) * 100
        delta_str = f"{delta_pct:+.0f}% vs {delta_noun}"
    elif total_tokens > 0:
        delta_str = f"first {delta_noun.replace('prev ', '')} with data"
    else:
        delta_str = ""

    avg_tokens_per_run = int(total_tokens / total_runs) if total_runs > 0 else 0

    # Percentile distribution of per-run token cost
    samples = [_row_tokens(r) for r in rows if _row_tokens(r) > 0]
    if samples:
        samples_sorted = sorted(samples)
        p50 = samples_sorted[len(samples_sorted) // 2]
        p95 = samples_sorted[min(len(samples_sorted) - 1, int(len(samples_sorted) * 0.95))]
        p_max = samples_sorted[-1]
    else:
        p50 = p95 = p_max = 0

    by_name = _aggregate(rows, include_failed)
    by_day = _by_day(rows, since, until)

    # Status breakdown
    status_counts = {}
    for r in rows:
        s = r.get("status") or "unknown"
        status_counts[s] = status_counts.get(s, 0) + 1
    success_rate = (
        100.0 * (status_counts.get("executed", 0) + status_counts.get("completed", 0) + status_counts.get("success", 0))
        / total_runs
    ) if total_runs > 0 else 0

    # Build metrics-report payload --------------------------------------
    # Period label adapts to mode:
    #   weekly:  "May 12 – May 18, 2026 (UTC)"
    #   monthly: "April 2026 (UTC)"
    #   rolling: "May 13 – May 20, 2026 (UTC)"
    if period_mode == "previous_month":
        period_str = f"{since.strftime('%B %Y')} (UTC)"
        intro_window = f"in {since.strftime('%B %Y')}"
    elif period_mode == "previous_week":
        period_str = f"{since.strftime('%b %-d')} – {until.strftime('%b %-d, %Y')} (UTC)"
        intro_window = f"in the week of {since.strftime('%b %-d')}"
    else:
        period_str = f"{since.strftime('%b %-d')} – {until.strftime('%b %-d, %Y')} (UTC)"
        intro_window = f"in the last {period_days} days"

    intro_parts = [
        f"{_format_number(total_tokens)} tokens consumed across {total_runs} runs {intro_window}."
    ]
    if by_name:
        top = by_name[0]
        share = (top["tokens"] / total_tokens * 100) if total_tokens > 0 else 0
        intro_parts.append(
            f"{share:.0f}% from `{top['name']}` ({_format_number(top['tokens'])} tokens, {top['runs']} runs)."
        )
    if wf_err or ag_err:
        intro_parts.append(
            f"Note: partial data — {wf_err or ag_err}. Some executions may be missing from this report."
        )

    summary_cards = [
        {"label": "Total tokens", "value": _format_number(total_tokens), "delta": delta_str},
        {"label": "Total runs", "value": f"{total_runs:,}"},
        {"label": "Avg tokens / run", "value": _format_number(avg_tokens_per_run)},
        {"label": "Success rate", "value": f"{success_rate:.0f}%"},
    ]

    sections = []

    # 1. By workflow/agent table — top 15, "others" bucket below
    if by_name:
        head = by_name[:15]
        tail_rows = by_name[15:]
        rows_for_table = [
            [r["name"], f"{r['runs']:,}", _format_number(r["tokens"]), _format_number(r["avg"])]
            for r in head
        ]
        if tail_rows:
            other_runs = sum(r["runs"] for r in tail_rows)
            other_tokens = sum(r["tokens"] for r in tail_rows)
            rows_for_table.append([
                f"… and {len(tail_rows)} others",
                f"{other_runs:,}",
                _format_number(other_tokens),
                "—",
            ])
        sections.append({
            "title": "By workflow / agent",
            "table": {
                "headers": ["Name", "Runs", "Tokens", "Avg/run"],
                "rows": rows_for_table,
            },
        })

    # 2. Per-day breakdown
    if by_day:
        sections.append({
            "title": "By day",
            "table": {
                "headers": ["Date", "Runs", "Tokens"],
                "rows": [
                    [d["date"], f"{d['runs']:,}", _format_number(d["tokens"])]
                    for d in by_day
                ],
            },
        })

    # 3. Distribution stats
    if samples:
        sections.append({
            "title": "Distribution (tokens per run)",
            "stats": [
                {"label": "p50", "value": _format_number(p50)},
                {"label": "p95", "value": _format_number(p95)},
                {"label": "max", "value": _format_number(p_max)},
            ],
        })

    # 4. Top 5 most expensive runs
    expensive = sorted(rows, key=_row_tokens, reverse=True)[:5]
    if expensive and _row_tokens(expensive[0]) > 0:
        sections.append({
            "title": "Top consuming runs",
            "bullets": [
                f"{_row_name(r)} — {_format_number(_row_tokens(r))} tokens ({(_row_date(r) or until).strftime('%b %-d %H:%M')})"
                for r in expensive
            ],
        })

    # 5. Status breakdown bullets when there are failures worth flagging
    failed_count = total_runs - sum(
        v for k, v in status_counts.items() if k in ("executed", "completed", "success")
    )
    if failed_count > 0:
        sections.append({
            "title": "Failures in window",
            "stats": [
                {"label": k, "value": f"{v:,}"} for k, v in sorted(status_counts.items())
            ],
        })

    notes = []
    if wf_err:
        notes.append(f"workflow-search partial: {wf_err}")
    if ag_err:
        notes.append(f"agent-search partial: {ag_err}")
    notes.append(f"Source: {api_base_url}/execution/{{workflow,agent}}-search")
    notes.append(f"Window: {since.isoformat()} → {until.isoformat()}")
    notes.append(f"Mode: {period_mode}")

    payload = {
        "title": f"{project_label} · {mode_label} Token Report",
        "period": period_str,
        "intro": " ".join(intro_parts),
        "summary_cards": summary_cards,
        "sections": sections,
        "notes": notes,
        "footer": f"Generated by token-usage-report · {now.strftime('%Y-%m-%d %H:%M UTC')}",
    }

    # Workflow engine spreads connector's `data` dict keys into the
    # task context root — so $.get('total_tokens') works, but
    # $.get('data', {}).get('total_tokens') returns None. Keep keys
    # at one level.
    result = {
        "status": True,
        "data": {
            "payload": payload,
            "total_tokens": total_tokens,
            "total_runs": total_runs,
            "total_tokens_prev": total_tokens_prev,
            "period_from": since.isoformat(),
            "period_to": until.isoformat(),
            "period_mode": period_mode,
            "mode_label": mode_label,
            "brand_color": brand_color,
        },
    }
    return result


# ---------------------------------------------------------------------------
# Multi-pod aggregation — for billing-grade reports that span an entire
# org. Takes a list of pod configs, queries each in turn, produces a
# hierarchical (org → project → workflow) metrics-report payload.
# ---------------------------------------------------------------------------


def invoke_aggregate_multi(request_data, *_, **__):
    """Roll up token usage across MULTIPLE pods into a single report.

    Inputs (under request_data['params'] or 'inputs'):

      org_label    — display name for the report header (e.g. "Entain")
      period_mode  — same as invoke_aggregate
      period_days  — same as invoke_aggregate
      brand_color  — hex accent for PDF
      pods         — list of {project_label, api_base_url, api_key} dicts.
                     Each entry is one customer pod to aggregate.
                     project_label appears as the per-pod row label in
                     the report; api_base_url + api_key authenticate
                     against that pod's /execution/* endpoints.

    Returns a payload shaped for pdf-generator's metrics-report layout
    with:

      - Title: "<org_label> · <Mode> Token Report (multi-pod)"
      - Summary cards: total tokens, total runs, total pods, avg/pod
      - Section "By project" (table): per-pod totals — runs, tokens,
        avg tokens/run, share of org total
      - Section "Top consuming workflows": top 15 across ALL pods
      - Section "By day": org-wide daily timeseries

    Each pod is queried in series; a per-pod fetch failure is logged
    as a `notes` entry but doesn't abort the report. Billing
    accountability requires we always emit something — partial data
    with explicit gaps is more useful than a hard failure.
    """

    if isinstance(request_data, dict):
        inputs = request_data.get("params") or request_data.get("inputs") or request_data
    else:
        inputs = {}

    org_label = inputs.get("org_label") or "Organization"
    period_mode = inputs.get("period_mode") or "previous_week"
    period_days = int(inputs.get("period_days") or 7)
    brand_color = inputs.get("brand_color") or "#FE4000"
    pods = inputs.get("pods") or []
    page_size_cap = int(inputs.get("page_size_cap") or 2000)
    include_failed = bool(inputs.get("include_failed", True))

    if not pods:
        return {
            "status": True,
            "data": {
                "payload": _empty_payload(org_label, period_mode, period_days, brand_color, "No pods configured — pass a non-empty `pods` array."),
                "total_tokens": 0,
                "total_runs": 0,
                "total_pods": 0,
                "period_mode": period_mode,
            },
        }

    now = datetime.now(timezone.utc)
    since, until, prev_since, prev_until, mode_label = _compute_window(period_mode, period_days, now)

    per_pod_results = []
    org_total_tokens = 0
    org_total_runs = 0
    org_total_tokens_prev = 0
    all_rows = []         # for cross-pod top-workflows ranking
    all_rows_by_pod = {}  # for cross-pod per-day rollup
    notes = []

    for pod_cfg in pods:
        project_label = pod_cfg.get("project_label") or pod_cfg.get("name") or "(unnamed)"
        api_base_url = pod_cfg.get("api_base_url") or ""
        api_key = pod_cfg.get("api_key") or ""
        if not api_base_url or not api_key:
            notes.append(f"{project_label}: skipped — missing api_base_url or api_key")
            per_pod_results.append({
                "project_label": project_label,
                "runs": 0,
                "tokens": 0,
                "tokens_prev": 0,
                "error": "missing credentials",
            })
            continue

        # Current window
        wf_rows, wf_err = _fetch_executions(
            api_base_url, api_key, "execution/workflow-search",
            since.isoformat(), until.isoformat(), page_size_cap,
        )
        ag_rows, ag_err = _fetch_executions(
            api_base_url, api_key, "execution/agent-search",
            since.isoformat(), until.isoformat(), page_size_cap,
        )

        # Previous window for delta
        wf_prev, _ = _fetch_executions(
            api_base_url, api_key, "execution/workflow-search",
            prev_since.isoformat(), prev_until.isoformat(), page_size_cap,
        )
        ag_prev, _ = _fetch_executions(
            api_base_url, api_key, "execution/agent-search",
            prev_since.isoformat(), prev_until.isoformat(), page_size_cap,
        )

        rows = wf_rows + ag_rows
        rows_prev = wf_prev + ag_prev
        # Annotate each row with its source pod so cross-pod rankings
        # can disambiguate same-named workflows running in different
        # projects (e.g. "wc-bracket-event-details" exists in both
        # sbot-stg and sports-interaction-v2 with different costs).
        for r in rows:
            r["_pod"] = project_label

        pod_tokens = sum(_row_tokens(r) for r in rows)
        pod_tokens_prev = sum(_row_tokens(r) for r in rows_prev)
        pod_runs = len(rows)

        org_total_tokens += pod_tokens
        org_total_runs += pod_runs
        org_total_tokens_prev += pod_tokens_prev

        all_rows.extend(rows)
        all_rows_by_pod[project_label] = rows

        per_pod_results.append({
            "project_label": project_label,
            "runs": pod_runs,
            "tokens": pod_tokens,
            "tokens_prev": pod_tokens_prev,
            "avg": int(pod_tokens / pod_runs) if pod_runs else 0,
            "error": wf_err or ag_err,
        })
        if wf_err:
            notes.append(f"{project_label}: workflow-search partial — {wf_err}")
        if ag_err:
            notes.append(f"{project_label}: agent-search partial — {ag_err}")

    # ---- Build metrics-report payload -----------------------------

    if period_mode == "previous_month":
        period_str = f"{since.strftime('%B %Y')} (UTC)"
    else:
        period_str = f"{since.strftime('%b %-d')} – {until.strftime('%b %-d, %Y')} (UTC)"

    # Org-level delta
    if org_total_tokens_prev > 0:
        delta_pct = ((org_total_tokens - org_total_tokens_prev) / org_total_tokens_prev) * 100
        org_delta_str = f"{delta_pct:+.0f}% vs prev period"
    elif org_total_tokens > 0:
        org_delta_str = "first period with data"
    else:
        org_delta_str = ""

    summary_cards = [
        {"label": "Total tokens", "value": _format_number(org_total_tokens), "delta": org_delta_str},
        {"label": "Total runs", "value": f"{org_total_runs:,}"},
        {"label": "Pods reporting", "value": f"{sum(1 for p in per_pod_results if not p.get('error') or p.get('runs', 0) > 0)} / {len(pods)}"},
        {"label": "Avg tokens / pod", "value": _format_number(org_total_tokens / max(1, len(pods)))},
    ]

    intro_parts = [
        f"{_format_number(org_total_tokens)} tokens consumed across {org_total_runs:,} runs in {len(pods)} {org_label} pods."
    ]
    if per_pod_results:
        # Top consumer pod
        top_pod = max(per_pod_results, key=lambda p: p.get("tokens", 0))
        if top_pod.get("tokens", 0) > 0:
            share = (top_pod["tokens"] / org_total_tokens * 100) if org_total_tokens > 0 else 0
            intro_parts.append(
                f"{share:.0f}% from `{top_pod['project_label']}` ({_format_number(top_pod['tokens'])} tokens)."
            )

    sections = []

    # 1. Per-project table (the most important section for billing)
    sorted_pods = sorted(per_pod_results, key=lambda p: p.get("tokens", 0), reverse=True)
    project_rows = []
    for p in sorted_pods:
        share = (p.get("tokens", 0) / org_total_tokens * 100) if org_total_tokens > 0 else 0
        project_rows.append([
            p["project_label"],
            f"{p.get('runs', 0):,}",
            _format_number(p.get("tokens", 0)),
            _format_number(p.get("avg", 0)),
            f"{share:.1f}%",
        ])
    sections.append({
        "title": "By project (billing breakdown)",
        "table": {
            "headers": ["Project", "Runs", "Tokens", "Avg/run", "Share"],
            "rows": project_rows,
        },
    })

    # 2. Top workflows across the org
    by_name = _aggregate(all_rows, include_failed)
    if by_name:
        head = by_name[:15]
        rows_for_table = [
            [r["name"], f"{r['runs']:,}", _format_number(r["tokens"]), _format_number(r["avg"])]
            for r in head
        ]
        if len(by_name) > 15:
            tail_runs = sum(r["runs"] for r in by_name[15:])
            tail_tokens = sum(r["tokens"] for r in by_name[15:])
            rows_for_table.append([
                f"… and {len(by_name) - 15} others",
                f"{tail_runs:,}",
                _format_number(tail_tokens),
                "—",
            ])
        sections.append({
            "title": "Top consuming workflows (org-wide)",
            "table": {
                "headers": ["Workflow", "Runs", "Tokens", "Avg/run"],
                "rows": rows_for_table,
            },
        })

    # 3. Per-day timeseries org-wide
    by_day = _by_day(all_rows, since, until)
    if by_day:
        sections.append({
            "title": "By day (org-wide)",
            "table": {
                "headers": ["Date", "Runs", "Tokens"],
                "rows": [
                    [d["date"], f"{d['runs']:,}", _format_number(d["tokens"])]
                    for d in by_day
                ],
            },
        })

    # 4. Distribution stats org-wide
    samples = [_row_tokens(r) for r in all_rows if _row_tokens(r) > 0]
    if samples:
        samples.sort()
        p50 = samples[len(samples) // 2]
        p95 = samples[min(len(samples) - 1, int(len(samples) * 0.95))]
        p_max = samples[-1]
        sections.append({
            "title": "Distribution (tokens per run, org-wide)",
            "stats": [
                {"label": "p50", "value": _format_number(p50)},
                {"label": "p95", "value": _format_number(p95)},
                {"label": "max", "value": _format_number(p_max)},
            ],
        })

    # 5. Top consuming individual runs (highest single costs)
    expensive = sorted(all_rows, key=_row_tokens, reverse=True)[:5]
    if expensive and _row_tokens(expensive[0]) > 0:
        sections.append({
            "title": "Top consuming runs",
            "bullets": [
                f"{r.get('_pod', '?')} · {_row_name(r)} — {_format_number(_row_tokens(r))} tokens ({(_row_date(r) or until).strftime('%b %-d %H:%M')})"
                for r in expensive
            ],
        })

    notes.append(f"Window: {since.isoformat()} → {until.isoformat()}")
    notes.append(f"Mode: {period_mode}")
    notes.append(f"Pods queried: {len(pods)}")

    payload = {
        "title": f"{org_label} · {mode_label} Token Report",
        "period": period_str,
        "intro": " ".join(intro_parts),
        "summary_cards": summary_cards,
        "sections": sections,
        "notes": notes,
        "footer": f"Generated by token-usage-report (multi-pod) · {now.strftime('%Y-%m-%d %H:%M UTC')}",
    }

    return {
        "status": True,
        "data": {
            "payload": payload,
            "total_tokens": org_total_tokens,
            "total_runs": org_total_runs,
            "total_tokens_prev": org_total_tokens_prev,
            "total_pods": len(pods),
            "pods_reporting": sum(1 for p in per_pod_results if not p.get("error") or p.get("runs", 0) > 0),
            "period_from": since.isoformat(),
            "period_to": until.isoformat(),
            "period_mode": period_mode,
            "mode_label": mode_label,
            "brand_color": brand_color,
            "per_pod": per_pod_results,
        },
    }


def _empty_payload(project_label, period_mode, period_days, brand_color, reason):
    """Return a valid-but-empty metrics-report payload so the downstream
    PDF render still produces a one-page report instead of crashing."""
    now = datetime.now(timezone.utc)
    since, until, _, _, mode_label = _compute_window(period_mode, period_days, now)
    if period_mode == "previous_month":
        period_str = f"{since.strftime('%B %Y')} (UTC)"
    else:
        period_str = f"{since.strftime('%b %-d')} – {until.strftime('%b %-d, %Y')} (UTC)"
    return {
        "title": f"{project_label} · {mode_label} Token Report",
        "period": period_str,
        "intro": f"No data: {reason}",
        "summary_cards": [
            {"label": "Total tokens", "value": "0"},
            {"label": "Total runs", "value": "0"},
        ],
        "sections": [],
        "notes": [reason],
        "footer": f"Generated by token-usage-report · {now.strftime('%Y-%m-%d %H:%M UTC')}",
    }
