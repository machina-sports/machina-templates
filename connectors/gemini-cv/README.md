# gemini-cv — Gemini CV route for the Automated Highlights Agent

The production path for the **machina-ai Gemini CV** stage of ClickUp 86ak32k1w. It sits
between the SportsClaw extraction core (which decides *which* moments exist and where they
are on the timeline) and HyperFrames composition. Product repos (Broadcast AI, its template
packs) call this connector; they never call Gemini directly.

## Command `rank_highlight_candidates`

Input (params / context-variables):

| field | required | notes |
|---|---|---|
| `manifest` | one of | `ClipManifest` from `sportsclaw highlights run` or the relay `/api/highlights/jobs/{id}/artifacts`. Rights must say `clearedForClipping: true` or the call is refused (HTTP-style 400, no model call). |
| `candidates` (+ `sync_anchor`, `duration_sec`) | one of | explicit list when no manifest is at hand |
| `video` | yes | `{gcs_uri}` (Vertex), `{uri}` (Files API URI) or `{path}` (local; ≤ 20 MB inline on Vertex, Files API upload on AI Studio) |
| `provider` | no | `vertex_ai` (default, `project_id` + `credential`, `location: global`) or `ai_studio` (`api_key`) |
| `processing` | no | `static` (default) or `agentic` — capability-gated, see below |
| `model_name` | no | default `gemini-3.7-flash` |
| `thinking_level` | no | `minimal` / `low` (default) / `medium` / `high` |
| `max_output_tokens`, `timeout_sec` | no | defaults 16384 / 180. Thought tokens count against the output budget. |

Output (`data`):

- `degraded` (bool), `degraded_reasons[]`, `fallback_mode` (`none` or `pbp-importance`)
- `ranking[]` — one entry per candidate the caller supplied, never more: `candidate_id, rank,
  verdict (keep|hold|reject), source (gemini-cv|pbp-importance), relevance, hype,
  editorial_safety, confidence, refined_start_sec, refined_end_sec, pbp_importance, description`
- `discovered_moments[]` — review-only hypotheses, never candidates
- `refusal`, `usage`, `latency_ms`, `model`, `provider`, `processing`, `prompt_version`,
  `request_sha256` (prompt + candidates + config; the video is not hashed)

## Fail-closed contract

| situation | result |
|---|---|
| output is not JSON / misses the schema / adds or drops a candidate / drifts > 10 s from a window | `degraded: true`, `schema-violation: …`, PBP ranking with `verdict: hold` and null scores |
| model fills `refusal` (e.g. "not sports footage") | `degraded: true`, `model-refusal: …`, the refusal text is kept |
| provider error, timeout, upload failure, missing credential | `degraded: true`, `provider-error: …` |
| `processing: agentic` where the runtime cannot reach the Interactions API | `degraded: true`, `agentic-unavailable: …` — **static is never substituted silently** |
| manifest rights not cleared, unknown provider/processing, missing video | `status: false`, error 400, no model call |

`degraded` never hides behind `status`: a degraded run returns `status: true` so the workflow
can store the deterministic ranking and show the flag to the operator.

## Agentic processing

Gemini's agentic video understanding (`processing: "agentic"`) is only exposed through the
Interactions API. The `google-genai` SDK pinned by the client API (1.49.0) has no
`interactions` client, so this route reaches it through the AI Studio REST surface only;
on `vertex_ai` the mode is reported as unavailable. `route_capabilities` says which is the
case in the running pod. Measured on 2026-09-04 (machina-agent-arena
`benchmarks/automated-highlights-cv`): both modes classified the synthetic fixture
correctly; static refused the synthetic footage in 2 of 3 runs, agentic never did.

## Workflow usage

```yaml
workflow:
  context-variables:
    gemini-cv:
      provider: vertex_ai
      project_id: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID
      credential: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL
      location: global
  tasks:
    - name: rank_candidates
      type: connector
      connector:
        name: gemini-cv
        command: rank_highlight_candidates
      inputs:
        manifest: "$.get('manifest')"
        video: "{'gcs_uri': $.get('source_gcs_uri'), 'mime_type': 'video/mp4'}"
        processing: "'static'"
      outputs:
        cv_ranking: "$"
```

Tests: `python -m pytest tests/test_gemini_cv_connector.py` (offline, transport injected).
