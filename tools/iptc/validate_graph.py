#!/usr/bin/env python3
"""Layers 1 + 2 + 3: JSON-LD/RDF parse, official pinned SHACL, Machina profile.

    python3 tools/iptc/validate_graph.py <document.json> [more.json ...]
    python3 tools/iptc/validate_graph.py --all
    python3 tools/iptc/validate_graph.py --all --json

Exit status is 1 if any document fails any of the three layers. This is the
command to reach for when asking "is this one graph conformant?"; the baseline
report is produced by ``python3 -m tools.iptc`` instead.

A thin wrapper over :mod:`tools.iptc.validate`. It adds no validation logic — if
this disagrees with the baseline report, that is a bug.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.iptc.cli_support import add_common_arguments, iter_targets, print_layer  # noqa: E402
from tools.iptc.reference import REPO_ROOT  # noqa: E402
from tools.iptc.validate import validate_document  # noqa: E402

LAYERS = ("jsonld_parse", "official_shacl", "machina_profile")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools/iptc/validate_graph.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_arguments(parser)
    args = parser.parse_args(argv)

    failed = 0
    payload = []
    for label, path in iter_targets(args):
        result = validate_document(path, label, repo_root=REPO_ROOT)
        ok = all(result.layers[layer]["ok"] for layer in LAYERS)
        failed += 0 if ok else 1
        if args.json:
            payload.append({
                "fixture": label,
                "path": result.path,
                "ok": ok,
                "layers": {layer: result.layers[layer] for layer in LAYERS},
            })
            continue
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
        for layer in LAYERS:
            print_layer(result, layer, verbose=args.verbose)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
