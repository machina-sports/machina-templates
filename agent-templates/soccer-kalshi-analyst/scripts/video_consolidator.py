def consolidate_videos(request_data):
    """
    Consolidate multiple video files into a single MP4 video with audio overlap transitions.
    Returns in the standard pyscript pattern: {status, data, message}
    
    Parameters:
        video_paths: List of video file paths in order to concatenate
        output_filename: Optional output filename (default: consolidated_podcast.mp4)
        audio_overlap_seconds: Optional overlap duration in seconds (default: 0.75)
            Creates J-cut effect: next video's audio starts while previous video's image continues
    
    The videos are concatenated with smooth audio transitions where the next video's audio
    overlaps with the previous video's image for a more professional, seamless feel.
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
        audio_overlap_seconds = params.get('audio_overlap_seconds', 0.75)  # Default 0.75 seconds overlap
        
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
                from moviepy import VideoFileClip, concatenate_videoclips, CompositeAudioClip, CompositeVideoClip  # type: ignore
                MOVIEPY_V2 = True
            except Exception:
                # Backwards compatibility with MoviePy 1.x
                from moviepy.editor import VideoFileClip, concatenate_videoclips, CompositeAudioClip, CompositeVideoClip  # type: ignore
                MOVIEPY_V2 = False
        except ImportError as e:
            return {
                "status": False,
                "data": {
                    "error": "moviepy not available",
                    "details": str(e),
                },
                "message": "Video consolidation requires moviepy. Please install it: pip install moviepy",
            }
        
        print(f"📦 Using moviepy (v2 detected: {MOVIEPY_V2}) for video concatenation...")
        
        # Compatibility helpers
        def set_start(clip, t):
            return clip.with_start(t) if hasattr(clip, 'with_start') else clip.set_start(t)

        def set_audio(clip, audio):
            return clip.with_audio(audio) if hasattr(clip, 'with_audio') else clip.set_audio(audio)

        def set_duration(clip, t):
            return clip.with_duration(t) if hasattr(clip, 'with_duration') else clip.set_duration(t)
            
        def without_audio(clip):
            if hasattr(clip, 'without_audio'):
                return clip.without_audio()
            if hasattr(clip, 'with_audio'):
                return clip.with_audio(None)
            return clip.set_audio(None)
        
        def subclip(clip, start, end, file_path=None):
            """
            Compatibility wrapper for subclip method - works with MoviePy 1.x and 2.x
            MoviePy 1.x uses: clip.subclip(start, end)
            MoviePy 2.x uses: clip.subclipped(start, end) or clip[start:end]
            """
            # Try MoviePy 1.x method: subclip()
            if hasattr(clip, 'subclip'):
                try:
                    return clip.subclip(start, end)
                except Exception as e:
                    print(f"  Warning: clip.subclip() failed: {e}, trying MoviePy 2.x methods...")
            
            # Try MoviePy 2.x method: subclipped()
            if hasattr(clip, 'subclipped'):
                try:
                    return clip.subclipped(start, end)
                except Exception as e:
                    print(f"  Warning: clip.subclipped() failed: {e}, trying slicing syntax...")
            
            # Try MoviePy 2.x slicing syntax: clip[start:end]
            try:
                # Check if slicing is supported by trying to access __getitem__
                if hasattr(clip, '__getitem__'):
                    return clip[start:end]
            except Exception as e:
                print(f"  Warning: Slicing syntax failed: {e}, trying reload from file...")
            
            # Fallback: reload from file if we have the path
            try:
                path = file_path
                if not path:
                    # Try to get filename from clip attributes
                    path = getattr(clip, 'filename', None) or (getattr(clip, 'reader', {}).get('filename', None) if hasattr(clip, 'reader') and isinstance(getattr(clip, 'reader'), dict) else None)
                
                if path and os.path.exists(path):
                    print(f"  Reloading clip from file for subclip operation...")
                    new_clip = VideoFileClip(path)
                    # Try all methods on the reloaded clip
                    if hasattr(new_clip, 'subclipped'):
                        return new_clip.subclipped(start, end)
                    elif hasattr(new_clip, 'subclip'):
                        return new_clip.subclip(start, end)
                    elif hasattr(new_clip, '__getitem__'):
                        return new_clip[start:end]
            except Exception as e:
                print(f"  Warning: Could not reload clip for subclip: {e}")
            
            # Last resort: raise helpful error
            available_methods = [m for m in dir(clip) if not m.startswith('_') and ('clip' in m.lower() or m == '__getitem__')]
            raise AttributeError(
                f"Clip does not support subclip operation. "
                f"Clip type: {type(clip)}, "
                f"Has subclip: {hasattr(clip, 'subclip')}, "
                f"Has subclipped: {hasattr(clip, 'subclipped')}, "
                f"Has __getitem__: {hasattr(clip, '__getitem__')}, "
                f"Available methods: {available_methods[:10]}"
            )

        clips = []
        clip_paths = []  # Store paths for potential reloading
        try:
            # Load all clips first
            for path in valid_paths:
                print(f"  Loading: {os.path.basename(path)}")
                try:
                    clip = VideoFileClip(path)
                    clips.append(clip)
                    clip_paths.append(path)  # Store path for this clip
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
            
            # Validate overlap duration
            audio_overlap_seconds = max(0.0, min(audio_overlap_seconds, 2.0))  # Clamp between 0 and 2 seconds
            
            if len(clips) == 1 or audio_overlap_seconds == 0:
                # Single clip or no overlap requested
                print(f"🔗 Concatenating {len(clips)} clips...")
                final_clip = concatenate_videoclips(clips, method="compose")
            else:
                print(f"🔗 Creating overlapping audio transitions ({audio_overlap_seconds}s overlap)...")
                print("   (Next video's audio starts while previous video continues playing)")
                print("   (Video image skips overlap duration to sync with audio)")
                
                # Build timeline: videos play sequentially, audio overlaps at transitions
                video_clips = []  # Video clips positioned sequentially
                audio_clips = []  # All audio clips with overlaps
                current_time = 0.0
                
                for i, clip in enumerate(clips):
                    clip_duration = clip.duration
                    audio_track = clip.audio if clip.audio else None
                    clip_path = clip_paths[i] if i < len(clip_paths) else None
                    
                    # Video handling
                    if i == 0:
                        # First clip: video starts at 0, plays from beginning
                        video_track = without_audio(clip)
                        video_positioned = set_start(video_track, current_time)
                        video_clips.append(video_positioned)
                    else:
                        # Subsequent clips: video must skip the overlap duration to sync with audio
                        # Audio has already been playing for audio_overlap_seconds, so video should start
                        # from that point in the clip to maintain sync
                        if audio_overlap_seconds < clip_duration:
                            # Trim the original clip first (before removing audio)
                            # This ensures subclip works on the full VideoFileClip
                            # Pass the file path in case we need to reload
                            trimmed_clip = subclip(clip, audio_overlap_seconds, clip_duration, file_path=clip_path)
                            # Then remove audio from the trimmed clip
                            video_track = without_audio(trimmed_clip)
                            video_positioned = set_start(video_track, current_time)
                            video_clips.append(video_positioned)
                        else:
                            # If overlap is longer than clip duration, just use the clip as-is
                            video_track = without_audio(clip)
                            video_positioned = set_start(video_track, current_time)
                            video_clips.append(video_positioned)
                    
                    # Audio handling
                    if audio_track:
                        if i == 0:
                            # First clip: audio starts at 0
                            audio_positioned = set_start(audio_track, 0.0)
                            audio_clips.append(audio_positioned)
                        else:
                            # Subsequent clips: audio starts early (during previous clip's overlap)
                            # Audio starts at (current_time - audio_overlap_seconds)
                            audio_start_time = current_time - audio_overlap_seconds
                            audio_positioned = set_start(audio_track, audio_start_time)
                            audio_clips.append(audio_positioned)
                    
                    # Move to next position
                    # For subsequent clips, account for the trimmed video duration
                    if i == 0:
                        current_time += clip_duration
                    else:
                        # Video duration is reduced by audio_overlap_seconds (we trimmed it)
                        actual_video_duration = max(0, clip_duration - audio_overlap_seconds)
                        current_time += actual_video_duration
                
                # Calculate total duration
                total_duration = current_time
                
                # Create composite video (all videos layered with their start times)
                composite_video = CompositeVideoClip(video_clips)
                
                # Create composite audio (all audio tracks layered with overlaps)
                if audio_clips:
                    composite_audio = CompositeAudioClip(audio_clips)
                    final_clip = set_duration(set_audio(composite_video, composite_audio), total_duration)
                else:
                    final_clip = set_duration(composite_video, total_duration)
            
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
                "audio_overlap_seconds": audio_overlap_seconds if len(valid_paths) > 1 else 0,
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
