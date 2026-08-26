"""
Paper trading propio.

Polymarket no tiene testnet ni modo simulacion: para probar el envio de
ordenes trabajas con fondos reales. Asi que el sandbox nos lo montamos
aqui, contra precios reales pero sin dinero.

La regla del proyecto: NO se toca dinero real hasta que este ledger
acumule una muestra decente de operaciones simuladas y el edge sobreviva.

El fill se simula caminando el libro de verdad, no asumiendo que te
llenan al mejor precio. Un simulador optimista es peor que no tener
simulador, porque te da confianza falsa antes de arriesgar capital.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from edgebot.markets.polymarket import OrderBook

DB_PATH = Path("data/paper.db")


@dataclass
class Fill:
    """Resultado de intentar cruzar el libro."""

    shares: float
    avg_price: float
    cost: float
    slippage: float  # precio medio menos mejor precio, en centimos de probabilidad
    partial: bool  # True si el libro no daba para el tamano pedido


def simulate_buy(book: OrderBook, usd_to_spend: float) -> Fill | None:
    """Camina el lado ask consumiendo niveles hasta gastar el presupuesto.

    Devuelve None si no hay libro. El campo `partial` es la senal mas
    util de todas: si sale True de forma sistematica, el mercado es
    demasiado fino para tu tamano y da igual lo bueno que sea tu modelo.
    """
    if not book.asks:
        return None

    best = book.asks[0].price
    remaining = usd_to_spend
    shares = 0.0
    cost = 0.0

    for level in book.asks:
        level_cost = level.price * level.size
        if level_cost <= remaining:
            shares += level.size
            cost += level_cost
            remaining -= level_cost
        else:
            take = remaining / level.price
            shares += take
            cost += remaining
            remaining = 0.0
            break

    if shares == 0:
        return None

    avg = cost / shares
    return Fill(
        shares=shares,
        avg_price=avg,
        cost=cost,
        slippage=avg - best,
        partial=remaining > 0.01,
    )


class PaperLedger:
    """Registro persistente de operaciones simuladas."""

    def __init__(self, path: Path = DB_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                opened_at     TEXT NOT NULL,
                condition_id  TEXT NOT NULL,
                token_id      TEXT NOT NULL,
                question      TEXT NOT NULL,
                -- lo que creia el modelo en el momento de entrar
                model_prob    REAL NOT NULL,
                market_price  REAL NOT NULL,
                edge          REAL NOT NULL,
                rationale     TEXT,
                -- ejecucion simulada
                shares        REAL NOT NULL,
                avg_price     REAL NOT NULL,
                cost          REAL NOT NULL,
                slippage      REAL NOT NULL,
                partial       INTEGER NOT NULL,
                -- resolucion
                resolved_at   TEXT,
                outcome       INTEGER,      -- 1 gano, 0 perdio
                pnl           REAL
            );
            CREATE INDEX IF NOT EXISTS idx_open ON trades(resolved_at);
            """
        )
        self.conn.commit()

    def record(
        self,
        *,
        condition_id: str,
        token_id: str,
        question: str,
        model_prob: float,
        market_price: float,
        fill: Fill,
        rationale: dict | None = None,
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO trades (opened_at, condition_id, token_id, question,
                                   model_prob, market_price, edge, rationale,
                                   shares, avg_price, cost, slippage, partial)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                condition_id,
                token_id,
                question,
                model_prob,
                market_price,
                model_prob - fill.avg_price,
                json.dumps(rationale or {}, ensure_ascii=False),
                fill.shares,
                fill.avg_price,
                fill.cost,
                fill.slippage,
                int(fill.partial),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def resolve(self, trade_id: int, won: bool) -> None:
        """Cierra una operacion. Un share ganador vale 1.00, uno perdedor 0."""
        row = self.conn.execute("SELECT shares, cost FROM trades WHERE id=?", (trade_id,)).fetchone()
        if row is None:
            raise KeyError(f"trade {trade_id} no existe")
        payout = row["shares"] if won else 0.0
        self.conn.execute(
            "UPDATE trades SET resolved_at=?, outcome=?, pnl=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), int(won), payout - row["cost"], trade_id),
        )
        self.conn.commit()

    def open_trades(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM trades WHERE resolved_at IS NULL").fetchall()

    def stats(self) -> dict:
        """El unico informe que importa antes de poner dinero real."""
        rows = self.conn.execute("SELECT * FROM trades WHERE resolved_at IS NOT NULL").fetchall()
        if not rows:
            return {"n": 0, "veredicto": "sin datos suficientes"}

        n = len(rows)
        pnl = sum(r["pnl"] for r in rows)
        invested = sum(r["cost"] for r in rows)
        wins = sum(1 for r in rows if r["outcome"])
        partials = sum(1 for r in rows if r["partial"])

        # Calibracion: cuando el modelo dijo 70%, gano el 70% de las veces?
        # Si el modelo esta sistematicamente por encima del resultado real,
        # el "edge" era imaginacion.
        avg_model = sum(r["model_prob"] for r in rows) / n
        real_rate = wins / n

        return {
            "n": n,
            "pnl": round(pnl, 2),
            "roi_pct": round(100 * pnl / invested, 2) if invested else 0.0,
            "win_rate": round(real_rate, 3),
            "prob_media_modelo": round(avg_model, 3),
            "error_calibracion": round(avg_model - real_rate, 3),
            "slippage_medio": round(sum(r["slippage"] for r in rows) / n, 4),
            "pct_fills_parciales": round(100 * partials / n, 1),
            "veredicto": _verdict(n, pnl, avg_model - real_rate),
        }


def _verdict(n: int, pnl: float, calib_error: float) -> str:
    if n < 50:
        return f"muestra corta ({n}). No concluyas nada todavia."
    if calib_error > 0.05:
        return "el modelo es optimista: se cree mas listo de lo que es. No pases a real."
    if pnl <= 0:
        return "sin edge demostrado. No pases a real."
    return "edge plausible. Revisa por que funciona antes de arriesgar."
