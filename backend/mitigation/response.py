import threading
from datetime import datetime, timezone
from typing import Dict, List
from collections import Counter
from config import RISK_AUTOBLOCK, RISK_APPROVAL, RISK_RATELIMIT

class ResponseEngine:
    def __init__(self):
        self.blocked_ips: Dict[str, Dict] = {}
        self.rate_limited_ips: Dict[str, Dict] = {}
        self.monitored_ips: Dict[str, Dict] = {}
        self.action_log: List[Dict] = []
        self.pending_approvals: List[Dict] = []
        self._lock = threading.Lock()

    def _record(self, ip: str, action: str, risk: float, reason: str):
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "ip": ip, "action": action, "risk": risk, "reason": reason}
        self.action_log.append(entry)
        return entry

    def respond(self, risk: float, features: Dict[str, float], logs: List[Dict], human_loop: bool = False) -> List[Dict]:
        ip_counts = Counter(log["ip"] for log in logs)
        top_ips = ip_counts.most_common(5)
        actions_taken = []

        with self._lock:

            # High risk → auto block
            if risk >= RISK_AUTOBLOCK:
                for ip, _ in top_ips:
                    if ip not in self.blocked_ips:
                        self.blocked_ips[ip] = {"risk": risk, "since": datetime.now(timezone.utc).isoformat(), "reason": f"Auto-block: risk >= {RISK_AUTOBLOCK}"}
                        actions_taken.append(self._record(ip, "AUTO_BLOCK", risk, f"Risk ≥ {RISK_AUTOBLOCK}"))
                        self.rate_limited_ips.pop(ip, None)
                        self.monitored_ips.pop(ip, None)

            # Medium risk → admin approval required
            elif risk >= RISK_APPROVAL:
                for ip, cnt in top_ips[:2]:
                    if ip not in self.blocked_ips and not any(p["ip"] == ip for p in self.pending_approvals):
                        self.pending_approvals.append({"ip": ip, "risk": risk, "count": cnt, 
                            "timestamp": datetime.now(timezone.utc).isoformat(), "reason": f"Risk {risk:.3f} — awaiting admin decision"})
                        actions_taken.append(self._record(ip, "PENDING_ADMIN", risk, f"Risk {risk:.3f} requires admin approval"))

            # Low-medium risk → rate limit
            elif risk >= RISK_RATELIMIT:
                for ip, _ in top_ips[:3]:
                    if ip not in self.blocked_ips and ip not in self.rate_limited_ips:
                        self.rate_limited_ips[ip] = {"risk": risk, "since": datetime.now(timezone.utc).isoformat(), "limit": "100req/min"}
                        actions_taken.append(self._record(ip, "RATE_LIMIT", risk, f"Risk ≥ {RISK_RATELIMIT}"))

            # Low risk → monitor only
            else:
                for ip, cnt in top_ips[:3]:
                    if ip not in self.blocked_ips and ip not in self.rate_limited_ips:
                        self.monitored_ips[ip] = {"risk": risk, "count": cnt, "since": datetime.now(timezone.utc).isoformat()}

        return actions_taken

    # Admin/manual override block
    def manual_block(self, ip: str, reason: str = "Manual block"):
        with self._lock:
            self.blocked_ips[ip] = {"risk": 1.0, "since": datetime.now(timezone.utc).isoformat(), "reason": reason}
            self._record(ip, "MANUAL_BLOCK", 1.0, reason)

    # Remove IP from all restriction lists
    def unblock(self, ip: str):
        with self._lock:
            self.blocked_ips.pop(ip, None)
            self.rate_limited_ips.pop(ip, None)

    # Admin approves → move to blocked
    def approve_block(self, ip: str) -> bool:
        with self._lock:
            self.pending_approvals = [p for p in self.pending_approvals if p["ip"] != ip]
            self.blocked_ips[ip] = {"risk":   1.0, "since": datetime.now(timezone.utc).isoformat(), "reason": "Admin approved block"}
            self._record(ip, "ADMIN_APPROVED_BLOCK", 1.0, "Admin approved")
            self.rate_limited_ips.pop(ip, None)
            return True

    # Admin rejects → keep monitoring
    def reject_block(self, ip: str) -> bool:
        with self._lock:
            self.pending_approvals = [p for p in self.pending_approvals if p["ip"] != ip]
            self._record(ip, "ADMIN_REJECTED_BLOCK", 0.0, "Admin rejected")
            return True

    # Return pending approval list
    def get_pending(self) -> List[Dict]:
        with self._lock:
            return list(self.pending_approvals)