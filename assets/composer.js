// Canvas composer — turns a (team, intent, rows, palette) tuple into a
// pixel-baked PNG via HTML5 Canvas. Three layouts keyed on aspect ratio.

const RATIOS = {
  square:    { w: 1080, h: 1080, label: "1:1"  },
  landscape: { w: 1920, h: 1080, label: "16:9" },
  vertical:  { w: 1080, h: 1920, label: "9:16" },
};

export function ratioPreset(key) { return RATIOS[key] || RATIOS.square; }

// ---------- Color helpers ----------
function hexToRgb(hex) {
  const h = hex.replace(/^#/, "");
  const n = parseInt(h.length === 3 ? h.split("").map(c => c + c).join("") : h, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}
function rgbToHex({ r, g, b }) {
  return [r, g, b].map(v => v.toString(16).padStart(2, "0")).join("");
}
function luminance({ r, g, b }) {
  const a = [r, g, b].map(v => {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];
}
function contrastRatio(hex1, hex2) {
  const L1 = luminance(hexToRgb(hex1));
  const L2 = luminance(hexToRgb(hex2));
  return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
}
// Pick the foreground color (from the team palette or pure black/white)
// that has the best contrast against the chosen background.
function bestFg(bgHex, candidates) {
  let best = candidates[0], score = 0;
  for (const c of candidates) {
    const s = contrastRatio(bgHex, c);
    if (s > score) { score = s; best = c; }
  }
  return best;
}

// ---------- Palette ----------
/**
 * Build the working palette from a team's brand colors, optionally
 * overridden by colors extracted from a user-uploaded reference image.
 *
 * Returns { bg, panel, ink, accent, muted } — all WITHOUT leading #.
 */
export function buildPalette(team, referenceColors) {
  // Prefer reference image colors when provided; the dominant + second
  // dominant become bg + panel, brightest becomes accent.
  if (referenceColors && referenceColors.length >= 2) {
    const [c1, c2, c3] = referenceColors;
    const bg = c1;
    const panel = c2;
    const accent = c3 || team.accent || team.secondary;
    const ink = bestFg(bg, ["FFFFFF", "0A0A0A"]);
    return { bg, panel, ink, accent, muted: "rgba(255,255,255,0.55)" };
  }

  const primary = team.primary;
  const secondary = team.secondary;
  const accent = team.accent || secondary;

  // If primary is very light (e.g. yellow Dortmund), flip — use a dark
  // sibling for bg so the graphic isn't blinding.
  const primaryLight = luminance(hexToRgb(primary)) > 0.55;
  const bg = primaryLight ? (luminance(hexToRgb(secondary)) < 0.4 ? secondary : "0A0A0A") : primary;
  const panel = bg === primary ? darken(primary, 0.18) : primary;
  const ink = bestFg(bg, ["FFFFFF", "0A0A0A"]);
  return { bg, panel, ink, accent, muted: ink === "FFFFFF" ? "rgba(255,255,255,0.55)" : "rgba(10,10,10,0.55)" };
}

function darken(hex, amount) {
  const { r, g, b } = hexToRgb(hex);
  return rgbToHex({
    r: Math.max(0, Math.round(r * (1 - amount))),
    g: Math.max(0, Math.round(g * (1 - amount))),
    b: Math.max(0, Math.round(b * (1 - amount))),
  });
}

// ---------- Reference image palette extraction ----------
// k-means lite via quantized histogram. Reduces each channel to 4 bits and
// picks the top buckets by frequency.
export async function extractPaletteFromImage(file) {
  const url = URL.createObjectURL(file);
  try {
    const img = await loadImage(url);
    const c = document.createElement("canvas");
    const W = 64, H = Math.max(1, Math.round(64 * img.height / img.width));
    c.width = W; c.height = H;
    const ctx = c.getContext("2d");
    ctx.drawImage(img, 0, 0, W, H);
    const data = ctx.getImageData(0, 0, W, H).data;
    const buckets = new Map();
    for (let i = 0; i < data.length; i += 4) {
      const a = data[i + 3];
      if (a < 200) continue;
      // 4 bits per channel = 16 levels = 4096 total buckets
      const r = data[i] >> 4, g = data[i + 1] >> 4, b = data[i + 2] >> 4;
      const key = (r << 8) | (g << 4) | b;
      buckets.set(key, (buckets.get(key) || 0) + 1);
    }
    const sorted = [...buckets.entries()].sort((a, b) => b[1] - a[1]);
    // Reject near-duplicates so we get 3 visually distinct picks
    const picks = [];
    for (const [key] of sorted) {
      const r = ((key >> 8) & 15) * 17;
      const g = ((key >> 4) & 15) * 17;
      const b = (key & 15) * 17;
      const hex = rgbToHex({ r, g, b });
      if (picks.every(p => colorDistance(p, hex) > 60)) {
        picks.push(hex);
        if (picks.length === 3) break;
      }
    }
    return picks;
  } finally {
    URL.revokeObjectURL(url);
  }
}

function colorDistance(a, b) {
  const A = hexToRgb(a), B = hexToRgb(b);
  return Math.sqrt((A.r - B.r) ** 2 + (A.g - B.g) ** 2 + (A.b - B.b) ** 2);
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

// ---------- Composer ----------
/**
 * Draw the graphic into a Canvas2D context.
 * @param {CanvasRenderingContext2D} ctx
 * @param {{w:number,h:number}} dims
 * @param {object} args { team, intent, rows, palette, headline }
 */
export function compose(ctx, dims, args) {
  const { w, h } = dims;
  const { team, intent, rows, palette, headline } = args;
  const isPortrait = h > w;
  const isLandscape = w > h * 1.2;

  // 1. Background — solid + diagonal panel for movement
  ctx.fillStyle = "#" + palette.bg;
  ctx.fillRect(0, 0, w, h);

  // Diagonal accent slash (subtle, off-center)
  ctx.save();
  ctx.translate(w * 0.7, 0);
  ctx.rotate(-0.25);
  ctx.fillStyle = "#" + palette.panel;
  ctx.fillRect(-w * 0.1, -h * 0.2, w * 0.55, h * 1.6);
  ctx.restore();

  // Thin accent rule bottom
  ctx.fillStyle = "#" + palette.accent;
  ctx.fillRect(0, h - h * 0.012, w, h * 0.012);

  // 2. Padding scaffold
  const padX = Math.round(w * 0.06);
  const padTop = Math.round(h * 0.06);

  // 3. Header strip: SPORT · LEAGUE · DATE
  const meta = `${team.sport.toUpperCase()}  ·  ${team.league.toUpperCase()}  ·  ${formatToday()}`;
  ctx.fillStyle = palette.muted;
  ctx.font = `600 ${Math.round(h * 0.018)}px "JetBrains Mono", "Menlo", monospace`;
  ctx.textBaseline = "top";
  ctx.fillText(meta, padX, padTop);

  // 4. Team crest mark — color block with short code
  const crestSize = Math.round(Math.min(w, h) * 0.16);
  const crestX = padX;
  const crestY = padTop + Math.round(h * 0.04);
  drawCrest(ctx, crestX, crestY, crestSize, team, palette);

  // 5. Team name
  ctx.fillStyle = "#" + palette.ink;
  ctx.textBaseline = "top";
  const nameSize = Math.round(h * (isLandscape ? 0.055 : 0.045));
  ctx.font = `900 ${nameSize}px "Archivo Black", "Anton", "Inter", system-ui, sans-serif`;
  const nameX = crestX + crestSize + Math.round(w * 0.025);
  ctx.fillText(team.name.toUpperCase(), nameX, crestY + Math.round(crestSize * 0.18));

  ctx.fillStyle = palette.muted;
  ctx.font = `600 ${Math.round(h * 0.022)}px "JetBrains Mono", monospace`;
  ctx.fillText(team.short + "  ·  EST. BRAND", nameX, crestY + Math.round(crestSize * 0.18) + nameSize + 6);

  // 6. Headline — the BIG thing
  const headlineY = crestY + crestSize + Math.round(h * 0.06);
  const headlineFontSize = Math.round(h * (isLandscape ? 0.085 : isPortrait ? 0.07 : 0.075));
  ctx.fillStyle = "#" + palette.ink;
  ctx.font = `900 ${headlineFontSize}px "Archivo Black", "Anton", "Inter", system-ui, sans-serif`;
  const headlineText = (headline || intent.label || "").toUpperCase();
  const headlineLines = wrapText(ctx, headlineText, w - padX * 2, headlineFontSize);
  let hy = headlineY;
  for (const line of headlineLines.slice(0, 3)) {
    ctx.fillText(line, padX, hy);
    hy += headlineFontSize * 1.0;
  }

  // 7. Data block — rows
  const blockTop = hy + Math.round(h * 0.04);
  const blockBottom = h - Math.round(h * 0.08);
  const available = blockBottom - blockTop;
  drawRows(ctx, padX, blockTop, w - padX * 2, available, rows, palette);

  // 8. Footer — brand tag
  ctx.fillStyle = palette.muted;
  ctx.font = `700 ${Math.round(h * 0.018)}px "JetBrains Mono", monospace`;
  ctx.textBaseline = "bottom";
  const footerY = h - Math.round(h * 0.025);
  ctx.fillText("MACHINA / SOCIAL", padX, footerY);
  const stamp = `#${team.short} · ${intent.intent.toUpperCase()}`;
  const stampW = ctx.measureText(stamp).width;
  ctx.fillText(stamp, w - padX - stampW, footerY);
}

function drawCrest(ctx, x, y, size, team, palette) {
  // Big square with short code reversed out — visually substitutes a logo
  ctx.fillStyle = "#" + (team.secondary === palette.bg ? team.accent : team.secondary);
  ctx.fillRect(x, y, size, size);

  // Inner outline using accent
  ctx.strokeStyle = "#" + team.accent;
  ctx.lineWidth = Math.max(3, size * 0.025);
  ctx.strokeRect(x + ctx.lineWidth, y + ctx.lineWidth, size - ctx.lineWidth * 2, size - ctx.lineWidth * 2);

  // Short code
  const code = team.short;
  ctx.fillStyle = "#" + team.primary;
  ctx.font = `900 ${Math.round(size * 0.42)}px "Archivo Black", "Anton", "Inter", sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(code, x + size / 2, y + size / 2);
  ctx.textAlign = "start";
  ctx.textBaseline = "alphabetic";
}

function wrapText(ctx, text, maxWidth, fontSize) {
  if (!text) return [""];
  const words = text.split(/\s+/);
  const lines = [];
  let line = "";
  for (const w of words) {
    const test = line ? `${line} ${w}` : w;
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = w;
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  // Auto-shrink: if we end up with more than 3 lines, fall back to ellipsis on line 3
  if (lines.length > 3) {
    let third = lines[2];
    while (ctx.measureText(third + "…").width > maxWidth && third.length > 4) {
      third = third.slice(0, -1);
    }
    lines[2] = third + "…";
  }
  return lines;
}

function drawRows(ctx, x, y, width, height, rows, palette) {
  if (!rows || rows.length === 0) {
    ctx.fillStyle = "#" + palette.ink;
    ctx.font = `700 ${Math.round(height * 0.06)}px "Inter", system-ui, sans-serif`;
    ctx.textBaseline = "top";
    ctx.fillText("No data available.", x, y);
    ctx.fillStyle = palette.muted;
    ctx.font = `500 ${Math.round(height * 0.035)}px "Inter", system-ui, sans-serif`;
    ctx.fillText("Try a different query — e.g. \"next 5 games\".", x, y + Math.round(height * 0.07));
    return;
  }

  const n = Math.min(rows.length, 5);
  const gap = Math.round(height * 0.025);
  const rowH = (height - gap * (n - 1)) / n;

  for (let i = 0; i < n; i++) {
    const row = rows[i];
    const ry = y + i * (rowH + gap);
    drawRow(ctx, x, ry, width, rowH, row, palette, i === 0);
  }
}

function drawRow(ctx, x, y, w, h, row, palette, highlight) {
  // Card background — semi-translucent ink so it works on both bg & panel
  ctx.fillStyle = palette.ink === "FFFFFF" ? "rgba(255,255,255,0.08)" : "rgba(10,10,10,0.08)";
  roundRect(ctx, x, y, w, h, Math.min(16, h * 0.12));
  ctx.fill();

  // Left accent bar
  ctx.fillStyle = "#" + (highlight ? palette.accent : palette.ink);
  ctx.fillRect(x, y, Math.max(4, w * 0.006), h);

  const padL = Math.round(w * 0.035);
  const padR = Math.round(w * 0.035);

  // Meta tag (top-left mini)
  if (row.meta) {
    ctx.fillStyle = "#" + palette.accent;
    ctx.font = `800 ${Math.round(h * 0.18)}px "JetBrains Mono", monospace`;
    ctx.textBaseline = "top";
    ctx.fillText(row.meta.toUpperCase(), x + padL + Math.round(w * 0.01), y + Math.round(h * 0.12));
  }

  // Primary (left, big)
  ctx.fillStyle = "#" + palette.ink;
  ctx.textBaseline = "middle";
  ctx.font = `900 ${Math.round(h * 0.42)}px "Archivo Black", "Anton", "Inter", sans-serif`;
  const primaryText = String(row.primary ?? "");
  // Auto-shrink primary if it doesn't fit
  let primarySize = Math.round(h * 0.42);
  while (ctx.measureText(primaryText).width > w * 0.5 && primarySize > 18) {
    primarySize -= 2;
    ctx.font = `900 ${primarySize}px "Archivo Black", "Anton", "Inter", sans-serif`;
  }
  ctx.fillText(primaryText, x + padL + Math.round(w * 0.01), y + h * (row.meta ? 0.62 : 0.52));

  // Secondary (right-aligned)
  const secondaryText = String(row.secondary ?? "");
  ctx.fillStyle = "#" + palette.ink;
  ctx.font = `600 ${Math.round(h * 0.22)}px "Inter", system-ui, sans-serif`;
  ctx.textAlign = "right";
  let sec = secondaryText;
  while (ctx.measureText(sec).width > w * 0.5 - padR && sec.length > 4) {
    sec = sec.slice(0, -1);
  }
  if (sec !== secondaryText) sec = sec.slice(0, -1) + "…";
  ctx.fillText(sec, x + w - padR, y + h / 2);
  ctx.textAlign = "start";
  ctx.textBaseline = "alphabetic";
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function formatToday() {
  const d = new Date();
  const months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
  return `${months[d.getMonth()]} ${String(d.getDate()).padStart(2,"0")}, ${d.getFullYear()}`;
}
