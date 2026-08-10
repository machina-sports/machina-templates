"""Tests for the Machina Sports Schema canonical contract (PR 2, tasks A1-A6).

Run from the repository root:

    python3 tests/test_iptc_canonical_serializer.py -v

Run the file directly, for the same reason as
``tests/test_iptc_validation_harness.py``: ``tests/`` is a namespace directory
with no ``__init__.py``, so ``-m unittest tests.<module>`` can be shadowed by an
installed distribution that ships a top-level regular ``tests`` package.

What is being defended here:

1. **The version claim is honest.** The profile minor bump and both schema
   versions are asserted against the RFCs that authorise them, so a version
   string can never drift away from its written contract.
2. **Fabrication is caught at the adapter boundary.** ``validate_observation``
   is the only place a null, an empty string, a placeholder, a short participant
   list or an invented statistic can be stopped before it reaches a serializer.
3. **Identity is a visibly-marked surrogate.** The resolver is provider-scoped,
   deterministic, collision-free across fixtures, and leaks no provider token
   into the identifier it mints.
4. **The allowlist is reproducible from the pin**, not hand-maintained.
5. **Capabilities fail closed.** An unrecognised capability name is never read as
   satisfied.
6. **No NewsCode is mapped into a scheme the pin cannot check.** Every mapped
   code is asserted present in a pinned SKOS scheme, which is what keeps
   ``spsocactiontype:`` out of the tables by construction rather than by memory.
"""

from __future__ import annotations

import ast
import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.iptc import canonical  # noqa: E402
from tools.iptc import profile as profile_module  # noqa: E402
from tools.iptc.canonical import export_official_terms  # noqa: E402
from tools.iptc.canonical.capabilities import (  # noqa: E402
    ALL_CAPABILITIES,
    TIER_OPTIONAL,
    TIER_ORDER,
    TIER_REQUIRED,
    capability_report,
    check_compatibility,
)
from tools.iptc.canonical.ids import SURROGATE_MARKER, surrogate_resolver  # noqa: E402
from tools.iptc.canonical.observation import (  # noqa: E402
    PLACEHOLDERS,
    validate_observation,
)
from tools.iptc.canonical import vocab  # noqa: E402
from tools.iptc.reference import NEWSCODE_STEM, load_reference  # noqa: E402

#: The smallest observation that is genuinely valid: two participants, every
#: required field, nothing optional. Every negative case below is this document
#: with exactly one thing broken, so a failure names the rule it broke.
MINIMAL = {
    "schema_version": "canonical-observation/1",
    "observation": {
        "provider": {"namespace": "api-football", "family": "licensed"},
        "observed_at": "2026-03-01T22:05:00+00:00",
        "sport": {"medtop": "20001065", "key": "soccer"},
        "competition": {
            "provider_id": "39",
            "name": "Synthetic Premier Division",
            "type": "recurring-competition",
        },
        "event": {
            "provider_id": "9001",
            "label": "H vs A",
            "start_time": "2026-03-01T20:00:00+00:00",
            "status": "closed",
        },
        "participants": [
            {"kind": "team", "provider_id": "9011", "name": "H",
             "alignment": "home", "score": "2"},
            {"kind": "team", "provider_id": "9012", "name": "A",
             "alignment": "away", "score": "1"},
        ],
    },
}


class TestVersionClaims(unittest.TestCase):
    """A1 — the profile version and the RFC that authorises it move together."""

    def test_profile_version_is_the_minor_bump(self):
        self.assertEqual(canonical.PROFILE_VERSION, "machina-iptc-profile/1.1")
        self.assertEqual(canonical.SCHEMA_VERSION, "canonical-observation/1")
        self.assertEqual(canonical.MACHINA_SCHEMA_VERSION, "machina-sports-schema/1")
        self.assertEqual(canonical.SERIALIZER_VERSION, "1")

    def test_rfc_001_records_the_bump_and_rfc_002_exists(self):
        rfc1 = (REPO_ROOT / "docs/rfcs/001-machina-iptc-sport-schema-profile.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("machina-iptc-profile/1.1", rfc1)
        self.assertIn("machina:ObservationProvenance", rfc1)
        rfc2 = REPO_ROOT / "docs/rfcs/002-machina-sports-schema-canonical-observation.md"
        self.assertTrue(rfc2.is_file())
        self.assertIn("canonical-observation/1", rfc2.read_text(encoding="utf-8"))


class TestObservationValidation(unittest.TestCase):
    """A2 — fabrication is caught at the adapter boundary or it is not caught."""

    def test_minimal_observation_is_valid(self):
        self.assertEqual(validate_observation(MINIMAL), [])

    def test_wrong_schema_version_is_rejected(self):
        bad = copy.deepcopy(MINIMAL)
        bad["schema_version"] = "canonical-observation/2"
        self.assertIn("schema_version", " ".join(validate_observation(bad)))

    def test_every_required_field_is_required(self):
        """One subtest per required field, so a regression names the field."""
        required = [
            ("provider", "namespace"),
            ("observed_at",),
            ("sport", "medtop"),
            ("competition", "provider_id"),
            ("event", "provider_id"),
            ("event", "start_time"),
            ("event", "status"),
        ]
        for path in required:
            with self.subTest(field=".".join(path)):
                bad = copy.deepcopy(MINIMAL)
                node = bad["observation"]
                for key in path[:-1]:
                    node = node[key]
                node.pop(path[-1])
                errors = validate_observation(bad)
                self.assertIn(
                    "observation." + ".".join(path) + ": required field is missing", errors
                )

    def test_one_participant_is_rejected(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["participants"] = bad["observation"]["participants"][:1]
        self.assertIn("observation.participants: need at least 2", validate_observation(bad))

    def test_null_and_placeholder_are_rejected_at_the_boundary(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["site"] = {
            "provider_id": "9101", "name": "Unknown Venue", "city": None,
        }
        errors = " ".join(validate_observation(bad))
        self.assertIn("placeholder", errors)
        self.assertIn("null", errors)

    def test_empty_string_is_rejected_as_its_own_error(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["event"]["label"] = ""
        self.assertIn("empty string", " ".join(validate_observation(bad)))

    def test_placeholder_set_matches_the_profile_the_harness_enforces(self):
        """Vendoring forces the set to be duplicated; this stops it diverging.

        ``observation.py`` is copied byte-exact into a package that cannot import
        ``tools.iptc.profile``, so it carries its own copy. Two copies of one
        list drift; the only question is when. This is the test that notices.
        """
        self.assertEqual(PLACEHOLDERS, frozenset(profile_module.PLACEHOLDER_VALUES))

    def test_provider_payload_under_raw_is_not_placeholder_scanned(self):
        """``raw`` is verbatim provider bytes and never reaches the graph.

        A real payload is full of nulls. Scanning it would make every genuine
        observation invalid, which would end with adapters stripping ``raw`` and
        the provenance trail disappearing.
        """
        ok = copy.deepcopy(MINIMAL)
        ok["observation"]["raw"] = {"venue": None, "status_text": "TBD", "note": ""}
        self.assertEqual(validate_observation(ok), [])

    def test_naive_datetime_is_rejected(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["event"]["start_time"] = "2026-03-01T20:00:00"
        self.assertIn("observation.event.start_time", " ".join(validate_observation(bad)))

    def test_impossible_datetime_is_rejected(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["observed_at"] = "2026-02-30T25:00:00+00:00"
        self.assertIn("observation.observed_at", " ".join(validate_observation(bad)))

    def test_a_date_without_a_time_is_not_a_datetime(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["event"]["start_time"] = "2026-03-01"
        self.assertIn("observation.event.start_time", " ".join(validate_observation(bad)))

    def test_unknown_statistic_curie_is_rejected(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["participants"][0]["statistics"] = {"spsocstat:machinaVibes": "9"}
        self.assertIn("spsocstat:machinaVibes", " ".join(validate_observation(bad)))

    def test_known_statistic_curie_is_accepted(self):
        ok = copy.deepcopy(MINIMAL)
        ok["observation"]["participants"][0]["statistics"] = {"spsocstat:shotsTotal": "14"}
        self.assertEqual(validate_observation(ok), [])

    def test_a_bare_statistic_name_without_a_prefix_is_rejected(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["participants"][0]["statistics"] = {"shotsTotal": "14"}
        self.assertIn("shotsTotal", " ".join(validate_observation(bad)))

    def test_a_numeric_statistic_is_rejected_because_the_shapes_say_string(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["participants"][0]["statistics"] = {"spsocstat:shotsTotal": 14}
        self.assertIn("must be a string", " ".join(validate_observation(bad)))

    def test_malformed_rights_block_is_rejected(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["rights"] = {"data_class": "public-non-commercial"}
        errors = " ".join(validate_observation(bad))
        self.assertIn("observation.rights.prototype_only", errors)
        self.assertIn("observation.rights.commercial_use", errors)

    def test_rights_flags_must_be_booleans_not_truthy_strings(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["rights"] = {
            "data_class": "public-non-commercial",
            "prototype_only": "true",
            "commercial_use": "false",
        }
        self.assertIn("must be a boolean", " ".join(validate_observation(bad)))

    def test_malformed_adapter_provenance_is_rejected(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["adapter"] = {"name": "sports_skills.canonical.adapters.football"}
        self.assertIn("observation.adapter.version", " ".join(validate_observation(bad)))

    def test_participant_missing_its_own_required_fields_is_rejected(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["participants"][1].pop("name")
        self.assertIn(
            "observation.participants[1].name: required field is missing",
            validate_observation(bad),
        )

    def test_a_team_participant_without_an_alignment_is_rejected(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["participants"][0].pop("alignment")
        self.assertIn(
            "observation.participants[0].alignment: required field is missing",
            validate_observation(bad),
        )

    def test_an_unknown_participant_kind_is_rejected(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["participants"][0]["kind"] = "mascot"
        self.assertIn("mascot", " ".join(validate_observation(bad)))

    def test_every_error_is_reported_not_just_the_first(self):
        """A validator that stops at the first error makes fixing an adapter a
        game of whack-a-mole, and reviewers stop running it."""
        bad = copy.deepcopy(MINIMAL)
        bad["observation"].pop("observed_at")
        bad["observation"]["event"].pop("status")
        bad["observation"]["participants"] = bad["observation"]["participants"][:1]
        self.assertEqual(len(validate_observation(bad)), 3, validate_observation(bad))

    def test_validation_never_mutates_the_document(self):
        """No silent defaults: a validator that repairs hides the adapter bug."""
        document = copy.deepcopy(MINIMAL)
        before = json.dumps(document, sort_keys=True)
        validate_observation(document)
        self.assertEqual(json.dumps(document, sort_keys=True), before)

    def test_a_non_dict_document_is_an_error_and_not_an_exception(self):
        self.assertNotEqual(validate_observation([]), [])


def rich_observation():
    """MINIMAL plus everything the live and advanced tiers ask for."""
    document = copy.deepcopy(MINIMAL)
    observation = document["observation"]
    observation["event"]["clock"] = {"minute": "90", "period": "2"}
    observation["participants"][0]["outcome"] = "win"
    observation["participants"][1]["outcome"] = "loss"
    observation["participants"].append({
        "kind": "individual", "provider_id": "9021", "name": "Synthetic Scorer",
        "team_provider_id": "9011", "player_status": "starter", "position": "forward",
        "statistics": {"spsocstat:goalsTotal": "1"},
    })
    observation["actions"] = [{
        "ordinal": 1, "class": "score", "minute": "23", "period": "1",
        "participant_provider_id": "9021", "label": "Goal",
    }]
    return document


class TestCapabilities(unittest.TestCase):
    """A5 — a consumer decides before it parses, and unknown names fail closed."""

    def test_the_rich_fixture_is_itself_a_valid_observation(self):
        """Otherwise the tier assertions below describe a document no adapter
        could ever legally produce."""
        self.assertEqual(validate_observation(rich_observation()), [])

    def test_minimal_observation_reaches_core_only(self):
        report = capability_report(MINIMAL)["capabilities"]
        self.assertEqual(report["tier"], "core")
        self.assertEqual(report["tiers_satisfied"], ["core"])
        self.assertIn("event.clock", report["absent"])
        self.assertEqual(report["violations"], [])

    def test_core_required_capabilities_are_all_present_on_the_minimal_fixture(self):
        report = capability_report(MINIMAL)["capabilities"]
        for capability in TIER_REQUIRED["core"]:
            with self.subTest(capability=capability):
                self.assertIn(capability, report["present"])

    def test_rich_observation_reaches_advanced(self):
        report = capability_report(rich_observation())["capabilities"]
        self.assertEqual(report["tier"], "advanced")
        self.assertEqual(report["tiers_satisfied"], ["core", "live", "advanced"])

    def test_tiers_do_not_skip(self):
        """Advanced statistics without a clock is still core.

        Reporting ``advanced`` there would tell a consumer it can rely on live
        data that will never arrive.
        """
        document = rich_observation()
        document["observation"]["event"].pop("clock")
        report = capability_report(document)["capabilities"]
        self.assertEqual(report["tier"], "core")
        self.assertEqual(report["tiers_satisfied"], ["core"])
        self.assertIn("participant.player_statistics", report["present"])

    def test_an_observation_below_core_reports_no_tier_rather_than_core(self):
        document = copy.deepcopy(MINIMAL)
        document["observation"]["competition"].pop("provider_id")
        report = capability_report(document)["capabilities"]
        self.assertIsNone(report["tier"])
        self.assertEqual(report["tiers_satisfied"], [])

    def test_started_event_without_a_score_is_a_violation(self):
        bad = copy.deepcopy(MINIMAL)
        for participant in bad["observation"]["participants"]:
            participant.pop("score")
        self.assertIn(
            "score-absent-on-started-event",
            capability_report(bad)["capabilities"]["violations"],
        )

    def test_a_prelive_event_without_a_score_is_not_a_violation(self):
        """The conditional rule is deliberately outside tier gating, so a
        legitimate pre-match payload still reaches core."""
        prelive = copy.deepcopy(MINIMAL)
        prelive["observation"]["event"]["status"] = "not_started"
        for participant in prelive["observation"]["participants"]:
            participant.pop("score")
        report = capability_report(prelive)["capabilities"]
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["tier"], "core")

    def test_present_and_absent_partition_every_known_capability(self):
        report = capability_report(MINIMAL)["capabilities"]
        self.assertEqual(
            sorted(report["present"] + report["absent"]), sorted(ALL_CAPABILITIES)
        )
        self.assertEqual(set(report["present"]) & set(report["absent"]), set())

    def test_capabilities_the_schema_cannot_carry_are_named_as_such(self):
        """``event.tracking`` is absent because ``canonical-observation/1`` has
        no field for it, not because the provider withheld it. A consumer that
        cannot tell those apart will chase the wrong provider."""
        report = capability_report(rich_observation())["capabilities"]
        self.assertIn("event.tracking", report["not_expressible"])
        self.assertIn("event.tracking", report["absent"])
        for capability in report["not_expressible"]:
            with self.subTest(capability=capability):
                self.assertNotIn(capability, report["present"])

    def test_by_tier_splits_required_from_optional(self):
        report = capability_report(MINIMAL)["capabilities"]
        core = report["by_tier"]["core"]
        self.assertEqual(core["required_absent"], [])
        self.assertEqual(core["required_present"], sorted(TIER_REQUIRED["core"]))
        self.assertIn("event.score", core["optional_present"])
        self.assertIn("event.result", core["optional_absent"])

    def test_requires_is_checked_and_optional_is_only_reported(self):
        caps = capability_report(MINIMAL)["capabilities"]
        result = check_compatibility(
            caps, requires=("event.status",), optional=("event.tracking",)
        )
        self.assertTrue(result["compatible"])
        self.assertEqual(result["missing_optional"], ["event.tracking"])
        self.assertEqual(result["missing_required"], [])

    def test_a_missing_required_capability_makes_it_incompatible(self):
        caps = capability_report(MINIMAL)["capabilities"]
        result = check_compatibility(caps, requires=("event.clock",))
        self.assertFalse(result["compatible"])
        self.assertEqual(result["missing_required"], ["event.clock"])

    def test_unknown_capability_fails_closed(self):
        caps = capability_report(MINIMAL)["capabilities"]
        result = check_compatibility(caps, requires=("event.staus",))
        self.assertFalse(result["compatible"])
        self.assertEqual(result["unknown_capabilities"], ["event.staus"])

    def test_an_unknown_optional_capability_also_fails_closed(self):
        """A typo is a typo wherever it appears. Reading an unknown optional as
        'merely absent' is how a consumer ships against a capability that does
        not exist."""
        caps = capability_report(MINIMAL)["capabilities"]
        result = check_compatibility(caps, optional=("event.trackng",))
        self.assertFalse(result["compatible"])
        self.assertEqual(result["unknown_capabilities"], ["event.trackng"])

    def test_no_requirements_at_all_is_compatible(self):
        caps = capability_report(MINIMAL)["capabilities"]
        self.assertTrue(check_compatibility(caps)["compatible"])

    def test_tier_tables_are_disjoint_and_cover_all_capabilities(self):
        named = []
        for tier in TIER_ORDER:
            named.extend(TIER_REQUIRED[tier])
            named.extend(TIER_OPTIONAL[tier])
        self.assertEqual(sorted(named), sorted(set(named)), "a capability is in two tiers")
        self.assertEqual(sorted(named), sorted(ALL_CAPABILITIES))


class TestSurrogateIds(unittest.TestCase):
    """A3 — identity is a visibly-marked, provider-scoped surrogate."""

    def test_ids_are_deterministic(self):
        a, b = surrogate_resolver("api-football"), surrogate_resolver("api-football")
        self.assertEqual(a("event", "9001"), b("event", "9001"))

    def test_ids_are_provider_scoped(self):
        self.assertNotEqual(
            surrogate_resolver("api-football")("event", "9001"),
            surrogate_resolver("sportradar-soccer")("event", "9001"),
        )

    def test_form_marks_the_id_as_a_surrogate(self):
        value = surrogate_resolver("api-football")("event", "9001")
        self.assertRegex(value, r"^urn:machina:sports:event:x[0-9a-f]{32}$")
        self.assertEqual(SURROGATE_MARKER, "x")

    def test_distinct_fixtures_never_collide(self):
        mint = surrogate_resolver("api-football")
        self.assertNotEqual(mint("event", "9001"), mint("event", "9002"))

    def test_no_provider_namespace_leaks_into_the_id(self):
        self.assertNotIn("api-football", surrogate_resolver("api-football")("team", "9011"))

    def test_no_provider_id_leaks_into_the_id(self):
        """The digest is opaque, so the profile's provider-id-as-resource-id rule
        can never be tripped by an identifier this resolver minted."""
        self.assertNotIn("9011", surrogate_resolver("api-football")("team", "9011"))

    def test_kinds_do_not_collide_with_each_other(self):
        mint = surrogate_resolver("api-football")
        self.assertNotEqual(
            mint("team", "9011").split(":")[-1], mint("athlete", "9011").split(":")[-1]
        )

    def test_part_boundaries_are_not_ambiguous(self):
        """``("a", "bc")`` and ``("ab", "c")`` must not mint the same identifier.

        Concatenating parts before hashing is the classic way to make two
        different fixtures collide, and a collision here silently merges two
        events into one resource.
        """
        mint = surrogate_resolver("api-football")
        self.assertNotEqual(mint("participation", "a", "bc"), mint("participation", "ab", "c"))

    def test_integer_and_string_parts_agree(self):
        """An adapter reading ordinal 1 as int must not mint a different action
        identifier from one reading it as "1"."""
        mint = surrogate_resolver("api-football")
        self.assertEqual(mint("action", "9001", 1), mint("action", "9001", "1"))


class TestOfficialTermExport(unittest.TestCase):
    """A4 — the allowlist is generated from the pin, never hand-maintained."""

    def test_allowlist_is_reproducible_from_the_pin(self):
        path = export_official_terms.OUTPUT_PATH
        self.assertTrue(
            path.is_file(),
            "run: python -m tools.iptc.canonical.export_official_terms",
        )
        self.assertEqual(path.read_text(encoding="utf-8"), export_official_terms.render())

    def test_allowlist_records_the_pin_it_was_generated_from(self):
        payload = json.loads(export_official_terms.OUTPUT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["pin"], canonical_pin())
        self.assertEqual(payload["target_version"], "1.1")

    def test_allowlist_contains_a_verified_statistic_and_not_an_invented_one(self):
        names = set(
            json.loads(export_official_terms.OUTPUT_PATH.read_text(encoding="utf-8"))["local_names"]
        )
        self.assertIn("shotsTotal", names)
        self.assertIn("startDateTime", names)
        self.assertNotIn("machinaVibes", names)

    def test_allowlist_holds_properties_only_and_not_classes(self):
        """A class name in a property allowlist would let ``spsocstat:Team`` pass."""
        names = set(
            json.loads(export_official_terms.OUTPUT_PATH.read_text(encoding="utf-8"))["local_names"]
        )
        self.assertNotIn("Event", names)
        self.assertNotIn("Team", names)


class TestVocab(unittest.TestCase):
    """A6 — no code is mapped into a scheme the pin cannot check."""

    def test_status_maps_to_a_node_reference(self):
        self.assertEqual(
            vocab.newscode("speventstatus", vocab.EVENT_STATUS["closed"]),
            {"@id": "speventstatus:post-event"},
        )

    def test_a_newscode_is_never_a_bare_string(self):
        """A literal cannot be followed to a concept, and layers 3 and 4 reject
        it. The only way to emit one is to bypass ``newscode``."""
        for scheme, table in vocab.TABLES.items():
            for key in table:
                with self.subTest(scheme=scheme, key=key):
                    self.assertEqual(list(vocab.newscode(scheme, table[key])), ["@id"])

    def test_every_mapped_code_is_in_a_pinned_scheme(self):
        reference = load_reference()
        for scheme, table in vocab.TABLES.items():
            for key, code in table.items():
                iri = "{0}{1}/{2}".format(NEWSCODE_STEM, vocab.SCHEME_PATH[scheme], code)
                with self.subTest(scheme=scheme, key=key):
                    pinned = reference.scheme_for(iri)
                    self.assertIsNotNone(
                        pinned, "{0} is not pinned; do not map into it".format(scheme)
                    )
                    self.assertIn(iri, pinned.concepts)

    def test_every_table_has_a_scheme_path(self):
        self.assertEqual(sorted(vocab.TABLES), sorted(vocab.SCHEME_PATH))

    def test_soccer_action_types_are_not_mapped_at_all(self):
        """RFC 001 §9.2: no ``spsocaction`` vocabulary exists at the pinned
        commit, layer 4 fails closed on unverifiable, so there is nothing
        defensible to map into. The provider's own action type survives in
        ``event_view`` and ``machina:evidence`` instead."""
        self.assertNotIn("spsocactiontype", vocab.TABLES)
        self.assertNotIn("spsocaction", vocab.TABLES)
        self.assertNotIn("spsocactiontype", vocab.SCHEME_PATH)

    def test_provider_status_codes_map_the_way_rfc_001_says(self):
        for provider_code, expected in (
            ("not_started", "pre-event"),
            ("in_progress", "mid-event"),
            ("halftime", "intermission"),
            ("closed", "post-event"),
            ("postponed", "postponed"),
            ("cancelled", "canceled"),
            ("suspended", "suspended"),
            ("abandoned", "halted"),
            ("awarded", "forfeited"),
        ):
            with self.subTest(status=provider_code):
                self.assertEqual(vocab.EVENT_STATUS[provider_code], expected)

    def test_unmapped_status_raises_rather_than_guessing(self):
        with self.assertRaises(KeyError):
            vocab.EVENT_STATUS["definitely_not_a_status"]

    def test_newscode_refuses_a_scheme_it_does_not_know(self):
        """Failing closed here is what stops a caller reaching an unpinned
        scheme by passing its name in as a string."""
        with self.assertRaises(KeyError):
            vocab.newscode("spsocactiontype", "goal")

    def test_newscode_refuses_a_code_that_is_not_in_the_table(self):
        with self.assertRaises(ValueError):
            vocab.newscode("speventstatus", "definitely-not-a-code")

    def test_the_expected_tables_exist(self):
        for name in ("EVENT_STATUS", "EVENT_OUTCOME", "EVENT_OUTCOME_TYPE",
                     "COMPETITION_TYPE", "ACTION_CLASS", "PLAYER_STATUS",
                     "SOCCER_POSITION"):
            with self.subTest(table=name):
                self.assertTrue(getattr(vocab, name))


#: Modules destined to be copied byte-exact into ``sports-skills``, a published
#: zero-dependency package that supports Python 3.9 and cannot import this
#: repository. ``export_official_terms.py`` is deliberately not here: it is a
#: generator, it runs only in this repository, and it is not vendored.
VENDORED_RUNTIME_MODULES = (
    "observation.py",
    "ids.py",
    "capabilities.py",
    "vocab.py",
)


class TestVendoringConstraints(unittest.TestCase):
    """The vendoring boundary, checked here rather than discovered downstream.

    Every one of these failures would otherwise surface as a broken install of a
    published package, which is the most expensive place to find them.
    """

    def module_source(self, name: str) -> str:
        return (REPO_ROOT / "tools/iptc/canonical" / name).read_text(encoding="utf-8")

    def test_every_vendored_module_parses_under_python_3_9(self):
        for name in VENDORED_RUNTIME_MODULES:
            with self.subTest(module=name):
                ast.parse(
                    self.module_source(name), filename=name, feature_version=(3, 9)
                )

    def test_no_vendored_module_imports_tools(self):
        for name in VENDORED_RUNTIME_MODULES:
            with self.subTest(module=name):
                tree = ast.parse(self.module_source(name), filename=name)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.assertNotEqual(alias.name.split(".")[0], "tools")
                    elif isinstance(node, ast.ImportFrom):
                        root = (node.module or "").split(".")[0]
                        self.assertNotEqual(root, "tools")
                        # level >= 2 escapes tools/iptc/canonical/ into
                        # tools/iptc/, which does not exist downstream.
                        self.assertLessEqual(node.level, 1, "relative import escapes the package")

    def test_no_vendored_module_imports_a_third_party_package(self):
        stdlib = set(sys.stdlib_module_names)
        for name in VENDORED_RUNTIME_MODULES:
            tree = ast.parse(self.module_source(name), filename=name)
            for node in ast.walk(tree):
                roots = []
                if isinstance(node, ast.Import):
                    roots = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    roots = [(node.module or "").split(".")[0]]
                for root in roots:
                    with self.subTest(module=name, imported=root):
                        self.assertTrue(
                            root in stdlib,
                            "{0} imports '{1}', which is not in the standard "
                            "library".format(name, root),
                        )


def canonical_pin() -> str:
    from tools.iptc.reference import UPSTREAM_COMMIT

    return UPSTREAM_COMMIT


if __name__ == "__main__":
    unittest.main(verbosity=2)
