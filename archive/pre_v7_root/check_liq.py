import json, urllib.request

def post(p):
    r = urllib.request.Request("https://api.hyperliquid.xyz/info",
                               data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.loads(resp.read().decode())

meta, ctxs = post({"type": "metaAndAssetCtxs"})
target = ["INJ", "kPEPE", "ARB"]
print(f"{'COIN':<8}{'VOL 24H':>16}{'OI':>16}{'MAXLEV':>8}{'szDec':>7}{'MARK':>14}")
print("-" * 72)
for a, c in zip(meta["universe"], ctxs):
    if a["name"] in target:
        print(f"{a['name']:<8}{float(c.get('dayNtlVlm',0)):>16,.0f}"
              f"{float(c.get('openInterest',0)):>16,.0f}{a.get('maxLeverage'):>8}"
              f"{a['szDecimals']:>7}{float(c.get('markPx',0)):>14.6g}")
