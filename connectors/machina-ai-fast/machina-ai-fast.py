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

    # Optional per-call timeout (seconds). Values larger than 600 are
    # interpreted as milliseconds for backwards compatibility with workflows
    # that already set e.g. `timeout: 20000`.
    timeout_param = params.get("timeout")
    timeout_seconds = None
    if timeout_param is not None:
        try:
            timeout_seconds = float(timeout_param)
            if timeout_seconds > 600:
                timeout_seconds = timeout_seconds / 1000.0
        except (TypeError, ValueError):
            timeout_seconds = None

    try:
        llm_kwargs = {"api_key": api_key, "model_name": model_name}
        if timeout_seconds is not None:
            llm_kwargs["timeout"] = timeout_seconds
        llm = ChatGroq(**llm_kwargs)
    except Exception as e:
        return {"status": "error", "message": f"Exception when creating model: {e}"}

    return {"status": True, "data": llm, "message": "Model loaded."}

