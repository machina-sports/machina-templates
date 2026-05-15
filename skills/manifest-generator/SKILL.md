# Project Manifest Generator

Generates a draft `project.manifest.yml` for a Machina template by statically
scanning a list of workflows and aggregating the credentials, connectors,
datasets and agents they reference.

Built to scale **Sprint 1A** of the Pipeline Platform Cleanup (the hand-written
botandwin manifest at `entain-templates`) to every template in
`machina-templates` without writing each one by hand.

## What it does

1. **Deterministic extraction (always)** — a pyscript connector walks each
   workflow_object in your list and emits the union of:
   - `TEMP_CONTEXT_VARIABLE_*` → credentials
   - `task.connector.name` for `type=connector|prompt` tasks → connector deps
   - `task.config.action == "search"` → dataset reads (external deps)
   - `task.config.action == "update|insert|save"` → dataset writes (deps_on)
   - `type=agent` references → agents
   - `type=workflow` references → workflow calls (for `extends`-like inheritance)

2. **Optional LLM enrichment** — pass `enrich_with_llm=true` and a
   Gemini/Vertex AI call fills in:
   - `source_label` ("OpenAI API key (platform.openai.com)" etc)
   - `test_workflow` ("<connector>-test-credentials")
   - `validation` rule (http for *_API_KEY, json_object for service-account JSON,
     non_empty_string for generic strings)
   - dataset `description` + `populated_by` guesses

3. **Output** — writes a `<template_name>-manifest-draft` document into
   the `document` collection. Operator opens it in Studio, eyeballs the
   suggested values, edits, then copies the `manifest` field into the
   real `project.manifest.yml` for commit.

## How to run

Install this skill into your project (via Studio template browser), then:

```bash
POST /workflow/executor/generate-project-manifest
Content-Type: application/json

{
  "workflow_names": [
    "machina-assistant-thread-create",
    "machina-assistant-thread-respond",
    "machina-assistant-kb-search"
  ],
  "template_name": "machina-assistant",
  "description": "Foundational AI assistant for Machina platform",
  "enrich_with_llm": true
}
```

Response carries `manifest_draft_doc_name`. Fetch with:

```bash
POST /document/search
{ "filters": { "name": "machina-assistant-manifest-draft" }, "page_size": 1 }
```

## Limitations (V1)

- Doesn't fetch workflow YAMLs from a Git repo — works against the
  workflows already imported into your project. To scan a template you
  haven't installed yet: import it first.
- Heuristic dataset detection (same caveats as
  `core/workflow/dependency_graph.py` — `$.get('xxx')` is mostly inferred
  from `type=document` tasks now, not just regex).
- LLM enrichment is best-effort. Always review the draft before commit.

## Roadmap

- **V2**: clone-from-git input so you can manifest a template without
  installing it.
- **V3**: bulk mode — scan an entire repo and emit one PR per template.
- **V4**: hook into `core/dataset/controller.py:process_install_file`
  so installing a template auto-generates + offers a draft manifest.

## Related

- `agent-templates/machina-assistant/project.manifest.yml` (hand-written reference)
- `docs/project-manifest-guide.md` (schema reference)
- machina-client-api `/project/health`, `/bootstrap-check`, `/workflow/<id>/dependencies`
