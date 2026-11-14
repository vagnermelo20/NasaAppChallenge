# SPEC — Calendário Harmonizado de Queimadas (MODIS + VIIRS)

> Fonte da verdade do projeto. Toda tarefa precisa apontar para um requisito daqui (R#).

## Problema
MODIS (1 km, 2000→hoje, saindo de operação) e VIIRS (375 m, 2012→hoje) contam focos de forma diferente.
Sem harmonizar, a série histórica tem um "degrau" falso em 2012 e não dá para comparar anos.

## Objetivo principal
Unir as duas bases numa **série mensal única (2001→hoje)** em que o sensor de origem não importa.

## Escopo
- Região piloto: **Brasil** (arquitetura pronta para expandir).
- Grade: células de **0,25°**, agregação **mensal**.
- Unidade final: **"focos equivalentes VIIRS"**.

## Requisitos
### Dados e harmonização (prioridade máxima)
- **R1** Baixar focos MODIS (C6.1) e VIIRS S-NPP (375 m) do FIRMS para o Brasil, 2001→hoje.
- **R2** Filtrar: MODIS `confidence >= 30`; VIIRS `confidence in (n, h)`; fontes estáticas removidas por **máscara única de células** (`type=2` em qualquer ano/sensor), igual para todos os anos e sensores (o `type` do MODIS mudou de regra em 2018 e não existe nos dados NRT).
- **R3** Agregar em grade 0,25° × mês × **satélite (Terra, Aqua, S-NPP)** × **dia/noite** (tabela de contagens).
- **R4** Treinar conversão MODIS → VIIRS no período de sobreposição **2012–2021** (depois de 2021 a órbita do Terra/Aqua deriva), **separada por satélite (Terra / Aqua)** e por bloco 5° × mês.
- **R5** Aplicar a conversão em 2001–2011 e usar VIIRS real de 2012→hoje. Jan/2001–jun/2002 só tem Terra → usar o `k` do Terra.
- **R5b** Incluir 2026 (ano corrente) via API do FIRMS (dados NRT, exigem MAP_KEY).
- **R5c** Marcar meses com dias sem observação (ex.: VIIRS 2022 e 2024) como "dado incompleto".
- **R6** Validar com dados de fora do treino (leave-one-year-out) e reportar métricas.

### App web
- **R7** Usuário escolhe região (retângulo/polígono no mapa ou lat/lon + raio; estado é opcional) e intervalo de datas.
- **R8** Calendário heatmap ano × mês com rampa de cor acessível (viridis).
- **R9** Comparar mês atual com a mediana histórica (anomalia).
- **R10** Download CSV da série da região selecionada.
- **R11** Página "Metodologia" com gráfico antes/depois e métricas de validação.

## Critérios de aceite
- **A1** O gráfico anual harmonizado **não mostra salto artificial em 2012**.
- **A2** Na validação: correlação mensal ≥ 0,85 e mês de pico correto em ≥ 80% das células com fogo.
- **A3** App responde a uma consulta de região em < 3 s.
- **A4** App publicado com link público e demo de 30 s gravada.

## Fora de escopo
Previsão de fogo, área queimada, dados em tempo real minuto a minuto, cobertura global.
