# Project Manifest — Adoption Guide

Adding `project.manifest.yml` next to a template's `_install.yml` makes that
template **observable** by the Project Health endpoints + Pipeline Visualizer
in Studio. Operators get blockers/warnings/oks instead of grepping logs.

## What a manifest declares

```yaml
name: <project-or-template-name>
version: 1
description: "One-liner so future operators know what this is for"

required_credentials:
  - name: TEMP_CONTEXT_VARIABLE_<NAME>          # vault key name
    source_label: "Where the operator gets it"  # shown in /project/health
    test_workflow: <slug>-test-credentials      # workflow that exercises the key
    validation:                                  # optional — runs on vault save + the Studio "Validate" button
      type: http | json_object | non_empty_string
      # http:
      url: "https://api.example.com/probe?key={value}"
      method: GET
      expect_status: 200
      headers:
        Authorization: "Bearer {value}"
      # json_object:
      required_keys: [project_id, private_key, ...]

required_config_documents:
  - name: <doc-name-in-mongo>
    description: "What it holds"
    example_path: "configs/<file>.example.json"   # optional, relative to template root

required_templates:
  - repo: https://github.com/<org>/<repo>
    path: <relative/path>
    reason: "Why this is a hard dep"

depends_on_datasets:
  - name: <document.name in Mongo>
    description: "What this dataset is"
    populated_by: <workflow-name>
    min_count: 50                                  # /project/health flags red if below
```

## How it gets consumed

1. **`/project/health`** — passive snapshot. Cross-references each
   `required_credentials[]` against the project's vault, each
   `required_config_documents[]` against the `document` collection, each
   `depends_on_datasets[]` count vs the declared `min_count`.

2. **`/project/bootstrap-check`** — preflight. Same primitives, classified as
   blockers/warnings/oks. With `trigger_tests=true` it actively fires the
   `test_workflow` for each credential.

3. **`/vault/validate`** — Studio "Validate" button. Probes the credential
   against its declared `validation` rule before persisting.

4. **`/workflow/<id>/dependencies`** — Pipeline Visualizer DAG. Status of
   every dataset/credential node in the graph comes from the manifest cross-check.

## How to install a manifest into a project

The loader checks two places (in order):

1. **Mongo** — collection `project_manifest`, doc shape `{ name: <project>, manifest: <parsed YAML> }`. Editable at runtime, no rebuild.
2. **Bundled file** — `core/system/manifests/bundled/<key>.yml` in the
   client-api image. Falls back to filename matching project name (strips
   env suffixes: `-production`, `-prod`, `-stg`, `-dev`).

To install:

```bash
# Option A: upsert into Mongo via the document API
curl -sS -X POST -H "x-api-token: $TOKEN" -H "Content-Type: application/json" \
  https://<your-api-host>/document \
  -d @- <<EOF
{
  "collection_name": "project_manifest",
  "document": {
    "name": "<your-project>",
    "manifest": $(yq eval -o=json agent-templates/<template>/project.manifest.yml)
  }
}
EOF

# Option B: query the endpoint with ?project=<template-name> directly to use
# the bundled fallback (only works for client-api versions ≥ v.staging-main.134)
curl -sS -H "x-api-token: $TOKEN" \
  "https://<your-api-host>/project/health?project=<template-name>"
```

## Examples in this repo

- [`agent-templates/machina-assistant/project.manifest.yml`](../agent-templates/machina-assistant/project.manifest.yml) — the foundational assistant (OpenAI + Vertex)
- [`agent-templates/chat-completion/project.manifest.yml`](../agent-templates/chat-completion/project.manifest.yml) — minimal chat (single credential)
- [`agent-templates/daily-football-recap/project.manifest.yml`](../agent-templates/daily-football-recap/project.manifest.yml) — content pipeline (3 credentials + 2 datasets)

## Roadmap

- **V1 (now)**: manifest opt-in, manual install per project.
- **V2**: auto-import manifest into Mongo on template install (backend hook in
  `core/dataset/controller.py:process_install_file` — Sprint 5 follow-up).
- **V3**: validation rules for connectors + `extends:` between manifests so a
  project manifest can inherit from its template's manifest.
