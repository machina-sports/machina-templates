#!/usr/bin/env python3
"""Term validation against the pinned official ontologies.

Answers two questions that the official SHACL shapes cannot:

* which ``sport:``-prefixed terms in this document are **not** declared by IPTC
  Sport Schema 1.1 (gate 1, "unknown ``sport:`` terms must be 0");
* which of those are provider field names that leaked into an official IPTC
  namespace (gate 4), attributed per provider via
  ``tools/iptc/rules/provider-leak-terms.json``.

    python3 tools/iptc/validate_terms.py <document.json> [more.json ...]
    python3 tools/iptc/validate_terms.py --all
    python3 tools/iptc/validate_terms.py --all --json

Exit status is 1 if either gate is non-zero on any document.

Gates 1 and 4 overlap on purpose: a provider field name under ``sport:`` is both
an undeclared term and an attributable leak, and it is counted once in each
column because the two columns answer different questions. Never add the two
numbers together.

A thin wrapper over :mod:`tools.iptc.profile`. It adds no detection logic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.iptc.cli_support import add_common_arguments, iter_targets  # noqa: E402
from tools.iptc.reference import OFFICIAL_MAIN_NS, REPO_ROOT, TARGET_VERSION, load_reference  # noqa: E402
from tools.iptc.validate import validate_document  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools/iptc/validate_terms.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_arguments(parser)
    parser.add_argument("--list-official-terms", action="store_true",
                        help="print every term the pinned ontologies declare, then exit")
    args = parser.parse_args(argv)

    if args.list_official_terms:
        reference = load_reference()
        print(f"# IPTC Sport Schema {TARGET_VERSION} declared terms in {OFFICIAL_MAIN_NS}")
        for name in sorted(reference.main_local_names()):
            print(name)
        return 0

    failed = 0
    payload = []
    for label, path in iter_targets(args):
        result = validate_document(path, label, repo_root=REPO_ROOT)
        detail = result.layers.get("counter_detail") or {}
        unknown = detail.get("unknown_sport_terms") or []
        leaks = detail.get("provider_properties_in_iptc_namespace") or []
        unknown_count = result.counters.get("unknown_sport_terms")
        leak_count = result.counters.get("provider_properties_in_iptc_namespace")
        ok = unknown_count == 0 and leak_count == 0
        failed += 0 if ok else 1

        if args.json:
            payload.append({
                "fixture": label,
                "path": result.path,
                "ok": ok,
                "unknown_sport_terms": unknown_count,
                "unknown_sport_terms_distinct": result.counters.get("unknown_sport_terms_distinct"),
                "provider_properties_in_iptc_namespace": leak_count,
                "unknown_terms": unknown,
                "provider_leaks": leaks,
            })
            continue

        if unknown_count is None:
            print(f"FAIL  {label}: document did not parse; terms could not be counted")
            continue
        print(f"{'PASS' if ok else 'FAIL'}  {label}: "
              f"{unknown_count} unknown sport: occurrence(s) of "
              f"{result.counters.get('unknown_sport_terms_distinct')} distinct term(s), "
              f"{leak_count} provider leak(s)")
        if args.verbose:
            for term in unknown:
                print(f"    - {term['term']} x{term['occurrences']}")
        elif unknown:
            print("    " + ", ".join(f"{t['term']}x{t['occurrences']}" for t in unknown))
        attribution: dict[str, set[str]] = {}
        for leak in leaks:
            for provider in leak["providers"]:
                attribution.setdefault(provider, set()).add(leak["term"])
        for provider, terms in sorted(attribution.items()):
            print(f"    leak {provider}: " + ", ".join(sorted(terms)))

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
