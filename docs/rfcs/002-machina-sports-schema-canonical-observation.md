# RFC 002 — Machina Sports Schema: the canonical observation

| | |
|---|---|
| **Status** | Accepted for PR 2. |
| **Depends on** | RFC 001 (`machina-iptc-profile/1.1`), which stays normative for everything this document does not restate |
| **External name** | Machina Sports Schema |
| **Input contract** | `canonical-observation/1` |
| **Output contract** | `machina-sports-schema/1` |
| **Profile claimed** | `machina-iptc-profile/1.1` |
| **Pin** | `https://github.com/iptc/sport-schema` @ `0e77bf8678f3702fe81c28673bede35efe47d633`, Sport Schema 1.1 |
| **Executable form** | `tools/iptc/canonical/` |

---

## 0. What this document does not claim

RFC 001 §0 drew one boundary. This document draws a second, and it is the more
easily lost of the two.

**A canonical observation is not a canonical record.** It is *one provider's
observation of one event*, normalised to Machina concepts and carrying its own
provenance and rights class. It is not the durable truth about that event, it is
not reconciled against any other provider, and nothing in this phase resolves
cross-provider identity.

Three things follow, and they are the ones a reader is most likely to assume
away:

1. **Two providers observing one fixture produce two observations and two
   different Machina identifiers.** See §6. The crosswalk in §5 records the
   evidence that links them. It does not collapse them, and no code in this phase
   does.
2. **There is no canonical ID service yet.** Identifiers here are provider-scoped
   deterministic surrogates, marked as such in their own lexical form, minted
   outside the serializer by an injected resolver.
3. **There is no canonical database.** Nothing here writes to MongoDB, defines a
   collection, or implies a migration.

Anything that reads this document as "Machina now has a canonical sports
database" has read it wrong.

---

## 1. The canonical observation

`SCHEMA_VERSION = "canonical-observation/1"`. Plain JSON, no JSON-LD, no
`sport:` term. It is the single input to serialization: every serializer reads
the observation and nothing else.

Validated by `validate_observation(document) -> list[str]`. An empty list means
valid. Validation is **hand-rolled and dependency-free** — neither repository
carries `jsonschema`, and adding a dependency to a published zero-dependency
package is not justified by a key walk.

```jsonc
{
  "schema_version": "canonical-observation/1",
  "observation": {
    "provider":   { "namespace": "sports-skills/espn", "family": "open-data" },
    "observed_at": "2026-03-01T22:05:00+00:00",
    "adapter":    { "name": "sports_skills.canonical.adapters.football", "version": "0.31.0" },
    "rights":     { "data_class": "public-non-commercial", "prototype_only": true,
                    "commercial_use": false },
    "sport":      { "medtop": "20001065", "key": "soccer" },
    "competition":{ "provider_id": "eng.1", "name": "Synthetic Premier Division",
                    "type": "recurring-competition",
                    "season": { "provider_id": "eng.1-2026", "name": "2026" } },
    "phase":      { "provider_id": "eng.1-2026-27", "name": "Matchday 27" },
    "site":       { "provider_id": "9101", "name": "Synthetic Home Ground",
                    "city": "Synthetic City", "country": "SYN" },
    "event":      { "provider_id": "9001", "label": "Home United vs Away Town",
                    "start_time": "2026-03-01T20:00:00+00:00",
                    "status": "closed", "outcome_type": "regular",
                    "attendance": "60123",
                    "clock": { "minute": "90", "period": "2" } },
    "participants": [
      { "kind": "team", "provider_id": "9011", "name": "Synthetic Home United",
        "alignment": "home", "score": "2", "outcome": "win",
        "statistics": { "spsocstat:shotsTotal": "14" } },
      { "kind": "individual", "provider_id": "9021", "name": "Synthetic Scorer",
        "team_provider_id": "9011", "player_status": "starter", "position": "forward",
        "statistics": { "spsocstat:goalsTotal": "1" } }
    ],
    "memberships": [ { "individual_provider_id": "9021", "team_provider_id": "9011",
                       "uniform_number": "9" } ],
    "actions": [ { "ordinal": 1, "class": "score", "minute": "23", "period": "1",
                   "participant_provider_id": "9021", "label": "Goal",
                   "action_time": "2026-03-01T20:23:11+00:00" } ],
    "raw": { }
  }
}
```

### 1.1 Rules, all enforced by `validate_observation`

- **Required:** `provider.namespace`, `observed_at`, `sport.medtop`,
  `competition.provider_id`, `event.provider_id`, `event.start_time`,
  `event.status`, and **at least two participants**. A one-sided event is not an
  event; it is a partially-parsed payload.
- **`null`, `""` and every placeholder in `profile.PLACEHOLDER_VALUES` are
  errors**, at any depth. This is the whole point of validating the observation
  rather than the output: fabrication is caught in the *adapter*, where a human
  can see which provider field produced it, not in the serializer, where the
  provenance is already gone.
- **Every `statistics` key is a CURIE** whose local name appears in
  `official-property-names.json` (§4). An unknown one is an **error**, not a
  warning. A statistic nobody can resolve is not data.
- **Datetimes are validated for form**, including an explicit offset. A naive
  timestamp is ambiguous by an unknown number of hours and is rejected.
- **`observed_at` is an input**, never sampled. Nothing in this package reads the
  clock, the environment or the network, so the same observation always produces
  the same output.
- **`raw` never travels into `sport_schema_graph`.** It survives only in
  `event_view.provider.raw`.
- **No silent defaults, ever.** `validate_observation` does not repair, coerce,
  fill or normalise. It returns errors, and the caller fixes the adapter.

---

## 2. `sport_schema_graph`

`sport_schema_graph(observation, *, id_resolver) -> dict`.

One document-level `@context` — the shared context at
`agent-templates/iptc-mappings/contexts/iptc-sport-schema-1.1.context.jsonld`,
inlined **by value**. Never a string, never `@import`, never scoped or nested;
RFC 001 layer 1 rejects those before rdflib ever sees the document. One flat
`@graph` of sibling resources referencing each other by `@id`.

| Class | Cardinality | Mandatory properties |
|---|---|---|
| `sport:Competition` (recurring) | 1 | `rdfs:label`, `sport:sport`→`medtop:`, `sport:competitionType`→`spct:` |
| `sport:Competition` (season) | 0–1 | as above + `sport:parent` |
| `sport:CompetitionPhase` | 0–1 | `rdfs:label`, `sport:phaseInCompetition` |
| `sport:Site` | 0–1 | `rdfs:label` |
| `sport:Team` | 0–n | `rdfs:label` |
| `sport:Athlete` | 0–n | `rdfs:label` |
| `sport:Event` | 1 | `rdfs:label`, `sport:sport`, `sport:eventInCompetition`, `sport:startDateTime`, `sport:eventStatus`, ≥2 `sport:participation` |
| `sport:TeamParticipation` | 0–n | `rdfs:label`, `sport:participationBy`, `sport:alignment` |
| `sport:IndividualParticipation` | 0–n | `rdfs:label`, `sport:participationBy` |
| `sport:IndividualMembership` | 0–n | `rdfs:label`, `sport:member`, `sport:membershipOf` |
| `sport:Action` | 0–n | `rdfs:label`, `sport:actionInEvent`, `sport:class`→`spactionclass:` |
| `machina:ProviderIdentifier` | 0–n | `machina:identifies`, `machina:providerNamespace`, `machina:providerId` |
| `machina:ObservationProvenance` | 1 | `machina:describes`, `machina:providerNamespace`, `machina:observedAt` |

A resource is emitted **only when the observation supplies it**. Statistics
attach as `spstat:` / `sp*stat:` properties on a Participation, never as a
`sport:Statistic` resource. Emission order is fixed by the table so the output is
byte-stable.

Official shapes are `sh:closed` (RFC 001 §5.4), so no `machina:` property ever
appears on a `sport:`-typed resource. Machina facts live on `machina:`-typed
siblings.

---

## 3. `event_view`

`event_view(observation) -> dict`. No `@context`, no `@graph`, no `sport:` term,
no RDF. **Derived independently from the observation** — never from
`sport_schema_graph`. Two serializers reading one input is the property that lets
either be replaced without silently corrupting the other.

Absent facts are absent keys. `provider.raw` is the only place a provider payload
survives, and it is the escape hatch for everything IPTC cannot express: an
unmappable status, a soccer action type (§7), a provider's own clock string.

---

## 4. The official property allowlist

`tools/iptc/canonical/official-property-names.json` is **generated**, not
maintained: `python -m tools.iptc.canonical.export_official_terms` reads the
pinned ontologies and writes every official property local name.

`{"pin": <commit>, "target_version": "1.1", "local_names": [ … sorted … ]}`, two-
space indent, trailing newline. A test asserts the checked-in bytes equal what
the generator renders, so the file cannot drift from the pin it claims to come
from. Bumping the pin regenerates it; nobody edits it by hand.

It is vendored into `sports-skills` because `validate_observation` needs it there
and that package cannot import this repository.

---

## 5. Provenance and crosswalk

Provenance appears twice, deliberately, for two audiences: as an envelope block
for consumers reading JSON, and as one `machina:ObservationProvenance` resource
for consumers reading RDF. Same facts.

```jsonc
"provenance": {
  "provider":   { "namespace": "sports-skills/espn", "family": "open-data" },
  "adapter":    { "name": "…", "version": "0.31.0" },
  "serializer": { "name": "machina-iptc-serializer", "version": "1" },
  "profile":    "machina-iptc-profile/1.1",
  "upstream_pin": { "repository": "https://github.com/iptc/sport-schema",
                    "commit": "0e77bf8678f3702fe81c28673bede35efe47d633",
                    "target_version": "1.1" },
  "observed_at": "2026-03-01T22:05:00+00:00",
  "source_refs": [ { "kind": "endpoint-class", "value": "espn/summary",
                     "note": "endpoint class only; no URL, query or credential is recorded" } ],
  "rights": { "data_class": "public-non-commercial", "prototype_only": true,
              "commercial_use": false },
  "determinism": { "id_strategy": "provider-scoped-surrogate", "digest": "blake2b-128",
                   "canonical_id_service": "not-available-in-this-phase" }
}
```

`source_refs` records an **endpoint class, never a URL**. A URL is a
request-shaped artefact: it is how an API key, a licensed path or a customer
identifier ends up committed to a fixture file.

Provider identifiers are **evidence attached to a Machina identity, never the
identity**:

```jsonc
"provider_ids": [
  { "machina_id": "urn:machina:sports:team:x…", "entity_type": "team",
    "provider_namespace": "sports-skills/espn", "provider_id": "9011",
    "resolution_method": "provider-native", "confidence": 1.0,
    "evidence": "observation.participants[0].provider_id" }
]
```

`resolution_method` is one of `provider-native` (the provider stated it),
`ordinal-derived` (no stable provider ID; positional) or `declared` (supplied by
the caller). There is no fourth value and there is **no fuzzy matching in this
phase**.

---

## 6. Identifiers

`urn:machina:sports:{kind}:x{32-hex}`, the hex being `blake2b(digest_size=16)`
over the canonical JSON of an identity tuple whose first element is the provider
namespace.

| kind | identity tuple |
|---|---|
| `competition` | `(ns, "competition", competition.provider_id[, season.provider_id])` |
| `phase` | `(ns, "phase", competition.provider_id, season.provider_id, phase.provider_id)` |
| `site` / `team` / `athlete` | `(ns, kind, provider_id)` |
| `event` | `(ns, "event", event.provider_id)` |
| `participation` | `(ns, "participation", event.provider_id, participant.kind, participant.provider_id)` |
| `membership` | `(ns, "membership", individual_provider_id, team_provider_id)` |
| `action` | `(ns, "action", event.provider_id, ordinal)` |
| `provider-identifier` | `(ns, "provider-identifier", entity_kind, provider_id)` |
| `observation-provenance` | `(ns, "observation-provenance", event.provider_id)` |

Never derived from names, dates, countries, slugs or home/away roles (RFC 001
§7.4). The leading `x` marks the value a surrogate so it can never be mistaken
for a Client-API-minted canonical identifier, and the digest is opaque, so no
provider namespace token leaks into the identifier itself.

**The serializer does not mint.** It takes `id_resolver(kind, *parts) -> str`.
`ids.surrogate_resolver(namespace)` is a separate module the caller injects,
which keeps RFC 001 §7.6 literally true and lets a later phase swap in the real
generator with no serializer change.

**Known limitation, recorded here and in `provenance.determinism`:** action
identifiers are `ordinal-derived`. They are stable for a given payload, and a
provider that re-orders its action list re-mints them. Fixing that needs a stable
provider-side action identifier, which no provider in scope supplies.

---

## 7. Controlled vocabularies

Every NewsCode is a **node reference** — `{"@id": "speventstatus:post-event"}` —
never a bare string (RFC 001 §9).

`vocab.py` maps Machina concepts into pinned schemes only:
`speventstatus:`, `speventoutcome:`, `speventoutcometype:`, `spct:`,
`spactionclass:`, `spplayerstatus:`, `spsocposition:`.

Two rules make that mechanical rather than remembered:

1. A test asserts, for every entry in every table, that the scheme is pinned and
   that the concept IRI is present in it. An invented or misspelled code fails
   the suite; it does not reach a fixture.
2. **`spsocactiontype:` is not mapped at all.** `tools/prefixes.ttl` binds the
   prefix and the SHACL references the scheme, but no vocabulary TTL for it
   exists at the pinned commit, so layer 4 reports its values `unverifiable` and
   RFC 001 §9.2 makes `unverifiable` fail closed. Soccer action detail therefore
   goes into `spactionclass:` for the class, and the provider's own action type
   survives in `event_view` and `machina:evidence`. No substitute code list is
   invented anywhere.

An unmapped key **raises**; it is never defaulted. A provider status with no
defensible mapping is omitted from `sport:eventStatus` and preserved verbatim in
`event_view`.

---

## 8. Capability tiers

`capability_report(observation)` describes what a payload actually supports, so a
consumer can decide before it parses rather than after it fails.

```python
TIER_ORDER = ("core", "live", "advanced")
```

| Tier | Required | Optional |
|---|---|---|
| `core` | `event.identity`, `event.competition`, `event.participants`, `event.start_time`, `event.status`, `provenance` | `event.score`, `event.result` |
| `live` | `event.clock`, `event.period`, `event.actions` | `event.play_by_play`, `event.live_statistics` |
| `advanced` | `participant.player_statistics` | `event.coordinates`, `event.tracking`, `event.expected_metrics`, `event.lineups`, `event.formations` |

`tier` is the highest `T` in `TIER_ORDER` such that every tier up to and
including `T` has all of its required capabilities present. Tiers do not skip: an
observation with advanced statistics but no clock is `core`, because claiming
`advanced` would tell a consumer it can rely on live data it will not get.

One conditional rule, kept **out** of tier gating so that a legitimate pre-match
payload still reaches `core`: `event.score` MUST be present when `event.status`
is `in_progress` or `closed`. Otherwise `violations` gains
`score-absent-on-started-event` and the report is a failure.

`check_compatibility(capabilities, requires=(), optional=())` **fails closed**: a
capability name that is not in `ALL_CAPABILITIES` lands in
`unknown_capabilities` and forces `compatible: false`. A typo in a consumer's
`requires` must never read as satisfied — that is exactly the failure mode a
compatibility check exists to prevent. A missing *optional* capability is
reported and does not affect `compatible`; a missing *required* one does.

---

## 9. The output envelope

```jsonc
{ "machina_sports_schema": {
    "schema_version": "machina-sports-schema/1",
    "profile": "machina-iptc-profile/1.1",
    "sport_schema_graph": { "@context": {…}, "@graph": [ … ] },
    "event_view": { … },
    "provenance": { … },
    "provider_ids": [ … ],
    "capabilities": { … },
    "rights": { … } } }
```

`rights` is not decoration. An open-data adapter can only ever emit
`prototype_only: true` / `commercial_use: false`, and a consumer gated on
production rights must refuse such an envelope rather than downgrade quietly.

---

## 10. Vendoring

`sports-skills` is a published zero-dependency package and cannot import this
repository, so `observation.py`, `ids.py`, `capabilities.py`, `serialize.py` and
`official-property-names.json` are vendored **byte-exact**, not reimplemented.
Two reimplementations of one contract diverge; the only question is when.

Those modules are therefore **Python 3.9-compatible and standard-library only**,
and must not import `tools.*`. `export_official_terms.py` may — it is a
generator, it runs only in this repository, and it is not vendored.

Two consequences a vendoring reviewer has to act on:

- A vendored module may use a package-relative import (`from . import
  SCHEMA_VERSION`), so the receiving `_vendored/__init__.py` must define the
  version constants in §0. If it does not, the import fails loudly at load time
  rather than producing a subtly mislabelled envelope.
- `PLACEHOLDERS` in `observation.py` is a second copy of
  `profile.PLACEHOLDER_VALUES`, forced by the same boundary. A test in this
  repository asserts the two are equal; that assertion is the only thing keeping
  them from drifting, so it is not optional.

Hash manifests on both sides catch a file changing without the manifest being
regenerated. Cross-repo *equality* of the two manifests is a **stated review
check, not an automated one**: neither CI can reach the other repository, and
claiming otherwise would be the sort of unearned assurance this program exists to
avoid.

---

## 11. What this RFC does not authorise

- no mapping YAML change, no connector workflow change, no install manifest
  change, and no consumer migration;
- no canonical database, collection, or identity service;
- no cross-provider identity resolution, and no fuzzy matching;
- no live provider call, no credential, and no network access in any code path
  described here;
- no change to `sports-skills` native output, which stays byte-identical by
  default;
- no product surface built on top of the envelope.
