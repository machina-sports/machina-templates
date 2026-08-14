# Project rules for AI assistants (Claude Code, etc.)

These rules apply to every change you make in this repo. Read before editing.

## LLM provider routing

Google Vertex AI remains the repository default, either directly through the
`google-genai` connector or through the `machina-ai` router. Provider-specific
connectors, SDKs, adapters, and compatibility routes remain supported when a
workflow explicitly selects them.

The `machina-ai` facade remains governed by
`scripts/check-machina-ai-policy.py`, which rejects workflow-owned credentials
and endpoints plus unsupported provider, profile, model, and command overrides.
Those controls protect operator-owned routing independently of provider choice.

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
