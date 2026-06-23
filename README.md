# 🛡️ KryptorisAI

> A real-time AI-powered intrusion detection and automated response system — combining XGBoost, LSTM and statistical anomaly detection to classify live HTTP traffic and neutralize threats instantly.

🔗 Built with Python · Flask · PyTorch · XGBoost · Vanilla JS

---

## 📌 Overview

**KryptorisAI** is a real-time machine learning cybersecurity intelligence system that monitors incoming HTTP traffic, classifies each window of requests as **Normal**, **Suspicious** or **Attack**, and autonomously responds — rate-limiting flagged IPs, queueing medium-risk cases for admin review and hard-blocking confirmed threats. Every detection cycle runs in under a second.

Unlike rule-based firewalls, KryptorisAI learns from traffic patterns. Unlike batch ML pipelines, it acts immediately. The system trains its own models on startup, persists them to disk and begins live inference within seconds — all from a single Python process with no external infrastructure.

---

## 🔒 Why a Simulation Environment?
 
Deploying an autonomous intrusion detection and response system on real-world infrastructure is not as simple as pointing it at a live server. It requires:
 
- **Backend-level access** to web infrastructure and server logs
- **Visibility into live request streams**, which are typically private and legally protected
- **Administrative authorization** to apply automated mitigations such as rate-limiting or IP blocking
- **Security compliance**, since an active mitigation system acting on production traffic carries operational risk if misconfigured
 
KryptorisAI is an **architectural proof-of-concept**. It demonstrates that the full detection and response pipeline — hybrid ML inference, adaptive fusion, SHAP explainability, tiered mitigation and human-in-the-loop review — can be built, evaluated and operated as a coherent system. To do this safely and reproducibly without requiring privileged access to real production systems, it includes a **dedicated traffic simulation and attack orchestration environment** that reproduces realistic HTTP behaviors: DDoS bursts, brute-force login attempts, traffic spikes and normal baseline traffic.
 
---

## 📊 Evaluation Metrics

Both models are trained and evaluated on a synthetic dataset of 6,000 labelled traffic windows, split 80/20 across Normal, Suspicious and Attack classes. The dataset is generated programmatically by `evaluation/metrics.py` to reproduce realistic statistical distributions for each traffic class.

| Model | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|---|
| **XGBoost** | 0.92 | 0.95 | 0.94 | 0.93 | 0.94 |
| **LSTM** | 0.95 | 0.93 | 0.95 | 0.92 | 0.93 |

The LSTM demonstrates stronger temporal pattern recognition, while XGBoost provides high-confidence point-in-time classification — validating the hybrid fusion approach.

---
## ✨ Features

| Feature | Description |
|---|---|
| **Hybrid ML Pipeline** | XGBoost (point-in-time) + LSTM (sequential memory) + Statistical detector running in parallel per window |
| **Adaptive Fusion Engine** | Weighted score fusion with dynamic weight-flipping when models strongly disagree |
| **Tiered Auto-Response** | Four escalation tiers: Monitor → Rate Limit → Admin Approval → Auto-Block |
| **Live SHAP Explainability** | Top contributing features computed and visualized on every single inference window |
| **Human-in-the-Loop** | Medium-risk IPs queued for admin approve/reject via REST API before any block is applied |
| **Dual-mode Ingestion** | Accepts real traffic via API; falls back to synthetic traffic generation when buffer is empty |
| **TTL-based Blocklist** | Blocked IPs auto-expire after a configurable TTL (default: 30 minutes) |
| **Control Panel** | Trigger attack scenarios (DDoS, Brute-force, Spike) live from the dashboard |
| **Live Dashboard** | Real-time charts, SHAP bars, alert feed, blocked IPs — all polling at 1s intervals |
| **Model Persistence** | Trained models saved to disk; reloaded instantly on subsequent server starts |
| **Input Validation** | API enforces required fields per log entry; rejects malformed or unauthorized payloads |

---

## 🚀 How to Run

No frontend build tools or package managers required. Pure Python backend + static frontend.

```bash
# Clone the repository
git clone https://github.com/Srejoye/KryptorisAI
cd KryptorisAI

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp backend/.env.example backend/.env   # then set your INGEST_API_KEY

# Start the server
python backend/main.py
```

Open **`http://localhost:5000`** in your browser. On first launch, models train automatically (~10–20 seconds). On subsequent starts, saved models are loaded instantly from disk.

---

## 🖥️ Usage

### Step 1 — Watch the Dashboard Initialize
On startup, a background thread begins generating synthetic traffic and running inference immediately. The dashboard at **`http://localhost:5000`** goes live before any real data arrives — charts update, risk scores pulse, the status badge activates.

### Step 2 — Launch the Control Panel
The **Control Panel** is a separate app that simulates real HTTP traffic and notifies KryptorisAI simultaneously. It exists precisely to exercise the full detection pipeline without requiring access to a real backend — sending actual HTTP requests to a local target server while signalling KryptorisAI to switch detection mode accordingly.

```bash
python backend/tools/control_panel.py
```

Open **`http://localhost:8080`**, select a scenario card and click **▶ Start Simulation**. The panel spawns worker threads sending real HTTP requests to your target (`http://localhost:8000` by default) while calling `/api/trigger-attack` on KryptorisAI to switch detection mode.

> ⚠️ `INGEST_API_KEY` must be set in `.env` for the control panel to authenticate with KryptorisAI.

> ℹ️ Port 8000 is the optional attack target. If nothing is running there, requests fail silently and KryptorisAI continues on synthetic data — the dashboard remains fully functional. To point the control panel at your own backend, set `TARGET_URL` in `.env` to your server's address.

| Scenario | Threads | Behaviour |
|---|---|---|
| 🟢 Normal | 3 | Randomized GET requests across endpoints, 0.5–2s apart |
| 🔴 DDoS | 20 | Rapid-fire GETs with spoofed `X-Forwarded-For` IPs, 10ms apart |
| 🟠 Brute Force | 20 | Repeated POST to `/login` with common passwords, 100ms apart |
| 🟣 Spike | 5 | Quiet for 2–4s, then 80 requests fired in rapid succession |

To trigger a scenario without the control panel:

```bash
curl -X POST http://localhost:5000/api/trigger-attack \
  -H "x-api-key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"type": "ddos"}'
```

### Step 3 — (Optional) Ingest Real Traffic
If you have access to a real backend and want to connect KryptorisAI to live infrastructure, you can push log entries directly to the ingest endpoint. This replaces synthetic generation with actual traffic data and is the intended path for production integration — subject to appropriate authorization on the target system.

```bash
curl -X POST http://localhost:5000/api/ingest \
  -H "x-api-key: your-key" \
  -H "Content-Type: application/json" \
  -d '[{"ip":"1.2.3.4","method":"POST","endpoint":"/api/login","status_code":401}]'
```

Required fields: `ip`, `method`, `endpoint`, `status_code`. Optional: `bytes`, `response_ms`, `timestamp`.

### Step 4 — Observe Detection and Response
- **Risk Score** and badge transition: ✅ Normal → ⚠️ Suspicious → 🚨 Attack
- **SHAP panel** shows which features drove each prediction
- **Alert feed** logs severity, reasons and top offending IPs
- **Blocked IPs** table updates as the response engine acts

### Step 5 — Manage Blocked IPs

```bash
curl -X POST http://localhost:5000/api/approve-block/1.2.3.4  # Approve pending block
curl -X POST http://localhost:5000/api/reject-block/1.2.3.4   # Reject pending block
curl -X POST http://localhost:5000/api/manual-block/9.9.9.9   # Force-block any IP
curl -X POST http://localhost:5000/api/unblock/1.2.3.4        # Remove all restrictions
```

---

## 🗂️ Project Structure

```
KryptorisAI/
├── backend/
│   ├── main.py                  # Flask app, API routes, background threads, state management
│   ├── config.py                # All thresholds, window settings, feature names (env-configurable)
│   ├── utils.py                 # Synthetic traffic generator, Dashboard collector
│   ├── inference/
│   │   └── engine.py            # CyberDetectionPipeline — orchestrates all components
│   ├── models/
│   │   ├── xgb_model.py         # XGBoost classifier with StandardScaler and SHAP explainer
│   │   ├── lstm_model.py        # 2-layer LSTM network (PyTorch) for sequential classification
│   │   ├── stats_model.py       # Statistical anomaly detector (Z-score, EMA, spike, fail rate)
│   │   ├── fusion.py            # Adaptive weighted fusion engine
│   │   └── saved/               # Persisted model weights (xgb.pkl, lstm.pt)
│   ├── features/
│   │   └── extractor.py         # 12-feature extractor with EMA, rolling stats, real elapsed-time RPS
│   ├── alert/
│   │   └── alert_system.py      # Rule + ML hybrid alerting with per-IP cooldown
│   ├── mitigation/
│   │   └── response.py          # Tiered response engine with human-in-the-loop support
│   ├── evaluation/
│   │   └── metrics.py           # Synthetic data generation and model training/evaluation
│   └── tools/
│       └── control_panel.py     # Dashboard control panel logic
├── frontend/
│   ├── index.html               # Dashboard shell — layout, live stat panels, charts, alert feed
│   ├── script.js                # Polling logic, Chart.js wrappers, SHAP renderer, DOM updates
│   └── style.css                # Design system — dark theme, animations, responsive layout
└── requirements.txt
```

---

## 🎨 Tech Stack

| Technology | Role |
|---|---|
| **Python + Flask** | Backend API server, background inference threads, state management |
| **XGBoost** | Point-in-time binary classification on the 12-feature vector |
| **PyTorch (LSTM)** | Sequential classification over a rolling 10-window feature buffer |
| **SHAP** | Per-inference explainability via TreeExplainer on every XGBoost prediction |
| **scikit-learn** | StandardScaler for feature normalization, evaluation metrics |
| **NumPy** | Feature computation, rolling statistics, sequence buffering |
| **HTML5 + CSS3** | Dashboard layout, dark-mode design system, keyframe animations |
| **Vanilla JS + Chart.js** | Real-time polling, live chart updates, SHAP bar rendering |

---

## 🔁 Detection Pipeline

```
Incoming Logs (real or synthetic)
        │
        ▼
  Feature Extractor  →  12 signals: RPS, spike, fail rate, IP concentration,
        │                 auth failures, EMA, rolling mean/std, endpoint ratio...
        │
   ┌────┴────┐
   ▼         ▼
XGBoost    LSTM          +   Statistical Anomaly Detector (Z-score, EMA dev, spike)
(current   (last 10
 window)    windows)
   │         │                      │
   └────┬────┘                      │
        ▼                           ▼
   Fusion Engine  ←─────── anomaly_score boost (+0.15 if score > 0.7)
  (adaptive weights: 60/40 default → 30/70 on model disagreement)
        │
        ▼
   Risk Score + Classification (Normal / Suspicious / Attack)
        │
   ┌────┴────────────────────────┐
   ▼                             ▼
Alert System              Response Engine
(rule + ML hybrid,       (Monitor / Rate-Limit /
 per-IP cooldown)         Pending Approval / Auto-Block)
   │                             │
   └────────────┬────────────────┘
                ▼
     Flask API + Live Dashboard
```

---

## 📊 Response Tiers

| Risk Score | Action | Details |
|---|---|---|
| `≥ 0.95` | **Auto-Block** | Top offending IPs added to blocklist instantly; expires after TTL |
| `0.85 – 0.95` | **Pending Admin** | Top 2 IPs queued for human approve/reject before any block |
| `0.60 – 0.85` | **Rate Limit** | Top 3 IPs throttled at 100 req/min |
| `< 0.60` | **Monitor** | IPs logged and tracked; no restriction applied |

All thresholds are configurable via environment variables: `RISK_AUTOBLOCK`, `RISK_APPROVAL`, `RISK_RATELIMIT`.

---

## 🌐 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/state` | GET | Current window: risk score, class, features, SHAP values, alert |
| `/api/data` | GET | Time-series history — last 60 windows of RPS and risk |
| `/api/alerts` | GET | Last 20 alerts with severity, reasons, top IPs, feature snapshot |
| `/api/blocked-ips` | GET | All blocked and rate-limited IPs with metadata |
| `/api/blocklist` | GET | TTL-managed blocklist (stale entries auto-cleaned) |
| `/api/pending-approvals` | GET | IPs awaiting admin decision |
| `/api/approve-block/<ip>` | POST | Admin approves → IP moved to blocked |
| `/api/reject-block/<ip>` | POST | Admin rejects → IP returned to monitoring |
| `/api/unblock/<ip>` | POST | Remove IP from all restriction lists |
| `/api/manual-block/<ip>` | POST | Force-block any IP immediately |
| `/api/ingest` | POST | Submit real log entries *(API key required)* |
| `/api/trigger-attack` | POST | Switch active traffic scenario *(API key required)* |
| `/api/status` | GET | Server readiness and ingest buffer depth |

---

## 📚 Concepts Covered

- **Ensemble ML Inference** — combining gradient-boosted trees and recurrent networks for complementary signal coverage
- **Adaptive Model Fusion** — dynamic weight assignment based on inter-model disagreement
- **Statistical Anomaly Detection** — Z-score, EMA deviation, spike detection and error rate thresholding in parallel with ML
- **SHAP Explainability** — model-agnostic feature attribution surfaced live per prediction, not just offline
- **Human-in-the-Loop Security** — automated escalation with mandatory admin override at medium-risk tier
- **Window-accurate RPS** — elapsed time computed from real log timestamps rather than fixed window constants
- **Sequence Modeling for Security** — LSTM over rolling feature buffers to detect gradual attack escalation

---

## ⭐ Support

If you found this project useful or interesting, consider giving it a ⭐ on GitHub.