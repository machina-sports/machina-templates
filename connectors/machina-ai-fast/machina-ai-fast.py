from langchain_groq import ChatGroq

def invoke_embedding(params):

    api_key = params.get("api_key", "")

    model_name = params.get("model_name", "llama2-70b-4096")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    try:
        llm = ChatGroq(
            api_key=api_key,
            model_name=model_name
        )
    except Exception as e:
        return {"status": "error", "message": f"Exception when creating model: {e}"}

    return {"status": True, "data": llm, "message": "Model loaded."}


def invoke_prompt(params):

    api_key = params.get("api_key")

    model_name = params.get("model_name", "llama2-70b-4096")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    try:
        llm = ChatGroq(
            api_key=api_key,
            model_name=model_name
        )
    except Exception as e:
        return {"status": "error", "message": f"Exception when creating model: {e}"}

    return {"status": True, "data": llm, "message": "Model loaded."}

