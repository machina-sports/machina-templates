"""Generate owner Phase 1 runtime, package, and compatibility receipts."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "tools/iptc/canonical"
DATA = PACKAGE / "data"
RUNTIME_MANIFEST = DATA / "trusted_loader_manifest_v1.json"
VENDORED_MANIFEST = ROOT / "tools/iptc/vendored-manifest.json"
PACKAGE_RECEIPT = PACKAGE / "package-receipt.json"
LEGACY_RECEIPT = DATA / "legacy_0_2_surface.json"
DISTRIBUTION_VERSION = "0.4.1"
RUNTIME_CONTRACT_VERSION = "0.4.0"
SOURCE_COMMIT = "a57ffcff0b6efabbbc62fd5b736c8fee0eb4b671"

PRIVATE_SYMBOLS = (
    "_IdentityResolutionProvider", "_load_source_artifact", "_build_statistic_fact",
    "_build_period_descriptor", "_build_rolling_event_anchor",
    "_validate_identity_occurrence", "_derive_provider_scoped_entity_id",
    "_derive_operational_resource_id", "_derive_operational_id_ledger",
    "_normalize_spatial_evidence", "_derive_spatial_distance", "_derive_spatial_zone",
    "_build_canonical_spatial_evidence", "_build_coverage_evidence",
    "_expand_managed_collection_patterns", "_build_successor_provenance",
    "_build_successor_envelope", "_project_successor_graph",
    "_validate_successor_envelope", "_validate_successor_envelope_bytes",
    "_validate_longitudinal_envelope_bytes", "_statistic_projection_disposition",
    "_load_0_3_compatibility_closure", "_load_0_4_closure",
    "_validate_source_shape_schema", "_validate_source_artifact_shape",
    "execute_adapter_operation",
)


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def file_record(path):
    return {
        "relative_path": path.relative_to(PACKAGE).as_posix(),
        "byte_length": path.stat().st_size,
        "sha256": digest(path),
        "executable_module": path.suffix == ".py",
    }


def source_symbols(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def generate_legacy_receipt():
    document = {
        "schema_version": "machina-legacy-python-surface-receipt/1",
        "distribution_version": "0.2.0",
        "constants": {
            "SCHEMA_VERSION": "canonical-observation/1.1",
            "PROFILE_VERSION": "machina-iptc-profile/1.2",
            "MACHINA_SCHEMA_VERSION": "machina-sports-schema/1",
        },
        "owner_all": [
            "PROFILE_VERSION", "EXACT_OBSERVATION_PROFILE_VERSION", "SCHEMA_VERSION",
            "PREDECESSOR_SCHEMA_VERSION", "ACCEPTED_SCHEMA_VERSIONS",
            "MACHINA_SCHEMA_VERSION", "SERIALIZER_VERSION", "SERIALIZER_NAME",
            "UPSTREAM_REPOSITORY", "UPSTREAM_COMMIT", "UPSTREAM_TARGET_VERSION",
        ],
        "signatures": {
            "observation.validate_observation": "(document)",
            "serialize.sport_schema_graph": "(document, *, id_resolver)",
            "serialize.canonical_envelope": "(document, *, id_resolver)",
        },
    }
    LEGACY_RECEIPT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def generate():
    generate_legacy_receipt()
    modules = sorted(
        path for path in PACKAGE.rglob("*.py")
        if path.name != "export_official_terms.py" and "__pycache__" not in path.parts
    )
    data_files = sorted(
        path for path in PACKAGE.rglob("*.json")
        if path not in (PACKAGE_RECEIPT, RUNTIME_MANIFEST)
    )
    module_records = [file_record(path) for path in modules]
    data_records = [file_record(path) for path in data_files]
    private = []
    for symbol in PRIVATE_SYMBOLS:
        owners = [path for path in modules if symbol in source_symbols(path)]
        if len(owners) != 1:
            raise RuntimeError("private symbol {0} has {1} owners".format(symbol, len(owners)))
        owner = owners[0]
        private.append({"symbol": symbol,
                        "defining_module_path": owner.relative_to(PACKAGE).as_posix(),
                        "source_file_sha256": digest(owner)})
    aggregate = "sha256:" + hashlib.sha256(canonical_bytes(
        [[item["relative_path"], item["sha256"]]
         for item in module_records + data_records])).hexdigest()
    runtime = {
        "schema_version": "machina-canonical-runtime-vendored-manifest/1",
        "owner_package": {"name": "machina-sports-canonical",
                          "version": RUNTIME_CONTRACT_VERSION,
                          "release_digest": aggregate},
        "runtime_files": module_records,
        "required_data_files": data_records,
        "private_symbols": private,
        "aggregate_runtime_digest": aggregate,
    }
    RUNTIME_MANIFEST.write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
    files = dict((item["relative_path"], item["sha256"].split(":", 1)[1])
                 for item in module_records + data_records + [file_record(RUNTIME_MANIFEST)])
    vendored = {
        "consumer": "machina-sports/sports-skills",
        "source_repository": "machina-sports/machina-templates",
        "source_path": "tools/iptc/canonical",
        "source_commit": SOURCE_COMMIT,
        "profile": "machina-iptc-profile/1.3",
        "schema_version": "canonical-observation/1.2",
        "machina_schema_version": "machina-sports-schema/1.1",
        "upstream_pin": {"repository": "https://github.com/iptc/sport-schema",
                         "commit": "0e77bf8678f3702fe81c28673bede35efe47d633",
                         "target_version": "1.1"},
        "files": dict(sorted(files.items())),
    }
    VENDORED_MANIFEST.write_text(json.dumps(vendored, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "distribution_version": DISTRIBUTION_VERSION,
        "source": "machina-templates:tools/iptc/canonical",
        "source_commit": SOURCE_COMMIT,
        "legacy_contract_version": "0.2.0",
        "runtime_manifest": digest(RUNTIME_MANIFEST),
        "core_manifest": dict(sorted(files.items())),
    }
    PACKAGE_RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    generate()
