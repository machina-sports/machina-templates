"""Tests for the offline IPTC Sport Schema 1.1 conformance harness.

Run from the repository root:

    python3 -m pip install -r requirements-iptc-validator.txt
    python3 tests/test_iptc_validation_harness.py -v

Run the file directly. ``tests/`` is a namespace directory with no ``__init__.py``,
so any installed distribution shipping a top-level regular ``tests`` package wins on
``sys.path`` and ``-m unittest tests.test_iptc_validation_harness`` never resolves.

What is being defended here, in order of importance:

1. **The pin is real.** Every vendored byte still hashes to what
   ``upstream-commit.json`` says, the version evidence is still in the artefacts,
   and no 1.1 release tag is referenced anywhere.
2. **The positive controls pass.** If an official upstream sample or the
   tightly-scoped conforming fixture regresses, the harness is broken and every
   finding it produces is suspect.
3. **Each detector actually fires.** A gate that cannot fail is decoration, so
   there is one negative fixture per gate and a test that asserts it trips the
   right one and, where relevant, only the right one.
4. **The baseline report is reproducible.** The baseline is EXPECTED to fail
   conformance; what CI can honestly assert is that the recorded failure is
   byte-stable.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import rdflib  # noqa: E402

from tools.iptc import context as context_module  # noqa: E402
from tools.iptc import fileio as fileio_module  # noqa: E402
from tools.iptc import inventory as inventory_module  # noqa: E402
from tools.iptc import profile as profile_module  # noqa: E402
from tools.iptc import reference as reference_module  # noqa: E402
from tools.iptc import report as report_module  # noqa: E402
from tools.iptc.__main__ import run  # noqa: E402
from tools.iptc.reference import (  # noqa: E402
    MACHINA_AUTHORED_REFERENCE_FILES,
    OFFICIAL_MAIN_NS,
    PIN_MANIFEST_PATH,
    REFERENCE_ROOT,
    ReferenceIntegrityError,
    SHACL_PATH,
    TARGET_VERSION,
    UPSTREAM_COMMIT,
    load_reference,
    verify_manifest,
)
from tools.iptc.validate import context_loader_findings, parse_jsonld, validate_document  # noqa: E402

FIXTURES = reference_module.PACKAGE_ROOT / "fixtures"


def validate(relative: str):
    """`relative` is repo-root-relative, matching fixtures/provenance.json."""
    path = REPO_ROOT / relative
    return validate_document(path, relative, repo_root=REPO_ROOT)


def codes(result) -> list[str]:
    return [f["code"] for f in result.layers["machina_profile"]["detail"]["findings"]]


class TestPin(unittest.TestCase):
    """The pin has to be exact and verifiable, or nothing downstream is evidence."""

    def test_every_vendored_file_matches_its_recorded_hash(self):
        checked = verify_manifest()
        self.assertGreater(len(checked), 30)

    def test_manifest_records_the_commit_not_a_tag(self):
        manifest = json.loads(PIN_MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(manifest["upstream_commit"], UPSTREAM_COMMIT)
        self.assertEqual(manifest["upstream_repository"], "https://github.com/iptc/sport-schema")
        self.assertEqual(manifest["license"]["spdx_id"], "CC-BY-4.0")
        self.assertIsNone(manifest["license"]["upstream_license_file"])

    def test_no_artefact_invents_a_v1_1_tag(self):
        """There is no 1.1 release tag upstream. Nothing may imply otherwise."""
        offenders = []
        roots = [
            REFERENCE_ROOT / "UPSTREAM.md",
            REFERENCE_ROOT / "LICENSE.md",
            PIN_MANIFEST_PATH,
            context_module.CONTEXT_PATH,
            reference_module.PACKAGE_ROOT / "README.md",
            REPO_ROOT / "docs" / "rfcs" / "001-machina-iptc-sport-schema-profile.md",
            REPO_ROOT / "docs" / "iptc" / "BASELINE-AUDIT.md",
        ]
        for path in roots:
            if not path.is_file():
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                lowered = line.lower()
                if "v1.1" not in lowered:
                    continue
                # A line that explicitly forbids the tag is the opposite of a
                # fabricated reference to it.
                if any(marker in lowered for marker in
                       ("no 1.1 tag", "never", "do not", "does not exist", "would be")):
                    continue
                offenders.append(f"{path.name}:{number}: {line.strip()}")
        self.assertEqual(offenders, [], "a 'v1.1' tag reference would be fabricated")

    def test_version_evidence_is_present_in_the_pinned_bytes(self):
        ontology = (REFERENCE_ROOT / "ontologies" / "iptc-sport-ontology.ttl").read_text(encoding="utf-8")
        self.assertIn(f"owl:versionIRI <{OFFICIAL_MAIN_NS}{TARGET_VERSION}>", ontology)
        self.assertIn('owl:versionInfo "1.1"^^xsd:string', ontology)
        self.assertIn("dcterms:license <https://creativecommons.org/licenses/by/4.0/>", ontology)
        readme = (REFERENCE_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Latest version: Sport Schema 1.1", readme)

    def test_official_sport_namespace_comes_from_the_pin(self):
        reference = load_reference()
        self.assertEqual(reference.prefixes["sport"], OFFICIAL_MAIN_NS)

    def test_upstream_shims_are_reported_not_hidden(self):
        shims = load_reference().shims_applied
        self.assertEqual(len(shims["unterminated_prefix_directive_repairs"]), 15)
        self.assertEqual(shims["orphan_sh_ignoredproperties_dropped"], 6)

    def test_ontology_term_extraction_finds_the_real_classes(self):
        reference = load_reference()
        local = reference.main_local_names()
        for official in ("Event", "Team", "Athlete", "Competition", "CompetitionPhase",
                         "Site", "Participation", "TeamParticipation", "Action",
                         "Membership", "eventStatus", "startDateTime", "alignment",
                         "participationBy", "score"):
            self.assertIn(official, local, f"{official} should be an official 1.1 term")
        for invented in ("Venue", "Season", "SportEvent", "Player", "competitors",
                         "qualifier", "status", "homeScore", "awayScore", "halfTime",
                         "matchStatus", "label", "year"):
            self.assertNotIn(invented, local, f"{invented} is NOT an official 1.1 term")


class TestSharedContext(unittest.TestCase):
    """The context's only claim is that it was copied. Check the copy."""

    def test_no_drift_against_the_pin(self):
        self.assertEqual(context_module.check_context_against_reference(), [])

    def test_verified_prefix_spellings(self):
        """Spellings the plan could plausibly have got wrong, checked against bytes."""
        shared = context_module.load_context()
        reference = load_reference()
        for prefix, expected_path in (
            ("spbblstat", "baseball"),
            ("spmcrstat", "motor-racing"),
            ("spfacet", "sport-facets"),
            ("spgolf", "golf"),
            ("spgolstat", "golf"),
            ("spsocstat", "soccer"),
            ("sptenstat", "tennis"),
            ("spamfstat", "american-football"),
            ("spbkbstat", "basketball"),
            ("sprgxstat", "rugby"),
            ("spvolstat", "volleyball"),
            ("spespstat", "esports"),
            ("spstat", "corestatistics"),
        ):
            iri = f"https://sportschema.org/ontologies/{expected_path}/"
            self.assertEqual(shared[prefix], iri, prefix)
            self.assertEqual(reference.prefixes[prefix], iri, f"{prefix} in the pin")

    def test_soccer_action_prefix_name_differs_from_its_path_segment(self):
        shared = context_module.load_context()
        self.assertEqual(shared["spsocactiontype"], "http://cv.iptc.org/newscodes/spsocaction/")

    def test_standard_and_extension_prefixes_are_explicit(self):
        shared = context_module.load_context()
        self.assertEqual(shared["rdf"], "http://www.w3.org/1999/02/22-rdf-syntax-ns#")
        self.assertEqual(shared["rdfs"], "http://www.w3.org/2000/01/rdf-schema#")
        self.assertEqual(shared["xsd"], "http://www.w3.org/2001/XMLSchema#")
        self.assertEqual(shared["skos"], "http://www.w3.org/2004/02/skos/core#")
        self.assertEqual(shared["schema"], "https://schema.org/")
        self.assertEqual(shared["prov"], "http://www.w3.org/ns/prov#")
        self.assertEqual(shared["machina"], context_module.MACHINA_NS)
        self.assertTrue(shared["machina"].startswith("https://machina.gg/"))

    def test_machina_namespace_is_not_under_sport(self):
        self.assertNotIn("sportschema.org", context_module.MACHINA_NS)


class TestPositiveControls(unittest.TestCase):
    """If these regress, the harness is wrong, not the data."""

    def test_official_upstream_samples_conform(self):
        for sample in ("soccer-match-02", "player-bio-01", "team-roster", "soccer-standings"):
            with self.subTest(sample=sample):
                result = validate(
                    "agent-templates/iptc-mappings/references/iptc-sport-schema-1.1"
                    f"/samples/json-ld/{sample}.jsonld")
                self.assertTrue(result.layers["jsonld_parse"]["ok"])
                self.assertTrue(
                    result.layers["official_shacl"]["ok"],
                    result.layers["official_shacl"]["detail"].get("results"),
                )
                self.assertFalse(result.layers["official_shacl"]["detail"]["vacuous"])

    def test_conforming_minimal_passes_all_four_layers_and_all_four_gates(self):
        result = validate("tools/iptc/fixtures/conforming/machina-profile-conforming-minimal.json")
        self.assertTrue(result.layers["jsonld_parse"]["ok"])
        self.assertTrue(result.layers["official_shacl"]["ok"],
                        result.layers["official_shacl"]["detail"].get("results"))
        self.assertTrue(result.layers["machina_profile"]["ok"],
                        result.layers["machina_profile"]["detail"].get("findings"))
        self.assertTrue(result.layers["controlled_vocabulary"]["ok"],
                        result.layers["controlled_vocabulary"]["detail"])
        self.assertEqual(result.counters["unknown_sport_terms"], 0)
        self.assertEqual(result.counters["invalid_newscode_values"], 0)
        self.assertEqual(result.counters["duplicate_resource_ids"], 0)
        self.assertEqual(result.counters["provider_properties_in_iptc_namespace"], 0)
        self.assertTrue(result.conforms)

    def test_conforming_minimal_covers_the_eight_resource_kinds(self):
        document = json.loads(
            (FIXTURES / "conforming" / "machina-profile-conforming-minimal.json")
            .read_text(encoding="utf-8"))
        types = {node.get("@type") for node in document["@graph"]}
        for required in ("sport:Event", "sport:Competition", "sport:CompetitionPhase",
                         "sport:Site", "sport:Team", "sport:Athlete",
                         "sport:TeamParticipation", "sport:IndividualParticipation",
                         "sport:Action", "sport:IndividualMembership"):
            self.assertIn(required, types)

    def test_machina_extension_lives_on_its_own_node_not_on_an_official_class(self):
        """The official shapes are sh:closed, so this is a hard constraint.

        Attaching machina:providerIdentifier directly to a sport:Team violates
        sport:TeamShape's ClosedConstraintComponent. The profile therefore requires
        extension properties on machina:-typed nodes that reference the official
        resource.
        """
        document = json.loads(
            (FIXTURES / "conforming" / "machina-profile-conforming-minimal.json")
            .read_text(encoding="utf-8"))
        for node in document["@graph"]:
            node_type = node.get("@type", "")
            if isinstance(node_type, str) and node_type.startswith("sport:"):
                leaked = [k for k in node if k.startswith("machina:")]
                self.assertEqual(leaked, [], f"{node['@id']} carries {leaked}")


class TestNegativeControls(unittest.TestCase):
    """One fixture per gate. A gate that cannot fail is decoration."""

    def test_invented_sport_term_trips_gate_one(self):
        result = validate("tools/iptc/fixtures/negative/invented-sport-term.json")
        self.assertGreater(result.counters["unknown_sport_terms"], 0)
        self.assertIn("invented-sport-term", codes(result))
        self.assertFalse(result.conforms)
        # Isolation: only gate 1 moves.
        self.assertEqual(result.counters["invalid_newscode_values"], 0)
        self.assertEqual(result.counters["duplicate_resource_ids"], 0)
        self.assertEqual(result.counters["provider_properties_in_iptc_namespace"], 0)

    def test_invalid_newscode_trips_gate_two(self):
        result = validate("tools/iptc/fixtures/negative/invalid-newscode.json")
        self.assertGreater(result.counters["invalid_newscode_values"], 0)
        self.assertFalse(result.layers["controlled_vocabulary"]["ok"])
        invalid = result.layers["controlled_vocabulary"]["detail"]["invalid"]
        self.assertTrue(any("definitely-not-a-status" in i["value"] for i in invalid))
        self.assertEqual(result.counters["unknown_sport_terms"], 0)
        self.assertEqual(result.counters["duplicate_resource_ids"], 0)

    def test_valid_newscode_is_recognised_from_the_pinned_ttl(self):
        result = validate("tools/iptc/fixtures/conforming/machina-profile-conforming-minimal.json")
        valid = result.layers["controlled_vocabulary"]["detail"]["valid"]
        values = {item["value"] for item in valid}
        self.assertIn("http://cv.iptc.org/newscodes/spplayerstatus/starter", values)
        self.assertIn("http://cv.iptc.org/newscodes/speventstatus/post-event", values)
        for item in valid:
            self.assertTrue(item["source"].startswith("vocabularies/"))

    def test_duplicate_ids_trip_gate_three(self):
        result = validate("tools/iptc/fixtures/negative/duplicate-ids.json")
        self.assertEqual(result.counters["duplicate_resource_ids"], 1)
        self.assertIn("duplicate-node-id", codes(result))
        self.assertEqual(result.counters["unknown_sport_terms"], 0)
        self.assertEqual(result.counters["provider_properties_in_iptc_namespace"], 0)

    def test_node_references_are_not_counted_as_duplicates(self):
        """Regression guard: {"@id": x} is a reference, not a second description."""
        result = validate("tools/iptc/fixtures/conforming/machina-profile-conforming-minimal.json")
        self.assertEqual(result.counters["duplicate_resource_ids"], 0)

    def test_provider_leakage_trips_gate_four(self):
        result = validate("tools/iptc/fixtures/negative/provider-leakage.json")
        self.assertEqual(result.counters["provider_properties_in_iptc_namespace"], 2)
        self.assertIn("provider-property-in-iptc-namespace", codes(result))
        leaks = result.layers["counter_detail"]["provider_properties_in_iptc_namespace"]
        attributed = {p for leak in leaks for p in leak["providers"]}
        self.assertIn("sportradar-mlb", attributed)
        # Gates 1 and 4 overlap by construction, and that overlap is documented.
        self.assertEqual(result.counters["unknown_sport_terms"], 2)

    def test_malformed_jsonld_fails_layer_one_and_nulls_the_counters(self):
        result = validate("tools/iptc/fixtures/negative/malformed.jsonld")
        self.assertFalse(result.layers["jsonld_parse"]["ok"])
        self.assertEqual(result.layers["jsonld_parse"]["detail"]["stage"], "json")
        for layer in ("official_shacl", "machina_profile", "controlled_vocabulary"):
            self.assertFalse(result.layers[layer]["ok"])
            self.assertIn("skipped", result.layers[layer]["detail"])
        # Null, never zero: nothing could be counted, and zero would read as clean.
        for gate in ("unknown_sport_terms", "invalid_newscode_values",
                     "duplicate_resource_ids",
                     "provider_properties_in_iptc_namespace"):
            self.assertIsNone(result.counters[gate])

    def test_null_and_placeholder_are_profile_violations_with_all_gates_clean(self):
        result = validate("tools/iptc/fixtures/negative/null-and-placeholder.json")
        found = codes(result)
        self.assertIn("null-value", found)
        self.assertIn("placeholder-value", found)
        self.assertFalse(result.layers["machina_profile"]["ok"])
        for gate in ("unknown_sport_terms", "invalid_newscode_values",
                     "duplicate_resource_ids",
                     "provider_properties_in_iptc_namespace"):
            self.assertEqual(result.counters[gate], 0, gate)
        self.assertFalse(result.conforms)

    def test_absent_value_is_accepted_where_null_is_not(self):
        """The rule is omission-over-fabrication, so omission must be clean."""
        document = json.loads(
            (FIXTURES / "conforming" / "machina-profile-conforming-minimal.json")
            .read_text(encoding="utf-8"))
        site = next(n for n in document["@graph"] if n["@type"] == "sport:Site")
        self.assertNotIn("sport:location", site)
        with_null = json.loads(json.dumps(document))
        next(n for n in with_null["@graph"] if n["@type"] == "sport:Site")["sport:location"] = None
        self.assertEqual([], [c for c in
                              (f["code"] for f in profile_module.check(document).findings)
                              if c == "null-value"])
        self.assertIn("null-value",
                      [f["code"] for f in profile_module.check(with_null).findings])


class TestOfflineContextGuard(unittest.TestCase):
    """Layer 1 must refuse every context the processor would fetch.

    "No network" is the claim the whole pin rests on. A document is untrusted
    input, and a JSON-LD processor handed a string ``@context`` will dereference
    it — so the guarantee has to be structural, not a comment.
    """

    def _write(self, payload: dict) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "document.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _assert_blocked(self, payload: dict, code: str):
        graph, detail = parse_jsonld(self._write(payload))
        self.assertIsNone(graph, "a blocked document must yield no graph")
        self.assertEqual(detail["stage"], "context")
        codes = [f["code"] for f in detail["blocked_context_references"]]
        self.assertIn(code, codes)
        return detail

    def test_string_context_url_is_rejected(self):
        detail = self._assert_blocked(
            {"@context": "https://example.invalid/ctx.jsonld", "@graph": []},
            "remote-context")
        self.assertEqual(detail["blocked_context_references"][0]["reference"],
                         "https://example.invalid/ctx.jsonld")

    def test_context_array_containing_a_url_is_rejected(self):
        self._assert_blocked(
            {"@context": [{"sport": OFFICIAL_MAIN_NS},
                          "https://example.invalid/ctx.jsonld"],
             "@graph": []},
            "remote-context")

    def test_nested_scoped_remote_context_is_rejected(self):
        """A scoped context is easy to miss: it hides inside a term definition."""
        self._assert_blocked(
            {"@context": {"sport": OFFICIAL_MAIN_NS,
                          "sport:participation": {
                              "@context": "https://example.invalid/scoped.jsonld"}},
             "@graph": []},
            "remote-context")

    def test_remote_context_on_a_nested_node_is_rejected(self):
        self._assert_blocked(
            {"@context": {"sport": OFFICIAL_MAIN_NS},
             "@graph": [{"@id": "urn:x:1", "@type": "sport:Event",
                         "sport:participation": {
                             "@context": "https://example.invalid/ctx.jsonld",
                             "@id": "urn:x:2"}}]},
            "remote-context")

    def test_context_import_is_rejected(self):
        self._assert_blocked(
            {"@context": {"@version": 1.1,
                          "@import": "https://example.invalid/base.jsonld",
                          "sport": OFFICIAL_MAIN_NS},
             "@graph": []},
            "context-import")

    def test_the_guard_runs_before_the_rdf_parser(self):
        """The point of the guard is ordering, so assert the ordering itself.

        rdflib is sabotaged: if layer 1 reached it, the test fails loudly instead
        of passing for the wrong reason.
        """
        path = self._write({"@context": "https://example.invalid/ctx.jsonld",
                            "@graph": []})

        def explode(*args, **kwargs):
            raise AssertionError("rdflib.Graph.parse was reached for a blocked "
                                 "document: the loader guard ran too late")

        original = rdflib.Graph.parse
        rdflib.Graph.parse = explode
        try:
            graph, detail = parse_jsonld(path)
        finally:
            rdflib.Graph.parse = original
        self.assertIsNone(graph)
        self.assertEqual(detail["stage"], "context")

    def test_inline_document_context_is_still_accepted(self):
        """The guard must not break the shape the profile actually requires."""
        self.assertEqual(context_loader_findings(
            {"@context": {"sport": OFFICIAL_MAIN_NS}, "@graph": []}), [])
        for sample in ("soccer-match-02", "player-bio-01", "team-roster",
                       "soccer-standings"):
            path = (REFERENCE_ROOT / "samples" / "json-ld" / f"{sample}.jsonld")
            with self.subTest(sample=sample):
                self.assertEqual(
                    context_loader_findings(json.loads(path.read_text(encoding="utf-8"))),
                    [], "an official upstream sample must not be blocked")

    def test_registered_negative_fixture_fails_layer_one_and_nulls_the_counters(self):
        result = validate("tools/iptc/fixtures/negative/remote-context.json")
        self.assertFalse(result.layers["jsonld_parse"]["ok"])
        self.assertEqual(result.layers["jsonld_parse"]["detail"]["stage"], "context")
        for layer in ("official_shacl", "machina_profile", "controlled_vocabulary"):
            self.assertFalse(result.layers[layer]["ok"])
            self.assertIn("will not load", result.layers[layer]["detail"]["skipped"])
        for gate in ("unknown_sport_terms", "invalid_newscode_values",
                     "duplicate_resource_ids",
                     "provider_properties_in_iptc_namespace"):
            self.assertIsNone(result.counters[gate])

    def test_findings_are_deterministic(self):
        payload = {"@context": ["https://example.invalid/b.jsonld",
                                "https://example.invalid/a.jsonld"],
                   "@graph": [{"@context": "https://example.invalid/c.jsonld"}]}
        first = context_loader_findings(payload)
        self.assertEqual(len(first), 3)
        self.assertEqual(first, context_loader_findings(payload))
        self.assertEqual([f["pointer"] for f in first],
                         sorted(f["pointer"] for f in first))


class TestPinRejectsUnmanifestedInputs(unittest.TestCase):
    """Hashing the listed files proves nothing about what the loader reads."""

    def test_an_extra_file_under_a_byte_exact_root_is_rejected(self):
        stray = REFERENCE_ROOT / "vocabularies" / "zz-unmanifested-test.ttl"
        self.assertFalse(stray.exists(), "test artefact left behind by a prior run")
        stray.write_text("@prefix ex: <https://example.invalid/> .\n", encoding="utf-8")
        try:
            with self.assertRaises(ReferenceIntegrityError) as caught:
                verify_manifest()
            self.assertIn("unmanifested", str(caught.exception))
            self.assertIn("zz-unmanifested-test.ttl", str(caught.exception))
        finally:
            stray.unlink()
        # And the tree verifies again once it is gone.
        self.assertGreater(len(verify_manifest()), 30)

    def test_the_three_machina_authored_files_are_deliberately_exempt(self):
        self.assertEqual(MACHINA_AUTHORED_REFERENCE_FILES,
                         {"LICENSE.md", "UPSTREAM.md", "upstream-commit.json"})
        manifest = json.loads(PIN_MANIFEST_PATH.read_text(encoding="utf-8"))
        listed = {entry["vendored_path"] for entry in manifest["files"]}
        for name in MACHINA_AUTHORED_REFERENCE_FILES:
            with self.subTest(name=name):
                self.assertTrue((REFERENCE_ROOT / name).is_file())
                self.assertNotIn(name, listed)

    def test_file_count_and_total_bytes_are_validated_not_decorative(self):
        manifest = json.loads(PIN_MANIFEST_PATH.read_text(encoding="utf-8"))
        listed = manifest["files"]
        self.assertEqual(manifest["file_count"], len(listed))
        self.assertEqual(manifest["total_bytes"],
                         sum(entry["size_bytes"] for entry in listed))
        for entry in listed:
            path = REFERENCE_ROOT / entry["vendored_path"]
            with self.subTest(file=entry["vendored_path"]):
                self.assertEqual(path.stat().st_size, entry["size_bytes"])

    def test_every_file_the_loader_globs_is_manifested(self):
        """The globbed roots are exactly what load_reference() reads."""
        manifest = json.loads(PIN_MANIFEST_PATH.read_text(encoding="utf-8"))
        listed = {entry["vendored_path"] for entry in manifest["files"]}
        for directory in ("ontologies", "shacl", "vocabularies", "samples", "tools"):
            for path in (REFERENCE_ROOT / directory).rglob("*"):
                if path.is_file():
                    relative = path.relative_to(REFERENCE_ROOT).as_posix()
                    with self.subTest(file=relative):
                        self.assertIn(relative, listed)


class TestFixtureWritesAreContainedAndAtomic(unittest.TestCase):
    """A fixture name is attacker-shaped input the moment it is a path fragment."""

    def test_traversal_names_are_rejected(self):
        from tools.iptc.extract_mapping_fixture import (
            FixtureNameError, fixture_target)

        for name in ("../../etc/passwd", "../escape", "a/b", "/absolute",
                     "..", ".", "Upper", "with space", "trailing/",
                     "-leading-hyphen", "under_score", ""):
            with self.subTest(name=name):
                with self.assertRaises(FixtureNameError):
                    fixture_target(name)

    def test_valid_slugs_resolve_inside_the_fixture_directory(self):
        from tools.iptc.extract_mapping_fixture import FIXTURE_DIR, fixture_target

        for name in ("sportradar-soccer-event", "custom-event", "a", "9x-y"):
            with self.subTest(name=name):
                target = fixture_target(name)
                self.assertEqual(target.parent, FIXTURE_DIR)
                self.assertEqual(target.name, f"{name}.json")

    def test_atomic_write_replaces_and_leaves_no_scratch_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "artefact.json"
            fileio_module.atomic_write_text(target, "first\n")
            self.assertEqual(target.read_text(encoding="utf-8"), "first\n")
            fileio_module.atomic_write_text(target, "second\n")
            self.assertEqual(target.read_text(encoding="utf-8"), "second\n")
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()),
                             ["artefact.json"])

    def test_a_failed_write_leaves_the_previous_bytes_and_no_scratch_file(self):
        """The destination is either the old bytes or the complete new bytes."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "artefact.json"
            fileio_module.atomic_write_text(target, "original\n")
            # Raises partway through, after the scratch file has been created.
            with self.assertRaises(TypeError):
                fileio_module.atomic_write_bytes(target, "not bytes")
            self.assertEqual(target.read_text(encoding="utf-8"), "original\n")
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()),
                             ["artefact.json"],
                             "the scratch file must not survive a failed write")

    def test_generated_markdown_has_exactly_one_trailing_newline(self):
        for path in (report_module.MARKDOWN_REPORT_PATH,
                     report_module.INVENTORY_MARKDOWN_PATH,
                     report_module.JSON_REPORT_PATH,
                     report_module.INVENTORY_JSON_PATH):
            with self.subTest(artefact=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.endswith("\n"))
                self.assertFalse(text.endswith("\n\n"),
                                 "a blank line at EOF fails git diff --check")


class TestInventoryClassificationIsHonest(unittest.TestCase):
    """An official local name under the wrong namespace is not an official term."""

    def test_official_local_name_under_a_legacy_namespace_is_not_official(self):
        legacy = {"sport": "https://www.sportschema.org/ontologies/sport#"}
        official = {"sport": OFFICIAL_MAIN_NS}
        for term in ("sport:Event", "sport:Team", "sport:eventStatus"):
            with self.subTest(term=term):
                self.assertEqual(inventory_module.classify(term, official)
                                 in ("official-iptc-class", "official-iptc-property"),
                                 True)
                self.assertEqual(inventory_module.classify(term, legacy),
                                 "official-local-name-wrong-namespace")
                self.assertEqual(inventory_module.classify(term, {}),
                                 "official-local-name-wrong-namespace")

    def test_an_invented_term_stays_invented_in_either_namespace(self):
        legacy = {"sport": "https://www.sportschema.org/ontologies/sport#"}
        for term in ("sport:Venue", "sport:homeScore", "sport:matchStatus"):
            with self.subTest(term=term):
                self.assertEqual(
                    inventory_module.classify(term, {"sport": OFFICIAL_MAIN_NS}),
                    "invented-sport-term")
                self.assertEqual(inventory_module.classify(term, legacy),
                                 "invented-sport-term")

    def test_newscode_membership_is_checked_not_assumed_from_the_prefix(self):
        # Pinned scheme, real code.
        self.assertEqual(
            inventory_module.classify("speventstatus:post-event", {}),
            "newscode-pinned-valid")
        # Pinned scheme, code that is not in it.
        self.assertEqual(
            inventory_module.classify("speventstatus:definitely-not-a-status", {}),
            "newscode-pinned-invalid")
        # Scheme upstream ships no TTL for: membership cannot be claimed.
        self.assertEqual(
            inventory_module.classify("spsocactiontype:score-change", {}),
            "newscode-unverifiable")
        # A bare prefix carries no code to check.
        self.assertEqual(inventory_module.classify("speventstatus:", {}),
                         "newscode-unverifiable")

    def test_no_category_claims_official_newscode_membership_by_prefix_alone(self):
        self.assertNotIn("official-iptc-newscode-reference",
                         inventory_module.CATEGORIES)

    def test_the_generated_inventory_is_explicit_about_the_wrong_namespace(self):
        inventory = json.loads(report_module.INVENTORY_JSON_PATH.read_text(encoding="utf-8"))
        categories = inventory["totals"]["terms_by_category"]
        self.assertIn("official-local-name-wrong-namespace", categories)
        self.assertGreater(categories["official-local-name-wrong-namespace"]["distinct_terms"], 0)
        markdown = report_module.INVENTORY_MARKDOWN_PATH.read_text(encoding="utf-8")
        self.assertIn("official-local-name-wrong-namespace", markdown)
        self.assertIn("is **not** the official term", markdown)
        # Every mapping that binds sport: to a legacy IRI must have zero terms in
        # the two official categories.
        for emitter in inventory["emitters"]:
            if emitter.get("sport_namespace_is_official"):
                continue
            with self.subTest(mapping=emitter.get("mapping")):
                for category in ("official-iptc-class", "official-iptc-property"):
                    self.assertNotIn(category, emitter.get("terms_by_category", {}))


class TestPublicSanitization(unittest.TestCase):
    """This repository is PUBLIC. Internal context must not ship in it.

    The scan covers every file this work authors — including this one — plus the
    generated reports. The only exclusion is the byte-exact vendored upstream,
    whose bytes are IPTC's and are already pinned by hash.

    The denylist cannot be spelled out here. A public test that lists the internal
    names it forbids publishes exactly what it defends, and excluding itself from
    the scan to hide that is worse: the one file guaranteed to contain internal
    strings would be the one file nobody checks. So every entry is reduced to a
    fingerprint — the character length and the SHA-256 of its casefolded,
    NFKC-normalized form — and a match reports the file path and the matched
    digest, never a recovered term.

    Fingerprints of short human-readable names are not secrets-grade; they keep
    the denylist out of a public diff, they do not make it unguessable. What they
    do guarantee is that this file no longer *is* the leak it exists to prevent.
    """

    #: Fingerprints of internal task identifiers, people, private roadmap names,
    #: the local home-directory path, and the internal source-tree directory
    #: prefix. Length plus digest only — nothing here is reversible by reading it.
    #: Ordered by digest, so the order carries no information about which entry is
    #: which. Spaced, hyphenated and path-separated spellings of one term
    #: normalize to the same digest, so one entry covers all of them.
    FORBIDDEN_FINGERPRINTS = (
        (21, "12f493c4f474d094afbe47a3aaec5c2c11edcc77f573d0a0c670e2c5f84039a0"),
        (6, "1957b9981fc9cfa67abff7eb73045b55f99b9673f7637e138fd3f8c7a1313e94"),
        (9, "28755128020fd39d3cd422df776a999b638285e0827c9f48851b0cc8b13f5e1c"),
        (12, "30a84f554f25e84694d08aca17f493511433b5f431cce8a3055bf90f59cee3cb"),
        (22, "7ff8624ff15b502d6841c98aa2cc8279dca346b85e504b61df3bffdae04fd3a9"),
        (6, "8d4321d936320802386311d254c4af52951abb880b47fb077edf3d89c150b289"),
        (14, "9e65bcccc4375983bfa6f414bdd0fd31eac3cba569606aabc4819db46d870c97"),
        (14, "9e6864835aee03646addb94577e4f1457add4641a670de96df7854c90e4aafde"),
        (3, "a543997d84f12798350c09bdef2cdb171bf41ed3e4a5f808af2feb0c56263009"),
        (5, "b2a2af3b9e82592079d3bc5b94c1a726a3c3259a542521065d0a55597f2e4d98"),
        (7, "c0d67255424148d869b8c00b4e7c27645b97147e36aaf9538a661a3d87883098"),
        (10, "da362e2d0405d48834c1f637b564f67a20a417b6a7833738d43731506b1ca5b6"),
        (13, "da8552b715c7c0153f1483a2bcc1c9655ac773d975bb4de113755c31eac4c4ac"),
        (25, "dc8749fd32a4ba1c17d2975222588ea611206487e111010d5d7048d387e36507"),
        (10, "f270ab8fb716bf60234eefa6e3aac8f4d2ad3d27e0ee51f43419505302c2c3ab"),
    )

    #: The longest fingerprinted term is three tokens. Four leaves margin without
    #: letting a candidate span wander far across unrelated prose.
    MAX_SPAN_TOKENS = 4

    @staticmethod
    def normalize(text: str) -> str:
        """Casefold, and collapse every non-alphanumeric run to a single space.

        This is what makes `Sport Schema`, `sport-schema`, `sport_schema` and a
        line-wrapped `sport\\nschema` one digest instead of four, and what turns a
        filesystem path into ordinary tokens.
        """
        folded = unicodedata.normalize("NFKC", text).casefold()
        return " ".join("".join(c if c.isalnum() else " " for c in folded).split())

    @classmethod
    def fingerprint(cls, term: str) -> tuple[int, str]:
        normalized = cls.normalize(term)
        return len(normalized), hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @classmethod
    def scan_text(cls, text: str, fingerprints) -> list[str]:
        """Digests of the fingerprinted terms present in `text`, sorted.

        Deterministic by construction: the text is tokenized once, every
        contiguous 1-to-`MAX_SPAN_TOKENS` span is normalized and hashed, and the
        result is the sorted set of digests that matched. The recorded length is
        the prefilter — a span whose length matches no entry cannot match any
        entry — so no plaintext is needed to run the scan, and none is returned.
        """
        lengths = {length for length, _ in fingerprints}
        wanted = {digest for _, digest in fingerprints}
        tokens = cls.normalize(text).split()
        found = set()
        for start in range(len(tokens)):
            span = ""
            for token in tokens[start:start + cls.MAX_SPAN_TOKENS]:
                span = f"{span} {token}" if span else token
                if len(span) not in lengths:
                    continue
                digest = hashlib.sha256(span.encode("utf-8")).hexdigest()
                if digest in wanted:
                    found.add(digest)
        return sorted(found)

    #: Everything this work authors. Vendored upstream bytes are excluded by
    #: listing only the Machina-authored files inside the reference directory.
    def scanned_files(self) -> list[Path]:
        found: list[Path] = []
        for directory in ("tools/iptc", "docs/iptc", "tests"):
            for path in sorted((REPO_ROOT / directory).rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    found.append(path)
        found.extend([
            REPO_ROOT / "tools" / "__init__.py",
            REPO_ROOT / "docs" / "rfcs" / "001-machina-iptc-sport-schema-profile.md",
            REPO_ROOT / ".github" / "workflows" / "validate-iptc-sport-schema.yml",
            REPO_ROOT / ".gitattributes",
            REPO_ROOT / ".gitignore",
            REPO_ROOT / "requirements-iptc-validator.txt",
            context_module.CONTEXT_PATH,
            REFERENCE_ROOT / "LICENSE.md",
            REFERENCE_ROOT / "UPSTREAM.md",
            REFERENCE_ROOT / "upstream-commit.json",
        ])
        return [p for p in found if p.is_file()]

    def test_no_internal_identifier_or_roadmap_name_is_published(self):
        offenders = []
        for path in self.scanned_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for digest in self.scan_text(text, self.FORBIDDEN_FINGERPRINTS):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {digest}")
        self.assertEqual(offenders, [], "internal content in a PUBLIC repository")

    def test_the_scan_actually_covers_the_generated_reports_the_rfc_and_itself(self):
        """A sanitization test that scans nothing would pass trivially."""
        scanned = {p.relative_to(REPO_ROOT).as_posix() for p in self.scanned_files()}
        for required in (
            "docs/iptc/INVENTORY.md", "docs/iptc/inventory.json",
            "docs/iptc/BASELINE-AUDIT.md", "docs/iptc/baseline-audit.json",
            "docs/rfcs/001-machina-iptc-sport-schema-profile.md",
            "tools/iptc/inventory.py", "tools/iptc/report.py",
            "tools/iptc/validate.py", "tools/iptc/profile.py",
            "tools/iptc/fixtures/provenance.json",
            "tools/iptc/rules/provider-leak-terms.json",
            "agent-templates/iptc-mappings/contexts/iptc-sport-schema-1.1.context.jsonld",
            # Root-level authored files are as public as the rest of the diff.
            ".gitattributes", ".gitignore", "requirements-iptc-validator.txt",
            # The denylist holder is no longer exempt from the denylist.
            Path(__file__).resolve().relative_to(REPO_ROOT).as_posix(),
        ):
            self.assertIn(required, scanned)
        self.assertGreater(len(scanned), 40)

    def test_the_only_exclusion_is_the_byte_exact_vendored_upstream(self):
        """The three Machina-authored reference files are scanned; the pin is not."""
        under_reference = [p for p in self.scanned_files()
                           if REFERENCE_ROOT in p.parents]
        self.assertEqual(sorted(p.name for p in under_reference),
                         sorted(MACHINA_AUTHORED_REFERENCE_FILES))

    def test_the_scan_would_catch_a_regression(self):
        """Guard the guard, without publishing anything worth guarding.

        The canary is invented here and is not internal to anything; its digest is
        computed at runtime and asserted absent from the committed table, so the
        matcher is proved end-to-end without a real value appearing in this file.
        """
        canary = self.fingerprint("Synthetic Canary Marker")
        self.assertNotIn(canary[1], [d for _, d in self.FORBIDDEN_FINGERPRINTS],
                         "the canary must be synthetic, not a real entry")
        for spelling in ("Synthetic Canary Marker",
                         "synthetic-canary-marker",
                         "SYNTHETIC_canary/marker",
                         "prose before synthetic\ncanary  marker and prose after"):
            with self.subTest(spelling=spelling):
                self.assertEqual(self.scan_text(spelling, (canary,)), [canary[1]])
        for clean in ("synthetic canary", "canary marker", "nothing to declare"):
            with self.subTest(clean=clean):
                self.assertEqual(self.scan_text(clean, (canary,)), [])

    def test_the_denylist_is_hash_only_and_has_not_been_gutted(self):
        table = self.FORBIDDEN_FINGERPRINTS
        digests = [digest for _, digest in table]
        self.assertEqual(len(digests), 15, "an entry left the denylist")
        self.assertEqual(len(set(digests)), len(digests), "duplicate fingerprint")
        self.assertEqual(digests, sorted(digests), "keep the table digest-ordered")
        for length, digest in table:
            with self.subTest(digest=digest):
                # Two committed fields, both non-reversible: a length and a digest.
                self.assertIsInstance(length, int)
                self.assertRegex(digest, r"^[0-9a-f]{64}$")
                self.assertGreaterEqual(length, 3,
                                        "a 1-2 character entry would match everywhere")

    def test_the_public_profile_states_the_boundary_without_internal_context(self):
        rfc = (REPO_ROOT / "docs" / "rfcs"
               / "001-machina-iptc-sport-schema-profile.md").read_text(encoding="utf-8")
        self.assertIn("canonical domain model", rfc)
        self.assertIn("output projection", rfc)
        inventory = json.loads(report_module.INVENTORY_JSON_PATH.read_text(encoding="utf-8"))
        boundary = inventory["scope_boundary"]
        self.assertIn("authoritative", boundary["canonical_model"])
        self.assertIn("output projection", boundary["canonical_model"])
        self.assertIn("foundation-only and output-neutral", boundary["read_this_way"])
        self.assertNotIn("assignee_note", boundary)
        # The internal tracker key is checked by fingerprint over the whole
        # published object: naming it here would reintroduce the plaintext this
        # class exists to keep out of a public file.
        self.assertEqual(
            self.scan_text(json.dumps(boundary, sort_keys=True),
                           self.FORBIDDEN_FINGERPRINTS),
            [], "the published scope boundary carries internal context")


class TestBaselineIsMeasuredNotAssumed(unittest.TestCase):
    """The baseline is expected to FAIL. These tests pin down how it fails."""

    def test_no_baseline_fixture_conforms(self):
        results = run()
        self.assertEqual(len(results["baseline"]), 14)
        for item in results["baseline"]:
            with self.subTest(fixture=item.fixture):
                self.assertFalse(item.conforms)

    def test_legacy_namespace_produces_a_vacuous_shacl_pass_not_a_real_one(self):
        """The most dangerous false positive in the whole audit."""
        result = validate("tools/iptc/fixtures/baseline/api-football-soccer-event.json")
        detail = result.layers["official_shacl"]["detail"]
        self.assertTrue(detail["conforms"], "pyshacl itself reports conforms")
        self.assertEqual(detail["official_class_instances"], 0)
        self.assertTrue(detail["vacuous"])
        self.assertFalse(result.layers["official_shacl"]["ok"],
                         "a vacuous pass must not be recorded as a layer-2 pass")
        self.assertIn("sport-namespace-not-official", codes(result))

    def test_every_required_coverage_area_has_a_fixture(self):
        provenance = report_module.load_provenance()
        present = {entry["fixture"] for entry in provenance["baseline"]}
        for required in (
            "api-football-soccer-event", "api-football-actions",
            "api-football-team-stats", "api-football-player-stats",
            "sportradar-soccer-event", "sportradar-soccer-timeline",
            "stats-perform-opta-event", "stats-perform-opta-timeline",
            "sportradar-tennis-event", "sportradar-nfl-event",
            "sportradar-mlb-event", "american-football-event", "custom-event",
        ):
            self.assertIn(required, present)

    def test_every_fixture_declares_its_provenance_and_class(self):
        provenance = report_module.load_provenance()
        for entry in provenance["baseline"]:
            with self.subTest(fixture=entry["fixture"]):
                self.assertIn(entry["class"],
                              {"repository-artifact", "mapping-contract-synthetic"})
                self.assertTrue(entry.get("source"))
                self.assertTrue(entry.get("transformation"))
                self.assertTrue(entry.get("emitted_by"))
                self.assertTrue(report_module.resolve(entry).is_file())
                if entry["class"] == "mapping-contract-synthetic":
                    self.assertTrue(
                        entry.get("limitation"),
                        "a synthetic fixture must record its limitation explicitly")

    def test_repository_artifact_fixtures_still_match_their_source(self):
        """A 'verbatim copy' claim has to stay true."""
        for fixture, source in (
            ("api-football-soccer-event", "agent-templates/iptc-mappings/example-apifootball-output.json"),
            ("api-football-soccer-event-nulls", "agent-templates/iptc-mappings/example-iptc-event.json"),
            ("custom-event", "agent-templates/iptc-mappings/example-any-event-output.json"),
        ):
            with self.subTest(fixture=fixture):
                copied = (FIXTURES / "baseline" / f"{fixture}.json").read_bytes()
                original = (REPO_ROOT / source).read_bytes()
                self.assertEqual(copied, original)

    def test_unwrapped_fixture_matches_its_source_envelope_content(self):
        wrapped = json.loads((REPO_ROOT / "agent-templates" / "iptc-mappings"
                              / "example-sportradar-output.json").read_text(encoding="utf-8"))
        unwrapped = json.loads((FIXTURES / "baseline" / "sportradar-soccer-event.json")
                               .read_text(encoding="utf-8"))
        self.assertEqual(list(wrapped), ["sport-schema-event"])
        self.assertEqual(wrapped["sport-schema-event"], unwrapped)

    def test_unverifiable_codes_are_never_promoted_to_valid_and_fail_closed(self):
        result = validate("tools/iptc/fixtures/baseline/stats-perform-opta-timeline.json")
        detail = result.layers["controlled_vocabulary"]["detail"]
        self.assertGreater(len(detail["unverifiable"]), 0)
        for item in detail["unverifiable"]:
            self.assertEqual(item["scheme"], "spsocaction")
            self.assertIn("cannot be checked offline", item["reason"])
        # The category stays distinct...
        self.assertEqual(result.counters["invalid_newscode_values"], 0,
                         "unverifiable is not invalid")
        self.assertEqual(detail["invalid"], [])
        self.assertEqual(detail["undeclared_prefix"], [])
        # ...but missing evidence does not pass. The profile requires provable
        # membership in a pinned vocabulary.
        self.assertFalse(result.layers["controlled_vocabulary"]["ok"],
                         "layer 4 must fail closed on an unverifiable code")
        self.assertFalse(result.conforms)

    def test_undeclared_prefix_value_counts_as_an_invalid_code(self):
        """The sportradar timeline emits `spsocaction:...` with no such prefix bound."""
        result = validate("tools/iptc/fixtures/baseline/sportradar-soccer-timeline.json")
        undeclared = result.layers["controlled_vocabulary"]["detail"]["undeclared_prefix"]
        self.assertGreater(len(undeclared), 0)
        self.assertGreater(result.counters["invalid_newscode_values"], 0)


class TestReportReproducibility(unittest.TestCase):
    """CI asserts the recorded failure report is reproducible, not that it passes."""

    def test_checked_in_reports_are_up_to_date(self):
        report = report_module.build_report(run())
        expected_json = json.dumps(report, indent=2, sort_keys=True) + "\n"
        self.assertEqual(
            report_module.JSON_REPORT_PATH.read_text(encoding="utf-8"),
            expected_json,
            "docs/iptc/baseline-audit.json is stale. Run: python3 -m tools.iptc",
        )
        self.assertEqual(
            report_module.MARKDOWN_REPORT_PATH.read_text(encoding="utf-8"),
            report_module.render_markdown(report),
            "docs/iptc/BASELINE-AUDIT.md is stale. Run: python3 -m tools.iptc",
        )

    def test_report_is_stable_across_two_runs(self):
        first = json.dumps(report_module.build_report(run()), indent=2, sort_keys=True)
        second = json.dumps(report_module.build_report(run()), indent=2, sort_keys=True)
        self.assertEqual(first, second)

    def test_report_carries_the_pin_and_the_no_tag_warning(self):
        report = json.loads(report_module.JSON_REPORT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(report["pin"]["upstream_commit"], UPSTREAM_COMMIT)
        self.assertEqual(report["pin"]["target_version"], TARGET_VERSION)
        self.assertIn("no 1.1 tag", report["pin"]["upstream_ref_note"])

    def test_markdown_states_the_baseline_is_expected_to_fail(self):
        markdown = report_module.MARKDOWN_REPORT_PATH.read_text(encoding="utf-8")
        self.assertIn("expected to fail", markdown)
        self.assertIn("VACUOUS", markdown)
        self.assertIn("MISSING EVIDENCE", markdown)


class TestArtifactOwnership(unittest.TestCase):
    """The approved paths are part of the contract, not an implementation detail."""

    def test_vendored_reference_lives_beside_the_mappings(self):
        expected = (REPO_ROOT / "agent-templates" / "iptc-mappings" / "references"
                    / "iptc-sport-schema-1.1")
        self.assertEqual(REFERENCE_ROOT, expected)
        self.assertTrue((REFERENCE_ROOT / "UPSTREAM.md").is_file())
        self.assertTrue((REFERENCE_ROOT / "LICENSE.md").is_file())
        self.assertTrue((REFERENCE_ROOT / "upstream-commit.json").is_file())
        self.assertTrue((REFERENCE_ROOT / "ontologies").is_dir())
        self.assertTrue((REFERENCE_ROOT / "vocabularies").is_dir())

    def test_official_shacl_directory_is_named_shacl(self):
        self.assertTrue(SHACL_PATH.is_file())
        self.assertEqual(SHACL_PATH.parent.name, "shacl")
        self.assertFalse((REFERENCE_ROOT / "shapes").exists(),
                         "the old shapes/ directory must not be left behind")

    def test_shared_context_lives_under_the_mappings_contexts_path(self):
        expected = (REPO_ROOT / "agent-templates" / "iptc-mappings" / "contexts"
                    / "iptc-sport-schema-1.1.context.jsonld")
        self.assertEqual(context_module.CONTEXT_PATH, expected)
        self.assertTrue(expected.is_file())

    def test_no_duplicate_vendored_upstream_tree(self):
        """The upstream tree was moved, not copied. One tree, one set of hashes."""
        strays = [
            REPO_ROOT / "tools" / "iptc" / "reference",
            REPO_ROOT / "tools" / "iptc" / "contexts",
        ]
        for path in strays:
            self.assertFalse(path.exists(), f"{path} would be a second copy")

    def test_operator_commands_exist_and_are_importable(self):
        import importlib

        for name in ("validate_graph", "validate_terms", "validate_vocabularies",
                     "extract_mapping_fixture"):
            with self.subTest(command=name):
                path = reference_module.PACKAGE_ROOT / f"{name}.py"
                self.assertTrue(path.is_file(), f"tools/iptc/{name}.py is missing")
                module = importlib.import_module(f"tools.iptc.{name}")
                self.assertTrue(callable(module.main))
        self.assertTrue((reference_module.PACKAGE_ROOT / "README.md").is_file())

    def test_readme_documents_the_deterministic_baseline_command(self):
        readme = (reference_module.PACKAGE_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("python3 -m tools.iptc --check", readme)
        self.assertIn("python3 -m tools.iptc --verify-pin", readme)
        for name in ("validate_graph.py", "validate_terms.py",
                     "validate_vocabularies.py", "extract_mapping_fixture.py"):
            self.assertIn(name, readme)

    def test_pinned_dependencies_are_exact(self):
        requirements = (REPO_ROOT / "requirements-iptc-validator.txt"
                        ).read_text(encoding="utf-8")
        for package in ("rdflib", "pyshacl", "owlrl"):
            self.assertRegex(requirements, rf"(?m)^{package}==\d")
        for line in requirements.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-r "):
                continue
            self.assertIn("==", line, f"unpinned requirement: {line}")

    def test_the_harness_dependencies_do_not_bloat_the_base_validator(self):
        """The IPTC pins are scoped, so the agent-builder workflow is unaffected.

        `validate-machina-agent-builder.yml` installs requirements-validator.txt and
        nothing else. If rdflib/pyshacl leaked back into that file, that pre-existing
        job would install this harness's whole tree — and one of those distributions
        shipping a top-level `tests` package would shadow its own test module.
        """
        base = (REPO_ROOT / "requirements-validator.txt").read_text(encoding="utf-8")
        self.assertEqual(base, "PyYAML==6.0.2\nmarkdown-it-py==3.0.0\n",
                         "requirements-validator.txt must stay the untouched base file")
        scoped = (REPO_ROOT / "requirements-iptc-validator.txt").read_text(encoding="utf-8")
        self.assertRegex(scoped, r"(?m)^-r requirements-validator\.txt$",
                         "the scoped file must include the base pins, not restate them")
        for package in ("rdflib", "pyshacl", "owlrl", "prettytable", "html5rdf"):
            with self.subTest(package=package):
                self.assertNotRegex(base, rf"(?m)^{package}==")

    @staticmethod
    def workflow_run_commands(workflow: str) -> list[str]:
        """Every shell line the workflow actually executes.

        Scanning the raw file would also match the header prose and the comment that
        explains *why* the module form is not used, so a comment could fail the test
        or — worse — a real `-m unittest` step could hide behind one.
        """
        commands: list[str] = []
        block_indent: int | None = None
        for raw in workflow.splitlines():
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

    def test_ci_installs_the_scoped_requirements_and_runs_the_tests_directly(self):
        workflow = (REPO_ROOT / ".github" / "workflows"
                    / "validate-iptc-sport-schema.yml").read_text(encoding="utf-8")
        commands = self.workflow_run_commands(workflow)
        self.assertIn("python -m pip install -r requirements-iptc-validator.txt", commands)
        # The module form is shadowable; the file form is not. See this file's docstring.
        self.assertIn("python tests/test_iptc_validation_harness.py -v", commands)
        for command in commands:
            with self.subTest(command=command):
                self.assertNotIn("-m unittest", command)

        agent_builder = (REPO_ROOT / ".github" / "workflows"
                         / "validate-machina-agent-builder.yml").read_text(encoding="utf-8")
        self.assertNotIn("requirements-iptc-validator.txt", agent_builder)

    def test_the_workflow_command_scan_reads_steps_and_not_comments(self):
        """Guard the guard: the parser must find real steps and ignore prose."""
        sample = (
            "# a comment mentioning python -m unittest tests.foo\n"
            "jobs:\n"
            "  validate:\n"
            "    steps:\n"
            "      - run: python -m pip install -r requirements-iptc-validator.txt\n"
            "      # explanatory comment: not `-m unittest tests.foo`\n"
            "      - name: Harness unit tests\n"
            "        run: python tests/test_iptc_validation_harness.py -v\n"
            "      - run: |\n"
            "          if [ -n \"$(git status --porcelain)\" ]; then\n"
            "            exit 1\n"
            "          fi\n"
        )
        self.assertEqual(self.workflow_run_commands(sample), [
            "python -m pip install -r requirements-iptc-validator.txt",
            "python tests/test_iptc_validation_harness.py -v",
            'if [ -n "$(git status --porcelain)" ]; then',
            "exit 1",
            "fi",
        ])
        # And it does catch a real shadowable step.
        self.assertIn("python -m unittest tests.x", self.workflow_run_commands(
            "    steps:\n      - run: python -m unittest tests.x\n"))


class TestOperatorCommands(unittest.TestCase):
    """The wrappers must agree with the harness, not re-implement it."""

    def test_validate_graph_passes_the_conforming_fixture_and_fails_a_baseline_one(self):
        from tools.iptc import validate_graph

        conforming = "tools/iptc/fixtures/conforming/machina-profile-conforming-minimal.json"
        baseline = "tools/iptc/fixtures/baseline/custom-event.json"
        self.assertEqual(validate_graph.main([conforming]), 0)
        self.assertEqual(validate_graph.main([baseline]), 1)

    def test_validate_terms_gate_agrees_with_the_baseline_report(self):
        from tools.iptc import validate_terms

        self.assertEqual(validate_terms.main([
            "tools/iptc/fixtures/conforming/machina-profile-conforming-minimal.json"]), 0)
        self.assertEqual(validate_terms.main([
            "tools/iptc/fixtures/negative/invented-sport-term.json"]), 1)

    def test_validate_vocabularies_fails_closed_on_invalid_and_on_unverifiable(self):
        from tools.iptc import validate_vocabularies

        # An invalid code fails, obviously.
        self.assertEqual(validate_vocabularies.main([
            "tools/iptc/fixtures/negative/invalid-newscode.json"]), 1)
        # And so does an unverifiable one. This fixture's only vocabulary findings
        # are `unverifiable` (spsocaction has no pinned TTL at this commit), so it
        # is the exact case that used to exit 0 while reporting missing evidence.
        self.assertEqual(validate_vocabularies.main([
            "tools/iptc/fixtures/baseline/stats-perform-opta-timeline.json"]), 1)
        # A document whose every code IS in a pinned scheme still passes.
        self.assertEqual(validate_vocabularies.main([
            "tools/iptc/fixtures/conforming/machina-profile-conforming-minimal.json"]), 0)

    def test_extract_mapping_fixture_refuses_to_invent_a_fixture(self):
        from tools.iptc import extract_mapping_fixture

        keys = extract_mapping_fixture.emitted_keys(
            REPO_ROOT / "connectors" / "sportradar-mlb" / "mappings" / "iptc-sport-event.yml")
        self.assertIn("iptc-sportradar-event-mlb-mapping", keys)
        emitted = keys["iptc-sportradar-event-mlb-mapping"]
        self.assertIn("sport:doubleHeader", emitted)
        self.assertIn("@context", emitted)
        # --mapping reports the contract and writes nothing.
        self.assertEqual(extract_mapping_fixture.main([
            "--mapping",
            "connectors/sportradar-mlb/mappings/iptc-sport-event.yml"]), 0)

    def test_extract_mapping_fixture_lists_the_artifacts_the_fixtures_came_from(self):
        from tools.iptc import extract_mapping_fixture

        listed = {str(p.relative_to(REPO_ROOT))
                  for p in extract_mapping_fixture.list_artifacts()}
        for source in ("agent-templates/iptc-mappings/example-apifootball-output.json",
                       "agent-templates/iptc-mappings/example-sportradar-output.json",
                       "agent-templates/iptc-mappings/example-any-event-output.json",
                       "agent-templates/iptc-mappings/example-iptc-event.json"):
            self.assertIn(source, listed)


class TestOutputNeutrality(unittest.TestCase):
    """PR 1 must change nothing a consumer can observe."""

    def test_no_mapping_or_workflow_yaml_references_the_harness(self):
        offenders = []
        for directory in ("agent-templates", "connectors", "skills", "mkn-constructor"):
            root = REPO_ROOT / directory
            if not root.is_dir():
                continue
            for path in root.rglob("*.yml"):
                text = path.read_text(encoding="utf-8", errors="replace")
                if "tools/iptc" in text or "tools.iptc" in text:
                    offenders.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(offenders, [],
                         "PR 1 is output-neutral: no mapping or workflow may call the harness")

    def test_no_iptc_mapping_install_manifest_gained_a_dataset(self):
        """The vendored reference and context must not be installed as templates."""
        install = (REPO_ROOT / "agent-templates" / "iptc-mappings" / "_install.yml"
                   ).read_text(encoding="utf-8")
        for token in ("references/", "contexts/", "iptc-sport-schema-1.1"):
            self.assertNotIn(token, install)

    def test_harness_imports_no_network_module_and_reads_no_environment(self):
        """A real check, not a substring grep: parse the AST.

        The harness's offline guarantee is what makes a pinned conformance result
        durable, so it is worth asserting structurally rather than by looking for
        words that also appear in prose.
        """
        import ast

        banned_modules = {"requests", "httpx", "socket", "urllib", "urllib.request",
                          "http", "http.client", "ftplib", "subprocess"}
        for path in sorted(reference_module.PACKAGE_ROOT.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        with self.subTest(module=path.name, imported=alias.name):
                            self.assertNotIn(alias.name.split(".")[0], banned_modules)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    with self.subTest(module=path.name, imported=node.module):
                        self.assertNotIn(node.module.split(".")[0], banned_modules)
                elif isinstance(node, ast.Attribute) and node.attr in ("environ", "getenv"):
                    self.fail(f"{path.name} reads the environment: no credential may "
                              f"influence a conformance result")


if __name__ == "__main__":
    unittest.main(verbosity=2)
