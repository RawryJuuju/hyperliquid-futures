#!/usr/bin/env python3
"""Hitung SL aktual + margin + kelayakan 3 kandidat finalis."""
import json, urllib.request, time

HL = "https://api.hyperliquid.xyz/info"
EQUITY = 991.59
CAND = json.load(open("/home/ubuntu/papertrade_backtest/candidate_coins.json"))


def post(p):
    r = urllib.request.Request(HL, data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.loads(resp.read().decode())


def candles(coin, limit=200):
    start = int(time.time() * 1000) - limit * 300_000
    raw = post({"type": "candleSnapshot",
                "req": {"coin": coin, "interval": "5m", "startTime": start}})
    return [{"h": float(k["h"]), "l": float(k["l"]), "c": float(k["c"])} for k in raw]


def atr(cs, p=14):
    trs = []
    for i in range(1, len(cs)):
        h, l, pc = cs[i]["h"], cs[i]["l"], cs[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-p:]) / p


meta = post({"type": "meta"})
maxlev = {a["name"]: a.get("maxLeverage", 10) for a in meta["universe"]}

print("=" * 96)
print(f"{'COIN':<8}{'ATR%':>7}{'SL%':>7}{'MAXLEV':>8}{'LIQ':>7}{'BUFFER':>8}{'MARGIN':>10}{'FEE/RISK':>10}{'OK?':>6}")
print("=" * 96)

# bobot: pakai rata-rata weight existing (0.0989) sebagai asumsi awal
ASSUME_W = 0.09
MAX_W = 0.198
BASE = 0.55

for c, info in CAND.items():
    cs = candles(c)
    a = atr(cs)
    price = cs[-1]["c"]
    atr_pct = a / price * 100
    sl_pct = atr_pct * info["params"]["atr_mult"]

    ml = maxlev.get(c, 10)
    # leverage pilih: min(maxlev, yg kasih buffer >= 2.5x)
    lev = max(3, min(ml, int(100 / (sl_pct * 2.5))))
    liq = 100 / lev
    buffer = liq / sl_pct

    rp = BASE * ASSUME_W / MAX_W
    ru = EQUITY * rp / 100
    notional = ru / (sl_pct / 100)
    margin = notional / lev
    fee_ratio = 0.0008 / (sl_pct / 100) * 100

    ok = "YES" if buffer >= 2.5 and margin < EQUITY * 0.35 else "NO"
    print(f"{c:<8}{atr_pct:>7.3f}{sl_pct:>7.3f}{ml:>7}x{liq:>6.1f}%{buffer:>7.1f}x"
          f"{margin:>9.0f}${fee_ratio:>9.1f}%{ok:>6}")

print("=" * 96)
print(f"asumsi: base_risk {BASE}%, weight 0.09 (rata-rata), equity ${EQUITY}")
print()
print("=== SIMULASI TAMBAH KE PORTFOLIO ===")
print()
print("Skenario: 9 coin existing + kandidat, buka 6 posisi max")
print()

# existing weights
CFG = json.load(open("/home/ubuntu/papertrade_backtest/strategy_config.json"))
ex_w = {c: v["weight"] for c, v in CFG["coins"].items()}
print(f"total weight existing: {sum(ex_w.values()):.3f}")
print(f"kalau tambah 1 coin weight 0.09 -> total {sum(ex_w.values())+0.09:.3f}")
print("-> weight semua coin harus dinormalisasi ulang (dibagi total baru)")
print()
print("Dampak: weight coin existing turun ~8.3%, risk per coin turun proporsional")
print("Tapi jumlah posisi bertambah -> diversifikasi naik")
