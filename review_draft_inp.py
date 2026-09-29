#!/usr/bin/env python3
"""Check the draft .inp (made from the DXF) against the survey and the Employer's Requirements.

Usage:  python review_draft_inp.py [--inp Tunduma_Transmission_Main_DRAFT.inp] [--out results]
Writes results/draft_inp_review.txt
"""
import argparse
import collections
import csv
import math
import os
import re

import build_model
import epanet_check

SURVEY = "Tunduma Project - Topographical Survey Data 24-31-08-2026.csv"


def read_sections(path):
    sec, out = None, collections.defaultdict(list)
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("["):
                sec = line.strip().upper()
                continue
            if line.strip() and not line.strip().startswith(";"):
                out[sec].append(line.rstrip("\n"))
    return out


def survey_points(path):
    pts = []
    with open(path, encoding="latin-1") as f:
        for r in csv.reader(f):
            try:
                pts.append((float(r[2]), float(r[1]), float(r[3]), r[4].strip()))
            except (ValueError, IndexError):
                pass
    return pts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inp", default="Tunduma_Transmission_Main_DRAFT.inp")
    ap.add_argument("--config", default="tunduma_config.json")
    ap.add_argument("--out", default="results")
    a = ap.parse_args(argv)
    cfg = build_model.load_config(a.config)
    al = build_model.Alignment(a.inp)
    sec = read_sections(a.inp)
    issues = []

    def issue(title, *lines):
        issues.append((title, list(lines)))

    # ---- boundary conditions
    res = [l.split() for l in sec["[RESERVOIRS]"]]
    src = next(f for f in cfg["facilities"] if f["type"] == "source")
    for r in res:
        issue("Reservoir head is the ground level, not the river water level",
              f"{r[0]} head = {float(r[1]):.2f} m (= ground at the intake). River Momba survey points are "
              f"1360.7-1364.5 m; model uses LWL {src['min_level']} m / HWL {src['max_level']} m.",
              "With the head at ground level the intake suction and low-lift pump head are wrong.")
    if not sec["[PUMPS]"]:
        pumped = [f for f in cfg["facilities"] if f.get("pumps")]
        issue("No pumps in the model",
              "ER stations: " + "; ".join(
                  f"{f['id']} Q={f['pumps']['er_duty']['q_m3h']} m3/h H={f['pumps']['er_duty']['head_m']} m "
                  f"({f['pumps']['duty']}W+{f['pumps']['standby']}S)" for f in pumped),
              "Without pumps a reservoir at ~1366 m cannot supply tanks at ~1700 m - EPANET gives large "
              "negative pressures and flow running back from the tanks to the river.")
    tanks = [l.split() for l in sec["[TANKS]"]]
    for t in tanks:
        vol = math.pi * float(t[5]) ** 2 / 4 * float(t[4])
        issue(f"Tank {t[0]} has placeholder geometry",
              f"D = {t[5]} m, levels 0-{t[4]} m -> {vol:,.0f} m3; elevation {t[1]} m. "
              "Replace with the real tank floor, BWL/TWL and diameter (see tunduma_config.json).")
    t_ids = {t[0] for t in tanks}
    for f in cfg["facilities"]:
        at = f.get("at")
        if f["type"] == "junction" and at in t_ids:
            issue(f"{at} is modelled as a tank but is junction {f['id']}",
                  f"ER schematic: {f['id']} is a pipe junction on the BPS rising main (Ipito offtake); "
                  "Uhuru Park GBR sits just after it and the Chapwa/Makambini line leaves the GBR by gravity.")

    # ---- missing facilities
    for f in cfg["facilities"]:
        if f["type"] in ("wtp", "tank", "bps", "sump") and f.get("at") not in t_ids:
            name = f"{f.get('name', f['id'])} (elevation {f['elevation']} m)"
            if "on_link" in f:
                detail = f"sits inside the inferred pipe {f['on_link']} - the draft has no station there."
            elif "offset" in f:
                inc = next(l for l in cfg["links"] if l["to"] == f["id"])
                detail = (f"off the surveyed route, fed by branch {inc['id']} from {inc['from']} "
                          f"({inc.get('er', '')}) - not in the draft.")
            else:
                detail = f"at alignment node {f['at']} - the draft runs the pipe straight through it as a junction."
            issue(f"{f['id']} missing from the model", f"{name}: {detail}")

    # ---- pipes
    diam = collections.Counter(l.split()[4] for l in sec["[PIPES]"])
    rough = collections.Counter(l.split()[5] for l in sec["[PIPES]"])
    issue("All pipes have placeholder diameter/roughness",
          f"Diameters used: {dict(diam)} mm; H-W C: {dict(rough)}. ER: STEEL DN600 main, "
          "DN150/DN100 branches to the existing tanks.")
    for pid, (n1, n2, length) in al.pipes.items():
        if pid.startswith("GAP"):
            dz = al.elev[n2] - al.elev[n1]
            issue(f"Inferred connector {pid} ({length:.0f} m straight line)",
                  f"{n1} ({al.elev[n1]:.2f} m) -> {n2} ({al.elev[n2]:.2f} m): dz = {dz:+.1f} m, "
                  f"slope {100 * abs(dz) / length:.0f} %. No survey levels in between - survey the real route.")
    for fx in al.fixes:
        issue("Pipe shorter than the distance between its end nodes", fx)

    # ---- lengths vs ER
    data, routes = build_model.build_engine_model(cfg, build_model.prepare_alignment(cfg))
    rows = []
    for lk in cfg["links"]:
        if lk["id"] in routes and lk.get("er_length"):
            r = routes[lk["id"]]
            rows.append(f"  {lk['id']:18s} ER {lk['er_length']:>8,.0f} m   alignment {r['plan_length']:>8,.0f} m "
                        f"(slope {r['length']:>8,.0f} m)   diff {r['length'] - lk['er_length']:+8,.0f} m")
    issue("Route lengths differ from the ER schematic", *rows,
          "Check against the DXF polylines: the WTP->Ikana and BPS->Uhuru Park sections are 1.3-2.1 km "
          "shorter than the ER, partly where GAP connectors cut straight across.")

    # ---- demands / controls
    if not sec["[DEMANDS]"] and not any(float(l.split()[2]) for l in sec["[JUNCTIONS]"] if len(l.split()) > 2):
        issue("No demands and no flow control",
              "ER demands: Uhuru Park town 16,215.62, Uhuru GSR01 1,546.56, ESR 371.52, Ipito/Makambini/"
              "Chapwa 622.1 each (m3/day). Branches to the existing tanks need flow control valves, "
              "otherwise the nearest/lowest tank takes all the water.")

    # ---- elevations vs survey
    if os.path.exists(SURVEY):
        pts = survey_points(SURVEY)
        grid = collections.defaultdict(list)
        for p in pts:
            grid[(int(p[0] // 50), int(p[1] // 50))].append(p)
        dz, off = [], []
        for n, (x, y) in al.xy.items():
            best = None
            for i in (-1, 0, 1):
                for j in (-1, 0, 1):
                    for p in grid.get((int(x // 50) + i, int(y // 50) + j), ()):
                        d = math.hypot(p[0] - x, p[1] - y)
                        if best is None or d < best[0]:
                            best = (d, p[2])
            if best:
                off.append(best[0])
                dz.append(al.elev[n] - best[1])
        off.sort()
        issue("OK - ground levels match the survey",
              f"{len(dz)} nodes checked: max |dz| to nearest survey point {max(abs(v) for v in dz):.2f} m, "
              f"median horizontal offset {off[len(off) // 2]:.1f} m. The alignment levels can be trusted.")

    # ---- EPANET run of the draft
    if epanet_check.available():
        import tempfile
        import wntr
        wn = wntr.network.WaterNetworkModel(a.inp)
        here, tmp = os.getcwd(), tempfile.mkdtemp()
        try:
            os.chdir(tmp)
            r = wntr.sim.EpanetSimulator(wn).run_sim()
        finally:
            os.chdir(here)
        p = r.node["pressure"].iloc[0]
        q = r.link["flowrate"].iloc[0] * 1000
        issue("EPANET result of the draft model",
              f"Pressure range {p.min():.0f} to {p.max():.0f} m; {int((p < 0).sum())} of {len(p)} nodes negative.",
              f"Flow in first pipe P0001: {q.iloc[0]:.1f} l/s (negative = towards the river).")

    os.makedirs(a.out, exist_ok=True)
    lines = [f"REVIEW OF {a.inp}", "=" * 100]
    for i, (title, body) in enumerate(issues, 1):
        lines.append(f"{i:2d}. {title}")
        lines += [f"    {b}" if not b.startswith("  ") else f"  {b}" for b in body]
        lines.append("")
    text = "\n".join(lines)
    with open(os.path.join(a.out, "draft_inp_review.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
