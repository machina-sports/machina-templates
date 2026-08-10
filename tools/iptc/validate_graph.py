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

#: Consumer tiers the rights gate knows. ``prototype`` may consume prototype-only,
#: personal/non-commercial data; ``production`` may not.
CONSUMER_TIERS = ("prototype", "production")

#: The tier the CLI assumes when none is given. ``prototype`` keeps this command's
#: existing output unchanged — every checked-in fixture predates the gate — while
#: :func:`rights_findings` itself defaults to ``production``, because a library
#: gate whose default is permissive is a gate nobody notices is off.
DEFAULT_CONSUMER_TIER = "prototype"


def rights_findings(envelope, consumer_tier: str = "production") -> list[dict]:
    """Why ``consumer_tier`` may not consume ``envelope``. Empty means it may.

    Fails closed on every path that cannot read a licence claim. No rights block
    is not a permissive rights block: it is the absence of a claim, and reading it
    as permission is how prototype-only data reaches a commercial surface.

    One finding, never a cascade. ``prototype_only`` and ``commercial_use: false``
    travel together on every open-data envelope, and reporting both buries the one
    line that names the fix — the same reasoning ``_check_rights`` applies to an
    absent block.
    """
    if consumer_tier not in CONSUMER_TIERS:
        return [{
            "code": "rights-unknown-consumer-tier",
            "consumer_tier": consumer_tier,
            "detail": f"Unknown consumer tier '{consumer_tier}'; expected one of "
                      f"{', '.join(CONSUMER_TIERS)}. Refused rather than read as "
                      f"the permissive tier.",
        }]

    block = envelope.get("machina_sports_schema") if isinstance(envelope, dict) else None
    rights = block.get("rights") if isinstance(block, dict) else None
    if not isinstance(rights, dict) or not all(
        isinstance(rights.get(flag), bool)
        for flag in ("prototype_only", "commercial_use")
    ):
        return [{
            "code": "rights-unreadable",
            "consumer_tier": consumer_tier,
            "detail": "No readable rights block: machina_sports_schema.rights must "
                      "carry boolean prototype_only and commercial_use. An absent "
                      "licence claim is not a permissive one.",
        }]

    if consumer_tier == "prototype":
        return []

    data_class = rights.get("data_class")
    if rights["prototype_only"]:
        return [{
            "code": "rights-prototype-only",
            "consumer_tier": consumer_tier,
            "data_class": data_class,
            "detail": "The envelope is marked prototype_only, so a production "
                      "consumer must refuse it rather than downgrade quietly.",
        }]
    if not rights["commercial_use"]:
        return [{
            "code": "rights-non-commercial",
            "consumer_tier": consumer_tier,
            "data_class": data_class,
            "detail": "The envelope forbids commercial use, so a production "
                      "consumer must refuse it.",
        }]
    return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tools/iptc/validate_graph.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_arguments(parser)
    parser.add_argument(
        "--consumer-tier", choices=CONSUMER_TIERS, default=DEFAULT_CONSUMER_TIER,
        help="Rights tier to report canonical envelopes against (default: "
             "%(default)s). Applies only to files carrying a "
             "machina_sports_schema envelope; graph documents are unaffected.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
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
