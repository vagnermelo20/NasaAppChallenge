"""Covariáveis do MODIS por região 2° × ano × mês (existem desde 2001). Salva em scratchpad."""
import duckdb, sys
sys.stdout.reconfigure(encoding='utf-8')
OUT = sys.argv[1]
con = duckdb.connect()
con.execute(f"""
COPY (
WITH p AS (
  SELECT floor(latitude/2)::INT qy, floor(longitude/2)::INT qx,
         year(CAST(acq_date AS DATE)) ano, month(CAST(acq_date AS DATE)) mes,
         satellite, daynight, frp, floor(latitude/0.25)::INT cy, floor(longitude/0.25)::INT cx
  FROM read_parquet('data/raw/modis_*.parquet') m
  ANTI JOIN 'data/processed/static_mask.parquet' s
    ON floor(m.latitude/0.02)::INT = s.fy AND floor(m.longitude/0.02)::INT = s.fx
  WHERE TRY_CAST(confidence AS INT) >= 30)
SELECT qy, qx, ano, mes, count(*) n_modis,
       avg((frp < 10)::INT) f_fraco, median(ln(greatest(frp, 0.1))) logfrp_med,
       quantile_cont(ln(greatest(frp, 0.1)), 0.9) logfrp_p90,
       avg((daynight = 'N')::INT) f_noite, avg((satellite = 'Aqua')::INT) f_aqua,
       count(DISTINCT (cy, cx)) n_celulas, count(*) / count(DISTINCT (cy, cx)) focos_por_celula
FROM p GROUP BY ALL) TO '{OUT}' (FORMAT PARQUET)""")
print(con.execute(f"SELECT count(*), min(ano), max(ano) FROM '{OUT}'").fetchall())
