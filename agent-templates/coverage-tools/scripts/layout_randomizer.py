import random

def randomize_layout(request_data):
    """
    Randomly select a layout from the available options.
    
    Args:
        request_data: Dictionary containing:
            - params: Dictionary with:
                - layout-options: List of layout configurations with layout_id, layout_name, layout_image, odd_position
    
    Returns:
        Dictionary with status and randomly selected layout
    """
    params = request_data.get("params", {})
    layout_options = params.get("layout-options", [])
    
    if not layout_options:
        return {
            "status": False,
            "message": "No layout options provided.",
            "data": {},
            "error": {"code": 400, "message": "layout-options is required"}
        }
    
    # Randomly select a layout
    selected_layout = random.choice(layout_options)
    
    return {
        "status": True,
        "message": f"Layout '{selected_layout.get('layout_name')}' selected successfully.",
        "data": {"layout-selected": selected_layout},
    }
