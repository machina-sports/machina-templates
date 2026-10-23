import measure
import publish

ARTICLE = {"headline": "h", "headline_fact_ids": ["f01"], "meta_description": "m",
           "lead": [{"text": "Boa.", "fact_ids": ["f02"]}, {"text": "Ruim.", "fact_ids": []}],
           "sections": [{"title": "A", "sentences": [{"text": "Ruim 2.", "fact_ids": ["f09"]}]},
                        {"title": "B", "sentences": [{"text": "Boa 2.", "fact_ids": ["f03"]}]}]}
VERIFY = {"sentences": [{"section": "título", "text": "h", "ok": False},
                        {"section": "lead", "text": "Boa.", "ok": True}, {"section": "lead", "text": "Ruim.", "ok": False},
                        {"section": "A", "text": "Ruim 2.", "ok": False}, {"section": "B", "text": "Boa 2.", "ok": True}],
          "anchored": 2, "total": 4, "lead_kind": "standing"}


def test_publish_drops_failing_sentences_and_empty_sections():
    pub = publish.publish(ARTICLE, VERIFY)
    assert [s["text"] for s in pub["lead"]] == ["Boa."]
    assert [s["title"] for s in pub["sections"]] == ["B"]
    assert pub["removed"] == ["Ruim.", "Ruim 2."] and pub["headline"] == "h"
    assert len(ARTICLE["lead"]) == 2  # the writer's article is left untouched


def test_mask_strips_match_sentences_and_team_names():
    doc = {"facts": [{"id": "f01", "kind": "match", "text": "", "value": {"home": "Vasco", "away": "Corinthians",
                                                                          "venue": "Estádio São Januário", "city": "Rio de Janeiro"}}]}
    pub = {"headline": "Vasco x Corinthians", "meta_description": "Vasco", "lead": [
        {"text": "Vasco recebe o Corinthians no sábado.", "fact_ids": ["f01", "f02"]},
        {"text": "Corinthians tem 9 jogos sem vencer; Vasco venceu 3.", "fact_ids": ["f10"]}], "sections": []}
    text = measure.mask(pub, doc)
    assert text == "TIME_B tem 9 jogos sem vencer; TIME_A venceu 3."


def test_anchoring_and_lead_share():
    res = measure.anchoring({"1": VERIFY, "2": {**VERIFY, "lead_kind": "streak"}, "3": VERIFY})
    assert res["anchored_pct"] == 50 and res["max_lead_kind_share"] == 0.67
