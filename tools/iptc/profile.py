"""Layer 3: the Machina IPTC profile.

The official SHACL shapes are necessary but not sufficient. They say nothing
about which JSON-LD context a payload must use, whether a NewsCode arrived as an
IRI or as a bare string, whether an absent fact was omitted or fabricated as
``null``/``""``/``"Unknown"``, or whether resources were flattened into one node.
Those are exactly the choices IPTC leaves open and the ones this repository has
historically got wrong, so they are checked here.

Every rule implemented here is specified in
``docs/rfcs/001-machina-iptc-sport-schema-profile.md``. The RFC is normative; this
module is its executable form. If they disagree, the RFC is right and this is a
bug.

These checks run over the **source JSON**, not the expanded RDF, and that is
deliberate. A payload whose ``sport`` prefix points at the wrong IRI expands to
triples in a namespace nobody owns; by the time you are looking at the graph, the
evidence that the author wrote ``sport:Venue`` is gone.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

from .context import MACHINA_NS
from .reference import (
    NEWSCODE_STEM,
    OFFICIAL_MAIN_NS,
    PACKAGE_ROOT,
    TARGET_VERSION,
    load_reference,
)

RULES_PATH = PACKAGE_ROOT / "rules" / "provider-leak-terms.json"

JSONLD_KEYWORDS = {
    "@base", "@container", "@context", "@direction", "@graph", "@id", "@import",
    "@included", "@index", "@json", "@language", "@list", "@nest", "@none",
    "@prefix", "@propagate", "@protected", "@reverse", "@set", "@type",
    "@value", "@version", "@vocab",
}

#: Values that assert a fact the provider never supplied. Omission beats
#: fabrication; see the RFC's omission and null rules.
PLACEHOLDER_VALUES = {
    "", "unknown", "Unknown", "UNKNOWN", "UNK", "unk", "TBD", "tbd", "N/A", "n/a",
    "Unknown Player", "Unknown Team", "Unknown Venue", "Unknown City",
    "Unknown Country", "Unknown Competition", "Unknown Season", "Unknown Round",
    "Unknown Phase", "Unknown Category", "Unknown Group", "Unknown Channel",
    "Unknown Title", "unknown Phase",
}

#: Properties whose value must be an ``xsd:date``.
DATE_PROPERTIES = {"sport:startDate", "sport:endDate", "sport:dateOfBirth"}

#: Properties whose value must be an ``xsd:dateTime``.
DATETIME_PROPERTIES = {"sport:startDateTime", "sport:endDateTime", "sport:actionDateTime"}

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_CURIE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(?!//)([^\s]*)$")

#: URI schemes that are legitimately CURIE-shaped and must not be mistaken for an
#: unbound prefix. `urn:` matters most: every provider identifier in this
#: repository is a URN.
URI_SCHEMES = frozenset({
    "urn", "http", "https", "mailto", "tel", "data", "file", "ftp", "ftps",
    "doi", "isbn", "uuid", "did", "geo", "news", "sms", "ws", "wss",
})


@dataclass
class Finding:
    code: str
    pointer: str
    detail: str
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        out = {"code": self.code, "pointer": self.pointer, "detail": self.detail}
        out.update(self.extra)
        return out


@lru_cache(maxsize=1)
def provider_leak_index() -> dict[str, list[str]]:
    """local name -> providers that field name belongs to."""
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    index: dict[str, list[str]] = {}
    for provider, spec in rules["providers"].items():
        for local in spec["local_names"]:
            index.setdefault(local, []).append(provider)
    return {k: sorted(v) for k, v in index.items()}


@dataclass
class ProfileResult:
    findings: list[dict]
    node_ids: list[str]
    duplicate_ids: list[dict]
    sport_terms: list[str]
    unknown_sport_terms: list[dict]
    provider_leaks: list[dict]
    newscode_values: list[dict]
    context_bindings: dict[str, str]

    @property
    def conforms(self) -> bool:
        return not self.findings


class _Walker:
    """One pass over the source JSON collecting everything the profile needs."""

    def __init__(self, reference) -> None:
        self.reference = reference
        self.official_local_names = reference.main_local_names()
        self.leaks = provider_leak_index()

        self.findings: list[Finding] = []
        self.node_ids: list[tuple[str, str]] = []          # (@id, pointer)
        self.sport_terms: set[str] = set()
        self.unknown_sport_terms: dict[str, list[str]] = {}
        self.provider_leaks: list[dict] = []
        self.newscode_values: list[dict] = []
        self.context_bindings: dict[str, str] = {}
        self._context_stack: list[dict[str, str]] = []

    # -- helpers --------------------------------------------------------------

    def _active_context(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for layer in self._context_stack:
            merged.update(layer)
        return merged

    def add(self, code: str, pointer: str, detail: str, **extra) -> None:
        self.findings.append(Finding(code, pointer, detail, extra))

    # -- term handling --------------------------------------------------------

    def _note_term(self, term: str, pointer: str, kind: str) -> None:
        """Record a ``prefix:local`` term seen as a key or as an ``@type``."""
        match = _CURIE.match(term)
        if not match:
            return
        prefix, local = match.group(1), match.group(2)
        context = self._active_context()

        if prefix == "sport":
            self.sport_terms.add(term)
            if local not in self.official_local_names:
                self.unknown_sport_terms.setdefault(term, []).append(pointer)
                self.add(
                    "invented-sport-term",
                    pointer,
                    f"'{term}' is not declared by IPTC Sport Schema {TARGET_VERSION} "
                    f"({OFFICIAL_MAIN_NS}). Machina extensions belong under "
                    f"machina: ({MACHINA_NS}) or in event_view.",
                    term=term,
                    kind=kind,
                )
            providers = self.leaks.get(local)
            if providers:
                self.provider_leaks.append({
                    "term": term,
                    "local_name": local,
                    "pointer": pointer,
                    "kind": kind,
                    "providers": providers,
                    "reason": "provider-field-transliteration",
                })
                self.add(
                    "provider-property-in-iptc-namespace",
                    pointer,
                    f"'{term}' is a {', '.join(providers)} field name emitted in an "
                    f"official IPTC namespace.",
                    term=term,
                )
            return

        if prefix in context:
            return
        if prefix in JSONLD_KEYWORDS:
            return
        self.add(
            "undeclared-prefix",
            pointer,
            f"Prefix '{prefix}:' is used but not bound by any @context in scope, "
            f"so '{term}' expands to a relative IRI rather than a term.",
            term=term,
        )

    # -- value handling -------------------------------------------------------

    def _note_value(self, key: str, value, pointer: str) -> None:
        if isinstance(value, str) and value.startswith(NEWSCODE_STEM):
            self.newscode_values.append({
                "pointer": pointer, "property": key, "value": value, "form": "literal",
            })
            self.add(
                "newscode-not-a-node",
                pointer,
                "A NewsCode was emitted as a plain string. Without an @id (or an "
                "@type: @id term definition) it expands to a literal, so no "
                "consumer can follow it to the concept.",
                property=key, value=value,
            )
            return

        if isinstance(value, str):
            curie = _CURIE.match(value)
            prefix = curie.group(1) if curie else None
            if prefix and prefix.lower() not in URI_SCHEMES and prefix not in self._active_context():
                # A value shaped like `prefix:local` whose prefix nothing binds is
                # broken either way it is read: JSON-LD leaves it a plain literal,
                # while the author plainly meant a controlled-vocabulary reference.
                # Note this catches the real in-repo defect, where the value uses
                # `spsocaction:` — upstream's prefix for that scheme is named
                # `spsocactiontype`, so keying the check on known prefix NAMES
                # missed it entirely.
                self.newscode_values.append({
                    "pointer": pointer, "property": key, "value": value,
                    "form": "undeclared-prefix",
                })
                self.add(
                    "controlled-vocabulary-undeclared-prefix",
                    pointer,
                    f"Value '{value}' uses prefix '{prefix}:' which no @context in "
                    f"scope binds, so it cannot resolve to a controlled-vocabulary "
                    f"concept.",
                    property=key, value=value,
                )

        if key in DATE_PROPERTIES and isinstance(value, str) and value and not _ISO_DATE.match(value):
            self.add("date-datatype", pointer,
                     f"'{key}' must be an xsd:date (YYYY-MM-DD); found '{value}'.",
                     property=key, value=value)
        if key in DATETIME_PROPERTIES and isinstance(value, str) and value and not _ISO_DATETIME.match(value):
            self.add("datetime-datatype", pointer,
                     f"'{key}' must be an xsd:dateTime; found '{value}'.",
                     property=key, value=value)

    # -- traversal ------------------------------------------------------------

    def walk(self, node, pointer: str = "", *, depth: int = 0, in_graph: bool = False) -> None:
        if isinstance(node, list):
            for index, item in enumerate(node):
                self.walk(item, f"{pointer}/{index}", depth=depth, in_graph=in_graph)
            return
        if not isinstance(node, dict):
            return

        pushed = False
        if "@context" in node:
            ctx = node["@context"]
            if isinstance(ctx, dict):
                bindings = {k: v for k, v in ctx.items() if isinstance(v, str)}
                self._context_stack.append(bindings)
                pushed = True
                for prefix, iri in bindings.items():
                    self.context_bindings.setdefault(prefix, iri)
                self._check_context(bindings, f"{pointer}/@context")
            elif isinstance(ctx, str):
                self._context_stack.append({})
                pushed = True
                self.context_bindings.setdefault("@context(remote)", ctx)
            if depth > 0:
                self.add(
                    "nested-context",
                    f"{pointer}/@context",
                    "A nested @context makes one document expand under two "
                    "vocabularies. The profile requires exactly one document-level "
                    "context, shared with every other serializer.",
                )

        types = node.get("@type")
        type_list = types if isinstance(types, list) else ([types] if isinstance(types, str) else [])

        if "@value" in node:
            # A value node. Its @type is a DATATYPE, not a class, so none of the
            # resource rules below apply — an xsd:dateTime is not a resource that
            # needs an @id. The lexical form was already checked by the parent.
            for t in type_list:
                self._note_term(t, f"{pointer}/@type", "datatype")
            if pushed:
                self._context_stack.pop()
            return

        for t in type_list:
            self._note_term(t, f"{pointer}/@type", "class")

        node_id = node.get("@id")
        # A bare {"@id": ...} is a REFERENCE to a resource, not a second
        # description of it. Counting references as descriptions would make every
        # correctly normalised graph look like it had duplicate identifiers.
        describes = any(key != "@id" for key in node)
        if isinstance(node_id, str) and node_id and describes:
            self.node_ids.append((node_id, pointer or "/"))

        if type_list and not isinstance(node_id, str):
            self.add("missing-node-id", pointer or "/",
                     f"A node typed {type_list} has no @id. Blank nodes are not "
                     f"addressable, so no consumer can reference the resource.",
                     types=type_list)

        if type_list and depth > 0 and not in_graph:
            self.add(
                "nested-resource",
                pointer or "/",
                f"A typed resource {type_list} is nested inside another resource. "
                f"The profile requires distinct resources as siblings in a "
                f"top-level @graph, referenced by @id.",
                types=type_list,
            )

        for key, value in node.items():
            child_pointer = f"{pointer}/{key}"
            if key == "@context":
                continue
            if key in ("@id", "@type"):
                continue

            if key in JSONLD_KEYWORDS:
                pass
            elif _CURIE.match(key):
                self._note_term(key, child_pointer, "property")
            else:
                context = self._active_context()
                if key not in context:
                    self.add(
                        "undefined-term",
                        child_pointer,
                        f"Key '{key}' is neither a JSON-LD keyword nor a term "
                        f"defined by any @context in scope. JSON-LD expansion drops "
                        f"it silently, so the value is lost.",
                        property=key,
                    )

            if value is None:
                self.add("null-value", child_pointer,
                         f"'{key}' is null. An absent fact must be omitted, not "
                         f"asserted as null.", property=key)
            elif isinstance(value, str) and value in PLACEHOLDER_VALUES:
                self.add("placeholder-value", child_pointer,
                         f"'{key}' carries the placeholder '{value}'. A fabricated "
                         f"default is a fact the provider never supplied.",
                         property=key, value=value)
            elif isinstance(value, dict) and "@value" in value:
                # A typed value node: {"@value": ..., "@type": "xsd:dateTime"}.
                # Datatype rules apply to the lexical form inside @value.
                self._note_value(key, value["@value"], f"{child_pointer}/@value")
                self.walk(value, child_pointer, depth=depth + 1, in_graph=False)
            elif isinstance(value, (dict, list)):
                self.walk(value, child_pointer, depth=depth + 1,
                          in_graph=(key == "@graph"))
            else:
                self._note_value(key, value, child_pointer)

        if pushed:
            self._context_stack.pop()

    def _check_context(self, bindings: dict[str, str], pointer: str) -> None:
        from .context import load_context

        shared = load_context()
        sport_iri = bindings.get("sport")
        if sport_iri is not None and sport_iri != OFFICIAL_MAIN_NS:
            self.add(
                "sport-namespace-not-official",
                f"{pointer}/sport",
                f"The 'sport' prefix is bound to '{sport_iri}'. IPTC Sport Schema "
                f"1.1 declares '{OFFICIAL_MAIN_NS}' (pinned "
                f"tools/prefixes.ttl and every ontology header). Every sport: term "
                f"in this document therefore expands into a namespace nobody owns.",
                found=sport_iri, expected=OFFICIAL_MAIN_NS,
            )
        for prefix, iri in sorted(bindings.items()):
            expected = shared.get(prefix)
            if expected is not None and expected != iri and prefix != "sport":
                self.add(
                    "context-prefix-drift",
                    f"{pointer}/{prefix}",
                    f"Prefix '{prefix}:' is bound to '{iri}' but the shared Machina "
                    f"context binds it to '{expected}'.",
                    found=iri, expected=expected,
                )


def check(document) -> ProfileResult:
    """Run every profile rule over one parsed JSON-LD document."""
    reference = load_reference()
    walker = _Walker(reference)
    walker.walk(document)

    if isinstance(document, dict) and "@context" not in document:
        walker.add("missing-document-context", "/",
                   "No document-level @context. Without one the payload has no "
                   "vocabulary and expands to nothing addressable.")
    if isinstance(document, list):
        walker.add("no-graph-envelope", "/",
                   "The document is a bare JSON array. The profile requires a "
                   "single object with one @context and one @graph.")
    elif isinstance(document, dict) and "@graph" not in document:
        walker.add("no-graph-envelope", "/",
                   "The document has no @graph. The profile requires resources as "
                   "siblings in a top-level @graph rather than one nested tree.")

    seen: dict[str, list[str]] = {}
    for node_id, pointer in walker.node_ids:
        seen.setdefault(node_id, []).append(pointer)
    duplicates = [
        {"@id": node_id, "occurrences": len(pointers), "pointers": pointers}
        for node_id, pointers in sorted(seen.items()) if len(pointers) > 1
    ]
    for duplicate in duplicates:
        walker.add("duplicate-node-id", duplicate["pointers"][0],
                   f"@id '{duplicate['@id']}' appears {duplicate['occurrences']} "
                   f"times in one document. Two descriptions of one identifier "
                   f"cannot both be authoritative.",
                   **{"@id": duplicate["@id"], "pointers": duplicate["pointers"]})

    return ProfileResult(
        findings=[f.as_dict() for f in walker.findings],
        node_ids=[node_id for node_id, _ in walker.node_ids],
        duplicate_ids=duplicates,
        sport_terms=sorted(walker.sport_terms),
        unknown_sport_terms=[
            {"term": term, "occurrences": len(pointers), "pointers": pointers}
            for term, pointers in sorted(walker.unknown_sport_terms.items())
        ],
        provider_leaks=walker.provider_leaks,
        newscode_values=walker.newscode_values,
        context_bindings=walker.context_bindings,
    )
