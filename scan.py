"""Fase 0: mide la liquidez real de los mercados que te interesan.

Antes de construir un cerebro, comprueba que el cuerpo aguanta.
Si estos mercados no tienen profundidad para 6 EUR, el proyecto
cambia de forma.
"""
from edgebot.markets.polymarket import PolymarketReader
from edgebot.engine.sizing import RiskLimits

WATCH = ["bitcoin", "gold", "fed", "ethereum"]

def main() -> None:
    lim = RiskLimits()
    with PolymarketReader() as pm:
        if not pm.health():
            print("CLOB no responde")
            return
        markets = pm.list_markets(limit=200)
        hits = [m for m in markets if any(w in m.question.lower() for w in WATCH)]
        print(f"{len(hits)} mercados de interes\n")

        for m in hits[:15]:
            mins = m.minutes_to_close
            print(f"{m.question[:70]}")
            print(f"  vol24h ${m.volume_24h:,.0f} | cierra en {mins:.0f} min" if mins else
                  f"  vol24h ${m.volume_24h:,.0f}")
            for tid, name in m.tokens.items():
                try:
                    book = pm.order_book(tid)
                except Exception as e:
                    print(f"  {name}: sin libro ({e})")
                    continue
                if book.best_ask is None:
                    print(f"  {name}: libro vacio")
                    continue
                # cuanto puedo comprar sin mover el precio mas de 2 puntos
                depth = book.depth_within(book.best_ask + 0.02)
                usd = depth * book.best_ask
                flag = "" if usd >= lim.max_pct_per_trade * lim.bankroll else "  <-- DEMASIADO FINO"
                print(f"  {name}: bid {book.best_bid:.2f} ask {book.best_ask:.2f} "
                      f"spread {book.spread:.3f} | ~${usd:,.0f} sin mover 2pts{flag}")
            print()

if __name__ == "__main__":
    main()
