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
shared; the disposable tree is removed in ``tearDownModule``. *Which* frontend
closure that is, is itself gated: ``requirements-iptc-build.txt`` pins every
distribution the frontend executes, and this suite walks the installed metadata
to prove the pinned set is still the whole set.
"""

from __future__ import annotations

import ast
import csv
import fnmatch
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

# Not an outside dependency this suite reaches for: `packaging` is a member of
# the closure it checks below, pinned in `requirements-iptc-build.txt` and
# imported by `build` itself, so every leg that can run this file at all has it.
# Hand-rolling requirement parsing and marker evaluation instead would mean this
# suite decided what `python_version < "3.11"` means and then proved its own
# opinion. Imported before `REPO_ROOT` is put on `sys.path` below, so the
# repository's own root `packaging/` directory cannot get in the way.
import packaging
from packaging.markers import Marker
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

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

#: The roots of what that file pins: the PEP 517 frontend, the backend
#: `pyproject.toml` names, and the helper its `build-system.requires` lists
#: beside that backend. Roots, not the whole set — the frontend executes more
#: than itself, and the closure below is what actually runs.
BUILD_REQUIREMENT_NAMES = ("build", "setuptools", "wheel")

#: The complete pinned execution closure: the three roots and every distribution
#: `build` resolves underneath them, each with the marker that says when it is
#: needed. Pinning only the roots left the frontend's own helpers to the
#: resolver, so the validate leg, the 3.9 leg and the 3.11 leg could each build
#: with a different `packaging`, `pyproject_hooks` or `tomli` while the diff
#: showed one pinned file — which made "identical build tooling on every leg" a
#: claim this repository could not support.
#:
#: The conditional four are conditional for a reason, not for symmetry.
#: `importlib-metadata` and its own `zipp` are what `build` falls back to below
#: 3.10.2; `tomli` is the TOML reader before `tomllib` existed in 3.11; and
#: `colorama` is Windows-only. Every pin here that is active on Linux or macOS
#: publishes wheels for 3.9, so the declared floor installs this file unchanged.
BUILD_REQUIREMENT_CLOSURE = (
    ("build", "1.4.4", ""),
    ("packaging", "26.3", ""),
    ("pyproject-hooks", "1.2.0", ""),
    ("setuptools", "82.0.1", ""),
    ("wheel", "0.47.0", ""),
    ("colorama", "0.4.6", 'os_name == "nt"'),
    ("importlib-metadata", "8.7.0", 'python_full_version < "3.10.2"'),
    ("tomli", "2.2.1", 'python_version < "3.11"'),
    ("zipp", "3.23.0", 'python_full_version < "3.10.2"'),
)

#: The only name the closure walk does not require a pin for. Every venv is
#: created with `pip` in it whether a requirements file names it or not, so
#: demanding a pin for it would fail on a correct install. Nothing else is
#: exempt: `setuptools` and `wheel` also arrive with some venvs, and they are
#: pinned anyway, because the build imports them.
BUILD_CLOSURE_BOOTSTRAP = ("pip",)

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

#: The tag that releases this version, spelled exactly. Distribution-scoped
#: rather than a bare `v0.1.0`: this repository also releases templates, and a
#: shared tag namespace makes one release trigger the other's workflow.
RELEASE_TAG = "{0}-v{1}".format(DISTRIBUTION, VERSION)

#: The pattern the publish workflow triggers on. Version-open so 0.1.1 needs no
#: workflow edit, distribution-scoped so nothing else in the namespace matches.
RELEASE_TAG_GLOB = "{0}-v*".format(DISTRIBUTION)

#: The release automation, and the document that says when a human may use it.
PUBLISH_WORKFLOW_PATH = (REPO_ROOT
                         / ".github/workflows/publish-machina-sports-canonical.yml")
RELEASE_DOCS_PATH = REPO_ROOT / "docs/iptc/RELEASING.md"

#: Two jobs, because approval has to sit between building and uploading. The
#: build job produces the artefacts with no upload scope at all; the publish job
#: has the OIDC scope and does nothing but verify and upload.
RELEASE_BUILD_JOB = "build"
RELEASE_PUBLISH_JOB = "publish"

#: The GitHub environment the publish job runs in. The reviewer requirement lives
#: on the environment, not in this repository — which is exactly why
#: `docs/iptc/RELEASING.md` has to spell out that it must be configured, and why
#: this suite asserts the job is bound to it.
PYPI_ENVIRONMENT = "pypi"

#: The action that exchanges the job's short-lived OIDC token for an upload
#: token. No password, no username, no long-lived secret in this repository.
TRUSTED_PUBLISHER_ACTION = "pypa/gh-action-pypi-publish"

#: What the build job records beside the artefacts, and what the publish job
#: checks before uploading them. The point of publishing the digests is that a
#: reviewer can compare what PyPI serves with what was approved.
RELEASE_DIGEST_FILE = "SHA256SUMS"

#: The reviewed digests, checked in. `RELEASE_DIGEST_FILE` is what a run
#: *produces*; this file is what a human *approved*, and without it every check in
#: this repository compared a build with itself. Each 3.9 and 3.11 matrix leg
#: proved only that its own build was stable, `docs/iptc/RELEASING.md` promised
#: "the digests below" and had none, and the release checklist's "compare the
#: published digest with the reviewed one" named no artefact to compare against.
#: One checked-in file makes cross-interpreter reproducibility falsifiable: a leg
#: whose bytes differ fails against the same rows every other leg passes against.
RELEASE_CHECKSUM_FILE = "docs/iptc/machina-sports-canonical-0.1.0.sha256"
RELEASE_CHECKSUM_PATH = REPO_ROOT / RELEASE_CHECKSUM_FILE

#: Exactly the rows that file carries, in exactly that order: the wheel, then the
#: sdist — the order `sha256sum *.whl *.tar.gz` produces, so the file is byte-equal
#: to what every job generates and `diff -u` reports a real difference rather than
#: a reordering.
#:
#: BASENAMES, NOT PATHS. The same two rows have to be the authority for a build in
#: a checkout root (`dist/`), a build into `$RUNNER_TEMP` (an absolute path) and
#: the `sha256sum --check` the publish job runs from inside the downloaded `dist`.
#: A path prefix would make each of those a different file and the comparison
#: unperformable in two of the three.
REVIEWED_RELEASE_DIGESTS = (
    ("{0}-py3-none-any.whl".format(ARTIFACT_STEM),
     "3c7fcbc539824ced118099f691ac23c3182c59ad0855aaec560d43dabb53361b"),
    ("{0}.tar.gz".format(ARTIFACT_STEM),
     "11783dd7fff89b634e55bccdd17952679b8f7362fe9fd0bfa8a378a5dbe8d324"),
)

#: The one artefact that crosses the approval gate. The publish job downloads it
#: and uploads those bytes; it never builds. Version-free, so releasing 0.1.1
#: needs no edit to the workflow — the tag pattern is version-open too.
RELEASE_ARTIFACT_NAME = "{0}-release".format(DISTRIBUTION)

#: The commit the canonical source bytes come from, as `package-receipt.json`
#: records it, and its committer timestamp.
#:
#: THE TIMESTAMP IS THE RELEASE EPOCH. `zip` and `tar` both store an mtime per
#: member, so two builds of identical bytes produce different archives and
#: therefore different digests — which makes "the published hash equals the hash
#: you reviewed" impossible to check. `SOURCE_DATE_EPOCH` replaces every stored
#: timestamp with one fixed value. It is the source commit's own time rather than
#: an arbitrary constant so the number in the workflow can be re-derived from the
#: tree it describes.
CANONICAL_SOURCE_COMMIT = "cf433075666de002e38fb3bd6f5dd8743e7caeb2"
RELEASE_SOURCE_DATE_EPOCH = "1786398569"

#: The one place a release is built. `SOURCE_DATE_EPOCH` is enough for the wheel —
#: `wheel` stamps every zip entry with it — and this backend's sdist ignores it
#: entirely, so the tar carried the source files' mtimes, the build time on every
#: generated member, and the builder's uid, gid and umask. The helper builds with
#: the epoch and then rewrites those machine facts out of the sdist, touching no
#: payload and no member order. Tests and the release workflow run this same
#: command, so neither can be reproducible while the other is not.
RELEASE_HELPER = "packaging/machina_sports_canonical/release.py"

#: The mtimes the two staging copies are stamped with. Different on purpose: see
#: `stage_packaging_inputs`.
REPRODUCTION_MTIMES = (1000000000, 1700000000)

#: Repository paths that are present when the release job builds — it builds from
#: a checkout root — and that `setuptools`' sdist defaults sweep in on their own:
#: every root `README*`, and every `tests/test*.py`. Both were in the sdist a root
#: build produced while the proof suite, which builds from the staged subset, had
#: never seen either. `MANIFEST.in` now excludes them, and the check below builds a
#: staging copy that holds them so the exclusion is proved rather than assumed.
REPOSITORY_NOISE = ("README.md", "tests")

#: Exactly what a released sdist contains, relative to its root directory. Spelled
#: out rather than counted: the members that leaked in were the repository's own
#: README and twenty test suites, and a length check would have accepted them.
#: `setup.cfg`, `PKG-INFO` and the `egg-info` members are generated by the backend.
EXPECTED_SDIST_MEMBERS = (
    "MANIFEST.in",
    "PKG-INFO",
    "README-machina-sports-canonical.md",
    "machina_sports_canonical.egg-info/PKG-INFO",
    "machina_sports_canonical.egg-info/SOURCES.txt",
    "machina_sports_canonical.egg-info/dependency_links.txt",
    "machina_sports_canonical.egg-info/top_level.txt",
    "packaging/machina_sports_canonical/build.py",
    "packaging/machina_sports_canonical/release.py",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
)

#: Either of these in the wheel `METADATA` means an owner has approved license
#: metadata for this distribution. Today neither is there, deliberately: this
#: repository has no root license and packaging must not invent one. So the
#: publish job refuses to upload, and the refusal is a checked-in, executable
#: gate rather than a note in a document.
LICENSE_METADATA_FIELDS = ("License-Expression", "License-File")

#: Ways a publish workflow can carry an upload credential of its own. Trusted
#: publishing needs none of them, so any of them appearing is a regression from
#: OIDC back to a long-lived token — including `secrets.`, because this workflow
#: has no legitimate use for a secret at all.
CREDENTIAL_MARKERS = (
    "PYPI_API_TOKEN",
    "PYPI_TOKEN",
    "TWINE_PASSWORD",
    "TWINE_USERNAME",
    "password:",
    "username:",
    "secrets.",
)

#: Every `uses:` in the release workflow, as it must be written: an immutable
#: 40-hex commit SHA, with the ref it was taken from in a comment beside it.
#:
#: A tag is not a pin. `actions/checkout@v4` and `pypa/gh-action-pypi-publish@
#: release/v1` are mutable refs that whoever controls those repositories can move
#: after review — and in this workflow they run in the job holding the OIDC
#: identity that PyPI accepts for this distribution, or in the job that produces
#: the bytes that job uploads. The rest of this file goes to some length to make
#: the released artefact exactly the reviewed one; a floating action ref hands the
#: whole chain to a third party's tag. The comment is required because a bare SHA
#: says nothing about what it is, and an unreadable pin is one nobody updates.
PINNED_USES = re.compile(r"^uses:\s+[A-Za-z0-9._/-]+@[0-9a-f]{40}\s+#\s*\S+")

#: Anything that would produce a distribution. Forbidden in the publish job: a
#: rebuild after approval publishes bytes nobody reviewed, however identical the
#: build is believed to be.
REBUILD_MARKERS = ("-m build", "pip wheel", "setup.py", "pip install -e",
                   "release.py")

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
_REPRODUCTIONS = {}


def workspace() -> Path:
    """The one disposable tree everything in this suite writes into."""
    global _WORKSPACE
    if _WORKSPACE is None:
        _WORKSPACE = Path(tempfile.mkdtemp(prefix="iptc-canonical-package-"))
    return _WORKSPACE


def tearDownModule():
    if _WORKSPACE is not None:
        shutil.rmtree(_WORKSPACE, ignore_errors=True)


def stage_packaging_inputs(name: str = "source", mtime: int = None,
                           extra: tuple = ()) -> Path:
    """Copy the declared build inputs into the staging tree, preserving layout.

    ``mtime``, when given, is stamped on every staged file and directory. The
    reproducibility check below builds from two copies stamped differently,
    because two copies made with ``copy2`` carry the repository's mtimes and would
    agree by accident: a release built on a fresh CI checkout sees whatever time
    that checkout happened, so "the same bytes twice" has to survive that.

    ``extra`` stages repository paths that are *not* packaging inputs. The release
    workflow builds from a checkout root, where they are all present, so a copy
    holding them is how this suite asks the question the staged subset cannot:
    does the build ignore them?
    """
    source = workspace() / name
    if source.exists():
        return source
    source.mkdir(parents=True)
    for relative in tuple(PACKAGING_INPUTS) + tuple(extra):
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
    if mtime is not None:
        for path in sorted(source.rglob("*"), reverse=True):
            os.utime(path, (mtime, mtime))
        os.utime(source, (mtime, mtime))
    return source


def staged_mtimes(source: Path) -> set:
    """Every distinct file mtime under a staging copy."""
    return {path.stat().st_mtime_ns
            for path in source.rglob("*") if path.is_file()}


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


def run_build(source: Path, outdir: Path) -> Built:
    """One ``python -m build`` run over ``source``, writing into ``outdir``.

    The single place this suite spawns a build, so the release-candidate build and
    the reproducibility check below cannot drift into asking two different
    questions.

    Driven through ``packaging/machina_sports_canonical/release.py`` with the
    release epoch in the environment — the same command line and the same epoch
    ``.github/workflows/publish-machina-sports-canonical.yml`` runs, so this suite
    proves the artefacts the release job actually produces rather than a
    lookalike built with different flags.
    """
    environment = dict(os.environ, SOURCE_DATE_EPOCH=RELEASE_SOURCE_DATE_EPOCH)
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / RELEASE_HELPER),
         str(source), str(outdir)],
        capture_output=True, text=True, timeout=900, env=environment)
    return Built(source, outdir, result)


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
        _BUILD = run_build(stage_packaging_inputs(), workspace() / "dist")
    return _BUILD


def reproduction(label: str, mtime: int, extra: tuple = ()) -> dict:
    """The wheel and sdist digests of an independent build, cached per label."""
    if label not in _REPRODUCTIONS:
        source = stage_packaging_inputs(label, mtime=mtime, extra=extra)
        # Read before building: the build leaves an `egg-info` directory in the
        # tree it builds, and those files carry the time the build ran.
        stamped = staged_mtimes(source)
        result = run_build(source, workspace() / "dist-{0}".format(label))
        if result.returncode != 0:
            raise AssertionError(result.diagnosis())
        _REPRODUCTIONS[label] = {
            "mtimes": stamped,
            "wheel": sha256_bytes(result.wheel.read_bytes()),
            "sdist": sha256_bytes(result.sdist.read_bytes()),
        }
    return _REPRODUCTIONS[label]


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


def release_helper():
    """``packaging/machina_sports_canonical/release.py``, loaded from its path.

    By path for the same reason ``build_filter`` is: this directory is
    deliberately not an importable package, because a regular ``packaging``
    package at a repository root would shadow the ``packaging`` distribution.
    """
    path = REPO_ROOT / RELEASE_HELPER
    spec = importlib.util.spec_from_file_location(
        "iptc_canonical_release_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_sdist(path: Path, mtime: int) -> list:
    """A small ``tar.gz`` shaped like an sdist, stamped with ``mtime``.

    Written here rather than reusing the real artefact so the normalizer can be
    exercised against members a correct build would never produce.
    """
    entries = [("pkg", None), ("pkg/a.py", b"a = 1\n"), ("pkg/b.json", b"{}\n")]
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in entries:
            member = tarfile.TarInfo(name)
            member.mtime = mtime
            member.uid = 501
            member.gid = 20
            member.uname = "builder"
            member.gname = "staff"
            if payload is None:
                member.type = tarfile.DIRTYPE
                member.mode = 0o700
                archive.addfile(member)
            else:
                member.size = len(payload)
                member.mode = 0o600
                archive.addfile(member, io.BytesIO(payload))
    return entries


def tar_members(path: Path) -> list:
    with tarfile.open(path) as archive:
        return archive.getmembers()


def tar_payloads(path: Path) -> dict:
    with tarfile.open(path) as archive:
        return {member.name: archive.extractfile(member).read()
                for member in archive.getmembers() if member.isfile()}


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


def publish_workflow_text() -> str:
    return PUBLISH_WORKFLOW_PATH.read_text(encoding="utf-8")


def publish_workflow_header() -> str:
    """Everything above ``jobs:`` — the triggers and the default permissions.

    Read separately from the jobs because the two claims are different: a
    workflow-wide ``contents: read`` is what makes the publish job's ``id-token:
    write`` an addition to a read-only default rather than a narrowing of a
    permissive one.

    Comments are dropped, for the reason ``workflow_jobs`` drops them: prose
    explaining a permission must not be able to satisfy — or to break — a claim
    about the permission.
    """
    header = publish_workflow_text().split("\njobs:", 1)[0]
    return "\n".join(line for line in header.splitlines()
                     if not line.strip().startswith("#"))


def workflow_uses(text: str) -> list:
    """Every ``uses:`` a job in ``text`` executes.

    Read through ``workflow_jobs``, so a full-line comment quoting an action
    cannot stand in for a step that runs one — and an inline comment on the step's
    own line survives, because that is where the pinned ref is named.
    """
    found = []
    for block in workflow_jobs(text).values():
        for raw in block.splitlines():
            stripped = raw.strip()
            if stripped.startswith("- "):
                stripped = stripped[2:]
            if stripped.startswith("uses:"):
                found.append(stripped)
    return found


def release_docs_text() -> str:
    return RELEASE_DOCS_PATH.read_text(encoding="utf-8")


def reviewed_digest_rows() -> list:
    """The checked-in checksum file, parsed the way ``sha256sum`` writes it.

    Read rather than reconstructed: the constants above say what the rows should
    be, and this says what the file on disk actually holds. A test that compared
    the constants with themselves would be green with no file checked in at all.
    """
    rows = []
    for line in RELEASE_CHECKSUM_PATH.read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        rows.append((name, digest) if separator else (line, ""))
    return rows


def line_index(block: str, needle: str) -> int:
    """Where ``needle`` first appears in ``block``, by line, or ``-1``.

    Order matters for exactly one thing here: a gate that runs after the upload
    is not a gate.
    """
    for number, raw in enumerate(block.splitlines()):
        if needle in raw:
            return number
    return -1


# ---------------------------------------------------------------------------
# The pinned build closure: what the file says, and what is actually running
# ---------------------------------------------------------------------------
#
# Two independent readings, because they answer different questions. The file
# reader says whether `requirements-iptc-build.txt` still is the closure this
# repository decided on. The metadata walk says whether that decision is still
# true — a `build` release that resolves one more distribution would leave a
# nine-pin file passing the first check while the tenth arrived from the index.


def marker_environment(environment: dict = None) -> dict:
    """This interpreter's marker environment, with extras switched off.

    ``extra`` is set to the empty string rather than left undefined so an
    ``extra == "test"`` requirement evaluates false instead of raising.
    ``setuptools`` declares its entire dependency list behind extras, and
    installing its test extra is not what building a wheel needs.

    ``environment`` overrides individual keys, which is how the marker selection
    can be stated for the floor and for Windows from whichever interpreter runs.
    """
    resolved = {"extra": ""}
    if environment:
        resolved.update(environment)
    return resolved


def expected_closure() -> dict:
    """``BUILD_REQUIREMENT_CLOSURE`` as canonical name -> (version, marker).

    Markers go through ``Marker`` in both directions, so a comparison answers
    "does this mean the same thing" rather than "was it typed the same way".
    """
    return {canonicalize_name(name):
            (version, str(Marker(marker)) if marker else "")
            for name, version, marker in BUILD_REQUIREMENT_CLOSURE}


def read_pinned_closure(text: str) -> tuple:
    """``text`` read as canonical name -> (version, marker), plus its problems.

    One reader for the checked-in file and for the drifted files the guard test
    feeds it, so that guard proves the reader CI actually runs.
    """
    found = {}
    problems = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            requirement = Requirement(line)
        except InvalidRequirement:
            problems.append("not a requirement: {0}".format(line))
            continue
        specifiers = list(requirement.specifier)
        if (requirement.url or requirement.extras or len(specifiers) != 1
                or specifiers[0].operator != "=="):
            problems.append("not an exact pin: {0}".format(line))
            continue
        name = canonicalize_name(requirement.name)
        if name in found:
            problems.append("pinned twice: {0}".format(name))
            continue
        found[name] = (specifiers[0].version,
                       str(requirement.marker) if requirement.marker else "")
    return found, problems


def closure_problems(text: str) -> list:
    """Every way ``text`` differs from ``BUILD_REQUIREMENT_CLOSURE``, sorted."""
    found, problems = read_pinned_closure(text)
    expected = expected_closure()
    for name in sorted(set(expected) - set(found)):
        problems.append("missing from the file: {0}".format(name))
    for name in sorted(set(found) - set(expected)):
        problems.append("pinned but not part of the closure: {0}".format(name))
    for name in sorted(set(found) & set(expected)):
        if found[name][0] != expected[name][0]:
            problems.append("{0} is pinned at {1}, the closure says {2}".format(
                name, found[name][0], expected[name][0]))
        if found[name][1] != expected[name][1]:
            problems.append(
                "{0} carries marker {1!r}, the closure says {2!r}".format(
                    name, found[name][1], expected[name][1]))
    return sorted(problems)


def active_pins(text: str, environment: dict = None) -> dict:
    """The pins in ``text`` whose marker holds, canonical name -> version.

    Read off the file rather than off ``BUILD_REQUIREMENT_CLOSURE``, so the walk
    below goes red when the file is the thing that is short a pin.
    """
    active = {}
    for name, (version, marker) in read_pinned_closure(text)[0].items():
        if marker and not Marker(marker).evaluate(marker_environment(environment)):
            continue
        active[name] = version
    return active


def installed_build_distributions() -> dict:
    """Canonical name -> (version, requirement strings) for what is installed.

    Collected in one pass over ``importlib.metadata.distributions()`` rather than
    asked for by name: on the declared floor, looking up ``pyproject-hooks`` means
    normalizing a name spelled with an underscore on disk, and this way the suite
    does not depend on which release learned to do that. Nothing is imported —
    reading metadata must not change the interpreter it is reading.
    """
    found = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        if not name:
            continue
        found.setdefault(
            canonicalize_name(name),
            (distribution.version, tuple(distribution.requires or ())))
    return found


def walk_active_closure(declared: dict) -> tuple:
    """Walk the installed build tooling from the roots out.

    ``declared`` is the marker-selected pin set, canonical name -> version.
    Returns what the walk reached and every disagreement between the installed
    metadata and that set:

    - a dependency the metadata declares as active here and the pins do not,
      which is how a future ``build`` release that grows a helper turns red;
    - a version installed that is not the pinned one, including a root;
    - a version installed that its own dependant refuses;
    - a pin nothing in the closure needs on this interpreter.
    """
    installed = installed_build_distributions()
    bootstrap = {canonicalize_name(name) for name in BUILD_CLOSURE_BOOTSTRAP}
    problems = []
    reached = {}
    attempted = set()
    queue = [canonicalize_name(name) for name in BUILD_REQUIREMENT_NAMES]
    while queue:
        name = queue.pop(0)
        attempted.add(name)
        if name in reached:
            continue
        if name not in installed:
            problems.append("{0} is pinned but not installed".format(name))
            continue
        version, requires = installed[name]
        reached[name] = version
        for raw in requires:
            requirement = Requirement(raw)
            if (requirement.marker is not None
                    and not requirement.marker.evaluate(marker_environment())):
                continue
            child = canonicalize_name(requirement.name)
            if child in bootstrap:
                continue
            if child not in declared:
                problems.append("{0} requires {1} here, which the pinned file "
                                "does not declare".format(name, child))
                continue
            child_version = installed.get(child, (None, ()))[0]
            if (child_version is not None and requirement.specifier
                    and not requirement.specifier.contains(child_version,
                                                           prereleases=True)):
                problems.append("{0} requires {1}{2}, and {1} {3} is "
                                "installed".format(name, child,
                                                   requirement.specifier,
                                                   child_version))
            queue.append(child)
    for name in sorted(reached):
        if reached[name] != declared.get(name):
            problems.append("{0} {1} is installed, the file pins {2}".format(
                name, reached[name], declared.get(name)))
    for name in sorted(set(declared) - attempted):
        problems.append("the file pins {0}, which nothing in the build closure "
                        "needs here".format(name))
    return reached, sorted(problems)


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

    def test_the_proof_job_compares_its_release_build_with_the_reviewed_digests(self):
        """What made the matrix worth having, and what it was missing.

        Each leg ran the suite and proved its own build reproducible on its own
        interpreter. Nothing compared the two, so 3.9 and 3.11 could each have
        been stably building *different* bytes with both legs green. The leg now
        builds a release through the same helper and the same epoch the release
        job uses and diffs the result against the reviewed digests, so a divergent
        interpreter fails its own job against the file the other one passes.

        Into ``$RUNNER_TEMP`` rather than into the checkout: this job's last step
        is a clean-tree gate, and an artefact left in a tracked path would turn a
        successful proof into a red gate one step later.
        """
        commands = run_commands(self.proof)
        builds = [command for command in commands
                  if RELEASE_HELPER in command or "-m build" in command]
        self.assertEqual(len(builds), 1,
                         "expected exactly one release build in the proof job, "
                         "through the release helper: {0}".format(builds))
        self.assertIn("$RUNNER_TEMP", builds[0],
                      "the release build must write outside the checkout")
        self.assertIn('SOURCE_DATE_EPOCH: "{0}"'.format(RELEASE_SOURCE_DATE_EPOCH),
                      self.proof,
                      "a build without the release epoch is not the release")
        digests = [command for command in commands if "sha256sum" in command]
        self.assertEqual(len(digests), 1, digests)
        self.assertNotIn("dist/", digests[0],
                         "the generated rows must carry basenames, or they can "
                         "never diff equal against the checked-in file")
        comparisons = [command for command in commands
                       if command.startswith("diff -u")]
        self.assertEqual(len(comparisons), 1, comparisons)
        self.assertIn(RELEASE_CHECKSUM_FILE, comparisons[0])

    def test_the_proof_job_keeps_its_clean_tree_gate_after_the_release_build(self):
        """The gate is what catches a build byproduct the step above did not clean
        up, so it has to run after it rather than before."""
        commands = run_commands(self.proof)
        self.assertTrue(any("git status --porcelain" in command
                            for command in commands), commands)
        comparison = line_index(self.proof, "diff -u")
        self.assertNotEqual(comparison, -1,
                            "the proof job compares nothing with the reviewed "
                            "digests")
        self.assertLess(comparison,
                        line_index(self.proof, "git status --porcelain"))

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
        """Stated here because this is where the workflow's install step is read:
        the file every job installs has to be the closure. What "the closure"
        means is the two classes below."""
        path = REPO_ROOT / BUILD_REQUIREMENTS
        self.assertTrue(path.is_file(), "missing: {0}".format(BUILD_REQUIREMENTS))
        self.assertEqual(closure_problems(path.read_text(encoding="utf-8")), [])

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


# ---------------------------------------------------------------------------
# The pinned file is the whole closure, and the whole closure is what runs
# ---------------------------------------------------------------------------


class TestThePinnedBuildClosureIsDeclaredInFull(unittest.TestCase):
    """``requirements-iptc-build.txt`` has to pin the execution closure, not the
    three names on the tin.

    ``build`` does not run on ``build`` alone. It imports ``packaging`` and
    ``pyproject_hooks`` on every interpreter, and ``tomli``,
    ``importlib-metadata`` and ``zipp`` on the declared floor. While those were
    left to the resolver, the validate leg and the two proof legs could each
    build with a different frontend closure and the diff would show one pinned
    file, so "identical build tooling across the legs" was not something this
    repository could claim. The reasoning that it was safe rested on a further
    error: the byte gates cover the wheel's *payload*, not its ``dist-info`` or
    the sdist, so a helper that changed only generated metadata changed the
    release without turning anything red.
    """

    def setUp(self):
        self.text = (REPO_ROOT / BUILD_REQUIREMENTS).read_text(encoding="utf-8")

    def test_the_file_pins_exactly_the_checked_in_closure(self):
        """Closed in both directions: a name missing, a name too many, a version
        that drifted or a marker that widened is one report each."""
        self.assertEqual(closure_problems(self.text), [])

    def test_the_roots_are_pinned_unconditionally(self):
        """A marker on a root would make the frontend or the backend conditional,
        and every leg builds."""
        found = read_pinned_closure(self.text)[0]
        for root in BUILD_REQUIREMENT_NAMES:
            name = canonicalize_name(root)
            with self.subTest(root=root):
                self.assertIn(name, found)
                self.assertEqual(found[name][1], "")

    def test_the_conditional_helpers_are_selected_by_interpreter_and_platform(self):
        """The markers are load-bearing, not decorative: they keep the floor's
        helpers off 3.11 and Windows' ``colorama`` off Linux, and they are what
        makes one checked-in file installable on both declared interpreters.

        Evaluated against stated environments rather than against the running
        one, so the claim holds on whichever interpreter runs the suite.
        """
        floor = active_pins(self.text, {"python_version": "3.9",
                                        "python_full_version": "3.9.25",
                                        "os_name": "posix"})
        image = active_pins(self.text, {"python_version": "3.11",
                                        "python_full_version": "3.11.14",
                                        "os_name": "posix"})
        windows = active_pins(self.text, {"python_version": "3.11",
                                          "python_full_version": "3.11.14",
                                          "os_name": "nt"})
        self.assertEqual(sorted(floor),
                         ["build", "importlib-metadata", "packaging",
                          "pyproject-hooks", "setuptools", "tomli", "wheel",
                          "zipp"])
        self.assertEqual(sorted(image),
                         ["build", "packaging", "pyproject-hooks", "setuptools",
                          "wheel"])
        self.assertEqual(sorted(set(windows) - set(image)), ["colorama"])
        self.assertEqual(sorted(set(image) - set(windows)), [])

    def test_the_closure_reader_rejects_every_way_the_file_could_drift(self):
        """Guard the guard. The assertion above is worth exactly what this one
        proves: a reader that shrugged at a range or absorbed an extra name would
        report a clean closure for a file that is not one. Each case is fed to
        the same reader the checked-in file goes through.
        """
        complete = "".join(
            "{0}=={1}{2}\n".format(name, version,
                                   "; {0}".format(marker) if marker else "")
            for name, version, marker in BUILD_REQUIREMENT_CLOSURE)
        self.assertEqual(closure_problems(complete), [],
                         "the closure constant does not read back as itself")
        pinned_tomli = 'tomli==2.2.1; python_version < "3.11"'
        drifted = {
            "missing": complete.replace("pyproject-hooks==1.2.0\n", ""),
            "extra": complete + "rdflib==7.1.4\n",
            "ranged": complete.replace("packaging==26.3", "packaging>=26.3"),
            "unpinned": complete.replace("wheel==0.47.0", "wheel"),
            "duplicate": complete + "wheel==0.47.0\n",
            "version drift": complete.replace("build==1.4.4", "build==1.5.0"),
            "marker dropped": complete.replace(pinned_tomli, "tomli==2.2.1"),
            "marker widened": complete.replace(
                pinned_tomli, 'tomli==2.2.1; python_version < "3.12"'),
        }
        for label, text in sorted(drifted.items()):
            with self.subTest(drift=label):
                self.assertNotEqual(text, complete, "the drift case is a no-op")
                self.assertNotEqual(closure_problems(text), [])


class TestThePinnedClosureIsTheOneThisInterpreterBuildsWith(unittest.TestCase):
    """Read off the installed metadata, not off the file.

    The class above proves the file still says what this repository decided. It
    cannot prove the decision is still true: ``build`` could publish a release
    that resolves one more distribution, and a file pinning nine names would go
    on passing while the tenth arrived from the index at whatever version the
    resolver liked. So the frontend's own metadata is walked here, from the three
    roots outwards, and every dependency active on this interpreter has to be a
    pin in the file, installed at exactly that version.
    """

    def setUp(self):
        self.text = (REPO_ROOT / BUILD_REQUIREMENTS).read_text(encoding="utf-8")
        self.declared = active_pins(self.text)

    def test_every_active_build_dependency_is_pinned_and_installed_at_its_pin(self):
        reached, problems = walk_active_closure(self.declared)
        self.assertEqual(problems, [])
        self.assertEqual(sorted(reached), sorted(self.declared))

    def test_the_walk_leaves_the_roots_and_reaches_the_frontend_helpers(self):
        """A walk that stopped at the three roots would report a complete closure
        for the three-pin file this pair of classes exists to reject."""
        reached = walk_active_closure(self.declared)[0]
        for helper in ("packaging", "pyproject-hooks"):
            with self.subTest(helper=helper):
                self.assertIn(helper, reached)
        self.assertTrue(set(reached) > {canonicalize_name(root)
                                        for root in BUILD_REQUIREMENT_NAMES})

    def test_the_walk_reports_a_dependency_the_pins_do_not_declare(self):
        """Guard the guard, on the exact regression: this is what the walk says
        about a file that pins the roots and leaves their closure open."""
        roots_only = {canonicalize_name(root): self.declared[canonicalize_name(root)]
                      for root in BUILD_REQUIREMENT_NAMES}
        problems = walk_active_closure(roots_only)[1]
        self.assertTrue(any("packaging" in problem for problem in problems),
                        problems)
        self.assertTrue(any("pyproject-hooks" in problem for problem in problems),
                        problems)

    def test_the_walk_reports_a_pin_at_a_version_that_is_not_installed(self):
        problems = walk_active_closure(dict(self.declared, packaging="0.0.0"))[1]
        self.assertTrue(any("packaging" in problem for problem in problems),
                        problems)

    def test_the_walk_reports_a_pin_nothing_in_the_closure_needs(self):
        """The other direction. A pin kept after the frontend stopped needing it
        is a version every leg installs for no stated reason, and the file would
        be the only place saying it is build tooling at all."""
        problems = walk_active_closure(dict(self.declared, rdflib="7.1.4"))[1]
        self.assertTrue(any("rdflib" in problem for problem in problems),
                        problems)

    def test_only_the_venv_bootstrap_is_left_out_of_the_walk(self):
        """Named as a constant so the exemption cannot grow quietly. ``pip`` is in
        every venv whether a requirements file says so or not; ``setuptools`` and
        ``wheel`` arrive with some venvs too, and they are pinned anyway."""
        self.assertEqual(BUILD_CLOSURE_BOOTSTRAP, ("pip",))

    def test_the_packaging_library_doing_the_reading_is_the_pinned_one(self):
        """Every claim in both classes is evaluated by ``packaging``, and this
        repository has a root ``packaging/`` directory that ``sys.path`` reaches.
        It has no ``__init__.py``, so an installed distribution wins — asserted
        rather than assumed, because on the day it gains one this suite would be
        taking marker semantics from a build helper."""
        location = Path(packaging.__file__).resolve()
        self.assertFalse(location == REPO_ROOT or REPO_ROOT in location.parents,
                         location)
        self.assertEqual(packaging.__version__, self.declared["packaging"])


# ---------------------------------------------------------------------------
# The release build helper: what it is allowed to change, and what it is not
# ---------------------------------------------------------------------------


class TestTheReleaseHelperNormalizesMetadataAndNothingElse(unittest.TestCase):
    """A step that rewrites a release artefact is a supply-chain surface.

    So it is held to the narrowest claim that makes the sdist reproducible: the
    same members, in the same order, with the same payload bytes, and only the
    facts that describe the machine — mtime, uid, gid, owner names, mode —
    replaced. Anything else it did would be a release altering its own contents
    after the backend produced them.
    """

    def setUp(self):
        self.helper = release_helper()
        self.epoch = int(RELEASE_SOURCE_DATE_EPOCH)
        self.staged = Path(tempfile.mkdtemp(prefix="iptc-release-helper-"))
        self.addCleanup(shutil.rmtree, self.staged, ignore_errors=True)

    def test_the_helper_requires_the_release_epoch(self):
        """A release built without it is silently irreproducible, so an absent or
        malformed epoch is an error rather than a default."""
        for environment in ({}, {"SOURCE_DATE_EPOCH": ""},
                            {"SOURCE_DATE_EPOCH": "now"},
                            {"SOURCE_DATE_EPOCH": "-1"}):
            with self.subTest(environment=environment):
                with self.assertRaises(ValueError):
                    self.helper.source_date_epoch(environment)
        self.assertEqual(
            self.helper.source_date_epoch(
                {"SOURCE_DATE_EPOCH": RELEASE_SOURCE_DATE_EPOCH}),
            self.epoch)

    def test_the_helper_refuses_a_member_it_cannot_account_for(self):
        """An sdist for this distribution holds files and directories. A symlink
        or a device is refused rather than normalized: guessing is how a release
        grows a member nobody reviewed."""
        link = tarfile.TarInfo("pkg/elsewhere")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        with self.assertRaises(ValueError):
            self.helper.normalized_member(link, self.epoch)

    def test_normalization_keeps_every_member_its_order_and_its_payload(self):
        archive = self.staged / "synthetic-0.1.0.tar.gz"
        entries = synthetic_sdist(archive, mtime=1000000000)
        before = tar_payloads(archive)
        self.helper.normalize_sdist(archive, self.epoch)
        self.assertEqual([member.name for member in tar_members(archive)],
                         [name for name, _ in entries])
        self.assertEqual(tar_payloads(archive), before)

    def test_normalization_replaces_exactly_the_builder_facts(self):
        archive = self.staged / "synthetic-0.1.0.tar.gz"
        synthetic_sdist(archive, mtime=1000000000)
        self.helper.normalize_sdist(archive, self.epoch)
        for member in tar_members(archive):
            with self.subTest(member=member.name):
                self.assertEqual(member.mtime, self.epoch)
                self.assertEqual((member.uid, member.gid), (0, 0))
                self.assertEqual((member.uname, member.gname), ("", ""))
                self.assertEqual(
                    member.mode,
                    self.helper.NORMALIZED_DIRECTORY_MODE if member.isdir()
                    else self.helper.NORMALIZED_FILE_MODE)

    def test_two_normalizations_of_one_input_are_the_same_bytes(self):
        """Including the gzip container, which stores an mtime and a filename of
        its own — the reason the archive is written explicitly rather than through
        ``tarfile``'s ``w:gz``."""
        digests = []
        for label, stamp in (("a", 1000000000), ("b", 1700000000)):
            archive = self.staged / "{0}/synthetic-0.1.0.tar.gz".format(label)
            archive.parent.mkdir(parents=True)
            synthetic_sdist(archive, mtime=stamp)
            self.helper.normalize_sdist(archive, self.epoch)
            digests.append(sha256_bytes(archive.read_bytes()))
        self.assertEqual(digests[0], digests[1])

    def test_the_released_sdist_still_carries_the_canonical_source_bytes(self):
        """The end-to-end form of "no payload was touched", on the real artefact:
        every canonical module and resource in the released sdist is byte-equal to
        its authoritative source."""
        payloads = tar_payloads(built().sdist)
        shipped = sorted((source_modules() - {GENERATOR_MODULE})
                         | set(JSON_RESOURCES))
        for relative in shipped:
            member = "{0}/tools/iptc/canonical/{1}".format(ARTIFACT_STEM, relative)
            with self.subTest(member=member):
                self.assertIn(member, payloads)
                self.assertEqual(payloads[member],
                                 (CANONICAL_ROOT / relative).read_bytes())
        self.assertEqual(len(shipped),
                         len(source_modules()) + len(JSON_RESOURCES) - 1)

    def test_the_sdist_carries_the_helper_and_the_wheel_does_not(self):
        """It is build support, not runtime. The sdist keeps it so the release can
        be rebuilt from the artefact itself; the import namespace never sees it,
        which the wheel's closed member set already decides and this states."""
        self.assertIn("{0}/{1}".format(ARTIFACT_STEM, RELEASE_HELPER),
                      tar_payloads(built().sdist))
        helper = Path(RELEASE_HELPER).name
        for member in wheel_record(built().wheel):
            with self.subTest(member=member):
                self.assertNotIn(helper, member)


# ---------------------------------------------------------------------------
# The same bytes twice: a release whose digests can be compared at all
# ---------------------------------------------------------------------------


class TestTheReleaseArtefactsAreReproducible(unittest.TestCase):
    """A release checklist that says "verify the published hash equals the hash
    you reviewed" is only meaningful if two builds of one commit agree.

    They did not. ``zip`` and ``tar`` store an mtime per member, so the wheel and
    the sdist carried whatever time the build happened and every build produced a
    different digest. The approved checklist then had a step nobody could execute:
    a mismatch meant nothing, so a substituted artefact would have looked exactly
    like a rebuild.
    """

    def test_two_clean_builds_produce_byte_identical_artefacts(self):
        first = reproduction("first", REPRODUCTION_MTIMES[0])
        second = reproduction("second", REPRODUCTION_MTIMES[1])
        for artefact in ("wheel", "sdist"):
            with self.subTest(artefact=artefact):
                self.assertEqual(
                    first[artefact], second[artefact],
                    "two builds of one commit produced different {0} bytes, so "
                    "no published digest can be compared with a reviewed "
                    "one".format(artefact))

    def test_a_release_build_ignores_repository_files_that_are_not_inputs(self):
        """The release job builds from a checkout root, the proof suite from a
        staged subset — so they were not building the same artefact.
        ``setuptools``' sdist defaults had swept the repository's own README and
        every IPTC test suite into the published sdist, and only the root build saw
        it. This copy holds those paths; its bytes must be the reviewed bytes."""
        clean = reproduction("first", REPRODUCTION_MTIMES[0])
        noisy = reproduction("noisy", REPRODUCTION_MTIMES[0],
                             extra=REPOSITORY_NOISE)
        for artefact in ("wheel", "sdist"):
            with self.subTest(artefact=artefact):
                self.assertEqual(
                    clean[artefact], noisy[artefact],
                    "a repository file that is not a packaging input changed the "
                    "released {0}".format(artefact))

    def test_the_released_sdist_holds_exactly_the_declared_members(self):
        """Closed set, like the wheel's. Named members rather than a count: what
        leaked in was twenty test files, and a count would have accepted them."""
        # Files only. Directory members carry no bytes of their own, and
        # ``getnames`` does not mark them.
        members = sorted(name.split("/", 1)[1]
                         for name in tar_payloads(built().sdist))
        canonical = ["tools/iptc/canonical/{0}".format(relative)
                     for relative in sorted((source_modules()
                                             - {GENERATOR_MODULE})
                                            | set(JSON_RESOURCES))]
        self.assertEqual(members,
                         sorted(list(EXPECTED_SDIST_MEMBERS) + canonical))

    def test_the_two_builds_really_saw_different_input_timestamps(self):
        """Guard the guard. ``copy2`` preserves mtimes, so two staging copies of
        this repository agree by accident — and a reproducibility check whose two
        inputs are indistinguishable proves nothing about a release built on a
        fresh checkout, which is the only kind CI makes."""
        first = reproduction("first", REPRODUCTION_MTIMES[0])["mtimes"]
        second = reproduction("second", REPRODUCTION_MTIMES[1])["mtimes"]
        self.assertEqual(len(first), 1, first)
        self.assertEqual(len(second), 1, second)
        self.assertNotEqual(first, second)

    def test_the_release_epoch_is_the_recorded_source_commit_it_claims(self):
        """The epoch is a magic number unless it can be re-derived. It is the
        committer timestamp of the commit ``package-receipt.json`` already
        records, so a reviewer can check the workflow's constant against the tree
        the distribution ships."""
        receipt = json.loads(
            (CANONICAL_ROOT / "package-receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["source_commit"], CANONICAL_SOURCE_COMMIT)
        found = subprocess.run(
            ["git", "log", "-1", "--format=%ct", CANONICAL_SOURCE_COMMIT],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120)
        if found.returncode != 0:
            # A shallow checkout does not have the object. Explicit, printed, and
            # never a substitute for the assertion above.
            raise unittest.SkipTest(
                "{0} is not in this checkout: {1}".format(
                    CANONICAL_SOURCE_COMMIT, found.stderr.strip()))
        self.assertEqual(found.stdout.strip(), RELEASE_SOURCE_DATE_EPOCH)


class TestTheReviewedReleaseDigestsAreCheckedIn(unittest.TestCase):
    """Reproducibility was proved, and never proved *against anything*.

    The class above shows that two builds in one process agree, and the matrix
    repeats that on 3.9 and on 3.11 — but each leg only ever compared its own
    build with its own build. Two interpreters that each reproduced a *different*
    artefact would both be green, and `docs/iptc/RELEASING.md` said "the digests
    below" while listing none, so the release checklist's central step — compare
    the digest PyPI serves with the digest you reviewed — named nothing to compare
    with.

    So the reviewed digests are checked in, and this class is what makes that file
    binding: the artefacts this interpreter builds must hash to exactly those rows.
    Running this suite on both declared interpreters therefore compares them with
    each other, through a third thing a human approved.
    """

    def test_the_checksum_file_is_checked_in_as_sha256sum_writes_it(self):
        """Byte-exact, because every job compares it with ``diff -u`` against
        generated output. A stray blank line, a single-space separator or a
        trailing space is a red diff on a release whose bytes are correct."""
        self.assertTrue(RELEASE_CHECKSUM_PATH.is_file(),
                        "no reviewed digests are checked in: {0}".format(
                            RELEASE_CHECKSUM_FILE))
        self.assertEqual(
            RELEASE_CHECKSUM_PATH.read_text(encoding="utf-8"),
            "".join("{0}  {1}\n".format(digest, name)
                    for name, digest in REVIEWED_RELEASE_DIGESTS))

    def test_the_rows_are_the_two_artefacts_of_this_version_in_a_stable_order(self):
        """The wheel then the sdist — the order ``sha256sum *.whl *.tar.gz``
        produces on every leg. Order is part of the file because the comparison is
        a diff, not a set membership test."""
        self.assertEqual([name for name, _ in reviewed_digest_rows()],
                         ["{0}-py3-none-any.whl".format(ARTIFACT_STEM),
                          "{0}.tar.gz".format(ARTIFACT_STEM)])

    def test_every_row_names_a_basename_so_one_file_is_every_jobs_authority(self):
        """The proof job builds into ``$RUNNER_TEMP``, the release job into
        ``dist``, and the publish job checks from inside a downloaded ``dist``. A
        path prefix would make those three different files."""
        for name, digest in reviewed_digest_rows():
            with self.subTest(name=name):
                self.assertNotIn("/", name)
                self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_the_release_this_interpreter_builds_is_the_reviewed_release(self):
        """The gate itself, and — because the proof job runs this suite on 3.9 and
        on 3.11 — the cross-interpreter comparison. Either interpreter drifting
        fails its own leg against the rows the other one passes against."""
        recorded = dict(reviewed_digest_rows())
        for artefact in (built().wheel, built().sdist):
            with self.subTest(artefact=artefact.name):
                self.assertIn(artefact.name, recorded,
                              "the build produced an artefact the reviewed "
                              "digests do not name")
                self.assertEqual(
                    sha256_bytes(artefact.read_bytes()), recorded[artefact.name],
                    "this interpreter built bytes that are not the reviewed "
                    "release; see {0}".format(RELEASE_CHECKSUM_FILE))

    def test_the_checksum_file_is_outside_the_artefacts_it_describes(self):
        """A checksum shipped inside the archive it hashes cannot hash it, and a
        row for the file itself is a digest nothing can ever verify. Neither is
        possible while the file lives under ``docs/`` and nothing packages
        ``docs/`` — which is what this asserts rather than assumes."""
        basename = Path(RELEASE_CHECKSUM_FILE).name
        for name, _ in reviewed_digest_rows():
            with self.subTest(name=name):
                self.assertNotEqual(name, basename)
        for member in wheel_record(built().wheel):
            with self.subTest(member=member):
                self.assertNotIn(basename, member)
        for member in tar_members(built().sdist):
            with self.subTest(member=member.name):
                self.assertNotIn(basename, member.name)


# ---------------------------------------------------------------------------
# The release automation: OIDC only, approved by a human, and blocked on license
# ---------------------------------------------------------------------------


class TestThePublishWorkflowUsesTrustedPublishing(unittest.TestCase):
    """What may upload this distribution, and what must stop it.

    Three properties, none of which a document can hold on its own:

    - **No credential lives here.** Publishing is authorized by the job's own
      short-lived OIDC token, exchanged by ``pypa/gh-action-pypi-publish`` for an
      upload token PyPI issues to this repository, this workflow and this
      environment. An API token in a repository secret is a standing credential
      that outlives the release it was added for.
    - **A human stands between building and uploading.** The artefacts are built
      once with no upload scope, and the job that has the upload scope downloads
      those exact bytes behind a reviewer-gated environment. It cannot rebuild:
      publishing a rebuild publishes bytes nobody approved.
    - **It refuses to publish today.** The distribution declares no license,
      because this repository has none to declare and packaging must not invent
      one. That refusal is an executable step in front of the upload, so the
      workflow can be committed while the release stays blocked.
    """

    # No skip when the workflow is absent, and no `is_file()` guard that turns
    # every assertion below into a no-op. A missing release workflow is a failure:
    # the reader raises here, once per test, and the suite reports the path.
    def setUp(self):
        self.text = publish_workflow_text()
        self.header = publish_workflow_header()
        self.jobs = workflow_jobs(self.text)
        self.build = self.jobs.get(RELEASE_BUILD_JOB, "")
        self.publish = self.jobs.get(RELEASE_PUBLISH_JOB, "")

    def license_gate_command(self) -> str:
        """The publish job's license preflight, as the workflow spells it."""
        found = [command for command in run_commands(self.publish)
                 if all(field in command for field in LICENSE_METADATA_FIELDS)]
        self.assertEqual(len(found), 1,
                         "expected exactly one license preflight command, "
                         "found {0}".format(found))
        return found[0]

    def test_publish_workflow_uses_trusted_publishing(self):
        """The claim the plan names: the workflow exists, releases are triggered
        by the tag convention, the upload is authorized by OIDC, and no API-token
        secret is referenced anywhere in it."""
        self.assertTrue(PUBLISH_WORKFLOW_PATH.is_file(), PUBLISH_WORKFLOW_PATH)
        self.assertIn('- "{0}"'.format(RELEASE_TAG_GLOB), self.header)
        self.assertIn("id-token: write", self.publish)
        self.assertIn("uses: {0}@".format(TRUSTED_PUBLISHER_ACTION), self.publish)
        for marker in CREDENTIAL_MARKERS:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.text,
                                 "trusted publishing needs no credential of its "
                                 "own; {0!r} is one".format(marker))

    def test_every_action_this_release_runs_is_pinned_to_a_commit(self):
        """The supply chain this workflow does not otherwise control.

        Everything else here works to make the published bytes the reviewed bytes:
        one build, digests recorded before approval, verified after, no rebuild.
        A mutable action ref undoes all of it from outside — the code that holds the
        OIDC identity, or that produces the artefact it uploads, would be whatever
        a third party's tag points at on the day the tag is pushed.
        """
        found = workflow_uses(self.text)
        self.assertEqual(len(found), 5, found)
        for line in found:
            with self.subTest(uses=line):
                self.assertRegex(
                    line, PINNED_USES,
                    "not pinned to a 40-hex commit SHA with the ref named "
                    "beside it")

    def test_the_only_trigger_is_the_distribution_scoped_release_tag(self):
        """A publish workflow that also runs on a branch push publishes on merge.
        The tag pattern is distribution-scoped so a template release cannot fire
        it, and the exact tag this version releases under matches it."""
        self.assertIn("tags:", self.header)
        for forbidden in ("pull_request:", "branches:", "schedule:"):
            with self.subTest(trigger=forbidden):
                self.assertNotIn(forbidden, self.header)
        self.assertTrue(
            fnmatch.fnmatch(RELEASE_TAG, RELEASE_TAG_GLOB),
            "{0} does not match {1}".format(RELEASE_TAG, RELEASE_TAG_GLOB))
        self.assertEqual(RELEASE_TAG, "machina-sports-canonical-v0.1.0")

    def test_the_workflow_default_is_read_only_and_only_publish_may_upload(self):
        """``id-token: write`` on the workflow would hand the upload identity to
        every job in it, including the one that runs a build backend."""
        self.assertIn("permissions:", self.header)
        self.assertIn("contents: read", self.header)
        self.assertNotIn("id-token", self.header)
        self.assertNotIn("id-token", self.build)
        for extra in ("contents: write", "packages: write", "write-all"):
            with self.subTest(scope=extra):
                self.assertNotIn(extra, self.text)

    def test_the_publish_job_is_bound_to_the_reviewer_gated_environment(self):
        """The environment is where the human approval is enforced. Without this
        binding the workflow uploads the moment a tag is pushed."""
        self.assertIn("environment: {0}".format(PYPI_ENVIRONMENT), self.publish)
        self.assertNotIn("environment:", self.build)
        self.assertIn("needs: {0}".format(RELEASE_BUILD_JOB), self.publish)

    def test_the_build_job_builds_once_with_the_pinned_tooling_and_the_epoch(self):
        """One build, through the same helper and with the same epoch this suite
        drives — otherwise the artefacts proved here and the artefacts released
        are two different things that happen to share a version number."""
        commands = run_commands(self.build)
        self.assertIn("python -m pip install -r {0}".format(BUILD_REQUIREMENTS),
                      commands)
        builds = [command for command in commands
                  if RELEASE_HELPER in command or "-m build" in command]
        self.assertEqual(builds,
                         ["python {0} . dist".format(RELEASE_HELPER)],
                         "expected exactly one build, through the release helper")
        self.assertIn('SOURCE_DATE_EPOCH: "{0}"'.format(RELEASE_SOURCE_DATE_EPOCH),
                      self.build)

    def test_no_install_step_in_the_publish_workflow_is_ranged_or_unpinned(self):
        for name, block in sorted(self.jobs.items()):
            for command in run_commands(block):
                if "pip install" not in command:
                    continue
                with self.subTest(job=name, command=command):
                    self.assertRegex(
                        command,
                        r"^python -m pip install -r [A-Za-z0-9._/-]+\.txt$",
                        "install neither pinned nor from a checked-in file")

    def test_the_build_job_publishes_the_digests_beside_the_artefacts(self):
        """The digests are the release's identity. Recorded by the job that built
        the bytes, uploaded with them, and left in the log where a reviewer reads
        them."""
        self.assertTrue(
            any(RELEASE_DIGEST_FILE in command and "sha256sum" in command
                for command in run_commands(self.build)),
            run_commands(self.build))
        self.assertIn("uses: actions/upload-artifact@", self.build)
        self.assertIn("name: {0}".format(RELEASE_ARTIFACT_NAME), self.build)
        self.assertIn("if-no-files-found: error", self.build)

    def test_the_build_job_refuses_a_release_that_is_not_the_reviewed_one(self):
        """Recording the digests put them in a log. It did not check them.

        The reviewer was asked to compare the log with digests they had seen
        somewhere, by eye, under release pressure — and if the build job produced
        different bytes, nothing in the run said so. The digests are now diffed
        against the checked-in reviewed file, in the job that built them and before
        the artefact is uploaded, so a release whose bytes are not the approved
        bytes never reaches the approval gate at all.
        """
        commands = run_commands(self.build)
        digests = [command for command in commands if "sha256sum" in command]
        self.assertEqual(len(digests), 1, digests)
        self.assertIn(RELEASE_DIGEST_FILE, digests[0])
        self.assertNotIn("dist/*", digests[0],
                         "the recorded rows must carry basenames, so one checked-"
                         "in file is the authority for every job that hashes them")
        comparisons = [command for command in commands
                       if command.startswith("diff -u")]
        self.assertEqual(len(comparisons), 1, comparisons)
        self.assertIn(RELEASE_CHECKSUM_FILE, comparisons[0])
        self.assertIn(RELEASE_DIGEST_FILE, comparisons[0])
        self.assertLess(line_index(self.build, comparisons[0]),
                        line_index(self.build, "upload-artifact"),
                        "a digest gate after the upload is not a gate")

    def test_the_publish_job_uploads_the_downloaded_bytes_and_nothing_else(self):
        self.assertIn("uses: actions/download-artifact@", self.publish)
        self.assertIn("name: {0}".format(RELEASE_ARTIFACT_NAME), self.publish)
        self.assertIn("uses: actions/upload-artifact@", self.build)

    def test_the_publish_job_verifies_the_digests_before_it_uploads(self):
        checks = [command for command in run_commands(self.publish)
                  if "sha256sum" in command and RELEASE_DIGEST_FILE in command]
        self.assertEqual(
            checks,
            ["cd dist && sha256sum --check --strict ../{0}".format(
                RELEASE_DIGEST_FILE)],
            "the publish job must verify the artefact it downloaded against the "
            "digests the build job recorded — from inside `dist`, because those "
            "rows carry basenames so one checked-in file is every job's authority")
        self.assertLess(line_index(self.publish, checks[0]),
                        line_index(self.publish, TRUSTED_PUBLISHER_ACTION))

    def test_the_publish_job_never_rebuilds_the_artefacts(self):
        """Rebuilding after approval publishes bytes nobody approved — and it is
        the failure reproducibility makes *look* harmless."""
        for command in run_commands(self.publish):
            for marker in REBUILD_MARKERS:
                with self.subTest(command=command, marker=marker):
                    self.assertNotIn(marker, command)

    def test_the_publish_job_refuses_a_wheel_with_no_approved_license_metadata(self):
        gate = self.license_gate_command()
        self.assertIn("exit 1", gate)
        self.assertLess(line_index(self.publish, gate),
                        line_index(self.publish, TRUSTED_PUBLISHER_ACTION),
                        "a license gate after the upload is not a gate")

    def test_the_license_gate_stops_the_wheel_this_repository_builds_today(self):
        """The point of the gate, executed rather than described: the wheel this
        commit produces declares no license, so the publish job stops before the
        upload action. This is the local proof that the release is blocked."""
        metadata = "\n" + wheel_metadata(built().wheel)
        for field in LICENSE_METADATA_FIELDS:
            with self.subTest(field=field):
                self.assertNotIn("\n{0}:".format(field), metadata,
                                 "license metadata appeared without an owner "
                                 "decision recorded in docs/iptc/RELEASING.md")
        result = self.run_gate(built().wheel)
        self.assertNotEqual(result.returncode, 0,
                            "the gate let today's unlicensed wheel through:\n"
                            "{0}{1}".format(result.stdout, result.stderr))
        self.assertIn("BLOCKED", result.stdout + result.stderr)

    def test_the_license_gate_admits_a_wheel_that_declares_a_license(self):
        """Guard the guard. A step that always fails would satisfy the test above
        and would also make every future release impossible for the wrong
        reason. The synthetic metadata here chooses nothing for this
        distribution — it exercises the matcher."""
        for field in LICENSE_METADATA_FIELDS:
            with self.subTest(field=field):
                staged = Path(tempfile.mkdtemp(prefix="iptc-license-fixture-"))
                try:
                    wheel = staged / built().wheel.name
                    with zipfile.ZipFile(wheel, "w") as archive:
                        archive.writestr(
                            "{0}.dist-info/METADATA".format(ARTIFACT_STEM),
                            "Metadata-Version: 2.4\nName: {0}\nVersion: {1}\n"
                            "{2}: SYNTHETIC-FIXTURE\n".format(
                                DISTRIBUTION, VERSION, field))
                    result = self.run_gate(wheel)
                    self.assertEqual(
                        result.returncode, 0,
                        "the gate rejected a wheel that declares {0}:\n{1}{2}"
                        .format(field, result.stdout, result.stderr))
                finally:
                    shutil.rmtree(staged, ignore_errors=True)

    def run_gate(self, wheel: Path):
        """Run the workflow's own license preflight over ``wheel``.

        The command is read out of the workflow and executed verbatim, so this is
        a check on the bytes that will run remotely rather than on a
        reimplementation of them.
        """
        staged = Path(tempfile.mkdtemp(prefix="iptc-license-gate-"))
        try:
            (staged / "dist").mkdir()
            shutil.copy2(wheel, staged / "dist" / wheel.name)
            return subprocess.run(
                ["bash", "-c", self.license_gate_command()],
                cwd=str(staged), capture_output=True, text=True, timeout=300)
        finally:
            shutil.rmtree(staged, ignore_errors=True)


# ---------------------------------------------------------------------------
# The release document: the approval gate, the blocker, and the recovery
# ---------------------------------------------------------------------------


class TestTheReleaseDocsGateTheFirstUpload(unittest.TestCase):
    """Automation cannot hold the two decisions this release still needs: whether
    an owner approves publishing at all, and under which license.

    So the document is asserted for the things a releaser would otherwise have to
    guess — how the trusted publisher is registered, that the environment must
    require a reviewer, in what order to merge, tag and publish, what to compare
    afterwards, and what to do when it goes wrong. Every phrase below is a step
    someone has to take outside this repository.
    """

    # Absent document, failing tests — not a skip. See the note in the class
    # above: this repository's release story is only as strong as the checked-in
    # instructions for the steps automation cannot take.
    def setUp(self):
        self.text = release_docs_text()
        self.lowered = self.text.lower()

    def assertMentions(self, *phrases):
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.lower(), self.lowered,
                              "docs/iptc/RELEASING.md does not state: "
                              "{0!r}".format(phrase))

    def test_release_docs_document_approval_gate(self):
        """The claim the plan names: an explicit human checkpoint before any
        upload, enforced by a reviewer on the environment the workflow names."""
        self.assertMentions(
            "environment", PYPI_ENVIRONMENT, "required reviewer",
            "human", "approve",
        )
        self.assertIn(RELEASE_TAG, self.text)

    def test_the_docs_explain_how_the_trusted_publisher_is_registered(self):
        """Trusted publishing fails at upload time unless the publisher was
        registered on PyPI first, and the four values it is registered with are
        exactly the ones this workflow presents."""
        self.assertMentions(
            "trusted publish", "publish-machina-sports-canonical.yml",
            DISTRIBUTION, "oidc",
        )
        self.assertMentions("no api token", "pending publisher")

    def test_the_docs_block_the_first_upload_on_the_license_decision(self):
        """The blocker, stated where a releaser reads it and in the same terms the
        workflow enforces: the owner has to choose license metadata, and nothing
        in this repository may choose it for them."""
        self.assertIn("BLOCKED", self.text)
        self.assertMentions("license", "owner")
        for field in LICENSE_METADATA_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, self.text)

    def step_line(self, phrase: str) -> int:
        """The line the release step ``phrase`` is on.

        Line positions of named steps rather than the first occurrence of a bare
        word: "publish" appears in the workflow's own filename, so a first-
        occurrence comparison would be measuring prose, not the checklist.
        """
        line = line_index(self.lowered, phrase.lower())
        self.assertNotEqual(line, -1, "no release step says {0!r}".format(phrase))
        return line

    def test_the_docs_state_the_order_of_merge_tag_and_publish(self):
        """Tagging an unmerged branch releases a commit that is not on the default
        branch, and the tag is what starts the upload — so the order is the
        checklist's substance, not its presentation."""
        steps = ("merge the pull request", "push the tag", "approve the")
        lines = [self.step_line(phrase) for phrase in steps]
        self.assertEqual(lines, sorted(lines),
                         "release steps out of order: {0}".format(
                             list(zip(steps, lines))))

    def test_the_docs_require_comparing_the_published_bytes_with_the_reviewed_ones(self):
        self.assertMentions(RELEASE_DIGEST_FILE, "sha256", "compare")
        self.assertMentions("pypi.org/pypi/machina-sports-canonical/json")

    def test_the_docs_require_a_clean_install_from_the_index_afterwards(self):
        self.assertMentions(
            "pip install {0}=={1}".format(DISTRIBUTION, VERSION),
            "clean",
        )
        self.assertIn(IMPORT_NAME, self.text)

    def test_the_docs_state_the_recovery_path_and_that_a_version_is_spent(self):
        """A bad 0.1.0 cannot be replaced; deleting it does not free the version.
        A document that omits that invites exactly the wrong recovery."""
        self.assertMentions("yank", "0.1.1", "cannot")

    def test_the_docs_record_the_reviewed_digests_and_name_the_file_that_holds_them(self):
        """The document said "the digests below" and listed none.

        So the checklist's own compare step — "read the digests in the build job
        log and compare them with the digests reviewed at the checkpoint above" —
        had nothing on either side of the comparison, and a releaser could only
        approve on trust. Both artefact names, both full hashes, and the checksum
        file named as the authority the automation diffs against.
        """
        self.assertIn(RELEASE_CHECKSUM_FILE, self.text)
        self.assertMentions("release candidate", "reviewed")
        for name, digest in REVIEWED_RELEASE_DIGESTS:
            with self.subTest(artefact=name):
                self.assertIn(name, self.text)
                self.assertIn(digest, self.text)

    def test_the_docs_record_the_reproducible_build_epoch(self):
        """The releaser has to be able to rebuild the reviewed bytes locally, and
        that is only possible with the epoch the release job used."""
        self.assertIn("SOURCE_DATE_EPOCH", self.text)
        self.assertIn(RELEASE_SOURCE_DATE_EPOCH, self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
