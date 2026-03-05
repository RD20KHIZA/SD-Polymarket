# Monthly Volatility Zones Dashboard — Contexto Completo

**Projeto:** `monthly-volatility-zones-indicator/backtest/`
**Data:** 2026-03-04
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
ANNUAL_VOL          = 0.65  # vol anualizada BTC
W_BARRIER           = 0.6   # peso barreira no consenso
W_SD                = 0.4   # peso SD histórico
KELLY_FRACTION      = 0.5   # half-kelly
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE  = "https://clob.polymarket.com"
# SEM FALLBACK_ODDS — strikes 100% da API
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
barrier_prob(strike, current, annual_vol, days) -> float   # P(ever touch)
current_sigma(btc_price, monthly_open, annual_vol) -> float
get_regime(btc_price, monthly_open) -> str  # "above_open"|"below_open"|"neutral"
calibrate_min_sigma(df_hitrate, min_n_events=8, min_hit_rate_diff=0.05) -> float
get_p_sd(sigma_atual, direction, df_hitrate, k_target, min_n_events) -> (float|None, int|None)
kelly(p_win, cost, kelly_fraction) -> float
get_scanner_data(...) -> pd.DataFrame
decay_table(strike, btc_price, annual_vol, days_remaining, step_days=6) -> pd.DataFrame
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

**Barreira log-normal (sem drift):**
```
T = days / 365
P(toque) = 2 × Φ(−|ln(strike/S)| / (σ_anual × √T))
```

**calibrate_min_sigma() — algoritmo completo:**
```python
# baseline = hit_rate médio dos buckets com sigma <= 0.75
low_sigma = df_hitrate[df_hitrate["sigma"] <= 0.75]
baseline  = low_sigma["hit_rate"].mean()   # ≈ 0.5 = ruído

# threshold = menor sigma com divergência significativa do baseline
significant = df_hitrate[
    (df_hitrate["n_events"] >= min_n_events) &         # N >= 8
    (abs(df_hitrate["hit_rate"] - baseline) >= 0.05)   # diverge ≥ 5pp
]
return significant["sigma"].min()   # ou fallback MIN_SIGMA_THRESHOLD=1.5
```

**get_p_sd() — algoritmo completo:**
```python
# 1. Encontra sigma mais próximo do atual no df_hitrate
closest_sigma = min(available_sigmas, key=lambda s: abs(s - sigma_atual))

# 2. Filtra por sigma + direction
sub = df_hitrate[(df_hitrate["sigma"] == closest_sigma) &
                 (df_hitrate["direction"] == direction)]

# 3. Encontra k mais próximo do k_target = days_remaining * 6
k_used = min(available_ks, key=lambda k: abs(k - k_target))

# 4. Retorna hit_rate e n_events (ou None se N < min_n_events)
row = sub[sub["k"] == k_used]
n = int(row["n_events"])
if n < min_n_events: return None, None
return float(row["hit_rate"]), n
```

**Consenso ponderado:**
```
p_internal = 0.6 × p_barrier + 0.4 × p_sd   (se SD ativo e N >= 8)
p_internal = p_barrier                         (se SD inativo ou N insuficiente)
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
`strike, direction, dist_pct, poly_yes, poly_no, p_barrier, p_sd, n_sd, p_internal, edge_pp, signal, signal_strength, kelly_pct, cost_¢, gain_¢, ev_¢, consensus_source, sd_active, sigma_atual, regime, source`

### tab_polymarket_scanner.py — sidebar

```python
monthly_open     = st.number_input("Monthly open ($)", value=66_973.0)
annual_vol       = st.slider("Vol anualizada BTC", 0.30, 1.20, 0.65)
days_remaining   = st.number_input("Dias restantes no mês", ...)
slug_override    = st.text_input("Slug override (vazio = auto)")
event_slug       = slug_override.strip() or None   # None = auto-detect
min_edge         = st.slider("Edge mínimo (pp)", 4, 20, 8)
w_barrier        = st.slider("Peso barreira", 0.3, 1.0, 0.6)
w_sd             = round(1.0 - w_barrier, 2)
min_sigma_override = st.slider("Min σ para SD ativo", 0.0, 3.0, 0.0)
# 0.0 = SD sempre ativo; sobrescreve o threshold calibrado
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
scipy             # scipy.stats.norm (modelo barreira)
requests          # Polymarket API + Binance
pyarrow           # Parquet cache
```

---

## Estado atual (2026-03-04)

- [x] Vol Zone Study tab completo (Price Chart, Return Curves, Hit Rate, Sharpe, Distribution, Full Report, Data, VectorBT)
- [x] Polymarket Scanner v2 com df_hitrate do Vol Zone Study
- [x] calibrate_min_sigma() empírico
- [x] BUY YES vs BUY NO separados com mecânica correta
- [x] Dynamic strikes via fetch_active_market() — sem FALLBACK_ODDS
- [x] Hard error se API falhar (sem fallback silencioso)
- [x] app.py ordering fix (run handler antes de st.tabs)
- [x] Validação end-to-end: 20 strikes ao vivo, scanner 20 linhas

**Nenhuma tarefa pendente.**
