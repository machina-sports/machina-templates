import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

def aggregate_features(params):
    """
    Aggregate basketball game features from API-Basketball data.

    This function computes:
    - Season strength metrics (win_pct, net_rating, etc.)
    - Rolling form features (last 3, 5, 10 games)
    - Schedule features (days_rest, back_to_back_flag)
    - Team style metrics (3p_rate, rebound rates, etc.)

    Args:
        params: Dictionary containing:
            - game_id: Target game ID
            - league: League ID
            - season: Season year

    Returns:
        Dictionary with aggregated features
    """

    game_id = params.get('game_id')
    league = params.get('league')
    season = params.get('season')

    if not all([game_id, league, season]):
        return {"error": "Missing required parameters: game_id, league, season"}

    try:
        # Load game data
        game_data = _load_game_data(game_id)
        if not game_data:
            return {"error": f"Game {game_id} not found"}

        home_team_id = game_data['teams']['home']['id']
        away_team_id = game_data['teams']['away']['id']

        # Load season data
        season_games = _load_season_games(league, season)
        standings_data = _load_standings_data(league, season)
        team_stats = _load_team_statistics(league, season)

        # Compute season strength metrics
        home_strength = _compute_team_strength(home_team_id, season_games, standings_data, team_stats)
        away_strength = _compute_team_strength(away_team_id, season_games, standings_data, team_stats)

        # Compute rolling form features
        home_form = _compute_rolling_form(home_team_id, season_games, game_data['date'])
        away_form = _compute_rolling_form(away_team_id, season_games, game_data['date'])

        # Compute schedule features
        home_schedule = _compute_schedule_features(home_team_id, season_games, game_data['date'])
        away_schedule = _compute_schedule_features(away_team_id, season_games, game_data['date'])

        # Compute matchup style features
        matchup_style = _compute_matchup_style(home_team_id, away_team_id, team_stats)

        # Build feature payload
        feature_payload = {
            "meta": {
                "league": league,
                "season": season,
                "game_id": game_id,
                "date": game_data['date'],
                "low_data_flag": False,  # Will be set based on data quality checks
                "player_depth_flag": True  # Will be set based on player stats availability
            },
            "home": {
                "team_id": home_team_id,
                "name": game_data['teams']['home']['name'],
                "season_strength": home_strength,
                "rolling_form": home_form,
                "schedule": home_schedule
            },
            "away": {
                "team_id": away_team_id,
                "name": game_data['teams']['away']['name'],
                "season_strength": away_strength,
                "rolling_form": away_form,
                "schedule": away_schedule
            },
            "matchup": {
                "style": matchup_style
            },
            "news": {
                "deltas": {"home_offense_delta": 0.0, "home_defense_delta": 0.0, "pace_delta": 0.0},
                "reliability": 0.0,
                "evidence_count": 0,
                "missing_info_flags": []
            }
        }

        return {"feature_payload": feature_payload}

    except Exception as e:
        return {"error": f"Feature aggregation failed: {str(e)}"}

def _load_game_data(game_id):
    """Load game data from documents"""
    # This would typically query the document database
    # For now, return mock data structure
    return {
        'game_id': game_id,
        'date': '2024-01-15',
        'teams': {
            'home': {'id': 1, 'name': 'Home Team'},
            'away': {'id': 2, 'name': 'Away Team'}
        }
    }

def _load_season_games(league, season):
    """Load all games for the season"""
    # This would query basketball-game documents
    return []

def _load_standings_data(league, season):
    """Load standings data"""
    # This would query basketball-standing documents
    return {}

def _load_team_statistics(league, season):
    """Load team statistics"""
    # This would query sport:TeamParticipation documents
    return {}

def _compute_team_strength(team_id, season_games, standings_data, team_stats):
    """Compute season strength metrics for a team"""

    # Filter games for this team
    team_games = [g for g in season_games if g.get('teams', {}).get('home', {}).get('id') == team_id or
                  g.get('teams', {}).get('away', {}).get('id') == team_id]

    if not team_games:
        return {
            "win_pct": 0.5,
            "net_rating": 0.0,
            "home_win_pct": 0.5
        }

    # Calculate win percentage
    wins = sum(1 for g in team_games if _did_team_win(g, team_id))
    win_pct = wins / len(team_games)

    # Calculate home win percentage
    home_games = [g for g in team_games if g.get('teams', {}).get('home', {}).get('id') == team_id]
    home_wins = sum(1 for g in home_games if _did_team_win(g, team_id))
    home_win_pct = home_wins / len(home_games) if home_games else 0.5

    # Calculate net rating (placeholder - would need actual scoring data)
    net_rating = (win_pct - 0.5) * 20  # Rough approximation

    return {
        "win_pct": win_pct,
        "net_rating": net_rating,
        "home_win_pct": home_win_pct
    }

def _compute_rolling_form(team_id, season_games, game_date):
    """Compute rolling form features"""

    # Convert game_date to datetime
    target_date = datetime.fromisoformat(game_date.replace('Z', '+00:00'))

    # Get games before target date
    past_games = []
    for game in season_games:
        game_date_str = game.get('date', '')
        if game_date_str:
            game_dt = datetime.fromisoformat(game_date_str.replace('Z', '+00:00'))
            if game_dt < target_date and (game.get('teams', {}).get('home', {}).get('id') == team_id or
                                         game.get('teams', {}).get('away', {}).get('id') == team_id):
                past_games.append(game)

    # Sort by date descending (most recent first)
    past_games.sort(key=lambda x: x.get('date', ''), reverse=True)

    # Calculate rolling win percentages
    last_3_games = past_games[:3]
    last_5_games = past_games[:5]
    last_10_games = past_games[:10]

    last_3_win_pct = sum(1 for g in last_3_games if _did_team_win(g, team_id)) / len(last_3_games) if last_3_games else 0.5
    last_5_win_pct = sum(1 for g in last_5_games if _did_team_win(g, team_id)) / len(last_5_games) if last_5_games else 0.5
    last_10_win_pct = sum(1 for g in last_10_games if _did_team_win(g, team_id)) / len(last_10_games) if last_10_games else 0.5

    # Calculate rolling net rating (placeholder)
    last_5_net_rating = (last_5_win_pct - 0.5) * 15
    last_10_net_rating = (last_10_win_pct - 0.5) * 15

    # Placeholder pace calculation
    pace = 95.0  # NBA average

    return {
        "last_3_win_pct": last_3_win_pct,
        "last_5_net_rating": last_5_net_rating,
        "last_10_win_pct": last_10_win_pct,
        "pace": pace
    }

def _compute_schedule_features(team_id, season_games, game_date):
    """Compute schedule-related features"""

    target_date = datetime.fromisoformat(game_date.replace('Z', '+00:00'))

    # Find previous game
    prev_game = None
    for game in season_games:
        game_date_str = game.get('date', '')
        if game_date_str:
            game_dt = datetime.fromisoformat(game_date_str.replace('Z', '+00:00'))
            if game_dt < target_date and (game.get('teams', {}).get('home', {}).get('id') == team_id or
                                         game.get('teams', {}).get('away', {}).get('id') == team_id):
                if prev_game is None or game_dt > datetime.fromisoformat(prev_game.get('date', '').replace('Z', '+00:00')):
                    prev_game = game

    days_rest = 2  # Default
    if prev_game:
        prev_date = datetime.fromisoformat(prev_game.get('date', '').replace('Z', '+00:00'))
        days_rest = (target_date - prev_date).days

    back_to_back = days_rest <= 1

    return {
        "days_rest": days_rest,
        "back_to_back": back_to_back
    }

def _compute_matchup_style(home_team_id, away_team_id, team_stats):
    """Compute matchup style features"""

    # Placeholder calculations - would need actual statistical data
    return {
        "home_3p_rate": 0.35,
        "away_3p_rate": 0.36,
        "rebound_edge_proxy": 0.0,
        "turnover_edge_proxy": 0.0
    }

def filter_search_results(params):
    """
    Filter and deduplicate search results.

    Args:
        params: Dictionary containing:
            - search_results: List of search result objects
            - recency_days: Number of days for recency filtering

    Returns:
        Dictionary with filtered search results
    """
    search_results = params.get('search_results', [])
    recency_days = params.get('recency_days', 3)

    if not search_results:
        return {"filtered_search_results": []}

    try:
        # Deduplicate by URL
        seen_urls = set()
        deduplicated = []

        for result in search_results:
            url = result.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                deduplicated.append(result)

        # Filter by recency (placeholder - would need actual date parsing)
        # For now, keep all results
        filtered_results = deduplicated

        # Remove irrelevant results (placeholder - would use LLM or keyword filtering)
        relevant_results = []
        for result in filtered_results:
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()

            # Simple keyword filtering for basketball content
            if any(keyword in title or keyword in snippet for keyword in
                   ['basketball', 'nba', 'game', 'match', 'vs', 'versus', 'team', 'player']):
                relevant_results.append(result)

        return {"filtered_search_results": relevant_results[:10]}  # Limit to top 10

    except Exception as e:
        return {"error": f"Search result filtering failed: {str(e)}", "filtered_search_results": []}

def format_evidence_outputs(params):
    """
    Format evidence extraction outputs for workflow consumption.

    Args:
        params: Dictionary containing evidence data

    Returns:
        Dictionary with formatted evidence outputs
    """
    return {
        "news_evidence": {
            'evidence_items': params.get('evidence_items', []),
            'news_reliability': params.get('news_reliability', 0.0),
            'missing_info_flags': params.get('missing_info_flags', [])
        },
        "news_deltas": {
            'deltas': params.get('team_level_deltas', {}),
            'news_reliability': params.get('news_reliability', 0.0),
            'missing_info_flags': params.get('missing_info_flags', [])
        }
    }

def _did_team_win(game, team_id):
    """Helper function to determine if team won the game"""
    # This would need actual score data from the game
    # Placeholder logic
    return team_id == game.get('teams', {}).get('home', {}).get('id')  # Assume home team wins