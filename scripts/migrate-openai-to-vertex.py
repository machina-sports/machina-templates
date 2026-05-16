#!/usr/bin/env python3
"""
Bulk migration: OpenAI → Vertex AI across machina-templates workflows.

Why: the OpenAI account used by Machina was deprecated. Every workflow that
still references it (~180 files) silently fails with "invalid_organization"
when its embedding/prompt step fires. Rather than rotate the dead key, we
move everything to the `google-genai` connector + Vertex AI.

What it does, in order:

  1. Replace model strings:
       text-embedding-3-* / text-embedding-ada-002  →  text-embedding-004
       gpt-4o-mini / gpt-4.1-mini / gpt-3.5-turbo   →  gemini-2.5-flash
       gpt-4 / gpt-4o / gpt-4.1                     →  gemini-2.5-pro

  2. Replace `context-variables:` blocks that hold the old api_key:
       machina-ai: { api_key: $TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY }
       →
       google-genai: { credential: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL,
                       project_id: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID }

  3. Replace `connector.name`:
       openai / machina-ai  →  google-genai

  4. For each task `connector:` block whose name is now `google-genai`, inject
     the `location: "global"` and `provider: "vertex_ai"` fields after the
     `model:` line if they're missing. This matches the canonical pattern
     established by `connectors/google-genai/test-credentials.yml`.

Run from the repo root:
    python3 scripts/migrate-openai-to-vertex.py            # dry-run, prints diff
    python3 scripts/migrate-openai-to-vertex.py --apply    # writes files

Idempotent: re-running on a migrated file is a no-op.
"""

import argparse
import difflib
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


PROMPT_MODELS_TO_FLASH = {"gpt-4o-mini", "gpt-4.1-mini", "gpt-3.5-turbo"}
PROMPT_MODELS_TO_PRO = {"gpt-4o", "gpt-4.1", "gpt-4"}
EMBEDDING_MODELS = {"text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"}


def _replace_value(text: str, old: str, new: str) -> str:
    """
    Replace `old` with `new` when it appears as a YAML scalar value — anchored
    by quotes, whitespace, or line boundaries on both sides. Avoids touching
    substrings inside identifiers/URLs.
    """
    # Match: start-of-token, the model, end-of-token. Tokens here are delimited
    # by quotes, whitespace, end of line, or `#` (comment).
    pattern = rf'(?P<pre>["\']?){re.escape(old)}(?P<post>["\']?)(?=[\s#\n]|$)'
    return re.sub(pattern, rf'\g<pre>{new}\g<post>', text)


def step_model_strings(text: str) -> str:
    for m in EMBEDDING_MODELS:
        text = _replace_value(text, m, "text-embedding-004")
    for m in PROMPT_MODELS_TO_FLASH:
        text = _replace_value(text, m, "gemini-2.5-flash")
    for m in PROMPT_MODELS_TO_PRO:
        text = _replace_value(text, m, "gemini-2.5-pro")
    return text


def step_context_variables(text: str) -> str:
    """
    Rewrite context-variables blocks. Two source forms seen in templates:

        machina-ai:
          api_key: $TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY

        openai:
          api_key: $TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY

    Both become:

        google-genai:
          credential: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL
          project_id: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID

    Preserves the existing indentation.
    """
    pattern = re.compile(
        r'(?P<outer>[ \t]*)(?:machina-ai|openai):[ \t]*\n'
        r'(?P<inner>[ \t]+)api_key:[ \t]*["\']?\$(?:TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY|MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY)["\']?[ \t]*\n',
        flags=re.MULTILINE,
    )

    def repl(m):
        outer = m.group("outer")
        inner = m.group("inner")
        return (
            f'{outer}google-genai:\n'
            f'{inner}credential: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL\n'
            f'{inner}project_id: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID\n'
        )

    return pattern.sub(repl, text)


def step_connector_name(text: str) -> str:
    """
    Replace `name: openai` and `name: machina-ai` with `name: google-genai`
    when they appear as a YAML key. Preserves any quotes around the value.
    """
    def repl(m):
        return f'{m.group("prefix")}{m.group("quote") or ""}google-genai{m.group("quote") or ""}'

    pattern = re.compile(
        r'(?P<prefix>\bname:[ \t]+)(?P<quote>["\']?)(?:openai|machina-ai)(?P=quote)(?=[ \t#\n]|$)',
        flags=re.MULTILINE,
    )
    return pattern.sub(repl, text)


def step_inject_vertex_fields(text: str) -> str:
    """
    For every line block where `name: "google-genai"` is set, ensure
    `location: "global"` and `provider: "vertex_ai"` follow the `model:` line
    (if they aren't already in the same indent level).

    We walk lines tracking the most-recently-opened google-genai connector
    block (defined by name's indent level). On exit (indent drops to <=
    block_indent OR end-of-file), we close the block and verify the fields
    are present. If `model:` was seen and they're missing, inject right after
    `model:` at the same indent.
    """
    lines = text.split("\n")
    out: list[str] = []

    # State for the current block (None = not inside a google-genai block)
    block_indent: int | None = None
    saw_model_at: int | None = None  # index into `out`
    saw_location = False
    saw_provider = False
    field_indent: str = ""

    def close_block():
        nonlocal block_indent, saw_model_at, saw_location, saw_provider, field_indent
        if block_indent is None:
            return
        if saw_model_at is not None and (not saw_location or not saw_provider):
            inject = []
            if not saw_location:
                inject.append(f'{field_indent}location: "global"')
            if not saw_provider:
                inject.append(f'{field_indent}provider: "vertex_ai"')
            # Insert after the model line we recorded
            out[saw_model_at + 1 : saw_model_at + 1] = inject
        block_indent = None
        saw_model_at = None
        saw_location = False
        saw_provider = False
        field_indent = ""

    for raw in lines:
        stripped = raw.lstrip()
        indent_len = len(raw) - len(stripped)

        # Detect opening of a google-genai connector block
        is_open = bool(re.match(r'name:[ \t]+["\']?google-genai["\']?(?:[ \t#].*)?$', stripped))

        if block_indent is not None:
            # YAML connector block siblings (`command:`, `model:`, etc) share the
            # SAME indent as `name:`. The block closes only when we see a non-blank
            # line at strictly lesser indent (parent level) OR a new `name:` opener.
            if stripped and indent_len < block_indent and not is_open:
                close_block()

        out.append(raw)

        if is_open:
            close_block()  # close any prior block first
            block_indent = indent_len

        if block_indent is not None:
            # Track sibling fields (same indent as the `name:` line)
            if stripped and indent_len == block_indent:
                if stripped.startswith("model:"):
                    saw_model_at = len(out) - 1
                    field_indent = " " * indent_len
                elif stripped.startswith("location:"):
                    saw_location = True
                elif stripped.startswith("provider:"):
                    saw_provider = True

    # End of file: close last block
    close_block()
    return "\n".join(out)


def migrate(text: str) -> str:
    text = step_model_strings(text)
    text = step_context_variables(text)
    text = step_connector_name(text)
    text = step_inject_vertex_fields(text)
    return text


def find_target_files() -> list[Path]:
    """All YAML files under the repo that match the OpenAI/embedding/gpt patterns."""
    import subprocess
    cmd = [
        "grep", "-ril", "--include=*.yml", "--include=*.yaml",
        "-E", r"openai|text-embedding-3|text-embedding-ada|gpt-3\.5|gpt-4|SDK_OPENAI",
        str(ROOT),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return [Path(p) for p in res.stdout.splitlines() if p.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    ap.add_argument("--paths", nargs="*", help="Restrict to specific files (relative to repo)")
    args = ap.parse_args()

    targets = [Path(p) for p in args.paths] if args.paths else find_target_files()
    if not targets:
        print("No target files found.")
        return 0

    changed: list[tuple[Path, str, str]] = []
    for p in targets:
        original = p.read_text()
        new = migrate(original)
        if new != original:
            changed.append((p, original, new))

    if not changed:
        print("Nothing to migrate (all files already on Vertex).")
        return 0

    for p, old, new in changed:
        rel = p.relative_to(ROOT) if str(p).startswith(str(ROOT)) else p
        if args.apply:
            p.write_text(new)
            print(f"updated: {rel}")
        else:
            diff = difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=str(rel),
                tofile=str(rel),
                n=2,
            )
            sys.stdout.writelines(diff)

    print(f"\n{len(changed)} file(s) {'updated' if args.apply else 'would change'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
