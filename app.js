/* eslint-disable */
// ─────────────────────────────────────────────────────────────────────────────
// SLATE — sports-data social-graphic studio
//
// Architecture:
//   1. Team picker  → typeahead over the curated catalog in teams.js
//   2. Headline     → free-form text from the user, no parsing assumptions
//   3. Reference    → optional image file → drawn as the canvas background
//   4. Aspect ratio → 1:1 / 16:9 / 9:16 → governs canvas dimensions
//   5. Generate     → fetch live data via the proxy → composeGraphic()
//   6. Download     → canvas.toBlob() → anchor click
//
// Live-data path uses window.MACHINA_DEPLOY.proxyUrl (injected at deploy
// time). The proxy authenticates by the page's Origin header, so we send
// NO bearer token. Body is the workflow inputs at the top level.
//
// When MACHINA_DEPLOY is absent (local file:// preview or non-Factory
// deploy), we still render a seeded preview so the page demonstrates the
// feature instead of showing a broken empty state.
// ─────────────────────────────────────────────────────────────────────────────

import { TEAMS, logoFor } from './teams.js';

// ───────── State ─────────
const state = {
  team: null,
  headline: '',
  refImage: null,         // HTMLImageElement, loaded
  refImageBlobUrl: null,  // tracked for revokeObjectURL()
  ratio: '1:1',
  loading: false,
  lastData: null,
  lastSource: null,
};

const RATIOS = {
  '1:1':  { w: 1080, h: 1080, label: '1080 × 1080 px' },
  '16:9': { w: 1920, h: 1080, label: '1920 × 1080 px' },
  '9:16': { w: 1080, h: 1920, label: '1080 × 1920 px' },
};

// ───────── DOM ─────────
const $ = (id) => document.getElementById(id);
const dom = {
  statusDot:   $('status-dot'),
  statusText:  $('status-text'),
  teamInput:   $('team-input'),
  teamResults: $('team-results'),
  teamHint:    $('team-hint'),
  selTeam:     $('selected-team'),
  selTeamLogo: $('selected-team-logo'),
  selTeamName: $('selected-team-name'),
  selTeamLg:   $('selected-team-league'),
  clearTeam:   $('clear-team'),
  headline:    $('headline'),
  charCount:   $('char-count'),
  dropzone:    $('dropzone'),
  dzEmpty:     $('dropzone-empty'),
  dzPreview:   $('dropzone-preview'),
  refInput:    $('ref-image-input'),
  refPreview:  $('ref-preview'),
  clearRef:    $('clear-ref'),
  ratioBtns:   document.querySelectorAll('.ratio-btn'),
  generate:    $('generate-btn'),
  download:    $('download-btn'),
  liveRegion:  $('live-region'),
  frame:       $('preview-frame'),
  canvas:      $('preview-canvas'),
  previewEmpty:$('preview-empty'),
  previewLoad: $('preview-loading'),
  loadingText: $('loading-text'),
  metaSource:  $('meta-source'),
  metaSize:    $('meta-size'),
};
const ctx = dom.canvas.getContext('2d');

// ───────── Init ─────────
function init() {
  resizeCanvas();
  bindTeamTypeahead();
  bindHeadline();
  bindDropzone();
  bindRatio();
  bindActions();
  updateGenerateState();
  updatePreviewSize();
  setStatus('ready', 'ok');
}

// ───────── Status / live region ─────────
function setStatus(text, kind = 'ok') {
  dom.statusText.textContent = text;
  dom.statusDot.classList.remove('is-busy', 'is-error');
  if (kind === 'busy')  dom.statusDot.classList.add('is-busy');
  if (kind === 'error') dom.statusDot.classList.add('is-error');
}
function setLive(text, kind = '') {
  dom.liveRegion.classList.remove('is-error', 'is-ok');
  if (kind) dom.liveRegion.classList.add(`is-${kind}`);
  dom.liveRegion.textContent = text;
}

// ───────── Team typeahead ─────────
function bindTeamTypeahead() {
  let activeIdx = -1;
  let currentResults = [];

  const render = (q) => {
    const norm = q.trim().toLowerCase();
    if (!norm) {
      currentResults = TEAMS.slice(0, 8);
    } else {
      currentResults = TEAMS.filter((t) =>
        t.name.toLowerCase().includes(norm) ||
        t.league.toLowerCase().includes(norm) ||
        t.abbr.toLowerCase().includes(norm)
      ).slice(0, 12);
    }
    activeIdx = -1;
    if (currentResults.length === 0) {
      dom.teamResults.innerHTML = '<li class="typeahead-empty">No matches. Try a league name or abbreviation.</li>';
    } else {
      dom.teamResults.innerHTML = currentResults
        .map((t, i) => `
          <li class="typeahead-result" role="option" data-idx="${i}">
            <img src="${logoFor(t)}" alt="" onerror="this.style.visibility='hidden'" />
            <div class="typeahead-result-meta">
              <div class="typeahead-result-name">${escapeHtml(t.name)}</div>
              <div class="typeahead-result-league">${escapeHtml(t.league)}</div>
            </div>
          </li>
        `)
        .join('');
    }
    dom.teamResults.hidden = false;
    dom.teamInput.setAttribute('aria-expanded', 'true');
  };

  const choose = (idx) => {
    const t = currentResults[idx];
    if (!t) return;
    state.team = t;
    dom.teamInput.value = '';
    dom.selTeam.hidden = false;
    dom.selTeamLogo.src = logoFor(t);
    dom.selTeamLogo.alt = t.name;
    dom.selTeamName.textContent = t.name;
    dom.selTeamLg.textContent = `${t.league} · ${t.abbr}`;
    dom.teamHint.textContent = 'team locked in';
    closeResults();
    updateGenerateState();
  };

  const closeResults = () => {
    dom.teamResults.hidden = true;
    dom.teamInput.setAttribute('aria-expanded', 'false');
    activeIdx = -1;
  };

  dom.teamInput.addEventListener('focus', () => render(dom.teamInput.value));
  dom.teamInput.addEventListener('input', () => render(dom.teamInput.value));
  dom.teamInput.addEventListener('keydown', (e) => {
    if (dom.teamResults.hidden) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIdx = Math.min(activeIdx + 1, currentResults.length - 1);
      paintActive();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIdx = Math.max(activeIdx - 1, 0);
      paintActive();
    } else if (e.key === 'Enter') {
      if (activeIdx >= 0) {
        e.preventDefault();
        choose(activeIdx);
      } else if (currentResults.length === 1) {
        e.preventDefault();
        choose(0);
      }
    } else if (e.key === 'Escape') {
      closeResults();
    }
  });

  const paintActive = () => {
    dom.teamResults.querySelectorAll('.typeahead-result').forEach((el, i) => {
      el.classList.toggle('is-active', i === activeIdx);
      if (i === activeIdx) el.scrollIntoView({ block: 'nearest' });
    });
  };

  dom.teamResults.addEventListener('mousedown', (e) => {
    const li = e.target.closest('.typeahead-result');
    if (!li) return;
    e.preventDefault();
    choose(Number(li.dataset.idx));
  });

  document.addEventListener('click', (e) => {
    if (!dom.teamResults.contains(e.target) && e.target !== dom.teamInput) {
      closeResults();
    }
  });

  dom.clearTeam.addEventListener('click', () => {
    state.team = null;
    dom.selTeam.hidden = true;
    dom.teamHint.textContent = 'type a team or league';
    dom.teamInput.focus();
    updateGenerateState();
  });
}

// ───────── Headline ─────────
function bindHeadline() {
  dom.headline.addEventListener('input', () => {
    state.headline = dom.headline.value;
    dom.charCount.textContent = String(state.headline.length);
    updateGenerateState();
  });
}

// ───────── Dropzone ─────────
function bindDropzone() {
  const handleFile = (file) => {
    if (!file) return;
    if (!/^image\//.test(file.type)) {
      setLive('that file isn’t an image', 'error');
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setLive('image is over 8 MB — try a smaller one', 'error');
      return;
    }
    if (state.refImageBlobUrl) URL.revokeObjectURL(state.refImageBlobUrl);
    const url = URL.createObjectURL(file);
    state.refImageBlobUrl = url;
    const img = new Image();
    img.onload = () => {
      state.refImage = img;
      dom.refPreview.src = url;
      dom.dzEmpty.hidden = true;
      dom.dzPreview.hidden = false;
      setLive('reference loaded — it becomes the banner background', 'ok');
    };
    img.onerror = () => {
      setLive('couldn’t decode that image', 'error');
    };
    img.src = url;
  };

  dom.refInput.addEventListener('change', (e) => {
    handleFile(e.target.files[0]);
  });
  dom.dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dom.dropzone.classList.add('is-drag');
  });
  dom.dropzone.addEventListener('dragleave', () => {
    dom.dropzone.classList.remove('is-drag');
  });
  dom.dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dom.dropzone.classList.remove('is-drag');
    handleFile(e.dataTransfer.files[0]);
  });
  dom.clearRef.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (state.refImageBlobUrl) URL.revokeObjectURL(state.refImageBlobUrl);
    state.refImage = null;
    state.refImageBlobUrl = null;
    dom.refInput.value = '';
    dom.dzPreview.hidden = true;
    dom.dzEmpty.hidden = false;
    setLive('reference cleared');
  });
}

// ───────── Aspect ratio ─────────
function bindRatio() {
  dom.ratioBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      dom.ratioBtns.forEach((b) => {
        b.classList.remove('is-active');
        b.setAttribute('aria-checked', 'false');
      });
      btn.classList.add('is-active');
      btn.setAttribute('aria-checked', 'true');
      state.ratio = btn.dataset.ratio;
      resizeCanvas();
      updatePreviewSize();
      // If we already have data, redraw at the new ratio.
      if (state.lastData) composeGraphic();
    });
  });
}

function resizeCanvas() {
  const { w, h } = RATIOS[state.ratio];
  dom.canvas.width = w;
  dom.canvas.height = h;
}
function updatePreviewSize() {
  dom.frame.setAttribute('data-ratio', state.ratio);
  dom.metaSize.textContent = RATIOS[state.ratio].label;
}

// ───────── Enable/disable Generate ─────────
function updateGenerateState() {
  const ok = !!state.team && state.headline.trim().length > 2;
  dom.generate.disabled = !ok;
  const sub = dom.generate.querySelector('.primary-btn-sub');
  if (!state.team)                       sub.textContent = 'pick a team first';
  else if (state.headline.trim().length < 3) sub.textContent = 'add a headline';
  else                                   sub.textContent = 'live data → graphic';
}

// ───────── Actions ─────────
function bindActions() {
  dom.generate.addEventListener('click', onGenerate);
  dom.download.addEventListener('click', onDownload);
}

async function onGenerate() {
  if (state.loading || !state.team || !state.headline.trim()) return;
  state.loading = true;
  dom.generate.classList.add('is-loading');
  dom.generate.disabled = true;
  dom.download.disabled = true;
  showLoading('Fetching live data…');
  setStatus('fetching', 'busy');
  setLive('');

  // Track final user-facing status separately so the `finally` block can
  // tear down the spinner / button state regardless of how many things
  // throw along the way. Previously: both `try` AND `catch` could throw
  // inside `composeGraphic()`, leaving the "Composing graphic…" overlay
  // stuck on screen with the page looking frozen.
  let finalKind = 'ok';
  let finalMsg  = '';

  try {
    let data;
    try {
      data = await fetchLiveData(state.team, state.headline);
    } catch (fetchErr) {
      console.error('[slate] fetchLiveData threw:', fetchErr);
      data = { ...seedData(state.team, state.headline), __source: 'sample (live fetch failed)', __usingFallback: true };
      finalKind = 'error';
      finalMsg  = fetchErr.message || 'live data fetch failed — showing sample';
    }

    state.lastData   = data;
    state.lastSource = data.__source;
    dom.metaSource.textContent = `Data source: ${data.__source}`;
    showLoading('Composing graphic…');

    // composeGraphic catches its own draw errors and never rejects, so
    // a single bad draw routine can't strand the spinner. We still wrap
    // it here as a final safety net.
    try {
      await composeGraphic();
      dom.previewEmpty.hidden = true;
      dom.download.disabled = false;
    } catch (composeErr) {
      console.error('[slate] composeGraphic threw:', composeErr);
      finalKind = 'error';
      finalMsg  = composeErr.message || 'graphic composition failed';
    }

    if (finalKind === 'ok') {
      finalMsg = data.__usingFallback
        ? 'live source returned nothing — showing sample data so you can preview the layout'
        : 'graphic ready — hit Download to save';
    }
  } catch (err) {
    // Should be unreachable now (both nested awaits have their own
    // try/catch) but keep as a last-resort safety net.
    console.error('[slate] onGenerate unexpected error:', err);
    finalKind = 'error';
    finalMsg  = err.message || 'unexpected error';
  } finally {
    // ALWAYS tear down loading state, regardless of how many things threw.
    hideLoading();
    state.loading = false;
    dom.generate.classList.remove('is-loading');
    setStatus(finalKind === 'ok' ? 'ready' : 'error', finalKind === 'ok' ? 'ok' : 'error');
    setLive(finalMsg, finalKind);
    updateGenerateState();
  }
}

function showLoading(text) {
  dom.loadingText.textContent = text;
  dom.previewLoad.hidden = false;
}
function hideLoading() {
  dom.previewLoad.hidden = true;
}

function onDownload() {
  if (!state.lastData) return;
  dom.canvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const slug = state.team.name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
    a.href = url;
    a.download = `slate-${slug}-${state.ratio.replace(':', 'x')}.png`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(url);
      a.remove();
    }, 0);
  }, 'image/png', 0.95);
}

// ───────── Live-data fetch ─────────
//
// Strategy:
// - Detect intent words in the headline (schedule / standings / leaders /
//   results / h2h / scoreboard / next / last). Map to the most informative
//   command available on each module.
// - Always fall back to the per-league standings call (which we verified
//   reliably returns rich data with logos + records).
// - If everything fails OR window.MACHINA_DEPLOY is missing (local
//   preview), emit a sample payload so the canvas still demonstrates the
//   feature.
async function fetchLiveData(team, headline) {
  const deploy = window.MACHINA_DEPLOY;
  if (!deploy || !deploy.proxyUrl) {
    return { ...seedData(team, headline), __source: 'sample (no proxy in this preview)' };
  }
  const intent = classifyIntent(headline);
  const calls  = buildCallChain(team, intent);

  for (const call of calls) {
    try {
      const result = await callWorkflow(deploy.proxyUrl, 'sports-skills-call', {
        module:  call.module,
        command: call.command,
        params:  call.params || {},
      });
      // The proxy may either unwrap the workflow outputs into a flat object
      // ({ result, "workflow-status" }) OR return the full Client API
      // envelope ({ data: { data: { outputs: {...} } } }). Handle both —
      // validate every level before access (anti-pattern: blind property
      // chaining → TypeError).
      const outputs = extractOutputs(result);
      if (!outputs) continue;
      const payload = outputs.result;
      const status  = outputs['workflow-status'];
      if (status === 'executed' && payload && Object.keys(payload).length > 0) {
        const shaped = shapeFor(call.intent, payload, team);
        if (shaped && shaped.rows && shaped.rows.length > 0) {
          return {
            ...shaped,
            __source: `${call.module}/${call.command}`,
            __usingFallback: false,
          };
        }
      }
    } catch (e) {
      console.warn('call failed', call, e);
    }
  }

  // Everything empty — give the user something to look at so they
  // understand what the layout will be once the data path is wired.
  return { ...seedData(team, headline), __source: 'sample (no live data for this query)', __usingFallback: true };
}

// Walk the proxy response and find the workflow's `outputs` dict —
// which the platform sometimes returns flat (`{result, "workflow-status"}`)
// and sometimes nested as `data.data.outputs` depending on the proxy
// version. Returns null when neither shape matches.
function extractOutputs(res) {
  if (!res || typeof res !== 'object') return null;
  // Shape A: proxy already unwrapped → outputs are at the top level.
  if ('workflow-status' in res || 'result' in res) return res;
  // Shape B: full Client API envelope.
  if (res.data && res.data.data && res.data.data.outputs) return res.data.data.outputs;
  // Shape C: single-level envelope.
  if (res.data && res.data.outputs) return res.data.outputs;
  return null;
}

async function callWorkflow(proxyUrl, name, inputs) {
  // Proxy auth is by Origin header — NO bearer token.
  // Body is workflow inputs at the top level (NO context-workflow wrapper).
  const res = await fetch(`${proxyUrl}/workflow/execute/${name}`, {
    method:  'POST',
    headers: { 'content-type': 'application/json' },
    body:    JSON.stringify(inputs),
  });
  if (!res.ok) throw new Error(`workflow ${name} → HTTP ${res.status}`);
  return res.json();
}

function classifyIntent(headline) {
  const t = headline.toLowerCase();
  if (/\b(h2h|head[- ]?to[- ]?head|vs\.?|versus)\b/.test(t)) return 'h2h';
  if (/\b(scor(er|ing)|top scorer|leaders?|goals?|points?|assists?)\b/.test(t)) return 'leaders';
  if (/\b(standing|table|rank|placement|playoff|seed|w[-_ ]l record)\b/.test(t)) return 'standings';
  if (/\b(next|upcom|schedul|fixtur|incoming|coming up)\b/.test(t)) return 'schedule';
  if (/\b(last|result|recent|past|previous|recap)\b/.test(t)) return 'results';
  if (/\b(today|tonight|live|scor|game[- ]?day|matchday)\b/.test(t)) return 'scoreboard';
  return 'standings';
}

// Build an ordered list of workflow calls to attempt. Each league has
// slightly different commands; we lean on `get_standings` and
// `get_scoreboard` for the NA leagues (verified to return rich data) and
// `get_daily_schedule` for football (verified, requires no params).
function buildCallChain(team, intent) {
  const m  = team.module;
  const id = team.espnId;
  const chain = [];

  if (m === 'football') {
    if (intent === 'schedule' || intent === 'results' || intent === 'h2h') {
      chain.push({ module: m, command: 'get_team_schedule', params: { team_id: id }, intent });
    }
    chain.push({ module: m, command: 'get_daily_schedule', params: {}, intent: 'scoreboard' });
  } else {
    // NA leagues — ESPN-backed.
    if (intent === 'schedule' || intent === 'results' || intent === 'h2h') {
      chain.push({ module: m, command: 'get_team_schedule', params: { team_id: id }, intent });
    }
    if (intent === 'scoreboard') {
      chain.push({ module: m, command: 'get_scoreboard', params: {}, intent });
    }
    // Standings ALWAYS works and gives us the team's record + position —
    // a useful payload to fall back to.
    chain.push({ module: m, command: 'get_standings', params: {}, intent: 'standings' });
  }

  return chain;
}

// Shape the raw payload into rows the renderer can chew on.
function shapeFor(intent, payload, team) {
  // Football team schedule
  if (payload.events && Array.isArray(payload.events)) {
    const upcoming = payload.events
      .filter((e) => e.status === 'not_started' || e.status === 'STATUS_SCHEDULED')
      .slice(0, 5);
    const recent = payload.events
      .filter((e) => e.status === 'FT' || e.status === 'STATUS_FINAL' || e.status === 'completed')
      .slice(-5);
    const pool = intent === 'results' ? recent : (upcoming.length ? upcoming : recent);
    if (pool.length === 0) return null;
    return {
      kind: 'fixtures',
      rows: pool.map((e) => fixtureRow(e, team)),
    };
  }

  // NA scoreboard
  if (payload.games && Array.isArray(payload.games)) {
    const rows = payload.games.slice(0, 4).map((g) => scoreboardRow(g));
    return { kind: 'scoreboard', rows, season: payload.game_date || '' };
  }

  // Standings (NBA / NFL / MLB / NHL get_standings)
  if (payload.groups && Array.isArray(payload.groups)) {
    const teamRow = findTeamInStandings(payload.groups, team);
    if (teamRow) {
      return {
        kind: 'standings',
        rows: [{
          team:   teamRow.team.name,
          logo:   teamRow.team.logo,
          wins:   teamRow.wins,
          losses: teamRow.losses,
          ties:   teamRow.ties || '',
          winPct: teamRow.win_pct,
          seed:   teamRow.playoff_seed,
          streak: teamRow.streak,
          diff:   teamRow.diff,
          ppg:    teamRow.points_per_game,
          oppg:   teamRow.opp_points_per_game,
          conf:   teamRow.__conf,
        }],
        season: payload.season,
      };
    }
    // Fall back to top 5 of the conference the team is in.
    const all = payload.groups.flatMap((g) =>
      (g.entries || []).map((e) => ({ ...e, __conf: g.conference }))
    ).slice(0, 5);
    return {
      kind: 'standings-top',
      rows: all.map((r) => ({
        team:   r.team.name,
        logo:   r.team.logo,
        wins:   r.wins,
        losses: r.losses,
        winPct: r.win_pct,
        seed:   r.playoff_seed,
      })),
      season: payload.season,
    };
  }

  return null;
}

function findTeamInStandings(groups, team) {
  for (const g of groups) {
    for (const e of (g.entries || [])) {
      if (e.team && (
        e.team.id === team.espnId ||
        e.team.abbreviation === team.abbr ||
        normalizeTeamName(e.team.name) === normalizeTeamName(team.name)
      )) {
        return { ...e, __conf: g.conference };
      }
    }
  }
  return null;
}
function normalizeTeamName(n) {
  return (n || '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

function fixtureRow(e, team) {
  const home = (e.competitors || []).find((c) => c.qualifier === 'home' || c.home_away === 'home') || {};
  const away = (e.competitors || []).find((c) => c.qualifier === 'away' || c.home_away === 'away') || {};
  const date = e.start_time || e.game_time_utc || '';
  return {
    date,
    venue: (e.venue && e.venue.name) || '',
    competition: (e.competition && e.competition.name) || '',
    home: { name: home.team?.short_name || home.team?.name || '', abbr: home.team?.abbreviation || '' },
    away: { name: away.team?.short_name || away.team?.name || '', abbr: away.team?.abbreviation || '' },
    score: { home: home.score, away: away.score },
  };
}
function scoreboardRow(g) {
  const home = (g.competitors || []).find((c) => c.home_away === 'home') || {};
  const away = (g.competitors || []).find((c) => c.home_away === 'away') || {};
  return {
    date:  g.game_time_utc || '',
    venue: g.venue || '',
    home: { name: home.team?.name || '', abbr: home.team?.abbreviation || '', score: home.score },
    away: { name: away.team?.name || '', abbr: away.team?.abbreviation || '', score: away.score },
    status: g.status_text || g.status || '',
  };
}

// Sample data shown when the proxy isn't reachable or every call
// returns empty. Lets the user see what the layout will look like.
function seedData(team, headline) {
  return {
    kind: 'standings',
    rows: [{
      team:   team.name,
      logo:   logoFor(team),
      wins:   '—',
      losses: '—',
      winPct: '—',
      seed:   '—',
      streak: '—',
      diff:   '—',
      ppg:    '—',
      oppg:   '—',
      conf:   team.league,
    }],
    season: '',
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Canvas composer
//
// Every draw step is wrapped in `safeDraw` so that a single buggy routine
// (e.g. an unexpected payload shape feeding the data block) can't strand
// the "Composing graphic…" overlay. The caller (`onGenerate`) clears the
// overlay in `finally`; we cooperate by never re-throwing from here.
// ─────────────────────────────────────────────────────────────────────────────
function safeDraw(name, fn) {
  try {
    fn();
  } catch (err) {
    console.error(`[slate] draw step "${name}" threw:`, err);
  }
}

async function composeGraphic() {
  const { w, h } = RATIOS[state.ratio];
  const team = state.team;
  const data = state.lastData;
  const refImg = state.refImage;

  safeDraw('clear', () => ctx.clearRect(0, 0, w, h));

  // 1) Background: reference image fills the entire canvas (cover fit).
  //    Otherwise — team-color diagonal gradient with subtle noise vignette.
  if (refImg) {
    safeDraw('background:reference', () => {
      drawCover(refImg, 0, 0, w, h);
      // Readability scrim on the bottom so text always lands.
      const grad = ctx.createLinearGradient(0, h * 0.35, 0, h);
      grad.addColorStop(0,    'rgba(0,0,0,0)');
      grad.addColorStop(0.55, 'rgba(0,0,0,0.55)');
      grad.addColorStop(1,    'rgba(0,0,0,0.88)');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
    });
  } else {
    safeDraw('background:team-colors', () => drawTeamBackground(team, w, h));
  }

  safeDraw('brand-strip', () => drawBrandStrip(team, w, h));
  safeDraw('headline',    () => drawHeadline(state.headline, team, w, h, refImg));
  safeDraw('data-block',  () => drawDataBlock(data, team, w, h, refImg));
  safeDraw('footer',      () => drawFooter(w, h));
}

function drawCover(img, x, y, w, h) {
  const ir = img.naturalWidth / img.naturalHeight;
  const tr = w / h;
  let sx = 0, sy = 0, sw = img.naturalWidth, sh = img.naturalHeight;
  if (ir > tr) {
    sw = img.naturalHeight * tr;
    sx = (img.naturalWidth - sw) / 2;
  } else {
    sh = img.naturalWidth / tr;
    sy = (img.naturalHeight - sh) / 2;
  }
  ctx.drawImage(img, sx, sy, sw, sh, x, y, w, h);
}

function drawTeamBackground(team, w, h) {
  const [c1, c2] = team.colors;
  // Diagonal split — a band of color along the bottom-left, the rest darker.
  const grad = ctx.createLinearGradient(0, 0, w, h);
  grad.addColorStop(0,    c1);
  grad.addColorStop(0.55, c1);
  grad.addColorStop(0.55, mix(c1, '#000', 0.35));
  grad.addColorStop(1,    mix(c1, '#000', 0.55));
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  // Decorative band stripe (the c2 accent)
  ctx.fillStyle = c2;
  ctx.save();
  ctx.translate(w * 0.85, 0);
  ctx.rotate(0.18);
  ctx.fillRect(0, -h * 0.2, w * 0.4, h * 1.6);
  ctx.restore();

  // Repeating dot pattern for texture
  ctx.fillStyle = 'rgba(255,255,255,0.05)';
  const dot = Math.max(6, w / 220);
  const step = dot * 4;
  for (let y = 0; y < h; y += step) {
    for (let x = (y / step) % 2 === 0 ? 0 : step / 2; x < w; x += step) {
      ctx.beginPath();
      ctx.arc(x, y, dot / 2, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

function drawBrandStrip(team, w, h) {
  const padX = Math.round(w * 0.045);
  const padY = Math.round(h * 0.045);
  const stripH = Math.round(Math.min(w, h) * 0.075);

  // Yellow brand chip
  ctx.fillStyle = '#ffd60a';
  ctx.fillRect(padX, padY, stripH * 3.4, stripH);
  // Black border
  ctx.strokeStyle = '#0c0c0c';
  ctx.lineWidth = Math.max(2, stripH * 0.06);
  ctx.strokeRect(padX, padY, stripH * 3.4, stripH);
  // SLATE wordmark
  ctx.fillStyle = '#0c0c0c';
  ctx.font = `900 ${Math.round(stripH * 0.55)}px 'Archivo Black', Archivo, sans-serif`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillText('SLATE', padX + stripH * 0.4, padY + stripH * 0.52);

  // League · team-abbr badge (right side of strip)
  const badgeX = padX + stripH * 3.5;
  ctx.fillStyle = 'rgba(255,255,255,0.92)';
  ctx.fillRect(badgeX, padY + stripH * 0.18, stripH * 4.4, stripH * 0.64);
  ctx.fillStyle = '#0c0c0c';
  ctx.font = `700 ${Math.round(stripH * 0.32)}px 'JetBrains Mono', monospace`;
  ctx.fillText(`${team.league.toUpperCase()} · ${team.abbr}`, badgeX + stripH * 0.18, padY + stripH * 0.5);
}

function drawHeadline(text, team, w, h, hasRef) {
  // Position so the headline ALWAYS finishes above the data card (which
  // starts at h * 0.68). We anchor the bottom of the last line at h * 0.64.
  const padX = Math.round(w * 0.06);
  const wrapW = w - padX * 2;
  const headlineBottom = Math.round(h * 0.64);
  // Headline font scales off the SHORTER axis so landscape doesn't
  // produce a tiny banner type and portrait doesn't blow up.
  const baseAxis = Math.min(w, h);
  const maxFont = Math.round(baseAxis * 0.085);
  const minFont = Math.round(baseAxis * 0.045);
  const lines = wrapLines(text.trim().toUpperCase(), wrapW, maxFont, minFont);

  const lineH = lines.fontSize * 0.95;
  const totalH = lineH * lines.list.length;
  const baseY  = headlineBottom - totalH;

  ctx.font = `900 ${lines.fontSize}px 'Archivo Black', Archivo, sans-serif`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';

  // Accent slab above the headline so the eye lands
  const slabH = Math.round(lines.fontSize * 0.18);
  ctx.fillStyle = '#ffd60a';
  ctx.fillRect(padX - 8, baseY - slabH - 12, Math.round(w * 0.18), slabH);

  // Headline lines
  lines.list.forEach((ln, i) => {
    const y = baseY + i * lineH;
    ctx.save();
    if (hasRef) {
      ctx.shadowColor = 'rgba(0,0,0,0.7)';
      ctx.shadowBlur = lines.fontSize * 0.2;
      ctx.shadowOffsetY = 2;
    }
    ctx.fillStyle = '#ffffff';
    ctx.fillText(ln, padX, y);
    ctx.restore();
  });
}

// Greedy word-wrap that auto-shrinks font until the longest line fits.
function wrapLines(text, maxW, startFont, minFont) {
  let font = startFont;
  while (font >= minFont) {
    ctx.font = `900 ${font}px 'Archivo Black', Archivo, sans-serif`;
    const words = text.split(/\s+/);
    const lines = [];
    let cur = '';
    for (const w of words) {
      const test = cur ? `${cur} ${w}` : w;
      if (ctx.measureText(test).width > maxW) {
        if (cur) lines.push(cur);
        cur = w;
      } else {
        cur = test;
      }
    }
    if (cur) lines.push(cur);
    const widest = Math.max(...lines.map((l) => ctx.measureText(l).width));
    if (widest <= maxW && lines.length <= 4) {
      return { list: lines.slice(0, 4), fontSize: font };
    }
    font -= 6;
  }
  return { list: [text], fontSize: minFont };
}

function drawDataBlock(data, team, w, h, hasRef) {
  const padX = Math.round(w * 0.06);
  const blockY = Math.round(h * 0.68);
  const blockH = h - blockY - Math.round(h * 0.08);
  const blockW = w - padX * 2;

  // Card background — always drawn so the layout reads even with no data.
  ctx.fillStyle = hasRef ? 'rgba(255,255,255,0.94)' : 'rgba(255,255,255,0.92)';
  roundRect(padX, blockY, blockW, blockH, 18);
  ctx.fill();
  ctx.strokeStyle = '#0c0c0c';
  ctx.lineWidth = 2;
  roundRect(padX, blockY, blockW, blockH, 18);
  ctx.stroke();

  // Empty payload → explicit empty-state
  if (!data || !data.rows || data.rows.length === 0) {
    drawEmptyCard(team, padX, blockY, blockW, blockH, h, 'No data available for this query.');
    return;
  }

  // Branch on data.kind. If the dispatch falls through (unknown kind →
  // the silent fail the user reported), drop into the explicit
  // empty-state instead of leaving the card blank.
  switch (data.kind) {
    case 'standings':
      // Single-row → big hero stat grid. Multi-row → top-5 list.
      if (data.rows.length === 1) {
        drawStandingsHero(data.rows[0], team, padX, blockY, blockW, blockH, w, h);
      } else {
        drawStandingsTop(data.rows, padX, blockY, blockW, blockH, h);
      }
      break;
    case 'standings-top':
      drawStandingsTop(data.rows, padX, blockY, blockW, blockH, h);
      break;
    case 'fixtures':
      drawFixtures(data.rows, padX, blockY, blockW, blockH, h);
      break;
    case 'scoreboard':
      drawScoreboard(data.rows, padX, blockY, blockW, blockH, h);
      break;
    default:
      // Surface the unknown shape in DevTools so the dev can debug,
      // and render a graceful empty-state instead of a blank card.
      console.warn(`[slate] drawDataBlock: unknown data.kind="${data.kind}" — falling back to empty-state`, data);
      drawEmptyCard(
        team, padX, blockY, blockW, blockH, h,
        `Couldn’t render data of type “${data.kind || 'unknown'}”.`
      );
  }
}

// Shared empty-card content — used for genuinely-empty payloads AND for
// the unknown-kind fallback, so we always show SOMETHING rather than a
// blank white box.
function drawEmptyCard(team, x, y, bw, bh, h, message) {
  ctx.save();
  ctx.fillStyle = '#0c0c0c';
  ctx.font = `900 ${Math.round(h * 0.028)}px 'Archivo Black', Archivo, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText((team?.name || '').toUpperCase(), x + bw / 2, y + bh * 0.34);
  ctx.fillStyle = '#6a6a6a';
  ctx.font = `500 ${Math.round(h * 0.02)}px Archivo, sans-serif`;
  ctx.fillText(message, x + bw / 2, y + bh * 0.6);
  ctx.font = `500 ${Math.round(h * 0.014)}px 'JetBrains Mono', monospace`;
  ctx.fillText('— retry, or rephrase your headline —', x + bw / 2, y + bh * 0.78);
  ctx.restore();
}

function drawStandingsHero(row, team, x, y, bw, bh, w, h) {
  const pad = Math.round(bw * 0.04);
  // Title
  ctx.fillStyle = '#6a6a6a';
  ctx.font = `700 ${Math.round(h * 0.018)}px 'JetBrains Mono', monospace`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText(`${row.conf || team.league} · CURRENT STANDINGS`, x + pad, y + pad);

  // Stat grid — Wins / Losses / Win% / Seed / Streak (and PPG if present)
  const cells = [
    ['WINS',     row.wins],
    ['LOSSES',   row.losses],
    ['WIN %',    row.winPct],
    ['SEED',     row.seed ? `#${row.seed}` : '—'],
    ['STREAK',   row.streak],
  ];
  if (row.ppg)  cells.push(['PPG',  row.ppg]);
  if (row.oppg) cells.push(['OPP PPG', row.oppg]);

  const cols = cells.length <= 5 ? cells.length : 6;
  const cellW = (bw - pad * 2) / cols;
  const cellY = y + pad * 2 + h * 0.025;
  const cellH = bh - (pad * 3) - h * 0.025;

  cells.slice(0, cols).forEach(([label, val], i) => {
    const cx = x + pad + cellW * i;
    // Label
    ctx.fillStyle = '#6a6a6a';
    ctx.font = `700 ${Math.round(h * 0.014)}px 'JetBrains Mono', monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(label, cx + cellW / 2, cellY + 4);
    // Value
    const valStr = String(val ?? '—');
    const valFont = Math.round(h * (valStr.length > 4 ? 0.05 : 0.062));
    ctx.fillStyle = '#0c0c0c';
    ctx.font = `900 ${valFont}px 'Archivo Black', Archivo, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(valStr, cx + cellW / 2, cellY + cellH / 2 + 4);
    // Divider
    if (i > 0) {
      ctx.strokeStyle = '#0c0c0c20';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(cx, cellY + 10);
      ctx.lineTo(cx, cellY + cellH - 10);
      ctx.stroke();
    }
  });
}

function drawStandingsTop(rows, x, y, bw, bh, h) {
  const pad = Math.round(bw * 0.04);
  ctx.fillStyle = '#6a6a6a';
  ctx.font = `700 ${Math.round(h * 0.018)}px 'JetBrains Mono', monospace`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText('CONFERENCE TOP 5', x + pad, y + pad);

  const rowH = (bh - pad * 2.5 - h * 0.025) / Math.min(rows.length, 5);
  const rowY0 = y + pad + h * 0.03;
  rows.slice(0, 5).forEach((r, i) => {
    const ry = rowY0 + i * rowH;
    // Seed
    ctx.fillStyle = i === 0 ? '#ffd60a' : '#f4efe7';
    roundRect(x + pad, ry + 4, rowH - 8, rowH - 8, 6);
    ctx.fill();
    ctx.strokeStyle = '#0c0c0c';
    ctx.lineWidth = 1.5;
    roundRect(x + pad, ry + 4, rowH - 8, rowH - 8, 6);
    ctx.stroke();
    ctx.fillStyle = '#0c0c0c';
    ctx.font = `900 ${Math.round(rowH * 0.5)}px 'Archivo Black', sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(String(r.seed || (i + 1)), x + pad + (rowH - 8) / 2, ry + rowH / 2);
    // Team name
    ctx.fillStyle = '#0c0c0c';
    ctx.font = `700 ${Math.round(rowH * 0.38)}px Archivo, sans-serif`;
    ctx.textAlign = 'left';
    ctx.fillText(r.team, x + pad + rowH + 4, ry + rowH / 2);
    // Record (right)
    ctx.font = `700 ${Math.round(rowH * 0.4)}px 'JetBrains Mono', monospace`;
    ctx.textAlign = 'right';
    ctx.fillText(`${r.wins}-${r.losses}`, x + bw - pad, ry + rowH / 2);
  });
}

function drawFixtures(rows, x, y, bw, bh, h) {
  const pad = Math.round(bw * 0.04);
  ctx.fillStyle = '#6a6a6a';
  ctx.font = `700 ${Math.round(h * 0.018)}px 'JetBrains Mono', monospace`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText('UPCOMING FIXTURES', x + pad, y + pad);

  const list = rows.slice(0, 5);
  const rowH = (bh - pad * 2.5 - h * 0.025) / list.length;
  const rowY0 = y + pad + h * 0.03;
  list.forEach((r, i) => {
    const ry = rowY0 + i * rowH;
    // Date chip
    const dateStr = formatDate(r.date);
    ctx.fillStyle = '#0c0c0c';
    roundRect(x + pad, ry + 4, rowH * 2.4, rowH - 8, 6);
    ctx.fill();
    ctx.fillStyle = '#ffd60a';
    ctx.font = `700 ${Math.round(rowH * 0.3)}px 'JetBrains Mono', monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(dateStr, x + pad + rowH * 1.2, ry + rowH / 2);
    // Match
    ctx.fillStyle = '#0c0c0c';
    ctx.font = `700 ${Math.round(rowH * 0.36)}px Archivo, sans-serif`;
    ctx.textAlign = 'left';
    ctx.fillText(`${r.home.abbr || r.home.name}  vs  ${r.away.abbr || r.away.name}`, x + pad + rowH * 2.6, ry + rowH / 2);
    // Competition (right, faint)
    if (r.competition) {
      ctx.fillStyle = '#6a6a6a';
      ctx.font = `500 ${Math.round(rowH * 0.26)}px 'JetBrains Mono', monospace`;
      ctx.textAlign = 'right';
      ctx.fillText(r.competition.toUpperCase().slice(0, 18), x + bw - pad, ry + rowH / 2);
    }
  });
}

function drawScoreboard(rows, x, y, bw, bh, h) {
  const pad = Math.round(bw * 0.04);
  ctx.fillStyle = '#6a6a6a';
  ctx.font = `700 ${Math.round(h * 0.018)}px 'JetBrains Mono', monospace`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText('SCOREBOARD', x + pad, y + pad);

  const list = rows.slice(0, 3);
  const rowH = (bh - pad * 2.5 - h * 0.025) / list.length;
  const rowY0 = y + pad + h * 0.03;
  list.forEach((r, i) => {
    const ry = rowY0 + i * rowH;
    ctx.fillStyle = '#0c0c0c';
    ctx.font = `900 ${Math.round(rowH * 0.4)}px 'Archivo Black', sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(`${r.home.abbr || r.home.name}`, x + pad, ry + rowH / 2);
    ctx.textAlign = 'center';
    ctx.fillText(`${r.home.score ?? '-'} : ${r.away.score ?? '-'}`, x + bw / 2, ry + rowH / 2);
    ctx.textAlign = 'right';
    ctx.fillText(`${r.away.abbr || r.away.name}`, x + bw - pad, ry + rowH / 2);
    // Status / time
    if (r.status) {
      ctx.fillStyle = '#6a6a6a';
      ctx.font = `500 ${Math.round(rowH * 0.22)}px 'JetBrains Mono', monospace`;
      ctx.textAlign = 'center';
      ctx.fillText(r.status.toUpperCase(), x + bw / 2, ry + rowH - 8);
    }
  });
}

function drawFooter(w, h) {
  const pad = Math.round(w * 0.045);
  ctx.fillStyle = 'rgba(255,255,255,0.65)';
  ctx.font = `500 ${Math.round(h * 0.014)}px 'JetBrains Mono', monospace`;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'bottom';
  ctx.fillText('SLATE · sports-data social graphics', w - pad, h - pad / 2);
}

// ───────── Utils ─────────
function roundRect(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y,     x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x,     y + h, r);
  ctx.arcTo(x,     y + h, x,     y,     r);
  ctx.arcTo(x,     y,     x + w, y,     r);
  ctx.closePath();
}

function mix(hex1, hex2, t) {
  const a = hexToRgb(hex1), b = hexToRgb(hex2);
  const r = Math.round(a.r + (b.r - a.r) * t);
  const g = Math.round(a.g + (b.g - a.g) * t);
  const bl = Math.round(a.b + (b.b - a.b) * t);
  return `rgb(${r},${g},${bl})`;
}
function hexToRgb(hex) {
  const h = hex.replace('#', '');
  const n = h.length === 3
    ? h.split('').map((c) => c + c).join('')
    : h;
  return {
    r: parseInt(n.slice(0, 2), 16),
    g: parseInt(n.slice(2, 4), 16),
    b: parseInt(n.slice(4, 6), 16),
  };
}

function formatDate(iso) {
  if (!iso) return 'TBD';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'TBD';
  const month = d.toLocaleString('en', { month: 'short' }).toUpperCase();
  const day = d.getDate();
  return `${month} ${day}`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

// ───────── Boot ─────────
init();
