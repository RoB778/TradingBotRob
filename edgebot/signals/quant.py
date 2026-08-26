"""
Capa quant. Convierte precios crudos en senales interpretables.

La diferencia entre "TLT esta a 89.4" y "TLT esta 1.8 desviaciones
estandar por debajo de su media de 60 dias" es la diferencia entre un
dato y una senal. Aqui se hace esa conversion.
"""

from __future__ import annotations

from dataclasses import dataclass

import yfinance as yf


@dataclass
class YieldCurvePoint:
    """La curva de tipos es el indicador macro mas seguido que existe.
    Inversion (corto > largo) ha precedido casi toda recesion de EEUU
    desde los 60. No es infalible, pero es la senal individual con
    mejor historial.
    """
    short_yield: float   # 2 anios (^IRX es 13-week, se usa como proxy corto)
    long_yield: float    # 10 anios (^TNX)
    spread: float         # largo - corto
    inverted: bool

    @property
    def note(self) -> str:
        if self.inverted:
            return f"curva invertida ({self.spread:+.2f}pp) -- historicamente senal de alerta de recesion"
        return f"curva normal ({self.spread:+.2f}pp)"


@dataclass
class ZScore:
    ticker: str
    label: str
    current: float
    mean_60d: float
    std_60d: float
    z: float

    @property
    def note(self) -> str:
        if abs(self.z) < 1:
            return "dentro de rango normal"
        direction = "por encima" if self.z > 0 else "por debajo"
        magnitude = "extremo" if abs(self.z) > 2 else "notable"
        return f"{magnitude}, {abs(self.z):.1f} desv. std {direction} de su media de 60d"


def fetch_yield_curve() -> YieldCurvePoint | None:
    try:
        short = yf.Ticker("^IRX").history(period="5d")["Close"].iloc[-1]
        long = yf.Ticker("^TNX").history(period="5d")["Close"].iloc[-1]
        spread = float(long) - float(short)
        return YieldCurvePoint(
            short_yield=float(short), long_yield=float(long),
            spread=spread, inverted=spread < 0,
        )
    except Exception as e:
        print(f"[quant] fallo yield curve: {e}")
        return None


def zscore(ticker: str, label: str, window: int = 60) -> ZScore | None:
    try:
        hist = yf.Ticker(ticker).history(period=f"{window + 5}d")["Close"]
        if len(hist) < window // 2:
            return None
        recent = hist.tail(window)
        mean, std = float(recent.mean()), float(recent.std())
        current = float(hist.iloc[-1])
        z = (current - mean) / std if std > 0 else 0.0
        return ZScore(ticker=ticker, label=label, current=current,
                       mean_60d=mean, std_60d=std, z=z)
    except Exception as e:
        print(f"[quant] fallo z-score {ticker}: {e}")
        return None


WATCH_ZSCORES = {
    "^VIX": "VIX",
    "GLD": "Oro (ETF)",
    "TLT": "Bonos largos",
    "BTC-USD": "Bitcoin",
}


def full_quant_snapshot() -> dict:
    return {
        "yield_curve": fetch_yield_curve(),
        "zscores": [z for t, l in WATCH_ZSCORES.items() if (z := zscore(t, l)) is not None],
    }
