#!/usr/bin/env python3
"""
TEST: BE dan Partial TP di level tinggi (2R, 2.5R, 3R)
Pertanyaan user: kalau TP di 4R, dan sudah profit 2R, kenapa tidak pasang SL di entry?

Logika:
  BE@2R untung  : trade yang pullback ke -1R jadi 0R (+1R)
  BE@2R rugi    : trade yang pullback ke 0R lalu lanjut 4R jadi 0R (-4R)

Yang menentukan: mana yang lebih sering?
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


def run(ce, c1, c2, P, rr, hold, look, slope_min,
        be_at=None, partial_at=None, partial_frac=0.5, trail_at=None, trail_gap=0.5):
    """
    Exit management:
      be_at      : geser SL ke entry saat profit >= be_at R
      partial_at : tutup partial_frac posisi saat profit >= partial_at R
      trail_at   : mulai trailing setelah trail_at R, jarak trail_gap R
    """
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
        sl0 = entry - dist if d == "LONG" else entry + dist
        tp = entry + dist * rr if d == "LONG" else entry - dist * rr

        cur_sl = sl0
        remaining = 1.0
        realized = 0.0
        partial_done = False
        be_done = False
        trail_done = False
        outcome = None
        bars = 0
        exit_p = None

        for j in range(i, min(i + hold + 1, n)):
            bars = j - i
            h, l = ce[j]["h"], ce[j]["l"]
            r_now = (h - entry) / dist if d == "LONG" else (entry - l) / dist

            # --- trailing stop ---
            if trail_at and r_now >= trail_at:
                if d == "LONG":
                    lock = entry + dist * (r_now - trail_gap)
                    cur_sl = max(cur_sl, lock)
                else:
                    lock = entry - dist * (r_now - trail_gap)
                    cur_sl = min(cur_sl, lock)
                trail_done = True

            # --- partial TP ---
            if partial_at and not partial_done and r_now >= partial_at:
                realized += partial_frac * partial_at
                remaining -= partial_frac
                partial_done = True
                # setelah partial, SL ke entry (kecuali sudah trailing lebih tinggi)
                if d == "LONG":
                    cur_sl = max(cur_sl, entry)
                else:
                    cur_sl = min(cur_sl, entry)
                be_done = True

            # --- breakeven ---
            elif be_at and not be_done and r_now >= be_at:
                cur_sl = entry
                be_done = True

            # --- cek SL ---
            if d == "LONG" and l <= cur_sl:
                r_exit = (cur_sl - entry) / dist
                realized += remaining * r_exit
                if cur_sl == sl0:
                    outcome = "SL"
                elif cur_sl == entry:
                    outcome = "BE"
                else:
                    outcome = "TRAIL"
                exit_p = cur_sl
                break
            if d == "SHORT" and h >= cur_sl:
                r_exit = (entry - cur_sl) / dist
                realized += remaining * r_exit
                if cur_sl == sl0:
                    outcome = "SL"
                elif cur_sl == entry:
                    outcome = "BE"
                else:
                    outcome = "TRAIL"
                exit_p = cur_sl
                break

            # --- cek TP ---
            if d == "LONG" and h >= tp:
                realized += remaining * rr
                outcome = "TP"
                exit_p = tp
                break
            if d == "SHORT" and l <= tp:
                realized += remaining * rr
                outcome = "TP"
                exit_p = tp
                break

        if outcome is None:
            outcome = "TIME"
            exit_p = ce[min(i + hold, n - 1)]["c"]
            r_exit = (exit_p - entry) / dist if d == "LONG" else (entry - exit_p) / dist
            realized += remaining * r_exit

        fee = (entry + exit_p) * 0.0009 / dist
        slip = (entry + exit_p) * 0.0005 / dist
        trades.append({"R": realized - fee - slip, "outcome": outcome, "bars": bars})
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
        "mdd": mdd, "avgR": sum(t["R"] for t in trs) / n,
        "tp": sum(1 for t in trs if t["outcome"] == "TP"),
        "sl": sum(1 for t in trs if t["outcome"] == "SL"),
        "be": sum(1 for t in trs if t["outcome"] == "BE"),
        "trail": sum(1 for t in trs if t["outcome"] == "TRAIL"),
        "time": sum(1 for t in trs if t["outcome"] == "TIME"),
    }


if __name__ == "__main__":
    COINS = ["WLD", "INJ", "ZEC", "NEAR", "HYPE", "ENA", "PUMP"]
    P = {"look": 10, "atr_mult": 1.5, "rr": 4.0, "min_body": 0.5}
    DAYS = 90
    SLOPE = 1.5

    print("Fetching 15m data...")
    data = {}
    for c in COINS:
        data[c] = {"e": fetch(c, "15m", DAYS),
                   "1": fetch(c, "1h", DAYS + 30),
                   "2": fetch(c, "4h", DAYS + 60)}
        print(f"  {c} ok")

    VARIANTS = [
        ("baseline (TP 4R)", {}),
        ("BE @ 1.0R", {"be_at": 1.0}),
        ("BE @ 1.5R", {"be_at": 1.5}),
        ("BE @ 2.0R", {"be_at": 2.0}),
        ("BE @ 2.5R", {"be_at": 2.5}),
        ("BE @ 3.0R", {"be_at": 3.0}),
        ("Partial 50% @ 2R + BE", {"partial_at": 2.0, "partial_frac": 0.5}),
        ("Partial 50% @ 2.5R + BE", {"partial_at": 2.5, "partial_frac": 0.5}),
        ("Partial 30% @ 2R + BE", {"partial_at": 2.0, "partial_frac": 0.3}),
        ("Trail 0.5R @ 2R", {"trail_at": 2.0, "trail_gap": 0.5}),
        ("Trail 0.5R @ 1.5R", {"trail_at": 1.5, "trail_gap": 0.5}),
        ("Trail 1.0R @ 2R", {"trail_at": 2.0, "trail_gap": 1.0}),
    ]

    print("\n" + "=" * 118)
    print("EXIT MANAGEMENT TEST — 15m breakout, TP 4R, slope 1.5, 90d, fee+slippage realistis")
    print("=" * 118)
    print(f"{'VARIAN':<28}{'N':>5}{'WR%':>7}{'PF':>7}{'TotR':>9}{'AvgR':>8}{'MaxDD':>8}"
          f"{'TP':>5}{'SL':>5}{'BE':>5}{'TRL':>5}")
    print("-" * 118)

    results = []
    for label, kw in VARIANTS:
        allt = []
        for c in COINS:
            allt.extend(run(data[c]["e"], data[c]["1"], data[c]["2"],
                            P, P["rr"], 48, P["look"], SLOPE, **kw))
        m = metrics(allt)
        if not m:
            continue
        results.append((label, m))
        print(f"{label:<28}{m['n']:>5}{m['wr']:>7.1f}{m['pf']:>7.2f}{m['totR']:>+9.1f}"
              f"{m['avgR']:>+8.3f}{m['mdd']:>8.1f}{m['tp']:>5}{m['sl']:>5}"
              f"{m['be']:>5}{m['trail']:>5}")

    print("-" * 118)
    base = next(m for l, m in results if l.startswith("baseline"))["totR"]
    print(f"\n{'RANKING':<32}{'TotR':>10}{'vs baseline':>14}{'PF':>8}")
    print("-" * 70)
    for label, m in sorted(results, key=lambda x: -x[1]["totR"]):
        delta = m["totR"] - base
        print(f"{label:<32}{m['totR']:>+10.1f}{delta:>+14.1f}{m['pf']:>8.2f}")
