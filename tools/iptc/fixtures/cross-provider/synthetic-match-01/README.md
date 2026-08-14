# `synthetic-match-01` — one match, four providers

One obviously synthetic 2-1 closed soccer match, expressed in four provider
payload shapes. Two consumers read this directory:
`tests/test_iptc_cross_provider_equivalence.py` checks that the API-Football and
sports-skills readings land on the same canonical facts, and
`tests/test_iptc_canonical_provider_substitution.py` runs all four legs through
the shared `machina-sports-canonical` connector for the Amendment C §C4
four-provider proof.

| Provider namespace | Native shape | File |
|---|---|---|
| `api-football` | API-Football `/fixtures` element | `api-football.json` (here) |
| `sportradar-soccer` | Sportradar `sport_event_summary` | `sportradar-soccer.json` (here) |
| `stats-perform-opta` | Opta legacy mapping-contract document | `stats-perform-opta.json` (here) |
| `sports-skills/espn` | canonical observation | `../../observations/sports-skills-espn-soccer-observation.json` |

**Two legs are read by reference rather than copied.** The sports-skills leg is
the A14 reference contract's own artefact, published byte-identically in two
repositories; a second copy here would drift from the first the day either is
corrected, and it would make the comparison partly self-referential. It enters
one step later than the other three for a second reason: there is no in-repo
sports-skills adapter and Amendment C does not authorise one, because canonical
mode for sports-skills is owned upstream. So that leg arrives as an
already-canonical observation while the other three arrive as native payloads
their adapters convert.

**Everything in every file is invented.** No API-Football, Sportradar, Opta or
ESPN endpoint was called, no credential exists in this repository, and there is
no network access in this harness. Nothing here is a rights claim: every adapter
emits `prototype_only` evidence, so a `production` consumer tier is refused
before a provider is reached.

## Identity is deliberately disjoint

The property under test is that four providers observing one match agree about
the *match* while agreeing about nothing at all about *identity*. Each leg
therefore uses its own identifier family, and the canonical identities only
converge because the canary injects a crosswalk (`canary_crosswalk()` in
`tests/iptc_canonical_support.py`).

| | event | competition | home / away | venue |
|---|---|---|---|---|
| api-football | `9501` | `9601` | `9511` / `9512` | `9701` |
| sports-skills | `9001` | `synthetic-league-1` | `9011` / `9012` | `9101` |
| sportradar | `sr:sport_event:9201` | `sr:competition:9202` | `sr:competitor:9211` / `9212` | `sr:venue:9204` |
| opta | `synthetic0matchid921` | `synthetic0compid921` | `synthetic0teamid921` / `922` | `synthetic0venueid921` |

`league.season` on the API-Football leg is `2026` rather than a `9xxx` token on
purpose: API-Football has no standalone season identifier, so a season is its
year, and inventing a tidier one would have put a string the provider never uses
into the crosswalk.

## Differences the legs keep, and why

The proof classifies every remaining difference against Amendment B §B11's
closed set rather than normalising the fixtures until they match. Normalising
would hide exactly what the proof exists to measure. What survives:

- **`season` and `site` identities** are provider-scoped surrogates. A season is
  derived from a *pair* of provider identifiers, so no single crosswalk entry
  denotes it — it keeps the package's marked surrogate, which is §B12 working.
- **`attendance`** is stated by Sportradar and Opta (both `30125`) and by
  neither of the others.
- **`site.country`** is stated only by sports-skills, and **`site.city`** by
  every leg except Opta, whose legacy venue block has no city field.
- **`clock`** is stated only by API-Football — the `event.clock` capability.
- **`outcome`** on participants is absent from the sports-skills leg, which does
  not state `event.result`.
- **`start_time`** is `...T20:00:00Z` on the Opta leg and `...+00:00` on the
  others, because that is how each shape writes an instant. The proof compares
  the instant, not the spelling.

None of these is a disagreement about the match, and none was smoothed over:
omission over fabrication applies to fixtures too.
