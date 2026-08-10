"""The shared Machina JSON-LD context, and drift checks against the pin.

``agent-templates/iptc-mappings/contexts/iptc-sport-schema-1.1.context.jsonld`` is
the single context every PR 2 serializer will use. Its value here is only as
strong as the guarantee that its prefix IRIs were copied from the pinned ontology
rather than typed from memory — so that guarantee is mechanical:
:func:`check_context_against_reference` fails if any sportschema.org or
cv.iptc.org binding disagrees with the vendored bytes.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .reference import REPO_ROOT, load_reference

#: Approved ownership path for the one shared context every serializer uses.
CONTEXT_PATH = (
    REPO_ROOT / "agent-templates" / "iptc-mappings" / "contexts"
    / "iptc-sport-schema-1.1.context.jsonld"
)

#: The Machina extension namespace. Everything IPTC 1.1 does not define lives
#: here or in ``event_view`` — never under ``sport:``.
MACHINA_NS = "https://machina.gg/ns/sport/1.0/"

#: Prefixes the shared context is allowed to define without upstream backing,
#: with the reason. Anything else outside the pin is drift.
NON_UPSTREAM_PREFIXES = {
    "machina": "Machina extension namespace; deliberately not an IPTC namespace.",
    "prov": "W3C PROV-O; Machina graphs carry provenance. Not part of IPTC Sport Schema.",
    "schema": "Alias for https://schema.org/. Upstream calls this prefix 'schemaorg'.",
}


@lru_cache(maxsize=1)
def load_context() -> dict[str, str]:
    """The prefix table from the shared context document."""
    document = json.loads(CONTEXT_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in document["@context"].items() if isinstance(v, str)}


def check_context_against_reference() -> list[dict]:
    """Findings where the shared context disagrees with the pinned artefacts.

    An empty list means every IPTC-owned IRI in the shared context is a verbatim
    copy of what the pin declares.
    """
    reference = load_reference()
    context = load_context()
    findings: list[dict] = []

    for prefix, iri in sorted(context.items()):
        upstream = reference.prefixes.get(prefix)
        if upstream is not None:
            if upstream != iri:
                findings.append({
                    "code": "prefix-iri-drift",
                    "prefix": prefix,
                    "context_iri": iri,
                    "pinned_iri": upstream,
                })
            continue
        if prefix in NON_UPSTREAM_PREFIXES:
            continue
        if iri.startswith("https://sportschema.org/") or iri.startswith("http://cv.iptc.org/"):
            findings.append({
                "code": "prefix-not-in-pin",
                "prefix": prefix,
                "context_iri": iri,
                "detail": "IPTC-owned IRI with no matching @prefix in the pinned artefacts.",
            })

    # Every IPTC ontology namespace in the pin must be reachable from the shared
    # context, otherwise a PR 2 serializer has no way to emit a term from it.
    reachable = set(context.values())
    for prefix, iri in sorted(reference.prefixes.items()):
        if iri.startswith("https://sportschema.org/ontologies/") and iri not in reachable:
            findings.append({
                "code": "pinned-namespace-unreachable",
                "prefix": prefix,
                "pinned_iri": iri,
                "detail": "Pinned ontology namespace is not bound by the shared context.",
            })

    return findings
