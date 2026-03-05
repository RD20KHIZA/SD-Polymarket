# Como Rodar o Dashboard — Monthly Volatility Zones Indicator

O dashboard é uma aplicação **Streamlit** (Python) — backend e frontend num único processo.
Não há servidor separado.

---

## Pré-requisitos

- Python 3.10+
- pip

Verificar versão:
```bash
python --version
```

---

## 1. Instalar dependências

```bash
cd "C:\Users\Rafael\claude teste\monthly-volatility-zones-indicator\backtest"
pip install -r requirements.txt
```

Pacotes instalados:
| Pacote | Uso |
|---|---|
| `streamlit` | Dashboard web |
| `pandas` / `numpy` | Processamento de dados |
| `plotly` | Gráficos interativos |
| `pyarrow` | Leitura dos arquivos `.parquet` |
| `vectorbt` | Backtesting (opcional — o app roda sem ele) |
| `ccxt` | Fetch de dados via KuCoin (exchange padrão) |
| `python-dotenv` | Variáveis de ambiente |

> **Nota:** `vectorbt` pode falhar na instalação em alguns ambientes Windows.
> O app continua funcional sem ele — a aba "VectorBT Sweep" fica desativada.

---

## 2. Subir o dashboard

```bash
cd "C:\Users\Rafael\claude teste\monthly-volatility-zones-indicator\backtest"
python -m streamlit run app.py
```

O Streamlit abre automaticamente em:
```
http://localhost:8501
```

Se a porta 8501 estiver ocupada, use outra:
```bash
python -m streamlit run app.py --server.port 8502
```

---

## 3. Abas disponíveis no dashboard

| Aba | Conteúdo |
|---|---|
| Price Chart | Gráfico de preço com zonas de volatilidade sobrepostas |
| Return Curves | Forward returns médios por sigma e direção |
| Hit Rate | Taxa de acerto por nível e holding period |
| Sharpe vs k | Sharpe ratio por horizonte (k) |
| Distribution | Distribuição dos retornos por evento |
| Full Report | Tabela completa com todas as métricas |
| Data | Dados brutos dos eventos detectados |
| VectorBT Sweep | Sweep de parâmetros via VectorBT (requer instalação) |

---

## 4. Configurações padrão no sidebar

- **Exchange:** KuCoin (padrão) — troque para Binance se preferir
- **Symbol:** BTC/USDT
- **Lookback vol:** 360 dias
- **Max k (holding period):** 120 bars (4H) = 20 dias
- **Sigmas analisados:** todos (0.5σ a 4.0σ)

---

## 5. Usar dados Binance locais (recomendado)

Os dados da Binance já foram baixados e estão em cache:
```
data/BTCUSDT_4h_binance.parquet   ← Binance, jan/2020 → mar/2026
data/BTC_USDT_4h_2018-01-01.parquet  ← histórico desde 2018
```

Para rodar os scripts de análise Polymarket (independentes do Streamlit):
```bash
cd "C:\Users\Rafael\claude teste\monthly-volatility-zones-indicator\backtest"

# Quotes ao vivo da Polymarket
python polymarket_live.py

# Análise completa de todos os strikes
python poly_full_analysis.py

# Backtest histórico 30 dias (N=4 eventos 2.25σ)
python polymarket_30d.py

# Risk management da posição NO $50k
python polymarket_riskmanager.py
```

---

## 6. Troubleshooting

**`streamlit: command not found`**
```bash
python -m streamlit run app.py
```

**`ModuleNotFoundError: vectorbt`**
```bash
pip install vectorbt
# ou ignore — o app roda sem ele
```

**`UnicodeEncodeError` nos scripts Python (Windows)**
Os scripts já têm `sys.stdout.reconfigure(encoding='utf-8')` na primeira linha.
Se aparecer mesmo assim, rode com:
```bash
set PYTHONIOENCODING=utf-8 && python nome_do_script.py
```

**Porta 8501 ocupada**
```bash
python -m streamlit run app.py --server.port 8502
```

**Dados desatualizados**
O arquivo `BTCUSDT_4h_binance.parquet` vai ficando obsoleto.
Para atualizar, rode o fetcher (requer internet):
```bash
python data_fetcher.py
```

---

## 7. Estrutura de arquivos

```
monthly-volatility-zones-indicator/
├── backtest/
│   ├── app.py                  ← entry point do Streamlit
│   ├── zone_calculator.py      ← cálculo das zonas SD
│   ├── event_study.py          ← detecção de toques e forward returns
│   ├── data_fetcher.py         ← fetch OHLCV (KuCoin/CCXT)
│   ├── visualization.py        ← gráficos Plotly
│   ├── vbt_backtest.py         ← VectorBT (opcional)
│   ├── polymarket_live.py      ← quotes ao vivo Polymarket
│   ├── poly_full_analysis.py   ← análise completa strikes
│   ├── polymarket_30d.py       ← backtest histórico 30d
│   ├── polymarket_riskmanager.py ← risk management NO $50k
│   └── requirements.txt
├── data/
│   ├── BTCUSDT_4h_binance.parquet
│   ├── BTC_USDT_4h_2018-01-01.parquet
│   ├── BTC_USDT_4h_2020-01-01.parquet
│   └── BTC_USDT_4h_2024-12-01.parquet
├── IC_MEMO_BTC_MARCH_2026.md   ← IC memo Polymarket
├── CONTEXT_FOR_AI.md           ← contexto para outros assistentes
└── COMO_RODAR.md               ← este arquivo
```
