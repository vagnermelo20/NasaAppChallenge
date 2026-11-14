"""Gera um MOCK do harmonized.parquet para desenvolver o front-end (tarefa B1).

NÃO é o dado harmonizado de verdade: usa VIIRS real de 2012 em diante e
MODIS x 3,8 (razão média provisória) antes de 2012.
Quando a Pessoa A entregar data/processed/harmonized.parquet, o app passa a usar o real.

Rodar a partir da raiz do repositório:
    python app/make_mock.py
"""
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
ORIGEM = RAIZ / "data" / "processed" / "grid_monthly.parquet"
DESTINO = RAIZ / "data" / "processed" / "harmonized_mock.parquet"
RAZAO_PROVISORIA = 3.8
COLUNAS = ["lat", "lon", "ano", "mes", "focos_harmonizados", "fonte", "dado_incompleto"]


def main() -> None:
    g = pd.read_parquet(ORIGEM)
    viirs = g["ano"] >= 2012
    g["focos_harmonizados"] = g["n_viirs"].where(viirs, g["n_modis"] * RAZAO_PROVISORIA).astype(float)
    g["fonte"] = viirs.map({True: "viirs", False: "modis_convertido"})
    g["dado_incompleto"] = False
    out = g.loc[g["focos_harmonizados"] > 0, COLUNAS].reset_index(drop=True)
    out.to_parquet(DESTINO, index=False)
    print(f"{DESTINO.name}: {len(out):,} linhas, anos {out.ano.min()}–{out.ano.max()}, colunas {list(out.columns)}")


if __name__ == "__main__":
    main()
