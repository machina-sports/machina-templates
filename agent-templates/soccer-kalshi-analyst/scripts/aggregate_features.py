from datetime import datetime, timedelta
import json

def aggregate_features(params):
    """
    Bulletproof feature aggregator.
    """
    try:
        # Handle string input
        if isinstance(params, str):
            try: params = json.loads(params)
            except: pass
        
        # Ensure params is a dict
        if not isinstance(params, dict):
            params = {}
            
        # Check if inputs are nested in 'params' key
        p = params.get('params', params)
        if not isinstance(p, dict): p = {}

        # 1. Identity & Metadata
        event_doc = p.get('event_doc', {})
        if not isinstance(event_doc, dict): event_doc = {}
        
        # Try to find fixture_id
        fixture_id = p.get('fixture_id')
        if not fixture_id:
            fixture_id = event_doc.get('fixture_id') or \
                         str(event_doc.get('@id', '')).split(':')[-1]
        
        # 2. Competitors
        competitors = event_doc.get('sport:competitors', [])
        if not isinstance(competitors, list): competitors = []
        home_team_info = {}
        away_team_info = {}
        for c in competitors:
            if not isinstance(c, dict): continue
            if c.get('sport:qualifier') == 'home': home_team_info = c
            if c.get('sport:qualifier') == 'away': away_team_info = c

        # 3. Statistics
        home_stats_raw = p.get('home_historical_stats', p.get('home_stats', {}))
        away_stats_raw = p.get('away_historical_stats', p.get('away_stats', {}))

        def safe_extract_stats(stats_obj):
            if not isinstance(stats_obj, dict): return {}
            res = stats_obj.get('response', stats_obj)
            if isinstance(res, list) and len(res) > 0: res = res[0]
            if not isinstance(res, dict): return {}
            return res

        h_stats = safe_extract_stats(home_stats_raw)
        a_stats = safe_extract_stats(away_stats_raw)

        # 4. News Deltas
        news_deltas_raw = p.get('news_deltas', {})
        if not isinstance(news_deltas_raw, dict): news_deltas_raw = {}
        news_deltas = news_deltas_raw.get('deltas', {})
        if not isinstance(news_deltas, dict): news_deltas = {}

        # 5. Build Payload
        comp_info = event_doc.get('sport:competition', {})
        if not isinstance(comp_info, dict): comp_info = {}
        
        season_info = comp_info.get('sport:season', {})
        if not isinstance(season_info, dict): season_info = {}

        venue_info = event_doc.get('sport:venue', {})
        if not isinstance(venue_info, dict): venue_info = {}

        feature_payload = {
            "meta": {
                "fixture_id": str(fixture_id) if fixture_id else "unknown",
                "league": str(comp_info.get('@id', '39')).split(':')[-1],
                "season": str(season_info.get('sport:year', '2025')),
                "venue": venue_info.get('name', 'Unknown'),
                "status": event_doc.get('sport:status', 'NS')
            },
            "home": {
                "id": str(home_team_info.get('@id', '')).split(':')[-1],
                "name": home_team_info.get('name', 'Home Team'),
                "stats": h_stats
            },
            "away": {
                "id": str(away_team_info.get('@id', '')).split(':')[-1],
                "name": away_team_info.get('name', 'Away Team'),
                "stats": a_stats
            },
            "news": news_deltas
        }

        return {"feature_payload": feature_payload}
    except Exception as e:
        return {"error": f"Aggregation Exception: {str(e)}", "feature_payload": {}}

def filter_search_results(params):
    try:
        p = params
        if isinstance(p, str): p = json.loads(p)
        if not isinstance(p, dict): return {"filtered_search_results": []}
        
        search_results = p.get('search_results', [])
        relevant = []
        if isinstance(search_results, list):
            for r in search_results:
                if isinstance(r, list): relevant.extend([str(i) for i in r if i])
                elif r: relevant.append(str(r))
        return {"filtered_search_results": relevant[:10]}
    except:
        return {"filtered_search_results": []}

def format_evidence_outputs(params):
    try:
        p = params
        if isinstance(p, str): p = json.loads(p)
        if not isinstance(p, dict): p = {}
        return {
            "news_evidence": {
                "items": p.get('evidence_items', []),
                "reliability": p.get('news_reliability', 0.0)
            },
            "news_deltas": {
                "deltas": p.get('team_level_deltas', {}),
                "reliability": p.get('news_reliability', 0.0)
            }
        }
    except:
        return {"news_evidence": {}, "news_deltas": {}}
