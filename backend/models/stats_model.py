import numpy as np
from typing import Dict, List, Tuple

class StatisticalAnomalyDetector:
    # Z-score tuning
    Z_NORM_SCALE = 3

    # EMA tuning
    EMA_NORM_SCALE = 5
    EPS = 1e-6

    # Spike tuning
    SPIKE_NORM_SCALE = 10

    # Thresholds
    FAIL_RATE_THRESHOLD = 0.4
    REQ_PER_IP_THRESHOLD = 30
    REQ_PER_IP_NORM_DIV = 300

    def __init__(self, z_threshold: float = 2.5, ema_dev_threshold: float = 0.4, spike_threshold: float = 15.0):
        self.z_threshold = z_threshold
        self.ema_dev_threshold = ema_dev_threshold
        self.spike_threshold = spike_threshold

    def score(self, features: Dict[str, float], rps_history: List[float]) -> Tuple[float, List[str]]:
        reasons = []
        score_components = []

        # Z-score on RPS
        z_norm = 0.0

        if len(rps_history) >= 5:
            hist = np.array(rps_history)
            mean_rps, std_rps = np.mean(hist), np.std(hist)
            if std_rps > 0:
                z = abs((features["rps"] - mean_rps) / std_rps)
                z_norm = min(z / (self.z_threshold * self.Z_NORM_SCALE), 1.0)
                if z > self.z_threshold:
                    reasons.append(f"Z-score anomaly: {z:.2f}σ on RPS")

        score_components.append(z_norm)

        # EMA deviation
        ema_norm = 0.0
        ema = features["ema_rps"]
        rps = features["rps"]

        if ema > 0:
            ema_dev = abs(rps - ema) / (ema + self.EPS)
            ema_norm = min(ema_dev / (self.ema_dev_threshold * self.EMA_NORM_SCALE), 1.0)
            if ema_dev > self.ema_dev_threshold:
                reasons.append(f"EMA deviation: {ema_dev:.2%} above EMA")

        score_components.append(ema_norm)

        # Spike detection
        spike_norm = 0.0
        spike = features["spike"]

        if abs(spike) > self.spike_threshold:
            spike_norm = min(abs(spike) / (self.spike_threshold * self.SPIKE_NORM_SCALE), 1.0)
            reasons.append(f"Traffic spike: +{spike:.1f} RPS")

        score_components.append(spike_norm)

        # High fail rate
        fail_norm = 0.0
        fail_rate = features["fail_rate"]

        if fail_rate > self.FAIL_RATE_THRESHOLD:
            fail_norm = min(fail_rate, 1.0)
            reasons.append(f"High fail rate: {fail_rate:.1%}")

        score_components.append(fail_norm)

        # IP concentration
        conc_norm = 0.0
        req_per_ip = features["req_per_ip"]

        if req_per_ip > self.REQ_PER_IP_THRESHOLD:
            conc_norm = min(req_per_ip / self.REQ_PER_IP_NORM_DIV, 1.0)
            reasons.append(f"IP concentration: {req_per_ip:.1f} req/IP")

        score_components.append(conc_norm)

        anomaly_score = float(np.max(score_components)) if score_components else 0.0
        return round(anomaly_score, 4), reasons