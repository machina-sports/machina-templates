"""Run the canonical/provider contracts against the installed reviewed wheel.

This suite deliberately reuses the substantive source-side conformance tests:
their fixtures, expected documents and four-layer validator remain repository
evidence, while a controlled alias makes every ``tools.iptc.canonical*`` import
resolve from the installed ``machina_sports_canonical`` package.  The one
generator-only class is excluded because ``export_official_terms.py`` is not a
runtime member and intentionally does not ship.

The child run starts in a neutral directory under isolated mode.  It prints the
installed root and selected test count, and audits every loaded canonical alias
before and after the run.  Any alias whose origin is under the repository's
``tools/iptc/canonical`` tree makes the proof fail.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import site
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
IMPORT_NAME = "machina_sports_canonical"
ARTIFACT_STEM = "machina_sports_canonical-0.4.0"
RELEASE_HELPER = "packaging/machina_sports_canonical/release.py"
RELEASE_CHECKSUM_PATH = (REPO_ROOT / "docs/iptc/"
                         "machina-sports-canonical-0.4.0.sha256")
RELEASE_SOURCE_DATE_EPOCH = "1786951696"

# The same closed staging set as the package proof.  Building a disposable copy
# avoids setuptools writing egg-info into the checkout.
#
# `LICENSES` and `NOTICE-IPTC.md` are build inputs, not documentation:
# `license-files` in `pyproject.toml` makes setuptools read all three at build
# time, so a staging copy without them does not build the reviewed release and
# the digest comparison below would be measuring a different artefact.
PACKAGING_INPUTS = (
    "pyproject.toml",
    "setup.py",
    "MANIFEST.in",
    "README-machina-sports-canonical.md",
    "LICENSES",
    "NOTICE-IPTC.md",
    "packaging",
    "tools/iptc/canonical",
)

# Exact order is intentional: core contracts first, then cross-cutting contracts.
# The adapter mapping below closes the packaged adapter inventory separately so a
# future installed adapter cannot inherit conformance by being absent from a loose
# suite list.
CORE_CONFORMANCE_SUITES = (
    "tests/test_iptc_canonical_evidence_phase1.py",
    "tests/test_iptc_canonical_runtime_0_4.py",
    "tests/test_iptc_canonical_serializer.py",
    "tests/test_iptc_capability_matrix.py",
    "tests/test_iptc_cli_rights_gate.py",
    "tests/test_iptc_cross_provider_equivalence.py",
    "tests/test_iptc_identity_resolution_method.py",
    "tests/test_iptc_multi_participant_contract.py",
    "tests/test_iptc_source_ref_credentials.py",
    "tests/test_iptc_sports_skills_reference_contract.py",
)

ADAPTER_CONFORMANCE_SUITES = {
    "api_football": "tests/test_iptc_api_football_adapter.py",
    "sportradar_mlb": "tests/test_iptc_sportradar_mlb_adapter.py",
    "sportradar_nfl": "tests/test_iptc_sportradar_nfl_adapter.py",
    "sportradar_soccer": "tests/test_iptc_sportradar_soccer_adapter.py",
    "sportradar_tennis": "tests/test_iptc_sportradar_tennis_adapter.py",
    "stats_perform_opta": "tests/test_iptc_stats_perform_opta_adapter.py",
}

GENERATOR_ONLY_CLASS = "TestOfficialTermExport"
CHILD_CONFORMANCE_TIMEOUT_SECONDS = 600
INSTALLED_CONFORMANCE_MANIFEST_TIMEOUT_SECONDS = 900
MINIMUM_SETUP_TIMEOUT_HEADROOM_SECONDS = 300


BOOTSTRAP = r'''\
from __future__ import annotations

import importlib
import importlib.util
import json
import pkgutil
import socket
import sys
import sysconfig
import types
import unittest
from pathlib import Path


sys.dont_write_bytecode = True


class NetworkAccessBlocked(RuntimeError):
    """The installed conformance proof attempted a forbidden network API."""


def blocked_network_api(name):
    def refuse(*args, **kwargs):
        raise NetworkAccessBlocked(
            "installed conformance forbids network access via {0}".format(name))
    return refuse


class RefusingSocket(socket.socket):
    def __new__(cls, *args, **kwargs):
        raise NetworkAccessBlocked(
            "installed conformance forbids network access via socket.socket")


def install_network_guard():
    guarded = (
        "create_connection",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
        "getnameinfo",
    )
    socket.socket = RefusingSocket
    for name in guarded:
        setattr(socket, name, blocked_network_api("socket." + name))


def probe_network_guard():
    install_network_guard()
    probes = (
        ("socket.socket", lambda: socket.socket(-1)),
        ("socket.create_connection", lambda: socket.create_connection(None)),
        ("socket.getaddrinfo", lambda: socket.getaddrinfo(object(), object())),
    )
    for name, probe in probes:
        try:
            probe()
        except NetworkAccessBlocked as error:
            if name not in str(error):
                raise SystemExit(
                    "network guard raised an unclear exception for {0}: {1}".format(
                        name, error))
            print("blocked {0}".format(name), flush=True)
        except Exception as error:
            raise SystemExit(
                "network guard did not intercept {0}: {1}: {2}".format(
                    name, type(error).__name__, error))
        else:
            raise SystemExit("network guard did not intercept {0}".format(name))
    return 0


def beneath(path, root):
    return path == root or root in path.parents


def canonical_source_resolutions(source_root):
    bad = []
    for name, module in sorted(sys.modules.items()):
        if name != "tools.iptc.canonical" \
                and not name.startswith("tools.iptc.canonical."):
            continue
        locations = []
        origin = getattr(module, "__file__", None)
        if origin:
            locations.append(origin)
        locations.extend(str(item) for item in getattr(module, "__path__", ()))
        for location in locations:
            resolved = Path(location).resolve()
            if beneath(resolved, source_root):
                bad.append("{0} -> {1}".format(name, resolved))
    return bad


def iter_cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            for case in iter_cases(item):
                yield case
        else:
            yield item


def adapter_modules(adapters_root):
    if not adapters_root.is_dir():
        raise SystemExit(
            "installed adapter package is missing: {0}".format(adapters_root))
    return {module.name for module in pkgutil.iter_modules([str(adapters_root)])
            if module.name != "__init__"}


def require_closed_adapter_inventory(adapters_root, declared):
    if not isinstance(declared, dict) or any(
            not isinstance(module, str) or not isinstance(suite, str)
            for module, suite in declared.items()):
        raise SystemExit(
            "declared adapter conformance mapping must contain string pairs")
    installed = adapter_modules(adapters_root)
    declared_modules = set(declared)
    problems = []
    undeclared = sorted(installed - declared_modules)
    absent = sorted(declared_modules - installed)
    if undeclared:
        problems.append(
            "installed adapters without declared conformance suites: " +
            ", ".join(undeclared))
    if absent:
        problems.append(
            "declared adapter conformance suites absent from installed package: " +
            ", ".join(absent))
    if problems:
        raise SystemExit("packaged adapter inventory mismatch:\n" +
                         "\n".join(problems))


def load_selected_suites(suite_paths, generator_only_class):
    selected = unittest.TestSuite()
    excluded_cases = []
    excluded_classes = set()
    discovered_count = 0
    for index, path in enumerate(suite_paths):
        name = "installed_contract_{0:02d}_{1}".format(index, path.stem)
        spec = importlib.util.spec_from_file_location(name, str(path))
        if spec is None or spec.loader is None:
            raise SystemExit("cannot load conformance suite: {0}".format(path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        discovered = unittest.defaultTestLoader.loadTestsFromModule(module)
        for case in iter_cases(discovered):
            discovered_count += 1
            if case.__class__.__name__ == generator_only_class:
                excluded_cases.append(case)
                excluded_classes.add(case.__class__)
                continue
            selected.addTest(case)

    if len(excluded_classes) != 1 or {
            item.__name__ for item in excluded_classes} != {generator_only_class}:
        raise SystemExit(
            "expected exactly one discovered generator-only class named {0}; "
            "found {1}".format(
                generator_only_class,
                sorted(item.__name__ for item in excluded_classes)))
    if discovered_count != selected.countTestCases() + len(excluded_cases):
        raise SystemExit("conformance selection lost a discovered test")
    return selected, len(excluded_cases)


def probe_adapter_inventory(arguments):
    if len(arguments) != 2:
        raise SystemExit(
            "usage: --probe-adapter-inventory ADAPTER_DIR DECLARED_JSON")
    require_closed_adapter_inventory(
        Path(arguments[0]).resolve(), json.loads(arguments[1]))
    return 0


def probe_generator_exclusion(arguments):
    if len(arguments) != 2:
        raise SystemExit(
            "usage: --probe-generator-exclusion CLASS SUITE_PATH")
    selected, excluded = load_selected_suites(
        [Path(arguments[1]).resolve()], arguments[0])
    print("selected tests: {0}".format(selected.countTestCases()), flush=True)
    print("excluded generator-only class: {0} ({1} tests)".format(
        arguments[0], excluded), flush=True)
    return 0


def run_installed_conformance(arguments):
    if len(arguments) < 4:
        raise SystemExit(
            "usage: REPO_ROOT GENERATOR_ONLY_CLASS ADAPTER_MAPPING_JSON "
            "CORE_SUITE...")
    repo_root = Path(arguments[0]).resolve()
    generator_only_class = arguments[1]
    declared_adapters = json.loads(arguments[2])
    core_suite_paths = [Path(value).resolve() for value in arguments[3:]]
    source_root = (repo_root / "tools/iptc/canonical").resolve()

    # This must precede importing the wheel or any repository contract.  The
    # contracts therefore cannot open a socket or resolve a host even if a future
    # test introduces a network path.
    install_network_guard()

    # Import the wheel before the checkout is made importable.  Under ``-I`` and
    # from the neutral directory, this can only be the venv's site-packages copy.
    installed_distribution = importlib.import_module("machina_sports_canonical")
    installed_root = Path(installed_distribution.__file__).resolve().parent
    purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
    if installed_root.parent != purelib:
        raise SystemExit("installed package is not in this venv: {0}".format(
            installed_root))
    if beneath(installed_root, repo_root):
        raise SystemExit(
            "installed package resolved under the repository: {0}".format(
                installed_root))

    require_closed_adapter_inventory(
        installed_root / "adapters", declared_adapters)
    adapter_suite_paths = [
        (repo_root / declared_adapters[module]).resolve()
        for module in sorted(declared_adapters)
    ]
    suite_paths = core_suite_paths + adapter_suite_paths

    # The tests and offline validator remain repository evidence.  Load the
    # installed package bytes under the alias's own spec name: merely storing a
    # package whose spec still says ``machina_sports_canonical`` under a second
    # sys.modules key can load its children twice and invalidate the
    # single-implementation contracts.
    sys.path.insert(0, str(repo_root))
    import tools.iptc as iptc
    canonical_spec = importlib.util.spec_from_file_location(
        "tools.iptc.canonical", str(installed_root / "__init__.py"),
        submodule_search_locations=[str(installed_root)])
    if canonical_spec is None or canonical_spec.loader is None:
        raise SystemExit("cannot alias installed canonical package: {0}".format(
            installed_root))
    canonical = importlib.util.module_from_spec(canonical_spec)
    sys.modules["tools.iptc.canonical"] = canonical
    canonical_spec.loader.exec_module(canonical)
    setattr(iptc, "canonical", canonical)

    # ``test_iptc_canonical_serializer`` imports its generator at module load
    # before unittest can exclude that class.  A pathless neutral stub permits
    # discovery; no selected test uses it, and no repository generator module is
    # imported.
    generator_name = "tools.iptc.canonical.export_official_terms"
    generator = types.ModuleType(generator_name)
    generator.__file__ = str(Path(__file__).resolve().parent /
                             "excluded_export_official_terms.py")
    sys.modules[generator_name] = generator
    setattr(canonical, "export_official_terms", generator)

    # The reused command tests intentionally pass repository-relative paths.
    # Their ordinary runner has the checkout as cwd; this proof must keep a
    # neutral cwd, so resolve those same arguments against the explicit
    # repository root instead of ambient process state.
    from tools.iptc import cli_support

    def neutral_iter_targets(args):
        if args.all:
            return cli_support.registered_fixtures(args.section)
        if not args.documents:
            raise SystemExit(
                "nothing to check: pass one or more documents, or --all")
        resolved = []
        for path in args.documents:
            target = path if path.is_absolute() else (repo_root / path)
            if not target.is_file():
                raise SystemExit("not a file: {0}".format(path))
            try:
                label = str(target.resolve().relative_to(repo_root))
            except ValueError:
                label = str(target)
            resolved.append((label, target.resolve()))
        return resolved

    cli_support.iter_targets = neutral_iter_targets

    selected, excluded = load_selected_suites(
        suite_paths, generator_only_class)
    bad = canonical_source_resolutions(source_root)
    if bad:
        raise SystemExit("canonical imports reached repository source:\n" +
                         "\n".join(bad))

    print("installed canonical root: {0}".format(installed_root), flush=True)
    print("excluded generator-only class: {0} ({1} tests)".format(
        generator_only_class, excluded), flush=True)
    print("installed conformance test count: {0}".format(
        selected.countTestCases()), flush=True)
    result = unittest.TextTestRunner(verbosity=1).run(selected)

    bad = canonical_source_resolutions(source_root)
    if bad:
        print("canonical imports reached repository source after the run:",
              file=sys.stderr)
        for problem in bad:
            print("  " + problem, file=sys.stderr)
    return 0 if result.wasSuccessful() and not bad else 1


def main():
    arguments = sys.argv[1:]
    if arguments == ["--probe-network-guard"]:
        return probe_network_guard()
    if arguments and arguments[0] == "--probe-adapter-inventory":
        return probe_adapter_inventory(arguments[1:])
    if arguments and arguments[0] == "--probe-generator-exclusion":
        return probe_generator_exclusion(arguments[1:])
    return run_installed_conformance(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
'''


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reviewed_digests() -> dict:
    rows = {}
    for line in RELEASE_CHECKSUM_PATH.read_text(encoding="utf-8").splitlines():
        digest, filename = line.split(None, 1)
        rows[filename.strip()] = digest
    return rows


def stage_inputs(destination: Path) -> None:
    destination.mkdir(parents=True)
    for relative in PACKAGING_INPUTS:
        source = REPO_ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target,
                            ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(source, target)


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin") \
        / ("python.exe" if os.name == "nt" else "python")


def purelib(python: Path) -> Path:
    result = subprocess.run(
        [str(python), "-c",
         "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise AssertionError("could not locate isolated site-packages:\n{0}".format(
            result.stdout + result.stderr))
    return Path(result.stdout.strip()).resolve()


def share_pinned_site_packages(python: Path) -> None:
    """Expose only this interpreter's already-installed pinned closures.

    ``--system-site-packages`` points at the base interpreter when this suite is
    itself running inside a venv, skipping the exact pins installed in the
    current environment.  A path file naming ``site.getsitepackages()`` follows
    the current interpreter in both local nested-venv runs and setup-python CI,
    with no resolver and no network access.
    """
    roots = [Path(path).resolve() for path in site.getsitepackages()]
    for path in roots:
        if path == REPO_ROOT or REPO_ROOT in path.parents:
            raise AssertionError("current site-packages reaches repository: "
                                 + str(path))
    (purelib(python) / "iptc-pinned-proof-inputs.pth").write_text(
        "".join("{0}\n".format(path) for path in roots), encoding="utf-8")


class TestInstalledCanonicalConformance(unittest.TestCase):
    """The reviewed wheel, installed and exercised outside the checkout."""

    @classmethod
    def setUpClass(cls):
        cls.workspace = Path(tempfile.mkdtemp(
            prefix="iptc-installed-conformance-"))
        cls.addClassCleanup(shutil.rmtree, cls.workspace, True)
        source = cls.workspace / "source"
        outdir = cls.workspace / "dist"
        neutral = cls.workspace / "neutral"
        environment = cls.workspace / "venv"
        neutral.mkdir()
        stage_inputs(source)

        build_environment = dict(
            os.environ, SOURCE_DATE_EPOCH=RELEASE_SOURCE_DATE_EPOCH)
        build = subprocess.run(
            [sys.executable, str(REPO_ROOT / RELEASE_HELPER),
             str(source), str(outdir)],
            cwd=str(neutral), capture_output=True, text=True, timeout=900,
            env=build_environment)
        if build.returncode != 0:
            raise AssertionError("reviewed build failed:\n{0}".format(
                build.stdout + build.stderr))

        artifacts = sorted(list(outdir.glob("*.whl"))
                           + list(outdir.glob("*.tar.gz")))
        actual = {path.name: sha256(path) for path in artifacts}
        expected = reviewed_digests()
        expected_names = {
            "{0}-py3-none-any.whl".format(ARTIFACT_STEM),
            "{0}.tar.gz".format(ARTIFACT_STEM),
        }
        if set(actual) != expected_names:
            raise AssertionError("candidate build artifact set is invalid: {0!r}".format(actual))
        if actual != expected:
            raise AssertionError(
                "reviewed build digests differ:\nactual={0!r}\nexpected={1!r}".format(
                    actual, expected))
        wheel_name = "{0}-py3-none-any.whl".format(ARTIFACT_STEM)
        wheel = outdir / wheel_name

        creation = subprocess.run(
            [sys.executable, "-m", "venv", str(environment)],
            cwd=str(neutral), capture_output=True, text=True, timeout=600)
        if creation.returncode != 0:
            raise AssertionError("isolated environment creation failed:\n{0}".format(
                creation.stdout + creation.stderr))
        cls.python = venv_python(environment)
        share_pinned_site_packages(cls.python)
        install = subprocess.run(
            [str(cls.python), "-m", "pip", "install", "--no-index",
             "--no-deps", "--ignore-installed", "--no-cache-dir",
             "--disable-pip-version-check", str(wheel)],
            cwd=str(neutral), capture_output=True, text=True, timeout=900)
        if install.returncode != 0:
            raise AssertionError("reviewed wheel install failed:\n{0}".format(
                install.stdout + install.stderr))

        cls.neutral = neutral
        cls.bootstrap = neutral / "installed_conformance_bootstrap.py"
        cls.bootstrap.write_text(textwrap.dedent(BOOTSTRAP), encoding="utf-8")

    def test_reviewed_wheel_passes_the_canonical_and_provider_contracts(self):
        command = [
            str(self.python), "-I", str(self.bootstrap), str(REPO_ROOT),
            GENERATOR_ONLY_CLASS, json.dumps(ADAPTER_CONFORMANCE_SUITES),
        ]
        command.extend(str(REPO_ROOT / relative)
                       for relative in CORE_CONFORMANCE_SUITES)
        result = subprocess.run(
            command, cwd=str(self.neutral),
            timeout=CHILD_CONFORMANCE_TIMEOUT_SECONDS)
        self.assertEqual(result.returncode, 0,
                         "installed conformance child exited {0}".format(
                             result.returncode))


if __name__ == "__main__":
    unittest.main(verbosity=2)
