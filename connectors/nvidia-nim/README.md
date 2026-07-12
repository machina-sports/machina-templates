# NVIDIA NIM connector

Chat inference on an NVIDIA NIM endpoint (OpenAI-compatible `/v1`), for the
Machina private runtime. The endpoint and the model allowlist are
**operational config** — injected on the runtime by the deployment, never
supplied by workflow YAML. A template may choose a model *within* the
allowlist; it cannot point the runtime at an arbitrary URL (the connector
fails closed on any `base_url` coming from a workflow).

## Environment (operational config)

| Env | Required | Meaning |
|---|---|---|
| `NVIDIA_NIM_CHAT_BASE_URL` | yes | NIM endpoint, e.g. `http://nemotron-nim:8001/v1` |
| `NVIDIA_NIM_CHAT_MODEL` | yes | Default model, e.g. `nvidia/nemotron-3-super-120b-a12b` |
| `NVIDIA_NIM_ALLOWED_MODELS` | no | CSV allowlist; defaults to just the default model |
| `NVIDIA_NIM_TIMEOUT_SECONDS` | no | Request timeout (default 70 — Nemotron with reasoning needs >18s for structured answers) |
| `NVIDIA_NIM_MAX_OUTPUT_TOKENS` | no | Hard cap applied to `max_tokens` |
| `NVIDIA_NIM_API_KEY` | no | Local NIMs don't validate it |

Embeddings are deliberately **separate**: the retrieval facade on
machina-client-api owns them under the `RETRIEVAL_NIM_*` envs. This
connector is chat only.

## Commands

- `invoke_chat` (Prompt) — returns a LangChain `ChatOpenAI` wired to the NIM
  endpoint; the engine runs the prompt against it. Honors `model_name`
  (allowlist-checked), `temperature`, `max_tokens` (capped by
  `NVIDIA_NIM_MAX_OUTPUT_TOKENS`).
- `list_models` — models served by the endpoint alongside the allowlist.
- `health` — private-runtime receipt: operational config present, endpoint
  reachable, default model served. Used by the
  `nvidia-nim-test-credentials` workflow.

## Usage in a workflow prompt task

```yaml
- type: prompt
  name: my-analysis
  connector:
    name: nvidia-nim
    command: invoke_chat
    model: nvidia/nemotron-3-super-120b-a12b   # must be in the allowlist
```
