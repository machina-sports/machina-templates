import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

CONNECTOR_DIR = Path(__file__).resolve().parents[1]
ROOT = CONNECTOR_DIR.parents[1]
FAST_DIR = CONNECTOR_DIR.parent / "machina-ai-fast"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


router = load_module("machina_ai_policy_tests", CONNECTOR_DIR / "machina-ai.py")
fast = load_module("machina_ai_fast_tests", FAST_DIR / "machina-ai-fast.py")


class TestFastCompatibility:
    def test_prompt_delegates_with_fast_profile(self):
        class Runtime:
            def __init__(self):
                self.call = None

            def delegate(self, connector, command, params):
                self.call = (connector, command, params)
                return {"status": True, "data": "model", "message": "Model loaded.", "metadata": {"contract_version": "v1"}}

        runtime = Runtime()
        result = fast.invoke_prompt({"_runtime": runtime, "timeout": 20})
        assert result["status"] is True
        assert runtime.call[0:2] == ("machina-ai", "invoke_prompt")
        assert runtime.call[2]["profile"] == "fast"
        assert runtime.call[2]["timeout"] == 20

    def test_explicit_profile_is_preserved_for_policy_to_evaluate(self):
        class Runtime:
            def delegate(self, connector, command, params):
                return params

        result = fast.invoke_prompt({"_runtime": Runtime(), "profile": "quality"})
        assert result["profile"] == "quality"

    def test_fake_embedding_returns_typed_unsupported_error(self):
        result = fast.invoke_embedding({})
        assert result["status"] is False
        assert result["data"] is None
        assert result["metadata"]["error_class"] == "unsupported_capability"
        assert result["error"] == result["message"]

    def test_offline_sibling_loader_uses_router_contract(self):
        result = fast.invoke_prompt({})
        assert set(result) >= {"status", "data", "message", "metadata"}
        assert result["metadata"]["contract_version"] == "v1"


class TestManifestAndPackaging:
    def test_single_installable_router_file_and_manifest_parity(self):
        manifest = (CONNECTOR_DIR / "machina-ai.yml").read_text()
        install = (CONNECTOR_DIR / "_install.yml").read_text()
        assert 'filename: "machina-ai.py"' in manifest
        assert 'path: "machina-ai.yml"' in install
        assert "router/" not in install
        for command in router.COMMANDS:
            assert f'value: "{command}"' in manifest
            assert callable(getattr(router, command))

    def test_fast_manifest_declares_only_real_compatibility_commands(self):
        manifest = (FAST_DIR / "machina-ai-fast.yml").read_text()
        assert 'value: "invoke_prompt"' in manifest
        assert 'value: "invoke_embedding"' in manifest
        assert "invoke_chat" not in manifest

    def test_openai_connector_identity_is_unique(self):
        openai_manifest = (ROOT / "connectors" / "openai" / "openai.yml").read_text()
        google_manifest = (ROOT / "connectors" / "google-genai" / "google-genai.yml").read_text()
        assert 'name: "openai"' in openai_manifest
        assert "name: google-genai" in google_manifest

    def test_nvidia_compatibility_contract_is_preserved(self):
        manifest = (ROOT / "connectors" / "nvidia-nim" / "nvidia-nim.yml").read_text()
        implementation = (ROOT / "connectors" / "nvidia-nim" / "nvidia-nim.py").read_text()
        for command in ("health", "list_models", "invoke_chat", "completion_receipt"):
            assert f'value: "{command}"' in manifest
            assert f"def {command}(" in implementation
        assert "NVIDIA_NIM_CHAT_BASE_URL" in implementation
        assert "NVIDIA_NIM_CHAT_ALLOWED_MODELS" in implementation

    def test_google_edit_image_alias_is_declared_and_callable(self):
        manifest = (ROOT / "connectors" / "google-genai" / "google-genai.yml").read_text()
        implementation = (ROOT / "connectors" / "google-genai" / "google-genai.py").read_text()
        workflow = (ROOT / "connectors" / "oxylabs" / "searching.yml").read_text()
        assert "value: edit_image" in manifest
        assert "def edit_image(" in implementation
        assert 'command: "invoke_image"' in workflow
        assert "gpt-image-1" not in workflow


class TestPolicyLint:
    SCRIPT = ROOT / "scripts" / "check-machina-ai-policy.py"

    def run_lint(self, tmp_path, content):
        path = tmp_path / "workflow.yml"
        path.write_text(content)
        return subprocess.run([sys.executable, str(self.SCRIPT), str(path)], text=True, capture_output=True)

    def test_safe_vertex_router_block_passes(self, tmp_path):
        result = self.run_lint(tmp_path, """
workflow:
  tasks:
    - type: prompt
      connector:
        name: machina-ai
        command: invoke_prompt
        provider: vertex_ai
        model: gemini-2.5-flash
        profile: balanced
      inputs:
        prompt: hello
""")
        assert result.returncode == 0, result.stderr

    @pytest.mark.parametrize(
        "line,expected",
        [
            ("provider: groq", "provider must be vertex_ai"),
            ("profile: fast", "profile 'fast' is not allowed"),
            ("base_url: https://evil.example/v1", "may not set policy/security field 'base_url'"),
            ("api_key: secret", "may not set policy/security field 'api_key'"),
            ("model: llama-3", "not a repository-approved Vertex model"),
            ("command: imaginary", "not in the v1 inventory"),
        ],
    )
    def test_unsafe_connector_fields_fail(self, tmp_path, line, expected):
        command_line = "" if line.startswith("command:") else "command: invoke_prompt"
        content = f"""
workflow:
  tasks:
    - type: prompt
      connector:
        name: machina-ai
        {command_line}
        {line}
"""
        result = self.run_lint(tmp_path, content)
        assert result.returncode == 1
        assert expected in result.stderr

    def test_routing_field_under_task_inputs_fails(self, tmp_path):
        result = self.run_lint(tmp_path, """
workflow:
  tasks:
    - type: prompt
      connector:
        name: machina-ai
        command: invoke_prompt
      inputs:
        endpoint: https://evil.example/v1
        prompt: hello
""")
        assert result.returncode == 1
        assert "task inputs may not set routing/security field 'endpoint'" in result.stderr

    def test_facade_context_variable_credential_fails(self, tmp_path):
        result = self.run_lint(tmp_path, """
workflow:
  context-variables:
    machina-ai:
      api_key: secret
  tasks: []
""")
        assert result.returncode == 1
        assert "context variables may not set 'api_key'" in result.stderr

    def test_repository_policy_lint_passes(self):
        result = subprocess.run([str(ROOT / "scripts" / "check-no-openai.sh"), "all"], cwd=ROOT, text=True, capture_output=True)
        assert result.returncode == 0, result.stderr


class TestInventory:
    def test_inventory_has_no_unknown_commands_or_identity_collisions(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check-ai-command-inventory.py"), "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["unknown"] == []
        assert payload["identity_collisions"] == {}

    def test_inventory_locks_down_nim_and_rest_dispatch_strings(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check-ai-command-inventory.py"), "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        mappings = {(item["connector"], item["command"]): item["mapping"] for item in json.loads(result.stdout)["declared"]}
        assert mappings[("nvidia-nim", "invoke_chat")] == "invoke_prompt(factory)"
        assert mappings[("nvidia-nim", "completion_receipt")] == "invoke_chat(execute)"
        assert mappings[("grok", "post-responses")] == "invoke_chat(tools-policy)"
        assert mappings[("byteplus-modelark", "get-contents/generations/tasks/{id}")] == "invoke_video(get_task)"
