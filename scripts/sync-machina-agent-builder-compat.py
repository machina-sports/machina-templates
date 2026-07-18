#!/usr/bin/env python3
"""Generate deprecated mkn-constructor aliases from machina-agent-builder."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "skills" / "machina-agent-builder"
LEGACY = (ROOT / "skills" / "mkn-constructor", ROOT / "mkn-constructor")


class TreeSafetyError(RuntimeError):
    """A compatibility tree contains a symlink that must not be followed."""


def checked_entries(path: Path, label: str):
    if path.is_symlink():
        raise TreeSafetyError(f"{label} root must not be a symlink: {path}")
    if not path.is_dir():
        return []
    entries = sorted(path.rglob("*"))
    for item in entries:
        if item.is_symlink():
            raise TreeSafetyError(f"{label} tree contains symlink: {item}")
    return entries


def transform(relative: Path, content: bytes) -> bytes:
    if relative.suffix not in {".md", ".yml", ".yaml"}:
        return content
    text = content.decode()
    text = text.replace("machina-agent-builder-check-setup", "mkn-constructor-check-setup")
    text = text.replace("skills/machina-agent-builder", "skills/mkn-constructor")
    text = text.replace("skill:machina-agent-builder", "skill:mkn-constructor")
    text = text.replace("labels=machina-agent-builder", "labels=mkn-constructor")
    text = text.replace("`machina-agent-builder`", "`mkn-constructor`")
    if relative == Path("SKILL.md"):
        text = text.replace("name: machina-agent-builder", "name: mkn-constructor", 1)
        marker = "# Machina Agent Builder\n"
        notice = (
            "# Machina Agent Builder (Deprecated Alias)\n\n"
            "> **Deprecated:** `mkn-constructor` is a compatibility alias. "
            "Use `machina-agent-builder` for all new work.\n"
        )
        text = text.replace(marker, notice, 1)
    elif relative == Path("skill.yml"):
        text = text.replace('name: "machina-agent-builder"', 'name: "mkn-constructor"', 1)
        text = text.replace('title: "Machina Agent Builder"', 'title: "Machina Agent Builder (Deprecated Alias)"', 1)
        text = text.replace(
            '  description: "',
            '  description: "Deprecated compatibility alias for machina-agent-builder. ',
            1,
        )
        text = text.replace('skill: "machina-agent-builder"', 'skill: "mkn-constructor"')
    elif relative == Path("_install.yml"):
        text = text.replace('title: "Machina Agent Builder"', 'title: "Machina Agent Builder (Deprecated Alias)"', 1)
        text = text.replace(
            '  description: "',
            '  description: "Deprecated compatibility alias for machina-agent-builder. ',
            1,
        )
    return text.encode()


def build(destination: Path) -> None:
    for source in checked_entries(CANONICAL, "canonical"):
        relative = source.relative_to(CANONICAL)
        target = destination / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(transform(relative, source.read_bytes()))


def snapshot(path: Path) -> dict[str, bytes]:
    entries = checked_entries(path, "snapshot")
    if not entries:
        return {}
    return {
        str(item.relative_to(path)): item.read_bytes()
        for item in entries
        if item.is_file()
    }


def transactional_replace(
    expected: Path,
    destinations: tuple[Path, ...],
    *,
    replace=Path.replace,
    copytree=shutil.copytree,
    remove_tree=shutil.rmtree,
) -> list[str]:
    """Replace all destinations as one transaction; return cleanup warnings."""
    records = []
    try:
        # Fully construct every candidate before retaining/moving either original.
        for destination in destinations:
            destination.parent.mkdir(parents=True, exist_ok=True)
            staged = None
            backup = None
            try:
                staged = Path(tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent))
                remove_tree(staged)
                copytree(expected, staged)
                backup = Path(tempfile.mkdtemp(prefix=f".{destination.name}.backup-", dir=destination.parent))
                remove_tree(backup)
            except BaseException:
                # Preparation can fail before this destination has a rollback
                # record. Remove any unique paths created during that window.
                for temporary_path in (staged, backup):
                    if temporary_path is not None and temporary_path.exists():
                        try:
                            remove_tree(temporary_path)
                        except BaseException:
                            pass
                raise
            records.append({"destination": destination, "staged": staged, "backup": backup,
                            "existed": destination.exists(), "original_moved": False, "swapped": False})

        for record in records:
            if record["existed"]:
                replace(record["destination"], record["backup"])
                record["original_moved"] = True
            replace(record["staged"], record["destination"])
            record["swapped"] = True

        expected_snapshot = snapshot(expected)
        for record in records:
            if snapshot(record["destination"]) != expected_snapshot:
                raise RuntimeError(f"post-swap byte parity failed: {record['destination']}")
        if any(snapshot(item["destination"]) != snapshot(records[0]["destination"])
               for item in records[1:]):
            raise RuntimeError("post-swap aliases are not byte-identical")
    except BaseException as transaction_error:
        # Reverse order handles a destination whose original was moved but whose new
        # tree was not installed. Initially absent destinations are removed again.
        restore_errors = []
        for record in reversed(records):
            destination, backup = record["destination"], record["backup"]
            try:
                if record["swapped"] and destination.exists():
                    remove_tree(destination)
                if record["original_moved"] and backup.exists():
                    replace(backup, destination)
            except BaseException as exc:
                restore_errors.append(exc)
        for record in records:
            if record["staged"].exists():
                try:
                    remove_tree(record["staged"])
                except BaseException:
                    pass
        if restore_errors:
            details = "; ".join(
                f"{type(exc).__name__}: {exc}" for exc in restore_errors
            )
            raise RuntimeError(
                f"compatibility transaction failed and {len(restore_errors)} "
                f"rollback operation(s) failed: {details}"
            ) from transaction_error
        raise

    # Commit is the successful two-tree parity check. Backup cleanup cannot undo it.
    warnings = []
    for record in records:
        backup = record["backup"]
        if backup.exists():
            try:
                remove_tree(backup)
            except BaseException as exc:
                warnings.append(f"could not remove committed backup {backup}: {exc}")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if aliases need regeneration")
    args = parser.parse_args()
    if CANONICAL.is_symlink():
        print(f"error: canonical root must not be a symlink: {CANONICAL.relative_to(ROOT)}", file=sys.stderr)
        return 1
    if not CANONICAL.is_dir():
        print(f"error: canonical tree missing: {CANONICAL.relative_to(ROOT)}", file=sys.stderr)
        return 1
    try:
        with tempfile.TemporaryDirectory() as temporary:
            expected = Path(temporary) / "alias"
            build(expected)
            if args.check:
                failures = [path for path in LEGACY if snapshot(path) != snapshot(expected)]
                if failures:
                    for path in failures:
                        print(f"error: compatibility tree is stale: {path.relative_to(ROOT)}", file=sys.stderr)
                    print("run: python3 scripts/sync-machina-agent-builder-compat.py", file=sys.stderr)
                    return 1
                print("machina-agent-builder compatibility trees are current")
                return 0
            warnings = transactional_replace(expected, LEGACY)
            for warning in warnings:
                print(f"warning: {warning}", file=sys.stderr)
    except (OSError, UnicodeError, TreeSafetyError) as exc:
        print(f"error: compatibility sync failed safely: {exc}", file=sys.stderr)
        return 1
    print("generated skills/mkn-constructor and mkn-constructor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
