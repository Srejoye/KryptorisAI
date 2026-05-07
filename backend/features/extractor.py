import numpy as np
from collections import Counter, deque
from datetime import datetime, timezone
from typing import List, Dict, Optional
from config import WINDOW_SEC, EMA_ALPHA, HISTORY_LEN, FEATURE_NAMES, MIN_WINDOW_SEC

# Parse ISO timestamp → epoch seconds
def _parse_ts(ts_str: str) -> Optional[float]:
    try:
        return datetime.fromisoformat(ts_str.rstrip("Z")).replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return None

# Compute actual elapsed time (fallback to window if needed)
def _elapsed_seconds(logs: List[Dict], fallback: float = WINDOW_SEC) -> float:
    ts_values = []
    for log in logs:
        raw = log.get("timestamp")
        if raw:
            epoch = _parse_ts(raw)
            if epoch is not None:
                ts_values.append(epoch)

    if len(ts_values) >= 2:
        elapsed = max(ts_values) - min(ts_values)
        if elapsed > MIN_WINDOW_SEC:
            return elapsed

    return max(fallback, MIN_WINDOW_SEC)

class FeatureExtractor:
    def __init__(self, history_len: int = HISTORY_LEN, ema_alpha: float = EMA_ALPHA):
        self.history_len = history_len
        self.ema_alpha = ema_alpha
        self.rps_history = deque(maxlen=history_len)
        self.previous_rps = 0.0
        self.ema_rps = 0.0
        self._initialized = False

    def extract(self, logs: List[Dict], window_wall_sec: Optional[float] = None) -> Dict[str, float]:
        if not logs:
            return self._zero_features()

        total_requests = len(logs)

        # Elapsed time → RPS
        fallback = window_wall_sec if window_wall_sec is not None else WINDOW_SEC
        elapsed  = _elapsed_seconds(logs, fallback=fallback)
        rps      = total_requests / elapsed

        # IP distribution
        ip_counts: Dict[str, int] = Counter(log["ip"] for log in logs)
        unique_ips  = len(ip_counts)
        req_per_ip  = total_requests / unique_ips if unique_ips > 0 else 0.0
        max_hits_ip = max(ip_counts.values()) if ip_counts else 0

        # Error rate
        failed    = sum(1 for log in logs if log["status_code"] >= 400)
        fail_rate = failed / total_requests if total_requests > 0 else 0.0

        # Endpoint concentration + auth failures (bruteforce signals)
        endpoint_counts    = Counter(log.get("endpoint", "") for log in logs)
        top_endpoint_ratio = max(endpoint_counts.values()) / total_requests if total_requests > 0 else 0.0

        auth_failures  = sum(1 for log in logs if log.get("status_code") in (401, 403))
        auth_fail_rate = auth_failures / total_requests if total_requests > 0 else 0.0

        # Change vs previous window
        spike = rps - self.previous_rps

        # Exponential moving average
        if not self._initialized:
            self.ema_rps = rps
            self._initialized = True
        else:
            self.ema_rps = self.ema_alpha * rps + (1 - self.ema_alpha) * self.ema_rps

        # Rolling stats
        self.rps_history.append(rps)
        hist_arr         = np.array(self.rps_history)
        rolling_mean_rps = float(np.mean(hist_arr))
        rolling_std_rps  = float(np.std(hist_arr)) if len(hist_arr) > 1 else 0.0

        self.previous_rps = rps

        return {
            "rps":              round(rps, 4),
            "total_requests":   float(total_requests),
            "unique_ips":       float(unique_ips),
            "req_per_ip":       round(req_per_ip, 4),
            "fail_rate":        round(fail_rate, 4),
            "max_hits_ip":      float(max_hits_ip),
            "spike":            round(spike, 4),
            "rolling_mean_rps": round(rolling_mean_rps, 4),
            "rolling_std_rps":  round(rolling_std_rps, 4),
            "ema_rps":          round(self.ema_rps, 4),
            "_elapsed_sec":     round(elapsed, 4),
            "endpoint_concentration": round(top_endpoint_ratio, 4),
            "auth_fail_rate":         round(auth_fail_rate, 4),
        }

    def _zero_features(self) -> Dict[str, float]:
        return {f: 0.0 for f in FEATURE_NAMES}

    def get_rps_history(self) -> List[float]:
        return list(self.rps_history)