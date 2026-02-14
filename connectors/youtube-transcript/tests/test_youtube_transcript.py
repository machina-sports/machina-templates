"""
Unit tests for YouTube Transcript Connector

Run with: python test_youtube_transcript.py
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Add parent directory to path to import the connector
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from youtube_transcript import (
    validate_youtube_url,
    clean_vtt_content,
    extract_transcript,
    get_available_languages
)


class TestYouTubeURLValidation(unittest.TestCase):
    """Test YouTube URL validation"""
    
    def test_valid_watch_url(self):
        """Test standard YouTube watch URL"""
        video_id = validate_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(video_id, "dQw4w9WgXcQ")
    
    def test_valid_short_url(self):
        """Test YouTube short URL"""
        video_id = validate_youtube_url("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(video_id, "dQw4w9WgXcQ")
    
    def test_valid_live_url(self):
        """Test YouTube live URL"""
        video_id = validate_youtube_url("https://www.youtube.com/live/Q2k9dHN93kA")
        self.assertEqual(video_id, "Q2k9dHN93kA")
    
    def test_without_https(self):
        """Test URL without https"""
        video_id = validate_youtube_url("www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(video_id, "dQw4w9WgXcQ")
    
    def test_invalid_url(self):
        """Test invalid URL"""
        video_id = validate_youtube_url("https://example.com/video")
        self.assertIsNone(video_id)
    
    def test_invalid_video_id(self):
        """Test URL with invalid video ID format"""
        video_id = validate_youtube_url("https://www.youtube.com/watch?v=invalid")
        self.assertIsNone(video_id)


class TestVTTCleaning(unittest.TestCase):
    """Test VTT content cleaning"""
    
    def test_clean_vtt_basic(self):
        """Test basic VTT cleaning"""
        vtt_content = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:03.000
Hello world

00:00:03.000 --> 00:00:06.000
This is a test"""
        
        cleaned = clean_vtt_content(vtt_content)
        self.assertEqual(cleaned, "Hello world This is a test")
    
    def test_remove_duplicates(self):
        """Test duplicate line removal"""
        vtt_content = """WEBVTT

00:00:00.000 --> 00:00:03.000
Hello world

00:00:03.000 --> 00:00:06.000
Hello world

00:00:06.000 --> 00:00:09.000
Different line"""
        
        cleaned = clean_vtt_content(vtt_content)
        self.assertEqual(cleaned, "Hello world Different line")
    
    def test_remove_html_tags(self):
        """Test HTML tag removal"""
        vtt_content = """WEBVTT

00:00:00.000 --> 00:00:03.000
<c>Hello</c> <c>world</c>"""
        
        cleaned = clean_vtt_content(vtt_content)
        self.assertEqual(cleaned, "Hello world")
    
    def test_normalize_whitespace(self):
        """Test whitespace normalization"""
        vtt_content = """WEBVTT

00:00:00.000 --> 00:00:03.000
Hello    world   test"""
        
        cleaned = clean_vtt_content(vtt_content)
        self.assertEqual(cleaned, "Hello world test")


class TestExtractTranscript(unittest.TestCase):
    """Test transcript extraction with mocked subprocess"""
    
    @patch('youtube_transcript.subprocess.run')
    @patch('youtube_transcript.Path')
    @patch('youtube_transcript.open', create=True)
    def test_extract_transcript_success(self, mock_open, mock_path, mock_run):
        """Test successful transcript extraction"""
        # Mock subprocess result
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr=""
        )
        
        # Mock VTT file
        mock_vtt_content = """WEBVTT

00:00:00.000 --> 00:00:03.000
Test transcript content"""
        
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = mock_vtt_content
        mock_open.return_value = mock_file
        
        # Mock Path.glob to return a VTT file
        mock_vtt_file = MagicMock()
        mock_vtt_file.name = "transcript.en.vtt"
        mock_path.return_value.glob.return_value = [mock_vtt_file]
        
        # Test extraction
        request_data = {
            "params": {
                "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "language": "en"
            }
        }
        
        result = extract_transcript(request_data)
        
        self.assertTrue(result["status"])
        self.assertIn("transcript", result["data"])
        self.assertEqual(result["data"]["video_id"], "dQw4w9WgXcQ")
    
    def test_extract_transcript_missing_url(self):
        """Test extraction without video URL"""
        request_data = {"params": {}}
        result = extract_transcript(request_data)
        
        self.assertFalse(result["status"])
        self.assertIn("required", result["message"])
    
    def test_extract_transcript_invalid_url(self):
        """Test extraction with invalid URL"""
        request_data = {
            "params": {
                "video_url": "https://example.com/video"
            }
        }
        result = extract_transcript(request_data)
        
        self.assertFalse(result["status"])
        self.assertIn("Invalid", result["message"])


class TestGetAvailableLanguages(unittest.TestCase):
    """Test language detection with mocked subprocess"""
    
    @patch('youtube_transcript.subprocess.run')
    def test_get_languages_success(self, mock_run):
        """Test successful language detection"""
        # Mock yt-dlp --list-subs output
        mock_output = """Available subtitles for dQw4w9WgXcQ:
Language formats
en       vtt, ttml, srv3, srv2, srv1, json3
es       vtt, ttml, srv3, srv2, srv1, json3

Available automatic captions for dQw4w9WgXcQ:
Language formats
pt       vtt, ttml, srv3, srv2, srv1, json3
fr       vtt, ttml, srv3, srv2, srv1, json3"""
        
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_output,
            stderr=""
        )
        
        request_data = {
            "params": {
                "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            }
        }
        
        result = get_available_languages(request_data)
        
        self.assertTrue(result["status"])
        self.assertIn("en", result["data"]["manual"])
        self.assertIn("es", result["data"]["manual"])
        self.assertIn("pt", result["data"]["auto_generated"])
        self.assertIn("fr", result["data"]["auto_generated"])
    
    def test_get_languages_missing_url(self):
        """Test language detection without URL"""
        request_data = {"params": {}}
        result = get_available_languages(request_data)
        
        self.assertFalse(result["status"])
        self.assertIn("required", result["message"])


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestYouTubeURLValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestVTTCleaning))
    suite.addTests(loader.loadTestsFromTestCase(TestExtractTranscript))
    suite.addTests(loader.loadTestsFromTestCase(TestGetAvailableLanguages))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

