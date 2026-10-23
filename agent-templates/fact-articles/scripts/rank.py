"""Step 2: how far each fact is from normal, as a score computed only from the fact's own value.

Scores are only compared within one kind (plan.py divides by the round's best score of that kind),
so each formula just has to order facts of its kind; the scales do not need to match across kinds.
"""


def standing_score(v):
    # Graduated, not binary. Two continuous parts, multiplied:
    #  - extremity = |points - league mean| / largest such distance in the table (0 mid-table, 1 the most extreme team);
    #  - nearest_gap = points to the closest neighbour in the table.
    # A position is a story when the team is far from the pack AND stands apart from the team next to it:
    # last place 8 points adrift is a story; 2nd place 1 point behind the leader is not, because the standing
    # text does not carry that race (the 22/10 test: binary "top 2 = max" beat Palmeiras' 8-game unbeaten run,
    # which the blind reader preferred). An isolated mid-table team scores near 0 through extremity.
    extremity = abs(v["points"] - v["league_mean_points"]) / v["league_max_dev"] if v["league_max_dev"] else 0.0
    return extremity * v["nearest_gap"]


def relegation_gap_score(v):
    gap = v.get("points_over_first_relegated", v.get("points_to_safety", 99))
    return max(0.0, 3.0 - abs(gap) / 2)


def last5_score(v):
    # Recent form against the team's own season rate (points per game, as a share of 3).
    n = len(v["games"])
    return abs(v["points"] / (3 * n) - v["season_points"] / (3 * max(1, v["season_played"]))) * 4


def goals_rate_score(v):
    avg = v["league_avg"] or 1
    return max(abs(v["gf_per_game"] - avg), abs(v["ga_per_game"] - avg)) / avg * 3


def record_score(v):
    return abs(v["won"] / max(1, v["games"]) - v["league_win_rate"]) * 5


SCORERS = {
    "match": lambda v: 0.0,
    "standing": standing_score,
    "relegation_gap": relegation_gap_score,
    "last5": last5_score,
    "streak": lambda v: float(v["length"]),
    "goals_rate": goals_rate_score,
    "casa_record": record_score,
    "fora_record": record_score,
    "h2h_season": lambda v: 1.5 + (0.5 if abs(v["gf"] - v["ga"]) >= 2 else 0),
}


def score_facts(facts):
    """Set `score` on every fact in place; returns the list."""
    for f in facts:
        f["score"] = round(SCORERS[f["kind"]](f["value"]), 3)
    return facts


def invoke_rank(request_data):
    p = request_data.get("params") or {}
    try:
        docs = p["facts_docs"]
        for d in docs:
            score_facts(d["facts"])
    except KeyError as e:
        return {"status": False, "message": f"rank: missing {e} (unknown fact kind or param)"}
    return {"status": True, "data": {"facts_docs": docs}}
