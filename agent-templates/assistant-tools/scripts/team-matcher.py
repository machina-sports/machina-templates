def match_teams_by_name(request_data):
    """
    Match team names from user query to team documents using fuzzy matching.
    
    Args:
        request_data (dict): Request data containing:
            - params (dict):
                - team_names (list): List of team names to match
                - team_documents (list): List of team documents to search
                - threshold (float): Minimum similarity ratio (default: 0.6)
    
    Returns:
        dict: Response containing:
            - status (bool): Success status
            - data (dict):
                - matched_teams (list): List of matched team documents
                - team_ids (list): List of matched team IDs
                - match_count (int): Number of matches found
    """
    import difflib
    
    try:
        params = request_data.get("params", {})
        team_names = params.get("team_names", [])
        team_documents = params.get("team_documents", [])
        threshold = float(params.get("threshold", 0.6))
        
        if not team_names or not team_documents:
            return {
                "status": True,
                "data": {
                    "matched_teams": [],
                    "team_ids": []
                }
            }
        
        matched_teams = []
        team_ids = []
        
        # Match each team name from query
        for query_team_name in team_names:
            query_name_lower = str(query_team_name).lower().strip()
            best_match = None
            best_ratio = 0.0
            
            # Find best match across all documents
            for doc in team_documents:
                if not isinstance(doc, dict):
                    continue
                
                value = doc.get("value", {})
                if not isinstance(value, dict):
                    value = {}
                
                # Collect all possible name variations
                names = []
                
                # Document title
                if doc.get("title"):
                    names.append(str(doc.get("title")).lower().strip())
                
                # Value fields
                if value.get("title"):
                    names.append(str(value.get("title")).lower().strip())
                if value.get("name"):
                    names.append(str(value.get("name")).lower().strip())
                if value.get("sport:shortName"):
                    names.append(str(value.get("sport:shortName")).lower().strip())
                if value.get("sport:officialName"):
                    names.append(str(value.get("sport:officialName")).lower().strip())
                if value.get("schema:name"):
                    names.append(str(value.get("schema:name")).lower().strip())
                
                # Remove duplicates and empty strings
                names = [n for n in list(set(names)) if n]
                
                # Try matching against all name variations
                for name_variant in names:
                    if not name_variant:
                        continue
                    
                    # Calculate similarity ratio
                    ratio = difflib.SequenceMatcher(None, query_name_lower, name_variant).ratio()
                    
                    # Boost exact matches
                    if query_name_lower == name_variant:
                        ratio = 1.0
                    # Boost partial matches (substring)
                    elif query_name_lower in name_variant or name_variant in query_name_lower:
                        ratio = max(ratio, 0.85)
                    
                    # Update best match if this is better
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_match = {
                            "doc": doc,
                            "match_ratio": ratio,
                            "matched_name": name_variant
                        }
            
            # Add match if above threshold
            if best_match and best_match["match_ratio"] >= threshold:
                best_doc = best_match["doc"]
                
                matched_teams.append({
                    "_id": best_doc.get("_id"),
                    "name": best_doc.get("name"),
                    "title": best_doc.get("title"),
                    "value": best_doc.get("value", {}),
                    "metadata": best_doc.get("metadata", {}),
                    "match_ratio": best_match["match_ratio"],
                    "matched_name": best_match["matched_name"]
                })
                
                # Extract team ID
                doc_value = best_doc.get("value", {})
                if isinstance(doc_value, dict):
                    team_id = doc_value.get("@id", "")
                    if team_id:
                        team_ids.append(team_id)
        
        return {
            "status": True,
            "data": {
                "matched_teams": matched_teams,
                "team_ids": list(set(team_ids)),
                "match_count": len(matched_teams)
            }
        }
    
    except Exception as e:
        import traceback
        return {
            "status": False,
            "error": str(e),
            "message": f"Error matching teams: {str(e)}",
            "traceback": traceback.format_exc()
        }

