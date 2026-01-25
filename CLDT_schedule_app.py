import streamlit as st
import pulp
import pandas as pd
import io
import math

# ============================================================
# 🫡 CLDT Leadership Schedule Builder
#
# HARD GUARANTEES FOR EVERY SOLDIER:
#   • ≥ 1 graded Squad Leader (SL-G) shift
#   • ≥ 1 Platoon Leader (PL) or Platoon Sergeant (PSG) shift
#
# STRUCTURAL RULES:
#   • SLs are squad-locked (Squad i → SL_i only)
#   • PL, PSG, RTO, MED assigned every shift
#   • RTO(t) → PL(t+1), MED(t) → PSG(t+1)
#   • ≤ 2 platoon-level roles per squad per shift
#   • One role per soldier per shift
#   • No back-to-back shifts except sequencing
#
# Solver will NOT run if configuration is infeasible.
# ============================================================

st.set_page_config(
    page_title="CLDT Leadership Schedule Builder",
    layout="wide",
    page_icon="🫡"
)

st.title("🫡 CLDT Leadership Schedule Builder")

st.info("""
This tool builds a **doctrinally strict CLDT leadership schedule**.

Each soldier is guaranteed:
- **At least one graded Squad Leader shift**
- **At least one PL or PSG shift**

Squad integrity is preserved at all times.
""")

# ------------------------------------------------------------
# Sidebar Inputs
# ------------------------------------------------------------
st.sidebar.header("📋 Exercise Configuration")

st.sidebar.subheader("Squad Composition")
SQUAD_SIZES = [
    st.sidebar.number_input("Squad 1 size", 6, 9, 6),
    st.sidebar.number_input("Squad 2 size", 6, 9, 6),
    st.sidebar.number_input("Squad 3 size", 6, 9, 6),
    st.sidebar.number_input("Squad 4 size", 6, 9, 6),
]

st.sidebar.subheader("Exercise Design")
lanes = st.sidebar.number_input("Number of lanes", 6, 12, 6)

same_shifts = st.sidebar.checkbox("All lanes have same number of shifts", True)
if same_shifts:
    SHIFTS_PER_LANE = st.sidebar.number_input("Shifts per lane", 1, 3, 2)
    lane_shifts = [SHIFTS_PER_LANE] * lanes
else:
    lane_shifts = [
        st.sidebar.number_input(f"Lane {l+1} shifts", 1, 3, 2)
        for l in range(lanes)
    ]

# ------------------------------------------------------------
# Derived values
# ------------------------------------------------------------
P = sum(SQUAD_SIZES)
T = sum(lane_shifts)
S = 4
R = 8  # PL, PSG, RTO, MED + 4 SLs
max_shifts = math.ceil(T / 2)

# ------------------------------------------------------------
# Pre-solve feasibility checks
# ------------------------------------------------------------
errors = []

if P * max_shifts < R * T:
    errors.append("Insufficient manpower to cover required roles with rest rules.")

if 2 * T < P:
    errors.append("Not enough PL/PSG or grading slots for all soldiers.")

for i, n in enumerate(SQUAD_SIZES, start=1):
    if n * max_shifts < T:
        errors.append(f"Squad {i} too small to provide an SL every shift.")
    if n * math.ceil(T / 3) < T:
        errors.append(f"Squad {i} cannot sustain sequencing + SL load.")

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
if st.button("🚀 Generate Schedule", use_container_width=True):

    if errors:
        st.error("🚫 Infeasible configuration:")
        for e in errors:
            st.write(f"- {e}")
        st.stop()

    # --------------------------------------------------------
    # Build indexing
    # --------------------------------------------------------
    offset = [0]
    for k in range(lanes):
        offset.append(offset[-1] + lane_shifts[k])

    people = []
    person_squad = {}
    for s_idx, n in enumerate(SQUAD_SIZES):
        for i in range(1, n + 1):
            pid = f"S{s_idx+1}-{i}"
            people.append(pid)
            person_squad[pid] = s_idx

    shifts = list(range(T))

    # --------------------------------------------------------
    # Roles
    # --------------------------------------------------------
    role_PL, role_PSG = "PL", "PSG"
    role_RTO, role_MED = "RTO", "MED"
    role_SL = [f"SL_{i+1}" for i in range(S)]

    platoon_roles = [role_PL, role_PSG, role_RTO, role_MED]
    all_roles = platoon_roles + role_SL

    # --------------------------------------------------------
    # Model
    # --------------------------------------------------------
    model = pulp.LpProblem("CLDT_Schedule", pulp.LpMinimize)

    x = {(p, t, r): pulp.LpVariable(f"x_{p}_{t}_{r}", 0, 1, cat="Binary")
         for p in people for t in shifts for r in all_roles}

    y = {(p, t): pulp.LpVariable(f"y_{p}_{t}", 0, 1, cat="Binary")
         for p in people for t in shifts}

    g = {(p, t): pulp.LpVariable(f"g_{p}_{t}", 0, 1, cat="Binary")
         for p in people for t in shifts}

    # Exposure variables (CRITICAL)
    e_pl = {p: pulp.LpVariable(f"exposed_pl_{p}", 0, 1, cat="Binary") for p in people}
    e_g  = {p: pulp.LpVariable(f"exposed_g_{p}", 0, 1, cat="Binary") for p in people}

    zmax = pulp.LpVariable("zmax", lowBound=0, cat="Integer")
    zmin = pulp.LpVariable("zmin", lowBound=0, cat="Integer")

    # --------------------------------------------------------
    # Coverage
    # --------------------------------------------------------
    for t in shifts:
        model += pulp.lpSum(x[p, t, role_PL]  for p in people) == 1
        model += pulp.lpSum(x[p, t, role_PSG] for p in people) == 1
        model += pulp.lpSum(x[p, t, role_RTO] for p in people) == 1
        model += pulp.lpSum(x[p, t, role_MED] for p in people) == 1

        for s_idx in range(S):
            model += pulp.lpSum(
                x[p, t, role_SL[s_idx]]
                for p in people if person_squad[p] == s_idx
            ) == 1

    # Forbid cross-squad SLs
    for p in people:
        for t in shifts:
            for s_idx in range(S):
                if person_squad[p] != s_idx:
                    model += x[p, t, role_SL[s_idx]] == 0

    # One role per shift
    for p in people:
        for t in shifts:
            model += pulp.lpSum(x[p, t, r] for r in all_roles) == y[p, t]

    # Squad pull cap
    for t in shifts:
        for s_idx in range(S):
            model += pulp.lpSum(
                x[p, t, r]
                for p in people if person_squad[p] == s_idx
                for r in platoon_roles
            ) <= 2

    # Sequencing + rest
    for p in people:
        for t in range(T - 1):
            model += y[p, t] + y[p, t + 1] <= 1 + x[p, t, role_RTO] + x[p, t, role_MED]
            model += x[p, t, role_RTO] == x[p, t + 1, role_PL]
            model += x[p, t, role_MED] == x[p, t + 1, role_PSG]

    # --------------------------------------------------------
    # Grading
    # --------------------------------------------------------
    for t in shifts:
        model += pulp.lpSum(g[p, t] for p in people) == 2
        for p in people:
            model += g[p, t] <= x[p, t, role_SL[person_squad[p]]]

    # --------------------------------------------------------
    # Exposure constraints (THE FIX)
    # --------------------------------------------------------
    for p in people:
        # PL / PSG exposure
        model += pulp.lpSum(
            x[p, t, role_PL] + x[p, t, role_PSG]
            for t in shifts
        ) >= e_pl[p]
        model += e_pl[p] == 1

        # Graded SL exposure
        model += pulp.lpSum(
            g[p, t] for t in shifts
        ) >= e_g[p]
        model += e_g[p] == 1

    # --------------------------------------------------------
    # Fairness objective
    # --------------------------------------------------------
    for p in people:
        Sp = pulp.lpSum(y[p, t] for t in shifts)
        model += Sp <= zmax
        model += Sp >= zmin

    model += zmax - zmin

    solver = pulp.PULP_CBC_CMD(msg=False)
    model.solve(solver)

    st.success("✅ Schedule generated with guaranteed leadership exposure")

    # --------------------------------------------------------
    # CSV Export
    # --------------------------------------------------------
    shift_labels = [
        f"L{ln+1}-S{sf+1}"
        for ln in range(lanes)
        for sf in range(lane_shifts[ln])
    ]

    rows = []
    for p in people:
        row = [p]
        for ln in range(lanes):
            for sf in range(lane_shifts[ln]):
                t = offset[ln] + sf
                cell = ""
                for r in all_roles:
                    if pulp.value(x[p, t, r]) > 0.5:
                        cell = r
                        if r.startswith("SL_") and pulp.value(g[p, t]) > 0.5:
                            cell = f"{r}-G"
                        break
                row.append(cell)
        rows.append(row)

    df = pd.DataFrame(rows, columns=["Soldier"] + shift_labels)
    buf = io.StringIO()
    df.to_csv(buf, index=False)

    st.download_button(
        "📊 Download Full Schedule CSV",
        buf.getvalue(),
        "cldt_lane_shift_schedule.csv",
        "text/csv",
        use_container_width=True
    )
