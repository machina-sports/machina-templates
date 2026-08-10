"""Tests for the Sportradar tennis canonical adapter (PR 2, task A15b.1).

Run from the repository root:

    python3 tests/test_iptc_sportradar_tennis_adapter.py -v

Run the file directly, for the same reason as
``tests/test_iptc_canonical_serializer.py``: ``tests/`` is a namespace directory
with no ``__init__.py``, so ``-m unittest tests.<module>`` can be shadowed by an
installed distribution that ships a top-level regular ``tests`` package.

A focused file per provider, on purpose: a failure here names Sportradar tennis
rather than "the canonical suite", and the four-layer assertion block is
deliberately repeated rather than factored into a shared loop (A14 handoff
item 1, restated by A15b).

**There is no raw Sportradar tennis payload in this repository.** Unlike the
soccer row, which reads ``example-sportradar.json``, the only evidence for this
feed is ``tools/iptc/fixtures/baseline/sportradar-tennis-event.json`` — a
document PR 1 hand-authored from the literal key set of
``iptc-sportradar-tennis-event-mapping``. It is therefore a **legacy
mapping-contract shape**: the output of Machina's own mapping, two removes from
what Sportradar sends, and synthetic throughout. No Sportradar endpoint was
called, no credential exists in this repository and there is no network access in
this harness. Calling this row provider data, or a commercial entitlement, would
be a claim nothing here supports.

What this file defends beyond A13, A15a.1 and A15a.2:

1. **Tennis exercises individual participation.** Two singles players are
   ``sport:Athlete`` / ``sport:IndividualParticipation``, not teams wearing a
   team class. No corrected row before this one had an individual in it.
2. **The sport is tennis, and the medtop says so.** ``medtop:20001085``, checked
   against the pinned mediatopic scheme, replacing the source's invented
   ``urn:iptc:sport:tennis`` node.
3. **No ``sptenstat:`` statistic is emitted, and the pinned shapes are why.**
   The source carries seventeen per-player tennis statistics.
   ``sport:IndividualParticipationShape`` is ``sh:closed`` and declares none of
   them, so emitting one would fail layer 2. A test injects one to prove that is
   a measured fact rather than an opinion, and the provider's detail survives in
   ``raw``.
4. **The status read is the one Sportradar states, not the mapping's second
   copy of a different field.** ``sport:gameInfo.sport:status`` carries
   ``sport_event_status.status``; the top-level ``sport:status`` carries
   ``match_status``, a different vocabulary this profile has no concept for.
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
from tools.iptc.canonical.adapters import sportradar_tennis  # noqa: E402
from tools.iptc.canonical.ids import surrogate_resolver  # noqa: E402
from tools.iptc.canonical.observation import validate_observation  # noqa: E402
from tools.iptc.canonical.serialize import canonical_envelope  # noqa: E402
from tools.iptc.validate import validate_document, validate_payload  # noqa: E402

#: The source evidence: PR 1's frozen baseline fixture for this mapping. READ
#: ONLY — it is the "before" document the corrected output is measured against,
#: and this task does not edit it.
SOURCE_PATH = (REPO_ROOT / "tools/iptc/fixtures/baseline"
               / "sportradar-tennis-event.json")

OBSERVATION_PATH = (REPO_ROOT
                    / "tools/iptc/fixtures/observations"
                    / "sportradar-tennis-observation.json")
GRAPH_PATH = (REPO_ROOT / "tools/iptc/fixtures/corrected"
              / "sportradar-tennis-graph.json")
ENVELOPE_PATH = (REPO_ROOT / "tools/iptc/fixtures/corrected"
                 / "sportradar-tennis-envelope.json")

#: Fixed, so the corrected fixtures are reproducible. Nothing in the adapter or
#: the serializer reads the clock; this is the one time value, and it is an input.
OBSERVED_AT = "2026-03-01T22:05:00+00:00"

SOURCE = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))


def observation():
    return sportradar_tennis.to_observation(SOURCE, observed_at=OBSERVED_AT)


def envelope():
    return canonical_envelope(observation(),
                              id_resolver=surrogate_resolver("sportradar-tennis"))


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
            sportradar_tennis.to_observation(SOURCE, OBSERVED_AT)

    def test_the_adapter_reads_the_source_without_mutating_it(self):
        before = copy.deepcopy(SOURCE)
        sportradar_tennis.to_observation(SOURCE, observed_at=OBSERVED_AT)
        self.assertEqual(SOURCE, before)


class TestTheSourceIsLabelledForWhatItIs(unittest.TestCase):
    """No raw Sportradar tennis payload exists here, so this row may not borrow
    the soccer row's data class."""

    def test_the_data_class_says_legacy_mapping_contract_shape(self):
        rights = observation()["observation"]["rights"]
        self.assertEqual(rights["data_class"], "legacy-mapping-contract-shape")
        self.assertEqual(rights["data_class"],
                         sportradar_tennis.RIGHTS_DATA_CLASS)

    def test_the_data_class_is_not_the_one_a_real_provider_example_earns(self):
        """``corrected-sportradar-soccer`` reads a checked-in provider example.
        This does not, and the audit has to be able to tell the two apart."""
        self.assertNotEqual(sportradar_tennis.RIGHTS_DATA_CLASS,
                            "licensed-provider-example-fixture")
        for word in ("redistributable", "provider-example", "entitlement",
                     "production"):
            with self.subTest(word=word):
                self.assertNotIn(word, sportradar_tennis.RIGHTS_DATA_CLASS)

    def test_the_source_ref_names_the_mapping_rather_than_an_endpoint(self):
        """There is no endpoint class to cite: nothing here came from one."""
        refs = observation()["observation"]["adapter"]["source_refs"]
        self.assertEqual([ref["kind"] for ref in refs], ["legacy-mapping-output"])
        self.assertEqual(refs[0]["value"],
                         "iptc-sportradar-tennis-event-mapping")
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
        """Sportradar publishes a separate feed per sport. One namespace across
        feeds would claim their identifier spaces are one, which nothing here has
        checked."""
        self.assertEqual(observation()["observation"]["provider"],
                         {"namespace": "sportradar-tennis", "family": "licensed"})

    def test_the_adapter_identifies_itself(self):
        adapter = observation()["observation"]["adapter"]
        self.assertEqual(adapter["name"],
                         "tools.iptc.canonical.adapters.sportradar_tennis")
        self.assertTrue(adapter["version"])


class TestProviderFactsAreReadCorrectly(unittest.TestCase):
    """Every value below is traceable to one key of the checked-in source."""

    def setUp(self):
        self.observation = observation()["observation"]

    def test_the_event_identifier_is_the_sportradar_one_not_machinas_urn(self):
        """The source's ``@id`` is
        ``urn:sportradar:tennis:match:sr:sport_event:9000001``: Machina's URN
        scheme wrapped around Sportradar's own identifier. Recording the whole
        URN would attribute this repository's scheme to Sportradar."""
        event = self.observation["event"]
        self.assertEqual(event["provider_id"], "sr:sport_event:9000001")
        self.assertEqual(event["start_time"], "2026-01-20T09:00:00+00:00")

    def test_the_status_is_the_canonical_key_not_the_provider_code(self):
        self.assertEqual(self.observation["event"]["status"], "closed")

    def test_the_status_read_is_game_infos_and_not_the_match_status_copy(self):
        """``sport:gameInfo.sport:status`` is Sportradar's
        ``sport_event_status.status``. The top-level ``sport:status`` is
        ``match_status`` — a finer-grained reading from a different vocabulary,
        which this adapter does not map. Garbage in the one it ignores must not
        change the answer."""
        payload = copy.deepcopy(SOURCE)
        payload["sport:status"] = "zzz-not-a-status"
        ignored = sportradar_tennis.to_observation(payload,
                                                   observed_at=OBSERVED_AT)
        self.assertEqual(ignored["observation"]["event"]["status"], "closed")

    def test_the_competition_and_its_season_carry_sportradar_identifiers(self):
        competition = self.observation["competition"]
        self.assertEqual(competition["provider_id"], "sr:competition:9001")
        self.assertEqual(competition["name"], "Synthetic Open")
        self.assertEqual(competition["season"]["provider_id"], "sr:season:9001")
        self.assertEqual(competition["season"]["name"], "Synthetic Open 2026")

    def test_the_venue_carries_its_city_and_its_own_country(self):
        site = self.observation["site"]
        self.assertEqual(site["provider_id"], "sr:venue:9001")
        self.assertEqual(site["name"], "Synthetic Centre Court")
        self.assertEqual(site["city"], "Synthetic City")
        self.assertEqual(site["country"], "Synthetica")

    def test_the_sport_is_tennis_as_a_pinned_mediatopic_code(self):
        self.assertEqual(self.observation["sport"],
                         {"medtop": "20001085", "key": "tennis"})

    def test_the_label_is_composed_from_the_two_player_names(self):
        self.assertEqual(self.observation["event"]["label"],
                         "Synthetic Player A vs Synthetic Player B")

    def test_both_players_are_individuals_and_never_teams(self):
        """The point of this row. A singles match has no team in it, and reading
        the two competitors as ``sport:Team`` would put a class on the graph the
        source never states."""
        self.assertEqual([p["kind"] for p in self.observation["participants"]],
                         ["individual", "individual"])

    def test_home_comes_first_and_both_players_carry_alignment_and_score(self):
        self.assertEqual(
            [(p["kind"], p["provider_id"], p["name"], p["alignment"], p["score"])
             for p in self.observation["participants"]],
            [("individual", "sr:competitor:9101", "Synthetic Player A", "home", "2"),
             ("individual", "sr:competitor:9102", "Synthetic Player B", "away", "1")],
        )

    def test_home_is_emitted_first_even_when_the_source_lists_away_first(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:competitors"].reverse()
        reordered = sportradar_tennis.to_observation(payload,
                                                     observed_at=OBSERVED_AT)
        self.assertEqual(
            [p["alignment"] for p in reordered["observation"]["participants"]],
            ["home", "away"],
        )

    def test_the_winner_id_names_one_player_and_the_other_loses(self):
        """``sport:gameInfo.sport:winnerId`` states the winner by identifier, so
        both outcomes fall out of one stated fact rather than from comparing the
        set scores."""
        self.assertEqual([p["outcome"] for p in self.observation["participants"]],
                         ["win", "loss"])

    def test_the_scoreline_is_sets_won_and_not_the_per_set_games(self):
        """``sport:score`` is 2-1 in sets. ``sport:periodScores`` are the games
        per set, and promoting either into the other would misreport the match."""
        self.assertEqual([p["score"] for p in self.observation["participants"]],
                         ["2", "1"])

    def test_the_source_document_is_carried_verbatim_and_only_under_raw(self):
        self.assertEqual(self.observation["raw"], SOURCE)
        for section in sorted(set(self.observation) - {"raw"}):
            with self.subTest(section=section):
                self.assertNotIn("periodScores",
                                 json.dumps(self.observation[section]))


class TestTennisStatisticsStayOutOfTheGraph(unittest.TestCase):
    """Seventeen per-player statistics are in the source and none is emitted.

    ``sptenstat:`` is an official Sport Schema namespace at the pinned commit —
    ``sptenstat:aces`` is a real declared property — and that is exactly why the
    rule cannot be "the term exists". ``sport:IndividualParticipationShape`` is
    ``sh:closed`` and declares no tennis statistic at all, so a document carrying
    one violates the official shapes. Both halves are asserted, because the
    interesting claim is that this was measured rather than assumed.
    """

    def test_no_participant_carries_a_statistics_block(self):
        for participant in observation()["observation"]["participants"]:
            with self.subTest(player=participant["provider_id"]):
                self.assertNotIn("statistics", participant)

    def test_no_sport_specific_statistic_prefix_appears_in_the_graph(self):
        blob = json.dumps(envelope()["machina_sports_schema"]
                          ["sport_schema_graph"]["@graph"])
        for prefix in ("sptenstat", "spstat", "spsocstat"):
            with self.subTest(prefix=prefix):
                self.assertNotIn(prefix, blob)

    def test_the_pinned_shapes_really_do_reject_a_tennis_statistic(self):
        """The measurement behind the omission. Inject one official tennis
        statistic onto the individual participation and layer 2 fails."""
        probe = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        participation = next(
            node for node in probe["@graph"]
            if node["@type"] == "sport:IndividualParticipation")
        participation["sptenstat:aces"] = "9"
        result = validate_payload(probe, "probe-sptenstat-on-participation",
                                  path=str(GRAPH_PATH.relative_to(REPO_ROOT)))
        self.assertFalse(result.layers["official_shacl"]["ok"])
        self.assertGreater(result.layers["official_shacl"]["detail"]["result_count"], 0)

    def test_the_provider_statistics_are_still_readable_in_raw(self):
        """The mirror of the omission. Dropping them from the graph is only
        defensible while none of them is lost."""
        raw = envelope()["machina_sports_schema"]["event_view"]["provider"]["raw"]
        players = raw["sport:statistics"]["sport:competitorStats"]
        self.assertEqual([p["sport:competitorId"] for p in players],
                         ["sr:competitor:9101", "sr:competitor:9102"])
        self.assertEqual(players[0]["sport:statistics"]["sport:aces"], 9)
        self.assertEqual(players[0]["sport:statistics"]["sport:doubleFaults"], 2)


class TestAbsenceStaysAbsent(unittest.TestCase):
    """The source's real absences, and the facts it states that this profile has
    nowhere to put."""

    def setUp(self):
        self.observation = observation()["observation"]

    def test_no_phase_is_invented_from_a_round_name_or_a_stage(self):
        """``sport:round`` is ``{roundName, roundNumber}`` and ``sport:stage``
        carries no ``@id`` at all, so neither is something Sportradar addresses a
        phase by. Recording either as provider-native evidence would invent it."""
        self.assertNotIn("phase", self.observation)

    def test_no_competition_type_is_inferred_from_the_stage_or_the_format(self):
        """``sport:stage.sport:type`` is ``cup`` and describes the stage, which
        this observation does not carry. ``sport:competitionFormat`` states a
        match type, a gender category and a tour level — none of which is a
        ``spct:`` competition kind."""
        self.assertNotIn("type", self.observation["competition"])

    def test_no_clock_and_no_period_are_invented_from_the_set_scores(self):
        self.assertNotIn("clock", self.observation["event"])

    def test_no_outcome_type_is_inferred_from_a_three_set_scoreline(self):
        self.assertNotIn("outcome_type", self.observation["event"])

    def test_no_end_time_and_no_attendance_are_invented(self):
        for key in ("end_time", "attendance"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.observation["event"])

    def test_no_action_and_no_membership_is_invented(self):
        """The source has no timeline and no team, so there is neither an action
        to emit nor a membership to assert."""
        for key in ("actions", "memberships"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.observation)

    def test_no_seed_or_bracket_number_is_promoted_to_a_rank(self):
        """``sport:rank`` is admissible on an IndividualParticipation, and a seed
        is not a rank: it is a draw position assigned before the tournament.
        ``sport:bracketNumber`` is not one either. Both survive in ``raw``."""
        for participant in self.observation["participants"]:
            with self.subTest(player=participant["provider_id"]):
                self.assertNotIn("rank", participant)
        raw = self.observation["raw"]["sport:competitors"]
        self.assertEqual(raw[0]["sport:seed"], 3)

    def test_a_player_with_no_stated_winner_gets_no_outcome(self):
        payload = copy.deepcopy(SOURCE)
        del payload["sport:gameInfo"]["sport:winnerId"]
        undecided = sportradar_tennis.to_observation(payload,
                                                     observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(undecided), [])
        for participant in undecided["observation"]["participants"]:
            with self.subTest(player=participant["provider_id"]):
                self.assertNotIn("outcome", participant)

    def test_a_pre_match_source_omits_the_scoreline_rather_than_emitting_zero(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:gameInfo"] = {"sport:status": "not_started"}
        payload["sport:score"] = {}
        pre_match = sportradar_tennis.to_observation(payload,
                                                     observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(pre_match), [])
        self.assertEqual(pre_match["observation"]["event"]["status"],
                         "not_started")
        for participant in pre_match["observation"]["participants"]:
            with self.subTest(player=participant["provider_id"]):
                self.assertNotIn("score", participant)
                self.assertNotIn("outcome", participant)

    def test_a_genuine_zero_scoreline_survives(self):
        """``0`` is knowledge and ``None`` is not, so omission cannot be a
        truthiness test."""
        payload = copy.deepcopy(SOURCE)
        payload["sport:score"]["sport:homeScore"] = 0
        payload["sport:score"]["sport:awayScore"] = 0
        blanked = sportradar_tennis.to_observation(payload,
                                                   observed_at=OBSERVED_AT)
        self.assertEqual(
            [p["score"] for p in blanked["observation"]["participants"]],
            ["0", "0"])

    def test_a_null_scoreline_is_omitted_rather_than_stringified(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:score"]["sport:homeScore"] = None
        nulled = sportradar_tennis.to_observation(payload,
                                                  observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(nulled), [])
        self.assertNotIn("score", nulled["observation"]["participants"][0])


class TestUnmappableProviderValuesFailLoudly(unittest.TestCase):
    """A provider value with no defensible canonical reading is an error, not a
    default. The message has to name the value, or the fix lands by guesswork."""

    def test_an_unmapped_status_raises_and_names_it(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:gameInfo"]["sport:status"] = "zzz"
        with self.assertRaises(ValueError) as raised:
            sportradar_tennis.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertIn("zzz", str(raised.exception))
        self.assertIn("tennis", str(raised.exception))

    def test_sportradars_own_unknown_status_raises_rather_than_mapping(self):
        """``unknown`` is Sportradar declining to state a status, and it is the
        literal default the legacy mapping falls back to. Mapping it to any
        canonical key would turn a declined statement into an asserted one."""
        payload = copy.deepcopy(SOURCE)
        payload["sport:gameInfo"]["sport:status"] = "unknown"
        with self.assertRaises(ValueError):
            sportradar_tennis.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertNotIn("unknown", sportradar_tennis.EVENT_STATUS_BY_CODE)

    def test_a_missing_status_raises_rather_than_defaulting(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:gameInfo"] = {}
        with self.assertRaises(ValueError):
            sportradar_tennis.to_observation(payload, observed_at=OBSERVED_AT)

    def test_every_mapped_status_reaches_a_pinned_event_status_newscode(self):
        from tools.iptc.canonical.vocab import EVENT_STATUS

        self.assertTrue(sportradar_tennis.EVENT_STATUS_BY_CODE)
        for code, canonical in sorted(
                sportradar_tennis.EVENT_STATUS_BY_CODE.items()):
            with self.subTest(code=code):
                self.assertIn(canonical, EVENT_STATUS)

    def test_a_source_with_no_event_identifier_raises(self):
        payload = copy.deepcopy(SOURCE)
        del payload["@id"]
        with self.assertRaises(ValueError):
            sportradar_tennis.to_observation(payload, observed_at=OBSERVED_AT)

    def test_an_event_id_outside_the_legacy_urn_stem_raises(self):
        """A half-parsed identifier recorded as provider-native evidence is worse
        than no crosswalk entry at all."""
        payload = copy.deepcopy(SOURCE)
        payload["@id"] = "urn:something-else:9000001"
        with self.assertRaises(ValueError):
            sportradar_tennis.to_observation(payload, observed_at=OBSERVED_AT)

    def test_a_source_stating_a_different_sport_raises_and_names_it(self):
        """This adapter asserts ``medtop`` 20001085. A table-tennis document read
        by it would emit tennis, and nothing downstream could tell."""
        payload = copy.deepcopy(SOURCE)
        payload["schema:sportName"] = "table_tennis"
        with self.assertRaises(ValueError) as raised:
            sportradar_tennis.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertIn("table_tennis", str(raised.exception))


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

    def test_the_capability_tier_is_core_and_says_why(self):
        """No clock, no period and no actions, so ``live`` is correctly not
        claimed. ``participant.player_statistics`` is absent too, which is what
        keeps ``advanced`` off a row whose source is full of statistics this
        profile cannot carry."""
        capabilities = envelope()["machina_sports_schema"]["capabilities"]
        self.assertEqual(capabilities["tier"], "core")
        self.assertEqual(capabilities["tiers_satisfied"], ["core"])
        self.assertEqual(capabilities["violations"], [])
        self.assertIn("event.actions", capabilities["absent"])
        self.assertIn("event.clock", capabilities["absent"])
        self.assertIn("participant.player_statistics", capabilities["absent"])
        self.assertIn("event.score", capabilities["present"])
        self.assertIn("event.result", capabilities["present"])

    def test_the_named_individuals_are_reported_as_a_present_capability(self):
        """``event.lineups`` means the event names individuals, and a singles
        match does. It is optional at the ``advanced`` tier, so it changes no
        tier claim."""
        capabilities = envelope()["machina_sports_schema"]["capabilities"]
        self.assertIn("event.lineups", capabilities["present"])


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
                         sportradar_tennis.RIGHTS_DATA_CLASS)

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

    def test_no_legacy_urn_and_no_sr_identifier_survives_in_the_graph(self):
        """The legacy mapping emits ``urn:sportradar:tennis:…`` resource ids
        built from ``sr:`` identifiers, plus an invented ``urn:iptc:sport:tennis``
        node. A corrected document carrying any of them would be the old identity
        model in new clothes."""
        for node in self.block["sport_schema_graph"]["@graph"]:
            with self.subTest(node=node["@id"]):
                self.assertNotIn("urn:sportradar", node["@id"])
                self.assertNotIn("urn:iptc:sport", node["@id"])
                self.assertNotIn("sr:", node["@id"])

    def test_the_invented_sport_node_is_replaced_by_a_pinned_mediatopic_code(self):
        event = next(node for node in self.block["sport_schema_graph"]["@graph"]
                     if node["@type"] == "sport:Event")
        self.assertEqual(event["sport:sport"], {"@id": "medtop:20001085"})

    def test_provider_identifiers_appear_only_as_crosswalk_evidence(self):
        for node in self.block["sport_schema_graph"]["@graph"]:
            if node["@type"] == "machina:ProviderIdentifier":
                continue
            with self.subTest(node=node["@type"]):
                self.assertNotIn("sr:competitor", json.dumps(node))

    def test_the_crosswalk_holds_every_identifier_the_source_stated(self):
        entries = self.block["provider_ids"]
        self.assertEqual([e["entity_type"] for e in entries],
                         ["competition", "season", "site", "event",
                          "athlete", "athlete"])
        self.assertEqual(
            sorted(e["provider_id"] for e in entries),
            sorted(["sr:competition:9001", "sr:season:9001", "sr:venue:9001",
                    "sr:sport_event:9000001", "sr:competitor:9101",
                    "sr:competitor:9102"]),
        )
        for entry in entries:
            with self.subTest(entity=entry["entity_type"]):
                self.assertEqual(entry["provider_namespace"], "sportradar-tennis")
                self.assertEqual(entry["resolution_method"], "provider-native")

    def test_the_players_crosswalk_as_athletes_and_never_as_teams(self):
        entity_types = {e["entity_type"] for e in self.block["provider_ids"]}
        self.assertIn("athlete", entity_types)
        self.assertNotIn("team", entity_types)

    def test_every_crosswalk_entry_names_the_field_it_came_from(self):
        by_type = {e["entity_type"]: e for e in self.block["provider_ids"]}
        self.assertEqual(by_type["event"]["evidence"],
                         "observation.event.provider_id")
        self.assertEqual(by_type["season"]["evidence"],
                         "observation.competition.season.provider_id")


class TestTheGraphUsesIndividualClassesThroughout(unittest.TestCase):
    """The structural claim of this row, asserted on emitted output."""

    def setUp(self):
        self.graph = envelope()["machina_sports_schema"]["sport_schema_graph"]

    def test_two_athletes_and_two_individual_participations_are_emitted(self):
        types = [node["@type"] for node in self.graph["@graph"]]
        self.assertEqual(types.count("sport:Athlete"), 2)
        self.assertEqual(types.count("sport:IndividualParticipation"), 2)

    def test_no_team_class_appears_anywhere_in_the_graph(self):
        for node in self.graph["@graph"]:
            with self.subTest(node=node["@id"]):
                self.assertNotIn(node["@type"],
                                 ("sport:Team", "sport:TeamParticipation"))

    def test_each_participation_points_at_an_athlete_the_graph_describes(self):
        athletes = {node["@id"] for node in self.graph["@graph"]
                    if node["@type"] == "sport:Athlete"}
        participations = [node for node in self.graph["@graph"]
                          if node["@type"] == "sport:IndividualParticipation"]
        self.assertEqual(len(participations), 2)
        for participation in participations:
            with self.subTest(participation=participation["@id"]):
                self.assertIn(participation["sport:participationBy"]["@id"], athletes)

    def test_the_event_references_both_individual_participations(self):
        event = next(node for node in self.graph["@graph"]
                     if node["@type"] == "sport:Event")
        participations = {node["@id"] for node in self.graph["@graph"]
                          if node["@type"] == "sport:IndividualParticipation"}
        self.assertEqual({ref["@id"] for ref in event["sport:participation"]},
                         participations)

    def test_no_participation_carries_team_alignment_the_shapes_reject(self):
        """``sport:alignment`` is declared on ``TeamParticipationShape`` and not
        on the individual one, which is ``sh:closed``. The observation still
        records the alignment, because it is what decides which score column is
        which; it just never reaches the graph."""
        for node in self.graph["@graph"]:
            if node["@type"] != "sport:IndividualParticipation":
                continue
            with self.subTest(node=node["@id"]):
                self.assertNotIn("sport:alignment", node)
        self.assertEqual(
            [p["alignment"] for p in observation()["observation"]["participants"]],
            ["home", "away"])

    def test_the_two_players_appear_in_the_views_players_list(self):
        view = envelope()["machina_sports_schema"]["event_view"]
        self.assertEqual([player["name"] for player in view["players"]],
                         ["Synthetic Player A", "Synthetic Player B"])
        self.assertEqual(view.get("participants"), None)


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
        """``provider.raw`` is excluded deliberately: it is the source's own
        bytes and rewriting it would destroy the one field whose value is being
        an unaltered record."""
        view = copy.deepcopy(self.block["event_view"])
        view.get("provider", {}).pop("raw", None)
        blob = json.dumps(view)
        self.assertNotIn("null", blob)
        self.assertNotIn('""', blob)
        for value in sorted(profile_module.PLACEHOLDER_VALUES):
            if value:
                with self.subTest(placeholder=value):
                    self.assertNotIn('"{0}"'.format(value), blob)

    def test_the_sources_own_placeholders_are_dropped_rather_than_forwarded(self):
        """The legacy mapping defaults hard: ``sport:title`` is
        ``"Unknown Title"`` and ``sport:seed`` is ``null`` for the unseeded
        player. Both are in ``raw`` and neither reaches the graph or the view."""
        raw = self.block["event_view"]["provider"]["raw"]
        self.assertEqual(raw["sport:eventDetails"]["sport:title"], "Unknown Title")
        self.assertIsNone(raw["sport:competitors"][1]["sport:seed"])

    def test_no_official_resource_carries_a_machina_property(self):
        for node in self.block["sport_schema_graph"]["@graph"]:
            if str(node["@type"]).startswith("sport:"):
                with self.subTest(resource=node["@type"]):
                    self.assertEqual(
                        [k for k in node if k.startswith("machina:")], [])

    def test_no_unpinned_action_or_position_vocabulary_is_asserted(self):
        blob = json.dumps(self.block["sport_schema_graph"]["@graph"])
        for token in ("spsocaction", "spsocposition", "spplayerstatus"):
            with self.subTest(token=token):
                self.assertNotIn(token, blob)


class TestCorrectedGraphConformance(unittest.TestCase):
    """The claim this task exists to make, checked by the PR 1 harness rather
    than by assertion: an individual-participation document conforms."""

    @classmethod
    def setUpClass(cls):
        cls.result = validate_document(GRAPH_PATH, "corrected-sportradar-tennis",
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

    def test_the_tennis_mediatopic_code_is_one_of_the_verified_codes(self):
        """The pinned mediatopic scheme is what makes 20001085 checkable rather
        than plausible."""
        detail = self.result.layers["controlled_vocabulary"]["detail"]
        self.assertIn("http://cv.iptc.org/newscodes/mediatopic/20001085",
                      [item["value"] for item in detail["valid"]])

    def test_the_document_conforms_overall(self):
        self.assertTrue(self.result.conforms)


class TestCorrectedSectionIsRegistered(unittest.TestCase):
    """A corrected fixture nothing runs is a corrected fixture nobody checks."""

    def setUp(self):
        self.entry = next(
            e for e in report_module.load_provenance()["corrected"]
            if e["fixture"] == "corrected-sportradar-tennis")

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
        """The honesty requirement, made mechanical. A reader must not be able to
        come away thinking a Sportradar tennis response is checked in here."""
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
        self.assertEqual(registered["corrected-sportradar-tennis"], GRAPH_PATH)

    def test_the_baseline_tennis_fixture_is_untouched(self):
        """The source doubles as the "before" evidence. It stays a baseline row,
        read-only, so the audit still measures the corrected output against it."""
        entry = next(e for e in report_module.load_provenance()["baseline"]
                     if e["fixture"] == "sportradar-tennis-event")
        self.assertEqual(entry["class"], "mapping-contract-synthetic")
        self.assertEqual(report_module.resolve(entry), SOURCE_PATH)
        self.assertTrue(report_module.resolve(entry).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
