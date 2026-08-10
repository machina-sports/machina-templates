#!/usr/bin/env python3
"""Derive a baseline fixture from a checked-in repository artefact.

    # what checked-in IPTC output artefacts exist?
    python3 tools/iptc/extract_mapping_fixture.py --list-artifacts

    # freeze one of them as a fixture
    python3 tools/iptc/extract_mapping_fixture.py \
        --source agent-templates/iptc-mappings/example-sportradar-output.json \
        --fixture sportradar-soccer-event \
        --unwrap sport-schema-event \
        --emitted-by "iptc-sportradar-event-mapping" \
        --coverage "Sportradar soccer event"

    # no artefact exists for this mapping: report the contract instead
    python3 tools/iptc/extract_mapping_fixture.py \
        --mapping connectors/sportradar-nfl/mappings/iptc-sport-event.yml

WHAT THIS TOOL WILL NOT DO
--------------------------
It will not call a provider, read a credential, or invent a provider fact. There
are exactly two ways a fixture can come into existence, and this tool supports the
first and refuses to fake the second:

1. ``--source`` copies a document that is already checked into this repository,
   optionally unwrapping one named envelope key. The result is recorded as
   ``repository-artifact`` and the copy is byte-exact unless ``--unwrap`` is used.

2. ``--mapping`` prints the literal set of keys a mapping expression emits, so an
   operator can hand-author a ``mapping-contract-synthetic`` fixture with
   obviously synthetic values. This tool deliberately does NOT generate that
   fixture: a machine-invented value would be indistinguishable from an observed
   one in the audit, which is precisely the failure mode the audit exists to
   remove. The operator writes the values and owns them.

Either way the tool prints the ``provenance.json`` stanza to paste in. It does not
edit ``provenance.json`` itself, because a fixture with no reviewed provenance is
worse than no fixture.

``--fixture`` takes a slug matching ``[a-z0-9][a-z0-9-]*`` and writes exactly
``tools/iptc/fixtures/baseline/<slug>.json``. The write is atomic, so an
interrupted run cannot leave a half-written fixture that the audit would then
report on as if it were complete.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.iptc.fileio import atomic_write_bytes, atomic_write_text  # noqa: E402
from tools.iptc.reference import REPO_ROOT  # noqa: E402

FIXTURE_DIR = (Path(__file__).resolve().parent / "fixtures" / "baseline").resolve()
PROVENANCE_PATH = Path(__file__).resolve().parent / "fixtures" / "provenance.json"

#: A fixture name is a slug: lowercase ASCII letters, digits and hyphens, starting
#: with a letter or digit. Nothing else — ``--fixture ../../etc/whatever`` would
#: otherwise write wherever the relative path led, and the fixture name is also
#: the key every report, provenance entry and test refers to.
FIXTURE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")

#: A quoted JSON-LD-ish key inside a mapping expression: "sport:foo": / "@id":
_EMITTED_KEY = re.compile(r'"((?:@|[A-Za-z][A-Za-z0-9_-]*:)[A-Za-z0-9_:@-]*|[A-Za-z_][A-Za-z0-9_-]*)"\s*:')

#: Repository directories that may contain checked-in IPTC output artefacts.
ARTIFACT_ROOTS = ("agent-templates", "connectors")


def looks_like_iptc_document(payload) -> bool:
    if isinstance(payload, list):
        return any(looks_like_iptc_document(item) for item in payload)
    if not isinstance(payload, dict):
        return False
    if "@context" in payload or "@graph" in payload:
        return True
    return any(looks_like_iptc_document(value) for value in payload.values())


def list_artifacts() -> list[Path]:
    found = []
    for root in ARTIFACT_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if looks_like_iptc_document(payload):
                found.append(path)
    return found


def emitted_keys(mapping_path: Path) -> dict[str, list[str]]:
    """The literal key set each named mapping output emits.

    The mapping expression is read as text and scanned for quoted keys. It is NOT
    evaluated: the expression language belongs to the Machina workflow engine, not
    to Python, and a local re-implementation would produce output that merely
    resembles production while being presented as production. Reporting the
    literal keys is honest about what it actually knows.

    The YAML is parsed properly rather than line-scanned, because some mappings
    (``connectors/sportradar-mlb/mappings/iptc-sport-event.yml`` for one) store the
    expression as a quoted folded scalar with escaped quotes, where a raw line scan
    finds nothing.
    """
    import yaml

    document = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
    entries = document.get("mappings") or document.get("mapping") or []
    if isinstance(entries, dict):
        entries = [entries]

    blocks: dict[str, list[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or "<unnamed mapping>"
        keys: list[str] = []
        for output_name, expression in (entry.get("outputs") or {}).items():
            for key in _EMITTED_KEY.findall(_as_text(expression)):
                if key not in keys:
                    keys.append(key)
            if not keys:
                keys.append(f"<output {output_name}: no quoted keys>")
        if keys:
            blocks[name] = keys
    return blocks


def _as_text(expression) -> str:
    """Flatten a mapping output expression to searchable text."""
    if isinstance(expression, str):
        return expression
    return json.dumps(expression)


class FixtureNameError(ValueError):
    """The requested fixture name is not a slug, or escapes FIXTURE_DIR."""


def fixture_target(name: str) -> Path:
    """The path a fixture named ``name`` is written to, or raise.

    Two independent checks, because a pattern is only as good as its author: the
    name must be a slug, and the resolved destination must still be a direct child
    of ``FIXTURE_DIR``.
    """
    if not FIXTURE_NAME.match(name):
        raise FixtureNameError(
            f"invalid fixture name {name!r}: use a slug matching "
            f"{FIXTURE_NAME.pattern} (lowercase letters, digits and hyphens), "
            f"for example 'sportradar-soccer-event'"
        )
    target = (FIXTURE_DIR / f"{name}.json").resolve()
    if target.parent != FIXTURE_DIR:
        raise FixtureNameError(
            f"fixture name {name!r} resolves to {target}, which is outside "
            f"{FIXTURE_DIR}"
        )
    return target


def stanza(**fields) -> str:
    return json.dumps({k: v for k, v in fields.items() if v is not None}, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools/iptc/extract_mapping_fixture.py",
                                     description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list-artifacts", action="store_true",
                        help="list checked-in JSON files that look like IPTC output")
    parser.add_argument("--mapping", type=Path,
                        help="report the literal emitted key set of a mapping YAML")
    parser.add_argument("--source", type=Path,
                        help="checked-in artefact to freeze as a fixture")
    parser.add_argument("--fixture",
                        help="fixture name: a [a-z0-9][a-z0-9-]* slug, "
                             "e.g. sportradar-soccer-event")
    parser.add_argument("--unwrap", metavar="KEY",
                        help="unwrap exactly one named envelope key from the source")
    parser.add_argument("--emitted-by", help="mapping name that produces this output")
    parser.add_argument("--coverage", help="which required coverage area this fills")
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing fixture file")
    args = parser.parse_args(argv)

    if args.list_artifacts:
        registered = {
            entry.get("source")
            for entry in json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))["baseline"]
        }
        artifacts = list_artifacts()
        for path in artifacts:
            relative = str(path.relative_to(REPO_ROOT))
            marker = "already used" if relative in registered else "available"
            print(f"{marker:13} {relative}")
        print(f"\n{len(artifacts)} candidate artefact(s). "
              f"'already used' means a baseline fixture already cites it.")
        return 0

    if args.mapping:
        path = args.mapping if args.mapping.is_absolute() else REPO_ROOT / args.mapping
        if not path.is_file():
            raise SystemExit(f"not a file: {args.mapping}")
        blocks = emitted_keys(path)
        if not blocks:
            raise SystemExit(f"no named mapping with emitted keys found in {args.mapping}")
        print(f"# literal emitted keys in {path.relative_to(REPO_ROOT)}")
        for name, keys in blocks.items():
            print(f"\n## {name}  ({len(keys)} distinct key(s))")
            for key in keys:
                print(f"  {key}")
        print(
            "\nNo fixture was written. Hand-author it with obviously synthetic values,"
            "\nsave it under tools/iptc/fixtures/baseline/, and register it in"
            "\nfixtures/provenance.json with class 'mapping-contract-synthetic' and an"
            "\nexplicit `limitation` field. Do not invent provider facts: use 9xxx or"
            "\n'synthetic0...' identifiers and 'Synthetic ...' names."
        )
        return 0

    if not args.source or not args.fixture:
        parser.error("--source and --fixture are both required (or use --list-artifacts / --mapping)")

    source = args.source if args.source.is_absolute() else REPO_ROOT / args.source
    if not source.is_file():
        raise SystemExit(f"not a file: {args.source}")
    try:
        relative_source = str(source.resolve().relative_to(REPO_ROOT))
    except ValueError:
        raise SystemExit(
            "the source must be a file already checked into this repository. "
            "Fixtures are never captured from a live provider call."
        ) from None

    try:
        target = fixture_target(args.fixture)
    except FixtureNameError as exc:
        raise SystemExit(str(exc)) from None
    if target.exists() and not args.force:
        raise SystemExit(f"{target.relative_to(REPO_ROOT)} exists; pass --force to overwrite")

    raw = source.read_bytes()
    if args.unwrap:
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or args.unwrap not in payload:
            raise SystemExit(f"source has no top-level key '{args.unwrap}'")
        if list(payload) != [args.unwrap]:
            raise SystemExit(
                f"source has keys {list(payload)}; --unwrap only accepts a source "
                f"whose ONLY top-level key is the envelope, so that nothing is "
                f"silently discarded"
            )
        atomic_write_text(target, json.dumps(payload[args.unwrap], indent=2) + "\n")
        transformation = f"Unwrapped the single top-level `{args.unwrap}` envelope key. Content otherwise unchanged."
    else:
        atomic_write_bytes(target, raw)
        transformation = "verbatim copy"

    print(f"wrote {target.relative_to(REPO_ROOT)}")
    print("\nAdd this to the `baseline` array in tools/iptc/fixtures/provenance.json:\n")
    print(stanza(
        fixture=args.fixture,
        path=str(target.relative_to(REPO_ROOT)),
        **{"class": "repository-artifact"},
        source=relative_source,
        transformation=transformation,
        emitted_by=args.emitted_by or "TODO: which mapping name and output key",
        coverage=args.coverage or "TODO: which required coverage area",
        consumers=["TODO: grep the repository for readers of these field paths"],
    ))
    print("\nThen regenerate the audit:  python3 -m tools.iptc")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
