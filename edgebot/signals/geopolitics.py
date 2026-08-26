"""
Riesgo geopolitico. Gratis, por RSS.

Guerra, sanciones, elecciones, disrupciones de suministro -- todo esto
mueve petroleo, oro y en cascada la Fed. Se trata igual que las
noticias macro: se recoge y se etiqueta, no se interpreta aqui.
"""

from __future__ import annotations

from edgebot.signals.news import NewsItem, fetch_feed  # reuso deliberado

FEEDS: dict[str, str] = {
    "reuters_world": "https://www.reutersagency.com/feed/?taxonomy=best-regions&post_type=best",
    "bbc_world": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "ap_topnews": "https://apnews.com/hub/ap-top-news?output=rss",
}

KEYWORDS = (
    "war", "conflict", "sanctions", "invasion", "military", "ceasefire",
    "election", "coup", "opec", "oil supply", "trade war", "tariff",
    "china", "russia", "taiwan", "middle east", "iran", "supply chain",
)


def collect(only_relevant: bool = True) -> list[NewsItem]:
    seen: set[str] = set()
    out: list[NewsItem] = []
    for name, url in FEEDS.items():
        for item in fetch_feed(name, url):
            if item.uid in seen:
                continue
            blob = f"{item.title} {item.summary}".lower()
            if only_relevant and not any(k in blob for k in KEYWORDS):
                continue
            seen.add(item.uid)
            out.append(item)
    out.sort(key=lambda i: i.published or __import__("datetime").datetime.min, reverse=True)
    return out
