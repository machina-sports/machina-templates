# RFC 001 — Machina IPTC Sport Schema Profile

| | |
|---|---|
| **Status** | Accepted for PR 1. Normative for PR 2 and PR 3. |
| **Target standard** | IPTC Sport Schema **1.1** |
| **Pin** | `https://github.com/iptc/sport-schema` @ `0e77bf8678f3702fe81c28673bede35efe47d633` |
| **Vendored at** | `agent-templates/iptc-mappings/references/iptc-sport-schema-1.1/` |
| **Shared context** | `agent-templates/iptc-mappings/contexts/iptc-sport-schema-1.1.context.jsonld` |
| **Executable form** | `tools/iptc/` — layer 3 of the harness implements this document |
| **Grounding** | The pinned upstream artefacts vendored in this repository, and the measured baseline in `docs/iptc/` |
| **Profile version** | `machina-iptc-profile/1.1` (see §15) |

---

## 0. The boundary this document does not cross

Read this section before anything else in this RFC. Three different things in this
program carry the word "graph" and conflating them is the specific failure this
document exists to prevent.

1. **The Machina canonical domain model lives in MongoDB.** It is authoritative
   and durable, and it is not called a graph. This RFC does not change that
   invariant: MongoDB owns canonical durable sports facts, everything derived from
   them is rebuildable, and a projection outage never blocks a canonical write.

2. **Internal derived projections** are rebuildable and traversable, and exist for
   identity resolution, provenance and impact analysis. Their labels and
   relationship names are internal and are never an external contract.

3. **`sport_schema_graph`** is a JSON-LD `@graph` interchange document. **Within
   the IPTC interoperability contract, and only there, it is the authoritative
   IPTC representation.** That is the entire scope of its authority. It is
   generated from the canonical model, it is versioned, and it can be regenerated
   from scratch. If it and the canonical model ever disagree, the canonical model
   is right and the serializer has a bug.

**IPTC is an output projection. It is never the database model and never Machina
identity.** IPTC terms attach to a Machina identity as classifications; they are
not the identity. IPTC response projection is owned by the mapping and serializer
layer, never by a storage schema.

`event_view` is a **separate** operational projection, defined in §11. It is not a
subset of `sport_schema_graph`, is not derived from it, and does not attempt to be
RDF. Both outputs derive independently from the canonical record, so a defect in
one cannot propagate into the other.

Anyone reading `sport_schema_graph` as "the database" is reading it wrong. Say so
in review.

---

## 1. Why a profile at all

The official SHACL shapes are necessary and insufficient. They are silent on every
question below, and every one of them is a question this repository has
historically answered inconsistently:

- which JSON-LD context a payload uses, and therefore what its terms mean;
- whether a controlled-vocabulary value arrived as a resolvable node reference or
  as a bare string that expands to a literal;
- whether an absent fact was omitted or fabricated as `null` / `""` / `"Unknown"`;
- whether distinct concepts are distinct resources or one flattened tree;
- whether resource identifiers are stable across regeneration and collision-free
  across providers;
- where a Machina-specific or provider-specific value is allowed to live.

The shapes also cannot catch the single most dangerous defect in the current
baseline. A payload whose `sport` prefix points at
`https://www.sportschema.org/ontologies/sport#` produces **no instances of any
official IPTC class**. Every `sh:targetClass` then matches nothing and a SHACL
processor reports `conforms=true` over an empty target set. Seven of the fourteen
baseline fixtures are in exactly that state. A profile that operates on the source
document rather than only on the expanded graph is what makes that visible.

**This document is normative. `tools/iptc/profile.py` is its executable form. If
they disagree, this document is right and the code is a bug.**

---

## 2. Target version and how the version claim is grounded

Sport Schema **1.1**, pinned to commit `0e77bf8678f3702fe81c28673bede35efe47d633`.

**There is no 1.1 release tag upstream.** The commit is the pin. Do not write a
tag-shaped reference and do not add a tag-shaped alias in tooling: an invented pin
is unverifiable, which is the class of defect this whole correction exists to
remove.

The version claim rests on three statements inside the pinned bytes, all vendored
so they can be re-checked offline:

1. `README.md` — "Latest version: Sport Schema 1.1".
2. `credits.markdown` — "Version 1.1 was approved by the IPTC Standards Committee
   on 2 October 2024."
3. `ontologies/iptc-sport-ontology.ttl` — `owl:versionIRI
   <https://sportschema.org/ontologies/main/1.1>` and `owl:versionInfo
   "1.1"^^xsd:string`.

Licence: CC-BY 4.0, declared in-band by `dcterms:license` and `dcterms:rights` on
every `owl:Ontology`. The upstream repository has **no LICENSE file** at this
commit; `LICENSE.md` in the vendored directory is a Machina-authored attribution
notice quoting the in-band declaration, and says so.

`upstream-commit.json` records the sha256 of every vendored file.
`python3 -m tools.iptc --verify-pin` re-checks all of them. A mismatch is a hard
failure, not a finding: a silently edited reference file voids every conformance
claim downstream of it.

### 2.1 Two upstream defects, worked around in memory only

Both are documented in the vendored `UPSTREAM.md` and reported on every run.
Neither ever modifies the vendored bytes.

| Defect | Extent | Handling |
|---|---|---|
| Missing `.` after the final `@prefix` directive | 15 of 17 vocabulary TTLs | each file is parsed as-is first; only on failure is a repaired in-memory copy used, so a future pin bump that fixes it upstream silently stops shimming |
| `sh:ignoredProperties` on a shape whose `sh:closed` is commented out | 6 node shapes | the orphan triple is removed from the shapes graph. Per the SHACL spec it constrains nothing without `sh:closed`, so this is semantics-preserving |

---

## 3. Namespaces

Every IPTC-owned IRI below was **copied from the pinned artefacts**, not typed
from memory, and `tools/iptc/context.py` re-asserts each one against the vendored
bytes on every run. Editing a value without editing the pin fails that check.

### 3.1 Required

| Prefix | IRI | Source of truth |
|---|---|---|
| `sport` | `https://sportschema.org/ontologies/main/` | `tools/prefixes.ttl`, every ontology header |
| `spstat` | `https://sportschema.org/ontologies/corestatistics/` | pinned |
| `spsocstat` | `https://sportschema.org/ontologies/soccer/` | pinned |
| `sptenstat` | `https://sportschema.org/ontologies/tennis/` | pinned |
| `spamfstat` | `https://sportschema.org/ontologies/american-football/` | pinned |
| `spbblstat` | `https://sportschema.org/ontologies/baseball/` | pinned |
| `spbkbstat` | `https://sportschema.org/ontologies/basketball/` | pinned |
| `spmcrstat` | `https://sportschema.org/ontologies/motor-racing/` | pinned |
| `sprgxstat` | `https://sportschema.org/ontologies/rugby/` | pinned |
| `spvolstat` | `https://sportschema.org/ontologies/volleyball/` | pinned |
| `spespstat` | `https://sportschema.org/ontologies/esports/` | pinned |
| `spgolf` | `https://sportschema.org/ontologies/golf/` | pinned |
| `spfacet` | `https://sportschema.org/ontologies/sport-facets/` | pinned |
| `rdf` | `http://www.w3.org/1999/02/22-rdf-syntax-ns#` | W3C |
| `rdfs` | `http://www.w3.org/2000/01/rdf-schema#` | W3C |
| `xsd` | `http://www.w3.org/2001/XMLSchema#` | W3C |
| `skos` | `http://www.w3.org/2004/02/skos/core#` | W3C |
| `schema` | `https://schema.org/` | schema.org |
| `prov` | `http://www.w3.org/ns/prov#` | W3C PROV-O |
| `machina` | `https://machina.gg/ns/sport/1.0/` | **Machina extension** |

`rdf`/`rdfs`/`xsd`/`skos`/`schema`/`prov` are stated explicitly rather than
assumed: a serializer that omits them emits terms that expand to nothing. `prov`
is present because Machina graphs carry provenance; it is not part of IPTC Sport
Schema.

### 3.2 Spellings that were verified rather than guessed

These are the ones a plausible-looking guess gets wrong.

- Baseball is **`spbblstat`**, not `spbstat` or `spbasestat`.
- Motor racing is **`spmcrstat`**, not `spmotorstat`.
- Facets are **`spfacet`** and the IRI path segment is **`sport-facets`**.
- Upstream binds golf under **two** names for one IRI: `spgolf` (in
  `ontologies/iptc-sport-golf.ttl` and the SHACL) and `spgolstat` (in
  `ontologies/iptc-sport-ontology.ttl`). The shared context reproduces both so
  either upstream spelling round-trips. **Machina serializers emit `spgolf`.**
- Upstream's prefix for schema.org is **`schemaorg`**, not `schema`. The shared
  context binds both names to `https://schema.org/` so legacy in-repo payloads
  using `schema:` keep expanding to identical IRIs. The IRI carries the meaning;
  the short name does not.
- The soccer action-type vocabulary prefix is **`spsocactiontype`** while its IRI
  path segment is **`spsocaction`**. They differ. Keying any check on the prefix
  *name* misses the real in-repo defect, where mappings emit `spsocaction:` as a
  value prefix that nothing binds.

### 3.3 Controlled-vocabulary namespaces

All 17 pinned schemes live under `http://cv.iptc.org/newscodes/<scheme>/`:
`asportfacetvalue`, `mediatopic`, `spactionclass`, `spcompetitionscope`, `spct`,
`speventoutcome`, `speventoutcometype`, `speventstatus`, `spgolholetype`,
`sphorposition`, `spichposition`, `spplayerstatus`, `spresulteffect`,
`spscoreunits`, `spsocposition`, `sptournamentform`, `sptournamentphase`.

---

## 4. Supported classes

A supported `sport_schema_graph` document describes resources drawn from this set,
and only from this set. Every name is declared by the pinned ontologies.

| Class | When it appears |
|---|---|
| `sport:Competition` | always |
| `sport:CompetitionPhase` | when the provider supplies a season, stage, round, group or matchday |
| `sport:Event` | always |
| `sport:Site` | when the provider supplies venue data |
| `sport:Team` | for each team competitor |
| `sport:Athlete` | for each individual competitor or named participant |
| `sport:TeamParticipation` | one per participating team |
| `sport:IndividualParticipation` | one per participating individual |
| `sport:Action` | one per notable in-event action the provider supplies |
| `sport:IndividualMembership` / `sport:TeamMembership` | when the provider supplies roster or club membership |
| `sport:Official`, `sport:OfficialParticipation` | when the provider supplies officials |
| `sport:Club`, `sport:GoverningBody`, `sport:Associate`, `sport:AssociateMembership`, `sport:AssociateParticipation`, `sport:CompetitorParticipation`, `sport:ParticipationSplit` | permitted; not required by any current mapping |

### 4.1 Classes the repository currently emits that do not exist in IPTC 1.1

Every one of these must disappear from the `sport:` namespace in PR 2. The
replacement column is the pinned official term.

| Currently emitted | Status | Use instead |
|---|---|---|
| `sport:Venue` | not an IPTC term | `sport:Site` |
| `sport:Season` | not an IPTC term | `sport:CompetitionPhase` |
| `sport:Stage`, `sport:Round`, `sport:Category` | not IPTC terms | `sport:CompetitionPhase` |
| `sport:Player` | not an IPTC term | `sport:Athlete` |
| `sport:Competitor` | not an IPTC term | `sport:Team` or `sport:Athlete` |
| `sport:Sport` | not an IPTC term | a `medtop:` NewsCode on `sport:sport` |
| `sport:Statistic`, `sport:TeamStatistics`, `sport:PlayerStatistics`, `sport:GameStatistics` | not IPTC terms | statistics are properties on a Participation, from `spstat:` / `sp*stat:` |
| `sport:BroadcastChannel` | not an IPTC term | `machina:` or `event_view` |
| `sport:IdentityCrosswalk` | not an IPTC term | `machina:` |
| `sport:SportEvent` | not an IPTC term (a legacy in-repo spelling) | `sport:Event` |

---

## 5. Properties

### 5.1 Mandatory

**On every document**

| Requirement | Rule |
|---|---|
| exactly one `@context` | at document level, being the shared context of §3, by value or by reference. **Not** a nested per-node context. |
| exactly one `@graph` | resources are siblings inside it |

**Per resource**

| Class | Mandatory |
|---|---|
| all | `@id` (§7), `@type`, `rdfs:label` |
| `sport:Event` | `sport:eventInCompetition`, `sport:startDateTime`, `sport:eventStatus`, at least two `sport:participation` |
| `sport:Competition` | `sport:sport` (a `medtop:` NewsCode), `sport:competitionType` (an `spct:` NewsCode) |
| `sport:CompetitionPhase` | `sport:phaseInCompetition` |
| `sport:TeamParticipation` | `sport:participationBy`, `sport:alignment` |
| `sport:IndividualParticipation` | `sport:participationBy` |
| `sport:Action` | `sport:actionInEvent`, `sport:class` (an `spactionclass:` NewsCode) |
| `sport:IndividualMembership` | `sport:member`, `sport:membershipOf` |

### 5.2 Optional

Everything else the pinned ontologies declare, **emitted only when the provider
supplies it**: `sport:eventInCompetitionPhase`, `sport:location`,
`sport:endDateTime`, `sport:eventOutcomeType`, `sport:attendance`, `sport:score`,
`sport:eventOutcome`, `sport:positionEvent`, `sport:playerStatus`,
`sport:minutesElapsed`, `sport:periodValue`, `sport:actionDateTime`,
`sport:actionType`, `sport:comment`, `sport:uniformNumber`, `sport:parent`, and
the `spstat:` / `sp*stat:` statistic properties.

### 5.3 Properties the repository currently emits that do not exist in IPTC 1.1

| Currently emitted | Use instead |
|---|---|
| `sport:competitors` (plural, inline array) | `sport:participation` → `sport:TeamParticipation` → `sport:participationBy` |
| `sport:competitor` (singular, the other legacy in-repo spelling) | same |
| `sport:status`, `sport:matchStatus` | `sport:eventStatus` with an `speventstatus:` NewsCode |
| `schema:startDate` on an Event | `sport:startDateTime` |
| `sport:startDate` on an Event | `sport:startDateTime`. **`sport:startDate` is not in `sport:EventShape`, and that shape is `sh:closed`, so it is an official SHACL violation on an Event.** |
| `sport:qualifier` | `sport:alignment` |
| `sport:homeScore`, `sport:awayScore`, `sport:halfTime`, `sport:penalties`, `sport:aggregate` | `sport:score` on each Participation, plus per-phase Participations |
| `sport:label` | `rdfs:label` |
| `sport:year`, `sport:season` | `sport:CompetitionPhase` with `rdfs:label` |
| `sport:venue` | `sport:location` → `sport:Site` |
| `sport:jerseyNumber`, `sport:shirtNumber` | `sport:uniformNumber` on a Membership |
| `sport:position` | `sport:positionEvent` with an `spsocposition:` NewsCode |
| `sport:participation` used as an inline object | keep the property; make the value a node reference |
| everything else in §12's leak table | `machina:` or `event_view` |

### 5.4 The official shapes are closed, and that constrains extensions

`sport:EventShape`, `sport:TeamShape`, `sport:AthleteShape`, `sport:SiteShape` and
others declare `sh:closed true`. A `machina:`-namespaced property attached
**directly** to a `sport:Team` therefore fails the official SHACL with
`ClosedConstraintComponent` — the extension namespace is not an escape hatch from
a closed shape.

**Normative rule.** A resource whose `@type` is an official `sport:` class carries
**only** official properties. Machina extension properties live on a separate
`machina:`-typed resource that references the official resource by `@id`.

```jsonc
// WRONG. sport:TeamShape is sh:closed; this fails the official SHACL.
{ "@id": "<Team id>", "@type": "sport:Team", "machina:providerId": "9001" }

// RIGHT. A machina:-typed resource points at the official one.
{ "@id": "<Team id>", "@type": "sport:Team", "rdfs:label": "..." },
{ "@id": "<ProviderIdentifier id>", "@type": "machina:ProviderIdentifier",
  "machina:identifies": { "@id": "<Team id>" },
  "machina:providerNamespace": "api-football",
  "machina:providerId": "9001" }
```

`tools/iptc/fixtures/conforming/machina-profile-conforming-minimal.json`
demonstrates the pattern and is the shape PR 2 is aiming at.

---

## 6. Provider identifier policy

Provider identifiers are **evidence attached to a Machina identity**, never the
identity.

1. A resource `@id` is a Machina identifier (§7). It is never a provider
   identifier and never a provider URN.
2. Every provider identifier appears as a `machina:ProviderIdentifier` resource
   carrying `machina:identifies`, `machina:providerNamespace` and
   `machina:providerId`, plus optional `machina:resolutionMethod`,
   `machina:confidence`, `machina:validFrom`, `machina:validTo`.
3. A provider identifier is **never** the value of an official `sport:` property,
   and a provider field name is **never** a `sport:` term. This is gate 4.
4. Raw provider payloads live in `event_view` or in separate source documents.
   They do not travel inside `sport_schema_graph`.
5. Existing World Cup URNs of the form `urn:machina:sport:soccer:event:...` remain
   resolvable throughout. They are recorded as `machina:legacyMachinaUrn`, not
   silently reinterpreted. PR 1 changes none of them.

---

## 7. Identifiers

1. **Absolute IRIs only.** No relative IRIs, no blank nodes for any resource in
   §4. A blank node is not addressable, so no consumer can reference it.
2. **Deterministic.** Regenerating the same canonical record yields byte-identical
   `@id` values.
3. **Scoped.** Two providers describing one fixture must not mint colliding
   identifiers, and one provider must not mint the same identifier for two
   fixtures.
4. **Not derived from mutable attributes.** Not from display names, dates,
   countries, participant slugs or home/away roles. Why: a correction or a
   postponement re-mints the identity, and two fixtures between the same pair
   collide. The current generic path
   (`urn:custom:event:La-Liga:Espanyol:Atletico-Madrid`) is exactly this hazard.
5. **Unique within a document.** Duplicate `@id` is gate 3 and a hard failure. A
   bare `{"@id": ...}` is a *reference*, not a second description, and is not a
   duplicate.
6. **Form.** An opaque, collision-free identifier minted by the canonical ID
   generator, which is owned by the Client API. Serializers and templates do not
   mint identifiers.

   A serializer therefore takes an **injected resolver**, `id_resolver(kind,
   *parts) -> str`, and calls it. It never contains minting logic, so the Client
   API generator can be swapped in later with no serializer change.

   Until that generator exists, the resolver of record is a **provider-scoped
   deterministic surrogate**: `urn:machina:sports:{kind}:x{32-hex}`, where the
   hex is a digest over an identity tuple whose first element is the provider
   namespace. Two consequences, stated rather than glossed:

   - the leading `x` is a permanent marker that the identifier is a surrogate, so
     it can never be mistaken for a canonical Client-API identity;
   - because the tuple is provider-scoped, **two providers observing one fixture
     mint two different identifiers**. That is honest, not a defect: this profile
     does not claim cross-provider identity resolution. The crosswalk in §6
     records the evidence linking them and stops there. Collapsing them is the
     canonical identity service's job.

---

## 8. Datatypes and dates

| Property class | Datatype | Form |
|---|---|---|
| `sport:startDateTime`, `sport:endDateTime`, `sport:actionDateTime` | `xsd:dateTime` | `{"@value": "2026-03-01T20:00:00+00:00", "@type": "xsd:dateTime"}` |
| `sport:startDate`, `sport:endDate`, `sport:dateOfBirth` | `xsd:date` | `YYYY-MM-DD` |
| statistics, scores, counts | `xsd:string` | the pinned shapes specify `sh:datatype xsd:string` for these, including `sport:attendance` and `sport:score`. Emit strings. Do not "improve" this to integers: it is an official SHACL violation. |
| controlled-vocabulary values | node reference | §9 |

**Date rules.** An instant carries an explicit UTC offset. A date without a time
is `xsd:date` and never a zero-filled `xsd:dateTime`. A provider's local date and
local time are `machina:` or `event_view` values, not IPTC properties. A time that
is a match clock reading rather than an instant (`"23"`, `"67+2"`) is
`sport:minutesElapsed`, never `sport:actionDateTime`.

---

## 9. NewsCode mapping

**A NewsCode is a node reference, never a bare string.** A string value expands to
a literal, and no consumer can follow a literal to a concept. This is currently
wrong in every mapping in the repository.

```jsonc
"sport:eventStatus": "closed"                                     // WRONG: a literal
"sport:eventStatus": "http://cv.iptc.org/newscodes/..."           // WRONG: still a literal
"sport:eventStatus": { "@id": "speventstatus:post-event" }        // RIGHT
```

| Machina concept | Scheme | Pinned |
|---|---|---|
| event status | `speventstatus:` | yes |
| event outcome / outcome type | `speventoutcome:`, `speventoutcometype:` | yes |
| competition type | `spct:` | yes |
| competition scope | `spcompetitionscope:` | yes |
| tournament form / phase | `sptournamentform:`, `sptournamentphase:` | yes |
| action class | `spactionclass:` | yes |
| player status | `spplayerstatus:` | yes |
| soccer position | `spsocposition:` | yes |
| sport | `medtop:` | yes |
| score units, result effect | `spscoreunits:`, `spresulteffect:` | yes |
| **soccer action type** | `spsocactiontype:` (path segment `spsocaction`) | **no — see below** |
| soccer role, esports action, per-sport action/result schemes | `spsocrole:`, `spesaction:`, … | **no** |

### 9.1 Status mapping, worked

The current mappings pass provider status codes straight through. The correction:

| API-Football | Sportradar | Opta | `speventstatus:` |
|---|---|---|---|
| `NS`, `TBD` | `not_started` | `Fixture` | `pre-event` |
| `1H`, `2H`, `ET`, `P`, `LIVE` | `live`, `inprogress` | `Playing` | `mid-event` |
| `HT`, `BT` | `halftime` | — | `intermission` |
| `FT`, `AET`, `PEN` | `closed`, `ended` | `Played` | `post-event` |
| `PST` | `postponed` | `Postponed` | `postponed` |
| `CANC` | `cancelled` | `Cancelled` | `canceled` (note the single `l`, as upstream spells it) |
| `SUSP` | `suspended` | `Suspended` | `suspended` |
| `ABD` | `abandoned` | `Abandoned` | `halted` |
| `AWD`, `WO` | — | `Awarded` | `forfeited` |

A provider status with no defensible mapping is **omitted** from
`sport:eventStatus` and preserved verbatim in `event_view`. It is never guessed and
never defaulted.

### 9.2 The `spsocaction` gap, stated plainly

`tools/prefixes.ttl` binds `spsocactiontype:` and the pinned SHACL references the
scheme, but **no `vocabularies/spsocaction.ttl` exists at the pinned commit.** The
same is true of `spsocrole`, `spesaction` and the other per-sport action and
result schemes.

Consequence: soccer action-type codes **cannot be validated offline against a
pinned TTL**. The harness reports them as `unverifiable` — a third outcome,
distinct from valid and from invalid. `unverifiable` is never promoted to valid and
never counted as invalid. No substitute code list is invented anywhere in this
repository.

**Normative rule: layer 4 fails closed on `unverifiable`.** §9 requires every
NewsCode to be *provably* present in a pinned vocabulary, so a value that nothing
in the pin can check does not conform, and `validate_vocabularies.py` exits
non-zero on it. Missing evidence is not evidence of correctness. The category and
its count stay separate from `invalid` because the two need different fixes: an
invalid code is a mapping bug to correct here, while an unverifiable one is
resolved by a pin bump once upstream publishes the scheme.

Serializers must still emit them as node references under `spsocactiontype:`. A
value under a prefix that no context in scope binds — which is what
`spsocaction:score-change` currently is — is a gate 2 failure, because it resolves
to nothing at all.

---

## 10. Graph rules

1. **One document, one `@context`, one `@graph`.** Nested per-node contexts are
   forbidden: they make one document expand under two vocabularies. The Opta
   mapping currently does this, with a different `sport:` IRI inside
   `sport:timeline` than at the top of the same document.
2. **Resources are siblings, not a tree.** Where the provider supplies the
   information, Event, Competition, CompetitionPhase, Site, Team/Athlete,
   Participation, Action and Membership are distinct resources with distinct
   `@id`s, at the top level of `@graph`, referring to one another by `@id`.
   Flattening them into one nested Event node is a profile violation.
3. **References are `{"@id": ...}`.** An inline object with `@type` inside another
   resource is a nested resource and a violation.
4. **No cross-document duplication.** One `@id` is described in exactly one place
   in one document.
5. **Machina operational blocks do not belong in the graph.** `metadata`,
   `version_control`, `provider_ids`, `title`, `stats`, `lastUpdated`,
   `commentaries`, and bare `name`/`type`/`competitor` keys are `machina:` terms or
   `event_view` fields. A key that is neither a JSON-LD keyword nor defined by a
   context in scope is silently dropped on expansion, which is worse than being
   rejected: the value is simply lost.

---

## 11. Omission and null rules

Omission beats fabrication. A missing field is a fact a consumer can handle; a
fabricated default is a false assertion that looks like data.

**Forbidden**

- `null` as a property value.
- `""` as a stand-in for an unsupplied value.
- Placeholder strings: `"unknown"`, `"Unknown"`, `"UNK"`, `"TBD"`, `"N/A"`,
  `"Unknown Player"`, `"Unknown Venue"`, `"Unknown City"`, `"Unknown Country"`,
  `"Unknown Competition"`, `"Unknown Season"`, `"Unknown Round"`,
  `"Unknown Phase"`, `"Unknown Category"`, `"Unknown Group"`,
  `"Unknown Channel"`, `"Unknown Title"`.
- A stub resource with an identifier and no facts — for example the generic path's
  `urn:custom:venue:unknown` named `"Unknown"`.
- `0` where the provider supplied nothing. Zero is a measurement.

**Required**

- Omit the property.
- Omit the whole resource if the provider supplies no facts about it.
- Where absence is itself meaningful, say so in `event_view`, not by fabricating an
  IPTC value.

### 11.1 One acknowledged migration hazard

`connectors/sportradar-mlb/mappings/iptc-sport-event.yml` emits `sport:score` with
explicit `null`s **deliberately** — its own comment records that `schedule.json`
carries no runs and that `sportradar-mlb-sync-results` later merges them in, so a
downstream reader depends on the key existing. Those nulls are load-bearing today.

This is exactly why the migration rule in §14 is add-then-migrate-then-deprecate
rather than a flag day. PR 2 emits the corrected graph alongside the legacy shape;
the null-bearing legacy output is removed only after
`sportradar-mlb-sync-results` and `extract-team-stats` read the corrected one.

### 11.2 `event_view`

A compact, stable, non-RDF projection, sized for the operations that dominate
Machina traffic: reading a fixture, its participants, its status, its notable
actions. It is where provider raw values live when they are operationally useful,
and where Machina convenience shapes live so they never need smuggling into
`sport:`.

```jsonc
{
  "event_view": {
    "event_id": "<canonical Machina id>",
    "status": "<canonical status value>",
    "start_time": "<ISO 8601>",
    "competition": { "id": "<canonical id>", "name": "<display>" },
    "participants": [
      { "role": "home", "id": "<canonical id>", "name": "<display>" },
      { "role": "away", "id": "<canonical id>", "name": "<display>" }
    ],
    "provider": { "namespace": "<provider>", "raw": { } }
  }
}
```

No `@context`, no `@graph`, no `sport:` terms. **PR 1 does not add `event_view`
production output.** This section fixes the contract so PR 2 can implement it.

---

## 12. The Machina extension namespace

`machina:` = `https://machina.gg/ns/sport/1.0/`

**Anything IPTC 1.1 does not define goes here or into `event_view`. Never under
`sport:`, for any reason, including "IPTC will probably add it later."**

An invented `sport:` term is worse than a missing field: it looks standard, it
survives casual review, and it fails only when an external consumer tries to
reason over it.

Extensions are subject to §5.4 — they live on `machina:`-typed resources, not as
extra properties on closed official shapes.

Initial `machina:` vocabulary: `machina:ProviderIdentifier`,
`machina:identifies`, `machina:providerNamespace`, `machina:providerId`,
`machina:resolutionMethod`, `machina:confidence`, `machina:validFrom`,
`machina:validTo`, `machina:legacyMachinaUrn`, `machina:canonicalRevision`,
`machina:mappingVersion`, `machina:sourceRef`.

Added in `machina-iptc-profile/1.1`, to carry observation provenance as a
resource in the graph rather than only as an envelope block:
`machina:ObservationProvenance`, `machina:describes`, `machina:observedAt`,
`machina:adapterVersion`, `machina:serializerVersion`, `machina:rightsClass`,
`machina:evidence`.

`machina:evidence` is where a provider's own detail survives when no pinned
NewsCode can carry it — a soccer action type, for instance (§9.2). It is a
`machina:` property on a `machina:`-typed resource, never an extra property on a
closed official shape.

### 12.1 Provider-specific properties currently in the IPTC namespace

Terms currently emitted under `sport:` that are transliterations of a provider's
own field names. All must move to `machina:` or `event_view` in PR 2. The
authoritative list is `tools/iptc/rules/provider-leak-terms.json`, which records
which mapping each attribution came from.

| Provider | Examples |
|---|---|
| API-Football | `sport:halfTime`, `sport:jerseyNumber`, `sport:rating`, `sport:captain`, `sport:substitute`, `sport:minutesPlayed` |
| Sportradar soccer | `sport:matchStatus`, `sport:channels`, `sport:channelName`, `sport:scoreMethod`, `sport:shootoutHomeScore`, `sport:cardType`, `sport:statType`, `sport:statValue`, `sport:statLabel`, `sport:aggregate` |
| Sportradar NFL | `sport:quarter`, `sport:clock`, `sport:broadcast`, `sport:weather`, `sport:firstDowns`, `sport:touchdowns`, `sport:passing`, `sport:rushing`, `sport:receiving`, `sport:defense`, `sport:fieldGoals`, `sport:kickReturns` |
| Sportradar MLB | `sport:market`, `sport:gameNumber`, `sport:doubleHeader`, `sport:probablePitcher` |
| Sportradar tennis | `sport:bestOf`, `sport:seed`, `sport:bracketNumber`, `sport:coverage`, `sport:playByPlay`, `sport:enhancedStats`, `sport:gameInfo`, `sport:eventDetails`, `sport:seasonContext`, `sport:competitionContext` |
| Stats Perform / Opta | `sport:localDate`, `sport:localTime`, `sport:coverageLevel`, `sport:var`, `sport:week`, `sport:knownName`, `sport:competitionCode`, `sport:clubId`, `sport:shirtNumber`, `sport:matchInfo`, `sport:timeline` |
| American football | `sport:gameInfo`, `sport:halfTime` |

**Gates 1 and 4 overlap by construction.** A provider field name under `sport:` is
both an undeclared term and an attributable leak, and is counted once in each
column because the two columns answer different questions. Never add them
together.

Generically-named invented terms — `sport:homeScore`, `sport:qualifier`,
`sport:status`, `sport:label`, `sport:year` — are counted by gate 1 alone. They are
invented, not provider-branded.

---

## 13. Validation and the four gates

| Layer | Command | Proves |
|---|---|---|
| 1 JSON-LD expansion / RDF parse | `tools/iptc/validate_graph.py` | valid JSON-LD, parseable RDF |
| 2 official IPTC SHACL | `tools/iptc/validate_graph.py` | conforms to the pinned shapes |
| 3 Machina profile | `tools/iptc/validate_graph.py` | this document |
| 4 controlled vocabulary | `tools/iptc/validate_vocabularies.py` | every code is provably present in a pinned vocabulary; `invalid`, undeclared-prefix and `unverifiable` all fail |

| Gate | Command | Target |
|---|---|---|
| unknown `sport:` terms | `validate_terms.py` | 0 |
| invalid controlled-vocabulary values | `validate_vocabularies.py` | 0 |
| duplicate resource IDs | `validate_graph.py` | 0 |
| provider properties in the IPTC namespace | `validate_terms.py` | 0 |

Layer 2 reproduces upstream's own procedure: the merged ontology **and every
vocabulary** are merged into the data graph before validating, because the shapes
depend on `rdfs:subClassOf` and `skos:inScheme`.

**A layer-1 document that would make the processor fetch a context is rejected
before the processor sees it.** A string `@context`, a string inside a `@context`
array, a scoped context given as a string, and `@import` inside a context are all
outbound requests whose result would silently decide what every term in the
document means. §5.1 requires exactly one inline document-level context, so the
harness refuses the rest rather than resolving it. This is what makes "validated
offline against pinned bytes" a structural property instead of an assumption.

**A layer-2 pass over zero official-class instances is `vacuous`, not a pass.**
The harness counts official-class instances and fails layer 2 when the count is
zero. This is normative: a document that instantiates no IPTC class cannot be
claimed IPTC-conformant, whatever a SHACL processor says about an empty target set.

---

## 14. Backward compatibility

1. **PR 1 changes no production mapping output.** No mapping YAML, no output
   shape, no selector, no consumer field path, no World Cup response envelope.
2. **Add, then migrate, then deprecate.** Corrected outputs land alongside the
   existing shapes. Consumers move. Only then are legacy fields deprecated.
3. **Legacy outputs are not removed inside this work at all.** Early removal is
   explicitly out of scope.
4. **World Cup compatibility holds throughout.** `/world-cup/v1` routes stay
   resolvable, existing URNs stay resolvable, and the response envelope of
   `worldcup-iptc-event-to-api-response` is unchanged by PR 1. The World Cup
   corpus is the regression baseline, not a production target.
5. **Compatibility projections are derived from the corrected graph**, never
   maintained as an independent legacy code path. An independent path is a second
   source of truth and would reintroduce exactly the drift being removed.
6. **Downstream emitters outside this repository are not changed.** The legacy
   `sport:SportEvent` / `sport:competitor` / `sport:eventStatus` shape is one of the
   two conflicting shapes in use today. The consumer migration documents what it
   needs; touching those IPTC types here without correcting them would ratify the
   wrong shape.

---

## 15. Versioning

- This profile is `machina-iptc-profile/1.1`, and every conformance claim cites
  both the profile version and the upstream pin.
- **`1` → `1.1`**, reviewed and approved by the profile owner, is a minor bump
  under the rule below. It *adds* the `machina:` observation terms in §12 and the
  injected-resolver rule in §7.6. It tightens nothing already emitted and changes
  the meaning of no already-conforming document: a document that conformed to
  `machina-iptc-profile/1` still conforms to `1.1`. The upstream pin is
  unchanged, so this is a profile bump and not a pin bump.
- **Bumping the upstream pin** means: change `UPSTREAM_COMMIT`, re-vendor the
  bytes, regenerate `upstream-commit.json`, re-run `--verify-pin`, regenerate the
  baseline audit, and record in `UPSTREAM.md` whether the two known upstream
  defects still need shimming. A pin bump is a reviewed act, never a range bump.
- **Adding a profile rule** is a minor bump: `machina-iptc-profile/1.n`. It may
  tighten what is emitted but must not change the meaning of an already-conforming
  document.
- **Removing or reinterpreting a rule** is a major bump and requires a new RFC.
- **A `machina:` term is never silently repurposed.** Its namespace carries its
  own version (`.../sport/1.0/`); a breaking change to an extension term means a
  new extension namespace, not a redefinition.
- The shared context is versioned by filename. `iptc-sport-schema-1.1.context.jsonld`
  is bound to Sport Schema 1.1; a 1.2 target gets its own file, and both may exist
  during a migration window.

---

## 16. What this RFC does not authorise

This RFC is a serialization profile. It authorises nothing beyond it. In
particular, and restated so it is not lost:

- no new storage engine, and no migration of the canonical model out of MongoDB;
- no new frontend, API surface or response envelope;
- no removal of a legacy output, and no consumer migration, inside PR 1;
- no `event_view` production output inside PR 1;
- no change to emitters outside this repository;
- no new product surface built on top of the graph. Anything of that kind is a
  separate decision, taken separately, and is not implied by adopting this
  profile.
