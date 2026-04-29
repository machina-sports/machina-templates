def invoke_map_markets(request_data):
    import re

    params = request_data.get("params", {})
    
    mapped_runners = params.get("mapped-runners", [])
    market_query = params.get("market-query", "").lower()
    sport_id = params.get("sport-id", "4")
    odd_from = params.get("odd-from")
    odd_to = params.get("odd-to")
    is_build_parlay = params.get("is-build-parlay", False)
    
    # Extract specific line from market_query (e.g., "over 2.5", "under 3,5")
    # Match patterns like "over 2.5", "under 3,5", "acima de 2.5", etc.
    line_match = re.search(r'(?:over|under|acima|abaixo)[\s]*(?:de)?[\s]*(\d+[.,]\d+)', market_query)
    specific_line = None
    if line_match:
        # Normalize to use comma (common in Portuguese odds display)
        specific_line = line_match.group(1).replace('.', ',')
        # Also keep dot version for matching
        specific_line_dot = line_match.group(1).replace(',', '.')

    # Handle football (sport 4) selections
    if sport_id == "4" and market_query:
        
        # Group keywords
        is_3way = "3way" in market_query or "vencedor" in market_query or "resultado" in market_query
        is_over_under = (
            "over" in market_query or 
            "under" in market_query or 
            "gols" in market_query or 
            "gol" in market_query or
            "goals" in market_query or
            "goal" in market_query
        )
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
                # If specific line is detected (e.g., "over 2.5"), filter by exact line match
                if specific_line:
                    # Check if title contains the specific line (with comma or dot)
                    if specific_line in title or specific_line_dot in title:
                        # Also filter by over/under direction if specified
                        if "over" in market_query and "over" in title:
                            selected_market_runners.append(runner)
                        elif "under" in market_query and "under" in title:
                            selected_market_runners.append(runner)
                        elif "acima" in market_query and "over" in title:
                            selected_market_runners.append(runner)
                        elif "abaixo" in market_query and "under" in title:
                            selected_market_runners.append(runner)
                else:
                    # No specific line, include all over/under markets
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
    
    # Filter by odds range if specified
    if odd_from is not None or odd_to is not None:
        # Each runner already has a direct 'price' field (not nested in options)
        filtered_runners = []
        for runner in selected_market_runners:
            if 'price' not in runner:
                continue
            
            price = runner['price']
            
            # Apply both filters if both are specified
            if odd_from is not None and odd_to is not None:
                if odd_from <= price <= odd_to:
                    filtered_runners.append(runner)
            # Apply only minimum filter
            elif odd_from is not None:
                if price >= odd_from:
                    filtered_runners.append(runner)
            # Apply only maximum filter
            elif odd_to is not None:
                if price <= odd_to:
                    filtered_runners.append(runner)
        
        # Sort filtered runners based on filter type
        if filtered_runners:
            # When only odd_to is specified (e.g., "abaixo de 2.50")
            # Sort DESCENDING to show odds closest to the upper limit first
            if odd_to is not None and odd_from is None:
                filtered_runners.sort(key=lambda r: r.get('price', 0), reverse=True)
            
            # When odd_from is specified (with or without odd_to)
            # Sort ASCENDING to show odds closest to the lower limit first
            else:
                filtered_runners.sort(key=lambda r: r.get('price', 0))
        
        selected_market_runners = filtered_runners
    
    # Apply parlay filtering if building combined bet
    if is_build_parlay and len(selected_market_runners) > 0:
        parlay_suitable_runners = []
        
        for runner in selected_market_runners:
            price = runner.get('price', 0)
            market_type = runner.get('marketType', '').lower()
            title = runner.get('title', '').lower()
            
            # Filter odds suitable for parlay (avoid very low or very high odds)
            if 1.3 <= price <= 10.0:
                # Exclude time-specific markets (not good for parlay)
                if "after" not in title and "half" not in title and "minute" not in title:
                    parlay_suitable_runners.append(runner)
        
        # Prioritize diverse market types for better parlay composition
        # Group by market type for later diversification
        market_type_groups = {}
        for runner in parlay_suitable_runners:
            market_type = runner.get('marketType', '')
            if market_type not in market_type_groups:
                market_type_groups[market_type] = []
            market_type_groups[market_type].append(runner)
        
        # Take top runners from each market type (diversification)
        diversified_runners = []
        max_per_type = 5  # Max 5 runners per market type
        
        for market_type, runners in market_type_groups.items():
            # Sort by price (prefer mid-range odds for parlay)
            sorted_runners = sorted(runners, key=lambda r: abs(r.get('price', 0) - 2.5))
            diversified_runners.extend(sorted_runners[:max_per_type])
        
        selected_market_runners = diversified_runners
    
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

