"""
Acceso a datos de Polymarket.

Dos APIs distintas, y conviene tenerlo claro desde el principio:

  - Gamma API  (gamma-api.polymarket.com) -> descubrimiento de mercados.
    Publica, sin autenticacion, sin wallet. Es por donde empezamos.
    Sus precios pueden ir unos segundos por detras del libro real.

  - CLOB API   (clob.polymarket.com)      -> libro de ordenes y trading.
    Para leer el libro no hace falta firmar. Para operar, si: wallet,
    private key y allowances.

Esta capa es SOLO LECTURA. No firma nada, no envia ordenes, no toca la
private key. La ejecucion vive en otro modulo y de momento no existe.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


@dataclass
class Market:
    """Un mercado binario, normalizado."""

    condition_id: str
    question: str
    slug: str
    end_date: datetime | None
    volume_24h: float
    liquidity: float
    # token_id -> nombre del outcome ("Yes" / "No")
    tokens: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def minutes_to_close(self) -> float | None:
        if self.end_date is None:
            return None
        delta = self.end_date - datetime.now(timezone.utc)
        return delta.total_seconds() / 60


@dataclass
class BookSide:
    price: float
    size: float


@dataclass
class OrderBook:
    """Libro de un token concreto. Aqui vive la verdad sobre la liquidez."""

    token_id: str
    bids: list[BookSide]  # ordenados de mejor (mas alto) a peor
    asks: list[BookSide]  # ordenados de mejor (mas bajo) a peor
    fetched_at: float = field(default_factory=time.time)

    @property
    def best_bid(self) -> float | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0].price if self.asks else None

    @property
    def mid(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    def depth_within(self, max_price: float, side: str = "asks") -> float:
        """Cuantos shares puedo comprar sin pasar de max_price.

        Esto es lo que de verdad limita el tamano de tu apuesta en
        mercados finos. El precio que ves de nada sirve si solo hay
        12 shares detras.
        """
        levels = self.asks if side == "asks" else self.bids
        total = 0.0
        for lvl in levels:
            if side == "asks" and lvl.price > max_price:
                break
            if side == "bids" and lvl.price < max_price:
                break
            total += lvl.size
        return total


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class PolymarketReader:
    """Lectura de mercados y libros. Nada mas."""

    def __init__(self, timeout: float = 10.0) -> None:
        self._client = httpx.Client(timeout=timeout, headers={"User-Agent": "edgebot/0.1"})

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PolymarketReader":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------- Gamma

    def list_markets(
        self,
        limit: int = 50,
        active: bool = True,
        closed: bool = False,
        order: str = "volume24hr",
    ) -> list[Market]:
        """Mercados activos ordenados por volumen de 24h."""
        resp = self._client.get(
            f"{GAMMA}/markets",
            params={
                "limit": limit,
                "active": active,
                "closed": closed,
                "order": order,
                "ascending": False,
            },
        )
        resp.raise_for_status()
        return [self._to_market(m) for m in resp.json()]

    def search_markets(self, needle: str, limit: int = 200) -> list[Market]:
        """Filtro por texto sobre la pregunta del mercado.

        Rudimentario a proposito: Gamma no expone una busqueda
        semantica y no merece la pena inventarsela todavia.
        """
        needle = needle.lower()
        return [m for m in self.list_markets(limit=limit) if needle in m.question.lower()]

    @staticmethod
    def _to_market(raw: dict[str, Any]) -> Market:
        # Gamma devuelve outcomes y clobTokenIds como listas o como
        # strings con JSON dentro, segun el endpoint y el dia.
        import json

        def _as_list(value: Any) -> list[Any]:
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    return parsed if isinstance(parsed, list) else []
                except json.JSONDecodeError:
                    return []
            return []

        outcomes = _as_list(raw.get("outcomes"))
        token_ids = _as_list(raw.get("clobTokenIds"))
        tokens = {str(tid): str(name) for tid, name in zip(token_ids, outcomes)}

        return Market(
            condition_id=str(raw.get("conditionId", "")),
            question=str(raw.get("question", "")),
            slug=str(raw.get("slug", "")),
            end_date=_parse_dt(raw.get("endDate")),
            volume_24h=float(raw.get("volume24hr") or 0),
            liquidity=float(raw.get("liquidity") or 0),
            tokens=tokens,
            raw=raw,
        )

    # ----------------------------------------------------------------- CLOB

    def order_book(self, token_id: str) -> OrderBook:
        """Libro real. Usar esto, no el precio de Gamma, para decidir."""
        resp = self._client.get(f"{CLOB}/book", params={"token_id": token_id})
        resp.raise_for_status()
        data = resp.json()

        def _levels(key: str) -> list[BookSide]:
            return [
                BookSide(price=float(lvl["price"]), size=float(lvl["size"]))
                for lvl in data.get(key) or []
            ]

        bids = sorted(_levels("bids"), key=lambda b: b.price, reverse=True)
        asks = sorted(_levels("asks"), key=lambda a: a.price)
        return OrderBook(token_id=token_id, bids=bids, asks=asks)

    def health(self) -> bool:
        try:
            return self._client.get(f"{CLOB}/ok").status_code == 200
        except httpx.HTTPError:
            return False
