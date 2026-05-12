"""PDF generator connector.

Renders a structured payload as a multi-page PDF and returns the result as
base64 so it can be handed straight to the `google-storage` connector
(which accepts Data URI / raw base64 inputs).

Four layouts are bundled out of the box — they're meant as starting
points for brand teams, sales, producers, and ops/analytics:

  * brand-assets    — a multi-page brand guide (cover, palette, logos,
                      typography, voice/tone, imagery do/don't)
  * rate-card       — a tabular rate card with tier pricing + notes
  * contact-sheet   — thumbnail grid of images (16-up, 4 cols x 4 rows)
  * metrics-report  — KPI summary cards + sectioned tables / stats lists
                      (analytics, observability, cost / usage reports)

Pages are deliberately capped around ~14pp for brand-assets to match the
canonical "PDF · 14pp · brand assets" deliverable shape.
"""

from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _hex_to_color(value, default="#111111"):
    if not value:
        value = default
    value = str(value).strip()
    if not value.startswith("#"):
        value = "#" + value
    try:
        return colors.HexColor(value)
    except Exception:
        return colors.HexColor(default)


def _pagesize(name):
    if str(name).lower() in ("a4",):
        return A4
    return letter


def _resolve_image(src):
    """Return a local file path for an image src (URL or path).

    Returns a tuple `(path, cleanup_path_or_None)`. The caller is
    responsible for deleting the cleanup path when done.
    """
    if not src:
        return None, None
    src = str(src)
    if src.startswith("http://") or src.startswith("https://"):
        try:
            req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            suffix = os.path.splitext(urllib.parse.urlparse(src).path)[1] or ".img"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(data)
            tmp.close()
            return tmp.name, tmp.name
        except Exception:
            return None, None
    if os.path.exists(src):
        return src, None
    return None, None


def _styles(brand_color):
    base = getSampleStyleSheet()
    out = {
        "title": ParagraphStyle(
            "title", parent=base["Title"],
            fontName="Helvetica-Bold", fontSize=32, leading=38,
            textColor=brand_color, spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"],
            fontName="Helvetica-Bold", fontSize=20, leading=24,
            textColor=brand_color, spaceBefore=18, spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"],
            fontName="Helvetica-Bold", fontSize=14, leading=18,
            textColor=colors.HexColor("#222222"), spaceBefore=10, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"],
            fontName="Helvetica", fontSize=10.5, leading=15,
            textColor=colors.HexColor("#333333"), spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "small", parent=base["BodyText"],
            fontName="Helvetica", fontSize=8.5, leading=12,
            textColor=colors.HexColor("#666666"),
        ),
    }
    return out


# ---------------------------------------------------------------------------
# Layout: brand-assets (≈14pp)
# ---------------------------------------------------------------------------


def _build_brand_assets(content, pagesize, brand_color):
    """Return (page_builder, story) for brand-assets layout."""
    s = _styles(brand_color)
    story = []

    brand_name = content.get("brand_name") or content.get("title") or "Brand Guidelines"
    tagline = content.get("tagline") or ""
    issued = content.get("issued") or datetime.utcnow().strftime("%B %Y")

    # Cover
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph(brand_name, s["title"]))
    if tagline:
        story.append(Paragraph(tagline, s["h2"]))
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph(f"Issued: {issued}", s["small"]))
    story.append(PageBreak())

    # 1. Mission / About
    if content.get("about"):
        story.append(Paragraph("01 · About", s["h1"]))
        story.append(Paragraph(content["about"], s["body"]))
        story.append(PageBreak())

    # 2. Mission & values
    if content.get("mission") or content.get("values"):
        story.append(Paragraph("02 · Mission & Values", s["h1"]))
        if content.get("mission"):
            story.append(Paragraph("Mission", s["h2"]))
            story.append(Paragraph(content["mission"], s["body"]))
        if content.get("values"):
            story.append(Paragraph("Values", s["h2"]))
            for v in content["values"]:
                if isinstance(v, dict):
                    story.append(Paragraph(f"<b>{v.get('name','')}.</b> {v.get('description','')}", s["body"]))
                else:
                    story.append(Paragraph(f"• {v}", s["body"]))
        story.append(PageBreak())

    # 3. Logo
    if content.get("logos"):
        story.append(Paragraph("03 · Logo", s["h1"]))
        story.append(Paragraph("Primary, secondary, and clear-space variants.", s["body"]))
        cleanup_paths = []
        for logo in content["logos"][:4]:
            src = logo.get("url") if isinstance(logo, dict) else logo
            path, cleanup = _resolve_image(src)
            if cleanup:
                cleanup_paths.append(cleanup)
            if path:
                story.append(Spacer(1, 6 * mm))
                try:
                    story.append(Image(path, width=10 * cm, height=5 * cm, kind="proportional"))
                except Exception:
                    pass
                if isinstance(logo, dict) and logo.get("label"):
                    story.append(Paragraph(logo["label"], s["small"]))
        story.append(PageBreak())

    # 4. Color palette (drawn primitive — no image needed)
    if content.get("palette"):
        story.append(Paragraph("04 · Color Palette", s["h1"]))
        rows = []
        header = ["Swatch", "Name", "HEX", "RGB", "Usage"]
        rows.append(header)
        for c in content["palette"][:8]:
            hex_value = c.get("hex", "#000000")
            try:
                col = colors.HexColor(hex_value)
                rgb = f"{int(col.red*255)}, {int(col.green*255)}, {int(col.blue*255)}"
            except Exception:
                rgb = ""
            rows.append(["", c.get("name", ""), hex_value, rgb, c.get("usage", "")])
        table = Table(rows, colWidths=[2.2 * cm, 4 * cm, 2.5 * cm, 3 * cm, 5 * cm])
        ts = TableStyle([
            ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4F4F4")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#222222")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#CCCCCC")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])
        for i, c in enumerate(content["palette"][:8], start=1):
            ts.add("BACKGROUND", (0, i), (0, i), _hex_to_color(c.get("hex"), "#000000"))
        table.setStyle(ts)
        story.append(table)
        story.append(PageBreak())

    # 5. Typography
    if content.get("typography"):
        story.append(Paragraph("05 · Typography", s["h1"]))
        for t in content["typography"]:
            story.append(Paragraph(t.get("name", ""), s["h2"]))
            story.append(Paragraph(t.get("description", ""), s["body"]))
            if t.get("sample"):
                story.append(Paragraph(f"<font size=\"18\">{t['sample']}</font>", s["body"]))
            story.append(Spacer(1, 4 * mm))
        story.append(PageBreak())

    # 6. Voice & tone
    if content.get("voice"):
        story.append(Paragraph("06 · Voice & Tone", s["h1"]))
        v = content["voice"]
        if isinstance(v, dict):
            if v.get("description"):
                story.append(Paragraph(v["description"], s["body"]))
            if v.get("do") or v.get("dont"):
                rows = [["Do", "Don't"]]
                rows += list(zip(v.get("do", []), v.get("dont", [])))
                table = Table(rows, colWidths=[8.5 * cm, 8.5 * cm])
                table.setStyle(TableStyle([
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 10),
                    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10),
                    ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#E8F5E9")),
                    ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#FFEBEE")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LINEABOVE", (0, 1), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
                ]))
                story.append(table)
        else:
            story.append(Paragraph(str(v), s["body"]))
        story.append(PageBreak())

    # 7. Imagery
    if content.get("imagery"):
        story.append(Paragraph("07 · Imagery", s["h1"]))
        story.append(Paragraph(
            content["imagery"].get("description", "") if isinstance(content["imagery"], dict) else "",
            s["body"],
        ))
        urls = (content["imagery"].get("samples", []) if isinstance(content["imagery"], dict) else content["imagery"])[:4]
        cells = []
        for url in urls:
            path, _cleanup = _resolve_image(url)
            if path:
                try:
                    cells.append(Image(path, width=8 * cm, height=5 * cm, kind="proportional"))
                except Exception:
                    cells.append("")
            else:
                cells.append("")
        if cells:
            rows = [cells[i:i + 2] for i in range(0, len(cells), 2)]
            for row in rows:
                while len(row) < 2:
                    row.append("")
            table = Table(rows, colWidths=[8.5 * cm, 8.5 * cm], rowHeights=[6 * cm] * len(rows))
            table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
            story.append(table)
        story.append(PageBreak())

    # 8. Contact
    contact = content.get("contact") or {}
    story.append(Paragraph("08 · Contact", s["h1"]))
    story.append(Paragraph(contact.get("description", "Reach the brand team for asset requests, approvals, and partnerships."), s["body"]))
    if contact.get("email"):
        story.append(Paragraph(f"<b>Email:</b> {contact['email']}", s["body"]))
    if contact.get("website"):
        story.append(Paragraph(f"<b>Web:</b> {contact['website']}", s["body"]))
    if contact.get("address"):
        story.append(Paragraph(f"<b>Address:</b> {contact['address']}", s["body"]))

    return story


# ---------------------------------------------------------------------------
# Layout: rate-card
# ---------------------------------------------------------------------------


def _build_rate_card(content, pagesize, brand_color):
    s = _styles(brand_color)
    story = []
    title = content.get("title") or "Rate Card"
    period = content.get("period") or datetime.utcnow().strftime("%Y")

    story.append(Paragraph(title, s["title"]))
    story.append(Paragraph(f"Effective {period}", s["h2"]))
    if content.get("intro"):
        story.append(Paragraph(content["intro"], s["body"]))
    story.append(Spacer(1, 8 * mm))

    tiers = content.get("tiers") or []
    if tiers:
        # Header
        rows = [["Tier", "Description", "Deliverables", "Price"]]
        for t in tiers:
            deliverables = t.get("deliverables", [])
            if isinstance(deliverables, list):
                deliverables = "\n".join(f"• {d}" for d in deliverables)
            rows.append([
                Paragraph(f"<b>{t.get('name','')}</b>", s["body"]),
                Paragraph(t.get("description", ""), s["body"]),
                Paragraph(deliverables.replace("\n", "<br/>"), s["body"]),
                Paragraph(f"<b>{t.get('price','')}</b>", s["body"]),
            ])
        table = Table(rows, colWidths=[3 * cm, 5 * cm, 6 * cm, 3 * cm], repeatRows=1)
        table.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10),
            ("BACKGROUND", (0, 0), (-1, 0), brand_color),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F8F8")]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
        ]))
        story.append(table)

    story.append(Spacer(1, 1 * cm))

    if content.get("notes"):
        story.append(Paragraph("Notes", s["h2"]))
        for note in content["notes"]:
            story.append(Paragraph(f"• {note}", s["body"]))

    contact = content.get("contact") or {}
    if contact:
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph("Contact", s["h2"]))
        if contact.get("email"):
            story.append(Paragraph(f"Email: {contact['email']}", s["body"]))
        if contact.get("phone"):
            story.append(Paragraph(f"Phone: {contact['phone']}", s["body"]))

    return story


# ---------------------------------------------------------------------------
# Layout: metrics-report (KPI summary cards + sectioned tables)
# ---------------------------------------------------------------------------


def _build_metrics_report(content, pagesize, brand_color):
    """Tabular metrics report — summary KPI cards, sectioned tables/stats, notes.

    Schema (all keys optional except title):
      title:           str
      period:          str — e.g. "Last 24h" / "2026-05-11"
      intro:           str — paragraph of insights (markdown-light: paragraphs)
      summary_cards:   [{label, value, delta?}]                       — 2-col grid
      sections:        [
        {
          title: str,
          table: { headers: [str], rows: [[str|number]] }              — tabular
            OR
          stats: [{label, value}]                                      — list
            OR
          bullets: [str]                                               — list
        }
      ]
      notes:           [str]
      footer:          str
    """
    s = _styles(brand_color)
    story = []

    title = content.get("title") or "Metrics Report"
    period = content.get("period") or datetime.utcnow().strftime("%Y-%m-%d")

    story.append(Paragraph(title, s["title"]))
    story.append(Paragraph(period, s["h2"]))

    intro = content.get("intro")
    if intro:
        # Split paragraphs on blank lines so reportlab wraps each cleanly
        for para in str(intro).split("\n\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(para.replace("\n", "<br/>"), s["body"]))
        story.append(Spacer(1, 6 * mm))

    # Summary cards — 2-column grid (label · value · optional delta)
    cards = content.get("summary_cards") or []
    if cards:
        # Group cards into rows of 2
        card_rows = []
        for i in range(0, len(cards), 2):
            pair = cards[i:i + 2]
            row = []
            for c in pair:
                value = str(c.get("value", ""))
                label = str(c.get("label", ""))
                delta = c.get("delta")
                cell_html = (
                    f'<font size="9" color="#666666">{label}</font><br/>'
                    f'<font size="20"><b>{value}</b></font>'
                )
                if delta:
                    cell_html += f'<br/><font size="8" color="#888888">{delta}</font>'
                row.append(Paragraph(cell_html, s["body"]))
            # Pad if odd number
            while len(row) < 2:
                row.append(Paragraph("", s["body"]))
            card_rows.append(row)
        card_table = Table(card_rows, colWidths=[8 * cm, 8 * cm])
        card_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8F8F8")),
            ("LINEBELOW", (0, 0), (-1, -1), 1, colors.white),
        ]))
        story.append(card_table)
        story.append(Spacer(1, 8 * mm))

    # Sections — each can be table | stats | bullets
    for section in content.get("sections") or []:
        sec_title = section.get("title")
        if sec_title:
            story.append(Paragraph(sec_title, s["h2"]))

        table = section.get("table")
        stats = section.get("stats")
        bullets = section.get("bullets")

        if table and table.get("headers") and table.get("rows"):
            headers = [str(h) for h in table["headers"]]
            n_cols = len(headers)
            data = [[Paragraph(f"<b>{h}</b>", s["body"]) for h in headers]]
            for row in table["rows"]:
                cells = [Paragraph(str(cell), s["body"]) for cell in row]
                # Pad/truncate to header width so the Table doesn't blow up
                cells = cells[:n_cols] + [Paragraph("", s["body"])] * max(0, n_cols - len(cells))
                data.append(cells)
            # Even column widths within available width (16cm content area)
            col_widths = [16.0 / n_cols * cm] * n_cols
            t = Table(data, colWidths=col_widths, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), brand_color),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F8F8")]),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
            ]))
            story.append(t)
        elif stats:
            # Two-column label/value list
            data = [
                [Paragraph(str(item.get("label", "")), s["body"]),
                 Paragraph(f"<b>{item.get('value', '')}</b>", s["body"])]
                for item in stats
            ]
            t = Table(data, colWidths=[10 * cm, 6 * cm])
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#EEEEEE")),
            ]))
            story.append(t)
        elif bullets:
            for b in bullets:
                story.append(Paragraph(f"• {b}", s["body"]))

        story.append(Spacer(1, 5 * mm))

    if content.get("notes"):
        story.append(Paragraph("Notes", s["h2"]))
        for note in content["notes"]:
            story.append(Paragraph(f"• {note}", s["body"]))
        story.append(Spacer(1, 5 * mm))

    footer = content.get("footer")
    if footer:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(str(footer), s["small"]))

    return story


# ---------------------------------------------------------------------------
# Layout: contact-sheet (image grid)
# ---------------------------------------------------------------------------


def _build_contact_sheet_canvas(content, pagesize, brand_color, output_path):
    """contact-sheet uses raw canvas drawing for tighter grid control."""
    title = content.get("title") or "Contact Sheet"
    images = content.get("images") or []
    columns = int(content.get("columns") or 4)
    rows = int(content.get("rows") or 4)
    show_captions = bool(content.get("show_captions", True))

    page_w, page_h = pagesize
    c = canvas.Canvas(output_path, pagesize=pagesize)

    margin = 1.5 * cm
    header_h = 1.5 * cm
    grid_w = page_w - 2 * margin
    grid_h = page_h - 2 * margin - header_h
    cell_w = grid_w / columns
    cell_h = grid_h / rows
    img_pad = 4
    caption_h = 10 if show_captions else 0

    cleanup_paths = []
    per_page = columns * rows
    page_no = 0
    total_pages = max(1, (len(images) + per_page - 1) // per_page)

    def draw_header():
        c.setFillColor(brand_color)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin, page_h - margin - 6, title)
        c.setFillColor(colors.HexColor("#666666"))
        c.setFont("Helvetica", 9)
        c.drawRightString(
            page_w - margin, page_h - margin - 6,
            f"Page {page_no + 1} of {total_pages} · {len(images)} images",
        )
        c.setStrokeColor(colors.HexColor("#DDDDDD"))
        c.setLineWidth(0.5)
        c.line(margin, page_h - margin - header_h + 4, page_w - margin, page_h - margin - header_h + 4)

    while page_no * per_page < len(images) or page_no == 0:
        draw_header()
        chunk = images[page_no * per_page:(page_no + 1) * per_page]
        for idx, item in enumerate(chunk):
            row = idx // columns
            col = idx % columns
            x = margin + col * cell_w
            y = page_h - margin - header_h - (row + 1) * cell_h

            url = item.get("url") if isinstance(item, dict) else item
            caption = item.get("caption", "") if isinstance(item, dict) else ""

            path, cleanup = _resolve_image(url)
            if cleanup:
                cleanup_paths.append(cleanup)
            if path:
                try:
                    img = ImageReader(path)
                    iw, ih = img.getSize()
                    avail_w = cell_w - 2 * img_pad
                    avail_h = cell_h - 2 * img_pad - caption_h
                    scale = min(avail_w / iw, avail_h / ih)
                    draw_w = iw * scale
                    draw_h = ih * scale
                    dx = x + (cell_w - draw_w) / 2
                    dy = y + caption_h + (cell_h - caption_h - draw_h) / 2
                    c.drawImage(img, dx, dy, width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")
                except Exception:
                    c.setFillColor(colors.HexColor("#EEEEEE"))
                    c.rect(x + img_pad, y + caption_h + img_pad, cell_w - 2 * img_pad, cell_h - caption_h - 2 * img_pad, fill=1, stroke=0)
            else:
                c.setFillColor(colors.HexColor("#EEEEEE"))
                c.rect(x + img_pad, y + caption_h + img_pad, cell_w - 2 * img_pad, cell_h - caption_h - 2 * img_pad, fill=1, stroke=0)

            if show_captions and caption:
                c.setFillColor(colors.HexColor("#444444"))
                c.setFont("Helvetica", 7.5)
                text = caption[:48]
                c.drawCentredString(x + cell_w / 2, y + 2, text)

        page_no += 1
        if page_no * per_page >= len(images):
            break
        c.showPage()

    c.showPage()
    c.save()

    for p in cleanup_paths:
        try:
            os.unlink(p)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public command
# ---------------------------------------------------------------------------


def _coerce_content(content):
    if isinstance(content, str):
        try:
            return json.loads(content)
        except Exception:
            return {"about": content}
    return content or {}


def invoke_generate(request_data):
    """Generate a PDF and return it as base64 (Data URI).

    Inputs (under `params` or `inputs`):
      - template:    one of "brand-assets", "rate-card", "contact-sheet"
      - content:     dict (or JSON string) with the fields the template expects
      - filename:    optional output filename (defaults to <template>-<ts>.pdf)
      - page_size:   "A4" or "Letter" (default Letter)
      - brand_color: hex color used for accents (default "#111111")

    Returns:
      {
        "status": True,
        "data": {
          "filename": "<name>.pdf",
          "content_type": "application/pdf",
          "size_bytes": <int>,
          "page_count_estimate": <int>,
          "data_uri": "data:application/pdf;base64,...",
          "base64": "...",   # raw base64 (no Data URI prefix)
        }
      }
    """
    params = request_data.get("params") or request_data.get("inputs") or {}

    template = (params.get("template") or "brand-assets").strip()
    content = _coerce_content(params.get("content"))
    filename = params.get("filename") or f"{template}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.pdf"
    if not filename.lower().endswith(".pdf"):
        filename = filename + ".pdf"
    pagesize = _pagesize(params.get("page_size", "Letter"))
    brand_color = _hex_to_color(params.get("brand_color"), "#111111")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_path = tmp.name
    tmp.close()

    try:
        if template == "contact-sheet":
            _build_contact_sheet_canvas(content, pagesize, brand_color, tmp_path)
        else:
            doc = SimpleDocTemplate(
                tmp_path,
                pagesize=pagesize,
                leftMargin=2 * cm,
                rightMargin=2 * cm,
                topMargin=2 * cm,
                bottomMargin=2 * cm,
                title=content.get("title") or template.replace("-", " ").title(),
            )
            if template == "rate-card":
                story = _build_rate_card(content, pagesize, brand_color)
            elif template == "metrics-report":
                story = _build_metrics_report(content, pagesize, brand_color)
            else:
                story = _build_brand_assets(content, pagesize, brand_color)
            doc.build(story)

        with open(tmp_path, "rb") as f:
            pdf_bytes = f.read()

        encoded = base64.b64encode(pdf_bytes).decode("ascii")
        data_uri = f"data:application/pdf;base64,{encoded}"

        # Rough page count: count "/Type /Page" markers (not /Pages)
        try:
            page_count = pdf_bytes.count(b"/Type /Page\n") + pdf_bytes.count(b"/Type /Page ")
        except Exception:
            page_count = 0

        return {
            "status": True,
            "data": {
                "filename": filename,
                "content_type": "application/pdf",
                "size_bytes": len(pdf_bytes),
                "page_count_estimate": page_count,
                "data_uri": data_uri,
                "base64": encoded,
            },
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to generate PDF: {e}"}
    finally:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except Exception:
            pass
