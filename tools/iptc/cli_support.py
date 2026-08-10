"""Shared argument handling for the four operator commands.

Kept in one place so ``validate_graph.py``, ``validate_terms.py`` and
``validate_vocabularies.py`` cannot drift apart on which documents they consider
"all", or on how they print a layer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .reference import REPO_ROOT

PROVENANCE_PATH = Path(__file__).resolve().parent / "fixtures" / "provenance.json"
SECTIONS = ("conforming", "corrected", "baseline", "negative")


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("documents", nargs="*", type=Path,
                        help="JSON-LD documents to check")
    parser.add_argument("--all", action="store_true",
                        help="check every fixture registered in fixtures/provenance.json")
    parser.add_argument("--section", choices=SECTIONS, action="append",
                        help="with --all, restrict to one section (repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable results instead of a summary")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="print every finding rather than a per-code tally")


def registered_fixtures(sections: list[str] | None = None) -> list[tuple[str, Path]]:
    provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
    wanted = sections or list(SECTIONS)
    return [
        (entry["fixture"], REPO_ROOT / entry["path"])
        for section in wanted
        for entry in provenance[section]
    ]


def iter_targets(args: argparse.Namespace) -> list[tuple[str, Path]]:
    if args.all:
        return registered_fixtures(args.section)
    if not args.documents:
        raise SystemExit("nothing to check: pass one or more documents, or --all")
    resolved = []
    for path in args.documents:
        target = path if path.is_absolute() else (Path.cwd() / path)
        if not target.is_file():
            raise SystemExit(f"not a file: {path}")
        try:
            label = str(target.resolve().relative_to(REPO_ROOT))
        except ValueError:
            label = str(target)
        resolved.append((label, target.resolve()))
    return resolved


def print_layer(result, layer: str, *, verbose: bool = False) -> None:
    entry = result.layers[layer]
    detail = entry["detail"]
    mark = "ok  " if entry["ok"] else "FAIL"
    if detail.get("skipped"):
        print(f"    {mark} {layer}: {detail['skipped']}")
        return

    if layer == "jsonld_parse":
        if entry["ok"]:
            print(f"    {mark} {layer}: {detail['triples']} triples")
        else:
            print(f"    {mark} {layer}: {detail.get('stage')} — {detail.get('error')}")
        return

    if layer == "official_shacl":
        if detail.get("vacuous"):
            print(f"    {mark} {layer}: VACUOUS — 0 instances of any official IPTC "
                  f"class, so no shape was exercised")
        else:
            print(f"    {mark} {layer}: {detail['result_count']} violation(s) over "
                  f"{detail['official_class_instances']} official-class instance(s)")
        if verbose:
            for item in detail.get("results", []):
                print(f"         - {item.get('constraint', '?').rsplit('#', 1)[-1]} "
                      f"{item.get('focus_node', '?')} {item.get('path', '')}")
        return

    if layer == "machina_profile":
        tally: dict[str, int] = {}
        for finding in detail.get("findings", []):
            tally[finding["code"]] = tally.get(finding["code"], 0) + 1
        print(f"    {mark} {layer}: {detail.get('finding_count', 0)} finding(s)")
        if verbose:
            for finding in detail.get("findings", []):
                print(f"         - {finding['code']} {finding['pointer']}: {finding['detail']}")
        else:
            for code, count in sorted(tally.items()):
                print(f"         - {code} x{count}")
        return

    if layer == "controlled_vocabulary":
        print(f"    {mark} {layer}: {len(detail['valid'])} valid, "
              f"{len(detail['invalid'])} invalid, "
              f"{len(detail['undeclared_prefix'])} unresolvable prefix, "
              f"{len(detail['unverifiable'])} unverifiable")
        for item in detail["invalid"]:
            print(f"         - INVALID {item['value']}")
        for item in detail["undeclared_prefix"]:
            print(f"         - UNRESOLVABLE {item['value']} on {item['property']}")
        # Unverifiable values fail the layer, so they are never hidden behind -v.
        for item in detail["unverifiable"]:
            print(f"         - UNVERIFIABLE {item['value']}"
                  + (f" ({item['reason']})" if verbose else ""))
