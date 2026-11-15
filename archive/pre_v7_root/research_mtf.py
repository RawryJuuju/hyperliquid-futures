#!/usr/bin/env python3
"""
MULTI-TIMEFRAME RESEARCH
=======================
Tes strategi breakout di 4 timeframe: 5m, 15m, 1h, 4h.
Untuk tiap TF ukur: frekuensi, win rate, PF, avg hold time, MFE/MAE.

Tujuan: tentukan alokasi risk per TF berdasarkan karakteristik masing-masing.
Prinsip: TF kecil = banyak sinyal, noise tinggi, risk kecil.
         TF besar = sedikit sinyal, conviction tinggi, risk besar.
"""
import json, urllib.request, time, statistics
from datetime import datetime, timezone, timedelta

HL = "https://api.hyperliquid.xyz/info"
WIB = timezone(timedelta(hours=7))

TF_MIN = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}


def post(p):
    r = urllib.request.Request(HL, data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=40) as resp:
        return json.loads(resp.read().decode())


def fetch(coin, interval, days):
    now = int(time.time() * 1000)
    step = TF_MIN[interval] * 60_000
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


def align(c_small, c_big):
    """Map tiap candle small ke index candle big terakhir yang closed."""
    ib = 0
    m = []
    for c in c_small:
        while ib + 1 < len(c_big) and c_big[ib + 1]["t"] <= c["t"]:
            ib += 1
        m.append(ib)
    return m


def run_breakout(entry_tf, c_entry, c_htf, c_htf2, P, rr, hold_bars, look):
    """
    entry_tf : tf eksekusi
    c_entry  : candle tf eksekusi
    c_htf    : candle 1 level di atas
    c_htf2   : candle 2 level di atas (trend filter)
    """
    n = len(c_entry)
    a = atr_series(c_entry, 14)
    m1 = align(c_entry, c_htf)
    m2 = align(c_entry, c_htf2)
    cl1 = [x["c"] for x in c_htf]
    cl2 = [x["c"] for x in c_htf2]
    e1 = ema_series(cl1, 20)
    e2 = ema_series(cl2, 20)
    e2_50 = ema_series(cl2, 50)

    trades = []
    busy = -1

    for i in range(max(120, look + 3), n - 1):
        if i <= busy:
            continue
        cur = c_entry[i - 1]
        k1, k2 = m1[i - 1], m2[i - 1]
        if None in (e1[k1], e2[k2], a[i - 1]):
            continue

        up1 = cl1[k1] > e1[k1]
        up2 = cl2[k2] > e2[k2]
        slope = e2_50[k2] is not None and e2[k2] > e2_50[k2]

        rng = c_entry[i - 1 - look:i - 1]
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
        mfe = 0.0
        mae = 0.0
        for j in range(i, min(i + hold_bars + 1, n)):
            bars = j - i
            h, l = c_entry[j]["h"], c_entry[j]["l"]
            if d == "LONG":
                mfe = max(mfe, (h - entry) / dist)
                mae = max(mae, (entry - l) / dist)
            else:
                mfe = max(mfe, (entry - l) / dist)
                mae = max(mae, (h - entry) / dist)

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
            exit_p = c_entry[min(i + hold_bars, n - 1)]["c"]

        pnl = (exit_p - entry) if d == "LONG" else (entry - exit_p)
        R = pnl / dist
        fee = (entry + exit_p) * 0.0004 / dist
        trades.append({"R": R - fee, "outcome": outcome, "bars": bars,
                       "mfe": mfe, "mae": mae})
        busy = i + max(bars, 1)

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
    return {
        "n": n, "wr": len(w) / n * 100,
        "pf": gw / gl if gl else 99,
        "totR": sum(t["R"] for t in trs),
        "avgR": sum(t["R"] for t in trs) / n,
        "mdd": mdd,
        "tp": sum(1 for t in trs if t["outcome"] == "TP"),
        "sl": sum(1 for t in trs if t["outcome"] == "SL"),
        "time": sum(1 for t in trs if t["outcome"] == "TIME"),
        "avg_bars": sum(t["bars"] for t in trs) / n,
        "avg_mfe": sum(t["mfe"] for t in trs) / n,
    }


if __name__ == "__main__":
    COINS = ["WLD", "INJ", "ZEC", "NEAR", "HYPE", "ENA", "PUMP"]

    # parameter per TF: SL lebih lebar di TF besar, hold lebih lama
    CONFIGS = {
        "5m":  {"look": 10, "atr_mult": 1.5, "min_body": 0.6, "rr": 5.0,
                "hold": 72,  "days": 60,  "htf": "15m", "htf2": "1h"},
        "15m": {"look": 10, "atr_mult": 1.5, "min_body": 0.5, "rr": 4.0,
                "hold": 48,  "days": 90,  "htf": "1h",  "htf2": "4h"},
        "1h":  {"look": 12, "atr_mult": 2.0, "min_body": 0.5, "rr": 4.0,
                "hold": 48,  "days": 180, "htf": "4h",  "htf2": "1d"},
        "4h":  {"look": 12, "atr_mult": 2.0, "min_body": 0.5, "rr": 4.0,
                "hold": 30,  "days": 365, "htf": "1d",  "htf2": "1d"},
    }

    print("Fetching data per timeframe...\n")
    cache = {}
    for tf, cfg in CONFIGS.items():
        for coin in COINS:
            for interval in {tf, cfg["htf"], cfg["htf2"]}:
                key = (coin, interval)
                if key in cache:
                    continue
                try:
                    cache[key] = fetch(coin, interval, cfg["days"] + 30)
                except Exception as e:
                    print(f"  {coin} {interval} ERR {e}")
                    cache[key] = []
        print(f"  {tf} done")

    print("\n" + "=" * 118)
    print("HASIL PER TIMEFRAME (7 coin, breakout RR)")
    print("=" * 118)
    print(f"{'TF':<6}{'N':>6}{'WR%':>7}{'PF':>7}{'TotR':>9}{'AvgR':>8}{'MaxDD':>8}"
          f"{'TP':>5}{'SL':>5}{'TIME':>6}{'AvgHold':>10}{'AvgMFE':>8}")
    print("-" * 118)

    results = {}
    for tf, cfg in CONFIGS.items():
        all_tr = []
        for coin in COINS:
            ce = cache.get((coin, tf), [])
            c1 = cache.get((coin, cfg["htf"]), [])
            c2 = cache.get((coin, cfg["htf2"]), [])
            if not ce or not c1 or not c2:
                continue
            try:
                all_tr.extend(run_breakout(tf, ce, c1, c2, cfg, cfg["rr"],
                                           cfg["hold"], cfg["look"]))
            except Exception:
                pass
        m = metrics(all_tr)
        if not m:
            print(f"{tf:<6}  no trades")
            continue
        results[tf] = m
        hold_str = f"{m['avg_bars']*TF_MIN[tf]:.0f}m"
        print(f"{tf:<6}{m['n']:>6}{m['wr']:>7.1f}{m['pf']:>7.2f}{m['totR']:>+9.1f}"
              f"{m['avgR']:>+8.3f}{m['mdd']:>8.1f}{m['tp']:>5}{m['sl']:>5}"
              f"{m['time']:>6}{hold_str:>10}{m['avg_mfe']:>8.2f}")

    print("\n" + "=" * 118)
    print("NORMALISASI: R per hari (frekuensi vs kualitas)")
    print("=" * 118)
    print(f"{'TF':<6}{'N':>6}{'days':>7}{'N/day':>8}{'R/day':>9}{'R/trade':>9}{'PF':>7}{'VERDICT':<18}")
    print("-" * 118)
    for tf, m in results.items():
        days = CONFIGS[tf]["days"]
        nday = m["n"] / days
        rday = m["totR"] / days
        verdict = ("BEST" if rday == max(x["totR"] / CONFIGS[t]["days"]
                                          for t, x in results.items()) else "")
        print(f"{tf:<6}{m['n']:>6}{days:>7}{nday:>8.1f}{rday:>+9.2f}"
              f"{m['avgR']:>+9.3f}{m['pf']:>7.2f}{verdict:<18}")
