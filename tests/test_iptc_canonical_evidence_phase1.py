"""Canonical Evidence Contract Phase 1 owner conformance tests."""

from __future__ import annotations

import importlib.util
import inspect
import json
import subprocess
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
observation = SUPPORT.canonical_module("observation")
serialize = SUPPORT.canonical_module("serialize")
validate_observation = observation.validate_observation
canonical_envelope = serialize.canonical_envelope
sport_schema_graph = serialize.sport_schema_graph


LEGACY_ALL = (
    "PROFILE_VERSION",
    "EXACT_OBSERVATION_PROFILE_VERSION",
    "SCHEMA_VERSION",
    "PREDECESSOR_SCHEMA_VERSION",
    "ACCEPTED_SCHEMA_VERSIONS",
    "MACHINA_SCHEMA_VERSION",
    "SERIALIZER_VERSION",
    "SERIALIZER_NAME",
    "UPSTREAM_REPOSITORY",
    "UPSTREAM_COMMIT",
    "UPSTREAM_TARGET_VERSION",
)

ADDITIVE_ALL = (
    "SUCCESSOR_PROFILE_VERSION",
    "SUCCESSOR_SCHEMA_VERSION",
    "SUCCESSOR_MACHINA_SCHEMA_VERSION",
    "LONGITUDINAL_SCHEMA_VERSION",
    "LONGITUDINAL_MACHINA_SCHEMA_VERSION",
)


def coverage_source_record(successor, namespace, pointer, count, artifact, index):
    record = {
        "id": "coverage-{0}".format(index), "version": "1",
        "kind": "coverage_source",
        "source": {"kind": "provider_record", "provider_namespace": namespace,
                   "record_id": "coverage"},
        "coverage_source": {
            "schema_version": "machina-coverage-source-evidence/1",
            "collection_pointer": pointer,
            "artifact_digest": artifact.artifact_digest,
            "fields": [],
            "reported_total": {"state": "known", "count": count,
                               "value_pointers": ["/totals/{0}".format(index - 1)]},
            "truncation": {"state": "not_truncated",
                           "value_pointers": ["/truncated"]},
            "cursor": {"state": "absent", "absence_probes": [
                {"probe": "member_absent", "pointer": "/cursor"}]},
            "page_cap": {"state": "none_reported", "absence_probes": [
                {"probe": "member_absent", "pointer": "/page_cap"}]},
            "request_limit": {"state": "none_reported", "absence_probes": [
                {"probe": "member_absent", "pointer": "/limit"}]},
        },
    }
    record["digest"] = successor.evidence_record_digest(record)
    return record


def successor_fixture(successor, promise_collections=True, promise_actions=False):
    document = json.loads((
        REPO_ROOT / "tools/iptc/fixtures/observations/"
        "mapping-contract-synthetic-observation.json"
    ).read_text(encoding="utf-8"))
    document["schema_version"] = canonical.SUCCESSOR_SCHEMA_VERSION
    for participant in document["observation"]["participants"]:
        participant["statistics"] = []
    namespace = document["observation"]["provider"]["namespace"]
    rights = {
        "profile_id": "mapping-contract", "profile_version": "1",
        "provider_namespace": namespace, "operation": "event",
        "data_class": "mapping-contract-synthetic", "prototype_only": True,
        "commercial_use": False, "allowed_consumer_tiers": ["prototype"],
        "rights_profile_digest": "sha256:" + "1" * 64,
    }
    trust = successor._construct_loaded_trust_closure(
        descriptor={"schema_version": "machina-adapter-descriptor/1",
                    "provider_namespace": namespace, "operation": "event",
                    "capabilities": [], "module_entrypoint": "fixture"},
        rights_profile=rights,
        source_shape={"media_type": "application/json", "source_shape_ref": {}},
        operation_contract={
            "promised_collections": ([
                {"pointer_pattern": "/observation/participants"},
                {"pointer_pattern": "/observation/participants/{participant_index}/statistics"},
            ] if promise_collections else []) + ([
                {"pointer_pattern": "/observation/actions"}
            ] if promise_actions else []),
            "promised_non_collection_evidence": [],
        },
    )
    artifact = successor._load_source_artifact(
        b'{"identity":"declared","totals":[3,0,0,0],"truncated":false}', trust)
    method_record = {
        "id": "provider-methods",
        "version": "1",
        "kind": "source_value",
        "source": {"kind": "provider_record", "provider_namespace": namespace,
                   "record_id": "mapping-contract"},
        "source_value": {
            "schema_version": "machina-source-value-evidence/1",
            "artifact_digest": artifact.artifact_digest,
            "value_pointer": "/identity",
            "value_digest": successor.derive_source_value_digest(
                artifact.artifact_digest, "/identity"),
        },
    }
    method_record["digest"] = successor.evidence_record_digest(method_record)
    inventory = [
        ("competition", "/observation/competition", "/observation/competition/provider_id"),
        ("season", "/observation/competition/season", "/observation/competition/season/provider_id"),
        ("site", "/observation/site", "/observation/site/provider_id"),
        ("event", "/observation/event", "/observation/event/provider_id"),
    ]
    inventory.extend(
        ("athlete", "/observation/participants/{0}".format(index),
         "/observation/participants/{0}/provider_id".format(index))
        for index in range(3)
    )
    identities = []
    subjects = []
    for index, (entity_type, subject_ref, provider_ref) in enumerate(inventory):
        provider_id = successor.resolve_json_pointer(document, provider_ref)
        provider = {"namespace": namespace, "id": provider_id}
        identities.append({
            "entity_type": entity_type,
            "provider": provider,
            "resolution_method": "declared",
            "method_source_ref": "/evidence_records/0",
            "status": "provider_scoped",
            "provider_scoped_id": successor._provider_scoped_id(
                namespace, entity_type, provider_id),
        })
        subjects.append({
            "subject_ref": subject_ref,
            "entity_type": entity_type,
            "identity_evidence_ref": "/identity_evidence/{0}".format(index),
            "inherited_provider": {"provider_id_ref": provider_ref,
                                   "provider": provider},
        })
    pointers = ["/observation/participants"] + [
        "/observation/participants/{0}/statistics".format(index)
        for index in range(3)
    ]
    claims = [{"collection_pointer": pointer,
               "target": "participants" if pointer.endswith("participants") else "statistics"}
              for pointer in pointers]
    coverage_records = [coverage_source_record(
        successor, namespace, claim["collection_pointer"],
        3 if claim["target"] == "participants" else 0, artifact, index)
        for index, claim in enumerate(claims, start=1)]
    coverage = [{
        "target": claim["target"],
        "collection_pointer": claim["collection_pointer"],
        "returned_count": 3 if claim["target"] == "participants" else 0,
        "available_total": {"state": "known",
                            "count": 3 if claim["target"] == "participants" else 0},
        "completeness": "complete",
        "truncation": "not_truncated",
        "limitations": [],
        "source_ref": "/evidence_records/{0}".format(index),
    } for index, claim in enumerate(claims, start=1)]
    document.update({
        "coordinate_system_registry": [], "period_registry": [],
        "evidence_records": [method_record] + coverage_records,
        "collection_claims": claims,
        "coverage": coverage, "identity_subjects": subjects,
        "identity_evidence": identities,
    })
    return document, trust


def longitudinal_fixture(successor):
    namespace = "sports-skills/espn"
    rights = {
        "profile_id": "espn-prototype", "profile_version": "1",
        "provider_namespace": namespace, "operation": "longitudinal",
        "data_class": "public-prototype", "prototype_only": True,
        "commercial_use": False, "allowed_consumer_tiers": ["prototype"],
        "rights_profile_digest": "sha256:" + "1" * 64,
    }
    trust = successor._construct_loaded_trust_closure(
        descriptor={"schema_version": "machina-adapter-descriptor/1",
                    "provider_namespace": namespace, "operation": "longitudinal",
                    "capabilities": [], "module_entrypoint": "fixture"},
        rights_profile=rights,
        source_shape={"media_type": "application/json", "source_shape_ref": {}},
        operation_contract={"promised_collections": [
            {"pointer_pattern": "/records"}, {"pointer_pattern": "/aggregates"},
            {"pointer_pattern": "/records/{record_index}/statistics"},
        ], "promised_non_collection_evidence": []},
    )
    artifact = successor._load_source_artifact(
        b'{"identity":"declared","totals":[0,0],"truncated":false}', trust)
    source = {
        "id": "identity-source", "version": "1", "kind": "source_value",
        "source": {"kind": "provider_record", "provider_namespace": namespace,
                   "record_id": "season"},
        "source_value": {"schema_version": "machina-source-value-evidence/1",
                         "artifact_digest": artifact.artifact_digest,
                         "value_pointer": "/identity",
                         "value_digest": successor.derive_source_value_digest(
                             artifact.artifact_digest, "/identity")},
    }
    source["digest"] = successor.evidence_record_digest(source)
    identities = []
    for entity_type, provider_id in (("athlete", "7"), ("season", "2026")):
        identities.append({
            "entity_type": entity_type,
            "provider": {"namespace": namespace, "id": provider_id},
            "resolution_method": "declared", "method_source_ref": "/evidence_records/0",
            "status": "provider_scoped",
            "provider_scoped_id": successor._provider_scoped_id(
                namespace, entity_type, provider_id),
        })
    scope = {"kind": "season", "sport": "basketball",
             "season_identity_ref": "/identity_evidence/1"}
    provenance = {
        "schema_version": "machina-successor-provenance/1",
        "canonical_input_version": canonical.LONGITUDINAL_SCHEMA_VERSION,
        "canonical_package": dict(trust.package_release),
        "adapter": {"provider_namespace": namespace, "operation": "longitudinal",
                    "descriptor_digest": "sha256:" + "6" * 64},
        "source_artifact_digests": [artifact.artifact_digest],
    }
    coverage_records = [
        coverage_source_record(successor, namespace, "/" + target, 0,
                               artifact, index)
        for index, target in enumerate(("records", "aggregates"), start=1)
    ]
    document = {
        "schema_version": canonical.LONGITUDINAL_SCHEMA_VERSION,
        "observed_at": "2026-08-16T12:00:00Z",
        "subject": {"entity_type": "athlete", "identity_ref": "/identity_evidence/0"},
        "scope": scope, "records": [], "aggregates": [],
        "evidence_records": [source] + coverage_records,
        "collection_claims": [
            {"collection_pointer": "/records", "target": "records"},
            {"collection_pointer": "/aggregates", "target": "aggregates"},
        ],
        "coverage": [
            {"target": target, "collection_pointer": "/" + target,
             "returned_count": 0, "available_total": {"state": "known", "count": 0},
             "completeness": "complete", "truncation": "not_truncated",
             "limitations": [], "source_ref": "/evidence_records/{0}".format(index)}
            for index, target in enumerate(("records", "aggregates"), start=1)
        ],
        "identity_subjects": [
            {"subject_ref": "/subject", "entity_type": "athlete",
             "identity_evidence_ref": "/identity_evidence/0"},
            {"subject_ref": "/identity_evidence/1", "entity_type": "season",
             "identity_evidence_ref": "/identity_evidence/1"},
        ],
        "identity_evidence": identities, "provenance": provenance, "rights": rights,
    }
    return document, trust


class TestFrozenLegacySurface(unittest.TestCase):
    def test_legacy_values_and_additive_exports_are_exact(self):
        self.assertEqual(canonical.SCHEMA_VERSION, "canonical-observation/1.1")
        self.assertEqual(canonical.PROFILE_VERSION, "machina-iptc-profile/1.2")
        self.assertEqual(canonical.MACHINA_SCHEMA_VERSION, "machina-sports-schema/1")
        self.assertEqual(canonical.SUCCESSOR_SCHEMA_VERSION, "canonical-observation/1.2")
        self.assertEqual(canonical.SUCCESSOR_PROFILE_VERSION, "machina-iptc-profile/1.3")
        self.assertEqual(
            canonical.SUCCESSOR_MACHINA_SCHEMA_VERSION, "machina-sports-schema/1.1"
        )
        self.assertEqual(
            canonical.LONGITUDINAL_SCHEMA_VERSION,
            "canonical-longitudinal-statistics/1",
        )
        self.assertEqual(
            canonical.LONGITUDINAL_MACHINA_SCHEMA_VERSION,
            "machina-longitudinal-schema/1",
        )
        self.assertEqual(tuple(canonical.__all__), LEGACY_ALL + ADDITIVE_ALL)

    def test_three_frozen_signatures_are_unannotated(self):
        self.assertEqual(str(inspect.signature(validate_observation)), "(document)")
        self.assertEqual(
            str(inspect.signature(sport_schema_graph)), "(document, *, id_resolver)"
        )
        self.assertEqual(
            str(inspect.signature(canonical_envelope)), "(document, *, id_resolver)"
        )

    def test_private_producer_names_are_not_exported(self):
        private = {
            "_load_source_artifact",
            "_build_statistic_fact",
            "_build_successor_envelope",
            "_derive_operational_resource_id",
            "execute_adapter_operation",
        }
        self.assertFalse(private.intersection(canonical.__all__))

    def test_legacy_direct_graph_is_successor_blind_before_resolver_use(self):
        calls = []

        def resolver(*parts):
            calls.append(parts)
            return "urn:should-not-exist"

        with self.assertRaisesRegex(ValueError, "not one of"):
            sport_schema_graph(
                {"schema_version": canonical.SUCCESSOR_SCHEMA_VERSION,
                 "observation": {"event": {"provider_id": "event"}}},
                id_resolver=resolver,
            )
        self.assertEqual(calls, [])

    def test_additive_reader_and_execution_signatures_are_closed(self):
        successor = SUPPORT.canonical_module("successor")
        self.assertEqual(
            str(inspect.signature(successor.parse_legacy_observation_bytes)),
            "(data: 'bytes') -> 'dict[str, Any]'",
        )
        self.assertEqual(
            tuple(inspect.signature(successor.execute_adapter_operation).parameters),
            ("package_ref", "request_bytes", "operation_arguments_bytes", "trusted_loader"),
        )
        self.assertTrue(all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            for parameter in inspect.signature(
                successor.execute_adapter_operation).parameters.values()))


class TestStrictByteBoundaries(unittest.TestCase):
    def setUp(self):
        successor = SUPPORT.canonical_module("successor")

        self.successor = successor
        self.trust = successor._construct_loaded_trust_closure()

    def test_legacy_parser_accepts_only_predecessor_and_current(self):
        for version in ("canonical-observation/1", "canonical-observation/1.1"):
            with self.subTest(version=version):
                document = json.loads((
                    REPO_ROOT / "tools/iptc/fixtures/observations/"
                    "mapping-contract-synthetic-observation.json"
                ).read_text(encoding="utf-8"))
                document["schema_version"] = version
                result = self.successor.parse_legacy_observation_bytes(
                    json.dumps(document).encode()
                )
                self.assertEqual(result["schema_version"], version)
        with self.assertRaises(ValueError):
            self.successor.parse_legacy_observation_bytes(
                b'{"schema_version":"canonical-observation/1.2","observation":{}}'
            )

    def test_successor_and_longitudinal_routes_are_disjoint(self):
        successor = b'{"schema_version":"canonical-observation/1.2"}'
        longitudinal = b'{"schema_version":"canonical-longitudinal-statistics/1"}'
        with self.assertRaises(ValueError):
            self.successor.parse_successor_observation_bytes(longitudinal, trust_closure=self.trust)
        with self.assertRaises(ValueError):
            self.successor.parse_longitudinal_bytes(successor, trust_closure=self.trust)

    def test_all_additive_text_boundaries_reject_invalid_json_bytes(self):
        invalid = (
            b'\xef\xbb\xbf{}',
            b'{"schema_version":"canonical-observation/1.2","x":"\xff"}',
            b'{"schema_version":"canonical-observation/1.2","x":"\xef\xbf\xbd"}',
            b'{"schema_version":"canonical-observation/1.2","x":NaN}',
            b'[]',
        )
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.successor.parse_successor_observation_bytes(data, trust_closure=self.trust)

    def test_duplicate_keys_fail_at_every_depth(self):
        for data in (
            b'{"schema_version":"canonical-observation/1.2","schema_version":"canonical-observation/1.2"}',
            b'{"schema_version":"canonical-observation/1.2","x":{"a":1,"a":2}}',
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.successor.parse_successor_observation_bytes(data, trust_closure=self.trust)


class TestClosedGrammarAndAlgorithms(unittest.TestCase):
    def test_provider_namespace_vectors(self):
        validate_provider_namespace = SUPPORT.canonical_module(
            "successor").validate_provider_namespace

        for value in ("provider-a", "sports-skills/espn", "A.b_9-x"):
            with self.subTest(value=value):
                self.assertEqual(validate_provider_namespace(value), value)
        invalid = (
            "/espn", "espn/", "sports-skills//espn", "a/b/c", ".", "..",
            "sports-skills/../espn", "https://espn", "user@espn", "espn?key=x",
            "espn#fragment", "espn%2Ffeed", "espn\\feed", " espn", "espn\n",
            "espn-\u00e9",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_provider_namespace(value)

    def test_statistic_lexical_grammars(self):
        validate_statistic_lexical = SUPPORT.canonical_module(
            "successor").validate_statistic_lexical

        valid = {
            "integer": ("0", "-1", "12"),
            "decimal": ("0.0", "-0.5", "12.25"),
            "boolean": ("true", "false"),
            "duration": ("PT0S", "PT34M", "P2DT3H4M5.25S"),
            "text": ("x",),
        }
        for kind, values in valid.items():
            for value in values:
                with self.subTest(kind=kind, value=value):
                    self.assertEqual(validate_statistic_lexical(kind, value), value)
        for kind, value in (
            ("integer", "-0"), ("integer", "+1"), ("integer", "01"),
            ("decimal", "-0.0"), ("decimal", "1.20"), ("decimal", "1e2"),
            ("boolean", "True"), ("duration", "P1Y"), ("text", ""),
        ):
            with self.subTest(kind=kind, value=value), self.assertRaises(ValueError):
                validate_statistic_lexical(kind, value)

    def test_range_endpoint_ordering(self):
        validate_temporal_range = SUPPORT.canonical_module(
            "successor").validate_temporal_range

        exact = lambda value: {"state": "exact", "instant": value, "source_ref": "/e"}
        bounded = lambda lower, upper: {
            "state": "bounded",
            "source_value": lower[:16] + "+00:00",
            "precision": "minute",
            "lower_inclusive": lower,
            "upper_exclusive": upper,
            "provenance": {
                "normalizer": "test", "normalizer_version": "1",
                "canonical_version": "0.3.0",
                "derivation": {"id": "declared_precision_interval", "version": "1"},
            },
            "source_ref": "/e",
        }
        base = {
            "schema_version": "canonical-temporal-range/1",
            "interval_semantics": "start_inclusive_end_exclusive",
        }
        with self.assertRaises(ValueError):
            validate_temporal_range(dict(base, start=exact("2026-01-01T00:00:00Z"), end=exact("2026-01-01T00:00:00Z")))
        validate_temporal_range(dict(base, start=bounded("2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"), end=exact("2026-01-01T00:01:00Z")))

    def test_domain_separated_digest_and_id_vectors_are_stable(self):
        successor = SUPPORT.canonical_module("successor")
        canonical_json_bytes = successor.canonical_json_bytes
        derive_source_value_digest = successor.derive_source_value_digest
        document_fingerprint = successor.document_fingerprint

        preimage = ["machina-source-value-ref-digest-v1", "sha256:" + "a" * 64, "/a~1b"]
        self.assertEqual(canonical_json_bytes(preimage), b'["machina-source-value-ref-digest-v1","sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","/a~1b"]')
        self.assertEqual(
            derive_source_value_digest("sha256:" + "a" * 64, "/a~1b"),
            "sha256:a95e09dbceac864324cf76f39966f810d80d8bf3e3520cf6654c850ff25c0339",
        )
        first = {"schema_version": "canonical-observation/1.2", "b": 1, "a": [2, 1]}
        second = {"a": [2, 1], "b": 1, "schema_version": "canonical-observation/1.2"}
        self.assertEqual(document_fingerprint(first), document_fingerprint(second))


class TestOpaqueRuntimeBoundary(unittest.TestCase):
    def test_raw_mapping_and_lookalike_trust_objects_fail(self):
        validate_successor_observation = SUPPORT.canonical_module(
            "successor").validate_successor_observation

        for trust in ({}, object()):
            with self.subTest(trust=type(trust).__name__), self.assertRaises(TypeError):
                validate_successor_observation(
                    {"schema_version": "canonical-observation/1.2"},
                    trust_closure=trust,
                )

    def test_runtime_handles_are_not_json_serializable(self):
        _construct_loaded_trust_closure = SUPPORT.canonical_module(
            "successor")._construct_loaded_trust_closure

        with self.assertRaises(TypeError):
            json.dumps(_construct_loaded_trust_closure())


class TestSuccessorDocumentContract(unittest.TestCase):
    def setUp(self):
        self.successor = SUPPORT.canonical_module("successor")
        self.document, self.trust = successor_fixture(self.successor)

    def test_valid_successor_returns_an_opaque_document_handle(self):
        handle = self.successor.validate_successor_observation(
            self.document, trust_closure=self.trust)
        self.assertIsInstance(handle, self.successor.ValidatedDocumentHandleV1)
        self.assertRegex(handle.document_fingerprint, r"^sha256:[0-9a-f]{64}$")

    def test_successor_parser_validates_the_same_document(self):
        parsed = self.successor.parse_successor_observation_bytes(
            self.successor.canonical_json_bytes(self.document),
            trust_closure=self.trust)
        self.assertEqual(parsed, self.document)

    def test_handle_owns_an_immutable_copy(self):
        handle = self.successor.validate_successor_observation(
            self.document, trust_closure=self.trust)
        self.document["observation"]["event"]["provider_id"] = "mutated"
        self.assertNotEqual(
            self.successor.resolve_json_pointer(
                handle._document, "/observation/event/provider_id"),
            "mutated",
        )

    def test_unknown_outer_member_fails(self):
        self.document["extension"] = {}
        with self.assertRaisesRegex(ValueError, "unknown members"):
            self.successor.validate_successor_observation(
                self.document, trust_closure=self.trust)

    def test_inherited_provider_tuple_contradiction_fails(self):
        self.document["identity_subjects"][0]["inherited_provider"]["provider"]["id"] = "other"
        with self.assertRaisesRegex(ValueError, "contradicts"):
            self.successor.validate_successor_observation(
                self.document, trust_closure=self.trust)

    def test_present_unpromised_collection_fails_immediately(self):
        self.document, self.trust = successor_fixture(
            self.successor, promise_collections=False)
        with self.assertRaisesRegex(ValueError, "unpromised-managed-collection-present"):
            self.successor.validate_successor_observation(
                self.document, trust_closure=self.trust)

    def test_unavailable_total_cannot_claim_complete(self):
        self.document["coverage"][0]["available_total"] = {"state": "unavailable"}
        with self.assertRaisesRegex(ValueError, "cannot imply complete"):
            self.successor.validate_successor_observation(
                self.document, trust_closure=self.trust)

    def test_returned_count_and_source_total_are_recomputed(self):
        self.document["coverage"][0]["returned_count"] = 0
        with self.assertRaisesRegex(ValueError, "returned_count"):
            self.successor.validate_successor_observation(
                self.document, trust_closure=self.trust)

    def test_coverage_record_is_closed(self):
        self.document["coverage"][0]["extension"] = True
        with self.assertRaisesRegex(ValueError, "unknown members"):
            self.successor.validate_successor_observation(
                self.document, trust_closure=self.trust)

    def test_present_cursor_forces_partial_coverage(self):
        trust = self.successor._construct_loaded_trust_closure(
            source_shape={"media_type": "application/json", "source_shape_ref": {}})
        artifact = self.successor._load_source_artifact(
            b'{"total":3,"truncated":false,"cursor":"next"}', trust)
        source = {
            "reported_total": {"state": "known", "count": 3,
                               "value_pointers": ["/total"]},
            "truncation": {"state": "not_truncated",
                           "value_pointers": ["/truncated"]},
            "cursor": {"state": "present", "value_pointers": ["/cursor"],
                       "value_digest": "sha256:" + "1" * 64},
            "page_cap": {"state": "none_reported", "absence_probes": [
                {"probe": "member_absent", "pointer": "/page_cap"}]},
            "request_limit": {"state": "none_reported", "absence_probes": [
                {"probe": "member_absent", "pointer": "/limit"}]},
        }
        item = {"returned_count": 3,
                "available_total": {"state": "known", "count": 3},
                "completeness": "complete", "truncation": "not_truncated"}
        errors = []
        self.successor._validate_coverage_recomputation(
            item, source, artifact, trust, errors)
        self.assertIn("coverage completeness does not recompute", errors)

    def test_absence_probes_cannot_hide_cursor_cap_or_limit(self):
        trust = self.successor._construct_loaded_trust_closure(
            source_shape={"media_type": "application/json", "source_shape_ref": {}})
        artifact = self.successor._load_source_artifact(
            b'{"total":3,"truncated":false,"cursor":"next","page_cap":50,"limit":25}',
            trust)
        absent = lambda pointer, state: {
            "state": state,
            "absence_probes": [{"probe": "member_absent", "pointer": pointer}],
        }
        source = {
            "reported_total": {"state": "known", "count": 3,
                               "value_pointers": ["/total"]},
            "truncation": {"state": "not_truncated",
                           "value_pointers": ["/truncated"]},
            "cursor": absent("/cursor", "absent"),
            "page_cap": absent("/page_cap", "none_reported"),
            "request_limit": absent("/limit", "none_reported"),
        }
        item = {"returned_count": 3,
                "available_total": {"state": "known", "count": 3},
                "completeness": "complete", "truncation": "not_truncated"}
        errors = []
        self.successor._validate_coverage_recomputation(
            item, source, artifact, trust, errors)
        self.assertEqual(sum("absent probe found a value" in error for error in errors), 3)

    def test_source_backed_statistic_requires_an_attested_binding(self):
        self.document["observation"]["participants"][0]["statistics"] = [{
            "kind": "official", "scope": "event",
            "name": "spsocstat:cornerKicks",
            "value": {"kind": "integer", "lexical": "999"},
            "source_ref": "/evidence_records/0",
        }]
        handle = self.successor.ValidatedDocumentHandleV1(
            self.successor._HANDLE_SEAL, self.document,
            self.successor.document_fingerprint(self.document), self.trust)
        with self.assertRaisesRegex(ValueError, "statistic-source-binding-not-unique"):
            self.successor._build_statistic_fact(
                handle, fact_ref="/observation/participants/0/statistics/0",
                trust_closure=self.trust)

    def test_invalid_nested_provider_namespace_fails(self):
        self.document["evidence_records"][0]["source"][
            "provider_namespace"] = "a/b/c"
        self.document["evidence_records"][0]["digest"] = \
            self.successor.evidence_record_digest(self.document["evidence_records"][0])
        with self.assertRaisesRegex(ValueError, "invalid ProviderNamespace"):
            self.successor.validate_successor_observation(
                self.document, trust_closure=self.trust)

    def test_caller_authored_spatial_coordinates_fail(self):
        self.document, self.trust = successor_fixture(
            self.successor, promise_actions=True)
        self.document["observation"]["actions"] = [{
            "ordinal": "1", "class": "play",
            "spatial_evidence": {"x": "1.0", "y": "2.0"},
        }]
        with self.assertRaisesRegex(ValueError, "caller-authored"):
            self.successor.validate_successor_observation(
                self.document, trust_closure=self.trust)

    def test_graphless_exact_envelope_has_no_graph_or_unavailability_reason(self):
        handle = self.successor.validate_successor_observation(
            self.document, trust_closure=self.trust)
        result = json.loads(self.successor._build_successor_envelope(
            handle, output_mode="operational_only", trust_closure=self.trust))
        root = result["machina_sports_schema"]
        self.assertNotIn("sport_schema_graph", root)
        self.assertNotIn("graph_unavailable_reason", root["capabilities"])

    def test_provider_scoped_identity_refuses_graph_before_projection(self):
        handle = self.successor.validate_successor_observation(
            self.document, trust_closure=self.trust)
        with self.assertRaisesRegex(ValueError, "canonical-identity-required-for-graph"):
            self.successor._build_successor_envelope(
                handle, output_mode="with_iptc_graph", trust_closure=self.trust)

    def test_operational_id_is_document_and_pointer_bound(self):
        first = self.successor.validate_successor_observation(
            self.document, trust_closure=self.trust)
        first_id = self.successor._derive_operational_resource_id(
            first, resource_kind="participation",
            canonical_rfc6901_pointer="/observation/participants/0")
        changed = json.loads(json.dumps(self.document))
        changed["observation"]["event"]["provider_id"] = "event-other"
        changed["identity_evidence"][3]["provider"]["id"] = "event-other"
        changed["identity_evidence"][3]["provider_scoped_id"] = \
            self.successor._provider_scoped_id(
                changed["observation"]["provider"]["namespace"], "event", "event-other")
        changed["identity_subjects"][3]["inherited_provider"]["provider"]["id"] = "event-other"
        second = self.successor.validate_successor_observation(
            changed, trust_closure=self.trust)
        second_id = self.successor._derive_operational_resource_id(
            second, resource_kind="participation",
            canonical_rfc6901_pointer="/observation/participants/0")
        self.assertNotEqual(first_id, second_id)


class TestLongitudinalDocumentContract(unittest.TestCase):
    def setUp(self):
        self.successor = SUPPORT.canonical_module("successor")
        self.document, self.trust = longitudinal_fixture(self.successor)

    def test_valid_longitudinal_document_and_envelope(self):
        handle = self.successor.validate_longitudinal_document(
            self.document, trust_closure=self.trust)
        output = json.loads(self.successor._build_successor_envelope(
            handle, output_mode="operational_only", trust_closure=self.trust))
        root = output["machina_longitudinal_schema"]
        self.assertEqual(root["schema_version"], canonical.LONGITUDINAL_MACHINA_SCHEMA_VERSION)
        self.assertNotIn("sport_schema_graph", root)

    def test_longitudinal_graph_mode_is_refused(self):
        handle = self.successor.validate_longitudinal_document(
            self.document, trust_closure=self.trust)
        with self.assertRaisesRegex(ValueError, "operational-only"):
            self.successor._build_successor_envelope(
                handle, output_mode="with_iptc_graph", trust_closure=self.trust)

    def test_event_scope_is_refused(self):
        self.document["scope"] = {"kind": "event", "sport": "basketball"}
        with self.assertRaisesRegex(ValueError, "scope kind is invalid"):
            self.successor.validate_longitudinal_document(
                self.document, trust_closure=self.trust)

    def test_subject_and_scope_identity_refs_must_resolve_with_matching_types(self):
        self.document["subject"]["identity_ref"] = "/identity_evidence/99"
        self.document["scope"]["season_identity_ref"] = 7
        with self.assertRaisesRegex(ValueError, "identity_ref"):
            self.successor.validate_longitudinal_document(
                self.document, trust_closure=self.trust)

    def test_unknown_total_state_is_refused(self):
        self.document["coverage"][0]["available_total"] = {"state": "unknown"}
        with self.assertRaisesRegex(ValueError, "known or unavailable"):
            self.successor.validate_longitudinal_document(
                self.document, trust_closure=self.trust)


class TestSourceArtifactBoundary(unittest.TestCase):
    def setUp(self):
        self.successor = SUPPORT.canonical_module("successor")
        self.trust = self.successor._construct_loaded_trust_closure(
            source_shape={"media_type": "application/json", "source_shape_ref": {}})

    def test_source_projection_is_deep_frozen_and_reparsed(self):
        artifact = self.successor._load_source_artifact(
            b'{"nested":{"items":[1,2]}}', self.trust)
        with self.assertRaises(TypeError):
            artifact.parsed_projection["nested"]["x"] = 1
        with self.assertRaises(TypeError):
            artifact.parsed_projection["nested"]["items"][0] = 9
        self.assertEqual(
            self.successor._reparse_source_artifact(artifact, self.trust)["nested"]["items"],
            ["1", "2"],
        )

    def test_source_boundary_rejects_duplicates_and_replacement_character(self):
        for data in (b'{"x":1,"x":2}', b'{"x":"\xef\xbf\xbd"}'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.successor._load_source_artifact(data, self.trust)

    def test_artifact_cannot_cross_closures(self):
        artifact = self.successor._load_source_artifact(b'{"x":1}', self.trust)
        other = self.successor._construct_loaded_trust_closure(
            source_shape={"media_type": "application/json", "source_shape_ref": {}})
        with self.assertRaises(TypeError):
            self.successor._reparse_source_artifact(artifact, other)

    def test_artifact_bytes_digest_and_closure_are_not_assignable(self):
        artifact = self.successor._load_source_artifact(b'{"x":1}', self.trust)
        for name, value in (("original_bytes", b'{"x":2}'),
                            ("artifact_digest", "sha256:" + "0" * 64),
                            ("_closure_id", object())):
            with self.subTest(name=name), self.assertRaises(TypeError):
                setattr(artifact, name, value)

    def test_execution_refuses_a_reused_closure_before_adapter_import(self):
        self.successor._load_source_artifact(b'{"x":1}', self.trust)
        imported = []

        class Loader:
            def load_static(_self, package_ref, request):
                return self.trust

            def import_adapter(_self, trust):
                imported.append(True)
                raise AssertionError("adapter import must remain at zero")

        request = self.successor.canonical_json_bytes({
            "requested_provider": "provider-a", "requested_operation": "event",
            "output_kind": "event", "output_mode": "operational_only",
            "consumer_tier": "prototype", "requires": [], "optional": [],
        })
        with self.assertRaisesRegex(ValueError, "closure-reused"):
            self.successor.execute_adapter_operation(
                package_ref={"package_name": "fixture", "package_version": "1",
                             "release_id": "fixture"},
                request_bytes=request, operation_arguments_bytes=b'{}',
                trusted_loader=Loader())
        self.assertEqual(imported, [])

    def test_artifact_session_has_no_unsealed_append_path(self):
        self.assertFalse(hasattr(self.trust._artifact_session, "append"))
        with self.assertRaises(TypeError):
            self.trust._artifact_session.register(object(), object())

    def test_source_number_and_string_representations_are_disjoint(self):
        number = self.successor._strict_json_object(b'{"x":8.0}', preserve_numbers=True)["x"]
        self.assertEqual(self.successor._parse_spatial_source(
            number, "json-number-exact-spatial-decimal/1"), "8.0")
        self.assertEqual(self.successor._parse_spatial_source(
            "8.0", "json-string-canonical-spatial-decimal/1"), "8.0")
        with self.assertRaises(ValueError):
            self.successor._parse_spatial_source(
                number, "json-string-canonical-spatial-decimal/1")
        with self.assertRaises(ValueError):
            self.successor._parse_spatial_source(
                "8.0", "json-number-exact-spatial-decimal/1")

    def test_longitudinal_period_is_built_from_one_artifact_tuple(self):
        artifact = self.successor._load_source_artifact(
            b'{"records":[{"period":{"scheme":"week","value":"week-1","sequence":1}}]}',
            self.trust)
        template = {
            "semantic_kind": "longitudinal_period",
            "scheme_pointer_template": "/records/{record_index}/period/scheme",
            "value_pointer_template": "/records/{record_index}/period/value",
            "sequence_pointer_template": "/records/{record_index}/period/sequence",
            "interpretation": {
                "scheme_values": ["week"],
                "sequence_numeric_parser": {
                    "source_representation": "json-number-exact-non-negative-integer/1"},
            },
        }
        handle = self.successor._load_source_value_handle(
            artifact, template, {"record_index": 0}, self.trust)
        self.assertEqual(self.successor._build_period_descriptor(
            handle, record_ref="/records/0", loaded_trust=self.trust), {
                "period": {"scheme": "week", "value": "week-1", "sequence": 1}})
        with self.assertRaises(ValueError):
            self.successor._build_period_descriptor(
                handle, record_ref="/records/1", loaded_trust=self.trust)

    def test_rolling_anchor_is_built_from_the_empty_tuple(self):
        artifact = self.successor._load_source_artifact(
            b'{"scope":{"anchor":{"provider_namespace":"sports-skills/espn","provider_id":"401","resolution_method":"provider_native","source":{"record":"401"}}}}',
            self.trust)
        template = {
            "semantic_kind": "rolling_event_anchor",
            "provider_namespace_pointer_template": "/scope/anchor/provider_namespace",
            "provider_id_pointer_template": "/scope/anchor/provider_id",
            "resolution_method_pointer_template": "/scope/anchor/resolution_method",
            "event_source_pointer_template": "/scope/anchor/source",
        }
        handle = self.successor._load_source_value_handle(
            artifact, template, {}, self.trust)
        anchor = self.successor._build_rolling_event_anchor(
            handle, anchor_ref="/scope/anchor", loaded_trust=self.trust)
        self.assertEqual(anchor["provider"]["namespace"], "sports-skills/espn")
        self.assertEqual(anchor["event_source"], {"record": "401"})

    def test_period_sequence_rejects_decimal_parser_and_wrong_representation(self):
        with self.assertRaisesRegex(ValueError, "not-non-negative-integer"):
            self.successor._parse_non_negative_integer_source(
                "1", {"source_representation": "json-string-canonical-spatial-decimal/1"})
        with self.assertRaisesRegex(ValueError, "representation-mismatch"):
            self.successor._parse_non_negative_integer_source(
                "1", {"source_representation": "json-number-exact-non-negative-integer/1"})


class TestGeneratedOwnerData(unittest.TestCase):
    def setUp(self):
        self.data = REPO_ROOT / "tools/iptc/canonical/data"

    def test_admissibility_is_reproducible_from_unchanged_pinned_bytes(self):
        target = self.data / "official_statistic_admissibility_v1.json"
        before = target.read_bytes()
        subprocess.run(
            [sys.executable, "tools/iptc/generate_phase1_manifests.py"],
            cwd=str(REPO_ROOT), check=True, timeout=120)
        self.assertEqual(target.read_bytes(), before)

    def test_shape_admission_fixtures_match_the_pinned_shapes(self):
        manifest = json.loads((self.data / "official_statistic_admissibility_v1.json").read_text(encoding="utf-8"))
        rows = {(item["curie"], item["participation_kind"]): item
                for item in manifest["entries"]}
        for kind in ("team", "individual"):
            corner = rows[("spsocstat:cornerKicks", kind)]
            self.assertTrue(corner["admitted"])
            self.assertEqual(corner["shacl_datatype"], "xsd:string")
            self.assertIn("lexicalization", corner)
            for curie in ("spbkbstat:minutesPlayed", "spamfstat:rushesAttempts"):
                row = rows[(curie, kind)]
                self.assertFalse(row["admitted"])
                self.assertNotIn("shacl_datatype", row)
                self.assertNotIn("lexicalization", row)

    def test_official_source_receipt_matches_every_pinned_byte(self):
        manifest = json.loads((self.data / "official_statistic_admissibility_v1.json").read_text(encoding="utf-8"))
        import hashlib
        for relative, expected in manifest["source_receipt"].items():
            with self.subTest(relative=relative):
                actual = "sha256:" + hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()
                self.assertEqual(actual, expected)

    def test_distance_units_are_the_closed_physical_registry(self):
        registry = json.loads((self.data / "spatial_distance_unit_registry_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [(item["unit_id"], item["metres_per_unit"]) for item in registry["entries"]],
            [("metre", "1.0"), ("yard", "0.9144"),
             ("foot", "0.3048"), ("centimetre", "0.01")],
        )

    def test_runtime_receipt_is_reproducible_and_lists_private_symbols(self):
        target = self.data / "trusted_loader_manifest_v1.json"
        before = target.read_bytes()
        subprocess.run(
            [sys.executable, "tools/iptc/generate_phase1_receipts.py"],
            cwd=str(REPO_ROOT), check=True, timeout=120)
        self.assertEqual(target.read_bytes(), before)
        receipt = json.loads(target.read_text(encoding="utf-8"))
        symbols = {item["symbol"] for item in receipt["private_symbols"]}
        self.assertIn("_build_successor_envelope", symbols)
        self.assertIn("execute_adapter_operation", symbols)

    def test_execution_runtime_contains_no_cache_path(self):
        source = (REPO_ROOT / "tools/iptc/canonical/successor.py").read_text(encoding="utf-8")
        execute_source = inspect.getsource(SUPPORT.canonical_module("successor").execute_adapter_operation)
        for token in ("cache_lookup", "cache_hit", "cache_write", "cache_key"):
            self.assertNotIn(token, execute_source)
        self.assertNotIn("functools.lru_cache", source)


if __name__ == "__main__":
    unittest.main()
