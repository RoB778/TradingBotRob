"""
Senales de mercado tradicional, como contexto para el analisis macro.

La idea no es tradear stocks -- es usar lo que YA sabe el mercado de
bonos y volatilidad para informar mejor la estimacion sobre la Fed.
Estos tres tickers son proxies estandar:

  ^VIX  -> miedo/incertidumbre. VIX alto = mercado nervioso, mas
           probable que la Fed actue con cautela o de emergencia.
  TLT   -> bonos largos (20+ anios). Sube cuando el mercado espera
           bajadas de tipos, baja cuando espera subidas o inflacion
           persistente. Es, en la practica, una apuesta de bond traders
           profesionales sobre la Fed -- gratis, y mas informada que
           cualquier tweet.
  DXY   -> fortaleza del dolar. Correlaciona (inversamente) con BTC y
           oro; sube con tipos altos o huida a calidad.

Nada de esto se opera. Es contexto que se anade al prompt del analyzer,
igual que las noticias. El modelo lee "TLT subio 1.2% esta semana" del
mismo modo que lee un titular -- es una senal mas, no una orden.
"""

from __future__ import annotations

from dataclasses import dataclass

import yfinance as yf

TICKERS = {
    "^VIX": "VIX (miedo/volatilidad)",
    "TLT": "TLT (bonos largos, apuesta de tipos)",
    "UUP": "DXY proxy (fortaleza del dolar)",  # UUP es el ETF, mas fiable via yfinance que ^DXY
}


@dataclass
class MarketSignal:
    ticker: str
    label: str
    last: float
    change_1d_pct: float
    change_5d_pct: float

    def as_line(self) -> str:
        arrow = "↑" if self.change_5d_pct > 0 else "↓"
        return (
            f"{self.label}: {self.last:.2f} "
            f"(1d: {self.change_1d_pct:+.2f}%, 5d: {self.change_5d_pct:+.2f}% {arrow})"
        )


def fetch_market_context() -> list[MarketSignal]:
    """Ultimo precio y variacion. Tolerante a fallos: un ticker caido
    no debe tumbar el pipeline entero -- se omite y se sigue.
    """
    out: list[MarketSignal] = []
    for ticker, label in TICKERS.items():
        try:
            hist = yf.Ticker(ticker).history(period="10d")
            if len(hist) < 2:
                continue
            closes = hist["Close"]
            last = float(closes.iloc[-1])
            prev = float(closes.iloc[-2])
            base5 = float(closes.iloc[max(0, len(closes) - 6)])
            out.append(
                MarketSignal(
                    ticker=ticker,
                    label=label,
                    last=last,
                    change_1d_pct=100 * (last - prev) / prev,
                    change_5d_pct=100 * (last - base5) / base5,
                )
            )
        except Exception as e:
            print(f"[market_context] {ticker} fallo, omito: {e}")
            continue
    return out


def as_prompt_block(signals: list[MarketSignal]) -> str:
    if not signals:
        return ""
    lines = ["CONTEXTO DE MERCADOS (proxies de lo que ya descuenta el mercado profesional):"]
    lines += [f"- {s.as_line()}" for s in signals]
    return "\n".join(lines)


if __name__ == "__main__":
    sigs = fetch_market_context()
    print(as_prompt_block(sigs))
