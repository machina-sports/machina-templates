def invoke_combine(request_data):
    """
    Combines search queries from Team B and Team A prompts into a single list.
    
    Args:
        request_data: Dictionary containing params
            params:
                - search_queries_team_b: List of search queries for Team B (optional)
                - search_queries_team_a: List of search queries for Team A (optional)
    
    Returns:
        Dictionary with status, data (containing combined search_queries), and message
    """
    
    params = request_data.get("params", {})
    
    search_queries_team_b = params.get("search_queries_team_b", [])
    search_queries_team_a = params.get("search_queries_team_a", [])
    
    # Ensure both are lists
    if not isinstance(search_queries_team_b, list):
        search_queries_team_b = []
    if not isinstance(search_queries_team_a, list):
        search_queries_team_a = []
    
    # Combine the lists
    combined_queries = (search_queries_team_b or []) + (search_queries_team_a or [])
    
    return {
        "status": True,
        "data": {
            "search_queries": combined_queries
        },
        "message": f"Successfully combined {len(combined_queries)} search queries."
    }

