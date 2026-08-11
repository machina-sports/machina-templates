# Attribution notice — IPTC Sport Schema

`machina-sports-canonical` is distributed under `MIT AND CC-BY-4.0`. Two files in
this distribution carry attribution obligations under the Creative Commons
Attribution 4.0 International licence. This notice is how those obligations are
discharged for anyone who has only the installed package.

## The upstream work

| | |
|---|---|
| Work | IPTC Sport Schema 1.1 |
| Creator | IPTC Sports Content Working Group |
| Copyright | Copyright (C) International Press Telecommunications Council 2024 |
| Source | https://github.com/iptc/sport-schema/tree/0e77bf8678f3702fe81c28673bede35efe47d633 |
| Licence | CC-BY-4.0 — https://creativecommons.org/licenses/by/4.0/ |

The source is a commit, not a branch, because the material below was taken from
that exact tree and from no other.

The full licence text ships beside this notice as `LICENSES/CC-BY-4.0.txt`.

## What in this distribution the attribution covers

Two packaged files, for two different reasons. They are named individually
because a reader deciding how to reuse one of them cannot act on a sentence
about "the JSON resources".

### `official-property-names.json`

The Sport Schema property allowlist. It is **extracted** from the upstream
ontology files and **generated** into this form by `export_official_terms`, which
stays in the originating repository. It is a derivative of the upstream work: the
term set is upstream's, the file format, ordering and framing are not.

### `shared-context.json`

The JSON-LD prefix table every canonical document inlines. It is
**Machina-authored** rather than copied — but it **reproduces** the pinned
namespace bindings that IPTC Sport Schema 1.1 declares, so the values it carries
originate in the upstream work and are attributed here.

## What was done to the upstream material

The upstream ontology files themselves are **not shipped** in this distribution.
What ships is an allowlist extracted and generated from those ontologies, and a
context that reproduces their namespace bindings.

This notice deliberately makes no blanket claim that the upstream work is carried
here as-is: it is not carried here at all, and the two files above are derived
from it. The CC BY obligation to indicate whether changes were made is discharged
by stating what was done, above, rather than by denying that anything was.

## The software is MIT, not CC BY

CC-BY-4.0 reaches the two files named above. It does **not** reach the software.
The Machina-authored Python runtime, the provider adapters and the build tooling
in this distribution are licensed under the MIT licence, whose text ships as
`LICENSES/MIT.txt`. The aggregate expression `MIT AND CC-BY-4.0` is a
conjunction — both sets of terms apply, to different members of the same archive —
and never a grant of CC BY over the code.

## No endorsement

Attribution is required by CC-BY-4.0. Endorsement is not granted by it, and none
is claimed here. Nothing in this distribution implies that the International
Press Telecommunications Council, or its Sports Content Working Group, endorses,
sponsors, certifies or is affiliated with `machina-sports-canonical` or with
Machina Sports. This distribution is not an IPTC product and speaks only for
itself.
