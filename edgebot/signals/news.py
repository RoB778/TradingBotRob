"""
Recogida de noticias macro. Gratis, por RSS.

Nada de Twitter API de pago aqui. Los feeds RSS de medios financieros y
de la propia Fed son publicos y tienen menos ruido de bots que el
timeline de X. Para leer la Fed, lo mejor es la Fed.

Esta capa SOLO recoge y normaliza. No interpreta. La interpretacion
(que significa esto para los tipos) vive en el modulo de analisis, que
es donde entra Claude. Separar recogida de interpretacion permite
cachear las noticias y no pagar por analizar dos veces lo mismo.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import feedparser

# Feeds centrados en lo que mueve a la Fed: inflacion, empleo, decisiones
# de tipos y las propias notas de prensa del FOMC. Todos publicos.
FEEDS: dict[str, str] = {
    "fed_press": "https://www.federalreserve.gov/feeds/press_all.xml",
    "fed_monetary": "https://www.federalreserve.gov/feeds/press_monetary.xml",
    "reuters_markets": "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best",
    "cnbc_economy": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "cnbc_finance": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
    "marketwatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
}

# Solo nos interesan noticias que rocen la politica monetaria. Filtrar
# aqui, en crudo, ahorra llamadas al analizador (= dinero).
KEYWORDS = (
    "fed", "fomc", "powell", "interest rate", "rate cut", "rate hike",
    "inflation", "cpi", "pce", "jobs report", "unemployment", "payroll",
    "monetary policy", "basis points", "treasury", "yield",
)


@dataclass
class NewsItem:
    source: str
    title: str
    summary: str
    link: str
    published: datetime | None
    fetched_at: float = field(default_factory=time.time)

    @property
    def uid(self) -> str:
        """Huella estable para deduplicar y cachear."""
        return hashlib.sha1(f"{self.source}|{self.title}".encode()).hexdigest()[:16]

    @property
    def is_relevant(self) -> bool:
        blob = f"{self.title} {self.summary}".lower()
        return any(k in blob for k in KEYWORDS)


def _parse_entry_date(entry: object) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            return datetime(*val[:6], tzinfo=timezone.utc)
    return None


def fetch_feed(name: str, url: str) -> list[NewsItem]:
    """Un feed. Tolerante a fallos: si un feed cae, no tumba el resto."""
    try:
        parsed = feedparser.parse(url)
    except Exception:
        return []

    items: list[NewsItem] = []
    for entry in parsed.entries:
        items.append(
            NewsItem(
                source=name,
                title=getattr(entry, "title", "").strip(),
                summary=getattr(entry, "summary", "").strip()[:500],
                link=getattr(entry, "link", ""),
                published=_parse_entry_date(entry),
            )
        )
    return items


def collect(only_relevant: bool = True) -> list[NewsItem]:
    """Recorre todos los feeds, deduplica y ordena por fecha."""
    seen: set[str] = set()
    out: list[NewsItem] = []

    for name, url in FEEDS.items():
        for item in fetch_feed(name, url):
            if item.uid in seen:
                continue
            if only_relevant and not item.is_relevant:
                continue
            seen.add(item.uid)
            out.append(item)

    out.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return out


if __name__ == "__main__":
    news = collect()
    print(f"{len(news)} noticias macro relevantes\n")
    for n in news[:15]:
        when = n.published.strftime("%m-%d %H:%M") if n.published else "??"
        print(f"[{when}] ({n.source}) {n.title[:80]}")
