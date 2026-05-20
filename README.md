# Reservoir Release Optimization Tool

Penalty-based constrained optimization for hydropower reservoir water release scheduling. This tool finds release schedules that maximize energy revenue while satisfying physical and operational constraints.

Developed by Edwin Trejo as part of an MS thesis at the University of Texas at El Paso, Department of Computer Science. Advised by Dr. Martine Ceberio.

## Overview

The tool consists of three components that can be used independently or together:

1. **Standalone Optimizer** (`reservoir_optimization_v4.py`): Runs the penalty-based optimizer directly on reservoir data. No external tools required.

2. **Meta-Loop with RealPaver** (`generate_realpaver.py` + `reservoir_metaloop_poc.py`): Combines the interval constraint solver RealPaver with the penalty optimizer. RealPaver analyzes constraints and finds guaranteed feasible solutions. The optimizer searches for higher-revenue schedules. A coordinator selects the best feasible result.

3. **LSTM Integration** (`lstm_penalty_integration.py`): Integrates penalty strategies into the DOF-LSTM neural network training loop for constraint-aware time series prediction.

## Requirements

- Python 3.8 or higher
- NumPy
- pandas (for LSTM integration only)
- scikit-learn (for LSTM integration only)
- matplotlib (for LSTM integration only)
- RealPaver (optional, only needed for the meta-loop; download from https://music.r3music.com/music-projects/realpaver/)

No GPU required. All scripts run on CPU. Tested on Google Colab.

## Data Files

The tool expects two CSV files:

**hydropower_hourly.csv** (required): Hourly reservoir operational records with columns:
- Start of Interval (UTC-06:00): timestamp
- End of Interval (UTC-06:00): timestamp
- Reservoir_water_level(m): float
- Discharge_Value (m^3/s): float
- Head(m): float
- Hydropower_Generation(MW): float or string

**hourly_evaporation_empirical_overwater_updated.csv** (optional): Hourly evaporation data with columns:
- Year: integer
- Month: integer
- Day: integer
- Hour: integer
- Evap_mm_hr: float

For the LSTM integration, a separate USIBWC discharge CSV is used (see LSTM section below).

## Quick Start: Standalone Optimizer

This is the simplest way to use the tool. No RealPaver needed.

### Step 1: Upload data to Google Colab

Upload `hydropower_hourly.csv` and `hourly_evaporation_empirical_overwater_updated.csv` to your Colab environment.

### Step 2: Update file paths

Open `reservoir_optimization_v4.py` and update the two file paths in the main section:

```python
data = load_data('/content/hydropower_hourly.csv')
evap_dict = load_evaporation('/content/hourly_evaporation_empirical_overwater_updated.csv')
```

### Step 3: Run

```
python reservoir_optimization_v4.py
```

### What it does

The script selects five 24-hour test windows from the data where the reservoir was actively generating power. For each window, it runs three penalty strategies (baseline, adaptive, learnable) with two penalty types (L1, L2) and compares the optimized schedule against the actual historical operations.

### Output

For each test window and configuration, the script prints:
- Revenue comparison (actual vs optimized)
- Whether the optimized schedule is feasible (satisfies all 75 constraints)
- Total constraint violation
- Number of constraints satisfied

For the best feasible result, it prints an hour-by-hour schedule showing discharge, power, revenue, reservoir level, evaporation, and ramp rate at each hour.

## Meta-Loop: Optimizer + RealPaver

This approach adds RealPaver as a constraint analysis layer. RealPaver finds guaranteed feasible solutions that serve as starting points and fallbacks for the optimizer.

### Step 1: Generate the RealPaver constraint file

Upload the data CSVs to Colab. Update the file paths at the top of `generate_realpaver.py`:

```python
HYDROPOWER_FILE = '/content/hydropower_hourly.csv'
EVAP_FILE = '/content/hourly_evaporation_empirical_overwater_updated.csv'
```

Run it with a window index (0 through 4):

```
python generate_realpaver.py 0
```

This produces a file called `reservoir_window_0.txt` containing the constraint problem in RealPaver format.

### Step 2: Run RealPaver

Download `reservoir_window_0.txt` from Colab to your local machine. Open it in RealPaver and run the solver. Save the output file (for example, as `reservoir_window_0_results.txt`).

### Step 3: Run the meta-loop optimizer

Upload the RealPaver output file to Colab. Open `reservoir_metaloop_poc.py` and update three file paths:

```python
data = load_data('/content/hydropower_hourly.csv')
evap_dict = load_evaporation('/content/hourly_evaporation_empirical_overwater_updated.csv')
REALPAVER_FILE = '/content/reservoir_window_0_results.txt'
```

Run it:

```
python reservoir_metaloop_poc.py
```

### What it does

The script automatically reads the RealPaver output file and extracts the feasible solution. It handles both UTF-16 and UTF-8 encoded files and parses outer boxes or inner boxes.

It then runs each penalty strategy twice: once starting from the actual historical discharge, and once starting from the RealPaver solution. A coordinator examines all candidate solutions and selects the one with the highest revenue among those that are feasible.

### Output

The script prints:
- RealPaver solution feasibility check
- Results for all strategies with both starting points
- Side-by-side comparison table
- Coordinator selections showing which starting point won for each strategy
- Hour-by-hour schedule for the best result

## Changing Constraints

All constraint values are defined in one place in each file. To change them, modify the values in the `ReservoirV4.__init__` method:

```python
self.Q_min = 2.0           # minimum discharge (m^3/s)
self.Q_max = 273.0         # maximum discharge (m^3/s)
level_band = 1.5           # reservoir level tolerance (meters)
self.ramp_max = 60.0       # max discharge change per hour (m^3/s)
self.S_end_tol = 5000.0    # end-of-day storage tolerance (TCM)
self.demand_tolerance = max(actual_total_tcm * 0.20, 500)  # demand tolerance
self.min_gen = sum(self.actual_P) * 0.5  # minimum generation (MWh)
```

If you are using the meta-loop, you must also update the same values in `generate_realpaver.py` so that RealPaver and the optimizer use identical constraints:

```python
Q_min_ms = 2.0        # must match self.Q_min
Q_max_ms = 273.0      # must match self.Q_max
ramp_max_ms = 60.0    # must match self.ramp_max
S_end_min = S0 - 5000.0  # must match self.S_end_tol
S_end_max = S0 + 5000.0  # must match self.S_end_tol
```

Both files must use the same constraint values. If they do not match, the RealPaver solution may not be feasible under the optimizer's constraints.

## LSTM Integration

This script integrates the penalty strategies into the DOF-LSTM neural network developed by Vega (2024).

### Data

The LSTM integration uses a different dataset than the reservoir optimizer. It requires the USIBWC discharge CSV file with columns for timestamp and discharge value in TCM.

### Setup

Upload the discharge CSV to Colab. Update the file path in `lstm_penalty_integration.py`:

```python
DATA_FILE = '/content/DataSetExport-Discharge_Total_Last-24-Hour-Change-in-Storage_08450800-Instantaneous-TCM-20240622194957.csv'
```

### Run

```
python lstm_penalty_integration.py
```

### What it does

The script trains the DOF-LSTM five times, each with a different penalty strategy:
- No penalty (baseline)
- Fixed lambda = 5
- Progressive (lambda multiplied by 10 every 10 epochs)
- Adaptive (lambda adjusted based on violation trend)
- Learnable (lambda computed by online controller)

All experiments use the same random seed for fair comparison.

### Output

The script prints a comparison table showing MSE, violation count, violation severity, and maximum lambda for each strategy. It also saves a four-panel plot (`lstm_penalty_comparison.png`) showing predictions, lambda evolution, violation counts, and training loss curves.

## Penalty Strategies

The tool implements four penalty update strategies. All share the same augmented objective:

```
F(x) = f(x) + lambda * P(x)
```

where f(x) is the original objective, P(x) is the penalty function (zero when feasible, positive when constraints are violated), and lambda controls the trade-off.

**Baseline Progressive**: Lambda starts at 1 and is multiplied by 10 at fixed intervals. Simple and predictable but does not adapt to the problem.

**Adaptive**: Lambda is adjusted based on how fast violations are decreasing. If violations drop fast, lambda increases gently (x2). If violations drop slowly, lambda increases moderately (x3). If violations are stuck, lambda increases aggressively (x10).

**Constraint-Aware Gradients**: Normalizes objective and penalty gradients to unit length and blends them with a feasibility-dependent weight. This strategy was found to be counterproductive and is not recommended. It is included for completeness and as a documented negative finding.

**Learnable**: An online controller computes lambda based on three signals: current violation severity, violation trend, and budget progress. The controller's weights are updated during optimization based on observed outcomes.

Two penalty formulations are supported:
- L1 (linear hinge): constant gradient at the constraint boundary. Recommended for inequality constraints.
- L2 (quadratic hinge): gradient proportional to violation magnitude. Smoother but loses enforcement power near the boundary.

## File Structure

```
reservoir-optimization/
    README.md
    reservoir_optimization_v4.py    # Standalone optimizer
    generate_realpaver.py           # RealPaver constraint file generator
    reservoir_metaloop_poc.py       # Meta-loop: optimizer + RealPaver + coordinator
    lstm_penalty_integration.py     # LSTM + penalty integration
    data/                           # Place your CSV files here
        hydropower_hourly.csv
        hourly_evaporation_empirical_overwater_updated.csv
```

## Constraints Reference

The optimizer enforces the following constraints (75 total per 24-hour window):

| ID | Constraint | Count | Description |
|----|-----------|-------|-------------|
| C1 | Release minimum | 24 | Discharge >= 2.0 m^3/s (environmental flow) |
| C2 | Release maximum | 24 | Discharge <= 273.0 m^3/s (turbine capacity) |
| C3 | Level bounds | 48 | Reservoir level within +/- 1.5 m of starting level |
| C4 | Demand | 2 | Total daily release within +/- 20% of historical |
| C5 | Min generation | 1 | Total power >= 50% of historical |
| C6 | Ramp rate | 23 | Consecutive hour discharge change <= 60 m^3/s |
| C7 | End storage | 1 | End-of-day storage within +/- 5,000 TCM of start |

Note: C1 and C2 are enforced via variable bounds (clipping after each gradient step), not via the penalty function. C3 through C7 are enforced via the penalty function.

## Citation

If you use this tool in your research, please cite:

```
Trejo, E. (2026). Penalty Approach to Constrained Optimization Problems 
in Water Reservoir and Energy Generation Management. Master's thesis, 
University of Texas at El Paso.
```

## Acknowledgments

This work builds on the DOF-LSTM architecture developed by Jose Vega (UTEP, 2024). Data provided by the UTEP water resources research team. RealPaver developed by the LINA laboratory.
