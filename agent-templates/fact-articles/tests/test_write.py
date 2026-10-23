import json
import subprocess

import pytest

import write

DOC = {"event_id": "1", "facts": [{"id": "f01", "kind": "match", "subject": "both", "text": "A x B", "value": {},
                                   "score": 0, "norm": 0, "source": "s", "as_of": "d", "tier": "data"}],
       "plan": {"lead_fact": "f01", "match_fact": "f01", "sections": []}}
CLIENT = {"writer": {"backend": "claude-cli", "model": "sonnet"}}


def test_missing_prompt_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.setattr(write, "PROMPT", tmp_path / "prompts" / "writer.md")
    with pytest.raises(write.WriterError, match="prompts/writer.md"):
        write.write(DOC, CLIENT)


def test_claude_cli_call_and_parse(tmp_path, monkeypatch):
    prompt = tmp_path / "writer.md"
    prompt.write_text("SYSTEM")
    monkeypatch.setattr(write, "PROMPT", prompt)
    monkeypatch.setenv("CLAUDE_CODE_PLUGIN_DIRS", "/x")
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["env"] = cmd, kw["env"]
        return subprocess.CompletedProcess(cmd, 0, stdout='Here:\n{"headline": "h", "lead": [], "sections": []}\n', stderr="")

    monkeypatch.setattr(write.subprocess, "run", fake_run)
    art = write.write(DOC, CLIENT)
    assert art == {"headline": "h", "lead": [], "sections": []}
    cmd = seen["cmd"]
    assert cmd[:4] == ["claude", "-p", "--model", "sonnet"]
    assert cmd[cmd.index("--setting-sources") + 1] == "" and cmd[cmd.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in cmd and cmd[cmd.index("--system-prompt") + 1] == "SYSTEM"
    sent = json.loads(cmd[-1])
    assert sent["plan"] == DOC["plan"] and set(sent["facts"][0]) == {"id", "kind", "subject", "text"}
    assert sent["client"] == CLIENT
    assert "CLAUDE_CODE_PLUGIN_DIRS" not in seen["env"]


def test_bad_output_and_unknown_backend(tmp_path, monkeypatch):
    with pytest.raises(write.WriterError, match="no JSON"):
        write.parse_article("sorry")
    with pytest.raises(write.WriterError, match="unknown writer backend"):
        write.write(DOC, {"writer": {"backend": "vertex"}})
