# RFC 002 — Machina Sports Schema: the canonical observation

| | |
|---|---|
| **Status** | Accepted for PR 2. |
| **Depends on** | RFC 001 (`machina-iptc-profile/1.1`), which stays normative for everything this document does not restate |
| **External name** | Machina Sports Schema |
| **Input contract** | `canonical-observation/1.1` (§12); `canonical-observation/1` still read, never emitted |
| **Output contract** | `machina-sports-schema/1` |
| **Profile claimed** | `machina-iptc-profile/1.2` |
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

`SCHEMA_VERSION = "canonical-observation/1.1"`, and
`ACCEPTED_SCHEMA_VERSIONS` is the closed set of identifiers a reader admits —
`canonical-observation/1` alongside it, for existing exact documents only (§12.3).
Plain JSON, no JSON-LD, no `sport:` term. It is the single input to
serialization: every serializer reads the observation and nothing else.

Validated by `validate_observation(document) -> list[str]`. An empty list means
valid. Validation is **hand-rolled and dependency-free** — neither repository
carries `jsonschema`, and adding a dependency to a published zero-dependency
package is not justified by a key walk.

```jsonc
{
  "schema_version": "canonical-observation/1.1",
  "observation": {
    "provider":   { "namespace": "sports-skills/espn", "family": "open-data" },
    "observed_at": "2026-03-01T22:05:00+00:00",
    "adapter":    { "name": "sports_skills.canonical.adapters.football", "version": "0.31.0",
                    "source_refs": [ { "kind": "endpoint-class", "value": "espn/summary" } ] },
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

- **Required:** `provider.namespace`, `observed_at`, `adapter` (`name`,
  `version`), `rights` (`data_class`, `prototype_only`, `commercial_use`),
  `sport.medtop`, `competition.provider_id`, `event.provider_id`,
  `event.status`, **exactly one of `event.start_time` or
  `event.temporal_evidence`** (§12), and **at least two `participants`**. A
  one-sided event is not an event; it is a partially-parsed payload, and an event
  that states its start neither way is one we cannot place at all.
- **`adapter` and `rights` are required, not optional-if-present.** Neither is
  derivable from a payload. An observation with no `rights` block leaves every
  consumer to pick its own licence default, which is a licence decision made by
  accident; an observation with no `adapter` block is an anonymous claim, so when
  a fact turns out to be wrong there is nothing naming the code that produced it.
  Both are omissions an adapter must fix, and neither is ever defaulted here.
- **`null`, `""` and every placeholder in `profile.PLACEHOLDER_VALUES` are
  errors**, at any depth. This is the whole point of validating the observation
  rather than the output: fabrication is caught in the *adapter*, where a human
  can see which provider field produced it, not in the serializer, where the
  provenance is already gone.
- **Every `statistics` key is a CURIE** whose whole `prefix:localName` appears in
  `official-property-names.json` (§4). An unknown one is an **error**, not a
  warning. A statistic nobody can resolve is not data. Matching the local name
  alone is not enough: `startDateTime` is declared by `.../ontologies/main/` and
  by nothing else, so a local-name check accepts `spsocstat:startDateTime`, and
  it accepts `notpinned:shotsTotal` — a CURIE under a prefix nothing binds, which
  expands to nothing at all.
- **`adapter.source_refs` is optional, and its values are endpoint classes.**
  Each entry carries `kind` and `value`, plus an optional `note`, and nothing
  else. Any of those three fields containing `://`, `?`, `&`, `api_key`,
  `api-key`, `apikey`, `key=`, `token`, `authorization`, `bearer`, `secret`,
  `password` or `cookie` is an **error**: it is a request or a credential rather
  than an endpoint class, and a request is how an API key or a licensed path ends
  up committed to a fixture file. **Matching is case-insensitive** (`str.casefold`
  on both sides) and covers all three published fields. Both properties are the
  fix for a real bypass: while the markers were matched as raw substrings against
  `value` alone, `Authorization: …` was refused and `authorization: …` accepted,
  `token=abc` refused and `TOKEN=abc` accepted, `key=abc` refused and
  `API_KEY=abc` accepted — and an accepted value is serialized into
  `provenance.source_refs` under a note reading "no URL, query or credential is
  recorded". Rejected here rather than *only* stripped by the serializer, because
  stripping alone would let such a fixture validate clean and the fixture is the
  artefact that gets published; the serializer additionally drops any entry that
  matches, reading the same rule, so that a caller invoking it without validating
  first cannot publish one either. Optional because most adapters have nothing to
  add beyond their name and version, and a required field with nothing to say
  gets filled with a placeholder.
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
unmappable status, a soccer action type (§7), a provider's own clock string, and a
venue's city and country, for which the closed `SiteShape` admits no property.

The signature takes the shared `id_resolver` — `event_view(observation, *,
id_resolver)` — which is how the two serializers agree on identifiers without
either reading the other's output. Independence is asserted by test, not by
comment: the suite replaces `sport_schema_graph` with a function that raises and
then calls `event_view`. Nothing else would notice, because an `event_id` derived
from the graph agrees with the graph by construction.

Three shape decisions:

- **`participants` holds teams, `players` holds individuals.** `role` means
  alignment for a team and would have to mean position or starter-status for a
  person. One key with two meanings is the kind of shape a consumer reads wrongly
  once and works around forever.
- **`statistics` is keyed by local name** (`shotsTotal`), not by CURIE
  (`spsocstat:shotsTotal`). A CURIE key would drag the RDF vocabulary into the one
  projection whose promise is not carrying it. A test asserts no key anywhere in
  the view contains a colon.
- **`provider.raw` is exempt from the RDF-token scan**, and only it. A real
  payload can legitimately contain `@type`; rewriting it to satisfy our own scan
  would destroy the one field whose value is being an unaltered record. The rule
  is "no RDF in anything the serializer authored", not "no RDF anywhere".

---

## 4. The official property allowlist

`tools/iptc/canonical/official-property-names.json` is **generated**, not
maintained: `python -m tools.iptc.canonical.export_official_terms` reads the
pinned ontologies and the shared context and writes every official property as a
full CURIE.

`{"pin": <commit>, "target_version": "1.1", "curies": [ … sorted … ]}`, two-space
indent, trailing newline. A test asserts the checked-in bytes equal what the
generator renders, so the file cannot drift from the pin it claims to come from.
Bumping the pin regenerates it; nobody edits it by hand.

Membership is the whole `prefix:localName`, and each half is evidence from a
different place: the IRI comes from the pinned ontology that declares the
property, and the prefix from the shared context that binds that IRI — the one
context an emitted document carries, so a prefix absent from it is a prefix no
document could resolve. The generator refuses to run while
`check_context_against_reference` reports drift, because a context that disagrees
with the pin makes its own prefixes evidence of nothing. Where upstream binds one
namespace under two prefixes — golf, as `spgolf` and `spgolstat` — both spellings
are listed, because both are what upstream says.

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
  "profile":    "machina-iptc-profile/1.2",
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
identifier ends up committed to a fixture file. It is projected from
`observation.adapter.source_refs` (§1.1), which is where the request-shape check
lives, and it is **omitted entirely** when the adapter supplies none — including
when every entry supplied was dropped for matching that check.

`determinism` is **declared by the injected `id_resolver`**, not stated by the
serializer. `surrogate_resolver` publishes it as `ids.STRATEGY`, and
`provenance_block` reads it off the callable it was handed. The resolver is
injected precisely so a later phase can swap in the canonical identity service; a
serializer that hard-coded the current resolver's digest would quietly start lying
on the day that happens. A resolver that declares nothing produces **no
`determinism` key** — omission over fabrication reaches provenance too.

Because a vendored module cannot import `tools.iptc.reference`, the pin constants
are carried in `tools/iptc/canonical/__init__.py` and a test asserts they equal
the ones this repository actually verifies. A conformance claim citing a pin
nobody checked is worse than no claim.

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

Presence is derived from the observation, one predicate per capability. Five
capabilities have no predicate because the observation contract has **no field
that could carry them**: `event.coordinates`, `event.tracking`,
`event.expected_metrics`, `event.formations`, and — as a schema-shape matter
rather than a provider one — anything a later version adds. Those are reported
absent, because they are, *and* listed under `not_expressible`.

That second list is not decoration. "The provider did not supply tracking data"
and "this contract cannot carry tracking data" send a consumer to two different
places, and only one of them is a conversation with the provider. Collapsing them
would have consumers chasing a provider for a field no adapter could ever emit.

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
    "profile": "machina-iptc-profile/1.2",
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

`canonical_envelope(observation, *, id_resolver)` composes the four builders plus
`capability_report`, and **raises `ValueError`** when `validate_observation`
reports anything. An envelope built from an invalid observation is a conformance
claim — citing a profile and a pin — about a document nobody validated. The
message carries every error rather than the first, so one run tells the adapter
author everything to fix.

The gate is `validate_graph.rights_findings(envelope, consumer_tier="production")`
— implemented in `tools/iptc/canonical/rights.py`, because a consumer downstream
has to run the same rule and cannot import this repository (§10), and re-exported
from `validate.py` and `validate_graph.py` under that name. Empty means the tier
may consume the envelope.

| Code | When |
|---|---|
| `rights-unreadable` | no envelope, no `rights` block, or `prototype_only`/`commercial_use` are not booleans |
| `rights-prototype-only` | tier `production`, `prototype_only: true` |
| `rights-non-commercial` | tier `production`, `commercial_use: false` |
| `rights-unknown-consumer-tier` | a tier outside `prototype` / `production` |

Four decisions in that table are deliberate:

- **It fails closed on unreadability.** An absent licence claim is not a
  permissive one, and reading it as permission is how prototype-only data reaches
  a commercial surface.
- **One finding, never a cascade.** `prototype_only` and `commercial_use: false`
  travel together on every open-data envelope, so reporting both buries the one
  line that names the fix — the same reasoning §1.1 applies to an absent block.
- **The function's default tier is `production`**, the strict one. A gate whose
  default is permissive is a gate nobody notices is off. `validate_graph.py`'s
  `--consumer-tier` flag defaults to `prototype` instead, so the command's
  verdict over checked-in fixtures is unchanged; every one of them predates the
  gate.
- **An unknown tier returns a finding rather than raising.** A raise can be caught
  and mistaken for "no findings"; a finding is a refusal by construction.

### 9.1 The gate at the command line

`validate_graph.py` accepts a canonical envelope as an input document and
**enforces** `--consumer-tier` on it:

```bash
python3 tools/iptc/validate_graph.py --consumer-tier production <envelope.json>
# FAIL  … rights_gate: consumer tier 'production' is refused this envelope
#            - rights-prototype-only: …                     → exit status 1
```

Three properties make that a check rather than a label:

- **An envelope is validated, not bounced.** Its inner `sport_schema_graph` goes
  through the same layers as a standalone graph document, in memory, and the
  result is reported under the path the caller named. Rejecting an envelope for
  "not being JSON-LD" would answer a question nobody asked while leaving the
  rights question unanswered.
- **The rights verdict is a `rights_gate` layer** in both the human and the
  `--json` output, and a refusal fails the run. An authorization flag that parses
  and decides nothing is worse than no flag: it reads as a check that passed.
- **A graph document gets no rights verdict at all** — not a passing one. Rights
  live in the envelope, so `rights_gate` is reported as not applicable and the
  document remains a valid input. Manufacturing a pass for a document that
  cannot carry a licence claim is the same failure as reading an absent claim as
  a permissive one.

---

## 10. Vendoring

`sports-skills` is a published zero-dependency package and cannot import this
repository, so `observation.py`, `ids.py`, `capabilities.py`, `vocab.py`,
`serialize.py`, `rights.py`, `official-property-names.json` and
`shared-context.json` are vendored **byte-exact**, not reimplemented. Two
reimplementations of one contract diverge; the only question is when.

`rights.py` joined that list because §9's gate is the one rule a *consumer* runs,
and a consumer downstream cannot import `tools.iptc.validate` — that module needs
pyshacl and rdflib, which the published package does not have. So the rule moved
to `canonical/rights.py` and `validate.py` / `validate_graph.py` re-export it;
`validate_graph.rights_findings` still resolves to it, and a test asserts the
re-exports are the same function object rather than a second copy. Of every file
on this list, this is the one where a divergence would be worst: the drifting copy
would be the one deciding whether prototype-only data reaches a commercial
surface.

`vocab.py` and `shared-context.json` joined that list when `serialize.py` landed.
`serialize.py` emits NewsCodes through `vocab.newscode`, so inlining those tables
would create exactly the second copy this section exists to prevent; and it inlines
the shared JSON-LD context, which it cannot read from `tools.iptc.context` because
there is no such module downstream. Both are therefore package-local, and a test in
this repository asserts this list names every file the runtime actually needs.

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

---

## 12. Reduced-precision temporal evidence

`canonical-observation/1.1`, profile `machina-iptc-profile/1.2`. Additive: it
adds one member and one capability name, and changes the meaning of no existing
field.

**The defect it corrects.** `event.start_time` requires an RFC 3339 instant with
seconds. Most providers publish schedules at minute granularity, so an honest
normalizer holding `2030-01-02T03:05Z` had two exits and both were wrong.
Appending `:00` invents a second-of-minute the source never stated, and once that
value is in the record no consumer can tell it from a source that genuinely said
`:00` — a fabricated numeral carrying a real source reference, below every gate
that could catch it. Refusing the observation blocks fact families for a
formatting mismatch rather than a missing fact.

The modelling error underneath is that one string was carrying three different
things. They are kept separate here:

| Concern | What it is | Authority |
|---|---|---|
| **Source lexical value** | the exact string the normalizer produced, byte for byte, including its explicit offset | observed, never rewritten |
| **Declared source precision** | how precise that string actually is | observed, never inferred from formatting |
| **Normalized comparison bounds** | the half-open instant interval the value denotes, UTC-normalized | derived, deterministic, recomputable |

**A reduced-precision value denotes an interval, not a point.**
`2030-01-02T03:05Z` at minute precision denotes
`[2030-01-02T03:05:00Z, 2030-01-02T03:06:00Z)` — lower inclusive, upper
exclusive, both emitted as second-precision RFC 3339 instants in UTC, so every
consumer compares like with like.

### 12.1 The member

```jsonc
{
  "schema_version": "canonical-observation/1.1",
  "observation": {
    "event": {
      // "start_time" is ABSENT in this case — see §12.2
      "temporal_evidence": {
        "kind": "start",
        "source_value": "2030-01-02T03:05-03:00",
        "precision": "minute",
        "lower_inclusive": "2030-01-02T06:05:00Z",
        "upper_exclusive": "2030-01-02T06:06:00Z",
        "provenance": { "derivation": "declared_precision_interval" }
      }
    }
  }
}
```

- `kind` — closed to `start`, the one instant `event.start_time` covers. An
  unrecognised kind would otherwise let an end-of-event bound satisfy a consumer
  that asked for a bounded *start*.
- `precision` — closed to `minute`. `date` and `hour` are deliberately out: no
  fixture cites them and their interval semantics (all-day events,
  timezone-ambiguous dates) are materially harder. Second and fractional-second
  values are out because they already have a home, `event.start_time`; admitting
  them here would be two ways to say one thing plus zero-width "intervals".
- `source_value` — verbatim, and it **must** carry an explicit RFC 3339 offset
  (`Z` or `±HH:MM`). **The offset lives here and nowhere else.** There is no
  separate offset field, and the member's key set is closed so that adding one is
  an error rather than a second source of truth that can disagree with the first.
- `lower_inclusive` / `upper_exclusive` — derived, second-precision, `Z`.
- `provenance` — identifiers and versions only: no URL, no query string, no
  credential. `derivation` is closed to `declared_precision_interval`.

**Bound derivation is a pure function of `(source_value, precision)`**,
implemented as `observation.derive_bounds`:

| `precision` | Width | Lower | Upper |
|---|---|---|---|
| `minute` | exactly 60 s | `source_value` with `:00` seconds, converted to UTC at its explicit offset | lower + 60 s |

**No timezone database ever participates.** The offset is explicit and is read
out of `source_value`; the arithmetic is fixed-offset subtraction. There is no
zone name to resolve, so no DST rule can apply — a value at a DST transition
instant derives exactly what the same wall value derives anywhere else. A value
with a zone name but no explicit offset, or a naive value, is not admissible.
This also keeps the packaging promise: standard library only, Python 3.9 floor,
no `dateutil`, no `pendulum`, no `zoneinfo`.

### 12.2 Conditional validation, fail-closed

An event carries **exactly one** of two temporal states:

1. **Exact** — `event.start_time` present, RFC 3339 with seconds;
   `temporal_evidence` absent. Behaviour is unchanged in every respect.
2. **Reduced** — `temporal_evidence` present with `precision: "minute"`;
   `event.start_time` absent.

Everything else is a hard validation error. There is no best-effort branch and no
defaulted precision:

| Condition | Disposition |
|---|---|
| both `start_time` and `temporal_evidence` present | **FAIL** — inconsistent dual assertion |
| neither present | **FAIL** |
| `precision` missing, unknown, or anything but `minute` | **FAIL** |
| a second or fractional-second value inside the member | **FAIL** — exact values belong in `start_time` |
| `source_value` naive, or its offset only implied by a zone name | **FAIL** |
| any key the member does not define, including a second offset-bearing one | **FAIL** |
| bounds absent, non-RFC-3339, not second-precision, or not `Z`-normalized | **FAIL** |
| bounds not exactly recomputable from `(source_value, precision)` | **FAIL** |
| `lower_inclusive >= upper_exclusive` (inverted **or** zero-width) | **FAIL** |
| width other than 60 s for `minute` | **FAIL** |
| `provenance` absent, or `derivation` outside its enum | **FAIL** |

`event.start_time` keeps **exact-instant semantics**, its current regex and its
current IPTC projection. Widening it instead would have changed the meaning of a
released, pinned field that every existing consumer reads as an instant, with no
way to detect the change from the data — a breaking change disguised as a
permissive one.

### 12.3 The closed schema-version acceptance matrix

`validate_observation` compares `schema_version` against a **closed set**
(`canonical.ACCEPTED_SCHEMA_VERSIONS`), not a single constant:

| Declared schema | Temporal state | Disposition |
|---|---|---|
| `canonical-observation/1` | exact; no temporal evidence | **ACCEPT** as a legacy exact document |
| `canonical-observation/1` | temporal evidence, with or without `start_time` | **REFUSE** — that contract defines no such member |
| `canonical-observation/1.1` | exact; no temporal evidence | **ACCEPT** |
| `canonical-observation/1.1` | valid minute evidence; no `start_time` | **ACCEPT** |
| `canonical-observation/1.1` | both states, or neither | **REFUSE** |
| any other identifier | any | **REFUSE** |

Adapters emit the successor for both exact and reduced documents. The predecessor
stays accepted only so existing exact documents keep reading, and is never
emitted for a new reduced one.

### 12.4 Capability and graph consequences

- `event.start_time` — unchanged, present iff an exact instant is present.
- `event.start_time.bounded` — present iff the record carries **valid** reduced
  evidence. It joins the **core-tier optional** set, never the required set:
  requiring it would knock every existing exact observation out of the core tier.
- No alternatives or OR semantics are added. `check_compatibility` evaluates
  `requires` as a flat conjunction, so a consumer picks **one** requirement set:
  requiring `event.start_time` fails closed on a reduced record, and requiring
  `event.start_time.bounded` fails closed on an exact one. Both are the truthful
  answer for that consumer.
- A reduced record therefore reports **below core**, with `event.start_time`
  listed as core-required-absent. That is the honest reading — the record has no
  exact instant — and requirement sets, not tier labels, are the mechanism for
  bounded consumers.
- Under profile `machina-iptc-profile/1.2`, a reduced-precision observation
  produces `event_view` normally and **no `sport_schema_graph` at all**: not a
  partial `Event`, not an `Event` with the start property dropped, and no
  `machina:`-namespaced temporal property inside the interoperability document. A
  partial `Event` is a conformance claim about a resource that is not conformant,
  and a `machina:` temporal property in the graph is the same invented-precision
  leak one namespace over. The evidence lives in `event_view`, where our
  provenance travels with it.
- **The omission is structured.** `capabilities.graph_unavailable_reason` carries
  the enumerated token `exact-event-start-time-required`, and a direct
  `sport_schema_graph` call raises `serialize.GraphUnavailable` carrying the same
  token — never an unstructured error and never an empty `@graph`, which would
  look like a conformant document that happens to describe nothing. The key is
  absent, not null, on records whose graph is available.

Exact observations are unaffected: `sport_schema_graph`, `event_view`,
`provenance`, `provider_ids` and `rights` are byte-identical across the bump,
apart from the profile identifier `provenance` restates. The only other changes
are `schema_version` on the input document, `profile` on the envelope, and
`event.start_time.bounded` appearing in the envelope's `capabilities.absent` and
core `optional_absent` lists. `tests/test_iptc_temporal_evidence.py` proves that
by rebuilding every corrected envelope, undoing exactly those changes, and
comparing the digest against
`tools/iptc/fixtures/exact-observation-0.1.0-digests.json`.
