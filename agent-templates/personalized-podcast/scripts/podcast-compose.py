import os
import tempfile
import urllib.request
import urllib.error
import re


def invoke_compose(request_data):
    """
    Composes an HTML email template for podcast by replacing variables with provided values.
    
    Args:
        request_data: Dictionary containing params
            params:
                - template_path: Path to HTML template (URL or local file path)
                - podcast-content: Podcast content with all fields
                - document_id: Document ID for generating podcast page URL (required for podcast access)
                - podcast_base_url: Base URL for podcast pages (default: https://podcast.machina.gg)
                - audio_url: Optional audio URL (for reference only, not used in email links)
                - user_name: Name of the user
                - favorite_sport: User's favorite sport
                - favorite_team: User's favorite team
                - header_image: Optional header image path/URL
                - footer_image: Optional footer image path/URL
                - podcast_duration: Optional podcast duration in seconds
                - newsletter_markdown: Newsletter markdown content
                - podcast_headline: Podcast headline
                - podcast_summary: Podcast summary
    
    Returns:
        Dictionary with status, data (containing output_path), and message
    """
    
    params = request_data.get("params", {})
    
    template_path = params.get("template_path")
    podcast_content = params.get("podcast-content", {})
    audio_url = params.get("audio_url")
    document_id = params.get("document_id")
    podcast_base_url = params.get("podcast_base_url", "https://podcast.machina.gg")
    user_name = params.get("user_name")
    name = params.get("name") or user_name  # Support both 'name' and 'user_name'
    favorite_sport = params.get("favorite_sport")
    favorite_team = params.get("favorite_team")
    header_image = params.get("header_image")
    header_background_image = params.get("header_background_image") or header_image
    footer_image = params.get("footer_image")
    podcast_duration = params.get("podcast_duration")
    podcast_mood_tone = params.get("podcast_mood_tone")
    sports_knowledge = params.get("sports_knowledge")
    language = params.get("language", "en")
    newsletter_markdown = params.get("newsletter_markdown")
    podcast_headline = params.get("podcast_headline")
    podcast_summary = params.get("podcast_summary")
    
    if not template_path:
        return {"status": "error", "message": "template_path is required."}
    
    # Build variables from podcast_content
    variables = {}
    
    # If podcast_content is a dict, use it directly
    if isinstance(podcast_content, dict):
        variables.update(podcast_content)
    
    # Add user information
    if name:
        variables['name'] = name
        variables['user_name'] = name  # Support both formats
    elif user_name:
        variables['name'] = user_name
        variables['user_name'] = user_name
    if favorite_sport:
        variables['favorite_sport'] = favorite_sport
    if favorite_team:
        variables['favorite_team'] = favorite_team
    if audio_url:
        variables['audio_url'] = audio_url
    if podcast_duration:
        variables['podcast_duration'] = str(podcast_duration)
    if podcast_mood_tone:
        variables['podcast_mood_tone'] = podcast_mood_tone
    if sports_knowledge:
        variables['sports_knowledge'] = sports_knowledge
    if language:
        variables['language'] = language
    if newsletter_markdown:
        variables['newsletter_markdown'] = newsletter_markdown
    if podcast_headline:
        variables['podcast_headline'] = podcast_headline
    if podcast_summary:
        variables['podcast_summary'] = podcast_summary
    
    # Create podcast_url from document_id and base URL
    if document_id:
        variables['podcast_url'] = f"{podcast_base_url}/podcast/{document_id}"
    else:
        variables['podcast_url'] = "#"
    
    # Add optional images
    # Ensure image is a valid URL (not just a path)
    image_url = None
    if header_background_image:
        image_url = header_background_image
    elif header_image:
        image_url = header_image
    
    if image_url:
        # If it's not already a full URL, it should be from Google Storage
        # The image_path from generate-image workflow is already a full URL
        variables['header_background_image'] = image_url
        variables['header_image'] = image_url
        variables['header_image_tag'] = f'<div class="team-image-section"><img src="{image_url}" alt="Team/Mascot Image" style="width: 100%; max-width: 100%; height: auto; display: block; margin: 0; border: 0; outline: none;"></div>'
        variables['header_title'] = ""
    else:
        # Use a default gradient background when no image
        variables['header_background_image'] = "linear-gradient(135deg, #000000 0%, #1a1a1a 100%)"
        variables['header_image'] = ""
        variables['header_image_tag'] = ""
        variables['header_title'] = "🎙️ Your Personalized Podcast"
    
    if footer_image:
        variables['footer_image'] = footer_image
        variables['footer_image_tag'] = f'<div class="footer-image"><img src="{footer_image}" alt="Promotional Image"></div>'
    else:
        variables['footer_image_tag'] = ""
    
    # Add podcast duration tag
    if podcast_duration:
        variables['podcast_duration_tag'] = f'<p><strong>Duration:</strong> {podcast_duration} seconds</p>'
    else:
        variables['podcast_duration_tag'] = ""
    
    # Add podcast button - links to podcast page
    if document_id:
        variables['download_button'] = f'<div class="download-button"><a href="{variables["podcast_url"]}">🎧 Listen to Your Podcast</a></div>'
        variables['podcast_button'] = f'<a href="{variables["podcast_url"]}">Listen Now</a>'
    else:
        variables['download_button'] = ""
        variables['podcast_button'] = ""
    
    # Set default values if not provided
    if 'subject_line' not in variables:
        variables['subject_line'] = f"Your Personalized {favorite_sport} Podcast"
    
    if 'headline' not in variables:
        variables['headline'] = f"Your {favorite_team} Podcast is Ready!"
    
    if 'description' not in variables:
        variables['description'] = f"<p>We've created a personalized podcast just for you about {favorite_team} and {favorite_sport}. Enjoy listening!</p>"
    
    if 'contact_info' not in variables:
        variables['contact_info'] = "If you have any questions, please contact our support team."
    
    # Check if template_path is a URL
    is_url = template_path.startswith(('http://', 'https://'))
    
    try:
        # Read template content
        if is_url:
            req = urllib.request.Request(
                template_path, 
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req) as response:
                html_content = response.read().decode('utf-8')
        else:
            if not os.path.exists(template_path):
                return {"status": "error", "message": f"Template file not found: {template_path}"}
            
            with open(template_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
        
        # Replace variables in template
        replaced_content = html_content
        
        for key, value in variables.items():
            value_str = "" if value is None else str(value)
            
            # Replace {{key}} format
            replaced_content = re.sub(
                r'\{\{' + re.escape(key) + r'\}\}',
                value_str,
                replaced_content
            )
        
        # Create temporary output file
        temp_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.html',
            delete=False,
            encoding='utf-8'
        )
        
        temp_file.write(replaced_content)
        temp_file.close()
        
        return {
            "status": True,
            "data": {
                "output_path": temp_file.name,
                "filename": os.path.basename(temp_file.name),
                "html_content": replaced_content,
                "variables_applied": len(variables)
            },
            "message": "Podcast email HTML template composed successfully."
        }
    
    except urllib.error.URLError as e:
        return {"status": "error", "message": f"Failed to download template: {e}"}
    except Exception as e:
        return {"status": "error", "message": f"Exception when composing template: {e}"}

