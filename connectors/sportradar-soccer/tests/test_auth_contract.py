"""Guard the public Soccer v4 auth contract without using real credentials."""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SoccerAuthenticationContract(unittest.TestCase):
    def test_every_endpoint_uses_header_auth_and_existing_context_binding(self):
        schema = json.loads((ROOT / "sportradar-soccer.json").read_text())
        # Machina resolves a security scheme from the equally named context
        # variable. Keep api_key so existing workflows need no secret migration.
        self.assertEqual(schema["components"]["securitySchemes"], {
            "api_key": {"type": "apiKey", "in": "header", "name": "x-api-key"}
        })
        methods = {"get", "post", "put", "patch", "delete"}
        for path, item in schema["paths"].items():
            for method, operation in item.items():
                if method not in methods:
                    continue
                with self.subTest(path=path, method=method):
                    self.assertEqual(operation["security"], [{"api_key": []}])
                    for parameter in item.get("parameters", []) + operation.get("parameters", []):
                        self.assertNotIn(parameter["name"], {"api_key", "x-api-key"},
                                         "Credentials must only come from the security binding")

    def test_schedule_and_summary_remain_available(self):
        schema = json.loads((ROOT / "sportradar-soccer.json").read_text())
        for path, identifier in [
            ("/seasons/{season_id}/schedules.json", "season_id"),
            ("/sport_events/{event_code}/{data_type}", "event_code"),
        ]:
            operation = schema["paths"][path]["get"]
            self.assertTrue(any(p["name"] == identifier and p["in"] == "path"
                                for p in operation["parameters"]))
        self.assertIn("/competitions.json", schema["paths"])


if __name__ == "__main__":
    unittest.main()
