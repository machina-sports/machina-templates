# RFC 003: Canonical Evidence Contract Phase 1

**Status:** implemented owner candidate, unreleased

This RFC records the owner implementation of the five independently approved
Phase 1 ADRs. The authoritative decision is Design Log 033; this document is the
repository-facing contract for the resulting 0.3.0 candidate.

## Version Boundary

The 0.2 public names remain fixed:

- `SCHEMA_VERSION = "canonical-observation/1.1"`
- `PROFILE_VERSION = "machina-iptc-profile/1.2"`
- `MACHINA_SCHEMA_VERSION = "machina-sports-schema/1"`

The opt-in names are additive:

- `SUCCESSOR_SCHEMA_VERSION = "canonical-observation/1.2"`
- `SUCCESSOR_PROFILE_VERSION = "machina-iptc-profile/1.3"`
- `SUCCESSOR_MACHINA_SCHEMA_VERSION = "machina-sports-schema/1.1"`
- `LONGITUDINAL_SCHEMA_VERSION = "canonical-longitudinal-statistics/1"`
- `LONGITUDINAL_MACHINA_SCHEMA_VERSION = "machina-longitudinal-schema/1"`

`canonical-observation/1` remains readable and is never emitted. Existing
adapters continue to emit `/1.1`; successor production is explicit and only the
sequence-owning execution wrapper can construct successor envelopes.

## Boundaries

`parse_legacy_observation_bytes`, `parse_successor_observation_bytes`, and
`parse_longitudinal_bytes` own disjoint byte classes. Additive textual boundaries
strict-decode UTF-8 and reject BOMs, duplicate object keys, non-finite constants,
non-object roots, unpaired surrogates, and U+FFFD. Legacy Mapping APIs retain
their 0.2 signatures and semantics.

The runtime uses one loader-created `LoadedCanonicalTrustClosureV1`. Documents,
identity occurrences, operation arguments, source values, source artifacts,
expansion witnesses, and operational-ID ledgers are opaque runtime-only objects.
They cannot be serialized into canonical data. Source artifacts retain immutable
original bytes and every trust-critical read re-hashes and reparses those bytes.

`execute_adapter_operation` performs static request, argument, trust, rights, and
capability preflight before adapter import. A successful invocation always fetches
provider bytes; Phase 1 has no cache path. It builds a generated-ID-free document,
validates it, derives operational IDs once from canonical input pointers, builds
the final candidate, optionally projects the graph, serializes once, validates and
postflights those exact bytes, and returns those same frozen bytes.

## Evidence Contracts

- Participation statistics are typed facts. Official and provider-native facts
  are rebuilt from attested same-tuple source bindings; derived facts use exact
  manifest keys and same-document statistic dependencies.
- Spatial inputs carry source/template references, never trusted coordinates or
  caller-selected source distance units and native zone interpretations. Numeric
  source representation is field-attested. Every canonical `SpatialDecimal` is a
  JSON string. Spatial graph status is always `not_projected` with the output-state
  reason.
- Season, career, rolling-window, and date-range facts use the separate
  longitudinal contract. Period and event-anchor fields come from named
  artifact-backed expansions. Sequence parsers are restricted to exact
  non-negative-integer source parsers.
- Coverage is operation-promised, pointer-addressed, and artifact-backed. Present
  unpromised managed collections fail. Empty roots remain covered; zero wildcard
  expansion does not satisfy wildcard capability evidence. Total state is only
  `known | unavailable`.
- Provider IDs remain evidence. Provider namespaces use one optional ASCII slash.
  Graph output requires authoritative registry-backed identity for the complete
  entity census. Provider-scoped identity is operational-only.

## IPTC Projection

Profile 1.3 is generated against unchanged IPTC Sport Schema 1.1 ontology and
SHACL bytes. The generated admissibility manifest distinguishes ontology
membership from exact closed-shape admission and datatype conversion.
`spsocstat:cornerKicks` is the positive team/individual fixture with
`xsd:string`; `spbkbstat:minutesPlayed` and `spamfstat:rushesAttempts` remain
non-admitted unless the pinned shape says otherwise. Successor graphs contain
official IPTC resources only and no Machina identity, crosswalk, provenance, or
rights resources.

## Generated Data

Package-owned data is under `tools/iptc/canonical/data/`. Run:

```bash
python3 tools/iptc/generate_phase1_manifests.py
python3 tools/iptc/generate_phase1_receipts.py
```

The first command derives statistic admissibility from pinned official bytes. The
second freezes the 0.2 Python surface and produces the complete runtime/data/private
symbol inventory, package receipt, and downstream vendoring receipt. Until exact
SHA review and release work begin, receipts deliberately state
`unreleased-owner-phase1` rather than inventing a reviewed commit.

## Release State

This owner candidate is not released, tagged, pushed, merged, or deployed. The
release-specific digest, publisher, tag, and downstream `sports-skills` gates stay
blocked until the separately approved exact-SHA review and release steps.
