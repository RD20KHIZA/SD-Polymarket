# IC MEMO
## "What price will Bitcoin hit in March 2026?" — Polymarket
**Data:** 3 março 2026, 16:08 UTC | **BTC:** $68,830 | **Desk:** Digital Assets / Event-Driven

---

## 1. Resumo Executivo

Identificamos **três posições com edge positivo** no mercado Polymarket *"What price will Bitcoin hit in March?"*, todas corroboradas por dois frameworks quantitativos independentes: modelo de barreira log-normal e indicador de zonas de volatilidade mensal (SD, N=4 eventos históricos 2.25σ demand).

| # | Posição | Custo | Ganho máx | EV/contrato | Convicção |
|---|---|---|---|---|---|
| 1 | **BUY NO — dip to $50k** | 88¢ | 12¢ | +4.4¢ | Alta — ambos frameworks convergem |
| 2 | **BUY YES — reach $75k** | 47¢ | 53¢ | +16.3¢ | Moderada — frameworks divergem em magnitude |
| 3 | **BUY YES — reach $85k** | 11¢ | 89¢ | +13.1¢ | Baixa — outlier-driven, posição especulativa |

---

## 2. Framework de Análise

### 2a. Modelo de Barreira Log-Normal

Calcula a probabilidade de o preço **tocar** um nível B em qualquer momento nos próximos T dias, a partir do preço atual S:

```
P(tocar B) = 2 × Φ( −|ln(B/S)| / (σ√T) )

Parâmetros: S = $68,830  |  T = 28 dias  |  σ = 65% a.a.  |  σ√T = 18.0%
```

Captura a probabilidade de barreira (ever-touch), não apenas o preço no vencimento.

### 2b. Indicador SD — Evidência Histórica (N=4)

Quatro eventos históricos de toque na banda 2.25σ demand (excluindo o evento em curso de fev/26). Para cada, computado o `max_high` e `min_low` dentro de **30 dias** a partir do touch bar close ($64,168):

| Evento | Touch close | Max 30d | Drawdown 30d |
|---|---|---|---|
| Mar-2020 (COVID) | $4,800 | +55.4% | -21.2% |
| Mai-2021 (China ban) | $37,319 | +13.8% | -16.9% |
| Jun-2022 (3AC) | $19,259 | +17.0% | -8.5% |
| Nov-2025 | $84,049 | +12.5% | -4.1% |

> **Nota de referência:** o indicador SD mede a partir do touch bar close ($64,168). O preço atual ($68,830) já está +7.3% acima desse nível. Para strikes downside, a distância real a partir do preço atual é **maior** do que a medida do touch bar — tornando os alvos ainda mais difíceis de atingir.

---

## 3. Tabela Completa de Odds — Todos os Strikes

*Live quotes capturadas em 16:08 UTC via Gamma API + CLOB API*

| Strike | Dir | YES mid | NO mid | Barreira | SD (N=4) | Δ Barreira | Δ SD | Sinal |
|---|---|---|---|---|---|---|---|---|
| $85,000 | ▲ | 11% | **89¢** | 24% | 25% | +13pp | +14pp | BUY YES |
| $80,000 | ▲ | 24% | **76¢** | 40% | 25% | +16pp | +1pp | BUY YES |
| **$75,000** | ▲ | **47%** | **53¢** | **63%** | **50%** | **+16pp** | **+3pp** | **BUY YES ★** |
| $70,000 | ▲ | 99.9% | 0.1¢ | 93% | 100% | — | — | já atingido |
| $65,000 | ▼ | 79% | 21¢ | 75% | 100%* | -4pp | — | ref. distorcida* |
| $60,000 | ▼ | 45% | 55¢ | 45% | 75%* | ~0pp | — | fair* |
| $55,000 | ▼ | 21% | 79¢ | 21% | 50%* | ~0pp | — | fair* |
| **$50,000** | ▼ | **12%** | **88¢** | **8%** | **0%** | **-4pp** | **-12pp** | **BUY NO ★★** |
| $45,000 | ▼ | 4.4% | 96¢ | 1.8% | 0% | -3pp | -4pp | BUY NO (illíquido) |

*\* Strikes downside $65k–$55k: SD usa touch bar ($64,168 < $65k) como referência, inflando artificialmente os percentuais. O modelo de barreira — que usa o preço atual — é o benchmark correto para esses níveis.*

---

## 4. Posição Principal ★★ — BUY NO: Dip to $50,000

### Tese

> O mercado precifica 12% de probabilidade de BTC tocar $50,000 antes de 31/março. O modelo de barreira calcula 7.6%. O indicador histórico registra 0/4 ocorrências. O mercado carrega um prêmio de tail risk de ~4pp injustificado pelo contexto estrutural.

### Mecânica

```
Instrumento : Polymarket binary — "Will Bitcoin dip to $50,000 in March?"
Posição     : BUY NO token

Custo       : 88¢ por contrato
Payout      : $1.00 se BTC NÃO tocar $50k antes de 31/março
Lucro       : 12¢ por contrato  (+13.6% ROI)
Perda máx   : 88¢ por contrato
Break-even  : P(NO) > 88%
```

### Evidências

**Modelo de barreira:**
```
|ln(50.000 / 68.830)| = 31.9%
σ√T = 65%/√365 × √28  = 18.0%

P(YES) = 2 × Φ(−31.9% / 18.0%) = 2 × Φ(−1.77) = 7.6%
P(NO)  = 92.4%
```

**Indicador SD (N=4, 30 dias):**
- Nenhum evento 2.25σ demand atingiu −27.4% em 30 dias
- Pior drawdown histórico: −21.2% (COVID, mar-2020) — ainda 6pp aquém da barreira
- Resultado: **0/4 = 0% de ocorrência**

**Convergência dos frameworks:**

| Framework | P(YES) estimado | vs. Polymarket (12%) |
|---|---|---|
| Barreira log-normal | 7.6% | −4.4pp |
| Indicador SD histórico | 0.0% | −12.0pp |
| Consenso | **~5–8%** | **−4 a −7pp de edge** |

### Estrutura de Entradas — Múltiplos Preços

Quando BTC cai sem violar o stop, o YES sobe por medo e o **NO fica mais barato — melhorando o ROI sem alterar a tese fundamental.**

| Tranche | Gatilho BTC | NO estimado | Custo | Lucro | ROI | Tamanho |
|---|---|---|---|---|---|---|
| **T1** | ~$68,830 (hoje) | **88¢** | 88¢ | 12¢ | 13.6% | 40% |
| **T2** | ~$64–65k | **~80¢** | 80¢ | 20¢ | 25.0% | 40% |
| **T3** | ~$61–62k | **~72¢** | 72¢ | 28¢ | 38.9% | 20% |
| *Média ponderada* | | **~81¢** | | **~19¢** | **~23.5%** | 100% |

> **T3 só se ativa se BTC > $60,000.** Qualquer violação do stop cancela T3 e fecha T1+T2.

### Sizing — Kelly Criterion

```
b = 12 / 88 = 0.136
p = 0.924  (P(NO) pelo modelo barreira)
q = 0.076

Full Kelly  = (0.924 × 0.136 − 0.076) / 0.136 = 38%
Half-Kelly  = 19% do capital alocado a Polymarket
```

**Teto prático:** volume do mercado ~$417k USDC. Posição acima de $50k começa a afetar o preço. Máximo recomendado: **$75k USDC total** (T1+T2+T3), com limit orders em cada tranche.

---

## 5. Posição Secundária ★ — BUY YES: Reach $75,000

### Tese

> O mercado precifica 47% de probabilidade de BTC tocar $75k em março. O modelo de barreira calcula 63%. O indicador SD corrobora com 50% (2/4 eventos). Há convergência parcial com edge de ~+16¢ por contrato.

### Mecânica

```
Custo       : 47¢
Payout      : $1.00 se BTC tocar $75,000 antes de 31/março
Lucro       : 53¢  (+112% ROI se ganhar)
Break-even  : P(YES) > 47%
Barreira    : 63%  |  SD: 50%  |  Consenso adotado: ~55%
EV          : +16¢ por contrato  (+34% ROI sobre capital)
```

### Nota de Cautela

A barreira de 63% assume passeio aleatório sem drift. As zonas de supply do indicador criam resistência real entre $68,830 e $75k:

- 0.5σ supply março: $70,344 *(já atingido — max $72,271)*
- 1.0σ supply março: $73,715 ← **resistência primária**

O indicador SD (50%) é o estimador mais conservador e provavelmente mais fiel à microestrutura. Utilizamos **50% como base**, gerando edge de +3pp vs. mercado (47%).

*Convicção moderada. Posição menor que o NO $50k.*

---

## 6. Posição Especulativa — BUY YES: Reach $85,000

### Mecânica

```
Custo       : 11¢
Payout      : $1.00 se BTC tocar $85,000 antes de 31/março
Lucro       : 89¢  (+809% ROI se ganhar)
Break-even  : P(YES) > 11%
Barreira    : 24%  |  SD: 25% (1/4 — Mar-2020 outlier)
EV          : +13¢ por contrato  (+119% ROI sobre capital)
```

### Risco Principal

O único evento histórico que suporta esta posição é o bounce de +55% do COVID (mar-2020) — um outlier estrutural. **Excluindo Mar-2020: 0/3 = 0%.**

> Posição pequena e especulativa. Sizing máximo: **5% do capital destinado ao livro Polymarket.**

---

## 7. Gestão de Risco e Stop

### BUY NO $50k — Posição Principal

| Nível | Preço BTC | Ação |
|---|---|---|
| Monitoramento | < $66,973 (monthly open março) | Atenção; sem ação |
| Alerta | < $62,510 (low de 23–24/fev) | Não ativar T3; revisar T2 |
| **Stop absoluto** | **< $60,000** | **Fechar 100% imediatamente** |
| Checkpoint temporal | > 15/março sem violar $62,510 | P($50k) < 2%; posição confortável |

### BUY YES $75k — Posição Secundária

| Cenário | Ação |
|---|---|
| BTC atinge $73,715 (1σ supply) | Realizar 50% — zona de resistência primária |
| BTC atinge $75,000 | Fechar 100% — alvo atingido |
| BTC fecha abaixo de $66,973 (monthly open) | Stop — momentum reverteu |

---

## 8. Decaimento Temporal — BUY NO $50k

O tempo trabalha ativamente a favor da posição. A cada dia sem tocar $50k, a probabilidade de toque cai mecanicamente:

| Data | Dias restantes | P($50k) modelo | P(NO) |
|---|---|---|---|
| 03/mar (hoje) | 28d | 7.6% | 92.4% |
| 09/mar | 22d | 4.5% | 95.5% |
| 15/mar | 16d | 1.9% | 98.1% |
| 21/mar | 10d | 0.3% | 99.7% |
| 24/mar | 7d | ~0.0% | ~100% |

> Após **21 de março**: posição praticamente resolvida independentemente do nível de preço, desde que o stop não tenha sido ativado.

---

## 9. Riscos e Mitigantes

| Risco | Probabilidade | Mitigante |
|---|---|---|
| BTC < $50k em março | ~7.6% (modelo) | Stop em $60k captura maior parte do percurso |
| N=4 insuficiente | Estrutural | Três frameworks convergem; sem dependência exclusiva do histórico |
| Evento exógeno (hack, regulação) | Não modelável | Sizing < 1.9% do portfólio total |
| Risco de protocolo Polymarket | Baixo/moderado | Limite duro de $75k USDC no NO $50k |
| Liquidez — spread se alarga | Baixo (vol $417k) | Entradas com limit orders; nunca market orders |
| $75k YES: resistência das supply zones | Moderado | Stop em $66,973; realização parcial em $73,715 |

---

## 10. Alocação Recomendada

| Posição | Capital USDC | % portfólio | Tipo | Status |
|---|---|---|---|---|
| NO $50k — T1 | $30,000 | 0.6% | Core | Executar agora |
| NO $50k — T2 | $30,000 | 0.6% | Add-on | Condicional BTC ~$64–65k |
| NO $50k — T3 | $15,000 | 0.3% | Máxima convicção | Condicional BTC ~$61–62k |
| YES $75k | $15,000 | 0.3% | Secundária | Executar agora |
| YES $85k | $5,000 | 0.1% | Especulativa | Opcional |
| **Total** | **$95,000** | **~1.9%** | | |

---

## 11. Recomendação ao IC

**Aprovado para execução imediata:**
- **NO $50k — T1** ($30k USDC), limit order em 88¢
- **YES $75k** ($15k USDC), limit order em 47¢

**Condicionais** (aguardam gatilhos de preço definidos na seção 7):
- NO $50k — T2 e T3
- YES $85k ($5k) pode ser executado se dados on-chain confirmarem momentum de alta

---

*Modelos e quotes gerados via scripts `poly_full_analysis.py` e `polymarket_live.py`.*
*Dados: Polymarket Gamma API + CLOB API (público, sem autenticação).*
*Indicador SD: `backtest/polymarket_30d.py` — N=4 eventos 2.25σ demand, janela 30 dias.*
