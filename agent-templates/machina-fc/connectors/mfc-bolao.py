"""
mfc-bolao connector - Bolao da Casa do Machina FC (server-side).

Porta fiel do tools/gen-bolao.py do prototipo. Fonte = SPORTSCLAW
(machina-sports/sports-skills: football=ESPN publico + betting=devig math puro).
NUNCA Sportradar / sportsbook. Roda IN-PROCESS (importlib), nao via CLI.

Comandos:
  gerar_boletim(request_data) -> {"status":True,"data":{"boletim":{...},"season_id","rodada","n_jogos"}}
      Boletim = predicoes (P casa/empate/fora + leitura + confianca) da rodada alvo.
      Contrato de 'boletim' identico ao data/bolao/rodada-atual.json do front.
  settle_rodada(request_data) -> {"status":True,"data":{"resultado":{...},"n_com_placar"}}
      Cruza placares REAIS da rodada com os palpites da casa (casa_pick derivado do P salvo).
      Contrato de 'resultado' identico ao data/bolao/rodada-resultado.json do front.

REAL (sportsclaw)     : season, fixtures (times, kickoff, match_id, placar), standings/forma, devig.
HEURISTICA (derivado) : probabilidades baseline, leitura, confianca, ids 3 letras, cores.
"""
import importlib
import math
import os
import subprocess
import sys
from datetime import datetime, timezone

# ----------------------------------------------------------------------------
# bootstrap sports-skills no pod (mesmo padrao do connector sports-skills)
# ----------------------------------------------------------------------------
_MIN_VERSION = (0, 26, 3)
_PIP_PACKAGE = "sports-skills>=0.26.3,<1.0"
_TARGET_DIR = "/tmp/sports-skills-site"


def _loaded_version_ok():
    mod = sys.modules.get("sports_skills")
    if mod is None:
        return False
    try:
        parts = str(getattr(mod, "__version__", "0")).split(".")[:3]
        return tuple(int(p) for p in parts) >= _MIN_VERSION
    except Exception:
        return False


def _activate_target():
    if _TARGET_DIR not in sys.path:
        sys.path.insert(0, _TARGET_DIR)
    importlib.invalidate_caches()
    for name in [m for m in sys.modules if m == "sports_skills" or m.startswith("sports_skills.")]:
        del sys.modules[name]


def _ensure_sports_skills():
    if _loaded_version_ok():
        return True, None
    if os.path.isdir(os.path.join(_TARGET_DIR, "sports_skills")):
        _activate_target()
        try:
            importlib.import_module("sports_skills")
        except ImportError:
            pass
        if _loaded_version_ok():
            return True, None
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--upgrade",
             "--target", _TARGET_DIR, _PIP_PACKAGE],
            capture_output=True, text=True, timeout=180,
        )
    except Exception as e:
        try:
            importlib.import_module("sports_skills")
            return True, None
        except ImportError:
            return False, "pip install raised: " + str(e)
    if proc.returncode != 0:
        try:
            importlib.import_module("sports_skills")
            return True, None
        except ImportError:
            return False, "pip install failed (rc=" + str(proc.returncode) + "): " + (proc.stderr or proc.stdout or "")[-1200:]
    _activate_target()
    try:
        importlib.import_module("sports_skills")
        return True, None
    except ImportError as e:
        return False, "sports_skills installed but not importable: " + str(e)


def _ss(module, command, **params):
    """Chama uma funcao do sports_skills in-process e devolve o dict ['data'].
    As funcoes retornam {"status","data","message"}; aqui ja desembrulhamos para ['data'].
    """
    mod = importlib.import_module("sports_skills." + module)
    fn = getattr(mod, command)
    r = fn(**params)
    if hasattr(r, "model_dump"):
        r = r.model_dump()
    elif hasattr(r, "dict"):
        r = r.dict()
    if isinstance(r, dict) and "data" in r and ("status" in r or "message" in r):
        return r.get("data") or {}
    return r


# ----------------------------------------------------------------------------
# constantes / mapas (reaproveitados do gen-bolao.py)
# ----------------------------------------------------------------------------
DEFAULT_COMP = "serie-a-brazil"
MIN_GAMES = 6
HOME_ADV = 0.35
FINISHED = {"closed", "complete", "final", "ft", "status_final", "post"}

COLOR_MAP = {
    "flamengo": "#D3122A", "fluminense": "#7A1F3D", "vasco da gama": "#52525B",
    "vasco": "#52525B", "botafogo": "#52525B", "palmeiras": "#1D6B3A",
    "corinthians": "#52525B", "bahia": "#1763B5", "cruzeiro": "#1A3A8F",
    "coritiba": "#0B3B2E", "athletico paranaense": "#C8102E", "atletico paranaense": "#C8102E",
    "mirassol": "#E0A100", "gremio": "#0D80BF", "santos": "#111114", "vitoria": "#C8102E",
    "red bull bragantino": "#E2231A", "bragantino": "#E2231A", "internacional": "#C81E27",
    "chapecoense": "#0E7C3A", "atletico-mg": "#111114", "atletico mg": "#111114",
    "sao paulo": "#C8102E", "remo": "#0E5BA6", "gremio fbpa": "#0D80BF",
    "fortaleza": "#0A357E", "juventude": "#15803D", "ceara": "#111114",
    "atletico-go": "#C8102E", "goias": "#0E7C3A",
}
DEFAULT_COLOR = "#52525B"
ID_OVERRIDE = {
    "flamengo": "MEN", "fluminense": "FLU", "vasco da gama": "VAS", "vasco": "VAS",
    "botafogo": "FOG", "palmeiras": "VER", "corinthians": "TIM", "bahia": "BAH",
    "cruzeiro": "RAP",
}


def _norm(name):
    s = (name or "").strip().lower()
    repl = (("á", "a"), ("à", "a"), ("ã", "a"), ("â", "a"),
            ("é", "e"), ("ê", "e"), ("í", "i"), ("ó", "o"),
            ("ô", "o"), ("õ", "o"), ("ú", "u"), ("ç", "c"))
    for a, b in repl:
        s = s.replace(a, b)
    return s


def _color_for(name):
    return COLOR_MAP.get(_norm(name), DEFAULT_COLOR)


def _id3(name, abbr):
    n = _norm(name)
    if n in ID_OVERRIDE:
        return ID_OVERRIDE[n]
    if abbr and len(abbr) >= 2:
        return abbr.upper()[:3]
    letters = [c for c in (name or "").upper() if c.isalpha()]
    return ("".join(letters[:3]) or "TBD").ljust(3, "X")[:3]


def _strength(e):
    pg = e.get("points", 0) / max(1, e.get("played", 1))
    gd = e.get("goal_difference", 0) / max(1, e.get("played", 1))
    return pg + 0.25 * gd


def _baseline_probs(eh, ea):
    diff = (_strength(eh) - _strength(ea)) + HOME_ADV
    p_home_core = 1 / (1 + math.exp(-1.1 * diff))
    p_draw = max(0.16, 0.30 - 0.10 * abs(diff))
    p_home = (1 - p_draw) * p_home_core
    p_away = (1 - p_draw) * (1 - p_home_core)
    return p_home, p_draw, p_away


def _devig_probs(p_home, p_draw, p_away):
    dv = _ss("betting", "devig", odds="%s,%s,%s" % (p_home, p_draw, p_away), format="probability")
    fp = [o["fair_prob"] for o in dv["outcomes"]]
    return fp[0], fp[1], fp[2]


def _pct_round(ph, pd, pa):
    raw = [ph * 100, pd * 100, pa * 100]
    fl = [int(math.floor(x)) for x in raw]
    rem = 100 - sum(fl)
    order = sorted(range(3), key=lambda i: raw[i] - fl[i], reverse=True)
    for i in range(rem):
        fl[order[i]] += 1
    return fl


def _conf_from_probs(p):
    mx, mn = max(p), min(p)
    spread = mx - mn
    if mx >= 50 and spread >= 25:
        return 4
    if p[2] > p[0] and mx < 50:
        return 3
    if spread <= 8:
        return 2
    if spread <= 16:
        return 3
    return 4 if mx >= 45 else 3


def _read_for(hn, an, p, eh, ea):
    ph, pd, pa = p
    fav, dog = (hn, an) if ph >= pa else (an, hn)
    fe = eh if ph >= pa else ea
    mando = "em casa" if fav == hn else "mesmo fora"
    form_fav = (fe.get("form") or "").replace("-", "")[:5]
    spread = max(p) - min(p)
    if max(p) >= 50 and spread >= 25:
        extra = " Vem embalado (%s)." % form_fav if form_fav else ""
        return "%s favorito claro %s: campanha melhor e prob de %s%%.%s" % (fav, mando, max(ph, pa), extra)
    if spread <= 8:
        return "%s x %s muito parelho — leitura aberta, qualquer resultado cabe (%s/%s/%s)." % (hn, an, ph, pd, pa)
    if pa > ph:
        return "%s chega como favorito mesmo fora; %s no mando é a zebra do dia." % (an, hn)
    return "%s leva leve favoritismo %s, mas %s segura o jogo — diferença curta." % (fav, mando, dog)


def _cluster_rounds(fixtures):
    fx = sorted(fixtures, key=lambda x: x.get("start_time", ""))
    rounds, cur, seen = [], [], set()
    for f in fx:
        teams = {c["team"]["id"] for c in f.get("competitors", [])}
        if teams & seen:
            rounds.append(cur)
            cur = []
            seen = set()
        cur.append(f)
        seen |= teams
    if cur:
        rounds.append(cur)
    return rounds


def _comp_pair(f):
    cs = {c["qualifier"]: c["team"] for c in f.get("competitors", [])}
    return cs.get("home"), cs.get("away")


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _resolve_season(season_id, competition_id):
    if season_id:
        return season_id
    season = _ss("football", "get_current_season", competition_id=competition_id)["season"]
    return season["id"]


def _fixtures_for(season_id):
    sch = _ss("football", "get_season_schedule", season_id=season_id)
    return sch.get("schedules") or sch.get("events") or []


def _casa_pick(p):
    return "1" if (p[0] >= p[1] and p[0] >= p[2]) else ("2" if p[2] >= p[1] else "X")


# ----------------------------------------------------------------------------
# comando: gerar_boletim
# ----------------------------------------------------------------------------
def gerar_boletim(request_data):
    ok, err = _ensure_sports_skills()
    if not ok:
        return {"status": False, "message": err}
    params = dict(request_data.get("params") or {})
    competition_id = params.get("competition_id") or DEFAULT_COMP
    try:
        min_games = int(params.get("min_games", MIN_GAMES))
    except Exception:
        min_games = MIN_GAMES

    try:
        season = _ss("football", "get_current_season", competition_id=competition_id)["season"]
        SID = season["id"]

        st = _ss("football", "get_season_standings", season_id=SID)
        entries = st["standings"][0]["entries"]
        by_id = {e["team"]["id"]: e for e in entries}

        fixtures = _fixtures_for(SID)
        upcoming = [f for f in fixtures if str(f.get("status", "")).lower() not in FINISHED]
        upcoming.sort(key=lambda f: f.get("start_time", ""))

        if len(upcoming) >= min_games:
            chosen = upcoming[:max(min_games, min(10, len(upcoming)))]
            live = True
        elif upcoming:
            chosen = upcoming
            live = True
        else:
            rounds = _cluster_rounds(fixtures)
            big = [r for r in rounds if len(r) >= min_games]
            chosen = (big[-1] if big else rounds[-1])
            live = False

        chosen.sort(key=lambda f: f.get("start_time", ""))

        rounds_all = _cluster_rounds(fixtures)
        rodada_num = len(rounds_all)
        for idx, r in enumerate(rounds_all, 1):
            if r and chosen and r[0].get("id") == chosen[0].get("id"):
                rodada_num = idx
                break

        jogos = []
        for f in chosen:
            home, away = _comp_pair(f)
            if not home or not away:
                continue
            eh = by_id.get(home["id"]) or {"points": 0, "played": 1, "goal_difference": 0, "form": ""}
            ea = by_id.get(away["id"]) or {"points": 0, "played": 1, "goal_difference": 0, "form": ""}
            ph0, pd0, pa0 = _baseline_probs(eh, ea)
            ph, pd, pa = _devig_probs(ph0, pd0, pa0)
            p = _pct_round(ph, pd, pa)
            hn, an = home["name"], away["name"]
            jogos.append({
                "match_id": str(f.get("id", "")),
                "kickoff": f.get("start_time", "") or "",
                "h": {"id": _id3(hn, home.get("abbreviation")), "nm": hn, "c": _color_for(hn)},
                "a": {"id": _id3(an, away.get("abbreviation")), "nm": an, "c": _color_for(an)},
                "p": p,
                "read": _read_for(hn, an, p, eh, ea),
                "conf": _conf_from_probs(p),
            })

        boletim = {
            "rodada": rodada_num,
            "competicao": "Brasileirão 2026",
            "season_id": SID,
            "live": live,
            "gerado_em": _now_iso(),
            "metodo_versao": "sportsclaw-v0",
            "fonte": "sportsclaw (sports-skills + devig) — SEM Sportradar",
            "jogos": jogos,
        }
        return {"status": True, "data": {"boletim": boletim, "season_id": SID,
                                         "rodada": rodada_num, "n_jogos": len(jogos)}}
    except Exception as e:
        return {"status": False, "message": "gerar_boletim falhou: " + str(e)}


# ----------------------------------------------------------------------------
# comando: settle_rodada
# ----------------------------------------------------------------------------
def _score_pair(f):
    sc = f.get("scores") or {}
    gh, ga = sc.get("home"), sc.get("away")
    if gh is not None and ga is not None:
        try:
            return int(gh), int(ga)
        except Exception:
            pass
    gh = ga = None
    for c in f.get("competitors", []):
        q = c.get("qualifier")
        v = c.get("score")
        if v is None:
            for k in ("score_display", "points", "goals", "runs"):
                if c.get(k) is not None:
                    v = c.get(k)
                    break
        if v is None:
            continue
        try:
            v = int(str(v).strip())
        except Exception:
            continue
        if q == "home":
            gh = v
        elif q == "away":
            ga = v
    return gh, ga


def settle_rodada(request_data):
    ok, err = _ensure_sports_skills()
    if not ok:
        return {"status": False, "message": err}
    params = dict(request_data.get("params") or {})
    competition_id = params.get("competition_id") or DEFAULT_COMP
    jogos = params.get("jogos") or []
    rodada = params.get("rodada", 0)
    if not jogos:
        return {"status": False, "message": "settle_rodada: faltou 'jogos' (boletim salvo)."}

    try:
        SID = _resolve_season(params.get("season_id"), competition_id)
        fixtures = _fixtures_for(SID)
        by_match = {str(f.get("id", "")): f for f in fixtures}

        resultados = []
        n_ok = 0
        for j in jogos:
            p = j.get("p") or [0, 0, 0]
            casa_pick = _casa_pick(p)
            f = by_match.get(str(j.get("match_id", "")))
            gh, ga = (None, None) if f is None else _score_pair(f)
            base = {"match_id": j.get("match_id"), "h": j.get("h"), "a": j.get("a"),
                    "casa_pick": casa_pick, "p": p}
            if gh is None or ga is None:
                base.update({"placar": None, "status": "sem_placar",
                             "resultado": None, "casa_ok": None})
            else:
                res = "1" if gh > ga else ("2" if ga > gh else "X")
                base.update({"placar": [gh, ga], "status": "final",
                             "resultado": res, "casa_ok": (casa_pick == res)})
                n_ok += 1
            resultados.append(base)

        resultado = {
            "rodada": rodada,
            "competicao": "Brasileirão 2026",
            "season_id": SID,
            "gerado_em": _now_iso(),
            "metodo_versao": "sportsclaw-v0",
            "fonte": "sportsclaw (sports-skills) — SEM Sportradar",
            "jogos": resultados,
        }
        return {"status": True, "data": {"resultado": resultado, "n_com_placar": n_ok}}
    except Exception as e:
        return {"status": False, "message": "settle_rodada falhou: " + str(e)}
