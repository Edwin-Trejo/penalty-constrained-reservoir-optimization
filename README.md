# Reservoir Release Optimizer

A web-based tool that finds optimal hourly water release schedules for hydropower reservoir operations. Given historical data for a 24-hour planning window, the optimizer determines how much water to release each hour to maximize revenue, maximize power generation, meet a target release volume, or minimize water use — while satisfying all physical and operational constraints.

Developed by Edwin Trejo as part of an MS thesis at the University of Texas at El Paso, Department of Computer Science. Advised by Dr. Martine Ceberio.

---

## Prerequisites

- **Python 3.8 or higher** — download from [python.org](https://www.python.org/downloads/).
  - **Windows:** During installation, check **"Add Python to PATH"**.
  - **Mac:** Python 3 is typically pre-installed. Run `python3 --version` in Terminal to confirm. If missing, install from [python.org](https://www.python.org/downloads/) or run `brew install python`.
- No GPU required. The optimizer runs entirely on CPU.

---

## Installation

### Step 1 — Place your data files

Put the two CSV files in the `data/` folder inside this project:

```
data/
    hydropower_hourly.csv
    hourly_evaporation_empirical_overwater_updated.csv
```

The app will load these automatically when it starts. See [Data Files](#data-files) below for the required format.

### Step 2 — Run the setup script

**Windows** — Double-click **`setup.bat`**.

**Mac / Linux** — Open Terminal, navigate to this folder, and run:

```bash
bash setup.sh
```

The setup script will:
1. Create a Python virtual environment called `myenv/`
2. Install all required packages from `requirements.txt`

This only needs to be done once.

You can also do this manually:

**Windows (Command Prompt):**
```bat
python -m venv myenv
myenv\Scripts\activate
pip install -r requirements.txt
```

**Mac / Linux (Terminal):**
```bash
python3 -m venv myenv
source myenv/bin/activate
pip install -r requirements.txt
```

### Step 3 — Launch the app

**Windows** — Double-click **`run.bat`**.

**Mac / Linux** — In Terminal:
```bash
bash run.sh
```

A browser window will open automatically at `http://localhost:8501`.

To launch manually:

**Windows:**
```bat
myenv\Scripts\activate
streamlit run app.py
```

**Mac / Linux:**
```bash
source myenv/bin/activate
streamlit run app.py
```

---

## Data Files

The app expects two CSV files in the `data/` folder.

### hydropower_hourly.csv (required)

Hourly reservoir operational records. Columns (in order):

| Column | Description |
|--------|-------------|
| Start of Interval (UTC-06:00) | Timestamp, e.g. `9/14/12 0:00` |
| End of Interval (UTC-06:00) | Timestamp (not used) |
| Reservoir_water_level(m) | Water surface elevation in meters |
| Discharge_Value (m³/s) | Actual release in cubic meters per second |
| Head(m) | Hydraulic head (not used directly) |
| Hydropower_Generation(MW) | Actual power output in megawatts |

### hourly_evaporation_empirical_overwater_updated.csv (required)

Hourly evaporation data. Columns (in order):

| Column | Description |
|--------|-------------|
| Year | Integer year |
| Month | Integer month (1–12) |
| Day | Integer day |
| Hour | Integer hour (0–23) |
| Evap_mm_hr | Evaporation rate in mm/hour |

If evaporation data is not available for a given hour, that hour is treated as zero evaporation.

---

## Using the App

When you launch the app, data loads automatically from the `data/` folder. The sidebar shows how many records were loaded. You then configure a run and click **Run Optimization**.

### Sidebar

**Data Files** — If you want to use different CSV files, type the new file paths here and click **Load Data**.

**RealPaver Warm Start** — Advanced option. If you have run the RealPaver interval constraint solver on a window and have its output file, upload it here. The optimizer will start from the RealPaver feasible point instead of historical data. This can improve feasibility when the optimizer has trouble satisfying all constraints on its own. See [Using RealPaver](#using-realpaver) below.

---

### Time Window

The optimizer works on one 24-hour period at a time. You choose which period to plan.

**Recommended windows** — A pre-filtered list of periods where the reservoir was actively generating power (>200 MWh) and had significant discharge (>20 m³/s). These are spaced roughly one week apart to give a representative spread across the dataset.

**Pick any date** — Use the calendar to select any date in the dataset. A warning appears if the selected period has low power generation, which may make the optimization results less meaningful.

---

### Optimization Objective

Choose what the optimizer should try to achieve:

| Objective | Description |
|-----------|-------------|
| **Maximize Revenue ($)** | Finds the release schedule that earns the most money given the hourly electricity prices. Higher releases during expensive hours (afternoon peak) earn more. |
| **Maximize Power Generation (MWh)** | Finds the schedule that produces the most total energy, ignoring electricity price signals. Useful when the goal is energy production rather than revenue. |
| **Meet a Target Water Release (TCM)** | You enter a total release volume (in thousand cubic meters) for the day, and the optimizer finds the hourly schedule that gets as close to that target as possible. The historical release for the selected window is shown as a reference. |
| **Minimize Water Release (Conservation)** | Finds the schedule that uses the least water while still satisfying all physical constraints. Useful for drought or conservation planning. |

---

### Electricity Prices ($/MWh)

Sets the hourly electricity price used when calculating revenue. This affects the **Maximize Revenue** objective and the revenue figures shown in results for all objectives.

| Option | Description |
|--------|-------------|
| **Default (ERCOT-style)** | A typical day-ahead price curve: low overnight (~$20–25/MWh), rising through the morning, peaking in late afternoon (~$85/MWh at 5pm). |
| **Flat rate** | A single price applied to all 24 hours. Enter the price in $/MWh. |
| **Custom (24-hour)** | Enter a different price for each hour individually. |
| **Upload CSV** | Upload a CSV file with 24 price values (one per row, or all in one row, no header). |

A bar chart preview shows the price curve for the current selection.

---

### Advanced Settings

#### Physical Constraints

| Setting | Default | Description |
|---------|---------|-------------|
| **Level band (±m)** | 1.5 m | The reservoir water level must stay within this range above or below the starting level for the window. Wider band = more flexibility for the optimizer. |
| **Max ramp rate (m³/s per hour)** | 40 m³/s | The maximum allowed change in discharge between consecutive hours. Prevents sudden surges that could damage turbine equipment. |
| **Demand tolerance (%)** | 20% | The optimizer's total daily release must be within this percentage of the historical release for the same period. |

#### Optimizer Settings

**Penalty update method** — Controls how the optimizer increases the penalty on constraint violations when a solution is infeasible.

| Method | Description | When to use |
|--------|-------------|-------------|
| **Adaptive** | Adjusts the penalty based on how fast violations are shrinking. If violations drop quickly, it increases the penalty gently; if they are stuck, it increases aggressively. | Good default for most cases. |
| **Learnable** | Tracks the rate of change of violations over time and adjusts both the penalty and its update weights dynamically. The most sophisticated method. | Use when Adaptive produces infeasible results. Slower (~5–10% more time). |
| **Baseline** | Multiplies the penalty by 10 at fixed intervals. Simple and predictable. | Use for comparison or when other methods behave unexpectedly. |

**Penalty type** — Controls the mathematical form of the penalty function.

| Type | Description | When to use |
|------|-------------|-------------|
| **L1** | Penalizes the sum of violations linearly. Produces a constant gradient near constraint boundaries, which can drive the solution feasible quickly. | Good default. Usually faster. |
| **L2** | Penalizes the sum of squared violations. Gradient is proportional to violation size, giving smoother convergence but losing enforcement strength near the boundary. | Try if L1 leaves small residual violations. |

---

### Run Optimization

Click **Run Optimization**. The optimizer runs for approximately 8,000 iterations, which typically takes 20–40 seconds depending on your computer. A spinner shows while it is running.

---

### Results

After the run completes, four summary metrics are shown:

| Metric | Description |
|--------|-------------|
| **Revenue** | Total electricity revenue for the optimized schedule. Delta shows the change vs. the actual historical operations. |
| **Total Release** | Total water released over the 24 hours in thousand cubic meters (TCM). A negative delta means less water released than historical. |
| **Power Generated** | Total power produced in megawatt-hours (MWh). |
| **Constraints** | How many of the 75 physical constraints are satisfied. "Feasible" means all constraints are met. |

A feasibility warning appears if the solution violates any constraints, along with a suggestion to try relaxing the Advanced Settings.

**Hourly Schedule table** — Shows every hour of the planned day:

| Column | Description |
|--------|-------------|
| Hour | Hour of day (0 = midnight, 12 = noon) |
| Price ($/MWh) | Electricity price for that hour |
| Actual Release (m³/s) | What actually happened historically |
| Optimal Release (m³/s) | The optimizer's recommended release |
| Actual Power (MW) | Historical power output |
| Optimal Power (MW) | Projected power output with the optimized release |
| Water Level (m) | Projected reservoir level at the start of each hour |
| Evaporation (m³/s) | Evaporative loss during that hour |
| Ramp (m³/s) | Change in release from the previous hour (positive = increase) |
| Hourly Revenue ($) | Revenue earned during that hour with the optimized release |

**Download Schedule as CSV** — Saves the hourly table to a CSV file named after the selected window.

**Constraint Details** — Expandable section showing the exact constraint values used for the run.

---

## Constraints Reference

The optimizer enforces 75 constraints per 24-hour window. Release bounds (minimum and maximum discharge) are enforced by clipping after each gradient step. All other constraints are enforced through the penalty function.

All values shown are defaults. Every constraint can be adjusted in the **Advanced Settings** section of the app.

| Constraint | Count | Default | Configurable | Description |
|------------|-------|---------|--------------|-------------|
| Release minimum | 24 | 2.0 m³/s | Yes | Environmental flow — minimum discharge required every hour |
| Release maximum | 24 | 273.0 m³/s | Yes | Turbine capacity — maximum discharge allowed per hour |
| Level bounds | 48 | ±1.5 m | Yes | Reservoir level must stay within the band around the starting level |
| Demand | 2 | ±20% | Yes | Total daily release must be within tolerance of the historical release |
| Ramp rate | 23 | 40 m³/s/hr | Yes | Maximum change in discharge between any two consecutive hours |
| End storage | 1 | ±2,000 TCM | Yes | End-of-day storage must be within this amount of the starting storage |
| Min generation | 1 | 50% of historical | Yes | Total power produced must meet this percentage of historical output |

---

## Using RealPaver

RealPaver is an interval constraint solver that guarantees a feasible solution by mathematically proving that a point satisfies all constraints. It is used as a warm start — giving the optimizer a good starting point — and as a fallback when the optimizer cannot find a feasible solution on its own.

### Step 1 — Generate the constraint file

Run the following command in a terminal (with the virtual environment active):

```bat
python generate_realpaver.py 0
```

Replace `0` with the window index (0–9) matching the window you want to optimize. This creates a file called `reservoir_window_0.txt` in the project folder.

### Step 2 — Run RealPaver

Run RealPaver on the constraint file:

```bat
Realpaver\realpaver.exe reservoir_window_0.txt > reservoir_window_0_results.txt
```

This produces a results file containing boxes of feasible solutions.

### Step 3 — Upload to the app

In the app sidebar, expand **RealPaver Warm Start** and upload `reservoir_window_0_results.txt`. The app will parse the file and activate the warm start for the next run.

> **Important:** A RealPaver results file is specific to the window it was generated for. Always match the uploaded file to the selected time window in the app.

---

## How the Optimizer Works

The optimizer uses **penalty-based constrained optimization** with Adam gradient descent.

The problem: find 24 release values Q₁…Q₂₄ that optimize an objective (revenue, power, etc.) while satisfying 75 constraints.

**Approach:**
1. Start from an initial guess (historical releases, with a small random perturbation).
2. Reformulate the constrained problem as an unconstrained one by adding a penalty term:  
   `F(Q) = objective(Q) + λ × penalty(Q)`  
   where `penalty(Q)` is zero when all constraints are satisfied and positive otherwise.
3. Run Adam gradient descent to minimize F(Q) iteratively.
4. Gradually increase λ (the penalty weight) when the solution remains infeasible, forcing the optimizer to prioritize constraint satisfaction.
5. Track the best feasible solution found throughout the process.

**Water balance model:**  
At each hour, the reservoir level changes according to:  
`Level(t+1) = Level(t) + (Inflow(t) − Release(t) − Evaporation(t)) × Δt / Area`

Inflows are estimated from historical data using the inverse water balance. Evaporation is loaded from the empirical evaporation dataset.

**Power generation model:**  
`Power(t) = η × ρ × g × Release(t) × Head(t) / 10⁶`  
where η = 0.976 (turbine efficiency), ρ = 1000 kg/m³, g = 9.81 m/s².

---

## File Structure

```
reservoir-optimizer/
├── app.py                          # Streamlit web app (main entry point)
├── reservoir_optimization_v4.py    # Core model, optimizer, and data loading
├── generate_realpaver.py           # Generates RealPaver constraint files
├── setup.bat                       # First-time setup script
├── run.bat                         # Launch script
├── requirements.txt                # Python package dependencies
├── data/
│   ├── hydropower_hourly.csv
│   └── hourly_evaporation_empirical_overwater_updated.csv
├── Realpaver/
│   ├── realpaver.exe               # RealPaver solver binary
│   ├── reservoir_window_0.txt      # Example constraint file (window 0)
│   └── reservoir_window_0_results.txt  # Example RealPaver output
└── legacy_optimizer/               # Original research scripts
    ├── README.md                   # Documentation for the legacy scripts
    ├── reservoir_metaloop_poc.py   # Meta-loop proof of concept
    └── lstm_penalty_integration.py # LSTM + penalty experiment
```

---

## Troubleshooting

**App does not open / "Module not found" error**  
Run `setup.bat` to install dependencies. Then use `run.bat` to launch — it activates the virtual environment automatically.

**"File not found" error on startup**  
Make sure `hydropower_hourly.csv` and `hourly_evaporation_empirical_overwater_updated.csv` are in the `data/` folder.

**Solution is infeasible**  
Try one or more of:
- Switch from **Baseline** to **Adaptive** or **Learnable** method
- Widen the **Level band** (e.g., 2.0 m instead of 1.5 m)
- Increase the **Demand tolerance** (e.g., 30%)
- Increase the **Max ramp rate** (e.g., 60 m³/s)
- Upload a RealPaver warm start file

**Optimization takes very long**  
The default 8,000 iterations takes 20–40 seconds. This is normal. **Learnable** is the slowest method; try **Adaptive** for faster results.

**RealPaver file upload fails**  
Make sure you are uploading the RealPaver *output* file (contains `OUTER BOX` sections), not the input constraint file. The output file is typically UTF-16 encoded.

---

## Citation

If you use this tool in your research, please cite:

```
Trejo, E. (2026). Penalty Approach to Constrained Optimization Problems
in Water Reservoir and Energy Generation Management. Master's thesis,
University of Texas at El Paso.
```

## Acknowledgments

This work builds on the DOF-LSTM architecture developed by Jose Vega (UTEP, 2024). Data provided by the UTEP water resources research team. RealPaver developed by the LINA laboratory.
