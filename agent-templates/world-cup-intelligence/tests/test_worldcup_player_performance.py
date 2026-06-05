"""Tests for World Cup player performance context primitives."""
import importlib.util
import os

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "worldcup_market_intelligence",
    os.path.join(_parent_dir, "worldcup-market-intelligence.py")
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

normalize_player_match_stats = _module.normalize_player_match_stats
classify_fifa_power_categories = _module.classify_fifa_power_categories
apply_power_ranking_eligibility = _module.apply_power_ranking_eligibility
score_provisional_player_performance = _module.score_provisional_player_performance
merge_official_and_provisional_performance = _module.merge_official_and_provisional_performance


def _player_stats(**overrides):
    base = {
        "player": {"id": 10, "name": "Alex Creator"},
        "statistics": [{
            "games": {"minutes": 87, "position": "M", "rating": "7.8"},
            "goals": {"total": 1, "assists": 1, "saves": 0},
            "shots": {"total": 4, "on": 2},
            "passes": {"total": 54, "key": 5, "accuracy": "86%"},
            "tackles": {"total": 3, "interceptions": 2},
            "duels": {"total": 9, "won": 6},
            "cards": {"yellow": 0, "red": 0},
        }],
    }
    base.update(overrides)
    return base


def test_normalize_player_match_stats_extracts_provider_shape():
    result = normalize_player_match_stats({
        "params": {
            "event_urn": "urn:apifootball:sport_event:123",
            "team": {"id": 7, "name": "Brazil"},
            "players": [_player_stats()],
        }
    })

    assert result["status"] is True
    player = result["data"]["players"][0]
    assert player["player_id"] == "10"
    assert player["name"] == "Alex Creator"
    assert player["team_id"] == "7"
    assert player["team_name"] == "Brazil"
    assert player["minutes_played"] == 87
    assert player["position"] == "M"
    assert player["is_goalkeeper"] is False
    assert player["source_quality"] == "provider"
    assert player["stats"]["goals"] == 1
    assert player["stats"]["assists"] == 1
    assert player["stats"]["key_passes"] == 5


def test_classify_fifa_power_categories_separates_outfield_and_goalkeeper():
    outfield = classify_fifa_power_categories({"params": {"position": "Midfielder"}})["data"]
    keeper = classify_fifa_power_categories({"params": {"position": "G"}})["data"]

    assert outfield["is_goalkeeper"] is False
    assert outfield["categories"] == ["attacking", "creativity", "defending"]
    assert keeper["is_goalkeeper"] is True
    assert keeper["categories"] == ["in_possession", "defending_goal"]


def test_apply_power_ranking_eligibility_enforces_twenty_minutes():
    eligible = apply_power_ranking_eligibility({"params": {"minutes_played": 20}})["data"]
    ineligible = apply_power_ranking_eligibility({"params": {"minutes_played": 19}})["data"]

    assert eligible["eligible_for_power_ranking"] is True
    assert eligible["minimum_minutes"] == 20
    assert ineligible["eligible_for_power_ranking"] is False
    assert "below FIFA minimum" in ineligible["warnings"][0]


def test_score_provisional_player_performance_returns_outfield_scores_with_drivers():
    player = normalize_player_match_stats({"params": {"players": [_player_stats()]}})["data"]["players"][0]
    result = score_provisional_player_performance({"params": {"player": player}})

    assert result["status"] is True
    signal = result["data"]["machina_provisional_performance_signal"]
    assert signal["status"] == "available"
    assert signal["source_quality"] == "provider"
    assert 0 <= signal["confidence"] <= 1
    assert set(signal["scores_0_10"]) == {"attacking", "creativity", "defending", "in_possession", "defending_goal"}
    assert signal["scores_0_10"]["attacking"] is not None
    assert signal["scores_0_10"]["creativity"] is not None
    assert signal["scores_0_10"]["defending"] is not None
    assert signal["scores_0_10"]["in_possession"] is None
    assert signal["drivers"]


def test_score_provisional_player_performance_goalkeeper_uses_goalkeeper_categories():
    player = normalize_player_match_stats({
        "params": {
            "players": [_player_stats(player={"id": 1, "name": "Casey Keeper"}, statistics=[{
                "games": {"minutes": 90, "position": "G", "rating": "8.1"},
                "goals": {"saves": 5},
                "passes": {"total": 31, "accuracy": "74%"},
            }])]
        }
    })["data"]["players"][0]

    signal = score_provisional_player_performance({"params": {"player": player}})["data"]["machina_provisional_performance_signal"]

    assert signal["scores_0_10"]["attacking"] is None
    assert signal["scores_0_10"]["creativity"] is None
    assert signal["scores_0_10"]["defending"] is None
    assert signal["scores_0_10"]["in_possession"] is not None
    assert signal["scores_0_10"]["defending_goal"] is not None


def test_score_provisional_player_performance_marks_under_20_minutes_ineligible():
    player = normalize_player_match_stats({
        "params": {"players": [_player_stats(statistics=[{"games": {"minutes": 12, "position": "F"}}])]}
    })["data"]["players"][0]

    signal = score_provisional_player_performance({"params": {"player": player}})["data"]["machina_provisional_performance_signal"]

    assert signal["status"] == "unavailable"
    assert signal["confidence"] == 0.0
    assert all(value is None for value in signal["scores_0_10"].values())
    assert any("below FIFA minimum" in warning for warning in signal["warnings"])


def test_merge_official_and_provisional_keeps_official_separate_and_pending_by_default():
    player = normalize_player_match_stats({"params": {"players": [_player_stats()]}})["data"]["players"][0]
    provisional = score_provisional_player_performance({"params": {"player": player}})["data"]["machina_provisional_performance_signal"]
    result = merge_official_and_provisional_performance({
        "params": {
            "event": {"event_urn": "urn:apifootball:sport_event:123"},
            "player": player,
            "provisional_signal": provisional,
        }
    })

    context = result["data"]["player_performance_context"]
    assert context["official_fifa_power_ranking"]["status"] == "pending"
    assert context["official_fifa_power_ranking"]["source"] == "fifa.com"
    assert context["official_fifa_power_ranking"]["scores"]["attacking"] is None
    assert context["machina_provisional_performance_signal"]["scores_0_10"]["attacking"] is not None
    assert context["context_and_evidence"]["fallback_path"] == ["provider"]


def test_merge_official_and_provisional_preserves_official_scores_when_available():
    result = merge_official_and_provisional_performance({
        "params": {
            "player": {"player_id": "10", "name": "Alex Creator", "minutes_played": 87, "position": "M"},
            "official_fifa_power_ranking": {
                "status": "available",
                "source": "fifa.com",
                "scores": {"attacking": 8.4, "creativity": 7.9, "defending": 6.1},
            },
            "provisional_signal": {
                "status": "available",
                "scores_0_10": {"attacking": 6.0, "creativity": 6.0, "defending": 6.0, "in_possession": None, "defending_goal": None},
                "confidence": 0.5,
                "source_quality": "provider",
                "drivers": [],
                "warnings": [],
            }
        }
    })

    context = result["data"]["player_performance_context"]
    assert context["official_fifa_power_ranking"]["scores"]["attacking"] == 8.4
    assert context["machina_provisional_performance_signal"]["scores_0_10"]["attacking"] == 6.0
