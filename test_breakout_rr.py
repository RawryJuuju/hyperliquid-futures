#!/usr/bin/env python3
"""Tes RR variants untuk BREAKOUT (strategi yang profit)."""
import json, urllib.request, time
from datetime import datetime, timezone, timedelta

HL = "https://api.hyperliquid.xyz/info"


def post(p):
    r = urllib.request.Request(HL, data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch(coin, s, e):
    raw = post({"type": "candleSnapshot",
                "req": {"coin": coin, "interval": "5m", "startTime": s, "endTime": e}})
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


def run(c5, c15, c1h, P, rr, be_at=None):
    n = len(c5)
    a = atr_series(c5, 14)
    m15, m1h = align(c5, c15, c1h)
    cl15 = [x["c"] for x in c15]
    cl1h = [x["c"] for x in c1h]
    e15 = ema_series(cl15, P.get("htf_ema", 20))
    e1h = ema_series(cl1h, P.get("htf_ema", 20))
    trades = []
    busy = -1
    look = P.get("look", 10)

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
        if cur["c"] > hh and up15 and up1h:
            d = "LONG"
        elif cur["c"] < ll and not up15 and not up1h:
            d = "SHORT"
        if not d:
            continue

        entry = cur["c"]
        dist = a[i - 1] * P["atr_mult"]
        if dist / entry > 0.035 or dist / entry < 0.0015:
            continue
        sl = entry - dist if d == "LONG" else entry + dist
        tp = entry + dist * rr if d == "LONG" else entry - dist * rr

        cur_sl = sl
        outcome = None
        bars = 0
        for j in range(i, min(i + P.get("hold", 72) + 1, n)):
            bars = j - i
            h, l = c5[j]["h"], c5[j]["l"]
            r_now = (h - entry) / dist if d == "LONG" else (entry - l) / dist
            if be_at and r_now >= be_at:
                cur_sl = entry
            if d == "LONG" and l <= cur_sl:
                outcome = "SL" if cur_sl == sl else "BE"; break
            if d == "SHORT" and h >= cur_sl:
                outcome = "SL" if cur_sl == sl else "BE"; break
            if d == "LONG" and h >= tp:
                outcome = "TP"; break
            if d == "SHORT" and l <= tp:
                outcome = "TP"; break
        if outcome is None:
            outcome = "TIME"
            exit_p = c5[min(i + P.get("hold", 72), n - 1)]["c"]
        elif outcome in ("SL", "BE"):
            exit_p = cur_sl
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
    bo = {c: cc for c, cc in CFG.items()
          if any(s["name"] == "breakout" for s in cc["strategies"])}
    print(f"Coin dengan breakout: {len(bo)}\nFetching 14 hari...\n")

    now = int(time.time() * 1000)
    start = now - 14 * 86400_000
    data = {}
    for c in bo:
        try:
            data[c] = {"5m": fetch(c, start, now),
                       "15m": fetch(c, start - 86400_000, now),
                       "1h": fetch(c, start - 5 * 86400_000, now)}
        except Exception as e:
            print(f"  {c} ERR {e}")

    print("=" * 100)
    print("BREAKOUT: VARIASI RR (14 hari)")
    print("=" * 100)
    print(f"{'RR':<7}{'N':>5}{'WR%':>7}{'PF':>7}{'TotR':>9}{'TP':>5}{'SL':>5}{'AvgMin':>8}")
    print("-" * 100)
    for rr in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]:
        trs = []
        for c, cc in bo.items():
            if c not in data:
                continue
            for s in cc["strategies"]:
                if s["name"] != "breakout":
                    continue
                trs.extend(run(data[c]["5m"], data[c]["15m"], data[c]["1h"],
                               s["params"], rr))
        if not trs:
            continue
        n = len(trs)
        w = sum(1 for t in trs if t["R"] > 0)
        gw = sum(t["R"] for t in trs if t["R"] > 0)
        gl = abs(sum(t["R"] for t in trs if t["R"] <= 0))
        pf = gw / gl if gl else 99
        tp = sum(1 for t in trs if t["outcome"] == "TP")
        sl_ = sum(1 for t in trs if t["outcome"] == "SL")
        print(f"1:{rr:<5}{n:>5}{w/n*100:>7.1f}{pf:>7.2f}{sum(t['R'] for t in trs):>+9.1f}"
              f"{tp:>5}{sl_:>5}{sum(t['bars'] for t in trs)/n*5:>8.0f}")

    print("\n" + "=" * 100)
    print("BREAKOUT: RR + BREAKEVEN LOCK")
    print("=" * 100)
    print(f"{'KONFIG':<22}{'N':>5}{'WR%':>7}{'PF':>7}{'TotR':>9}")
    print("-" * 100)
    for rr in [2.5, 3.0, 4.0]:
        for be in [None, 1.0, 1.5]:
            trs = []
            for c, cc in bo.items():
                if c not in data:
                    continue
                for s in cc["strategies"]:
                    if s["name"] != "breakout":
                        continue
                    trs.extend(run(data[c]["5m"], data[c]["15m"], data[c]["1h"],
                                   s["params"], rr, be))
            if not trs:
                continue
            n = len(trs)
            w = sum(1 for t in trs if t["R"] > 0)
            gw = sum(t["R"] for t in trs if t["R"] > 0)
            gl = abs(sum(t["R"] for t in trs if t["R"] <= 0))
            pf = gw / gl if gl else 99
            lbl = f"RR 1:{rr}" + (f" + BE {be}R" if be else "")
            print(f"{lbl:<22}{n:>5}{w/n*100:>7.1f}{pf:>7.2f}{sum(t['R'] for t in trs):>+9.1f}")
