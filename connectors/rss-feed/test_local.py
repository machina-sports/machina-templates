#!/usr/bin/env python3
"""
Local test script for RSS Feed connector.
Run this to test the connector functions directly without the Machina platform.

Usage:
    # Test with regular RSS feed URL
    python test_local.py [feed_url]
    
    # Test with Google News
    python test_local.py --google-news "query" [--language en-US] [--country US]

Examples:
    python test_local.py https://rss.cnn.com/rss/edition.rss
    python test_local.py --google-news "Jeremiah Smith Jr"
    python test_local.py --google-news "NBA" --language en-US --country US
"""

import sys
import os
import argparse

# Add the current directory to the path so we can import rss_feed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the functions - note: Python can't import modules with hyphens directly
# So we'll use importlib or exec, or just copy the functions here for testing
# For simplicity, let's use importlib
import importlib.util

spec = importlib.util.spec_from_file_location("rss_feed", "rss-feed.py")
rss_feed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rss_feed)


def test_fetch_feed(params):
    """Test the fetch_feed function."""
    print(f"\n{'='*60}")
    if params.get("google_news"):
        print(f"Testing fetch_feed with Google News")
        print(f"   Query: {params.get('query')}")
        print(f"   Language: {params.get('language', 'en-US')}")
        print(f"   Country: {params.get('country', 'US')}")
        if params.get('after'):
            print(f"   After: {params.get('after')}")
        if params.get('before'):
            print(f"   Before: {params.get('before')}")
        if params.get('sort_by_date'):
            print(f"   Sort by date: Enabled (newest first)")
    else:
        print(f"Testing fetch_feed with URL: {params.get('url')}")
    print(f"{'='*60}\n")
    
    result = rss_feed.fetch_feed(params)
    
    if result.get("status") == "error":
        print(f"❌ Error: {result.get('message')}")
        return False
    
    if result.get("status") is True:
        data = result.get("data", {})
        print(f"✅ Success!")
        print(f"   Title: {data.get('title', 'N/A')}")
        print(f"   Link: {data.get('link', 'N/A')}")
        print(f"   Language: {data.get('language', 'N/A')}")
        print(f"   Updated: {data.get('updated', 'N/A')}")
        print(f"   Entries: {len(data.get('entries', []))}")
        
        # Show first entry
        entries = data.get("entries", [])
        if entries:
            print(f"\n   First Entry:")
            first = entries[0]
            print(f"     Title: {first.get('title', 'N/A')}")
            print(f"     Link: {first.get('link', 'N/A')}")
            print(f"     Published: {first.get('published', 'N/A')}")
            print(f"     Author: {first.get('author', 'N/A')}")
        
        return True
    
    print(f"❌ Unexpected result: {result}")
    return False


def test_fetch_items(params, limit=5):
    """Test the fetch_items function."""
    params_with_limit = {**params, "limit": limit}
    
    print(f"\n{'='*60}")
    if params.get("google_news"):
        print(f"Testing fetch_items with Google News")
        print(f"   Query: {params.get('query')}")
        print(f"   Limit: {limit}")
        if params.get('after'):
            print(f"   After: {params.get('after')}")
        if params.get('before'):
            print(f"   Before: {params.get('before')}")
        if params.get('sort_by_date'):
            print(f"   Sort by date: Enabled (newest first)")
    else:
        print(f"Testing fetch_items with URL: {params.get('url')}, Limit: {limit}")
    print(f"{'='*60}\n")
    
    result = rss_feed.fetch_items(params_with_limit)
    
    if result.get("status") == "error":
        print(f"❌ Error: {result.get('message')}")
        return False
    
    if result.get("status") is True:
        items = result.get("data", [])
        print(f"✅ Success! Retrieved {len(items)} items")
        
        for i, item in enumerate(items[:3], 1):  # Show first 3
            print(f"\n   Item {i}:")
            print(f"     Title: {item.get('title', 'N/A')}")
            print(f"     Link: {item.get('link', 'N/A')}")
            print(f"     Published: {item.get('published', 'N/A')}")
        
        return True
    
    print(f"❌ Unexpected result: {result}")
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test RSS Feed Connector")
    parser.add_argument("positional", nargs="?", help="RSS feed URL or Google News query")
    parser.add_argument("--google-news", action="store_true", help="Use Google News RSS feed")
    parser.add_argument("--query", help="Search query for Google News (alternative to positional)")
    parser.add_argument("--language", default="en-US", help="Language code (default: en-US)")
    parser.add_argument("--country", default="US", help="Country code (default: US)")
    parser.add_argument("--after", help="Filter articles published after this date (YYYY-MM-DD)")
    parser.add_argument("--before", help="Filter articles published before this date (YYYY-MM-DD)")
    parser.add_argument("--sort-by-date", action="store_true", help="Sort entries by publication date (newest first)")
    
    args = parser.parse_args()
    
    print("RSS Feed Connector - Local Test")
    print("=" * 60)
    
    # Prepare test parameters
    if args.google_news:
        # Use --query if provided, otherwise use positional argument
        query = args.query if args.query else args.positional
        if not query:
            print("❌ Error: Query is required when using --google-news. Provide as positional arg or --query")
            sys.exit(1)
        test_params = {
            "google_news": True,
            "query": query,
            "language": args.language,
            "country": args.country,
            "after": args.after,
            "before": args.before,
            "sort_by_date": args.sort_by_date
        }
    else:
        test_url = args.positional if args.positional else "https://rss.cnn.com/rss/edition.rss"
        test_params = {
            "google_news": False,
            "url": test_url,
            "sort_by_date": args.sort_by_date
        }
    
    # Test fetch_feed
    success1 = test_fetch_feed(test_params)
    
    # Test fetch_items
    success2 = test_fetch_items(test_params, limit=5)
    
    # Summary
    print(f"\n{'='*60}")
    if success1 and success2:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
    print(f"{'='*60}\n")

