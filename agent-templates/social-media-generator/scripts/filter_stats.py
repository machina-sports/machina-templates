import json

def filter_team_stats(request_data):
    """
    Extract only social media-relevant stats from API Football response.
    Returns a clean, minimal dict suitable for LLM prompts.
    """
    try:
        if isinstance(request_data, str):
            try:
                request_data = json.loads(request_data)
            except:
                pass
        
        if not isinstance(request_data, dict):
            request_data = {}
        
        params = request_data.get('params', request_data)
        if not isinstance(params, dict):
            params = {}
        
        # Extract home and away stats
        home_stats_raw = params.get('home_stats', {})
        away_stats_raw = params.get('away_stats', {})
        
        def extract_key_stats(stats_obj):
            """Extract only social media-relevant stats"""
            if not isinstance(stats_obj, dict):
                return {}
            
            # Get the stats dict (sometimes wrapped in 'response' array)
            stats = stats_obj
            if 'response' in stats and isinstance(stats['response'], list) and len(stats['response']) > 0:
                stats = stats['response'][0]
            
            if not isinstance(stats, dict):
                return {}
            
            # Extract ONLY the relevant fields for social media
            filtered = {}
            
            # Basic info
            if 'team' in stats and isinstance(stats['team'], dict):
                filtered['team'] = {
                    'name': stats['team'].get('name', ''),
                    'id': stats['team'].get('id')
                }
            
            # Recent form (last 5-10 games)
            if 'form' in stats:
                filtered['form'] = stats['form']
            
            # Fixtures summary
            if 'fixtures' in stats and isinstance(stats['fixtures'], dict):
                fixtures = stats['fixtures']
                filtered['record'] = {
                    'played': fixtures.get('played', {}).get('total', 0),
                    'wins': fixtures.get('wins', {}).get('total', 0),
                    'draws': fixtures.get('draws', {}).get('total', 0),
                    'losses': fixtures.get('loses', {}).get('total', 0),
                    'home_wins': fixtures.get('wins', {}).get('home', 0),
                    'away_wins': fixtures.get('wins', {}).get('away', 0)
                }
            
            # Goals summary
            if 'goals' in stats and isinstance(stats['goals'], dict):
                goals = stats['goals']
                filtered['goals'] = {}
                
                # Goals scored
                if 'for' in goals and isinstance(goals['for'], dict):
                    filtered['goals']['scored'] = {
                        'total': goals['for'].get('total', {}).get('total', 0),
                        'average': goals['for'].get('average', {}).get('total', '0.0')
                    }
                
                # Goals conceded
                if 'against' in goals and isinstance(goals['against'], dict):
                    filtered['goals']['conceded'] = {
                        'total': goals['against'].get('total', {}).get('total', 0),
                        'average': goals['against'].get('average', {}).get('total', '0.0')
                    }
            
            # Clean sheets & failed to score
            if 'clean_sheet' in stats and isinstance(stats['clean_sheet'], dict):
                filtered['clean_sheets'] = stats['clean_sheet'].get('total', 0)
            
            if 'failed_to_score' in stats and isinstance(stats['failed_to_score'], dict):
                filtered['failed_to_score'] = stats['failed_to_score'].get('total', 0)
            
            # Biggest wins/losses (for storytelling)
            if 'biggest' in stats and isinstance(stats['biggest'], dict):
                biggest = stats['biggest']
                filtered['biggest'] = {}
                
                if 'wins' in biggest and isinstance(biggest['wins'], dict):
                    filtered['biggest']['win_home'] = biggest['wins'].get('home', 'N/A')
                    filtered['biggest']['win_away'] = biggest['wins'].get('away', 'N/A')
                
                if 'loses' in biggest and isinstance(biggest['loses'], dict):
                    filtered['biggest']['loss_home'] = biggest['loses'].get('home', 'N/A')
                    filtered['biggest']['loss_away'] = biggest['loses'].get('away', 'N/A')
                
                if 'streak' in biggest and isinstance(biggest['streak'], dict):
                    filtered['biggest']['streak'] = biggest['streak']
            
            # Preferred formation (for tactical analysis)
            if 'lineups' in stats and isinstance(stats['lineups'], list) and len(stats['lineups']) > 0:
                most_used = max(stats['lineups'], key=lambda x: x.get('played', 0) if isinstance(x, dict) else 0)
                if isinstance(most_used, dict):
                    filtered['preferred_formation'] = most_used.get('formation', 'Unknown')
            
            return filtered
        
        # Filter both teams
        home_filtered = extract_key_stats(home_stats_raw)
        away_filtered = extract_key_stats(away_stats_raw)
        
        return {
            "status": True,
            "data": {
                "home_stats_filtered": home_filtered,
                "away_stats_filtered": away_filtered
            },
            "message": "Stats filtered successfully"
        }
        
    except Exception as e:
        return {
            "status": False,
            "data": {
                "home_stats_filtered": {},
                "away_stats_filtered": {},
                "error": str(e)
            },
            "message": f"Filter Exception: {str(e)}"
        }

