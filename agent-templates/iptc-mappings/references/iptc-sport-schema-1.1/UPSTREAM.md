# Vendored upstream: IPTC Sport Schema 1.1

This directory is a byte-exact partial copy of the official IPTC Sport Schema
repository at one pinned commit. Nothing here is Machina-authored except
`UPSTREAM.md`, `LICENSE.md` and `upstream-commit.json`.

## The pin

| Field | Value |
|---|---|
| Upstream repository | `https://github.com/iptc/sport-schema` |
| Pinned commit | `0e77bf8678f3702fe81c28673bede35efe47d633` |
| Version | **1.1** |
| Licence | CC-BY 4.0 (`https://creativecommons.org/licenses/by/4.0/`) |
| Archive fetched | `https://codeload.github.com/iptc/sport-schema/tar.gz/0e77bf8678f3702fe81c28673bede35efe47d633` |
| Archive sha256 | `d480ec88688034400bdd3fcb4cc89a84cc6ed005f55fc3e0a5a93d222b77b415` |

### Why a commit and not a tag

**The upstream GitHub Releases list contains no `1.1` tag.** There is nothing to
pin a tag to, so the commit is the pin. Do not write `v1.1`, do not link to a
`v1.1` tag, and do not add a tag-shaped alias in tooling: any such reference
would be fabricated and unverifiable, which is exactly the class of defect this
work exists to remove.

### Version evidence, recorded with the copy

Three independent statements inside the pinned bytes agree on 1.1:

1. `README.md` — heading `## Latest version: Sport Schema 1.1`.
2. `credits.markdown` — "Version 1.1 was approved by the IPTC Standards
   Committee on 2 October 2024."
3. `ontologies/iptc-sport-ontology.ttl` — the `owl:Ontology` node
   `<https://sportschema.org/ontologies/main/>` declares
   `owl:versionIRI <https://sportschema.org/ontologies/main/1.1>` and
   `owl:versionInfo "1.1"^^xsd:string`.

Every other ontology in `ontologies/` declares its own `owl:versionInfo "1.1"`
and a matching per-ontology `owl:versionIRI` (for example
`<https://sportschema.org/ontologies/soccer/1.1>`).

`README.md` and `credits.markdown` are vendored here specifically so that the
version claim can be re-checked offline, without a network round trip to GitHub.

## Layout, and how it maps to upstream

| This directory | Upstream path at the pinned commit |
|---|---|
| `ontologies/*.ttl` | `ontologies/*.ttl`, minus the SHACL file |
| `shacl/iptc-sport-shacl.ttl` | `ontologies/iptc-sport-shacl.ttl` |
| `vocabularies/*.ttl` | `vocabularies/*.ttl` (all 17) |
| `samples/json-ld/*.jsonld` | `samples/json-ld/*.jsonld` (4 of 18, see below) |
| `tools/prefixes.ttl` | `tools/prefixes.ttl` |
| `README.md` | `README.md` |
| `credits.markdown` | `docs/credits.markdown` |

`upstream-commit.json` records, per file, the upstream path, the byte size and the
sha256 of the vendored bytes. It is the authoritative integrity check — the
archive sha256 above is provenance only, because gzip framing served by
`codeload.github.com` is not guaranteed byte-stable over time.

### Which samples, and why only four

`samples/json-ld/soccer-match-02.jsonld`, `player-bio-01.jsonld`,
`team-roster.jsonld` and `soccer-standings.jsonld` are vendored as
**known-conforming positive controls** for the validation harness: if the
harness reports a failure on one of these, the harness is wrong, not the data.
They were selected because they conform against the official SHACL shapes and
are small enough to keep the test suite fast. The other 14 official samples,
the SPARQL query corpus, the SportsML XML corpus and the HTML documentation are
deliberately not vendored — they are not needed to validate a Machina payload,
and copying them would add megabytes of dead weight.

## Byte preservation, and two upstream defects worked around in memory

**The vendored files are never rewritten.** `upstream-commit.json` asserts their
sha256, and `tools/iptc` verifies that assertion on every run.

Two artefacts at this commit are not accepted by a strict parser. Apache Jena,
which upstream's own `tools/shacl-validate.sh` uses, tolerates both. `rdflib`
and `pyshacl` do not. The harness therefore applies two narrow, deterministic,
**in-memory** shims at load time and reports that it did so. Both are recorded
here so that a future pin bump can check whether upstream has fixed them.

### Defect 1 — missing `.` after the final `@prefix` directive

15 of the 17 files in `vocabularies/` end their prefix block without the
Turtle statement terminator. For example, `vocabularies/spplayerstatus.ttl`:

```turtle
@prefix spplayerstatus:	<http://cv.iptc.org/newscodes/spplayerstatus/>
```

Affected: `spactionclass`, `spcompetitionscope`, `spct`, `speventoutcome`,
`speventoutcometype`, `speventstatus`, `spgolholetype`, `sphorposition`,
`spichposition`, `spplayerstatus`, `spresulteffect`, `spscoreunits`,
`spsocposition`, `sptournamentform`, `sptournamentphase`.
Not affected: `asportfacetvalue`, `mediatopic`.

Shim: a file is first parsed as-is. Only if that raises does the harness retry
against an in-memory copy in which any `@prefix`/`@base` line ending in `>` gains
a ` .`. Nothing else in the text is touched, and the repaired text is never
written to disk.

### Defect 2 — `sh:ignoredProperties` on a shape that is not `sh:closed`

`shacl/iptc-sport-shacl.ttl` has six node shapes that declare
`sh:ignoredProperties` while their `sh:closed true` line is commented out.
`pyshacl` rejects this at shape-load time with
`ConstraintLoadError: ClosedConstraintComponent`.

Shim: after the shapes graph is parsed, the harness removes the
`sh:ignoredProperties` triple from any shape that does not also assert
`sh:closed true`. Per the SHACL specification, `sh:ignoredProperties` has no
effect without `sh:closed`, so this is semantics-preserving: it drops a
statement that could not have constrained anything.

## How the official validation procedure is reproduced

Upstream's `tools/shacl-validate.sh` concatenates the merged ontology, **all**
vocabulary files and the instance data into one data graph, then validates that
graph against `iptc-sport-shacl.ttl`. The merge is load-bearing: shapes rely on
`rdfs:subClassOf` from the ontology and on `skos:inScheme` from the
vocabularies, so validating instance data alone produces false failures.

`tools/iptc` does the same thing with `rdflib` + `pyshacl` instead of Jena. That
is why every vocabulary is vendored, including the 2.7 MB `mediatopic.ttl`: the
SHACL shapes reference `<http://cv.iptc.org/newscodes/mediatopic/>` and dropping
it would silently weaken the vocabulary layer.

## Known gap: `spsocaction` is not published in this repository

`tools/prefixes.ttl` binds `spsocactiontype:` to
`<http://cv.iptc.org/newscodes/spsocaction/>`, and the SHACL shapes reference
that scheme — but **no `vocabularies/spsocaction.ttl` exists at this commit**.
The same is true of `spsocrole`, `spesaction` and the other per-sport action and
result schemes named by the shapes.

Consequence, stated plainly: soccer action-type NewsCodes **cannot be validated
offline against a pinned TTL**. The harness reports such values as
`unverifiable` — a distinct outcome from `valid` and from `invalid` — and
`docs/iptc/BASELINE-AUDIT.md` carries the same distinction. Nothing in this
repository infers those code lists, and no substitute list is invented.

## Attribution

See `LICENSE.md` in this directory.
