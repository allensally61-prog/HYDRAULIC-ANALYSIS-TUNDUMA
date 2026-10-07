#!/usr/bin/env python3
"""Excel zone calculator: one sheet per hydraulic zone, every result a live Excel formula.

    python make_zone_workbook.py   -> results/Tunduma_Zone_Calculator.xlsx

The starting values come from tunduma_config.json and the survey alignment (same model as
run_analysis.py). In Excel, change any blue input cell and the zone recalculates: flows,
Hazen-Williams losses, HGL, Bernoulli pump head / gravity surplus, power, motor, energy,
pressures at critical points, PN class and surge. The 'Profile' sheet checks the pressure at
every surveyed point.
"""
import os

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

import build_model
import water_hydraulics as wh

FONT = "Arial"
F_IN = Font(name=FONT, size=10, color="0000FF")             # inputs: blue
F_CALC = Font(name=FONT, size=10, color="000000")           # formulas: black
F_LINK = Font(name=FONT, size=10, color="008000")           # links to other sheets: green
F_HEAD = Font(name=FONT, size=10, bold=True, color="FFFFFF")
F_BOLD = Font(name=FONT, size=10, bold=True)
F_TITLE = Font(name=FONT, size=14, bold=True)
F_SUB = Font(name=FONT, size=10, italic=True, color="555555")
F_KEY = Font(name=FONT, size=11, bold=True)
FILL_IN = PatternFill("solid", fgColor="FFFF99")             # key assumptions / editable
FILL_HEAD = PatternFill("solid", fgColor="1F4E78")
FILL_SEC = PatternFill("solid", fgColor="D9E1F2")
FILL_RES = PatternFill("solid", fgColor="E2EFDA")
THIN = Side(style="thin", color="999999")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


class Sheet:
    """Small helper to write labelled rows and remember cell addresses."""

    def __init__(self, ws):
        self.ws = ws
        self.r = 1

    def cell(self, row, col, value, font=F_CALC, fmt=None, fill=None, border=True, align=None):
        c = self.ws.cell(row=row, column=col, value=value)
        c.font = font
        if fmt:
            c.number_format = fmt
        if fill:
            c.fill = fill
        if border:
            c.border = BOX
        if align:
            c.alignment = align
        return c

    def title(self, text, sub=None):
        self.cell(self.r, 1, text, F_TITLE, border=False)
        self.r += 1
        if sub:
            self.cell(self.r, 1, sub, F_SUB, border=False)
            self.r += 1
        self.r += 1

    def section(self, text, width=8):
        for c in range(1, width + 1):
            self.cell(self.r, c, text if c == 1 else None, F_BOLD, fill=FILL_SEC)
        self.r += 1

    def row(self, label, value, unit="", note="", kind="calc", fmt="#,##0.00"):
        """Label | value | unit | note. kind: input, calc, link, key."""
        font = {"input": F_IN, "calc": F_CALC, "link": F_LINK, "key": F_KEY}[kind]
        self.cell(self.r, 1, label)
        c = self.cell(self.r, 2, value, font, fmt, FILL_IN if kind == "input" else
                      (FILL_RES if kind == "key" else None))
        self.cell(self.r, 3, unit)
        self.cell(self.r, 4, note, F_SUB, align=Alignment(wrap_text=False))
        ref = f"$B${self.r}"
        self.r += 1
        return ref

    def header(self, cols, row=None):
        row = row or self.r
        for i, h in enumerate(cols, 1):
            self.cell(row, i, h, F_HEAD, fill=FILL_HEAD, align=Alignment(wrap_text=True, vertical="center"))
        self.ws.row_dimensions[row].height = 42
        self.r = row + 1


def q(name):
    """Quoted sheet name for formulas."""
    return f"'{name}'"


def build(out_path, cfg_path="tunduma_config.json"):
    cfg = build_model.load_config(cfg_path)
    al = build_model.prepare_alignment(cfg)
    data, routes = build_model.build_engine_model(cfg, al)
    s = wh.System(data).solve()
    st = s.settings
    N, L = s.nodes, {l.id: l for l in s.links}
    fac = {f["id"]: f for f in cfg["facilities"]}
    lcfg = {l["id"]: l for l in cfg["links"]}
    wb = Workbook()

    # ================================================================ Read Me
    ws = wb.active
    ws.title = "Read Me"
    sh = Sheet(ws)
    sh.title("Tunduma Water Supply – Zone Calculator",
             "Hydraulic analysis split by zone, from the Momba River intake to the Tunduma tanks. "
             "All results are live Excel formulas.")
    lines = [
        ("HOW TO USE", None),
        ("1. Change only the cells with BLUE text on a YELLOW background (inputs). Everything else is a formula.", None),
        ("2. Global constants (minor losses, station losses, cover, min. pressure, wave speed, PN classes) are on 'Global'.", None),
        ("3. Tank demands and WTP losses are on 'Demands'; the flow in every pipe is worked out there.", None),
        ("4. Each zone sheet: inputs → pipe table (Hazen-Williams) → destinations → critical points → Bernoulli result.", None),
        ("5. 'Summary' collects every zone; 'Storage' checks tank balancing; 'Profile' checks the pressure at every survey point.", None),
        ("", None),
        ("COLOUR LEGEND", None),
        ("Blue text, yellow fill", "input / assumption – edit these"),
        ("Black text", "formula – do not overwrite"),
        ("Green text", "link from another sheet"),
        ("Green fill, bold", "key result"),
        ("", None),
        ("ZONES (split at every free water surface)", None),
        ("Z1 River-Intake", "gravity: Momba River → intake sump (abstraction pipe)"),
        ("Z2 Intake-Grit", "pumped: low-lift pumps, intake sump → grit tank"),
        ("Z3 Grit-WTP", "pumped: high-lift pumps, grit tank → WTP inlet (raw-water main)"),
        ("Z4 WTP-Ikana", "pumped: WTP clear-water pumps → Ikana GBR (treated-water rising main)"),
        ("Z5 Ikana-Nkangamo", "gravity: Ikana GBR → Nkangamo BPS sump"),
        ("Z6 Nkangamo-Uhuru", "pumped: Nkangamo BPS → J-001N (ESR), J-002N (GSR01), J-003N (Ipito) → Uhuru Park GBR"),
        ("Z7 Uhuru-Chapwa", "gravity: Uhuru Park GBR → J-004N → Makambini GSR03 and Chapwa GSR04"),
        ("", None),
        ("METHOD (Bernoulli / energy equation between two water surfaces)", None),
        ("z1 + p1/ρg + V1²/2g + Hp = z2 + p2/ρg + V2²/2g + hL", "at tank surfaces p = 0 and V ≈ 0"),
        ("Pumped zone", "Hp = H_req − z1 ;  TDH = Hp + station losses"),
        ("Gravity zone", "surplus = z1 − H_req  (≥ 0 OK, burnt by an FCV/PRV; < 0 short of head)"),
        ("H_req (head needed at zone start)", "largest of: each destination inlet + residual + losses on the way, "
                                              "and each critical point crown + min. pressure + losses up to it"),
        ("Friction (Hazen-Williams)", "hf = 10.67 L Q^1.852 / (C^1.852 D^4.8704) ;  hL = hf × (1 + minor-loss factor)"),
        ("Pressure at a point", "p = HGL − pipe crown ;  working = max(p, static level − crown) ;  PN = smallest class ≥ working/10.2"),
        ("Surge (Joukowsky)", "Δh = a V / g"),
        ("", None),
        ("SOURCE", None),
        ("Starting values", "tunduma_config.json (Employer's Requirements + ASSUMED levels) and the topographic survey; "
                            "same data as run_analysis.py. Column 'Python model' on Summary shows the script result for checking."),
    ]
    for a, b in lines:
        bold = b is None and a.isupper()
        sh.cell(sh.r, 1, a, F_BOLD if bold else F_CALC, border=False)
        if b:
            sh.cell(sh.r, 2, b, F_CALC, border=False)
        sh.r += 1
    ws["A11"].font = F_IN
    ws["A11"].fill = FILL_IN
    ws["A13"].font = F_LINK
    ws["A14"].font = F_KEY
    ws["A14"].fill = FILL_RES
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 120

    # ================================================================ Global
    ws = wb.create_sheet("Global")
    sh = Sheet(ws)
    sh.title("Global constants and design criteria", "Used by every zone (named cells).")
    names = {}

    def gname(name, label, value, unit, note, fmt="0.00"):
        ref = sh.row(label, value, unit, note, "input", fmt)
        wb.defined_names[name] = DefinedName(name, attr_text=f"Global!{ref}")
        names[name] = ref

    sh.section("Constants and criteria", 4)
    gname("g", "Gravitational acceleration g", 9.81, "m/s²", "physical constant")
    gname("k_minor", "Minor losses as fraction of friction", st["minor_loss_factor"], "–",
          "ASSUMED 10 % (bends, valves, fittings)")
    gname("h_station", "Losses inside each pump station", st["station_losses"], "m", "ASSUMED pipework/valves/meter")
    gname("h_res", "Residual head above a tank inlet", st["terminal_residual_head"], "m", "ASSUMED safety margin")
    gname("cover", "Pipe crown depth below ground", st["pipe_cover"], "m", "ASSUMED")
    gname("p_min", "Minimum pressure at pipe crown along mains", s.pipe_pmin, "m", "ASSUMED")
    gname("p_min_j", "Minimum pressure at junctions / delivery", st["min_pressure_head"], "m", "ER Table 7")
    gname("wave", "Pressure wave speed a (steel)", cfg["pipe_defaults"]["wave_speed"], "m/s", "ASSUMED, for surge")
    gname("motor_margin", "Motor size margin over shaft power", st["motor_margin"], "–", "common practice")
    gname("tariff", "Electricity tariff", st["electricity_tariff"], "per kWh", "enter the TANESCO tariff")
    gname("bar_per_m", "Bar per metre of water", 0.0981, "bar/m", "ρg/10⁵")
    gname("C_default", "Default Hazen-Williams C", cfg["pipe_defaults"]["hw_c"], "–", "ASSUMED, cement-lined steel (aged)")
    sh.r += 1
    sh.section("Pipe pressure classes (PN, bar)", 4)
    start = sh.r
    for pn in st["pn_classes"]:
        sh.cell(sh.r, 1, f"PN{pn}")
        sh.cell(sh.r, 2, pn, F_IN, "0", FILL_IN)
        sh.r += 1
    wb.defined_names["PN_list"] = DefinedName("PN_list", attr_text=f"Global!$B${start}:$B${sh.r - 1}")
    sh.r += 1
    sh.section("Standard motor sizes (kW)", 4)
    start = sh.r
    for kw in wh.MOTOR_KW:
        sh.cell(sh.r, 2, kw, F_IN, "0.0#", FILL_IN)
        sh.r += 1
    wb.defined_names["Motor_list"] = DefinedName("Motor_list", attr_text=f"Global!$B${start}:$B${sh.r - 1}")
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 9
    ws.column_dimensions["D"].width = 48

    # ================================================================ Demands
    ws = wb.create_sheet("Demands")
    sh = Sheet(ws)
    sh.title("Demands and design flows", "Daily volumes (m³/d) supplied by each tank; pipe volumes follow by mass balance.")
    sh.section("Tank demands (ER schematic, design year 2035)", 4)
    dem = {}
    for tid, label in (("UHURU_PARK_GBR", "Uhuru Park GBR – town supply"), ("UHURU_GSR01", "Existing Uhuru GSR 01"),
                       ("TUNDUMA_ESR", "Existing Tunduma ESR"), ("IPITO_GSR02", "Existing Ipito GSR 02"),
                       ("MAKAMBINI_GSR03", "Existing Makambini GSR 03"), ("CHAPWA_GSR04", "Existing Chapwa GSR 04")):
        dem[tid] = sh.row(label, N[tid].demand, "m³/d", "ER schematic", "input", "#,##0.00")
    loss = sh.row("WTP + intake-to-WTP losses", N["MOMBA_WTP"].loss, "–", "ER Table 8: 2 % + 5 %", "input", "0.0%")
    sh.r += 1
    sh.section("Daily volume in each pipe (mass balance, downstream → upstream)", 4)
    D = {}
    D["MAKAMBINI_BRANCH"] = sh.row("J-004N → Makambini", f"={dem['MAKAMBINI_GSR03']}", "m³/d")
    D["CHAPWA_BRANCH"] = sh.row("J-004N → Chapwa", f"={dem['CHAPWA_GSR04']}", "m³/d")
    D["UHURU_J004N"] = sh.row("Uhuru Park → J-004N", f"={D['MAKAMBINI_BRANCH']}+{D['CHAPWA_BRANCH']}", "m³/d")
    D["UHURU_INLET"] = sh.row("J-003N → Uhuru Park GBR", f"={dem['UHURU_PARK_GBR']}+{D['UHURU_J004N']}", "m³/d")
    D["IPITO_BRANCH"] = sh.row("J-003N → Ipito", f"={dem['IPITO_GSR02']}", "m³/d")
    D["GSR01_BRANCH"] = sh.row("J-002N → GSR01", f"={dem['UHURU_GSR01']}", "m³/d")
    D["ESR_BRANCH"] = sh.row("J-001N → ESR", f"={dem['TUNDUMA_ESR']}", "m³/d")
    D["BPS_RM_3"] = sh.row("J-002N → J-003N", f"={D['UHURU_INLET']}+{D['IPITO_BRANCH']}", "m³/d")
    D["BPS_RM_2"] = sh.row("J-001N → J-002N", f"={D['BPS_RM_3']}+{D['GSR01_BRANCH']}", "m³/d")
    D["BPS_RM_1"] = sh.row("Nkangamo BPS → J-001N", f"={D['BPS_RM_2']}+{D['ESR_BRANCH']}", "m³/d")
    D["IKANA_NKANGAMO_GM"] = sh.row("Ikana GBR → Nkangamo BPS", f"={D['BPS_RM_1']}", "m³/d")
    D["WTP_IKANA_RM"] = sh.row("WTP → Ikana GBR (net WTP output)", f"={D['IKANA_NKANGAMO_GM']}", "m³/d", "", "key")
    D["RAW_MAIN"] = sh.row("Raw water: intake → WTP", f"={D['WTP_IKANA_RM']}/(1-{loss})", "m³/d",
                           "net ÷ (1 − losses)", "key")
    D["LL_DELIVERY"] = sh.row("Low-lift → grit tank", f"={D['RAW_MAIN']}", "m³/d")
    D["ABSTRACTION"] = sh.row("River → intake sump", f"={D['RAW_MAIN']}", "m³/d")
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 8
    ws.column_dimensions["D"].width = 30

    # ================================================================ zones
    def points_for(lid, extra=()):
        """Critical points of a pipe from the model: governing high point and deepest point."""
        l = L[lid]
        if l.id not in routes:
            return list(extra)
        inner = [r for r in l.rows[1:-1]]
        if not inner:
            return list(extra)
        hi = max(inner, key=lambda r: r[1] + l.hloss * r[0] / l.length)
        lo = min(inner, key=lambda r: r[1])
        pts = [(lid, hi[0], hi[1] + st["pipe_cover"], "critical high point"),
               (lid, lo[0], lo[1] + st["pipe_cover"], "lowest point (highest static pressure)")]
        if l.gov_point:
            x, z = l.gov_point
            if all(abs(x - p[1]) > 1 for p in pts):
                pts.insert(0, (lid, x, z + st["pipe_cover"], "governing point (model)"))
        return pts + list(extra)

    def dest(tid, lid, res=None):
        nd = N[tid]
        return (tid, lid, nd.inlet_level, res)

    zones = [
        dict(sheet="Z1 River-Intake", title="Zone 1 – Momba River to intake sump (gravity)", kind="gravity",
             start="MOMBA_RIVER", start_label="River low water level (LWL)", z1=N["MOMBA_RIVER"].min_level,
             twl=N["MOMBA_RIVER"].max_level, hours=N["MOMBA_INTAKE"].pumps["operating_hours"],
             hours_note="carries the intake pump flow (22 h)",
             pipes=[("ABSTRACTION", None)], dests=[dest("MOMBA_INTAKE", "ABSTRACTION", 0.0)],
             points=[], static=N["MOMBA_RIVER"].max_level),
        dict(sheet="Z2 Intake-Grit", title="Zone 2 – Intake low-lift pumps to grit tank (pumped)", kind="pumped",
             start="MOMBA_INTAKE", start_label="Intake sump LWL (pump suction)", z1=N["MOMBA_INTAKE"].min_level,
             hours=N["MOMBA_INTAKE"].pumps["operating_hours"], pipes=[("LL_DELIVERY", None)],
             dests=[dest("GRIT_TANK", "LL_DELIVERY")], points=[], static=N["GRIT_TANK"].inlet_level),
        dict(sheet="Z3 Grit-WTP", title="Zone 3 – Grit tank high-lift pumps to the WTP (pumped)", kind="pumped",
             start="GRIT_TANK", start_label="Grit tank LWL (pump suction)", z1=N["GRIT_TANK"].min_level,
             hours=N["GRIT_TANK"].pumps["operating_hours"], pipes=[("RAW_MAIN", None)],
             dests=[dest("MOMBA_WTP", "RAW_MAIN")], points=points_for("RAW_MAIN"),
             static=N["MOMBA_WTP"].inlet_level),
        dict(sheet="Z4 WTP-Ikana", title="Zone 4 – WTP clear-water pumps to Ikana GBR (pumped)", kind="pumped",
             start="MOMBA_WTP", start_label="Clear-water tank LWL (pump suction)", z1=N["MOMBA_WTP"].min_level,
             hours=N["MOMBA_WTP"].pumps["operating_hours"], pipes=[("WTP_IKANA_RM", None)],
             dests=[dest("IKANA_GBR", "WTP_IKANA_RM")], points=points_for("WTP_IKANA_RM"),
             static=N["IKANA_GBR"].max_level),
        dict(sheet="Z5 Ikana-Nkangamo", title="Zone 5 – Ikana GBR to Nkangamo BPS (gravity)", kind="gravity",
             start="IKANA_GBR", start_label="Ikana GBR bottom water level (BWL)", z1=N["IKANA_GBR"].min_level,
             twl=N["IKANA_GBR"].max_level, hours=st["gravity_hours"], pipes=[("IKANA_NKANGAMO_GM", None)],
             dests=[dest("NKANGAMO_BPS", "IKANA_NKANGAMO_GM")], points=points_for("IKANA_NKANGAMO_GM"),
             static=N["IKANA_GBR"].max_level),
        dict(sheet="Z6 Nkangamo-Uhuru", title="Zone 6 – Nkangamo BPS to Uhuru Park GBR and existing tanks (pumped)",
             kind="pumped", start="NKANGAMO_BPS", start_label="Nkangamo sump LWL (pump suction)",
             z1=N["NKANGAMO_BPS"].min_level, hours=N["NKANGAMO_BPS"].pumps["operating_hours"],
             pipes=[("BPS_RM_1", None), ("BPS_RM_2", "BPS_RM_1"), ("BPS_RM_3", "BPS_RM_2"),
                    ("UHURU_INLET", "BPS_RM_3"), ("ESR_BRANCH", "BPS_RM_1"), ("GSR01_BRANCH", "BPS_RM_2"),
                    ("IPITO_BRANCH", "BPS_RM_3")],
             dests=[dest("TUNDUMA_ESR", "ESR_BRANCH"), dest("UHURU_GSR01", "GSR01_BRANCH"),
                    dest("IPITO_GSR02", "IPITO_BRANCH"), dest("UHURU_PARK_GBR", "UHURU_INLET")],
             points=points_for("BPS_RM_1") + points_for("IPITO_BRANCH"), static=N["TUNDUMA_ESR"].max_level),
        dict(sheet="Z7 Uhuru-Chapwa", title="Zone 7 – Uhuru Park GBR to Makambini and Chapwa (gravity)",
             kind="gravity", start="UHURU_PARK_GBR", start_label="Uhuru Park GBR bottom water level (BWL)",
             z1=N["UHURU_PARK_GBR"].min_level, twl=N["UHURU_PARK_GBR"].max_level, hours=st["gravity_hours"],
             pipes=[("UHURU_J004N", None), ("MAKAMBINI_BRANCH", "UHURU_J004N"), ("CHAPWA_BRANCH", "UHURU_J004N")],
             dests=[dest("MAKAMBINI_GSR03", "MAKAMBINI_BRANCH"), dest("CHAPWA_GSR04", "CHAPWA_BRANCH")],
             points=points_for("UHURU_J004N") + points_for("CHAPWA_BRANCH"), static=N["UHURU_PARK_GBR"].max_level),
    ]

    prof_last = 4 + sum(len(l.points) for l in s.links)      # Profile sheet: header row 4, data from row 5
    zone_refs = {}
    pipe_rows = {}                     # pipe id -> (sheet, row)
    for z in zones:
        ws = wb.create_sheet(z["sheet"])
        sh = Sheet(ws)
        sh.title(z["title"], "Bernoulli between the water surface at the start and the inlet of each destination. "
                             "Blue/yellow cells are inputs.")
        sh.section("A. Inputs", 4)
        z1 = sh.row(z["start_label"], z["z1"], "m a.s.l.", "point 1 of Bernoulli (worst case: lowest level)",
                    "input")
        twl = sh.row("Top water level at start (TWL)", z.get("twl", z["z1"]), "m a.s.l.",
                     "used for static pressure in gravity zones", "input") if z["kind"] == "gravity" else None
        hours = sh.row("Operating hours per day", z["hours"], "h/d", z.get("hours_note", "ER: pumps 22 h/d; gravity 24 h/d"),
                       "input", "0.0")
        static = sh.row("Static level for pressure class", z["static"], "m a.s.l.",
                        "highest water level the pipe can see when flow stops", "input")
        if z["kind"] == "pumped":
            p = fac[z["start"]]["pumps"]
            duty = sh.row("Number of duty pumps", p["duty"], "no.", "", "input", "0")
            stby = sh.row("Number of standby pumps", p["standby"], "no.", "", "input", "0")
            eff = sh.row("Pump efficiency η_p", p["efficiency"], "–", "ASSUMED", "input", "0.00")
            meff = sh.row("Motor efficiency η_m", p["motor_efficiency"], "–", "ASSUMED", "input", "0.00")
            er_q = sh.row("ER duty flow per pump", p["er_duty"]["q_m3h"], "m³/h", "Employer's Requirements", "input",
                          "#,##0")
            er_h = sh.row("ER duty head", p["er_duty"]["head_m"], "m", "Employer's Requirements", "input", "#,##0.0")
        sh.r += 1

        # ---- pipe table
        sh.section("B. Pipes – continuity and Hazen-Williams friction", 20)
        cols = ["Pipe", "From", "To", "Upstream pipe", "DN", "Internal D (mm)", "Length L (m)", "C (H-W)",
                "Daily volume (m³/d)", "Q (m³/s)", "Q (l/s)", "Area (m²)", "V (m/s)", "hf friction (m)",
                "hm minor (m)", "hL total (m)", "Gradient (m/km)", "Loss before this pipe (m)", "HGL start (m)",
                "HGL end (m)", "Surge Δh = aV/g (m)"]
        sh.header(cols)
        first = sh.r
        rows = {}
        for lid, parent in z["pipes"]:
            l = L[lid]
            r = sh.r
            rows[lid] = r
            pipe_rows[lid] = (z["sheet"], r)
            sh.cell(r, 1, lid, F_BOLD)
            sh.cell(r, 2, l.frm)
            sh.cell(r, 3, l.to)
            sh.cell(r, 4, parent or "–")
            sh.cell(r, 5, l.dn, F_IN, "0", FILL_IN)
            sh.cell(r, 6, f"=E{r}", F_CALC, "0.0").comment = Comment(
                "Internal diameter. Defaults to DN; overwrite with the real ID (e.g. lined steel) if known.", "model")
            sh.cell(r, 7, round(l.length, 1), F_IN, "#,##0.0", FILL_IN).comment = Comment(
                lcfg[lid].get("er", "") + (f" | ER length {lcfg[lid]['er_length']:,} m" if lcfg[lid].get('er_length')
                                           else "") + " | model length measured along the surveyed slope", "model")
            sh.cell(r, 8, "=C_default", F_IN, "0", FILL_IN)
            sh.cell(r, 9, f"=Demands!{D[lid]}", F_LINK, "#,##0.0")
            sh.cell(r, 10, f"=I{r}/({hours}*3600)", fmt="0.0000")
            sh.cell(r, 11, f"=J{r}*1000", fmt="0.0")
            sh.cell(r, 12, f"=PI()*(F{r}/1000)^2/4", fmt="0.0000")
            sh.cell(r, 13, f"=J{r}/L{r}", fmt="0.000")
            sh.cell(r, 14, f"=10.67*G{r}*J{r}^1.852/(H{r}^1.852*(F{r}/1000)^4.8704)", fmt="0.00")
            sh.cell(r, 15, f"=k_minor*N{r}", fmt="0.00")
            sh.cell(r, 16, f"=N{r}+O{r}", fmt="0.00")
            sh.cell(r, 17, f"=P{r}/G{r}*1000", fmt="0.00")
            sh.cell(r, 18, f"=R{rows[parent]}+P{rows[parent]}" if parent else 0, fmt="0.00")
            sh.cell(r, 21, f"=wave*M{r}/g", fmt="0.0")
            sh.r += 1
        last = sh.r - 1
        sh.r += 1

        # ---- destinations
        sh.section("C. Destinations – Bernoulli to each receiving water surface", 9)
        sh.header(["Destination", "Ends with pipe", "Inlet level (m)", "Residual (m)", "Level needed z2 (m)",
                   "Head needed at zone start = z2 + losses (m)", "Arriving HGL (m)", "Excess head (m)",
                   "Comment"])
        dfirst = sh.r
        for tid, lid, inlet, res in z["dests"]:
            r = sh.r
            pr = rows[lid]
            sh.cell(r, 1, tid, F_BOLD)
            sh.cell(r, 2, lid)
            sh.cell(r, 3, inlet, F_IN, "#,##0.00", FILL_IN)
            sh.cell(r, 4, "=h_res" if res is None else res, F_IN, "0.00", FILL_IN)
            sh.cell(r, 5, f"=C{r}+D{r}", fmt="#,##0.00")
            sh.cell(r, 6, f"=E{r}+R{pr}+P{pr}", fmt="#,##0.00")
            sh.cell(r, 7, f"=T{pr}", fmt="#,##0.00")
            sh.cell(r, 8, f"=G{r}-E{r}", fmt="#,##0.00")
            sh.cell(r, 9, f'=IF(H{r}<-0.005,"NOT REACHED",IF(H{r}>5,"fit flow control valve / PRV","OK"))')
            sh.r += 1
        dlast = sh.r - 1
        sh.r += 1

        # ---- critical points
        sh.section("D. Critical points along the pipes – pressure check (add your own rows)", 14)
        sh.header(["Pipe", "Chainage in pipe x (m)", "Ground level (m)", "Pipe crown (m)", "Head needed at zone "
                   "start (m)", "HGL at point (m)", "Pressure (m)", "Static (m)", "Working (m)", "Working (bar)",
                   "PN required", "Transient min = p − Δh (m)", "Note", "Status"])
        pfirst = sh.r
        n_blank = 3
        for i in range(len(z["points"]) + n_blank):
            r = sh.r
            if i < len(z["points"]):
                lid, x, ground, note = z["points"][i]
                sh.cell(r, 1, lid, F_IN, fill=FILL_IN)
                sh.cell(r, 2, round(x, 1), F_IN, "#,##0.0", FILL_IN)
                sh.cell(r, 3, round(ground, 2), F_IN, "#,##0.00", FILL_IN)
                sh.cell(r, 13, note, F_SUB)
            else:
                for c in (1, 2, 3):
                    sh.cell(r, c, None, F_IN, fill=FILL_IN)
                sh.cell(r, 13, "add a point: pipe ID, chainage, ground level", F_SUB)
            m = f"MATCH($A{r},$A${first}:$A${last},0)"
            idx = lambda col: f"INDEX(${col}${first}:${col}${last},{m})"   # noqa: E731
            blank = f'IF($A{r}="","",'
            sh.cell(r, 4, f"={blank}C{r}-cover)", fmt="#,##0.00")
            sh.cell(r, 5, f"={blank}D{r}+p_min+{idx('R')}+{idx('P')}*B{r}/{idx('G')})", fmt="#,##0.00")
            sh.cell(r, 6, f"={blank}{idx('S')}-{idx('P')}*B{r}/{idx('G')})", fmt="#,##0.00")
            sh.cell(r, 7, f"={blank}F{r}-D{r})", fmt="#,##0.0")
            sh.cell(r, 8, f"={blank}{static}-D{r})", fmt="#,##0.0")
            sh.cell(r, 9, f"={blank}MAX(G{r},H{r}))", fmt="#,##0.0")
            sh.cell(r, 10, f"={blank}I{r}*bar_per_m)", fmt="0.0")
            sh.cell(r, 11, f'={blank}IFERROR("PN"&SMALL(PN_list,COUNTIF(PN_list,"<"&J{r})+1),"> max PN"))')
            sh.cell(r, 12, f"={blank}G{r}-{idx('U')})", fmt="#,##0.0")
            sh.cell(r, 14, f'={blank}IF(G{r}<0,"NEGATIVE PRESSURE",IF(G{r}<p_min-0.005,"below minimum","OK")))')
            sh.r += 1
        plast = sh.r - 1
        sh.r += 1

        # ---- result
        sh.section("E. Bernoulli result", 4)
        hreq = sh.row("Head needed at zone start H_req", f"=MAX($F${dfirst}:$F${dlast},$E${pfirst}:$E${plast})",
                      "m a.s.l.", "largest of section C (destinations) and section D (points)", "key")
        gov = sh.row("Set by", f'=IF(MAX($F${dfirst}:$F${dlast})>=MAX($E${pfirst}:$E${plast}),'
                               f'INDEX($A${dfirst}:$A${dlast},MATCH(MAX($F${dfirst}:$F${dlast}),$F${dfirst}:$F${dlast},0)),'
                               f'"point on "&INDEX($A${pfirst}:$A${plast},MATCH(MAX($E${pfirst}:$E${plast}),'
                               f'$E${pfirst}:$E${plast},0)))', "", "governing destination or point", "calc", "@")
        res = {"sheet": z["sheet"], "kind": z["kind"], "hreq": hreq, "gov": gov, "first": first, "z1": z1}
        if z["kind"] == "pumped":
            hstart = hreq
            lift = sh.row("Bernoulli: Hp = H_req − z1", f"={hreq}-{z1}", "m",
                          "z1 + 0 + 0 + Hp = H_req  (p = 0, V ≈ 0 at the sump surface)")
            tdh = sh.row("Pump head TDH = Hp + station losses", f"={lift}+h_station", "m", "", "key")
            qtot = sh.row("Total pumped flow", f"=J{first}", "m³/s", "flow in the first pipe")
            qp = sh.row("Flow per pump", f"={qtot}/{duty}", "m³/s")
            sh.row("Flow per pump", f"={qp}*3600", "m³/h", "compare ER duty flow", "calc", "#,##0")
            ph = sh.row("Hydraulic power per pump P_h = ρgQH", f"=1000*g*{qp}*{tdh}/1000", "kW", "", "calc", "#,##0.0")
            ps = sh.row("Shaft power per pump P_s = P_h / η_p", f"={ph}/{eff}", "kW", "", "key", "#,##0.0")
            mreq = sh.row("Motor needed = P_s × margin", f"={ps}*motor_margin", "kW", "", "calc", "#,##0.0")
            motor = sh.row("Standard motor per pump", f'=IFERROR(SMALL(Motor_list,COUNTIF(Motor_list,"<"&{mreq})+1),'
                                                       f'"> list")', "kW", "next size up", "key", "#,##0.0")
            energy = sh.row("Electricity per day", f"={duty}*{ps}*{hours}/{meff}", "kWh/d", "", "calc", "#,##0")
            spec = sh.row("Specific energy", f"={energy}/I{first}", "kWh/m³", "", "calc", "0.000")
            cost = sh.row("Electricity cost per year", f"={energy}*365*tariff", "per year", "uses Global tariff",
                          "calc", "#,##0")
            diff = sh.row("TDH minus ER duty head", f"={tdh}-{er_h}", "m",
                          "negative = ER pump has spare head (throttle / VFD)", "calc", "+0.0;-0.0")
            res.update(tdh=tdh, motor=motor, energy=energy, ps=ps, er_h=er_h, diff=diff, qp=qp, spec=spec)
        else:
            hstart = z1
            surplus = sh.row("Bernoulli: surplus = z1 − H_req", f"={z1}-{hreq}", "m",
                             "z1 = H_req + surplus  (no pump)", "key")
            sh.row("Status", f'=IF({surplus}<-0.005,"SHORT OF HEAD – bigger pipe, lower outlet or pump",'
                             f'"OK – "&TEXT({surplus},"0.0")&" m to burn with a flow control valve / PRV")',
                   "", "", "calc", "@")
            res.update(surplus=surplus)
        # HGL columns need the zone start head
        for lid, parent in z["pipes"]:
            r = rows[lid]
            sh.cell(r, 19, f"={hstart}-R{r}", fmt="#,##0.00")
            sh.cell(r, 20, f"=S{r}-P{r}", fmt="#,##0.00")
        sh.row("Lowest pressure at any survey point (sheet Profile)",
               f'=_xlfn.MINIFS(Profile!$H$5:$H${prof_last},Profile!$A$5:$A${prof_last},"{z["sheet"]}",'
               f'Profile!$L$5:$L${prof_last},"yes")', "m",
               "if below the minimum, add that point to section D", "calc", "#,##0.0")
        res["hstart"] = hstart
        zone_refs[z["sheet"]] = res

        widths = [22, 14, 16, 14, 9, 11, 12, 9, 12, 10, 9, 10, 9, 11, 10, 10, 11, 12, 12, 12, 12]
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.column_dimensions["A"].width = 44
        ws.column_dimensions["D"].width = 16
        ws.freeze_panes = "B4"

    # ================================================================ Storage
    ws = wb.create_sheet("Storage")
    sh = Sheet(ws)
    sh.title("Storage – balancing for pump rest hours", "V_bal = inflow × (1 − hours/24); emergency = outflow × hours/24")
    sh.header(["Tank", "Daily inflow (m³/d)", "Inflow hours (h/d)", "Balancing volume (m³)", "Emergency hours",
               "Emergency volume (m³)", "Required (m³)", "Actual volume (m³)", "Storage (h of outflow)", "Status"])
    tank_in = {"IKANA_GBR": ("WTP_IKANA_RM", "Z4 WTP-Ikana"), "UHURU_PARK_GBR": ("UHURU_INLET", "Z6 Nkangamo-Uhuru"),
               "TUNDUMA_ESR": ("ESR_BRANCH", "Z6 Nkangamo-Uhuru"), "UHURU_GSR01": ("GSR01_BRANCH", "Z6 Nkangamo-Uhuru"),
               "IPITO_GSR02": ("IPITO_BRANCH", "Z6 Nkangamo-Uhuru"),
               "MAKAMBINI_GSR03": ("MAKAMBINI_BRANCH", "Z7 Uhuru-Chapwa"),
               "CHAPWA_GSR04": ("CHAPWA_BRANCH", "Z7 Uhuru-Chapwa"), "NKANGAMO_BPS": ("IKANA_NKANGAMO_GM", "Z5 Ikana-Nkangamo")}
    for tid, (lid, zs) in tank_in.items():
        r = sh.r
        sheet, pr = pipe_rows[lid]
        sh.cell(r, 1, tid, F_BOLD)
        sh.cell(r, 2, f"={q(sheet)}!I{pr}", F_LINK, "#,##0")
        # hours = Q*86400/daily inverse: daily / (Q*3600)
        sh.cell(r, 3, f"={q(sheet)}!I{pr}/({q(sheet)}!J{pr}*3600)", F_LINK, "0.0")
        if tid == "NKANGAMO_BPS":
            sh.cell(r, 4, f"=B{r}*(1-{q('Z6 Nkangamo-Uhuru')}!$B$6/24)", fmt="#,##0").comment = Comment(
                "Sump receives 24 h gravity flow and pumps for the BPS hours: volume for the pump-off period.", "model")
        else:
            sh.cell(r, 4, f"=B{r}*(1-C{r}/24)", fmt="#,##0")
        sh.cell(r, 5, 0, F_IN, "0.0", FILL_IN)
        sh.cell(r, 6, f"=B{r}*E{r}/24", fmt="#,##0")
        sh.cell(r, 7, f"=D{r}+F{r}", fmt="#,##0")
        sh.cell(r, 8, N[tid].volume, F_IN, "#,##0", FILL_IN)
        sh.cell(r, 9, f"=H{r}/(B{r}/24)", fmt="0.0")
        sh.cell(r, 10, f'=IF(H{r}>=G{r},"OK","TOO SMALL")')
        sh.r += 1
    for i, w in enumerate([22, 14, 12, 14, 12, 14, 12, 14, 14, 12], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # ================================================================ Summary
    ws = wb.create_sheet("Summary", 1)
    sh = Sheet(ws)
    sh.title("Summary of all zones", "Linked to the zone sheets (green). 'Python model' = run_analysis.py result for "
                                     "the starting inputs, kept as a check.")
    sh.header(["Zone", "Type", "Flow (l/s)", "Velocity first pipe (m/s)", "hL first pipe (m)", "H_req (m a.s.l.)",
               "Set by", "Pump TDH (m) / gravity surplus (m)", "ER duty head (m)", "TDH − ER (m)", "Shaft kW per pump",
               "Motor kW per pump", "Energy (kWh/d)", "Python model (m)", "Excel − Python (m)"])
    py = {"Z1 River-Intake": N["MOMBA_RIVER"].surplus, "Z2 Intake-Grit": N["MOMBA_INTAKE"].station["tdh"],
          "Z3 Grit-WTP": N["GRIT_TANK"].station["tdh"], "Z4 WTP-Ikana": N["MOMBA_WTP"].station["tdh"],
          "Z5 Ikana-Nkangamo": N["IKANA_GBR"].surplus, "Z6 Nkangamo-Uhuru": N["NKANGAMO_BPS"].station["tdh"],
          "Z7 Uhuru-Chapwa": N["UHURU_PARK_GBR"].surplus}
    for name, rf in zone_refs.items():
        r = sh.r
        sn = q(name)
        sh.cell(r, 1, name, F_BOLD)
        sh.cell(r, 2, rf["kind"])
        sh.cell(r, 3, f"={sn}!K{rf['first']}", F_LINK, "#,##0.0")
        sh.cell(r, 4, f"={sn}!M{rf['first']}", F_LINK, "0.00")
        sh.cell(r, 5, f"={sn}!P{rf['first']}", F_LINK, "#,##0.00")
        sh.cell(r, 6, f"={sn}!{rf['hreq']}", F_LINK, "#,##0.00")
        sh.cell(r, 7, f"={sn}!{rf['gov']}", F_LINK)
        main = rf.get("tdh", rf.get("surplus"))
        sh.cell(r, 8, f"={sn}!{main}", F_LINK, "#,##0.0", FILL_RES)
        if rf["kind"] == "pumped":
            sh.cell(r, 9, f"={sn}!{rf['er_h']}", F_LINK, "#,##0.0")
            sh.cell(r, 10, f"={sn}!{rf['diff']}", F_LINK, "+0.0;-0.0")
            sh.cell(r, 11, f"={sn}!{rf['ps']}", F_LINK, "#,##0.0")
            sh.cell(r, 12, f"={sn}!{rf['motor']}", F_LINK, "#,##0.0")
            sh.cell(r, 13, f"={sn}!{rf['energy']}", F_LINK, "#,##0")
        else:
            for c in range(9, 14):
                sh.cell(r, c, "–")
        sh.cell(r, 14, round(py[name], 2), F_IN, "#,##0.00").comment = Comment(
            "Value from run_analysis.py (Python model) with the starting inputs. Fixed number, for checking.", "model")
        sh.cell(r, 15, f"=H{r}-N{r}", fmt="+0.00;-0.00;0.00")
        sh.r += 1
    tot = sh.r
    sh.cell(tot, 1, "Total pumping energy", F_BOLD)
    sh.cell(tot, 13, f"=SUM(M{tot - 7}:M{tot - 1})", F_KEY, "#,##0", FILL_RES)
    sh.r += 2
    sh.cell(sh.r, 1, "Pumped zones: column H is the pump head TDH. Gravity zones: column H is the spare energy "
                     "(≥ 0 OK, to be burnt by a valve; < 0 short of head).", F_SUB, border=False)
    for i, w in enumerate([22, 9, 10, 11, 10, 12, 26, 14, 10, 10, 10, 10, 12, 12, 12], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # ================================================================ Profile
    ws = wb.create_sheet("Profile")
    sh = Sheet(ws)
    sh.title("Pressure at every surveyed point", "HGL from the zone sheets; ground from the topographic survey. "
                                                 "Column L = 'no' for pipe ends at a water surface (not checked).")
    sh.header(["Zone", "Pipe", "Chainage in pipe (m)", "Ground (m)", "Pipe crown (m)", "HGL (m)", "Static (m)",
               "Pressure (m)", "Working (m)", "PN required", "Status", "Check?"])
    zone_of = {lid: z["sheet"] for z in zones for lid, _ in z["pipes"]}
    static_of = {}
    for z in zones:
        wsz = wb[z["sheet"]]
        for row in wsz.iter_rows(min_row=1, max_row=12, max_col=1):
            if row[0].value == "Static level for pressure class":
                static_of[z["sheet"]] = f"$B${row[0].row}"
    for l in s.links:
        sheet, pr = pipe_rows[l.id]
        sn = q(sheet)
        n_pts = len(l.points)
        frm_free, to_free = s.nodes[l.frm].is_free_surface, s.nodes[l.to].is_free_surface
        for i, (x, zc) in enumerate(l.points):
            r = sh.r
            sh.cell(r, 1, sheet, border=False)
            sh.cell(r, 2, l.id, border=False)
            sh.cell(r, 3, round(x, 2), F_IN, "#,##0.0", border=False)
            sh.cell(r, 4, round(zc + st["pipe_cover"], 2), F_IN, "#,##0.00", border=False)
            sh.cell(r, 5, f"=D{r}-cover", fmt="#,##0.00", border=False)
            sh.cell(r, 6, f"={sn}!S{pr}-{sn}!P{pr}*C{r}/{sn}!G{pr}", F_LINK, "#,##0.00", border=False)
            sh.cell(r, 7, f"={sn}!{static_of[sheet]}-E{r}", F_LINK, "#,##0.0", border=False)
            sh.cell(r, 8, f"=F{r}-E{r}", fmt="#,##0.0", border=False)
            sh.cell(r, 9, f"=MAX(H{r},G{r})", fmt="#,##0.0", border=False)
            sh.cell(r, 10, f'=IFERROR("PN"&SMALL(PN_list,COUNTIF(PN_list,"<"&I{r}*bar_per_m)+1),"> max PN")',
                    border=False)
            check = not ((i == 0 and frm_free) or (i == n_pts - 1 and to_free))
            sh.cell(r, 11, f'=IF(L{r}="no","end at tank",IF(H{r}<0,"NEGATIVE",IF(H{r}<p_min-0.005,"low","OK")))',
                    border=False)
            sh.cell(r, 12, "yes" if check else "no", border=False)
            sh.r += 1
    ws.freeze_panes = "C5"
    ws.auto_filter.ref = f"A4:L{sh.r - 1}"
    for i, w in enumerate([20, 18, 12, 11, 11, 11, 10, 11, 11, 11, 12, 8], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    for wsx in wb.worksheets:
        wsx.sheet_view.showGridLines = wsx.title in ("Profile",)
    wb.save(out_path)
    return out_path


if __name__ == "__main__":
    os.makedirs("results", exist_ok=True)
    print(build(os.path.join("results", "Tunduma_Zone_Calculator.xlsx")))
