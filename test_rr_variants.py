#!/usr/bin/env python3
"""
Tes 2 hipotesis:
1. sweep_fade lebih baik dengan RR lebih kecil (1:1.5, 1:2, 1:2.5)?
2. Kalau RR diturunkan, TP lebih cepat kena -> slot lebih cepat bebas -> capture naik
"""
import json, urllib.request, time
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
HL = "https://api.hyperliquid.xyz/info"


def post(p):
    r = urllib.request.Request(HL, data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch(coin, start_ms, end_ms):
    raw = post({"type": "candleSnapshot",
                "req": {"coin": coin, "interval": "5m",
                        "startTime": start_ms, "endTime": end_ms}})
    return [{"t": k["t"], "o": float(k["o"]), "h": float(k["h"]),
             "l": float(k["l"]), "c": float(k["c"])} for k in raw]


def ema_series(v, p):
    if len(v) < p:
        return [None] * len(v)
    k = 2 / (p + 1)
    out = [None] * (p - 1)
    e = sum(v[:p]) / p
    out.append(e)
    for x in v[p:]:
        e = x * k + e * (1 - k)
        out.append(e)
    return out


def atr_series(c, p=14):
    out = [None]
    trs = []
    for i in range(1, len(c)):
        h, l, pc = c[i]["h"], c[i]["l"], c[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        out.append(sum(trs[-p:]) / p if len(trs) >= p else None)
    return out


def align(c5, c15, c1h):
    i15 = i1h = 0
    m15, m1h = [], []
    for c in c5:
        while i15 + 1 < len(c15) and c15[i15 + 1]["t"] <= c["t"]:
            i15 += 1
        while i1h + 1 < len(c1h) and c1h[i1h + 1]["t"] <= c["t"]:
            i1h += 1
        m15.append(i15)
        m1h.append(i1h)
    return m15, m1h


def run_sweep(c5, c15, c1h, P, rr):
    n = len(c5)
    a = atr_series(c5, 14)
    m15, m1h = align(c5, c15, c1h)
    cl15 = [x["c"] for x in c15]
    cl1h = [x["c"] for x in c1h]
    e15 = ema_series(cl15, P.get("htf_ema", 20))
    e1h = ema_series(cl1h, P.get("htf_ema", 20))
    trades = []
    busy = -1
    look = P.get("look", 6)

    for i in range(max(120, look + 3), n - 1):
        if i <= busy:
            continue
        cur = c5[i - 1]
        k15, k1h = m15[i - 1], m1h[i - 1]
        if None in (e15[k15], e1h[k1h], a[i - 1]):
            continue
        up15 = cl15[k15] > e15[k15]
        up1h = cl1h[k1h] > e1h[k1h]
        rng = c5[i - 1 - look:i - 1]
        hh = max(x["h"] for x in rng)
        ll = min(x["l"] for x in rng)
        body = abs(cur["c"] - cur["o"])
        rngc = max(cur["h"] - cur["l"], 1e-9)
        if body / rngc < P.get("min_body", 0):
            continue

        d = None
        if cur["l"] < ll and cur["c"] > ll and up15 and up1h:
            d = "LONG"
        elif cur["h"] > hh and cur["c"] < hh and not up15 and not up1h:
            d = "SHORT"
        if not d:
            continue

        entry = cur["c"]
        dist = a[i - 1] * P["atr_mult"]
        if dist / entry > 0.035 or dist / entry < 0.0015:
            continue
        sl = entry - dist if d == "LONG" else entry + dist
        tp = entry + dist * rr if d == "LONG" else entry - dist * rr

        outcome = None
        bars = 0
        for j in range(i, min(i + P.get("hold", 72) + 1, n)):
            bars = j - i
            h, l = c5[j]["h"], c5[j]["l"]
            if d == "LONG" and l <= sl:
                outcome = "SL"; break
            if d == "SHORT" and h >= sl:
                outcome = "SL"; break
            if d == "LONG" and h >= tp:
                outcome = "TP"; break
            if d == "SHORT" and l <= tp:
                outcome = "TP"; break
        if outcome is None:
            outcome = "TIME"
            exit_p = c5[min(i + P.get("hold", 72), n - 1)]["c"]
        elif outcome == "SL":
            exit_p = sl
        else:
            exit_p = tp

        pnl = (exit_p - entry) if d == "LONG" else (entry - exit_p)
        R = pnl / dist
        fee = (entry + exit_p) * 0.0004 / dist
        trades.append({"R": R - fee, "outcome": outcome, "bars": bars})
        busy = i + max(bars, 1)
    return trades


if __name__ == "__main__":
    CFG = json.load(open("/home/ubuntu/papertrade_backtest/strategy_config.json"))["coins"]
    sweep_coins = {c: cc for c, cc in CFG.items()
                   if any(s["name"] == "sweep_fade" for s in cc["strategies"])}

    print(f"Coin dengan sweep_fade: {len(sweep_coins)}")
    print("Fetching 7 hari data...\n")

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - 7 * 86400_000
    data = {}
    for c in sweep_coins:
        try:
            data[c] = {
                "5m": fetch(c, start_ms, now_ms),
                "15m": fetch(c, start_ms - 86400_000, now_ms),
                "1h": fetch(c, start_ms - 5 * 86400_000, now_ms),
            }
        except Exception as e:
            print(f"  {c} ERR {e}")

    print("=" * 104)
    print("SWEEP_FADE: VARIASI RR (7 hari, semua coin)")
    print("=" * 104)
    print(f"{'RR':<6}{'N':>5}{'WR%':>7}{'PF':>7}{'TotR':>9}{'TP':>5}{'SL':>5}{'TIME':>6}{'AvgBars':>9}{'AvgMin':>8}")
    print("-" * 104)

    for rr in [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]:
        all_tr = []
        for c, cc in sweep_coins.items():
            if c not in data:
                continue
            for s in cc["strategies"]:
                if s["name"] != "sweep_fade":
                    continue
                try:
                    all_tr.extend(run_sweep(data[c]["5m"], data[c]["15m"],
                                            data[c]["1h"], s["params"], rr))
                except Exception:
                    pass
        if not all_tr:
            continue
        n = len(all_tr)
        w = sum(1 for t in all_tr if t["R"] > 0)
        gw = sum(t["R"] for t in all_tr if t["R"] > 0)
        gl = abs(sum(t["R"] for t in all_tr if t["R"] <= 0))
        pf = gw / gl if gl else 99
        tot = sum(t["R"] for t in all_tr)
        tp = sum(1 for t in all_tr if t["outcome"] == "TP")
        sl_ = sum(1 for t in all_tr if t["outcome"] == "SL")
        tm = sum(1 for t in all_tr if t["outcome"] == "TIME")
        ab = sum(t["bars"] for t in all_tr) / n
        print(f"1:{rr:<4}{n:>5}{w/n*100:>7.1f}{pf:>7.2f}{tot:>+9.1f}{tp:>5}{sl_:>5}{tm:>6}{ab:>9.1f}{ab*5:>8.0f}")

    print("\n" + "=" * 104)
    print("PER COIN: RR terbaik")
    print("=" * 104)
    print(f"{'COIN':<7}{'best_rr':>9}{'N':>5}{'WR%':>7}{'PF':>7}{'TotR':>9}{'AvgMin':>8}")
    print("-" * 104)

    for c, cc in sweep_coins.items():
        if c not in data:
            continue
        best = None
        for rr in [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]:
            trs = []
            for s in cc["strategies"]:
                if s["name"] != "sweep_fade":
                    continue
                trs.extend(run_sweep(data[c]["5m"], data[c]["15m"], data[c]["1h"],
                                     s["params"], rr))
            if not trs:
                continue
            tot = sum(t["R"] for t in trs)
            if best is None or tot > best[1]:
                n = len(trs)
                w = sum(1 for t in trs if t["R"] > 0)
                gw = sum(t["R"] for t in trs if t["R"] > 0)
                gl = abs(sum(t["R"] for t in trs if t["R"] <= 0))
                best = (rr, tot, n, w / n * 100, gw / gl if gl else 99,
                        sum(t["bars"] for t in trs) / n * 5)
        if best:
            print(f"{c:<7}1:{best[0]:<7}{best[2]:>5}{best[3]:>7.1f}{best[4]:>7.2f}"
                  f"{best[1]:>+9.1f}{best[5]:>8.0f}")
