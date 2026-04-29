def invoke_past_events(request_data):

    params = request_data.get("params") or {}
    
    past_events_objects = params.get("past-events") or []
    current_match_teams = params.get("current-match-teams") or []
    
    # Track which teams we've already seen their first match
    teams_first_match_seen = set()
    
    events = []
    
    for event_index, event in enumerate(past_events_objects):
        if not event:
            continue
            
        # Extract basic information
        event_name = event.get("name", "Unknown Event")
        sport_name = event.get("schema:sportName", "Unknown Sport")
        start_date = event.get("schema:startDate", "Unknown Date")
        
        # Extract competition and season information
        competition = event.get("sport:competition") or {}
        competition_name = competition.get("name", "Unknown Competition")
        season = competition.get("sport:season") or {}
        season_name = season.get("name", "Unknown Season")
        
        # Extract competitors (home vs away)
        competitors = event.get("sport:competitors") or []
        home_team = "Unknown"
        away_team = "Unknown"
        for competitor in competitors:
            if not competitor:
                continue
            if competitor.get("sport:qualifier") == "home":
                home_team = competitor.get("name", "Unknown")
            elif competitor.get("sport:qualifier") == "away":
                away_team = competitor.get("name", "Unknown")
        
        match_name = f"{home_team} vs {away_team}"
        
        # Extract match status
        match_status = event.get("sport:matchStatus", "unknown")
        
        # Extract score information
        score_obj = event.get("sport:score") or {}
        if match_status == "ended" or match_status == "closed":
            home_score = score_obj.get("sport:homeScore", 0)
            away_score = score_obj.get("sport:awayScore", 0)
            score_text = f"{home_score}-{away_score}"
            
            # Get half-time score
            half_time = score_obj.get("sport:halfTime") or {}
            ht_home = half_time.get("home_score", 0)
            ht_away = half_time.get("away_score", 0)
            half_time_score = f"HT: {ht_home}-{ht_away}"
        else:
            score_text = "No score"
            half_time_score = ""
        
        # Extract venue information
        venue = event.get("sport:venue") or {}
        venue_name = venue.get("name", "Unknown Venue")
        venue_city = venue.get("schema:addressLocality", "Unknown City")
        
        # Extract goals/scorers from timeline
        timeline_scores = event.get("timeline:scores") or []
        goals_list = []
        for goal in timeline_scores:
            if not goal:
                continue
            goal_time = goal.get("match_clock", "?")
            competitor = goal.get("competitor", "")
            players = goal.get("players") or []
            scorer = players[0].get("name", "Unknown") if players and len(players) > 0 else "Unknown"
            team = home_team if competitor == "home" else away_team
            goals_list.append(f"{scorer} ({goal_time}', {team})")
        
        goals_summary = "; ".join(goals_list) if goals_list else "No goals"
        
        # Extract RED cards ONLY from the FIRST match of EACH team in the current matchup
        # Robust logic: Check if any team from current match is in this event
        timeline_cards = event.get("timeline:cards") or []
        red_cards = []
        
        # Get teams that participated in THIS event
        event_team_ids = [comp.get("@id") for comp in competitors if comp]
        
        # Check if this event involves any team from the current match
        # AND if we haven't seen this team's first match yet
        is_first_match_of_team = False
        for team_id in event_team_ids:
            if team_id in current_match_teams and team_id not in teams_first_match_seen:
                is_first_match_of_team = True
                teams_first_match_seen.add(team_id)
        
        # Only collect red cards if this is the first match of one of the teams
        if is_first_match_of_team:
            for card in timeline_cards:
                if not card:
                    continue
                card_type = card.get("type", "")
                
                # Only collect RED cards (ignore yellow cards)
                if card_type == "red_card" or card_type == "yellow_red_card":
                    card_time = card.get("match_clock", "?")
                    competitor = card.get("competitor", "")
                    players = card.get("players") or []
                    player_name = players[0].get("name", "Unknown") if players and len(players) > 0 else "Unknown"
                    team = home_team if competitor == "home" else away_team
                    red_cards.append(f"{player_name} ({card_time}', {team})")
        
        red_cards_summary = "; ".join(red_cards) if red_cards else "None"
        
        # Extract team statistics
        timeline_stats = event.get("timeline:statistics") or []
        home_stats = {}
        away_stats = {}
        
        if timeline_stats and len(timeline_stats) > 0:
            first_stat = timeline_stats[0]
            if first_stat:
                totals = first_stat.get("totals") or {}
                competitors_stats = totals.get("competitors") or []
                
                for comp_stat in competitors_stats:
                    if not comp_stat:
                        continue
                    qualifier = comp_stat.get("qualifier", "")
                    stats = comp_stat.get("statistics") or {}
                    
                    if qualifier == "home":
                        home_stats = stats
                    elif qualifier == "away":
                        away_stats = stats
        
        # Format team statistics
        team_stats_summary = ""
        if home_stats and away_stats:
            possession_home = home_stats.get("ball_possession", 0)
            possession_away = away_stats.get("ball_possession", 0)
            
            shots_home = home_stats.get("shots_total", 0)
            shots_away = away_stats.get("shots_total", 0)
            
            shots_on_target_home = home_stats.get("shots_on_target", 0)
            shots_on_target_away = away_stats.get("shots_on_target", 0)
            
            corners_home = home_stats.get("corner_kicks", 0)
            corners_away = away_stats.get("corner_kicks", 0)
            
            fouls_home = home_stats.get("fouls", 0)
            fouls_away = away_stats.get("fouls", 0)
            
            team_stats_summary = (
                f"Possession: {possession_home}%-{possession_away}% | "
                f"Shots: {shots_home}-{shots_away} | "
                f"On Target: {shots_on_target_home}-{shots_on_target_away} | "
                f"Corners: {corners_home}-{corners_away} | "
                f"Fouls: {fouls_home}-{fouls_away}"
            )
        
        # Extract top performers (goals and assists)
        top_performers = []
        if timeline_stats and len(timeline_stats) > 0:
            first_stat = timeline_stats[0]
            if first_stat:
                totals = first_stat.get("totals") or {}
                competitors_stats = totals.get("competitors") or []
                
                for comp_stat in competitors_stats:
                    if not comp_stat:
                        continue
                    team_name = comp_stat.get("name", "")
                    players = comp_stat.get("players") or []
                    
                    for player in players:
                        if not player:
                            continue
                        
                        player_id = player.get("id")
                        player_name = player.get("name", "")
                        player_stats = player.get("statistics") or {}
                        goals = player_stats.get("goals_scored", 0)
                        assists = player_stats.get("assists", 0)
                        
                        if goals > 0 or assists > 0:
                            top_performers.append({
                                "player_id": player_id,
                                "player_name": player_name,
                                "team_name": team_name,
                                "goals": goals,
                                "assists": assists
                            })
        
        # Create unified event object
        event_obj = {
            "summary": f"{match_name} | {sport_name} | {start_date} | {competition_name} | {season_name} | {event_name} | {match_status} | {score_text} | {venue_name} | {venue_city}",
            "match": match_name,
            "sport": sport_name,
            "date": start_date,
            "competition": competition_name,
            "season": season_name,
            "status": match_status,
            "venue": f"{venue_name}, {venue_city}",
            "score": {
                "final": score_text,
                "half_time": half_time_score
            },
            "goals": goals_summary,
            "cards": {
                "red": red_cards_summary  # Only red cards from last match
            },
            "team_statistics": team_stats_summary,
            "top_performers": top_performers
        }
        events.append(event_obj)

    return {
        "status": True,
        "message": "Past events parsed successfully.",
        "data": {
            "events": events
        }
    }
