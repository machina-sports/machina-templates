"""Step 5: every claim in the article must be anchored in the facts it cites. Two layers.

a) Deterministic (always): see check(). Numbers, dates, times and scores must appear as whole tokens in the
   cited facts' text; names, venues and cities need a cited fact that names them; nicknames, compliance terms,
   style phrases and dashes fail. Headline, meta description and section titles go through the same rules.
b) Entailment judge (optional, one call per article): every item that passed (a) is sent with the text of its
   cited facts; an item the judge does not support fails. It is the net for what tokens cannot see: who won,
   whose number it is, computed gaps, predictions, betting advice.
The rules are frozen during a run: the runner calls this module as is for every match. pt-BR only.
"""
import hashlib
import json
import os
import re
import subprocess
import unicodedata

UNITS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
         "oito": 8, "nove": 9}
TEENS = {"dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14, "quatorze": 14, "quinze": 15,
         "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19}
TENS = {"vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70,
        "oitenta": 80, "noventa": 90}
ORDINALS = {"primeir": 1, "segund": 2, "terceir": 3, "quart": 4, "quint": 5, "sext": 6, "setim": 7, "oitav": 8,
            "non": 9}
# Ordinal words are a position claim only before these nouns ("terceiro colocado", not "o primeiro a vencer").
ORDINAL_NOUN = r"(?=\s+(?:colocad|lugar|posic|colocac|turno|rodada|jogo|partida|vitoria|derrota|empate|gol))"
# "dois/duas" (and bare "um/uma") count only before a countable noun: "os dois times" is not a data claim.
COUNTABLE = r"(?:(?:ultim|primeir)[oa]s\s+)?(?:gols?|pontos?|jogos?|vitorias?|empates?|derrotas?|rodadas?|partidas?|minutos?)\b"
DATE_WORDS = re.compile(r"\b(?:segunda|terca|quarta|quinta|sexta)-feira\b|\bsabado\b|\bdomingo\b|\b(?:janeiro|fevereiro|"
                        r"marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\b")
# shortcut: pt-BR style rules live here; move them to the client/contract when a second language arrives.
STYLE_BLOCKLIST = [
    r"o mercado aponta", r"a leitura do mercado", r"cenario de (grande |extremo )?equilibrio",
    r"decidid[ao] nos detalhes", r"a cautela prevalece", r"nos documentos fornecidos", r"no relatorio fornecido",
    r"\b(refletindo|evidenciando|consolidando|destacando|ressaltando)\b", r"promete", r"eletrizante",
    r"tudo pode acontecer",
    # relative dates: the page stays up after the day, and "amanhã" is computed from a date the facts do not hold
    r"\b(hoje|amanha|ontem)\b", r"\bnest[ae] (semana|rodada|segunda|terca|quarta|quinta|sexta|sabado|domingo)\b",
]
HEADLINE_BLOCK = [r"previa", r"duelo", r"confronto", r"jogo em", r"serie a em"]
DASHES = "—–―"
INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"))
MAX_IDS = 4  # stated in prompts/writer.md rule 1


def require_ptbr(client):
    lang = (client or {}).get("language", "pt-BR")
    if lang != "pt-BR":
        raise ValueError(f"fact-articles is pt-BR only in this phase (facts, verifier and prompt); client language is {lang!r}")


def fold(s):
    """Lowercase, no accents, no invisible characters: every comparison runs on this form."""
    return unicodedata.normalize("NFKD", s.translate(INVISIBLE).lower()).encode("ascii", "ignore").decode()


def unaccent(s):
    return unicodedata.normalize("NFKD", s.translate(INVISIBLE)).encode("ascii", "ignore").decode()


def has(pattern, text):
    return bool(re.search(fold(pattern), fold(text)))


def venue_names(venue):
    """The venue as the feed names it plus without "Estádio/Arena" and a trailing "(...)", since writers drop them."""
    short = re.sub(r"\s*\(.*\)$", "", re.sub(r"^(?:Est[aá]dio|Arena)\s+(?:d[oae]\s+)?", "", venue or "")).strip()
    return {n for n in (venue, short) if n and len(n) > 3}


def words_matching(pattern, text):
    """The whole folded words of `text` a nickname pattern hits ("mineir" -> "mineiros")."""
    low, words = fold(text), set()
    for m in re.finditer(fold(pattern), low):
        a, b = m.start(), m.end()
        while a > 0 and (low[a - 1].isalnum() or low[a - 1] == "-"):
            a -= 1
        while b < len(low) and (low[b].isalnum() or low[b] == "-"):
            b += 1
        words.add(low[a:b])
    return words


def tokens(text):
    """Data tokens of a text: dates, times, scores and numbers, each compared as a whole value."""
    t = fold(text)
    dates, times, scores, nums = set(), set(), set(), set()
    for d, m, y in re.findall(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{4}))?(?![\d/])", t):
        dates.add((int(d), int(m), int(y)) if y else (int(d), int(m)))
    t = re.sub(r"\d{1,2}/\d{1,2}(?:/\d{4})?", " ", t)
    for h, mi in re.findall(r"(?<!\d)(\d{1,2})h(\d{2})?(?![a-z\d])", t):
        times.add((int(h), int(mi or 0)))
    t = re.sub(r"(?<!\d)\d{1,2}h(\d{2})?(?![a-z\d])", " ", t)
    for a, b in re.findall(r"(?<!\d)(\d+)\s?x\s?(\d+)(?!\d)", t):
        scores.add(tuple(sorted((int(a), int(b)))))  # "venceu por 4x0" quotes "0x4" winner-first; who won is the judge's call
    t = re.sub(r"(?<!\d)\d+\s?x\s?\d+(?!\d)", " ", t)
    t = re.sub(r"\b[gz]-?\d+\b", " ", t)  # Z-4 and G-4 name a band of the table; they are not data
    for n in re.findall(r"\d+(?:[.,]\d+)*", t):  # no word boundary: "11v" in "11V 3E 1D" is 11
        nums.add(n if "." in n else float(n.replace(",", ".")))  # "1.2" is not pt-BR: it only matches itself
    for tens, unit in re.findall(rf"\b({'|'.join(TENS)})(?:\s+e\s+({'|'.join(UNITS)}))?\b", t):
        nums.add(float(TENS[tens] + UNITS.get(unit, 0)))
    t = re.sub(rf"\b(?:{'|'.join(TENS)})(?:\s+e\s+(?:{'|'.join(UNITS)}))?\b", " ", t)
    nums |= {float(TEENS[w]) for w in re.findall(rf"\b({'|'.join(TEENS)})\b", t)}
    nums |= {float(UNITS[w]) for w in re.findall(r"\b(tres|quatro|cinco|seis|sete|oito|nove)\b", t)}
    nums |= {float(UNITS[w]) for w in re.findall(rf"\b(um|uma|dois|duas)\s+{COUNTABLE}", t)}
    nums |= {float(100) for _ in re.findall(r"\bcem\b", t)}
    for m in re.finditer(rf"\b(decim[oa]\s+)?({'|'.join(ORDINALS)})[oa]s?\b{ORDINAL_NOUN}", t):
        dec, base = m.groups()
        if not dec and base == "primeir" and re.match(r"\s+(?:vitoria|derrota|gol|jogo|ponto)", t[m.end():]):
            continue  # "a primeira vitória desde 26/07" is not a position claim
        nums.add(float(ORDINALS[base] + (10 if dec else 0)))
    nums |= {10.0 for _ in re.findall(rf"\bdecim[oa]s?\b(?!\s+(?:{'|'.join(ORDINALS)}))" + ORDINAL_NOUN, t)}
    return {"data": dates, "hora": times, "placar": scores, "número": nums}


def check(role, text, ids, facts, ctx):
    """Problems of one item. role: headline | meta | section_title | sentence."""
    problems = []
    known = [facts[i] for i in ids if i in facts]
    if role in ("headline", "sentence"):
        if not ids:
            problems.append("sem fact_id")
        if len(ids) > MAX_IDS:
            problems.append(f"mais de {MAX_IDS} fact_ids: {len(ids)}")
    if len(known) < len(ids):
        problems.append(f"fact_id inexistente: {[i for i in ids if i not in facts]}")
    source = " ".join(f["text"] for f in known) + " " + ctx["match_teams"]
    have, need = tokens(source), tokens(text)
    for kind, values in need.items():
        missing = values - have[kind]
        if kind == "data":  # "24/10" is anchored by "24/10/2026"
            missing = {d for d in missing if d not in {x[:2] for x in have["data"]}}
        if missing:
            problems.append(f"{kind} fora dos fatos citados: {sorted(missing, key=str)}")
    for w in DATE_WORDS.findall(fold(text)):
        if w not in fold(source):
            problems.append(f"data fora dos fatos citados: {w}")
    ftext, ctext, csource = fold(text), unaccent(text), unaccent(source)
    for n in ctx["names"]:
        cn = unaccent(n)  # case kept: the team "Vitória" is a name, "sem vitória" is not
        if re.search(rf"(?<![\w-]){re.escape(cn)}(?![\w-])", ctext) and cn not in csource:
            problems.append(f"nome fora dos fatos citados: {n}")
    if role in ("headline", "sentence"):
        named = [s for s, n in ctx["sides"].items() if re.search(rf"(?<![\w-]){re.escape(unaccent(n))}(?![\w-])", ctext)]
        if len(named) == 1 and not any(f["subject"] in (named[0], "both") or fold(ctx["sides"][named[0]]) in fold(f["text"])
                                       for f in known):
            problems.append(f"time sem fato citado: {ctx['sides'][named[0]]}")
    if role in ("headline", "meta"):
        h, a = (re.escape(unaccent(ctx["sides"][k])) for k in ("home", "away"))
        if re.search(rf"(?<![\w-]){a}\s+x\s+{h}(?![\w-])", ctext):
            problems.append(f"mandante e visitante trocados: o fato diz {ctx['sides']['home']} x {ctx['sides']['away']}")
    if role == "headline":
        problems += [f"título genérico: {p}" for p in HEADLINE_BLOCK if has(p, text)]
    allowed_words = set(re.findall(r"[\w-]+", fold(source + " " + ctx["venue_city"] + " " + " ".join(ctx["names"]))))
    problems += [f"apelido: {w}" for p in ctx["nicknames"] for w in words_matching(p, text) if w not in allowed_words]
    problems += [f"compliance: {p}" for p in ctx["forbidden"] if has(p, text)]
    problems += [f"lista bloqueada: {p}" for p in STYLE_BLOCKLIST if has(p, text)]
    if any(c in text for c in DASHES):
        problems.append("travessão")
    return problems


def items_of(article):
    """(role, section, text, fact_ids) for everything the reader sees. The meta description summarises the page,
    so it cites every fact the article cites; a section title cites what its sentences cite."""
    head_ids = list(article.get("headline_fact_ids", []))
    all_ids = head_ids + [i for s in article.get("lead", []) for i in s.get("fact_ids", [])] + [
        i for sec in article.get("sections", []) for s in sec.get("sentences", []) for i in s.get("fact_ids", [])]
    out = [("headline", "título", article.get("headline", ""), head_ids)]
    if article.get("meta_description"):
        out.append(("meta", "meta", article["meta_description"], list(dict.fromkeys(all_ids))))
    for sec in article.get("sections", []):
        sec_ids = list(dict.fromkeys(i for s in sec.get("sentences", []) for i in s.get("fact_ids", [])))
        out.append(("section_title", sec["title"], sec["title"], sec_ids))
    out += [("sentence", "lead", s["text"], s.get("fact_ids", [])) for s in article.get("lead", [])]
    out += [("sentence", sec["title"], s["text"], s.get("fact_ids", []))
            for sec in article.get("sections", []) for s in sec.get("sentences", [])]
    return out


def verify(facts_doc, article, client, known_names=(), judge=None):
    """known_names: every team (official and short name), venue and city the dataset knows.
    judge: optional callable(items) -> [{"i", "supported", "reason"}] (layer b)."""
    require_ptbr(client)
    facts = {f["id"]: f for f in facts_doc["facts"]}
    m = next(f for f in facts_doc["facts"] if f["kind"] == "match")["value"]
    ctx = {
        "match_teams": f"{m['home']} {m['away']}",
        "sides": {"home": m["home"], "away": m["away"]},
        "venue_city": f"{m['venue']} {m['city']}",  # "Mineirão" and "Belo Horizonte" are not nicknames
        "names": set(known_names) | {m["home"], m["away"], m["city"]} - {""} | venue_names(m["venue"]),
        "nicknames": client.get("nicknames", []),
        "forbidden": (client.get("compliance") or {}).get("forbidden", []),
    }
    rows = []
    for role, section, text, ids in items_of(article):
        problems = check(role, text, ids, facts, ctx)
        rows.append({"role": role, "section": section, "text": text, "fact_ids": ids, "ok": not problems,
                     "problems": problems})
    if judge:
        todo = [i for i, r in enumerate(rows) if r["ok"]]
        verdicts = {int(v["i"]): v for v in judge([{"i": i, "role": rows[i]["role"], "text": rows[i]["text"],
                                                    "facts": [facts[x]["text"] for x in rows[i]["fact_ids"] if x in facts]}
                                                   for i in todo])}
        for i in todo:
            v = verdicts.get(i) or {"supported": False, "reason": "sem resposta do juiz"}
            if v.get("supported") is not True:
                rows[i]["problems"].append(f"juiz: {v.get('reason') or 'não suportado'}")
                rows[i]["ok"] = False
    body = [r for r in rows if r["role"] == "sentence"]
    ok = sum(r["ok"] for r in body)
    lead = article.get("lead") or [{}]
    first = (lead[0].get("fact_ids") or [None])[0]
    return {"sentences": rows, "anchored": ok, "total": len(body),
            "anchored_pct": round(100 * ok / len(body)) if body else 0,
            "lead_kind": facts[first]["kind"] if first in facts else None,
            "headline_ok": rows[0]["ok"],
            "meta_ok": all(r["ok"] for r in rows if r["role"] == "meta"),
            "titles_ok": all(r["ok"] for r in rows if r["role"] == "section_title"),
            "judged": bool(judge)}


JUDGE_PROMPT = """Você confere prévias de futebol em português. Para cada item recebe o texto e os fatos que ele cita.
Diga se TUDO o que o item afirma está nos fatos citados. Paráfrase e os nomes dos dois times são permitidos.
Não suportado: placar invertido; vitória e derrota trocadas; número ou resultado atribuído ao time errado;
número calculado que não está escrito nos fatos (diferença, soma, média, porcentagem); previsão (placar provável,
quem vai vencer); conselho de aposta ou de risco ("vale a pena arriscar"); status da partida contrário aos fatos
(adiada, confirmada); adjetivo que afirma algo que os fatos não dizem (líder, invicto, em crise);
time chamado por outro nome que não o dos fatos (apelido, gentílico ou nome de cor); mandante e visitante
trocados (quem joga em casa é o primeiro time do fato da partida).
Item sem afirmação factual (título de seção como "Momento") é suportado.
Responda só JSON: {"items": [{"i": 0, "supported": true, "reason": "curta"}]}"""


class JudgeError(RuntimeError):
    """No verdict: the article cannot be verified, so it gets no page (fail closed)."""


def last_json(raw, key):
    """The LAST JSON object in `raw` that has `key`: the judge sometimes answers, writes "Correção:", answers again."""
    dec, found, i = json.JSONDecoder(), None, 0
    while (i := raw.find("{", i)) >= 0:
        try:
            obj, end = dec.raw_decode(raw, i)
        except ValueError:
            i += 1
            continue
        if isinstance(obj, dict) and key in obj:
            found = obj
        i = end
    return found


def rules_hash(client):
    """Ties a run to one rule set: this module's source (regex layer) + the judge prompt + the judge model."""
    with open(__file__, "rb") as fh:
        src = fh.read()
    return hashlib.sha256(src + JUDGE_PROMPT.encode() + client.get("verifier_model", "sonnet").encode()).hexdigest()[:16]


def claude_judge(client, on_retry=None):
    """Layer b via claude CLI, isolated with the writer's flags; model = client.verifier_model (default sonnet)."""
    model = client.get("verifier_model", "sonnet")
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_PLUGIN_DIRS"}

    def ask(items):
        cmd = ["claude", "-p", "--model", model, "--setting-sources", "", "--strict-mcp-config", "--tools", "",
               "--system-prompt", JUDGE_PROMPT, json.dumps({"items": items}, ensure_ascii=False)]
        out = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600, stdin=subprocess.DEVNULL)
        found = last_json(out.stdout or "", "items") if out.returncode == 0 else None
        return found, f"exit {out.returncode}: {(out.stdout or out.stderr or '').strip()[:300]}"

    def judge(items):
        if not items:
            return []
        for attempt in range(2):  # one retry when the reply holds no parseable verdict
            if attempt and on_retry:
                on_retry()
            found, raw = ask(items)
            if found is not None:
                return found["items"]
        raise JudgeError(f"judge gave no parseable verdict twice: {raw!r}")
    return judge


def invoke_verify(request_data):
    p = request_data.get("params") or {}
    try:
        res = verify(p["facts_doc"], p["article"], p.get("client") or {}, p.get("known_names") or [])
    except (KeyError, StopIteration, ValueError) as e:
        return {"status": False, "message": f"verify: bad input ({e!r})"}
    return {"status": True, "data": res}
