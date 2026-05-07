import os
from dotenv import load_dotenv

load_dotenv()

# Helper functions for safe parsing
def get_float(key, default):
    try:
        return float(os.getenv(key, default))
    except (TypeError, ValueError):
        return default

def get_int(key, default):
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default

# Window & sequence settings
WINDOW_SEC      = 5
MIN_WINDOW_SEC  = 0.05
BATCH_SIZE      = 50
HISTORY_LEN     = 60
LSTM_SEQ_LEN    = 10
EMA_ALPHA       = 0.3
ALERT_COOLDOWN  = 15

# Risk thresholds
RISK_MONITOR    = 0.0
RISK_RATELIMIT  = get_float("RISK_RATELIMIT", 0.60)
RISK_APPROVAL   = get_float("RISK_APPROVAL", 0.85)
RISK_AUTOBLOCK  = get_float("RISK_AUTOBLOCK", 0.95)

# Feature names
FEATURE_NAMES = ["rps", "total_requests", "unique_ips", "req_per_ip", "fail_rate", "max_hits_ip", "spike",
    "rolling_mean_rps", "rolling_std_rps", "ema_rps", "endpoint_concentration", "auth_fail_rate"
]

# API & security settings
INGEST_API_KEY = os.getenv("INGEST_API_KEY") or "dev-key"
BLOCK_TTL_MINUTES = get_int("BLOCK_TTL_MINUTES", 30)