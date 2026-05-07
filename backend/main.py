#!/usr/bin/env python3
import os
import time
from datetime import datetime, timezone, timedelta
import threading
import numpy as np
from utils import generate_window_logs
from inference.engine import CyberDetectionPipeline
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()
 
app = Flask(__name__)
CORS(app)

INGEST_API_KEY = os.getenv("INGEST_API_KEY", "dev-key")
BLOCK_TTL_MINUTES = int(os.getenv("BLOCK_TTL_MINUTES", 30))
WINDOW_SIZE = 10

lock = threading.Lock()
pipeline = None

state = {
    "window": 0,
    "timestamp": "",
    "scenario": "normal",
    "risk": 0.0,
    "class": "Normal",
    "xgb_prob": 0.0,
    "lstm_prob": 0.0,
    "anomaly_score": 0.0,
    "features": {},
    "shap": {},
    "alert": None,
    "actions": [],
    "anomaly_reasons": [],
    "ready": False,
}

history = {"rps": [], "risk": [], "ts": []}
alerts_log = []
current_scenario = ["normal"]

ingest_buffer = []
ingest_lock = threading.Lock()

blocklist = {}
blocklist_lock = threading.Lock()

def _safe(obj):
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj

def _check_api_key():
    key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    return key and key == INGEST_API_KEY

def _add_to_blocklist(ip, risk, reason):
    expires = (datetime.now(timezone.utc) + timedelta(minutes=BLOCK_TTL_MINUTES)).isoformat()
    with blocklist_lock:
        blocklist[ip] = {"risk": round(risk, 4), "reason": reason, "blocked_at": datetime.now(timezone.utc).isoformat(), "expires_at": expires,}

def _clean_expired_blocks():
    now = datetime.now(timezone.utc).isoformat()
    with blocklist_lock:
        expired = [ip for ip, info in blocklist.items() if info.get("expires_at") and info["expires_at"] < now]
        for ip in expired:
            del blocklist[ip]

def _process_window(logs: list, scenario: str, wall_sec: float = None):
    global pipeline

    result = pipeline.process_window(logs, scenario, wall_sec=wall_sec)
    safe_result = _safe(result)

    with lock:
        state.update(safe_result)
        state["ready"] = True

        history["rps"].append(safe_result["features"].get("rps", 0))
        history["risk"].append(safe_result["risk"])
        history["ts"].append(safe_result["timestamp"])

        for key in ("rps", "risk", "ts"):
            if len(history[key]) > 60:
                history[key] = history[key][-60:]

        if safe_result.get("alert"):
            alerts_log.append(safe_result["alert"])

    for action in safe_result.get("actions", []):
        if action["action"] == "AUTO_BLOCK":
            _add_to_blocklist(ip=action["ip"], risk=safe_result["risk"], reason="Auto-block: risk >= 0.95")

        elif action["action"] == "PENDING_ADMIN":
            pass

        elif action["action"] == "RATE_LIMIT":
            with blocklist_lock:
                if "_rate_limited" not in blocklist:
                    blocklist["_rate_limited"] = {}

                blocklist["_rate_limited"][action["ip"]] = {"risk": round(safe_result["risk"], 4), "since": action["timestamp"], "limit": "100req/min"}

def _fallback_loop():
    while True:
        try:
            with ingest_lock:
                has_real_logs = len(ingest_buffer) > 0

            if has_real_logs:
                time.sleep(0.5)
                continue

            logs = generate_window_logs(current_scenario[0])
            _process_window(logs, current_scenario[0])
            time.sleep(0.5)

        except Exception as e:
            print(f"[fallback_loop] Error: {e}")
            time.sleep(1)

def _ingest_processor():
    while True:
        try:
            with ingest_lock:
                if len(ingest_buffer) >= WINDOW_SIZE:
                    slots = ingest_buffer[:WINDOW_SIZE]
                    del ingest_buffer[:WINDOW_SIZE]
                else:
                    slots = None

            if slots:
                logs = [s["log"] for s in slots]
                t0, t1 = slots[0]["arrived_at"], slots[-1]["arrived_at"]
                wall_sec = max(t1 - t0, 0.05)

                _clean_expired_blocks()
                _process_window(logs, current_scenario[0], wall_sec=wall_sec)
            else:
                time.sleep(0.5)

        except Exception as e:
            print(f"[ingest_processor] Error: {e}")
            time.sleep(1)

def startup():
    global pipeline

    print("[KryptorisAI] Training models — please wait...")
    pipeline = CyberDetectionPipeline()
    pipeline.train()
    print("[KryptorisAI] Training complete. Server ready.")

    with lock:
        state["ready"] = True

    threading.Thread(target=_ingest_processor, daemon=True).start()
    threading.Thread(target=_fallback_loop, daemon=True).start()

@app.route("/api/ingest", methods=["POST"])
def api_ingest():
    if not _check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "no data"}), 400

    logs = data if isinstance(data, list) else [data]

    required = {"ip", "method", "endpoint", "status_code"}
    valid = []

    for log in logs:
        if required.issubset(log.keys()):
            valid.append({
                "ip": log["ip"],
                "method": log["method"],
                "endpoint": log["endpoint"],
                "status_code": int(log["status_code"]),
                "bytes": int(log.get("bytes", 0)),
                "response_ms": int(log.get("response_ms", 0)),
                "timestamp": log.get("timestamp", datetime.now(timezone.utc).isoformat())
            })

    if not valid:
        return jsonify({"error": "no valid log entries"}), 400

    arrived_at = time.monotonic()
    stamped = [{"log": v, "arrived_at": arrived_at} for v in valid]

    with ingest_lock:
        ingest_buffer.extend(stamped)

    return jsonify({"accepted": len(valid), "buffered": len(ingest_buffer), "window_size": WINDOW_SIZE}), 202

@app.route("/api/blocklist", methods=["GET"])
def api_blocklist():
    _clean_expired_blocks()
    with blocklist_lock:
        return jsonify(_safe(blocklist))
    
@app.route("/api/state")
def api_state():
    with lock:
        return jsonify(_safe(state))

@app.route("/api/data")
def api_data():
    with lock:
        return jsonify(_safe(history))

@app.route("/api/alerts")
def api_alerts():
    with lock:
        return jsonify(_safe(list(reversed(alerts_log[-20:]))))

@app.route("/api/blocked-ips")
def api_blocked():
    _clean_expired_blocks()

    combined = {}
    with blocklist_lock:
        combined.update(blocklist)

    if pipeline:
        with lock:
            for ip, info in pipeline.response_engine.blocked_ips.items():
                if ip not in combined:
                    combined[ip] = info
            rate_limited = dict(pipeline.response_engine.rate_limited_ips)
    else:
        rate_limited = {}

    return jsonify(_safe({"blocked": combined, "rate_limited": rate_limited}))
 
# Trigger external scenario (used by control panel)
@app.route("/api/trigger-attack", methods=["POST"])
def api_trigger():
    api_key = request.headers.get("x-api-key")
    expected_key = INGEST_API_KEY
    if not expected_key or api_key != expected_key:
        return jsonify({"error": "unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    attack = data.get("type", "normal")

    if attack not in ("normal", "ddos", "bruteforce", "spike"):
        return jsonify({"error": "unknown type"}), 400

    current_scenario[0] = attack

    with ingest_lock:
        ingest_buffer.clear()

    if pipeline:
        fe = pipeline.feature_extractor
        fe.rps_history.clear()
        fe.previous_rps = 0.0
        fe.ema_rps = 0.0
        fe._initialized = False
        pipeline.sequence_buffer.clear()

    return jsonify({"ok": True, "scenario": attack})

@app.route("/api/unblock/<ip>", methods=["POST"])
def api_unblock(ip):
    with blocklist_lock:
        blocklist.pop(ip, None)

    if pipeline:
        with lock:
            pipeline.response_engine.blocked_ips.pop(ip, None)
            pipeline.response_engine.rate_limited_ips.pop(ip, None)

    return jsonify({"ok": True, "ip": ip})

@app.route("/api/pending-approvals", methods=["GET"])
def api_pending_approvals():
    if pipeline is None:
        return jsonify([])
    return jsonify(_safe(pipeline.response_engine.get_pending()))

@app.route("/api/approve-block/<ip>", methods=["POST"])
def api_approve_block(ip):
    if pipeline is None:
        return jsonify({"error": "pipeline not ready"}), 503

    pipeline.response_engine.approve_block(ip)
    _add_to_blocklist(ip, risk=1.0, reason="Admin approved block")

    return jsonify({"ok": True, "ip": ip, "action": "blocked"})

@app.route("/api/reject-block/<ip>", methods=["POST"])
def api_reject_block(ip):
    if pipeline is None:
        return jsonify({"error": "pipeline not ready"}), 503
    
    pipeline.response_engine.reject_block(ip)
    return jsonify({"ok": True, "ip": ip, "action": "rejected"})

@app.route("/api/manual-block/<ip>", methods=["POST"])
def api_manual_block(ip):
    _add_to_blocklist(ip, risk=1.0, reason="Manual block")
    return jsonify({"ok": True, "ip": ip})

@app.route("/api/status")
def api_status():
    with ingest_lock:
        buffered = len(ingest_buffer)

    return jsonify({"ready": state["ready"], "buffered": buffered, "window_size": WINDOW_SIZE})

@app.route("/")
def dashboard():
    return send_from_directory(os.path.join(os.path.dirname(__file__), "..", "frontend"), "index.html")

@app.route("/<path:filename>")
def dashboard_static(filename):
    return send_from_directory(os.path.join(os.path.dirname(__file__), "..", "frontend"), filename)

def run_server():
    threading.Thread(target=startup, daemon=True).start()
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", 5000)), debug=False)

if __name__ == "__main__":
    run_server()