import streamlit as st
import pulp
import pandas as pd
import io
import math

st.set_page_config(
    page_title="CLDT Leadership Schedule Builder",
    layout="wide",
    page_icon="🎖️"
)

# ----------------------------
# Styling
# ----------------------------
st.markdown("""
<style>
.stAlert { padding: 1rem; }
</style>
""", unsafe_allow_html=True)

# ----------------------------
# Header
# ----------------------------
st.title("🎖️ CLDT Leadership Schedule Builder")

st.info("""
**Purpose:** Build a balanced CLDT leadership rotation by lane and shift.

**Roles Assigned Per Shift**
- PL, PSG
- 1 SL per squad
- RTO (precedes PL)
- MED (precedes PSG)
- Exactly 2 SLs graded

**Hard Rules**
- One role per soldier per shift
- No back-to-back shifts (except RTO→PL, MED→PSG)
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
n1 = st.sidebar.number_input("Squad 1 size", 6, 9, 8)
n2 = st.sidebar.number_input("Squad 2 size", 6, 9, 8)
n3 = st.sidebar.number_input("Squad 3 size", 6, 9, 8)
n4 = st.sidebar.number_input("Squad 4 size", 6, 9, 8)
SQUAD_SIZES = [n1, n2, n3, n4]

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

# ----------------------------
# Summary
# ----------------------------
P = sum(SQUAD_SIZES)
T = sum(lane_shifts)

col1, col2 = st.columns([2, 1])
with col2:
    st.metric("Total Soldiers", P)
    st.metric("Total Lanes", lanes)
    st.metric("Total Shifts", T)
    st.write("Squad sizes:", SQUAD_SIZES)

# ----------------------------
# Feasibility Checks
# ----------------------------
R = 8  # PL, PSG, 4x SL, RTO, MED
max_shifts_per_person = math.ceil(T / 2)

feasibility_errors = []

if P * max_shifts_per_person < R * T:
    feasibility_errors.append(
        "Not enough people to cover all required roles given rest constraints."
    )

if P < 2 * R:
    feasibility_errors.append(
        "Too few soldiers overall. Minimum required is 16."
    )

if 2 * T < P:
    feasibility_errors.append(
        "Too many soldiers for the number of shifts. Not enough PL/PSG and grading slots."
    )

for idx, n in enumerate(SQUAD_SIZES, start=1):
    if n * max_shifts_per_person < T:
        feasibility_errors.append(
            f"Squad {idx} is too small to provide one SL per shift."
        )

# ----------------------------
# Main Button
# ----------------------------
with col1:
    if st.button("🚀 Generate Schedule", use_container_width=True):

        if feasibility_errors:
            st.error("🚫 This configuration is infeasible:")
            for err in feasibility_errors:
                st.write(f"- {err}")
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
            S = len(SQUAD_SIZES)

            # ----------------------------
            # Roles
            # ----------------------------
            role_PL = "PL"
            role_PSG = "PSG"
            role_RTO = "RTO"
            role_MED = "MED"
            role_SL = [f"SL_{s+1}" for s in range(S)]

            all_roles = [role_PL, role_PSG, role_RTO, role_MED] + role_SL

            # ----------------------------
            # Model
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
            # Coverage
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

            # ----------------------------
            # One role per shift
            # ----------------------------
            for p in people:
                for t in shifts:
                    model += pulp.lpSum(x[p, t, r] for r in all_roles) == y[p, t]
                    model += y[p, t] <= 1

            # ----------------------------
            # Leadership exposure
            # ----------------------------
            for p in people:
                model += pulp.lpSum(
                    x[p, t, role_PL] + x[p, t, role_PSG]
                    for t in shifts
                ) >= 1

            # ----------------------------
            # RTO → PL, MED → PSG sequencing
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
                    s_idx = person_squad[p]
                    model += g[p, t] <= x[p, t, role_SL[s_idx]]

            # ----------------------------
            # Fairness
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
            # CSV EXPORT
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
            buffer = io.StringIO()
            df.to_csv(buffer, index=False)

            st.download_button(
                "📊 Download Full Schedule CSV",
                buffer.getvalue(),
                "cldt_lane_shift_schedule.csv",
                "text/csv",
                use_container_width=True
            )

# ----------------------------
# Footer
# ----------------------------
st.markdown("---")
st.caption("Built by K. Hamm with assistance from ChatGPT")
