"""Design 035 owner-runtime prerequisites and frozen 0.3 compatibility."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SUPPORT_SPEC = importlib.util.spec_from_file_location(
    "iptc_canonical_support", REPO_ROOT / "tests/iptc_canonical_support.py"
)
SUPPORT = importlib.util.module_from_spec(SUPPORT_SPEC)
SUPPORT_SPEC.loader.exec_module(SUPPORT)
canonical = SUPPORT.canonical_package()
successor = SUPPORT.canonical_module("successor")


REGISTRY_V1_BYTES = (
    b'{\n  "schema_version": "machina-source-shape-registry/1",\n'
    b'  "registry_id": "machina-phase1-source-shapes",\n'
    b'  "registry_version": "1",\n  "shapes": [],\n'
    b'  "operation_contracts": []\n}\n'
)
RELEASE_0_3_DIGESTS = {
    "machina_sports_canonical-0.3.0-py3-none-any.whl":
        "52c2b5a321a60ca242166e5522307f72ef974a460e8f906775bb3cf0480d22a1",
    "machina_sports_canonical-0.3.0.tar.gz":
        "0cbb26540e346daf86a31cc2ed2b1126da0e28c5836114ccb6cd39212c915024",
}
LEGACY_FIXTURE_DIGESTS = {
    "api-football-soccer-envelope.json":
        "129f0d2f610fca913741882a2889840bc7740ddf5c7f1e9b662d4c27f3cd4956",
    "sports-skills-espn-soccer-envelope.json":
        "cdcbc745a24eea0e3771cfd93c5603702c9700a4070fd222d53ae75856e493cd",
    "sportradar-soccer-envelope.json":
        "3c12039ab633ea4ef1613c520204c3cda354c2e87cac13fcbb6f4cb2e0787bf8",
    "stats-perform-opta-soccer-envelope.json":
        "8eaf41ae31aafb293d3fad3f4bb13375e67e070278c38844473bc39024a1d15e",
}


def digest_bytes(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def record_digest(record):
    return digest_bytes(successor.canonical_json_bytes(record))


def object_schema(members=None, required=None):
    return {
        "kind": "object",
        "members": members or {},
        "required": required or [],
        "unknown_members": "forbidden",
    }


def one_record_package(*, schema=None, allowed_values=None, embedded_promises=False,
                       fixture_ids=None, owner_version="0.4.0",
                       package_release_version=None):
    fixture_ids = fixture_ids or ["approved-fixture"]
    schema = schema or object_schema({"fixture_id": {
        "kind": "string", "allowed_values": fixture_ids
    }}, ["fixture_id"])
    source_shape = {
        "schema_version": "machina-source-shape/1",
        "source_shape_id": "fixture-shape",
        "source_shape_version": "1",
        "provider_namespace": "provider-a",
        "operation": "fixture_operation",
        "output_kind": "event",
        "media_type": "application/json",
        "artifact_schema": schema,
    }
    source_ref = {
        "source_shape_id": "fixture-shape",
        "source_shape_version": "1",
        "source_shape_digest": record_digest(source_shape),
    }
    output_contract = {
        "schema_version": "machina-output-collection-contract/1",
        "output_collection_contract_id": "fixture-output",
        "output_collection_contract_version": "1",
        "provider_namespace": "provider-a",
        "operation": "fixture_operation",
        "output_kind": "event",
        "source_shape_ref": source_ref,
        "promised_collections": [{
            "pointer_pattern": "/observation/participants"
        }],
    }
    output_ref = {
        "output_collection_contract_id": "fixture-output",
        "output_collection_contract_version": "1",
        "output_collection_contract_digest": record_digest(output_contract),
    }
    operation_contract = {
        "schema_version": "machina-operation-contract/1",
        "provider_namespace": "provider-a",
        "operation": "fixture_operation",
        "output_kind": "event",
        "source_shape_ref": source_ref,
        "output_collection_contract_ref": output_ref,
        "promised_non_collection_evidence": [],
    }
    if embedded_promises:
        operation_contract["promised_collections"] = []
    registry = {
        "schema_version": "machina-source-shape-registry/1",
        "registry_id": "machina-phase1-source-shapes",
        "registry_version": "2",
        "shapes": [source_shape],
        "operation_contracts": [operation_contract],
        "output_collection_contracts": [output_contract],
    }
    field = {
        "name": "fixture_id",
        "semantic_class": "selector",
        "value_kind": "string",
        "required": True,
        "canonical_lexical_rule": "exact-operation-fixture-enum/1",
        "provider_parameter_name": "fixture_id",
        "allowed_values": (fixture_ids if allowed_values is None else allowed_values),
    }
    closure_values = {
        "descriptor": {
            "schema_version": "machina-adapter-descriptor/1",
            "provider_namespace": "provider-a",
            "operation": "fixture_operation",
            "capabilities": [],
            "module_entrypoint": "fixture",
        },
        "rights_profile": {
            "profile_id": "fixture", "profile_version": "1",
            "provider_namespace": "provider-a", "operation": "fixture_operation",
            "data_class": "synthetic", "prototype_only": True,
            "commercial_use": False, "allowed_consumer_tiers": ["prototype"],
            "rights_profile_digest": "sha256:" + "1" * 64,
        },
        "argument_schema": {
            "fields": [field], "unknown_fields": "forbidden",
            "secret_fields": "forbidden",
        },
        "package_release": {
            "name": "machina-sports-canonical",
            "version": package_release_version or owner_version,
            "package_artifact_digest": "sha256:" + "2" * 64,
            "release_id": "unreleased", "release_digest": "sha256:" + "3" * 64,
        },
    }
    package_link = {
        "provider_namespace": "provider-a",
        "operation": "fixture_operation",
        "output_kind": "event",
        "source_shape_ref": source_ref,
        "source_shape_digest": source_ref["source_shape_digest"],
        "operation_contract_digest": record_digest(operation_contract),
        "output_collection_contract_digest": output_ref[
            "output_collection_contract_digest"],
        "operation_argument_schema_digest": record_digest(
            closure_values["argument_schema"]),
        "fixture_manifest_digest": record_digest({
            "fixture_ids": fixture_ids}),
    }
    return {
        "owner_package": {
            "name": "machina-sports-canonical", "version": owner_version},
        "registry_bytes": successor.canonical_json_bytes(registry),
        "package_link": package_link,
        "fixture_manifest": {"fixture_ids": fixture_ids},
        "closure_values": closure_values,
    }


def request():
    return {
        "requested_provider": "provider-a",
        "requested_operation": "fixture_operation",
        "output_kind": "event",
        "output_mode": "operational_only",
        "consumer_tier": "prototype",
        "requires": [],
        "optional": [],
    }


class TestFrozenOwner030Compatibility(unittest.TestCase):
    def test_release_artifact_digests_are_frozen(self):
        rows = {}
        checksum_path = REPO_ROOT / "docs/iptc/machina-sports-canonical-0.3.0.sha256"
        for line in checksum_path.read_text(encoding="ascii").splitlines():
            digest, filename = line.split("  ", 1)
            rows[filename] = digest
        self.assertEqual(rows, RELEASE_0_3_DIGESTS)

    def test_registry_v1_bytes_and_empty_counts_are_frozen(self):
        path = REPO_ROOT / "tools/iptc/canonical/data/source_shape_registry_v1.json"
        self.assertEqual(path.read_bytes(), REGISTRY_V1_BYTES)
        self.assertEqual(digest_bytes(REGISTRY_V1_BYTES),
                         "sha256:3b4bc5cf04af3cfa15a9f2544202bdfeb0402a75277e15aa086c0de887319c42")
        value = json.loads(REGISTRY_V1_BYTES)
        self.assertEqual(value["schema_version"], "machina-source-shape-registry/1")
        self.assertEqual(value["registry_id"], "machina-phase1-source-shapes")
        self.assertEqual(value["registry_version"], "1")
        self.assertEqual(value["shapes"], [])
        self.assertEqual(value["operation_contracts"], [])
        self.assertNotIn("output_collection_contracts", value)

    def test_registry_v2_has_the_separately_reviewed_data_only_records(self):
        path = REPO_ROOT / "tools/iptc/canonical/data/source_shape_registry_v2.json"
        value = json.loads(path.read_bytes())
        self.assertEqual(set(value), {
            "schema_version", "registry_id", "registry_version", "shapes",
            "operation_contracts", "output_collection_contracts"})
        self.assertEqual(value["registry_version"], "2")
        operations = {
            "arena_soccer_event", "arena_nfl_event", "arena_nba_event",
            "arena_soccer_longitudinal", "arena_nfl_longitudinal",
            "arena_nba_longitudinal", "arena_soccer_refusal_event",
            "arena_nfl_refusal_event", "arena_nba_refusal_event",
        }
        for key in ("shapes", "operation_contracts",
                    "output_collection_contracts"):
            self.assertEqual(len(value[key]), 9)
            self.assertEqual({item["operation"] for item in value[key]}, operations)

    def test_legacy_fixture_bytes_are_frozen(self):
        root = REPO_ROOT / "tools/iptc/fixtures/corrected"
        actual = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                  for name in LEGACY_FIXTURE_DIGESTS}
        self.assertEqual(actual, LEGACY_FIXTURE_DIGESTS)

    def test_public_exports_and_signatures_remain_frozen(self):
        self.assertEqual(tuple(canonical.__all__), (
            "PROFILE_VERSION", "EXACT_OBSERVATION_PROFILE_VERSION", "SCHEMA_VERSION",
            "PREDECESSOR_SCHEMA_VERSION", "ACCEPTED_SCHEMA_VERSIONS",
            "MACHINA_SCHEMA_VERSION", "SERIALIZER_VERSION", "SERIALIZER_NAME",
            "UPSTREAM_REPOSITORY", "UPSTREAM_COMMIT", "UPSTREAM_TARGET_VERSION",
            "SUCCESSOR_PROFILE_VERSION", "SUCCESSOR_SCHEMA_VERSION",
            "SUCCESSOR_MACHINA_SCHEMA_VERSION", "LONGITUDINAL_SCHEMA_VERSION",
            "LONGITUDINAL_MACHINA_SCHEMA_VERSION",
        ))
        observation = SUPPORT.canonical_module("observation")
        serialize = SUPPORT.canonical_module("serialize")
        self.assertEqual(str(inspect.signature(observation.validate_observation)), "(document)")
        self.assertEqual(str(inspect.signature(serialize.sport_schema_graph)),
                         "(document, *, id_resolver)")
        self.assertEqual(str(inspect.signature(serialize.canonical_envelope)),
                         "(document, *, id_resolver)")


class TestOutputCollectionAuthority(unittest.TestCase):
    def test_closure_has_exactly_one_new_immutable_member(self):
        expected = list(successor.LoadedCanonicalTrustClosureV1.__slots__)
        self.assertEqual(expected.count("output_collection_contract"), 1)
        expected.remove("output_collection_contract")
        self.assertEqual(tuple(expected), (
            "_seal", "descriptor", "rights_profile", "source_shape",
            "operation_contract", "capability_contract", "identity_registry",
            "statistic_units", "statistic_derivations", "statistic_implementations",
            "admissibility", "spatial", "longitudinal", "_artifact_session",
            "document_builder", "argument_schema", "package_release", "closure_id",
            "_requested_consumer_tier", "_required_capabilities",
        ))
        trust = successor._load_0_4_closure(
            package_ref=one_record_package(), request=request())
        with self.assertRaises(TypeError):
            trust.output_collection_contract["promised_collections"] = []

    def test_version_2_rejects_embedded_collection_promises(self):
        with self.assertRaisesRegex(successor.CanonicalContractError,
                                    "invalid-operation-contract"):
            successor._load_0_4_closure(
                package_ref=one_record_package(embedded_promises=True), request=request())

    def test_version_2_has_no_output_contract_fallback(self):
        package = one_record_package()
        registry = json.loads(package["registry_bytes"])
        registry["output_collection_contracts"] = []
        package["registry_bytes"] = successor.canonical_json_bytes(registry)
        with self.assertRaisesRegex(successor.CanonicalContractError,
                                    "output-collection-contract-not-found"):
            successor._load_0_4_closure(package_ref=package, request=request())

    def test_collection_readers_ignore_operation_contract_promises(self):
        package = one_record_package()
        trust = successor._load_0_4_closure(package_ref=package, request=request())
        operation = dict(trust.operation_contract)
        operation["promised_collections"] = []
        object.__setattr__(trust, "operation_contract", operation)
        promise = successor._promise_for_pointer("/observation/participants", trust)
        self.assertEqual(promise["pointer_pattern"], "/observation/participants")

    def test_version_2_registry_is_closed_duplicate_free_and_fully_referenced(self):
        mutations = []
        extra = one_record_package()
        value = json.loads(extra["registry_bytes"])
        value["extension"] = True
        extra["registry_bytes"] = successor.canonical_json_bytes(value)
        mutations.append((extra, "invalid-source-shape-registry"))

        duplicate = one_record_package()
        value = json.loads(duplicate["registry_bytes"])
        value["shapes"].append(value["shapes"][0])
        duplicate["registry_bytes"] = successor.canonical_json_bytes(value)
        mutations.append((duplicate, "duplicate-source-shape-record"))

        unreferenced = one_record_package()
        value = json.loads(unreferenced["registry_bytes"])
        orphan = dict(value["output_collection_contracts"][0])
        orphan["output_collection_contract_id"] = "orphan-output"
        value["output_collection_contracts"].append(orphan)
        unreferenced["registry_bytes"] = successor.canonical_json_bytes(value)
        mutations.append((unreferenced, "unreferenced-owner-record"))

        for package, reason in mutations:
            with self.subTest(reason=reason), self.assertRaisesRegex(
                    successor.CanonicalContractError, "^{0}$".format(reason)):
                successor._load_0_4_closure(package_ref=package, request=request())


class TestExactOwnerPatchReleaseIdentity(unittest.TestCase):
    def test_exact_0_4_0_and_0_4_1_releases_load(self):
        for version in ("0.4.0", "0.4.1"):
            with self.subTest(version=version):
                trust = successor._load_0_4_closure(
                    package_ref=one_record_package(owner_version=version),
                    request=request(),
                )
                self.assertEqual(trust.package_release["version"], version)

    def test_successor_provenance_reports_truthful_0_4_1_release(self):
        trust = successor._load_0_4_closure(
            package_ref=one_record_package(owner_version="0.4.1"),
            request=request(),
        )
        handle = successor.ValidatedDocumentHandleV1(
            successor._HANDLE_SEAL,
            {"schema_version": successor.SUCCESSOR_SCHEMA_VERSION},
            "sha256:" + "4" * 64,
            trust,
        )
        provenance = successor._build_successor_provenance(
            handle, source_artifacts=[], loaded_trust=trust)
        self.assertEqual(provenance["canonical_package"]["version"], "0.4.1")

    def test_no_broad_0_4_semver_or_release_identity_mismatch_is_accepted(self):
        variants = [
            one_record_package(owner_version=version)
            for version in ("0.4", "0.4.2", "0.5.0")
        ]
        variants.append(one_record_package(
            owner_version="0.4.1", package_release_version="0.4.0"))
        for package in variants:
            with self.subTest(
                    owner=package["owner_package"],
                    release=package["closure_values"]["package_release"]), \
                    self.assertRaisesRegex(
                        successor.CanonicalContractError,
                        "^invalid-0.4-owner-package$"):
                successor._load_0_4_closure(
                    package_ref=package, request=request())


class TestExplicit030CompatibilityReader(unittest.TestCase):
    def package(self):
        receipt_path = (REPO_ROOT / "tools/iptc/canonical/data/"
                        "package_receipt_0_3.json")
        return {
            "owner_package": {"name": "machina-sports-canonical", "version": "0.3.0"},
            "package_receipt_bytes": receipt_path.read_bytes(),
            "registry_bytes": REGISTRY_V1_BYTES,
            "closure_values": {
                "operation_contract": {
                    "promised_collections": [{"pointer_pattern": "/records"}],
                    "promised_non_collection_evidence": [],
                }
            },
        }

    def test_exact_reader_projects_without_altering_legacy_bytes(self):
        package = self.package()
        before = bytes(package["registry_bytes"])
        trust = successor._load_0_3_compatibility_closure(
            package_ref=package, request=request())
        self.assertEqual(package["registry_bytes"], before)
        self.assertEqual(trust.output_collection_contract["promised_collections"],
                         ({"pointer_pattern": "/records"},))
        with self.assertRaises(TypeError):
            trust.output_collection_contract["promised_collections"][0]["x"] = True

    def test_reader_requires_exact_release_and_registry_identity(self):
        variants = []
        wrong_version = self.package()
        wrong_version["owner_package"] = dict(wrong_version["owner_package"], version="0.4.0")
        variants.append(wrong_version)
        patch_version = self.package()
        patch_version["owner_package"] = dict(
            patch_version["owner_package"], version="0.4.1")
        variants.append(patch_version)
        wrong_registry = self.package()
        value = json.loads(wrong_registry["registry_bytes"])
        value["registry_version"] = "2"
        wrong_registry["registry_bytes"] = successor.canonical_json_bytes(value)
        variants.append(wrong_registry)
        for package in variants:
            with self.subTest(package=package["owner_package"]), self.assertRaisesRegex(
                    successor.CanonicalContractError, "incompatible-0.3-owner-package"):
                successor._load_0_3_compatibility_closure(
                    package_ref=package, request=request())


class TestClosedSourceShapeGrammar(unittest.TestCase):
    @staticmethod
    def fixture_branch(fixture_id, value_kind="string"):
        return {
            "fixture_id": fixture_id,
            "shape": object_schema({
                "fixture_id": {
                    "kind": "string", "allowed_values": [fixture_id]},
                "sequence": {"kind": value_kind},
            }, ["fixture_id", "sequence"]),
        }

    def fixture_schema(self, *fixture_ids):
        return {
            "kind": "fixture-discriminated",
            "branches": [self.fixture_branch(fixture_id)
                         for fixture_id in fixture_ids],
        }

    def test_complete_recursive_grammar_is_accepted(self):
        schema = object_schema({
            "name": {"kind": "string", "allowed_values": ["a", "b"]},
            "active": {"kind": "boolean", "allowed_values": [False, True]},
            "score": {"kind": "number", "allowed_values": ["1", "1.0", "1e0"]},
            "rows": {"kind": "array", "items": object_schema({
                "value": {"kind": "number"}
            }, ["value"])},
        }, ["active", "name", "rows", "score"])
        self.assertIsNone(successor._validate_source_shape_schema(schema))

    def test_invalid_grammar_has_one_bounded_refusal(self):
        invalid = (
            {"kind": "null"},
            {"kind": "string", "extension": True},
            {"kind": "object", "members": {}, "required": [],
             "unknown_members": "allowed"},
            object_schema({"x": {"kind": "string"}}, ["missing"]),
            object_schema({"x": {"kind": "string"}}, ["x", "x"]),
            {"kind": "string", "allowed_values": []},
            {"kind": "string", "allowed_values": ["b", "a"]},
            {"kind": "boolean", "allowed_values": [True, False]},
            {"kind": "number", "allowed_values": [1]},
            {"kind": "number", "allowed_values": ["01"]},
            {"kind": "array", "items": {"kind": "string"}, "maxItems": 1},
        )
        for schema in invalid:
            with self.subTest(schema=schema), self.assertRaisesRegex(
                    successor.CanonicalContractError, "^invalid-source-shape-schema$"):
                successor._validate_source_shape_schema(schema)

    def test_fixture_discriminator_is_root_only_closed_and_duplicate_free(self):
        schema = self.fixture_schema("fixture-a", "fixture-b")
        self.assertIsNone(successor._validate_source_shape_schema(schema))
        invalid = (
            {"kind": "fixture-discriminated", "branches": [], "extension": True},
            {"kind": "fixture-discriminated", "branches": [
                self.fixture_branch("fixture-a"),
                self.fixture_branch("fixture-a"),
            ]},
            object_schema({"nested": schema}, ["nested"]),
            {"kind": "fixture-discriminated", "branches": [{
                "fixture_id": "fixture-a",
                "shape": object_schema({
                    "fixture_id": {"kind": "string"},
                    "sequence": {"kind": "string"},
                }, ["fixture_id", "sequence"]),
            }]},
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaisesRegex(
                    successor.CanonicalContractError,
                    "^invalid-source-shape-schema$"):
                successor._validate_source_shape_schema(candidate)

    def test_fixture_discriminator_requires_complete_approved_branch_set(self):
        fixture_ids = ["fixture-a", "fixture-b"]
        schemas = {
            "missing": self.fixture_schema("fixture-a"),
            "extra": self.fixture_schema("fixture-a", "fixture-b", "fixture-c"),
            "unknown": self.fixture_schema("fixture-a", "fixture-c"),
        }
        for label, schema in schemas.items():
            package = one_record_package(
                schema=schema, fixture_ids=fixture_ids,
                allowed_values=fixture_ids)
            with self.subTest(label=label), self.assertRaisesRegex(
                    successor.CanonicalContractError,
                    "^fixture-manifest-disagreement$"):
                successor._load_0_4_closure(
                    package_ref=package, request=request())

    def test_static_grammar_failure_precedes_adapter_import(self):
        package = one_record_package(schema={"kind": "string"})
        imported = []

        class Loader:
            def load_static(self, package_ref, operation_request):
                return successor._load_0_4_closure(
                    package_ref=package, request=operation_request)

            def import_adapter(self, trust):
                imported.append(True)

        with self.assertRaisesRegex(successor.CanonicalContractError,
                                    "invalid-source-shape-schema"):
            successor.execute_adapter_operation(
                package_ref={},
                request_bytes=successor.canonical_json_bytes(request()),
                operation_arguments_bytes=b'{"fixture_id":"approved-fixture"}',
                trusted_loader=Loader(),
            )
        self.assertEqual(imported, [])

    def test_execution_rechecks_a_directly_constructed_0_4_closure(self):
        for version in ("0.4.0", "0.4.1"):
            trust = successor._construct_loaded_trust_closure(
                source_shape={"media_type": "application/json",
                              "artifact_schema": {"kind": "string"}},
                package_release={
                    "name": "machina-sports-canonical", "version": version,
                    "package_artifact_digest": "sha256:" + "2" * 64,
                    "release_id": "unreleased",
                    "release_digest": "sha256:" + "3" * 64,
                })
            imported = []

            class Loader:
                def load_static(self, package_ref, operation_request):
                    return trust

                def import_adapter(self, loaded):
                    imported.append(True)

            direct_request = request()
            direct_request["requested_operation"] = "event"
            with self.subTest(version=version), self.assertRaisesRegex(
                    successor.CanonicalContractError,
                    "invalid-source-shape-schema"):
                successor.execute_adapter_operation(
                    package_ref={},
                    request_bytes=successor.canonical_json_bytes(direct_request),
                    operation_arguments_bytes=b'{}', trusted_loader=Loader())
            self.assertEqual(imported, [])


class TestSourceArtifactShapeBoundary(unittest.TestCase):
    def trust(self, schema):
        return successor._load_0_4_closure(
            package_ref=one_record_package(schema=schema), request=request())

    def test_recursive_shape_and_exact_scalar_representations(self):
        schema = object_schema({
            "rows": {"kind": "array", "items": object_schema({
                "number": {"kind": "number", "allowed_values": ["1.0"]},
                "string": {"kind": "string", "allowed_values": ["1.0"]},
                "flag": {"kind": "boolean", "allowed_values": [True]},
            }, ["flag", "number", "string"])}
        }, ["rows"])
        trust = self.trust(schema)
        artifact = successor._load_source_artifact(
            b'{"rows":[{"number":1.0,"string":"1.0","flag":true}]}', trust)
        self.assertEqual(len(trust.source_artifacts), 1)
        self.assertIsInstance(artifact.parsed_projection["rows"][0]["number"],
                              successor._JsonNumber)
        for data in (
            b'{"rows":[{"number":"1.0","string":"1.0","flag":true}]}',
            b'{"rows":[{"number":true,"string":"1.0","flag":true}]}',
            b'{"rows":[{"number":1,"string":"1.0","flag":true}]}',
            b'{"rows":[{"number":1.0,"string":1.0,"flag":true}]}',
            b'{"rows":[{"number":1.0,"string":"1.0","flag":false}]}',
            b'{"rows":[{"number":1.0,"string":"1.0","flag":true,"secret":"x"}]}',
        ):
            isolated = self.trust(schema)
            with self.subTest(data=data), self.assertRaisesRegex(
                    successor.CanonicalContractError, "^source-artifact-shape-mismatch$"):
                successor._load_source_artifact(data, isolated)
            self.assertEqual(isolated.source_artifacts, ())

    def test_shape_refusal_never_leaks_path_member_or_value(self):
        trust = self.trust(object_schema({"public": {"kind": "string"}}, ["public"]))
        with self.assertRaises(successor.CanonicalContractError) as caught:
            successor._load_source_artifact(
                b'{"public":"provider-secret-value","api_key":"do-not-leak"}', trust)
        self.assertEqual(str(caught.exception), "source-artifact-shape-mismatch")
        self.assertEqual(trust.source_artifacts, ())

    def test_strict_parser_precedence_and_zero_registration_remain(self):
        for data in (b'{"x":1,"x":2}', b'{"x":NaN}', b'[]'):
            trust = self.trust(object_schema({"x": {"kind": "number"}}, ["x"]))
            with self.subTest(data=data), self.assertRaises(ValueError) as caught:
                successor._load_source_artifact(data, trust)
            self.assertNotIn("source-artifact-shape-mismatch", str(caught.exception))
            self.assertEqual(trust.source_artifacts, ())

    def test_0_4_artifact_loading_never_falls_back_without_a_schema(self):
        for version in ("0.4.0", "0.4.1"):
            trust = successor._construct_loaded_trust_closure(
                source_shape={"media_type": "application/json",
                              "source_shape_ref": {}},
                package_release={
                    "name": "machina-sports-canonical", "version": version,
                    "package_artifact_digest": "sha256:" + "2" * 64,
                    "release_id": "unreleased",
                    "release_digest": "sha256:" + "3" * 64,
                })
            with self.subTest(version=version), self.assertRaisesRegex(
                    successor.CanonicalContractError,
                    "^invalid-source-shape-schema$"):
                successor._load_source_artifact(b'{"x":1}', trust)
            self.assertEqual(trust.source_artifacts, ())

    def test_reparse_rehashes_and_revalidates_original_bytes(self):
        trust = self.trust(object_schema({"x": {"kind": "number"}}, ["x"]))
        artifact = successor._load_source_artifact(b'{"x":1}', trust)
        replacement = b'{"x":"1"}'
        object.__setattr__(artifact, "original_bytes", replacement)
        object.__setattr__(artifact, "artifact_digest", digest_bytes(replacement))
        with self.assertRaisesRegex(successor.CanonicalContractError,
                                    "^source-artifact-shape-mismatch$"):
            successor._reparse_source_artifact(artifact, trust)


class TestClosedSelectorArguments(unittest.TestCase):
    def test_argument_schema_is_closed_and_allowed_values_are_exact(self):
        invalid_values = ([], ["z", "a"], ["a", "a"], [1])
        for values in invalid_values:
            with self.subTest(values=values), self.assertRaisesRegex(
                    successor.CanonicalContractError, "invalid-operation-argument-schema"):
                successor._load_0_4_closure(
                    package_ref=one_record_package(allowed_values=values), request=request())
        package = one_record_package()
        registry = json.loads(package["registry_bytes"])
        package["closure_values"]["argument_schema"]["fields"][0]["extension"] = True
        with self.assertRaisesRegex(successor.CanonicalContractError,
                                    "invalid-operation-argument-schema"):
            successor._load_0_4_closure(package_ref=package, request=request())

    def test_selector_enum_is_enforced_with_bounded_reason(self):
        trust = successor._load_0_4_closure(
            package_ref=one_record_package(), request=request())
        with self.assertRaisesRegex(successor.CanonicalContractError,
                                    "^operation-argument-value-not-allowed$"):
            successor._validate_operation_arguments(
                b'{"fixture_id":"provider-value-must-not-leak"}', trust)

    def test_strict_secret_unknown_type_enum_precedence(self):
        cases = (
            (b'{"api_key":"synthetic"}', "secret-operation-argument-forbidden"),
            (b'{"undeclared_selector":"synthetic"}', "unknown-operation-argument"),
            (b'{"fixture_id":1}', "operation-argument-type-mismatch"),
            (b'{"fixture_id":"not-approved"}', "operation-argument-value-not-allowed"),
        )
        for data, reason in cases:
            trust = successor._load_0_4_closure(
                package_ref=one_record_package(), request=request())
            with self.subTest(data=data), self.assertRaisesRegex(
                    successor.CanonicalContractError, "^{0}$".format(reason)):
                successor._validate_operation_arguments(data, trust)
        trust = successor._load_0_4_closure(
            package_ref=one_record_package(), request=request())
        with self.assertRaises(ValueError) as caught:
            successor._validate_operation_arguments(
                b'{"api_key":"x","api_key":"y"}', trust)
        self.assertIn("duplicate JSON object key", str(caught.exception))

    def test_argument_refusals_have_zero_preflight_activity(self):
        counters = {name: 0 for name in (
            "adapter_import", "adapter_invocation", "fixture_read", "source_load",
            "network", "document", "persistence", "dispatch", "return_bytes")}

        class Loader:
            def load_static(self, package_ref, operation_request):
                return successor._load_0_4_closure(
                    package_ref=one_record_package(), request=operation_request)

            def import_adapter(self, trust):
                counters["adapter_import"] += 1
                raise AssertionError("adapter import must remain at zero")

        with self.assertRaisesRegex(successor.CanonicalContractError,
                                    "operation-argument-value-not-allowed"):
            successor.execute_adapter_operation(
                package_ref={}, request_bytes=successor.canonical_json_bytes(request()),
                operation_arguments_bytes=b'{"fixture_id":"not-approved"}',
                trusted_loader=Loader())
        self.assertEqual(counters, dict.fromkeys(counters, 0))


if __name__ == "__main__":
    unittest.main()
