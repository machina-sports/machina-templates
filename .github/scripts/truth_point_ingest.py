#!/usr/bin/env python3
"""Walk the templates repo, build one payload per component, POST to Truth Point.

A "component" is any directory containing an `_install.yml`. The directory's
parent (e.g. `agent-templates`, `connectors`, `skills`) becomes the `kind`.

Triggered from .github/workflows/truth-point-ingest.yml — accepts an optional
list of changed paths so PR runs only re-ingest the affected components.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml


COMPONENT_ROOTS = ("agent-templates", "connectors", "skills")
MAX_FILE_BYTES = 256 * 1024  # 256 KiB per file — anything larger is summarized
RETRIES = 3
BACKOFF_SEC = 2


def find_components(root: Path) -> list[Path]:
    out: list[Path] = []
    for top in COMPONENT_ROOTS:
        base = root / top
        if not base.is_dir():
            continue
        for install in base.glob("*/_install.yml"):
            out.append(install.parent)
    return sorted(out)


def filter_by_changed(components: list[Path], changed: list[str], root: Path) -> list[Path]:
    if not changed:
        return components
    rels = []
    for comp in components:
        rel = comp.relative_to(root).as_posix() + "/"
        if any(c.startswith(rel) for c in changed):
            rels.append(comp)
    return rels


def read_text_safe(path: Path) -> tuple[str, bool]:
    """Return (content, truncated). Skip binaries; truncate huge files."""
    try:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            with path.open("rb") as f:
                head = f.read(MAX_FILE_BYTES)
            try:
                return head.decode("utf-8"), True
            except UnicodeDecodeError:
                return "", True
        return path.read_text(encoding="utf-8"), False
    except (UnicodeDecodeError, OSError):
        return "", False


def collect_files(component: Path) -> list[dict]:
    files: list[dict] = []
    for f in sorted(component.rglob("*")):
        if not f.is_file():
            continue
        if f.name.startswith(".") or "__pycache__" in f.parts:
            continue
        if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".zip", ".pdf", ".mp3", ".mp4", ".wav"}:
            continue
        content, truncated = read_text_safe(f)
        files.append(
            {
                "path": f.relative_to(component).as_posix(),
                "content": content,
                "truncated": truncated,
                "size": f.stat().st_size,
            }
        )
    return files


def build_payload(component: Path, kind: str, repo: str, ref: str) -> dict:
    install_path = component / "_install.yml"
    install_raw = install_path.read_text(encoding="utf-8")
    install = yaml.safe_load(install_raw) or {}
    setup = install.get("setup", {}) or {}

    categories = setup.get("category") or []
    if isinstance(categories, str):
        categories = [categories]

    return {
        "kind": kind,                                # agent-template | connector | skill
        "name": component.name,                      # dir name
        "source_repo": repo,                         # machina-sports/machina-templates
        "source_path": component.relative_to(component.parent.parent).as_posix(),
        "source_ref": ref,                           # commit SHA
        "version": setup.get("version", ""),
        "title": setup.get("title", ""),
        "description": setup.get("description", ""),
        "categories": categories,
        "integrations": setup.get("integrations", []) or [],
        "status": setup.get("status", ""),
        "value": setup.get("value", ""),
        "manifest": install_raw,                     # raw _install.yml
        "manifest_parsed": install,
        "files": collect_files(component),
    }


def post(endpoint: str, token: str, payload: dict, timeout: int = 60) -> tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Api-Token": token,
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def post_with_retry(endpoint: str, token: str, payload: dict) -> tuple[bool, str]:
    last_err = ""
    for attempt in range(1, RETRIES + 1):
        try:
            status, text = post(endpoint, token, payload)
            if 200 <= status < 300:
                return True, f"http {status}"
            last_err = f"http {status}: {text[:200]}"
            if 400 <= status < 500 and status not in (408, 429):
                return False, last_err  # don't retry client errors except 408/429
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            last_err = f"HTTPError {e.code}: {body}"
            if 400 <= e.code < 500 and e.code not in (408, 429):
                return False, last_err
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = f"{type(e).__name__}: {e}"
        if attempt < RETRIES:
            time.sleep(BACKOFF_SEC * attempt)
    return False, last_err


def parse_changed(path: str | None) -> list[str]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    return [line.strip() for line in p.read_text().splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repo root")
    parser.add_argument("--endpoint", default=os.environ.get("TRUTH_POINT_INGEST_URL", ""))
    parser.add_argument("--token", default=os.environ.get("TRUTH_POINT_API_TOKEN", ""))
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "machina-sports/machina-templates"))
    parser.add_argument("--ref", default=os.environ.get("GITHUB_SHA", "HEAD"))
    parser.add_argument("--changed-paths", default="", help="Optional file with changed paths (one per line)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Fail loud on any per-component error")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    components = find_components(root)
    if not components:
        print("no components found")
        return 0

    changed = parse_changed(args.changed_paths)
    targeted = filter_by_changed(components, changed, root) if changed else components

    print(f"components total={len(components)}  targeted={len(targeted)}  changed_paths={len(changed)}")
    if not targeted:
        print("nothing to ingest")
        return 0

    if not args.dry_run:
        if not args.endpoint or not args.token:
            print("WARN: TRUTH_POINT_INGEST_URL or TRUTH_POINT_API_TOKEN missing — skipping (dry-run mode)")
            args.dry_run = True

    successes = 0
    failures: list[tuple[str, str]] = []
    for comp in targeted:
        kind = comp.parent.name.rstrip("s")  # agent-templates → agent-template
        if comp.parent.name == "skills":
            kind = "skill"
        elif comp.parent.name == "connectors":
            kind = "connector"
        elif comp.parent.name == "agent-templates":
            kind = "agent-template"

        try:
            payload = build_payload(comp, kind, args.repo, args.ref)
        except Exception as e:
            failures.append((comp.name, f"build_payload: {type(e).__name__}: {e}"))
            print(f"  SKIP {comp.name} (build error: {e})")
            continue

        if args.dry_run:
            print(f"  DRY {kind}/{comp.name}  files={len(payload['files'])}  size={sum(len(f.get('content', '')) for f in payload['files'])}B")
            successes += 1
            continue

        ok, msg = post_with_retry(args.endpoint, args.token, payload)
        if ok:
            successes += 1
            print(f"  OK  {kind}/{comp.name}  {msg}")
        else:
            failures.append((comp.name, msg))
            print(f"  ERR {kind}/{comp.name}  {msg}")

    print(f"summary: ok={successes}  failed={len(failures)}")
    if failures:
        for name, err in failures:
            print(f"  - {name}: {err}")
        if args.strict or successes == 0:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
