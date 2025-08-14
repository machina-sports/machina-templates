import re
from typing import Any, Dict, List, Tuple


def _collect_sections(article: Dict[str, Any]) -> List[Tuple[str, str]]:
    title_pattern = re.compile(r"^section_(\d+)_title$")
    content_pattern = re.compile(r"^section_(\d+)_content$")

    titles: Dict[str, str] = {}
    contents: Dict[str, str] = {}

    for key, value in article.items():
        if not isinstance(value, str):
            continue
        m = title_pattern.match(key)
        if m:
            titles[m.group(1)] = value
        m2 = content_pattern.match(key)
        if m2:
            contents[m2.group(1)] = value

    indices = sorted(set(titles.keys()) | set(contents.keys()), key=lambda x: int(x))
    sections: List[Tuple[str, str]] = []
    for idx in indices:
        t = titles.get(idx, "").strip()
        c = contents.get(idx, "").strip()
        if t or c:
            sections.append((t, c))
    return sections


def _build_content_html(article: Dict[str, Any]) -> str:
    subtitle = article.get("subtitle") or article.get("section_1_title")
    sections = _collect_sections(article)

    parts: List[str] = []
    if subtitle:
        parts.append(f"<p><em>{subtitle}</em></p>")
    for (sec_title, sec_content) in sections:
        if sec_title:
            parts.append(f"<h2>{sec_title}</h2>")
        if sec_content:
            parts.append(f"<p>{sec_content}</p>")
    return "\n".join(parts)


def article_model_to_wp_params(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a generic article model (like articles.model.json) into inputs for the WordPress connector.

    Inputs:
      params.article: object containing keys such as title, subtitle, slug, section_*_title/content
      params.images: optional list of image dicts [{url|file_path, alt_text?, caption?, description?, filename?}]
    Outputs:
      title, content_html, excerpt, slug, images
    """
    params = request_data.get("params", {})
    article = params.get("article") or {}
    images = params.get("images") or []

    title = article.get("title") or "Untitled"

    # Excerpt preference: subtitle, then first section content (truncated)
    excerpt_source = (
        article.get("subtitle")
        or article.get("section_1_content")
        or ""
    )
    excerpt = (excerpt_source or "").strip()
    if len(excerpt) > 280:
        excerpt = excerpt[:277] + "..."

    content_html = _build_content_html(article)

    slug = article.get("slug")

    return {
        "status": True,
        "data": {
            "title": title,
            "content_html": content_html,
            "excerpt": excerpt,
            "slug": slug,
            "images": images,
        },
        "message": "Article transformed to WordPress parameters.",
    }


