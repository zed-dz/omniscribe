"""Generate educational assets from the extracted schema.

Outputs:
  * guidebook  -> PDF   (structured study guide)
  * infographic-> PDF   (visual one-pager)
  * flashcards -> PDF   (printable Q/A cards)
  * quiz       -> PDF   (multiple-choice with answer key)
  * mindmap    -> PNG   (radial concept map)

Arabic is shaped (contextual joining) and bidi-reordered per line so it renders correctly
in both ReportLab PDFs and PIL images, which otherwise have no complex-script support.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

from .. import config

# ------------------------------------------------------------------ Arabic shaping
_HAS_ARABIC = re.compile(r"[؀-ۿ]")


def _contains_arabic(text: str) -> bool:
    return bool(_HAS_ARABIC.search(text or ""))


# Map sub/superscript digits to ASCII so common notation (CO₂, x²) renders with normal fonts.
_SUBSUP = {ord(c): d for c, d in zip("₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹", "01234567890123456789")}


def shape(text: str) -> str:
    """Sanitise glyphs and shape + bidi-reorder a line for correct display."""
    if not text:
        return text
    text = text.translate(_SUBSUP)
    if not _contains_arabic(text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


# ------------------------------------------------------------------ fonts
_FONTS_REGISTERED = False
FONT_BODY = "OSBody"
FONT_BOLD = "OSBold"


def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    reg = config.FONT_REGULAR or config.FONT_ARABIC
    bold = config.FONT_BOLD or reg
    if reg:
        pdfmetrics.registerFont(TTFont(FONT_BODY, reg))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, bold))
    else:  # last resort: built-in (no Arabic, but never crashes)
        pdfmetrics.registerFont(TTFont(FONT_BODY, "Helvetica")) if False else None
    _FONTS_REGISTERED = True


def _font_or_default(name: str) -> str:
    return name if (config.FONT_REGULAR or config.FONT_ARABIC) else "Helvetica"


# ------------------------------------------------------------------ palette
PRIMARY = HexColor("#4f46e5")
PRIMARY_DK = HexColor("#3730a3")
ACCENT = HexColor("#ec4899")
INK = HexColor("#1f2937")
MUTED = HexColor("#6b7280")
CARD_BG = HexColor("#f3f4f6")
BRANCH_COLORS = ["#4f46e5", "#ec4899", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#14b8a6"]


# ------------------------------------------------------------------ flowing PDF writer
class _PDFWriter:
    """A minimal flowing layout engine on top of reportlab Canvas.

    Handles page breaks, Arabic shaping and RTL alignment, manual word wrapping.
    """

    def __init__(self, path: str, rtl: bool = False, title: str = ""):
        _register_fonts()
        self.c = rl_canvas.Canvas(path, pagesize=A4)
        self.W, self.H = A4
        self.ml = self.mr = 20 * mm
        self.mt = 20 * mm
        self.mb = 18 * mm
        self.rtl = rtl
        self.body = _font_or_default(FONT_BODY)
        self.bold = _font_or_default(FONT_BOLD)
        self.x = self.ml
        self.y = self.H - self.mt
        self.title = title
        if title:
            self.c.setTitle(title)

    @property
    def content_w(self) -> float:
        return self.W - self.ml - self.mr

    def _new_page(self):
        self.c.showPage()
        self.y = self.H - self.mt

    def ensure(self, h: float):
        if self.y - h < self.mb:
            self._new_page()

    def space(self, h: float):
        self.y -= h

    def _wrap(self, text: str, font: str, size: float, width: float) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        lines, cur = [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if self.c.stringWidth(shape(trial), font, size) <= width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def _draw_line(self, text: str, font: str, size: float, color, indent: float = 0.0):
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        disp = shape(text)
        if self.rtl:
            self.c.drawRightString(self.W - self.mr - indent, self.y, disp)
        else:
            self.c.drawString(self.ml + indent, self.y, disp)

    def text_block(self, text: str, size: float = 11, color=INK, font: str | None = None,
                   leading: float = 1.5, indent: float = 0.0, gap: float = 4):
        if not text:
            return
        font = font or self.body
        line_h = size * leading
        for para in text.split("\n"):
            for line in self._wrap(para, font, size, self.content_w - indent):
                self.ensure(line_h)
                self._draw_line(line, font, size, color, indent)
                self.y -= line_h
        self.y -= gap

    def heading(self, text: str, size: float = 16, color=PRIMARY, rule: bool = True, top_gap: float = 8):
        self.space(top_gap)
        self.ensure(size * 1.6)
        self._draw_line(text, self.bold, size, color)
        self.y -= size * 1.2
        if rule:
            self.c.setStrokeColor(HexColor("#e5e7eb"))
            self.c.setLineWidth(1)
            self.c.line(self.ml, self.y + 4, self.W - self.mr, self.y + 4)
            self.y -= 6

    def bullet(self, text: str, size: float = 11, color=INK, marker="•"):
        line_h = size * 1.5
        indent = 14
        lines = self._wrap(text, self.body, size, self.content_w - indent)
        for i, line in enumerate(lines):
            self.ensure(line_h)
            self.c.setFont(self.body, size)
            self.c.setFillColor(color)
            if self.rtl:
                if i == 0:
                    self.c.drawRightString(self.W - self.mr, self.y, marker)
                self.c.drawRightString(self.W - self.mr - indent, self.y, shape(line))
            else:
                if i == 0:
                    self.c.drawString(self.ml, self.y, marker)
                self.c.drawString(self.ml + indent, self.y, shape(line))
            self.y -= line_h
        self.y -= 2

    def cover(self, title: str, subtitle: str = ""):
        self.c.setFillColor(PRIMARY)
        self.c.rect(0, self.H - 55 * mm, self.W, 55 * mm, fill=1, stroke=0)
        self.c.setFillColor(HexColor("#ffffff"))
        # Auto-fit the title: shrink the font, then truncate (the logical text) if still too wide.
        max_w = self.W - self.ml - self.mr
        size = 26
        title = title or ""
        while size > 15 and self.c.stringWidth(shape(title), self.bold, size) > max_w:
            size -= 1
        truncated = False
        while len(title) > 8 and self.c.stringWidth(shape(title + "…"), self.bold, size) > max_w:
            title = title[:-1]
            truncated = True
        disp = shape(title + "…" if truncated else title)
        self.c.setFont(self.bold, size)
        if self.rtl:
            self.c.drawRightString(self.W - self.mr, self.H - 30 * mm, disp)
        else:
            self.c.drawString(self.ml, self.H - 30 * mm, disp)
        if subtitle:
            self.c.setFont(self.body, 12)
            self.c.setFillColor(HexColor("#e0e7ff"))
            if self.rtl:
                self.c.drawRightString(self.W - self.mr, self.H - 40 * mm, shape(subtitle))
            else:
                self.c.drawString(self.ml, self.H - 40 * mm, shape(subtitle))
        self.y = self.H - 65 * mm

    def save(self):
        self.c.save()


# ------------------------------------------------------------------ generators
def _rtl(schema: dict) -> bool:
    return schema.get("language") == "ar"


def guidebook_pdf(schema: dict, out_path: str | Path) -> str:
    out_path = str(out_path)
    rtl = _rtl(schema)
    w = _PDFWriter(out_path, rtl=rtl, title=schema.get("title", "Guidebook"))
    w.cover(schema.get("title", "Study Guidebook"), "OmniScribe · Study Guidebook")

    if schema.get("summary"):
        w.heading("Overview" if not rtl else "نظرة عامة")
        w.text_block(schema["summary"], size=11.5, color=INK)

    if schema.get("concepts"):
        w.heading("Key Concepts" if not rtl else "المفاهيم الأساسية")
        for i, c in enumerate(schema["concepts"], 1):
            w.text_block(f"{i}. {c['name']}", size=13, color=PRIMARY_DK, font=w.bold, gap=2)
            if c.get("explanation"):
                w.text_block(c["explanation"], size=11, color=INK, indent=10)
            for ex in c.get("examples", []):
                w.bullet(ex, size=10.5, color=MUTED)
            w.space(4)

    if schema.get("applications"):
        w.heading("Applications" if not rtl else "التطبيقات")
        for a in schema["applications"]:
            w.bullet(a)

    if schema.get("keyTakeaways"):
        w.heading("Key Takeaways" if not rtl else "أهم النقاط")
        for t in schema["keyTakeaways"]:
            w.bullet(t, marker="•", color=PRIMARY_DK)

    w.save()
    return out_path


def infographic_pdf(schema: dict, out_path: str | Path) -> str:
    out_path = str(out_path)
    _register_fonts()
    rtl = _rtl(schema)
    body = _font_or_default(FONT_BODY)
    bold = _font_or_default(FONT_BOLD)
    c = rl_canvas.Canvas(out_path, pagesize=A4)
    W, H = A4

    # gradient-ish header band
    c.setFillColor(PRIMARY)
    c.rect(0, H - 70 * mm, W, 70 * mm, fill=1, stroke=0)
    c.setFillColor(HexColor("#ffffff"))
    c.setFont(bold, 24)
    title = shape(schema.get("infographic", {}).get("title") or schema.get("title", "Infographic"))
    if rtl:
        c.drawRightString(W - 18 * mm, H - 35 * mm, title)
    else:
        c.drawString(18 * mm, H - 35 * mm, title)
    c.setFont(body, 12)
    c.setFillColor(HexColor("#e0e7ff"))
    if rtl:
        c.drawRightString(W - 18 * mm, H - 47 * mm, "OmniScribe · Infographic")
    else:
        c.drawString(18 * mm, H - 47 * mm, "OmniScribe · Infographic")

    # stat cards
    stats = schema.get("infographic", {}).get("stats", [])[:4]
    y = H - 95 * mm
    if stats:
        card_w = (W - 36 * mm - (len(stats) - 1) * 6 * mm) / max(1, len(stats))
        for i, st in enumerate(stats):
            x = 18 * mm + i * (card_w + 6 * mm)
            c.setFillColor(CARD_BG)
            c.roundRect(x, y, card_w, 28 * mm, 6, fill=1, stroke=0)
            c.setFillColor(PRIMARY)
            c.setFont(bold, 20)
            c.drawCentredString(x + card_w / 2, y + 16 * mm, shape(str(st.get("value", "")))[:14])
            c.setFillColor(MUTED)
            c.setFont(body, 9)
            c.drawCentredString(x + card_w / 2, y + 7 * mm, shape(str(st.get("label", "")))[:24])
        y -= 16 * mm

    # main points
    points = schema.get("infographic", {}).get("mainPoints", [])[:6]
    c.setFillColor(INK)
    for p in points:
        box_h = 22 * mm
        if y - box_h < 20 * mm:
            break
        c.setFillColor(HexColor("#ffffff"))
        c.setStrokeColor(HexColor("#e5e7eb"))
        c.roundRect(18 * mm, y - box_h, W - 36 * mm, box_h, 5, fill=1, stroke=1)
        c.setFillColor(ACCENT)
        c.circle(28 * mm if not rtl else W - 28 * mm, y - 8 * mm, 3 * mm, fill=1, stroke=0)
        c.setFillColor(PRIMARY_DK)
        c.setFont(bold, 12)
        tx = (W - 36 * mm) if rtl else 36 * mm
        draw = c.drawRightString if rtl else c.drawString
        draw(tx, y - 8 * mm, shape(str(p.get("title", "")))[:60])
        c.setFillColor(MUTED)
        c.setFont(body, 9.5)
        desc = shape(str(p.get("description", "")))[:110]
        draw(tx, y - 15 * mm, desc)
        y -= box_h + 5 * mm

    c.save()
    return out_path


def flashcards_pdf(schema: dict, out_path: str | Path) -> str:
    out_path = str(out_path)
    _register_fonts()
    rtl = _rtl(schema)
    body = _font_or_default(FONT_BODY)
    bold = _font_or_default(FONT_BOLD)
    cards = schema.get("flashcards", [])
    c = rl_canvas.Canvas(out_path, pagesize=A4)
    W, H = A4
    margin = 18 * mm
    card_h = 62 * mm
    gap = 8 * mm
    per_page = 3
    draw = c.drawRightString if rtl else c.drawString
    tx = (W - margin - 6 * mm) if rtl else (margin + 6 * mm)

    def wrap(text, font, size, width):
        words, lines, cur = text.split(), [], ""
        for wd in words:
            trial = (cur + " " + wd).strip()
            if c.stringWidth(shape(trial), font, size) <= width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        return lines

    for i, card in enumerate(cards):
        slot = i % per_page
        if slot == 0:
            if i > 0:
                c.showPage()
            c.setFillColor(MUTED)
            c.setFont(body, 9)
            c.drawCentredString(W / 2, H - 12 * mm, f"OmniScribe Flashcards — {schema.get('title','')[:50]}")
        top = H - 22 * mm - slot * (card_h + gap)
        # card
        c.setFillColor(HexColor("#fffbeb"))
        c.setStrokeColor(HexColor("#f59e0b"))
        c.setLineWidth(1.5)
        c.roundRect(margin, top - card_h, W - 2 * margin, card_h, 8, fill=1, stroke=1)
        # Q label
        c.setFillColor(ACCENT)
        c.setFont(bold, 10)
        draw(tx, top - 9 * mm, "Q" if not rtl else "س")
        c.setFillColor(INK)
        c.setFont(bold, 12)
        qy = top - 16 * mm
        for ln in wrap(card.get("question", ""), bold, 12, W - 2 * margin - 14 * mm)[:3]:
            draw(tx, qy, shape(ln))
            qy -= 6.2 * mm
        # divider
        c.setStrokeColor(HexColor("#fcd34d"))
        c.line(margin + 6 * mm, qy - 1 * mm, W - margin - 6 * mm, qy - 1 * mm)
        # A label
        c.setFillColor(PRIMARY)
        c.setFont(bold, 10)
        draw(tx, qy - 7 * mm, "A" if not rtl else "ج")
        c.setFillColor(HexColor("#374151"))
        c.setFont(body, 11)
        ay = qy - 13 * mm
        for ln in wrap(card.get("answer", ""), body, 11, W - 2 * margin - 14 * mm)[:4]:
            if ay < top - card_h + 4 * mm:
                break
            draw(tx, ay, shape(ln))
            ay -= 5.6 * mm

    if not cards:
        c.setFont(body, 12)
        c.drawCentredString(W / 2, H / 2, "No flashcards generated.")
    c.save()
    return out_path


def quiz_pdf(schema: dict, out_path: str | Path) -> str:
    out_path = str(out_path)
    rtl = _rtl(schema)
    w = _PDFWriter(out_path, rtl=rtl, title="Quiz")
    w.cover(("Quiz: " + schema.get("title", "")) if not rtl else ("اختبار: " + schema.get("title", "")),
            "OmniScribe · Self-check Quiz")
    quiz = schema.get("quiz", [])

    def letter(j: int) -> str:
        return chr(ord("A") + j) if 0 <= j < 26 else str(j + 1)

    for i, q in enumerate(quiz, 1):
        w.text_block(f"{i}. {q['question']}", size=12, color=PRIMARY_DK, font=w.bold, gap=2)
        for j, opt in enumerate(q.get("options", [])):
            w.bullet(f"{letter(j)}. {opt}", size=10.5, color=INK, marker=" ")
        w.space(6)
    # answer key
    if quiz:
        w.heading("Answer Key" if not rtl else "مفتاح الإجابات")
        key = "   ".join(
            f"{i}-{letter(q.get('answer_index', 0))}" for i, q in enumerate(quiz, 1)
        )
        w.text_block(key, size=11, color=MUTED)
    else:
        w.text_block("No quiz questions generated.", color=MUTED)
    w.save()
    return out_path


def mindmap_png(schema: dict, out_path: str | Path, size=(1600, 1100)) -> str:
    out_path = str(out_path)
    mm_data = schema.get("mindmap", {})
    central = mm_data.get("central") or schema.get("title", "Topic")
    branches = mm_data.get("branches", [])[:8]

    W, H = size
    img = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(img)

    def font(sz, bold=False):
        path = config.FONT_BOLD if bold else config.FONT_ARABIC
        try:
            return ImageFont.truetype(path or config.FONT_REGULAR, sz)
        except Exception:
            return ImageFont.load_default()

    def text_centered(cx, cy, text, fnt, fill):
        disp = shape(text)
        bbox = d.textbbox((0, 0), disp, font=fnt)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text((cx - tw / 2, cy - th / 2), disp, font=fnt, fill=fill)

    cx, cy = W / 2, H / 2
    # branches first (so lines sit under nodes)
    n = max(1, len(branches))
    radius = min(W, H) * 0.32
    f_branch = font(24, bold=True)
    f_sub = font(17)
    f_central = font(30, bold=True)

    for i, b in enumerate(branches):
        ang = (2 * math.pi * i / n) - math.pi / 2
        bx, by = cx + radius * math.cos(ang), cy + radius * math.sin(ang)
        color = BRANCH_COLORS[i % len(BRANCH_COLORS)]
        d.line([(cx, cy), (bx, by)], fill=color, width=5)
        # branch node
        name = (b.get("name") or "")[:40]
        bbox = d.textbbox((0, 0), shape(name), font=f_branch)
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = 16
        d.rounded_rectangle(
            [bx - bw / 2 - pad, by - bh / 2 - pad, bx + bw / 2 + pad, by + bh / 2 + pad],
            radius=14, fill=color,
        )
        text_centered(bx, by, name, f_branch, "#ffffff")

        # subbranches
        subs = b.get("subbranches", [])[:4]
        for j, sub in enumerate(subs):
            sub_ang = ang + (j - (len(subs) - 1) / 2) * 0.32
            sx = bx + radius * 0.62 * math.cos(sub_ang)
            sy = by + radius * 0.62 * math.sin(sub_ang)
            d.line([(bx, by), (sx, sy)], fill=color, width=2)
            label = (sub or "")[:34]
            sbbox = d.textbbox((0, 0), shape(label), font=f_sub)
            sw, sh = sbbox[2] - sbbox[0], sbbox[3] - sbbox[1]
            d.rounded_rectangle(
                [sx - sw / 2 - 8, sy - sh / 2 - 6, sx + sw / 2 + 8, sy + sh / 2 + 6],
                radius=8, fill="#ffffff", outline=color, width=2,
            )
            text_centered(sx, sy, label, f_sub, "#374151")

    # central node on top
    cname = central[:46]
    cbbox = d.textbbox((0, 0), shape(cname), font=f_central)
    cw, ch = cbbox[2] - cbbox[0], cbbox[3] - cbbox[1]
    pad = 26
    d.ellipse(
        [cx - cw / 2 - pad, cy - ch / 2 - pad, cx + cw / 2 + pad, cy + ch / 2 + pad],
        fill="#4f46e5", outline="#3730a3", width=4,
    )
    text_centered(cx, cy, cname, f_central, "#ffffff")

    # footer
    text_centered(W / 2, H - 30, "Generated by OmniScribe", font(15), "#9ca3af")
    img.save(out_path, "PNG")
    return out_path


GENERATORS = {
    "guidebook": (guidebook_pdf, "pdf"),
    "infographic": (infographic_pdf, "pdf"),
    "flashcards": (flashcards_pdf, "pdf"),
    "quiz": (quiz_pdf, "pdf"),
    "mindmap": (mindmap_png, "png"),
}
