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
  notebooks/
    00_entendendo_dados   análise + visualização (feito)
    01_dados              R1, R3 download + grade (feito; regerar com satélite/dia-noite)
    02_identificacao      identificação campo a campo (feito)
    03_versao_pixel       versão MODIS, pixel, campos (feito)
    04_harmonizacao       R2 (máscara), R4, R5, R5b, R5c
    05_validacao          R6 -> figuras + metrics.json em reports/
  app/app.py            R7–R11
  reports/              figuras + métricas.json
```

## Fluxo dos dados
```
CSV FIRMS (pontos) -> filtro -> célula 0,25° + mês -> contagens por sensor
   -> fator de conversão (2012–2021, por satélite) -> série harmonizada 2001→hoje -> app
```

## Método de harmonização (o coração)
1. **Definição de "MODIS":** Terra e Aqua **convertidos separadamente** e depois somados (VIIRS ≈ 6,1× Aqua e ≈ 9,8× Terra; horários de passagem diferentes).
   **Definição de "VIIRS":** só S-NPP (evita contar o mesmo foco duas vezes com NOAA-20).
   Bônus para a apresentação: Aqua e S-NPP passam no mesmo horário (~13:30), o que mostra que a diferença vem do sensor.
2. **Fator por grupo:** `k_sat = soma(VIIRS) / soma(MODIS_sat)` por **satélite × bloco 5°×5° × mês do ano**,
   usando 2012–2021. Dia/noite separado é opcional (VIIRS tem proporcionalmente mais focos à noite). Grupos com pouco fogo (< 30 focos MODIS) usam o fator nacional do mês.
3. **Série final:**
   - 2001–2011: `harmonizado = (Terra × k_Terra + Aqua × k_Aqua) / 2` (média das duas estimativas; jan/2001–jun/2002 só Terra)
   - 2012→hoje: `harmonizado = VIIRS` (real)
4. **Upgrade se sobrar tempo (R4 v2):** regressão `log(VIIRS+1) ~ log(MODIS+1) + mês + bioma`.
   Só troca o método se melhorar as métricas da validação.

## Validação (R6)
- Leave-one-year-out em 2012–2021: treina o `k` sem o ano X, prevê X, compara com VIIRS real.
- Métricas: correlação, erro relativo, % de acerto do mês de pico.
- Figura principal: série anual **bruta** (degrau em 2012) × **harmonizada** (contínua).

## Decisões e riscos
- **Download pesado** -> usar CSV anual por país do FIRMS (Brasil), converter logo para Parquet.
- **Deriva da órbita do Terra/Aqua (comprovada a partir de 2022)** -> calibrar só até 2021 (citar na apresentação).
- **Fontes estáticas** -> máscara única de células com `type=2` em qualquer ano/sensor (o `type` do MODIS mudou em 2018 e não existe em NRT).
- **2026** -> API do FIRMS (NRT, MAP_KEY). Mês corrente sempre marcado como provisório.
- **Contrato entre as duas frentes:** `data/processed/harmonized.parquet` com colunas
  `lat, lon, ano, mes, focos_harmonizados, fonte ('modis_convertido'|'viirs'), dado_incompleto (bool)`.
  O app começa usando um mock com esse formato gerado a partir do `grid_monthly.parquet`.
- **Deduplicação VIIRS (375 m -> 1 km)** fica como melhoria opcional; o fator `k` já absorve a diferença média.
