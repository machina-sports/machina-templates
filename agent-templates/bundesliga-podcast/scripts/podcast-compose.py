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
                - audio_url: URL or path to the podcast audio file (overridden by podcast page if user-data.id exists)
                - image_path: Primary header image path/URL (takes precedence over header_image)
                - user_name: Name of the user
                - user-data: User data object containing 'id' for podcast page URL generation
                - favorite_sport: User's favorite sport
                - favorite_team: User's favorite team
                - header_image: Optional header image path/URL (fallback if image_path not provided)
                - footer_image: Optional footer image path/URL
                - podcast_duration: Optional podcast duration in seconds
    
    Returns:
        Dictionary with status, data (containing output_path), and message
    """
    
    params = request_data.get("params", {})
    
    template_path = params.get("template_path")
    podcast_content = params.get("podcast-content", {})
    audio_url = params.get("audio_url")
    document_id = params.get("document_id")
    podcast_base_url = params.get("podcast_base_url", "https://podcast.machina.gg")
    image_path = params.get("image_path")
    user_name = params.get("user_name")
    favorite_sport = params.get("favorite_sport")
    favorite_team = params.get("favorite_team")
    header_image = params.get("header_image")
    footer_image = params.get("footer_image")
    podcast_duration = params.get("podcast_duration")
    user_data = params.get("user-data", {}) or params.get("user_data", {})
    
    if not template_path:
        return {"status": "error", "message": "template_path is required."}
    
    # Build variables from podcast_content
    variables = {}
    
    # If podcast_content is a dict, use it directly
    if isinstance(podcast_content, dict):
        variables.update(podcast_content)
    
    # Add user information
    if user_name:
        variables['user_name'] = user_name
        variables['name'] = user_name  # Also set 'name' for template compatibility
    if favorite_sport:
        variables['favorite_sport'] = favorite_sport
    if favorite_team:
        variables['favorite_team'] = favorite_team
    if audio_url:
        variables['audio_url'] = audio_url
    if podcast_duration:
        variables['podcast_duration'] = str(podcast_duration)
    
    # Create podcast page URL from document_id
    # Support both new document_id parameter and legacy user_data.id
    user_id = document_id or (user_data.get("id") if isinstance(user_data, dict) else None)
    if user_id:
        variables['podcast_page_url'] = f"{podcast_base_url}/podcast/{user_id}"
        variables['podcast_url'] = variables['podcast_page_url']  # New variable name for template
        variables['audio_url'] = variables['podcast_page_url']  # Override audio_url with page URL (legacy)
    else:
        variables['podcast_page_url'] = audio_url or ""
        variables['podcast_url'] = audio_url or ""  # New variable name for template
    
    # Add optional images
    # Use image_path as primary source for header, fallback to header_image
    actual_header_image = image_path or header_image
    
    if actual_header_image:
        variables['header_image'] = actual_header_image
        variables['header_background_image'] = actual_header_image  # For CSS background-image
        variables['header_image_tag'] = f'<img src="{actual_header_image}" alt="Header" style="width: 100%; height: auto; display: block;">'
        variables['header_title'] = ""
    else:
        variables['header_image_tag'] = ""
        variables['header_background_image'] = ""  # Empty if no image
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
    
    # Add podcast button (links to podcast page if user_id exists, otherwise direct download)
    if variables.get('podcast_page_url'):
        if user_id:
            # Link to podcast page
            variables['download_button'] = f'<div class="download-button"><a href="{variables["podcast_page_url"]}">🎧 Listen to Your Podcast</a></div>'
            variables['podcast_button'] = f'<a href="{variables["podcast_page_url"]}">Listen Now</a>'
        else:
            # Direct download if no user_id
            variables['download_button'] = f'<div class="download-button"><a href="{variables["podcast_page_url"]}" download>📥 Download Podcast</a></div>'
            variables['podcast_button'] = f'<a href="{variables["podcast_page_url"]}" download>Download</a>'
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

