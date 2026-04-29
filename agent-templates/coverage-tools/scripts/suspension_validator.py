def invoke_suspension_validator(request_data):
    """
    Validate suspension stories by checking actual card data from the most recent matches in the same competition.
    
    Rules:
    - Red card: Player must have received red card in most recent match
    - Yellow cards: Player must have accumulated 3+ yellows in recent matches (same competition)
    """
    
    def validate_suspension(story, past_events, all_cards, competition_id):
        """
        Validate if a suspension story is accurate based on actual card data.
        
        Returns:
            tuple: (is_valid: bool, reason: str)
        """
        player_id = story.get('player_id', '')
        team_id = story.get('team_id', '')
        event_type = story.get('event_type', '')
        
        if not player_id or not team_id:
            return False, "Missing player_id or team_id"
        
        # Get events for this team in chronological order (most recent first)
        team_events = [
            event for event in past_events
            if team_id in event.get('competitors', []) and 
            event.get('competition_id') == competition_id
        ]
        
        if not team_events:
            return False, f"No past events found for team {team_id} in competition {competition_id}"
        
        # For red card suspensions
        if event_type == 'red_card':
            most_recent_event_id = team_events[0].get('event_id')
            
            # Find cards for this event
            event_cards = next(
                (ec.get('cards', []) for ec in all_cards if ec.get('event_id') == most_recent_event_id),
                []
            )
            
            # Check if player received red card
            # Handle both ID formats: with and without urn:sportradar:player: prefix
            player_id_variants = [
                player_id,
                player_id.replace('urn:sportradar:player:', 'sr:player:'),
                player_id.replace('sr:player:', 'urn:sportradar:player:')
            ]
            
            player_red_cards = [
                card for card in event_cards
                if card.get('player', {}).get('id') in player_id_variants and
                card.get('type', '').lower() == 'red_card'
            ]
            
            if len(player_red_cards) > 0:
                return True, "Valid: Red card in most recent match"
            else:
                return False, f"No red card found for player in most recent match ({most_recent_event_id})"
        
        # For yellow card accumulation (3 yellows = suspension)
        elif event_type in ['yellow_card', 'accumulation']:
            yellow_count = 0
            matches_to_check = min(5, len(team_events))
            
            # Handle both ID formats
            player_id_variants = [
                player_id,
                player_id.replace('urn:sportradar:player:', 'sr:player:'),
                player_id.replace('sr:player:', 'urn:sportradar:player:')
            ]
            
            for i in range(matches_to_check):
                event_id = team_events[i].get('event_id')
                
                # Find cards for this event
                event_cards = next(
                    (ec.get('cards', []) for ec in all_cards if ec.get('event_id') == event_id),
                    []
                )
                
                # Count yellow cards for this player
                player_yellow_cards = [
                    card for card in event_cards
                    if card.get('player', {}).get('id') in player_id_variants and
                    card.get('type', '').lower() == 'yellow_card'
                ]
                
                yellow_count += len(player_yellow_cards)
            
            # Suspension occurs at 3 yellow cards
            if yellow_count >= 3:
                return True, f"Valid: {yellow_count} yellow cards accumulated"
            else:
                return False, f"Only {yellow_count} yellow cards found in last {matches_to_check} matches (need 3 for suspension)"
        
        # Unknown event type
        return False, f"Unknown event type: {event_type}"
    
    # Main execution
    params = request_data.get("params") or {}
    
    suspension_stories = params.get("suspension_stories", [])
    past_events = params.get("past_events_parsed", [])
    all_cards = params.get("all_cards", [])
    competition_id = params.get("competition_id", "")
    
    validated_stories = []
    invalid_stories = []
    
    for story in suspension_stories:
        is_valid, reason = validate_suspension(story, past_events, all_cards, competition_id)
        
        if is_valid:
            validated_stories.append(story)
        else:
            invalid_stories.append({
                **story,
                'validation_reason': reason
            })
    
    validation_summary = {
        'total_stories': len(suspension_stories),
        'validated': len(validated_stories),
        'invalid': len(invalid_stories),
        'competition_id': competition_id
    }
    
    return {
        "status": True,
        "message": "Suspension validation completed successfully.",
        "data": {
            "validated_stories": validated_stories,
            "invalid_stories": invalid_stories,
            "validation_summary": validation_summary
        }
    }
