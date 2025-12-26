from datetime import datetime, timedelta
import json

def aggregate_features(request_data):
    """
    Bulletproof feature aggregator.
    Returns in the standard pyscript pattern: {status, data, message}
    """
    try:
        # The pyscript infrastructure passes inputs as request_data.get('params', {})
        if isinstance(request_data, str):
            try: request_data = json.loads(request_data)
            except: pass
        
        if not isinstance(request_data, dict):
            request_data = {}
        
        # Get params from request_data (standard pyscript pattern)
        params = request_data.get('params', request_data)
        if not isinstance(params, dict): params = {}

        # 1. Identity & Metadata
        event_doc = params.get('event_doc', {})
        if not isinstance(event_doc, dict): event_doc = {}
        
        # Try to find fixture_id
        fixture_id = params.get('fixture_id')
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
        home_stats_raw = params.get('home_historical_stats', params.get('home_stats', {}))
        away_stats_raw = params.get('away_historical_stats', params.get('away_stats', {}))

        def safe_extract_stats(stats_obj):
            if not isinstance(stats_obj, dict): return {}
            res = stats_obj.get('response', stats_obj)
            if isinstance(res, list) and len(res) > 0: res = res[0]
            if not isinstance(res, dict): return {}
            return res

        h_stats = safe_extract_stats(home_stats_raw)
        a_stats = safe_extract_stats(away_stats_raw)

        # 4. News Deltas
        news_deltas_raw = params.get('news_deltas', {})
        if not isinstance(news_deltas_raw, dict): news_deltas_raw = {}
        news_deltas = news_deltas_raw.get('deltas', news_deltas_raw)
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

        # Return in standard pyscript format
        return {
            "status": True,
            "data": {
                "feature_payload": feature_payload
            },
            "message": "Features aggregated successfully"
        }
    except Exception as e:
        return {
            "status": False,
            "data": {
                "feature_payload": {},
                "error": str(e)
            },
            "message": f"Aggregation Exception: {str(e)}"
        }

def filter_search_results(request_data):
    try:
        if isinstance(request_data, str): request_data = json.loads(request_data)
        if not isinstance(request_data, dict): 
            return {"status": True, "data": {"filtered_search_results": []}}
        
        params = request_data.get('params', request_data)
        search_results = params.get('search_results', [])
        relevant = []
        if isinstance(search_results, list):
            for r in search_results:
                if isinstance(r, list): relevant.extend([str(i) for i in r if i])
                elif r: relevant.append(str(r))
        return {
            "status": True, 
            "data": {"filtered_search_results": relevant[:10]},
            "message": "Search results filtered"
        }
    except:
        return {"status": True, "data": {"filtered_search_results": []}}

def format_evidence_outputs(request_data):
    try:
        if isinstance(request_data, str): request_data = json.loads(request_data)
        if not isinstance(request_data, dict): request_data = {}
        
        params = request_data.get('params', request_data)
        return {
            "status": True,
            "data": {
            "news_evidence": {
                    "items": params.get('evidence_items', []),
                    "reliability": params.get('news_reliability', 0.0)
            },
            "news_deltas": {
                    "deltas": params.get('team_level_deltas', {}),
                    "reliability": params.get('news_reliability', 0.0)
            }
            },
            "message": "Evidence formatted"
        }
    except:
        return {"status": True, "data": {"news_evidence": {}, "news_deltas": {}}}
