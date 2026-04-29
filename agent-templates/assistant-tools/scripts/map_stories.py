import json

def invoke_map_stories(request_data):

    params = request_data.get("params", {})
    
    event_stories_snippets = params.get("event-stories-snippets", [])
    story_fact_check_parsed = params.get("story-fact-check-parsed", [])
    
    # Merge stories with their respective fact-checks
    selected_event_stories_snippets = []
    
    for i, story in enumerate(event_stories_snippets):
        # Get corresponding fact-check if exists
        if i < len(story_fact_check_parsed):
            fact_check_str = story_fact_check_parsed[i].strip()
            
            # Parse JSON string to object
            try:
                fact_check_obj = json.loads(fact_check_str)
            except json.JSONDecodeError:
                fact_check_obj = {}
            
            # Merge story with fact-check
            merged_story = {
                **story,
                **fact_check_obj
            }
        else:
            # No fact-check available for this story
            merged_story = story
        
        selected_event_stories_snippets.append(merged_story)
    
    # Filter stories by veracity threshold (minimum 70)
    selected_event_stories_snippets = [
        story for story in selected_event_stories_snippets 
        if story.get('veracity-factor', 0) >= 70
    ]
    
    # Sort by combined quality score (veracity + relevance)
    # Higher combined score = better overall quality
    selected_event_stories_snippets.sort(
        key=lambda x: x.get('veracity-factor', 0) + x.get('relevance-factor', 0),
        reverse=True
    )
    
    # Remove unwanted fields from final objects
    for story in selected_event_stories_snippets:
        story.pop('event_type', None)
        story.pop('subject', None)

    return {
        "status": True,
        "message": "Mapped stories successfully.",
        "data": {
            "selected-event-stories-snippets": selected_event_stories_snippets
        }
    }

