# Machina AI Intelligent Router Specification

## Status

- **Status:** Proposed
- **Target facade:** `machina-ai`
- **Compatibility alias:** `machina-ai-fast`
- **Initial contract version:** `v1`
- **Repository default route:** Google Vertex AI through the `google-genai` adapter
- **Repository-policy prerequisite:** `CLAUDE.md` and `scripts/check-no-openai.sh` currently reject `connector.name: machina-ai` outside legacy paths. Shipping `machina-ai` as the new workflow facade requires an approved, narrow policy/lint change that permits the router only when its effective default is Vertex AI. Until then, canonical workflow examples using the new facade are specification-only and MUST NOT be committed as runnable YAML.
- **Primary audience:** connector maintainers, workflow authors, runtime operators, Studio, CLI, and platform API teams

---

## 1. Purpose

This document specifies how `machina-ai` evolves from an OpenAI-compatible model loader into a unified, policy-driven AI router.

The router provides one stable connector facade for workflows that need an AI capability but do not require a specific vendor. It chooses an allowed provider and model from explicit request overrides, capability requirements, profiles, organization/runtime policy, and fallback rules.

The router is intended to:

- preserve existing `machina-ai` prompt, embedding, and transcription calls
- represent `machina-ai-fast` as `machina-ai` with a `fast` profile while retaining a compatibility alias
- provide one abstract capability contract across current standalone AI/model connectors
- allow provider/model remapping without editing every workflow
- preserve provider-specific security constraints, especially private-runtime and NVIDIA NIM fail-closed behavior
- normalize request extraction, responses, errors, metadata, timeouts, credentials, and observability
- let provider-specific connectors remain available as escape hatches while the router is proven

The router is a facade and policy boundary. It is not a requirement to remove every provider connector or erase provider-specific capabilities.

---

## 2. Design decision: modalities in v1

The router **owns the common capability namespace for all AI modalities in v1**, but modality implementations are delivered in phases.

### 2.1 Required v1 implementation

The first production release MUST implement and test:

- chat/prompt model loading and direct chat execution
- embeddings
- search_answer
- fast chat through Groq or an equivalent configured low-latency route
- NVIDIA NIM/private-runtime chat with fail-closed endpoint and model policy, preserving the merged connector's factory and completion-receipt semantics
- Azure Foundry/Azure OpenAI chat
- Gemini/Vertex chat and embeddings
- audio transcription, because it is part of the existing `machina-ai` contract
- at least one generated multimodal route, preferably image generation through Google or Stability
- `health` and `list_models`

### 2.2 Contract in v1, incremental provider coverage

The v1 command and adapter contracts also define:

- image editing and generation
- asynchronous video generation
- TTS and custom voice operations
- music generation

Video, TTS/custom voice, and music MAY remain preview capabilities until their adapters satisfy the same security, receipt, error, and test requirements as the core routes.

This resolves the design-review question as follows:

> Do not build a chat-only facade that must later be redesigned. Define the multimodal contract now, ship the core text/embedding/search/private-runtime routes first, preserve existing transcription, prove one generated multimodal route, and add the remaining adapters incrementally.

---

## 3. Scope

### 3.1 In scope

- stable router commands and compatibility aliases
- canonical request and response envelopes
- legacy parameter extraction
- provider adapter architecture
- capability and profile routing
- global provider remapping
- provider/model/endpoint allowlists
- credential alias migration
- fallback, timeout, retry, and circuit-breaker semantics
- synchronous and asynchronous operations
- observability and sanitized errors
- migration guidance for standalone AI connectors
- offline unit tests and live smoke-test expectations

### 3.2 Non-goals

The first release does not:

- delete provider-specific connectors
- guarantee identical model output across providers
- silently emulate a provider-specific feature that another provider does not support
- permit arbitrary endpoints in protected or private deployments
- forward credentials from one provider to another during fallback
- make marketing metadata in `_install.yml` authoritative for runtime capabilities
- route document ingestion/preprocessing such as Docling through the model router
- require live provider credentials in CI

---

## 4. Repository constraints

New workflows in this repository MUST continue to follow `CLAUDE.md`:

- Vertex AI through `google-genai` is the default provider for new workflows.
- The router's repository-default route MUST resolve to `provider: vertex_ai`.
- The existence of OpenAI-compatible and other provider adapters is for compatibility, explicit approved usage, customer-owned endpoints, and runtime portability. It does not change the repository's default-provider policy.
- New YAML workflows MUST NOT reintroduce banned OpenAI/GPT connector or model references.
- `connector.name: machina-ai` is itself currently banned by the repository lint. The router cannot become the preferred committed workflow facade until maintainers approve a narrow lint/policy change.
- That policy change SHOULD permit `machina-ai` only as a provider-independent router whose repository default is Vertex AI; it MUST NOT make OpenAI, Groq, or another non-Vertex provider the default for committed templates.
- `fast` routes and non-Vertex fallbacks are operator-approved runtime options, not repository defaults.

The router implementation, documentation, tests, and migration tooling may describe legacy/provider compatibility without changing the default write path for workflows. Every canonical runnable YAML example MUST pass `scripts/check-no-openai.sh all` after the approved policy change.

---

## 5. Definitions

### Capability

A provider-independent operation such as chat, embedding, search_answer, image generation, video generation, transcription, TTS, or music generation.

### Provider

A concrete API/runtime family such as Vertex AI, Google AI Studio, Azure Foundry, Groq, NVIDIA NIM, xAI, Perplexity, Stability, ElevenLabs, or a policy-approved OpenAI-compatible endpoint.

### Route

The resolved provider, model, credential binding, endpoint binding, adapter, timeout, and fallback policy used for one operation.

### Profile

A workload intent such as `fast`, `quality`, or `private_runtime`. A profile is not a provider name; policy maps profiles to routes.

### Adapter

A small provider-specific implementation behind the router's canonical interface.

### Factory operation

An operation that returns a configured model/client object for the Machina prompt or document runtime. Existing `invoke_prompt` and `invoke_embedding` calls use this behavior.

### Execution operation

An operation that sends content to a provider and returns generated or transformed data, such as `invoke_chat`, `invoke_search`, image generation, or transcription.

### Protected route

A route whose endpoint, credentials, and allowlist are controlled by runtime configuration and cannot be changed by workflow input. NVIDIA NIM/private runtime is protected by default.

---

## 6. Architecture

The router MUST be composed from small testable components rather than a single provider `if/else` chain.

```text
workflow invocation
        |
        v
legacy/canonical parameter normalizer
        |
        v
command + capability resolver
        |
        v
policy engine -------------------- router configuration
        |                           - defaults
        |                           - profiles
        |                           - remaps
        |                           - allowlists
        |                           - fallbacks
        v
credential + endpoint binder ----- vault/runtime environment
        |
        v
provider adapter registry
        |
        v
adapter execution / model factory
        |
        v
response + metadata normalizer
```

Recommended modules:

```text
connectors/machina-ai/
  machina-ai.py                 # thin public command functions
  router/
    models.py                   # normalized request/response types
    normalize.py                # legacy envelope and alias extraction
    capabilities.py             # command -> capability resolution
    policy.py                   # route selection, remap, fallback rules
    registry.py                 # validated adapter/capability registry
    credentials.py              # provider-scoped credential resolution
    endpoints.py                # endpoint policy and allowlists
    errors.py                   # sanitized error taxonomy
    receipts.py                 # metadata and usage extraction
    adapters/
      base.py
      openai_compatible.py
      azure_foundry.py
      google_genai.py
      groq.py
      xai.py
      perplexity.py
      nvidia_nim.py
      stability.py
      byteplus_modelark.py
      elevenlabs.py
      google_speech.py
  tests/
```

The exact file layout MAY change, but the implementation MUST preserve these separations of responsibility.

### 6.1 Packaging prerequisite

Current connector packages register a YAML definition and execute its Python script directly. Nested Python packages are not yet proven to be copied, imported, and loaded by every installation/runtime path.

Before adopting the layout above, implementation MUST prove through an installed-template integration test that:

- nested `router/` modules are included in the connector bundle
- imports resolve in the target runtime
- dependency versions are present
- a connector loaded from the installed dataset can execute both a prompt factory and a document/embedding factory

If the runtime cannot package nested modules, the first implementation MUST use a compatible bundled single-file or explicit dynamic-loader design while retaining the architectural boundaries in tests. The hyphenated `machina-ai.py` file MUST NOT be assumed importable as `machina_ai`; the `machina-ai-fast` wrapper needs a runtime-supported shared module or loader.

---

## 7. Stable command contract

### 7.1 Canonical commands

| Capability | Canonical command | Compatibility commands | Required v1 status |
|---|---|---|---|
| Chat model factory | `invoke_prompt` | existing `invoke_prompt` | GA |
| Direct chat execution | `invoke_chat` | provider chat-completion operations | GA |
| Embedding model factory/direct embedding | `invoke_embedding` | `embed_query`, `embed_documents` | GA |
| Model discovery | `list_models` | existing provider model-list commands | GA |
| Readiness | `health` | provider health commands | GA |
| Search-answer | `invoke_search` | search-enabled prompt mode | GA |
| Image generation/edit | `invoke_image` | `generate_image` | one adapter GA; others preview |
| Video generation | `invoke_video` | create/get/list/delete task commands | contract GA; adapters may be preview |
| Transcription | `transcribe_audio_to_text` | `invoke_transcribe` | GA |
| TTS | `invoke_tts` | `get_text_to_speech` | contract GA; adapter may be preview |
| Voice management | provider-specific voice commands | `get_voices`, clone/train/custom voice commands | provider extension |
| Music generation | `invoke_music` | existing Google music command | preview |

### 7.2 Factory versus execution behavior

Existing Machina workflows use `invoke_prompt` and `invoke_embedding` as model factories. The router MUST preserve this behavior.

- `invoke_prompt` defaults to `operation_mode: factory` and returns the provider-compatible chat model/client in `data`.
- `invoke_embedding` defaults to `operation_mode: factory` and MUST remain a factory unless `operation_mode: execute` is explicit.
- `invoke_chat` always uses `operation_mode: execute`.
- `embed_query` and `embed_documents` always use `operation_mode: execute`.
- The presence of `input`, `texts`, `prompt`, or similarly named metadata MUST NOT silently switch a factory command into execution mode.
- The router MUST NOT silently send content merely because a legacy factory call contains content-like fields in nested metadata.

Factory operations are **in-process runtime operations in v1**. They return live model/client objects only to the Machina task runtime that invoked them; they are not serialized across HTTP/process boundaries. Any future remote router MUST return opaque server-side handles instead of attempting to serialize LangChain/provider client objects.

### 7.3 Command aliases

Aliases MUST be resolved before provider selection:

```text
invoke_prompt                -> capability=chat, operation_mode=factory
invoke_chat                  -> capability=chat, operation_mode=execute
invoke_embedding             -> capability=embedding, mode=factory|execute
embed_query                  -> capability=embedding, mode=execute, input_kind=query
embed_documents              -> capability=embedding, mode=execute, input_kind=documents
transcribe_audio_to_text     -> capability=transcription
invoke_transcribe            -> capability=transcription
invoke_image                 -> capability=image
generate_image               -> capability=image
invoke_tts                   -> capability=tts
get_text_to_speech           -> capability=tts
```

Provider-specific legacy commands are normalized with their source connector identity. In particular, legacy `nvidia-nim/invoke_chat` is a chat **factory** and maps to router `invoke_prompt`; router `machina-ai/invoke_chat` remains direct execution. NIM `completion_receipt` maps to direct execution plus the canonical metadata receipt.

Serialized capability and provider IDs use lowercase `snake_case`. Canonical capability IDs include `chat`, `embedding`, `search_answer`, `image`, `video`, `transcription`, `tts`, and `music`. Legacy `search-answer` is accepted only as an input alias. Provider alias `ai_studio` normalizes to `google_ai_studio` in receipts and policy evaluation.

### 7.4 Command inventory parity

Implementation MUST generate an inventory from both connector declarations and workflow call sites. Every declared or observed command string MUST be mapped, explicitly deprecated, or identified as broken with a test.

Known irregularities that must be resolved:

- Google voice commands are exactly `invoke_clone_instant_voice`, `invoke_train_pro_voice`, and `invoke_synthesize_custom_voice`.
- A workflow currently references `google-genai/edit_image`, but that command is absent from the connector YAML and Python implementation. Migration must either repair the workflow, add a tested compatibility alias to `invoke_image`, or mark it unsupported; it must not be silently ignored.
- Grok/xAI exposes observed REST dispatch strings `post-responses` and `post-chat/completions`. `post-responses` can include web/X search and code-interpreter tools, so it maps to chat plus declared tool/search capabilities rather than chat alone.
- BytePlus ModelArk compatibility must recognize its exact REST command family, including `post-contents/generations/tasks`, `get-contents/generations/tasks`, and path-ID task operations.
- An Azure test workflow uses display label `Prompt` while the connector value is `invoke_prompt`. The inventory must establish whether display labels are valid dispatch aliases or classify the workflow as broken.

---

## 8. Canonical request envelope

New callers SHOULD use this shape:

```yaml
contract_version: v1
command: invoke_chat
capability: chat             # optional when command is sufficient
operation_mode: execute
profile: balanced
provider: vertex_ai          # optional explicit override
model: gemini-2.5-flash      # `model_name` remains accepted
options:
  temperature: 0.2
  max_tokens: 2048
  timeout_ms: 30000
  response_format: text
  stream: false
input:
  messages:
    - role: user
      content: Summarize this event.
output:
  path: null
metadata:
  request_tags:
    workflow: event-summary
```

The Python connector command will continue receiving a dictionary. `command` MAY remain implicit when dispatch already selected the Python function.

### 8.1 Backward-compatible input locations

The normalizer MUST accept values from:

1. explicit canonical top-level fields
2. legacy top-level fields
3. `params`
4. `headers`
5. `path_attribute`

For duplicate ordinary fields, the earlier source wins. The router SHOULD record conflicting aliases in debug telemetry without recording secret values or raw content.

Security-sensitive values use separate precedence: operator/runtime route bindings win over every workflow source. Workflow-supplied credentials, endpoints, deployment names, callback URLs, and allowlist-affecting fields are accepted only when trusted policy enables that exact field for that provider; they never shadow an operator binding by ordinary top-level precedence.

`headers` and `path_attribute` are compatibility sources, not unrestricted configuration namespaces:

- `headers` MAY supply known credential/header aliases only.
- `path_attribute` MAY supply declared path identifiers only.
- Unknown headers MUST NOT be forwarded automatically.
- Provider adapters MUST declare which fields they consume from each source.

### 8.2 Accepted common aliases

| Canonical field | Accepted aliases |
|---|---|
| `model` | `model_name`, provider-specific model/deployment aliases where unambiguous |
| `api_key` | `credential` only when adapter policy defines the same credential type |
| `organization` | `org_id` |
| `project` | `project_id` |
| `endpoint` | `azure_endpoint`; `base_url` only for approved OpenAI-compatible routes |
| `deployment` | `azure_deployment`, `deployment_name` |
| `api_version` | provider API-version aliases |
| `audio_path` | `audio-path`, first compatible file item |
| `image_paths` | `image_path`, `images`, provider file-item arrays |
| `prompt` | single user message when execution mode allows conversion |
| `messages` | provider-compatible chat message arrays |
| `timeout_ms` | legacy `timeout`, normalized as described below |

### 8.3 Common option set

The normalized request model SHOULD support:

- `provider`
- `model` / `model_name`
- `profile`
- `base_url`
- `endpoint` / `azure_endpoint`
- `deployment` / `azure_deployment`
- `api_version`
- `api_key` / `credential`
- `project` / `project_id`
- `organization` / `org_id`
- `location`
- `temperature`
- `max_tokens`
- `timeout_ms`
- `response_format`
- `stream`
- `messages`
- `prompt`
- `input` / `texts`
- `image_path` / `image_paths`
- `audio_path`
- input and output file paths
- capability-specific options under `options`

Adapters MUST reject unsupported options when silently ignoring them could change safety, privacy, price, or output semantics. Harmless unknown metadata MAY be ignored.

### 8.4 Timeout normalization

The canonical unit is milliseconds: `timeout_ms`.

For legacy `timeout`:

- values `<= 600` are interpreted as seconds
- values `> 600` are interpreted as milliseconds
- invalid values fall back to the configured route timeout
- the normalized timeout MUST be bounded by route policy

This preserves current `machina-ai-fast` and `google-genai` behavior while creating one unambiguous new write path.

### 8.5 Local file inputs

For audio, image, video, and output paths, the router MUST:

- resolve files inside an approved sandbox/work directory
- reject path traversal and paths outside allowed roots
- validate existence before provider invocation
- enforce configured size and media-type limits
- avoid logging full sensitive paths by default
- use collision-safe generated output names when no path is supplied
- clean up temporary files according to runtime policy

### 8.6 Remote media inputs

When an adapter accepts an audio/image/video/document URL, the router MUST treat the fetch as a separate SSRF boundary:

- allow only configured schemes and hosts; deny by default
- resolve DNS and reject loopback, link-local, metadata-service, and unapproved private addresses
- revalidate every redirect target and limit redirect count
- protect against DNS rebinding by validating the connected address
- enforce connect/read timeouts and maximum byte counts while streaming
- verify declared and detected content type
- reject embedded credentials and unexpected URL fragments
- define explicitly whether signed GCS/private object URLs are allowed
- apply the same sandbox policy to credential file paths; production credentials SHOULD be inline vault material or runtime identity, not arbitrary caller-supplied filesystem paths

---

## 9. Canonical response envelope

Every router command MUST return:

```json
{
  "status": true,
  "data": {},
  "message": "Route completed.",
  "metadata": {
    "contract_version": "v1",
    "capability": "chat",
    "operation_mode": "execute",
    "selected_provider": "vertex_ai",
    "selected_model": "gemini-2.5-flash",
    "route_reason": "profile:balanced",
    "latency_ms": 241,
    "fallback_used": false,
    "fallback_attempts": [],
    "provider_request_id": null,
    "usage": null,
    "error_class": null
  }
}
```

### 9.1 Status

- `status` MUST be boolean in the router contract.
- Legacy error values such as `status: "error"` MUST be normalized to `false`.
- Compatibility wrappers MAY provide a legacy projection only when a proven downstream dependency requires it, but the underlying router receipt MUST use boolean status.

### 9.2 Data

`data` is capability-specific:

- factory operations: configured model/client object
- chat/search: generated message/content plus structured provider fields when safe
- embeddings: vector or vectors
- transcription: text and optional segments
- image/audio/music: bytes, encoded data, or approved output-file receipt
- video: asynchronous task receipt or completed artifact receipt
- health/listing: structured status/model entries

For direct chat/search execution, normalized `data` MUST use:

```json
{
  "role": "assistant",
  "content": "generated text or structured parts",
  "finish_reason": "stop",
  "citations": [],
  "tool_calls": [],
  "provider_extensions": {}
}
```

Provider-only fields belong under `provider_extensions`; adapters MUST NOT overwrite canonical fields with incompatible types.

Streaming is out of scope for v1. `stream: true` MUST return `unsupported_option` until a versioned chunk/event, cancellation, final-receipt, and error contract is approved. Adapters MUST NOT return provider-native iterators through the canonical envelope.

### 9.3 Required metadata

`metadata` MUST include when applicable:

- `contract_version`
- `capability`
- `operation_mode`
- `selected_provider`
- `selected_model`
- `route_reason`
- `latency_ms`
- `fallback_used`
- `fallback_attempts` with sanitized outcomes
- `provider_request_id` when safe to expose
- token/character/second usage when available
- `error_class` on failure

The router MUST NOT log or return secrets, raw authorization headers, service-account JSON, or raw prompts by default.

### 9.4 Error envelope

```json
{
  "status": false,
  "data": null,
  "message": "The selected model is not allowed for this runtime.",
  "metadata": {
    "contract_version": "v1",
    "capability": "chat",
    "selected_provider": "nvidia_nim",
    "selected_model": "unapproved-model",
    "route_reason": "explicit_provider",
    "latency_ms": 2,
    "fallback_used": false,
    "fallback_attempts": [],
    "provider_request_id": null,
    "usage": null,
    "error_class": "policy_model_not_allowed"
  }
}
```

Recommended sanitized error classes:

- `invalid_request`
- `unsupported_capability`
- `unsupported_option`
- `credential_missing`
- `credential_invalid`
- `policy_provider_not_allowed`
- `policy_model_not_allowed`
- `policy_endpoint_not_allowed`
- `policy_fallback_forbidden`
- `input_file_invalid`
- `provider_authentication`
- `provider_rate_limited`
- `provider_timeout`
- `provider_unavailable`
- `provider_bad_response`
- `provider_content_rejected`
- `budget_exceeded`
- `internal_adapter_error`

Raw provider exceptions MAY be retained in restricted debug telemetry but MUST NOT be exposed in normal workflow output.

---

## 10. Provider adapter interface

Every provider adapter MUST declare capabilities and implement only the operations it actually supports.

Illustrative interface:

```python
class ProviderAdapter:
    provider_id: str

    def capabilities(self) -> set[str]: ...
    def validate_route(self, route, request) -> None: ...
    def health(self, route) -> dict: ...
    def list_models(self, route) -> list[dict]: ...
    def create_chat_model(self, route, request): ...
    def invoke_chat(self, route, request) -> dict: ...
    def create_embedding_model(self, route, request): ...
    def embed(self, route, request) -> dict: ...
```

Optional methods MAY cover search, image, video, transcription, TTS, voice, and music.

An adapter MUST:

- declare capability support in a validated registry
- validate provider-specific required fields
- receive credentials already bound to that provider
- avoid reading arbitrary workflow-provided endpoints in protected routes
- map provider errors into the router taxonomy
- extract safe request IDs and usage receipts
- support dependency/readiness checks
- be testable with mocked provider clients

The registry MUST NOT derive support from `_install.yml` feature text. Existing metadata contains capability claims that do not match executable commands.

---

## 11. Provider identifiers and v1 coverage

Canonical provider identifiers:

| Provider ID | Meaning |
|---|---|
| `vertex_ai` | Google Vertex AI |
| `google_ai_studio` | Google Gemini API/AI Studio |
| `openai_compatible` | Approved OpenAI-compatible endpoint family |
| `openai` | OpenAI-hosted route, where policy explicitly allows it |
| `azure_foundry` | Azure AI Foundry/Azure OpenAI deployment |
| `groq` | Groq low-latency inference |
| `xai` | xAI/Grok |
| `perplexity` | Perplexity search_answer/chat |
| `nvidia_nim` | Runtime-managed NVIDIA NIM/private inference |
| `byteplus_modelark` | BytePlus ModelArk asynchronous generation |
| `stability` | Stability image generation |
| `elevenlabs` | ElevenLabs TTS/voice |
| `google_speech` | Google Speech-to-Text |

Aliases MAY be accepted, but metadata MUST emit the canonical identifier.

---

## 12. Routing decision engine

### 12.1 Resolution order

The policy engine MUST resolve a route in this order:

1. normalize the command, capability, operation mode, aliases, and legacy envelopes
2. load organization/runtime policy and capability registry
3. apply protected-runtime constraints
4. evaluate an explicit `provider` and `model` override, if supplied
5. apply global family/capability remaps
6. apply the requested profile or the configured default profile
7. filter candidates by capability, operation mode, modality, allowlists, residency/privacy constraints, and available credentials
8. choose the primary route deterministically
9. attach the configured fallback chain
10. execute and return an observable receipt

### 12.2 Explicit override

An explicit allowed `provider` wins over profile selection.

An explicit `model` selects only among models allowed for that provider, capability, organization, and runtime.

Explicit input does not override:

- runtime-owned endpoints
- provider/model deny rules
- private-runtime fail-closed policy
- missing capability support
- credential binding rules
- data residency or privacy requirements

### 12.3 Capability inference

When no capability is supplied, the router infers it from the command first and inputs second.

Examples:

| Signal | Inferred capability |
|---|---|
| `invoke_prompt`, `invoke_chat`, `messages` | chat |
| `invoke_embedding`, `embed_query`, `embed_documents`, embedding input | embedding |
| `invoke_search`, `search: true` | search_answer |
| `invoke_image`, `generate_image`, image generation options | image |
| `invoke_video`, video task operation | video |
| `transcribe_audio_to_text`, `invoke_transcribe`, `audio_path` with transcription command | transcription |
| `invoke_tts`, `get_text_to_speech` | TTS |
| `invoke_music` | music |

Ambiguous inputs MUST fail with `invalid_request`; the router MUST NOT guess a high-cost or privacy-sensitive modality.

### 12.4 Profiles

| Profile | Intent | Typical route policy |
|---|---|---|
| `balanced` / `default` | general production workloads | repository default: Vertex AI balanced model |
| `fast` | lowest practical latency | Groq or configured low-latency model |
| `quality` | best configured output quality | higher-quality allowed model |
| `cheap` | minimize expected cost | low-cost allowed model with bounded output |
| `open_source` | prefer open-weight serving | approved NIM/open-source endpoint; no arbitrary URL |
| `private_runtime` | data stays in private runtime | protected NIM/local route, fail closed |
| `multimodal` | image/audio/video-capable route | provider selected by requested modality |
| `long_context` | large context requirement | model with sufficient configured context window |

Profiles MUST map to policy-controlled provider/model candidates. Workflow authors MUST NOT rely on a profile always naming the same vendor.

### 12.5 Default behavior in this repository

Unless organization/runtime policy overrides it:

```yaml
defaults:
  chat:
    provider: vertex_ai
    model: gemini-2.5-flash
  embedding:
    provider: vertex_ai
    model: text-embedding-004
```

This is a router configuration example, not workflow YAML.

---

## 13. Global provider remapping

Operators MUST be able to redirect an abstract family, capability, or profile without editing workflow YAML.

Example:

```yaml
version: 1
remaps:
  families:
    gemini-default:
      provider: vertex_ai
      model: gemini-2.5-flash
  capabilities:
    search_answer:
      provider: perplexity
      model: sonar
  profiles:
    fast:
      provider: groq
      model: configured-fast-model
```

A remap may point a formerly Gemini-oriented abstract family to another approved provider or OpenAI-compatible implementation. Workflows SHOULD reference capabilities/profiles or stable family aliases rather than hardcoded vendor model IDs when vendor portability is desired.

Remaps MUST NOT:

- change a protected private-runtime route into a public route unless an operator changes the protected policy itself
- reuse the old provider's credentials
- bypass allowlists
- silently downgrade required capabilities

Resolved metadata MUST state that a remap was used in `route_reason`.

---

## 14. Router configuration

Illustrative configuration:

```yaml
version: 1

policy:
  default_profile: balanced
  allow_workflow_credentials: false
  allow_custom_base_url: false
  log_raw_prompts: false
  log_raw_responses: false

providers:
  vertex_ai:
    adapter: google_genai
    credential_ref: TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL
    project_ref: TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID
    location: global
    allowed_models:
      chat: [gemini-2.5-flash, gemini-2.5-pro]
      embedding: [text-embedding-004]

  groq:
    adapter: groq
    credential_ref: TEMP_CONTEXT_VARIABLE_GROQ_API_KEY
    allowed_models:
      chat: [configured-fast-model]

  nvidia_nim:
    adapter: nvidia_nim
    protected: true
    endpoint_env: NVIDIA_NIM_CHAT_BASE_URL
    credential_env: NVIDIA_NIM_CHAT_API_KEY
    allowed_models_env: NVIDIA_NIM_CHAT_ALLOWED_MODELS
    default_model_env: NVIDIA_NIM_CHAT_MODEL
    fail_closed: true

profiles:
  balanced:
    chat: [{provider: vertex_ai, model: gemini-2.5-flash}]
  fast:
    chat: [{provider: groq, model: configured-fast-model}]
  quality:
    chat: [{provider: vertex_ai, model: gemini-2.5-pro}]
  private_runtime:
    chat: [{provider: nvidia_nim}]

fallbacks:
  chat:
    vertex_ai:
      - {provider: groq, profile: fast}
  search_answer:
    perplexity:
      - {provider: vertex_ai, capability_options: {grounding: true}}
```

Production configuration SHOULD be loaded from an operator-controlled document or runtime settings. Workflow inputs MUST NOT be able to rewrite it.

---

## 15. Credentials and endpoint security

### 15.1 Provider-scoped credentials

Credentials MUST be bound to one provider route.

- A Vertex service-account credential MUST NOT be sent to Google AI Studio, OpenAI-compatible endpoints, or fallback providers.
- An OpenAI-compatible API key MUST NOT be forwarded to a remapped provider unless configuration explicitly binds that same secret reference to the target route.
- Fallback selects a new provider route and resolves that route's own credential.
- Metadata and logs MUST identify credential aliases/references only when safe, never secret values.

### 15.2 Credential aliases

The normalizer MAY accept legacy fields:

- `api_key`
- `credential`
- `project` / `project_id`
- `organization` / `org_id`
- `endpoint` / `azure_endpoint`
- `base_url`

The credential binder maps them to provider-specific slots only when policy allows workflow-supplied credentials. Production SHOULD prefer vault/runtime references.

Canonical new secret names and observed legacy aliases MUST be distinguished in configuration and tests. At minimum:

- Groq: `TEMP_CONTEXT_VARIABLE_GROQ_API_KEY` and legacy `TEMP_CONTEXT_VARIABLE_SDK_GROQ_API_KEY`
- Azure: observed `TEMP_CONTEXT_VARIABLE_AZURE_OPENAI_API_KEY`, `TEMP_CONTEXT_VARIABLE_AZURE_OPENAI_ENDPOINT`, and `TEMP_CONTEXT_VARIABLE_AZURE_OPENAI_DEPLOYMENT_NAME`, plus any approved canonical Foundry aliases
- BytePlus: observed `TEMP_CONTEXT_VARIABLE_BYTEPLUS_MODELARK_API_KEY`

Alias support maps secret references; it never copies one provider's resolved secret into another provider route.

### 15.3 Endpoint policy

Arbitrary `base_url` is a security boundary, not a convenience field.

The router MUST prevent SSRF and credential exfiltration by:

- denying caller-supplied endpoints by default
- allowing custom endpoints only through operator allowlists
- binding endpoint and credential as one configured route
- rejecting loopback, link-local, metadata-service, private-network, and unapproved DNS/IP destinations unless the protected runtime explicitly owns them
- validating redirects or disabling them for provider API calls
- never copying credentials to a redirect target

### 15.4 NVIDIA NIM/private runtime

The NIM adapter MUST preserve the existing operational rule:

- endpoint comes from runtime environment/configuration
- credential comes from runtime environment/configuration
- workflow may request only an allowed model
- the adapter validates the model allowlist before creating a client or sending a request
- workflow-provided `base_url`/`endpoint` is ignored or rejected
- fallback to a public provider is disabled by default
- unavailable private runtime fails closed with `policy_fallback_forbidden` or `provider_unavailable`

A private-runtime fallback chain MAY contain multiple private routes only when explicitly configured.

### 15.5 Secret and content logging

Default observability MUST exclude:

- API keys and authorization headers
- service-account JSON
- raw prompts/messages
- raw model responses
- uploaded media bytes
- full local file paths

Operators MAY enable content logging only through explicit protected configuration with retention and access controls.

---

## 16. Fallback, retry, timeout, and circuit-breaker semantics

### 16.1 Observable fallback

Fallback MUST be explicit in configuration and observable in metadata.

`fallback_attempts` SHOULD contain:

- provider/model
- sanitized error class
- attempt latency
- whether a retry occurred

### 16.2 When fallback is allowed

Fallback MAY occur for:

- provider timeout
- rate limiting when retry budget is exhausted or another route is preferred
- transient provider unavailability
- configured capacity exhaustion
- malformed provider response when the adapter marks it transient

Fallback MUST NOT occur automatically for:

- invalid input
- missing/invalid credentials
- disallowed provider/model/endpoint
- content/safety rejection
- unsupported capability
- budget limit violation
- protected private-runtime failure unless policy explicitly allows it

### 16.3 Retry rules

- Retries occur inside one route before provider fallback.
- Retry count, backoff, and total time are bounded by route policy.
- Non-idempotent generation operations MUST NOT be retried unless the provider supports an idempotency key or the adapter can prove safe replay.
- Asynchronous create-task operations MUST use provider idempotency support where available.

### 16.4 Time budgets

The router SHOULD enforce:

- per-attempt timeout
- per-route retry budget
- total invocation deadline
- optional token/cost budget

A fallback attempt MUST NOT start when it cannot complete within the remaining deadline.

### 16.5 Circuit breaker

Adapters SHOULD support route-level circuit breakers keyed by configured route identity, not by untrusted raw endpoint.

Circuit state MUST NOT cause private-runtime traffic to escape to public providers unless policy already permits that fallback.

---

## 17. Asynchronous job contract

Video and other long-running providers require a normalized task model.

`invoke_video` MUST accept an operation:

- `create_task`
- `get_task`
- `list_tasks`
- `delete_task`
- `wait_for_task` when supported by runtime policy

Create response example:

```json
{
  "status": true,
  "data": {
    "task_id": "provider-task-id",
    "state": "queued",
    "poll_after_ms": 5000,
    "result": null
  },
  "message": "Video generation task created.",
  "metadata": {
    "selected_provider": "byteplus_modelark",
    "selected_model": "configured-video-model",
    "provider_request_id": "safe-request-id",
    "fallback_used": false
  }
}
```

Adapters MUST normalize provider states into:

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`
- `expired`

The router MUST preserve the provider task ID but MUST NOT imply task portability across providers. Fallback after task creation is prohibited unless the original task is known not to have been accepted.

Task operations MUST be authorized and scoped:

- persist tenant/project, route, provider, and creator ownership with the task receipt
- authorize `get_task`, `list_tasks`, and `delete_task` against that ownership
- never allow a caller to enumerate another tenant's provider tasks through a shared credential
- allow callback URLs only from operator configuration/allowlists
- verify provider callback signatures, timestamp/nonce freshness, and replay protection
- use a stable non-PII hash for provider safety/correlation identifiers
- avoid placing secrets or user content in callback URLs and correlation fields

---

## 18. Model listing and health

### 18.1 `list_models`

`list_models` MUST return the intersection of:

- models discoverable/configured for the provider
- the adapter's capability support
- organization/runtime allowlists
- the caller's authorized capabilities

It MUST NOT expose disallowed runtime models merely because a provider API lists them.

For static/private providers, configured allowlists are authoritative.

### 18.2 `health`

Health has two levels:

- **adapter readiness:** dependencies/config are loadable without spending provider credits where possible
- **provider readiness:** an optional bounded remote probe

Health output SHOULD identify missing configuration and dependency classes without exposing secret values.

---

## 19. Provider and connector migration matrix

### 19.1 `machina-ai`

| Existing command | Router mapping | Compatibility notes | Recommended route |
|---|---|---|---|
| `invoke_prompt` | `invoke_prompt`, chat factory | Preserve `api_key`, `model_name`, `organization`/`org_id`, `project`/`project_id`, and approved `base_url`. Existing calls return a model object in `data`. | `balanced`; repository default is Vertex AI |
| `invoke_embedding` | `invoke_embedding`, embedding factory | Preserve model factory behavior. | `balanced` embedding route |
| `transcribe_audio_to_text` | same canonical command | Preserve `headers.api_key` plus `params.audio-path`; add sandbox and file limits. | configured transcription route |

Gaps/current risks:

- current `base_url` is unrestricted and MUST become policy-controlled
- current errors sometimes use `status: "error"`; normalize to boolean
- current transcription assumes nested keys and the first file item; normalizer MUST validate safely
- connector YAML labels transcription as another human-readable Prompt command and SHOULD be corrected during implementation

A historical `machina-ai` request containing only an OpenAI API key/model cannot automatically become a Vertex call. Resolution MUST be deterministic:

1. use an explicitly allowed legacy OpenAI-compatible route bound to that credential; or
2. apply an operator-configured model and credential migration to Vertex; or
3. return a typed `credential_missing`/migration-policy error.

The router MUST NOT pretend that a provider remap can manufacture the Vertex `credential` and `project_id` required by the target route.

### 19.2 `machina-ai-fast`

| Existing command | Router mapping | Compatibility notes | Recommended route |
|---|---|---|---|
| `invoke_prompt` | `invoke_prompt` with `profile: fast` | Compatibility connector delegates to `machina-ai`; preserve legacy timeout conversion. | `fast`, normally Groq |
| `invoke_embedding` | reject or migrate explicitly | Current implementation returns `ChatGroq`, not an embedding model. It is not a valid embedding capability. Compatibility mode MAY preserve the historical loader only behind a named legacy flag, but the router MUST NOT advertise it as embeddings. | migrate to the configured embedding route |

The compatibility alias SHOULD inject `profile=fast` and MAY inject `provider=groq` only when no operator remap exists. Operator profile mapping remains authoritative.

### 19.3 `openai`

The current package is malformed legacy evidence, not a safe installable escape hatch: `connectors/openai/openai.yml` declares the connector identity `google-genai` while loading `openai.py`, which can collide with or replace the real Google connector. Its implementation also does not provide the organization/project/custom-`base_url` behavior exposed by `machina-ai`.

| Python command present | Intended router mapping | Required action before migration | Recommended route |
|---|---|---|---|
| `list_models` | `list_models` | fix connector identity and add install-collision test | explicit approved `openai` route |
| `invoke_prompt` | `invoke_prompt` / `invoke_chat` | inventory actual accepted parameters; do not inherit `machina-ai` claims | approved compatibility route |
| `invoke_embedding` | `invoke_embedding` | prove factory/direct behavior and output shape | approved embedding route |
| `transcribe_audio_to_text` | canonical transcription | add media sandbox and request-shape tests | configured transcription route |

The router MAY reuse code from `openai.py` after correction, but the current package MUST NOT be documented as an available provider-specific connector until its install identity is fixed and tested.

### 19.4 `azure-foundry`

| Existing command | Router mapping | Accepted compatibility | Unsupported gaps | Recommended route |
|---|---|---|---|---|
| `invoke_prompt` | `invoke_prompt` / `invoke_chat` | `endpoint`/`azure_endpoint`, `deployment`/`azure_deployment`, `api_version`, credential aliases | deployment is not interchangeable with a generic model ID | explicit provider or approved cloud profile |
| `invoke_embedding` | `invoke_embedding` | same Azure route fields | capability depends on configured deployment | configured Azure embedding route |

Endpoint and deployment MUST be bound by policy in protected production environments.

### 19.5 `google-genai`

| Existing command | Router mapping | Compatibility notes | Recommended route |
|---|---|---|---|
| `invoke_prompt` | `invoke_prompt` / `invoke_chat` | preserve `provider=vertex_ai|ai_studio`, `credential`, `project_id`, `location`, API key for AI Studio, priority mode, timeout conversion | `balanced`, `quality`, `long_context` |
| `invoke_embedding` | `invoke_embedding` | preserve Vertex credential/project aliases and current legacy model remapping where explicitly enabled | default embedding route |
| `invoke_search` | `invoke_search` | preserve Gemini grounding/search options | `search_answer` remap or `multimodal` |
| `invoke_image` | `invoke_image` | normalize prompt, image inputs, output path | `multimodal` |
| `invoke_video` | `invoke_video` | normalize long-running result/task semantics | preview multimodal/video |
| `invoke_tts` | `invoke_tts` | normalize audio outputs and voices | preview TTS |
| `invoke_clone_instant_voice`, `invoke_train_pro_voice`, `invoke_synthesize_custom_voice` | provider extensions | expose only when Google-specific voice lifecycle is requested | explicit provider extension |
| `invoke_music` | `invoke_music` | normalize output receipt | preview music |

Google custom voice operations remain provider-specific extensions because voice enrollment/training lifecycles are not portable.

### 19.6 `vertex-embedding`

| Existing command | Router mapping | Compatibility notes | Recommended route |
|---|---|---|---|
| `invoke_embedding` | same | preserve model factory behavior and Vertex project/location/credential aliases | default embedding |
| `embed_query` | same alias | direct single-query vector | default embedding |
| `embed_documents` | same alias | direct vector list | default embedding |

Default model remains `text-embedding-004` unless runtime configuration changes it.

### 19.7 `groq`

| Existing command | Router mapping | Compatibility notes | Gaps | Recommended route |
|---|---|---|---|---|
| `list_models` | `list_models` | filtered through allowlists | none if configured | `fast` |
| `invoke_prompt` | `invoke_prompt` / `invoke_chat` | preserve API key/model aliases; legacy timeout conversion is supplied by the router/`machina-ai-fast` normalizer, not the current standalone Groq connector | model defaults belong in config, not code | `fast` |
| `invoke_embedding` | capability-gated | expose only if the configured Groq adapter genuinely supports embeddings | do not repeat `machina-ai-fast` fake embedding behavior | configured embedding route instead |

### 19.8 `grok`

| Observed command | Router mapping | Compatibility notes | Recommended route |
|---|---|---|---|
| `post-chat/completions` | `invoke_chat` | map JSON API messages, model, temperature, max tokens, and response format; streaming remains unsupported in router v1 | explicit `xai` or approved quality profile |
| `post-responses` | `invoke_chat` with declared tools/search capability | preserve supported web/X search and code-interpreter inputs under explicit capability/tool policy | explicit `xai` route |

JSON connector path/header parameters MUST be normalized without forwarding unknown headers. Search/tool use MUST be observable in metadata and MUST NOT be inferred merely from provider choice.

### 19.9 `perplexity`

| Existing operation | Router mapping | Compatibility notes | Recommended route |
|---|---|---|---|
| chat/search-style completion | `invoke_search` by default; `invoke_chat` when search semantics are not required | normalize citations/search result metadata when available | search_answer profile |

The adapter SHOULD return citations/sources as structured data rather than flattening them into message text.

### 19.10 `nvidia-nim`

NVIDIA NIM is a merged provider-specific connector and a required v1 target.

| Existing command | Router mapping | Compatibility notes | Recommended route |
|---|---|---|---|
| `health` | `health` | preserve runtime readiness checks | `private_runtime` / `open_source` |
| `list_models` | `list_models` | return configured allowlist intersection | same |
| `invoke_chat` | `invoke_prompt`, operation mode `factory` | existing NIM command returns a configured `ChatOpenAI` model object; migration MUST NOT reinterpret it as direct execution | same |
| `completion_receipt` | `invoke_chat`, operation mode `execute`, plus canonical metadata receipt | preserve completion content, usage, model, latency, and safe provider request metadata | same |

The router MUST copy the NIM connector's allowlist and fail-closed semantics, not merely its OpenAI-compatible request syntax. Canonical router `invoke_chat` remains direct execution; source connector identity resolves the legacy NIM command collision.

### 19.11 `byteplus-modelark`

| Existing operation | Router mapping | Compatibility notes | Recommended route |
|---|---|---|---|
| `post-contents/generations/tasks` | `invoke_video(operation=create_task)` | normalize async task receipt | explicit video route |
| `get-contents/generations/tasks/{task_id}` and path-ID variants | `invoke_video(operation=get_task)` | normalize task state and enforce task ownership | same |
| `get-contents/generations/tasks` | `invoke_video(operation=list_tasks)` | preserve pagination under normalized data and scope results to tenant/route ownership | same |
| delete path-ID task operation | `invoke_video(operation=delete_task)` | destructive task deletion remains explicit and authorized | same |

Provider-specific video controls remain under `options.provider_options` when no portable equivalent exists.

### 19.12 `stability`

| Existing command | Router mapping | Compatibility notes | Recommended route |
|---|---|---|---|
| `generate_image` | `invoke_image` / `generate_image` alias | normalize prompt, dimensions/aspect, image inputs, seed, output path, and artifact receipt | `multimodal` image route |

Unsupported edit/upscale operations MUST be reported rather than silently treated as text-to-image.

### 19.13 `elevenlabs`

| Existing command | Router mapping | Compatibility notes | Recommended route |
|---|---|---|---|
| `get_text_to_speech` | `invoke_tts` | normalize voice ID, model, output format, and file receipt | explicit TTS route |
| `get_voices` | provider extension `list_voices` | voice catalogs are provider-specific | explicit ElevenLabs |

Voice cloning and voice identity are not portable abstractions. They remain provider extensions with explicit consent, storage, and lifecycle requirements.

### 19.14 `google-speech-to-text`

| Existing command | Router mapping | Compatibility notes | Recommended route |
|---|---|---|---|
| `invoke_transcribe` | `transcribe_audio_to_text` / alias | normalize credential/project/audio/language options | configured transcription route |

The router may route transcription between Google and an approved OpenAI-compatible provider, but credentials and media must be rebound per route.

### 19.15 `docling`

Docling remains outside the AI model router.

Reason:

- its primary contract is document loading, parsing, and preprocessing
- routing it as a generative model would blur ingestion and model-execution boundaries
- document parsing has different file, resource, and output semantics

A future ingestion orchestrator MAY call Docling before the AI router, but `load_documents` is not an AI router capability.

### 19.16 Reuse blockers in current implementations

Existing provider code MUST NOT be copied into router adapters without regression fixes:

- `vertex-embedding` currently logs a prefix of service-account credential material; the adapter must remove this and tests must assert that no credential fragment reaches logs.
- `google-speech-to-text` accepts an arbitrary credential filesystem path and downloads arbitrary HTTP URLs without sufficient redirect, timeout, and size controls; the adapter must use the credential and remote-media policies in Sections 8.6 and 15.
- `stability` uses caller-controlled image identifiers in output paths; the adapter must sanitize/generated filenames and enforce sandbox containment.
- ElevenLabs currently exposes output paths and raw exception text in logs/errors; the adapter must sanitize both.

These are mandatory migration blockers, not optional cleanup.

---

## 20. `machina-ai-fast` compatibility strategy

Keep `connectors/machina-ai-fast` as a thin delegating connector during migration.

Conceptual behavior:

```python
def invoke_prompt(params):
    normalized = dict(params or {})
    normalized.setdefault("profile", "fast")
    return machina_ai.invoke_prompt(normalized)
```

Rules:

- explicit caller profile MAY override the alias only if policy permits
- global `fast` profile remapping takes precedence over hardcoded Groq coupling
- missing provider credentials return the router's normalized error
- legacy timeout conversion remains supported
- `invoke_embedding` MUST be corrected, deprecated with a clear error, or placed behind an explicit legacy-bug compatibility mode; it MUST NOT claim a real Groq embedding implementation when it returns a chat model

The alias may be removed only after repository and production telemetry show no remaining calls for an agreed deprecation window.

---

## 21. Backward-compatibility rules

### Rule 1: existing `machina-ai` factory shapes remain accepted

Prompt and embedding calls with the current flattened parameter shape MUST remain parseable. They continue to load models when an allowed route can bind compatible credentials/model configuration; otherwise they return the deterministic typed migration/policy error defined in Section 19.1.

### Rule 2: existing transcription envelope remains accepted

`headers.api_key` and `params.audio-path` remain readable, with added validation.

### Rule 3: aliases are additive

`model_name`, `org_id`, `project_id`, `audio-path`, Azure aliases, and provider-specific legacy names remain accepted during migration.

### Rule 4: current workflows do not need provider rewrites immediately

Provider-specific connectors remain installable and callable.

### Rule 5: security fixes override insecure legacy behavior

Backward compatibility does not require accepting arbitrary endpoints, leaking raw exceptions, reading files outside approved roots, or forwarding credentials across providers.

### Rule 6: response metadata is additive

Existing `status`, `data`, and `message` fields remain. `metadata` is added consistently.

### Rule 7: output equivalence is structural, not semantic

Migration guarantees compatible command and envelope behavior. It does not guarantee word-for-word output across models/providers.

---

## 22. Observability

The router SHOULD emit metrics and structured logs for:

- invocations by capability/profile/provider/model
- route-selection reasons
- success/error class
- latency by attempt and total invocation
- retries and fallback usage
- token/character/audio-second usage where available
- policy rejections
- circuit-breaker state
- asynchronous task state transitions

Recommended correlation fields:

- router invocation ID
- workflow execution ID
- task ID
- provider request ID when safe
- route configuration version

Prompt and response content MUST be excluded by default.

`completion_receipt`-style data SHOULD become part of the standard metadata receipt rather than requiring every workflow to call a second provider-specific command.

---

## 23. Dependency and readiness policy

Because connector-level dependency manifests are not currently authoritative, the router implementation MUST define supported dependency ranges for its adapters.

At startup or health check, the registry SHOULD report:

- adapter import success/failure
- installed client/library version when safe
- required configuration present/missing
- enabled capabilities
- disabled capabilities with sanitized reasons

A missing optional media dependency MUST disable only the affected adapter/capability, not the entire router, unless it is required by runtime policy.

---

## 24. Testing strategy

CI/unit tests MUST NOT require live provider credentials.

### 24.1 Normalization tests

- flattened legacy parameters
- `params`, `headers`, and `path_attribute`
- alias precedence and conflicts
- `model`/`model_name`
- organization/project aliases
- Azure endpoint/deployment aliases
- legacy timeout seconds/milliseconds conversion
- nested transcription file inputs
- canonical request parsing

### 24.2 Routing tests

- explicit provider override wins when allowed
- explicit disallowed provider/model fails
- profile-based route selection
- repository default resolves to Vertex AI
- global provider remap
- capability inference from command
- ambiguous capability rejection
- missing capability adapter rejection
- model allowlist filtering

### 24.3 Fallback tests

- transient provider failure uses configured fallback
- metadata records attempts and final route
- authentication failure does not fall back
- invalid request does not fall back
- private-runtime/NIM failure fails closed
- deadline prevents a late fallback
- credentials are independently rebound for fallback

### 24.4 Security tests

- arbitrary `base_url` rejected
- allowed endpoint accepted
- loopback/link-local/metadata endpoint rejected
- NIM endpoint cannot be overridden by workflow
- disallowed NIM model rejected before client creation
- credentials absent from logs/errors/metadata
- raw prompt absent from default logs
- path traversal rejected
- oversized/invalid media rejected
- redirects do not receive credentials

### 24.5 Adapter contract tests

At minimum, mocked/offline tests MUST cover:

- OpenAI-compatible chat factory and execution
- embedding factory and execution
- Groq fast chat
- Azure Foundry chat
- Vertex/Gemini chat and embeddings
- NVIDIA NIM chat and allowlist behavior
- Perplexity or Gemini search_answer
- transcription
- one generated multimodal adapter
- health and model listing
- sanitized provider errors
- usage/request-ID metadata extraction

### 24.6 Compatibility tests

- current `machina-ai.invoke_prompt` shape
- current `machina-ai.invoke_embedding` shape
- current `machina-ai.transcribe_audio_to_text` shape
- current `machina-ai-fast.invoke_prompt` shape and timeout behavior
- compatibility alias delegates to `profile=fast`
- existing `status`, `data`, and `message` keys remain present

### 24.7 Smoke tests

Before production rollout:

- run at least one real configured provider smoke test plus one mocked/offline path during initial development
- run a staging smoke test for every route enabled as GA in the target environment
- exercise both Vertex chat and Vertex embeddings
- exercise model factory integration inside actual Machina prompt and document tasks
- verify receipt metadata and absence of secrets/raw prompt logs
- exercise NIM/private-runtime factory loading, completion receipt execution, and rejection with a disallowed model or endpoint override

Live smoke tests MUST be opt-in in generic CI and skipped cleanly when credentials are absent, but a route MUST NOT be marked GA in an environment without its successful staging smoke receipt.

### 24.8 Inventory, packaging, and lint tests

- every declared connector command is mapped, deprecated, or excluded
- every command string observed in workflow YAML is mapped or flagged as broken
- connector install/load succeeds with nested modules or the selected compatible bundle design
- connector identities do not collide, including the malformed current `openai` package
- canonical runnable YAML examples pass `scripts/check-no-openai.sh all`
- factory objects load through real prompt and document runtime integrations

### 24.9 Configuration and async authorization tests

- configuration schema rejects unknown security-sensitive fields
- layered precedence is deterministic: runtime > organization > project > repository defaults
- request credentials/endpoints cannot shadow operator bindings
- remote-media URL SSRF, redirects, DNS rebinding, timeout, size, and content-type controls
- arbitrary credential paths are rejected
- async task get/list/delete enforce tenant/project ownership
- callbacks require allowlisted URLs, valid signatures, freshness, and replay protection

---

## 25. Acceptance criteria traceability

| Acceptance criterion | Spec coverage |
|---|---|
| Existing `machina-ai` prompt/embedding call shape works | Sections 7, 8, 19.1, 21, 24.6 |
| `machina-ai-fast` represented by `profile=fast` or alias | Sections 12.4, 19.2, 20 |
| Chat/prompt, embedding, fast, NIM, Azure, both Vertex chat and embeddings, multimodal tests | Sections 2.1, 24.5, and 24.7 |
| Migration table covers all requested connectors | Section 19 |
| Explicit override/profile/remap/fallback tests | Sections 12–16 and 24.2–24.3 |
| Disallowed endpoint/model rejection | Sections 15 and 24.4 |
| Backward-compatible parameter extraction | Section 8 and 24.1 |
| Sanitized errors | Sections 9.4, 15.5, 24.4–24.5 |
| Metadata receipt | Sections 9, 22, 24.5 |
| Real plus offline smoke tests | Section 24.7 |
| Canonical examples pass repository lint | Sections 4 and 24.8 |
| Declared/observed command inventory parity | Sections 7.4 and 24.8 |
| Connector packaging and identity collision safety | Sections 6.1, 19.3, and 24.8 |
| Remote-media and credential-path security | Sections 8.6, 19.16, and 24.9 |
| Async task ownership and callback authentication | Sections 17 and 24.9 |
| Valid provider-specific connectors remain available; malformed packages are fixed before being advertised | Sections 1, 3.2, 19.3, and 21 |

---

## 26. Delivery phases

### Phase 0: inventory and contract tests

- freeze the command/capability registry
- add compatibility fixtures from existing connectors
- identify active workflow references and response assumptions
- generate declared-command and observed-command inventory
- approve the narrow `machina-ai` repository policy/lint change, or choose a different public facade before implementation
- prove connector packaging/import behavior and identity collision checks
- define router configuration ownership and loading path

### Phase 1: core router and compatibility facade

- parameter normalizer
- canonical envelope/errors/receipts
- policy engine and adapter registry
- Vertex/Gemini default adapter
- OpenAI-compatible compatibility adapter
- Azure Foundry adapter
- Groq `fast` adapter
- NIM protected adapter preserving merged `invoke_chat` factory and `completion_receipt` execution semantics
- `machina-ai-fast` delegating alias
- chat/prompt and embedding factory compatibility
- health/list models

### Phase 2: search and required legacy/multimodal routes

- Perplexity/Gemini search_answer
- transcription compatibility and Google Speech adapter
- one image generation adapter through Google or Stability
- media sandbox and artifact receipts

### Phase 3: asynchronous and voice modalities

- BytePlus/Google video task adapters
- TTS through Google/ElevenLabs
- provider-specific voice lifecycle extensions
- music generation preview

### Phase 4: migration and deprecation review

- publish workflow migration examples
- measure router/provider-specific connector usage
- migrate candidates capability by capability
- retain provider connectors as explicit escape hatches
- deprecate aliases only after telemetry, compatibility tests, and an announced window

---

## 27. Configuration examples

### 27.1 Local development with an approved mock/offline adapter

```yaml
version: 1
policy:
  default_profile: balanced
  allow_workflow_credentials: false
providers:
  offline:
    adapter: mock
    allowed_models:
      chat: [mock-chat]
      embedding: [mock-embedding]
profiles:
  balanced:
    chat: [{provider: offline, model: mock-chat}]
    embedding: [{provider: offline, model: mock-embedding}]
```

### 27.2 Default cloud route

```yaml
providers:
  vertex_ai:
    adapter: google_genai
    credential_ref: TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL
    project_ref: TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID
    location: global
profiles:
  balanced:
    chat: [{provider: vertex_ai, model: gemini-2.5-flash}]
    embedding: [{provider: vertex_ai, model: text-embedding-004}]
```

### 27.3 Fast/Groq

```yaml
providers:
  groq:
    adapter: groq
    credential_ref: TEMP_CONTEXT_VARIABLE_GROQ_API_KEY
    allowed_models:
      chat: [configured-fast-model]
profiles:
  fast:
    chat: [{provider: groq, model: configured-fast-model}]
```

### 27.4 Azure Foundry

```yaml
providers:
  azure_foundry:
    adapter: azure_foundry
    credential_ref: TEMP_CONTEXT_VARIABLE_AZURE_OPENAI_API_KEY
    endpoint_ref: TEMP_CONTEXT_VARIABLE_AZURE_OPENAI_ENDPOINT
    api_version: configured-api-version
    deployments:
      chat-quality:
        deployment: configured-chat-deployment
        capability: chat
```

### 27.5 NIM/private runtime

```yaml
providers:
  nvidia_nim:
    adapter: nvidia_nim
    protected: true
    endpoint_env: NVIDIA_NIM_CHAT_BASE_URL
    credential_env: NVIDIA_NIM_CHAT_API_KEY
    allowed_models_env: NVIDIA_NIM_CHAT_ALLOWED_MODELS
    default_model_env: NVIDIA_NIM_CHAT_MODEL
    fail_closed: true
profiles:
  private_runtime:
    chat: [{provider: nvidia_nim}]
fallbacks:
  chat:
    nvidia_nim: []
```

### 27.6 Image route

```yaml
providers:
  stability:
    adapter: stability
    credential_ref: TEMP_CONTEXT_VARIABLE_STABILITY_API_KEY
    allowed_models:
      image: [configured-image-model]
profiles:
  multimodal:
    image: [{provider: stability, model: configured-image-model}]
```

### 27.7 Video route

```yaml
providers:
  byteplus_modelark:
    adapter: byteplus_modelark
    credential_ref: TEMP_CONTEXT_VARIABLE_BYTEPLUS_MODELARK_API_KEY
    allowed_models:
      video: [configured-video-model]
profiles:
  multimodal:
    video: [{provider: byteplus_modelark, model: configured-video-model}]
```

---

## 28. Migration guidance for workflow authors

### Existing `machina-ai`

No immediate call-shape change is required.

New workflows SHOULD request a profile/capability and rely on the configured default rather than embedding provider credentials in workflow YAML.

### Existing `machina-ai-fast`

Conceptual runtime form after the approved facade policy/lint change:

```yaml
connector:
  name: machina-ai
  command: invoke_prompt
  profile: fast
```

This is not currently valid committed repository YAML: `machina-ai` is blocked by lint under the Vertex-only repository policy. The Groq-backed `fast` route ships enabled in the repository default router config for no-regression with `machina-ai-fast`, but it activates only when the operator provisions `TEMP_CONTEXT_VARIABLE_GROQ_API_KEY` (or the SDK alias) in the runtime environment; workflow-supplied Groq credentials remain disabled, and an absent credential fails with a typed `credential_missing` error. The compatibility alias exists primarily so already-installed or legacy workflows do not break during rollout. Canonical committed examples MUST use the approved router syntax with an effective Vertex default and pass `scripts/check-no-openai.sh all`.

### Provider-specific connectors

Keep the provider-specific connector when the workflow intentionally depends on:

- a provider-specific endpoint or response format
- model-specific tuning with no router mapping
- custom voice lifecycle
- provider task administration
- unsupported media operations
- debugging or certification against one vendor

Use `machina-ai` when the workflow wants a capability and accepts an operator-selected approved route.

---

## 29. Open implementation questions

These questions must be answered before implementation, but they do not change the contract above:

1. Where is router policy stored and versioned: connector config document, project manifest extension, runtime environment, or a layered combination?
2. Which platform component owns organization-level overrides and authorization to edit them?
3. Which current workflows inspect provider-specific model object types or response fields?
4. Which generated multimodal adapter is the first GA proof: Google image or Stability?
5. What deprecation window and telemetry threshold are required before removing `machina-ai-fast`?
6. Should direct execution and in-process factory operations share one adapter client instance/cache, and what are the lifecycle/thread-safety rules?
7. Will the connector installer support nested modules, or must v1 ship as a bundled single-file artifact?

Recommended defaults:

- layered config: runtime policy > organization policy > project policy > repository defaults
- runtime policy is authoritative for protected routes
- Stability or Google image is the first generated multimodal proof based on available production credentials
- no alias removal until there are zero observed calls for at least one full release/deprecation window

---

## 30. Summary

`machina-ai` becomes the preferred provider-independent AI facade while preserving the current model-factory contract.

The design:

- defaults new repository usage to Vertex AI
- consolidates fast routing through a profile and compatibility alias
- standardizes chat, embedding, search, transcription, media, health, and model discovery contracts
- keeps multimodal extensibility without forcing every adapter into the first milestone
- permits global remapping without workflow rewrites
- makes fallback observable and policy-controlled
- preserves NIM/private-runtime fail-closed security
- normalizes legacy envelopes and aliases
- keeps provider connectors available for explicit provider-specific needs

This gives workflows a stable capability contract while letting operators change approved providers, models, credentials, and runtime targets centrally.
