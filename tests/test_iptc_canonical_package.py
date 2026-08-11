"""The distribution `machina-sports-canonical` is real, clean and faithful.

Run from the repository root:

    python3 tests/test_iptc_canonical_package.py -v

Run the file directly, for the same reason as the other IPTC suites: ``tests/``
is a namespace directory with no ``__init__.py``, so ``-m unittest
tests.<module>`` can be shadowed by an installed distribution that ships a
top-level regular ``tests`` package.

**What this suite is for.** ``machina-client-api`` execs a pyscript connector
sidecar *in-process*, in the image's own interpreter. There is no per-template
dependency install, no vendoring hook and no ``sys.path`` injection at execution
time, so ``import machina_sports_canonical`` inside a connector works only if a
wheel was installed into the image. That makes the wheel — not
``tools/iptc/canonical`` on disk — the artefact consumers actually run. Nothing
in this repository checked that artefact before this suite: the source bytes were
gated by ``tests/test_iptc_vendored_manifest.py``, and everything between those
bytes and an installed package was unexamined.

So the questions here are the ones a build can silently get wrong:

- **Does it build at all**, exactly one wheel and one sdist, at the declared
  version? A packaging config that produces two wheels or none is a release that
  cannot be pinned.
- **Does a clean interpreter install it offline?** Installed with ``--no-index``
  into a throwaway venv, then imported there. An import that only works from the
  repository root is not a package.
- **Are the shipped bytes the authoritative bytes?** Every installed core file is
  hashed against ``tools/iptc/vendored-manifest.json``; every adapter and JSON
  resource is compared byte-for-byte with ``tools/iptc/canonical/``. If packaging
  ever rewrites, reformats or re-encodes a source file, that is a red test — never
  a reason to regenerate the manifest from the installed copy, which would make
  the comparison compare the artefact to itself.
- **Do the JSON resources load from the installed package?** ``shared-context.json``
  and ``official-property-names.json`` are read through ``__file__``, so a wheel
  that omits them fails at first use rather than at install. The probe runs from a
  neutral directory, under ``-I``, with the socket module disabled: it cannot reach
  back into this repository and it cannot reach a network.
- **Is the floor still 3.9 and the dependency set still empty?** Both are promises
  the client image relies on. They are checked against the *installed* files and
  the *installed* metadata, not against the source tree that produced them.
- **Is the wheel a closed set?** Every member accounted for, the repository-only
  generator ``export_official_terms.py`` absent, and the build filter proved to
  reject any exclusion other than that one. A build filter with a free-form
  exclusion list is a supply-chain hole: it can drop a module and still produce a
  valid-looking wheel.

**Where the artefacts are built, and why not in place.** ``python -m build``
writes ``build/`` and ``*.egg-info/`` into the directory it builds, and this
repository's CI fails on a dirty working tree after the harness runs. So the
packaging inputs are copied into a disposable staging tree and built there, with
``--outdir`` pointing at the same disposable tree. Nothing this suite does can
leave an artefact in a tracked path. The copy is the exact set of build inputs
named in ``PACKAGING_INPUTS``, so building from it proves the same thing building
in place would — and additionally proves that set is closed, because a build input
left out of it makes the build fail here.

**Offline and deterministic.** ``--no-isolation`` (the build frontend and
``setuptools``/``wheel`` come from the interpreter running the suite, not from
PyPI) and ``--no-index`` on every install. The build runs once per process and is
shared; the disposable tree is removed in ``tearDownModule``.
"""

from __future__ import annotations

import ast
import csv
import fnmatch
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: The authoritative source the distribution maps onto. Not copied, not moved.
CANONICAL_ROOT = REPO_ROOT / "tools/iptc/canonical"

#: The nine-file core receipt sports-skills vendors. The same hashes have to come
#: out of the wheel, or the two consumers are running different code.
VENDORED_MANIFEST_PATH = REPO_ROOT / "tools/iptc/vendored-manifest.json"

#: Distribution name on the index, import namespace in the interpreter, and the
#: version both are pinned at. The three are deliberately spelled out separately:
#: PEP 503 normalization makes the first two look interchangeable and they are not.
DISTRIBUTION = "machina-sports-canonical"
IMPORT_NAME = "machina_sports_canonical"
VERSION = "0.1.0"

#: The stem every built artefact carries. ``build`` normalizes the distribution
#: name to its underscore form for filenames.
ARTIFACT_STEM = "{0}-{1}".format(IMPORT_NAME, VERSION)

#: The one module that stays in this repository and is not shipped: a generator
#: that regenerates ``official-property-names.json`` from the pinned upstream
#: ontologies, which exist only here. ``canonical/__init__.py`` already names it
#: as the single deliberate exception; this suite makes that binding.
GENERATOR_MODULE = "export_official_terms.py"

#: Non-Python files the wheel must carry. Spelled out rather than globbed, so a
#: new resource is an explicit, reviewable addition instead of something a glob
#: absorbs.
JSON_RESOURCES = (
    "official-property-names.json",
    "package-receipt.json",
    "shared-context.json",
)

#: The complete set of build inputs, copied into the staging tree. A file the
#: build needs that is missing here makes the build fail rather than silently
#: succeed against the repository it was supposed to be isolated from.
PACKAGING_INPUTS = (
    "pyproject.toml",
    "setup.py",
    "MANIFEST.in",
    "README-machina-sports-canonical.md",
    "packaging",
    "tools/iptc/canonical",
)

#: The packaging configuration this suite proves. Named so the RED before Task 3
#: reads as "the configuration does not exist" rather than as a build traceback.
REQUIRED_PACKAGING_FILES = (
    "pyproject.toml",
    "setup.py",
    "packaging/machina_sports_canonical/build.py",
    "tools/iptc/canonical/package-receipt.json",
)

#: Interpreters the clean-install proof is repeated on. Absence is an explicit,
#: printed skip — never a silent pass. 3.9 is the declared floor; 3.11 is what the
#: client image runs.
PROVEN_INTERPRETERS = ("3.9", "3.11")

#: The workflow that decides which interpreters remotely exist. Asserted here
#: rather than assumed, because the two proofs above degrade to a skip on an
#: interpreter that is not installed — and a skip is green. A workflow whose only
#: job selects 3.12 therefore reports a passing 3.9 floor it never ran.
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/validate-iptc-sport-schema.yml"

#: The job that runs the whole tree once, and the job that runs this suite on
#: each declared interpreter. Two jobs rather than a matrix over everything: the
#: slow conformance suites answer nothing new on a second interpreter, and paying
#: for them three times would buy latency instead of coverage.
VALIDATION_JOB = "validate"
PACKAGE_PROOF_JOB = "package-proof"

#: The interpreter the full validation job stays on. It remains the authority for
#: the whole suite; the matrix below adds interpreters, it does not replace one.
VALIDATION_PYTHON = "3.12"

#: Exactly pinned build tooling, checked in. `pip install "build>=1.0"` in a
#: workflow is a build frontend that can change between two runs of the same
#: commit, with nothing in the diff to show it.
BUILD_REQUIREMENTS = "requirements-iptc-build.txt"

#: What that file exists to pin: the PEP 517 frontend, the backend
#: `pyproject.toml` names, and the helper its `build-system.requires` lists
#: beside that backend.
BUILD_REQUIREMENT_NAMES = ("build", "setuptools", "wheel")

#: This suite, as CI spells it.
PACKAGE_PROOF_SUITE = "tests/test_iptc_canonical_package.py"

#: Every input this proof reads or builds from. A change to one of these that did
#: not trigger the workflow would leave the package unproven for that commit,
#: which is the same gap as not having the job at all.
PACKAGING_INPUTS_THE_FILTERS_MUST_REACH = (
    BUILD_REQUIREMENTS,
    PACKAGE_PROOF_SUITE,
    "pyproject.toml",
    "setup.py",
    "MANIFEST.in",
    "README-machina-sports-canonical.md",
    "packaging/machina_sports_canonical/build.py",
    "tools/iptc/canonical/serialize.py",
    "tools/iptc/canonical/package-receipt.json",
    "tools/iptc/vendored-manifest.json",
)

#: Attributes this suite must never reach for, because the declared floor does
#: not have them. `sys.stdlib_module_names` is 3.10+: on 3.9 it raised
#: AttributeError before the constraint it was checking could be answered, so the
#: floor was unprovable by the very suite that claims it.
FLOOR_HOSTILE_ATTRIBUTES = ("stdlib_module_names",)

#: Prepended to every probe that runs inside an installed venv. A canonical
#: module that reached a network would do it while loading a JSON resource, which
#: is exactly what the resource probe exercises.
NETWORK_GUARD = '''
import socket


class NetworkReached(RuntimeError):
    pass


def _refuse(*args, **kwargs):
    raise NetworkReached("the installed package must not reach the network")


socket.socket = _refuse
socket.create_connection = _refuse
socket.getaddrinfo = _refuse
'''


# ---------------------------------------------------------------------------
# Disposable build and install, shared across the suite
# ---------------------------------------------------------------------------

_WORKSPACE = None
_BUILD = None
_INSTALLS = {}


def workspace() -> Path:
    """The one disposable tree everything in this suite writes into."""
    global _WORKSPACE
    if _WORKSPACE is None:
        _WORKSPACE = Path(tempfile.mkdtemp(prefix="iptc-canonical-package-"))
    return _WORKSPACE


def tearDownModule():
    if _WORKSPACE is not None:
        shutil.rmtree(_WORKSPACE, ignore_errors=True)


def stage_packaging_inputs() -> Path:
    """Copy the declared build inputs into the staging tree, preserving layout."""
    source = workspace() / "source"
    if source.exists():
        return source
    source.mkdir(parents=True)
    for relative in PACKAGING_INPUTS:
        origin = REPO_ROOT / relative
        if not origin.exists():
            continue
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if origin.is_dir():
            shutil.copytree(origin, target,
                            ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(origin, target)
    return source


class Built:
    """What one ``python -m build`` run produced, successful or not."""

    def __init__(self, source: Path, outdir: Path, result):
        self.source = source
        self.outdir = outdir
        self.returncode = result.returncode
        self.output = result.stdout + result.stderr
        self.wheels = sorted(outdir.glob("*.whl")) if outdir.is_dir() else []
        self.sdists = sorted(outdir.glob("*.tar.gz")) if outdir.is_dir() else []

    @property
    def wheel(self) -> Path:
        assert len(self.wheels) == 1, "expected exactly one wheel"
        return self.wheels[0]

    @property
    def sdist(self) -> Path:
        assert len(self.sdists) == 1, "expected exactly one sdist"
        return self.sdists[0]

    def diagnosis(self) -> str:
        return "build exit {0}\n{1}".format(self.returncode, self.output[-4000:])


def built() -> Built:
    """Build the wheel and the sdist once per process.

    ``--no-isolation`` because this suite must run offline: the frontend uses the
    ``setuptools``/``wheel`` already present in the interpreter running it rather
    than fetching a build environment. ``build`` produces the sdist first and then
    builds the wheel *from that sdist*, so an sdist missing a build input cannot
    yield a wheel — which is what makes ``MANIFEST.in`` coverage checkable here
    rather than assumed.
    """
    global _BUILD
    if _BUILD is None:
        source = stage_packaging_inputs()
        outdir = workspace() / "dist"
        result = subprocess.run(
            [sys.executable, "-m", "build", "--no-isolation",
             "--outdir", str(outdir), str(source)],
            capture_output=True, text=True, timeout=900)
        _BUILD = Built(source, outdir, result)
    return _BUILD


def interpreter(version: str):
    """A real interpreter for ``version``, or ``None``.

    The interpreter running this suite answers for its own version first. On a CI
    matrix leg that is the whole point: the leg selected an interpreter, installed
    the pinned build tooling into it and ran this file with it, so resolving
    ``python3.9`` on PATH instead could prove a *different* 3.9 — or find none and
    reduce that leg's own proof to a skip, which is green.

    Otherwise resolved by asking the candidate what it is rather than trusting its
    name: a ``python3.9`` on PATH that is a shim for something else would turn the
    3.9 proof into a 3.12 one.
    """
    if "{0}.{1}".format(*sys.version_info[:2]) == version:
        return sys.executable
    candidate = shutil.which("python{0}".format(version))
    if candidate is None:
        return None
    probe = subprocess.run(
        [candidate, "-c",
         "import sys; print('%d.%d' % sys.version_info[:2])"],
        capture_output=True, text=True, timeout=120)
    if probe.returncode != 0 or probe.stdout.strip() != version:
        return None
    return candidate


def clean_install(python_exe: str, label: str) -> Path:
    """A throwaway venv with the built wheel installed offline, cached per label.

    ``--no-index`` is the whole point: the distribution declares no dependency, so
    a correct install needs no index at all. An install that quietly reached PyPI
    would prove nothing about what the client image can do behind its firewall.
    """
    if label in _INSTALLS:
        return _INSTALLS[label]
    venv_dir = workspace() / "venv-{0}".format(label)
    creation = subprocess.run([python_exe, "-m", "venv", str(venv_dir)],
                              capture_output=True, text=True, timeout=600)
    if creation.returncode != 0:
        raise AssertionError("could not create a venv for {0}:\n{1}".format(
            label, creation.stdout + creation.stderr))
    venv_python = venv_dir / ("Scripts" if os.name == "nt" else "bin") \
        / ("python.exe" if os.name == "nt" else "python")
    for wheel in built().wheels:
        install = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--no-index",
             "--no-cache-dir", "--disable-pip-version-check", str(wheel)],
            capture_output=True, text=True, timeout=900)
        if install.returncode != 0:
            raise AssertionError("offline install failed for {0}:\n{1}".format(
                label, install.stdout + install.stderr))
    _INSTALLS[label] = venv_python
    return venv_python


def probe(venv_python: Path, body: str, label: str):
    """Run ``body`` inside an installed venv, from a neutral directory.

    ``-I`` drops the user site directory and every ``PYTHON*`` environment
    variable, and makes ``sys.path[0]`` the script's own directory. Combined with a
    ``cwd`` outside this repository, that is what makes "no repository reach-back"
    a demonstrated property rather than an intention.
    """
    neutral = Path(tempfile.mkdtemp(prefix="iptc-neutral-"))
    try:
        script = neutral / "probe_{0}.py".format(label)
        script.write_text(NETWORK_GUARD + body, encoding="utf-8")
        return subprocess.run([str(venv_python), "-I", str(script)],
                              cwd=str(neutral), capture_output=True,
                              text=True, timeout=600)
    finally:
        shutil.rmtree(neutral, ignore_errors=True)


def probe_payload(result):
    """The JSON object a probe printed on its last line."""
    return json.loads(result.stdout.strip().splitlines()[-1])


def purelib(venv_python: Path) -> Path:
    """The venv's ``site-packages``, resolved.

    Resolved because the probes resolve too, and on macOS a temporary directory is
    reached through a symlink (``/var`` -> ``/private/var``): comparing one
    resolved path with one unresolved path would fail for a reason that has
    nothing to do with packaging.
    """
    result = subprocess.run(
        [str(venv_python), "-c",
         "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        capture_output=True, text=True, timeout=120)
    return Path(result.stdout.strip()).resolve()


# ---------------------------------------------------------------------------
# Source-side expectations
# ---------------------------------------------------------------------------


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def vendored_manifest() -> dict:
    return json.loads(VENDORED_MANIFEST_PATH.read_text(encoding="utf-8"))


def source_modules() -> set:
    """Every ``.py`` under the canonical root, repository-relative to it."""
    found = set()
    for path in sorted(CANONICAL_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        found.add(path.relative_to(CANONICAL_ROOT).as_posix())
    return found


def expected_runtime_members() -> set:
    """What the wheel must contain under the import namespace.

    Derived from the source tree rather than typed out, minus the one deliberate
    exclusion, plus the declared resources. A module added under ``canonical/``
    therefore has to ship — or the exclusion list has to grow, which the build
    filter refuses.
    """
    return (source_modules() - {GENERATOR_MODULE}) | set(JSON_RESOURCES)


def installed_root(venv_python: Path) -> Path:
    return purelib(venv_python) / IMPORT_NAME


def installed_members(venv_python: Path) -> set:
    root = installed_root(venv_python)
    found = set()
    for path in sorted(root.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        found.add(path.relative_to(root).as_posix())
    return found


def adapter_modules() -> list:
    """Shipped adapter module names, read off the source package."""
    return sorted(path.stem
                  for path in (CANONICAL_ROOT / "adapters").glob("*.py")
                  if path.stem != "__init__")


def build_filter():
    """``packaging/machina_sports_canonical/build.py``, loaded from its path.

    Loaded by file rather than imported as ``packaging.…``: a root ``packaging``
    directory that were importable would shadow the ``packaging`` distribution
    setuptools itself resolves, and turning a build helper into that hazard is a
    much worse trade than one ``importlib`` call.
    """
    path = REPO_ROOT / "packaging/machina_sports_canonical/build.py"
    spec = importlib.util.spec_from_file_location(
        "iptc_canonical_build_filter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wheel_record(wheel: Path) -> list:
    with zipfile.ZipFile(wheel) as archive:
        name = "{0}.dist-info/RECORD".format(ARTIFACT_STEM)
        blob = archive.read(name).decode("utf-8")
    return [row[0] for row in csv.reader(io.StringIO(blob)) if row]


def wheel_metadata(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        return archive.read(
            "{0}.dist-info/METADATA".format(ARTIFACT_STEM)).decode("utf-8")


def parses_on_python_39(source: str) -> bool:
    """Whether ``source`` is syntax CPython 3.9 accepts.

    ``compile()`` under the interpreter running these tests would accept 3.12
    syntax, so it answers the wrong question.
    """
    try:
        ast.parse(source, feature_version=(3, 9))
    except SyntaxError:
        return False
    return True


def is_standard_library(root: str) -> bool:
    """Whether ``root`` is a standard library top-level module *here*.

    Asked of the running interpreter rather than read off a table, because the
    table does not exist on the interpreter that matters: ``sys.stdlib_module_names``
    arrived in 3.10 and the declared floor is 3.9. A permissive fallback would be
    worse than the AttributeError it replaced — it would answer "yes" for every
    third-party import and quietly retire the zero-dependency claim.

    Three questions, in the order that keeps a false "yes" impossible: is it
    built into this interpreter; does it resolve at all; and does it resolve
    inside this interpreter's own standard library directory rather than in a
    site directory. The site check comes first because a system install puts
    ``site-packages`` *underneath* the stdlib path, where a containment test
    alone would call every installed distribution standard library.
    """
    if root in sys.builtin_module_names:
        return True
    try:
        spec = importlib.util.find_spec(root)
    except (ImportError, ValueError):
        return False
    if spec is None:
        return False
    if spec.origin in ("built-in", "frozen"):
        return True
    if spec.origin is None:
        return False
    location = Path(spec.origin).resolve()
    if {"site-packages", "dist-packages"} & set(location.parts):
        return False
    stdlib = Path(sysconfig.get_paths()["stdlib"]).resolve()
    return location == stdlib or stdlib in location.parents


def absolute_import_roots(tree: ast.Module) -> list:
    roots = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            roots.append((node.module or "").split(".")[0])
    return roots


# ---------------------------------------------------------------------------
# Reading the workflow, with the standard library only
# ---------------------------------------------------------------------------
#
# Not a YAML parse, and not borrowed from `tests/test_iptc_validation_harness.py`
# which reads the same file for its own assertions. This is the one suite CI runs
# on the floor interpreter with the pinned build tooling and nothing else
# installed: it can import no YAML library, and reaching into a suite whose
# module-level imports pull the harness's dependency tree would make the floor
# proof depend on the very install it is meant to run without. The shapes read
# here are a flat `jobs:` mapping and two flat `paths:` lists.


def workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def workflow_jobs(text: str = None) -> dict:
    """Each job's own lines, keyed by job id.

    Job-scoped on purpose. "The workflow installs the pinned requirements"
    is not the claim that matters — every job that builds has to install them,
    and a whole-file scan cannot tell one job's steps from another's.

    Comment lines are dropped here, so no assertion below can be satisfied — or
    broken — by prose explaining a step rather than by the step.
    """
    jobs = {}
    current = None
    in_jobs = False
    for raw in (workflow_text() if text is None else text).splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        stripped = raw.strip()
        if indent == 0:
            in_jobs = stripped == "jobs:"
            current = None
            continue
        if not in_jobs:
            continue
        if indent == 2 and stripped.endswith(":") and not stripped.startswith("-"):
            current = jobs.setdefault(stripped[:-1], [])
            continue
        if current is not None:
            current.append(raw)
    return {name: "\n".join(lines) for name, lines in jobs.items()}


def run_commands(block: str) -> list:
    """Every shell line a job actually executes, block scalars included."""
    commands = []
    block_indent = None
    for raw in block.splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        if block_indent is not None:
            if indent > block_indent:
                commands.append(raw.strip())
                continue
            block_indent = None
        stripped = raw.strip()
        if stripped.startswith("- "):
            stripped = stripped[2:]
        if not stripped.startswith("run:"):
            continue
        body = stripped[len("run:"):].strip()
        if body in ("|", ">", "|-", ">-", "|+", ">+"):
            block_indent = indent
        elif body:
            commands.append(body)
    return commands


def matrix_python_versions(block: str) -> list:
    """The interpreters a job's matrix declares, in declaration order."""
    for raw in block.splitlines():
        stripped = raw.strip()
        if stripped.startswith("python-version:") and "[" in stripped:
            inside = stripped[stripped.index("[") + 1:stripped.rindex("]")]
            return [item.strip().strip('"').strip("'")
                    for item in inside.split(",") if item.strip()]
    return []


def path_filter_blocks() -> list:
    """Every ``paths:`` list in the trigger section — ``pull_request``, ``push``."""
    blocks = []
    current = None
    for raw in workflow_text().splitlines():
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


def reached_by(path: str, globs) -> bool:
    """Whether any filter glob reaches ``path``.

    ``fnmatch`` is not GitHub's matcher — it reads ``**`` as ``*`` and lets ``*``
    cross a separator — so this is permissive. That is the safe direction here: it
    can only fail to report a gap if GitHub is stricter, and every glob asserted
    against is a plain prefix wildcard where the two agree.
    """
    return any(fnmatch.fnmatch(path, pattern.replace("**", "*"))
               for pattern in globs)


# ---------------------------------------------------------------------------
# 1. The artefacts exist, and there is exactly one of each
# ---------------------------------------------------------------------------


class TestTheDistributionBuilds(unittest.TestCase):
    """One wheel, one sdist, at the declared version. Anything else cannot be
    pinned by a consumer, and pinning is the entire point of publishing."""

    def test_the_packaging_configuration_is_checked_in(self):
        """Named separately so a missing configuration reads as a missing
        configuration rather than as a build traceback three tests down."""
        for relative in REQUIRED_PACKAGING_FILES:
            with self.subTest(path=relative):
                self.assertTrue((REPO_ROOT / relative).is_file(),
                                "missing packaging file: {0}".format(relative))

    def test_wheel_and_sdist_build(self):
        result = built()
        self.assertEqual(result.returncode, 0, result.diagnosis())
        self.assertEqual([path.name for path in result.wheels],
                         ["{0}-py3-none-any.whl".format(ARTIFACT_STEM)],
                         result.diagnosis())
        self.assertEqual([path.name for path in result.sdists],
                         ["{0}.tar.gz".format(ARTIFACT_STEM)],
                         result.diagnosis())

    def test_the_wheel_is_pure_python_and_universal(self):
        """``py3-none-any`` is the shape a zero-dependency stdlib package has. A
        platform tag would mean something got compiled, which nothing here does."""
        self.assertTrue(built().wheel.name.endswith("-py3-none-any.whl"),
                        built().wheel.name)

    def test_the_sdist_carries_the_build_inputs_and_not_the_generator(self):
        """An sdist that cannot rebuild itself is a release nobody can audit.
        ``build`` already proves the point by building the wheel from this sdist;
        this test states which members that depends on."""
        with tarfile.open(built().sdist) as archive:
            members = {name.split("/", 1)[1]
                       for name in archive.getnames() if "/" in name}
        for required in ("pyproject.toml", "setup.py",
                         "packaging/machina_sports_canonical/build.py"):
            with self.subTest(member=required):
                self.assertIn(required, members)
        self.assertNotIn("tools/iptc/canonical/{0}".format(GENERATOR_MODULE),
                         members)


# ---------------------------------------------------------------------------
# 2-4. A clean interpreter installs it offline and can use it
# ---------------------------------------------------------------------------


class TestACleanInterpreterInstallsAndImportsIt(unittest.TestCase):
    """Installed with ``--no-index`` into a throwaway venv, then used from a
    neutral directory. An import that only works from the repository root is not a
    package, and a resource that only loads beside the repository is not shipped."""

    def setUp(self):
        self.venv_python = clean_install(sys.executable, "primary")

    def test_clean_venv_import(self):
        result = probe(self.venv_python,
                       "import json\n"
                       "import machina_sports_canonical as package\n"
                       "print(json.dumps({'file': package.__file__}))\n",
                       "import")
        self.assertEqual(result.returncode, 0, result.stderr)
        location = Path(probe_payload(result)["file"]).resolve()
        self.assertEqual(location.parent, installed_root(self.venv_python))
        self.assertNotIn(CANONICAL_ROOT, location.parents)

    def test_constants_functions_and_adapters_import(self):
        adapters = adapter_modules()
        self.assertTrue(adapters, "no adapter modules found to prove")
        body = (
            "import importlib, json\n"
            "from machina_sports_canonical import (\n"
            "    PROFILE_VERSION, SCHEMA_VERSION, MACHINA_SCHEMA_VERSION,\n"
            "    SERIALIZER_NAME, SERIALIZER_VERSION, UPSTREAM_COMMIT,\n"
            "    UPSTREAM_REPOSITORY, UPSTREAM_TARGET_VERSION)\n"
            "from machina_sports_canonical.observation import validate_observation\n"
            "from machina_sports_canonical.serialize import (\n"
            "    canonical_envelope, event_view, provenance_block,\n"
            "    provider_identifiers, shared_context, sport_schema_graph)\n"
            "from machina_sports_canonical.capabilities import capability_report\n"
            "from machina_sports_canonical.rights import rights_findings\n"
            "from machina_sports_canonical.ids import surrogate_resolver\n"
            "from machina_sports_canonical.vocab import newscode\n"
            "loaded = []\n"
            "for name in {0!r}:\n"
            "    module = importlib.import_module(\n"
            "        'machina_sports_canonical.adapters.' + name)\n"
            "    assert callable(module.to_observation), name\n"
            "    loaded.append(name)\n"
            "print(json.dumps({{'profile': PROFILE_VERSION,\n"
            "                  'schema': SCHEMA_VERSION,\n"
            "                  'envelope': MACHINA_SCHEMA_VERSION,\n"
            "                  'serializer': SERIALIZER_NAME,\n"
            "                  'adapters': loaded,\n"
            "                  'callables': [f.__name__ for f in (\n"
            "                      validate_observation, canonical_envelope,\n"
            "                      event_view, provenance_block,\n"
            "                      provider_identifiers, shared_context,\n"
            "                      sport_schema_graph, capability_report,\n"
            "                      rights_findings, surrogate_resolver,\n"
            "                      newscode)]}}))\n"
        ).format(adapters)
        result = probe(self.venv_python, body, "api")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = probe_payload(result)
        self.assertEqual(payload["adapters"], adapters)
        self.assertEqual(payload["profile"], "machina-iptc-profile/1.1")
        self.assertEqual(payload["schema"], "canonical-observation/1")
        self.assertEqual(payload["envelope"], "machina-sports-schema/1")
        self.assertEqual(len(payload["callables"]), 11)

    def test_json_resources_load_offline(self):
        """Both resources are read through ``__file__``, so this is the assertion
        that separates "the wheel lists them" from "the wheel ships them where the
        code looks". The socket module is disabled before the import."""
        body = (
            "import json, pathlib, sys\n"
            "import machina_sports_canonical as package\n"
            "from machina_sports_canonical import observation, serialize\n"
            "base = pathlib.Path(package.__file__).resolve().parent\n"
            "context = serialize.shared_context()\n"
            "curies = observation.official_property_curies()\n"
            "receipt = json.loads((base / 'package-receipt.json')\n"
            "                     .read_text(encoding='utf-8'))\n"
            "print(json.dumps({'base': str(base),\n"
            "                  'context_path': str(serialize.SHARED_CONTEXT_PATH),\n"
            "                  'context_terms': len(context),\n"
            "                  'curies': len(curies),\n"
            "                  'receipt_version': receipt['distribution_version'],\n"
            "                  'sys_path': [str(entry) for entry in sys.path]}))\n"
        )
        result = probe(self.venv_python, body, "resources")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = probe_payload(result)
        base = Path(payload["base"])
        self.assertEqual(base, installed_root(self.venv_python))
        self.assertEqual(Path(payload["context_path"]).parent, base)
        self.assertGreater(payload["context_terms"], 0)
        self.assertGreater(payload["curies"], 0)
        self.assertEqual(payload["receipt_version"], VERSION)

    def test_the_resource_probe_cannot_reach_back_into_this_repository(self):
        """The guard behind the test above: if the repository were on the probe's
        path, loading a resource from the repository copy would be indistinguishable
        from loading it from the wheel."""
        result = probe(self.venv_python,
                       "import json, sys\n"
                       "print(json.dumps({'sys_path': list(sys.path)}))\n",
                       "syspath")
        self.assertEqual(result.returncode, 0, result.stderr)
        for entry in probe_payload(result)["sys_path"]:
            if not entry:
                continue
            with self.subTest(entry=entry):
                resolved = Path(entry).resolve()
                self.assertFalse(resolved == REPO_ROOT
                                 or REPO_ROOT in resolved.parents,
                                 "{0} reaches this repository".format(entry))

    def test_the_network_guard_in_the_probe_actually_bites(self):
        """Guard the guard. A disabled socket module that still connects would make
        every "offline" claim in this suite decorative."""
        result = probe(self.venv_python,
                       "import socket\n"
                       "socket.create_connection(('example.invalid', 80))\n",
                       "network")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NetworkReached", result.stderr)


# ---------------------------------------------------------------------------
# 5. The shipped bytes are the authoritative bytes
# ---------------------------------------------------------------------------


class TestTheInstalledBytesAreTheAuthoritativeBytes(unittest.TestCase):
    """The load-bearing fidelity check.

    If this class fails because packaging rewrote or reformatted a source file,
    the answer is to stop packaging from transforming it — never to regenerate the
    manifest from the installed copy, which would compare the artefact with
    itself and assert nothing at all.
    """

    def setUp(self):
        self.venv_python = clean_install(sys.executable, "primary")
        self.root = installed_root(self.venv_python)
        self.manifest = vendored_manifest()

    def test_installed_core_hashes_equal_the_vendored_manifest(self):
        for name, recorded in sorted(self.manifest["files"].items()):
            with self.subTest(name=name):
                installed = self.root / name
                self.assertTrue(installed.is_file(),
                                "core file missing from the wheel: {0}".format(name))
                self.assertEqual(sha256_bytes(installed.read_bytes()), recorded)

    def test_the_receipt_core_manifest_equals_the_vendored_manifest(self):
        receipt = json.loads((self.root / "package-receipt.json")
                             .read_text(encoding="utf-8"))
        self.assertEqual(receipt["core_manifest"], self.manifest["files"])
        self.assertEqual(receipt["distribution_version"], VERSION)
        self.assertEqual(receipt["source"],
                         "machina-templates:tools/iptc/canonical")
        self.assertEqual(receipt["source_commit"], self.manifest["source_commit"])
        self.assertRegex(receipt["source_commit"], r"^[0-9a-f]{40}$")

    def test_every_installed_runtime_file_is_byte_equal_to_its_source(self):
        """Wider than the nine-file core: the adapters and the JSON resources ship
        in the wheel but sit outside the sports-skills receipt, so nothing else
        would compare them with the files they were built from."""
        for member in sorted(expected_runtime_members()):
            with self.subTest(member=member):
                installed = self.root / member
                self.assertTrue(installed.is_file(),
                                "not installed: {0}".format(member))
                self.assertEqual(installed.read_bytes(),
                                 (CANONICAL_ROOT / member).read_bytes())

    def test_no_installed_runtime_file_is_unaccounted_for(self):
        """Both directions. A file the wheel adds is as much a change to a
        published package as a file it drops."""
        self.assertEqual(sorted(installed_members(self.venv_python)),
                         sorted(expected_runtime_members()))

    def test_the_receipt_is_present_and_is_data_rather_than_code(self):
        receipt = self.root / "package-receipt.json"
        self.assertTrue(receipt.is_file())
        self.assertIsInstance(json.loads(receipt.read_text(encoding="utf-8")), dict)
        self.assertNotIn("package_receipt.py", installed_members(self.venv_python))

    def test_the_generator_is_still_in_this_repository(self):
        """Excluded from the wheel, not deleted. It regenerates
        ``official-property-names.json`` from the pinned upstream ontologies, which
        exist only here."""
        self.assertTrue((CANONICAL_ROOT / GENERATOR_MODULE).is_file())

    def test_the_only_non_python_source_files_are_the_declared_resources(self):
        """So a new JSON resource cannot slip past ``expected_runtime_members``
        by being neither a module nor a declared resource."""
        others = set()
        for path in sorted(CANONICAL_ROOT.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts or path.suffix == ".py":
                continue
            others.add(path.relative_to(CANONICAL_ROOT).as_posix())
        self.assertEqual(sorted(others), sorted(JSON_RESOURCES))


# ---------------------------------------------------------------------------
# 6-7. The floor is 3.9, the standard library is the whole dependency set
# ---------------------------------------------------------------------------


class TestThePackagedCodeHoldsItsConstraints(unittest.TestCase):
    """Checked against the *installed* files. The source tree is already gated by
    ``tests/test_iptc_vendored_manifest.py``; what a consumer runs is this."""

    def setUp(self):
        self.venv_python = clean_install(sys.executable, "primary")
        self.root = installed_root(self.venv_python)
        self.modules = sorted(member for member in
                              installed_members(self.venv_python)
                              if member.endswith(".py"))

    def test_python39_parse_and_stdlib_only(self):
        self.assertTrue(self.modules)
        for member in self.modules:
            source = (self.root / member).read_text(encoding="utf-8")
            with self.subTest(member=member):
                self.assertTrue(parses_on_python_39(source),
                                "{0} uses syntax Python 3.9 rejects".format(member))
            for root in absolute_import_roots(ast.parse(source, filename=member)):
                with self.subTest(member=member, imports=root):
                    self.assertTrue(
                        root == IMPORT_NAME or is_standard_library(root),
                        "{0} imports {1}, which is neither the standard library "
                        "of this interpreter nor the package itself".format(
                            member, root))

    def test_the_standard_library_check_is_real_and_not_permissive(self):
        """The dependency claim is only worth the check behind it.

        A check that answered "standard library" for everything would make
        ``test_python39_parse_and_stdlib_only`` pass while a packaged module
        imported ``rdflib``. So both directions are proved on whichever
        interpreter is running: real standard library modules in, and the two
        distributions ``requirements-iptc-build.txt`` guarantees are installed on
        every leg out.

        Those two and no others. ``pip`` is the obvious third probe and it is
        deliberately not used: on Python before 3.12, resolving the name ``pip``
        makes setuptools' distutils shim stand down for the rest of the process,
        so a later ``import setuptools`` — which the build filter does — dies on
        an assertion inside ``_distutils_hack``. Probing for a negative must not
        change the interpreter it is probing.
        """
        for name in ("ast", "collections", "hashlib", "importlib", "json",
                     "os", "pathlib", "re", "sys", "typing"):
            with self.subTest(stdlib=name):
                self.assertTrue(is_standard_library(name))
        for name in ("build", "setuptools"):
            with self.subTest(third_party=name):
                self.assertFalse(is_standard_library(name))
        self.assertFalse(is_standard_library(IMPORT_NAME))
        self.assertFalse(is_standard_library("no_such_top_level_module_at_all"))

    def test_no_test_helper_reaches_for_an_attribute_the_floor_lacks(self):
        """The regression this locks: ``sys.stdlib_module_names`` is 3.10+, so on
        the declared floor this suite raised AttributeError twenty times over
        before it could answer anything about the floor. Invisible on 3.12, which
        is why it is asserted rather than remembered. Prose may name the
        attribute; code may not — the scan reads attribute nodes, not text.
        """
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        offenders = sorted({node.attr for node in ast.walk(tree)
                            if isinstance(node, ast.Attribute)
                            and node.attr in FLOOR_HOSTILE_ATTRIBUTES})
        self.assertEqual(offenders, [])

    def test_the_python_39_check_rejects_newer_syntax(self):
        """Guard the guard: without ``feature_version`` every one of these parses
        under the interpreter running the suite."""
        for newer in ("match x:\n    case 1:\n        pass\n",
                      "type Alias = int\n"):
            with self.subTest(snippet=newer.splitlines()[0]):
                self.assertFalse(parses_on_python_39(newer))
        self.assertTrue(parses_on_python_39("import json\nx: int = 1\n"))

    def test_no_packaged_module_imports_tools(self):
        """``tools`` does not exist inside an installed wheel, so one such import
        is an ImportError the first time a connector runs."""
        for member in self.modules:
            tree = ast.parse((self.root / member).read_text(encoding="utf-8"))
            with self.subTest(member=member):
                self.assertNotIn("tools", absolute_import_roots(tree))

    def test_zero_runtime_dependencies(self):
        """Read off the installed metadata rather than off ``pyproject.toml``: a
        dependency added by a build hook would not appear in the source config."""
        distinfo = purelib(self.venv_python) / "{0}.dist-info".format(ARTIFACT_STEM)
        self.assertTrue(distinfo.is_dir(), distinfo)
        metadata = (distinfo / "METADATA").read_text(encoding="utf-8")
        requires = [line for line in metadata.splitlines()
                    if line.startswith("Requires-Dist")]
        self.assertEqual(requires, [])
        self.assertIn("Name: {0}".format(DISTRIBUTION), metadata)
        self.assertIn("Version: {0}".format(VERSION), metadata)
        self.assertIn("Requires-Python: >=3.9", metadata)

    def test_the_wheel_metadata_agrees_with_the_installed_metadata(self):
        metadata = wheel_metadata(built().wheel)
        self.assertNotIn("\nRequires-Dist", metadata)
        self.assertIn("Name: {0}".format(DISTRIBUTION), metadata)
        self.assertIn("Version: {0}".format(VERSION), metadata)


# ---------------------------------------------------------------------------
# 8. The wheel is a closed set and the filter has exactly one exclusion
# ---------------------------------------------------------------------------


class TestTheWheelIsAClosedSet(unittest.TestCase):
    """A build filter with a free-form exclusion list can drop a module and still
    produce a valid-looking wheel. So the exclusion is pinned to one name, and the
    filter is asked to reject anything else."""

    def setUp(self):
        self.record = wheel_record(built().wheel)
        self.runtime = sorted(entry[len(IMPORT_NAME) + 1:] for entry in self.record
                              if entry.startswith(IMPORT_NAME + "/"))

    def test_the_record_lists_exactly_the_expected_runtime_members(self):
        self.assertEqual(self.runtime, sorted(expected_runtime_members()))

    def test_wheel_record_excludes_the_generator(self):
        self.assertNotIn("{0}/{1}".format(IMPORT_NAME, GENERATOR_MODULE),
                         self.record)

    def test_every_record_entry_is_runtime_or_distribution_metadata(self):
        stray = [entry for entry in self.record
                 if not entry.startswith(IMPORT_NAME + "/")
                 and not entry.startswith("{0}.dist-info/".format(ARTIFACT_STEM))]
        self.assertEqual(stray, [])

    def test_the_record_accounts_for_every_member_of_the_archive(self):
        """"Closed" in both directions: a file present in the zip but absent from
        RECORD is a file no installer verifies."""
        with zipfile.ZipFile(built().wheel) as archive:
            members = [name for name in archive.namelist()
                       if not name.endswith("/")]
        self.assertEqual(sorted(members), sorted(self.record))

    def test_no_bytecode_or_cache_ships(self):
        for entry in self.record:
            with self.subTest(entry=entry):
                self.assertNotIn("__pycache__", entry)
                self.assertFalse(entry.endswith(".pyc"))

    def test_the_build_filter_excludes_exactly_one_module(self):
        module = build_filter()
        self.assertEqual(sorted(module.EXCLUDED_MODULES),
                         ["{0}.{1}".format(IMPORT_NAME,
                                           GENERATOR_MODULE[: -len(".py")])])

    def test_the_build_filter_rejects_any_other_exclusion(self):
        """The assertion that makes the filter safe rather than merely correct
        today: it is not a place a module can be quietly removed from a release."""
        module = build_filter()
        for forbidden in ("{0}.serialize".format(IMPORT_NAME),
                          "{0}.adapters.api_football".format(IMPORT_NAME),
                          "{0}.__init__".format(IMPORT_NAME)):
            with self.subTest(forbidden=forbidden):
                with self.assertRaises(ValueError):
                    module.validate_exclusions({forbidden})
        self.assertEqual(module.validate_exclusions(module.EXCLUDED_MODULES),
                         frozenset(module.EXCLUDED_MODULES))


# ---------------------------------------------------------------------------
# The clean-install proof, repeated on the floor and on the image interpreter
# ---------------------------------------------------------------------------


class TestTheProofHoldsOnEveryDeclaredInterpreter(unittest.TestCase):
    """3.9 is the declared floor; 3.11 is what the client image runs. A missing
    interpreter is an explicit, printed skip — never a silent pass."""

    def prove(self, version: str):
        python_exe = interpreter(version)
        if python_exe is None:
            self.skipTest("no Python {0} interpreter on PATH; the clean-install "
                          "proof did not run for it".format(version))
        venv_python = clean_install(python_exe, version)
        body = (
            "import hashlib, json, pathlib\n"
            "import machina_sports_canonical as package\n"
            "from machina_sports_canonical import observation, serialize\n"
            "base = pathlib.Path(package.__file__).resolve().parent\n"
            "digests = {}\n"
            "for path in sorted(base.rglob('*')):\n"
            "    if path.is_dir() or '__pycache__' in path.parts:\n"
            "        continue\n"
            "    digests[path.relative_to(base).as_posix()] = \\\n"
            "        hashlib.sha256(path.read_bytes()).hexdigest()\n"
            "print(json.dumps({'version': package.PROFILE_VERSION,\n"
            "                  'context_terms': len(serialize.shared_context()),\n"
            "                  'curies': len(observation.official_property_curies()),\n"
            "                  'digests': digests}))\n"
        )
        result = probe(venv_python, body, "proof-{0}".format(version))
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = probe_payload(result)
        self.assertEqual(payload["version"], "machina-iptc-profile/1.1")
        self.assertGreater(payload["context_terms"], 0)
        self.assertGreater(payload["curies"], 0)
        self.assertEqual(sorted(payload["digests"]),
                         sorted(expected_runtime_members()))
        for name, recorded in sorted(vendored_manifest()["files"].items()):
            with self.subTest(version=version, name=name):
                self.assertEqual(payload["digests"][name], recorded)

    def test_python_3_9_installs_imports_loads_resources_and_matches_hashes(self):
        self.prove("3.9")

    def test_python_3_11_installs_imports_loads_resources_and_matches_hashes(self):
        self.prove("3.11")

    def test_the_declared_interpreters_are_the_ones_the_proof_runs(self):
        """So the pair cannot shrink to one without the change being visible."""
        self.assertEqual(PROVEN_INTERPRETERS, ("3.9", "3.11"))

    def test_the_running_interpreter_proves_itself_rather_than_one_found_on_path(self):
        """On a matrix leg, the interpreter under proof is the one running this
        suite — the one the job selected and installed the pinned tooling into.

        Resolving ``python<version>`` on PATH instead answers a different
        question twice over: it can find a *different* build of the same version,
        and it can find nothing at all and turn that leg's own proof into a skip.
        A skipped proof on the leg that exists to run it is the exact failure this
        assertion exists to prevent, so it is stated for whatever is running,
        3.12 included.
        """
        running = "{0}.{1}".format(*sys.version_info[:2])
        self.assertEqual(interpreter(running), sys.executable)


# ---------------------------------------------------------------------------
# CI actually runs the proof above on those interpreters
# ---------------------------------------------------------------------------


class TestCiRunsThisProofOnEveryDeclaredInterpreter(unittest.TestCase):
    """Everything above degrades to a skip on an interpreter that is not
    installed, and a skip is green.

    While the only job in this workflow selected 3.12, the 3.9 floor and the 3.11
    client-image claim were proved on developer machines and nowhere else: the
    remote run reported them passing without executing either. So the shape of
    the workflow is asserted here, beside the proofs whose truth depends on it.
    """

    def setUp(self):
        self.jobs = workflow_jobs()
        self.proof = self.jobs.get(PACKAGE_PROOF_JOB, "")
        self.validation = self.jobs.get(VALIDATION_JOB, "")

    def test_a_dedicated_package_proof_job_exists_beside_the_validation_job(self):
        self.assertIn(VALIDATION_JOB, self.jobs)
        self.assertIn(PACKAGE_PROOF_JOB, self.jobs,
                      "no job runs the package proof on the declared "
                      "interpreters: {0}".format(sorted(self.jobs)))

    def test_the_proof_job_matrix_is_exactly_the_declared_interpreters(self):
        """The same pair the proofs above name, in the same order. A matrix that
        drifted from ``PROVEN_INTERPRETERS`` would run one set and claim the
        other."""
        self.assertEqual(matrix_python_versions(self.proof),
                         list(PROVEN_INTERPRETERS))

    def test_the_proof_job_selects_the_matrix_interpreter(self):
        """A matrix that every leg ignores is three identical runs of one
        interpreter wearing three names."""
        self.assertIn("python-version: ${{ matrix.python-version }}", self.proof)

    def test_the_proof_job_installs_the_pinned_build_tooling_and_runs_this_suite(self):
        commands = run_commands(self.proof)
        self.assertIn("python -m pip install -r {0}".format(BUILD_REQUIREMENTS),
                      commands)
        self.assertIn("python {0} -v".format(PACKAGE_PROOF_SUITE), commands)

    def test_the_proof_job_stays_focused_on_this_suite(self):
        """It is the same suite three times over, so it buys nothing by running
        the rest of the tree again — and the manifest runner is the validation
        job's answer, not this one's."""
        for command in run_commands(self.proof):
            with self.subTest(command=command):
                self.assertNotIn("run_test_suites.py", command)
        named = [command for command in run_commands(self.proof)
                 if "tests/test_iptc_" in command]
        self.assertEqual(named, ["python {0} -v".format(PACKAGE_PROOF_SUITE)])

    def test_the_validation_job_stays_on_one_interpreter_and_keeps_every_gate(self):
        """The matrix is additive. If proving two more interpreters cost the pin
        check, the manifest run or the clean-tree check, the trade would be a bad
        one."""
        self.assertIn('python-version: "{0}"'.format(VALIDATION_PYTHON),
                      self.validation)
        self.assertEqual(matrix_python_versions(self.validation), [])
        commands = run_commands(self.validation)
        for gate in ("python -m pip install -r requirements-iptc-validator.txt",
                     "python -m tools.iptc --verify-pin",
                     "python tools/iptc/run_test_suites.py --list",
                     "python tools/iptc/run_test_suites.py --verbose",
                     "python -m tools.iptc --check"):
            with self.subTest(gate=gate):
                self.assertIn(gate, commands)
        self.assertTrue(any("git status --porcelain" in command
                            for command in commands))

    def test_the_validation_job_installs_build_tooling_only_from_the_pinned_file(self):
        self.assertIn("python -m pip install -r {0}".format(BUILD_REQUIREMENTS),
                      run_commands(self.validation))

    def test_no_install_step_in_this_workflow_is_ranged_or_unpinned(self):
        """The second finding, stated as a property of every job rather than of
        the one line that had it: an install argument that is not a checked-in
        requirements file is a version this repository does not record."""
        for name, block in sorted(self.jobs.items()):
            for command in run_commands(block):
                if "pip install" not in command:
                    continue
                with self.subTest(job=name, command=command):
                    self.assertRegex(
                        command,
                        r"^python -m pip install -r [A-Za-z0-9._/-]+\.txt$",
                        "install neither pinned nor from a checked-in file")

    def test_the_build_requirements_file_is_checked_in_and_exactly_pinned(self):
        path = REPO_ROOT / BUILD_REQUIREMENTS
        self.assertTrue(path.is_file(), "missing: {0}".format(BUILD_REQUIREMENTS))
        pinned = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            with self.subTest(requirement=line):
                self.assertRegex(line, r"^[A-Za-z0-9][A-Za-z0-9._-]*==[0-9][^ ]*$",
                                 "not an exact pin: {0}".format(line))
            pinned.append(line.split("==")[0].lower())
        self.assertEqual(sorted(pinned), sorted(BUILD_REQUIREMENT_NAMES))

    def test_both_path_filters_reach_every_input_this_proof_depends_on(self):
        blocks = path_filter_blocks()
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0], blocks[1],
                         "one trigger is narrower than the other, so the gate "
                         "depends on how the change arrived")
        for path in PACKAGING_INPUTS_THE_FILTERS_MUST_REACH:
            with self.subTest(path=path):
                self.assertTrue(reached_by(path, blocks[0]),
                                "no path filter reaches {0}".format(path))

    def test_the_workflow_reader_separates_jobs_and_reads_steps_not_prose(self):
        """Guard the guard. Every assertion in this class is only as good as the
        two readers under it: one that told jobs apart wrongly would let a step in
        one job satisfy a claim about another, and one that read comments would
        let the explanation of a step stand in for the step."""
        sample = (
            "jobs:\n"
            "  validate:\n"
            "    steps:\n"
            "      # run: python -m pip install \"build>=1.0\"\n"
            "      - run: python -m pip install -r requirements-iptc-build.txt\n"
            "      - run: |\n"
            "          if [ -n \"$(git status --porcelain)\" ]; then\n"
            "            exit 1\n"
            "          fi\n"
            "  package-proof:\n"
            "    strategy:\n"
            "      matrix:\n"
            "        python-version: [\"3.9\", \"3.11\"]\n"
            "    steps:\n"
            "      - run: python tests/test_iptc_canonical_package.py -v\n"
        )
        jobs = workflow_jobs(sample)
        self.assertEqual(sorted(jobs), ["package-proof", "validate"])
        self.assertEqual(run_commands(jobs["validate"]), [
            "python -m pip install -r requirements-iptc-build.txt",
            'if [ -n "$(git status --porcelain)" ]; then',
            "exit 1",
            "fi",
        ])
        self.assertEqual(run_commands(jobs["package-proof"]),
                         ["python tests/test_iptc_canonical_package.py -v"])
        self.assertEqual(matrix_python_versions(jobs["package-proof"]),
                         ["3.9", "3.11"])
        self.assertEqual(matrix_python_versions(jobs["validate"]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
