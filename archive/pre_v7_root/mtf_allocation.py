#!/usr/bin/env python3
"""
ALOKASI RISK MULTI-TIMEFRAME
============================
Principle: higher TF = higher conviction, fewer signals, larger risk per trade.
         Lower TF = more noise, more signals, smaller risk per trade.

Input: real per-TF metrics from research_mtf.
Output: per-TF risk allocation, portfolio simulation, and psychological profile.
"""
import math

# from mtf_result2.txt (7 coin, breakout)
TF_DATA = {
    "5m":  {"n": 604, "days": 60,  "wr": 23.2, "pf": 1.07, "totR": 38.2,
            "avgR": 0.063, "mdd": -25.2, "hold_min": 91},
    "15m": {"n": 695, "days": 90,  "wr": 29.8, "pf": 1.34, "totR": 173.0,
            "avgR": 0.249, "mdd": -21.5, "hold_min": 221},
    "1h":  {"n": 208, "days": 180, "wr": 34.1, "pf": 1.51, "totR": 70.0,
            "avgR": 0.336, "mdd": -12.2, "hold_min": 1258},
    "4h":  {"n": 50,  "days": 365, "wr": 34.0, "pf": 1.18, "totR": 5.6,
            "avgR": 0.113, "mdd": -9.8,  "hold_min": 3254},
}

EQUITY = 950.0
CAP_RISK = 2.25          # % equity total open risk
BASE = 0.25              # % base risk saat ini


def kelly_fraction(pf, wr, avg_win=5.0, avg_loss=1.0):
    """Kelly fraction from PF and WR (approx)."""
    p = wr / 100
    q = 1 - p
    b = avg_win / avg_loss
    f = (p * b - q) / b
    return max(0.0, min(f, 0.25))   # cap 25% Kelly


print("=" * 112)
print("METRIK PER TIMEFRAME")
print("=" * 112)
print(f"{'TF':<6}{'N':>6}{'N/day':>8}{'WR%':>7}{'PF':>7}{'AvgR':>8}{'R/day':>9}"
      f"{'MaxDD':>8}{'Hold':>9}{'Kelly':>8}")
print("-" * 112)

for tf, d in TF_DATA.items():
    nday = d["n"] / d["days"]
    rday = d["totR"] / d["days"]
    k = kelly_fraction(d["pf"], d["wr"])
    hold = f"{d['hold_min']/60:.1f}h" if d["hold_min"] >= 60 else f"{d['hold_min']}m"
    print(f"{tf:<6}{d['n']:>6}{nday:>8.1f}{d['wr']:>7.1f}{d['pf']:>7.2f}"
          f"{d['avgR']:>+8.3f}{rday:>+9.2f}{d['mdd']:>8.1f}{hold:>9}{k:>7.2f}")

print("\n" + "=" * 112)
print("ALOKASI RISK: 3 MODEL")
print("=" * 112)

# --- Model A: Risk parity (every TF gets the same risk) ---
print("\n[A] RISK PARITY — every TF gets identical risk")
print(f"{'TF':<6}{'risk%':>8}{'est trades/day':>16}{'est R/day':>11}{'notes':<30}")
print("-" * 112)
for tf, d in TF_DATA.items():
    nday = d["n"] / d["days"]
    rday = d["totR"] / d["days"]
    print(f"{tf:<6}{BASE:>7.2f}%{nday:>16.1f}{rday:>+11.2f}{'identical risk across TFs':<30}")

# --- Model B: Conviction-weighted (TF large = risk larger) ---
print("\n[B] CONVICTION-WEIGHTED — TF large risk larger (psikologi trader)")
print(f"{'TF':<6}{'weight':>8}{'risk%':>8}{'est trades/day':>16}{'est R/day':>11}{'notes':<26}")
print("-" * 112)

conviction = {"5m": 0.6, "15m": 1.0, "1h": 1.8, "4h": 2.5}
total_conv = sum(conviction.values())
conv_alloc = {}
for tf, d in TF_DATA.items():
    w = conviction[tf] / total_conv
    risk = CAP_RISK * w
    conv_alloc[tf] = risk
    nday = d["n"] / d["days"]
    rday = d["totR"] / d["days"]
    note = {"5m": "noise high, size small", "15m": "workhorse",
            "1h": "high conviction", "4h": "very few signals"}[tf]
    print(f"{tf:<6}{w:>7.2f}{risk:>7.2f}%{nday:>16.1f}{rday:>+11.2f}{note:<26}")
print(f"{'TOTAL':<6}{1.0:>7.2f}{sum(conv_alloc.values()):>7.2f}%")

# --- Model C: R/day optimized (drop TF lemah) ---
print("\n[C] R/DAY OPTIMIZED — only TFs with R/day > 0.5")
print(f"{'TF':<6}{'R/day':>9}{'status':>10}{'risk%':>8}{'est R/day':>11}")
print("-" * 112)
good = {tf: d for tf, d in TF_DATA.items() if d["totR"] / d["days"] > 0.5}
total_rday = sum(d["totR"] / d["days"] for d in good.values())
for tf, d in TF_DATA.items():
    rday = d["totR"] / d["days"]
    if tf in good:
        w = rday / total_rday
        risk = CAP_RISK * w
        print(f"{tf:<6}{rday:>+9.2f}{'KEEP':>10}{risk:>7.2f}%{rday:>+11.2f}")
    else:
        print(f"{tf:<6}{rday:>+9.2f}{'DROP':>10}{0:>7.2f}%{0:>+11.2f}")

print("\n" + "=" * 112)
print("PORTFOLIO SIMULATION: 30 days")
print("=" * 112)
print(f"{'MODEL':<26}{'active TFs':<22}{'est trades':>12}{'est R':>10}{'est USD':>12}{'worst DD':>10}")
print("-" * 112)

for name, alloc in [("A: Risk parity", {tf: BASE for tf in TF_DATA}),
                    ("B: Conviction", conv_alloc),
                    ("C: R/day optimized", {tf: CAP_RISK * (d["totR"]/d["days"]) / total_rday
                                            if tf in good else 0
                                            for tf, d in TF_DATA.items()})]:
    active = [tf for tf, r in alloc.items() if r > 0]
    est_trades = sum(TF_DATA[tf]["n"] / TF_DATA[tf]["days"] * 30 for tf in active)
    # R/day diskalakan oleh risk allocation vs base
    est_r = sum((TF_DATA[tf]["totR"] / TF_DATA[tf]["days"]) * (alloc[tf] / BASE)
                for tf in active) * 30
    est_usd = est_r * (EQUITY * BASE / 100)
    worst = min(TF_DATA[tf]["mdd"] for tf in active) if active else 0
    print(f"{name:<26}{','.join(active):<22}{est_trades:>12.0f}{est_r:>+10.1f}"
          f"{est_usd:>+12.0f}{worst:>10.1f}")

print("\n" + "=" * 112)
print("PROFIL PSIKOLOGIS PER TIMEFRAME")
print("=" * 112)
print(f"{'TF':<6}{'trades/day':>12}{'hold time':>12}{'screen time':>14}{'stress level':<22}")
print("-" * 112)
prof = {
    "5m":  ("10.1", "91 minutes",  "4-6 hours/days", "high - overtrade risk"),
    "15m": ("7.7",  "3.7 hours",   "2-3 hours/days", "currently - manageable"),
    "1h":  ("1.2",  "21 hours",    "30 min/days",  "low - sabar"),
    "4h":  ("0.1",  "54 hours",    "15 min/day",  "VERY low - nearly idle"),
}
for tf, (nd, hold, screen, stress) in prof.items():
    print(f"{tf:<6}{nd:>12}{hold:>12}{screen:>14}{stress:<22}")
