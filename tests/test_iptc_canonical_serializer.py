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
import tempfile
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
from tools.iptc.canonical import serialize as serialize_module  # noqa: E402
from tools.iptc.canonical import rights as rights_module  # noqa: E402
from tools.iptc import validate as validate_module  # noqa: E402
from tools.iptc import validate_graph  # noqa: E402
from tools.iptc.canonical.serialize import (  # noqa: E402
    SHARED_CONTEXT_PATH,
    canonical_envelope,
    event_view,
    provenance_block,
    provider_identifiers,
    shared_context,
    sport_schema_graph,
)
from tools.iptc.context import CONTEXT_PATH, load_context  # noqa: E402
from tools.iptc.reference import NEWSCODE_STEM, load_reference  # noqa: E402
from tools.iptc.validate import validate_document  # noqa: E402
from tools.iptc.validate_graph import rights_findings  # noqa: E402

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

    def test_rfc_001_names_the_check_that_enforces_its_identifier_policy(self):
        """§6.1 asserted "never a provider URN" for a whole PR while nothing
        checked it. A normative rule with no named check is a rule a reader cannot
        tell apart from an aspiration, so §6 now cites the finding code.
        """
        section = rfc_section(RFC_001_PATH, "6")
        self.assertIn("provider-id-as-resource-id", section)
        self.assertIn("provider-id-as-resource-id",
                      [f["code"] for f in profile_module.check(
                          official_graph("urn:apifootball:sport_event:1")).findings])

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
            "adapter": {"name": "tests.synthetic", "version": "0",
                        "source_refs": [{"kind": "endpoint-class",
                                         "value": "api-football/fixtures"}]},
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


class TestOmission(unittest.TestCase):
    """A8 — omission over fabrication, asserted on the document, not the helper.

    Every test here scans emitted output rather than calling ``_put``. A helper
    that drops placeholders proves nothing if one call site bypasses it, and the
    call sites are where this has gone wrong before.
    """

    def test_absent_site_emits_no_site_resource_and_no_location_property(self):
        doc = sport_schema_graph(MINIMAL, id_resolver=mint())
        self.assertNotIn("sport:Site", [n["@type"] for n in doc["@graph"]])
        self.assertNotIn("sport:location", typed(doc, "sport:Event")[0])

    def test_no_null_no_empty_string_and_no_placeholder_survives_anywhere(self):
        """Scanned over both fixtures, because the rich one is where an unmapped
        optional field has somewhere to leak from."""
        for label, observation in (("minimal", MINIMAL), ("rich", graph_observation())):
            blob = json.dumps(sport_schema_graph(observation, id_resolver=mint()))
            with self.subTest(fixture=label):
                self.assertNotIn("null", blob)
                self.assertNotIn('""', blob)
                for value in sorted(profile_module.PLACEHOLDER_VALUES):
                    if value:
                        self.assertNotIn('"{0}"'.format(value), blob)

    def test_absent_score_omits_the_property_rather_than_emitting_zero(self):
        """A pre-match fixture has no score. ``"0"`` is a claim that both sides
        have scored nothing, which is a different fact from not yet knowing."""
        observation = copy.deepcopy(MINIMAL)
        observation["observation"]["event"]["status"] = "not_started"
        for participant in observation["observation"]["participants"]:
            participant.pop("score")
        doc = sport_schema_graph(observation, id_resolver=mint())
        for node in doc["@graph"]:
            self.assertNotIn("sport:score", node)

    def test_a_genuine_zero_is_a_fact_and_survives(self):
        """The mirror of the test above, and the reason omission is not a
        truthiness test: ``0`` is knowledge, ``None`` is not."""
        observation = copy.deepcopy(MINIMAL)
        observation["observation"]["participants"][0]["score"] = "0"
        observation["observation"]["participants"][1]["score"] = 0
        scores = [p.get("sport:score") for p in
                  typed(sport_schema_graph(observation, id_resolver=mint()),
                        "sport:TeamParticipation")]
        self.assertEqual(scores, ["0", "0"])

    def test_a_placeholder_in_a_provider_field_is_dropped_not_forwarded(self):
        observation = copy.deepcopy(MINIMAL)
        observation["observation"]["competition"]["name"] = "Unknown Competition"
        observation["observation"]["event"]["label"] = "TBD"
        doc = sport_schema_graph(observation, id_resolver=mint())
        for node in doc["@graph"]:
            if node["@type"] in ("sport:Competition", "sport:Event"):
                self.assertNotIn("rdfs:label", node)

    def test_a_resource_left_with_no_facts_is_not_emitted_as_a_stub(self):
        """A node carrying only ``@id`` and ``@type`` reads as a described entity
        to every consumer and describes nothing. It also silently satisfies the
        non-vacuity check, which is worse than being absent."""
        observation = copy.deepcopy(MINIMAL)
        observation["observation"]["site"] = {"provider_id": "9101",
                                             "name": "Unknown Venue"}
        doc = sport_schema_graph(observation, id_resolver=mint())
        self.assertNotIn("sport:Site", [n["@type"] for n in doc["@graph"]])
        for node in doc["@graph"]:
            with self.subTest(node=node["@id"]):
                self.assertNotEqual(sorted(node), ["@id", "@type"])

    def test_an_unmapped_provider_status_omits_the_property_rather_than_guessing(self):
        """``vocab`` has no entry for this status, so there is nothing defensible
        to emit. The provider's own string survives in ``observation.raw``."""
        observation = copy.deepcopy(MINIMAL)
        observation["observation"]["event"]["status"] = "extra_time_pending"
        event = typed(sport_schema_graph(observation, id_resolver=mint()),
                      "sport:Event")[0]
        self.assertNotIn("sport:eventStatus", event)
        self.assertNotIn("extra_time_pending", json.dumps(event))

    def test_the_serializer_placeholder_set_is_the_profile_placeholder_set(self):
        """``serialize.py`` reaches ``PLACEHOLDERS`` through ``observation.py``
        rather than keeping a third copy. If that ever becomes a copy, the two
        halves of the repository start disagreeing about what a stub looks like.
        """
        self.assertEqual(PLACEHOLDERS, profile_module.PLACEHOLDER_VALUES)


def official_graph(node_id, type_name="sport:Event"):
    """The smallest document the profile will walk, with one official resource."""
    return {
        "@context": dict(load_context()),
        "@graph": [{"@id": node_id, "@type": type_name, "rdfs:label": "x"}],
    }


class TestCrosswalk(unittest.TestCase):
    """A9 — a provider identifier is evidence attached to an identity, never the
    identity itself (RFC 002 §5)."""

    def setUp(self):
        self.doc = sport_schema_graph(graph_observation(), id_resolver=mint())

    def test_provider_ids_are_separate_machina_typed_resources(self):
        crosswalk = typed(self.doc, "machina:ProviderIdentifier")
        self.assertTrue(crosswalk)
        node = crosswalk[0]
        self.assertEqual(node["machina:providerNamespace"], "api-football")
        self.assertIn("machina:providerId", node)
        self.assertIn("@id", node["machina:identifies"])

    def test_every_crosswalk_resource_points_at_a_resource_in_this_graph(self):
        ids = {n["@id"] for n in self.doc["@graph"]}
        for node in typed(self.doc, "machina:ProviderIdentifier"):
            self.assertIn(node["machina:identifies"]["@id"], ids)

    def test_official_resources_carry_no_machina_property(self):
        """The pinned shapes are ``sh:closed`` (RFC 001 §5.4), so one ``machina:``
        key on a ``sport:`` resource fails layer 2 for the whole document."""
        for node in self.doc["@graph"]:
            if str(node["@type"]).startswith("sport:"):
                with self.subTest(resource=node["@type"]):
                    self.assertEqual([k for k in node if k.startswith("machina:")], [])

    def test_crosswalk_resources_carry_no_official_property(self):
        """The mirror: a ``machina:``-typed resource is not an official resource
        and must not describe itself with official predicates either."""
        for node in typed(self.doc, "machina:ProviderIdentifier"):
            self.assertEqual([k for k in node if k.startswith("sport:")], [])

    def test_resolution_method_is_one_of_the_three_and_never_a_guess(self):
        """RFC 002 §5: ``provider-native``, ``ordinal-derived`` or ``declared``.
        There is no fourth value and no fuzzy matching in this phase."""
        for node in typed(self.doc, "machina:ProviderIdentifier"):
            self.assertIn(node["machina:resolutionMethod"],
                          ("provider-native", "ordinal-derived", "declared"))

    def test_the_envelope_crosswalk_lists_every_identified_entity(self):
        entries = provider_identifiers(graph_observation(), id_resolver=mint())
        self.assertEqual(
            [e["entity_type"] for e in entries],
            ["competition", "season", "phase", "site", "event", "team", "team",
             "athlete"],
        )
        for entry in entries:
            with self.subTest(entity=entry["entity_type"]):
                self.assertEqual(sorted(entry), [
                    "confidence", "entity_type", "evidence", "machina_id",
                    "provider_id", "provider_namespace", "resolution_method",
                ])

    def test_the_evidence_pointer_names_where_the_provider_id_came_from(self):
        """A crosswalk entry a reviewer cannot trace back to a field in the
        observation is an assertion with no source."""
        entries = provider_identifiers(graph_observation(), id_resolver=mint())
        by_type = {}
        for entry in entries:
            by_type.setdefault(entry["entity_type"], []).append(entry)
        self.assertEqual(by_type["event"][0]["evidence"],
                         "observation.event.provider_id")
        self.assertEqual(by_type["season"][0]["evidence"],
                         "observation.competition.season.provider_id")
        self.assertEqual(by_type["athlete"][0]["evidence"],
                         "observation.participants[2].provider_id")

    def test_the_envelope_crosswalk_and_the_graph_crosswalk_agree(self):
        """Two views of one fact. They are built from one entry list rather than
        two passes, because a second pass is a second chance to disagree."""
        entries = provider_identifiers(graph_observation(), id_resolver=mint())
        nodes = typed(self.doc, "machina:ProviderIdentifier")
        self.assertEqual(
            [(e["machina_id"], e["provider_id"]) for e in entries],
            [(n["machina:identifies"]["@id"], n["machina:providerId"]) for n in nodes],
        )

    def test_derived_structures_get_no_crosswalk_entry(self):
        """Participations, memberships and actions are structures this serializer
        derives, not entities the provider named. There is no provider identifier
        that could honestly be recorded for them."""
        entries = provider_identifiers(graph_observation(), id_resolver=mint())
        for kind in ("participation", "membership", "action"):
            self.assertNotIn(kind, [e["entity_type"] for e in entries])


class TestProviderIdAsResourceIdRule(unittest.TestCase):
    """A9 — the profile rejects a provider identifier used as canonical identity.

    This is the rule that makes the surrogate resolver load-bearing rather than
    advisory: without it, "provider IDs are evidence, never identity" is a
    sentence in an RFC that nothing enforces.
    """

    def test_profile_rejects_a_provider_id_used_as_a_resource_id(self):
        result = profile_module.check(official_graph("urn:apifootball:sport_event:1035842"))
        self.assertIn("provider-id-as-resource-id",
                      [f["code"] for f in result.findings])

    def test_the_finding_names_the_token_and_the_pointer(self):
        finding = next(f for f in profile_module.check(
            official_graph("urn:espn:event:401547")).findings
            if f["code"] == "provider-id-as-resource-id")
        self.assertEqual(finding["token"], "espn")
        self.assertEqual(finding["@id"], "urn:espn:event:401547")
        self.assertEqual(finding["pointer"], "/@graph/0")

    def test_every_known_provider_namespace_is_rejected(self):
        for token in sorted(profile_module.PROVIDER_NAMESPACE_TOKENS):
            with self.subTest(token=token):
                codes = [f["code"] for f in profile_module.check(
                    official_graph("urn:{0}:event:1".format(token))).findings]
                self.assertIn("provider-id-as-resource-id", codes)

    def test_the_tokens_are_derived_from_the_leak_rules_not_hand_listed(self):
        """A hand-listed set goes stale the moment a connector is added. Every
        provider in ``provider-leak-terms.json`` must be covered, in both the
        hyphenated and the run-together spelling a URN might use."""
        rules = json.loads(profile_module.RULES_PATH.read_text(encoding="utf-8"))
        for provider in sorted(rules["providers"]):
            with self.subTest(provider=provider):
                self.assertIn(provider, profile_module.PROVIDER_NAMESPACE_TOKENS)
                self.assertIn(provider.replace("-", ""),
                              profile_module.PROVIDER_NAMESPACE_TOKENS)

    def test_the_rule_does_not_fire_on_a_machina_typed_crosswalk_resource(self):
        """The crosswalk resource's whole job is to carry a provider identifier.
        Flagging it would make the rule fire on the fix for the defect."""
        document = {
            "@context": dict(load_context()),
            "@graph": [{
                "@id": "urn:machina:sports:provider-identifier:xabc",
                "@type": "machina:ProviderIdentifier",
                "machina:providerNamespace": "api-football",
                "machina:providerId": "39",
                "machina:resolutionMethod": "provider-native",
            }],
        }
        self.assertEqual(
            [f for f in profile_module.check(document).findings
             if f["code"] == "provider-id-as-resource-id"], [])

    def test_a_provider_id_in_a_property_value_is_not_this_rule(self):
        """Only ``@id`` is identity. A provider identifier as the *value* of a
        ``machina:`` evidence property is the sanctioned form, and conflating the
        two would leave no way to record the crosswalk at all."""
        document = {
            "@context": dict(load_context()),
            "@graph": [
                {"@id": "urn:machina:sports:event:xabc", "@type": "sport:Event",
                 "rdfs:label": "x"},
                {"@id": "urn:machina:sports:provider-identifier:xdef",
                 "@type": "machina:ProviderIdentifier",
                 "machina:identifies": {"@id": "urn:machina:sports:event:xabc"},
                 "machina:providerId": "urn:apifootball:sport_event:1035842"},
            ],
        }
        self.assertEqual(
            [f for f in profile_module.check(document).findings
             if f["code"] == "provider-id-as-resource-id"], [])

    def test_a_token_inside_a_larger_word_is_not_flagged(self):
        """The rule matches a delimited segment, not a bare substring. An opaque
        surrogate digest that happens to contain provider letters is not a
        provider identifier, and a rule that cried wolf there would be switched
        off rather than fixed."""
        self.assertEqual(
            [f for f in profile_module.check(
                official_graph("urn:machina:sports:event:xespnish401547")).findings
             if f["code"] == "provider-id-as-resource-id"], [])

    def test_a_hyphen_delimited_provider_token_is_still_flagged(self):
        """``urn:machina:…:espn-401547`` is the leak the substring rule was
        reaching for, and delimited matching still catches it."""
        codes = [f["code"] for f in profile_module.check(
            official_graph("urn:machina:sports:event:espn-401547")).findings]
        self.assertIn("provider-id-as-resource-id", codes)

    def test_the_graph_this_serializer_emits_is_clean_under_the_rule(self):
        """The point of the whole surrogate design, asserted end to end."""
        document = sport_schema_graph(graph_observation(), id_resolver=mint())
        self.assertEqual(
            [f for f in profile_module.check(document).findings
             if f["code"] == "provider-id-as-resource-id"], [])

    def test_a_surrogate_id_never_contains_a_provider_token_at_all(self):
        document = sport_schema_graph(graph_observation(), id_resolver=mint())
        for node in document["@graph"]:
            for token in sorted(profile_module.PROVIDER_NAMESPACE_TOKENS):
                with self.subTest(node=node["@id"], token=token):
                    self.assertNotIn(token, node["@id"])


class TestProvenanceBlock(unittest.TestCase):
    """A10 — provenance appears twice for two audiences, with the same facts.

    An envelope block for consumers reading JSON, one
    ``machina:ObservationProvenance`` resource for consumers reading RDF (RFC 002
    §5). Both are built from the observation, and a test below asserts they agree.
    """

    def block(self, document=None, resolver=None):
        return provenance_block(document or MINIMAL,
                                id_resolver=resolver or mint())["provenance"]

    def test_the_block_cites_the_pin_and_the_profile(self):
        block = self.block()
        self.assertEqual(block["upstream_pin"]["commit"],
                         "0e77bf8678f3702fe81c28673bede35efe47d633")
        self.assertEqual(block["upstream_pin"]["target_version"], "1.1")
        self.assertEqual(block["profile"], "machina-iptc-profile/1.1")
        self.assertEqual(block["observed_at"], "2026-03-01T22:05:00+00:00")
        self.assertEqual(block["serializer"],
                         {"name": "machina-iptc-serializer", "version": "1"})

    def test_the_pin_the_vendored_package_carries_is_the_pin_this_repo_verifies(self):
        """``serialize.py`` cannot import ``tools.iptc.reference``, so the package
        carries the pin itself. Same discipline as ``PLACEHOLDERS`` and
        ``shared-context.json``: a second copy is only safe while something
        asserts it is a copy. A conformance claim citing a pin the repository does
        not actually verify is worse than no claim.
        """
        from tools.iptc import reference

        self.assertEqual(canonical.UPSTREAM_COMMIT, reference.UPSTREAM_COMMIT)
        self.assertEqual(canonical.UPSTREAM_REPOSITORY, reference.UPSTREAM_REPOSITORY)
        self.assertEqual(canonical.UPSTREAM_TARGET_VERSION, reference.TARGET_VERSION)

    def test_the_observation_provider_and_adapter_are_carried_verbatim(self):
        block = self.block()
        self.assertEqual(block["provider"],
                         {"namespace": "api-football", "family": "licensed"})
        self.assertEqual(block["adapter"]["version"], "0.31.0")
        self.assertEqual(block["rights"], MINIMAL["observation"]["rights"])

    def test_no_url_or_credential_is_recorded(self):
        """``source_refs`` records an endpoint *class*. A URL is a request-shaped
        artefact, and it is how an API key or a licensed path ends up committed to
        a fixture file."""
        blob = json.dumps(self.block(graph_observation()))
        blob = blob.replace("https://github.com/iptc/sport-schema", "")
        for token in ("http://", "https://", "key=", "token=", "Authorization",
                      "secret", "?"):
            with self.subTest(token=token):
                self.assertNotIn(token, blob)

    def test_determinism_is_declared_by_the_resolver_not_asserted_here(self):
        """The resolver is injected precisely so it can be swapped, so the
        serializer cannot know its digest. It reads what the resolver declares
        about itself instead of restating the current one from memory."""
        block = self.block()
        self.assertEqual(block["determinism"], {
            "id_strategy": "provider-scoped-surrogate",
            "digest": "blake2b-128",
            "canonical_id_service": "not-available-in-this-phase",
        })
        self.assertEqual(surrogate_resolver("api-football").strategy,
                         block["determinism"])

    def test_a_resolver_that_declares_nothing_omits_the_determinism_block(self):
        """Omission over fabrication reaches provenance too. A future injected
        resolver that says nothing about itself must produce no claim, not the
        previous resolver's claim."""
        def anonymous(kind, *parts):
            return "urn:machina:sports:{0}:x0".format(kind)

        self.assertNotIn("determinism", self.block(resolver=anonymous))

    def test_source_refs_are_omitted_when_the_adapter_supplies_none(self):
        self.assertNotIn("source_refs", self.block())

    def test_source_refs_carry_kind_value_and_note_and_nothing_else(self):
        block = self.block(graph_observation())
        self.assertEqual(block["source_refs"], [{
            "kind": "endpoint-class",
            "value": "api-football/fixtures",
            "note": "endpoint class only; no URL, query or credential is recorded",
        }])

    def test_a_source_ref_holding_a_url_is_rejected_at_the_boundary(self):
        """Stopped by ``validate_observation`` rather than stripped by the
        serializer. Stripping would let a fixture carrying a credentialled URL
        validate clean, and the fixture is the thing that gets committed."""
        observation = copy.deepcopy(graph_observation())
        observation["observation"]["adapter"]["source_refs"] = [
            {"kind": "endpoint-class",
             "value": "https://v3.football.api-sports.io/fixtures?id=9001"}
        ]
        errors = validate_observation(observation)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("source_refs", errors[0])

    def test_the_rich_fixture_with_source_refs_is_still_a_valid_observation(self):
        self.assertEqual(validate_observation(graph_observation()), [])


class TestProvenanceResource(unittest.TestCase):
    """A10 — the RDF half of the same facts, on its own ``machina:`` resource."""

    def setUp(self):
        self.doc = sport_schema_graph(MINIMAL, id_resolver=mint())

    def test_the_graph_carries_one_provenance_resource_describing_the_event(self):
        event = typed(self.doc, "sport:Event")[0]
        provenance = typed(self.doc, "machina:ObservationProvenance")
        self.assertEqual(len(provenance), 1)
        self.assertEqual(provenance[0]["machina:describes"], {"@id": event["@id"]})
        self.assertEqual(provenance[0]["machina:observedAt"],
                         {"@value": "2026-03-01T22:05:00+00:00",
                          "@type": "xsd:dateTime"})

    def test_the_provenance_resource_is_not_an_official_resource(self):
        """It is `machina:`-typed and carries only `machina:` and `rdfs:` keys.
        A `machina:` property on a `sport:` resource fails layer 2 for the whole
        document, which is why this is a sibling and not an annotation."""
        provenance = typed(self.doc, "machina:ObservationProvenance")[0]
        for key in provenance:
            with self.subTest(key=key):
                self.assertFalse(key.startswith("sport:"))

    def test_the_resource_and_the_block_agree_on_every_shared_fact(self):
        """Two representations of one observation. They are allowed to carry
        different amounts of detail; they are not allowed to disagree."""
        provenance = typed(self.doc, "machina:ObservationProvenance")[0]
        block = provenance_block(MINIMAL, id_resolver=mint())["provenance"]
        self.assertEqual(provenance["machina:observedAt"]["@value"],
                         block["observed_at"])
        self.assertEqual(provenance["machina:providerNamespace"],
                         block["provider"]["namespace"])
        self.assertEqual(provenance["machina:adapterVersion"],
                         block["adapter"]["version"])
        self.assertEqual(provenance["machina:serializerVersion"],
                         block["serializer"]["version"])
        self.assertEqual(provenance["machina:rightsClass"],
                         block["rights"]["data_class"])


def view_of(observation, resolver=None):
    return event_view(observation, id_resolver=resolver or mint())["event_view"]


def without_raw(view):
    """``view`` minus the provider payload.

    The RDF-token scans below exclude ``provider.raw`` deliberately. ``raw`` is
    the provider's own bytes, and this fixture's payload genuinely contains
    ``"@type": "provider-payload"``. Rewriting a provider payload to satisfy our
    own scan would destroy the one field whose value is being an unaltered
    record, so the rule is "no RDF in anything the serializer authored" rather
    than "no RDF anywhere".
    """
    stripped = copy.deepcopy(view)
    stripped.get("provider", {}).pop("raw", None)
    return stripped


class TestEventView(unittest.TestCase):
    """A11 — a compact non-RDF projection, derived from the observation alone."""

    def test_the_view_carries_no_rdf_keyword_term_or_node_reference(self):
        """``machina:`` is deliberately not in this list. The view's identifiers
        are ``urn:machina:sports:…`` URNs, which are Machina identifiers rather
        than RDF terms — the ``machina:`` *prefix* only becomes a term when it
        heads a key, and the CURIE-key test below is what covers that.
        """
        for label, observation in (("minimal", MINIMAL), ("rich", graph_observation())):
            blob = json.dumps(without_raw(view_of(observation)))
            with self.subTest(fixture=label):
                for token in ("@context", "@graph", "@type", "@id", "@value",
                              "sport:", "rdfs:", "medtop:", "machina:Provider",
                              "machina:Observation"):
                    self.assertNotIn(token, blob)

    def test_no_key_anywhere_in_the_view_is_a_curie(self):
        """A statistic keyed ``spsocstat:shotsTotal`` would drag the RDF
        vocabulary into a projection whose whole promise is not carrying it. The
        local name is what a consumer of the compact view wants."""
        def keys(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    yield key
                    for found in keys(value):
                        yield found
            elif isinstance(node, list):
                for item in node:
                    for found in keys(item):
                        yield found

        for key in keys(without_raw(view_of(graph_observation()))):
            with self.subTest(key=key):
                self.assertNotIn(":", key)

    def test_the_view_is_compact_and_role_addressable(self):
        view = view_of(MINIMAL)
        self.assertEqual(view["status"], "closed")
        self.assertEqual([p["role"] for p in view["participants"]], ["home", "away"])
        self.assertEqual(view["provider"]["namespace"], "api-football")

    def test_the_provider_status_survives_verbatim_even_when_unmapped(self):
        """The graph omits an unmapped status because it has nothing defensible to
        emit. The view is where the provider's own word is preserved, and that is
        the whole reason two serializers exist."""
        observation = copy.deepcopy(MINIMAL)
        observation["observation"]["event"]["status"] = "extra_time_pending"
        self.assertEqual(view_of(observation)["status"], "extra_time_pending")

    def test_the_view_ids_agree_with_the_graph_without_being_derived_from_it(self):
        resolver = mint()
        view = view_of(MINIMAL, resolver)
        graph = sport_schema_graph(MINIMAL, id_resolver=resolver)
        self.assertEqual(view["event_id"], typed(graph, "sport:Event")[0]["@id"])
        team_ids = {t["@id"] for t in typed(graph, "sport:Team")}
        self.assertEqual({p["id"] for p in view["participants"]}, team_ids)

    def test_event_view_does_not_call_sport_schema_graph(self):
        """Asserted by making the call impossible, not by reading the source.

        Two serializers reading one input is the property that lets either be
        replaced without silently corrupting the other. If ``event_view`` ever
        derives from the graph, that property is gone and this test is the only
        thing that would notice.
        """
        def refuse(*args, **kwargs):
            raise AssertionError("event_view called sport_schema_graph")

        original = serialize_module.sport_schema_graph
        serialize_module.sport_schema_graph = refuse
        try:
            view = view_of(graph_observation())
        finally:
            serialize_module.sport_schema_graph = original
        self.assertEqual(view["event_id"],
                         typed(sport_schema_graph(graph_observation(),
                                                  id_resolver=mint()),
                               "sport:Event")[0]["@id"])

    def test_absent_facts_are_absent_keys(self):
        view = view_of(MINIMAL)
        for key in ("site", "phase", "season", "clock", "actions", "players",
                    "attendance", "outcome_type"):
            with self.subTest(key=key):
                self.assertNotIn(key, view)

    def test_the_rich_view_carries_what_the_graph_had_to_drop(self):
        """The clock has no place in a closed ``EventShape``, and ``sport:Site``
        admits nothing but a label. Those facts are real, so this is where they
        live rather than being forced into a shape that rejects them."""
        view = view_of(graph_observation())
        self.assertEqual(view["clock"], {"minute": "90", "period": "2"})
        self.assertEqual(view["site"], {"id": view["site"]["id"],
                                        "name": "Synthetic Home Ground",
                                        "city": "Synthetic City",
                                        "country": "SYN"})

    def test_the_provider_raw_payload_lives_only_here(self):
        view = view_of(graph_observation())
        self.assertEqual(view["provider"]["raw"],
                         graph_observation()["observation"]["raw"])
        self.assertNotIn("provider-payload",
                         json.dumps(sport_schema_graph(graph_observation(),
                                                       id_resolver=mint())))

    def test_the_unmapped_soccer_action_detail_survives_in_the_view(self):
        """``"Normal Goal"`` has no pinned vocabulary, so the graph cannot carry
        it (RFC 001 §9.2). It is not lost: it is here, and in ``provider.raw``."""
        view = view_of(graph_observation())
        self.assertEqual(view["actions"][0]["label"], "Goal")
        self.assertIn("Normal Goal", json.dumps(view["provider"]["raw"]))

    def test_statistics_are_keyed_by_local_name_and_kept_as_strings(self):
        view = view_of(graph_observation())
        home = next(p for p in view["participants"] if p["role"] == "home")
        self.assertEqual(home["statistics"],
                         {"shotsTotal": "14", "timeOfPossessionPercentage": "57.0"})

    def test_players_are_addressable_and_point_at_their_team(self):
        view = view_of(graph_observation())
        self.assertEqual(len(view["players"]), 1)
        player = view["players"][0]
        home = next(p for p in view["participants"] if p["role"] == "home")
        self.assertEqual(player["name"], "Synthetic Scorer")
        self.assertEqual(player["team_id"], home["id"])
        self.assertEqual(player["status"], "starter")
        self.assertEqual(player["position"], "forward")

    def test_no_placeholder_or_null_reaches_the_view_either(self):
        observation = copy.deepcopy(MINIMAL)
        observation["observation"]["site"] = {"provider_id": "9101",
                                             "name": "Unknown Venue"}
        blob = json.dumps(without_raw(view_of(observation)))
        self.assertNotIn("null", blob)
        for value in sorted(profile_module.PLACEHOLDER_VALUES):
            if value:
                self.assertNotIn('"{0}"'.format(value), blob)

    def test_the_view_is_byte_stable_across_runs(self):
        self.assertEqual(json.dumps(view_of(graph_observation())),
                         json.dumps(view_of(graph_observation())))


def envelope_of(observation=None, resolver=None):
    return canonical_envelope(observation or graph_observation(),
                              id_resolver=resolver or mint())


def licensed(prototype_only=False, commercial_use=True,
             data_class="licensed-redistributable"):
    observation = copy.deepcopy(graph_observation())
    observation["observation"]["rights"] = {"data_class": data_class,
                                           "prototype_only": prototype_only,
                                           "commercial_use": commercial_use}
    return observation


class TestCanonicalEnvelope(unittest.TestCase):
    """A12 — the envelope composes the four builders and claims both versions."""

    def test_the_envelope_carries_every_part_rfc_002_names(self):
        block = envelope_of()["machina_sports_schema"]
        self.assertEqual(sorted(block), [
            "capabilities", "event_view", "profile", "provenance", "provider_ids",
            "rights", "schema_version", "sport_schema_graph",
        ])
        self.assertEqual(block["schema_version"], "machina-sports-schema/1")
        self.assertEqual(block["profile"], "machina-iptc-profile/1.1")

    def test_the_envelope_has_no_key_beyond_the_one_block(self):
        self.assertEqual(sorted(envelope_of()), ["machina_sports_schema"])

    def test_each_part_is_the_builder_output_and_not_a_reimplementation(self):
        """Composition, asserted. A second code path producing the same shape is
        the thing that drifts."""
        observation = graph_observation()
        block = envelope_of(observation)["machina_sports_schema"]
        self.assertEqual(block["sport_schema_graph"],
                         sport_schema_graph(observation, id_resolver=mint()))
        self.assertEqual(block["event_view"],
                         event_view(observation, id_resolver=mint())["event_view"])
        self.assertEqual(block["provenance"],
                         provenance_block(observation, id_resolver=mint())["provenance"])
        self.assertEqual(block["provider_ids"],
                         provider_identifiers(observation, id_resolver=mint()))
        self.assertEqual(block["capabilities"],
                         capability_report(observation)["capabilities"])
        self.assertEqual(block["rights"], observation["observation"]["rights"])

    def test_one_resolver_serves_the_whole_envelope_consistently(self):
        block = envelope_of()["machina_sports_schema"]
        event = typed(block["sport_schema_graph"], "sport:Event")[0]
        self.assertEqual(block["event_view"]["event_id"], event["@id"])
        crosswalk = [e for e in block["provider_ids"] if e["entity_type"] == "event"]
        self.assertEqual(crosswalk[0]["machina_id"], event["@id"])

    def test_an_invalid_observation_raises_rather_than_emitting_a_bad_envelope(self):
        """The serializer is not a repair shop. An envelope built from an invalid
        observation is a conformance claim about a document nobody validated."""
        broken = copy.deepcopy(MINIMAL)
        del broken["observation"]["rights"]
        broken["observation"]["event"]["label"] = "Unknown"
        with self.assertRaises(ValueError) as raised:
            envelope_of(broken)
        message = str(raised.exception)
        self.assertIn("observation.rights: required field is missing", message)
        self.assertIn("event.label", message)

    def test_the_envelope_is_byte_stable_across_runs(self):
        self.assertEqual(json.dumps(envelope_of()), json.dumps(envelope_of()))

    def test_capabilities_are_reported_non_vacuously_for_the_rich_fixture(self):
        """The rich fixture is deliberately complete enough to reach the top tier.
        A capability report that satisfied nothing would let every assertion above
        pass while proving the serializer can emit an empty envelope."""
        capabilities = envelope_of()["machina_sports_schema"]["capabilities"]
        self.assertEqual(capabilities["tier"], "advanced")
        self.assertEqual(capabilities["tiers_satisfied"], ["core", "live", "advanced"])
        self.assertEqual(capabilities["violations"], [])
        for name in ("event.identity", "event.participants", "event.actions",
                     "participant.player_statistics", "provenance"):
            with self.subTest(capability=name):
                self.assertIn(name, capabilities["present"])

    def test_capabilities_absent_for_the_right_reason(self):
        """``not_expressible`` separates "the provider withheld it" from
        "``canonical-observation/1`` has no field that could carry it". Only one of
        those is a provider conversation."""
        capabilities = envelope_of()["machina_sports_schema"]["capabilities"]
        self.assertIn("event.tracking", capabilities["not_expressible"])
        self.assertNotIn("event.live_statistics", capabilities["not_expressible"])


class TestRightsGate(unittest.TestCase):
    """A12 — a production consumer refuses prototype-only data rather than
    downgrading quietly. Rights are not decoration (RFC 002 §9)."""

    def test_prototype_only_rights_fail_closed_for_a_production_consumer(self):
        envelope = canonical_envelope(
            MINIMAL, id_resolver=surrogate_resolver("sports-skills/espn"))
        self.assertEqual(rights_findings(envelope, consumer_tier="prototype"), [])
        findings = rights_findings(envelope, consumer_tier="production")
        self.assertEqual([f["code"] for f in findings], ["rights-prototype-only"])

    def test_the_finding_names_the_tier_and_the_class_it_refused(self):
        envelope = canonical_envelope(
            MINIMAL, id_resolver=surrogate_resolver("sports-skills/espn"))
        finding = rights_findings(envelope, consumer_tier="production")[0]
        self.assertEqual(finding["consumer_tier"], "production")
        self.assertEqual(finding["data_class"], "public-non-commercial")
        self.assertIn("prototype", finding["detail"])

    def test_a_prototype_only_envelope_reports_exactly_one_finding_not_a_cascade(self):
        """``prototype_only`` and ``commercial_use: false`` travel together on
        every open-data envelope. Reporting both buries the one line that names
        the fix, which is the same reasoning ``_check_rights`` uses on absence."""
        envelope = canonical_envelope(
            MINIMAL, id_resolver=surrogate_resolver("sports-skills/espn"))
        self.assertEqual(len(rights_findings(envelope, consumer_tier="production")), 1)

    def test_non_commercial_alone_still_fails_a_production_consumer(self):
        envelope = envelope_of(licensed(prototype_only=False, commercial_use=False))
        self.assertEqual([f["code"] for f in
                          rights_findings(envelope, consumer_tier="production")],
                         ["rights-non-commercial"])

    def test_licensed_commercial_data_passes_a_production_consumer(self):
        envelope = envelope_of(licensed())
        self.assertEqual(rights_findings(envelope, consumer_tier="production"), [])
        self.assertEqual(rights_findings(envelope, consumer_tier="prototype"), [])

    def test_the_default_tier_is_the_strict_one(self):
        """A caller who forgets the argument gets the safe answer. A gate whose
        default is permissive is a gate nobody notices is off."""
        envelope = canonical_envelope(
            MINIMAL, id_resolver=surrogate_resolver("sports-skills/espn"))
        self.assertEqual([f["code"] for f in rights_findings(envelope)],
                         ["rights-prototype-only"])

    def test_an_unreadable_rights_block_fails_closed(self):
        """No rights block means no licence claim, which is not the same as a
        permissive one. Every path that cannot read rights must refuse."""
        for label, envelope in (
            ("no envelope", {}),
            ("no block", {"machina_sports_schema": {}}),
            ("rights not an object", {"machina_sports_schema": {"rights": "public"}}),
            ("flags not booleans", {"machina_sports_schema": {
                "rights": {"data_class": "x", "prototype_only": "no",
                           "commercial_use": "yes"}}}),
        ):
            with self.subTest(case=label):
                codes = [f["code"] for f in
                         rights_findings(envelope, consumer_tier="production")]
                self.assertEqual(codes, ["rights-unreadable"])

    def test_an_unknown_consumer_tier_is_refused_rather_than_guessed(self):
        """A typo'd tier must not be read as the permissive one. It returns a
        finding rather than raising, because a raise can be caught and mistaken
        for 'no findings' while a finding is a refusal by construction."""
        envelope = envelope_of(licensed())
        codes = [f["code"] for f in rights_findings(envelope, consumer_tier="prod")]
        self.assertEqual(codes, ["rights-unknown-consumer-tier"])

    def test_every_known_tier_is_accepted(self):
        envelope = envelope_of(licensed())
        for tier in sorted(validate_graph.CONSUMER_TIERS):
            with self.subTest(tier=tier):
                self.assertEqual(rights_findings(envelope, consumer_tier=tier), [])


class TestValidateGraphCli(unittest.TestCase):
    """A12 — the new flag is additive; the existing CLI is untouched."""

    def test_the_consumer_tier_flag_defaults_to_prototype(self):
        parser = validate_graph.build_parser()
        self.assertEqual(parser.parse_args([]).consumer_tier, "prototype")

    def test_the_flag_rejects_a_tier_the_gate_does_not_know(self):
        parser = validate_graph.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--consumer-tier", "prod"])

    def test_the_existing_invocation_still_validates_a_fixture(self):
        """A conforming fixture from PR 1, through the unchanged code path."""
        self.assertEqual(validate_graph.main(["--all", "--json"]), 1)


class TestFourLayerConformance(unittest.TestCase):
    """The proof A1-A6 could not give: a conforming document falls out of the
    contract, checked by the PR 1 harness rather than by assertion.

    The graph is built here from the synthetic observation and written to a
    temporary file inside the repository, because ``validate_document`` reports
    paths relative to the repo root.
    """

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(dir=str(REPO_ROOT))
        path = Path(cls.temporary.name) / "synthetic-canonical-graph.json"
        document = envelope_of()["machina_sports_schema"]["sport_schema_graph"]
        path.write_text(json.dumps(document, indent=2), encoding="utf-8")
        cls.result = validate_document(path, "synthetic-canonical",
                                       repo_root=REPO_ROOT)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_all_four_layers_pass(self):
        for layer in ("jsonld_parse", "official_shacl", "machina_profile",
                      "controlled_vocabulary"):
            with self.subTest(layer=layer):
                self.assertTrue(self.result.layers[layer]["ok"],
                                self.result.layers[layer])

    def test_the_shacl_pass_is_not_vacuous(self):
        """A SHACL run over zero official-class instances 'conforms'. That is the
        failure mode this whole programme exists to catch."""
        shacl = self.result.layers["official_shacl"]["detail"]
        self.assertFalse(shacl["vacuous"])
        self.assertGreater(shacl["official_class_instances"], 0)
        self.assertEqual(shacl["result_count"], 0)

    def test_all_four_counters_are_zero(self):
        for counter in ("unknown_sport_terms", "invalid_newscode_values",
                        "duplicate_resource_ids",
                        "provider_properties_in_iptc_namespace"):
            with self.subTest(counter=counter):
                self.assertEqual(self.result.counters[counter], 0)

    def test_the_controlled_vocabulary_layer_checked_real_codes(self):
        """Layer 4 passing on zero NewsCodes would be the vacuity failure again,
        one layer down."""
        detail = self.result.layers["controlled_vocabulary"]["detail"]
        self.assertGreater(len(detail["valid"]), 0)
        for key in ("invalid", "undeclared_prefix", "unverifiable"):
            with self.subTest(key=key):
                self.assertEqual(detail[key], [])

    def test_the_document_conforms_overall(self):
        self.assertTrue(self.result.conforms)



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
    "rights.py",
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

    def test_rfc_002_names_every_file_that_has_to_be_vendored(self):
        """A vendoring list in prose that omits a runtime file is a broken install
        of a published package, discovered by whoever copies the list.

        Mechanical for the same reason RFC 002 §1.1's required list is: A7 added
        two files to this boundary (``vocab.py``, because ``serialize.py`` needs
        its tables and ``sports-skills`` cannot import this repository, and
        ``shared-context.json``, because there is no ``tools.iptc.context``
        downstream) and prose does not notice when that happens.
        """
        section = rfc_section(RFC_002_PATH, "10")
        for name in VENDORED_RUNTIME_MODULES + VENDORED_RUNTIME_DATA:
            with self.subTest(vendored=name):
                self.assertIn(
                    "`{0}`".format(name), section,
                    "{0} is vendored and RFC 002 §10 does not name it".format(name),
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


class TestTheRightsGateIsOneVendorableImplementation(unittest.TestCase):
    """The rights gate is a cross-repository rule, so it has to be vendorable.

    ``sports-skills`` cannot import this repository, and a gate reimplemented
    downstream is the same failure RFC 002 §10 exists to prevent for the
    serializer: two copies of one contract diverge, and the copy that drifts is
    the one deciding whether prototype-only data reaches a commercial surface.

    So the rule lives in ``canonical/rights.py`` beside the modules that already
    cross the boundary, and ``validate.py`` / ``validate_graph.py`` re-export it.
    Identity — ``is``, not equality of behaviour — is what makes that a fact
    rather than a convention someone will helpfully "clean up" into a second
    implementation.
    """

    #: The two paths RFC 002 §9 and every existing caller import the gate by.
    RE_EXPORTS = ("tools.iptc.validate", "tools.iptc.validate_graph")

    def test_the_library_re_export_is_the_canonical_function_itself(self):
        self.assertIs(validate_module.rights_findings,
                      rights_module.rights_findings)

    def test_the_cli_module_re_export_is_the_canonical_function_itself(self):
        """RFC 002 §9 names ``validate_graph.rights_findings``, so that name has
        to resolve to the vendorable implementation and not to a wrapper."""
        self.assertIs(validate_graph.rights_findings,
                      rights_module.rights_findings)

    def test_the_gate_the_cli_calls_is_defined_in_the_vendored_module(self):
        """``__module__`` is the check a reader can make without a debugger: it
        says where the code that decided actually lives."""
        for path in self.RE_EXPORTS:
            with self.subTest(caller=path):
                self.assertEqual(sys.modules[path].rights_findings.__module__,
                                 "tools.iptc.canonical.rights")

    def test_no_caller_defines_a_second_copy_of_the_rule(self):
        """A re-export that is really a reimplementation passes every behavioural
        test on the day it lands and disagrees the first time either side is
        fixed. The only definition allowed is the vendorable one."""
        for name in ("validate.py", "validate_graph.py"):
            source = (REPO_ROOT / "tools/iptc" / name).read_text(encoding="utf-8")
            tree = ast.parse(source, filename=name)
            defined = [node.name for node in ast.walk(tree)
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
            with self.subTest(module=name):
                self.assertNotIn("rights_findings", defined)

    def test_the_tier_vocabulary_is_not_a_second_copy_either(self):
        """A gate whose caller carries its own tier list can accept a tier the
        gate refuses, which is a permissive disagreement — the worst direction."""
        self.assertIs(validate_module.CONSUMER_TIERS, rights_module.CONSUMER_TIERS)
        self.assertIs(validate_graph.CONSUMER_TIERS, rights_module.CONSUMER_TIERS)
        self.assertEqual(validate_module.STRICT_CONSUMER_TIER,
                         rights_module.STRICT_CONSUMER_TIER)

    def test_the_vendored_gate_reads_the_envelope_key_the_serializer_writes(self):
        """The gate has to find the block in a real envelope, not just in the
        hand-built dicts the negative cases use, and the harness must read that
        key from the gate rather than keeping a third copy of the literal."""
        envelope = envelope_of()
        self.assertIn(rights_module.ENVELOPE_KEY, envelope)
        self.assertIs(validate_module.ENVELOPE_KEY, rights_module.ENVELOPE_KEY)


def canonical_pin() -> str:
    from tools.iptc.reference import UPSTREAM_COMMIT

    return UPSTREAM_COMMIT


if __name__ == "__main__":
    unittest.main(verbosity=2)
