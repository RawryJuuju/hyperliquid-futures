#!/usr/bin/env python3
"""Compute capture rate: what share of the edge the bot actually captured."""
import json

rows = [json.loads(l) for l in open("/home/ubuntu/hl-futures-engine/fut_trades.jsonl") if l.strip()]

# from diag_result.txt
bt = {
    "sweep_fade": {"n": 68, "R": -20.4, "pf": 0.67, "wr": 20.6},
    "breakout":   {"n": 307, "R": 44.5, "pf": 1.20, "wr": 34.9},
    "bollinger":  {"n": 82, "R": 5.1, "pf": 1.10, "wr": 41.5},
}

print("=" * 92)
print("CAPTURE RATE: live vs backtest over the same window (17.2 hours)")
print("=" * 92)
print(f"{'strategy':<14}{'BT_N':>6}{'LIVE_N':>8}{'CAPTURE%':>10}{'BT_R':>8}{'LIVE_R':>9}{'R_CAPTURE%':>12}")
print("-" * 92)

for name, b in bt.items():
    lr = [r for r in rows if r["strategy"] == name]
    live_n = len(lr)
    live_R = sum(r["R"] for r in lr)
    cap_n = live_n / b["n"] * 100
    cap_r = (live_R / b["R"] * 100) if b["R"] != 0 else 0
    print(f"{name:<14}{b['n']:>6}{live_n:>8}{cap_n:>9.1f}%{b['R']:>+8.1f}{live_R:>+9.1f}{cap_r:>11.1f}%")

print("-" * 92)
tot_bt = sum(b["R"] for b in bt.values())
tot_live = sum(r["R"] for r in rows)
print(f"{'TOTAL':<14}{sum(b['n'] for b in bt.values()):>6}{len(rows):>8}"
      f"{len(rows)/sum(b['n'] for b in bt.values())*100:>9.1f}%"
      f"{tot_bt:>+8.1f}{tot_live:>+9.1f}{tot_live/tot_bt*100:>11.1f}%")

print("\n" + "=" * 92)
print("ANALYSIS: HOW MUCH EDGE IS LOST?")
print("=" * 92)
print(f"""
Backtest same window  : {tot_bt:+.1f}R  (457 signals)
Live actual           : {tot_live:+.1f}R  (46 trade)
Edge tertangkap       : {tot_live/tot_bt*100:.1f}%
Edge LOST            : {tot_bt-tot_live:+.1f}R  ({(1-tot_live/tot_bt)*100:.0f}%)

Penyebab utama:
1. Only 6 slots -> of 457 signals, just 46 were executed (10%)
2. Every position holds to TP/SL (can be hours) -> low throughput
3. sweep_fade & bollinger makan slot, padahal breakout that profit
""")

print("=" * 92)
print("SIMULATION: IF WE USED BREAKOUT ONLY")
print("=" * 92)
print(f"{'SCENARIO':<38}{'signal':>10}{'EST_R':>10}{'NOTE':<30}")
print("-" * 92)

# breakout only
print(f"{'Breakout only (all coins)':<38}{307:>10}{44.5:>+10.1f}{'full capture (teoretis)':<30}")

# with capture rate sama (10%)
cap = 46 / 457
est = 44.5 * cap
print(f"{'Breakout only @ capture 10%':<38}{int(307*cap):>10}{est:>+10.1f}{'realistis dgn slot terbatas':<30}")

# if slot dinaikkan
for slots, mult in [(6, 1.0), (10, 1.67), (15, 2.5), (20, 3.33)]:
    est_n = min(307, int(46 * mult))
    est_r = 44.5 * (est_n / 307)
    print(f"{'Breakout, slot '+str(slots):<38}{est_n:>10}{est_r:>+10.1f}{'more slots':<30}")

print("\n" + "=" * 92)
print("SIMULATION: DISABLE sweep_fade + bollinger")
print("=" * 92)
# if slots were breakout-only, capture rises
# 46 live trades so far: 23 breakout, 14 sweep, 9 bollinger
# if sweep+bollinger were disabled, breakout slots rise from 23 to ~46
mult = 46 / 23
est_n = min(307, int(23 * mult))
est_r = 44.5 * (est_n / 307)
print(f"Current      : 23 breakout + 14 sweep + 9 bollinger = 46 trades, {tot_live:+.1f}R")
print(f"Breakout only: ~{est_n} trade breakout (slot penuh), est {est_r:+.1f}R")
print(f"Perbaikan    : {est_r - tot_live:+.1f}R")
