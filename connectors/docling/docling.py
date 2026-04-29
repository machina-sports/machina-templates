from langchain_docling import DoclingLoader
from typing import List, Optional, Dict, Any, Union


def invoke_loader(params):
    """
    Initialize and return a DoclingLoader instance.
    
    :param params: Dictionary containing the 'file_path' and optional parameters.
    :return: Loader instance or error message.
    """
    file_path = params.get("file_path")
    convert_kwargs = params.get("convert_kwargs", {})
    md_export_kwargs = params.get("md_export_kwargs", {})

    if not file_path:
        return {"status": "error", "message": "file_path is required."}

    # Convert single string path to list if necessary
    if isinstance(file_path, str):
        file_path = [file_path]

    try:
        loader = DoclingLoader(
            file_path=file_path,
            convert_kwargs=convert_kwargs,
            md_export_kwargs=md_export_kwargs
        )

        return {"status": True, "data": loader, "message": "Loader initialized successfully."}

    except Exception as e:
        return {"status": "error", "message": f"Exception when creating loader: {e}"}


def load_documents(params):
    """
    Load and process documents using the DoclingLoader.
    
    :param params: Dictionary containing the 'loader' instance.
    :return: Processed documents or error message.
    """
    loader = params.get("loader")

    if not loader:
        return {"status": "error", "message": "loader is required."}

    try:
        documents = loader.load()
        return {"status": True, "data": documents, "message": "Documents loaded successfully."}

    except Exception as e:
        return {"status": "error", "message": f"Exception when loading documents: {e}"} 
