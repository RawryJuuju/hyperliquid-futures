#!/usr/bin/env python3
"""
PnL Calendar generator — baca fut_trades.jsonl, agregasi per hari WIB,
render HTML kalender bulanan dengan detail per tanggal.
"""
import json, os, calendar
from datetime import datetime, timezone, timedelta
from collections import defaultdict

WIB = timezone(timedelta(hours=7))
BASE = "/home/ubuntu/papertrade_backtest"
TRADE_LOG = os.path.join(BASE, "fut_trades.jsonl")
EQUITY_LOG = os.path.join(BASE, "equity_curve.jsonl")


def load_trades():
    if not os.path.exists(TRADE_LOG):
        return []
    out = []
    for line in open(TRADE_LOG):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            t = datetime.fromisoformat(r["t"]).astimezone(WIB)
            r["_dt"] = t
            r["_day"] = t.strftime("%Y-%m-%d")
            out.append(r)
        except Exception:
            pass
    return out


def aggregate(trades):
    daily = defaultdict(lambda: {"n": 0, "w": 0, "l": 0, "R": 0.0, "usd": 0.0,
                                 "coins": defaultdict(float), "trades": []})
    for t in trades:
        d = daily[t["_day"]]
        d["n"] += 1
        R = t.get("R", 0) or 0
        usd = t.get("usd", 0) or 0
        d["R"] += R
        d["usd"] += usd
        if usd > 0:
            d["w"] += 1
        else:
            d["l"] += 1
        d["coins"][t.get("coin", "?")] += usd
        d["trades"].append({
            "time": t["_dt"].strftime("%H:%M"),
            "coin": t.get("coin", "?"),
            "dir": t.get("dir", ""),
            "strat": t.get("strategy", ""),
            "kind": t.get("kind", ""),
            "R": round(R, 2),
            "usd": round(usd, 2),
            "equity": round(t.get("equity", 0) or 0, 2),
        })
    return daily


def build_calendar_html(daily):
    trades = load_trades()
    if trades:
        months = sorted({t["_day"][:7] for t in trades})
    else:
        months = [datetime.now(WIB).strftime("%Y-%m")]

    # default bulan terbaru
    cur_month = months[-1]
    y, m = int(cur_month[:4]), int(cur_month[5:7])

    first_weekday, days_in_month = calendar.monthrange(y, m)
    month_label = datetime(y, m, 1).strftime("%B %Y")

    # total bulan ini
    m_n = sum(daily[d]["n"] for d in daily if d.startswith(cur_month))
    m_usd = sum(daily[d]["usd"] for d in daily if d.startswith(cur_month))
    m_R = sum(daily[d]["R"] for d in daily if d.startswith(cur_month))
    m_w = sum(daily[d]["w"] for d in daily if d.startswith(cur_month))
    m_l = sum(daily[d]["l"] for d in daily if d.startswith(cur_month))

    cells = []
    # padding awal (Senin = 0)
    for _ in range(first_weekday):
        cells.append('<div class="cal-cell empty"></div>')

    for day in range(1, days_in_month + 1):
        key = f"{y:04d}-{m:02d}-{day:02d}"
        d = daily.get(key)
        if not d:
            cells.append(f'<div class="cal-cell"><div class="cd-num">{day}</div></div>')
            continue
        usd = d["usd"]
        cls = "pos" if usd > 0 else ("neg" if usd < 0 else "flat")
        sign = "+" if usd > 0 else ""
        cells.append(
            f'<div class="cal-cell {cls}" onclick="showDay(\'{key}\')">'
            f'<div class="cd-num">{day}</div>'
            f'<div class="cd-pnl">{sign}{usd:.2f}</div>'
            f'<div class="cd-meta">{d["n"]}t · {d["R"]:+.1f}R</div>'
            f'</div>'
        )

    # detail data untuk JS
    detail = {}
    for key, d in daily.items():
        detail[key] = {
            "n": d["n"], "w": d["w"], "l": d["l"],
            "R": round(d["R"], 2), "usd": round(d["usd"], 2),
            "coins": {k: round(v, 2) for k, v in d["coins"].items()},
            "trades": d["trades"],
        }

    month_opts = "".join(
        f'<option value="{mm}"{" selected" if mm == cur_month else ""}>'
        f'{datetime(int(mm[:4]), int(mm[5:7]), 1).strftime("%B %Y")}</option>'
        for mm in reversed(months)
    )

    total_usd = sum(d["usd"] for d in daily.values())
    total_n = sum(d["n"] for d in daily.values())
    green_days = sum(1 for d in daily.values() if d["usd"] > 0)
    red_days = sum(1 for d in daily.values() if d["usd"] < 0)

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PnL Calendar — Hyperliquid Futures</title>
<link rel="icon" type="image/png" sizes="32x32" href="/static/hl-favicon-32x32.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{{
 --bg:#0b0e11;--bg2:#12161c;--panel:#161b22;--line:#252d38;
 --txt:#eaecef;--txt2:#8b95a5;--txt3:#5e6776;
 --green:#0ecb81;--red:#f6465d;--cyan:#22d3ee;
 --mono:'JetBrains Mono',monospace;--ui:'Inter',sans-serif;--head:'Sora',sans-serif;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--txt);font-family:var(--ui);min-height:100vh;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1080px;margin:0 auto;padding:32px 24px 64px}}
header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px;gap:16px;flex-wrap:wrap}}
.brand{{display:flex;align-items:center;gap:11px}}
.logo{{width:26px;height:26px}}
h1{{font-family:var(--head);font-size:20px;font-weight:600;letter-spacing:-.02em}}
.sub{{font-size:11px;color:var(--txt3);margin-top:2px;font-family:var(--mono)}}
.nav{{display:flex;gap:8px}}
.nav a{{font-family:var(--head);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;
 padding:7px 14px;border-radius:7px;border:1px solid var(--line);color:var(--txt2);text-decoration:none;transition:.18s}}
.nav a:hover{{color:var(--cyan);border-color:rgba(34,211,238,.4);background:rgba(34,211,238,.06)}}

.summary{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:24px}}
.sc{{background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:14px 16px}}
.sc .l{{font-size:9px;color:var(--txt3);text-transform:uppercase;letter-spacing:.08em;margin-bottom:5px;font-weight:600}}
.sc .v{{font-family:var(--mono);font-size:17px;font-weight:600}}

.calhead{{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}}
.month{{font-family:var(--head);font-size:17px;font-weight:600}}
select{{background:var(--bg2);border:1px solid var(--line);color:var(--txt);padding:7px 11px;border-radius:7px;
 font-family:var(--mono);font-size:11px;cursor:pointer}}
select:hover{{border-color:var(--txt3)}}

.weekdays{{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin-bottom:6px}}
.wd{{font-size:9px;color:var(--txt3);text-align:center;text-transform:uppercase;letter-spacing:.08em;
 padding:6px 0;font-weight:600}}
.cal{{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}}
.cal-cell{{background:var(--bg2);border:1px solid var(--line);border-radius:8px;min-height:76px;padding:8px;
 transition:.15s;position:relative}}
.cal-cell.empty{{background:transparent;border-color:transparent}}
.cal-cell.pos{{border-color:rgba(14,203,129,.3);background:rgba(14,203,129,.06);cursor:pointer}}
.cal-cell.neg{{border-color:rgba(246,70,93,.3);background:rgba(246,70,93,.06);cursor:pointer}}
.cal-cell.pos:hover{{border-color:var(--green);transform:translateY(-1px)}}
.cal-cell.neg:hover{{border-color:var(--red);transform:translateY(-1px)}}
.cd-num{{font-family:var(--mono);font-size:11px;color:var(--txt2);margin-bottom:4px}}
.cd-pnl{{font-family:var(--mono);font-size:13px;font-weight:600}}
.cal-cell.pos .cd-pnl{{color:var(--green)}}
.cal-cell.neg .cd-pnl{{color:var(--red)}}
.cd-meta{{font-family:var(--mono);font-size:9px;color:var(--txt3);margin-top:2px}}

/* modal */
.ov{{position:fixed;inset:0;background:rgba(0,0,0,.72);backdrop-filter:blur(6px);display:none;
 align-items:center;justify-content:center;z-index:100;padding:20px}}
.ov.on{{display:flex}}
.modal{{background:var(--panel);border:1px solid var(--line);border-radius:14px;max-width:720px;width:100%;
 max-height:82vh;overflow-y:auto;padding:24px}}
.mh{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid var(--line)}}
.mt{{font-family:var(--head);font-size:17px;font-weight:600}}
.ms{{font-family:var(--mono);font-size:11px;color:var(--txt3);margin-top:3px}}
.close{{background:none;border:none;color:var(--txt3);font-size:22px;cursor:pointer;line-height:1;padding:0 4px}}
.close:hover{{color:var(--txt)}}
.mgrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin-bottom:18px}}
.mc{{background:var(--bg2);border:1px solid var(--line);border-radius:8px;padding:11px 13px}}
.mc .l{{font-size:9px;color:var(--txt3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px}}
.mc .v{{font-family:var(--mono);font-size:14px;font-weight:600}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{text-align:left;padding:8px 10px;font-size:9px;text-transform:uppercase;letter-spacing:.06em;
 color:var(--txt3);border-bottom:1px solid var(--line);font-weight:600}}
td{{padding:8px 10px;border-bottom:1px solid rgba(37,45,56,.5);font-family:var(--mono)}}
tr:last-child td{{border-bottom:none}}
tbody tr:hover{{background:rgba(255,255,255,.02)}}
.tag{{font-family:var(--ui);font-size:9px;font-weight:600;padding:2px 6px;border-radius:3px}}
.t-long{{background:rgba(14,203,129,.12);color:var(--green)}}
.t-short{{background:rgba(246,70,93,.12);color:var(--red)}}
.empty-state{{text-align:center;padding:60px 20px;color:var(--txt3);font-size:13px}}
@media(max-width:820px){{
 .summary{{grid-template-columns:repeat(2,1fr)}}
 .mgrid{{grid-template-columns:repeat(2,1fr)}}
 .cal-cell{{min-height:64px;padding:6px}}
 .cd-pnl{{font-size:11px}}
}}
</style></head><body>
<div class="wrap">
  <header>
    <div class="brand">
      <img class="logo" src="/static/hl-favicon-32x32.png" alt="">
      <div>
        <h1>PnL Calendar</h1>
        <div class="sub">HYPERLIQUID FUTURES · WIB (UTC+7)</div>
      </div>
    </div>
    <nav class="nav">
      <a href="/terminal">Terminal</a>
      <a href="/versions">Versions</a>
      <a href="/">About</a>
    </nav>
  </header>

  <div class="summary">
    <div class="sc"><div class="l">Total PnL</div>
      <div class="v" style="color:{'var(--green)' if total_usd>=0 else 'var(--red)'}">
      {'+' if total_usd>=0 else ''}{total_usd:.2f}</div></div>
    <div class="sc"><div class="l">Total Trades</div><div class="v">{total_n}</div></div>
    <div class="sc"><div class="l">Green Days</div><div class="v" style="color:var(--green)">{green_days}</div></div>
    <div class="sc"><div class="l">Red Days</div><div class="v" style="color:var(--red)">{red_days}</div></div>
    <div class="sc"><div class="l">This Month</div>
      <div class="v" style="color:{'var(--green)' if m_usd>=0 else 'var(--red)'}">
      {'+' if m_usd>=0 else ''}{m_usd:.2f}</div></div>
  </div>

  <div class="calhead">
    <div class="month">{month_label} — {m_n} trades · {m_w}W/{m_l}L · {m_R:+.1f}R</div>
    <select onchange="location.href='/calendar?m='+this.value">{month_opts}</select>
  </div>

  <div class="weekdays">
    <div class="wd">Mon</div><div class="wd">Tue</div><div class="wd">Wed</div>
    <div class="wd">Thu</div><div class="wd">Fri</div><div class="wd">Sat</div><div class="wd">Sun</div>
  </div>

  <div class="cal">{''.join(cells)}</div>
</div>

<div class="ov" id="ov" onclick="if(event.target===this)hideDay()">
  <div class="modal">
    <div class="mh">
      <div><div class="mt" id="mtitle">—</div><div class="ms" id="msub"></div></div>
      <button class="close" onclick="hideDay()">×</button>
    </div>
    <div class="mgrid" id="mgrid"></div>
    <table><thead><tr>
      <th>Time</th><th>Coin</th><th>Side</th><th>Strategy</th><th>Exit</th><th>R</th><th>PnL</th>
    </tr></thead><tbody id="mbody"></tbody></table>
  </div>
</div>

<script>
const DATA = {json.dumps(detail)};
function showDay(k){{
  const d = DATA[k]; if(!d) return;
  document.getElementById('mtitle').textContent = k;
  document.getElementById('msub').textContent =
    d.n + ' trades · ' + d.w + 'W / ' + d.l + 'L · ' + (d.R>=0?'+':'') + d.R + 'R';
  const color = d.usd>=0 ? 'var(--green)' : 'var(--red)';
  document.getElementById('mgrid').innerHTML = `
    <div class="mc"><div class="l">Net PnL</div><div class="v" style="color:${{color}}">${{d.usd>=0?'+':''}}${{d.usd.toFixed(2)}}</div></div>
    <div class="mc"><div class="l">Trades</div><div class="v">${{d.n}}</div></div>
    <div class="mc"><div class="l">Win Rate</div><div class="v">${{d.n?((d.w/d.n*100).toFixed(0)):0}}%</div></div>
    <div class="mc"><div class="l">Total R</div><div class="v" style="color:${{color}}">${{d.R>=0?'+':''}}${{d.R}}</div></div>`;
  document.getElementById('mbody').innerHTML = d.trades.map(t => `
    <tr>
      <td style="color:var(--txt3)">${{t.time}}</td>
      <td style="font-weight:600">${{t.coin}}</td>
      <td><span class="tag ${{t.dir==='LONG'?'t-long':'t-short'}}">${{t.dir}}</span></td>
      <td style="color:var(--txt2)">${{t.strat}}</td>
      <td style="color:var(--txt3)">${{t.kind}}</td>
      <td style="color:${{t.R>=0?'var(--green)':'var(--red)'}}">${{t.R>=0?'+':''}}${{t.R}}</td>
      <td style="color:${{t.usd>=0?'var(--green)':'var(--red)'}}">${{t.usd>=0?'+':''}}${{t.usd.toFixed(2)}}</td>
    </tr>`).join('');
  document.getElementById('ov').classList.add('on');
}}
function hideDay(){{ document.getElementById('ov').classList.remove('on'); }}
document.addEventListener('keydown', e => {{ if(e.key==='Escape') hideDay(); }});
</script>
</body></html>"""


def render(month=None):
    trades = load_trades()
    daily = aggregate(trades)
    return build_calendar_html(daily)


if __name__ == "__main__":
    html = render()
    out = os.path.join(BASE, "static", "calendar.html")
    open(out, "w").write(html)
    print(f"written {out} ({len(html)} bytes)")
