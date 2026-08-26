"""
El cerebro. Noticias -> probabilidad estructurada.

Aqui entra Claude. Le damos las noticias macro recientes y la pregunta
concreta del mercado ("cambia la Fed los tipos en septiembre?") y pedimos
una probabilidad calibrada CON su razonamiento.

Reglas de diseno que importan:

  - Salida ESTRUCTURADA (JSON). Un parrafo en prosa no se puede meter en
    un decision engine. Forzamos JSON y lo parseamos.

  - Pedimos calibracion explicita. El modelo tiende a la sobreconfianza;
    le exigimos que la probabilidad refleje incertidumbre real y que
    liste que la subiria o bajaria.

  - Esto NO decide operar. Devuelve una estimacion. La decision (sizing,
    limites) la toma engine/sizing.py con esta cifra como entrada. El
    cerebro opina; el gestor de riesgo manda.

  - Sin API key, este modulo no explota: avisa y devuelve None. Asi el
    resto del pipeline se puede probar gratis.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from edgebot.signals.news import NewsItem

MODEL = "claude-sonnet-4-6"  # ajusta al modelo que uses

SYSTEM = """Eres un analista macro que estima probabilidades para mercados
de eventos. Tu unico objetivo es la CALIBRACION: que cuando digas 70%,
acierte el 70% de las veces. La sobreconfianza te penaliza.

Respondes SIEMPRE y SOLO con un objeto JSON valido, sin texto alrededor,
sin markdown, con esta forma exacta:
{
  "probability": <float 0..1>,
  "confidence": <"low"|"medium"|"high">,
  "key_drivers": [<hasta 3 factores que mas pesan>],
  "would_raise": <que noticia subiria tu probabilidad>,
  "would_lower": <que noticia la bajaria>,
  "reasoning": <2-3 frases, en espanol>
}"""


@dataclass
class Analysis:
    probability: float
    confidence: str
    key_drivers: list[str]
    would_raise: str
    would_lower: str
    reasoning: str
    raw: dict


def _build_prompt(question: str, news: list[NewsItem]) -> str:
    lines = [f"PREGUNTA DEL MERCADO: {question}", "", "NOTICIAS MACRO RECIENTES:"]
    for n in news[:20]:
        when = n.published.strftime("%Y-%m-%d") if n.published else "s/f"
        lines.append(f"- [{when}] ({n.source}) {n.title}")
        if n.summary:
            lines.append(f"    {n.summary[:200]}")
    lines += [
        "",
        "Estima la probabilidad de que la respuesta sea SI (Yes).",
        "Se conservador: si las noticias no aportan senal clara, acercate",
        "a lo que ya diria el consenso, no inventes conviccion.",
    ]
    return "\n".join(lines)


def analyze(question: str, news: list[NewsItem]) -> Analysis | None:
    """Devuelve la estimacion, o None si no hay API key."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[analyzer] sin ANTHROPIC_API_KEY -> modo recogida, no analizo")
        return None

    try:
        import anthropic
    except ImportError:
        print("[analyzer] falta 'anthropic' -> pip install anthropic")
        return None

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=600,
        system=SYSTEM,
        messages=[{"role": "user", "content": _build_prompt(question, news)}],
    )

    text = "".join(block.text for block in resp.content if block.type == "text").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print(f"[analyzer] respuesta no-JSON, descarto:\n{text[:200]}")
        return None

    prob = float(data.get("probability", -1))
    if not 0 <= prob <= 1:
        print(f"[analyzer] probabilidad fuera de rango: {prob}")
        return None

    return Analysis(
        probability=prob,
        confidence=str(data.get("confidence", "low")),
        key_drivers=list(data.get("key_drivers", [])),
        would_raise=str(data.get("would_raise", "")),
        would_lower=str(data.get("would_lower", "")),
        reasoning=str(data.get("reasoning", "")),
        raw=data,
    )
