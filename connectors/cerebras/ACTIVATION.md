# Activating the Cerebras fast route

The standalone `cerebras` connector is installable, while the canonical
`machina-ai` provider ships dormant (`providers.cerebras.enabled: false`). The
repository default remains Vertex AI. With Cerebras dormant or missing its
credential, `profile: fast` keeps its previous Groq behavior.

The public endpoint is fixed at `https://api.cerebras.ai/v1`. Credentials and
model policy are runtime-owned; workflows must not set an endpoint or override
an API key. The seeded public chat allowlist follows the official catalog checked
on 2026-08-18: `gpt-oss-120b` and `gemma-4-31b`.

## Prerequisites

1. Install/import the `cerebras` connector before re-importing `machina-ai`, so
   runtime delegation is available.
2. Configure `TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY` in the target runtime.
3. Keep the provider disabled until the credential smoke and benchmark pass.
4. Do not put credentials, endpoints, or provider policy in workflow YAML.

The standalone `test-credentials.yml` workflow executes one bounded completion
and records a receipt. A live smoke remains pending until an approved credential
is configured in the target environment.

## Benchmark and canary

Before enabling production traffic, compare `gpt-oss-120b` with the existing
Groq fast route on representative prompts. Record success rate, p50/p95 latency,
output acceptance, rate limits, and receipt metadata. Do not promote if auth,
policy, invalid request, content rejection, or unsupported errors occur; those
classes deliberately do not fall back.

Enable Cerebras for a bounded environment canary through layered router config:

```json
{
  "providers": {
    "cerebras": {
      "enabled": true
    }
  }
}
```

The canonical `fast` profile then selects Cerebras first. Approved transient
classes (`provider_timeout`, `provider_rate_limited`, `provider_unavailable`, and
`provider_bad_response`) may fall back to the explicit Groq model
`llama-3.3-70b-versatile`. Receipts must show `selected_provider`,
`selected_model`, `route_reason`, `fallback_used`, and `fallback_attempts`.

## Rollback

Rollback is config-only: set `providers.cerebras.enabled` to `false` or remove
the enabling overlay. The ordered fast profile skips dormant Cerebras and resumes
the prior Groq route without workflow, connector alias, or secret changes.
