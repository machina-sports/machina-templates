def consolidate_videos(request_data):
    """
    Consolidate multiple video files into a single MP4 video.
    Returns in the standard pyscript pattern: {status, data, message}
    
    Parameters:
        video_paths: List of video file paths in order to concatenate
        output_filename: Optional output filename (default: consolidated_podcast.mp4)
    
    The videos are concatenated in the exact order provided.
    Uses moviepy for video processing with fallback to ffmpeg CLI.
    """
    try:
        import json
        import os
        import tempfile
        import subprocess
        
        # Parse request_data
        if isinstance(request_data, str):
            try:
                request_data = json.loads(request_data)
            except:
                pass
        
        if not isinstance(request_data, dict):
            request_data = {}
        
        # Get params from request_data (standard pyscript pattern)
        params = request_data.get('params', request_data)
        if not isinstance(params, dict):
            params = {}
        
        video_paths = params.get('video_paths', [])
        output_filename = params.get('output_filename', 'consolidated_podcast.mp4')
        
        if not video_paths or len(video_paths) == 0:
            return {
                "status": False,
                "data": {"error": "No video paths provided"},
                "message": "No video paths provided for consolidation"
            }
        
        # Filter out None/empty paths and verify files exist
        valid_paths = []
        missing_paths = []
        for path in video_paths:
            if path and isinstance(path, str):
                if os.path.exists(path):
                    valid_paths.append(path)
                else:
                    missing_paths.append(path)
        
        if len(valid_paths) == 0:
            return {
                "status": False,
                "data": {"error": "No valid video files found", "missing_paths": missing_paths},
                "message": f"No valid video files found. Missing: {missing_paths}"
            }
        
        print(f"🎬 Consolidating {len(valid_paths)} videos...")
        for i, path in enumerate(valid_paths):
            print(f"  {i+1}. {os.path.basename(path)}")
        
        # Create output path in temp directory
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, output_filename)
        
        # Try moviepy first, fallback to ffmpeg CLI
        consolidated = False
        method_used = None
        
        # Method 1: Try moviepy
        try:
            from moviepy.editor import VideoFileClip, concatenate_videoclips
            
            print("📦 Using moviepy for video concatenation...")
            
            clips = []
            for path in valid_paths:
                print(f"  Loading: {os.path.basename(path)}")
                clip = VideoFileClip(path)
                clips.append(clip)
            
            print("🔗 Concatenating clips...")
            final_clip = concatenate_videoclips(clips, method="compose")
            
            print(f"💾 Writing consolidated video to: {output_path}")
            final_clip.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=os.path.join(temp_dir, 'temp_audio.m4a'),
                remove_temp=True,
                verbose=False,
                logger=None
            )
            
            # Close all clips to free resources
            for clip in clips:
                clip.close()
            final_clip.close()
            
            consolidated = True
            method_used = "moviepy"
            
        except ImportError:
            print("⚠️ moviepy not available, trying ffmpeg CLI...")
        except Exception as e:
            print(f"⚠️ moviepy failed: {e}, trying ffmpeg CLI...")
        
        # Method 2: Fallback to ffmpeg CLI
        if not consolidated:
            try:
                print("📦 Using ffmpeg CLI for video concatenation...")
                
                # Create a temporary file list for ffmpeg
                list_file_path = os.path.join(temp_dir, 'video_list.txt')
                with open(list_file_path, 'w') as f:
                    for path in valid_paths:
                        # Escape single quotes and write in ffmpeg concat format
                        escaped_path = path.replace("'", "'\\''")
                        f.write(f"file '{escaped_path}'\n")
                
                print(f"  Created file list: {list_file_path}")
                
                # Run ffmpeg concat
                cmd = [
                    'ffmpeg', '-y',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', list_file_path,
                    '-c', 'copy',
                    output_path
                ]
                
                print(f"  Running: {' '.join(cmd)}")
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    # Try re-encoding if copy fails
                    print("⚠️ Copy mode failed, trying re-encode...")
                    cmd = [
                        'ffmpeg', '-y',
                        '-f', 'concat',
                        '-safe', '0',
                        '-i', list_file_path,
                        '-c:v', 'libx264',
                        '-c:a', 'aac',
                        '-preset', 'fast',
                        output_path
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        raise Exception(f"ffmpeg failed: {result.stderr}")
                
                # Clean up temp file
                os.remove(list_file_path)
                
                consolidated = True
                method_used = "ffmpeg"
                
            except FileNotFoundError:
                return {
                    "status": False,
                    "data": {"error": "Neither moviepy nor ffmpeg available"},
                    "message": "Video consolidation requires moviepy or ffmpeg. Please install one of them."
                }
            except Exception as e:
                return {
                    "status": False,
                    "data": {"error": str(e)},
                    "message": f"ffmpeg consolidation failed: {e}"
                }
        
        if not consolidated:
            return {
                "status": False,
                "data": {"error": "All consolidation methods failed"},
                "message": "Failed to consolidate videos with any available method"
            }
        
        # Get file info
        file_size = os.path.getsize(output_path)
        file_size_mb = round(file_size / (1024 * 1024), 2)
        
        print(f"✅ Video consolidated successfully!")
        print(f"  Output: {output_path}")
        print(f"  Size: {file_size_mb} MB")
        print(f"  Method: {method_used}")
        
        return {
            "status": True,
            "data": {
                "video_path": output_path,
                "filename": output_filename,
                "file_size_bytes": file_size,
                "file_size_mb": file_size_mb,
                "input_video_count": len(valid_paths),
                "method_used": method_used,
                "missing_paths": missing_paths if missing_paths else None
            },
            "message": f"Successfully consolidated {len(valid_paths)} videos into {output_filename} ({file_size_mb} MB)"
        }
        
    except Exception as e:
        return {
            "status": False,
            "data": {"error": str(e)},
            "message": f"Video consolidation exception: {str(e)}"
        }
