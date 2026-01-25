import os
import re
import tempfile
import subprocess
import json
from pathlib import Path

# yt-dlp library (installed from requirements.txt)
# This connector uses yt-dlp CLI via subprocess for maximum compatibility
try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False


def validate_youtube_url(url):
    """Validate YouTube URL format"""
    youtube_regex = r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/live/)([a-zA-Z0-9_-]{11})'
    match = re.match(youtube_regex, url)
    if match:
        return match.group(4)  # Return video ID
    return None


def clean_vtt_content(vtt_content):
    """Clean VTT content to remove timestamps and formatting"""
    lines = vtt_content.split('\n')
    cleaned_lines = []
    prev_line = None
    
    for line in lines:
        stripped = line.strip()
        
        # Skip empty lines, WEBVTT header, metadata
        if not stripped:
            continue
        if stripped.startswith('WEBVTT'):
            continue
        if stripped.startswith('Kind:'):
            continue
        if stripped.startswith('Language:'):
            continue
        
        # Skip timestamp lines (format: 00:00:00.000 --> 00:00:03.000)
        if re.match(r'^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}', stripped):
            continue
        
        # Skip line numbers
        if stripped.isdigit():
            continue
        
        # Remove HTML tags
        stripped = re.sub(r'<[^>]*>', '', stripped)
        
        # Normalize whitespace
        stripped = re.sub(r'\s+', ' ', stripped)
        
        # Skip duplicates
        if stripped and stripped != prev_line:
            cleaned_lines.append(stripped)
            prev_line = stripped
    
    return ' '.join(cleaned_lines)


def get_video_info(video_url):
    """Get video metadata using yt-dlp"""
    try:
        cmd = [
            'yt-dlp',
            '--dump-json',
            '--skip-download',
            video_url
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return None
            
        info = json.loads(result.stdout)
        return {
            'video_id': info.get('id'),
            'title': info.get('title'),
            'duration': info.get('duration'),
            'description': info.get('description'),
            'upload_date': info.get('upload_date')
        }
    except Exception:
        return None


def extract_transcript(request_data):
    """
    Extract clean transcript from YouTube video (no timestamps)

    Input (via workflow):
    {
        "params": {
            "video_url": "https://www.youtube.com/watch?v=VIDEO_ID",  # Required
            "language": "pt",                                         # Optional (default: auto)
            "format": "text"                                          # Optional: text|vtt|srt
        }
    }

    Output:
    {
        "status": True,
        "data": {
            "transcript": "Full clean transcript text...",
            "video_id": "VIDEO_ID",
            "language": "pt",
            "word_count": 13161,
            "duration_seconds": 7200,
            "title": "Video Title"
        },
        "message": "Transcript extracted successfully"
    }
    """
    params = request_data.get("params", {})
    
    video_url = params.get("video_url")
    if not video_url:
        return {
            "status": False,
            "message": "video_url is required",
            "data": {}
        }
    
    # Validate URL
    video_id = validate_youtube_url(video_url)
    if not video_id:
        return {
            "status": False,
            "message": "Invalid YouTube URL format",
            "data": {}
        }
    
    language = params.get("language", "en")
    output_format = params.get("format", "text")
    
    # Create temporary directory for downloads
    with tempfile.TemporaryDirectory() as temp_dir:
        output_template = os.path.join(temp_dir, "transcript")
        
        try:
            # Download subtitles using yt-dlp
            cmd = [
                'yt-dlp',
                '--write-auto-sub',
                '--write-sub',
                '--skip-download',
                '--sub-lang', f'{language},en',
                '--sub-format', 'vtt',
                '-o', output_template,
                video_url
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                if "no subtitles" in error_msg.lower() or "no automatic captions" in error_msg.lower():
                    return {
                        "status": False,
                        "message": "No subtitles available for this video",
                        "data": {"video_id": video_id}
                    }
                return {
                    "status": False,
                    "message": f"yt-dlp error: {error_msg[:200]}",
                    "data": {"video_id": video_id}
                }
            
            # Find downloaded VTT file
            vtt_files = list(Path(temp_dir).glob("*.vtt"))
            if not vtt_files:
                return {
                    "status": False,
                    "message": "No subtitle files downloaded",
                    "data": {"video_id": video_id}
                }
            
            # Read VTT content
            vtt_file = vtt_files[0]
            with open(vtt_file, 'r', encoding='utf-8') as f:
                vtt_content = f.read()
            
            # Get video info
            video_info = get_video_info(video_url) or {}
            
            # Determine actual language from filename
            detected_lang = language
            filename = vtt_file.name
            if '.en.' in filename:
                detected_lang = 'en'
            elif f'.{language}.' in filename:
                detected_lang = language
            
            # Clean transcript
            if output_format == "vtt":
                transcript = vtt_content
            else:
                transcript = clean_vtt_content(vtt_content)
            
            # Calculate word count
            word_count = len(transcript.split())
            
            return {
                "status": True,
                "data": {
                    "transcript": transcript,
                    "video_id": video_id,
                    "language": detected_lang,
                    "word_count": word_count,
                    "duration_seconds": video_info.get('duration'),
                    "title": video_info.get('title'),
                    "format": output_format
                },
                "message": "Transcript extracted successfully"
            }
            
        except subprocess.TimeoutExpired:
            return {
                "status": False,
                "message": "Request timeout - video may be too long or unavailable",
                "data": {"video_id": video_id}
            }
        except Exception as e:
            return {
                "status": False,
                "message": f"Error extracting transcript: {str(e)}",
                "data": {"video_id": video_id}
            }


def extract_transcript_with_timestamps(request_data):
    """
    Extract transcript with timestamps (VTT format)

    Input: Same as extract_transcript

    Output: Includes vtt_content with timestamps
    """
    params = request_data.get("params", {})

    # Force VTT format
    params_copy = params.copy()
    params_copy["format"] = "vtt"

    request_data_copy = {"params": params_copy}
    result = extract_transcript(request_data_copy)
    
    if result.get("status"):
        result["data"]["vtt_content"] = result["data"]["transcript"]
        # Also provide cleaned version
        result["data"]["transcript_clean"] = clean_vtt_content(result["data"]["transcript"])
    
    return result


def get_available_languages(request_data):
    """
    Get available subtitle languages for a YouTube video

    Input (via workflow):
    {
        "params": {
            "video_url": "https://www.youtube.com/watch?v=VIDEO_ID"
        }
    }

    Output:
    {
        "status": True,
        "data": {
            "languages": ["pt", "en", "es"],
            "auto_generated": ["pt"],
            "manual": ["en", "es"],
            "video_id": "VIDEO_ID"
        },
        "message": "Languages retrieved successfully"
    }
    """
    params = request_data.get("params", {})
    video_url = params.get("video_url")
    if not video_url:
        return {
            "status": False,
            "message": "video_url is required",
            "data": {}
        }
    
    # Validate URL
    video_id = validate_youtube_url(video_url)
    if not video_id:
        return {
            "status": False,
            "message": "Invalid YouTube URL format",
            "data": {}
        }
    
    try:
        # List available subtitles
        cmd = [
            'yt-dlp',
            '--list-subs',
            '--skip-download',
            video_url
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return {
                "status": False,
                "message": "Failed to retrieve subtitle information",
                "data": {"video_id": video_id}
            }
        
        output = result.stdout
        
        # Parse available languages
        auto_generated = []
        manual = []
        
        # Look for language codes in the output
        lines = output.split('\n')
        in_auto_section = False
        in_manual_section = False
        
        for line in lines:
            line_lower = line.lower()
            
            if 'automatic captions' in line_lower:
                in_auto_section = True
                in_manual_section = False
                continue
            elif 'available subtitles' in line_lower:
                in_manual_section = True
                in_auto_section = False
                continue
            
            # Extract language code (usually 2-3 letter codes at start of line)
            match = re.match(r'^([a-z]{2,3})\s', line)
            if match:
                lang_code = match.group(1)
                if in_auto_section and lang_code not in auto_generated:
                    auto_generated.append(lang_code)
                elif in_manual_section and lang_code not in manual:
                    manual.append(lang_code)
        
        all_languages = sorted(set(auto_generated + manual))
        
        return {
            "status": True,
            "data": {
                "languages": all_languages,
                "auto_generated": sorted(auto_generated),
                "manual": sorted(manual),
                "video_id": video_id
            },
            "message": "Languages retrieved successfully"
        }
        
    except subprocess.TimeoutExpired:
        return {
            "status": False,
            "message": "Request timeout",
            "data": {"video_id": video_id}
        }
    except Exception as e:
        return {
            "status": False,
            "message": f"Error retrieving languages: {str(e)}",
            "data": {"video_id": video_id}
        }
