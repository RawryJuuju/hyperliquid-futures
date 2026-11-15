#!/usr/bin/env python3
"""
Versions page generator — editorial style matching /about.
Reads versions.json + fut_trades.jsonl, computes per-version stats.
"""
import json, os
from datetime import datetime, timezone, timedelta
from collections import defaultdict

WIB = timezone(timedelta(hours=7))
BASE = "/home/ubuntu/papertrade_backtest"
VERSIONS = os.path.join(BASE, "versions.json")
TRADES = os.path.join(BASE, "fut_trades.jsonl")
OUT = os.path.join(BASE, "static", "versions.html")

from versions_style import PAGE


def load_versions():
    return json.load(open(VERSIONS))


def load_trades():
    out = []
    if not os.path.exists(TRADES):
        return out
    for line in open(TRADES):
        line = line.strip()
        if not line:
            continue
        try:
            t = json.loads(line)
            t["_dt"] = datetime.fromisoformat(t["t"]).astimezone(WIB)
            out.append(t)
        except Exception:
            pass
    out.sort(key=lambda x: x["_dt"])
    return out


def slice_trades(trades, start, end):
    s = datetime.fromisoformat(start).astimezone(WIB) if start else None
    e = datetime.fromisoformat(end).astimezone(WIB) if end else None
    out = []
    for t in trades:
        if s and t["_dt"] < s:
            continue
        if e and t["_dt"] > e:
            continue
        out.append(t)
    return out


def compute(trades, initial):
    if not trades:
        return None
    n = len(trades)
    wins = [t for t in trades if t["usd"] > 0]
    losses = [t for t in trades if t["usd"] <= 0]
    w = len(wins)
    gw = sum(t["usd"] for t in wins)
    gl = sum(t["usd"] for t in losses)
    usd = gw + gl
    R = sum(t["R"] for t in trades)
    pf = abs(gw / gl) if gl else 0.0

    eq = initial
    peak = initial
    mdd = 0.0
    curve = [(trades[0]["_dt"], initial)]
    for t in trades:
        eq += t["usd"]
        peak = max(peak, eq)
        if peak > 0:
            mdd = min(mdd, (eq - peak) / peak)
        curve.append((t["_dt"], eq))

    by_strat = defaultdict(lambda: {"n": 0, "w": 0, "R": 0.0, "usd": 0.0})
    by_coin = defaultdict(lambda: {"n": 0, "w": 0, "R": 0.0, "usd": 0.0})
    by_kind = defaultdict(int)
    for t in trades:
        for bucket, key in ((by_strat, t["strategy"]), (by_coin, t["coin"])):
            b = bucket[key]
            b["n"] += 1
            if t["usd"] > 0:
                b["w"] += 1
            b["R"] += t["R"]
            b["usd"] += t["usd"]
        by_kind[t["kind"]] += 1

    span = (trades[-1]["_dt"] - trades[0]["_dt"]).total_seconds() / 86400

    return {
        "n": n, "w": w, "l": len(losses), "wr": w / n * 100,
        "gw": gw, "gl": gl, "usd": usd, "R": R, "pf": pf,
        "mdd": mdd * 100, "final_eq": eq, "ret": (eq / initial - 1) * 100,
        "span_days": span,
        "avg_win": gw / w if w else 0,
        "avg_loss": gl / len(losses) if losses else 0,
        "best": max(trades, key=lambda x: x["usd"]),
        "worst": min(trades, key=lambda x: x["usd"]),
        "by_strat": dict(by_strat), "by_coin": dict(by_coin), "by_kind": dict(by_kind),
        "curve": curve, "trades": trades,
        "start_dt": trades[0]["_dt"], "end_dt": trades[-1]["_dt"],
    }


def fmt_money(v, sign=True):
    return f"${v:+,.2f}" if sign else f"${v:,.2f}"


def cls(v):
    return "pos" if v > 0 else ("neg" if v < 0 else "mut")


def sparkline(curve, w=900, h=120):
    if len(curve) < 2:
        return ""
    vals = [c[1] for c in curve]
    lo, hi = min(vals), max(vals)
    rng = hi - lo if hi > lo else 1
    pts = []
    for i, v in enumerate(vals):
        x = i / (len(vals) - 1) * w
        y = h - ((v - lo) / rng * (h - 12)) - 6
        pts.append(f"{x:.1f},{y:.1f}")
    up = vals[-1] >= vals[0]
    color = "#5eead4" if up else "#f2707f"
    area = f"0,{h} " + " ".join(pts) + f" {w},{h}"
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
        f'<polygon points="{area}" fill="{color}" opacity="0.07"/>'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="1.5" '
        f'stroke-linejoin="round" stroke-linecap="round"/></svg>'
    )


def hero_stats(versions, all_trades):
    live = [v for v in versions if v.get("status") == "live"]
    total = len(versions)
    n_trades = len(all_trades)
    net = sum(t["usd"] for t in all_trades)
    cells = [
        (str(total), "Releases"),
        (str(len(live)), "Live Now"),
        (f"{n_trades}", "Trades Logged"),
        (fmt_money(net), "Net PnL"),
    ]
    out = []
    for val, lab in cells:
        neg = " neg" if val.startswith("$-") else ""
        out.append(f'<div class="stat"><div class="sv{neg}">{val}</div><div class="sl">{lab}</div></div>')
    return "\n    ".join(out)


def render():
    vers = load_versions()["versions"]
    all_trades = load_trades()

    blocks = []
    for v in sorted(vers, key=lambda x: x["id"], reverse=True):
        tr = slice_trades(all_trades, v.get("start"), v.get("end"))
        st = compute(tr, v.get("initial_equity", 1000.0))
        blocks.append(build_version_block(v, st))

    html = PAGE.replace("{{VERSIONS}}", "\n".join(blocks))
    html = html.replace("{{HERO_STATS}}", hero_stats(vers, all_trades))
    with open(OUT, "w") as f:
        f.write(html)
    return OUT, len(vers)


def build_version_block(v, st):
    badge = {"live": "b1", "testing": "b2", "archived": "b3"}.get(v.get("status"), "b3")
    status_txt = v.get("status", "unknown").upper()
    num = v["id"].replace(".", "-")

    if not st:
        body = '<p class="empty">No trades recorded for this release yet.</p>'
        return f"""
<section id="v{num}">
  <div class="sh"><span class="sn">{v['id']}</span><h2>{v['name']}</h2></div>
  <div class="vmeta-row">
    <span class="badge {badge}">{status_txt}</span>
    <span class="vdate">Released {v.get('released','—')}</span>
  </div>
  <div class="prose"><p>{v['summary']}</p></div>
  {body}
</section>"""

    # ---- metric grid ----
    metrics = f"""
  <div class="metrics">
    <div class="m"><div class="ml">Total Return</div><div class="mv {cls(st['ret'])}">{st['ret']:+.2f}%</div></div>
    <div class="m"><div class="ml">Net PnL</div><div class="mv {cls(st['usd'])}">{fmt_money(st['usd'])}</div></div>
    <div class="m"><div class="ml">Win Rate</div><div class="mv">{st['wr']:.1f}%</div></div>
    <div class="m"><div class="ml">Profit Factor</div><div class="mv {'pos' if st['pf'] >= 1 else 'neg'}">{st['pf']:.2f}</div></div>
    <div class="m"><div class="ml">Total R</div><div class="mv {cls(st['R'])}">{st['R']:+.2f}R</div></div>
    <div class="m"><div class="ml">Max Drawdown</div><div class="mv neg">{st['mdd']:.2f}%</div></div>
    <div class="m"><div class="ml">Closed Trades</div><div class="mv">{st['n']}</div></div>
    <div class="m"><div class="ml">Ending Equity</div><div class="mv">{fmt_money(st['final_eq'], False)}</div></div>
  </div>"""

    # ---- breakdown tables ----
    def rows(d, label):
        return "".join(
            f'<tr><td class="n">{k}</td><td class="mut">{b["n"]}</td>'
            f'<td class="mut">{b["w"]/b["n"]*100:.1f}%</td>'
            f'<td class="{cls(b["R"])}">{b["R"]:+.2f}</td>'
            f'<td class="{cls(b["usd"])}">{fmt_money(b["usd"])}</td></tr>'
            for k, b in sorted(d.items(), key=lambda x: -x[1]["usd"])
        )

    breakdown = f"""
  <div class="grid2">
    <div class="card">
      <div class="ct">By Strategy</div>
      <table class="tbl">
        <thead><tr><th>Strategy</th><th>Trades</th><th>Win Rate</th><th>R</th><th>PnL</th></tr></thead>
        <tbody>{rows(st['by_strat'], 'strategy')}</tbody>
      </table>
    </div>
    <div class="card">
      <div class="ct">By Instrument</div>
      <table class="tbl">
        <thead><tr><th>Coin</th><th>Trades</th><th>Win Rate</th><th>R</th><th>PnL</th></tr></thead>
        <tbody>{rows(st['by_coin'], 'coin')}</tbody>
      </table>
    </div>
  </div>"""

    facts = f"""
  <div class="factrow">
    <span>Avg win <b class="pos">{fmt_money(st['avg_win'])}</b></span>
    <span>Avg loss <b class="neg">{fmt_money(st['avg_loss'])}</b></span>
    <span>Best <b class="pos">{st['best']['coin']} {fmt_money(st['best']['usd'])}</b></span>
    <span>Worst <b class="neg">{st['worst']['coin']} {fmt_money(st['worst']['usd'])}</b></span>
    <span>Exits <b>SL {st['by_kind'].get('SL',0)} · TP {st['by_kind'].get('TP',0)} · TIME {st['by_kind'].get('TIME',0)}</b></span>
    <span>Span <b>{st['span_days']*24:.1f}h</b></span>
  </div>"""

    cfg = v.get("config_snapshot", {})
    cfgblock = f"""
  <div class="cfgsnap">
    <div class="ct">Configuration</div>
    <div class="cfgrow">
      <span>Coins <b>{', '.join(cfg.get('coins', []))}</b></span>
      <span>Timeframes <b>{', '.join(cfg.get('timeframes', []))}</b></span>
      <span>Strategies <b>{', '.join(cfg.get('strategies', []))}</b></span>
      <span>Risk / trade <b>{cfg.get('base_risk_pct')}%</b></span>
      <span>Max open risk <b>{cfg.get('max_open_risk_pct')}%</b></span>
      <span>Leverage <b>{cfg.get('leverage')}x</b></span>
      <span>Slots <b>{cfg.get('total_slots')}</b></span>
      <span>Stop model <b>{cfg.get('sl_model')}</b></span>
    </div>
  </div>"""

    changes = "".join(f"<li>{c}</li>" for c in v.get("changes", []))
    changelog = f"""  <div class="changelog">
    <div class="ct">Changes in this release</div>
    <ul>{changes}</ul>
  </div>"""

    vd = v.get("verdict")
    verdict = f'<div class="quote">{vd}<span>Post-mortem</span></div>' if vd else ""

    trows = "".join(
        f'<tr><td class="mut">{t["_dt"]:%d %b %H:%M}</td>'
        f'<td class="n">{t["coin"]}</td>'
        f'<td class="{"pos" if t["dir"]=="LONG" else "neg"}">{t["dir"]}</td>'
        f'<td class="mut">{t["strategy"]}</td>'
        f'<td class="mut">{t["kind"]}</td>'
        f'<td>{t["entry"]:.6g}</td><td>{t["exit"]:.6g}</td>'
        f'<td class="{cls(t["R"])}">{t["R"]:+.2f}</td>'
        f'<td class="{cls(t["usd"])}">{fmt_money(t["usd"])}</td>'
        f'<td class="mut">{fmt_money(t["equity"], False)}</td></tr>'
        for t in reversed(st["trades"])
    )

    tradelog = f"""
  <details class="tradelog">
    <summary>Full trade ledger — {st['n']} closed positions</summary>
    <div class="scroll">
      <table class="tbl">
        <thead><tr><th>Time (WIB)</th><th>Coin</th><th>Side</th><th>Strategy</th><th>Exit</th>
        <th>Entry</th><th>Exit</th><th>R</th><th>PnL</th><th>Equity</th></tr></thead>
        <tbody>{trows}</tbody>
      </table>
    </div>
  </details>"""

    return f"""
<section id="v{num}">
  <div class="sh"><span class="sn">{v['id']}</span><h2>{v['name']}</h2></div>
  <div class="vmeta-row">
    <span class="badge {badge}">{status_txt}</span>
    <span class="vdate">Released {v.get('released','—')} · {st['start_dt']:%d %b %H:%M} → {st['end_dt']:%d %b %H:%M} WIB</span>
  </div>
  <div class="prose"><p>{v['summary']}</p></div>

  {verdict}
  {metrics}
  <div class="curvebox">
    <div class="curvehead">Equity curve · {st['n']} closed trades</div>
    {sparkline(st['curve'])}
  </div>

  {breakdown}
  {facts}
  {cfgblock}
  {changelog}
  {tradelog}
</section>"""


if __name__ == "__main__":
    path, n = render()
    print(f"written {path} ({os.path.getsize(path)} bytes), {n} versions")
