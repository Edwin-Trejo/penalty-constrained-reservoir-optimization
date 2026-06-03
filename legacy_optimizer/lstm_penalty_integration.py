"""
=============================================================================
LSTM + Penalty Integration: Constraint-Aware Training
=============================================================================
Based on Jose Vega's DOF-LSTM (SLSTMV_Penalty.py).
Modified by Edwin Trejo for Google Colab.

Runs two experiments:
  1. Standard LSTM: Loss = MSE(predicted, actual)  [no penalty]
  2. Penalty LSTM:  Loss = MSE(predicted, actual) + λ × penalty(violations)

Compares: prediction accuracy (MSE, MAE) and constraint violation rate.

Data: USIBWC discharge measurements (TCM, 15-min intervals)
=============================================================================
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error

np.random.seed(40)

# ============================================================
# DATA LOADING (replaces Ingestor dependency)
# ============================================================
def load_discharge_data(filepath):
    """Load USIBWC discharge CSV directly."""
    df = pd.read_csv(filepath, skiprows=1)  # skip comment row
    df.columns = ['Timestamp', 'Value']
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df.set_index('Timestamp', inplace=True)
    df['Value'] = pd.to_numeric(df['Value'], errors='coerce').ffill()
    return df

# ============================================================
# OPTIMIZER (from Jose's code)
# ============================================================
class AdamOptimizer:
    def __init__(self, lr=0.001, beta_1=0.95, beta_2=0.999, epsilon=1e-8):
        self.lr = lr
        self.beta_1 = beta_1
        self.beta_2 = beta_2
        self.epsilon = epsilon
        self.m = {}
        self.v = {}
        self.t = 0

    def update(self, param, grad, key):
        if key not in self.m:
            self.m[key] = np.zeros_like(grad)
            self.v[key] = np.zeros_like(grad)
        self.t += 1
        self.m[key] = self.beta_1 * self.m[key] + (1 - self.beta_1) * grad
        self.v[key] = self.beta_2 * self.v[key] + (1 - self.beta_2) * (grad ** 2)
        m_hat = self.m[key] / (1 - self.beta_1 ** self.t)
        v_hat = self.v[key] / (1 - self.beta_2 ** self.t)
        param -= self.lr * m_hat / (np.sqrt(v_hat) + self.epsilon)
        return param


# ============================================================
# DOF-LSTM MODEL (from Jose's code, with penalty integration)
# ============================================================
class DOF_LSTM:
    def __init__(self, input_dim, hidden_dim, output_dim, learning_rate=0.001,
                 clip_norm=5.0, dropout_rate=0.2):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        self.clip_norm = clip_norm
        self.dropout_rate = dropout_rate
        self.optimizer = AdamOptimizer(lr=learning_rate)

        def xavier_init(shape):
            return np.random.randn(*shape) * np.sqrt(1. / shape[1])

        self.W = {gate: xavier_init((hidden_dim, hidden_dim + input_dim + 1))
                  for gate in ['f', 'i', 'c', 'o']}
        self.b = {gate: np.zeros((hidden_dim, 1)) for gate in ['f', 'i', 'c', 'o']}
        self.W['y'] = xavier_init((output_dim, hidden_dim))
        self.b['y'] = np.zeros((output_dim, 1))

    @staticmethod
    def sigmoid(x):
        return 1 / (1 + np.exp(-np.clip(x, -500, 500)))

    @staticmethod
    def tanh(x):
        return np.tanh(np.clip(x, -500, 500))

    def dropout(self, x, training=True):
        if self.dropout_rate > 0 and training:
            mask = np.random.binomial(1, 1 - self.dropout_rate, size=x.shape)
            return x * mask / (1 - self.dropout_rate)
        return x

    def adaptive_thresholding(self, c_t, c_prev, deviation_threshold,
                               optimizer, key, alpha=0.95, temperature=1.0):
        """DOF filter: Vega's dynamic outlier filter on cell state."""
        grad_c_t = np.abs(c_t - c_prev)
        smoothed_state = optimizer.update(c_prev, grad_c_t, key)
        std_c_t = np.std(c_t) + 1e-6
        deviation = np.abs(c_t - smoothed_state)
        grad_clip = np.clip(grad_c_t / std_c_t, -10, 10)
        adaptive_threshold = deviation_threshold * std_c_t * (1 + np.tanh(grad_clip))
        scaled_threshold = adaptive_threshold * temperature
        replace_mask = deviation >= scaled_threshold
        replacement = np.random.uniform(-scaled_threshold[replace_mask],
                                         scaled_threshold[replace_mask])
        adjusted_alpha = alpha * (1 - np.tanh(np.mean(grad_c_t) / std_c_t))
        c_t[replace_mask] = adjusted_alpha * c_t[replace_mask] + \
                            (1 - adjusted_alpha) * replacement
        return c_t

    def forward(self, x, cache_enabled=True, temperature=1.0, training=True):
        T, _ = x.shape
        h_t = np.zeros((self.hidden_dim, 1))
        c_t = np.zeros((self.hidden_dim, 1))
        cache = []

        for t in range(T):
            x_t = x[t].reshape(-1, 1)
            combined = np.vstack((h_t, np.ones((1, 1)), x_t))

            f_t = self.sigmoid(np.dot(self.W['f'], combined) + self.b['f'])
            i_t = self.sigmoid(np.dot(self.W['i'], combined) + self.b['i'])
            o_t = self.sigmoid(np.dot(self.W['o'], combined) + self.b['o'])
            c_candidate = self.tanh(np.dot(self.W['c'], combined) + self.b['c'])
            c_prev = c_t.copy()

            c_t = f_t * c_t + i_t * c_candidate
            c_t = self.adaptive_thresholding(c_t, c_prev, 2.0,
                                              self.optimizer, f"time_{t}", 0.95, temperature)

            h_t = o_t * self.tanh(c_t)

            if training:
                h_t = self.dropout(h_t, training=True)

            if cache_enabled:
                cache.append({
                    'combined': combined, 'f': f_t, 'i': i_t, 'o': o_t,
                    'c_candidate': c_candidate, 'c_prev': c_prev,
                    'c': c_t.copy(), 'h': h_t.copy()
                })

        y_t = np.dot(self.W['y'], h_t) + self.b['y']

        if cache_enabled:
            return y_t.flatten(), h_t, cache
        else:
            return y_t.flatten(), h_t

    def backward(self, x, y_true, cache, y_pred, lam_bounds=0.0, y_min=0.0, y_max=1.0):
        """Backprop with optional penalty gradient for bound violations."""
        d_y = 2 * (y_pred.reshape(-1, 1) - y_true)

        # Penalty gradient for bounds (Edwin's contribution)
        y = y_pred.reshape(-1, 1)
        dpen = np.zeros_like(y)
        mask_low = y < y_min
        dpen[mask_low] = 2.0 * (y[mask_low] - y_min)  # push up
        mask_high = y > y_max
        dpen[mask_high] = 2.0 * (y[mask_high] - y_max)  # push down
        d_y = d_y + lam_bounds * dpen

        last_cache = cache[-1]
        h_T = last_cache['h']
        dW_y = np.dot(d_y, h_T.T)
        db_y = d_y.copy()
        d_h = np.dot(self.W['y'].T, d_y)

        grad_W = {gate: np.zeros_like(self.W[gate]) for gate in ['f', 'i', 'c', 'o']}
        grad_b = {gate: np.zeros_like(self.b[gate]) for gate in ['f', 'i', 'c', 'o']}
        d_c = np.zeros((self.hidden_dim, 1))

        for t in reversed(range(len(cache))):
            ct = cache[t]
            f_t, i_t, o_t = ct['f'], ct['i'], ct['o']
            c_candidate, c_t, c_prev = ct['c_candidate'], ct['c'], ct['c_prev']
            combined = ct['combined']

            d_o = d_h * self.tanh(c_t)
            d_o_input = d_o * (o_t * (1 - o_t))
            d_tanh_c = d_h * o_t * (1 - self.tanh(c_t) ** 2)
            d_c_total = d_tanh_c + d_c
            d_f = d_c_total * c_prev
            d_f_input = d_f * (f_t * (1 - f_t))
            d_i = d_c_total * c_candidate
            d_i_input = d_i * (i_t * (1 - i_t))
            d_c_cand = d_c_total * i_t
            d_c_cand_input = d_c_cand * (1 - c_candidate ** 2)

            grad_W['f'] += np.dot(d_f_input, combined.T)
            grad_b['f'] += d_f_input
            grad_W['i'] += np.dot(d_i_input, combined.T)
            grad_b['i'] += d_i_input
            grad_W['o'] += np.dot(d_o_input, combined.T)
            grad_b['o'] += d_o_input
            grad_W['c'] += np.dot(d_c_cand_input, combined.T)
            grad_b['c'] += d_c_cand_input

            d_combined = (np.dot(self.W['f'].T, d_f_input) +
                          np.dot(self.W['i'].T, d_i_input) +
                          np.dot(self.W['o'].T, d_o_input) +
                          np.dot(self.W['c'].T, d_c_cand_input))
            d_h = d_combined[:self.hidden_dim, :]
            d_c = d_c_total * f_t

        return grad_W, grad_b, dW_y, db_y

    def _clip_gradients(self, grad):
        norm = np.linalg.norm(grad)
        if norm > self.clip_norm:
            grad = grad * (self.clip_norm / norm)
        return grad

    def train(self, X_train, y_train, epochs=50, batch_size=32,
              initial_temperature=1.0, anneal_rate=0.99,
              lam_bounds=0.0, y_min=0.0, y_max=1.0, strategy='none'):
        """
        Train with optional penalty and lambda scheduling strategy.
        Strategies:
          'none'       - no penalty (lam_bounds=0 forced)
          'fixed'      - fixed lambda throughout training
          'progressive'- lambda starts at lam_bounds, multiplied by 10 every 10 epochs
          'adaptive'   - lambda adjusted based on violation trend every 5 epochs
          'learnable'  - lambda computed from violation state with online-learned weights
        """
        if strategy == 'none':
            lam_bounds = 0.0

        lam = lam_bounds if lam_bounds > 0 else 1.0  # starting lambda for strategies
        print(f"\nTraining DOF-LSTM [{strategy}] (initial lam={lam if strategy != 'none' else 0})...")
        n_samples = len(X_train)
        temperature = initial_temperature
        history = []
        lam_history = []

        # For adaptive/learnable: track violations
        prev_viol = None
        init_viol = None
        # For learnable: controller weights
        w_viol = 5.0

        for epoch in range(epochs):
            perm = np.random.permutation(n_samples)
            X_s, y_s = X_train[perm], y_train[perm]
            total_loss = 0.0
            epoch_violations = 0.0
            batch_count = 0

            # Current effective lambda
            if strategy == 'none':
                eff_lam = 0.0
            elif strategy == 'fixed':
                eff_lam = lam_bounds
            else:
                eff_lam = lam

            for i in range(0, n_samples, batch_size):
                X_b, y_b = X_s[i:i+batch_size], y_s[i:i+batch_size]
                acc_gW = {g: np.zeros_like(self.W[g]) for g in ['f','i','c','o']}
                acc_gb = {g: np.zeros_like(self.b[g]) for g in ['f','i','c','o']}
                acc_dWy = np.zeros_like(self.W['y'])
                acc_dby = np.zeros_like(self.b['y'])
                batch_loss = 0.0

                for j in range(len(X_b)):
                    y_true = y_b[j].reshape(-1, 1)
                    y_pred, h, cache = self.forward(X_b[j], cache_enabled=True,
                                                     temperature=temperature, training=True)
                    loss = np.mean((y_pred - y_true) ** 2)

                    # Penalty
                    v_low = np.maximum(0.0, y_min - y_pred)
                    v_high = np.maximum(0.0, y_pred - y_max)
                    pen = np.mean(v_low**2 + v_high**2)
                    epoch_violations += np.sum(v_low) + np.sum(v_high)
                    batch_loss += loss + eff_lam * pen

                    gW, gb, dWy, dby = self.backward(X_b[j], y_true, cache, y_pred,
                                                      lam_bounds=eff_lam,
                                                      y_min=y_min, y_max=y_max)
                    for g in ['f','i','c','o']:
                        acc_gW[g] += gW[g]; acc_gb[g] += gb[g]
                    acc_dWy += dWy; acc_dby += dby

                bs = len(X_b)
                for g in ['f','i','c','o']:
                    acc_gW[g] = self._clip_gradients(acc_gW[g] / bs)
                    acc_gb[g] = self._clip_gradients(acc_gb[g] / bs)
                    self.W[g] = self.optimizer.update(self.W[g], acc_gW[g], f'W_{g}')
                    self.b[g] = self.optimizer.update(self.b[g], acc_gb[g], f'b_{g}')
                self.W['y'] = self.optimizer.update(self.W['y'],
                              self._clip_gradients(acc_dWy/bs), 'W_y')
                self.b['y'] = self.optimizer.update(self.b['y'],
                              self._clip_gradients(acc_dby/bs), 'b_y')

                total_loss += batch_loss / bs
                batch_count += 1

            avg_loss = total_loss / batch_count
            avg_viol = epoch_violations / n_samples
            history.append(avg_loss)
            lam_history.append(eff_lam)

            # Initialize violation tracking
            if init_viol is None and avg_viol > 0:
                init_viol = avg_viol
            if prev_viol is None:
                prev_viol = avg_viol

            # ---- LAMBDA SCHEDULING ----
            if strategy == 'progressive':
                # Multiply by 10 every 10 epochs
                if (epoch + 1) % 10 == 0 and avg_viol > 1e-6:
                    lam = min(lam * 10, 1e6)

            elif strategy == 'adaptive':
                # Check every 5 epochs, adjust based on violation trend
                if (epoch + 1) % 5 == 0 and prev_viol > 1e-12:
                    ratio = avg_viol / prev_viol
                    if ratio < 0.5:
                        lam = min(lam * 2, 1e6)    # good progress, gentle increase
                    elif ratio < 0.9:
                        lam = min(lam * 3, 1e6)    # moderate progress
                    else:
                        lam = min(lam * 10, 1e6)   # stuck, aggressive increase
                    prev_viol = avg_viol

            elif strategy == 'learnable':
                # Online controller: lambda based on violation state
                if init_viol and init_viol > 0:
                    prog = epoch / epochs
                    vr = min(avg_viol / init_viol, 10)
                    lam_mult = max(1, 1 + w_viol * vr + 3 * prog)
                    lam = lam_bounds * lam_mult
                    # Update controller weight
                    if prev_viol > 1e-12:
                        change = (avg_viol - prev_viol) / prev_viol
                        if change > 0.05:
                            w_viol = min(w_viol + 0.3, 20)
                        elif change < -0.1:
                            w_viol *= 0.95
                    if (epoch + 1) % 10 == 0 and avg_viol > 1e-6:
                        lam *= 5
                    lam = min(lam, 1e6)
                    prev_viol = avg_viol

            if (epoch + 1) % 10 == 0 or epoch == 0:
                print(f"  Epoch {epoch+1}/{epochs}, Loss: {avg_loss:.6f}, "
                      f"Viol: {avg_viol:.4f}, \u03BB: {eff_lam:.1f}")

            temperature *= anneal_rate

        return history, lam_history

    def predict(self, X):
        """Predict without dropout or caching."""
        preds = []
        for x in X:
            y_pred, _ = self.forward(x, cache_enabled=False, training=False)
            preds.append(y_pred)
        return np.array(preds).reshape(-1, 1)


# ============================================================
# MAIN: COMPARISON EXPERIMENT
# ============================================================
if __name__ == '__main__':
    print("="*80)
    print("  LSTM + PENALTY INTEGRATION: Constraint-Aware Training")
    print("="*80)

    # Load data
    DATA_FILE = '/content/DataSetExport-Discharge_Total_Last-24-Hour-Change-in-Storage_08450800-Instantaneous-TCM-20240622194957.csv'
    df = load_discharge_data(DATA_FILE)
    print(f"Loaded {len(df)} records, date range: {df.index[0]} to {df.index[-1]}")
    print(f"Value range: {df['Value'].min():.1f} to {df['Value'].max():.1f} TCM")

    # Add time features (same as Jose)
    df['hour'] = df.index.hour
    df['dayofweek'] = df.index.dayofweek
    df['month'] = df.index.month
    df['day'] = df.index.day

    # Scale
    scaler_value = MinMaxScaler()
    scaler_time = MinMaxScaler()
    features = df[['Value', 'hour', 'dayofweek', 'month', 'day']].copy()
    scaled_values = scaler_value.fit_transform(features[['Value']])
    scaled_time = scaler_time.fit_transform(features.drop(columns='Value'))
    combined_scaled = np.hstack([scaled_values, scaled_time])

    # Create sequences
    seq_length = 10
    X, y = [], []
    for i in range(seq_length, len(combined_scaled)):
        X.append(combined_scaled[i-seq_length:i])
        y.append(combined_scaled[i, 0])
    X, y = np.array(X), np.array(y).reshape(-1, 1)

    train_size = int(len(X) * 0.8)
    X_train, y_train = X[:train_size], y[:train_size]
    X_test, y_test = X[train_size:], y[train_size:]
    print(f"Train: {len(X_train)}, Test: {len(X_test)}")

    # Constraint bounds in SCALED space
    # Physical zero (0 TCM) mapped to scaled space:
    #   scaled_zero = (0 - data_min) / (data_max - data_min)
    # This ensures the penalty enforces non-negative releases in REAL units
    val_min = scaler_value.data_min_[0]   # most negative value in data
    val_max = scaler_value.data_max_[0]   # most positive value in data
    val_range = val_max - val_min

    Y_MIN = (0.0 - val_min) / val_range   # physical 0 TCM in scaled space
    Y_MAX = 1.0                            # physical max in scaled space

    print(f"\n  Constraint bounds:")
    print(f"  Physical range: [{val_min:.1f}, {val_max:.1f}] TCM")
    print(f"  Physical zero (0 TCM) = {Y_MIN:.4f} in scaled space")
    print(f"  Penalty enforces: predictions >= 0 TCM (non-negative releases)")

    # ============================================================
    # FOUR-STRATEGY EXPERIMENT
    # ============================================================
    y_test_inv = scaler_value.inverse_transform(y_test)

    STRATEGIES = [
        ('none',        0.0,  'No Penalty'),
        ('fixed',       5.0,  'Fixed \u03BB=5'),
        ('progressive', 1.0,  'Progressive'),
        ('adaptive',    1.0,  'Adaptive'),
        ('learnable',   1.0,  'Learnable'),
    ]

    results = []

    for strategy, init_lam, label in STRATEGIES:
        print(f"\n{'='*80}")
        print(f"  EXPERIMENT: {label}")
        print(f"{'='*80}")

        np.random.seed(40)  # same seed for fair comparison
        model = DOF_LSTM(input_dim=5, hidden_dim=64, output_dim=1,
                         learning_rate=0.001, clip_norm=1.0, dropout_rate=0.001)
        hist, lam_hist = model.train(X_train, y_train, epochs=50, batch_size=32,
                                      lam_bounds=init_lam, y_min=Y_MIN, y_max=Y_MAX,
                                      strategy=strategy)

        preds = model.predict(X_test)
        preds_inv = scaler_value.inverse_transform(preds)

        mse_val = mean_squared_error(y_test_inv, preds_inv)
        mae_val = mean_absolute_error(y_test_inv, preds_inv)
        n_negative = int(np.sum(preds_inv < 0))
        n_total = len(y_test)
        neg_vals = preds_inv[preds_inv < 0]
        avg_neg = float(np.mean(neg_vals)) if len(neg_vals) > 0 else 0.0
        min_pred = float(preds_inv.min())
        max_lam = max(lam_hist) if lam_hist else 0

        results.append({
            'strategy': strategy, 'label': label, 'init_lam': init_lam,
            'mse': mse_val, 'mae': mae_val,
            'n_neg': n_negative, 'rate': n_negative/n_total*100,
            'avg_neg': avg_neg, 'min_pred': min_pred, 'max_lam': max_lam,
            'preds_inv': preds_inv.copy(), 'hist': hist, 'lam_hist': lam_hist
        })

    # ============================================================
    # COMPARISON TABLE
    # ============================================================
    print(f"\n{'='*110}")
    print(f"{'COMPARISON: Four Penalty Strategies in DOF-LSTM Training':^110}")
    print(f"{'='*110}")

    baseline = results[0]  # no penalty

    print(f"\n  {'Strategy':<14} {'MSE':>10} {'MAE':>8} {'MSE Chg':>9} "
          f"{'Neg':>5} {'Rate':>7} {'Avg Neg':>9} {'Min Pred':>10} {'Max \u03BB':>10}")
    print(f"  {'-'*88}")

    for r in results:
        mse_chg = (r['mse'] - baseline['mse']) / baseline['mse'] * 100 if baseline['mse'] > 0 else 0
        chg_str = f"{mse_chg:>+8.1f}%" if r['strategy'] != 'none' else "    \u2014"
        print(f"  {r['label']:<14} {r['mse']:>10.0f} {r['mae']:>8.1f} {chg_str} "
              f"{r['n_neg']:>5} {r['rate']:>6.1f}% {r['avg_neg']:>9.1f} {r['min_pred']:>10.1f} "
              f"{r['max_lam']:>10.1f}")

    # Find best penalty result
    pen_results = [r for r in results if r['strategy'] != 'none']
    best_pen = min(pen_results, key=lambda r: (r['n_neg'], r['mse']))

    print(f"\n  Summary:")
    print(f"  Baseline (no penalty): {baseline['n_neg']}/{len(y_test)} negative predictions "
          f"({baseline['rate']:.1f}%), avg={baseline['avg_neg']:.0f} TCM")
    print(f"  Best strategy ({best_pen['label']}): {best_pen['n_neg']}/{len(y_test)} negative "
          f"predictions ({best_pen['rate']:.1f}%), avg={best_pen['avg_neg']:.0f} TCM")

    if best_pen['n_neg'] < baseline['n_neg']:
        reduction = baseline['n_neg'] - best_pen['n_neg']
        pct = reduction / max(1, baseline['n_neg']) * 100
        mse_cost = (best_pen['mse'] - baseline['mse']) / baseline['mse'] * 100
        print(f"  >> {best_pen['label']} eliminated {reduction} violations ({pct:.0f}% reduction)")
        print(f"  >> MSE change: {mse_cost:+.1f}%")
    
    # Check severity improvement
    sev_results = sorted(pen_results, key=lambda r: abs(r['avg_neg']))
    least_severe = sev_results[0]
    if abs(least_severe['avg_neg']) < abs(baseline['avg_neg']):
        sev_improve = (1 - abs(least_severe['avg_neg']) / abs(baseline['avg_neg'])) * 100
        print(f"  >> {least_severe['label']} reduced violation severity by {sev_improve:.0f}% "
              f"(avg neg: {baseline['avg_neg']:.0f} \u2192 {least_severe['avg_neg']:.0f} TCM)")

    # Lambda evolution
    print(f"\n  Lambda evolution (final values):")
    for r in results:
        if r['strategy'] not in ['none', 'fixed'] and r['lam_hist']:
            print(f"    {r['label']:<14}: \u03BB went from {r['lam_hist'][0]:.1f} to {r['lam_hist'][-1]:.1f} "
                  f"(max: {r['max_lam']:.1f})")

    # ============================================================
    # SAVE PLOT
    # ============================================================
    colors = {'none': 'black', 'fixed': 'blue', 'progressive': 'green',
              'adaptive': 'orange', 'learnable': 'red'}

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # Plot 1: Predictions comparison
    axes[0,0].plot(y_test_inv, label='Actual', color='gray', linewidth=1.5, alpha=0.5)
    for r in results:
        axes[0,0].plot(r['preds_inv'], label=r['label'],
                        color=colors[r['strategy']], linewidth=1, alpha=0.8)
    axes[0,0].axhline(y=0, color='green', linestyle='--', linewidth=2, alpha=0.5,
                        label='C1: min=0 TCM')
    axes[0,0].set_title('Predictions by Strategy (all test samples)')
    axes[0,0].set_ylabel('Discharge (TCM)')
    axes[0,0].legend(fontsize=8, loc='upper right')
    axes[0,0].grid(True, alpha=0.3)

    # Plot 2: Lambda evolution over epochs
    for r in results:
        if r['strategy'] not in ['none', 'fixed'] and r['lam_hist']:
            axes[0,1].plot(r['lam_hist'], label=r['label'],
                            color=colors[r['strategy']], linewidth=1.5)
    axes[0,1].set_title('\u03BB Evolution During Training')
    axes[0,1].set_xlabel('Epoch')
    axes[0,1].set_ylabel('\u03BB')
    if any(r['max_lam'] > 10 for r in results if r['strategy'] not in ['none','fixed']):
        axes[0,1].set_yscale('log')
    axes[0,1].legend(fontsize=9)
    axes[0,1].grid(True, alpha=0.3)

    # Plot 3: Bar chart - violations per strategy
    labels = [r['label'] for r in results]
    x = range(len(labels))
    neg_counts = [r['n_neg'] for r in results]
    bar_colors = [colors[r['strategy']] for r in results]
    axes[1,0].bar(x, neg_counts, color=bar_colors, alpha=0.8)
    axes[1,0].set_xticks(list(x))
    axes[1,0].set_xticklabels(labels, rotation=15, fontsize=9)
    axes[1,0].set_ylabel('Negative Predictions (out of 130)')
    axes[1,0].set_title('Constraint Violations by Strategy')
    for i, r in enumerate(results):
        axes[1,0].text(i, r['n_neg']+0.5, str(r['n_neg']), ha='center', fontsize=11, fontweight='bold')

    # Plot 4: Training loss curves
    for r in results:
        axes[1,1].plot(r['hist'], label=r['label'],
                        color=colors[r['strategy']], linewidth=1.5, alpha=0.8)
    axes[1,1].set_title('Training Loss Over Epochs')
    axes[1,1].set_xlabel('Epoch')
    axes[1,1].set_ylabel('Loss')
    axes[1,1].legend(fontsize=8)
    axes[1,1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('lstm_penalty_comparison.png', dpi=150, bbox_inches='tight')
    print(f"\nSaved: lstm_penalty_comparison.png")
    plt.close()

    print(f"\nDone!")
