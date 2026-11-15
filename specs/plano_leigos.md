# Plano: deixar o EMBER entendível para leigos (15/11/2026)

**Status (15/11/2026, noite): L1–L7, L9 e L10 feitos. Falta só o L8 (teste com 2–3 leigos de verdade).**

Regra de ouro: **uma pessoa que nunca ouviu falar de MODIS ou VIIRS precisa entender a tela em 10 segundos.**
Se não for entendível por leigo, não entra na tela principal.

## Diagnóstico (o que está errado hoje)

1. **O mapa do Calendar não mostra os focos.** Em "Select an area" o mapa é só um mapa de ruas (OpenStreetMap)
   sem nenhum ponto de fogo. A pessoa precisa desenhar a área "às cegas", sem ver onde está queimando.
   A função que desenha os focos dentro da área (`show_area_hotspots`, `app/app.py:1242`) existe, mas **nunca é chamada**.
2. **Duas telas de mapa separadas.** O mapa com os pontos fica em "Fire map"; o desenho da área fica em "Calendar".
   O leigo não liga uma coisa à outra (o próprio texto da página manda ir de uma aba para a outra).
3. **Controles demais.** Barra lateral com "Data product", "Display style", "Layer appearance", "Science status",
   "Lat-Lon + radius"; no Calendar, mais de 10 blocos empilhados (resumo, gráfico de harmonização, Day/Week/Month,
   calendário, anomalias, valores nas células, faixa de incerteza, comparação, métricas, CSV, tabela).
4. **Seis abas** (Fire map, Calendar, Hotspot search, Trends, Methodology, About). Três delas são para especialistas.
5. **Jargão.** "VIIRS-equivalent", "harmonized activity", "0.25° grid", "UTC", "active grid cells", "A2 target not met",
   "anomalies", "LOYO". Números de validação (66%, 92%, 73,7%) aparecem na tela principal.

## Como o mapa da NASA (FIRMS) resolve, e o que copiar

- Fundo de satélite, pontos pequenos de fogo, **cor pela idade** (amarelo = últimas 24 h, laranja = 2–7 dias, vermelho = mais antigo).
- Abre já mostrando os **últimos dias**, sem pedir nada.
- Legenda curta e sempre visível: "Each dot = a hot spot seen from space".
- Desenhar uma área é feito **sobre o próprio mapa de focos**.

## A nova tela (um único fluxo: Onde? → Quando? → Quanto?)

```
┌───────────────────────────────────────────────────────────┐
│ EMBER — Where and when does Brazil burn?                  │
│ "Each dot is a hot spot seen by a NASA satellite.         │
│  Draw a box around any place to see its fire history."    │
├───────────────────────────────────────────────────────────┤
│ [Last 7 days ▼]   (Last 24 h / 7 days / 30 days / pick)   │
│                                                           │
│   MAPA ÚNICO: satélite + pontos de fogo (cor pela idade)  │
│   + ferramenta de desenhar quadrado/forma                 │
│                                                           │
│ [Clear area]                                              │
├───────────────────────────────────────────────────────────┤
│ YOUR AREA (aparece depois de desenhar)                    │
│  ● 3 frases grandes:                                      │
│    "Fire season here: Aug–Oct. Worst month: Sep."         │
│    "Last month: 1,240 hot spots — 30% below normal."      │
│    "Worst year since 2001: 2010."                         │
│  ● Calendário ano × mês (azul = pouco, vermelho = muito)  │
│  ● Gráfico simples por ano                                │
│  ● [Download data]                                        │
├───────────────────────────────────────────────────────────┤
│ ▸ Why can we compare 2005 with 2024? (gráfico 1 frase)    │
│ ▸ For experts (busca de focos, dia/semana, anomalias,     │
│   faixa de incerteza, metodologia, CSV detalhado)         │
└───────────────────────────────────────────────────────────┘
```

## Etapas

| # | O quê | Detalhe | Horas |
|---|---|---|---|
| L1 | **Mapa único com focos e desenho** | Juntar "Fire map" e "Select an area": fundo de satélite, pontos de fogo do período escolhido, ferramenta de desenhar no mesmo mapa. Ao desenhar, o resto da página atualiza (sem botão "Apply" separado, ou um botão grande "Show this area"). | 3 |
| L2 | **Pontos como no FIRMS** | Cor pela idade do foco (24 h / 2–7 dias / mais antigo), ponto pequeno com borda; abre em "Last 7 days". Acima de 50 mil pontos: mostrar os mais recentes e avisar em uma frase. Popup: data, hora local (não UTC), satélite em palavras simples. | 2 |
| L3 | **Bloco "Your area" em frases** | Reaproveitar `show_region_summary`: 3–4 frases grandes no topo. Depois calendário e gráfico anual. Sem números de validação. | 1,5 |
| L4 | **Menos abas** | Ficam 3: **Map** (tudo acima), **How it works** (Methodology + About em linguagem simples, 1 figura), **For experts** (Hotspot search, Day/Week/Month, Trends, anomalias, faixa de incerteza, CSVs, métricas). | 1,5 |
| L5 | **Barra lateral vazia ou fechada** | Tirar "Data product", "Display style", "Layer appearance", "Science status", "Lat-Lon + radius" da tela principal (vão para For experts ou somem). Barra lateral começa fechada. | 1 |
| L6 | **Trocar o jargão** | Glossário único no código: "hotspot" → "hot spot (heat seen from space)"; "VIIRS-equivalent / harmonized" → "same scale for every year"; sem "0.25°", "grid cell", "UTC", "A2". Avisos técnicos ficam em For experts. Um aviso só, curto: "A hot spot is heat seen from space, not the size of the fire." | 1 |
| L7 | **"Why can we compare years?"** | O botão sem/com harmonização vira um bloco recolhido, com uma frase: "The newer satellite (2012+) sees about 4× more spots. We corrected older years so all years use the same ruler." | 0,5 |
| L8 | **Teste com leigo** | Mostrar a 2–3 pessoas sem explicar nada e perguntar: (1) onde está pegando fogo agora? (2) qual o pior mês na sua cidade? (3) este ano está pior ou melhor que o normal? Anotar onde travam e corrigir. | 1 |
| L10 ✅ | **Aba "How it works"** | Feita em 15/11/2026: explicação em 7 passos simples (satélites medem calor → satélite velho × novo → o salto falso de 2012 com o gráfico sem/com harmonização → o que fizemos, comparando com troca de moeda → quão bom é em frases "9 de 10" → o que dá para fazer → cuidados). Na L4 ela vira a aba fixa "How it works", junto com Methodology/About. | 1 |
| L9 | **Testes automáticos e publicação** | Ajustar `app/test_delivery.py` às novas abas; incluir teste de que o mapa de desenho recebe os pontos; rodar `check_release`; publicar. | 1,5 |

**Total: ~13 h.** Se o tempo apertar, a ordem é L1 → L2 → L3 → L6 → L4 → L5 → L9 → L7 → L8.
L1 sozinho já resolve o problema principal ("o Calendar não mostra onde é o fogo").

## O que NÃO muda
- Dados, harmonização v2 e números de validação (só saem da tela principal; continuam em How it works / For experts).
- O usuário continua desenhando a área (sem regiões com nome).
- Cores azul → vermelho do calendário.

## Critério de pronto
- Uma pessoa leiga responde às 3 perguntas do L8 sem ajuda.
- Abrir o link mostra pontos de fogo em menos de 5 s, sem clicar em nada.
- Nenhuma palavra do glossário técnico na aba Map.
