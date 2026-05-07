import os
import time
import torch
import joblib
import numpy as np
from collections import Counter, deque
from datetime import datetime, timezone
from typing import List, Dict, Deque
from config import WINDOW_SEC, FEATURE_NAMES, LSTM_SEQ_LEN
from features.extractor import FeatureExtractor
from models.xgb_model import XGBModel
from models.lstm_model import LSTMModel
from models.stats_model import StatisticalAnomalyDetector
from models.fusion import FusionEngine
from alert.alert_system import AlertSystem
from mitigation.response import ResponseEngine
from evaluation.metrics import train_and_evaluate
from utils import generate_window_logs, Dashboard

# Directory to store trained models and Model file paths
SAVE_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "saved")
XGB_PATH  = os.path.join(SAVE_DIR, "xgb.pkl")
LSTM_PATH = os.path.join(SAVE_DIR, "lstm.pt")

class CyberDetectionPipeline:
    def __init__(self):
        self.feature_extractor = FeatureExtractor()
        self.xgb_model = XGBModel()
        self.lstm_model = LSTMModel()
        self.stat_detector = StatisticalAnomalyDetector()
        self.fusion = FusionEngine()
        self.alert_system = AlertSystem()
        self.response_engine = ResponseEngine()
        self.dashboard = Dashboard()
        self.sequence_buffer: Deque[np.ndarray] = deque(maxlen=LSTM_SEQ_LEN * 2)
        self._running = False
        self.window_count = 0
 
    def train(self):
        os.makedirs(SAVE_DIR, exist_ok=True)

        # Load existing models if available
        if os.path.exists(XGB_PATH) and os.path.exists(LSTM_PATH):
            print("[KryptorisAI] Saved models found — loading instead of retraining...")

            saved = joblib.load(XGB_PATH)
            self.xgb_model.model = saved["model"]
            self.xgb_model.scaler = saved["scaler"]
            self.xgb_model._explainer = saved["explainer"]
            self.xgb_model.trained = True

            self.lstm_model.net.load_state_dict(torch.load(LSTM_PATH, map_location="cpu"))
            self.lstm_model.net.eval()
            self.lstm_model.trained  = True

            # Empty metrics (since not retraining)
            metrics = {"xgb": {}, "lstm": {}}
            self.dashboard.xgb_metrics  = metrics["xgb"]
            self.dashboard.lstm_metrics = metrics["lstm"]

            print("[KryptorisAI] Models loaded. Server ready.")
            return metrics

        # Train models if not available
        metrics = train_and_evaluate(self.xgb_model, self.lstm_model)
        self.dashboard.xgb_metrics = metrics["xgb"]
        self.dashboard.lstm_metrics = metrics["lstm"]

        # Save trained models
        joblib.dump({"model": self.xgb_model.model, "scaler": self.xgb_model.scaler, "explainer": self.xgb_model._explainer}, XGB_PATH)
        torch.save(self.lstm_model.net.state_dict(), LSTM_PATH)
        print(f"[KryptorisAI] Models saved to {SAVE_DIR}")
        return metrics

    def process_window(self, logs: List[Dict], scenario: str = "unknown", wall_sec: float = None) -> Dict:
        self.window_count += 1
        ts = datetime.now(timezone.utc).isoformat()

        # Extract features → vector
        features = self.feature_extractor.extract(logs, window_wall_sec=wall_sec)
        fvec = np.array([features[f] for f in FEATURE_NAMES], dtype=np.float32)

        # XGBoost prediction
        self.sequence_buffer.append(fvec)
        xgb_prob = self.xgb_model.predict_proba(fvec)

        # LSTM prediction (requires sequence buffer)
        if len(self.sequence_buffer) < LSTM_SEQ_LEN:
            lstm_prob = 0.5
        else:
            seq = np.array(list(self.sequence_buffer)[-LSTM_SEQ_LEN:], dtype=np.float32)
            lstm_prob = self.lstm_model.predict_proba(seq)

        # Statistical anomaly detection
        rps_hist = self.feature_extractor.get_rps_history()
        anomaly_score, anomaly_reasons = self.stat_detector.score(features, rps_hist)

        # Fusion → final risk + class
        risk, cls = self.fusion.fuse(xgb_prob, lstm_prob, anomaly_score)

        # Explainability (SHAP)
        shap_vals = self.xgb_model.shap_explain(fvec)

        # Alert + response
        alert = self.alert_system.evaluate(risk, features, anomaly_reasons, logs)
        actions = self.response_engine.respond(risk, features, logs, human_loop=False)

        # Dashboard update
        self.dashboard.update(rps=features["rps"], risk=risk, cls=cls, ts=ts, alerts=self.alert_system.alert_log, blocked=self.response_engine.blocked_ips,
            flagged=self.response_engine.rate_limited_ips, shap=shap_vals, features=features
        )

        return {
            "window": self.window_count,
            "timestamp": ts,
            "scenario": scenario,
            "features": features,
            "xgb_prob": round(xgb_prob, 4),
            "lstm_prob": round(lstm_prob, 4),
            "anomaly_score": round(anomaly_score, 4),
            "risk": risk,
            "class": cls,
            "shap": shap_vals,
            "alert": alert,
            "actions": actions,
            "anomaly_reasons": anomaly_reasons
        }
        
    def _print_result(self, result: Dict):
        CLS_EMOJI = {"Normal": "✅", "Suspicious": "⚠️ ", "Attack": "🚨"}
        SEV_COLOR = {"Normal": "\033[92m", "Suspicious": "\033[93m", "Attack": "\033[91m"}
        RESET = "\033[0m"

        cls = result["class"]
        color = SEV_COLOR.get(cls, "")
        emoji = CLS_EMOJI.get(cls, "")

        print(f"\n{'─'*65}")
        print(f" Window #{result['window']:03d}  [{result['timestamp'][-9:-1]}]  Scenario: {result['scenario'].upper()}")
        print(f"{'─'*65}")
        print(f" {emoji} {color}CLASS: {cls:12s}{RESET}  RISK: {color}{result['risk']:.4f}{RESET}")
        print(f" XGB_prob: {result['xgb_prob']:.4f}  LSTM_prob: {result['lstm_prob']:.4f}  Anomaly: {result['anomaly_score']:.4f}")
        
        f = result["features"]

        # Key traffic metrics
        print(f" RPS:{f['rps']:7.1f}  ReqPerIP:{f['req_per_ip']:6.1f}  FailRate:{f['fail_rate']:.2%}  Spike:{f['spike']:+.1f}")
        print(f" UniqueIPs:{f['unique_ips']:.0f}  MaxHitsIP:{f['max_hits_ip']:.0f}  EMA_RPS:{f['ema_rps']:.2f}")

        # Anomaly reasons
        if result["anomaly_reasons"]:
            print(f" 🔔 Anomalies: {'; '.join(result['anomaly_reasons'][:3])}")

        # Alert summary
        if result["alert"]:
            a = result["alert"]
            print(f" 🚨 ALERT [{a['severity']}]: {'; '.join(a['reasons'][:2])}")

        # Actions taken
        if result["actions"]:
            for act in result["actions"]:
                print(f" 🔒 ACTION: {act['action']} → {act['ip']}")

        # Top SHAP features
        top_shap = sorted(result["shap"].items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        print(f" 🔍 Top SHAP: " + "  ".join(f"{k}={v:+.4f}" for k, v in top_shap))

    def run(self, n_windows: int = 30, render_interval: int = 5):
        """Run real-time detection loop for testing."""
        print("\n" + "═" * 65)
        print("  REAL-TIME DETECTION LOOP STARTED")
        print(f"  Window: {WINDOW_SEC}s | Cycles: {n_windows}")
        print("═" * 65)

        self._running = True
        scenario = "normal"

        for i in range(n_windows):
            if not self._running:
                break

            # Generate logs → process → print
            logs = generate_window_logs(scenario)
            result = self.process_window(logs, scenario)
            self._print_result(result)

            # Periodic dashboard rendering
            if (i + 1) % render_interval == 0 or i == n_windows - 1:
                try:
                    self.dashboard.render()
                except Exception as e:
                    print(f"  [Dashboard render error: {e}]")

            time.sleep(WINDOW_SEC)
        self._running = False

        # Final summary
        print("\n" + "═" * 65)
        print("  DETECTION LOOP COMPLETE")
        print(f"  Total windows processed: {self.window_count}")
        print(f"  Total alerts generated:  {len(self.alert_system.alert_log)}")
        print(f"  Blocked IPs:             {len(self.response_engine.blocked_ips)}")
        print(f"  Rate-limited IPs:        {len(self.response_engine.rate_limited_ips)}")
        print("═" * 65)

    def print_final_report(self):
        """Print final aggregated security report."""
        print("\n" + "═" * 65)
        print("  FINAL SECURITY REPORT")
        print("═" * 65)

        print("\n  📋 ALERT SUMMARY:")
        severity_counts = Counter(a["severity"] for a in self.alert_system.alert_log) 
        for sev, cnt in sorted(severity_counts.items()):
            print(f"    {sev}: {cnt}")

        print("\n  🔒 BLOCKED IPs:")
        if self.response_engine.blocked_ips:
            for ip, info in self.response_engine.blocked_ips.items():
                print(f"    {ip}  risk={info['risk']:.3f}  reason={info['reason']}")
        else:
            print("    None")

        print("\n  ⏱  RATE-LIMITED IPs:")
        if self.response_engine.rate_limited_ips:
            for ip, info in self.response_engine.rate_limited_ips.items():
                print(f"    {ip}  risk={info['risk']:.3f}")
        else:
            print("    None")

        print("\n  📈 RISK STATISTICS:")
        if self.dashboard.risk_history:
            arr = np.array(self.dashboard.risk_history)
            print(f"    Mean Risk:  {np.mean(arr):.4f}")
            print(f"    Max Risk:   {np.max(arr):.4f}")
            print(f"    Std Risk:   {np.std(arr):.4f}")

            counts = Counter(self.dashboard.predictions) 
            for cls, cnt in sorted(counts.items()):
                print(f"    {cls}: {cnt} windows")

        print("\n  🔍 TOP SHAP FEATURES (last window):")
        if self.dashboard.shap_vals:
            for feat, val in sorted(self.dashboard.shap_vals.items(), key=lambda x: abs(x[1]), reverse=True):
                bar = "█" * int(abs(val) * 200)
                sign = "+" if val >= 0 else "-"
                print(f"    {feat:20s}  {sign}{abs(val):.5f}  {bar[:30]}")

        print("\n  ✅ Model Metrics (XGBoost):")
        if self.dashboard.xgb_metrics:
            for k, v in self.dashboard.xgb_metrics.items():
                print(f"    {k:12s}: {v:.4f}")

        print("\n  ✅ Model Metrics (LSTM Sequential):")
        if self.dashboard.lstm_metrics:
            for k, v in self.dashboard.lstm_metrics.items():
                print(f"    {k:12s}: {v:.4f}")

        print("═" * 65)