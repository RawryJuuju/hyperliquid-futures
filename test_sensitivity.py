#!/usr/bin/env python3
"""Sensitivity test: apakah edge tahan kalau parameter digeser?"""
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


def run(ce, c1, c2, P, rr, hold, look, slope_min, atr_mult, min_body):
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

        if slope_min:
            if abs(cl2[k2] - e2[k2]) / a[i - 1] < slope_min:
                continue

        up1 = cl1[k1] > e1[k1]
        up2 = cl2[k2] > e2[k2]
        slope = e2_50[k2] is not None and e2[k2] > e2_50[k2]

        rng = ce[i - 1 - look:i - 1]
        hh = max(x["h"] for x in rng)
        ll = min(x["l"] for x in rng)
        body = abs(cur["c"] - cur["o"])
        rngc = max(cur["h"] - cur["l"], 1e-9)
        if body / rngc < min_body:
            continue

        d = None
        if cur["c"] > hh and up1 and up2 and slope:
            d = "LONG"
        elif cur["c"] < ll and (not up1) and (not up2) and (not slope):
            d = "SHORT"
        if not d:
            continue

        entry = cur["c"]
        dist = a[i - 1] * atr_mult
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
        fee = (entry + exit_p) * 0.0004 / dist
        trades.append({"R": R - fee})
        busy = i + max(bars, 1)

    return trades


def metrics(trs):
    if not trs:
        return None
    n = len(trs)
    w = [t for t in trs if t["R"] > 0]
    gw = sum(t["R"] for t in w)
    gl = abs(sum(t["R"] for t in trs if t["R"] <= 0))
    return {"n": n, "pf": gw / gl if gl else 99, "totR": sum(t["R"] for t in trs)}


if __name__ == "__main__":
    COINS = ["WLD", "INJ", "ZEC", "NEAR", "HYPE", "ENA", "PUMP"]
    DAYS = 90
    BASE = {"look": 10, "atr_mult": 1.5, "rr": 4.0, "min_body": 0.5,
            "hold": 48, "slope_min": 1.5}

    print("Fetching...")
    data = {}
    for c in COINS:
        data[c] = {"e": fetch(c, "15m", DAYS), "1": fetch(c, "1h", DAYS + 30),
                   "2": fetch(c, "4h", DAYS + 60)}
        print(f"  {c} ok")

    print("\n" + "=" * 100)
    print("SENSITIVITY TEST — geser parameter ±20-50%, PF harus tetap > 1.0")
    print("=" * 100)
    print(f"{'PARAM':<18}{'VALUE':>8}{'N':>6}{'PF':>7}{'TotR':>9}{'STATUS':>10}")
    print("-" * 100)

    tests = []
    for v in [8, 10, 12, 15]:
        tests.append(("look", v, {**BASE, "look": v}))
    for v in [1.0, 1.25, 1.5, 1.75, 2.0]:
        tests.append(("atr_mult", v, {**BASE, "atr_mult": v}))
    for v in [3.0, 3.5, 4.0, 4.5, 5.0]:
        tests.append(("rr", v, {**BASE, "rr": v}))
    for v in [0.35, 0.4, 0.5, 0.6, 0.7]:
        tests.append(("min_body", v, {**BASE, "min_body": v}))
    for v in [1.0, 1.25, 1.5, 1.75, 2.0]:
        tests.append(("slope_min", v, {**BASE, "slope_min": v}))

    fails = 0
    for pname, val, cfg in tests:
        allt = []
        for c in COINS:
            allt.extend(run(data[c]["e"], data[c]["1"], data[c]["2"],
                            cfg, cfg["rr"], cfg["hold"], cfg["look"],
                            cfg["slope_min"], cfg["atr_mult"], cfg["min_body"]))
        m = metrics(allt)
        if not m:
            continue
        ok = "PASS" if m["pf"] > 1.0 and m["totR"] > 0 else "FAIL"
        if ok == "FAIL":
            fails += 1
        print(f"{pname:<18}{val:>8.2f}{m['n']:>6}{m['pf']:>7.2f}{m['totR']:>+9.1f}{ok:>10}")

    print("-" * 100)
    print(f"\nTotal config diuji: {len(tests)} | FAIL: {fails} ({fails/len(tests)*100:.0f}%)")
    print(f"Verdict: {'ROBUST' if fails <= len(tests)*0.2 else 'FRAGILE — rawan overfit'}")
