"""The authoritative vendored-runtime manifest (PR 2, task A17).

Run from the repository root:

    python3 tests/test_iptc_vendored_manifest.py -v

Run the file directly, for the same reason as the other IPTC suites: ``tests/``
is a namespace directory with no ``__init__.py``, so ``-m unittest
tests.<module>`` can be shadowed by an installed distribution that ships a
top-level regular ``tests`` package.

**Which repository is authoritative, and why it is this one.**
``machina-sports/sports-skills`` ships a byte-exact copy of
``tools/iptc/canonical`` inside its own package and records what it copied in
``src/sports_skills/canonical/_vendored/VENDORED.json``. That file is the
*consumer's* receipt: it says what sports-skills currently holds. It cannot say
what sports-skills *should* hold, because it is written by whoever last ran the
sync — and a receipt that is also the specification can never be wrong. At the
time this manifest was written, that receipt was already two files stale
(``observation.py`` and ``serialize.py`` had moved on here), and nothing on either
side reported it.

So the specification lives here, beside the bytes it describes, and
``tools/iptc/vendored-manifest.json`` is it. It is deliberately in the consumer's
own schema, key for key and in the consumer's key order, so the next sync is a
copy rather than a translation: whoever re-vendors can move these bytes into
``VENDORED.json`` unchanged and the two repositories then agree by construction.
``test_the_manifest_is_bytes_the_consumer_can_copy_without_editing`` is what keeps
that property from quietly decaying.

What this suite holds, beyond "the file exists":

- **The set is exact.** Nine files, no more and no fewer. A tenth vendorable
  module that nobody added to the manifest fails here rather than arriving in
  sports-skills as an untracked file.
- **Every hash is the file on disk.** This is the whole point: a drifted runtime
  byte turns this suite red in the repository that owns the byte, at the commit
  that changed it, instead of surfacing as a mystery in a consumer months later.
- **Nothing under the vendoring root is unaccounted for.** Every file is either
  manifested or named as a deliberate exclusion with a reason.
- **The vendoring constraints are checked, not documented.** ``canonical/``'s
  docstring promises Python 3.9 syntax, standard library only, and no ``tools.*``
  import. sports-skills is a published zero-dependency 3.9+ package, so each of
  those promises is load-bearing for a consumer this repository's CI never runs.
- **The two shared-context copies are one file.** The serializer input that ships
  with the templates and the copy that crosses the vendoring boundary are compared
  byte-for-byte, not assumed to match.
- **The versions are read from the runtime, not retyped.** A manifest that
  restates a profile version can disagree with the module that emits it.

**This task changes no canonical runtime byte.** It records the bytes that are
already here at ``fd787c7``. If a test in this file fails on a later commit, the
answer is to update the manifest and re-sync the consumer — never to loosen the
assertion.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.iptc import canonical  # noqa: E402
from tools.iptc import reference  # noqa: E402

MANIFEST_PATH = REPO_ROOT / "tools/iptc/vendored-manifest.json"

#: The vendoring root. Every path in the manifest is relative to it.
VENDOR_ROOT = REPO_ROOT / "tools/iptc/canonical"

#: The authoritative copy of the shared JSON-LD context: it is a serializer
#: input, so it ships with the templates rather than with the harness.
MAPPINGS_CONTEXT = (REPO_ROOT / "agent-templates/iptc-mappings/contexts"
                    / "iptc-sport-schema-1.1.context.jsonld")

#: The complete runtime set sports-skills ships, spelled out here rather than
#: globbed. A glob would silently vendor whatever appeared next; this list makes
#: adding a file to the published package an explicit, reviewable act.
RUNTIME_MANIFEST_PATH = (VENDOR_ROOT / "data"
                         / "trusted_loader_manifest_v1.json")
_RUNTIME_MANIFEST = json.loads(RUNTIME_MANIFEST_PATH.read_text(encoding="utf-8"))
VENDORED_FILES = tuple(sorted(
    [item["relative_path"] for item in _RUNTIME_MANIFEST["runtime_files"]]
    + [item["relative_path"] for item in _RUNTIME_MANIFEST["required_data_files"]]
    + ["data/trusted_loader_manifest_v1.json"]
))

#: Files under the vendoring root that are deliberately **not** vendored, and the
#: reason each one stays behind. Recorded so the "nothing is unaccounted for"
#: test can be exact: an exclusion with no reason is indistinguishable from a
#: file somebody forgot.
NOT_VENDORED_FILES = {
    # A generator, not runtime: it regenerates official-property-names.json from
    # the pinned upstream ontologies, which only exist in this repository.
    # ``canonical/__init__.py`` names it as the one deliberate exception.
    "export_official_terms.py",
    # Package metadata for the `machina-sports-canonical` distribution, not
    # runtime and not part of the contract sports-skills vendors. It ships in the
    # wheel and it *restates* this manifest's nine-file receipt, so vendoring it
    # would put a second copy of these hashes inside the consumer — a receipt
    # describing a receipt, which is exactly the "the record is also the
    # specification" failure this suite's docstring exists to prevent. The core
    # manifest stays nine files; `tests/test_iptc_canonical_package.py` asserts
    # the shipped receipt equals it key for key and hash for hash.
    "package-receipt.json",
}

#: Subtrees under the vendoring root that are deliberately not vendored. A prefix
#: rather than a file list because ``tests/test_iptc_sports_skills_reference_
#: contract.py`` already pins the adapter package's contents exhaustively, and two
#: exhaustive inventories of one directory drift the first time either is edited.
NOT_VENDORED_PREFIXES = ()

#: The consumer's key order, which is also this manifest's key order. Pinned so
#: the bytes stay copy-pasteable into ``VENDORED.json`` rather than merely
#: equivalent to it.
CONSUMER_KEY_ORDER = (
    "consumer",
    "source_repository",
    "source_path",
    "source_commit",
    "profile",
    "schema_version",
    "machina_schema_version",
    "upstream_pin",
    "files",
)

#: The commit whose canonical bytes this manifest pins. A17 records the runtime
#: as it stands and changes none of it.
SOURCE_COMMIT = "ca275c65b3ad2e830ecf755d41c6ff95533c2040"


def manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vendored_modules():
    """The manifested ``.py`` files, as (name, parsed module) pairs."""
    for name in VENDORED_FILES:
        if name.endswith(".py"):
            source = (VENDOR_ROOT / name).read_text(encoding="utf-8")
            yield name, ast.parse(source, filename=name)


def parses_on_python_39(source: str) -> bool:
    """Whether ``source`` is syntax CPython 3.9 accepts.

    ``compile()`` under the interpreter running these tests would accept 3.12
    syntax, so it answers the wrong question. ``ast.parse`` with
    ``feature_version`` answers the one that matters for a package whose floor is
    3.9.
    """
    try:
        ast.parse(source, feature_version=(3, 9))
    except SyntaxError:
        return False
    return True


def absolute_import_roots(tree: ast.Module):
    """The top-level package each absolute import in ``tree`` reaches for."""
    roots = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            roots.append((node.module or "").split(".")[0])
    return roots


class TestTheManifestPinsTheWholeRuntimeSet(unittest.TestCase):
    """Exact set equality, in both directions."""

    def setUp(self):
        self.files = manifest()["files"]

    def test_the_manifest_pins_exactly_the_files_sports_skills_ships(self):
        self.assertEqual(sorted(self.files), sorted(VENDORED_FILES))

    def test_every_manifested_file_exists_under_the_vendoring_root(self):
        for name in sorted(self.files):
            with self.subTest(name=name):
                self.assertTrue((VENDOR_ROOT / name).is_file(),
                                "manifested file is missing: {0}".format(name))

    def test_no_file_under_the_vendoring_root_is_unmanifested(self):
        """The direction that catches growth.

        A new vendorable module under ``canonical/`` is a change to a published
        package's contents. Left to review it is invisible; here it is a red test
        with two honest fixes — manifest it, or name it as an exclusion.
        """
        unaccounted = []
        for path in sorted(VENDOR_ROOT.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(VENDOR_ROOT).as_posix()
            if relative in self.files or relative in NOT_VENDORED_FILES:
                continue
            if relative.startswith(NOT_VENDORED_PREFIXES):
                continue
            unaccounted.append(relative)
        self.assertEqual(unaccounted, [])

    def test_each_deliberate_exclusion_is_still_a_real_file(self):
        """An exclusion for a file that no longer exists is stale reasoning that
        would silently absorb a future file of the same name."""
        for name in sorted(NOT_VENDORED_FILES):
            with self.subTest(name=name):
                self.assertTrue((VENDOR_ROOT / name).is_file())
        for prefix in NOT_VENDORED_PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertTrue((VENDOR_ROOT / prefix.rstrip("/")).is_dir())

    def test_nothing_excluded_is_also_manifested(self):
        for name in sorted(self.files):
            with self.subTest(name=name):
                self.assertNotIn(name, NOT_VENDORED_FILES)
                self.assertFalse(name.startswith(NOT_VENDORED_PREFIXES))


class TestEveryHashIsTheFileOnDisk(unittest.TestCase):
    """The load-bearing assertion of this task.

    A drifted runtime byte has to fail in the repository that owns the byte, at
    the commit that changed it. The alternative is what A17 was written to end: a
    consumer holding a two-file-stale copy with nothing on either side reporting
    it.
    """

    def setUp(self):
        self.files = manifest()["files"]

    def test_every_recorded_hash_is_the_sha256_of_the_checked_in_file(self):
        for name, recorded in sorted(self.files.items()):
            with self.subTest(name=name):
                self.assertEqual(recorded, sha256(VENDOR_ROOT / name))

    def test_every_hash_is_lowercase_hex_sha256(self):
        for name, recorded in sorted(self.files.items()):
            with self.subTest(name=name):
                self.assertRegex(recorded, r"^[0-9a-f]{64}$")

    def test_the_hashes_are_distinct(self):
        """Nine files, nine hashes. A repeated hash means a copy-paste, and a
        copy-pasted hash pins the wrong file while looking correct."""
        self.assertEqual(len(set(self.files.values())), len(self.files))

    def test_a_changed_byte_would_be_caught(self):
        """Guard the guard. The comparison above is only a gate if a one-byte
        difference actually breaks it, so the failure is demonstrated rather than
        trusted — without touching the checked-in file."""
        original = (VENDOR_ROOT / "serialize.py").read_bytes()
        mutated = hashlib.sha256(original + b"\n").hexdigest()
        self.assertNotEqual(mutated, self.files["serialize.py"])


class TestTheVendoringConstraintsHold(unittest.TestCase):
    """sports-skills is a published, zero-dependency, Python 3.9+ package.

    Its CI runs in a repository this one cannot see, so every one of these
    promises has to be checked here or it is checked nowhere until an install
    fails for a user.
    """

    def test_every_vendored_module_parses_as_python_3_9(self):
        for name, _ in vendored_modules():
            with self.subTest(name=name):
                self.assertTrue(
                    parses_on_python_39(
                        (VENDOR_ROOT / name).read_text(encoding="utf-8")),
                    "{0} uses syntax Python 3.9 rejects".format(name))

    def test_the_python_39_check_rejects_newer_syntax(self):
        """Guard the guard: ``ast.parse`` without ``feature_version`` would accept
        every one of these under the 3.12 interpreter CI runs."""
        for newer in ("match x:\n    case 1:\n        pass\n",
                      "def f(*, x): return (y := x)\nclass C:\n"
                      "    def m(self) -> Self: ...\n" "type Alias = int\n"):
            with self.subTest(snippet=newer.splitlines()[0]):
                self.assertFalse(parses_on_python_39(newer))
        self.assertTrue(parses_on_python_39("import json\nx: int = 1\n"))

    def test_no_vendored_module_imports_tools(self):
        """The boundary, stated as the thing it forbids. ``tools`` does not exist
        inside sports-skills, so one such import is an ImportError on install."""
        for name, tree in vendored_modules():
            with self.subTest(name=name):
                self.assertNotIn("tools", absolute_import_roots(tree))

    def test_every_absolute_import_is_standard_library(self):
        """Checked against the interpreter's own module list rather than a
        hand-kept allowlist, which would drift into permitting a third-party
        package the day somebody added one to this repository's requirements."""
        for name, tree in vendored_modules():
            for root in absolute_import_roots(tree):
                with self.subTest(name=name, imports=root):
                    self.assertIn(root, sys.stdlib_module_names)

    def test_every_relative_import_resolves_inside_the_vendored_set(self):
        """A relative import reaching a module that is not vendored would resolve
        here and fail there, which is the worst of the two outcomes."""
        for name, tree in vendored_modules():
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.level:
                    continue
                target = "__init__.py" if not node.module \
                    else "{0}.py".format(node.module.split(".")[0])
                with self.subTest(name=name, imports=target):
                    self.assertIn(target, VENDORED_FILES)

    def test_no_vendored_module_reaches_into_a_non_vendored_sibling(self):
        """The exclusions are only safe if nothing vendored depends on them. This
        is what lets ``adapters/`` be excluded as a whole subtree."""
        excluded = {name[: -len(".py")] for name in NOT_VENDORED_FILES}
        excluded |= {prefix.rstrip("/") for prefix in NOT_VENDORED_PREFIXES}
        for name, tree in vendored_modules():
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.level:
                    continue
                reached = {node.module.split(".")[0]} if node.module else set()
                reached |= {alias.name for alias in node.names}
                with self.subTest(name=name):
                    self.assertEqual(sorted(reached & excluded), [])

    def test_a_module_that_annotates_defers_its_annotations(self):
        """``from __future__ import annotations`` is what makes a modern
        annotation legal on 3.9. A module that annotates without it would parse
        and then raise at import time on the floor version."""
        for name, tree in vendored_modules():
            annotates = any(isinstance(node, (ast.AnnAssign, ast.arg))
                            and getattr(node, "annotation", None) is not None
                            for node in ast.walk(tree))
            annotates = annotates or any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.returns is not None for node in ast.walk(tree))
            if not annotates:
                continue
            deferred = any(
                isinstance(node, ast.ImportFrom) and node.module == "__future__"
                and any(a.name == "annotations" for a in node.names)
                for node in tree.body)
            with self.subTest(name=name):
                self.assertTrue(deferred,
                                "{0} annotates without deferring".format(name))

    def test_every_manifested_json_file_is_parseable_json(self):
        for name in VENDORED_FILES:
            if not name.endswith(".json"):
                continue
            with self.subTest(name=name):
                json.loads((VENDOR_ROOT / name).read_text(encoding="utf-8"))


class TestTheSharedContextIsOneFile(unittest.TestCase):
    """Two copies compared, not assumed equal.

    The context that ships with the templates is the serializer's input; the copy
    under ``canonical/`` is the one that crosses the vendoring boundary. If they
    drift, a document serialized inside sports-skills expands its terms
    differently from the same document serialized here, and every cross-repository
    byte comparison becomes a coin toss.
    """

    def test_the_two_copies_are_byte_identical(self):
        self.assertEqual((VENDOR_ROOT / "shared-context.json").read_bytes(),
                         MAPPINGS_CONTEXT.read_bytes())

    def test_the_manifest_hash_covers_both_copies(self):
        self.assertEqual(manifest()["files"]["shared-context.json"],
                         sha256(MAPPINGS_CONTEXT))

    def test_the_context_declares_no_remote_reference(self):
        """The harness refuses a document that would make the JSON-LD processor
        fetch anything. The vendored context is the one input that could smuggle a
        fetch past that rule, and sports-skills runs it with no harness at all."""
        blob = (VENDOR_ROOT / "shared-context.json").read_text(encoding="utf-8")
        document = json.loads(blob)
        self.assertNotIn("@import", blob)
        self.assertIsInstance(document["@context"], dict)


class TestTheRecordedVersionsComeFromTheRuntime(unittest.TestCase):
    """A manifest that retypes a version can disagree with the module emitting
    it, and the manifest is what a consumer reads first."""

    def setUp(self):
        self.manifest = manifest()

    def test_the_profile_is_the_one_the_runtime_emits(self):
        self.assertEqual(self.manifest["profile"],
                         canonical.SUCCESSOR_PROFILE_VERSION)

    def test_the_observation_and_envelope_versions_are_the_runtime_constants(self):
        self.assertEqual(self.manifest["schema_version"],
                         canonical.SUCCESSOR_SCHEMA_VERSION)
        self.assertEqual(self.manifest["machina_schema_version"],
                         canonical.SUCCESSOR_MACHINA_SCHEMA_VERSION)

    def test_the_upstream_pin_agrees_with_the_runtime_and_the_harness(self):
        """Three copies of one pin — the vendored constants, the harness reference
        module, and this manifest. The vendoring boundary forces the first two to
        be separate; nothing forces them to agree except this."""
        pin = self.manifest["upstream_pin"]
        self.assertEqual(pin["repository"], canonical.UPSTREAM_REPOSITORY)
        self.assertEqual(pin["commit"], canonical.UPSTREAM_COMMIT)
        self.assertEqual(pin["target_version"], canonical.UPSTREAM_TARGET_VERSION)
        self.assertEqual(pin["commit"], reference.UPSTREAM_COMMIT)
        self.assertEqual(pin["target_version"], reference.TARGET_VERSION)

    def test_the_pin_records_a_commit_and_invents_no_version_tag(self):
        """Upstream published no 1.1 tag. A tag here would be a citation to
        something that does not exist."""
        pin = self.manifest["upstream_pin"]
        self.assertRegex(pin["commit"], r"^[0-9a-f]{40}$")
        self.assertNotIn("v1.1", json.dumps(pin))


class TestTheManifestNamesItsSubjectAndItsSource(unittest.TestCase):
    """Who ships these bytes, from where, at which commit."""

    def setUp(self):
        self.manifest = manifest()

    def test_the_consumer_and_the_source_repository_are_named(self):
        self.assertEqual(self.manifest["consumer"],
                         "machina-sports/sports-skills")
        self.assertEqual(self.manifest["source_repository"],
                         "machina-sports/machina-templates")

    def test_the_source_path_is_the_vendoring_root(self):
        self.assertEqual(self.manifest["source_path"],
                         str(VENDOR_ROOT.relative_to(REPO_ROOT).as_posix()))

    def test_the_source_commit_is_the_commit_this_task_pins(self):
        self.assertEqual(self.manifest["source_commit"], SOURCE_COMMIT)

    def test_the_source_commit_is_a_full_reviewed_commit(self):
        self.assertRegex(self.manifest["source_commit"], r"^[0-9a-f]{40}$")


class TestTheManifestIsCopyableIntoTheConsumer(unittest.TestCase):
    """The property that makes the next sync a copy instead of a translation.

    sports-skills' ``VENDORED.json`` has these keys, in this order, with these
    types. Being merely *equivalent* is not enough: a reordered or extra key means
    whoever re-vendors has to hand-edit, and a hand-edit is where the two
    repositories start to disagree again.
    """

    def setUp(self):
        self.manifest = manifest()
        self.blob = MANIFEST_PATH.read_text(encoding="utf-8")

    def test_the_key_set_and_order_are_the_consumer_manifest_shape(self):
        self.assertEqual(tuple(self.manifest), CONSUMER_KEY_ORDER)

    def test_the_upstream_pin_block_has_the_consumer_key_order(self):
        self.assertEqual(tuple(self.manifest["upstream_pin"]),
                         ("repository", "commit", "target_version"))

    def test_the_file_table_is_sorted_so_a_diff_reads(self):
        """Insertion-ordered hashes make a one-file change look like a rewrite."""
        self.assertEqual(list(self.manifest["files"]),
                         sorted(self.manifest["files"]))

    def test_every_value_is_a_string_except_the_two_nested_objects(self):
        for key, value in self.manifest.items():
            with self.subTest(key=key):
                expected = dict if key in ("upstream_pin", "files") else str
                self.assertIsInstance(value, expected)

    def test_the_manifest_is_bytes_the_consumer_can_copy_without_editing(self):
        """Serialized exactly as the consumer's file is: two-space indent, keys in
        their recorded order, one trailing newline."""
        self.assertEqual(
            self.blob,
            json.dumps(self.manifest, indent=2, ensure_ascii=False) + "\n")

    def test_no_field_carries_a_local_path_or_a_credential(self):
        """These bytes are published in a second repository. A developer's home
        directory or a token would travel with them."""
        for marker in ("/Users/", "/home/", "://github.com/machina-sports",
                       "token", "secret", "api_key", "Authorization"):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.blob)


if __name__ == "__main__":
    unittest.main(verbosity=2)
