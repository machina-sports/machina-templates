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

**Layer 3 — Machina profile:** 36 finding(s).

- `invented-sport-term` × 14
- `nested-resource` × 5
- `no-graph-envelope` × 1
- `placeholder-value` × 2
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

**Layer 3 — Machina profile:** 24 finding(s).

- `datetime-datatype` × 2
- `invented-sport-term` × 7
- `nested-resource` × 10
- `newscode-not-a-node` × 2
- `no-graph-envelope` × 1
- `placeholder-value` × 2
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

**Layer 3 — Machina profile:** 51 finding(s).

- `invented-sport-term` × 12
- `nested-resource` × 2
- `newscode-not-a-node` × 2
- `no-graph-envelope` × 1
- `placeholder-value` × 4
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

**Layer 3 — Machina profile:** 31 finding(s).

- `invented-sport-term` × 13
- `nested-resource` × 5
- `no-graph-envelope` × 1
- `null-value` × 2
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

**Layer 3 — Machina profile:** 14 finding(s).

- `nested-resource` × 4
- `no-graph-envelope` × 1
- `placeholder-value` × 2
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
- **known consumer dependencies:** none recorded. For a negative or positive control that is correct; for a baseline mapping it would be an inventory defect.

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
- **known consumer dependencies:** none recorded. For a negative or positive control that is correct; for a baseline mapping it would be an inventory defect.

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
- **known consumer dependencies:** none recorded. For a negative or positive control that is correct; for a baseline mapping it would be an inventory defect.

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
- **known consumer dependencies:** none recorded. For a negative or positive control that is correct; for a baseline mapping it would be an inventory defect.

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
- **known consumer dependencies:** none recorded. For a negative or positive control that is correct; for a baseline mapping it would be an inventory defect.

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
- **known consumer dependencies:** none recorded. For a negative or positive control that is correct; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** pass, 637 triples.

**Layer 2 — official SHACL:** conforms, over 132 instance(s) of an official IPTC class.

**Layer 3 — Machina profile:** conforms.

**Layer 4 — controlled vocabulary:** 6 valid, 0 invalid, 0 unresolvable prefix, 3 unverifiable.

- UNVERIFIABLE `http://cv.iptc.org/newscodes/spphasestatus/active` — No vocabularies/spphasestatus.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spphasestatus/inactive` — No vocabularies/spphasestatus.ttl exists at the pinned commit, so this code cannot be checked offline.
- UNVERIFIABLE `http://cv.iptc.org/newscodes/spphasestatus/injured` — No vocabularies/spphasestatus.ttl exists at the pinned commit, so this code cannot be checked offline.

### `negative-duplicate-ids`

- **section:** negative
- **document:** `tools/iptc/fixtures/negative/duplicate-ids.json`
- **construction:** Two sport:Team nodes sharing one @id.
- **asserts:** counter 3 > 0 and profile finding duplicate-node-id
- **known consumer dependencies:** none recorded. For a negative or positive control that is correct; for a baseline mapping it would be an inventory defect.

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
- **known consumer dependencies:** none recorded. For a negative or positive control that is correct; for a baseline mapping it would be an inventory defect.

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
- **known consumer dependencies:** none recorded. For a negative or positive control that is correct; for a baseline mapping it would be an inventory defect.

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
- **known consumer dependencies:** none recorded. For a negative or positive control that is correct; for a baseline mapping it would be an inventory defect.

**Layer 1 — JSON-LD parse:** FAIL at the `json` stage — `JSONDecodeError: Expecting property name enclosed in double quotes: line 5 column 7 (char 163)`. Layers 2-4 were not run and the four counters are `null`, not `0`.

**Layer 2 — official SHACL:** not run: the document is not valid JSON.

**Layer 3 — Machina profile:** not run: the document is not valid JSON.

**Layer 4 — controlled vocabulary:** not run: the document is not valid JSON.

### `negative-null-and-placeholder`

- **section:** negative
- **document:** `tools/iptc/fixtures/negative/null-and-placeholder.json`
- **construction:** The conforming minimal fixture with one null-valued property and one 'Unknown' string. Nothing here is an invented term, an invalid code, a duplicate id or a provider leak, which is the point: it isolates the omission rule from the four gates.
- **asserts:** profile findings null-value and placeholder-value; counters 1-4 all zero
- **known consumer dependencies:** none recorded. For a negative or positive control that is correct; for a baseline mapping it would be an inventory defect.

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
- **known consumer dependencies:** none recorded. For a negative or positive control that is correct; for a baseline mapping it would be an inventory defect.

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
- **known consumer dependencies:** none recorded. For a negative or positive control that is correct; for a baseline mapping it would be an inventory defect.

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
