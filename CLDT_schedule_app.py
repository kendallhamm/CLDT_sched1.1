import streamlit as st
import pulp
import pandas as pd
from typing import List, Dict
import io

st.set_page_config(page_title="CLDT Leadership Schedule Builder", layout="wide", page_icon="🎖️")

# Custom CSS
st.markdown("""
<style>
.stAlert {
    padding: 1rem;
}
.shift-box {
    background-color: #f0f2f6;
    padding: 1rem;
    border-radius: 0.5rem;
    margin: 0.5rem 0;
}
</style>
""", unsafe_allow_html=True)

# Header
st.title("🎖️ CLDT Leadership Schedule Builder")

st.info("""
**Purpose:** Intakes basic exercise information such as platoon composition and exercise design (lanes/shifts).

**User Guidance Options:**
- Whether or not to enforce RTO/MED pairings with the next shift's PL/PSG
- Whether or not soldiers volunteer for RTO/MED roles

**System Functions:**
- Assign PL or PSG role (at least 1 per soldier across exercise)
- Assign one SL per squad per shift
- Designate exactly 2 SLs as graded per shift (CLDT 2025 constraint)
- Enforce rest between shifts
- Balance total shifts as evenly as possible
- Export results to CSV

**Objective:** Minimize the difference in total shifts across soldiers.

*Built by K. Hamm with heavy assistance from ChatGPT 5.0*
""")

# Sidebar
st.sidebar.header("📋 Exercise Configuration")

# Squad sizes
st.sidebar.subheader("Squad Composition")
n1 = st.sidebar.number_input("Squad 1 size", min_value=6, max_value=9, value=8)
n2 = st.sidebar.number_input("Squad 2 size", min_value=6, max_value=9, value=8)
n3 = st.sidebar.number_input("Squad 3 size", min_value=6, max_value=9, value=8)
n4 = st.sidebar.number_input("Squad 4 size", min_value=6, max_value=9, value=8)

# Exercise design
st.sidebar.subheader("Exercise Design")
lanes = st.sidebar.number_input("Number of lanes", min_value=6, max_value=12, value=6)

same_shifts = st.sidebar.checkbox("All lanes have same number of shifts", value=True)
if same_shifts:
    SHIFTS_PER_LANE = st.sidebar.number_input("Shifts per lane", min_value=1, max_value=3, value=2)
    lane_shifts = [SHIFTS_PER_LANE] * lanes
else:
    lane_shifts = []
    for l in range(lanes):
        lane_shifts.append(
            st.sidebar.number_input(f"Lane {l+1} shifts", min_value=1, max_value=3, value=2)
        )

# Training options
st.sidebar.subheader("⚙️ Training Options")
train = st.sidebar.checkbox(
    "Enforce RTO→PL and MED→PSG pairing on next shift",
    value=False
)

volunteer_mode = False
if not train:
    volunteer_mode = st.sidebar.checkbox(
        "Volunteer mode for RTO/MED (unassigned)",
        value=False
    )

# Summary
col1, col2 = st.columns([2, 1])
with col2:
    SQUAD_SIZES = [n1, n2, n3, n4]
    P = sum(SQUAD_SIZES)
    T = sum(lane_shifts)
    st.metric("Total Soldiers", P)
    st.metric("Total Lanes", lanes)
    st.metric("Total Shifts", T)
    st.write("**Squad Sizes:**", SQUAD_SIZES)

with col1:
    if st.button("🚀 Generate Schedule", use_container_width=True):
        with st.spinner("Building optimal schedule..."):

            # Lane offsets
            offset = [0]
            for k in range(lanes):
                offset.append(offset[-1] + lane_shifts[k])

            def lane_of_shift(t):
                for l in range(lanes):
                    if offset[l] <= t < offset[l+1]:
                        return l
                raise RuntimeError

            # Build soldiers
            people = []
            person_squad = {}
            for s_idx, n in enumerate(SQUAD_SIZES):
                for i in range(1, n + 1):
                    pid = f"S{s_idx+1}-{i}"
                    people.append(pid)
                    person_squad[pid] = s_idx

            shifts = list(range(T))
            S = len(SQUAD_SIZES)

            # Roles
            role_PL = "PL"
            role_PSG = "PSG"
            role_RTO = "RTO"
            role_MED = "MED"
            role_SL = [f"SL_{s+1}" for s in range(S)]

            base_roles = [role_PL, role_PSG] + role_SL
            all_roles = base_roles if volunteer_mode else base_roles + [role_RTO, role_MED]

            def roles_for_shift(t):
                return all_roles

            # Model
            model = pulp.LpProblem("CLDT_Schedule", pulp.LpMinimize)

            x = {(p,t,r): pulp.LpVariable(f"x_{p}_{t}_{r}", 0, 1, cat="Binary")
                 for p in people for t in shifts for r in roles_for_shift(t)}

            y = {(p,t): pulp.LpVariable(f"y_{p}_{t}", 0, 1, cat="Binary")
                 for p in people for t in shifts}

            g = {(p,t): pulp.LpVariable(f"g_{p}_{t}", 0, 1, cat="Binary")
                 for p in people for t in shifts}

            zmax = pulp.LpVariable("zmax", lowBound=0, cat="Integer")
            zmin = pulp.LpVariable("zmin", lowBound=0, cat="Integer")

            zg_max = [pulp.LpVariable(f"zgmax_{s}", lowBound=0, cat="Integer") for s in range(S)]
            zg_min = [pulp.LpVariable(f"zgmin_{s}", lowBound=0, cat="Integer") for s in range(S)]

            zsl_max = [pulp.LpVariable(f"zslmax_{s}", lowBound=0, cat="Integer") for s in range(S)]
            zsl_min = [pulp.LpVariable(f"zslmin_{s}", lowBound=0, cat="Integer") for s in range(S)]

            # Coverage
            for t in shifts:
                model += pulp.lpSum(x[p,t,role_PL] for p in people) == 1
                model += pulp.lpSum(x[p,t,role_PSG] for p in people) == 1
                for s_idx in range(S):
                    model += pulp.lpSum(
                        x[p,t,role_SL[s_idx]] for p in people if person_squad[p] == s_idx
                    ) == 1
                if not volunteer_mode:
                    model += pulp.lpSum(x[p,t,role_RTO] for p in people) == 1
                    model += pulp.lpSum(x[p,t,role_MED] for p in people) == 1

            # One role per shift
            for p in people:
                for t in shifts:
                    model += pulp.lpSum(x[p,t,r] for r in roles_for_shift(t)) == y[p,t]
                    model += y[p,t] <= 1

            # Leadership exposure
            for p in people:
                model += pulp.lpSum(x[p,t,role_PL] + x[p,t,role_PSG] for t in shifts) >= 1

            # No consecutive shifts
            for p in people:
                for t in range(T-1):
                    if train and not volunteer_mode:
                        model += y[p,t] + y[p,t+1] <= 1 + x[p,t,role_RTO] + x[p,t,role_MED]
                    else:
                        model += y[p,t] + y[p,t+1] <= 1

            # Grading
            for t in shifts:
                model += pulp.lpSum(g[p,t] for p in people) == 2
                for p in people:
                    s_idx = person_squad[p]
                    model += g[p,t] <= x[p,t,role_SL[s_idx]]

            # Grading balance
            for s_idx in range(S):
                members = [p for p in people if person_squad[p] == s_idx]
                for p in members:
                    Gp = pulp.lpSum(g[p,t] for t in shifts)
                    model += Gp <= zg_max[s_idx]
                    model += Gp >= zg_min[s_idx]
                model += zg_max[s_idx] - zg_min[s_idx] <= 1

            # SL balance
            for s_idx in range(S):
                members = [p for p in people if person_squad[p] == s_idx]
                for p in members:
                    SLp = pulp.lpSum(x[p,t,role_SL[s_idx]] for t in shifts)
                    model += SLp <= zsl_max[s_idx]
                    model += SLp >= zsl_min[s_idx]
                model += zsl_max[s_idx] - zsl_min[s_idx] <= 1

            # Per-squad cap
            for s_idx in range(S):
                for t in shifts:
                    model += pulp.lpSum(
                        x[p,t,r]
                        for p in people if person_squad[p] == s_idx
                        for r in roles_for_shift(t)
                    ) <= 2

            # Fairness
            for p in people:
                Sp = pulp.lpSum(y[p,t] for t in shifts)
                model += Sp <= zmax
                model += Sp >= zmin

            model += zmax - zmin

            solver = pulp.PULP_CBC_CMD(msg=False)
            model.solve(solver)

            st.success("✅ Schedule generated")

            # Display
            st.header("📅 Leadership Rotation Schedule")
            for lane in range(lanes):
                with st.expander(f"Lane {lane+1}", expanded=True):
                    for sft in range(lane_shifts[lane]):
                        t = offset[lane] + sft
                        st.markdown(f"**Shift {sft+1}**")

                        cols = st.columns(4)
                        for s_idx in range(S):
                            with cols[s_idx]:
                                for p in people:
                                    if person_squad[p] == s_idx and pulp.value(x[p,t,role_SL[s_idx]]) > 0.5:
                                        st.write(f"Squad {s_idx+1} SL: {p}")

                        pls = [p for p in people if pulp.value(x[p,t,role_PL]) > 0.5]
                        psgs = [p for p in people if pulp.value(x[p,t,role_PSG]) > 0.5]
                        st.write("PL:", pls[0])
                        st.write("PSG:", psgs[0])

                        if not volunteer_mode:
                            rto = [p for p in people if pulp.value(x[p,t,role_RTO]) > 0.5][0]
                            med = [p for p in people if pulp.value(x[p,t,role_MED]) > 0.5][0]
                            st.write("RTO:", rto)
                            st.write("MED:", med)

            # Summary table
            summary = []
            for p in people:
                summary.append({
                    "Soldier": p,
                    "Squad": person_squad[p] + 1,
                    "Total Shifts": int(sum(pulp.value(y[p,t]) for t in shifts)),
                    "PL": int(sum(pulp.value(x[p,t,role_PL]) for t in shifts)),
                    "PSG": int(sum(pulp.value(x[p,t,role_PSG]) for t in shifts)),
                    "SL": int(sum(pulp.value(x[p,t,r]) for t in shifts for r in role_SL)),
                    "Graded": int(sum(pulp.value(g[p,t]) for t in shifts))
                })

            st.dataframe(pd.DataFrame(summary), use_container_width=True)

            # CSV export
            csv_buffer = io.StringIO()
            pd.DataFrame(summary).to_csv(csv_buffer, index=False)

            st.download_button(
                "📥 Download Summary CSV",
                csv_buffer.getvalue(),
                "cldt_schedule.csv",
                "text/csv"
            )

st.markdown("---")
st.caption("Built by K. Hamm with heavy assistance from ChatGPT 5.0")
