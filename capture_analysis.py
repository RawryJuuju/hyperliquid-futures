#!/usr/bin/env python3
"""Hitung capture rate: berapa persen edge yang berhasil ditangkap bot."""
import json

rows = [json.loads(l) for l in open("/home/ubuntu/papertrade_backtest/fut_trades.jsonl") if l.strip()]

# dari diag_result.txt
bt = {
    "sweep_fade": {"n": 68, "R": -20.4, "pf": 0.67, "wr": 20.6},
    "breakout":   {"n": 307, "R": 44.5, "pf": 1.20, "wr": 34.9},
    "bollinger":  {"n": 82, "R": 5.1, "pf": 1.10, "wr": 41.5},
}

print("=" * 92)
print("CAPTURE RATE: live vs backtest pada periode yang sama (17.2 jam)")
print("=" * 92)
print(f"{'STRATEGI':<14}{'BT_N':>6}{'LIVE_N':>8}{'CAPTURE%':>10}{'BT_R':>8}{'LIVE_R':>9}{'R_CAPTURE%':>12}")
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
print("ANALISA: BERAPA BANYAK EDGE YANG HILANG?")
print("=" * 92)
print(f"""
Backtest periode sama : {tot_bt:+.1f}R  (457 sinyal)
Live actual           : {tot_live:+.1f}R  (46 trade)
Edge tertangkap       : {tot_live/tot_bt*100:.1f}%
Edge HILANG           : {tot_bt-tot_live:+.1f}R  ({(1-tot_live/tot_bt)*100:.0f}%)

Penyebab utama:
1. Slot cuma 6 -> dari 457 sinyal, cuma 46 yang dieksekusi (10%)
2. Tiap posisi hold sampai TP/SL (bisa berjam-jam) -> throughput rendah
3. sweep_fade & bollinger makan slot, padahal breakout yang profit
""")

print("=" * 92)
print("SIMULASI: KALAU CUMA PAKAI BREAKOUT")
print("=" * 92)
print(f"{'SKENARIO':<38}{'SINYAL':>10}{'EST_R':>10}{'NOTE':<30}")
print("-" * 92)

# breakout only
print(f"{'Breakout saja (semua coin)':<38}{307:>10}{44.5:>+10.1f}{'full capture (teoretis)':<30}")

# dengan capture rate sama (10%)
cap = 46 / 457
est = 44.5 * cap
print(f"{'Breakout saja @ capture 10%':<38}{int(307*cap):>10}{est:>+10.1f}{'realistis dgn slot terbatas':<30}")

# kalau slot dinaikkan
for slots, mult in [(6, 1.0), (10, 1.67), (15, 2.5), (20, 3.33)]:
    est_n = min(307, int(46 * mult))
    est_r = 44.5 * (est_n / 307)
    print(f"{'Breakout, slot '+str(slots):<38}{est_n:>10}{est_r:>+10.1f}{'slot lebih banyak':<30}")

print("\n" + "=" * 92)
print("SIMULASI: MATIKAN sweep_fade + bollinger")
print("=" * 92)
# kalau slot dipakai breakout saja, capture naik
# 46 trade live sekarang: 23 breakout, 14 sweep, 9 bollinger
# kalau sweep+bollinger dimatikan, slot untuk breakout naik dari 23 ke ~46
mult = 46 / 23
est_n = min(307, int(23 * mult))
est_r = 44.5 * (est_n / 307)
print(f"Sekarang     : 23 breakout + 14 sweep + 9 bollinger = 46 trade, {tot_live:+.1f}R")
print(f"Breakout only: ~{est_n} trade breakout (slot penuh), est {est_r:+.1f}R")
print(f"Perbaikan    : {est_r - tot_live:+.1f}R")
