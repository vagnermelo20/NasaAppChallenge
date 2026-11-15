"""09 — Série diária e semanal harmonizada, com cascata de sensores (tarefas D2–D3 do CLAUDE.md).

Rodar da raiz do repositório:  .venv/Scripts/python notebooks/09_serie_diaria.py

Cascata por dia (no Brasil inteiro):
  1. S-NPP observou o dia            -> usa S-NPP                         (fonte = snpp)
  2. sem S-NPP, NOAA-20 observou     -> usa NOAA-20 / 0,965 (escala S-NPP) (fonte = noaa20)
  3. sem VIIRS (antes de 2012)       -> MODIS convertido (peso_harmonizado) (fonte = modis_convertido)
  4. nenhum sensor                   -> dia sem dado (não é zero fogo)
"Observou o dia" = o sensor teve ao menos um foco no Brasil naquele dia (o FIRMS não publica a faixa de passagem).
O mês continua sendo o harmonized.parquet: nos dias de S-NPP/MODIS a soma diária reproduz o mensal.

Saídas (data/processed/):
  diario/diario_AAAA.parquet   lat, lon (canto SW 0,25°), data, focos, fonte
  semanal.parquet              lat, lon, semana (segunda-feira), focos, dias_observados, semana_incompleta
  disponibilidade_diaria.parquet  data, snpp, noaa20, terra, aqua, fonte_usada
"""
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
PROC, RAW = ROOT / 'data/processed', ROOT / 'data/raw'
OUT = PROC / 'diario'; OUT.mkdir(exist_ok=True)
RAZAO_N20 = 0.965          # NOAA-20 / S-NPP no Brasil, 2018–2021 (notebook 07 / revisão)
con = duckdb.connect()
focos = f"read_parquet('{(PROC / 'focos').as_posix()}/focos_*.parquet')"
n20_arqs = sorted(p.as_posix() for p in (RAW / 'noaa20').glob('viirs-jpss1_*.parquet'))
mask = (PROC / 'static_mask.parquet').as_posix()
celulas = f"(SELECT DISTINCT lat, lon FROM '{(PROC / 'harmonized.parquet').as_posix()}')"

# NOAA-20 com os mesmos filtros do S-NPP (confiança n|h, máscara, células do Brasil)
con.execute(f"""CREATE TABLE n20 AS
SELECT floor(latitude/0.25)*0.25 lat, floor(longitude/0.25)*0.25 lon, CAST(acq_date AS DATE) data, count(*) / {RAZAO_N20} focos
FROM read_parquet({n20_arqs}) p ANTI JOIN '{mask}' m ON floor(p.latitude/0.02)::INT = m.fy AND floor(p.longitude/0.02)::INT = m.fx
WHERE confidence IN ('n','h') GROUP BY ALL""" if n20_arqs else "CREATE TABLE n20 (lat DOUBLE, lon DOUBLE, data DATE, focos DOUBLE)")
con.execute(f"DELETE FROM n20 WHERE (lat, lon) NOT IN (SELECT (lat, lon) FROM {celulas})")

# disponibilidade por dia e fonte escolhida
con.execute(f"""CREATE TABLE disp AS
WITH f AS (SELECT CAST(data AS DATE) data, bool_or(satelite='S-NPP') snpp, bool_or(satelite='Terra') terra, bool_or(satelite='Aqua') aqua
           FROM {focos} GROUP BY 1),
     n AS (SELECT DISTINCT data, true noaa20 FROM n20),
     d AS (SELECT CAST(x AS DATE) data FROM range(DATE '2001-01-01', current_date, INTERVAL 1 DAY) t(x))
SELECT d.data, coalesce(f.snpp,false) snpp, coalesce(n.noaa20,false) noaa20, coalesce(f.terra,false) terra, coalesce(f.aqua,false) aqua,
       CASE WHEN f.snpp THEN 'snpp' WHEN n.noaa20 THEN 'noaa20' WHEN f.terra OR f.aqua THEN 'modis_convertido' ELSE 'sem_dado' END fonte_usada
FROM d LEFT JOIN f USING (data) LEFT JOIN n USING (data) ORDER BY 1""")
con.execute(f"COPY disp TO '{(PROC / 'disponibilidade_diaria.parquet').as_posix()}' (FORMAT PARQUET)")

# série diária pela cascata
con.execute(f"""CREATE TABLE diario AS
SELECT lat_cel lat, lon_cel lon, CAST(data AS DATE) data, sum(peso_harmonizado) focos,
       CASE WHEN any_value(satelite) = 'S-NPP' THEN 'snpp' ELSE 'modis_convertido' END fonte
FROM {focos} f JOIN disp USING (data)
WHERE (disp.fonte_usada = 'snpp' AND f.satelite = 'S-NPP') OR (disp.fonte_usada = 'modis_convertido' AND f.satelite <> 'S-NPP')
GROUP BY lat_cel, lon_cel, CAST(data AS DATE)
UNION ALL
SELECT n.lat, n.lon, n.data, n.focos, 'noaa20' FROM n20 n JOIN disp USING (data) WHERE disp.fonte_usada = 'noaa20'""")
for f in OUT.glob('diario_*.parquet'): f.unlink()
for (ano,) in con.execute("SELECT DISTINCT year(data) FROM diario ORDER BY 1").fetchall():
    con.execute(f"COPY (SELECT * FROM diario WHERE year(data) = {ano} ORDER BY data, lat, lon) "
                f"TO '{(OUT / f'diario_{ano}.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")

# semanal (semana começando na segunda-feira); semana incompleta = algum dia sem dado
con.execute(f"""COPY (
WITH w AS (SELECT date_trunc('week', data)::DATE semana, count(*) FILTER (WHERE fonte_usada <> 'sem_dado') dias_observados FROM disp GROUP BY 1)
SELECT d.lat, d.lon, date_trunc('week', d.data)::DATE semana, sum(d.focos) focos, any_value(w.dias_observados) dias_observados,
       any_value(w.dias_observados) < 7 semana_incompleta
FROM diario d JOIN w ON w.semana = date_trunc('week', d.data)::DATE GROUP BY 1, 2, 3 ORDER BY 3, 1, 2)
TO '{(PROC / 'semanal.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)""")

# conferências
print(con.execute("SELECT fonte_usada, count(*) dias, min(data), max(data) FROM disp GROUP BY 1 ORDER BY 2 DESC").df().to_string(index=False))
print(con.execute("SELECT fonte, count(*) linhas, round(sum(focos)) focos FROM diario GROUP BY 1").df().to_string(index=False))
chk = con.execute(f"""WITH m AS (SELECT lat, lon, year(data) ano, month(data) mes, sum(focos) s FROM diario WHERE fonte <> 'noaa20' GROUP BY ALL)
SELECT max(abs(m.s - h.focos_harmonizados)) dif_max FROM m JOIN '{(PROC / 'harmonized.parquet').as_posix()}' h USING (lat, lon)
WHERE h.ano = m.ano AND h.mes = m.mes AND NOT h.dado_incompleto""").fetchone()[0]
print('Diferença máxima diario->mensal (meses completos, sem NOAA-20):', chk)
