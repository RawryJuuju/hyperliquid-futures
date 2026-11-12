#!/usr/bin/env python3
"""
Money Management Research — pakai trade list riil dari config terpilih.
Hitung: expectancy, correlation antar koin, equity curve di berbagai risk%,
optimal fixed-fractional, dan simulasi Monte Carlo drawdown.
"""
import json, random, statistics
from engine import fetch, FAMILIES

CFG = json.load(open("/home/ubuntu/papertrade_backtest/strategy_config.json"))["coins"]
START_EQUITY = 1000.0

def get_trades(coin, cfg):
    d = {"5m": fetch(coin, "5m", 120), "15m": fetch(coin, "15m", 130), "1h": fetch(coin, "1h", 170)}
    fn = FAMILIES[cfg["family"]]
    t = fn(d["5m"], d["15m"], d["1h"], cfg["params"])
    return [x["R"] for x in t]

def stats_of(rs):
    if not rs: return None
    n = len(rs); w = sum(1 for r in rs if r > 0)
    gw = sum(r for r in rs if r > 0); gl = abs(sum(r for r in rs if r <= 0))
    return {"n": n, "wr": w/n*100, "pf": gw/gl if gl else 99,
            "avg": sum(rs)/n, "tot": sum(rs)}

def max_dd(curve):
    peak = curve[0]; mdd = 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = min(mdd, (v-peak)/peak)
    return mdd*100

if __name__ == "__main__":
    print("Fetching trades for all coins...\n")
    all_trades = {}
    for coin, cfg in CFG.items():
        try:
            rs = get_trades(coin, cfg)
            all_trades[coin] = rs
            s = stats_of(rs)
            print(f"  {coin:<6} {cfg['family']:<12} N={s['n']:<3} WR={s['wr']:5.1f}% "
                  f"PF={s['pf']:5.2f} avg={s['avg']:+.3f}R tot={s['tot']:+.1f}R")
        except Exception as e:
            print(f"  {coin:<6} ERR {e}")

    print("\n" + "="*78)
    print("EXPECTANCY RANKING (avg R per trade)")
    print("="*78)
    rows = [(c, stats_of(r)) for c, r in all_trades.items() if r]
    for c, s in sorted(rows, key=lambda x: -x[1]["avg"]):
        print(f"  {c:<6} avg={s['avg']:+.4f}R  PF={s['pf']:5.2f}  N={s['n']:<3} tot={s['tot']:+.1f}R")

    # ---- correlation of trade outcomes is tricky (different timestamps).
    # Use daily-aggregated PnL instead: approximate by splitting each list into 5 buckets.
    print("\n" + "="*78)
    print("CORRELATION (bucket-aggregated R, 5 buckets per coin)")
    print("="*78)
    buckets = {}
    for c, rs in all_trades.items():
        if not rs: continue
        k = 5
        size = max(1, len(rs)//k)
        b = [sum(rs[i*size:(i+1)*size]) for i in range(k)]
        buckets[c] = b
    coins = list(buckets.keys())
    print("      " + "".join(f"{c:>7}" for c in coins))
    for a in coins:
        line = f"{a:<6}"
        for b in coins:
            if a == b:
                line += f"{'1.00':>7}"
            else:
                try:
                    ca = buckets[a]; cb = buckets[b]
                    m = min(len(ca), len(cb))
                    line += f"{statistics.correlation(ca[:m], cb[:m]):>7.2f}"
                except Exception:
                    line += f"{'-':>7}"
        print(line)

    # ---- portfolio equity at various risk fractions
    print("\n" + "="*78)
    print("PORTFOLIO EQUITY SIMULATION ($1000 start, fixed-fractional risk)")
    print("="*78)

    # interleave trades round-robin across coins (approximates concurrent operation)
    seq = []
    maxlen = max(len(r) for r in all_trades.values() if r)
    for i in range(maxlen):
        for c in coins:
            if i < len(all_trades[c]):
                seq.append(all_trades[c][i])

    print(f"  total sequential trades: {len(seq)}")
    print(f"\n{'risk%':>7}{'final$':>12}{'return%':>10}{'maxDD%':>9}{'CAGR-ish':>10}{'ruin?':>7}")
    print("-"*58)
    best = None
    for risk_pct in [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
        eq = START_EQUITY
        curve = [eq]
        ruined = False
        for R in seq:
            eq += eq * (risk_pct/100) * R
            if eq <= 1:
                eq = 0; ruined = True; curve.append(0); break
            curve.append(eq)
        mdd = max_dd(curve)
        ret = (eq/START_EQUITY - 1)*100
        print(f"{risk_pct:>6.2f}%{eq:>12,.0f}{ret:>9.1f}%{mdd:>8.1f}%{'':>10}{'YES' if ruined else 'no':>7}")
        # score: return per unit of drawdown
        if not ruined:
            score = ret / abs(mdd) if mdd else ret
            if best is None or score > best[1]:
                best = (risk_pct, score, eq, ret, mdd)

    print(f"\n  OPTIMAL by return/DD ratio: risk = {best[0]}%  ->  ${best[2]:,.0f} ({best[3]:+.1f}%) DD {best[4]:.1f}%")

    # ---- Monte Carlo: shuffle trade order, measure DD distribution
    print("\n" + "="*78)
    print("MONTE CARLO (500 shuffles) — drawdown & ruin risk")
    print("="*78)
    for risk_pct in [0.5, 1.0, 2.0, 3.0]:
        random.seed(42)
        dds = []; finals = []; ruins = 0
        for _ in range(500):
            s = seq[:]
            random.shuffle(s)
            eq = START_EQUITY; curve = [eq]; ruined = False
            for R in s:
                eq += eq * (risk_pct/100) * R
                if eq <= 1:
                    eq = 0; ruined = True; break
                curve.append(eq)
            dds.append(max_dd(curve))
            finals.append(eq)
            if ruined: ruins += 1
        finals.sort()
        print(f"  risk {risk_pct:>4.2f}%: DD median {statistics.median(dds):6.1f}% | "
              f"worst {min(dds):6.1f}% | final median ${statistics.median(finals):,.0f} | "
              f"P5 ${finals[int(len(finals)*0.05)]:,.0f} | ruin {ruins/500*100:.1f}%")

    # ---- per-coin allocation proposal (weight by expectancy, cap by N confidence)
    print("\n" + "="*78)
    print("PROPOSED ALLOCATION (edge-weighted, confidence-adjusted)")
    print("="*78)
    total_score = 0
    scores = {}
    for c, s in rows:
        # weight = avg_R * sqrt(N)  -> reward edge, penalize small sample
        sc = max(0.0, s["avg"]) * (s["n"] ** 0.5)
        scores[c] = sc
        total_score += sc
    print(f"{'COIN':<7}{'avgR':>8}{'N':>5}{'weight':>9}{'risk/trade%':>13}")
    print("-"*44)
    for c in sorted(scores, key=lambda x: -scores[x]):
        s = stats_of(all_trades[c])
        w = scores[c]/total_score if total_score else 0
        # normalize: total portfolio risk per trade target = 1.0% of equity
        risk = w * 1.0
        print(f"{c:<7}{s['avg']:>+8.3f}{s['n']:>5}{w*100:>8.1f}%{risk:>12.3f}%")
