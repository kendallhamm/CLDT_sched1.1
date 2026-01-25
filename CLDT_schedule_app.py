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

# ----------------------------
# Header
# ----------------------------
st.title("🫡 CLDT Leadership Schedule Builder")

st.info("""
**Purpose**
Generate a CLDT leadership schedule while preserving squad integrity.

**Roles per Shift**
- PL, PSG
- RTO → PL (next shift)
- MED → PSG (next shift)
- One SL per squad (squad-locked)
- Exactly 2 SLs graded per shift

**Hard Rules**
- One role per soldier per shift
- No back-to-back shifts except sequencing
- Max **2 platoon-level roles per squad per shift**
- Everyone serves as PL or PSG at least once
- Everyone is graded at least once

**Objective**
Minimize the difference in total shifts worked.

*Built by K. Hamm with assistance from ChatGPT*
""")

# ----------------------------
# Sidebar Inputs
# ----------------------------
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

same_shifts = st.sidebar.checkbox("All lanes have the same number of shifts", True)

if same_shifts:
    SHIFTS_PER_LANE = st.sidebar.number_input(
        "Shifts per lane", min_value=1, max_value=3, value=2
    )
    lane_shifts = [SHIFTS_PER_LANE] * lanes
else:
    lane_shifts = []
    for l in range(lanes):
        lane_shifts.append(
            st.sidebar.number_input(
                f"Lane {l+1} shifts", min_value=1, max_value=3, value=2
            )
        )

# ----------------------------
# Derived values & summary
# ----------------------------
P = sum(SQUAD_SIZES)
T = sum(lane_shifts)
S = 4
R = 8  # PL, PSG, RTO, MED + 4 SLs
max_shifts_per_person = math.ceil(T / 2)

col1, col2 = st.columns([2, 1])
with col2:
    st.metric("Total Soldiers", P)
    st.metric("Total Shifts", T)
    st.write("Squad sizes:", SQUAD_SIZES)

# ----------------------------
# Pre-solve feasibility checks
# ----------------------------
errors = []

# Global manpower capacity
if P * max_shifts_per_person < R * T:
    errors.append(
        "Not enough total personnel to cover all required roles with rest constraints."
    )

# PL/PSG + grading coverage
if 2 * T < P:
    errors.append(
        "Too many soldiers for available PL/PSG and grading slots."
    )

# SL supply per squad
for i, n in enumerate(SQUAD_SIZES, start=1):
    if n * max_shifts_per_person < T:
        errors.append(
            f"Squad {i} is too small to provide an SL every shift."
        )

# Sequencing-saturated squad capacity (critical test)
for i, n in enumerate(SQUAD_SIZES, start=1):
    if n * math.ceil(T / 3) < T:
        errors.append(
            f"Squad {i} cannot sustain SL + platoon-role sequencing load."
        )

# ----------------------------
# Main button
# ----------------------------
with col1:
    if st.button("🚀 Generate Schedule", use_container_width=True):

        if errors:
            st.error("🚫 This configuration is mathematically infeasible:")
            for e in errors:
                st.write(f"- {e}")
            st.stop()

        with st.spinner("Solving optimization model..."):

            # ----------------------------
            # Lane offsets
            # ----------------------------
            offset = [0]
            for k in range(lanes):
                offset.append(offset[-1] + lane_shifts[k])

            # ----------------------------
            # Build soldiers
            # ----------------------------
            people = []
            person_squad = {}
            for s_idx, n in enumerate(SQUAD_SIZES):
                for i in range(1, n + 1):
                    pid = f"S{s_idx+1}-{i}"
                    people.append(pid)
                    person_squad[pid] = s_idx

            shifts = list(range(T))

            # ----------------------------
            # Roles
            # ----------------------------
            role_PL, role_PSG = "PL", "PSG"
            role_RTO, role_MED = "RTO", "MED"
            role_SL = [f"SL_{i+1}" for i in range(S)]

            platoon_roles = [role_PL, role_PSG, role_RTO, role_MED]
            all_roles = platoon_roles + role_SL

            # ----------------------------
            # Optimization model
            # ----------------------------
            model = pulp.LpProblem("CLDT_Schedule", pulp.LpMinimize)

            x = {(p, t, r): pulp.LpVariable(f"x_{p}_{t}_{r}", 0, 1, cat="Binary")
                 for p in people for t in shifts for r in all_roles}

            y = {(p, t): pulp.LpVariable(f"y_{p}_{t}", 0, 1, cat="Binary")
                 for p in people for t in shifts}

            g = {(p, t): pulp.LpVariable(f"g_{p}_{t}", 0, 1, cat="Binary")
                 for p in people for t in shifts}

            zmax = pulp.LpVariable("zmax", lowBound=0, cat="Integer")
            zmin = pulp.LpVariable("zmin", lowBound=0, cat="Integer")

            # ----------------------------
            # Coverage constraints
            # ----------------------------
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

            # ❗ Forbid cross-squad SL assignments
            for p in people:
                for t in shifts:
                    for s_idx in range(S):
                        if person_squad[p] != s_idx:
                            model += x[p, t, role_SL[s_idx]] == 0

            # ----------------------------
            # One role per soldier per shift
            # ----------------------------
            for p in people:
                for t in shifts:
                    model += pulp.lpSum(x[p, t, r] for r in all_roles) == y[p, t]

            # ----------------------------
            # Squad pull cap (platoon roles)
            # ----------------------------
            for t in shifts:
                for s_idx in range(S):
                    model += pulp.lpSum(
                        x[p, t, r]
                        for p in people if person_squad[p] == s_idx
                        for r in platoon_roles
                    ) <= 2

            # ----------------------------
            # Sequencing + rest
            # ----------------------------
            for p in people:
                for t in range(T - 1):
                    model += (
                        y[p, t] + y[p, t + 1]
                        <= 1 + x[p, t, role_RTO] + x[p, t, role_MED]
                    )
                    model += x[p, t, role_RTO] == x[p, t + 1, role_PL]
                    model += x[p, t, role_MED] == x[p, t + 1, role_PSG]

            # ----------------------------
            # Grading
            # ----------------------------
            for t in shifts:
                model += pulp.lpSum(g[p, t] for p in people) == 2
                for p in people:
                    model += g[p, t] <= x[p, t, role_SL[person_squad[p]]]

            # ----------------------------
            # Fairness objective
            # ----------------------------
            for p in people:
                Sp = pulp.lpSum(y[p, t] for t in shifts)
                model += Sp <= zmax
                model += Sp >= zmin

            model += zmax - zmin

            # ----------------------------
            # Solve
            # ----------------------------
            solver = pulp.PULP_CBC_CMD(msg=False)
            model.solve(solver)

            st.success("✅ Schedule generated")

            # ----------------------------
            # CSV export (lane × shift grid)
            # ----------------------------
            st.markdown("---")
            st.header("📥 Export Schedule (Lane / Shift Grid)")

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

st.markdown("---")
st.caption("Built by K. Hamm with assistance from ChatGPT")
