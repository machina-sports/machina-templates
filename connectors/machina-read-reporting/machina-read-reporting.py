"""Bounded public ESPN reporting collection for Machina Read.

The connector accepts only a fixed sport identifier. It has no credential,
endpoint, redirect, proxy, or arbitrary URL surface.
"""
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import json
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


API_ORIGIN = "https://now.core.api.espn.com"
SPORT_PATHS = {
    "football": ("soccer/eng.1", "/soccer/"),
    "americanfootball": ("football/nfl", "/nfl/"),
    "baseball": ("baseball/mlb", "/mlb/"),
    "basketball": ("basketball/nba", "/nba/"),
    "hockey": ("hockey/nhl", "/nhl/"),
    "tennis": ("tennis/atp", "/tennis/"),
    "motorsport": ("racing/f1", "/f1/"),
    "golf": ("golf/pga", "/golf/"),
    "cricket": ("cricket/8048", "/cricket/"),
}
ALLOWED_TYPES = {"Story", "HeadlineNews"}
MAX_ARTICLES = 3
MAX_HEADLINES_SCANNED = 10
MAX_RESPONSE_BYTES = 262144
MAX_TEXT_CHARS = 6000
MIN_TEXT_CHARS = 200
TIMEOUT_SECONDS = 6
TRUNCATION_NOTICE = " [Reporting excerpt truncated.]"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _ArticleParser(HTMLParser):
    BLOCKS = {"address", "article", "aside", "blockquote", "br", "div", "figcaption", "figure",
              "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main",
              "nav", "ol", "p", "section", "table", "td", "th", "tr", "ul"}
    SKIP = {"script", "style", "embed"}
    RAW_LIMIT = MAX_TEXT_CHARS * 4

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.length = 0
        self.skip_depth = 0

    def _append(self, value):
        if self.length >= self.RAW_LIMIT:
            return
        value = value[:self.RAW_LIMIT - self.length]
        self.parts.append(value)
        self.length += len(value)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP:
            self.skip_depth += 1
        elif not self.skip_depth and tag in self.BLOCKS:
            self._append(" ")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif not self.skip_depth and tag in self.BLOCKS:
            self._append(" ")

    def handle_data(self, data):
        if not self.skip_depth:
            self._append(data)

    def text(self):
        value = re.sub(r"\s+", " ", "".join(self.parts)).strip()
        value = re.sub(r"[\x00-\x1f\x7f]", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        truncated = len(value) > MAX_TEXT_CHARS
        if truncated:
            value = value[:MAX_TEXT_CHARS - len(TRUNCATION_NOTICE)].rstrip() + TRUNCATION_NOTICE
        return value, truncated


_OPENER = build_opener(ProxyHandler({}), _NoRedirect())


def _now():
    return datetime.now(timezone.utc)


def _failure(kind):
    return {"status": False, "message": kind}


def _instant(value):
    if not isinstance(value, str):
        raise ValueError("invalid_date")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("invalid_date")
    return parsed.astimezone(timezone.utc)


def _plain(value, limit, *, allow_empty=False):
    if not isinstance(value, str):
        raise ValueError("invalid_text")
    value = re.sub(r"\s+", " ", value).strip()
    if (not value and not allow_empty) or len(value) > limit or re.search(r"[<>\x00-\x1f\x7f]", value):
        raise ValueError("invalid_text")
    return value


def _article_url(value, article_id, web_path):
    if not isinstance(value, str) or len(value) > 1500:
        raise ValueError("invalid_url")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("invalid_url") from error
    prefix = web_path + "story/_/id/" + article_id
    if not (parsed.scheme == "https" and parsed.hostname == "www.espn.com" and
            parsed.username is None and parsed.password is None and port is None and
            not parsed.query and not parsed.fragment and
            (parsed.path == prefix or parsed.path.startswith(prefix + "/"))):
        raise ValueError("invalid_url")
    return value


def _normalize(record, sport, web_path, current):
    if not isinstance(record, dict) or record.get("premium") is not False:
        raise ValueError("invalid_article")
    if record.get("type") not in ALLOWED_TYPES:
        raise ValueError("invalid_article")
    article_id = str(record.get("id"))
    if not article_id.isdigit() or len(article_id) > 24:
        raise ValueError("invalid_article")
    published = _instant(record.get("published"))
    modified = _instant(record.get("lastModified"))
    if not current - timedelta(hours=48) <= published <= current or not published <= modified <= current:
        raise ValueError("invalid_date")
    links = record.get("links")
    if not isinstance(links, dict) or not isinstance(links.get("web"), dict):
        raise ValueError("invalid_article")
    url = _article_url(links["web"].get("href"), article_id, web_path)
    parser = _ArticleParser()
    story = record.get("story")
    if not isinstance(story, str) or len(story.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("invalid_article")
    parser.feed(story)
    parser.close()
    text, truncated = parser.text()
    if len(text) < MIN_TEXT_CHARS:
        raise ValueError("no_substantive_body")
    return {
        "id": article_id,
        "sport": sport,
        "type": record["type"],
        "headline": _plain(record.get("headline"), 300),
        "description": _plain(record.get("description") or "", 1000, allow_empty=True),
        "published": published.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "lastModified": modified.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "text": text,
        "textTruncated": truncated,
        "url": url,
    }


def invoke_reporting(request):
    params = request.get("params") if isinstance(request, dict) else None
    if not isinstance(params, dict):
        return _failure("invalid_request")
    if any(key in params for key in ("endpoint", "url", "proxy", "redirect")):
        return _failure("invalid_request")
    sport = params.get("sport")
    if not isinstance(sport, str) or sport not in SPORT_PATHS:
        return _failure("unsupported_sport")
    api_path, web_path = SPORT_PATHS[sport]
    url = API_ORIGIN + "/v1/sports/" + api_path + "/news?limit=3"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "machina-read-reporting/1.0"})
    try:
        with _OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:
            if response.geturl() != url:
                return _failure("redirect_forbidden")
            if response.status != 200:
                return _failure("upstream_status")
            content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                return _failure("invalid_response")
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > MAX_RESPONSE_BYTES:
                return _failure("response_too_large")
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        return _failure("redirect_forbidden" if 300 <= error.code < 400 else "upstream_status")
    except (TimeoutError, socket.timeout):
        return _failure("upstream_timeout")
    except URLError as error:
        return _failure("upstream_timeout" if isinstance(error.reason, (TimeoutError, socket.timeout))
                        else "upstream_unavailable")
    except (OSError, ValueError, TypeError):
        return _failure("upstream_unavailable")
    if len(body) > MAX_RESPONSE_BYTES:
        return _failure("response_too_large")
    try:
        payload = json.loads(body)
        headlines = payload["headlines"]
        if not isinstance(payload, dict) or not isinstance(headlines, list):
            raise ValueError("invalid_response")
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return _failure("invalid_response")

    current = _now()
    articles = []
    for record in headlines[:MAX_HEADLINES_SCANNED]:
        try:
            articles.append(_normalize(record, sport, web_path, current))
        except (ValueError, TypeError, KeyError):
            continue
        if len(articles) == MAX_ARTICLES:
            break
    return {"status": True, "data": {"sport": sport, "articles": articles}}
