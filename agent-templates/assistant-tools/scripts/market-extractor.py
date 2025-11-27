from difflib import SequenceMatcher

def extract_markets_from_events(request_data):
    """
    Extract all markets from events' market_data.
    Returns a list of all markets with their options and odds.
    """
    try:
        if not isinstance(request_data, dict):
            return {
                "status": False,
                "error": "Invalid request_data: expected dict",
                "data": {
                    "all_markets": [],
                    "events_with_markets": []
                }
            }
        
        params = request_data.get("params", {})
        if not isinstance(params, dict):
            return {
                "status": False,
                "error": "Invalid params: expected dict",
                "data": {
                    "all_markets": [],
                    "events_with_markets": []
                }
            }
        
        events = params.get("events", [])
        if not isinstance(events, list):
            events = []
        
        all_markets = []
        events_with_markets = []
        
        for event in events:
            if not isinstance(event, dict):
                continue
            
            event_id_sportradar = event.get("@id", "")
            event_title = event.get("name", "Unknown Event")
            
            # Navigate to markets: event -> market_data -> items[0] -> markets
            market_data = event.get("market_data", {})
            if not isinstance(market_data, dict):
                continue
            
            items = market_data.get("items", [])
            if not isinstance(items, list) or len(items) == 0:
                continue
            
            first_item = items[0]
            if not isinstance(first_item, dict):
                continue
            
            # Extract Sportingbet event ID from market_data.items[0].id.entityId
            event_id_obj = first_item.get("id", {})
            event_id = None
            if isinstance(event_id_obj, dict):
                entity_id = event_id_obj.get("entityId")
                if entity_id is not None:
                    event_id = str(entity_id) if not isinstance(entity_id, str) else entity_id
            
            # Fallback to sportradar ID if Sportingbet ID not found
            if not event_id:
                event_id = event_id_sportradar
            
            markets = first_item.get("markets", [])
            if not isinstance(markets, list) or len(markets) == 0:
                continue
            
            # Track if this event has valid markets
            event_has_markets = False
            
            for market in markets:
                if not isinstance(market, dict):
                    continue
                
                market_id = market.get("id")
                market_type = market.get("marketType", "")
                is_open = market.get("isOpenForBetting", False)
                is_displayed = market.get("isDisplayed", False)
                
                # Only include markets that are open and displayed
                if not is_open or not is_displayed:
                    continue
                
                market_name_obj = market.get("name", {})
                if isinstance(market_name_obj, dict):
                    market_name = market_name_obj.get("text", "")
                else:
                    market_name = str(market_name_obj)
                
                # Extract options (selections/runners)
                options = market.get("options", [])
                if not isinstance(options, list):
                    continue
                
                formatted_options = []
                for option in options:
                    if not isinstance(option, dict):
                        continue
                    
                    option_id = option.get("id")
                    is_option_open = option.get("isOpenForBetting", False)
                    is_option_displayed = option.get("isDisplayed", False)
                    
                    if not is_option_open or not is_option_displayed:
                        continue
                    
                    option_name_obj = option.get("name", {})
                    if isinstance(option_name_obj, dict):
                        option_name = option_name_obj.get("text", "")
                    else:
                        option_name = str(option_name_obj)
                    
                    price_obj = option.get("price", {})
                    if isinstance(price_obj, dict):
                        odds = price_obj.get("odds")
                    else:
                        odds = None
                    
                    if odds is not None:
                        formatted_options.append({
                            "id": option_id,
                            "name": option_name,
                            "odds": odds
                        })
                
                # Only add markets with valid options
                if formatted_options:
                    event_has_markets = True
                    all_markets.append({
                        "event_id": event_id,
                        "event_title": event_title,
                        "market_id": market_id,
                        "market_name": market_name,
                        "market_type": market_type,
                        "options": formatted_options
                    })
            
            if event_has_markets:
                events_with_markets.append(event_id)
        
        return {
            "status": True,
            "data": {
                "all_markets": all_markets,
                "events_with_markets": events_with_markets,
                "total_markets": len(all_markets),
                "total_events": len(events_with_markets)
            }
        }
        
    except Exception as e:
        return {
            "status": False,
            "error": f"Error extracting markets: {str(e)}",
            "data": {
                "all_markets": [],
                "events_with_markets": []
            }
        }


def filter_and_summarize_markets(request_data):
    """
    Filter markets by market_query or popular market types.
    Returns formatted summaries for LLM consumption.
    """
    try:
        if not isinstance(request_data, dict):
            return {
                "status": False,
                "error": "Invalid request_data: expected dict",
                "data": {
                    "markets_docs": [],
                    "markets_parsed": []
                }
            }
        
        params = request_data.get("params", {})
        if not isinstance(params, dict):
            return {
                "status": False,
                "error": "Invalid params: expected dict",
                "data": {
                    "markets_docs": [],
                    "markets_parsed": []
                }
            }
        
        all_markets = params.get("all_markets", [])
        market_query = params.get("market_query", "")
        top_n_markets = params.get("top_n_markets", 5)
        translations = params.get("translations", {})  # Translation dictionaries from document
        
        # Reasoning-based filters (from chat-reasoning)
        reasoning_filters = params.get("reasoning_filters", {})
        recommended_market_types = reasoning_filters.get("recommended_market_types", [])
        odds_range = reasoning_filters.get("odds_range", {})
        runner_filter = reasoning_filters.get("runner_filter", "all")
        reasoning_market_query = reasoning_filters.get("market_query", "")
        
        # Use reasoning market_query if provided, otherwise use direct param
        if reasoning_market_query:
            market_query = reasoning_market_query
        
        if not isinstance(all_markets, list):
            all_markets = []
        
        # Define popular market types (in order of preference)
        popular_market_types = [
            "3way",
            "total",
            # "handicap",  # Excluded per user request
            "draw_no_bet",
            "both_teams_to_score",
            "double_chance",
            "correct_score",
            "over/under"  # Added to include Total Goals markets
        ]
        
        # Define market name patterns to exclude
        excluded_market_patterns = [
            "result after",  # Excludes "Result after 60:00 min", etc.
            "after",         # Additional pattern to catch time-based markets
            "handicap"       # Exclude handicap markets by name
        ]
        
        filtered_markets = []
        
        # Helper function to check if market should be excluded
        def should_exclude_market(market):
            market_name = market.get("market_name", "").lower()
            market_type = market.get("market_type", "").lower()
            
            # Check if market name contains any excluded patterns
            for pattern in excluded_market_patterns:
                if pattern in market_name or pattern in market_type:
                    return True
            
            return False
        
        # Strategy 1: If market_query is provided, use fuzzy matching
        if market_query and isinstance(market_query, str) and market_query.strip():
            query_lower = market_query.strip().lower()
            
            for market in all_markets:
                # Skip excluded markets
                if should_exclude_market(market):
                    continue
                
                market_name = market.get("market_name", "").lower()
                market_type = market.get("market_type", "").lower()
                
                # Calculate similarity scores
                name_similarity = SequenceMatcher(None, query_lower, market_name).ratio()
                type_similarity = SequenceMatcher(None, query_lower, market_type).ratio()
                
                # Check if query words are in market name or type
                query_words = set(query_lower.split())
                name_words = set(market_name.split())
                type_words = set(market_type.split())
                
                word_match_score = len(query_words & (name_words | type_words)) / len(query_words) if query_words else 0
                
                # Combined score (prioritize word matches)
                combined_score = max(name_similarity, type_similarity, word_match_score)
                
                if combined_score > 0.3:  # Threshold for relevance
                    filtered_markets.append({
                        **market,
                        "relevance_score": combined_score
                    })
            
            # Sort by relevance score
            filtered_markets.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        # Strategy 2: If no matches or no query, use popular market types
        if not filtered_markets:
            # Group markets by event
            markets_by_event = {}
            for market in all_markets:
                # Skip excluded markets
                if should_exclude_market(market):
                    continue
                
                event_id = market.get("event_id")
                if event_id not in markets_by_event:
                    markets_by_event[event_id] = []
                markets_by_event[event_id].append(market)
            
            # For each event, select popular markets
            for event_id, event_markets in markets_by_event.items():
                # Sort markets by popularity (based on market type order)
                def get_popularity_rank(market):
                    market_type = market.get("market_type", "").lower()
                    try:
                        return popular_market_types.index(market_type)
                    except ValueError:
                        return len(popular_market_types)
                
                event_markets.sort(key=get_popularity_rank)
                
                # Take top N markets per event
                filtered_markets.extend(event_markets[:top_n_markets])
        
        # Limit overall results
        filtered_markets = filtered_markets[:top_n_markets * 3]  # Allow more results across multiple events
        
        # Apply reasoning-based filters if provided
        if reasoning_filters:
            reasoning_filtered = []
            
            for market in filtered_markets:
                # Filter by recommended market types
                if recommended_market_types and isinstance(recommended_market_types, list):
                    market_type = market.get("market_type", "").lower()
                    if market_type not in [t.lower() for t in recommended_market_types]:
                        continue
                
                # Filter by odds range
                if odds_range and isinstance(odds_range, dict):
                    min_odds = odds_range.get("min_odds")
                    max_odds = odds_range.get("max_odds")
                    
                    # Filter options within odds range
                    if min_odds is not None or max_odds is not None:
                        filtered_options = []
                        for opt in market.get("options", []):
                            if isinstance(opt, dict):
                                opt_odds = opt.get("odds")
                                if opt_odds is not None:
                                    if min_odds is not None and opt_odds < min_odds:
                                        continue
                                    if max_odds is not None and opt_odds > max_odds:
                                        continue
                                    filtered_options.append(opt)
                        
                        # Skip market if no options remain after filtering
                        if not filtered_options:
                            continue
                        
                        market = {**market, "options": filtered_options}
                
                # Filter by runner (home/away/draw)
                if runner_filter and runner_filter != "all":
                    filtered_options = []
                    for opt in market.get("options", []):
                        if isinstance(opt, dict):
                            opt_name = opt.get("name", "").lower()
                            
                            # Detect runner type
                            if runner_filter == "draw":
                                # Match draw/empate/x
                                if any(x in opt_name for x in ["x", "draw", "empate", "tie"]):
                                    filtered_options.append(opt)
                            elif runner_filter == "home":
                                # Match first option or team names (heuristic: not draw, not second team)
                                event_title = market.get("event_title", "")
                                if event_title and " vs " in event_title.lower():
                                    home_team = event_title.split(" vs ")[0].strip().lower()
                                    if home_team in opt_name or opt_name.startswith("1"):
                                        filtered_options.append(opt)
                                elif opt_name.startswith("1") or "home" in opt_name:
                                    filtered_options.append(opt)
                            elif runner_filter == "away":
                                # Match second option or away team
                                event_title = market.get("event_title", "")
                                if event_title and " vs " in event_title.lower():
                                    away_team = event_title.split(" vs ")[-1].strip().lower()
                                    if away_team in opt_name or opt_name.startswith("2"):
                                        filtered_options.append(opt)
                                elif opt_name.startswith("2") or "away" in opt_name:
                                    filtered_options.append(opt)
                    
                    # Skip market if no options remain
                    if not filtered_options:
                        continue
                    
                    market = {**market, "options": filtered_options}
                
                reasoning_filtered.append(market)
            
            filtered_markets = reasoning_filtered
        
        # Check if user query mentions "under" to show both over/under
        show_under = False
        if market_query and isinstance(market_query, str):
            query_lower = market_query.lower()
            if "under" in query_lower or "abaixo" in query_lower:
                show_under = True
        
        # Apply translations and filter options
        translated_markets = []
        for market in filtered_markets:
            if translations and isinstance(translations, dict):
                translated_market = market.copy()
                
                # Translate market type
                market_type = market.get("market_type", "")
                if market_type and "market_types" in translations:
                    market_types_dict = translations.get("market_types", {})
                    translated_type = market_types_dict.get(market_type.lower())
                    if translated_type:
                        translated_market["market_type_original"] = market_type
                        translated_market["market_type"] = translated_type
                
                # Translate market name (partial match - case insensitive)
                market_name = market.get("market_name", "")
                if market_name and "market_names" in translations:
                    market_names_dict = translations.get("market_names", {})
                    market_name_lower = market_name.lower()
                    translated = False
                    
                    # Try exact match first
                    if market_name_lower in market_names_dict:
                        translated_market["market_name_original"] = market_name
                        translated_market["market_name"] = market_names_dict[market_name_lower]
                        translated = True
                    else:
                        # Try partial match (find any key in market name)
                        for key, value in market_names_dict.items():
                            if key in market_name_lower:
                                translated_market["market_name_original"] = market_name
                                # Replace case-insensitive
                                import re
                                translated_market["market_name"] = re.sub(
                                    re.escape(key), 
                                    value, 
                                    market_name, 
                                    flags=re.IGNORECASE
                                )
                                translated = True
                                break
                
                # Translate and filter options
                options = market.get("options", [])
                if options and isinstance(options, list) and "option_names" in translations:
                    option_names_dict = translations.get("option_names", {})
                    translated_options = []
                    
                    for opt in options:
                        if isinstance(opt, dict):
                            translated_opt = opt.copy()
                            opt_name = opt.get("name", "")
                            
                            if opt_name:
                                opt_name_lower = opt_name.lower().strip()
                                
                                # Filter out "Under" options by default (unless user asked for them)
                                if not show_under and ("under" in opt_name_lower or "abaixo" in opt_name_lower):
                                    continue
                                
                                # Translate option name
                                translated_name = option_names_dict.get(opt_name_lower)
                                if translated_name:
                                    translated_opt["name_original"] = opt_name
                                    translated_opt["name"] = translated_name
                            
                            translated_options.append(translated_opt)
                        else:
                            translated_options.append(opt)
                    
                    # Sort options by odds (ascending - lowest odds first)
                    translated_options.sort(key=lambda x: x.get("odds", 999) if isinstance(x, dict) else 999)
                    
                    translated_market["options"] = translated_options
                
                translated_markets.append(translated_market)
            else:
                translated_markets.append(market)
        
        # Format for LLM consumption (markets_docs)
        markets_docs = []
        for market in translated_markets:
            event_title = market.get("event_title", "Unknown Event")
            market_name = market.get("market_name", "Unknown Market")
            options = market.get("options", [])
            
            # Format options
            options_text = []
            for opt in options:
                opt_name = opt.get("name", "")
                opt_odds = opt.get("odds", "N/A")
                options_text.append(f"{opt_name}: {opt_odds}")
            
            # Create summary text
            doc_text = f"{event_title} - {market_name}: {', '.join(options_text)}"
            markets_docs.append(doc_text)
        
        # Return structured data (markets_parsed) - use translated markets
        markets_parsed = translated_markets
        
        # Collect statistics about excluded markets
        excluded_count = 0
        excluded_types = set()
        all_market_types = set()
        
        for market in all_markets:
            market_type = market.get("market_type", "unknown")
            market_name = market.get("market_name", "")
            all_market_types.add(f"{market_type}: {market_name}")
            
            if should_exclude_market(market):
                excluded_count += 1
                excluded_types.add(f"{market_type}: {market_name}")
        
        return {
            "status": True,
            "data": {
                "markets_docs": markets_docs,
                "markets_parsed": markets_parsed,
                "total_filtered": len(filtered_markets),
                "filter_method": "query_match" if market_query else "popular_markets",
                "translations_applied": bool(translations and isinstance(translations, dict)),
                "under_options_shown": show_under,
                "reasoning_filters_applied": bool(reasoning_filters),
                "debug_info": {
                    "total_markets_before_filter": len(all_markets),
                    "excluded_markets_count": excluded_count,
                    "excluded_market_examples": list(excluded_types)[:5],  # Show first 5 excluded
                    "all_unique_market_types": list(all_market_types)[:20],  # Show first 20 types
                    "excluded_patterns": excluded_market_patterns,
                    "options_filter": "showing only OVER options (default)" if not show_under else "showing both OVER and UNDER options (user requested)",
                    "reasoning_filters": {
                        "applied": bool(reasoning_filters),
                        "recommended_market_types": recommended_market_types if recommended_market_types else None,
                        "odds_range": odds_range if odds_range else None,
                        "runner_filter": runner_filter if runner_filter != "all" else None
                    }
                }
            }
        }
        
    except Exception as e:
        return {
            "status": False,
            "error": f"Error filtering markets: {str(e)}",
            "data": {
                "markets_docs": [],
                "markets_parsed": []
            }
        }


def extract_message_data_for_markets(request_data):
    """
    Extract team-events and market query from last user message.
    Combines event value extraction and reasoning extraction in one step.
    
    Args:
        request_data (dict): Request data containing:
            - params (dict):
                - last_user_msg (dict): The last user message object
    
    Returns:
        dict: Response containing event values and market query
    """
    try:
        params = request_data.get("params", {})
        last_user_msg = params.get("last_user_msg", {})
        
        if not isinstance(last_user_msg, dict):
            return {
                "status": False,
                "error": "Invalid last_user_msg: expected dict",
                "data": {
                    "event_values": [],
                    "market_query": ""
                }
            }
        
        # Extract team-events
        team_events_docs = last_user_msg.get("team-events", [])
        event_values = []
        
        if isinstance(team_events_docs, list):
            for event in team_events_docs:
                if not isinstance(event, dict):
                    continue
                
                # If it has a 'value' field, extract it
                if 'value' in event:
                    event_value = event.get('value', {})
                    if isinstance(event_value, dict):
                        event_values.append(event_value)
                # If it's already a value object (has IPTC fields), use it directly
                elif '@id' in event or 'sport:competitors' in event:
                    event_values.append(event)
        
        # Extract market query from reasoning
        reasoning = last_user_msg.get("reasoning", {})
        market_query = ""
        if isinstance(reasoning, dict):
            market_query = reasoning.get("market_query", "")
        
        return {
            "status": True,
            "data": {
                "event_values": event_values,
                "market_query": market_query,
                "total_events": len(event_values)
            }
        }
        
    except Exception as e:
        return {
            "status": False,
            "error": f"Error extracting message data for markets: {str(e)}",
            "data": {
                "event_values": [],
                "market_query": ""
            }
        }


def extract_event_values(request_data):
    """
    Extract event values from team-events document array.
    Handles both full document objects and already-extracted values.
    
    Args:
        request_data (dict): Request data containing:
            - params (dict):
                - team_events_docs (list): Array of event documents with 'value' field
    
    Returns:
        dict: Response containing extracted event values
    """
    try:
        params = request_data.get("params", {})
        team_events_docs = params.get("team_events_docs", [])
        
        if not isinstance(team_events_docs, list):
            return {
                "status": False,
                "error": "Invalid team_events_docs: expected list",
                "data": {
                    "event_values": []
                }
            }
        
        event_values = []
        
        for event in team_events_docs:
            if not isinstance(event, dict):
                continue
            
            # If it has a 'value' field, extract it
            if 'value' in event:
                event_value = event.get('value', {})
                if isinstance(event_value, dict):
                    event_values.append(event_value)
            # If it's already a value object (has IPTC fields), use it directly
            elif '@id' in event or 'sport:competitors' in event:
                event_values.append(event)
        
        return {
            "status": True,
            "data": {
                "event_values": event_values,
                "total_events": len(event_values)
            }
        }
        
    except Exception as e:
        return {
            "status": False,
            "error": f"Error extracting event values: {str(e)}",
            "data": {
                "event_values": []
            }
        }
