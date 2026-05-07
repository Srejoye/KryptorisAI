import os
import time
import httpx
import random
import threading
from flask_cors import CORS
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)
CORS(app)

# Configurations
TARGET = os.getenv("TARGET_URL", "http://127.0.0.1:8000")
KRYPTORIS_URL = os.getenv("KRYPTORIS_URL", "http://127.0.0.1:5000")
ENDPOINTS = ["/", "/collection", "/about", "/contact", "/service"]
THREAD_COUNTS = {"normal": 3, "ddos": 20, "bruteforce": 20, "spike": 5}

# Helper : Interruptible Sleep
def sleep_interruptible(seconds):
    steps = max(1, int(seconds / 0.01))
    for _ in range(steps):
        if not attack_state["running"]:
            break
        time.sleep(0.01)

# Global attack state
attack_state = {"running": False, "mode": "stopped"}
attack_threads = []

# Traffic generators
def normal_traffic():
    while attack_state["running"] and attack_state["mode"] == "normal":
        try:
            httpx.get(f"{TARGET}{random.choice(ENDPOINTS)}", timeout=2)
        except Exception:
            pass
        sleep_interruptible(random.uniform(0.5, 2.0))

def ddos_traffic():
    fake_ips = [f"10.0.{random.randint(0,255)}.{random.randint(1,254)}" for _ in range(100)]
    while attack_state["running"] and attack_state["mode"] == "ddos":
        try:
            ip = random.choice(fake_ips[:50])
            httpx.get(f"{TARGET}{random.choice(ENDPOINTS)}", headers={"X-Forwarded-For": ip}, timeout=1)
        except Exception:
            pass
        sleep_interruptible(0.01)

def bruteforce_traffic():
    passwords = ["123456", "password", "admin", "letmein", "test123"]
    while attack_state["running"] and attack_state["mode"] == "bruteforce":
        try:
            httpx.post(f"{TARGET}/login", data={"user": "admin", "pass": random.choice(passwords)}, timeout=1)
        except Exception:
            pass
        sleep_interruptible(0.1)

def spike_traffic():
    while attack_state["running"] and attack_state["mode"] == "spike":
        sleep_interruptible(random.uniform(2, 4))
        if not attack_state["running"]:
            break
        for _ in range(80):
            if not attack_state["running"]:
                break
            try:
                httpx.get(f"{TARGET}/", timeout=1)
            except Exception:
                pass

TRAFFIC_FUNCS = {"normal": normal_traffic, "ddos": ddos_traffic, "bruteforce": bruteforce_traffic, "spike": spike_traffic}

# Attack control logic
def start_attack(mode: str):
    global attack_threads
    attack_state["running"] = False
    for t in attack_threads:
        if t.is_alive():
            t.join(timeout=0.2)
    attack_state["running"] = True
    attack_state["mode"] = mode
    attack_threads = []
    count = THREAD_COUNTS.get(mode, 5)
    func = TRAFFIC_FUNCS.get(mode, normal_traffic)
    for _ in range(count):
        t = threading.Thread(target=func, daemon=True)
        t.start()
        attack_threads.append(t)

def _notify_kryptoris(mode: str):
    try:
        import json as _json
        import urllib.request as _urllib
        api_key = os.getenv("INGEST_API_KEY")
        if not api_key:
            return 
        payload = _json.dumps({"type": mode}).encode()
        req = _urllib.Request(f"{KRYPTORIS_URL}/api/trigger-attack", data=payload, headers={"Content-Type": "application/json", "x-api-key": api_key}, method="POST",)
        _urllib.urlopen(req, timeout=1)
    except Exception as e:
      print(f"[Notify Error] {e}")

# API endpoints
@app.route("/start/<mode>", methods=["POST"])
def api_start(mode):
    if mode not in TRAFFIC_FUNCS:
        return jsonify({"error": "unknown mode"}), 400
    start_attack(mode)
    _notify_kryptoris(mode)        
    return jsonify({"ok": True, "mode": mode})

@app.route("/stop", methods=["POST"])
def api_stop():
    attack_state["running"] = False
    attack_state["mode"] = "stopped"
    for t in attack_threads:
        if t.is_alive():
            t.join(timeout=0.2)
    return jsonify({"ok": True})

@app.route("/status")
def api_status():
    return jsonify(attack_state)

# Control panel UI
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title> Attack Control Panel </title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {box-sizing: border-box; margin: 0; padding: 0;}

    :root {
      --bg-page: #f6f7f3;
      --surface-0: rgba(255,255,255,0.5);
      --surface-1: rgba(255,255,255,0.65);
      --surface-2: rgba(255,255,255,0.8);
      --border: rgba(122,143,106,0.14);
      --border-active: rgba(122,143,106,0.35);
      --olive: #7a8f6a;
      --olive-dim: #5e7050;
      --olive-light: #a3b18a;
      --olive-mist: #d4ddc8;
      --text-primary: #2f3e2f;
      --text-secondary: #6b7c6b;
      --text-dim: #9aab92;
      --status-green: #4a7c59;
      --status-red: #b05555;
      --status-orange: #a07040;
      --status-purple: #7a6aaa;
      --status-grey: #9aab92;
      --font-display: 'Syne', sans-serif;
      --font-body: 'DM Sans', sans-serif;
      --radius-sm: 12px;
      --radius-md: 18px;
      --radius-lg: 24px;
      --radius-xl: 32px;
    }

    html, body {height: 100%; background: var(--bg-page); color: var(--text-primary); font-family: var(--font-body); font-weight: 300; overflow-x: hidden; -webkit-font-smoothing: antialiased;}

    .scene {position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden;}
    .orb {position: absolute; border-radius: 50%; filter: blur(100px); opacity: 0.22; animation: breathe 10s ease-in-out infinite;}
    .orb-1 {width: 560px; height: 560px; background: radial-gradient(circle, #c2ceaf, transparent 70%); top: -180px; left: -120px; animation-delay: 0s;}
    .orb-2 {width: 480px; height: 480px; background: radial-gradient(circle, #b8c9a0, transparent 70%); bottom: -120px; right: -100px; animation-delay: -3s;}
    .orb-3 {width: 280px; height: 280px; background: radial-gradient(circle, #a3b18a, transparent 70%); top: 40%; left: 55%; animation-delay: -5s; opacity: 0.14;}
    @keyframes breathe {0%, 100% {transform: scale(1) translate(0,0);} 50% {transform: scale(1.08) translate(10px,-15px);}}

    .grid-lines {position: absolute; inset: 0; background-image: linear-gradient(rgba(122,143,106,0.30) 1px, transparent 1px), linear-gradient(90deg, rgba(122,143,106,0.30) 1px, transparent 1px); background-size: 48px 48px; mask-image: radial-gradient(ellipse 80% 80% at 50% 50%, black 30%, transparent 100%);}
    .shield-wrap {position: fixed; left: 50%; top: 50%; transform: translate(-50%, -50%); z-index: 1; pointer-events: none; opacity: 0.04; filter: blur(2px);}
    .shield-svg {width: 440px; height: 500px;}

    .layout {position: relative; z-index: 10; height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px 24px;}
    .panel {width: 100%; max-width: 680px; background: rgba(255, 255, 255, 0.72); backdrop-filter: blur(28px) saturate(1.3); -webkit-backdrop-filter: blur(28px) saturate(1.3);
      border: 1px solid rgba(122,143,106,0.16); border-radius: var(--radius-xl); box-shadow: 0 2px 0 rgba(255,255,255,0.9) inset, 0 30px 80px rgba(80,100,70,0.12), 0 10px 30px rgba(80,100,70,0.08);
      padding: 30px 30px 10px; animation: panelIn 0.8s cubic-bezier(0.16, 1, 0.3, 1) both; transform-style: preserve-3d;}
    @keyframes panelIn {from {opacity: 0; transform: translateY(28px) scale(0.97);} to {opacity: 1; transform: translateY(0) scale(1);}}
    .panel::before {content: ''; position: absolute; top: 0; left: 12%; right: 12%; height: 1px; background: linear-gradient(90deg, transparent, rgba(163,177,138,0.6), transparent); border-radius: 1px;}

    .header {display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 36px;}
    .logo-group {display: flex; flex-direction: column; gap: 6px;}
    .logo-badge {display: inline-flex; align-items: center; gap: 8px; background: rgba(122,143,106,0.1); border: 1px solid rgba(122,143,106,0.2); border-radius: 8px; padding: 4px 10px 4px 8px; width: fit-content; margin-bottom: 4px;}
    .logo-icon {width: 18px; height: 18px;}
    .logo-badge-text {font-family: var(--font-display); font-size: 10px; font-weight: 700; letter-spacing: 0.12em; color: var(--olive); text-transform: uppercase;}
    .logo-title {font-family: var(--font-display); font-size: 28px; font-weight: 800; letter-spacing: -0.02em; line-height: 1; background: linear-gradient(135deg, #2f3e2f 0%, #5e7050 55%, #7a8f6a 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;}
    .logo-sub {font-size: 12px; color: var(--text-dim); letter-spacing: 0.04em; font-weight: 400; margin-top: 2px;}

    .divider {height: 1.8px; background: linear-gradient(90deg, transparent 0%, rgba(122,143,106,0.15) 25%, rgba(122,143,106,0.4) 50%, rgba(122,143,106,0.15) 75%, transparent 100%); margin: 24px 74px 20px;}
    .section-label {font-size: 10px; font-weight: 600; letter-spacing: 0.14em; color: var(--text-dim); text-transform: uppercase; margin-bottom: 14px;}

    .scenarios {display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 28px;}
    .scenario-card {position: relative; background: rgba(255,255,255,0.55); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 18px 16px; cursor: pointer; transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1); overflow: hidden; box-shadow: 0 2px 8px rgba(80,100,70,0.05); animation: cardIn 0.6s cubic-bezier(0.16, 1, 0.3, 1) both;}
    .scenario-card:nth-child(1) {animation-delay: 0.1s;}
    .scenario-card:nth-child(2) {animation-delay: 0.18s;}
    .scenario-card:nth-child(3) {animation-delay: 0.26s;}
    .scenario-card:nth-child(4) {animation-delay: 0.34s;}
    @keyframes cardIn {from {opacity: 0; transform: translateY(16px);} to {opacity: 1; transform: translateY(0);}}

    .scenario-card::before {content: ''; position: absolute; inset: 0; border-radius: inherit; background: linear-gradient(135deg, rgba(255,255,255,0.5), transparent 60%); opacity: 0; transition: opacity 0.25s;}
    .scenario-card:hover {transform: translateY(-3px) scale(1.015); border-color: rgba(122,143,106,0.28); box-shadow: 0 10px 32px rgba(80,100,70,0.12), 0 2px 8px rgba(80,100,70,0.06);}
    .scenario-card:hover::before {opacity: 1;}
    .scenario-card.active {border-color: var(--olive); background: rgba(122,143,106,0.08); box-shadow: 0 0 0 1px rgba(122,143,106,0.2), 0 8px 24px rgba(80,100,70,0.1);}
    .scenario-card.active::after {content: ''; position: absolute; top: -1px; left: 10%; right: 10%; height: 2px; background: linear-gradient(90deg, transparent, var(--olive), transparent); border-radius: 1px;}
    .card-icon {width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; margin-bottom: 12px; font-size: 17px; position: relative; z-index: 1;}
    .card-title {font-family: var(--font-display); font-size: 14px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; position: relative; z-index: 1;}
    .card-desc {font-size: 11px; color: var(--text-dim); line-height: 1.5; font-weight: 300; position: relative; z-index: 1;}

    .card-normal .card-icon {background: rgba(74,124,89,0.1);}
    .card-ddos .card-icon {background: rgba(176,85,85,0.1);}
    .card-brute .card-icon {background: rgba(160,112,64,0.1);}
    .card-spike .card-icon {background: rgba(122,106,170,0.1);}

    .actions {display: flex; gap: 12px; margin-bottom: 32px;}
    .btn {flex: 1; padding: 15px 20px; border-radius: var(--radius-sm); border: none; cursor: pointer; font-family: var(--font-display); font-size: 14px; font-weight: 700; letter-spacing: 0.04em;transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1); position: relative; overflow: hidden;}
    .btn:active {transform: scale(0.97);}
    .btn-start {background: linear-gradient(135deg, #5e7050 0%, #7a8f6a 55%, #8fa07a 100%); color: #fff; box-shadow: 0 4px 16px rgba(90,112,76,0.25), 0 1px 0 rgba(255,255,255,0.18) inset; letter-spacing: 0.06em;}
    .btn-start::before {content: ''; position: absolute; top: 0; left: -100%; width: 60%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.12), transparent); transform: skewX(-20deg); transition: left 0.5s;}
    .btn-start:hover::before {left: 150%;}
    .btn-start:hover {box-shadow: 0 8px 28px rgba(90,112,76,0.35), 0 1px 0 rgba(255,255,255,0.2) inset; transform: translateY(-1px);}
    
    .footer {display: flex; align-items: center; justify-content: space-between; padding-top: 24px; border-top: 1px solid var(--border);}
    .footer-links {display: flex; gap: 20px;}
    .footer-link {display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-dim); text-decoration: none; transition: color 0.2s; letter-spacing: 0.02em;}
    .footer-link:hover {color: var(--olive);}
    .footer-link svg {width: 11px; height: 11px; opacity: 0.6;}
    .footer-hint {font-size: 10.5px; color: var(--text-dim); letter-spacing: 0.03em; opacity: 0.6;}

    .particles {position: fixed; inset: 0; pointer-events: none; z-index: 2;}
    .particle {position: absolute; width: 2px; height: 2px; border-radius: 50%; background: rgba(122,143,106,0.35); animation: drift linear infinite;}
    @keyframes drift {from {transform: translateY(100vh) translateX(0); opacity: 0;} 10% {opacity: 1;} 90% {opacity: 0.4;} to {transform: translateY(-10vh) translateX(var(--dx)); opacity: 0;}}

    ::-webkit-scrollbar {width: 4px;}
    ::-webkit-scrollbar-track {background: transparent;}
    ::-webkit-scrollbar-thumb {background: rgba(122,143,106,0.2); border-radius: 2px;}

    @media (max-width: 520px) {
      .panel {padding: 28px 20px 24px;}
      .scenarios {grid-template-columns: 1fr;}
      .header {flex-direction: column; gap: 14px;}
      .shield-wrap {display: none;}
      .footer {flex-direction: column; gap: 12px; align-items: flex-start;}
    }
  </style>
</head>
<body>
  <div class="scene">
    <div class="orb orb-1"></div>
    <div class="orb orb-2"></div>
    <div class="orb orb-3"></div>
    <div class="grid-lines"></div>
  </div>

  <div class="particles" id="particles"></div>
  <div class="shield-wrap" id="shield">
    <svg class="shield-svg" viewBox="0 0 280 320" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="shieldFill" x1="140" y1="20" x2="140" y2="310" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stop-color="#7a8f6a" stop-opacity="0.9"/>
          <stop offset="60%" stop-color="#a3b18a" stop-opacity="0.6"/>
          <stop offset="100%" stop-color="#5e7050" stop-opacity="0.3"/>
        </linearGradient>
        <linearGradient id="shieldStroke" x1="0" y1="0" x2="280" y2="320" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stop-color="#c2ceaf" stop-opacity="0.8"/>
          <stop offset="50%" stop-color="#7a8f6a" stop-opacity="0.5"/>
          <stop offset="100%" stop-color="#5e7050" stop-opacity="0.2"/>
        </linearGradient>
      </defs>
      <path d="M140 20 L240 60 L240 160 C240 230 180 290 140 310 C100 290 40 230 40 160 L40 60 Z"
            fill="url(#shieldFill)" stroke="url(#shieldStroke)" stroke-width="1.5"/>
      <path d="M140 44 L216 76 L216 160 C216 216 168 268 140 284 C112 268 64 216 64 160 L64 76 Z"
            fill="none" stroke="rgba(122,143,106,0.4)" stroke-width="1"/>
      <path d="M140 68 L192 92 L192 158 C192 202 156 246 140 258 C124 246 88 202 88 158 L88 92 Z"
            fill="none" stroke="rgba(163,177,138,0.3)" stroke-width="1"/>
      <circle cx="140" cy="170" r="32" fill="rgba(122,143,106,0.15)" stroke="rgba(122,143,106,0.4)" stroke-width="1"/>
      <path d="M140 148 L156 166 L148 166 L148 192 L132 192 L132 166 L124 166 Z"
            fill="rgba(94,112,80,0.8)"/>
      <path d="M100 60 L140 44 L140 100 Z" fill="rgba(255,255,255,0.1)"/>
    </svg>
  </div>

  <div class="layout">
    <div class="panel" id="panel">
      <div class="header">
        <div class="logo-group">
          <div class="logo-badge">
            <svg class="logo-icon" viewBox="0 0 18 18" fill="none">
              <path d="M9 2L15 5V10C15 13.5 12.5 16.5 9 17.5C5.5 16.5 3 13.5 3 10V5L9 2Z" fill="rgba(122,143,106,0.2)" stroke="#7a8f6a" stroke-width="1.2"/>
              <path d="M9 6L11 8L10 8L10 12L8 12L8 8L7 8Z" fill="#5e7050"/>
            </svg>
            <span class="logo-badge-text"> Secure </span>
          </div>
          <div class="logo-title"> KryptorisAI </div>
          <div class="logo-sub"> Attack Simulation Control Panel </div>
        </div>
      </div>

      <div class="divider"></div>
      <div class="section-label"> Select Scenario </div>
      <div class="scenarios">
        <div class="scenario-card card-normal active" data-mode="normal" onclick="selectMode(this)">
          <div class="card-icon"> 🟢 </div>
          <div class="card-title"> Normal </div>
          <div class="card-desc"> Baseline network traffic under typical load conditions </div>
        </div>
        <div class="scenario-card card-ddos" data-mode="ddos" onclick="selectMode(this)">
          <div class="card-icon"> 🔴 </div>
          <div class="card-title"> DDoS Attack </div>
          <div class="card-desc"> Distributed traffic floods to test system resilience and availability </div>
        </div>
        <div class="scenario-card card-brute" data-mode="bruteforce" onclick="selectMode(this)">
          <div class="card-icon"> 🟠 </div>
          <div class="card-title"> Brute Force </div>
          <div class="card-desc"> Repeated authentication attempts to evaluate credential security </div>
        </div>
        <div class="scenario-card card-spike" data-mode="spike" onclick="selectMode(this)">
          <div class="card-icon"> 🟣 </div>
          <div class="card-title"> Spike Attack </div>
          <div class="card-desc"> Sudden traffic surges to assess system stability under peak load </div>
        </div>
      </div>

      <div class="section-label"> Control </div>
      <div class="actions">
        <button class="btn btn-start" onclick="startSim()"> ▶ Start Simulation </button>
      </div>
    </div>
  </div>

  <script>
    let currentMode = 'normal', pollInterval = null;
    const $ = id => document.getElementById(id);
    const cards = document.querySelectorAll('.scenario-card');
    const particleContainer = document.getElementById('particles');
    const api = (url, method='GET') => fetch(url, { method }).then(r => (r && r.ok ? r : null)).catch(() => null);

    function selectMode(el) {
      cards.forEach(card => card.classList.remove('active'));
      el.classList.add('active'); currentMode = el.dataset.mode;
    }

    async function checkStatus() {
      const res = await api('/status');
      if (!res) return;
      try { const data = await res.json(); } catch {}
    }

    async function startSim() {stopPolling(); await api(`/start/${currentMode}`, 'POST'); startPolling();}
    function startPolling() {stopPolling(); pollInterval = setInterval(checkStatus, 1000);}
    function stopPolling() {if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }}

    if (particleContainer) {
      for (let i = 0; i < 18; i++) {
        const p = document.createElement('div'); p.className = 'particle';
        const x = Math.random() * 100;
        const delay = Math.random() * 20;
        const dur = 14 + Math.random() * 16;
        const dx = (Math.random() - 0.5) * 120;
        p.style.cssText = `left:${x}vw; --dx:${dx}px; animation-duration:${dur}s; animation-delay:-${delay}s; opacity:${0.3+Math.random()*0.4};`;
        particleContainer.appendChild(p);
      }
    }

    const orb1 = document.querySelector('.orb-1');
    const orb2 = document.querySelector('.orb-2');
    const shield = $('shield');

    document.addEventListener('mousemove', (e) => {
      const cx = window.innerWidth / 2;
      const cy = window.innerHeight / 2;
      const dx = (e.clientX - cx) / cx;
      const dy = (e.clientY - cy) / cy;
      if (orb1) {orb1.style.transform = `translate(${dx * 14}px, ${dy * 12}px)`;}
      if (orb2) {orb2.style.transform = `translate(${-dx * 10}px, ${-dy * 8}px)`;}
      if (shield) {shield.style.transform = `translateY(-50%) translateY(${dy * -8}px) rotateY(${dx * 6}deg)`;}
    });
  </script>
</body>
</html>
"""

@app.route("/")
def control_panel():
    return render_template_string(HTML)

if __name__ == "__main__":
    print("Control Panel running at http://127.0.0.1:8080")
    app.run(host="0.0.0.0", port=8080, debug=False)