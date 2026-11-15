#!/usr/bin/env python3
"""
FORENSIK: kenapa 34 dari 46 trade kena SL?
Analisa MFE/MAE per trade dari data candle asli.
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


_cache = {}


def candles_range(coin, start_ms, end_ms):
    key = (coin, start_ms // 300000, end_ms // 300000)
    if key in _cache:
        return _cache[key]
    raw = post({"type": "candleSnapshot",
                "req": {"coin": coin, "interval": "5m",
                        "startTime": start_ms, "endTime": end_ms}})
    out = [{"t": k["t"], "o": float(k["o"]), "h": float(k["h"]),
            "l": float(k["l"]), "c": float(k["c"])} for k in raw]
    _cache[key] = out
    return out


rows = [json.loads(l) for l in open("/home/ubuntu/papertrade_backtest/fut_trades.jsonl") if l.strip()]
print(f"Total trade: {len(rows)}\n")

print("=" * 118)
print("FORENSIK PER TRADE: MFE (max profit) vs MAE (max drawdown) sebelum exit")
print("=" * 118)
print(f"{'TIME':<9}{'COIN':<6}{'DIR':<6}{'STRAT':<11}{'KIND':<5}{'R':>7}"
      f"{'MFE(R)':>8}{'MAE(R)':>8}{'bars':>6}{'SL hit bar':>11}")
print("-" * 118)

diag = []

for r in rows:
    coin = r["coin"]
    entry = r["entry"]
    exit_p = r["exit"]
    d = r["dir"]
    # risk = |entry - exit| kalau SL, tapi kalau TP kita perlu rekonstruksi
    # pakai risk dari R: R = (exit-entry)/risk -> risk = (exit-entry)/R
    if r["R"] == 0:
        continue
    raw_move = (exit_p - entry) if d == "LONG" else (entry - exit_p)
    # fee sudah dipotong di R, jadi risk dari R sedikit beda. pakai pendekatan
    risk_est = abs(raw_move / r["R"]) if r["R"] != 0 else 0
    if risk_est <= 0:
        continue

    t0 = datetime.fromisoformat(r["t"])
    start_ms = int(t0.timestamp() * 1000) - 3600_000
    end_ms = int(t0.timestamp() * 1000) + 8 * 3600_000

    try:
        cs = candles_range(coin, start_ms, end_ms)
    except Exception as e:
        continue
    if not cs:
        continue

    # cari candle entry (yang paling dekat dengan waktu trade)
    entry_ts = int(t0.timestamp() * 1000)
    idx = None
    for i, c in enumerate(cs):
        if c["t"] >= entry_ts:
            idx = i
            break
    if idx is None:
        continue

    # hitung MFE/MAE dari entry sampai exit
    mfe = 0.0
    mae = 0.0
    sl_bar = None
    for j in range(idx, min(idx + 100, len(cs))):
        c = cs[j]
        if d == "LONG":
            fav = (c["h"] - entry) / risk_est
            adv = (entry - c["l"]) / risk_est
        else:
            fav = (entry - c["l"]) / risk_est
            adv = (c["h"] - entry) / risk_est
        mfe = max(mfe, fav)
        mae = max(mae, adv)
        if sl_bar is None and adv >= 1.0:
            sl_bar = j - idx

    bars = sl_bar if sl_bar is not None else 0

    print(f"{r['t'][11:19]:<9}{coin:<6}{d:<6}{r['strategy'][:10]:<11}{r['kind']:<5}"
          f"{r['R']:>+7.2f}{mfe:>8.2f}{mae:>8.2f}{bars:>6}{str(sl_bar):>11}")

    diag.append({
        "coin": coin, "strategy": r["strategy"], "kind": r["kind"],
        "R": r["R"], "mfe": mfe, "mae": mae, "sl_bar": sl_bar,
        "near_miss": mfe >= 0.5 and r["R"] < 0,
    })

print("=" * 118)

# Analisa agregat
print("\n" + "=" * 100)
print("ANALISA AGREGAT")
print("=" * 100)

losers = [x for x in diag if x["R"] < 0]
winners = [x for x in diag if x["R"] > 0]

print(f"\nLOSERS ({len(losers)}):")
if losers:
    avg_mfe = sum(x["mfe"] for x in losers) / len(losers)
    near = [x for x in losers if x["near_miss"]]
    print(f"  avg MFE (max profit sempat diraih) : {avg_mfe:.2f}R")
    print(f"  trade yang SEMPAT profit >=0.5R    : {len(near)}/{len(losers)} ({len(near)/len(losers)*100:.0f}%)")
    print(f"  trade yang MFE < 0.3R (langsung mati): {sum(1 for x in losers if x['mfe']<0.3)}")
    slbars = [x["sl_bar"] for x in losers if x["sl_bar"] is not None]
    if slbars:
        print(f"  median bar sampai SL kena          : {sorted(slbars)[len(slbars)//2]} bar ({sorted(slbars)[len(slbars)//2]*5} menit)")
        print(f"  SL kena < 5 bar (25 menit)         : {sum(1 for b in slbars if b<5)}/{len(slbars)}")

print(f"\nWINNERS ({len(winners)}):")
if winners:
    avg_mfe = sum(x["mfe"] for x in winners) / len(winners)
    print(f"  avg MFE : {avg_mfe:.2f}R")

print("\n" + "=" * 100)
print("DIAGNOSA PER STRATEGI")
print("=" * 100)
from collections import defaultdict
by_strat = defaultdict(list)
for x in diag:
    by_strat[x["strategy"]].append(x)

for s, v in by_strat.items():
    n = len(v)
    w = sum(1 for x in v if x["R"] > 0)
    near = sum(1 for x in v if x["near_miss"])
    avg_mfe = sum(x["mfe"] for x in v) / n
    print(f"\n{s}: n={n} WR={w/n*100:.0f}%")
    print(f"  avg MFE     : {avg_mfe:.2f}R")
    print(f"  near-miss   : {near}/{n} (sempat +0.5R lalu berbalik)")
    print(f"  MFE < 0.3R  : {sum(1 for x in v if x['mfe']<0.3)}/{n} (langsung salah arah)")
