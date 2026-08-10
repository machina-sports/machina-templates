#!/usr/bin/env python3
"""Layer 4: controlled-vocabulary validation against the pinned TTL files.

    python3 tools/iptc/validate_vocabularies.py <document.json> [more.json ...]
    python3 tools/iptc/validate_vocabularies.py --all
    python3 tools/iptc/validate_vocabularies.py --list-schemes

Three outcomes, kept as three because they need different fixes:

* **valid** — the code is a ``skos:Concept`` in the pinned scheme.
* **invalid** — the scheme is pinned and does not contain the code. Gate 2.
* **unverifiable** — upstream names the scheme but ships no TTL for it at the
  pinned commit (``spsocaction``, ``spsocrole``, ``spesaction``, ...). This is
  missing evidence and is NEVER promoted to valid, and never counted as invalid.

A value that uses a prefix no ``@context`` in scope binds is also counted as
invalid, because it cannot resolve to a NewsCode at all.

**This command fails closed.** Exit status is 1 if any value is invalid, uses an
undeclared prefix, OR is unverifiable. The profile requires every NewsCode to be
provably present in a pinned vocabulary, so a value nothing can check does not
pass — missing evidence is not evidence of correctness. The three categories and
their counts stay separate in the output regardless.

A thin wrapper over :mod:`tools.iptc.validate`. It adds no validation logic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.iptc.cli_support import add_common_arguments, iter_targets, print_layer  # noqa: E402
from tools.iptc.reference import REPO_ROOT, load_reference  # noqa: E402
from tools.iptc.validate import validate_document  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools/iptc/validate_vocabularies.py",
                                     description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_arguments(parser)
    parser.add_argument("--list-schemes", action="store_true",
                        help="print every pinned concept scheme and its size, then exit")
    args = parser.parse_args(argv)

    if args.list_schemes:
        reference = load_reference()
        for scheme_iri, scheme in sorted(reference.schemes.items()):
            print(f"{len(scheme.concepts):6}  {scheme_iri}  ({scheme.source})")
        print(f"\n{len(reference.schemes)} pinned scheme(s).")
        print("Schemes named by the pinned SHACL but NOT shipped upstream at this "
              "commit cannot be validated offline; values in them are reported as "
              "unverifiable and FAIL, because provable membership is the "
              "requirement. See the reference directory's UPSTREAM.md, 'Known gap'.")
        return 0

    failed = 0
    payload = []
    for label, path in iter_targets(args):
        result = validate_document(path, label, repo_root=REPO_ROOT)
        detail = result.layers["controlled_vocabulary"]["detail"]
        invalid_count = result.counters.get("invalid_newscode_values")
        # The layer's own verdict, so this wrapper cannot drift from the harness:
        # it already fails closed on unverifiable values.
        ok = bool(result.layers["controlled_vocabulary"]["ok"])
        failed += 0 if ok else 1

        if args.json:
            payload.append({
                "fixture": label,
                "path": result.path,
                "ok": ok,
                "invalid_newscode_values": invalid_count,
                "unverifiable_newscode_values": result.counters.get("unverifiable_newscode_values"),
                "detail": detail,
            })
            continue

        print(f"{'PASS' if ok else 'FAIL'}  {label}")
        print_layer(result, "controlled_vocabulary", verbose=args.verbose)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
