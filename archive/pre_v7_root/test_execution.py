#!/usr/bin/env python3
"""
EXECUTION REALITY TEST
=====================
Backtest selama ini entry di CLOSE candle sinyal.
Realitanya: bot baru tahu candle close SETELAH candle tutup,
lalu kirim order -> fill di harga yang sudah bergerak.

Test 4 model eksekusi:
  A. close      : entry di close candle sinyal (optimistis, yang dipakai backtest)
  B. next_open  : entry di open candle berikutnya (realistis)
  C. next_open + slip : + slippage 0.05%
  D. delayed 1 bar : entry di close candle berikutnya (pesimistis)

Kalau edge hilang di B/C/D -> backtest overfit ke eksekusi sempurna.
"""
import json, urllib.request, time

HL = "https://api.hyperliquid.xyz/info"


def post(p):
    r = urllib.request.Request(HL, data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=40) as resp:
        return json.loads(resp.read().decode())


def fetch(coin, interval, days):
    now = int(time.time() * 1000)
    start = now - days * 86400_000
    raw = post({"type": "candleSnapshot",
                "req": {"coin": coin, "interval": interval, "startTime": start}})
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


def run(ce, c1, c2, P, rr, hold, look, mode, slip=0.0, slope_min=0.0):
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
            strength = abs(cl2[k2] - e2[k2]) / a[i - 1]
            if strength < slope_min:
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

        # --- ENTRY MODEL ---
        if mode == "close":
            entry = cur["c"]
            entry_idx = i
        elif mode == "next_open":
            entry = ce[i]["o"]
            entry_idx = i
        elif mode == "next_open_slip":
            base = ce[i]["o"]
            entry = base * (1 + slip) if d == "LONG" else base * (1 - slip)
            entry_idx = i
        elif mode == "delayed_close":
            entry = ce[i]["c"]
            entry_idx = i + 1
        else:
            continue

        dist = a[i - 1] * P["atr_mult"]
        if dist / entry > 0.06 or dist / entry < 0.0015:
            continue
        sl = entry - dist if d == "LONG" else entry + dist
        tp = entry + dist * rr if d == "LONG" else entry - dist * rr

        outcome = None
        bars = 0
        for j in range(entry_idx, min(entry_idx + hold + 1, n)):
            bars = j - entry_idx
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
            exit_p = ce[min(entry_idx + hold, n - 1)]["c"]

        pnl = (exit_p - entry) if d == "LONG" else (entry - exit_p)
        R = pnl / dist
        fee = (entry + exit_p) * 0.0004 / dist
        trades.append({"R": R - fee, "outcome": outcome, "bars": bars})
        busy = entry_idx + max(bars, 1)

    return trades


def metrics(trs):
    if not trs:
        return None
    n = len(trs)
    w = [t for t in trs if t["R"] > 0]
    gw = sum(t["R"] for t in w)
    gl = abs(sum(t["R"] for t in trs if t["R"] <= 0))
    eq = peak = mdd = 0.0
    for t in trs:
        eq += t["R"]
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return {"n": n, "wr": len(w) / n * 100, "pf": gw / gl if gl else 99,
            "totR": sum(t["R"] for t in trs), "mdd": mdd,
            "avgR": sum(t["R"] for t in trs) / n}


if __name__ == "__main__":
    COINS = ["WLD", "INJ", "ZEC", "NEAR", "HYPE", "ENA", "PUMP"]
    P = {"look": 10, "atr_mult": 1.5, "rr": 4.0, "min_body": 0.5}
    DAYS = 90

    print(f"Fetching 15m data ({DAYS}d)...")
    data = {}
    for c in COINS:
        try:
            data[c] = {"e": fetch(c, "15m", DAYS),
                       "1": fetch(c, "1h", DAYS + 30),
                       "2": fetch(c, "4h", DAYS + 60)}
            print(f"  {c} ok")
        except Exception as ex:
            print(f"  {c} ERR {ex}")

    MODES = [
        ("A. close (backtest)", "close", 0.0),
        ("B. next_open", "next_open", 0.0),
        ("C. next_open + slip 0.05%", "next_open_slip", 0.0005),
        ("D. delayed 1 bar", "delayed_close", 0.0),
    ]

    print("\n" + "=" * 108)
    print("EXECUTION REALITY TEST — 15m breakout RR 1:4, slope 1.5, 90d")
    print("=" * 108)
    print(f"{'MODEL':<30}{'N':>5}{'WR%':>7}{'PF':>7}{'TotR':>9}{'AvgR':>8}{'MaxDD':>8}{'vs A':>9}")
    print("-" * 108)

    base = None
    for label, mode, slip in MODES:
        allt = []
        for c in COINS:
            if c not in data:
                continue
            allt.extend(run(data[c]["e"], data[c]["1"], data[c]["2"],
                            P, P["rr"], 48, P["look"], mode, slip, 1.5))
        m = metrics(allt)
        if not m:
            print(f"{label:<30}  no trades")
            continue
        if base is None:
            base = m["totR"]
        delta = m["totR"] - base
        print(f"{label:<30}{m['n']:>5}{m['wr']:>7.1f}{m['pf']:>7.2f}{m['totR']:>+9.1f}"
              f"{m['avgR']:>+8.3f}{m['mdd']:>8.1f}{delta:>+9.1f}")

    print("-" * 108)
    print("Kalau B/C/D jauh lebih buruk dari A -> backtest overfit ke eksekusi sempurna.")
