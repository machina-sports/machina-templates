# `tools/iptc` — offline IPTC Sport Schema 1.1 conformance harness

Operator tooling. Not a template: nothing here is installed into a Machina
project, and no mapping or workflow calls it.

**It never touches the network and never reads a credential.** Every check runs
against a pinned, vendored copy of the official IPTC Sport Schema, so a
conformance result obtained today is reproducible years from now against exactly
the bytes it was obtained against. That is enforced rather than assumed: layer 1
rejects any document that would make the JSON-LD processor fetch a context —
a string `@context`, a string inside a `@context` array, a scoped context given as
a string, or `@import` — **before** the processor is handed the bytes.

## Where things live, and why

| Path | What | Why there |
|---|---|---|
| `agent-templates/iptc-mappings/references/iptc-sport-schema-1.1/` | vendored upstream ontologies, `shacl/`, vocabularies, samples, `UPSTREAM.md`, `LICENSE.md`, `upstream-commit.json` | the pinned standard sits beside the mappings it governs |
| `agent-templates/iptc-mappings/contexts/iptc-sport-schema-1.1.context.jsonld` | the one shared JSON-LD context | it is a serializer input, so it ships with the templates |
| `tools/iptc/` | the harness, its rules and its fixtures | operator tooling, not installed |
| `tools/iptc/vendored-manifest.json` | the authoritative pin of the runtime `sports-skills` vendors byte-exact | the specification belongs beside the bytes; the consumer's `VENDORED.json` is only its receipt |
| `docs/rfcs/001-machina-iptc-sport-schema-profile.md` | the normative Machina profile | layer 3 is this document's executable form |
| `docs/iptc/BASELINE-AUDIT.md`, `docs/iptc/baseline-audit.json` | the recorded baseline | generated; CI checks they are current |
| `docs/iptc/INVENTORY.md`, `docs/iptc/inventory.json` | every IPTC emitter and consumer in the repo | the evidence base for PR 2 scope and PR 3 consumer migration |

## Install

Python 3.12, matching CI:

```bash
python3 -m pip install -r requirements-iptc-validator.txt
```

`rdflib` and `pyshacl` are pinned there with exact versions. Both are pure Python
and need no system packages.

That file is scoped to this harness and includes `-r requirements-validator.txt`
for the base validator pins. The split is deliberate: the pre-existing
`validate-machina-agent-builder` workflow installs only the base file, so it does
not inherit this harness's dependency tree.

## The commands

Run all of these from the repository root.

```bash
# verify the vendored upstream bytes still match the recorded hashes,
# and that the shared context has not drifted from the pin
python3 -m tools.iptc --verify-pin

# THE baseline report command. Deterministic: same inputs, same bytes out.
python3 -m tools.iptc                       # regenerate docs/iptc/*
python3 -m tools.iptc --check               # fail if the checked-in reports are stale (CI gate)

# focused, single-document checks
python3 tools/iptc/validate_graph.py         <doc.json>   # layers 1 + 2 + 3
python3 tools/iptc/validate_terms.py         <doc.json>   # gates 1 + 4, against the pinned ontologies
python3 tools/iptc/validate_vocabularies.py  <doc.json>   # layer 4 / gate 2, against the pinned TTLs

# a canonical envelope is validated through its inner sport_schema_graph, and is
# additionally gated on the rights it carries. A refused envelope exits nonzero.
python3 tools/iptc/validate_graph.py --consumer-tier production <envelope.json>

# each focused command also takes --all [--section baseline] [--json] [--verbose]
python3 tools/iptc/validate_graph.py --all --section baseline
python3 tools/iptc/validate_terms.py --list-official-terms
python3 tools/iptc/validate_vocabularies.py --list-schemes

# freeze a new baseline fixture from a checked-in artefact
python3 tools/iptc/extract_mapping_fixture.py --list-artifacts
python3 tools/iptc/extract_mapping_fixture.py --mapping <mapping.yml>

# tests — run the file directly. `tests/` has no `__init__.py`, so an installed
# distribution shipping a top-level `tests` package would shadow the module form.
python3 tests/test_iptc_validation_harness.py -v
```

## The four layers

| Layer | Command | What it proves |
|---|---|---|
| 1 JSON-LD expansion / RDF parse | `validate_graph.py` | the document is valid JSON-LD and expands to parseable RDF |
| 2 official IPTC SHACL | `validate_graph.py` | it conforms to the shapes shipped with the pinned 1.1 ontology |
| 3 Machina profile | `validate_graph.py` | it satisfies the constraints IPTC leaves open (the RFC) |
| 4 controlled vocabulary | `validate_vocabularies.py` | every NewsCode is provably present in a pinned vocabulary |

Layer 2 reproduces upstream's own procedure from `tools/shacl-validate.sh`: the
merged ontology **and every vocabulary** are merged into the data graph before
validating, because the shapes depend on `rdfs:subClassOf` and `skos:inScheme`.
Skipping that merge manufactures failures.

## The four gates

Not metrics to be trended. Gates.

| Gate | Command | Target |
|---|---|---|
| unknown `sport:` terms | `validate_terms.py` | 0 |
| invalid NewsCode values | `validate_vocabularies.py` | 0 |
| duplicate resource IDs | `validate_graph.py` | 0 |
| provider properties in the IPTC namespace | `validate_terms.py` | 0 |

Gates 1 and 4 overlap by construction. A provider field name emitted under
`sport:` is both an undeclared term and an attributable provider leak, and it is
counted once in each column because the two columns answer different questions.
**Never add the gate numbers together and call it a total.**

## Three things that will mislead you if you do not know them

**A layer-2 pass can be vacuous.** A payload whose `sport` prefix points at
`https://www.sportschema.org/ontologies/sport#` instead of the official
`https://sportschema.org/ontologies/main/` produces no instances of any official
IPTC class. Every `sh:targetClass` then matches nothing and pyshacl reports
`conforms=True` over an empty target set. The harness counts official-class
instances and records that as `vacuous`, failing layer 2. Seven of the fourteen
baseline fixtures are in exactly this state.

**`unverifiable` is not `valid`, and layer 4 fails closed on it.** Upstream's
`tools/prefixes.ttl` and SHACL shapes name concept schemes — `spsocaction`,
`spsocrole`, `spesaction` and the other per-sport action/result schemes — for which
no TTL exists at the pinned commit. Values in those schemes cannot be checked
offline. They are reported as `unverifiable`, never counted as valid and never
counted as invalid — but they **fail** layer 4 and exit `validate_vocabularies.py`
non-zero, because the requirement is *provable* membership in a pinned vocabulary
and missing evidence is not evidence of correctness. The category stays separate
from `invalid` because the fixes differ: an invalid code is a mapping bug, while an
unverifiable one is resolved by a pin bump once upstream publishes the scheme.

Consequence worth knowing before reading the report: several **official upstream
samples** carry codes from those schemes, so they pass layer 2 (the claim they are
a control for) and fail layer 4. `machina-profile-conforming-minimal` is the only
document expected to pass all four layers.

**The official shapes are `sh:closed`.** `sport:TeamShape`, `sport:EventShape`,
`sport:AthleteShape`, `sport:SiteShape` and others close their property set, so a
`machina:`-namespaced property attached directly to a `sport:Team` fails the
official SHACL. Extension properties therefore belong on `machina:`-typed nodes
that reference the official resource by `@id`. The conforming fixture demonstrates
the pattern.

## Two upstream defects, worked around in memory only

The vendored bytes are never rewritten. Both defects are documented in the
reference directory's `UPSTREAM.md` and reported in every run, so they cannot
become invisible.

1. **15 of 17 vocabulary TTLs omit the `.` after their final `@prefix`.** Invalid
   Turtle; Jena tolerates it, `rdflib` does not. Each file is parsed as-is first
   and only retried against a repaired in-memory copy if that raises, so a future
   pin bump that fixes it upstream silently stops using the shim.
2. **6 SHACL shapes declare `sh:ignoredProperties` with `sh:closed` commented
   out.** `pyshacl` refuses to load the shapes at all. Per the SHACL spec that
   statement constrains nothing without `sh:closed`, so the harness drops it from
   the shapes graph — semantics-preserving.

## Adding a fixture

1. `extract_mapping_fixture.py --list-artifacts` — is there a checked-in artefact?
   If yes, `--source` it and the fixture is `repository-artifact` evidence. The
   `--fixture` name is a `[a-z0-9][a-z0-9-]*` slug and is written only into
   `tools/iptc/fixtures/baseline/`.
2. If not, `--mapping <yml>` prints the literal emitted key set. Hand-author the
   fixture with obviously synthetic values (`9xxx`, `synthetic0...`,
   `Synthetic ...`), register it as `mapping-contract-synthetic`, and fill in the
   `limitation` field. **Never invent a provider fact**, and never capture from a
   live provider call.
3. Register it in `fixtures/provenance.json` with source, transformation,
   emitting mapping, coverage area and known consumers.
4. `python3 -m tools.iptc` to regenerate the audit, then commit the regenerated
   `docs/iptc/*` alongside the fixture.

## Scope

PR 1 is output-neutral. This harness observes; it changes no mapping, no output
shape, no selector and no consumer field path. PR 2 corrects the mappings against
it. PR 3 migrates consumers.
