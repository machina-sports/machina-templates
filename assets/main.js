// Main controller — wires inputs to the composer.

import { TEAMS, TEAMS_BY_ID, searchTeams } from "./teams.js";
import { parseIntent } from "./intent.js";
import { resolveData } from "./data.js";
import {
  compose, ratioPreset, buildPalette, extractPaletteFromImage,
} from "./composer.js";

// ---------- State ----------
const state = {
  team:        null,           // selected team object
  prompt:      "",
  ratio:       "square",       // "square" | "landscape" | "vertical"
  refImage:    null,           // File
  refPalette:  null,           // [hex, hex, hex]
  lastRender:  null,           // { dataUrl, filename }
};

// ---------- Elements ----------
const $ = (id) => document.getElementById(id);
const els = {
  teamInput:    $("team-input"),
  teamList:     $("team-list"),
  teamHint:     $("team-hint"),
  promptInput:  $("prompt-input"),
  refInput:     $("ref-input"),
  dropzone:     $("dropzone"),
  dzEmpty:      $("dz-empty"),
  dzPreview:    $("dz-preview"),
  dzThumb:      $("dz-thumb"),
  dzPalette:    $("dz-palette"),
  dzClear:      $("dz-clear"),
  ratioButtons: document.querySelectorAll(".ratio"),
  chips:        document.querySelectorAll(".chip"),
  generateBtn:  $("generate-btn"),
  downloadBtn:  $("download-btn"),
  btnLabel:     document.querySelector("#generate-btn .btn-label"),
  btnSpinner:   document.querySelector("#generate-btn .btn-spinner"),
  canvas:       $("canvas"),
  overlay:      $("canvas-overlay"),
  previewMeta:  $("preview-meta"),
  previewTeam:  $("preview-team"),
  previewRatio: $("preview-ratio"),
  previewIntent:$("preview-intent"),
  statusText:   $("status-text"),
  sourceRow:    $("source-row"),
  sourceDot:    $("source-dot"),
  sourceText:   $("source-text"),
};

// ---------- Typeahead ----------
let activeSuggestion = -1;
let currentSuggestions = [];

function renderSuggestions(items) {
  currentSuggestions = items;
  activeSuggestion = -1;
  if (!items.length) {
    els.teamList.hidden = true;
    els.teamList.innerHTML = "";
    return;
  }
  els.teamList.innerHTML = items.map((t, i) => `
    <li class="suggestion" role="option" data-id="${t.id}" data-i="${i}">
      <span class="suggestion-mark" style="background:#${t.secondary};color:#${t.primary};">${t.short}</span>
      <span class="suggestion-meta">
        <span class="suggestion-name">${escapeHtml(t.name)}</span>
        <span class="suggestion-sub">${t.sport} · ${t.league}</span>
      </span>
    </li>
  `).join("");
  els.teamList.hidden = false;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[c]));
}

function setActive(i) {
  const nodes = els.teamList.querySelectorAll(".suggestion");
  nodes.forEach(n => n.classList.remove("is-active"));
  if (i >= 0 && nodes[i]) {
    nodes[i].classList.add("is-active");
    nodes[i].scrollIntoView({ block: "nearest" });
  }
  activeSuggestion = i;
}

function selectTeam(team) {
  state.team = team;
  els.teamInput.value = team.name;
  els.teamHint.textContent = `${team.sport} · ${team.league}`;
  renderSuggestions([]);
  // Auto-generate as soon as a team is picked & we already have a prompt
  maybeAutoGenerate();
}

els.teamInput.addEventListener("focus", () => {
  renderSuggestions(searchTeams(els.teamInput.value));
});
els.teamInput.addEventListener("input", () => {
  state.team = null;
  renderSuggestions(searchTeams(els.teamInput.value));
});
els.teamInput.addEventListener("keydown", (e) => {
  if (els.teamList.hidden) return;
  if (e.key === "ArrowDown") {
    e.preventDefault();
    setActive(Math.min(activeSuggestion + 1, currentSuggestions.length - 1));
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    setActive(Math.max(activeSuggestion - 1, 0));
  } else if (e.key === "Enter") {
    if (activeSuggestion >= 0) {
      e.preventDefault();
      selectTeam(currentSuggestions[activeSuggestion]);
    } else if (currentSuggestions.length === 1) {
      e.preventDefault();
      selectTeam(currentSuggestions[0]);
    }
  } else if (e.key === "Escape") {
    renderSuggestions([]);
  }
});
els.teamList.addEventListener("mousedown", (e) => {
  const li = e.target.closest(".suggestion");
  if (!li) return;
  e.preventDefault();
  const team = TEAMS_BY_ID[li.dataset.id];
  if (team) selectTeam(team);
});
document.addEventListener("click", (e) => {
  if (!els.teamInput.contains(e.target) && !els.teamList.contains(e.target)) {
    renderSuggestions([]);
  }
});

// ---------- Prompt + chips ----------
els.promptInput.addEventListener("input", () => {
  state.prompt = els.promptInput.value;
});
els.chips.forEach(chip => {
  chip.addEventListener("click", () => {
    const v = chip.dataset.preset;
    els.promptInput.value = v;
    state.prompt = v;
    maybeAutoGenerate();
  });
});

// ---------- Dropzone ----------
els.refInput.addEventListener("change", (e) => handleFile(e.target.files?.[0]));
["dragenter", "dragover"].forEach(ev =>
  els.dropzone.addEventListener(ev, (e) => { e.preventDefault(); els.dropzone.classList.add("is-drag"); })
);
["dragleave", "drop"].forEach(ev =>
  els.dropzone.addEventListener(ev, (e) => { e.preventDefault(); els.dropzone.classList.remove("is-drag"); })
);
els.dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer?.files?.[0];
  if (file) handleFile(file);
});
els.dzClear.addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  state.refImage = null;
  state.refPalette = null;
  els.refInput.value = "";
  els.dzPreview.hidden = true;
  els.dzEmpty.hidden = false;
  if (state.team && state.prompt) generate();
});

async function handleFile(file) {
  if (!file || !file.type.startsWith("image/")) return;
  state.refImage = file;
  els.dzThumb.src = URL.createObjectURL(file);
  els.dzEmpty.hidden = true;
  els.dzPreview.hidden = false;
  els.dzPalette.innerHTML = "<span class='dz-swatch' style='background:#222'></span><span class='dz-swatch' style='background:#222'></span><span class='dz-swatch' style='background:#222'></span>";
  try {
    const palette = await extractPaletteFromImage(file);
    state.refPalette = palette;
    els.dzPalette.innerHTML = palette.map(c => `<span class="dz-swatch" style="background:#${c}"></span>`).join("");
    if (state.team && state.prompt) generate();
  } catch {
    state.refPalette = null;
  }
}

// ---------- Ratio toggle ----------
els.ratioButtons.forEach(btn => {
  btn.addEventListener("click", () => {
    els.ratioButtons.forEach(b => {
      b.classList.remove("is-active");
      b.setAttribute("aria-checked", "false");
    });
    btn.classList.add("is-active");
    btn.setAttribute("aria-checked", "true");
    state.ratio = btn.dataset.ratio;
    if (state.team && state.prompt) generate();
  });
});

// ---------- Generation ----------
let isGenerating = false;

function maybeAutoGenerate() {
  // Don't auto-fire unless both team AND prompt are set — avoids
  // generating an empty graphic on first focus.
  if (state.team && state.prompt.trim()) generate();
}

els.generateBtn.addEventListener("click", () => {
  if (!state.team) {
    flashHint(els.teamInput, "Pick a team first");
    return;
  }
  if (!state.prompt.trim()) {
    flashHint(els.promptInput, "Type a headline");
    return;
  }
  generate();
});

function flashHint(el, msg) {
  el.focus();
  el.placeholder = msg;
  setTimeout(() => el.blur(), 1500);
}

async function generate() {
  if (isGenerating) return;
  isGenerating = true;
  setBusy(true);
  els.statusText.textContent = "Composing…";

  try {
    const intent = parseIntent(state.prompt, state.team.id);
    const { rows, source, warning } = await resolveData(state.team, intent);

    const dims = ratioPreset(state.ratio);
    const canvas = els.canvas;
    canvas.width = dims.w;
    canvas.height = dims.h;
    const ctx = canvas.getContext("2d");

    const palette = buildPalette(state.team, state.refPalette);

    compose(ctx, dims, {
      team: state.team,
      intent,
      rows,
      palette,
      headline: state.prompt,
    });

    // Reveal canvas, hide overlay
    canvas.classList.remove("is-empty");
    els.overlay.hidden = true;

    // Generate download blob
    canvas.toBlob((blob) => {
      if (state.lastRender?.url) URL.revokeObjectURL(state.lastRender.url);
      const url = URL.createObjectURL(blob);
      const filename = `${state.team.short.toLowerCase()}-${intent.intent}-${state.ratio}.png`;
      state.lastRender = { url, filename };
      els.downloadBtn.disabled = false;
    }, "image/png");

    // Meta strip under preview
    els.previewMeta.hidden = false;
    els.previewTeam.textContent = state.team.name.toUpperCase();
    els.previewRatio.textContent = dims.label.toUpperCase() + ` (${dims.w}×${dims.h})`;
    els.previewIntent.textContent = intent.intent.toUpperCase();

    // Source row
    els.sourceRow.hidden = false;
    els.sourceDot.className = "source-dot " + (source === "live" ? "is-live" : "is-seed");
    els.sourceText.textContent = warning
      ? warning.toUpperCase()
      : source === "live"
        ? "LIVE DATA · PULLED FROM WORKFLOW"
        : "SAMPLE DATA · WIRE A WORKFLOW TO GO LIVE";

    els.statusText.textContent = source === "live" ? "Live" : "Sample";
  } catch (err) {
    console.error(err);
    els.statusText.textContent = "Error";
  } finally {
    setBusy(false);
    isGenerating = false;
  }
}

function setBusy(busy) {
  els.generateBtn.disabled = busy;
  els.btnLabel.textContent = busy ? "Composing…" : "Generate graphic";
  els.btnSpinner.hidden = !busy;
}

// ---------- Download ----------
els.downloadBtn.addEventListener("click", () => {
  if (!state.lastRender) return;
  const a = document.createElement("a");
  a.href = state.lastRender.url;
  a.download = state.lastRender.filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
});

// ---------- Boot ----------
// Show an initial empty state on first paint
els.canvas.classList.add("is-empty");
els.overlay.hidden = false;
els.previewMeta.hidden = true;

// Drop a friendly first suggestion to seed the typeahead
renderSuggestions([]); // empty until user focuses
