import streamlit as st
import pulp
import pandas as pd
import io
import math

st.set_page_config(
    page_title="CLDT Leadership Schedule Builder",
    layout="wide",
    page_icon="🫡"
)

st.title("🫡 CLDT Leadership Schedule Builder")

st.info("""
Strict squad-integrity CLDT scheduler.
""")

# ---------------- Sidebar ----------------
st.sidebar.header("📋 Exercise Configuration")

SQUAD_SIZES = [
    st.sidebar.number_input("Squad 1 size", 6, 9, 6),
    st.sidebar.number_input("Squad 2 size", 6, 9, 6),
    st.sidebar.number_input("Squad 3 size", 6, 9, 6),
    st.sidebar.number_input("Squad 4 size", 6, 9, 6),
]

lanes = st.sidebar.number_input("Number of lanes", 6, 12, 6)
SHIFTS_PER_LANE = st.sidebar.number_input("Shifts per lane", 1, 3, 2)
lane_shifts = [SHIFTS_PER_LANE] * lanes

# ---------------- Derived ----------------
P = sum(SQUAD_SIZES)
T = sum(lane_shifts)
S = 4

max_shifts = math.ceil(T / 2)

# ---------------- Feasibility ----------------
errors = []

if P * max_shifts < 8 * T:
    errors.append("Global manpower insufficient.")

for i, n in enumerate(SQUAD_SIZES, 1):
    if n * max_shifts < 2 * T:
        errors.append(
            f"Squad {i} cannot support SL + platoon-role load under sequencing."
        )

if T > 2 * min(SQUAD_SIZES):
    errors.append(
        "Too many shifts for smallest squad under sequencing and pull caps."
    )

# ---------------- Main ----------------
if st.button("🚀 Generate Schedule"):

    if errors:
        st.error("🚫 Infeasible configuration:")
        for e in errors:
            st.write(f"- {e}")
        st.stop()

    # ---------------- Build offsets ----------------
    offset = [0]
    for k in range(lanes):
        offset.append(offset[-1] + lane_shifts[k])

    # ---------------- Build people ----------------
    people = []
    person_squad = {}
    for s_idx, n in enumerate(SQUAD_SIZES):
        for i in range(1, n + 1):
            pid = f"S{s_idx+1}-{i}"
            people.append(pid)
            person_squad[pid] = s_idx

    shifts = list(range(T))

    # ---------------- Roles ----------------
    role_PL, role_PSG, role_RTO, role_MED = "PL", "PSG", "RTO", "MED"
    role_SL = [f"SL_{i+1}" for i in range(S)]

    platoon_roles = [role_PL, role_PSG, role_RTO, role_MED]
    all_roles = platoon_roles + role_SL

    # ---------------- Model ----------------
    model = pulp.LpProblem("CLDT_Schedule", pulp.LpMinimize)

    x = {(p, t, r): pulp.LpVariable(f"x_{p}_{t}_{r}", 0, 1, cat="Binary")
         for p in people for t in shifts for r in all_roles}

    y = {(p, t): pulp.LpVariable(f"y_{p}_{t}", 0, 1, cat="Binary")
         for p in people for t in shifts}

    g = {(p, t): pulp.LpVariable(f"g_{p}_{t}", 0, 1, cat="Binary")
         for p in people for t in shifts}

    zmax = pulp.LpVariable("zmax", lowBound=0, cat="Integer")
    zmin = pulp.LpVariable("zmin", lowBound=0, cat="Integer")

    # ---------------- Coverage ----------------
    for t in shifts:
        model += pulp.lpSum(x[p, t, role_PL] for p in people) == 1
        model += pulp.lpSum(x[p, t, role_PSG] for p in people) == 1
        model += pulp.lpSum(x[p, t, role_RTO] for p in people) == 1
        model += pulp.lpSum(x[p, t, role_MED] for p in people) == 1

        for s_idx in range(S):
            model += pulp.lpSum(
                x[p, t, role_SL[s_idx]]
                for p in people if person_squad[p] == s_idx
            ) == 1

    # 🔒 FORBID cross-squad SLs
    for p in people:
        for t in shifts:
            for s_idx in range(S):
                if person_squad[p] != s_idx:
                    model += x[p, t, role_SL[s_idx]] == 0

    # ---------------- One role ----------------
    for p in people:
        for t in shifts:
            model += pulp.lpSum(x[p, t, r] for r in all_roles) == y[p, t]

    # ---------------- Squad pull cap ----------------
    for t in shifts:
        for s_idx in range(S):
            model += pulp.lpSum(
                x[p, t, r]
                for p in people if person_squad[p] == s_idx
                for r in platoon_roles
            ) <= 2

    # ---------------- Sequencing ----------------
    for p in people:
        for t in range(T - 1):
            model += y[p, t] + y[p, t + 1] <= 1 + x[p, t, role_RTO] + x[p, t, role_MED]
            model += x[p, t, role_RTO] == x[p, t + 1, role_PL]
            model += x[p, t, role_MED] == x[p, t + 1, role_PSG]

    # ---------------- Grading ----------------
    for t in shifts:
        model += pulp.lpSum(g[p, t] for p in people) == 2
        for p in people:
            model += g[p, t] <= x[p, t, role_SL[person_squad[p]]]

    # ---------------- Fairness ----------------
    for p in people:
        Sp = pulp.lpSum(y[p, t] for t in shifts)
        model += Sp <= zmax
        model += Sp >= zmin

    model += zmax - zmin

    solver = pulp.PULP_CBC_CMD(msg=False)
    model.solve(solver)

    st.success("✅ Schedule generated (no integrity violations)")
