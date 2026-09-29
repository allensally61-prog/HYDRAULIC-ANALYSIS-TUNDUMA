#!/usr/bin/env python3
"""Tunduma Water Supply - hydraulic analysis, source to storage tanks.

    Momba River -> Intake (low lift) -> Grit tank (high lift) -> Momba WTP
    -> WTP pumps -> Ikana GBR -> gravity -> Nkangamo BPS -> BPS pumps
    -> J-001N/J-002N/J-003N -> Uhuru Park GBR + existing tanks

Steps:
  1. build the model from the survey alignment + tunduma_config.json
  2. design analysis with water_hydraulics.py (flows, head losses, HGL,
     pressures, pump heads/power, PN, surge, storage)
  3. compare with the Employer's Requirements (lengths, pump duties, velocities)
  4. write corrected EPANET .inp files and, if WNTR is installed, solve them in
     EPANET as an independent check

Usage:  python run_analysis.py [--config tunduma_config.json] [--out results]
"""
import argparse
import json
import os

import build_model
import epanet_check
import water_hydraulics as wh


def er_comparison(cfg, s, routes):
    rows_len, rows_pump = [], []
    for lk in cfg["links"]:
        l = next(x for x in s.links if x.id == lk["id"])
        er_len = lk.get("er_length")
        r = routes.get(lk["id"])
        rows_len.append({
            "Link": lk["id"], "ER description": lk.get("er", ""), "ER length (m)": er_len,
            "Alignment plan length (m)": r["plan_length"] if r else None,
            "Model length incl. slope (m)": l.length,
            "Difference vs ER (m)": (l.length - er_len) if er_len else None,
            "Design Q (m3/day)": l.daily, "Hours/day": l.hours, "V (m/s)": l.v,
        })
    for f in cfg["facilities"]:
        if not f.get("pumps"):
            continue
        st = s.nodes[f["id"]].station
        er = f["pumps"]["er_duty"]
        rows_pump.append({
            "Station": f["id"], "Pumps": f"{f['pumps']['duty']}W+{f['pumps']['standby']}S",
            "ER Q/pump (m3/h)": er["q_m3h"], "Model Q/pump (m3/h)": st["q_pump"] * 3600,
            "ER head (m)": er["head_m"], "Model TDH (m)": st["tdh"],
            "Head difference (m)": st["tdh"] - er["head_m"],
            "Model shaft kW/pump": st["shaft_kw"], "Model motor kW/pump": st["motor_kw"],
        })
    t = ["COMPARISON WITH THE EMPLOYER'S REQUIREMENTS (schematic Fig. 2)"]
    t.append(wh.table(["Link", "ER L (m)", "Plan L (m)", "Model L (m)", "Diff (m)", "Q (m3/d)", "h/d", "V (m/s)"],
                      [[r["Link"], wh.fmt(r["ER length (m)"], 0), wh.fmt(r["Alignment plan length (m)"], 0),
                        wh.fmt(r["Model length incl. slope (m)"], 0), wh.fmt(r["Difference vs ER (m)"], 0),
                        wh.fmt(r["Design Q (m3/day)"], 0), wh.fmt(r["Hours/day"], 0), wh.fmt(r["V (m/s)"], 2)]
                       for r in rows_len]))
    t.append("")
    t.append(wh.table(["Station", "Pumps", "ER Q m3/h", "Model Q m3/h", "ER H (m)", "Model TDH (m)", "Diff (m)",
                       "Shaft kW", "Motor kW"],
                      [[r["Station"], r["Pumps"], wh.fmt(r["ER Q/pump (m3/h)"], 0), wh.fmt(r["Model Q/pump (m3/h)"], 0),
                        wh.fmt(r["ER head (m)"], 0), wh.fmt(r["Model TDH (m)"]), wh.fmt(r["Head difference (m)"]),
                        wh.fmt(r["Model shaft kW/pump"], 0), wh.fmt(r["Model motor kW/pump"], 0)]
                       for r in rows_pump]))
    t.append("")
    t.append("PIPE PRESSURE CLASS - length (m) per PN: ER schedule vs model (working pressure / incl. unprotected surge)")
    classes = s.settings["pn_classes"]
    rows_pn = []
    for lk in cfg["links"]:
        if "er_pn" not in lk:
            continue
        l = next(x for x in s.links if x.id == lk["id"])
        for basis, segs in (("ER", None), ("model working", l.pn_segments_working),
                            ("model + surge", l.pn_segments_surge)):
            if segs is None:
                by = {int(k): v for k, v in lk["er_pn"].items()}
            else:
                by = {}
                for x0, x1, pn in segs:
                    by[pn] = by.get(pn, 0) + (x1 - x0)
            row = {"Link": lk["id"], "Basis": basis}
            row.update({f"PN{c}": by.get(c) for c in classes})
            row["> max"] = by.get(None)
            rows_pn.append(row)
    heads = ["Link", "Basis"] + [f"PN{c}" for c in classes] + ["> max"]
    t.append(wh.table(heads, [[r[h] if h in ("Link", "Basis") else wh.fmt(r[h], 0) for h in heads] for r in rows_pn]))
    t.append("  Note: the ER schedule for BPS_RM_1 covers the whole BPS -> Uhuru Park main (21,672 m).")
    return "\n".join(t), rows_len, rows_pump, rows_pn


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="tunduma_config.json")
    ap.add_argument("--out", default="results")
    ap.add_argument("--model-dir", default="model")
    a = ap.parse_args(argv)

    cfg = build_model.load_config(a.config)
    al = build_model.prepare_alignment(cfg)
    data, routes = build_model.build_engine_model(cfg, al)
    os.makedirs(a.model_dir, exist_ok=True)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.model_dir, "tunduma_system.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)

    s = wh.System(data).solve()
    report = wh.text_report(s)
    er_text, rows_len, rows_pump, rows_pn = er_comparison(cfg, s, routes)
    parts = [report, "", er_text]
    if al.fixes:
        parts += ["", "ALIGNMENT CORRECTIONS"] + [f"  {x}" for x in al.fixes]

    extra_sheets = [("ER comparison - links", rows_len), ("ER comparison - pumps", rows_pump),
                    ("ER comparison - PN", rows_pn)]
    for mode, label in (("er", "ER_pumps"), ("design", "design_pumps")):
        inp = os.path.join(a.model_dir, f"Tunduma_Transmission_Main_v1_{label}.inp")
        build_model.write_epanet(inp, cfg, al, routes, s, pump_mode=mode)
        if epanet_check.available():
            text, rows = epanet_check.run(inp, s, cfg, routes)
            parts += ["", "=" * 100, text]
            extra_sheets += [(f"EPANET {label} stations", rows["stations"]),
                             (f"EPANET {label} links", rows["links"])]
            wh.write_csv(os.path.join(a.out, f"epanet_{label}_nodes.csv"), rows["nodes"])
    if not epanet_check.available():
        parts += ["", "(EPANET check skipped - pip install wntr to solve the .inp files in EPANET)"]

    full = "\n".join(parts)
    with open(os.path.join(a.out, "report.txt"), "w", encoding="utf-8") as f:
        f.write(full + "\n")
    wh.write_csv(os.path.join(a.out, "pipes.csv"), wh.pipe_rows(s))
    wh.write_csv(os.path.join(a.out, "pump_stations.csv"), wh.station_rows(s))
    wh.write_csv(os.path.join(a.out, "tanks.csv"), wh.tank_rows(s))
    wh.write_csv(os.path.join(a.out, "profile_points.csv"), wh.profile_rows(s))
    for path in s.paths():
        wh.write_profile_svg(os.path.join(a.out, f"profile_{path[0].frm}_to_{path[-1].to}.svg"), s, path)
    if not wh.write_excel(os.path.join(a.out, "Tunduma_hydraulic_results.xlsx"), s, full, extra_sheets):
        print("(openpyxl not installed - Excel output skipped: pip install openpyxl)")
    print(full)
    print(f"\nModel files in {a.model_dir}/, results in {a.out}/")


if __name__ == "__main__":
    main()
