"""
Polymarket live quotes — What price will Bitcoin hit in [month]?
Busca via Gamma API + CLOB API (sem CLI, sem wallet).

Uso como biblioteca:
    from polymarket_live import fetch_active_market
    odds = fetch_active_market()   # auto-detecta slug do mês atual

Uso como script:
    python polymarket_live.py
"""

import sys
import json
from datetime import date, datetime, timezone

import requests

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE  = "https://clob.polymarket.com"
HEADERS    = {"Accept": "application/json", "User-Agent": "polymarket-research/1.0"}


# ── helpers internos ──────────────────────────────────────────────────────────

def _current_event_slug() -> str:
    """Gera o slug do evento para o mês corrente. Ex: what-price-will-bitcoin-hit-in-march-2026"""
    today = date.today()
    month = today.strftime("%B").lower()   # "march"
    year  = today.year                     # 2026
    return f"what-price-will-bitcoin-hit-in-{month}-{year}"


def _parse_price_level(question: str) -> int | None:
    """Extrai o nível de preço (em dólares) da pergunta do mercado."""
    for p in [150, 130, 120, 110, 105, 100, 95, 90, 85, 80, 75, 70,
              65, 60, 55, 50, 45, 40, 35, 30, 25, 20, 15, 10]:
        if (f"${p:,},000" in question or
                f"${p}," in question or
                f"${p * 1000}" in question or
                f"${p},000" in question):
            return p * 1_000
    return None


def get_event(slug: str) -> dict:
    r = requests.get(f"{GAMMA_BASE}/events/slug/{slug}", headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def get_midpoint(token_id: str) -> float | None:
    try:
        r = requests.get(
            f"{CLOB_BASE}/midpoints",
            params={"token_id": token_id},
            headers=HEADERS, timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        mid  = data.get("mid") or data.get("midpoint")
        return float(mid) if mid else None
    except Exception:
        return None


# ── função pública principal ──────────────────────────────────────────────────

def fetch_active_market(slug: str | None = None) -> dict:
    """
    Busca o mercado ativo do mês corrente (ou do slug fornecido) na Polymarket.

    Parâmetros
    ----------
    slug : str | None
        Slug do evento. None → auto-detecta para o mês atual.
        Ex: "what-price-will-bitcoin-hit-in-march-2026"

    Retorna
    -------
    dict  {strike (int): {
        "yes_mid"  : float,   # preço do YES token  (0–1)
        "no_mid"   : float,   # preço do NO token   (0–1)
        "direction": str,     # "reach" ou "dip"
        "token_id" : str,     # CLOB token_id do YES
        "bid"      : float | None,
        "ask"      : float | None,
        "question" : str,
        "source"   : "live",
    }}

    Raises
    ------
    RuntimeError
        Se a API falhar ou nenhum strike for parseável.
    """
    if slug is None:
        slug = _current_event_slug()

    try:
        event = get_event(slug)
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Gamma API retornou {exc.response.status_code} para slug '{slug}'. "
            f"Verifique se o mercado do mês existe na Polymarket."
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Falha ao buscar evento '{slug}': {exc}") from exc

    markets = event.get("markets", [])
    if not markets:
        raise RuntimeError(
            f"Nenhum mercado encontrado para slug '{slug}'. "
            f"O evento pode não existir ainda ou ter um nome diferente."
        )

    result: dict[int, dict] = {}
    for m in markets:
        if m.get("closed"):
            continue  # mercado já resolvido — não mostrar no scanner

        question = m.get("question") or m.get("title") or ""
        level    = _parse_price_level(question)
        if level is None:
            continue

        tokens = m.get("clobTokenIds") or []
        if isinstance(tokens, str):
            try:    tokens = json.loads(tokens)
            except: tokens = [tokens]

        yes_token = tokens[0] if tokens else None
        yes_mid   = get_midpoint(yes_token) if yes_token else None

        # fallback para lastTradePrice da Gamma se CLOB não responder
        if yes_mid is None:
            ltp     = m.get("lastTradePrice")
            yes_mid = float(ltp) if ltp else None

        if yes_mid is None:
            continue  # sem preço disponível — pula

        bid = float(m["bestBid"]) if m.get("bestBid") else None
        ask = float(m["bestAsk"]) if m.get("bestAsk") else None

        direction = "dip" if "dip" in question.lower() else "reach"

        result[level] = {
            "yes_mid"  : round(yes_mid, 4),
            "no_mid"   : round(1.0 - yes_mid, 4),
            "direction": direction,
            "token_id" : yes_token,
            "bid"      : bid,
            "ask"      : ask,
            "question" : question,
            "source"   : "live",
        }

    if not result:
        raise RuntimeError(
            f"Nenhum strike com preço disponível no evento '{slug}'. "
            f"CLOB pode estar indisponível e lastTradePrice ausente."
        )

    return result


# ── script standalone ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    slug = _current_event_slug()
    print("=" * 70)
    print(f"POLYMARKET LIVE — {slug}")
    print(f"Atualizado em: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 70)

    print(f"\nSlug detectado: {slug}")
    print("Buscando mercados...\n")

    try:
        odds = fetch_active_market(slug)
    except RuntimeError as e:
        print(f"ERRO: {e}")
        sys.exit(1)

    # buscar BTC spot para cálculo de distância
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": "BTCUSDT"}, timeout=5,
        )
        btc_price = float(r.json()["price"])
    except Exception:
        btc_price = None

    print(f"Strikes encontrados: {len(odds)}")
    if btc_price:
        print(f"BTC spot: ${btc_price:,.2f}\n")

    def _fmt(v):
        return f"{v*100:>5.1f}%" if v is not None else "  N/A"

    def _dist(strike):
        if btc_price is None: return ""
        return f"{(strike / btc_price - 1) * 100:>+.1f}%"

    print(f"  {'Strike':>12}  {'Dir':>6}  {'Bid':>6}  {'Mid':>6}  {'Ask':>6}  {'Dist':>8}  Pergunta")
    print("  " + "─" * 80)

    for strike in sorted(odds.keys(), reverse=True):
        m = odds[strike]
        print(
            f"  ${strike:>10,}  {m['direction']:>6}  "
            f"{_fmt(m['bid'])} {_fmt(m['yes_mid'])} {_fmt(m['ask'])}  "
            f"{_dist(strike):>8}  {m['question']}"
        )

    print(f"\nTotal: {len(odds)} strikes ao vivo.")
