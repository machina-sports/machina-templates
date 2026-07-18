#!/usr/bin/env python3
"""Structural lint for committed machina-ai workflow connector blocks.

The repository may use the provider-independent facade only when the workflow
cannot redirect it away from the repository's Vertex-default policy.  Provider
adapters remain implementation details inside connectors/machina-ai.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only where PyYAML is absent
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_PROFILES = {"", "default", "balanced", "quality", "long_context"}
ALLOWED_PROVIDERS = {"", "vertex_ai"}
ALLOWED_COMMANDS = {
    "invoke_prompt",
    "invoke_chat",
    "completion_receipt",
    "invoke_embedding",
    "embed_query",
    "embed_documents",
    "list_models",
    "health",
    "invoke_search",
    "invoke_image",
    "generate_image",
    "edit_image",
    "invoke_video",
    "transcribe_audio_to_text",
    "invoke_transcribe",
    "invoke_tts",
    "get_text_to_speech",
    "list_voices",
    "get_voices",
    "invoke_clone_instant_voice",
    "invoke_train_pro_voice",
    "invoke_synthesize_custom_voice",
    "invoke_music",
}
FORBIDDEN_KEYS = {
    "api_key",
    "credential",
    "base_url",
    "endpoint",
    "azure_endpoint",
    "deployment",
    "azure_deployment",
    "deployment_name",
    "fallback",
    "fallbacks",
    "remap",
    "remaps",
    "allowed_models",
    "allowed_providers",
}
INPUT_ROUTING_KEYS = FORBIDDEN_KEYS | {"provider", "profile", "model", "model_name"}
EXEMPT_PREFIXES = (
    "connectors/machina-ai/machina-ai.yml",
    "connectors/openai/",
    "scripts/",
    ".githooks/",
    ".github/workflows/lint-no-openai.yml",
)


def scalar(value: str) -> str:
    value = value.strip()
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.strip()


def key_value(line: str):
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or ":" not in stripped:
        return None, None
    key, value = stripped.split(":", 1)
    key = key.lstrip("- ").strip().strip("'\"")
    return key, scalar(value)


def connector_blocks(lines):
    index = 0
    while index < len(lines):
        line = lines[index]
        key, _ = key_value(line)
        if key != "connector":
            index += 1
            continue
        indent = len(line) - len(line.lstrip())
        block = []
        cursor = index + 1
        while cursor < len(lines):
            current = lines[cursor]
            if current.strip() and (len(current) - len(current.lstrip())) <= indent:
                break
            block.append((cursor + 1, current))
            cursor += 1
        yield index + 1, block
        index = cursor


def _validate_router_connector(connector, errors, line=0):
    provider = str(connector.get("provider") or "")
    profile = str(connector.get("profile") or "")
    command = str(connector.get("command") or "")
    model = str(connector.get("model") or connector.get("model_name") or "")
    if provider not in ALLOWED_PROVIDERS:
        errors.add((line, f"machina-ai provider must be vertex_ai or omitted, got {provider!r}"))
    if profile not in ALLOWED_PROFILES:
        errors.add((line, f"machina-ai profile {profile!r} is not allowed in committed workflows"))
    if command not in ALLOWED_COMMANDS:
        errors.add((line, f"machina-ai command {command!r} is not in the v1 inventory"))
    if model and model != "text-embedding-004" and not model.startswith("gemini-"):
        errors.add((line, f"machina-ai model {model!r} is not a repository-approved Vertex model"))
    for forbidden in sorted(FORBIDDEN_KEYS.intersection(connector)):
        errors.add(
            (line, f"machina-ai workflow connector may not set policy/security field {forbidden!r}")
        )


def _mapping_items(node):
    """Return {scalar_key: value_node} for a YAML MappingNode, else {}."""
    if yaml is None or not isinstance(node, yaml.nodes.MappingNode):
        return {}
    items = {}
    for key_node, value_node in node.value:
        if isinstance(key_node, yaml.nodes.ScalarNode):
            items.setdefault(str(key_node.value), value_node)
    return items


def _scalar(node):
    if yaml is not None and isinstance(node, yaml.nodes.ScalarNode):
        return "" if node.value is None else str(node.value)
    return ""


def _node_line(node):
    mark = getattr(node, "start_mark", None)
    return (mark.line + 1) if mark is not None else 0


def semantic_lint(text: str) -> set[tuple[int, str]]:
    """Parsed-YAML pass so quoted keys and flow mappings cannot dodge the lint.

    Walks the composed node graph (instead of plain ``safe_load`` values) so
    findings carry real line numbers.
    """

    errors: set[tuple[int, str]] = set()
    if yaml is None:
        return errors
    try:
        documents = list(yaml.compose_all(text))
    except yaml.YAMLError:
        return errors

    seen = set()

    def walk(node):
        if node is None or id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, yaml.nodes.MappingNode):
            items = _mapping_items(node)
            connector_node = items.get("connector")
            if isinstance(connector_node, yaml.nodes.MappingNode):
                connector_items = _mapping_items(connector_node)
                connector_line = _node_line(connector_node)
                connector = {key: _scalar(value) for key, value in connector_items.items()}
                name = str(connector.get("name") or "")
                if name == "machina-ai":
                    _validate_router_connector(connector, errors, line=connector_line)
                    inputs_items = _mapping_items(items.get("inputs"))
                    for key in sorted(INPUT_ROUTING_KEYS.intersection(inputs_items)):
                        errors.add(
                            (
                                _node_line(inputs_items[key]),
                                f"machina-ai task inputs may not set routing/security field {key!r}",
                            )
                        )
                elif name == "openai":
                    errors.add(
                        (
                            connector_line,
                            "workflow connector name 'openai' is banned; use google-genai "
                            "or the policy-governed machina-ai router",
                        )
                    )
                model = str(connector.get("model") or connector.get("model_name") or "")
                if model.lower().startswith("gpt-"):
                    errors.add(
                        (
                            connector_line,
                            f"hardcoded GPT model route {model!r} is banned; use a Vertex model",
                        )
                    )
            router_variables = _mapping_items(items.get("machina-ai"))
            for key in sorted(FORBIDDEN_KEYS.intersection(router_variables)):
                errors.add(
                    (
                        _node_line(router_variables[key]),
                        f"machina-ai context variables may not set {key!r}; "
                        "bind provider credentials in runtime policy",
                    )
                )
            for _, value in node.value:
                walk(value)
        elif isinstance(node, yaml.nodes.SequenceNode):
            for item in node.value:
                walk(item)

    for document in documents:
        walk(document)
    return errors


def lint_file(path: Path, content=None, relative_override=None):
    try:
        relative = relative_override or path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        relative = relative_override or path.as_posix()
    if any(relative == prefix or relative.startswith(prefix) for prefix in EXEMPT_PREFIXES):
        return []
    text = path.read_text(encoding="utf-8") if content is None else content
    lines = text.splitlines()
    errors = []
    for start, block in connector_blocks(lines):
        values = {}
        locations = {}
        for line_number, line in block:
            key, value = key_value(line)
            if key:
                values.setdefault(key, value)
                locations.setdefault(key, line_number)
        if values.get("name") != "machina-ai":
            continue
        provider = values.get("provider", "")
        profile = values.get("profile", "")
        command = values.get("command", "")
        model = values.get("model", "") or values.get("model_name", "")
        if provider not in ALLOWED_PROVIDERS:
            errors.append((locations.get("provider", start), f"machina-ai provider must be vertex_ai or omitted, got {provider!r}"))
        if profile not in ALLOWED_PROFILES:
            errors.append((locations.get("profile", start), f"machina-ai profile {profile!r} is not allowed in committed workflows"))
        if command not in ALLOWED_COMMANDS:
            errors.append((locations.get("command", start), f"machina-ai command {command!r} is not in the v1 inventory"))
        if model and model != "text-embedding-004" and not model.startswith("gemini-"):
            errors.append((locations.get("model", locations.get("model_name", start)), f"machina-ai model {model!r} is not a repository-approved Vertex model"))
        for forbidden in sorted(FORBIDDEN_KEYS.intersection(values)):
            errors.append((locations[forbidden], f"machina-ai workflow connector may not set policy/security field {forbidden!r}"))

        connector_indent = len(lines[start - 1]) - len(lines[start - 1].lstrip())
        cursor = start
        while cursor < len(lines):
            current = lines[cursor]
            current_indent = len(current) - len(current.lstrip()) if current.strip() else connector_indent + 1
            if current.strip() and current_indent < connector_indent:
                break
            key, _ = key_value(current)
            if key == "inputs" and current_indent == connector_indent:
                input_indent = current_indent
                input_cursor = cursor + 1
                while input_cursor < len(lines):
                    input_line = lines[input_cursor]
                    if input_line.strip() and len(input_line) - len(input_line.lstrip()) <= input_indent:
                        break
                    input_key, _ = key_value(input_line)
                    if input_key in INPUT_ROUTING_KEYS:
                        errors.append((input_cursor + 1, f"machina-ai task inputs may not set routing/security field {input_key!r}"))
                    input_cursor += 1
                break
            cursor += 1
    # Context-variable credentials for the facade bypass provider-scoped runtime binding.
    for index, line in enumerate(lines):
        if line.strip().rstrip(":").strip("'\"") != "machina-ai":
            continue
        indent = len(line) - len(line.lstrip())
        cursor = index + 1
        while cursor < len(lines):
            current = lines[cursor]
            if current.strip() and (len(current) - len(current.lstrip())) <= indent:
                break
            key, _ = key_value(current)
            if key in FORBIDDEN_KEYS:
                errors.append((cursor + 1, f"machina-ai context variables may not set {key!r}; bind provider credentials in runtime policy"))
            cursor += 1

    reported = {message for _, message in errors}
    for line, message in sorted(semantic_lint(text)):
        if message not in reported:
            errors.append((line, message))
    return [(relative, line, message) for line, message in errors]


def candidate_files(arguments):
    mode = arguments[0] if arguments else "all"
    if mode == "staged":
        output = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=ROOT,
            text=True,
        )
        return [ROOT / item for item in output.splitlines() if item.endswith((".yml", ".yaml"))]
    if mode == "all":
        return [path for path in ROOT.rglob("*.yml") if ".git" not in path.parts and "node_modules" not in path.parts] + [
            path for path in ROOT.rglob("*.yaml") if ".git" not in path.parts and "node_modules" not in path.parts
        ]
    return [Path(item).resolve() for item in arguments]


def main(argv=None):
    arguments = list(argv if argv is not None else sys.argv[1:])
    require_semantic = "--require-semantic" in arguments
    arguments = [item for item in arguments if item != "--require-semantic"]
    if yaml is None:
        print(
            "[lint-machina-ai-policy] WARNING: PyYAML is not installed, so the "
            "semantic (parsed-YAML) router-policy pass was SKIPPED. Quoted keys "
            "and flow-style YAML can dodge the line-based scan. Install pyyaml "
            "(python3 -m pip install pyyaml) to restore full coverage.",
            file=sys.stderr,
        )
        if require_semantic:
            print(
                "[lint-machina-ai-policy] --require-semantic: failing because "
                "the semantic pass is unavailable without PyYAML.",
                file=sys.stderr,
            )
            return 2
    staged = bool(arguments and arguments[0] == "staged")
    paths = candidate_files(arguments)
    errors = []
    for path in paths:
        if staged:
            relative = path.resolve().relative_to(ROOT).as_posix()
            content = subprocess.check_output(["git", "show", f":{relative}"], cwd=ROOT, text=True)
            errors.extend(lint_file(path, content=content, relative_override=relative))
        else:
            errors.extend(lint_file(path))
    if errors:
        print("[lint-machina-ai-policy] Unsafe machina-ai workflow configuration found.", file=sys.stderr)
        for relative, line, message in errors:
            print(f"  {relative}:{line}: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
