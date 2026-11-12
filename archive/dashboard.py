#!/usr/bin/env python3
"""
Papertrade Quantitative TradingView Slate/Grey Dashboard
Palette: Muted Slate-Grey with Luminous Shiny Light-Blue (Ice Cyan) Accents
Engine: FastAPI + Hyperliquid L1 Oracle Cache Shield
Frontend: TradingView Lightweight Charts v4.1 (Pure Light Mode, No Volume, Refined Lines)
Port: 8899
"""
import os
import json
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

WIB = timezone(timedelta(hours=7))
BASE_DIR = "/home/ubuntu/papertrade_backtest"
STATE_FILE = os.path.join(BASE_DIR, "papertrade_state.json")
LOG_FILE = os.path.join(BASE_DIR, "papertrade_watcher.log")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="Papertrade Quant Desk")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_DASH_CACHE = {}

def fetch_hyperliquid_candles(coin="BTC", interval="5m", limit=160):
    now = time.time()
    cache_key = f"dash_candles_{coin}_{interval}_{limit}"
    ttl = 45 if interval in ["15m", "1h", "4h"] else 10
    if cache_key in _DASH_CACHE:
        c_time, c_val = _DASH_CACHE[cache_key]
        if now - c_time < ttl:
            return c_val

    now_ms = int(time.time() * 1000)
    mins_map = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240}
    step = mins_map.get(interval, 5)
    start_ms = now_ms - (limit * step * 60 * 1000)
    
    url = "https://api.hyperliquid.xyz/info"
    payload = json.dumps({
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": interval,
            "startTime": start_ms
        }
    }).encode("utf-8")
    
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            candles = []
            for k in raw:
                candles.append({
                    "time": int(k["t"] / 1000),
                    "open": float(k["o"]),
                    "high": float(k["h"]),
                    "low": float(k["l"]),
                    "close": float(k["c"])
                })
            _DASH_CACHE[cache_key] = (now, candles)
            return candles
    except:
        if cache_key in _DASH_CACHE:
            return _DASH_CACHE[cache_key][1]
        return []

def fetch_all_mids():
    now = time.time()
    if "_dash_mids" in _DASH_CACHE:
        c_time, c_mids = _DASH_CACHE["_dash_mids"]
        if now - c_time < 2.5:
            return c_mids

    url = "https://api.hyperliquid.xyz/info"
    payload = json.dumps({"type": "allMids"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res = {k: float(v) for k, v in data.items() if k in ["ETH", "BTC"]}
            _DASH_CACHE["_dash_mids"] = (now, res)
            return res
    except:
        if "_dash_mids" in _DASH_CACHE:
            return _DASH_CACHE["_dash_mids"][1]
        return {}

def calc_ema(values, period=20):
    if len(values) < period:
        return values[-1] if values else 0
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for price in values[period:]:
        ema = (price * k) + (ema * (1 - k))
    return ema

def get_mtf_summary(coin):
    now = time.time()
    ckey = f"mtf_summary_{coin}"
    if ckey in _DASH_CACHE:
        c_time, c_val = _DASH_CACHE[ckey]
        if now - c_time < 30:
            return c_val

    c_1h = fetch_hyperliquid_candles(coin=coin, interval="1h", limit=25)
    c_15m = fetch_hyperliquid_candles(coin=coin, interval="15m", limit=25)
    if not c_1h or not c_15m:
        res = ("NEUTRAL", 0, 0)
        _DASH_CACHE[ckey] = (now, res)
        return res
    ema_1h = calc_ema([c["close"] for c in c_1h], 20)
    ema_15m = calc_ema([c["close"] for c in c_15m], 20)
    cur_1h = c_1h[-1]["close"]
    cur_15m = c_15m[-1]["close"]
    if cur_1h >= ema_1h and cur_15m >= ema_15m:
        bias = "BULLISH"
    elif cur_1h <= ema_1h and cur_15m <= ema_15m:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"
    res = (bias, ema_1h, ema_15m)
    _DASH_CACHE[ckey] = (now, res)
    return res

VALID_COINS = {"BTC", "ETH"}
VALID_INTERVALS = {"1m", "5m", "15m", "1h", "4h"}

@app.get("/api/candles")
def api_candles(coin: str = Query("BTC"), interval: str = Query("5m")):
    c_clean = coin.upper() if coin.upper() in VALID_COINS else "BTC"
    i_clean = interval if interval in VALID_INTERVALS else "5m"
    data = fetch_hyperliquid_candles(coin=c_clean, interval=i_clean, limit=160)
    return JSONResponse(content=data, headers={"X-Content-Type-Options": "nosniff"})

@app.get("/api/state")
def api_state():
    state_data = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                state_data = json.load(f)
        except:
            pass
            
    mids = fetch_all_mids()
    eth_p = float(mids.get("ETH", 0))
    btc_p = float(mids.get("BTC", 0))
    
    eth_bias, eth_ema1h, eth_ema15m = get_mtf_summary("ETH")
    btc_bias, btc_ema1h, btc_ema15m = get_mtf_summary("BTC")
    
    recent_logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE) as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
                recent_logs = lines[-16:]
        except:
            pass

    # Calculate Live Realtime Realized & Unrealized PnL
    active_pos = state_data.get("active_position")
    unrealized_usd = 0.0
    unrealized_pct = 0.0
    if active_pos:
        c = active_pos.get("coin", "BTC")
        cur_p = btc_p if c == "BTC" else eth_p
        entry_p = float(active_pos.get("limit_price", active_pos.get("entry", 0)))
        qty = float(active_pos.get("qty", 0))
        if cur_p > 0 and entry_p > 0 and qty > 0:
            diff = (cur_p - entry_p) if active_pos.get("dir") == "LONG" else (entry_p - cur_p)
            unrealized_usd = diff * qty
            unrealized_pct = (unrealized_usd / 50.0) * 100.0

    realized_usd = float(state_data.get("account", {}).get("net_pnl", 0.0))

    return JSONResponse(content={
        "state": state_data,
        "prices": {"ETH": eth_p, "BTC": btc_p},
        "mtf": {
            "ETH": {"bias": eth_bias, "ema1h": eth_ema1h, "ema15m": eth_ema15m},
            "BTC": {"bias": btc_bias, "ema1h": btc_ema1h, "ema15m": btc_ema15m}
        },
        "pnl": {
            "unrealized_usd": round(unrealized_usd, 2),
            "unrealized_pct": round(unrealized_pct, 2),
            "realized_usd": round(realized_usd, 2)
        },
        "logs": recent_logs,
        "server_time": datetime.now(tz=WIB).strftime("%H:%M:%S WIB")
    }, headers={"X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN"})

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def index():
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Papertrade // Quant Titanium Desk</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src="/static/lightweight-charts.js"></script>
  <style>
    :root {
      /* Muted Slate Grey Base (Comfortable on the eyes, not blinding white) */
      --bg-base: #e5ebf2;
      --bg-canvas: #e8ecf4;
      --bg-header: #edf2f8;
      --bg-panel: #eef3f9;
      --bg-card: #ffffff;
      --border: #ccd6e3;
      --border-subtle: #dbe3ed;
      
      /* Obsidian Slate Typography */
      --text-main: #0f172a;
      --text-muted: #526074;
      --text-dim: #8292a6;
      
      /* Shiny Luminous Light Blue / Ice Cyan Accents */
      --cyan-bright: #38bdf8;
      --cyan-deep: #0284c7;
      --cyan-glow: rgba(56, 189, 248, 0.35);
      --cyan-surface: #e0f2fe;
      
      --green: #059669;
      --green-subtle: #ecfdf5;
      --red: #e11d48;
      --red-subtle: #fff1f2;
      
      --font-ui: 'Plus Jakarta Sans', -apple-system, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg-base);
      color: var(--text-main);
      font-family: var(--font-ui);
      height: 100vh;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      -webkit-font-smoothing: antialiased;
    }
    
    /* TOP NAVIGATION (FROSTED COOL GREY + SHINY BLUE ACCENT) */
    header {
      background: var(--bg-header);
      border-bottom: 1px solid var(--border);
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 20px;
      user-select: none;
      z-index: 20;
      box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
    }
    .brand-group {
      display: flex;
      align-items: center;
      gap: 20px;
    }
    .logo-badge {
      display: flex;
      align-items: center;
      gap: 9px;
      font-family: var(--font-mono);
      font-size: 14px;
      font-weight: 700;
      color: var(--text-main);
      letter-spacing: -0.3px;
    }
    .shiny-dot {
      width: 8px;
      height: 8px;
      background: var(--cyan-bright);
      border-radius: 50%;
      box-shadow: 0 0 10px var(--cyan-bright), 0 0 18px var(--cyan-glow);
    }
    .pill-tabs {
      display: flex;
      background: #dce4ef;
      border-radius: 8px;
      padding: 3px;
      gap: 3px;
      border: 1px solid #cbd5e1;
    }
    .tab-btn {
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-muted);
      padding: 5px 12px;
      font-size: 12px;
      font-weight: 600;
      border-radius: 6px;
      cursor: pointer;
      font-family: var(--font-mono);
      transition: all 0.15s ease;
    }
    .tab-btn:hover { color: var(--text-main); }
    .tab-btn.active {
      background: linear-gradient(180deg, #ffffff 0%, #e0f2fe 100%);
      color: var(--cyan-deep);
      border: 1px solid #7dd3fc;
      box-shadow: 0 2px 8px var(--cyan-glow);
    }

    .ticker-display {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .ticker-price {
      font-family: var(--font-mono);
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.5px;
      color: var(--text-main);
    }
    .status-tag {
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 600;
      padding: 3px 10px;
      border-radius: 6px;
      display: flex;
      align-items: center;
      gap: 6px;
      border: 1px solid transparent;
    }
    .tag-bull { 
      background: var(--green-subtle); 
      color: var(--green); 
      border-color: #a7f3d0; 
    }
    .tag-bear { 
      background: var(--red-subtle); 
      color: var(--red); 
      border-color: #fecdd3; 
    }
    .tag-neutral { 
      background: #dce4ef; 
      color: var(--text-muted); 
      border-color: #cbd5e1; 
    }
    .tag-cyan {
      background: var(--cyan-surface);
      color: var(--cyan-deep);
      border-color: #7dd3fc;
      box-shadow: 0 0 10px var(--cyan-glow);
    }

    .nav-meta {
      display: flex;
      align-items: center;
      gap: 24px;
    }
    .meta-box {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
    }
    .meta-lbl {
      font-size: 10px;
      font-weight: 600;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .meta-val {
      font-family: var(--font-mono);
      font-size: 13px;
      font-weight: 700;
      color: var(--text-main);
    }

    /* MAIN WORKSPACE */
    .workspace {
      display: flex;
      flex: 1;
      height: calc(100vh - 56px);
      background: var(--bg-canvas);
    }
    .chart-viewport {
      flex: 1;
      position: relative;
      background: var(--bg-canvas);
      height: 100%;
    }
    #tv_chart {
      width: 100%;
      height: 100%;
    }

    /* OHLC BAR WITH SHINY LIGHT BLUE SHADOW */
    .ohlc-bar {
      position: absolute;
      top: 14px;
      left: 18px;
      z-index: 10;
      pointer-events: none;
      font-family: var(--font-mono);
      font-size: 12px;
      display: flex;
      gap: 16px;
      background: rgba(255, 255, 255, 0.88);
      padding: 6px 14px;
      border-radius: 8px;
      border: 1px solid rgba(56, 189, 248, 0.4);
      box-shadow: 0 4px 18px var(--cyan-glow);
      backdrop-filter: blur(8px);
      color: var(--text-muted);
    }
    .ohlc-bar span b { color: var(--text-main); }

    /* RIGHT CONTROL SIDEBAR */
    .sidebar {
      width: 380px;
      background: var(--bg-panel);
      border-left: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      overflow-y: auto;
      gap: 1px;
    }
    .panel-card {
      background: #f7fafc;
      padding: 18px 20px;
      border-bottom: 1px solid var(--border);
    }
    .card-title {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.6px;
      text-transform: uppercase;
      color: var(--text-dim);
      margin-bottom: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    
    /* SHINY LIGHT BLUE ACCENTED ORDER CARD */
    .order-box {
      background: #ffffff;
      border: 1px solid rgba(56, 189, 248, 0.45);
      border-radius: 10px;
      padding: 14px 16px;
      box-shadow: 0 4px 20px rgba(56, 189, 248, 0.12);
      transition: all 0.2s ease;
    }
    .ob-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      padding-bottom: 10px;
      border-bottom: 1px solid #edf2f7;
    }
    .ob-symbol {
      font-family: var(--font-mono);
      font-size: 14px;
      font-weight: 700;
      color: var(--text-main);
    }
    .ob-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 12px;
      margin-bottom: 7px;
    }
    .ob-lbl { 
      color: var(--text-muted); 
      font-weight: 500; 
      font-size: 11px; 
      opacity: 0.50; 
    }
    .ob-val { font-family: var(--font-mono); font-weight: 600; color: var(--text-main); }
    .val-entry { color: var(--cyan-deep); }
    .val-sl { color: var(--red); opacity: 0.85; }
    .val-tp { color: var(--green); opacity: 0.85; }

    /* SCORECARD GRID */
    .score-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .score-tile {
      background: #ffffff;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      box-shadow: 0 2px 8px rgba(15, 23, 42, 0.03);
    }
    .st-label {
      font-size: 10px;
      font-weight: 600;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }
    .st-value {
      font-family: var(--font-mono);
      font-size: 17px;
      font-weight: 700;
      color: var(--text-main);
      margin-top: 4px;
    }

    /* LOG STREAM FEED */
    .log-container {
      font-family: var(--font-mono);
      font-size: 11px;
      height: 180px;
      overflow-y: auto;
      background: #ffffff;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 12px;
      color: #475569;
      line-height: 1.6;
    }
    .log-item {
      padding: 3px 0;
      border-bottom: 1px solid #f1f5f9;
    }
    .log-item:last-child { border-bottom: none; }
  </style>
</head>
<body>

  <!-- HEADER -->
  <header>
    <div class="brand-group">
      <div class="logo-badge">
        <div class="shiny-dot"></div>
        <span>PAPERTRADE // DESK</span>
      </div>

      <!-- COIN TABS -->
      <div class="pill-tabs">
        <button class="tab-btn active" id="btn_btc" onclick="switchCoin('BTC')">BTC/USDT</button>
        <button class="tab-btn" id="btn_eth" onclick="switchCoin('ETH')">ETH/USDT</button>
      </div>

      <!-- TIMEFRAME TABS (TICKS, 1M, 5M, 15M, 1H) -->
      <div class="pill-tabs">
        <button class="tab-btn" id="tf_ticks" onclick="switchTf('ticks')">Ticks</button>
        <button class="tab-btn" id="tf_1m" onclick="switchTf('1m')">1m</button>
        <button class="tab-btn active" id="tf_5m" onclick="switchTf('5m')">5m</button>
        <button class="tab-btn" id="tf_15m" onclick="switchTf('15m')">15m</button>
        <button class="tab-btn" id="tf_1h" onclick="switchTf('1h')">1h</button>
      </div>
    </div>

    <!-- SPOT TICKER -->
    <div class="ticker-display">
      <span class="ticker-price" id="spot_price">Loading...</span>
      <span class="status-tag tag-neutral" id="mtf_tag">MTF: ...</span>
    </div>

    <!-- METRICS -->
    <div class="nav-meta">
      <div class="meta-box">
        <span class="meta-lbl">Margin / Lev</span>
        <span class="meta-val">$50 (100x)</span>
      </div>
      <div class="meta-box">
        <span class="meta-lbl">Realized Profit</span>
        <span class="meta-val" id="top_realized_pnl" style="color:var(--green)">+$0.00</span>
      </div>
      <div class="meta-box">
        <span class="meta-lbl">Floating Unrealized</span>
        <span class="meta-val" id="top_unrealized_pnl" style="color:var(--text-muted)">$0.00 (0.0%)</span>
      </div>
      <div class="meta-box">
        <span class="meta-lbl">Uptime</span>
        <span class="meta-val" id="top_uptime">--:--</span>
      </div>
    </div>
  </header>

  <!-- WORKSPACE -->
  <div class="workspace">
    <!-- CHART (NO VOLUME, CALM SLATE GREY CANVAS) -->
    <div class="chart-viewport">
      <div class="ohlc-bar" id="ohlc_overlay">
        <span>O: <b id="co_o">-</b></span>
        <span>H: <b id="co_h">-</b></span>
        <span>L: <b id="co_l">-</b></span>
        <span>C: <b id="co_c">-</b></span>
      </div>
      <div id="tv_chart"></div>
    </div>

    <!-- CONTROL PANEL SIDEBAR -->
    <div class="sidebar">
      
      <!-- ORDER BRACKET CARD -->
      <div class="panel-card">
        <div class="card-title">
          <span>Active Order Bracket</span>
          <span class="status-tag tag-neutral" id="order_status_badge">STANDBY</span>
        </div>

        <div class="order-box">
          <div class="ob-header">
            <span class="ob-symbol" id="card_symbol">NO ACTIVE ORDER</span>
            <span class="status-tag tag-neutral" id="card_side_badge">-</span>
          </div>
          <div class="ob-row">
            <span class="ob-lbl">Limit Entry:</span>
            <span class="ob-val val-entry" id="card_entry">-</span>
          </div>
          <div class="ob-row">
            <span class="ob-lbl">Cut-Loss (0.30%):</span>
            <span class="ob-val val-sl" id="card_sl">-</span>
          </div>
          <div class="ob-row">
            <span class="ob-lbl" id="card_tp_lbl">Win Target:</span>
            <span class="ob-val val-tp" id="card_tp">-</span>
          </div>
          <div class="ob-row">
            <span class="ob-lbl">Risk : Reward</span>
            <span class="ob-val" style="color:var(--cyan-deep)" id="card_rr">1 : 4.0</span>
          </div>
          <div class="ob-row">
            <span class="ob-lbl">Live Floating PnL:</span>
            <span class="ob-val" id="card_unrealized" style="font-weight:700;">-</span>
          </div>
          <div class="ob-row">
            <span class="ob-lbl">TTL Window:</span>
            <span class="ob-val" id="card_ttl">-</span>
          </div>
        </div>
      </div>

      <!-- PERFORMANCE SCORECARD -->
      <div class="panel-card">
        <div class="card-title">
          <span>Quant Scorecard & Bankroll</span>
          <span class="status-tag tag-cyan" id="sc_inc_badge" style="font-size:10px;">INCUBATION</span>
        </div>
        <div class="score-grid">
          <div class="score-tile">
            <div class="st-label">Win Rate</div>
            <div class="st-value" id="sc_winrate">0.0%</div>
          </div>
          <div class="score-tile">
            <div class="st-label">Record (W / L)</div>
            <div class="st-value" id="sc_wl" style="color:var(--text-muted)">0W / 0L</div>
          </div>
          <div class="score-tile">
            <div class="st-label">Bankroll Equity</div>
            <div class="st-value" id="sc_equity" style="font-size:15px; color:var(--text-main);">$500.00</div>
          </div>
          <div class="score-tile">
            <div class="st-label">Realized Profit</div>
            <div class="st-value" id="sc_realized" style="color:var(--green)">+$0.00</div>
          </div>
          <div class="score-tile">
            <div class="st-label">Profit Factor</div>
            <div class="st-value" id="sc_pf" style="font-size:15px; color:var(--cyan-deep);">0.00</div>
          </div>
          <div class="score-tile">
            <div class="st-label">Incubation Gate</div>
            <div class="st-value" id="sc_progress" style="font-size:15px; color:var(--text-main);">0 / 50</div>
          </div>
        </div>
      </div>

      <!-- STRATEGY BLUEPRINT -->
      <div class="panel-card">
        <div class="card-title">
          <span>Strategy Blueprint</span>
        </div>
        <div style="font-size:12px; line-height:1.7; color:var(--text-muted)">
          • <b>Trend Confluence:</b> 1H & 15M EMA20 Directional Filter<br>
          • <b>Execution Trigger:</b> 5M Pro-Trend Pullback Retest<br>
          • <b>Asymmetric Bracket:</b> ✂️ Cut 0.30% | 🎯 Win 1.20% (RR 1:4)<br>
          • <b>Order TTL:</b> 25 Menit (5 Candle) Auto-Cancel<br>
          • <b>Rate-Limit Shield:</b> In-Memory Anti-429 Oracle Cache
        </div>
      </div>

      <!-- EVENT FEED -->
      <div class="panel-card" style="flex:1; display:flex; flex-direction:column;">
        <div class="card-title">
          <span>System Activity Log</span>
        </div>
        <div class="log-container" id="log_stream">
          <div class="log-item">Engine initialized. Ready.</div>
        </div>
      </div>

    </div>
  </div>

  <script>
    let currentCoin = 'BTC';
    let currentTf = '5m';
    let chart, candleSeries = null, areaSeries = null;
    let entryLine = null, slLine = null, tpLine = null;
    let lastSavedBracket = null;

    function initChart() {
      const container = document.getElementById('tv_chart');
      chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: container.clientHeight,
        layout: {
          background: { color: '#e8edf4' },
          textColor: '#526074',
          fontFamily: "'JetBrains Mono', monospace",
        },
        grid: {
          vertLines: { color: '#dde4ee' },
          horzLines: { color: '#dde4ee' },
        },
        crosshair: {
          mode: LightweightCharts.CrosshairMode.Normal,
          vertLine: { color: '#94a3b8', width: 1, style: 3 },
          horzLine: { color: '#94a3b8', width: 1, style: 3 },
        },
        rightPriceScale: {
          borderColor: '#cbd5e1',
          autoScale: true,
        },
        timeScale: {
          borderColor: '#cbd5e1',
          timeVisible: true,
          secondsVisible: true,
        },
      });

      setupCandleSeries();

      chart.subscribeCrosshairMove(param => {
        if (!param.time) return;
        if (candleSeries && param.seriesData.get(candleSeries)) {
          const d = param.seriesData.get(candleSeries);
          document.getElementById('co_o').innerText = d.open.toFixed(1);
          document.getElementById('co_h').innerText = d.high.toFixed(1);
          document.getElementById('co_l').innerText = d.low.toFixed(1);
          document.getElementById('co_c').innerText = d.close.toFixed(1);
        } else if (areaSeries && param.seriesData.get(areaSeries)) {
          const d = param.seriesData.get(areaSeries);
          document.getElementById('co_o').innerText = 'Tick:';
          document.getElementById('co_h').innerText = d.value ? d.value.toFixed(1) : '-';
          document.getElementById('co_l').innerText = '-';
          document.getElementById('co_c').innerText = '-';
        }
      });

      window.addEventListener('resize', () => {
        chart.resize(container.clientWidth, container.clientHeight);
      });
    }

    function setupCandleSeries() {
      if (areaSeries) {
        chart.removeSeries(areaSeries);
        areaSeries = null;
      }
      if (!candleSeries) {
        candleSeries = chart.addCandlestickSeries({
          upColor: '#059669',
          downColor: '#e11d48',
          borderVisible: false,
          wickUpColor: '#059669',
          wickDownColor: '#e11d48',
        });
      }
    }

    function setupAreaSeries() {
      if (candleSeries) {
        chart.removeSeries(candleSeries);
        candleSeries = null;
      }
      if (!areaSeries) {
        areaSeries = chart.addAreaSeries({
          lineColor: '#0284c7',
          topColor: 'rgba(56, 189, 248, 0.40)',
          bottomColor: 'rgba(56, 189, 248, 0.02)',
          lineWidth: 2,
          priceLineVisible: true,
          lastValueVisible: true,
        });
      }
    }

    async function loadCandles() {
      if (currentTf === 'ticks') {
        setupAreaSeries();
        try {
          const res = await fetch(`/api/candles?coin=${currentCoin}&interval=1m`);
          const data = await res.json();
          if (data && data.length > 0) {
            const points = data.map(d => ({ time: d.time, value: d.close }));
            areaSeries.setData(points);
          }
        } catch(e) {}
      } else {
        setupCandleSeries();
        try {
          const res = await fetch(`/api/candles?coin=${currentCoin}&interval=${currentTf}`);
          const data = await res.json();
          if (data && data.length > 0) {
            candleSeries.setData(data);
          }
        } catch (err) {}
      }
      if (lastSavedBracket) {
        updateChartLines(lastSavedBracket);
      }
    }

    // LUMINOUS CYAN / LIGHT BLUE ENTRY LINE
    function updateChartLines(bracket) {
      lastSavedBracket = bracket;
      const s = candleSeries || areaSeries;
      if (!s) return;

      if (entryLine) { try { s.removePriceLine(entryLine); } catch(e){} entryLine = null; }
      if (slLine) { try { s.removePriceLine(slLine); } catch(e){} slLine = null; }
      if (tpLine) { try { s.removePriceLine(tpLine); } catch(e){} tpLine = null; }

      if (!bracket || bracket.coin !== currentCoin) return;

      entryLine = s.createPriceLine({
        price: bracket.limit_price || bracket.entry,
        color: 'rgba(0, 180, 216, 0.50)',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dotted,
        axisLabelVisible: true,
        title: 'entry',
      });

      slLine = s.createPriceLine({
        price: bracket.sl,
        color: 'rgba(239, 68, 68, 0.50)',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'cutloss 0.3%',
      });

      tpLine = s.createPriceLine({
        price: bracket.tp,
        color: 'rgba(16, 185, 129, 0.50)',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'target 1.2%',
      });
    }

    async function pollState() {
      try {
        const res = await fetch('/api/state');
        const data = await res.json();

        const p = data.prices[currentCoin];
        const spotEl = document.getElementById('spot_price');
        spotEl.innerText = p ? `$${p.toLocaleString('en-US', {minimumFractionDigits: 1, maximumFractionDigits: 2})}` : '--';

        // LIVE REALTIME TICK STREAMING TO AREA SERIES
        if (currentTf === 'ticks' && areaSeries && p) {
          const nowSec = Math.floor(Date.now() / 1000);
          try {
            areaSeries.update({ time: nowSec, value: p });
          } catch(e) {}
        }

        const mtf = data.mtf[currentCoin];
        const mtfEl = document.getElementById('mtf_tag');
        if (mtf) {
          mtfEl.innerText = `1H: ${mtf.bias} | 15M: ${mtf.bias}`;
          mtfEl.className = `status-tag ${mtf.bias === 'BULLISH' ? 'tag-bull' : (mtf.bias === 'BEARISH' ? 'tag-bear' : 'tag-neutral')}`;
        }

        const acc = data.state.account || {};
        const winrate = acc.total_trades > 0 ? ((acc.wins / acc.total_trades) * 100).toFixed(1) : '0.0';
        document.getElementById('sc_winrate').innerText = `${winrate}%`;
        document.getElementById('sc_wl').innerText = `${acc.wins || 0}W / ${acc.losses || 0}L`;

        // REALIZED & UNREALIZED PNL
        const pnl = data.pnl || {};
        const relUsd = pnl.realized_usd || 0;
        const unUsd = pnl.unrealized_usd || 0;
        const unPct = pnl.unrealized_pct || 0;
        
        const relStr = (relUsd >= 0 ? '+$' : '-$') + Math.abs(relUsd).toFixed(2);
        const unStr = (unUsd >= 0 ? '+$' : '-$') + Math.abs(unUsd).toFixed(2) + ` (${unPct >= 0 ? '+' : ''}${unPct.toFixed(2)}%)`;

        const topRel = document.getElementById('top_realized_pnl');
        if (topRel) {
          topRel.innerText = relStr;
          topRel.style.color = relUsd >= 0 ? 'var(--green)' : 'var(--red)';
        }

        const topUn = document.getElementById('top_unrealized_pnl');
        const scRel = document.getElementById('sc_realized');
        const scUn = document.getElementById('sc_unrealized');
        const cardUn = document.getElementById('card_unrealized');

        if (scRel) {
          scRel.innerText = relStr;
          scRel.style.color = relUsd >= 0 ? 'var(--green)' : 'var(--red)';
        }

        // BANKROLL & INCUBATION TELEMETRY
        const initBank = acc.initial_bankroll || 500.0;
        const curEq = acc.current_equity !== undefined ? acc.current_equity : (initBank + relUsd);
        const eqEl = document.getElementById('sc_equity');
        if (eqEl) {
          eqEl.innerText = `$${curEq.toFixed(2)}`;
          eqEl.style.color = curEq >= initBank ? 'var(--green)' : 'var(--red)';
        }

        const gw = acc.gross_wins || 0;
        const gl = acc.gross_losses || 0;
        const pf = gl > 0 ? (gw / gl).toFixed(2) : (gw > 0 ? '99.9' : '0.00');
        const pfEl = document.getElementById('sc_pf');
        if (pfEl) {
          pfEl.innerText = pf;
          pfEl.style.color = pf >= 1.30 ? 'var(--green)' : (pf > 0 ? 'var(--cyan-deep)' : 'var(--text-dim)');
        }

        const totalTr = acc.total_trades || 0;
        const progEl = document.getElementById('sc_progress');
        if (progEl) progEl.innerText = `${totalTr} / 50 (${((totalTr/50)*100).toFixed(0)}%)`;

        const badgeInc = document.getElementById('sc_inc_badge');
        if (badgeInc) {
          if (totalTr >= 50 && parseFloat(pf) >= 1.30) {
            badgeInc.innerText = 'REAL-READY';
            badgeInc.className = 'status-tag tag-bull';
          } else {
            badgeInc.innerText = `INCUBATION ${totalTr}/50`;
            badgeInc.className = 'status-tag tag-cyan';
          }
        }

        if (acc.started_at) {
          const upSec = Math.floor(Date.now()/1000 - acc.started_at);
          const h = Math.floor(upSec / 3600);
          const m = Math.floor((upSec % 3600) / 60);
          document.getElementById('top_uptime').innerText = `${h}h ${m}m`;
        }

        const pending = data.state.pending_limit;
        const activePos = data.state.active_position;
        const orderStatusBadge = document.getElementById('order_status_badge');

        if (activePos) {
          orderStatusBadge.innerText = 'IN POSITION';
          orderStatusBadge.className = 'status-tag tag-cyan';
          document.getElementById('card_symbol').innerText = `${activePos.coin} ${activePos.dir}`;
          document.getElementById('card_side_badge').innerText = 'FILLED';
          document.getElementById('card_side_badge').className = 'status-tag tag-cyan';
          document.getElementById('card_entry').innerText = `$${(activePos.limit_price || activePos.entry).toLocaleString()}`;
          document.getElementById('card_sl').innerText = `$${activePos.sl.toLocaleString()}`;
          document.getElementById('card_tp').innerText = `$${activePos.tp.toLocaleString()}`;
          document.getElementById('card_ttl').innerText = 'HOLDING TO TARGET';

          const rrVal = activePos.rr_ratio || (activePos.regime_name === 'HIGH_SURGE' ? 4.0 : 2.0);
          const tpPctVal = activePos.win_target_pct ? (activePos.win_target_pct * 100).toFixed(2) : (rrVal === 4.0 ? '1.20' : '0.60');
          const isSurge = activePos.regime_name === 'HIGH_SURGE' || rrVal >= 4.0;
          const rrEl = document.getElementById('card_rr');
          if (rrEl) {
            rrEl.innerText = `1 : ${rrVal.toFixed(1)} (${isSurge ? 'Surge' : 'Normal Vol'})`;
            rrEl.style.color = isSurge ? 'var(--cyan-deep)' : 'var(--blue)';
          }
          const tpLbl = document.getElementById('card_tp_lbl');
          if (tpLbl) tpLbl.innerText = `Win Target (${tpPctVal}%):`;
          
          if (cardUn) {
            cardUn.innerText = unStr;
            cardUn.style.color = unUsd >= 0 ? 'var(--green)' : 'var(--red)';
          }
          if (topUn) {
            topUn.innerText = unStr;
            topUn.style.color = unUsd >= 0 ? 'var(--green)' : 'var(--red)';
          }
          if (scUn) {
            scUn.innerText = unStr;
            scUn.style.color = unUsd >= 0 ? 'var(--green)' : 'var(--red)';
          }
          
          updateChartLines(activePos);
        } else if (pending) {
          orderStatusBadge.innerText = 'PENDING LIMIT';
          orderStatusBadge.className = 'status-tag tag-neutral';
          document.getElementById('card_symbol').innerText = `${pending.coin} ${pending.dir}`;
          document.getElementById('card_side_badge').innerText = 'LIMIT STANDBY';
          document.getElementById('card_side_badge').className = 'status-tag tag-neutral';
          document.getElementById('card_entry').innerText = `$${pending.limit_price.toLocaleString()}`;
          document.getElementById('card_sl').innerText = `$${pending.sl.toLocaleString()}`;
          document.getElementById('card_tp').innerText = `$${pending.tp.toLocaleString()}`;
          
          const rrVal = pending.rr_ratio || (pending.regime_name === 'HIGH_SURGE' ? 4.0 : 2.0);
          const tpPctVal = pending.win_target_pct ? (pending.win_target_pct * 100).toFixed(2) : (rrVal === 4.0 ? '1.20' : '0.60');
          const isSurge = pending.regime_name === 'HIGH_SURGE' || rrVal >= 4.0;
          const rrEl = document.getElementById('card_rr');
          if (rrEl) {
            rrEl.innerText = `1 : ${rrVal.toFixed(1)} (${isSurge ? 'Surge' : 'Normal Vol'})`;
            rrEl.style.color = isSurge ? 'var(--cyan-deep)' : 'var(--blue)';
          }
          const tpLbl = document.getElementById('card_tp_lbl');
          if (tpLbl) tpLbl.innerText = `Win Target (${tpPctVal}%):`;

          if (cardUn) { cardUn.innerText = '-'; cardUn.style.color = 'var(--text-muted)'; }
          if (topUn) { topUn.innerText = '$0.00 (0.0%)'; topUn.style.color = 'var(--text-muted)'; }
          if (scUn) { scUn.innerText = '$0.00'; scUn.style.color = 'var(--text-muted)'; }

          const placedSec = pending.placed_time || Date.now()/1000;
          const ttlRemain = Math.max(0, 1500 - Math.floor(Date.now()/1000 - placedSec));
          const rm = Math.floor(ttlRemain / 60);
          const rs = ttlRemain % 60;
          document.getElementById('card_ttl').innerText = `${rm}m ${rs < 10 ? '0' : ''}${rs}s remain`;
          updateChartLines(pending);
        } else {
          orderStatusBadge.innerText = 'STANDBY';
          orderStatusBadge.className = 'status-tag tag-neutral';
          document.getElementById('card_symbol').innerText = 'NO ACTIVE ORDER';
          document.getElementById('card_side_badge').innerText = 'RADAR SCAN';
          document.getElementById('card_side_badge').className = 'status-tag tag-neutral';
          document.getElementById('card_entry').innerText = '-';
          document.getElementById('card_sl').innerText = '-';
          document.getElementById('card_tp').innerText = '-';
          document.getElementById('card_ttl').innerText = '-';
          
          if (cardUn) { cardUn.innerText = '-'; cardUn.style.color = 'var(--text-muted)'; }
          if (topUn) { topUn.innerText = '$0.00 (0.0%)'; topUn.style.color = 'var(--text-muted)'; }
          if (scUn) { scUn.innerText = '$0.00'; scUn.style.color = 'var(--text-muted)'; }
          
          updateChartLines(null);
        }

        if (data.logs && data.logs.length > 0) {
          const logEl = document.getElementById('log_stream');
          logEl.innerHTML = data.logs.slice(-14).map(l => `<div class="log-item">${l}</div>`).join('');
          logEl.scrollTop = logEl.scrollHeight;
        }

      } catch (err) {}
    }

    function switchCoin(coin) {
      currentCoin = coin;
      document.getElementById('btn_btc').className = `tab-btn ${coin === 'BTC' ? 'active' : ''}`;
      document.getElementById('btn_eth').className = `tab-btn ${coin === 'ETH' ? 'active' : ''}`;
      loadCandles();
      pollState();
    }

    function switchTf(tf) {
      currentTf = tf;
      ['ticks', '1m', '5m', '15m', '1h'].forEach(t => {
        const el = document.getElementById(`tf_${t}`);
        if (el) el.className = `tab-btn ${t === tf ? 'active' : ''}`;
      });
      loadCandles();
    }

    window.addEventListener('load', () => {
      initChart();
      loadCandles();
      pollState();
      setInterval(loadCandles, 8000);
      setInterval(pollState, 3000);
    });
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8899, log_level="warning")
