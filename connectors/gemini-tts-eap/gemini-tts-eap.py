import json
import base64
import urllib.request
import tempfile
import wave
import uuid

def generate_speech(request_data):
    """
    Generates TTS using the Gemini 3.1 Flash TTS EAP endpoint.
    
    Parameters:
    - text: Required - Text content (supports inline tags like [shouting], [sighs]).
    - voice_name: Voice to use (default: "Puck").
    
    Headers:
    - api_key: AI Studio API Key.
    """
    params = request_data.get("params", {})
    headers = request_data.get("headers", {})
    
    api_key = headers.get("api_key")
    if not api_key:
        return {"status": False, "message": "Missing api_key in headers"}
        
    text = params.get("text")
    if not text:
        return {"status": False, "message": "Missing text parameter"}
        
    voice_name = params.get("voice_name") or "Puck"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-tts-eap:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice_name
                    }
                }
            }
        }
    }
    
    req = urllib.request.Request(url, method="POST", headers={"Content-Type": "application/json"})
    
    try:
        response = urllib.request.urlopen(req, data=json.dumps(payload).encode("utf-8"))
        data = json.loads(response.read().decode("utf-8"))
        
        inline_data = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        pcm_data = base64.b64decode(inline_data)
        
        file_path = f"{tempfile.gettempdir()}/gemini_tts_{uuid.uuid4().hex}.wav"
        
        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(pcm_data)
            
        return {
            "status": True,
            "message": "Audio generated successfully",
            "file_path": file_path,
            "voice": voice_name
        }
        
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        return {"status": False, "message": f"API Error: {e.code} - {error_msg}"}
    except Exception as e:
        return {"status": False, "message": f"Exception: {str(e)}"}
