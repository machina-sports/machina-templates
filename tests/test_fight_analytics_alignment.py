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

    def test_reduced_precision_with_split_time_and_offset(self):
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

    def test_exact_precision_with_start_time(self):
        payload = copy.deepcopy(self.raw_payload)
        # Add explicit exact startsAt
        payload["event"]["startTime"] = "2022-11-12T16:00:00-05:00"
        
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
        payload["event"]["startTime"] = "2022-11-12T16:00:00-05:00"
        
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
