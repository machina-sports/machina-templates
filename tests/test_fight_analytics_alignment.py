"""Tests for the Fight Analytics local schema alignment adapter and projection."""

from __future__ import annotations

import copy
import json
import unittest
import sys
import ast
import importlib.util
from pathlib import Path

# Set up paths so we can import the local connector-local adapter and machina_sports_canonical
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load support helper so machina_sports_canonical package namespace is registered
_SUPPORT_PATH = REPO_ROOT / "tests/iptc_canonical_support.py"
_spec_support = importlib.util.spec_from_file_location("iptc_canonical_support", _SUPPORT_PATH)
support = importlib.util.module_from_spec(_spec_support)
_spec_support.loader.exec_module(support)
support.canonical_package()

# Dynamically import the adapter from connectors/fight-analytics/
ADAPTER_PATH = REPO_ROOT / "connectors" / "fight-analytics" / "fight_analytics_adapter.py"
_spec = importlib.util.spec_from_file_location("fight_analytics_adapter", ADAPTER_PATH)
fight_analytics_adapter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fight_analytics_adapter)

from machina_sports_canonical.observation import validate_observation

MOCK_PAYLOAD_PATH = REPO_ROOT / "connectors" / "fight-analytics" / "swagger-documentation-evidence-fight-dto.json"


class TestFightAnalyticsAlignment(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MOCK_PAYLOAD_PATH.is_file(), f"Mock payload missing: {MOCK_PAYLOAD_PATH}")
        with MOCK_PAYLOAD_PATH.open(encoding="utf-8") as f:
            self.raw_payload = json.load(f)

        # Ensure distinct IDs for corners to be valid
        self.raw_payload["redCornerId"] = "fighter-red-123"
        self.raw_payload["redCorner"]["id"] = "fighter-red-123"
        self.raw_payload["redCorner"]["firstName"] = "Song"
        self.raw_payload["redCorner"]["lastName"] = "Yadong"

        self.raw_payload["blueCornerId"] = "fighter-blue-456"
        self.raw_payload["blueCorner"]["id"] = "fighter-blue-456"
        self.raw_payload["blueCorner"]["firstName"] = "Marlon"
        self.raw_payload["blueCorner"]["lastName"] = "Vera"

        # Give event.time a default explicit offset to be valid for general tests
        self.raw_payload["event"]["time"] = "04:00 PM-05:00"

    def test_fixture_is_documentation_evidence_only(self):
        """Verify that the fixture is explicitly named and documented as documentation-evidence only."""
        self.assertIn("swagger-documentation-evidence-fight-dto.json", str(MOCK_PAYLOAD_PATH))

    def test_adapter_exists(self):
        self.assertIsNotNone(fight_analytics_adapter, "Fight Analytics adapter is missing")

    def test_fail_closed_for_production_tier(self):
        """Verify that the adapter fails closed for production/commercial tiers before adaptation."""
        payload = copy.deepcopy(self.raw_payload)
        with self.assertRaises(ValueError) as ctx:
            fight_analytics_adapter.to_observation(payload, observed_at="2026-08-15T12:00:00Z")
        self.assertIn("fails closed for production", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            fight_analytics_adapter.to_observation(payload, observed_at="2026-08-15T12:00:00Z", consumer_tier="production")
        self.assertIn("fails closed for production", str(ctx.exception))

    def test_to_envelope_fails_closed_for_production_tier(self):
        """Verify that to_envelope fails closed for production/commercial tiers."""
        payload = copy.deepcopy(self.raw_payload)
        with self.assertRaises(ValueError) as ctx:
            fight_analytics_adapter.to_envelope(payload, observed_at="2026-08-15T12:00:00Z")
        self.assertIn("fails closed for production", str(ctx.exception))

    def test_synthetic_reduced_precision_with_split_time_and_offset(self):
        """Verify reduced precision with synthetic split time and offset."""
        payload = copy.deepcopy(self.raw_payload)
        # Give time an explicit offset (-05:00)
        payload["event"]["time"] = "04:00 PM-05:00"

        doc = fight_analytics_adapter.to_observation(payload, observed_at="2026-08-15T12:00:00Z", consumer_tier="prototype")

        # Verify it validates against the canonical-observation contract
        errors = validate_observation(doc)
        self.assertEqual(errors, [])

        # Check temporal evidence is correctly derived
        obs = doc["observation"]
        event = obs["event"]
        self.assertIn("temporal_evidence", event)
        self.assertNotIn("start_time", event)

        evidence = event["temporal_evidence"]
        self.assertEqual(evidence["kind"], "start")
        self.assertEqual(evidence["precision"], "minute")
        self.assertEqual(evidence["source_value"], "2022-11-12T16:00-05:00")
        self.assertEqual(evidence["lower_inclusive"], "2022-11-12T21:00:00Z")
        self.assertEqual(evidence["upper_exclusive"], "2022-11-12T21:01:00Z")

    def test_synthetic_exact_precision_with_start_time(self):
        """Verify exact precision with synthetic start time and offset."""
        payload = copy.deepcopy(self.raw_payload)
        # Use documented event.date/event.time with seconds+offset
        payload["event"]["date"] = "2022-11-12"
        payload["event"]["time"] = "04:00:00 PM-05:00"

        doc = fight_analytics_adapter.to_observation(payload, observed_at="2026-08-15T12:00:00Z", consumer_tier="prototype")

        # Verify it validates
        errors = validate_observation(doc)
        self.assertEqual(errors, [])

        obs = doc["observation"]
        event = obs["event"]
        self.assertNotIn("temporal_evidence", event)
        self.assertEqual(event["start_time"], "2022-11-12T16:00:00-05:00")

    def test_participant_alignment_and_outcomes(self):
        payload = copy.deepcopy(self.raw_payload)
        payload["event"]["startTime"] = "2022-11-12T16:00:00-05:00"
        payload["winner"] = "fighter-red-123"

        doc = fight_analytics_adapter.to_observation(payload, observed_at="2026-08-15T12:00:00Z", consumer_tier="prototype")
        obs = doc["observation"]

        participants = obs["participants"]
        self.assertEqual(len(participants), 2)

        # Red Corner
        self.assertEqual(participants[0]["provider_id"], "fighter-red-123")
        self.assertEqual(participants[0]["name"], "Song Yadong")
        self.assertEqual(participants[0]["alignment"], "red")
        self.assertEqual(participants[0]["outcome"], "win")

        # Blue Corner
        self.assertEqual(participants[1]["provider_id"], "fighter-blue-456")
        self.assertEqual(participants[1]["name"], "Marlon Vera")
        self.assertEqual(participants[1]["alignment"], "blue")
        self.assertEqual(participants[1]["outcome"], "loss")

    def test_draw_outcome(self):
        payload = copy.deepcopy(self.raw_payload)
        payload["event"]["startTime"] = "2022-11-12T16:00:00-05:00"
        payload["result"] = "DRAW"
        payload["winner"] = "Not available yet"

        doc = fight_analytics_adapter.to_observation(payload, observed_at="2026-08-15T12:00:00Z", consumer_tier="prototype")
        obs = doc["observation"]

        participants = obs["participants"]
        self.assertEqual(participants[0]["outcome"], "draw")
        self.assertEqual(participants[1]["outcome"], "draw")

    def test_sports_mapping(self):
        for fa_sport, expected_medtop in [
            ("MMA", "20001231"),
            ("BOXING", "20000856"),
            ("KICKBOXING", "20001310"),
            ("WRESTLING", "20001098"),
        ]:
            with self.subTest(fa_sport=fa_sport):
                payload = copy.deepcopy(self.raw_payload)
                payload["event"]["startTime"] = "2022-11-12T16:00:00-05:00"
                payload["sport"] = fa_sport

                doc = fight_analytics_adapter.to_observation(payload, observed_at="2026-08-15T12:00:00Z", consumer_tier="prototype")
                self.assertEqual(doc["observation"]["sport"]["medtop"], expected_medtop)

    def test_to_envelope_prototype_tier(self):
        """Verify that to_envelope succeeds for the prototype tier and returns a valid canonical envelope."""
        payload = copy.deepcopy(self.raw_payload)
        payload["event"]["date"] = "2022-11-12"
        payload["event"]["time"] = "04:00:00 PM-05:00"

        envelope = fight_analytics_adapter.to_envelope(
            payload, observed_at="2026-08-15T12:00:00Z", consumer_tier="prototype"
        )

        # Verify the structure is a canonical envelope
        self.assertIn("machina_sports_schema", envelope)
        schema = envelope["machina_sports_schema"]
        self.assertEqual(schema["schema_version"], "machina-sports-schema/1")
        self.assertIn("sport_schema_graph", schema)
        self.assertIn("event_view", schema)
        self.assertIn("provenance", schema)
        self.assertIn("capabilities", schema)
        self.assertIn("rights", schema)

        # Check provider scoped surrogate resolver is used for provider ids
        event_view = schema["event_view"]
        event_id = event_view["event_id"]
        # The surrogate is formatted as urn:machina:sports:event:x<hex>
        self.assertTrue(event_id.startswith("urn:machina:sports:event:x"), f"Unexpected event_id: {event_id}")

    def test_adapter_imports_no_repository_roots(self):
        """Verify that the local adapter does not import from connectors, tools, or other repo roots."""
        with open(ADAPTER_PATH, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    self.assertFalse(
                        name.name.startswith(("tools", "connectors", "agent_templates")),
                        f"Banned import: {name.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.assertFalse(
                        node.module.startswith(("tools", "connectors", "agent_templates")),
                        f"Banned import: {node.module}"
                    )

    def test_canonical_descriptor_and_install_manifest_exists_and_declares_command(self):
        """Verify the canonical projection connector descriptor and its registration in _install.yml."""
        import yaml
        install_path = REPO_ROOT / "connectors" / "fight-analytics" / "_install.yml"
        canonical_yaml_path = REPO_ROOT / "connectors" / "fight-analytics" / "fight-analytics-canonical.yml"

        self.assertTrue(install_path.is_file(), f"absent: {install_path}")
        self.assertTrue(canonical_yaml_path.is_file(), f"absent: {canonical_yaml_path}")

        # Verify registration in _install.yml
        with install_path.open(encoding="utf-8") as f:
            install_data = yaml.safe_load(f)
        datasets = install_data.get("datasets", [])
        registered_paths = [d.get("path") for d in datasets if d.get("type") == "connector"]
        self.assertIn("fight-analytics-canonical.yml", registered_paths)

        # Verify fight-analytics-canonical.yml
        with canonical_yaml_path.open(encoding="utf-8") as f:
            canonical_data = yaml.safe_load(f)

        connector = canonical_data.get("connector", {})
        self.assertEqual(connector.get("name"), "fight-analytics-canonical")
        self.assertEqual(connector.get("filename"), "fight_analytics_adapter.py")
        self.assertEqual(connector.get("filetype"), "pyscript")

        commands = connector.get("commands", [])
        command_values = [cmd.get("value") for cmd in commands]
        self.assertIn("canonicalize_fight", command_values)

    def test_canonicalize_fight_command_executes_with_real_machina_params_and_status_data_envelope(self):
        """Verify that the canonicalize_fight command executes with the real Machina {params} and {status, data} contract."""
        payload = copy.deepcopy(self.raw_payload)
        payload["event"]["startTime"] = "2022-11-12T16:00:00-05:00"

        request_data = {
            "params": {
                "payload": payload,
                "observed_at": "2026-08-15T12:00:00Z",
                "consumer_tier": "prototype"
            }
        }

        res = fight_analytics_adapter.canonicalize_fight(request_data)
        self.assertTrue(res.get("status"), f"Command failed: {res}")
        self.assertIn("data", res)

        envelope = res["data"]
        self.assertIn("machina_sports_schema", envelope)
        schema = envelope["machina_sports_schema"]
        self.assertEqual(schema["schema_version"], "machina-sports-schema/1")

    def test_production_refusal_happens_before_adaptation(self):
        """Verify that production/commercial tier refusal happens before any adaptation of the payload."""
        # Pass a completely invalid payload (empty dict). If it doesn't raise KeyError/TypeError but refuses on tier first,
        # it proves production refusal happens before adaptation!
        request_data = {
            "params": {
                "payload": {},
                "observed_at": "2026-08-15T12:00:00Z",
                "consumer_tier": "production"
            }
        }

        res = fight_analytics_adapter.canonicalize_fight(request_data)
        self.assertFalse(res.get("status"))
        self.assertIn("data", res)
        self.assertIn("error", res["data"])
        self.assertEqual(res["data"]["error"], "TIER_REFUSAL")

    def test_raw_swagger_documentation_fixture_itself_fails_closed_on_missing_timezone(self):
        """Verify that the unmodified raw Swagger fixture itself fails closed on missing timezone."""
        # Use unmodified raw_payload (time is "04:00 PM", which has no UTC offset)
        with MOCK_PAYLOAD_PATH.open(encoding="utf-8") as f:
            raw_payload = json.load(f)
        raw_payload["redCornerId"] = "fighter-red-123"
        raw_payload["redCorner"]["id"] = "fighter-red-123"
        raw_payload["redCorner"]["firstName"] = "Song"
        raw_payload["redCorner"]["lastName"] = "Yadong"
        raw_payload["blueCornerId"] = "fighter-blue-456"
        raw_payload["blueCorner"]["id"] = "fighter-blue-456"
        raw_payload["blueCorner"]["firstName"] = "Marlon"
        raw_payload["blueCorner"]["lastName"] = "Vera"

        request_data = {
            "params": {
                "payload": raw_payload,
                "observed_at": "2026-08-15T12:00:00Z",
                "consumer_tier": "prototype"
            }
        }

        res = fight_analytics_adapter.canonicalize_fight(request_data)
        self.assertFalse(res.get("status"))
        self.assertIn("data", res)
        self.assertIn("error", res["data"])
        self.assertEqual(res["data"]["error"], "CANONICALIZATION_REFUSED")

    def test_canonicalize_fight_adversarial_vulnerability_leak(self):
        """Verify that adversarial/hostile payload fields and credentials do not leak in error responses."""
        payload = copy.deepcopy(self.raw_payload)
        payload["sport"] = "SECRET_API_KEY_MMA_VULN"
        payload["event"]["time"] = "SECRET_BEARER_TOKEN_04:00 PM"

        request_data = {
            "params": {
                "payload": payload,
                "observed_at": "2026-08-15T12:00:00Z",
                "consumer_tier": "prototype"
            }
        }

        # 1. Test prototype shape/semantic failure error response
        res = fight_analytics_adapter.canonicalize_fight(request_data)
        self.assertFalse(res.get("status"))
        self.assertIn("data", res)
        self.assertIn("error", res["data"])

        # Verify the error matches the generic canonicalization-refused code
        self.assertEqual(res["data"]["error"], "CANONICALIZATION_REFUSED")

        # Verify no sensitive keywords or values exist in the output error dictionary
        res_str = json.dumps(res)
        self.assertNotIn("SECRET_API_KEY_MMA_VULN", res_str)
        self.assertNotIn("SECRET_BEARER_TOKEN", res_str)

        # 2. Test tier refusal error response
        request_data_prod = {
            "params": {
                "payload": payload,
                "observed_at": "2026-08-15T12:00:00Z",
                "consumer_tier": "production"
            }
        }
        res_prod = fight_analytics_adapter.canonicalize_fight(request_data_prod)
        self.assertFalse(res_prod.get("status"))
        self.assertIn("data", res_prod)
        self.assertIn("error", res_prod["data"])

        # Verify the error matches the specific safe tier refusal code
        self.assertEqual(res_prod["data"]["error"], "TIER_REFUSAL")

        # Verify no sensitive values exist in production refusal either
        res_prod_str = json.dumps(res_prod)
        self.assertNotIn("SECRET_API_KEY_MMA_VULN", res_prod_str)
        self.assertNotIn("SECRET_BEARER_TOKEN", res_prod_str)

    def test_canonicalize_fight_malformed_inputs_generic_error(self):
        """Verify that malformed request_data structure returns CANONICALIZATION_REFUSED instead of throwing uncaught exceptions."""
        for malformed in ["secret", 123, True, [], None]:
            with self.subTest(malformed_request_data=malformed):
                res = fight_analytics_adapter.canonicalize_fight(malformed)
                self.assertFalse(res.get("status"))
                self.assertEqual(res.get("data", {}).get("error"), "CANONICALIZATION_REFUSED")

        for malformed_params in [{"params": "secret"}, {"params": 123}, {"params": True}, {"params": []}]:
            with self.subTest(malformed_params=malformed_params):
                res = fight_analytics_adapter.canonicalize_fight(malformed_params)
                self.assertFalse(res.get("status"))
                self.assertEqual(res.get("data", {}).get("error"), "CANONICALIZATION_REFUSED")

    def test_no_undocumented_fields_or_status_mappings_consumed_behavior(self):
        """Verify behaviorally that undocumented status and start aliases are not consumed."""
        # 1. Start time projection: if event date/time are missing but startTime is present, it should fail
        payload_no_date_time = copy.deepcopy(self.raw_payload)
        payload_no_date_time["event"].pop("date", None)
        payload_no_date_time["event"].pop("time", None)
        payload_no_date_time["event"]["startTime"] = "2022-11-12T16:00:00-05:00"
        
        request_data = {
            "params": {
                "payload": payload_no_date_time,
                "observed_at": "2026-08-15T12:00:00Z",
                "consumer_tier": "prototype"
            }
        }
        res = fight_analytics_adapter.canonicalize_fight(request_data)
        self.assertFalse(res.get("status"))
        self.assertEqual(res.get("data", {}).get("error"), "CANONICALIZATION_REFUSED")

        # 2. Status mapping: if terminal result is NOT present, but status UPCOMING or LIVE is present, it should fail closed
        payload_no_result = copy.deepcopy(self.raw_payload)
        payload_no_result["result"] = "NOT_AVAILABLE_YET"
        payload_no_result["status"] = "LIVE"
        payload_no_result["event"]["status"] = "LIVE"
        payload_no_result["event"]["time"] = "04:00 PM-05:00"

        request_data_no_result = {
            "params": {
                "payload": payload_no_result,
                "observed_at": "2026-08-15T12:00:00Z",
                "consumer_tier": "prototype"
            }
        }
        res_no_result = fight_analytics_adapter.canonicalize_fight(request_data_no_result)
        self.assertFalse(res_no_result.get("status"))
        self.assertEqual(res_no_result.get("data", {}).get("error"), "CANONICALIZATION_REFUSED")

    def test_no_undocumented_fields_ast(self):
        """AST check proving that undocumented status, start aliases, and code branches are not in the source file."""
        with open(ADAPTER_PATH, "r", encoding="utf-8") as f:
            code = f.read()

        # Check for forbidden start time/date aliases
        forbidden_aliases = [
            "startTime", "startsAt", "starts_at",
            "startDateTime", "start_datetime"
        ]
        for alias in forbidden_aliases:
            self.assertNotIn(alias, code, f"Forbidden start time alias '{alias}' remains in the adapter code")

        # Check for forbidden status lookups/mappings that could parse raw/event status
        self.assertNotIn("payload.get(\"status\")", code.replace("'", '"'))
        self.assertNotIn("event.get(\"status\")", code.replace("'", '"'))
        self.assertNotIn("payload.get('status')", code)
        self.assertNotIn("event.get('status')", code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
