def format_event_summaries(request_data):
    """
    Format event value objects into concise string summaries.
    Expects events as value objects (not full document structure).
    """
    from datetime import datetime, timezone, timedelta
    
    def format_datetime(datetime_str):
        """Format datetime: 2025-12-07T19:00:00Z -> 07/12 16:00 (UTC to GMT-3)"""
        if not datetime_str:
            return None
        try:
            # Handle formats like "2025-12-07ZT19:00:00Z" (fix double T)
            datetime_str = datetime_str.replace("ZT", "T")
            
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
                if "T" in datetime_str:
                    date_part = datetime_str.split("T")[0]
                    dt = datetime.fromisoformat(date_part)
                    return dt.strftime("%d/%m")
            except:
                pass
            return None
    
    def format_summary(value):
        """Format: Home vs Away | Competition | Date Time | Status | Score | Channel"""
        try:
            if not isinstance(value, dict):
                return None
            
            # Extract teams
            competitors = value.get("sport:competitors", [])
            if not isinstance(competitors, list):
                return None
            
            home = next((c.get("name") for c in competitors if isinstance(c, dict) and c.get("sport:qualifier") == "home"), None)
            away = next((c.get("name") for c in competitors if isinstance(c, dict) and c.get("sport:qualifier") == "away"), None)
            
            if not home or not away:
                return None
            
            parts = [f"{home} vs {away}"]
            
            # Competition
            competition_obj = value.get("sport:competition", {})
            competition = competition_obj.get("name") if isinstance(competition_obj, dict) else None
            if competition:
                parts.append(competition)
            
            # Date/Time
            start_date = value.get("schema:startDate")
            date_time = format_datetime(start_date) if start_date else None
            if date_time:
                parts.append(date_time)
            
            # Status
            status = value.get("sport:status", "Fixture")
            if status:
                parts.append(str(status))
            
            # Score
            score = value.get("sport:score", {})
            if isinstance(score, dict) and score.get("sport:homeScore") is not None:
                parts.append(f"{score.get('sport:homeScore')}-{score.get('sport:awayScore')}")
            
            # Channel (for fixtures)
            channels = value.get("sport:channels", [])
            if isinstance(channels, list) and len(channels) > 0:
                channel = channels[0]
                if isinstance(channel, dict):
                    channel_name = channel.get("sport:channelName")
                    if channel_name:
                        parts.append(f"📺 {channel_name}")
            
            return " | ".join(parts)
        except:
            return None
    
    try:
        if not isinstance(request_data, dict):
            return {
                "status": False,
                "error": "Invalid request_data: expected dict",
                "data": {
                    "event_summaries": []
                }
            }
        
        params = request_data.get("params", {})
        if not isinstance(params, dict):
            return {
                "status": False,
                "error": "Invalid params: expected dict",
                "data": {
                    "event_summaries": []
                }
            }
        
        events = params.get("events", [])
        if not isinstance(events, list):
            return {
                "status": False,
                "error": f"Invalid events: expected list, got {type(events).__name__}",
                "data": {
                    "event_summaries": []
                }
            }
        
        if not events:
            return {
                "status": True,
                "data": {
                    "event_summaries": []
                }
            }
        
        event_summaries = []
        for event in events:
            if not isinstance(event, dict):
                continue
            
            summary = format_summary(event)
            if summary:
                event_summaries.append(summary)
        
        return {
            "status": True,
            "data": {
                "event_summaries": event_summaries
            }
        }
        
    except Exception as e:
        import traceback
        return {
            "status": False,
            "error": str(e),
            "message": f"Error formatting event summaries: {str(e)}",
            "traceback": traceback.format_exc(),
            "data": {
                "event_summaries": []
            }
        }


def prepare_event_summaries(request_data):
    """
    Prepare event summaries separated by Played/Fixture status.
    Formats summaries concisely.
    """
    from datetime import datetime, timezone, timedelta
    
    def format_datetime(datetime_str):
        """Format datetime: 2025-12-07T19:00:00Z -> 07/12 16:00 (UTC to GMT-3)"""
        if not datetime_str:
            return None
        try:
            # Handle formats like "2025-12-07ZT19:00:00Z" (fix double T)
            datetime_str = datetime_str.replace("ZT", "T")
            
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
                if "T" in datetime_str:
                    date_part = datetime_str.split("T")[0]
                    dt = datetime.fromisoformat(date_part)
                    return dt.strftime("%d/%m")
            except:
                pass
            return None
    
    def format_summary(value):
        """Format: Home vs Away | Competition | Date Time | Status | Score | Channel"""
        try:
            if not isinstance(value, dict):
                return None
            
            # Extract teams
            competitors = value.get("sport:competitors", [])
            if not isinstance(competitors, list):
                return None
            
            home = next((c.get("name") for c in competitors if isinstance(c, dict) and c.get("sport:qualifier") == "home"), None)
            away = next((c.get("name") for c in competitors if isinstance(c, dict) and c.get("sport:qualifier") == "away"), None)
            
            if not home or not away:
                return None
            
            parts = [f"{home} vs {away}"]
            
            # Competition
            competition_obj = value.get("sport:competition", {})
            competition = competition_obj.get("name") if isinstance(competition_obj, dict) else None
            if competition:
                parts.append(competition)
            
            # Date/Time
            start_date = value.get("schema:startDate")
            date_time = format_datetime(start_date) if start_date else None
            if date_time:
                parts.append(date_time)
            
            # Status
            status = value.get("sport:status", "Fixture")
            if status:
                parts.append(str(status))
            
            # Score
            score = value.get("sport:score", {})
            if isinstance(score, dict) and score.get("sport:homeScore") is not None:
                parts.append(f"{score.get('sport:homeScore')}-{score.get('sport:awayScore')}")
            
            # Channel (for fixtures)
            channels = value.get("sport:channels", [])
            if isinstance(channels, list) and len(channels) > 0:
                channel = channels[0]
                if isinstance(channel, dict):
                    channel_name = channel.get("sport:channelName")
                    if channel_name:
                        parts.append(f"📺 {channel_name}")
            
            return " | ".join(parts)
        except:
            return None
    
    try:
        if not isinstance(request_data, dict):
            return {
                "status": False,
                "error": "Invalid request_data: expected dict",
                "data": {
                    "found_events_docs": []
                }
            }
        
        params = request_data.get("params", {})
        if not isinstance(params, dict):
            return {
                "status": False,
                "error": "Invalid params: expected dict",
                "data": {
                    "found_events_docs": []
                }
            }
        
        team_events = params.get("team_events", [])
        if not isinstance(team_events, list):
            return {
                "status": False,
                "error": f"Invalid team_events: expected list, got {type(team_events).__name__}",
                "data": {
                    "played_events": [],
                    "fixture_events": [],
                    "found_events_docs": []
                }
            }
        
        if not team_events:
            return {
                "status": True,
                "data": {
                    "played_events": [],
                    "fixture_events": [],
                    "found_events_docs": []
                }
            }
        
        played_events = []
        fixture_events = []
        
        for event in team_events:
            if not isinstance(event, dict):
                continue
            
            value = event.get("value", {})
            if not isinstance(value, dict):
                continue
            
            status = str(value.get("sport:status", "")).lower()
            score = value.get("sport:score", {})
            has_score = isinstance(score, dict) and score.get("sport:homeScore") is not None
            
            summary = format_summary(value)
            if not summary:
                continue
            
            if status in ["played", "closed", "complete", "finished"] or has_score:
                played_events.append(summary)
            else:
                fixture_events.append(summary)
        
        # Combine for backward compatibility
        found_events_docs = played_events + fixture_events
        
        return {
            "status": True,
            "data": {
                "played_events": played_events,
                "fixture_events": fixture_events,
                "found_events_docs": found_events_docs
            }
        }
        
    except Exception as e:
        import traceback
        return {
            "status": False,
            "error": str(e),
            "message": f"Error preparing event summaries: {str(e)}",
            "traceback": traceback.format_exc(),
            "data": {
                "played_events": [],
                "fixture_events": [],
                "found_events_docs": []
            }
        }

