# Project rules for AI assistants (Claude Code, etc.)

These rules apply to every change you make in this repo. Read before editing.

## LLM provider: Vertex AI default; no hardcoded OpenAI routes

This repo runs on **Google Vertex AI** by default, either directly through the
`google-genai` connector or through the policy-governed `machina-ai` router.
Do not introduce direct OpenAI/GPT/`text-embedding-3-*` routes in workflows,
prompts, or manifests. The deprecated OpenAI account silently 401s in
production (incident 2026-05-16 — `botandwin-stg` outage).

The `machina-ai` facade is the only narrow exception to the old connector-name
ban. It is allowed only because its repository defaults resolve to Vertex AI
and `scripts/check-machina-ai-policy.py` structurally rejects workflow-owned
provider credentials/endpoints, non-Vertex provider overrides, non-default
profiles such as `fast`, and unknown commands. Provider-specific adapters in
its implementation do not change the repository default.

A repo-wide lint (`scripts/check-no-openai.sh`) runs in CI and as a pre-commit
hook. It continues to reject:

| Banned | Use instead |
|---|---|
| `name: openai` in a workflow connector block | `name: google-genai` or policy-governed `name: machina-ai` |
| `model: text-embedding-3-small`, `text-embedding-3-large`, or `text-embedding-ada-002` | `model: text-embedding-004` |
| hardcoded GPT model routes | `gemini-2.5-flash` or `gemini-2.5-pro` |
| deprecated OpenAI context-variable secrets | runtime-bound Vertex credential and project configuration |
| `machina-ai` with `api_key`, `credential`, `base_url`, `endpoint`, deployment, remap, or fallback fields | bind credentials/endpoints/remaps/fallbacks in operator-controlled router policy |
| `machina-ai` with a non-Vertex provider or non-default profile such as `fast` | omit provider/profile or use an allowed Vertex-backed profile |

Exemptions are limited to legacy/provider connector definitions and migration
or lint tooling. They do not permit new workflows to call direct OpenAI/GPT
routes. If a workflow legitimately needs a non-Vertex route, do not add a skip
flag or caller endpoint; obtain an explicit operator policy decision first.

## Canonical Vertex patterns

Direct connector:

```yaml
workflow:
  context-variables:
    google-genai:
      credential: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL
      project_id: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID

  tasks:
    - type: document
      connector:
        name: google-genai
        command: invoke_embedding
        model: text-embedding-004
        location: "global"
        provider: "vertex_ai"

    - type: prompt
      connector:
        name: google-genai
        command: invoke_prompt
        model: gemini-2.5-flash
        location: "global"
        provider: "vertex_ai"
```

Policy-governed facade (credentials and endpoints are runtime-owned):

```yaml
workflow:
  tasks:
    - type: prompt
      connector:
        name: machina-ai
        command: invoke_prompt
        provider: vertex_ai
        model: gemini-2.5-flash
        profile: balanced
```

Reference implementations: `connectors/google-genai/test-credentials.yml` and
`connectors/machina-ai/test-credentials.yml`.

## Enabling the local hook

```bash
git config core.hooksPath .githooks
```

Once. After that, `git commit` runs `scripts/check-no-openai.sh staged` and
fails the commit if a banned or unsafe AI route was introduced.

## Migration helper

If you inherit a workflow that still has direct OpenAI references:

```bash
python3 scripts/migrate-openai-to-vertex.py --apply --paths path/to/file.yml
```

Idempotent; safe to run on already-migrated files.
