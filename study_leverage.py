#!/usr/bin/env python3
"""
Studi mendalam: leverage, fee drag, margin, likuidasi, dan sizing optimal.
Tujuan: tentukan parameter final untuk 9 coin dengan bukti angka.
"""
import json, urllib.request, time

HL = "https://api.hyperliquid.xyz/info"
COINS = ["PUMP", "WLD", "ZEC", "ENA", "NEAR", "HYPE", "ETH", "SOL", "XRP"]
CFG = json.load(open("/home/ubuntu/papertrade_backtest/strategy_config.json"))
EQUITY = 991.59
FEE_ROUNDTRIP = 0.0008  # 0.04% open + 0.04% close


def post(payload):
    r = urllib.request.Request(HL, data=json.dumps(payload).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.loads(resp.read().decode())


def candles(coin, interval="5m", limit=200):
    start = int(time.time() * 1000) - limit * 300_000
    raw = post({"type": "candleSnapshot",
                "req": {"coin": coin, "interval": interval, "startTime": start}})
    return [{"h": float(k["h"]), "l": float(k["l"]), "c": float(k["c"])} for k in raw]


def atr(cs, p=14):
    trs = []
    for i in range(1, len(cs)):
        h, l, pc = cs[i]["h"], cs[i]["l"], cs[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-p:]) / p


meta = post({"type": "meta"})
maxlev = {a["name"]: a.get("maxLeverage", 10) for a in meta["universe"]}

print("=" * 100)
print("BAGIAN 1: APAKAH LEVERAGE MEMPENGARUHI FEE DRAG?")
print("=" * 100)
print()
print("fee_dollar = notional x 0.08%")
print("risk_dollar = notional x SL%")
print("fee/risk = 0.08% / SL%   <-- LEVERAGE TIDAK MUNCUL DI RUMUS")
print()

print("=" * 100)
print("BAGIAN 2: SL AKTUAL 9 COIN + FEE DRAG + LEVERAGE AMAN")
print("=" * 100)
print(f"{'COIN':<7}{'ATR%':>7}{'SL%':>7}{'FEE/RISK':>10}{'MAXLEV':>8}{'LEV PILIH':>11}"
      f"{'LIQ':>7}{'BUFFER':>8}{'MARGIN':>9}{'RISK$':>8}")
print("-" * 100)

rows = []
for c in COINS:
    cc = CFG["coins"][c]
    mults = [s["params"]["atr_mult"] for s in cc["strategies"]]
    atr_mult = sum(mults) / len(mults)

    cs = candles(c)
    a = atr(cs)
    price = cs[-1]["c"]
    atr_pct = a / price * 100
    sl_pct = atr_pct * atr_mult

    fee_ratio = FEE_ROUNDTRIP / (sl_pct / 100) * 100

    ml = maxlev.get(c, 10)
    # pilih leverage: max lev dikurangi buffer, minimal liq >= 2.5x SL
    lev_safe_by_sl = int(100 / (sl_pct * 2.5))
    lev = max(3, min(ml, lev_safe_by_sl))

    liq = 100 / lev
    buffer = liq / sl_pct

    risk_pct = 0.0075 * cc["weight"] / 0.198
    risk_usd = EQUITY * risk_pct
    notional = risk_usd / (sl_pct / 100)
    margin = notional / lev

    rows.append({"coin": c, "atr_pct": atr_pct, "sl_pct": sl_pct, "fee_ratio": fee_ratio,
                 "maxlev": ml, "lev": lev, "liq": liq, "buffer": buffer,
                 "margin": margin, "risk_usd": risk_usd, "notional": notional,
                 "weight": cc["weight"], "cluster": cc["cluster"]})

    print(f"{c:<7}{atr_pct:>7.3f}{sl_pct:>7.3f}{fee_ratio:>9.1f}%{ml:>7}x{lev:>10}x"
          f"{liq:>6.1f}%{buffer:>7.1f}x{margin:>8.0f}${risk_usd:>7.2f}")

print("-" * 100)
print(f"total margin semua 9 coin: ${sum(r['margin'] for r in rows):.0f}")
print(f"total risk semua 9 coin  : ${sum(r['risk_usd'] for r in rows):.2f} "
      f"({sum(r['risk_usd'] for r in rows)/EQUITY*100:.2f}% equity)")

print()
print("=" * 100)
print("BAGIAN 3: KALIBRASI BASE RISK agar 6 POSISI MUAT DI CAP 2.25%")
print("=" * 100)
print()
avg_w = sum(r["weight"] for r in rows) / len(rows)
max_w = max(r["weight"] for r in rows)

for base in [0.75, 0.70, 0.65, 0.60, 0.55, 0.50]:
    # worst case: 6 coin dengan weight tertinggi
    top6 = sorted(rows, key=lambda r: -r["weight"])[:6]
    tot_risk_pct = sum(base * r["weight"] / max_w for r in top6)
    tot_margin = 0
    for r in top6:
        rp = base * r["weight"] / max_w
        ru = EQUITY * rp / 100
        no = ru / (r["sl_pct"] / 100)
        tot_margin += no / r["lev"]
    margin_pct = tot_margin / EQUITY * 100
    status = "OK" if tot_risk_pct <= 2.25 and margin_pct <= 60 else "OVER"
    print(f"base {base:.2f}%: 6 posisi -> risk {tot_risk_pct:.2f}% | margin {margin_pct:.1f}% | {status}")

print()
print("=" * 100)
print("BAGIAN 4: SIMULASI 6 POSISI REALISTIS (pilih 6 coin terberat SL)")
print("=" * 100)
print()
worst6 = sorted(rows, key=lambda r: -r["sl_pct"])[:6]
print("coin dipilih:", ", ".join(r["coin"] for r in worst6))
print()
print(f"{'BASE':<8}{'risk total':>12}{'margin total':>14}{'margin %':>10}{'status':>8}")
print("-" * 60)
for base in [0.75, 0.65, 0.60, 0.55]:
    tr = 0
    tm = 0
    for r in worst6:
        rp = base * r["weight"] / max_w
        ru = EQUITY * rp / 100
        no = ru / (r["sl_pct"] / 100)
        tr += rp
        tm += no / r["lev"]
    mp = tm / EQUITY * 100
    st = "OK" if tr <= 2.25 and mp <= 60 else "OVER"
    print(f"{base:.2f}%{tr:>11.2f}%{tm:>13.0f}${mp:>9.1f}%{st:>8}")

print()
print("=" * 100)
print("BAGIAN 5: RISIKO LIKUIDASI — seberapa aman buffer?")
print("=" * 100)
print()
for r in sorted(rows, key=lambda x: x["buffer"]):
    status = "AMAN" if r["buffer"] >= 2.5 else ("MEPET" if r["buffer"] >= 1.5 else "BAHAYA")
    print(f"  {r['coin']:<6} lev={r['lev']:>2}x  liq={r['liq']:>5.1f}%  SL={r['sl_pct']:>5.2f}%  "
          f"buffer={r['buffer']:>4.1f}x  {status}")
