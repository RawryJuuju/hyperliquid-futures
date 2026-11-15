import json, subprocess

s = json.load(open("/home/ubuntu/papertrade_backtest/fut_state.json"))
print(f"equity: {s['equity']:.2f} | open: {len(s['open'])}")
for k, p in s["open"].items():
    print(f"  {k:<26} {p['dir']:<6} risk={p['risk_pct_equity']:.3f}%")
if s["open"]:
    print(f"  total risk {sum(p['risk_pct_equity'] for p in s['open'].values()):.2f}%")

out = subprocess.run(["grep", "-ciE", "error|traceback",
                      "/home/ubuntu/papertrade_backtest/futures_bot.log"],
                     capture_output=True, text=True).stdout.strip()
print(f"errors in log: {out}")
