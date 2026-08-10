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
import re
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
from tools.iptc.canonical.serialize import (  # noqa: E402
    SHARED_CONTEXT_PATH,
    shared_context,
    sport_schema_graph,
)
from tools.iptc.context import CONTEXT_PATH, load_context  # noqa: E402
from tools.iptc.reference import NEWSCODE_STEM, load_reference  # noqa: E402

#: The smallest observation that is genuinely valid: two participants, every
#: required field, nothing optional. Every negative case below is this document
#: with exactly one thing broken, so a failure names the rule it broke.
MINIMAL = {
    "schema_version": "canonical-observation/1",
    "observation": {
        "provider": {"namespace": "api-football", "family": "licensed"},
        "observed_at": "2026-03-01T22:05:00+00:00",
        "adapter": {"name": "sports_skills.canonical.adapters.football",
                    "version": "0.31.0"},
        "rights": {"data_class": "public-non-commercial", "prototype_only": True,
                   "commercial_use": False},
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
            ("adapter",),
            ("rights",),
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

    def test_a_statistic_under_an_unbound_prefix_is_rejected(self):
        """``notpinned:shotsTotal`` carries a genuine local name under a prefix
        no context in scope binds, so it expands to nothing at all. A check that
        looks only at the local name reads it as official.
        """
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["participants"][0]["statistics"] = {"notpinned:shotsTotal": "14"}
        errors = " ".join(validate_observation(bad))
        self.assertIn("notpinned:shotsTotal", errors)
        self.assertIn("not an official Sport Schema property", errors)

    def test_a_real_local_name_under_the_wrong_pinned_namespace_is_rejected(self):
        """``sport:startDateTime`` is official and ``spsocstat:startDateTime`` is
        not: the soccer statistics ontology declares no such property. Both
        prefixes are pinned, so only full-CURIE membership separates them.
        """
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["participants"][0]["statistics"] = {
            "spsocstat:startDateTime": "2026-03-01T20:00:00+00:00"
        }
        self.assertIn("spsocstat:startDateTime", " ".join(validate_observation(bad)))

    def test_a_pinned_core_statistic_curie_is_accepted(self):
        """The counterpart to the two rejections above: a CURIE whose prefix and
        local name both come from the pin is accepted, from any pinned statistics
        namespace and not just soccer.
        """
        ok = copy.deepcopy(MINIMAL)
        ok["observation"]["participants"][0]["statistics"] = {"spstat:eventsPlayed": "38"}
        self.assertEqual(validate_observation(ok), [])

    def test_a_bare_statistic_name_without_a_prefix_is_rejected(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["participants"][0]["statistics"] = {"shotsTotal": "14"}
        self.assertIn("shotsTotal", " ".join(validate_observation(bad)))

    def test_a_numeric_statistic_is_rejected_because_the_shapes_say_string(self):
        bad = copy.deepcopy(MINIMAL)
        bad["observation"]["participants"][0]["statistics"] = {"spsocstat:shotsTotal": 14}
        self.assertIn("must be a string", " ".join(validate_observation(bad)))

    def test_an_absent_rights_block_is_one_deterministic_error(self):
        """Rights are a licence fact, and a licence fact is not derivable from a
        payload. Accepting an observation with no rights block means every
        consumer picks its own default, which is a licence decision made by
        accident. The error names the block once and does not cascade into its
        member fields, so the adapter fix is unambiguous.
        """
        bad = copy.deepcopy(MINIMAL)
        del bad["observation"]["rights"]
        self.assertEqual(
            validate_observation(bad),
            ["observation.rights: required field is missing"],
        )

    def test_an_absent_adapter_block_is_one_deterministic_error(self):
        """Adapter provenance is what makes a wrong fact traceable to the code
        that produced it. Without it an observation is an anonymous claim.
        """
        bad = copy.deepcopy(MINIMAL)
        del bad["observation"]["adapter"]
        self.assertEqual(
            validate_observation(bad),
            ["observation.adapter: required field is missing"],
        )

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

    def allowlist(self) -> set:
        payload = json.loads(export_official_terms.OUTPUT_PATH.read_text(encoding="utf-8"))
        return set(payload["curies"])

    def test_allowlist_contains_a_verified_statistic_and_not_an_invented_one(self):
        curies = self.allowlist()
        self.assertIn("spsocstat:shotsTotal", curies)
        self.assertIn("sport:startDateTime", curies)
        self.assertNotIn("spsocstat:machinaVibes", curies)

    def test_allowlist_membership_is_the_whole_curie_not_the_local_name(self):
        """The local name is not the term. ``spsocstat:startDateTime`` pairs a
        real local name with a namespace that does not declare it, and
        ``notpinned:shotsTotal`` pairs one with a prefix nothing binds. Both are
        indistinguishable from an official term if only local names are stored.
        """
        curies = self.allowlist()
        self.assertNotIn("spsocstat:startDateTime", curies)
        self.assertNotIn("notpinned:shotsTotal", curies)

    def test_allowlist_prefixes_are_all_bound_by_the_shared_context(self):
        """A CURIE whose prefix the shared context does not bind expands to
        nothing, so allowing one would be allowing a term no document can carry.
        """
        bound = set(load_context())
        self.assertTrue(bound)
        for curie in sorted(self.allowlist()):
            with self.subTest(curie=curie):
                self.assertIn(curie.split(":")[0], bound)

    def test_allowlist_holds_properties_only_and_not_classes(self):
        """A class name in a property allowlist would let ``spsocstat:Team`` pass."""
        curies = self.allowlist()
        self.assertNotIn("sport:Event", curies)
        self.assertNotIn("sport:Team", curies)


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


RFC_001_PATH = REPO_ROOT / "docs/rfcs/001-machina-iptc-sport-schema-profile.md"
RFC_002_PATH = REPO_ROOT / "docs/rfcs/002-machina-sports-schema-canonical-observation.md"


def rfc_section(path: Path, number: str) -> str:
    """The body of the section numbered ``number``, up to the next heading.

    Section-scoped rather than whole-file, so "the RFC mentions this somewhere"
    can never be mistaken for "the rule that governs it says so".
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    heading = re.compile(r"^#{2,4} " + re.escape(number) + r"[.\s]")
    start = next((i + 1 for i, line in enumerate(lines) if heading.match(line)), None)
    assert start is not None, "{0} has no section {1}".format(path.name, number)
    body = []
    for line in lines[start:]:
        if re.match(r"^#{2,4} ", line):
            break
        body.append(line)
    return "\n".join(body)


class TestRfcContractConsistency(unittest.TestCase):
    """The RFCs and the code they authorise are checked against each other.

    Every gap closed in this class was first found by a human reading two
    documents side by side. That is the expensive way to find a contradiction,
    and it only works while someone is looking.
    """

    def required_bullet(self) -> str:
        """RFC 002 §1.1's ``**Required:**`` bullet, and only that bullet.

        Scoped to the one bullet on purpose. A whole-section search passes on any
        stray mention — "the caller fixes the adapter" would have satisfied a
        looser check while the required list still omitted `adapter`.
        """
        section = rfc_section(RFC_002_PATH, "1.1")
        match = re.search(r"^- \*\*Required:\*\*(.*?)(?=^- \*\*)", section,
                          re.DOTALL | re.MULTILINE)
        self.assertIsNotNone(match, "RFC 002 §1.1 has no **Required:** bullet")
        return match.group(1)

    #: A scheme prefix as the RFCs write one: ``prefix:`` inside backticks. The
    #: closing backtick right after the colon is what keeps ``sport:eventStatus``
    #: and other term references out of the match.
    SCHEME_REFERENCE = re.compile(r"`([a-z][a-z0-9]*):`")

    #: An instruction to emit, minus its negations. ``must not`` and ``must never``
    #: are the reconciled rule, not the defect, so a test that flagged them would
    #: fail on exactly the text it is asking for.
    EMIT_INSTRUCTION = re.compile(r"\bmust\b(?!\s+(?:not|never))[^.]*\bemit\b")

    def unpinned_scheme_prefixes(self) -> set:
        """Prefixes the shared context binds to a NewsCode scheme the pin cannot check.

        Read from the pin rather than from `vocab.TABLES`: "this profile maps
        nothing into it" and "nothing can validate it" are different facts, and
        only the second one makes an emission instruction indefensible. `medtop:`
        is pinned and unmapped — RFC 001 is right to require emitting it — so a
        check keyed on the mapping tables would flag it.
        """
        pinned = {scheme.scheme_iri for scheme in load_reference().schemes.values()}
        unpinned = {
            prefix for prefix, iri in load_context().items()
            if iri.startswith(NEWSCODE_STEM) and iri not in pinned
        }
        self.assertIn("spsocactiontype", unpinned, "no spsocaction TTL exists at the pin")
        self.assertNotIn("medtop", unpinned, "mediatopic is pinned and must stay emittable")
        return unpinned

    def test_no_rfc_instructs_emitting_a_newscode_from_an_unpinned_scheme(self):
        """RFC 001 §9.2 named `spsocactiontype:` as an emission target while §9's
        own normative rule fails closed on any value nothing in the pin can check
        — and while RFC 002 §7 and `vocab.py` map nothing into it. An adapter
        author following the RFC would emit a NewsCode layer 4 then rejects.

        Mechanical on both sides: the scheme names come out of the prose, their
        pinned-ness out of the vendored vocabularies. A pin bump that publishes
        `spsocaction.ttl` retires this check by itself, with no test edit.
        """
        unpinned = self.unpinned_scheme_prefixes()
        offenders = []
        for path in (RFC_001_PATH, RFC_002_PATH):
            for sentence in re.split(r"(?<=\.)\s+", path.read_text(encoding="utf-8")):
                named = sorted(
                    p for p in set(self.SCHEME_REFERENCE.findall(sentence)) if p in unpinned
                )
                if named and self.EMIT_INSTRUCTION.search(sentence):
                    offenders.append("{0} [{1}]: {2}".format(
                        path.name, ", ".join(named), " ".join(sentence.split())
                    ))
        self.assertEqual(
            offenders, [],
            "an RFC instructs emitting a NewsCode from a scheme the pin cannot "
            "check, which §9 requires failing closed on",
        )

    def test_rfc_001_and_rfc_002_agree_on_where_soccer_action_detail_goes(self):
        """The reconciled rule, asserted on both sides: the class goes to the one
        pinned scheme, the provider's own action type survives outside the graph.
        """
        section = rfc_section(RFC_001_PATH, "9.2")
        self.assertIn("spactionclass:", section)
        self.assertIn("event_view", section)
        self.assertIn("spactionclass", vocab.TABLES)
        self.assertNotIn("spsocactiontype", vocab.TABLES)
        rfc_002_vocabularies = rfc_section(RFC_002_PATH, "7")
        self.assertIn("spsocactiontype:` is not mapped at all", rfc_002_vocabularies)

    def test_rfc_002_records_every_top_level_field_the_validator_requires(self):
        """A required field the contract does not list is a trap: the adapter
        author reads the RFC, the validator rejects the result."""
        bullet = self.required_bullet()
        for key in sorted(MINIMAL["observation"]):
            bad = copy.deepcopy(MINIMAL)
            del bad["observation"][key]
            if not validate_observation(bad):
                continue
            with self.subTest(field=key):
                self.assertRegex(
                    bullet, r"`{0}[.`]".format(re.escape(key)),
                    "validate_observation requires observation.{0} and the RFC "
                    "002 §1.1 required list does not name it".format(key),
                )


def graph_observation():
    """A wholly synthetic observation exercising every resource kind in RFC 002 §2.

    Invented from end to end: no provider was called, and no name, identifier or
    venue below belongs to a real entity. Its statistics are chosen from the
    properties the pinned ``sh:closed`` participation shapes actually admit, which
    is the difference between a fixture that proves conformance and one that
    proves the serializer can emit plausible-looking JSON.
    """
    return {
        "schema_version": "canonical-observation/1",
        "observation": {
            "provider": {"namespace": "api-football", "family": "licensed"},
            "observed_at": "2026-03-01T22:05:00+00:00",
            "adapter": {"name": "tests.synthetic", "version": "0"},
            "rights": {"data_class": "licensed-redistributable",
                       "prototype_only": False, "commercial_use": True},
            "sport": {"medtop": "20001065", "key": "soccer"},
            "competition": {
                "provider_id": "39",
                "name": "Synthetic Premier Division",
                "type": "recurring-competition",
                "season": {"provider_id": "39-2026",
                           "name": "Synthetic Premier Division 2025/2026"},
            },
            "phase": {"provider_id": "39-2026-27", "name": "Matchday 27"},
            "site": {"provider_id": "9101", "name": "Synthetic Home Ground",
                     "city": "Synthetic City", "country": "SYN"},
            "event": {
                "provider_id": "9001",
                "label": "Synthetic Home United vs Synthetic Away Town",
                "start_time": "2026-03-01T20:00:00+00:00",
                "status": "closed",
                "outcome_type": "regular",
                "attendance": "60123",
                "clock": {"minute": "90", "period": "2"},
            },
            "participants": [
                {"kind": "team", "provider_id": "9011",
                 "name": "Synthetic Home United", "alignment": "home",
                 "score": "2", "outcome": "win",
                 "statistics": {"spsocstat:shotsTotal": "14",
                                "spstat:timeOfPossessionPercentage": "57.0"}},
                {"kind": "team", "provider_id": "9012",
                 "name": "Synthetic Away Town", "alignment": "away",
                 "score": "1", "outcome": "loss",
                 "statistics": {"spsocstat:shotsTotal": "8"}},
                {"kind": "individual", "provider_id": "9021",
                 "name": "Synthetic Scorer", "team_provider_id": "9011",
                 "player_status": "starter", "position": "forward",
                 "statistics": {"spsocstat:goalsTotal": "1",
                                "spstat:timePlayedTotal": "90"}},
            ],
            "memberships": [{"individual_provider_id": "9021",
                             "team_provider_id": "9011", "uniform_number": "9"}],
            "actions": [{"ordinal": 1, "class": "score", "minute": "23",
                         "period": "1", "participant_provider_id": "9021",
                         "label": "Goal",
                         "action_time": "2026-03-01T20:23:11+00:00"}],
            "raw": {"@type": "provider-payload", "fixture": {"id": 9001},
                    "events": [{"type": "Goal", "detail": "Normal Goal"}]},
        },
    }


def mint():
    return surrogate_resolver("api-football")


def typed(document, type_name):
    return [n for n in document["@graph"] if n.get("@type") == type_name]


class TestPackagedSharedContext(unittest.TestCase):
    """A7 — the serializer inlines the *published* context, not a lookalike.

    ``serialize.py`` is vendored into a package that has no ``tools.iptc.context``
    to import, so it carries its own copy. A copy nobody checks is a fork waiting
    to happen: these two assertions are what make it a copy rather than a second
    source of truth.
    """

    def test_packaged_copy_is_byte_identical_to_the_published_context(self):
        self.assertEqual(SHARED_CONTEXT_PATH.read_bytes(), CONTEXT_PATH.read_bytes())

    def test_packaged_copy_binds_exactly_what_load_context_binds(self):
        self.assertEqual(shared_context(), load_context())

    def test_the_returned_table_cannot_be_mutated_through_a_caller(self):
        first = shared_context()
        first["sport"] = "https://example.invalid/"
        self.assertEqual(shared_context()["sport"],
                         "https://sportschema.org/ontologies/main/")


class TestGraphCore(unittest.TestCase):
    """A7 — one context, one flat @graph, resources as addressable siblings."""

    def setUp(self):
        self.doc = sport_schema_graph(MINIMAL, id_resolver=mint())

    def test_one_inline_document_context_and_one_graph(self):
        self.assertIsInstance(self.doc["@context"], dict)
        self.assertEqual(self.doc["@context"]["sport"],
                         "https://sportschema.org/ontologies/main/")
        self.assertEqual(load_context()["sport"], self.doc["@context"]["sport"])
        self.assertIsInstance(self.doc["@graph"], list)
        self.assertTrue(all("@context" not in n for n in self.doc["@graph"]))

    def test_the_document_has_no_key_beyond_context_and_graph(self):
        self.assertEqual(sorted(self.doc), ["@context", "@graph"])

    def test_resources_are_separate_siblings(self):
        types = [n["@type"] for n in self.doc["@graph"]]
        for expected in ("sport:Competition", "sport:Event", "sport:Team",
                         "sport:TeamParticipation", "machina:ObservationProvenance"):
            self.assertIn(expected, types)
        self.assertEqual(types.count("sport:TeamParticipation"), 2)

    def test_no_resource_is_nested_inside_another(self):
        """A nested typed node is a resource nobody else can reference by @id.

        A typed *value* node — ``{"@value": …, "@type": "xsd:dateTime"}`` — carries
        a datatype rather than a class, so it is not a resource and is exempt.
        """
        for node in self.doc["@graph"]:
            for key, value in node.items():
                for child in (value if isinstance(value, list) else [value]):
                    if isinstance(child, dict) and "@value" not in child:
                        self.assertNotIn("@type", child, "{0} nests a resource".format(key))

    def test_event_carries_the_mandatory_properties(self):
        event = typed(self.doc, "sport:Event")[0]
        self.assertEqual(event["rdfs:label"], "H vs A")
        self.assertEqual(event["sport:sport"], {"@id": "medtop:20001065"})
        self.assertEqual(event["sport:eventStatus"], {"@id": "speventstatus:post-event"})
        self.assertEqual(event["sport:startDateTime"],
                         {"@value": "2026-03-01T20:00:00+00:00", "@type": "xsd:dateTime"})
        self.assertIn("sport:eventInCompetition", event)
        self.assertEqual(len(event["sport:participation"]), 2)
        self.assertTrue(all(set(r) == {"@id"} for r in event["sport:participation"]))

    def test_event_participation_references_resolve_inside_the_graph(self):
        ids = {n["@id"] for n in self.doc["@graph"]}
        event = typed(self.doc, "sport:Event")[0]
        for reference in event["sport:participation"]:
            self.assertIn(reference["@id"], ids)

    def test_team_participation_carries_alignment_score_and_the_team(self):
        home = next(p for p in typed(self.doc, "sport:TeamParticipation")
                    if p["sport:alignment"] == "home")
        team_ids = {t["@id"] for t in typed(self.doc, "sport:Team")}
        self.assertEqual(home["sport:score"], "2")
        self.assertIn(home["sport:participationBy"]["@id"], team_ids)

    def test_ids_are_unique_and_output_is_byte_stable(self):
        ids = [n["@id"] for n in self.doc["@graph"]]
        self.assertEqual(len(ids), len(set(ids)))
        again = sport_schema_graph(MINIMAL, id_resolver=mint())
        self.assertEqual(json.dumps(self.doc, sort_keys=False),
                         json.dumps(again, sort_keys=False))

    def test_every_sport_term_emitted_is_declared_by_the_pin(self):
        reference = load_reference()
        official = reference.main_local_names()
        for node in self.doc["@graph"]:
            for term in [node["@type"]] + list(node):
                if isinstance(term, str) and term.startswith("sport:"):
                    with self.subTest(term=term):
                        self.assertIn(term.split(":", 1)[1], official)


class TestGraphRichObservation(unittest.TestCase):
    """A7 — every resource kind in the RFC 002 §2 table, from one observation."""

    def setUp(self):
        self.observation = graph_observation()
        self.doc = sport_schema_graph(self.observation, id_resolver=mint())

    def test_the_fixture_is_itself_a_valid_observation(self):
        self.assertEqual(validate_observation(self.observation), [])

    def test_every_contract_resource_kind_is_emitted(self):
        types = [n["@type"] for n in self.doc["@graph"]]
        for expected in ("sport:Competition", "sport:CompetitionPhase", "sport:Site",
                         "sport:Team", "sport:Athlete", "sport:Event",
                         "sport:TeamParticipation", "sport:IndividualParticipation",
                         "sport:IndividualMembership", "sport:Action",
                         "machina:ProviderIdentifier", "machina:ObservationProvenance"):
            with self.subTest(resource=expected):
                self.assertIn(expected, types)
        self.assertEqual(types.count("sport:Competition"), 2)
        self.assertEqual(types.count("sport:Event"), 1)
        self.assertEqual(types.count("machina:ObservationProvenance"), 1)

    def test_the_season_competition_points_at_the_recurring_one(self):
        recurring, season = typed(self.doc, "sport:Competition")
        self.assertNotIn("sport:parent", recurring)
        self.assertEqual(season["sport:parent"], {"@id": recurring["@id"]})
        self.assertEqual(season["sport:competitionType"], {"@id": "spct:season"})

    def test_the_event_sits_in_the_season_not_the_recurring_competition(self):
        _, season = typed(self.doc, "sport:Competition")
        event = typed(self.doc, "sport:Event")[0]
        self.assertEqual(event["sport:eventInCompetition"], {"@id": season["@id"]})

    def test_the_phase_and_site_are_referenced_by_the_event(self):
        event = typed(self.doc, "sport:Event")[0]
        self.assertEqual(event["sport:eventInCompetitionPhase"],
                         {"@id": typed(self.doc, "sport:CompetitionPhase")[0]["@id"]})
        self.assertEqual(event["sport:location"],
                         {"@id": typed(self.doc, "sport:Site")[0]["@id"]})

    def test_the_site_carries_only_a_label_because_its_shape_admits_nothing_else(self):
        site = typed(self.doc, "sport:Site")[0]
        self.assertEqual(sorted(site), ["@id", "@type", "rdfs:label"])

    def test_the_clock_never_becomes_a_datetime_or_an_event_property(self):
        event = typed(self.doc, "sport:Event")[0]
        self.assertNotIn("sport:minutesElapsed", event)
        self.assertNotIn("sport:clock", event)

    def test_statistics_land_on_participations_as_string_literals(self):
        home = next(p for p in typed(self.doc, "sport:TeamParticipation")
                    if p["sport:alignment"] == "home")
        self.assertEqual(home["spsocstat:shotsTotal"], "14")
        self.assertEqual(home["spstat:timeOfPossessionPercentage"], "57.0")
        self.assertNotIn("sport:Statistic", [n["@type"] for n in self.doc["@graph"]])

    def test_participant_outcome_is_a_newscode_node_reference(self):
        home = next(p for p in typed(self.doc, "sport:TeamParticipation")
                    if p["sport:alignment"] == "home")
        self.assertEqual(home["sport:eventOutcome"], {"@id": "speventoutcome:win"})

    def test_outcome_type_stays_on_the_event_where_the_closed_shape_admits_it(self):
        event = typed(self.doc, "sport:Event")[0]
        self.assertEqual(event["sport:eventOutcomeType"],
                         {"@id": "speventoutcometype:regular"})
        self.assertEqual(event["sport:attendance"], "60123")
        for participation in typed(self.doc, "sport:TeamParticipation"):
            self.assertNotIn("sport:eventOutcomeType", participation)

    def test_the_individual_participation_links_athlete_status_and_team(self):
        individual = typed(self.doc, "sport:IndividualParticipation")[0]
        athlete = typed(self.doc, "sport:Athlete")[0]
        home = next(p for p in typed(self.doc, "sport:TeamParticipation")
                    if p["sport:alignment"] == "home")
        self.assertEqual(individual["sport:participationBy"], {"@id": athlete["@id"]})
        self.assertEqual(individual["sport:playerStatus"],
                         {"@id": "spplayerstatus:starter"})
        self.assertEqual(individual["sport:positionEvent"],
                         {"@id": "spsocposition:forward"})
        self.assertEqual(individual["sport:teamParticipation"], {"@id": home["@id"]})
        self.assertEqual(individual["spsocstat:goalsTotal"], "1")

    def test_the_membership_joins_the_athlete_to_the_team(self):
        membership = typed(self.doc, "sport:IndividualMembership")[0]
        self.assertEqual(membership["sport:member"],
                         {"@id": typed(self.doc, "sport:Athlete")[0]["@id"]})
        home_team = typed(self.doc, "sport:Team")[0]
        self.assertEqual(membership["sport:membershipOf"], {"@id": home_team["@id"]})
        self.assertEqual(membership["sport:uniformNumber"], "9")

    def test_the_action_references_the_event_its_class_and_its_participation(self):
        action = typed(self.doc, "sport:Action")[0]
        event = typed(self.doc, "sport:Event")[0]
        individual = typed(self.doc, "sport:IndividualParticipation")[0]
        self.assertEqual(action["sport:actionInEvent"], {"@id": event["@id"]})
        self.assertEqual(action["sport:class"], {"@id": "spactionclass:score"})
        self.assertEqual(action["sport:actionDateTime"],
                         {"@value": "2026-03-01T20:23:11+00:00", "@type": "xsd:dateTime"})
        self.assertEqual(action["sport:minutesElapsed"], "23")
        self.assertEqual(action["sport:periodValue"], "1")
        self.assertEqual(action["sport:participation"], {"@id": individual["@id"]})

    def test_no_unpinned_action_vocabulary_is_invented_for_the_provider_detail(self):
        """No TTL for ``spsocaction`` exists at the pin, so layer 4 cannot check it.

        Asserted over ``@graph`` rather than the whole document: the shared context
        *binds* the prefix, because upstream declares it. Binding a prefix commits
        to nothing; emitting a value in it commits to a code nobody can verify.
        """
        blob = json.dumps(self.doc["@graph"])
        for token in ("spsocactiontype", "spsocaction:", "Normal Goal"):
            self.assertNotIn(token, blob)

    def test_the_provider_payload_never_reaches_the_graph(self):
        self.assertNotIn("provider-payload", json.dumps(self.doc))

    def test_every_reference_resolves_and_no_id_repeats(self):
        """A dangling @id is a fact that reads as present and resolves to nothing.

        Two kinds of reference exist: a resource URN, which must name a sibling in
        this graph, and a controlled-vocabulary CURIE, which names a concept in a
        pinned scheme and is checked by layer 4 instead.
        """
        ids = [n["@id"] for n in self.doc["@graph"]]
        self.assertEqual(len(ids), len(set(ids)))
        known = set(ids)
        for node in self.doc["@graph"]:
            for key, value in node.items():
                if key in ("@id", "@type"):
                    continue
                for child in (value if isinstance(value, list) else [value]):
                    if not (isinstance(child, dict) and set(child) == {"@id"}):
                        continue
                    target = child["@id"]
                    with self.subTest(pointer="{0}/{1}".format(node["@id"], key)):
                        if target.startswith("urn:"):
                            self.assertIn(target, known)
                        else:
                            self.assertIn(target.split(":", 1)[0], load_context())

    def test_output_is_byte_stable_across_runs(self):
        again = sport_schema_graph(graph_observation(), id_resolver=mint())
        self.assertEqual(json.dumps(self.doc), json.dumps(again))


#: Modules destined to be copied byte-exact into ``sports-skills``, a published
#: zero-dependency package that supports Python 3.9 and cannot import this
#: repository. ``export_official_terms.py`` is deliberately not here: it is a
#: generator, it runs only in this repository, and it is not vendored.
VENDORED_RUNTIME_MODULES = (
    "observation.py",
    "ids.py",
    "capabilities.py",
    "vocab.py",
    "serialize.py",
)

#: Non-Python files that travel with those modules. ``serialize.py`` reads the
#: shared context from a package-local copy rather than importing
#: ``tools.iptc.context``, because the vendored package has no such module.
VENDORED_RUNTIME_DATA = (
    "official-property-names.json",
    "shared-context.json",
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

    def test_every_vendored_data_file_is_present_and_is_plain_json(self):
        """A runtime module that reads a data file drags that file downstream.

        Recorded here so the vendoring list is the whole set a reviewer has to
        copy, not just the ``.py`` files that are easy to notice.
        """
        for name in VENDORED_RUNTIME_DATA:
            path = REPO_ROOT / "tools/iptc/canonical" / name
            with self.subTest(data=name):
                self.assertTrue(path.is_file(), path)
                json.loads(path.read_text(encoding="utf-8"))

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
