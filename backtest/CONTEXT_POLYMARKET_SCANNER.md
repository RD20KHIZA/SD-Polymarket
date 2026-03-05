# Monthly Volatility Zones Dashboard — Contexto Completo

**Projeto:** `monthly-volatility-zones-indicator/backtest/`
**Data:** 2026-03-05
**Estado:** Implementação completa, validada end-to-end.

---

## Como rodar

```bash
cd "C:\Users\Rafael\claude teste\monthly-volatility-zones-indicator\backtest"
python -m streamlit run app.py
```

---

## Arquivos do projeto

```
backtest/
├── app.py                        # Streamlit app principal
├── tab_polymarket_scanner.py     # Tab Polymarket Scanner (render)
├── polymarket_scanner.py         # Lógica: barreira, kelly, get_scanner_data
├── polymarket_live.py            # Fetch ao vivo: fetch_active_market()
├── scanner_config.py             # Constantes e pesos do modelo
├── data_fetcher.py               # Fetch OHLCV (KuCoin via vectorbt/ccxt)
├── event_study.py                # detect_zone_touches, compute_forward_returns, summarize_events
├── visualization.py              # Plots Plotly (tema dark TradingView)
├── zone_calculator.py            # compute_zones, ZONE_SIGMAS
└── vbt_backtest.py               # VectorBT portfolio simulation (opcional)

../data/                          # Cache Parquet de OHLCV (criado automaticamente)
```

---

## Estrutura do app.py — ordem crítica

```python
# 1. run handler ANTES de st.tabs() — garante dados no scanner no mesmo ciclo
if run:
    study, df_zones = load_and_compute(symbol, since, lookback, max_k)
    summary = summarize_events(study, max_k=max_k)
    st.session_state.update({
        "study": study, "df_zones": df_zones, "symbol": symbol,
        "max_k": max_k, "sigmas": sigmas_selected, "since": since,
        "summary": summary,
    })

# 2. Extrair dados ANTES de criar tabs
_df_hitrate = st.session_state.get("summary")   # None até o estudo rodar
_df_events  = st.session_state.get("study")

# 3. Criar tabs
_main_tab, _scanner_tab = st.tabs(["📈 Vol Zone Study", "🎯 Polymarket Scanner"])

# 4. Scanner tab (sem st.stop() — sempre renderiza)
with _scanner_tab:
    render_polymarket_scanner_tab(df_hitrate=_df_hitrate, df_returns=_df_hitrate, df_events=_df_events)

# 5. Main tab (tem st.stop() se estudo não rodou)
with _main_tab:
    if "study" not in st.session_state:
        st.info("...")
        st.stop()
    # conteúdo do Vol Zone Study...
```

**Por que essa ordem importa:** se o run handler estiver dentro de `with _main_tab:`, o scanner recebe `df_hitrate=None` no mesmo ciclo de render em que o estudo é rodado.

---

## Sidebar (app.py)

| Controle | Tipo | Default |
|---|---|---|
| Symbol | selectbox | BTC/USDT |
| Custom symbol | text_input | — |
| From (YYYY-MM-DD) | text_input | 2020-01-01 |
| Vol Lookback (days) | slider | 360 |
| Max Holding Period (4H bars) | slider | 120 |
| Zone levels (σ) | multiselect | todos |
| ▶ Run Study | button | — |

---

## Tab 1 — Vol Zone Study

### Sub-tabs

| Tab | Conteúdo |
|---|---|
| Price Chart | Candlestick 4H + zonas sobrepostas + marcadores de toque |
| Return Curves | Média ± 1σ do forward return vs k (supply \| demand) |
| Hit Rate | Fração favorável vs k (supply \| demand) |
| Sharpe vs k | Sharpe per-trade vs k (supply \| demand) |
| Distribution | Violin plot dos retornos em k escolhido |
| Full Report | Grid 4×2 com todos os painéis |
| Data | Tabela resumo + raw events + download CSV |
| VectorBT Sweep | (opcional) Sweep de parâmetros com portfólio real |

### Métricas exibidas no topo
- Total events, Supply touch events, Demand touch events, Date range

---

## zone_calculator.py

### Fórmula das zonas (replica o indicador Pine Script)
```python
src         = (high + low + close + close) / 4   # hlcc4
log_ret     = log(src / src.shift(1))
daily_vol   = rolling_std(log_ret, lookback=360) * sqrt(365)
monthly_vol = daily_vol / sqrt(12)
zone        = monthly_open * (1 ± n_sigma * monthly_vol)
```

### ZONE_SIGMAS
```python
ZONE_SIGMAS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75, 4.0]
```

### Colunas adicionadas ao df_4h por compute_zones()
- `monthly_open` — open do primeiro bar do mês
- `monthly_vol` — vol mensal vigente no mês
- `supply_{n}sd` e `demand_{n}sd` para cada sigma em ZONE_SIGMAS
  - Formato: `supply_1_0sd`, `demand_0_5sd` (pontos → underscores)

### Funções
```python
compute_monthly_vol(daily_df, lookback=360) -> pd.Series
compute_zones(df_4h, daily_df, lookback=360) -> pd.DataFrame
zone_summary(df_zones) -> pd.DataFrame   # resumo mensal
```

---

## data_fetcher.py

### Funções
```python
fetch_crypto_ohlcv(symbol, timeframe="4h", since="2020-01-01", exchange="binance", force_refresh=False) -> pd.DataFrame
resample_to_daily(df) -> pd.DataFrame
```

### Cache
- Salva Parquet em `../data/{symbol}_{timeframe}_{since}.parquet`
- Incremental: só busca barras novas desde o último timestamp cacheado
- Exchange padrão: KuCoin (vectorbt CCXTData)

### Output
- DataFrame indexado por UTC timestamp
- Colunas: `open, high, low, close, volume`

---

## event_study.py

### detect_zone_touches()
```python
detect_zone_touches(df_zones) -> pd.DataFrame
```
- Supply: `bar.high >= zone_level`
- Demand: `bar.low <= zone_level`
- Apenas o **primeiro toque por zona por mês** é registrado
- Retorna colunas: `timestamp, month, sigma, direction, zone_level, monthly_open, monthly_vol, bar_open, bar_high, bar_low, bar_close`

### compute_forward_returns()
```python
compute_forward_returns(df_zones, events, max_k=120) -> pd.DataFrame
```
- Adiciona colunas `fwd_1 … fwd_{max_k}` (log returns)
- `fwd_k = log(close[t+k] / close[t])`
- Entrada simulada no close do bar de toque

### summarize_events()
```python
summarize_events(study, max_k=120) -> pd.DataFrame
```
Retorna long-form DataFrame — é o `df_hitrate` usado pelo scanner.

Colunas: `direction, sigma, k, n_events, mean_ret, median_ret, std_ret, mean_signed, hit_rate, sharpe`

Hit rate:
- supply: `hit_rate = fração onde fwd_k < 0`
- demand: `hit_rate = fração onde fwd_k > 0`

Sharpe: `mean(signed_ret) / std(signed_ret)`

---

## visualization.py

### Tema
- TradingView dark: `plot_bgcolor="#131722"`, `paper_bgcolor="#131722"`
- Paleta supply: Oranges (0.25–0.72), demand: Blues (0.25–0.72)
- `SUPPLY_COLOR` e `DEMAND_COLOR` exportados (usados em app.py VectorBT)

### Funções públicas
```python
plot_price_zones(df_zones, study_df=None, symbol, sigmas=None, show_touches=True) -> go.Figure
plot_return_curve(study_df, direction, sigmas=None, title_suffix="") -> go.Figure
plot_hit_rate(study_df, direction, sigmas=None) -> go.Figure
plot_sharpe_vs_k(study_df, direction, sigmas=None) -> go.Figure
plot_distribution(study_df, direction, k=18, sigmas=None) -> go.Figure
full_report(study_df, symbol) -> go.Figure   # grid 4×2, height=1400
_hex_to_rgba(color, alpha) -> str            # helper exportado
_color(sigma, direction) -> str              # cor canônica por sigma/direção
```

### Helpers internos usados no app.py
- `_hex_to_rgba`, `_color` — importados explicitamente

---

## vbt_backtest.py (opcional)

Importado com `try/except` — app não quebra se vectorbt não estiver instalado.

```python
run_single(df, events, sigma, direction, hold_k, init_cash=10000, tc=0.001) -> vbt.Portfolio
sweep_params(df, events, hold_k_values, sigmas, tc=0.001) -> pd.DataFrame
plot_equity(pf, sigma, direction, hold_k, symbol)  # matplotlib (standalone)
```

### Diferença vs event_study
- Event study: captura **todos** os toques, independente de overlap
- VectorBT: `accumulate=False` — se dois toques ocorrem dentro de `hold_k` bars, o segundo é **ignorado**

### Tab VectorBT Sweep no app.py
- Parâmetros: TC, holding periods, zone levels
- Saída: tabela sweep (sortável por Sharpe) + gráfico de equity curve selecionável
- Equity chart usa log-scale + subplot drawdown

---

## Tab 2 — Polymarket Scanner

### Arquivos
- `scanner_config.py` — constantes
- `polymarket_live.py` — fetch API ao vivo
- `polymarket_scanner.py` — modelo matemático
- `tab_polymarket_scanner.py` — render Streamlit

### scanner_config.py
```python
MIN_SIGMA_THRESHOLD = 1.5   # fallback; calibrate_min_sigma() sobrescreve
MIN_N_EVENTS        = 8     # N mínimo no bucket para ativar SD histórico
MIN_EDGE_PP         = 8.0   # edge mínimo em pp para gerar sinal
STRONG_EDGE_PP      = 12.0  # edge para sinal STRONG
ANNUAL_VOL          = 0.65  # vol anualizada BTC (fallback)
W_BARRIER           = 0.6   # peso barreira no consenso
W_SD                = 0.4   # peso SD histórico (base; adaptativo no Sprint 2)
KELLY_FRACTION      = 0.5   # half-kelly
# Sprint 1
EWMA_HALFLIFE_DAYS  = 30    # halflife EWMA realized vol
MAX_SPREAD_CENTS    = 5.0   # flag illiquid if spread > this
WILSON_Z            = 1.96  # z-score Wilson CI (95%)
# Sprint 2
DRIFT_HALFLIFE_DAYS = 90    # halflife EWMA drift estimation
DRIFT_SHRINKAGE     = 0.5   # shrink drift 50% toward zero
CALIBRATION_ALPHA   = 0.05  # significance level binomial test
# APIs
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE  = "https://clob.polymarket.com"
```

### polymarket_live.py — API dinâmica

```python
fetch_active_market(slug: str | None = None) -> dict[int, dict]
```
- `slug=None` → auto: `f"what-price-will-bitcoin-hit-in-{month}-{year}"`
- Gamma API (`/events/slug/{slug}`) + CLOB API (`/midpoints?token_id=...`)
- Fallback para `lastTradePrice` se CLOB retornar None
- **Levanta `RuntimeError`** se falhar — sem fallback silencioso

**Retorno:**
```python
{
  85000: {
    "yes_mid": 0.42,   # 0–1
    "no_mid":  0.58,
    "direction": "reach",   # ou "dip"
    "token_id": "...",
    "bid": 0.41, "ask": 0.43,
    "question": "Will Bitcoin hit $85,000 in March 2026?",
    "source": "live",
  }, ...
}
```

Validado: março 2026 → 20 strikes ($20k–$150k) ao vivo.

### polymarket_scanner.py — modelo

```python
fetch_btc_price() -> float                  # Binance REST
fetch_realized_vol(halflife=30, lookback=120) -> float  # EWMA ann vol (Binance daily)
fetch_deribit_iv() -> float                 # Deribit DVOL (30d implied vol)
estimate_drift(halflife=90, shrinkage=0.5, lookback=120) -> float  # EWMA drift ann
wilson_interval(hits, n, z=1.96) -> (center, lower, upper)  # Wilson score CI
barrier_prob(strike, current, annual_vol, days, drift=0.0) -> float  # GBM+drift
current_sigma(btc_price, monthly_open, annual_vol) -> float
get_regime(btc_price, monthly_open) -> str  # "above_open"|"below_open"|"neutral"
calibrate_min_sigma(df_hitrate, ...) -> float  # binomial test + fallback heuristic
get_p_sd(sigma, dir, df_hitrate, k, min_n) -> (p_wilson, n, ci_lo, ci_hi)  # 4-tuple
kelly(p_win, cost, kelly_fraction) -> float
get_scanner_data(barrier_vol, zone_vol, drift, ...) -> pd.DataFrame
decay_table(strike, btc, barrier_vol, days, drift=0.0, step=6) -> pd.DataFrame
```

**current_sigma() — distância ao monthly_open em σ mensais:**
```python
monthly_vol = annual_vol / sqrt(12)
sigma_atual = |log(btc_price / monthly_open)| / monthly_vol
```

**get_regime() — thresholds exatos:**
```python
if btc_price > monthly_open * 1.001:  → "above_open"
if btc_price < monthly_open * 0.999:  → "below_open"
else:                                  → "neutral"
```

**Regime → direction no df_hitrate (get_scanner_data):**
```
above_open → "supply"
below_open → "demand"
neutral    → "demand"  (default)
```

**Barreira GBM com drift (Shreve Ch.7):**
```
T = days / 365
σ = barrier_vol × √T
b = |ln(strike / S)|
m = drift − 0.5 × barrier_vol²     # log-space drift

Upper barrier (strike > S):
  d1 = (−b + m×T) / σ
  d2 = (−b − m×T) / σ
  P  = Φ(d1) + exp(2×m×b / barrier_vol²) × Φ(d2)

Lower barrier (strike < S):
  flip drift sign (m → −m), same formula

drift = 0 → colapsa para 2×Φ(−b/σ)  (modelo original sem drift)
```

**estimate_drift() — EWMA drift com shrinkage:**
```python
# Busca 120 klines diárias Binance, computa EWMA mean de log-returns
# halflife = DRIFT_HALFLIFE_DAYS (90d)
# mu_annual = ewma_mean * 365
# return mu_annual * DRIFT_SHRINKAGE (0.5)   # shrink 50% toward zero
```

**calibrate_min_sigma() — algoritmo (Sprint 2: binomial test):**
```python
# Primary: binomial exact test (scipy.stats.binomtest)
# Para cada sigma (crescente), acumula hits e n_events
# Se binomtest(total_hits, total_n, 0.5).pvalue < CALIBRATION_ALPHA (0.05):
#   → retorna esse sigma como threshold
#
# Fallback: heurística original 5pp (baseline + divergência)
# Se nenhum teste rejeita: retorna MIN_SIGMA_THRESHOLD (1.5)
```

**get_p_sd() — interpolação 1D em sigma (Sprint 3):**
```python
# 1. Encontra sigma_lo e sigma_hi que encaixam sigma_atual
#    Clamp se fora dos limites do grid

# 2. Lookup (hit_rate, N) em cada nó via _lookup_node()
#    k usa nearest-neighbor (espaçamento 1 bar, erro desprezível)

# 3. Se ambos nós válidos (N >= min_n_events):
#    t = (sigma_q - sigma_lo) / (sigma_hi - sigma_lo)
#    center_interp = (1-t) × wilson_center_lo + t × wilson_center_hi
#    N_eff = média harmônica ponderada: 1 / (w_lo/N_lo + w_hi/N_hi)
#    CI recomputado via wilson_interval(center_interp × N_eff, N_eff)

# 4. Se apenas 1 nó válido: fallback nearest-neighbor (usa o nó disponível)
# 5. Se nenhum nó válido: retorna (None,)*4
```

**Consenso ponderado (Sprint 2: pesos adaptativos):**
```
# Pesos base: W_BARRIER=0.6, W_SD=0.4
# Sprint 2: w_sd escala com qualidade dos dados SD

confidence_n = 1 − 1/(1 + N/25)          # 0→0, 25→0.5, 100→0.8
precision    = clamp((0.70 − ci_width) / 0.40, 0, 1)   # CI estreito → confiável
w_sd_eff     = W_SD × confidence_n × precision

# Resultado prático:
# N=4  → w_sd ≈ 0.6%    (quase todo barreira)
# N=8  → w_sd ≈ 3.5%
# N=20 → w_sd ≈ 14.5%
# N=50 → w_sd ≈ 26.7%
# N=100→ w_sd ≈ 32.0%   (nunca chega em 40%)

w_barrier_eff = 1 − w_sd_eff
p_internal = w_barrier_eff × p_barrier + w_sd_eff × p_sd
```

**Edge e sinal:**
```
edge_pp = (p_internal - poly_yes) × 100
edge_pp > min_edge  → BUY YES (cost=poly_yes, gain=1-poly_yes, p_win=p_internal)
edge_pp < -min_edge → BUY NO  (cost=poly_no,  gain=poly_yes,   p_win=1-p_internal)
else                → MONITOR
```

**signal_strength — lógica completa:**
```python
if signal == "MONITOR":
    signal_strength = "— MONITOR"
elif p_sd is not None:
    barrier_dir = "YES" if p_barr > poly_yes else "NO"
    sd_dir      = "YES" if p_sd   > poly_yes else "NO"
    if barrier_dir == sd_dir and abs(edge_pp) >= strong_edge:   # ambos concordam + edge forte
        signal_strength = "★★ STRONG"
    elif barrier_dir != sd_dir:                                  # modelos divergem
        signal_strength = "⚠ CONFLICTING"
    else:
        signal_strength = "★ MODERATE"
else:
    signal_strength = "★ MODERATE"   # só barreira disponível
```

**EV e Kelly:**
```
ev_¢ = (trade_prob × (1-cost) − (1-trade_prob) × cost) × 100
b    = (1-cost) / cost
kelly = max(0, (p×b − q) / b) × 0.5      # half-kelly
```

**_price_to_activate_sd() — preços para ativar SD:**
```python
monthly_vol  = annual_vol / sqrt(12)
demand_price = monthly_open * exp(−threshold × monthly_vol)
supply_price = monthly_open * exp(+threshold × monthly_vol)
```

**dist_pct (distância do strike ao spot):**
```python
dist_pct = (strike / btc_price - 1) * 100   # % positivo = acima do spot
```

**summarize_events() — signed_ret:**
```python
sign = -1 if direction == "supply" else +1   # supply: queda é lucro
signed = sign * fwd_k
hit_rate = mean(signed > 0)
sharpe   = mean(signed) / std(signed)
```

**Bug corrigido (truthiness):**
```python
# ERRADO — falha silenciosamente se valor for 0.0
if (trade_prob and cost):
# CORRETO
_has_trade = trade_prob is not None and cost is not None
```

### Colunas do DataFrame retornado por get_scanner_data()
`strike, direction, dist_pct, poly_yes, poly_no, p_barrier, p_sd, n_sd, p_internal, edge_pp, signal, signal_strength, kelly_pct, cost_¢, gain_¢, ev_¢, consensus_source, sd_active, sigma_atual, regime, source, spread_¢, ci_width`

### tab_polymarket_scanner.py — sidebar

```python
monthly_open     = st.number_input("Monthly open ($)", value=66_973.0)
barrier_vol      = st.number_input("Barrier vol (IV)", value=deribit_iv)    # Deribit DVOL
zone_vol         = st.number_input("Zone vol (realized)", value=ewma_rv)   # EWMA realized
drift            = st.number_input("Drift (annualized)", value=est_drift)  # EWMA drift
days_remaining   = st.number_input("Dias restantes no mês", ...)
slug_override    = st.text_input("Slug override (vazio = auto)")
min_edge         = st.slider("Edge mínimo (pp)", 4, 20, 8)
w_barrier        = st.slider("Peso barreira", 0.3, 1.0, 0.6)
w_sd             = round(1.0 - w_barrier, 2)
min_sigma_override = st.slider("Min σ para SD ativo", 0.0, 3.0, 0.0)
# Botão "Refresh all" limpa caches de vol, drift, odds
```

### Dois valores de threshold (distintos)
- `min_sigma_calibrated` = `calibrate_min_sigma(df_hitrate)` → referência informacional no rodapé
- `effective_threshold = min_sigma_override` → controla `sd_active` e texto dos avisos

### Cache e refresh
```python
@st.cache_data(ttl=300)
def _fetch_market_data(slug_override, refresh_key):
    ...
# Botão "🔄 Atualizar odds":
_fetch_market_data.clear()
st.session_state["scanner_refresh"] += 1
st.rerun()
```

### Tabela de strikes — colunas exibidas

| Coluna interna | Exibido como | Cor |
|---|---|---|
| signal | Ação | BUY YES=azul, BUY NO=roxo, MONITOR=cinza |
| signal_strength | Força | STRONG=verde escuro, MODERATE=verde, CONFLICTING=laranja |
| edge_pp | Edge pp | >12=verde escuro, >8=verde, >4=laranja, <-8=vermelho |
| p_sd + n_sd | SD % (N) | combinadas em uma coluna |

### Componentes visuais da tab
1. **KPIs** — BTC spot, σ atual, dias restantes, sinais ativos
2. **Tabela de strikes** — styled DataFrame
3. **Contexto do Modelo** (expander) — parâmetros + bucket SD ativo ou aviso de inativo
4. **Scatter histórico** — eventos do bucket ativo (só se SD ativo + estudo rodado)
5. **Decaimento temporal** — tabela P(toque) por dia para sinais STRONG
6. **Rodapé** — fonte, modelo, N eventos, timestamp

---

## Fluxo de dados completo

```
KuCoin API
    ↓
fetch_crypto_ohlcv()           → df_4h (cache Parquet)
    ↓
resample_to_daily()            → daily_df
    ↓
compute_zones()                → df_zones (+ colunas supply/demand por sigma)
    ↓
detect_zone_touches()          → events (primeiro toque por zona por mês)
    ↓
compute_forward_returns()      → study (events + colunas fwd_1…fwd_k)
    ↓
summarize_events()             → summary / df_hitrate (direction, sigma, k, hit_rate, sharpe, n)
    ↓
st.session_state["summary"]   → render_polymarket_scanner_tab(df_hitrate=...)
    ↓
get_scanner_data()             → df com edge_pp, signal, kelly, ev por strike
    ↓
Tabela Streamlit styled
```

---

## Dependências principais

```
streamlit
vectorbt          # fetch OHLCV + VBT (pip install vectorbt)
pandas, numpy
plotly
scipy             # scipy.stats.norm + binomtest (modelo barreira + calibração)
requests          # Polymarket API + Binance + Deribit
pyarrow           # Parquet cache
```

---

## Estado atual (2026-03-05)

- [x] Vol Zone Study tab completo (Price Chart, Return Curves, Hit Rate, Sharpe, Distribution, Full Report, Data, VectorBT)
- [x] Polymarket Scanner v2 com df_hitrate do Vol Zone Study
- [x] calibrate_min_sigma() empírico
- [x] BUY YES vs BUY NO separados com mecânica correta
- [x] Dynamic strikes via fetch_active_market() — sem FALLBACK_ODDS
- [x] Hard error se API falhar (sem fallback silencioso)
- [x] app.py ordering fix (run handler antes de st.tabs)
- [x] Validação end-to-end: 20 strikes ao vivo, scanner 20 linhas

### Sprint 1 — Otimizações do modelo (2026-03-05)

- [x] **Vol dinâmica (EWMA)**: `fetch_realized_vol()` busca 120 klines diárias Binance, computa EWMA ann vol (halflife 30d). Substitui `ANNUAL_VOL=0.65` como default do slider. Cache 10min no Streamlit.
- [x] **Wilson CI no SD**: `wilson_interval()` → `get_p_sd()` retorna Wilson center (shrunk toward 50% para small N) + CI bounds. N=4 com 75% → 62.8%. CI width reportado na tabela como métrica de confiança.
- [x] **Bid-ask spread**: Kelly e EV usam preço de execução (ask para BUY YES, 1-bid para BUY NO) em vez de midpoint. Coluna `Spread ¢` na tabela. Edge detection mantém midpoint.

### Sprint 2 — Modelo robusto (2026-03-05)

- [x] **Drift no barrier model**: `barrier_prob()` reescrita com GBM+drift (Shreve Ch.7). `estimate_drift()` usa EWMA 90d com 50% shrinkage toward zero. Drift negativo → P(touch) sobe para downside, desce para upside.
- [x] **Pesos adaptativos no consenso**: `w_sd_eff = W_SD × confidence_n × precision`. confidence_n satura com N (via 1-1/(1+N/25)), precision penaliza CI largo. N=4→0.6%, N=50→26.7%. Barreira domina quando dados SD são fracos.
- [x] **Binomial test na calibração**: `calibrate_min_sigma()` usa `scipy.stats.binomtest` como teste primário (α=0.05). Fallback para heurística 5pp se scipy falhar ou nenhum sigma rejeitar H0.
- [x] **Separação vol inputs**: Barrier vol (Deribit DVOL, forward-looking) vs Zone vol (EWMA realized). Dois inputs independentes na sidebar + "Refresh all" button.

### Sprint 3 — Refinamento (2026-03-05)

- [x] **Interpolação 1D em sigma**: `get_p_sd()` interpola Wilson centers entre os dois sigmas adjacentes do grid. N_eff via média harmônica ponderada. CI recomputado. Fallback nearest-neighbor se um nó não tem dados. k mantém nearest-neighbor (espaçamento 1 bar).
- [x] **Remoção do slider Barrier weight**: pesos adaptativos (Sprint 2) tornam o slider redundante. Usa `cfg.W_BARRIER/W_SD` como base fixa.
- [x] **Vol inputs read-only com timestamps**: barrier_vol, zone_vol, drift auto-fetched e read-only. Cada valor mostra fonte + horário UTC de fetch.

Propostas revisadas por quant-analyst + quant-dev e descartadas:
- **Temporal weighting**: DEFERIDO — N por bucket (8-30) muito baixo; decay exponencial destruiria N_eff. Wilson CI já trata confiança.
- **Intra-month decay**: DROPADO — GBM é Markov; P(touch) já condiciona em (spot, T_restante). DVOL já captura vol forward.
- **Strike correlation**: DROPADO — modelo já é monotônico (p_barrier monotônico, p_sd constante para todos strikes).

### Próximos (Sprint 4 — não solicitado)

- [ ] Per-strike sigma lookup (sigma_strike em vez de sigma_spot para SD)
- [ ] Vol term structure (IV tenor-matched da Deribit em vez de DVOL 30d fixo)
