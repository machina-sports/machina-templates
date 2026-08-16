"""Generate Phase 1 statistic admissibility from pinned IPTC bytes.

Run from the repository root:

    python3 tools/iptc/generate_phase1_manifests.py
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PIN = ROOT / "agent-templates/iptc-mappings/references/iptc-sport-schema-1.1"
SHACL = PIN / "shacl/iptc-sport-shacl.ttl"
ONTOLOGIES = PIN / "ontologies"
OUTPUT = ROOT / "tools/iptc/canonical/data/official_statistic_admissibility_v1.json"

PROPERTY = re.compile(r"(?m)^\s*([A-Za-z][A-Za-z0-9]*:[A-Za-z][A-Za-z0-9]*)\s+rdf:type\s+owl:DatatypeProperty\s*;")
RANGE = re.compile(r"rdfs:range\s+([^\s;]+)")
SHACL_PROPERTY = re.compile(
    r"sh:property\s*\[\s*sh:path\s+([^\s;]+)\s*;(?P<body>.*?)\]\s*;?",
    re.DOTALL,
)
SHACL_DATATYPE = re.compile(r"sh:datatype\s+([^\s;]+)")


def ontology_properties():
    properties = {}
    for path in sorted(ONTOLOGIES.glob("*.ttl")):
        if path.name == "iptc-sport-merged-ontology.ttl":
            continue
        text = path.read_text(encoding="utf-8")
        matches = list(PROPERTY.finditer(text))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            block = text[match.start():end]
            range_match = RANGE.search(block)
            properties[match.group(1)] = range_match.group(1) if range_match else None
    return properties


def shape_properties(text, shape_name, next_shape_name=None):
    start = text.index("sport:{0}Shape".format(shape_name))
    end = text.index("sport:{0}Shape".format(next_shape_name), start) \
        if next_shape_name else len(text)
    result = {}
    for match in SHACL_PROPERTY.finditer(text[start:end]):
        datatype = SHACL_DATATYPE.search(match.group("body"))
        if datatype:
            result[match.group(1)] = datatype.group(1)
    return result


def source_receipt(paths):
    return {
        path.relative_to(ROOT).as_posix(): "sha256:" + hashlib.sha256(
            path.read_bytes()).hexdigest()
        for path in paths
    }


def generate():
    shacl_text = SHACL.read_text(encoding="utf-8")
    shapes = {
        "individual": shape_properties(
            shacl_text, "IndividualParticipation", "Membership"),
        "team": shape_properties(
            shacl_text, "TeamParticipation", "GolfCourse"),
    }
    properties = ontology_properties()
    entries = []
    for curie in sorted(properties):
        for kind in ("individual", "team"):
            datatype = shapes[kind].get(curie)
            admitted = datatype is not None
            entry = {
                "curie": curie,
                "participation_kind": kind,
                "shape_id": "pinned-{0}-participation-shape".format(kind),
                "ontology_range": properties[curie],
                "admitted": admitted,
                "canonical_value_kinds": [
                    "integer", "decimal", "boolean", "duration", "text"
                ],
            }
            if admitted:
                entry["shacl_datatype"] = datatype
                entry["lexicalization"] = {
                    "id": "canonical-lexical-to-xsd-string",
                    "version": "1",
                    "target_datatype": datatype,
                    "conflict_disposition": "explicit_conversion",
                }
            entries.append(entry)
    document = {
        "schema_version": "machina-official-statistic-admissibility/1",
        "manifest_id": "iptc-sport-schema-1.1-participation-statistics",
        "manifest_version": "1",
        "source_receipt": source_receipt(
            [SHACL] + sorted(path for path in ONTOLOGIES.glob("*.ttl")
                             if path.name != "iptc-sport-merged-ontology.ttl")),
        "entries": entries,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


if __name__ == "__main__":
    generate()
