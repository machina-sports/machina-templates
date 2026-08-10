"""Regenerate the official property allowlist from the pinned ontologies.

    python -m tools.iptc.canonical.export_official_terms

``observation.validate_observation`` rejects any statistic CURIE whose local name
is not in this allowlist. That check has to work inside ``sports-skills``, which
cannot import this repository and cannot depend on ``rdflib``, so the allowlist
travels as data rather than as a query.

Data that travels rots. The defence is that this file is a **generator**, the
output is checked in, and a test asserts the checked-in bytes equal what the
generator renders right now — so the allowlist cannot drift from the pin it
claims to come from without the suite going red. Bumping the pin regenerates it.
Nobody edits it by hand.

This module is the one thing under ``tools/iptc/canonical/`` that is NOT vendored
downstream, which is why it alone may import ``tools.iptc.reference``.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..reference import TARGET_VERSION, UPSTREAM_COMMIT, load_reference

OUTPUT_PATH = Path(__file__).resolve().parent / "official-property-names.json"


def local_names() -> list[str]:
    """Sorted local names of every property in an official Sport Schema namespace.

    Properties only. A class name here would let ``spsocstat:Team`` through as a
    statistic, which is exactly the kind of near-miss the allowlist exists to
    catch. ``official_namespace_of`` is used rather than a prefix match on the
    main namespace, because statistics live in the per-sport ontologies
    (``.../soccer/``, ``.../corestatistics/``, …), not in ``.../main/``.
    """
    reference = load_reference()
    names = set()
    for iri in reference.properties:
        namespace = reference.official_namespace_of(iri)
        if namespace is not None:
            names.add(iri[len(namespace):])
    return sorted(names)


def render() -> str:
    """The exact bytes of the allowlist file, as text."""
    payload = {
        "pin": UPSTREAM_COMMIT,
        "target_version": TARGET_VERSION,
        "local_names": local_names(),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    OUTPUT_PATH.write_text(render(), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.relative_to(Path.cwd())}" if OUTPUT_PATH.is_relative_to(Path.cwd())
          else f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
