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
ARTIFACT_STEM = "machina_sports_canonical-0.1.0"
RELEASE_HELPER = "packaging/machina_sports_canonical/release.py"
RELEASE_CHECKSUM_PATH = (
    REPO_ROOT / "docs/iptc/machina-sports-canonical-0.1.0.sha256")
RELEASE_SOURCE_DATE_EPOCH = "1786398569"

# The same closed staging set as the package proof.  Building a disposable copy
# avoids setuptools writing egg-info into the checkout.
PACKAGING_INPUTS = (
    "pyproject.toml",
    "setup.py",
    "MANIFEST.in",
    "README-machina-sports-canonical.md",
    "packaging",
    "tools/iptc/canonical",
)

# Exact order is intentional: core contracts first, then cross-cutting contracts,
# then every packaged provider adapter.  The manifest gives this outer suite its
# place in the repository-wide order; this tuple gives the reused contracts their
# order inside the installed proof.
CONFORMANCE_SUITES = (
    "tests/test_iptc_canonical_serializer.py",
    "tests/test_iptc_capability_matrix.py",
    "tests/test_iptc_cli_rights_gate.py",
    "tests/test_iptc_cross_provider_equivalence.py",
    "tests/test_iptc_identity_resolution_method.py",
    "tests/test_iptc_multi_participant_contract.py",
    "tests/test_iptc_source_ref_credentials.py",
    "tests/test_iptc_sports_skills_reference_contract.py",
    "tests/test_iptc_api_football_adapter.py",
    "tests/test_iptc_sportradar_mlb_adapter.py",
    "tests/test_iptc_sportradar_nfl_adapter.py",
    "tests/test_iptc_sportradar_soccer_adapter.py",
    "tests/test_iptc_sportradar_tennis_adapter.py",
    "tests/test_iptc_stats_perform_opta_adapter.py",
)

GENERATOR_ONLY_CLASS = "TestOfficialTermExport"


BOOTSTRAP = r'''\
from __future__ import annotations

import importlib
import importlib.util
import sys
import sysconfig
import types
import unittest
from pathlib import Path


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


repo_root = Path(sys.argv[1]).resolve()
suite_paths = [Path(value).resolve() for value in sys.argv[2:]]
source_root = (repo_root / "tools/iptc/canonical").resolve()
sys.dont_write_bytecode = True

# Import the wheel before the checkout is made importable.  Under ``-I`` and
# from the neutral directory, this can only be the venv's site-packages copy.
installed_distribution = importlib.import_module("machina_sports_canonical")
installed_root = Path(installed_distribution.__file__).resolve().parent
purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
if installed_root.parent != purelib:
    raise SystemExit("installed package is not in this venv: {0}".format(
        installed_root))
if beneath(installed_root, repo_root):
    raise SystemExit("installed package resolved under the repository: {0}".format(
        installed_root))

# The tests and offline validator remain repository evidence.  Load the installed
# package bytes under the alias's own spec name: merely storing a package whose
# spec still says ``machina_sports_canonical`` under a second sys.modules key can
# load its children twice and invalidate the single-implementation contracts.
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

# ``test_iptc_canonical_serializer`` imports its generator at module load before
# unittest can exclude that class.  A pathless neutral stub permits discovery;
# no selected test uses it, and no repository generator module is imported.
generator_name = "tools.iptc.canonical.export_official_terms"
generator = types.ModuleType(generator_name)
generator.__file__ = str(Path(__file__).resolve().parent /
                         "excluded_export_official_terms.py")
sys.modules[generator_name] = generator
setattr(canonical, "export_official_terms", generator)

# The reused command tests intentionally pass repository-relative paths.  Their
# ordinary runner has the checkout as cwd; this proof must keep a neutral cwd, so
# resolve those same arguments against the explicit repository root instead of
# ambient process state.
from tools.iptc import cli_support


def neutral_iter_targets(args):
    if args.all:
        return cli_support.registered_fixtures(args.section)
    if not args.documents:
        raise SystemExit("nothing to check: pass one or more documents, or --all")
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

selected = unittest.TestSuite()
excluded = 0
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
        if ".{0}.".format("TestOfficialTermExport") in case.id():
            excluded += 1
            continue
        selected.addTest(case)

if excluded == 0:
    raise SystemExit("the generator-only class was not found to exclude")
bad = canonical_source_resolutions(source_root)
if bad:
    raise SystemExit("canonical imports reached repository source:\n" +
                     "\n".join(bad))

print("installed canonical root: {0}".format(installed_root), flush=True)
print("installed conformance test count: {0}".format(
    selected.countTestCases()), flush=True)
result = unittest.TextTestRunner(verbosity=1).run(selected)

bad = canonical_source_resolutions(source_root)
if bad:
    print("canonical imports reached repository source after the run:",
          file=sys.stderr)
    for problem in bad:
        print("  " + problem, file=sys.stderr)
raise SystemExit(0 if result.wasSuccessful() and not bad else 1)
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
        if actual != expected:
            raise AssertionError("build is not the reviewed release:\n"
                                 "expected {0!r}\nactual {1!r}".format(
                                     expected, actual))
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
        command = [str(self.python), "-I", str(self.bootstrap), str(REPO_ROOT)]
        command.extend(str(REPO_ROOT / relative)
                       for relative in CONFORMANCE_SUITES)
        result = subprocess.run(command, cwd=str(self.neutral), timeout=1800)
        self.assertEqual(result.returncode, 0,
                         "installed conformance child exited {0}".format(
                             result.returncode))


if __name__ == "__main__":
    unittest.main(verbosity=2)
