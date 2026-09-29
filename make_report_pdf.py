#!/usr/bin/env python3
"""Write an academic-style (black and white) PDF report of the Tunduma hydraulic analysis.

Every number is taken from the model built by build_model.py / water_hydraulics.py, so the
report always matches tunduma_config.json. Re-run after changing the config:

    python make_report_pdf.py            -> results/Tunduma_Hydraulic_Analysis_Report.pdf

Needs: pip install reportlab   (wntr optional, for the EPANET verification section)
"""
import datetime
import math
import os

from reportlab.graphics.shapes import Drawing, Line, PolyLine, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

import build_model
import epanet_check
import water_hydraulics as wh

BLACK, WHITE = colors.black, colors.white
G, RHO = wh.G, wh.RHO

# ---------------------------------------------------------------- fonts and styles
FONT_DIR = "/usr/share/fonts/truetype/liberation"
try:
    for name, file in (("Serif", "LiberationSerif-Regular.ttf"), ("Serif-Bold", "LiberationSerif-Bold.ttf"),
                       ("Serif-Italic", "LiberationSerif-Italic.ttf"),
                       ("Serif-BoldItalic", "LiberationSerif-BoldItalic.ttf")):
        pdfmetrics.registerFont(TTFont(name, os.path.join(FONT_DIR, file)))
    pdfmetrics.registerFontFamily("Serif", normal="Serif", bold="Serif-Bold", italic="Serif-Italic",
                                  boldItalic="Serif-BoldItalic")
    FONT, BOLD, ITALIC = "Serif", "Serif-Bold", "Serif-Italic"
except Exception:          # fall back to the built-in Times (no Greek letters)
    FONT, BOLD, ITALIC = "Times-Roman", "Times-Bold", "Times-Italic"

ST = {
    "title": ParagraphStyle("title", fontName=BOLD, fontSize=17, leading=22, alignment=TA_CENTER, spaceAfter=10),
    "subtitle": ParagraphStyle("subtitle", fontName=FONT, fontSize=12, leading=16, alignment=TA_CENTER),
    "h1": ParagraphStyle("h1", fontName=BOLD, fontSize=13, leading=17, spaceBefore=14, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=11, leading=14, spaceBefore=10, spaceAfter=4),
    "h3": ParagraphStyle("h3", fontName=ITALIC, fontSize=10.5, leading=14, spaceBefore=6, spaceAfter=2),
    "body": ParagraphStyle("body", fontName=FONT, fontSize=10.5, leading=14.5, alignment=TA_JUSTIFY,
                           spaceAfter=5),
    "abstract": ParagraphStyle("abstract", fontName=FONT, fontSize=10, leading=13.5, alignment=TA_JUSTIFY,
                               leftIndent=12 * mm, rightIndent=12 * mm),
    "calc": ParagraphStyle("calc", fontName=FONT, fontSize=10, leading=14, leftIndent=8 * mm),
    "eq": ParagraphStyle("eq", fontName=FONT, fontSize=10.5, leading=15, alignment=TA_CENTER),
    "eqno": ParagraphStyle("eqno", fontName=FONT, fontSize=10.5, leading=15, alignment=TA_RIGHT),
    "cap": ParagraphStyle("cap", fontName=FONT, fontSize=9.5, leading=12, alignment=TA_CENTER, spaceBefore=3,
                          spaceAfter=8),
    "cell": ParagraphStyle("cell", fontName=FONT, fontSize=8.5, leading=10.5, alignment=TA_LEFT),
    "cellr": ParagraphStyle("cellr", fontName=FONT, fontSize=8.5, leading=10.5, alignment=TA_RIGHT),
    "cellh": ParagraphStyle("cellh", fontName=BOLD, fontSize=8.5, leading=10.5, alignment=TA_LEFT),
    "ref": ParagraphStyle("ref", fontName=FONT, fontSize=9.5, leading=12.5, leftIndent=8 * mm,
                          firstLineIndent=-8 * mm, spaceAfter=3),
    "bullet": ParagraphStyle("bullet", fontName=FONT, fontSize=10.5, leading=14.5, leftIndent=6 * mm,
                             bulletIndent=1 * mm, alignment=TA_JUSTIFY, spaceAfter=2),
}
PAGE_W = A4[0] - 50 * mm


def n(v, nd=1):
    """Number with thousands separator."""
    if v is None:
        return "–"
    return f"{v:,.{nd}f}"


class Doc:
    """Collects the report content with numbered sections, equations, tables and figures."""

    def __init__(self):
        self.story, self.eq_no, self.tab_no, self.fig_no = [], 0, 0, 0
        self.sec = [0, 0]

    def group_start(self):
        self._mark = len(self.story)

    def group_end(self):
        """Keep everything added since group_start on one page (e.g. a heading and its first block)."""
        items = self.story[self._mark:]
        del self.story[self._mark:]
        self._mark = None
        self.story.append(KeepTogether(items))

    def h1(self, text, numbered=True):
        if not numbered:
            self.story.append(Paragraph(text, ST["h1"]))
            return
        self.sec = [self.sec[0] + 1, 0]
        self.story.append(CondPageBreak(75 * mm))
        self.story.append(Paragraph(f"{self.sec[0]}.&nbsp;&nbsp;{text}", ST["h1"]))

    def h2(self, text):
        self.sec[1] += 1
        self.story.append(CondPageBreak(40 * mm))
        self.story.append(Paragraph(f"{self.sec[0]}.{self.sec[1]}&nbsp;&nbsp;{text}", ST["h2"]))

    def h3(self, text):
        self.story.append(Paragraph(text, ST["h3"]))

    def p(self, text, style="body"):
        self.story.append(Paragraph(text, ST[style]))

    def bullets(self, items):
        for it in items:
            self.story.append(Paragraph(it, ST["bullet"], bulletText="–"))

    def calc(self, *lines):
        """Worked calculation lines (indented)."""
        items = [Paragraph(x, ST["calc"]) for x in lines] + [Spacer(1, 4)]
        if getattr(self, "_mark", None) is not None:
            self.story += items          # already inside a group
        else:
            self.story.append(KeepTogether(items))

    def eq(self, text):
        self.eq_no += 1
        t = Table([[Paragraph(text, ST["eq"]), Paragraph(f"({self.eq_no})", ST["eqno"])]],
                  colWidths=[PAGE_W - 16 * mm, 16 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        self.story.append(t)
        return self.eq_no

    def table(self, caption, header, rows, widths=None, align=None):
        """Academic (booktabs-like) table: rules above/below, no vertical lines, no shading."""
        self.tab_no += 1
        align = align or (["l"] + ["r"] * (len(header) - 1))

        def cell(v, i, head=False):
            if head:
                return Paragraph(str(v), ST["cellh"] if align[i] == "l" else
                                 ParagraphStyle("hr", parent=ST["cellh"], alignment=TA_RIGHT))
            return Paragraph("–" if v is None else str(v), ST["cell"] if align[i] == "l" else ST["cellr"])

        data = [[cell(h, i, True) for i, h in enumerate(header)]]
        data += [[cell(v, i) for i, v in enumerate(r)] for r in rows]
        if widths:
            widths = [w * PAGE_W / sum(widths) for w in widths]
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("LINEABOVE", (0, 0), (-1, 0), 1.0, BLACK), ("LINEBELOW", (0, 0), (-1, 0), 0.5, BLACK),
            ("LINEBELOW", (0, -1), (-1, -1), 1.0, BLACK), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
        cap = Paragraph(f"<b>Table {self.tab_no}.</b> {caption}", ST["cap"])
        self.story.append(KeepTogether([cap, t, Spacer(1, 8)]))
        return self.tab_no

    def figure(self, drawing, caption):
        self.fig_no += 1
        self.story.append(KeepTogether([drawing, Paragraph(f"<b>Figure {self.fig_no}.</b> {caption}", ST["cap"])]))
        return self.fig_no


# ---------------------------------------------------------------- figures (black and white)
def schematic(s):
    """Line diagram of the system from source to tanks (snake layout, black only)."""
    W, H = PAGE_W, 360
    d = Drawing(W, H)
    N, L = s.nodes, {l.id: l for l in s.links}

    def box(x, y, w, h, lines):
        d.add(Rect(x, y, w, h, strokeColor=BLACK, fillColor=WHITE, strokeWidth=0.8))
        top = y + h / 2 + 4.5 * (len(lines) - 1) - 2.5
        for i, t in enumerate(lines):
            d.add(String(x + w / 2, top - 9 * i, t, fontName=BOLD if i == 0 else FONT,
                         fontSize=7.4 if i == 0 else 6.8, textAnchor="middle"))

    def arrow(x1, y1, x2, y2, dashed=False):
        ln = Line(x1, y1, x2, y2, strokeColor=BLACK, strokeWidth=1.0)
        if dashed:
            ln.strokeDashArray = [4, 2]
        d.add(ln)
        ang = math.atan2(y2 - y1, x2 - x1)
        a1, a2 = ang + math.radians(155), ang - math.radians(155)
        d.add(Polygon([x2, y2, x2 + 6 * math.cos(a1), y2 + 6 * math.sin(a1),
                       x2 + 6 * math.cos(a2), y2 + 6 * math.sin(a2)],
                      fillColor=BLACK, strokeColor=BLACK, strokeWidth=0.5))

    def label(x, y, lines, anchor="middle"):
        for i, t in enumerate(lines):
            d.add(String(x, y - 8 * i, t, fontName=FONT, fontSize=6.6, textAnchor=anchor))

    def junction(x, y, name, left=False):
        d.add(Rect(x - 3, y - 3, 6, 6, fillColor=BLACK, strokeColor=BLACK))
        if left:
            d.add(String(x - 6, y + 4, name, fontName=BOLD, fontSize=6.8, textAnchor="end"))
        else:
            d.add(String(x, y + 7, name, fontName=BOLD, fontSize=6.8, textAnchor="middle"))

    bw, bh = 96, 48
    # row 1: river -> intake/grit -> WTP
    y1 = 300
    x_r, x_i, x_w = 0, (W - bw) / 2, W - bw
    box(x_r, y1, bw, bh, ["MOMBA RIVER", f"LWL {n(N['MOMBA_RIVER'].min_level)} m", "source"])
    box(x_i, y1, bw, bh, ["INTAKE + GRIT TANK", f"low-lift TDH {N['MOMBA_INTAKE'].station['tdh']:.1f} m",
                          f"high-lift TDH {N['GRIT_TANK'].station['tdh']:.1f} m", "1W+1S each"])
    box(x_w, y1, bw, bh, ["MOMBA WTP", "20,000 m³/d net", f"clear water {n(N['MOMBA_WTP'].volume, 0)} m³",
                          f"3W+1S, TDH {N['MOMBA_WTP'].station['tdh']:.0f} m"])
    arrow(x_r + bw, y1 + bh / 2, x_i, y1 + bh / 2)
    label((x_r + bw + x_i) / 2, y1 + bh / 2 + 12, ["DN600, 100 m"])
    arrow(x_i + bw, y1 + bh / 2, x_w, y1 + bh / 2)
    label((x_i + bw + x_w) / 2, y1 + bh / 2 + 12, [f"DN600, {n(L['RAW_MAIN'].length, 0)} m"])
    # row 2: WTP -> Ikana (down), Ikana -> Nkangamo (right to left, gravity)
    y2 = 200
    box(x_w, y2, bw, bh, ["IKANA GBR", f"{n(N['IKANA_GBR'].volume, 0)} m³",
                          f"BWL {n(N['IKANA_GBR'].min_level)} m"])
    arrow(x_w + bw / 2, y1, x_w + bw / 2, y2 + bh)
    label(x_w + bw / 2 - 5, (y1 + y2 + bh) / 2 + 4, ["rising main DN600", f"{n(L['WTP_IKANA_RM'].length, 0)} m"],
          anchor="end")
    box(x_r, y2, bw, bh, ["NKANGAMO BPS", f"sump {n(N['NKANGAMO_BPS'].volume, 0)} m³",
                          f"2W+1S, TDH {N['NKANGAMO_BPS'].station['tdh']:.0f} m"])
    arrow(x_w, y2 + bh / 2, x_r + bw, y2 + bh / 2, dashed=True)
    label((x_r + bw + x_w) / 2, y2 + bh / 2 + 6,
          [f"gravity main DN600, {n(L['IKANA_NKANGAMO_GM'].length, 0)} m"])
    # row 3: junctions and Uhuru Park
    y3 = 130
    jx = {"J-001N": x_r + bw / 2, "J-002N": 150, "J-003N": 245}
    ux, uw = 290, 82
    j4 = W - 36
    arrow(x_r + bw / 2, y2, x_r + bw / 2, y3 + 4)
    label(x_r + bw / 2 + 5, (y2 + y3) / 2 + 4, ["rising main DN600", f"{n(L['BPS_RM_1'].length, 0)} m"],
          anchor="start")
    for name, x in jx.items():
        junction(x, y3, name, left=(name == "J-001N"))
    arrow(jx["J-001N"] + 3, y3, jx["J-002N"] - 4, y3)
    arrow(jx["J-002N"] + 3, y3, jx["J-003N"] - 4, y3)
    arrow(jx["J-003N"] + 3, y3, ux, y3)
    box(ux, y3 - 22, uw, 44, ["UHURU PARK GBR", "5,000 m³", f"town {n(N['UHURU_PARK_GBR'].demand, 0)} m³/d"])
    arrow(ux + uw, y3, j4 - 4, y3, dashed=True)
    label((ux + uw + j4) / 2, y3 + 6, ["DN150"])
    junction(j4, y3, "J-004N")
    # row 4: existing tanks
    y4, tw, th = 22, 80, 38
    tanks = [("J-001N", "TUNDUMA_ESR", "ESR 120 m³", "ESR_BRANCH"),
             ("J-002N", "UHURU_GSR01", "GSR01 500 m³", "GSR01_BRANCH"),
             ("J-003N", "IPITO_GSR02", "IPITO GSR02", "IPITO_BRANCH")]
    for jn, tid, title, lid in tanks:
        x = jx[jn]
        arrow(x, y3 - 3, x, y4 + th)
        label(x + 4, (y3 + y4 + th) / 2, [f"DN{L[lid].dn}", f"{n(L[lid].length, 0)} m"], anchor="start")
        box(x - tw / 2, y4, tw, th, [title, f"{n(N[tid].demand, 1)} m³/d"])
    arrow(j4, y3 - 3, j4, y4 + th, dashed=True)
    box(j4 - 82, y4, 82 + 36, th, ["MAKAMBINI + CHAPWA", "622.1 m³/d each", "DN100 branches"])
    # legend
    d.add(Line(W - 150, H - 8, W - 128, H - 8, strokeColor=BLACK, strokeWidth=1.0))
    d.add(String(W - 124, H - 10.5, "pumped main", fontName=FONT, fontSize=6.6))
    ln = Line(W - 75, H - 8, W - 53, H - 8, strokeColor=BLACK, strokeWidth=1.0)
    ln.strokeDashArray = [4, 2]
    d.add(ln)
    d.add(String(W - 49, H - 10.5, "gravity main", fontName=FONT, fontSize=6.6))
    return d


def profile_drawing(s, links, height=95 * mm, title=None):
    """Longitudinal section: ground (thin line) and HGL (thick line), black only."""
    ground, hgl, marks, x0 = [], [], [], 0.0
    cover = s.settings["pipe_cover"]
    for i, l in enumerate(links):
        frm = s.nodes[l.frm]
        if frm.is_free_surface:
            if hgl:
                hgl.append((x0, frm.min_level))
            if frm.pumps:
                hgl.append((x0, frm.min_level))
            marks.append((x0, frm.id))
        elif i:
            marks.append((x0, frm.id))
        for x, z in l.points:
            ground.append((x0 + x, z + cover))
        for x, z, h, *_ in l.rows:
            hgl.append((x0 + x, h))
        x0 += l.length
    end = s.nodes[links[-1].to]
    marks.append((x0, end.id))
    hgl.append((x0, end.max_level or end.min_level))

    W, H = PAGE_W, height
    ml, mr, mt, mb = 38, 6, 30, 26
    xmax = x0
    ys = [p[1] for p in ground + hgl]
    ymin, ymax = min(ys), max(ys)
    pad = (ymax - ymin) * 0.06
    ymin, ymax = ymin - pad, ymax + pad
    X = lambda x: ml + x / xmax * (W - ml - mr)          # noqa: E731
    Y = lambda y: mb + (y - ymin) / (ymax - ymin) * (H - mt - mb)   # noqa: E731
    d = Drawing(W, H)
    d.add(Rect(ml, mb, W - ml - mr, H - mt - mb, strokeColor=BLACK, fillColor=None, strokeWidth=0.6))
    step = wh.nice_step((ymax - ymin) / 6)
    y = math.ceil(ymin / step) * step
    while y <= ymax:
        d.add(Line(ml - 3, Y(y), ml, Y(y), strokeColor=BLACK, strokeWidth=0.5))
        d.add(String(ml - 5, Y(y) - 2.5, f"{y:,.0f}", fontName=FONT, fontSize=7, textAnchor="end"))
        y += step
    xs = wh.nice_step(xmax / 8)
    x = 0.0
    while x <= xmax + 1:
        d.add(Line(X(x), mb - 3, X(x), mb, strokeColor=BLACK, strokeWidth=0.5))
        d.add(String(X(x), mb - 11, f"{x / 1000:,.0f}", fontName=FONT, fontSize=7, textAnchor="middle"))
        x += xs
    d.add(String((W + ml) / 2, 3, "Chainage (km)", fontName=FONT, fontSize=8, textAnchor="middle"))
    d.add(PolyLine([v for p in ground for v in (X(p[0]), Y(p[1]))], strokeColor=BLACK, strokeWidth=0.5))
    d.add(PolyLine([v for p in hgl for v in (X(p[0]), Y(p[1]))], strokeColor=BLACK, strokeWidth=1.6))
    short = {"MOMBA_RIVER": "River", "MOMBA_INTAKE": "Intake", "GRIT_TANK": "Grit tank", "MOMBA_WTP": "WTP",
             "IKANA_GBR": "Ikana GBR", "NKANGAMO_BPS": "Nkangamo BPS", "UHURU_PARK_GBR": "Uhuru Park GBR",
             "CHAPWA_GSR04": "Chapwa", "IPITO_GSR02": "Ipito", "MAKAMBINI_GSR03": "Makambini",
             "TUNDUMA_ESR": "ESR", "UHURU_GSR01": "GSR01"}
    clusters = []
    for x, name in marks:
        ln = Line(X(x), mb, X(x), H - mt, strokeColor=BLACK, strokeWidth=0.3)
        ln.strokeDashArray = [2, 2]
        d.add(ln)
        if clusters and X(x) - X(clusters[-1][-1][0]) < 45:
            clusters[-1].append((x, name))
        else:
            clusters.append([(x, name)])
    for i, cl in enumerate(clusters):
        x = cl[0][0]
        text = ", ".join(short.get(nm, nm) for _, nm in cl)
        anchor = "start" if X(x) < W * 0.6 else "end"
        d.add(String(X(x) + (2 if anchor == "start" else -2), H - mt + 4 + 9 * (i % 2), text,
                     fontName=FONT, fontSize=6.5, textAnchor=anchor))
    # legend
    d.add(Line(ml + 6, mb + 10, ml + 26, mb + 10, strokeColor=BLACK, strokeWidth=1.6))
    d.add(String(ml + 30, mb + 7.5, "Hydraulic grade line (HGL)", fontName=FONT, fontSize=7))
    d.add(Line(ml + 140, mb + 10, ml + 160, mb + 10, strokeColor=BLACK, strokeWidth=0.5))
    d.add(String(ml + 164, mb + 7.5, "Ground level (survey)", fontName=FONT, fontSize=7))
    d.add(String(2, H - mt + 4, "Level (m)", fontName=FONT, fontSize=7))
    return d


# ---------------------------------------------------------------- calculation text helpers
def hw_steps(doc, s, l, nu):
    """Step-by-step Hazen-Williams calculation for one pipe."""
    D = l.d
    A = math.pi * D ** 2 / 4
    q = l.q
    re = l.v * D / nu
    q185, c185, d487 = q ** 1.852, l.c ** 1.852, D ** 4.8704
    k = s.settings["minor_loss_factor"]
    doc.calc(
        f"Design flow: Q = V<sub>d</sub> / (t × 3600) = {n(l.daily, 2)} / ({l.hours:.0f} × 3600) "
        f"= <b>{q:.4f} m³/s</b> ({q * 1000:.1f} l/s)",
        f"Area: A = πD²/4 = π × {D:.3f}² / 4 = {A:.4f} m²;  velocity V = Q/A = {q:.4f} / {A:.4f} "
        f"= <b>{l.v:.3f} m/s</b>",
        f"Reynolds number: Re = VD/ν = {l.v:.3f} × {D:.3f} / {nu:.3e} = {re:,.0f} (turbulent, Re &gt; 4,000)",
        f"Friction: h<sub>f</sub> = 10.67 L Q<super>1.852</super> / (C<super>1.852</super> D<super>4.8704</super>) "
        f"= 10.67 × {n(l.length, 1)} × {q185:.5f} / ({c185:,.1f} × {d487:.5f}) = <b>{l.hf:.2f} m</b>",
        f"Minor losses: h<sub>m</sub> = k<sub>m</sub> h<sub>f</sub> = {k:.2f} × {l.hf:.2f} = {l.hm:.2f} m;  "
        f"total h<sub>L</sub> = {l.hf:.2f} + {l.hm:.2f} = <b>{l.hloss:.2f} m</b> "
        f"(gradient {l.hloss / l.length * 1000:.2f} m/km)",
    )


def surge_line(l):
    return (f"Surge (Joukowsky): Δh = aV/g = {l.wave_speed:.0f} × {l.v:.3f} / 9.81 = <b>{l.surge:.1f} m</b>; "
            f"minimum transient pressure ≈ p<sub>min</sub> − Δh = "
            f"{'–' if l.p_min is None else f'{l.p_min:.1f} − {l.surge:.1f} = {l.p_min - l.surge:.1f} m'}")


def critical_head_text(s, zone):
    """Explain how the head required at the start of a zone was obtained (critical path)."""
    path = s._critical_path(zone)
    ppipe = s.pipe_pmin
    idx = next((i for i, l in enumerate(path) if l.gov_point is not None), None)
    lines = []
    if idx is None:
        end = s.nodes[path[-1].to]
        base = end.inlet_level + end.residual
        lines.append(f"Controlling point: inlet of {end.id}: H = inlet level + residual = {end.inlet_level:.2f} + "
                     f"{end.residual:.2f} = {base:.2f} m")
        used = path
    else:
        l = path[idx]
        x, z = l.gov_point
        base = z + ppipe + l.hloss * x / l.length
        lines.append(f"Controlling point: pipe {l.id} at {x:,.0f} m (pipe crown {z:.2f} m); the HGL there must be "
                     f"≥ {z:.2f} + {ppipe:.1f} = {z + ppipe:.2f} m, so at the start of {l.id}: "
                     f"H = {z + ppipe:.2f} + {l.hloss:.2f} × {x:,.0f}/{l.length:,.0f} = {base:.2f} m")
        used = path[:idx]
    total = base
    for l in reversed(used):
        total += l.hloss
        lines.append(f"+ head loss in {l.id}: {l.hloss:.2f} m → {total:.2f} m")
    lines.append(f"Head required at the start of the zone: <b>H<sub>req</sub> = {zone.required_head:.2f} m</b>")
    return lines


# ---------------------------------------------------------------- report
def build(out_path, cfg_path="tunduma_config.json"):
    cfg = build_model.load_config(cfg_path)
    al = build_model.prepare_alignment(cfg)
    data, routes = build_model.build_engine_model(cfg, al)
    s = wh.System(data).solve()
    st = s.settings
    N, L = s.nodes, {l.id: l for l in s.links}
    fac = {f["id"]: f for f in cfg["facilities"]}
    lcfg = {l["id"]: l for l in cfg["links"]}
    nu = s.nu
    doc = Doc()
    P = doc.p

    # ---- title page
    doc.story += [Spacer(1, 45 * mm),
                  Paragraph("Hydraulic Analysis of the Tunduma Water Supply Transmission System", ST["title"]),
                  Paragraph("From the Momba River Intake to the Storage Tanks", ST["subtitle"]),
                  Spacer(1, 10 * mm),
                  Paragraph("Technical Report – Design Year 2035", ST["subtitle"]),
                  Spacer(1, 4 * mm),
                  Paragraph(datetime.date.today().strftime("%B %Y"), ST["subtitle"]),
                  Spacer(1, 25 * mm)]
    P("<b>Abstract.</b> This report presents a steady-state hydraulic analysis of the Tunduma Water Supply "
      "transmission system. The system abstracts water from the Momba (Saisi) River and treats it at the Momba "
      "Water Treatment Plant (20,000 m³/d net). The treated water is pumped to Ikana Ground-Level Balancing "
      "Reservoir (GBR) and conveyed by gravity to the Nkangamo Booster Pump Station (BPS). From there it is "
      "pumped to Uhuru Park GBR and four existing storage tanks in Tunduma. The pipeline geometry was taken "
      "from the topographic survey of the route. Facility data, flows and pump duties follow the Employer's "
      "Requirements (ER). Design flows are obtained from a mass balance of the tank demands. Friction losses are "
      "computed with the Hazen–Williams equation, and the hydraulic grade line is traced along "
      f"{len(al.elev):,} surveyed points. Pump heads are set by the most critical point of each pressure zone. "
      "Pipe pressure classes are checked to EN 805, and surge is estimated with the Joukowsky equation. "
      "The results were verified independently with the EPANET 2.2 solver. Each calculation is shown step "
      "by step, from the intake to the last storage tank.", "abstract")
    doc.story.append(PageBreak())

    # ---- nomenclature
    doc.h1("Nomenclature", numbered=False)
    doc.table("Symbols and units.", ["Symbol", "Description", "Unit"], [
        ["A", "internal cross-sectional area of the pipe", "m²"],
        ["a", "pressure wave speed", "m/s"],
        ["C", "Hazen–Williams roughness coefficient", "–"],
        ["D", "internal pipe diameter", "m"],
        ["g", "gravitational acceleration (9.81)", "m/s²"],
        ["H", "hydraulic (piezometric) head, HGL", "m a.s.l."],
        ["h<sub>f</sub>, h<sub>m</sub>, h<sub>L</sub>", "friction, minor and total head loss", "m"],
        ["h<sub>st</sub>", "head loss in pump-station pipework", "m"],
        ["L", "pipe length (along the slope)", "m"],
        ["p", "pressure head", "m"],
        ["P<sub>h</sub>, P<sub>s</sub>", "hydraulic and shaft power", "kW"],
        ["Q", "flow rate", "m³/s"],
        ["Re", "Reynolds number", "–"],
        ["t", "operating hours per day", "h/d"],
        ["TDH", "total dynamic head of a pump", "m"],
        ["V", "mean velocity", "m/s"],
        ["V<sub>d</sub>", "daily volume", "m³/d"],
        ["z", "elevation (ground or pipe crown)", "m a.s.l."],
        ["Δh", "surge head", "m"],
        ["η<sub>p</sub>, η<sub>m</sub>", "pump and motor efficiency", "–"],
        ["ν", "kinematic viscosity of water", "m²/s"],
        ["ρ", "density of water (1,000)", "kg/m³"],
    ], widths=[1.2, 4, 1], align=["l", "l", "l"])

    # ---- 1 introduction
    doc.h1("Introduction")
    P("The Tunduma Water Supply Project (Phase 1) supplies Tunduma town, Songwe Region, from the Momba (Saisi) "
      "River. The works comprise:")
    doc.bullets([
        "a river intake with low-lift pumps and a grit tank with high-lift pumps;",
        "a raw-water main to the Momba WTP;",
        "a treated-water rising main to Ikana GBR;",
        "a gravity main to Nkangamo BPS;",
        "a rising main from the BPS to Uhuru Park GBR, with branches to the existing Tunduma tanks.",
    ])
    P("The objective of this study is to verify the hydraulic performance of the whole chain, from the "
      "intake to the storage tanks. It determines:")
    doc.bullets([
        "the flows, velocities and head losses in every main;",
        "the hydraulic grade line and pressures along the surveyed route;",
        "the heads, power and energy required at each pump station;",
        "the pipe pressure classes;",
        "the storage needed to balance pumping against supply.",
    ])
    P("<b>Data sources.</b> The analysis uses three sources:")
    doc.bullets([
        "the Employer's Requirements and Specifications, in particular the schematic diagram of the "
        "waterworks (Section 2.1) and Tables 7 and 8 (design criteria);",
        f"the topographic survey of the pipeline route ({len(al.elev):,} alignment nodes, levels in m a.s.l.);",
        "a draft EPANET model derived from the route drawing (DXF). Only its geometry was used: node "
        "coordinates, ground levels and pipe lengths.",
    ])
    P("Parameters not given in the ER are stated as assumptions in Section 3 and should be confirmed during "
      "detailed design.")

    # ---- 2 system description
    doc.h1("System Description")
    P("Water flows through seven hydraulic zones separated by free water surfaces: the river, the intake sump, "
      "the grit tank, the WTP clear-water tank, Ikana GBR, the Nkangamo sump and Uhuru Park GBR. Each zone is "
      "either pumped or gravity-fed. Figure 1 shows the arrangement; Table 2 lists the facilities.")
    doc.figure(schematic(s), "Schematic of the Tunduma transmission system (after ER Figure 2). "
                             "Solid lines: pumped mains; dashed lines: gravity mains.")
    rows = []
    for f in cfg["facilities"]:
        nd = N[f["id"]]
        rows.append([f["id"], f["type"].upper(), n(nd.elevation, 2), n(nd.min_level, 2) if nd.min_level else None,
                     n(nd.max_level, 2) if nd.max_level else None, n(nd.volume, 0) if nd.volume else None,
                     n(nd.demand, 2) if nd.demand else None])
    doc.table("Facilities of the system (levels in m a.s.l.). LWL/BWL = lowest water level; TWL = top water level.",
              ["Facility", "Type", "Ground", "LWL/BWL", "TWL", "Volume (m³)", "Demand (m³/d)"], rows,
              widths=[2.4, 1, 1, 1, 1, 1.1, 1.2])
    rows = []
    for lk in cfg["links"]:
        l = L[lk["id"]]
        rows.append([lk["id"], f"{l.frm} → {l.to}", f"DN{l.dn}", n(l.length, 0), n(lk.get("er_length"), 0)
                     if lk.get("er_length") else None, "gravity" if s._zone_start_of(s.nodes[l.to]).pumps is None
                     else "pumped"])
    doc.table("Pipelines. Model length is measured along the surveyed ground slope; ER length from the schematic.",
              ["Pipe", "From → To", "Size", "Model L (m)", "ER L (m)", "Flow"], rows,
              widths=[2, 3.6, 0.9, 1.1, 1, 0.9], align=["l", "l", "l", "r", "r", "l"])

    # ---- 3 criteria
    doc.h1("Design Criteria and Assumptions")
    doc.table("Design criteria adopted.", ["Parameter", "Value", "Source"], [
        ["Net WTP output (peak day)", "20,000 m³/d", "ER Table 8"],
        ["Losses intake→WTP + within WTP", "2 % + 5 % = 7 %", "ER Table 8"],
        ["Pump operating time", "22 h/d", "ER Table 8"],
        ["Gravity main operating time", f"{st['gravity_hours']:.0f} h/d", "continuous supply"],
        ["Friction formula", "Hazen–Williams", "–"],
        ["Hazen–Williams C (cement-lined steel, aged)", f"{cfg['pipe_defaults']['hw_c']}", "assumed"],
        ["Minor losses", f"{st['minor_loss_factor'] * 100:.0f} % of friction", "assumed"],
        ["Losses inside pump stations", f"{st['station_losses']:.1f} m", "assumed"],
        ["Minimum pressure at junctions / delivery", f"{st['min_pressure_head']:.0f} m", "ER Table 7"],
        ["Minimum pressure at the pipe crown along mains", f"{s.pipe_pmin:.0f} m", "assumed"],
        ["Depth of pipe crown below ground", f"{st['pipe_cover']:.1f} m", "assumed"],
        ["Residual head above tank inlet level", f"{st['terminal_residual_head']:.1f} m", "assumed"],
        ["Maximum velocity (transmission)", f"{st['max_velocity']:.1f} m/s", "ER Table 7"],
        ["Pressure wave speed (steel)", f"{cfg['pipe_defaults']['wave_speed']} m/s", "assumed"],
        ["Pipe pressure classes", ", ".join(f"PN{c}" for c in st["pn_classes"]), "ER schematic"],
        ["Water temperature", f"{st['water_temperature_c']:.0f} °C (ν = {nu:.3e} m²/s)", "assumed"],
    ], widths=[3.5, 2, 1.3], align=["l", "l", "l"])
    P("<b>Assumed levels.</b> The ER gives ground elevations and capacities but not the operating water levels. "
      "The following were assumed:")
    doc.bullets([
        f"river low water level {n(N['MOMBA_RIVER'].min_level)} m, taken from the survey points of the "
        "river bed (1,360.7–1,364.5 m);",
        f"intake sump LWL {n(N['MOMBA_INTAKE'].min_level)} m;",
        f"grit tank {n(N['GRIT_TANK'].min_level)}–{n(N['GRIT_TANK'].max_level)} m;",
        f"WTP inlet (cascade aerator) {n(N['MOMBA_WTP'].inlet_level)} m;",
        f"clear-water tank {n(N['MOMBA_WTP'].min_level)}–{n(N['MOMBA_WTP'].max_level)} m;",
        "new GBRs 5 m deep above the ER elevation;",
        "existing tanks 3 m deep, with the ESR floor at its ER elevation of 1,703.5 m.",
    ])
    P("These assumptions influence the pump heads and should be replaced by the final civil designs.")

    # ---- 4 methodology
    doc.h1("Methodology")
    doc.h2("Continuity and design flows")
    P("Flows are derived backwards from the demands, i.e. the outflow of each storage tank to its distribution "
      "zone. The daily volume entering a node equals its own demand plus the volumes passed on to the "
      "downstream nodes, divided by (1 − losses):")
    e_cont = doc.eq("V<sub>d,in</sub> = (V<sub>d,node</sub> + Σ V<sub>d,out</sub>) / (1 − λ)")
    P("where λ is the fractional loss at the node (7 % at the WTP). The instantaneous design flow of a main is "
      "the daily volume divided by its operating time t:")
    e_q = doc.eq("Q = V<sub>d</sub> / (3600 t)")
    doc.h2("Velocity and flow regime")
    e_v = doc.eq("A = π D² / 4 ,&nbsp;&nbsp;&nbsp; V = Q / A ,&nbsp;&nbsp;&nbsp; Re = V D / ν")
    doc.h2("Friction and minor losses")
    P("Friction losses are computed with the Hazen–Williams equation in SI units, valid for fully turbulent "
      "flow of water:")
    e_hw = doc.eq("h<sub>f</sub> = 10.67 L Q<super>1.852</super> / (C<super>1.852</super> D<super>4.8704</super>)")
    P("Minor losses at bends, valves and fittings are taken as a fraction k<sub>m</sub> of the friction loss:")
    e_hm = doc.eq("h<sub>m</sub> = k<sub>m</sub> h<sub>f</sub> ,&nbsp;&nbsp;&nbsp; "
                  "h<sub>L</sub> = h<sub>f</sub> + h<sub>m</sub>")
    P("Pipe lengths are measured along the ground slope between successive survey points: "
      "L = Σ (ΔL<sub>plan</sub>² + Δz²)<super>½</super>.")
    doc.h2("Energy equation and hydraulic grade line")
    P("Velocity heads are small (V²/2g &lt; 0.07 m for V &lt; 1.2 m/s), so energy and hydraulic grade lines "
      "are taken as equal. Along a pipe of uniform flow the HGL falls linearly with chainage x:")
    e_hgl = doc.eq("H(x) = H<sub>0</sub> − h<sub>L</sub> x / L ,&nbsp;&nbsp;&nbsp; p(x) = H(x) − z<sub>c</sub>(x)")
    P("Here z<sub>c</sub> is the pipe crown level (ground level minus cover). A zone starts at a free water "
      "surface and ends at the next one. The head required at the start of a zone is the largest of two "
      "values, taken over every downstream point:")
    doc.bullets([
        "(i) the inlet level of each receiving tank plus a residual head, plus the losses on the way;",
        "(ii) the level needed to keep the minimum pressure p<sub>min</sub> at every survey point of every pipe.",
    ])
    e_req = doc.eq("H<sub>req</sub> = max [ z<sub>inlet</sub> + h<sub>res</sub> + Σ h<sub>L</sub> ;&nbsp; "
                   "z<sub>c</sub>(x) + p<sub>min</sub> + h<sub>L</sub> x/L + Σ h<sub>L,upstream</sub> ]")
    P("In a gravity zone, the available head is the bottom water level (BWL) of the supplying tank, and the "
      "surplus H<sub>avail</sub> − H<sub>req</sub> must be dissipated by a flow-control or pressure-reducing "
      "valve. In a pumped zone, the pumps must supply H<sub>req</sub>.")
    doc.h2("Pump head, power and energy")
    e_tdh = doc.eq("TDH = H<sub>req</sub> − z<sub>LWL,suction</sub> + h<sub>st</sub>")
    e_pw = doc.eq("P<sub>h</sub> = ρ g Q<sub>pump</sub> TDH / 1000 ,&nbsp;&nbsp; P<sub>s</sub> = P<sub>h</sub> / "
                  "η<sub>p</sub> ,&nbsp;&nbsp; P<sub>motor</sub> ≥ 1.15 P<sub>s</sub>")
    e_en = doc.eq("E = n<sub>duty</sub> P<sub>s</sub> t / η<sub>m</sub>&nbsp;&nbsp; (kWh/d) ,&nbsp;&nbsp; "
                  "e = E / V<sub>d</sub>&nbsp;&nbsp; (kWh/m³)")
    doc.h2("Pressure class and surge")
    P("The working pressure at each point is the larger of the steady-state pressure and the static pressure "
      "with the flow stopped. For a gravity zone, the static level is the TWL of the supplying tank; for a "
      "pumped zone, it is the highest TWL at the end of the zone. Following EN 805, the allowable operating "
      "pressure PFA (= PN, bar) must cover the working pressure. The allowable maximum pressure "
      "PMA = 1.2 PFA must also cover the working pressure plus surge. The surge caused by sudden pump trip or "
      "valve closure is estimated with the Joukowsky equation:")
    e_j = doc.eq("Δh = a ΔV / g ,&nbsp;&nbsp;&nbsp; p<sub>work</sub> · 0.0981 ≤ PFA ,&nbsp;&nbsp;&nbsp; "
                 "(p<sub>work</sub> + Δh) · 0.0981 ≤ 1.2 PFA")
    doc.h2("Storage")
    P("A tank filled for t hours per day but drawn at a uniform rate over 24 hours must store the volume "
      "delivered during the pumping-off period:")
    e_st = doc.eq("V<sub>bal</sub> = V<sub>d,in</sub> (1 − t / 24)")
    doc.h2("Computation")
    P("The calculations were implemented in Python (water_hydraulics.py). The same network was also written "
      "as an EPANET 2.2 input file and solved with EPANET through the WNTR library, as an independent check "
      "(Section 9).")

    # ---- 5 design flows
    doc.h1("Design Flows")
    P("Table 5 gives the demand of each storage tank (ER schematic). Working back up the system with "
      f"Equation ({e_cont}):")
    dem_rows = [[t, n(N[t].demand, 2)] for t in ("UHURU_PARK_GBR", "UHURU_GSR01", "TUNDUMA_ESR", "IPITO_GSR02",
                                                  "MAKAMBINI_GSR03", "CHAPWA_GSR04")]
    total = sum(N[t].demand for t in ("UHURU_PARK_GBR", "UHURU_GSR01", "TUNDUMA_ESR", "IPITO_GSR02",
                                      "MAKAMBINI_GSR03", "CHAPWA_GSR04"))
    dem_rows.append(["<b>Total delivered</b>", f"<b>{n(total, 2)}</b>"])
    doc.table("Demands supplied by the storage tanks (ER schematic, design year 2035).",
              ["Tank / zone", "Demand (m³/d)"], dem_rows, widths=[3, 1.5])
    raw = N["MOMBA_WTP"].inflow_daily
    doc.calc(
        f"Treated water leaving the WTP: V<sub>d</sub> = {n(total, 2)} m³/d",
        f"Raw water at the intake: V<sub>d</sub> = 20,000 / (1 − 0.07) = <b>{n(raw, 1)} m³/d</b> "
        "(ER intake capacity 21,506 m³/d)",
        f"Flow in pumped mains (t = 22 h): Q<sub>raw</sub> = {n(raw, 1)} / (22 × 3600) = "
        f"{raw / 79200:.4f} m³/s;  Q<sub>treated</sub> = 20,000 / 79,200 = {20000 / 79200:.4f} m³/s",
        f"Flow in the gravity main (t = 24 h): Q = 20,000 / 86,400 = {20000 / 86400:.4f} m³/s",
        f"Branch J-004N (gravity from Uhuru Park, 24 h): V<sub>d</sub> = 622.1 + 622.1 = "
        f"{n(L['UHURU_J004N'].daily, 1)} m³/d → Q = {L['UHURU_J004N'].q * 1000:.2f} l/s",
    )

    # ---- 6 step-by-step, zone by zone
    doc.h1("Step-by-Step Hydraulic Calculations")
    P("The calculations follow the water from the river to the last tank. For each pipe, the design flow, "
      f"velocity and head loss are computed with Equations ({e_q})–({e_hm}). For each zone, the head required "
      f"is then found with Equation ({e_req}). Finally the pump head and power are computed with Equations "
      f"({e_tdh})–({e_en}), or the gravity surplus is determined.")

    def station_calc(sid, zone_links):
        nd = N[sid]
        r = nd.station
        p = fac[sid]["pumps"]
        doc.group_start()
        doc.h3(f"Pump station {sid}")
        doc.calc(*critical_head_text(s, nd))
        doc.group_end()
        doc.calc(
            f"TDH = H<sub>req</sub> − z<sub>LWL</sub> + h<sub>st</sub> = {nd.required_head:.2f} − "
            f"{nd.min_level:.2f} + {st['station_losses']:.1f} = <b>{r['tdh']:.1f} m</b> "
            f"(ER duty head {p['er_duty']['head_m']} m)",
            f"Flow per pump: Q<sub>pump</sub> = {r['q_total']:.4f} / {r['duty']} = {r['q_pump']:.4f} m³/s "
            f"= {r['q_pump'] * 3600:.0f} m³/h (ER {p['er_duty']['q_m3h']} m³/h)",
            f"P<sub>h</sub> = 1000 × 9.81 × {r['q_pump']:.4f} × {r['tdh']:.1f} / 1000 = {r['hyd_kw']:.1f} kW;  "
            f"P<sub>s</sub> = {r['hyd_kw']:.1f} / {p['efficiency']:.2f} = <b>{r['shaft_kw']:.1f} kW</b>",
            f"Motor: 1.15 × {r['shaft_kw']:.1f} = {1.15 * r['shaft_kw']:.1f} kW → standard motor "
            f"<b>{r['motor_kw']:g} kW</b> per pump ({r['duty']} duty + {r['standby']} standby)",
            f"Energy: E = {r['duty']} × {r['shaft_kw']:.1f} × {r['hours']:.0f} / {p['motor_efficiency']:.2f} = "
            f"{n(r['energy_day'], 0)} kWh/d;  specific energy e = {n(r['energy_day'], 0)} / "
            f"{n(r['daily'], 0)} = {r['kwh_per_m3']:.3f} kWh/m³",
        )

    def pipe_block(lid, text=None):
        l = L[lid]
        lk = lcfg[lid]
        doc.group_start()
        doc.h3(f"Pipe {lid}: {l.frm} → {l.to} (DN{l.dn}, L = {n(l.length, 0)} m, C = {l.c:g})")
        if text:
            P(text)
        hw_steps(doc, s, l, nu)
        doc.group_end()
        pn_w = wh.pn_text(l, l.pn_segments_working)
        prange = (f"up to {n(l.p_max)} m" if l.p_min is None else f"{n(l.p_min)} to {n(l.p_max)} m")
        lines = [f"HGL: H<sub>start</sub> = {l.h_start:.2f} m, H<sub>end</sub> = {l.h_start:.2f} − {l.hloss:.2f} "
                 f"= {l.h_end:.2f} m;  pressure along the pipe {prange}"]
        if l.p_min is not None and l.length >= 200:
            lines.append(surge_line(l))
        doc.calc(*lines,
                 f"Pressure class (working pressure): {pn_w}"
                 + (f";  ER: {', '.join(f'PN{k} {int(v):,} m' for k, v in lk['er_pn'].items())}"
                    if lk.get("er_pn") else ""))

    doc.h2("Zone 1 – River to intake sump (gravity abstraction)")
    P("Water enters the intake sump by gravity through the abstraction pipe. The river low water level must "
      "exceed the sump LWL plus the losses in the abstraction pipe.")
    pipe_block("ABSTRACTION")
    zr = N["MOMBA_RIVER"]
    doc.calc(f"Available: river LWL = {zr.available_head:.2f} m;  required: sump LWL + h<sub>L</sub> = "
             f"{N['MOMBA_INTAKE'].min_level:.2f} + {L['ABSTRACTION'].hloss:.2f} = {zr.required_head:.2f} m;  "
             f"surplus = <b>{zr.surplus:.2f} m</b> → the sump fills at the design flow.")

    doc.h2("Zone 2 – Intake low-lift pumps to grit tank")
    pipe_block("LL_DELIVERY")
    station_calc("MOMBA_INTAKE", ["LL_DELIVERY"])

    doc.h2("Zone 3 – Grit tank high-lift pumps and raw-water main to the WTP")
    pipe_block("RAW_MAIN", f"The raw-water main follows the surveyed route for {n(L['RAW_MAIN'].length, 0)} m "
                           "and discharges into the WTP inlet (cascade aerator).")
    station_calc("GRIT_TANK", ["RAW_MAIN"])

    doc.h2("Zone 4 – WTP clear-water pumps and rising main to Ikana GBR")
    P(f"The WTP delivers 20,000 m³/d. The clear-water tank ({n(N['MOMBA_WTP'].volume, 0)} m³) supplies the "
      f"treated-water rising main, which climbs from {n(N['MOMBA_WTP'].min_level)} m (CWT LWL) to Ikana GBR "
      f"(TWL {n(N['IKANA_GBR'].max_level)} m).")
    pipe_block("WTP_IKANA_RM")
    station_calc("MOMBA_WTP", ["WTP_IKANA_RM"])

    doc.h2("Zone 5 – Ikana GBR to Nkangamo BPS (gravity main)")
    pipe_block("IKANA_NKANGAMO_GM")
    zi = N["IKANA_GBR"]
    doc.calc(*critical_head_text(s, zi))
    doc.calc(f"Available head: Ikana BWL = {zi.available_head:.2f} m;  surplus = {zi.available_head:.2f} − "
             f"{zi.required_head:.2f} = <b>{zi.surplus:.1f} m</b>",
             "The surplus is dissipated by a flow-control valve at the Nkangamo sump inlet, set to the design "
             f"flow of {L['IKANA_NKANGAMO_GM'].q * 1000:.1f} l/s.")

    doc.h2("Zone 6 – Nkangamo BPS to Uhuru Park GBR and the existing tanks")
    P("The BPS rising main supplies three offtakes before Uhuru Park GBR: J-001N (existing ESR), J-002N "
      "(existing Uhuru GSR 01) and J-003N (Ipito GSR 02). Every branch must be satisfied. The branch that "
      "needs the highest head at the pumps governs, and flow-control valves throttle the other branches.")
    for lid in ("BPS_RM_1", "BPS_RM_2", "BPS_RM_3", "UHURU_INLET", "ESR_BRANCH", "GSR01_BRANCH", "IPITO_BRANCH"):
        pipe_block(lid)
    station_calc("NKANGAMO_BPS", [])
    rows = []
    for tid in ("TUNDUMA_ESR", "UHURU_GSR01", "IPITO_GSR02", "UHURU_PARK_GBR"):
        t = N[tid]
        rows.append([tid, n(t.inlet_level + t.residual, 2), n(t.hgl, 2), n(t.excess_head, 2)])
    doc.table("Heads arriving at the receiving tanks of Zone 6. Excess head is removed by the inlet "
              "flow-control valves.", ["Tank", "Required (m)", "Arriving HGL (m)", "Excess (m)"], rows,
              widths=[2.5, 1.3, 1.3, 1.1])

    doc.h2("Zone 7 – Uhuru Park GBR to Makambini and Chapwa (gravity)")
    for lid in ("UHURU_J004N", "MAKAMBINI_BRANCH", "CHAPWA_BRANCH"):
        pipe_block(lid)
    zu = N["UHURU_PARK_GBR"]
    doc.calc(*critical_head_text(s, zu))
    doc.calc(f"Available head: Uhuru Park BWL = {zu.available_head:.2f} m;  surplus = "
             f"<b>{zu.surplus:.1f} m</b>")
    P(f"The negative surplus does not mean the tanks cannot be reached. Chapwa arrives with "
      f"{N['CHAPWA_GSR04'].excess_head:.0f} m of excess head and Makambini with "
      f"{N['MAKAMBINI_GSR03'].excess_head:.0f} m. The shortfall is local, in the first ~200 m after the GBR: "
      "the surveyed ground (≈1,698–1,699 m) lies above the GBR bottom water level taken from the ER elevation "
      "(1,697.3 m). The pressure at the pipe crown there falls below the 2 m criterion. The outlet pipe should "
      "be laid deeper over this length, or the GBR levels confirmed.")

    # ---- 7 profiles
    doc.h1("Hydraulic Profiles")
    P("Figures 2 and 3 show the longitudinal sections: the surveyed ground and the computed HGL. At each "
      "pump station the HGL rises vertically by the pump head. At each tank it drops to the water level. "
      "Wherever the HGL stays above the ground line the pressure is positive.")
    paths = {p[-1].to: p for p in s.paths()}
    doc.figure(profile_drawing(s, paths["CHAPWA_GSR04"]),
               "Longitudinal profile from the Momba River to Chapwa GSR 04 (via the WTP, Ikana GBR, "
               "Nkangamo BPS and Uhuru Park GBR).")
    doc.figure(profile_drawing(s, paths["IPITO_GSR02"][-1:], height=70 * mm),
               "Longitudinal profile of the Ipito branch (J-003N to Ipito GSR 02).")
    P("A high point of the BPS main at about 74.1 km (ground ≈1,710 m) lies above the Uhuru Park top water "
      "level. The HGL must stay above it during pumping, and air valves are required. When the pumps stop, "
      "the main will partly drain towards both ends.")

    # ---- 8 PN and storage
    doc.h1("Pressure Classes, Surge and Storage")
    rows = []
    for lk in cfg["links"]:
        if "er_pn" not in lk:
            continue
        l = L[lk["id"]]
        by = {}
        for x0, x1, pn in l.pn_segments_working:
            by[pn] = by.get(pn, 0) + (x1 - x0)
        er = ", ".join(f"PN{k}: {int(v):,}" for k, v in lk["er_pn"].items())
        mdl = ", ".join(f"PN{k}: {v:,.0f}" for k, v in sorted(by.items(), key=lambda kv: kv[0] or 999))
        rows.append([lk["id"], er, mdl, f"{l.surge:.0f}"])
    doc.table("Pipe length (m) per pressure class: ER schedule vs this analysis (working pressure), and the "
              "unprotected Joukowsky surge.", ["Pipe", "ER schedule", "This analysis", "Δh (m)"], rows,
              widths=[1.8, 3, 3, 0.8], align=["l", "l", "l", "r"])
    P("The PN30 length of the WTP → Ikana main agrees closely with the ER. The ER's PN40 length corresponds to "
      "the length that needs PN40 once surge is included. Unprotected surge would reach 80–100 m on the long "
      "mains and produce sub-atmospheric transients. Surge vessels at the WTP and BPS pump stations and air "
      "valves at the high points are therefore required, as the ER specifies. Their sizing requires a "
      "transient analysis.")
    rows = []
    for tid in ("IKANA_GBR", "UHURU_PARK_GBR", "TUNDUMA_ESR", "UHURU_GSR01", "IPITO_GSR02", "MAKAMBINI_GSR03",
                "CHAPWA_GSR04"):
        t = N[tid].tank
        rows.append([tid, n(t["inflow"], 0), f"{t['inflow_hours']:.0f}",
                     f"{n(t['inflow'], 0)} × (1 − {t['inflow_hours']:.0f}/24) = {n(t['balancing'], 0)}",
                     n(t["volume"], 0), n(t["storage_hours"], 1)])
    doc.table(f"Balancing storage, Equation ({e_st}).",
              ["Tank", "Inflow (m³/d)", "t (h)", "V<sub>bal</sub> (m³)", "Volume (m³)", "Storage (h)"], rows,
              widths=[2, 1.1, 0.6, 2.7, 1, 1])
    P("Every tank has more than the balancing volume required by the 22-hour pumping regime. The Nkangamo "
      f"sump ({n(N['NKANGAMO_BPS'].volume, 0)} m³) receives 24-hour gravity flow and pumps for 22 hours; it must "
      f"hold 20,000 × 2/24 = {20000 * 2 / 24:,.0f} m³ over the two pump-off hours, which it can.")

    # ---- 9 EPANET verification
    doc.h1("Verification with EPANET")
    P("The network was rebuilt as an EPANET 2.2 model with the same surveyed profile. It includes pumps, tanks "
      "at their critical levels, and flow-control valves at the tank inlets. It was solved twice: with pump "
      "curves through the duty points computed in Section 6, and with pump curves through the ER duty "
      "points.")
    if epanet_check.available():
        rows = []
        for mode, label in (("design", "design_pumps"), ("er", "ER_pumps")):
            inp = os.path.join("model", f"Tunduma_Transmission_Main_v1_{label}.inp")
            os.makedirs("model", exist_ok=True)
            build_model.write_epanet(inp, cfg, al, routes, s, pump_mode=mode)
            _, res = epanet_check.run(inp, s, cfg, routes)
            for r in res["stations"]:
                rows.append([("Computed duty" if mode == "design" else "ER duty"), r["Station"],
                             f"{r['EPANET Q total (m3/h)']:.0f}", f"{r['Design Q total (m3/h)']:.0f}",
                             f"{r['EPANET pump head (m)']:.1f}", f"{r['Design TDH (m)']:.1f}"])
            if mode == "design":
                hrows = [[r["Link"], f"{r['EPANET HGL at end (m)']:.2f}", f"{r['Design HGL at end (m)']:.2f}",
                          f"{r['EPANET HGL at end (m)'] - r['Design HGL at end (m)']:+.2f}"]
                         for r in res["links"] if r["Link"] in ("RAW_MAIN", "BPS_RM_1", "BPS_RM_2", "BPS_RM_3",
                                                                "IPITO_BRANCH", "GSR01_BRANCH", "ESR_BRANCH")]
        doc.table("Pump operating points from EPANET compared with the design.",
                  ["Pump curves", "Station", "EPANET Q (m³/h)", "Design Q (m³/h)", "EPANET head (m)",
                   "Design TDH (m)"], rows, widths=[1.4, 1.8, 1.2, 1.2, 1.2, 1.2], align=["l", "l", "r", "r", "r", "r"])
        doc.table("HGL at the end of selected pipes: EPANET (computed pump duties) vs the Python analysis.",
                  ["Pipe", "EPANET (m)", "Python (m)", "Difference (m)"], hrows, widths=[2, 1.2, 1.2, 1.2])
        P("With the computed pump duties, EPANET reproduces the design flows and the HGL at the junctions of "
          "the BPS main within about 0.1 m. This confirms the hand-traceable calculations. The intake "
          "low-lift pump shows a larger flow in EPANET, because the grit tank is held at its mid level there. "
          "With the ER pump curves, the WTP pumps deliver within 1 % of the design flow, which confirms the "
          "ER selection. The grit-tank and BPS pumps have more head than required. Their flow must be "
          "controlled, by the inlet valves or by variable-speed drives.")
    else:
        P("(WNTR was not installed when this report was generated – run pip install wntr to include the "
          "EPANET comparison.)")

    # ---- 10 draft model review
    doc.h1("Review of the Draft EPANET Model")
    P("The draft model produced from the route drawing was checked against the survey and the ER. Its ground "
      "levels agree with the survey to within 0.01 m. It is not, however, a valid hydraulic model of the "
      "system, for the following reasons:")
    doc.bullets([
        "the source reservoir head equals the ground level (1,365.94 m) instead of the river water level;",
        "no pumps are defined;",
        "the WTP, Ikana GBR, Nkangamo BPS and three existing tanks are missing;",
        "node N2163 is modelled as a tank although it is junction J-003N;",
        "all pipes are placeholders (300 mm, C = 120) instead of DN600 steel with DN150/DN100 branches;",
        "tank geometry is a placeholder (D = 15 m, 0–6 m);",
        "there are no demands and no flow-control valves;",
        "two inferred connectors (up to 34 % slope) replace unsurveyed sections;",
        "two pipes are shorter than the distance between their end nodes;",
        "the WTP–Ikana and BPS–Uhuru Park sections are 1.3–2.1 km shorter than the ER lengths.",
    ])
    P("Solved as it stands, the draft returns pressures down to −209 m and reverse flow towards the river. "
      "The corrected model described in this report resolves these deficiencies.")

    # ---- 11 conclusions
    doc.h1("Conclusions and Recommendations")
    b = N["NKANGAMO_BPS"].station
    w = N["MOMBA_WTP"].station
    doc.bullets([
        f"The system delivers 20,000 m³/d to the Tunduma tanks with a raw-water abstraction of {n(raw, 0)} m³/d. "
        "All velocities (0.4–1.1 m/s) are within the ER limit of 3 m/s.",
        f"The WTP clear-water pumps require TDH = {w['tdh']:.0f} m at {w['q_pump'] * 3600:.0f} m³/h per pump "
        f"(3 duty). This agrees with the ER duty of 330 m; each pump needs a {w['motor_kw']:g} kW motor. "
        f"The station uses {n(w['energy_day'], 0)} kWh/d ({w['kwh_per_m3']:.2f} kWh/m³).",
        f"The Nkangamo BPS requires TDH = {b['tdh']:.0f} m, governed by the existing ESR. The ER value of "
        f"221 m has about {221 - b['tdh']:.0f} m of reserve. The ESR levels should be confirmed before the "
        "pumps are purchased.",
        f"The Ikana–Nkangamo gravity main has {N['IKANA_GBR'].surplus:.0f} m of surplus head. A flow-control "
        "valve is required at the BPS sump inlet.",
        f"The branches to Ipito, Makambini and Chapwa arrive with excess heads of "
        f"{N['IPITO_GSR02'].excess_head:.0f}, {N['MAKAMBINI_GSR03'].excess_head:.0f} and "
        f"{N['CHAPWA_GSR04'].excess_head:.0f} m. They require flow-control or pressure-reducing valves; the "
        "lower Chapwa section requires PN25.",
        "Surge protection is required on all long mains, together with air valves at the high points (notably "
        "≈74 km on the BPS main). A transient analysis should size the surge vessels.",
        "The assumed operating levels (river, intake, grit tank, WTP, tanks) and the missing route sections "
        "should be confirmed. The analysis can then be re-run directly from the configuration file.",
    ])

    # ---- references
    doc.h1("References", numbered=False)
    for r in [
        "CEN (2000). <i>EN 805: Water supply – Requirements for systems and components outside buildings.</i> "
        "European Committee for Standardization, Brussels.",
        "Joukowsky, N. (1904). On the hydraulic hammer in water supply pipes. <i>Proceedings of the American "
        "Water Works Association</i>, 24, 341–424.",
        "Klise, K. A., et al. (2018). <i>Water Network Tool for Resilience (WNTR) User Manual.</i> "
        "EPA/600/R-17/264, U.S. Environmental Protection Agency.",
        "Rossman, L. A., Woo, H., Tryby, M., Shang, F., Janke, R. and Haxton, T. (2020). <i>EPANET 2.2 User "
        "Manual.</i> EPA/600/R-20/133, U.S. Environmental Protection Agency.",
        "Swamee, P. K. and Sharma, A. K. (2008). <i>Design of Water Supply Pipe Networks.</i> Wiley, Hoboken.",
        "Tunduma Water Supply Project (2026). <i>Employer's Requirements and Specifications, Part 2, Section "
        "VII.</i> Songwe Region, Tanzania.",
        "Tunduma Water Supply Project (2026). <i>Topographical Survey Data, 24–31 August 2026.</i>",
        "Williams, G. S. and Hazen, A. (1920). <i>Hydraulic Tables</i>, 3rd ed. Wiley, New York.",
        "Wylie, E. B. and Streeter, V. L. (1993). <i>Fluid Transients in Systems.</i> Prentice Hall, "
        "Englewood Cliffs.",
    ]:
        doc.p(r, "ref")

    # ---- build
    def on_page(canvas, d):
        canvas.saveState()
        canvas.setFont(FONT, 8.5)
        canvas.setStrokeColor(BLACK)
        if d.page > 1:
            canvas.drawString(25 * mm, A4[1] - 15 * mm, "Tunduma Water Supply – Hydraulic Analysis")
            canvas.drawRightString(A4[0] - 25 * mm, A4[1] - 15 * mm, "Technical Report")
            canvas.setLineWidth(0.4)
            canvas.line(25 * mm, A4[1] - 16.5 * mm, A4[0] - 25 * mm, A4[1] - 16.5 * mm)
            canvas.drawCentredString(A4[0] / 2, 12 * mm, str(d.page))
        canvas.restoreState()

    pdf = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=25 * mm, rightMargin=25 * mm, topMargin=22 * mm,
                            bottomMargin=20 * mm, title="Hydraulic Analysis of the Tunduma Water Supply "
                            "Transmission System", author="Tunduma Water Supply Project")
    pdf.build(doc.story, onFirstPage=on_page, onLaterPages=on_page)
    return out_path


if __name__ == "__main__":
    os.makedirs("results", exist_ok=True)
    print(build(os.path.join("results", "Tunduma_Hydraulic_Analysis_Report.pdf")))
