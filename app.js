/* ===============================================================
 * Drop — sports graphic studio
 *
 * Flow:
 *   1. team chip → sport module + colors
 *   2. prompt → intent (schedule / results / leaders / standings / h2h)
 *   3. fetch sports-skills-call workflow at runtime
 *   4. (optional) reference image → palette + canvas background
 *   5. (optional) generate AI background via graphic-generator workflow
 *   6. compose Canvas at the chosen ratio
 *   7. download as PNG
 *
 * Defensive non-negotiables:
 *   - every async function: try{} around full body, finally{} cleans spinner
 *   - every catch: console.error + visible status
 *   - every switch on intent.kind: default branch with empty-state render
 *   - cleanup on async useEffect-style listeners (AbortController)
 * =============================================================== */

(function () {
  "use strict";

  /* ── state ──────────────────────────────────────────────── */
  const state = {
    team: null,                 // selected team object (from teams.js)
    prompt: "",
    refImage: null,             // HTMLImageElement of reference
    refPalette: null,           // [hex, hex, hex, hex, hex] extracted from ref
    aspect: { ratio: "1:1", w: 1080, h: 1080 },
    useAiBg: false,
    aiBgUrl: null,              // last generated AI background URL
    lastData: null,             // last successful data fetch
    lastIntent: null,
    loading: false,
    activeFetchController: null,
  };

  /* ── runtime config ─────────────────────────────────────── */
  const RUNTIME = (() => {
    const deploy = window.MACHINA_DEPLOY;
    if (deploy && deploy.proxyUrl) {
      return { proxyUrl: deploy.proxyUrl, mode: "proxy" };
    }
    // local-dev fallback: hit the project pod directly (will CORS-fail; for inspection only)
    return { proxyUrl: null, mode: "offline" };
  })();

  /* ── DOM lookups ────────────────────────────────────────── */
  const $ = (id) => document.getElementById(id);
  const els = {
    apiStatus:   $("api-status"),
    teamInput:   $("team-input"),
    teamResults: $("team-results"),
    teamChip:    $("team-chip"),
    teamChipDot: $("team-chip-dot"),
    teamChipLabel: $("team-chip-label"),
    teamChipMeta: $("team-chip-meta"),
    teamChipClear: $("team-chip-clear"),
    promptInput: $("prompt-input"),
    promptHints: $("prompt-hints"),
    dropzone:    $("dropzone"),
    refFile:     $("ref-file"),
    refUrl:      $("ref-url"),
    dzEmpty:     $("dropzone-empty"),
    dzPreview:   $("dropzone-preview"),
    refImg:      $("ref-img"),
    refPals:     $("ref-pals"),
    refClear:    $("ref-clear"),
    ratios:      document.querySelectorAll(".ratio"),
    aiBgChk:     $("ai-bg"),
    generateBtn: $("generate-btn"),
    downloadBtn: $("download-btn"),
    errorLine:   $("error-line"),
    canvas:      $("canvas"),
    canvasWrap:  $("canvas-wrap"),
    canvasOverlay: $("canvas-overlay"),
    overlayMsg:  $("overlay-msg"),
    previewMeta: $("preview-meta"),
  };

  /* ── status indicator ───────────────────────────────────── */
  function setStatus(kind, text) {
    if (!els.apiStatus) return;
    const dot = els.apiStatus.querySelector(".dot");
    const t = els.apiStatus.querySelector(".status-text");
    if (dot) dot.className = "dot dot-" + kind;
    if (t) t.textContent = text;
  }

  function setError(msg, kind) {
    if (!els.errorLine) return;
    els.errorLine.textContent = msg || "";
    els.errorLine.classList.remove("is-err", "is-ok");
    if (kind === "err") els.errorLine.classList.add("is-err");
    if (kind === "ok")  els.errorLine.classList.add("is-ok");
  }

  function showOverlay(msg) {
    if (!els.canvasOverlay) return;
    els.overlayMsg.textContent = msg || "Working…";
    els.canvasOverlay.hidden = false;
  }
  function hideOverlay() {
    if (!els.canvasOverlay) return;
    els.canvasOverlay.hidden = true;
  }

  /* ── prompt → intent parser ─────────────────────────────── */
  // Maps natural language to a sports-skills command + nice headline.
  function parseIntent(prompt, team) {
    const p = (prompt || "").trim().toLowerCase();
    if (!team) return { kind: "empty" };

    // head-to-head
    const h2hMatch = p.match(/(?:vs|versus|against|head[- ]?to[- ]?head(?:\s+vs)?)\s+(?:the\s+)?([a-z0-9 .'-]+?)(?:\s+this|\s+last|\s+next|\?|$)/i);
    if (h2hMatch) {
      return {
        kind: "h2h",
        opponent: h2hMatch[1].trim(),
        headline: `${team.name} vs ${titleCase(h2hMatch[1].trim())}`,
        kicker: "Head to head",
      };
    }

    // results / last N
    const lastMatch = p.match(/last\s+(\d+)?/);
    if (lastMatch || /\b(results?|past|recap)\b/.test(p)) {
      const n = lastMatch && lastMatch[1] ? parseInt(lastMatch[1], 10) : 5;
      return {
        kind: "results",
        limit: clampLimit(n),
        headline: `Last ${clampLimit(n)} results`,
        kicker: team.name,
      };
    }

    // schedule / next N / upcoming
    const nextMatch = p.match(/next\s+(\d+)?/);
    if (nextMatch || /\b(schedule|upcoming|fixtures?|games?|matches?)\b/.test(p)) {
      const n = nextMatch && nextMatch[1] ? parseInt(nextMatch[1], 10) : 5;
      return {
        kind: "schedule",
        limit: clampLimit(n),
        headline: `Next ${clampLimit(n)} games`,
        kicker: team.name,
      };
    }

    // leaders / scorers
    if (/\b(leaders?|top scorers?|top scorer|leading|stats|standings)\b/.test(p)) {
      if (/standings?|table/.test(p)) {
        return { kind: "standings", headline: `Standings`, kicker: team.sport };
      }
      return { kind: "leaders", headline: prompt.trim() || "Season leaders", kicker: team.name };
    }

    // fallback — treat the whole prompt as headline, fetch latest games
    return {
      kind: "schedule",
      limit: 5,
      headline: prompt.trim() || `Next 5 games`,
      kicker: team.name,
    };
  }

  function clampLimit(n) {
    if (!Number.isFinite(n)) return 5;
    return Math.max(1, Math.min(10, n));
  }
  function titleCase(s) {
    return s.replace(/\w\S*/g, (w) => w.charAt(0).toUpperCase() + w.slice(1));
  }

  /* ── workflow call (via Factory proxy) ──────────────────── */
  async function callWorkflow(name, inputs, signal) {
    if (RUNTIME.mode === "offline") {
      throw new Error("Not deployed via Factory — workflow calls unavailable in offline preview.");
    }
    const url = `${RUNTIME.proxyUrl}/workflow/execute/${encodeURIComponent(name)}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(inputs || {}),
      signal,
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`workflow ${name} failed: HTTP ${res.status} ${txt.slice(0, 200)}`);
    }
    const json = await res.json();
    // Two response shapes we've seen:
    //   { outputs: {...}, ... }                 — direct
    //   { data: { outputs: {...}, ... } }       — wrapped
    const outputs =
      (json && json.outputs) ||
      (json && json.data && json.data.outputs) ||
      (json && json.data && json.data.data && json.data.data.outputs) ||
      {};
    return outputs;
  }

  async function fetchSportsData(intent, team, signal) {
    // dispatch table — keys map to module-specific commands
    const dispatch = {
      schedule: () => callSchedule(team, intent, signal),
      results:  () => callResults(team, intent, signal),
      leaders:  () => callLeaders(team, intent, signal),
      standings:() => callStandings(team, intent, signal),
      h2h:      () => callHeadToHead(team, intent, signal),
      empty:    () => Promise.resolve({ rows: [], note: "Pick a team to get started." }),
    };
    const fn = dispatch[intent.kind] || dispatch.empty;
    return await fn();
  }

  async function callSchedule(team, intent, signal) {
    // football has "get_team_schedule"; others use "get_team_schedule" too via ESPN.
    const params = { team: team.query, limit: intent.limit };
    if (team.competition) params.competition_id = team.competition;
    const out = await callWorkflow(
      "sports-skills-call",
      { module: team.module, command: "get_team_schedule", params },
      signal,
    );
    return normalizeSchedule(out, team, intent.limit);
  }

  async function callResults(team, intent, signal) {
    // Same endpoint — many providers return both played + upcoming; we filter completed.
    const params = { team: team.query, limit: 20 };
    if (team.competition) params.competition_id = team.competition;
    const out = await callWorkflow(
      "sports-skills-call",
      { module: team.module, command: "get_team_schedule", params },
      signal,
    );
    return normalizeResults(out, team, intent.limit);
  }

  async function callLeaders(team, intent, signal) {
    const out = await callWorkflow(
      "sports-skills-call",
      { module: team.module, command: "get_scoreboard", params: {} },
      signal,
    );
    return normalizeLeaders(out, team);
  }

  async function callStandings(team, intent, signal) {
    const params = {};
    if (team.competition) params.competition_id = team.competition;
    if (team.module === "football") params.season = "2025";
    const out = await callWorkflow(
      "sports-skills-call",
      { module: team.module, command: team.module === "football" ? "get_season_standings" : "get_standings", params },
      signal,
    );
    return normalizeStandings(out, team);
  }

  async function callHeadToHead(team, intent, signal) {
    // Best-effort: pull schedule and filter rows that mention the opponent string.
    const params = { team: team.query, limit: 25 };
    if (team.competition) params.competition_id = team.competition;
    const out = await callWorkflow(
      "sports-skills-call",
      { module: team.module, command: "get_team_schedule", params },
      signal,
    );
    return normalizeH2H(out, team, intent.opponent);
  }

  /* ── shape normalizers (defensive against missing data) ── */
  function digOut(out) {
    // workflow returns outputs.result.{games|events|...}
    const r = (out && (out.result || out)) || {};
    return r;
  }

  function normalizeSchedule(out, team, limit) {
    const r = digOut(out);
    const games = r.games || r.events || r.schedule || [];
    const now = Date.now();
    const rows = [];
    for (const g of games) {
      const row = normalizeGameRow(g, team);
      if (!row) continue;
      const dt = row.dateMs;
      if (dt && dt < now - 4 * 60 * 60 * 1000) continue; // skip past
      rows.push(row);
      if (rows.length >= limit) break;
    }
    return { rows, kind: "schedule" };
  }

  function normalizeResults(out, team, limit) {
    const r = digOut(out);
    const games = r.games || r.events || r.schedule || [];
    const now = Date.now();
    const rows = [];
    for (const g of games) {
      const row = normalizeGameRow(g, team);
      if (!row) continue;
      if (row.status !== "closed" && row.status !== "final" && row.status !== "completed" && row.status !== "post" && row.dateMs && row.dateMs > now) continue;
      // include if it has scores
      if (row.score === "—") continue;
      rows.push(row);
      if (rows.length >= limit) break;
    }
    return { rows: rows.reverse(), kind: "results" };
  }

  function normalizeLeaders(out, team) {
    const r = digOut(out);
    const games = r.games || r.events || [];
    // surface leader names from any game involving the team
    const rows = [];
    for (const g of games) {
      const leaders = g.leaders || {};
      ["home", "away"].forEach((side) => {
        const l = leaders[side];
        if (!l || !l.name) return;
        rows.push({
          left: l.name,
          right: `${l.points || 0} pts`,
          sub: `${l.assists || 0} ast · ${l.rebounds || 0} reb`,
        });
      });
      if (rows.length >= 5) break;
    }
    return { rows, kind: "leaders" };
  }

  function normalizeStandings(out, team) {
    const r = digOut(out);
    const std = r.standings || r.table || r.entries || [];
    const rows = [];
    for (const entry of std) {
      const name = (entry.team && entry.team.name) || entry.name || entry.team_name || "";
      const rank = entry.rank || entry.position || rows.length + 1;
      const pts  = entry.points ?? entry.pts ?? "";
      const wl   = `${entry.wins ?? entry.w ?? "—"}-${entry.losses ?? entry.l ?? "—"}`;
      if (!name) continue;
      rows.push({ left: `${rank}. ${name}`, right: String(pts || wl), sub: pts ? wl : "" });
      if (rows.length >= 8) break;
    }
    return { rows, kind: "standings" };
  }

  function normalizeH2H(out, team, opponent) {
    const sched = normalizeResults(out, team, 50);
    const opp = (opponent || "").toLowerCase();
    const rows = sched.rows.filter((r) => (r.left + " " + r.right + " " + (r.matchup || "")).toLowerCase().includes(opp));
    return { rows: rows.slice(0, 5), kind: "h2h" };
  }

  function normalizeGameRow(g, team) {
    if (!g) return null;
    // ESPN-shape: competitors[]
    const comps = g.competitors || (g.competitions && g.competitions[0] && g.competitions[0].competitors) || [];
    let home = null, away = null;
    for (const c of comps) {
      const side = c.home_away || c.homeAway || c.qualifier;
      if (side === "home") home = c;
      else if (side === "away") away = c;
    }
    if (!home && !away && comps.length === 2) { home = comps[0]; away = comps[1]; }
    const homeName = home && home.team && (home.team.short_name || home.team.name || home.team.abbreviation) || "";
    const awayName = away && away.team && (away.team.short_name || away.team.name || away.team.abbreviation) || "";
    const homeScore = (home && home.score != null) ? String(home.score) : null;
    const awayScore = (away && away.score != null) ? String(away.score) : null;
    const status = (g.status || g.state || "").toLowerCase();
    const start = g.start_time || g.game_time_utc || g.startDate || g.date || "";
    const dateMs = start ? Date.parse(start) : null;
    const score = (homeScore != null && awayScore != null && (homeScore !== "0" || awayScore !== "0" || /closed|final|post/.test(status)))
      ? `${homeScore} – ${awayScore}`
      : "—";

    return {
      left: awayName ? `${awayName}` : homeName,
      right: homeName ? `@ ${homeName}` : "",
      score,
      status,
      dateMs,
      dateLabel: dateMs ? formatDateLabel(dateMs) : (g.status_detail || ""),
      matchup: `${awayName} @ ${homeName}`,
      venue: (g.venue && (g.venue.name || g.venue.city)) || "",
    };
  }

  function formatDateLabel(ms) {
    try {
      const d = new Date(ms);
      const opts = { month: "short", day: "numeric" };
      return d.toLocaleDateString(undefined, opts).toUpperCase();
    } catch (e) {
      return "";
    }
  }

  /* ── palette extraction from reference image ────────────── */
  function extractPalette(img, k) {
    k = k || 5;
    // downscale to manageable size
    const w = 64, h = 64;
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    const ctx = c.getContext("2d");
    try { ctx.drawImage(img, 0, 0, w, h); }
    catch (e) {
      console.error("palette: drawImage failed (CORS likely):", e);
      return null;
    }
    let data;
    try { data = ctx.getImageData(0, 0, w, h).data; }
    catch (e) {
      console.error("palette: getImageData failed (CORS):", e);
      return null;
    }
    // quantize to a 5-bit color cube
    const bins = new Map();
    for (let i = 0; i < data.length; i += 4) {
      const a = data[i + 3];
      if (a < 128) continue;
      const r = data[i]     >> 4;
      const g = data[i + 1] >> 4;
      const b = data[i + 2] >> 4;
      const key = (r << 8) | (g << 4) | b;
      const cur = bins.get(key);
      if (cur) { cur.r += data[i]; cur.g += data[i+1]; cur.b += data[i+2]; cur.n += 1; }
      else     { bins.set(key, { r: data[i], g: data[i+1], b: data[i+2], n: 1 }); }
    }
    const arr = Array.from(bins.values()).sort((a, b) => b.n - a.n).slice(0, k * 3);
    // dedupe perceptually
    const out = [];
    for (const b of arr) {
      const r = Math.round(b.r / b.n);
      const g = Math.round(b.g / b.n);
      const bl = Math.round(b.b / b.n);
      const hex = rgbToHex(r, g, bl);
      // skip near-white / near-black if we already have one
      const lum = (0.299 * r + 0.587 * g + 0.114 * bl);
      if (lum > 245 && out.some((o) => luminance(o) > 245)) continue;
      if (lum < 12  && out.some((o) => luminance(o) < 12))  continue;
      if (out.some((o) => colorDistance(o, hex) < 30)) continue;
      out.push(hex);
      if (out.length >= k) break;
    }
    while (out.length < k) out.push(out[out.length - 1] || "#cccccc");
    return out;
  }

  function rgbToHex(r, g, b) {
    const h = (n) => n.toString(16).padStart(2, "0");
    return "#" + h(r) + h(g) + h(b);
  }
  function hexToRgb(h) {
    const s = h.replace("#", "");
    return { r: parseInt(s.slice(0,2),16), g: parseInt(s.slice(2,4),16), b: parseInt(s.slice(4,6),16) };
  }
  function luminance(hex) {
    const c = hexToRgb(hex);
    return 0.299*c.r + 0.587*c.g + 0.114*c.b;
  }
  function colorDistance(a, b) {
    const x = hexToRgb(a), y = hexToRgb(b);
    return Math.sqrt((x.r-y.r)**2 + (x.g-y.g)**2 + (x.b-y.b)**2);
  }

  /* ── canvas composition ─────────────────────────────────── */
  function getActivePalette() {
    if (state.refPalette && state.refPalette.length) {
      // sort: darkest first as primary bg, then accent (most saturated)
      const sorted = [...state.refPalette].sort((a, b) => luminance(a) - luminance(b));
      const darkest = sorted[0];
      const lightest = sorted[sorted.length - 1];
      const accent = sorted.find((c) => saturation(c) > 0.4) || sorted[Math.floor(sorted.length / 2)];
      return { primary: darkest, secondary: lightest, accent };
    }
    if (state.team && state.team.colors) {
      const [a, b] = state.team.colors;
      return { primary: a, secondary: b, accent: b };
    }
    return { primary: "#0a0a0a", secondary: "#f4f1eb", accent: "#ff3d00" };
  }

  function saturation(hex) {
    const c = hexToRgb(hex);
    const max = Math.max(c.r, c.g, c.b), min = Math.min(c.r, c.g, c.b);
    if (max === 0) return 0;
    return (max - min) / max;
  }

  function setCanvasDims() {
    els.canvas.width = state.aspect.w;
    els.canvas.height = state.aspect.h;
  }

  async function loadImage(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => resolve(img);
      img.onerror = (e) => reject(new Error("image load failed: " + src));
      img.src = src;
    });
  }

  function drawCard(ctx, opts) {
    const { x, y, w, h, label, value, sub, palette } = opts;
    ctx.fillStyle = palette.secondary;
    ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = palette.primary;
    ctx.lineWidth = Math.max(2, w * 0.012);
    ctx.strokeRect(x, y, w, h);

    // label
    ctx.fillStyle = palette.primary;
    ctx.textBaseline = "top";
    ctx.font = `700 ${Math.round(w * 0.045)}px "JetBrains Mono", monospace`;
    ctx.fillText(label.toUpperCase(), x + w * 0.06, y + h * 0.10);

    // value
    ctx.font = `900 ${Math.round(w * 0.18)}px "Bebas Neue", "Inter", sans-serif`;
    ctx.fillText(value, x + w * 0.06, y + h * 0.28);

    if (sub) {
      ctx.font = `500 ${Math.round(w * 0.05)}px "Inter", sans-serif`;
      ctx.fillStyle = palette.primary + "cc";
      ctx.fillText(sub, x + w * 0.06, y + h * 0.72);
    }
  }

  // wrap text to a max width
  function wrapText(ctx, text, maxWidth) {
    const words = String(text || "").split(/\s+/);
    const lines = [];
    let line = "";
    for (const w of words) {
      const test = line ? line + " " + w : w;
      if (ctx.measureText(test).width > maxWidth && line) {
        lines.push(line);
        line = w;
      } else line = test;
    }
    if (line) lines.push(line);
    return lines;
  }

  async function composeGraphic() {
    setCanvasDims();
    const canvas = els.canvas;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    const palette = getActivePalette();
    const isVertical = H > W;
    const isLandscape = W > H * 1.3;

    // base
    ctx.fillStyle = palette.primary;
    ctx.fillRect(0, 0, W, H);

    // background — either AI image or reference image (dimmed) or gradient
    let bgImg = null;
    if (state.aiBgUrl) {
      try { bgImg = await loadImage(state.aiBgUrl); }
      catch (e) { console.error("aiBg load failed:", e); }
    }
    if (!bgImg && state.refImage) {
      bgImg = state.refImage;
    }
    if (bgImg) {
      // cover-fit
      const iw = bgImg.naturalWidth || bgImg.width;
      const ih = bgImg.naturalHeight || bgImg.height;
      const scale = Math.max(W / iw, H / ih);
      const dw = iw * scale, dh = ih * scale;
      const dx = (W - dw) / 2, dy = (H - dh) / 2;
      ctx.globalAlpha = 0.75;
      try { ctx.drawImage(bgImg, dx, dy, dw, dh); } catch (e) { console.error("bg draw failed:", e); }
      ctx.globalAlpha = 1;
      // darken overlay
      const grad = ctx.createLinearGradient(0, 0, 0, H);
      grad.addColorStop(0, palette.primary + "22");
      grad.addColorStop(0.6, palette.primary + "cc");
      grad.addColorStop(1, palette.primary + "f0");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, W, H);
    } else {
      // editorial gradient mesh
      const grad = ctx.createLinearGradient(0, 0, W, H);
      grad.addColorStop(0, palette.primary);
      grad.addColorStop(1, shadeColor(palette.primary, -20));
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, W, H);

      // diagonal accent stripe
      ctx.save();
      ctx.translate(W * 0.65, 0);
      ctx.rotate(0.35);
      ctx.fillStyle = palette.accent + "33";
      ctx.fillRect(0, -H, W, H * 2.5);
      ctx.restore();

      // dot grid texture
      ctx.fillStyle = palette.secondary + "10";
      const step = Math.round(W * 0.025);
      for (let yy = step; yy < H; yy += step) {
        for (let xx = step; xx < W; xx += step) {
          ctx.beginPath();
          ctx.arc(xx, yy, 1.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }

    // grain layer
    drawGrain(ctx, W, H, 0.05);

    // margin
    const pad = Math.round(Math.min(W, H) * 0.06);

    // top kicker bar
    ctx.fillStyle = palette.accent;
    ctx.fillRect(pad, pad, Math.round(W * 0.12), Math.round(W * 0.012));

    // team / kicker
    const kicker = (state.lastIntent && state.lastIntent.kicker) || (state.team ? state.team.name : "DROP");
    ctx.fillStyle = palette.secondary;
    ctx.font = `700 ${Math.round(W * 0.024)}px "JetBrains Mono", monospace`;
    ctx.textBaseline = "top";
    ctx.fillText(String(kicker).toUpperCase(), pad, pad + Math.round(W * 0.025));

    // big headline
    const headline = (state.lastIntent && state.lastIntent.headline) || state.prompt || "Drop something.";
    ctx.fillStyle = palette.secondary;
    const headlineSize = isVertical ? W * 0.10 : (isLandscape ? W * 0.07 : W * 0.085);
    ctx.font = `900 ${Math.round(headlineSize)}px "Bebas Neue", "Inter", sans-serif`;
    const maxHeadlineW = W - pad * 2;
    const headlineLines = wrapText(ctx, headline, maxHeadlineW);
    let hy = pad + Math.round(W * 0.07);
    const lh = headlineSize * 0.95;
    for (const ln of headlineLines.slice(0, 3)) {
      ctx.fillText(ln, pad, hy);
      hy += lh;
    }
    hy += Math.round(W * 0.02);

    // separator
    ctx.strokeStyle = palette.secondary + "55";
    ctx.lineWidth = Math.max(1, W * 0.003);
    ctx.beginPath();
    ctx.moveTo(pad, hy);
    ctx.lineTo(W - pad, hy);
    ctx.stroke();
    hy += Math.round(W * 0.03);

    // DATA BLOCK — dispatch on intent kind
    const intent = state.lastIntent || { kind: "empty" };
    const data = state.lastData || { rows: [] };
    try {
      drawDataBlock(ctx, { intent, data, palette, pad, x: pad, y: hy, w: W - pad * 2, h: H - hy - pad * 2 });
    } catch (e) {
      console.error("drawDataBlock failed:", e);
      drawEmpty(ctx, { palette, x: pad, y: hy, w: W - pad * 2, msg: "Render failed — " + e.message });
    }

    // bottom footer / attribution
    ctx.fillStyle = palette.secondary + "88";
    ctx.font = `500 ${Math.round(W * 0.017)}px "JetBrains Mono", monospace`;
    ctx.textBaseline = "bottom";
    const footer = [
      state.team ? state.team.name.toUpperCase() : "",
      state.team ? state.team.sport.toUpperCase() : "",
      "DROP.STUDIO",
    ].filter(Boolean).join("  ·  ");
    ctx.fillText(footer, pad, H - pad * 0.5);

    // brand mark (top-right)
    ctx.fillStyle = palette.accent;
    ctx.font = `700 ${Math.round(W * 0.022)}px "JetBrains Mono", monospace`;
    ctx.textAlign = "right";
    ctx.textBaseline = "top";
    ctx.fillText("◤ DROP", W - pad, pad);
    ctx.textAlign = "start";
  }

  function drawDataBlock(ctx, opts) {
    const { intent, data, palette, x, y, w, h } = opts;
    const rows = (data && data.rows) || [];
    if (!rows.length) {
      drawEmpty(ctx, { palette, x, y, w, msg: defaultEmptyMsg(intent) });
      return;
    }

    switch (intent.kind) {
      case "schedule":  drawListGames(ctx, { rows, palette, x, y, w, h, showDate: true }); break;
      case "results":   drawListGames(ctx, { rows, palette, x, y, w, h, showScore: true }); break;
      case "h2h":       drawListGames(ctx, { rows, palette, x, y, w, h, showScore: true }); break;
      case "standings": drawListRanks(ctx, { rows, palette, x, y, w, h }); break;
      case "leaders":   drawListRanks(ctx, { rows, palette, x, y, w, h }); break;
      default:          drawEmpty(ctx, { palette, x, y, w, msg: "No layout for: " + intent.kind });
    }
  }

  function drawListGames(ctx, opts) {
    const { rows, palette, x, y, w, h, showScore, showDate } = opts;
    const maxRows = Math.min(rows.length, Math.floor(h / Math.max(60, w * 0.09)));
    const rowH = Math.min(w * 0.12, h / maxRows);
    let cy = y;
    ctx.textBaseline = "middle";
    for (let i = 0; i < maxRows; i++) {
      const r = rows[i];
      const rcy = cy + rowH / 2;
      // index pill
      ctx.fillStyle = palette.accent;
      ctx.fillRect(x, cy + rowH * 0.18, rowH * 0.6, rowH * 0.64);
      ctx.fillStyle = palette.primary;
      ctx.font = `900 ${Math.round(rowH * 0.45)}px "Bebas Neue", sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText(String(i + 1), x + rowH * 0.3, rcy);
      ctx.textAlign = "start";

      // teams
      const leftX = x + rowH * 0.85;
      ctx.fillStyle = palette.secondary;
      ctx.font = `700 ${Math.round(rowH * 0.4)}px "Inter", sans-serif`;
      const matchup = (r.matchup || (r.left + " " + r.right)).replace(/^@\s*/, "");
      const matchupLine = matchup.length > 32 ? matchup.slice(0, 30) + "…" : matchup;
      ctx.fillText(matchupLine, leftX, rcy - rowH * 0.12);
      // sub
      if (r.dateLabel || r.venue) {
        ctx.font = `500 ${Math.round(rowH * 0.2)}px "JetBrains Mono", monospace`;
        ctx.fillStyle = palette.secondary + "aa";
        ctx.fillText([r.dateLabel, r.venue].filter(Boolean).join(" · "), leftX, rcy + rowH * 0.22);
      }

      // right: score / date
      ctx.font = `900 ${Math.round(rowH * 0.5)}px "Bebas Neue", sans-serif`;
      ctx.fillStyle = palette.accent;
      ctx.textAlign = "right";
      const rightLabel = showScore ? r.score : (showDate ? r.dateLabel : "");
      ctx.fillText(rightLabel || "—", x + w, rcy);
      ctx.textAlign = "start";

      cy += rowH;
      // separator
      ctx.strokeStyle = palette.secondary + "22";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, cy);
      ctx.lineTo(x + w, cy);
      ctx.stroke();
    }
  }

  function drawListRanks(ctx, opts) {
    const { rows, palette, x, y, w, h } = opts;
    const maxRows = Math.min(rows.length, Math.floor(h / Math.max(50, w * 0.07)));
    const rowH = Math.min(w * 0.09, h / maxRows);
    let cy = y;
    ctx.textBaseline = "middle";
    for (let i = 0; i < maxRows; i++) {
      const r = rows[i];
      const rcy = cy + rowH / 2;
      ctx.fillStyle = palette.secondary;
      ctx.font = `700 ${Math.round(rowH * 0.45)}px "Inter", sans-serif`;
      ctx.fillText(r.left || "", x, rcy - (r.sub ? rowH * 0.12 : 0));
      if (r.sub) {
        ctx.font = `500 ${Math.round(rowH * 0.22)}px "JetBrains Mono", monospace`;
        ctx.fillStyle = palette.secondary + "aa";
        ctx.fillText(r.sub, x, rcy + rowH * 0.24);
      }
      ctx.font = `900 ${Math.round(rowH * 0.55)}px "Bebas Neue", sans-serif`;
      ctx.fillStyle = palette.accent;
      ctx.textAlign = "right";
      ctx.fillText(String(r.right || "—"), x + w, rcy);
      ctx.textAlign = "start";
      cy += rowH;
      ctx.strokeStyle = palette.secondary + "22";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, cy); ctx.lineTo(x + w, cy);
      ctx.stroke();
    }
  }

  function drawEmpty(ctx, opts) {
    const { palette, x, y, w, msg } = opts;
    ctx.fillStyle = palette.secondary + "55";
    ctx.font = `600 ${Math.round(w * 0.038)}px "Inter", sans-serif`;
    ctx.textBaseline = "top";
    const lines = wrapText(ctx, msg || "No data.", w);
    let yy = y;
    for (const ln of lines.slice(0, 3)) {
      ctx.fillText(ln, x, yy);
      yy += Math.round(w * 0.05);
    }
  }

  function defaultEmptyMsg(intent) {
    switch (intent && intent.kind) {
      case "schedule":  return "No games scheduled in the next 7 days.";
      case "results":   return "No recent results found.";
      case "h2h":       return "No head-to-head matchups found.";
      case "leaders":   return "No leaders available for this matchup.";
      case "standings": return "No standings data available for this league.";
      default:          return "Type a headline and pick a team to compose.";
    }
  }

  function drawGrain(ctx, W, H, alpha) {
    const c = document.createElement("canvas");
    c.width = 200; c.height = 200;
    const g = c.getContext("2d");
    const img = g.createImageData(200, 200);
    for (let i = 0; i < img.data.length; i += 4) {
      const v = Math.random() * 255;
      img.data[i] = v; img.data[i+1] = v; img.data[i+2] = v; img.data[i+3] = 80;
    }
    g.putImageData(img, 0, 0);
    ctx.save();
    ctx.globalAlpha = alpha;
    const pattern = ctx.createPattern(c, "repeat");
    ctx.fillStyle = pattern;
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
  }

  function shadeColor(hex, percent) {
    const { r, g, b } = hexToRgb(hex);
    const pct = percent / 100;
    const adj = (v) => Math.max(0, Math.min(255, Math.round(v + v * pct)));
    return rgbToHex(adj(r), adj(g), adj(b));
  }

  /* ── team typeahead ─────────────────────────────────────── */
  function renderTeamResults(results, highlightIdx) {
    if (!results.length) { els.teamResults.hidden = true; els.teamResults.innerHTML = ""; return; }
    els.teamResults.innerHTML = results.map((t, i) => `
      <div class="combo-row ${i === highlightIdx ? "active" : ""}" data-id="${t.id}" role="option">
        <span class="combo-swatch" style="background:${t.colors[0]}"></span>
        <span class="combo-name">${escapeHtml(t.name)}</span>
        <span class="combo-meta">${escapeHtml(t.sport)}</span>
      </div>
    `).join("");
    els.teamResults.hidden = false;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }

  function pickTeam(team) {
    state.team = team;
    els.teamInput.value = "";
    els.teamInput.hidden = true;
    els.teamResults.hidden = true;
    els.teamChip.hidden = false;
    els.teamChipDot.style.background = team.colors[0];
    els.teamChipLabel.textContent = team.name;
    els.teamChipMeta.textContent = team.sport;
    updateHints(team);
    composeGraphic().catch((e) => console.error("compose after pickTeam:", e));
  }

  function clearTeam() {
    state.team = null;
    els.teamChip.hidden = true;
    els.teamInput.hidden = false;
    els.teamInput.value = "";
    els.teamInput.focus();
    updateHints(null);
  }

  function updateHints(team) {
    const hints = [];
    if (team) {
      hints.push("next 5 games", "last 5 results");
      if (team.module === "football") hints.push("standings");
      if (team.module === "nba" || team.module === "nfl") hints.push("top scorers");
      hints.push("head-to-head vs ___");
    } else {
      hints.push("next 5 games", "last 10 results", "head-to-head vs Celtics", "top scorers this month");
    }
    els.promptHints.innerHTML = hints.map((h) => `<button class="hint" type="button" data-h="${escapeHtml(h)}">${escapeHtml(h)}</button>`).join("");
  }

  /* ── reference image handling ───────────────────────────── */
  async function loadReferenceFromFile(file) {
    if (!file || !file.type.startsWith("image/")) return;
    const url = URL.createObjectURL(file);
    await loadReferenceFromUrl(url, /*revoke*/ true);
  }

  async function loadReferenceFromUrl(url, revoke) {
    try {
      setError("");
      setStatus("busy", "loading reference…");
      const img = await loadImage(url);
      state.refImage = img;
      state.refPalette = extractPalette(img, 5);
      els.refImg.src = url;
      els.dzEmpty.hidden = true;
      els.dzPreview.hidden = false;
      renderPals();
      setStatus("ok", "reference loaded");
      composeGraphic().catch((e) => console.error("compose after ref:", e));
    } catch (err) {
      console.error("loadReferenceFromUrl failed:", err);
      setError("Couldn't load that image (CORS may be blocking color extraction).", "err");
      setStatus("error", "ref failed");
    } finally {
      if (revoke) { /* keep alive for img element */ }
    }
  }

  function renderPals() {
    if (!state.refPalette) { els.refPals.innerHTML = ""; return; }
    els.refPals.innerHTML = state.refPalette
      .map((c) => `<span class="dz-pal" style="background:${c}" title="${c}"></span>`)
      .join("");
  }

  function clearReference() {
    state.refImage = null;
    state.refPalette = null;
    state.aiBgUrl = null;
    els.dzEmpty.hidden = false;
    els.dzPreview.hidden = true;
    els.refImg.src = "";
    els.refPals.innerHTML = "";
    composeGraphic().catch((e) => console.error("compose after clearRef:", e));
  }

  /* ── main action ────────────────────────────────────────── */
  async function onGenerate() {
    if (state.loading) return;
    state.loading = true;
    els.generateBtn.classList.add("is-loading");
    els.generateBtn.disabled = true;
    els.downloadBtn.disabled = true;
    setStatus("busy", "fetching live data…");
    setError("");
    showOverlay("Fetching live data…");

    // cancel any in-flight
    if (state.activeFetchController) {
      try { state.activeFetchController.abort(); } catch (e) {}
    }
    state.activeFetchController = new AbortController();
    const signal = state.activeFetchController.signal;

    try {
      if (!state.team) {
        throw new Error("Pick a team first.");
      }
      state.prompt = els.promptInput.value.trim();
      const intent = parseIntent(state.prompt, state.team);
      state.lastIntent = intent;

      // 1. fetch sports data
      let data;
      try {
        data = await fetchSportsData(intent, state.team, signal);
      } catch (e) {
        console.error("fetchSportsData failed:", e);
        data = { rows: [], _error: e.message };
        setError("Live data unavailable — composing with empty state. (" + e.message.slice(0, 80) + ")", "err");
      }
      state.lastData = data;

      // 2. optional AI background
      if (state.useAiBg) {
        showOverlay("Generating background…");
        try {
          const palette = getActivePalette();
          const bgPrompt = buildAiBgPrompt(intent, state.team, palette, state.refImage);
          const bgInputs = {
            image_prompt: bgPrompt,
            aspect_ratio: state.aspect.ratio,
          };
          // if we have a reference image as a public URL, send it; refImage from file is blob:, skip
          if (els.refUrl && els.refUrl.value && /^https?:/.test(els.refUrl.value)) {
            bgInputs.reference_image_url = els.refUrl.value;
          }
          const out = await callWorkflow("graphic-generator", bgInputs, signal);
          if (out && out.image_url) {
            state.aiBgUrl = out.image_url;
          } else {
            console.warn("graphic-generator returned empty image_url", out);
            setError("AI background didn't return — falling back to gradient.", "err");
          }
        } catch (e) {
          console.error("AI bg gen failed:", e);
          setError("AI background failed (" + e.message.slice(0, 80) + "). Using gradient.", "err");
        }
      }

      // 3. compose
      showOverlay("Composing graphic…");
      await composeGraphic();

      // 4. update meta
      const dim = state.aspect.w + "×" + state.aspect.h;
      els.previewMeta.textContent = `${state.team.name} · ${intent.kind} · ${dim}`;
      els.downloadBtn.disabled = false;
      setStatus("ok", "ready");
      if (!data._error) setError("Done. " + (data.rows ? data.rows.length : 0) + " rows baked in.", "ok");
    } catch (err) {
      console.error("onGenerate failed:", err);
      setError(err.message || "Something broke.", "err");
      setStatus("error", "error");
      // still try to render an empty-state graphic so the canvas isn't blank
      try {
        await composeGraphic();
      } catch (e2) {
        console.error("fallback compose failed:", e2);
      }
    } finally {
      state.loading = false;
      els.generateBtn.classList.remove("is-loading");
      els.generateBtn.disabled = false;
      hideOverlay();
    }
  }

  function buildAiBgPrompt(intent, team, palette, refImg) {
    const colorHex = team.colors.join(" / ");
    const baseStyle = refImg
      ? "Match the mood, palette, and composition of the reference image. Editorial sports magazine aesthetic. "
      : "Editorial sports magazine background. Atmospheric stadium lighting. Subtle film grain. ";
    return [
      baseStyle,
      "Color palette: " + colorHex + ".",
      "Subject: ambient backdrop for a " + team.sport + " social graphic about " + team.name + ".",
      "Leave the top-left and bottom-right zones empty (negative space) for typography overlay.",
      "No text, no logos, no players' faces. Pure atmospheric composition with depth.",
    ].join(" ");
  }

  function onDownload() {
    if (!state.team) return;
    try {
      const url = els.canvas.toDataURL("image/png");
      const a = document.createElement("a");
      const team = state.team.name.toLowerCase().replace(/\s+/g, "-");
      const stamp = new Date().toISOString().slice(0, 10);
      a.download = `drop-${team}-${state.aspect.ratio.replace(":", "x")}-${stamp}.png`;
      a.href = url;
      a.click();
    } catch (e) {
      console.error("download failed:", e);
      setError("Download failed: " + e.message, "err");
    }
  }

  /* ── event wiring ───────────────────────────────────────── */
  function init() {
    setStatus("idle", RUNTIME.mode === "proxy" ? "ready" : "offline preview");

    let teamHighlight = -1;
    let lastTeamResults = [];

    els.teamInput.addEventListener("input", () => {
      lastTeamResults = window.searchTeams(els.teamInput.value);
      teamHighlight = lastTeamResults.length ? 0 : -1;
      renderTeamResults(lastTeamResults, teamHighlight);
    });
    els.teamInput.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); teamHighlight = Math.min(lastTeamResults.length - 1, teamHighlight + 1); renderTeamResults(lastTeamResults, teamHighlight); }
      if (e.key === "ArrowUp")   { e.preventDefault(); teamHighlight = Math.max(0, teamHighlight - 1); renderTeamResults(lastTeamResults, teamHighlight); }
      if (e.key === "Enter" && teamHighlight >= 0) { e.preventDefault(); pickTeam(lastTeamResults[teamHighlight]); }
      if (e.key === "Escape") { els.teamResults.hidden = true; }
    });
    els.teamInput.addEventListener("blur", () => {
      setTimeout(() => { els.teamResults.hidden = true; }, 180);
    });
    els.teamResults.addEventListener("mousedown", (e) => {
      const row = e.target.closest(".combo-row");
      if (!row) return;
      const id = row.dataset.id;
      const team = window.TEAMS.find((t) => t.id === id);
      if (team) pickTeam(team);
    });
    els.teamChipClear.addEventListener("click", clearTeam);

    els.promptHints.addEventListener("click", (e) => {
      const btn = e.target.closest(".hint");
      if (!btn) return;
      const current = els.promptInput.value.trim();
      const v = btn.dataset.h;
      els.promptInput.value = current ? current + ". " + v : v;
      els.promptInput.focus();
    });

    // dropzone
    els.dropzone.addEventListener("click", (e) => {
      if (e.target === els.refUrl) return;
      els.refFile.click();
    });
    els.dropzone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); els.refFile.click(); }
    });
    els.dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      els.dropzone.classList.add("is-dragging");
    });
    els.dropzone.addEventListener("dragleave", () => els.dropzone.classList.remove("is-dragging"));
    els.dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      els.dropzone.classList.remove("is-dragging");
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) loadReferenceFromFile(f).catch((err) => console.error(err));
    });
    els.refFile.addEventListener("change", () => {
      const f = els.refFile.files && els.refFile.files[0];
      if (f) loadReferenceFromFile(f).catch((err) => console.error(err));
    });
    els.refUrl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const v = els.refUrl.value.trim();
        if (v) loadReferenceFromUrl(v, false).catch((err) => console.error(err));
      }
    });
    els.refUrl.addEventListener("click", (e) => e.stopPropagation());
    els.refClear.addEventListener("click", (e) => { e.stopPropagation(); clearReference(); });

    // ratios
    els.ratios.forEach((btn) => {
      btn.addEventListener("click", () => {
        els.ratios.forEach((b) => { b.classList.remove("active"); b.setAttribute("aria-checked", "false"); });
        btn.classList.add("active"); btn.setAttribute("aria-checked", "true");
        state.aspect = {
          ratio: btn.dataset.ratio,
          w: parseInt(btn.dataset.w, 10),
          h: parseInt(btn.dataset.h, 10),
        };
        composeGraphic().catch((e) => console.error("compose after ratio:", e));
      });
    });

    els.aiBgChk.addEventListener("change", () => {
      state.useAiBg = els.aiBgChk.checked;
    });

    els.generateBtn.addEventListener("click", onGenerate);
    els.downloadBtn.addEventListener("click", onDownload);

    // initial paint
    updateHints(null);
    composeGraphic().catch((e) => console.error("initial compose:", e));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
