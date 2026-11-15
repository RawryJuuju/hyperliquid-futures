import json, urllib.request

def post(payload):
    r = urllib.request.Request("https://api.hyperliquid.xyz/info",
                               data=json.dumps(payload).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=25) as resp:
        return json.loads(resp.read().decode())

meta, ctxs = post({"type": "metaAndAssetCtxs"})
rows = []
for a, c in zip(meta["universe"], ctxs):
    if a.get("isDelisted"): continue
    try:
        vol = float(c.get("dayNtlVlm", 0) or 0)
        oi = float(c.get("openInterest", 0) or 0)
    except Exception:
        continue
    rows.append({"coin": a["name"], "vol": vol, "oi": oi,
                 "maxLev": a.get("maxLeverage"), "szDec": a["szDecimals"]})
rows.sort(key=lambda x: -x["vol"])

print(f"{'#':<3}{'COIN':<10}{'VOL 24H ($)':>16}{'OI ($)':>15}{'LEV':>5}")
print("-"*52)
for i, r in enumerate(rows[:30], 1):
    print(f"{i:<3}{r['coin']:<10}{r['vol']:>16,.0f}{r['oi']:>15,.0f}{r['maxLev']:>5}")

# Filter: cukup likuid untuk trading retail
liquid = [r["coin"] for r in rows if r["vol"] >= 20_000_000]
print(f"\nLikuid (vol >= $20M/24h): {len(liquid)}")
print(", ".join(liquid))
