def invoke_build_parlay(request_data):
    """
    Builds parlay combinations that reach target odd
    
    Input:
        - available_runners: list of market runners
        - target_odd: desired total odd
        - max_legs: maximum legs in parlay (default: 5)
        - tolerance: % tolerance for target (default: 0.20 = 20%)
    
    Output:
        - parlay_combinations: list of combinations
        - Each combination has: runners, total_odd, leg_count
    """
    
    params = request_data.get("params", {})
    runners = params.get("available-runners", [])
    target_odd = params.get("target-odd", 10.0)
    max_legs = params.get("max-legs", 5)
    tolerance = params.get("tolerance", 0.20)
    
    if not runners or len(runners) == 0:
        return {
            "status": False,
            "message": "No runners available for parlay building",
            "data": {
                "parlay-combinations": [],
                "target-odd": target_odd,
                "combinations-found": 0
            }
        }
    
    # Filter runners with valid prices
    valid_runners = [r for r in runners if 'price' in r and r['price'] > 1.0]
    
    if not valid_runners:
        return {
            "status": False,
            "message": "No valid runners with prices available",
            "data": {
                "parlay-combinations": [],
                "target-odd": target_odd,
                "combinations-found": 0
            }
        }
    
    # Sort runners by price (ascending) for better algorithm performance
    sorted_runners = sorted(valid_runners, key=lambda r: r.get('price', 1))
    
    combinations = []
    target_min = target_odd * (1 - tolerance)
    target_max = target_odd * (1 + tolerance)
    
    def calculate_combination(selected, current_odd, remaining_runners, depth):
        """Recursive function to find valid parlay combinations"""
        
        # Base cases
        if depth > max_legs:
            return
        
        # Limit number of combinations to avoid performance issues
        if len(combinations) >= 50:
            return
        
        # Check if current combination is valid
        if depth >= 2 and target_min <= current_odd <= target_max:
            combinations.append({
                'runners': selected.copy(),
                'total_odd': round(current_odd, 2),
                'leg_count': len(selected)
            })
        
        # Pruning: if already too high, no point continuing this branch
        if current_odd > target_max * 1.5:
            return
        
        # Try adding more runners
        for i, runner in enumerate(remaining_runners):
            new_odd = current_odd * runner.get('price', 1)
            
            # Prune: if multiplying would exceed maximum too much
            if new_odd > target_max * 2:
                continue
            
            # Diversification: avoid same event (check event-id)
            event_ids = [r.get('event-id') for r in selected if 'event-id' in r]
            runner_event_id = runner.get('event-id')
            
            # For single-event parlays, allow multiple markets from same event
            # For multi-event parlays, avoid duplicate events
            if runner_event_id and len(set(event_ids)) > 1 and runner_event_id in event_ids:
                continue
            
            # Diversification: avoid too many of the same market type
            market_types = [r.get('marketType') for r in selected]
            runner_market_type = runner.get('marketType')
            if market_types.count(runner_market_type) >= 2:  # Max 2 of same type
                continue
            
            calculate_combination(
                selected + [runner],
                new_odd,
                remaining_runners[i+1:],
                depth + 1
            )
    
    # Start recursion
    calculate_combination([], 1.0, sorted_runners, 0)
    
    # Sort combinations by multiple criteria:
    # 1. Closest to target odd
    # 2. Prefer fewer legs (more likely to win)
    combinations.sort(key=lambda c: (
        abs(c['total_odd'] - target_odd),
        c['leg_count']
    ))
    
    # Return top combinations with formatted data
    top_combinations = []
    for combo in combinations[:5]:
        # Format runner info for better display
        formatted_runners = []
        for runner in combo['runners']:
            formatted_runners.append({
                'title': runner.get('title', ''),
                'name': runner.get('name', ''),
                'price': runner.get('price', 0),
                'marketType': runner.get('marketType', ''),
                'event-id': runner.get('event-id', ''),
                'market-id': runner.get('market-id', ''),
                'option-id': runner.get('option-id', '')
            })
        
        top_combinations.append({
            'runners': formatted_runners,
            'total_odd': combo['total_odd'],
            'leg_count': combo['leg_count'],
            'potential_return': round(combo['total_odd'] * 10, 2),  # Assuming R$10 stake
            'stake_suggestion': 10.0
        })
    
    return {
        "status": True,
        "message": f"Found {len(combinations)} parlay combinations (showing top 5)",
        "data": {
            "parlay-combinations": top_combinations,
            "target-odd": target_odd,
            "combinations-found": len(combinations),
            "best-combination": top_combinations[0] if top_combinations else None
        }
    }

