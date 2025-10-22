def invoke_map_markets(request_data):

    params = request_data.get("params", {})
    
    mapped_runners = params.get("mapped-runners", [])
    market_query = params.get("market-query", "").lower()
    sport_id = params.get("sport-id", "4")

    # Handle football (sport 4) selections
    if sport_id == "4" and market_query:
        
        # Group keywords
        is_3way = "3way" in market_query
        is_over_under = "over" in market_query or "under" in market_query
        is_handicap = "handicap" in market_query
        
        selected_market_runners = []
        fallback_runners = []
        
        for runner in mapped_runners:
            market_type = runner.get('marketType', '').lower()
            title = runner.get('title', '').lower()
            
            # Filter by market type group
            if is_3way and "3way" in market_type:
                fallback_runners.append(runner)
                # Prefer standard match results or 2UP, exclude time-specific and half results
                if "after" not in title and "half" not in title:
                    selected_market_runners.append(runner)
                    
            elif is_over_under and "over/under" in market_type:
                selected_market_runners.append(runner)
                
            elif is_handicap and "handicap" in market_type:
                selected_market_runners.append(runner)
        
        # If no clean markets found for 3way, use fallback
        if is_3way and len(selected_market_runners) == 0 and len(fallback_runners) > 0:
            selected_market_runners = fallback_runners
    
    elif market_query:
        # Generic filter for other sports
        selected_market_runners = [
            runner for runner in mapped_runners 
            if market_query in runner.get('marketType', '').lower()
        ]
    else:
        selected_market_runners = mapped_runners
    
    # Extract runner titles
    selected_market_runners_names = [
        runner.get('title') for runner in selected_market_runners
    ]

    return {
        "status": True,
        "message": "Mapped odds successfully.",
        "data": {
            "selected-market-runners": selected_market_runners,
            "selected-market-runners-names": selected_market_runners_names
        }
    }

