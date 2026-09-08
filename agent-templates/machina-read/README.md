# Native Machina Read

A native workflow package, not a standalone application or agent service.

## Install and ownership

The target pod needs the existing `sports-skills` and `machina-ai` connectors. Import `connectors/machina-read-transform`, then this package's workflows. Credentials remain runtime-owned. Do not update unrelated connectors or routing policy as part of installation.

- `machina-read-produce-daily`: native collection, deterministic domain transforms, one Gemini task, validation and native document save.
- `machina-read-get-latest`: native document retrieval and expiry check only. No source calls or generation.
- `machina-read-source-probe`: read-only installation canary; not the daily producer.

The transform contains only pure domain logic. It performs no network, SDK, model, database, filesystem or scheduler operations. All such work belongs to native workflow tasks. SportsClaw is not needed for this bounded pipeline.

## Context and identity

Initial coverage is MLB title futures. Market tickers join to unique Sports Skills MLB abbreviations and verified aliases. Display names derive from the team catalog, so provider labels such as Los Angeles D do not leak into the post. Raw labels and original questions remain in native provenance. Shared-city aliases cannot choose a team by guesswork.

At most two focus teams receive recent-results, season-stats, availability and news enrichment. Standings, schedules and stats retain source identities/seasons. Invalid optional lanes are omitted and recorded as gaps. Google News RFC publication dates control recency; ambiguous derived timestamps do not refresh old headlines. Headlines are reported metadata, not full-article verification.

## Reasoning and output

The only model route is `machina-ai`, Vertex AI, `gemini-3.5-flash-lite`. Do not substitute another model without approval. The output is a short headline/body plus public evidence-based points and source references. It must connect market evidence with structured sports context, not merely format a quote table. Numbers/citations, normalized identities, timing, truncation and source availability are checked before storage. These checks do not constitute a semantic guarantee for every possible model claim; review consequential claims and do not infer news-caused price movement from a single snapshot.

The v2 value contains status, edition/observation/generation/expiry times, story, sources, teams, retained market evidence, capability gaps and engine metadata. Valid values are stored under `machina-read-edition`. Provider quotes and native timestamps are not rewritten on cache reads. Overall source indexing includes the valid citations already supplied by generated points; it does not invent sources.

## Cache and publication

A same-day unexpired native edition is reused, skipping collection and generation. This is sequential cache reuse, not a claim of race-safe global once-per-day execution. Failed validation does not store a replacement or extend an old expiry.

Workflows retain draft definitions. The `machina-read-daily` agent ships **inactive**, with the platform's established `context.config-frequency: 720` mechanism, not a jobs/cron entry. After verified activation it checks twice a day; healthy same-day editions are reused, so normal generation is once per UTC day. Failed refreshes may be retried on the next scheduled check, not continuously. This is not a wall-clock 06:00 cron promise.

Every completed producer check writes `machina-read-health` with an explicit healthy/failed outcome and timestamp, also exposed in workflow/agent output. These are native operational health records, not a claim that an external notification channel is configured. A source or storage outage can prevent a health write; platform execution failures remain separate evidence.

The transform defaults to private results; the approved producer explicitly supplies boolean `publish_public: True` after validation. Reads select admitted editions. Public admission, scheduling and code installation remain separately verified operations. Website consumers use the standard boilerplate server-only pod auth and a fixed read-only document query. The initial adapter is intentionally MLB title-futures only; missing/closed/off-season or unsupported aliases fail closed rather than inventing another sport's data.

## Checks

Run `python -m pytest tests/test_machina_read_native.py -q` and `python scripts/check-machina-ai-policy.py agent-templates/machina-read/workflows/machina-read-produce-daily.yml`. Tests use synthetic teams/news/results with observed provider shapes. Verify live imported definitions, a complete execution, the exact saved document, and a cache-only second execution before claiming runtime success. Keep real payloads, execution IDs and credentials out of Git.
