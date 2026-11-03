# Machina AI Router Activation

## Repository default

`machina-ai` defaults chat and search-answer requests to the Vertex AI model ID
`gemini-3.5-flash-lite`. The `default`, `balanced`, `quality`, `cheap`, and
`long_context` chat profiles use the same model; `fast`, `private_runtime`, and
`open_source` retain their provider-specific routes. The model ID and GA availability
are sourced from the [Google Cloud Vertex AI model documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-5-flash-lite).

The installable non-production probe is `test-smoke-gemini-35-flash-lite.yml`.
It requires operator-provided Vertex credentials. No live smoke was run as part of
this repository change because those credentials were unavailable.

### Priority PayGo for router-only prompts

Use the router's boolean `priority_paygo` option on prompt tasks. Keep provider
credentials, project, and the required `global` location in runtime policy:

```yaml
- type: prompt
  connector:
    name: machina-ai
    command: invoke_prompt
    profile: balanced
    priority_paygo: true
  inputs:
    prompt: "$.get('prompt')"
```

Do not add `google-genai` context variables or its native `priority_mode` flag to
a `machina-ai` task. The router maps `priority_paygo` to that native flag only
after policy resolves the profile to a Vertex AI chat route. It rejects non-boolean
values, non-Vertex routes, and non-global Vertex locations before provider
invocation. Omit the option, or set it to `false`, for standard PayGo behavior.

Successful router metadata may include `requested_priority_paygo`; this records
the sanitized request intent and is not confirmation that Vertex acknowledged or
served the priority tier.

## Vertex structured-output and pipeline compatibility

The Vertex factory preserves nullable JSON Schema fields by translating
`type: [T, "null"]` into `type: T` with `nullable: true` on a copy of the
schema. Required fields, enums, defaults, and examples are preserved. Other
type-array unions fail before provider invocation rather than being silently
weakened. Non-dictionary schemas pass through to the provider library unchanged.

The factory remains callable for LCEL composition, forwards invocation config,
and delegates streaming to the underlying model. Validate both structured and
plain-text workflows against the deployed client runtime before a rollout.

## Activating the Claude on Vertex route (`vertex_anthropic`)

The `vertex_anthropic` provider ships **dormant** (`enabled: false`). Nothing routes
to Claude until an environment opts in. This is the Stage 0 activation runbook for
the Entain Gemini→Claude migration (ClickUp 86ajmxm3u).

## Deploy sequence (Stage 0 → live)

Ordered by dependency; merge/deploy is gated on review sign-off.

1. **Runtime** — merge machina-client-api #326, cut a client-api release (bump
   from 1.19.1) that includes the router runtime (#316) + `anthropic`; deploy
   staging → prod. Puts the dependency in the pod runtime.
2. **Connector** — merge machina-templates #292, re-import the `machina-ai`
   connector into the target pod. The `vertex_anthropic` route arrives dormant.
3. **Enable + validate** — set `providers.vertex_anthropic.enabled: true` (§2),
   validate the enabled Claude ids (§1), smoke Haiku + Sonnet (§3).
4. **Widgets facade** — merge entain-widgets #44, re-import the widgets
   workflows. Migrated assistants route through `machina-ai`, still on Gemini
   (zero model change). Needs the connector from step 2 in the pod; does **not**
   need `anthropic` (the Gemini path delegates to `google-genai`).
5. **Claude cutover** — swap the model via §4 (capability remap or per-workflow).

### Stage 0 — Definition of Done
- [ ] client-api release/deploy with `anthropic` + router runtime (release version)
- [ ] `machina-ai` connector imported into the target pod (import confirmation)
- [ ] `providers.vertex_anthropic.enabled: true` in the env (config diff)
- [ ] Haiku **and** Sonnet receipts showing `selected_provider: vertex_anthropic`,
      `selected_model`, `route_reason`, `fallback_used`

Rollback at any step is config-only (§5).

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
(`claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-sonnet-5`, `claude-opus-4-8`),
plus the opt-in `claude-haiku-5-5` (§1a).
Model Garden enablement is **per-project** — confirm which are enabled in the target
project/region (`global`) before relying on them, e.g.:

```bash
gcloud ai model-garden models list --project <ENTAIN_VERTEX_PROJECT> \
  --region global | grep -i claude
```

Override the list per environment if it differs (see §2). If a requested id is not
enabled, the route returns a sanitized `provider_unavailable` / `provider_bad_response`.

### 1a. Claude Haiku 5.5 (opt-in only)

`claude-haiku-5-5` is allowlisted for `vertex_anthropic` chat on the `global`
endpoint, per the [Google Cloud Claude Haiku 5.5 partner-model page](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/claude/haiku-5-5).
No repository default, profile, fallback, or remap references it. Enable the
provider (§2), then select it explicitly as below. Operator-owned runtime policy
may also select it through the existing remap mechanism (§4):

```yaml
- type: prompt
  connector:
    name: machina-ai
    command: invoke_prompt
    provider: vertex_anthropic
    model: claude-haiku-5-5
    location: global
  inputs:
    prompt: "$.get('prompt')"
```

Validation status: offline tests only (`tests/test_router.py::TestVertexAnthropicRoute`)
— policy routing, `list_models`, and model forwarding into a **mocked**
`ChatAnthropicVertex`. No live Vertex call has been made; a live receipt
(§3, with `"model": "claude-haiku-5-5"`) is still required in the target project.

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
`resolved_route` / `decision_method` / `route_reason`. Payload:

```json
{ "command": "invoke_prompt", "provider": "vertex_anthropic",
  "model": "claude-haiku-4-5", "prompt": "Reply in one sentence and name the model." }
```

Run once for `claude-haiku-4-5` and once for `claude-sonnet-5`. Expected receipt:

```json
{ "status": true, "message": "Model loaded.",
  "metadata": { "selected_provider": "vertex_anthropic",
                "selected_model": "claude-haiku-4-5",
                "requested_profile": "balanced",
                "resolved_route": { "provider": "vertex_anthropic",
                                    "model": "claude-haiku-4-5",
                                    "capability": "chat",
                                    "operation_mode": "factory" },
                "decision_method": "explicit_override",
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

## Vercel AI Gateway backend (`vercel_gateway`)

Vercel AI Gateway is an optional backend behind this router, not a replacement
for it. Profiles, model allowlists, retries, fallbacks and receipts stay owned
by `machina-ai`. The provider ships **dormant** (`enabled: false`, empty
`allowed_models`), so no existing route changes until an operator opts in.

Transport: the existing OpenAI-compatible adapter against the fixed endpoint
`https://ai-gateway.vercel.sh/v1` (`FIXED_PROVIDER_ENDPOINTS`; a workflow cannot
replace it). Capability: **chat only** (direct `invoke_chat` /
`completion_receipt` and the model returned by `invoke_prompt`). Embeddings,
search, image and other modalities are not wired through the gateway.

### Ordinary activation (no ZDR)

1. Store the gateway key server-side as `TEMP_CONTEXT_VARIABLE_AI_GATEWAY_API_KEY`
   (or `AI_GATEWAY_API_KEY`). Workflow-supplied credentials are always refused
   (`reject_request_credentials: true`).
2. Enable the provider and list the gateway model ids this environment may use.
   The list is a policy bound, not a claim that the whole Vercel catalog works:

   ```json
   {
     "providers": {
       "vercel_gateway": {
         "enabled": true,
         "allowed_models": { "chat": ["anthropic/claude-sonnet-4.5"] }
       }
     }
   }
   ```

3. Route traffic to it with an operator remap (§4 pattern). Committed workflows
   cannot name `provider: vercel_gateway`; the repository policy lint rejects it.
4. Check `health` with `provider: vercel_gateway`: `ready: true` means the
   configuration is present, not that a model call succeeded.

In this mode the request **omits** `providerOptions.gateway.zeroDataRetention`
entirely (it is never sent as `false`). No ZDR guarantee is made. Vercel treats
team-wide and request-level ZDR as an OR, so if the Vercel team enforces ZDR it
still applies; the router cannot see that and reports it as `unknown`.
Ordinary fallbacks configured under `fallbacks.chat.vercel_gateway` apply.

### Zero Data Retention opt-in (separate step)

ZDR is operator policy, OFF by default. Turn it on only after all of these hold:

- The Vercel team is on a plan that supports per-request ZDR (Pro or
  Enterprise per Vercel's docs). The router cannot check entitlement.
- Every model in `allowed_models.chat` has a ZDR-eligible provider on the
  gateway for the features you use (tools, structured output, caching). Some
  features and provider-side caching are excluded from ZDR even when the flag is
  accepted. Verify against the [Vercel ZDR docs](https://vercel.com/docs/ai-gateway/capabilities/zdr).
- No BYOK keys are configured on the Vercel account for those providers:
  Vercel does not enforce ZDR on BYOK requests, and account-side BYOK is not
  visible to the router.

Then opt in through `MACHINA_AI_ROUTER_CONFIG_JSON`:

```json
{ "providers": { "vercel_gateway": { "zero_data_retention": true } } }
```

What the router then guarantees, offline-tested in `tests/test_vercel_gateway.py`:

- Every request sends `providerOptions.gateway.zeroDataRetention: true`, via
  `extra_body`, on the direct path and on the returned model's `invoke`,
  `bind_tools`, `with_structured_output` and `stream`, including router retries.
- The route is protected and fail-closed: no fallback and no profile skip to a
  provider with weaker or unknown retention. A gateway error (including "no
  ZDR-eligible provider") is returned typed, never retried elsewhere.
- Operator BYOK config (`providers.vercel_gateway.byok`) is refused with
  `policy_credential_not_allowed`, as are request credentials even if
  `reject_request_credentials` is relaxed.
- In both modes a workflow cannot set `provider_options`, `providerOptions`,
  `extra_body`, `zero_data_retention` or `byok`; the request fails
  `unsupported_option` before any outbound call.

What it does **not** guarantee: plan entitlement, per-model or per-feature
eligibility, account-side BYOK state, or that a successful response proves
retention compliance. A successful call is not evidence of ZDR.

### Receipts and health

Gateway routes add to the receipt `metadata`:

```json
{ "zdr_mode": "requested",
  "gateway": { "backend": "vercel_ai_gateway", "zdr_effective": "unknown",
               "upstream_provider": null, "upstream_model": "anthropic/claude-sonnet-4.5" } }
```

`zdr_mode` is what the router asked for (`requested` / `not_requested`).
`selected_provider`/`selected_model` are the gateway route; `upstream_model` is
what the gateway reported back (`null` when not reported, e.g. factory mode).
The upstream provider is not exposed by the OpenAI-compatible response and stays
`null`. `health` adds `zdr_mode` and `gateway.{zdr_effective, zdr_entitlement,
account_byok}`, all `unknown`. No prompt or response content is logged.

### Validation status and rollback

Offline only: fake SDKs plus the real `langchain-openai`/`openai` clients
against an `httpx` mock transport. No Vercel call, live or paid, has been made;
ZDR-on against a real entitled team is unverified.

Rollback is config-only: set `zero_data_retention: false` to stop sending the
flag, or `enabled: false` (and remove any remap) to take the gateway out of the
route entirely.
