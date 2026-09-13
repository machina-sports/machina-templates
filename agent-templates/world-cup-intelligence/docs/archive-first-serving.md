# World Cup Final Archive Serving

## Approved Bulk Finalization

The v1 bulk closeout extends the deployed canary without changing its archive
row contract. An offline, resumable operator enumerates the checked-in 104-match
source manifest, captures each fixture once per required workflow, normalizes one
raw `get-fixtures/players` response into a fixture player pack, assembles
source-backed rows, imports bounded batches, verifies exact readbacks, and only
then prepares the active closure manifest. It never rewrites the 104 original
forecast documents; invalid legacy recaps remain raw evidence while a corrected,
grounded archive version is stored separately.

Runtime fixture readers resolve the canonical event first and query by archive
version, endpoint, and `subject.event_urn`; player performance is selected locally
from one fixture pack, preserving the public single-player shape and conjunctive
URN/provider-id/name/team matching. A closure may become active only when all 104
fixtures have context, squads, injuries, player performance, original forecast,
and recap states of complete/partial/unavailable (never error), all 104 recaps are
score/opponent/status grounded, fixture/player coverage is enumerated, hashes pass
exact readback, and the baseline forecast hash is unchanged. Before activation,
clean misses preserve legacy behavior. After activation, catalog misses and
unsupported variants are explicit unavailable responses and cannot call providers,
models, or writers, including through `force_regen`; non-World-Cup and live-market
workflows remain unchanged. The two existing spotlights may be archived when valid,
but spotlight generation is disabled at closure and is not a match-completion gate.

## Decision

The completed FIFA World Cup 2026 catalog is served from immutable,
versioned `worldcup:final-archive` documents. The active version is
`world-cup-2026-final-v2`. Existing v1 canary rows remain immutable and are never
overwritten by bulk publication.

The eleven standard storefront workflows are archive readers only. They may
perform deterministic local selection and filtering through the
`worldcup-market-intelligence` connector, but they never call a provider, a
search connector, or an LLM, and they never write a document. Live market
workflows are outside this contract.

An archive miss, invalidated row, duplicate identity, unsupported parameter
variant, or hash/schema failure returns an explicit unavailable response. It
does not fall through to the old generation path.

## Stored Document

Each row has document name `worldcup:final-archive` and this value shape:

```json
{
  "_id": "world-cup-2026-final-v2:<endpoint>:<subject>:<identity-hash>",
  "archive_version": "world-cup-2026-final-v2",
  "endpoint": "worldcup-get-match-forecast",
  "subject": {
    "key": "urn:machina:sport:soccer:event:...",
    "event_urn": "urn:machina:sport:soccer:event:...",
    "provider_event_id": "1489417"
  },
  "subject_sha256": "...",
  "parameter_identity": {
    "include_reasoning": false,
    "min_gap_bps": 100
  },
  "parameter_identity_sha256": "...",
  "response": {},
  "response_sha256": "...",
  "source_manifest": [],
  "source_manifest_sha256": "...",
  "invalidated": false
}
```

Hashes use UTF-8 canonical JSON (`sort_keys=True`, compact separators). Rows
with missing or mismatched hashes are malformed and are never served. A
duplicate canonical request identity is ambiguous and fails closed even when
the duplicate responses happen to match.

There is no expiry. Publication and invalidation are explicit versioned
operations. Invalidating a version means preparing rows with
`invalidated: true` or publishing a new active version; request input cannot
select, invalidate, regenerate, or overwrite an archive version.

## Request Identity

Selectors are canonicalized to the selected archived subject before hashing.
Every result-changing non-selector field is retained:

| Workflow | Canonical subject | Parameters |
| --- | --- | --- |
| `worldcup-resolve` | resolved entity URN | none |
| `worldcup-get-schedule` | `tournament` | `date_from`, `date_to`, `team`, `opponent`, `status`, `limit` |
| `worldcup-get-event-context` | event URN | `include_prematch_research`, `include_social_pulse` |
| `worldcup-get-standings` | competition/league-season | `league`, `season` |
| `worldcup-get-squads` | event URN | none |
| `worldcup-get-injuries` | event URN | `league`, `season` |
| `worldcup-get-player-performance-context` | event URN + player URN/provider id | `team_id` |
| `worldcup-get-match-forecast` | event URN | `include_reasoning`, `min_gap_bps` |
| `worldcup-backtest-forecasts` | competition | `league`, `season`, `calibration_window_days` |
| `worldcup-match-recap` | event URN | none |
| `worldcup-player-spotlight` | player URN | none |

Schedule filters are applied locally to one versioned tournament snapshot.
Resolve is an exact local lookup over versioned entity rows. This avoids an
exact-request cache explosion while the returned `request_identity_sha256`
still covers every filter. Other parameter variants require an exact warmed
row. Public `force_regen` is accepted for compatibility but ignored and never
enters the identity; operator warming is a separate offline operation.

## Evidence Semantics

- Forecast responses preserve the original forecast payload and
  `model.computed_at`. Final scores are never used to regenerate predictions.
- The standard backtest returns its precomputed response and version/hash; it
  performs no request-time audit, CLV, or calibration computation.
- Recaps and spotlights preserve the stored `generated_at`, body, sources, and
  provenance. Retrospective content is never relabeled as original matchday
  copy.
- Squad identities are an incomplete tournament identity snapshot unless the
  source explicitly proves complete official registration.
- Empty injury data remains partial unless the archived response explicitly
  records `coverage_complete: true`.
- Current squad/injury/provider output is not accepted as historical evidence
  without an explicit historical/tournament scope in its source manifest.

Every served response retains its legacy fields and includes `archive` with
`mode`, `version`, `status`, `response_sha256`,
`source_manifest_sha256`, `request_identity_sha256`, provenance, snapshot
time, capability status, missing capabilities, and notes. Misses use
`archive.status: miss`; malformed or ambiguous rows use
`archive.status: error`.

## Preparation And Publication

`tools/worldcup_archive.py` prepares import bundles from exported document
search JSON. It has no network or credential access and is dry-run by default.
The source manifest supplies exact expected counts and the finite spotlight
target set; the tool never invents fixture/player ids and never generates a
forecast or editorial card.

Preparation is bounded by `--offset` and `--batch-size`, deterministic, and
idempotent. It rejects unsorted/duplicate identities, count mismatches,
ambiguous joins, unverified temporal scope, hash drift, and missing required
manifest fields. A one-item `--canary` bundle is required before `--fanout`.
Resume state records the manifest hash, archive version, verified next offset,
pending batch identities, and emitted row hashes; changing any of them fails
closed. Preparation does not advance the verified offset. `verify` accepts the
real MCP `content[0].text -> data.data` readback envelope, recomputes every
hash, requires the exact pending identities and count, and only then advances
the resume state. Verifying later batches never clears the canary gate.

The preparation tool emits document-store import records only. Import and
invalidation remain explicit operator actions outside public workflows. After
import, operators must read the same rows back and run `verify` against that
export before exposing the version.

Manifest `targets` must contain all eleven endpoint names. Each target is an
object with `subject_key` and exact `parameters`; `entries` must match that set
one-for-one and provide `subject`, `response`, and `source_manifest`. Each
source-manifest row includes `source_payload`; preparation recomputes
`source_sha256` from that payload and omits the payload from the import row.
Claimed response provenance must be represented by a source row. The
manifest also carries `fixture_urns`, `recap_fixture_urns`,
`fixture_player_targets`, `spotlight_targets`, and `expected_archive_count`.
These lists are the only source of fan-out identities.

```bash
# Validation only; writes nothing.
python3 tools/worldcup_archive.py prepare --manifest archive-manifest.json

# Prepare one canary import bundle, then verify its read-back export.
python3 tools/worldcup_archive.py prepare --manifest archive-manifest.json \
  --batch-size 1 --canary --write --output canary.json --resume-state state.json
python3 tools/worldcup_archive.py verify --bundle canary-readback.json \
  --manifest archive-manifest.json --resume-state state.json

# Continue from the verified state. Batch size is capped at 100.
python3 tools/worldcup_archive.py prepare --manifest archive-manifest.json \
  --batch-size 100 --fanout --write --output batch.json --resume-state state.json
```

Use `--invalidate` only to prepare explicit invalidation rows for an operator
review/import. It does not mutate a store itself.

### Bulk Operator

`tools/worldcup_bulk.py` owns the all-match sequence. Every command is offline
or dry-run unless `--apply`/`--write` is explicit. Network commands read only
`WORLDCUP_MCP_URL` and `WORLDCUP_MCP_TOKEN`; they do not read repository or user
configuration. Capture defaults to concurrency 2, records the returned
`workflow_run_id` before polling, polls an existing pending run before dispatch,
and retries a recorded terminal error only on a later bounded invocation.

```bash
# Validate the exact 104-event baseline and build the capture plan.
python3 agent-templates/world-cup-intelligence/tools/worldcup_bulk.py plan \
  --checklist .local/worldcup-bulk/match-checklist.json \
  --baseline .local/worldcup-bulk/baseline \
  --captures .local/worldcup-bulk/captures

# Dispatch a bounded set of missing captures; default is dry-run. The five
# workflows are event context, squads, injuries, match forecast with reasoning
# disabled, and the dedicated worldcup-archive-capture-players operator workflow.
python3 agent-templates/world-cup-intelligence/tools/worldcup_bulk.py capture \
  --checklist .local/worldcup-bulk/match-checklist.json \
  --baseline .local/worldcup-bulk/baseline \
  --captures .local/worldcup-bulk/captures \
  --journal .local/worldcup-bulk/capture-journal.json \
  --batch-size 8 --concurrency 2 --apply

# Assemble and validate all rows. The optional result supplement is accepted
# only when its single page exactly matches all 104 canonical final fixtures.
python3 agent-templates/world-cup-intelligence/tools/worldcup_bulk.py assemble \
  --checklist .local/worldcup-bulk/match-checklist.json \
  --baseline .local/worldcup-bulk/baseline \
  --captures .local/worldcup-bulk/captures \
  --executions .local/worldcup-archive/executions \
  --result-details .local/worldcup-bulk/provider-results-compact.json \
  --generated-at 2026-09-13T00:00:00Z \
  --manifest-output bulk-manifest.json --output bulk-bundle.json --write

# Use worldcup_archive.py prepare/verify to split the full bundle into <=100-row
# imports. The import journal makes each prepared batch resumable.
python3 agent-templates/world-cup-intelligence/tools/worldcup_bulk.py import --bundle batch.json \
  --journal import-journal.json --apply
python3 agent-templates/world-cup-intelligence/tools/worldcup_bulk.py verify --bundle readback.json \
  --manifest bulk-manifest.json

# Replay source-derived request identities after import (dry-run without --apply).
python3 agent-templates/world-cup-intelligence/tools/worldcup_bulk.py replay \
  --manifest bulk-manifest.json --output-dir replay \
  --journal replay-journal.json --batch-size 8 --concurrency 2 --apply

# Prepare (but do not publish) the one-row closure document after full readback.
python3 agent-templates/world-cup-intelligence/tools/worldcup_bulk.py close --manifest bulk-manifest.json \
  --readback full-readback.json \
  --forecast-export fresh-worldcup-model-forecast.json \
  --closed-at 2026-09-13T00:00:00Z \
  --output closure.json --write
```

When supplied, result details add source-hashed regulation, extra-time,
shootout, and explicit winner evidence without changing canonical events or
stored forecasts. Without the supplement, knockout recap scorecards retain the
explicit missing-regulation-evidence state.

The close command checks exact row identity/value equality, all six fixture
capability states, 104 validated recaps, fixture/player enumeration, and all 104
IDs and values from a fresh original-forecast export against the independent
assembly baseline. Import the v2 rows and validated `closure.json` before updating
the public workflow definitions from v1 to v2. Importing `closure.json` remains a
separate final operator action.

## Canary-Safe Migration Revision

The initial archive-only cutover described above is superseded during migration
by an incremental archive-first gate. Each of the eleven workflows first reads
the versioned archive and the required canonical event/player indexes. A valid
archive hit returns the captured response and skips every legacy provider, LLM,
and write task. A clean miss runs the original workflow unchanged. Ordinary
unresolved or ambiguous selectors also defer to the original resolver so its
candidate lists remain available. Requests outside the warmed fixture/player
set do not acquire new error behavior merely because a canary exists. Corrupt,
invalidated, duplicate archive identities, truncated lookups, and conflicting
selectors for a warmed player fail closed. `force_regen` cannot bypass a valid
hit. Non-World-Cup backtests continue through the legacy path.

Fixture selection is resolved against the complete 104-event canonical index,
not the set of warmed endpoint rows. Player selectors are conjunctive: every
supplied URN, provider id, name/alias, and team must identify the same canonical
player. Archive identities hash the full subject metadata as well as normalized
result-changing parameters. Injury identities include league and season.
Schedule filter values remain raw when filtering, while their request hash uses
normalized values. Filtering selects original snapshot rows unchanged, retaining
fixture IDs, venue, team URNs, and home/away qualifiers. `response_sha256` identifies
the stored unfiltered snapshot; `request_identity_sha256` identifies the selected
filter variant. The former is not a hash of the filtered HTTP response body.

The offline `capture` command consumes labeled execution JSON from
`executions/` plus hash-checked source exports from `export/`. It regenerates
the unfiltered 104-event schedule before building the archive row and verifies
the exact selected response content, source payload hashes, subject hash, and
row hashes. Execution capture time is provenance only, never evidence of
historical scope. The current artifact is deliberately marked
`coverage_scope: one_fixture_canary` and `publication_ready: false`; it contains
all eleven endpoints for Brazil vs Morocco (`1489371`) and Vinicius (`762`). A
separate complete-coverage gate is required before any fan-out publication.

```bash
python3 tools/worldcup_archive.py capture \
  --executions .local/worldcup-archive/executions \
  --exports .local/worldcup-archive/export \
  --manifest-output .local/worldcup-archive/canary-manifest.json \
  --output .local/worldcup-archive/canary-import.json \
  --write
```
