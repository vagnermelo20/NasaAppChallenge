# Entrega da Pessoa A para a Pessoa B — dados reais

## O que chegou no repositório
| Arquivo | O que é |
|---|---|
| `data/processed/harmonized.parquet` | **Dado real.** Contrato combinado: `lat, lon, ano, mes, focos_harmonizados, fonte, dado_incompleto`. 2001–2026 (2026 recortado às células do Brasil); meses com dias sem dado marcados como incompletos. |
| `reports/metrics.json` | Métricas. Para o app, use a seção `prova_harmonizacao`. |
| `docs/metodologia.md` | Texto da aba Methodology, em inglês, com os números finais. |
| `reports/prova_antes_depois.png`, `reports/prova_pantanal.png`, `reports/harmonizado_anual.png` | Figuras principais para a aba Methodology e para o vídeo. |

## O que fazer (B11)
1. `git pull`.
2. Rodar o app: ele já prioriza o `harmonized.parquet` real sobre o mock (o rodapé deve mostrar `harmonized.parquet`).
3. Conferir: `.venv\Scripts\python -m app.check_release` (deve dar `ready_for_review`) e `.venv\Scripts\python -m unittest app.test_delivery -v` (16 testes passaram do lado de A).
4. Conferir no navegador as 3 regiões de exemplo (Pantanal, Matopiba, Acre) e que 2011 → 2012 não tem degrau.
5. Na aba Methodology, ler o texto de `docs/metodologia.md` e as figuras acima.

## Números que podem aparecer no app
- Por ano, MODIS convertido e VIIRS concordam dentro de ±20% em **92%** das regiões de 2°; por mês, em 66% (85% nos meses com muito fogo).
- Referência: dois VIIRS idênticos concordam em 85% por mês.

## Ideias novas (combinar entre A e B antes de implementar)
- **Faixa de incerteza antes de 2012:** `metrics.json → prova_harmonizacao → faixa_incerteza → largura_por_focos_modis` dá a faixa de 90% conforme a quantidade de focos MODIS (ex.: > 500 focos: −19% a +21%; ≤ 20 focos: −70% a +249%). Leitura: VIIRS equivalente entre `convertido × fator_baixo` e `convertido × fator_alto`. Ela acerta 89,9% das vezes. **Correção:** a versão anterior deste recado dizia −6%; a faixa foi recalibrada sem filtrar pelo VIIRS (antes de 2012 não existe VIIRS para filtrar).
- **Aviso para regiões pequenas e meses isolados antes de 2012:** a comparação é mais confiável em regiões de ~1° ou maiores e em somas anuais.
- **Caso real no vídeo:** a seca da Amazônia de 2005 e 2010 (só MODIS) agora fica na mesma escala de 2019 e 2024.

## Limitações a manter visíveis
- Foco detectado ≠ incêndio ≠ área queimada.
- **2026 está no `harmonized.parquet`** (notebook 06): SP até 31/07 e NRT depois. Meses com dias sem dado estão com `dado_incompleto = True` (mar, abr, jun, jul, ago e nov); set e out vêm do NRT com todos os dias e contam como completos. **Não há dados do S-NPP desde 02/11/2026** (serviço data_availability do FIRMS; causa desconhecida): novembro tem só 2 dias e está marcado como incompleto. O "mês completo mais recente" é outubro de 2026.

---
## Atualização de 14/11/2026 (depois da revisão independente)
**Novos arquivos de A:** 2026 em `harmonized.parquet` e `grid_sat.parquet`; base de focos `data/processed/focos/focos_AAAA.parquet` (notebook 08); robustez e faixa recalibrada no notebook 07; notebook 05 com o método final.

**Decisões fechadas com o revisor:**
- Calendário continua **mensal e harmonizado**; dia e hora entram pela busca de focos (R12).
- **A2 não atingido na célula** (73,7%; ±1 mês 90,4%). O critério não foi mudado; o app deve avisar que o mês de pico é confiável em áreas de ~2° ou mais, ou com centenas de focos.
- Números para o pitch: mensal **66%** (±20%, região 2°), anual **92%**; nunca apresentar o 92% como acurácia geral.

**Tarefas do B (detalhes e ordem no `tasks.md`, seção "Roteiro do B"):** B15 último mês completo (out/2026) no destaque · ~~B16 Fire map no `grid_sat`~~ (feito no B21) · B17 regra do mês de pico e textos finais · B18 busca por datas com `peso_harmonizado` · B10/B20 acabamento e VERIFY.md · B19 faixa de incerteza (opcional).

**Como usar a base de focos (B18):** leia só os anos do intervalo, por exemplo
`SELECT * FROM read_parquet(['data/processed/focos/focos_2020.parquet']) WHERE data BETWEEN ? AND ? AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?`.
Para comparar o mesmo intervalo em anos diferentes, some `peso_harmonizado` (2012+ é exato = contagem VIIRS; antes de 2012 é aproximado).

