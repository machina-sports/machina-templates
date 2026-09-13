# World Cup Final Archive Repair

The six `worldcup-backfill-*` workflows are archive **assessments**, not backfill
writers. They inspect stored World Cup 2026 evidence and return deterministic,
bounded repair plans. They make no provider, model, search, prompt, MCP, or
document-mutation calls.

## Why the earlier files were not imported

`_install.yml` is an explicit dataset manifest; it does not discover files by
globbing `workflows/`. The earlier six workflows were committed without manifest
entries, so a normal template import did not add them. A manual workflow install
bypassed that protection. The manifest now includes only the tested read-only
replacements. It includes no archive writer.

## Shared contract

All six workflows load same-pod documents with a fixed `5000`-document bound and
the total-order sorter `['_id', 1]`, then call the pure
`worldcup-market-intelligence.plan_archive_repair` connector command.

Inputs:

- `offset` (default `0`): stable offset into fixtures sorted by canonical event URN,
  falling back to the API-Football fixture id.
- `batch_size` (default `20`, maximum `100`): number of fixture assessments returned.
- `expected_fixture_count` (default `104`): count guard for the completed tournament.
- `expected_event_urns` (optional): source-backed fixture manifest. When supplied,
  missing fixtures are reported by exact URN. Without it, a count mismatch is
  reported honestly; missing ids are not invented.
- `expected_player_urns` (crosswalk/master only): source-backed tournament player
  manifest. Without it, stored player rows are validated individually but player
  population completeness remains `not_assessed`.
- `target_player_urns` (editorial/master only): approved spotlight target set. No
  spotlight completeness claim is made without this input.

The result always includes `dry_run: true`, `mutation_capability: disabled`, zero
provider/forecast/write outcome counters, preserved evidence ids and timestamps,
stable batch metadata, per-fixture joins, exact observed gaps, and warnings when a
search or evidence bound prevents a complete conclusion.

Large reports compact detail arrays to fit the response budget. `array_metadata`
reports each array's total, returned, and truncated counts. Fixture pages advance
by examined rows: follow `batch.next_offset`, never add the requested batch size.
`array_metadata.fixtures.oversized_omitted` explicitly reports fixture details too
large to return; inspect the original source records for those omissions. Report
compaction does not change the global assessment or imply complete source coverage.

An empty collection or response means only that archive evidence is missing or
empty. It does **not** establish that an upstream API is unavailable. Historical
timestamps are expected and are not treated as stale by request-time comparisons.

## Supported assessments

| Workflow | Supported | Explicitly blocked |
| --- | --- | --- |
| `worldcup-backfill-crosswalks` | Stored event/team/player identities and missing provider ids | Provider calls and crosswalk writes |
| `worldcup-backfill-model-forecasts` | Existing forecast-to-fixture joins, probabilities, and model-time checks | Every forecast computation, regeneration, and overwrite |
| `worldcup-backfill-market-sources` | Existing direct `event_urn`/fixture-id joins and deterministic team-pair fallback joins | Current/settled market fetches and cache replacement |
| `worldcup-backfill-historical-data` | Stored fixture-scoped injury, squad, and player-performance evidence | On-demand getter calls and archive writes |
| `worldcup-backfill-editorial-content` | Existing final-match recaps and explicitly approved spotlight targets | Search, prompting, generation, and cache writes |
| `worldcup-backfill-master` | One combined assessment with the five stages in dependency order | Workflow orchestration or mutation |

Squad evidence is `unverified_temporal_scope` unless the stored record explicitly
declares `historical_evidence: true` or a World Cup 2026 tournament scope. A current
roster is never presented as a historical tournament squad.

Forecast evidence is `historical_model` only when a stored model timestamp is
provably before kickoff and probabilities exist. A missing forecast is
unrecoverable without a genuine prematch snapshot. A forecast timestamp at or
after kickoff is preserved for review but rejected as prematch evidence. Final
results must never be used to regenerate or overwrite forecasts.

## Approval-gated canary

The current implementation stops at assessment. Before approving any separate
future archive writer:

1. Run the focused offline tests and policy validation listed below.
2. Review a read-only assessment with `batch_size: 1`, `offset: 0`, and an approved
   `expected_event_urns` manifest. Confirm every evidence id, join method, timestamp,
   and missing-work reason against stored documents.
3. Require immutable source payloads or hashes for the exact missing item. Current
   provider output is not historical evidence unless its historical scope is proven.
4. Produce a dry-run before/after diff for one fixture. It must preserve canonical
   ids, provider ids, raw evidence references, and every existing forecast byte for
   byte.
5. Obtain explicit human approval for that one-fixture mutation. Execute no fan-out.
6. Verify the durable document and execution trace, then rerun the read-only
   assessment. A workflow success status alone is not evidence of a saved repair.
7. Stop on any ambiguous join, empty/unverified response, count mismatch, timestamp
   conflict, or forecast change. A broader batch requires separate approval.

Offline verification:

```bash
python3 -m pytest agent-templates/world-cup-intelligence/tests/test_worldcup_archive_repair.py -q
python3 -m pytest agent-templates/world-cup-intelligence/tests/test_worldcup_market_intelligence.py agent-templates/world-cup-intelligence/tests/test_worldcup_workflow_regressions.py agent-templates/world-cup-intelligence/tests/test_worldcup_final_archive_contract.py -q
python3 scripts/check-machina-ai-policy.py
```
