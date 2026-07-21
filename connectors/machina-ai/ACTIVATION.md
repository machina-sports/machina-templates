# Activating the Claude on Vertex route (`vertex_anthropic`)

The `vertex_anthropic` provider ships **dormant** (`enabled: false`). Nothing routes
to Claude until an environment opts in. This is the Stage 0 activation runbook for
the Entain Gemini→Claude migration (ClickUp 86ajmxm3u).

## 0. Prerequisites (both must be live)

| Change | PR |
| --- | --- |
| `vertex_anthropic` provider + adapter (this connector) | machina-templates #292 |
| `anthropic` package in the runtime | machina-client-api #326 |

Deploy order is not strict (the route is dormant), but **both must be live before
you flip `enabled`** — the adapter builds `anthropic.AnthropicVertex` at route time.

1. Merge + deploy **machina-client-api #326** (new image ships `anthropic`).
2. Merge **machina-templates #292**, then re-import the `machina-ai` connector into
   the target pod so the new provider/adapter is loaded.

No new secret is required: the route reuses the existing Vertex service-account
(`TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL` + `_PROJECT_ID`), since Model Garden
bills Claude under the GCP project.

## 1. Validate the model ids in the target Vertex project

`allowed_models.chat` is seeded with the canonical current-gen bare ids
(`claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-sonnet-5`, `claude-opus-4-8`).
Model Garden enablement is **per-project** — confirm which are enabled in the target
project/region (`global`) before relying on them, e.g.:

```bash
gcloud ai model-garden models list --project <ENTAIN_VERTEX_PROJECT> \
  --region global | grep -i claude
```

Override the list per environment if it differs (see §2). If a requested id is not
enabled, the route returns a sanitized `provider_unavailable` / `provider_bad_response`.

## 2. Enable (per environment)

Add to the environment's `MACHINA_AI_ROUTER_CONFIG_JSON` (layered
repository < project < organization < runtime):

```json
{
  "providers": {
    "vertex_anthropic": {
      "enabled": true
    }
  }
}
```

To pin the exact validated ids for this env, also set
`providers.vertex_anthropic.allowed_models.chat` to that list.

## 3. Smoke — Haiku and Sonnet, with receipts

The authoritative check is a direct connector call: the router returns the full
envelope, so you can read `metadata.selected_provider` / `selected_model` /
`route_reason`. Payload:

```json
{ "command": "invoke_prompt", "provider": "vertex_anthropic",
  "model": "claude-haiku-4-5", "prompt": "Reply in one sentence and name the model." }
```

Run once for `claude-haiku-4-5` and once for `claude-sonnet-5`. Expected receipt:

```json
{ "status": true, "message": "Model loaded.",
  "metadata": { "selected_provider": "vertex_anthropic",
                "selected_model": "claude-haiku-4-5",
                "route_reason": "explicit_provider", "fallback_used": false } }
```

A repeatable workflow probe ships alongside this file:
`test-smoke-claude-vertex.yml` (Haiku; swap `model` to `claude-sonnet-5` for
Sonnet). The repository policy lint (`scripts/check-machina-ai-policy.py`) allows
committed `machina-ai` workflows to use `provider: vertex_anthropic` with the
approved Claude ids.

## 4. First cutover (Stage 2) — one config flip, no workflow edits

Redirect all chat off the Gemini repository default onto Claude via a capability
remap (Haiku for chat; point reasoning workflows at `claude-sonnet-5` explicitly or
with a second remap):

```json
{
  "providers": { "vertex_anthropic": { "enabled": true } },
  "remaps": {
    "capabilities": {
      "chat": { "provider": "vertex_anthropic", "model": "claude-haiku-4-5" }
    }
  }
}
```

Receipts then show `route_reason: "remap:capability:chat"`.

## 5. Rollback

Instant, config-only — remove the remap and/or set
`providers.vertex_anthropic.enabled: false`. All traffic falls back to the Gemini
repository default; no workflow or code change is needed.
