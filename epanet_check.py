"""Run a corrected Tunduma .inp in EPANET (through WNTR) and compare with the design model.

Needs:  pip install wntr
"""
import os
import tempfile


def available():
    try:
        import wntr  # noqa: F401
        return True
    except ImportError:
        return False


def run(inp_path, system, cfg, routes):
    """Solve the .inp (steady state) and return (text summary, rows for Excel/CSV)."""
    import wntr

    wn = wntr.network.WaterNetworkModel(inp_path)
    here = os.getcwd()
    tmp = tempfile.mkdtemp()
    try:
        os.chdir(tmp)
        res = wntr.sim.EpanetSimulator(wn).run_sim()
    finally:
        os.chdir(here)
    head = res.node["head"].iloc[0]
    pres = res.node["pressure"].iloc[0]
    flow = res.link["flowrate"].iloc[0] * 1000          # l/s
    link_status = res.link["status"].iloc[0]

    out, rows = [], {"stations": [], "links": [], "nodes": []}
    out.append(f"EPANET steady-state check: {os.path.basename(inp_path)}")
    out.append("-" * 100)

    # ---- pump stations
    out.append("PUMP STATIONS  (EPANET operating point vs design)")
    hdr = f"{'Station':16s} {'pumps':>5s} {'Q/pump l/s':>10s} {'design':>7s} {'ER':>7s} {'Q tot m3/h':>10s} " \
          f"{'design':>7s} {'head m':>7s} {'design':>7s} {'ER':>6s}"
    out.append(hdr)
    for f in cfg["facilities"]:
        if not f.get("pumps"):
            continue
        fid = f["id"]
        st = system.nodes[fid].station
        duty = f["pumps"]["duty"]
        q = sum(flow[f"{fid}_P{i}"] for i in range(1, duty + 1))
        suction = fid if f["type"] == "intake" else (f"{fid}_CWT" if f["type"] == "wtp" else fid)
        h = head[f"{fid}_PS"] - head[suction]
        er = f["pumps"]["er_duty"]
        out.append(f"{fid:16s} {duty:5d} {q / duty:10.1f} {st['q_pump'] * 1000:7.1f} {er['q_m3h'] / 3.6:7.1f} "
                   f"{q * 3.6:10.0f} {st['q_total'] * 3600:7.0f} {h:7.1f} {st['tdh']:7.1f} {er['head_m']:6.0f}")
        rows["stations"].append({"Station": fid, "Duty pumps": duty,
                                 "EPANET Q/pump (l/s)": q / duty, "Design Q/pump (l/s)": st["q_pump"] * 1000,
                                 "ER Q/pump (l/s)": er["q_m3h"] / 3.6, "EPANET Q total (m3/h)": q * 3.6,
                                 "Design Q total (m3/h)": st["q_total"] * 3600,
                                 "EPANET pump head (m)": h, "Design TDH (m)": st["tdh"], "ER head (m)": er["head_m"],
                                 "Flow vs design (%)": 100 * (q / 1000 / st["q_total"] - 1)})
    out.append("")

    # ---- links: flow, and pressure range along each route
    out.append("PIPELINES  (flow and pressure along the route in EPANET)")
    out.append(f"{'Link':18s} {'Q l/s':>8s} {'design':>8s} {'diff %':>7s} {'Pmin m':>8s} {'Pmax m':>8s} "
               f"{'HGL end':>9s} {'design':>9s}  valve")
    for l in system.links:
        if l.id in routes:
            first = routes[l.id]["pipes"][0]
            node_ids = [n for n in routes[l.id]["nodes"][1:-1] if n in pres.index]
        else:
            first, node_ids = l.id, []
        q = flow[first] if first in flow.index else float("nan")
        pmin = min((pres[n] for n in node_ids), default=float("nan"))
        pmax = max((pres[n] for n in node_ids), default=float("nan"))
        valve = f"{l.id}_FCV"
        vtxt = ""
        end_node = routes[l.id]["pipes"][-1] if l.id in routes else l.id
        end_head = head[wn.get_link(end_node).end_node_name]
        if valve in flow.index:
            code = int(link_status[valve])
            vtxt = {0: "CLOSED", 1: "OPEN (cannot reach setting)", 2: "ACTIVE (controlling)"}.get(code, str(code))
        diff = 100 * (q / (l.q * 1000) - 1) if l.q else 0.0
        out.append(f"{l.id:18s} {q:8.1f} {l.q * 1000:8.1f} {diff:7.1f} {pmin:8.1f} {pmax:8.1f} "
                   f"{end_head:9.1f} {l.h_end:9.1f}  {vtxt}")
        rows["links"].append({"Link": l.id, "EPANET Q (l/s)": q, "Design Q (l/s)": l.q * 1000,
                              "Flow diff (%)": diff, "EPANET Pmin along route (m)": pmin,
                              "EPANET Pmax along route (m)": pmax, "EPANET HGL at end (m)": end_head,
                              "Design HGL at end (m)": l.h_end, "FCV status": vtxt})
    neg = pres[[n for n in pres.index if not n.endswith("_DIST")]]
    neg = neg[neg < 0]
    out.append("")
    out.append(f"Nodes with negative pressure: {len(neg)}"
               + (f"  (worst {neg.min():.1f} m at {neg.idxmin()})" if len(neg) else ""))
    for n in pres.index:
        rows["nodes"].append({"Node": n, "Head (m)": head[n], "Pressure (m)": pres[n]})
    return "\n".join(out), rows
