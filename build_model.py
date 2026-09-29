"""Build the Tunduma hydraulic model from the surveyed alignment and tunduma_config.json.

The draft .inp (made from the DXF) is used only as the surveyed ALIGNMENT: node
coordinates, ground levels and pipe lengths along the route. The facilities
(river, intake, grit tank, WTP, Ikana GBR, Nkangamo BPS, junctions, tanks) and the
pipe data come from tunduma_config.json, which follows the Employer's Requirements.

Two models are produced from the same data:
  * a model for water_hydraulics.py (design analysis: required pump heads, HGL,
    pressures, PN, surge, storage)
  * a corrected EPANET .inp (pumps, tanks, flow control valves) for checking in
    EPANET / WNTR
"""
import collections
import json
import math

G = 9.81


# ---------------------------------------------------------------- alignment
class Alignment:
    """Survey alignment read from an EPANET .inp: nodes, coordinates and pipes."""

    def __init__(self, path):
        self.elev, self.xy, self.pipes = {}, {}, {}
        sec = None
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("["):
                    sec = line.strip().upper()
                    continue
                s = line.split(";")[0].strip()
                if not s:
                    continue
                t = s.split()
                if sec in ("[JUNCTIONS]", "[TANKS]", "[RESERVOIRS]"):
                    self.elev[t[0]] = float(t[1])
                elif sec == "[PIPES]":
                    self.pipes[t[0]] = [t[1], t[2], float(t[3])]
                elif sec == "[COORDINATES]":
                    self.xy[t[0]] = (float(t[1]), float(t[2]))
        self.fixes = []
        for pid, (a, b, length) in self.pipes.items():
            chord = math.dist(self.xy[a], self.xy[b])
            if length < chord - 1.0:
                # a pipe cannot be shorter than the straight line between its ends
                self.fixes.append(f"{pid}: length {length:.2f} m < straight-line distance {chord:.2f} m "
                                  f"-> {chord:.2f} m used")
                self.pipes[pid][2] = chord
        self._build_adjacency()

    def _build_adjacency(self):
        self.adj = collections.defaultdict(list)
        for pid, (a, b, _) in self.pipes.items():
            self.adj[a].append((b, pid))
            self.adj[b].append((a, pid))

    def split_pipe(self, pid, fraction, new_node, elevation):
        """Insert a node part-way along a pipe (e.g. a pump station inside a gap)."""
        a, b, length = self.pipes.pop(pid)
        (xa, ya), (xb, yb) = self.xy[a], self.xy[b]
        self.xy[new_node] = (xa + (xb - xa) * fraction, ya + (yb - ya) * fraction)
        self.elev[new_node] = elevation
        self.pipes[f"{pid}_A"] = [a, new_node, length * fraction]
        self.pipes[f"{pid}_B"] = [new_node, b, length * (1 - fraction)]
        self._build_adjacency()

    def path(self, start, end):
        """Nodes and pipes along the (tree) alignment from start to end."""
        prev = {start: None}
        queue = collections.deque([start])
        while queue:
            n = queue.popleft()
            if n == end:
                break
            for m, pid in self.adj[n]:
                if m not in prev:
                    prev[m] = (n, pid)
                    queue.append(m)
        if end not in prev:
            raise ValueError(f"no alignment path from {start} to {end}")
        nodes, pipes, n = [end], [], end
        while prev[n] is not None:
            n, pid = prev[n]
            nodes.append(n)
            pipes.append(pid)
        return nodes[::-1], pipes[::-1]

    def length(self, pid, slope=True):
        a, b, length = self.pipes[pid]
        if not slope:
            return length
        return math.hypot(length, self.elev[a] - self.elev[b])


# ---------------------------------------------------------------- engine model
ENGINE_NODE_KEYS = ("id", "type", "name", "elevation", "min_level", "max_level", "inlet_level",
                    "residual_head", "demand_m3_day", "process_loss", "volume_m3", "safe_yield_m3_day",
                    "pumps")


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def prepare_alignment(cfg):
    al = Alignment(cfg["alignment_inp"])
    for fac in cfg["facilities"]:
        if "on_link" in fac:
            al.split_pipe(fac["on_link"], fac["fraction"], fac["id"], fac["elevation"])
    return al


def facility_xy(fac, al):
    if "xy" in fac:
        return tuple(fac["xy"])
    base = al.xy[fac["at"]] if "at" in fac else al.xy[fac["id"]]
    dx, dy = fac.get("offset", (0, 0))
    return base[0] + dx, base[1] + dy


def build_engine_model(cfg, al):
    """Return the water_hydraulics.py input dict and route details for each link."""
    slope = cfg.get("use_slope_length", True)
    nodes = []
    for fac in cfg["facilities"]:
        n = {k: v for k, v in fac.items() if k in ENGINE_NODE_KEYS and v is not None}
        if fac["type"] == "junction":
            n["elevation"] = al.elev[fac["at"]]
        nodes.append(n)
    defaults = cfg.get("pipe_defaults", {})
    links, routes = [], {}
    for lk in cfg["links"]:
        link = {"id": lk["id"], "from": lk["from"], "to": lk["to"], "dn": lk["dn"],
                "name": lk.get("er", lk["id"]), **defaults}
        for k in ("material", "hw_c", "wave_speed", "id_mm", "minor_k", "pn", "profile"):
            if k in lk:
                link[k] = lk[k]
        if "route" in lk:
            path_nodes, path_pipes = al.path(*lk["route"])
            x, prof = 0.0, [[0.0, al.elev[path_nodes[0]]]]
            plan = 0.0
            for pid, n in zip(path_pipes, path_nodes[1:]):
                x += al.length(pid, slope)
                plan += al.length(pid, False)
                prof.append([round(x, 2), al.elev[n]])
            link["length"] = round(x, 2)
            link["profile"] = prof
            routes[lk["id"]] = {"nodes": path_nodes, "pipes": path_pipes, "plan_length": plan,
                                "length": x}
        else:
            link["length"] = lk["length"]
        links.append(link)
    return {"project": cfg["project"], "settings": cfg.get("settings", {}),
            "nodes": nodes, "links": links}, routes


# ---------------------------------------------------------------- EPANET model
def write_epanet(path, cfg, al, routes, system, pump_mode="er"):
    """Write a corrected EPANET .inp.

    pump_mode "er"     - pump curves through the ER duty points (checks the ER pump selection)
    pump_mode "design" - pump curves through the duty points computed by water_hydraulics.py
    """
    st = system.settings
    fac = {f["id"]: f for f in cfg["facilities"]}
    lk_cfg = {l["id"]: l for l in cfg["links"]}
    c_factor = (1 + st["minor_loss_factor"]) ** (-1 / 1.852)   # minor losses folded into C
    junctions, reservoirs, tanks, pipes, pumps, valves, curves, coords, status = [], [], [], [], [], [], [], {}, []
    notes = []

    def add_j(nid, elev, xy, demand=0.0):
        junctions.append((nid, elev, demand))
        coords[nid] = xy

    # ---- facilities
    start_of, end_of = {}, {}      # facility id -> EPANET node where pipes leave / arrive
    for f in cfg["facilities"]:
        fid, ftype = f["id"], f["type"]
        xy = facility_xy(f, al)
        node = system.nodes[fid]
        if ftype == "source":
            reservoirs.append((fid, f["min_level"]))
            coords[fid] = xy
            start_of[fid] = end_of[fid] = fid
        elif ftype == "junction":
            add_j(fid, al.elev[f["at"]], xy)
            start_of[fid] = end_of[fid] = fid
        elif ftype == "intake":
            # sump as a junction: its water level is the HGL there, set by river level - abstraction loss
            add_j(fid, f["min_level"] - 1.0, xy)
            end_of[fid] = fid
        else:
            floor = f.get("floor", f["min_level"] - 0.5)
            if ftype == "wtp":
                inlet = f"{fid}_INLET"
                res = node.residual
                tanks.append((inlet, f["inlet_level"], res, 0.0, res + 0.5, 20.0))
                coords[inlet] = (xy[0] - 30, xy[1] + 20)
                end_of[fid] = inlet
                tid = f"{fid}_CWT"
            else:
                tid = fid
                end_of[fid] = fid
            vol = f.get("volume_m3") or 500.0
            depth = f["max_level"] - floor
            diam = math.sqrt(4 * vol / (math.pi * depth))
            lvl_mode = f.get("epanet_level", "min" if f.get("pumps") else "max")
            lvl = {"min": f["min_level"], "max": f["max_level"],
                   "mid": (f["min_level"] + f["max_level"]) / 2}[lvl_mode] - floor
            # EPANET treats a tank at exactly min (max) level as empty (full) and blocks flow
            lvl = min(max(lvl, f["min_level"] - floor + 0.05), f["max_level"] - floor - 0.05)
            tanks.append((tid, floor, lvl, f["min_level"] - floor, f["max_level"] - floor, diam))
            coords[tid] = xy
            start_of[fid] = tid
            if node.demand > 0:
                dist = f"{fid}_DIST"
                q = node.demand / 86.4
                d_out = max(100, min(600, round(math.sqrt(4 * q / 1000 / (math.pi * 1.0)) * 1000 / 50) * 50))
                add_j(dist, floor - 5.0, (xy[0] + 15, xy[1] - 15), q)
                pipes.append((f"{fid}_OUT", tid, dist, 10.0, d_out, 130, 0.0))
                notes.append(f"{dist}: distribution outflow {node.demand:,.2f} m3/day = {q:.2f} l/s")
        if f.get("pumps"):
            r = node.station
            ps, dis = f"{fid}_PS", f"{fid}_DIS"
            suction = fid if ftype == "intake" else start_of[fid]
            add_j(ps, f["elevation"], (xy[0] + 20, xy[1] + 10))
            add_j(dis, f["elevation"], (xy[0] + 40, xy[1] + 10))
            # station pipework losses as a minor loss on a short pipe
            d_st = 0.6 if r["q_total"] > 0.15 else 0.3
            v_st = r["q_total"] / (math.pi * d_st ** 2 / 4)
            k_st = st["station_losses"] * 2 * G / v_st ** 2
            pipes.append((f"{fid}_STATION", ps, dis, 5.0, d_st * 1000, 140, round(k_st, 2)))
            if pump_mode == "er":
                q_pump = f["pumps"]["er_duty"]["q_m3h"] / 3.6
                h_pump = f["pumps"]["er_duty"]["head_m"]
            else:
                q_pump = r["q_pump"] * 1000
                h_pump = r["tdh"]
            curves.append((f"{fid}_CURVE", q_pump, h_pump))
            n_all = f["pumps"]["duty"] + f["pumps"]["standby"]
            for i in range(1, n_all + 1):
                pid = f"{fid}_P{i}"
                pumps.append((pid, suction, ps, f"HEAD {fid}_CURVE"))
                if i > f["pumps"]["duty"]:
                    status.append((pid, "Closed"))
            start_of[fid] = dis
        elif ftype == "intake":
            start_of[fid] = fid

    # ---- links
    for l in system.links:
        lc = lk_cfg[l.id]
        c = lc.get("hw_c", cfg.get("pipe_defaults", {}).get("hw_c", 120)) * c_factor
        a = start_of[l.frm]
        b_final = end_of[l.to]
        if lc.get("fcv"):
            b = f"{l.to}_IN"
            to_fac = fac[l.to]
            txy = facility_xy(to_fac, al)
            z_in = to_fac.get("floor", to_fac.get("min_level", to_fac.get("elevation", 0)))
            vd = f"{l.to}_VD"
            add_j(b, z_in, (txy[0] - 15, txy[1] + 15))
            add_j(vd, z_in, (txy[0] - 8, txy[1] + 8))
            # EPANET does not allow a valve directly on a tank: FCV -> short pipe -> tank
            valves.append((f"{l.id}_FCV", b, vd, l.dn, "FCV", round(l.q * 1000, 3)))
            pipes.append((f"{l.id}_INLET", vd, b_final, 5.0, l.dn, round(c, 1), 0.0))
        else:
            b = b_final
        if l.id in routes:
            r = routes[l.id]
            inner = r["nodes"][1:-1]
            for n in inner:
                if n not in coords:
                    add_j(n, al.elev[n], al.xy[n])
            seq = [a] + inner + [b]
            for pid, n1, n2 in zip(r["pipes"], seq, seq[1:]):
                pipes.append((pid, n1, n2, round(al.length(pid, cfg.get("use_slope_length", True)), 2),
                              l.dn, round(c, 1), 0.0))
        else:
            pipes.append((l.id, a, b, l.length, l.dn, round(c, 1), 0.0))

    # ---- write
    L = ["[TITLE]",
         f"{cfg['project']}",
         f"Corrected model built by build_model.py - pump curves: {'ER duty points' if pump_mode == 'er' else 'design duty points from water_hydraulics.py'}",
         f"Minor losses folded into C (C x {c_factor:.3f}); station losses as K on *_STATION pipes; tanks at fixed levels (snapshot).",
         "", "[JUNCTIONS]", ";ID\tElev\tDemand"]
    L += [f"{i}\t{e:.2f}\t{d:.3f}" for i, e, d in junctions]
    L += ["", "[RESERVOIRS]", ";ID\tHead"] + [f"{i}\t{h:.2f}" for i, h in reservoirs]
    L += ["", "[TANKS]", ";ID\tElevation\tInitLevel\tMinLevel\tMaxLevel\tDiameter\tMinVol"]
    L += [f"{i}\t{e:.2f}\t{il:.2f}\t{mn:.2f}\t{mx:.2f}\t{d:.2f}\t0" for i, e, il, mn, mx, d in tanks]
    L += ["", "[PIPES]", ";ID\tNode1\tNode2\tLength\tDiameter\tRoughness\tMinorLoss\tStatus"]
    L += [f"{i}\t{a}\t{b}\t{ln:.2f}\t{d:.0f}\t{c}\t{k}\tOpen" for i, a, b, ln, d, c, k in pipes]
    L += ["", "[PUMPS]", ";ID\tNode1\tNode2\tParameters"] + [f"{i}\t{a}\t{b}\t{p}" for i, a, b, p in pumps]
    L += ["", "[VALVES]", ";ID\tNode1\tNode2\tDiameter\tType\tSetting\tMinorLoss"]
    L += [f"{i}\t{a}\t{b}\t{d:.0f}\t{t}\t{s}\t0" for i, a, b, d, t, s in valves]
    L += ["", "[STATUS]"] + [f"{i}\t{s}" for i, s in status]
    L += ["", "[CURVES]", ";ID\tFlow (l/s)\tHead (m)"] + [f"{i}\t{q:.2f}\t{h:.2f}" for i, q, h in curves]
    L += ["", "[ENERGY]", " Global Efficiency\t75", " Global Price\t0",
          "", "[OPTIONS]", " Units\tLPS", " Headloss\tH-W", " Specific Gravity\t1.0", " Viscosity\t1.0",
          " Trials\t200", " Accuracy\t0.001", " Unbalanced\tContinue 10", " Demand Multiplier\t1.0",
          " Quality\tNone",
          "", "[TIMES]", " Duration\t0:00", " Hydraulic Timestep\t1:00", " Report Timestep\t1:00",
          "", "[REPORT]", " Status\tYes", " Summary\tNo",
          "", "[COORDINATES]", ";Node\tX-Coord\tY-Coord"]
    L += [f"{i}\t{x:.3f}\t{y:.3f}" for i, (x, y) in coords.items()]
    L += ["", "[END]", ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return notes
