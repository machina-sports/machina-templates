"""Offline tests for scripts/render.py. Fixtures are inline (prototype event 401841281, new shape)."""
import copy
import importlib.util
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("fact_articles_render", ROOT / "scripts" / "render.py")
render = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render)

NOW = datetime(2026, 10, 22, 15, 4, 0, tzinfo=timezone(timedelta(hours=-3)))
SRC = "sports-skills football (ESPN open data)"


def _fact(fid, kind, subject, value, text):
    return {"id": fid, "kind": kind, "subject": subject, "value": value, "text": text, "score": 0.0,
            "norm": 0.0, "source": SRC, "as_of": "2026-10-22", "tier": "data"}


FACTS_DOC = {
    "event_id": "401841281",
    "facts": [
        _fact("f01", "match", "both",
              {"home": "Vasco", "away": "Corinthians", "date": "24/10/2026", "time_local": "18h30",
               "start_iso": "2026-10-24T18:30:00-03:00", "venue": "Estádio São Januário",
               "city": "Rio de Janeiro", "competition": "Brasileirão Série A 2026", "status": "not_started",
               "sport": "Futebol"},
              "Vasco x Corinthians, 24/10/2026 às 18h30 (Brasília), Estádio São Januário, Rio de Janeiro, "
              "Brasileirão Série A 2026."),
        _fact("f02", "standing", "home", {"position": 15, "points": 35},
              "Vasco: 15º lugar, 35 pontos em 30 jogos (9V 8E 13D), 36 gols marcados e 43 sofridos."),
        _fact("f07", "standing", "away", {"position": 16, "points": 33},
              "Corinthians: 16º lugar, 33 pontos em 31 jogos (8V 9E 14D), 32 gols marcados e 39 sofridos."),
        _fact("f08", "relegation_gap", "away", {"points_over_17th": 1},
              "Corinthians tem 1 ponto a mais que o 17º colocado (Internacional, 32 pontos)."),
        _fact("f13", "h2h_season", "both", {}, "Primeiro turno, 26/04, em casa do Corinthians: Corinthians 1x0 Vasco."),
    ],
    "plan": {"lead_fact": "f08", "match_fact": "f01", "sections": [
        {"title": "Tabela", "fact_ids": ["f02", "f07"], "max_norm": 0.25},
        {"title": "Primeiro turno", "fact_ids": ["f13"], "max_norm": 0.75}]},
}

REMOVED = "O Vasco é o favorito para vencer em casa."
ARTICLE = {
    "headline": "Vasco x Corinthians: Corinthians está 1 ponto acima da zona",
    "headline_fact_ids": ["f01", "f08"],
    "meta_description": "Vasco e Corinthians jogam em 24/10/2026, às 18h30, em São Januário.",
    "lead": [{"text": "O Corinthians tem 1 ponto a mais que o Internacional, 17º colocado, e visita o Vasco em 24/10/2026.",
              "fact_ids": ["f08", "f01"]},
             {"text": "A partida é às 18h30 (Brasília), no Estádio São Januário, no Rio de Janeiro.",
              "fact_ids": ["f01"]}],
    "sections": [
        {"title": "Tabela", "sentences": [
            {"text": "O Vasco está em 15º lugar, com 35 pontos; o Corinthians, em 16º, com 33.",
             "fact_ids": ["f02", "f07"]},
            {"text": REMOVED, "fact_ids": ["f02"]}]},
        {"title": "Primeiro turno", "sentences": [
            {"text": "Corinthians e Vasco empataram três vezes seguidas.", "fact_ids": ["f13"]}]},
    ],
    "removed": [REMOVED, "Corinthians e Vasco empataram três vezes seguidas."],
}
CLIENT = {"site_name": "Prévias Ancoradas (demo)", "language": "pt-BR",
          "author": {"type": "Organization", "name": "Redação Prévias Ancoradas"},
          "data_source_label": SRC,
          "disclosure": "Texto gerado por IA a partir de dados abertos; cada frase cita o dado de que veio.",
          "compliance": {"forbidden": ["palpite"]}, "nicknames": ["tim[aã]o"]}


def _page(article=ARTICLE, facts=FACTS_DOC, client=CLIENT, status=None):
    facts = copy.deepcopy(facts)
    if status is not None:
        facts["facts"][0]["value"]["status"] = status
    return render.render_article(copy.deepcopy(article), facts, client, now=NOW)


def _ld(page):
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    assert len(blocks) == 1
    return json.loads(blocks[0])


def _body(page):
    return page.split("<body>", 1)[1]


def test_jsonld_parses_with_required_props():
    ld = _ld(_page())
    assert ld["@type"] == "NewsArticle"
    assert ld["headline"] == ARTICLE["headline"]
    assert ld["description"] == ARTICLE["meta_description"]
    assert ld["inLanguage"] == "pt-BR"
    assert ld["author"] == {"@type": "Organization", "name": "Redação Prévias Ancoradas"}
    assert ld["dateModified"] == "2026-10-22T15:04:00-03:00"
    assert "datePublished" not in ld  # not published yet: see render.py
    ev = ld["about"]
    assert ev["@type"] == "SportsEvent"
    assert ev["name"] == "Vasco x Corinthians"
    assert ev["startDate"] == "2026-10-24T18:30:00-03:00"
    assert ev["location"] == {"@type": "Place", "name": "Estádio São Januário",
                              "address": {"@type": "PostalAddress", "addressLocality": "Rio de Janeiro"}}
    assert ev["homeTeam"] == {"@type": "SportsTeam", "name": "Vasco"}
    assert ev["awayTeam"] == {"@type": "SportsTeam", "name": "Corinthians"}
    assert ev["sport"] == "Futebol"


def test_person_author_and_no_sport_when_absent():
    client = {**CLIENT, "author": {"type": "Person", "name": "Ana Lima"}}
    facts = copy.deepcopy(FACTS_DOC)
    del facts["facts"][0]["value"]["sport"]
    ld = _ld(_page(facts=facts, client=client))
    assert ld["author"] == {"@type": "Person", "name": "Ana Lima"}
    assert "sport" not in ld["about"]


@pytest.mark.parametrize("raw, expected, notice", [
    ("not_started", "https://schema.org/EventScheduled", None),
    ("scheduled", "https://schema.org/EventScheduled", None),
    ("postponed", "https://schema.org/EventPostponed", "Partida adiada"),
    ("STATUS_POSTPONED", "https://schema.org/EventPostponed", "Partida adiada"),
    ("cancelled", "https://schema.org/EventCancelled", "Partida cancelada"),
    ("STATUS_CANCELED", "https://schema.org/EventCancelled", "Partida cancelada"),
    ("rescheduled", "https://schema.org/EventRescheduled", "Partida remarcada"),
    ("closed", None, None),  # unknown to the mapping: omitted, Google then assumes EventScheduled
])
def test_event_status_mapping(raw, expected, notice):
    page = _page(status=raw)
    ev = _ld(page)["about"]
    assert ev.get("eventStatus") == expected
    # Postponed and cancelled keep the original startDate and every other property (Event docs).
    assert ev["startDate"] == "2026-10-24T18:30:00-03:00"
    assert ev["location"]["name"] == "Estádio São Januário"
    assert ev["homeTeam"]["name"] == "Vasco" and ev["awayTeam"]["name"] == "Corinthians"
    if notice:
        assert notice in _body(page)
    else:
        assert 'class="status"' not in page


def test_text_is_escaped_everywhere():
    evil = '<script>alert(1)</script> & "x"'
    article = {**ARTICLE, "headline": evil, "meta_description": evil,
               "sections": [{"title": evil, "sentences": [{"text": evil, "fact_ids": ["f02"]}]}]}
    page = _page(article=article)
    assert "<script>alert" not in page
    assert page.count("<script") == 1  # only the JSON-LD block; no external or injected script
    assert "</script>" not in page.split("</script>", 1)[1]
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;x&quot;" in page
    assert _ld(page)["headline"] == evil  # JSON-LD still decodes to the original text


def test_document_structure_byline_and_disclosure():
    page = _page()
    body = _body(page)
    assert page.startswith("<!DOCTYPE html>")
    assert '<html lang="pt-BR">' in page
    assert f"<title>{ARTICLE['headline']}</title>" in page
    assert f'<meta name="description" content="{ARTICLE["meta_description"]}">' in page
    assert body.count("<h1>") == 1
    assert "<h2>Tabela</h2>" in body
    assert "Por Redação Prévias Ancoradas" in body
    assert '<time datetime="2026-10-22T15:04:00-03:00">22/10/2026, 15h04</time>' in body
    assert CLIENT["disclosure"] in body
    assert f"Fonte dos dados: {SRC}. Dados coletados em 22/10/2026." in body
    assert FACTS_DOC["facts"][0]["text"] in body  # every SportsEvent property is visible


def test_default_disclosure_says_ai_when_client_has_none():
    client = {k: v for k, v in CLIENT.items() if k != "disclosure"}
    assert "Texto gerado por IA" in _body(_page(client=client))


def test_removed_sentences_and_emptied_sections_are_not_rendered():
    page = _page()
    assert REMOVED not in page
    assert "empataram três vezes" not in page
    assert "Primeiro turno" not in page  # its only sentence was removed: no empty H2
    assert "O Vasco está em 15º lugar" in page


def test_invoke_render_envelope():
    out = render.invoke_render({"params": {"article_pub": ARTICLE, "facts_doc": FACTS_DOC, "client": CLIENT}})
    assert out["status"] is True
    assert out["data"]["html"].startswith("<!DOCTYPE html>")
    assert render.invoke_render({"params": {}})["status"] is False
