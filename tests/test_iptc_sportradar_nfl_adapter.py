"""Tests for the Sportradar NFL canonical adapter (PR 2, task A15b.2).

Run from the repository root:

    python3 tests/test_iptc_sportradar_nfl_adapter.py -v

Run the file directly, for the same reason as
``tests/test_iptc_canonical_serializer.py``: ``tests/`` is a namespace directory
with no ``__init__.py``, so ``-m unittest tests.<module>`` can be shadowed by an
installed distribution that ships a top-level regular ``tests`` package.

A focused file per provider, on purpose: a failure here names Sportradar NFL
rather than "the canonical suite", and the four-layer assertion block is
deliberately repeated rather than factored into a shared loop (A14 handoff
item 1, restated by A15b).

**There is no raw Sportradar NFL payload in this repository.** The only evidence
is ``tools/iptc/fixtures/baseline/sportradar-nfl-event.json`` — a document PR 1
hand-authored from the literal key set of ``iptc-sportradar-event-nfl-mapping``.
It is therefore a **legacy mapping-contract shape**: the output of Machina's own
mapping, two removes from what Sportradar sends, and synthetic throughout. No
Sportradar endpoint was called, no credential exists in this repository and there
is no network access in this harness. Calling this row provider data, or a
commercial entitlement, would be a claim nothing here supports.

What this file defends beyond the tennis row:

1. **American football is its own sport, and the medtop says so.**
   ``medtop:20000823``, checked against the pinned mediatopic scheme. The source
   says ``schema:sportName: "nfl"``, which is a league rather than a sport; the
   adapter reads it as the discriminator it is and asserts the sport itself.
2. **Two teams, with alignment and scores as strings.** This is the team-shaped
   counterpart to the tennis row, on the same serializer.
3. **The competition and season identifiers are mapping constants, not
   Sportradar identifiers, and this file says so out loud.** The mapping
   hardcodes ``urn:sportradar:competition:nfl`` and
   ``urn:sportradar:season:2025``; the event, venue and team identifiers really
   do come from provider fields. That distinction is the whole value of a
   crosswalk, so it is asserted rather than left to prose.
4. **A 24-17 scoreline produces no winner.** The source states no winner, and
   comparing two numbers is inference, not observation.
5. **The raw Sportradar period object the mapping smuggles under
   ``sport:score.sport:halfTime`` never reaches the corrected output.** It is the
   provider-leak defect the baseline row is fixtured for.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.iptc import cli_support  # noqa: E402
from tools.iptc import profile as profile_module  # noqa: E402
from tools.iptc import report as report_module  # noqa: E402
from tools.iptc.canonical.adapters import sportradar_nfl  # noqa: E402
from tools.iptc.canonical.ids import surrogate_resolver  # noqa: E402
from tools.iptc.canonical.observation import validate_observation  # noqa: E402
from tools.iptc.canonical.serialize import canonical_envelope  # noqa: E402
from tools.iptc.validate import validate_document  # noqa: E402

#: The source evidence: PR 1's frozen baseline fixture for this mapping. READ
#: ONLY — it is the "before" document the corrected output is measured against,
#: and this task does not edit it.
SOURCE_PATH = (REPO_ROOT / "tools/iptc/fixtures/baseline"
               / "sportradar-nfl-event.json")

OBSERVATION_PATH = (REPO_ROOT
                    / "tools/iptc/fixtures/observations"
                    / "sportradar-nfl-observation.json")
GRAPH_PATH = (REPO_ROOT / "tools/iptc/fixtures/corrected"
              / "sportradar-nfl-graph.json")
ENVELOPE_PATH = (REPO_ROOT / "tools/iptc/fixtures/corrected"
                 / "sportradar-nfl-envelope.json")

#: Fixed, so the corrected fixtures are reproducible. Nothing in the adapter or
#: the serializer reads the clock; this is the one time value, and it is an input.
OBSERVED_AT = "2026-03-01T22:05:00+00:00"

SOURCE = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))


def observation():
    return sportradar_nfl.to_observation(SOURCE, observed_at=OBSERVED_AT)


def envelope():
    return canonical_envelope(observation(),
                              id_resolver=surrogate_resolver("sportradar-nfl"))


def serialized(document):
    """The exact bytes a corrected fixture is checked in as."""
    return json.dumps(document, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


class TestAdapterOutputIsAValidObservation(unittest.TestCase):
    """``validate_observation`` is the adapter's acceptance test (RFC 002 §1)."""

    def test_the_observation_is_valid(self):
        self.assertEqual(validate_observation(observation()), [])

    def test_the_document_claims_the_canonical_observation_contract(self):
        self.assertEqual(observation()["schema_version"], "canonical-observation/1")

    def test_the_top_level_document_carries_nothing_but_the_observation(self):
        self.assertEqual(sorted(observation()), ["observation", "schema_version"])

    def test_observed_at_is_the_caller_input_and_is_keyword_only(self):
        self.assertEqual(observation()["observation"]["observed_at"], OBSERVED_AT)
        with self.assertRaises(TypeError):
            sportradar_nfl.to_observation(SOURCE, OBSERVED_AT)

    def test_the_adapter_reads_the_source_without_mutating_it(self):
        before = copy.deepcopy(SOURCE)
        sportradar_nfl.to_observation(SOURCE, observed_at=OBSERVED_AT)
        self.assertEqual(SOURCE, before)


class TestTheSourceIsLabelledForWhatItIs(unittest.TestCase):
    """No raw Sportradar NFL payload exists here, so this row may not borrow the
    soccer row's data class."""

    def test_the_data_class_says_legacy_mapping_contract_shape(self):
        rights = observation()["observation"]["rights"]
        self.assertEqual(rights["data_class"], "legacy-mapping-contract-shape")
        self.assertEqual(rights["data_class"], sportradar_nfl.RIGHTS_DATA_CLASS)

    def test_the_data_class_is_not_the_one_a_real_provider_example_earns(self):
        self.assertNotEqual(sportradar_nfl.RIGHTS_DATA_CLASS,
                            "licensed-provider-example-fixture")
        for word in ("redistributable", "provider-example", "entitlement",
                     "production"):
            with self.subTest(word=word):
                self.assertNotIn(word, sportradar_nfl.RIGHTS_DATA_CLASS)

    def test_the_source_ref_names_the_mapping_rather_than_an_endpoint(self):
        refs = observation()["observation"]["adapter"]["source_refs"]
        self.assertEqual([ref["kind"] for ref in refs], ["legacy-mapping-output"])
        self.assertEqual(refs[0]["value"], "iptc-sportradar-event-nfl-mapping")
        self.assertIn("not raw provider data", refs[0]["note"])

    def test_no_source_ref_is_request_shaped(self):
        for ref in observation()["observation"]["adapter"]["source_refs"]:
            for marker in ("://", "?", "&", "key=", "token=", "secret"):
                with self.subTest(marker=marker):
                    self.assertNotIn(marker, ref["value"])

    def test_the_rights_block_refuses_a_commercial_reading(self):
        rights = observation()["observation"]["rights"]
        self.assertIs(rights["prototype_only"], True)
        self.assertIs(rights["commercial_use"], False)

    def test_the_provider_namespace_is_per_feed_and_the_family_is_licensed(self):
        """The legacy NFL and MLB mappings both mint ``urn:sportradar:team:<id>``
        with no sport in the stem, so their identifier spaces collide in the old
        model. A per-feed crosswalk namespace is what keeps them apart here."""
        self.assertEqual(observation()["observation"]["provider"],
                         {"namespace": "sportradar-nfl", "family": "licensed"})

    def test_the_adapter_identifies_itself(self):
        adapter = observation()["observation"]["adapter"]
        self.assertEqual(adapter["name"],
                         "tools.iptc.canonical.adapters.sportradar_nfl")
        self.assertTrue(adapter["version"])


class TestProviderFactsAreReadCorrectly(unittest.TestCase):
    """Every value below is traceable to one key of the checked-in source."""

    def setUp(self):
        self.observation = observation()["observation"]

    def test_the_event_identifier_is_the_sportradar_one_not_machinas_urn(self):
        event = self.observation["event"]
        self.assertEqual(event["provider_id"],
                         "00000000-0000-4000-8000-000000009001")
        self.assertEqual(event["start_time"], "2025-11-09T18:00:00+00:00")

    def test_the_status_is_the_canonical_key_not_the_provider_code(self):
        self.assertEqual(self.observation["event"]["status"], "closed")

    def test_only_sport_status_is_read_and_not_the_mappings_duplicate(self):
        """The mapping writes the same expression into ``sport:status`` and
        ``sport:matchStatus``. Two copies of one field are one field, and reading
        both would give a second place for the answer to come from."""
        payload = copy.deepcopy(SOURCE)
        payload["sport:matchStatus"] = "zzz-not-a-status"
        ignored = sportradar_nfl.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(ignored["observation"]["event"]["status"], "closed")

    def test_the_sport_is_american_football_as_a_pinned_mediatopic_code(self):
        """``schema:sportName`` says ``nfl``, which is a league. The sport is
        American football, and ``medtop:20000823`` is the pinned code for it."""
        self.assertEqual(self.observation["sport"],
                         {"medtop": "20000823", "key": "american-football"})

    def test_the_venue_carries_its_city_and_no_country_is_invented(self):
        site = self.observation["site"]
        self.assertEqual(site["provider_id"],
                         "00000000-0000-4000-8000-000000009801")
        self.assertEqual(site["name"], "Synthetic Dome")
        self.assertEqual(site["city"], "Synthetic City")
        self.assertNotIn("country", site)

    def test_the_label_is_composed_from_the_two_team_names(self):
        self.assertEqual(self.observation["event"]["label"],
                         "Synthetic Home Hawks vs Synthetic Away Anchors")

    def test_both_competitors_are_teams_with_alignment_and_scores_as_strings(self):
        self.assertEqual(
            [(p["kind"], p["provider_id"], p["name"], p["alignment"], p["score"])
             for p in self.observation["participants"]],
            [("team", "00000000-0000-4000-8000-000000009101",
              "Synthetic Home Hawks", "home", "24"),
             ("team", "00000000-0000-4000-8000-000000009102",
              "Synthetic Away Anchors", "away", "17")],
        )

    def test_home_is_emitted_first_even_when_the_source_lists_away_first(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:competitors"].reverse()
        reordered = sportradar_nfl.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(
            [p["alignment"] for p in reordered["observation"]["participants"]],
            ["home", "away"],
        )

    def test_the_source_document_is_carried_verbatim_and_only_under_raw(self):
        self.assertEqual(self.observation["raw"], SOURCE)
        for section in sorted(set(self.observation) - {"raw"}):
            with self.subTest(section=section):
                self.assertNotIn("halfTime", json.dumps(self.observation[section]))


class TestTheCompetitionIdentityIsAMappingConstant(unittest.TestCase):
    """The honest reading of this source's weakest identifiers.

    ``urn:sportradar:competition:nfl`` and ``urn:sportradar:season:2025`` are
    literals in the mapping expression, not values read from a Sportradar field:
    the NFL schedule payload the mapping consumes carries no competition entity
    and no season entity at all. The event, venue and team identifiers really are
    provider fields. Recording all five the same way would be a crosswalk that
    cannot be trusted at the two places it is weakest, so the distinction is
    asserted here and restated in the fixture's limitation.
    """

    def setUp(self):
        self.observation = observation()["observation"]

    def test_the_competition_and_season_identifiers_are_the_mapping_literals(self):
        competition = self.observation["competition"]
        self.assertEqual(competition["provider_id"], "nfl")
        self.assertEqual(competition["name"], "NFL")
        self.assertEqual(competition["season"]["provider_id"], "2025")
        self.assertEqual(competition["season"]["name"], "NFL 2025")

    def test_the_adapter_names_them_as_constants_rather_than_provider_fields(self):
        """A module-level list, so the claim is checkable rather than a comment."""
        self.assertEqual(sorted(sportradar_nfl.MAPPING_CONSTANT_IDENTIFIERS),
                         ["competition", "season"])

    def test_the_event_venue_and_team_identifiers_are_provider_uuids(self):
        """The other half. These come from ``f.get('id')``,
        ``f['venue']['id']`` and ``f['home'|'away']['id']``, so they are
        genuinely provider-native."""
        provider_ids = [self.observation["event"]["provider_id"],
                        self.observation["site"]["provider_id"]]
        provider_ids += [p["provider_id"]
                         for p in self.observation["participants"]]
        for provider_id in provider_ids:
            with self.subTest(provider_id=provider_id):
                self.assertRegex(
                    provider_id,
                    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

    def test_the_fixture_limitation_says_so_in_the_audit(self):
        """The reader who never opens this test file still has to be told."""
        entry = next(e for e in report_module.load_provenance()["corrected"]
                     if e["fixture"] == "corrected-sportradar-nfl")
        self.assertIn("mapping constant", entry["limitation"].lower())


class TestAbsenceStaysAbsent(unittest.TestCase):
    """The source's real absences, and the one fact it states that this profile
    has nowhere to put."""

    def setUp(self):
        self.observation = observation()["observation"]

    def test_no_winner_is_inferred_from_the_scoreline(self):
        """24-17 is not a statement about who won. The source states no winner,
        and inferring one would be this adapter deciding a result."""
        for participant in self.observation["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("outcome", participant)

    def test_the_raw_period_object_is_not_read_as_a_clock_or_a_period(self):
        """``sport:score.sport:halfTime`` is the first Sportradar period object
        verbatim, keys and all. It is a score for one period, not a reading of how
        far into the game play had reached, so it produces no clock — and its
        provider keys never escape ``raw``."""
        self.assertNotIn("clock", self.observation["event"])
        blob = json.dumps({k: v for k, v in self.observation.items()
                           if k != "raw"})
        for provider_key in ("period_type", "home_points", "away_points",
                             "sequence"):
            with self.subTest(provider_key=provider_key):
                self.assertNotIn(provider_key, blob)

    def test_the_period_object_is_still_readable_in_raw(self):
        half_time = self.observation["raw"]["sport:score"]["sport:halfTime"]
        self.assertEqual(half_time["period_type"], "quarter")
        self.assertEqual(half_time["home_points"], 7)

    def test_no_phase_and_no_competition_type_are_invented(self):
        """The source states neither. The NFL genuinely has a regular season and
        a post-season, and this document says which of them this game is in
        nowhere at all, so ``spct:season-regular`` would be a guess."""
        self.assertNotIn("phase", self.observation)
        self.assertNotIn("type", self.observation["competition"])

    def test_no_outcome_type_end_time_or_attendance_is_invented(self):
        for key in ("outcome_type", "end_time", "attendance"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.observation["event"])

    def test_no_action_no_membership_and_no_statistic_is_invented(self):
        """The event mapping emits no timeline, no roster and no statistics. The
        connector has separate statistics mappings; joining one to this document
        would attach numbers to a game nothing here says they belong to."""
        for key in ("actions", "memberships"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.observation)
        for participant in self.observation["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("statistics", participant)

    def test_no_team_abbreviation_is_promoted_to_a_graph_property(self):
        """``sport:abbreviation`` is not an official term and ``TeamShape`` is
        ``sh:closed`` with only ``rdfs:label`` admissible, so the alias stays in
        ``raw``."""
        blob = json.dumps({k: v for k, v in self.observation.items()
                           if k != "raw"})
        self.assertNotIn("SHH", blob)
        self.assertEqual(
            self.observation["raw"]["sport:competitors"][0]["sport:abbreviation"],
            "SHH")

    def test_a_pre_match_source_omits_the_scoreline_rather_than_emitting_zero(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:status"] = "not_started"
        payload["sport:score"] = {}
        pre_match = sportradar_nfl.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(pre_match), [])
        self.assertEqual(pre_match["observation"]["event"]["status"],
                         "not_started")
        for participant in pre_match["observation"]["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("score", participant)

    def test_a_genuine_shutout_scoreline_survives(self):
        """``0`` is knowledge and ``None`` is not, so omission cannot be a
        truthiness test."""
        payload = copy.deepcopy(SOURCE)
        payload["sport:score"]["sport:awayScore"] = 0
        shutout = sportradar_nfl.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(
            [p["score"] for p in shutout["observation"]["participants"]],
            ["24", "0"])

    def test_a_null_scoreline_is_omitted_rather_than_stringified(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:score"]["sport:homeScore"] = None
        nulled = sportradar_nfl.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(nulled), [])
        self.assertNotIn("score", nulled["observation"]["participants"][0])


class TestUnmappableProviderValuesFailLoudly(unittest.TestCase):
    """A provider value with no defensible canonical reading is an error, not a
    default. The message has to name the value, or the fix lands by guesswork."""

    def test_an_unmapped_status_raises_and_names_it(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:status"] = "zzz"
        with self.assertRaises(ValueError) as raised:
            sportradar_nfl.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertIn("zzz", str(raised.exception))
        self.assertIn("nfl", str(raised.exception))

    def test_a_status_the_repository_has_no_evidence_for_raises(self):
        """``complete`` and ``interrupted`` are plausible Sportradar codes and
        neither is in this repository's evidence, so neither is mapped. Failing
        closed names the code; guessing a neighbour would put a wrong status on a
        conforming document."""
        for code in ("complete", "interrupted", "halftime"):
            payload = copy.deepcopy(SOURCE)
            payload["sport:status"] = code
            with self.subTest(code=code):
                self.assertNotIn(code, sportradar_nfl.EVENT_STATUS_BY_CODE)
                with self.assertRaises(ValueError):
                    sportradar_nfl.to_observation(payload,
                                                  observed_at=OBSERVED_AT)

    def test_a_missing_status_raises_rather_than_defaulting(self):
        payload = copy.deepcopy(SOURCE)
        del payload["sport:status"]
        with self.assertRaises(ValueError):
            sportradar_nfl.to_observation(payload, observed_at=OBSERVED_AT)

    def test_the_mapped_codes_are_exactly_the_ones_the_mapping_can_emit(self):
        """The mapping rewrites ``created`` and ``scheduled`` to ``not_started``
        and ``inprogress`` to ``live``, and the fixture carries ``closed``. Those
        three are the whole of this repository's evidence."""
        self.assertEqual(sorted(sportradar_nfl.EVENT_STATUS_BY_CODE),
                         ["closed", "live", "not_started"])

    def test_every_mapped_status_reaches_a_pinned_event_status_newscode(self):
        from tools.iptc.canonical.vocab import EVENT_STATUS

        self.assertTrue(sportradar_nfl.EVENT_STATUS_BY_CODE)
        for code, canonical in sorted(sportradar_nfl.EVENT_STATUS_BY_CODE.items()):
            with self.subTest(code=code):
                self.assertIn(canonical, EVENT_STATUS)

    def test_a_source_with_no_event_identifier_raises(self):
        payload = copy.deepcopy(SOURCE)
        del payload["@id"]
        with self.assertRaises(ValueError):
            sportradar_nfl.to_observation(payload, observed_at=OBSERVED_AT)

    def test_an_event_id_outside_the_legacy_urn_stem_raises(self):
        payload = copy.deepcopy(SOURCE)
        payload["@id"] = "urn:something-else:9001"
        with self.assertRaises(ValueError):
            sportradar_nfl.to_observation(payload, observed_at=OBSERVED_AT)

    def test_a_source_stating_a_different_league_raises_and_names_it(self):
        """This adapter asserts ``medtop`` 20000823. An MLB document read by it
        would emit American football for a baseball game, and nothing downstream
        could tell — and the two mappings share every URN stem, so nothing in the
        identifiers would catch it either."""
        payload = copy.deepcopy(SOURCE)
        payload["schema:sportName"] = "mlb"
        with self.assertRaises(ValueError) as raised:
            sportradar_nfl.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertIn("mlb", str(raised.exception))


class TestCorrectedFixturesAreReproducible(unittest.TestCase):
    """A checked-in fixture that cannot be regenerated is a screenshot."""

    def test_the_observation_fixture_is_reproducible_from_the_adapter(self):
        self.assertEqual(OBSERVATION_PATH.read_text(encoding="utf-8"),
                         serialized(observation()))

    def test_the_envelope_fixture_is_reproducible_byte_for_byte(self):
        self.assertEqual(ENVELOPE_PATH.read_text(encoding="utf-8"),
                         serialized(envelope()))

    def test_the_graph_fixture_is_exactly_the_envelope_graph(self):
        self.assertEqual(
            json.loads(GRAPH_PATH.read_text(encoding="utf-8")),
            envelope()["machina_sports_schema"]["sport_schema_graph"],
        )

    def test_two_runs_of_the_adapter_agree(self):
        self.assertEqual(serialized(envelope()), serialized(envelope()))

    def test_the_envelope_claims_both_versions_and_every_rfc_002_part(self):
        block = envelope()["machina_sports_schema"]
        self.assertEqual(sorted(block), [
            "capabilities", "event_view", "profile", "provenance", "provider_ids",
            "rights", "schema_version", "sport_schema_graph",
        ])
        self.assertEqual(block["schema_version"], "machina-sports-schema/1")
        self.assertEqual(block["profile"], "machina-iptc-profile/1.1")

    def test_the_capability_tier_is_core_and_the_result_is_correctly_absent(self):
        """``event.result`` is optional at ``core``, so its absence costs no tier.
        Reporting it present off a scoreline comparison would tell a consumer the
        provider stated a winner."""
        capabilities = envelope()["machina_sports_schema"]["capabilities"]
        self.assertEqual(capabilities["tier"], "core")
        self.assertEqual(capabilities["tiers_satisfied"], ["core"])
        self.assertEqual(capabilities["violations"], [])
        self.assertIn("event.score", capabilities["present"])
        self.assertIn("event.result", capabilities["absent"])
        self.assertIn("event.actions", capabilities["absent"])
        self.assertIn("event.clock", capabilities["absent"])
        self.assertIn("event.lineups", capabilities["absent"])


class TestRightsAreRefusedForProduction(unittest.TestCase):
    """Checked twice: the library gate RFC 002 §9 names, and the command an
    operator actually runs."""

    def test_the_library_gate_refuses_the_checked_in_envelope_once(self):
        from tools.iptc.validate_graph import rights_findings

        checked_in = json.loads(ENVELOPE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(rights_findings(checked_in, consumer_tier="prototype"), [])
        findings = rights_findings(checked_in, consumer_tier="production")
        self.assertEqual([f["code"] for f in findings], ["rights-prototype-only"])
        self.assertEqual(findings[0]["data_class"],
                         sportradar_nfl.RIGHTS_DATA_CLASS)

    def test_the_command_exits_zero_for_prototype_and_nonzero_for_production(self):
        import contextlib
        import io

        from tools.iptc import validate_graph

        argument = str(ENVELOPE_PATH.relative_to(REPO_ROOT))
        for tier, expected in (("prototype", 0), ("production", 1)):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                status = validate_graph.main(["--consumer-tier", tier, argument])
            with self.subTest(tier=tier):
                self.assertEqual(status, expected)
        self.assertIn("rights-prototype-only", buffer.getvalue())


class TestIdentityIsASurrogate(unittest.TestCase):
    """Provider identifiers are crosswalk evidence; canonical identity is minted
    (RFC 001 §7.6)."""

    def setUp(self):
        self.block = envelope()["machina_sports_schema"]

    def test_every_graph_resource_id_is_a_marked_machina_surrogate(self):
        for node in self.block["sport_schema_graph"]["@graph"]:
            with self.subTest(node=node["@type"]):
                self.assertRegex(node["@id"],
                                 r"^urn:machina:sports:[a-z-]+:x[0-9a-f]{32}$")

    def test_no_legacy_urn_and_no_provider_uuid_survives_in_a_resource_id(self):
        for node in self.block["sport_schema_graph"]["@graph"]:
            with self.subTest(node=node["@id"]):
                self.assertNotIn("urn:sportradar", node["@id"])
                self.assertNotIn("0000-4000-8000", node["@id"])

    def test_provider_identifiers_appear_only_as_crosswalk_evidence(self):
        for node in self.block["sport_schema_graph"]["@graph"]:
            if node["@type"] == "machina:ProviderIdentifier":
                continue
            with self.subTest(node=node["@type"]):
                self.assertNotIn("000000009101", json.dumps(node))

    def test_the_crosswalk_holds_every_identifier_the_source_stated(self):
        entries = self.block["provider_ids"]
        self.assertEqual([e["entity_type"] for e in entries],
                         ["competition", "season", "site", "event",
                          "team", "team"])
        self.assertEqual(
            sorted(e["provider_id"] for e in entries),
            sorted(["nfl", "2025",
                    "00000000-0000-4000-8000-000000009801",
                    "00000000-0000-4000-8000-000000009001",
                    "00000000-0000-4000-8000-000000009101",
                    "00000000-0000-4000-8000-000000009102"]),
        )
        for entry in entries:
            with self.subTest(entity=entry["entity_type"]):
                self.assertEqual(entry["provider_namespace"], "sportradar-nfl")
                self.assertEqual(entry["resolution_method"], "provider-native")

    def test_every_crosswalk_entry_names_the_field_it_came_from(self):
        by_type = {e["entity_type"]: e for e in self.block["provider_ids"]}
        self.assertEqual(by_type["event"]["evidence"],
                         "observation.event.provider_id")
        self.assertEqual(by_type["season"]["evidence"],
                         "observation.competition.season.provider_id")

    def test_the_two_teams_crosswalk_as_teams_and_never_as_athletes(self):
        entity_types = {e["entity_type"] for e in self.block["provider_ids"]}
        self.assertIn("team", entity_types)
        self.assertNotIn("athlete", entity_types)


class TestNothingFabricatedReachesTheOutput(unittest.TestCase):
    """Scanned over emitted output rather than over a helper. A helper that drops
    placeholders proves nothing if one call site bypasses it."""

    def setUp(self):
        self.block = envelope()["machina_sports_schema"]

    def test_no_null_no_empty_string_and_no_placeholder_in_the_graph(self):
        blob = json.dumps(self.block["sport_schema_graph"])
        self.assertNotIn("null", blob)
        self.assertNotIn('""', blob)
        for value in sorted(profile_module.PLACEHOLDER_VALUES):
            if value:
                with self.subTest(placeholder=value):
                    self.assertNotIn('"{0}"'.format(value), blob)

    def test_no_null_no_empty_string_and_no_placeholder_in_the_view(self):
        view = copy.deepcopy(self.block["event_view"])
        view.get("provider", {}).pop("raw", None)
        blob = json.dumps(view)
        self.assertNotIn("null", blob)
        self.assertNotIn('""', blob)
        for value in sorted(profile_module.PLACEHOLDER_VALUES):
            if value:
                with self.subTest(placeholder=value):
                    self.assertNotIn('"{0}"'.format(value), blob)

    def test_no_official_resource_carries_a_machina_property(self):
        for node in self.block["sport_schema_graph"]["@graph"]:
            if str(node["@type"]).startswith("sport:"):
                with self.subTest(resource=node["@type"]):
                    self.assertEqual(
                        [k for k in node if k.startswith("machina:")], [])

    def test_no_provider_property_lands_in_the_iptc_namespace(self):
        """The defect the baseline row is fixtured for: the legacy document puts
        raw Sportradar keys inside ``sport:score.sport:halfTime`` and emits
        ``sport:matchStatus``, both under the official namespace."""
        blob = json.dumps(self.block["sport_schema_graph"]["@graph"])
        for term in ("sport:matchStatus", "sport:halfTime", "sport:abbreviation"):
            with self.subTest(term=term):
                self.assertNotIn(term, blob)

    def test_no_sport_specific_statistic_vocabulary_is_asserted(self):
        blob = json.dumps(self.block["sport_schema_graph"]["@graph"])
        for token in ("spamfstat", "spsocstat", "spstat", "spsocaction"):
            with self.subTest(token=token):
                self.assertNotIn(token, blob)


class TestCorrectedGraphConformance(unittest.TestCase):
    """The claim this task exists to make, checked by the PR 1 harness rather
    than by assertion: an NFL-derived document conforms."""

    @classmethod
    def setUpClass(cls):
        cls.result = validate_document(GRAPH_PATH, "corrected-sportradar-nfl",
                                       repo_root=REPO_ROOT)

    def test_all_four_layers_pass(self):
        for layer in ("jsonld_parse", "official_shacl", "machina_profile",
                      "controlled_vocabulary"):
            with self.subTest(layer=layer):
                self.assertTrue(self.result.layers[layer]["ok"],
                                self.result.layers[layer]["detail"])

    def test_the_shacl_pass_is_not_vacuous(self):
        shacl = self.result.layers["official_shacl"]["detail"]
        self.assertFalse(shacl["vacuous"])
        self.assertGreater(shacl["official_class_instances"], 0)
        self.assertEqual(shacl["result_count"], 0)

    def test_all_four_gates_are_zero(self):
        for gate in ("unknown_sport_terms", "invalid_newscode_values",
                     "duplicate_resource_ids",
                     "provider_properties_in_iptc_namespace"):
            with self.subTest(gate=gate):
                self.assertEqual(self.result.counters[gate], 0)

    def test_the_controlled_vocabulary_layer_checked_real_codes(self):
        detail = self.result.layers["controlled_vocabulary"]["detail"]
        self.assertGreater(len(detail["valid"]), 0)
        for key in ("invalid", "undeclared_prefix", "unverifiable"):
            with self.subTest(key=key):
                self.assertEqual(detail[key], [])

    def test_the_american_football_mediatopic_code_is_verified(self):
        detail = self.result.layers["controlled_vocabulary"]["detail"]
        self.assertIn("http://cv.iptc.org/newscodes/mediatopic/20000823",
                      [item["value"] for item in detail["valid"]])

    def test_the_document_conforms_overall(self):
        self.assertTrue(self.result.conforms)


class TestCorrectedSectionIsRegistered(unittest.TestCase):
    """A corrected fixture nothing runs is a corrected fixture nobody checks."""

    def setUp(self):
        self.entry = next(
            e for e in report_module.load_provenance()["corrected"]
            if e["fixture"] == "corrected-sportradar-nfl")

    def test_the_corrected_graph_is_registered_and_resolvable(self):
        self.assertEqual(self.entry["class"], "corrected-serializer-output")
        self.assertEqual(report_module.resolve(self.entry), GRAPH_PATH)
        self.assertTrue(report_module.resolve(self.entry).is_file())

    def test_the_entry_labels_its_evidence_and_its_limits(self):
        for key in ("source", "transformation", "emitted_by", "limitation",
                    "rights"):
            with self.subTest(key=key):
                self.assertTrue(self.entry.get(key))

    def test_the_entry_calls_the_source_a_legacy_mapping_shape(self):
        self.assertIn(str(SOURCE_PATH.relative_to(REPO_ROOT)), self.entry["source"])
        self.assertIn("legacy-mapping-contract-shape", self.entry["rights"])
        prose = (self.entry["limitation"] + self.entry["transformation"]
                 + self.entry["provenance"]).lower()
        for phrase in ("legacy mapping", "not raw provider data",
                       "no sportradar endpoint was called"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, prose)

    def test_the_entry_makes_no_commercial_or_entitlement_claim(self):
        prose = json.dumps(self.entry).lower()
        self.assertIn("not an entitlement", prose)
        self.assertNotIn("redistributable", prose)

    def test_the_section_is_reachable_through_registered_fixtures(self):
        registered = dict(cli_support.registered_fixtures(["corrected"]))
        self.assertEqual(registered["corrected-sportradar-nfl"], GRAPH_PATH)

    def test_the_baseline_nfl_fixture_is_untouched(self):
        entry = next(e for e in report_module.load_provenance()["baseline"]
                     if e["fixture"] == "sportradar-nfl-event")
        self.assertEqual(entry["class"], "mapping-contract-synthetic")
        self.assertEqual(report_module.resolve(entry), SOURCE_PATH)
        self.assertTrue(report_module.resolve(entry).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
