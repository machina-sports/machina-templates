"""Tests for the Sportradar MLB canonical adapter (PR 2, task A15b.3).

Run from the repository root:

    python3 tests/test_iptc_sportradar_mlb_adapter.py -v

Run the file directly, for the same reason as
``tests/test_iptc_canonical_serializer.py``: ``tests/`` is a namespace directory
with no ``__init__.py``, so ``-m unittest tests.<module>`` can be shadowed by an
installed distribution that ships a top-level regular ``tests`` package.

A focused file per provider, on purpose: a failure here names Sportradar MLB
rather than "the canonical suite", and the four-layer assertion block is
deliberately repeated rather than factored into a shared loop (A14 handoff
item 1, restated by A15b).

**There is no raw Sportradar MLB payload in this repository.** The only evidence
is ``tools/iptc/fixtures/baseline/sportradar-mlb-event.json`` — a document PR 1
hand-authored from the literal key set of ``iptc-sportradar-event-mlb-mapping``.
It is therefore a **legacy mapping-contract shape**: the output of Machina's own
mapping, two removes from what Sportradar sends, and synthetic throughout. No
Sportradar endpoint was called, no credential exists in this repository and there
is no network access in this harness. Calling this row provider data, or a
commercial entitlement, would be a claim nothing here supports.

What this file defends beyond the tennis and NFL rows:

1. **Baseball is its own sport.** ``medtop:20000849``, checked against the pinned
   mediatopic scheme.
2. **The explicit nulls are dropped, and the gap is REPORTED rather than filled.**
   This mapping emits ``sport:homeScore: null`` on purpose — its own comment says
   why: ``schedule.json`` carries no runs and a later workflow merges them in. The
   corrected output omits the scoreline and the capability report raises
   ``score-absent-on-started-event``, which is the honest outcome for a closed
   game with no score. Emitting ``"0"`` would invent a shutout.
3. **The status vocabulary is wider than the NFL one, and the evidence says why.**
   ``sportradar-mlb-sync-results`` writes ``game.status`` onto ``sport:status``
   with no rewrite, so raw Sportradar codes reach this field on the MLB path where
   they cannot on the NFL one. The two adapters are deliberately not symmetric.
4. **The doubleheader disambiguators do not reach the graph.**
   ``sport:doubleHeader`` and ``sport:gameNumber`` are load-bearing downstream and
   have no canonical home, so they stay in ``raw`` and the gap is stated rather
   than papered over.
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
from tools.iptc.canonical.adapters import sportradar_mlb  # noqa: E402
from tools.iptc.canonical.ids import surrogate_resolver  # noqa: E402
from tools.iptc.canonical.observation import validate_observation  # noqa: E402
from tools.iptc.canonical.serialize import canonical_envelope  # noqa: E402
from tools.iptc.validate import validate_document  # noqa: E402

#: The source evidence: PR 1's frozen baseline fixture for this mapping. READ
#: ONLY — it is the "before" document the corrected output is measured against,
#: and this task does not edit it.
SOURCE_PATH = (REPO_ROOT / "tools/iptc/fixtures/baseline"
               / "sportradar-mlb-event.json")

OBSERVATION_PATH = (REPO_ROOT
                    / "tools/iptc/fixtures/observations"
                    / "sportradar-mlb-observation.json")
GRAPH_PATH = (REPO_ROOT / "tools/iptc/fixtures/corrected"
              / "sportradar-mlb-graph.json")
ENVELOPE_PATH = (REPO_ROOT / "tools/iptc/fixtures/corrected"
                 / "sportradar-mlb-envelope.json")

#: Fixed, so the corrected fixtures are reproducible. Nothing in the adapter or
#: the serializer reads the clock; this is the one time value, and it is an input.
OBSERVED_AT = "2026-03-01T22:05:00+00:00"

SOURCE = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))


def observation():
    return sportradar_mlb.to_observation(SOURCE, observed_at=OBSERVED_AT)


def envelope():
    return canonical_envelope(observation(),
                              id_resolver=surrogate_resolver("sportradar-mlb"))


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
            sportradar_mlb.to_observation(SOURCE, OBSERVED_AT)

    def test_the_adapter_reads_the_source_without_mutating_it(self):
        before = copy.deepcopy(SOURCE)
        sportradar_mlb.to_observation(SOURCE, observed_at=OBSERVED_AT)
        self.assertEqual(SOURCE, before)


class TestTheSourceIsLabelledForWhatItIs(unittest.TestCase):
    """No raw Sportradar MLB payload exists here, so this row may not borrow the
    soccer row's data class."""

    def test_the_data_class_says_legacy_mapping_contract_shape(self):
        rights = observation()["observation"]["rights"]
        self.assertEqual(rights["data_class"], "legacy-mapping-contract-shape")
        self.assertEqual(rights["data_class"], sportradar_mlb.RIGHTS_DATA_CLASS)

    def test_the_data_class_is_not_the_one_a_real_provider_example_earns(self):
        self.assertNotEqual(sportradar_mlb.RIGHTS_DATA_CLASS,
                            "licensed-provider-example-fixture")
        for word in ("redistributable", "provider-example", "entitlement",
                     "production"):
            with self.subTest(word=word):
                self.assertNotIn(word, sportradar_mlb.RIGHTS_DATA_CLASS)

    def test_the_source_ref_names_the_mapping_rather_than_an_endpoint(self):
        refs = observation()["observation"]["adapter"]["source_refs"]
        self.assertEqual([ref["kind"] for ref in refs], ["legacy-mapping-output"])
        self.assertEqual(refs[0]["value"], "iptc-sportradar-event-mlb-mapping")
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
        """The legacy MLB and NFL mappings both mint
        ``urn:sportradar:sport_event:<id>`` with no sport in the stem, so their
        identifier spaces collide in the old model. A per-feed crosswalk namespace
        is what keeps them apart here."""
        self.assertEqual(observation()["observation"]["provider"],
                         {"namespace": "sportradar-mlb", "family": "licensed"})

    def test_the_adapter_identifies_itself(self):
        adapter = observation()["observation"]["adapter"]
        self.assertEqual(adapter["name"],
                         "tools.iptc.canonical.adapters.sportradar_mlb")
        self.assertTrue(adapter["version"])


class TestProviderFactsAreReadCorrectly(unittest.TestCase):
    """Every value below is traceable to one key of the checked-in source."""

    def setUp(self):
        self.observation = observation()["observation"]

    def test_the_event_identifier_is_the_sportradar_one_not_machinas_urn(self):
        event = self.observation["event"]
        self.assertEqual(event["provider_id"],
                         "00000000-0000-4000-8000-000000009002")
        self.assertEqual(event["start_time"], "2026-04-15T23:05:00+00:00")

    def test_the_status_is_the_canonical_key_not_the_provider_code(self):
        self.assertEqual(self.observation["event"]["status"], "closed")

    def test_only_sport_status_is_read_and_not_the_mappings_duplicate(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:matchStatus"] = "zzz-not-a-status"
        ignored = sportradar_mlb.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(ignored["observation"]["event"]["status"], "closed")

    def test_the_sport_is_baseball_as_a_pinned_mediatopic_code(self):
        """``schema:sportName`` says ``mlb``, which is a league. The sport is
        baseball, and ``medtop:20000849`` is the pinned code for it."""
        self.assertEqual(self.observation["sport"],
                         {"medtop": "20000849", "key": "baseball"})

    def test_the_venue_carries_its_city_and_no_country_is_invented(self):
        site = self.observation["site"]
        self.assertEqual(site["provider_id"],
                         "00000000-0000-4000-8000-000000009802")
        self.assertEqual(site["name"], "Synthetic Ballpark")
        self.assertEqual(site["city"], "Synthetic City")
        self.assertNotIn("country", site)

    def test_the_label_is_composed_from_the_two_team_names(self):
        self.assertEqual(self.observation["event"]["label"],
                         "Synthetic City Sentinels vs Synthetic Town Tanagers")

    def test_both_competitors_are_teams_with_alignment_and_no_score(self):
        """The scoreline is the interesting half and it lives in its own class
        below: this source states ``null`` for both, so no score is emitted."""
        self.assertEqual(
            [(p["kind"], p["provider_id"], p["name"], p["alignment"])
             for p in self.observation["participants"]],
            [("team", "00000000-0000-4000-8000-000000009201",
              "Synthetic City Sentinels", "home"),
             ("team", "00000000-0000-4000-8000-000000009202",
              "Synthetic Town Tanagers", "away")],
        )

    def test_home_is_emitted_first_even_when_the_source_lists_away_first(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:competitors"].reverse()
        reordered = sportradar_mlb.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(
            [p["alignment"] for p in reordered["observation"]["participants"]],
            ["home", "away"],
        )

    def test_the_team_name_is_the_mappings_composed_market_plus_name(self):
        """``sport:market`` is stated separately and is also already inside
        ``name``. The composed name is what the source says the team is called;
        the market is not an official term and ``TeamShape`` is ``sh:closed``
        admitting only ``rdfs:label``, so it stays in ``raw``."""
        blob = json.dumps({k: v for k, v in self.observation.items()
                           if k != "raw"})
        self.assertNotIn("sport:market", blob)
        self.assertEqual(
            self.observation["raw"]["sport:competitors"][0]["sport:market"],
            "Synthetic City")

    def test_the_source_document_is_carried_verbatim_and_only_under_raw(self):
        self.assertEqual(self.observation["raw"], SOURCE)
        for section in sorted(set(self.observation) - {"raw"}):
            with self.subTest(section=section):
                self.assertNotIn("doubleHeader",
                                 json.dumps(self.observation[section]))


class TestTheExplicitNullsAreDroppedAndTheGapIsReported(unittest.TestCase):
    """The reason this row is worth having.

    The mapping's own description says it emits ``sport:score`` with explicit
    nulls on purpose: ``schedule.json`` carries no runs, and
    ``sportradar-mlb-sync-results`` merges them in from the daily boxscore feed
    later. So a closed game with no scoreline is a real state of this document,
    not a parse failure — and the honest output is to omit the score and say so,
    rather than to emit ``"0"`` and invent a shutout.
    """

    def test_neither_participant_carries_a_score(self):
        for participant in observation()["observation"]["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("score", participant)

    def test_no_zero_is_substituted_anywhere_outside_raw(self):
        block = envelope()["machina_sports_schema"]
        blob = json.dumps(block["sport_schema_graph"])
        self.assertNotIn("sport:score", blob)

    def test_the_capability_report_raises_the_score_gap_rather_than_hiding_it(self):
        """A closed event with no scoreline is exactly what
        ``score-absent-on-started-event`` exists to report. This is the first
        corrected row that trips it, and tripping it is correct."""
        capabilities = envelope()["machina_sports_schema"]["capabilities"]
        self.assertEqual(capabilities["violations"],
                         ["score-absent-on-started-event"])
        self.assertIn("event.score", capabilities["absent"])
        self.assertIn("event.result", capabilities["absent"])

    def test_the_violation_costs_no_tier_because_a_score_is_optional_at_core(self):
        capabilities = envelope()["machina_sports_schema"]["capabilities"]
        self.assertEqual(capabilities["tier"], "core")
        self.assertEqual(capabilities["tiers_satisfied"], ["core"])

    def test_the_providers_own_nulls_are_still_readable_in_raw(self):
        score = observation()["observation"]["raw"]["sport:score"]
        self.assertIsNone(score["sport:homeScore"])
        self.assertIsNone(score["sport:awayScore"])

    def test_a_merged_scoreline_is_read_when_the_source_states_one(self):
        """The mirror. Once ``sync-results`` has merged the runs in, the same
        document states a scoreline and the adapter reads it as strings."""
        payload = copy.deepcopy(SOURCE)
        payload["sport:score"] = {"sport:homeScore": 4, "sport:awayScore": 0}
        scored = sportradar_mlb.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(scored), [])
        self.assertEqual(
            [p["score"] for p in scored["observation"]["participants"]],
            ["4", "0"])
        merged = canonical_envelope(
            scored, id_resolver=surrogate_resolver("sportradar-mlb"))
        self.assertEqual(
            merged["machina_sports_schema"]["capabilities"]["violations"], [])


class TestTheCompetitionIdentityIsAMappingConstant(unittest.TestCase):
    """The same honest reading the NFL row makes, and it is asserted here too
    rather than cross-referenced: a reader of this file must not have to open
    another one to learn that two of these six identifiers are literals."""

    def setUp(self):
        self.observation = observation()["observation"]

    def test_the_competition_and_season_identifiers_are_the_mapping_literals(self):
        competition = self.observation["competition"]
        self.assertEqual(competition["provider_id"], "mlb")
        self.assertEqual(competition["name"], "MLB")
        self.assertEqual(competition["season"]["provider_id"], "2026")
        self.assertEqual(competition["season"]["name"], "MLB 2026")

    def test_the_adapter_names_them_as_constants_rather_than_provider_fields(self):
        self.assertEqual(sorted(sportradar_mlb.MAPPING_CONSTANT_IDENTIFIERS),
                         ["competition", "season"])

    def test_the_event_venue_and_team_identifiers_are_provider_uuids(self):
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
        entry = next(e for e in report_module.load_provenance()["corrected"]
                     if e["fixture"] == "corrected-sportradar-mlb")
        self.assertIn("mapping constant", entry["limitation"].lower())


class TestAbsenceStaysAbsent(unittest.TestCase):
    """The source's real absences, and the facts it states that this profile has
    nowhere to put."""

    def setUp(self):
        self.observation = observation()["observation"]

    def test_no_winner_is_invented_from_a_document_with_no_scoreline(self):
        for participant in self.observation["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("outcome", participant)

    def test_the_doubleheader_disambiguators_do_not_reach_the_graph(self):
        """``sport:gameNumber`` and ``sport:doubleHeader`` exist because MLB plays
        two games between the same teams on the same day, and a naive team+date
        join would collapse the pair. Neither is an official term —
        ``sport:doubleHeader`` is a named provider leak in
        ``rules/provider-leak-terms.json`` — and this profile has no home for
        either, so both stay in ``raw`` and the gap goes to the handoff rather
        than into an invented property."""
        blob = json.dumps(envelope()["machina_sports_schema"]
                          ["sport_schema_graph"]["@graph"])
        for term in ("sport:gameNumber", "sport:doubleHeader",
                     "sport:matchStatus", "sport:market"):
            with self.subTest(term=term):
                self.assertNotIn(term, blob)

    def test_they_are_still_readable_in_raw(self):
        raw = self.observation["raw"]
        self.assertEqual(raw["sport:gameNumber"], 1)
        self.assertIs(raw["sport:doubleHeader"], False)

    def test_no_clock_no_period_and_no_inning_is_invented(self):
        self.assertNotIn("clock", self.observation["event"])

    def test_no_phase_and_no_competition_type_are_invented(self):
        """MLB has a regular season and a post-season, and this document says
        which one this game is in nowhere at all."""
        self.assertNotIn("phase", self.observation)
        self.assertNotIn("type", self.observation["competition"])

    def test_no_outcome_type_end_time_or_attendance_is_invented(self):
        for key in ("outcome_type", "end_time", "attendance"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.observation["event"])

    def test_no_action_no_membership_and_no_statistic_is_invented(self):
        """The event mapping emits no timeline, no roster and no statistics. The
        connector has separate pitcher and team-statistics workflows; joining one
        to this document would attach numbers to a game nothing here says they
        belong to."""
        for key in ("actions", "memberships"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.observation)
        for participant in self.observation["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("statistics", participant)

    def test_a_pre_match_source_is_read_without_a_score(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:status"] = "scheduled"
        pre_match = sportradar_mlb.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(pre_match), [])
        self.assertEqual(pre_match["observation"]["event"]["status"],
                         "not_started")
        pre_match_envelope = canonical_envelope(
            pre_match, id_resolver=surrogate_resolver("sportradar-mlb"))
        self.assertEqual(
            pre_match_envelope["machina_sports_schema"]["capabilities"]
            ["violations"], [],
            "a pre-match document with no score is not a score gap")


class TestUnmappableProviderValuesFailLoudly(unittest.TestCase):
    """A provider value with no defensible canonical reading is an error, not a
    default. The message has to name the value, or the fix lands by guesswork."""

    def test_an_unmapped_status_raises_and_names_it(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:status"] = "zzz"
        with self.assertRaises(ValueError) as raised:
            sportradar_mlb.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertIn("zzz", str(raised.exception))
        self.assertIn("mlb", str(raised.exception))

    def test_the_table_covers_both_write_paths_this_repository_has(self):
        """``iptc-sportradar-event-mlb-mapping`` rewrites ``created`` and
        ``scheduled`` to ``not_started`` and ``inprogress`` to ``live``.
        ``sportradar-mlb-sync-results`` then writes ``game.status`` onto the same
        field with NO rewrite, so the raw codes reach it too. Both are checked-in
        evidence, so both spellings are mapped."""
        self.assertEqual(sorted(sportradar_mlb.EVENT_STATUS_BY_CODE),
                         ["closed", "created", "inprogress", "live",
                          "not_started", "scheduled"])
        for code in ("created", "scheduled", "not_started"):
            with self.subTest(code=code):
                self.assertEqual(sportradar_mlb.EVENT_STATUS_BY_CODE[code],
                                 "not_started")
        for code in ("inprogress", "live"):
            with self.subTest(code=code):
                self.assertEqual(sportradar_mlb.EVENT_STATUS_BY_CODE[code],
                                 "in_progress")

    def test_the_table_is_wider_than_the_nfl_one_and_the_asymmetry_is_deliberate(self):
        """The NFL connector rewrites on every write path it has, so no raw code
        can reach its ``sport:status``. The MLB one does not. Two adapters
        agreeing on a vocabulary neither provider states would be tidier and
        wrong."""
        from tools.iptc.canonical.adapters import sportradar_nfl

        self.assertEqual(sorted(sportradar_nfl.EVENT_STATUS_BY_CODE),
                         ["closed", "live", "not_started"])
        self.assertLess(set(sportradar_nfl.EVENT_STATUS_BY_CODE),
                        set(sportradar_mlb.EVENT_STATUS_BY_CODE))

    def test_a_status_the_repository_has_no_evidence_for_raises(self):
        """``complete`` is Sportradar's "game over, statistics not final" state
        and appears in no checked-in expression here. Reading it as ``closed``
        would be a guess that validates."""
        for code in ("complete", "unnecessary", "if-necessary"):
            payload = copy.deepcopy(SOURCE)
            payload["sport:status"] = code
            with self.subTest(code=code):
                self.assertNotIn(code, sportradar_mlb.EVENT_STATUS_BY_CODE)
                with self.assertRaises(ValueError):
                    sportradar_mlb.to_observation(payload,
                                                  observed_at=OBSERVED_AT)

    def test_a_missing_status_raises_rather_than_defaulting(self):
        payload = copy.deepcopy(SOURCE)
        del payload["sport:status"]
        with self.assertRaises(ValueError):
            sportradar_mlb.to_observation(payload, observed_at=OBSERVED_AT)

    def test_a_null_status_raises_rather_than_defaulting(self):
        """``sync-results`` writes whatever ``scored_map`` returns, and a game
        the boxscore feed does not carry yields ``None``."""
        payload = copy.deepcopy(SOURCE)
        payload["sport:status"] = None
        with self.assertRaises(ValueError):
            sportradar_mlb.to_observation(payload, observed_at=OBSERVED_AT)

    def test_every_mapped_status_reaches_a_pinned_event_status_newscode(self):
        from tools.iptc.canonical.vocab import EVENT_STATUS

        self.assertTrue(sportradar_mlb.EVENT_STATUS_BY_CODE)
        for code, canonical in sorted(sportradar_mlb.EVENT_STATUS_BY_CODE.items()):
            with self.subTest(code=code):
                self.assertIn(canonical, EVENT_STATUS)

    def test_a_source_with_no_event_identifier_raises(self):
        payload = copy.deepcopy(SOURCE)
        del payload["@id"]
        with self.assertRaises(ValueError):
            sportradar_mlb.to_observation(payload, observed_at=OBSERVED_AT)

    def test_an_event_id_outside_the_legacy_urn_stem_raises(self):
        payload = copy.deepcopy(SOURCE)
        payload["@id"] = "urn:something-else:9002"
        with self.assertRaises(ValueError):
            sportradar_mlb.to_observation(payload, observed_at=OBSERVED_AT)

    def test_a_source_stating_a_different_league_raises_and_names_it(self):
        """This adapter asserts ``medtop`` 20000849. An NFL document read by it
        would emit baseball for a football game, and nothing downstream could
        tell — and the two mappings share every URN stem, so nothing in the
        identifiers would catch it either."""
        payload = copy.deepcopy(SOURCE)
        payload["schema:sportName"] = "nfl"
        with self.assertRaises(ValueError) as raised:
            sportradar_mlb.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertIn("nfl", str(raised.exception))


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
                         sportradar_mlb.RIGHTS_DATA_CLASS)

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
                self.assertNotIn("000000009201", json.dumps(node))

    def test_the_crosswalk_holds_every_identifier_the_source_stated(self):
        entries = self.block["provider_ids"]
        self.assertEqual([e["entity_type"] for e in entries],
                         ["competition", "season", "site", "event",
                          "team", "team"])
        self.assertEqual(
            sorted(e["provider_id"] for e in entries),
            sorted(["mlb", "2026",
                    "00000000-0000-4000-8000-000000009802",
                    "00000000-0000-4000-8000-000000009002",
                    "00000000-0000-4000-8000-000000009201",
                    "00000000-0000-4000-8000-000000009202"]),
        )
        for entry in entries:
            with self.subTest(entity=entry["entity_type"]):
                self.assertEqual(entry["provider_namespace"], "sportradar-mlb")
                self.assertEqual(entry["resolution_method"], "provider-native")

    def test_the_mlb_surrogates_differ_from_the_nfl_ones_for_the_same_uuid(self):
        """Identity is provider-scoped. The two legacy mappings share every URN
        stem, so the same UUID under two feeds must still mint two identifiers —
        and nothing here claims they are the same entity."""
        from tools.iptc.canonical.ids import surrogate_resolver as resolver

        shared = "00000000-0000-4000-8000-000000009201"
        self.assertNotEqual(resolver("sportradar-mlb")("team", shared),
                            resolver("sportradar-nfl")("team", shared))

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

    def test_no_sport_specific_statistic_vocabulary_is_asserted(self):
        blob = json.dumps(self.block["sport_schema_graph"]["@graph"])
        for token in ("spbblstat", "spsocstat", "spstat", "spsocaction"):
            with self.subTest(token=token):
                self.assertNotIn(token, blob)


class TestCorrectedGraphConformance(unittest.TestCase):
    """The claim this task exists to make, checked by the PR 1 harness rather
    than by assertion: an MLB-derived document conforms."""

    @classmethod
    def setUpClass(cls):
        cls.result = validate_document(GRAPH_PATH, "corrected-sportradar-mlb",
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

    def test_the_provider_leak_gate_is_zero_where_the_baseline_row_is_not(self):
        """``sport:doubleHeader`` and ``sport:matchStatus`` are both named in
        ``rules/provider-leak-terms.json`` and both are in the baseline document.
        Gate 4 at zero here is the measured difference."""
        baseline = validate_document(SOURCE_PATH, "sportradar-mlb-event",
                                    repo_root=REPO_ROOT)
        self.assertGreater(
            baseline.counters["provider_properties_in_iptc_namespace"], 0)
        self.assertEqual(
            self.result.counters["provider_properties_in_iptc_namespace"], 0)

    def test_the_controlled_vocabulary_layer_checked_real_codes(self):
        detail = self.result.layers["controlled_vocabulary"]["detail"]
        self.assertGreater(len(detail["valid"]), 0)
        for key in ("invalid", "undeclared_prefix", "unverifiable"):
            with self.subTest(key=key):
                self.assertEqual(detail[key], [])

    def test_the_baseball_mediatopic_code_is_verified(self):
        detail = self.result.layers["controlled_vocabulary"]["detail"]
        self.assertIn("http://cv.iptc.org/newscodes/mediatopic/20000849",
                      [item["value"] for item in detail["valid"]])

    def test_the_document_conforms_overall(self):
        self.assertTrue(self.result.conforms)


class TestCorrectedSectionIsRegistered(unittest.TestCase):
    """A corrected fixture nothing runs is a corrected fixture nobody checks."""

    def setUp(self):
        self.entry = next(
            e for e in report_module.load_provenance()["corrected"]
            if e["fixture"] == "corrected-sportradar-mlb")

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

    def test_the_entry_records_the_score_gap_and_the_doubleheader_gap(self):
        """Both are real losses against the baseline document, and a corrected row
        that only listed its wins would be the kind of audit this programme
        exists not to produce."""
        prose = (self.entry["limitation"] + self.entry["coverage"]).lower()
        for phrase in ("score", "doubleheader"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, prose)

    def test_the_entry_makes_no_commercial_or_entitlement_claim(self):
        prose = json.dumps(self.entry).lower()
        self.assertIn("not an entitlement", prose)
        self.assertNotIn("redistributable", prose)

    def test_the_section_is_reachable_through_registered_fixtures(self):
        registered = dict(cli_support.registered_fixtures(["corrected"]))
        self.assertEqual(registered["corrected-sportradar-mlb"], GRAPH_PATH)

    def test_the_baseline_mlb_fixture_is_untouched(self):
        entry = next(e for e in report_module.load_provenance()["baseline"]
                     if e["fixture"] == "sportradar-mlb-event")
        self.assertEqual(entry["class"], "mapping-contract-synthetic")
        self.assertEqual(report_module.resolve(entry), SOURCE_PATH)
        self.assertTrue(report_module.resolve(entry).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
