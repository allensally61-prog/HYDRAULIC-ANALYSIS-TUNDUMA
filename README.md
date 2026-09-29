# Tunduma Water Supply – Hydraulic Analysis (Python)

Hydraulic model of the Tunduma bulk water system, from the source to the storage tanks:

```
Momba River ─► Intake (low-lift) ─► Grit tank (high-lift) ─► Momba WTP (20,000 m³/d)
   ─► WTP pumps ─► Ikana GBR 3,000 m³ ─► gravity ─► Nkangamo BPS ─► BPS pumps
   ─► J-001N (ESR) ─► J-002N (Uhuru GSR01) ─► J-003N (Ipito GSR02) ─► Uhuru Park GBR 5,000 m³
   ─► gravity ─► J-004N ─► Makambini GSR03 / Chapwa GSR04
```

The route and ground levels come from the surveyed alignment in the draft `.inp`, which was made from the DXF. The facilities, flows, pipe sizes and pump duties come from the Employer's Requirements (Figure 2 schematic, Tables 7 and 8). The survey CSV is used to check the levels.

## Run it

```bash
pip install openpyxl wntr      # optional: Excel output + EPANET check
python run_analysis.py         # build model, analyse, compare with ER, check in EPANET
python review_draft_inp.py     # list the problems in the draft .inp
python make_report_pdf.py      # academic black-and-white PDF report (needs reportlab)
```

`run_analysis.py` with no extra packages still does the full design analysis; `wntr` adds the independent EPANET solve.

## Files

| File | What it is |
|---|---|
| `tunduma_config.json` | **All project data**: facilities, levels, pumps, pipes, demands, design criteria. ER values are labelled; values marked `ASSUMED` must be confirmed. Edit this, then re-run. |
| `build_model.py` | Reads the survey alignment, splits it at the facilities, builds the Python model and writes corrected EPANET `.inp` files. |
| `water_hydraulics.py` | Analysis engine (standard library only): flows, Hazen-Williams/Darcy-Weisbach losses, HGL and pressures along the profile, pump TDH/power/energy, EN 805 PN check, Joukowsky surge, tank/sump storage. |
| `epanet_check.py` | Solves the corrected `.inp` in EPANET (via WNTR) and compares it with the Python results. |
| `run_analysis.py` | Runs everything and writes `results/` and `model/`. |
| `review_draft_inp.py` | Checks the draft `.inp` → `results/draft_inp_review.txt`. |
| `make_report_pdf.py` | Writes `results/Tunduma_Hydraulic_Analysis_Report.pdf`: an academic, black-and-white report of the whole process from intake to tanks, with every calculation worked step by step (numbers taken live from the model). |
| `model/Tunduma_Transmission_Main_v1_*.inp` | Corrected EPANET models (open in EPANET 2.2): `ER_pumps` uses the ER pump duty points, `design_pumps` uses the duties computed here. |
| `results/report.txt` | Full text report. `Tunduma_hydraulic_results.xlsx` has the same results in sheets. |
| `results/profile_*.svg` | Longitudinal sections (ground and HGL) from the river to each tank. |
| `results/profile_points.csv` | Ground, HGL, pressure and PN at every survey point, for plotting profiles. |

## How the analysis works

- **Flows:** demand at each tank → mass balance back to the river. WTP losses are 7 % (2 % intake-to-WTP + 5 % WTP), which gives the 21,506 m³/d raw water flow. Pumped mains run 22 h/d; gravity mains run 24 h/d.
- **Zones:** the system is split at every free water surface (river, sumps, WTP, tanks). For each zone the program works backwards from the far end to find the head needed at its start. That head must reach each inlet level plus 1 m, and keep at least 2 m pressure at the pipe crown at every survey point (5 m at junctions, ER Table 7).
  - **Pumped zones:** the pump TDH is that required head, minus the sump low water level (LWL), plus 3 m station losses.
  - **Gravity zones:** the required head is compared with the tank's bottom water level (BWL). Any surplus has to be burnt off by a flow-control valve (FCV) or PRV.
- **Pipe pressure class (PN):** at every survey point, the working pressure is the higher of the steady and static pressures. This gives the PN class by chainage, reported twice: for working pressure only, and with unprotected Joukowsky surge added (EN 805: PMA = 1.2 × PFA). Both are compared with the ER PN schedule.
- **EPANET check:** the same network is written as an EPANET `.inp`, with pumps and tank levels set for the worst case, and FCVs at the tank inlets. With the `design_pumps` curves, EPANET reproduces the Python HGL within about 0.1 m at the junctions, which confirms the two models agree. The `ER_pumps` run shows how the pumps specified in the ER would actually operate.

## Key results (current config)

| Station | ER duty | Model TDH | EPANET with ER pumps | Head set by |
|---|---|---|---|---|
| Intake low-lift | 978 m³/h @ 10 m | 12.1 m | 1,065 m³/h | Grit tank inlet (levels ASSUMED) |
| Grit tank high-lift | 978 m³/h @ 25 m | 17.4 m | 1,230 m³/h (+26 %) | WTP inlet level (ASSUMED 1378 m) |
| WTP pumps 3W+1S | 304 m³/h @ 330 m | 334.1 m | 902 m³/h (−0.8 %) | Ikana GBR inlet – **ER selection confirmed** |
| Nkangamo BPS 2W+1S | 455 m³/h @ 221 m | 188.2 m | ER head is 33 m more than needed | Existing ESR inlet (ESR levels ASSUMED) |

- **Ikana → Nkangamo gravity main:** 53 m surplus head. An FCV (or PRV plus FCV) is needed at the BPS sump inlet.
- **High point at ch. ~74.1 km (ground 1,710 m):** this is higher than the Uhuru Park GBR top water level (TWL). The BPS main needs air valves there, and the HGL must stay above it.
- **Uhuru Park GBR → J-004N:** 3.9 m short of head in the first ~200 m. The ground there (1,698–1,699 m) is higher than the GBR BWL (1,697.6 m, from the ER elevation). Lay that pipe deeper or confirm the GBR levels.
- **Chapwa GSR04:** arrives with 125 m excess head. It needs a PRV/FCV and PN25 on the lower section (the ER shows PN25).
- **Pipe pressure class on the WTP → Ikana main:** PN30 length is 10,776 m in the model vs 10,798 m in the ER. The ER's PN40 length (5,067 m) matches the model *including surge* (5,926 m).
- **Surge:** every long main needs surge protection (unprotected pump-trip transients drop to −80 to −90 m). This agrees with the ER's requirement for surge vessels.

## Assumptions to confirm (`ASSUMED` in the config)

- River LWL/HWL (1,361.0 / 1,364.5 m, taken from the survey points), and the intake sump and grit tank levels.
- WTP inlet (aerator) level 1,378 m, and clear-water tank LWL/TWL 1,368.5 / 1,373.0 m.
- Tank floor = ER elevation, with a water depth of 5 m (new GBRs) or 3 m (existing tanks). The ESR is taken as elevated, with floor 1,703.5 m; **this sets the BPS head**.
- Ipito GSR02 capacity: the ER says 200 m³, but the survey labels it "2000 m³ tank".
- Site locations:
  - BPS site placed where the inferred gap reaches 1,555.5 m;
  - J-001N and J-002N placed at the survey chambers;
  - J-004N placed 1,561 m along the Chapwa branch;
  - Makambini branch drawn as a straight 494 m line.
- H-W C = 120 (aged cement-lined steel), minor losses +10 %, station losses 3 m, pipe cover 1.2 m.

## Problems found in the draft `.inp`

See `results/draft_inp_review.txt`. In short:

- **Ground levels are correct:** within 0.01 m of the survey at all 2,335 nodes.
- **Hydraulic set-up:**
  - the reservoir head is the ground level instead of the river level;
  - there are **no pumps**;
  - the WTP, Ikana GBR, Nkangamo BPS and three existing tanks are missing;
  - N2163 is modelled as a tank but is junction J-003N;
  - all pipes are DN300 C120 placeholders;
  - tanks have placeholder geometry;
  - there are no demands or flow-control valves.
- **Geometry:**
  - the two GAP connectors are straight-line guesses (GAP-Waypoint1 climbs 123 m at 34 %);
  - two pipes are shorter than the distance between their end nodes;
  - the WTP→Ikana and BPS→Uhuru Park routes are 1.3–2.1 km shorter than the ER lengths.
- **EPANET result:** the draft gives pressures down to −209 m, with 1,098 negative nodes, and flow running back to the river.

## Next steps

- Replace the `ASSUMED` values with the actual designs.
- Add an extended-period (24–72 h) run with pump on/off controls based on tank levels.
- Run a transient analysis to size the surge vessels.
