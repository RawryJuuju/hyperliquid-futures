#!/usr/bin/env python3
"""
Multi-strategy research harness — cari metode yang PROFITABLE, apa pun itu.
Test 6 keluarga strategi x parameter grid x 14 koin likuid.
Walk-forward: IS 60d / OOS 60d.
"""
import urllib.request, json, time, itertools
from datetime import datetime, timezone, timedelta

URL = "https://api.hyperliquid.xyz/info"
WIB = timezone(timedelta(hours=7))

# ---------- data ----------
_CACHE = {}

def fetch(coin, interval, days=120):
    key = f"{coin}_{interval}_{days}"
    if key in _CACHE: return _CACHE[key]
    step = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000}[interval]
    n = int(days * 24 * 3600 * 1000 / step)
    now = int(time.time() * 1000)
    p = json.dumps({"type": "candleSnapshot",
                    "req": {"coin": coin, "interval": interval, "startTime": now - n * step}}).encode()
    # retry dengan backoff untuk 429
    for attempt in range(6):
        try:
            r = urllib.request.Request(URL, data=p, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=40) as resp:
                raw = json.loads(resp.read().decode())
            out = [{"t": k["t"], "o": float(k["o"]), "h": float(k["h"]),
                    "l": float(k["l"]), "c": float(k["c"]), "v": float(k["v"])} for k in raw]
            _CACHE[key] = out
            time.sleep(1.2)   # rate-limit friendly
            return out
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(4 * (attempt + 1))
                continue
            raise
        except Exception:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"fetch failed after retries: {coin} {interval}")

# ---------- indicators ----------
def ema_series(v, p):
    if len(v) < p: return [None]*len(v)
    k = 2/(p+1); out = [None]*(p-1)
    e = sum(v[:p])/p; out.append(e)
    for x in v[p:]:
        e = x*k + e*(1-k); out.append(e)
    return out

def sma_series(v, p):
    out = [None]*(p-1)
    for i in range(p-1, len(v)):
        out.append(sum(v[i-p+1:i+1])/p)
    return out

def stdev_series(v, p):
    out = [None]*(p-1)
    for i in range(p-1, len(v)):
        w = v[i-p+1:i+1]; m = sum(w)/p
        out.append((sum((x-m)**2 for x in w)/p) ** 0.5)
    return out

def atr_series(c, p=14):
    out = [None]; trs = []
    for i in range(1, len(c)):
        h, l, pc = c[i]["h"], c[i]["l"], c[i-1]["c"]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
        out.append(sum(trs[-p:])/p if len(trs) >= p else None)
    return out

def rsi_series(v, p=14):
    out = [None]*len(v)
    if len(v) < p+1: return out
    gains = []; losses = []
    for i in range(1, len(v)):
        d = v[i]-v[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains[:p])/p; al = sum(losses[:p])/p
    out[p] = 100 - 100/(1 + (ag/al if al > 0 else 999))
    for i in range(p, len(gains)):
        ag = (ag*(p-1)+gains[i])/p
        al = (al*(p-1)+losses[i])/p
        out[i+1] = 100 - 100/(1 + (ag/al if al > 0 else 999))
    return out

def align(c5, c15, c1h):
    i15 = i1h = 0; m15 = []; m1h = []
    for c in c5:
        while i15+1 < len(c15) and c15[i15+1]["t"] <= c["t"]: i15 += 1
        while i1h+1 < len(c1h) and c1h[i1h+1]["t"] <= c["t"]: i1h += 1
        m15.append(i15); m1h.append(i1h)
    return m15, m1h

# ---------- trade simulator ----------
def simulate(c5, entry, sl, tp, direction, i_fill, max_hold, be_at=None,
             trail_at=None, trail_gap=0.5, partial_at=None, partial_frac=0.5):
    """Return (R, outcome, bars). Conservative: SL checked before TP."""
    risk = abs(entry - sl)
    if risk <= 0: return None
    n = len(c5)
    cur_sl = sl
    realized = 0.0
    rem = 1.0
    partial_done = False

    for j in range(i_fill+1, min(i_fill+max_hold+1, n)):
        bars = j - i_fill
        h, l = c5[j]["h"], c5[j]["l"]
        r_now = (h-entry)/risk if direction == "LONG" else (entry-l)/risk

        if be_at and r_now >= be_at:
            cur_sl = entry

        if trail_at and r_now >= trail_at:
            lock = (entry + risk*(r_now-trail_gap)) if direction == "LONG" else (entry - risk*(r_now-trail_gap))
            cur_sl = max(cur_sl, lock) if direction == "LONG" else min(cur_sl, lock)

        if partial_at and not partial_done and r_now >= partial_at:
            realized += partial_frac * partial_at
            rem = 1 - partial_frac
            partial_done = True

        # stop first (conservative)
        if direction == "LONG" and l <= cur_sl:
            r_exit = (cur_sl - entry)/risk
            realized += rem * r_exit
            kind = "SL" if abs(cur_sl - sl) < 1e-9 else "BE/TRAIL"
            return realized, kind, bars
        if direction == "SHORT" and h >= cur_sl:
            r_exit = (entry - cur_sl)/risk
            realized += rem * r_exit
            kind = "SL" if abs(cur_sl - sl) < 1e-9 else "BE/TRAIL"
            return realized, kind, bars

        if direction == "LONG" and h >= tp:
            realized += rem * ((tp-entry)/risk)
            return realized, "TP", bars
        if direction == "SHORT" and l <= tp:
            realized += rem * ((entry-tp)/risk)
            return realized, "TP", bars

    # time exit
    exit_p = c5[min(i_fill+max_hold, n-1)]["c"]
    r_exit = (exit_p-entry)/risk if direction == "LONG" else (entry-exit_p)/risk
    realized += rem * r_exit
    return realized, "TIME", max_hold

# ---------- strategy families ----------
def strat_sweep_fade(c5, c15, c1h, P):
    n = len(c5); a = atr_series(c5, 14)
    m15, m1h = align(c5, c15, c1h)
    cl15 = [x["c"] for x in c15]; cl1h = [x["c"] for x in c1h]
    e15 = ema_series(cl15, P["htf_ema"]); e1h = ema_series(cl1h, P["htf_ema"])
    trades = []; busy = -1; look = P["look"]

    for i in range(max(120, look+3), n-1):
        if i <= busy: continue
        cur = c5[i-1]; k15, k1h = m15[i-1], m1h[i-1]
        if None in (e15[k15], e1h[k1h], a[i-1]): continue
        up15 = cl15[k15] > e15[k15]; up1h = cl1h[k1h] > e1h[k1h]
        rng = c5[i-1-look:i-1]
        hh = max(x["h"] for x in rng); ll = min(x["l"] for x in rng)
        body = abs(cur["c"]-cur["o"]); rngc = max(cur["h"]-cur["l"], 1e-9)
        if body/rngc < P["min_body"]: continue

        d = None
        if cur["l"] < ll and cur["c"] > ll and up15 and up1h: d = "LONG"
        elif cur["h"] > hh and cur["c"] < hh and not up15 and not up1h: d = "SHORT"
        if not d: continue

        entry = cur["c"]; dist = a[i-1]*P["atr_mult"]
        sl = entry-dist if d == "LONG" else entry+dist
        tp = entry+dist*P["rr"] if d == "LONG" else entry-dist*P["rr"]
        if dist/entry > 0.03: continue

        r = simulate(c5, entry, sl, tp, d, i, P["hold"], P.get("be_at"))
        if not r: continue
        R, kind, bars = r
        fee = (entry+tp)*0.0004/dist
        trades.append({"R": R-fee, "kind": kind, "bars": bars})
        busy = i + bars
    return trades

def strat_breakout(c5, c15, c1h, P):
    n = len(c5); a = atr_series(c5, 14)
    m15, m1h = align(c5, c15, c1h)
    cl15 = [x["c"] for x in c15]; cl1h = [x["c"] for x in c1h]
    e15 = ema_series(cl15, P["htf_ema"]); e1h = ema_series(cl1h, P["htf_ema"])
    trades = []; busy = -1; look = P["look"]

    for i in range(max(120, look+3), n-1):
        if i <= busy: continue
        cur = c5[i-1]; k15, k1h = m15[i-1], m1h[i-1]
        if None in (e15[k15], e1h[k1h], a[i-1]): continue
        up15 = cl15[k15] > e15[k15]; up1h = cl1h[k1h] > e1h[k1h]
        rng = c5[i-1-look:i-1]
        hh = max(x["h"] for x in rng); ll = min(x["l"] for x in rng)
        body = abs(cur["c"]-cur["o"]); rngc = max(cur["h"]-cur["l"], 1e-9)
        if body/rngc < P["min_body"]: continue

        d = None
        if cur["c"] > hh and up15 and up1h: d = "LONG"
        elif cur["c"] < ll and not up15 and not up1h: d = "SHORT"
        if not d: continue

        entry = cur["c"]; dist = a[i-1]*P["atr_mult"]
        sl = entry-dist if d == "LONG" else entry+dist
        tp = entry+dist*P["rr"] if d == "LONG" else entry-dist*P["rr"]
        if dist/entry > 0.03: continue

        r = simulate(c5, entry, sl, tp, d, i, P["hold"], P.get("be_at"))
        if not r: continue
        R, kind, bars = r
        fee = (entry+tp)*0.0004/dist
        trades.append({"R": R-fee, "kind": kind, "bars": bars})
        busy = i + bars
    return trades

def strat_ema_pullback(c5, c15, c1h, P):
    n = len(c5); a = atr_series(c5, 14)
    closes = [x["c"] for x in c5]
    e20 = ema_series(closes, P["ema_fast"])
    e50 = ema_series(closes, P["ema_slow"])
    trades = []; busy = -1

    for i in range(120, n-1):
        if i <= busy: continue
        cur = c5[i-1]
        if None in (e20[i-1], e50[i-1], a[i-1]): continue

        d = None
        # trend: fast above slow, price pulls to fast EMA then closes above
        if e20[i-1] > e50[i-1] and cur["l"] <= e20[i-1] and cur["c"] > e20[i-1]:
            d = "LONG"
        elif e20[i-1] < e50[i-1] and cur["h"] >= e20[i-1] and cur["c"] < e20[i-1]:
            d = "SHORT"
        if not d: continue

        entry = cur["c"]; dist = a[i-1]*P["atr_mult"]
        sl = entry-dist if d == "LONG" else entry+dist
        tp = entry+dist*P["rr"] if d == "LONG" else entry-dist*P["rr"]
        if dist/entry > 0.03: continue

        r = simulate(c5, entry, sl, tp, d, i, P["hold"], P.get("be_at"))
        if not r: continue
        R, kind, bars = r
        fee = (entry+tp)*0.0004/dist
        trades.append({"R": R-fee, "kind": kind, "bars": bars})
        busy = i + bars
    return trades

def strat_bollinger(c5, c15, c1h, P):
    """Mean reversion: fade touches of BB extremes, only in ranging regime."""
    n = len(c5); a = atr_series(c5, 14)
    closes = [x["c"] for x in c5]
    sma = sma_series(closes, P["bb_period"])
    sd = stdev_series(closes, P["bb_period"])
    trades = []; busy = -1

    for i in range(120, n-1):
        if i <= busy: continue
        cur = c5[i-1]
        if None in (sma[i-1], sd[i-1], a[i-1]) or sd[i-1] <= 0: continue
        upper = sma[i-1] + P["bb_k"]*sd[i-1]
        lower = sma[i-1] - P["bb_k"]*sd[i-1]

        # regime filter: ATR must be below median (ranging)
        recent_atr = [x for x in a[max(0,i-60):i] if x]
        if len(recent_atr) < 20: continue
        if a[i-1] > sorted(recent_atr)[len(recent_atr)//2] * P["atr_max_ratio"]: continue

        d = None
        if cur["l"] < lower and cur["c"] > lower: d = "LONG"
        elif cur["h"] > upper and cur["c"] < upper: d = "SHORT"
        if not d: continue

        entry = cur["c"]; dist = a[i-1]*P["atr_mult"]
        sl = entry-dist if d == "LONG" else entry+dist
        tp = entry+dist*P["rr"] if d == "LONG" else entry-dist*P["rr"]

        r = simulate(c5, entry, sl, tp, d, i, P["hold"], P.get("be_at"))
        if not r: continue
        R, kind, bars = r
        fee = (entry+tp)*0.0004/dist
        trades.append({"R": R-fee, "kind": kind, "bars": bars})
        busy = i + bars
    return trades

def strat_rsi_rev(c5, c15, c1h, P):
    """RSI extreme reversal with trend filter."""
    n = len(c5); a = atr_series(c5, 14)
    closes = [x["c"] for x in c5]
    rsi = rsi_series(closes, P["rsi_period"])
    e200 = ema_series(closes, P["ema_trend"])
    trades = []; busy = -1

    for i in range(220, n-1):
        if i <= busy: continue
        cur = c5[i-1]
        if None in (rsi[i-1], e200[i-1], a[i-1]): continue

        d = None
        # only trade WITH the higher trend
        if rsi[i-1] < P["rsi_lo"] and cur["c"] > e200[i-1]: d = "LONG"
        elif rsi[i-1] > P["rsi_hi"] and cur["c"] < e200[i-1]: d = "SHORT"
        if not d: continue

        entry = cur["c"]; dist = a[i-1]*P["atr_mult"]
        sl = entry-dist if d == "LONG" else entry+dist
        tp = entry+dist*P["rr"] if d == "LONG" else entry-dist*P["rr"]

        r = simulate(c5, entry, sl, tp, d, i, P["hold"], P.get("be_at"))
        if not r: continue
        R, kind, bars = r
        fee = (entry+tp)*0.0004/dist
        trades.append({"R": R-fee, "kind": kind, "bars": bars})
        busy = i + bars
    return trades

def strat_donchian(c5, c15, c1h, P):
    """Turtle-style: break of N-bar channel, trail stop."""
    n = len(c5); a = atr_series(c5, 14)
    trades = []; busy = -1; look = P["look"]

    for i in range(max(120, look+3), n-1):
        if i <= busy: continue
        cur = c5[i-1]
        if a[i-1] is None: continue
        rng = c5[i-1-look:i-1]
        hh = max(x["h"] for x in rng); ll = min(x["l"] for x in rng)

        d = None
        if cur["c"] > hh: d = "LONG"
        elif cur["c"] < ll: d = "SHORT"
        if not d: continue

        entry = cur["c"]; dist = a[i-1]*P["atr_mult"]
        sl = entry-dist if d == "LONG" else entry+dist
        tp = entry+dist*P["rr"] if d == "LONG" else entry-dist*P["rr"]

        r = simulate(c5, entry, sl, tp, d, i, P["hold"], P.get("be_at"),
                     trail_at=P.get("trail_at"), trail_gap=P.get("trail_gap", 0.5))
        if not r: continue
        R, kind, bars = r
        fee = (entry+tp)*0.0004/dist
        trades.append({"R": R-fee, "kind": kind, "bars": bars})
        busy = i + bars
    return trades

FAMILIES = {
    "sweep_fade": strat_sweep_fade,
    "breakout": strat_breakout,
    "ema_pullback": strat_ema_pullback,
    "bollinger": strat_bollinger,
    "rsi_rev": strat_rsi_rev,
    "donchian": strat_donchian,
}

# ---------- metrics ----------
def metrics(trades):
    if not trades: return None
    n = len(trades)
    wins = [t for t in trades if t["R"] > 0]
    gw = sum(t["R"] for t in wins)
    gl = abs(sum(t["R"] for t in trades if t["R"] <= 0))
    pf = gw/gl if gl > 0 else (99 if gw > 0 else 0)
    tot = sum(t["R"] for t in trades)
    eq = peak = mdd = 0.0
    for t in trades:
        eq += t["R"]; peak = max(peak, eq); mdd = min(mdd, eq-peak)
    return {"n": n, "wr": len(wins)/n*100, "pf": pf, "totR": tot,
            "mdd": mdd, "avgR": tot/n}
