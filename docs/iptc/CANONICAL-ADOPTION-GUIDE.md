# Canonical adoption guide — start here, forward only

Authority: the approved greenfield canonical-adoption architecture, recorded in
`docs/plans/2026-08-13-iptc-pr3d-greenfield-canary-amendment-c.md`.

This replaces the migration guide that earlier PR3-D drafts would have produced.
The replacement is deliberate, not cosmetic: a migration guide implies a
programme to remove legacy fields on a schedule, and **no legacy alias-removal
programme is implied or scheduled by this work.**

---

## 1. Scope, before anything else

- The four-provider proof behind this guide is **synthetic**. It establishes
  shape and behaviour at the **prototype** tier.
- It is **not live parity**. No provider API is called anywhere in it.
- It is **not a rights position**. Every adapter reachable through the seam emits
  `prototype_only` evidence, so a `production` consumer tier is refused *before*
  the provider is reached. That is the gate working as designed.

## 2. What a new consumer does

**Start canonical.** A new consumer reads the `machina_sports_schema` envelope
and nothing else. There is no legacy shape to adopt, no alias to depend on, and
no compatibility step to plan for.

1. **Install the shared connector.** Reference
   `../../connectors/machina-sports-canonical/machina-sports-canonical.yml` from
   your template's `_install.yml`. Do not copy it — one connector reaches the
   canonical package, and every consumer installs that one.
2. **Gate before you retrieve.** Call `provider_preflight` with your `provider`,
   your `consumer_tier`, and your own `requires` / `optional` capability
   declaration. Condition everything downstream on `allowed`.
3. **Canonicalize.** Call `canonicalize_event` with the observed payload and your
   crosswalk. Identity resolves from the crosswalk you inject; anything it does
   not map gets a **visibly marked surrogate**, never a silent identifier.
4. **Read `event_view`.** It is the default consumption path and it is what
   almost every consumer actually needs.
5. **Carry `capabilities`, `rights` and `provenance`.** They travel with every
   path and must not be stripped. A projection served without its rights block is
   an unlicensed payload wearing a licensed one's shape.
6. **Ask for the graph only if you need it.** `sport_schema_graph` is opt-in.

`agent-templates/machina-sports-canonical-canary` is the worked example. It is
minimal on purpose: copy its shape, not its content.

## 3. Declaring capabilities

Use the existing dotted names from `ALL_CAPABILITIES`. Do not invent a second
spelling — a shorthand alias is a second vocabulary, and this programme has
already paid for one of those.

Two rules. `provenance` is always required, because an unattributed fact is not
usable editorially. And a capability belongs in `requires` only if you would
produce something *wrong* without it; if you would merely produce something
*thinner*, it is `optional`. Over-declaring `requires` turns the fail-closed gate
into an outage.

## 4. Refusals you should expect

| Code | Means |
|---|---|
| `provider-not-allowlisted` | The provider is not one the seam reaches. No retrieval was attempted. |
| `capability-unknown` | A declared capability name is outside the contract. Refused rather than read as absent. |
| `rights-prototype-only` | A `production` consumer asked for prototype-only evidence. Refused, never downgraded. |
| `capability-incompatible` | The envelope does not satisfy your declared `requires`. |

Post-render rights evaluation still runs, but it is a **drift check** that
reports and never authorizes.

## 5. The historical World Cup runtime

**It is untouched, and it stays that way.** The World Cup is finished. Its
template, workflows, connector, documents and storage are **byte-unchanged** by
this work; the canonical seam does not read them, does not migrate them, and
builds no compatibility projection over them. They remain as historical
regression evidence.

Concretely, for anyone reading the old inventory: no legacy alias projection was
built, no resolver or ingest or read-seam repoint was performed, and no
preservation work is owed for the historical identifier shape. If you maintain
something that reads those documents, nothing you depend on has moved.

## 6. What is deliberately not here

- No alias-removal schedule, because there is no alias programme.
- No deprecation timetable for the historical runtime.
- No instruction to migrate an existing consumer. Migrating any current consumer
  is later, separately-approved work, and it stops for review first.
