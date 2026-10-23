"""Step 6: the version that would go live. A sentence the verifier failed leaves the text;
a section left empty disappears. Headline, meta and section titles are not touched here: when one of them
fails, the runner regenerates once and then publishes no page at all."""


def publish(article, verify_result):
    bad = list(dict.fromkeys(r["text"] for r in verify_result["sentences"]
                             if not r["ok"] and r.get("role", "sentence") == "sentence" and r["section"] != "título"))
    pub = dict(article)
    pub["lead"] = [s for s in article.get("lead", []) if s["text"] not in bad]
    sections = [dict(sec, sentences=[s for s in sec.get("sentences", []) if s["text"] not in bad])
                for sec in article.get("sections", [])]
    pub["sections"] = [sec for sec in sections if sec["sentences"]]
    pub["removed"] = bad  # in reading order
    return pub


def invoke_publish(request_data):
    p = request_data.get("params") or {}
    try:
        return {"status": True, "data": publish(p["article"], p["verify"])}
    except KeyError as e:
        return {"status": False, "message": f"publish: missing {e}"}
