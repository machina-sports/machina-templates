# Perplexity Sonar search (`perplexity`) — readiness

The `perplexity` provider is prepared for **search only** (`invoke_search`) and
ships **disabled**. No repository default, profile, fallback or remap routes to
it, and no workflow is switched. Enabling it, adding a key, or running a model
smoke each need separate operator approval.

## Contract

Perplexity's documented Sonar API, called as POST `https://api.perplexity.ai/v1/sonar`:

- OpenAPI: <https://docs.perplexity.ai/openapi.json>
- Migration notes: "How to migrate from Sonar", listed in the official docs
  index <https://docs.perplexity.ai/llms.txt>.

The Agent API (`/v1/agent`) is a different contract and is not implemented here.
Perplexity's migration guide points Sonar users toward it. A move to the Agent
API would be a separate integration; the Sonar contract above is still published.

The router sends a fixed body and nothing else:

```json
{ "model": "sonar", "messages": [...], "stream": false,
  "disable_search": false, "enable_search_classifier": false }
```

Web search is always on. Caller options such as `extra_body`, provider options,
endpoint or credential fields are not forwarded. Search filters (recency, domain,
date) are **not supported yet**; do not rely on them until they are implemented
and tested.

Transport is the existing OpenAI SDK client over the fixed endpoint, with the
route timeout and `max_retries=0` (the router owns retries).

## Policy

| Setting | Value |
| --- | --- |
| `enabled` | `false` |
| `require_credential` | `true` (an ambient `OPENAI_API_KEY` is never used) |
| credential | `TEMP_CONTEXT_VARIABLE_PERPLEXITY_API_KEY`, server-side only |
| `allowed_models.search_answer` | `sonar`, `sonar-pro` |
| `allowed_models.chat` | empty: generic chat and the `invoke_prompt` factory are **not** activation-ready |

Under the repository's default endpoint policy (`allow_custom_base_url: false`),
workflow-supplied endpoints are refused (`policy_endpoint_not_allowed`). Models
outside the allowlist are refused (`policy_model_not_allowed`), and a missing key
fails `credential_missing`, all before any HTTP call. Existing operator-owned
endpoint and credential policy remains authoritative; this adapter adds no bypass.

## Response mapping

- `data.content`: the answer text. An empty, missing or truncated
  (`finish_reason: length`) answer fails `provider_bad_response`. Nothing is
  returned as a success without an answer.
- A refusal shape (`finish_reason: content_filter` or a `refusal` field) fails
  `provider_content_rejected` without echoing provider text.
- `data.citations`: objects with `url`, `title` and, when the provider supplied
  a citation list, the original one-based `citation_index`. Order and duplicates
  are retained. Match answer markers using `citation_index`, **not** the filtered
  list position: rejected sources can leave gaps. Titles come only from a web
  `search_results` entry with the exact same URL, otherwise `""`.
  If `citations` is absent, valid web `search_results` are used in returned order
  without invented marker indices. Non-http(s), host-less, userinfo,
  whitespace/control-character and bad-port URLs are dropped, as are attachment-only
  results. Citations are never derived from answer text.
- `metadata.provider_request_id` and `metadata.usage` are passed through; usage
  stays `null` when not reported.
- `data.provider_extensions.provider_model` is the model the provider reported.
  The receipt (`selected_model`, `router_receipt`) records the model the router
  requested, not a server claim.

Errors use the shared classes: 401/402/403 `provider_authentication`, 429
`provider_rate_limited`, 500/502/503/504 `provider_unavailable`, timeouts
`provider_timeout`. Other errors follow the shared classifier; not every 5xx
status is classified as retryable. With no fallback configured, a failure is
returned typed and never rerouted. Array-form message content is currently rejected
as `provider_bad_response`; this readiness path supports nonempty text answers only.

## Inactive example config

`examples/perplexity-search.disabled.json` shows the shape of an opt-in: a
`perplexity_search` profile with `provider.enabled: false`. It is **not applied**
anywhere. Applied as-is it still refuses before any HTTP call. It does not add
any automatic fallback.

## Validation status

Offline only (`tests/test_perplexity.py`): the real `openai` SDK against an
`httpx` mock transport with synthetic, schema-shaped responses. No Perplexity
call has been made, and no credential was used.
