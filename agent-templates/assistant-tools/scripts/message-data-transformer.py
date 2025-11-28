def summarize_message_data(request_data):
    """
    Transform all data in a user message to LLM-friendly summaries.
    Handles: matched-teams, fixture-events, played-events, head-to-head-events.
    Passes through: faq-docs, insights-docs, markets-docs, websearch-docs (already summarized).
    
    Args:
        request_data (dict): Request data containing:
            - params (dict):
                - last_user_msg (dict): The last user message object from thread
                - played_events (list): Loaded played event documents (optional)
                - fixture_events (list): Loaded fixture event documents (optional)
                - head_to_head_events (list): Loaded head-to-head event documents (optional)
    
    Returns:
        dict: Response containing summarized data ready for LLM consumption
    """
    from datetime import datetime, timezone, timedelta
    
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
    
    def format_datetime(datetime_str):
        """Format datetime: 2025-12-07T19:00:00Z -> 07/12 16:00 (UTC to GMT-3 for Brazil)"""
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
            
            # Convert UTC to GMT-3 (Brasília timezone)
            gmt_minus_3 = timezone(timedelta(hours=-3))
            dt_brasilia = dt.astimezone(gmt_minus_3)
            
            return dt_brasilia.strftime("%d/%m %H:%M")
            
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
    
    def format_event_summary(event):
        """Format event dict to: Home vs Away | Competition | Date Time | Status | Score | Channel"""
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
            
            # Date/Time (convert UTC to GMT-3 for Brazil)
            start_date = event.get("schema:startDate")
            if start_date:
                date_time = format_datetime(start_date)
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
                parts.append(f"{home_score}-{away_score}")
            
            # Channel (for fixtures)
            channels = event.get("sport:channels", [])
            if isinstance(channels, list) and len(channels) > 0:
                channel = channels[0]
                if isinstance(channel, dict):
                    channel_name = channel.get("sport:channelName")
                    if channel_name:
                        parts.append(f"📺 {channel_name}")
            
            return " | ".join(parts)
            
        except Exception:
            return None
    
    def summarize_events(events):
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
                summary = format_event_summary(event)
                if summary:
                    summaries.append(summary)
        
        return summaries
    
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
    
    # Main function logic
    try:
        params = request_data.get("params", {})
        last_user_msg = params.get("last_user_msg", {})
        
        # Get loaded events and markets from params (passed from workflow)
        played_events = params.get("played_events", [])
        fixture_events = params.get("fixture_events", [])
        head_to_head_events = params.get("head_to_head_events", [])
        next_events = params.get("next_events", [])
        markets_docs = params.get("markets_docs", [])
        markets_parsed = params.get("markets_parsed", [])
        
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
        fixture_events_summary = summarize_events(fixture_events if fixture_events else last_user_msg.get("fixture-events", []))
        played_events_summary = summarize_events(played_events if played_events else last_user_msg.get("played-events", []))
        head_to_head_events_summary = summarize_events(head_to_head_events if head_to_head_events else last_user_msg.get("head-to-head-events", []))
        next_events_summary = summarize_events(next_events if next_events else last_user_msg.get("next-events", []))
        
        # Pass through already-summarized docs
        faq_docs = last_user_msg.get("faq-docs", [])
        insights_docs = last_user_msg.get("insights-docs", [])
        websearch_docs = last_user_msg.get("websearch-docs", [])
        game_schedule = last_user_msg.get("game-schedule", None)
        
        # Create compact context (summary + user question) for token efficiency
        context_summary = last_user_msg.get("reasoning", {}).get("short_message", "")
        user_question = last_user_msg.get("content", "")
        
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
                            "title": market_name,
                            "runner": option.get("name", ""),
                            "odds": option.get("odds"),
                            "market_type": market_type,
                            "market_id": market_id,
                            "option_id": option.get("id"),
                            "event_id": event_id,
                            "event_title": event_title
                        })
        
        return {
            "status": True,
            "data": {
                "matched_teams_summary": matched_teams_summary,
                "fixture_events_summary": fixture_events_summary,
                "played_events_summary": played_events_summary,
                "head_to_head_events_summary": head_to_head_events_summary,
                "next_events_summary": next_events_summary,
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

