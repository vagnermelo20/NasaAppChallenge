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
- **R2** Filtrar: MODIS `confidence >= 30`; VIIRS `confidence in (n, h)`; fontes estáticas removidas por **máscara única de células de 0,02° (~2 km)** que tiveram `type` 1, 2 ou 3 em **pelo menos 2 anos** (qualquer sensor), igual para todos os anos e sensores; a exigência de 2 anos evita remover fogo real classificado uma única vez (o `type` do MODIS mudou de regra em 2018 e não existe nos dados NRT).
- **R3** Agregar em grade 0,25° × mês × **satélite (Terra, Aqua, S-NPP)** × **dia/noite** (tabela de contagens).
- **R4** Treinar conversão MODIS → VIIRS no período de sobreposição **2012–2021** (depois de 2021 a órbita do Terra/Aqua deriva), **separada por satélite (Terra / Aqua)** e por bloco 5° × mês, refinada na região de 2° × mês com encolhimento para o bloco; Terra e Aqua combinados pelo inverso da variância.
- **R5** Aplicar a conversão em 2001–2011 e usar VIIRS real de 2012→hoje. Jan/2001–jun/2002 só tem Terra → usar o `k` do Terra.
- **R5b** Incluir 2026 (ano corrente) via API do FIRMS (SP até 31/07/2026 e NRT depois; exige MAP_KEY). O S-NPP parou de enviar dados em 02/11/2026; dias sem dado ficam marcados como incompletos.
- **R5c** Marcar meses com dias sem observação (ex.: VIIRS 2022 e 2024) como "dado incompleto".
- **R6** Validar com dados de fora do treino (leave-one-year-out) e reportar métricas.

### App web
- **R7** Usuário escolhe região (retângulo/polígono no mapa ou lat/lon + raio; estado é opcional) e intervalo de datas.
- **R8** Calendário heatmap ano × mês com rampa de cor acessível (viridis).
- **R9** Comparar mês atual com a mediana histórica (anomalia).
- **R10** Download CSV da série da região selecionada.
- **R11** Página "Metodologia" com gráfico antes/depois e métricas de validação.
- **R12** Busca por **intervalo de datas exato** (até 92 dias, até 200 mil focos): lista dos focos da região (data, hora UTC, satélite, lat/lon, FRP) com download CSV, rotulada como observação por sensor. Cada foco tem `peso_harmonizado` (VIIRS = 1; MODIS = 1/(1/k_Terra + 1/k_Aqua) da célula × mês; só Terra: k_Terra), cuja soma por célula × mês reproduz o `harmonized.parquet`; comparar o mesmo intervalo entre anos usa a soma dos pesos (antes de 2012: "aproximado", com faixa de incerteza).

## Critérios de aceite
- **A1** O gráfico anual harmonizado **não mostra salto artificial em 2012**.
- **A2** Na validação: correlação mensal ≥ 0,85 e mês de pico correto em ≥ 80% das células com fogo.
  **Resultado (decisão da revisão independente, 14/11/2026): não atingido na célula 0,25°** — correlação 0,959 ✅, mês de pico 73,7% ❌ (±1 mês 90,4%; nacional 90%; bloco 5° 79,9%; células com ≥ 200 focos/ano 83,5%). O critério **não foi alterado** depois do resultado; o app avisa que o mês de pico é confiável em regiões de ~2° ou mais, ou com centenas de focos.
- **A3** App responde a uma consulta de região em < 3 s.
- **A4** App publicado com link público e demo de 30 s gravada.

## Fora de escopo
Previsão de fogo, área queimada, dados em tempo real minuto a minuto, cobertura global.
