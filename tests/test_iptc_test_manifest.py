"""The suite manifest and its runner (PR 2, task A18).

Run from the repository root:

    python3 tests/test_iptc_test_manifest.py -v

Run the file directly, for the same reason as the other IPTC suites: ``tests/``
is a namespace directory with no ``__init__.py``, so ``-m unittest
tests.<module>`` can be shadowed by an installed distribution that ships a
top-level regular ``tests`` package.

**The hole this closes.** Until now CI ran exactly one suite by name:
``tests/test_iptc_validation_harness.py``, hard-coded in the workflow. Every
suite added since — the canonical serializer, six provider adapters, the
cross-provider equivalence check, the capability matrix, the rights gate, the
source-ref credential regression, the vendored-runtime manifest — was green only
on the machine of whoever remembered to run it. Adding a suite and adding it to
CI were two separate acts, and only one of them was visible in review.

So the list of suites is now data (``tools/iptc/test-suites.json``), a stdlib
runner executes all of it (``tools/iptc/run_test_suites.py``), and this file is
the gate that makes the list complete: exact set equality against
``tests/test_iptc_*.py`` on disk, in both directions. A new suite that nobody
registers fails here. **This suite requires itself in the manifest**, so the gate
cannot be removed from CI by the same omission it exists to catch — deleting its
own entry breaks it, and deleting the file breaks set equality.

What is checked, beyond "the manifest exists":

- **Both directions of set equality**, plus no duplicate and no phantom path.
- **The order is derivable**, not editorial: declared group order, then path. A
  reordered manifest is a red test rather than a silent change in what runs first.
- **The validator catches every bypass**, checked against synthetic manifests
  rather than trusted. A validator that cannot report a problem is a validator
  that reports none.
- **The runner's real behaviour** — nonzero on failure, streamed child output,
  the file form rather than the module form, an enforced timeout, validation
  before execution — exercised against temporary manifests, never against this
  repository's own.
- **The runner is stdlib and Python 3.9**, because it is the entry point CI calls
  before anything is installed to import.
- **CI's path filters reach every suite**, so a change to a suite cannot skip the
  workflow that runs it.

The workflow's *commands* are asserted in
``tests/test_iptc_validation_harness.py``, next to the parser that reads run
steps rather than prose. One owner per check.
"""

from __future__ import annotations

import ast
import fnmatch
import importlib.util
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MANIFEST_PATH = REPO_ROOT / "tools/iptc/test-suites.json"
RUNNER_PATH = REPO_ROOT / "tools/iptc/run_test_suites.py"
WORKFLOW_PATH = (REPO_ROOT / ".github/workflows/validate-iptc-sport-schema.yml")

#: The glob that defines "an IPTC suite". Recorded in the manifest too, and the
#: two are compared: a manifest that narrowed its own pattern could exclude a
#: whole family of suites while still passing set equality against it.
SUITE_PATTERN = "tests/test_iptc_*.py"

#: This file, as the manifest spells it. The self-registration gate.
SELF = "tests/test_iptc_test_manifest.py"

#: The remote acceptance suite that runs the canonical/provider contracts
#: against the reviewed wheel from site-packages.
INSTALLED_CONFORMANCE_SUITE = "tests/test_iptc_installed_conformance.py"
INSTALLED_CONFORMANCE_PATH = REPO_ROOT / INSTALLED_CONFORMANCE_SUITE

#: Suites whose registration is called out by name rather than left to set
#: equality. Each one is a gate a consumer or an auditor relies on, and each was
#: outside CI before this task: the two source-fixture contracts, the credential
#: regression, the cross-provider equivalence check and the A17 runtime pin.
SUITES_THIS_TASK_BRINGS_INTO_CI = (
    "tests/test_iptc_api_football_adapter.py",
    "tests/test_iptc_canonical_serializer.py",
    "tests/test_iptc_cross_provider_equivalence.py",
    "tests/test_iptc_source_ref_credentials.py",
    "tests/test_iptc_sports_skills_reference_contract.py",
    "tests/test_iptc_vendored_manifest.py",
)

#: Concrete inputs whose change must not be able to skip this workflow. Asserted
#: against the path filters so a runtime byte, a fixture or a report cannot move
#: without the job that checks it running.
#:
#: THE LAST TWO ARE THE RELEASE PATH, AND THEY WERE THE GAP. Every property of
#: `.github/workflows/publish-machina-sports-canonical.yml` that matters — trusted
#: publishing with no credential of its own, the reviewer-gated environment, no
#: rebuild after approval, the license refusal, the pinned action SHAs — is
#: asserted by `tests/test_iptc_canonical_package.py`, which this workflow runs.
#: Nothing in either filter reached that file, so a change touching only the
#: publish workflow skipped the workflow that checks it: a security regression in
#: the one file that can upload to PyPI could merge with CI green because CI never
#: ran. The reviewed digests are here for the same reason — they are what the proof
#: job and the release job diff against, so an edit to them must run the jobs that
#: read them.
INPUTS_THE_FILTERS_MUST_REACH = (
    "tools/iptc/test-suites.json",
    "tools/iptc/run_test_suites.py",
    "tools/iptc/vendored-manifest.json",
    "tools/iptc/canonical/serialize.py",
    "tools/iptc/fixtures/source/sports-skills-espn-soccer-native.json",
    "tools/iptc/fixtures/corrected/sports-skills-espn-soccer-graph.json",
    "docs/iptc/baseline-audit.json",
    "docs/iptc/BASELINE-AUDIT.md",
    "docs/iptc/machina-sports-canonical-0.3.0.sha256",
    "docs/rfcs/003-canonical-evidence-contract-phase-1.md",
    ".github/workflows/publish-machina-sports-canonical.yml",
    #: THE LICENSE FILES ARE PACKAGE INPUTS. `license-files` in `pyproject.toml`
    #: makes setuptools read all three at build time and write them into the wheel
    #: and the sdist, so editing one changes the released bytes and the reviewed
    #: digests. A change touching only `LICENSES/` or `NOTICE-IPTC.md` that skipped
    #: this workflow would leave the package unproven for that commit — and it is
    #: the attribution the CC-BY-4.0 half of the expression rests on.
    "LICENSES/MIT.txt",
    "LICENSES/CC-BY-4.0.txt",
    "NOTICE-IPTC.md",
    #: `.gitattributes` DECIDES HOW A PACKAGE INPUT IS READ AND CHECKED. It is
    #: what marks the CC BY legal code vendored and exempt from diff and
    #: whitespace checking, so the official trailing blank line survives review
    #: instead of being trimmed into a file that is no longer the licence. Editing
    #: that rule — widening it over the authored licence files, or dropping it —
    #: changes what CI and the pre-commit hook will accept for the packaged bytes,
    #: and must not be a change that skips the workflow proving them.
    ".gitattributes",
)

#: The keys a suite entry may carry. ``group`` and ``timeout_seconds`` are
#: optional; a key outside this set is a typo that would be silently ignored.
SUITE_KEYS = {"path", "group", "timeout_seconds"}


def runner():
    """The runner, loaded from its file rather than as ``tools.iptc.*``.

    This is how CI invokes it, and it matters: importing it as a package member
    would execute ``tools/iptc/__init__.py``, which imports ``rdflib``. The runner
    must work before any of that, so it is loaded the way it actually runs.
    """
    spec = importlib.util.spec_from_file_location("iptc_run_test_suites",
                                                  RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def installed_conformance():
    """Load the installed bootstrap definition without running its outer proof."""
    spec = importlib.util.spec_from_file_location(
        "iptc_installed_conformance_guard_target", INSTALLED_CONFORMANCE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def suite_paths():
    return [entry["path"] for entry in manifest()["suites"]]


def suites_on_disk():
    return sorted(path.relative_to(REPO_ROOT).as_posix()
                  for path in (REPO_ROOT / "tests").glob("test_iptc_*.py"))


def path_filter_blocks():
    """Every ``paths:`` list in the workflow's trigger section.

    Deliberately not a YAML parse: this suite must run with the standard library
    only, and the shape being read is two flat lists of quoted globs.
    """
    blocks = []
    current = None
    for raw in WORKFLOW_PATH.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped == "paths:":
            current = []
            blocks.append(current)
            continue
        if current is None:
            continue
        if stripped.startswith('- "') and stripped.endswith('"'):
            current.append(stripped[3:-1])
        elif stripped and not stripped.startswith("#"):
            current = None
    return blocks


def covered(path: str, globs) -> bool:
    """Whether any filter glob reaches ``path``.

    ``fnmatch`` is not GitHub's matcher — it treats ``**`` as ``*`` and lets
    ``*`` cross a separator — so this is an approximation. It is the *permissive*
    direction, which is the safe one for this assertion: it can only ever fail to
    report a gap if GitHub is stricter than ``fnmatch``, and every glob asserted
    here is a plain prefix wildcard where the two agree.
    """
    return any(fnmatch.fnmatch(path, pattern.replace("**", "*"))
               for pattern in globs)


def write_temp_repository(directory: Path, suites, groups=("only",)):
    """A throwaway repository root with its own manifest, for runner tests.

    The runner is never pointed at this repository's manifest by a test: a test
    that could fail a real suite from inside another suite makes both results
    meaningless.
    """
    (directory / "tools/iptc").mkdir(parents=True, exist_ok=True)
    (directory / "tests").mkdir(parents=True, exist_ok=True)
    document = {
        "manifest_version": manifest()["manifest_version"],
        "runner": "tools/iptc/run_test_suites.py",
        "pattern": SUITE_PATTERN,
        "groups": list(groups),
        "suites": list(suites),
    }
    (directory / "tools/iptc/test-suites.json").write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document


def write_temp_suite(directory: Path, name: str, body: str):
    path = directory / "tests" / name
    path.write_text(body, encoding="utf-8")
    return "tests/{0}".format(name)


PASSING_SUITE = ("import sys\n"
                 "print('temp suite ran as', sys.argv[0])\n")
FAILING_SUITE = ("import sys\n"
                 "print('temp suite failing')\n"
                 "sys.exit(1)\n")
HANGING_SUITE = "import time\ntime.sleep(30)\n"


def run_runner(repo_root: Path, *arguments):
    return subprocess.run(
        [sys.executable, str(RUNNER_PATH), "--repo-root", str(repo_root)]
        + list(arguments),
        capture_output=True, text=True, timeout=120)


class TestTheManifestIsTheCompleteSuiteList(unittest.TestCase):
    """Exact set equality, in both directions. This is the whole gate."""

    def setUp(self):
        self.paths = suite_paths()

    def test_the_manifest_lists_exactly_the_suites_on_disk(self):
        """A suite nobody registered is a suite CI does not run, and the only
        signal today is that it never appears in a log nobody reads."""
        self.assertEqual(sorted(self.paths), suites_on_disk())

    def test_no_suite_is_listed_twice(self):
        """A duplicate runs a suite twice and, worse, hides a missing one behind
        a set comparison that still has the right length."""
        self.assertEqual(len(self.paths), len(set(self.paths)))

    def test_every_listed_path_is_a_file_that_exists(self):
        for path in self.paths:
            with self.subTest(path=path):
                self.assertTrue((REPO_ROOT / path).is_file())

    def test_this_suite_requires_itself(self):
        """The gate cannot be removed by the omission it exists to catch. Drop
        this entry and this test fails; drop the file and set equality fails."""
        self.assertIn(SELF, self.paths)
        self.assertEqual(SELF, Path(__file__).resolve()
                         .relative_to(REPO_ROOT).as_posix())

    def test_the_installed_conformance_suite_is_registered(self):
        self.assertIn(INSTALLED_CONFORMANCE_SUITE, self.paths)
        entry = next((item for item in manifest()["suites"]
                      if item["path"] == INSTALLED_CONFORMANCE_SUITE), None)
        self.assertIsNotNone(entry)
        self.assertGreater(entry.get("timeout_seconds", 0), 120)

    def test_the_suites_this_task_brings_into_ci_are_named_not_inferred(self):
        """Set equality already covers these. Naming them records what was
        outside CI before A18, so a later change that drops one has to argue with
        a list rather than with a glob."""
        for path in SUITES_THIS_TASK_BRINGS_INTO_CI:
            with self.subTest(path=path):
                self.assertIn(path, self.paths)

    def test_the_recorded_pattern_is_the_pattern_this_test_globs(self):
        """A manifest that narrowed its own pattern could drop a whole family of
        suites and still satisfy set equality against itself."""
        self.assertEqual(manifest()["pattern"], SUITE_PATTERN)

    def test_the_manifest_names_the_runner_that_executes_it(self):
        recorded = manifest()["runner"]
        self.assertEqual(recorded, RUNNER_PATH.relative_to(REPO_ROOT).as_posix())
        self.assertTrue((REPO_ROOT / recorded).is_file())

    def test_the_manifest_declares_its_own_version(self):
        self.assertEqual(manifest()["manifest_version"], "iptc-test-suites/1")

    def test_the_manifest_is_checked_in_as_canonical_bytes(self):
        """A generated-looking file with hand-edited whitespace makes every later
        diff unreadable."""
        self.assertEqual(
            MANIFEST_PATH.read_text(encoding="utf-8"),
            json.dumps(manifest(), indent=2, ensure_ascii=False) + "\n")


class TestTheOrderIsDeterministicAndNotEditorial(unittest.TestCase):
    """Execution order is the manifest order, so the manifest order has to be
    derivable from the manifest itself. Otherwise "deterministic" only means
    "whatever the last editor happened to type"."""

    def setUp(self):
        self.manifest = manifest()
        self.groups = self.manifest["groups"]

    def order_key(self, entry):
        group = entry.get("group")
        index = self.groups.index(group) if group in self.groups \
            else len(self.groups)
        return (index, entry["path"])

    def test_the_order_is_declared_group_then_path(self):
        self.assertEqual(
            [entry["path"] for entry in self.manifest["suites"]],
            [entry["path"]
             for entry in sorted(self.manifest["suites"], key=self.order_key)])

    def test_every_group_a_suite_claims_is_declared(self):
        for entry in self.manifest["suites"]:
            with self.subTest(path=entry["path"]):
                self.assertIn(entry.get("group"), self.groups)

    def test_every_declared_group_is_used(self):
        """A group name nothing claims is a category that was renamed halfway."""
        claimed = {entry.get("group") for entry in self.manifest["suites"]}
        self.assertEqual(sorted(claimed), sorted(self.groups))

    def test_the_group_names_are_unique(self):
        self.assertEqual(len(self.groups), len(set(self.groups)))

    def test_the_meta_gates_run_before_the_suites_they_gate(self):
        """The two manifest suites are cheap and they are the ones that report a
        bypass. Running them last means a whole CI run is spent before the
        cheapest and most structural failure is reported."""
        self.assertEqual(self.groups[0], "manifest")
        first = [entry["path"] for entry in self.manifest["suites"]
                 if entry.get("group") == "manifest"]
        self.assertEqual(sorted(first), [SELF,
                                         "tests/test_iptc_vendored_manifest.py"])

    def test_the_slowest_suite_runs_last(self):
        """The installed proof rebuilds, installs and repeats the substantive
        contracts. Ahead of the others it delays every cheap failure behind it."""
        self.assertEqual(self.groups[-1], "installed")
        self.assertEqual(self.manifest["suites"][-1]["path"],
                         INSTALLED_CONFORMANCE_SUITE)


class TestOptionalMetadataIsWellFormed(unittest.TestCase):
    """``group`` and ``timeout_seconds`` are optional. Optional is not the same as
    unchecked: a misspelled key is silently ignored by any reader."""

    def setUp(self):
        self.suites = manifest()["suites"]

    def test_no_suite_entry_carries_an_unknown_key(self):
        for entry in self.suites:
            with self.subTest(path=entry["path"]):
                self.assertEqual(sorted(set(entry) - SUITE_KEYS), [])

    def test_every_entry_has_a_path(self):
        for entry in self.suites:
            with self.subTest(entry=entry):
                self.assertIsInstance(entry.get("path"), str)
                self.assertTrue(entry["path"].startswith("tests/"))

    def test_every_declared_timeout_is_a_positive_whole_number_of_seconds(self):
        for entry in self.suites:
            if "timeout_seconds" not in entry:
                continue
            with self.subTest(path=entry["path"]):
                timeout = entry["timeout_seconds"]
                self.assertIsInstance(timeout, int)
                self.assertNotIsInstance(timeout, bool)
                self.assertGreater(timeout, 0)

    def test_the_harness_suite_declares_a_ceiling(self):
        """The one suite whose runtime is dominated by pyshacl. A shape regression
        there does not fail, it hangs, and a hung job burns a runner until the
        workflow-level limit kills it with no useful output."""
        entry = next(e for e in self.suites
                     if e["path"] == "tests/test_iptc_validation_harness.py")
        self.assertIn("timeout_seconds", entry)
        self.assertGreater(entry["timeout_seconds"], 120)

    def test_a_timeout_is_optional_for_the_cheap_suites(self):
        """Stated as a test so nobody 'completes' the manifest by inventing a
        ceiling for every suite: seventeen invented numbers is seventeen future
        flakes, and the schema allows absence precisely to avoid them."""
        without = [e["path"] for e in self.suites if "timeout_seconds" not in e]
        self.assertTrue(without)


class TestInstalledConformanceBootstrapGuardrails(unittest.TestCase):
    """Executable controls around the installed proof's own controls."""

    def setUp(self):
        self.target = installed_conformance()
        self.temporary = tempfile.TemporaryDirectory(
            prefix="iptc-installed-bootstrap-guard-")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.bootstrap = self.workspace / "installed_conformance_bootstrap.py"
        self.bootstrap.write_text(
            textwrap.dedent(self.target.BOOTSTRAP), encoding="utf-8")

    def run_bootstrap_probe(self, *arguments):
        return subprocess.run(
            [sys.executable, "-I", str(self.bootstrap)] + list(arguments),
            cwd=str(self.workspace), capture_output=True, text=True, timeout=30)

    def test_the_bootstrap_refuses_socket_connection_and_dns_apis(self):
        result = self.run_bootstrap_probe("--probe-network-guard")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("blocked socket.socket", result.stdout)
        self.assertIn("blocked socket.create_connection", result.stdout)
        self.assertIn("blocked socket.getaddrinfo", result.stdout)

    def test_packaged_adapter_mapping_closes_the_staged_source_inventory(self):
        adapters = REPO_ROOT / "tools/iptc/canonical/adapters"
        packaged = {
            path.stem for path in adapters.iterdir()
            if path.is_file() and path.suffix == ".py"
            and path.name != "__init__.py"
        }
        declared = self.target.ADAPTER_CONFORMANCE_SUITES
        self.assertEqual(set(declared), packaged)
        self.assertEqual(len(set(declared.values())), len(declared))
        for module, suite in declared.items():
            with self.subTest(module=module, suite=suite):
                self.assertTrue((REPO_ROOT / suite).is_file())

    def test_adapter_inventory_guard_reports_both_mismatch_directions(self):
        adapters = self.workspace / "adapters"
        adapters.mkdir()
        (adapters / "__init__.py").write_text("", encoding="utf-8")
        (adapters / "covered.py").write_text("", encoding="utf-8")
        (adapters / "installed_only.py").write_text("", encoding="utf-8")
        declared = json.dumps({
            "covered": "tests/test_covered.py",
            "declared_only": "tests/test_declared_only.py",
        })

        result = self.run_bootstrap_probe(
            "--probe-adapter-inventory", str(adapters), declared)

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        output = result.stdout + result.stderr
        self.assertIn(
            "installed adapters without declared conformance suites: "
            "installed_only", output)
        self.assertIn(
            "declared adapter conformance suites absent from installed package: "
            "declared_only", output)

    def test_generator_exclusion_uses_the_passed_class_and_only_that_class(self):
        suite = self.workspace / "synthetic_generator_contract.py"
        suite.write_text(textwrap.dedent("""\
            import unittest


            class KeepContract(unittest.TestCase):
                def test_kept(self):
                    pass


            class SyntheticGeneratorOnly(unittest.TestCase):
                def test_excluded_one(self):
                    pass

                def test_excluded_two(self):
                    pass
            """), encoding="utf-8")

        result = self.run_bootstrap_probe(
            "--probe-generator-exclusion", "SyntheticGeneratorOnly", str(suite))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("selected tests: 1", result.stdout)
        self.assertIn(
            "excluded generator-only class: SyntheticGeneratorOnly (2 tests)",
            result.stdout)

    def test_manifest_timeout_leaves_named_headroom_above_the_child(self):
        entry = next(
            item for item in manifest()["suites"]
            if item["path"] == INSTALLED_CONFORMANCE_SUITE)
        outer = entry["timeout_seconds"]
        self.assertEqual(
            outer,
            self.target.INSTALLED_CONFORMANCE_MANIFEST_TIMEOUT_SECONDS)
        self.assertGreaterEqual(
            outer - self.target.CHILD_CONFORMANCE_TIMEOUT_SECONDS,
            self.target.MINIMUM_SETUP_TIMEOUT_HEADROOM_SECONDS)


class TestTheValidatorCatchesEveryBypass(unittest.TestCase):
    """The runner validates before it runs. Checked against synthetic manifests,
    because a validator trusted to report problems reports none the day it
    breaks."""

    def setUp(self):
        self.runner = runner()
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.directory,
                        ignore_errors=True)
        (self.directory / "tests").mkdir(parents=True, exist_ok=True)
        self.registered = write_temp_suite(self.directory, "test_iptc_one.py",
                                           PASSING_SUITE)

    def problems(self, suites, groups=("only",)):
        document = write_temp_repository(self.directory, suites, groups)
        return self.runner.manifest_problems(document, self.directory)

    def test_a_clean_manifest_reports_nothing(self):
        self.assertEqual(
            self.problems([{"path": self.registered, "group": "only"}]), [])

    def test_a_suite_on_disk_that_is_not_listed_is_reported(self):
        """The bypass this task exists to close."""
        write_temp_suite(self.directory, "test_iptc_two.py", PASSING_SUITE)
        problems = self.problems([{"path": self.registered, "group": "only"}])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("test_iptc_two.py", problems[0])

    def test_a_listed_path_that_does_not_exist_is_reported(self):
        problems = self.problems([{"path": self.registered, "group": "only"},
                                  {"path": "tests/test_iptc_gone.py",
                                   "group": "only"}])
        self.assertTrue(any("test_iptc_gone.py" in problem
                            for problem in problems), problems)

    def test_a_duplicate_entry_is_reported(self):
        problems = self.problems([{"path": self.registered, "group": "only"},
                                  {"path": self.registered, "group": "only"}])
        self.assertTrue(any("duplicate" in problem.lower()
                            for problem in problems), problems)

    def test_an_out_of_order_entry_is_reported(self):
        write_temp_suite(self.directory, "test_iptc_two.py", PASSING_SUITE)
        problems = self.problems([
            {"path": "tests/test_iptc_two.py", "group": "only"},
            {"path": self.registered, "group": "only"},
        ])
        self.assertTrue(any("order" in problem.lower()
                            for problem in problems), problems)

    def test_an_undeclared_group_is_reported(self):
        problems = self.problems(
            [{"path": self.registered, "group": "invented"}])
        self.assertTrue(any("invented" in problem for problem in problems),
                        problems)

    def test_an_unknown_entry_key_is_reported(self):
        problems = self.problems([{"path": self.registered, "group": "only",
                                   "tiemout_seconds": 30}])
        self.assertTrue(any("tiemout_seconds" in problem
                            for problem in problems), problems)

    def test_a_non_positive_timeout_is_reported(self):
        problems = self.problems([{"path": self.registered, "group": "only",
                                   "timeout_seconds": 0}])
        self.assertTrue(any("timeout" in problem.lower()
                            for problem in problems), problems)

    def test_this_repositorys_own_manifest_reports_no_problem(self):
        """The synthetic cases above prove the validator bites. This one proves it
        agrees with the real thing, which is what CI asks it."""
        self.assertEqual(
            self.runner.manifest_problems(manifest(), REPO_ROOT), [])


class TestTheRunnerRunsWhatTheManifestSays(unittest.TestCase):
    """Real subprocesses, temporary manifests. Never this repository's own."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.directory,
                        ignore_errors=True)
        (self.directory / "tests").mkdir(parents=True, exist_ok=True)

    def test_a_manifest_whose_suites_pass_exits_zero(self):
        path = write_temp_suite(self.directory, "test_iptc_one.py",
                                PASSING_SUITE)
        write_temp_repository(self.directory,
                              [{"path": path, "group": "only"}])
        result = run_runner(self.directory)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_failing_suite_makes_the_whole_run_exit_nonzero(self):
        """A runner that reports a failure and exits 0 is worse than no runner:
        the log says FAILED and the job is green."""
        good = write_temp_suite(self.directory, "test_iptc_one.py",
                                PASSING_SUITE)
        bad = write_temp_suite(self.directory, "test_iptc_two.py",
                               FAILING_SUITE)
        write_temp_repository(self.directory, [{"path": good, "group": "only"},
                                               {"path": bad, "group": "only"}])
        result = run_runner(self.directory)
        self.assertEqual(result.returncode, 1)
        self.assertIn("test_iptc_two.py", result.stdout)

    def test_a_later_suite_still_runs_after_an_earlier_one_fails(self):
        """Stopping at the first failure hides every other failure behind a fix
        round-trip, which is how a two-line change becomes four CI runs."""
        bad = write_temp_suite(self.directory, "test_iptc_one.py",
                               FAILING_SUITE)
        good = write_temp_suite(self.directory, "test_iptc_two.py",
                                PASSING_SUITE)
        write_temp_repository(self.directory, [{"path": bad, "group": "only"},
                                               {"path": good, "group": "only"}])
        result = run_runner(self.directory)
        self.assertEqual(result.returncode, 1)
        self.assertIn("temp suite ran as", result.stdout)

    def test_child_output_reaches_the_log_rather_than_being_swallowed(self):
        """A CI runner that captures and discards is a runner whose failures have
        to be reproduced locally before they can be read."""
        path = write_temp_suite(self.directory, "test_iptc_one.py",
                                PASSING_SUITE)
        write_temp_repository(self.directory,
                              [{"path": path, "group": "only"}])
        result = run_runner(self.directory)
        self.assertIn("temp suite ran as", result.stdout)

    def test_each_suite_is_executed_as_a_file_not_as_a_module(self):
        """The reason every IPTC suite is invoked by path: ``tests/`` has no
        ``__init__.py``, so ``-m unittest tests.<module>`` can be shadowed by an
        installed distribution shipping a top-level ``tests`` package. The child
        reports its own ``sys.argv[0]``, so this is read off the process rather
        than off the runner's source."""
        path = write_temp_suite(self.directory, "test_iptc_one.py",
                                PASSING_SUITE)
        write_temp_repository(self.directory,
                              [{"path": path, "group": "only"}])
        result = run_runner(self.directory)
        self.assertIn("ran as {0}".format(path), result.stdout.replace("\\", "/"))

    def test_the_verbose_flag_reaches_the_suite(self):
        """The step this runner replaced ran the harness with ``-v``. Losing the
        per-test names would make a CI failure harder to place, so the flag is
        forwarded rather than dropped."""
        path = write_temp_suite(self.directory, "test_iptc_one.py",
                               "import sys\nprint('argv:', sys.argv[1:])\n")
        write_temp_repository(self.directory,
                              [{"path": path, "group": "only"}])
        self.assertIn("argv: ['-v']", run_runner(self.directory,
                                                 "--verbose").stdout)
        self.assertIn("argv: []", run_runner(self.directory).stdout)

    def test_a_declared_timeout_is_enforced_and_counts_as_a_failure(self):
        path = write_temp_suite(self.directory, "test_iptc_one.py",
                                HANGING_SUITE)
        write_temp_repository(self.directory, [{"path": path, "group": "only",
                                               "timeout_seconds": 1}])
        result = run_runner(self.directory)
        self.assertEqual(result.returncode, 1)
        self.assertIn("timed out", (result.stdout + result.stderr).lower())

    def test_validation_runs_before_any_suite_does(self):
        """An unregistered suite has to fail the run even when every registered
        suite passes — and it has to fail before the slow ones start."""
        registered = write_temp_suite(self.directory, "test_iptc_one.py",
                                      PASSING_SUITE)
        write_temp_suite(self.directory, "test_iptc_two.py", PASSING_SUITE)
        write_temp_repository(self.directory,
                              [{"path": registered, "group": "only"}])
        result = run_runner(self.directory)
        self.assertEqual(result.returncode, 1)
        self.assertIn("test_iptc_two.py", result.stdout + result.stderr)
        self.assertNotIn("temp suite ran as", result.stdout)


class TestListModeIsFastAndValidating(unittest.TestCase):
    """``--list`` is what the workflow runs first: it answers "is every suite
    registered?" in milliseconds, before the install-heavy work behind it."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.directory,
                        ignore_errors=True)
        (self.directory / "tests").mkdir(parents=True, exist_ok=True)

    def test_list_mode_prints_exactly_the_manifest_paths_in_order(self):
        result = run_runner(REPO_ROOT, "--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        printed = [line for line in result.stdout.splitlines()
                   if line.startswith("tests/")]
        self.assertEqual(printed, suite_paths())

    def test_list_mode_runs_no_suite(self):
        """The distinction that makes it a fast check rather than the slow one
        with extra printing."""
        result = run_runner(REPO_ROOT, "--list")
        for marker in ("Ran ", "... ok", "OK"):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, result.stdout)

    def test_list_mode_fails_on_an_unregistered_suite_and_prints_nothing_to_run(self):
        registered = write_temp_suite(self.directory, "test_iptc_one.py",
                                      PASSING_SUITE)
        write_temp_suite(self.directory, "test_iptc_two.py", PASSING_SUITE)
        write_temp_repository(self.directory,
                              [{"path": registered, "group": "only"}])
        result = run_runner(self.directory, "--list")
        self.assertEqual(result.returncode, 1)
        self.assertIn("test_iptc_two.py", result.stdout + result.stderr)

    def test_a_missing_manifest_is_a_clear_failure_not_a_traceback(self):
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, empty, ignore_errors=True)
        result = run_runner(empty, "--list")
        self.assertEqual(result.returncode, 1)
        combined = result.stdout + result.stderr
        self.assertIn("test-suites.json", combined)
        self.assertNotIn("Traceback", combined)


class TestTheRunnerIsTheEntryPointCiCanCall(unittest.TestCase):
    """It runs before anything this repository's requirements install, and it is
    the file that decides whether the rest runs at all."""

    def setUp(self):
        self.source = RUNNER_PATH.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source, filename=RUNNER_PATH.name)

    def test_the_runner_parses_as_python_3_9(self):
        """The same floor the vendored runtime is held to. Not because the runner
        is vendored — it is not — but because the whole IPTC tree is written to
        one syntax level, and a runner that only parses on 3.12 fails with a
        SyntaxError rather than a test result."""
        ast.parse(self.source, feature_version=(3, 9))

    def test_the_runner_imports_only_the_standard_library(self):
        roots = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                roots.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level:
                roots.append((node.module or "").split(".")[0])
        for root in roots:
            with self.subTest(imports=root):
                self.assertIn(root, sys.stdlib_module_names)

    def test_the_runner_imports_nothing_from_this_repository(self):
        """Importing ``tools.iptc`` would execute its ``__init__``, which imports
        rdflib — turning "list the suites" into "install the harness first"."""
        for banned in ("tools", "rdflib", "pyshacl"):
            with self.subTest(imports=banned):
                self.assertNotIn("import {0}".format(banned), self.source)

    def test_the_runner_exposes_the_validator_the_tests_call(self):
        module = runner()
        for name in ("manifest_problems", "load_manifest", "main"):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(module, name)))

    def test_the_runner_never_reaches_the_network_or_the_environment(self):
        """Every other command in this tree holds this line; the one that runs
        them all should not be the exception."""
        for banned in ("urllib", "socket", "requests", "http.client",
                       "os.environ", "getenv"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, self.source)

    def test_the_runner_spawns_this_interpreter_and_nothing_else(self):
        """The substance behind the one waiver this runner holds.

        ``tests/test_iptc_validation_harness.py`` forbids every module under
        ``tools/iptc`` from importing ``subprocess`` — a harness that can shell out
        can reach a network, and an offline conformance result is the guarantee
        that buys. This file is exempted because launching the suites is its whole
        job, so the exemption has to be paid for by showing what it launches.
        Read off the spawned process rather than off the source: the child reports
        the interpreter it is running under.
        """
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, directory,
                        ignore_errors=True)
        (directory / "tests").mkdir(parents=True, exist_ok=True)
        path = write_temp_suite(directory, "test_iptc_one.py",
                                "import sys\nprint('interpreter:', sys.executable)\n")
        write_temp_repository(directory, [{"path": path, "group": "only"}])
        result = run_runner(directory)
        self.assertIn("interpreter: {0}".format(sys.executable), result.stdout)

    def test_the_runner_uses_no_shell_and_no_open_ended_spawn(self):
        """``shell=True`` would turn a manifest entry into a command line, and the
        manifest is checked in as data that only has to be a path."""
        used = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                    and node.value.id == "subprocess":
                used.add(node.attr)
            if isinstance(node, ast.keyword) and node.arg == "shell":
                self.fail("the runner passes shell=")
        self.assertEqual(sorted(used), ["TimeoutExpired", "run"])
        for banned in ("Popen", "os.system", "os.exec", "shell=True"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, self.source)


class TestCiPathFiltersReachEverySuite(unittest.TestCase):
    """A suite whose change skips the workflow that runs it is not gated.

    The workflow's run *commands* are asserted in the harness suite, beside the
    parser that reads steps rather than prose. This class owns the trigger.
    """

    def setUp(self):
        self.blocks = path_filter_blocks()

    def test_the_workflow_declares_two_identical_path_filters(self):
        """``pull_request`` and ``push``. One narrower than the other means the
        gate depends on how the change arrived."""
        self.assertEqual(len(self.blocks), 2)
        self.assertEqual(self.blocks[0], self.blocks[1])

    def test_every_registered_suite_is_reached_by_the_filters(self):
        for path in suite_paths():
            with self.subTest(path=path):
                self.assertTrue(covered(path, self.blocks[0]),
                                "no path filter reaches {0}".format(path))

    def test_the_suite_glob_is_declared_rather_than_one_suite_by_name(self):
        """Before A18 the filter named a single file, so every suite added since
        was outside the trigger as well as outside the run."""
        self.assertIn(SUITE_PATTERN, self.blocks[0])

    def test_the_manifest_the_runner_the_runtime_the_fixtures_and_the_reports_are_reached(self):
        for path in INPUTS_THE_FILTERS_MUST_REACH:
            with self.subTest(path=path):
                self.assertTrue(covered(path, self.blocks[0]),
                                "no path filter reaches {0}".format(path))

    def test_the_workflow_file_itself_is_reached(self):
        self.assertTrue(covered(
            ".github/workflows/validate-iptc-sport-schema.yml", self.blocks[0]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
