# IPTC Sport Schema 1.1 — baseline conformance audit

<!-- GENERATED FILE. Do not edit by hand. -->
<!-- Regenerate with: python3 -m tools.iptc --check -->

## What this document is

The exact, measured distance between what this repository's IPTC mappings currently emit and what IPTC Sport Schema 1.1 actually requires.

The Machina canonical domain model remains authoritative. IPTC Sport Schema is an **output projection** generated from it, never the storage model and never Machina identity.

**Every baseline fixture below is expected to fail.** That is the finding, not a defect in the harness. This PR is foundation-only and output-neutral: it changes no production mapping output, and instead makes the failure measurable so that a later conformance claim is checkable against a number rather than against a judgement. A conformance claim that does not reference this audit is not evidence.

## The pin

| Field | Value |
|---|---|
| Target version | 1.1 |
| Upstream | `https://github.com/iptc/sport-schema` |
| Commit | `0e77bf8678f3702fe81c28673bede35efe47d633` |
| Licence | CC-BY-4.0 |
| Reference files verified by sha256 | 40 |
| Official classes / properties in the pin | 26 / 957 |
| Pinned controlled-vocabulary schemes | 17 |

> The GitHub Releases list for iptc/sport-schema has no 1.1 tag. The commit IS the pin. Do not reference a 1.1 release tag; it does not exist.

### Upstream defects worked around in memory

- `15` pinned Turtle files need the missing `.` after their final `@prefix` directive before a strict parser will read them.
- `6` SHACL shapes declare `sh:ignoredProperties` without an active `sh:closed`, which pyshacl rejects at shape-load time.

Neither shim touches the vendored bytes; both are documented in `agent-templates/iptc-mappings/references/iptc-sport-schema-1.1/UPSTREAM.md`.

### Shared JSON-LD context

`agent-templates/iptc-mappings/contexts/iptc-sport-schema-1.1.context.jsonld`

Every `sportschema.org` and `cv.iptc.org` prefix binding in the shared context is a verbatim copy of what the pinned artefacts declare. Verified mechanically, not by eye.

## The four gates, across the baseline set

| Gate | Target | Baseline total |
|---|---|---|
| unknown `sport:` terms | 0 | **316** |
| invalid NewsCode values | 0 | **8** |
| duplicate resource IDs | 0 | **1** |
| provider properties in the IPTC namespace | 0 | **98** |

Plus **5** NewsCode value(s) that are *unverifiable* rather than invalid: upstream names the scheme but ships no TTL for it at this commit, so no offline check is possible. These are counted separately from invalid values, because the two need different fixes — but **layer 4 fails closed on them**. The profile requires every NewsCode to be provably present in a pinned vocabulary, and missing evidence is not evidence of correctness. See `UPSTREAM.md`, 'Known gap'.

**Do not add the gate rows together.** Gates 1 and 4 overlap by construction: a provider field name emitted under `sport:` is both an undeclared term and an attributable provider leak, and it is counted once in each column because the two columns answer different questions.

## Positive controls

The controlled claim here is **layer 2 only**: the four upstream samples are known to conform against the official SHACL shapes, so if an L2 cell regresses the harness is wrong rather than the data. They are NOT expected to satisfy the Machina profile, which is deliberately stricter than IPTC and imposes the Machina graph envelope, and they are not expected to satisfy layer 4 either — several of them carry codes from schemes upstream ships no TTL for, which layer 4 fails closed on. `machina-profile-conforming-minimal` is the only document in this repository expected to pass everything, and it is the target shape the corrected serializers aim at.

| Fixture | L1 JSON-LD | L2 official SHACL | L3 Machina profile | L4 vocabulary | unknown `sport:` | invalid codes | dup IDs | provider leaks |
|---|---|---|---|---|---|---|---|---|
| `machina-profile-conforming-minimal` | pass | pass | pass | pass | 0 | 0 | 0 | 0 |
| `official-player-bio-01` | pass | pass | pass | **FAIL** | 0 | 0 | 0 | 0 |
| `official-soccer-match-02` | pass | pass | **FAIL** | **FAIL** | 0 | 1 | 0 | 0 |
| `official-soccer-standings` | pass | pass | **FAIL** | **FAIL** | 0 | 5 | 0 | 0 |
| `official-team-roster` | pass | pass | pass | **FAIL** | 0 | 0 | 0 | 0 |

## Corrected — canonical serializer outputs

The 'after' rows. Each is emitted by `tools/iptc/canonical/serialize.py` from a canonical observation that a provider adapter built from checked-in source evidence, and each is expected to pass all four layers with all four gates at zero. Read a green row narrowly: it is evidence that one provider payload shape can be serialized conformingly, not a licence to redistribute that provider's data and not a statement about payloads this fixture does not contain. The `rights` and `MISSING EVIDENCE` lines in each fixture's detail below say which is which.

| Fixture | L1 JSON-LD | L2 official SHACL | L3 Machina profile | L4 vocabulary | unknown `sport:` | invalid codes | dup IDs | provider leaks |
|---|---|---|---|---|---|---|---|---|
| `corrected-api-football-soccer` | pass | pass | pass | pass | 0 | 0 | 0 | 0 |
| `corrected-sportradar-mlb` | pass | pass | pass | pass | 0 | 0 | 0 | 0 |
| `corrected-sportradar-nfl` | pass | pass | pass | pass | 0 | 0 | 0 | 0 |
| `corrected-sportradar-soccer` | pass | pass | pass | pass | 0 | 0 | 0 | 0 |
| `corrected-sportradar-tennis` | pass | pass | pass | pass | 0 | 0 | 0 | 0 |
| `corrected-sports-skills-espn-soccer` | pass | pass | pass | pass | 0 | 0 | 0 | 0 |
| `corrected-stats-perform-opta-soccer` | pass | pass | pass | pass | 0 | 0 | 0 | 0 |

## Baseline — current mapping outputs

One row per supported mapping output. `class` distinguishes a verbatim checked-in artefact from a fixture hand-authored against the mapping contract because no checked-in sample exists.

| Fixture | L1 JSON-LD | L2 official SHACL | L3 Machina profile | L4 vocabulary | unknown `sport:` | invalid codes | dup IDs | provider leaks |
|---|---|---|---|---|---|---|---|---|
| `american-football-event` | pass | **FAIL** (vacuous: 0 targets) | **FAIL** | pass | 14 | 0 | 0 | 2 |
| `api-football-actions` | pass | **FAIL** | **FAIL** | **FAIL** | 7 | 0 | 0 | 0 |
| `api-football-player-stats` | pass | **FAIL** | **FAIL** | pass | 12 | 0 | 0 | 10 |
| `api-football-soccer-event` | pass | **FAIL** (vacuous: 0 targets) | **FAIL** | pass | 13 | 0 | 0 | 1 |
| `api-football-soccer-event-nulls` | pass | **FAIL** (vacuous: 0 targets) | **FAIL** | pass | 13 | 0 | 0 | 1 |
| `api-football-team-stats` | pass | **FAIL** | **FAIL** | pass | 0 | 0 | 0 | 0 |
| `custom-event` | pass | **FAIL** (vacuous: 0 targets) | **FAIL** | pass | 13 | 0 | 0 | 1 |
| `sportradar-mlb-event` | pass | **FAIL** (vacuous: 0 targets) | **FAIL** | pass | 19 | 0 | 0 | 7 |
| `sportradar-nfl-event` | pass | **FAIL** (vacuous: 0 targets) | **FAIL** | pass | 16 | 0 | 0 | 4 |
| `sportradar-soccer-event` | pass | **FAIL** (vacuous: 0 targets) | **FAIL** | pass | 13 | 0 | 0 | 1 |
| `sportradar-soccer-timeline` | pass | **FAIL** | **FAIL** | **FAIL** | 15 | 2 | 0 | 7 |
| `sportradar-tennis-event` | pass | **FAIL** (vacuous: 0 targets) | **FAIL** | **FAIL** | 133 | 6 | 0 | 50 |
| `stats-perform-opta-event` | pass | **FAIL** | **FAIL** | **FAIL** | 41 | 0 | 1 | 14 |
| `stats-perform-opta-timeline` | pass | **FAIL** | **FAIL** | **FAIL** | 7 | 0 | 0 | 0 |

## Negative controls

Each row proves one detector actually fires. A green row here would mean the corresponding gate is decorative.

| Fixture | L1 JSON-LD | L2 official SHACL | L3 Machina profile | L4 vocabulary | unknown `sport:` | invalid codes | dup IDs | provider leaks |
|---|---|---|---|---|---|---|---|---|
| `negative-duplicate-ids` | pass | **FAIL** | **FAIL** | pass | 0 | 0 | 1 | 0 |
| `negative-invalid-newscode` | pass | **FAIL** | pass | **FAIL** | 0 | 1 | 0 | 0 |
| `negative-invented-sport-term` | pass | **FAIL** | **FAIL** | pass | 1 | 0 | 0 | 0 |
| `negative-malformed` | **FAIL** | **FAIL** | **FAIL** | **FAIL** | n/a | n/a | n/a | n/a |
| `negative-null-and-placeholder` | pass | pass | **FAIL** | pass | 0 | 0 | 0 | 0 |
| `negative-provider-leakage` | pass | **FAIL** | **FAIL** | pass | 2 | 0 | 0 | 2 |
| `negative-remote-context` | **FAIL** | **FAIL** | **FAIL** | **FAIL** | n/a | n/a | n/a | n/a |

## Per-mapping detail

### `american-football-event`

- **section:** baseline
- **document:** `tools/iptc/fixtures/baseline/american-football-event.json`
- **fixture class:** mapping-contract-synthetic
- **derived from:** `connectors/american-football/mappings/iptc-american-football-event-mapping.yml`
- **transformation:** Hand-authored from the literal key set of iptc-american-football-event-mapping (output key sport_schema_events). Synthetic league/team/venue ids.
- **emitted by:** iptc-american-football-event-mapping
- **coverage:** American football
- **MISSING EVIDENCE:** No checked-in sample of this mapping's output exists.
- **known consumer dependencies:**
  - `connectors/american-football/workflows/sync-games.yml`

**Layer 1 — JSON-LD parse:** pass, 25 triples.

**Layer 2 — official SHACL:** **VACUOUS** — pyshacl reports `conforms=True`, but the document contains **0 instances of any official IPTC class**, so every `sh:targetClass` matched nothing and no shape was exercised. This is the wrong-namespace defect: the document's `sport:` prefix does not point at `https://sportschema.org/ontologies/main/`, so its `sport:Event`, `sport:Team` and friends are not IPTC classes at all. Counted as a layer-2 failure.

**Layer 3 — Machina profile:** 42 finding(s).

- `invented-sport-term` × 14
- `nested-resource` × 5
- `no-graph-envelope` × 1
- `placeholder-value` × 2
- `provider-id-as-resource-id` × 6
- `provider-property-in-iptc-namespace` × 2
- `sport-namespace-not-official` × 1
- `undefined-term` × 11
- context binds `sport:` to `https://www.sportschema.org/ontologies/sport#`

**Layer 4 — controlled vocabulary:** 0 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


**Unknown `sport:` terms — 14 occurrence(s) of 13 distinct term(s):**

`sport:Season`×1, `sport:Venue`×1, `sport:awayScore`×1, `sport:competition`×1, `sport:competitors`×1, `sport:gameInfo`×1, `sport:halfTime`×1, `sport:homeScore`×1, `sport:qualifier`×2, `sport:season`×1, `sport:status`×1, `sport:venue`×1, `sport:year`×1

**Provider properties in the IPTC namespace:**

- american-football: `sport:gameInfo`, `sport:halfTime`
- api-football: `sport:halfTime`
- sportradar-nfl: `sport:gameInfo`
- sportradar-tennis: `sport:gameInfo`

### `api-football-actions`

- **section:** baseline
- **document:** `tools/iptc/fixtures/baseline/api-football-actions.json`
- **fixture class:** mapping-contract-synthetic
- **derived from:** `agent-templates/iptc-mappings/api-football/event-mapping.yml`
- **transformation:** Hand-authored from the literal key set of the iptc-api-football-events-mapping expression (output key iptc_events). Synthetic ids 9001/9002/9101/9102/9201.
- **emitted by:** iptc-api-football-events-mapping
- **coverage:** API-Football actions
- **MISSING EVIDENCE:** No checked-in sample of this mapping's output exists. The fixture reproduces the emitted shape only.
- **known consumer dependencies:**
  - `agent-templates/iptc-mappings/any-selector/events-summary.yml (iptc-events-summary-timeline)`

**Layer 1 — JSON-LD parse:** pass, 37 triples.

**Layer 2 — official SHACL:** 9 violation(s).

- `ClosedConstraintComponent` on `urn:apifootball:action:23:Goal:9001` path `https://sportschema.org/ontologies/main/label` — Node <urn:apifootball:action:23:Goal:9001> is closed. It cannot have value: Literal("Goal - Normal Goal at 23'")
- `ClosedConstraintComponent` on `urn:apifootball:action:67:Card:9002` path `https://sportschema.org/ontologies/main/label` — Node <urn:apifootball:action:67:Card:9002> is closed. It cannot have value: Literal("Card - Yellow Card at 67'")
- `ClosedConstraintComponent` on `urn:apifootball:player:9101` path `https://sportschema.org/ontologies/main/label` — Node <urn:apifootball:player:9101> is closed. It cannot have value: Literal("Synthetic Scorer")
- `ClosedConstraintComponent` on `urn:apifootball:player:9102` path `https://sportschema.org/ontologies/main/label` — Node <urn:apifootball:player:9102> is closed. It cannot have value: Literal("Synthetic Assister")
- `ClosedConstraintComponent` on `urn:apifootball:player:9201` path `https://sportschema.org/ontologies/main/label` — Node <urn:apifootball:player:9201> is closed. It cannot have value: Literal("Synthetic Booked Player")
- `ClosedConstraintComponent` on `urn:apifootball:team:9001` path `https://sportschema.org/ontologies/main/label` — Node <urn:apifootball:team:9001> is closed. It cannot have value: Literal("Synthetic Home FC")
- `ClosedConstraintComponent` on `urn:apifootball:team:9002` path `https://sportschema.org/ontologies/main/label` — Node <urn:apifootball:team:9002> is closed. It cannot have value: Literal("Synthetic Away FC")
- `DatatypeConstraintComponent` on `urn:apifootball:action:23:Goal:9001` path `https://sportschema.org/ontologies/main/actionDateTime` — Value is not Literal with datatype xsd:dateTime
- `DatatypeConstraintComponent` on `urn:apifootball:action:67:Card:9002` path `https://sportschema.org/ontologies/main/actionDateTime` — Value is not Literal with datatype xsd:dateTime

**Layer 3 — Machina profile:** 36 finding(s).

- `datetime-datatype` × 2
- `invented-sport-term` × 7
- `nested-resource` × 10
- `newscode-not-a-node` × 2
- `no-graph-envelope` × 1
- `placeholder-value` × 2
- `provider-id-as-resource-id` × 12
- context binds `sport:` to `https://sportschema.org/ontologies/main/`

**Layer 4 — controlled vocabulary:** 0 valid, 0 invalid, 0 unresolvable prefix, 2 unverifiable.

- UNVERIFIABLE `http://cv.iptc.org/newscodes/spsocaction/card` — No vocabularies/spsocaction.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spsocaction/goal` — No vocabularies/spsocaction.ttl exists at the pinned commit, so this code cannot be checked offline.

**Unknown `sport:` terms — 7 occurrence(s) of 1 distinct term(s):**

`sport:label`×7

### `api-football-player-stats`

- **section:** baseline
- **document:** `tools/iptc/fixtures/baseline/api-football-player-stats.json`
- **fixture class:** mapping-contract-synthetic
- **derived from:** `agent-templates/iptc-mappings/api-football/event-players-stats.yml`
- **transformation:** Hand-authored from the literal key set of iptc-api-football-event-players-stats (output key iptc_players_statistics), including the Machina `metadata` block the mapping emits alongside the JSON-LD keys, and the goalkeeper-only spread.
- **emitted by:** iptc-api-football-event-players-stats
- **coverage:** API-Football player statistics
- **MISSING EVIDENCE:** No checked-in sample of this mapping's output exists.
- **known consumer dependencies:**
  - `connectors/api-football/sync-fixtures-players-statistics.yml`

**Layer 1 — JSON-LD parse:** pass, 72 triples.

**Layer 2 — official SHACL:** 70 violation(s).

- `ClassConstraintComponent` on `urn:apifootball:player-participation:9101:9000` path `https://sportschema.org/ontologies/main/playerStatus` — Value does not have class skos:Concept
- `ClassConstraintComponent` on `urn:apifootball:player-participation:9103:9000` path `https://sportschema.org/ontologies/main/playerStatus` — Value does not have class skos:Concept
- `ClosedConstraintComponent` on `urn:apifootball:player-participation:9101:9000` path `https://sportschema.org/ontologies/soccer/duelsTotal` — Node <urn:apifootball:player-participation:9101:9000> is closed. It cannot have value: Literal("14", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:apifootball:player-participation:9101:9000` path `https://sportschema.org/ontologies/soccer/offsides` — Node <urn:apifootball:player-participation:9101:9000> is closed. It cannot have value: Literal("1", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:apifootball:player-participation:9101:9000` path `https://sportschema.org/ontologies/soccer/shotsBlocked` — Node <urn:apifootball:player-participation:9101:9000> is closed. It cannot have value: Literal("1", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:apifootball:player-participation:9101:9000` path `https://sportschema.org/ontologies/soccer/passesKey` — Node <urn:apifootball:player-participation:9101:9000> is closed. It cannot have value: Literal("2", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:apifootball:player-participation:9101:9000` path `https://sportschema.org/ontologies/soccer/dribblesSuccessful` — Node <urn:apifootball:player-participation:9101:9000> is closed. It cannot have value: Literal("3", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:apifootball:player-participation:9101:9000` path `https://sportschema.org/ontologies/soccer/dribblesAttempted` — Node <urn:apifootball:player-participation:9101:9000> is closed. It cannot have value: Literal("5", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:apifootball:player-participation:9101:9000` path `https://sportschema.org/ontologies/main/rating` — Node <urn:apifootball:player-participation:9101:9000> is closed. It cannot have value: Literal("7.8", datatype=xsd:double)
- `ClosedConstraintComponent` on `urn:apifootball:player-participation:9101:9000` path `https://sportschema.org/ontologies/soccer/passesCompletePercentage` — Node <urn:apifootball:player-participation:9101:9000> is closed. It cannot have value: Literal("78")
- `ClosedConstraintComponent` on `urn:apifootball:player-participation:9101:9000` path `https://sportschema.org/ontologies/soccer/duelsWon` — Node <urn:apifootball:player-participation:9101:9000> is closed. It cannot have value: Literal("8", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:apifootball:player-participation:9101:9000` path `https://sportschema.org/ontologies/main/minutesPlayed` — Node <urn:apifootball:player-participation:9101:9000> is closed. It cannot have value: Literal("90", datatype=xsd:integer)
- … 58 more, in `baseline-audit.json`.

**Layer 3 — Machina profile:** 55 finding(s).

- `invented-sport-term` × 12
- `nested-resource` × 2
- `newscode-not-a-node` × 2
- `no-graph-envelope` × 1
- `placeholder-value` × 4
- `provider-id-as-resource-id` × 4
- `provider-property-in-iptc-namespace` × 10
- `undeclared-prefix` × 10
- `undefined-term` × 10
- context binds `sport:` to `https://sportschema.org/ontologies/main/`

**Layer 4 — controlled vocabulary:** 1 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


**Unknown `sport:` terms — 12 occurrence(s) of 6 distinct term(s):**

`sport:captain`×2, `sport:jerseyNumber`×2, `sport:minutesPlayed`×2, `sport:position`×2, `sport:rating`×2, `sport:substitute`×2

**Provider properties in the IPTC namespace:**

- api-football: `sport:captain`, `sport:jerseyNumber`, `sport:minutesPlayed`, `sport:rating`, `sport:substitute`

### `api-football-soccer-event`

- **section:** baseline
- **document:** `tools/iptc/fixtures/baseline/api-football-soccer-event.json`
- **fixture class:** repository-artifact
- **derived from:** `agent-templates/iptc-mappings/example-apifootball-output.json`
- **transformation:** verbatim copy
- **emitted by:** iptc-api-football-event-mapping (agent-templates/iptc-mappings/api-football/event-mapping.yml), output key sport_schema_events
- **coverage:** API-Football soccer event
- **known consumer dependencies:**
  - `agent-templates/iptc-mappings/any-selector/event-selector.yml`
  - `agent-templates/iptc-mappings/any-selector/events-selector.yml`
  - `agent-templates/iptc-mappings/any-selector/events-summary.yml`
  - `connectors/api-football/workflows/event-consumer-live.yml`
  - `connectors/api-football/workflows/event-consumer-prelive.yml`
  - `agent-templates/coverage-tools/mappings/selectors.yml`
  - `agent-templates/world-cup-intelligence/mappings/worldcup-iptc-event-to-api-response.yml`

**Layer 1 — JSON-LD parse:** pass, 24 triples.

**Layer 2 — official SHACL:** **VACUOUS** — pyshacl reports `conforms=True`, but the document contains **0 instances of any official IPTC class**, so every `sh:targetClass` matched nothing and no shape was exercised. This is the wrong-namespace defect: the document's `sport:` prefix does not point at `https://sportschema.org/ontologies/main/`, so its `sport:Event`, `sport:Team` and friends are not IPTC classes at all. Counted as a layer-2 failure.

**Layer 3 — Machina profile:** 35 finding(s).

- `invented-sport-term` × 13
- `nested-resource` × 5
- `no-graph-envelope` × 1
- `provider-id-as-resource-id` × 6
- `provider-property-in-iptc-namespace` × 1
- `sport-namespace-not-official` × 1
- `undefined-term` × 8
- context binds `sport:` to `https://www.sportschema.org/ontologies/sport#`

**Layer 4 — controlled vocabulary:** 0 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


**Unknown `sport:` terms — 13 occurrence(s) of 12 distinct term(s):**

`sport:Season`×1, `sport:Venue`×1, `sport:awayScore`×1, `sport:competition`×1, `sport:competitors`×1, `sport:halfTime`×1, `sport:homeScore`×1, `sport:qualifier`×2, `sport:season`×1, `sport:status`×1, `sport:venue`×1, `sport:year`×1

**Provider properties in the IPTC namespace:**

- american-football: `sport:halfTime`
- api-football: `sport:halfTime`

### `api-football-soccer-event-nulls`

- **section:** baseline
- **document:** `tools/iptc/fixtures/baseline/api-football-soccer-event-nulls.json`
- **fixture class:** repository-artifact
- **derived from:** `agent-templates/iptc-mappings/example-iptc-event.json`
- **transformation:** verbatim copy
- **emitted by:** iptc-api-football-event-mapping, pre-kickoff state
- **coverage:** API-Football soccer event, null/absent-value behaviour
- **note:** Kept as a separate fixture because it carries explicit nulls (sport:score.sport:homeScore, sport:awayScore) and a numeric sport:year where the sibling artefact has a string. It is the repository's own evidence for the null-vs-omission rule and for datatype drift between two runs of the SAME mapping. It also uses urn:apifootball:fixture: while the mapping now emits urn:apifootball:sport_event: — an identifier-scheme drift already present in checked-in examples.
- **known consumer dependencies:**
  - `same as api-football-soccer-event`

**Layer 1 — JSON-LD parse:** pass, 22 triples.

**Layer 2 — official SHACL:** **VACUOUS** — pyshacl reports `conforms=True`, but the document contains **0 instances of any official IPTC class**, so every `sh:targetClass` matched nothing and no shape was exercised. This is the wrong-namespace defect: the document's `sport:` prefix does not point at `https://sportschema.org/ontologies/main/`, so its `sport:Event`, `sport:Team` and friends are not IPTC classes at all. Counted as a layer-2 failure.

**Layer 3 — Machina profile:** 37 finding(s).

- `invented-sport-term` × 13
- `nested-resource` × 5
- `no-graph-envelope` × 1
- `null-value` × 2
- `provider-id-as-resource-id` × 6
- `provider-property-in-iptc-namespace` × 1
- `sport-namespace-not-official` × 1
- `undefined-term` × 8
- context binds `sport:` to `https://www.sportschema.org/ontologies/sport#`

**Layer 4 — controlled vocabulary:** 0 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


**Unknown `sport:` terms — 13 occurrence(s) of 12 distinct term(s):**

`sport:Season`×1, `sport:Venue`×1, `sport:awayScore`×1, `sport:competition`×1, `sport:competitors`×1, `sport:halfTime`×1, `sport:homeScore`×1, `sport:qualifier`×2, `sport:season`×1, `sport:status`×1, `sport:venue`×1, `sport:year`×1

**Provider properties in the IPTC namespace:**

- american-football: `sport:halfTime`
- api-football: `sport:halfTime`

### `api-football-team-stats`

- **section:** baseline
- **document:** `tools/iptc/fixtures/baseline/api-football-team-stats.json`
- **fixture class:** mapping-contract-synthetic
- **derived from:** `agent-templates/iptc-mappings/api-football/event-teams-stats.yml`
- **transformation:** Hand-authored from the literal key set of iptc-api-football-event-teams-stats (output key iptc_teams_statistics). Statistic values synthetic.
- **emitted by:** iptc-api-football-event-teams-stats
- **coverage:** API-Football team statistics
- **MISSING EVIDENCE:** No checked-in sample of this mapping's output exists.
- **known consumer dependencies:**
  - `connectors/api-football/sync-fixtures-teams-statistics.yml`

**Layer 1 — JSON-LD parse:** pass, 44 triples.

**Layer 2 — official SHACL:** 31 violation(s).

- `ClosedConstraintComponent` on `urn:apifootball:sport_event:9000` path `rdfs:label` — Node <urn:apifootball:sport_event:9000> is closed. It cannot have value: Literal("Synthetic Home FC vs Synthetic Away FC")
- `ClosedConstraintComponent` on `urn:apifootball:team-participation:9001` path `https://sportschema.org/ontologies/soccer/ejectionsTotal` — Node <urn:apifootball:team-participation:9001> is closed. It cannot have value: Literal("0", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:apifootball:team-participation:9001` path `https://sportschema.org/ontologies/soccer/saves` — Node <urn:apifootball:team-participation:9001> is closed. It cannot have value: Literal("2", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:apifootball:team-participation:9001` path `https://sportschema.org/ontologies/soccer/passesComplete` — Node <urn:apifootball:team-participation:9001> is closed. It cannot have value: Literal("441", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:apifootball:team-participation:9001` path `https://sportschema.org/ontologies/soccer/passesCompletePercentage` — Node <urn:apifootball:team-participation:9001> is closed. It cannot have value: Literal("86")
- `ClosedConstraintComponent` on `urn:apifootball:team-participation:9001` path `rdfs:label` — Node <urn:apifootball:team-participation:9001> is closed. It cannot have value: Literal("Synthetic Home FC participation")
- `ClosedConstraintComponent` on `urn:apifootball:team-participation:9002` path `https://sportschema.org/ontologies/soccer/ejectionsTotal` — Node <urn:apifootball:team-participation:9002> is closed. It cannot have value: Literal("0", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:apifootball:team-participation:9002` path `https://sportschema.org/ontologies/soccer/passesComplete` — Node <urn:apifootball:team-participation:9002> is closed. It cannot have value: Literal("299", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:apifootball:team-participation:9002` path `https://sportschema.org/ontologies/soccer/saves` — Node <urn:apifootball:team-participation:9002> is closed. It cannot have value: Literal("4", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:apifootball:team-participation:9002` path `https://sportschema.org/ontologies/soccer/passesCompletePercentage` — Node <urn:apifootball:team-participation:9002> is closed. It cannot have value: Literal("77")
- `ClosedConstraintComponent` on `urn:apifootball:team-participation:9002` path `rdfs:label` — Node <urn:apifootball:team-participation:9002> is closed. It cannot have value: Literal("Synthetic Away FC participation")
- `ClosedConstraintComponent` on `urn:apifootball:team:9001` path `rdfs:label` — Node <urn:apifootball:team:9001> is closed. It cannot have value: Literal("Synthetic Home FC")
- … 19 more, in `baseline-audit.json`.

**Layer 3 — Machina profile:** 19 finding(s).

- `nested-resource` × 4
- `no-graph-envelope` × 1
- `placeholder-value` × 2
- `provider-id-as-resource-id` × 5
- `undeclared-prefix` × 7
- context binds `sport:` to `https://sportschema.org/ontologies/main/`

**Layer 4 — controlled vocabulary:** 0 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


### `custom-event`

- **section:** baseline
- **document:** `tools/iptc/fixtures/baseline/custom-event.json`
- **fixture class:** repository-artifact
- **derived from:** `agent-templates/iptc-mappings/example-any-event-output.json`
- **transformation:** verbatim copy
- **emitted by:** iptc-custom-event-mapping (agent-templates/iptc-mappings/any-source/custom-event-mapping.yml), output key sport_schema_event
- **coverage:** Generic custom event
- **note:** The generic path fabricates a venue (`urn:custom:venue:unknown`, name 'Unknown') rather than omitting it, and mints event/team ids from mutable display names — the identity hazard the RFC's identifier rules forbid.
- **known consumer dependencies:**
  - `agent-templates/iptc-mappings/any-selector/*`
  - `agent-templates/chat-completion/workflows/chat-moderator.yml`

**Layer 1 — JSON-LD parse:** pass, 22 triples.

**Layer 2 — official SHACL:** **VACUOUS** — pyshacl reports `conforms=True`, but the document contains **0 instances of any official IPTC class**, so every `sh:targetClass` matched nothing and no shape was exercised. This is the wrong-namespace defect: the document's `sport:` prefix does not point at `https://sportschema.org/ontologies/main/`, so its `sport:Event`, `sport:Team` and friends are not IPTC classes at all. Counted as a layer-2 failure.

**Layer 3 — Machina profile:** 31 finding(s).

- `invented-sport-term` × 13
- `nested-resource` × 5
- `no-graph-envelope` × 1
- `placeholder-value` × 2
- `provider-property-in-iptc-namespace` × 1
- `sport-namespace-not-official` × 1
- `undefined-term` × 8
- context binds `sport:` to `https://www.sportschema.org/ontologies/sport#`

**Layer 4 — controlled vocabulary:** 0 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


**Unknown `sport:` terms — 13 occurrence(s) of 12 distinct term(s):**

`sport:Season`×1, `sport:Venue`×1, `sport:awayScore`×1, `sport:competition`×1, `sport:competitors`×1, `sport:halfTime`×1, `sport:homeScore`×1, `sport:qualifier`×2, `sport:season`×1, `sport:status`×1, `sport:venue`×1, `sport:year`×1

**Provider properties in the IPTC namespace:**

- american-football: `sport:halfTime`
- api-football: `sport:halfTime`

### `sportradar-mlb-event`

- **section:** baseline
- **document:** `tools/iptc/fixtures/baseline/sportradar-mlb-event.json`
- **fixture class:** mapping-contract-synthetic
- **derived from:** `connectors/sportradar-mlb/mappings/iptc-sport-event.yml`
- **transformation:** Hand-authored from the literal key set of iptc-sportradar-event-mlb-mapping (output key sport_schema_events). Synthetic UUIDs.
- **emitted by:** iptc-sportradar-event-mlb-mapping
- **coverage:** Sportradar MLB
- **MISSING EVIDENCE:** No checked-in sample of this mapping's output exists.
- **note:** The mapping deliberately emits sport:score with explicit nulls (its own comment says so) because schedule.json carries no runs and a later workflow merges them in. The nulls are load-bearing for a downstream reader today, which is exactly why the null rule needs a migration and not a flag day.
- **known consumer dependencies:**
  - `connectors/sportradar-mlb/sync-games.yml`
  - `connectors/sportradar-mlb/sync-results.yml`
  - `connectors/sportradar-mlb/sync-pitchers.yml`

**Layer 1 — JSON-LD parse:** pass, 27 triples.

**Layer 2 — official SHACL:** **VACUOUS** — pyshacl reports `conforms=True`, but the document contains **0 instances of any official IPTC class**, so every `sh:targetClass` matched nothing and no shape was exercised. This is the wrong-namespace defect: the document's `sport:` prefix does not point at `https://sportschema.org/ontologies/main/`, so its `sport:Event`, `sport:Team` and friends are not IPTC classes at all. Counted as a layer-2 failure.

**Layer 3 — Machina profile:** 41 finding(s).

- `invented-sport-term` × 19
- `nested-resource` × 5
- `no-graph-envelope` × 1
- `null-value` × 2
- `provider-property-in-iptc-namespace` × 7
- `sport-namespace-not-official` × 1
- `undefined-term` × 6
- context binds `sport:` to `https://www.sportschema.org/ontologies/sport#`

**Layer 4 — controlled vocabulary:** 0 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


**Unknown `sport:` terms — 19 occurrence(s) of 16 distinct term(s):**

`sport:Season`×1, `sport:Venue`×1, `sport:abbreviation`×2, `sport:awayScore`×1, `sport:competition`×1, `sport:competitors`×1, `sport:doubleHeader`×1, `sport:gameNumber`×1, `sport:homeScore`×1, `sport:market`×2, `sport:matchStatus`×1, `sport:qualifier`×2, `sport:season`×1, `sport:status`×1, `sport:venue`×1, `sport:year`×1

**Provider properties in the IPTC namespace:**

- sportradar-mlb: `sport:abbreviation`, `sport:doubleHeader`, `sport:gameNumber`, `sport:market`, `sport:matchStatus`
- sportradar-nfl: `sport:matchStatus`
- sportradar-soccer: `sport:abbreviation`, `sport:matchStatus`

### `sportradar-nfl-event`

- **section:** baseline
- **document:** `tools/iptc/fixtures/baseline/sportradar-nfl-event.json`
- **fixture class:** mapping-contract-synthetic
- **derived from:** `connectors/sportradar-nfl/mappings/iptc-sport-event.yml`
- **transformation:** Hand-authored from the literal key set of iptc-sportradar-event-nfl-mapping (output key sport_schema_events). Synthetic UUIDs.
- **emitted by:** iptc-sportradar-event-nfl-mapping
- **coverage:** Sportradar NFL
- **MISSING EVIDENCE:** No checked-in sample of this mapping's output exists.
- **note:** sport:score.sport:halfTime is the raw Sportradar period object, verbatim, so the fixture carries raw provider keys (period_type, home_points, ...) inside an IPTC-namespaced property. The season is hardcoded to 2025 in the mapping.
- **known consumer dependencies:**
  - `connectors/sportradar-nfl/workflows/event-consumer-live.yml`
  - `connectors/sportradar-nfl/workflows/event-consumer-prelive.yml`
  - `connectors/sportradar-nfl/sync-games.yml`

**Layer 1 — JSON-LD parse:** pass, 26 triples.

**Layer 2 — official SHACL:** **VACUOUS** — pyshacl reports `conforms=True`, but the document contains **0 instances of any official IPTC class**, so every `sh:targetClass` matched nothing and no shape was exercised. This is the wrong-namespace defect: the document's `sport:` prefix does not point at `https://sportschema.org/ontologies/main/`, so its `sport:Event`, `sport:Team` and friends are not IPTC classes at all. Counted as a layer-2 failure.

**Layer 3 — Machina profile:** 39 finding(s).

- `invented-sport-term` × 16
- `nested-resource` × 5
- `no-graph-envelope` × 1
- `provider-property-in-iptc-namespace` × 4
- `sport-namespace-not-official` × 1
- `undefined-term` × 12
- context binds `sport:` to `https://www.sportschema.org/ontologies/sport#`

**Layer 4 — controlled vocabulary:** 0 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


**Unknown `sport:` terms — 16 occurrence(s) of 14 distinct term(s):**

`sport:Season`×1, `sport:Venue`×1, `sport:abbreviation`×2, `sport:awayScore`×1, `sport:competition`×1, `sport:competitors`×1, `sport:halfTime`×1, `sport:homeScore`×1, `sport:matchStatus`×1, `sport:qualifier`×2, `sport:season`×1, `sport:status`×1, `sport:venue`×1, `sport:year`×1

**Provider properties in the IPTC namespace:**

- american-football: `sport:halfTime`
- api-football: `sport:halfTime`
- sportradar-mlb: `sport:abbreviation`, `sport:matchStatus`
- sportradar-nfl: `sport:matchStatus`
- sportradar-soccer: `sport:abbreviation`, `sport:matchStatus`

### `sportradar-soccer-event`

- **section:** baseline
- **document:** `tools/iptc/fixtures/baseline/sportradar-soccer-event.json`
- **fixture class:** repository-artifact
- **derived from:** `agent-templates/iptc-mappings/example-sportradar-output.json`
- **transformation:** Unwrapped the single top-level `sport-schema-event` envelope key. Content otherwise unchanged; re-serialized with 2-space indent and sorted-key order preserved from the source.
- **emitted by:** iptc-sportradar-event-mapping (connectors/sportradar-soccer/mappings/iptc-sport-event.yml), output key sport_schema_events
- **coverage:** Sportradar soccer event
- **known consumer dependencies:**
  - `connectors/sportradar-soccer/workflows/event-consumer.yml`
  - `connectors/sportradar-soccer/workflows/event-consumer-live.yml`
  - `connectors/sportradar-soccer/workflows/event-consumer-prelive.yml`
  - `connectors/sportradar-soccer/workflows/load-round-events.yml`
  - `agent-templates/iptc-mappings/any-selector/*`
  - `agent-templates/coverage-tools/mappings/selectors.yml`

**Layer 1 — JSON-LD parse:** pass, 22 triples.

**Layer 2 — official SHACL:** **VACUOUS** — pyshacl reports `conforms=True`, but the document contains **0 instances of any official IPTC class**, so every `sh:targetClass` matched nothing and no shape was exercised. This is the wrong-namespace defect: the document's `sport:` prefix does not point at `https://sportschema.org/ontologies/main/`, so its `sport:Event`, `sport:Team` and friends are not IPTC classes at all. Counted as a layer-2 failure.

**Layer 3 — Machina profile:** 29 finding(s).

- `invented-sport-term` × 13
- `nested-resource` × 5
- `no-graph-envelope` × 1
- `provider-property-in-iptc-namespace` × 1
- `sport-namespace-not-official` × 1
- `undefined-term` × 8
- context binds `sport:` to `https://www.sportschema.org/ontologies/sport#`

**Layer 4 — controlled vocabulary:** 0 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


**Unknown `sport:` terms — 13 occurrence(s) of 12 distinct term(s):**

`sport:Season`×1, `sport:Venue`×1, `sport:awayScore`×1, `sport:competition`×1, `sport:competitors`×1, `sport:halfTime`×1, `sport:homeScore`×1, `sport:qualifier`×2, `sport:season`×1, `sport:status`×1, `sport:venue`×1, `sport:year`×1

**Provider properties in the IPTC namespace:**

- american-football: `sport:halfTime`
- api-football: `sport:halfTime`

### `sportradar-soccer-timeline`

- **section:** baseline
- **document:** `tools/iptc/fixtures/baseline/sportradar-soccer-timeline.json`
- **fixture class:** mapping-contract-synthetic
- **derived from:** `connectors/sportradar-soccer/mappings/iptc-sport-event.yml`
- **transformation:** Hand-authored from the literal key set of iptc-sportradar-events-timeline-mapping (output key iptc_events_timeline), including the score_change and card conditional spreads. Synthetic sr: identifiers.
- **emitted by:** iptc-sportradar-events-timeline-mapping
- **coverage:** Sportradar soccer timeline
- **MISSING EVIDENCE:** No checked-in sample of this mapping's output exists.
- **note:** Preserves the mapping's `spsocaction:` compact value for sport:actionType even though no @context in that mapping binds the spsocaction prefix. That is what the mapping emits.
- **known consumer dependencies:**
  - `agent-templates/iptc-mappings/any-selector/events-summary.yml (iptc-events-summary-timeline)`

**Layer 1 — JSON-LD parse:** pass, 36 triples.

**Layer 2 — official SHACL:** 15 violation(s).

- `ClosedConstraintComponent` on `urn:sportradar:action:sr:action:9000001` path `https://sportschema.org/ontologies/main/awayScore` — Node <urn:sportradar:action:sr:action:9000001> is closed. It cannot have value: Literal("0", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:sportradar:action:sr:action:9000001` path `https://sportschema.org/ontologies/main/homeScore` — Node <urn:sportradar:action:sr:action:9000001> is closed. It cannot have value: Literal("1", datatype=xsd:integer)
- `ClosedConstraintComponent` on `urn:sportradar:action:sr:action:9000001` path `https://sportschema.org/ontologies/main/label` — Node <urn:sportradar:action:sr:action:9000001> is closed. It cannot have value: Literal("Score Change at 23' - Regular Period")
- `ClosedConstraintComponent` on `urn:sportradar:action:sr:action:9000001` path `https://sportschema.org/ontologies/main/scoreMethod` — Node <urn:sportradar:action:sr:action:9000001> is closed. It cannot have value: Literal("penalty")
- `ClosedConstraintComponent` on `urn:sportradar:action:sr:action:9000001` path `https://sportschema.org/ontologies/main/periodType` — Node <urn:sportradar:action:sr:action:9000001> is closed. It cannot have value: Literal("regular_period")
- `ClosedConstraintComponent` on `urn:sportradar:action:sr:action:9000002` path `https://sportschema.org/ontologies/main/label` — Node <urn:sportradar:action:sr:action:9000002> is closed. It cannot have value: Literal("Yellow Card at 67' - Regular Period")
- `ClosedConstraintComponent` on `urn:sportradar:action:sr:action:9000002` path `https://sportschema.org/ontologies/main/periodType` — Node <urn:sportradar:action:sr:action:9000002> is closed. It cannot have value: Literal("regular_period")
- `ClosedConstraintComponent` on `urn:sportradar:action:sr:action:9000002` path `https://sportschema.org/ontologies/main/cardColor` — Node <urn:sportradar:action:sr:action:9000002> is closed. It cannot have value: Literal("yellow")
- `ClosedConstraintComponent` on `urn:sportradar:action:sr:action:9000002` path `https://sportschema.org/ontologies/main/cardType` — Node <urn:sportradar:action:sr:action:9000002> is closed. It cannot have value: Literal("yellow")
- `ClosedConstraintComponent` on `urn:sportradar:player-participation:sr:player:9101` path `https://sportschema.org/ontologies/main/playerRole` — Node <urn:sportradar:player-participation:sr:player:9101> is closed. It cannot have value: Literal("scorer")
- `ClosedConstraintComponent` on `urn:sportradar:player:sr:player:9101` path `https://sportschema.org/ontologies/main/label` — Node <urn:sportradar:player:sr:player:9101> is closed. It cannot have value: Literal("Synthetic Scorer")
- `ClosedConstraintComponent` on `urn:sportradar:team:sr:competitor:9001` path `https://sportschema.org/ontologies/main/label` — Node <urn:sportradar:team:sr:competitor:9001> is closed. It cannot have value: Literal("Synthetic Home SC")
- … 3 more, in `baseline-audit.json`.

**Layer 3 — Machina profile:** 40 finding(s).

- `controlled-vocabulary-undeclared-prefix` × 2
- `invented-sport-term` × 15
- `nested-resource` × 6
- `no-graph-envelope` × 1
- `null-value` × 3
- `provider-property-in-iptc-namespace` × 7
- `undefined-term` × 6
- context binds `sport:` to `https://sportschema.org/ontologies/main/`

**Layer 4 — controlled vocabulary:** 0 valid, 0 invalid, 2 unresolvable prefix, 0 unverifiable.

- UNRESOLVABLE `spsocaction:score-change` on `sport:actionType` — Prefix is not bound by any @context in scope.
- UNRESOLVABLE `spsocaction:yellow-card` on `sport:actionType` — Prefix is not bound by any @context in scope.

**Unknown `sport:` terms — 15 occurrence(s) of 10 distinct term(s):**

`sport:awayScore`×1, `sport:cardColor`×1, `sport:cardType`×1, `sport:homeScore`×1, `sport:label`×5, `sport:periodType`×2, `sport:playerRole`×1, `sport:scoreMethod`×1, `sport:shootoutAwayScore`×1, `sport:shootoutHomeScore`×1

**Provider properties in the IPTC namespace:**

- sportradar-soccer: `sport:cardColor`, `sport:cardType`, `sport:periodType`, `sport:scoreMethod`, `sport:shootoutAwayScore`, `sport:shootoutHomeScore`

### `sportradar-tennis-event`

- **section:** baseline
- **document:** `tools/iptc/fixtures/baseline/sportradar-tennis-event.json`
- **fixture class:** mapping-contract-synthetic
- **derived from:** `connectors/sportradar-tennis/mappings/iptc-event-mapping.yml`
- **transformation:** Hand-authored from the literal key set of iptc-sportradar-tennis-event-mapping (output key sport_schema_events). Synthetic sr: identifiers and player names.
- **emitted by:** iptc-sportradar-tennis-event-mapping
- **coverage:** Sportradar tennis
- **MISSING EVIDENCE:** No checked-in sample of this mapping's output exists.
- **note:** This is the widest mapping in the repository by distinct sport: term count. It also emits sport:round twice with two different shapes (once under sport:gameInfo as a string, once as an object), and an invented sport:sport node id urn:iptc:sport:tennis.
- **known consumer dependencies:**
  - `connectors/sportradar-tennis/workflows/sync-season-summaries.yml`

**Layer 1 — JSON-LD parse:** pass, 148 triples.

**Layer 2 — official SHACL:** **VACUOUS** — pyshacl reports `conforms=True`, but the document contains **0 instances of any official IPTC class**, so every `sh:targetClass` matched nothing and no shape was exercised. This is the wrong-namespace defect: the document's `sport:` prefix does not point at `https://sportschema.org/ontologies/main/`, so its `sport:Event`, `sport:Team` and friends are not IPTC classes at all. Counted as a layer-2 failure.

**Layer 3 — Machina profile:** 208 finding(s).

- `controlled-vocabulary-undeclared-prefix` × 6
- `invented-sport-term` × 133
- `missing-node-id` × 1
- `nested-resource` × 7
- `no-graph-envelope` × 1
- `null-value` × 1
- `placeholder-value` × 1
- `provider-property-in-iptc-namespace` × 50
- `sport-namespace-not-official` × 1
- `undefined-term` × 7
- context binds `sport:` to `https://www.sportschema.org/ontologies/sport#`

**Layer 4 — controlled vocabulary:** 0 valid, 0 invalid, 6 unresolvable prefix, 0 unverifiable.

- UNRESOLVABLE `sr:competitor:9101` on `sport:winnerId` — Prefix is not bound by any @context in scope.
- UNRESOLVABLE `sr:competitor:9101` on `sport:competitorId` — Prefix is not bound by any @context in scope.
- UNRESOLVABLE `sr:competitor:9102` on `sport:competitorId` — Prefix is not bound by any @context in scope.
- UNRESOLVABLE `sr:category:9001` on `sport:categoryId` — Prefix is not bound by any @context in scope.
- UNRESOLVABLE `sr:competition:9000` on `sport:parentId` — Prefix is not bound by any @context in scope.
- UNRESOLVABLE `sportradar-tennis:sport_event_summary` on `sport:documentType` — Prefix is not bound by any @context in scope.

**Unknown `sport:` terms — 133 occurrence(s) of 87 distinct term(s):**

`sport:Competitor`×2, `sport:Season`×1, `sport:Sport`×1, `sport:Stage`×1, `sport:Venue`×1, `sport:abbreviation`×4, `sport:aces`×2, `sport:awayScore`×4, `sport:bestOf`×2, `sport:bracketNumber`×2, `sport:breakpointsWon`×2, `sport:category`×1, `sport:categoryId`×1, `sport:categoryName`×1, `sport:channelName`×1, `sport:channels`×1, `sport:competition`×1, `sport:competitionContext`×1, `sport:competitionGender`×1, `sport:competitionLevel`×1, `sport:competitorId`×2, `sport:competitorName`×2, `sport:competitorStats`×1, `sport:competitors`×1, `sport:country`×2, `sport:countryCode`×2, `sport:coverage`×1, `sport:detailedServeOutcomes`×1, `sport:documentType`×1, `sport:doubleFaults`×2, `sport:enhancedStats`×1, `sport:estimated`×1, `sport:eventDetails`×1, `sport:firstServePointsWon`×2, `sport:firstServeSuccessful`×2, `sport:gameInfo`×1, `sport:gamesWon`×2, `sport:genderCategory`×1, `sport:groups`×1, `sport:hasWinner`×1, `sport:homeScore`×4, `sport:isFinished`×1, `sport:level`×1, `sport:matchType`×1, `sport:maxGamesInARow`×2, `sport:maxPointsInARow`×2, `sport:mode`×1, `sport:order`×1, `sport:parentId`×1, `sport:periodNumber`×3, `sport:periodScores`×1, `sport:periodType`×3, `sport:phase`×1, `sport:playByPlay`×1, `sport:pointsWon`×2, `sport:pointsWonFromLast10`×2, `sport:qualifier`×4, `sport:round`×2, `sport:roundName`×1, `sport:roundNumber`×2, `sport:scores`×1, `sport:season`×1, `sport:seasonContext`×1, `sport:seasonEndDate`×1, `sport:seasonStartDate`×1, `sport:secondServePointsWon`×2, `sport:secondServeSuccessful`×2, `sport:seed`×2, `sport:selected`×1, `sport:serviceGamesWon`×2, `sport:servicePointsLost`×2, `sport:servicePointsWon`×2, `sport:stage`×1, `sport:stagePhase`×1, `sport:startTime`×1, `sport:startTimeConfirmed`×1, `sport:statistics`×3, `sport:status`×2, `sport:tiebreaksWon`×2, `sport:timezone`×1, `sport:title`×1, `sport:totalBreakpoints`×2, `sport:totalSets`×1, `sport:type`×1, `sport:venue`×1, `sport:winnerId`×1, `sport:year`×1

**Provider properties in the IPTC namespace:**

- american-football: `sport:gameInfo`
- sportradar-mlb: `sport:abbreviation`
- sportradar-nfl: `sport:gameInfo`
- sportradar-soccer: `sport:abbreviation`, `sport:channelName`, `sport:channels`, `sport:periodType`
- sportradar-tennis: `sport:bestOf`, `sport:bracketNumber`, `sport:categoryId`, `sport:categoryName`, `sport:competitionContext`, `sport:competitionLevel`, `sport:competitorId`, `sport:competitorName`, `sport:competitorStats`, `sport:coverage`, `sport:detailedServeOutcomes`, `sport:documentType`, `sport:enhancedStats`, `sport:estimated`, `sport:eventDetails`, `sport:gameInfo`, `sport:genderCategory`, `sport:groups`, `sport:hasWinner`, `sport:isFinished`, `sport:matchType`, `sport:mode`, `sport:parentId`, `sport:playByPlay`, `sport:roundName`, `sport:roundNumber`, `sport:seasonContext`, `sport:seasonEndDate`, `sport:seasonStartDate`, `sport:seed`, `sport:selected`, `sport:stagePhase`, `sport:startTimeConfirmed`, `sport:totalSets`, `sport:winnerId`

### `stats-perform-opta-event`

- **section:** baseline
- **document:** `tools/iptc/fixtures/baseline/stats-perform-opta-event.json`
- **fixture class:** mapping-contract-synthetic
- **derived from:** `connectors/stats-perform/mappings/iptc-sport-event.yml`
- **transformation:** Hand-authored from the literal key set of iptc-opta-event-mapping (output key sport_schema_events), including the Machina `version_control` block and the nested `sport:timeline` array with its own nested @context. Synthetic opta identifiers.
- **emitted by:** iptc-opta-event-mapping
- **coverage:** Stats Perform / Opta event (with embedded timeline)
- **MISSING EVIDENCE:** No checked-in sample of this mapping's output exists.
- **known consumer dependencies:**
  - `connectors/stats-perform/workflows/sp-opta-event-consumer-live.yml`
  - `connectors/stats-perform/workflows/sp-opta-event-consumer-prelive.yml`
  - `connectors/stats-perform/workflows/sp-opta-event-synchronize.yml`
  - `connectors/stats-perform/workflows/sync-update-live.yml`

**Layer 1 — JSON-LD parse:** pass, 69 triples.

**Layer 2 — official SHACL:** 8 violation(s).

- `ClosedConstraintComponent` on `urn:opta:action:synthetic0eventid01` path `https://sportschema.org/ontologies/main/label` — Node <urn:opta:action:synthetic0eventid01> is closed. It cannot have value: Literal("G at 23' - Period 1")
- `ClosedConstraintComponent` on `urn:opta:player:synthetic0persoid01` path `https://sportschema.org/ontologies/main/label` — Node <urn:opta:player:synthetic0persoid01> is closed. It cannot have value: Literal("Synthetic Scorer")
- `ClosedConstraintComponent` on `urn:opta:team:synthetic0teamid001` path `https://www.sportschema.org/ontologies/sport#shortName` — Node <urn:opta:team:synthetic0teamid001> is closed. It cannot have value: Literal("Home Utd")
- `ClosedConstraintComponent` on `urn:opta:team:synthetic0teamid001` path `https://www.sportschema.org/ontologies/sport#code` — Node <urn:opta:team:synthetic0teamid001> is closed. It cannot have value: Literal("SHU")
- `ClosedConstraintComponent` on `urn:opta:team:synthetic0teamid001` path `https://www.sportschema.org/ontologies/sport#officialName` — Node <urn:opta:team:synthetic0teamid001> is closed. It cannot have value: Literal("Synthetic Home United FC")
- `ClosedConstraintComponent` on `urn:opta:team:synthetic0teamid001` path `https://sportschema.org/ontologies/main/label` — Node <urn:opta:team:synthetic0teamid001> is closed. It cannot have value: Literal("Synthetic Home United")
- `ClosedConstraintComponent` on `urn:opta:team:synthetic0teamid001` path `https://www.sportschema.org/ontologies/sport#qualifier` — Node <urn:opta:team:synthetic0teamid001> is closed. It cannot have value: Literal("home")
- `DatatypeConstraintComponent` on `urn:opta:action:synthetic0eventid01` path `https://sportschema.org/ontologies/main/actionDateTime` — Value is not Literal with datatype xsd:dateTime

**Layer 3 — Machina profile:** 90 finding(s).

- `duplicate-node-id` × 1
- `invented-sport-term` × 41
- `nested-context` × 1
- `nested-resource` × 11
- `newscode-not-a-node` × 1
- `no-graph-envelope` × 1
- `null-value` × 3
- `provider-property-in-iptc-namespace` × 14
- `sport-namespace-not-official` × 1
- `undefined-term` × 16
- context binds `sport:` to `https://www.sportschema.org/ontologies/sport#`

**Layer 4 — controlled vocabulary:** 0 valid, 0 invalid, 0 unresolvable prefix, 1 unverifiable.

- UNVERIFIABLE `http://cv.iptc.org/newscodes/spsocaction/g` — No vocabularies/spsocaction.ttl exists at the pinned commit, so this code cannot be checked offline.

**Unknown `sport:` terms — 41 occurrence(s) of 32 distinct term(s):**

`sport:Season`×1, `sport:Stage`×1, `sport:Venue`×1, `sport:aggregate`×1, `sport:awayScore`×2, `sport:code`×2, `sport:competition`×1, `sport:competitionCode`×1, `sport:competitors`×1, `sport:coverageLevel`×1, `sport:halfTime`×1, `sport:homeScore`×2, `sport:knownName`×1, `sport:label`×3, `sport:localDate`×1, `sport:localTime`×1, `sport:matchInfo`×1, `sport:neutral`×1, `sport:numberOfPeriods`×1, `sport:officialName`×2, `sport:penalties`×1, `sport:periodLength`×1, `sport:qualifier`×2, `sport:season`×1, `sport:shortName`×3, `sport:stage`×1, `sport:status`×1, `sport:timeline`×1, `sport:var`×1, `sport:venue`×1, `sport:week`×1, `sport:winner`×1

**Provider properties in the IPTC namespace:**

- american-football: `sport:halfTime`
- api-football: `sport:halfTime`
- sportradar-soccer: `sport:aggregate`
- stats-perform-opta: `sport:competitionCode`, `sport:coverageLevel`, `sport:knownName`, `sport:localDate`, `sport:localTime`, `sport:matchInfo`, `sport:neutral`, `sport:numberOfPeriods`, `sport:periodLength`, `sport:timeline`, `sport:var`, `sport:week`

**Duplicate resource IDs:**

- `urn:opta:team:synthetic0teamid001` × 2

### `stats-perform-opta-timeline`

- **section:** baseline
- **document:** `tools/iptc/fixtures/baseline/stats-perform-opta-timeline.json`
- **fixture class:** mapping-contract-synthetic
- **derived from:** `connectors/stats-perform/mappings/iptc-sport-event.yml`
- **transformation:** The `sport:timeline` element shape from iptc-opta-event-mapping, extracted as a standalone document set. This is how a consumer that reads only the timeline sees it.
- **emitted by:** iptc-opta-event-mapping, sport:timeline array
- **coverage:** Stats Perform / Opta timeline
- **MISSING EVIDENCE:** No checked-in sample exists, and the timeline is not a separately named mapping upstream of this fixture — it is a nested array inside the event mapping.
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 38 triples.

**Layer 2 — official SHACL:** 11 violation(s).

- `ClosedConstraintComponent` on `urn:opta:action:synthetic0eventid01` path `https://sportschema.org/ontologies/main/label` — Node <urn:opta:action:synthetic0eventid01> is closed. It cannot have value: Literal("G at 23' - Period 1")
- `ClosedConstraintComponent` on `urn:opta:action:synthetic0eventid02` path `https://sportschema.org/ontologies/main/label` — Node <urn:opta:action:synthetic0eventid02> is closed. It cannot have value: Literal("Yc at 67' - Period 2")
- `ClosedConstraintComponent` on `urn:opta:player:synthetic0persoid01` path `https://sportschema.org/ontologies/main/label` — Node <urn:opta:player:synthetic0persoid01> is closed. It cannot have value: Literal("Synthetic Scorer")
- `ClosedConstraintComponent` on `urn:opta:player:synthetic0persoid02` path `https://sportschema.org/ontologies/main/label` — Node <urn:opta:player:synthetic0persoid02> is closed. It cannot have value: Literal("Synthetic Assister")
- `ClosedConstraintComponent` on `urn:opta:player:synthetic0persoid03` path `https://sportschema.org/ontologies/main/label` — Node <urn:opta:player:synthetic0persoid03> is closed. It cannot have value: Literal("Synthetic Booked Player")
- `ClosedConstraintComponent` on `urn:opta:team:synthetic0teamid001` path `https://sportschema.org/ontologies/main/label` — Node <urn:opta:team:synthetic0teamid001> is closed. It cannot have value: Literal("Synthetic Home United")
- `ClosedConstraintComponent` on `urn:opta:team:synthetic0teamid002` path `https://sportschema.org/ontologies/main/label` — Node <urn:opta:team:synthetic0teamid002> is closed. It cannot have value: Literal("Synthetic Away Town")
- `DatatypeConstraintComponent` on `urn:opta:action:synthetic0eventid01` path `https://sportschema.org/ontologies/main/actionDateTime` — Value is not Literal with datatype xsd:dateTime
- `DatatypeConstraintComponent` on `urn:opta:action:synthetic0eventid02` path `https://sportschema.org/ontologies/main/actionDateTime` — Value is not Literal with datatype xsd:dateTime
- `NodeKindConstraintComponent` on `urn:opta:player-participation:synthetic0persoid02` path `https://sportschema.org/ontologies/main/role` — Value is not of Node Kind sh:IRI
- `NodeKindConstraintComponent` on `urn:opta:player-participation:synthetic0persoid02` path `https://sportschema.org/ontologies/main/role` — Value is not of Node Kind sh:IRI

**Layer 3 — Machina profile:** 28 finding(s).

- `invented-sport-term` × 7
- `nested-resource` × 10
- `newscode-not-a-node` × 2
- `no-graph-envelope` × 1
- `undefined-term` × 8
- context binds `sport:` to `https://sportschema.org/ontologies/main/`

**Layer 4 — controlled vocabulary:** 0 valid, 0 invalid, 0 unresolvable prefix, 2 unverifiable.

- UNVERIFIABLE `http://cv.iptc.org/newscodes/spsocaction/g` — No vocabularies/spsocaction.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spsocaction/yc` — No vocabularies/spsocaction.ttl exists at the pinned commit, so this code cannot be checked offline.

**Unknown `sport:` terms — 7 occurrence(s) of 1 distinct term(s):**

`sport:label`×7

### `machina-profile-conforming-minimal`

- **section:** conforming
- **document:** `tools/iptc/fixtures/conforming/machina-profile-conforming-minimal.json`
- **fixture class:** machina-authored-conforming
- **provenance:** Machina-authored. Every term IRI copied from the pinned ontology; the shared context at agent-templates/iptc-mappings/contexts/iptc-sport-schema-1.1.context.jsonld is inlined.
- **role:** Tightly-scoped positive control for ALL FOUR layers and all four counters at zero. This is the only fixture in this repository that is expected to pass everything, and it is what the PR 2 serializers are aiming at.
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 90 triples.

**Layer 2 — official SHACL:** conforms, over 13 instance(s) of an official IPTC class.

**Layer 3 — Machina profile:** conforms.

**Layer 4 — controlled vocabulary:** 10 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


### `official-player-bio-01`

- **section:** conforming
- **document:** `agent-templates/iptc-mappings/references/iptc-sport-schema-1.1/samples/json-ld/player-bio-01.jsonld`
- **fixture class:** official-upstream-sample
- **provenance:** Byte-exact upstream samples/json-ld/player-bio-01.jsonld at the pinned commit.
- **role:** Smallest official positive control; keeps the fast test path fast.
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 40 triples.

**Layer 2 — official SHACL:** conforms, over 9 instance(s) of an official IPTC class.

**Layer 3 — Machina profile:** conforms.

**Layer 4 — controlled vocabulary:** 1 valid, 0 invalid, 0 unresolvable prefix, 2 unverifiable.

- UNVERIFIABLE `http://cv.iptc.org/newscodes/spphasestatus/active` — No vocabularies/spphasestatus.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spphasestatus/inactive` — No vocabularies/spphasestatus.ttl exists at the pinned commit, so this code cannot be checked offline.

### `official-soccer-match-02`

- **section:** conforming
- **document:** `agent-templates/iptc-mappings/references/iptc-sport-schema-1.1/samples/json-ld/soccer-match-02.jsonld`
- **fixture class:** official-upstream-sample
- **provenance:** Byte-exact upstream samples/json-ld/soccer-match-02.jsonld at the pinned commit.
- **role:** Positive control for layers 1 and 2. Known to conform against the official SHACL shapes. A layer-1 or layer-2 failure here means the harness is wrong, not the data.
- **profile expectation:** Satisfies every Machina structural rule — one document-level @context, a flat @graph, node references by @id, NewsCodes as node references — which is worth noting, because it shows layer 3 is stricter than IPTC without being arbitrary: it codifies the shape upstream's own samples already use. It nevertheless carries ONE profile finding: `sport:infractionType` has the value `vendpenalty:foul`, and no @context in the sample binds a `vendpenalty` prefix. That is a real defect in the upstream sample, not a harness artefact — the value resolves to nothing. It is left visible rather than allowlisted.
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 1280 triples.

**Layer 2 — official SHACL:** conforms, over 165 instance(s) of an official IPTC class.

**Layer 3 — Machina profile:** 1 finding(s).

- `controlled-vocabulary-undeclared-prefix` × 1
- context binds `sport:` to `https://sportschema.org/ontologies/main/`

**Layer 4 — controlled vocabulary:** 19 valid, 0 invalid, 1 unresolvable prefix, 9 unverifiable.

- UNRESOLVABLE `vendpenalty:foul` on `sport:infractionType` — Prefix is not bound by any @context in scope.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/sprecipienttype/player` — No vocabularies/sprecipienttype.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spsocaction/video-review` — No vocabularies/spsocaction.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spsocpenaltylevel/yellow-card` — No vocabularies/spsocpenaltylevel.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spsocrole/assist` — No vocabularies/spsocrole.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spsocrole/infraction-committed-by` — No vocabularies/spsocrole.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spsocrole/scorer` — No vocabularies/spsocrole.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spsocrole/sub-off` — No vocabularies/spsocrole.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spsocrole/sub-on` — No vocabularies/spsocrole.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spsocscore/regular` — No vocabularies/spsocscore.ttl exists at the pinned commit, so this code cannot be checked offline.

### `official-soccer-standings`

- **section:** conforming
- **document:** `agent-templates/iptc-mappings/references/iptc-sport-schema-1.1/samples/json-ld/soccer-standings.jsonld`
- **fixture class:** official-upstream-sample
- **provenance:** Byte-exact upstream samples/json-ld/soccer-standings.jsonld at the pinned commit.
- **role:** Core-statistics coverage in a document that conforms to the official SHACL shapes.
- **profile expectation:** Conforms to layers 1, 2 and 4 but carries 5 profile findings, all the same defect: `spstat:resultEffectTarget` values of the form `league:l.uefa.org.champions`, where no @context in the sample binds a `league` prefix. Same class of upstream sample defect as soccer-match-02. Recorded, not allowlisted: an unbound prefix in a value is broken whoever wrote it.
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 765 triples.

**Layer 2 — official SHACL:** conforms, over 82 instance(s) of an official IPTC class.

**Layer 3 — Machina profile:** 5 finding(s).

- `controlled-vocabulary-undeclared-prefix` × 5
- context binds `sport:` to `https://sportschema.org/ontologies/main/`

**Layer 4 — controlled vocabulary:** 7 valid, 0 invalid, 5 unresolvable prefix, 0 unverifiable.

- UNRESOLVABLE `league:l.uefa.org.cup` on `spstat:resultEffectTarget` — Prefix is not bound by any @context in scope.
- UNRESOLVABLE `league:l.uefa.org.champions` on `spstat:resultEffectTarget` — Prefix is not bound by any @context in scope.
- UNRESOLVABLE `league:l.uefa.org.champions` on `spstat:resultEffectTarget` — Prefix is not bound by any @context in scope.
- UNRESOLVABLE `league:l.uefa.org.champions` on `spstat:resultEffectTarget` — Prefix is not bound by any @context in scope.
- UNRESOLVABLE `league:l.uefa.org.champions` on `spstat:resultEffectTarget` — Prefix is not bound by any @context in scope.

### `official-team-roster`

- **section:** conforming
- **document:** `agent-templates/iptc-mappings/references/iptc-sport-schema-1.1/samples/json-ld/team-roster.jsonld`
- **fixture class:** official-upstream-sample
- **provenance:** Byte-exact upstream samples/json-ld/team-roster.jsonld at the pinned commit.
- **role:** Membership and Participation coverage in a known-conforming document.
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 637 triples.

**Layer 2 — official SHACL:** conforms, over 132 instance(s) of an official IPTC class.

**Layer 3 — Machina profile:** conforms.

**Layer 4 — controlled vocabulary:** 6 valid, 0 invalid, 0 unresolvable prefix, 3 unverifiable.

- UNVERIFIABLE `http://cv.iptc.org/newscodes/spphasestatus/active` — No vocabularies/spphasestatus.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spphasestatus/inactive` — No vocabularies/spphasestatus.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spphasestatus/injured` — No vocabularies/spphasestatus.ttl exists at the pinned commit, so this code cannot be checked offline.

### `corrected-api-football-soccer`

- **section:** corrected
- **document:** `tools/iptc/fixtures/corrected/api-football-soccer-graph.json`
- **fixture class:** corrected-serializer-output
- **derived from:** `agent-templates/iptc-mappings/example-apifootball.json`
- **provenance:** SANITIZED CHECKED-IN PROVIDER EXAMPLE. No API-Football endpoint was called and no credential exists in this repository. The source is the provider example already committed at agent-templates/iptc-mappings/example-apifootball.json, read verbatim and unmodified by this task.
- **RIGHTS:** Shape evidence, NOT an entitlement. A checked-in provider example proves what an API-Football payload looks like; it grants this repository no right to redistribute API-Football data. The observation behind this graph is `licensed-provider-example-fixture`, prototype_only true, commercial_use false, and tools.iptc.validate_graph.rights_findings on the envelope beside it returns `rights-prototype-only` for consumer_tier `production` — a test asserts that rather than leaving it as prose. The gate is also the command: `python3 tools/iptc/validate_graph.py --consumer-tier production tools/iptc/fixtures/corrected/api-football-soccer-envelope.json` reports the refusal and exits nonzero. Do not read this fixture, or the audit row it produces, as a commercial redistribution claim.
- **transformation:** Read by tools/iptc/canonical/adapters/api_football.py into the canonical observation checked in at tools/iptc/fixtures/observations/api-football-soccer-observation.json with observed_at 2026-03-01T22:05:00+00:00, then serialized by tools/iptc/canonical/serialize.py. Reproducible byte-for-byte from those two inputs; tests/test_iptc_api_football_adapter.py asserts it rather than trusting it.
- **emitted by:** tools/iptc/canonical/serialize.py sport_schema_graph, via canonical_envelope with surrogate_resolver('api-football'). The full envelope a consumer receives is checked in beside it at tools/iptc/fixtures/corrected/api-football-soccer-envelope.json; this file is the same graph standalone, because the harness validates JSON-LD documents rather than envelopes.
- **coverage:** API-Football soccer event, corrected. Capability tier `core`: the payload carries no clock period, no actions and no player statistics, so `live` and `advanced` are correctly not claimed.
- **role:** The first corrected output measured against the baseline set, and the first conformance evidence in this repository derived from a real provider shape rather than a hand-authored synthetic one. Expected to pass all four layers with all four gates at zero. The matching baseline row, `api-football-soccer-event`, is the same provider's current mapping output and fails layer 2 vacuously; the two rows read together are the before and after.
- **MISSING EVIDENCE:** The source is a checked-in EXAMPLE, not a captured production response, and it carries real club, competition and venue names copied verbatim from that already-committed example. So: (1) it is one finished fixture, which exercises no pre-match, in-play, drawn, extra-time or abandoned path — those are covered by adapter unit tests over locally-mutated copies of this payload, not by a checked-in provider document; (2) it is a single-sport, single-provider shape, so a green row here is evidence about API-Football's fixtures payload and about nothing else; (3) three real provider absences are visible in it and are deliberately NOT filled in — no competition type (league.standings is not a competition type), no event outcome type (null extratime is not a statement of `regular`) and no venue country (league.country is the competition's) — so the row understates what a richer payload could carry, which is the correct direction to be wrong in.
- **note:** Canonical identity here is a marked provider-scoped surrogate (`urn:machina:sports:<kind>:x<blake2b-128>`). The provider's own identifiers — fixture 1390823, league 140, venue 1474, teams 540 and 530, round `Regular Season - 1` and season 2025 — appear only as machina:ProviderIdentifier crosswalk evidence with an evidence pointer back to the observation field each came from. No `urn:apifootball:` identifier survives anywhere in the document.
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 90 triples.

**Layer 2 — official SHACL:** conforms, over 9 instance(s) of an official IPTC class.

**Layer 3 — Machina profile:** conforms.

**Layer 4 — controlled vocabulary:** 5 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


### `corrected-sportradar-mlb`

- **section:** corrected
- **document:** `tools/iptc/fixtures/corrected/sportradar-mlb-graph.json`
- **fixture class:** corrected-serializer-output
- **derived from:** `tools/iptc/fixtures/baseline/sportradar-mlb-event.json`
- **provenance:** SYNTHETIC, AND TWO REMOVES FROM PROVIDER DATA. No Sportradar endpoint was called, no credential exists in this repository and there is no network access in this harness. No Sportradar MLB sample of any kind is checked in — not a payload, not a captured response, not a sanitized example. The source is the OUTPUT SHAPE of Machina's own iptc-sportradar-event-mlb-mapping, hand-authored by PR 1 from that mapping's literal key set with synthetic `00000000-0000-4000-8000-0000000098xx/92xx` UUIDs and `Synthetic *` names throughout.
- **RIGHTS:** Legacy mapping-contract shape evidence, NOT an entitlement and NOT provider data. The observation is `legacy-mapping-contract-shape` — deliberately a different data class from the `licensed-provider-example-fixture` used by the API-Football and Sportradar SOCCER rows, because those read checked-in provider examples and this does not, and the audit has to be able to tell the two apart. It is prototype_only true, commercial_use false, and tools.iptc.validate_graph.rights_findings on the envelope beside it returns `rights-prototype-only` exactly once for consumer_tier `production`. The gate is also the command: `python3 tools/iptc/validate_graph.py --consumer-tier production tools/iptc/fixtures/corrected/sportradar-mlb-envelope.json` reports the refusal and exits nonzero. Tests assert both. Nothing here claims a right to redistribute Sportradar data, and nothing here is evidence about Sportradar's real MLB feed.
- **transformation:** Read by tools/iptc/canonical/adapters/sportradar_mlb.py into the canonical observation checked in at tools/iptc/fixtures/observations/sportradar-mlb-observation.json with observed_at 2026-03-01T22:05:00+00:00, then serialized by tools/iptc/canonical/serialize.py. Reproducible byte-for-byte from those two inputs; tests/test_iptc_sportradar_mlb_adapter.py asserts it rather than trusting it. THE SOURCE IS A LEGACY MAPPING-CONTRACT SHAPE, NOT RAW PROVIDER DATA: it is PR 1's frozen baseline row for iptc-sportradar-event-mlb-mapping, hand-authored from that mapping's literal key set, and it is read strictly read-only here. Unlike `corrected-sportradar-soccer`, which reads a checked-in provider example, NO Sportradar MLB payload of any kind exists in this repository. The source doubles as this row's own 'before' document, which is why no copy of it was checked in beside the corrected output — two copies of one payload is the drift this programme refuses elsewhere.
- **emitted by:** tools/iptc/canonical/serialize.py sport_schema_graph, via canonical_envelope with surrogate_resolver('sportradar-mlb'). The full envelope a consumer receives is checked in beside it at tools/iptc/fixtures/corrected/sportradar-mlb-envelope.json; this file is the same graph standalone, because the harness validates JSON-LD documents rather than envelopes.
- **coverage:** Sportradar MLB game, corrected. Baseball as its own sport — `medtop:20000849`, checked against the pinned mediatopic scheme — with two `sport:Team` competitors and their alignment. Capability tier `core`, and this is the ONLY corrected row that reports a capability violation: `score-absent-on-started-event`, because the source states `sport:homeScore: null` on a closed game and the honest output omits the scoreline rather than inventing a shutout. The doubleheader disambiguators the source carries have no canonical home and are not emitted; see the limitation.
- **role:** The sixth corrected output, the first baseball one, and the row that carries the set's most useful negative result: a corrected document can be fully conforming and still be missing a fact a consumer needs, and the capability report is what says so out loud. It is also the second row to state the mapping-constant competition identity problem, and the only one to record a named downstream field — the doubleheader disambiguator — as an unsolved loss. The matching baseline row, `sportradar-mlb-event`, is the same mapping's output and trips the provider-leak gate; the two rows read together are the before and after.
- **MISSING EVIDENCE:** The source is a legacy mapping output, not raw provider data, and it is synthetic. So: (1) a green row here is evidence that Machina's own Sportradar MLB mapping output can be read into a conforming canonical shape — it is NOT evidence about Sportradar's MLB payload, its coverage, its status vocabulary or its identifier stability, and it cannot be, because no Sportradar MLB sample is checked in; (2) the game, the ballpark and both teams are invented; (3) NO SCORE IS CARRIED, AND THAT IS A REPORTED GAP RATHER THAN A FIXED ONE. The mapping emits `sport:score` with explicit nulls on purpose — its own description says `schedule.json` carries no runs and `sportradar-mlb-sync-results` merges them in from the daily boxscore feed later — so the corrected output omits the scoreline and `capability_report` raises `score-absent-on-started-event` on a closed game. Emitting `"0"` would have invented a shutout and would have validated. A consumer that needs the score must read a document produced after the results merge; a test covers that path over a locally-mutated copy; (4) THE DOUBLEHEADER DISAMBIGUATORS ARE LOST. `sport:gameNumber` and `sport:doubleHeader` exist because MLB plays two games between the same teams on the same day, and the mapping's own comment says a naive team+date join would collapse the pair. Neither is an official term — `sport:doubleHeader` is a named provider leak in tools/iptc/rules/provider-leak-terms.json — and `EventShape` is `sh:closed` with nothing that could carry either, so both stay in `raw` only. This is a real loss against the baseline document and it is a named A16 handoff item, not a solved problem; (5) THE COMPETITION AND SEASON IDENTIFIERS ARE MAPPING CONSTANTS, NOT PROVIDER IDENTIFIERS. `urn:sportradar:competition:mlb` is a literal and `urn:sportradar:season:{season_year}` is a workflow variable with a hardcoded default; the schedule payload carries no competition entity and no season entity at all. The crosswalk entries `mlb` and `2026` are recorded because `observation.competition.provider_id` is a required field, and they are NOT evidence that Sportradar addresses either entity by that string. The event, venue and team identifiers are genuinely provider-native. The adapter names the two constants in `MAPPING_CONSTANT_IDENTIFIERS` and a test asserts the split; a real crosswalk must replace both; (6) `EVENT_STATUS_BY_CODE` holds six codes because this connector has TWO writers of `sport:status` — the event mapping, which rewrites `created`/`scheduled` to `not_started` and `inprogress` to `live`, and `sportradar-mlb-sync-results`, which merges `game.status` onto the same field with no rewrite at all. Both spellings are therefore mapped, which makes this table wider than the NFL adapter's; that asymmetry is deliberate, because the NFL connector rewrites on every write path it has. `complete`, `unnecessary` and `if-necessary` appear in no checked-in expression here and are absent rather than guessed; an unmapped, missing or null status raises naming the code; (7) it is one closed game, so no in-play, postponed or suspended path is exercised by the checked-in document, and no doubleheader pair is either.
- **note:** Canonical identity here is a marked provider-scoped surrogate (`urn:machina:sports:<kind>:x<blake2b-128>`). The identifiers are recovered from the legacy `urn:sportradar:<kind>:` wrapper per entity kind; recording the wrapper itself would attribute Machina's URN scheme to Sportradar. They appear only as machina:ProviderIdentifier crosswalk evidence with a pointer back to the observation field each came from, and no `urn:sportradar:` identifier survives anywhere in the document. The crosswalk namespace is `sportradar-mlb` rather than `sportradar`, and here that is load-bearing rather than tidy: the legacy MLB and NFL mappings both mint `urn:sportradar:sport_event:<id>`, `urn:sportradar:team:<id>` and `urn:sportradar:venue:<id>` with no sport in the stem, so their identifier spaces collide in the old model. Because surrogates are provider-scoped, one UUID under the two feeds mints two identifiers and nothing here claims they are the same entity — a test asserts that. Three provider-leak terms the baseline row is fixtured for are gone from the corrected output: `sport:matchStatus`, `sport:doubleHeader` and `sport:market`, all emitted under the official namespace by the mapping. All three survive in `raw` and none reaches `@graph`, and gate 4 moves from nonzero on the baseline document to zero here, which a test measures on both.
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 75 triples.

**Layer 2 — official SHACL:** conforms, over 8 instance(s) of an official IPTC class.

**Layer 3 — Machina profile:** conforms.

**Layer 4 — controlled vocabulary:** 3 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


### `corrected-sportradar-nfl`

- **section:** corrected
- **document:** `tools/iptc/fixtures/corrected/sportradar-nfl-graph.json`
- **fixture class:** corrected-serializer-output
- **derived from:** `tools/iptc/fixtures/baseline/sportradar-nfl-event.json`
- **provenance:** SYNTHETIC, AND TWO REMOVES FROM PROVIDER DATA. No Sportradar endpoint was called, no credential exists in this repository and there is no network access in this harness. No Sportradar NFL sample of any kind is checked in — not a payload, not a captured response, not a sanitized example. The source is the OUTPUT SHAPE of Machina's own iptc-sportradar-event-nfl-mapping, hand-authored by PR 1 from that mapping's literal key set with synthetic `00000000-0000-4000-8000-0000000098xx/91xx` UUIDs and `Synthetic *` names throughout.
- **RIGHTS:** Legacy mapping-contract shape evidence, NOT an entitlement and NOT provider data. The observation is `legacy-mapping-contract-shape` — deliberately a different data class from the `licensed-provider-example-fixture` used by the API-Football and Sportradar SOCCER rows, because those read checked-in provider examples and this does not, and the audit has to be able to tell the two apart. It is prototype_only true, commercial_use false, and tools.iptc.validate_graph.rights_findings on the envelope beside it returns `rights-prototype-only` exactly once for consumer_tier `production`. The gate is also the command: `python3 tools/iptc/validate_graph.py --consumer-tier production tools/iptc/fixtures/corrected/sportradar-nfl-envelope.json` reports the refusal and exits nonzero. Tests assert both. Nothing here claims a right to redistribute Sportradar data, and nothing here is evidence about Sportradar's real NFL feed.
- **transformation:** Read by tools/iptc/canonical/adapters/sportradar_nfl.py into the canonical observation checked in at tools/iptc/fixtures/observations/sportradar-nfl-observation.json with observed_at 2026-03-01T22:05:00+00:00, then serialized by tools/iptc/canonical/serialize.py. Reproducible byte-for-byte from those two inputs; tests/test_iptc_sportradar_nfl_adapter.py asserts it rather than trusting it. THE SOURCE IS A LEGACY MAPPING-CONTRACT SHAPE, NOT RAW PROVIDER DATA: it is PR 1's frozen baseline row for iptc-sportradar-event-nfl-mapping, hand-authored from that mapping's literal key set, and it is read strictly read-only here. Unlike `corrected-sportradar-soccer`, which reads a checked-in provider example, NO Sportradar NFL payload of any kind exists in this repository. The source doubles as this row's own 'before' document, which is why no copy of it was checked in beside the corrected output — two copies of one payload is the drift this programme refuses elsewhere.
- **emitted by:** tools/iptc/canonical/serialize.py sport_schema_graph, via canonical_envelope with surrogate_resolver('sportradar-nfl'). The full envelope a consumer receives is checked in beside it at tools/iptc/fixtures/corrected/sportradar-nfl-envelope.json; this file is the same graph standalone, because the harness validates JSON-LD documents rather than envelopes.
- **coverage:** Sportradar NFL game, corrected. American football as its own sport — `medtop:20000823`, checked against the pinned mediatopic scheme — with two `sport:Team` competitors, their alignment and a scoreline as strings. Capability tier `core`: no clock, no period reading, no timeline and no statistics, so `live` and `advanced` are correctly not claimed, and `event.result` is correctly ABSENT because the source states no winner. Together with `corrected-sportradar-tennis` this is the team-shaped counterpart to that row's individual participation, reached through the same serializer.
- **role:** The fifth corrected output, and the first American-football one. It pairs with `corrected-sportradar-tennis` to show one serializer reaching team participation and individual participation from two feeds of the same provider, and it is the row that carries the honest statement about mapping-constant competition identity — the weakest link in this repository's crosswalk evidence, stated rather than smoothed over. The matching baseline row, `sportradar-nfl-event`, is the same mapping's output; the two rows read together are the before and after.
- **MISSING EVIDENCE:** The source is a legacy mapping output, not raw provider data, and it is synthetic. So: (1) a green row here is evidence that Machina's own Sportradar NFL mapping output can be read into a conforming canonical shape — it is NOT evidence about Sportradar's NFL payload, its coverage, its status vocabulary or its identifier stability, and it cannot be, because no Sportradar NFL sample is checked in; (2) the game, the venue and both teams are invented; (3) THE COMPETITION AND SEASON IDENTIFIERS ARE MAPPING CONSTANTS, NOT PROVIDER IDENTIFIERS. The mapping hardcodes `urn:sportradar:competition:nfl` and `urn:sportradar:season:2025` — the schedule payload it consumes carries no competition entity and no season entity at all — so the crosswalk entries `nfl` and `2025` are recorded because `observation.competition.provider_id` is a required field, and they are NOT evidence that Sportradar addresses either entity by that string. The event, venue and team identifiers are genuinely provider-native (`f['id']`, `f['venue']['id']`, `f['home'|'away']['id']`). The adapter names the two constants in `MAPPING_CONSTANT_IDENTIFIERS` and a test asserts the split, so this is a stated weakness rather than a silent one; a real crosswalk must replace both; (4) `EVENT_STATUS_BY_CODE` holds exactly three codes — `not_started`, `live`, `closed` — because the mapping's own rewrites (`created`/`scheduled` to `not_started`, `inprogress` to `live`) and the checked-in shape's `closed` are the whole of this repository's evidence for the vocabulary. Sportradar's real game-status enum is wider (`complete`, `interrupted`, `halftime`, `time-tbd`, …); the rest is deliberately absent rather than guessed, and an unmapped or missing status raises naming the code; (5) it is one closed game, so no pre-match, in-play or postponed path is exercised by the checked-in document — those are covered by adapter unit tests over locally-mutated copies; (6) five absences stay absent — no winner (24-17 is a scoreline, and comparing two numbers is inference), no competition phase (the source never says regular season or post-season, so `spct:season-regular` would be a guess), no clock (`sport:score.sport:halfTime` is a score for one period, not a reading of how far into the game play had reached), no venue country and no attendance.
- **note:** Canonical identity here is a marked provider-scoped surrogate (`urn:machina:sports:<kind>:x<blake2b-128>`). The identifiers are recovered from the legacy `urn:sportradar:<kind>:` wrapper per entity kind; recording the wrapper itself would attribute Machina's URN scheme to Sportradar. They appear only as machina:ProviderIdentifier crosswalk evidence with a pointer back to the observation field each came from, and no `urn:sportradar:` identifier survives anywhere in the document. The crosswalk namespace is `sportradar-nfl` rather than `sportradar`, and here that is load-bearing rather than tidy: the legacy NFL and MLB mappings both mint `urn:sportradar:sport_event:<id>`, `urn:sportradar:team:<id>` and `urn:sportradar:venue:<id>` with no sport in the stem, so their identifier spaces collide in the old model. Two provider-leak defects the baseline row is fixtured for are gone from the corrected output: `sport:matchStatus` (a duplicate of `sport:status` under the official namespace) and `sport:score.sport:halfTime` (the raw Sportradar period object with its provider key names `period_type`, `home_points`, `away_points`, `sequence` inside an IPTC-namespaced property). Both survive in `raw` and neither reaches `@graph`.
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 77 triples.

**Layer 2 — official SHACL:** conforms, over 8 instance(s) of an official IPTC class.

**Layer 3 — Machina profile:** conforms.

**Layer 4 — controlled vocabulary:** 3 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


### `corrected-sportradar-soccer`

- **section:** corrected
- **document:** `tools/iptc/fixtures/corrected/sportradar-soccer-graph.json`
- **fixture class:** corrected-serializer-output
- **derived from:** `agent-templates/iptc-mappings/example-sportradar.json`
- **provenance:** SANITIZED CHECKED-IN PROVIDER EXAMPLE. No Sportradar endpoint was called and no credential exists in this repository. The source is the provider example already committed at agent-templates/iptc-mappings/example-sportradar.json, read verbatim and unmodified by this task.
- **RIGHTS:** Shape evidence, NOT an entitlement. A checked-in provider example proves what a Sportradar summary payload looks like; it grants this repository no right to redistribute Sportradar data. The observation behind this graph is `licensed-provider-example-fixture`, prototype_only true, commercial_use false, and tools.iptc.validate_graph.rights_findings on the envelope beside it returns `rights-prototype-only` exactly once for consumer_tier `production`. The gate is also the command: `python3 tools/iptc/validate_graph.py --consumer-tier production tools/iptc/fixtures/corrected/sportradar-soccer-envelope.json` reports the refusal and exits nonzero. Tests assert both. Do not read this fixture, or the audit row it produces, as a commercial redistribution claim.
- **transformation:** Read by tools/iptc/canonical/adapters/sportradar_soccer.py into the canonical observation checked in at tools/iptc/fixtures/observations/sportradar-soccer-observation.json with observed_at 2026-03-01T22:05:00+00:00, then serialized by tools/iptc/canonical/serialize.py. Reproducible byte-for-byte from those two inputs; tests/test_iptc_sportradar_soccer_adapter.py asserts it rather than trusting it. The source is the RAW provider summary payload (`sport_event` + `sport_event_status`), NOT this repository's own mapping output: the matching baseline row `sportradar-soccer-event` is the legacy output for the same match and is read by nothing here.
- **emitted by:** tools/iptc/canonical/serialize.py sport_schema_graph, via canonical_envelope with surrogate_resolver('sportradar-soccer'). The full envelope a consumer receives is checked in beside it at tools/iptc/fixtures/corrected/sportradar-soccer-envelope.json; this file is the same graph standalone, because the harness validates JSON-LD documents rather than envelopes.
- **coverage:** Sportradar soccer event, corrected. Capability tier `core`: the summary payload carries no clock, no period reading, no timeline and no player statistics, so `live` and `advanced` are correctly not claimed. It does carry attendance, a venue country and a stated winner, which the API-Football row does not.
- **role:** The second corrected output derived from a real provider shape, and the first that reads a RAW provider payload for a provider whose legacy mapping output is also in the baseline set. The matching baseline row, `sportradar-soccer-event`, is that legacy output for the same fixture; the two rows read together are the before and after for one match, one from the mapping and one from the provider.
- **MISSING EVIDENCE:** The source is a checked-in EXAMPLE, not a captured production response, and it carries real club, competition and venue names copied verbatim from that already-committed example. So: (1) it is one finished fixture, which exercises no pre-match, in-play, drawn, extra-time or abandoned path — those are covered by adapter unit tests over locally-mutated copies of this payload, not by a checked-in provider document; (2) it is a single-sport, single-endpoint shape, so a green row here is evidence about Sportradar's soccer summary payload and about nothing else; (3) NO TIMELINE IS COVERED. The plan expected this row to reach the `live` tier from `sportradar-soccer-timeline.json`, and it does not: that baseline fixture is a hand-authored mapping-contract shape for a DIFFERENT, synthetic match (sr:competitor:9001/9002), so joining it to this real fixture would fabricate a timeline for a real match. `sport:Action`, `spactionclass:` and the unpinned soccer action-type rule are exercised by the `corrected-stats-perform-opta-soccer` row instead; (4) four real provider absences are visible and deliberately NOT filled in — no competition phase (`sport_event_context.round` is `{"number": 1}`, an ordinal inside a season, and `stage` has no identifier), no competition type (`stage.type` describes the stage, not the competition), no clock (`period_scores` are scores per period, not a reading) and no outcome type — so the row understates what a richer payload could carry, which is the correct direction to be wrong in; (5) `sport_event_status.match_status` is deliberately unmapped and survives only in `raw`, so this row makes no claim about Sportradar's half-by-half status vocabulary.
- **note:** Canonical identity here is a marked provider-scoped surrogate (`urn:machina:sports:<kind>:x<blake2b-128>`). The provider's own identifiers — sport_event sr:sport_event:61623432, competition sr:competition:8, season sr:season:130805, venue sr:venue:1307 and competitors sr:competitor:2814 and sr:competitor:2836 — appear only as machina:ProviderIdentifier crosswalk evidence with an evidence pointer back to the observation field each came from. No `urn:sportradar:` identifier and no bare `sr:` token survives in any resource identifier. The crosswalk namespace is `sportradar-soccer` rather than `sportradar`: Sportradar publishes a separate feed per sport, and one namespace across feeds would claim their identifier spaces are one, which nothing here has checked.
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 80 triples.

**Layer 2 — official SHACL:** conforms, over 8 instance(s) of an official IPTC class.

**Layer 3 — Machina profile:** conforms.

**Layer 4 — controlled vocabulary:** 5 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


### `corrected-sportradar-tennis`

- **section:** corrected
- **document:** `tools/iptc/fixtures/corrected/sportradar-tennis-graph.json`
- **fixture class:** corrected-serializer-output
- **derived from:** `tools/iptc/fixtures/baseline/sportradar-tennis-event.json`
- **provenance:** SYNTHETIC, AND TWO REMOVES FROM PROVIDER DATA. No Sportradar endpoint was called, no credential exists in this repository and there is no network access in this harness. No Sportradar tennis sample of any kind is checked in — not a payload, not a captured response, not a sanitized example. The source is the OUTPUT SHAPE of Machina's own iptc-sportradar-tennis-event-mapping, hand-authored by PR 1 from that mapping's literal key set with invented `sr:*:9xxx` identifiers and `Synthetic *` names throughout.
- **RIGHTS:** Legacy mapping-contract shape evidence, NOT an entitlement and NOT provider data. The observation is `legacy-mapping-contract-shape` — deliberately a different data class from the `licensed-provider-example-fixture` used by the API-Football and Sportradar SOCCER rows, because those read checked-in provider examples and this does not, and the audit has to be able to tell the two apart. It is prototype_only true, commercial_use false, and tools.iptc.validate_graph.rights_findings on the envelope beside it returns `rights-prototype-only` exactly once for consumer_tier `production`. The gate is also the command: `python3 tools/iptc/validate_graph.py --consumer-tier production tools/iptc/fixtures/corrected/sportradar-tennis-envelope.json` reports the refusal and exits nonzero. Tests assert both. Nothing here claims a right to redistribute Sportradar data, and nothing here is evidence about Sportradar's real tennis feed.
- **transformation:** Read by tools/iptc/canonical/adapters/sportradar_tennis.py into the canonical observation checked in at tools/iptc/fixtures/observations/sportradar-tennis-observation.json with observed_at 2026-03-01T22:05:00+00:00, then serialized by tools/iptc/canonical/serialize.py. Reproducible byte-for-byte from those two inputs; tests/test_iptc_sportradar_tennis_adapter.py asserts it rather than trusting it. THE SOURCE IS A LEGACY MAPPING-CONTRACT SHAPE, NOT RAW PROVIDER DATA: it is PR 1's frozen baseline row for iptc-sportradar-tennis-event-mapping, hand-authored from that mapping's literal key set, and it is read strictly read-only here. Unlike `corrected-sportradar-soccer`, which reads a checked-in provider example, NO Sportradar tennis payload of any kind exists in this repository. The source doubles as this row's own 'before' document, which is why no copy of it was checked in beside the corrected output — two copies of one payload is the drift this programme refuses elsewhere.
- **emitted by:** tools/iptc/canonical/serialize.py sport_schema_graph, via canonical_envelope with surrogate_resolver('sportradar-tennis'). The full envelope a consumer receives is checked in beside it at tools/iptc/fixtures/corrected/sportradar-tennis-envelope.json; this file is the same graph standalone, because the harness validates JSON-LD documents rather than envelopes.
- **coverage:** Sportradar tennis singles match, corrected. THE FIRST CORRECTED ROW WITH INDIVIDUAL PARTICIPATION: two singles players are `sport:Athlete` and `sport:IndividualParticipation`, and no `sport:Team` or `sport:TeamParticipation` appears anywhere in the document. Also the first row on a sport other than association football — `medtop:20001085` (tennis), checked against the pinned mediatopic scheme. Capability tier `core`: no clock, no period reading and no timeline, so `live` is correctly not claimed, and no participant statistic is emitted, so `advanced` is not either. `event.lineups` is reported present, which is true — the event names individuals.
- **role:** The fourth corrected output, the first to exercise individual rather than team participation, and the first on a non-football sport. It is a second honest counter-example in the set alongside `corrected-stats-perform-opta-soccer`: reading the corrected section as N provider conformance results overstates it by the number of rows whose source is a mapping shape rather than a provider example. The matching baseline row, `sportradar-tennis-event`, is the same mapping's output and is the widest mapping in the repository by distinct `sport:` term count; the two rows read together are the before and after.
- **MISSING EVIDENCE:** The source is a legacy mapping output, not raw provider data, and it is synthetic. So: (1) a green row here is evidence that Machina's own Sportradar tennis mapping output can be read into a conforming canonical shape — it is NOT evidence about Sportradar's tennis payload, its coverage, its status vocabulary or its identifier stability, and it cannot be, because no Sportradar tennis sample is checked in; (2) the match, the tournament, the venue and both players are invented; (3) it is one finished three-set singles match, so no pre-match, in-play, retired, walkover or doubles path is exercised by the checked-in document — the pre-match, unstated-winner, null-score and unmapped-status paths are covered by adapter unit tests over locally-mutated copies; (4) NO TENNIS STATISTIC IS CARRIED. The source states seventeen per-player statistics and the corrected output emits none, because `sport:IndividualParticipationShape` is `sh:closed` and the pinned shapes declare no `sptenstat:` property on it — the terms are official at the pinned commit, but they are not admissible on this class, and a test measures that by injecting one and watching layer 2 reject it. Every statistic survives in `raw` and is readable in `event_view`, so this row understates what the source carries, which is the correct direction to be wrong in; (5) DOUBLES ARE NOT COVERED. `sport:competitionFormat.sport:matchType` is `singles`, and a doubles pairing is a multi-participant shape this task deliberately did not build; (6) five further absences stay absent — no competition phase (`sport:round` is a display name plus an ordinal and `sport:stage` carries no `@id`), no competition type (`sport:stage.sport:type` describes the stage; a match type, a gender category and a tour level are not `spct:` concepts), no clock (`sport:periodScores` are games per set, not a reading), no outcome type and no participant rank (a seed is a draw position, not `sport:rank`); (7) `sport:status` — the mapping's copy of Sportradar's `match_status` — is deliberately unmapped and survives only in `raw`, so this row makes no claim about that vocabulary. The status read is `sport:gameInfo.sport:status`, which carries `sport_event_status.status`.
- **note:** Canonical identity here is a marked provider-scoped surrogate (`urn:machina:sports:<kind>:x<blake2b-128>`). The six identifiers the source states — sport_event sr:sport_event:9000001, competition sr:competition:9001, season sr:season:9001, venue sr:venue:9001 and competitors sr:competitor:9101 and sr:competitor:9102 — are recovered from the legacy `urn:sportradar:tennis:<kind>:` wrapper per entity kind rather than by splitting on the last colon, because a Sportradar identifier contains colons and splitting would record `9000001` and throw away the kind. Recording the wrapper itself would attribute Machina's URN scheme to Sportradar. They appear only as machina:ProviderIdentifier crosswalk evidence with a pointer back to the observation field each came from; no `urn:sportradar:` identifier survives anywhere in the document, and neither does the source's invented `urn:iptc:sport:tennis` node, which is replaced by the pinned `medtop:20001085`. The crosswalk namespace is `sportradar-tennis` rather than `sportradar`: Sportradar publishes a separate feed per sport, and one namespace across feeds would claim their identifier spaces are one, which nothing here has checked. `sport:alignment` is recorded in the observation — it is what decides which score column belongs to which player — and never reaches the graph, because the pinned `sh:closed` IndividualParticipationShape declares it only for team participations.
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 77 triples.

**Layer 2 — official SHACL:** conforms, over 8 instance(s) of an official IPTC class.

**Layer 3 — Machina profile:** conforms.

**Layer 4 — controlled vocabulary:** 5 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


### `corrected-sports-skills-espn-soccer`

- **section:** corrected
- **document:** `tools/iptc/fixtures/corrected/sports-skills-espn-soccer-graph.json`
- **fixture class:** corrected-serializer-output
- **derived from:** `tools/iptc/fixtures/source/sports-skills-espn-soccer-native.json`
- **provenance:** SYNTHETIC. No ESPN endpoint was called, no sports-skills command was run, no credential exists in this repository and there is no network access in this harness. The source payload was hand-authored in the exact shape sports-skills' own `_normalize_espn_event` returns — its key set, key order and value types — with invented identifiers (9001/9011/9012/9101, `synthetic-league-1`) and `Synthetic *` names throughout.
- **RIGHTS:** TWO CLASSES, DELIBERATELY NOT ONE. The **runtime rights class** the envelope carries is `open-public`: it describes the data the sports-skills adapter emits, which is ESPN's public endpoints read live, and the published adapter stamps that one constant onto this fixture and onto every real match it will ever read. The **fixture evidence class** behind this audit row is `mapping-contract-synthetic`: the match, the teams, the venue and the competition are invented, so nothing here is provider data, no third party's rights are engaged and there is no redistribution claim to read into it. The runtime class was previously `mapping-contract-synthetic-open-prototype`, which answered the fixture question in the field that carries the runtime one — shipped downstream, that class travels out attached to real ESPN events and calls them synthetic, which is false about live data. Reclassifying it weakens nothing: rights stay prototype_only true, commercial_use false, because the sports-skills package is public, personal/non-commercial and can never emit anything else, and those two booleans are what the gate reads. tools.iptc.canonical.rights.rights_findings — re-exported as tools.iptc.validate_graph.rights_findings, and vendored into sports-skills so a consumer runs the same rule — returns `rights-prototype-only` exactly once on the envelope beside it for consumer_tier `production`, and the gate is also the command: `python3 tools/iptc/validate_graph.py --consumer-tier production tools/iptc/fixtures/corrected/sports-skills-espn-soccer-envelope.json` reports the refusal and exits nonzero. Tests assert both classes and both halves of the gate.
- **transformation:** REFERENCE CONTRACT, not an adapter in this repository. The native->canonical adapter for the `sports-skills/espn` open-data provider is owned by the `sports-skills` repository, which publishes it and vendors this repository's serializer byte-exact; a second adapter here would be a second source of truth for one provider reading. So the canonical observation that source payload must produce is checked in at tools/iptc/fixtures/observations/sports-skills-espn-soccer-observation.json with observed_at 2026-03-01T22:05:00+00:00, and this graph is serialized from THAT observation by tools/iptc/canonical/serialize.py. Reproducible byte-for-byte from the observation; tests/test_iptc_sports_skills_reference_contract.py asserts it rather than trusting it, and also asserts that no sports-skills adapter module exists here. The `sports-skills` PR reproduces the observation from the source fixture with its own adapter and the vendored runtime, and must match these bytes exactly.
- **emitted by:** tools/iptc/canonical/serialize.py sport_schema_graph, via canonical_envelope with surrogate_resolver('sports-skills/espn'). The full envelope a consumer receives is checked in beside it at tools/iptc/fixtures/corrected/sports-skills-espn-soccer-envelope.json; this file is the same graph standalone, because the harness validates JSON-LD documents rather than envelopes.
- **coverage:** sports-skills/espn open-data soccer event, corrected. Capability tier `core`: the normalized native payload carries no clock, no actions and no player statistics, so `live` and `advanced` are correctly not claimed. It also carries no winner flag, so no participant outcome is claimed either.
- **role:** The cross-repository reference contract, and the second corrected output. It is also the open-data counterpart to the licensed `corrected-api-football-soccer` row: the two together show one canonical shape reached from a licensed provider example and from an open-data provider's normalized output, which is what the cross-provider concept-equivalence test is built on.
- **MISSING EVIDENCE:** The match is INVENTED, so this row is evidence about the mapping contract and about nothing observed. Specifically: (1) it proves the shape sports-skills' normalized ESPN event can be read into, not that any real ESPN payload carries these values — a green row here is not a claim about ESPN's coverage, its status vocabulary or its identifier stability; (2) it is one finished, single-sport event, so no pre-match, in-play, halftime, drawn, abandoned or extra-time path is exercised; (3) the adapter that will produce this observation in production does not exist in this repository, so what is proved here is that the contract is satisfiable and self-consistent, not that the published adapter satisfies it — that is the `sports-skills` PR's gate, and until it lands this entry is a contract awaiting its implementation; (4) the native payload's own `status` value happens to coincide with the canonical key `closed`, which the sibling native values `live`, `1st_half` and `2nd_half` do not, so the adapter must map its status vocabulary explicitly and raise on an unmapped code rather than pass the string through.
- **note:** Four native placeholders are carried in the source payload on purpose — `matchday: null`, `round: ""`, `round_name: ""` and `odds: null` — because they are what sports-skills' normalizer actually emits, and the contract is that every one of them is dropped rather than forwarded. None reaches the observation outside `raw`, the graph or the view, and no `sport:CompetitionPhase` is invented from the empty round fields. `round_name` is a display string with no identifier the provider addresses, so recording it as provider-native evidence would be an invention; the API-Football adapter's `league.round` is different because that API takes that exact string as a round key. Canonical identity is a marked provider-scoped surrogate (`urn:machina:sports:<kind>:x<blake2b-128>`); the six invented provider identifiers appear only as machina:ProviderIdentifier crosswalk evidence with a pointer back to the observation field each came from.
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 77 triples.

**Layer 2 — official SHACL:** conforms, over 8 instance(s) of an official IPTC class.

**Layer 3 — Machina profile:** conforms.

**Layer 4 — controlled vocabulary:** 3 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


### `corrected-stats-perform-opta-soccer`

- **section:** corrected
- **document:** `tools/iptc/fixtures/corrected/stats-perform-opta-soccer-graph.json`
- **fixture class:** corrected-serializer-output
- **derived from:** `tools/iptc/fixtures/baseline/stats-perform-opta-event.json`
- **provenance:** SYNTHETIC, AND TWO REMOVES FROM PROVIDER DATA. No Stats Perform endpoint was called, no credential exists in this repository and there is no network access in this harness. No Stats Perform sample of any kind is checked in — not a payload, not a captured response, not a sanitized example. The source is the OUTPUT SHAPE of Machina's own iptc-opta-event-mapping, hand-authored by PR 1 from that mapping's literal key set with invented `synthetic0…` identifiers and `Synthetic *` names throughout.
- **RIGHTS:** Legacy mapping-contract shape evidence, NOT an entitlement and NOT provider data. The observation is `legacy-mapping-contract-shape` — deliberately a different data class from the `licensed-provider-example-fixture` used by the API-Football and Sportradar rows, because those read checked-in provider examples and this does not, and the audit has to be able to tell the two apart. It is prototype_only true, commercial_use false, and tools.iptc.validate_graph.rights_findings on the envelope beside it returns `rights-prototype-only` exactly once for consumer_tier `production`. The gate is also the command: `python3 tools/iptc/validate_graph.py --consumer-tier production tools/iptc/fixtures/corrected/stats-perform-opta-soccer-envelope.json` reports the refusal and exits nonzero. Tests assert both. Nothing here claims a right to redistribute Stats Perform data, and nothing here is evidence about Stats Perform's real feed.
- **transformation:** Read by tools/iptc/canonical/adapters/stats_perform_opta.py into the canonical observation checked in at tools/iptc/fixtures/observations/stats-perform-opta-soccer-observation.json with observed_at 2026-03-01T22:05:00+00:00, then serialized by tools/iptc/canonical/serialize.py. Reproducible byte-for-byte from those two inputs; tests/test_iptc_stats_perform_opta_adapter.py asserts it rather than trusting it. THE SOURCE IS A LEGACY MAPPING-CONTRACT SHAPE, NOT RAW PROVIDER DATA: it is PR 1's frozen baseline row for iptc-opta-event-mapping, hand-authored from that mapping's literal key set, and it is read strictly read-only here. The source doubles as this row's own 'before' document, which is why no copy of it was checked in beside the corrected output — two copies of one payload is the drift this programme refuses elsewhere.
- **emitted by:** tools/iptc/canonical/serialize.py sport_schema_graph, via canonical_envelope with surrogate_resolver('stats-perform-opta'). The full envelope a consumer receives is checked in beside it at tools/iptc/fixtures/corrected/stats-perform-opta-soccer-envelope.json; this file is the same graph standalone, because the harness validates JSON-LD documents rather than envelopes.
- **coverage:** Stats Perform / Opta soccer event with an embedded timeline, corrected. Capability tier `core`, and `core` is right despite the actions: `live` also requires a clock and a period reading, and the source states neither, so tiers do not skip. This is the only corrected row carrying `sport:Action`, `spactionclass:` and `sport:CompetitionPhase`, and the only one reaching `spct:league`.
- **role:** The third corrected output, and the one that exercises everything the other two cannot: a timeline, a pinned action class, a competition phase and a competition type. It is also the honest counter-example in the set — two corrected rows are derived from checked-in provider examples and this one is not, so reading the section as three provider conformance results would overstate it by one.
- **MISSING EVIDENCE:** The source is a legacy mapping output, not raw provider data, and it is synthetic. So: (1) a green row here is evidence that Machina's own Opta mapping output can be read into a conforming canonical shape — it is NOT evidence about Opta's payload, Opta's coverage, Opta's status vocabulary or Opta's identifier stability, and it cannot be, because no Opta sample is checked in; (2) the match, the competition, the venue, the teams and the players are invented; (3) it is one finished event, so no pre-match, in-play, drawn or abandoned path is exercised by the checked-in document — those are covered by adapter unit tests over locally-mutated copies; (4) `ACTION_CLASS_BY_TYPE` holds exactly two Opta action codes, `G` and `YC`, because those are the only two this repository's checked-in shapes carry. Opta's real event vocabulary is far wider; the rest is deliberately absent rather than guessed, and an unmapped type produces no `sport:Action` while keeping its place in `event_view`; (5) five real absences stay absent — no clock (numberOfPeriods and periodLength describe the format, not the reading), no outcome type (null penalties are not a statement of `regular`), no venue city or country (the source states coordinates, and a place name is not derivable from one), no end time, and no individual participants.
- **note:** RFC 001 §9.2 in practice. The source carries `sport:actionType` as `http://cv.iptc.org/newscodes/spsocaction/g`, a NewsCode from a scheme with no vocabulary TTL at the pinned commit; layer 4 reports such values `unverifiable` and fails closed on them. The corrected output emits the action's CLASS as pinned `spactionclass:score` and never forwards the type: Opta's own `G` survives as `action.provider_type` in `event_view` and in `raw`, and no `spsocaction` token appears anywhere in `@graph`. The timeline also names a scorer, who is deliberately NOT promoted to a match participant — one named player would make the capability report claim `event.lineups`. Canonical identity is a marked provider-scoped surrogate (`urn:machina:sports:<kind>:x<blake2b-128>`); the seven provider identifiers are recovered from the legacy `urn:opta:<kind>:<id>` wrapper (recording the wrapper would attribute Machina's URN scheme to Stats Perform) and appear only as machina:ProviderIdentifier crosswalk evidence. No `urn:opta:` identifier survives anywhere in the document.
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 101 triples.

**Layer 2 — official SHACL:** conforms, over 10 instance(s) of an official IPTC class.

**Layer 3 — Machina profile:** conforms.

**Layer 4 — controlled vocabulary:** 7 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


### `negative-duplicate-ids`

- **section:** negative
- **document:** `tools/iptc/fixtures/negative/duplicate-ids.json`
- **construction:** Two sport:Team nodes sharing one @id.
- **asserts:** counter 3 > 0 and profile finding duplicate-node-id
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 89 triples.

**Layer 2 — official SHACL:** 2 violation(s).

- `ClassConstraintComponent` on `urn:machina:sports:participation:0000000000000000000000000011` path `https://sportschema.org/ontologies/main/participationBy` — Value does not have class sport:Team
- `OrConstraintComponent` on `urn:machina:sports:participation:0000000000000000000000000011` path `https://sportschema.org/ontologies/main/participationBy` — Node <urn:machina:sports:team:0000000000000000000000000006> must conform to one or more shapes in [ sh:class sport:Agent ] , [ sh:class sport:Individual ] , [ sh:class sport:Associate ] , [ sh:class sport:Athlete ] , [ sh:class sport:Official ]

**Layer 3 — Machina profile:** 1 finding(s).

- `duplicate-node-id` × 1
- context binds `sport:` to `https://sportschema.org/ontologies/main/`

**Layer 4 — controlled vocabulary:** 10 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


**Duplicate resource IDs:**

- `urn:machina:sports:team:0000000000000000000000000005` × 2

### `negative-invalid-newscode`

- **section:** negative
- **document:** `tools/iptc/fixtures/negative/invalid-newscode.json`
- **construction:** sport:playerStatus points at spplayerstatus/definitely-not-a-status, which the pinned vocabularies/spplayerstatus.ttl does not contain.
- **asserts:** counter 2 > 0 and layer 4 invalid
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 90 triples.

**Layer 2 — official SHACL:** 3 violation(s).

- `ClassConstraintComponent` on `urn:machina:sports:participation:0000000000000000000000000012` path `https://sportschema.org/ontologies/main/playerStatus` — Value does not have class skos:Concept
- `HasValueConstraintComponent` on `http://cv.iptc.org/newscodes/spplayerstatus/definitely-not-a-status` path `http://www.w3.org/2004/02/skos/core#inScheme` — Node <http://cv.iptc.org/newscodes/spplayerstatus/definitely-not-a-status>->skos:inScheme does not contain a value in the set: ['<http://cv.iptc.org/newscodes/spplayerstatus/>']
- `NodeConstraintComponent` on `urn:machina:sports:participation:0000000000000000000000000012` path `https://sportschema.org/ontologies/main/playerStatus` — Value does not conform to Shape sport:NewsCodesSportPlayerStatusShape. See details for more information.

**Layer 3 — Machina profile:** conforms.

**Layer 4 — controlled vocabulary:** 9 valid, 1 invalid, 0 unresolvable prefix, 0 unverifiable.

- INVALID `http://cv.iptc.org/newscodes/spplayerstatus/definitely-not-a-status` — Not a skos:Concept in http://cv.iptc.org/newscodes/spplayerstatus/.

### `negative-invented-sport-term`

- **section:** negative
- **document:** `tools/iptc/fixtures/negative/invented-sport-term.json`
- **construction:** The conforming minimal fixture with exactly one added property, sport:machinaConfidenceScore.
- **asserts:** counter 1 > 0 and profile finding invented-sport-term
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 91 triples.

**Layer 2 — official SHACL:** 1 violation(s).

- `ClosedConstraintComponent` on `urn:machina:sports:event:0000000000000000000000000009` path `https://sportschema.org/ontologies/main/machinaConfidenceScore` — Node <urn:machina:sports:event:0000000000000000000000000009> is closed. It cannot have value: Literal("0.82")

**Layer 3 — Machina profile:** 1 finding(s).

- `invented-sport-term` × 1
- context binds `sport:` to `https://sportschema.org/ontologies/main/`

**Layer 4 — controlled vocabulary:** 10 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


**Unknown `sport:` terms — 1 occurrence(s) of 1 distinct term(s):**

`sport:machinaConfidenceScore`×1

### `negative-malformed`

- **section:** negative
- **document:** `tools/iptc/fixtures/negative/malformed.jsonld`
- **construction:** A trailing comma and an unquoted key.
- **asserts:** layer 1 fails at the json stage and every later layer is skipped, with null counters rather than zero counters
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** FAIL at the `json` stage — `JSONDecodeError: Expecting property name enclosed in double quotes: line 5 column 7 (char 163)`. Layers 2-4 were not run and the four counters are `null`, not `0`.

**Layer 2 — official SHACL:** not run: the document is not valid JSON.

**Layer 3 — Machina profile:** not run: the document is not valid JSON.

**Layer 4 — controlled vocabulary:** not run: the document is not valid JSON.

### `negative-null-and-placeholder`

- **section:** negative
- **document:** `tools/iptc/fixtures/negative/null-and-placeholder.json`
- **construction:** The conforming minimal fixture with one null-valued property and one 'Unknown' string. Nothing here is an invented term, an invalid code, a duplicate id or a provider leak, which is the point: it isolates the omission rule from the four gates.
- **asserts:** profile findings null-value and placeholder-value; counters 1-4 all zero
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 90 triples.

**Layer 2 — official SHACL:** conforms, over 13 instance(s) of an official IPTC class.

**Layer 3 — Machina profile:** 2 finding(s).

- `null-value` × 1
- `placeholder-value` × 1
- context binds `sport:` to `https://sportschema.org/ontologies/main/`

**Layer 4 — controlled vocabulary:** 10 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


### `negative-provider-leakage`

- **section:** negative
- **document:** `tools/iptc/fixtures/negative/provider-leakage.json`
- **construction:** sport:doubleHeader and sport:matchStatus emitted under the official namespace; both appear in rules/provider-leak-terms.json.
- **asserts:** counter 4 > 0 and profile finding provider-property-in-iptc-namespace
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 92 triples.

**Layer 2 — official SHACL:** 2 violation(s).

- `ClosedConstraintComponent` on `urn:machina:sports:event:0000000000000000000000000009` path `https://sportschema.org/ontologies/main/matchStatus` — Node <urn:machina:sports:event:0000000000000000000000000009> is closed. It cannot have value: Literal("ended")
- `ClosedConstraintComponent` on `urn:machina:sports:event:0000000000000000000000000009` path `https://sportschema.org/ontologies/main/doubleHeader` — Node <urn:machina:sports:event:0000000000000000000000000009> is closed. It cannot have value: Literal("false")

**Layer 3 — Machina profile:** 4 finding(s).

- `invented-sport-term` × 2
- `provider-property-in-iptc-namespace` × 2
- context binds `sport:` to `https://sportschema.org/ontologies/main/`

**Layer 4 — controlled vocabulary:** 10 valid, 0 invalid, 0 unresolvable prefix, 0 unverifiable.


**Unknown `sport:` terms — 2 occurrence(s) of 2 distinct term(s):**

`sport:doubleHeader`×1, `sport:matchStatus`×1

**Provider properties in the IPTC namespace:**

- sportradar-mlb: `sport:doubleHeader`, `sport:matchStatus`
- sportradar-nfl: `sport:matchStatus`
- sportradar-soccer: `sport:matchStatus`

### `negative-remote-context`

- **section:** negative
- **document:** `tools/iptc/fixtures/negative/remote-context.json`
- **construction:** A minimal @graph document whose @context is a URL on the reserved .invalid TLD. Nothing resolves it, and nothing is meant to: the point is that the harness rejects it before the RDF parser is handed the bytes.
- **asserts:** layer 1 fails at the `context` stage and layers 2-4 are not run: a string @context would be dereferenced by IRI, which the offline harness refuses.
- **role:** Proves the offline guarantee is enforced rather than assumed.
- **known consumer dependencies:** none recorded. For a negative control, a positive control or a corrected serializer output that is correct — nothing in production reads them yet; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** FAIL at the `context` stage — `1 off-document JSON-LD context reference(s): remote-context at /@context. The harness is offline by construction and will not dereference a context; the profile requires one inline document-level context.`. Layers 2-4 were not run and the four counters are `null`, not `0`.
- BLOCKED `remote-context` at `/@context` → `https://example.invalid/iptc-sport-schema-1.1.context.jsonld`. Rejected before the RDF parser ran; no request was made.

**Layer 2 — official SHACL:** not run: the document references a JSON-LD context the offline harness will not load.

**Layer 3 — Machina profile:** not run: the document references a JSON-LD context the offline harness will not load.

**Layer 4 — controlled vocabulary:** not run: the document references a JSON-LD context the offline harness will not load.

## Coverage and what is missing

| Required coverage | Fixture | Evidence class |
|---|---|---|
| API-Football soccer event | `api-football-soccer-event` | repository-artifact |
| API-Football soccer event, null-bearing | `api-football-soccer-event-nulls` | repository-artifact |
| API-Football actions | `api-football-actions` | mapping-contract-synthetic |
| API-Football team statistics | `api-football-team-stats` | mapping-contract-synthetic |
| API-Football player statistics | `api-football-player-stats` | mapping-contract-synthetic |
| Sportradar soccer event | `sportradar-soccer-event` | repository-artifact |
| Sportradar soccer timeline | `sportradar-soccer-timeline` | mapping-contract-synthetic |
| Stats Perform / Opta event | `stats-perform-opta-event` | mapping-contract-synthetic |
| Stats Perform / Opta timeline | `stats-perform-opta-timeline` | mapping-contract-synthetic |
| Sportradar tennis | `sportradar-tennis-event` | mapping-contract-synthetic |
| Sportradar NFL | `sportradar-nfl-event` | mapping-contract-synthetic |
| Sportradar MLB | `sportradar-mlb-event` | mapping-contract-synthetic |
| American football | `american-football-event` | mapping-contract-synthetic |
| Generic custom event | `custom-event` | repository-artifact |

**10 of 14 baseline fixtures are `mapping-contract-synthetic`**, because no checked-in sample of those mappings' output exists and this work may not call a licensed provider to get one. Those fixtures faithfully reproduce the SHAPE each mapping emits — the key set, the nesting, the context — but their values are synthetic. Read their rows as statements about the mapping contract, not as production volumes: `api-football-actions`, `api-football-team-stats`, `api-football-player-stats`, `sportradar-soccer-timeline`, `stats-perform-opta-event`, `stats-perform-opta-timeline`, `sportradar-tennis-event`, `sportradar-nfl-event`, `sportradar-mlb-event`, `american-football-event`.

**The same rule governs the 7 `corrected-serializer-output` fixtures, and it is worth stating twice because a passing row invites the stronger reading.** Each one is derived from checked-in source evidence — a sanitized provider example or a mapping-contract-synthetic payload — and NO licensed provider was called and no credential was used to produce any of them. A checked-in example is evidence of a payload's *shape*; it is not an entitlement, and none of these fixtures is a claim that this repository may commercially redistribute the provider's data. Every observation behind them is marked `prototype_only` with `commercial_use: false`, which `rights_findings(envelope, consumer_tier="production")` refuses. Per-fixture source, rights and limitations: `corrected-api-football-soccer`, `corrected-sports-skills-espn-soccer`, `corrected-sportradar-soccer`, `corrected-stats-perform-opta-soccer`, `corrected-sportradar-tennis`, `corrected-sportradar-nfl`, `corrected-sportradar-mlb`.

### Missing evidence, stated rather than papered over

1. **No `spsocaction` vocabulary exists upstream at the pinned commit.** `tools/prefixes.ttl` binds the prefix and the SHACL shapes reference the scheme, but there is no `vocabularies/spsocaction.ttl`. Soccer action-type codes therefore cannot be validated offline and are reported as `unverifiable`. The same applies to `spsocrole`, `spesaction` and the other per-sport action/result schemes. `unverifiable` is reported as its own category and never promoted to `valid`, and it **fails** layer 4 — the profile's requirement is provable membership in a pinned vocabulary, so a value nothing can check does not pass.
2. **No baseline fixture is a captured production document.** The four verbatim fixtures are checked-in *examples*, which are themselves already drifted from what the mappings now emit (`custom-event` and `api-football-soccer-event` use `urn:apifootball:fixture:` while the mapping now emits `urn:apifootball:sport_event:`). Treat them as representative shapes, not as a snapshot of live output.
3. **The provider-leak attribution table is reviewed, not inferred.** Nothing in the term `sport:doubleHeader` marks it as a Sportradar MLB field; that attribution lives in `tools/iptc/rules/provider-leak-terms.json` and is only as complete as the inventory behind it. Terms that are invented but not provider-branded are counted by gate 1 alone.
4. **`worldcup-iptc-event-to-api-response` is a consumer, not an emitter, and is therefore not fixtured here.** It reads `sport:competition`, `schema:startDate`, `sport:status`, `sport:competitors` and `sport:venue` off whichever provider document it is given. Its response envelope is unchanged by this PR and is migrated with the other consumers.

## Reproducing this report

```bash
python3 -m pip install -r requirements-iptc-validator.txt
python3 -m tools.iptc --verify-pin   # vendored bytes vs upstream-commit.json
python3 -m tools.iptc                # regenerate both reports
python3 -m tools.iptc --check        # fail if the checked-in reports are stale
python3 tests/test_iptc_validation_harness.py -v
```

`--check` is what CI runs. CI stays green while the baseline fails conformance, because what is asserted is that the recorded failure report is still exactly reproducible — not that legacy output passes.
