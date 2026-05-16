# Project rules for AI assistants (Claude Code, etc.)

These rules apply to every change you make in this repo. Read before editing.

## LLM provider: Vertex AI only — no OpenAI

This repo runs on **Google Vertex AI** via the `google-genai` connector.
**Do not introduce OpenAI / GPT / `text-embedding-3-*` references** in
workflows, prompts, or manifests. The OpenAI account is deprecated; any new
workflow that talks to it will silently 401 in production (incident
2026-05-16 — `botandwin-stg` outage).

A repo-wide lint (`scripts/check-no-openai.sh`) runs in CI and as a
pre-commit hook and rejects the following patterns in `*.yml` / `*.yaml`
files outside the exempted dirs:

| Banned                                                                          | Use instead                                                                                 |
|---------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| `name: openai` / `name: machina-ai` (in a `connector:` block)                  | `name: google-genai` + `location: "global"` + `provider: "vertex_ai"`                       |
| `model: text-embedding-3-small` / `-large` / `text-embedding-ada-002`           | `model: text-embedding-004`                                                                 |
| `model: gpt-4o-mini` / `gpt-4.1-mini` / `gpt-3.5-turbo`                         | `model: gemini-2.5-flash`                                                                   |
| `model: gpt-4` / `gpt-4o` / `gpt-4.1`                                           | `model: gemini-2.5-pro`                                                                     |
| `$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY` / `$MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY` | `$TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL` + `$TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID` |
| context-variable block `openai:` / `machina-ai:` with `api_key:`               | `google-genai:` with `credential:` + `project_id:`                                          |

Exempted paths (the legacy connector definitions themselves and the
migration tooling):

- `connectors/openai/**`
- `connectors/machina-ai/**`
- `scripts/**`
- `.githooks/**`
- `.github/workflows/lint-no-openai.yml`

If a workflow legitimately needs OpenAI in the future, do not bypass the
lint with skip-flags. Open a discussion first.

## Canonical Vertex pattern

```yaml
workflow:
  context-variables:
    google-genai:
      credential: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL
      project_id: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID

  tasks:
    # Embedding
    - type: document
      connector:
        name: google-genai
        command: invoke_embedding
        model: text-embedding-004
        location: "global"
        provider: "vertex_ai"

    # Prompt
    - type: prompt
      connector:
        name: google-genai
        command: invoke_prompt
        model: gemini-2.5-flash       # or gemini-2.5-pro for higher quality
        location: "global"
        provider: "vertex_ai"
```

Reference implementation: `connectors/google-genai/test-credentials.yml`.

## Enabling the local hook

```bash
git config core.hooksPath .githooks
```

Once. After that, `git commit` runs `scripts/check-no-openai.sh staged`
and fails the commit if a banned pattern was reintroduced.

## Migration helper

If you inherit a workflow that still has OpenAI references:

```bash
python3 scripts/migrate-openai-to-vertex.py --apply --paths path/to/file.yml
```

Idempotent; safe to run on already-migrated files.
