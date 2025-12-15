import os

def read_file(params):
    file_path = params.get("file_path")
    if not file_path:
        return {"error": "file_path is required"}
    
    # Handle relative paths from workspace root if needed, 
    # but usually the execution context allows simple paths.
    # We will assume the path provided is correct relative to CWD or absolute.
    
    try:
        if not os.path.exists(file_path):
             return {"error": f"File not found: {file_path}"}
             
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        return {"error": str(e)}
