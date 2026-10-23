import pytest

import facts
import verify

NAMES = ["Vasco", "Vasco da Gama", "Corinthians", "Palmeiras", "Internacional", "Cruzeiro", "Remo",
         "Estádio São Januário", "São Januário", "Estadio Mineirão", "Mineirão"]


@pytest.fixture
def doc(dataset, contract, client):
    """Vasco x Corinthians: f01 match, f02 Vasco standing, f04 Vasco last5, f06 Vasco home record,
    f08 Corinthians relegation gap (1 point over 17th), f10 Corinthians 9 without a win."""
    return facts.build_doc(next(e for e in dataset["events"] if e["id"] == "401841281"), dataset, contract, client)


def check(doc, client, text, ids, headline="Corinthians chega com 9 jogos sem vencer", headline_ids=("f10",)):
    art = {"headline": headline, "headline_fact_ids": list(headline_ids), "meta_description": "x",
           "lead": [{"text": text, "fact_ids": list(ids)}], "sections": []}
    return verify.verify(doc, art, client, NAMES)


def body(doc, client, text, ids):
    return next(r for r in check(doc, client, text, ids)["sentences"] if r["role"] == "sentence")


def ok(doc, client, text, ids):
    return body(doc, client, text, ids)["ok"]


def problems(doc, client, text, ids):
    return " ".join(body(doc, client, text, ids)["problems"])


# The prototype's self-test cases.
def test_prototype_cases(doc, client):
    assert ok(doc, client, "Corinthians chega com 9 jogos sem vencer no Brasileirão.", ["f10"])
    assert not ok(doc, client, "Vasco venceu 6 dos últimos 7 jogos.", ["f04"])
    assert not ok(doc, client, "O mercado aponta um cenário de equilíbrio.", ["f01"])
    assert "nome fora" in problems(doc, client, "O Palmeiras observa o confronto.", ["f02"])
    assert "sem fact_id" in problems(doc, client, "Frase sem fato.", [])
    assert "apelido" in problems(doc, client, "Os cruzmaltinos somaram 35 pontos em 30 jogos.", ["f02"])
    assert "inexistente" in problems(doc, client, "Vasco tem 35 pontos.", ["f99"])


def test_headline_is_checked(doc, client):
    generic = check(doc, client, "x", ["f02"], headline="Vasco x Corinthians: prévia do jogo", headline_ids=["f01"])
    assert not generic["headline_ok"] and "título genérico" in generic["sentences"][0]["problems"][0]
    for bad in ("Duelo em São Januário", "Vasco e Corinthians: confronto direto", "Série A em foco"):
        assert not check(doc, client, "x", ["f02"], headline=bad, headline_ids=["f01"])["headline_ok"], bad
    assert not check(doc, client, "x", ["f02"], headline="Corinthians tem 12 jogos sem vencer", headline_ids=["f10"])["headline_ok"]
    assert not check(doc, client, "x", ["f02"], headline="Corinthians tem 9 jogos sem vencer", headline_ids=[])["headline_ok"]
    good = check(doc, client, "x", ["f02"], headline="Corinthians chega a São Januário com 9 jogos sem vencer",
                 headline_ids=["f10", "f01"])
    assert good["headline_ok"]


def test_title_row_is_excluded_from_counts(doc, client):
    r = check(doc, client, "Vasco tem 35 pontos.", ["f02"], headline="Vasco: prévia")
    assert r["total"] == 1 and r["anchored"] == 1 and r["anchored_pct"] == 100 and not r["headline_ok"]
    assert r["sentences"][0]["section"] == "título" and r["lead_kind"] == "standing"


def test_match_teams_nameable_anywhere(doc, client):
    assert ok(doc, client, "Vasco e Corinthians estão perto da zona de rebaixamento.", ["f08"])


def test_venue_and_dates_need_the_match_fact(doc, client):
    assert "nome fora" in problems(doc, client, "O Vasco recebe o Corinthians em São Januário.", ["f06"])
    assert ok(doc, client, "O Vasco recebe o Corinthians em São Januário.", ["f01"])
    assert "data fora" in problems(doc, client, "O jogo é no sábado.", ["f02"])
    assert "data fora" in problems(doc, client, "O jogo é em 24/10, às 18h30.", ["f02"])  # dates are date tokens now
    assert ok(doc, client, "O jogo é no sábado, 24/10, às 18h30, em São Januário.", ["f01"])


def test_z4_and_g4_are_terms_not_numbers(doc, client):
    assert ok(doc, client, "O Corinthians está 1 ponto acima do Z-4.", ["f08"])
    assert ok(doc, client, "O Vasco está longe do G-4 e do Z4.", ["f02"])


def test_two_counts_only_before_a_countable_noun(doc, client):
    assert ok(doc, client, "Os dois times chegam perto da zona de rebaixamento.", ["f08"])
    assert ok(doc, client, "As duas equipes somam derrotas recentes.", ["f09"])
    assert "número fora" in problems(doc, client, "O Vasco marcou dois gols no último jogo.", ["f02"])
    assert "número fora" in problems(doc, client, "O Corinthians perdeu os dois últimos jogos.", ["f08"])
    assert "número fora" in problems(doc, client, "O Vasco somou duas vitórias.", ["f02"])


def test_nicknames_fail_unless_in_facts_venue_or_official_names(dataset, contract, client, doc):
    assert "apelido" in problems(doc, client, "Os alvinegros chegam pressionados.", ["f08"])
    cru = facts.build_doc(next(e for e in dataset["events"] if e["id"] == "401841287"), dataset, contract, client)
    art = {"headline": "Cruzeiro recebe o Remo", "headline_fact_ids": ["f01"], "lead": [
        {"text": "O Cruzeiro recebe o Remo no Mineirão.", "fact_ids": ["f01"]},
        {"text": "Os mineiros chegam bem.", "fact_ids": ["f01"]}], "sections": []}
    rows = [r for r in verify.verify(cru, art, client, NAMES)["sentences"] if r["role"] != "meta"]
    assert rows[1]["ok"], rows[1]  # "Mineirão" is the venue, not a nickname
    assert not rows[2]["ok"] and "apelido" in rows[2]["problems"][0]


def test_compliance_and_em_dash(doc, client):
    assert "compliance" in problems(doc, client, "O Vasco é favorito em casa.", ["f06"])
    assert "compliance" in problems(doc, client, "Boa oportunidade de aposta no Vasco.", ["f06"])
    assert "compliance" in problems(doc, client, "As odds do Vasco caíram.", ["f06"])
    assert "travessão" in problems(doc, client, "Vasco em casa — 15 jogos.", ["f06"])


def test_hardened_tokens(doc, client):
    assert "hora fora" in problems(doc, client, "A partida começa às 19h30.", ["f01"])
    assert ok(doc, client, "No primeiro turno, o Corinthians venceu o Vasco por 1x0.", ["f13"])
    # scores in either order (the winner-first quote is idiomatic); who won is the judge's call (round-2 decision 3)
    assert ok(doc, client, "O Corinthians perdeu para o Flamengo por 1x2 e para o Palmeiras por 4x1.", ["f09"])
    assert ok(doc, client, "O Vasco somou 10 de 15 pontos; o Corinthians, 1.", ["f04", "f09"])
    assert "número fora" in problems(doc, client, "O Vasco tem trinta e cinco pontos a mais.", ["f03"])
    assert ok(doc, client, "O Vasco é o décimo quinto colocado, com 35 pontos.", ["f02"])
    assert "mais de 4" in problems(doc, client, "O Vasco tem 35 pontos.", ["f02", "f03", "f04", "f05", "f06"])  # cap 4 (round 2)
    assert "lista bloqueada" in problems(doc, client, "Vasco e Corinthians jogam amanhã.", ["f01"])
    assert "nome fora" not in problems(doc, client, "O Vasco busca a vitória em casa.", ["f06"])  # "vitória" is not the team


def test_section_title_and_meta_are_verified(doc, client):
    art = {"headline": "Corinthians chega com 9 jogos sem vencer", "headline_fact_ids": ["f10"],
           "meta_description": "Palpite: Vasco 3x0.", "lead": [{"text": "Vasco tem 35 pontos.", "fact_ids": ["f02"]}],
           "sections": [{"title": "Odds do Timão", "sentences": [{"text": "Vasco tem 35 pontos.", "fact_ids": ["f02"]}]}]}
    r = verify.verify(doc, art, client, NAMES)
    assert r["headline_ok"] and not r["meta_ok"] and not r["titles_ok"] and r["total"] == 2 and r["anchored"] == 2
