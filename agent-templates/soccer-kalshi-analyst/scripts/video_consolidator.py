def consolidate_videos(request_data):
    """
    Consolidate multiple video files into a single MP4 video.
    Returns in the standard pyscript pattern: {status, data, message}
    
    Parameters:
        video_paths: List of video file paths in order to concatenate
        output_filename: Optional output filename (default: consolidated_podcast.mp4)
    
    The videos are concatenated in the exact order provided.
    Uses moviepy for video processing.
    """
    try:
        import json
        import os
        import tempfile
        
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
        
        # Use moviepy for video concatenation (supports MoviePy 2.x and 1.x)
        try:
            # MoviePy 2.x removed `moviepy.editor`; prefer top-level imports.
            try:
                from moviepy import VideoFileClip, concatenate_videoclips  # type: ignore
            except Exception:
                # Backwards compatibility with MoviePy 1.x
                from moviepy.editor import VideoFileClip, concatenate_videoclips  # type: ignore
        except ImportError as e:
            return {
                "status": False,
                "data": {
                    "error": "moviepy not available",
                    "details": str(e),
                },
                "message": "Video consolidation requires moviepy. Please install it: pip install moviepy",
            }
        
        print("📦 Using moviepy for video concatenation...")
        
        clips = []
        try:
            # Load all clips first
            for path in valid_paths:
                print(f"  Loading: {os.path.basename(path)}")
                try:
                    clip = VideoFileClip(path)
                    clips.append(clip)
                    print(f"    ✓ Loaded: {clip.duration:.2f}s, {clip.size[0]}x{clip.size[1]}")
                except Exception as e:
                    print(f"    ✗ Failed to load {os.path.basename(path)}: {e}")
                    # Close already loaded clips before failing
                    for c in clips:
                        try:
                            c.close()
                        except:
                            pass
                    raise Exception(f"Failed to load video {os.path.basename(path)}: {e}")
            
            if len(clips) == 0:
                raise Exception("No clips were successfully loaded")
            
            print(f"🔗 Concatenating {len(clips)} clips...")
            # Use 'compose' method to handle different resolutions/codecs
            final_clip = concatenate_videoclips(clips, method="compose")
            
            print(f"💾 Writing consolidated video to: {output_path}")
            # Use threads=1 for better compatibility, preset='medium' for balance
            final_clip.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=os.path.join(temp_dir, 'temp_audio.m4a'),
                remove_temp=True,
                logger=None,
                threads=1,
                preset='medium'
            )
            
            # Close all clips to free resources
            print("🧹 Cleaning up resources...")
            for clip in clips:
                try:
                    clip.close()
                except:
                    pass
            try:
                final_clip.close()
            except:
                pass
            
            print("✅ moviepy consolidation successful!")
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            # Clean up any partially loaded clips
            for clip in clips:
                try:
                    clip.close()
                except:
                    pass
            return {
                "status": False,
                "data": {
                    "error": str(e),
                    "traceback": error_trace[:500]
                },
                "message": f"Video consolidation failed: {e}"
            }
        
        # Get file info
        file_size = os.path.getsize(output_path)
        file_size_mb = round(file_size / (1024 * 1024), 2)
        
        print(f"✅ Video consolidated successfully!")
        print(f"  Output: {output_path}")
        print(f"  Size: {file_size_mb} MB")
        
        return {
            "status": True,
            "data": {
                "video_path": output_path,
                "filename": output_filename,
                "file_size_bytes": file_size,
                "file_size_mb": file_size_mb,
                "input_video_count": len(valid_paths),
                "method_used": "moviepy",
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
