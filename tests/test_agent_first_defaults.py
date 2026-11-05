"""Regressions for agent-first template defaults.

Run from the repository root:

    python3 -m pytest tests/test_agent_first_defaults.py -q
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_SKILL = REPO_ROOT / "skills/manifest-generator"
COPILOT = REPO_ROOT / "agent-templates/machina-copilot"

# First segments allowed in multi-word template prefixes: vendors, public
# templates and platform names only — never a named customer.
GENERIC_PREFIX_HEADS = {
    "api", "bundesliga", "byteplus", "daily", "event", "google", "machina",
    "personalized", "sportradar", "sports", "voice",
}


def _load_extractor():
    path = MANIFEST_SKILL / "connectors/manifest-extractor.py"
    spec = importlib.util.spec_from_file_location("manifest_extractor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest_docs():
    names = ("SKILL.md", "skill.yml", "_install.yml")
    return {name: (MANIFEST_SKILL / name).read_text() for name in names}


# --- manifest-generator: generic customer-facing copy -----------------------

@pytest.mark.parametrize("name", ["SKILL.md", "skill.yml", "_install.yml"])
def test_manifest_docs_have_no_internal_history(name):
    text = _manifest_docs()[name]
    lowered = text.lower()
    for term in ("sprint", "cleanup", "roadmap"):
        assert term not in lowered, f"{name} mentions internal {term!r}"
    public_names = {"machina-templates", "agent-templates", "special-templates"}
    other_repos = set(re.findall(r"\b[\w]+-templates\b", text)) - public_names
    assert not other_repos, f"{name} references other template repos: {other_repos}"


def test_manifest_docs_describe_dependency_inventory_for_project_health():
    combined = " ".join(_manifest_docs().values()).lower()
    assert "project health" in combined
    assert "deterministic" in combined
    assert "dependenc" in combined
    assert re.search(r"optional[^.\n]*(llm|model)[^.\n]*enrich", combined)


def test_skill_yml_description_is_generic():
    skill = yaml.safe_load((MANIFEST_SKILL / "skill.yml").read_text())["skill"]
    description = skill["description"].lower()
    assert "project health" in description
    assert "manifest" in description


# --- manifest-generator: template prefix heuristic ---------------------------

@pytest.mark.parametrize(
    ("workflow_name", "expected"),
    [
        ("api-football-fixtures-sync", "api-football"),
        ("google-genai-test-credentials", "google-genai"),
        ("machina-ai-fast-invoke", "machina-ai-fast"),
        ("machina-ai-invoke", "machina-ai"),
        ("sportradar-soccer-update", "sportradar-soccer"),
        ("acme-coverage-daily-run", "acme"),
        ("acme-assistant-respond", "acme"),
        ("standalone", "standalone"),
    ],
)
def test_infer_template_prefix(workflow_name, expected):
    assert _load_extractor()._infer_template_prefix(workflow_name) == expected


def test_multi_word_prefixes_are_generic():
    source = (MANIFEST_SKILL / "connectors/manifest-extractor.py").read_text()
    block = re.search(r"MULTI_WORD_PREFIXES = \{(.*?)\n    \}", source, re.S)
    assert block, "MULTI_WORD_PREFIXES block not found"
    heads = set(re.findall(r'\(\s*"([a-z0-9]+)"', block.group(1)))
    assert heads, "no prefixes parsed"
    assert heads <= GENERIC_PREFIX_HEADS, f"non-generic prefixes: {heads - GENERIC_PREFIX_HEADS}"


# --- machina-copilot: direct Vertex AI model defaults -------------------------

COPILOT_MODEL = "gemini-3.8-flash"


@pytest.mark.parametrize("workflow", ["copilot-reasoning.yml", "copilot-response.yml"])
def test_copilot_prompt_task_uses_flash_on_vertex(workflow):
    doc = yaml.safe_load((COPILOT / "workflows" / workflow).read_text())["workflow"]
    prompts = [t for t in doc["tasks"] if t.get("type") == "prompt"]
    assert len(prompts) == 1
    connector = prompts[0]["connector"]
    assert connector["name"] == "google-genai"
    assert connector["model"] == COPILOT_MODEL
    assert connector["provider"] == "vertex_ai"
    assert connector["location"] == "global"
    assert doc["context-variables"]["google-genai"] == {
        "credential": "$TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL",
        "project_id": "$TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID",
    }


def test_copilot_install_docs_match_model_family():
    text = (COPILOT / "_install.yml").read_text()
    assert COPILOT_MODEL in text
    assert "gemini-2.5" not in text


# --- machina-copilot: response prompt guard -----------------------------------

def _response_instruction():
    doc = yaml.safe_load((COPILOT / "prompts/copilot-response.yml").read_text())
    prompt = next(p for p in doc["prompts"] if p["name"] == "copilot-response-prompt")
    return " ".join(prompt["instruction"].split()).lower()


def test_response_prompt_preserves_clarification():
    instruction = _response_instruction()
    assert re.search(r"preserve[^.]*clarif", instruction)


def test_response_prompt_forbids_unverified_tool_claims():
    instruction = _response_instruction()
    assert re.search(r"never (claim|assert|say|state)[^.]*tool[^.]*(ran|run|executed)", instruction)
    assert re.search(r"success[^.]*tool (evidence|output)|tool (evidence|output)[^.]*success", instruction)
