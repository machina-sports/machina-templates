#!/usr/bin/env python3
"""Inventory AI connector declarations and workflow dispatch strings.

Every discovered command for the v1 provider set must be explicitly mapped,
kept as a provider escape hatch, or marked unsupported.  This is intentionally
stdlib-only so it can run in pre-merge CI without provider dependencies.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONNECTORS = {
    "machina-ai",
    "machina-ai-fast",
    "google-genai",
    "vertex-embedding",
    "openai",
    "azure-foundry",
    "groq",
    "grok",
    "perplexity",
    "nvidia-nim",
    "byteplus-modelark",
    "stability",
    "elevenlabs",
    "google-speech-to-text",
}

# (connector, command): router canonical command or an explicit disposition.
MAPPINGS = {
    **{("machina-ai", command): command for command in (
        "invoke_prompt", "invoke_chat", "completion_receipt", "invoke_embedding",
        "embed_query", "embed_documents", "list_models", "health", "invoke_search",
        "invoke_image", "generate_image", "edit_image", "invoke_video",
        "transcribe_audio_to_text", "invoke_transcribe", "invoke_tts",
        "get_text_to_speech", "list_voices", "get_voices",
        "invoke_clone_instant_voice", "invoke_train_pro_voice",
        "invoke_synthesize_custom_voice", "invoke_music",
    )},
    ("machina-ai-fast", "invoke_prompt"): "invoke_prompt(profile=fast)",
    ("machina-ai-fast", "invoke_embedding"): "unsupported:fake-embedding-removed",
    ("google-genai", "invoke_prompt"): "invoke_prompt",
    ("google-genai", "invoke_embedding"): "invoke_embedding",
    ("google-genai", "list_models"): "list_models",
    ("google-genai", "transcribe_audio_to_text"): "transcribe_audio_to_text",
    ("google-genai", "invoke_search"): "invoke_search",
    ("google-genai", "invoke_image"): "invoke_image",
    ("google-genai", "edit_image"): "invoke_image(operation=edit)",
    ("google-genai", "invoke_video"): "invoke_video",
    ("google-genai", "invoke_tts"): "invoke_tts",
    ("google-genai", "invoke_clone_instant_voice"): "provider-extension:voice",
    ("google-genai", "invoke_train_pro_voice"): "provider-extension:voice",
    ("google-genai", "invoke_synthesize_custom_voice"): "provider-extension:voice",
    ("google-genai", "invoke_music"): "invoke_music",
    ("vertex-embedding", "invoke_embedding"): "invoke_embedding",
    ("vertex-embedding", "embed_query"): "embed_query",
    ("vertex-embedding", "embed_documents"): "embed_documents",
    ("openai", "list_models"): "list_models",
    ("openai", "invoke_prompt"): "invoke_prompt",
    ("openai", "invoke_embedding"): "invoke_embedding",
    ("openai", "transcribe_audio_to_text"): "transcribe_audio_to_text",
    ("azure-foundry", "invoke_prompt"): "invoke_prompt",
    ("azure-foundry", "invoke_embedding"): "invoke_embedding",
    ("azure-foundry", "Prompt"): "broken-display-label:use-invoke_prompt",
    ("groq", "list_models"): "list_models",
    ("groq", "invoke_prompt"): "invoke_prompt(profile=fast)",
    ("groq", "invoke_embedding"): "unsupported:groq-has-no-embeddings",
    ("grok", "post-responses"): "invoke_chat(tools-policy)",
    ("grok", "responses"): "invoke_chat(tools-policy)",
    ("grok", "post-chat/completions"): "invoke_chat",
    ("grok", "createChatCompletion"): "invoke_chat",
    ("perplexity", "post-chat/completions"): "invoke_search",
    ("perplexity", "chat/completions"): "invoke_search",
    ("perplexity", "createChatCompletion"): "invoke_search",
    ("nvidia-nim", "health"): "health",
    ("nvidia-nim", "list_models"): "list_models",
    ("nvidia-nim", "invoke_chat"): "invoke_prompt(factory)",
    ("nvidia-nim", "completion_receipt"): "invoke_chat(execute)",
    ("byteplus-modelark", "post-contents/generations/tasks"): "invoke_video(create_task)",
    ("byteplus-modelark", "get-contents/generations/tasks"): "invoke_video(list_tasks)",
    ("byteplus-modelark", "get-contents/generations/tasks/{id}"): "invoke_video(get_task)",
    ("byteplus-modelark", "delete-contents/generations/tasks/{id}"): "invoke_video(delete_task)",
    ("stability", "generate_image"): "invoke_image",
    ("elevenlabs", "get_text_to_speech"): "invoke_tts",
    ("elevenlabs", "get_voices"): "list_voices",
    ("google-speech-to-text", "invoke_transcribe"): "transcribe_audio_to_text",
}

SCALAR = re.compile(r"^\s*(?:-\s*)?([A-Za-z0-9_-]+)\s*:\s*['\"]?([^#'\"]*?)['\"]?\s*(?:#.*)?$")


def yaml_scalar(line):
    match = SCALAR.match(line)
    if not match:
        return None, None
    return match.group(1), match.group(2).strip()


def yaml_connector_identity(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    in_connector = False
    connector_indent = -1
    name = None
    commands = []
    in_commands = False
    commands_indent = -1
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        key, value = yaml_scalar(line)
        if key == "connector" and not value and indent == 0:
            in_connector = True
            connector_indent = indent
            in_commands = False
            continue
        if in_connector and indent <= connector_indent:
            in_connector = False
            in_commands = False
        if not in_connector:
            continue
        if key == "name" and name is None:
            name = value
        if key == "commands" and not value:
            in_commands = True
            commands_indent = indent
            continue
        if in_commands and indent <= commands_indent:
            in_commands = False
        if in_commands and key == "value" and value:
            commands.append(value)
    return name, commands


def yaml_calls(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    calls = []
    index = 0
    while index < len(lines):
        key, value = yaml_scalar(lines[index])
        if key != "connector" or value:
            index += 1
            continue
        indent = len(lines[index]) - len(lines[index].lstrip())
        block = {}
        cursor = index + 1
        while cursor < len(lines):
            line = lines[cursor]
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            child_key, child_value = yaml_scalar(line)
            if child_key in {"name", "command"} and child_value:
                block[child_key] = child_value
            cursor += 1
        if block.get("name") in CONNECTORS and block.get("command"):
            calls.append((block["name"], block["command"], index + 1))
        index = cursor
    return calls


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def json_inventory(path):
    """Derive REST dispatch strings (method-path) from an OpenAPI-style spec.

    Every discovered command is returned, mapped or not, so an unreviewed
    endpoint added to a provider JSON surfaces in the unknown-commands report
    instead of being filtered out before comparison.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    connector = path.parent.name if path.parent.name in CONNECTORS else None
    if not connector:
        return []
    declared = []
    paths = document.get("paths", {})
    if isinstance(paths, dict):
        for api_path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, operation in methods.items():
                if method.lower() not in HTTP_METHODS:
                    continue
                declared.append((connector, f"{method.lower()}-{api_path.lstrip('/')}"))
                if isinstance(operation, dict) and isinstance(operation.get("operationId"), str):
                    declared.append((connector, operation["operationId"]))
    return declared


def collect():
    declared = set()
    observed = []
    identities = {}
    for connector in sorted(CONNECTORS):
        directory = ROOT / "connectors" / connector
        if not directory.is_dir():
            continue
        for path in directory.glob("*.yml"):
            name, commands = yaml_connector_identity(path)
            if name:
                identities.setdefault(name, []).append(path.relative_to(ROOT).as_posix())
                for command in commands:
                    declared.add((name, command))
        for path in directory.glob("*.json"):
            declared.update(json_inventory(path))
    for pattern in ("*.yml", "*.yaml"):
        for path in ROOT.rglob(pattern):
            if ".git" in path.parts or "node_modules" in path.parts:
                continue
            for connector, command, line in yaml_calls(path):
                observed.append((connector, command, path.relative_to(ROOT).as_posix(), line))
    return declared, observed, identities


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    declared, observed, identities = collect()
    discovered = set(declared) | {(connector, command) for connector, command, _, _ in observed}
    unknown = sorted(discovered - set(MAPPINGS))
    collisions = {name: paths for name, paths in identities.items() if len(set(paths)) > 1 and name in CONNECTORS}
    result = {
        "declared": [{"connector": c, "command": cmd, "mapping": MAPPINGS.get((c, cmd))} for c, cmd in sorted(declared)],
        "observed": [{"connector": c, "command": cmd, "path": path, "line": line, "mapping": MAPPINGS.get((c, cmd))} for c, cmd, path, line in sorted(observed)],
        "unknown": [{"connector": c, "command": cmd} for c, cmd in unknown],
        "identity_collisions": collisions,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"AI commands declared: {len(declared)}")
        print(f"AI workflow calls observed: {len(observed)}")
        print(f"Unknown commands: {len(unknown)}")
        print(f"Connector identity collisions: {len(collisions)}")
        for connector, command in unknown:
            print(f"  unmapped: {connector}/{command}", file=sys.stderr)
        for name, paths in collisions.items():
            print(f"  identity collision {name}: {', '.join(paths)}", file=sys.stderr)
    return 1 if unknown or collisions else 0


if __name__ == "__main__":
    raise SystemExit(main())
