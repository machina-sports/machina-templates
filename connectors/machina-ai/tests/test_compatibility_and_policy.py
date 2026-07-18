import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

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


class RuntimeContractServices:
    """Fake with the real RouterRuntimeServices.delegate signature."""

    def __init__(self):
        self.call = None

    def delegate(self, target_name, request_data=None, command=None):
        self.call = (target_name, request_data, command)
        return {
            "status": True,
            "data": "model",
            "message": "Model loaded.",
            "metadata": {"contract_version": "v1"},
        }


class TestFastCompatibility:
    def test_prompt_delegates_with_runtime_contract_signature(self):
        runtime = RuntimeContractServices()
        result = fast.invoke_prompt({"_runtime": runtime, "timeout": 20})
        assert result["status"] is True
        target_name, request_data, command = runtime.call
        assert target_name == "machina-ai"
        assert request_data["profile"] == "fast"
        assert request_data["timeout"] == 20
        assert "_runtime" not in request_data
        assert command == "invoke_prompt"

    def test_wrapper_execd_without_file_returns_typed_unavailable(self):
        # The production runtime execs connector source without __file__ and,
        # on pre-delegation runtimes, without any injected delegate — the
        # wrapper must return the typed error, not raise NameError.
        source = (FAST_DIR / "machina-ai-fast.py").read_text()
        namespace = {"__builtins__": __builtins__}
        exec(compile(source, "<machina-ai-fast>", "exec"), namespace)
        assert "__file__" not in namespace
        result = namespace["invoke_prompt"]({"prompt": "hi"})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "provider_unavailable"

    def test_wrapper_resolves_injected_machina_router_runtime_global(self):
        module = load_module("machina_ai_fast_injected_runtime", FAST_DIR / "machina-ai-fast.py")
        runtime = RuntimeContractServices()
        module.machina_router_runtime = runtime
        result = module.invoke_prompt({"timeout": 7})
        assert result["status"] is True
        target_name, request_data, command = runtime.call
        assert target_name == "machina-ai"
        assert request_data == {"profile": "fast", "timeout": 7}
        assert command == "invoke_prompt"

    def test_wrapper_falls_back_to_injected_machina_delegate_global(self):
        module = load_module("machina_ai_fast_injected_delegate", FAST_DIR / "machina-ai-fast.py")
        calls = []

        def machina_delegate(target_name, request_data=None, command=None):
            calls.append((target_name, request_data, command))
            return {
                "status": True,
                "data": "model",
                "message": "Model loaded.",
                "metadata": {"contract_version": "v1"},
            }

        module.machina_delegate = machina_delegate
        result = module.invoke_prompt({})
        assert result["status"] is True
        assert calls == [("machina-ai", {"profile": "fast"}, "invoke_prompt")]

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

    def test_fast_manifest_declares_runtime_delegation_allowlist(self):
        document = yaml.safe_load((FAST_DIR / "machina-ai-fast.yml").read_text())
        assert document["connector"]["delegates_to"] == ["machina-ai"]

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
        # Oxylabs udm=2 organic results carry base64 thumbnails, so the
        # workflow must feed them through edit_image's images_base64 input.
        assert 'command: "edit_image"' in workflow
        assert "images_base64" in workflow
        assert "image_paths" not in workflow
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

    FLOW_STYLE_UNSAFE = (
        "workflow: {tasks: [{type: prompt, connector: "
        "{name: machina-ai, command: invoke_prompt, api_key: secret}}]}\n"
    )

    def _hidden_pyyaml_env(self, tmp_path):
        """Environment whose PYTHONPATH shadows PyYAML with an ImportError stub."""
        fake_site = tmp_path / "fake_site"
        (fake_site / "yaml").mkdir(parents=True)
        (fake_site / "yaml" / "__init__.py").write_text('raise ImportError("PyYAML hidden for test")\n')
        env = dict(os.environ)
        env["PYTHONPATH"] = str(fake_site)
        return env

    def test_semantic_pass_catches_flow_style_and_reports_real_lines(self, tmp_path):
        result = self.run_lint(tmp_path, self.FLOW_STYLE_UNSAFE)
        assert result.returncode == 1
        assert "may not set policy/security field 'api_key'" in result.stderr
        assert "workflow.yml:1:" in result.stderr
        assert ":0:" not in result.stderr

    def test_missing_pyyaml_warns_loudly_on_stderr(self, tmp_path):
        path = tmp_path / "workflow.yml"
        path.write_text(self.FLOW_STYLE_UNSAFE)
        result = subprocess.run(
            [sys.executable, str(self.SCRIPT), str(path)],
            text=True,
            capture_output=True,
            env=self._hidden_pyyaml_env(tmp_path),
        )
        # Without PyYAML the flow-style block dodges the line scan (the
        # documented bypass) — the run must at least warn loudly.
        assert result.returncode == 0
        assert "WARNING" in result.stderr
        assert "PyYAML" in result.stderr
        assert "SKIPPED" in result.stderr

    def test_missing_pyyaml_fails_with_require_semantic(self, tmp_path):
        path = tmp_path / "workflow.yml"
        path.write_text("workflow: {}\n")
        result = subprocess.run(
            [sys.executable, str(self.SCRIPT), "--require-semantic", str(path)],
            text=True,
            capture_output=True,
            env=self._hidden_pyyaml_env(tmp_path),
        )
        assert result.returncode == 2
        assert "--require-semantic" in result.stderr

    def test_require_semantic_passes_when_pyyaml_is_available(self, tmp_path):
        path = tmp_path / "workflow.yml"
        path.write_text("workflow: {}\n")
        result = subprocess.run(
            [sys.executable, str(self.SCRIPT), "--require-semantic", str(path)],
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr

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
