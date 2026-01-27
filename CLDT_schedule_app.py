import streamlit as st
import pulp
import pandas as pd
import io
import math
import requests

# ============================================================
# CLDT Leadership Schedule Builder
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


GOOGLE_APP_URL = "https://script.google.com/macros/s/AKfycbzjUh59dgNZ4AfbyQGFIBOGVpOnrsW0XQ6TkxaSrcE50sHpE__YFUZVBbFtp26RzC4B9w/exec"

def log_schedule_generated():
    try:
        requests.post(GOOGLE_APP_URL, timeout=5)
    except Exception:
        # Fail silently: logging should never break scheduling
        pass

@st.cache_data(ttl=300)  # refresh every 5 minutes
def get_total_schedules_generated():
    try:
        r = requests.get(GOOGLE_APP_URL, timeout=5)
        return int(r.text)
    except Exception:
        return None



st.title("CLDT Leadership Schedule Builder")

st.info("""
This tool builds a **CLDT leadership schedule** for a single PLT.

This model assumes:
- Each shift (also known as a 'look') includes 1 graded PL, 1 graded PSG, 2 graded SLs, 2 ungraded SLs, 1 ungraded RTO, and 1 ungraded Medic.
- No back to back shifts, except RTO/MED-> PL/PSG
- Each soldier gets at least one graded SL shift
- Each soldier gets at least one PL or PSG shift

- Solver is optimizing to **minimize the difference between the most total shifts and the least**, or equitably distribute the workload across all soldiers.

Use the toggles on the left of the screen to build your custom schedule. Then click **Generate Schedule** and you will receive a report as well as an option to download a .csv file. 

Once complete you can paste your platoon roster (once sorted alphabetically by squad) into the most left column of that .csv file for a full look at your platoon's schedule.
""")

with st.expander("What's a lane vs a shift?"):
    st.markdown(r"""
**Definitions:**

**Lane:**

A lane is generally going to be a 24-36 hour period. These are set and distinguished by DMI. 

**Shift:**

Most lanes will have multiple shifts. Generally these break into a patrol base shift, a planning shift, and an actions on objective shift. This is commonly also called a "look."
""")


st.info("""
Having trouble?  

There are a few combinations that mathematically present unsolvable schedules. 
The key four are highlighted below. 

Let:
P = total number of soldiers (PLT size)
T = total number of shifts across all lanes
nₛ = size of squad s (if 1st SQD has 7 soldiers, n₁ = 7)

A schedule can be generated ONLY if all of the following conditions are met.
1) P × ⌈T / 2⌉ ≥ 8 × T
2) 2 × T ≥ P
3) nₛ × ⌈T / 2⌉ ≥ T
4) nₛ × ⌈T / 3⌉ ≥ T

These conditions are more detailed below if you have additional questions.
""")
with st.expander("Click here for Supporting Math for Feasibility Conditions"):
    st.markdown(r"""
### Feasibility Rules (Based on P and T)

Let:
- \( P \) = total number of soldiers  
- \( T \) = total number of shifts across all lanes  
- \( n_s \) = size of squad \( s \)

A schedule can be generated **only if all of the following conditions are met**.

---

#### 1️⃣ Capacity across the platoon

Each shift requires **8 different soldiers**:
- PL, PSG, RTO, MED  
- One Squad Leader from each of the 4 squads  

Because soldiers normally cannot work back-to-back shifts, each soldier can work
at most $ \lceil T / 2 \rceil $ shifts.


$$
P \cdot \left\lceil \frac{T}{2} \right\rceil \ge 8T
$$

If this condition fails, there are not enough soldiers to staff all shifts.

---

#### 2️⃣ Graded shift requirement

Every soldier must:
- Serve **at least once** as PL or PSG  
- Serve **at least once** as a graded Squad Leader  

Each shift provides:
- 2 PL/PSG slots  
- 2 graded SL slots  

$$
2T \ge P
$$

If this condition fails, there are not enough leadership opportunities for everyone.

---

#### 3️⃣ Squad integrity- SL leads his/her own squad, only

Each squad must provide **exactly one Squad Leader every shift**.
Squad Leaders are locked to their own squad.

For each squad \( s \):

$$
n_s \cdot \left\lceil \frac{T}{2} \right\rceil \ge T
\quad \forall s
$$

If any squad fails this condition, it cannot sustain SL coverage across all shifts.

---

#### 4️⃣ RTO/MED transitioning to PL/PSG (Critical)

RTO and MED roles are paired with leadership roles on the next shift:
- RTO\(t\) → PL\(t+1\)  
- MED\(t\) → PSG\(t+1\)  

This pairing consumes **two adjacent shifts** for the same soldier and significantly
reduces flexibility.

To absorb this sequencing load **in addition to SL duties**, each squad must satisfy:

$$
n_s \cdot \left\lceil \frac{T}{3} \right\rceil \ge T
\quad \forall s
$$

If this condition fails, sequencing forces overloads and no valid schedule exists.

---

#### 5️⃣ Squad min-force: pull no more than 2 soldiers per squad for platoon level taskings

To preserve unit integrity:
- **No more than 2 soldiers per squad per shift** may serve as  
  PL, PSG, RTO, or MED.

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

If squad sizes are too small relative to \( T \), this limit prevents platoon-level
roles from being filled legally.

(This constraint is enforced implicitly by Conditions 3 and 4.)

---

#### 6️⃣ Equitable total workload (Optimization Objective)

The solver minimizes the difference between the **most-worked** and **least-worked**
soldiers.

Because of:
- squad locking  
- sequencing  
- rest rules  
- exposure requirements  

perfect equality is often mathematically impossible.

$$
\min \left( \max_p S_p - \min_p S_p \right)
$$

The solver returns the **fairest possible solution**, not necessarily a perfectly
even one.
""")


# ------------------------------------------------------------
# Sidebar Inputs
# ------------------------------------------------------------
st.sidebar.header("Exercise Configuration")

st.sidebar.subheader("Squad Composition")
SQUAD_SIZES = [
    st.sidebar.number_input("Squad 1 size", 6, 9, 6),
    st.sidebar.number_input("Squad 2 size", 6, 9, 6),
    st.sidebar.number_input("Squad 3 size", 6, 9, 6),
    st.sidebar.number_input("Squad 4 size", 6, 9, 6),
]

st.sidebar.subheader("Exercise Design")
lanes = st.sidebar.number_input("Number of lanes", 6, 12, 8)

same_shifts = st.sidebar.checkbox("All lanes have same number of shifts", True)
if same_shifts:
    SHIFTS_PER_LANE = st.sidebar.number_input("Shifts per lane", 1, 3, 3)
    lane_shifts = [SHIFTS_PER_LANE] * lanes
else:
    lane_shifts = [
        st.sidebar.number_input(f"Lane {l+1} shifts", 1, 3, 3)
        for l in range(lanes)
    ]

#Usage Display
with st.sidebar:
    st.markdown("# App Usage")
    st.markdown("### Updates every ~5 minutes")

    total = get_total_schedules_generated()

    if total is not None:
        st.metric(
            label="Schedules generated",
            value=total
        )
    else:
        st.metric(
            label="Schedules generated",
            value="—"
        )

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
if st.button("Generate Schedule", use_container_width=True):

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
    # Log successful schedule generation
    log_schedule_generated()
    get_total_schedules_generated.clear()


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

    st.markdown("###Overall Leadership Load (SL + PL + PSG)")
    st.text(
        f"Max SL+PL+PSG shifts: {max_val}  ({', '.join(max_people)})\n"
        f"Min SL+PL+PSG shifts: {min_val}  ({', '.join(min_people)})\n"
        f"Avg SL+PL+PSG shifts: {avg_val:.2f}"
        )
        

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

    # --------------------------------------------------------
    # TEXT REPORT: Per-Soldier Leadership Summary
    # --------------------------------------------------------
    st.markdown("---")
    st.header("Leadership Summary by Soldier")

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

