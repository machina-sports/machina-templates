"""CLI: run the harness, then regenerate or verify the checked-in reports.

    python3 -m tools.iptc                 regenerate docs/iptc/* (the baseline report)
    python3 -m tools.iptc --check         fail if the checked-in reports are stale
    python3 -m tools.iptc --verify-pin    verify vendored bytes against upstream-commit.json
    python3 -m tools.iptc --only api      run a subset, print to stdout, write nothing

``--check`` is the CI gate. It deliberately does NOT require the baseline to
conform: the baseline is expected to fail, and what CI asserts is that the
recorded failure report is still exactly reproducible.

For a single document rather than the whole baseline, use the focused commands:
``validate_graph.py``, ``validate_terms.py``, ``validate_vocabularies.py``.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys

from .report import (
    REPO_ROOT,
    build_report,
    expected_artifacts,
    load_provenance,
    resolve,
    write_reports,
)
from .validate import validate_document

SECTIONS = ("conforming", "baseline", "negative")


def run(only: str | None = None) -> dict:
    provenance = load_provenance()
    results: dict[str, list] = {}
    for section in SECTIONS:
        entries = [e for e in provenance[section] if not only or only in e["fixture"]]
        results[section] = [
            validate_document(resolve(entry), entry["fixture"], repo_root=REPO_ROOT)
            for entry in entries
        ]
    return results


def verify_pin() -> int:
    """Confirm the vendored upstream bytes still match the recorded hashes.

    Separate from --check because they fail for different reasons and want
    different fixes. A hash mismatch means someone edited a vendored upstream file
    and every conformance claim in the audit is void until that is resolved; a
    stale report just needs regenerating.
    """
    from .context import check_context_against_reference
    from .reference import (
        PIN_MANIFEST_PATH,
        ReferenceIntegrityError,
        UPSTREAM_COMMIT,
        load_reference,
        verify_manifest,
    )

    try:
        checked = verify_manifest()
    except ReferenceIntegrityError as exc:
        print(f"PIN VERIFICATION FAILED: {exc}", file=sys.stderr)
        print(
            "\nA vendored upstream file no longer matches upstream-commit.json. The "
            "vendored bytes are meant to be byte-exact and are never rewritten, so "
            "either the file was edited by mistake or the pin was bumped without "
            "regenerating the manifest. Do not 'fix' this by regenerating the "
            "manifest against the edited bytes.",
            file=sys.stderr,
        )
        return 1

    manifest = json.loads(PIN_MANIFEST_PATH.read_text(encoding="utf-8"))
    reference = load_reference()
    drift = check_context_against_reference()

    print(f"pin              {UPSTREAM_COMMIT}")
    print(f"manifest         {PIN_MANIFEST_PATH.relative_to(REPO_ROOT)}")
    print(f"files verified   {len(checked)} / {manifest['file_count']}")
    print(f"total bytes      {manifest['total_bytes']}")
    print(f"licence          {manifest['license']['spdx_id']}")
    print(f"declared version {manifest['declared_version']['version']}")
    print(f"official terms   {len(reference.classes)} classes, "
          f"{len(reference.properties)} properties")
    print(f"vocab schemes    {len(reference.schemes)}")
    shims = reference.shims_applied
    print(f"shims            {len(shims['unterminated_prefix_directive_repairs'])} "
          f"unterminated @prefix repair(s), "
          f"{shims['orphan_sh_ignoredproperties_dropped']} orphan "
          f"sh:ignoredProperties dropped")
    print(f"context drift    {len(drift)}")
    if drift:
        for finding in drift:
            print(f"  - {json.dumps(finding, sort_keys=True)}", file=sys.stderr)
        print("\nThe shared JSON-LD context disagrees with the pinned artefacts. Its "
              "only claim is that its IRIs were copied from the pin, so this is a "
              "hard failure.", file=sys.stderr)
        return 1
    print("\nPin verified. Vendored bytes are byte-exact and the shared context "
          "matches the pin.")
    return 0


def _diff(label: str, expected: str, actual: str) -> str:
    return "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=f"{label} (checked in)",
            tofile=f"{label} (regenerated)",
            n=2,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m tools.iptc", description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify the checked-in reports are up to date; write nothing")
    parser.add_argument("--verify-pin", action="store_true",
                        help="verify every vendored byte against upstream-commit.json, then exit")
    parser.add_argument("--only", metavar="SUBSTRING",
                        help="run only fixtures whose name contains SUBSTRING")
    parser.add_argument("--json", action="store_true",
                        help="print the machine-readable report to stdout")
    args = parser.parse_args(argv)

    if args.verify_pin:
        return verify_pin()

    results = run(args.only)
    report = build_report(results)

    if args.only:
        print(json.dumps(report["totals"], indent=2, sort_keys=True))
        for section in SECTIONS:
            for item in results[section]:
                print(f"{'PASS' if item.conforms else 'FAIL'}  {section:11} {item.fixture}")
        return 0

    if args.check:
        # Every generated artefact, from one source of truth, so that --check and a
        # plain regeneration cannot disagree about which files are generated.
        stale = []
        for path, expected in expected_artifacts(report).items():
            label = str(path.relative_to(REPO_ROOT))
            if not path.is_file():
                stale.append(f"{label}: missing")
                continue
            actual = path.read_text(encoding="utf-8")
            if actual != expected:
                stale.append(f"{label}: out of date\n{_diff(label, actual, expected)}")
        if stale:
            print(
                "The checked-in IPTC reports no longer match the harness output.\n\n"
                "This is not a conformance failure — the baseline is EXPECTED to fail "
                "conformance. It means a recorded report is stale. Regenerate and "
                "commit the result:\n\n"
                "    python3 -m tools.iptc\n",
                file=sys.stderr,
            )
            for entry in stale:
                print(entry, file=sys.stderr)
            return 1
        totals = report["totals"]
        print("IPTC baseline and inventory reports are up to date.")
        for section in SECTIONS:
            section_totals = totals[section]
            print(
                f"  {section:11} {section_totals['conforming']}/"
                f"{section_totals['documents']} fully conforming"
            )
        return 0

    written = write_reports(report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for path in written:
            print(f"wrote {path.relative_to(REPO_ROOT)}")
        for section in SECTIONS:
            for item in results[section]:
                print(f"  {'PASS' if item.conforms else 'FAIL'}  {section:11} {item.fixture}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
