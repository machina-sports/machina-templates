# machina-sports-canonical

The canonical **Machina Sports Schema** runtime: provider-neutral observations,
IPTC Sport Schema 1.1 serialization, and the shared JSON-LD context that every
document produced by it inlines.

Standard library only. No runtime dependencies. Python 3.9+.

## What it is for

A provider payload goes into an adapter and a `canonical-observation/1` document
comes out. Everything downstream — validation, both serializers, the capability
report, the rights gate — sees that contract and never a provider's vocabulary.
Adding a provider therefore costs one adapter module rather than a fork of the
serializer.

```python
from machina_sports_canonical.adapters import api_football
from machina_sports_canonical.ids import surrogate_resolver
from machina_sports_canonical.observation import validate_observation
from machina_sports_canonical.serialize import canonical_envelope

observation = api_football.to_observation(payload, observed_at="2026-08-11T12:00:00Z")
problems = validate_observation(observation)
envelope = canonical_envelope(observation, id_resolver=surrogate_resolver("urn:machina"))
```

Adapters take no clock, no network, no credential and no environment:
`observed_at` is an input precisely so that serializing the same payload twice
produces the same bytes.

## Contents

| Module | What it holds |
| --- | --- |
| `machina_sports_canonical` | the three version constants and the upstream pin |
| `.observation` | the `canonical-observation/1` input contract and its validator |
| `.serialize` | the IPTC Sport Schema graph, the event view and the envelope |
| `.vocab` | the NewsCodes tables provider values map onto |
| `.ids` | Machina identifier minting and the injected resolver |
| `.rights` | the consumer-tier rights gate |
| `.capabilities` | what a given document can and cannot support |
| `.adapters` | one module per provider reading |

Two JSON resources ship beside the code and are read through `__file__`:
`shared-context.json` (the prefix table) and `official-property-names.json` (the
official Sport Schema property allowlist, generated from the pinned upstream
ontologies).

## Provenance

These bytes are not authored in this distribution. They are published from
`machina-templates` at `tools/iptc/canonical`, unmodified. `package-receipt.json`
ships inside the package and records the distribution version, the source path
and the exact source commit, together with a SHA-256 manifest of the nine core
files:

```python
import json, pathlib, machina_sports_canonical
receipt = json.loads(
    (pathlib.Path(machina_sports_canonical.__file__).parent / "package-receipt.json")
    .read_text(encoding="utf-8"))
```

The same nine hashes gate the source tree in the originating repository, so an
installed file that disagrees with the receipt is a build that transformed
something it had no business transforming.

`export_official_terms`, the generator that produces
`official-property-names.json`, stays in the originating repository: it needs the
pinned upstream ontologies, which are not part of this distribution.

## License

`MIT AND CC-BY-4.0`. A conjunction, because both sets of terms apply — to
different files in the same archive.

- **The software is MIT.** The Python runtime, the adapters and the build tooling
  are Copyright (c) 2026 Machina Sports, under `LICENSES/MIT.txt`.
- **Two packaged assets carry CC-BY-4.0 attribution obligations.**
  `official-property-names.json` is extracted and generated from IPTC Sport
  Schema 1.1, and `shared-context.json` is Machina-authored but reproduces that
  work's pinned namespace bindings. The licence text is `LICENSES/CC-BY-4.0.txt`
  — https://creativecommons.org/licenses/by/4.0/.

The upstream work is IPTC Sport Schema 1.1 by the IPTC Sports Content Working
Group. **`NOTICE-IPTC.md` ships in this distribution** and carries the full
attribution: creator, copyright, the exact upstream commit, what was extracted or
reproduced, and the boundary between the two licences. Read it before reusing
either asset.

CC BY does not reach the software, and none of this implies IPTC endorsement,
sponsorship or affiliation.
