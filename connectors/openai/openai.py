from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from openai import OpenAI


def list_models(params):
    """List available models from OpenAI API. Useful for testing credentials."""
    api_key = params.get("headers", {}).get("api_key") or params.get("params", {}).get("api_key") or params.get("api_key", "")

    if not api_key:
        return {"status": False, "message": "API key is required."}

    try:
        client = OpenAI(api_key=api_key)
        models = client.models.list()
        model_list = [{"id": m.id, "owned_by": m.owned_by} for m in models.data[:10]]
        return {"status": True, "data": {"models": model_list, "total_count": len(models.data)}, "message": "Models retrieved successfully."}
    except Exception as e:
        return {"status": False, "message": f"Error listing models: {str(e)}"}


def invoke_embedding(params):

    api_key = params.get("api_key", "")

    model_name = params.get("model_name")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    if not model_name:
        return {"status": "error", "message": "Model name is required."}

    try:
        llm = OpenAIEmbeddings(api_key=api_key, model=model_name)
        # llm = OpenAI(api_key=api_key)

    except Exception as e:
        return {"status": "error", "message": f"Exception when creating model: {e}"}

    return {"status": True, "data": llm, "message": "Model loaded."}


def invoke_prompt(params):

    api_key = params.get("api_key")

    model_name = params.get("model_name")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    if not model_name:
        return {"status": "error", "message": "Model name is required."}

    try:
        llm = ChatOpenAI(model=model_name, api_key=api_key)

    except Exception as e:
        return {"status": "error", "message": f"Exception when creating model: {e}"}

    return {"status": True, "data": llm, "message": "Model loaded."}


def transcribe_audio_to_text(params):
    """
    Transcribe an audio file to text using the new OpenAI Whisper transcription API.

    :param params: Dictionary containing the 'api_key' and 'audio-path' parameters.
    :return: Transcribed text or error message.
    """

    api_key = params.get("headers").get("api_key")
    file_items = params.get("params").get("audio-path", [])

    audio_file_path = file_items[0]

    try:

        llm = OpenAI(api_key=api_key)

        with open(audio_file_path, "rb") as audio_file:
            print(f"Transcribing file: {audio_file_path}")

            transcript = llm.audio.transcriptions.create(
              model="whisper-1",
              file=audio_file
            )

        return {"status": True, "data": transcript.text}

    except Exception as e:
        return {"status": False, "message": f"Exception when transcribing audio: {e}"} 
