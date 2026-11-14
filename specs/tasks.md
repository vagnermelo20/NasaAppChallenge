# TASKS — 36 horas (ref.: spec.md / plan.md)

Regra: só começa a próxima fase quando o **checkpoint** da atual passar.
Marque `[x]` ao concluir. Horas = estimativa; inclui ~6 h de sono/pausas.

## Fase 0 — Setup (h 0–1)
- [x] T01 Criar repo GitHub, venv, `requirements.txt` (pandas, duckdb, pyarrow, streamlit, streamlit-folium, plotly, scikit-learn)
- [x] T02 MAP_KEY não necessária para o histórico (CSVs por país são públicos; só para 2026 via API)

## Fase 1 — Dados (h 1–6) · R1, R2, R3
- [x] T03 `01_download.py`: baixar CSVs anuais do Brasil — MODIS 2001→hoje, VIIRS S-NPP 2012→hoje
- [x] T04 `02_clean_grid.py`: aplicar filtros R2
- [x] T05 Criar célula 0,25° (`floor(lat/0.25)*0.25`) + ano + mês; contar por sensor -> `grid_monthly.parquet`
- [x] T06 Adicionar coluna `bloco` (5° × 5°) a cada célula — usada no fator `k` (sem precisar baixar mapa de estados)
> Formato: notebooks Jupyter em `notebooks/` (Fase 1 = `01_dados.ipynb`)
- **Checkpoint 1:** gráfico anual Brasil MODIS × VIIRS lado a lado (deve mostrar VIIRS bem maior)  ✅ razão VIIRS/MODIS ≈ 3,8 estável (2012–2022)
- [ ] T06b 2001–jun/2002 só tem Terra (Aqua começou em jul/2002): calcular `k` separado para Terra na Fase 2

## Fase 2 — Harmonização (h 6–14) · R4, R5 ← PRIORIDADE
- [ ] T07 `03_harmonize.py`: calcular `k` por estado × mês (2012–2020), fallback nacional
- [ ] T08 Gerar `harmonized.parquet` (2001–2011 convertido + 2012→hoje VIIRS)
- [ ] T09 Gráfico anual bruto × harmonizado
- **Checkpoint 2 (A1):** sem degrau em 2012

## Fase 3 — Validação (h 14–17) · R6
- [ ] T10 `04_validate.py`: leave-one-year-out, métricas -> `reports/metrics.json` + figuras
- [ ] T11 (opcional) Regressão log; manter só se melhorar
- **Checkpoint 3 (A2):** correlação ≥ 0,85

## Fase 4 — App (h 17–27) · R7–R11
- [ ] T12 `app.py`: mapa folium com desenho de polígono + filtro por estado + datas (R7)
- [ ] T13 Consulta DuckDB: soma das células dentro da região, por ano × mês
- [ ] T14 Heatmap calendário plotly com viridis (R8)
- [ ] T15 Cartão "mês atual vs mediana" + modo anomalia (R9)
- [ ] T16 Botão download CSV (R10)
- [ ] T17 Aba Metodologia com figuras e métricas (R11)
- **Checkpoint 4 (A3):** consulta < 3 s

## Fase 5 — Entrega (h 27–36) · A4
- [ ] T18 Deploy no Streamlit Cloud (parquet pequeno vai junto no repo)
- [ ] T19 README: problema, método, link, dados NASA usados
- [ ] T20 Vídeo de 30 s + slides (história -> degrau de 2012 sumindo -> demo do calendário)
- [ ] T21 Enviar no portal do Space Apps (reservar 2 h de folga antes do prazo)

## Se o tempo apertar, corte nesta ordem
T11 → polígono desenhado (fica só filtro por estado) → T15 modo anomalia → T17 vira imagem estática.
**Nunca corte:** T07, T08, T09, T14, T16, T18.
