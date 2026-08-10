# Licence and attribution for the vendored IPTC Sport Schema

## What this file is

**This is a Machina-authored attribution notice. It is not a vendored upstream
file.** The upstream repository `iptc/sport-schema` contains no `LICENSE` file at
commit `0e77bf8678f3702fe81c28673bede35efe47d633`; the licence is declared
in-band, inside the ontology files themselves. This notice exists so that the
declaration travels with the copy.

## The upstream declaration, quoted verbatim

Every `owl:Ontology` node in `ontologies/*.ttl` carries these two statements.
From `ontologies/iptc-sport-ontology.ttl`:

```turtle
    dcterms:license <https://creativecommons.org/licenses/by/4.0/> ;
    dcterms:rights "Copyright (C) International Press Telecommunications Council 2024. Released under the Creative Commons Attribution (CC-BY) 4.0 licence."@en ;
```

and, from the same node:

```turtle
    dcterms:creator "IPTC Sports Content Working Group"@en ;
    dcterms:created "2023-10-04"^^xsd:date ;
    dcterms:modified "2024-10-02"^^xsd:date ;
```

## Attribution

- **Work:** IPTC Sport Schema, version 1.1
- **Creator:** IPTC Sports Content Working Group, International Press
  Telecommunications Council (IPTC)
- **Copyright:** Copyright (C) International Press Telecommunications Council
  2024
- **Licence:** Creative Commons Attribution 4.0 International (CC-BY 4.0),
  `https://creativecommons.org/licenses/by/4.0/`
- **SPDX identifier:** `CC-BY-4.0`
- **Source:** `https://github.com/iptc/sport-schema` at commit
  `0e77bf8678f3702fe81c28673bede35efe47d633`
- **Documentation:** `https://www.sportschema.org/`
- **Contributors:** listed in `credits.markdown` in this directory, vendored from
  upstream `docs/credits.markdown`

## What CC-BY 4.0 requires of us here

Attribution, an indication of the licence, and an indication of whether changes
were made.

**No changes were made.** Every upstream file in this directory is byte-exact;
`upstream-commit.json` records the sha256 of each one and `tools/iptc` verifies those
hashes on every run. The two upstream syntax defects documented in `UPSTREAM.md`
are worked around by in-memory shims at load time and are never written back to
these files.

Machina-authored material that builds on this work — the shared JSON-LD context
at `agent-templates/iptc-mappings/contexts/iptc-sport-schema-1.1.context.jsonld`, the profile RFC at
`docs/rfcs/001-machina-iptc-sport-schema-profile.md`, and the harness under
`tools/iptc/` — is licensed under this repository's own terms and is not covered
by this notice. Those artefacts cite the pinned commit as their source of truth
for every term IRI and prefix binding they contain.

## What this notice does not grant

Nothing about provider data. The IPTC Sport Schema licence covers the schema —
the ontologies, shapes and controlled vocabularies in this directory. It says
nothing about API-Football, Sportradar, Stats Perform/Opta or any other feed.
Provider payload licensing is governed separately, which is why the fixtures
under `tools/iptc/fixtures/` are derived only from artefacts already checked into
this repository and never from a live licensed call.
