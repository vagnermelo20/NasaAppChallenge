# PLAN — Como implementar (ref.: spec.md)

## Stack (escolhida pela velocidade)
| Camada | Ferramenta | Por quê |
|---|---|---|
| Dados | Python + pandas + DuckDB + Parquet | Rápido, roda local, sem servidor de banco |
| Harmonização | pandas + scikit-learn (opcional) | Razão simples primeiro, regressão se sobrar tempo |
| App | **Streamlit** + streamlit-folium + plotly | App inteiro em 1 arquivo Python |
| Deploy | Streamlit Community Cloud (grátis) | Deploy direto do GitHub |

## Estrutura de pastas
```
hotspots/
  specs/            spec.md, plan.md, tasks.md
  data/raw/         CSVs do FIRMS (não vai pro git)
  data/processed/   grid_monthly.parquet, harmonized.parquet
  src/
    01_download.py      R1
    02_clean_grid.py    R2, R3
    03_harmonize.py     R4, R5
    04_validate.py      R6  -> gera figuras em reports/
  app/app.py            R7–R11
  reports/              figuras + métricas.json
```

## Fluxo dos dados
```
CSV FIRMS (pontos) -> filtro -> célula 0,25° + mês -> contagens por sensor
   -> fator de conversão (2012–2020) -> série harmonizada 2001→hoje -> app
```

## Método de harmonização (o coração)
1. **Definição de "MODIS":** Terra + Aqua somados (cobre 2001→hoje).
   **Definição de "VIIRS":** só S-NPP (evita contar o mesmo foco duas vezes com NOAA-20).
   Bônus para a apresentação: Aqua e S-NPP passam no mesmo horário (~13:30), o que mostra que a diferença vem do sensor.
2. **Fator por grupo:** `k = soma(VIIRS) / soma(MODIS)` por **bloco 5°×5° × mês do ano**,
   usando 2012–2020. Grupos com pouco fogo (< 30 focos MODIS) usam o fator nacional do mês.
3. **Série final:**
   - 2001–2011: `harmonizado = MODIS × k`
   - 2012→hoje: `harmonizado = VIIRS` (real)
4. **Upgrade se sobrar tempo (R4 v2):** regressão `log(VIIRS+1) ~ log(MODIS+1) + mês + bioma`.
   Só troca o método se melhorar as métricas da validação.

## Validação (R6)
- Leave-one-year-out em 2012–2020: treina o `k` sem o ano X, prevê X, compara com VIIRS real.
- Métricas: correlação, erro relativo, % de acerto do mês de pico.
- Figura principal: série anual **bruta** (degrau em 2012) × **harmonizada** (contínua).

## Decisões e riscos
- **Download pesado** -> usar CSV anual por país do FIRMS (Brasil), converter logo para Parquet.
- **Deriva da órbita do Terra/Aqua após 2020** -> calibrar só até 2020 (citar na apresentação).
- **Deduplicação VIIRS (375 m -> 1 km)** fica como melhoria opcional; o fator `k` já absorve a diferença média.
