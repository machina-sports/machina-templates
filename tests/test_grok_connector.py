"""Offline contract tests for the Grok REST connector."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
CONNECTOR_DIR = REPO_ROOT / "connectors" / "grok"
DESCRIPTOR_PATH = CONNECTOR_DIR / "grok.yml"
INSTALL_PATH = CONNECTOR_DIR / "_install.yml"
OPENAPI_PATH = CONNECTOR_DIR / "grok.json"
WORKFLOW_PATHS = (
    CONNECTOR_DIR / "test.yml",
    REPO_ROOT / "agent-templates" / "template-newsletter" / "workflows" / "xai-search.yml",
    REPO_ROOT
    / "agent-templates"
    / "world-cup-intelligence"
    / "workflows"
    / "worldcup-fan-sentiment-context.yml",
    REPO_ROOT
    / "agent-templates"
    / "world-cup-intelligence"
    / "workflows"
    / "worldcup-fan-pulse.yml",
)


def read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


class TestGrokConnector(unittest.TestCase):
    def setUp(self):
        with OPENAPI_PATH.open(encoding="utf-8") as stream:
            self.document = json.load(stream)

    def test_import_manifests_register_the_rest_connector_and_smoke_workflow(self):
        self.assertEqual(
            read_yaml(DESCRIPTOR_PATH)["connector"],
            {
                "name": "grok",
                "description": (
                    "This connector is the xAI Grok API connector for chat "
                    "completions and embeddings."
                ),
                "filename": "grok.json",
                "filetype": "restapi",
            },
        )
        self.assertEqual(
            read_yaml(INSTALL_PATH)["setup"]["value"],
            "connectors/grok",
        )
        self.assertEqual(
            read_yaml(INSTALL_PATH)["datasets"],
            [
                {"type": "connector", "path": "grok.yml"},
                {"type": "workflow", "path": "test.yml"},
            ],
        )

    def test_uses_runtime_bearer_security_contract_for_every_operation(self):
        self.assertNotIn("securitySchemes", self.document)
        self.assertEqual(self.document["security"], [{"authorization": []}])
        self.assertEqual(
            self.document["components"]["securitySchemes"],
            {
                "authorization": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "Authorization",
                    "description": "Authorization header value supplied by the runtime context",
                }
            },
        )
        for path, path_item in self.document["paths"].items():
            with self.subTest(path=path):
                self.assertEqual(path_item["post"]["security"], [{"authorization": []}])

    def test_workflows_map_the_vault_secret_to_the_runtime_bearer_key(self):
        expected = {"authorization": "$MACHINA_CONTEXT_VARIABLE_GROK_API_KEY"}
        for path in WORKFLOW_PATHS:
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                workflow = read_yaml(path)["workflow"]
                self.assertEqual(workflow["context-variables"]["grok"], expected)

    def test_responses_operation_preserves_server_side_tools(self):
        request_properties = self.document["paths"]["/responses"]["post"][
            "requestBody"
        ]["content"]["application/json"]["schema"]["properties"]
        self.assertEqual(request_properties["tools"]["type"], "array")
        self.assertEqual(
            request_properties["tools"]["items"]["properties"]["type"]["description"],
            "Server-side tool type: web_search, x_search, code_interpreter",
        )

        response_workflows = WORKFLOW_PATHS[2:]
        for path in response_workflows:
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                workflow = read_yaml(path)["workflow"]
                task = next(
                    task
                    for task in workflow["tasks"]
                    if task.get("connector", {}).get("command") == "post-responses"
                )
                body = task["inputs"]["body"]
                self.assertIn('{"type": "x_search"}', body)
                self.assertIn('{"type": "web_search"}', body)


if __name__ == "__main__":
    unittest.main()
