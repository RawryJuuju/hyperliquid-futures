import json, urllib.request

def post(base, payload):
    r = urllib.request.Request(f"{base}/info", data=json.dumps(payload).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.loads(resp.read().decode())

BASE = "https://api.hyperliquid.xyz"
meta, ctxs = post(BASE, {"type": "metaAndAssetCtxs"})
universe = meta["universe"]

rows = []
for a, c in zip(universe, ctxs):
    try:
        vol = float(c.get("dayNtlVlm", 0) or 0)
        oi = float(c.get("openInterest", 0) or 0)
        mark = float(c.get("markPx", 0) or 0)
        funding = float(c.get("funding", 0) or 0)
    except Exception:
        continue
    if a.get("isDelisted"): continue
    rows.append({
        "coin": a["name"],
        "vol24h": vol,
        "oi": oi,
        "mark": mark,
        "funding": funding,
        "maxLev": a.get("maxLeverage"),
        "szDec": a["szDecimals"],
    })

rows.sort(key=lambda x: -x["vol24h"])
print(f"{'#':<3}{'COIN':<10}{'VOL 24H ($)':>18}{'OPEN INT ($)':>16}{'MARK':>12}{'FUND%':>9}{'MAXLEV':>8}")
print("-" * 80)
for i, r in enumerate(rows[:25], 1):
    print(f"{i:<3}{r['coin']:<10}{r['vol24h']:>18,.0f}{r['oi']:>16,.0f}{r['mark']:>12,.4f}{r['funding']*100:>9.4f}{r['maxLev']:>8}")

print("\n=== TOP 5 BY 24H VOLUME ===")
for r in rows[:5]:
    print(f"  {r['coin']:<6} vol=${r['vol24h']:,.0f}  OI=${r['oi']:,.0f}  mark={r['mark']}")
