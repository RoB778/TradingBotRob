"""Pipeline completo: noticias -> analisis -> deteccion de value bet.

Este es el bucle central del bot. De momento en modo observacion:
detecta oportunidades y las registra en el ledger de paper trading.
No envia ordenes reales. Ese codigo no existe todavia, a proposito.
"""
from edgebot.markets.polymarket import PolymarketReader
from edgebot.signals.news import collect
from edgebot.signals.analyzer import analyze
from edgebot.engine.sizing import stake_for, RiskLimits
from edgebot.engine.paper import simulate_buy, PaperLedger
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parents[1] / ".env")

# Mercados Fed: los mas liquidos segun el scan. Rellena con las preguntas
# reales que te devolvio scan.py.
TARGETS = ["fed", "interest rate", "fomc"]


def main() -> None:
    lim = RiskLimits()
    print("Recogiendo noticias macro...")
    news = collect()
    print(f"  {len(news)} noticias relevantes\n")

    with PolymarketReader() as pm:
        markets = pm.list_markets(limit=200)
        fed_markets = [m for m in markets
                       if any(t in m.question.lower() for t in TARGETS)]
        print(f"{len(fed_markets)} mercados Fed encontrados\n")

        ledger = PaperLedger()

        for m in fed_markets[:5]:
            print(f"── {m.question[:70]}")
            analysis = analyze(m.question, news)
            if analysis is None:
                print("   (sin analisis: falta API key o error)\n")
                continue

            # Precio del outcome Yes
            yes_token = next((tid for tid, name in m.tokens.items()
                              if name.lower() == "yes"), None)
            if not yes_token:
                print("   sin token Yes\n"); continue

            book = pm.order_book(yes_token)
            if book.best_ask is None:
                print("   libro vacio\n"); continue

            price = book.best_ask
            stake, why = stake_for(analysis.probability, price, lim)
            print(f"   modelo: {analysis.probability:.2f} | mercado: {price:.2f} "
                  f"| conf: {analysis.confidence}")
            print(f"   {analysis.reasoning}")

            if stake > 0:
                fill = simulate_buy(book, stake)
                if fill:
                    tid = ledger.record(
                        condition_id=m.condition_id, token_id=yes_token,
                        question=m.question, model_prob=analysis.probability,
                        market_price=price, fill=fill,
                        rationale=analysis.raw)
                    print(f"   ✓ VALUE BET registrada (paper) #{tid}: {stake}€ | {why}")
            else:
                print(f"   sin apuesta: {why}")
            print()

        print("Stats acumulados:", ledger.stats())


if __name__ == "__main__":
    main()
