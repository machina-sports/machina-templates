/* parlay-builder · chat-driven · frontend
 *
 * Talks to the customer's Machina pod via the Factory proxy:
 *   POST {proxyUrl}/workflow/schedule/parlay-builder  → { workflow_run_id }
 *   GET  {proxyUrl}/workflow/schedule/{id}            → poll for completion
 *
 * Schedule + poll is required because the workflow runs two gemini-2.5-pro
 * calls back-to-back and routinely takes 60-110s, which would blow past
 * the proxy's sync timeout on /workflow/execute.
 *
 * window.MACHINA_DEPLOY is injected by Factory at deploy time. If it's
 * missing (local preview, etc.) we keep the seeded reply visible and
 * surface a small banner instead of breaking the page.
 */

(function () {
  'use strict';

  const $thread = document.getElementById('thread');
  const $form = document.getElementById('angle-form');
  const $input = document.getElementById('angle-input');
  const $submit = document.getElementById('submit');

  // -----------------------------------------------------------
  // seed render: turn the seeded markdown into clean tickets
  // so the page demonstrates the feature on first paint.
  // -----------------------------------------------------------
  function hydrateSeed() {
    const seedMd = document.getElementById('seed-reply');
    if (seedMd) {
      seedMd.innerHTML = renderMarkdown(seedMd.textContent.trim());
    }
    try {
      const payload = JSON.parse(document.getElementById('seed-payload-json').textContent);
      document.getElementById('seed-tickets').innerHTML = renderTickets(payload.tickets);
      document.getElementById('seed-payload').textContent = JSON.stringify(payload, null, 2);
    } catch (e) {
      console.warn('seed payload parse failed', e);
    }
  }

  // -----------------------------------------------------------
  // chip handlers (presets + followups) — wire any [data-preset]
  // button to drop its text into the textarea and submit.
  // -----------------------------------------------------------
  document.addEventListener('click', (e) => {
    const t = e.target.closest('[data-preset]');
    if (!t) return;
    e.preventDefault();
    $input.value = t.getAttribute('data-preset');
    $input.focus();
    // a small UX nicety: scroll the composer back into view on small screens
    document.querySelector('.composer').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });

  // -----------------------------------------------------------
  // form submit → schedule workflow + poll
  // -----------------------------------------------------------
  $form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = $input.value.trim();
    if (!query) return;

    appendUser(query);
    const $assistant = appendWorking(query);
    $submit.disabled = true;

    try {
      const result = await runParlayWorkflow(query, (step) => {
        const $step = $assistant.querySelector('.working-step');
        if ($step) $step.textContent = step;
      });
      renderAssistant($assistant, result);
    } catch (err) {
      renderError($assistant, err);
    } finally {
      $submit.disabled = false;
      $input.focus();
      $assistant.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  });

  // -----------------------------------------------------------
  // workflow runner — schedule + poll the Machina pod
  // -----------------------------------------------------------
  async function runParlayWorkflow(query, onStep) {
    const deploy = window.MACHINA_DEPLOY;
    if (!deploy || !deploy.proxyUrl) {
      throw new Error(
        'this page is showing seeded sample tickets. live generation activates ' +
        'once it is deployed via Machina Factory (which injects the runtime proxy).'
      );
    }
    const proxy = deploy.proxyUrl.replace(/\/+$/, '');

    onStep('scheduling workflow…');
    const schedRes = await fetch(`${proxy}/workflow/schedule/parlay-builder`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ user_query: query }),
    });
    if (!schedRes.ok) {
      throw new Error(`schedule failed (${schedRes.status})`);
    }
    const schedJson = await schedRes.json();
    // Machina wraps responses as { data: { workflow_run_id } } sometimes,
    // and as { workflow_run_id } directly other times. Handle both.
    const runId =
      schedJson?.data?.workflow_run_id ||
      schedJson?.workflow_run_id ||
      schedJson?.data?.data?.workflow_run_id;
    if (!runId) {
      throw new Error('schedule returned no workflow_run_id');
    }

    onStep('parsing your angle…');

    // poll loop — up to ~3 minutes
    const STEPS = [
      'parsing your angle…',
      'pulling today\'s fixtures…',
      'reading lines from the book…',
      'pricing candidate legs…',
      'composing parlays + EV math…',
      'composing parlays + EV math…',
      'finalising tickets…',
    ];
    let lastStepIdx = 0;
    const MAX_POLLS = 60;       // 60 * 3s = 3min
    const POLL_INTERVAL = 3000;

    for (let i = 0; i < MAX_POLLS; i++) {
      await sleep(POLL_INTERVAL);
      // advance the working-step text every ~9s for perceived progress
      const stepIdx = Math.min(Math.floor(i / 3), STEPS.length - 1);
      if (stepIdx !== lastStepIdx) {
        onStep(STEPS[stepIdx]);
        lastStepIdx = stepIdx;
      }

      const pollRes = await fetch(`${proxy}/workflow/schedule/${runId}`, {
        method: 'GET',
        headers: { 'content-type': 'application/json' },
      });
      if (!pollRes.ok) {
        // transient — log and keep polling
        console.warn('poll non-ok', pollRes.status);
        continue;
      }
      const pollJson = await pollRes.json();
      const run = pollJson?.data?.data || pollJson?.data || pollJson;
      const status = run?.status;
      if (status === 'executed' || status === 'failed' || status === 'skipped') {
        const outputs = run?.workflow_output?.outputs || {};
        if (status !== 'executed') {
          throw new Error(
            `workflow ${status} — ${outputs['workflow-error']?.message || 'no tickets produced'}`
          );
        }
        return outputs;
      }
    }
    throw new Error('workflow timed out after 3 minutes');
  }

  // -----------------------------------------------------------
  // dom helpers — append / render messages
  // -----------------------------------------------------------
  function appendUser(text) {
    const $el = document.createElement('article');
    $el.className = 'msg user';
    $el.innerHTML = `
      <div class="role">bettor</div>
      <div class="bubble">${escapeHtml(text)}</div>
    `;
    $thread.appendChild($el);
    $el.scrollIntoView({ behavior: 'smooth', block: 'end' });
    return $el;
  }

  function appendWorking(query) {
    const $el = document.createElement('article');
    $el.className = 'msg assistant working';
    $el.innerHTML = `
      <div class="role">copilot</div>
      <div class="bubble">
        <div class="working-row">
          <span class="spinner" aria-hidden="true"></span>
          <span>building tickets for <em>${escapeHtml(query)}</em></span>
        </div>
        <div class="working-step muted small" style="margin-top:8px">scheduling workflow…</div>
      </div>
    `;
    $thread.appendChild($el);
    $el.scrollIntoView({ behavior: 'smooth', block: 'end' });
    return $el;
  }

  function renderAssistant($el, outputs) {
    const tickets = Array.isArray(outputs.tickets) ? outputs.tickets : [];
    const reply = (outputs.reply_markdown || '').trim();
    const followups = Array.isArray(outputs.followup_suggestions) ? outputs.followup_suggestions : [];

    const payload = { tickets, followup_suggestions: followups };

    $el.classList.remove('working');
    $el.innerHTML = `
      <div class="role">copilot</div>
      <div class="bubble">
        <div class="reply markdown">${renderMarkdown(reply || 'no tickets returned.')}</div>
        <div class="tickets">${renderTickets(tickets)}</div>
        <div class="payload">
          <details>
            <summary><span class="dot-mono"></span>raw ticket payload <span class="muted small">— what the operator's frontend submits</span></summary>
            <pre>${escapeHtml(JSON.stringify(payload, null, 2))}</pre>
          </details>
        </div>
        ${followups.length ? `<div class="followups">${followups
          .map((s) => `<button type="button" class="chip muted" data-preset="${escapeAttr(s)}">${escapeHtml(s)}</button>`)
          .join('')}</div>` : ''}
      </div>
    `;
  }

  function renderError($el, err) {
    $el.classList.remove('working');
    $el.classList.add('error');
    $el.innerHTML = `
      <div class="role">copilot</div>
      <div class="bubble">
        <div class="err-text">${escapeHtml(err.message || 'something went wrong')}</div>
        <div class="muted small" style="margin-top:8px">
          if you're seeing this on a local preview, the seeded sample tickets above
          show what a live response looks like.
        </div>
      </div>
    `;
  }

  // -----------------------------------------------------------
  // ticket renderer — turns the workflow's structured ticket list
  // into the trading-desk card grid the operator sees.
  // -----------------------------------------------------------
  function renderTickets(tickets) {
    if (!tickets || tickets.length === 0) return '';
    return tickets
      .map((t, i) => {
        const odds = formatAmericanOdds(t.combined_american_odds);
        const ev = Number(t.expected_value_pct ?? 0);
        const kelly = Number(t.kelly_fraction_pct ?? 0);
        const prob = Number(t.combined_probability ?? 0);
        const evCls = ev >= 0 ? 'ev-pos' : 'ev-neg';
        const negCls = t.combined_american_odds < 0 ? 'neg' : '';
        const legsHtml = (t.legs || [])
          .map((l) => `
            <li>
              <div class="leg-row">
                <span class="leg-sel">${escapeHtml(l.selection || '')}</span>
                <span class="leg-price">${formatAmericanOdds(l.book_american_odds)}</span>
              </div>
              <div class="leg-match">${escapeHtml(l.match_label || '')} · ${escapeHtml(humanMarket(l.market_type))}</div>
              ${l.justification ? `<div class="leg-just">${escapeHtml(l.justification)}</div>` : ''}
            </li>
          `).join('');
        return `
          <div class="ticket rank-${i + 1} ${negCls}">
            <div class="ticket-head">
              <span class="ticket-rank">ticket ${i + 1}</span>
              <span class="ticket-odds">${odds}</span>
            </div>
            <div class="ticket-meta">
              <span>EV <b class="${evCls}">${formatPct(ev)}</b></span>
              <span>hit <b>${formatPct(prob * 100)}</b></span>
              <span>kelly <b>${formatPct(kelly)}</b></span>
            </div>
            <ul class="ticket-legs">${legsHtml}</ul>
            ${t.rationale ? `<div class="ticket-rationale">${escapeHtml(t.rationale)}</div>` : ''}
          </div>
        `;
      })
      .join('');
  }

  // -----------------------------------------------------------
  // formatters
  // -----------------------------------------------------------
  function formatAmericanOdds(n) {
    if (n === null || n === undefined || isNaN(n)) return '—';
    const v = Math.round(Number(n));
    return v >= 0 ? `+${v}` : `${v}`;
  }
  function formatPct(n) {
    if (n === null || n === undefined || isNaN(n)) return '—';
    const sign = n > 0 ? '+' : '';
    return `${sign}${Number(n).toFixed(1)}%`;
  }
  function humanMarket(m) {
    if (!m) return '';
    return String(m).replace(/_/g, ' ').toLowerCase();
  }

  // -----------------------------------------------------------
  // tiny safe markdown renderer — handles **bold**, *italic*,
  // `code`, paragraphs, and `*  ` bullets (the shape gemini emits).
  // No external deps; keeps the bundle small and the DOM trusted.
  // -----------------------------------------------------------
  function renderMarkdown(src) {
    if (!src) return '';
    const lines = src.split('\n');
    const out = [];
    let inList = false;
    let buf = [];
    const flushPara = () => {
      if (buf.length) {
        out.push(`<p>${inline(buf.join(' '))}</p>`);
        buf = [];
      }
    };
    const closeList = () => {
      if (inList) {
        out.push('</ul>');
        inList = false;
      }
    };
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (!line.trim()) {
        flushPara();
        closeList();
        continue;
      }
      // bullet: leading "*   " or "- "
      const bullet = line.match(/^\s*[*\-•]\s+(.*)$/);
      if (bullet) {
        flushPara();
        if (!inList) { out.push('<ul>'); inList = true; }
        out.push(`<li>${inline(bullet[1])}</li>`);
        continue;
      }
      // heading-ish lines starting with **xxx** by themselves
      closeList();
      buf.push(line);
    }
    flushPara();
    closeList();
    return out.join('\n');
  }
  function inline(s) {
    // escape first, then re-apply bold/italic/code via tokens we control
    let str = escapeHtml(s);
    str = str.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    str = str.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    str = str.replace(/`([^`]+)`/g, '<code>$1</code>');
    return str;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
  function escapeAttr(s) {
    return escapeHtml(s);
  }

  function sleep(ms) {
    return new Promise((res) => setTimeout(res, ms));
  }

  // -----------------------------------------------------------
  // bootstrap
  // -----------------------------------------------------------
  hydrateSeed();
})();
