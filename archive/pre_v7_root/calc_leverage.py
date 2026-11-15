#!/usr/bin/env python3
"""Hitung SL distance (ATR-based) + margin + leverage aman untuk 9 coin."""
import json, urllib.request, time

HL = "https://api.hyperliquid.xyz/info"
COINS = ["PUMP", "WLD", "ZEC", "ENA", "NEAR", "HYPE", "ETH", "SOL", "XRP"]
CFG = json.load(open("/home/ubuntu/papertrade_backtest/strategy_config.json"))
EQUITY = 991.59


def post(payload):
    r = urllib.request.Request(HL, data=json.dumps(payload).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.loads(resp.read().decode())


def candles(coin, interval="5m", limit=100):
    step = 300_000
    start = int(time.time() * 1000) - limit * step
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

print("=" * 108)
print(f"{'COIN':<7}{'ATR%':>7}{'SL(AVR x)':>11}{'SL%':>8}{'MAXLEV':>8}{'LIQ@MAX':>9}"
      f"{'SAFE LEV':>10}{'MARGIN@10x':>12}{'LIQ@10x':>9}")
print("=" * 108)

rows = []
for c in COINS:
    cc = CFG["coins"][c]
    # ambil atr_mult rata-rata dari semua strategi coin ini
    mults = [s["params"]["atr_mult"] for s in cc["strategies"]]
    atr_mult = sum(mults) / len(mults)

    cs = candles(c)
    a = atr(cs)
    price = cs[-1]["c"]
    atr_pct = a / price * 100
    sl_pct = atr_pct * atr_mult

    ml = maxlev.get(c, 10)
    liq_at_max = 100 / ml
    # leverage aman: liq distance minimal 2x SL
    safe_lev = min(ml, int(100 / (sl_pct * 2)))

    # risk_pct sebagai fraksi (0.0075 = 0.75%)
    risk_pct = 0.0075 * cc["weight"] / 0.198
    risk_usd = EQUITY * risk_pct
    notional = risk_usd / (sl_pct / 100)
    margin_10x = notional / 10

    rows.append({"coin": c, "atr_pct": atr_pct, "sl_pct": sl_pct, "maxlev": ml,
                 "liq_max": liq_at_max, "safe_lev": safe_lev,
                 "margin10": margin_10x, "risk_usd": risk_usd,
                 "notional": notional, "weight": cc["weight"]})

    print(f"{c:<7}{atr_pct:>7.3f}{atr_mult:>11.1f}{sl_pct:>8.3f}{ml:>8}{liq_at_max:>8.1f}%"
          f"{safe_lev:>9}x{margin_10x:>11.1f}${100/10:>8.1f}%")

print("=" * 108)

print("\n" + "=" * 100)
print("BERAPA POSISI MUAT? (equity $%.2f, margin cap 60%% = $%.2f)" % (EQUITY, EQUITY * 0.6))
print("=" * 100)
print(f"{'LEV':<6}{'avg margin/pos':>16}{'max posisi':>12}{'liq dist':>11}{'SL max':>9}{'AMAN?':>8}")
print("-" * 100)

for lev in [3, 5, 10, 15, 20, 25]:
    avg_m = sum(r["margin10"] * 10 / lev for r in rows) / len(rows)
    maxpos = int((EQUITY * 0.6) / avg_m)
    liq = 100 / lev
    slmax = max(r["sl_pct"] for r in rows)
    ok = "YES" if liq > slmax * 2 else ("TIGHT" if liq > slmax else "NO")
    print(f"{lev:<6}x{avg_m:>14.1f}${maxpos:>12}{liq:>10.1f}%{slmax:>8.2f}%{ok:>8}")

print("-" * 100)
print("avg margin/pos = rata-rata margin per posisi di leverage tersebut")
print("liq dist       = jarak likuidasi (isolated margin, tanpa maintenance)")
print("SL max         = SL terlebar dari 9 coin (ATR-based)")
print("AMAN           = liq dist > 2x SL max")

print("\n" + "=" * 100)
print("SIMULASI: 6 POSISI BERSAMAAN DI BERBAGAI LEVERAGE")
print("=" * 100)
print(f"{'LEV':<6}{'total margin':>14}{'% equity':>11}{'total risk':>12}{'liq buffer':>12}{'STATUS':>10}")
print("-" * 100)

# ambil 6 coin dengan SL terlebar (worst case margin)
worst6 = sorted(rows, key=lambda r: -r["sl_pct"])[:6]
tot_risk = sum(r["risk_usd"] for r in worst6)

for lev in [3, 5, 10, 15]:
    tot_m = sum(r["notional"] / lev for r in worst6)
    pct = tot_m / EQUITY * 100
    liq = 100 / lev
    status = "OK" if pct <= 60 and liq > max(r["sl_pct"] for r in worst6) * 2 else \
             ("MARGIN?" if pct > 60 else "LIQ RISK")
    print(f"{lev:<6}x{tot_m:>12.0f}${pct:>10.1f}%{tot_risk:>11.2f}${liq:>10.1f}%{status:>10}")

print("-" * 100)
print(f"total risk 6 posisi (worst case): ${tot_risk:.2f} = {tot_risk/EQUITY*100:.2f}% equity")
print(f"cap risk saat ini: 2.25% = ${EQUITY*0.0225:.2f}")
