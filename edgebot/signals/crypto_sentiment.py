"""
Sentimiento crypto agregado. Sin Twitter API de pago.

alternative.me publica el Fear & Greed Index de crypto, calculado a
partir de volatilidad, volumen, redes sociales y dominancia -- ya hace
el trabajo de agregar sentimiento que ibamos a montar con Twitter, y es
gratis y sin autenticacion.

Un solo numero no sustituye analisis, pero es la version cuantificada
de "el mercado esta eufórico o en panico", que es justo lo que buscabas
sacar del ruido de Twitter sin pagar la API.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

FNG_URL = "https://api.alternative.me/fng/"


@dataclass
class FearGreed:
    value: int  # 0-100
    classification: str  # "Extreme Fear".."Extreme Greed"
    timestamp: str

    @property
    def contrarian_note(self) -> str:
        """El indice funciona mejor al reves de lo intuitivo:
        panico extremo historicamente ha sido buena zona de entrada,
        euforia extrema mala. No es una regla, es un sesgo a vigilar.
        """
        if self.value <= 20:
            return "miedo extremo -- historicamente zona de descuento, no de panico vendedor"
        if self.value >= 80:
            return "codicia extrema -- historicamente zona de complacencia, cuidado"
        return "sin sesgo fuerte"


def fetch_fear_greed() -> FearGreed | None:
    try:
        resp = httpx.get(FNG_URL, params={"limit": 1}, timeout=10)
        resp.raise_for_status()
        data = resp.json()["data"][0]
        return FearGreed(
            value=int(data["value"]),
            classification=str(data["value_classification"]),
            timestamp=str(data["timestamp"]),
        )
    except Exception as e:
        print(f"[crypto_sentiment] fallo fear&greed: {e}")
        return None


if __name__ == "__main__":
    fg = fetch_fear_greed()
    if fg:
        print(f"{fg.value}/100 -- {fg.classification}")
        print(fg.contrarian_note)
