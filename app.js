// Pitchprint — social graphic generator.
// Wires controls, calls the project's social-graphic-* workflows via the
// Factory proxy, and renders the result onto a 1080-resolution canvas.

import { TEAMS, COMPETITIONS, leagueForTeam } from "./teams.js";

// ---------- DOM ----------
const $ = (id) => document.getElementById(id);
const els = {
  teamInput:    $("team-input"),
  teamList:     $("team-list"),
  teamChip:     $("team-chip"),
  teamChipName: $("team-chip-name"),
  teamChipDot:  $("team-chip-dot"),
  teamChipClr:  $("team-chip-clear"),
  prompt:       $("prompt-input"),
  quickChips:   $("quick-chips"),
  dropzone:     $("dropzone"),
  refInput:     $("ref-input"),
  dzInner:      $("dropzone-inner"),
  dzPreview:    $("dropzone-preview"),
  dzClear:      $("dropzone-clear"),
  paletteStrip: $("palette-strip"),
  ratioGroup:   document.querySelector(".ratio-group"),
  previewFrame: $("preview-frame"),
  canvas:       $("canvas"),
  status:       $("status-line"),
  cta:          $("generate-btn"),
  download:     $("download-btn"),
  metaLine:     $("meta-line"),
};

// ---------- State ----------
const state = {
  team: null,           // TEAM object
  ratio: "square",      // square | landscape | vertical
  refPalette: null,     // [hex,hex,hex,hex,hex] or null
  refImage: null,       // <img> or null
  busy: false,
};

const RATIOS = {
  square:    { w: 1080, h: 1080 },
  landscape: { w: 1920, h: 1080 },
  vertical:  { w: 1080, h: 1920 },
};

// ---------- Proxy bootstrap ----------
function getProxyBase() {
  const d = window.MACHINA_DEPLOY;
  if (d && d.proxyUrl) return d.proxyUrl;
  // Defensive local-dev fallback. The page still renders; live calls will
  // surface a clear empty state instead of throwing.
  return null;
}

async function callWorkflow(name, inputs) {
  const base = getProxyBase();
  if (!base) {
    throw new Error(
      "No proxy URL on this page — open via the Factory-deployed Netlify URL " +
      "so window.MACHINA_DEPLOY is injected."
    );
  }
  const res = await fetch(`${base}/workflow/execute/${name}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(inputs),
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`Workflow ${name} failed (${res.status}): ${txt.slice(0, 200)}`);
  }
  const json = await res.json();
  // Client API shape: { data: { outputs: {...} }, status, meta }
  return (json && json.data && json.data.outputs) || {};
}

// ---------- Typeahead ----------
function normalize(s) { return (s || "").toLowerCase().normalize("NFKD").replace(/[^\w\s]/g, " "); }

function renderTeamOptions(query) {
  const q = normalize(query);
  const matches = (q
    ? TEAMS.filter(t => {
        const hay = normalize(`${t.name} ${t.short} ${t.league} ${t.abbr}`);
        return hay.includes(q);
      })
    : TEAMS).slice(0, 24);

  els.teamList.innerHTML = matches.map((t, i) => `
    <li class="combo__option" role="option" data-id="${t.id}" id="opt-${i}" data-index="${i}">
      <span class="combo__option-dot" style="background:${t.primary}"></span>
      <span class="combo__option-name">${t.name}</span>
      <span class="combo__option-meta">${t.country} · ${t.league}</span>
    </li>
  `).join("");
  els.teamList.hidden = matches.length === 0;
  els.teamInput.setAttribute("aria-expanded", matches.length > 0 ? "true" : "false");

  // wire click
  els.teamList.querySelectorAll(".combo__option").forEach(li => {
    li.addEventListener("mousedown", (e) => {
      // mousedown (not click) so it fires before the input's blur
      e.preventDefault();
      pickTeam(li.getAttribute("data-id"));
    });
  });
}

function pickTeam(id) {
  const t = TEAMS.find(x => x.id === id);
  if (!t) return;
  state.team = t;
  els.teamInput.value = "";
  els.teamInput.hidden = true;
  els.teamChip.hidden = false;
  els.teamChipName.textContent = t.name;
  els.teamChipDot.style.background = t.primary;
  els.teamList.hidden = true;
  setStatus(`Locked in: ${t.name}. Now type a headline →`, "ok");
}

function clearTeam() {
  state.team = null;
  els.teamChip.hidden = true;
  els.teamInput.hidden = false;
  els.teamInput.value = "";
  els.teamInput.focus();
  setStatus("Pick a team, type what you want, hit generate.");
}

els.teamInput.addEventListener("input", (e) => renderTeamOptions(e.target.value));
els.teamInput.addEventListener("focus", () => renderTeamOptions(els.teamInput.value));
els.teamInput.addEventListener("blur",  () => setTimeout(() => { els.teamList.hidden = true; }, 120));
els.teamChipClr.addEventListener("click", clearTeam);

// Keyboard navigation in the listbox
let activeOption = -1;
els.teamInput.addEventListener("keydown", (e) => {
  const opts = els.teamList.querySelectorAll(".combo__option");
  if (!opts.length) return;
  if (e.key === "ArrowDown") {
    e.preventDefault();
    activeOption = Math.min(opts.length - 1, activeOption + 1);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    activeOption = Math.max(0, activeOption - 1);
  } else if (e.key === "Enter") {
    if (activeOption >= 0) {
      e.preventDefault();
      pickTeam(opts[activeOption].getAttribute("data-id"));
      activeOption = -1;
      return;
    }
  } else { return; }
  opts.forEach((o, i) => o.setAttribute("aria-selected", i === activeOption ? "true" : "false"));
  if (activeOption >= 0) opts[activeOption].scrollIntoView({ block: "nearest" });
});

// ---------- Quick chips ----------
els.quickChips.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-quick]");
  if (!btn) return;
  els.prompt.value = btn.getAttribute("data-quick");
  els.prompt.focus();
});

// ---------- Ratio toggle ----------
els.ratioGroup.addEventListener("click", (e) => {
  const btn = e.target.closest(".ratio");
  if (!btn) return;
  state.ratio = btn.getAttribute("data-ratio");
  els.ratioGroup.querySelectorAll(".ratio").forEach(b => {
    const isActive = b === btn;
    b.classList.toggle("is-active", isActive);
    b.setAttribute("aria-checked", isActive ? "true" : "false");
  });
  els.previewFrame.setAttribute("data-ratio", state.ratio);
  const { w, h } = RATIOS[state.ratio];
  els.canvas.width = w; els.canvas.height = h;
  // Re-render last result if we have one.
  if (lastRender) lastRender();
});

// ---------- Dropzone + palette extraction ----------
let currentRefUrl = null;
function revokeRefUrl() {
  if (currentRefUrl) { URL.revokeObjectURL(currentRefUrl); currentRefUrl = null; }
}
function setupDropzone() {
  const onFiles = (files) => {
    const file = files && files[0];
    if (!file || !file.type.startsWith("image/")) return;
    revokeRefUrl(); // free the previous blob before allocating a new one
    const url = URL.createObjectURL(file);
    currentRefUrl = url;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      state.refImage = img;
      state.refPalette = extractPalette(img, 5);
      els.dzPreview.src = url;
      els.dzPreview.hidden = false;
      els.dzInner.hidden = true;
      els.dzClear.hidden = false;
      renderPaletteStrip(state.refPalette);
    };
    img.onerror = () => {
      revokeRefUrl();
      setStatus("Couldn't read that image — try a different file.", "error");
    };
    img.src = url;
  };

  els.refInput.addEventListener("change", (e) => onFiles(e.target.files));
  ["dragenter", "dragover"].forEach(ev => els.dropzone.addEventListener(ev, (e) => {
    e.preventDefault(); els.dropzone.classList.add("is-drag");
  }));
  ["dragleave", "drop"].forEach(ev => els.dropzone.addEventListener(ev, (e) => {
    e.preventDefault(); els.dropzone.classList.remove("is-drag");
  }));
  els.dropzone.addEventListener("drop", (e) => onFiles(e.dataTransfer.files));
  els.dzClear.addEventListener("click", (e) => {
    e.preventDefault(); e.stopPropagation();
    revokeRefUrl();
    state.refImage = null; state.refPalette = null;
    els.dzPreview.hidden = true; els.dzPreview.src = "";
    els.dzClear.hidden = true; els.dzInner.hidden = false;
    els.paletteStrip.hidden = true; els.paletteStrip.innerHTML = "";
    els.refInput.value = "";
  });
}

function renderPaletteStrip(palette) {
  if (!palette || !palette.length) { els.paletteStrip.hidden = true; return; }
  els.paletteStrip.innerHTML = palette.map(c => `<div style="background:${c}"></div>`).join("");
  els.paletteStrip.hidden = false;
}

// k-means-lite palette extraction. Buckets RGB values into a 4x4x4 cube,
// returns the 5 highest-population non-near-grey buckets.
function extractPalette(img, k = 5) {
  const W = 80, H = 80;
  const off = document.createElement("canvas");
  off.width = W; off.height = H;
  const ctx = off.getContext("2d");
  ctx.drawImage(img, 0, 0, W, H);
  const data = ctx.getImageData(0, 0, W, H).data;
  const buckets = new Map();
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i], g = data[i+1], b = data[i+2], a = data[i+3];
    if (a < 200) continue;
    // skip near-white / near-black so the palette is the *color* not the bg
    const mx = Math.max(r,g,b), mn = Math.min(r,g,b);
    if (mx > 240 && mn > 230) continue;
    if (mx < 30) continue;
    const key = `${r >> 5}-${g >> 5}-${b >> 5}`;
    const cur = buckets.get(key) || { r: 0, g: 0, b: 0, n: 0 };
    cur.r += r; cur.g += g; cur.b += b; cur.n += 1;
    buckets.set(key, cur);
  }
  const top = [...buckets.values()]
    .sort((a, b) => b.n - a.n)
    .slice(0, k)
    .map(c => rgbToHex(c.r / c.n, c.g / c.n, c.b / c.n));
  return top.length ? top : null;
}
function rgbToHex(r, g, b) {
  const h = (v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0");
  return `#${h(r)}${h(g)}${h(b)}`;
}

// ---------- Intent parsing ----------
// Parses the headline into { kind, opponent?, n? }.
// kind ∈ "schedule" | "results" | "h2h" | "scorers"
function parseIntent(text) {
  const t = (text || "").trim().toLowerCase();
  if (!t) return { kind: "schedule", n: 5 };

  const n = (() => {
    const m = t.match(/\b(\d{1,2})\b/);
    return m ? Math.max(1, Math.min(10, parseInt(m[1], 10))) : 5;
  })();

  // head-to-head
  if (/(\bh2h\b|head.?to.?head|versus|\bvs\.?\b|against)/.test(t)) {
    // try to extract opponent name (last quoted thing or after the marker)
    const after = t.replace(/.*?(h2h|head.?to.?head|versus|vs\.?|against)\s*/i, "");
    return { kind: "h2h", opponent: after.trim(), n };
  }
  // top scorers / leaders
  if (/(scorers?|leaders?|top.?goal|golden boot|assists?)/.test(t)) {
    return { kind: "scorers", n };
  }
  // results / last / recent / past
  if (/(last|recent|past|results?|form)/.test(t)) {
    return { kind: "results", n };
  }
  // schedule / next / upcoming / fixtures
  if (/(next|upcoming|fixtures?|schedule|coming)/.test(t)) {
    return { kind: "schedule", n };
  }
  // default — interpret unknown prompts as "next 5"
  return { kind: "schedule", n };
}

function findOpponent(name) {
  const q = normalize(name);
  if (!q) return null;
  return TEAMS.find(t =>
    normalize(t.name).includes(q) ||
    normalize(t.short).includes(q) ||
    normalize(t.abbr) === q
  ) || null;
}

// ---------- Generate ----------
let lastRender = null;

function setStatus(msg, kind = "") {
  els.status.textContent = msg;
  els.status.classList.remove("is-error", "is-ok");
  if (kind) els.status.classList.add(`is-${kind}`);
}

function setBusy(b) {
  state.busy = b;
  els.cta.disabled = b;
  els.cta.classList.toggle("is-loading", b);
  els.cta.querySelector(".cta__label").textContent = b ? "Generating" : "Generate graphic";
}

els.cta.addEventListener("click", async () => {
  if (state.busy) return;
  if (!state.team) {
    setStatus("Pick a team first.", "error");
    els.teamInput.focus();
    return;
  }
  const headline = els.prompt.value.trim() || "Next 5 games";
  const intent = parseIntent(headline);

  setBusy(true);
  setStatus(`Fetching ${describeIntent(intent)} for ${state.team.name}…`);

  try {
    const payload = await fetchData(intent, state.team);
    if (!payload || payload.__empty) {
      // Render an empty-state graphic so the user still gets something to download.
      lastRender = () => renderGraphic({
        team: state.team,
        headline,
        intent,
        palette: paletteFor(state.team),
        empty: payload && payload.__emptyReason || `No data available for "${headline}"`,
      });
      lastRender();
      setStatus(payload && payload.__emptyReason || "No data found — showing empty-state graphic.", "error");
    } else {
      lastRender = () => renderGraphic({
        team: state.team,
        headline,
        intent,
        palette: paletteFor(state.team),
        data: payload,
      });
      lastRender();
      setStatus(`Done. ${describeIntent(intent)} → ${state.team.name}.`, "ok");
    }
    els.previewFrame.classList.add("is-ready");
    els.download.disabled = false;
    els.metaLine.textContent = `${state.ratio} · ${RATIOS[state.ratio].w}×${RATIOS[state.ratio].h}`;
  } catch (err) {
    console.error(err);
    setStatus(err.message || "Generation failed.", "error");
  } finally {
    setBusy(false);
  }
});

function describeIntent(i) {
  if (i.kind === "schedule") return `next ${i.n} games`;
  if (i.kind === "results")  return `last ${i.n} results`;
  if (i.kind === "h2h")      return `head-to-head vs ${i.opponent || "—"}`;
  if (i.kind === "scorers")  return "league top scorers";
  return i.kind;
}

function paletteFor(team) {
  // reference image overrides team palette when present
  if (state.refPalette && state.refPalette.length >= 3) {
    return {
      bg:     state.refPalette[0],
      accent: state.refPalette[1] || team.primary,
      ink:    pickContrastInk(state.refPalette[0]),
      muted:  state.refPalette[2] || "#888",
      source: "reference image",
    };
  }
  return {
    bg:     team.primary,
    accent: team.secondary === "#FFFFFF" ? "#FFE000" : team.secondary,
    ink:    pickContrastInk(team.primary),
    muted:  pickContrastInk(team.primary, 0.7),
    source: "team palette",
  };
}

function luminance(hex) {
  const c = hex.replace("#", "");
  const r = parseInt(c.slice(0, 2), 16) / 255;
  const g = parseInt(c.slice(2, 4), 16) / 255;
  const b = parseInt(c.slice(4, 6), 16) / 255;
  const f = (v) => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
function pickContrastInk(hex, fade = 1) {
  const isLight = luminance(hex) > 0.45;
  const base = isLight ? [10, 12, 16] : [248, 246, 240];
  const a = Math.round(255 * fade).toString(16).padStart(2, "0");
  return `#${base.map(v => v.toString(16).padStart(2, "0")).join("")}${fade < 1 ? a : ""}`;
}

// ---------- Data fetching ----------
async function fetchData(intent, team) {
  if (intent.kind === "schedule" || intent.kind === "results") {
    const out = await callWorkflow("social-graphic-team-schedule", { competitor_id: team.id });
    const summaries = out.summaries || [];
    if (!summaries.length) return { __empty: true, __emptyReason: "No matches returned by Sportradar." };

    // Each summary has sport_event.start_time and sport_event_status.status
    const now = Date.now();
    const upcoming = summaries
      .filter(s => s.sport_event_status && s.sport_event_status.status !== "closed" && s.sport_event_status.status !== "ended"
                   || (s.sport_event && new Date(s.sport_event.start_time).getTime() > now))
      .sort((a, b) => new Date(a.sport_event.start_time) - new Date(b.sport_event.start_time));
    const recent = summaries
      .filter(s => s.sport_event_status && (s.sport_event_status.status === "closed" || s.sport_event_status.status === "ended"))
      .sort((a, b) => new Date(b.sport_event.start_time) - new Date(a.sport_event.start_time));

    const matches = (intent.kind === "schedule" ? upcoming : recent).slice(0, intent.n);
    if (!matches.length) {
      const reason = intent.kind === "schedule"
        ? `No upcoming games scheduled for ${team.short}.`
        : `No recent results found for ${team.short}.`;
      return { __empty: true, __emptyReason: reason };
    }
    return { type: intent.kind, matches };
  }

  if (intent.kind === "h2h") {
    const opp = findOpponent(intent.opponent);
    if (!opp) return { __empty: true, __emptyReason: `Opponent "${intent.opponent}" not in catalog. Try a full club name.` };
    if (opp.id === team.id) return { __empty: true, __emptyReason: "H2H needs two different teams." };
    const out = await callWorkflow("social-graphic-head-to-head", {
      competitor_id_a: team.id, competitor_id_b: opp.id,
    });
    const summaries = out.summaries || out.last_meetings || [];
    if (!summaries.length) return { __empty: true, __emptyReason: `No meetings between ${team.short} and ${opp.short}.` };
    return { type: "h2h", opponent: opp, summaries: summaries.slice(0, intent.n) };
  }

  if (intent.kind === "scorers") {
    const comp = leagueForTeam(team.id);
    const out = await callWorkflow("mini-app-top-scorers", { competition_id: comp.id });
    const scorers = (out.top_scorers || []).slice(0, intent.n);
    if (!scorers.length) return { __empty: true, __emptyReason: `No top-scorer data for ${comp.name} yet.` };
    return {
      type: "scorers",
      competition: comp,
      season_name: out.season_name || "",
      scorers,
    };
  }

  return { __empty: true, __emptyReason: "Unsupported intent." };
}

// ---------- Canvas renderer ----------
function renderGraphic({ team, headline, intent, palette, data, empty }) {
  const { w, h } = RATIOS[state.ratio];
  els.canvas.width = w; els.canvas.height = h;
  const ctx = els.canvas.getContext("2d");

  // Background — diagonal split: team color + darker variant
  drawBackground(ctx, w, h, palette);

  // Top bar — date + competition tag
  drawTopBar(ctx, w, h, team, palette, data);

  // Headline block
  const hl = computedHeadline(intent, team, data);
  drawHeadline(ctx, w, h, hl, palette);

  // Main body
  if (empty) {
    drawEmpty(ctx, w, h, empty, palette);
  } else if (data && data.type === "schedule") {
    drawScheduleList(ctx, w, h, data.matches, team, palette, "next");
  } else if (data && data.type === "results") {
    drawScheduleList(ctx, w, h, data.matches, team, palette, "results");
  } else if (data && data.type === "h2h") {
    drawH2H(ctx, w, h, team, data.opponent, data.summaries, palette);
  } else if (data && data.type === "scorers") {
    drawScorers(ctx, w, h, data, team, palette);
  }

  // Footer — team mark + brand
  drawFooter(ctx, w, h, team, palette);
}

function computedHeadline(intent, team, data) {
  if (data && data.type === "schedule")    return { kicker: "Upcoming", main: `Next ${data.matches.length}`, tail: "games" };
  if (data && data.type === "results")     return { kicker: "Form",     main: `Last ${data.matches.length}`, tail: "results" };
  if (data && data.type === "h2h")         return { kicker: "Head-to-head", main: data.opponent.short.toUpperCase(), tail: "rivalry" };
  if (data && data.type === "scorers")     return { kicker: data.competition.name, main: `Top ${data.scorers.length}`, tail: "scorers" };
  return { kicker: intent.kind, main: team.short.toUpperCase(), tail: "" };
}

function drawBackground(ctx, w, h, p) {
  // Two-tone diagonal poster.
  ctx.fillStyle = p.bg;
  ctx.fillRect(0, 0, w, h);

  // Subtle diagonal swath of the accent
  ctx.save();
  ctx.translate(w * 0.5, h * 0.5);
  ctx.rotate(-Math.PI / 9);
  ctx.fillStyle = hexAlpha(p.accent, 0.12);
  ctx.fillRect(-w, -h * 0.18, w * 2, h * 0.36);
  ctx.restore();

  // Vignette
  const g = ctx.createRadialGradient(w * 0.5, h * 0.5, h * 0.2, w * 0.5, h * 0.5, h * 0.9);
  g.addColorStop(0, "rgba(0,0,0,0)");
  g.addColorStop(1, "rgba(0,0,0,0.45)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);

  // Top-left bracket
  ctx.strokeStyle = hexAlpha(p.ink, 0.4);
  ctx.lineWidth = scale(w, 3);
  ctx.beginPath();
  ctx.moveTo(margin(w), margin(h) + scale(w, 60));
  ctx.lineTo(margin(w), margin(h));
  ctx.lineTo(margin(w) + scale(w, 60), margin(h));
  ctx.stroke();
}

function drawTopBar(ctx, w, h, team, p, data) {
  const m = margin(w);
  const top = margin(h);
  ctx.fillStyle = p.ink;
  ctx.font = `${scale(w, 18)}px "Space Grotesk", sans-serif`;
  ctx.textBaseline = "top";

  const ds = new Date();
  const date = ds.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase();

  ctx.fillText(date, m + scale(w, 80), top + scale(w, 4));

  // Right-aligned tag — competition or section
  const tag = data && data.type === "scorers" ? data.competition.name.toUpperCase() : team.league.toUpperCase();
  ctx.textAlign = "right";
  ctx.fillStyle = p.accent;
  ctx.fillRect(w - m - measure(ctx, tag) - scale(w, 24), top, measure(ctx, tag) + scale(w, 20), scale(w, 30));
  ctx.fillStyle = invert(p.accent);
  ctx.fillText(tag, w - m - scale(w, 14), top + scale(w, 4));
  ctx.textAlign = "left";
}

function drawHeadline(ctx, w, h, headline, p) {
  const m = margin(w);
  const top = margin(h) + scale(w, 70);

  ctx.fillStyle = p.ink;
  ctx.textBaseline = "top";

  // Kicker
  ctx.font = `${scale(w, 22)}px "Space Grotesk", sans-serif`;
  ctx.fillStyle = hexAlpha(p.ink, 0.7);
  ctx.fillText(headline.kicker.toUpperCase(), m, top);

  // Main — huge condensed
  ctx.fillStyle = p.ink;
  const mainSize = scale(w, state.ratio === "landscape" ? 130 : 180);
  ctx.font = `${mainSize}px "Bebas Neue", "Archivo Black", sans-serif`;
  ctx.fillText(headline.main, m, top + scale(w, 38));

  // Tail
  if (headline.tail) {
    ctx.font = `${scale(w, 36)}px "Archivo Black", sans-serif`;
    ctx.fillStyle = p.accent;
    ctx.fillText(headline.tail.toUpperCase(), m, top + scale(w, 38) + mainSize + scale(w, 4));
  }
}

function bodyTop(w, h) {
  // Where the data list / cards start
  return margin(h) + scale(w, state.ratio === "landscape" ? 290 : 380);
}

function drawScheduleList(ctx, w, h, matches, team, p, mode) {
  const m = margin(w);
  let y = bodyTop(w, h);
  const rowH = scale(w, state.ratio === "landscape" ? 60 : 80);
  const maxRows = Math.min(matches.length, Math.floor((h - y - margin(h) - scale(w, 80)) / rowH));

  ctx.textBaseline = "middle";

  for (let i = 0; i < maxRows; i++) {
    const M = matches[i];
    const home = (M.sport_event.competitors || []).find(c => c.qualifier === "home") || {};
    const away = (M.sport_event.competitors || []).find(c => c.qualifier === "away") || {};
    const start = new Date(M.sport_event.start_time);
    const dateStr = start.toLocaleDateString("en-GB", { day: "2-digit", month: "short" }).toUpperCase();
    const timeStr = start.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

    // Row separator
    ctx.strokeStyle = hexAlpha(p.ink, 0.18);
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(m, y); ctx.lineTo(w - m, y); ctx.stroke();

    // Date column
    ctx.fillStyle = p.accent;
    ctx.font = `${scale(w, 26)}px "Archivo Black", sans-serif`;
    ctx.fillText(dateStr, m, y + rowH / 2 - scale(w, 8));
    ctx.fillStyle = hexAlpha(p.ink, 0.6);
    ctx.font = `${scale(w, 16)}px "Space Grotesk", sans-serif`;
    ctx.fillText(timeStr, m, y + rowH / 2 + scale(w, 14));

    // Matchup — home (abbr) vs away (abbr)  | full names smaller
    ctx.fillStyle = p.ink;
    ctx.font = `${scale(w, 34)}px "Bebas Neue", "Archivo Black", sans-serif`;
    const match = `${home.abbreviation || home.name?.slice(0,3).toUpperCase() || "?"} vs ${away.abbreviation || away.name?.slice(0,3).toUpperCase() || "?"}`;
    ctx.fillText(match, m + scale(w, 200), y + rowH / 2 - scale(w, 8));
    ctx.font = `${scale(w, 15)}px "Space Grotesk", sans-serif`;
    ctx.fillStyle = hexAlpha(p.ink, 0.65);
    ctx.fillText(`${home.name || "?"} · ${away.name || "?"}`, m + scale(w, 200), y + rowH / 2 + scale(w, 14));

    // Right side — score (results) or competition (schedule)
    ctx.textAlign = "right";
    if (mode === "results" && M.sport_event_status) {
      const s = M.sport_event_status;
      ctx.fillStyle = p.ink;
      ctx.font = `${scale(w, 38)}px "Archivo Black", sans-serif`;
      const score = `${s.home_score ?? 0}–${s.away_score ?? 0}`;
      ctx.fillText(score, w - m, y + rowH / 2);
    } else {
      const comp = M.sport_event_context?.competition?.name || "";
      ctx.fillStyle = hexAlpha(p.ink, 0.7);
      ctx.font = `${scale(w, 16)}px "Space Grotesk", sans-serif`;
      ctx.fillText(comp.toUpperCase(), w - m, y + rowH / 2);
    }
    ctx.textAlign = "left";

    y += rowH;
  }

  // Final separator
  ctx.strokeStyle = hexAlpha(p.ink, 0.18);
  ctx.beginPath(); ctx.moveTo(m, y); ctx.lineTo(w - m, y); ctx.stroke();

  if (matches.length > maxRows) {
    ctx.fillStyle = hexAlpha(p.ink, 0.55);
    ctx.font = `${scale(w, 14)}px "Space Grotesk", sans-serif`;
    ctx.fillText(`+ ${matches.length - maxRows} more`, m, y + scale(w, 18));
  }
}

function drawH2H(ctx, w, h, team, opp, summaries, p) {
  const m = margin(w);
  let y = bodyTop(w, h);

  // Tally: wins per side + draws
  let homeWins = 0, awayWins = 0, draws = 0;
  for (const s of summaries) {
    const st = s.sport_event_status;
    if (!st || (st.status !== "closed" && st.status !== "ended")) continue;
    if (st.match_tie) { draws++; continue; }
    if (st.winner_id === team.id)      homeWins++;
    else if (st.winner_id === opp.id)  awayWins++;
    else draws++;
  }

  // Score panel
  ctx.textBaseline = "middle";
  const colW = (w - 2 * m) / 3;
  ctx.font = `${scale(w, 110)}px "Bebas Neue", "Archivo Black", sans-serif`;
  ctx.textAlign = "center";

  ctx.fillStyle = p.ink;
  ctx.fillText(String(homeWins), m + colW * 0.5, y + scale(w, 60));
  ctx.fillStyle = p.accent;
  ctx.fillText(String(draws),    m + colW * 1.5, y + scale(w, 60));
  ctx.fillStyle = p.ink;
  ctx.fillText(String(awayWins), m + colW * 2.5, y + scale(w, 60));

  ctx.font = `${scale(w, 18)}px "Archivo Black", sans-serif`;
  ctx.fillStyle = hexAlpha(p.ink, 0.7);
  ctx.fillText(team.short.toUpperCase(), m + colW * 0.5, y + scale(w, 140));
  ctx.fillText("DRAW",                   m + colW * 1.5, y + scale(w, 140));
  ctx.fillText(opp.short.toUpperCase(),  m + colW * 2.5, y + scale(w, 140));

  ctx.textAlign = "left";

  // Recent meetings list
  y += scale(w, 200);
  ctx.font = `${scale(w, 16)}px "Archivo Black", sans-serif`;
  ctx.fillStyle = hexAlpha(p.ink, 0.7);
  ctx.fillText("RECENT MEETINGS", m, y);
  y += scale(w, 24);

  const rowH = scale(w, 46);
  const maxRows = Math.min(summaries.length, Math.floor((h - y - margin(h) - scale(w, 80)) / rowH));
  for (let i = 0; i < maxRows; i++) {
    const M = summaries[i];
    const home = (M.sport_event.competitors || []).find(c => c.qualifier === "home") || {};
    const away = (M.sport_event.competitors || []).find(c => c.qualifier === "away") || {};
    const s = M.sport_event_status || {};
    const start = new Date(M.sport_event.start_time);
    const date = start.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "2-digit" }).toUpperCase();

    ctx.strokeStyle = hexAlpha(p.ink, 0.15);
    ctx.beginPath(); ctx.moveTo(m, y); ctx.lineTo(w - m, y); ctx.stroke();

    ctx.fillStyle = hexAlpha(p.ink, 0.7);
    ctx.font = `${scale(w, 14)}px "Space Grotesk", sans-serif`;
    ctx.fillText(date, m, y + rowH / 2);

    ctx.fillStyle = p.ink;
    ctx.font = `${scale(w, 22)}px "Archivo Black", sans-serif`;
    ctx.fillText(`${home.abbreviation || home.name?.slice(0,3) || "?"}  ${s.home_score ?? "-"}  –  ${s.away_score ?? "-"}  ${away.abbreviation || away.name?.slice(0,3) || "?"}`, m + scale(w, 140), y + rowH / 2);

    y += rowH;
  }
}

function drawScorers(ctx, w, h, data, team, p) {
  const m = margin(w);
  let y = bodyTop(w, h);
  ctx.textBaseline = "middle";

  // Season subtitle
  ctx.fillStyle = hexAlpha(p.ink, 0.7);
  ctx.font = `${scale(w, 18)}px "Archivo Black", sans-serif`;
  ctx.fillText(`SEASON ${data.season_name || ""}`.trim(), m, y);
  y += scale(w, 30);

  const rowH = scale(w, state.ratio === "landscape" ? 64 : 84);
  const maxRows = Math.min(data.scorers.length, Math.floor((h - y - margin(h) - scale(w, 80)) / rowH));

  for (let i = 0; i < maxRows; i++) {
    const s = data.scorers[i];
    ctx.strokeStyle = hexAlpha(p.ink, 0.18);
    ctx.beginPath(); ctx.moveTo(m, y); ctx.lineTo(w - m, y); ctx.stroke();

    // Rank
    ctx.fillStyle = p.accent;
    ctx.font = `${scale(w, 60)}px "Bebas Neue", "Archivo Black", sans-serif`;
    ctx.fillText(String(s.rank).padStart(2, "0"), m, y + rowH / 2 - scale(w, 4));

    // Player name + club
    ctx.fillStyle = p.ink;
    ctx.font = `${scale(w, 32)}px "Archivo Black", sans-serif`;
    ctx.fillText(s.player_name, m + scale(w, 130), y + rowH / 2 - scale(w, 12));
    ctx.fillStyle = hexAlpha(p.ink, 0.7);
    ctx.font = `${scale(w, 16)}px "Space Grotesk", sans-serif`;
    ctx.fillText(s.competitor_name, m + scale(w, 130), y + rowH / 2 + scale(w, 16));

    // Goals — right
    ctx.textAlign = "right";
    ctx.fillStyle = p.ink;
    ctx.font = `${scale(w, 52)}px "Archivo Black", sans-serif`;
    ctx.fillText(String(s.goals), w - m, y + rowH / 2 - scale(w, 4));
    ctx.fillStyle = hexAlpha(p.ink, 0.6);
    ctx.font = `${scale(w, 12)}px "Archivo Black", sans-serif`;
    ctx.fillText("GOALS", w - m, y + rowH / 2 + scale(w, 24));
    ctx.textAlign = "left";

    y += rowH;
  }
}

function drawEmpty(ctx, w, h, msg, p) {
  const m = margin(w);
  const y = bodyTop(w, h);
  ctx.textBaseline = "top";
  ctx.fillStyle = hexAlpha(p.ink, 0.85);
  ctx.font = `${scale(w, 28)}px "Archivo Black", sans-serif`;
  wrapText(ctx, msg, m, y, w - 2 * m, scale(w, 38));

  ctx.fillStyle = hexAlpha(p.ink, 0.55);
  ctx.font = `${scale(w, 16)}px "Space Grotesk", sans-serif`;
  ctx.fillText("Try a different headline or pick another team.", m, y + scale(w, 120));
}

function drawFooter(ctx, w, h, team, p) {
  const m = margin(w);
  const y = h - margin(h) - scale(w, 36);

  // Team mark — pill with abbr
  ctx.fillStyle = p.ink;
  ctx.fillRect(m, y, scale(w, 70), scale(w, 36));
  ctx.fillStyle = invert(p.ink);
  ctx.textBaseline = "middle";
  ctx.font = `${scale(w, 22)}px "Archivo Black", sans-serif`;
  ctx.textAlign = "center";
  ctx.fillText(team.abbr, m + scale(w, 35), y + scale(w, 18));
  ctx.textAlign = "left";

  ctx.fillStyle = hexAlpha(p.ink, 0.8);
  ctx.font = `${scale(w, 16)}px "Space Grotesk", sans-serif`;
  ctx.fillText(team.name.toUpperCase(), m + scale(w, 82), y + scale(w, 18));

  // Brand mark right
  ctx.textAlign = "right";
  ctx.fillStyle = hexAlpha(p.ink, 0.7);
  ctx.font = `${scale(w, 13)}px "Space Grotesk", sans-serif`;
  ctx.fillText("PITCHPRINT · DATA: SPORTRADAR", w - m, y + scale(w, 18));
  ctx.textAlign = "left";
}

// ---------- Canvas helpers ----------
function margin(dim) { return Math.round(dim * 0.055); }
function scale(w, px) { return Math.round(px * (w / 1080)); }
function measure(ctx, s) { return ctx.measureText(s).width; }
function hexAlpha(hex, a) {
  if (!hex) return `rgba(0,0,0,${a})`;
  const c = hex.replace("#", "");
  const r = parseInt(c.slice(0,2), 16);
  const g = parseInt(c.slice(2,4), 16);
  const b = parseInt(c.slice(4,6), 16);
  return `rgba(${r},${g},${b},${a})`;
}
function invert(hex) { return luminance(hex) > 0.45 ? "#0a0c10" : "#f8f6f0"; }
function wrapText(ctx, text, x, y, maxW, lineH) {
  const words = text.split(" ");
  let line = "";
  for (let i = 0; i < words.length; i++) {
    const test = line + words[i] + " ";
    if (ctx.measureText(test).width > maxW && line) {
      ctx.fillText(line.trim(), x, y);
      line = words[i] + " ";
      y += lineH;
    } else {
      line = test;
    }
  }
  ctx.fillText(line.trim(), x, y);
}

// ---------- Download ----------
els.download.addEventListener("click", () => {
  if (!state.team) return;
  const a = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 10);
  a.download = `pitchprint-${state.team.short.toLowerCase().replace(/\s+/g, "-")}-${state.ratio}-${stamp}.png`;
  a.href = els.canvas.toDataURL("image/png");
  document.body.appendChild(a);
  a.click();
  a.remove();
});

// ---------- Init ----------
setupDropzone();
renderTeamOptions(""); // keeps the list ready for first focus

// Wait for the brand fonts to finish loading before any render, so the canvas
// uses the real typeface instead of a fallback sans-serif on the first run.
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(() => { /* fonts ready */ });
}
