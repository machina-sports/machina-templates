"""Google Speech-to-Text connector with bounded media and credential handling."""

import json
import os
from pathlib import Path
from urllib.parse import urlparse

MAX_AUDIO_BYTES = 25 * 1024 * 1024


def _failure(message):
    return {"status": False, "data": None, "message": message, "error": message}


def _credentials(raw):
    if not raw:
        return None
    # Arbitrary credential file paths are intentionally no longer accepted.
    try:
        info = json.loads(raw) if isinstance(raw, str) else raw
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    except Exception:
        raise ValueError("The configured Google credential is invalid.")


def _local_audio(path_value):
    path = Path(str(path_value)).expanduser().resolve()
    root = Path(os.getenv("MACHINA_WORK_DIR", os.getcwd())).expanduser().resolve()
    if path != root and root not in path.parents:
        raise ValueError("The audio path is outside the approved work directory.")
    if not path.is_file() or path.stat().st_size > MAX_AUDIO_BYTES:
        raise ValueError("The audio file is missing or exceeds the configured size limit.")
    return path.read_bytes()


def _gcs_https_parts(raw_url):
    parsed = urlparse(raw_url)
    if parsed.scheme != "https" or parsed.hostname != "storage.googleapis.com" or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Only authenticated Google Cloud Storage HTTPS media URLs are supported.")
    parts = parsed.path.lstrip("/").split("/", 1)
    if len(parts) != 2 or not all(parts):
        raise ValueError("The Google Cloud Storage media URL is invalid.")
    return parts


def invoke_transcribe(request_data):
    """Transcribe local or authenticated GCS audio without arbitrary downloads."""
    from google.cloud import speech_v1p1beta1 as speech

    request_data = request_data or {}
    params = request_data.get("params") or request_data
    headers = request_data.get("headers") or {}
    audio_path = params.get("audio_path") or params.get("audio-path")
    if isinstance(audio_path, list):
        audio_path = audio_path[0] if audio_path else None
    if not audio_path:
        return _failure("audio_path is required.")

    try:
        credentials = _credentials(headers.get("credential") or headers.get("api_key") or params.get("credential") or params.get("api_key"))
        client = speech.SpeechClient(credentials=credentials) if credentials else speech.SpeechClient()

        if str(audio_path).startswith("gs://"):
            audio = speech.RecognitionAudio(uri=audio_path)
        else:
            if str(audio_path).startswith(("http://", "https://")):
                bucket_name, blob_name = _gcs_https_parts(str(audio_path))
                from google.cloud import storage

                storage_client = storage.Client(credentials=credentials)
                blob = storage_client.bucket(bucket_name).blob(blob_name)
                blob.reload()
                if blob.size is not None and blob.size > MAX_AUDIO_BYTES:
                    return _failure("The audio file exceeds the configured size limit.")
                content = blob.download_as_bytes(timeout=30, checksum="auto")
                if len(content) > MAX_AUDIO_BYTES:
                    return _failure("The audio file exceeds the configured size limit.")
            else:
                content = _local_audio(audio_path)
            audio = speech.RecognitionAudio(content=content)

        config_params = {
            "language_code": params.get("language_code", "pt-BR"),
            "enable_automatic_punctuation": True,
        }
        alternative_languages = params.get("alternative_language_codes")
        if isinstance(alternative_languages, str):
            alternative_languages = [item.strip() for item in alternative_languages.split(",") if item.strip()]
        if alternative_languages:
            config_params["alternative_language_codes"] = alternative_languages
        encoding = params.get("encoding")
        if encoding:
            try:
                config_params["encoding"] = getattr(speech.RecognitionConfig.AudioEncoding, str(encoding).upper())
            except AttributeError:
                return _failure("The requested audio encoding is not supported.")
        else:
            config_params["encoding"] = speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED
        if params.get("sample_rate_hertz"):
            config_params["sample_rate_hertz"] = int(params["sample_rate_hertz"])

        response = client.recognize(config=speech.RecognitionConfig(**config_params), audio=audio)
        transcript = " ".join(result.alternatives[0].transcript for result in response.results if result.alternatives)
        confidence = max(
            (result.alternatives[0].confidence for result in response.results if result.alternatives),
            default=0.0,
        )
        return {
            "status": True,
            "data": {"transcript": transcript, "confidence": confidence},
            "message": "Transcription successful." if transcript else "No speech detected.",
        }
    except ValueError as error:
        return _failure(str(error))
    except Exception:
        return _failure("The configured Google Speech provider could not transcribe the audio.")
