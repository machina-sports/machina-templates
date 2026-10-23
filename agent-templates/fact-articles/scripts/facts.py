"""Step 1: every fact the article may use, with its source, for one match of the round.

Input is the connector dataset (see connectors/sports_skills_football.py). Fact text is pt-BR:
it is what the writer quotes and what the verifier checks numbers and names against.
Scores are filled by rank.py and norms by plan.py; here they start at 0.
"""
from datetime import datetime, timedelta


class MissingFactError(RuntimeError):
    """A mandatory fact could not be built from the feed: connector data is incomplete, no article."""


def dec(x):
    return f"{x:.2f}".replace(".", ",")


def pts_word(n):
    return count(n, "ponto", "pontos")


def count(n, one, many):
    return f"{n} {one if n == 1 else many}"


STATUS_NOTE = {"postponed": "Partida adiada.", "cancelled": "Partida cancelada.", "live": "Partida em andamento.",
               "suspended": "Partida suspensa.",
               "closed": "Partida encerrada."}


def status_note(status):
    """The feed status in the match text when the game is not simply scheduled, so the writer cannot miss it."""
    if status in ("", "not_started", "scheduled"):
        return ""
    return " " + STATUS_NOTE.get(status, f"Situação no feed: {status}.")


def to_local(iso, offset_hours):
    return datetime.strptime(iso, "%Y-%m-%dT%H:%MZ") + timedelta(hours=offset_hours)


def result(gf, ga):
    return "V" if gf > ga else "E" if gf == ga else "D"


def games_of(team_id, results, offset_hours):
    out = []
    for e in results:
        home, away = e["competitors"]
        if team_id not in (home["team"]["id"], away["team"]["id"]):
            continue
        me, opp = (home, away) if home["team"]["id"] == team_id else (away, home)
        out.append({
            "date": to_local(e["start_time"], offset_hours).strftime("%d/%m"),
            "opponent": opp["team"]["short_name"], "opponent_id": opp["team"]["id"],
            "where": "casa" if me is home else "fora",
            "gf": me["score"], "ga": opp["score"], "result": result(me["score"], opp["score"]),
            "event_id": e["id"],
        })
    return out


WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
STREAKS = {"vitórias seguidas": "V", "jogos sem perder": "VE", "jogos sem vencer": "ED", "derrotas seguidas": "D"}
BROKEN_LABEL = {"vitórias seguidas": "o último jogo sem vitória", "jogos sem perder": "a última derrota",
                "jogos sem vencer": "a última vitória", "derrotas seguidas": "o último ponto"}


def streak(games):
    """Longest current run of 3+ games, with the game that broke it (None if the run is the whole season)."""
    best = None
    for name, ok in STREAKS.items():
        n = 0
        for g in reversed(games):
            if g["result"] not in ok:
                break
            n += 1
        if n >= 3 and (best is None or n > best[1]):
            best = (name, n, games[-n - 1] if n < len(games) else None)
    return best


def league_context(dataset, client):
    table = dataset["standings"]
    results = dataset["results"]
    points = [r["points"] for r in table]
    mean = sum(points) / len(points)
    n_home = sum(e["scores"]["home"] > e["scores"]["away"] for e in results)
    n_away = sum(e["scores"]["home"] < e["scores"]["away"] for e in results)
    first_rel = len(table) - int(client.get("relegation_spots", 4)) + 1
    by_pos = {r["position"]: r for r in table}
    return {
        "by_id": {r["team"]["id"]: r for r in table},
        "by_pos": by_pos,
        "mean_points": mean,
        "max_dev": max(abs(p - mean) for p in points),
        "gpg": sum(r["goals_for"] for r in table) / max(1, sum(r["played"] for r in table)),
        "home_win": n_home / max(1, len(results)),
        "away_win": n_away / max(1, len(results)),
        "first_rel": by_pos.get(first_rel),
        "last_safe": by_pos.get(first_rel - 1),
    }


def build(event, dataset, client, ctx=None):
    """Facts for one event. Raises MissingFactError when a team is not in the table."""
    ctx = ctx or league_context(dataset, client)
    off = int(client.get("timezone_offset_hours", 0))
    source, as_of = client.get("data_source_label", "data feed"), dataset["as_of"]
    comp = client.get("competition_name") or dataset["competition"]["name"]
    home, away = event["competitors"]
    hid, aid = home["team"]["id"], away["team"]["id"]
    when = to_local(event["start_time"], off)
    venue = event.get("venue") or {}
    facts = []

    def add(kind, subject, value, text):
        facts.append({"id": f"f{len(facts) + 1:02d}", "kind": kind, "subject": subject, "value": value,
                      "text": text, "score": 0.0, "norm": 0.0, "source": source, "as_of": as_of, "tier": "data"})

    tz = f" ({client['timezone_label']})" if client.get("timezone_label") else ""
    weekday = WEEKDAYS[when.weekday()]
    sign = "+" if off >= 0 else "-"
    add("match", "both", {
        "home": home["team"]["short_name"], "away": away["team"]["short_name"],
        "date": when.strftime("%d/%m/%Y"), "time_local": when.strftime("%Hh%M"),
        "start_iso": when.strftime("%Y-%m-%dT%H:%M:00") + f"{sign}{abs(off):02d}:00",
        "venue": venue.get("name", ""), "city": venue.get("city", ""), "competition": comp,
        "status": event.get("status", ""), "sport": client.get("sport", ""),
    }, f"{home['team']['short_name']} x {away['team']['short_name']}, {weekday}, {when:%d/%m/%Y} às {when:%Hh%M}{tz}, "
       f"{venue.get('name', '')}, {venue.get('city', '')}, {comp}.{status_note(event.get('status', ''))}")

    for tid, label in ((hid, "home"), (aid, "away")):
        r = ctx["by_id"].get(tid)
        if r is None:
            raise MissingFactError(f"connector error: team {tid} of event {event['id']} is not in the standings")
        name, played = r["team"]["short_name"], r["played"]
        games = games_of(tid, dataset["results"], off)
        pos = r["position"]
        neighbours = [ctx["by_pos"][p]["points"] for p in (pos - 1, pos + 1) if p in ctx["by_pos"]]
        add("standing", label, {
            **{k: r[k] for k in ("position", "points", "played", "won", "drawn", "lost", "goals_for", "goals_against")},
            "nearest_gap": min(abs(r["points"] - p) for p in neighbours) if neighbours else 0,
            "league_mean_points": round(ctx["mean_points"], 2), "league_max_dev": round(ctx["max_dev"], 2),
        }, f"{name}: {pos}º lugar, {r['points']} pontos em {count(played, 'jogo', 'jogos')} ({r['won']}V {r['drawn']}E {r['lost']}D), "
           f"{r['goals_for']} gols marcados e {r['goals_against']} sofridos.")

        first_rel, last_safe = ctx["first_rel"], ctx["last_safe"]
        if first_rel and last_safe and pos < first_rel["position"]:
            gap = r["points"] - first_rel["points"]
            add("relegation_gap", label, {"points_over_first_relegated": gap, "team": first_rel["team"]["short_name"],
                                          "team_position": first_rel["position"], "team_points": first_rel["points"]},
                f"{name} tem {pts_word(gap)} a mais que o {first_rel['position']}º colocado ({first_rel['team']['short_name']}, "
                f"{first_rel['points']} pontos), a primeira posição da zona de rebaixamento.")
        elif first_rel and last_safe:
            # Inside the zone the distance that matters is to safety (the last safe spot), not to the zone's first spot.
            gap = last_safe["points"] - r["points"]
            add("relegation_gap", label, {"points_to_safety": gap, "team": last_safe["team"]["short_name"],
                                          "team_position": last_safe["position"], "team_points": last_safe["points"]},
                f"{name} está na zona de rebaixamento, em {pos}º, {pts_word(gap)} atrás do {last_safe['position']}º colocado "
                f"({last_safe['team']['short_name']}, {last_safe['points']} pontos).")

        last5 = games[-5:]
        if last5:
            w, d, l = (sum(g["result"] == x for g in last5) for x in "VED")
            pts5 = 3 * w + d
            add("last5", label, {"games": last5, "won": w, "drawn": d, "lost": l, "points": pts5,
                                 "season_points": r["points"], "season_played": played},
                (f"Últimos {len(last5)} jogos" if len(last5) > 1 else "Último jogo") + f" do {name}: " + "; ".join(
                    f"{g['date']}: {g['gf']}x{g['ga']} contra {g['opponent']} ({g['where']}, {g['result']})" for g in last5)
                + f". {pts5} de {3 * len(last5)} pontos possíveis: "
                f"{count(w, 'vitória', 'vitórias')}, {count(d, 'empate', 'empates')} e {count(l, 'derrota', 'derrotas')}.")

        s = streak(games)
        if s:
            kind, n, brk = s
            add("streak", label, {"type": kind, "length": n, "broken_by": brk},
                f"{name} está com {n} {kind} no {comp}." + (
                    f" {BROKEN_LABEL[kind].capitalize()} foi em {brk['date']}: {brk['gf']}x{brk['ga']} contra "
                    f"{brk['opponent']} ({brk['where']})." if brk else ""))

        gf_pg, ga_pg = r["goals_for"] / max(1, played), r["goals_against"] / max(1, played)
        if played:  # no games, no rate: do not state a 0,00 the data does not have
            add("goals_rate", label, {"gf_per_game": round(gf_pg, 2), "ga_per_game": round(ga_pg, 2), "league_avg": round(ctx["gpg"], 2)},
                f"{name} marca {dec(gf_pg)} e sofre {dec(ga_pg)} gols por jogo; a média do {comp} é {dec(ctx['gpg'])} gols por time por jogo.")

        where = "casa" if label == "home" else "fora"
        gw = [g for g in games if g["where"] == where]
        if gw:
            w, d, l = (sum(g["result"] == x for g in gw) for x in "VED")
            rate = ctx["home_win"] if where == "casa" else ctx["away_win"]
            add(f"{where}_record", label, {"games": len(gw), "won": w, "drawn": d, "lost": l,
                                           "gf": sum(g["gf"] for g in gw), "ga": sum(g["ga"] for g in gw),
                                           "league_win_rate": round(rate, 2)},
                f"{name} {'em casa' if where == 'casa' else 'fora de casa'}: {count(len(gw), 'jogo', 'jogos')}, {w}V {d}E {l}D, "
                f"{sum(g['gf'] for g in gw)} gols marcados e {sum(g['ga'] for g in gw)} sofridos. "
                f"No {comp}, o {'mandante' if where == 'casa' else 'visitante'} vence {round(rate * 100)}% dos jogos.")

    hn, an = home["team"]["short_name"], away["team"]["short_name"]
    for g in (g for g in games_of(hid, dataset["results"], off) if g["opponent_id"] == aid):
        add("h2h_season", "both", g, (
            f"Primeiro turno, {g['date']}, em casa do {hn}: {hn} {g['gf']}x{g['ga']} {an}." if g["where"] == "casa" else
            f"Primeiro turno, {g['date']}, em casa do {an}: {an} {g['ga']}x{g['gf']} {hn}."))
    return facts


def check_mandatory(facts, contract, event_id):
    """Raise MissingFactError if the contract's mandatory facts are not all there."""
    missing = []
    for kind in contract.get("mandatory", []):
        if kind == "match":
            m = next((f for f in facts if f["kind"] == "match"), None)
            empty = [k for k in contract.get("match_fields", []) if not (m and m["value"].get(k))]
            missing += [f"match.{k}" for k in empty]
        else:
            missing += [f"{kind}.{s}" for s in ("home", "away") if not any(f["kind"] == kind and f["subject"] == s for f in facts)]
    if missing:
        raise MissingFactError(f"connector error: event {event_id} lacks mandatory facts {missing}; no article")


PLAYED = {"closed", "finished"}


def build_doc(event, dataset, contract, client, ctx=None):
    if event.get("status") in PLAYED:  # a preview of a played game would state a past match as upcoming
        raise MissingFactError(f"event {event['id']} status {event['status']!r}: already played, no preview")
    facts = [f for f in build(event, dataset, client, ctx) if f["kind"] in contract["kinds"]]
    check_mandatory(facts, contract, event["id"])
    return {"event_id": event["id"], "facts": facts}


def build_round(dataset, contract, client):
    """(facts_docs, errors): a match with missing mandatory facts gets no article; the rest of the round goes on."""
    ctx = league_context(dataset, client)
    docs, errors = [], {}
    for e in dataset["events"]:
        try:
            docs.append(build_doc(e, dataset, contract, client, ctx))
        except MissingFactError as err:
            errors[e["id"]] = str(err)
    return docs, errors


def invoke_facts(request_data):
    p = request_data.get("params") or {}
    try:
        docs, errors = build_round(p["dataset"], p["contract"], p["client"])
    except KeyError as e:
        return {"status": False, "message": f"missing param {e}"}
    return {"status": True, "data": {"facts_docs": docs, "errors": errors}}
