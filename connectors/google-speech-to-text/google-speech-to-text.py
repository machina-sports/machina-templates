import json
import os
import tempfile
import requests

def invoke_transcribe(request_data):
    """
    Transcribe audio using Google Cloud Speech-to-Text (v1p1beta1 for better compressed audio support).
    """
    # Use v1p1beta1 for better support of MP3/M4A/AAC
    from google.cloud import speech_v1p1beta1 as speech
    
    params = request_data.get("params", {})
    headers = request_data.get("headers", {})
    
    audio_path = params.get("audio_path")
    language_code = params.get("language_code", "pt-BR")
    encoding_input = params.get("encoding")
    sample_rate_hertz = params.get("sample_rate_hertz")
    
    # api_key can be in headers or params
    api_key = headers.get("api_key") or params.get("api_key")
    
    if not audio_path:
        return {"status": False, "message": "audio_path is required."}
    
    if not api_key:
        return {"status": False, "message": "API key (Service Account JSON) is required."}
    
    temp_sa_path = None
    temp_audio_path = None
    
    try:
        # Handle Service Account JSON
        service_account_info = None
        if isinstance(api_key, dict):
            service_account_info = api_key
        else:
            try:
                service_account_info = json.loads(api_key)
            except (json.JSONDecodeError, TypeError):
                if os.path.exists(str(api_key)):
                    with open(api_key, 'r') as f:
                        service_account_info = json.load(f)
                else:
                    return {"status": False, "message": "Invalid service account JSON or file path in api_key"}
            
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_sa:
            json.dump(service_account_info, temp_sa)
            temp_sa_path = temp_sa.name
            
        client = speech.SpeechClient.from_service_account_json(temp_sa_path)
        
        audio = None
        
        # Handle Audio Path
        if audio_path.startswith("gs://"):
            # Use Google Cloud Storage URI directly
            audio = speech.RecognitionAudio(uri=audio_path)
            
        elif audio_path.startswith(('http://', 'https://')):
            try:
                # Basic check for Google Drive viewer links
                if "drive.google.com" in audio_path and "/view" in audio_path:
                    return {"status": False, "message": "Google Drive viewer links are not supported. Use a direct download link or a local file."}
                
                # Check if it's a GCS URL to use the authenticated client
                is_gcs_url = False
                if "storage.googleapis.com" in audio_path:
                    is_gcs_url = True
                    # Format: https://storage.googleapis.com/bucket-name/object-path
                    import urllib.parse
                    parsed_url = urllib.parse.urlparse(audio_path)
                    path_parts = parsed_url.path.lstrip("/").split("/", 1)
                    if len(path_parts) >= 2:
                        source_bucket_name = path_parts[0]
                        source_blob_name = path_parts[1]
                        
                        from google.cloud import storage
                        storage_client = storage.Client.from_service_account_json(temp_sa_path)
                        source_bucket = storage_client.bucket(source_bucket_name)
                        source_blob = source_bucket.blob(source_blob_name)
                        
                        with tempfile.NamedTemporaryFile(delete=False) as temp_audio:
                            source_blob.download_to_filename(temp_audio.name)
                            temp_audio_path = temp_audio.name
                    else:
                        is_gcs_url = False

                if not is_gcs_url:
                    response = requests.get(audio_path)
                    response.raise_for_status()
                    
                    # Check if it's actually an audio/binary file and not HTML
                    content_type = response.headers.get('Content-Type', '').lower()
                    if 'text/html' in content_type:
                        return {"status": False, "message": f"The URL returned an HTML page instead of an audio file. Content-Type: {content_type}"}

                    with tempfile.NamedTemporaryFile(delete=False) as temp_audio:
                        temp_audio.write(response.content)
                        temp_audio_path = temp_audio.name
            except Exception as e:
                return {"status": False, "message": f"Error downloading audio: {e}"}
        else:
            if not os.path.exists(audio_path):
                return {"status": False, "message": f"Audio file not found: {audio_path}. Remember that Docker only sees files inside the mapped volumes."}
            temp_audio_path = audio_path
            
        if not audio:
            # Read the audio file if not using GCS URI
            with open(temp_audio_path, "rb") as audio_file:
                content = audio_file.read()
            audio = speech.RecognitionAudio(content=content)
        
        # Configure transcription using v1p1beta1 features
        config_params = {
            "language_code": language_code,
            "enable_automatic_punctuation": True,
        }

        # Support for alternative language codes (for multi-language detection)
        alt_langs = params.get("alternative_language_codes")
        if alt_langs:
            if isinstance(alt_langs, str):
                alt_langs = [l.strip() for l in alt_langs.split(",") if l.strip()]
            config_params["alternative_language_codes"] = alt_langs

        # For v1p1beta1, ENCODING_UNSPECIFIED works great for most compressed formats
        if not encoding_input:
            config_params["encoding"] = speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED
        else:
            try:
                config_params["encoding"] = getattr(speech.RecognitionConfig.AudioEncoding, encoding_input.upper())
            except AttributeError:
                pass
                
        if sample_rate_hertz:
            config_params["sample_rate_hertz"] = int(sample_rate_hertz)
            
        config = speech.RecognitionConfig(**config_params)
        
        # Perform transcription
        response = client.recognize(config=config, audio=audio)
        
        transcript = ""
        confidence = 0.0
        
        for result in response.results:
            transcript += result.alternatives[0].transcript
            confidence = max(confidence, result.alternatives[0].confidence)
            
        if not transcript:
            return {"status": True, "data": {"transcript": "", "confidence": 0.0}, "message": "No speech detected."}
            
        return {
            "status": True, 
            "data": {
                "transcript": transcript,
                "confidence": confidence
            },
            "message": "Transcription successful."
        }
        
    except Exception as e:
        return {"status": False, "message": f"Exception during transcription: {e}"}
        
    finally:
        if temp_sa_path and os.path.exists(temp_sa_path):
            os.unlink(temp_sa_path)
        if temp_audio_path and temp_audio_path != audio_path and os.path.exists(temp_audio_path):
            os.unlink(temp_audio_path)
