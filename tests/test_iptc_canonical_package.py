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
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
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

    Resolved by asking the candidate what it is rather than trusting its name: a
    ``python3.9`` on PATH that is a shim for something else would otherwise turn
    the 3.9 proof into a 3.12 one.
    """
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


def absolute_import_roots(tree: ast.Module) -> list:
    roots = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            roots.append((node.module or "").split(".")[0])
    return roots


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
                    self.assertIn(root,
                                  set(sys.stdlib_module_names) | {IMPORT_NAME})

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
