"""Render a verified fact-anchored article to one standalone HTML5 page with JSON-LD.

Inputs: the published article (writer output + "removed"), the facts doc, the client config.
Everything is server-side HTML: no script runs to show the text.
Official rules each choice rests on are cited inline (URL, rule, page date, read 2026-10-22).
"""
import html
import json
from datetime import datetime, timezone

# Chrome around the writer's text. shortcut: pt and en only, add a key when a client needs another.
LABELS = {
    "pt": {"by": "Por", "updated": "Atualizado em", "method": "Como este texto foi feito",
           "ai": "Texto gerado por IA a partir de dados esportivos. Cada frase cita o dado de que veio; "
                 "as frases que não puderam ser conferidas foram retiradas.",
           "source": "Fonte dos dados", "collected": "Dados coletados em", "vs": " x ",
           "date_fmt": "%d/%m/%Y", "time_fmt": "%d/%m/%Y, %Hh%M",
           "EventPostponed": "Partida adiada. A nova data ainda não foi definida.",
           "EventRescheduled": "Partida remarcada para a data informada acima.",
           "EventCancelled": "Partida cancelada."},
    "en": {"by": "By", "updated": "Updated", "method": "How this article was made",
           "ai": "Written by AI from sports data. Every sentence cites the data it came from; "
                 "sentences that could not be checked were removed.",
           "source": "Data source", "collected": "Data collected on", "vs": " vs. ",
           "date_fmt": "%Y-%m-%d", "time_fmt": "%Y-%m-%d %H:%M",
           "EventPostponed": "Match postponed. The new date has not been set.",
           "EventRescheduled": "Match rescheduled to the date shown above.",
           "EventCancelled": "Match cancelled."},
}

CSS = ("body{margin:0;background:#fff;color:#1a1a1a;font:18px/1.6 Georgia,'Times New Roman',serif}"
       "main{max-width:680px;margin:0 auto;padding:24px 20px 64px}"
       "h1{font-size:2rem;line-height:1.2;margin:.4em 0}h2{font-size:1.3rem;margin:1.6em 0 .4em}"
       ".site,.byline,.event,.method{font-family:system-ui,sans-serif;font-size:.9rem;color:#555}"
       ".status{font-family:system-ui,sans-serif;font-weight:700;color:#a00}"
       ".method{border-top:1px solid #ddd;margin-top:2.5em;padding-top:.5em}.method h2{font-size:1rem}")


def _status(raw):
    """Feed status -> schema.org EventStatusType, or None when unknown.

    https://developers.google.com/search/docs/appearance/structured-data/event (updated 2026-09-08):
    "If you don't use this field, Google understands the eventStatus to be EventScheduled", so an
    unknown status is left out instead of guessed. Postponed: "Keep the original date in the
    startDate". Cancelled: "Don't remove or change other properties". Both hold because startDate
    and location below never depend on the status.
    """
    s = (raw or "").lower()
    if "postpon" in s:
        return "EventPostponed"
    if "resched" in s:
        return "EventRescheduled"
    if "cancel" in s:
        return "EventCancelled"
    if s in ("scheduled", "not_started", "status_scheduled"):
        return "EventScheduled"
    return None


def _date(value, fmt):
    try:
        return datetime.fromisoformat(value).strftime(fmt)
    except (TypeError, ValueError):
        return str(value)


def _drop_none(d):
    return {k: v for k, v in d.items() if v not in (None, "")}


def render_article(article_pub, facts_doc, client, now=None):
    lang = client.get("language") or "pt-BR"
    L = LABELS.get(lang[:2].lower(), LABELS["en"])
    esc = html.escape

    facts = {f["id"]: f for f in facts_doc["facts"]}
    match_id = facts_doc.get("plan", {}).get("match_fact") or next(
        f["id"] for f in facts_doc["facts"] if f["kind"] == "match")
    match = facts[match_id]
    m = match["value"]

    # Removed sentences never reach the page, whether or not the publisher already stripped them.
    removed = set(article_pub.get("removed") or [])
    lead = [s for s in article_pub.get("lead", []) if s["text"] not in removed]
    sections = [(sec["title"], kept) for sec in article_pub.get("sections", [])
                if (kept := [s for s in sec["sentences"] if s["text"] not in removed])]

    # dateModified = render time, in the match's offset so the visible time reads local.
    tz = datetime.fromisoformat(m["start_iso"]).tzinfo if m.get("start_iso") else timezone.utc
    now = (now or datetime.now(tz)).replace(microsecond=0)
    modified = now.isoformat()

    cited = {match_id} | {i for s in lead for i in s["fact_ids"]} | {
        i for _, sents in sections for s in sents for i in s["fact_ids"]}
    as_of = ", ".join(sorted({_date(facts[i]["as_of"], L["date_fmt"]) for i in cited
                              if i in facts and facts[i].get("as_of")}))

    status = _status(m.get("status"))
    author = client.get("author") or {}
    event = _drop_none({
        "@type": "SportsEvent",
        "name": f"{m['home']}{L['vs']}{m['away']}",
        "startDate": m.get("start_iso"),
        "eventStatus": f"https://schema.org/{status}" if status else None,
        # Event doc wants a street address in location.address; the facts carry venue and city only.
        # We do not invent a street: the page stays a valid SportsEvent description, likely not an
        # Event rich result. https://developers.google.com/search/docs/appearance/structured-data/event
        "location": _drop_none({"@type": "Place", "name": m.get("venue"),
                                "address": _drop_none({"@type": "PostalAddress",
                                                       "addressLocality": m.get("city")})}),
        "homeTeam": {"@type": "SportsTeam", "name": m["home"]},
        "awayTeam": {"@type": "SportsTeam", "name": m["away"]},
        # Not in the fixed match contract yet; never hardcoded, the renderer serves every sport.
        "sport": m.get("sport") or client.get("sport"),
    })
    # NewsArticle with the match as `about`, not a top-level event: the page is an article about a
    # match. https://developers.google.com/search/docs/appearance/structured-data/sd-policies
    # (updated 2026-07-10): "Your structured data must be a true representation of the page content."
    #
    # datePublished is left out on purpose. Article doc (updated 2026-09-08): "There are no required
    # properties" and datePublished is "The date and time the article was first published".
    # https://developers.google.com/search/docs/appearance/publication-dates (updated 2025-12-10):
    # "Don't specify future dates" and "The dates must describe the publication or update date of the
    # page". This file is not published; render time is not first publication. The publish step owns
    # datePublished and must add it, visible and in markup, when the page goes live.
    article_ld = _drop_none({
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": article_pub["headline"],
        "description": article_pub.get("meta_description"),
        "inLanguage": lang,
        "dateModified": modified,
        # Article doc: Person for people, Organization for organisations; author.name only the name.
        "author": {"@type": author.get("type") or "Organization", "name": author.get("name", "")},
        "about": event,
    })
    # "<" only appears inside JSON strings, so < keeps the JSON valid and no "</script>" survives.
    ld = json.dumps(article_ld, ensure_ascii=False, indent=1).replace("<", "\\u003c")

    def para(sents, cls=""):
        attr = f' class="{cls}"' if cls else ""
        return f"<p{attr}>{esc(' '.join(s['text'] for s in sents))}</p>"

    body = [f'<p class="site">{esc(client.get("site_name", ""))}</p>',
            f"<h1>{esc(article_pub['headline'])}</h1>",
            # Visible author and date matching the markup. Helpful content page (updated 2026-10-05):
            # "Is it self-evident to your visitors who authored your content?" Publication-dates page:
            # "Ensure that the date ... match between the equivalent user-visible and structured values."
            f'<p class="byline">{esc(L["by"])} {esc(author.get("name", ""))} · {esc(L["updated"])} '
            f'<time datetime="{esc(modified)}">{esc(now.strftime(L["time_fmt"]))}</time></p>',
            # The match fact's own text makes every SportsEvent property visible on the page:
            # sd-policies "Don't mark up content that is not visible to readers of the page."
            f'<p class="event">{esc(match["text"])}</p>']
    if status in ("EventPostponed", "EventRescheduled", "EventCancelled"):
        body.append(f'<p class="status" role="status">{esc(L[status])}</p>')
    if lead:
        body.append(para(lead, "lead"))
    for title, sents in sections:
        body.append(f"<section><h2>{esc(title)}</h2>{para(sents)}</section>")
    # https://developers.google.com/search/docs/fundamentals/using-gen-ai-content (updated 2026-10-01):
    # "If you're automatically generating content, consider adding information on how your content
    # was created". Helpful content: "Is the use of automation, including AI-generation, self-evident
    # to visitors through disclosures". The client text replaces the default and must say AI wrote it.
    source = esc(client.get("data_source_label") or match.get("source", ""))
    body.append(f'<aside class="method"><h2>{esc(L["method"])}</h2>'
                f'<p>{esc(client.get("disclosure") or L["ai"])}</p>'
                f'<p>{esc(L["source"])}: {source}. {esc(L["collected"])} {esc(as_of)}.</p></aside>')

    return ("<!DOCTYPE html>\n"
            f'<html lang="{esc(lang)}">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{esc(article_pub['headline'])}</title>\n"
            f'<meta name="description" content="{esc(article_pub.get("meta_description", ""))}">\n'
            f"<style>{CSS}</style>\n"
            f'<script type="application/ld+json">\n{ld}\n</script>\n</head>\n'
            "<body>\n<main><article>\n" + "\n".join(body) + "\n</article></main>\n</body>\n</html>\n")


def invoke_render(request_data):
    """Pyscript entry. Params: article_pub, facts_doc, client. Workflow reads `$.get('html')`."""
    params = request_data.get("params", {})
    try:
        page = render_article(params["article_pub"], params["facts_doc"], params["client"])
    except (KeyError, TypeError, ValueError, StopIteration) as e:
        return {"status": False, "message": f"render failed: {type(e).__name__}: {e}"}
    return {"status": True, "message": "Article rendered", "data": {"html": page}}
