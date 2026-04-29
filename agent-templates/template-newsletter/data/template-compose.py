import os
import tempfile
import urllib.request
import urllib.error
import re


def invoke_compose(request_data):
    """
    Composes an HTML email template by replacing variables with provided values.
    
    Args:
        request_data: Dictionary containing params
            params:
                - template_path: Path to HTML template (URL or local file path)
                - newsletter-content: Newsletter content with all fields
                - footer_image: Optional footer image path
                - header_image: Optional header image path
    
    Returns:
        Dictionary with status, data (containing output_path), and message
    """
    
    params = request_data.get("params", {})
    
    template_path = params.get("template_path")
    newsletter_content = params.get("newsletter-content", {})
    footer_image = params.get("footer_image")
    header_image = params.get("header_image")
    
    if not template_path:
        return {"status": "error", "message": "template_path is required."}
    
    # Build variables from newsletter_content
    variables = {}
    
    # If newsletter_content is a dict, use it directly
    if isinstance(newsletter_content, dict):
        variables.update(newsletter_content)
    
    # Add optional images
    if footer_image:
        variables['footer_image'] = footer_image
    if header_image:
        variables['header_image'] = header_image
    
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
                "variables_applied": len(variables)
            },
            "message": "HTML template composed successfully."
        }
    
    except urllib.error.URLError as e:
        return {"status": "error", "message": f"Failed to download template: {e}"}
    except Exception as e:
        return {"status": "error", "message": f"Exception when composing template: {e}"}
