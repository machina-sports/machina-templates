# Canonical event-evidence contract and API-Football dual-write

Status: local implementation candidate. Not deployed, not merged, not imported to any
environment. Scope is the producer half only; no consumer reads the new family yet.

## Problem

The event is canonical and the evidence is not. Fixture discovery and per-event refresh
both write `sport:Event` through `machina-sports-canonical.canonicalize_event`, but
everything that turns a fixture into content lives in five API-Football-named documents —
`api-football-event-actions`, `-lineups`, `-team-statistics`, `-player-statistics`,
`-head-to-head` — carrying `schema_version: api-football-event-projection/2`.

Consumers key on those names. Adding a second data provider therefore means writing a new
enrich workflow *and* teaching every consumer a new set of document names. This change
closes the producer half of that gap so a second provider becomes a configuration
exercise rather than a rewrite.

## What this delivers

1. A provider-neutral evidence contract, `machina-event-evidence/1`, as a JSON Schema at
   `connectors/machina-sports-canonical/machina-event-evidence-1.schema.json`.
2. `api-football-event-data.py` emits `canonical-event-evidence` documents against that
   contract **alongside** the five legacy projections, which keep their exact bytes.
3. `api-football-enrich-event-data.yml` persists the new family in one upsert and reports
   honestly when only half of the dual-write lands.

The legacy family is still written and still read. Retiring it is a later, separate step
gated on no consumer reading those names.

## The contract

One document family, five kinds today and a sixth reserved:

```
name:     canonical-event-evidence
metadata: { event_code, source_event_document_id, provider_namespace, evidence_kind }
value:    { @id, schema_version: machina-event-evidence/1, kind, event_id, event_code,
            source_event_document_id, provider {namespace, family}, provider_event_id,
            status, observed_at, projection_key, projection_capability,
            provenance, rights, request_context, facts[], unavailable_reason? }
```

`evidence_kind` ∈ `actions | lineups | team_statistics | player_statistics |
head_to_head | season_form`. The five API-Football projections map 1:1. `season_form` is
declared but emitted by nobody — see *Deviations*.

Every fact carries `claim_type` and `claim_scope`, canonical `urn:machina:sports:*`
identifiers, and a single `provider_evidence` block holding the provider's own ids and the
exact provider row. Provider identifiers never appear as fact keys; the schema enforces
that with `additionalProperties: false` on every fact shape.

### The upsert identity, and why `metadata` is only four keys

The runtime's `document_update_bulk` filters on `{"metadata": metadata, "name": name}` —
the **whole** `metadata` subdocument, matched for equality. Any field in there that changes
between refreshes produces a *new* document every tick instead of updating the existing
one.

So `metadata` is exactly the identity tuple — event, source document, provider, kind — and
everything volatile (`observed_at`, `status`, `provenance`, `rights`,
`projection_capability`) lives in `value`, where the schema still requires it. A retry
updates five documents; it never adds a sixth.

### Exact binding is preserved, not relaxed

The canonical facts are derived from the legacy projector's already-validated output, not
from a second parse of the provider payload. That output is where the exact checks already
happened — fixture-id equality, crosswalk equality for both teams, duplicate participation
refusal, head-to-head pair equality — so the two families cannot disagree about what the
provider said.

Deliberately **not** done, because these would be trust reductions on the producer side:

- Athlete identity remains exact crosswalk equality. There is no
  `startswith("urn:machina:sports:player:")` anywhere in the producer. Where the source
  event's crosswalk does not map a provider player, the fact carries **no** athlete
  identifier rather than a plausible one.
- Provider trust remains the source event's `provenance.provider.namespace` compared for
  equality, not membership in an allowlist.
- `provider` is copied from the source event and the schema admits only
  `{namespace, family}`, so `event_view.provider.raw` cannot be smuggled in.

Unavailable stays unavailable: status, reason and the empty fact list are copied from the
legacy document. The schema refuses an `unavailable` document carrying facts, an
`unavailable` document with no reason, and an `available` document carrying a reason.

### Statistics: the owner's vocabulary or nothing

The intent was exact IPTC CURIEs where expressible, with non-expressible measurements
under a bounded `metrics` block.

Nothing is expressible today. The canonical package's own API-Football adapter
(`tools/iptc/canonical/adapters/api_football.py`) contains zero statistic CURIEs at the
pinned upstream commit, so there is no owner-published mapping from API-Football statistic
labels to `spsocstat:*`. Writing one in this connector would create a second statistic
vocabulary beside the one the package owns — the drift the canonical seam's own suite
already forbids in `machina-sports-canonical.py`.

So this change emits `statistics: []`, puts every measurement under `metrics` with the
provider's own label, and keeps the untouched provider rows in `provider_evidence` for
whoever writes that mapping. Two tests hold the line:

- `test_the_producer_owns_no_iptc_statistic_vocabulary` — no `sp*stat:` literal in the
  producer source.
- `test_every_emitted_statistic_curie_is_admitted_by_the_owners_manifest` — any CURIE that
  ever appears must be `admitted: true` in
  `tools/iptc/canonical/data/official_statistic_admissibility_v1.json` for the fact's
  participation kind. Vacuous today; a real gate the moment a mapping lands.

`metrics` is bounded structurally: one level of the provider's own key path, scalar values
only. Nothing deeper is flattened or summarised. The two provider shapes are handled
distinctly — a label/value row whose value is a container yields no metric rather than
having its keys read as labels.

## Persistence and honest failure

The dual-write is a single `bulk-update` task. Its receipt is what the store echoed back,
not the fact that the task ran:

```yaml
evidence-saved-kinds: "sorted({... for item in $.get('documents', []) if item.get('name') == 'canonical-event-evidence' ...})"
```

The workflow reports `executed` only when the projection was valid, the five legacy
documents were written, **and** all five kinds came back from the store. A run that wrote
the legacy family and lost the canonical one reports `failed`, with
`evidence-dual-write: false` naming which half.

This is an intentional change to `workflow-status` semantics, and it has an operational
consequence: a canonical-write failure now fails a run that would previously have reported
`executed`. That is the point — a silently half-populated evidence family is what the next
phase would read.

## Files changed

| File | Change |
|---|---|
| `connectors/machina-sports-canonical/machina-event-evidence-1.schema.json` | New. The contract. |
| `connectors/api-football/api-football-event-data.py` | New evidence projectors + `evidence_documents` in the result. Legacy path untouched. |
| `connectors/api-football/api-football-enrich-event-data.yml` | Two new projection outputs, one `bulk-update` dual-write task, stricter `workflow-status`, new `evidence-dual-write`. |
| `connectors/api-football/tests/test_canonical_event_evidence.py` | New. 50 tests. |
| `connectors/api-football/tests/fixtures/legacy-projection-golden.json` | New. See below. |
| `docs/plans/2026-09-04-dl050-phase1-canonical-event-evidence.md` | This file. |

Deliberately not touched: `event-synchronize.yml` and its tests, `tools/iptc/canonical/**`
(owner-vendored and pinned), `.machina/maintenance.json`, and every consumer repository.

### About the golden fixture

`legacy-projection-golden.json` is **synthetic test data, not a record of live traffic.**
It is the projector's output for the repository's existing synthetic fixture
`connectors/api-football/tests/fixtures/event-data.json` — fixture id `7001`, teams
`Home FC` (40) and `Away FC` (47), players `H. Scorer` / `A. Starter`. It contains no
customer data, no tenant identifiers, no credentials and no provider response captured
from a real account. Its only purpose is to pin the five legacy documents byte-for-byte so
the dual-write cannot perturb them.

## Test evidence

```
$ python3 -m pytest connectors/api-football/tests -q     # this interpreter, jsonschema present
137 passed
```

86 pre-existing + 51 new. The pre-existing 86 — the baseline after PR #364 merged — are
unchanged and still pass.

`jsonschema` is not a dependency of this repository's runtime, so the two tests that need
a validator skip on an interpreter without it and the other 135 run regardless. The
properties that must hold everywhere — legacy byte-identity, exact identity binding,
unavailability, upsert identity, expression safety — are in the 135, not the 2.

Expression validation was run against the actual runtime evaluator rather than a local
imitation (the workflow engine's `safe_eval`): **141 expressions accepted, 0 rejected**
across the enrich workflow.

The suite reproduces both of the runtime's evaluation semantics rather than one: the task
`outputs` path (`$.get` reads the task *response*, `$.context` reads accumulated state)
and the workflow-outputs / task-inputs / conditions path (`$.get` reads accumulated
state). It also asserts the runtime's newline-stripping and its "an output evaluating to
`None` is silently dropped" behaviour, both of which are real ways a workflow reads as
"never ran".

### The guards were checked against mutation, not assumed

| Injected defect | Caught by |
|---|---|
| Extra field on a legacy document | the byte-identity test |
| `observed_at` added to the upsert key | 4 tests, incl. idempotency and schema |
| Fabricated CURIE `spsocstat:vibesTotal` | 3 tests, incl. the owner-admissibility gate |
| Ordinal prefix corrupting label/value metrics | the non-scalar-value metric test |

Schema negative cases, all rejected: volatile field in the upsert key; `available` document
carrying `unavailable_reason`; `unavailable` document carrying facts; `unavailable` with no
reason; invented CURIE shape; `provider.raw` smuggled into the provider block;
non-canonical team id; nested value in a bounded metric; wrong `claim_type` for the kind;
provider id promoted to a fact key; `season_form` without the owner longitudinal binding.

The golden file's own provenance is tested: `test_the_golden_is_what_the_reviewed_producer_actually_emitted`
re-runs the projection against the producer as `HEAD` has it and compares, so a golden
regenerated to match a regression fails instead of passing.

## Deviations from the design as written

1. **`metadata` carries the identity tuple only.** The design listed `observed_at`,
   `provenance`, `status`, `projection_capability` and `projection_key` under `metadata`.
   The store keys its upsert on the whole `metadata` subdocument, so following that
   literally would have created five new documents per refresh instead of updating five.
   All those fields remain required by the contract, in `value`.
2. **No IPTC statistic CURIEs are emitted.** The "where expressible" condition is not met
   at the current pin, and the alternative was inventing a mapping.
3. **`season_form` is declared but not produced.** It is the longitudinal kind, it already
   has an owner contract (`LONGITUDINAL_SCHEMA_VERSION` =
   `canonical-longitudinal-statistics/1`), and its source is the season workflow, not the
   per-event enrich workflow. The schema binds the kind to the owner's constant, and a
   test asserts the schema constant equals the package's so the two cannot drift.
4. **The contract lives in `connectors/machina-sports-canonical/` as a schema file only.**
   Placing it in `tools/iptc/canonical/` was preferred but that tree is owner-vendored and
   pinned, so the stated fallback applies. The file is not added to that connector's
   `_install.yml` and the connector's pyscript is untouched, so the seam suite's "this
   connector owns nothing" guards are unaffected. Consequence: the schema is a repository
   contract enforced by tests, not a runtime artifact loaded by a running environment.

## Unresolved gates

- **Readback in a running environment** has not been performed: no deploy, no import, no
  network writes were in scope. The claim that both document families appear after a
  refresh is therefore untested outside this repository.
- **Consumers are unchanged** and still read the five legacy names, so behaviour is
  unaltered other than the stricter `workflow-status`.
- **Upsert-key field order.** MongoDB embedded-document equality is order-sensitive. The
  four keys are emitted in one fixed order from one code path, so this is stable in
  practice, but it is a property of the engine's filter rather than something this
  contract can enforce. Worth noting for whoever writes the second producer.
- **The byte-exact copy rule to a second producer repository** is not exercised — there is
  no second producer yet.
