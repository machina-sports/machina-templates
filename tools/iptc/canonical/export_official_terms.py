"""Regenerate the official property allowlist from the pinned ontologies.

    python -m tools.iptc.canonical.export_official_terms

``observation.validate_observation`` rejects any statistic CURIE that is not in
this allowlist. That check has to work inside ``sports-skills``, which cannot
import this repository and cannot depend on ``rdflib``, so the allowlist travels
as data rather than as a query.

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

from ..context import check_context_against_reference, load_context
from ..reference import TARGET_VERSION, UPSTREAM_COMMIT, load_reference

OUTPUT_PATH = Path(__file__).resolve().parent / "official-property-names.json"


def curies() -> list[str]:
    """Sorted full CURIEs of every official Sport Schema property.

    A local name is not a term. ``startDateTime`` is declared by
    ``.../ontologies/main/`` and by nothing else, so a local-name allowlist
    accepts ``spsocstat:startDateTime`` — a property the soccer statistics
    ontology does not declare — and ``notpinned:shotsTotal``, which expands to
    nothing at all. Both are near-misses the allowlist exists to catch, so
    membership is the whole ``prefix:localName``.

    The prefix side comes from the shared context and the IRI side from the pin,
    which is what makes a CURIE here evidence rather than a convention: a prefix
    the shared context does not bind is a prefix no emitted document can carry,
    and ``check_context_against_reference`` has already proved every binding is a
    verbatim copy of what the pin declares. Upstream binds golf under both
    ``spgolf`` and ``spgolstat``, so both spellings of its properties appear —
    that is what upstream says, and a serializer emitting either is right.

    Properties only. A class name here would let ``spsocstat:Team`` through as a
    statistic.
    """
    drift = check_context_against_reference()
    if drift:
        raise RuntimeError(
            "the shared context disagrees with the pin, so its prefixes are not "
            "evidence of anything: {0}".format(drift)
        )
    reference = load_reference()
    names = set()
    for prefix, namespace in load_context().items():
        if namespace not in reference.official_namespaces:
            continue
        for iri in reference.properties:
            if iri.startswith(namespace) and iri != namespace:
                names.add("{0}:{1}".format(prefix, iri[len(namespace):]))
    return sorted(names)


def render() -> str:
    """The exact bytes of the allowlist file, as text."""
    payload = {
        "pin": UPSTREAM_COMMIT,
        "target_version": TARGET_VERSION,
        "curies": curies(),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    OUTPUT_PATH.write_text(render(), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.relative_to(Path.cwd())}" if OUTPUT_PATH.is_relative_to(Path.cwd())
          else f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
