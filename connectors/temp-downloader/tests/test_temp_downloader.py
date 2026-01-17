"""Tests for temp-downloader connector."""
import importlib.util
import json
import os
import sys
import tempfile

import pytest

# Load module with hyphenated filename using importlib
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "temp_downloader",
    os.path.join(_parent_dir, "temp-downloader.py")
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

invoke_download = _module.invoke_download
invoke_read_json = _module.invoke_read_json
invoke_save_to_tmp = _module.invoke_save_to_tmp


class TestInvokeDownload:
    """Tests for invoke_download function."""

    def test_download_valid_url(self):
        """Test downloading from a valid URL."""
        request = {
            "params": {
                "image_url": "https://storage.googleapis.com/machina-templates-bucket-default/static/dazn-runofshow-assets/templates/serie_a.json"
            }
        }
        result = invoke_download(request)
        assert result["status"] == True
        assert "temp_path" in result["data"]
        assert os.path.exists(result["data"]["temp_path"])
        # Cleanup
        os.unlink(result["data"]["temp_path"])

    def test_download_invalid_url_format(self):
        """Test downloading from invalid URL format."""
        request = {
            "params": {
                "image_url": "not-a-valid-url"
            }
        }
        result = invoke_download(request)
        assert result["status"] == "error"
        assert "Invalid URL format" in result["message"]

    def test_download_missing_url(self):
        """Test missing URL parameter."""
        request = {"params": {}}
        result = invoke_download(request)
        assert result["status"] == "error"
        assert "image_url is required" in result["message"]

    def test_download_with_custom_filename(self):
        """Test downloading with custom filename."""
        request = {
            "params": {
                "image_url": "https://storage.googleapis.com/machina-templates-bucket-default/static/dazn-runofshow-assets/templates/serie_a.json",
                "filename": "custom_name.json"
            }
        }
        result = invoke_download(request)
        assert result["status"] == True
        assert result["data"]["filename"] == "custom_name.json"
        # Cleanup
        os.unlink(result["data"]["temp_path"])


class TestInvokeSaveToTmp:
    """Tests for invoke_save_to_tmp function."""

    def test_save_base64_image(self):
        """Test saving base64 encoded image."""
        # Simple 1x1 red PNG
        base64_image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        request = {
            "params": {
                "image_base64": base64_image
            }
        }
        result = invoke_save_to_tmp(request)
        assert result["status"] == True
        assert "image_path" in result["data"]
        assert os.path.exists(result["data"]["image_path"])
        # Cleanup
        os.unlink(result["data"]["image_path"])

    def test_save_base64_without_data_uri(self):
        """Test saving base64 without data URI prefix."""
        # Simple 1x1 red PNG (just base64, no prefix)
        base64_image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        request = {
            "params": {
                "image_base64": base64_image
            }
        }
        result = invoke_save_to_tmp(request)
        assert result["status"] == True
        # Cleanup
        os.unlink(result["data"]["image_path"])

    def test_save_missing_base64(self):
        """Test missing base64 parameter."""
        request = {"params": {}}
        result = invoke_save_to_tmp(request)
        assert result["status"] == False
        assert "Image base64 is required" in result["message"]


class TestInvokeReadJson:
    """Tests for invoke_read_json function."""

    def test_read_valid_json(self):
        """Test reading valid JSON file."""
        # Create temp JSON file
        test_data = {"id": "test", "name": "Test Template", "value": 123}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        request = {
            "params": {
                "file_path": temp_path
            }
        }
        result = invoke_read_json(request)
        assert result["status"] == True
        assert result["data"]["json_content"] == test_data
        assert result["data"]["file_path"] == temp_path
        # Cleanup
        os.unlink(temp_path)

    def test_read_nested_json(self):
        """Test reading nested JSON structure."""
        test_data = {
            "id": "serie_a",
            "market": {
                "country": "ITA",
                "language": "Italian"
            },
            "timeline": [
                {"time": -30, "type": "poll"},
                {"time": 0, "type": "kickoff"}
            ]
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        request = {"params": {"file_path": temp_path}}
        result = invoke_read_json(request)
        assert result["status"] == True
        assert result["data"]["json_content"]["market"]["country"] == "ITA"
        assert len(result["data"]["json_content"]["timeline"]) == 2
        # Cleanup
        os.unlink(temp_path)

    def test_read_invalid_json(self):
        """Test reading invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("not valid json {{{")
            temp_path = f.name

        request = {
            "params": {
                "file_path": temp_path
            }
        }
        result = invoke_read_json(request)
        assert result["status"] == "error"
        assert "Invalid JSON" in result["message"]
        # Cleanup
        os.unlink(temp_path)

    def test_read_missing_file(self):
        """Test reading non-existent file."""
        request = {
            "params": {
                "file_path": "/nonexistent/path/file.json"
            }
        }
        result = invoke_read_json(request)
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_read_missing_path_param(self):
        """Test missing file_path parameter."""
        request = {"params": {}}
        result = invoke_read_json(request)
        assert result["status"] == "error"
        assert "file_path is required" in result["message"]


class TestIntegration:
    """Integration tests for download + read workflow."""

    @pytest.mark.integration
    def test_download_and_read_json(self):
        """Test full workflow: download JSON then read it."""
        # Step 1: Download
        download_request = {
            "params": {
                "image_url": "https://storage.googleapis.com/machina-templates-bucket-default/static/dazn-runofshow-assets/templates/serie_a.json"
            }
        }
        download_result = invoke_download(download_request)
        assert download_result["status"] == True, f"Download failed: {download_result}"

        # Step 2: Read JSON
        read_request = {
            "params": {
                "file_path": download_result["data"]["temp_path"]
            }
        }
        read_result = invoke_read_json(read_request)
        assert read_result["status"] == True, f"Read failed: {read_result}"
        assert "id" in read_result["data"]["json_content"]
        assert read_result["data"]["json_content"]["id"] == "serie_a"

        # Cleanup
        os.unlink(download_result["data"]["temp_path"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
