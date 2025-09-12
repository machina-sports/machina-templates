import json
from typing import Any, Dict


def _get_by_pointer(data: Any, pointer: str | None) -> Any:
    if not pointer:
        return data
    current = data
    for part in pointer.split('.'):
        if part == '':
            continue
        if isinstance(current, list):
            try:
                idx = int(part)
            except ValueError:
                raise ValueError(f"Pointer segment '{part}' is not a list index")
            if idx < 0 or idx >= len(current):
                raise IndexError(f"List index out of range at '{part}'")
            current = current[idx]
        elif isinstance(current, dict):
            if part not in current:
                raise KeyError(f"Key '{part}' not found in object")
            current = current[part]
        else:
            raise TypeError("Pointer traversal hit non-indexable type")
    return current


def read_json_file(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Read a JSON file from local path and optionally extract a nested object using a dot pointer.

    params:
      - file_path: absolute or relative path to JSON file
      - json_pointer: optional dot path (e.g., "0.value") to extract a nested object
    """
    params = request_data.get("params", {})
    file_path = params.get("file_path")
    pointer = params.get("json_pointer")

    if not file_path:
        return {"status": False, "message": "Missing file_path."}

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # If no pointer, but data looks like [ { value: {...} } ], try to return first.value
        if pointer is None and isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict) and isinstance(first.get('value'), dict):
                return {"status": True, "data": first["value"], "message": "JSON loaded (auto first.value)."}
        # If pointer provided, use it
        if pointer is not None:
            node = _get_by_pointer(data, pointer)
            return {"status": True, "data": node, "message": "JSON loaded (by pointer)."}
        return {"status": True, "data": data, "message": "JSON loaded."}
    except Exception as e:
        return {"status": False, "message": f"Exception reading JSON: {e}"}


def read_json_by_id(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Read a JSON array and return the entry matching a document id, optionally extracting a nested pointer.

    params:
      - file_path: path to JSON file containing an array of documents
      - object_id: string to match against id_path
      - id_path: dot path to id field (default: "_id.$oid")
      - json_pointer: optional nested pointer to extract from the matched object (e.g., "value")
    """
    params = request_data.get("params", {})
    file_path = params.get("file_path")
    object_id = params.get("object_id")
    id_path = params.get("id_path", "_id.$oid")
    pointer = params.get("json_pointer")

    if not file_path or not object_id:
        return {"status": False, "message": "Missing file_path or object_id."}

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list):
            return {"status": False, "message": "JSON root is not a list."}

        for entry in data:
            try:
                id_value = _get_by_pointer(entry, id_path)
            except Exception:
                continue
            if id_value == object_id:
                node = entry
                if pointer is not None:
                    try:
                        node = _get_by_pointer(entry, pointer)
                    except Exception as e:
                        return {"status": False, "message": f"Pointer error: {e}"}
                return {"status": True, "data": node, "message": "JSON loaded (by id)."}

        return {"status": False, "message": f"Object id not found: {object_id}"}
    except Exception as e:
        return {"status": False, "message": f"Exception reading JSON: {e}"}


