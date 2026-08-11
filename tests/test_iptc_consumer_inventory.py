"""Coupling detection in the consumer inventory (PR 3-A, tasks 1 and 2).

Task 1 is the scan (everything up to :class:`TestTheInventoryExposesCouplings`).
Task 2 is the review ledger it feeds — ``docs/iptc/consumer-review.json``, which
has to account for every dependency the generated inventory records; see
:class:`ReviewLedgerTestCase` onwards.

Run from the repository root:

    python3 -m pytest tests/test_iptc_consumer_inventory.py -q
    python3 tests/test_iptc_consumer_inventory.py -v

Run the file directly, for the same reason as the other IPTC suites: ``tests/``
is a namespace directory with no ``__init__.py``, so ``-m unittest
tests.<module>`` can be shadowed by an installed distribution that ships a
top-level regular ``tests`` package.

**The hole this closes.** ``build_consumers`` finds a consumer by matching known
IPTC *field paths* and *payload state keys* as substrings. That misses two ways a
consumer can be welded to the persisted document, both of which the PR 3 seam has
to preserve:

1. **document-name coupling** — a literal document name such as ``worldcup:event``
   in a save, load or query position. Rename the document and every one of these
   silently reads nothing. The current scan never looks at document names.
2. **storage-predicate coupling** — a filter, sorter or query path such as
   ``value.schema:startDate`` or ``value.sport:status``. These bind the consumer
   to the *storage* shape rather than to the response shape, so a projection that
   only supplies the field nested under a canonical envelope breaks them while
   every field-path check still passes.

Both are evidence-bearing: a finding nobody can locate is a finding nobody can
act on, so each records file, line, category, the matched literal or path, and
the source line.

**Why the matchers are narrow, and why that is the point.** ``worldcup:event``
and ``sport:status`` both appear in ordinary prose and in commented-out YAML all
over this repository — docstrings, ``description:`` fields, disabled tasks. A
substring-anywhere matcher would report those, and an inventory that cries wolf
is an inventory whose findings get skimmed. So detection keys on *position*: a
document-name literal is only a finding under a document-name key, and a storage
predicate is only a finding on a line that is neither a comment nor part of a
``description:`` scalar. Several tests below exist purely to hold that line.

The ``description:`` exclusion was **missing** from the first version of this
suite, and the resulting false positive
(``connectors/sportradar-mlb/sync-results.yml:7``) survived review — see
:class:`TestDescriptionProseIsNotAStoragePredicate`. Anchoring on ``value.`` was
assumed to be enough to keep the matcher off prose. It is not, because a
description's job is to name the very path it is describing.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.iptc.inventory import (  # noqa: E402
    COUPLING_DOCUMENT_NAME,
    COUPLING_STORAGE_PREDICATE,
    SCAN_ROOTS,
    build_inventory,
    scan_couplings,
)

#: The consumer tree PR 3-D substitutes providers underneath.
WCI_ROOT = "agent-templates/world-cup-intelligence"

#: A document task that loads by literal document name — the shape used across
#: the WCI workflows, minus the quoting the workflow engine happens to require.
DOCUMENT_NAME_SNIPPET = """\
workflow:
  tasks:
    - type: document
      name: load-events
      description: Load cached worldcup:event docs from same-pod document state.
      config:
        action: search
      filters:
        name: worldcup:event
"""

#: A document task that filters and sorts on the persisted document shape.
STORAGE_PREDICATE_SNIPPET = """\
workflow:
  tasks:
    - type: document
      name: load-upcoming
      config:
        action: search
        search-sorters: ["value.schema:startDate", 1]
      filters:
        value.schema:startDate: "{'$gt': 'now'}"
        value.sport:status: "{'$in': ['not_started']}"
"""


#: A multi-line ``description:`` scalar that names storage paths in prose, plus a
#: real filter after the scalar ends. Modelled on
#: ``connectors/sportradar-mlb/sync-results.yml``, where the description explains
#: which storage path a *downstream* workflow reads. Explaining a path is not
#: evaluating one, so nothing in the scalar is a coupling; the ``filters:`` key
#: below it is.
DESCRIPTION_PROSE_SNIPPET = """\
workflow:
  name: sportradar-mlb-sync-results
  description: 'Companion to sportradar-mlb-sync-games. The season schedule.json
    carries NO runs, so this merges the score onto the existing docs.

    Without this, extract-team-stats has nothing to read — it needs
    value.sport:score.sport:homeScore / sport:awayScore — so no team stats.

    Merge-not-replace: only value.sport:matchStatus is written, so version_control
    survives.'
  tasks:
  - type: document
    name: load-upcoming
    description: |
      A block scalar names value.sport:competition without evaluating it either.
    filters:
      value.sport:status: "{'$in': ['not_started']}"
"""


class CouplingScanTestCase(unittest.TestCase):
    """Scans run against a throwaway tree, never against this repository, except
    where a test says it is checking the real thing."""

    def scan_snippet(self, filename: str, text: str) -> list:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        (directory / filename).write_text(text, encoding="utf-8")
        return scan_couplings(str(directory))

    def of_category(self, findings, category) -> list:
        return [f for f in findings if f["category"] == category]


class TestDocumentNameCoupling(CouplingScanTestCase):

    def test_detects_document_name_coupling(self):
        """A literal document name in a load position, reported as such."""
        findings = self.scan_snippet("consumer.yml", DOCUMENT_NAME_SNIPPET)
        document_name = self.of_category(findings, COUPLING_DOCUMENT_NAME)
        self.assertEqual([f["literal"] for f in document_name], ["worldcup:event"])
        self.assertEqual(document_name[0]["category"], "document-name")

    def test_the_task_name_is_not_mistaken_for_a_document_name(self):
        """``name: load-events`` is a task name. Reporting it would mean the
        matcher is keying on the key alone and not on the value being a
        prefixed literal at all."""
        findings = self.scan_snippet("consumer.yml", DOCUMENT_NAME_SNIPPET)
        self.assertNotIn(
            "load-events",
            [f.get("literal") for f in self.of_category(findings,
                                                        COUPLING_DOCUMENT_NAME)])

    def test_a_prose_mention_of_a_document_name_is_not_a_finding(self):
        """``worldcup:event`` appears in the snippet's ``description:`` too, and
        in docstrings throughout the real tree. A matcher that reports prose is a
        false-positive generator; this is the stop condition, as a test."""
        findings = self.scan_snippet("consumer.yml", DOCUMENT_NAME_SNIPPET)
        lines = [f["line"] for f in self.of_category(findings,
                                                     COUPLING_DOCUMENT_NAME)]
        description_line = DOCUMENT_NAME_SNIPPET.splitlines().index(
            "      description: Load cached worldcup:event docs from same-pod"
            " document state.") + 1
        self.assertNotIn(description_line, lines)


class TestStoragePredicateCoupling(CouplingScanTestCase):

    def test_detects_storage_predicate_startdate(self):
        findings = self.scan_snippet("consumer.yml", STORAGE_PREDICATE_SNIPPET)
        predicates = self.of_category(findings, COUPLING_STORAGE_PREDICATE)
        self.assertIn("value.schema:startDate", [f["path"] for f in predicates])
        for finding in predicates:
            self.assertEqual(finding["category"], "storage-predicate")

    def test_detects_storage_predicate_status(self):
        findings = self.scan_snippet("consumer.yml", STORAGE_PREDICATE_SNIPPET)
        predicates = self.of_category(findings, COUPLING_STORAGE_PREDICATE)
        self.assertIn("value.sport:status", [f["path"] for f in predicates])

    def test_the_sorter_position_is_detected_as_well_as_the_filter_key(self):
        """``search-sorters`` binds the consumer to the storage shape exactly as
        a filter key does, and it is the position the real repository uses most."""
        findings = self.scan_snippet("consumer.yml", STORAGE_PREDICATE_SNIPPET)
        sorter_line = [
            index + 1
            for index, line in enumerate(STORAGE_PREDICATE_SNIPPET.splitlines())
            if "search-sorters" in line
        ][0]
        self.assertIn(sorter_line,
                      [f["line"] for f in self.of_category(
                          findings, COUPLING_STORAGE_PREDICATE)])

    def test_a_commented_out_predicate_is_not_a_finding(self):
        """``connectors/sportradar-soccer/workflows/event-consumer-prelive.yml``
        carries a whole disabled task whose filter lines are commented out. A
        matcher that reports those reports work nobody has to do."""
        findings = self.scan_snippet("consumer.yml", """\
workflow:
  tasks:
    # - type: document
    #   filters:
    #     value.schema:startDate: "{'$gt': 'now'}"
    #     value.sport:status: "{'$in': ['not_started']}"
""")
        self.assertEqual(self.of_category(findings, COUPLING_STORAGE_PREDICATE),
                         [])


class TestDescriptionProseIsNotAStoragePredicate(CouplingScanTestCase):
    """Regression. ``value.`` anchoring was assumed to keep the storage-predicate
    matcher off prose, and it does not: a ``description:`` scalar is prose that
    happens to quote the storage path, and a multi-line one puts that quote on an
    indented continuation line that looks exactly like a nested mapping key.

    The narrowness claim in this module's docstring — and the "0 prose false
    positives" claim in the commit that introduced the scan — were therefore
    wrong for description scalars. This holds the corrected line.
    """

    def test_a_multi_line_description_scalar_is_not_a_storage_predicate(self):
        """Prose inside the scalar is skipped; the ``filters:`` key that follows
        it is still reported. Asserted as an exact list, because a fix that
        swallowed the real filter along with the prose would pass a
        ``assertNotIn`` and still be wrong."""
        findings = self.scan_snippet("consumer.yml", DESCRIPTION_PROSE_SNIPPET)
        predicates = self.of_category(findings, COUPLING_STORAGE_PREDICATE)
        self.assertEqual([f["path"] for f in predicates], ["value.sport:status"])

    def test_the_sportradar_mlb_description_line_is_not_reported(self):
        """The real-repo instance the review found: line 7 of
        ``connectors/sportradar-mlb/sync-results.yml`` is a continuation line of
        the ``description:`` scalar opened on line 4."""
        source = (REPO_ROOT / "connectors/sportradar-mlb/sync-results.yml").read_text(
            encoding="utf-8").splitlines()
        self.assertIn(
            "value.sport:score", source[6],
            "line 7 no longer carries the prose this regression is about; "
            "re-point the assertion rather than deleting it")
        self.assertEqual(
            [f for f in scan_couplings("connectors")
             if f["file"] == "connectors/sportradar-mlb/sync-results.yml"
             and f["line"] == 7],
            [])


class TestEveryFindingCanBeLocated(CouplingScanTestCase):

    def all_findings(self) -> list:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        (directory / "names.yml").write_text(DOCUMENT_NAME_SNIPPET,
                                             encoding="utf-8")
        (directory / "predicates.yml").write_text(STORAGE_PREDICATE_SNIPPET,
                                                  encoding="utf-8")
        return scan_couplings(str(directory))

    def test_findings_carry_file_and_line_evidence(self):
        findings = self.all_findings()
        self.assertTrue(findings, "the scan found nothing to carry evidence for")
        for finding in findings:
            with self.subTest(finding=finding):
                self.assertIsInstance(finding["file"], str)
                self.assertTrue(finding["file"])
                self.assertIsInstance(finding["line"], int)
                self.assertNotIsInstance(finding["line"], bool)
                self.assertGreaterEqual(finding["line"], 1)

    def test_every_finding_carries_a_category_and_a_snippet(self):
        for finding in self.all_findings():
            with self.subTest(finding=finding):
                self.assertIn(finding["category"],
                              (COUPLING_DOCUMENT_NAME,
                               COUPLING_STORAGE_PREDICATE))
                self.assertTrue(finding["snippet"].strip())

    def test_the_recorded_line_really_contains_the_matched_text(self):
        """Evidence that cannot be checked is decoration. The recorded line
        number is read back off the file it names."""
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        (directory / "predicates.yml").write_text(STORAGE_PREDICATE_SNIPPET,
                                                  encoding="utf-8")
        for finding in scan_couplings(str(directory)):
            with self.subTest(finding=finding):
                matched = finding.get("literal") or finding.get("path")
                source = (directory / "predicates.yml").read_text(
                    encoding="utf-8").splitlines()
                self.assertIn(matched, source[finding["line"] - 1])


class TestTheRealRepositoryIsScanned(CouplingScanTestCase):
    """The synthetic cases prove the matchers bite. These prove they bite on the
    tree PR 3 actually has to keep working."""

    def test_real_repo_scan_detects_worldcup_event_couplings(self):
        """WCI's document-name coupling, and the storage-predicate couplings, on
        real bytes.

        **Deviation from the task brief, recorded here rather than hidden.** The
        brief expected all three findings inside
        ``agent-templates/world-cup-intelligence/``. The document-name coupling
        is there. The two storage predicates are **not**: WCI filters only on
        ``name``, ``value._id``, ``value.@type``, ``value.event_urn``,
        ``value.subject_urn``, ``value.status`` and ``value.ts``, and reads
        ``schema:startDate`` / ``sport:status`` in Python off an already-loaded
        document instead. ``value.schema:startDate`` and ``value.sport:status``
        live in ``connectors/sportradar-soccer/`` and
        ``connectors/stats-perform/``.

        Making this test pass against the WCI root alone would require matching a
        bare ``sport:status`` anywhere in a file, which fires in prose and
        comments — the explicitly forbidden outcome. So the assertion is split to
        follow the evidence: document-name where the document name is, storage
        predicates where the storage predicates are. The consequence for PR 3-D
        task 12 is real and is not this task's to fix: the consumers coupled to
        the persisted event shape are in the provider connector trees, not in WCI.
        """
        wci = scan_couplings(WCI_ROOT)
        document_names = [f for f in wci
                          if f["category"] == COUPLING_DOCUMENT_NAME
                          and f["literal"] == "worldcup:event"]
        self.assertTrue(
            document_names,
            "no document-name coupling found for worldcup:event under "
            "{0}".format(WCI_ROOT))

        predicates = {f["path"] for f in scan_couplings("connectors")
                      if f["category"] == COUPLING_STORAGE_PREDICATE}
        for path in ("value.schema:startDate", "value.sport:status"):
            with self.subTest(path=path):
                self.assertIn(path, predicates)

    def test_the_storage_predicates_are_absent_from_wci_and_present_in_connectors(self):
        """The deviation above, asserted rather than asserted-about. If a later
        change puts a storage predicate into WCI, this test fails and the
        compatibility-projection reasoning in task 12 has to be revisited."""
        wci = {f["path"] for f in scan_couplings(WCI_ROOT)
               if f["category"] == COUPLING_STORAGE_PREDICATE}
        self.assertEqual(
            wci & {"value.schema:startDate", "value.sport:status"}, set())

        connectors = {f["path"] for f in scan_couplings("connectors")
                      if f["category"] == COUPLING_STORAGE_PREDICATE}
        self.assertIn("value.schema:startDate", connectors)
        self.assertIn("value.sport:status", connectors)

    def test_every_real_finding_is_locatable_in_the_file_it_names(self):
        """The same read-back check as the synthetic case, against real bytes —
        this is what makes the findings usable as a work list."""
        for finding in scan_couplings(WCI_ROOT):
            with self.subTest(finding=finding):
                path = REPO_ROOT / finding["file"]
                self.assertTrue(path.is_file(), finding["file"])
                lines = path.read_text(encoding="utf-8",
                                       errors="replace").splitlines()
                matched = finding.get("literal") or finding.get("path")
                self.assertIn(matched, lines[finding["line"] - 1])

    def test_no_finding_lands_on_a_comment_line(self):
        """Narrowness, measured on the real tree rather than promised."""
        for root in SCAN_ROOTS:
            for finding in scan_couplings(root):
                with self.subTest(finding=finding):
                    self.assertFalse(finding["snippet"].lstrip().startswith("#"))


class TestTheInventoryExposesCouplings(unittest.TestCase):
    """The findings have to reach the generated inventory, or task 2's review
    ledger has nothing to review."""

    @classmethod
    def setUpClass(cls):
        cls.inventory = build_inventory()

    def test_the_inventory_carries_the_couplings_additively(self):
        self.assertIn("couplings", self.inventory)
        self.assertTrue(self.inventory["couplings"])

    def test_the_inventory_couplings_cover_both_categories_from_the_scan_roots(self):
        """The findings task 2's ledger has to account for: the WCI document name
        and the connector storage predicates, reached from the inventory rather
        than from a second scan a reader would have to run themselves."""
        couplings = self.inventory["couplings"]
        for finding in couplings:
            with self.subTest(finding=finding):
                self.assertTrue(finding["file"].startswith(SCAN_ROOTS))
        self.assertIn(
            ("{0}/_folders.yml".format(WCI_ROOT), "worldcup:event"),
            [(f["file"], f.get("literal")) for f in couplings
             if f["category"] == COUPLING_DOCUMENT_NAME])
        predicates = {f["path"] for f in couplings
                      if f["category"] == COUPLING_STORAGE_PREDICATE}
        self.assertIn("value.schema:startDate", predicates)
        self.assertIn("value.sport:status", predicates)

    def test_the_pre_existing_top_level_keys_are_unchanged_and_in_order(self):
        """The one shape change allowed is the added key. This pins every other
        key and its position, so a refactor that reorders or renames one fails
        here rather than in a reviewer's diff of a regenerated artifact."""
        self.assertEqual(
            [key for key in self.inventory if key != "couplings"],
            ["inventory_version", "inventory_kind", "reproduce", "pin",
             "categories", "scope_boundary", "known_gaps", "totals",
             "sport_namespace_usage", "emitters", "consumers"])


#: The review ledger task 2 adds. Hand-authored data, not a generated artefact.
LEDGER_PATH = REPO_ROOT / "docs/iptc/consumer-review.json"

#: The generated artefact the ledger is checked against. Read off disk rather than
#: from :func:`build_inventory`, because the point is that the *committed* artefact
#: and the *committed* ledger agree — a ledger that only agrees with a fresh
#: in-memory scan would let a stale artefact ship.
INVENTORY_JSON_PATH = REPO_ROOT / "docs/iptc/inventory.json"

LEDGER_SCHEMA = "machina.iptc.consumer-review/v1"

#: No fifth disposition. A row nobody can place is ``excluded`` with a reason.
ALLOWED_DISPOSITIONS = ("migrate", "compat-alias", "no-change", "excluded")

#: This repository. The ledger carries ``repo`` because later PR 3 lanes review
#: cross-repository consumers, and a bare path would then be ambiguous.
REPO = "machina-templates"

#: The generated inventory sections that record a file-level dependency on the
#: legacy shape: files that read it, files that emit it, files welded to the
#: document name or the storage predicate.
DEPENDENCY_SECTIONS = ("consumers", "emitters", "couplings")

#: Owner label for a dependency whose ownership cannot be grounded. Paired with
#: ``disposition: excluded`` — inventing an owner is worse than admitting there
#: isn't one, because an invented owner reads as a commitment somebody made.
UNASSIGNED = "UNASSIGNED"


class ReviewLedgerTestCase(unittest.TestCase):
    """Base for the ledger cases.

    Every test loads the ledger **first**. That ordering is deliberate: before
    ``docs/iptc/consumer-review.json`` exists, the failure has to be the missing
    ledger (``FileNotFoundError``) and not some incidental complaint about the
    inventory artefact, or the RED step proves nothing about the file under test.
    """

    def load_ledger(self) -> dict:
        with LEDGER_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)

    def entries(self) -> list:
        return self.load_ledger()["entries"]

    def load_inventory(self) -> dict:
        inventory = json.loads(INVENTORY_JSON_PATH.read_text(encoding="utf-8"))
        for section in DEPENDENCY_SECTIONS:
            self.assertIn(
                section, inventory,
                "docs/iptc/inventory.json is stale — regenerate it with "
                "`python3 -m tools.iptc`")
        return inventory

    def generated_dependencies(self) -> set:
        """Every ``(repo, path)`` the generated inventory records as depending on
        the legacy shape."""
        inventory = self.load_inventory()
        return {
            (REPO, row["file"])
            for section in DEPENDENCY_SECTIONS
            for row in inventory[section]
        }

    def reviewed(self, entry: dict) -> bool:
        """A row counts as reviewed only if it carries a disposition from the
        allowed set *and* evidence. A row with a blank ``evidence`` is a row
        somebody ticked, not a row somebody reviewed."""
        return (entry.get("disposition") in ALLOWED_DISPOSITIONS
                and isinstance(entry.get("evidence"), str)
                and bool(entry["evidence"].strip()))


class TestTheReviewLedgerIsWellFormed(ReviewLedgerTestCase):

    def test_review_ledger_exists_and_has_schema_and_version(self):
        ledger = self.load_ledger()
        self.assertEqual(ledger["schema"], LEDGER_SCHEMA)
        self.assertIsInstance(ledger["version"], str)
        self.assertTrue(ledger["version"].strip())
        self.assertIsInstance(ledger["entries"], list)
        self.assertTrue(ledger["entries"], "a ledger with no entries reviews nothing")

    def test_every_entry_has_required_fields(self):
        for entry in self.entries():
            with self.subTest(entry=entry.get("path"), category=entry.get("category")):
                for field in ("repo", "path", "category", "owner", "disposition",
                              "evidence"):
                    self.assertIsInstance(entry.get(field), str, field)
                    self.assertTrue(entry[field].strip(), field)
                self.assertIn(entry["disposition"], ALLOWED_DISPOSITIONS)
                self.assertEqual(entry["repo"], REPO)

    def test_every_owner_is_grounded_in_the_path_it_owns(self):
        """Ownership is a claim, so it has to be checkable. An owner is either
        ``UNASSIGNED`` — which forces ``excluded`` — or a
        ``<repo>:<surface-directory>`` label that the reviewed path actually lives
        under. This is what stops the ledger naming a person, a team that owns
        nothing here, or a directory the row is not in."""
        for entry in self.entries():
            with self.subTest(path=entry["path"], owner=entry["owner"]):
                if entry["owner"] == UNASSIGNED:
                    self.assertEqual(entry["disposition"], "excluded")
                    continue
                repo, separator, surface = entry["owner"].partition(":")
                self.assertEqual(repo, REPO)
                self.assertTrue(separator, "owner must be <repo>:<surface>")
                self.assertTrue(
                    entry["path"].startswith(surface + "/"),
                    "{0} does not live under its claimed owner {1}".format(
                        entry["path"], surface))


class TestTheLedgerCoversEveryGeneratedDependency(ReviewLedgerTestCase):

    def test_every_generated_dependency_is_reviewed_or_excluded(self):
        ledger_keys = {(entry["repo"], entry["path"]) for entry in self.entries()}
        missing = sorted(self.generated_dependencies() - ledger_keys)
        self.assertEqual(missing, [],
                         "{0} generated dependencies are absent from the "
                         "ledger".format(len(missing)))

    def test_unreviewed_count_is_zero(self):
        """The headline number. A dependency is unreviewed when no ledger entry
        for it carries both a disposition and evidence."""
        reviewed_keys = {(entry["repo"], entry["path"]) for entry in self.entries()
                         if self.reviewed(entry)}
        unreviewed = sorted(self.generated_dependencies() - reviewed_keys)
        self.assertEqual(len(unreviewed), 0, "unreviewed: {0}".format(unreviewed))

    def test_no_orphan_ledger_entries(self):
        """A ledger that drifts ahead of reality is worse than no ledger: it
        reports work as accounted for against paths that no longer exist.
        ``excluded`` rows are exempt, since exclusion is how a row that is *not*
        a generated dependency gets recorded."""
        entries = self.entries()
        generated = self.generated_dependencies()
        orphans = sorted(
            (entry["repo"], entry["path"], entry["category"])
            for entry in entries
            if entry["disposition"] != "excluded"
            and (entry["repo"], entry["path"]) not in generated)
        self.assertEqual(orphans, [])


class TestTheLedgerAgreesWithTheGeneratedEvidence(ReviewLedgerTestCase):
    """Coverage is necessary and not sufficient. These hold the ledger to the
    *category* the inventory recorded, in both directions, so a row cannot be
    filed under a dependency it does not have."""

    def coupling_triples(self) -> set:
        return {(finding["file"], finding["category"],
                 finding.get("literal") or finding.get("path"))
                for finding in self.load_inventory()["couplings"]}

    def test_the_coupling_entries_and_the_generated_findings_agree(self):
        entries = self.entries()
        ledger_triples = {
            (entry["path"], entry["category"], entry.get("literal"))
            for entry in entries
            if entry["category"] in (COUPLING_DOCUMENT_NAME,
                                     COUPLING_STORAGE_PREDICATE)}
        generated = self.coupling_triples()
        self.assertEqual(sorted(ledger_triples - generated), [],
                         "ledger claims couplings the inventory does not record")
        self.assertEqual(sorted(generated - ledger_triples), [],
                         "inventory records couplings the ledger does not review")

    def test_read_and_emitter_entries_match_their_inventory_section(self):
        entries = self.entries()
        inventory = self.load_inventory()
        field_readers = {c["file"] for c in inventory["consumers"]
                         if c["reads_field_paths"]}
        payload_readers = {c["file"] for c in inventory["consumers"]
                           if c["reads_payload_keys"]}
        emitters = {e["file"] for e in inventory["emitters"]}
        expected = {"field-path-read": field_readers,
                    "payload-key-read": payload_readers,
                    "emitter": emitters}
        actual = {category: set() for category in expected}
        for entry in entries:
            if entry["category"] in actual:
                actual[entry["category"]].add(entry["path"])
        self.assertEqual(actual, expected)


class TestTheDispositionsFollowTheDependencyCategory(ReviewLedgerTestCase):
    """The failure mode this guards against is a ledger filled in with one
    disposition everywhere, which satisfies coverage while recording no decision.
    Each case below pins a disposition the PR 3 plan actually commits to."""

    def dispositions_for(self, category, literal=None, path_prefix="") -> set:
        return {entry["disposition"] for entry in self.entries()
                if entry["category"] == category
                and (literal is None or entry.get("literal") == literal)
                and entry["path"].startswith(path_prefix)}

    def test_the_worldcup_event_document_name_is_kept_by_compatibility_alias(self):
        """The plan keeps the ``worldcup:event`` document name unchanged and
        derives exact-path compatibility aliases underneath it. So every WCI row
        coupled to that literal is ``compat-alias`` — not ``migrate``, which would
        mean renaming the document, and not ``no-change``, which would mean the
        alias requirement did not exist."""
        dispositions = self.dispositions_for(
            COUPLING_DOCUMENT_NAME, literal="worldcup:event",
            path_prefix=WCI_ROOT + "/")
        self.assertTrue(dispositions, "no worldcup:event document-name rows")
        self.assertEqual(dispositions, {"compat-alias"})

    def test_the_storage_predicates_are_owned_by_the_connector_surfaces(self):
        """Task 1's evidence amendment, carried into the ledger: the consumers
        welded to the persisted event shape are provider connector workflows, so
        those connector paths — not WCI — are what carries an owner and a
        disposition for ``value.schema:startDate`` and ``value.sport:status``."""
        for literal in ("value.schema:startDate", "value.sport:status"):
            with self.subTest(literal=literal):
                owners = {entry["owner"] for entry in self.entries()
                          if entry["category"] == COUPLING_STORAGE_PREDICATE
                          and entry.get("literal") == literal
                          and entry["path"].startswith("connectors/")}
                self.assertTrue(owners, "no connector owner for " + literal)
                for owner in owners:
                    self.assertTrue(owner.startswith(REPO + ":connectors/"), owner)
                self.assertEqual(
                    self.dispositions_for(COUPLING_STORAGE_PREDICATE,
                                          literal=literal,
                                          path_prefix="connectors/"),
                    {"compat-alias"})

    def test_the_dispositions_are_not_uniform(self):
        """Belt and braces on the same failure mode, measured over the whole
        ledger rather than per case."""
        used = {entry["disposition"] for entry in self.entries()}
        self.assertEqual(used, set(ALLOWED_DISPOSITIONS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
