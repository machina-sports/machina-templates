import feedparser
import time
from datetime import datetime
from urllib.parse import quote_plus
from email.utils import parsedate_to_datetime


def _build_google_news_url(query, language="en-US", country="US", after=None, before=None):
    """
    Build a Google News RSS feed URL from a search query.
    
    Args:
        query (str): Search query string
        language (str): Language code (default: "en-US")
        country (str): Country code (default: "US")
        after (str, optional): Filter articles published after this date (YYYY-MM-DD format)
        before (str, optional): Filter articles published before this date (YYYY-MM-DD format)
    
    Returns:
        str: Google News RSS URL
    """
    # Extract language code (e.g., "en" from "en-US")
    lang_code = language.split("-")[0] if "-" in language else language
    
    # Build the ceid parameter (country:language)
    ceid = f"{country}:{lang_code}"
    
    # Build query string with optional date filters
    query_parts = [query]
    if after:
        query_parts.append(f"after:{after}")
    if before:
        query_parts.append(f"before:{before}")
    
    # Join query parts and URL encode
    full_query = " ".join(query_parts)
    encoded_query = quote_plus(full_query)
    
    # Build the Google News RSS URL
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl={language}&gl={country}&ceid={ceid}"
    
    return url


def fetch_feed(params):
    """
    Fetch and parse an RSS/Atom feed.

    Args:
        params (dict): Dictionary containing:
            - google_news (bool, optional): If True, use Google News RSS feed. Default: False
            - query (str, required if google_news=True): Search query for Google News
            - url (str, required if google_news=False): The URL of the RSS feed
            - language (str, optional): Language code for Google News (default: "en-US")
            - country (str, optional): Country code for Google News (default: "US")
            - after (str, optional): Filter articles published after this date (YYYY-MM-DD format)
            - before (str, optional): Filter articles published before this date (YYYY-MM-DD format)
            - sort_by_date (bool, optional): Sort entries by publication date (newest first). Default: False

    Returns:
        dict: Status and parsed feed data.
    """
    google_news = params.get("google_news", False)
    sort_by_date = params.get("sort_by_date", False)
    
    # Determine the URL to use
    if google_news:
        query = params.get("query")
        if not query:
            return {"status": "error", "message": "Query is required when google_news is True."}
        
        language = params.get("language", "en-US")
        country = params.get("country", "US")
        after = params.get("after")
        before = params.get("before")
        url = _build_google_news_url(query, language, country, after, before)
    else:
        url = params.get("url")
        if not url:
            return {"status": "error", "message": "URL is required when google_news is False."}

    try:
        feed = feedparser.parse(url)
        
        # Check if the feed was fetched successfully
        if hasattr(feed, 'status') and feed.status >= 400:
             return {
                "status": "error", 
                "message": f"Failed to fetch feed. HTTP Status: {feed.status}"
            }
        
        if feed.bozo:
            # We log the exception but continue if entries were parsed, 
            # as feedparser is lenient. However, if no entries and bozo is set, it's likely a fatal error.
            if not feed.entries and not feed.feed:
                 return {"status": "error", "message": f"Failed to parse feed: {feed.bozo_exception}"}

        # Process feed metadata
        feed_data = {
            "title": feed.feed.get("title", ""),
            "subtitle": feed.feed.get("subtitle", ""),
            "link": feed.feed.get("link", ""),
            "language": feed.feed.get("language", ""),
            "updated": feed.feed.get("updated", ""),
            "entries": []
        }

        # Process entries
        for entry in feed.entries:
            parsed_entry = _parse_entry(entry)
            feed_data["entries"].append(parsed_entry)
        
        # Sort by date if requested (newest first)
        if sort_by_date:
            feed_data["entries"] = _sort_entries_by_date(feed_data["entries"])

        return {"status": True, "data": feed_data}

    except Exception as e:
        return {"status": "error", "message": f"Exception when fetching feed: {e}"}


def fetch_items(params):
    """
    Fetch items from an RSS/Atom feed, optionally limited by count or date.

    Args:
        params (dict): Dictionary containing:
            - google_news (bool, optional): If True, use Google News RSS feed. Default: False
            - query (str, required if google_news=True): Search query for Google News
            - url (str, required if google_news=False): The URL of the RSS feed
            - limit (int, optional): Max number of items to return
            - language (str, optional): Language code for Google News (default: "en-US")
            - country (str, optional): Country code for Google News (default: "US")
            - after (str, optional): Filter articles published after this date (YYYY-MM-DD format)
            - before (str, optional): Filter articles published before this date (YYYY-MM-DD format)
            - sort_by_date (bool, optional): Sort entries by publication date (newest first). Default: False

    Returns:
        dict: Status and list of feed items.
    """
    limit = params.get("limit")
    
    # Pass all params to fetch_feed, which will handle URL resolution
    try:
        result = fetch_feed(params)
        if result.get("status") == "error":
            return result
        
        items = result.get("data", {}).get("entries", [])
        
        if limit:
            try:
                limit = int(limit)
                items = items[:limit]
            except (ValueError, TypeError):
                pass # Ignore invalid limit
        
        return {"status": True, "data": items}

    except Exception as e:
        return {"status": "error", "message": f"Exception when fetching items: {e}"}


def _sort_entries_by_date(entries, reverse=True):
    """
    Sort entries by publication date.
    
    Args:
        entries (list): List of entry dictionaries
        reverse (bool): If True, sort newest first (default). If False, sort oldest first.
    
    Returns:
        list: Sorted list of entries
    """
    def get_sort_key(entry):
        """Extract timestamp for sorting."""
        published_iso = entry.get("published_iso", "")
        if published_iso:
            try:
                return datetime.fromisoformat(published_iso.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
        
        # Fallback to published string
        published = entry.get("published", "")
        if published:
            try:
                # Try parsing common date formats
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(published)
                return dt
            except (ValueError, TypeError):
                pass
        
        # If no date found, put at the end (or beginning if reverse=False)
        return datetime.min if reverse else datetime.max
    
    return sorted(entries, key=get_sort_key, reverse=reverse)


def _parse_entry(entry):
    """
    Helper to parse a single feed entry into a standardized dictionary.
    """
    # Extract content - prefer full content, fallback to summary/description
    content = ""
    if hasattr(entry, 'content'):
        # Atom usually has a list of content objects
        content = entry.content[0].value if entry.content else ""
    elif hasattr(entry, 'description'):
        content = entry.description
    elif hasattr(entry, 'summary'):
        content = entry.summary
        
    published_parsed = entry.get('published_parsed') or entry.get('updated_parsed')
    published_iso = ""
    if published_parsed:
        published_iso = datetime.fromtimestamp(time.mktime(published_parsed)).isoformat()
    
    return {
        "title": entry.get("title", ""),
        "link": entry.get("link", ""),
        "id": entry.get("id", ""),
        "published": entry.get("published", entry.get("updated", "")),
        "published_iso": published_iso,
        "author": entry.get("author", ""),
        "summary": entry.get("summary", ""),
        "content": content,
        "tags": [tag.term for tag in entry.tags] if hasattr(entry, 'tags') else []
    }

