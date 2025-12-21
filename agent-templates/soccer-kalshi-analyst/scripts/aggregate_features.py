from datetime import datetime, timedelta
import json

def aggregate_features(params):
    """
    Aggregate soccer match features from API-Football data and IPTC sport:Event documents.
    """
    p = params
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except Exception:
            pass
            
    if not isinstance(p, dict):
        return {"error": f"Params must be a dict, got {type(p).__name__}"}

    # Extract match metadata from sport:Event document if provided
    event_doc = p.get('event_doc', {})
    fixture_id = p.get('fixture_id') or event_doc.get('metadata', {}).get('event_code')
    league = p.get('league') or event_doc.get('sport:competition', {}).get('@id')
    season = p.get('season') or event_doc.get('sport:competition', {}).get('sport:season', {}).get('sport:year')

    if not fixture_id:
        return {"error": "Missing fixture_id"}

    # Competitors extraction from sport:Event
    competitors = event_doc.get('sport:competitors', [])
    home_team_info = next((c for c in competitors if c.get('sport:qualifier') == 'home'), {})
    away_team_info = next((c for c in competitors if c.get('sport:qualifier') == 'away'), {})

    # Live Match Data
    match_stats = p.get('match_stats', [])
    match_events = p.get('match_events', [])

    # Historical Data (if provided)
    home_history = p.get('home_historical_stats', [])
    away_history = p.get('away_historical_stats', [])

    def parse_stats(stats_list):
        if not isinstance(stats_list, list): return {}
        return {str(item.get('type')): item.get('value') for item in stats_list if isinstance(item, dict)}

    def calculate_form(history):
        if not history: return {"avg_goals": 0, "win_rate": 0}
        total_goals = 0
        wins = 0
        for match in history:
            # Note: Logic here depends on API-Football response format for team statistics
            # This is a placeholder for actual aggregation logic
            pass
        return {"avg_goals": 0, "win_rate": 0}

    feature_payload = {
        "meta": {
            "league": league,
            "season": season,
            "fixture_id": fixture_id,
            "status": event_doc.get('sport:status', 'NS'),
            "venue": event_doc.get('sport:venue', {}).get('name'),
            "start_date": event_doc.get('schema:startDate'),
            "has_live_stats": len(match_stats) > 0,
            "has_historical_stats": len(home_history) > 0
        },
        "home": {
            "team_id": home_team_info.get('@id', 'home_id').split(':')[-1],
            "name": home_team_info.get('name', 'Home Team'),
            "logo": home_team_info.get('schema:logo'),
            "live_stats": parse_stats(next((s for s in match_stats if str(s.get('team', {}).get('id')) == str(home_team_info.get('@id', '').split(':')[-1])), {}).get('statistics', [])),
            "historical_summary": calculate_form(home_history)
        },
        "away": {
            "team_id": away_team_info.get('@id', 'away_id').split(':')[-1],
            "name": away_team_info.get('name', 'Away Team'),
            "logo": away_team_info.get('schema:logo'),
            "live_stats": parse_stats(next((s for s in match_stats if str(s.get('team', {}).get('id')) == str(away_team_info.get('@id', '').split(':')[-1])), {}).get('statistics', [])),
            "historical_summary": calculate_form(away_history)
        }
    }
    
    return {"feature_payload": feature_payload}

def filter_search_results(params):
    p = params
    if isinstance(p, str):
        try: p = json.loads(p)
        except: pass
    if not isinstance(p, dict): return {"filtered_search_results": []}
    
    search_results = p.get('search_results', [])
    relevant_results = []
    if isinstance(search_results, list):
        for result in search_results:
            if isinstance(result, list):
                relevant_results.extend([str(r) for r in result if r])
            elif result:
                relevant_results.append(str(result))
    return {"filtered_search_results": relevant_results[:10]}

def format_evidence_outputs(params):
    p = params
    if isinstance(p, str):
        try: p = json.loads(p)
        except: pass
    if not isinstance(p, dict): p = {}
    
    return {
        "news_evidence": {
            'evidence_items': p.get('evidence_items', []),
            'news_reliability': p.get('news_reliability', 0.0)
        },
        "news_deltas": {
            'deltas': p.get('team_level_deltas', {}),
            'news_reliability': p.get('news_reliability', 0.0)
        }
    }
