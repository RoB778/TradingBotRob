"""
Cuanto apostar.

Kelly completo maximiza el crecimiento a largo plazo asumiendo que tus
probabilidades son correctas. Las tuyas no lo son: salen de un LLM
leyendo tweets. Por eso aqui se usa Kelly fraccional agresivamente
recortado, y encima varios topes duros.

Con un banco de 150 EUR, la ruina no es una abstraccion academica.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLimits:
    bankroll: float = 150.0
    kelly_fraction: float = 0.25       # cuarto de Kelly
    max_pct_per_trade: float = 0.04    # 4% del banco = 6 EUR
    min_stake: float = 1.0             # por debajo, las comisiones se lo comen
    min_edge: float = 0.07             # 7 puntos de probabilidad
    max_open_positions: int = 5
    max_daily_loss_pct: float = 0.15   # tras -15% en un dia, el bot para


def kelly_fraction(model_prob: float, price: float) -> float:
    """Fraccion optima del banco para un mercado binario.

    Comprando un share a `price`, cobras 1 si aciertas. Es decir:
    ganas (1-price)/price por unidad arriesgada.

        f* = (p*b - q) / b   con b = (1-price)/price
    """
    if not 0 < price < 1 or not 0 <= model_prob <= 1:
        return 0.0
    b = (1 - price) / price
    f = (model_prob * b - (1 - model_prob)) / b
    return max(0.0, f)


def stake_for(
    model_prob: float,
    price: float,
    limits: RiskLimits,
    open_positions: int = 0,
    day_pnl: float = 0.0,
) -> tuple[float, str]:
    """Devuelve (cantidad_en_eur, motivo). 0 significa no operar."""

    if day_pnl < -limits.bankroll * limits.max_daily_loss_pct:
        return 0.0, "limite de perdida diaria alcanzado; el bot para hoy"

    if open_positions >= limits.max_open_positions:
        return 0.0, "demasiadas posiciones abiertas"

    edge = model_prob - price
    if edge < limits.min_edge:
        return 0.0, f"edge insuficiente ({edge:.3f} < {limits.min_edge})"

    f = kelly_fraction(model_prob, price) * limits.kelly_fraction
    stake = min(f * limits.bankroll, limits.max_pct_per_trade * limits.bankroll)

    if stake < limits.min_stake:
        return 0.0, "stake por debajo del minimo util"

    return round(stake, 2), f"kelly/{1/limits.kelly_fraction:.0f}, edge {edge:.3f}"
