#!/usr/bin/env python3
"""
REGIME FILTER TEST
==================
Prinsip systematic trading: strategi trend-following hanya bekerja di regime trending.
Mean reversion hanya bekerja di regime ranging.

Test: breakout + filter regime (ADX, ATR percentile, EMA slope strength).
Tujuan: buang trade di regime yang salah.
"""
import json, urllib.request, time, statistics

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


def adx_series(c, p=14):
    n = len(c)
    out = [None] * n
    if n < p * 2:
        return out
    tr, pdm, ndm = [], [], []
    for i in range(1, n):
        h, l, ph, pl, pc = c[i]["h"], c[i]["l"], c[i - 1]["h"], c[i - 1]["l"], c[i - 1]["c"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, dn = h - ph, pl - l
        pdm.append(up if (up > dn and up > 0) else 0.0)
        ndm.append(dn if (dn > up and dn > 0) else 0.0)
    atr_s, pdi_s, ndi_s = sum(tr[:p]), sum(pdm[:p]), sum(ndm[:p])
    dxs = []
    for i in range(p, len(tr)):
        atr_s = atr_s - atr_s / p + tr[i]
        pdi_s = pdi_s - pdi_s / p + pdm[i]
        ndi_s = ndi_s - ndi_s / p + ndm[i]
        if atr_s <= 0:
            dxs.append(0); continue
        pdi, ndi = 100 * pdi_s / atr_s, 100 * ndi_s / atr_s
        den = pdi + ndi
        dxs.append(100 * abs(pdi - ndi) / den if den > 0 else 0)
    if len(dxs) < p:
        return out
    adx = sum(dxs[:p]) / p
    out[p * 2] = adx
    for i in range(p, len(dxs)):
        adx = (adx * (p - 1) + dxs[i]) / p
        idx = p + i + 1
        if idx < n:
            out[idx] = adx
    return out


def align(cs, cb):
    ib = 0
    m = []
    for c in cs:
        while ib + 1 < len(cb) and cb[ib + 1]["t"] <= c["t"]:
            ib += 1
        m.append(ib)
    return m


def run(ce, c1, c2, P, rr, hold, look, regime=None):
    n = len(ce)
    a = atr_series(ce, 14)
    adx = adx_series(ce, 14) if regime and "adx" in regime else [None] * n
    m1, m2 = align(ce, c1), align(ce, c2)
    cl1 = [x["c"] for x in c1]
    cl2 = [x["c"] for x in c2]
    e1 = ema_series(cl1, 20)
    e2 = ema_series(cl2, 20)
    e2_50 = ema_series(cl2, 50)

    trades = []
    busy = -1

    for i in range(max(120, look + 3), n - 1):
        if i <= busy:
            continue
        cur = ce[i - 1]
        k1, k2 = m1[i - 1], m2[i - 1]
        if None in (e1[k1], e2[k2], a[i - 1]):
            continue

        # --- REGIME FILTERS ---
        if regime:
            # ADX: hanya trade kalau trend kuat
            if "adx" in regime:
                if adx[i - 1] is None or adx[i - 1] < regime["adx"]:
                    continue
            # ATR percentile: hanya trade kalau volatilitas di rentang tertentu
            if "atr_pct" in regime:
                hist = [x for x in a[max(0, i - 100):i] if x]
                if len(hist) < 40:
                    continue
                pct_rank = sum(1 for x in hist if x <= a[i - 1]) / len(hist)
                lo, hi = regime["atr_pct"]
                if not (lo <= pct_rank <= hi):
                    continue
            # EMA slope strength: seberapa jauh harga dari EMA2
            if "slope_min" in regime:
                strength = abs(cl2[k2] - e2[k2]) / a[i - 1]
                if strength < regime["slope_min"]:
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
        fee = (entry + exit_p) * 0.0004 / dist
        trades.append({"R": R - fee, "outcome": outcome, "bars": bars})
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
    return {"n": n, "wr": len(w) / n * 100, "pf": gw / gl if gl else 99,
            "totR": sum(t["R"] for t in trs), "mdd": mdd,
            "avgR": sum(t["R"] for t in trs) / n}


if __name__ == "__main__":
    COINS = ["WLD", "INJ", "ZEC", "NEAR", "HYPE", "ENA", "PUMP"]
    TF = "15m"
    P = {"look": 10, "atr_mult": 1.5, "rr": 4.0, "min_body": 0.5, "hold": 48}
    DAYS = 90

    print(f"Fetching {TF} data ({DAYS}d) untuk {len(COINS)} coin...")
    data = {}
    for c in COINS:
        try:
            data[c] = {
                "e": fetch(c, TF, DAYS),
                "1": fetch(c, "1h", DAYS + 30),
                "2": fetch(c, "4h", DAYS + 60),
            }
            print(f"  {c} ok")
        except Exception as ex:
            print(f"  {c} ERR {ex}")

    REGIMES = {
        "baseline (no filter)": None,
        "ADX >= 20": {"adx": 20},
        "ADX >= 25": {"adx": 25},
        "ADX >= 30": {"adx": 30},
        "ATR pct 20-80": {"atr_pct": (0.20, 0.80)},
        "ATR pct 30-90": {"atr_pct": (0.30, 0.90)},
        "ATR pct 50-95": {"atr_pct": (0.50, 0.95)},
        "slope >= 1.0 ATR": {"slope_min": 1.0},
        "slope >= 1.5 ATR": {"slope_min": 1.5},
        "ADX25 + ATR30-90": {"adx": 25, "atr_pct": (0.30, 0.90)},
        "ADX20 + slope1.0": {"adx": 20, "slope_min": 1.0},
        "ADX25 + slope1.5": {"adx": 25, "slope_min": 1.5},
        "ALL: ADX20+ATR30-90+slope1": {"adx": 20, "atr_pct": (0.30, 0.90), "slope_min": 1.0},
    }

    print("\n" + "=" * 104)
    print(f"REGIME FILTER TEST — BREAKOUT {TF} RR 1:{P['rr']} ({DAYS}d, {len(COINS)} coin)")
    print("=" * 104)
    print(f"{'REGIME':<30}{'N':>5}{'WR%':>7}{'PF':>7}{'TotR':>9}{'AvgR':>8}{'MaxDD':>8}{'R/day':>8}")
    print("-" * 104)

    rows = []
    for name, rg in REGIMES.items():
        allt = []
        for c in COINS:
            if c not in data:
                continue
            try:
                allt.extend(run(data[c]["e"], data[c]["1"], data[c]["2"],
                                P, P["rr"], P["hold"], P["look"], rg))
            except Exception:
                pass
        m = metrics(allt)
        if not m:
            print(f"{name:<30}  no trades")
            continue
        rows.append((name, m))
        print(f"{name:<30}{m['n']:>5}{m['wr']:>7.1f}{m['pf']:>7.2f}{m['totR']:>+9.1f}"
              f"{m['avgR']:>+8.3f}{m['mdd']:>8.1f}{m['totR']/DAYS:>+8.2f}")

    print("\n" + "=" * 104)
    print("RANKING by Total R")
    print("=" * 104)
    for name, m in sorted(rows, key=lambda x: -x[1]["totR"]):
        lift = ""
        base = next((x[1] for x in rows if x[0] == "baseline (no filter)"), None)
        if base and name != "baseline (no filter)":
            lift = f"  ({m['totR']-base['totR']:+.1f}R vs baseline)"
        print(f"  {name:<30} {m['totR']:>+8.1f}R  PF {m['pf']:.2f}  N={m['n']:<4}{lift}")
