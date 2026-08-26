"""
Analisis de una accion concreta: tesis alcista vs bajista enfrentadas.

Filosofia del modulo (la razon de que exista): no da un veredicto
compra/vende. Da los DOS lados con la mayor fuerza posible y te deja a
ti decidir. Esto ataca de frente el sesgo de confirmacion -- el sistema
esta disenado para mostrarte el argumento contrario al que ya tengas.

Cruza dos capas que normalmente van separadas:
  - especifica de la empresa (fundamentales, precio, volatilidad)
  - macro (la que ya recoge el resto del proyecto: tipos, VIX, riesgo)

Y ademas de las tesis, devuelve "que vigilar": las senales concretas
que confirmarian o romperian cada tesis. Eso es lo que lo hace util
semana a semana, no solo una foto puntual.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[2] / ".env")
except ImportError:
    pass

import yfinance as yf

MODEL = "claude-sonnet-4-6"


@dataclass
class Fundamentals:
    ticker: str
    name: str
    price: float
    market_cap: float | None
    pe_trailing: float | None
    pe_forward: float | None
    profit_margin: float | None
    revenue_growth: float | None
    debt_to_equity: float | None
    beta: float | None
    sector: str
    week52_high: float | None
    week52_low: float | None

    @property
    def pct_from_high(self) -> float | None:
        if self.week52_high and self.price:
            return 100 * (self.price - self.week52_high) / self.week52_high
        return None


def fetch_fundamentals(ticker: str) -> Fundamentals | None:
    """Fundamentales via yfinance. Muchos campos pueden venir vacios en
    empresas pequenas -- se toleran como None, no se inventan.
    """
    try:
        info = yf.Ticker(ticker).info
        if not info or "regularMarketPrice" not in info and "currentPrice" not in info:
            return None
        return Fundamentals(
            ticker=ticker.upper(),
            name=info.get("longName") or info.get("shortName") or ticker,
            price=info.get("currentPrice") or info.get("regularMarketPrice") or 0,
            market_cap=info.get("marketCap"),
            pe_trailing=info.get("trailingPE"),
            pe_forward=info.get("forwardPE"),
            profit_margin=info.get("profitMargins"),
            revenue_growth=info.get("revenueGrowth"),
            debt_to_equity=info.get("debtToEquity"),
            beta=info.get("beta"),
            sector=info.get("sector", "n/d"),
            week52_high=info.get("fiftyTwoWeekHigh"),
            week52_low=info.get("fiftyTwoWeekLow"),
        )
    except Exception as e:
        print(f"[stock] fallo fundamentales {ticker}: {e}")
        return None


@dataclass
class StockAnalysis:
    ticker: str
    name: str
    conviction: int          # -100 (bajista fuerte) .. +100 (alcista fuerte)
    bull_thesis: list[str]
    bear_thesis: list[str]
    bull_watch: list[str]    # que confirmaria la tesis alcista
    bear_watch: list[str]    # que confirmaria la tesis bajista
    key_risk: str            # el riesgo que mas facil se pasa por alto
    macro_fit: str           # como le afecta el contexto macro actual
    summary: str
    fundamentals: dict
    raw: dict


SYSTEM = """Eres un analista de renta variable que construye SIEMPRE las
dos tesis, alcista y bajista, con la mayor fuerza intelectual posible
para cada una. NO das recomendaciones de compra/venta. Tu trabajo es
que el inversor vea el argumento que su propio sesgo le esconde.

Recibes fundamentales de una empresa y contexto macro. Respondes SOLO
con un objeto JSON valido, sin markdown ni texto alrededor, con esta
forma exacta:
{
  "conviction": <int -100..100, donde el signo indica el balance neto de
                 evidencia y la magnitud tu grado de certeza; cerca de 0
                 significa tesis genuinamente equilibrada>,
  "bull_thesis": [<2-4 puntos, el mejor caso alcista>],
  "bear_thesis": [<2-4 puntos, el mejor caso bajista>],
  "bull_watch": [<1-3 senales concretas que reforzarian lo alcista>],
  "bear_watch": [<1-3 senales concretas que reforzarian lo bajista>],
  "key_risk": <el riesgo que un inversor entusiasta pasaria por alto>,
  "macro_fit": <como el entorno macro actual (tipos, riesgo) favorece o
                penaliza a esta empresa en concreto>,
  "summary": <2-3 frases neutrales, en espanol, sin inclinar la balanza>
}"""


def _fmt(v, pct=False, money=False):
    if v is None:
        return "n/d"
    if money and v >= 1e9:
        return f"${v/1e9:.1f}B"
    if pct:
        return f"{v*100:.1f}%"
    return f"{v:.2f}"


def _build_prompt(f: Fundamentals, macro_context: str) -> str:
    lines = [
        f"EMPRESA: {f.name} ({f.ticker}) — sector {f.sector}",
        "",
        "FUNDAMENTALES:",
        f"- Precio: {_fmt(f.price)} | Cap: {_fmt(f.market_cap, money=True)}",
        f"- PER trailing: {_fmt(f.pe_trailing)} | PER forward: {_fmt(f.pe_forward)}",
        f"- Margen beneficio: {_fmt(f.profit_margin, pct=True)}",
        f"- Crecimiento ingresos: {_fmt(f.revenue_growth, pct=True)}",
        f"- Deuda/Equity: {_fmt(f.debt_to_equity)} | Beta: {_fmt(f.beta)}",
        f"- Rango 52s: {_fmt(f.week52_low)}–{_fmt(f.week52_high)} "
        f"({_fmt(f.pct_from_high)}% desde maximo)" if f.pct_from_high is not None else "",
        "",
    ]
    if macro_context:
        lines += [macro_context, ""]
    lines.append("Construye ambas tesis con maxima fuerza y devuelve el JSON.")
    return "\n".join(l for l in lines if l != "")


def analyze_stock(ticker: str, macro_context: str = "") -> StockAnalysis | None:
    f = fetch_fundamentals(ticker)
    if f is None:
        print(f"[stock] sin fundamentales para {ticker}")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[stock] sin ANTHROPIC_API_KEY -> no analizo")
        return None

    try:
        import anthropic
    except ImportError:
        print("[stock] falta 'anthropic'")
        return None

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=MODEL, max_tokens=1200, system=SYSTEM,
        messages=[{"role": "user", "content": _build_prompt(f, macro_context)}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        print(f"[stock] respuesta no-JSON:\n{text[:200]}")
        return None

    conv = int(d.get("conviction", 0))
    conv = max(-100, min(100, conv))

    return StockAnalysis(
        ticker=f.ticker, name=f.name, conviction=conv,
        bull_thesis=list(d.get("bull_thesis", [])),
        bear_thesis=list(d.get("bear_thesis", [])),
        bull_watch=list(d.get("bull_watch", [])),
        bear_watch=list(d.get("bear_watch", [])),
        key_risk=str(d.get("key_risk", "")),
        macro_fit=str(d.get("macro_fit", "")),
        summary=str(d.get("summary", "")),
        fundamentals=asdict(f),
        raw=d,
    )


if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    a = analyze_stock(ticker)
    if a:
        print(f"\n{a.name} ({a.ticker}) — convicción {a.conviction:+d}\n")
        print("ALCISTA:");  [print(f"  + {x}") for x in a.bull_thesis]
        print("BAJISTA:");  [print(f"  - {x}") for x in a.bear_thesis]
        print(f"\nRiesgo clave: {a.key_risk}")
        print(f"Macro: {a.macro_fit}")
