import time
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional
from config import ALERT_COOLDOWN, RISK_AUTOBLOCK, RISK_APPROVAL, RISK_RATELIMIT

# Thresholds for rule-based triggers
SPIKE_THRESHOLD = 20
FAIL_RATE_THRESHOLD = 0.5
REQ_PER_IP_THRESHOLD = 50

class AlertSystem:
    def __init__(self, cooldown: int = ALERT_COOLDOWN):
        self.cooldown = cooldown
        self.last_alert: Dict[str, float] = {}  # last alert time per key (IP/global)
        self.alert_log: List[Dict] = []

    def _severity(self, risk: float) -> str:
        if risk >= RISK_AUTOBLOCK:
            return "CRITICAL"
        elif risk >= RISK_APPROVAL:
            return "HIGH"
        elif risk >= RISK_RATELIMIT:
            return "WARNING"
        return "LOW"

    def evaluate(self, risk: float, features: Dict[str, float], anomaly_reasons: List[str], logs: List[Dict],) -> Optional[Dict]:
        now = time.time()

        # Identify most active IPs
        ip_counts = Counter(log["ip"] for log in logs)
        top_ips = ip_counts.most_common(3)

        trigger = False
        trigger_reasons = list(anomaly_reasons)

        # Extract feature values once
        spike = features.get("spike", 0)
        fail_rate = features.get("fail_rate", 0)
        req_per_ip = features.get("req_per_ip", 0)

        # Rule-based trigger checks
        rules = [
            (risk >= RISK_RATELIMIT, f"Risk score {risk:.3f} exceeds threshold {RISK_RATELIMIT}"),
            (spike > SPIKE_THRESHOLD, f"Spike: {spike:.1f} RPS"),
            (fail_rate > FAIL_RATE_THRESHOLD, f"Fail rate: {fail_rate:.1%}"),
            (req_per_ip > REQ_PER_IP_THRESHOLD, f"Req/IP: {req_per_ip:.1f}")
        ]

        for condition, message in rules:
            if condition:
                trigger = True
                trigger_reasons.append(message)

        if not trigger:
            return None

        # Cooldown check per top IP (fallback: global)
        key = str(top_ips[0][0]) if top_ips else "global"
        if key in self.last_alert and (now - self.last_alert[key]) < self.cooldown:
            return None

        self.last_alert[key] = now
        severity = self._severity(risk)

        alert = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": severity,
            "risk_score": risk,
            "reasons": trigger_reasons,
            "top_ips": top_ips,
            "features_snapshot": {k: round(v, 4) for k, v in features.items()}
        }

        self.alert_log.append(alert)
        return alert