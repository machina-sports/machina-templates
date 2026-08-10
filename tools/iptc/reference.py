"""Loading and integrity-checking the pinned IPTC Sport Schema 1.1 reference.

Everything here reads only from
``agent-templates/iptc-mappings/references/iptc-sport-schema-1.1/``. There is no
network access and no credential use anywhere in this package: the whole point of
pinning the upstream bytes is that conformance can be re-established offline,
years from now, against exactly the artefacts we validated against.

The vendored reference and the shared context live next to the mappings they
govern, under ``agent-templates/iptc-mappings/``, because that is the artefact the
PR 2 serializers consume. The harness that reads them lives under ``tools/iptc/``,
because that is operator tooling and is not installed as a template.

Two upstream syntax defects at the pinned commit are worked around by in-memory
shims. Both are documented in the reference directory's ``UPSTREAM.md``, both are
reported by the harness so they can never become invisible, and neither ever
touches the vendored bytes.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from rdflib import Graph, Literal, RDF, URIRef
from rdflib.namespace import OWL, RDFS, SKOS
from rdflib.namespace import Namespace

SH = Namespace("http://www.w3.org/ns/shacl#")

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent.parent

#: Approved ownership path for the vendored upstream artefacts.
REFERENCE_ROOT = (
    REPO_ROOT / "agent-templates" / "iptc-mappings" / "references" / "iptc-sport-schema-1.1"
)

#: The machine-readable commit manifest inside REFERENCE_ROOT.
PIN_MANIFEST_PATH = REFERENCE_ROOT / "upstream-commit.json"

#: The official SHACL shape graph, under the approved ``shacl/`` directory name.
SHACL_PATH = REFERENCE_ROOT / "shacl" / "iptc-sport-shacl.ttl"

#: Files inside REFERENCE_ROOT that are Machina-authored rather than vendored
#: upstream bytes, and are therefore deliberately absent from the manifest. Every
#: other file under REFERENCE_ROOT must be listed in ``upstream-commit.json``.
MACHINA_AUTHORED_REFERENCE_FILES = frozenset({
    "LICENSE.md", "UPSTREAM.md", "upstream-commit.json",
})

UPSTREAM_REPOSITORY = "https://github.com/iptc/sport-schema"
UPSTREAM_COMMIT = "0e77bf8678f3702fe81c28673bede35efe47d633"
TARGET_VERSION = "1.1"
UPSTREAM_LICENSE = "CC-BY-4.0"

#: The one official base IRI for the IPTC Sport Schema main ontology, read from
#: the pinned ``tools/prefixes.ttl`` and confirmed by every ontology header.
OFFICIAL_MAIN_NS = "https://sportschema.org/ontologies/main/"

#: NewsCode scheme IRIs all live under this stem.
NEWSCODE_STEM = "http://cv.iptc.org/newscodes/"

#: A ``@prefix``/``@base`` directive that ends at the IRI, with no ``.``.
#: Upstream defect 1. See UPSTREAM.md.
_UNTERMINATED_DIRECTIVE = re.compile(r"^\s*@(?:prefix|base)\b.*?>\s*$")


class ReferenceIntegrityError(RuntimeError):
    """A vendored file does not match the sha256 recorded in upstream-commit.json."""


def _repair_unterminated_directives(text: str) -> str:
    """Append the missing Turtle statement terminator to prefix directives.

    Deterministic and narrow: a line is rewritten only when it is a
    ``@prefix``/``@base`` directive whose last non-whitespace character is ``>``.
    Nothing else in the document is touched.
    """
    out = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if _UNTERMINATED_DIRECTIVE.match(body):
            newline = line[len(body):] or "\n"
            out.append(f"{body} .{newline}")
        else:
            out.append(line)
    return "".join(out)


def parse_turtle(path: Path, graph: Graph | None = None) -> tuple[Graph, bool]:
    """Parse a vendored Turtle file, shimming upstream defect 1 if required.

    Returns the graph and whether the shim was needed. The file is always
    attempted as-is first, so a future pin bump that fixes the defect upstream
    silently stops using the shim.
    """
    graph = Graph() if graph is None else graph
    raw = path.read_text(encoding="utf-8")
    try:
        graph.parse(data=raw, format="turtle")
        return graph, False
    except Exception:
        graph.parse(data=_repair_unterminated_directives(raw), format="turtle")
        return graph, True


@dataclass(frozen=True)
class VocabularyScheme:
    """One pinned SKOS concept scheme."""

    prefix: str
    scheme_iri: str
    source: str
    concepts: frozenset[str]

    def code(self, iri: str) -> str | None:
        """The code part of ``iri`` if it belongs to this scheme, else None."""
        return iri[len(self.scheme_iri):] if iri.startswith(self.scheme_iri) else None


@dataclass
class PinnedReference:
    """Every fact the harness needs from the pinned upstream, loaded once."""

    manifest: dict
    prefixes: dict[str, str]
    official_namespaces: frozenset[str]
    classes: frozenset[str]
    properties: frozenset[str]
    schemes: dict[str, VocabularyScheme]
    base_graph: Graph
    shapes_graph: Graph
    shims_applied: dict[str, object] = field(default_factory=dict)

    # -- term questions -------------------------------------------------------

    def is_official_term(self, iri: str) -> bool:
        return iri in self.classes or iri in self.properties

    def official_namespace_of(self, iri: str) -> str | None:
        for ns in self.official_namespaces:
            if iri.startswith(ns) and iri != ns:
                return ns
        return None

    def main_local_names(self) -> frozenset[str]:
        n = len(OFFICIAL_MAIN_NS)
        return frozenset(
            t[n:] for t in (self.classes | self.properties) if t.startswith(OFFICIAL_MAIN_NS)
        )

    # -- vocabulary questions -------------------------------------------------

    def scheme_for(self, iri: str) -> VocabularyScheme | None:
        for scheme in self.schemes.values():
            if scheme.code(iri) is not None:
                return scheme
        return None

    def newscode_scheme_name(self, iri: str) -> str | None:
        """The scheme segment of a NewsCode IRI, whether or not it is pinned."""
        if not iri.startswith(NEWSCODE_STEM):
            return None
        rest = iri[len(NEWSCODE_STEM):]
        return rest.split("/", 1)[0] or None


def verify_manifest() -> list[dict]:
    """Confirm the pinned reference tree is exactly what the manifest describes.

    Four assertions, and the third is the one that makes the other three worth
    anything:

    1. every listed file exists and matches its recorded sha256 and byte size;
    2. ``file_count`` and ``total_bytes`` match what was actually found;
    3. **no file under REFERENCE_ROOT is unlisted.** :func:`load_reference` reaches
       the reference tree by glob, not by manifest, so an extra ``.ttl`` dropped
       into ``vocabularies/`` would be loaded into the ontology, the shapes or a
       concept scheme while every recorded hash still verified. Hashing only the
       listed files proves nothing about what the loader actually reads;
    4. the manifest pins the same commit this module does.

    Raises on any of them. A silently-altered reference tree invalidates every
    conformance claim downstream of it, so this is a hard failure rather than a
    finding.
    """
    manifest = json.loads(PIN_MANIFEST_PATH.read_text(encoding="utf-8"))
    checked = []
    listed: set[str] = set()
    total_bytes = 0
    for entry in manifest["files"]:
        path = REFERENCE_ROOT / entry["vendored_path"]
        if not path.is_file():
            raise ReferenceIntegrityError(f"missing vendored file: {entry['vendored_path']}")
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry["sha256"]:
            raise ReferenceIntegrityError(
                f"sha256 mismatch for {entry['vendored_path']}: "
                f"expected {entry['sha256']}, found {digest}"
            )
        if len(data) != entry["size_bytes"]:
            raise ReferenceIntegrityError(
                f"size mismatch for {entry['vendored_path']}: "
                f"manifest says {entry['size_bytes']}, found {len(data)}"
            )
        listed.add(entry["vendored_path"])
        total_bytes += len(data)
        checked.append({"vendored_path": entry["vendored_path"], "sha256": digest})

    if manifest["file_count"] != len(checked):
        raise ReferenceIntegrityError(
            f"upstream-commit.json declares file_count {manifest['file_count']} but "
            f"lists {len(checked)} file(s)"
        )
    if manifest["total_bytes"] != total_bytes:
        raise ReferenceIntegrityError(
            f"upstream-commit.json declares total_bytes {manifest['total_bytes']} but "
            f"the listed files total {total_bytes}"
        )

    unlisted = sorted(
        relative
        for path in REFERENCE_ROOT.rglob("*")
        if path.is_file()
        for relative in [path.relative_to(REFERENCE_ROOT).as_posix()]
        if relative not in listed and relative not in MACHINA_AUTHORED_REFERENCE_FILES
    )
    if unlisted:
        raise ReferenceIntegrityError(
            "unmanifested file(s) under the pinned reference root: "
            + ", ".join(unlisted)
            + ". The loader reads this tree by glob, so an unlisted file would be "
            "loaded without ever being hashed. Either vendor it properly and "
            "regenerate upstream-commit.json, or remove it."
        )

    if manifest["upstream_commit"] != UPSTREAM_COMMIT:
        raise ReferenceIntegrityError(
            f"upstream-commit.json pins {manifest['upstream_commit']} but reference.py "
            f"pins {UPSTREAM_COMMIT}"
        )
    return checked


def _read_prefixes() -> dict[str, str]:
    """Prefix bindings as declared by the pinned artefacts themselves.

    Read from every ``@prefix`` directive in the vendored ontologies, shapes,
    vocabularies and ``tools/prefixes.ttl``. Nothing is inferred from a prefix
    name: upstream binds golf under both ``spgolf`` and ``spgolstat``, and both
    survive here because both are what upstream actually says.
    """
    pattern = re.compile(r"^@prefix\s+([A-Za-z][A-Za-z0-9_-]*):\s*<([^>]+)>")
    sources = [
        *sorted((REFERENCE_ROOT / "ontologies").glob("*.ttl")),
        *sorted((REFERENCE_ROOT / "shacl").glob("*.ttl")),
        *sorted((REFERENCE_ROOT / "vocabularies").glob("*.ttl")),
        REFERENCE_ROOT / "tools" / "prefixes.ttl",
    ]
    prefixes: dict[str, str] = {}
    for path in sources:
        for line in path.read_text(encoding="utf-8").splitlines():
            match = pattern.match(line)
            if match:
                prefixes.setdefault(match.group(1), match.group(2))
    return prefixes


def _ontology_terms(graph: Graph) -> tuple[frozenset[str], frozenset[str]]:
    class_types = (OWL.Class, RDFS.Class)
    property_types = (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, RDF.Property)
    classes = {str(s) for t in class_types for s in graph.subjects(RDF.type, t) if isinstance(s, URIRef)}
    properties = {str(s) for t in property_types for s in graph.subjects(RDF.type, t) if isinstance(s, URIRef)}
    return frozenset(classes), frozenset(properties)


def _strip_orphan_ignored_properties(shapes: Graph) -> int:
    """Shim upstream defect 2: ``sh:ignoredProperties`` without ``sh:closed``.

    Per the SHACL specification such a statement constrains nothing, so removing
    it is semantics-preserving. pyshacl otherwise refuses to load the shapes at
    all.
    """
    dropped = 0
    for subject, predicate, obj in list(shapes.triples((None, SH.ignoredProperties, None))):
        if (subject, SH.closed, Literal(True)) not in shapes:
            shapes.remove((subject, predicate, obj))
            dropped += 1
    return dropped


@lru_cache(maxsize=1)
def load_reference() -> PinnedReference:
    """Load the pinned reference once per process."""
    verified = verify_manifest()

    repaired: list[str] = []

    ontology_graph = Graph()
    for path in sorted((REFERENCE_ROOT / "ontologies").glob("*.ttl")):
        _, shimmed = parse_turtle(path, ontology_graph)
        if shimmed:
            repaired.append(f"ontologies/{path.name}")
    classes, properties = _ontology_terms(ontology_graph)

    # The official validation procedure (upstream tools/shacl-validate.sh) merges
    # the ontology AND every vocabulary into the data graph before validating, so
    # that rdfs:subClassOf and skos:inScheme resolve. Reproduce that exactly.
    base_graph = Graph()
    for triple in ontology_graph:
        base_graph.add(triple)

    schemes: dict[str, VocabularyScheme] = {}
    for path in sorted((REFERENCE_ROOT / "vocabularies").glob("*.ttl")):
        vocab = Graph()
        _, shimmed = parse_turtle(path, vocab)
        if shimmed:
            repaired.append(f"vocabularies/{path.name}")
        for triple in vocab:
            base_graph.add(triple)
        for scheme_iri in {str(s) for s in vocab.subjects(RDF.type, SKOS.ConceptScheme)}:
            concepts = frozenset(
                str(c)
                for c in vocab.subjects(SKOS.inScheme, URIRef(scheme_iri))
                if isinstance(c, URIRef)
            )
            schemes[scheme_iri] = VocabularyScheme(
                prefix=path.stem,
                scheme_iri=scheme_iri,
                source=f"vocabularies/{path.name}",
                concepts=concepts,
            )

    shapes_graph = Graph()
    _, shapes_shimmed = parse_turtle(SHACL_PATH, shapes_graph)
    if shapes_shimmed:
        repaired.append("shacl/iptc-sport-shacl.ttl")
    dropped = _strip_orphan_ignored_properties(shapes_graph)

    prefixes = _read_prefixes()
    official_namespaces = frozenset(
        iri for iri in prefixes.values() if iri.startswith("https://sportschema.org/ontologies/")
    )

    return PinnedReference(
        manifest=json.loads(PIN_MANIFEST_PATH.read_text(encoding="utf-8")),
        prefixes=prefixes,
        official_namespaces=official_namespaces,
        classes=classes,
        properties=properties,
        schemes=schemes,
        base_graph=base_graph,
        shapes_graph=shapes_graph,
        shims_applied={
            "manifest_files_verified": len(verified),
            "unterminated_prefix_directive_repairs": sorted(repaired),
            "orphan_sh_ignoredproperties_dropped": dropped,
        },
    )
