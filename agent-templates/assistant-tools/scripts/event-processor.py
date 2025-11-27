def collect_fixture_ids(request_data):
    """
    Collect @id values from fixture and head-to-head events.
    Returns a flat list of event IDs for filtering.
    """
    try:
        if not isinstance(request_data, dict):
            return {
                "status": False,
                "error": "Invalid request_data: expected dict",
                "data": {
                    "fixture_event_ids": []
                }
            }
        
        params = request_data.get("params", {})
        if not isinstance(params, dict):
            return {
                "status": False,
                "error": "Invalid params: expected dict",
                "data": {
                    "fixture_event_ids": []
                }
            }
        
        fixture_events = params.get("fixture_events", [])
        head_to_head_events = params.get("head_to_head_events", [])
        
        if not isinstance(fixture_events, list):
            fixture_events = []
        if not isinstance(head_to_head_events, list):
            head_to_head_events = []
        
        # Collect all @id values
        fixture_event_ids = []
        
        for event in fixture_events + head_to_head_events:
            if isinstance(event, dict):
                event_id = event.get("@id")
                if event_id:
                    fixture_event_ids.append(event_id)
        
        return {
            "status": True,
            "data": {
                "fixture_event_ids": fixture_event_ids
            }
        }
        
    except Exception as e:
        import traceback
        return {
            "status": False,
            "error": str(e),
            "message": f"Error collecting fixture IDs: {str(e)}",
            "traceback": traceback.format_exc(),
            "data": {
                "fixture_event_ids": []
            }
        }


def process_team_events(request_data):
    """
    Process team events to extract head-to-head matches and separate by played/fixture status.
    
    - If exactly 2 team_ids: filter events where both teams face each other
    - Otherwise: use all events
    - Separate into played_events and fixture_events based on status
    - Apply limits to played and fixture events (from reasoning)
    """
    
    def is_head_to_head(event_value, team_ids):
        """Check if event contains both teams as competitors"""
        if not isinstance(event_value, dict):
            return False
        
        competitors = event_value.get("sport:competitors", [])
        if not isinstance(competitors, list):
            return False
        
        # Extract competitor IDs
        competitor_ids = []
        for comp in competitors:
            if isinstance(comp, dict):
                comp_id = comp.get("@id")
                if comp_id:
                    competitor_ids.append(comp_id)
        
        # Check if both team_ids are in competitors
        return all(team_id in competitor_ids for team_id in team_ids)
    
    def is_played_event(event_value):
        """Determine if event is played based on status or score"""
        if not isinstance(event_value, dict):
            return False
        
        # Check status
        status = str(event_value.get("sport:status", "")).lower()
        if status in ["played", "closed", "complete", "finished"]:
            return True
        
        # Check if has score
        score = event_value.get("sport:score", {})
        if isinstance(score, dict) and score.get("sport:homeScore") is not None:
            return True
        
        return False
    
    try:
        if not isinstance(request_data, dict):
            return {
                "status": False,
                "error": "Invalid request_data: expected dict",
                "data": {
                    "played_events": [],
                    "fixture_events": [],
                    "head_to_head_events": []
                }
            }
        
        params = request_data.get("params", {})
        if not isinstance(params, dict):
            return {
                "status": False,
                "error": "Invalid params: expected dict",
                "data": {
                    "played_events": [],
                    "fixture_events": [],
                    "head_to_head_events": []
                }
            }
        
        team_events_parsed = params.get("team_events_parsed", [])
        team_ids = params.get("team_ids", [])
        limit_played_events = params.get("limit_played_events", 3)
        limit_fixture_events = params.get("limit_fixture_events", 3)
        
        # Ensure limits are integers
        if not isinstance(limit_played_events, int):
            try:
                limit_played_events = int(limit_played_events)
            except (ValueError, TypeError):
                limit_played_events = 3
        
        if not isinstance(limit_fixture_events, int):
            try:
                limit_fixture_events = int(limit_fixture_events)
            except (ValueError, TypeError):
                limit_fixture_events = 3
        
        if not isinstance(team_events_parsed, list):
            return {
                "status": False,
                "error": f"Invalid team_events_parsed: expected list, got {type(team_events_parsed).__name__}",
                "data": {
                    "played_events": [],
                    "fixture_events": [],
                    "head_to_head_events": []
                }
            }
        
        if not isinstance(team_ids, list):
            return {
                "status": False,
                "error": f"Invalid team_ids: expected list, got {type(team_ids).__name__}",
                "data": {
                    "played_events": [],
                    "fixture_events": [],
                    "head_to_head_events": []
                }
            }
        
        # If empty, return empty results
        if not team_events_parsed:
            return {
                "status": True,
                "data": {
                    "played_events": [],
                    "fixture_events": [],
                    "head_to_head_events": []
                }
            }
        
        # Filter for head-to-head if exactly 2 teams
        events_to_process = team_events_parsed
        head_to_head_events = []
        
        if len(team_ids) == 2:
            head_to_head_events = [
                event for event in team_events_parsed 
                if is_head_to_head(event, team_ids)
            ]
        
        # Separate into played and fixture
        played_events = []
        fixture_events = []
        
        for event in events_to_process:
            if not isinstance(event, dict):
                continue
            
            if is_played_event(event):
                played_events.append(event)
            else:
                fixture_events.append(event)
        
        # Apply limits (most recent played events, earliest upcoming fixture events)
        # Played events are already sorted by date descending (most recent first)
        # Fixture events need the earliest ones (sorted ascending by date)
        limited_played_events = played_events[:limit_played_events] if limit_played_events > 0 else played_events
        limited_fixture_events = fixture_events[:limit_fixture_events] if limit_fixture_events > 0 else fixture_events
        
        return {
            "status": True,
            "data": {
                "played_events": limited_played_events,
                "fixture_events": limited_fixture_events,
                "head_to_head_events": head_to_head_events,
                "debug_info": {
                    "total_played_before_limit": len(played_events),
                    "total_fixture_before_limit": len(fixture_events),
                    "limit_played_events": limit_played_events,
                    "limit_fixture_events": limit_fixture_events,
                    "played_events_returned": len(limited_played_events),
                    "fixture_events_returned": len(limited_fixture_events)
                }
            }
        }
        
    except Exception as e:
        import traceback
        return {
            "status": False,
            "error": str(e),
            "message": f"Error processing team events: {str(e)}",
            "traceback": traceback.format_exc(),
            "data": {
                "played_events": [],
                "fixture_events": [],
                "head_to_head_events": []
            }
        }


