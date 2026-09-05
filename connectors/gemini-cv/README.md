# gemini-cv — Gemini CV route for the Automated Highlights Agent

The production path for the **machina-ai Gemini CV** stage of ClickUp 86ak32k1w. It sits
between the SportsClaw extraction core (which decides *which* moments exist and where they
are on the timeline) and HyperFrames composition. Product repos (Broadcast AI, its template
packs) call this connector; they never call Gemini directly.

## Command `rank_highlight_candidates`

Input (params / context-variables):

| field | required | notes |
|---|---|---|
| `manifest` | one of | Succeeded `ClipManifest` with `source.sha256`, source duration, event, and explicitly cleared clipping rights with holder and license reference. |
| `candidates` (+ `sync_anchor`, `duration_sec`, `event`, `rights`, `source_sha256`) | one of | Explicit list, subject to the same rights and source verification as a manifest. Contradictory rights aliases are refused. |
| `video` | yes | One authenticated `{gcs_uri}` / `{uri}` or local `{path}`. Arbitrary HTTP and pre-existing Files API URIs are not accepted because they do not establish byte identity. |
| `provider` | no | `vertex_ai` (default, `project_id` + `credential`, `location: global`) or `ai_studio` (`api_key`) |
| `processing` | no | `static` (default) or `agentic` — capability-gated, see below |
| `model_name` | no | requested default `gemini-3.8-flash`; availability must be verified in the target pod, never silently substituted |
| `thinking_level` | no | `minimal` / `low` (default) / `medium` / `high` |
| `max_output_tokens`, `timeout_sec` | no | defaults 16384 / 180. Thought tokens count against the output budget. |

Unresolved optional credential overrides fall back in this platform connector to the pod's
existing `TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID`, `TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL`
and, only when AI Studio is explicitly selected, `TEMP_CONTEXT_VARIABLE_GOOGLE_GENERATIVE_AI_API_KEY`.
Explicit resolved workflow credentials take precedence. Secrets never enter ranking hashes or receipts.

Output (`data`):

- `degraded` (bool), `degraded_reasons[]`, `fallback_mode` (`none` or `pbp-importance`)
- `ranking[]` — one entry per candidate the caller supplied, never more: `candidate_id, rank,
  verdict (keep|hold|reject), source (gemini-cv|pbp-importance), relevance, hype,
  editorial_safety, confidence, refined_start_sec, refined_end_sec, pbp_importance, description`
- `discovered_moments[]` — review-only hypotheses, never candidates
- `refusal`, `usage`, `latency_ms`, `model`, `provider`, `processing`, `prompt_version`,
  `request_sha256` (prompt + candidates + provider/model/mode + video reference + duration + event + rights + source/manifest hashes)
- `ranking_id`, `created_at`: a distinct receipt for every attempt, even with identical request inputs
- `source_sha256`, `manifest_sha256`, `rights_sha256`, `media_verified`: evidence binding;
  `media_verified` is true only after checking the actual bytes against the extraction digest

### Verified-media limits (contract 1.1)

GCS reads pin a single object generation and use a generation-match precondition. The
connector hashes a private snapshot before any model submission, then sends those exact
bytes inline or uploads that same snapshot to the configured AI Studio Files API. A mutable
GCS URI is **never** forwarded after hashing, avoiding a check-to-model race. See
[Google Storage generation preconditions](https://docs.cloud.google.com/python/docs/reference/storage/latest/generation_metageneration).

Vertex currently supports verified inline media up to **20 MiB** on this route. AI Studio
supports verified media up to **512 MiB**, with explicit Files API upload when needed.
Larger sources degrade with a byte-budget reason, without auto-transcoding, auto-cutting,
changing providers, or bypassing verification. Full-match CV needs a separately reviewed
large-media/clip-batch path before it can be claimed demo-ready. Clipping stays in SportsClaw.

## Fail-closed contract

| situation | result |
|---|---|
| output is not JSON / misses the schema / adds or drops a candidate / drifts > 10 s from a window | `degraded: true`, `schema-violation: …`, PBP ranking with `verdict: hold` and null scores |
| model fills `refusal` (e.g. "not sports footage") | `degraded: true`, `model-refusal: …`, the refusal text is kept |
| provider error, timeout, upload failure, missing credential | `degraded: true`, `provider-error: …` |
| `processing: agentic` where the runtime cannot reach the Interactions API | `degraded: true`, `agentic-unavailable: …` — **static is never substituted silently** |
| rights absent/denied/contradictory on either input path, missing digest, invalid event/window/duration/budget | `status: false`, error 400, no model call |
| source bytes differ from the extraction digest, unsupported URI or oversized media | refused input or explicit degraded fallback, never a verified CV ranking |

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
