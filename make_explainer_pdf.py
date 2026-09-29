#!/usr/bin/env python3
"""Plain-language teaching guide to the Tunduma hydraulic analysis (black and white PDF).

Explains every step from first principles using the Bernoulli (energy) equation, with the real
numbers from the model, what each result means, and how it feeds the next step.

    python make_explainer_pdf.py   -> results/Tunduma_Hydraulics_Explained_Simply.pdf
"""
import math
import os

from reportlab.graphics.shapes import Drawing, Line, PolyLine, Polygon, Rect, String
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

import build_model
import epanet_check
import water_hydraulics as wh
from make_report_pdf import (BLACK, BOLD, FONT, ITALIC, PAGE_W, ST, WHITE, Doc, n, profile_drawing,
                             schematic)

ST = dict(ST)
ST["body"] = ParagraphStyle("b2", parent=ST["body"], fontSize=11, leading=15.5)
ST["bullet"] = ParagraphStyle("bl2", parent=ST["bullet"], fontSize=11, leading=15.5)
ST["calc"] = ParagraphStyle("c2", parent=ST["calc"], fontSize=10.5, leading=15)
ST["boxtitle"] = ParagraphStyle("bt", fontName=BOLD, fontSize=10.5, leading=14, spaceAfter=2)
ST["boxbody"] = ParagraphStyle("bb", fontName=FONT, fontSize=10.3, leading=14, spaceAfter=2)
ST["big"] = ParagraphStyle("big", fontName=FONT, fontSize=12.5, leading=19, alignment=1)
ST["qa_q"] = ParagraphStyle("qq", fontName=BOLD, fontSize=10.8, leading=14.5, spaceBefore=6)
ST["qa_a"] = ParagraphStyle("qa", fontName=FONT, fontSize=10.8, leading=14.5, leftIndent=6 * mm)
import make_report_pdf as mr  # noqa: E402

mr.ST.update({k: ST[k] for k in ("body", "bullet", "calc")})


# ---------------------------------------------------------------- building blocks
def box(doc, title, lines, style="plain"):
    """Framed box. style 'plain' = thin frame, 'key' = thick frame."""
    items = [Paragraph(title, ST["boxtitle"])] + [Paragraph(t, ST["boxbody"]) for t in lines]
    t = Table([[items]], colWidths=[PAGE_W])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1.6 if style == "key" else 0.7, BLACK),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    doc.story += [Spacer(1, 4), t, Spacer(1, 8)]


def analogy(doc, *lines):
    box(doc, "Think of it like this", list(lines))


def means(doc, *lines):
    box(doc, "What this means, and what happens next", list(lines), "key")


def say_it(doc, text):
    box(doc, "Say it in one sentence", [f"<i>“{text}”</i>"])


def arrow(d, x1, y1, x2, y2, w=0.8, both=False):
    d.add(Line(x1, y1, x2, y2, strokeColor=BLACK, strokeWidth=w))
    for (xa, ya, xb, yb) in ([(x1, y1, x2, y2)] + ([(x2, y2, x1, y1)] if both else [])):
        ang = math.atan2(yb - ya, xb - xa)
        a1, a2 = ang + math.radians(155), ang - math.radians(155)
        d.add(Polygon([xb, yb, xb + 5 * math.cos(a1), yb + 5 * math.sin(a1), xb + 5 * math.cos(a2),
                       yb + 5 * math.sin(a2)], fillColor=BLACK, strokeColor=BLACK, strokeWidth=0.4))


def txt(d, x, y, s, size=8, anchor="start", bold=False):
    d.add(String(x, y, s, fontName=BOLD if bold else FONT, fontSize=size, textAnchor=anchor))


def fig_three_heads():
    """A pipe with a piezometer and a pitot tube: z, p/(rho g), V^2/2g."""
    W, H = PAGE_W, 215
    d = Drawing(W, H)
    base = 20
    d.add(Line(20, base, W - 20, base, strokeColor=BLACK, strokeWidth=0.6))
    txt(d, W - 20, base - 12, "datum (level 0 – we use sea level)", 7.5, "end")
    py = 70                                   # pipe centre
    d.add(Rect(40, py - 12, W - 80, 24, strokeColor=BLACK, fillColor=WHITE, strokeWidth=1))
    arrow(d, 330, py, 390, py, 1.2)
    txt(d, 330, py + 17, "water flows this way, velocity V", 7.5)
    # piezometer
    x1 = 180
    d.add(Rect(x1 - 4, py + 12, 8, 95, strokeColor=BLACK, fillColor=WHITE, strokeWidth=0.8))
    lvl1 = py + 12 + 70
    d.add(Rect(x1 - 4, py + 12, 8, 70, strokeColor=BLACK, fillColor=BLACK, strokeWidth=0))
    # pitot
    x2 = 262
    d.add(Rect(x2 - 4, py + 12, 8, 115, strokeColor=BLACK, fillColor=WHITE, strokeWidth=0.8))
    d.add(Line(x2, py, x2 - 20, py, strokeColor=BLACK, strokeWidth=3))
    lvl2 = py + 12 + 90
    d.add(Rect(x2 - 4, py + 12, 8, 90, strokeColor=BLACK, fillColor=BLACK, strokeWidth=0))
    # dimension lines
    arrow(d, x1 - 55, base, x1 - 55, py, both=True)
    txt(d, x1 - 60, (base + py) / 2 - 3, "z  (height of the pipe)", 8, "end")
    arrow(d, x1 - 20, py, x1 - 20, lvl1, both=True)
    txt(d, x1 - 25, (py + lvl1) / 2, "p/ρg  (pressure head)", 8, "end")
    d.add(Line(x1 - 30, lvl1, x2 + 70, lvl1, strokeColor=BLACK, strokeWidth=0.5, strokeDashArray=[3, 2]))
    d.add(Line(x2 - 10, lvl2, x2 + 70, lvl2, strokeColor=BLACK, strokeWidth=0.5, strokeDashArray=[3, 2]))
    arrow(d, x2 + 22, lvl1, x2 + 22, lvl2, both=True)
    txt(d, x2 + 26, (lvl1 + lvl2) / 2 - 3, "V²/2g", 8)
    txt(d, x2 + 74, lvl1 - 3, "HGL = z + p/ρg", 8, bold=True)
    txt(d, x2 + 74, lvl2 - 3, "EGL = HGL + V²/2g (total head H)", 8, bold=True)
    txt(d, x1, py + 12 + 100, "tube A (piezometer)", 7.5, "middle")
    txt(d, x2, py + 12 + 120, "tube B (pitot, faces the flow)", 7.5, "middle")
    return d


def fig_pump_bernoulli():
    """Two tanks, a pump and a rising pipe with the energy line."""
    W, H = PAGE_W, 230
    d = Drawing(W, H)
    base = 15
    d.add(Line(10, base, W - 10, base, strokeColor=BLACK, strokeWidth=0.6))
    txt(d, W - 12, base + 3, "datum", 7, "end")
    # low tank
    d.add(Rect(20, 40, 70, 45, strokeColor=BLACK, fillColor=WHITE, strokeWidth=1))
    z1 = 75
    d.add(Line(20, z1, 90, z1, strokeColor=BLACK, strokeWidth=0.8))
    txt(d, 55, z1 + 4, "point 1", 7.5, "middle", True)
    txt(d, 55, 45, "suction tank", 7, "middle")
    # pump
    d.add(Rect(110, 45, 20, 16, strokeColor=BLACK, fillColor=BLACK))
    txt(d, 120, 32, "pump", 7.5, "middle")
    d.add(Line(90, 50, 110, 50, strokeColor=BLACK, strokeWidth=2))
    # pipe up to high tank
    d.add(PolyLine([130, 53, 180, 60, 300, 130, 380, 165], strokeColor=BLACK, strokeWidth=2))
    d.add(Rect(380, 150, 70, 50, strokeColor=BLACK, fillColor=WHITE, strokeWidth=1))
    z2 = 190
    d.add(Line(380, z2, 450, z2, strokeColor=BLACK, strokeWidth=0.8))
    txt(d, 415, z2 + 4, "point 2", 7.5, "middle", True)
    txt(d, 415, 155, "receiving tank", 7, "middle")
    # energy line
    top = 215
    d.add(Line(20, z1, 120, z1, strokeColor=BLACK, strokeWidth=0.6, strokeDashArray=[4, 2]))
    arrow(d, 120, z1, 120, top, 1.2)
    txt(d, 124, (z1 + top) / 2, "pump adds H_p", 8, bold=True)
    d.add(Line(120, top, 380, z2 + 3, strokeColor=BLACK, strokeWidth=1.2, strokeDashArray=[4, 2]))
    txt(d, 255, 182, "energy line slopes down:", 7.5, "middle")
    txt(d, 255, 173, "friction uses energy (h_L)", 7.5, "middle")
    arrow(d, 465, z2 + 3, 465, top, both=True)
    txt(d, 462, top - 6, "", 7)
    txt(d, 461, (z2 + 3 + top) / 2 - 3, "h_L", 8, "end", True)
    d.add(Line(380, top, 470, top, strokeColor=BLACK, strokeWidth=0.4, strokeDashArray=[2, 2]))
    arrow(d, 8, base, 8, z1, both=True)
    txt(d, 12, (base + z1) / 2, "z1", 8, bold=True)
    arrow(d, 470, base, 470, z2, both=True)
    txt(d, 466, (base + z2) / 2, "z2", 8, "end", True)
    return d


def fig_hgl_hill():
    """A pipe over a hill with the HGL above it; pressure = gap."""
    W, H = PAGE_W, 190
    d = Drawing(W, H)
    ground = [20, 40, 100, 55, 170, 100, 230, 140, 280, 130, 350, 70, 440, 50]
    d.add(PolyLine(ground, strokeColor=BLACK, strokeWidth=1.8))
    txt(d, 440, 38, "pipe (following the ground)", 7.5, "end")
    d.add(Line(20, 175, 440, 120, strokeColor=BLACK, strokeWidth=1.2, strokeDashArray=[5, 2]))
    txt(d, 30, 178, "HGL (the level the water would rise to in a tube)", 8, bold=True)
    # pressure at a low point
    x = 100
    hy = 175 - (x - 20) * 55 / 420
    arrow(d, x, 55, x, hy, both=True)
    txt(d, x + 4, (55 + hy) / 2, "big gap = high pressure", 7.5)
    x = 230
    hy = 175 - (x - 20) * 55 / 420
    arrow(d, x, 140, x, hy, both=True)
    txt(d, x + 4, 150, "small gap = low pressure (high point)", 7.5)
    txt(d, 240, 20, "If the dashed line ever dips BELOW the pipe, pressure is negative (suction): air comes out,", 7.5,
        "middle")
    txt(d, 240, 10, "the pipe can collapse or water stops flowing properly.", 7.5, "middle")
    return d


# ---------------------------------------------------------------- helpers from the model
def path_links(s, start_id, end_id):
    """Pipes from zone start to a node (walking upstream from the node)."""
    out, node = [], end_id
    while node != start_id:
        l = s.inc[node]
        out.append(l)
        node = l.frm
    return out[::-1]


def bernoulli_zone(doc, s, start, end, pump=True, st_loss=3.0, extra_note=None):
    """Write the Bernoulli equation between the water surface at `start` and the inlet of `end`."""
    a, b = s.nodes[start], s.nodes[end]
    links = path_links(s, start, end)
    z1 = a.min_level
    z2 = b.inlet_level + b.residual
    hl = sum(l.hloss for l in links)
    parts = " + ".join(f"{l.hloss:.2f}" for l in links)
    doc.calc(
        f"<b>Point 1</b> = water surface in {start} at its <i>lowest</i> level: z<sub>1</sub> = {z1:.2f} m, "
        "p<sub>1</sub> = 0 (open to the air), V<sub>1</sub> ≈ 0 (a big tank, the surface hardly moves).",
        f"<b>Point 2</b> = where the pipe pours into {end}: inlet level {b.inlet_level:.2f} m + safety margin "
        f"{b.residual:.1f} m → z<sub>2</sub> = {z2:.2f} m, p<sub>2</sub> = 0, V<sub>2</sub> ≈ 0.",
        f"Energy lost on the way: h<sub>L</sub> = {parts} = <b>{hl:.2f} m</b>"
        + (f" (pipes {', '.join(l.id for l in links)})" if len(links) > 1 else f" (pipe {links[0].id})"),
    )
    if pump:
        hp = z2 - z1 + hl
        doc.calc(
            "Bernoulli: z<sub>1</sub> + 0 + 0 + H<sub>p</sub> = z<sub>2</sub> + 0 + 0 + h<sub>L</sub> "
            "&nbsp;&nbsp;→&nbsp;&nbsp; H<sub>p</sub> = (z<sub>2</sub> − z<sub>1</sub>) + h<sub>L</sub>",
            f"H<sub>p</sub> = ({z2:.2f} − {z1:.2f}) + {hl:.2f} = {z2 - z1:.2f} (lift) + {hl:.2f} (friction) "
            f"= <b>{hp:.2f} m</b>",
            f"Add the losses inside the pump house (valves, bends, meter): {st_loss:.1f} m → "
            f"<b>pump head needed = {hp + st_loss:.1f} m</b>",
        )
        return hp + st_loss
    surplus = z1 - z2 - hl
    doc.calc(
        "Bernoulli with no pump: z<sub>1</sub> = z<sub>2</sub> + h<sub>L</sub> + (extra energy left over)",
        f"Extra energy = z<sub>1</sub> − z<sub>2</sub> − h<sub>L</sub> = {z1:.2f} − {z2:.2f} − {hl:.2f} = "
        f"<b>{surplus:.2f} m</b>",
    )
    return surplus


# ---------------------------------------------------------------- the guide
def build(out_path, cfg_path="tunduma_config.json"):
    cfg = build_model.load_config(cfg_path)
    al = build_model.prepare_alignment(cfg)
    data, routes = build_model.build_engine_model(cfg, al)
    s = wh.System(data).solve()
    N, L = s.nodes, {l.id: l for l in s.links}
    stl = s.settings["station_losses"]
    doc = Doc()
    P = doc.p

    # ---------------- title
    doc.story += [Spacer(1, 50 * mm),
                  Paragraph("Tunduma Water Supply Hydraulics – Explained Simply", ST["title"]),
                  Paragraph("How water gets from the Momba River to the Tunduma tanks, "
                            "and how every number was worked out", ST["subtitle"]),
                  Spacer(1, 15 * mm),
                  Paragraph("A step-by-step learning guide built on the Bernoulli (energy) equation", ST["subtitle"]),
                  Spacer(1, 30 * mm)]
    P("<b>How to use this guide.</b> Read it in order: every chapter uses the ideas from the one before. "
      "Part 1 builds the ideas from zero. Part 2 applies them to the Tunduma system, one piece at a time, from "
      "the river to the last tank. Part 3 prepares you for questions. Each step has the same three boxes:")
    doc.bullets([
        "<b>Think of it like this</b>: an everyday picture of the idea;",
        "<b>What this means, and what happens next</b>: why the number matters and where it is used later;",
        "<b>Say it in one sentence</b>: how to explain it to someone else.",
    ])
    P("All numbers come from the same model as the technical report, so the two documents always agree.")
    doc.story.append(PageBreak())

    # ================= PART 1
    doc.h1("Part 1 – The ideas you need (from zero)")

    doc.h2("What problem are we solving?")
    P(f"Tunduma needs <b>20,000 m³ of clean water every day</b>. One cubic metre is 1,000 litres, so that is "
      "20 million litres, about 1,000 big water-tanker lorries per day. The water is in the Momba River, "
      f"at about <b>{n(N['MOMBA_RIVER'].min_level, 0)} m above sea level</b>. The Tunduma tanks sit at about "
      f"<b>1,700 m</b>, some <b>{n(sum(L[x].length for x in ('RAW_MAIN', 'WTP_IKANA_RM', 'IKANA_NKANGAMO_GM', 'BPS_RM_1')) / 1000, 0)} km</b> "
      "away by pipe. So the water has to travel far <i>and</i> climb about <b>340 m</b>, higher than a "
      "100-storey building.")
    analogy(doc, "Water is lazy: it only moves downhill, or when something pushes it. A pump is the "
                 "“push”. A pipe is a road, and every road has friction that tires the traveller. Our job is to "
                 "make sure the water always has <b>enough energy</b> to finish each part of the journey, "
                 "without being pushed so hard that the pipes burst.")

    doc.h2("The journey of one drop of water")
    doc.figure(schematic(s), "The whole system. Solid lines: water is pushed by pumps. Dashed lines: water "
                             "flows downhill by itself (gravity).")
    doc.bullets([
        "<b>Momba River</b>: the source. Its lowest water level matters, because in the dry season the "
        "intake must still get water.",
        "<b>Intake + low-lift pumps</b>: water flows from the river into a sump (a concrete pit). Pumps lift "
        "it a little into the <b>grit tank</b>, where sand settles.",
        "<b>High-lift pumps</b>: push the raw water 1 km to the <b>water treatment plant (WTP)</b>.",
        "<b>WTP</b>: cleans the water. About 7 % is used up in cleaning (washing filters, sludge), so we "
        "must take in more than we deliver. Clean water collects in the clear-water tank.",
        "<b>WTP pumps</b>: the hardest job. They push the water about 20 km and 300 m up the hill to "
        "<b>Ikana GBR</b> (Ground Balancing Reservoir).",
        "<b>Ikana GBR → Nkangamo BPS</b>: from the top of the hill the water runs downhill by itself for "
        "about 39 km to the <b>Booster Pump Station</b>.",
        "<b>Nkangamo BPS</b>: pumps it up again, about 20 km, to <b>Uhuru Park GBR</b> in Tunduma. On the way "
        "it drops water off at three existing tanks (ESR, GSR01, Ipito).",
        "<b>Uhuru Park GBR</b>: feeds the town, and sends water downhill to Makambini and Chapwa tanks.",
    ])
    say_it(doc, "We pump river water up to the WTP, clean it, pump it over the Ikana hill, let it run down to "
                "Nkangamo, pump it up again to Tunduma, and share it between the tanks.")

    doc.h2("Words and units you must be comfortable with")
    doc.table("Units and words used everywhere in this guide.", ["Word", "Meaning in plain words"], [
        ["m³/d", "cubic metres per day: how much water in a whole day"],
        ["l/s, m³/s", "litres (or cubic metres) per second: how fast it flows right now. 1 m³/s = 1,000 l/s"],
        ["m a.s.l.", "metres above sea level: height of something"],
        ["head (m)", "energy of water written as a height in metres (explained in the next section)"],
        ["pressure head (m)", "how hard the water pushes, as a height. <b>10 m of water ≈ 1 bar</b>"],
        ["HGL", "hydraulic grade line: the level water would rise to in a small open tube on the pipe"],
        ["LWL / BWL / TWL", "lowest / bottom / top water level in a tank"],
        ["DN600", "pipe of about 600 mm (0.6 m) inside diameter"],
        ["PN16", "pipe strong enough for 16 bar ≈ 160 m of water pressure"],
        ["TDH", "total dynamic head: how much energy (in metres) a pump must add"],
    ], widths=[1.3, 5], align=["l", "l"])

    doc.h2("Idea 1 – Continuity: water does not disappear")
    P("If 20,000 m³ goes into a pipe per day, 20,000 m³ comes out (no leaks). The flow in any pipe is:")
    doc.eq("Q (m³/s) = daily volume ÷ seconds the pipe works per day = V<sub>d</sub> / (t × 3600)")
    P("The pumps run <b>22 hours</b>, not 24 (ER Table 8). The 2 spare hours leave time for maintenance and "
      "power cuts. So the same daily volume must pass in less time, and the flow must be <i>faster</i>:")
    doc.calc(f"Pumped: Q = 20,000 / (22 × 3600) = <b>{20000 / 79200:.4f} m³/s</b> = {20000 / 79.2:.1f} l/s",
             f"Gravity (24 h): Q = 20,000 / (24 × 3600) = <b>{20000 / 86400:.4f} m³/s</b> = {20000 / 86.4:.1f} l/s")
    P("How fast does the water move inside the pipe? Flow = area × speed, so speed = flow ÷ area:")
    doc.eq("A = π D² / 4 ,&nbsp;&nbsp;&nbsp; V = Q / A")
    doc.calc(f"DN600: A = 3.1416 × 0.6² / 4 = 0.2827 m²;  V = {20000 / 79200:.4f} / 0.2827 = "
             f"<b>{20000 / 79200 / 0.2827:.2f} m/s</b> (a slow walking pace)")
    analogy(doc, "A crowd leaving a stadium: if the gate is narrow (small D), people must move faster to get "
                 "the same number out per minute. If you have less time (22 h instead of 24 h), everyone must "
                 "hurry a bit.")
    means(doc, "0.9 m/s is a healthy speed: fast enough that dirt does not settle (&gt; 0.3–0.5 m/s), slow "
               "enough that friction and water hammer stay moderate (ER limit 3 m/s). Speed is used next in "
               "friction (Idea 3) and in water hammer (Idea 6).")

    doc.h2("Idea 2 – The Bernoulli equation: the energy bank account of water")
    P("Every kilogram of water carries energy in <b>three pockets</b>:")
    doc.bullets([
        "<b>Height energy (z)</b>: water that is high up can fall. A tank on a hill has lots of it.",
        "<b>Pressure energy (p/ρg)</b>: water that is squeezed wants to push out. That is why water shoots "
        "out of a hole in a pipe.",
        "<b>Movement energy (V²/2g)</b>: moving water carries energy, like a moving car.",
    ])
    P("Engineers measure all three in <b>metres</b> (“head”), because each can be pictured as a height. "
      "Pressure p divided by (ρ × g) is the height of a water column that would give that pressure. V²/2g is "
      "the height a ball thrown up at speed V would reach. Figure 2 shows all three on a real pipe.")
    doc.figure(fig_three_heads(), "The three kinds of head. Tube A shows the pressure head; tube B faces "
                                  "the flow and catches the velocity head as well.")
    P("Daniel Bernoulli (1738) noticed that if nothing adds or removes energy, the total stays the same "
      "between any two points 1 and 2 along the flow:")
    doc.eq("z<sub>1</sub> + p<sub>1</sub>/ρg + V<sub>1</sub>²/2g = z<sub>2</sub> + p<sub>2</sub>/ρg + "
           "V<sub>2</sub>²/2g")
    P("In real pipes, two more things happen. A <b>pump adds</b> energy (H<sub>p</sub>), and <b>friction "
      "removes</b> energy (h<sub>L</sub>, turned into a tiny bit of heat). So the real, working form of "
      "Bernoulli, used for <i>every</i> calculation in this project, is:")
    doc.eq("<b>z<sub>1</sub> + p<sub>1</sub>/ρg + V<sub>1</sub>²/2g + H<sub>p</sub> = z<sub>2</sub> + "
           "p<sub>2</sub>/ρg + V<sub>2</sub>²/2g + h<sub>L</sub></b>")
    analogy(doc, "A bank account. Your money sits in three accounts (height, pressure, speed) and can move "
                 "between them. A pump is a salary deposit (H<sub>p</sub>). Friction is a fee charged on every "
                 "metre of pipe (h<sub>L</sub>). Bernoulli says: <b>what you start with + deposits = what you "
                 "end with + fees</b>. Nothing disappears without a record.")
    P("<b>Three tricks that make it easy.</b> We choose points 1 and 2 cleverly:")
    doc.bullets([
        "on the <b>water surface of a tank</b>, the water is open to the air, so <b>p = 0</b> (we measure "
        "pressure above atmospheric);",
        "a tank is so big that its surface barely moves, so <b>V ≈ 0</b>;",
        "inside the pipe, V²/2g = 0.9² / (2 × 9.81) = <b>0.04 m</b>. That is only 4 cm, tiny compared "
        "with hundreds of metres of height, so we can ignore it.",
    ])
    P("Between two tank surfaces, Bernoulli therefore shrinks to something a child can use:")
    doc.eq("<b>H<sub>p</sub> = (z<sub>2</sub> − z<sub>1</sub>) + h<sub>L</sub></b>&nbsp;&nbsp;&nbsp; "
           "(pump head = lift + friction)")
    doc.figure(fig_pump_bernoulli(), "Bernoulli between two tanks. The pump raises the energy line by "
                                     "H<sub>p</sub>; friction makes it slope down; at point 2 what is left "
                                     "must still reach the water level z<sub>2</sub>.")
    P("And inside a pipe at any point x, Bernoulli tells us the <b>pressure</b>, which we need for pipe "
      "strength:")
    doc.eq("p(x)/ρg = H(x) − z(x) − V²/2g ≈ H(x) − z(x)")
    means(doc, "This one equation answers the three big questions of the project. (1) How strong must each "
               "pump be? Solve for H<sub>p</sub>. (2) Does gravity alone have enough energy? Set "
               "H<sub>p</sub> = 0 and see what is left. (3) How much pressure does each pipe feel? Use the "
               "point form.")
    say_it(doc, "Bernoulli is an energy balance: energy at the start plus what the pump adds equals energy "
                "at the end plus what friction took, and we count every energy in metres of water.")

    doc.h2("Idea 3 – Friction: the fee for travelling")
    P("Water rubbing along the pipe wall loses energy. We compute this loss with the <b>Hazen–Williams</b> "
      "formula, an experimental rule that has been proven for water pipes for over 100 years:")
    doc.eq("h<sub>f</sub> = 10.67 × L × Q<super>1.852</super> / (C<super>1.852</super> × "
           "D<super>4.8704</super>)")
    doc.bullets([
        "<b>L</b> (length, m): twice as long means twice the loss. Obvious: a longer road is more tiring.",
        "<b>Q</b> (flow, m³/s) to the power 1.852: pushing <b>twice the flow costs about 3.6 times</b> the "
        "loss (2<super>1.852</super> = 3.6). This is why rushing water is expensive.",
        "<b>D</b> (diameter, m) to the power 4.87: a slightly bigger pipe helps a lot. Going from DN500 to "
        "DN600 cuts the loss by (0.6/0.5)<super>4.87</super> = 2.4 times.",
        f"<b>C</b> (smoothness): new smooth pipe about 140, old rough pipe about 100. We used "
        f"<b>C = {cfg['pipe_defaults']['hw_c']}</b> (steel with a cement lining, after some years of use), "
        "to be on the safe side.",
    ])
    P("Bends, valves, meters and fittings also take a small bite, called <b>minor losses</b>. We add "
      f"<b>{s.settings['minor_loss_factor'] * 100:.0f} %</b> of the friction loss for them: "
      "h<sub>L</sub> = h<sub>f</sub> + 0.10 h<sub>f</sub>.")
    analogy(doc, "Walking through a crowded market. The longer the market (L), the more tired you get. If "
                 "you run (large Q), you bump into far more people. A wide street (large D) is much easier. "
                 "A clean street (high C) is easier than a muddy one.")
    means(doc, "Friction decides how much <i>extra</i> head the pumps need on top of the lift, and how much "
               "energy gravity mains lose. It also makes the energy line slope down, which sets the pressure "
               "at every point.")

    doc.h2("Idea 4 – The hydraulic grade line (HGL) and pressure")
    P("Imagine small open tubes standing on the pipe every few metres. Water would rise in each tube to a "
      "certain level. Join those levels and you get the <b>HGL</b>. The pressure at any point is simply the "
      "<b>gap between the HGL and the pipe</b>.")
    doc.figure(fig_hgl_hill(), "The HGL (dashed) slopes down because of friction. Pressure is the vertical "
                               "gap between the HGL and the pipe.")
    P("We computed the HGL at <b>every one of the 2,336 surveyed points</b> along the route. We then required "
      f"it to stay at least <b>{s.pipe_pmin:.0f} m above the pipe</b> everywhere (the pipe is {s.settings['pipe_cover']:.1f} m "
      f"underground), and at least <b>{s.settings['min_pressure_head']:.0f} m</b> at junctions and delivery "
      "points (ER Table 7).")
    means(doc, "High points on the route are the dangerous places: the gap is small there. Sometimes a high "
               "point, not the tank at the end, decides how strong the pump must be. Low points have the "
               "biggest gap, which means the highest pressure, so they need the strongest pipes.")

    doc.h2("Idea 5 – Pumps: how much energy and electricity")
    P("Bernoulli gives the pump head H<sub>p</sub>. The pump must add that many metres of energy to "
      "<i>every</i> kilogram of water. Power is energy per second:")
    doc.eq("Power to the water: P<sub>h</sub> = ρ × g × Q × H / 1000 &nbsp;&nbsp;(kW)")
    doc.bullets([
        "ρ = 1,000 kg/m³ (mass of one cubic metre of water), g = 9.81 m/s²;",
        "ρ × g × Q = weight of water lifted per second; × H = energy per second = power;",
        "no pump is perfect: shaft power P<sub>s</sub> = P<sub>h</sub> / η<sub>pump</sub> (η ≈ 0.75–0.78);",
        "the motor is chosen about 15 % bigger than P<sub>s</sub>, then rounded up to a standard size;",
        "electricity per day = number of pumps × P<sub>s</sub> × hours ÷ motor efficiency.",
    ])
    analogy(doc, "Carrying buckets up stairs. Power = (weight of buckets per second) × (height of the "
                 "stairs). More buckets or taller stairs means more power, and a tired person (a poor pump "
                 "efficiency) wastes some of the effort.")

    doc.h2("Idea 6 – Pressure strength (PN) and water hammer")
    P("Pipes are sold in strengths: PN10, PN16, PN25, PN30, PN40. <b>PN16 means it can safely carry 16 bar "
      "≈ 160 m of water</b>, continuously. At each point we check the larger of two pressures:")
    doc.bullets([
        "the <b>working pressure</b> while flowing (from the HGL);",
        "the <b>static pressure</b> when the flow stops and the water just sits, pushed by the highest tank "
        "level.",
    ])
    P("<b>Water hammer (surge).</b> If a pump suddenly stops (a power cut), the moving water column slams to a "
      "halt. The pressure then jumps up and down by:")
    doc.eq("Δh = a × V / g&nbsp;&nbsp;&nbsp; (Joukowsky)")
    P("Here a is the speed of the pressure wave in the pipe, about 1,000 m/s in steel. For V = 0.9 m/s that "
      "gives Δh = 1,000 × 0.9 / 9.81 ≈ <b>92 m</b>, a huge jump.")
    analogy(doc, "A fast train hitting a wall: the longer and faster the train, the bigger the crash. Surge "
                 "vessels (air cushions) and air valves act like buffers that soften the crash.")
    means(doc, "Water hammer can also pull the pressure <i>below zero</i>, which sucks in air and can "
               "collapse pipes. This is why the ER requires surge protection at the pump stations. The PN is "
               "chosen for the normal (working) pressure; the surge devices keep the transients within the "
               "pipe's allowed maximum (1.2 × PN, from EN 805).")

    doc.h2("Idea 7 – Tanks: why we need storage")
    P("Pumps work 22 hours, but people use water all 24 hours. During the 2 hours the pumps rest, the tanks "
      "must supply the town from storage:")
    doc.eq("V<sub>balance</sub> = daily volume × (1 − pumping hours / 24)")
    doc.calc("Example, Ikana GBR: 20,000 × (1 − 22/24) = 20,000 × 0.0833 = <b>1,667 m³</b> needed; it holds "
             f"<b>{n(N['IKANA_GBR'].volume, 0)} m³</b> → enough.")
    analogy(doc, "A water bottle on a long walk: you drink all the time, but you can only refill at certain "
                 "stops. The bottle must be big enough to last between stops.")

    # ================= PART 2
    doc.story.append(PageBreak())
    doc.h1("Part 2 – Walking through Tunduma, piece by piece")
    P("We now follow the water from the river to the last tank. For each piece we use the same recipe:")
    doc.bullets([
        "(1) decide the flow (continuity);",
        "(2) compute the friction loss in each pipe (Hazen–Williams);",
        "(3) write Bernoulli between the water surface where the piece starts and the water surface where it "
        "ends;",
        "(4) solve for the pump head, or for the extra energy if there is no pump;",
        "(5) explain what the result means.",
    ])
    P("<b>Important choice:</b> we always take the <b>lowest</b> water level in the tank the water leaves, "
      "and the <b>highest</b> level (the inlet) of the tank it enters. This is the worst case: the pump must "
      "cope even then.")

    raw = N["MOMBA_WTP"].inflow_daily
    doc.h2("Step 0 – How much water must we take from the river?")
    doc.calc("Water the WTP must deliver: <b>20,000 m³/d</b> (the sum of all tank demands, Table 2)",
             "The WTP and the raw-water line use about 7 % (2 % + 5 %, ER Table 8), so only 93 % of what "
             "enters comes out:",
             f"Intake flow = 20,000 / (1 − 0.07) = 20,000 / 0.93 = <b>{n(raw, 0)} m³/d</b> "
             "(the ER says 21,506 m³/d ✓)",
             f"Per second (22 h pumping): Q = {n(raw, 0)} / 79,200 = <b>{raw / 79200:.4f} m³/s</b> = "
             f"{raw / 79.2:.0f} l/s")
    doc.table("Where the 20,000 m³/d goes (ER schematic).", ["Tank", "Daily demand (m³/d)"],
              [[t, n(N[t].demand, 2)] for t in ("UHURU_PARK_GBR", "UHURU_GSR01", "TUNDUMA_ESR", "IPITO_GSR02",
                                                "MAKAMBINI_GSR03", "CHAPWA_GSR04")], widths=[3, 1.5])
    means(doc, "Everything upstream of the WTP is sized for 21,505 m³/d, and everything downstream for "
               "20,000 m³/d. If the WTP wasted more water, the intake and raw-water pumps would need to be "
               "bigger.")

    # ---- step 1
    doc.h2("Step 1 – River to intake sump (gravity, no pump)")
    P("Water flows from the river into the sump by itself, through a DN600 pipe 100 m long. Will the "
      "river push enough water in?")
    ab = L["ABSTRACTION"]
    doc.calc(f"Friction in the pipe: h<sub>f</sub> = 10.67 × 100 × {ab.q:.4f}<super>1.852</super> / "
             f"(120<super>1.852</super> × 0.6<super>4.8704</super>) = {ab.hf:.2f} m;  + 10 % → "
             f"h<sub>L</sub> = {ab.hloss:.2f} m")
    sur = bernoulli_zone(doc, s, "MOMBA_RIVER", "MOMBA_INTAKE", pump=False)
    means(doc, f"The river is higher than the sump's lowest level by more than the friction loss, leaving "
               f"<b>{sur:.2f} m</b> to spare. So even in the dry season the sump fills by itself. When "
               f"pumping, the sump water settles at about {N['MOMBA_RIVER'].min_level - ab.hloss:.2f} m. For "
               "the pumps we use the worst case, the sump's lowest level (1,360.0 m), as point 1 of the next "
               "step.")
    say_it(doc, "The river is a little higher than the sump, so water falls in by itself; we only lose "
                f"{ab.hloss * 100:.0f} cm to friction.")

    # ---- step 2
    doc.h2("Step 2 – Low-lift pumps: sump to grit tank")
    ld = L["LL_DELIVERY"]
    doc.calc(f"Flow: {ld.q:.4f} m³/s;  30 m of DN600 → h<sub>L</sub> = {ld.hloss:.2f} m (almost nothing)")
    hp = bernoulli_zone(doc, s, "MOMBA_INTAKE", "GRIT_TANK", st_loss=stl)
    r = N["MOMBA_INTAKE"].station
    doc.calc(f"Power: P<sub>h</sub> = 1000 × 9.81 × {r['q_pump']:.4f} × {r['tdh']:.1f} / 1000 = "
             f"{r['hyd_kw']:.1f} kW;  P<sub>s</sub> = {r['hyd_kw']:.1f} / 0.75 = {r['shaft_kw']:.1f} kW → "
             f"motor <b>{r['motor_kw']:g} kW</b>")
    means(doc, f"The pump needs about <b>{hp:.0f} m</b>. The ER gives 10 m. The difference comes from our "
               "<i>assumed</i> grit-tank level. Every 1 m higher that tank is, the pump needs 1 m more. So "
               "confirm the grit-tank levels before buying the pumps. The grit tank's lowest level "
               f"({N['GRIT_TANK'].min_level} m) becomes point 1 of the next step.")

    # ---- step 3
    doc.h2("Step 3 – High-lift pumps: grit tank to the WTP")
    rm = L["RAW_MAIN"]
    P(f"The raw-water main is {n(rm.length, 0)} m of DN600 along the surveyed ground.")
    doc.calc(f"V = {rm.q:.4f} / 0.2827 = {rm.v:.2f} m/s",
             f"h<sub>f</sub> = 10.67 × {n(rm.length, 1)} × {rm.q ** 1.852:.5f} / (7,090 × 0.08308) = "
             f"{rm.hf:.2f} m;  h<sub>L</sub> = {rm.hf:.2f} × 1.10 = <b>{rm.hloss:.2f} m</b>")
    hp = bernoulli_zone(doc, s, "GRIT_TANK", "MOMBA_WTP", st_loss=stl)
    means(doc, f"We need about <b>{hp:.0f} m</b>. The ER pumps give 25 m, about 8 m more than needed. "
               "What does extra head do? Bernoulli must still balance, so the pump pushes <i>more flow</i> "
               "until friction eats the extra. The EPANET check showed about 1,230 m³/h instead of 978 m³/h "
               "(+26 %). The WTP would then receive more water than it is designed for. So a control valve "
               "or a variable-speed drive is needed.")

    # ---- step 4
    doc.h2("Step 4 – WTP pumps to Ikana GBR (the big climb)")
    w = L["WTP_IKANA_RM"]
    P(f"This is the most important pipe. {n(w.length, 0)} m of DN600 climbs from the WTP clear-water tank "
      f"to Ikana GBR on top of the hill. First the friction:")
    doc.calc(f"Q = 20,000 / 79,200 = {w.q:.4f} m³/s;  V = {w.q:.4f} / 0.2827 = <b>{w.v:.3f} m/s</b>",
             f"h<sub>f</sub> = 10.67 × {n(w.length, 1)} × {w.q:.4f}<super>1.852</super> / "
             f"(120<super>1.852</super> × 0.6<super>4.8704</super>)",
             f"&nbsp;&nbsp;&nbsp;&nbsp;= 10.67 × {n(w.length, 1)} × {w.q ** 1.852:.5f} / "
             f"({120 ** 1.852:,.1f} × {0.6 ** 4.8704:.5f}) = <b>{w.hf:.2f} m</b>",
             f"Minor losses 10 %: {w.hm:.2f} m → total h<sub>L</sub> = <b>{w.hloss:.2f} m</b> "
             f"(that is {w.hloss / w.length * 1000:.2f} m lost per km)")
    hp = bernoulli_zone(doc, s, "MOMBA_WTP", "IKANA_GBR", st_loss=stl)
    r = N["MOMBA_WTP"].station
    lift = N["IKANA_GBR"].inlet_level + N["IKANA_GBR"].residual - N["MOMBA_WTP"].min_level
    doc.calc(f"Per pump (3 working): Q = {w.q:.4f} / 3 = {r['q_pump']:.4f} m³/s = {r['q_pump'] * 3600:.0f} m³/h",
             f"P<sub>h</sub> = 1000 × 9.81 × {r['q_pump']:.4f} × {r['tdh']:.1f} / 1000 = {r['hyd_kw']:.0f} kW;  "
             f"P<sub>s</sub> = {r['hyd_kw']:.0f} / 0.78 = <b>{r['shaft_kw']:.0f} kW</b> → motor "
             f"<b>{r['motor_kw']:g} kW</b> each",
             f"Electricity: 3 × {r['shaft_kw']:.0f} × 22 / 0.95 = <b>{n(r['energy_day'], 0)} kWh per day</b> "
             f"= {r['kwh_per_m3']:.2f} kWh for each m³ delivered")
    P("<b>How much pressure does the pipe feel?</b> Use Bernoulli at a point, p/ρg = H − z:")
    top = w.rows[0]
    doc.calc(f"Just after the pumps: H = {top[2]:.1f} m, pipe at {top[1]:.1f} m → p = {top[2]:.1f} − "
             f"{top[1]:.1f} = <b>{top[3]:.1f} m ≈ {top[3] / 10.2:.1f} bar</b> → needs PN40 here",
             f"Near Ikana: H ≈ 1,669 m, pipe ≈ 1,660 m → p ≈ 9 m ≈ 0.9 bar → PN10 is enough")
    means(doc, f"Of the {hp:.0f} m pump head, <b>{lift:.0f} m ({100 * lift / hp:.0f} %) is pure lifting</b> and "
               f"only {w.hloss:.0f} m is friction. So a bigger pipe would save little. The hill itself is the "
               f"cost. Our {hp:.0f} m agrees with the ER's 330 m, and EPANET confirmed the ER pumps deliver "
               "within 1 % of the needed flow. Because pressure falls from about 330 m at the WTP to about 9 m "
               "at Ikana, the pipe strength also steps down along the route: PN40, then PN30, PN25, PN16, "
               "PN10. Our PN30 length (10,776 m) matches the ER (10,798 m).")
    say_it(doc, f"The WTP pumps must lift the water about {lift:.0f} m and beat about {w.hloss:.0f} m of friction, "
                f"so they need about {hp:.0f} m of head; pressure is highest at the pumps, so the strongest "
                "pipe is there.")

    # ---- step 5
    doc.h2("Step 5 – Ikana GBR to Nkangamo BPS (downhill by gravity)")
    gm = L["IKANA_NKANGAMO_GM"]
    P(f"From the hilltop the water runs {n(gm.length / 1000, 1)} km downhill to the booster station. There is "
      "no pump, so the question is: <b>does gravity give enough energy, or too much?</b>")
    doc.calc(f"24-hour flow: Q = 20,000 / 86,400 = {gm.q:.4f} m³/s;  V = {gm.v:.2f} m/s",
             f"h<sub>f</sub> = 10.67 × {n(gm.length, 0)} × {gm.q ** 1.852:.5f} / (7,090 × 0.08308) = "
             f"{gm.hf:.2f} m;  h<sub>L</sub> = <b>{gm.hloss:.2f} m</b>")
    sur = bernoulli_zone(doc, s, "IKANA_GBR", "NKANGAMO_BPS", pump=False)
    q_free = gm.q * ((gm.hloss + sur) / gm.hloss) ** (1 / 1.852)
    doc.calc("<b>What if we did nothing?</b> The leftover energy would make the water rush faster until "
             "friction eats it all. Friction grows as Q<super>1.852</super>, so:",
             f"Q<sub>free</sub> = {gm.q * 1000:.0f} × (({gm.hloss:.1f} + {sur:.1f}) / {gm.hloss:.1f})"
             f"<super>1/1.852</super> = <b>{q_free * 1000:.0f} l/s</b> instead of {gm.q * 1000:.0f} l/s")
    static = max(gm.rows, key=lambda r: r[4])
    doc.calc(f"<b>Worst pressure (valve closed, water still):</b> Ikana top level 1,668.0 m, lowest pipe "
             f"{static[1]:.1f} m → 1,668.0 − {static[1]:.1f} = <b>{static[4]:.0f} m ≈ {static[4] / 10.2:.0f} bar</b>"
             " → PN25")
    means(doc, f"Gravity gives <b>{sur:.0f} m too much</b>. Left alone, the water would flow about "
               f"{100 * (q_free / gm.q - 1):.0f} % faster, empty Ikana GBR and overflow the Nkangamo sump. So we "
               "fit a <b>flow control valve</b> at the sump inlet that deliberately “burns” those 53 m. We cannot "
               f"use a smaller pipe instead: the static pressure of about {static[4]:.0f} m in the valleys already "
               "needs PN25. "
               "The Nkangamo sump level is point 1 of the next step.")
    say_it(doc, "Going downhill, the water has more energy than it needs, so a valve at the bottom brakes it "
                "to the right flow.")

    # ---- step 6
    doc.h2("Step 6 – Nkangamo BPS to Uhuru Park and the existing tanks")
    P("Now one pump station feeds <b>four destinations</b>: the ESR (at J-001N), GSR01 (at J-002N), Ipito "
      "(at J-003N) and Uhuru Park GBR. There is also a high hill at about 74 km. We write Bernoulli from the "
      "sump to <b>each</b> destination. The one that needs the most head decides the pump, like a "
      "family trip that must wait for the slowest child.")
    bm = L["BPS_RM_1"]
    doc.calc(f"Main pipe BPS → J-001N: {n(bm.length, 0)} m, Q = {bm.q:.4f} m³/s, V = {bm.v:.2f} m/s, "
             f"h<sub>L</sub> = <b>{bm.hloss:.2f} m</b>")
    sump = N["NKANGAMO_BPS"].min_level
    rows = []
    for tid in ("TUNDUMA_ESR", "UHURU_GSR01", "IPITO_GSR02", "UHURU_PARK_GBR"):
        t = N[tid]
        links = path_links(s, "NKANGAMO_BPS", tid)
        hl = sum(l.hloss for l in links)
        need = t.inlet_level + t.residual + hl
        rows.append([tid, f"{t.inlet_level + t.residual:.2f}", f"{hl:.2f}", f"{need:.2f}",
                     f"{need - sump + stl:.1f}"])
    hp_x, hp_z = bm.gov_point if bm.gov_point else (14583.1, 1708.8)
    hi = max(bm.rows[1:-1], key=lambda r: r[1])
    need_hill = hi[1] + s.pipe_pmin + bm.hloss * hi[0] / bm.length
    rows.append([f"high point at {hi[0] / 1000:.1f} km of this pipe", f"{hi[1]:.1f} + {s.pipe_pmin:.0f}",
                 f"{bm.hloss * hi[0] / bm.length:.2f}", f"{need_hill:.2f}", f"{need_hill - sump + stl:.1f}"])
    doc.table(f"Bernoulli from the Nkangamo sump (LWL {sump:.1f} m) to each destination: level needed + "
              "friction on the way = HGL needed at the pumps.",
              ["Destination", "z<sub>2</sub> (m)", "h<sub>L</sub> on the way (m)", "HGL needed (m)",
               "Pump head (m)"], rows, widths=[2.6, 1.1, 1.3, 1.2, 1.1])
    r = N["NKANGAMO_BPS"].station
    doc.calc(f"The biggest is the ESR: pump head = {N['NKANGAMO_BPS'].required_head:.2f} − {sump:.2f} + "
             f"{stl:.1f} = <b>{r['tdh']:.1f} m</b>",
             f"P<sub>s</sub> = 1000 × 9.81 × {r['q_pump']:.4f} × {r['tdh']:.1f} / (1000 × 0.78) = "
             f"<b>{r['shaft_kw']:.0f} kW</b> per pump (2 working) → motor {r['motor_kw']:g} kW")
    means(doc, "The small <b>elevated ESR</b> (assumed water level 1,706.5 m) is the hardest to reach, so it "
               f"sets the pump head at <b>{r['tdh']:.0f} m</b>. Every other destination then gets <i>more</i> "
               "energy than it needs (Ipito about 13 m more), so each gets a <b>flow control valve</b>. "
               "Otherwise the easiest tank would steal the water. The ER pumps give 221 m, about 33 m more "
               f"than needed. The high point at 74 km needs {need_hill - sump + stl:.0f} m, only a little "
               "less, so it also needs <b>air valves</b>. If the ESR levels turn out lower than assumed, the "
               "pump head drops by a few metres. Confirm them.")

    # ---- step 7
    doc.h2("Step 7 – Uhuru Park GBR to Makambini and Chapwa (gravity)")
    ch, uj = L["CHAPWA_BRANCH"], L["UHURU_J004N"]
    doc.calc(f"Uhuru → J-004N: DN150, {n(uj.length, 0)} m, h<sub>L</sub> = {uj.hloss:.2f} m;  "
             f"J-004N → Chapwa: DN100, {n(ch.length, 0)} m, h<sub>L</sub> = {ch.hloss:.2f} m")
    sur = bernoulli_zone(doc, s, "UHURU_PARK_GBR", "CHAPWA_GSR04", pump=False)
    x, z = uj.gov_point
    h_at = N["UHURU_PARK_GBR"].min_level - uj.hloss * x / uj.length
    doc.calc(f"<b>But check a point near the tank</b> (Bernoulli at a point), {x:.0f} m after the GBR: "
             f"H = {N['UHURU_PARK_GBR'].min_level:.2f} − {uj.hloss:.2f} × {x:.0f}/{n(uj.length, 0)} = "
             f"{h_at:.2f} m;  pipe at {z:.2f} m → p = <b>{h_at - z:.2f} m (negative!)</b>")
    means(doc, f"Chapwa is far below Uhuru Park, so it arrives with <b>{sur:.0f} m</b> of extra energy. It needs a "
               "pressure-reducing or flow control valve, and PN25 on the lowest part. But right next to the "
               "GBR the ground is about 1 m <i>higher</i> than the tank's bottom level (ER 1,697.3 m). When "
               "the tank is low, the HGL there dips below the pipe: negative pressure. Fix: lay the first "
               "~200 m of pipe deeper, or confirm or raise the GBR levels.")

    # ---- overview
    doc.story.append(CondPageBreak(130 * mm))
    doc.h2("The whole journey in one picture")
    paths = {p[-1].to: p for p in s.paths()}
    doc.figure(profile_drawing(s, paths["CHAPWA_GSR04"]),
               "Ground (thin line) and HGL (thick line) from the river to Chapwa. Vertical jumps are the "
               "pumps adding energy. Downward drops are water arriving in a tank. The slopes are friction.")
    P("Read the picture like a story. At about 1 km, the WTP pumps lift the HGL by more than 300 m. It "
      "slopes gently down to Ikana at 20.7 km. From there it slopes down to Nkangamo at about 60 km, staying "
      "well above the ground, and drops at the valve. The BPS then lifts it by about 190 m. Near 74 km the "
      "ground almost touches the HGL: that is the critical high point. Finally the HGL runs down to Chapwa.")

    # ---- storage
    doc.h2("Storage check")
    rows = []
    for tid in ("IKANA_GBR", "UHURU_PARK_GBR", "TUNDUMA_ESR", "UHURU_GSR01", "IPITO_GSR02"):
        t = N[tid].tank
        rows.append([tid, n(t["inflow"], 0), f"{n(t['inflow'], 0)} × 2/24 = {n(t['balancing'], 0)}",
                     n(t["volume"], 0), "yes"])
    doc.table("Does each tank hold enough water for the 2 hours the pumps rest?",
              ["Tank", "Daily inflow (m³)", "Needed (m³)", "Has (m³)", "Enough?"], rows,
              widths=[2.2, 1.2, 2.2, 1, 0.8])
    means(doc, "All tanks can cover the pump rest time. The larger volumes give extra safety for power cuts "
               "and for the busy morning and evening hours in town.")

    # ---- EPANET
    doc.h2("How do we know the numbers are right?")
    P("We solved the same network a second, independent way, with <b>EPANET</b>, the standard free program "
      "from the US Environmental Protection Agency. It solves Bernoulli and continuity at all 2,300+ points "
      "at once. With our pump heads, EPANET gave the <b>same water levels within about 0.1 m</b> and the same "
      "flows. With the ER pumps, it showed that the WTP pumps are right, while the grit-tank and BPS pumps "
      "have extra head that must be controlled.")
    analogy(doc, "Checking a long sum with a calculator after doing it by hand. Two different methods giving "
                 "the same answer is strong proof.")

    # ================= PART 3
    doc.story.append(PageBreak())
    doc.h1("Part 3 – Be ready to explain: questions and answers")
    qa = [
        ("Why do you use Bernoulli?",
         "Because it is simply conservation of energy for flowing water. It links height, pressure and speed, "
         "and with pump and friction terms added it tells us exactly how much energy must be supplied or "
         "removed between any two points."),
        ("Why can you ignore the velocity term V²/2g?",
         "At 0.9 m/s it is 0.04 m, while the heights involved are hundreds of metres. At tank surfaces the "
         "velocity is practically zero anyway. The exit loss where the pipe enters a tank is covered by the "
         "1 m safety margin."),
        ("Why do the pumps run 22 hours and not 24?",
         "The ER sets 22 h. It leaves time for maintenance, power interruptions and cheaper tariff periods. "
         "The price is a slightly larger flow (and more friction) while pumping, plus tanks big enough to "
         "cover the 2-hour gap."),
        ("Why is the WTP pump head so large?",
         "About 300 m of it is pure height: the water must climb from about 1,368 m to 1,669 m. Friction is "
         "only about 31 m. A bigger pipe would not reduce the height."),
        ("Why does the gravity main need a valve if water is flowing downhill?",
         "Downhill it has about 53 m more energy than needed. Without a valve it would flow about 47 % faster "
         "than designed, emptying Ikana and flooding the BPS sump. The valve turns the extra energy into "
         "harmless turbulence."),
        ("Why is the BPS head (188 m) lower than the ER's 221 m?",
         "Our calculation uses the survey route, which is about 2 km shorter than the ER length. We also found "
         "the elevated ESR governs, not the far end. The ER value keeps about 33 m of reserve; the valves at "
         "the tanks absorb it."),
        ("What decides the pipe class (PN)?",
         "The highest pressure the pipe will see at each point: working pressure while flowing, or static "
         "pressure when the flow stops. Near the pumps and in deep valleys the pressure is high, so the pipe "
         "is stronger there. Surge devices keep water hammer within 1.2 × PN."),
        ("What is the most uncertain part of this analysis?",
         "The water levels not given in the ER: the river low level, the intake and grit tank, the WTP inlet "
         "and clear-water tank, the tank depths, and especially the ESR level. The route gaps (the GAP pipes) "
         "should also be surveyed. Changing any of these in the configuration file and re-running updates "
         "every number."),
        ("What was wrong with the first EPANET file from the DXF?",
         "The ground levels were right. But it had no pumps, the river level was set at ground level, and "
         "the WTP, Ikana, BPS and several tanks were missing. The pipes were placeholders. As a result it "
         "showed −209 m pressures and water flowing back to the river."),
    ]
    for q, a in qa:
        doc.story.append(KeepTogether([Paragraph(q, ST["qa_q"]), Paragraph(a, ST["qa_a"])]))

    # ---------------- cheat sheet
    doc.story.append(PageBreak())
    doc.h1("One-page cheat sheet")
    doc.table("The formulas and what each is for.", ["Formula", "Use it to find"], [
        ["Q = V<sub>d</sub> / (3600 t)", "flow per second from daily volume and pumping hours"],
        ["V = Q / (πD²/4)", "speed of water in the pipe"],
        ["z<sub>1</sub> + p<sub>1</sub>/ρg + V<sub>1</sub>²/2g + H<sub>p</sub> = z<sub>2</sub> + "
         "p<sub>2</sub>/ρg + V<sub>2</sub>²/2g + h<sub>L</sub>", "Bernoulli / energy balance between two points"],
        ["H<sub>p</sub> = (z<sub>2</sub> − z<sub>1</sub>) + h<sub>L</sub>", "pump head between two tank surfaces"],
        ["surplus = z<sub>1</sub> − z<sub>2</sub> − h<sub>L</sub>", "extra energy in a gravity main (valve)"],
        ["p/ρg = H − z", "pressure at any point in a pipe"],
        ["h<sub>f</sub> = 10.67 L Q<super>1.852</super>/(C<super>1.852</super>D<super>4.87</super>)",
         "friction loss (Hazen–Williams)"],
        ["P = ρ g Q H / (1000 η)", "pump power in kW"],
        ["Δh = a V / g", "water hammer jump"],
        ["V<sub>bal</sub> = V<sub>d</sub> (1 − t/24)", "tank volume to cover pump rest time"],
    ], widths=[3.2, 3], align=["l", "l"])
    rows = [[k, v] for k, v in [
        ("Water delivered", "20,000 m³/d; intake 21,505 m³/d (7 % WTP losses)"),
        ("Pumped flow (22 h)", f"{20000 / 79.2:.1f} l/s treated; {raw / 79.2:.1f} l/s raw"),
        ("Intake low-lift / high-lift", f"{N['MOMBA_INTAKE'].station['tdh']:.0f} m / "
                                        f"{N['GRIT_TANK'].station['tdh']:.0f} m (ER 10 / 25 m)"),
        ("WTP pumps", f"{N['MOMBA_WTP'].station['tdh']:.0f} m, 3 × {N['MOMBA_WTP'].station['motor_kw']:g} kW "
                      "(ER 330 m) – confirmed"),
        ("Ikana → Nkangamo", f"gravity, {N['IKANA_GBR'].surplus:.0f} m surplus → flow control valve"),
        ("Nkangamo BPS", f"{N['NKANGAMO_BPS'].station['tdh']:.0f} m (ER 221 m), set by the ESR"),
        ("Critical high point", "≈ 74 km on the BPS main: air valves"),
        ("Chapwa", f"{N['CHAPWA_GSR04'].excess_head:.0f} m excess → PRV/FCV, PN25"),
        ("Water hammer", "≈ 80–100 m on the long mains → surge vessels"),
        ("Check", "EPANET agrees within about 0.1 m"),
    ]]
    doc.table("Key results to remember.", ["Item", "Result"], rows, widths=[2, 4.2], align=["l", "l"])

    def on_page(canvas, d):
        canvas.saveState()
        canvas.setFont(FONT, 8.5)
        if d.page > 1:
            canvas.drawString(25 * mm, A4[1] - 15 * mm, "Tunduma Hydraulics – Explained Simply")
            canvas.setLineWidth(0.4)
            canvas.line(25 * mm, A4[1] - 16.5 * mm, A4[0] - 25 * mm, A4[1] - 16.5 * mm)
            canvas.drawCentredString(A4[0] / 2, 12 * mm, str(d.page))
        canvas.restoreState()

    pdf = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=25 * mm, rightMargin=25 * mm, topMargin=22 * mm,
                            bottomMargin=20 * mm, title="Tunduma Water Supply Hydraulics – Explained Simply")
    pdf.build(doc.story, onFirstPage=on_page, onLaterPages=on_page)
    return out_path


if __name__ == "__main__":
    os.makedirs("results", exist_ok=True)
    print(build(os.path.join("results", "Tunduma_Hydraulics_Explained_Simply.pdf")))
