"""Inventory of every IPTC emitter, term and consumer in this repository.

PR 1 deliverable 1. This is generated rather than hand-written, for one reason:
a hand-written inventory is a snapshot of what someone noticed on one afternoon,
and PR 3's "zero known legacy consumer breakages" is scoped to it. A generated
inventory can be re-run, and a consumer it misses is a fixable tooling gap rather
than a fact nobody can recover.

Two passes:

**Emitters.** Every mapping YAML that emits a prefixed term. For each, the mapping
name, the output keys, the ``@context`` prefix bindings it declares, and a
classification of every term against the pinned ontologies.

**Consumers.** Every file that READS an IPTC field path it does not emit. These are
the field paths the consumer migration has to cover, and each one is a promise this
PR is making on that migration's behalf.

Where a classification cannot be checked offline, it says so instead of guessing —
see ``schema-org-term-unverified`` and ``newscode-unverifiable``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .extract_mapping_fixture import emitted_keys
from .fileio import markdown_document
from .profile import URI_SCHEMES, provider_leak_index
from .reference import NEWSCODE_STEM, OFFICIAL_MAIN_NS, REPO_ROOT, load_reference

#: Directories that may contain an IPTC emitter or consumer.
SCAN_ROOTS = ("agent-templates", "connectors")

#: A prefixed term, as it appears as a JSON key or an @type value.
_TERM = re.compile(r'"((?:@|[A-Za-z][A-Za-z0-9_-]*:)[A-Za-z0-9_:@-]*)"')

#: Machina workflow state keys that carry an IPTC payload. A file that reads one of
#: these is a consumer even if it never names a `sport:` term.
PAYLOAD_KEYS = (
    "sport_schema_events", "sport_schema_event", "sport_schema_teams",
    "sport_schema_players", "iptc_schema_events", "iptc_schema_ids", "iptc_events",
    "iptc_events_statistics", "iptc_events_timeline", "iptc_teams_statistics",
    "iptc_players_statistics", "iptc_players_stats", "iptc_match_statistics",
    "iptc_game_statistics", "iptc_player_statistics", "iptc_teams", "iptc_players",
    "sport-schema-event", "iptc-events",
)

#: Field paths a consumer reads off an IPTC document.
CONSUMED_PATHS = (
    "sport:competitors", "sport:competitor", "sport:status", "sport:matchStatus",
    "sport:score", "sport:homeScore", "sport:awayScore", "sport:halfTime",
    "sport:venue", "sport:competition", "sport:season", "sport:qualifier",
    "sport:label", "sport:participation", "sport:participationBy",
    "sport:actionType", "sport:minutesElapsed", "sport:periodValue",
    "sport:fieldLocation", "sport:statistics", "sport:statLabel",
    "sport:statValue", "sport:statParticipant", "sport:channels",
    "sport:channelName", "sport:abbreviation", "sport:year", "sport:round",
    "sport:stage", "sport:eventStatus", "sport:startDate", "schema:startDate",
    "schema:sportName",
)

CATEGORIES = {
    "jsonld-keyword": "A JSON-LD keyword. Not a vocabulary term.",
    "official-iptc-class": (
        "Declared as a class by the pinned IPTC Sport Schema 1.1 ontology, AND the "
        "emitting mapping binds sport: to the official IRI, so it really is that class."
    ),
    "official-iptc-property": (
        "Declared as a property by the pinned IPTC Sport Schema 1.1 ontology, AND the "
        "emitting mapping binds sport: to the official IRI."
    ),
    "official-local-name-wrong-namespace": (
        "The local name IS declared by IPTC Sport Schema 1.1, but the emitting "
        "mapping does not bind sport: to "
        "https://sportschema.org/ontologies/main/ — so the term expands into a "
        "namespace nobody owns and is NOT the official term. This is the defect that "
        "makes a SHACL pass vacuous. Counting these as official would be the most "
        "flattering possible misreading of the baseline."
    ),
    "official-sport-specific-statistic": "Declared by a pinned per-sport or core statistics ontology.",
    "newscode-pinned-valid": (
        "A literal NewsCode that IS a skos:Concept in a pinned concept scheme. "
        "Checked against the vendored TTL, not inferred from the prefix."
    ),
    "newscode-pinned-invalid": (
        "A literal NewsCode whose scheme IS pinned and does NOT contain it. Gate 2."
    ),
    "newscode-unverifiable": (
        "A NewsCode reference that cannot be checked offline: either upstream ships "
        "no TTL for the scheme at the pinned commit, or the mapping names a prefix "
        "without a literal code to check. Membership is NOT claimed. A prefix "
        "pointing at the NewsCodes stem proves nothing about the code."
    ),
    "schema-org-term-unverified": (
        "A schema.org term. NOT VERIFIED: no schema.org vocabulary is pinned in "
        "this repository, so offline validation of schema.org terms is not possible. "
        "Listed rather than asserted valid."
    ),
    "standard-rdf-term": "An RDF, RDFS, XSD or SKOS term.",
    "machina-extension": "A term in the Machina extension namespace. Permitted by the profile.",
    "machina-operational-field": (
        "An unprefixed key. Neither a JSON-LD keyword nor a term defined by any "
        "@context in scope, so JSON-LD expansion drops it silently and the value is "
        "lost. Belongs under machina: or in event_view."
    ),
    "invented-sport-term": (
        "Uses the official sport: prefix but is NOT declared by IPTC Sport Schema "
        "1.1. Gate 1. Must move to machina: or event_view in PR 2."
    ),
    "invented-statistic-term": (
        "Uses an official statistics prefix but is not declared by the "
        "corresponding pinned ontology. Gate 1."
    ),
    "undeclared-prefix-term": (
        "Uses a prefix that no @context in the emitting mapping binds, so it "
        "expands to a relative IRI rather than a term."
    ),
}

CV_PREFIX_STEM = NEWSCODE_STEM
STAT_NAMESPACE_STEM = "https://sportschema.org/ontologies/"

#: A consumer welded to a literal document name — ``worldcup:event`` in a save,
#: load or query position. Rename the document and every one of these reads
#: nothing, silently.
COUPLING_DOCUMENT_NAME = "document-name"

#: A consumer welded to the *storage* shape through a filter, sorter or query
#: path such as ``value.schema:startDate``. A projection that supplies the field
#: only nested under a canonical envelope breaks these while every field-path
#: check in :func:`build_consumers` still passes.
COUPLING_STORAGE_PREDICATE = "storage-predicate"

#: The keys whose value is a document name. This allowlist is the whole reason
#: the document-name matcher does not fire in prose: ``worldcup:event`` appears in
#: docstrings and ``description:`` fields throughout this repository, and only a
#: ``name``/``document_name`` key puts it in a save, load or query position.
_DOCUMENT_NAME_KEY = re.compile(
    r'^\s*(?:-\s*)?"?(?:name|document_name|document-name)"?\s*:\s*(\S.*)$')

#: A ``prefix:localName`` literal inside a document-name value. The lookbehind and
#: lookahead keep it from matching a segment of a longer colon-delimited token, so
#: a URN value yields nothing rather than yielding its first two segments.
_DOCUMENT_NAME_LITERAL = re.compile(
    r'(?<![\w.:-])([a-z][a-z0-9_-]*):([A-Za-z][A-Za-z0-9_-]*)(?![\w:-])')

#: A ``value.…prefix:localName`` storage path, as it appears both as a filter key
#: and inside a ``search-sorters`` list. Anchored on the ``value.`` root the
#: document store actually uses, which keeps it off most prose — but NOT off a
#: ``description:`` scalar, which is prose whose whole job is to name the storage
#: path a downstream workflow reads. See :data:`_DESCRIPTION_KEY`.
_STORAGE_PREDICATE_PATH = re.compile(
    r'(?<![\w.])value(?:\.[A-Za-z0-9_@$-]+)*'
    r'\.[A-Za-z][A-Za-z0-9_-]*:[A-Za-z][A-Za-z0-9_-]+')

#: A ``description:`` key, capturing everything before it so its column is known.
#: The column is what makes the skip safe: a YAML scalar's continuation lines are
#: always indented *past* their key's column, so the scalar ends at the first
#: subsequent line indented at or before it — which is the sibling key, and a
#: sibling key is a real task parameter that must still be scanned.
_DESCRIPTION_KEY = re.compile(r'^(\s*(?:-\s+)?)"?description"?\s*:')


def _description_scalar_lines(lines: list[str]) -> set[int]:
    """1-based line numbers occupied by a ``description:`` key and its scalar.

    Covers every scalar style the repository uses — single-quoted spanning
    several lines, block (``|`` / ``>``) and plain — because none of them need
    telling apart: all three continue on lines indented past the key's column and
    all three end at the first line that is not.
    """
    inside: set[int] = set()
    column: int | None = None
    for number, line in enumerate(lines, start=1):
        if column is not None:
            if not line.strip():
                inside.add(number)
                continue
            if len(line) - len(line.lstrip()) > column:
                inside.add(number)
                continue
            column = None
        match = _DESCRIPTION_KEY.match(line)
        if match:
            column = len(match.group(1))
            inside.add(number)
    return inside


def _coupling_files(root: Path) -> list[Path]:
    found = [
        path
        for pattern in ("*.yml", "*.py")
        for path in root.rglob(pattern)
        if path.is_file() and "__pycache__" not in path.parts
    ]
    return sorted(set(found))


def scan_couplings(root: str) -> list[dict]:
    """Every document-name and storage-predicate coupling under ``root``.

    Returns findings of the form
    ``{file, line, category, literal|path, snippet}`` — ``literal`` for a
    document name, ``path`` for a storage predicate.

    ``root`` is repository-relative or absolute.

    Detection is deliberately **position-aware rather than substring-anywhere**.
    Both ``worldcup:event`` and ``sport:status`` occur constantly in prose,
    docstrings and commented-out tasks here, so a substring scan would report
    dozens of lines nobody has to change — and an inventory whose findings are
    mostly noise is one whose findings get skimmed. A document name therefore
    counts only under a document-name key, a storage predicate only when rooted at
    the ``value.`` path the document store uses, and neither counts on a comment
    line or inside a ``description:`` scalar.

    The description skip is the one exclusion that is not about the *shape* of the
    text. ``value.sport:score`` inside a description is spelled exactly like a
    filter key, and on a multi-line scalar it even sits on an indented
    continuation line — so position alone cannot separate the two. What separates
    them is that a description explains a path rather than evaluating one.
    """
    base = Path(root)
    if not base.is_absolute():
        base = REPO_ROOT / base
    findings: list[dict] = []
    for path in _coupling_files(base):
        try:
            relative = str(path.relative_to(REPO_ROOT))
        except ValueError:
            relative = str(path.relative_to(base))
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        described = _description_scalar_lines(lines)
        for number, line in enumerate(lines, start=1):
            if line.lstrip().startswith("#") or number in described:
                continue
            snippet = line.strip()
            key_match = _DOCUMENT_NAME_KEY.match(line)
            if key_match:
                for prefix, local in _DOCUMENT_NAME_LITERAL.findall(
                        key_match.group(1)):
                    if prefix in URI_SCHEMES:
                        continue
                    findings.append({
                        "file": relative, "line": number,
                        "category": COUPLING_DOCUMENT_NAME,
                        "literal": f"{prefix}:{local}", "snippet": snippet,
                    })
            for predicate in _STORAGE_PREDICATE_PATH.findall(line):
                findings.append({
                    "file": relative, "line": number,
                    "category": COUPLING_STORAGE_PREDICATE,
                    "path": predicate, "snippet": snippet,
                })
    return findings


def _mapping_files() -> list[Path]:
    found: list[Path] = []
    for root in SCAN_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.yml")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if re.search(r'"sport:[A-Za-z]', text) or '"@context"' in text:
                found.append(path)
    return found


def _context_bindings(text: str) -> dict[str, str]:
    """Prefix bindings declared anywhere in a mapping's expression text."""
    return {
        match.group(1): match.group(2)
        for match in re.finditer(
            r'"([A-Za-z][A-Za-z0-9_-]*)"\s*:\s*\\?"(https?://[^"\\]+)\\?"', text)
    }


def classify(term: str, bindings: dict[str, str]) -> str:
    """Classify one emitted term, in the context of the emitting mapping.

    ``bindings`` are the ``@context`` prefix bindings that *this mapping* declares,
    and they are load-bearing rather than decorative. A term is only the official
    IPTC term if the mapping binds ``sport:`` to the official IRI; a mapping that
    binds it elsewhere emits ``sport:Event`` into a namespace nobody owns, and
    calling that an official IPTC class would misreport the single defect this
    inventory exists to surface.
    """
    reference = load_reference()
    if term.startswith("@"):
        return "jsonld-keyword"
    if ":" not in term:
        return "machina-operational-field"
    prefix, local = term.split(":", 1)
    if prefix.lower() in URI_SCHEMES:
        return "machina-operational-field"

    if prefix == "sport":
        official_local = local in reference.main_local_names()
        if bindings.get("sport") != OFFICIAL_MAIN_NS:
            # Either bound to a legacy IRI or not bound at all. Either way the term
            # does not expand to the official IPTC term.
            return ("official-local-name-wrong-namespace" if official_local
                    else "invented-sport-term")
        iri = OFFICIAL_MAIN_NS + local
        if iri in reference.classes:
            return "official-iptc-class"
        if iri in reference.properties:
            return "official-iptc-property"
        return "invented-sport-term"

    if prefix in ("rdf", "rdfs", "xsd", "skos", "owl", "sh", "dcterms", "dct"):
        return "standard-rdf-term"
    if prefix in ("schema", "schemaorg"):
        return "schema-org-term-unverified"
    if prefix == "machina":
        return "machina-extension"

    pinned = reference.prefixes.get(prefix) or bindings.get(prefix)
    if pinned and pinned.startswith(CV_PREFIX_STEM):
        # A prefix pointing at the NewsCodes stem says nothing about whether the
        # code exists. Check the pinned TTL where there is a literal code to check,
        # and say "unverifiable" where there is not.
        if not local:
            return "newscode-unverifiable"
        scheme = reference.scheme_for(pinned + local)
        if scheme is None:
            return "newscode-unverifiable"
        return ("newscode-pinned-valid" if (pinned + local) in scheme.concepts
                else "newscode-pinned-invalid")
    if pinned and pinned.startswith(STAT_NAMESPACE_STEM):
        iri = pinned + local
        if iri in reference.properties or iri in reference.classes:
            return "official-sport-specific-statistic"
        return "invented-statistic-term"
    return "undeclared-prefix-term"


def emitted_terms(mapping_path: Path) -> dict[str, list[str]]:
    """Every quoted prefixed token per mapping — keys AND values.

    ``emitted_keys`` only sees JSON keys, which misses every class name: a class
    arrives as the *value* of ``@type``. Since the brief asks for class names to be
    classified too, this collects both and lets :func:`classify` sort them out.
    """
    import yaml

    document = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
    entries = document.get("mappings") or document.get("mapping") or []
    if isinstance(entries, dict):
        entries = [entries]

    blocks: dict[str, list[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or "<unnamed mapping>"
        terms: list[str] = []
        for expression in (entry.get("outputs") or {}).values():
            text = expression if isinstance(expression, str) else json.dumps(expression)
            for term in _TERM.findall(text):
                if term not in terms:
                    terms.append(term)
        if terms:
            blocks[name] = terms
    return blocks


def build_emitters() -> list[dict]:
    leaks = provider_leak_index()
    emitters = []
    for path in _mapping_files():
        relative = str(path.relative_to(REPO_ROOT))
        text = path.read_text(encoding="utf-8", errors="replace")
        bindings = _context_bindings(text)
        try:
            blocks = emitted_terms(path)
            key_blocks = emitted_keys(path)
        except Exception as exc:  # a malformed YAML is itself worth reporting
            emitters.append({"file": relative, "error": f"{type(exc).__name__}: {exc}"})
            continue
        for mapping_name, all_terms in blocks.items():
            keys = [k for k in key_blocks.get(mapping_name, []) if not k.startswith("<output ")]
            # Union of both scans: emitted_terms catches prefixed tokens including
            # class names in @type VALUES, emitted_keys catches unprefixed KEYS that
            # JSON-LD expansion silently drops. Neither alone is the full picture.
            terms = sorted({t for t in all_terms + keys if not t.startswith("<output ")})
            if not any(term.startswith("sport:") for term in terms):
                continue
            classified: dict[str, list[str]] = {}
            for term in terms:
                classified.setdefault(classify(term, bindings), []).append(term)
            sport_iri = bindings.get("sport")
            emitters.append({
                "file": relative,
                "mapping": mapping_name,
                "declared_prefixes": dict(sorted(bindings.items())),
                "sport_namespace": sport_iri,
                "sport_namespace_is_official": sport_iri == OFFICIAL_MAIN_NS,
                "term_count": len(terms),
                "emitted_property_keys": sorted(keys),
                "terms_by_category": {k: sorted(v) for k, v in sorted(classified.items())},
                "provider_leak_terms": sorted(
                    term for term in terms
                    if term.startswith("sport:") and term.split(":", 1)[1] in leaks
                ),
            })
    return sorted(emitters, key=lambda e: (e["file"], e.get("mapping", "")))


def build_consumers() -> list[dict]:
    emitter_files = {e["file"] for e in build_emitters()}
    consumers = []
    for root in SCAN_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(list(base.rglob("*.yml")) + list(base.rglob("*.py"))):
            relative = str(path.relative_to(REPO_ROOT))
            if relative in emitter_files:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            paths_read = sorted({p for p in CONSUMED_PATHS if p in text})
            payloads = sorted({k for k in PAYLOAD_KEYS if k in text})
            if not paths_read and not payloads:
                continue
            consumers.append({
                "file": relative,
                "reads_field_paths": paths_read,
                "reads_payload_keys": payloads,
                "kind": "test" if "/tests/" in relative or relative.split("/")[-1].startswith("test_")
                        else ("script" if relative.endswith(".py") else "workflow-or-mapping"),
            })
    return consumers


def build_inventory() -> dict:
    reference = load_reference()
    emitters = build_emitters()
    consumers = build_consumers()

    tally: dict[str, dict[str, int]] = {}
    for emitter in emitters:
        for category, terms in emitter.get("terms_by_category", {}).items():
            bucket = tally.setdefault(category, {"distinct_terms": 0, "occurrences": 0})
            bucket["occurrences"] += len(terms)
    distinct: dict[str, set[str]] = {}
    for emitter in emitters:
        for category, terms in emitter.get("terms_by_category", {}).items():
            distinct.setdefault(category, set()).update(terms)
    for category, terms in distinct.items():
        tally[category]["distinct_terms"] = len(terms)

    namespaces: dict[str, list[str]] = {}
    for emitter in emitters:
        namespaces.setdefault(str(emitter.get("sport_namespace")), []).append(
            f"{emitter['file']}::{emitter.get('mapping')}")

    return {
        "inventory_version": "1",
        "inventory_kind": "iptc-emitter-and-consumer-inventory",
        "reproduce": "python3 -m tools.iptc",
        "pin": {
            "upstream_commit": reference.manifest["upstream_commit"],
            "target_version": reference.manifest["declared_version"]["version"],
        },
        "categories": CATEGORIES,
        "scope_boundary": {
            "canonical_model": (
                "The Machina canonical domain model remains authoritative. IPTC Sport "
                "Schema is an output projection generated from it — never the storage "
                "model and never Machina identity."
            ),
            "what_this_pr_does": [
                "Pins and vendors the official IPTC Sport Schema 1.1 artefacts with attribution and per-file hashes.",
                "Adds one shared JSON-LD context copied from the pinned prefixes.",
                "Adds the Machina IPTC profile RFC.",
                "Adds the offline four-layer validation harness, its fixtures and CI.",
                "Records this inventory and the exact baseline failure audit.",
            ],
            "what_this_pr_does_NOT_do": [
                "No serializer is implemented. sport_schema_graph is not produced by any corrected serializer yet.",
                "No canonical identity work. Opaque identifiers and provider-identifier persistence remain unimplemented; the profile only states the policy.",
                "No API or MCP contract change, and no response envelope change.",
                "No event_view production output.",
                "No consumer migration. Every consumer listed below still reads the legacy shape, unchanged.",
                "No mapping YAML, output shape, selector or consumer field path is modified.",
            ],
            "read_this_way": (
                "This PR is foundation-only and output-neutral. It makes conformance "
                "measurable; it does not make anything conformant. Anyone reading the "
                "inventory as a statement that the projection now exists is reading "
                "it wrong."
            ),
        },
        "known_gaps": [
            "schema.org terms are listed but NOT validated: no schema.org vocabulary "
            "is pinned in this repository, so `schema-org-term-unverified` means "
            "exactly that and no more.",
            "Emitted terms are read from the literal quoted keys in each mapping "
            "expression. The expression is never evaluated, because its language "
            "belongs to the Machina workflow engine rather than to Python. A term "
            "produced only by string construction at runtime would not appear here.",
            "The consumer scan matches known IPTC field paths and payload state keys "
            "as substrings. A consumer that reaches an IPTC field through a variable "
            "it built at runtime would be missed. A consumer this inventory misses is "
            "an inventory defect: extend the inventory, do not widen the tolerance.",
            "Provider attribution for gate 4 comes from the reviewed table in "
            "tools/iptc/rules/provider-leak-terms.json, not from inference.",
            "Term classification is per emitting mapping, so the same spelling can "
            "land in different categories in different mappings: `sport:Event` is "
            "`official-iptc-class` only where the mapping binds sport: to "
            "https://sportschema.org/ontologies/main/, and "
            "`official-local-name-wrong-namespace` where it does not.",
            "NewsCode classification checks a literal code against the pinned TTL "
            "where one is present in the mapping text. Where the mapping supplies "
            "only a prefix, or the scheme has no TTL at the pinned commit, the term "
            "is `newscode-unverifiable` and no membership claim is made.",
        ],
        "totals": {
            "emitting_mappings": len(emitters),
            "emitting_files": len({e["file"] for e in emitters}),
            "consumer_files": len(consumers),
            "terms_by_category": dict(sorted(tally.items())),
            "sport_namespaces_in_use": {
                key: len(value) for key, value in sorted(namespaces.items())
            },
        },
        "sport_namespace_usage": {k: sorted(v) for k, v in sorted(namespaces.items())},
        "emitters": emitters,
        "consumers": consumers,
        # Additive. The field-path scan above cannot see a literal document name
        # or a storage-predicate path, and both are consumer dependencies the
        # migration has to carry. Kept as its own list rather than folded into
        # `consumers` because a coupled file is not necessarily a field-path
        # consumer — `_folders.yml` names the document and reads no field at all.
        "couplings": [
            finding for root in SCAN_ROOTS for finding in scan_couplings(root)
        ],
    }


def render_markdown(inventory: dict) -> str:
    lines: list[str] = []
    add = lines.append
    totals = inventory["totals"]

    add("# IPTC emitter, term and consumer inventory")
    add("")
    add("<!-- GENERATED FILE. Do not edit by hand. -->")
    add(f"<!-- Regenerate with: {inventory['reproduce']} -->")
    add("")
    add(
        "Every IPTC-emitting mapping and every consumer of an IPTC output, with each "
        "term classified against the pinned IPTC Sport Schema "
        f"{inventory['pin']['target_version']} at commit "
        f"`{inventory['pin']['upstream_commit']}`."
    )
    add("")
    add(
        "This is generated, not hand-written. The \"zero known legacy consumer "
        "breakages\" claim of the later consumer migration is scoped to this list, so "
        "it has to be re-runnable rather than a snapshot of what someone noticed once."
    )
    add("")

    boundary = inventory["scope_boundary"]
    add("## Scope boundary — read before using this inventory")
    add("")
    add(f"{boundary['canonical_model']}")
    add("")
    add("**This PR does:**")
    add("")
    for item in boundary["what_this_pr_does"]:
        add(f"- {item}")
    add("")
    add("**This PR does NOT do:**")
    add("")
    for item in boundary["what_this_pr_does_NOT_do"]:
        add(f"- {item}")
    add("")
    add(f"> {boundary['read_this_way']}")
    add("")

    add("## Headline")
    add("")
    add(f"- **{totals['emitting_mappings']}** emitting mappings across "
        f"**{totals['emitting_files']}** files.")
    add(f"- **{totals['consumer_files']}** files read an IPTC field path or payload key.")
    add("")
    add("### Two conflicting `sport:` namespaces are in use today")
    add("")
    add("| `sport:` bound to | Emitting mappings | Official? |")
    add("|---|---|---|")
    for namespace, count in totals["sport_namespaces_in_use"].items():
        official = "**yes**" if namespace == "https://sportschema.org/ontologies/main/" else "no"
        shown = f"`{namespace}`" if namespace != "None" else "_not declared in the mapping_"
        add(f"| {shown} | {count} | {official} |")
    add("")
    add(
        "This is the defect that makes a SHACL pass vacuous. A mapping whose "
        "`sport:` prefix is not the official IRI emits no instance of any IPTC "
        "class, so every shape target matches nothing and a validator reports "
        "success over an empty set. See `docs/iptc/BASELINE-AUDIT.md`."
    )
    add("")
    wrong_namespace = totals["terms_by_category"].get(
        "official-local-name-wrong-namespace")
    if wrong_namespace:
        add(
            f"**Read the term table with this in mind.** "
            f"{wrong_namespace['distinct_terms']} distinct term(s) "
            f"({wrong_namespace['occurrences']} occurrence(s)) are classified "
            f"`official-local-name-wrong-namespace`: the local name — `sport:Event` "
            f"and friends — *is* declared by IPTC 1.1, but the emitting mapping does "
            f"not bind `sport:` to the official IRI, so the emitted term is **not** "
            f"the official term. They are deliberately not counted as "
            f"`official-iptc-class` or `official-iptc-property`."
        )
        add("")

    add("## Term classification")
    add("")
    add("| Category | Distinct terms | Occurrences |")
    add("|---|---|---|")
    for category, counts in totals["terms_by_category"].items():
        add(f"| `{category}` | {counts['distinct_terms']} | {counts['occurrences']} |")
    add("")
    for category, description in sorted(inventory["categories"].items()):
        if category in totals["terms_by_category"]:
            add(f"- **`{category}`** — {description}")
    add("")

    add("## Emitters")
    add("")
    for emitter in inventory["emitters"]:
        if "error" in emitter:
            add(f"### `{emitter['file']}`")
            add("")
            add(f"- **could not be read:** {emitter['error']}")
            add("")
            continue
        add(f"### `{emitter['mapping']}`")
        add("")
        add(f"- **file:** `{emitter['file']}`")
        add(f"- **`sport:` bound to:** "
            + (f"`{emitter['sport_namespace']}`" if emitter["sport_namespace"]
               else "_not declared_")
            + ("  ✅ official" if emitter["sport_namespace_is_official"] else "  ❌ not official"))
        add(f"- **distinct emitted terms:** {emitter['term_count']}")
        if emitter["declared_prefixes"]:
            add("- **declared prefixes:** "
                + ", ".join(f"`{k}` → `{v}`" for k, v in emitter["declared_prefixes"].items()))
        for category, terms in emitter["terms_by_category"].items():
            add(f"- **{category}** ({len(terms)}): "
                + ", ".join(f"`{t}`" for t in terms))
        if emitter["provider_leak_terms"]:
            add("- **provider field names in the IPTC namespace:** "
                + ", ".join(f"`{t}`" for t in emitter["provider_leak_terms"]))
        add("")

    add("## Consumers")
    add("")
    add(
        "Each row is a field path the consumer migration must cover. A consumer here "
        "is a legacy dependency: it was written against whichever shape it happened "
        "to see first, so its expectations are a contract this PR is not allowed to "
        "break."
    )
    add("")
    add("| File | Kind | Field paths read | Payload keys read |")
    add("|---|---|---|---|")
    for consumer in inventory["consumers"]:
        paths = ", ".join(f"`{p}`" for p in consumer["reads_field_paths"]) or "—"
        payloads = ", ".join(f"`{p}`" for p in consumer["reads_payload_keys"]) or "—"
        add(f"| `{consumer['file']}` | {consumer['kind']} | {paths} | {payloads} |")
    add("")

    add("## Known gaps in this inventory")
    add("")
    for gap in inventory["known_gaps"]:
        add(f"- {gap}")
    return markdown_document(lines)
