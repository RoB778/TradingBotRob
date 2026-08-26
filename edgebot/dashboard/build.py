"""
Genera el dashboard como HTML autocontenido.

Direccion visual: "instrumento de precision". No es una web de
marketing, es un panel de lectura. Fondo grafito azulado (no negro
puro, que es cliche), datos en monoespaciada tabular, y un unico acento
ambar reservado SOLO para lo accionable. La firma es el "medidor de
conviccion": alcista y bajista empujan desde extremos opuestos y el
punto de equilibrio hace visible cuanta tension hay en la tesis.

Ejecutar:  python -m edgebot.dashboard.build           (solo macro)
           python -m edgebot.dashboard.build NVDA AAPL  (macro + acciones)
Abre:      dashboard/index.html
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")

from edgebot.signals import news, geopolitics, crypto_sentiment, quant
from edgebot.signals.market_context import fetch_market_context, as_prompt_block
from edgebot.signals.stock import analyze_stock

OUT_DIR = Path("dashboard")
OUT_FILE = OUT_DIR / "index.html"


def gather(tickers: list[str]) -> dict:
    data: dict = {"generated_at": datetime.now(timezone.utc).isoformat()}

    def safe(key, fn):
        try:
            data[key] = fn()
        except Exception as e:
            data[key] = None
            data[f"{key}_error"] = str(e)

    safe("fed_news", lambda: [vars(n) | {"published": str(n.published)} for n in news.collect()[:10]])
    safe("geo_news", lambda: [vars(n) | {"published": str(n.published)} for n in geopolitics.collect()[:10]])
    safe("market", lambda: [vars(s) for s in fetch_market_context()])

    def _fng():
        fg = crypto_sentiment.fetch_fear_greed()
        return (vars(fg) | {"note": fg.contrarian_note}) if fg else None
    safe("fear_greed", _fng)

    def _quant():
        snap = quant.full_quant_snapshot()
        yc = snap["yield_curve"]
        return {
            "yield_curve": (vars(yc) | {"note": yc.note}) if yc else None,
            "zscores": [vars(z) | {"note": z.note} for z in snap["zscores"]],
        }
    safe("quant", _quant)

    stocks = []
    if tickers:
        macro_block = ""
        try:
            macro_block = as_prompt_block(fetch_market_context())
        except Exception:
            pass
        for t in tickers:
            try:
                a = analyze_stock(t, macro_block)
                if a:
                    stocks.append({
                        "ticker": a.ticker, "name": a.name, "conviction": a.conviction,
                        "bull_thesis": a.bull_thesis, "bear_thesis": a.bear_thesis,
                        "bull_watch": a.bull_watch, "bear_watch": a.bear_watch,
                        "key_risk": a.key_risk, "macro_fit": a.macro_fit,
                        "summary": a.summary, "fundamentals": a.fundamentals,
                    })
            except Exception as e:
                print(f"[dashboard] fallo analisis {t}: {e}")
    data["stocks"] = stocks
    return data


TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panel de instrumentos · macro & valores</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  :root {
    --bg:#141821; --panel:#1c2230; --panel-2:#232b3b; --line:#2c3548;
    --ink:#e8ecf2; --ink-dim:#8a94a8; --ink-faint:#5c6577;
    --amber:#e0a340; --bull:#5aa86f; --bear:#d16b5c; --mauve:#8b7fb5;
    --mono:'IBM Plex Mono',monospace; --disp:'Space Grotesk',sans-serif; --body:'Inter',sans-serif;
  }
  @media (prefers-reduced-motion: reduce){ *{animation:none!important;transition:none!important} }
  * { box-sizing:border-box; }
  body {
    background:var(--bg); color:var(--ink); font-family:var(--body);
    margin:0; padding:32px 28px 60px; line-height:1.5;
    background-image:radial-gradient(circle at 20% -10%, rgba(224,163,64,0.04), transparent 40%);
  }
  .head { display:flex; justify-content:space-between; align-items:flex-end;
    border-bottom:1px solid var(--line); padding-bottom:16px; margin-bottom:28px; }
  .head h1 { font-family:var(--disp); font-weight:700; font-size:1.5rem; letter-spacing:-0.02em; margin:0; }
  .head .eyebrow { font-family:var(--mono); font-size:0.7rem; color:var(--amber);
    text-transform:uppercase; letter-spacing:0.18em; margin-bottom:6px; }
  .head .stamp { font-family:var(--mono); font-size:0.72rem; color:var(--ink-faint); text-align:right; }
  .head .stamp b { color:var(--ink-dim); font-weight:500; }
  .section-label { font-family:var(--mono); font-size:0.7rem; color:var(--ink-faint);
    text-transform:uppercase; letter-spacing:0.15em; margin:36px 0 14px; display:flex; align-items:center; gap:10px; }
  .section-label::after { content:''; flex:1; height:1px; background:var(--line); }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; }
  .panel { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:18px; }
  .panel canvas { min-height:150px; }
  .panel h2 { font-family:var(--mono); font-size:0.72rem; color:var(--ink-dim);
    text-transform:uppercase; letter-spacing:0.1em; margin:0 0 14px; font-weight:500; }
  .row { display:flex; justify-content:space-between; align-items:baseline; padding:7px 0; border-bottom:1px solid var(--line); }
  .row:last-child { border-bottom:none; }
  .k { color:var(--ink-dim); font-size:0.85rem; }
  .v { font-family:var(--mono); font-weight:500; font-size:0.9rem; }
  .up{color:var(--bull)} .down{color:var(--bear)}
  .note { font-size:0.76rem; color:var(--ink-faint); margin-top:10px; font-style:italic; line-height:1.45; }
  .fng { text-align:center; padding:6px 0 2px; }
  .fng .n { font-family:var(--mono); font-size:2.6rem; font-weight:600; line-height:1; }
  .fng .c { font-family:var(--mono); font-size:0.78rem; color:var(--ink-dim); text-transform:uppercase; letter-spacing:0.12em; margin-top:6px; }
  .news { padding:9px 0; border-bottom:1px solid var(--line); }
  .news:last-child{border-bottom:none}
  .news .t { font-size:0.85rem; line-height:1.35; }
  .news .s { font-family:var(--mono); font-size:0.68rem; color:var(--ink-faint); margin-top:3px; text-transform:uppercase; letter-spacing:0.05em; }
  .friction { background:linear-gradient(180deg, rgba(139,127,181,0.08), transparent);
    border:1px solid var(--mauve); border-radius:10px; padding:13px 15px; font-size:0.82rem; margin-top:10px; color:#c9c2e0; line-height:1.5; }
  .friction b { color:var(--mauve); }
  .stock { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:22px; margin-bottom:16px; }
  .stock-head { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:18px; }
  .stock-name { font-family:var(--disp); font-weight:700; font-size:1.25rem; letter-spacing:-0.01em; }
  .stock-ticker { font-family:var(--mono); color:var(--amber); font-size:0.8rem; letter-spacing:0.1em; margin-top:2px; }
  .stock-price { font-family:var(--mono); font-size:1.1rem; text-align:right; }
  .stock-sector { font-family:var(--mono); font-size:0.68rem; color:var(--ink-faint); text-transform:uppercase; letter-spacing:0.08em; text-align:right; margin-top:3px; }
  .gauge-wrap { margin:6px 0 20px; }
  .gauge-labels { display:flex; justify-content:space-between; font-family:var(--mono); font-size:0.7rem; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:7px; }
  .gauge-labels .bear-l{color:var(--bear)} .gauge-labels .bull-l{color:var(--bull)}
  .gauge { position:relative; height:10px; border-radius:5px;
    background:linear-gradient(90deg, rgba(209,107,92,0.35), rgba(138,148,168,0.15) 50%, rgba(90,168,111,0.35)); }
  .gauge .center { position:absolute; left:50%; top:-3px; bottom:-3px; width:1px; background:var(--ink-faint); }
  .gauge .needle { position:absolute; top:-4px; width:3px; height:18px; border-radius:2px;
    background:var(--amber); box-shadow:0 0 8px rgba(224,163,64,0.6); transform:translateX(-50%); transition:left 0.6s cubic-bezier(.2,.8,.2,1); }
  .gauge-read { font-family:var(--mono); font-size:0.72rem; color:var(--ink-dim); margin-top:8px; text-align:center; }
  .gauge-read b{color:var(--amber)}
  .theses { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:16px; }
  @media (max-width:640px){ .theses{grid-template-columns:1fr} }
  .thesis h3 { font-family:var(--mono); font-size:0.72rem; text-transform:uppercase; letter-spacing:0.1em; margin:0 0 10px; padding-bottom:6px; border-bottom:1px solid var(--line); }
  .thesis.bull h3{color:var(--bull)} .thesis.bear h3{color:var(--bear)}
  .thesis ul { margin:0; padding:0; list-style:none; }
  .thesis li { font-size:0.84rem; padding:6px 0 6px 16px; position:relative; line-height:1.4; }
  .thesis.bull li::before{content:'+';position:absolute;left:0;color:var(--bull);font-family:var(--mono)}
  .thesis.bear li::before{content:'\2212';position:absolute;left:0;color:var(--bear);font-family:var(--mono)}
  .watch { font-size:0.75rem; color:var(--ink-dim); margin-top:10px; padding-top:8px; border-top:1px dashed var(--line); }
  .watch b { font-family:var(--mono); font-size:0.66rem; text-transform:uppercase; letter-spacing:0.08em; color:var(--ink-faint); display:block; margin-bottom:4px; }
  .stock-foot { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:4px; }
  @media (max-width:640px){ .stock-foot{grid-template-columns:1fr} }
  .foot-box { background:var(--panel-2); border-radius:9px; padding:12px 14px; }
  .foot-box .lbl { font-family:var(--mono); font-size:0.66rem; text-transform:uppercase; letter-spacing:0.09em; margin-bottom:6px; }
  .foot-box.risk .lbl{color:var(--bear)} .foot-box.macro .lbl{color:var(--mauve)}
  .foot-box p { margin:0; font-size:0.83rem; line-height:1.45; }
  .stock-summary { font-size:0.85rem; color:var(--ink-dim); margin:16px 0 0; padding-top:14px; border-top:1px solid var(--line); line-height:1.55; }
  .disclaimer { font-family:var(--mono); font-size:0.68rem; color:var(--ink-faint); text-align:center; margin-top:40px; padding-top:20px; border-top:1px solid var(--line); line-height:1.6; }
  .empty { color:var(--ink-faint); font-size:0.83rem; }
</style>
</head>
<body>
<div class="head">
  <div>
    <div class="eyebrow">Panel de instrumentos</div>
    <h1>Lectura macro &amp; valores</h1>
  </div>
  <div class="stamp">Actualizado<br><b id="stamp"></b></div>
</div>
<div id="stocks-region"></div>
<div class="section-label">Contexto macro</div>
<div class="grid">
  <div class="panel"><h2>Mercados</h2><div id="market"></div></div>
  <div class="panel"><h2>Curva de tipos</h2><div id="yield"></div></div>
  <div class="panel"><h2>Sentimiento crypto</h2><div id="fng"></div></div>
  <div class="panel"><h2>Desviacion vs media 60d</h2><canvas id="zc" height="150"></canvas></div>
</div>
<div class="section-label">Flujo de noticias</div>
<div class="grid">
  <div class="panel"><h2>Fed / macro</h2><div id="fed-news"></div></div>
  <div class="panel"><h2>Geopolitica</h2><div id="geo-news"></div></div>
</div>
<div class="section-label">Friccion entre fuentes</div>
<div id="friction-region"></div>
<div class="disclaimer">
  Herramienta de investigacion para criterio propio · No es asesoramiento financiero · Ninguna cifra predice el precio<br>
  Las fuentes se muestran sin fusionar — el desacuerdo entre ellas es informacion, no ruido
</div>
<script>
const DATA = __DATA_JSON__;
const $ = id => document.getElementById(id);
$('stamp').textContent = new Date(DATA.generated_at).toLocaleString('es-ES',{dateStyle:'medium',timeStyle:'short'});
function convictionWord(c){
  const a=Math.abs(c); const dir=c>0?'alcista':c<0?'bajista':'neutral';
  const mag=a<20?'equilibrio':a<50?'inclinacion':a<75?'sesgo':'conviccion';
  return c===0?'equilibrio genuino':mag+' '+dir;
}
function stockCard(s){
  const f=s.fundamentals||{};
  const needlePos=50+(s.conviction/2);
  const price=f.price!=null?Number(f.price).toFixed(2):'—';
  const pe=f.pe_forward!=null?Number(f.pe_forward).toFixed(1):(f.pe_trailing!=null?Number(f.pe_trailing).toFixed(1):'n/d');
  const bull=(s.bull_thesis||[]).map(x=>'<li>'+x+'</li>').join('');
  const bear=(s.bear_thesis||[]).map(x=>'<li>'+x+'</li>').join('');
  const bw=(s.bull_watch||[]).join(' · ');
  const rw=(s.bear_watch||[]).join(' · ');
  return '<div class="stock"><div class="stock-head"><div>'+
    '<div class="stock-name">'+s.name+'</div><div class="stock-ticker">'+s.ticker+'</div></div>'+
    '<div><div class="stock-price">'+price+'</div><div class="stock-sector">'+(f.sector||'')+' · PER '+pe+'</div></div></div>'+
    '<div class="gauge-wrap"><div class="gauge-labels"><span class="bear-l">◄ bajista</span><span class="bull-l">alcista ►</span></div>'+
    '<div class="gauge"><div class="center"></div><div class="needle" style="left:'+needlePos+'%"></div></div>'+
    '<div class="gauge-read">balance de evidencia: <b>'+(s.conviction>0?'+':'')+s.conviction+'</b> · '+convictionWord(s.conviction)+'</div></div>'+
    '<div class="theses"><div class="thesis bull"><h3>Tesis alcista</h3><ul>'+bull+'</ul>'+
    (bw?'<div class="watch"><b>Que lo confirmaria</b>'+bw+'</div>':'')+'</div>'+
    '<div class="thesis bear"><h3>Tesis bajista</h3><ul>'+bear+'</ul>'+
    (rw?'<div class="watch"><b>Que lo confirmaria</b>'+rw+'</div>':'')+'</div></div>'+
    '<div class="stock-foot"><div class="foot-box risk"><div class="lbl">Riesgo que se pasa por alto</div><p>'+(s.key_risk||'—')+'</p></div>'+
    '<div class="foot-box macro"><div class="lbl">Encaje macro actual</div><p>'+(s.macro_fit||'—')+'</p></div></div>'+
    (s.summary?'<p class="stock-summary">'+s.summary+'</p>':'')+'</div>';
}
if(DATA.stocks && DATA.stocks.length){
  $('stocks-region').innerHTML='<div class="section-label">Analisis de valores</div>'+DATA.stocks.map(stockCard).join('');
}
if(DATA.market && DATA.market.length){
  $('market').innerHTML=DATA.market.map(m=>{
    const cls=m.change_5d_pct>=0?'up':'down', ar=m.change_5d_pct>=0?'▲':'▼';
    return '<div class="row"><span class="k">'+m.label+'</span><span class="v">'+Number(m.last).toFixed(2)+' <span class="'+cls+'">'+ar+' '+Number(m.change_5d_pct).toFixed(1)+'%</span></span></div>';
  }).join('');
} else $('market').innerHTML='<span class="empty">Sin datos — revisa la conexion</span>';
const q=DATA.quant||{};
if(q.yield_curve){
  const y=q.yield_curve;
  $('yield').innerHTML='<div class="row"><span class="k">Corto (13s)</span><span class="v">'+y.short_yield.toFixed(2)+'%</span></div>'+
    '<div class="row"><span class="k">Largo (10a)</span><span class="v">'+y.long_yield.toFixed(2)+'%</span></div>'+
    '<div class="row"><span class="k">Spread</span><span class="v '+(y.inverted?'down':'up')+'">'+y.spread.toFixed(2)+'pp</span></div>'+
    '<div class="note">'+y.note+'</div>';
} else $('yield').innerHTML='<span class="empty">Sin datos</span>';
if(DATA.fear_greed){
  const g=DATA.fear_greed;
  const col=g.value<=25?'var(--bear)':g.value>=75?'var(--bull)':'var(--amber)';
  $('fng').innerHTML='<div class="fng"><div class="n" style="color:'+col+'">'+g.value+'</div><div class="c">'+g.classification+'</div></div><div class="note">'+g.note+'</div>';
} else $('fng').innerHTML='<span class="empty">Sin datos</span>';
if(q.zscores && q.zscores.length){
  new Chart($('zc'),{type:'bar',
    data:{labels:q.zscores.map(z=>z.label),
      datasets:[{data:q.zscores.map(z=>z.z),
        backgroundColor:q.zscores.map(z=>Math.abs(z.z)>2?'#d16b5c':Math.abs(z.z)>1?'#e0a340':'#5aa86f'),
        borderRadius:3, barThickness:16}]},
    options:{indexAxis:'y', plugins:{legend:{display:false}},
      scales:{x:{grid:{color:'#2c3548'},ticks:{color:'#8a94a8',font:{family:'IBM Plex Mono'}}},
        y:{grid:{display:false},ticks:{color:'#e8ecf2',font:{family:'IBM Plex Mono'}}}}}});
}
function renderNews(el,items){
  if(!items||!items.length){el.innerHTML='<span class="empty">Sin datos</span>';return;}
  el.innerHTML=items.slice(0,7).map(n=>'<div class="news"><div class="t">'+n.title+'</div><div class="s">'+n.source+' · '+(n.published&&n.published!=='None'?n.published.slice(0,10):'')+'</div></div>').join('');
}
renderNews($('fed-news'),DATA.fed_news);
renderNews($('geo-news'),DATA.geo_news);
let flags=[];
if(DATA.fear_greed && DATA.fear_greed.value<=25 && DATA.market){
  const vix=DATA.market.find(m=>m.label.includes('VIX'));
  if(vix && vix.change_5d_pct<0) flags.push('El miedo en <b>crypto</b> es extremo pero el <b>VIX</b> (miedo en bolsa) baja — el miedo no es transversal, parece especifico de crypto.');
}
if(q.yield_curve && q.yield_curve.inverted) flags.push('La <b>curva esta invertida</b> (alerta clasica de recesion) — contrastalo con los z-scores antes de concluir desde una sola senal.');
if(DATA.stocks){ DATA.stocks.forEach(s=>{ if(Math.abs(s.conviction)<20) flags.push('<b>'+s.ticker+'</b>: la evidencia esta genuinamente equilibrada ('+(s.conviction>0?'+':'')+s.conviction+') — no fuerces una decision donde el propio analisis no la ve clara.'); }); }
$('friction-region').innerHTML = flags.length
  ? flags.map(f=>'<div class="friction">'+f+'</div>').join('')
  : '<div class="friction" style="border-color:var(--line);color:var(--ink-faint)">Sin discrepancias marcadas automaticamente. No significa que las fuentes coincidan en todo — revisalas.</div>';
</script>
</body>
</html>
"""


def build(tickers: list[str] | None = None) -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    data = gather(tickers or [])
    html = TEMPLATE.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False))
    OUT_FILE.write_text(html, encoding="utf-8")
    return OUT_FILE


if __name__ == "__main__":
    tickers = [t.upper() for t in sys.argv[1:]]
    path = build(tickers)
    print(f"Dashboard generado: {path.resolve()}")
    if not tickers:
        print("Consejo: pasa tickers, p.ej.  python -m edgebot.dashboard.build NVDA AAPL")
