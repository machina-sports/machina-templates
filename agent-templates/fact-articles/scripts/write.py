"""Step 4: the writer turns a facts doc into an article (pt-BR JSON, every sentence citing fact ids).

Backends share one interface, write(facts_doc, client) -> article, picked by client.writer.backend.
Only `claude-cli` exists now (local runs); a Vertex/Gemini backend, the machina-templates default,
plugs into BACKENDS when the engine phase starts.
"""
import json
import os
import pathlib
import subprocess

PROMPT = pathlib.Path(__file__).resolve().parents[1] / "prompts" / "writer.md"


class WriterError(RuntimeError):
    pass


def writer_input(facts_doc, client):
    """What the writer sees: fact id, kind, subject and text (values and scores stay out), the plan, and the
    client config (the prompt reads language, site, nicknames and compliance.forbidden from it)."""
    return {"facts": [{k: f[k] for k in ("id", "kind", "subject", "text")} for f in facts_doc["facts"]],
            "plan": facts_doc["plan"], "client": client}


def parse_article(raw):
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise WriterError(f"writer returned no JSON object: {raw[:200]!r}")
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError as e:
        raise WriterError(f"writer returned invalid JSON ({e}): {raw[:200]!r}") from e


def system_prompt():
    if not PROMPT.exists():
        raise WriterError(f"writer prompt not found at {PROMPT}; it is written by the SEO specialist (prompts/writer.md)")
    return PROMPT.read_text()


def write_claude_cli(facts_doc, client):
    model = (client.get("writer") or {}).get("model", "sonnet")
    cmd = ["claude", "-p", "--model", model, "--setting-sources", "", "--strict-mcp-config", "--tools", "",
           "--system-prompt", system_prompt(), json.dumps(writer_input(facts_doc, client), ensure_ascii=False)]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_PLUGIN_DIRS"}  # = env -u CLAUDE_CODE_PLUGIN_DIRS
    out = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600, stdin=subprocess.DEVNULL)
    if out.returncode != 0:
        raise WriterError(f"claude CLI exited {out.returncode}: {(out.stderr or out.stdout)[:300]}")
    return parse_article(out.stdout)


BACKENDS = {"claude-cli": write_claude_cli}


def write(facts_doc, client):
    backend = (client.get("writer") or {}).get("backend", "claude-cli")
    if backend not in BACKENDS:
        raise WriterError(f"unknown writer backend {backend!r}; available: {sorted(BACKENDS)}")
    return BACKENDS[backend](facts_doc, client)


def invoke_write(request_data):
    p = request_data.get("params") or {}
    try:
        return {"status": True, "data": write(p["facts_doc"], p.get("client") or {})}
    except (WriterError, KeyError, subprocess.TimeoutExpired) as e:
        return {"status": False, "message": f"write: {e}"}
