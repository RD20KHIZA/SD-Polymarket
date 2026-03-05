"""
Polymarket Scanner v2 — configuração global.
Parâmetros editáveis via sidebar do Streamlit.
"""

# ── thresholds ────────────────────────────────────────────────────────────────
MIN_SIGMA_THRESHOLD: float = 1.5   # fallback; sobrescrito por calibrate_min_sigma()
MIN_N_EVENTS: int          = 8     # N mínimo no bucket para ativar SD histórico
MIN_EDGE_PP: float         = 8.0   # edge mínimo em pp para gerar sinal
STRONG_EDGE_PP: float      = 12.0  # edge para sinal STRONG (ambos frameworks)

# ── modelo ────────────────────────────────────────────────────────────────────
ANNUAL_VOL: float     = 0.65   # vol anualizada BTC (atualizar mensalmente)
W_BARRIER: float      = 0.6    # peso do modelo de barreira no consenso
W_SD: float           = 0.4    # peso do SD histórico no consenso
KELLY_FRACTION: float = 0.5    # half-kelly

# ── Polymarket APIs ───────────────────────────────────────────────────────────
GAMMA_BASE: str = "https://gamma-api.polymarket.com"
CLOB_BASE:  str = "https://clob.polymarket.com"

# Fallback removido — todos os strikes vêm da API ao vivo (fetch_active_market).
# Se a API falhar, o dashboard exibe erro explícito.
