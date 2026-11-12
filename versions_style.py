PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Versions — Systematic Futures Trader</title>
<link rel="icon" type="image/png" sizes="32x32" href="/static/hl-favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/static/hl-favicon-16x16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/static/hl-apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
 --bg:#08090b; --bg2:#0d0f12; --panel:#111418; --line:#1d2228;
 --txt:#f2f4f7; --txt2:#8b939f; --txt3:#5a626d;
 --acc:#5eead4; --acc2:#38bdf8; --gold:#e8b923;
 --mono:'JetBrains Mono',monospace; --ui:'Inter',sans-serif; --serif:'Instrument Serif',serif;
}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--txt);font-family:var(--ui);overflow-x:hidden;-webkit-font-smoothing:antialiased}

.glow{position:fixed;border-radius:50%;filter:blur(120px);pointer-events:none;z-index:0}
.g1{width:520px;height:520px;background:rgba(94,234,212,.09);top:-180px;left:-120px}
.g2{width:460px;height:460px;background:rgba(56,189,248,.07);bottom:-200px;right:-140px}

.wrap{position:relative;z-index:1;max-width:1080px;margin:0 auto;padding:0 28px}

nav{position:fixed;top:0;left:0;right:0;z-index:50;backdrop-filter:blur(20px);
 background:rgba(8,9,11,.72);border-bottom:1px solid var(--line)}
.nav-in{max-width:1080px;margin:0 auto;padding:16px 28px;display:flex;
 align-items:center;justify-content:space-between}
.logo{display:flex;align-items:center;gap:10px;font-family:var(--mono);
 font-size:13px;font-weight:600;letter-spacing:-.2px}
.pulse{width:7px;height:7px;border-radius:50%;background:var(--acc);
 box-shadow:0 0 10px var(--acc);animation:p 2s infinite}
@keyframes p{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.85)}}
.navlinks{display:flex;gap:26px;font-size:12.5px;color:var(--txt2);align-items:center}
.navlinks a{color:inherit;text-decoration:none;transition:.2s}
.navlinks a:hover{color:var(--acc)}
.navlinks a.on{color:var(--acc)}
.nav-cta{border:1px solid rgba(94,234,212,.35);border-radius:6px;padding:6px 13px;
 color:var(--acc) !important;font-family:var(--mono);font-size:11px;font-weight:600;
 letter-spacing:.02em;transition:.18s}
.nav-cta:hover{background:rgba(94,234,212,.1);border-color:var(--acc);transform:translateY(-1px)}

.hero{padding:170px 0 80px;position:relative}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.18em;
 text-transform:uppercase;color:var(--acc);margin-bottom:26px;
 display:flex;align-items:center;gap:10px}
.eyebrow::before{content:'';width:28px;height:1px;background:var(--acc)}
h1{font-family:var(--serif);font-size:clamp(46px,7vw,82px);line-height:1.02;
 font-weight:400;letter-spacing:-.025em;margin-bottom:28px}
h1 em{font-style:italic;color:var(--acc)}
.lede{font-size:17px;line-height:1.78;color:var(--txt2);max-width:640px;font-weight:300}
.lede strong{color:var(--txt);font-weight:500}

.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;
 background:var(--line);border:1px solid var(--line);border-radius:14px;
 overflow:hidden;margin-top:56px}
.stat{background:var(--bg2);padding:26px 22px;transition:.25s}
.stat:hover{background:var(--panel)}
.sv{font-family:var(--mono);font-size:26px;font-weight:600;letter-spacing:-.03em;color:var(--acc)}
.sv.neg{color:#f2707f}
.sl{font-size:10.5px;color:var(--txt3);text-transform:uppercase;letter-spacing:.1em;margin-top:7px}

section{padding:78px 0;border-top:1px solid var(--line)}
.sh{display:flex;align-items:baseline;gap:16px;margin-bottom:38px;flex-wrap:wrap}
.sn{font-family:var(--mono);font-size:11px;color:var(--txt3)}
h2{font-family:var(--serif);font-size:clamp(30px,4vw,44px);font-weight:400;letter-spacing:-.02em}
h2 em{font-style:italic;color:var(--acc2)}

.vmeta-row{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-bottom:26px}
.badge{display:inline-block;padding:3px 9px;border-radius:4px;font-size:10px;
 font-family:var(--mono);letter-spacing:.05em;text-transform:uppercase}
.b1{background:rgba(94,234,212,.1);color:var(--acc);border:1px solid rgba(94,234,212,.2)}
.b2{background:rgba(232,185,35,.1);color:var(--gold);border:1px solid rgba(232,185,35,.2)}
.b3{background:rgba(139,147,159,.1);color:var(--txt2);border:1px solid var(--line)}
.vdate{font-family:var(--mono);font-size:11px;color:var(--txt3)}

.prose{max-width:660px;font-size:15.5px;line-height:1.85;color:var(--txt2);font-weight:300}
.prose p{margin-bottom:18px}
.prose strong{color:var(--txt);font-weight:500}

.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;
 background:var(--line);border:1px solid var(--line);border-radius:14px;
 overflow:hidden;margin:34px 0}
.m{background:var(--bg2);padding:22px 20px;transition:.25s}
.m:hover{background:var(--panel)}
.ml{font-size:10px;color:var(--txt3);text-transform:uppercase;letter-spacing:.1em;margin-bottom:8px}
.mv{font-family:var(--mono);font-size:22px;font-weight:600;letter-spacing:-.02em}
.pos{color:var(--acc)}
.neg{color:#f2707f}
.mut{color:var(--txt3)}

.curvebox{background:var(--bg2);border:1px solid var(--line);border-radius:12px;
 padding:16px 14px 10px;margin-bottom:34px}
.curvehead{font-family:var(--mono);font-size:10px;text-transform:uppercase;
 letter-spacing:.1em;color:var(--txt3);margin-bottom:8px}
.spark{width:100%;height:120px;display:block}

.grid2{display:grid;grid-template-columns:1fr 1fr;gap:26px;margin-bottom:32px}
.card{background:var(--bg2);border:1px solid var(--line);border-radius:12px;
 padding:22px 20px;transition:.25s}
.card:hover{border-color:#2a3238}
.ct{font-size:14px;font-weight:600;margin-bottom:14px;letter-spacing:-.01em}

.tbl{width:100%;border-collapse:collapse;font-size:13px}
.tbl th{text-align:right;padding:9px 10px;font-family:var(--mono);font-size:9.5px;
 text-transform:uppercase;letter-spacing:.1em;color:var(--txt3);
 border-bottom:1px solid var(--line);font-weight:500;white-space:nowrap}
.tbl th:first-child,.tbl td:first-child{text-align:left}
.tbl td{padding:9px 10px;border-bottom:1px solid rgba(29,34,40,.6);
 font-family:var(--mono);font-size:12px;text-align:right;white-space:nowrap}
.tbl tr:last-child td{border-bottom:none}
.tbl tbody tr:hover{background:rgba(255,255,255,.015)}
.tbl .n{color:var(--txt);font-weight:500}

.factrow{display:flex;flex-wrap:wrap;gap:8px 26px;padding:16px 20px;
 background:var(--bg2);border:1px solid var(--line);border-radius:12px;
 font-size:12px;color:var(--txt2);margin-bottom:26px}
.factrow b{color:var(--txt);font-weight:500;font-family:var(--mono)}

.cfgsnap{background:var(--bg2);border:1px solid var(--line);border-radius:12px;
 padding:20px 22px;margin-bottom:26px}
.cfgrow{display:flex;flex-wrap:wrap;gap:10px 28px;font-size:12.5px;color:var(--txt2)}
.cfgrow b{color:var(--txt);font-weight:500;font-family:var(--mono)}

.changelog ul{list-style:none;padding:0}
.changelog li{position:relative;padding-left:20px;font-size:13.5px;color:var(--txt2);
 margin-bottom:9px;line-height:1.7;font-weight:300}
.changelog li::before{content:'—';position:absolute;left:0;color:var(--acc);opacity:.5}

.tradelog{margin-top:30px;border-top:1px solid var(--line);padding-top:22px}
.tradelog summary{cursor:pointer;font-family:var(--mono);font-size:11px;
 text-transform:uppercase;letter-spacing:.1em;color:var(--acc);
 padding:6px 0;user-select:none;list-style:none;font-weight:500}
.tradelog summary::-webkit-details-marker{display:none}
.tradelog summary::before{content:'▸ ';display:inline-block;transition:.2s}
.tradelog[open] summary::before{transform:rotate(90deg)}
.scroll{max-height:460px;overflow-y:auto;margin-top:16px;
 border:1px solid var(--line);border-radius:10px}
.scroll .tbl th{position:sticky;top:0;background:var(--bg2);z-index:2}
.scroll::-webkit-scrollbar{width:8px}
.scroll::-webkit-scrollbar-track{background:var(--bg2)}
.scroll::-webkit-scrollbar-thumb{background:#242a31;border-radius:4px}

.quote{border-left:2px solid var(--acc);padding:6px 0 6px 30px;margin:44px 0;
 font-family:var(--serif);font-size:clamp(22px,3vw,30px);line-height:1.45;
 font-style:italic;color:var(--txt);letter-spacing:-.01em;max-width:720px}
.quote span{display:block;font-family:var(--ui);font-size:12px;font-style:normal;
 color:var(--txt3);margin-top:20px;letter-spacing:.06em;text-transform:uppercase}

.empty{color:var(--txt3);font-size:13px;font-style:italic;padding:18px 0;font-weight:300}

footer{border-top:1px solid var(--line);padding:34px 0;text-align:center;
 font-size:11.5px;color:var(--txt3);font-family:var(--mono)}
.disclaimer{max-width:640px;margin:22px auto 0;font-family:var(--ui);font-size:11px;
 line-height:1.7;color:var(--txt3);text-align:center}

@media(max-width:860px){
 .stats{grid-template-columns:repeat(2,1fr)}
 .metrics{grid-template-columns:repeat(2,1fr)}
 .grid2{grid-template-columns:1fr}
 .navlinks{display:none}
 .hero{padding:130px 0 60px}
 section{padding:60px 0}
}
</style>
</head>
<body>
<div class="glow g1"></div><div class="glow g2"></div>

<nav><div class="nav-in">
  <div class="logo"><div class="pulse"></div>QUANT FUTURES</div>
  <div class="navlinks">
    <a href="/terminal">Terminal</a>
    <a href="/calendar">PnL Calendar</a>
    <a href="/versions" class="on">Versions</a>
    <a href="/">About</a>
    <a href="/terminal" class="nav-cta">Terminal →</a>
  </div>
</div></nav>

<div class="wrap">

<div class="hero">
  <div class="eyebrow">Release Registry · Hyperliquid L1</div>
  <h1>Every version,<br>on the <em>record.</em></h1>
  <p class="lede">
    Each release of the strategy stack is logged here with its full performance breakdown,
    configuration snapshot, and complete trade ledger.
    <strong>Nothing is rewritten. Nothing is hidden.</strong>
  </p>

  <div class="stats">
    {{HERO_STATS}}
  </div>
</div>

{{VERSIONS}}

</div>

<footer>
  QUANT FUTURES — VERSION REGISTRY
  <div class="disclaimer">
    All figures measured from closed positions. Times in WIB (UTC+7).
    Past performance is not indicative of future results.
  </div>
</footer>
</body>
</html>
"""
