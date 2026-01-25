# CLDT Leadership Schedule Builder - Streamlit App

A web-based application for generating optimal leadership rotation schedules for Cadet Leader Development Training (CLDT) exercises.

## Features

- **Smart Optimization**: Uses mixed integer linear programming to minimize shift inequality across soldiers
- **Flexible Configuration**: 
  - Variable squad sizes (6-9 soldiers per squad)
  - Adjustable lane and shift counts
- **Fair Distribution**: Ensures balanced workload across all soldiers
- **Professional Output**: Clean schedule display and CSV export

## Installation

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
   streamlit run cldt_scheduler_app.py
   ```

3. **Access the app:**
   - The app will automatically open in your browser
   - If not, navigate to `http://localhost:8501`

## Usage Guide

### Input Configuration

1. **Squad Composition** (Sidebar)
   - Set the number of soldiers in each of the 4 squads (6-9 per squad)

2. **Exercise Design** (Sidebar)
   - Number of lanes (6-12)
   - Shifts per lane (1-3)
   - Option for variable shifts per lane

3. **Training Options** (Sidebar)
   - Maybe more features coming!

4. **Generate Schedule**
   - Click "Generate Schedule" button
   - Wait for solver (may take up to 60 seconds for complex configurations)

### Outputs

The app provides:

1. **CSV Export**:
   - Download button for full schedule
   - Rows = soldiers
   - Columns = shifts (formatted as L#-S#)
   - Includes all role assignments

## Understanding the Output

### Role Abbreviations
- **PL**: Platoon Leader
- **PSG**: Platoon Sergeant
- **SL**: Squad Leader
- **RTO**: Radio Transmission Operator
- **MED**: Medic
- **-G**: Graded (appended to SL roles)

### Constraints Applied
- Every soldier gets at least one PL or PSG assignment
- Every soldier gets at least one graded SL assignment
- Exactly 2 squad leaders are graded per shift
- No back-to-back shifts (except RTO->PL and MED->PSG)
- Fair distribution of all roles within squads
- Per-squad caps enforced for working positions

## Troubleshooting

### "Infeasible" Solution
If the solver returns an infeasible solution:
- **Reduce constraints**: Try disabling team leaders or RTO/MED pairings
- **Increase shifts**: More shifts provide more flexibility for assignments
- **Check squad sizes**: Very small squads may struggle with all constraints

### Slow Performance
- Complex configurations (many soldiers, many shifts, team leaders enabled) take longer
- Allow up to 60 seconds for optimization
- Consider simplifying configuration for faster results

### Installation Issues
If you encounter package installation errors:
```bash
pip install --upgrade pip
pip install -r requirements.txt --no-cache-dir
```

## Technical Details

- **Optimization Engine**: PuLP (Python Linear Programming)
- **Solver**: CBC (Coin-or Branch and Cut)
- **Objective**: Minimize max-min difference in total shifts across all soldiers
- **Framework**: Streamlit for web interface

## Credits

Built by K. Hamm with heavy assistance from ChatGPT 5.0 and 5.2

Questions/Comments/Feedback - reach out to K. Hamm

## License

This tool is provided for military training purposes. Use at your own discretion. 
