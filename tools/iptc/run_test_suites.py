#!/usr/bin/env python3
"""Run every IPTC suite the manifest registers, and refuse to run a stale one.

    python3 tools/iptc/run_test_suites.py --list      # validate, print, run nothing
    python3 tools/iptc/run_test_suites.py --verbose   # validate, then run all of it

**Why this exists.** CI used to run one suite by name. Every suite added after it
— the canonical serializer, six provider adapters, the cross-provider equivalence
check, the capability matrix, the rights gate, the source-ref credential
regression, the vendored-runtime pin — was green only on the machine of whoever
remembered to run it locally. Registering a suite and running it in CI were two
separate acts and only one of them showed up in review.

So the list of suites is data: ``tools/iptc/test-suites.json``. This file executes
it, and ``tests/test_iptc_test_manifest.py`` holds the list equal to
``tests/test_iptc_*.py`` on disk in both directions.

**Standard library only, and 3.9-parseable.** This is the entry point CI calls,
so it has to work before anything is installed for it to load. In particular it
must not be imported as ``tools.iptc.run_test_suites``: that would execute the
package ``__init__``, which pulls in the harness's third-party dependency tree.
Nothing here reaches a network or reads configuration from the surrounding
process — the manifest is the whole input.

**Each suite is executed as a file, never as a module.** ``tests/`` is a namespace
directory with no ``__init__.py``, so ``-m unittest tests.<module>`` can be
shadowed by an installed distribution that ships a top-level regular ``tests``
package. Running the path cannot be shadowed.

**Validation happens before the first suite starts.** An unregistered suite is a
gap in coverage, and reporting it after twenty minutes of green output would let
it pass for a warning. It exits nonzero, immediately, having run nothing.

**Order is derived, not editorial.** Suites run in manifest order, and the
manifest order is ``groups`` order then path — checked, not trusted. The declared
group order is deliberate: ``manifest`` first, because those two suites are
milliseconds and they are the ones that report a bypass; ``harness`` last, because
it is roughly half the wall clock of the whole run and putting it earlier delays
every cheap failure behind it.

**A timeout is optional and means a ceiling.** It is declared for the suites whose
runtime is dominated by pyshacl, where a shape regression does not fail — it
hangs. The cheap suites carry none on purpose: seventeen invented ceilings would
be seventeen future flakes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

#: Repository root, from this file's location: ``<root>/tools/iptc/<this>``.
DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: The manifest, always at this path under the given root. Deliberately not a
#: command-line argument: a runner that can be pointed at an arbitrary manifest
#: can be pointed at a shorter one.
MANIFEST_RELATIVE = "tools/iptc/test-suites.json"

#: The keys a suite entry may carry. ``group`` and ``timeout_seconds`` are
#: optional; anything else is a typo, and a typo in optional metadata is silently
#: ignored by every reader unless something rejects it.
SUITE_KEYS = frozenset(("path", "group", "timeout_seconds"))

#: Fallback for a manifest that states no pattern. The real manifest states one,
#: and the manifest suite asserts it is this.
DEFAULT_PATTERN = "tests/test_iptc_*.py"


class ManifestError(Exception):
    """The manifest could not be read or parsed at all."""


def load_manifest(repo_root=DEFAULT_REPO_ROOT):
    """The manifest as a dict, or ``ManifestError`` naming the file and the fault.

    A traceback would be a worse failure than the one it describes: the reader is
    a CI log, and "no such file" spelled as a stack trace reads like a bug in the
    runner rather than a missing manifest.
    """
    path = Path(repo_root) / MANIFEST_RELATIVE
    try:
        blob = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ManifestError("cannot read {0}: {1}".format(path, error))
    try:
        return json.loads(blob)
    except ValueError as error:
        raise ManifestError("{0} is not valid JSON: {1}".format(path, error))


def suites_on_disk(pattern, repo_root):
    """Every file the manifest's own pattern finds, repo-root-relative."""
    directory, _, name_glob = pattern.rpartition("/")
    root = Path(repo_root) / directory if directory else Path(repo_root)
    return sorted(path.relative_to(repo_root).as_posix()
                  for path in root.glob(name_glob))


def order_key(entry, groups):
    """A suite's position: declared group order, then path.

    An entry with no group, or one outside ``groups``, sorts after every declared
    group rather than raising — ``manifest_problems`` reports it, and reporting
    two faults beats crashing on the first.
    """
    group = entry.get("group")
    index = groups.index(group) if group in groups else len(groups)
    return (index, entry.get("path") or "")


def manifest_problems(manifest, repo_root=DEFAULT_REPO_ROOT):
    """Everything wrong with ``manifest``, as lines a reader can act on.

    Returns every problem rather than the first: a run that reports one
    unregistered suite per CI round-trip costs one round-trip per suite.
    """
    problems = []
    groups = manifest.get("groups")
    if not isinstance(groups, list) or not groups:
        problems.append("manifest declares no groups")
        groups = []
    suites = manifest.get("suites")
    if not isinstance(suites, list) or not suites:
        problems.append("manifest declares no suites")
        return problems

    listed = []
    for position, entry in enumerate(suites):
        if not isinstance(entry, dict):
            problems.append("suite {0} is not an object: {1!r}".format(
                position, entry))
            continue
        unknown = sorted(set(entry) - SUITE_KEYS)
        for key in unknown:
            problems.append("suite {0} carries an unknown key: {1}".format(
                entry.get("path", position), key))
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            problems.append("suite {0} declares no path".format(position))
            continue
        listed.append(path)
        if not (Path(repo_root) / path).is_file():
            problems.append("registered suite does not exist: {0}".format(path))
        group = entry.get("group")
        if group is not None and group not in groups:
            problems.append("suite {0} claims an undeclared group: {1}".format(
                path, group))
        if "timeout_seconds" in entry:
            timeout = entry["timeout_seconds"]
            if isinstance(timeout, bool) or not isinstance(timeout, int) \
                    or timeout <= 0:
                problems.append(
                    "suite {0} declares a timeout that is not a positive "
                    "whole number of seconds: {1!r}".format(path, timeout))

    for path in sorted(set(path for path in listed if listed.count(path) > 1)):
        problems.append("duplicate suite entry: {0}".format(path))

    expected = [entry.get("path") for entry
                in sorted((e for e in suites if isinstance(e, dict)),
                          key=lambda entry: order_key(entry, groups))]
    if [e.get("path") for e in suites if isinstance(e, dict)] != expected:
        problems.append(
            "suites are out of order; expected group order then path: "
            + ", ".join(str(path) for path in expected))

    pattern = manifest.get("pattern") or DEFAULT_PATTERN
    unregistered = sorted(set(suites_on_disk(pattern, repo_root)) - set(listed))
    for path in unregistered:
        problems.append(
            "suite on disk is not registered, so CI does not run it: {0} "
            "(add it to {1})".format(path, MANIFEST_RELATIVE))
    return problems


def run_suite(entry, repo_root, verbose):
    """Execute one suite as a file, streaming its output. Returns a failure line
    or ``None``.

    Output is inherited rather than captured: a CI runner that swallows a child's
    output makes every failure something to reproduce locally before it can be
    read.
    """
    path = entry["path"]
    command = [sys.executable, path] + (["-v"] if verbose else [])
    timeout = entry.get("timeout_seconds")
    sys.stdout.flush()
    try:
        completed = subprocess.run(command, cwd=str(repo_root), timeout=timeout)
    except subprocess.TimeoutExpired:
        sys.stdout.flush()
        return "{0} timed out after {1}s".format(path, timeout)
    sys.stdout.flush()
    if completed.returncode:
        return "{0} exited {1}".format(path, completed.returncode)
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run every IPTC suite registered in "
                    + MANIFEST_RELATIVE + ".")
    parser.add_argument("--list", action="store_true",
                        help="validate the manifest and print the suites it "
                             "registers, without running any of them")
    parser.add_argument("--verbose", action="store_true",
                        help="pass -v to each suite, so CI logs name each test")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT),
                        help="repository root holding " + MANIFEST_RELATIVE)
    arguments = parser.parse_args(argv)
    repo_root = Path(arguments.repo_root).resolve()

    try:
        manifest = load_manifest(repo_root)
    except ManifestError as error:
        print("manifest error: {0}".format(error), file=sys.stderr)
        return 1

    problems = manifest_problems(manifest, repo_root)
    if problems:
        print("{0} is not a faithful list of the suites on disk:".format(
            MANIFEST_RELATIVE), file=sys.stderr)
        for problem in problems:
            print("  - {0}".format(problem), file=sys.stderr)
        return 1

    suites = manifest["suites"]
    if arguments.list:
        for entry in suites:
            print(entry["path"])
        return 0

    failures = []
    for position, entry in enumerate(suites, start=1):
        print("=== [{0}/{1}] {2} ({3})".format(
            position, len(suites), entry["path"], entry.get("group", "-")))
        failure = run_suite(entry, repo_root, arguments.verbose)
        if failure:
            failures.append(failure)

    print("--- {0} suite(s), {1} passed, {2} failed".format(
        len(suites), len(suites) - len(failures), len(failures)))
    for failure in failures:
        print("FAILED {0}".format(failure))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
