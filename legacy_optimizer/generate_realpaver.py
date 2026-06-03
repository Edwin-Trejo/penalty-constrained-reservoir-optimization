"""
Generate RealPaver constraint files from hydropower + evaporation data.
Follows the exact format of Jose Vega's Expe3.txt.

Usage:
    python generate_realpaver.py [window_index]
    
    window_index: 0-4 (default 0, which is 9/14/12)
    
Produces: reservoir_window_N.txt ready to run in RealPaver.

Units in the RealPaver file: TCM (thousand cubic meters)
    - Release variables R1..R24 in TCM per hour
    - Storage in TCM
    - Inflows as net inflow (inflow - evaporation) in TCM per hour
"""
import csv
import numpy as np
import sys

# ============================================================
# CONFIGURATION (same as reservoir_optimization_v4.py)
# ============================================================
AREA_M2 = 50e6
L_REF = 330.0
S_REF = 690000.0
HYDROPOWER_FILE = 'hydropower_hourly.csv'       # change path as needed
EVAP_FILE = 'hourly_evaporation_empirical_overwater_updated.csv'  # change path as needed

def sf(s, default=0.0):
    try: return float(s.strip())
    except: return default

def l2s(level):
    return S_REF + AREA_M2 * (level - L_REF) / 1000.0

def parse_timestamp(ts):
    try:
        parts = ts.split(' ')
        date_parts = parts[0].split('/')
        hour = int(parts[1].split(':')[0])
        month = int(date_parts[0])
        day = int(date_parts[1])
        year = int(date_parts[2])
        if year < 100: year += 2000
        return (year, month, day, hour)
    except:
        return None

def load_data(filepath):
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f); next(reader)
        return [{'time':r[0],'level':sf(r[2]),'discharge':sf(r[3]),
                 'head':sf(r[4]),'power':sf(r[5])} for r in reader if len(r)>=6]

def load_evaporation(filepath):
    evap = {}
    with open(filepath, 'r') as f:
        reader = csv.reader(f); next(reader)
        for r in reader:
            if len(r) >= 5:
                key = (int(r[0]), int(r[1]), int(r[2]), int(r[3]))
                evap[key] = max(0, float(r[4])) * AREA_M2 / 1000.0 / 3600.0  # mm/hr -> m³/s
    return evap

def find_windows(data, n_windows=5):
    windows = []
    for s in range(6000, len(data)-24, 24*7):
        Qs = [data[s+t]['discharge'] for t in range(24)]
        gen = sum(data[s+t]['power'] for t in range(24))
        if gen > 200 and np.mean(Qs) > 20:
            windows.append(s)
            if len(windows) >= n_windows: break
    return windows

def generate_realpaver_file(data, evap_dict, start_idx, output_file):
    """Generate a RealPaver constraint file for a 24-hour window."""
    horizon = 24
    dt = 3600.0  # seconds per hour

    # Starting conditions
    L0 = data[start_idx]['level']
    S0 = l2s(L0)

    # Compute net inflows (inflow - evaporation) in TCM per hour
    net_inflows_tcm = []
    for t in range(horizon):
        idx = start_idx + t
        Q_actual = data[idx]['discharge']  # m³/s
        dL = (data[idx+1]['level'] - data[idx]['level']) if idx+1 < len(data) else 0

        # Estimate inflow (m³/s)
        ts = parse_timestamp(data[idx]['time'])
        evap_ms = evap_dict.get(ts, 0) if ts else 0
        inflow_ms = max(0, Q_actual + evap_ms + AREA_M2 * dL / dt)

        # Net inflow = inflow - evaporation, converted to TCM/hr
        net_inflow_ms = inflow_ms - evap_ms
        net_inflow_tcm = net_inflow_ms * dt / 1000.0  # m³/s * 3600s / 1000 = TCM/hr
        net_inflows_tcm.append(net_inflow_tcm)

    # Constraint parameters
    level_band = 1.5  # meters
    L_min = L0 - level_band
    L_max = L0 + level_band
    S_min = l2s(L_min)
    S_max = l2s(L_max)

    # Release bounds in TCM/hr
    Q_min_ms = 2.0    # m³/s
    Q_max_ms = 273.0   # m³/s
    R_min_tcm = Q_min_ms * dt / 1000.0   # 7.2 TCM/hr
    R_max_tcm = Q_max_ms * dt / 1000.0   # 982.8 TCM/hr

    # Demand target in TCM
    actual_Q = [data[start_idx+t]['discharge'] for t in range(horizon)]
    actual_total_tcm = sum(actual_Q) * dt / 1000.0
    demand_min = actual_total_tcm * 0.80
    demand_max = actual_total_tcm * 1.20

    # Ramp rate in TCM/hr (RELAXED from 40 to 60 m³/s)
    ramp_max_ms = 60.0  # m³/s
    ramp_max_tcm = ramp_max_ms * dt / 1000.0  # 216 TCM/hr

    # End storage tolerance (RELAXED from ±2000 to ±5000 TCM)
    S_end_min = S0 - 5000.0
    S_end_max = S0 + 5000.0

    # Build the file
    lines = []
    lines.append(f"/* Water Reservoir Optimization - RealPaver Constraint File")
    lines.append(f" * Window: {data[start_idx]['time']}")
    lines.append(f" * Generated from hydropower + evaporation data")
    lines.append(f" * Starting level: {L0:.3f} m, Starting storage: {S0:.0f} TCM")
    lines.append(f" * Units: releases and inflows in TCM per hour, storage in TCM")
    lines.append(f"*/")
    lines.append("")

    # Constants
    lines.append("Constants")
    lines.append(f"     w0 = {S0:.2f},")
    for t in range(horizon):
        comma = "," if t < horizon - 1 else ","
        lines.append(f"     c{t+1} = {net_inflows_tcm[t]:.2f}{comma}")
    lines.append(f"     reservoirMin = {S_min:.2f},")
    lines.append(f"     reservoirMax = {S_max:.2f},")
    lines.append(f"     demandMin = {demand_min:.2f},")
    lines.append(f"     demandMax = {demand_max:.2f},")
    lines.append(f"     rampMax = {ramp_max_tcm:.2f};")
    lines.append("")

    # Variables
    lines.append("Variables")
    for t in range(horizon):
        comma = "," if t < horizon - 1 else ";"
        lines.append(f"     R{t+1} in [{R_min_tcm:.1f}, {R_max_tcm:.1f}]{comma}")
    lines.append("")

    # Branch settings
    lines.append("Branch precision = 0.01,")
    lines.append("%mode = paving,")
    lines.append("parts = 4;")
    lines.append("")

    # Constraints
    lines.append("Constraints")

    # 1. Storage bounds at each time step (cumulative water balance)
    #    Storage(t) = w0 + sum(c_i - R_i for i=1..t)
    for t in range(1, horizon + 1):
        # Build cumulative expression
        expr = "w0"
        for i in range(1, t + 1):
            expr += f" + c{i} - R{i}"

        lines.append(f"     {expr} >= reservoirMin,")
        lines.append(f"     {expr} <= reservoirMax,")

    # 2. Demand constraint (total release)
    release_sum = " + ".join([f"R{t+1}" for t in range(horizon)])
    lines.append(f"     {release_sum} >= demandMin,")
    lines.append(f"     {release_sum} <= demandMax,")

    # 3. Ramp rate constraints: |R_{t+1} - R_t| <= rampMax
    #    Expressed as: R_{t+1} - R_t <= rampMax AND R_t - R_{t+1} <= rampMax
    for t in range(1, horizon):
        lines.append(f"     R{t+1} - R{t} <= rampMax,")
        lines.append(f"     R{t} - R{t+1} <= rampMax,")

    # 4. End storage constraint
    end_expr = "w0"
    for i in range(1, horizon + 1):
        end_expr += f" + c{i} - R{i}"
    lines.append(f"     {end_expr} >= {S_end_min:.2f},")
    lines.append(f"     {end_expr} <= {S_end_max:.2f};")

    # Write file
    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))

    # Print summary
    print(f"\nGenerated: {output_file}")
    print(f"  Window: {data[start_idx]['time']}")
    print(f"  Starting storage: {S0:.0f} TCM")
    print(f"  Storage bounds: {S_min:.0f} - {S_max:.0f} TCM")
    print(f"  Release bounds: {R_min_tcm:.1f} - {R_max_tcm:.1f} TCM/hr")
    print(f"  Demand: {demand_min:.0f} - {demand_max:.0f} TCM")
    print(f"  Ramp max: {ramp_max_tcm:.1f} TCM/hr")
    print(f"  End storage: {S_end_min:.0f} - {S_end_max:.0f} TCM")
    print(f"  Net inflows (TCM/hr): min={min(net_inflows_tcm):.1f}, max={max(net_inflows_tcm):.1f}")
    n_constraints = 2*horizon + 2 + 2*(horizon-1) + 2
    print(f"  Total constraints: {n_constraints}")


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    window_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    print("Loading data...")
    data = load_data(HYDROPOWER_FILE)
    evap_dict = load_evaporation(EVAP_FILE)
    print(f"  Hydropower: {len(data)} records")
    print(f"  Evaporation: {len(evap_dict)} records")

    windows = find_windows(data)
    print(f"  Found {len(windows)} test windows")

    if window_idx < len(windows):
        start = windows[window_idx]
        output = f"reservoir_window_{window_idx}.txt"
        generate_realpaver_file(data, evap_dict, start, output)
    else:
        print(f"Window index {window_idx} out of range (max {len(windows)-1})")
        print("Generating all windows...")
        for i, start in enumerate(windows):
            output = f"reservoir_window_{i}.txt"
            generate_realpaver_file(data, evap_dict, start, output)
