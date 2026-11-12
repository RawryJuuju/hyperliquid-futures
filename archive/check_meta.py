import json, urllib.request

def post(url, payload):
    r = urllib.request.Request(url, data=json.dumps(payload).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=15) as resp:
        return json.loads(resp.read().decode())

for net, base in [("TESTNET", "https://api.hyperliquid-testnet.xyz"),
                  ("MAINNET", "https://api.hyperliquid.xyz")]:
    meta = post(f"{base}/info", {"type": "meta"})
    print(f"=== {net} ===")
    for a in meta["universe"]:
        if a["name"] in ("ETH", "BTC"):
            print(f"  {a['name']}: szDecimals={a['szDecimals']} maxLeverage={a.get('maxLeverage')}")
    print(f"  total pairs: {len(meta['universe'])}")
