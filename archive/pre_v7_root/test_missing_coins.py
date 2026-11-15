#!/usr/bin/env python3
"""Tes 4 coin yang hilang (ETH, SOL, XRP, ARB) pakai breakout 15m."""
import json, urllib.request, time

HL = "https://api.hyperliquid.xyz/info"


def post(p):
    r = urllib.request.Request(HL, data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=40) as resp:
        return json.loads(resp.read().decode())


def fetch(coin, interval, days):
    now = int(time.time() * 1000)
    raw = post({"type": "candleSnapshot",
                "req": {"coin": coin, "interval": interval,
                        "startTime": now - days * 86400_000}})
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


def align(cs, cb):
    ib = 0
    m = []
    for c in cs:
        while ib + 1 < len(cb) and cb[ib + 1]["t"] <= c["t"]:
            ib += 1
        m.append(ib)
    return m


def run(ce, c1, c2, P, rr, hold, look, slope_min):
    n = len(ce)
    a = atr_series(ce, 14)
    m1, m2 = align(ce, c1), align(ce, c2)
    cl1 = [x["c"] for x in c1]
    cl2 = [x["c"] for x in c2]
    e1 = ema_series(cl1, 20)
    e2 = ema_series(cl2, 20)
    e2_50 = ema_series(cl2, 50)
    trades = []
    busy = -1

    for i in range(max(120, look + 3), n - 2):
        if i <= busy:
            continue
        cur = ce[i - 1]
        k1, k2 = m1[i - 1], m2[i - 1]
        if None in (e1[k1], e2[k2], a[i - 1]):
            continue
        if slope_min and abs(cl2[k2] - e2[k2]) / a[i - 1] < slope_min:
            continue
        up1 = cl1[k1] > e1[k1]
        up2 = cl2[k2] > e2[k2]
        slope = e2_50[k2] is not None and e2[k2] > e2_50[k2]
        rng = ce[i - 1 - look:i - 1]
        hh = max(x["h"] for x in rng)
        ll = min(x["l"] for x in rng)
        body = abs(cur["c"] - cur["o"])
        rngc = max(cur["h"] - cur["l"], 1e-9)
        if body / rngc < P["min_body"]:
            continue
        d = None
        if cur["c"] > hh and up1 and up2 and slope:
            d = "LONG"
        elif cur["c"] < ll and (not up1) and (not up2) and (not slope):
            d = "SHORT"
        if not d:
            continue
        entry = cur["c"]
        dist = a[i - 1] * P["atr_mult"]
        if dist / entry > 0.06 or dist / entry < 0.0015:
            continue
        sl = entry - dist if d == "LONG" else entry + dist
        tp = entry + dist * rr if d == "LONG" else entry - dist * rr
        outcome = None
        bars = 0
        for j in range(i, min(i + hold + 1, n)):
            bars = j - i
            h, l = ce[j]["h"], ce[j]["l"]
            if d == "LONG" and l <= sl:
                outcome = "SL"; exit_p = sl; break
            if d == "SHORT" and h >= sl:
                outcome = "SL"; exit_p = sl; break
            if d == "LONG" and h >= tp:
                outcome = "TP"; exit_p = tp; break
            if d == "SHORT" and l <= tp:
                outcome = "TP"; exit_p = tp; break
        else:
            outcome = "TIME"
            exit_p = ce[min(i + hold, n - 1)]["c"]
        pnl = (exit_p - entry) if d == "LONG" else (entry - exit_p)
        R = pnl / dist
        fee = (entry + exit_p) * 0.0009 / dist
        slip = (entry + exit_p) * 0.0005 / dist
        trades.append({"R": R - fee - slip})
        busy = i + max(bars, 1)
    return trades


def metrics(t):
    if not t:
        return None
    n = len(t)
    w = [x for x in t if x["R"] > 0]
    gw = sum(x["R"] for x in w)
    gl = abs(sum(x["R"] for x in t if x["R"] <= 0))
    return {"n": n, "wr": len(w) / n * 100, "pf": gw / gl if gl else 99,
            "totR": sum(x["R"] for x in t), "avgR": sum(x["R"] for x in t) / n}


if __name__ == "__main__":
    TEST = ["ETH", "SOL", "XRP", "ARB"]
    P = {"look": 10, "atr_mult": 1.5, "rr": 4.0, "min_body": 0.5}
    DAYS = 90

    print(f"Tes {len(TEST)} coin yang hilang pakai breakout 15m ({DAYS}d)...\n")
    print(f"{'COIN':<7}{'N':>5}{'WR%':>7}{'PF':>7}{'TotR':>9}{'AvgR':>8}{'VERDICT':>12}")
    print("-" * 62)

    for c in TEST:
        try:
            ce = fetch(c, "15m", DAYS)
            c1 = fetch(c, "1h", DAYS + 30)
            c2 = fetch(c, "4h", DAYS + 60)
            tr = run(ce, c1, c2, P, P["rr"], 48, P["look"], 1.5)
            m = metrics(tr)
            if not m:
                print(f"{c:<7}  no trades")
                continue
            v = "LAYAK" if m["pf"] > 1.2 and m["totR"] > 0 else "TIDAK"
            print(f"{c:<7}{m['n']:>5}{m['wr']:>7.1f}{m['pf']:>7.2f}{m['totR']:>+9.1f}"
                  f"{m['avgR']:>+8.3f}{v:>12}")
        except Exception as e:
            print(f"{c:<7} ERR {e}")
