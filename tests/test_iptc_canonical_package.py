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
import site
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
VERSION = "0.2.0"

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

#: The owner-approved license decision for this distribution, and the three files
#: that carry it.
#:
#: TWO LICENSES, ONE ARCHIVE. The Machina-authored Python runtime, the adapters and
#: the build tooling are MIT. Two packaged assets carry CC-BY-4.0 attribution
#: obligations instead: ``official-property-names.json`` is extracted and generated
#: from IPTC Sport Schema 1.1, and ``shared-context.json`` is Machina-authored but
#: reproduces that work's pinned namespace bindings. The distribution therefore
#: expresses ``MIT AND CC-BY-4.0`` — a conjunction, because both sets of terms
#: apply to different members of the same archive, and CC BY is never placed over
#: the software.
LICENSE_EXPRESSION = "MIT AND CC-BY-4.0"
MIT_LICENSE_FILE = "LICENSES/MIT.txt"
CC_BY_LICENSE_FILE = "LICENSES/CC-BY-4.0.txt"
NOTICE_FILE = "NOTICE-IPTC.md"

#: In declaration order, because ``License-File`` appears in METADATA in the order
#: ``pyproject.toml`` lists it and this suite compares an ordered list rather than
#: a set: a reordering is a metadata change and should read as one.
LICENSE_FILES = (MIT_LICENSE_FILE, CC_BY_LICENSE_FILE, NOTICE_FILE)

#: Where PEP 639 stores them inside the wheel. Under ``dist-info``, so the closed
#: RECORD set above already accounts for them as distribution metadata rather than
#: as importable payload — a license file inside the import namespace would be a
#: module-shaped file a consumer could shadow.
WHEEL_LICENSE_PREFIX = "{0}.dist-info/licenses/".format(ARTIFACT_STEM)

#: The MIT text, exactly. Byte-identical to the sibling `sports-skills/LICENSE`,
#: because the two distributions publish the same canonical bytes and a
#: paraphrased MIT is not MIT. Written out here rather than read from that
#: repository: this suite must hold with nothing beside this checkout.
MIT_LICENSE_TEXT = '''MIT License

Copyright (c) 2026 Machina Sports

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

#: The official CC BY 4.0 legal code, pinned by digest rather than described.
#:
#: A license text this repository paraphrased, truncated or reflowed would not be
#: the license it names in ``License-Expression``, and the failure mode is
#: invisible: the file still reads like CC BY. So the bytes are pinned to the
#: plain-text legal code published at
#: ``https://creativecommons.org/licenses/by/4.0/legalcode.txt``, and the markers
#: below make a red diff legible — a digest mismatch alone says nothing about
#: which half of the text moved.
CC_BY_LICENSE_SHA256 = \
    "9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411"

#: `.gitattributes`, and what the vendored rule for the CC BY legal code must set.
#:
#: THE OFFICIAL TEXT ENDS IN A BLANK LINE. That byte is part of what Creative
#: Commons publishes and therefore part of the pinned digest above, and Git's
#: whitespace check calls it an error — `new blank line at EOF`. Trimming it would
#: make the file cheaper to commit and would stop it being the CC BY 4.0 legal
#: code, silently, in a way that reads correctly. So Git is told to leave this one
#: file alone, exactly as the repository already does for the pinned upstream
#: ontologies, and the rule is asserted to reach nothing else.
GITATTRIBUTES_FILE = ".gitattributes"
GITATTRIBUTES_PATH = REPO_ROOT / GITATTRIBUTES_FILE
VENDORED_ATTRIBUTES = ("linguist-vendored", "-diff", "-whitespace")
CC_BY_LICENSE_LINES = 396
CC_BY_LICENSE_MARKERS = (
    "Attribution 4.0 International",
    "Creative Commons Attribution 4.0 International Public License",
    "Section 1 -- Definitions.",
    "Section 2 -- Scope.",
    "Section 3 -- License Conditions.",
    "Section 4 -- Sui Generis Database Rights.",
    "Section 5 -- Disclaimer of Warranties and Limitation of Liability.",
    "Section 6 -- Term and Termination.",
    "Section 7 -- Other Terms and Conditions.",
    "Section 8 -- Interpretation.",
)

#: The upstream work the CC-BY-4.0 half of the expression attributes, spelled
#: exactly as its own pinned bytes declare it. `agent-templates/iptc-mappings/
#: references/iptc-sport-schema-1.1/` holds the declaration these strings come
#: from; the ontology files themselves are NOT shipped in this distribution.
UPSTREAM_WORK = "IPTC Sport Schema 1.1"
UPSTREAM_CREATOR = "IPTC Sports Content Working Group"
UPSTREAM_COPYRIGHT = (
    "Copyright (C) International Press Telecommunications Council 2024")
UPSTREAM_SOURCE_PIN = ("https://github.com/iptc/sport-schema/tree/"
                       "0e77bf8678f3702fe81c28673bede35efe47d633")
CC_BY_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"

#: The two packaged assets the notice has to classify individually, and the phrase
#: each classification turns on. A single blanket sentence over "the JSON
#: resources" would be wrong in both directions: one file is extracted from the
#: upstream work and the other is authored here and reproduces its bindings.
ATTRIBUTION_ASSET_CLASSIFICATIONS = (
    ("official-property-names.json", "extracted"),
    ("shared-context.json", "Machina-authored"),
)

#: A blanket "no changes were made" is the one attribution claim this notice may
#: not make. The upstream ontologies are not shipped at all; what ships is an
#: allowlist extracted and generated from them and a context reproducing their
#: bindings, so the CC BY "indicate if changes were made" obligation is discharged
#: by saying what was done — never by denying that anything was.
FORBIDDEN_NOTICE_CLAIMS = (
    "no changes were made",
    "no modifications were made",
    "unmodified",
)

#: Nothing here may read as an IPTC endorsement of this distribution. Attribution
#: is a requirement of the license; endorsement is a claim the license explicitly
#: does not grant.
FORBIDDEN_ENDORSEMENT_CLAIMS = (
    "endorsed by iptc",
    "endorsed by the iptc",
    "iptc endorses",
    "in partnership with iptc",
    "approved by iptc",
    "certified by iptc",
)

#: The complete set of build inputs, copied into the staging tree. A file the
#: build needs that is missing here makes the build fail rather than silently
#: succeed against the repository it was supposed to be isolated from.
#:
#: THE LICENSE FILES ARE BUILD INPUTS, NOT DOCUMENTATION. ``license-files`` in
#: ``pyproject.toml`` makes setuptools read them at build time and write them into
#: both artefacts, so a staging copy without them builds a wheel whose METADATA
#: names three files the archive does not carry — or fails outright. Either way the
#: staged build stops being the release build, which is the one thing this staging
#: set exists to guarantee.
PACKAGING_INPUTS = (
    "pyproject.toml",
    "setup.py",
    "MANIFEST.in",
    "README-machina-sports-canonical.md",
    "LICENSES",
    NOTICE_FILE,
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
    MIT_LICENSE_FILE,
    CC_BY_LICENSE_FILE,
    NOTICE_FILE,
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
INSTALLED_CONFORMANCE_JOB = "installed-conformance"

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

#: The dedicated suite that reruns the canonical/provider contracts against the
#: reviewed wheel installed in site-packages rather than this repository's
#: ``tools/iptc/canonical`` source tree.
INSTALLED_CONFORMANCE_SUITE = "tests/test_iptc_installed_conformance.py"

#: The validator closure is needed by the reused four-layer conformance tests.
#: Like the build closure, the workflow may install it only from its checked-in,
#: exactly pinned requirements file.
VALIDATOR_REQUIREMENTS = "requirements-iptc-validator.txt"

#: The installed-conformance job executes checkout code and creates the isolated
#: Python environment, so it uses the same reviewed immutable action commits as
#: the release build rather than mutable major-version tags.
CHECKOUT_ACTION = (
    "uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
    "  # v4"
)
SETUP_PYTHON_ACTION = (
    "uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"
    "  # v5"
)

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
    MIT_LICENSE_FILE,
    CC_BY_LICENSE_FILE,
    NOTICE_FILE,
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

#: What still stops this release now that the license decision is made, each stated
#: as its own sentence in `docs/iptc/RELEASING.md`.
#:
#: A resolved blocker is the kind of change that reads like an unblocking. It is
#: not one: the reviewer-gated environment does not exist yet, PyPI has no
#: publisher registered for this project, and no owner has said "publish". Listing
#: them individually is what keeps "still blocked" from being a sentence a
#: releaser can argue past.
#:
#: THREE, NOT FOUR. The digest hold below has been closed on evidence — the
#: renewed rows were rebuilt independently from a clean export of the exact
#: package-input candidate on both proven interpreters. Every remaining hold needs
#: an action outside this repository, which is precisely why none of them can be
#: closed by a commit.
#: The three absolutes this document used to state, asserted **absent**.
#:
#: Each was true when written and each is now provably false: the `pypi`
#: environment carries a required reviewer and a branch policy, the registry
#: serves `0.1.0` at the digests recorded below — which only a working trusted
#: publisher could have uploaded — and the owner has approved the release.
#: A blocker that has been cleared but still reads as blocking is not a
#: conservative document; it teaches a releaser that this file's warnings are
#: stale and can be stepped past, which is exactly the habit the real gates
#: depend on them not having.
FALSE_RELEASE_ABSOLUTES = (
    "the pypi environment is not configured",
    "the trusted publisher is not registered",
    "no human has approved publication",
    "pypi has no pending publisher",
    "does not exist with a required human reviewer",
)

#: The evidence that closed them, named so the claim is falsifiable rather than
#: asserted. A reader with repository access can re-check every one of these.
RELEASE_PREREQUISITE_EVIDENCE = (
    # The publish workflow ran to success on the 0.1.0 tag, which is only
    # possible if the environment resolved and the OIDC exchange was accepted.
    "31743535579",
    "machina-sports-canonical-v0.1.0",
    "48d4168162fc84b48931b82971738b9359298dde",
)

#: The gates that still stand at release time. Closed prerequisites are not an
#: open door: they mean the *standing setup* is in place, and every per-release
#: check below still has to pass on its own evidence.
#:
#: The runtime reviewer is the load-bearing one. It is enforced by GitHub, not by
#: any file here, and it is the only thing between a pushed tag and an upload.
RELEASE_TIME_GATE_PHRASES = (
    "required reviewer",
    "merge",
    "tag",
    "sha256sum --check",
    "license",
    "after publishing",
)

#: The hold the renewed verification closed, spelled as the document used to state
#: it. Asserted ABSENT: a document that records the rebuild and still carries the
#: sentence saying it never happened is a document a releaser cannot act on, and
#: leaving the stale claim in is the likeliest way this follow-up goes wrong.
CLOSED_RELEASE_HOLD = "the renewed digests have not been independently verified"

#: The candidate the renewed digests were independently rebuilt from, in full.
#:
#: The full forty characters rather than a short prefix: this is the commit whose
#: package inputs produced the bytes the release will upload, and an abbreviation
#: is a claim about a prefix. `acf9955` is the commit that added the approved
#: licensing, which is what changed the artefacts in the first place.
RENEWED_VERIFICATION_COMMIT = "acf9955029652c493f10ecd46cb7936dd44d6662"

#: Three jobs, because approval has to sit between building and uploading, and a
#: GitHub Release must not claim bytes PyPI never accepted. The build job produces
#: the artefacts with no upload scope at all; the publish job has the OIDC scope
#: and uploads them; the release job runs only after that succeeds and attaches
#: the same downloaded bytes to the tag.
RELEASE_BUILD_JOB = "build"
RELEASE_PUBLISH_JOB = "publish"
RELEASE_GITHUB_JOB = "release"

#: The GitHub environment the publish job runs in. The reviewer requirement lives
#: on the environment, not in this repository — which is exactly why
#: `docs/iptc/RELEASING.md` has to spell out that it must be configured, and why
#: this suite asserts the job is bound to it.
PYPI_ENVIRONMENT = "pypi"

#: The action that exchanges the job's short-lived OIDC token for an upload
#: token. No password, no username, no long-lived secret in this repository.
TRUSTED_PUBLISHER_ACTION = "pypa/gh-action-pypi-publish"

#: The two actions the release job is allowed to run, at the reviewed immutable
#: commits. The download pin is deliberately the same one the publish job uses.
DOWNLOAD_ARTIFACT_ACTION = (
    "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
    "  # v4"
)
GITHUB_RELEASE_ACTION = (
    "softprops/action-gh-release@3bb12739c298aeb8a4eeaf626c5b8d85266b0e65"
    "  # v2"
)

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
RELEASE_CHECKSUM_FILE = "docs/iptc/machina-sports-canonical-0.2.0.sha256"
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
     "177bec5af3a2984898a412eaedaa1725103b102d9191dcb8dfdb35d8f4d8d19d"),
    ("{0}.tar.gz".format(ARTIFACT_STEM),
     "60f6ee03a64ecd8e38aba257675ee2b91b71008b7cdca5ad7880afceaa70102a"),
)

#: The digests the reviewed file carried before the license decision, kept as a
#: named constant for one reason: the independent verification recorded in
#: `docs/iptc/RELEASING.md` reproduced *these* bytes, at a commit that predates the
#: license metadata. Adding `License-Expression`, three `License-File` fields and
#: three archive members changes both artefacts, so that evidence now describes a
#: superseded candidate and the document has to say so rather than appear to vouch
#: for rows nobody rebuilt.
#: The artefact stem the *historical* verification evidence actually rebuilt.
#:
#: Pinned to the version it verified rather than derived from `ARTIFACT_STEM`,
#: which moves with the distribution. While it was derived, bumping the version
#: silently re-stamped every historical row with the new filename, so the document
#: read as though a rebuild of 0.1.0 had verified 0.2.0's bytes. A record of what
#: happened must not move when what happens next changes.
HISTORICAL_VERIFIED_STEM = "machina_sports_canonical-0.1.0"

SUPERSEDED_RELEASE_DIGESTS = (
    ("{0}-py3-none-any.whl".format(HISTORICAL_VERIFIED_STEM),
     "3c7fcbc539824ced118099f691ac23c3182c59ad0855aaec560d43dabb53361b"),
    ("{0}.tar.gz".format(HISTORICAL_VERIFIED_STEM),
     "11783dd7fff89b634e55bccdd17952679b8f7362fe9fd0bfa8a378a5dbe8d324"),
)

#: The rows the renewed independent rebuild at :data:`RENEWED_VERIFICATION_COMMIT`
#: reproduced: the digests 0.1.0 shipped, under 0.1.0's filenames. History, and
#: therefore never regenerated.
HISTORICAL_RELEASE_DIGESTS = (
    ("{0}-py3-none-any.whl".format(HISTORICAL_VERIFIED_STEM),
     "c162c20514a3d3ad2d5f43e5392ce23fc52053edc44a4ed60599f0a2db6dd9bf"),
    ("{0}.tar.gz".format(HISTORICAL_VERIFIED_STEM),
     "5ba1fcc65182cce58b40df478bf74e04937a4350dbe9fa3eebe0bfa2d7f1894e"),
)

#: The commit whose `git archive` export was rebuilt to verify the 0.2.0 rows.
#:
#: The successor of the commit `package-receipt.json` pins, and necessarily so:
#: the receipt names the canonical *source* commit, and the commit that records
#: the resulting digests is the one after it. Named in full, because an
#: abbreviation is a claim about a prefix.
VERIFIED_RELEASE_COMMIT = "c5750ffa5656e4285c40ad734d05c41588475f6b"

#: The two interpreters that independently reproduced the 0.2.0 rows, at the
#: patch level each actually ran.
#:
#: NOT :data:`INDEPENDENT_VERIFICATION_INTERPRETERS`. That tuple records what
#: rebuilt 0.1.0, on 3.9.**25**; this rebuild ran on 3.9.**6**. Reusing one tuple
#: for both would silently restate whichever patch version was edited last, and a
#: verification record that names an interpreter nobody ran is worse than one that
#: names none.
VERIFIED_RELEASE_INTERPRETERS = ("3.9.6", "3.11.14")

#: What a CLOSED verification record must state.
#:
#: `git archive` is load-bearing rather than decorative: a rebuild from a working
#: tree proves nothing, because an untracked file or a build cache can contribute
#: bytes. The isolation is the evidence.
CLOSED_VERIFICATION_PHRASES = (
    "independently verified",
    "git archive",
)

#: Asserted ABSENT once the rebuild has happened. A document that records the
#: verification and still carries the sentence saying it never happened
#: contradicts itself about the one thing a releaser reads it for — the same rule
#: :data:`CLOSED_RELEASE_HOLD` enforces one version earlier.
OPEN_CANDIDATE_CLAIM = "have not been independently verified"

#: Closing the digest hold closes the digest hold. It is not release approval, it
#: does not stand in for the required reviewer, and the three external holds are
#: untouched by it — so the record has to keep saying so.
VERIFICATION_IS_NOT_APPROVAL_PHRASES = (
    "not release approval",
    "do not publish",
)

#: The fixed point the release metadata has to reach, and the evidence it was
#: reached. Named phrase by phrase, because a releaser who is told only "it is
#: blocked" has been given a dead end rather than a procedure.
#:
#: THE MECHANISM, NOT THE STEP LABELS. An earlier version of this asserted the
#: words "commit a" and "commit b", which described the sequence only while it was
#: still ahead of us; once the re-pin landed, the document stopped narrating steps
#: and started recording a state, and the gate failed on prose rather than on
#: substance. What must always be present is *why* the metadata is
#: self-referential and *which* values resolve it.
FIXED_POINT_SEQUENCE_PHRASES = (
    "package-receipt.json",
    "source_commit",
    "source_date_epoch",
    "fixed point",
)

#: The commit the canonical source is pinned to, and the epoch derived from it.
#: Asserted in the release document as well as in the receipt, because a releaser
#: reconstructing a build reads the document and must not have to open a JSON file
#: to discover which two values the build depends on.
FIXED_POINT_COMMIT = "1b20df3c55b2c8a2ce2112c17fc2cfca65f86bbc"

#: The candidate whose digests were rebuilt outside the agent that produced them,
#: and the two patch-level interpreters that rebuilt it.
#:
#: Every check above compares a build with rows this repository checked in — which
#: proves the rows are reproducible, not that they were ever reproduced by anyone
#: other than the process that wrote them. A releaser approving the upload is
#: entitled to know that someone rebuilt the exact candidate from a clean export,
#: with what, and that the rebuild is evidence rather than the approval itself.
INDEPENDENT_VERIFICATION_COMMIT = "f46799c"
INDEPENDENT_VERIFICATION_INTERPRETERS = ("3.9.25", "3.11.14")

#: The one artefact that crosses the approval gate. The publish job downloads it
#: and uploads those bytes; it never builds. Version-free, so releasing 0.1.1
#: needs no edit to the workflow — the tag pattern is version-open too.
RELEASE_ARTIFACT_NAME = "{0}-release".format(DISTRIBUTION)

#: Exactly what the GitHub Release exposes. Patterns stay version-open, while
#: the build helper and the package proof enforce exactly one wheel and one sdist.
GITHUB_RELEASE_ATTACHMENTS = ("dist/*.whl", "dist/*.tar.gz",
                              RELEASE_DIGEST_FILE)

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
CANONICAL_SOURCE_COMMIT = "1b20df3c55b2c8a2ce2112c17fc2cfca65f86bbc"
RELEASE_SOURCE_DATE_EPOCH = "1786714340"

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
#:
#: The three license members are added by ``setuptools`` from ``license-files``,
#: not by ``MANIFEST.in``: PEP 639 makes them part of the distribution's metadata,
#: so an sdist that could not rebuild its own ``License-File`` fields would be an
#: sdist whose wheel is not the released wheel.
EXPECTED_SDIST_MEMBERS = (
    CC_BY_LICENSE_FILE,
    MIT_LICENSE_FILE,
    "MANIFEST.in",
    NOTICE_FILE,
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

#: The two `METADATA` fields the publish preflight reads. Both are named here so
#: the preflight command can be found in the workflow by the fields it inspects.
#:
#: THE GATE IS NO LONGER "ANY LICENSE FIELD". While it accepted the mere presence
#: of `License-Expression` OR `License-File`, a wheel declaring
#: `License-Expression: Proprietary` and no license file at all would have passed
#: it — and so would the reverse. The owner decision is a specific expression and a
#: specific set of three files, so the gate now requires exactly those, and the
#: tests below feed it wrong expressions and dropped files one at a time.
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


def clean_sdist_install(python_exe: str, label: str) -> Path:
    """A separate venv with the built sdist installed through closed PEP 517.

    The venv receives a path file naming the running interpreter's site-packages
    solely so its build frontend can use the exact versions pinned by
    ``requirements-iptc-build.txt``.  ``--no-build-isolation`` prevents pip from
    creating a second, resolver-populated build environment; ``--no-index`` and
    ``--no-deps`` close every remaining network/dependency path.  The install is
    launched from a neutral directory, and the runtime probe comparing it with
    the wheel is neutral too.
    """
    if label in _INSTALLS:
        return _INSTALLS[label]
    venv_dir = workspace() / "venv-{0}".format(label)
    creation = subprocess.run(
        [python_exe, "-m", "venv", str(venv_dir)],
        capture_output=True, text=True, timeout=600)
    if creation.returncode != 0:
        raise AssertionError("could not create a venv for {0}:\n{1}".format(
            label, creation.stdout + creation.stderr))
    venv_python = venv_dir / ("Scripts" if os.name == "nt" else "bin") \
        / ("python.exe" if os.name == "nt" else "python")
    site_roots = [Path(path).resolve() for path in site.getsitepackages()]
    for path in site_roots:
        if path == REPO_ROOT or REPO_ROOT in path.parents:
            raise AssertionError("current site-packages reaches repository: "
                                 + str(path))
    (purelib(venv_python) / "iptc-pinned-build-tooling.pth").write_text(
        "".join("{0}\n".format(path) for path in site_roots), encoding="utf-8")
    neutral = Path(tempfile.mkdtemp(prefix="iptc-sdist-install-"))
    try:
        install = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--no-index",
             "--no-deps", "--no-build-isolation", "--ignore-installed",
             "--no-cache-dir", "--disable-pip-version-check",
             str(built().sdist)],
            cwd=str(neutral), capture_output=True, text=True, timeout=900)
    finally:
        shutil.rmtree(neutral, ignore_errors=True)
    if install.returncode != 0:
        raise AssertionError("offline sdist install failed for {0}:\n{1}".format(
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


def metadata_values(metadata: str, field: str) -> list:
    """Every value ``field`` carries in ``metadata``, in file order.

    A list rather than a set: ``License-File`` is repeatable, and the order it is
    written in is the order ``pyproject.toml`` declares. A set would call a
    reordering equal, and a reordering is a change to published metadata.
    """
    prefix = "{0}: ".format(field)
    return [line[len(prefix):].strip() for line in metadata.splitlines()
            if line.startswith(prefix)]


def source_license_bytes() -> dict:
    """The three checked-in license and notice files, keyed by declared path."""
    return {relative: (REPO_ROOT / relative).read_bytes()
            for relative in LICENSE_FILES}


def wheel_license_members(wheel: Path) -> dict:
    """What the wheel carries under ``dist-info/licenses/``, keyed as declared."""
    with zipfile.ZipFile(wheel) as archive:
        return {name[len(WHEEL_LICENSE_PREFIX):]: archive.read(name)
                for name in archive.namelist()
                if name.startswith(WHEEL_LICENSE_PREFIX)}


def gitattributes_rules() -> list:
    """``.gitattributes`` as ``(pattern, [attribute, ...])``, comments dropped.

    Parsed rather than substring-matched so a rule can be asserted to reach one
    path and no other: `assertIn("LICENSES/CC-BY-4.0.txt", text)` would be equally
    satisfied by a `LICENSES/**` line that also exempted the MIT text from review.
    """
    rules = []
    for line in GITATTRIBUTES_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        rules.append((fields[0], fields[1:]))
    return rules


def check_attr(*paths) -> list:
    """``git check-attr`` for the attributes this suite cares about, as lines.

    Git's own answer, not this suite's reading of the file: pattern syntax has
    precedence rules, and a rule that parses correctly can still fail to apply.
    """
    result = subprocess.run(
        ["git", "check-attr", "whitespace", "diff", "--"] + list(paths),
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise AssertionError("git check-attr failed: {0}{1}".format(
            result.stdout, result.stderr))
    return result.stdout.splitlines()


def notice_text() -> str:
    return (REPO_ROOT / NOTICE_FILE).read_text(encoding="utf-8")


def package_readme_text() -> str:
    return (REPO_ROOT / "README-machina-sports-canonical.md").read_text(
        encoding="utf-8")


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


def literal_block_lines(block: str, key: str) -> list:
    """The non-comment lines in a job's ``key: |`` scalar.

    This keeps the release attachment assertion exact without importing a YAML
    parser into the Python 3.9 package-proof environment.
    """
    lines = block.splitlines()
    for index, raw in enumerate(lines):
        if raw.strip() != "{0}: |".format(key):
            continue
        indent = len(raw) - len(raw.lstrip())
        found = []
        for child in lines[index + 1:]:
            if not child.strip():
                continue
            child_indent = len(child) - len(child.lstrip())
            if child_indent <= indent:
                break
            if not child.strip().startswith("#"):
                found.append(child.strip())
        return found
    return []


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
        self.assertEqual(payload["profile"], "machina-iptc-profile/1.2")
        self.assertEqual(payload["schema"], "canonical-observation/1.1")
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

    def test_sdist_install_has_exactly_the_wheel_installs_members_and_bytes(self):
        """An sdist install is a separate consumer path, even though the default
        PEP 517 build already constructs the reviewed wheel from that sdist.

        Install each artefact into its own clean environment, then compare the
        installed package in both membership directions and byte-for-byte.  This
        is intentionally wider than the source comparison above: it proves the
        two distribution formats produce the same runtime, not merely that each
        member we expected happened to appear in one of them.
        """
        wheel_python = clean_install(sys.executable, "parity-wheel")
        sdist_python = clean_sdist_install(sys.executable, "parity-sdist")
        wheel_root = installed_root(wheel_python)
        sdist_root = installed_root(sdist_python)
        wheel_members = installed_members(wheel_python)
        sdist_members = installed_members(sdist_python)

        self.assertNotEqual(wheel_root, sdist_root)
        self.assertEqual(wheel_members - sdist_members, set(),
                         "members installed only from the wheel")
        self.assertEqual(sdist_members - wheel_members, set(),
                         "members installed only from the sdist")
        for member in sorted(wheel_members | sdist_members):
            with self.subTest(member=member):
                self.assertEqual((wheel_root / member).read_bytes(),
                                 (sdist_root / member).read_bytes())

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
# The license decision: two licenses, three files, one aggregate expression
# ---------------------------------------------------------------------------
#
# The owner decided this distribution is `MIT AND CC-BY-4.0`: MIT over the
# Machina-authored Python runtime, adapters and build tooling; CC-BY-4.0
# attribution obligations over the two packaged assets that derive from — or
# reproduce bindings of — IPTC Sport Schema 1.1. The classes below hold that
# decision to the artefacts rather than to a document: the expression as METADATA
# spells it, the three files as METADATA names them, and the same bytes inside
# both the wheel and the sdist.


def pyproject() -> dict:
    """``pyproject.toml``, parsed.

    ``tomllib`` on 3.11+ and the pinned ``tomli`` below it — the same conditional
    the build frontend itself resolves, so this needs nothing the declared floor
    does not already install from ``requirements-iptc-build.txt``.
    """
    try:
        import tomllib
    except ImportError:  # the declared floor
        import tomli as tomllib
    return tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


class TestTheLicenseTextsAreTheRealOnes(unittest.TestCase):
    """A license file this repository wrote from memory is not the license.

    Both texts are held to their authoritative form: MIT byte-identical to the
    sibling distribution publishing the same canonical bytes, and CC BY 4.0
    byte-identical to the legal code Creative Commons publishes. Neither is
    paraphrased, reflowed or summarized, because a summary of a license grants
    nothing and the failure is invisible on reading.
    """

    def test_the_mit_text_is_the_standard_text_with_the_machina_copyright(self):
        path = REPO_ROOT / MIT_LICENSE_FILE
        self.assertTrue(path.is_file(), "missing: {0}".format(MIT_LICENSE_FILE))
        self.assertEqual(path.read_text(encoding="utf-8"), MIT_LICENSE_TEXT)

    def test_the_cc_by_text_is_the_official_legal_code(self):
        path = REPO_ROOT / CC_BY_LICENSE_FILE
        self.assertTrue(path.is_file(), "missing: {0}".format(CC_BY_LICENSE_FILE))
        blob = path.read_bytes()
        self.assertEqual(sha256_bytes(blob), CC_BY_LICENSE_SHA256,
                         "this is not the official CC BY 4.0 legal code; it must "
                         "be the text published by Creative Commons, never a "
                         "paraphrase")
        text = blob.decode("utf-8")
        self.assertEqual(len(text.splitlines()), CC_BY_LICENSE_LINES)
        for marker in CC_BY_LICENSE_MARKERS:
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_the_cc_by_text_is_not_the_human_readable_summary(self):
        """Guard the guard. The deed at ``creativecommons.org/licenses/by/4.0/``
        is a summary and says so; shipping it in place of the legal code would
        look right and grant nothing."""
        text = (REPO_ROOT / CC_BY_LICENSE_FILE).read_text(encoding="utf-8")
        for summary_marker in ("This deed highlights only some of the key features",
                              "human-readable summary of (and not a substitute"):
            with self.subTest(marker=summary_marker):
                self.assertNotIn(summary_marker, text)

    def test_the_official_text_ends_in_the_blank_line_git_objects_to(self):
        """The reason the rule below has to exist, stated as bytes.

        Creative Commons ends the legal code with a blank line. It is inside the
        pinned digest, so removing it to satisfy a pre-commit whitespace check
        would silently stop this file being CC BY 4.0 — the failure a reader
        cannot see. This asserts the byte is there, so the exemption is never
        "simplified" by deleting what it protects.
        """
        blob = (REPO_ROOT / CC_BY_LICENSE_FILE).read_bytes()
        self.assertTrue(blob.endswith(b"\n\n"),
                        "the official trailing blank line was trimmed; the file "
                        "is no longer the published legal code")
        self.assertEqual(sha256_bytes(blob), CC_BY_LICENSE_SHA256)

    def test_git_is_told_to_leave_the_vendored_cc_by_text_alone(self):
        """One rule, naming that one file, marking it vendored and turning diff
        and whitespace checking off — the same treatment, for the same reason, as
        the pinned upstream ontologies already declared in this file."""
        matching = [attributes for pattern, attributes in gitattributes_rules()
                    if pattern == CC_BY_LICENSE_FILE]
        self.assertEqual(len(matching), 1,
                         "expected exactly one {0} rule for {1}, found {2}".format(
                             GITATTRIBUTES_FILE, CC_BY_LICENSE_FILE, matching))
        self.assertEqual(matching[0], list(VENDORED_ATTRIBUTES))

    def test_the_exemption_reaches_no_authored_file(self):
        """`LICENSES/MIT.txt` and `NOTICE-IPTC.md` are Machina-authored and are
        reviewed like anything else. A broad `LICENSES/**` rule would have fixed
        the commit and quietly dropped both out of whitespace and diff review."""
        patterns = [pattern for pattern, _ in gitattributes_rules()]
        for authored in (MIT_LICENSE_FILE, NOTICE_FILE):
            with self.subTest(authored=authored):
                self.assertNotIn(authored, patterns)
        for broad in ("LICENSES/*", "LICENSES/**", "LICENSES/", "LICENSES",
                      "*.txt", "LICENSES/*.txt"):
            with self.subTest(broad=broad):
                self.assertNotIn(broad, patterns,
                                 "{0} exempts more than the vendored legal "
                                 "code".format(broad))

    def test_git_itself_applies_the_exemption_to_that_file_and_no_other(self):
        """Asked of Git rather than of the file, because a rule can parse and
        still not apply — and because this is the behaviour the pre-commit hook
        and CI actually observe."""
        lines = check_attr(CC_BY_LICENSE_FILE, MIT_LICENSE_FILE, NOTICE_FILE)
        for attribute in ("whitespace", "diff"):
            with self.subTest(attribute=attribute, path=CC_BY_LICENSE_FILE):
                self.assertIn("{0}: {1}: unset".format(CC_BY_LICENSE_FILE,
                                                       attribute), lines)
            for authored in (MIT_LICENSE_FILE, NOTICE_FILE):
                with self.subTest(attribute=attribute, path=authored):
                    self.assertIn("{0}: {1}: unspecified".format(authored,
                                                                 attribute), lines)

    def test_the_license_texts_are_not_mixed_up(self):
        """Two files, two licenses. A copy-paste that put CC BY in ``MIT.txt``
        would satisfy "both files exist" and misstate both halves."""
        mit = (REPO_ROOT / MIT_LICENSE_FILE).read_text(encoding="utf-8")
        cc_by = (REPO_ROOT / CC_BY_LICENSE_FILE).read_text(encoding="utf-8")
        self.assertNotIn("Creative Commons", mit)
        self.assertNotIn("MIT License", cc_by)


class TestTheNoticeAttributesTheUpstreamWork(unittest.TestCase):
    """`NOTICE-IPTC.md` is how the CC BY attribution obligation is discharged for
    a consumer who has only the installed package.

    CC BY 4.0 requires the creator, the copyright notice, a link to the license,
    an identification of the material, and an indication of whether changes were
    made. It grants no endorsement, and it does not reach the software. So the
    notice is asserted for each of those, and asserted *not* to claim the two
    things it must not: that nothing was changed, and that IPTC endorses this.
    """

    def setUp(self):
        self.path = REPO_ROOT / NOTICE_FILE
        self.assertTrue(self.path.is_file(), "missing: {0}".format(NOTICE_FILE))
        self.text = notice_text()
        self.lowered = self.text.lower()

    def test_the_notice_names_the_work_creator_copyright_source_and_license(self):
        for required in (UPSTREAM_WORK, UPSTREAM_CREATOR, UPSTREAM_COPYRIGHT,
                         UPSTREAM_SOURCE_PIN, CC_BY_LICENSE_URL, "CC-BY-4.0"):
            with self.subTest(required=required):
                self.assertIn(required, self.text,
                              "{0} does not state: {1!r}".format(NOTICE_FILE,
                                                                 required))

    def test_the_source_pin_is_the_exact_commit_and_not_a_moving_ref(self):
        """A link to the default branch attributes whatever upstream looks like
        today. The allowlist was extracted from one commit, and that commit is the
        only honest source statement."""
        self.assertIn("0e77bf8678f3702fe81c28673bede35efe47d633", self.text)
        for moving in ("/tree/main", "/tree/master", "/tree/HEAD"):
            with self.subTest(ref=moving):
                self.assertNotIn(moving, self.text)

    def test_the_notice_classifies_each_attribution_bearing_asset_by_name(self):
        """File level, not archive level. The two assets carry the CC BY
        obligation for different reasons, and a reader deciding how to reuse one
        of them cannot act on a sentence about "the JSON resources"."""
        for asset, classification in ATTRIBUTION_ASSET_CLASSIFICATIONS:
            with self.subTest(asset=asset):
                self.assertIn(asset, self.text,
                              "{0} does not classify {1}".format(NOTICE_FILE,
                                                                 asset))
                self.assertIn(classification.lower(), self.lowered,
                              "{0} does not say {1} is {2}".format(
                                  NOTICE_FILE, asset, classification))

    def test_the_notice_states_the_extraction_rather_than_denying_change(self):
        """The obligation is to indicate whether changes were made, and the true
        answer here is not "none": the upstream ontology files are not shipped, the
        allowlist is extracted and generated from them, and the context reproduces
        their bindings. A blanket "no changes" would be a false attribution
        statement about material that was in fact derived."""
        for phrase in ("extract", "generat", "reproduc"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.lowered,
                              "{0} does not say what was done to the upstream "
                              "material".format(NOTICE_FILE))
        for forbidden in FORBIDDEN_NOTICE_CLAIMS:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.lowered,
                                 "{0} makes a blanket no-change claim, which is "
                                 "not true of extracted or reproduced "
                                 "material".format(NOTICE_FILE))

    def test_the_notice_says_the_upstream_ontology_files_are_not_shipped(self):
        """What is attributed matters as much as who is attributed: a reader must
        not conclude that the pinned ``.ttl`` bytes are inside this wheel."""
        self.assertIn("not shipped", self.lowered)
        self.assertIn("ontolog", self.lowered)

    def test_the_notice_keeps_the_software_under_mit(self):
        """CC BY must not be read as covering the Python runtime. The boundary is
        stated in the notice itself, because the notice is the file a consumer
        reads when they see ``CC-BY-4.0`` in the expression and go looking for what
        it applies to."""
        self.assertIn("MIT", self.text)
        for phrase in ("mit", "software"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.lowered)
        self.assertIn(MIT_LICENSE_FILE, self.text)
        self.assertIn(LICENSE_EXPRESSION, self.text)

    def test_the_notice_makes_no_endorsement_claim(self):
        """Attribution is required; endorsement is not granted. The notice says so
        explicitly, and says nothing that reads the other way."""
        self.assertIn("endors", self.lowered)
        for forbidden in FORBIDDEN_ENDORSEMENT_CLAIMS:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.lowered,
                                 "{0} implies IPTC endorsement".format(NOTICE_FILE))


class TestTheDistributionDeclaresTheApprovedLicense(unittest.TestCase):
    """The decision as the index, the installer and a consumer's tooling see it.

    Read off the built wheel's ``METADATA`` and off the installed ``dist-info``,
    not off ``pyproject.toml``: what a resolver reports and what an audit tool
    scans is the generated metadata, and a build hook could have produced
    something else.
    """

    def setUp(self):
        self.metadata = wheel_metadata(built().wheel)

    def test_the_metadata_declares_the_exact_aggregate_expression(self):
        self.assertIn("\nLicense-Expression: {0}\n".format(LICENSE_EXPRESSION),
                      "\n" + self.metadata)
        self.assertEqual(metadata_values(self.metadata, "License-Expression"),
                         [LICENSE_EXPRESSION])

    def test_the_metadata_version_supports_a_license_expression(self):
        """``License-Expression`` is PEP 639 and only defined from 2.4. A 2.3
        wheel carrying the field is metadata a strict consumer may reject."""
        self.assertEqual(metadata_values(self.metadata, "Metadata-Version"),
                         ["2.4"])

    def test_the_metadata_names_exactly_the_three_license_files_in_order(self):
        self.assertEqual(metadata_values(self.metadata, "License-File"),
                         list(LICENSE_FILES))

    def test_the_metadata_carries_no_legacy_license_classifier_or_field(self):
        """PEP 639 deprecates both. Two sources of truth for one decision is how
        an expression and a classifier come to disagree."""
        self.assertEqual(metadata_values(self.metadata, "License"), [])
        for line in self.metadata.splitlines():
            if line.startswith("Classifier: License ::"):
                self.fail("legacy license classifier: {0}".format(line))

    def test_pyproject_declares_the_expression_and_the_three_files(self):
        """The source side of the same claim, so a red test names the file to edit
        rather than only the artefact that came out wrong."""
        project = pyproject()["project"]
        self.assertEqual(project["license"], LICENSE_EXPRESSION)
        self.assertEqual(list(project["license-files"]), list(LICENSE_FILES))

    def test_the_installed_metadata_declares_the_same_license(self):
        venv_python = clean_install(sys.executable, "primary")
        distinfo = purelib(venv_python) / "{0}.dist-info".format(ARTIFACT_STEM)
        installed = (distinfo / "METADATA").read_text(encoding="utf-8")
        self.assertEqual(metadata_values(installed, "License-Expression"),
                         [LICENSE_EXPRESSION])
        self.assertEqual(metadata_values(installed, "License-File"),
                         list(LICENSE_FILES))

    def test_the_license_decision_did_not_add_a_runtime_dependency(self):
        """The zero-dependency contract is unrelated to licensing and must survive
        it. Stated here because this is the change that rewrote the metadata."""
        self.assertEqual(metadata_values(self.metadata, "Requires-Dist"), [])
        self.assertEqual(metadata_values(self.metadata, "Requires-Python"),
                         [">=3.9"])


class TestTheLicenseFilesShipInBothArtefacts(unittest.TestCase):
    """Metadata that names a license file the archive does not carry is an
    attribution promise nothing keeps.

    So the bytes are compared, in both distribution formats, against the
    checked-in files — the same standard the canonical runtime is held to.
    """

    def test_the_wheel_carries_exactly_the_declared_license_files(self):
        self.assertEqual(sorted(wheel_license_members(built().wheel)),
                         sorted(LICENSE_FILES))

    def test_every_license_file_in_the_wheel_is_byte_equal_to_its_source(self):
        shipped = wheel_license_members(built().wheel)
        for relative, blob in sorted(source_license_bytes().items()):
            with self.subTest(member=relative):
                self.assertIn(relative, shipped)
                self.assertEqual(shipped[relative], blob)

    def test_the_sdist_carries_the_license_files_byte_equal_to_their_source(self):
        payloads = tar_payloads(built().sdist)
        for relative, blob in sorted(source_license_bytes().items()):
            member = "{0}/{1}".format(ARTIFACT_STEM, relative)
            with self.subTest(member=member):
                self.assertIn(member, payloads)
                self.assertEqual(payloads[member], blob)

    def test_the_metadata_names_no_license_file_the_wheel_omits(self):
        """Both directions, off the generated metadata rather than off the
        constant: a fourth ``License-File`` added without the file is exactly the
        broken promise this class exists to catch."""
        declared = metadata_values(wheel_metadata(built().wheel), "License-File")
        shipped = wheel_license_members(built().wheel)
        self.assertEqual(sorted(declared), sorted(shipped))

    def test_no_license_file_lands_inside_the_import_namespace(self):
        """They are distribution metadata, not package data. A ``NOTICE-IPTC.md``
        inside ``machina_sports_canonical/`` would join the closed runtime member
        set and become something a consumer could import over."""
        for member in wheel_record(built().wheel):
            if not member.startswith(IMPORT_NAME + "/"):
                continue
            with self.subTest(member=member):
                self.assertNotIn("LICENSE", member.upper())
                self.assertNotIn("NOTICE", member.upper())

    def test_the_license_files_are_not_readable_through_the_installed_package(self):
        """The corollary, on the installed tree: the runtime member set is closed
        and unchanged, so nothing licensing added is importable."""
        venv_python = clean_install(sys.executable, "primary")
        self.assertEqual(sorted(installed_members(venv_python)),
                         sorted(expected_runtime_members()))


class TestThePackageReadmeStatesTheLicenseAndPointsAtTheNotice(unittest.TestCase):
    """The README is the package's front page on the index — `[project] readme`
    puts these bytes in the metadata a consumer reads before installing.

    It carries the aggregate expression and a pointer to the packaged notice, so
    the CC-BY-4.0 half of the expression is explicable without cloning this
    repository.
    """

    def setUp(self):
        self.text = package_readme_text()

    def test_the_readme_states_the_aggregate_expression(self):
        self.assertIn(LICENSE_EXPRESSION, self.text)

    def test_the_readme_points_at_the_packaged_notice(self):
        self.assertIn(NOTICE_FILE, self.text)

    def test_the_readme_names_both_license_files(self):
        for relative in (MIT_LICENSE_FILE, CC_BY_LICENSE_FILE):
            with self.subTest(relative=relative):
                self.assertIn(relative, self.text)

    def test_the_readme_attributes_the_upstream_work_without_claiming_endorsement(self):
        self.assertIn(UPSTREAM_WORK, self.text)
        self.assertIn(CC_BY_LICENSE_URL, self.text)
        lowered = self.text.lower()
        for forbidden in FORBIDDEN_ENDORSEMENT_CLAIMS:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)

    def test_the_readme_reaches_the_metadata_it_claims_to_describe(self):
        """Guard the pointer: the README is the declared readme, so these bytes
        really are the ``Description`` a consumer sees."""
        self.assertEqual(pyproject()["project"]["readme"],
                         "README-machina-sports-canonical.md")
        self.assertIn(NOTICE_FILE, wheel_metadata(built().wheel))


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

    def test_the_record_accounts_for_exactly_the_declared_license_files(self):
        """The closed set has to close over the license members too. They are the
        only thing licensing adds to the archive, and a RECORD that listed a fourth
        — or dropped one METADATA names — would be a distribution whose attribution
        no installer verifies."""
        licenses = sorted(entry[len(WHEEL_LICENSE_PREFIX):]
                          for entry in self.record
                          if entry.startswith(WHEEL_LICENSE_PREFIX))
        self.assertEqual(licenses, sorted(LICENSE_FILES))

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
        self.assertEqual(payload["version"], "machina-iptc-profile/1.2")
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
        self.installed = self.jobs.get(INSTALLED_CONFORMANCE_JOB, "")

    def test_a_dedicated_package_proof_job_exists_beside_the_validation_job(self):
        self.assertIn(VALIDATION_JOB, self.jobs)
        self.assertIn(PACKAGE_PROOF_JOB, self.jobs,
                      "no job runs the package proof on the declared "
                      "interpreters: {0}".format(sorted(self.jobs)))

    def test_a_dedicated_installed_conformance_job_exists(self):
        self.assertIn(INSTALLED_CONFORMANCE_JOB, self.jobs,
                      "no dedicated job proves the installed wheel's canonical "
                      "contracts: {0}".format(sorted(self.jobs)))

    def test_the_installed_conformance_job_is_python_3_11_without_a_matrix(self):
        self.assertIn('python-version: "3.11"', self.installed)
        self.assertEqual(matrix_python_versions(self.installed), [])

    def test_the_installed_conformance_job_uses_the_release_action_pins(self):
        uses = []
        for raw in self.installed.splitlines():
            stripped = raw.strip()
            if stripped.startswith("- "):
                stripped = stripped[2:]
            if stripped.startswith("uses:"):
                uses.append(stripped)
        self.assertEqual(uses, [CHECKOUT_ACTION, SETUP_PYTHON_ACTION])

    def test_the_installed_conformance_job_installs_only_pinned_inputs_and_runs_the_suite(self):
        commands = run_commands(self.installed)
        installs = [command for command in commands if "pip install" in command]
        self.assertEqual(installs, [
            "python -m pip install -r {0}".format(VALIDATOR_REQUIREMENTS),
            "python -m pip install -r {0}".format(BUILD_REQUIREMENTS),
        ])
        self.assertIn("python {0} -v".format(INSTALLED_CONFORMANCE_SUITE),
                      commands)

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
    - **It publishes only the approved license.** The owner decided
      ``MIT AND CC-BY-4.0`` with three named license files, so the preflight
      requires *that* expression and *all three* ``License-File`` entries. The
      earlier gate accepted the presence of either field, which would have admitted
      a wheel declaring any expression at all — including one that placed CC BY
      over the software, or MIT over the attribution-bearing assets. An upload
      under the wrong license cannot be taken back: PyPI does not free a version
      number.
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
        self.release = self.jobs.get(RELEASE_GITHUB_JOB, "")

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
        self.assertEqual(len(found), 7, found)
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
        self.assertEqual(RELEASE_TAG, "machina-sports-canonical-v0.2.0")

    def test_the_workflow_scopes_each_write_permission_to_the_job_that_needs_it(self):
        """``id-token: write`` on the workflow would hand the upload identity to
        every job in it, including the one that runs a build backend. Likewise,
        only the final job may write the GitHub Release."""
        self.assertIn("permissions:", self.header)
        self.assertIn("contents: read", self.header)
        self.assertNotIn("id-token", self.header)
        self.assertNotIn("id-token", self.build)
        self.assertNotIn("contents: write", self.build)
        self.assertIn("id-token: write", self.publish)
        self.assertNotIn("contents: write", self.publish)
        self.assertNotIn("id-token", self.release)
        self.assertIn("contents: write", self.release)
        self.assertEqual(self.text.count("contents: write"), 1)
        for extra in ("packages: write", "write-all"):
            with self.subTest(scope=extra):
                self.assertNotIn(extra, self.text)

    def test_a_third_job_creates_the_github_release_only_after_publish_succeeds(self):
        self.assertEqual(
            list(self.jobs),
            [RELEASE_BUILD_JOB, RELEASE_PUBLISH_JOB, RELEASE_GITHUB_JOB],
            "release automation must be the third job, after build and publish")
        self.assertIn("needs: {0}".format(RELEASE_PUBLISH_JOB), self.release)
        self.assertNotIn("if:", self.release,
                         "the default success condition must not be bypassed")

    def test_the_release_job_has_no_oidc_checkout_build_or_credential(self):
        self.assertTrue(self.release, "release job missing")
        self.assertNotIn("id-token", self.release)
        self.assertNotIn("actions/checkout@", self.release)
        self.assertNotIn(TRUSTED_PUBLISHER_ACTION, self.release)
        for command in run_commands(self.release):
            for marker in REBUILD_MARKERS:
                with self.subTest(command=command, marker=marker):
                    self.assertNotIn(marker, command)
        for marker in CREDENTIAL_MARKERS:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.release)

    def test_the_release_job_downloads_and_verifies_the_same_artifact(self):
        self.assertIn("uses: {0}".format(DOWNLOAD_ARTIFACT_ACTION), self.release)
        self.assertIn("name: {0}".format(RELEASE_ARTIFACT_NAME), self.release)
        checks = [command for command in run_commands(self.release)
                  if "sha256sum" in command and RELEASE_DIGEST_FILE in command]
        self.assertEqual(
            checks,
            ["cd dist && sha256sum --check --strict ../{0}".format(
                RELEASE_DIGEST_FILE)])
        self.assertLess(line_index(self.release, checks[0]),
                        line_index(self.release, GITHUB_RELEASE_ACTION))

    def test_the_release_job_attaches_exactly_the_built_distributions_and_digests(self):
        self.assertIn("uses: {0}".format(GITHUB_RELEASE_ACTION), self.release)
        self.assertIn("tag_name: ${{ github.ref_name }}", self.release)
        self.assertEqual(literal_block_lines(self.release, "files"),
                         list(GITHUB_RELEASE_ATTACHMENTS))
        self.assertIn("fail_on_unmatched_files: true", self.release)

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

    def test_the_publish_job_refuses_a_wheel_without_the_approved_license(self):
        gate = self.license_gate_command()
        self.assertIn("exit 1", gate)
        self.assertLess(line_index(self.publish, gate),
                        line_index(self.publish, TRUSTED_PUBLISHER_ACTION),
                        "a license gate after the upload is not a gate")

    def test_the_gate_requires_the_exact_expression_and_all_three_files(self):
        """Read off the command itself, so a gate that only looked for the *word*
        ``License-Expression`` could not satisfy the executed cases below by
        accident. Every value the owner approved is named in the step."""
        gate = self.license_gate_command()
        self.assertIn(LICENSE_EXPRESSION, gate)
        for relative in LICENSE_FILES:
            with self.subTest(relative=relative):
                self.assertIn(relative, gate)

    def test_the_license_gate_admits_the_wheel_this_repository_now_builds(self):
        """The owner decision, executed end to end: the wheel this commit produces
        carries the approved expression and the three approved files, so the
        preflight lets it through. Every rejection case below is measured against
        this one — a gate that always failed would satisfy them all and block every
        release for the wrong reason."""
        metadata = wheel_metadata(built().wheel)
        self.assertEqual(metadata_values(metadata, "License-Expression"),
                         [LICENSE_EXPRESSION])
        self.assertEqual(metadata_values(metadata, "License-File"),
                         list(LICENSE_FILES))
        result = self.run_gate(built().wheel)
        self.assertEqual(result.returncode, 0,
                         "the gate rejected the approved wheel:\n{0}{1}".format(
                             result.stdout, result.stderr))

    def test_the_license_gate_refuses_a_wheel_that_declares_no_license(self):
        """The state this repository was in before the decision. It must stay
        rejected: an upload under no license cannot be withdrawn."""
        result = self.run_gate(self.synthetic_wheel([]))
        self.assertNotEqual(result.returncode, 0,
                            "the gate let an unlicensed wheel through:\n{0}{1}"
                            .format(result.stdout, result.stderr))
        self.assertIn("BLOCKED", result.stdout + result.stderr)

    def test_the_license_gate_refuses_any_expression_but_the_approved_one(self):
        """The hole the old gate had. It accepted the mere presence of a license
        field, so each of these would have published: MIT alone drops the
        attribution obligation on the two IPTC-derived assets, CC-BY-4.0 alone
        places CC BY over the software, ``OR`` lets a consumer choose one, and a
        reordered conjunction is not the string the owner approved."""
        for wrong in ("MIT", "CC-BY-4.0", "MIT OR CC-BY-4.0",
                      "CC-BY-4.0 AND MIT", "Proprietary"):
            with self.subTest(expression=wrong):
                lines = ["License-Expression: {0}".format(wrong)]
                lines += ["License-File: {0}".format(relative)
                          for relative in LICENSE_FILES]
                result = self.run_gate(self.synthetic_wheel(lines))
                self.assertNotEqual(
                    result.returncode, 0,
                    "the gate admitted {0!r}:\n{1}{2}".format(
                        wrong, result.stdout, result.stderr))
                self.assertIn("BLOCKED", result.stdout + result.stderr)

    def test_the_license_gate_refuses_a_wheel_missing_any_one_license_file(self):
        """Three files, each dropped in turn. A wheel whose METADATA names the
        expression but not the notice would publish ``CC-BY-4.0`` with no
        attribution reachable from the artefact."""
        for dropped in LICENSE_FILES:
            with self.subTest(dropped=dropped):
                lines = ["License-Expression: {0}".format(LICENSE_EXPRESSION)]
                lines += ["License-File: {0}".format(relative)
                          for relative in LICENSE_FILES if relative != dropped]
                result = self.run_gate(self.synthetic_wheel(lines))
                self.assertNotEqual(
                    result.returncode, 0,
                    "the gate admitted a wheel without {0}:\n{1}{2}".format(
                        dropped, result.stdout, result.stderr))
                self.assertIn("BLOCKED", result.stdout + result.stderr)

    def test_the_license_gate_refuses_the_shape_the_old_gate_admitted(self):
        """Named as its own case because it is the regression: a single license
        field with an arbitrary value used to pass."""
        for field in LICENSE_METADATA_FIELDS:
            with self.subTest(field=field):
                result = self.run_gate(self.synthetic_wheel(
                    ["{0}: SYNTHETIC-FIXTURE".format(field)]))
                self.assertNotEqual(
                    result.returncode, 0,
                    "the gate still admits a bare {0}:\n{1}{2}".format(
                        field, result.stdout, result.stderr))

    def test_the_license_gate_refuses_a_duplicated_license_expression(self):
        """`License-Expression` is single-use in the metadata spec, and a
        presence-only matcher cannot see a second one.

        A wheel carrying the approved expression *and* a second one is a wheel
        whose license a consumer's tooling resolves by which line it happens to
        read first — and the second line is where a wrong license hides behind a
        right one. Both orders are exercised, because a matcher that stops at the
        first hit is fooled by exactly one of them.
        """
        for extra in (LICENSE_EXPRESSION, "Proprietary"):
            for first in (LICENSE_EXPRESSION, extra):
                second = extra if first == LICENSE_EXPRESSION else LICENSE_EXPRESSION
                with self.subTest(first=first, second=second):
                    lines = ["License-Expression: {0}".format(first),
                             "License-Expression: {0}".format(second)]
                    lines += ["License-File: {0}".format(relative)
                              for relative in LICENSE_FILES]
                    result = self.run_gate(self.synthetic_wheel(lines))
                    self.assertNotEqual(
                        result.returncode, 0,
                        "the gate admitted two License-Expression values "
                        "({0!r}, {1!r}):\n{2}{3}".format(
                            first, second, result.stdout, result.stderr))
                    self.assertIn("BLOCKED", result.stdout + result.stderr)

    def test_the_license_gate_refuses_a_license_file_the_owner_did_not_approve(self):
        """The approved set is closed. A fourth `License-File` is a fourth claim
        about what licenses this distribution — and the file it names ships in the
        wheel, so the extra entry is not cosmetic."""
        for unapproved in ("LICENSES/APACHE-2.0.txt", "LICENSE",
                           "LICENSES/CC-BY-NC-4.0.txt"):
            with self.subTest(unapproved=unapproved):
                lines = ["License-Expression: {0}".format(LICENSE_EXPRESSION)]
                lines += ["License-File: {0}".format(relative)
                          for relative in LICENSE_FILES]
                lines.append("License-File: {0}".format(unapproved))
                result = self.run_gate(self.synthetic_wheel(lines))
                self.assertNotEqual(
                    result.returncode, 0,
                    "the gate admitted an unapproved license file {0}:\n{1}{2}"
                    .format(unapproved, result.stdout, result.stderr))
                self.assertIn("BLOCKED", result.stdout + result.stderr)

    def test_the_license_gate_refuses_a_duplicated_license_file(self):
        """Each approved file, listed twice. A duplicate is how an entry survives
        a review that counted names rather than values, and a gate satisfied by
        "all three are present" cannot tell three from four."""
        for duplicated in LICENSE_FILES:
            with self.subTest(duplicated=duplicated):
                lines = ["License-Expression: {0}".format(LICENSE_EXPRESSION)]
                lines += ["License-File: {0}".format(relative)
                          for relative in LICENSE_FILES]
                lines.append("License-File: {0}".format(duplicated))
                result = self.run_gate(self.synthetic_wheel(lines))
                self.assertNotEqual(
                    result.returncode, 0,
                    "the gate admitted a duplicated {0}:\n{1}{2}".format(
                        duplicated, result.stdout, result.stderr))
                self.assertIn("BLOCKED", result.stdout + result.stderr)

    def test_the_license_gate_reads_metadata_as_metadata_not_as_text(self):
        """The gate must parse the METADATA headers, not scan the archive for
        strings.

        A wheel's `Description` is the README, verbatim, in the same file as the
        headers. This repository's README *names the approved expression and all
        three files* — so a line-scanner that did not stop at the header/body
        boundary would find every value it was looking for in prose and admit a
        wheel that declares nothing at all.
        """
        prose = "\n".join(
            ["License-Expression: {0}".format(LICENSE_EXPRESSION)]
            + ["License-File: {0}".format(relative)
               for relative in LICENSE_FILES])
        wheel = self.synthetic_wheel([], body=prose)
        result = self.run_gate(wheel)
        self.assertNotEqual(
            result.returncode, 0,
            "the gate read the description body as license metadata:\n{0}{1}"
            .format(result.stdout, result.stderr))
        self.assertIn("BLOCKED", result.stdout + result.stderr)

    def synthetic_wheel(self, metadata_lines, body: str = "") -> Path:
        """A wheel-shaped zip carrying only ``metadata_lines`` as license fields.

        Synthetic on purpose: the rejection cases have to be metadata this
        repository would never build, and rebuilding the real wheel with a wrong
        license to test the gate would mean producing an artefact that misstates
        the owner decision.

        ``body`` is the ``Description`` — the README, in a real wheel — placed
        after the blank line that ends the headers. It is a parameter so a
        rejection case can put license-shaped prose where a header scanner would
        wrongly find it.
        """
        staged = Path(tempfile.mkdtemp(prefix="iptc-license-fixture-"))
        self.addCleanup(shutil.rmtree, staged, ignore_errors=True)
        wheel = staged / built().wheel.name
        headers = "".join("{0}\n".format(line) for line in metadata_lines)
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr(
                "{0}.dist-info/METADATA".format(ARTIFACT_STEM),
                "Metadata-Version: 2.4\nName: {0}\nVersion: {1}\n{2}\n{3}".format(
                    DISTRIBUTION, VERSION, headers, body))
        return wheel

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
    """One of the two decisions this release needed is now made; the other is not.

    The owner has chosen ``MIT AND CC-BY-4.0`` with three named license files, so
    the license blocker is recorded as resolved rather than left standing as a
    blocker nobody can close. Everything else still holds: the ``pypi`` environment
    is not configured, the trusted publisher is not registered, the renewed digests
    have not been independently verified, and no human has approved publication.
    Marking the license decision done must not read as "the release is unblocked".

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

    def test_the_docs_record_the_owner_license_decision_as_resolved(self):
        """The decision, stated where a releaser reads it and in the same terms the
        workflow enforces: the exact expression, the three files it names, and the
        packaged notice that carries the attribution."""
        self.assertMentions("license", "owner", "resolved")
        self.assertIn(LICENSE_EXPRESSION, self.text)
        for relative in LICENSE_FILES:
            with self.subTest(relative=relative):
                self.assertIn(relative, self.text)
        for field in LICENSE_METADATA_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, self.text)

    def test_the_docs_record_the_upstream_attribution_and_the_mit_boundary(self):
        """A releaser reading only this document must be able to see what the
        CC-BY-4.0 half attributes and that it does not reach the software."""
        self.assertIn(UPSTREAM_WORK, self.text)
        self.assertIn(UPSTREAM_CREATOR, self.text)
        self.assertIn(NOTICE_FILE, self.text)
        self.assertMentions("mit", "attribution")

    def test_the_docs_record_the_prerequisites_as_closed_on_evidence(self):
        """The standing setup is in place, and the document says so with the
        evidence rather than on trust.

        Each prerequisite is closed by something a reader can re-check: a
        successful publish run on the 0.1.0 tag, at a named head commit. Naming
        the run is what separates "these are configured" from "somebody said
        these are configured", and it is the same standard the digest records
        below are held to.
        """
        for token in RELEASE_PREREQUISITE_EVIDENCE:
            with self.subTest(evidence=token):
                self.assertIn(token, self.text)

    def test_the_docs_do_not_state_the_false_release_absolutes(self):
        """The stale blockers, asserted gone.

        A document that says the environment does not exist, while the
        environment exists with a required reviewer, is not being careful — it is
        wrong, and being wrong in the safe-sounding direction is how a releaser
        learns to discount every other warning in the file.
        """
        for claim in FALSE_RELEASE_ABSOLUTES:
            with self.subTest(claim=claim):
                self.assertNotIn(claim, self.lowered)

    def test_the_docs_preserve_every_release_time_gate(self):
        """Closed prerequisites are not an open door.

        The per-release checks are untouched by any of this: a green run, a merge
        to the default branch, a tag on the exact merge commit, the runtime
        reviewer on the `pypi` environment, the digest and license gates, and the
        post-publish registry verification. Asserted individually, because
        "the gates still apply" without a list is a sentence a releaser can talk
        themselves past.
        """
        self.assertMentions(*RELEASE_TIME_GATE_PHRASES)

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

    def test_the_docs_require_verifying_an_actual_github_release_and_attachments(self):
        self.assertNotIn("release/run", self.lowered)
        self.assertMentions("GitHub Release", "exists", RELEASE_TAG,
                            "exactly three attachments")
        attachments = [name for name, _ in REVIEWED_RELEASE_DIGESTS]
        attachments.append(RELEASE_DIGEST_FILE)
        for attachment in attachments:
            with self.subTest(attachment=attachment):
                self.assertIn(attachment, self.text)
        self.assertMentions("sha256sum --check --strict")

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

    def test_the_docs_record_the_independent_verification_as_superseded(self):
        """The independent rebuild happened, and it rebuilt different bytes.

        `f46799c` predates the license metadata. Adding an expression, three
        ``License-File`` fields and three archive members changes both artefacts, so
        that evidence now describes a candidate this repository no longer builds.
        The document keeps it — a releaser is entitled to see that the method
        works and that the pre-license candidate was reproduced — but it must be
        labelled superseded and carry the digests it actually verified, or it reads
        as vouching for rows nobody has rebuilt.
        """
        self.assertIn(INDEPENDENT_VERIFICATION_COMMIT, self.text)
        self.assertMentions("independent", "git archive", "temporary trees",
                            "superseded")
        for version in INDEPENDENT_VERIFICATION_INTERPRETERS:
            with self.subTest(interpreter=version):
                self.assertIn(version, self.text)
        for distribution, version, _ in BUILD_REQUIREMENT_CLOSURE:
            with self.subTest(build_pin=distribution):
                self.assertIn("{0}=={1}".format(distribution, version),
                              self.text)
        for name, digest in SUPERSEDED_RELEASE_DIGESTS:
            with self.subTest(superseded=name):
                self.assertIn(digest, self.text)
        self.assertIn(RELEASE_SOURCE_DATE_EPOCH, self.text)
        self.assertIn(RELEASE_CHECKSUM_FILE, self.text)
        self.assertMentions("not release approval", "not a license decision")

    def test_the_docs_do_not_call_this_release_the_projects_first_upload(self):
        """`machina-sports-canonical-v0.1.0` is an annotated tag on `48d4168`,
        pushed to `origin`. Whatever the index state, this repository has already
        cut a release of this distribution, so 0.2.0 is not a first upload and the
        project is not a never-registered pending-publisher case.

        A releaser who reads "the project does not exist on the index yet" will
        try to add a *pending* publisher for a project that already converted, get
        an authentication failure at upload time with no helpful message, and have
        no idea which of the four matched values is wrong. The stale sentence
        costs a debugging session at precisely the worst moment.

        Nothing here relaxes a hold: all three remain, and the reviewer-gated
        environment and no-API-token rules are asserted by their own cases.
        """
        self.assertNotIn("does not exist on the index yet", self.lowered)
        self.assertNotIn("the first upload still cannot happen", self.lowered)
        self.assertMentions("0.1.0", "already")

    def test_the_docs_preserve_the_0_1_0_independent_verification_as_history(self):
        """The 0.1.0 rebuild happened and its record must survive intact.

        It was real evidence: a clean ``git archive`` export of an exact commit,
        rebuilt on both proven interpreters, reproducing the rows that release
        shipped. A later version bump does not unmake it, and deleting it would
        throw away the only demonstration in this repository that the method
        works end to end.

        It must keep **its own** artefact names and digests. Re-stamping a
        historical record with the current version's filenames is how a document
        comes to vouch for bytes nobody rebuilt — the exact failure the
        superseded-section rule already exists to prevent, one version later.
        """
        self.assertIn(RENEWED_VERIFICATION_COMMIT, self.text)
        self.assertMentions("independent", "git archive")
        for version in INDEPENDENT_VERIFICATION_INTERPRETERS:
            with self.subTest(interpreter=version):
                self.assertIn(version, self.text)
        for name, digest in HISTORICAL_RELEASE_DIGESTS:
            with self.subTest(artefact=name):
                self.assertIn(name, self.text)
                self.assertIn(digest, self.text)

    def test_the_docs_record_the_0_2_0_independent_verification_as_closed(self):
        """The 0.2.0 digest hold, closed on evidence rather than on assertion.

        The rows were rebuilt from a clean ``git archive`` export of an exact
        commit, in isolated trees, on both proven interpreters, and both
        reproduced what the checked-in authority holds. A releaser can only weigh
        that by seeing the same four things the 0.1.0 record gave them: which
        commit, which two interpreters, which epoch, and which digests came out.

        Every value is asserted against a named constant rather than against
        prose, so a record that verified *some other* bytes, or that names an
        interpreter nobody ran, is red.
        """
        self.assertMentions(*CLOSED_VERIFICATION_PHRASES)
        self.assertIn(VERIFIED_RELEASE_COMMIT, self.text)
        self.assertIn(RELEASE_SOURCE_DATE_EPOCH, self.text)
        for version in VERIFIED_RELEASE_INTERPRETERS:
            with self.subTest(interpreter=version):
                self.assertIn(version, self.text)
        for name, digest in REVIEWED_RELEASE_DIGESTS:
            with self.subTest(artefact=name):
                self.assertIn(name, self.text)
                self.assertIn(digest, self.text)

    def test_the_docs_no_longer_carry_the_open_candidate_claim(self):
        """The stale sentence, asserted gone.

        Recording the rebuild while leaving the claim that it never happened is
        not a half-finished edit — it is a document that contradicts itself about
        the one thing a releaser reads it for.
        """
        self.assertNotIn(OPEN_CANDIDATE_CLAIM, self.lowered)

    def test_the_closed_verification_does_not_read_as_release_approval(self):
        """The failure mode a ✅ invites. Closing the digest hold says the bytes
        are reproducible; it says nothing about whether this particular upload
        may proceed, and every release-time gate is untouched by it."""
        self.assertMentions(*VERIFICATION_IS_NOT_APPROVAL_PHRASES)
        self.assertMentions(*RELEASE_TIME_GATE_PHRASES)

    def test_the_verified_interpreters_are_not_confused_with_the_0_1_0_ones(self):
        """Guard the guard. The two records ran on different 3.9 patch versions,
        so one shared tuple would make whichever was edited last silently vouch
        for a run that never happened."""
        self.assertNotEqual(VERIFIED_RELEASE_INTERPRETERS,
                            INDEPENDENT_VERIFICATION_INTERPRETERS)
        for version in INDEPENDENT_VERIFICATION_INTERPRETERS:
            with self.subTest(historical=version):
                self.assertIn(version, self.text)

    def test_the_docs_record_the_release_metadata_fixed_point(self):
        """Why the release metadata is self-referential, and which values resolve
        it.

        ``package-receipt.json`` ships inside the wheel and records the source
        commit, and ``SOURCE_DATE_EPOCH`` is that commit's committer timestamp —
        so recording either changes the artefacts whose digests are being
        recorded. A releaser who is not told this will either fabricate an
        identifier or conclude the release is impossible, and both of those end
        with bytes nobody can reproduce.

        The exact commit and epoch are asserted in the prose, not only in the
        JSON: reconstructing a build from the document alone has to be possible,
        and the two values it depends on are the two a reader cannot guess.
        """
        self.assertMentions(*FIXED_POINT_SEQUENCE_PHRASES)
        self.assertIn(RELEASE_SOURCE_DATE_EPOCH, self.text)
        self.assertIn(FIXED_POINT_COMMIT, self.text)

    def test_the_pinned_source_commit_is_the_one_the_epoch_belongs_to(self):
        """The receipt, the manifest and the release document must name one
        commit. Two of them agreeing while the third drifts is how a build gets an
        epoch belonging to some other tree — reproducible, and reproducibly
        wrong."""
        receipt = json.loads(
            (CANONICAL_ROOT / "package-receipt.json").read_text(encoding="utf-8"))
        manifest = json.loads(
            (REPO_ROOT / "tools/iptc/vendored-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["source_commit"], FIXED_POINT_COMMIT)
        self.assertEqual(manifest["source_commit"], FIXED_POINT_COMMIT)
        self.assertEqual(CANONICAL_SOURCE_COMMIT, FIXED_POINT_COMMIT)

    def test_the_docs_no_longer_claim_the_renewed_digests_are_unverified(self):
        """The stale sentence, asserted gone.

        Recording the rebuild while leaving the claim that it never happened is
        not a half-finished edit — it is a document that contradicts itself about
        the one thing a releaser reads it for.
        """
        self.assertNotIn(CLOSED_RELEASE_HOLD, self.lowered)

    def test_no_closed_item_is_still_written_as_a_blocker(self):
        """Guard the guard. Every hold this document has ever carried is now
        closed, so none of their sentences may survive anywhere in it — including
        the digest hold closed one version earlier. A file that records a closure
        in one section and restates it as a blocker in another teaches a releaser
        to discount both."""
        self.assertNotIn(CLOSED_RELEASE_HOLD, self.lowered)
        for claim in FALSE_RELEASE_ABSOLUTES:
            with self.subTest(claim=claim):
                self.assertNotIn(claim, self.lowered)

    def test_the_verified_digests_are_the_ones_the_authority_holds(self):
        """The rebuild is only evidence about this release if the rows it
        reproduced are the rows every automated comparison diffs against. Read off
        the checked-in authority rather than off the prose, so a document that
        recorded a verification of some other bytes is red."""
        authority = RELEASE_CHECKSUM_PATH.read_text(encoding="utf-8")
        for name, digest in REVIEWED_RELEASE_DIGESTS:
            with self.subTest(artefact=name):
                self.assertIn("{0}  {1}".format(digest, name), authority)

    def test_the_resolved_digest_gate_does_not_authorize_a_release(self):
        """Closing a hold is not permission. The document has to keep saying so in
        the same breath, because "independently verified" is the phrase most
        likely to be read as "ready to publish".

        Asserted as the gates that remain rather than as the word "BLOCKED",
        which described this document only while the standing prerequisites were
        open. Keying on that word made the check fail the moment they closed —
        measuring the banner instead of the safeguard.
        """
        self.assertMentions("do not publish", "not release approval")
        self.assertMentions(*RELEASE_TIME_GATE_PHRASES)

    def test_the_docs_do_not_present_the_superseded_digests_as_current(self):
        """Two digest pairs in one document is a reading hazard. The reviewed file
        is named as the authority, and the superseded rows must not be the ones
        `docs/iptc/machina-sports-canonical-0.2.0.sha256` is said to hold."""
        current = {digest for _, digest in REVIEWED_RELEASE_DIGESTS}
        stale = {digest for _, digest in SUPERSEDED_RELEASE_DIGESTS}
        self.assertEqual(current & stale, set(),
                         "the renewed digests were never re-recorded")
        for digest in stale:
            with self.subTest(digest=digest):
                self.assertNotIn(digest, RELEASE_CHECKSUM_PATH.read_text(
                    encoding="utf-8"))

    def test_the_docs_record_the_reproducible_build_epoch(self):
        """The releaser has to be able to rebuild the reviewed bytes locally, and
        that is only possible with the epoch the release job used."""
        self.assertIn("SOURCE_DATE_EPOCH", self.text)
        self.assertIn(RELEASE_SOURCE_DATE_EPOCH, self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
