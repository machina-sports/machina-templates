def grep_nfl_markets(request_data):
    """
    Filter NFL markets from Bwin fixtures.
    Returns: Moneyline, Spread (Point Spread), Total (Total Points)
    
    Extracts exactly 3 markets per game:
    - 1 Moneyline (Money Line)
    - 1 Spread (Point Spread)
    - 1 Total (Total Points - preferring 45.5, 47.5, 44.5)
    """
    print("🔍 Filtering NFL markets...")
    
    params = request_data.get("params", {})
    fixtures = params.get("fixtures", [])
    
    # NFL Market Configuration
    NFL_CONFIG = {
        "moneyline": {
            "market_types": ["money line period y", "moneyline", "money line"],
            "periods": ["fulltime", "game", "match"]
        },
        "spread": {
            "market_types": ["handicap period y", "spread", "point spread"],
            "periods": ["fulltime", "game", "match"]
        },
        "total": {
            "market_types": ["over/under points period y", "total period y", "total points"],
            "periods": ["fulltime", "game", "match"],
            "preferred_values": ["45.5", "47.5", "44.5", "46.5", "48.5", "43.5", "43", "45", "47"]
        }
    }
    
    # Store one market per fixture per category
    market_by_fixture_category = {}
    
    for fixture in fixtures:
        fixture_id = str(fixture.get("id", {}).get("full", ""))
        fixture_name = fixture.get("name", {}).get("text", "")
        competition_name = fixture.get("competition", {}).get("name", {}).get("text", "")
        
        markets = fixture.get("markets", [])
        
        for market in markets:
            market_type = market.get("marketType", "").lower()
            period = market.get("period", "").lower()
            market_value = str(market.get("value", ""))
            
            # For markets without 'value', try to extract from first option name (e.g., "Over 43")
            if not market_value or market_value == "":
                options = market.get("options", [])
                if options and len(options) > 0:
                    first_option_name = options[0].get("name", {}).get("text", "")
                    # Extract number from "Over 43" or "Under 43.5"
                    import re
                    match = re.search(r'(\d+\.?\d*)', first_option_name)
                    if match:
                        market_value = match.group(1)
            
            # Determine market category
            matched_category = None
            
            # Check Moneyline
            if market_type in [mt.lower() for mt in NFL_CONFIG["moneyline"]["market_types"]]:
                if period in [p.lower() for p in NFL_CONFIG["moneyline"]["periods"]]:
                    matched_category = "moneyline"
            
            # Check Spread
            elif market_type in [mt.lower() for mt in NFL_CONFIG["spread"]["market_types"]]:
                if period in [p.lower() for p in NFL_CONFIG["spread"]["periods"]]:
                    matched_category = "spread"
            
            # Check Total
            elif market_type in [mt.lower() for mt in NFL_CONFIG["total"]["market_types"]]:
                if period in [p.lower() for p in NFL_CONFIG["total"]["periods"]]:
                    matched_category = "total"
            
            # Skip if not matched
            if not matched_category:
                continue
            
            # Deduplication key: fixture + category
            dedup_key = f"{fixture_id}-{matched_category}"
            
            # Special handling for Total markets - prefer certain values
            if matched_category == "total":
                preferred_values = NFL_CONFIG["total"]["preferred_values"]
                
                should_use = False
                
                if dedup_key not in market_by_fixture_category:
                    # No total yet, use this one
                    should_use = True
                else:
                    # Compare with existing total
                    existing_value = str(market_by_fixture_category[dedup_key].get("value", ""))
                    
                    # Calculate priority (lower index = higher priority)
                    current_priority = preferred_values.index(market_value) if market_value in preferred_values else 999
                    existing_priority = preferred_values.index(existing_value) if existing_value in preferred_values else 999
                    
                    # Replace if current is better
                    if current_priority < existing_priority:
                        should_use = True
                        print(f"   → Replacing total {existing_value} with preferred {market_value} for {fixture_id}")
                
                if not should_use:
                    print(f"   ⏭️  Skipping total {market_value} (keeping {market_by_fixture_category[dedup_key].get('value', '')})")
                    continue
            
            # For moneyline and spread, skip duplicates
            elif dedup_key in market_by_fixture_category:
                print(f"   ⏭️  Skipping duplicate {matched_category} for {fixture_id}")
                continue
            
            # Create unique market_id
            market_name = market.get("name", {}).get("text", "").lower().replace(" ", "-")
            market_value_clean = market_value.replace(" ", "")
            unique_market_id = f"{fixture_id}-{matched_category}-{market_name}-{market_value_clean}"
            
            # Build market data object
            market_data = {
                **market,
                "value": market_value,  # Add extracted value
                "metadata": {
                    "market_id": unique_market_id,
                    "fixture_id": fixture_id,
                    "sport_id": "11",
                    "market_category": matched_category,
                    "fixture_name": fixture_name,
                    "competition_name": competition_name
                },
                "competition_name": competition_name,
                "title": f"{fixture_name} | {market.get('name', {}).get('text', '')} {market_value}"
            }
            
            # Store this market
            market_by_fixture_category[dedup_key] = market_data
            
            print(f"✓ {matched_category.upper()}: {unique_market_id} | Value: {market_value}")
    
    # Convert dict to lists
    market_odds = list(market_by_fixture_category.values())
    market_ids = [m.get("metadata", {}).get("market_id", "") for m in market_odds]
    
    # Count by category
    category_counts = {}
    for market in market_odds:
        category = market.get("metadata", {}).get("market_category", "other")
        category_counts[category] = category_counts.get(category, 0) + 1
    
    print(f"\n✅ Filtered {len(market_odds)} NFL markets from {len(fixtures)} fixtures")
    print(f"   Market breakdown: {category_counts}")
    print(f"   Expected: {len(fixtures)} fixtures × 3 categories = {len(fixtures) * 3} markets")
    
    return {
        "status": True,
        "data": {
            "market_ids": market_ids,
            "market_odds": market_odds,
            "total_markets": len(market_odds),
            "category_counts": category_counts
        }
    }
