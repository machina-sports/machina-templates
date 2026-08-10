# IPTC emitter, term and consumer inventory

<!-- GENERATED FILE. Do not edit by hand. -->
<!-- Regenerate with: python3 -m tools.iptc -->

Every IPTC-emitting mapping and every consumer of an IPTC output, with each term classified against the pinned IPTC Sport Schema 1.1 at commit `0e77bf8678f3702fe81c28673bede35efe47d633`.

This is generated, not hand-written. The "zero known legacy consumer breakages" claim of the later consumer migration is scoped to this list, so it has to be re-runnable rather than a snapshot of what someone noticed once.

## Scope boundary — read before using this inventory

The Machina canonical domain model remains authoritative. IPTC Sport Schema is an output projection generated from it — never the storage model and never Machina identity.

**This PR does:**

- Pins and vendors the official IPTC Sport Schema 1.1 artefacts with attribution and per-file hashes.
- Adds one shared JSON-LD context copied from the pinned prefixes.
- Adds the Machina IPTC profile RFC.
- Adds the offline four-layer validation harness, its fixtures and CI.
- Records this inventory and the exact baseline failure audit.

**This PR does NOT do:**

- No serializer is implemented. sport_schema_graph is not produced by any corrected serializer yet.
- No canonical identity work. Opaque identifiers and provider-identifier persistence remain unimplemented; the profile only states the policy.
- No API or MCP contract change, and no response envelope change.
- No event_view production output.
- No consumer migration. Every consumer listed below still reads the legacy shape, unchanged.
- No mapping YAML, output shape, selector or consumer field path is modified.

> This PR is foundation-only and output-neutral. It makes conformance measurable; it does not make anything conformant. Anyone reading the inventory as a statement that the projection now exists is reading it wrong.

## Headline

- **25** emitting mappings across **16** files.
- **75** files read an IPTC field path or payload key.

### Two conflicting `sport:` namespaces are in use today

| `sport:` bound to | Emitting mappings | Official? |
|---|---|---|
| _not declared in the mapping_ | 1 | no |
| `https://sportschema.org/ontologies/main/` | 16 | **yes** |
| `https://www.sportschema.org/ontologies/sport#` | 8 | no |

This is the defect that makes a SHACL pass vacuous. A mapping whose `sport:` prefix is not the official IRI emits no instance of any IPTC class, so every shape target matches nothing and a validator reports success over an empty set. See `docs/iptc/BASELINE-AUDIT.md`.

**Read the term table with this in mind.** 10 distinct term(s) (30 occurrence(s)) are classified `official-local-name-wrong-namespace`: the local name — `sport:Event` and friends — *is* declared by IPTC 1.1, but the emitting mapping does not bind `sport:` to the official IRI, so the emitted term is **not** the official term. They are deliberately not counted as `official-iptc-class` or `official-iptc-property`.

## Term classification

| Category | Distinct terms | Occurrences |
|---|---|---|
| `invented-sport-term` | 192 | 350 |
| `invented-statistic-term` | 24 | 28 |
| `jsonld-keyword` | 3 | 69 |
| `machina-operational-field` | 49 | 119 |
| `official-iptc-class` | 7 | 46 |
| `official-iptc-property` | 16 | 48 |
| `official-local-name-wrong-namespace` | 10 | 30 |
| `official-sport-specific-statistic` | 24 | 64 |
| `schema-org-term-unverified` | 19 | 50 |
| `standard-rdf-term` | 1 | 4 |

- **`invented-sport-term`** — Uses the official sport: prefix but is NOT declared by IPTC Sport Schema 1.1. Gate 1. Must move to machina: or event_view in PR 2.
- **`invented-statistic-term`** — Uses an official statistics prefix but is not declared by the corresponding pinned ontology. Gate 1.
- **`jsonld-keyword`** — A JSON-LD keyword. Not a vocabulary term.
- **`machina-operational-field`** — An unprefixed key. Neither a JSON-LD keyword nor a term defined by any @context in scope, so JSON-LD expansion drops it silently and the value is lost. Belongs under machina: or in event_view.
- **`official-iptc-class`** — Declared as a class by the pinned IPTC Sport Schema 1.1 ontology, AND the emitting mapping binds sport: to the official IRI, so it really is that class.
- **`official-iptc-property`** — Declared as a property by the pinned IPTC Sport Schema 1.1 ontology, AND the emitting mapping binds sport: to the official IRI.
- **`official-local-name-wrong-namespace`** — The local name IS declared by IPTC Sport Schema 1.1, but the emitting mapping does not bind sport: to https://sportschema.org/ontologies/main/ — so the term expands into a namespace nobody owns and is NOT the official term. This is the defect that makes a SHACL pass vacuous. Counting these as official would be the most flattering possible misreading of the baseline.
- **`official-sport-specific-statistic`** — Declared by a pinned per-sport or core statistics ontology.
- **`schema-org-term-unverified`** — A schema.org term. NOT VERIFIED: no schema.org vocabulary is pinned in this repository, so offline validation of schema.org terms is not possible. Listed rather than asserted valid.
- **`standard-rdf-term`** — An RDF, RDFS, XSD or SKOS term.

## Emitters

### `iptc-custom-event-mapping`

- **file:** `agent-templates/iptc-mappings/any-source/custom-event-mapping.yml`
- **`sport:` bound to:** `https://www.sportschema.org/ontologies/sport#`  ❌ not official
- **distinct emitted terms:** 32
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://www.sportschema.org/ontologies/sport#`
- **invented-sport-term** (12): `sport:Season`, `sport:Venue`, `sport:awayScore`, `sport:competition`, `sport:competitors`, `sport:halfTime`, `sport:homeScore`, `sport:qualifier`, `sport:season`, `sport:status`, `sport:venue`, `sport:year`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (10): `away`, `canceled`, `finished`, `home`, `name`, `not_started`, `postponed`, `schema`, `sport`, `urn:custom:venue:unknown`
- **official-local-name-wrong-namespace** (4): `sport:Competition`, `sport:Event`, `sport:Team`, `sport:score`
- **schema-org-term-unverified** (3): `schema:SportsEvent`, `schema:addressLocality`, `schema:startDate`
- **provider field names in the IPTC namespace:** `sport:halfTime`

### `iptc-api-football-event-mapping`

- **file:** `agent-templates/iptc-mappings/api-football/event-mapping.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 26
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://sportschema.org/ontologies/main/`
- **invented-sport-term** (12): `sport:Season`, `sport:Venue`, `sport:awayScore`, `sport:competition`, `sport:competitors`, `sport:halfTime`, `sport:homeScore`, `sport:qualifier`, `sport:season`, `sport:status`, `sport:venue`, `sport:year`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (3): `name`, `schema`, `sport`
- **official-iptc-class** (3): `sport:Competition`, `sport:Event`, `sport:Team`
- **official-iptc-property** (1): `sport:score`
- **schema-org-term-unverified** (4): `schema:SportsEvent`, `schema:addressLocality`, `schema:logo`, `schema:startDate`
- **provider field names in the IPTC namespace:** `sport:halfTime`

### `iptc-api-football-events-mapping`

- **file:** `agent-templates/iptc-mappings/api-football/event-mapping.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 16
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://sportschema.org/ontologies/main/`
- **invented-sport-term** (1): `sport:label`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (1): `sport`
- **official-iptc-class** (5): `sport:Action`, `sport:Athlete`, `sport:IndividualParticipation`, `sport:Team`, `sport:TeamParticipation`
- **official-iptc-property** (6): `sport:actionDateTime`, `sport:actionType`, `sport:comment`, `sport:minutesElapsed`, `sport:participation`, `sport:participationBy`

### `iptc-api-football-event-players-stats`

- **file:** `agent-templates/iptc-mappings/api-football/event-players-stats.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 47
- **declared prefixes:** `sport` → `https://sportschema.org/ontologies/main/`, `spsocstat` → `https://sportschema.org/ontologies/soccer/`, `spstat` → `https://sportschema.org/ontologies/corestatistics/`
- **invented-sport-term** (6): `sport:captain`, `sport:jerseyNumber`, `sport:minutesPlayed`, `sport:position`, `sport:rating`, `sport:substitute`
- **invented-statistic-term** (5): `spsocstat:dribblesAttempted`, `spsocstat:dribblesSuccessful`, `spsocstat:duelsTotal`, `spsocstat:duelsWon`, `spsocstat:passesKey`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (8): `document_type`, `event_code`, `metadata`, `player_code`, `sport`, `spsocstat`, `spstat`, `team_code`
- **official-iptc-class** (2): `sport:Athlete`, `sport:IndividualParticipation`
- **official-iptc-property** (2): `sport:participationBy`, `sport:playerStatus`
- **official-sport-specific-statistic** (17): `spsocstat:assistsTotal`, `spsocstat:cautionsTotal`, `spsocstat:ejectionsTotal`, `spsocstat:foulsCommited`, `spsocstat:foulsSuffered`, `spsocstat:goalsAgainstTotal`, `spsocstat:goalsTotal`, `spsocstat:interceptions`, `spsocstat:offsides`, `spsocstat:passesComplete`, `spsocstat:passesCompletePercentage`, `spsocstat:passesTotal`, `spsocstat:saves`, `spsocstat:shotsBlocked`, `spsocstat:shotsOnGoalTotal`, `spsocstat:shotsTotal`, `spsocstat:tacklesTotal`
- **schema-org-term-unverified** (3): `schema:image`, `schema:teamLogo`, `schema:teamName`
- **standard-rdf-term** (1): `rdfs:label`
- **provider field names in the IPTC namespace:** `sport:captain`, `sport:jerseyNumber`, `sport:minutesPlayed`, `sport:rating`, `sport:substitute`

### `iptc-api-football-event-teams-stats`

- **file:** `agent-templates/iptc-mappings/api-football/event-teams-stats.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 27
- **declared prefixes:** `sport` → `https://sportschema.org/ontologies/main/`, `spsocstat` → `https://sportschema.org/ontologies/soccer/`, `spstat` → `https://sportschema.org/ontologies/corestatistics/`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (3): `sport`, `spsocstat`, `spstat`
- **official-iptc-class** (3): `sport:Event`, `sport:Team`, `sport:TeamParticipation`
- **official-iptc-property** (3): `sport:alignment`, `sport:participation`, `sport:participationBy`
- **official-sport-specific-statistic** (13): `spsocstat:cautionsTotal`, `spsocstat:cornerKicks`, `spsocstat:ejectionsTotal`, `spsocstat:foulsCommited`, `spsocstat:offsides`, `spsocstat:passesComplete`, `spsocstat:passesCompletePercentage`, `spsocstat:passesTotal`, `spsocstat:saves`, `spsocstat:shotsBlocked`, `spsocstat:shotsOnGoalTotal`, `spsocstat:shotsTotal`, `spstat:timeOfPossessionPercentage`
- **schema-org-term-unverified** (1): `schema:logo`
- **standard-rdf-term** (1): `rdfs:label`

### `iptc-sportradar-tennis-event-hierarchy-mapping`

- **file:** `agent-templates/iptc-mappings/sportradar-tennis/event-mapping.yml`
- **`sport:` bound to:** `https://www.sportschema.org/ontologies/sport#`  ❌ not official
- **distinct emitted terms:** 5
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://www.sportschema.org/ontologies/sport#`
- **invented-sport-term** (4): `sport:childCompetitions`, `sport:competitionDepth`, `sport:competitionLevel`, `sport:parentCompetitions`
- **jsonld-keyword** (1): `@id`
- **provider field names in the IPTC namespace:** `sport:competitionDepth`, `sport:competitionLevel`

### `iptc-sportradar-tennis-event-mapping`

- **file:** `agent-templates/iptc-mappings/sportradar-tennis/event-mapping.yml`
- **`sport:` bound to:** `https://www.sportschema.org/ontologies/sport#`  ❌ not official
- **distinct emitted terms:** 28
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://www.sportschema.org/ontologies/sport#`
- **invented-sport-term** (13): `sport:Category`, `sport:Sport`, `sport:category`, `sport:competition`, `sport:countryCode`, `sport:genderCategory`, `sport:hasChildren`, `sport:indoor`, `sport:isChildCompetition`, `sport:level`, `sport:matchType`, `sport:parentCompetition`, `sport:surfaceType`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (4): `name`, `schema`, `sport`, `urn:iptc:sport:tennis`
- **official-local-name-wrong-namespace** (5): `sport:Competition`, `sport:Event`, `sport:competitionFormat`, `sport:competitionType`, `sport:sport`
- **schema-org-term-unverified** (3): `schema:SportsEvent`, `schema:addressCountry`, `schema:alternativeName`
- **provider field names in the IPTC namespace:** `sport:genderCategory`, `sport:hasChildren`, `sport:indoor`, `sport:isChildCompetition`, `sport:matchType`, `sport:surfaceType`

### `iptc-sportradar-event-players-stats`

- **file:** `agent-templates/iptc-mappings/sportradar/event-players-stats.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 57
- **declared prefixes:** `rdfs` → `http://www.w3.org/2000/01/rdf-schema#`, `sport` → `https://sportschema.org/ontologies/main/`, `spsocstat` → `https://sportschema.org/ontologies/soccer/`
- **invented-sport-term** (3): `sport:jerseyNumber`, `sport:minutesPlayed`, `sport:position`
- **invented-statistic-term** (21): `spsocstat:aerialDuelsTotal`, `spsocstat:aerialDuelsWon`, `spsocstat:ballsLost`, `spsocstat:ballsRecovered`, `spsocstat:blocksDefensive`, `spsocstat:cautionsSecondYellow`, `spsocstat:crossesSuccessful`, `spsocstat:crossesTotal`, `spsocstat:distributionKicks`, `spsocstat:distributionThrows`, `spsocstat:dribblesAttempted`, `spsocstat:dribblesSuccessful`, `spsocstat:duelsTotal`, `spsocstat:duelsWon`, `spsocstat:longBalls`, `spsocstat:savesCaught`, `spsocstat:savesFromPenalty`, `spsocstat:savesParried`, `spsocstat:substitutedIn`, `spsocstat:substitutedOut`, `spsocstat:throughBalls`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (3): `rdfs`, `sport`, `spsocstat`
- **official-iptc-class** (2): `sport:Athlete`, `sport:IndividualParticipation`
- **official-iptc-property** (2): `sport:participationBy`, `sport:playerStatus`
- **official-sport-specific-statistic** (22): `spsocstat:assistsTotal`, `spsocstat:cautionsTotal`, `spsocstat:clearancesSuccessful`, `spsocstat:cornerKicks`, `spsocstat:ejectionsTotal`, `spsocstat:foulsCommited`, `spsocstat:foulsSuffered`, `spsocstat:goalsAgainstTotal`, `spsocstat:goalsOwn`, `spsocstat:goalsTotal`, `spsocstat:interceptions`, `spsocstat:offsides`, `spsocstat:passesComplete`, `spsocstat:passesCompletePercentage`, `spsocstat:passesTotal`, `spsocstat:saves`, `spsocstat:shotsBlocked`, `spsocstat:shotsOffGoalTotal`, `spsocstat:shotsOnGoalTotal`, `spsocstat:shotsTotal`, `spsocstat:tacklesTotal`, `spsocstat:touches`
- **standard-rdf-term** (1): `rdfs:label`
- **provider field names in the IPTC namespace:** `sport:jerseyNumber`, `sport:minutesPlayed`

### `iptc-sportradar-event-teams-stats`

- **file:** `agent-templates/iptc-mappings/sportradar/event-teams-stats.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 27
- **declared prefixes:** `sport` → `https://sportschema.org/ontologies/main/`, `spsocstat` → `https://sportschema.org/ontologies/soccer/`, `spstat` → `https://sportschema.org/ontologies/corestatistics/`
- **invented-statistic-term** (2): `spsocstat:substitutions`, `spsocstat:throwIns`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (3): `sport`, `spsocstat`, `spstat`
- **official-iptc-class** (3): `sport:Event`, `sport:Team`, `sport:TeamParticipation`
- **official-iptc-property** (3): `sport:alignment`, `sport:participation`, `sport:participationBy`
- **official-sport-specific-statistic** (12): `spsocstat:cautionsTotal`, `spsocstat:cornerKicks`, `spsocstat:ejectionsTotal`, `spsocstat:foulsCommited`, `spsocstat:freeKicks`, `spsocstat:goalsTotal`, `spsocstat:offsides`, `spsocstat:saves`, `spsocstat:shotsBlocked`, `spsocstat:shotsOnGoalTotal`, `spsocstat:shotsTotal`, `spstat:timeOfPossessionPercentage`
- **standard-rdf-term** (1): `rdfs:label`

### `iptc-american-football-event-mapping`

- **file:** `connectors/american-football/mappings/iptc-american-football-event-mapping.yml`
- **`sport:` bound to:** `https://www.sportschema.org/ontologies/sport#`  ❌ not official
- **distinct emitted terms:** 30
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://www.sportschema.org/ontologies/sport#`
- **invented-sport-term** (13): `sport:Season`, `sport:Venue`, `sport:awayScore`, `sport:competition`, `sport:competitors`, `sport:gameInfo`, `sport:halfTime`, `sport:homeScore`, `sport:qualifier`, `sport:season`, `sport:status`, `sport:venue`, `sport:year`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (6): `name`, `schema`, `sport`, `stage`, `timezone`, `week`
- **official-local-name-wrong-namespace** (4): `sport:Competition`, `sport:Event`, `sport:Team`, `sport:score`
- **schema-org-term-unverified** (4): `schema:SportsEvent`, `schema:addressLocality`, `schema:logo`, `schema:startDate`
- **provider field names in the IPTC namespace:** `sport:gameInfo`, `sport:halfTime`

### `iptc-sportradar-event-mlb-mapping`

- **file:** `connectors/sportradar-mlb/mappings/iptc-sport-event.yml`
- **`sport:` bound to:** _not declared_  ❌ not official
- **distinct emitted terms:** 31
- **invented-sport-term** (16): `sport:Season`, `sport:Venue`, `sport:abbreviation`, `sport:awayScore`, `sport:competition`, `sport:competitors`, `sport:doubleHeader`, `sport:gameNumber`, `sport:homeScore`, `sport:market`, `sport:matchStatus`, `sport:qualifier`, `sport:season`, `sport:status`, `sport:venue`, `sport:year`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (4): `name`, `schema`, `sport`, `urn:sportradar:competition:mlb`
- **official-local-name-wrong-namespace** (4): `sport:Competition`, `sport:Event`, `sport:Team`, `sport:score`
- **schema-org-term-unverified** (4): `schema:SportsEvent`, `schema:addressLocality`, `schema:sportName`, `schema:startDate`
- **provider field names in the IPTC namespace:** `sport:abbreviation`, `sport:doubleHeader`, `sport:gameNumber`, `sport:market`, `sport:matchStatus`

### `iptc-sportradar-event-nfl-mapping`

- **file:** `connectors/sportradar-nfl/mappings/iptc-sport-event.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 30
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://sportschema.org/ontologies/main/`, `spsocstat` → `http://cv.iptc.org/newscodes/spsocstat/`, `spstat` → `http://cv.iptc.org/newscodes/spstat/`
- **invented-sport-term** (14): `sport:Season`, `sport:Venue`, `sport:abbreviation`, `sport:awayScore`, `sport:competition`, `sport:competitors`, `sport:halfTime`, `sport:homeScore`, `sport:matchStatus`, `sport:qualifier`, `sport:season`, `sport:status`, `sport:venue`, `sport:year`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (5): `name`, `schema`, `sport`, `urn:sportradar:competition:nfl`, `urn:sportradar:season:2025`
- **official-iptc-class** (3): `sport:Competition`, `sport:Event`, `sport:Team`
- **official-iptc-property** (1): `sport:score`
- **schema-org-term-unverified** (4): `schema:SportsEvent`, `schema:addressLocality`, `schema:sportName`, `schema:startDate`
- **provider field names in the IPTC namespace:** `sport:abbreviation`, `sport:halfTime`, `sport:matchStatus`

### `iptc-sportradar-event-update-mapping`

- **file:** `connectors/sportradar-nfl/mappings/iptc-sport-event.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 11
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://sportschema.org/ontologies/main/`, `spsocstat` → `http://cv.iptc.org/newscodes/spsocstat/`, `spstat` → `http://cv.iptc.org/newscodes/spstat/`
- **invented-sport-term** (9): `sport:awayScore`, `sport:broadcast`, `sport:clock`, `sport:duration`, `sport:homeScore`, `sport:matchStatus`, `sport:quarter`, `sport:status`, `sport:weather`
- **official-iptc-property** (2): `sport:attendance`, `sport:score`
- **provider field names in the IPTC namespace:** `sport:broadcast`, `sport:clock`, `sport:duration`, `sport:matchStatus`, `sport:quarter`, `sport:weather`

### `iptc-sportradar-events-statistics-mapping`

- **file:** `connectors/sportradar-nfl/mappings/iptc-sport-event.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 17
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://sportschema.org/ontologies/main/`, `spsocstat` → `http://cv.iptc.org/newscodes/spsocstat/`, `spstat` → `http://cv.iptc.org/newscodes/spstat/`
- **invented-sport-term** (8): `sport:Statistic`, `sport:TeamStatistics`, `sport:qualifier`, `sport:statLabel`, `sport:statParticipant`, `sport:statType`, `sport:statValue`, `sport:statistics`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (5): `abbreviation`, `name`, `sport`, `spsocstat`, `spstat`
- **official-iptc-class** (1): `sport:Team`
- **provider field names in the IPTC namespace:** `sport:statLabel`, `sport:statParticipant`, `sport:statType`, `sport:statValue`

### `iptc-sportradar-events-timeline-mapping`

- **file:** `connectors/sportradar-nfl/mappings/iptc-sport-event.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 20
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://sportschema.org/ontologies/main/`, `spsocstat` → `http://cv.iptc.org/newscodes/spsocstat/`, `spstat` → `http://cv.iptc.org/newscodes/spstat/`
- **invented-sport-term** (1): `sport:label`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (4): `commentaries`, `competitor`, `sport`, `type`
- **official-iptc-class** (5): `sport:Action`, `sport:Athlete`, `sport:IndividualParticipation`, `sport:Team`, `sport:TeamParticipation`
- **official-iptc-property** (7): `sport:actionDateTime`, `sport:actionType`, `sport:fieldLocation`, `sport:minutesElapsed`, `sport:participation`, `sport:participationBy`, `sport:periodValue`

### `iptc-sportradar-game-statistics-mapping`

- **file:** `connectors/sportradar-nfl/mappings/iptc-sport-event.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 36
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://sportschema.org/ontologies/main/`, `spsocstat` → `http://cv.iptc.org/newscodes/spsocstat/`, `spstat` → `http://cv.iptc.org/newscodes/spstat/`
- **invented-sport-term** (27): `sport:GameStatistics`, `sport:TeamStatistics`, `sport:broadcast`, `sport:clock`, `sport:defense`, `sport:duration`, `sport:efficiency`, `sport:extraPoints`, `sport:fieldGoals`, `sport:firstDowns`, `sport:fumbles`, `sport:interceptions`, `sport:kickReturns`, `sport:kickoffs`, `sport:passing`, `sport:penalties`, `sport:puntReturns`, `sport:punts`, `sport:qualifier`, `sport:quarter`, `sport:receiving`, `sport:rushing`, `sport:summary`, `sport:team`, `sport:teamStatistics`, `sport:touchdowns`, `sport:weather`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (4): `abbreviation`, `name`, `sport`, `spstat`
- **official-iptc-class** (1): `sport:Team`
- **official-iptc-property** (1): `sport:attendance`
- **provider field names in the IPTC namespace:** `sport:broadcast`, `sport:clock`, `sport:defense`, `sport:duration`, `sport:efficiency`, `sport:extraPoints`, `sport:fieldGoals`, `sport:firstDowns`, `sport:fumbles`, `sport:interceptions`, `sport:kickReturns`, `sport:kickoffs`, `sport:passing`, `sport:puntReturns`, `sport:punts`, `sport:quarter`, `sport:receiving`, `sport:rushing`, `sport:summary`, `sport:teamStatistics`, `sport:touchdowns`, `sport:weather`

### `iptc-sportradar-player-statistics-mapping`

- **file:** `connectors/sportradar-nfl/mappings/iptc-sport-event.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 13
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://sportschema.org/ontologies/main/`, `spsocstat` → `http://cv.iptc.org/newscodes/spsocstat/`, `spstat` → `http://cv.iptc.org/newscodes/spstat/`
- **invented-sport-term** (8): `sport:PlayerStatistics`, `sport:category`, `sport:jersey`, `sport:player`, `sport:position`, `sport:qualifier`, `sport:statistics`, `sport:team`
- **jsonld-keyword** (2): `@id`, `@type`
- **machina-operational-field** (1): `name`
- **official-iptc-class** (2): `sport:Athlete`, `sport:Team`
- **provider field names in the IPTC namespace:** `sport:jersey`

### `iptc-sportradar-event-mapping`

- **file:** `connectors/sportradar-soccer/mappings/iptc-sport-event.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 41
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://sportschema.org/ontologies/main/`, `spsocstat` → `http://cv.iptc.org/newscodes/spsocstat/`, `spstat` → `http://cv.iptc.org/newscodes/spstat/`
- **invented-sport-term** (27): `sport:BroadcastChannel`, `sport:Round`, `sport:Season`, `sport:Stage`, `sport:Venue`, `sport:aggregate`, `sport:awayScore`, `sport:channelName`, `sport:channelUrl`, `sport:channels`, `sport:competition`, `sport:competitors`, `sport:country`, `sport:countryCode`, `sport:halfTime`, `sport:homeScore`, `sport:matchStatus`, `sport:number`, `sport:penalties`, `sport:phase`, `sport:qualifier`, `sport:round`, `sport:season`, `sport:stage`, `sport:status`, `sport:venue`, `sport:year`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (3): `name`, `schema`, `sport`
- **official-iptc-class** (3): `sport:Competition`, `sport:Event`, `sport:Team`
- **official-iptc-property** (1): `sport:score`
- **schema-org-term-unverified** (4): `schema:SportsEvent`, `schema:addressLocality`, `schema:sportName`, `schema:startDate`
- **provider field names in the IPTC namespace:** `sport:aggregate`, `sport:channelName`, `sport:channelUrl`, `sport:channels`, `sport:halfTime`, `sport:matchStatus`

### `iptc-sportradar-events-statistics-mapping`

- **file:** `connectors/sportradar-soccer/mappings/iptc-sport-event.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 17
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://sportschema.org/ontologies/main/`, `spsocstat` → `http://cv.iptc.org/newscodes/spsocstat/`, `spstat` → `http://cv.iptc.org/newscodes/spstat/`
- **invented-sport-term** (8): `sport:Statistic`, `sport:TeamStatistics`, `sport:qualifier`, `sport:statLabel`, `sport:statParticipant`, `sport:statType`, `sport:statValue`, `sport:statistics`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (5): `abbreviation`, `name`, `sport`, `spsocstat`, `spstat`
- **official-iptc-class** (1): `sport:Team`
- **provider field names in the IPTC namespace:** `sport:statLabel`, `sport:statParticipant`, `sport:statType`, `sport:statValue`

### `iptc-sportradar-events-timeline-mapping`

- **file:** `connectors/sportradar-soccer/mappings/iptc-sport-event.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 31
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://sportschema.org/ontologies/main/`, `spsocstat` → `http://cv.iptc.org/newscodes/spsocstat/`, `spstat` → `http://cv.iptc.org/newscodes/spstat/`
- **invented-sport-term** (12): `sport:awayScore`, `sport:cardColor`, `sport:cardType`, `sport:homeScore`, `sport:label`, `sport:penaltyStatus`, `sport:periodType`, `sport:playerRole`, `sport:scoreMethod`, `sport:shootoutAttempt`, `sport:shootoutAwayScore`, `sport:shootoutHomeScore`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (4): `commentaries`, `competitor`, `sport`, `type`
- **official-iptc-class** (5): `sport:Action`, `sport:Athlete`, `sport:IndividualParticipation`, `sport:Team`, `sport:TeamParticipation`
- **official-iptc-property** (7): `sport:actionDateTime`, `sport:actionType`, `sport:fieldLocation`, `sport:minutesElapsed`, `sport:participation`, `sport:participationBy`, `sport:periodValue`
- **provider field names in the IPTC namespace:** `sport:cardColor`, `sport:cardType`, `sport:penaltyStatus`, `sport:periodType`, `sport:scoreMethod`, `sport:shootoutAttempt`, `sport:shootoutAwayScore`, `sport:shootoutHomeScore`

### `iptc-sportradar-team-mapping`

- **file:** `connectors/sportradar-soccer/mappings/iptc-team.yml`
- **`sport:` bound to:** `https://www.sportschema.org/ontologies/sport#`  ❌ not official
- **distinct emitted terms:** 17
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://www.sportschema.org/ontologies/sport#`
- **invented-sport-term** (7): `sport:abbreviation`, `sport:code`, `sport:country`, `sport:countryCode`, `sport:officialName`, `sport:shortName`, `sport:status`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (4): `name`, `schema`, `sport`, `title`
- **official-local-name-wrong-namespace** (1): `sport:Team`
- **schema-org-term-unverified** (2): `schema:SportsTeam`, `schema:name`
- **provider field names in the IPTC namespace:** `sport:abbreviation`

### `iptc-sportradar-tennis-event-mapping`

- **file:** `connectors/sportradar-tennis/mappings/iptc-event-mapping.yml`
- **`sport:` bound to:** `https://www.sportschema.org/ontologies/sport#`  ❌ not official
- **distinct emitted terms:** 109
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://www.sportschema.org/ontologies/sport#`
- **invented-sport-term** (89): `sport:Competitor`, `sport:Season`, `sport:Sport`, `sport:Stage`, `sport:Venue`, `sport:abbreviation`, `sport:aces`, `sport:awayScore`, `sport:bestOf`, `sport:bracketNumber`, `sport:breakpointsWon`, `sport:category`, `sport:categoryId`, `sport:categoryName`, `sport:channelName`, `sport:channels`, `sport:competition`, `sport:competitionContext`, `sport:competitionGender`, `sport:competitionLevel`, `sport:competitorId`, `sport:competitorName`, `sport:competitorStats`, `sport:competitors`, `sport:country`, `sport:countryCode`, `sport:coverage`, `sport:detailedServeOutcomes`, `sport:documentType`, `sport:doubleFaults`, `sport:enhancedStats`, `sport:estimated`, `sport:eventDetails`, `sport:firstServePointsWon`, `sport:firstServeSuccessful`, `sport:gameInfo`, `sport:gamesWon`, `sport:genderCategory`, `sport:groupId`, `sport:groupName`, `sport:groups`, `sport:hasWinner`, `sport:homeScore`, `sport:isFinished`, `sport:level`, `sport:matchType`, `sport:maxGamesInARow`, `sport:maxPointsInARow`, `sport:mode`, `sport:order`, `sport:parentId`, `sport:periodNumber`, `sport:periodScores`, `sport:periodType`, `sport:phase`, `sport:playByPlay`, `sport:pointsWon`, `sport:pointsWonFromLast10`, `sport:qualifier`, `sport:round`, `sport:roundName`, `sport:roundNumber`, `sport:scores`, `sport:season`, `sport:seasonContext`, `sport:seasonEndDate`, `sport:seasonStartDate`, `sport:secondServePointsWon`, `sport:secondServeSuccessful`, `sport:seed`, `sport:selected`, `sport:serviceGamesWon`, `sport:servicePointsLost`, `sport:servicePointsWon`, `sport:stage`, `sport:stagePhase`, `sport:startTime`, `sport:startTimeConfirmed`, `sport:statistics`, `sport:status`, `sport:tiebreaksWon`, `sport:timezone`, `sport:title`, `sport:totalBreakpoints`, `sport:totalSets`, `sport:type`, `sport:venue`, `sport:winnerId`, `sport:year`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (4): `name`, `schema`, `sport`, `urn:iptc:sport:tennis`
- **official-local-name-wrong-namespace** (8): `sport:Competition`, `sport:Event`, `sport:competitionFormat`, `sport:competitionType`, `sport:endDate`, `sport:score`, `sport:sport`, `sport:startDate`
- **schema-org-term-unverified** (5): `schema:SportsEvent`, `schema:addressCountry`, `schema:addressLocality`, `schema:sportName`, `schema:startDate`
- **provider field names in the IPTC namespace:** `sport:abbreviation`, `sport:bestOf`, `sport:bracketNumber`, `sport:categoryId`, `sport:categoryName`, `sport:channelName`, `sport:channels`, `sport:competitionContext`, `sport:competitionLevel`, `sport:competitorId`, `sport:competitorName`, `sport:competitorStats`, `sport:coverage`, `sport:detailedServeOutcomes`, `sport:documentType`, `sport:enhancedStats`, `sport:estimated`, `sport:eventDetails`, `sport:gameInfo`, `sport:genderCategory`, `sport:groupId`, `sport:groupName`, `sport:groups`, `sport:hasWinner`, `sport:isFinished`, `sport:matchType`, `sport:mode`, `sport:parentId`, `sport:periodType`, `sport:playByPlay`, `sport:roundName`, `sport:roundNumber`, `sport:seasonContext`, `sport:seasonEndDate`, `sport:seasonStartDate`, `sport:seed`, `sport:selected`, `sport:stagePhase`, `sport:startTimeConfirmed`, `sport:totalSets`, `sport:winnerId`

### `iptc-opta-player-mapping`

- **file:** `connectors/stats-perform/mappings/iptc-player.yml`
- **`sport:` bound to:** `https://www.sportschema.org/ontologies/sport#`  ❌ not official
- **distinct emitted terms:** 44
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://www.sportschema.org/ontologies/sport#`
- **invented-sport-term** (17): `sport:Player`, `sport:active`, `sport:club`, `sport:clubCode`, `sport:clubId`, `sport:competitionId`, `sport:competitionName`, `sport:gender`, `sport:knownName`, `sport:matchName`, `sport:nationalityId`, `sport:placeOfBirth`, `sport:position`, `sport:seasonId`, `sport:secondNationality`, `sport:shirtNumber`, `sport:type`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (16): `appearances`, `chances_created`, `expected_goals`, `final_third_passes`, `games_played`, `goals`, `key_passes`, `lastUpdated`, `minutes_played`, `name`, `schema`, `shots`, `shots_on_target`, `sport`, `stats`, `title`
- **official-local-name-wrong-namespace** (3): `sport:endDate`, `sport:nationality`, `sport:startDate`
- **schema-org-term-unverified** (5): `schema:Person`, `schema:birthDate`, `schema:familyName`, `schema:givenName`, `schema:name`
- **provider field names in the IPTC namespace:** `sport:clubCode`, `sport:clubId`, `sport:competitionId`, `sport:competitionName`, `sport:knownName`, `sport:matchName`, `sport:nationalityId`, `sport:seasonId`, `sport:shirtNumber`

### `iptc-opta-event-mapping`

- **file:** `connectors/stats-perform/mappings/iptc-sport-event.yml`
- **`sport:` bound to:** `https://sportschema.org/ontologies/main/`  ✅ official
- **distinct emitted terms:** 71
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://sportschema.org/ontologies/main/`
- **invented-sport-term** (32): `sport:Season`, `sport:Stage`, `sport:Venue`, `sport:aggregate`, `sport:awayScore`, `sport:code`, `sport:competition`, `sport:competitionCode`, `sport:competitors`, `sport:coverageLevel`, `sport:halfTime`, `sport:homeScore`, `sport:knownName`, `sport:label`, `sport:localDate`, `sport:localTime`, `sport:matchInfo`, `sport:neutral`, `sport:numberOfPeriods`, `sport:officialName`, `sport:penalties`, `sport:periodLength`, `sport:qualifier`, `sport:season`, `sport:shortName`, `sport:stage`, `sport:status`, `sport:timeline`, `sport:var`, `sport:venue`, `sport:week`, `sport:winner`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (12): `commentaries`, `competitor`, `consumer-update-timestamp`, `counter`, `finished`, `name`, `processing`, `schema`, `sport`, `text`, `type`, `version_control`
- **official-iptc-class** (7): `sport:Action`, `sport:Athlete`, `sport:Competition`, `sport:Event`, `sport:IndividualParticipation`, `sport:Team`, `sport:TeamParticipation`
- **official-iptc-property** (12): `sport:actionDateTime`, `sport:actionType`, `sport:attendance`, `sport:competitionFormat`, `sport:endDate`, `sport:minutesElapsed`, `sport:participation`, `sport:participationBy`, `sport:periodValue`, `sport:role`, `sport:score`, `sport:startDate`
- **schema-org-term-unverified** (5): `schema:SportsEvent`, `schema:latitude`, `schema:longitude`, `schema:sportName`, `schema:startDate`
- **provider field names in the IPTC namespace:** `sport:aggregate`, `sport:competitionCode`, `sport:coverageLevel`, `sport:halfTime`, `sport:knownName`, `sport:localDate`, `sport:localTime`, `sport:matchInfo`, `sport:neutral`, `sport:numberOfPeriods`, `sport:periodLength`, `sport:timeline`, `sport:var`, `sport:week`

### `iptc-opta-team-mapping`

- **file:** `connectors/stats-perform/mappings/iptc-team.yml`
- **`sport:` bound to:** `https://www.sportschema.org/ontologies/sport#`  ❌ not official
- **distinct emitted terms:** 25
- **declared prefixes:** `schema` → `https://schema.org/`, `sport` → `https://www.sportschema.org/ontologies/sport#`
- **invented-sport-term** (11): `sport:city`, `sport:code`, `sport:country`, `sport:countryId`, `sport:details`, `sport:founded`, `sport:officialName`, `sport:shortName`, `sport:status`, `sport:teamType`, `sport:type`
- **jsonld-keyword** (3): `@context`, `@id`, `@type`
- **machina-operational-field** (7): `lastUpdated`, `name`, `postalCode`, `schema`, `sport`, `streetAddress`, `title`
- **official-local-name-wrong-namespace** (1): `sport:Team`
- **schema-org-term-unverified** (3): `schema:SportsTeam`, `schema:address`, `schema:name`
- **provider field names in the IPTC namespace:** `sport:countryId`, `sport:teamType`

## Consumers

Each row is a field path the consumer migration must cover. A consumer here is a legacy dependency: it was written against whichever shape it happened to see first, so its expectations are a contract this PR is not allowed to break.

| File | Kind | Field paths read | Payload keys read |
|---|---|---|---|
| `agent-templates/assistant-tools/scripts/event-processor.py` | script | `schema:startDate`, `sport:competitor`, `sport:competitors`, `sport:homeScore`, `sport:score`, `sport:status` | — |
| `agent-templates/assistant-tools/scripts/event-summarizer.py` | script | `schema:startDate`, `sport:awayScore`, `sport:channelName`, `sport:channels`, `sport:competition`, `sport:competitor`, `sport:competitors`, `sport:homeScore`, `sport:qualifier`, `sport:score`, `sport:status` | — |
| `agent-templates/assistant-tools/scripts/market-event-matcher.py` | script | `schema:startDate`, `sport:competitor`, `sport:competitors` | — |
| `agent-templates/assistant-tools/scripts/market-extractor.py` | script | `sport:competitor`, `sport:competitors` | — |
| `agent-templates/assistant-tools/scripts/message-data-transformer.py` | script | `schema:startDate`, `sport:awayScore`, `sport:channelName`, `sport:channels`, `sport:competition`, `sport:competitor`, `sport:competitors`, `sport:homeScore`, `sport:label`, `sport:minutesElapsed`, `sport:participation`, `sport:participationBy`, `sport:qualifier`, `sport:score`, `sport:statLabel`, `sport:statValue`, `sport:statistics`, `sport:status` | — |
| `agent-templates/assistant-tools/tools/event-matcher.yml` | workflow-or-mapping | `schema:startDate`, `sport:competition`, `sport:season`, `sport:status` | — |
| `agent-templates/assistant-tools/tools/find-historical.yml` | workflow-or-mapping | `schema:startDate`, `sport:status` | `iptc-events` |
| `agent-templates/assistant-tools/tools/find-odds.yml` | workflow-or-mapping | `schema:startDate`, `sport:status` | — |
| `agent-templates/assistant-tools/tools/find-upcoming.yml` | workflow-or-mapping | `schema:startDate` | `iptc-events` |
| `agent-templates/chat-completion/workflows/chat-moderator.yml` | workflow-or-mapping | `schema:startDate` | `iptc-events`, `sport-schema-event`, `sport_schema_event` |
| `agent-templates/coverage-tools/mappings/selectors.yml` | workflow-or-mapping | `schema:sportName`, `schema:startDate`, `sport:awayScore`, `sport:competition`, `sport:homeScore`, `sport:round`, `sport:score`, `sport:season`, `sport:stage`, `sport:status`, `sport:venue` | `iptc-events` |
| `agent-templates/coverage-tools/scripts/past_events.py` | script | `schema:sportName`, `schema:startDate`, `sport:awayScore`, `sport:competition`, `sport:competitor`, `sport:competitors`, `sport:halfTime`, `sport:homeScore`, `sport:matchStatus`, `sport:qualifier`, `sport:score`, `sport:season`, `sport:venue` | — |
| `agent-templates/coverage-tools/tools/find-images.yml` | workflow-or-mapping | `schema:startDate`, `sport:competitor`, `sport:competitors` | — |
| `agent-templates/coverage-tools/tools/soccer/tallysight-widgets.yml` | workflow-or-mapping | `schema:startDate`, `sport:competition`, `sport:competitor`, `sport:competitors` | — |
| `agent-templates/iptc-mappings/any-selector/event-selector.yml` | workflow-or-mapping | `schema:startDate`, `sport:score` | — |
| `agent-templates/iptc-mappings/any-selector/events-selector.yml` | workflow-or-mapping | `schema:startDate`, `sport:score` | `iptc-events` |
| `agent-templates/iptc-mappings/any-selector/events-summary.yml` | workflow-or-mapping | `schema:sportName`, `schema:startDate`, `sport:actionType`, `sport:awayScore`, `sport:channelName`, `sport:channels`, `sport:competition`, `sport:fieldLocation`, `sport:homeScore`, `sport:label`, `sport:minutesElapsed`, `sport:participation`, `sport:participationBy`, `sport:periodValue`, `sport:qualifier`, `sport:score`, `sport:season`, `sport:statLabel`, `sport:statParticipant`, `sport:statValue`, `sport:statistics`, `sport:status`, `sport:venue` | `iptc-events` |
| `agent-templates/iptc-mappings/any-source/custom-event-test.yml` | workflow-or-mapping | — | `sport-schema-event`, `sport_schema_event` |
| `agent-templates/iptc-mappings/api-football/event-mapping-test.yml` | workflow-or-mapping | — | `sport-schema-event`, `sport_schema_event` |
| `agent-templates/iptc-mappings/sportradar/event-mapping-test.yml` | workflow-or-mapping | — | `sport-schema-event`, `sport_schema_event` |
| `agent-templates/kalshi-market-agent/scripts/market-event-matcher.py` | script | `schema:startDate`, `sport:competitor`, `sport:competitors` | — |
| `agent-templates/kalshi-market-agent/workflows/combo-analysis/executor.yml` | workflow-or-mapping | `schema:startDate`, `sport:competition`, `sport:status` | `iptc-events` |
| `agent-templates/kalshi-market-agent/workflows/event-matcher.yml` | workflow-or-mapping | `schema:startDate`, `sport:competition`, `sport:season`, `sport:status` | — |
| `agent-templates/kalshi-market-agent/workflows/market-analysis/consumer.yml` | workflow-or-mapping | `schema:sportName`, `schema:startDate`, `sport:competition`, `sport:status` | — |
| `agent-templates/kalshi-market-agent/workflows/market-analysis/executor.yml` | workflow-or-mapping | `schema:startDate`, `sport:competitor`, `sport:competitors`, `sport:status` | `iptc-events` |
| `agent-templates/world-cup-intelligence/mappings/worldcup-iptc-event-to-api-response.yml` | workflow-or-mapping | `schema:startDate`, `sport:competition`, `sport:competitor`, `sport:competitors`, `sport:status`, `sport:venue` | — |
| `agent-templates/world-cup-intelligence/prompts/worldcup-match-recap.yml` | workflow-or-mapping | `sport:status` | — |
| `agent-templates/world-cup-intelligence/tests/test_worldcup_market_intelligence.py` | test | `schema:startDate`, `sport:competition`, `sport:competitor`, `sport:competitors`, `sport:qualifier`, `sport:round`, `sport:status`, `sport:venue` | — |
| `agent-templates/world-cup-intelligence/workflows/wcbracket-enrich-teams.yml` | workflow-or-mapping | `sport:competitor`, `sport:competitors`, `sport:qualifier` | — |
| `agent-templates/world-cup-intelligence/workflows/wcbracket-simulate.yml` | workflow-or-mapping | `schema:startDate`, `sport:competitor`, `sport:competitors`, `sport:qualifier`, `sport:status` | — |
| `agent-templates/world-cup-intelligence/workflows/worldcup-coverage-gateway.yml` | workflow-or-mapping | `sport:status` | — |
| `agent-templates/world-cup-intelligence/workflows/worldcup-get-injuries.yml` | workflow-or-mapping | `schema:startDate`, `sport:competitor`, `sport:competitors`, `sport:qualifier` | — |
| `agent-templates/world-cup-intelligence/workflows/worldcup-get-squads.yml` | workflow-or-mapping | `sport:competitor`, `sport:competitors`, `sport:qualifier` | — |
| `agent-templates/world-cup-intelligence/workflows/worldcup-get-standings.yml` | workflow-or-mapping | `schema:startDate` | — |
| `agent-templates/world-cup-intelligence/workflows/worldcup-ingest-fixtures.yml` | workflow-or-mapping | — | `iptc_events`, `sport_schema_event`, `sport_schema_events` |
| `agent-templates/world-cup-intelligence/workflows/worldcup-match-recap.yml` | workflow-or-mapping | `sport:status` | — |
| `agent-templates/world-cup-intelligence/workflows/worldcup-sync-market-sources.yml` | workflow-or-mapping | `schema:startDate`, `sport:competitor`, `sport:competitors` | — |
| `agent-templates/world-cup-intelligence/workflows/worldcup-sync-model-forecasts.yml` | workflow-or-mapping | `sport:status` | — |
| `agent-templates/world-cup-intelligence/worldcup-market-intelligence.py` | script | `schema:startDate`, `sport:competition`, `sport:competitor`, `sport:competitors`, `sport:qualifier`, `sport:round`, `sport:status`, `sport:venue` | `sport_schema_event`, `sport_schema_events` |
| `connectors/american-football/workflows/sync-games.yml` | workflow-or-mapping | — | `sport_schema_event`, `sport_schema_events` |
| `connectors/api-football/sync-fixtures-events.yml` | workflow-or-mapping | `sport:label` | `iptc_events`, `iptc_schema_events`, `iptc_schema_ids` |
| `connectors/api-football/sync-fixtures-players-statistics.yml` | workflow-or-mapping | — | `iptc_players`, `iptc_players_statistics`, `iptc_schema_events`, `iptc_schema_ids` |
| `connectors/api-football/sync-fixtures-teams-statistics.yml` | workflow-or-mapping | `sport:participation`, `sport:participationBy` | `iptc_schema_events`, `iptc_schema_ids`, `iptc_teams`, `iptc_teams_statistics` |
| `connectors/api-football/sync-fixtures.yml` | workflow-or-mapping | — | `sport_schema_event`, `sport_schema_events` |
| `connectors/api-football/workflows/event-consumer-live.yml` | workflow-or-mapping | `schema:startDate`, `sport:competition`, `sport:status` | — |
| `connectors/api-football/workflows/event-consumer-prelive.yml` | workflow-or-mapping | `schema:startDate`, `sport:competition`, `sport:status` | — |
| `connectors/api-football/workflows/event-sync-markets.yml` | workflow-or-mapping | `schema:startDate` | `iptc_schema_events` |
| `connectors/api-football/workflows/event-synchronize.yml` | workflow-or-mapping | `schema:startDate` | `iptc_schema_events`, `sport_schema_event`, `sport_schema_events` |
| `connectors/api-football/workflows/event-update.yml` | workflow-or-mapping | `schema:startDate` | — |
| `connectors/sportradar-mlb/sync-games.yml` | workflow-or-mapping | `schema:sportName`, `sport:competition`, `sport:homeScore`, `sport:score`, `sport:status` | `sport_schema_event`, `sport_schema_events` |
| `connectors/sportradar-mlb/sync-pitchers.yml` | workflow-or-mapping | `sport:score`, `sport:status` | — |
| `connectors/sportradar-mlb/sync-results.yml` | workflow-or-mapping | `sport:awayScore`, `sport:homeScore`, `sport:matchStatus`, `sport:score`, `sport:status` | — |
| `connectors/sportradar-nfl/sync-games.yml` | workflow-or-mapping | `schema:sportName`, `sport:abbreviation`, `sport:competition`, `sport:competitor`, `sport:competitors`, `sport:status` | `sport_schema_event`, `sport_schema_events` |
| `connectors/sportradar-nfl/workflows/event-consumer-live.yml` | workflow-or-mapping | `schema:sportName`, `schema:startDate`, `sport:competition`, `sport:status` | — |
| `connectors/sportradar-nfl/workflows/event-consumer-prelive.yml` | workflow-or-mapping | `schema:sportName`, `schema:startDate`, `sport:competition`, `sport:status` | — |
| `connectors/sportradar-nfl/workflows/event-sync-timeline.yml` | workflow-or-mapping | — | `iptc_game_statistics`, `iptc_player_statistics`, `iptc_schema_events` |
| `connectors/sportradar-soccer/workflows/event-consumer-live.yml` | workflow-or-mapping | `schema:startDate`, `sport:competition`, `sport:status` | — |
| `connectors/sportradar-soccer/workflows/event-consumer-prelive.yml` | workflow-or-mapping | `schema:startDate`, `sport:competition`, `sport:status` | — |
| `connectors/sportradar-soccer/workflows/event-consumer.yml` | workflow-or-mapping | `schema:startDate`, `sport:status` | — |
| `connectors/sportradar-soccer/workflows/event-synchronize.yml` | workflow-or-mapping | — | `iptc_events`, `iptc_events_statistics`, `iptc_events_timeline`, `iptc_schema_events`, `sport_schema_event`, `sport_schema_events` |
| `connectors/sportradar-soccer/workflows/load-round-events.yml` | workflow-or-mapping | `schema:startDate`, `sport:competition`, `sport:round` | — |
| `connectors/sportradar-soccer/workflows/sync-competitors.yml` | workflow-or-mapping | — | `iptc_teams`, `sport_schema_teams` |
| `connectors/sportradar-soccer/workflows/sync-events-stats.yml` | workflow-or-mapping | — | `iptc_events`, `iptc_match_statistics`, `iptc_players`, `iptc_players_statistics`, `iptc_schema_events`, `iptc_schema_ids`, `iptc_teams`, `iptc_teams_statistics` |
| `connectors/sportradar-soccer/workflows/sync-schedules.yml` | workflow-or-mapping | `schema:sportName`, `sport:competition` | `sport_schema_event`, `sport_schema_events` |
| `connectors/sportradar-tennis/workflows/sync-season-info.yml` | workflow-or-mapping | `sport:competition`, `sport:season`, `sport:venue` | — |
| `connectors/sportradar-tennis/workflows/sync-season-summaries.yml` | workflow-or-mapping | — | `iptc-events`, `sport_schema_event`, `sport_schema_events` |
| `connectors/stats-perform/workflows/sp-opta-event-consumer-live.yml` | workflow-or-mapping | `schema:startDate`, `sport:status` | — |
| `connectors/stats-perform/workflows/sp-opta-event-consumer-prelive.yml` | workflow-or-mapping | `schema:startDate`, `sport:status` | — |
| `connectors/stats-perform/workflows/sp-opta-event-sync-markets.yml` | workflow-or-mapping | `schema:startDate` | — |
| `connectors/stats-perform/workflows/sp-opta-event-synchronize.yml` | workflow-or-mapping | `schema:startDate`, `sport:competition` | `sport_schema_event`, `sport_schema_events` |
| `connectors/stats-perform/workflows/sp-opta-event-update.yml` | workflow-or-mapping | `schema:startDate` | — |
| `connectors/stats-perform/workflows/sync-players.yml` | workflow-or-mapping | `sport:competition`, `sport:season` | `iptc_players`, `sport_schema_players` |
| `connectors/stats-perform/workflows/sync-schedules.yml` | workflow-or-mapping | `schema:sportName`, `sport:competition` | `sport_schema_event`, `sport_schema_events` |
| `connectors/stats-perform/workflows/sync-teams.yml` | workflow-or-mapping | `schema:sportName` | `iptc_teams`, `sport_schema_teams` |
| `connectors/stats-perform/workflows/sync-update-live.yml` | workflow-or-mapping | `schema:startDate`, `sport:status` | `sport_schema_event`, `sport_schema_events` |

## Known gaps in this inventory

- schema.org terms are listed but NOT validated: no schema.org vocabulary is pinned in this repository, so `schema-org-term-unverified` means exactly that and no more.
- Emitted terms are read from the literal quoted keys in each mapping expression. The expression is never evaluated, because its language belongs to the Machina workflow engine rather than to Python. A term produced only by string construction at runtime would not appear here.
- The consumer scan matches known IPTC field paths and payload state keys as substrings. A consumer that reaches an IPTC field through a variable it built at runtime would be missed. A consumer this inventory misses is an inventory defect: extend the inventory, do not widen the tolerance.
- Provider attribution for gate 4 comes from the reviewed table in tools/iptc/rules/provider-leak-terms.json, not from inference.
- Term classification is per emitting mapping, so the same spelling can land in different categories in different mappings: `sport:Event` is `official-iptc-class` only where the mapping binds sport: to https://sportschema.org/ontologies/main/, and `official-local-name-wrong-namespace` where it does not.
- NewsCode classification checks a literal code against the pinned TTL where one is present in the mapping text. Where the mapping supplies only a prefix, or the scheme has no TTL at the pinned commit, the term is `newscode-unverifiable` and no membership claim is made.
