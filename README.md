# Harmonized Burning Activity Calendar — MODIS × VIIRS

NASA Space Apps Challenge 2026 · *MODIS and VIIRS Hot Spots Harmonization*

Une os focos de calor do **MODIS** (1 km, 2001→) e do **VIIRS S-NPP** (375 m, 2012→) do NASA FIRMS numa série mensal única e harmonizada, e mostra um calendário de queimadas por região.

## Estrutura
| Pasta | Conteúdo |
|---|---|
| `specs/` | Spec-Driven Development: `spec.md` (o quê), `plan.md` (como), `tasks.md` (tarefas) |
| `notebooks/00_entendendo_dados.ipynb` | Análise e visualização: o que cada sensor mede e por que diferem |
| `notebooks/01_dados.ipynb` | Download do FIRMS (Brasil), filtros e grade 0,25° × mês |
| `data/processed/` | `grid_monthly.parquet` — contagens por célula, mês e sensor |
| `reports/` | Figuras geradas pelos notebooks |

## Como rodar
```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows
.venv/Scripts/python -m ipykernel install --user --name hotspots
```
Execute `notebooks/01_dados.ipynb` primeiro (baixa ~500 MB para `data/raw/`, fora do git) e depois `00_entendendo_dados.ipynb`.

## Dados
NASA FIRMS — MODIS Collection 6.1 (MCD14ML) e VIIRS S-NPP 375 m (VNP14IMG), arquivos anuais por país.
