def summarize_message_data(request_data):
    """
    Transform all data in a user message to LLM-friendly summaries.
    Handles: matched-teams, fixture-events, played-events, head-to-head-events.
    Also handles: content-articles (optional).
    Passes through: faq-docs, insights-docs, markets-docs, websearch-docs (already summarized).
    
    Args:
        request_data (dict): Request data containing:
            - params (dict):
                - last_user_msg (dict): The last user message object from thread
                - played_events (list): Loaded played event documents (optional)
                - fixture_events (list): Loaded fixture event documents (optional)
                - head_to_head_events (list): Loaded head-to-head event documents (optional)
                - content_articles (list): Loaded content-article objects (optional)
                - timezone (str): Timezone code: 'br' (Brazil, GMT-3), 'es' (Spain, GMT+1), 'en' (Washington D.C., GMT-4) - default: 'br'
    
    Returns:
        dict: Response containing summarized data ready for LLM consumption
    """
    from datetime import datetime, timezone, timedelta
    import re
    
    # Define timezone mappings
    TIMEZONE_MAP = {
        'br': ('Brazil/Brasilia', -3),       # GMT-3
        'es': ('Europe/Madrid', 1),          # GMT+1 (CET)
        'en': ('US/Eastern', -4),            # GMT-4 (Washington D.C., EDT)
    }
    
    def normalize_team_name(team_name):
        """
        Normalize team names by:
        1. Removing prefixes (SC, FC, EC, CR, FR, CA, FB, etc.)
        2. Removing regional suffixes (SP, RS, RJ, MG, CE, BA, PE, etc.)
        3. Removing intermediate club type indicators
        4. Adding proper accents to Brazilian team names
        """
        if not team_name or not isinstance(team_name, str):
            return team_name
        
        team = team_name.strip()
        
        # Remove leading club type prefixes
        team = re.sub(r'^(FC|SC|EC|AC|CE|EF|PE|ASS|ASOC|SE|IND|CR|FR|CA|FB|CBS|CEF)\s+', '', team, flags=re.IGNORECASE)
        
        # Remove trailing state/region abbreviations with optional club type before them
        team = re.sub(r'\s+(FC|SC|EC|AC|CE|EF|PE|ASS|ASOC|SE|IND|CR|FR|CA|FB|CBS|CEF)?\s*[A-Z]{2}$', '', team, flags=re.IGNORECASE)
        
        # Remove intermediate club type abbreviations
        team = re.sub(r'\s+(FC|SC|EC|AC|CE|EF|PE|ASS|ASOC|SE|IND|CR|FR|CA|FB|CBS|CEF)\s+', ' ', team, flags=re.IGNORECASE)
        
        # Remove extra spaces
        team = re.sub(r'\s+', ' ', team).strip()
        
        # Specific team mappings
        team_map = {
            "Sao Paulo": "São Paulo",
            "Sao paulo": "São Paulo",
            "SAO PAULO": "São Paulo",
            "Corinthians": "Corinthians",
            "Corinthians SP": "Corinthians",
            "Palmeiras": "Palmeiras",
            "SE Palmeiras": "Palmeiras",
            "Flamengo": "Flamengo",
            "CR Flamengo": "Flamengo",
            "Vasco": "Vasco da Gama",
            "Botafogo": "Botafogo",
            "FR Botafogo": "Botafogo",
            "Fluminense": "Fluminense",
            "Santos": "Santos",
            "Santos FC": "Santos",
            "Sao Paulo FC": "São Paulo",
            "Internacional": "Internacional",
            "Internacional RS": "Internacional",
            "SC Internacional": "Internacional",
            "Gremio": "Grêmio",
            "Gremio FB Porto Alegrense": "Grêmio",
            "Gremio Porto Alegrense": "Grêmio",
            "Gremio Porto-alegrense": "Grêmio",
            "FB Porto Alegrense": "Grêmio",
            "Cruzeiro": "Cruzeiro",
            "Cruzeiro EC": "Cruzeiro",
            "Atletico": "Atlético Mineiro",
            "Atletico Mineiro": "Atlético Mineiro",
            "CA Mineiro": "Atlético Mineiro",
            "Mineiro": "Atlético Mineiro",
            "Bahia": "Bahia",
            "EC Bahia": "Bahia",
            "Fortaleza": "Fortaleza",
            "Fortaleza EC": "Fortaleza",
            "Ceara": "Ceará",
            "Ceara SC": "Ceará",
            "Ceara SC Fortaleza": "Ceará",
            "Ceara Fortaleza": "Ceará",
            "Ceará": "Ceará",
            "Vitoria": "Vitória",
            "EC Vitoria": "Vitória",
            "EC Vitoria Salvador": "Vitória",
            "Vitoria Salvador": "Vitória",
            "Juventude": "Juventude",
            "EC Juventude": "Juventude",
            "EC Juventude Caxias do Sul": "Juventude",
            "Juventude Caxias do Sul": "Juventude",
            "Sport": "Sport Recife",
            "Sport Recife": "Sport Recife",
            "Sport Club do Recife": "Sport Recife",
            "Red Bull Bragantino": "Red Bull Bragantino",
            "Bragantino": "Red Bull Bragantino",
            "Nautico": "Náutico",
            "Náutico": "Náutico",
            "Paysandu": "Paysandu",
            "America": "América",
            "América": "América",
            "CSA": "CSA",
            "Ponte Preta": "Ponte Preta",
            "Londrina": "Londrina",
            "Goias": "Goiás",
            "Goiás": "Goiás",
            "Mirassol": "Mirassol",
            "Mirassol FC": "Mirassol",
            "Vasco da Gama": "Vasco da Gama",
        }
        
        team = team.strip()
        return team_map.get(team, team)
    
    def normalize_runner_name(runner_name):
        """
        Normalize runner names by:
        1. Translating Over/Under to Portuguese (Acima/Abaixo)
        2. Translating Draw/X to Empate
        3. Removing leading club type prefixes from team names
        """
        if not runner_name or not isinstance(runner_name, str):
            return runner_name
        
        runner = runner_name.strip()
        
        # Translate Over/Under to Portuguese
        runner = re.sub(r'^Over\s+', 'Acima ', runner, flags=re.IGNORECASE)
        runner = re.sub(r'^Under\s+', 'Abaixo ', runner, flags=re.IGNORECASE)
        
        # Translate Draw/X to Empate
        if runner.upper() == "X" or runner.upper() == "DRAW":
            runner = "Empate"
        
        # Normalize team names within runner
        runner = normalize_team_name(runner)
        
        return runner
    
    def normalize_event_title(event_title):
        """
        Normalize event title by:
        1. Converting "Team1 - Team2" format to "Team1 x Team2"
        2. Normalizing team names (removing suffixes, adding accents)
        """
        if not event_title or not isinstance(event_title, str):
            return event_title
        
        # Split by " - " to get teams
        parts = event_title.split(" - ")
        if len(parts) == 2:
            team1 = normalize_team_name(parts[0].strip())
            team2 = normalize_team_name(parts[1].strip())
            return f"{team1} x {team2}"
        
        return event_title
    
    def translate_market_title(title):
        """
        Translate English market titles to Portuguese
        """
        if not title or not isinstance(title, str):
            return title
        
        market_translations = {
            "Match Result": "Resultado Correto",
            "Match Result - 2UP (EP)": "Resultado Correto",
            "Match Result - 2UP": "Resultado Correto",
            "Winner": "Vencedor",
            "Draw": "Empate",
            "Over/Under": "Acima/Abaixo",
            "Both Teams to Score": "Ambos Times Marcam",
            "First Goal Scorer": "Primeiro Goleador",
            "Last Goal Scorer": "Último Goleador",
            "Correct Score": "Placar Correto",
            "Total Goals": "Total de Gols",
            "Next Goal": "Próximo Gol",
            "Handicap": "Handicap",
            "Asian Handicap": "Handicap Asiático",
            "Total Corners": "Total de Escanteios",
            "Total Cards": "Total de Cartões",
            "Double Chance": "Dupla Chance",
            "Half Time Result": "Resultado Primeiro Tempo",
            "Half Time/Full Time": "Resultado HT/FT",
            "Goal in Both Halves": "Gol nos Dois Tempos",
            "Team to Score in Both Halves": "Time Marca nos Dois Tempos",
            "Draw No Bet": "Sem Empate",
            "Accumulator": "Acumulador",
        }
        
        # Try exact match first
        if title in market_translations:
            return market_translations[title]
        
        # Try partial match for titles with variations
        for key, value in market_translations.items():
            if key.lower() in title.lower():
                return value
        
        return title
    
    def summarize_teams(matched_teams):
        """Summarize matched teams to simple strings."""
        summaries = []
        
        if not isinstance(matched_teams, list):
            return summaries
        
        for team in matched_teams:
            if not isinstance(team, dict):
                continue
            
            # Extract team name from various possible locations
            team_name = None
            value = team.get("value", {})
            
            if isinstance(value, dict):
                team_name = (
                    value.get("name") or 
                    value.get("schema:name") or 
                    value.get("sport:officialName") or 
                    value.get("sport:shortName") or
                    value.get("title")
                )
            
            if not team_name:
                team_name = team.get("title") or team.get("name") or "Unknown"
            
            # Extract match ratio
            match_ratio = team.get("match_ratio", 0)
            match_percentage = int(match_ratio * 100)
            
            summary = f"{team_name} (Match: {match_percentage}%)"
            summaries.append(summary)
        
        return summaries
    
    def format_datetime(datetime_str, tz_offset=-3):
        """
        Format datetime: 2025-12-07T19:00:00Z -> 07/12 16:00 (UTC to specified timezone)
        
        Args:
            datetime_str: ISO format datetime string
            tz_offset: Hour offset from UTC (default: -3 for Brazil)
        """
        if not datetime_str:
            return None
        
        try:
            # Handle formats like "2025-12-07ZT19:00:00Z" (fix double T)
            datetime_str = str(datetime_str).replace("ZT", "T")
            
            # Parse as UTC
            if datetime_str.endswith("Z"):
                datetime_str = datetime_str[:-1] + "+00:00"
            elif "T" in datetime_str and "+" not in datetime_str and "-" not in datetime_str[10:]:
                # Has T but no timezone, assume UTC
                datetime_str = datetime_str + "+00:00"
            
            dt = datetime.fromisoformat(datetime_str)
            
            # Convert UTC to specified timezone
            target_tz = timezone(timedelta(hours=tz_offset))
            dt_converted = dt.astimezone(target_tz)
            
            return dt_converted.strftime("%d/%m %H:%M")
            
        except Exception:
            # Try to extract just date if time parsing fails
            try:
                if "T" in str(datetime_str):
                    date_part = str(datetime_str).split("T")[0]
                    dt = datetime.fromisoformat(date_part)
                    return dt.strftime("%d/%m")
            except:
                pass
            return None
    
    def get_stat_abbreviation(stat_label):
        """Map statistic labels to abbreviations for compact display."""
        stat_abbreviations = {
            "Ball Possession": "Poss",
            "Cards Given": "Cd",
            "Corner Kicks": "Cor",
            "Fouls": "Fouls",
            "Free Kicks": "FK",
            "Goal Kicks": "GK",
            "Injuries": "Inj",
            "Offsides": "Off",
            "Red Cards": "Cd R",
            "Shots Blocked": "SB",
            "Shots Off Target": "SOT",
            "Shots On Target": "SOnT",
            "Shots Saved": "SS",
            "Shots Total": "ST",
            "Substitutions": "Sub",
            "Throw Ins": "TI",
            "Yellow Cards": "Cd Y",
            "Yellow Red Cards": "Cd YR",
            "Tackles": "Tack",
            "Interceptions": "Int",
            "Clearances": "Clear",
            "Dribbles": "Drib",
            "Passes": "Pass",
            "Pass Accuracy": "PA%",
            "Crosses": "Cross",
            "Touches": "Touch",
            "Possession": "Poss",
        }
        return stat_abbreviations.get(stat_label, stat_label)
    
    def extract_penalties_from_score(event):
        """Extract penalty shootout score information from sport:score."""
        score = event.get("sport:score", {})
        if not isinstance(score, dict):
            return None, None
        
        penalties = score.get("sport:penalties", {})
        if isinstance(penalties, dict) and penalties.get("sport:homeScore") is not None:
            pen_home = penalties.get("sport:homeScore")
            pen_away = penalties.get("sport:awayScore")
            print(f"[DEBUG] Extracted penalties from sport:score: {pen_home}-{pen_away}")
            return pen_home, pen_away
        
        return None, None
    
    def extract_cards_from_timeline(event):
        """Extract cards (yellow_card, red_card events) from schema:timeline separated by home/away."""
        timeline = event.get("schema:timeline", [])
        print(f"[DEBUG] Extracting cards from schema:timeline")
        
        cards_home_yellow = []
        cards_home_red = []
        cards_away_yellow = []
        cards_away_red = []
        
        if isinstance(timeline, list):
            for timeline_idx, action in enumerate(timeline):
                if isinstance(action, dict):
                    # Check if this is a card action
                    action_type = action.get("type") or action.get("@type")
                    is_yellow_card = (
                        action_type == "yellow_card" or 
                        (isinstance(action_type, str) and "yellow" in action_type.lower())
                    )
                    is_red_card = (
                        action_type == "red_card" or 
                        (isinstance(action_type, str) and "red" in action_type.lower())
                    )
                    
                    if is_yellow_card or is_red_card:
                        card_type = "yellow" if is_yellow_card else "red"
                        print(f"[DEBUG] Found {card_type}_card at timeline index {timeline_idx}")
                        
                        # Get competitor (home or away)
                        competitor = action.get("competitor", "")
                        print(f"[DEBUG] Competitor: {competitor}")
                        
                        # Get time of card
                        minutes = action.get("sport:minutesElapsed", "")
                        print(f"[DEBUG] Minutes elapsed: {minutes}")
                        
                        # Get player who received card
                        player_name = ""
                        participation = action.get("sport:participation", [])
                        if isinstance(participation, list) and len(participation) > 0:
                            first_player = participation[0]
                            if isinstance(first_player, dict):
                                participation_by = first_player.get("sport:participationBy", {})
                                if isinstance(participation_by, dict):
                                    player_name = participation_by.get("sport:label", "")
                        
                        print(f"[DEBUG] Player: {player_name}")
                        
                        # Format card entry: "Minutes' PlayerName"
                        card_entry = ""
                        
                        if minutes:
                            card_entry = f"{minutes}'"
                        
                        if player_name:
                            if card_entry:
                                card_entry += f" {player_name}"
                            else:
                                card_entry = player_name
                        
                        print(f"[DEBUG] Card entry: {card_entry}")
                        
                        # Add to appropriate list based on team and card type
                        if competitor.lower() == "home":
                            if is_yellow_card:
                                cards_home_yellow.append(card_entry)
                            else:
                                cards_home_red.append(card_entry)
                        elif competitor.lower() == "away":
                            if is_yellow_card:
                                cards_away_yellow.append(card_entry)
                            else:
                                cards_away_red.append(card_entry)
        
        return cards_home_yellow, cards_home_red, cards_away_yellow, cards_away_red
    
    def extract_goals_from_timeline(event):
        """Extract goals (score_change) and penalty_shootout events from schema:timeline separated by home/away."""
        timeline = event.get("schema:timeline", [])
        print(f"[DEBUG] schema:timeline type: {type(timeline)}, length: {len(timeline) if isinstance(timeline, list) else 'N/A'}")
        
        goals_home = []
        goals_away = []
        penalties_home = []
        penalties_away = []
        
        if isinstance(timeline, list):
            for timeline_idx, action in enumerate(timeline):
                if isinstance(action, dict):
                    # Check if this is a score_change or penalty_shootout action
                    action_type = action.get("type") or action.get("@type")
                    is_score_change = (
                        action_type == "score_change" or 
                        (isinstance(action_type, str) and "score-change" in action_type.lower())
                    )
                    is_penalty_shootout = (
                        action_type == "penalty_shootout" or 
                        (isinstance(action_type, str) and "penalty-shootout" in action_type.lower()) or
                        (isinstance(action_type, str) and "penalty_shootout" in action_type.lower())
                    )
                    
                    if is_score_change or is_penalty_shootout:
                        event_name = "penalty_shootout" if is_penalty_shootout else "score_change"
                        print(f"[DEBUG] Found {event_name} at timeline index {timeline_idx}")
                        
                        # Get competitor (home or away)
                        competitor = action.get("competitor", "")
                        print(f"[DEBUG] Competitor: {competitor}")
                        
                        # Get time of goal/penalty
                        minutes = action.get("sport:minutesElapsed", "")
                        print(f"[DEBUG] Minutes elapsed: {minutes}")
                        
                        # For penalty_shootout: Get penalty status (scored/missed)
                        penalty_status = ""
                        if is_penalty_shootout:
                            penalty_status = action.get("sport:penaltyStatus", "")
                            print(f"[DEBUG] Penalty status: {penalty_status}")
                        
                        # Get all participants (scorer + assisters)
                        participants = []
                        participation = action.get("sport:participation", [])
                        if isinstance(participation, list) and len(participation) > 0:
                            for p_idx, p in enumerate(participation):
                                if isinstance(p, dict):
                                    participation_by = p.get("sport:participationBy", {})
                                    if isinstance(participation_by, dict):
                                        player_label = participation_by.get("sport:label", "")
                                        if player_label:
                                            participants.append(player_label)
                                            print(f"[DEBUG] Participant {p_idx}: {player_label}")
                        
                        # Format entry: "Minutes' Player1 (assist: Player2, ...)" or "Minutes' Player1 (status)"
                        entry = ""
                        
                        if minutes:
                            entry = f"{minutes}'"
                        
                        if len(participants) > 0:
                            if entry:
                                entry += f" {participants[0]}"
                            else:
                                entry = participants[0]
                            # Add assisters if there are more than 1 participant
                            if len(participants) > 1:
                                assisters = ", ".join(participants[1:])
                                entry += f" (assist: {assisters})"
                        
                        # Add penalty status if it's a penalty shootout
                        if is_penalty_shootout and penalty_status:
                            if entry:
                                entry += f" ({penalty_status})"
                            else:
                                entry = penalty_status
                        
                        print(f"[DEBUG] Entry: {entry}")
                        
                        # Only add non-empty entries (filter out empty strings, whitespace, and "0'")
                        if entry and entry.strip() and entry.strip() != "0'":
                            # Add to appropriate list based on type and competitor
                            if is_score_change:
                                if competitor.lower() == "home":
                                    goals_home.append(entry)
                                elif competitor.lower() == "away":
                                    goals_away.append(entry)
                            elif is_penalty_shootout:
                                if competitor.lower() == "home":
                                    penalties_home.append(entry)
                                elif competitor.lower() == "away":
                                    penalties_away.append(entry)
        
        return goals_home, goals_away, penalties_home, penalties_away
    
    def format_event_summary(event, tz_offset=-3):
        """Format event dict to: Home vs Away | Competition | Date Time | Status | Score | Channel | Statistics"""
        try:
            # Extract teams
            competitors = event.get("sport:competitors", [])
            if not isinstance(competitors, list):
                return None
            
            home = next(
                (c.get("name") for c in competitors 
                 if isinstance(c, dict) and c.get("sport:qualifier") == "home"), 
                None
            )
            away = next(
                (c.get("name") for c in competitors 
                 if isinstance(c, dict) and c.get("sport:qualifier") == "away"), 
                None
            )
            
            if not home or not away:
                return None
            
            parts = [f"{home} vs {away}"]
            
            # Competition
            competition_obj = event.get("sport:competition", {})
            if isinstance(competition_obj, dict):
                competition = competition_obj.get("name")
                if competition:
                    parts.append(competition)
            
            # Date/Time (convert UTC to specified timezone)
            start_date = event.get("schema:startDate")
            if start_date:
                date_time = format_datetime(start_date, tz_offset)
                if date_time:
                    parts.append(date_time)
            
            # Status
            status = event.get("sport:status", "Fixture")
            if status:
                parts.append(str(status))
            
            # Score (if available)
            score = event.get("sport:score", {})
            if isinstance(score, dict) and score.get("sport:homeScore") is not None:
                home_score = score.get("sport:homeScore")
                away_score = score.get("sport:awayScore")
                score_str = f"{home_score}-{away_score}"
                
                # Add extra time score if available
                aggregate = score.get("sport:aggregate", {})
                if isinstance(aggregate, dict) and aggregate.get("sport:homeScore") is not None:
                    agg_home = aggregate.get("sport:homeScore")
                    agg_away = aggregate.get("sport:awayScore")
                    score_str += f" (AET: {agg_home}-{agg_away})"
                
                # Add penalty shootout score if available
                penalties = score.get("sport:penalties", {})
                if isinstance(penalties, dict) and penalties.get("sport:homeScore") is not None:
                    pen_home = penalties.get("sport:homeScore")
                    pen_away = penalties.get("sport:awayScore")
                    score_str += f" (Penalties: {pen_home}-{pen_away})"
                
                parts.append(score_str)
            
            # Channel (for fixtures)
            channels = event.get("sport:channels", [])
            if isinstance(channels, list) and len(channels) > 0:
                channel = channels[0]
                if isinstance(channel, dict):
                    channel_name = channel.get("sport:channelName")
                    if channel_name:
                        parts.append(f"📺 {channel_name}")
            
            # Statistics summary (schema:statistics is an array of team statistics objects)
            statistics = event.get("schema:statistics", [])
            print(f"[DEBUG] schema:statistics type: {type(statistics)}, length: {len(statistics) if isinstance(statistics, (list, dict)) else 'N/A'}")
            
            if isinstance(statistics, list) and len(statistics) > 0:
                stats_home = []
                stats_away = []
                
                # Iterate through each team's statistics object (home=idx 0, away=idx 1)
                for idx, team_stat in enumerate(statistics):
                    team_type = "Home" if idx == 0 else "Away"
                    print(f"[DEBUG] Processing team_stat[{idx}] ({team_type}): {type(team_stat)}")
                    
                    if isinstance(team_stat, dict):
                        # Get the sport:statistics array from this team
                        sport_stats_array = team_stat.get("sport:statistics", [])
                        print(f"[DEBUG] sport:statistics array type: {type(sport_stats_array)}, length: {len(sport_stats_array) if isinstance(sport_stats_array, list) else 'N/A'}")
                        
                        # Choose which array to append to (home or away)
                        target_stats = stats_home if idx == 0 else stats_away
                        
                        if isinstance(sport_stats_array, list):
                            # Iterate through each statistic in the array
                            for stat_idx, stat in enumerate(sport_stats_array):
                                print(f"[DEBUG] Processing stat[{stat_idx}]: {type(stat)}")
                                if isinstance(stat, dict):
                                    stat_label = stat.get("sport:statLabel", "")
                                    stat_value = stat.get("sport:statValue", "")
                                    stat_type = stat.get("sport:statType", "")
                                    print(f"[DEBUG] Stat: label='{stat_label}', value='{stat_value}', type='{stat_type}'")
                                    
                                    # Include all stats (including zeros)
                                    if stat_label and stat_value is not None:
                                        # Use abbreviation for compact display
                                        stat_abbr = get_stat_abbreviation(stat_label)
                                        target_stats.append(f"{stat_abbr}: {stat_value}")
                                        print(f"[DEBUG] Added {team_type} stat: {stat_abbr}: {stat_value}")
                
                # Format and append home and away statistics
                if stats_home or stats_away:
                    if stats_home:
                        stats_home_str = " | ".join(stats_home)
                        parts.append(f"[Home: {stats_home_str}]")
                        print(f"[DEBUG] Added Home stats: {stats_home_str}")
                    
                    if stats_away:
                        stats_away_str = " | ".join(stats_away)
                        parts.append(f"[Away: {stats_away_str}]")
                        print(f"[DEBUG] Added Away stats: {stats_away_str}")
            
            # Timeline - Extract goals and penalties from schema:timeline
            goals_home, goals_away, penalties_home, penalties_away = extract_goals_from_timeline(event)
            
            # Also extract penalty shootout scores from sport:score if available
            penalties_home_score, penalties_away_score = extract_penalties_from_score(event)
            
            # Add goals section
            if goals_home or goals_away:
                if goals_home:
                    goals_home_str = " | ".join(goals_home)
                    parts.append(f"[Home Players Goals: {goals_home_str}]")
                    print(f"[DEBUG] Added Home goals: {goals_home_str}")
                
                if goals_away:
                    goals_away_str = " | ".join(goals_away)
                    parts.append(f"[Away Players Goals: {goals_away_str}]")
                    print(f"[DEBUG] Added Away goals: {goals_away_str}")
            
            # Add penalties section (from timeline events)
            if penalties_home or penalties_away:
                if penalties_home:
                    penalties_home_str = " | ".join(penalties_home)
                    parts.append(f"[Home Players Penalties: {penalties_home_str}]")
                    print(f"[DEBUG] Added Home penalties: {penalties_home_str}")
                
                if penalties_away:
                    penalties_away_str = " | ".join(penalties_away)
                    parts.append(f"[Away Players Penalties: {penalties_away_str}]")
                    print(f"[DEBUG] Added Away penalties: {penalties_away_str}")
            
            # Add penalty shootout score summary if available (from sport:score)
            if penalties_home_score is not None or penalties_away_score is not None:
                parts.append(f"[Shootout Score: {penalties_home_score}-{penalties_away_score}]")
                print(f"[DEBUG] Added Shootout Score: {penalties_home_score}-{penalties_away_score}")
            
            # Timeline - Extract cards from schema:timeline
            cards_home_yellow, cards_home_red, cards_away_yellow, cards_away_red = extract_cards_from_timeline(event)
            
            # Format home cards
            if cards_home_yellow or cards_home_red:
                card_parts = []
                if cards_home_yellow:
                    yellow_str = " | ".join(cards_home_yellow)
                    card_parts.append(f"Yellow: {yellow_str}")
                if cards_home_red:
                    red_str = " | ".join(cards_home_red)
                    card_parts.append(f"Red: {red_str}")
                if card_parts:
                    home_cards_str = " | ".join(card_parts)
                    parts.append(f"[Home Cards: {home_cards_str}]")
                    print(f"[DEBUG] Added Home cards: {home_cards_str}")
            
            # Format away cards
            if cards_away_yellow or cards_away_red:
                card_parts = []
                if cards_away_yellow:
                    yellow_str = " | ".join(cards_away_yellow)
                    card_parts.append(f"Yellow: {yellow_str}")
                if cards_away_red:
                    red_str = " | ".join(cards_away_red)
                    card_parts.append(f"Red: {red_str}")
                if card_parts:
                    away_cards_str = " | ".join(card_parts)
                    parts.append(f"[Away Cards: {away_cards_str}]")
                    print(f"[DEBUG] Added Away cards: {away_cards_str}")
            
            # Add goal and penalty count summaries
            goals_home_count = len(goals_home)
            goals_away_count = len(goals_away)
            
            # Count only scored penalties (not missed ones)
            penalties_home_scored = sum(1 for p in penalties_home if "scored" in p.lower())
            penalties_away_scored = sum(1 for p in penalties_away if "scored" in p.lower())
            
            if goals_home_count > 0 or goals_away_count > 0:
                if goals_home_count > 0:
                    parts.append(f"[Home Goals: {goals_home_count}]")
                    print(f"[DEBUG] Added Home goals count: {goals_home_count}")
                if goals_away_count > 0:
                    parts.append(f"[Away Goals: {goals_away_count}]")
                    print(f"[DEBUG] Added Away goals count: {goals_away_count}")
            
            if penalties_home_scored > 0 or penalties_away_scored > 0:
                if penalties_home_scored > 0:
                    parts.append(f"[Home Penalties Goals: {penalties_home_scored}]")
                    print(f"[DEBUG] Added Home penalties goals count: {penalties_home_scored}")
                if penalties_away_scored > 0:
                    parts.append(f"[Away Penalties Goals: {penalties_away_scored}]")
                    print(f"[DEBUG] Added Away penalties goals count: {penalties_away_scored}")
            
            return " | ".join(parts)
            
        except Exception:
            return None
    
    def summarize_events(events, tz_offset=-3):
        """Summarize events to concise strings."""
        summaries = []
        
        if not isinstance(events, list):
            return summaries
        
        for event in events:
            # If already a string summary, pass through
            if isinstance(event, str):
                summaries.append(event)
                continue
            
            # If dict, format it
            if isinstance(event, dict):
                summary = format_event_summary(event, tz_offset)
                if summary:
                    summaries.append(summary)
        
        return summaries
    
    def summarize_standings(standings):
        """Summarize standings to concise docs for LLM grouped by team with classification."""
        standings_summary = []
        
        # Validate input
        if standings is None:
            print(f"[DEBUG] summarize_standings: standings is None")
            return standings_summary
        
        if not isinstance(standings, list):
            print(f"[DEBUG] summarize_standings: standings is not a list, type: {type(standings)}")
            return standings_summary
        
        if len(standings) == 0:
            print(f"[DEBUG] summarize_standings: standings is an empty list")
            return standings_summary
        
        for team in standings:
            try:
                if not isinstance(team, dict):
                    continue
                
                # Extract team information
                rank = team.get("rank", "")
                competitor = team.get("competitor", {})
                
                if not isinstance(competitor, dict):
                    competitor = {}
                
                team_name = normalize_team_name(competitor.get("name", "Unknown"))
                team_abbreviation = competitor.get("abbreviation", "")
                
                # Extract standings statistics
                points = team.get("points", 0)
                played = team.get("played", 0)
                wins = team.get("win", 0)
                draws = team.get("draw", 0)
                losses = team.get("loss", 0)
                goals_for = team.get("goals_for", 0)
                goals_against = team.get("goals_against", 0)
                goals_diff = team.get("goals_diff", 0)
                current_outcome = team.get("current_outcome", "")
                
                # Extract additional info
                form = competitor.get("form", "")
                points_per_game = team.get("points_per_game", 0)
                
                # Build summary string
                summary_parts = []
                
                # Main info: Rank, Team, Points
                summary_parts.append(f"#{rank} {team_name} ({team_abbreviation})")
                summary_parts.append(f"Pts: {points}")
                
                # Record
                summary_parts.append(f"{played}J ({wins}V {draws}E {losses}D)")
                
                # Goals
                summary_parts.append(f"G: {goals_for}-{goals_against} ({goals_diff:+d})")
                
                # Classification zone if available
                if current_outcome:
                    summary_parts.append(f"Zone: {current_outcome}")
                
                # Form if available
                if form:
                    summary_parts.append(f"Form: {form}")
                
                # Average points per game
                if points_per_game:
                    summary_parts.append(f"PPG: {points_per_game:.2f}")
                
                standings_summary.append(" | ".join(summary_parts))
                
            except Exception as e:
                print(f"[ERROR] Failed to process team standing: {str(e)}")
                continue
        
        return standings_summary
    
    def summarize_leaders(leaders_data):
        """Summarize season leaders to concise docs for LLM grouped by player, team and stats."""
        leaders_summary = []
        
        # Validate input
        if leaders_data is None:
            print(f"[DEBUG] summarize_leaders: leaders_data is None")
            return leaders_summary
        
        # Handle both array format (new) and dict format (legacy)
        lists = []
        
        if isinstance(leaders_data, list):
            # New format: leaders_data is directly an array of list objects
            lists = leaders_data
            print(f"[DEBUG] summarize_leaders: leaders_data is array format with {len(lists)} items")
        elif isinstance(leaders_data, dict):
            # Legacy format: leaders_data is a dict with "lists" property
            lists = leaders_data.get("lists", [])
            print(f"[DEBUG] summarize_leaders: leaders_data is dict format with {len(lists)} lists")
        else:
            print(f"[DEBUG] summarize_leaders: leaders_data is neither list nor dict, type: {type(leaders_data)}")
            return leaders_summary
        
        if not isinstance(lists, list) or len(lists) == 0:
            print(f"[DEBUG] summarize_leaders: lists is empty or not a list")
            return leaders_summary
        
        # Process each leader list (usually one per stat type)
        for list_obj in lists:
            try:
                if not isinstance(list_obj, dict):
                    continue
                
                leaders = list_obj.get("leaders", [])
                if not isinstance(leaders, list):
                    continue
                
                # Process each leader ranking
                for leader in leaders:
                    if not isinstance(leader, dict):
                        continue
                    
                    rank = leader.get("rank", "")
                    players = leader.get("players", [])
                    
                    if not isinstance(players, list):
                        continue
                    
                    # Process each player in this ranking
                    for player in players:
                        if not isinstance(player, dict):
                            continue
                        
                        player_name = player.get("name", "Unknown")
                        competitors = player.get("competitors", [])
                        
                        if not isinstance(competitors, list):
                            continue
                        
                        # Process each competitor (team) for this player
                        for competitor in competitors:
                            if not isinstance(competitor, dict):
                                continue
                            
                            team_name = normalize_team_name(competitor.get("name", "Unknown"))
                            team_abbreviation = competitor.get("abbreviation", "")
                            datapoints = competitor.get("datapoints", [])
                            
                            # Extract stats from datapoints
                            stats_parts = []
                            if isinstance(datapoints, list):
                                for datapoint in datapoints:
                                    if isinstance(datapoint, dict):
                                        stat_type = datapoint.get("type", "")
                                        stat_value = datapoint.get("value", 0)
                                        if stat_type:
                                            stats_parts.append(f"{stat_type}: {stat_value}")
                            
                            # Build summary string: Rank - Player - Team - Stats
                            summary_parts = []
                            
                            if rank:
                                summary_parts.append(f"#{rank}")
                            
                            summary_parts.append(player_name)
                            summary_parts.append(f"{team_name} ({team_abbreviation})")
                            
                            if stats_parts:
                                summary_parts.append(" | ".join(stats_parts))
                            
                            leaders_summary.append(" - ".join(summary_parts))
                
            except Exception as e:
                print(f"[ERROR] Failed to process leaders: {str(e)}")
                continue
        
        return leaders_summary
    
    def summarize_markets(markets_parsed):
        """Summarize markets-parsed to concise docs for LLM."""
        markets_docs = []
        
        if not isinstance(markets_parsed, list):
            return markets_docs
        
        for market in markets_parsed:
            if not isinstance(market, dict):
                continue
            
            # Extract key fields for summary (using correct field names from markets-parsed)
            market_name = market.get("market_name", "Unknown Market")
            event_title = market.get("event_title", "")
            options = market.get("options", [])
            market_type = market.get("market_type", "")
            
            # Create a concise summary
            doc = {
                "name": market_name,
                "event": event_title,
                "type": market_type,
                "selections_count": len(options) if isinstance(options, list) else 0
            }
            
            # Add selection details if available
            if isinstance(options, list) and len(options) > 0:
                selections = []
                for opt in options[:5]:  # Limit to first 5
                    if isinstance(opt, dict):
                        opt_name = opt.get("name", "")
                        opt_odds = opt.get("odds", "")
                        if opt_name:
                            # Include odds if available
                            if opt_odds:
                                selections.append(f"{opt_name} ({opt_odds})")
                            else:
                                selections.append(opt_name)
                
                if selections:
                    doc["selections"] = selections
            
            markets_docs.append(doc)
        
        return markets_docs

    def summarize_articles(content_articles):
        """
        Summarize content-articles to compact strings for LLM.
        Expected shape (best-effort):
          {
            'title': str,
            'subtitle': str (optional),
            'slug': str (optional),
            'execution': datetime/str (optional),
            'metadata': {'article_type': str, 'language': str, 'event_code': str, ...}
          }
        """
        summaries = []
        if not isinstance(content_articles, list):
            return summaries

        for article in content_articles[:10]:
            if not isinstance(article, dict):
                continue

            title = article.get("title") or article.get("headline") or article.get("name") or "Matéria"
            subtitle = article.get("subtitle") or article.get("summary") or ""
            slug = article.get("slug") or ""
            metadata = article.get("metadata", {}) if isinstance(article.get("metadata", {}), dict) else {}
            article_type = metadata.get("article_type") or metadata.get("type") or ""

            parts = [str(title).strip()]
            if subtitle:
                parts.append(str(subtitle).strip())
            if article_type:
                parts.append(f"tipo: {article_type}")
            if slug:
                parts.append(f"slug: {slug}")

            summaries.append(" | ".join([p for p in parts if p]))

        return summaries

    def build_articles_objects(content_articles):
        """
        Build UI widget objects for content-articles.
        Mirrors the shape used in assistant-tools/tools/find-insights.yml (articles-parsed).
        """
        objects = []
        if not isinstance(content_articles, list):
            return objects

        for index, article in enumerate(content_articles[:5]):
            if not isinstance(article, dict):
                continue

            metadata = article.get("metadata", {}) if isinstance(article.get("metadata", {}), dict) else {}
            objects.append({
                # Common/id fields
                "article_id": article.get("article_id") or article.get("_id") or article.get("id"),
                "article_index": article.get("article_index", index),
                # Display fields
                "image_path": article.get("image_path", ""),
                "title": article.get("title", ""),
                "subtitle": article.get("subtitle", ""),
                "slug": article.get("slug", ""),
                # Metadata passthrough
                "metadata": metadata,
            })

        return objects
    
    # Main function logic
    try:
        params = request_data.get("params", {})
        last_user_msg = params.get("last_user_msg", {})
        
        # Get timezone parameter (default: 'br' for Brazil)
        timezone_code = params.get("timezone", "br").lower()
        if timezone_code not in TIMEZONE_MAP:
            timezone_code = "br"
        tz_name, tz_offset = TIMEZONE_MAP[timezone_code]
        
        # Get loaded events and markets from params (passed from workflow)
        played_events = params.get("played_events", [])
        fixture_events = params.get("fixture_events", [])
        head_to_head_events = params.get("head_to_head_events", [])
        next_events = params.get("next_events", [])
        content_articles = params.get("content_articles", [])
        markets_docs = params.get("markets_docs", [])
        markets_parsed = params.get("markets_parsed", [])
        season_standings = params.get("season_standings", [])
        leaders_data = params.get("leaders_data", {})
        
        if not isinstance(last_user_msg, dict):
            return {
                "status": False,
                "error": "Invalid last_user_msg: expected dict",
                "data": {
                    "matched_teams_summary": [],
                    "fixture_events_summary": [],
                    "played_events_summary": [],
                    "head_to_head_events_summary": [],
                    "next_events_summary": [],
                    "content_articles_summary": [],
                    "season_standings_summary": [],
                    "season_leaders_summary": [],
                    "faq_docs": [],
                    "insights_docs": [],
                    "markets_docs": [],
                    "markets_objects": [],
                    "websearch_docs": [],
                    "game_schedule": None,
                    "context_summary": "",
                    "user_question": ""
                }
            }
        
        # Summarize matched teams
        matched_teams_summary = summarize_teams(last_user_msg.get("matched-teams", []))
        
        # Summarize events (use loaded events if available, fallback to message data for backward compatibility)
        # Pass timezone offset to all summarize_events calls
        fixture_events_summary = summarize_events(fixture_events if fixture_events else last_user_msg.get("fixture-events", []), tz_offset)
        played_events_summary = summarize_events(played_events if played_events else last_user_msg.get("played-events", []), tz_offset)
        head_to_head_events_summary = summarize_events(head_to_head_events if head_to_head_events else last_user_msg.get("head-to-head-events", []), tz_offset)
        next_events_summary = summarize_events(next_events if next_events else last_user_msg.get("next-events", []), tz_offset)

        # Summarize related content-articles (if provided)
        content_articles_summary = summarize_articles(content_articles)
        articles_objects = build_articles_objects(content_articles)
        
        # Pass through already-summarized docs
        faq_docs = last_user_msg.get("faq-docs", [])
        insights_docs = last_user_msg.get("insights-docs", [])
        websearch_docs = last_user_msg.get("websearch-docs", [])
        game_schedule = last_user_msg.get("game-schedule", None)
        
        # Create compact context (summary + user question) for token efficiency
        context_summary = last_user_msg.get("reasoning", {}).get("short_message", "")
        user_question = last_user_msg.get("content", "")
        
        # Summarize standings by team
        try:
            season_standings_summary = summarize_standings(season_standings)
            print(f"[DEBUG] season_standings_summary generated with {len(season_standings_summary)} entries")
        except Exception as e:
            print(f"[ERROR] Failed to summarize standings: {str(e)}")
            season_standings_summary = []
        
        # Summarize leaders by player, team and stats
        try:
            season_leaders_summary = summarize_leaders(leaders_data)
            print(f"[DEBUG] season_leaders_summary generated with {len(season_leaders_summary)} entries")
        except Exception as e:
            print(f"[ERROR] Failed to summarize leaders: {str(e)}")
            season_leaders_summary = []
        
        # Flatten markets-parsed into individual market objects for UI widgets
        markets_objects = []
        for market in markets_parsed:
            if not isinstance(market, dict):
                continue
            
            market_name = market.get("market_name", "")
            market_type = market.get("market_type", "")
            market_id = market.get("market_id")
            event_id = market.get("event_id", "")
            event_title = market.get("event_title", "")
            options = market.get("options", [])
            
            # Create one object per option
            if isinstance(options, list):
                for option in options:
                    if isinstance(option, dict):
                        markets_objects.append({
                            "title": translate_market_title(market_name),
                            "runner": normalize_runner_name(option.get("name", "")),
                            "odds": option.get("odds"),
                            "market_type": market_type,
                            "market_id": market_id,
                            "option_id": option.get("id"),
                            "event_id": event_id,
                            "event_title": normalize_event_title(event_title)
                        })
        
        return {
            "status": True,
            "data": {
                "matched_teams_summary": matched_teams_summary,
                "fixture_events_summary": fixture_events_summary,
                "played_events_summary": played_events_summary,
                "head_to_head_events_summary": head_to_head_events_summary,
                "next_events_summary": next_events_summary,
                "content_articles_summary": content_articles_summary,
                "articles_objects": articles_objects,
                "season_standings_summary": season_standings_summary,
                "season_leaders_summary": season_leaders_summary,
                "faq_docs": faq_docs,
                "insights_docs": insights_docs,
                "markets_docs": markets_docs,
                "markets_objects": markets_objects,
                "websearch_docs": websearch_docs,
                "game_schedule": game_schedule,
                "context_summary": context_summary,
                "user_question": user_question
            }
        }
        
    except Exception as e:
        import traceback
        return {
            "status": False,
            "error": str(e),
            "message": f"Error summarizing message data: {str(e)}",
            "traceback": traceback.format_exc(),
            "data": {
                "matched_teams_summary": [],
                "fixture_events_summary": [],
                "played_events_summary": [],
                "head_to_head_events_summary": [],
                "next_events_summary": [],
                "content_articles_summary": [],
                "articles_objects": [],
                "season_standings_summary": [],
                "season_leaders_summary": [],
                "faq_docs": [],
                "insights_docs": [],
                "markets_docs": [],
                "markets_objects": [],
                "websearch_docs": [],
                "game_schedule": None,
                "context_summary": "",
                "user_question": ""
            }
        }

