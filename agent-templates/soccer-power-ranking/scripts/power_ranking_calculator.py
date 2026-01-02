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
    
    Now accepts 3 SEPARATE fixture lists for symmetric metrics:
    - fixtures_total: Last N matches (home OR away) - for overall ranking
    - fixtures_home: Last N HOME matches only - for home ranking  
    - fixtures_away: Last N AWAY matches only - for away ranking
    
    This ensures each context has the same sample size (e.g., 10 games each).
    
    Input:
        fixtures_total: List of fixture results (home or away) for total ranking
        fixtures_home: List of HOME fixture results for home ranking
        fixtures_away: List of AWAY fixture results for away ranking
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
        
        # Accept 3 separate fixture lists (new approach)
        # Fall back to old 'fixtures' param for backward compatibility
        fixtures_total = params.get('fixtures_total', params.get('fixtures', []))
        fixtures_home = params.get('fixtures_home', [])
        fixtures_away = params.get('fixtures_away', [])
        
        team_id = str(params.get('team_id', ''))
        team_name = params.get('team_name', f'Team {team_id}')
        team_logo = params.get('team_logo')
        last_matches = params.get('last_matches', 10)
        
        if not fixtures_total:
            return {
                "status": False,
                "data": {"error": "No fixtures provided"},
                "message": "Missing fixtures_total parameter"
            }
        
        if not team_id:
            return {
                "status": False,
                "data": {"error": "No team_id provided"},
                "message": "Missing team_id parameter"
            }
        
        # Helper to initialize stats
        def init_stats():
            return {
                'games': 0,
                'wins': 0,
                'draws': 0,
                'losses': 0,
                'goals_for': 0,
                'goals_against': 0,
                'clean_sheets': 0,
                'failed_to_score': 0
            }
        
        # Helper to update stats from a single fixture
        def update_stats(stats, our_goals, opp_goals):
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
        
        # Process a list of fixtures and return stats
        def process_fixtures(fixtures, context_hint=None):
            stats = init_stats()
            # Deduplicate by fixture id to avoid counting the same match multiple times
            # (e.g., when the database contains duplicated league-fixture documents).
            seen_fixture_ids = set()
            for fixture in fixtures:
                try:
                    fixture_meta = fixture.get('fixture', {}) if isinstance(fixture, dict) else {}
                    fixture_id_raw = fixture_meta.get('id')
                    fixture_id = str(fixture_id_raw) if fixture_id_raw is not None else ''
                    if fixture_id:
                        if fixture_id in seen_fixture_ids:
                            continue
                        seen_fixture_ids.add(fixture_id)

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
                    
                    update_stats(stats, our_goals, opp_goals)
                        
                except Exception as e:
                    print(f"Error processing fixture: {e}")
                    continue
            return stats
        
        # Process each fixture list independently
        stats_total = process_fixtures(fixtures_total, 'total')
        stats_home = process_fixtures(fixtures_home, 'home') if fixtures_home else init_stats()
        stats_away = process_fixtures(fixtures_away, 'away') if fixtures_away else init_stats()
        
        if stats_total['games'] == 0:
            return {
                "status": False,
                "data": {"error": f"No valid fixtures for team {team_id}"},
                "message": f"No completed matches found for team {team_name}"
            }
        
        # Helper to calculate per-game metrics from stats
        def calc_metrics(stats, context):
            if stats['games'] == 0:
                return None
            
            goals_per_game = stats['goals_for'] / stats['games']
            concede_rate = stats['goals_against'] / stats['games']
            win_rate = stats['wins'] / stats['games']
            points_per_game = (stats['wins'] * 3 + stats['draws']) / stats['games']
            clean_sheet_rate = stats['clean_sheets'] / stats['games']
            scoring_rate = 1 - (stats['failed_to_score'] / stats['games'])
            
            return {
                "team_id": team_id,
                "team_name": team_name,
                "team_logo": team_logo,
                "context": context,
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
                "last_matches": last_matches
            }
        
        from datetime import datetime
        
        metrics_total = calc_metrics(stats_total, 'total')
        metrics_home = calc_metrics(stats_home, 'home')
        metrics_away = calc_metrics(stats_away, 'away')
        
        return {
            "status": True,
            "data": {
                "team_metrics": metrics_total,  # For backward compatibility
                "metrics_total": metrics_total,
                "metrics_home": metrics_home,
                "metrics_away": metrics_away,
                "calculated_at": datetime.utcnow().isoformat()
            },
            "message": f"Successfully calculated metrics for {team_name} (total: {stats_total['games']}, home: {stats_home['games']}, away: {stats_away['games']} games)"
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
    
    Now generates 3 separate rankings:
    - rankings_total: Based on all games
    - rankings_home: Based on home games only
    - rankings_away: Based on away games only
    
    Input:
        team_metrics: List of team metric documents (from calculate_team_metrics)
        league_id: League identifier
        season: Season year (optional - can be null)
        date: Reference date in "YYYY-MM-DD" format (optional)
        last_matches: Number of matches considered (for metadata)
    
    Returns normalized rankings with power_score for each team in 3 contexts.
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
        # Now we extract 3 sets of metrics: total, home, away
        teams_total = {}
        teams_home = {}
        teams_away = {}
        
        for doc in team_metrics_docs:
            try:
                # Handle both direct metrics and document wrapper formats
                if isinstance(doc, dict):
                    doc_date = ''
                    
                    # Check if it's a document wrapper (has 'value' key)
                    if 'value' in doc:
                        value = doc.get('value', {})
                        metrics_total = value.get('metrics_total') or value.get('team_metrics')
                        metrics_home = value.get('metrics_home')
                        metrics_away = value.get('metrics_away')
                        doc_date = doc.get('created') or value.get('calculated_at', '')
                    elif 'metrics_total' in doc or 'team_metrics' in doc:
                        metrics_total = doc.get('metrics_total') or doc.get('team_metrics')
                        metrics_home = doc.get('metrics_home')
                        metrics_away = doc.get('metrics_away')
                        doc_date = doc.get('calculated_at', '')
                    else:
                        # Backward compatibility - single metrics object
                        metrics_total = doc
                        metrics_home = None
                        metrics_away = None
                        doc_date = doc.get('calculated_at', '')
                    
                    # Extract total metrics
                    if metrics_total and metrics_total.get('games', 0) > 0:
                        team_id = metrics_total.get('team_id', '')
                        if team_id:
                            existing = teams_total.get(team_id)
                            if not existing or doc_date > existing.get('_doc_date', ''):
                                metrics_total['_doc_date'] = doc_date
                                teams_total[team_id] = metrics_total
                    
                    # Extract home metrics
                    if metrics_home and metrics_home.get('games', 0) > 0:
                        team_id = metrics_home.get('team_id', '')
                        if team_id:
                            existing = teams_home.get(team_id)
                            if not existing or doc_date > existing.get('_doc_date', ''):
                                metrics_home['_doc_date'] = doc_date
                                teams_home[team_id] = metrics_home
                    
                    # Extract away metrics
                    if metrics_away and metrics_away.get('games', 0) > 0:
                        team_id = metrics_away.get('team_id', '')
                        if team_id:
                            existing = teams_away.get(team_id)
                            if not existing or doc_date > existing.get('_doc_date', ''):
                                metrics_away['_doc_date'] = doc_date
                                teams_away[team_id] = metrics_away
                                
            except Exception as e:
                print(f"Error extracting metrics from doc: {e}")
                continue
        
        # Convert to lists and remove temporary _doc_date field
        def to_list(teams_dict):
            result = []
            for metrics in teams_dict.values():
                metrics.pop('_doc_date', None)
                result.append(metrics)
            return result
        
        teams_data_total = to_list(teams_total)
        teams_data_home = to_list(teams_home)
        teams_data_away = to_list(teams_away)
        
        if not teams_data_total:
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
        
        # Helper to calculate rankings for a given context
        def calculate_rankings(teams_data, context):
            if not teams_data:
                return []
            
            # Normalize metrics across all teams in this context
            goals_per_game_norm = normalize_minmax([t.get('goals_per_game', 0) for t in teams_data])
            concede_rate_norm = normalize_minmax([t.get('concede_rate', 0) for t in teams_data])
            
            rankings = []
            for i, team in enumerate(teams_data):
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
                    'context': context,
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
            
            return rankings
        
        # Calculate rankings for each context
        rankings_total = calculate_rankings(teams_data_total, 'total')
        rankings_home = calculate_rankings(teams_data_home, 'home')
        rankings_away = calculate_rankings(teams_data_away, 'away')
        
        # Calculate league stats (using total for summary)
        avg_power_score = sum(r['power_score'] for r in rankings_total) / len(rankings_total) if rankings_total else 0
        
        from datetime import datetime
        
        return {
            "status": True,
            "data": {
                # For backward compatibility, 'rankings' is the total rankings
                "rankings": rankings_total,
                # New fields for context-aware rankings
                "rankings_total": rankings_total,
                "rankings_home": rankings_home,
                "rankings_away": rankings_away,
                "league_stats": {
                    "total_teams": len(rankings_total),
                    "home_teams": len(rankings_home),
                    "away_teams": len(rankings_away),
                    "avg_power_score": round(avg_power_score, 4),
                    "league_id": league_id,
                    "season": season,
                    "date": date,
                    "last_matches": last_matches,
                    "calculation_type": "progressive",
                    "calculated_at": datetime.utcnow().isoformat()
                }
            },
            "message": f"Successfully calculated power rankings for {len(rankings_total)} teams (total), {len(rankings_home)} (home), {len(rankings_away)} (away)"
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


def filter_sport_events_by_team(request_data):
    """
    Filter sport:Event documents by team ID and extract normalized fixture data.
    
    Takes all finished fixtures from a league and filters by team,
    separating into total/home/away contexts with proper date filtering and limiting.
    
    sport:Event schema:
    - Team URN: value.sport:competitors[].@id = "urn:apifootball:team:{team_id}"
    - Qualifier: value.sport:competitors[].sport:qualifier = "home" | "away"
    - Score: value.sport:score.sport:homeScore, sport:awayScore
    - Date: value.schema:startDate
    - Status: value.sport:status
    
    Input:
        all_fixtures: List of sport:Event documents from database
        team_id: Team ID (numeric string, e.g., "40")
        team_urn: Full URN (e.g., "urn:apifootball:team:40")
        date: Optional date limit (YYYY-MM-DD format) - fixtures up to this date
        last_matches: Number of most recent fixtures to return per context (default: 10)
    
    Returns:
        fixtures_total: Last N fixtures (home or away)
        fixtures_home: Last N home fixtures
        fixtures_away: Last N away fixtures
    """
    try:
        # Parse request_data
        if isinstance(request_data, str):
            import json
            request_data = json.loads(request_data)
        
        params = request_data.get('params', request_data)
        all_fixtures = params.get('all_fixtures', [])
        team_id = str(params.get('team_id', ''))
        team_urn = params.get('team_urn', f'urn:apifootball:team:{team_id}')
        date_limit = params.get('date')  # Optional: "YYYY-MM-DD"
        last_matches = params.get('last_matches', 10)
        
        if not all_fixtures:
            return {
                "status": True,
                "data": {
                    "fixtures_total": [],
                    "fixtures_home": [],
                    "fixtures_away": [],
                },
                "message": "No fixtures provided"
            }
        
        if not team_id:
            return {
                "status": False,
                "data": {"error": "No team_id provided"},
                "message": "Missing team_id parameter"
            }
        
        # Helper to extract team info from sport:competitors
        def get_team_qualifier(competitors, team_id, team_urn):
            """Returns 'home', 'away', or None if team not found"""
            for comp in competitors:
                comp_id = comp.get('@id', '')
                # Match by full URN or just the ID part
                if comp_id == team_urn or comp_id.endswith(f':{team_id}'):
                    return comp.get('sport:qualifier')
            return None
        
        # Helper to normalize sport:Event to common fixture format
        def normalize_fixture(doc):
            """Convert sport:Event to a normalized fixture dict"""
            value = doc.get('value', {}) if isinstance(doc, dict) else {}
            
            competitors = value.get('sport:competitors', [])
            score = value.get('sport:score', {})
            
            # Find home and away teams
            home_team = None
            away_team = None
            for comp in competitors:
                qualifier = comp.get('sport:qualifier', '')
                if qualifier == 'home':
                    home_team = comp
                elif qualifier == 'away':
                    away_team = comp
            
            if not home_team or not away_team:
                return None
            
            # Extract team IDs from URNs
            def extract_team_id(urn):
                if not urn:
                    return ''
                # URN format: urn:apifootball:team:40
                parts = urn.split(':')
                return parts[-1] if parts else ''
            
            home_id = extract_team_id(home_team.get('@id', ''))
            away_id = extract_team_id(away_team.get('@id', ''))
            
            # Extract fixture ID from @id
            event_id = value.get('@id', '')
            fixture_id = extract_team_id(event_id)  # Last part of URN
            
            # Get date (format: 2025-08-15T19:00:00+00:00)
            start_date = value.get('schema:startDate', '')
            fixture_date = start_date[:10] if start_date else ''
            
            return {
                'fixture': {
                    'id': fixture_id,
                    'date': start_date,
                },
                'teams': {
                    'home': {
                        'id': home_id,
                        'name': home_team.get('name', ''),
                        'logo': home_team.get('schema:logo', ''),
                    },
                    'away': {
                        'id': away_id,
                        'name': away_team.get('name', ''),
                        'logo': away_team.get('schema:logo', ''),
                    }
                },
                'goals': {
                    'home': score.get('sport:homeScore'),
                    'away': score.get('sport:awayScore'),
                },
                'score': {
                    'fulltime': {
                        'home': score.get('sport:homeScore'),
                        'away': score.get('sport:awayScore'),
                    },
                    'halftime': score.get('sport:halfTime', {}),
                },
                # Keep original sport:Event data for reference
                '_sport_event': {
                    '@id': event_id,
                    'name': value.get('name', ''),
                    'status': value.get('sport:status', ''),
                },
                '_date': fixture_date,
                '_doc_id': doc.get('_id', ''),
            }
        
        # Filter and categorize fixtures
        fixtures_total = []
        fixtures_home = []
        fixtures_away = []
        seen_ids = set()
        
        for doc in all_fixtures:
            try:
                value = doc.get('value', {}) if isinstance(doc, dict) else {}
                
                # Check status - only finished matches
                status = value.get('sport:status', '')
                if status != 'FT':
                    continue
                
                # Check if this fixture involves our team
                competitors = value.get('sport:competitors', [])
                qualifier = get_team_qualifier(competitors, team_id, team_urn)
                
                if not qualifier:
                    continue  # Team not in this fixture
                
                # Check date if limit provided
                start_date = value.get('schema:startDate', '')
                fixture_date = start_date[:10] if start_date else ''
                
                if date_limit and fixture_date:
                    if fixture_date > date_limit:
                        continue
                
                # Normalize the fixture
                normalized = normalize_fixture(doc)
                if not normalized:
                    continue
                
                # Deduplicate by fixture ID
                fixture_id = normalized['fixture']['id']
                if fixture_id in seen_ids:
                    continue
                seen_ids.add(fixture_id)
                
                # Add to appropriate lists
                fixtures_total.append(normalized)
                if qualifier == 'home':
                    fixtures_home.append(normalized)
                elif qualifier == 'away':
                    fixtures_away.append(normalized)
                
            except Exception as e:
                print(f"Error processing sport:Event: {e}")
                continue
        
        # Sort all lists by date descending (most recent first)
        fixtures_total.sort(key=lambda x: x.get('_date', ''), reverse=True)
        fixtures_home.sort(key=lambda x: x.get('_date', ''), reverse=True)
        fixtures_away.sort(key=lambda x: x.get('_date', ''), reverse=True)
        
        # Limit to last_matches
        fixtures_total = fixtures_total[:last_matches]
        fixtures_home = fixtures_home[:last_matches]
        fixtures_away = fixtures_away[:last_matches]
        
        # Clean up temporary fields
        def clean_fixtures(fixtures):
            for f in fixtures:
                f.pop('_date', None)
            return fixtures
        
        fixtures_total = clean_fixtures(fixtures_total)
        fixtures_home = clean_fixtures(fixtures_home)
        fixtures_away = clean_fixtures(fixtures_away)
        
        return {
            "status": True,
            "data": {
                "fixtures_total": fixtures_total,
                "fixtures_home": fixtures_home,
                "fixtures_away": fixtures_away,
            },
            "message": f"Filtered {len(fixtures_total)} total, {len(fixtures_home)} home, {len(fixtures_away)} away fixtures for team {team_id}"
        }
        
    except Exception as e:
        import traceback
        return {
            "status": False,
            "data": {"error": str(e), "traceback": traceback.format_exc()},
            "message": f"Error filtering sport:Event fixtures: {str(e)}"
        }


def calculate_team_metrics_from_sport_events(request_data):
    """
    Calculate raw metrics for a SINGLE team based on normalized sport:Event fixtures.
    
    This is similar to calculate_team_metrics but expects fixtures already normalized
    from sport:Event format (by filter_sport_events_by_team).
    
    Input:
        fixtures_total: List of normalized fixtures (home or away) for total ranking
        fixtures_home: List of normalized HOME fixtures for home ranking
        fixtures_away: List of normalized AWAY fixtures for away ranking
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
        
        fixtures_total = params.get('fixtures_total', [])
        fixtures_home = params.get('fixtures_home', [])
        fixtures_away = params.get('fixtures_away', [])
        
        team_id = str(params.get('team_id', ''))
        team_name = params.get('team_name', f'Team {team_id}')
        team_logo = params.get('team_logo')
        last_matches = params.get('last_matches', 10)
        
        if not fixtures_total:
            return {
                "status": False,
                "data": {"error": "No fixtures provided"},
                "message": "Missing fixtures_total parameter"
            }
        
        if not team_id:
            return {
                "status": False,
                "data": {"error": "No team_id provided"},
                "message": "Missing team_id parameter"
            }
        
        # Helper to initialize stats
        def init_stats():
            return {
                'games': 0,
                'wins': 0,
                'draws': 0,
                'losses': 0,
                'goals_for': 0,
                'goals_against': 0,
                'clean_sheets': 0,
                'failed_to_score': 0
            }
        
        # Helper to update stats from a single fixture
        def update_stats(stats, our_goals, opp_goals):
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
        
        # Process a list of fixtures and return stats
        def process_fixtures(fixtures, context_hint=None):
            stats = init_stats()
            seen_fixture_ids = set()
            
            for fixture in fixtures:
                try:
                    fixture_meta = fixture.get('fixture', {}) if isinstance(fixture, dict) else {}
                    fixture_id = str(fixture_meta.get('id', ''))
                    
                    if fixture_id:
                        if fixture_id in seen_fixture_ids:
                            continue
                        seen_fixture_ids.add(fixture_id)
                    
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
                        continue
                    
                    # Get our team's goals and opponent's goals
                    if is_home:
                        our_goals = home_goals
                        opp_goals = away_goals
                    else:
                        our_goals = away_goals
                        opp_goals = home_goals
                    
                    update_stats(stats, our_goals, opp_goals)
                    
                except Exception as e:
                    print(f"Error processing fixture: {e}")
                    continue
            
            return stats
        
        # Process each fixture list independently
        stats_total = process_fixtures(fixtures_total, 'total')
        stats_home = process_fixtures(fixtures_home, 'home') if fixtures_home else init_stats()
        stats_away = process_fixtures(fixtures_away, 'away') if fixtures_away else init_stats()
        
        if stats_total['games'] == 0:
            return {
                "status": False,
                "data": {"error": f"No valid fixtures for team {team_id}"},
                "message": f"No completed matches found for team {team_name}"
            }
        
        # Helper to calculate per-game metrics from stats
        def calc_metrics(stats, context):
            if stats['games'] == 0:
                return None
            
            goals_per_game = stats['goals_for'] / stats['games']
            concede_rate = stats['goals_against'] / stats['games']
            win_rate = stats['wins'] / stats['games']
            points_per_game = (stats['wins'] * 3 + stats['draws']) / stats['games']
            clean_sheet_rate = stats['clean_sheets'] / stats['games']
            scoring_rate = 1 - (stats['failed_to_score'] / stats['games'])
            
            return {
                "team_id": team_id,
                "team_name": team_name,
                "team_logo": team_logo,
                "context": context,
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
                "last_matches": last_matches
            }
        
        from datetime import datetime
        
        metrics_total = calc_metrics(stats_total, 'total')
        metrics_home = calc_metrics(stats_home, 'home')
        metrics_away = calc_metrics(stats_away, 'away')
        
        return {
            "status": True,
            "data": {
                "team_metrics": metrics_total,  # For backward compatibility
                "metrics_total": metrics_total,
                "metrics_home": metrics_home,
                "metrics_away": metrics_away,
                "calculated_at": datetime.utcnow().isoformat()
            },
            "message": f"Successfully calculated metrics for {team_name} (total: {stats_total['games']}, home: {stats_home['games']}, away: {stats_away['games']} games)"
        }
        
    except Exception as e:
        import traceback
        return {
            "status": False,
            "data": {"error": str(e), "traceback": traceback.format_exc()},
            "message": f"Error calculating team metrics from sport:Event: {str(e)}"
        }
