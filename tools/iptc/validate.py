"""The four-layer offline validation harness.

| Layer | What it proves |
|---|---|
| 1 JSON-LD expansion / RDF parse | the document is valid JSON-LD and expands to parseable RDF |
| 2 official IPTC SHACL           | it conforms to the shapes shipped with the pinned 1.1 ontology |
| 3 Machina profile               | it satisfies the constraints IPTC leaves open (see profile.py) |
| 4 controlled vocabulary         | every NewsCode is a real code from a pinned vocabulary |

and four counters that are gates, not metrics:

* unknown ``sport:`` terms
* invalid NewsCode values
* duplicate resource IDs
* provider-specific properties in the IPTC namespace

Everything runs offline against
``agent-templates/iptc-mappings/references/iptc-sport-schema-1.1/``. No network, no
credentials, no provider calls. Layer 1 enforces that rather than assuming it: a
document that would make the JSON-LD processor fetch a context is rejected before
the processor ever sees it. See :func:`context_loader_findings`.

Two kinds of document arrive here. A **graph document** is the JSON-LD the four
layers describe. A **canonical envelope** (RFC 002 §9) carries that same graph
under ``machina_sports_schema.sport_schema_graph`` alongside the rights claim a
consumer is gated on; it is unwrapped and its inner graph validated identically,
under the caller's own path. An envelope additionally gets a ``rights_gate``
result, which :func:`rights_findings` decides and which fails closed. A graph
document gets no such result at all — rights live in the envelope, and inventing
a verdict for a document that cannot carry one is worse than reporting none.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pyshacl
from rdflib import RDF, BNode, Graph, URIRef
from rdflib.namespace import SH

from . import profile
from .canonical.rights import (
    CONSUMER_TIERS,
    ENVELOPE_KEY,
    STRICT_CONSUMER_TIER,
    rights_findings,
)
from .reference import (
    NEWSCODE_STEM,
    TARGET_VERSION,
    UPSTREAM_COMMIT,
    UPSTREAM_LICENSE,
    UPSTREAM_REPOSITORY,
    load_reference,
)

HARNESS_VERSION = "1"

#: The layer name an envelope's rights verdict is reported under. It is absent
#: from a graph document's layers on purpose — see :func:`validate_payload`.
RIGHTS_LAYER = "rights_gate"

#: ``rights_findings``, ``ENVELOPE_KEY``, ``CONSUMER_TIERS`` and
#: ``STRICT_CONSUMER_TIER`` are imported from :mod:`tools.iptc.canonical.rights`
#: and re-exported, not defined here. The gate is a cross-repository rule that
#: has to be vendorable into a package which cannot import this one, and this
#: module needs pyshacl and rdflib. Re-exporting keeps every documented import
#: path — RFC 002 §9 names ``validate_graph.rights_findings`` — resolving to the
#: single implementation, rather than to a second copy that agrees until the day
#: one side is fixed.


@dataclass
class LayerResult:
    name: str
    ok: bool
    detail: dict = field(default_factory=dict)


@dataclass
class DocumentResult:
    """The complete verdict for one fixture."""

    fixture: str
    path: str
    layers: dict
    counters: dict
    conforms: bool

    def as_dict(self) -> dict:
        return {
            "fixture": self.fixture,
            "path": self.path,
            "conforms": self.conforms,
            "counters": self.counters,
            "layers": self.layers,
        }


# ---------------------------------------------------------------------------
# Layer 1
# ---------------------------------------------------------------------------

#: Human-readable reason layers 2-4 were skipped, per layer-1 failure stage.
SKIP_REASONS = {
    "json": "not run: the document is not valid JSON",
    "context": (
        "not run: the document references a JSON-LD context the offline harness "
        "will not load"
    ),
    "rdf": "not run: the document does not expand to parseable RDF",
    "envelope": (
        "not run: the canonical envelope carries no sport_schema_graph object to "
        "validate"
    ),
}


def context_loader_findings(node, pointer: str = "") -> list[dict]:
    """Every context reference that would send the JSON-LD processor off-document.

    The harness's entire value rests on being reproducible offline against pinned
    bytes, and a document is untrusted input. A JSON-LD processor will dereference
    a string ``@context``, any string inside a ``@context`` array, a string
    ``@context`` on a scoped (nested) term definition, and a ``@import`` inside a
    context — each of which is an outbound request to whatever IRI the document
    names, and a request whose result silently decides what every term in the
    document means. rdflib is never given the chance: layer 1 fails first.

    The Machina profile requires exactly one inline document-level context anyway
    (RFC §5.1, §10.1), so nothing legitimate is lost by refusing the rest.

    Returns findings sorted by pointer, so the result is byte-stable.
    """
    found: list[dict] = []
    if isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(context_loader_findings(item, f"{pointer}/{index}"))
        return sorted(found, key=lambda f: (f["pointer"], f["code"]))
    if not isinstance(node, dict):
        return found

    for key, value in node.items():
        here = f"{pointer}/{key}"
        if key == "@import":
            found.append({
                "code": "context-import",
                "pointer": here,
                "reference": value if isinstance(value, str) else None,
                "detail": "@import pulls in a second context document by IRI.",
            })
        elif key == "@context":
            for ref_pointer, reference in _context_references(value, here):
                found.append({
                    "code": "remote-context",
                    "pointer": ref_pointer,
                    "reference": reference,
                    "detail": "A context given as a string is dereferenced by IRI.",
                })
        # Recurse into everything, including context values, so a scoped context
        # nested inside a term definition cannot hide a reference.
        found.extend(context_loader_findings(value, here))
    return sorted(found, key=lambda f: (f["pointer"], f["code"]))


def _context_references(value, pointer: str) -> list[tuple[str, str]]:
    """String context references in an ``@context`` value, with their pointers."""
    if isinstance(value, str):
        return [(pointer, value)]
    if isinstance(value, list):
        return [
            (f"{pointer}/{index}", item)
            for index, item in enumerate(value) if isinstance(item, str)
        ]
    return []


def parse_jsonld(path: Path) -> tuple[Graph | None, dict]:
    """Parse JSON, reject off-document contexts, then expand to RDF.

    Returns (graph or None, detail). The context check runs **before** rdflib is
    handed the bytes, so a rejected document never reaches a loader.
    """
    raw = path.read_text(encoding="utf-8")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, {
            "stage": "json",
            "error": f"{type(exc).__name__}: {exc}",
            "document": None,
        }
    return expand_jsonld(document, raw=raw)


def expand_jsonld(document, *, raw: str | None = None) -> tuple[Graph | None, dict]:
    """The same check over an already-parsed document, with no file behind it.

    This is what lets a canonical envelope's inner graph reach layer 1 without
    being written to a transient file first: a temporary artifact would have to be
    created, named and cleaned up, and the result would report its path instead of
    the one the caller asked about.

    ``raw`` is the document's own bytes when they exist; rdflib is handed those in
    preference to a re-serialization, so validating a file stays byte-for-byte the
    operation it always was.
    """
    blocked = context_loader_findings(document)
    if blocked:
        return None, {
            "stage": "context",
            "error": (
                f"{len(blocked)} off-document JSON-LD context reference(s): "
                + ", ".join(f"{f['code']} at {f['pointer']}" for f in blocked)
                + ". The harness is offline by construction and will not "
                "dereference a context; the profile requires one inline "
                "document-level context."
            ),
            "blocked_context_references": blocked,
            "document": document,
        }

    graph = Graph()
    try:
        # base= keeps relative IRIs resolvable without reaching for the network.
        graph.parse(data=raw if raw is not None else json.dumps(document),
                    format="json-ld", base="urn:machina:iptc:fixture:")
    except Exception as exc:
        return None, {
            "stage": "rdf",
            "error": f"{type(exc).__name__}: {exc}",
            "document": document,
        }
    return graph, {"stage": "ok", "triples": len(graph), "document": document}


# ---------------------------------------------------------------------------
# Layer 2
# ---------------------------------------------------------------------------

def _shacl_results(report: Graph) -> list[dict]:
    """Extract validation results in a form that is stable across runs.

    Blank-node identifiers are normalised to ``_:blank``. rdflib mints a fresh
    random label for every blank node on every parse, and the official shapes use
    anonymous property shapes heavily, so leaving the raw labels in would make the
    checked-in report differ from itself on consecutive runs — turning the CI
    snapshot gate into a coin toss. The path and constraint component are what
    identify a violation; the shape's internal label is not.
    """
    out = []
    for result in report.subjects(URIRef(f"{SH}resultSeverity"), None):
        entry = {}
        for key, predicate in (
            ("severity", SH.resultSeverity),
            ("focus_node", SH.focusNode),
            ("path", SH.resultPath),
            ("value", SH.value),
            ("message", SH.resultMessage),
            ("constraint", SH.sourceConstraintComponent),
            ("shape", SH.sourceShape),
        ):
            value = report.value(result, predicate)
            if value is not None:
                entry[key] = "_:blank" if isinstance(value, BNode) else str(value)
        out.append(entry)
    # Deterministic ordering: the report graph is unordered, and the audit is
    # snapshot-compared in CI.
    return sorted(out, key=lambda e: json.dumps(e, sort_keys=True))


def _official_target_nodes(data_graph: Graph) -> int:
    """How many nodes the official shapes actually have to say anything about.

    This is the single most important number for reading layer 2 honestly. A
    payload whose ``sport`` prefix points at the wrong IRI produces no instances
    of any official class, so every ``sh:targetClass`` matches nothing and pyshacl
    reports ``conforms=True``. That is a **vacuous** pass: the shapes were never
    exercised. Reporting it as a pass without saying so would be the most
    flattering possible lie about the baseline.
    """
    reference = load_reference()
    official_classes = {URIRef(c) for c in reference.classes}
    return sum(
        1 for _, _, obj in data_graph.triples((None, RDF.type, None))
        if obj in official_classes
    )


def official_shacl(data_graph: Graph) -> dict:
    """Validate against the pinned official shapes, the official way.

    Upstream's own ``tools/shacl-validate.sh`` merges the merged ontology and
    every vocabulary into the data graph before validating, because the shapes
    depend on ``rdfs:subClassOf`` and ``skos:inScheme``. Skipping that merge
    manufactures failures.
    """
    reference = load_reference()
    target_nodes = _official_target_nodes(data_graph)
    merged = Graph()
    for triple in reference.base_graph:
        merged.add(triple)
    for triple in data_graph:
        merged.add(triple)
    conforms, report_graph, report_text = pyshacl.validate(
        merged,
        shacl_graph=reference.shapes_graph,
        advanced=True,
        inference="none",
        abort_on_first=False,
    )
    results = _shacl_results(report_graph)
    return {
        "conforms": bool(conforms),
        "official_class_instances": target_nodes,
        "vacuous": bool(conforms) and target_nodes == 0,
        "result_count": len(results),
        "results": results,
        "report_text_head": report_text.strip().splitlines()[:1],
    }


# ---------------------------------------------------------------------------
# Layer 4
# ---------------------------------------------------------------------------

def controlled_vocabulary(data_graph: Graph, profile_result) -> dict:
    """Check every NewsCode against the pinned vocabulary TTLs.

    Three outcomes, kept distinct on purpose:

    * ``valid``        — the code is a skos:Concept in the pinned scheme.
    * ``invalid``      — the scheme is pinned and does not contain the code.
    * ``unverifiable`` — the scheme is named by upstream but no TTL for it exists
      at the pinned commit (``spsocaction`` and friends; see UPSTREAM.md). This is
      missing evidence, and it is never silently promoted to ``valid``.

    **The layer fails closed.** The profile requires every NewsCode to be provably
    present in a pinned vocabulary (RFC §9), so ``unverifiable`` fails the layer
    exactly as ``invalid`` does. Missing evidence is not evidence of correctness.
    The three categories and their counts stay separate regardless, because
    "wrong code" and "no pinned scheme to check against" need different fixes.
    """
    reference = load_reference()

    candidates: dict[str, dict] = {}
    for obj in set(data_graph.objects(None, None)):
        text = str(obj)
        if isinstance(obj, URIRef) and text.startswith(NEWSCODE_STEM):
            candidates.setdefault(text, {"value": text, "forms": set()})["forms"].add("iri")
    for entry in profile_result.newscode_values:
        if entry["form"] == "literal":
            candidates.setdefault(entry["value"], {"value": entry["value"], "forms": set()})["forms"].add("literal")

    valid, invalid, unverifiable = [], [], []
    for value, info in sorted(candidates.items()):
        record = {"value": value, "forms": sorted(info["forms"])}
        scheme_name = reference.newscode_scheme_name(value)
        record["scheme"] = scheme_name
        scheme = reference.scheme_for(value)
        if scheme is None:
            record["reason"] = (
                f"No vocabularies/{scheme_name}.ttl exists at the pinned commit, so "
                f"this code cannot be checked offline."
            )
            unverifiable.append(record)
        elif value in scheme.concepts:
            record["source"] = scheme.source
            valid.append(record)
        else:
            record["source"] = scheme.source
            record["reason"] = f"Not a skos:Concept in {scheme.scheme_iri}."
            invalid.append(record)

    undeclared = [
        {"value": e["value"], "property": e["property"], "pointer": e["pointer"],
         "reason": "Prefix is not bound by any @context in scope."}
        for e in profile_result.newscode_values if e["form"] == "undeclared-prefix"
    ]

    return {
        "ok": not invalid and not undeclared and not unverifiable,
        "valid": valid,
        "invalid": invalid,
        "undeclared_prefix": undeclared,
        "unverifiable": unverifiable,
        "pinned_scheme_count": len(reference.schemes),
    }


# ---------------------------------------------------------------------------
# The rights gate — see the re-export note above; the rule lives in
# tools/iptc/canonical/rights.py, which is vendored into sports-skills.
# ---------------------------------------------------------------------------

def envelope_block(document) -> dict | None:
    """The canonical envelope block in ``document``, or None if it carries none.

    One key decides it, because one key is what RFC 002 §9 defines. A document
    without it is a graph document and is validated as one.
    """
    if isinstance(document, dict) and isinstance(document.get(ENVELOPE_KEY), dict):
        return document[ENVELOPE_KEY]
    return None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def validate_document(path: Path, fixture: str, *, repo_root: Path,
                      consumer_tier: str = STRICT_CONSUMER_TIER) -> DocumentResult:
    """Run all four layers plus the four counters against one file."""
    relative = str(path.relative_to(repo_root))
    raw = path.read_text(encoding="utf-8")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _nothing_to_validate(fixture, relative, {
            "stage": "json",
            "error": f"{type(exc).__name__}: {exc}",
        }, rights=None)
    return validate_payload(document, fixture, path=relative,
                            consumer_tier=consumer_tier, raw=raw)


def validate_payload(document, fixture: str, *, path: str,
                     consumer_tier: str = STRICT_CONSUMER_TIER,
                     raw: str | None = None) -> DocumentResult:
    """The same verdict for an already-parsed document, reported under ``path``.

    ``path`` is the caller's logical path and is echoed verbatim: a canonical
    envelope is validated through its inner graph, but the result is about the
    document the caller named, not about an unwrapped copy of part of it.
    """
    block = envelope_block(document)
    rights = None
    payload = document
    if block is not None:
        findings = rights_findings(document, consumer_tier)
        rights = asdict(LayerResult(RIGHTS_LAYER, not findings, {
            "consumer_tier": consumer_tier,
            "finding_count": len(findings),
            "findings": findings,
        }))
        payload = block.get("sport_schema_graph")
        # The envelope's bytes are not the graph's; re-serialize the inner graph.
        raw = None
        if not isinstance(payload, dict):
            return _nothing_to_validate(fixture, path, {
                "stage": "envelope",
                "error": "machina_sports_schema.sport_schema_graph is missing or is "
                         "not an object, so the envelope carries no graph to "
                         "validate. An envelope with nothing to check does not pass.",
            }, rights=rights)

    graph, parse_detail = expand_jsonld(payload, raw=raw)
    parse_detail.pop("document", None)

    if graph is None:
        return _nothing_to_validate(fixture, path, parse_detail, rights=rights)

    layer1 = LayerResult("jsonld_parse", True, parse_detail)
    shacl = official_shacl(graph)
    # A vacuous pass is not a pass. See _official_target_nodes.
    layer2 = LayerResult("official_shacl", shacl["conforms"] and not shacl["vacuous"], shacl)

    profile_result = profile.check(payload)
    layer3 = LayerResult("machina_profile", profile_result.conforms, {
        "conforms": profile_result.conforms,
        "finding_count": len(profile_result.findings),
        "findings": profile_result.findings,
        "context_bindings": profile_result.context_bindings,
        "sport_terms_used": profile_result.sport_terms,
        "node_id_count": len(profile_result.node_ids),
    })

    vocabulary = controlled_vocabulary(graph, profile_result)
    layer4 = LayerResult("controlled_vocabulary", vocabulary["ok"], vocabulary)

    counters = {
        "unknown_sport_terms": sum(t["occurrences"] for t in profile_result.unknown_sport_terms),
        "unknown_sport_terms_distinct": len(profile_result.unknown_sport_terms),
        "invalid_newscode_values": len(vocabulary["invalid"]) + len(vocabulary["undeclared_prefix"]),
        "duplicate_resource_ids": len(profile_result.duplicate_ids),
        "provider_properties_in_iptc_namespace": len(profile_result.provider_leaks),
        "unverifiable_newscode_values": len(vocabulary["unverifiable"]),
    }

    detail = {
        "unknown_sport_terms": profile_result.unknown_sport_terms,
        "duplicate_resource_ids": profile_result.duplicate_ids,
        "provider_properties_in_iptc_namespace": profile_result.provider_leaks,
    }

    layers = {
        "jsonld_parse": asdict(layer1),
        "official_shacl": asdict(layer2),
        "machina_profile": asdict(layer3),
        "controlled_vocabulary": asdict(layer4),
        "counter_detail": detail,
    }
    if rights is not None:
        layers[RIGHTS_LAYER] = rights

    return DocumentResult(
        fixture=fixture,
        path=path,
        layers=layers,
        counters=counters,
        # ``conforms`` stays a statement about the four layers and the four
        # counters. The rights gate answers "may this consumer use it?", which is
        # a different question from "is this document conformant?" and is reported
        # as its own layer rather than folded into this one.
        conforms=layer1.ok and layer2.ok and layer3.ok and layer4.ok
        and counters["unknown_sport_terms"] == 0
        and counters["invalid_newscode_values"] == 0
        and counters["duplicate_resource_ids"] == 0
        and counters["provider_properties_in_iptc_namespace"] == 0,
    )


def _nothing_to_validate(fixture: str, path: str, parse_detail: dict,
                         *, rights: dict | None) -> DocumentResult:
    """The verdict when layer 1 never got a graph. Layers 2-4 are failures, not
    blanks, and the counters are null rather than zero: nothing was counted."""
    skipped = SKIP_REASONS[parse_detail["stage"]]
    layers = {
        "jsonld_parse": asdict(LayerResult("jsonld_parse", False, parse_detail)),
        "official_shacl": asdict(LayerResult("official_shacl", False, {
            "skipped": skipped})),
        "machina_profile": asdict(LayerResult("machina_profile", False, {
            "skipped": skipped})),
        "controlled_vocabulary": asdict(LayerResult("controlled_vocabulary", False, {
            "skipped": skipped})),
    }
    if rights is not None:
        layers[RIGHTS_LAYER] = rights
    return DocumentResult(
        fixture=fixture,
        path=path,
        layers=layers,
        counters={
            "unknown_sport_terms": None,
            "invalid_newscode_values": None,
            "duplicate_resource_ids": None,
            "provider_properties_in_iptc_namespace": None,
            "note": "Counters are null, not zero: nothing could be counted.",
        },
        conforms=False,
    )


def pin_metadata() -> dict:
    reference = load_reference()
    return {
        "harness_version": HARNESS_VERSION,
        "target_version": TARGET_VERSION,
        "upstream_repository": UPSTREAM_REPOSITORY,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_ref_note": reference.manifest["upstream_ref_note"],
        "license": UPSTREAM_LICENSE,
        "reference_files_verified": reference.shims_applied["manifest_files_verified"],
        "upstream_shims_applied": reference.shims_applied,
        "pinned_vocabulary_schemes": sorted(reference.schemes),
        "official_term_counts": {
            "classes": len(reference.classes),
            "properties": len(reference.properties),
        },
    }
