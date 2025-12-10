"""
Simplified Canvas Image Generator

Minimal version focused on basic image generation with background support.
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import tempfile

def create_image(request_data):
    """
    Create a simple image with optional background, logo overlay and text

    Args:
        request_data: Dictionary containing:
            - params: Dictionary with image parameters
                - width: Image width in pixels (default: 850)
                - height: Image height in pixels (calculated from width / 1.5)
                - assets_font_black_path: Path to font file for text (optional)
                - assets_font_medium_path: Path to font file for text (optional)
                - assets_font_medium_italic_path: Path to font file for text (optional)
                - assets_image_background_back: Path to back background image (optional, layer 1)
                - assets_image_background: Path to main background image with built-in opacity (optional, layer 2)
                - odd_position: Position object for odds {left: "6%", top: "6%", right: "auto", bottom: "auto"}
                - text_position: Position object for text {left: "20%", top: "26%", right: "auto", bottom: "auto"}
                - odd_color: RGBA color array for odd value (default: [0, 0, 0, 255] - black)
                - text_color: RGBA color array for words (default: [93, 173, 226, 255] - light blue)
                - odd_value: Odd value (ex: '2.40', '1.85', '1.75')
                - words: Array of words to display (up to 3 words, each on its own row)

    Returns:
        Dictionary with status and path to created image
    """
    
    def parse_position(position, width, height):
        """
        Parse position object to get x, y coordinates, alignment, and dimensions.
        
        Args:
            position: Dict with left/right/top/bottom values (e.g., "20%", "auto", "50px")
                     and optional width/height values
            width: Image width
            height: Image height
            
        Returns:
            tuple: (x_anchor, y_anchor, h_align, v_align, box_width, box_height)
                   x_anchor/y_anchor: pixel position or None
                   h_align: 'left' or 'right'
                   v_align: 'top' or 'bottom'
                   box_width/box_height: box dimensions in pixels or None
        """
        h_align = 'left'
        v_align = 'top'
        x_anchor = None
        y_anchor = None
        box_width = None
        box_height = None
        
        # Parse horizontal position
        if position.get('left') and position.get('left') != 'auto':
            h_align = 'left'
            left_val = position.get('left')
            if isinstance(left_val, str) and '%' in left_val:
                x_anchor = int(width * float(left_val.strip('%')) / 100)
            elif isinstance(left_val, str) and 'px' in left_val:
                x_anchor = int(left_val.replace('px', ''))
            elif isinstance(left_val, (int, float)):
                x_anchor = int(left_val)
        elif position.get('right') and position.get('right') != 'auto':
            h_align = 'right'
            right_val = position.get('right')
            if isinstance(right_val, str) and '%' in right_val:
                x_anchor = int(width * (1 - float(right_val.strip('%')) / 100))
            elif isinstance(right_val, str) and 'px' in right_val:
                x_anchor = width - int(right_val.replace('px', ''))
            elif isinstance(right_val, (int, float)):
                x_anchor = width - int(right_val)
        
        # Parse vertical position
        if position.get('top') and position.get('top') != 'auto':
            v_align = 'top'
            top_val = position.get('top')
            if isinstance(top_val, str) and '%' in top_val:
                y_anchor = int(height * float(top_val.strip('%')) / 100)
            elif isinstance(top_val, str) and 'px' in top_val:
                y_anchor = int(top_val.replace('px', ''))
            elif isinstance(top_val, (int, float)):
                y_anchor = int(top_val)
        elif position.get('bottom') and position.get('bottom') != 'auto':
            v_align = 'bottom'
            bottom_val = position.get('bottom')
            if isinstance(bottom_val, str) and '%' in bottom_val:
                y_anchor = int(height * (1 - float(bottom_val.strip('%')) / 100))
            elif isinstance(bottom_val, str) and 'px' in bottom_val:
                y_anchor = height - int(bottom_val.replace('px', ''))
            elif isinstance(bottom_val, (int, float)):
                y_anchor = height - int(bottom_val)
        
        # Parse box dimensions
        if position.get('width'):
            width_val = position.get('width')
            if isinstance(width_val, str) and 'px' in width_val:
                box_width = int(width_val.replace('px', ''))
            elif isinstance(width_val, (int, float)):
                box_width = int(width_val)
        
        if position.get('height'):
            height_val = position.get('height')
            if isinstance(height_val, str) and 'px' in height_val:
                box_height = int(height_val.replace('px', ''))
            elif isinstance(height_val, (int, float)):
                box_height = int(height_val)
        
        return x_anchor, y_anchor, h_align, v_align, box_width, box_height
    
    def resize_image_cover(img, target_width, target_height):
        """
        Resize image to cover the target dimensions without distortion.
        Works like CSS background-size: cover - maintains aspect ratio and crops excess.
        
        Args:
            img: PIL Image object
            target_width: Target width in pixels
            target_height: Target height in pixels
        
        Returns:
            Resized and cropped PIL Image
        """
        # Get original dimensions
        original_width, original_height = img.size
        original_ratio = original_width / original_height
        target_ratio = target_width / target_height
        
        # Calculate dimensions to cover the target area
        if original_ratio > target_ratio:
            # Image is wider - scale to match height, crop width
            new_height = target_height
            new_width = int(original_width * (target_height / original_height))
        else:
            # Image is taller - scale to match width, crop height
            new_width = target_width
            new_height = int(original_height * (target_width / original_width))
        
        # Resize image
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Calculate crop box to center the image
        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height
        
        # Crop to target dimensions
        img_cropped = img_resized.crop((left, top, right, bottom))
        
        return img_cropped

    try:
        # Extract params from request_data
        params = request_data.get("params", {})
        
        # Get parameters with defaults
        # Default dimensions match display size 850x555 to avoid pixelation
        width = params.get("width", 850)
        height = params.get("height", int(width / 1.5))
        assets_image_background = params.get("assets_image_background", None)
        assets_image_background_back = params.get("assets_image_background_back", None)
        assets_font_black_path = params.get("assets_font_black_path", None)
        assets_font_medium_path = params.get("assets_font_medium_path", None)
        assets_font_medium_italic_path = params.get("assets_font_medium_italic_path", None)
        
        # Get position objects (new format)
        odd_position = params.get("odd_position", {"left": "6%", "top": "6%", "right": "auto", "bottom": "auto"})
        text_position = params.get("text_position", {"left": "20%", "top": "26%", "right": "auto", "bottom": "auto"})
        
        # Get color arrays (RGBA format)
        odd_color = params.get("odd_color", [0, 0, 0, 255])  # Default: black
        text_color = params.get("text_color", [93, 173, 226, 255])  # Default: light blue
        
        odd_value = params.get("odd_value", "")
        words = params.get("words", [])
        
        # Format odd_value to always have 2 decimal places
        if odd_value:
            try:
                odd_float = float(odd_value)
                odd_value = f"{odd_float:.2f}"
            except (ValueError, TypeError):
                pass  # Keep original value if conversion fails
        
        # Start with back background if provided
        if assets_image_background_back and Path(assets_image_background_back).exists():
            # Load and resize back background with cover (no distortion)
            img = Image.open(assets_image_background_back)
            img = resize_image_cover(img, width, height)
            img = img.convert('RGBA')
        else:
            # Create blank image with gradient
            img = Image.new('RGB', (width, height), color='white')
            draw = ImageDraw.Draw(img)
            
            # Simple gradient background
            for y in range(height):
                # Calculate gradient color (light blue to darker blue)
                ratio = y / height
                r = int(93 + (52 - 93) * ratio)  # From 93 to 52
                g = int(173 + (152 - 173) * ratio)  # From 173 to 152
                b = int(226 + (219 - 226) * ratio)  # From 226 to 219
                draw.line([(0, y), (width, y)], fill=(r, g, b))
            
            # Convert to RGBA for overlay
            img = img.convert('RGBA')
        
        # Add main background on top if provided (layer already has opacity built-in)
        if assets_image_background and Path(assets_image_background).exists():
            main_bg = Image.open(assets_image_background)
            main_bg = resize_image_cover(main_bg, width, height)
            main_bg = main_bg.convert('RGBA')
            
            # Composite without additional opacity - the layer already has it
            img = Image.alpha_composite(img, main_bg)

        # Add text if font is provided
        if assets_font_black_path and Path(assets_font_black_path).exists() and odd_value:
            # Limit to 3 words (after odd_value)
            words = words[:3] if words else []
            
            print(f"Drawing text - odd_value: {odd_value}, words: {words}")
            print(f"Positions - odd: {odd_position}, text: {text_position}")
            
            # Load fonts - odd_value uses large font, words use smaller fonts
            font_size_large = int(height * 0.18)  # Large font for odd_value (reduced from 0.25)
            font_size_small = int(font_size_large / 1.8)  # Small font for words
            
            font_large = ImageFont.truetype(assets_font_black_path, font_size_large)
            font_small = ImageFont.truetype(assets_font_medium_path, font_size_small) if assets_font_medium_path and Path(assets_font_medium_path).exists() else None
            font_small_italic = ImageFont.truetype(assets_font_medium_italic_path, font_size_small) if assets_font_medium_italic_path and Path(assets_font_medium_italic_path).exists() else None
            
            print(f"Fonts loaded - large: {font_large is not None}, small: {font_small is not None}, italic: {font_small_italic is not None}")
            
            # Draw setup
            draw = ImageDraw.Draw(img)
            
            # Parse positions
            odd_x_anchor, odd_y_anchor, odd_h_align, odd_v_align, odd_box_width, odd_box_height = parse_position(odd_position, width, height)
            text_x_anchor, text_y_anchor, text_h_align, text_v_align, text_box_width, text_box_height = parse_position(text_position, width, height)
            
            spacing_between_lines = int(font_size_small * 0.15)  # Space between text lines
            
            # DRAW ODD_VALUE
            if odd_value:
                bbox = draw.textbbox((0, 0), str(odd_value), font=font_large)
                odd_text_width = bbox[2] - bbox[0]
                odd_text_height = bbox[3] - bbox[1]
                
                # Calculate X position for odd_value
                if odd_h_align == 'left':
                    x_odd = odd_x_anchor if odd_x_anchor is not None else 0
                else:  # right
                    x_odd = (odd_x_anchor - odd_text_width) if odd_x_anchor is not None else (width - odd_text_width)
                
                # Calculate Y position for odd_value
                if odd_v_align == 'top':
                    y_odd = odd_y_anchor if odd_y_anchor is not None else 0
                else:  # bottom
                    y_odd = (odd_y_anchor - odd_text_height) if odd_y_anchor is not None else (height - odd_text_height)
                
                # Draw odd_value with specified color
                odd_color_tuple = tuple(odd_color) if isinstance(odd_color, list) else odd_color
                print(f"Drawing odd_value '{odd_value}' at position ({x_odd}, {y_odd}), align: {odd_h_align}-{odd_v_align}, color: {odd_color_tuple}")
                draw.text((x_odd, y_odd), str(odd_value), font=font_large, fill=odd_color_tuple)
            
            # DRAW WORDS
            if words:
                words_color_tuple = tuple(text_color) if isinstance(text_color, list) else text_color
                
                # Calculate total height of words
                total_words_height = 0
                for i, word in enumerate(words):
                    if i == 0 or i == 1:
                        temp_font = font_small if font_small else font_large
                    else:  # i == 2 (third line)
                        temp_font = font_small_italic if font_small_italic else (font_small if font_small else font_large)
                    
                    bbox = draw.textbbox((0, 0), word, font=temp_font)
                    total_words_height += bbox[3] - bbox[1]
                    if i < len(words) - 1:
                        total_words_height += spacing_between_lines
                
                # Calculate starting Y position for words
                if text_v_align == 'top':
                    current_y = text_y_anchor if text_y_anchor is not None else 0
                else:  # bottom
                    current_y = (text_y_anchor - total_words_height) if text_y_anchor is not None else (height - total_words_height)
                
                # Draw each word
                for i, word in enumerate(words):
                    # Use small font for first two lines, italic for third line
                    if i == 0 or i == 1:
                        font = font_small if font_small else font_large
                        font_style = 'normal'
                    else:  # i == 2 (third line)
                        font = font_small_italic if font_small_italic else (font_small if font_small else font_large)
                        font_style = 'italic'
                    
                    # Calculate text dimensions
                    bbox = draw.textbbox((0, 0), word, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    
                    # Calculate X position for word
                    if text_h_align == 'left':
                        x = text_x_anchor if text_x_anchor is not None else 0
                    else:  # right
                        x = (text_x_anchor - text_width) if text_x_anchor is not None else (width - text_width)
                    
                    # Draw text with specified color
                    print(f"Drawing word '{word}' at position ({x}, {current_y}), font: {font_style}, color: {words_color_tuple}")
                    draw.text((x, current_y), word, font=font, fill=words_color_tuple)
                    
                    # Update Y position for next word
                    current_y += text_height
                    if i < len(words) - 1:
                        current_y += spacing_between_lines

        # Convert back to RGB for saving
        img = img.convert('RGB')
        
        # Create temporary file for original output
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
            temp_path = temp_file.name
        
        # Save the original image to temp path
        img.save(temp_path, 'PNG', quality=95)
        
        # Create web-optimized version for SEO (use original size if <= 850, otherwise scale to 850)
        web_width = min(width, 850)
        web_height = int(height * (web_width / width))
        img_web = img.resize((web_width, web_height), Image.Resampling.LANCZOS) if web_width < width else img
        
        # Create temporary file for web version
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file_web:
            temp_path_web = temp_file_web.name
        
        # Save web-optimized version as JPEG
        img_web.save(temp_path_web, 'JPEG', quality=85, optimize=True)
        
        print(f"✓ Created images")
        print(f"  • Original: {width}x{height}px - {temp_path}")
        print(f"  • Web: {web_width}x{web_height}px - {temp_path_web}")
        
        return {
            "status": True,
            "data": {
                "path": temp_path,
                "path_web": temp_path_web,
                "width": width,
                "height": height,
                "web_width": web_width,
                "web_height": web_height
            }
        }

    except Exception as e:
        print(f"Error creating image: {e}")
        return {
            "status": False,
            "data": {},
            "error": {"code": 500, "message": str(e)}
        }

if __name__ == "__main__":
    # Example usage
    request_data = {
        "params": {
            "width": 850,
            "height": 567,
            "assets_image_background": None,
            "assets_font_black_path": None,
            "odd_position": {"left": "6%", "top": "6%", "right": "auto", "bottom": "auto"},
            "text_position": {"left": "20%", "top": "26%", "right": "auto", "bottom": "auto"},
            "odd_color": [0, 0, 0, 255],  # Black (RGBA)
            "text_color": [93, 173, 226, 255],  # Light blue (RGBA)
            "odd_value": "1.58",
            "words": ["SANTOS", "PARA VENCER", "EM CASA"]
        }
    }
    result = create_image(request_data)
    print(f"\nResult: {result}")
