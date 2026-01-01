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


def calculate_progressive_rankings(request_data):
    """
    Calculate power rankings based on the last N matches of each team.
    
    Uses 3 pillars (discipline excluded due to lack of card data in fixtures):
    - Outcome (45%): Win rate and points per game
    - Attack (30%): Goals scored and scoring consistency
    - Defense (25%): Goals conceded and clean sheets
    
    Input:
        fixtures: List of fixture results from API Football
        teams_info: Team information including logos
        last_matches: Number of matches considered (for metadata)
        league_id: League identifier
        season: Season year
    
    Returns rankings sorted by power_score in descending order.
    """
    try:
        # Parse request_data
        if isinstance(request_data, str):
            import json
            request_data = json.loads(request_data)
        
        params = request_data.get('params', request_data)
        fixtures = params.get('fixtures', [])
        teams_info = params.get('teams_info', [])
        last_matches = params.get('last_matches', 10)
        league_id = params.get('league_id', 'unknown')
        season = params.get('season', 'unknown')
        
        # Create lookup for team logos
        team_logos = {
            str(t.get('team_id')): t.get('team_logo')
            for t in teams_info
        }
        
        # Create lookup for team names
        team_names = {
            str(t.get('team_id')): t.get('team_name')
            for t in teams_info
        }
        
        if not fixtures:
            return {
                "status": False,
                "data": {"error": "No fixtures provided"},
                "message": "Missing fixtures parameter"
            }
        
        # Initialize team stats
        team_stats = {}
        
        def init_team(team_id):
            if team_id not in team_stats:
                team_stats[team_id] = {
                    'games': 0,
                    'wins': 0,
                    'draws': 0,
                    'losses': 0,
                    'goals_for': 0,
                    'goals_against': 0,
                    'clean_sheets': 0,
                    'failed_to_score': 0
                }
        
        # Process fixtures and aggregate stats by team
        for fixture in fixtures:
            try:
                # Handle nested fixture structure from API Football
                teams = fixture.get('teams', {})
                goals = fixture.get('goals', {})
                
                home_team = teams.get('home', {})
                away_team = teams.get('away', {})
                
                home_id = str(home_team.get('id', ''))
                away_id = str(away_team.get('id', ''))
                
                home_goals = goals.get('home')
                away_goals = goals.get('away')
                
                # Skip if missing data
                if not home_id or not away_id or home_goals is None or away_goals is None:
                    continue
                
                # Initialize teams if needed
                init_team(home_id)
                init_team(away_id)
                
                # Update home team stats
                team_stats[home_id]['games'] += 1
                team_stats[home_id]['goals_for'] += home_goals
                team_stats[home_id]['goals_against'] += away_goals
                
                if away_goals == 0:
                    team_stats[home_id]['clean_sheets'] += 1
                if home_goals == 0:
                    team_stats[home_id]['failed_to_score'] += 1
                
                if home_goals > away_goals:
                    team_stats[home_id]['wins'] += 1
                    team_stats[away_id]['losses'] += 1
                elif home_goals < away_goals:
                    team_stats[home_id]['losses'] += 1
                    team_stats[away_id]['wins'] += 1
                else:
                    team_stats[home_id]['draws'] += 1
                    team_stats[away_id]['draws'] += 1
                
                # Update away team stats
                team_stats[away_id]['games'] += 1
                team_stats[away_id]['goals_for'] += away_goals
                team_stats[away_id]['goals_against'] += home_goals
                
                if home_goals == 0:
                    team_stats[away_id]['clean_sheets'] += 1
                if away_goals == 0:
                    team_stats[away_id]['failed_to_score'] += 1
                    
            except Exception as e:
                print(f"Error processing fixture: {e}")
                continue
        
        if not team_stats:
            return {
                "status": False,
                "data": {"error": "No valid fixtures processed"},
                "message": "Failed to extract team metrics from fixtures"
            }
        
        # Convert to list and calculate per-game metrics
        teams_data = []
        for team_id, stats in team_stats.items():
            if stats['games'] == 0:
                continue
            
            teams_data.append({
                'team_id': team_id,
                'team_name': team_names.get(team_id, f"Team {team_id}"),
                **stats,
                'goals_per_game': stats['goals_for'] / stats['games'],
                'concede_rate': stats['goals_against'] / stats['games']
            })
        
        if not teams_data:
            return {
                "status": False,
                "data": {"error": "No teams with valid games"},
                "message": "No teams found with completed matches"
            }
        
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
        
        # Calculate power rankings (3 pillars - no discipline)
        rankings = []
        for i, team in enumerate(teams_data):
            # 1. Outcome Score (45% - increased from 40% since no discipline)
            win_rate = team['wins'] / team['games']
            points_per_game = (team['wins'] * 3 + team['draws']) / team['games']
            outcome_score = 0.6 * win_rate + 0.4 * (points_per_game / 3)
            
            # 2. Attack Score (30% - increased from 25%)
            scoring_rate = 1 - (team['failed_to_score'] / team['games'])
            attack_score = 0.7 * goals_per_game_norm[i] + 0.3 * scoring_rate
            
            # 3. Defense Score (25% - unchanged)
            clean_sheet_rate = team['clean_sheets'] / team['games']
            defense_score = 0.6 * (1 - concede_rate_norm[i]) + 0.4 * clean_sheet_rate
            
            # Final Power Score (without discipline: 45% + 30% + 25% = 100%)
            power_score = (
                0.45 * outcome_score +
                0.30 * attack_score +
                0.25 * defense_score
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
                    'discipline_score': None  # Not available in progressive mode
                },
                'metrics': {
                    'games': team['games'],
                    'wins': team['wins'],
                    'draws': team['draws'],
                    'losses': team['losses'],
                    'goals_for': team['goals_for'],
                    'goals_against': team['goals_against'],
                    'goal_difference': team['goals_for'] - team['goals_against'],
                    'win_rate': round(win_rate, 4),
                    'points_per_game': round(points_per_game, 2),
                    'goals_per_game': round(team['goals_per_game'], 2),
                    'concede_rate': round(team['concede_rate'], 2),
                    'clean_sheets': team['clean_sheets'],
                    'clean_sheet_rate': round(clean_sheet_rate, 4),
                    'failed_to_score': team['failed_to_score'],
                    'scoring_rate': round(scoring_rate, 4)
                }
            })
        
        # Sort by power_score descending and assign ranks
        rankings.sort(key=lambda x: x['power_score'], reverse=True)
        for i, ranking in enumerate(rankings):
            ranking['rank'] = i + 1
        
        # Calculate league stats
        avg_power_score = sum(r['power_score'] for r in rankings) / len(rankings) if rankings else 0
        
        from datetime import datetime
        
        return {
            "status": True,
            "data": {
                "rankings": rankings,
                "league_stats": {
                    "total_teams": len(rankings),
                    "avg_power_score": round(avg_power_score, 4),
                    "league_id": league_id,
                    "season": season,
                    "last_matches": last_matches,
                    "calculation_type": "progressive",
                    "calculated_at": datetime.utcnow().isoformat()
                }
            },
            "message": f"Successfully calculated progressive rankings for {len(rankings)} teams (last {last_matches} matches)"
        }
        
    except Exception as e:
        import traceback
        return {
            "status": False,
            "data": {"error": str(e), "traceback": traceback.format_exc()},
            "message": f"Error calculating progressive rankings: {str(e)}"
        }


def calculate_team_metrics(request_data):
    """
    Calculate raw metrics for a SINGLE team based on their fixtures.
    
    This function processes fixtures for ONE team only and returns raw metrics
    WITHOUT normalization. Normalization is done later in aggregate_and_normalize.
    
    Input:
        fixtures: List of fixture results for this team from API Football
        team_id: The team's ID
        team_name: The team's name
        team_logo: The team's logo URL
        last_matches: Number of matches considered (for metadata)
    
    Returns raw metrics (games, wins, goals_per_game, etc.) without power_score.
    """
    try:
        # Parse request_data
        if isinstance(request_data, str):
            import json
            request_data = json.loads(request_data)
        
        params = request_data.get('params', request_data)
        fixtures = params.get('fixtures', [])
        team_id = str(params.get('team_id', ''))
        team_name = params.get('team_name', f'Team {team_id}')
        team_logo = params.get('team_logo')
        last_matches = params.get('last_matches', 10)
        
        if not fixtures:
            return {
                "status": False,
                "data": {"error": "No fixtures provided"},
                "message": "Missing fixtures parameter"
            }
        
        if not team_id:
            return {
                "status": False,
                "data": {"error": "No team_id provided"},
                "message": "Missing team_id parameter"
            }
        
        # Initialize stats for this team
        stats = {
            'games': 0,
            'wins': 0,
            'draws': 0,
            'losses': 0,
            'goals_for': 0,
            'goals_against': 0,
            'clean_sheets': 0,
            'failed_to_score': 0
        }
        
        # Process fixtures - only count stats for OUR team
        for fixture in fixtures:
            try:
                teams = fixture.get('teams', {})
                goals = fixture.get('goals', {})
                
                home_team = teams.get('home', {})
                away_team = teams.get('away', {})
                
                home_id = str(home_team.get('id', ''))
                away_id = str(away_team.get('id', ''))
                
                home_goals = goals.get('home')
                away_goals = goals.get('away')
                
                # Skip if missing data
                if home_goals is None or away_goals is None:
                    continue
                
                # Determine if our team is home or away
                is_home = (home_id == team_id)
                is_away = (away_id == team_id)
                
                if not is_home and not is_away:
                    # This fixture doesn't involve our team, skip
                    continue
                
                # Get our team's goals and opponent's goals
                if is_home:
                    our_goals = home_goals
                    opp_goals = away_goals
                else:
                    our_goals = away_goals
                    opp_goals = home_goals
                
                # Update stats
                stats['games'] += 1
                stats['goals_for'] += our_goals
                stats['goals_against'] += opp_goals
                
                if opp_goals == 0:
                    stats['clean_sheets'] += 1
                if our_goals == 0:
                    stats['failed_to_score'] += 1
                
                if our_goals > opp_goals:
                    stats['wins'] += 1
                elif our_goals < opp_goals:
                    stats['losses'] += 1
                else:
                    stats['draws'] += 1
                    
            except Exception as e:
                print(f"Error processing fixture: {e}")
                continue
        
        if stats['games'] == 0:
            return {
                "status": False,
                "data": {"error": f"No valid fixtures for team {team_id}"},
                "message": f"No completed matches found for team {team_name}"
            }
        
        # Calculate per-game metrics (raw, not normalized)
        goals_per_game = stats['goals_for'] / stats['games']
        concede_rate = stats['goals_against'] / stats['games']
        win_rate = stats['wins'] / stats['games']
        points_per_game = (stats['wins'] * 3 + stats['draws']) / stats['games']
        clean_sheet_rate = stats['clean_sheets'] / stats['games']
        scoring_rate = 1 - (stats['failed_to_score'] / stats['games'])
        
        from datetime import datetime
        
        return {
            "status": True,
            "data": {
                "team_metrics": {
                    "team_id": team_id,
                    "team_name": team_name,
                    "team_logo": team_logo,
                    "games": stats['games'],
                    "wins": stats['wins'],
                    "draws": stats['draws'],
                    "losses": stats['losses'],
                    "goals_for": stats['goals_for'],
                    "goals_against": stats['goals_against'],
                    "goal_difference": stats['goals_for'] - stats['goals_against'],
                    "clean_sheets": stats['clean_sheets'],
                    "failed_to_score": stats['failed_to_score'],
                    # Per-game metrics (raw, not normalized)
                    "goals_per_game": round(goals_per_game, 4),
                    "concede_rate": round(concede_rate, 4),
                    "win_rate": round(win_rate, 4),
                    "points_per_game": round(points_per_game, 4),
                    "clean_sheet_rate": round(clean_sheet_rate, 4),
                    "scoring_rate": round(scoring_rate, 4),
                    # Metadata
                    "last_matches": last_matches,
                    "calculated_at": datetime.utcnow().isoformat()
                }
            },
            "message": f"Successfully calculated metrics for {team_name} ({stats['games']} games)"
        }
        
    except Exception as e:
        import traceback
        return {
            "status": False,
            "data": {"error": str(e), "traceback": traceback.format_exc()},
            "message": f"Error calculating team metrics: {str(e)}"
        }


def aggregate_and_normalize(request_data):
    """
    Aggregate team metrics and apply Min-Max normalization to generate power rankings.
    
    Takes raw metrics from multiple teams (calculated by calculate_team_metrics)
    and applies normalization across the group to generate comparable power scores.
    
    Input:
        team_metrics: List of team metric documents (from calculate_team_metrics)
        league_id: League identifier
        season: Season year (optional - can be null)
        date: Reference date in "YYYY-MM-DD" format (optional)
        last_matches: Number of matches considered (for metadata)
    
    Returns normalized rankings with power_score for each team.
    """
    try:
        # Parse request_data
        if isinstance(request_data, str):
            import json
            request_data = json.loads(request_data)
        
        params = request_data.get('params', request_data)
        team_metrics_docs = params.get('team_metrics', [])
        league_id = params.get('league_id', 'unknown')
        season = params.get('season')  # Can be null
        date = params.get('date')  # Optional date filter
        last_matches = params.get('last_matches', 10)
        
        if not team_metrics_docs:
            return {
                "status": False,
                "data": {"error": "No team_metrics provided"},
                "message": "Missing team_metrics parameter"
            }
        
        # Extract metrics from documents with deduplication by team_id
        # Uses dict to keep only the most recent entry per team
        teams_by_id = {}
        for doc in team_metrics_docs:
            try:
                # Handle both direct metrics and document wrapper formats
                if isinstance(doc, dict):
                    # Check if it's a document wrapper (has 'value' key)
                    if 'value' in doc:
                        metrics = doc.get('value', {}).get('team_metrics', {})
                        doc_date = doc.get('created') or doc.get('date') or ''
                    elif 'team_metrics' in doc:
                        metrics = doc.get('team_metrics', {})
                        doc_date = doc.get('created') or doc.get('date') or ''
                    else:
                        metrics = doc
                        doc_date = doc.get('calculated_at', '')
                    
                    if metrics and metrics.get('games', 0) > 0:
                        team_id = metrics.get('team_id', '')
                        if team_id:
                            # Keep the entry with the most recent date, or first if dates equal
                            existing = teams_by_id.get(team_id)
                            if not existing or doc_date > existing.get('_doc_date', ''):
                                metrics['_doc_date'] = doc_date
                                teams_by_id[team_id] = metrics
            except Exception as e:
                print(f"Error extracting metrics from doc: {e}")
                continue
        
        # Convert to list and remove temporary _doc_date field
        teams_data = []
        for metrics in teams_by_id.values():
            metrics.pop('_doc_date', None)
            teams_data.append(metrics)
        
        if not teams_data:
            return {
                "status": False,
                "data": {"error": "No valid team metrics found"},
                "message": "Failed to extract team metrics from documents"
            }
        
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
        goals_per_game_norm = normalize_minmax([t.get('goals_per_game', 0) for t in teams_data])
        concede_rate_norm = normalize_minmax([t.get('concede_rate', 0) for t in teams_data])
        
        # Calculate power rankings (3 pillars - no discipline in progressive mode)
        rankings = []
        for i, team in enumerate(teams_data):
            games = team.get('games', 1)
            
            # 1. Outcome Score (45%)
            win_rate = team.get('win_rate', 0)
            points_per_game = team.get('points_per_game', 0)
            outcome_score = 0.6 * win_rate + 0.4 * (points_per_game / 3)
            
            # 2. Attack Score (30%)
            scoring_rate = team.get('scoring_rate', 0)
            attack_score = 0.7 * goals_per_game_norm[i] + 0.3 * scoring_rate
            
            # 3. Defense Score (25%)
            clean_sheet_rate = team.get('clean_sheet_rate', 0)
            defense_score = 0.6 * (1 - concede_rate_norm[i]) + 0.4 * clean_sheet_rate
            
            # Final Power Score (45% + 30% + 25% = 100%)
            power_score = (
                0.45 * outcome_score +
                0.30 * attack_score +
                0.25 * defense_score
            )
            
            rankings.append({
                'team_id': team.get('team_id', ''),
                'team_name': team.get('team_name', 'Unknown'),
                'team_logo': team.get('team_logo'),
                'power_score': round(power_score, 4),
                'breakdown': {
                    'outcome_score': round(outcome_score, 4),
                    'attack_score': round(attack_score, 4),
                    'defense_score': round(defense_score, 4),
                    'discipline_score': None  # Not available in progressive mode
                },
                'metrics': {
                    'games': team.get('games', 0),
                    'wins': team.get('wins', 0),
                    'draws': team.get('draws', 0),
                    'losses': team.get('losses', 0),
                    'goals_for': team.get('goals_for', 0),
                    'goals_against': team.get('goals_against', 0),
                    'goal_difference': team.get('goal_difference', 0),
                    'win_rate': round(win_rate, 4),
                    'points_per_game': round(points_per_game, 2),
                    'goals_per_game': round(team.get('goals_per_game', 0), 2),
                    'concede_rate': round(team.get('concede_rate', 0), 2),
                    'clean_sheets': team.get('clean_sheets', 0),
                    'clean_sheet_rate': round(clean_sheet_rate, 4),
                    'failed_to_score': team.get('failed_to_score', 0),
                    'scoring_rate': round(scoring_rate, 4)
                }
            })
        
        # Sort by power_score descending and assign ranks
        rankings.sort(key=lambda x: x['power_score'], reverse=True)
        for i, ranking in enumerate(rankings):
            ranking['rank'] = i + 1
        
        # Calculate league stats
        avg_power_score = sum(r['power_score'] for r in rankings) / len(rankings) if rankings else 0
        
        from datetime import datetime
        
        return {
            "status": True,
            "data": {
                "rankings": rankings,
                "league_stats": {
                    "total_teams": len(rankings),
                    "avg_power_score": round(avg_power_score, 4),
                    "league_id": league_id,
                    "season": season,
                    "date": date,
                    "last_matches": last_matches,
                    "calculation_type": "progressive",
                    "calculated_at": datetime.utcnow().isoformat()
                }
            },
            "message": f"Successfully calculated power rankings for {len(rankings)} teams"
        }
        
    except Exception as e:
        import traceback
        return {
            "status": False,
            "data": {"error": str(e), "traceback": traceback.format_exc()},
            "message": f"Error aggregating and normalizing rankings: {str(e)}"
        }


def filter_fixtures_for_sync(request_data):
    """
    Filter fixtures from API that need to be synced to the database.
    
    Compares API fixtures with existing fixture IDs to determine which
    fixtures are new or have been updated (status changed to FT).
    
    Input:
        api_fixtures: List of fixtures from API Football
        existing_fixture_ids: List of fixture IDs already in the database
    
    Returns:
        fixtures_to_sync: List of fixtures that need to be saved/updated
    """
    try:
        # Parse request_data
        if isinstance(request_data, str):
            import json
            request_data = json.loads(request_data)
        
        params = request_data.get('params', request_data)
        api_fixtures = params.get('api_fixtures', [])
        existing_fixture_ids = params.get('existing_fixture_ids', [])
        
        # Convert existing IDs to set for O(1) lookup
        existing_set = set(str(fid) for fid in existing_fixture_ids)
        
        fixtures_to_sync = []
        
        for fixture in api_fixtures:
            try:
                fixture_data = fixture.get('fixture', {})
                fixture_id = str(fixture_data.get('id', ''))
                status = fixture_data.get('status', {}).get('short', '')
                
                # Skip if no fixture ID
                if not fixture_id:
                    continue
                
                # Sync if:
                # 1. New fixture (not in existing)
                # 2. OR completed fixture (FT status) - always update to get final scores
                is_new = fixture_id not in existing_set
                is_finished = status == 'FT'
                
                if is_new or is_finished:
                    fixtures_to_sync.append(fixture)
                    
            except Exception as e:
                print(f"Error processing fixture for sync: {e}")
                continue
        
        return {
            "status": True,
            "data": {
                "fixtures_to_sync": fixtures_to_sync,
                "total_api": len(api_fixtures),
                "existing_count": len(existing_fixture_ids),
                "to_sync_count": len(fixtures_to_sync)
            },
            "message": f"Found {len(fixtures_to_sync)} fixtures to sync out of {len(api_fixtures)} total"
        }
        
    except Exception as e:
        import traceback
        return {
            "status": False,
            "data": {"error": str(e), "traceback": traceback.format_exc()},
            "message": f"Error filtering fixtures for sync: {str(e)}"
        }


def filter_fixtures_by_date(request_data):
    """
    Filter local fixture documents by team, date, and limit.
    
    Processes fixture documents from the database, filters by team ID,
    optionally filters by date, and returns the most recent N fixtures.
    
    Input:
        fixture_docs: List of fixture documents from database
        team_id: Team ID to filter fixtures for
        date: Optional date limit (YYYY-MM-DD format) - fixtures up to this date
        last_matches: Number of most recent fixtures to return (default: 10)
    
    Returns:
        fixtures: Filtered and sorted fixtures in API Football format
    """
    try:
        # Parse request_data
        if isinstance(request_data, str):
            import json
            request_data = json.loads(request_data)
        
        params = request_data.get('params', request_data)
        fixture_docs = params.get('fixture_docs', [])
        team_id = str(params.get('team_id', ''))
        date_limit = params.get('date')  # Optional: "YYYY-MM-DD"
        last_matches = params.get('last_matches', 10)
        
        if not fixture_docs:
            return {
                "status": True,
                "data": {
                    "fixtures": [],
                    "fixtures_count": 0
                },
                "message": "No fixture documents provided"
            }
        
        if not team_id:
            return {
                "status": False,
                "data": {"error": "No team_id provided"},
                "message": "Missing team_id parameter"
            }
        
        # Filter fixtures for this team
        team_fixtures = []
        
        for doc in fixture_docs:
            try:
                # Handle document wrapper format
                if 'value' in doc:
                    fixture_data = doc.get('value', {})
                else:
                    fixture_data = doc
                
                # Get metadata for quick filtering
                metadata = doc.get('metadata', {}) or fixture_data.get('metadata', {})
                
                # Check if this fixture involves our team
                home_id = str(metadata.get('team_home_id', ''))
                away_id = str(metadata.get('team_away_id', ''))
                
                if team_id not in [home_id, away_id]:
                    continue
                
                # Check status - only finished matches
                status = metadata.get('status', '')
                if status != 'FT':
                    continue
                
                # Check date if limit provided
                fixture_date = metadata.get('date', '')
                if date_limit and fixture_date:
                    if fixture_date > date_limit:
                        continue
                
                # Build fixture in API Football format
                fixture = {
                    'fixture': fixture_data.get('fixture', {}),
                    'league': fixture_data.get('league', {}),
                    'teams': fixture_data.get('teams', {}),
                    'goals': fixture_data.get('goals', {}),
                    'score': fixture_data.get('score', {})
                }
                
                # Add date for sorting
                fixture['_date'] = fixture_date or fixture.get('fixture', {}).get('date', '')
                
                team_fixtures.append(fixture)
                
            except Exception as e:
                print(f"Error processing fixture document: {e}")
                continue
        
        # Sort by date descending (most recent first)
        team_fixtures.sort(key=lambda x: x.get('_date', ''), reverse=True)
        
        # Limit to last_matches
        limited_fixtures = team_fixtures[:last_matches]
        
        # Remove temporary _date field
        for f in limited_fixtures:
            f.pop('_date', None)
        
        return {
            "status": True,
            "data": {
                "fixtures": limited_fixtures,
                "fixtures_count": len(limited_fixtures),
                "total_available": len(team_fixtures)
            },
            "message": f"Found {len(limited_fixtures)} fixtures for team {team_id}" + (f" up to {date_limit}" if date_limit else "")
        }
        
    except Exception as e:
        import traceback
        return {
            "status": False,
            "data": {"error": str(e), "traceback": traceback.format_exc()},
            "message": f"Error filtering fixtures by date: {str(e)}"
        }
