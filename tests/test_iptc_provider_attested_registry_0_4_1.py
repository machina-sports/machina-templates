"""Design 034 owner registry conformance for canonical 0.4.1."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_REGISTRY_PATH = (
    REPO_ROOT / "tools/iptc/canonical/data/source_shape_registry_v2.json"
)
SUPPORT_SPEC = importlib.util.spec_from_file_location(
    "iptc_canonical_support", REPO_ROOT / "tests/iptc_canonical_support.py"
)
SUPPORT = importlib.util.module_from_spec(SUPPORT_SPEC)
SUPPORT_SPEC.loader.exec_module(SUPPORT)
CANONICAL_ROOT = Path(SUPPORT.canonical_package().__file__).resolve().parent
successor = SUPPORT.canonical_module("successor")
REGISTRY_PATH = CANONICAL_ROOT / "data/source_shape_registry_v2.json"
GENERATOR = REPO_ROOT / "tools/iptc/generate_provider_attested_registry.py"
PROVIDER = "sports-skills/espn"

FIXTURES = {
    "arena_nba_event": ["nba-exact-authoritative", "nba-exact-provider-scoped"],
    "arena_nba_longitudinal": ["nba-career-string"],
    "arena_nba_refusal_event": [
        "ambiguous-identity",
        "unpromised-managed-collection",
        "unresolved-identity",
    ],
    "arena_nfl_event": ["nfl-exact-authoritative", "nfl-exact-provider-scoped"],
    "arena_nfl_longitudinal": [
        "nfl-rolling-anchor-number",
        "nfl-season-string",
    ],
    "arena_nfl_refusal_event": ["rights-ineligible", "unsupported-capability"],
    "arena_soccer_event": [
        "soccer-exact-authoritative",
        "soccer-exact-provider-scoped",
        "soccer-reduced-provider-scoped",
    ],
    "arena_soccer_longitudinal": [
        "soccer-date-range-string",
        "soccer-season-number",
    ],
    "arena_soccer_refusal_event": [
        "provider-scoped-graph",
        "reduced-graph",
        "source-representation-mismatch",
    ],
}

SPORTS = {
    "arena_nba_event": "basketball",
    "arena_nba_longitudinal": "basketball",
    "arena_nba_refusal_event": "basketball",
    "arena_nfl_event": "american-football",
    "arena_nfl_longitudinal": "american-football",
    "arena_nfl_refusal_event": "american-football",
    "arena_soccer_event": "soccer",
    "arena_soccer_longitudinal": "soccer",
    "arena_soccer_refusal_event": "soccer",
}

OUTPUT_KINDS = {
    operation: "longitudinal" if operation.endswith("_longitudinal") else "event"
    for operation in FIXTURES
}

EVENT_COLLECTIONS = {
    "/observation/actions": "/coverage/actions",
    "/observation/participants": "/coverage/participants",
    "/observation/participants/{participant_index}/statistics":
        "/coverage/participant_statistics/{participant_index}",
}
LONGITUDINAL_COLLECTIONS = {
    "/aggregates": "/coverage/aggregates",
    "/records": "/coverage/records",
    "/records/{record_index}/statistics":
        "/coverage/record_statistics/{record_index}",
}

STATISTICS = {
    "arena_nba_event": (
        "spbkbstat:minutesPlayed", "json-number-exact-integer/1",
        "not_projected", "closed-shape-not-admitted",
    ),
    "arena_nfl_event": (
        "spamfstat:rushesAttempts", "json-number-exact-integer/1",
        "not_projected", "closed-shape-not-admitted",
    ),
    "arena_soccer_event": (
        "spsocstat:cornerKicks", "json-string-canonical-integer/1",
        "projected", "shape-admitted",
    ),
}

SPATIAL_REPRESENTATIONS = {
    "arena_nba_event": "json-number-exact-spatial-decimal/1",
    "arena_nfl_event": "json-number-exact-spatial-decimal/1",
    "arena_soccer_event": "json-string-canonical-spatial-decimal/1",
    "arena_soccer_refusal_event": "json-string-canonical-spatial-decimal/1",
}

SEQUENCE_REPRESENTATIONS = {
    "arena_nba_longitudinal": {
        "nba-career-string": "json-string-canonical-non-negative-integer/1",
    },
    "arena_nfl_longitudinal": {
        "nfl-rolling-anchor-number": "json-number-exact-non-negative-integer/1",
        "nfl-season-string": "json-string-canonical-non-negative-integer/1",
    },
    "arena_soccer_longitudinal": {
        "soccer-date-range-string": "json-string-canonical-non-negative-integer/1",
        "soccer-season-number": "json-number-exact-non-negative-integer/1",
    },
}


def digest(record):
    data = json.dumps(
        record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def by_operation(records):
    return {record["operation"]: record for record in records}


def argument_schema(fixture_ids):
    return {
        "fields": [{
            "allowed_values": fixture_ids,
            "canonical_lexical_rule": "exact-operation-fixture-enum/1",
            "name": "fixture_id",
            "provider_parameter_name": "fixture_id",
            "required": True,
            "semantic_class": "selector",
            "value_kind": "string",
        }],
        "secret_fields": "forbidden",
        "unknown_fields": "forbidden",
    }


def package_for_operation(operation, *, registry_bytes=None, fixture_ids=None,
                          schema_fixture_ids=None):
    value = registry()
    shapes = by_operation(value["shapes"])
    operations = by_operation(value["operation_contracts"])
    outputs = by_operation(value["output_collection_contracts"])
    shape = shapes[operation]
    contract = operations[operation]
    output = outputs[operation]
    approved = list(FIXTURES[operation] if fixture_ids is None else fixture_ids)
    schema = argument_schema(approved)
    manifest_ids = list(approved)
    if schema_fixture_ids is not None:
        artifact_schema = shape["artifact_schema"]
        if artifact_schema["kind"] == "fixture-discriminated":
            raise AssertionError("ordinary-root substitution helper only")
        artifact_schema["members"]["fixture_id"]["allowed_values"] = \
            list(schema_fixture_ids)
        source_ref = contract["source_shape_ref"]
        source_ref["source_shape_digest"] = digest(shape)
        output["source_shape_ref"] = source_ref
        contract["output_collection_contract_ref"][
            "output_collection_contract_digest"] = digest(output)
        registry_bytes = successor.canonical_json_bytes(value)
    fixture_manifest = {"fixture_ids": manifest_ids}
    return {
        "owner_package": {
            "name": "machina-sports-canonical", "version": "0.4.1"},
        "registry_bytes": REGISTRY_PATH.read_bytes() if registry_bytes is None
            else registry_bytes,
        "package_link": {
            "provider_namespace": PROVIDER,
            "operation": operation,
            "output_kind": OUTPUT_KINDS[operation],
            "source_shape_ref": contract["source_shape_ref"],
            "source_shape_digest": digest(shape),
            "operation_contract_digest": digest(contract),
            "output_collection_contract_digest": digest(output),
            "operation_argument_schema_digest": digest(schema),
            "fixture_manifest_digest": digest(fixture_manifest),
        },
        "fixture_manifest": fixture_manifest,
        "closure_values": {
            "argument_schema": schema,
            "descriptor": {
                "schema_version": "machina-adapter-descriptor/1",
                "provider_namespace": PROVIDER,
                "operation": operation,
                "capabilities": [],
                "module_entrypoint": "synthetic-fixture",
            },
            "package_release": {
                "name": "machina-sports-canonical",
                "version": "0.4.1",
                "package_artifact_digest": "sha256:" + "2" * 64,
                "release_id": "machina-sports-canonical-v0.4.1",
                "release_digest": "sha256:" + "3" * 64,
            },
            "rights_profile": {
                "profile_id": "synthetic", "profile_version": "1",
                "provider_namespace": PROVIDER, "operation": operation,
                "data_class": "synthetic-provider-data-free-replay",
                "prototype_only": True, "commercial_use": False,
                "allowed_consumer_tiers": ["prototype"],
                "rights_profile_digest": "sha256:" + "1" * 64,
            },
        },
    }


def request_for_operation(operation):
    return {
        "requested_provider": PROVIDER,
        "requested_operation": operation,
        "output_kind": OUTPUT_KINDS[operation],
        "output_mode": "operational_only",
        "consumer_tier": "prototype",
        "requires": [],
        "optional": [],
    }


def longitudinal_fixture(operation, fixture_id, sequence):
    sport = SPORTS[operation]
    statistic_value = "1" if sport == "soccer" else 1
    coverage_tuple = {
        "cursor": "", "page_cap": 1, "request_limit": 1,
        "total": 1, "truncated": False,
    }
    return {
        "aggregates": [{"field_id": "stat", "value": statistic_value}],
        "contains_provider_data": False,
        "coverage": {
            "aggregates": coverage_tuple,
            "record_statistics": [coverage_tuple],
            "records": coverage_tuple,
        },
        "fixture_id": fixture_id,
        "identity": [],
        "records": [{
            "period": {
                "scheme": "period", "sequence": sequence, "value": "period-1"},
            "semantics": "period_delta",
            "statistics": [{"field_id": "stat", "value": statistic_value}],
        }],
        "scope": {"kind": "season"},
        "sport": sport,
        "subject": {"entity_type": "team", "provider_id": "synthetic-team"},
        "synthetic": True,
    }


def event_fixture(operation, fixture_id):
    sport = SPORTS[operation]
    number_source = sport != "soccer"
    scalar = 1 if number_source else "1"
    coverage_tuple = {
        "cursor": "", "page_cap": 1, "request_limit": 1,
        "total": 1, "truncated": False,
    }
    return {
        "contains_provider_data": False,
        "coverage": {
            "actions": coverage_tuple,
            "participant_statistics": [coverage_tuple],
            "participants": coverage_tuple,
        },
        "event": {
            "actions": [{
                "id": "action-1",
                "spatial": {"distance": scalar, "x": scalar, "y": scalar,
                            "zone": "synthetic-zone"},
                "team_id": "team-1",
            }],
            "competition_id": "competition-1",
            "id": "event-1",
            "participants": [{
                "id": "team-1", "kind": "team",
                "statistics": [{"field_id": "stat", "value": scalar}],
            }],
            "periods": [{
                "event_provider_id": "event-1",
                "event_provider_namespace": PROVIDER,
                "event_resolution_method": "provider_native",
                "scheme": "period", "sequence": scalar, "value": "period-1",
            }],
            "start": {"state": "exact", "value": "2026-08-17T12:00:00Z"},
            "status": "complete",
        },
        "fixture_id": fixture_id,
        "identity": [],
        "sport": sport,
        "synthetic": True,
    }


class TestProviderAttestedOwnerRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = registry()
        self.shapes = by_operation(self.registry["shapes"])
        self.operations = by_operation(self.registry["operation_contracts"])
        self.outputs = by_operation(self.registry["output_collection_contracts"])

    def test_exact_nine_closed_owner_triplets(self):
        self.assertEqual(set(self.shapes), set(FIXTURES))
        self.assertEqual(set(self.operations), set(FIXTURES))
        self.assertEqual(set(self.outputs), set(FIXTURES))
        self.assertEqual(
            (len(self.shapes), len(self.operations), len(self.outputs)), (9, 9, 9)
        )

        for operation in sorted(FIXTURES):
            with self.subTest(operation=operation):
                shape = self.shapes[operation]
                contract = self.operations[operation]
                output = self.outputs[operation]
                self.assertEqual(shape["provider_namespace"], PROVIDER)
                self.assertEqual(contract["provider_namespace"], PROVIDER)
                self.assertEqual(output["provider_namespace"], PROVIDER)
                self.assertEqual(shape["output_kind"], OUTPUT_KINDS[operation])
                self.assertEqual(contract["output_kind"], OUTPUT_KINDS[operation])
                self.assertEqual(output["output_kind"], OUTPUT_KINDS[operation])
                self.assertNotIn("promised_collections", contract)

                source_ref = contract["source_shape_ref"]
                self.assertEqual(source_ref["source_shape_digest"], digest(shape))
                self.assertEqual(output["source_shape_ref"], source_ref)
                output_ref = contract["output_collection_contract_ref"]
                self.assertEqual(
                    output_ref["output_collection_contract_digest"], digest(output)
                )

    def test_packaged_registry_bytes_are_newline_free_canonical_and_loadable(self):
        raw = REGISTRY_PATH.read_bytes()
        self.assertEqual(raw, successor.canonical_json_bytes(json.loads(raw)))
        for operation in sorted(FIXTURES):
            with self.subTest(operation=operation):
                trust = successor._load_0_4_closure(
                    package_ref=package_for_operation(operation),
                    request=request_for_operation(operation),
                )
                self.assertEqual(trust.descriptor["operation"], operation)
                self.assertEqual(trust.package_release["version"], "0.4.1")

    def test_all_source_shapes_own_closed_executable_binding_inventories(self):
        expected_members = {
            "artifact_schema", "media_type", "operation", "output_kind",
            "provider_namespace", "safe_absence_probe_templates",
            "schema_version", "semantic_binding_templates", "source_shape_id",
            "source_shape_ref", "source_shape_version",
            "statistic_source_binding_templates",
        }
        for operation, shape in self.shapes.items():
            with self.subTest(operation=operation):
                self.assertEqual(set(shape), expected_members)
                self.assertEqual(shape["source_shape_ref"], {
                    "source_shape_id": shape["source_shape_id"],
                    "source_shape_version": shape["source_shape_version"],
                })
                self.assertIsInstance(shape["statistic_source_binding_templates"], list)
                self.assertIsInstance(shape["semantic_binding_templates"], list)
                self.assertIsInstance(shape["safe_absence_probe_templates"], list)

    def test_fixture_manifest_argument_and_owner_enums_agree_for_all_nine(self):
        for operation, fixture_ids in FIXTURES.items():
            with self.subTest(operation=operation):
                trust = successor._load_0_4_closure(
                    package_ref=package_for_operation(operation),
                    request=request_for_operation(operation),
                )
                allowed = trust.argument_schema["fields"][0]["allowed_values"]
                self.assertEqual(list(allowed), fixture_ids)

    def test_ordinary_owner_schema_substitution_refuses_before_adapter_import(self):
        imported = []
        package = package_for_operation(
            "arena_nba_event", schema_fixture_ids=["substituted-fixture"])

        class Loader:
            def load_static(self, package_ref, operation_request):
                return successor._load_0_4_closure(
                    package_ref=package, request=operation_request)

            def import_adapter(self, trust):
                imported.append(True)
                raise AssertionError("adapter import must remain at zero")

        with self.assertRaisesRegex(
                successor.CanonicalContractError,
                "^fixture-manifest-disagreement$"):
            successor.execute_adapter_operation(
                package_ref={},
                request_bytes=successor.canonical_json_bytes(
                    request_for_operation("arena_nba_event")),
                operation_arguments_bytes=b'{"fixture_id":"nba-exact-authoritative"}',
                trusted_loader=Loader(),
            )
        self.assertEqual(imported, [])

    def test_discriminated_fixture_manifest_substitution_refuses_before_adapter_import(self):
        imported = []
        operation = "arena_soccer_longitudinal"
        package = package_for_operation(operation, fixture_ids=[
            "soccer-date-range-string", "soccer-substituted"])

        class Loader:
            def load_static(self, package_ref, operation_request):
                return successor._load_0_4_closure(
                    package_ref=package, request=operation_request)

            def import_adapter(self, trust):
                imported.append(True)
                raise AssertionError("adapter import must remain at zero")

        with self.assertRaisesRegex(
                successor.CanonicalContractError,
                "^fixture-manifest-disagreement$"):
            successor.execute_adapter_operation(
                package_ref={},
                request_bytes=successor.canonical_json_bytes(
                    request_for_operation(operation)),
                operation_arguments_bytes=
                    b'{"fixture_id":"soccer-date-range-string"}',
                trusted_loader=Loader(),
            )
        self.assertEqual(imported, [])

    def test_representative_event_artifacts_reach_runtime_statistic_spatial_and_coverage_bindings(self):
        for operation in ("arena_soccer_event", "arena_nfl_event", "arena_nba_event"):
            fixture_id = FIXTURES[operation][0]
            trust = successor._load_0_4_closure(
                package_ref=package_for_operation(operation),
                request=request_for_operation(operation),
            )
            source = event_fixture(operation, fixture_id)
            raw = json.dumps(source, sort_keys=True, separators=(",", ":")).encode()
            artifact = successor._load_source_artifact(raw, trust)
            statistic_template = trust.source_shape[
                "statistic_source_binding_templates"][0]
            parsed = successor._reparse_source_artifact(artifact, trust)
            source_value = successor.resolve_json_pointer(
                parsed,
                statistic_template["source_value_pointer_template"]
                .replace("{participant_index}", "0")
                .replace("{statistic_index}", "0"),
            )
            lexical = successor._parse_statistic_source(
                source_value, statistic_template["source_representation"],
                statistic_template["value_kind"])
            self.assertEqual(lexical, "1")

            spatial = next(
                item for item in trust.source_shape["semantic_binding_templates"]
                if item["semantic_kind"] == "source_position_coordinates")
            x_pointer = spatial["x_pointer_template"].replace("{action_index}", "0")
            self.assertEqual(
                successor._parse_spatial_source(
                    successor.resolve_json_pointer(parsed, x_pointer),
                    spatial["x_source_representation"]),
                "1" if SPORTS[operation] == "soccer" else "1.0",
            )
            promise = trust.output_collection_contract["promised_collections"][0]
            for field in promise["source_fields"].values():
                pointer = field["value_pointer_templates"][0]
                self.assertIsNotNone(successor.resolve_json_pointer(parsed, pointer))

    def test_all_longitudinal_artifacts_reach_period_and_anchor_bindings(self):
        cases = (
            ("arena_soccer_longitudinal", "soccer-date-range-string", "1"),
            ("arena_soccer_longitudinal", "soccer-season-number", 1),
            ("arena_nfl_longitudinal", "nfl-rolling-anchor-number", 1),
            ("arena_nfl_longitudinal", "nfl-season-string", "1"),
            ("arena_nba_longitudinal", "nba-career-string", "1"),
        )
        for operation, fixture_id, sequence in cases:
            trust = successor._load_0_4_closure(
                package_ref=package_for_operation(operation),
                request=request_for_operation(operation),
            )
            source = longitudinal_fixture(operation, fixture_id, sequence)
            if fixture_id == "nfl-rolling-anchor-number":
                source["scope"]["anchor"] = {
                    "provider_id": "event-1", "provider_namespace": PROVIDER,
                    "resolution_method": "provider_native",
                    "source_record_id": "event-1",
                }
            raw = json.dumps(source, sort_keys=True, separators=(",", ":")).encode()
            artifact = successor._load_source_artifact(raw, trust)
            period = next(
                item for item in trust.source_shape["semantic_binding_templates"]
                if item["semantic_kind"] == "longitudinal_period" and
                fixture_id in item["fixture_ids"])
            handle = successor._load_source_value_handle(
                artifact, period, {"record_index": 0}, trust)
            built = successor._build_period_descriptor(
                handle, record_ref="/records/0", loaded_trust=trust)
            self.assertEqual(built["period"]["sequence"], 1)
            if fixture_id == "nfl-rolling-anchor-number":
                anchor = next(
                    item for item in trust.source_shape["semantic_binding_templates"]
                    if item["semantic_kind"] == "rolling_event_anchor")
                anchor_handle = successor._load_source_value_handle(
                    artifact, anchor, {}, trust)
                built_anchor = successor._build_rolling_event_anchor(
                    anchor_handle, anchor_ref="/scope/anchor", loaded_trust=trust)
                self.assertEqual(built_anchor["provider"]["id"], "event-1")

    def test_refusal_shapes_expose_only_assigned_runtime_binding_paths(self):
        expected = {
            "arena_soccer_refusal_event": {
                "statistics": 0, "semantics": {"source_position_coordinates"}},
            "arena_nfl_refusal_event": {"statistics": 0, "semantics": set()},
            "arena_nba_refusal_event": {"statistics": 0, "semantics": set()},
        }
        for operation, limits in expected.items():
            shape = self.shapes[operation]
            semantic_kinds = {
                item["semantic_kind"] for item in shape["semantic_binding_templates"]}
            with self.subTest(operation=operation):
                self.assertEqual(
                    len(shape["statistic_source_binding_templates"]),
                    limits["statistics"])
                self.assertEqual(semantic_kinds, limits["semantics"])

    def test_binding_records_are_closed_digest_bound_and_coherent_pre_import(self):
        package = package_for_operation("arena_soccer_event")
        value = json.loads(package["registry_bytes"])
        shape = by_operation(value["shapes"])["arena_soccer_event"]
        shape["semantic_binding_templates"][0]["extension"] = True
        contract = by_operation(value["operation_contracts"])["arena_soccer_event"]
        output = by_operation(value["output_collection_contracts"])["arena_soccer_event"]
        contract["source_shape_ref"]["source_shape_digest"] = digest(shape)
        output["source_shape_ref"] = contract["source_shape_ref"]
        contract["output_collection_contract_ref"][
            "output_collection_contract_digest"] = digest(output)
        package["registry_bytes"] = successor.canonical_json_bytes(value)
        package["package_link"]["source_shape_ref"] = contract["source_shape_ref"]
        package["package_link"]["source_shape_digest"] = digest(shape)
        package["package_link"]["operation_contract_digest"] = digest(contract)
        package["package_link"]["output_collection_contract_digest"] = digest(output)
        imported = []

        class Loader:
            def load_static(self, package_ref, operation_request):
                return successor._load_0_4_closure(
                    package_ref=package, request=operation_request)

            def import_adapter(self, trust):
                imported.append(True)

        with self.assertRaisesRegex(
                successor.CanonicalContractError,
                "^invalid-source-shape-record$"):
            successor.execute_adapter_operation(
                package_ref={},
                request_bytes=successor.canonical_json_bytes(
                    request_for_operation("arena_soccer_event")),
                operation_arguments_bytes=b'{"fixture_id":"soccer-exact-authoritative"}',
                trusted_loader=Loader(),
            )
        self.assertEqual(imported, [])

    def test_fixture_enums_literals_and_root_field_families_are_exact(self):
        for operation, fixture_ids in FIXTURES.items():
            with self.subTest(operation=operation):
                schema = self.shapes[operation]["artifact_schema"]
                branches = schema["branches"] if schema["kind"] == \
                    "fixture-discriminated" else [{
                        "fixture_id": None, "shape": schema}]
                actual_fixture_ids = []
                for branch in branches:
                    branch_schema = branch["shape"]
                    members = branch_schema["members"]
                    branch_fixture_ids = members["fixture_id"]["allowed_values"]
                    actual_fixture_ids.extend(branch_fixture_ids)
                    if branch["fixture_id"] is not None:
                        self.assertEqual(branch_fixture_ids, [branch["fixture_id"]])
                    self.assertEqual(members["synthetic"]["allowed_values"], [True])
                    self.assertEqual(
                        members["contains_provider_data"]["allowed_values"], [False]
                    )
                    self.assertEqual(
                        members["sport"]["allowed_values"], [SPORTS[operation]])
                    self.assertEqual(branch_schema["unknown_members"], "forbidden")
                    self.assertEqual(
                        branch_schema["required"], sorted(branch_schema["required"]))
                    if operation == "arena_nfl_refusal_event":
                        self.assertEqual(
                            set(members),
                            {"contains_provider_data", "fixture_id", "sport", "synthetic"},
                        )
                    else:
                        family = "scope" if OUTPUT_KINDS[
                            operation] == "longitudinal" else "event"
                        self.assertIn(family, members)
                        self.assertIn("coverage", members)
                        self.assertIn("identity", members)
                self.assertEqual(actual_fixture_ids, fixture_ids)

    def test_d7_pointer_templates_and_d8_representations_are_exact(self):
        for operation, expected in STATISTICS.items():
            evidence = self.operations[operation]["promised_non_collection_evidence"]
            statistic = next(item for item in evidence if item["evidence_class"] ==
                             "validated_statistic_source_and_disposition")
            self.assertEqual(
                statistic["canonical_occurrence_pattern"],
                "/observation/participants/{participant_index}/statistics/{statistic_index}",
            )
            self.assertEqual(
                statistic["source_value_pointer_template"],
                "/event/participants/{participant_index}/statistics/{statistic_index}/value",
            )
            self.assertEqual(
                (statistic["statistic_name"], statistic["source_representation"],
                 statistic["projection"], statistic["projection_reason"]), expected
            )

        for operation, representation in SPATIAL_REPRESENTATIONS.items():
            evidence = self.operations[operation]["promised_non_collection_evidence"]
            spatial = next(item for item in evidence if item["evidence_class"] ==
                           "validated_spatial_evidence_and_disposition")
            self.assertEqual(spatial["canonical_occurrence_pattern"],
                             "/observation/actions/{action_index}")
            self.assertEqual(spatial["x_pointer_template"],
                             "/event/actions/{action_index}/spatial/x")
            self.assertEqual(spatial["y_pointer_template"],
                             "/event/actions/{action_index}/spatial/y")
            self.assertEqual(spatial["source_representation"], representation)

        for operation, expected in SEQUENCE_REPRESENTATIONS.items():
            evidence = self.operations[operation]["promised_non_collection_evidence"]
            periods = next(item for item in evidence if item["evidence_class"] ==
                           "longitudinal_period_source")
            self.assertEqual(periods["canonical_occurrence_pattern"],
                             "/records/{record_index}")
            self.assertEqual(periods["sequence_pointer_template"],
                             "/records/{record_index}/period/sequence")
            self.assertEqual(periods["fixture_sequence_representations"], expected)

    def test_mixed_longitudinal_shapes_are_fixture_discriminated_only(self):
        for operation in ("arena_soccer_longitudinal", "arena_nfl_longitudinal"):
            with self.subTest(operation=operation):
                schema = self.shapes[operation]["artifact_schema"]
                self.assertEqual(schema["kind"], "fixture-discriminated")
                self.assertEqual(
                    [branch["fixture_id"] for branch in schema["branches"]],
                    FIXTURES[operation],
                )
        for operation in set(FIXTURES) - {
                "arena_soccer_longitudinal", "arena_nfl_longitudinal"}:
            with self.subTest(operation=operation):
                self.assertEqual(
                    self.shapes[operation]["artifact_schema"]["kind"], "object")

    def test_all_approved_longitudinal_sequence_representations_validate_exactly(self):
        cases = (
            ("arena_soccer_longitudinal", "soccer-season-number", 1,
             successor._JsonNumber),
            ("arena_nfl_longitudinal", "nfl-rolling-anchor-number", 1,
             successor._JsonNumber),
            ("arena_soccer_longitudinal", "soccer-date-range-string", "1", str),
            ("arena_nfl_longitudinal", "nfl-season-string", "1", str),
            ("arena_nba_longitudinal", "nba-career-string", "1", str),
        )
        for operation, fixture_id, sequence, expected_type in cases:
            schema = self.shapes[operation]["artifact_schema"]
            raw = json.dumps(
                longitudinal_fixture(operation, fixture_id, sequence),
                sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
            parsed = successor._strict_json_object(raw, preserve_numbers=True)
            with self.subTest(operation=operation, fixture_id=fixture_id):
                self.assertIsNone(
                    successor._validate_source_artifact_shape(parsed, schema))
                self.assertIsInstance(
                    parsed["records"][0]["period"]["sequence"], expected_type)

    def test_cross_representation_discriminator_mismatch_and_unknown_fixture_refuse(self):
        cases = (
            ("arena_soccer_longitudinal", "soccer-season-number", "1"),
            ("arena_soccer_longitudinal", "soccer-date-range-string", 1),
            ("arena_nfl_longitudinal", "nfl-rolling-anchor-number", "1"),
            ("arena_nfl_longitudinal", "nfl-season-string", 1),
            ("arena_nfl_longitudinal", "unknown-fixture", 1),
        )
        for operation, fixture_id, sequence in cases:
            schema = self.shapes[operation]["artifact_schema"]
            raw = json.dumps(
                longitudinal_fixture(operation, fixture_id, sequence),
                sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
            parsed = successor._strict_json_object(raw, preserve_numbers=True)
            with self.subTest(operation=operation, fixture_id=fixture_id,
                              sequence=sequence), self.assertRaisesRegex(
                    successor.CanonicalContractError,
                    "^source-artifact-shape-mismatch$"):
                successor._validate_source_artifact_shape(parsed, schema)

    def test_refusal_non_collection_evidence_sets_are_target_exact(self):
        expected = {
            "arena_soccer_refusal_event": {
                "complete_identity_census",
                "validated_spatial_evidence_and_disposition",
            },
            "arena_nba_refusal_event": {"complete_identity_census"},
        }
        for operation, evidence_classes in expected.items():
            actual = {
                item["evidence_class"]
                for item in self.operations[operation][
                    "promised_non_collection_evidence"]
            }
            with self.subTest(operation=operation):
                self.assertEqual(actual, evidence_classes)

    def test_d9_collection_boundaries_use_one_exact_source_tuple(self):
        expected_by_operation = {
            "arena_soccer_event": EVENT_COLLECTIONS,
            "arena_nfl_event": EVENT_COLLECTIONS,
            "arena_nba_event": EVENT_COLLECTIONS,
            "arena_soccer_longitudinal": LONGITUDINAL_COLLECTIONS,
            "arena_nfl_longitudinal": LONGITUDINAL_COLLECTIONS,
            "arena_nba_longitudinal": LONGITUDINAL_COLLECTIONS,
            "arena_soccer_refusal_event": {
                key: value for key, value in EVENT_COLLECTIONS.items()
                if key != "/observation/participants/{participant_index}/statistics"
            },
            "arena_nfl_refusal_event": {},
            "arena_nba_refusal_event": {
                "/observation/participants": "/coverage/participants",
            },
        }
        for operation, expected in expected_by_operation.items():
            promises = self.outputs[operation]["promised_collections"]
            self.assertEqual(
                {item["pointer_pattern"]: item["source_base_pointer_template"]
                 for item in promises}, expected
            )
            for promise in promises:
                base = promise["source_base_pointer_template"]
                fields = promise["source_fields"]
                self.assertEqual(set(fields), {
                    "cursor", "page_cap", "request_limit", "total", "truncation"
                })
                expected_members = {
                    "cursor": "cursor", "page_cap": "page_cap",
                    "request_limit": "request_limit", "total": "total",
                    "truncation": "truncated",
                }
                for name, member in expected_members.items():
                    self.assertEqual(fields[name], {
                        "state": "value",
                        "value_pointer_templates": [base + "/" + member],
                    })

    def test_non_evidenced_semantics_are_explicitly_synthetic_only(self):
        for operation, contract in self.operations.items():
            evidence = contract["promised_non_collection_evidence"]
            descriptions = " ".join(item["description"] for item in evidence)
            if operation != "arena_nfl_refusal_event":
                self.assertIn("synthetic-replay-only", descriptions)
            self.assertNotIn("raw ESPN fidelity", descriptions)
            self.assertNotIn("raw ESPN", descriptions)

    def test_checked_in_registry_is_a_deterministic_generator_fixed_point(self):
        before = REGISTRY_PATH.read_bytes()
        subprocess.run(
            [sys.executable, str(GENERATOR)],
            cwd=str(REPO_ROOT), check=True, timeout=120,
        )
        self.assertEqual(SOURCE_REGISTRY_PATH.read_bytes(), before)
        self.assertEqual(REGISTRY_PATH.read_bytes(), before)

    def test_trusted_loader_manifest_truthfully_owns_0_4_1(self):
        manifest = json.loads((
            CANONICAL_ROOT / "data/trusted_loader_manifest_v1.json"
        ).read_bytes())
        self.assertEqual(manifest["owner_package"]["version"], "0.4.1")


if __name__ == "__main__":
    unittest.main()
