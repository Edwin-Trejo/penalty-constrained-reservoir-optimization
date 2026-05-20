"""
=============================================================================
Water Reservoir Optimization v4 — With Evaporation Losses
=============================================================================
Changes from v3:
  - Incorporates hourly evaporation data from
    hourly_evaporation_empirical_overwater_updated.csv (1998-2022)
  - Water balance now: Level(t+1) = Level(t) + (Inflow - Discharge - Evap) * dt / Area
  - Evaporation ranges from ~1-5 m³/s equivalent (peaks midday)
  - All v3 constraints remain the same
=============================================================================
"""
import numpy as np
import csv
import time

np.random.seed(42)

# ============================================================
# DATA LOADING
# ============================================================
def sf(s, default=0.0):
    try: return float(s.strip())
    except: return default

def load_data(filepath):
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f); next(reader)
        return [{'time':r[0],'level':sf(r[2]),'discharge':sf(r[3]),
                 'head':sf(r[4]),'power':sf(r[5])} for r in reader if len(r)>=6]

def load_evaporation(filepath):
    """Load hourly evaporation data. Returns dict keyed by (year,month,day,hour) -> evap in m³/s."""
    evap = {}
    with open(filepath, 'r') as f:
        reader = csv.reader(f); next(reader)
        for r in reader:
            if len(r) >= 5:
                key = (int(r[0]), int(r[1]), int(r[2]), int(r[3]))
                # Convert mm/hr to m³/s: mm/hr * area_m2 / 1000 / 3600
                evap[key] = float(r[4]) * AREA_M2 / 1000.0 / 3600.0
    return evap

def parse_timestamp(ts):
    """Parse '9/14/12 0:00' -> (year, month, day, hour)."""
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

# Level <-> Storage conversion
AREA_M2 = 50e6; L_REF = 330.0; S_REF = 690000.0

def l2s(level): return S_REF + AREA_M2 * (level - L_REF) / 1000.0
def s2l(storage): return L_REF + (storage - S_REF) * 1000.0 / AREA_M2

# Electricity prices (ERCOT-style $/MWh)
PRICES = np.array([25,22,20,20,22,30,45,55,65,70,70,65,60,65,75,80,85,80,70,55,45,35,30,25.0])


# ============================================================
# RESERVOIR MODEL v4
# ============================================================
class ReservoirV4:
    def __init__(self, data, start_idx, evap_dict=None, horizon=24):
        self.horizon = horizon
        self.tailwater = 273.4
        self.eta = 0.976
        self.rho = 1000.0
        self.g = 9.81
        self.dt = 3600.0

        self.L0 = data[start_idx]['level']
        self.S0 = l2s(self.L0)

        # Load evaporation for this window (m³/s at each hour)
        self.evap = np.zeros(horizon)
        if evap_dict is not None:
            for t in range(horizon):
                ts = parse_timestamp(data[start_idx + t]['time'])
                if ts and ts in evap_dict:
                    self.evap[t] = max(0, evap_dict[ts])  # no negative evap

        # Estimate inflows (now accounting for evaporation)
        # Water balance: A * dL/dt = Inflow - Discharge - Evap
        # So: Inflow = Discharge + Evap + A * dL/dt
        self.inflows = np.zeros(horizon)
        for t in range(horizon):
            idx = start_idx + t
            Q = data[idx]['discharge']
            dL = (data[idx+1]['level'] - data[idx]['level']) if idx+1 < len(data) else 0
            self.inflows[t] = max(0, Q + self.evap[t] + AREA_M2 * dL / self.dt)

        # Historical data
        self.actual_Q = np.array([data[start_idx+t]['discharge'] for t in range(horizon)])
        self.actual_P = np.array([data[start_idx+t]['power'] for t in range(horizon)])
        self.prices = PRICES[:horizon]

        # ============================================================
        # DATA-CALIBRATED CONSTRAINTS
        # ============================================================

        # Release bounds (from physical turbine limits)
        self.Q_min = 2.0           # m³/s environmental minimum
        self.Q_max = 273.0         # m³/s turbine capacity

        # Storage band: stay within ±1.5m of starting level
        # This is tight enough to bind but achievable
        level_band = 1.5  # meters
        self.L_min = self.L0 - level_band
        self.L_max = self.L0 + level_band
        self.S_min = l2s(self.L_min)
        self.S_max = l2s(self.L_max)

        # Demand target: based on actual daily release for this window
        actual_total_tcm = sum(self.actual_Q) * self.dt / 1000.0
        # Target: similar to actual, ± 20% tolerance
        self.demand_target = actual_total_tcm
        self.demand_tolerance = max(actual_total_tcm * 0.20, 500)

        # End storage: within 2,000 TCM of start
        self.S_end_tol = 2000.0

        # Ramp rate: 40 m³/s per hour
        self.ramp_max = 40.0

        # Minimum total generation: at least 50% of actual
        self.min_gen = sum(self.actual_P) * 0.5

        self.n_vars = horizon

    def compute_levels(self, Q):
        L = np.zeros(self.horizon)
        L[0] = self.L0
        for t in range(1, self.horizon):
            L[t] = L[t-1] + (self.inflows[t-1] - Q[t-1] - self.evap[t-1]) * self.dt / AREA_M2
        return L

    def compute_power(self, Q):
        L = self.compute_levels(Q)
        H = np.maximum(L - self.tailwater, 0)
        P = self.eta * self.rho * self.g * Q * H / 1e6
        return P, L, H

    def revenue(self, Q):
        P, _, _ = self.compute_power(Q)
        return np.sum(self.prices * P)

    def total_release_tcm(self, Q):
        return np.sum(Q) * self.dt / 1000.0

    def objective(self, Q):
        return -self.revenue(Q)

    def constraint_violations(self, Q):
        P, L, H = self.compute_power(Q)
        S = np.array([l2s(l) for l in L])
        v = []

        # Storage bounds (2 per timestep = 48)
        for t in range(self.horizon):
            v.append(max(0, self.S_min - S[t]))
            v.append(max(0, S[t] - self.S_max))

        # Demand (2)
        total = self.total_release_tcm(Q)
        v.append(max(0, (self.demand_target - self.demand_tolerance) - total))
        v.append(max(0, total - (self.demand_target + self.demand_tolerance)))

        # Ramp rate (23)
        for t in range(1, self.horizon):
            v.append(max(0, abs(Q[t] - Q[t-1]) - self.ramp_max))

        # End storage (1)
        S_final = S[-1]
        v.append(max(0, abs(S_final - self.S0) - self.S_end_tol))

        # Minimum generation (1)
        total_gen = np.sum(P)
        v.append(max(0, self.min_gen - total_gen))

        return np.array(v)

    def total_violation(self, Q):
        return float(np.sum(self.constraint_violations(Q)))

    def is_feasible(self, Q, tol=0.1):
        return bool(np.all(self.constraint_violations(Q) <= tol))

    def n_constraints_satisfied(self, Q, tol=0.1):
        v = self.constraint_violations(Q)
        return int(np.sum(v <= tol)), len(v)

    def describe(self):
        print(f"  Starting: level={self.L0:.3f}m, storage={self.S0:.0f} TCM")
        print(f"  Level band: {self.L_min:.2f} - {self.L_max:.2f} m")
        print(f"  Storage band: {self.S_min:.0f} - {self.S_max:.0f} TCM")
        print(f"  Release: {self.Q_min} - {self.Q_max} m³/s")
        print(f"  Demand: {self.demand_target:.0f} ± {self.demand_tolerance:.0f} TCM")
        print(f"  Ramp max: {self.ramp_max} m³/s/hr")
        print(f"  End storage tol: ±{self.S_end_tol:.0f} TCM")
        print(f"  Min generation: {self.min_gen:.0f} MWh")
        print(f"  Evaporation: avg={np.mean(self.evap):.2f} m³/s, "
              f"max={np.max(self.evap):.2f} m³/s, "
              f"daily loss={np.sum(self.evap)*self.dt/1000:.0f} TCM")
        n = 2*self.horizon + 2 + (self.horizon-1) + 1 + 1
        print(f"  Total constraints: {n}")


# ============================================================
# OPTIMIZERS
# ============================================================
class AdamOpt:
    def __init__(self, lr=0.5):
        self.lr=lr;self.b1=0.9;self.b2=0.999;self.eps=1e-8;self.m={};self.v={};self.t=0
    def step(self, x, g):
        k='x'
        if k not in self.m: self.m[k]=np.zeros_like(x);self.v[k]=np.zeros_like(x)
        self.t+=1
        self.m[k]=self.b1*self.m[k]+(1-self.b1)*g
        self.v[k]=self.b2*self.v[k]+(1-self.b2)*g**2
        mh=self.m[k]/(1-self.b1**self.t);vh=self.v[k]/(1-self.b2**self.t)
        return x-self.lr*mh/(np.sqrt(vh)+self.eps)


# ============================================================
# PENALTY OPTIMIZATION
# ============================================================
def num_grad(model, Q, lam, ptype):
    eps = 1e-4; n = len(Q)
    f0 = model.objective(Q)
    v0 = model.constraint_violations(Q)
    p0 = lam * (np.sum(v0) if ptype=='L1' else np.sum(v0**2))
    grad = np.zeros(n)
    for i in range(n):
        Qp = Q.copy(); Qp[i] = min(Qp[i]+eps, model.Q_max)
        fp = model.objective(Qp)
        vp = model.constraint_violations(Qp)
        pp = lam * (np.sum(vp) if ptype=='L1' else np.sum(vp**2))
        grad[i] = (fp+pp-f0-p0) / eps
    return grad


def optimize(model, method='baseline', ptype='L1', max_iters=10000):
    n = model.horizon
    Q = model.actual_Q.copy() + np.random.randn(n) * 2.0
    Q = np.clip(Q, model.Q_min, model.Q_max)

    opt = AdamOpt(lr=0.3)
    lam = 1.0; best_Q = Q.copy(); best_rev = -1e30
    prev_viol = model.total_violation(Q)
    init_viol = max(prev_viol, 1e-10)
    w_viol = 5.0

    for it in range(max_iters):
        grad = num_grad(model, Q, lam, ptype)
        gnorm = np.linalg.norm(grad)
        if gnorm > 100: grad *= 100/gnorm

        Q = opt.step(Q, grad)
        Q = np.clip(Q, model.Q_min, model.Q_max)

        if model.is_feasible(Q):
            rev = model.revenue(Q)
            if rev > best_rev: best_rev = rev; best_Q = Q.copy()

        if (it+1) % 500 == 0:
            cv = model.total_violation(Q)

            if method == 'baseline':
                if (it+1) % 2000 == 0 and not model.is_feasible(Q):
                    lam *= 10

            elif method == 'adaptive':
                if not model.is_feasible(Q) and prev_viol > 1e-12:
                    r = cv / prev_viol
                    if r < 0.5: lam = min(lam*2, 1e8)
                    elif r < 0.9: lam = min(lam*3, 1e8)
                    else: lam = min(lam*10, 1e8)

            elif method == 'learnable':
                prog = it/max_iters
                vr = min(cv/init_viol, 10)
                if not model.is_feasible(Q):
                    lam *= max(1, 1 + w_viol*vr + 3*prog)
                if prev_viol > 1e-12:
                    ch = (cv-prev_viol)/prev_viol
                    if ch > 0.05: w_viol = min(w_viol+0.3, 20)
                    elif ch < -0.1: w_viol *= 0.95
                if (it+1) % 2000 == 0 and not model.is_feasible(Q):
                    lam *= 5

            prev_viol = cv; lam = min(lam, 1e8)

    return best_Q if best_rev > -1e30 else Q


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    print("="*90)
    print("  WATER RESERVOIR OPTIMIZATION v4 — WITH EVAPORATION LOSSES")
    print("="*90)

    data = load_data('/content/hydropower_hourly.csv')
    print(f"Loaded {len(data)} hydropower records")

    evap_dict = load_evaporation('/content/hourly_evaporation_empirical_overwater_updated.csv')
    print(f"Loaded {len(evap_dict)} evaporation records")

    # Find good test windows (active generation, moderate releases)
    windows = []
    for s in range(6000, len(data)-24, 24*7):
        Qs = [data[s+t]['discharge'] for t in range(24)]
        gen = sum(data[s+t]['power'] for t in range(24))
        avg_q = np.mean(Qs)
        if gen > 200 and avg_q > 20:
            windows.append(s)
            if len(windows) >= 5: break

    print(f"Test windows: {len(windows)}")

    # Show constraints for first window
    m0 = ReservoirV4(data, windows[0], evap_dict)
    print(f"\n  CONSTRAINTS (Window 0: {data[windows[0]]['time']}):")
    m0.describe()

    # Check actual feasibility
    af = m0.is_feasible(m0.actual_Q)
    av = m0.total_violation(m0.actual_Q)
    ns,nt = m0.n_constraints_satisfied(m0.actual_Q)
    ar = m0.revenue(m0.actual_Q)
    print(f"\n  ACTUAL: feasible={af}, violation={av:.2f}, sat={ns}/{nt}, revenue=${ar:.0f}")
    print(f"  Actual release: {m0.total_release_tcm(m0.actual_Q):.0f} TCM "
          f"(target: {m0.demand_target:.0f} ± {m0.demand_tolerance:.0f})")

    methods = ['baseline', 'adaptive', 'learnable']

    print(f"\n{'='*105}")
    print(f"{'Win':>3} {'Start':<16} {'Method':<11} {'Pen':>3} "
          f"{'Actual$':>9} {'Opt$':>9} {'Improve':>9} "
          f"{'Feas':>5} {'Viol':>10} {'Sat':>7} {'Time':>6}")
    print(f"{'-'*105}")

    results = []
    for wi, s in enumerate(windows):
        model = ReservoirV4(data, s, evap_dict)
        actual_rev = model.revenue(model.actual_Q)

        for method in methods:
            for ptype in ['L1', 'L2']:
                np.random.seed(42)
                t0 = time.time()
                oQ = optimize(model, method, ptype, max_iters=8000)
                elapsed = time.time() - t0

                orev = model.revenue(oQ)
                imp = orev - actual_rev
                feas = model.is_feasible(oQ)
                viol = model.total_violation(oQ)
                ns,nt = model.n_constraints_satisfied(oQ)

                results.append({'wi':wi,'start':data[s]['time'],'method':method,
                               'ptype':ptype,'actual':actual_rev,'opt':orev,
                               'imp':imp,'feas':feas,'viol':viol,'ns':ns,'nt':nt,'t':elapsed})

                print(f"{wi:>3} {data[s]['time']:<16} {method:<11} {ptype:>3} "
                      f"${actual_rev:>8.0f} ${orev:>8.0f} ${imp:>+8.0f} "
                      f"{'YES' if feas else 'no':>5} {viol:>10.2f} {ns:>3}/{nt:<3} {elapsed:>5.1f}s")

    # Summary
    print(f"\n{'='*80}")
    print(f"{'SUMMARY':^80}")
    print(f"{'='*80}")
    for method in methods:
        for pt in ['L1','L2']:
            sub = [r for r in results if r['method']==method and r['ptype']==pt]
            if sub:
                ai = np.mean([r['imp'] for r in sub])
                nf = sum(1 for r in sub if r['feas'])
                av = np.mean([r['viol'] for r in sub])
                print(f"  {method:<11} {pt}: avg improve ${ai:>+8.0f}, "
                      f"feasible {nf}/{len(sub)}, avg viol {av:.2f}")

    # Best hourly schedule
    feas_r = [r for r in results if r['feas']]
    if feas_r:
        best = max(feas_r, key=lambda r: r['imp'])
        model = ReservoirV4(data, windows[best['wi']], evap_dict)
        np.random.seed(42)
        oQ = optimize(model, best['method'], best['ptype'], 8000)
        oP, oL, oH = model.compute_power(oQ)
        aP, aL, _ = model.compute_power(model.actual_Q)

        print(f"\n{'='*90}")
        print(f"  BEST: {best['method']} {best['ptype']}, {best['start']}")
        print(f"{'='*90}")
        print(f"{'Hr':>3} {'$/MWh':>6} {'ActQ':>6} {'OptQ':>6} {'ActP':>6} {'OptP':>6} "
              f"{'ActL':>8} {'OptL':>8} {'Evap':>5} {'Ramp':>6}")
        print(f"{'-'*66}")
        for t in range(24):
            ramp = f"{oQ[t]-oQ[t-1]:+.1f}" if t>0 else "  ---"
            print(f"{t:>3} ${model.prices[t]:>5.0f} {model.actual_Q[t]:>6.1f} {oQ[t]:>6.1f} "
                  f"{aP[t]:>6.1f} {oP[t]:>6.1f} {aL[t]:>8.3f} {oL[t]:>8.3f} "
                  f"{model.evap[t]:>5.1f} {ramp:>6}")
        print(f"\n  Revenue: actual ${model.revenue(model.actual_Q):.0f} → optimized ${model.revenue(oQ):.0f}")
        print(f"  Release: actual {model.total_release_tcm(model.actual_Q):.0f} TCM → "
              f"optimized {model.total_release_tcm(oQ):.0f} TCM")
        print(f"  Evaporation loss: {np.sum(model.evap)*model.dt/1000:.0f} TCM over 24h")
    else:
        print("\n  No feasible solution found.")
        # Show closest to feasible
        best_infeas = min(results, key=lambda r: r['viol'])
        print(f"  Closest: {best_infeas['method']} {best_infeas['ptype']}, "
              f"violation={best_infeas['viol']:.2f}, sat={best_infeas['ns']}/{best_infeas['nt']}")

    print("\nDone!")
