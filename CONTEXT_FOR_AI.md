# Contexto da Análise — BTC Monthly Volatility Zones + Polymarket
*Documento gerado para continuidade da análise em outro assistente de IA.*
*Data de referência: 3 março 2026*

---

## 1. O Indicador

**Monthly Volatility Zones Indicator** — localizado em `monthly-volatility-zones-indicator/backtest/`.

Calcula zonas de suporte e resistência mensais usando:
```
hlcc4 = (High + Low + Close + Close) / 4
daily_ret = log(hlcc4_t / hlcc4_{t-1})
monthly_vol = rolling_std(daily_ret, 360d) × sqrt(365) / sqrt(12)
monthly_open = primeiro open do mês (4H)

supply_zone = monthly_open × (1 + n_sigma × monthly_vol)
demand_zone = monthly_open × (1 − n_sigma × monthly_vol)
```

Bandas: 0.5σ a 4.0σ em incrementos de 0.25. Lookback: 360 dias. Dados: BTCUSDT 4H (Binance).

---

## 2. O Evento de Fevereiro 2026

Em **6 de fevereiro de 2026**, o BTCUSDT tocou a **banda de demanda 2.25σ** do indicador.

- Touch bar close: **$64,168**
- Entry do usuário: **$63,262** (100% de exposição, mesmo dia)
- Touch low (mínima do candle): **~$60,000**
- Zona 2.25σ demand calculada: **$61,624**

---

## 3. Análise Histórica — N=5 Eventos 2.25σ Demand

Todos os eventos históricos de toque na banda 2.25σ demand encontrados nos dados (BTCUSDT 4H, desde 2018):

| # | Mês | Touch close | Evento |
|---|---|---|---|
| 1 | Mar-2020 | $4,800 | COVID crash |
| 2 | Mai-2021 | $37,319 | China mining ban + Elon tweets |
| 3 | Jun-2022 | $19,259 | Colapso 3AC / Celsius |
| 4 | Nov-2025 | $84,049 | — |
| 5 | **Fev-2026** | **$64,168** | **Evento atual (em curso)** |

---

## 4. Resultados do Backtest (N=4 excl. evento atual)

### Forward returns — Max High e Min Low em 30 dias (k=180 bars 4H)

| Evento | Touch close | Max 30d (%) | Min 30d (%) |
|---|---|---|---|
| Mar-2020 | $4,800 | +55.4% | -21.2% |
| Mai-2021 | $37,319 | +13.8% | -16.9% |
| Jun-2022 | $19,259 | +17.0% | -8.5% |
| Nov-2025 | $84,049 | +12.5% | -4.1% |
| **Fev-2026** | **$64,168** | **+12.6% (até dia 25)** | **-2.6% (até dia 25)** |

### Observações importantes

- **Dia 25 do evento** (3 março 2026): max $72,271 (+12.6%), min $62,510 (-2.6%)
- Nenhum evento quebrou o touch low dentro de 30 dias em menos de 4 dias (exceto Mar-20, Mai-21 e Jun-22 que quebraram rapidamente)
- Nov-25 e Fev-26 mostram padrão mais forte — drawdown contido, sem quebra rápida do low
- **Double-bottom pattern**: Nov-25 tocou $84k → eventual mínima foi exatamente $60,000 → virou touch do Fev-26

### Probabilidades históricas (N=4, janela 30 dias, ref = touch bar)

**Upside:**
- Reach +16.9% ($75k equiv.): 2/4 = **50%** (Mar-20 e Jun-22)
- Reach +24.7% ($80k equiv.): 1/4 = **25%** (Mar-20 apenas)
- Reach +32.5% ($85k equiv.): 1/4 = **25%** (Mar-20 apenas — outlier COVID)

**Downside:**
- Dip to -6.5% ($60k equiv.): 3/4 = **75%** (Mar-20, Mai-21, Jun-22)
- Dip to -14.3% ($55k equiv.): 2/4 = **50%** (Mar-20, Mai-21)
- Dip to -22.1% ($50k equiv.): 0/4 = **0%** (nunca ocorreu — pior foi -21.2%)

> **Atenção:** percentuais acima medidos do touch bar ($64,168). O preço atual ($68,830) já está +7.3% acima do touch bar — para strikes downside, a distância real a partir do preço atual é maior, tornando os eventos ainda menos prováveis.

---

## 5. Situação Atual (3 março 2026)

- **Preço BTC**: $68,830 (Binance, fechamento diário 2 março)
- **Monthly open março**: $66,973
- **Dias restantes em março**: 28

### Zonas de março 2026

| Sigma | Supply | Demand | Dist. atual (demand) |
|---|---|---|---|
| 0.50σ | $70,344 | $63,603 | -7.6% |
| 1.00σ | $73,715 | $60,232 | -12.5% |
| 1.50σ | $77,086 | $56,861 | -17.4% |
| 2.00σ | $80,457 | $53,490 | -22.3% |
| 2.25σ | $82,141 | $51,805 | -24.7% |
| 2.50σ | $83,827 | $50,120 | -27.2% |

**Monthly vol março**: 10.07%

- $50,000 corresponde a **2.52σ demand** de março
- Já atingido: 0.5σ supply ($70,344) — máxima foi $72,271

---

## 6. Análise Polymarket

**Mercado:** *"What price will Bitcoin hit in March 2026?"*
**Slug:** `what-price-will-bitcoin-hit-in-march-2026`
**API:** `GET https://gamma-api.polymarket.com/events/slug/what-price-will-bitcoin-hit-in-march-2026`

### Quotes ao vivo (capturadas 3 março, 16:08 UTC)

| Strike | Direção | YES mid | NO mid | Barreira | SD (N=4) | Δ Barreira | Sinal |
|---|---|---|---|---|---|---|---|
| $85,000 | ▲ reach | 11% | 89¢ | 24% | 25% | +13pp | BUY YES |
| $80,000 | ▲ reach | 24% | 76¢ | 40% | 25% | +16pp | BUY YES |
| $75,000 | ▲ reach | 47% | 53¢ | 63% | 50% | +16pp | **BUY YES ★** |
| $70,000 | ▲ reach | 99.9% | 0.1¢ | 93% | 100% | — | já atingido |
| $65,000 | ▼ dip | 79% | 21¢ | 75% | — | -4pp | ref. distorcida |
| $60,000 | ▼ dip | 45% | 55¢ | 45% | — | ~0pp | fair |
| $55,000 | ▼ dip | 21% | 79¢ | 21% | — | ~0pp | fair |
| $50,000 | ▼ dip | 12% | 88¢ | 8% | 0% | -4pp | **BUY NO ★★** |
| $45,000 | ▼ dip | 4.4% | 96¢ | 1.8% | 0% | -3pp | BUY NO (illíquido) |

### Modelo de barreira log-normal

```
P(ever touch B in T days) = 2 × Φ(−|ln(B/S)| / (σ√T))

Parâmetros hoje:
  S = $68,830  |  B = barreira  |  T = 28 dias
  σ = 65% a.a.  |  σ√T = 18.0%
```

---

## 7. Teses de Trade (IC Memo)

### Tese 1 — BUY NO: "Will Bitcoin dip to $50,000?" ★★ (maior convicção)

**Mecânica:**
- Comprar token NO a **88¢**
- Recebe $1.00 se BTC NÃO tocar $50k antes de 31/março
- Lucro: 12¢ por contrato (+13.6% ROI)
- Break-even: P(NO) > 88%

**Edge:**
- Barreira: P(YES) = 7.6% → P(NO) = 92.4% → edge = +4.4pp vs mercado
- SD histórico: P(YES) = 0% (0/4 eventos) → edge = +12pp vs mercado
- Para atingir $50k: BTC precisaria cair -27.4% do atual em 28 dias
- Histórico: pior queda em 30d foi -21.2% (COVID) — ainda 6pp aquém

**Estrutura de entradas (múltiplos preços):**
| Tranche | Gatilho BTC | NO aprox. | ROI |
|---|---|---|---|
| T1 (40%) | ~$68,830 (agora) | 88¢ | 13.6% |
| T2 (40%) | ~$64–65k | ~80¢ | 25.0% |
| T3 (20%) | ~$61–62k | ~72¢ | 38.9% |

**Stop:** BTC < $60,000 → fechar 100% imediatamente

**Decaimento temporal:**
| Data | Dias rest. | P($50k toque) |
|---|---|---|
| 03/mar | 28d | 7.6% |
| 09/mar | 22d | 4.5% |
| 15/mar | 16d | 1.9% |
| 21/mar | 10d | 0.3% |

### Tese 2 — BUY YES: "Will Bitcoin reach $75,000?" ★ (convicção moderada)

- Custo: 47¢ | Lucro máx: 53¢
- Barreira: 63% | SD: 50% | Consenso: ~55%
- EV: +16¢ por contrato (+34% ROI)
- Stop: BTC fecha abaixo de $66,973 (monthly open março)
- Realizar 50% em $73,715 (1σ supply março — resistência primária)

### Tese 3 — BUY YES: "Will Bitcoin reach $85,000?" (especulativa)

- Custo: 11¢ | Lucro máx: 89¢
- Barreira: 24% | SD: 25% (Mar-20 outlier — excluindo: 0/3)
- EV: +13¢ por contrato (+119% ROI)
- Posição pequena — máximo 5% do capital Polymarket

---

## 8. Gestão de Risco — Níveis Críticos de Preço

| Nível | Preço | Significado |
|---|---|---|
| Monthly open março | $66,973 | Pivot mensal — perda = atenção |
| Touch bar Fev-26 | $64,168 | Suporte histórico |
| Low Fev 23-24 | $62,510 | Suporte recente — alerta |
| **Stop absoluto** | **$60,000** | **Fundo absoluto Fev-26 — fechar tudo** |
| 1.5σ demand março | $56,861 | Zona extrema |
| 2.5σ demand março | $50,120 | ≈ barreira Polymarket |

---

## 9. Scripts Criados

Todos em `monthly-volatility-zones-indicator/backtest/`:

| Arquivo | Função |
|---|---|
| `polymarket_live.py` | Quotes ao vivo via Gamma API + CLOB API |
| `poly_full_analysis.py` | Análise completa de todos os strikes com barreira + SD |
| `polymarket_30d.py` | Backtest histórico N=4, janela 30 dias |
| `polymarket_riskmanager.py` | Risk management da posição NO $50k |

**Para atualizar quotes ao vivo:**
```bash
cd "C:\Users\Rafael\claude teste\monthly-volatility-zones-indicator\backtest"
python polymarket_live.py
python poly_full_analysis.py
```

**APIs Polymarket (sem autenticação):**
```
Gamma API : https://gamma-api.polymarket.com/events/slug/what-price-will-bitcoin-hit-in-march-2026
CLOB API  : https://clob.polymarket.com/midpoints?token_id=TOKEN_ID
```

---

## 10. IC Memo Completo

Ver arquivo: `IC_MEMO_BTC_MARCH_2026.md`

---

## 11. Perguntas em Aberto / Próximos Passos Sugeridos

1. **Atualizar quotes** — rodar `poly_full_analysis.py` para ver se os preços mudaram
2. **Monitoramento de stops** — verificar se BTC ainda está acima de $62,510
3. **Análise condicional** — se BTC cair para $64-65k, recalcular probabilidades e executar T2
4. **$75k YES** — acompanhar resistência no 1σ supply ($73,715); decidir se realiza parcial
5. **Atualizar dados Binance** — o parquet `BTCUSDT_4h_binance.parquet` vai ficando desatualizado; re-fetch periódico necessário

---

*Análise conduzida com base em dados históricos BTCUSDT 4H (Binance + KuCoin).*
*Modelo de barreira: log-normal sem drift, vol = 65% a.a.*
*N=4 é um sample pequeno — todos os resultados devem ser interpretados com cautela.*
