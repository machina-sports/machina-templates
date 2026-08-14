"""The capability and compatibility contract, provider by provider (task A16b).

Run from the repository root:

    python3 tests/test_iptc_capability_matrix.py -v

Run the file directly, for the same reason as the other IPTC suites: ``tests/``
is a namespace directory with no ``__init__.py``, so ``-m unittest
tests.<module>`` can be shadowed by an installed distribution that ships a
top-level regular ``tests`` package.

**Why an explicit matrix rather than a loop over an expected shape.** A
capability report is the one artefact a consumer plans against *before* it
parses, so the cost of a wrong cell is a consumer that ships against data it will
never receive. Each provider suite already checks its own report, but nothing
until now has held the seven side by side — and side by side is the only place
two things become visible:

- **A cell that is wrong for a reason that is not this provider's fault.** If a
  presence rule regresses, six rows move at once and the shape of the damage says
  so immediately.
- **Which differences are the provider's and which are the schema's.**
  ``not_expressible`` is identical across all seven, because it is a statement
  about ``canonical-observation/1`` and not about anybody's feed. ``present``
  differs seven ways, because that is the feed. Conflating the two sends a reader
  to a provider conversation about a contract gap, or the reverse.

**Every expected value here is derived from the observation's own facts**, not
copied from a report. The Sportradar MLB row reports no score because the
mapping emits ``sport:score`` with explicit nulls; the tennis row reports
``event.lineups`` because its participants are individuals; the Opta row reports
``event.play_by_play`` because its one action carries a label. If a row here
disagrees with the code, one of the two is wrong about the fixture, and the cell
name says which fact to go and read.

**Failures name the provider.** Every assertion runs under a ``subTest`` carrying
the provider namespace and, where it applies, the capability. A single opaque
loop over seven providers reports "the matrix failed", which is the report that
gets muted.

The compatibility half asserts the contract **exactly as it currently stands**,
including the part a reader might expect to be stricter: a missing *optional*
capability is reported and does **not** on its own make ``compatible`` false.
That is `check_compatibility`'s stated behaviour — optional means optional — and
this file pins it rather than quietly improving it. What *does* fail closed is an
unrecognised name, in ``requires`` and in ``optional`` alike.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.iptc.canonical.capabilities import (  # noqa: E402
    ALL_CAPABILITIES,
    NOT_EXPRESSIBLE,
    SCORE_VIOLATION,
    TIER_OPTIONAL,
    TIER_ORDER,
    TIER_REQUIRED,
    capability_report,
    check_compatibility,
)

OBSERVATIONS = REPO_ROOT / "tools/iptc/fixtures/observations"

#: The seven corrected observations, by provider namespace, in the order the
#: corrected section was built. Named rather than globbed: a file appearing in
#: that directory without a row here is a provider nobody decided about.
PROVIDERS = (
    ("sports-skills/espn", "sports-skills-espn-soccer-observation.json"),
    ("api-football", "api-football-soccer-observation.json"),
    ("sportradar-soccer", "sportradar-soccer-observation.json"),
    ("stats-perform-opta", "stats-perform-opta-soccer-observation.json"),
    ("sportradar-tennis", "sportradar-tennis-observation.json"),
    ("sportradar-nfl", "sportradar-nfl-observation.json"),
    ("sportradar-mlb", "sportradar-mlb-observation.json"),
)

#: Canonical observations in that directory that are deliberately NOT rows here,
#: with the reason. This matrix is about what seven *providers* can supply, and
#: the A16d fixture has no provider behind it at all — including it would put a
#: hand-authored document in a table a reader uses to compare feeds. Named rather
#: than filtered by a pattern, so a second such file forces a decision here
#: instead of silently disappearing from the coverage guard below.
NON_PROVIDER_OBSERVATIONS = {
    "mapping-contract-synthetic-observation.json":
        "A16d's hand-authored multi-participant contract fixture. No provider, "
        "no adapter, so nothing about it is evidence about a feed. Covered by "
        "tests/test_iptc_multi_participant_contract.py, which asserts its own "
        "capability report.",
    "nba-reduced-precision-synthetic-observation.json":
        "Hand-authored reduced-precision fixture (RFC 002 §12). No provider "
        "payload was retrieved, so it says nothing about any feed — and it "
        "reports BELOW core by design, because it carries bounded rather than "
        "exact event timing. A row here would put a deliberate below-core "
        "record in a table a reader uses to compare feeds. Covered by "
        "tests/test_iptc_temporal_evidence.py, which asserts its own capability "
        "report and its graph refusal.",
    "soccer-reduced-precision-synthetic-observation.json":
        "The provider-neutrality half of the same pair: a second sport and an "
        "explicit non-UTC offset on the same code path. Same reasons as the "
        "basketball row above, and covered by the same suite.",
}

#: The six core capabilities. Every row below reaches all six, which is why the
#: matrix records what each row has *beyond* them rather than restating them
#: seven times.
CORE = ("event.competition", "event.identity", "event.participants",
        "event.start_time", "event.status", "provenance")

#: The matrix. ``beyond_core`` is what this provider's payload states on top of
#: :data:`CORE`, and each entry names the fact in the observation that produces
#: it. ``tier`` and ``violations`` are the two summary cells a consumer reads
#: first.
MATRIX = {
    # A closed 2-1 match with a scoreline and no winner flag in the native shape.
    "sports-skills/espn": {
        "beyond_core": ("event.score",),
        "tier": "core",
        "violations": (),
    },
    # Adds teams.*.winner (event.result) and fixture.status.elapsed (event.clock).
    "api-football": {
        "beyond_core": ("event.clock", "event.result", "event.score"),
        "tier": "core",
        "violations": (),
    },
    "sportradar-soccer": {
        "beyond_core": ("event.result", "event.score"),
        "tier": "core",
        "violations": (),
    },
    # The only row with a timeline: one action, and it carries a label, so
    # event.play_by_play is present alongside event.actions.
    "stats-perform-opta": {
        "beyond_core": ("event.actions", "event.play_by_play", "event.result",
                        "event.score"),
        "tier": "core",
        "violations": (),
    },
    # Individual participants, so event.lineups is present without any lineup
    # data: the rule is "this payload names people", which is what a consumer
    # asking for lineups can actually rely on here.
    "sportradar-tennis": {
        "beyond_core": ("event.lineups", "event.result", "event.score"),
        "tier": "core",
        "violations": (),
    },
    # 24-17 is a scoreline; the source states no winner, so no event.result.
    "sportradar-nfl": {
        "beyond_core": ("event.score",),
        "tier": "core",
        "violations": (),
    },
    # The set's negative result: a fully conforming document that is missing a
    # fact a consumer needs, and the report is what says so.
    "sportradar-mlb": {
        "beyond_core": (),
        "tier": "core",
        "violations": (SCORE_VIOLATION,),
    },
}

#: Capabilities ``canonical-observation/1`` has no field that could carry. A
#: property of the contract, so it is one tuple rather than seven.
EXPECTED_NOT_EXPRESSIBLE = ("event.coordinates", "event.expected_metrics",
                            "event.formations", "event.tracking")

#: Representative consumers, named for what they would actually be. Each states
#: what it cannot work without and what it would use if offered.
CONSUMERS = {
    "results-feed": {
        "requires": ("event.identity", "event.start_time", "event.status",
                     "event.score"),
        "optional": ("event.result",),
    },
    "live-ticker": {
        "requires": ("event.clock", "event.period", "event.actions"),
        "optional": ("event.play_by_play",),
    },
    "player-stats-page": {
        "requires": ("participant.player_statistics",),
        "optional": ("event.lineups",),
    },
}

#: Which providers satisfy each consumer's ``requires``, derived from the matrix
#: above rather than from a run. ``live-ticker`` and ``player-stats-page`` are
#: satisfied by nobody, and that is the useful finding: this repository has no
#: corrected row with a clock, a period reading and a timeline together, and none
#: with player statistics at all.
CONSUMER_SATISFIED_BY = {
    "results-feed": ("sports-skills/espn", "api-football", "sportradar-soccer",
                     "stats-perform-opta", "sportradar-tennis",
                     "sportradar-nfl"),
    "live-ticker": (),
    "player-stats-page": (),
}


def report(namespace):
    filename = dict(PROVIDERS)[namespace]
    document = json.loads((OBSERVATIONS / filename).read_text(encoding="utf-8"))
    return capability_report(document)["capabilities"]


def expected_present(namespace):
    return tuple(sorted(set(CORE) | set(MATRIX[namespace]["beyond_core"])))


class TestTheMatrixCoversExactlyTheCorrectedProviders(unittest.TestCase):
    """A matrix with a missing row is a matrix that passes by not looking."""

    def test_every_checked_in_observation_has_a_row_or_a_stated_reason(self):
        on_disk = sorted(p.name for p in OBSERVATIONS.glob("*.json"))
        accounted = sorted([filename for _, filename in PROVIDERS]
                           + list(NON_PROVIDER_OBSERVATIONS))
        self.assertEqual(accounted, on_disk)

    def test_every_exclusion_names_a_file_that_exists_and_says_why(self):
        """An exclusion list is a hole in a coverage guard. It stays honest only
        if each hole points at a real file and carries its own reason."""
        for filename, reason in sorted(NON_PROVIDER_OBSERVATIONS.items()):
            with self.subTest(observation=filename):
                self.assertTrue((OBSERVATIONS / filename).is_file())
                self.assertNotIn(filename, dict(PROVIDERS).values())
                self.assertGreater(len(reason), 40)

    def test_every_row_names_a_provider_the_matrix_describes(self):
        self.assertEqual(sorted(MATRIX), sorted(n for n, _ in PROVIDERS))

    def test_all_seven_providers_are_the_ones_this_task_names(self):
        self.assertEqual(len(PROVIDERS), 7)
        for namespace in ("sports-skills/espn", "api-football",
                          "sportradar-soccer", "stats-perform-opta",
                          "sportradar-tennis", "sportradar-nfl",
                          "sportradar-mlb"):
            with self.subTest(provider=namespace):
                self.assertIn(namespace, MATRIX)


class TestPresentIsExactlyWhatEachPayloadStates(unittest.TestCase):
    """Cell by cell, named by provider and by capability."""

    def test_present_matches_the_matrix(self):
        for namespace, _ in PROVIDERS:
            with self.subTest(provider=namespace):
                self.assertEqual(tuple(report(namespace)["present"]),
                                 expected_present(namespace))

    def test_every_provider_reaches_all_six_core_capabilities(self):
        for namespace, _ in PROVIDERS:
            present = set(report(namespace)["present"])
            for capability in CORE:
                with self.subTest(provider=namespace, capability=capability):
                    self.assertIn(capability, present)

    def test_each_capability_beyond_core_is_present_only_where_the_matrix_says(self):
        """The half a per-provider suite cannot check: that a capability is
        *absent* everywhere it should be. A presence rule that started returning
        True unconditionally would pass every 'is it present' test in the
        repository."""
        beyond = sorted({c for row in MATRIX.values()
                         for c in row["beyond_core"]})
        for capability in beyond:
            for namespace, _ in PROVIDERS:
                expected = capability in MATRIX[namespace]["beyond_core"]
                with self.subTest(capability=capability, provider=namespace):
                    self.assertEqual(
                        capability in report(namespace)["present"], expected)

    def test_absent_is_exactly_the_complement_of_present(self):
        for namespace, _ in PROVIDERS:
            row = report(namespace)
            with self.subTest(provider=namespace):
                self.assertEqual(sorted(set(row["present"]) | set(row["absent"])),
                                 sorted(ALL_CAPABILITIES))
                self.assertEqual(set(row["present"]) & set(row["absent"]), set())

    def test_no_provider_claims_a_capability_this_schema_cannot_express(self):
        for namespace, _ in PROVIDERS:
            present = set(report(namespace)["present"])
            for capability in EXPECTED_NOT_EXPRESSIBLE:
                with self.subTest(provider=namespace, capability=capability):
                    self.assertNotIn(capability, present)


class TestNotExpressibleIsAboutTheContractNotTheProvider(unittest.TestCase):
    """Two different absences, kept apart because they send a reader to two
    different places — and only one of them is a provider conversation."""

    def test_the_same_four_are_not_expressible_for_every_provider(self):
        for namespace, _ in PROVIDERS:
            with self.subTest(provider=namespace):
                self.assertEqual(tuple(report(namespace)["not_expressible"]),
                                 EXPECTED_NOT_EXPRESSIBLE)

    def test_the_module_and_the_matrix_agree_on_which_four(self):
        self.assertEqual(tuple(NOT_EXPRESSIBLE), EXPECTED_NOT_EXPRESSIBLE)

    def test_a_not_expressible_capability_is_also_reported_absent(self):
        """It *is* absent. Reporting it in only one of the two lists would make a
        consumer scanning ``absent`` miss it entirely."""
        for namespace, _ in PROVIDERS:
            absent = set(report(namespace)["absent"])
            for capability in EXPECTED_NOT_EXPRESSIBLE:
                with self.subTest(provider=namespace, capability=capability):
                    self.assertIn(capability, absent)

    def test_a_not_expressible_name_is_still_a_known_name(self):
        """The distinction that keeps ``check_compatibility`` honest: asking for
        tracking data is a reasonable request this contract cannot serve, and it
        must read as unmet rather than as a typo."""
        for capability in EXPECTED_NOT_EXPRESSIBLE:
            with self.subTest(capability=capability):
                self.assertIn(capability, ALL_CAPABILITIES)


class TestTiersDoNotSkipAndAreClaimedHonestly(unittest.TestCase):
    """An observation with advanced data but no clock is ``core``. Reporting
    otherwise tells a consumer it can rely on live data it will never get."""

    def test_the_tier_matches_the_matrix(self):
        for namespace, _ in PROVIDERS:
            with self.subTest(provider=namespace):
                self.assertEqual(report(namespace)["tier"],
                                 MATRIX[namespace]["tier"])

    def test_no_provider_reaches_live_or_advanced(self):
        """Stated positively so the day one does, this fails and someone has to
        write down which payload changed."""
        for namespace, _ in PROVIDERS:
            with self.subTest(provider=namespace):
                self.assertEqual(report(namespace)["tiers_satisfied"], ["core"])

    def test_the_two_rows_with_partial_live_data_still_report_core(self):
        """The load-bearing case for 'tiers do not skip'. API-Football has a clock
        and no timeline; Opta has a timeline and no clock. Neither is halfway to
        ``live``, because ``live`` is all three or nothing."""
        for namespace, has, lacks in (
            ("api-football", "event.clock", "event.actions"),
            ("stats-perform-opta", "event.actions", "event.clock"),
        ):
            row = report(namespace)
            with self.subTest(provider=namespace):
                self.assertIn(has, row["present"])
                self.assertIn(lacks, row["absent"])
                self.assertEqual(row["tier"], "core")

    def test_every_row_reports_its_core_tier_with_nothing_required_missing(self):
        for namespace, _ in PROVIDERS:
            with self.subTest(provider=namespace):
                self.assertEqual(
                    report(namespace)["by_tier"]["core"]["required_absent"], [])

    def test_the_tier_tables_agree_with_present_for_every_tier(self):
        for namespace, _ in PROVIDERS:
            row = report(namespace)
            present = set(row["present"])
            for tier in TIER_ORDER:
                if tier not in row["by_tier"]:
                    continue
                block = row["by_tier"][tier]
                with self.subTest(provider=namespace, tier=tier):
                    self.assertEqual(
                        block["required_present"],
                        sorted(n for n in TIER_REQUIRED[tier] if n in present))
                    self.assertEqual(
                        block["optional_present"],
                        sorted(n for n in TIER_OPTIONAL[tier] if n in present))


class TestViolationsAreReportedWhereTheyAreReal(unittest.TestCase):
    """A conforming document can still be missing a fact a consumer needs."""

    def test_violations_match_the_matrix(self):
        for namespace, _ in PROVIDERS:
            with self.subTest(provider=namespace):
                self.assertEqual(tuple(report(namespace)["violations"]),
                                 MATRIX[namespace]["violations"])

    def test_only_the_mlb_row_reports_a_score_absent_on_a_started_event(self):
        offenders = sorted(namespace for namespace, _ in PROVIDERS
                           if SCORE_VIOLATION in report(namespace)["violations"])
        self.assertEqual(offenders, ["sportradar-mlb"])

    def test_the_violation_does_not_cost_the_row_its_core_tier(self):
        """Kept out of tier gating on purpose: a legitimate pre-match payload has
        no score either, and failing it out of ``core`` would make the tier useless
        for the case it exists to serve."""
        row = report("sportradar-mlb")
        self.assertEqual(row["violations"], [SCORE_VIOLATION])
        self.assertEqual(row["tier"], "core")


class TestConsumerRequirementsAreCheckedProviderByProvider(unittest.TestCase):
    """Three representative consumers against seven providers, named on failure."""

    def check(self, namespace, consumer):
        return check_compatibility(report(namespace), **CONSUMERS[consumer])

    def test_each_consumer_is_compatible_with_exactly_the_expected_providers(self):
        for consumer in sorted(CONSUMERS):
            satisfied = sorted(namespace for namespace, _ in PROVIDERS
                               if self.check(namespace, consumer)["compatible"])
            with self.subTest(consumer=consumer):
                self.assertEqual(satisfied,
                                 sorted(CONSUMER_SATISFIED_BY[consumer]))

    def test_a_missing_required_capability_is_named_rather_than_summarised(self):
        """``compatible: false`` alone tells an integrator to open a ticket.
        ``missing_required: ["event.score"]`` tells them what to ask for."""
        result = self.check("sportradar-mlb", "results-feed")
        self.assertFalse(result["compatible"])
        self.assertEqual(result["missing_required"], ["event.score"])
        self.assertEqual(result["unknown_capabilities"], [])

    def test_the_live_ticker_is_refused_by_every_provider_and_says_why(self):
        for namespace, _ in PROVIDERS:
            result = self.check(namespace, "live-ticker")
            with self.subTest(provider=namespace):
                self.assertFalse(result["compatible"])
                self.assertIn("event.period", result["missing_required"])

    def test_a_missing_optional_is_reported_and_does_not_make_it_incompatible(self):
        """The current contract, pinned rather than quietly improved: optional
        means optional. ``sportradar-nfl`` meets every ``results-feed``
        requirement and states no winner, so it is compatible *and* the gap is on
        the record."""
        result = self.check("sportradar-nfl", "results-feed")
        self.assertTrue(result["compatible"])
        self.assertEqual(result["missing_optional"], ["event.result"])
        self.assertEqual(result["missing_required"], [])

    def test_a_provider_that_meets_everything_reports_no_gap_at_all(self):
        result = self.check("api-football", "results-feed")
        self.assertEqual(result, {
            "compatible": True,
            "missing_required": [],
            "missing_optional": [],
            "unknown_capabilities": [],
        })

    def test_the_player_stats_page_is_refused_even_where_lineups_are_offered(self):
        """Tennis names its participants, so the *optional* half is met. The
        required half is not, and an optional match must never rescue that."""
        result = self.check("sportradar-tennis", "player-stats-page")
        self.assertFalse(result["compatible"])
        self.assertEqual(result["missing_required"],
                         ["participant.player_statistics"])
        self.assertEqual(result["missing_optional"], [])


class TestCompatibilityFailsClosedOnAnUnknownName(unittest.TestCase):
    """A check that reads an unknown name as satisfied is worse than no check,
    because it is trusted."""

    def test_an_unknown_required_name_fails_against_every_provider(self):
        for namespace, _ in PROVIDERS:
            result = check_compatibility(report(namespace),
                                         requires=("event.xg",))
            with self.subTest(provider=namespace):
                self.assertFalse(result["compatible"])
                self.assertEqual(result["unknown_capabilities"], ["event.xg"])

    def test_an_unknown_optional_name_fails_too(self):
        """A typo is a typo wherever it appears. Treating an unknown optional as
        merely absent is how a consumer ships against a capability that does not
        exist."""
        for namespace, _ in PROVIDERS:
            result = check_compatibility(report(namespace),
                                         requires=("event.identity",),
                                         optional=("event.xg",))
            with self.subTest(provider=namespace):
                self.assertFalse(result["compatible"])
                self.assertEqual(result["unknown_capabilities"], ["event.xg"])
                self.assertEqual(result["missing_required"], [])

    def test_an_unknown_name_fails_even_when_every_known_requirement_is_met(self):
        """The dangerous case: everything real is satisfied, so a check that
        ignored the unknown name would return ``compatible: true``."""
        result = check_compatibility(report("api-football"),
                                     requires=CORE + ("event.typo",))
        self.assertFalse(result["compatible"])
        self.assertEqual(result["missing_required"], [])
        self.assertEqual(result["unknown_capabilities"], ["event.typo"])

    def test_a_capability_from_a_future_schema_version_is_unknown_not_absent(self):
        for name in ("event.win_probability", "participant.tracking",
                     "provenance.signature"):
            with self.subTest(name=name):
                result = check_compatibility(report("api-football"),
                                             requires=(name,))
                self.assertEqual(result["unknown_capabilities"], [name])
                self.assertEqual(result["missing_required"], [])

    def test_a_known_but_not_expressible_name_is_missing_rather_than_unknown(self):
        """The mirror of the test above, and the reason both exist: ``compatible``
        is false either way, but one of them means 'fix your spelling' and the
        other means 'this contract cannot carry that'."""
        result = check_compatibility(report("api-football"),
                                     requires=("event.tracking",))
        self.assertFalse(result["compatible"])
        self.assertEqual(result["missing_required"], ["event.tracking"])
        self.assertEqual(result["unknown_capabilities"], [])

    def test_a_consumer_that_asks_for_nothing_is_compatible_with_everything(self):
        """The base case, asserted so an empty ``requires`` can never be read as
        an error and turned into a fail-closed of its own."""
        for namespace, _ in PROVIDERS:
            with self.subTest(provider=namespace):
                self.assertTrue(check_compatibility(report(namespace))["compatible"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
