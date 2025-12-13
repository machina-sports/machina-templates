def calculate_odds_delta(request_data):
    """
    Calculate odds delta and maintain history for market options.
    
    Args:
        request_data (dict): Dictionary containing:
            - params (dict): Dictionary with:
                - current_markets (list): List of current market data from API
                - existing_documents (list): List of existing documents from DB
    
    Returns:
        dict: Updated markets with history arrays in each option
    """
    params = request_data.get("params", {})
    current_markets = params.get("current_markets", [])
    existing_documents = params.get("existing_documents", [])
    
    print(f"Processing {len(current_markets)} markets")
    print(f"Found {len(existing_documents)} existing docs")
    
    # Create a lookup dictionary for existing documents by market_id
    existing_lookup = {}
    for doc in existing_documents:
        market_id = doc.get("metadata", {}).get("market_id", "")
        if market_id:
            existing_lookup[str(market_id)] = doc
    
    # Process each current market
    updated_markets = []
    for market in current_markets:
        market_id = str(market.get("metadata", {}).get("market_id", ""))
        
        # Find existing document for this market
        existing_doc = existing_lookup.get(market_id)
        
        # Process options in the market
        options = market.get("options", [])
        updated_options = []
        
        for option in options:
            option_id = option.get("id")
            current_odds = option.get("price", {}).get("odds", 0)
            
            # Find matching option in existing document and copy its history
            existing_history = []
            previous_odds = None
            
            if existing_doc:
                existing_options = existing_doc.get("value", {}).get("options", [])
                for existing_option in existing_options:
                    if existing_option.get("id") == option_id:
                        # Copy the entire existing history
                        existing_history = existing_option.get("history", [])
                        if existing_history and len(existing_history) > 0:
                            previous_odds = existing_history[-1][0]
                        print(f"Market {market_id} | Option {option_id} | Existing: {len(existing_history)} | Last odds: {previous_odds}")
                        break
            
            # Calculate variation
            if previous_odds is not None:
                variation = round(current_odds - previous_odds, 2)
            else:
                variation = 0
                print(f"Market {market_id} | Option {option_id} | First entry | Current: {current_odds}")
            
            # Start with existing history, then append new entry
            new_history = list(existing_history)
            new_history.append([current_odds, variation])
            
            # Keep only last 100 entries
            if len(new_history) > 100:
                new_history = new_history[-100:]
            
            print(f"Market {market_id} | Option {option_id} | New entry: [{current_odds}, {variation}] | Total: {len(new_history)}")
            
            # Set the history on the option
            option["history"] = new_history
            
            updated_options.append(option)
        
        # Update market with processed options
        market["options"] = updated_options
        updated_markets.append(market)
    
    print(f"Processed {len(updated_markets)} markets")
    
    return {
        "status": True,
        "data": {
            "markets": updated_markets,
            "processed_count": len(updated_markets)
        }
    }

