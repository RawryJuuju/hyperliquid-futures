#!/usr/bin/env python3
"""
Diagnosa v2: bandingkan backtest periode SAMA vs hasil live.
Kalau backtest periode itu juga rugi -> periode jelek.
Kalau backtest untung tapi live rugi -> ada mismatch eksekusi.
"""
import json, urllib.request, time
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
HL = "https://api.hyperliquid.xyz/info"


def post(p):
    r = urllib.request.Request(HL, data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=25) as resp:
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


def run_family(c5, c15, c1h, P, family):
    n = len(c5)
    a = atr_series(c5, 14)
    m15, m1h = align(c5, c15, c1h)
    cl15 = [x["c"] for x in c15]
    cl1h = [x["c"] for x in c1h]
    e15 = ema_series(cl15, P.get("htf_ema", 20))
    e1h = ema_series(cl1h, P.get("htf_ema", 20))
    e1h50 = ema_series(cl1h, 50)
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
        slope = e1h[k1h] > e1h50[k1h]
        rng = c5[i - 1 - look:i - 1]
        hh = max(x["h"] for x in rng)
        ll = min(x["l"] for x in rng)
        body = abs(cur["c"] - cur["o"])
        rngc = max(cur["h"] - cur["l"], 1e-9)
        br = body / rngc

        d = None
        if family == "breakout":
            if br < P.get("min_body", 0):
                continue
            if cur["c"] > hh and up15 and up1h:
                d = "LONG"
            elif cur["c"] < ll and not up15 and not up1h:
                d = "SHORT"
        elif family == "sweep_fade":
            if br < P.get("min_body", 0):
                continue
            if cur["l"] < ll and cur["c"] > ll and up15 and up1h:
                d = "LONG"
            elif cur["h"] > hh and cur["c"] < hh and not up15 and not up1h:
                d = "SHORT"
        elif family == "bollinger":
            import statistics as st
            if i < P["bb_period"]:
                continue
            cl5 = [x["c"] for x in c5[:i]]
            ww = cl5[-P["bb_period"]:]
            m = sum(ww) / len(ww)
            sd = st.pstdev(ww)
            upper = m + P["bb_k"] * sd
            lower = m - P["bb_k"] * sd
            if cur["l"] < lower and cur["c"] > lower:
                d = "LONG"
            elif cur["h"] > upper and cur["c"] < upper:
                d = "SHORT"
        if not d:
            continue

        entry = cur["c"]
        dist = a[i - 1] * P["atr_mult"]
        if dist / entry > 0.035 or dist / entry < 0.0015:
            continue
        sl = entry - dist if d == "LONG" else entry + dist
        tp = entry + dist * P["rr"] if d == "LONG" else entry - dist * P["rr"]

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
    # rentang LIVE: dari trade pertama sampai terakhir
    rows = [json.loads(l) for l in open("/home/ubuntu/papertrade_backtest/fut_trades.jsonl") if l.strip()]
    t_first = datetime.fromisoformat(rows[0]["t"])
    t_last = datetime.fromisoformat(rows[-1]["t"])
    print(f"Live period: {t_first.strftime('%d/%m %H:%M')} -> {t_last.strftime('%d/%m %H:%M')} WIB")
    print(f"Duration: {(t_last-t_first).total_seconds()/3600:.1f} jam\n")

    CFG = json.load(open("/home/ubuntu/papertrade_backtest/strategy_config.json"))["coins"]

    # fetch 3 hari terakhir supaya ada warmup untuk EMA/ATR
    end_ms = int(t_last.timestamp() * 1000) + 3600_000
    start_ms = int(t_first.timestamp() * 1000) - 3 * 86400_000

    print("Fetching data...")
    data = {}
    for c in CFG:
        try:
            data[c] = {
                "5m": fetch(c, start_ms, end_ms),
                "15m": fetch(c, start_ms - 86400_000, end_ms),
                "1h": fetch(c, start_ms - 5 * 86400_000, end_ms),
            }
            print(f"  {c:<6} 5m={len(data[c]['5m'])}")
        except Exception as e:
            print(f"  {c:<6} ERR {e}")

    print("\n" + "=" * 100)
    print("BACKTEST PADA PERIODE LIVE YANG SAMA")
    print("=" * 100)
    print(f"{'STRATEGY':<14}{'N':>5}{'WR%':>7}{'PF':>7}{'TotR':>9}{'TP':>5}{'SL':>5}{'TIME':>6}")
    print("-" * 100)

    by_strat = {}
    for c, cc in CFG.items():
        if c not in data:
            continue
        for s in cc["strategies"]:
            try:
                tr = run_family(data[c]["5m"], data[c]["15m"], data[c]["1h"],
                                s["params"], s["name"])
                by_strat.setdefault(s["name"], []).extend(tr)
            except Exception as e:
                print(f"  {c} {s['name']} ERR {e}")

    for name, tr in by_strat.items():
        if not tr:
            continue
        n = len(tr)
        w = sum(1 for t in tr if t["R"] > 0)
        gw = sum(t["R"] for t in tr if t["R"] > 0)
        gl = abs(sum(t["R"] for t in tr if t["R"] <= 0))
        pf = gw / gl if gl else 99
        tot = sum(t["R"] for t in tr)
        tp = sum(1 for t in tr if t["outcome"] == "TP")
        sl_ = sum(1 for t in tr if t["outcome"] == "SL")
        tm = sum(1 for t in tr if t["outcome"] == "TIME")
        print(f"{name:<14}{n:>5}{w/n*100:>7.1f}{pf:>7.2f}{tot:>+9.1f}{tp:>5}{sl_:>5}{tm:>6}")

    # bandingkan dengan live
    print("\n" + "=" * 100)
    print("LIVE ACTUAL (periode sama)")
    print("=" * 100)
    for name in by_strat:
        lr = [r for r in rows if r["strategy"] == name]
        if not lr:
            continue
        n = len(lr)
        w = sum(1 for r in lr if r["R"] > 0)
        gw = sum(r["R"] for r in lr if r["R"] > 0)
        gl = abs(sum(r["R"] for r in lr if r["R"] <= 0))
        pf = gw / gl if gl else 0
        print(f"{name:<14}{n:>5}{w/n*100:>7.1f}{pf:>7.2f}{sum(r['R'] for r in lr):>+9.1f}")
