from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from openai import OpenAI


def invoke_embedding(params):

    api_key = params.get("api_key", "")

    model_name = params.get("model_name")

    organization = params.get("organization") or params.get("org_id")

    project = params.get("project") or params.get("project_id")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    if not model_name:
        return {"status": "error", "message": "Model name is required."}

    kwargs = {"api_key": api_key, "model": model_name}

    if organization:
        kwargs["organization"] = organization

    if project:
        kwargs["default_headers"] = {"OpenAI-Project": project}

    try:
        llm = OpenAIEmbeddings(**kwargs)

    except Exception as e:
        return {"status": "error", "message": f"Exception when creating model: {e}"}

    return {"status": True, "data": llm, "message": "Model loaded."}


def invoke_prompt(params):

    api_key = params.get("api_key")

    model_name = params.get("model_name")

    organization = params.get("organization") or params.get("org_id")

    project = params.get("project") or params.get("project_id")

    base_url = params.get("base_url")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    if not model_name:
        return {"status": "error", "message": "Model name is required."}

    kwargs = {"model": model_name, "api_key": api_key}

    if organization:
        kwargs["organization"] = organization

    if project:
        kwargs["default_headers"] = {"OpenAI-Project": project}

    if base_url:
        kwargs["base_url"] = base_url

    try:
        llm = ChatOpenAI(**kwargs)

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
