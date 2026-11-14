# Entrega da Pessoa A para a Pessoa B — dados reais

## O que chegou no repositório
| Arquivo | O que é |
|---|---|
| `data/processed/harmonized.parquet` | **Dado real.** Contrato combinado: `lat, lon, ano, mes, focos_harmonizados, fonte, dado_incompleto`. 1.212.739 linhas, 2001–2025, 15 meses marcados como incompletos. |
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
- **Faixa de incerteza antes de 2012:** `metrics.json → prova_harmonizacao → faixa_incerteza → largura_por_focos_modis` dá a faixa de 90% conforme a quantidade de focos MODIS (ex.: > 500 focos: −19% a +21%; ≤ 20 focos: −6% a +229%). Ela acerta 89,9% das vezes.
- **Aviso para regiões pequenas e meses isolados antes de 2012:** a comparação é mais confiável em regiões de ~1° ou maiores e em somas anuais.
- **Caso real no vídeo:** a seca da Amazônia de 2005 e 2010 (só MODIS) agora fica na mesma escala de 2019 e 2024.

## Limitações a manter visíveis
- Foco detectado ≠ incêndio ≠ área queimada.
- 2026 ainda não está no arquivo: depende da MAP_KEY do FIRMS (notebook 06). O "mês atual" do app hoje é dezembro de 2025.
