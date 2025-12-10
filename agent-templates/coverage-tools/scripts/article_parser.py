def invoke_transform_article_into_wp(request_data):
    
    params = request_data.get("params", {})
    
    content_articles = params.get("content-articles", [])
    
    events_widgets = params.get("events-widgets", [])
    
    anytime_goalscorer_widget = params.get("anytime-goalscorer-widget")
    
    wp_posts = []
    
    for article in content_articles:
        # Extract article metadata
        title = article.get("title", "")
        subtitle = article.get("subtitle", "")
        slug = article.get("slug", "")
        
        # Build article content from sections
        content_parts = []
        
        # Find all sections (section_1, section_2, etc.)
        section_num = 1
        while True:
            section_title_key = f"section_{section_num}_title"
            section_content_key = f"section_{section_num}_content"
            
            if section_title_key not in article or section_content_key not in article:
                break
            
            section_title = article.get(section_title_key, "")
            section_content = article.get(section_content_key, "")
            
            # Add section to content (markdown format)
            if section_title:
                # Skip H3 tag for intro section (section_1), use paragraph instead
                if section_num == 1:
                    content_parts.append(f"<p><strong>{section_title}</strong></p>")
                else:
                    content_parts.append(f"<h3>{section_title}</h3>")
            if section_content:
                content_parts.append(f"<p>{section_content}</p>")
            
            # Add widgets after section_1_content
            if section_num == 1 and events_widgets:
                for widget in events_widgets:
                    content_parts.append(f"<p>{widget.get('embed', '')}</p>")
            
            # Add anytime goalscorer widget after section_2_content
            if section_num == 2 and anytime_goalscorer_widget:
                widget_embed = anytime_goalscorer_widget.get('embed', '')
                if widget_embed:
                    content_parts.append(f"<p>{widget_embed}</p>")
            
            section_num += 1
        
        # Join all content parts
        full_content = "\n\n".join(content_parts)
        
        # Create WordPress post object
        wp_post = {
            "title": title,
            "slug": slug,
            "summary": subtitle,
            "content": full_content,
            "selected": False
        }
        
        wp_posts.append(wp_post)
    
    return {
        "status": True,
        "message": "Articles transformed into WordPress posts successfully.",
        "data": {
            "wp-posts": wp_posts
        }
    }
