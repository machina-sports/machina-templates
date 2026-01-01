def calculate_power_rankings(request_data):
    """
    Calculate power rankings for soccer teams based on performance metrics.
    
    Uses 4 pillars:
    - Outcome (40%): Win rate and points per game
    - Attack (25%): Goals scored and scoring consistency
    - Defense (25%): Goals conceded and clean sheets
    - Discipline (10%): Card management
    
    Returns rankings sorted by power_score in descending order.
    """
    try:
        # Parse request_data
        if isinstance(request_data, str):
            import json
            request_data = json.loads(request_data)
        
        params = request_data.get('params', request_data)
        teams_stats = params.get('teams_stats', [])
        teams_info = params.get('teams_info', [])
        league_id = params.get('league_id', 'unknown')
        season = params.get('season', 'unknown')
        
        # Create lookup for team logos from teams_info
        team_logos = {
            str(t.get('team_id')): t.get('team_logo')
            for t in teams_info
        }
        
        if not teams_stats:
            return {
                "status": False,
                "data": {"error": "No teams_stats provided"},
                "message": "Missing teams_stats parameter"
            }
        
        # Extract metrics for all teams
        teams_data = []
        for doc in teams_stats:
            try:
                team_stats = doc.get('value', {}).get('data', {})
                if not team_stats:
                    continue
                
                team_info = team_stats.get('team', {})
                fixtures = team_stats.get('fixtures', {})
                goals = team_stats.get('goals', {})
                cards = team_stats.get('cards', {})
                
                # Extract basic metrics
                games = fixtures.get('played', {}).get('total', 0)
                if games == 0:
                    continue
                
                wins = fixtures.get('wins', {}).get('total', 0)
                draws = fixtures.get('draws', {}).get('total', 0)
                goals_for = goals.get('for', {}).get('total', {}).get('total', 0)
                goals_against = goals.get('against', {}).get('total', {}).get('total', 0)
                clean_sheets = team_stats.get('clean_sheet', {}).get('total', 0)
                failed_to_score = team_stats.get('failed_to_score', {}).get('total', 0)
                
                # Count cards (sum all non-null totals)
                yellow_cards = sum(
                    period.get('total', 0) or 0 
                    for period in cards.get('yellow', {}).values() 
                    if isinstance(period, dict)
                )
                red_cards = sum(
                    period.get('total', 0) or 0 
                    for period in cards.get('red', {}).values() 
                    if isinstance(period, dict)
                )
                
                teams_data.append({
                    'team_id': str(team_info.get('id', '')),
                    'team_name': team_info.get('name', 'Unknown'),
                    'games': games,
                    'wins': wins,
                    'draws': draws,
                    'goals_for': goals_for,
                    'goals_against': goals_against,
                    'clean_sheets': clean_sheets,
                    'failed_to_score': failed_to_score,
                    'yellow_cards': yellow_cards,
                    'red_cards': red_cards
                })
            except Exception as e:
                print(f"Error processing team: {e}")
                continue
        
        if not teams_data:
            return {
                "status": False,
                "data": {"error": "No valid teams data found"},
                "message": "Failed to extract team metrics"
            }
        
        # Calculate per-game metrics for normalization
        for team in teams_data:
            team['goals_per_game'] = team['goals_for'] / team['games']
            team['concede_rate'] = team['goals_against'] / team['games']
            team['cards_per_game'] = (team['yellow_cards'] + team['red_cards'] * 2) / team['games']
        
        # Min-Max normalization helper
        def normalize_minmax(values):
            if not values:
                return [0.5] * len(values)
            min_val = min(values)
            max_val = max(values)
            if max_val == min_val:
                return [0.5] * len(values)
            return [(v - min_val) / (max_val - min_val) for v in values]
        
        # Normalize metrics across all teams
        goals_per_game_norm = normalize_minmax([t['goals_per_game'] for t in teams_data])
        concede_rate_norm = normalize_minmax([t['concede_rate'] for t in teams_data])
        cards_per_game_norm = normalize_minmax([t['cards_per_game'] for t in teams_data])
        
        # Calculate power rankings
        rankings = []
        for i, team in enumerate(teams_data):
            # 1. Outcome Score (40%)
            win_rate = team['wins'] / team['games']
            points_per_game = (team['wins'] * 3 + team['draws']) / team['games']
            outcome_score = 0.6 * win_rate + 0.4 * (points_per_game / 3)
            
            # 2. Attack Score (25%)
            scoring_rate = 1 - (team['failed_to_score'] / team['games'])
            attack_score = 0.7 * goals_per_game_norm[i] + 0.3 * scoring_rate
            
            # 3. Defense Score (25%)
            clean_sheet_rate = team['clean_sheets'] / team['games']
            defense_score = 0.6 * (1 - concede_rate_norm[i]) + 0.4 * clean_sheet_rate
            
            # 4. Discipline Score (10%)
            discipline_score = 1 - cards_per_game_norm[i]
            
            # Final Power Score
            power_score = (
                0.40 * outcome_score +
                0.25 * attack_score +
                0.25 * defense_score +
                0.10 * discipline_score
            )
            
            rankings.append({
                'team_id': team['team_id'],
                'team_name': team['team_name'],
                'team_logo': team_logos.get(team['team_id']),
                'power_score': round(power_score, 4),
                'breakdown': {
                    'outcome_score': round(outcome_score, 4),
                    'attack_score': round(attack_score, 4),
                    'defense_score': round(defense_score, 4),
                    'discipline_score': round(discipline_score, 4)
                },
                'metrics': {
                    'games': team['games'],
                    'wins': team['wins'],
                    'draws': team['draws'],
                    'losses': team['games'] - team['wins'] - team['draws'],
                    'win_rate': round(win_rate, 4),
                    'points_per_game': round(points_per_game, 2),
                    'goals_per_game': round(team['goals_per_game'], 2),
                    'concede_rate': round(team['concede_rate'], 2),
                    'clean_sheets': team['clean_sheets'],
                    'clean_sheet_rate': round(clean_sheet_rate, 4),
                    'failed_to_score': team['failed_to_score'],
                    'scoring_rate': round(scoring_rate, 4),
                    'cards_per_game': round(team['cards_per_game'], 2),
                    'yellow_cards': team['yellow_cards'],
                    'red_cards': team['red_cards']
                }
            })
        
        # Sort by power_score descending and assign ranks
        rankings.sort(key=lambda x: x['power_score'], reverse=True)
        for i, ranking in enumerate(rankings):
            ranking['rank'] = i + 1
        
        # Calculate league stats
        avg_power_score = sum(r['power_score'] for r in rankings) / len(rankings)
        
        return {
            "status": True,
            "data": {
                "rankings": rankings,
                "league_stats": {
                    "total_teams": len(rankings),
                    "avg_power_score": round(avg_power_score, 4),
                    "league_id": league_id,
                    "season": season
                }
            },
            "message": f"Successfully calculated power rankings for {len(rankings)} teams"
        }
        
    except Exception as e:
        import traceback
        return {
            "status": False,
            "data": {"error": str(e), "traceback": traceback.format_exc()},
            "message": f"Error calculating power rankings: {str(e)}"
        }

