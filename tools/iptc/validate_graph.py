#!/usr/bin/env python3
"""Layers 1 + 2 + 3: JSON-LD/RDF parse, official pinned SHACL, Machina profile.

    python3 tools/iptc/validate_graph.py <document.json> [more.json ...]
    python3 tools/iptc/validate_graph.py --all
    python3 tools/iptc/validate_graph.py --all --json
    python3 tools/iptc/validate_graph.py --consumer-tier production <envelope.json>

A canonical envelope (RFC 002 §9) is a valid input: its inner
``sport_schema_graph`` goes through the same layers, and the envelope also gets a
``rights_gate`` result answering whether ``--consumer-tier`` may consume it.

Exit status is 1 if any document fails any of the three layers, or if the rights
gate refuses an envelope for the named tier. This is the command to reach for
when asking "is this one graph conformant?"; the baseline report is produced by
``python3 -m tools.iptc`` instead.

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
from tools.iptc.validate import (  # noqa: E402
    CONSUMER_TIERS,
    RIGHTS_LAYER,
    rights_findings,
    validate_document,
)

LAYERS = ("jsonld_parse", "official_shacl", "machina_profile")

#: ``rights_findings`` is re-exported, not defined here: RFC 002 §9 names it
#: ``validate_graph.rights_findings`` and callers import it by that path, but the
#: gate itself lives in ``tools/iptc/canonical/rights.py`` — it is vendored into
#: ``sports-skills``, so a consumer that cannot import this repository runs the
#: same rule rather than a second copy of it (RFC 002 §10). This file adds no
#: validation logic.
__all__ = ["CONSUMER_TIERS", "DEFAULT_CONSUMER_TIER", "LAYERS", "build_parser",
           "main", "rights_findings"]

#: The tier the CLI assumes when none is given. ``prototype`` keeps this command's
#: verdict over the checked-in fixtures unchanged — every one of them predates the
#: gate — while :func:`rights_findings` itself defaults to ``production``, because
#: a library gate whose default is permissive is a gate nobody notices is off.
DEFAULT_CONSUMER_TIER = "prototype"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tools/iptc/validate_graph.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_arguments(parser)
    parser.add_argument(
        "--consumer-tier", choices=CONSUMER_TIERS, default=DEFAULT_CONSUMER_TIER,
        help="Rights tier canonical envelopes are gated against (default: "
             "%(default)s). A refused envelope fails the run. Applies only to "
             "files carrying a machina_sports_schema envelope; graph documents "
             "carry no rights claim and are unaffected.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    failed = 0
    payload = []
    for label, path in iter_targets(args):
        result = validate_document(path, label, repo_root=REPO_ROOT,
                                   consumer_tier=args.consumer_tier)
        # None for a graph document, which carries no rights claim to judge.
        rights = result.layers.get(RIGHTS_LAYER)
        ok = (all(result.layers[layer]["ok"] for layer in LAYERS)
              and (rights is None or rights["ok"]))
        failed += 0 if ok else 1
        if args.json:
            payload.append({
                "fixture": label,
                "path": result.path,
                "ok": ok,
                "layers": {layer: result.layers[layer] for layer in LAYERS},
                RIGHTS_LAYER: rights,
            })
            continue
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
        for layer in LAYERS:
            print_layer(result, layer, verbose=args.verbose)
        if rights is None:
            print(f"    --   {RIGHTS_LAYER}: not applicable — a graph document "
                  f"carries no rights claim; rights live in the canonical envelope")
        else:
            print_layer(result, RIGHTS_LAYER, verbose=args.verbose)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
