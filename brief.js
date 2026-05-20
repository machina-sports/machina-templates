// brief.js — Pre-game brief generator
// White-label: refers to "the broadcaster" / "the production team".
// Empty sections render a placeholder, never get dropped.

(function () {
  "use strict";

  // ---------- Config ----------
  const WF = {
    fixture:      "football-data-get-fixture",
    recentForm:   "football-data-get-team-recent-form",
    headToHead:   "football-data-get-head-to-head",
    lineup:       "football-data-get-projected-lineup",
  };
  const RECENT_LAST = 5;
  const H2H_LAST = 5;

  // ---------- DOM ----------
  const $ = (id) => document.getElementById(id);
  const form        = $("brief-form");
  const fxInput     = $("fixture-id");
  const generateBtn = $("generate-btn");
  const statusEl    = $("status");
  const sectionEl   = $("section-status");
  const briefEl     = $("brief");
  const copyBtn     = $("copy-btn");
  const downloadBtn = $("download-btn");

  // ---------- State ----------
  const state = {
    busy: false,
    abort: null,                 // AbortController for in-flight requests
    lastMarkdown: "",            // for copy/download
    currentRunId: 0,             // monotonic id to ignore stale async results
  };

  // ---------- Status helpers ----------
  function setStatus(text, tone = "idle") {
    if (!statusEl) return;
    statusEl.dataset.tone = tone;
    const prefix = tone === "busy"
      ? '<span class="blink" aria-hidden="true"></span>'
      : "";
    statusEl.innerHTML = prefix + escapeHtml(text);
  }

  // section-status pills
  const SECTIONS = ["fixture", "form-home", "form-away", "h2h", "lineups"];
  const SECTION_LABELS = {
    "fixture":   "Fixture",
    "form-home": "Home form",
    "form-away": "Away form",
    "h2h":       "H2H",
    "lineups":   "Lineups",
  };
  function resetSections(initialState = "idle") {
    sectionEl.innerHTML = SECTIONS.map(k => pillHtml(k, initialState, "—")).join("");
  }
  function setSection(key, state, note) {
    const el = sectionEl.querySelector(`[data-key="${key}"]`);
    if (!el) return;
    el.outerHTML = pillHtml(key, state, note);
  }
  function pillHtml(key, state, note) {
    return `<span class="pill" data-key="${key}" data-state="${state}">
      <span class="sw" aria-hidden="true"></span>
      <span>${escapeHtml(SECTION_LABELS[key])}</span>
      <span style="opacity:.7">${escapeHtml(note || "")}</span>
    </span>`;
  }

  // ---------- Markdown rendering ----------
  // Lightweight markdown -> HTML for the in-page preview. Intentionally
  // narrow: headings, paragraphs, lists, blockquotes, bold/italic, code.
  // The raw markdown is what we copy/download — preview is just a courtesy.
  function renderMarkdown(md) {
    const lines = md.split(/\r?\n/);
    let html = "";
    let inList = false;
    let inPara = false;
    const closePara = () => { if (inPara) { html += "</p>"; inPara = false; } };
    const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };

    for (const raw of lines) {
      const line = raw.trimEnd();
      if (!line.trim()) { closePara(); closeList(); continue; }

      // Headings
      const h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) {
        closePara(); closeList();
        const lvl = h[1].length;
        html += `<h${lvl}>${inlineMd(h[2])}</h${lvl}>`;
        continue;
      }
      // Blockquote
      if (line.startsWith("> ")) {
        closePara(); closeList();
        html += `<blockquote>${inlineMd(line.slice(2))}</blockquote>`;
        continue;
      }
      // List item
      if (/^[-*]\s+/.test(line)) {
        closePara();
        if (!inList) { html += "<ul>"; inList = true; }
        html += `<li>${inlineMd(line.replace(/^[-*]\s+/, ""))}</li>`;
        continue;
      }
      // Horizontal rule
      if (/^---+$/.test(line)) {
        closePara(); closeList();
        html += "<hr/>";
        continue;
      }
      // Paragraph (joined)
      closeList();
      if (!inPara) { html += "<p>"; inPara = true; } else { html += " "; }
      html += inlineMd(line);
    }
    closePara(); closeList();
    return html;
  }
  function inlineMd(s) {
    s = escapeHtml(s);
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
    return s;
  }
  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // ---------- Markdown composition ----------
  // Inputs: fixture (obj), homeForm (arr), awayForm (arr), h2h (arr), lineups (arr)
  // Each section renders a one-line placeholder if its data is empty.

  function composeBrief({ fixture, homeForm, awayForm, h2h, lineups }) {
    const home = (fixture && fixture.teams && fixture.teams.home) || {};
    const away = (fixture && fixture.teams && fixture.teams.away) || {};
    const league = (fixture && fixture.league) || {};
    const venue = (fixture && fixture.venue) || {};
    const status = (fixture && fixture.status) || {};
    const kickoff = fixture && fixture.date ? formatKickoff(fixture.date) : "Kickoff time TBC";

    const homeName = home.name || "Home side";
    const awayName = away.name || "Away side";
    const lines = [];

    // ---- Header
    lines.push(`# ${homeName} vs ${awayName} — pre-game brief`);
    const headerBits = [];
    if (league.name)     headerBits.push(league.name + (league.round ? ` · ${league.round}` : ""));
    if (kickoff)         headerBits.push(kickoff);
    if (venue.name)      headerBits.push(`${venue.name}${venue.city ? `, ${venue.city}` : ""}`);
    if (fixture && fixture.referee) headerBits.push(`Referee: ${fixture.referee}`);
    if (headerBits.length) lines.push("");
    if (headerBits.length) lines.push("`" + headerBits.join("  ·  ") + "`");
    lines.push("");

    // ---- Storylines (derived strictly from the data we have)
    lines.push("## Storylines");
    const storylines = deriveStorylines({ home, away, league, venue, fixture, homeForm, awayForm, h2h });
    if (storylines.length) {
      storylines.forEach(s => lines.push("- " + s));
    } else {
      lines.push("- _Storylines pending — limited pre-match data available so far._");
    }
    lines.push("");

    // ---- Recent form
    lines.push(`## Recent form — last ${RECENT_LAST}`);
    lines.push("");
    lines.push(`### ${homeName}`);
    lines.push(...renderFormBlock(homeForm, home.id, homeName));
    lines.push("");
    lines.push(`### ${awayName}`);
    lines.push(...renderFormBlock(awayForm, away.id, awayName));
    lines.push("");

    // ---- Head-to-head
    lines.push(`## Head-to-head — last ${H2H_LAST}`);
    if (!h2h || h2h.length === 0) {
      lines.push("_No head-to-head meetings on record between these sides in the available window._");
    } else {
      const tally = h2hTally(h2h, home.id, away.id);
      lines.push(`**Tally:** ${homeName} ${tally.homeWins} · Draws ${tally.draws} · ${awayName} ${tally.awayWins}`);
      lines.push("");
      h2h.forEach(m => {
        lines.push("- " + formatMatchLine(m, /*highlightTeamId*/ null));
      });
    }
    lines.push("");

    // ---- Projected lineups
    lines.push("## Projected lineups");
    if (!lineups || lineups.length === 0) {
      lines.push("_Lineup not yet confirmed. The production team should plan to refresh this section ~60 minutes before kickoff, when the teamsheets are published._");
    } else {
      lineups.forEach(line => {
        lines.push("");
        lines.push(`### ${line.team && line.team.name ? line.team.name : "Team"}${line.formation ? ` — ${line.formation}` : ""}`);
        if (line.coach) lines.push(`_Coach: ${line.coach}_`);
        const xi = Array.isArray(line.startXI) ? line.startXI : [];
        if (xi.length === 0) {
          lines.push("- _Starting XI not yet released._");
        } else {
          xi.forEach(p => {
            const num = p.number ? `**${p.number}**` : "**—**";
            const pos = p.pos ? ` (${p.pos})` : "";
            lines.push(`- ${num} ${p.name || "Unnamed player"}${pos}`);
          });
        }
        const subs = Array.isArray(line.substitutes) ? line.substitutes : [];
        if (subs.length) {
          const named = subs.map(p => `${p.number || "—"} ${p.name || ""}`.trim()).join(", ");
          lines.push("");
          lines.push(`_Bench:_ ${named}`);
        }
      });
    }
    lines.push("");

    // ---- Production notes (white-label, no operator naming)
    lines.push("## Production notes");
    lines.push("- This brief is white-label — refer to **the broadcaster** and **the production team** on air; do not name a specific operator.");
    lines.push("- All claims above are sourced from the live data feed; do not extend predictions beyond what the numbers show.");
    lines.push("- Refresh ~60 minutes pre-kickoff to lock in the confirmed lineups and any late storyline updates.");
    lines.push("");
    lines.push("---");
    lines.push(`_Generated by the pre-game brief generator · fixture #${fixture && fixture.id ? fixture.id : "—"} · ${new Date().toISOString()}_`);

    return lines.join("\n");
  }

  function deriveStorylines({ home, away, league, venue, fixture, homeForm, awayForm, h2h }) {
    const out = [];

    // Competition / round
    if (league && league.name) {
      const roundBit = league.round ? ` (${league.round})` : "";
      out.push(`Competition: **${league.name}**${roundBit}.`);
    }
    // Venue + status
    if (venue && venue.name) {
      out.push(`Played at **${venue.name}**${venue.city ? `, ${venue.city}` : ""}.`);
    }
    if (fixture && fixture.status && fixture.status.long) {
      out.push(`Fixture status flagged as *${fixture.status.long}* by the data feed.`);
    }

    // Recent form summary per side
    if (Array.isArray(homeForm) && homeForm.length && home && home.id) {
      const s = formStreak(homeForm, home.id);
      out.push(`**${home.name}** form (last ${homeForm.length}): ${s.summary} — ${s.line}.`);
    }
    if (Array.isArray(awayForm) && awayForm.length && away && away.id) {
      const s = formStreak(awayForm, away.id);
      out.push(`**${away.name}** form (last ${awayForm.length}): ${s.summary} — ${s.line}.`);
    }

    // H2H tally
    if (Array.isArray(h2h) && h2h.length && home && home.id && away && away.id) {
      const t = h2hTally(h2h, home.id, away.id);
      out.push(`Last ${h2h.length} meetings: **${home.name}** ${t.homeWins} · Draws ${t.draws} · **${away.name}** ${t.awayWins}.`);
    }

    return out;
  }

  function renderFormBlock(form, teamId, teamName) {
    if (!Array.isArray(form) || form.length === 0) {
      return ["_Form data unavailable for the available window._"];
    }
    const streak = formStreak(form, teamId);
    const lines = [];
    lines.push(`**Form:** ${streak.summary}  ·  ${streak.line}`);
    lines.push("");
    form.forEach(m => {
      lines.push("- " + formatMatchLine(m, teamId));
    });
    return lines;
  }

  // Convert a list of matches into a W/D/L summary string + a sentence.
  function formStreak(matches, teamId) {
    let w = 0, d = 0, l = 0, gf = 0, ga = 0;
    const tokens = [];
    matches.forEach(m => {
      const isHome = m.home && m.home.id === teamId;
      const isAway = m.away && m.away.id === teamId;
      if (!isHome && !isAway) { tokens.push("·"); return; }
      const my  = isHome ? m.goals && m.goals.home : m.goals && m.goals.away;
      const opp = isHome ? m.goals && m.goals.away : m.goals && m.goals.home;
      if (typeof my === "number" && typeof opp === "number") {
        gf += my; ga += opp;
        if (my > opp)      { w++; tokens.push("W"); }
        else if (my < opp) { l++; tokens.push("L"); }
        else               { d++; tokens.push("D"); }
      } else {
        // Winner field fallback
        const won = isHome ? m.home && m.home.winner : m.away && m.away.winner;
        if (won === true)  { w++; tokens.push("W"); }
        else if (won === false) { l++; tokens.push("L"); }
        else { d++; tokens.push("D"); }
      }
    });
    const summary = `${tokens.join(" ")}  (${w}W ${d}D ${l}L)`;
    const line = `${gf} goals scored, ${ga} conceded across these ${matches.length} matches`;
    return { w, d, l, gf, ga, summary, line };
  }

  function h2hTally(matches, homeTeamId, awayTeamId) {
    let homeWins = 0, awayWins = 0, draws = 0;
    matches.forEach(m => {
      const hg = m.goals && m.goals.home, ag = m.goals && m.goals.away;
      const homeTeamOnHomeSide = m.home && m.home.id === homeTeamId;
      if (typeof hg === "number" && typeof ag === "number") {
        if (hg === ag) { draws++; return; }
        const homeSideWon = hg > ag;
        if (homeTeamOnHomeSide ? homeSideWon : !homeSideWon) homeWins++;
        else awayWins++;
      } else if (m.home && m.home.winner != null) {
        const homeSideWon = m.home.winner === true;
        const homeSideDraw = m.home.winner == null && m.away && m.away.winner == null;
        if (homeSideDraw) { draws++; return; }
        if (homeTeamOnHomeSide ? homeSideWon : !homeSideWon) homeWins++;
        else awayWins++;
      } else {
        draws++;
      }
    });
    return { homeWins, awayWins, draws };
  }

  function formatMatchLine(m, highlightTeamId) {
    const date = m.date ? formatShortDate(m.date) : "TBC";
    const homeName = m.home && m.home.name ? m.home.name : "Home";
    const awayName = m.away && m.away.name ? m.away.name : "Away";
    const score = (m.goals && typeof m.goals.home === "number" && typeof m.goals.away === "number")
      ? `${m.goals.home}–${m.goals.away}`
      : "vs";
    let homeStr = homeName, awayStr = awayName;
    if (highlightTeamId && m.home && m.home.id === highlightTeamId) homeStr = `**${homeName}**`;
    if (highlightTeamId && m.away && m.away.id === highlightTeamId) awayStr = `**${awayName}**`;
    const league = m.league ? ` · ${m.league}` : "";
    return `\`${date}\` ${homeStr} ${score} ${awayStr}${league}`;
  }

  function formatKickoff(iso) {
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return iso;
      return d.toLocaleString(undefined, {
        weekday: "short", year: "numeric", month: "short",
        day: "numeric", hour: "2-digit", minute: "2-digit",
        timeZoneName: "short",
      });
    } catch { return iso; }
  }
  function formatShortDate(iso) {
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return iso;
      return d.toISOString().slice(0, 10);
    } catch { return iso; }
  }

  // ---------- Workflow caller ----------
  function callWorkflow(name, body, signal) {
    const deploy = window.MACHINA_DEPLOY;
    if (!deploy || !deploy.proxyUrl) {
      return Promise.reject(new Error(
        "Live data unavailable — this page must be opened through a Factory deploy " +
        "(window.MACHINA_DEPLOY missing)."
      ));
    }
    const url = deploy.proxyUrl.replace(/\/+$/, "") + "/workflow/execute/" + encodeURIComponent(name);
    return fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body || {}),
      signal,
    }).then(async (res) => {
      if (!res.ok) {
        const txt = await safeText(res);
        throw new Error(`Workflow ${name} returned HTTP ${res.status}: ${truncate(txt, 220)}`);
      }
      const data = await res.json();
      // Machina sync execute returns { ..., outputs: {...} } or wrapped inside data.data
      const outputs = pickOutputs(data);
      if (!outputs) {
        throw new Error(`Workflow ${name} returned no outputs.`);
      }
      // surface workflow-error if present
      if (outputs["workflow-error"]) {
        const err = outputs["workflow-error"];
        const msg = typeof err === "string" ? err
          : err.message ? err.message
          : `code ${err.code || "?"}`;
        throw new Error(`Workflow ${name} failed upstream: ${truncate(msg, 220)}`);
      }
      return outputs;
    });
  }
  function pickOutputs(data) {
    if (!data || typeof data !== "object") return null;
    // common shapes: { outputs: {...} } | { data: { outputs: {...} } } | { workflow_output: { outputs: {...} } }
    if (data.outputs) return data.outputs;
    if (data.workflow_output && data.workflow_output.outputs) return data.workflow_output.outputs;
    if (data.data) return pickOutputs(data.data);
    return null;
  }
  async function safeText(res) {
    try { return (await res.text()).slice(0, 400); } catch { return ""; }
  }
  function truncate(s, n) {
    s = String(s || "");
    return s.length > n ? s.slice(0, n) + "…" : s;
  }

  // ---------- Pipeline ----------
  async function generate(fixtureId) {
    if (state.busy) return;
    if (state.abort) state.abort.abort();
    const myRun = ++state.currentRunId;
    state.busy = true;
    generateBtn.disabled = true;
    state.abort = new AbortController();
    const { signal } = state.abort;

    resetSections("idle");
    setSection("fixture", "busy", "loading");
    setStatus(`Fetching fixture #${fixtureId}…`, "busy");

    try {
      // 1. Fixture
      const fxOut = await callWorkflow(WF.fixture, { fixture_id: numberOrString(fixtureId) }, signal);
      if (myRun !== state.currentRunId) return; // stale
      const fixture = (fxOut && fxOut.fixture) || {};
      if (!fixture || !fixture.id || !fixture.teams || !fixture.teams.home || !fixture.teams.away) {
        setSection("fixture", "error", "no data");
        throw new Error(`No fixture found for id ${fixtureId}. Double-check the API-Football fixture id.`);
      }
      setSection("fixture", "ok", `${fixture.teams.home.name} vs ${fixture.teams.away.name}`);

      const homeId = fixture.teams.home.id;
      const awayId = fixture.teams.away.id;

      // 2 + 3 + 4 in parallel — all independent given the team ids + fixture id.
      setSection("form-home", "busy", "loading");
      setSection("form-away", "busy", "loading");
      setSection("h2h",       "busy", "loading");
      setSection("lineups",   "busy", "loading");
      setStatus("Fetching recent form, head-to-head and projected lineups…", "busy");

      const settled = await Promise.allSettled([
        callWorkflow(WF.recentForm, { team_id: homeId, last: RECENT_LAST }, signal),
        callWorkflow(WF.recentForm, { team_id: awayId, last: RECENT_LAST }, signal),
        callWorkflow(WF.headToHead, { team_a_id: homeId, team_b_id: awayId, last: H2H_LAST }, signal),
        callWorkflow(WF.lineup,     { fixture_id: numberOrString(fixtureId) }, signal),
      ]);
      if (myRun !== state.currentRunId) return; // stale

      const [homeFormR, awayFormR, h2hR, lineupsR] = settled;
      const homeForm = settleArray(homeFormR, "matches");
      const awayForm = settleArray(awayFormR, "matches");
      const h2h      = settleArray(h2hR,      "matches");
      const lineups  = settleArray(lineupsR,  "lineups");

      // Pills
      setSection("form-home",
        homeFormR.status === "fulfilled" ? "ok"  : "warn",
        homeFormR.status === "fulfilled" ? `${homeForm.length} match${homeForm.length === 1 ? "" : "es"}` : "fallback");
      setSection("form-away",
        awayFormR.status === "fulfilled" ? "ok"  : "warn",
        awayFormR.status === "fulfilled" ? `${awayForm.length} match${awayForm.length === 1 ? "" : "es"}` : "fallback");
      setSection("h2h",
        h2hR.status === "fulfilled" ? "ok" : "warn",
        h2hR.status === "fulfilled" ? `${h2h.length} meeting${h2h.length === 1 ? "" : "s"}` : "fallback");
      setSection("lineups",
        lineupsR.status === "fulfilled"
          ? (lineups.length ? "ok" : "warn")
          : "warn",
        lineupsR.status === "fulfilled"
          ? (lineups.length ? `${lineups.length} side${lineups.length === 1 ? "" : "s"}` : "not yet confirmed")
          : "fallback");

      // Compose + render
      const md = composeBrief({ fixture, homeForm, awayForm, h2h, lineups });
      paintBrief(md, fixture);

      const partials = settled.filter(r => r.status === "rejected").length;
      if (partials === 0) {
        setStatus(`Brief ready — fixture #${fixture.id}, all sections live.`, "ok");
      } else {
        setStatus(`Brief ready — fixture #${fixture.id}, ${partials} section(s) fell back to a placeholder.`, "warn");
      }
    } catch (err) {
      console.error("generate failed:", err);
      // Mark any still-busy sections as error so the UI is honest.
      ["fixture","form-home","form-away","h2h","lineups"].forEach(k => {
        const cur = sectionEl.querySelector(`[data-key="${k}"]`);
        if (cur && cur.dataset.state === "busy") setSection(k, "error", "—");
      });
      setStatus(`Couldn't generate brief: ${err.message || err}`, "error");
    } finally {
      state.busy = false;
      generateBtn.disabled = false;
    }
  }

  function settleArray(r, key) {
    if (r.status !== "fulfilled" || !r.value) return [];
    const v = r.value[key];
    return Array.isArray(v) ? v : [];
  }

  function numberOrString(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n : String(v);
  }

  // ---------- Render ----------
  function paintBrief(md, fixture) {
    state.lastMarkdown = md;
    briefEl.innerHTML = renderMarkdown(md);
    // Update copy/download
    const safeName = fixture && fixture.teams
      ? `${slug(fixture.teams.home && fixture.teams.home.name)}-vs-${slug(fixture.teams.away && fixture.teams.away.name)}`
      : `fixture-${fixture && fixture.id ? fixture.id : "brief"}`;
    const filename = `pre-game-brief--${safeName}.md`;
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown;charset=utf-8" }));
    const prev = downloadBtn.dataset.objectUrl;
    if (prev) { try { URL.revokeObjectURL(prev); } catch (_) {} }
    downloadBtn.href = url;
    downloadBtn.setAttribute("download", filename);
    downloadBtn.dataset.objectUrl = url;
  }

  function slug(s) {
    return String(s || "team").toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40) || "team";
  }

  // ---------- Copy ----------
  function copyMarkdown() {
    const md = state.lastMarkdown || "";
    if (!md) {
      setStatus("Nothing to copy yet — generate a brief first.", "warn");
      return;
    }
    const done = (ok) => {
      const original = "Copy markdown";
      copyBtn.textContent = ok ? "Copied ✓" : "Copy failed";
      setStatus(ok ? "Markdown copied to clipboard." : "Copy to clipboard failed — try Download instead.", ok ? "ok" : "error");
      setTimeout(() => { copyBtn.textContent = original; }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(md).then(() => done(true), () => fallbackCopy(md, done));
    } else {
      fallbackCopy(md, done);
    }
  }
  function fallbackCopy(text, cb) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "absolute";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      cb(!!ok);
    } catch (_) { cb(false); }
  }

  // ---------- Seed sample ----------
  // Rendered on first paint so the customer SEES the feature working
  // even before they wire an API-Football key into the vault.
  const SAMPLE = (function () {
    const teamHome = { id: 33, name: "Manchester United" };
    const teamAway = { id: 50, name: "Manchester City" };
    const fixture = {
      id: 868247,
      date: "2026-08-31T15:30:00+00:00",
      status: { long: "Not Started", short: "NS" },
      venue: { name: "Old Trafford", city: "Manchester" },
      referee: "M. Oliver",
      league: { name: "Premier League", round: "Regular Season - 4", season: 2026 },
      teams: { home: teamHome, away: teamAway },
      goals: { home: null, away: null },
      lineups: [],
    };
    const homeForm = [
      { fixture_id: 1, date: "2026-08-24", league: "Premier League", home: { id: 40, name: "Liverpool" },       away: { id: 33, name: "Manchester United" }, goals: { home: 3, away: 0 } },
      { fixture_id: 2, date: "2026-08-17", league: "Premier League", home: { id: 33, name: "Manchester United" }, away: { id: 51, name: "Brighton" },          goals: { home: 1, away: 1 } },
      { fixture_id: 3, date: "2026-08-10", league: "Premier League", home: { id: 49, name: "Chelsea" },           away: { id: 33, name: "Manchester United" }, goals: { home: 0, away: 2 } },
      { fixture_id: 4, date: "2026-08-03", league: "Friendly",       home: { id: 33, name: "Manchester United" }, away: { id: 47, name: "Tottenham" },          goals: { home: 2, away: 2 } },
      { fixture_id: 5, date: "2026-07-27", league: "Friendly",       home: { id: 39, name: "Wolves" },            away: { id: 33, name: "Manchester United" }, goals: { home: 1, away: 0 } },
    ];
    const awayForm = [
      { fixture_id: 6,  date: "2026-08-25", league: "Premier League", home: { id: 50, name: "Manchester City" }, away: { id: 66, name: "Aston Villa" },      goals: { home: 4, away: 1 } },
      { fixture_id: 7,  date: "2026-08-18", league: "Premier League", home: { id: 35, name: "Bournemouth" },     away: { id: 50, name: "Manchester City" }, goals: { home: 0, away: 3 } },
      { fixture_id: 8,  date: "2026-08-11", league: "Community Shield", home: { id: 50, name: "Manchester City" }, away: { id: 42, name: "Arsenal" },        goals: { home: 1, away: 1 } },
      { fixture_id: 9,  date: "2026-08-04", league: "Friendly",       home: { id: 47, name: "Tottenham" },         away: { id: 50, name: "Manchester City" }, goals: { home: 2, away: 2 } },
      { fixture_id: 10, date: "2026-07-28", league: "Friendly",       home: { id: 50, name: "Manchester City" }, away: { id: 86, name: "Real Madrid" },     goals: { home: 3, away: 1 } },
    ];
    const h2h = [
      { fixture_id: 90, date: "2026-04-06", league: "Premier League", home: { id: 50, name: "Manchester City" }, away: { id: 33, name: "Manchester United" }, goals: { home: 3, away: 1 } },
      { fixture_id: 91, date: "2025-12-15", league: "Premier League", home: { id: 33, name: "Manchester United" }, away: { id: 50, name: "Manchester City" }, goals: { home: 0, away: 0 } },
      { fixture_id: 92, date: "2025-05-25", league: "FA Cup",         home: { id: 50, name: "Manchester City" }, away: { id: 33, name: "Manchester United" }, goals: { home: 1, away: 2 } },
      { fixture_id: 93, date: "2025-03-03", league: "Premier League", home: { id: 33, name: "Manchester United" }, away: { id: 50, name: "Manchester City" }, goals: { home: 1, away: 3 } },
      { fixture_id: 94, date: "2024-10-29", league: "Premier League", home: { id: 50, name: "Manchester City" }, away: { id: 33, name: "Manchester United" }, goals: { home: 6, away: 3 } },
    ];
    const lineups = []; // intentionally empty — exercise the "Lineup not yet confirmed" placeholder
    return { fixture, homeForm, awayForm, h2h, lineups };
  })();

  function paintSample() {
    const md = composeBrief(SAMPLE);
    paintBrief(md, SAMPLE.fixture);
    resetSections("idle");
    setSection("fixture",   "ok",   "sample");
    setSection("form-home", "ok",   "sample");
    setSection("form-away", "ok",   "sample");
    setSection("h2h",       "ok",   "sample");
    setSection("lineups",   "warn", "not yet confirmed");
  }

  // ---------- Wire-up ----------
  function init() {
    // Initial sample so the page demonstrates the feature on first load.
    paintSample();

    // Defensive: surface the deploy seam in the status line.
    if (!window.MACHINA_DEPLOY || !window.MACHINA_DEPLOY.proxyUrl) {
      setStatus(
        "Sample brief shown. Live generation activates when this page is opened through a Factory deploy " +
        "(the deploy injects window.MACHINA_DEPLOY).",
        "warn"
      );
    }

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const v = (fxInput.value || "").trim();
      if (!v) { setStatus("Enter a fixture id to generate a brief.", "warn"); fxInput.focus(); return; }
      if (!/^\d+$/.test(v)) { setStatus("Fixture id must be numeric (API-Football ids are integers).", "warn"); fxInput.focus(); return; }
      generate(v);
    });

    // Example chips
    document.querySelectorAll(".chip[data-id]").forEach(btn => {
      btn.addEventListener("click", () => {
        fxInput.value = btn.dataset.id;
        form.dispatchEvent(new Event("submit", { cancelable: true }));
      });
    });

    copyBtn.addEventListener("click", copyMarkdown);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
