import random
from datetime import datetime, timezone
from typing import List, Dict

# Traffic Generator
ENDPOINTS = ["/api/login", "/api/data", "/api/upload", "/api/admin", "/health", "/api/users", "/api/search", "/static/js/app.js", "/api/logout", "/api/reset-password", "/api/token"]
METHODS      = ["GET", "POST", "PUT", "DELETE"]
NORMAL_IPS   = [f"192.168.{random.randint(1,5)}.{random.randint(1,254)}" for _ in range(40)]
ATTACKER_IPS = [f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}" for _ in range(8)]

def generate_log_entry(attack_type: str = "normal", attacker_ip: str = None) -> Dict:
    ts = datetime.now(timezone.utc).isoformat()
    if attack_type == "normal":
        ip     = random.choice(NORMAL_IPS)
        method = random.choices(METHODS, weights=[50, 30, 10, 10])[0]
        endpoint = random.choice(ENDPOINTS)
        status = random.choices([200, 201, 204, 301, 304, 400, 401, 403, 404, 500], weights=[55, 5, 5, 5, 5, 5, 5, 3, 7, 5])[0]
    elif attack_type == "ddos":
        ip       = attacker_ip or random.choice(ATTACKER_IPS)
        method   = "GET"
        endpoint = random.choice(["/api/data", "/health", "/api/search"])
        status   = random.choices([200, 503, 429], weights=[40, 30, 30])[0]
    elif attack_type == "bruteforce":
        ip       = attacker_ip or random.choice(ATTACKER_IPS[:3])
        method   = "POST"
        endpoint = "/api/login"
        status   = random.choices([401, 403, 200], weights=[70, 25, 5])[0]
    elif attack_type == "spike":
        ip       = random.choice(NORMAL_IPS + ATTACKER_IPS)
        method   = random.choice(METHODS)
        endpoint = random.choice(ENDPOINTS)
        status   = random.choices([200, 400, 500], weights=[60, 20, 20])[0]
    else:
        ip = random.choice(NORMAL_IPS)
        method, endpoint, status = "GET", "/api/data", 200

    return {
        "timestamp":   ts,
        "ip":          ip,
        "method":      method,
        "endpoint":    endpoint,
        "status_code": status,
        "bytes":       random.randint(100, 8192),
        "response_ms": random.randint(5, 2000),
    }

def generate_window_logs(scenario: str = "normal", count: int = None) -> List[Dict]:
    if scenario == "normal":
        n = count or random.randint(15, 60)
        logs = [generate_log_entry("normal") for _ in range(n)]

    elif scenario == "ddos":
        n        = count or random.randint(300, 800)
        attacker = random.choice(ATTACKER_IPS)
        logs     = [generate_log_entry("ddos", attacker_ip=attacker) for _ in range(n)]
        logs    += [generate_log_entry("normal") for _ in range(random.randint(5, 15))]

    elif scenario == "bruteforce":
        n        = count or random.randint(50, 150)
        attacker = random.choice(ATTACKER_IPS[:3])
        logs     = [generate_log_entry("bruteforce", attacker_ip=attacker) for _ in range(n)]
        logs    += [generate_log_entry("normal") for _ in range(random.randint(10, 25))]

    elif scenario == "spike":
        import datetime as _dt
        n    = count or random.randint(120, 250)
        logs = []
        base = _dt.datetime.now(_dt.timezone.utc)
        for i in range(n):
            # Compress all spike logs into a 200ms window — real burst behaviour
            ts = (base + _dt.timedelta(milliseconds=i * (200 / n))).isoformat() + "Z"
            entry = generate_log_entry("spike")
            entry["timestamp"] = ts
            logs.append(entry)

    else:
        logs = [generate_log_entry("normal") for _ in range(20)]
    
    random.shuffle(logs)
    return logs

# Dashboard (in-memory metrics collector)
class Dashboard:
    def __init__(self, output_path: str = "dashboard.html"):
        self.output_path  = output_path
        self.rps_history  : List[float] = []
        self.risk_history : List[float] = []
        self.predictions  : List[str]   = []
        self.timestamps   : List[str]   = []
        self.alerts       : List[Dict]  = []
        self.blocked      : Dict        = {}
        self.flagged      : Dict        = {}
        self.shap_vals    : Dict        = {}
        self.features     : Dict        = {}
        self.xgb_metrics  : Dict        = {}
        self.lstm_metrics : Dict        = {}

    def update(self, rps: float, risk: float, cls: str, ts: str, alerts: list, blocked: dict, flagged: dict, shap: dict, features: dict):
        self.rps_history.append(rps)
        self.risk_history.append(risk)
        self.predictions.append(cls)
        self.timestamps.append(ts)
        self.alerts  = alerts
        self.blocked = blocked
        self.flagged = flagged
        self.shap_vals = shap
        self.features  = features

    def render(self):
        pass