import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

def aggregate_features(params):
    """
    Aggregate soccer match features from API-Football data.
    """
    fixture_id = params.get('fixture_id')
    league = params.get('league')
    season = params.get('season')
    match_stats = params.get('match_stats', [])
    match_events = params.get('match_events', [])

    if not all([fixture_id, league, season]):
        return {"error": "Missing required parameters: fixture_id, league, season"}

    # Extract team IDs and names from stats if available
    home_stats = next((s for s in match_stats if s.get('team', {}).get('id')), {})
    away_stats = next((s for s in match_stats if s.get('team', {}).get('id') and s.get('team', {}).get('id') != home_stats.get('team', {}).get('id')), {})

    # Helper to parse statistics array into a dict
    def parse_stats(stats_list):
        return {item.get('type'): item.get('value') for item in stats_list} if stats_list else {}

    feature_payload = {
        "meta": {
            "league": league,
            "season": season,
            "fixture_id": fixture_id,
            "sport": "soccer",
            "has_stats": len(match_stats) > 0,
            "has_events": len(match_events) > 0
        },
        "home": {
            "team_id": home_stats.get('team', {}).get('id', 'home_id'),
            "name": home_stats.get('team', {}).get('name', 'Home Team'),
            "stats": parse_stats(home_stats.get('statistics', [])),
            "events_count": len([e for e in match_events if e.get('team', {}).get('id') == home_stats.get('team', {}).get('id')])
        },
        "away": {
            "team_id": away_stats.get('team', {}).get('id', 'away_id'),
            "name": away_stats.get('team', {}).get('name', 'Away Team'),
            "stats": parse_stats(away_stats.get('statistics', [])),
            "events_count": len([e for e in match_events if e.get('team', {}).get('id') == away_stats.get('team', {}).get('id')])
        }
    }
    return {"feature_payload": feature_payload}

def filter_search_results(params):
    search_results = params.get('search_results', [])
    relevant_results = [r for result in search_results for r in (result if isinstance(result, list) else [result])]
    return {"filtered_search_results": relevant_results[:10]}

def format_evidence_outputs(params):
    return {
        "news_evidence": {
            'evidence_items': params.get('evidence_items', []),
            'news_reliability': params.get('news_reliability', 0.0)
        },
        "news_deltas": {
            'deltas': params.get('team_level_deltas', {}),
            'news_reliability': params.get('news_reliability', 0.0)
        }
    }

