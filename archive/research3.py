#!/usr/bin/env python3
"""Round 3: ETH tuning + out-of-sample validation (IS = first 30d, OOS = last 30d)."""
from stratlib import fetch, run_v2, stats

if __name__ == "__main__":
    print("Fetching ETH 60d...")
    c5 = fetch("ETH", "5m", 60); c15 = fetch("ETH", "15m", 70); c1h = fetch("ETH", "1h", 90)
    print(f"5m={len(c5)} 15m={len(c15)} 1h={len(c1h)}")

    mid = len(c5)//2
    oos5 = c5[mid:]

    V = {
     "Q1_base":     dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=2.0,ttl=5,max_hold=60,require_slope=True,min_body=0.45,be_at=1.0),
     "Q2_strength": dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=2.0,ttl=5,max_hold=60,require_slope=True,min_body=0.45,min_strength=1.0,be_at=1.0),
     "Q3_s15":      dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=2.0,ttl=5,max_hold=60,require_slope=True,min_body=0.45,min_strength=1.5,be_at=1.0),
     "Q4_be08":     dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=2.0,ttl=5,max_hold=60,require_slope=True,min_body=0.45,min_strength=1.0,be_at=0.8),
     "Q5_rr25":     dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=2.5,ttl=5,max_hold=80,require_slope=True,min_body=0.45,min_strength=1.0,be_at=1.0),
     "Q6_rr15":     dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=1.5,ttl=5,max_hold=48,require_slope=True,min_body=0.45,min_strength=1.0,be_at=0.8),
     "Q7_look4":    dict(lookback=4,sl_model="atr",atr_mult=1.2,rr=2.0,ttl=4,max_hold=48,require_slope=True,min_body=0.45,min_strength=1.0,be_at=1.0),
     "Q8_look10":   dict(lookback=10,sl_model="atr",atr_mult=1.2,rr=2.0,ttl=6,max_hold=72,require_slope=True,min_body=0.45,min_strength=1.0,be_at=1.0),
     "Q9_atr15":    dict(lookback=6,sl_model="atr",atr_mult=1.5,rr=2.0,ttl=5,max_hold=60,require_slope=True,min_body=0.45,min_strength=1.0,be_at=1.0),
     "Q10_atr10":   dict(lookback=6,sl_model="atr",atr_mult=1.0,rr=2.0,ttl=5,max_hold=60,require_slope=True,min_body=0.45,min_strength=1.0,be_at=1.0),
     "Q11_ttl8":    dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=2.0,ttl=8,max_hold=60,require_slope=True,min_body=0.45,min_strength=1.0,be_at=1.0),
     "Q12_hold96":  dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=2.0,ttl=5,max_hold=96,require_slope=True,min_body=0.45,min_strength=1.0,be_at=1.0),
    }

    print("\n" + "="*108)
    print(f"{'VARIANT':<14}{'N':>5}{'WR%':>7}{'PF':>7}{'TotR':>8}{'AvgR':>7}{'MaxDD':>8}{'TP':>5}{'BEP':>5}{'TIME':>6}   || OOS")
    print("="*108)
    rows=[]
    for name,cfg in V.items():
        tr = run_v2(c5,c15,c1h,cfg); st = stats(tr,name)
        tro = run_v2(oos5,c15,c1h,cfg); so = stats(tro,name)
        if st["n"]==0: continue
        rows.append((name,st,so))
        print(f"{name:<14}{st['n']:>5}{st['wr']:>7.1f}{st['pf']:>7.2f}{st['totR']:>8.1f}{st['avgR']:>7.2f}{st['mdd']:>8.1f}{st['TP']:>5}{st['BEP']:>5}{st['TIME']:>6}   || N={so.get('n',0):>3} PF={so.get('pf',0):>5.2f} TotR={so.get('totR',0):>6.1f}")

    print("\n=== TOP 6 by full-60d TotR ===")
    for name,st,so in sorted(rows,key=lambda x:-x[1]["totR"])[:6]:
        print(f"  {name:<14} 60d: N={st['n']:>3} PF={st['pf']:>5.2f} TotR={st['totR']:>6.1f} WR={st['wr']:>5.1f}% | OOS: N={so.get('n',0):>3} PF={so.get('pf',0):>5.2f} TotR={so.get('totR',0):>6.1f}")
