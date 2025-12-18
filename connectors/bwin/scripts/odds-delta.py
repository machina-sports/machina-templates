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
        
    History format: Array of objects with structure:
        {
            "odds": 2.45,           # Decimal odds
            "var": 0.05,            # Decimal odds variation
            "us": 145,              # American odds (can be negative)
            "us_var": 10,           # American odds variation
            "ts": "2025-12-15T..."  # Timestamp (ISO 8601)
        }
    """
    from datetime import datetime
    
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
            print(f"📚 Existing doc found: {market_id}")
    
    # Process each current market
    updated_markets = []
    for market in current_markets:
        market_id = str(market.get("metadata", {}).get("market_id", ""))
        print(f"\n🔍 Processing market: {market_id}")
        
        # Find existing document for this market
        existing_doc = existing_lookup.get(market_id)
        print(f"   {'✓ Found existing doc' if existing_doc else '✗ No existing doc (new market)'}")
        
        # Process options in the market
        options = market.get("options", [])
        updated_options = []
        
        for option in options:
            option_id = option.get("id")
            price = option.get("price", {})
            current_odds = price.get("odds", 0)
            current_us_odds = price.get("usOdds", None)
            
            # Find matching option in existing document and copy its history
            existing_history = []
            previous_odds = None
            previous_us_odds = None
            
            if existing_doc:
                existing_options = existing_doc.get("value", {}).get("options", [])
                for existing_option in existing_options:
                    if existing_option.get("id") == option_id:
                        # Copy the entire existing history
                        existing_history = existing_option.get("history", [])
                        if existing_history and len(existing_history) > 0:
                            last_entry = existing_history[-1]
                            # Handle both old array format and new object format
                            if isinstance(last_entry, dict):
                                previous_odds = last_entry.get("odds")
                                previous_us_odds = last_entry.get("us") or last_entry.get("us_odds")  # Support old key
                            elif isinstance(last_entry, list):
                                # Legacy format: [odds, variation, timestamp, usOdds]
                                previous_odds = last_entry[0] if len(last_entry) > 0 else None
                                previous_us_odds = last_entry[3] if len(last_entry) > 3 else None
                        print(f"Market {market_id} | Option {option_id} | Existing: {len(existing_history)} | Last odds: {previous_odds} ({previous_us_odds})")
                        break
            
            # Calculate variations
            if previous_odds is not None:
                odds_variation = round(current_odds - previous_odds, 2)
            else:
                odds_variation = 0
                print(f"Market {market_id} | Option {option_id} | First entry | Odds: {current_odds} ({current_us_odds})")
            
            # Calculate American odds variation
            if previous_us_odds is not None and current_us_odds is not None:
                us_odds_variation = current_us_odds - previous_us_odds
            else:
                us_odds_variation = 0
            
            # Start with existing history
            new_history = list(existing_history)
            timestamp = datetime.utcnow().isoformat()
            
            # Only save to history if there's a variation OR it's the first entry
            is_first_entry = len(existing_history) == 0
            has_variation = odds_variation != 0 or us_odds_variation != 0
            
            if is_first_entry or has_variation:
                new_entry = {
                    "odds": current_odds,
                    "var": odds_variation,
                    "us": current_us_odds,
                    "us_var": us_odds_variation,
                    "ts": timestamp
                }
                
                new_history.append(new_entry)
                
                # Keep only last 100 entries
                if len(new_history) > 100:
                    new_history = new_history[-100:]
                
                us_odds_str = f"{current_us_odds} ({int(us_odds_variation):+d})" if current_us_odds is not None else "None"
                print(f"Market {market_id} | Option {option_id} | ✅ SAVED: odds={current_odds} ({odds_variation:+.2f}) | us_odds={us_odds_str} | Total: {len(new_history)}")
            else:
                us_odds_str = f"{current_us_odds}" if current_us_odds is not None else "None"
                print(f"Market {market_id} | Option {option_id} | ⏭️  SKIPPED (no change): odds={current_odds} | us_odds={us_odds_str} | Total: {len(new_history)}")
            
            # Set the history on the option
            option["history"] = new_history
            
            updated_options.append(option)
        
        # Update market with processed options
        market["options"] = updated_options
        
        # Add version control
        existing_version_control = {}
        if existing_doc:
            existing_version_control = existing_doc.get("value", {}).get("version_control", {})
        
        update_count = existing_version_control.get("update_count", 0) + 1
        market["version_control"] = {
            **existing_version_control,
            "update_count": update_count,
            "last_updated": datetime.utcnow().isoformat(),
            "last_sync_status": "completed"
        }
        
        print(f"   ✅ Market {market_id} | Update count: {update_count} | Options: {len(market.get('options', []))}")
        updated_markets.append(market)
    
    print(f"Processed {len(updated_markets)} markets")
    
    return {
        "status": True,
        "data": {
            "markets": updated_markets,
            "processed_count": len(updated_markets)
        }
    }

