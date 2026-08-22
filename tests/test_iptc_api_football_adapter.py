"""Tests for the API-Football canonical adapter (PR 2, task A13).

Run from the repository root:

    python3 tests/test_iptc_api_football_adapter.py -v

Run the file directly, for the same reason as
``tests/test_iptc_canonical_serializer.py``: ``tests/`` is a namespace directory
with no ``__init__.py``, so ``-m unittest tests.<module>`` can be shadowed by an
installed distribution that ships a top-level regular ``tests`` package.

A7-A12 proved the contract, the serializer and the four gates against a wholly
**synthetic** observation. This is the first *real provider shape*, and what is
being defended here is narrower and harder:

1. **The evidence is shape evidence, not an entitlement.** The source payload is
   a provider *example* already checked into this repository. No API-Football
   endpoint was called, no credential exists in this process, and nothing here
   claims a licence to redistribute API-Football data. The observation's rights
   block says so in the two fields a consumer actually reads.
2. **A real payload's absences stay absent.** This payload carries four
   provider nulls, a competition with no stated type and a venue with no country.
   Every one of them is an omission path A8 already tests; A13's job is to
   confirm them against provider data rather than to add leniency.
3. **A provider code is never guessed at.** An API-Football status short code
   with no defensible canonical mapping raises, naming the code. A drawn fixture,
   whose ``winner`` flags are both null, produces no participant outcome at all
   rather than an invented ``draw``.
4. **The checked-in corrected fixtures are reproducible byte-for-byte** from the
   source payload plus a fixed ``observed_at``. A fixture that cannot be
   regenerated is a screenshot, not evidence.
5. **The corrected graph passes the PR 1 harness** — all four layers, a
   non-vacuous layer 2, and all four gates at zero — on provider-derived data.
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
from tools.iptc import __main__ as iptc_main  # noqa: E402
from tools.iptc import profile as profile_module  # noqa: E402
from tools.iptc import report as report_module  # noqa: E402
from tools.iptc.canonical.adapters import api_football  # noqa: E402
from tools.iptc.canonical.ids import surrogate_resolver  # noqa: E402
from tools.iptc.canonical.observation import validate_observation  # noqa: E402
from tools.iptc.canonical.serialize import canonical_envelope  # noqa: E402
from tools.iptc.validate import validate_document  # noqa: E402

#: The source evidence: a sanitized API-Football example payload already checked
#: into this repository. Read-only here — this task changes no provider mapping,
#: no example and no connector.
NATIVE_PATH = REPO_ROOT / "agent-templates/iptc-mappings/example-apifootball.json"

OBSERVATION_PATH = (REPO_ROOT
                    / "tools/iptc/fixtures/observations"
                    / "api-football-soccer-observation.json")
GRAPH_PATH = (REPO_ROOT / "tools/iptc/fixtures/corrected"
              / "api-football-soccer-graph.json")
ENVELOPE_PATH = (REPO_ROOT / "tools/iptc/fixtures/corrected"
                 / "api-football-soccer-envelope.json")

#: Fixed, so the corrected fixtures are reproducible. Nothing in the adapter or
#: the serializer reads the clock; this is the one time value, and it is an input.
OBSERVED_AT = "2026-03-01T22:05:00+00:00"

NATIVE = json.loads(NATIVE_PATH.read_text(encoding="utf-8"))


def observation():
    return api_football.to_observation(NATIVE, observed_at=OBSERVED_AT)


def envelope():
    return canonical_envelope(observation(),
                              id_resolver=surrogate_resolver("api-football"))


def serialized(document):
    """The exact bytes a corrected fixture is checked in as."""
    return json.dumps(document, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


class TestAdapterOutputIsAValidObservation(unittest.TestCase):
    """``validate_observation`` is the adapter's acceptance test (RFC 002 §1)."""

    def test_the_observation_is_valid(self):
        self.assertEqual(validate_observation(observation()), [])

    def test_the_document_claims_the_canonical_observation_contract(self):
        self.assertEqual(observation()["schema_version"], "canonical-observation/1.1")

    def test_the_top_level_document_carries_nothing_but_the_observation(self):
        self.assertEqual(sorted(observation()), ["observation", "schema_version"])

    def test_observed_at_is_the_caller_input_and_is_keyword_only(self):
        self.assertEqual(observation()["observation"]["observed_at"], OBSERVED_AT)
        with self.assertRaises(TypeError):
            api_football.to_observation(NATIVE, OBSERVED_AT)

    def test_the_adapter_reads_the_payload_without_mutating_it(self):
        """An adapter that edits its input makes the second call disagree with the
        first, and makes the checked-in source fixture unreproducible."""
        before = copy.deepcopy(NATIVE)
        api_football.to_observation(NATIVE, observed_at=OBSERVED_AT)
        self.assertEqual(NATIVE, before)


class TestProviderAndRightsHonesty(unittest.TestCase):
    """A checked-in provider example is shape evidence, not an entitlement."""

    def test_the_provider_namespace_and_family_are_recorded(self):
        self.assertEqual(observation()["observation"]["provider"],
                         {"namespace": "api-football", "family": "licensed"})

    def test_the_rights_block_refuses_a_commercial_reading(self):
        """The two flags a production consumer reads. ``rights_findings`` fails
        closed on ``prototype_only``, which is the whole point of setting it."""
        rights = observation()["observation"]["rights"]
        self.assertIs(rights["prototype_only"], True)
        self.assertIs(rights["commercial_use"], False)

    def test_the_data_class_names_the_evidence_rather_than_a_licence(self):
        rights = observation()["observation"]["rights"]
        self.assertEqual(rights["data_class"], api_football.RIGHTS_DATA_CLASS)
        self.assertNotIn("redistributable", rights["data_class"])

    def test_the_adapter_identifies_itself_and_its_endpoint_class(self):
        """Provenance with no adapter block is an anonymous claim: when a fact is
        wrong there is nothing naming the code that produced it."""
        adapter = observation()["observation"]["adapter"]
        self.assertEqual(adapter["name"], "tools.iptc.canonical.adapters.api_football")
        self.assertTrue(adapter["version"])
        self.assertEqual([ref["kind"] for ref in adapter["source_refs"]],
                         ["endpoint-class"])

    def test_no_source_ref_is_request_shaped(self):
        """A URL is how an API key or a licensed path reaches a published fixture.
        ``validate_observation`` refuses one; this asserts none is offered."""
        for ref in observation()["observation"]["adapter"]["source_refs"]:
            for marker in ("://", "?", "&", "key=", "token=", "secret"):
                with self.subTest(marker=marker):
                    self.assertNotIn(marker, ref["value"])


class TestProviderFactsAreReadCorrectly(unittest.TestCase):
    """Every value below is traceable to one key of the checked-in payload."""

    def setUp(self):
        self.observation = observation()["observation"]

    def test_the_event_is_read_from_the_fixture_block(self):
        event = self.observation["event"]
        self.assertEqual(event["provider_id"], "1390823")
        self.assertEqual(event["start_time"], "2025-08-17T19:30:00+00:00")

    def test_the_status_is_the_canonical_key_not_the_provider_short_code(self):
        """``event_status`` is mapped in the adapter so the graph's NewsCode and
        every other provider's observation agree on one vocabulary."""
        self.assertEqual(self.observation["event"]["status"], "closed")

    def test_the_clock_reading_is_carried_as_the_provider_stated_it(self):
        self.assertEqual(self.observation["event"]["clock"], {"minute": "90"})

    def test_the_competition_and_season_are_read_from_the_league_block(self):
        competition = self.observation["competition"]
        self.assertEqual(competition["provider_id"], "140")
        self.assertEqual(competition["name"], "La Liga")
        self.assertEqual(competition["season"]["provider_id"], "2025")

    def test_the_round_string_is_the_providers_own_phase_identifier(self):
        """API-Football addresses a round by that exact string, so recording it as
        the phase's provider identifier is provider-native evidence rather than a
        composite this adapter would have had to invent."""
        phase = self.observation["phase"]
        self.assertEqual(phase["provider_id"], "Regular Season - 1")
        self.assertEqual(phase["name"], "Regular Season - 1")

    def test_the_site_is_read_from_the_venue_block(self):
        site = self.observation["site"]
        self.assertEqual(site["provider_id"], "1474")
        self.assertEqual(site["name"], "RCDE Stadium")
        self.assertEqual(site["city"], "Cornella de Llobregat")

    def test_the_sport_is_declared_as_the_medtop_code_and_a_key(self):
        self.assertEqual(self.observation["sport"],
                         {"medtop": "20001065", "key": "soccer"})

    def test_home_comes_first_and_both_teams_carry_alignment_and_score(self):
        participants = self.observation["participants"]
        self.assertEqual(
            [(p["kind"], p["provider_id"], p["name"], p["alignment"], p["score"])
             for p in participants],
            [("team", "540", "Espanyol", "home", "2"),
             ("team", "530", "Atletico Madrid", "away", "1")],
        )

    def test_the_scoreline_is_full_time_not_half_time(self):
        """``score.halftime`` is a different fact from the result and survives in
        ``observation.raw``; ``goals`` is the one that is the scoreline."""
        self.assertEqual([p["score"] for p in self.observation["participants"]],
                         ["2", "1"])

    def test_the_winner_flag_becomes_a_participant_outcome(self):
        self.assertEqual([p["outcome"] for p in self.observation["participants"]],
                         ["win", "loss"])

    def test_the_raw_payload_is_carried_verbatim_and_only_under_raw(self):
        self.assertEqual(self.observation["raw"], NATIVE)
        sections = set(self.observation) - {"raw"}
        for section in sorted(sections):
            with self.subTest(section=section):
                self.assertNotIn("api-sports.io", json.dumps(self.observation[section]))


class TestAbsenceStaysAbsent(unittest.TestCase):
    """The payload's real absences, confirmed against provider data.

    Each one is a fact the payload does not state. Filling any of them in would
    be indistinguishable, downstream, from the provider having stated it.
    """

    def setUp(self):
        self.observation = observation()["observation"]

    def test_no_competition_type_is_inferred_from_the_standings_flag(self):
        """``league.standings: true`` is not a competition type. Reading it as
        ``league`` would put a NewsCode on the graph nothing in the payload says."""
        self.assertNotIn("type", self.observation["competition"])

    def test_no_outcome_type_is_inferred_from_null_extra_time(self):
        """``score.extratime`` and ``score.penalty`` are both null. That is the
        absence of a statement, not a statement of ``regular``."""
        self.assertNotIn("outcome_type", self.observation["event"])

    def test_no_country_is_invented_for_the_venue(self):
        """``league.country`` is the competition's country, not the venue's."""
        self.assertNotIn("country", self.observation["site"])

    def test_no_attendance_and_no_end_time_are_invented(self):
        for key in ("attendance", "end_time"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.observation["event"])

    def test_no_period_is_derived_from_the_period_timestamps(self):
        """``fixture.periods`` holds two epoch seconds, not a period number."""
        self.assertNotIn("period", self.observation["event"]["clock"])

    def test_no_action_and_no_player_is_invented_from_a_payload_with_neither(self):
        for key in ("actions", "memberships"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.observation)
        self.assertEqual([p["kind"] for p in self.observation["participants"]],
                         ["team", "team"])


class TestRosterEnrichment(unittest.TestCase):
    """The adapter consumes only exact normalized provider roster fields."""

    def test_squad_players_become_individuals_and_memberships(self):
        payload = copy.deepcopy(NATIVE)
        payload["players"] = [
            {
                "team": {"id": 540, "name": "Espanyol"},
                "players": [
                    {"player": {"id": 101, "name": "A. Keeper", "number": 1,
                                "pos": "Goalkeeper"}},
                ],
            },
            {
                "team": {"id": 530, "name": "Atletico Madrid"},
                "players": [
                    {"player": {"id": 201, "name": "F. Forward", "number": 9,
                                "pos": "Attacker"}},
                ],
            },
        ]
        payload["_roster_provenance"] = {
            "provider": {"namespace": "api-football", "family": "licensed"},
            "fixture_id": "1390823",
            "source": "team-squads",
            "endpoint_classes": ["api-football/fixtures",
                                 "api-football/players/squads"],
            "profile_count": 0,
        }

        document = api_football.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(document), [])
        players = document["observation"]["participants"][2:]
        self.assertEqual(players, [
            {"kind": "individual", "provider_id": "101", "name": "A. Keeper",
             "team_provider_id": "540", "position": "goalkeeper",
             "uniform_number": "1"},
            {"kind": "individual", "provider_id": "201", "name": "F. Forward",
             "team_provider_id": "530", "position": "forward",
             "uniform_number": "9"},
        ])
        self.assertEqual(document["observation"]["memberships"], [
            {"individual_provider_id": "101", "team_provider_id": "540",
             "uniform_number": "1"},
            {"individual_provider_id": "201", "team_provider_id": "530",
             "uniform_number": "9"},
        ])
        self.assertEqual(
            [ref["value"] for ref in document["observation"]["adapter"]["source_refs"]],
            ["api-football/fixtures", "api-football/players/squads"],
        )

    def test_lineups_take_precedence_and_carry_exact_statuses(self):
        payload = copy.deepcopy(NATIVE)
        payload["lineups"] = [
            {"team": {"id": 540},
             "startXI": [{"player": {"id": 101, "name": "Home Starter",
                                       "number": 8, "pos": "M"}}],
             "substitutes": []},
            {"team": {"id": 530},
             "startXI": [{"player": {"id": 201, "name": "Away Starter",
                                       "number": 9, "pos": "F"}}],
             "substitutes": [{"player": {"id": 202, "name": "Away Bench",
                                           "number": 18, "pos": "D"}}]},
        ]
        payload["players"] = [
            {"team": {"id": 540},
             "players": [{"player": {"id": 999, "name": "Ignored"}}]},
        ]
        payload["_roster_provenance"] = {
            "source": "fixture-lineups", "profile_count": 0,
        }

        document = api_football.to_observation(payload, observed_at=OBSERVED_AT)
        players = document["observation"]["participants"][2:]
        self.assertEqual(
            [(p["provider_id"], p["player_status"], p["position"],
              p["uniform_number"]) for p in players],
            [("101", "starter", "midfielder", "8"),
             ("201", "starter", "forward", "9"),
             ("202", "substitute", "defender", "18")],
        )
        self.assertNotIn("999", [p["provider_id"] for p in players])

    def test_unknown_position_is_not_fabricated(self):
        payload = copy.deepcopy(NATIVE)
        payload["players"] = [
            {"team": {"id": 540},
             "players": [{"player": {"id": 101, "name": "Utility",
                                       "pos": "Utility"}}]},
            {"team": {"id": 530},
             "players": [{"player": {"id": 201, "name": "Away",
                                       "pos": "M"}}]},
        ]
        player = api_football.to_observation(
            payload, observed_at=OBSERVED_AT)["observation"]["participants"][2]
        self.assertNotIn("position", player)
        self.assertEqual(payload["players"][0]["players"][0]["player"]["pos"],
                         "Utility")

    def test_duplicate_player_id_across_teams_fails_closed(self):
        payload = copy.deepcopy(NATIVE)
        payload["players"] = [
            {"team": {"id": 540},
             "players": [{"player": {"id": 101, "name": "Home"}}]},
            {"team": {"id": 530},
             "players": [{"player": {"id": 101, "name": "Away"}}]},
        ]
        with self.assertRaisesRegex(ValueError, "101"):
            api_football.to_observation(payload, observed_at=OBSERVED_AT)

    def test_a_drawn_fixture_yields_no_participant_outcome(self):
        """API-Football nulls **both** ``winner`` flags on a draw and on a fixture
        that has not finished, so the flag alone cannot tell those apart. Emitting
        ``draw`` would be a guess; the scoreline and the status still travel."""
        payload = copy.deepcopy(NATIVE)
        payload["teams"]["home"]["winner"] = None
        payload["teams"]["away"]["winner"] = None
        payload["goals"] = {"home": 1, "away": 1}
        drawn = api_football.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(drawn), [])
        for participant in drawn["observation"]["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("outcome", participant)
                self.assertEqual(participant["score"], "1")

    def test_a_pre_match_payload_omits_the_scoreline_rather_than_emitting_zero(self):
        """``"0"`` is a claim that both sides have scored nothing, which is a
        different fact from the match not having started."""
        payload = copy.deepcopy(NATIVE)
        payload["fixture"]["status"] = {"long": "Not Started", "short": "NS",
                                        "elapsed": None, "extra": None}
        payload["goals"] = {"home": None, "away": None}
        payload["teams"]["home"]["winner"] = None
        payload["teams"]["away"]["winner"] = None
        pre_match = api_football.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(pre_match), [])
        self.assertEqual(pre_match["observation"]["event"]["status"], "not_started")
        self.assertNotIn("clock", pre_match["observation"]["event"])
        for participant in pre_match["observation"]["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("score", participant)

    def test_a_genuine_nil_nil_scoreline_survives(self):
        """The mirror: ``0`` is knowledge, ``None`` is not, so omission cannot be
        a truthiness test."""
        payload = copy.deepcopy(NATIVE)
        payload["goals"] = {"home": 0, "away": 0}
        nil_nil = api_football.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual([p["score"] for p in nil_nil["observation"]["participants"]],
                         ["0", "0"])


class TestUnmappableProviderValuesFailLoudly(unittest.TestCase):
    """A provider value with no defensible canonical reading is an error, not a
    default. The message has to name the code, or the fix lands by guesswork."""

    def test_an_unmapped_status_short_code_raises_and_names_it(self):
        payload = copy.deepcopy(NATIVE)
        payload["fixture"]["status"]["short"] = "ZZZ"
        with self.assertRaises(ValueError) as raised:
            api_football.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertIn("ZZZ", str(raised.exception))

    def test_a_missing_status_short_code_raises_rather_than_defaulting(self):
        payload = copy.deepcopy(NATIVE)
        payload["fixture"]["status"] = {}
        with self.assertRaises(ValueError):
            api_football.to_observation(payload, observed_at=OBSERVED_AT)

    def test_every_mapped_status_reaches_a_pinned_event_status_newscode(self):
        """A status table entry that no pinned NewsCode scheme admits would be
        caught only at layer 4, one provider fixture later."""
        from tools.iptc.canonical.vocab import EVENT_STATUS

        self.assertTrue(api_football.EVENT_STATUS_BY_SHORT_CODE)
        for short_code, canonical in sorted(
                api_football.EVENT_STATUS_BY_SHORT_CODE.items()):
            with self.subTest(short_code=short_code):
                self.assertIn(canonical, EVENT_STATUS)

    def test_a_payload_with_no_event_identifier_raises(self):
        payload = copy.deepcopy(NATIVE)
        del payload["fixture"]["id"]
        with self.assertRaises(ValueError):
            api_football.to_observation(payload, observed_at=OBSERVED_AT)


class TestCorrectedFixturesAreReproducible(unittest.TestCase):
    """A checked-in fixture that cannot be regenerated is a screenshot."""

    def test_the_observation_fixture_is_reproducible_from_the_adapter(self):
        self.assertEqual(OBSERVATION_PATH.read_text(encoding="utf-8"),
                         serialized(observation()))

    def test_the_envelope_fixture_is_reproducible_byte_for_byte(self):
        self.assertEqual(ENVELOPE_PATH.read_text(encoding="utf-8"),
                         serialized(envelope()))

    def test_the_graph_fixture_is_exactly_the_envelope_graph(self):
        """One graph, checked in twice: once inside the envelope a consumer
        receives and once as the standalone JSON-LD the harness validates. Two
        copies that could disagree would make the conformance claim meaningless."""
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
        self.assertEqual(block["profile"], "machina-iptc-profile/1.2")

    def test_the_checked_in_envelope_is_refused_for_a_production_consumer(self):
        """The rights claim in ``provenance.json`` for this fixture, enforced
        rather than left as prose. The gate itself is A12's; what is new here is
        that a real provider-derived envelope trips it, which is the whole reason
        the adapter marks the observation ``prototype_only``.
        """
        from tools.iptc.validate_graph import rights_findings

        checked_in = json.loads(ENVELOPE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(rights_findings(checked_in, consumer_tier="prototype"), [])
        findings = rights_findings(checked_in, consumer_tier="production")
        self.assertEqual([f["code"] for f in findings], ["rights-prototype-only"])
        self.assertEqual(findings[0]["data_class"], api_football.RIGHTS_DATA_CLASS)

    def test_the_capability_tier_is_core_and_says_why(self):
        """A payload with no clock period, no actions and no player statistics is
        ``core``. Reporting ``live`` would tell a consumer it can rely on
        play-by-play it will never get."""
        capabilities = envelope()["machina_sports_schema"]["capabilities"]
        self.assertEqual(capabilities["tier"], "core")
        self.assertEqual(capabilities["tiers_satisfied"], ["core"])
        self.assertEqual(capabilities["violations"], [])
        self.assertIn("event.actions", capabilities["absent"])
        self.assertIn("event.score", capabilities["present"])


class TestIdentityIsASurrogate(unittest.TestCase):
    """Provider identifiers are crosswalk evidence; canonical identity is minted
    (RFC 001 §7.6). This is the rule the corrected output exists to demonstrate."""

    def setUp(self):
        self.block = envelope()["machina_sports_schema"]

    def test_every_graph_resource_id_is_a_marked_machina_surrogate(self):
        for node in self.block["sport_schema_graph"]["@graph"]:
            with self.subTest(node=node["@type"]):
                self.assertRegex(node["@id"],
                                 r"^urn:machina:sports:[a-z-]+:x[0-9a-f]{32}$")

    def test_no_provider_urn_stem_survives_anywhere_in_the_graph(self):
        """The legacy mappings emit ``urn:apifootball:…``. A corrected document
        that still carried one would be the old identity model in new clothes."""
        blob = json.dumps(self.block["sport_schema_graph"])
        for stem in ("urn:apifootball", "apifootball", "api-sports.io"):
            with self.subTest(stem=stem):
                self.assertNotIn(stem, blob)

    def test_the_crosswalk_holds_every_provider_identifier_the_payload_stated(self):
        entries = self.block["provider_ids"]
        self.assertEqual([e["entity_type"] for e in entries],
                         ["competition", "season", "phase", "site", "event",
                          "team", "team"])
        self.assertEqual(
            sorted(e["provider_id"] for e in entries),
            sorted(["140", "2025", "Regular Season - 1", "1474", "1390823",
                    "540", "530"]),
        )
        for entry in entries:
            with self.subTest(entity=entry["entity_type"]):
                self.assertEqual(entry["provider_namespace"], "api-football")
                self.assertEqual(entry["resolution_method"], "provider-native")

    def test_every_crosswalk_entry_names_the_field_it_came_from(self):
        by_type = {e["entity_type"]: e for e in self.block["provider_ids"]}
        self.assertEqual(by_type["event"]["evidence"],
                         "observation.event.provider_id")
        self.assertEqual(by_type["season"]["evidence"],
                         "observation.competition.season.provider_id")


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
        """``provider.raw`` is excluded deliberately: it is the provider's own
        bytes, it genuinely contains four nulls, and rewriting it would destroy
        the one field whose value is being an unaltered record."""
        view = copy.deepcopy(self.block["event_view"])
        view.get("provider", {}).pop("raw", None)
        blob = json.dumps(view)
        self.assertNotIn("null", blob)
        self.assertNotIn('""', blob)
        for value in sorted(profile_module.PLACEHOLDER_VALUES):
            if value:
                with self.subTest(placeholder=value):
                    self.assertNotIn('"{0}"'.format(value), blob)

    def test_the_provider_nulls_are_still_readable_in_raw(self):
        """The mirror of the two scans above: the absences the graph omits are not
        lost, they are where a reviewer can see what the provider actually said."""
        raw = self.block["event_view"]["provider"]["raw"]
        self.assertIsNone(raw["score"]["extratime"]["home"])
        self.assertIsNone(raw["score"]["penalty"]["home"])

    def test_no_official_resource_carries_a_machina_property(self):
        """The pinned shapes are ``sh:closed``, so one ``machina:`` key on a
        ``sport:`` resource fails layer 2 for the whole document."""
        for node in self.block["sport_schema_graph"]["@graph"]:
            if str(node["@type"]).startswith("sport:"):
                with self.subTest(resource=node["@type"]):
                    self.assertEqual([k for k in node if k.startswith("machina:")], [])


class TestCorrectedGraphConformance(unittest.TestCase):
    """The claim this task exists to make, checked by the PR 1 harness rather
    than by assertion: provider-derived data conforms."""

    @classmethod
    def setUpClass(cls):
        cls.result = validate_document(GRAPH_PATH, "corrected-api-football-soccer",
                                       repo_root=REPO_ROOT)

    def test_all_four_layers_pass(self):
        for layer in ("jsonld_parse", "official_shacl", "machina_profile",
                      "controlled_vocabulary"):
            with self.subTest(layer=layer):
                self.assertTrue(self.result.layers[layer]["ok"],
                                self.result.layers[layer]["detail"])

    def test_the_shacl_pass_is_not_vacuous(self):
        """A SHACL run over zero official-class instances 'conforms'. That is the
        failure mode this whole programme exists to catch."""
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
        """Layer 4 passing on zero NewsCodes would be the vacuity failure again,
        one layer down."""
        detail = self.result.layers["controlled_vocabulary"]["detail"]
        self.assertGreater(len(detail["valid"]), 0)
        for key in ("invalid", "undeclared_prefix", "unverifiable"):
            with self.subTest(key=key):
                self.assertEqual(detail[key], [])

    def test_the_document_conforms_overall(self):
        self.assertTrue(self.result.conforms)


class TestCorrectedSectionIsRegistered(unittest.TestCase):
    """A corrected fixture nothing runs is a corrected fixture nobody checks."""

    def test_both_command_surfaces_know_the_section(self):
        self.assertIn("corrected", iptc_main.SECTIONS)
        self.assertIn("corrected", cli_support.SECTIONS)

    def test_the_corrected_graph_is_registered_and_resolvable(self):
        provenance = report_module.load_provenance()
        entries = provenance["corrected"]
        # This fixture is registered; siblings are other tasks' business. Pinning
        # the whole list here would make every later corrected fixture fail a test
        # that is about API-Football.
        self.assertIn("corrected-api-football-soccer",
                      [entry["fixture"] for entry in entries])
        for entry in entries:
            with self.subTest(fixture=entry["fixture"]):
                self.assertEqual(entry["class"], "corrected-serializer-output")
                self.assertTrue(report_module.resolve(entry).is_file())

    def test_every_corrected_entry_labels_its_evidence_and_its_limits(self):
        """The source is a checked-in provider example. Calling it a production
        capture, or leaving a reader to assume it is one, is the failure mode."""
        for entry in report_module.load_provenance()["corrected"]:
            with self.subTest(fixture=entry["fixture"]):
                self.assertTrue(entry.get("source"))
                self.assertTrue(entry.get("transformation"))
                self.assertTrue(entry.get("emitted_by"))
                self.assertTrue(entry.get("limitation"))
                self.assertTrue(entry.get("rights"))

    def test_the_section_is_reachable_through_registered_fixtures(self):
        registered = dict(cli_support.registered_fixtures(["corrected"]))
        self.assertEqual(registered["corrected-api-football-soccer"], GRAPH_PATH)


if __name__ == "__main__":
    unittest.main(verbosity=2)
