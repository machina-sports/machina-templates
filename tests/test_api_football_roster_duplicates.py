"""The roster normalizer against provider rows that repeat.

API-Football occasionally returns the same player twice in one squad, byte for
byte. Refusing the roster over that left a fixture with no mini-games at all,
so a verbatim repeat is now dropped. An id that carries a different name is
still a genuine identity conflict and still refuses.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONNECTOR = REPO_ROOT / "connectors" / "api-football" / "api-football-roster.py"

spec = importlib.util.spec_from_file_location("api_football_roster", CONNECTOR)
roster = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roster)


def squad(players):
    return [{"team": {"id": 746, "name": "Sunderland"}, "players": players}]


JONES = {"id": 381014, "name": "Jenson Jones", "number": 48, "position": "Defender"}
OTHER = {"id": 900001, "name": "Someone Else", "number": 7, "position": "Attacker"}


class SquadDuplicates(unittest.TestCase):
    def test_a_verbatim_repeat_is_dropped_and_the_squad_survives(self):
        normalized, error = roster._normalize_squad(
            squad([JONES, OTHER, dict(JONES)]), "746", {"name": "Sunderland"}, {})
        self.assertIsNone(error)
        self.assertEqual([player["id"] for player in normalized["players"]], [381014, 900001])

    def test_the_same_id_under_another_name_still_refuses(self):
        collision = {**JONES, "name": "Someone Different"}
        normalized, error = roster._normalize_squad(
            squad([JONES, collision]), "746", {"name": "Sunderland"}, {})
        self.assertIsNone(normalized)
        self.assertEqual(error, "a squad contains a duplicate provider player id")


class LineupDuplicates(unittest.TestCase):
    def lineups(self, home_players, away_players):
        return [
            {"team": {"id": 746, "name": "Sunderland"},
             "startXI": [{"player": player} for player in home_players], "substitutes": []},
            {"team": {"id": 42, "name": "Arsenal"},
             "startXI": [{"player": player} for player in away_players], "substitutes": []},
        ]

    def teams(self):
        return {"746": {"name": "Sunderland"}, "42": {"name": "Arsenal"}}

    def test_a_verbatim_repeat_inside_one_lineup_is_dropped(self):
        rosters, error = roster._rosters_from_lineups(
            self.lineups([JONES, OTHER, dict(JONES)], [{"id": 5, "name": "Arsenal Player"}]),
            self.teams(), {})
        self.assertIsNone(error)
        self.assertEqual([player["id"] for player in rosters[0]["players"]], [381014, 900001])

    def test_the_same_player_on_both_teams_still_refuses(self):
        rosters, error = roster._rosters_from_lineups(
            self.lineups([JONES], [dict(JONES)]), self.teams(), {})
        self.assertIsNone(rosters)
        self.assertEqual(error, "a provider player id appears more than once")


if __name__ == "__main__":
    unittest.main()
