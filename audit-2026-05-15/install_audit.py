#!/usr/bin/env python3
"""
Install audit driver for machina-templates catalog.

Drives the MCP `machina-factory-customers` SSE server (templates-testing project)
to call `import_templates_from_git` against every published template path.
Captures status + error for each install and writes structured evidence.

Usage:
    python3 install_audit.py [--scope agent-templates,connectors,skills,mkn-constructor]

Outputs:
    results.json       — full structured payload per template
    results.md         — human-readable report (RED for failures)
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import queue
import re
import sys
import threading
import time
import urllib.request

MCP_BASE = "https://machina-factory-factory-templates-testing.org.machina.gg"
MCP_TOKEN = "BuDmcwOt7-97vbWaXUnsd3EwFdMmqpLSgqJ95G8boG1_hTDM6NRL-wV1LKc1fsBXHKGIuUHtZ-_pw_bzzpiE7Q"
SSE_URL = f"{MCP_BASE}/mcp/sse"
REPO_URL = "https://github.com/machina-sports/machina-templates"
REPO_BRANCH = "main"

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = pathlib.Path(__file__).resolve().parent


class MCPClient:
    """Minimal MCP SSE client. Holds the SSE stream open in a thread, posts
    JSON-RPC to /messages/?session_id=…, routes responses by id."""

    def __init__(self, sse_url: str, token: str):
        self.sse_url = sse_url
        self.token = token
        self.session_endpoint: str | None = None
        self._next_id = 1
        self._pending: dict[int, queue.Queue] = {}
        self._stop = False
        self._sse_thread = threading.Thread(target=self._sse_reader, daemon=True)

    def start(self, timeout: float = 10.0):
        self._sse_thread.start()
        deadline = time.time() + timeout
        while time.time() < deadline and self.session_endpoint is None:
            time.sleep(0.05)
        if self.session_endpoint is None:
            raise RuntimeError("MCP: SSE endpoint never arrived")

        # initialize
        self._call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "machina-templates-audit", "version": "0.1"},
        }, timeout=15)
        self._notify("notifications/initialized", {})

    def _sse_reader(self):
        req = urllib.request.Request(
            self.sse_url,
            headers={
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {self.token}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                event = None
                for raw in resp:
                    if self._stop:
                        break
                    line = raw.decode("utf-8", errors="replace").rstrip("\n")
                    if line.startswith("event:"):
                        event = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        data = line.split(":", 1)[1].strip()
                        if event == "endpoint" and self.session_endpoint is None:
                            self.session_endpoint = MCP_BASE + data
                        elif event == "message":
                            try:
                                msg = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            rid = msg.get("id")
                            if rid in self._pending:
                                self._pending[rid].put(msg)
                    elif line == "":
                        event = None
        except Exception as exc:
            # surface SSE crash to any waiting calls
            for q in self._pending.values():
                q.put({"error": {"message": f"SSE reader crashed: {exc}"}})

    def _post(self, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.session_endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status

    def _call(self, method: str, params: dict, timeout: float = 120.0) -> dict:
        rid = self._next_id
        self._next_id += 1
        q: queue.Queue = queue.Queue()
        self._pending[rid] = q
        self._post({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            msg = q.get(timeout=timeout)
        except queue.Empty:
            del self._pending[rid]
            raise TimeoutError(f"MCP call '{method}' timed out after {timeout}s")
        del self._pending[rid]
        return msg

    def _notify(self, method: str, params: dict):
        self._post({"jsonrpc": "2.0", "method": method, "params": params})

    def call_tool(self, name: str, arguments: dict, timeout: float = 180.0) -> dict:
        return self._call("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)

    def stop(self):
        self._stop = True


def discover_catalog(scopes: list[str]) -> list[tuple[str, str]]:
    """Return list of (scope, template_path) tuples from the local repo."""
    items: list[tuple[str, str]] = []

    if "agent-templates" in scopes:
        for d in sorted((REPO_ROOT / "agent-templates").iterdir()):
            if d.is_dir() and (d / "_install.yml").exists():
                items.append(("agent-templates", f"agent-templates/{d.name}"))

    if "connectors" in scopes:
        for d in sorted((REPO_ROOT / "connectors").iterdir()):
            if d.is_dir() and (d / "_install.yml").exists():
                items.append(("connectors", f"connectors/{d.name}"))

    if "skills" in scopes:
        for d in sorted((REPO_ROOT / "skills").iterdir()):
            if d.is_dir() and (d / "_install.yml").exists():
                items.append(("skills", f"skills/{d.name}"))

    if "mkn-constructor" in scopes:
        mkn = REPO_ROOT / "mkn-constructor"
        if mkn.is_dir() and (mkn / "_install.yml").exists():
            items.append(("mkn-constructor", "mkn-constructor"))

    return items


def classify(response: dict) -> tuple[str, str]:
    """Inspect the MCP tools/call response. Returns (status, evidence_summary)."""
    if "error" in response:
        return ("ERROR", json.dumps(response["error"])[:1000])

    result = response.get("result", {})
    if result.get("isError"):
        text_parts = []
        for c in result.get("content", []):
            if c.get("type") == "text":
                text_parts.append(c.get("text", ""))
        return ("FAIL", "\n".join(text_parts)[:2000])

    text_parts = []
    for c in result.get("content", []):
        if c.get("type") == "text":
            text_parts.append(c.get("text", ""))
    body = "\n".join(text_parts)

    # The API wraps responses as {"status": "success"|"error", ...}
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        parsed = None

    if isinstance(parsed, dict):
        status = parsed.get("status")
        if status == "error":
            err = parsed.get("error") or parsed.get("message") or parsed
            return ("FAIL", json.dumps(err)[:2000])
        if status == "success":
            # walk the nested response looking for status:false or error markers.
            issues = _collect_issues(parsed)
            if issues:
                return ("PARTIAL", json.dumps(issues, ensure_ascii=False)[:2000])
            return ("OK", body[:600])

    return ("OK", body[:600])


def _collect_issues(node, path: str = "") -> list[dict]:
    """Walk arbitrary JSON; flag any dict that has status:false / error fields
    that look like a real failure (non-empty)."""
    issues: list[dict] = []
    if isinstance(node, dict):
        st = node.get("status")
        if st is False or st == "error":
            err = node.get("error") or node.get("message")
            issues.append({"path": path, "message": err, "snippet": {k: node.get(k) for k in ("status", "message", "error") if k in node}})
        # 'error' field with truthy non-empty content (besides None/null/empty)
        e = node.get("error")
        if e and not isinstance(e, bool) and not (isinstance(e, str) and e.strip().lower() in ("none", "null")):
            issues.append({"path": path + ".error", "message": e if not isinstance(e, dict) else json.dumps(e)[:500]})
        for k, v in node.items():
            issues.extend(_collect_issues(v, f"{path}.{k}" if path else k))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            issues.extend(_collect_issues(item, f"{path}[{i}]"))
    return issues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scope",
        default="agent-templates,connectors,skills,mkn-constructor",
        help="Comma-separated scopes to test",
    )
    parser.add_argument("--limit", type=int, default=0, help="Stop after N templates (0 = no limit)")
    parser.add_argument("--skip", type=int, default=0, help="Skip the first N templates")
    parser.add_argument("--resume", action="store_true", help="Resume from existing results.json")
    args = parser.parse_args()

    scopes = [s.strip() for s in args.scope.split(",") if s.strip()]
    catalog = discover_catalog(scopes)

    if args.skip:
        catalog = catalog[args.skip:]
    if args.limit:
        catalog = catalog[: args.limit]

    print(f"[audit] catalog size: {len(catalog)}")
    print(f"[audit] scopes: {scopes}")

    results_path = OUT_DIR / "results.json"
    done: dict[str, dict] = {}
    if args.resume and results_path.exists():
        done = {r["template"]: r for r in json.loads(results_path.read_text()).get("results", [])}
        print(f"[audit] resuming, {len(done)} prior results loaded")

    client = MCPClient(SSE_URL, MCP_TOKEN)
    client.start()
    print(f"[audit] MCP session: {client.session_endpoint}")

    # sanity
    try:
        h = client.call_tool("health_check", {}, timeout=15)
        print(f"[audit] health_check: {classify(h)[0]}")
    except Exception as e:
        print(f"[audit] health_check failed: {e}", file=sys.stderr)

    results: list[dict] = []
    for idx, (scope, template_path) in enumerate(catalog, 1):
        if template_path in done:
            results.append(done[template_path])
            print(f"[{idx}/{len(catalog)}] {template_path} (cached: {done[template_path]['status']})")
            continue

        payload = {
            "repositories": [{
                "repo_url": REPO_URL,
                "template": template_path,
                "repo_branch": REPO_BRANCH,
                "private_repository": False,
            }]
        }
        start = time.time()
        try:
            resp = client.call_tool("import_templates_from_git", payload, timeout=240)
            status, evidence = classify(resp)
        except Exception as e:
            resp = {"error": {"message": str(e)}}
            status, evidence = ("ERROR", str(e)[:2000])
        elapsed = round(time.time() - start, 2)

        entry = {
            "template": template_path,
            "scope": scope,
            "status": status,
            "elapsed_s": elapsed,
            "evidence": evidence,
            "raw": resp,
        }
        results.append(entry)
        marker = "OK" if status == "OK" else ("FAIL" if status == "FAIL" else "ERROR")
        print(f"[{idx}/{len(catalog)}] {template_path:<60} {marker} ({elapsed}s)")

        # incremental save
        results_path.write_text(json.dumps({"results": results}, indent=2))

    client.stop()

    # final summary
    ok = [r for r in results if r["status"] == "OK"]
    fail = [r for r in results if r["status"] in ("FAIL", "ERROR")]
    print(f"\n[audit] DONE — OK: {len(ok)}, FAIL/ERROR: {len(fail)}, total: {len(results)}")


if __name__ == "__main__":
    main()
