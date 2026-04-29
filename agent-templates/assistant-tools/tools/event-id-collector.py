"""
Event ID Collector Tool
Collects and combines event IDs from different sources in a message.
Generic tool that can be used across different assistant workflows.
"""


def collect_all_event_ids(request_data):
    """
    Collect all event IDs from fixture, played, and next event IDs.
    
    Args:
        request_data: Dictionary containing:
            - params: Dictionary with parameters
                - last_user_msg: The last user message containing event ID lists
        
    Returns:
        Dictionary with status, message, and data containing combined event IDs
    """
    try:
        # Extract params from request_data
        params = request_data.get("params", {})
        last_user_msg = params.get("last_user_msg", {})
        
        if not last_user_msg:
            return {
                "status": True,
                "message": "No user message provided",
                "data": {
                    "all_event_ids": [],
                    "has_event_ids": False,
                    "total_event_ids": 0
                }
            }
        
        # Extract event ID lists
        fixture_ids = last_user_msg.get('fixture-event-ids', [])
        played_ids = last_user_msg.get('played-event-ids', [])
        next_ids = last_user_msg.get('next-event-ids', [])
        head_to_head_ids = last_user_msg.get('head-to-head-event-ids', [])
        
        # Combine all event IDs
        all_event_ids = fixture_ids + played_ids + next_ids + head_to_head_ids
        
        # Check if any event IDs exist
        has_event_ids = (
            len(fixture_ids) > 0 or 
            len(played_ids) > 0 or 
            len(next_ids) > 0 or
            len(head_to_head_ids) > 0
        )
        
        # Check if head-to-head events exist (for specific team match filtering)
        has_head_to_head = len(head_to_head_ids) > 0
        
        return {
            "status": True,
            "message": "Event IDs collected successfully",
            "data": {
                "all_event_ids": all_event_ids,
                "has_event_ids": has_event_ids,
                "has_head_to_head": has_head_to_head,
                "total_event_ids": len(all_event_ids)
            }
        }
    
    except Exception as e:
        return {
            "status": False,
            "error": str(e),
            "message": f"Error collecting event IDs: {str(e)}",
            "data": {
                "all_event_ids": [],
                "has_event_ids": False,
                "total_event_ids": 0
            }
        }

