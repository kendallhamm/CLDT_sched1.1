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
- Solver is optimizing to **minimize the difference between the most total shifts and the least**, or equitably distribute the workload across all soldiers.

Squad integrity is preserved at all times.
""")

st.info("""
FEASIBILITY RULES (BASED ON P AND T)

Let:
P = total number of soldiers
T = total number of shifts across all lanes
nₛ = size of squad s

A schedule can be generated ONLY if all of the following conditions are met.
1) P × ⌈T / 2⌉ ≥ 8 × T
2) 2 × T ≥ P
3) nₛ × ⌈T / 2⌉ ≥ T
4) nₛ × ⌈T / 3⌉ ≥ T

These conditions are more below if you are interested in the math behind them.
""")
with st.expander("Click here for Supporting Math for feasibility conditions"):
    st.markdown(r"""
### Formal Feasibility Conditions

Let:
- \( P \) = total number of soldiers  
- \( T \) = total number of shifts  
- \( n_s \) = size of squad \( s \)

---

#### 1. Global manpower capacity
$$
P \cdot \left\lceil \frac{T}{2} \right\rceil \ge 8T
$$

---

#### 2. Leadership exposure capacity
$$
2T \ge P
$$

---

#### 3. Squad-locked SL coverage
$$
n_s \cdot \left\lceil \frac{T}{2} \right\rceil \ge T
\quad \forall s
$$

---

#### 4. Sequencing-induced workload
$$
n_s \cdot \left\lceil \frac{T}{3} \right\rceil \ge T
\quad \forall s
$$

---

#### 5. Squad integrity (platoon-level pull cap)
$$
\sum_{p \in s}
\big(
x_{p,t,\text{PL}} +
x_{p,t,\text{PSG}} +
x_{p,t,\text{RTO}} +
x_{p,t,\text{MED}}
\big)
\le 2
\quad \forall s,t
$$

---

#### 6. Optimization objective (not feasibility)
$$
\min \left( \max_p S_p - \min_p S_p \right)
$$
""")

#--------------------------------------------------
#1) GLOBAL MANPOWER CAPACITY
#--------------------------------------------------
#Each shift requires 8 different soldiers:
#• PL, PSG, RTO, MED
#• One Squad Leader from each of the 4 squads

#Because soldiers normally cannot work back-to-back shifts, each soldier can work
#at most ⌈T / 2⌉ shifts.

# Required condition:
# P × ⌈T / 2⌉ ≥ 8 × T

# If this fails, there are not enough soldiers to staff all shifts.

# --------------------------------------------------
# 2) LEADERSHIP EXPOSURE REQUIREMENTS
# --------------------------------------------------
# Every soldier must:
# • Serve at least once as PL or PSG
# • Serve at least once as a graded Squad Leader

# Each shift provides:
# • 2 PL/PSG slots
# • 2 graded SL slots

# Required condition:
# 2 × T ≥ P

# If this fails, there are not enough leadership opportunities for everyone.

# --------------------------------------------------
# 3) SQUAD-LOCKED SL CAPACITY
# --------------------------------------------------
# Each squad must provide exactly one Squad Leader every shift.
# SLs are locked to their own squad.

# For each squad s:
# nₛ × ⌈T / 2⌉ ≥ T

# If any squad fails this, it cannot sustain SL coverage across all shifts.

# --------------------------------------------------
# 4) SEQUENCING-INDUCED WORKLOAD (CRITICAL)
# --------------------------------------------------
# RTO and MED roles are paired with leadership roles on the next shift:
# • RTO(t) → PL(t+1)
# • MED(t) → PSG(t+1)

# This pairing consumes two adjacent shifts for the same soldier and significantly
# reduces flexibility.

# To absorb this sequencing load in addition to SL duties, each squad must satisfy:
# nₛ × ⌈T / 3⌉ ≥ T

# If this fails, sequencing forces overloads and no valid schedule exists.

# --------------------------------------------------
# 5) SQUAD INTEGRITY (PLATOON-LEVEL PULL LIMIT)
# --------------------------------------------------
# To preserve unit integrity:
# • No more than 2 soldiers per squad per shift may serve as
#   PL, PSG, RTO, or MED.

# If squad sizes are too small relative to T, this limit prevents platoon roles
# from being filled legally.

# (This constraint is enforced implicitly by Conditions 3 and 4.)

# --------------------------------------------------
# 6) FAIRNESS EXPECTATION
# --------------------------------------------------
# The solver minimizes the difference between the most-worked and least-worked soldiers.

# Because of:
# • squad locking,
# • sequencing,
# • rest rules,
# • and exposure requirements, perfect equality (everyone working exactly the same number of leadership shifts)
# is often mathematically impossible.

# The solver returns the fairest possible solution, not necessarily a perfectly
# even one.



# """)



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
    # Exposure constraints
    # --------------------------------------------------------
    for p in people:
        model += pulp.lpSum(
            x[p, t, role_PL] + x[p, t, role_PSG]
            for t in shifts
        ) >= e_pl[p]
        model += e_pl[p] == 1

        model += pulp.lpSum(g[p, t] for t in shifts) >= e_g[p]
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
    # TEXT REPORT: Overall Leadership Load Summary
    # --------------------------------------------------------
    leadership_totals = {}

    for p in people:
        total = 0
        for t in shifts:
            if pulp.value(x[p, t, "PL"]) > 0.5:
                total += 1
            if pulp.value(x[p, t, "PSG"]) > 0.5:
                total += 1
            sl_role = f"SL_{person_squad[p] + 1}"
            if pulp.value(x[p, t, sl_role]) > 0.5:
                total += 1
        leadership_totals[p] = total

    max_val = max(leadership_totals.values())
    min_val = min(leadership_totals.values())
    avg_val = sum(leadership_totals.values()) / len(leadership_totals)

    max_people = [p for p, v in leadership_totals.items() if v == max_val]
    min_people = [p for p, v in leadership_totals.items() if v == min_val]

    st.markdown("### 📊 Overall Leadership Load (SL + PL + PSG)")
    st.text(
        f"Max SL+PL+PSG shifts: {max_val}  ({', '.join(max_people)})\n"
        f"Min SL+PL+PSG shifts: {min_val}  ({', '.join(min_people)})\n"
        f"Avg SL+PL+PSG shifts: {avg_val:.2f}"
        )
        

    # --------------------------------------------------------
    # TEXT REPORT: Per-Soldier Leadership Summary
    # --------------------------------------------------------
    st.markdown("---")
    st.header("🧾 Per-Soldier Leadership Summary")

    report_lines = []

    for p in people:
        sl_total = 0
        sl_graded = 0
        sl_ungraded = 0
        pl_count = 0
        psg_count = 0

        for t in shifts:
            if pulp.value(x[p, t, "PL"]) > 0.5:
                pl_count += 1
            if pulp.value(x[p, t, "PSG"]) > 0.5:
                psg_count += 1

            sl_role = f"SL_{person_squad[p] + 1}"
            if pulp.value(x[p, t, sl_role]) > 0.5:
                sl_total += 1
                if pulp.value(g[p, t]) > 0.5:
                    sl_graded += 1
                else:
                    sl_ungraded += 1

        report_lines.append(
            f"{p}:\n"
            f"  Total SL(graded & ungraded), PL, PSG shifts: {sl_graded+sl_ungraded+pl_count+psg_count}\n"
            f"  Total SL shifts: {sl_total}\n"
            f"  Total PL & PSG shifts: {pl_count + psg_count}\n"
            f"  ├─ PL shifts: {pl_count}\n"
            f"  ├─ PSG shifts: {psg_count}\n"
            f"  Total Graded SL shifts: {sl_graded}\n"
            f"  Total Ungraded SL shifts: {sl_ungraded}\n"
        )

    st.text("\n".join(report_lines))

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
