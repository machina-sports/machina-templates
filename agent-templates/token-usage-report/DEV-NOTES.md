# Dev notes — what the Machina workflow yml engine actually does

This document captures patterns / traps discovered while building
`token-usage-report` (2026-05-20 session). Future contributors:
read this BEFORE editing the workflow yml files. Every item here
cost real time to diagnose and the fix is non-obvious.

The system has THREE separately-evaluating contexts that touch your
workflow:

1. **YAML parser** — reads the file, builds a dict
2. **`context-variables` substitutor** — replaces `$TEMP_CONTEXT_VARIABLE_*` / `$MACHINA_CONTEXT_VARIABLE_*` with vault values, ONLY inside the `context-variables` block scoped by connector name
3. **`inputs` / `outputs` expression evaluator** — runs each value through Python `eval()` against the workflow context dict (`$` is the context, `.get()` is a method on it)

Most painful-bug-of-the-day patterns trace to confusing layer 2 with layer 3.

---

## 1. `$TEMP_CONTEXT_VARIABLE_*` substitution is scoped by connector name

ONLY this substitutes:

```yaml
context-variables:
  resend:                                     # ← matches a CONNECTOR named "resend"
    api_key: "$TEMP_CONTEXT_VARIABLE_RESEND_API_KEY"   # ← substituted when that connector fires
```

These do NOT substitute (you get the literal string `$NAME...`):

```yaml
inputs:
  api_key: "$.get('api_key', '$TEMP_CONTEXT_VARIABLE_RESEND_API_KEY')"   # ← default is just a Python string literal
  webhook_url: "$TEMP_CONTEXT_VARIABLE_SLACK_WEBHOOK_URL"               # ← parsed as a Python expression, $ is invalid syntax → 'invalid syntax' error
```

**The substituted secret then lands in the workflow context AS THE
KEY NAME under context-variables.** Subsequent tasks read it via
`$.get('api_key')` — the `resend.` prefix doesn't appear in the
context, just the leaf field name.

This is the only practical way to get a vault secret into a workflow
without baking it into the cron's `--inputs` block.

---

## 2. Workflow input expressions are Python `eval()` — bare strings break

```yaml
inputs:
  template: "metrics-report"     # ← FAILS: tries to evaluate `metrics - report`
  page_size: "Letter"            # ← FAILS: NameError: name 'Letter' is not defined
```

Wrap literals in single quotes INSIDE the outer yml double quotes:

```yaml
inputs:
  template: "'metrics-report'"   # ← OK: Python string literal
  page_size: "'Letter'"          # ← OK
  to: "['delivered@resend.dev']" # ← OK: list literal
```

Pattern confirmed in production via `pdf-generator/pdf-generator.yml`:
`cache_control: "'public, max-age=300'"`.

---

## 3. `type: "mapping"` task ≠ inline transformation

`type: mapping` references a REGISTERED mapping document in the pod's
mongo. If you don't have one with that name, you get `Mapping id not
found` and the whole workflow fails with the opaque error string
`'error'` at the workflow level.

For inline transformations, just put the expressions in the next
`type: "connector"` task's `inputs` block. That's what we did for
recipient-list parsing in `send-email.yml`:

```yaml
inputs:
  to: "[a.strip() for a in $.get('email_to', '').split(',') if a.strip()]"
```

List comprehensions, conditionals, f-strings all work as input
expressions because they're all valid Python.

---

## 4. `type: "workflow"` sub-workflow tasks are ASYNC

When task `type: workflow` dispatches a sub-workflow, it returns a
`run_id` immediately — it does NOT block and return the sub-workflow's
outputs synchronously. So you can't do:

```yaml
- type: workflow
  workflow: { name: send-email }
  outputs:
    message_id: "$.get('message_id')"   # ← will be null; sub-workflow's outputs aren't populated yet
```

**Solution:** call the underlying connector DIRECTLY from your
workflow. That's why `token-usage-report.yml` has 5 `type: connector`
tasks in a row (aggregate-tokens → render-pdf → upload-pdf →
send-email → post-slack) instead of calling the `send-email` and
`slack-post-message` wrapper workflows. The wrappers exist as
standalone entry points (call from `/workflow/execute/send-email`)
but aren't useful as sub-workflows in a chain.

Confirmed pattern: `cli-workflow-run` uses `type: workflow` to dispatch
asynchronously and reads back ONLY a `run_id` — not outputs.

---

## 5. Connector return `data` field spreads into workflow context root

A pyscript connector returns:

```python
return {
    "status": True,
    "data": {"id": "abc123", "from": "...", "created_at": "..."},
}
```

After that connector task fires, the workflow context exposes the
`data` dict's keys AT THE ROOT, not nested:

```yaml
outputs:
  message_id: "$.get('id')"                       # ← WORKS
  message_id_nested: "$.get('data', {}).get('id')" # ← returns None — there's no 'data' key in workflow context
```

The same applies to ALL fields in the connector's `data` dict.
Workflow context after the call effectively becomes:
`{...previous_context, ...connector.data}`.

**Implication for designing pyscript returns:** if you want field X
accessible to downstream tasks, put it directly in `data: {X: ...}`.
Don't nest further — `data: {nested: {X: ...}}` won't be readable.

Confirmed via debugging the resend wrapper — `$.get('data', {}).get('id')`
returned None even though Resend's response WAS `{"id": "..."}`. Then
`$.get('id')` worked.

---

## 6. `restapi` connector Bearer auth can't be prefix-templated

The restapi connector's `context-variables` substitution only handles
single-token replacement:

```yaml
context-variables:
  resend:
    Authorization: "$TEMP_CONTEXT_VARIABLE_RESEND_API_KEY"   # ← becomes literal "re_xxxxx" (no prefix added)
```

You CAN'T do:

```yaml
    Authorization: "Bearer $TEMP_CONTEXT_VARIABLE_RESEND_API_KEY"   # ← becomes literal "Bearer $TEMP_CONTEXT_VARIABLE_..." with NO substitution
```

Workarounds tried:

1. **Store the secret WITH the prefix** (`Bearer re_xxxxx` in vault) —
   works but feels hacky and breaks if anyone updates the vault
   thinking it's just a raw key.
2. **Pyscript connector** that adds the prefix in code — chosen path
   for both `resend` and `slack-webhook` connectors in this template.

Pyscript connectors trade off OpenAPI nicety for full control over
headers, body shape, error handling, and the response envelope. For
anything beyond the simplest `apiKey-in-header` auth, just use pyscript.

---

## 7. Output `message_id is not None and 'executed' or 'failed'` is FRAGILE

This idiom appears all over the codebase:

```yaml
outputs:
  workflow-status: "$.get('message_id') is not None and 'executed' or 'failed'"
```

It works as long as the truth value of the FIRST operand is a string
truthy after `and`. If `message_id` is `False` or `0`, you get
`'failed'` even when the operation succeeded. Use the equivalent
Python ternary for clarity:

```yaml
workflow-status: "'executed' if $.get('message_id') is not None else 'failed'"
```

---

## 8. High-volume pods need EARLY-EXIT pagination

The pod's `/execution/workflow-search` endpoint returns newest-first
by default. With `page_size_cap=5000`, my first version pulled the
first 5000 rows of a 180k-row table and filtered client-side — slow,
inaccurate (truncated billing), and unreliable (timed out at 60s
curl ceilings).

Fix in `_fetch_executions()`:

- Increase `per_page` from 200 → **5000** (3x latency only, 25x throughput because mongo cursor cost dominates response build cost)
- Add early-exit: when a full page is older than `since_iso` AND no rows matched, stop paginating
- `max_pages=20` ceiling = 100k rows per source — even sbot-prd weekly fits

Benchmarks on sbot-prd (180k execs, 7-day window):
  per_page=500   2.2s/call, ~1.4d covered/call → ~5 pages × 2.2s = 11s per source
  per_page=2000  1.7s/call, ~6.8h covered → 25 pages × 1.7s = 42s per source
  per_page=5000  2.1s/call, ~37h covered → 5 pages × 2.1s = 10s per source ← sweet spot

For high-volume pods with proper window early-exit: ~30s end-to-end
for single-pod, ~2-3 min for org-wide 6 pods serial.

---

## 9. The `pdf-generator` template ships with a RUNAWAY AGENT

`agent-templates/pdf-generator/agent.yml` has `config-frequency: 0`.
The COMMENT says this disables scheduling, but the LEGACY scheduler
treats `0` as "fire every tick" (5-second loop). After a fresh
install you get 300+ runs of the agent in 23 minutes — burning
compute + spamming google-genai with errors.

**Workaround:** after installing `agent-templates/pdf-generator`,
immediately `DELETE /agent/<pdf-generator-agent-id>`. The
`pdf-generator` workflow + connector still work — you just don't
need the agent wrapper, since the cron-scheduled agents in THIS
template call the workflow directly.

This is a bug in the upstream pdf-generator template, NOT in
`token-usage-report`. Filed as a follow-up but kept the workaround
documented here.

---

## 10. Customer pod API keys are NOT in any cluster-accessible DB

The Factory Postgres has hashed keys only (key_hash + key_prefix in
`api_keys` table). Each customer pod's own Mongo doesn't store raw
keys either. The raw API tokens are issued by the Machina control
plane (outside the cluster) and only the user / Studio admin can
mint them.

**Implication for the reports pod pattern:** API keys for every
customer pod must be passed INLINE in the cron-agent's workflow
inputs. They can't be auto-discovered. When adding a new customer
pod to monitor:

1. Mint a key via Studio UI on that customer pod
2. Drop it into the agent definition's `workflows[0].inputs.api_key`
3. PUT the updated agent

This is why the reports pod has 11 agents each with the customer
pod's key baked into its workflow inputs.

---

## 11. The aggregate-tokens task REWRITES `project_label` in workflow context

This is a deliberate naming trick so PDF title + email subject + Slack
text all read "Entain · SBOT Production" instead of "SBOT Production"
without us having to compose the combined string 3 times:

```yaml
# in aggregate-tokens task:
inputs:
  project_label: "f\"{($.get('org_label') + ' · ') if $.get('org_label') else ''}{$.get('project_label')}\""
```

The expression's RESULT (`"Entain · SBOT Production"`) lands in
workflow context as the new `project_label`. Downstream tasks
(send-email, post-slack) just use `$.get('project_label')` and get
the combined form for free.

**The catch:** downstream MUST NOT re-prepend `org_label`. We did
that initially and got "Entain · Entain · Entain · SBOT Production".
Fix is documented in `token-usage-report.yml` comments inline.

---

## Quick checklist before editing workflow yml

- [ ] Every string literal in an `inputs:` value is wrapped in single quotes (`"'metrics-report'"`)
- [ ] Vault secrets reach the workflow via `context-variables` scoped by connector name, NOT via `$.get` defaults
- [ ] Connector output extraction reads keys at the ROOT level (`$.get('id')`), NOT nested under `data` (`$.get('data', {}).get('id')`)
- [ ] Sub-workflow calls (`type: workflow`) are USED ONLY for async fire-and-forget; for synchronous results, call the underlying connector directly
- [ ] No `type: mapping` task unless you've ALSO registered a mapping document with that name
- [ ] If reading a vault secret as part of a Bearer auth header — use a pyscript connector, not restapi
- [ ] Pagination over high-volume tables uses `per_page=5000` + `max_pages=20` + early-exit on out-of-window pages
