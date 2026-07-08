# CLDT Leadership Schedule Builder - Streamlit App

A web-based application for generating optimal leadership rotation schedules for Cadet Leader Development Training (CLDT) exercises.

**Live app:** [schedulecldt.streamlit.app](https://www.schedulecldt.streamlit.app) - no installation needed, use this unless you're developing or modifying the code.

## Features

- **Smart Optimization**: Uses mixed integer linear programming to minimize shift inequality across soldiers
- **Flexible Configuration**:
  - Variable squad sizes (6-13 soldiers per squad, 4 squads)
  - Adjustable lane and shift counts, or a built-in DMI CST 2026 default scheme
- **Fair Distribution**: Minimizes the gap between the most-worked and least-worked soldiers
- **Guaranteed Exposure**: Every soldier gets at least one PL/PSG shift and one graded SL shift
- **Professional Output**: On-screen leadership load summaries plus a CSV export
- **Usage Analytics**: Anonymous generation counter logged via a Google Apps Script endpoint

## Running Locally (optional)

Most users should just use the [live app](https://www.schedulecldt.streamlit.app). Run it locally only if you're developing or modifying the code.

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application:**
   ```bash
   streamlit run CLDT_schedule_app.py
   ```

3. **Access the app:**
   - This starts a local development server; it does not affect or connect to the hosted `schedulecldt.streamlit.app` instance.
   - It will automatically open in your browser.
   - If not, navigate to `http://localhost:8501`.

## Usage Guide

### Input Configuration

1. **Squad Composition** (Sidebar)
   - Set the size of each of the 4 squads (6-13 soldiers each)

2. **Exercise Design** (Sidebar)
   - **Use DMI CST 2026 default lane scheme** (checked by default): 8 lanes with shift counts `[2, 3, 3, 3, 3, 3, 3, 1]`, for 21 total shifts. Most users will want to leave this checked.
   - If unchecked: choose the number of lanes (6-12) and either a single shift count applied to all lanes, or a shift count (1-3) for each lane individually.

3. **Generate Schedule**
   - Click **Generate Schedule** in the sidebar.
   - The app runs pre-solve feasibility checks first; if the configuration is infeasible, it reports which condition(s) failed instead of running the solver.
   - If feasible, the solver runs (may take up to 60 seconds for complex configurations).

### In-App Guidance

The main page includes three expanders to help with configuration and troubleshooting:
- **What's a lane vs a shift?** - defines lanes (24-36 hour DMI-set blocks) and shifts/"looks" within them.
- **HELP!!!! My schedule is not building!** - walks through the mathematical feasibility conditions (platoon size, squad size, and shift count relationships) that must hold for a solution to exist, including worked examples for the default CST 2026 scheme.
- **Why do some soldiers get a second shift before others have had a first?** - explains why strict chronological fairness isn't enforced, in favor of guaranteed exposure plus overall workload balancing.

### Outputs

The app provides:

1. **On-screen summaries**:
   - Overall leadership load (SL + PL + PSG): max, min, and average shifts across the platoon, with who holds the max/min.
   - Per-soldier leadership summary: total SL/PL/PSG shifts, and a breakdown of PL, PSG, graded SL, and ungraded SL counts for each soldier.

2. **CSV Export** (`cldt_lane_shift_schedule.csv`):
   - Rows = soldiers.
   - First block of columns = each shift, labeled `L#-S#`, showing that soldier's role assignment (or blank if unassigned).
   - Followed by 5 blank spacer columns, then a summary block: Total Leadership Shifts, Total Graded Leadership Shifts, Total SL Shifts, Total PL+PSG Shifts, PL Shifts, PSG Shifts, Graded SL Shifts, Ungraded SL Shifts.

## Understanding the Output

### Role Abbreviations
- **PL**: Platoon Leader
- **PSG**: Platoon Sergeant
- **SL_1 / SL_2 / SL_3 / SL_4**: Squad Leader, locked to that squad
- **RTO**: Radio Transmission Operator
- **MED**: Medic
- **-G**: Graded (appended to an SL assignment, e.g. `SL_2-G`)

### Constraints Applied
- Every soldier gets at least one PL or PSG assignment.
- Every soldier gets at least one graded SL assignment.
- Exactly 2 squad leaders (out of the 4 on duty) are graded per shift.
- No back-to-back shifts for the same soldier, except that an RTO shift is always followed by a PL shift the next period, and a MED shift is always followed by a PSG shift the next period, for that same soldier.
- Squad Leaders are squad-locked: only a member of Squad *s* can serve as SL for Squad *s*.
- No more than 2 soldiers from the same squad may be pulled into PL, PSG, RTO, MED, or that squad's SL role in the same shift.
- Objective: minimize the difference between the most-worked and least-worked soldier's total shift count (not a per-role or per-squad balance guarantee).

## Feasibility at a Glance (Default CST 2026 Scheme)

With the default scheme (T = 21 total shifts), the practical binding condition is total platoon size: **P ≤ 42**. Squad size and manpower-vs-rest conditions are automatically satisfied across the entire allowed squad-size range (6-13). See the in-app **HELP!!!!** expander for the full derivation and all four conditions.

## Troubleshooting

### "Infeasible" Solution
If the solver reports an infeasible configuration:
- **Check total platoon size**: under the default CST 2026 scheme, total soldiers across all 4 squads must not exceed 42.
- **Increase shifts**: disable the default scheme and add more lanes/shifts for more flexibility.
- **Check squad sizes**: very small or very unbalanced squads may struggle to sustain SL coverage and sequencing.

### Slow Performance
- Complex configurations (many soldiers, many shifts) take longer.
- Allow up to 60 seconds for optimization.
- Consider simplifying the configuration for faster results.

### Installation Issues
If you encounter package installation errors:
```bash
pip install --upgrade pip
pip install -r requirements.txt --no-cache-dir
```

## Technical Details

- **Optimization Engine**: PuLP (Python Linear Programming)
- **Solver**: CBC (Coin-or Branch and Cut)
- **Objective**: Minimize the max-min difference in total (SL + PL + PSG) shifts across all soldiers
- **Framework**: Streamlit for the web interface
- **Analytics**: Anonymous generation-count logging via a Google Apps Script web endpoint (timestamp only; no roster or platoon data is transmitted)

## Credits

Built by K. Hamm with heavy assistance from ChatGPT 5.0 and 5.2.

Questions/Comments/Feedback: reach out to K. Hamm, use the in-app feedback form, or use the feedback tool.

## License

This project is licensed under the MIT License (see `LICENSE`). It is provided for military training purposes; use at your own discretion.
