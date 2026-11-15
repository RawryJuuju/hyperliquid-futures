#!/usr/bin/env python3
"""Round 5: cari frekuensi lebih tinggi di ETH tanpa ngerusak PF.
Target: >=40 trade / 90d, PF >= 1.25."""
from stratlib import fetch, run_v2, stats

if __name__ == "__main__":
    print("Fetching ETH 90d...")
    c5 = fetch("ETH","5m",90); c15 = fetch("ETH","15m",100); c1h = fetch("ETH","1h",130)

    base = dict(lookback=6, sl_model="atr", atr_mult=1.0, rr=2.0, ttl=5, max_hold=60,
                require_slope=True, min_body=0.45, min_strength=1.0, be_at=1.0)

    V = {
      "R0_lock":      dict(base),
      "R1_ttl8":      {**base, "ttl":8},
      "R2_ttl12":     {**base, "ttl":12},
      "R3_ttl12_l4":  {**base, "ttl":12, "lookback":4},
      "R4_ttl12_l8":  {**base, "ttl":12, "lookback":8},
      "R5_ttl12_s05": {**base, "ttl":12, "min_strength":0.5},
      "R6_ttl12_s0":  {**base, "ttl":12, "min_strength":0.0},
      "R7_ttl12_b35": {**base, "ttl":12, "min_body":0.35},
      "R8_ttl20":     {**base, "ttl":20},
      "R9_ttl20_l4":  {**base, "ttl":20, "lookback":4},
      "R10_noslope":  {**base, "ttl":12, "require_slope":False},
      "R11_rr25":     {**base, "ttl":12, "rr":2.5, "max_hold":80},
      "R12_rr15":     {**base, "ttl":12, "rr":1.5, "max_hold":48},
      "R13_be08":     {**base, "ttl":12, "be_at":0.8},
      "R14_atr08":    {**base, "ttl":12, "atr_mult":0.8},
      "R15_atr14":    {**base, "ttl":12, "atr_mult":1.4},
    }

    print("\n" + "="*100)
    print(f"{'VARIANT':<16}{'N':>5}{'WR%':>7}{'PF':>7}{'TotR':>8}{'AvgR':>7}{'MaxDD':>8}{'TP':>5}{'BEP':>5}{'TIME':>6}{'Bars':>6}")
    print("="*100)
    rows=[]
    for name,cfg in V.items():
        tr = run_v2(c5,c15,c1h,cfg); st = stats(tr,name)
        if st["n"]==0: continue
        rows.append((name,st))
        print(f"{name:<16}{st['n']:>5}{st['wr']:>7.1f}{st['pf']:>7.2f}{st['totR']:>8.1f}{st['avgR']:>7.2f}{st['mdd']:>8.1f}{st['TP']:>5}{st['BEP']:>5}{st['TIME']:>6}{st['avgBars']:>6.1f}")

    print("\n=== FILTER: N>=35 AND PF>=1.20, ranked by TotR ===")
    good=[(n,s) for n,s in rows if s["n"]>=35 and s["pf"]>=1.20]
    for n,s in sorted(good,key=lambda x:-x[1]["totR"]):
        print(f"  {n:<16} N={s['n']:>3} PF={s['pf']:>5.2f} WR={s['wr']:>5.1f}% TotR={s['totR']:>+6.1f} DD={s['mdd']:>5.1f}")
    if not good:
        print("  (tidak ada yang lolos — frekuensi vs kualitas trade-off keras)")
        print("\n=== SEMUA, ranked by TotR ===")
        for n,s in sorted(rows,key=lambda x:-x[1]["totR"])[:8]:
            print(f"  {n:<16} N={s['n']:>3} PF={s['pf']:>5.2f} WR={s['wr']:>5.1f}% TotR={s['totR']:>+6.1f}")
