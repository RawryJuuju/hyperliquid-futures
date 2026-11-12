#!/usr/bin/env python3
"""
HL Futures Terminal — MEXC-style trading UI
Read-only data endpoints + guarded control endpoint.
Port 8899
"""
import os
import json
import time
import secrets
import urllib.request
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

WIB = timezone(timedelta(hours=7))
BASE_DIR = "/home/ubuntu/papertrade_backtest"
FUT_STATE = os.path.join(BASE_DIR, "fut_state.json")
FUT_LOG = os.path.join(BASE_DIR, "futures_bot.log")
TRADE_LOG = os.path.join(BASE_DIR, "fut_trades.jsonl")
EQUITY_LOG = os.path.join(BASE_DIR, "equity_curve.jsonl")
CFG_FILE = os.path.join(BASE_DIR, "strategy_config.json")
KILL_SWITCH = os.path.join(BASE_DIR, "STOP_TRADING")
STATIC_DIR = os.path.join(BASE_DIR, "static")
HL = "https://api.hyperliquid.xyz"

COINS = ["WLD", "INJ", "ZEC", "NEAR", "HYPE", "ENA", "PUMP"]
CFG_FILE = os.path.join(BASE_DIR, "strategy_config.json")


def _load_coins():
    """Ambil daftar coin dari config supaya selalu sinkron."""
    try:
        c = json.load(open(CFG_FILE))
        ks = list(c.get("coins", {}).keys())
        return ks if ks else COINS
    except Exception:
        return COINS

# control PIN — stored in file, NOT embedded in served page
PIN_FILE = os.path.join(BASE_DIR, ".control_pin")


def get_pin():
    if os.path.exists(PIN_FILE):
        return open(PIN_FILE).read().strip()
    p = secrets.token_urlsafe(9)
    with open(PIN_FILE, "w") as f:
        f.write(p)
    os.chmod(PIN_FILE, 0o600)
    return p


CTRL_PIN = get_pin()

app = FastAPI(title="HL Futures Terminal")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_CACHE = {}


def post_info(payload):
    req = urllib.request.Request(f"{HL}/info", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def mids():
    now = time.time()
    if "_mids" in _CACHE and now - _CACHE["_mids"][0] < 2.5:
        return _CACHE["_mids"][1]
    try:
        d = post_info({"type": "allMids"})
        cl = _load_coins()
        out = {c: float(d[c]) for c in cl if c in d}
        _CACHE["_mids"] = (now, out)
        return out
    except Exception:
        return _CACHE.get("_mids", (0, {}))[1]


def market_stats():
    """24h change + volume per coin dari metaAndAssetCtxs."""
    now = time.time()
    if "_mstats" in _CACHE and now - _CACHE["_mstats"][0] < 20:
        return _CACHE["_mstats"][1]
    try:
        data = post_info({"type": "metaAndAssetCtxs"})
        universe = data[0]["universe"]
        ctxs = data[1]
        out = {}
        for a, c in zip(universe, ctxs):
            name = a["name"]
            if name not in _load_coins():
                continue
            mark = float(c.get("markPx", 0) or 0)
            prev = float(c.get("prevDayPx", 0) or 0)
            vol = float(c.get("dayNtlVlm", 0) or 0)
            chg = ((mark - prev) / prev * 100) if prev else 0.0
            out[name] = {"mark": mark, "prev": prev, "chg24h": round(chg, 2),
                         "vol24h": round(vol, 0)}
        _CACHE["_mstats"] = (now, out)
        return out
    except Exception:
        return _CACHE.get("_mstats", (0, {}))[1]


def candles(coin, interval, limit=1500):
    key = f"c_{coin}_{interval}_{limit}"
    now = time.time()
    ttl = 10 if interval in ("1m", "5m") else 45
    if key in _CACHE and now - _CACHE[key][0] < ttl:
        return _CACHE[key][1]
    step = {"1m": 60_000, "5m": 300_000, "15m": 900_000,
            "1h": 3_600_000, "4h": 14_400_000}[interval]
    start = int(time.time() * 1000) - limit * step
    try:
        raw = post_info({"type": "candleSnapshot",
                         "req": {"coin": coin, "interval": interval, "startTime": start}})
        out = [{"time": int(k["t"] / 1000), "open": float(k["o"]), "high": float(k["h"]),
                "low": float(k["l"]), "close": float(k["c"]), "volume": float(k["v"])}
               for k in raw]
        _CACHE[key] = (now, out)
        return out
    except Exception:
        return _CACHE.get(key, (0, []))[1]


def read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        return json.load(open(path))
    except Exception:
        return default


def read_lines(path, n):
    if not os.path.exists(path):
        return []
    try:
        lines = open(path).read().strip().split("\n")[-n:]
        return [json.loads(l) for l in lines if l.strip()]
    except Exception:
        return []


@app.get("/api/candles")
def api_candles(coin: str = Query("ETH"), interval: str = Query("5m"), limit: int = Query(1500)):
    cl = _load_coins()
    c = coin.upper() if coin.upper() in cl else (cl[0] if cl else "ETH")
    i = interval if interval in ("1m", "5m", "15m", "1h", "4h") else "5m"
    lim = max(50, min(int(limit), 3000))
    return JSONResponse(candles(c, i, lim), headers={"X-Content-Type-Options": "nosniff"})


def _stats_by_tf(stats):
    """Agregasi stats per timeframe dari key 'COIN:strategy:tf'."""
    out = {}
    for key, v in (stats or {}).items():
        parts = key.split(":")
        tf = parts[2] if len(parts) >= 3 else "5m"
        d = out.setdefault(tf, {"n": 0, "w": 0, "l": 0, "R": 0.0, "usd": 0.0})
        d["n"] += v.get("n", 0)
        d["w"] += v.get("w", 0)
        d["l"] += v.get("l", 0)
        d["R"] += v.get("R", 0.0)
        d["usd"] += v.get("usd", 0.0)
    for tf, d in out.items():
        d["R"] = round(d["R"], 2)
        d["usd"] = round(d["usd"], 2)
        d["wr"] = round(d["w"] / d["n"] * 100, 1) if d["n"] else 0.0
    return out


@app.get("/api/state")
def api_state():
    st = read_json(FUT_STATE, {})
    m = mids()
    mstats = market_stats()
    cfg = read_json(CFG_FILE, {})
    coins_cfg = cfg.get("coins", {})
    rm = cfg.get("_risk_model", {})

    open_pos = st.get("open", {})
    positions = []
    triggers = []
    total_unreal = 0.0
    total_risk = 0.0

    for slot, p in open_pos.items():
        coin = p.get("coin", slot.split(":")[0])
        mark = m.get(coin, 0)
        R = 0.0
        usd = 0.0
        if mark:
            R = ((mark - p["entry"]) if p["dir"] == "LONG" else (p["entry"] - mark)) / p["risk_px"]
            usd = R * p.get("risk_usd", 0)
        total_unreal += usd
        total_risk += p.get("risk_pct_equity", 0)

        pos = {
            "slot": slot, "coin": coin, "side": p["dir"], "strategy": p.get("strategy", ""),
            "timeframe": p.get("timeframe", "5m"),
            "size": p.get("size", 0), "entry": p["entry"], "mark": mark,
            "liq": None, "margin": p.get("margin", 0),
            "notional": p.get("notional", 0),
            "leverage": p.get("leverage", 10),
            "unreal_R": round(R, 4), "unreal_usd": round(usd, 2),
            "unreal_pct": round((usd / p.get("margin", 1)) * 100, 2) if p.get("margin") else 0,
            "risk_pct": p.get("risk_pct_equity", 0),
            "opened": datetime.fromtimestamp(p["opened_ts"], tz=WIB).strftime("%H:%M:%S"),
            "hold_bars": round((time.time() - p["opened_ts"]) / 300, 1),
            "be_done": bool(p.get("be_done")),
            "partial_done": bool(p.get("partial_done")),
            "realized_usd": round(p.get("realized_usd", 0), 2),
        }
        positions.append(pos)

        triggers.append({
            "slot": slot, "coin": coin, "side": p["dir"],
            "type": "TP/SL Bracket",
            "sl": p["sl"], "tp": p["tp"],
            "sl_dist_pct": round(abs(p["sl"] - p["entry"]) / p["entry"] * 100, 3),
            "tp_dist_pct": round(abs(p["tp"] - p["entry"]) / p["entry"] * 100, 3),
            "rr": p.get("rr", 0), "status": "active",
        })

    history = read_lines(TRADE_LOG, 60)
    eq_curve = read_lines(EQUITY_LOG, 600)
    logs = []
    if os.path.exists(FUT_LOG):
        try:
            logs = [l.rstrip() for l in open(FUT_LOG).readlines()[-20:]]
        except Exception:
            pass

    running = not os.path.exists(KILL_SWITCH)

    return JSONResponse({
        "account": {
            "equity": round(st.get("equity", 1000.0), 2),
            "initial": st.get("initial_equity", 1000.0),
            "peak": round(st.get("peak_equity", 1000.0), 2),
            "day_pnl": round(st.get("day_pnl", 0.0), 2),
            "unrealized": round(total_unreal, 2),
            "open_risk_pct": round(total_risk, 3),
            "mode": "LIVE",
            "running": running,
        },
        "positions": positions,
        "triggers": triggers,
        "open_orders": [],           # market-entry bot: no resting limits
        "history": history,
        "prices": m,
        "market": mstats,
        "equity_curve": eq_curve,
        "risk_model": {k: v for k, v in rm.items() if not k.startswith("_")},
        "exit_mgmt": {
            "enabled": cfg.get("_exit_management", {}).get("enabled", False),
            "be_at_R": cfg.get("_exit_management", {}).get("be_at_R"),
            "partial_at_R": cfg.get("_exit_management", {}).get("partial_at_R"),
        },
        "cfg": {k: {"cluster": v.get("cluster"), "weight": v.get("weight"),
                    "pf": v.get("combined_pf"), "R": v.get("combined_R"),
                    "strategies": [{"name": s["name"], "tf": s.get("timeframe", "5m"),
                                    "rr": s["params"].get("rr"),
                                    "pf": s.get("oos_pf"), "n": s.get("n"),
                                    "risk_w": s.get("risk_weight")}
                                   for s in v.get("strategies", [])]}
                for k, v in coins_cfg.items()},
        "stats": st.get("stats", {}),
        "stats_by_tf": _stats_by_tf(st.get("stats", {})),
        "logs": logs,
        "server_time": datetime.now(tz=WIB).strftime("%H:%M:%S WIB"),
    }, headers={"X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN"})


@app.post("/api/control")
async def api_control(request: Request):
    """Guarded control: start/stop bot. Requires PIN (not embedded in page)."""
    pin = request.headers.get("x-control-pin", "")
    if not secrets.compare_digest(pin, CTRL_PIN):
        raise HTTPException(status_code=403, detail="invalid pin")
    body = await request.json()
    action = body.get("action")
    if action == "stop":
        open(KILL_SWITCH, "w").write("stop")
        return {"ok": True, "running": False}
    if action == "start":
        if os.path.exists(KILL_SWITCH):
            os.remove(KILL_SWITCH)
        return {"ok": True, "running": True}
    raise HTTPException(status_code=400, detail="unknown action")


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def index():
    p = os.path.join(STATIC_DIR, "about.html")
    if os.path.exists(p):
        return HTMLResponse(open(p).read())
    return HTMLResponse("<h1>About page not found</h1>", status_code=404)


@app.api_route("/terminal", methods=["GET", "HEAD"], response_class=HTMLResponse)
def terminal_page():
    return HTML


@app.api_route("/versions", methods=["GET", "HEAD"], response_class=HTMLResponse)
def versions_page():
    try:
        import importlib
        import versions_gen
        importlib.reload(versions_gen)
        path, _ = versions_gen.render()
        return HTMLResponse(open(path).read())
    except Exception as e:
        return HTMLResponse(f"<pre>versions error: {e}</pre>", status_code=500)


@app.api_route("/calendar", methods=["GET", "HEAD"], response_class=HTMLResponse)
def calendar_page():
    try:
        import importlib
        import calendar_gen
        importlib.reload(calendar_gen)
        return HTMLResponse(calendar_gen.render())
    except Exception as e:
        return HTMLResponse(f"<h1>Calendar error</h1><pre>{e}</pre>", status_code=500)


@app.api_route("/about", methods=["GET", "HEAD"])
def about():
    return RedirectResponse(url="/", status_code=301)


HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hyperliquid Futures Terminal</title>
<link rel="icon" type="image/png" sizes="32x32" href="/static/hl-favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/static/hl-favicon-16x16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/static/hl-apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&family=Sora:wght@500;600;700&display=swap" rel="stylesheet">
<script src="/static/lightweight-charts.js"></script>
<style>
:root{
 --bg:#0b0e11; --bg2:#12161c; --panel:#161b22; --panel2:#1c2229;
 --border:#252d38; --border2:#2f3947;
 --txt:#eaecef; --txt2:#8b95a5; --txt3:#5e6776;
 --green:#0ecb81; --green-d:#0a9e65; --red:#f6465d; --red-d:#c9304a;
 --cyan:#22d3ee; --cyan-d:#0891b2;
 --yellow:#f0b90b;
 --mono:'JetBrains Mono',monospace; --ui:'Inter',sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--bg);color:var(--txt);font-family:var(--ui);overflow:hidden;font-size:12px;-webkit-font-smoothing:antialiased}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#2a3441;border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:#3a4756}

/* ===== LAYOUT ===== */
.app{display:flex;flex-direction:column;height:100vh}
.topbar{height:48px;background:var(--bg2);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 14px;gap:20px;flex-shrink:0}
.main{flex:1;display:flex;min-height:0;overflow:hidden}
.watch{width:200px;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
.center{flex:1;display:flex;flex-direction:column;min-width:0;min-height:0}
.leftcol{flex:1;display:flex;flex-direction:column;min-width:0;min-height:0;overflow:hidden}
.chartrow{flex:1;display:flex;min-height:0;min-width:0}
.right{width:300px;background:var(--bg2);border-left:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0;overflow-y:auto;height:100%}
.bottom{height:240px;background:var(--bg2);border-top:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0;min-height:80px;overflow:hidden}

/* ===== RESIZE HANDLES ===== */
.hsplit{height:6px;background:var(--border);cursor:row-resize;position:relative;flex-shrink:0;transition:background .12s;z-index:10}
.hsplit:hover,.hsplit.drag{background:var(--cyan)}
.hsplit::after{content:'';position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:44px;height:2px;background:var(--txt3);border-radius:1px;opacity:.55}
.hsplit:hover::after,.hsplit.drag::after{background:#0b0e11;opacity:1}
.vsplit{width:6px;background:var(--border);cursor:col-resize;flex-shrink:0;position:relative;transition:background .12s;z-index:10}
.vsplit:hover,.vsplit.drag{background:var(--cyan)}
.vsplit::after{content:'';position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:2px;height:44px;background:var(--txt3);border-radius:1px;opacity:.55}
.vsplit:hover::after,.vsplit.drag::after{background:#0b0e11;opacity:1}
body.resizing{user-select:none;cursor:inherit}
body.resizing iframe,body.resizing #chart{pointer-events:none}

/* ===== TOPBAR ===== */
.brand{display:flex;align-items:center;gap:8px;font-weight:700;font-size:13px;letter-spacing:-.2px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
.brand .sub{color:var(--txt3);font-size:10px;font-weight:500;margin-left:2px}
.tb-sep{width:1px;height:20px;background:var(--border)}
.tb-metrics{display:flex;gap:22px;margin-left:auto}
.tbm{display:flex;flex-direction:column;align-items:flex-end;gap:1px}
.tbm .l{font-size:9px;color:var(--txt3);text-transform:uppercase;letter-spacing:.5px}
.tbm .v{font-family:var(--mono);font-size:13px;font-weight:600}
.pill{font-family:'Sora',var(--ui);font-size:10px;font-weight:600;padding:4px 11px;border-radius:6px;border:1px solid transparent;letter-spacing:.04em;text-transform:uppercase;transition:.18s}
.pill:hover{filter:brightness(1.25)}
.chipbar{display:flex;align-items:center;gap:7px;margin-left:2px}
a.pill{display:inline-flex;align-items:center;gap:4px}
.p-green{background:rgba(14,203,129,.12);color:var(--green);border-color:rgba(14,203,129,.3)}
.p-red{background:rgba(246,70,93,.12);color:var(--red);border-color:rgba(246,70,93,.3)}
.p-grey{background:rgba(139,149,165,.1);color:var(--txt2);border-color:var(--border2)}
.p-cyan{background:rgba(34,211,238,.1);color:var(--cyan);border-color:rgba(34,211,238,.3)}

/* ===== WATCHLIST ===== */
.whead{padding:9px 12px;font-size:10px;color:var(--txt3);text-transform:uppercase;letter-spacing:.6px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between}
.wlist{flex:1;overflow-y:auto}
.witem{display:grid;grid-template-columns:1fr auto;gap:2px 8px;padding:7px 12px;cursor:pointer;border-left:2px solid transparent;transition:.12s}
.witem:hover{background:var(--panel)}
.witem.on{background:var(--panel);border-left-color:var(--cyan)}
.witem .c{font-weight:600;font-size:12px}
.witem .cl{font-size:9px;color:var(--txt3);margin-left:4px;font-weight:500}
.witem .p{font-family:var(--mono);font-size:11px;text-align:right}
.witem .ch{font-family:var(--mono);font-size:9px;text-align:right}
.up{color:var(--green)} .down{color:var(--red)} .flat{color:var(--txt2)}

/* ===== CHART AREA ===== */
.ctools{height:38px;display:flex;align-items:center;gap:8px;padding:0 12px;border-bottom:1px solid var(--border);background:var(--bg2)}
.sym{font-weight:700;font-size:14px}
.sym .px{font-family:var(--mono);font-size:13px;margin-left:8px}
.sym .chg{font-family:var(--mono);font-size:11px;margin-left:6px}
.tfs{display:flex;gap:1px;margin-left:8px}
.tf{background:none;border:none;color:var(--txt2);padding:4px 8px;font-size:11px;font-weight:600;border-radius:3px;cursor:pointer;font-family:var(--mono)}
.tf:hover{color:var(--txt);background:var(--panel2)}
.tf.on{color:var(--cyan);background:rgba(34,211,238,.1)}
.ctools-right{margin-left:auto;display:flex;gap:6px;align-items:center}
.chtoggle{background:var(--panel);border:1px solid var(--border);color:var(--txt2);padding:3px 8px;font-size:10px;border-radius:3px;cursor:pointer;font-family:var(--mono)}
.chtoggle:hover{border-color:var(--border2);color:var(--txt)}
.chtoggle.on{color:var(--cyan);border-color:rgba(34,211,238,.4);background:rgba(34,211,238,.08)}
.chartwrap{flex:1;position:relative;min-height:0}
#chart{width:100%;height:100%}
.ohlc{position:absolute;top:8px;left:10px;z-index:5;display:flex;gap:12px;font-family:var(--mono);font-size:10px;color:var(--txt2);pointer-events:none;background:rgba(11,14,17,.7);padding:4px 9px;border-radius:3px}
.ohlc b{color:var(--txt)}
@keyframes ctp{0%,100%{opacity:1}50%{opacity:.35}}

/* ===== RIGHT PANEL ===== */
.rp{border-bottom:1px solid var(--border);padding:10px 12px}
.rp-t{font-size:10px;color:var(--txt3);text-transform:uppercase;letter-spacing:.6px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center}
.kv{display:flex;justify-content:space-between;padding:3px 0;font-size:11px}
.kv .k{color:var(--txt2)}
.kv .v{font-family:var(--mono);font-weight:500}
.ctrlrow{display:flex;align-items:center;justify-content:space-between;padding:6px 0}
.ctrlrow .lab{font-size:11px;color:var(--txt2)}
.switch{position:relative;width:38px;height:20px;background:#2a3441;border-radius:10px;cursor:pointer;transition:.2s;border:1px solid var(--border2)}
.switch.on{background:rgba(14,203,129,.3);border-color:var(--green)}
.switch::after{content:'';position:absolute;top:2px;left:2px;width:14px;height:14px;background:#8b95a5;border-radius:50%;transition:.2s}
.switch.on::after{left:20px;background:var(--green);box-shadow:0 0 6px var(--green)}
.riskbar{height:4px;background:#1e2630;border-radius:2px;overflow:hidden;margin-top:6px}
.riskfill{height:100%;background:linear-gradient(90deg,var(--cyan),var(--yellow));transition:width .3s}

/* ===== BOTTOM TABS ===== */
.btabs{height:36px;display:flex;align-items:center;gap:0;border-bottom:1px solid var(--border);padding:0 6px;flex-shrink:0}
.bt{background:none;border:none;color:var(--txt2);padding:0 14px;height:36px;font-size:11px;font-weight:600;cursor:pointer;border-bottom:2px solid transparent;position:relative;transition:.12s}
.bt:hover{color:var(--txt)}
.bt.on{color:var(--cyan);border-bottom-color:var(--cyan)}
.bt .cnt{font-family:var(--mono);font-size:9px;margin-left:5px;padding:1px 5px;border-radius:8px;background:var(--panel2);color:var(--txt2)}
.bt.on .cnt{background:rgba(34,211,238,.15);color:var(--cyan)}
.btbody{flex:1;overflow:auto;min-height:0}
.tbl{width:100%;border-collapse:collapse;font-size:11px}
.tbl th{position:sticky;top:0;background:var(--bg2);color:var(--txt3);font-weight:500;font-size:9px;text-transform:uppercase;letter-spacing:.5px;text-align:right;padding:7px 10px;border-bottom:1px solid var(--border);white-space:nowrap;z-index:2}
.tbl th:first-child,.tbl td:first-child{text-align:left}
.tbl td{padding:7px 10px;text-align:right;border-bottom:1px solid rgba(37,45,56,.5);font-family:var(--mono);white-space:nowrap}
.tbl tbody tr:hover{background:var(--panel)}
.tbl tbody tr.clickrow{cursor:pointer}
.tbl tbody tr.clickrow:hover{background:rgba(34,211,238,.07);box-shadow:inset 2px 0 0 var(--cyan)}
.tbl .coin{font-family:var(--ui);font-weight:600}
.tbl .strat{font-family:var(--ui);font-size:10px;color:var(--txt2)}
.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--txt3);gap:6px}
.empty svg{opacity:.3}
.empty .t{font-size:11px}
.tag{font-family:var(--ui);font-size:9px;font-weight:600;padding:2px 6px;border-radius:3px}
.t-long{background:rgba(14,203,129,.12);color:var(--green)}
.t-short{background:rgba(246,70,93,.12);color:var(--red)}
.t-neu{background:var(--panel2);color:var(--txt2)}
.t-cyan{background:rgba(34,211,238,.12);color:var(--cyan)}

.toast{position:fixed;bottom:20px;right:20px;background:var(--panel);border:1px solid var(--border2);border-left:3px solid var(--cyan);padding:10px 14px;border-radius:4px;font-size:11px;z-index:100;opacity:0;transform:translateY(10px);transition:.2s;pointer-events:none}
.toast.show{opacity:1;transform:translateY(0)}
</style></head><body>
<div class="app">

<!-- TOPBAR -->
<div class="topbar">
  <div class="brand"><div class="dot" id="statusDot"></div>HYPERLIQUID FUTURES<span class="sub">TERMINAL</span></div>
  <div class="tb-sep"></div>
  <div class="chipbar">
    <span class="pill p-green" id="modePill">LIVE</span>
    <a href="/versions" class="pill p-grey" title="Versions">VERSIONS</a>
    <a href="/calendar" class="pill p-grey" title="PnL Calendar">PNL CALENDAR</a>
    <a href="/" class="pill p-cyan" title="About">ABOUT ↗</a>
  </div>
  <div class="tb-metrics">
    <div class="tbm"><span class="l">Equity</span><span class="v" id="mEquity">$1,000.00</span></div>
    <div class="tbm"><span class="l">Unrealized</span><span class="v" id="mUnreal">$0.00</span></div>
    <div class="tbm"><span class="l">Day PnL</span><span class="v" id="mDay">$0.00</span></div>
    <div class="tbm"><span class="l">Open Risk</span><span class="v" id="mRisk">0.00%</span></div>
    <div class="tbm"><span class="l">Positions</span><span class="v" id="mPos">0</span></div>
  </div>
</div>

<!-- MAIN -->
<div class="main">

  <div class="leftcol">

    <!-- ROW: watchlist | chart -->
    <div class="chartrow">

      <div class="watch" id="watchPanel">
        <div class="whead"><span>Markets</span><span id="wCount">0</span></div>
        <div class="wlist" id="wlist"></div>
      </div>

      <div class="vsplit" id="splitL"></div>

      <div class="center">
        <div class="ctools">
          <span class="sym" id="symName">—</span>
          <span class="sym"><span class="px" id="symPx">—</span><span class="chg" id="symChg"></span></span>
          <div class="tfs" id="tfs">
            <button class="tf" data-tf="1m">1m</button>
            <button class="tf on" data-tf="5m">5m</button>
            <button class="tf" data-tf="15m">15m</button>
            <button class="tf" data-tf="1h">1h</button>
            <button class="tf" data-tf="4h">4h</button>
          </div>
          <div class="ctools-right">
            <button class="chtoggle on" id="tgVol">VOL</button>
            <button class="chtoggle" id="tgLines">POS</button>
            <button class="chtoggle" id="tgReset">RESET</button>
            <button class="chtoggle" id="tgMax">MAX</button>
          </div>
        </div>
        <div class="chartwrap">
          <div class="ohlc">
            <span>O <b id="oO">—</b></span><span>H <b id="oH">—</b></span>
            <span>L <b id="oL">—</b></span><span>C <b id="oC">—</b></span>
            <span>V <b id="oV">—</b></span>
          </div>
          <div id="chart"></div>
        </div>
      </div>

    </div><!-- /chartrow -->

    <div class="hsplit" id="splitB"></div>

    <div class="bottom" id="bottomPanel">
      <div class="btabs" id="btabs">
        <button class="bt on" data-tab="positions">Positions<span class="cnt" id="cPos">0</span></button>
        <button class="bt" data-tab="orders">Open Orders<span class="cnt" id="cOrd">0</span></button>
        <button class="bt" data-tab="triggers">Trigger Orders<span class="cnt" id="cTrg">0</span></button>
        <button class="bt" data-tab="tpsl">TP / SL<span class="cnt" id="cTp">0</span></button>
        <button class="bt" data-tab="history">Order History<span class="cnt" id="cHis">0</span></button>
      </div>
      <div class="btbody" id="btbody"></div>
    </div>

  </div><!-- /leftcol -->

  <div class="vsplit" id="splitR"></div>

  <!-- RIGHT SIDEBAR (full height) -->
  <div class="right" id="rightPanel">
    <div class="rp">
      <div class="rp-t">Account</div>
      <div class="kv"><span class="k">Equity</span><span class="v" id="accEquity">$—</span></div>
      <div class="kv"><span class="k">Total PnL</span><span class="v" id="accTotalPnl">—</span></div>
      <div class="kv"><span class="k">Return</span><span class="v" id="accReturn">—</span></div>
    </div>
    <div class="rp">
      <div class="rp-t">Margin &amp; Exposure</div>
      <div class="kv"><span class="k">Margin used</span><span class="v" id="mgUsed">$—</span></div>
      <div class="kv"><span class="k">Margin / equity</span><span class="v" id="mgPct">—</span></div>
      <div class="kv"><span class="k">Free margin</span><span class="v" id="mgFree">$—</span></div>
      <div class="kv"><span class="k">Open positions</span><span class="v" id="mgPos">0</span></div>
    </div>
    <div class="rp">
      <div class="rp-t">Trade Stats</div>
      <div class="kv"><span class="k">Closed trades</span><span class="v" id="tsClosed">0</span></div>
      <div class="kv"><span class="k">Win / Loss</span><span class="v" id="tsWL">0 / 0</span></div>
      <div class="kv"><span class="k">Win rate</span><span class="v" id="tsWR">—</span></div>
      <div class="kv"><span class="k">Realized R</span><span class="v" id="tsR">—</span></div>
      <div class="kv"><span class="k">Realized PnL</span><span class="v" id="tsPnl">—</span></div>
      <div class="kv"><span class="k">Profit factor</span><span class="v" id="tsPF">—</span></div>
      <div class="kv"><span class="k">Unrealized</span><span class="v" id="tsUnreal">—</span></div>
    </div>
    <div class="rp">
      <div class="rp-t">Equity Curve <span id="eqTag" style="font-size:9px;color:var(--txt3)"></span></div>
      <div id="eqChart" style="height:78px"></div>
    </div>
    <div class="rp">
      <div class="rp-t">Per-Timeframe <span id="tfStatsTag" style="font-size:9px;color:var(--txt3)"></span></div>
      <div id="tfStats"></div>
    </div>
    <div class="rp">
      <div class="rp-t">Risk Model</div>
      <div class="kv"><span class="k">Base risk / trade</span><span class="v" id="rBase">—</span></div>
      <div class="kv"><span class="k">Max open risk</span><span class="v" id="rMax">—</span></div>
      <div class="kv"><span class="k">Daily cap</span><span class="v" id="rDay">—</span></div>
      <div class="kv"><span class="k">Weekly cap</span><span class="v" id="rWeek">—</span></div>
      <div class="kv"><span class="k">DD throttle</span><span class="v" id="rDD">—</span></div>
      <div style="margin-top:6px;font-size:9px;color:var(--txt3)">Open risk usage</div>
      <div class="riskbar"><div class="riskfill" id="riskFill" style="width:0%"></div></div>
    </div>
    <div class="rp" style="flex:1;display:flex;flex-direction:column;min-height:120px">
      <div class="rp-t">Event Log</div>
      <div id="logs" style="flex:1;overflow-y:auto;font-family:var(--mono);font-size:9.5px;line-height:1.7;color:var(--txt2)"></div>
    </div>
  </div>

</div>
</div><!-- /app -->

<div class="toast" id="toast"></div>

<script>
const CTRL='';
let COINS=[];   // populated from API, synced with config
let coin='', tf='5m', chart, cs, vs, lines=[], showVol=true, showLines=true;
let lastData=null, tab='positions', prevPrices={};

/* ---------- INIT ---------- */
function initWatch(){
  const el = document.getElementById('wlist');
  if (!COINS.length) { el.innerHTML = '<div style="padding:14px;color:var(--txt3);font-size:11px">loading…</div>'; return; }
  el.innerHTML=COINS.map(c=>`
    <div class="witem${c===coin?' on':''}" id="w_${c}" onclick="setCoin('${c}')">
      <div><span class="c">${c}</span><span class="cl">USDT</span></div>
      <div class="p" id="wp_${c}">—</div>
      <div></div>
      <div class="ch flat" id="wc_${c}">—</div>
    </div>`).join('');
  document.getElementById('wCount').textContent=COINS.length;
}

/* sync coin list from API, then set default coin */
function syncCoins(d){
  const cfgCoins = Object.keys(d.cfg||{});
  if (!cfgCoins.length) return;
  const changed = cfgCoins.length !== COINS.length || cfgCoins.some((c,i)=>COINS[i]!==c);
  if (!changed) return;
  COINS = cfgCoins;
  // only pick a coin on first load; never override user selection
  if (!coin || !COINS.includes(coin)) {
    coin = COINS[0];
    loadCandles();
  }
  initWatch();
  document.getElementById('symName').textContent = coin+'/USDT';
}

function initChart(){
  const el=document.getElementById('chart');
  chart=LightweightCharts.createChart(el,{
    width:el.clientWidth,height:el.clientHeight,
    layout:{background:{color:'#0b0e11'},textColor:'#5e6776',fontFamily:"'JetBrains Mono',monospace",fontSize:10},
    grid:{vertLines:{color:'#151b23',style:3},horzLines:{color:'#151b23',style:3}},
    crosshair:{mode:LightweightCharts.CrosshairMode.Normal,
      vertLine:{color:'#3a4756',width:1,style:3,labelBackgroundColor:'#1c2229'},
      horzLine:{color:'#3a4756',width:1,style:3,labelBackgroundColor:'#1c2229'}},
    rightPriceScale:{
      borderColor:'#252d38',
      scaleMargins:{top:0.08,bottom:showVol?0.22:0.08},
      entireTextOnly:false,
      ticksVisible:true,
      minimumWidth:72,
    },
    timeScale:{borderColor:'#252d38',timeVisible:true,secondsVisible:false,rightOffset:5,barSpacing:5,fixLeftEdge:false,fixRightEdge:false},
    handleScroll:true,handleScale:true,
  });
  cs=chart.addCandlestickSeries({
    upColor:'#0ecb81',downColor:'#f6465d',borderVisible:false,
    wickUpColor:'#0ecb81',wickDownColor:'#f6465d',
  });
  vs=chart.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'vol',scaleMargins:{top:0.78,bottom:0}});
  chart.priceScale('vol').applyOptions({scaleMargins:{top:0.78,bottom:0}});

  chart.subscribeCrosshairMove(p=>{
    if(!p.time)return;
    const d=p.seriesData.get(cs); if(!d)return;
    const v=p.seriesData.get(vs);
    document.getElementById('oO').textContent=fmt(d.open);
    document.getElementById('oH').textContent=fmt(d.high);
    document.getElementById('oL').textContent=fmt(d.low);
    document.getElementById('oC').textContent=fmt(d.close);
    document.getElementById('oV').textContent=v?fmtVol(v.value):'—';
  });
  window.addEventListener('resize',()=>chart.resize(el.clientWidth,el.clientHeight));
}

function fmt(n){ if(n===undefined||n===null)return '—';
  if(n>=1000)return n.toFixed(2); if(n>=1)return n.toFixed(4); return n.toFixed(6); }
function fmtVol(v){ if(v>=1e9)return (v/1e9).toFixed(2)+'B'; if(v>=1e6)return (v/1e6).toFixed(2)+'M'; if(v>=1e3)return (v/1e3).toFixed(1)+'K'; return v.toFixed(1); }

async function loadCandles(){
  try{
    if(!coin) return false;   // wait until coin list synced
    const lim=3000;
    const r=await fetch(`/api/candles?coin=${coin}&interval=${tf}&limit=${lim}`);
    const d=await r.json();
    if(d&&d.length){
      cs.setData(d);
      vs.setData(d.map(x=>({time:x.time,value:x.volume||0,
        color:x.close>=x.open?'rgba(14,203,129,.4)':'rgba(246,70,93,.4)'})));
      if(!chart._firstLoad){ chart.timeScale().fitContent(); chart._firstLoad=true; }
    }
    return true;
  }catch(e){ return false; }
}

/* ---------- POSITION LINES + HISTORY MARKERS ---------- */
let markers=[];

function drawLines(){
  lines.forEach(l=>{try{cs.removePriceLine(l)}catch(e){}}); lines=[];
  if(!showLines||!lastData) return;

  (lastData.positions||[]).filter(p=>p.coin===coin).forEach(p=>{
    lines.push(cs.createPriceLine({price:p.entry,color:'rgba(34,211,238,.6)',lineWidth:1,
      lineStyle:LightweightCharts.LineStyle.Dotted,axisLabelVisible:true,title:'ENTRY'}));
    const tp=lastData.triggers.find(t=>t.slot===p.slot);
    if(tp){
      lines.push(cs.createPriceLine({price:tp.tp,color:'rgba(14,203,129,.55)',lineWidth:1,
        lineStyle:LightweightCharts.LineStyle.Dashed,axisLabelVisible:true,title:'TP'}));
      lines.push(cs.createPriceLine({price:tp.sl,color:'rgba(246,70,93,.55)',lineWidth:1,
        lineStyle:LightweightCharts.LineStyle.Dashed,axisLabelVisible:true,title:'SL'}));
    }
  });
}

/* re-fit scale without clearing positions */
function refitScale(){
  if(!chart)return;
  chart.priceScale('right').applyOptions({autoScale:true});
  chart.timeScale().fitContent();
}

/* ---------- RENDER ---------- */
function money(n,dec=2){
  const s=n>=0?'+':'-'; return s+'$'+Math.abs(n).toLocaleString('en-US',{minimumFractionDigits:dec,maximumFractionDigits:dec});
}
function pct(n){ return (n>=0?'+':'')+n.toFixed(2)+'%'; }

function render(d){
  lastData=d;
  syncCoins(d);
  const a=d.account;

  // topbar — equity live = realized + unrealized
  const liveEquity = a.equity + (a.unrealized || 0);
  const eqEl=document.getElementById('mEquity');
  eqEl.textContent='$'+liveEquity.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  eqEl.style.color=liveEquity>=a.initial?'var(--green)':'var(--red)';

  const uEl=document.getElementById('mUnreal');
  uEl.textContent=money(a.unrealized);
  uEl.style.color=a.unrealized>=0?'var(--green)':'var(--red)';

  const dEl=document.getElementById('mDay');
  dEl.textContent=money(a.day_pnl);
  dEl.style.color=a.day_pnl>=0?'var(--green)':'var(--red)';

  document.getElementById('mRisk').textContent=a.open_risk_pct.toFixed(2)+'%';
  document.getElementById('mPos').textContent=d.positions.length;

  // ===== RIGHT PANEL: ACCOUNT / MARGIN / TRADE STATS =====
  const startEq = a.initial || 1000;
  const peakEq  = a.peak || startEq;
  const totalPnl = a.equity - startEq;
  const retPct = (a.equity/startEq - 1) * 100;
  const ddPct = ((a.equity - peakEq) / peakEq) * 100;

  const setKV = (id, txt, val) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = txt;
    if (val !== undefined) el.style.color = val >= 0 ? 'var(--green)' : 'var(--red)';
  };

  setKV('accEquity', '$'+liveEquity.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}), liveEquity-startEq);
  setKV('accTotalPnl', money(liveEquity-startEq), liveEquity-startEq);
  const liveRetPct = (liveEquity/startEq - 1) * 100;
  setKV('accReturn', (liveRetPct>=0?'+':'')+liveRetPct.toFixed(2)+'%', liveRetPct);

  // margin and exposure
  let marginUsed=0, notionalSum=0;
  (d.positions||[]).forEach(p=>{
    marginUsed += p.margin||0;
    notionalSum += p.notional || (p.size*p.mark) || 0;
  });
  const mgPct = a.equity ? (marginUsed/a.equity*100) : 0;
  const freeMargin = a.equity - marginUsed;
  setKV('mgUsed','$'+marginUsed.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}));
  setKV('mgPct', mgPct.toFixed(1)+'%');
  setKV('mgFree','$'+freeMargin.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}));
  setKV('mgPos', d.positions.length);

  // trade stats from history + stats
  const hist = d.history||[];
  const st = d.stats||{};
  let closed=0, wins=0, losses=0, Rsum=0, usdSum=0;
  Object.values(st).forEach(s=>{
    closed += s.n||0; wins += s.w||0; losses += s.l||0;
    Rsum += s.R||0; usdSum += s.usd||0;
  });
  // fallback to history when stats empty
  if (!closed && hist.length) {
    closed = hist.length;
    hist.forEach(h=>{
      Rsum += h.R||0; usdSum += h.usd||0;
      if ((h.usd||0) > 0) wins++; else losses++;
    });
  }
  const wr = closed ? (wins/closed*100) : 0;
  setKV('tsClosed', closed);
  setKV('tsWL', wins+' / '+losses);
  setKV('tsWR', closed ? wr.toFixed(1)+'%' : '—');
  setKV('tsR', (Rsum>=0?'+':'')+Rsum.toFixed(2)+'R', Rsum);
  setKV('tsPnl', money(usdSum), usdSum);
  // profit factor from history
  let gw=0, gl=0;
  hist.forEach(h=>{ const v=h.usd||0; if(v>0) gw+=v; else gl+=Math.abs(v); });
  setKV('tsPF', gl>0 ? (gw/gl).toFixed(2) : (gw>0?'∞':'—'));
  setKV('tsUnreal', money(a.unrealized), a.unrealized);

  document.getElementById('statusDot').style.background=a.running?'var(--green)':'var(--red)';
  const mp=document.getElementById('modePill');
  if(mp){ mp.textContent=a.running?'LIVE':'STOPPED';
    mp.className='pill '+(a.running?'p-green':'p-red'); }

  // watchlist with real 24h change
  COINS.forEach(c=>{
    const mkt=(d.market||{})[c]||{};
    const p=d.prices[c]||mkt.mark||0;
    const ch=mkt.chg24h||0;
    const pe=document.getElementById('wp_'+c), ce=document.getElementById('wc_'+c);
    if(pe)pe.textContent=fmt(p);
    if(ce){ce.textContent=pct(ch);ce.className='ch '+(ch>0.01?'up':ch<-0.01?'down':'flat');}
  });

  // symbol header
  document.getElementById('symName').textContent=coin+'/USDT';
  const sp=d.prices[coin]||0;
  document.getElementById('symPx').textContent=fmt(sp);
  const pos=d.positions.find(x=>x.coin===coin);
  const chEl=document.getElementById('symChg');
  if(pos){
    chEl.textContent=(pos.unreal_R>=0?'+':'')+pos.unreal_R.toFixed(2)+'R';
    chEl.style.color=pos.unreal_R>=0?'var(--green)':'var(--red)';
  } else { chEl.textContent=''; }

  // equity curve
  const eqChartEl = document.getElementById('eqChart');
  if (eqChartEl && d.equity_curve && d.equity_curve.length) {
    if (!window._eqChart) {
      window._eqChart = LightweightCharts.createChart(eqChartEl, {
        width: eqChartEl.clientWidth, height: 78,
        layout:{background:{color:'#0d0f12'}, textColor:'#5a626d',
                fontFamily:"'JetBrains Mono',monospace", fontSize:9},
        grid:{vertLines:{color:'#151b23'}, horzLines:{color:'#151b23'}},
        rightPriceScale:{borderColor:'#1d2228', scaleMargins:{top:.15,bottom:.15}},
        timeScale:{borderColor:'#1d2228', timeVisible:true, secondsVisible:false, visible:false},
        handleScroll:false, handleScale:false, crosshair:{mode:2},
      });
      window._eqSeries = window._eqChart.addAreaSeries({
        lineColor:'#5eead4', topColor:'rgba(94,234,212,.28)',
        bottomColor:'rgba(94,234,212,.01)', lineWidth:2,
        priceLineVisible:false, lastValueVisible:true,
      });
    }
    const seen = {};
    const pts = d.equity_curve
      .map(x => ({ time: Math.floor(new Date(x.t).getTime()/1000), value: x.equity }))
      .filter(p => { if (seen[p.time]) return false; seen[p.time]=1; return true; })
      .sort((a,b)=>a.time-b.time);
    window._eqSeries.setData(pts);
    const tag = document.getElementById('eqTag');
    if (tag) tag.textContent = pts.length ? pts.length+' pts' : '';
    window._eqChart.timeScale().fitContent();
  }

  // per-timeframe stats
  const tfBox = document.getElementById('tfStats');
  const byTf = d.stats_by_tf || {};
  if (tfBox) {
    const order = ['5m','15m','1h'];
    const rows = order.filter(t => byTf[t]).map(t => {
      const s = byTf[t];
      const col = s.R >= 0 ? 'var(--green)' : 'var(--red)';
      return `<div class="kv"><span class="k">${t}</span>
        <span class="v" style="color:${col}">${s.R>=0?'+':''}${s.R.toFixed(1)}R · ${s.n}t · ${s.wr}%</span></div>`;
    });
    tfBox.innerHTML = rows.length ? rows.join('') :
      '<div style="font-size:10px;color:var(--txt3)">no closed trades yet</div>';
    const tag = document.getElementById('tfStatsTag');
    if (tag) tag.textContent = rows.length ? 'live' : '';
  }

  // risk model
  const rm=d.risk_model||{};
  document.getElementById('rBase').textContent=(rm.base_risk_pct||0)+'%';
  document.getElementById('rMax').textContent=(rm.max_total_open_risk_pct||0)+'%';
  document.getElementById('rDay').textContent='-'+(rm.daily_loss_cap_pct||0)+'%';
  document.getElementById('rWeek').textContent='-'+(rm.weekly_loss_cap_pct||0)+'%';
  document.getElementById('rDD').textContent=(rm.reduce_after_dd_pct||0)+'% → ×'+(rm.reduce_factor||0);
  const usage=Math.min(100,(a.open_risk_pct/(rm.max_total_open_risk_pct||1))*100);
  document.getElementById('riskFill').style.width=usage+'%';

  // counts
  document.getElementById('cPos').textContent=d.positions.length;
  document.getElementById('cOrd').textContent=d.open_orders.length;
  document.getElementById('cTrg').textContent=d.triggers.length;
  document.getElementById('cTp').textContent=d.triggers.length;
  document.getElementById('cHis').textContent=d.history.length;

  // logs
  const le=document.getElementById('logs');
  if(d.logs&&d.logs.length){
    le.innerHTML=d.logs.map(l=>{
      const esc=l.replace(/</g,'&lt;');
      const col=/TP|🎯/.test(l)?'var(--green)':/SL|🛑/.test(l)?'var(--red)':/SIGNAL|🔔/.test(l)?'var(--cyan)':'var(--txt2)';
      return `<div style="color:${col}">${esc}</div>`;
    }).join('');
    le.scrollTop=le.scrollHeight;
  }

  drawLines();
  renderTab();
}

/* ---------- TABLES ---------- */
function emptyBox(msg){
  return `<div class="empty"><svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
    <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
    <div class="t">${msg}</div></div>`;
}

function renderTab(){
  const d=lastData; if(!d)return;
  const b=document.getElementById('btbody');

  if(tab==='positions'){
    if(!d.positions.length){ b.innerHTML=emptyBox('No open positions'); return; }
    b.innerHTML=`<table class="tbl"><thead><tr>
      <th>Symbol</th><th>Side</th><th>Strategy</th><th>Size</th><th>Entry</th><th>Mark</th>
      <th>Unrealized</th><th>R</th><th>ROI%</th><th>Risk%</th><th>Margin</th><th>Lev</th><th>Age</th>
    </tr></thead><tbody>${d.positions.map(p=>`
      <tr class="clickrow" onclick="focusCoin('${p.coin}')" title="Click to view ${p.coin} chart">
        <td class="coin">${p.coin}</td>
        <td><span class="tag ${p.side==='LONG'?'t-long':'t-short'}">${p.side}</span></td>
        <td class="strat">${p.strategy} <span class="tag t-neu" style="font-size:8px">${p.timeframe||'5m'}</span>${p.partial_done?' <span class="tag t-cyan" style="font-size:8px">PART</span>':''}${p.be_done?' <span class="tag t-long" style="font-size:8px">BE</span>':''}</td>
        <td>${p.size.toFixed(4)}</td>
        <td>${fmt(p.entry)}</td>
        <td>${fmt(p.mark)}</td>
        <td style="color:${p.unreal_usd>=0?'var(--green)':'var(--red)'}">${money(p.unreal_usd)}</td>
        <td style="color:${p.unreal_R>=0?'var(--green)':'var(--red)'}">${p.unreal_R>=0?'+':''}${p.unreal_R.toFixed(3)}</td>
        <td style="color:${p.unreal_pct>=0?'var(--green)':'var(--red)'}">${pct(p.unreal_pct)}</td>
        <td style="color:var(--txt2)">${p.risk_pct.toFixed(2)}%</td>
        <td>$${p.margin.toFixed(2)}</td>
        <td>${p.leverage}x</td>
        <td style="color:var(--txt2)">${p.opened}</td>
      </tr>`).join('')}</tbody></table>`;
  }

  else if(tab==='orders'){
    b.innerHTML=emptyBox('No open orders. Bot enters via market, not limit.');
  }

  else if(tab==='triggers'){
    if(!d.triggers.length){ b.innerHTML=emptyBox('No active trigger orders'); return; }
    b.innerHTML=`<table class="tbl"><thead><tr>
      <th>Symbol</th><th>Side</th><th>Type</th><th>Trigger Price</th><th>Distance</th><th>Qty</th><th>Status</th>
    </tr></thead><tbody>${d.triggers.map(t=>{
      const p=d.positions.find(x=>x.slot===t.slot)||{};
      return `<tr class="clickrow" onclick="focusCoin('${t.coin}')" title="Click to view ${t.coin} chart">
        <td class="coin">${t.coin}</td>
        <td><span class="tag ${t.side==='LONG'?'t-long':'t-short'}">${t.side}</span></td>
        <td><span class="tag t-cyan">TP/SL</span></td>
        <td style="color:var(--green)">${fmt(t.tp)} <span style="color:var(--txt3)">/</span> <span style="color:var(--red)">${fmt(t.sl)}</span></td>
        <td style="color:var(--txt2)">+${t.tp_dist_pct}% / -${t.sl_dist_pct}%</td>
        <td>${(p.size||0).toFixed(4)}</td>
        <td><span class="tag t-long">ACTIVE</span></td>
      </tr>`}).join('')}</tbody></table>`;
  }

  else if(tab==='tpsl'){
    if(!d.triggers.length){ b.innerHTML=emptyBox('No TP/SL levels yet'); return; }
    b.innerHTML=`<table class="tbl"><thead><tr>
      <th>Symbol</th><th>Entry</th><th>Take Profit</th><th>TP %</th><th>Stop Loss</th><th>SL %</th><th>R:R</th><th>Action</th>
    </tr></thead><tbody>${d.triggers.map(t=>{
      const p=d.positions.find(x=>x.slot===t.slot)||{};
      return `<tr class="clickrow" onclick="focusCoin('${t.coin}')" title="Click to view ${t.coin} chart">
        <td class="coin">${t.coin}</td>
        <td>${fmt(p.entry)}</td>
        <td style="color:var(--green)">${fmt(t.tp)}</td>
        <td style="color:var(--green)">+${t.tp_dist_pct}%</td>
        <td style="color:var(--red)">${fmt(t.sl)}</td>
        <td style="color:var(--red)">-${t.sl_dist_pct}%</td>
        <td style="color:var(--cyan)">1:${t.rr}</td>
        <td><span class="tag t-neu">reduce-only</span></td>
      </tr>`}).join('')}</tbody></table>`;
  }

  else if(tab==='history'){
    if(!d.history.length){ b.innerHTML=emptyBox('No closed trades yet'); return; }
    const rev=[...d.history].reverse();
    b.innerHTML=`<table class="tbl"><thead><tr>
      <th>Time</th><th>Symbol</th><th>Side</th><th>Strategy</th><th>Entry</th><th>Exit</th>
      <th>R</th><th>PnL</th><th>Equity</th><th>Result</th>
    </tr></thead><tbody>${rev.map(h=>`
      <tr class="clickrow" onclick="focusCoin('${h.coin}')" title="Click to view ${h.coin} chart">
        <td style="color:var(--txt2)">${(h.t||'').slice(11,19)}</td>
        <td class="coin">${h.coin}</td>
        <td><span class="tag ${h.dir==='LONG'?'t-long':'t-short'}">${h.dir}</span></td>
        <td class="strat">${h.strategy||''}</td>
        <td>${fmt(h.entry)}</td>
        <td>${fmt(h.exit)}</td>
        <td style="color:${h.R>=0?'var(--green)':'var(--red)'}">${h.R>=0?'+':''}${h.R.toFixed(2)}</td>
        <td style="color:${h.usd>=0?'var(--green)':'var(--red)'}">${money(h.usd)}</td>
        <td>$${(h.equity||0).toFixed(2)}</td>
        <td><span class="tag ${h.kind==='TP'?'t-long':'t-short'}">${h.kind}</span></td>
      </tr>`).join('')}</tbody></table>`;
  }
}

/* ---------- CONTROLS ---------- */
async function toggleBot(){
  const running=lastData?.account?.running;
  const action=running?'stop':'start';
  const pin=prompt('Masukkan control PIN:');
  if(!pin) return;
  try{
    const r=await fetch('/api/control',{method:'POST',
      headers:{'Content-Type':'application/json','X-Control-Pin':pin},
      body:JSON.stringify({action})});
    if(r.status===403){ toast('Invalid PIN'); return; }
    const j=await r.json();
    if(j.ok){ toast(running?'Bot stopped':'Bot started'); poll(); }
  }catch(e){ toast('Failed: '+e.message); }
}

function toast(msg){
  const t=document.getElementById('toast');
  t.textContent=msg; t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),2200);
}

function setCoin(c){
  coin=c;
  COINS.forEach(x=>{
    const e=document.getElementById('w_'+x);
    if(e)e.className='witem'+(x===c?' on':'');
  });
  document.getElementById('symName').textContent=c+'/USDT';
  loadCandles(); poll();
}

/* click table row -> focus chart on that coin */
function focusCoin(c){
  if(!COINS.includes(c))return;
  setCoin(c);
  // scroll chart into view if needed
  document.querySelector('.chartwrap').scrollIntoView({block:'nearest'});
  toast('Chart → '+c+'/USDT');
}

/* reset chart to default, including price scale distorted by distant positions */
function resetChart(){
  // Reset CHART VIEW ONLY. Keep current coin + timeframe.
  showVol=true; showLines=true;

  document.getElementById('tgVol').classList.add('on');
  document.getElementById('tgLines').classList.remove('on');
  if(maxMode)toggleMax();
  try{localStorage.removeItem(LS);}catch(e){}
  document.getElementById('bottomPanel').style.height='';
  document.getElementById('watchPanel').style.width='';
  document.getElementById('rightPanel').style.width='';

  // 1. clear all price lines
  lines.forEach(l=>{try{cs.removePriceLine(l)}catch(e){}}); lines=[];
  try{cs.setMarkers([])}catch(e){}

  // 2. reset volume and margins
  vs.applyOptions({visible:true});
  chart.priceScale('vol').applyOptions({scaleMargins:{top:0.78,bottom:0}});
  chart.priceScale('right').applyOptions({scaleMargins:{top:0.06,bottom:0.24}});

  // 3. FORCE autoscale reset, fixes flattened candles
  chart.priceScale('right').applyOptions({
    autoScale:true,
    scaleMargins:{top:0.06,bottom:0.24},
  });

  // 4. reload current coin/tf data then full fit (fitContent MUST be last)
  setTimeout(()=>{
    loadCandles().then(()=>{
      chart._firstLoad=true;
      chart.timeScale().applyOptions({rightOffset:5});
      chart.timeScale().fitContent();
      chart.priceScale('right').applyOptions({autoScale:true});
      resizeChart();
    });
  },80);

  toast('Chart reset. Scale and zoom restored.');
}

/* ---------- RESIZE ---------- */
const LS='hlterm.layout.v1';

function saveLayout(){
  try{
    localStorage.setItem(LS,JSON.stringify({
      bottom:document.getElementById('bottomPanel').offsetHeight,
      left:document.getElementById('watchPanel').offsetWidth,
      right:document.getElementById('rightPanel').offsetWidth,
    }));
  }catch(e){}
}

function loadLayout(){
  try{
    const j=JSON.parse(localStorage.getItem(LS)||'{}');
    if(j.bottom)document.getElementById('bottomPanel').style.height=j.bottom+'px';
    if(j.left)document.getElementById('watchPanel').style.width=j.left+'px';
    if(j.right)document.getElementById('rightPanel').style.width=j.right+'px';
  }catch(e){}
}

function resizeChart(){
  const el=document.getElementById('chart');
  if(chart&&el)chart.resize(el.clientWidth,el.clientHeight);
}

function dragH(handleId,panelId,invert){
  const h=document.getElementById(handleId), p=document.getElementById(panelId);
  if(!h||!p)return;
  h.addEventListener('mousedown',e=>{
    e.preventDefault();
    const startY=e.clientY, startH=p.offsetHeight;
    h.classList.add('drag'); document.body.classList.add('resizing');
    document.body.style.cursor='row-resize';
    const move=ev=>{
      const dy=invert?(ev.clientY-startY):(startY-ev.clientY);
      let nh=startH+dy;
      const maxH=window.innerHeight-180;
      nh=Math.max(80,Math.min(nh,maxH));
      p.style.height=nh+'px';
      resizeChart();
    };
    const up=()=>{
      h.classList.remove('drag'); document.body.classList.remove('resizing');
      document.body.style.cursor='';
      document.removeEventListener('mousemove',move);
      document.removeEventListener('mouseup',up);
      saveLayout(); resizeChart();
    };
    document.addEventListener('mousemove',move);
    document.addEventListener('mouseup',up);
  });
}

function dragV(handleId,panelId,invert){
  const h=document.getElementById(handleId), p=document.getElementById(panelId);
  if(!h||!p)return;
  h.addEventListener('mousedown',e=>{
    e.preventDefault();
    const startX=e.clientX, startW=p.offsetWidth;
    h.classList.add('drag'); document.body.classList.add('resizing');
    document.body.style.cursor='col-resize';
    const move=ev=>{
      const dx=invert?(startX-ev.clientX):(ev.clientX-startX);
      let nw=startW+dx;
      nw=Math.max(120,Math.min(nw,window.innerWidth*0.45));
      p.style.width=nw+'px';
      resizeChart();
    };
    const up=()=>{
      h.classList.remove('drag'); document.body.classList.remove('resizing');
      document.body.style.cursor='';
      document.removeEventListener('mousemove',move);
      document.removeEventListener('mouseup',up);
      saveLayout(); resizeChart();
    };
    document.addEventListener('mousemove',move);
    document.addEventListener('mouseup',up);
  });
}

function initResize(){
  loadLayout();
  dragH('splitB','bottomPanel',false);  // drag up = bottom bigger
  dragV('splitL','watchPanel',false);   // drag right = watch wider
  dragV('splitR','rightPanel',true);    // drag left = right wider
}

/* ---------- MAX CHART ---------- */
let maxMode=false;
function toggleMax(){
  maxMode=!maxMode;
  const b=document.getElementById('bottomPanel');
  const w=document.getElementById('watchPanel');
  const r=document.getElementById('rightPanel');
  const sB=document.getElementById('splitB');
  const sL=document.getElementById('splitL');
  const sR=document.getElementById('splitR');
  const btn=document.getElementById('tgMax');
  if(maxMode){
    b.style.display='none'; sB.style.display='none';
    w.style.display='none'; sL.style.display='none';
    r.style.display='none'; sR.style.display='none';
    btn.classList.add('on'); btn.textContent='NORM';
  }else{
    b.style.display=''; sB.style.display='';
    w.style.display=''; sL.style.display='';
    r.style.display=''; sR.style.display='';
    btn.classList.remove('on'); btn.textContent='MAX';
    loadLayout();
  }
  setTimeout(resizeChart,60);
}

/* ---------- EVENTS ---------- */
document.getElementById('tfs').addEventListener('click',e=>{
  const b=e.target.closest('.tf'); if(!b)return;
  document.querySelectorAll('.tf').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); tf=b.dataset.tf; loadCandles();
});

document.getElementById('btabs').addEventListener('click',e=>{
  const b=e.target.closest('.bt'); if(!b)return;
  document.querySelectorAll('.bt').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); tab=b.dataset.tab; renderTab();
});

document.getElementById('tgVol').onclick=function(){
  showVol=!showVol; this.classList.toggle('on',showVol);
  vs.applyOptions({visible:showVol});
  chart.priceScale('right').applyOptions({scaleMargins:{top:0.06,bottom:showVol?0.24:0.06}});
};
document.getElementById('tgLines').onclick=function(){
  showLines=!showLines; this.classList.toggle('on',showLines); drawLines();
};
document.getElementById('tgMax').onclick=toggleMax;
document.getElementById('tgReset').onclick=resetChart;

/* keyboard shortcuts */
document.addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT')return;
  if(e.key==='m'||e.key==='M')toggleMax();
  if(e.key==='r'||e.key==='R')resetChart();
});

/* ---------- POLL ---------- */
async function poll(){
  try{
    const r=await fetch('/api/state');
    const d=await r.json();
    render(d);
  }catch(e){}
}

window.addEventListener('load',()=>{
  initWatch(); initChart(); initResize(); loadCandles(); poll();
  setInterval(loadCandles,6000);
  setInterval(poll,2000);
});
</script></body></html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8899, log_level="warning")
