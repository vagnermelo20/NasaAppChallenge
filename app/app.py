"""EMBER: where and when Brazil burns, explained for everyone (plan in specs/plano_leigos.md)."""
import calendar
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import folium
import numpy as np
import pandas as pd
import pyarrow as pa
import plotly.express as px
import plotly.graph_objects as go
import shapely
import streamlit as st
from branca.element import MacroElement, Template
from folium.plugins import Draw, HeatMap
from folium.utilities import JsCode
from shapely.geometry import Polygon, shape
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / 'data/processed/harmonized.parquet'
MOCK = ROOT / 'data/processed/harmonized_mock.parquet'
MONTHS = list(calendar.month_abbr)[1:]
MAX_MAP_POINTS = 50_000   # above this the browser map becomes slow and unreadable
SEARCH_PAGE_SIZE = 5_000


@st.cache_data
def hotspot_locations(path: str, version: int, year: int, month: int,
                      sensor: str | None, region_wkt: str | None, days: tuple = (1, 31)) -> pd.DataFrame:
    last = calendar.monthrange(year, month)[1]
    start = date(year, month, max(1, days[0]))
    end = date(year, month, min(last, days[1])) + timedelta(days=1)
    predicate = " AND satelite = 'S-NPP'" if sensor == 'VIIRS S-NPP' else (
        " AND satelite IN ('Terra', 'Aqua')" if sensor == 'MODIS Terra + Aqua' else '')
    with duckdb.connect() as con:
        points = con.execute('SELECT lat, lon, data, hora_utc, satelite, frp, daynight, peso_harmonizado '
                             'FROM read_parquet(?) WHERE data >= ? AND data < ?' + predicate,
                             [path, start, end]).df()
    if region_wkt:
        points = points[shapely.contains_xy(shapely.from_wkt(region_wkt), points.lon, points.lat)]
    return points.reset_index(drop=True)


def point_selection(con, files: tuple[tuple[str, int], ...], start: date, end: date,
                    sensor: str, region_wkt: str | None) -> tuple[str, list]:
    """Apply exact spatial selection inside DuckDB, before aggregation or pagination."""
    if end < start:
        raise ValueError('The end date must be on or after the start date.')
    if not files:
        raise ValueError('No point files are available for this interval.')
    predicates = {'All available sensors': '', 'VIIRS S-NPP': " AND satelite='S-NPP'",
                  'MODIS Terra + Aqua': " AND satelite IN ('Terra','Aqua')"}
    if sensor not in predicates:
        raise ValueError('Unknown satellite sensor.')
    sql = 'FROM read_parquet(?) WHERE data BETWEEN ? AND ?' + predicates[sensor]
    args: list = [[p for p, _ in files], start, end]
    geometry = shapely.from_wkt(region_wkt) if region_wkt else None
    if geometry is not None:
        west, south, east, north = geometry.bounds
        sql += ' AND lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?'
        args.extend([west, east, south, north])
        def inside_area(latitudes, longitudes):
            return pa.array(shapely.contains_xy(geometry,
                            longitudes.to_numpy(zero_copy_only=False),
                            latitudes.to_numpy(zero_copy_only=False)))
        con.create_function('inside_area', inside_area, ['DOUBLE', 'DOUBLE'], 'BOOLEAN', type='arrow')
        sql += ' AND inside_area(CAST(lat AS DOUBLE), CAST(lon AS DOUBLE))'
    return sql, args


@st.cache_data(max_entries=16)
def search_hotspots(files: tuple[tuple[str, int], ...], start: date, end: date,
                    sensor: str, region_wkt: str | None, limit: int | None = None,
                    newest_first: bool = False, offset: int = 0) -> tuple[pd.DataFrame, bool]:
    """One bounded page of exact matches; the boolean indicates another page exists."""
    page_size = min(SEARCH_PAGE_SIZE, limit if limit is not None else SEARCH_PAGE_SIZE)
    if page_size < 1 or offset < 0:
        raise ValueError('Page size must be positive and offset must not be negative.')
    columns = 'lat,lon,data,hora_utc,satelite,frp,daynight,peso_harmonizado'
    order = ' DESC' if newest_first else ''
    with duckdb.connect() as con:
        where, args = point_selection(con, files, start, end, sensor, region_wkt)
        points = con.execute('SELECT ' + columns + ' ' + where
                             + f' ORDER BY data{order}, hora_utc{order}, satelite, lat, lon, frp, daynight, peso_harmonizado'
                             + ' LIMIT ? OFFSET ?', [*args, page_size+1, offset]).df()
    return points.iloc[:page_size].copy(), len(points) > page_size


@st.cache_data(max_entries=16)
def area_point_totals(files: tuple[tuple[str, int], ...], start: date, end: date,
                      region_wkt: str | None) -> tuple[int, float]:
    with duckdb.connect() as con:
        where, args = point_selection(con, files, start, end, 'All available sensors', region_wkt)
        count, total = con.execute('SELECT count(*), coalesce(sum(peso_harmonizado),0) ' + where, args).fetchone() or (0, 0.)
    return int(count), float(total)


@st.cache_data(max_entries=4)
def area_points(files: tuple[tuple[str, int], ...], start: date, end: date, region_wkt: str | None) -> pd.DataFrame:
    """Every hot spot in the dates and area, with no cap (exact area filter inside DuckDB)."""
    with duckdb.connect() as con:
        where, args = point_selection(con, files, start, end, 'All available sensors', region_wkt)
        return con.execute('SELECT lat, lon, data, hora_utc, satelite, frp, peso_harmonizado ' + where
                           + ' ORDER BY data, hora_utc, lat, lon', args).df()


def point_export(points: pd.DataFrame) -> pd.DataFrame:
    """Unified hot spot list: where, when, how strong (percentile) and how much it counts on the common scale."""
    result = pd.DataFrame({'date_utc': pd.to_datetime(points.data).dt.strftime('%Y-%m-%d'),
                           'time_utc': points.hora_utc.map(lambda value: f'{int(value)//100:02d}:{int(value)%100:02d}'),
                           'latitude': points.lat, 'longitude': points.lon,
                           'hotspots_common_scale': points.peso_harmonizado})
    if 'frp_pct' in points.columns:
        result.insert(4, 'heat_strength_percentile', points.frp_pct)
    return result


def point_files(start: date, end: date) -> tuple[tuple[str, int], ...]:
    files = [ROOT / f'data/processed/focos/focos_{year}.parquet' for year in range(start.year, end.year + 1)]
    if any(not p.exists() for p in files):
        raise ValueError('A point file is missing for one of the requested years.')
    return tuple((str(p), p.stat().st_mtime_ns) for p in files)


def interval_coverage(start: date, end: date, coverage: pd.DataFrame) -> str:
    months = pd.period_range(start, end, freq='M')
    for month in months:
        row = coverage[(coverage.ano == month.year) & (coverage.mes == month.month)]
        if row.empty:
            return 'Outside available monthly coverage'
    if any(bool(coverage.loc[(coverage.ano == month.year) & (coverage.mes == month.month),
                              'incompleto'].any()) for month in months):
        return 'Provisional · intersects an incomplete month'
    return 'No monthly completeness flag'


def data_source() -> tuple[str, int]:
    path = REAL if REAL.exists() else MOCK
    return str(path), path.stat().st_mtime_ns


@st.cache_data
def metadata(path: str, modified_ns: int) -> pd.DataFrame:
    with duckdb.connect() as con:
        columns = set(con.execute('DESCRIBE SELECT * FROM read_parquet(?)', [path]).df().column_name)
        required = {'lat', 'lon', 'ano', 'mes', 'focos_harmonizados', 'fonte', 'dado_incompleto'}
        missing = required - columns
        if missing:
            raise ValueError('Dataset does not match the agreed format. Missing columns: '
                             + ', '.join(sorted(missing)))
        invalid = con.execute(
            'SELECT count(*) FROM read_parquet(?) WHERE '
            'lat IS NULL OR lon IS NULL OR NOT isfinite(lat) OR NOT isfinite(lon) '
            'OR ano IS NULL OR mes IS NULL OR mes NOT BETWEEN 1 AND 12 '
            'OR focos_harmonizados IS NULL OR NOT isfinite(focos_harmonizados) '
            'OR focos_harmonizados < 0 OR dado_incompleto IS NULL '
            "OR fonte IS NULL OR fonte NOT IN ('modis_convertido', 'viirs')", [path]
        ).fetchone()
        if invalid and invalid[0]:
            raise ValueError(f'Dataset contains {invalid[0]:,} invalid records. Ask the data team to verify the export.')
        return con.execute(
            'SELECT ano, mes, bool_or(dado_incompleto) AS incompleto, '
            "string_agg(DISTINCT fonte, '+') AS source "
            'FROM read_parquet(?) GROUP BY ano, mes ORDER BY ano, mes', [path]
        ).df()


@st.cache_data
def cached_cells(path: str, modified_ns: int) -> pd.DataFrame:
    with duckdb.connect() as con:
        return con.execute('SELECT DISTINCT lat, lon FROM read_parquet(?)', [path]).df()


def celulas() -> pd.DataFrame:
    return cached_cells(*data_source())


def complete_months(raw: pd.DataFrame, coverage: pd.DataFrame,
                    ano_ini: int, ano_fim: int) -> pd.DataFrame:
    """Sparse rows mean zero only within the source's temporal coverage."""
    index = pd.MultiIndex.from_product(
        [range(ano_ini, ano_fim + 1), range(1, 13)], names=['ano', 'mes'])
    result = raw.set_index(['ano', 'mes']).reindex(index)
    result['focos'] = result['focos'].fillna(0.0)
    flags = coverage.set_index(['ano', 'mes']).incompleto.reindex(index).fillna(False)
    result['incompleto'] = result.incompleto.fillna(False).astype(bool) | flags.astype(bool)
    first = int((coverage.ano * 12 + coverage.mes).min())
    last = int((coverage.ano * 12 + coverage.mes).max())
    codes = index.get_level_values('ano') * 12 + index.get_level_values('mes')
    outside = (codes < first) | (codes > last)
    result.loc[outside, 'focos'] = np.nan
    result.loc[outside, 'incompleto'] = True
    return result.reset_index()[['ano', 'mes', 'focos', 'incompleto']]


@st.cache_data
def cached_series(path: str, modified_ns: int, poligono_wkt: str | None,
                  ano_ini: int, ano_fim: int) -> pd.DataFrame:
    selected = cached_cells(path, modified_ns)
    if poligono_wkt:
        polygon = shapely.from_wkt(poligono_wkt)
        selected = selected[shapely.contains_xy(
            polygon, selected.lon + 0.125, selected.lat + 0.125)]
    with duckdb.connect() as con:
        con.register('sel', selected)
        raw = con.execute(
            'SELECT ano, mes, sum(focos_harmonizados) AS focos, '
            'bool_or(dado_incompleto) AS incompleto FROM read_parquet(?) '
            'JOIN sel USING (lat, lon) WHERE ano BETWEEN ? AND ? '
            'GROUP BY ano, mes', [path, ano_ini, ano_fim]).df()
    return complete_months(raw, metadata(path, modified_ns), ano_ini, ano_fim)


def serie_regiao(poligono_wkt: str | None, ano_ini: int, ano_fim: int) -> pd.DataFrame:
    return cached_series(*data_source(), poligono_wkt, ano_ini, ano_fim)


def drawn_region(payload: dict) -> str | None:
    """Union drawn polygons; an empty list means drawings were deleted."""
    drawings = payload.get('all_drawings')
    if drawings is None:
        active = payload.get('last_active_drawing')
        drawings = [active] if active else []
    polygons = []
    for feature in drawings:
        geometry = shape(feature['geometry'])
        if geometry.geom_type not in ('Polygon', 'MultiPolygon') or not geometry.is_valid:
            raise ValueError('Draw a valid, non-intersecting polygon or rectangle.')
        if not geometry.is_empty:
            polygons.append(geometry)
    return shapely.union_all(polygons).wkt if polygons else None


def anomaly_values(series: pd.DataFrame) -> pd.Series:
    """Compare each complete month only with earlier complete years."""
    result = pd.Series(np.nan, index=series.index, dtype=float)
    complete = series[~series.incompleto & series.focos.notna()]
    for index, row in complete.iterrows():
        history = complete[(complete.mes == row.mes) & (complete.ano < row.ano)].focos
        median = history.median()
        if pd.notna(median) and median > 0:
            result.loc[index] = (row.focos - median) / median * 100
    return result


def latest_comparison(series: pd.DataFrame) -> dict:
    available = series[series.focos.notna()].sort_values(['ano', 'mes'])
    complete = available[~available.incompleto]
    if complete.empty:
        return {}
    latest = complete.iloc[-1]
    newer_incomplete = available[available.incompleto & (
        (available.ano * 12 + available.mes) > (latest.ano * 12 + latest.mes))]
    history = series[(series.mes == latest.mes) & (series.ano < latest.ano)
                     & ~series.incompleto & series.focos.notna()].copy()
    median = history.focos.median()
    delta = ((latest.focos - median) / median * 100
             if pd.notna(median) and median > 0 and not latest.incompleto else None)
    if len(history) < 3:
        category = 'Limited history'
    elif latest.focos > history.focos.quantile(0.90):
        category = 'Critical'
    elif latest.focos > history.focos.quantile(0.75):
        category = 'Above normal'
    elif latest.focos < history.focos.quantile(0.25):
        category = 'Below normal'
    else:
        category = 'Normal'
    return dict(year=int(latest.ano), month=int(latest.mes), value=float(latest.focos),
                incomplete=bool(latest.incompleto), history=history, median=median,
                delta=delta, category=category,
                newer_incomplete=[f'{MONTHS[int(row.mes)-1]} {int(row.ano)}'
                                  for row in newer_incomplete.itertuples()])


def calendar_figure(series: pd.DataFrame, anomaly: bool = False, show_values: bool = True):
    values = series.pivot(index='ano', columns='mes', values='focos')
    shown = (series.assign(anomaly=anomaly_values(series))
             .pivot(index='ano', columns='mes', values='anomaly')) if anomaly else values
    labels = shown.map(lambda n: (f'{n:+.0f}%' if anomaly else f'{n:,.0f}')
                       if pd.notna(n) else '—')
    flags = series.pivot(index='ano', columns='mes', values='incompleto')
    for year in values.index:
        for month in values.columns:
            if flags.loc[year, month] and pd.notna(shown.loc[year, month]):
                labels.loc[year, month] += '*'
    # Counts: log colour scale so the Aug-Oct peaks do not flatten the rest; labels and hover keep real values.
    colour = shown.to_numpy() if anomaly else np.log10(shown.to_numpy(dtype=float) + 1)
    fig = px.imshow(colour, x=MONTHS, y=values.index.astype(str),
                    color_continuous_scale='RdBu_r' if anomaly else 'RdYlBu_r', aspect='auto',
                    labels={'x': 'Month', 'y': 'Year',
                            'color': 'vs usual (%)' if anomaly else 'Hot spots<br>per month'})
    if anomaly:
        fig.update_coloraxes(cmin=-100, cmax=100, cmid=0, colorbar=dict(
            tickvals=[-100, -50, 0, 50, 100], ticktext=['-100%', '-50%', 'usual', '+50%', '>= +100%']))
    else:
        top = int(np.ceil(np.nanmax(colour))) if np.isfinite(colour).any() else 1
        ticks = list(range(0, top + 1))
        fig.update_coloraxes(colorbar=dict(tickvals=ticks, ticktext=[f'{10**t:,.0f}' for t in ticks]))
    fig.update_traces(text=labels.to_numpy(), texttemplate='%{text}' if show_values else '',
                      customdata=np.where(flags.to_numpy(), 'Some satellite days missing', 'All days seen'),
                      hovertemplate=('Year: %{y}<br>Month: %{x}<br>'
                                     + ('vs usual: %{text}' if anomaly else 'Hot spots: %{text}')
                                     + '<br>%{customdata}<extra></extra>'),
                      hoverongaps=False)
    if not show_values:
        marked = series[series.incompleto & series.focos.notna()]
        if not marked.empty:
            fig.add_trace(go.Scatter(
                x=[MONTHS[int(m) - 1] for m in marked.mes], y=marked.ano.astype(str),
                mode='text', text=['*'] * len(marked), textfont=dict(color='#111111', size=18),
                name='Incomplete data', hovertemplate='%{y} %{x}: incomplete data<extra></extra>'))
    fig.update_layout(height=max(350, len(values) * 26 + 120),
                      margin=dict(l=10, r=10, t=30, b=10))
    # Anos como categorias: "2001", "2002"... parecem números e o Plotly faria um eixo linear, misturando
    # anos (≈2000) com as posições 0..N da linha 2011|2012 e espremendo o calendário em poucos pixels.
    fig.update_yaxes(type='category', dtick=1)
    return fig


def export_table(series: pd.DataFrame, coverage: pd.DataFrame,
                 region_wkt: str | None, dataset: str) -> pd.DataFrame:
    result = series.rename(columns={'ano': 'year', 'mes': 'month', 'focos': 'hotspots',
                                    'incompleto': 'incomplete'}).copy()
    result['anomaly_pct'] = anomaly_values(series)
    result['dataset'] = dataset
    result['region_wkt'] = region_wkt or 'Brazil (entire dataset)'
    return result[['year', 'month', 'hotspots', 'anomaly_pct', 'incomplete', 'dataset', 'region_wkt']]












def show_how_it_works(first_year: int, last_year: int) -> None:
    """Plain-language explanation of the project for people with no science background."""
    st.subheader('How EMBER works, in simple words')
    st.markdown(
        '#### 1. Satellites look for heat\n'
        'NASA satellites pass over Brazil several times a day. They measure the heat coming from the ground. '
        'When a small piece of land is much hotter than the land around it, the satellite marks it as a '
        '**hot spot**. It can indicate active burning; a detection is not a confirmed separate fire.\n\n'
        f'#### 2. One single record, from {first_year} to {last_year}\n'
        'Over the years NASA has watched fires with different instruments, and each one counted them in its own way. '
        'EMBER joins all of them into **one single, unified record**, measured with the same ruler in every year. '
        'The ruler was built for monthly activity in regions, so months and large areas are the most reliable.\n\n'
        '#### 3. How the records were joined\n'
        'For ten years (2012–2021) the instruments observed overlapping regions and periods. '
        'We used those years to learn, for each region of Brazil and each month, how their counts relate, '
        'and put every year on one common scale. '
        'It is like converting old prices into today\'s money: comparing years becomes fair. '
        'Daily values before 2012 are approximate, so look at weeks, months and years for steadier answers.\n\n'
        '#### 4. How good is it?\n'
        'We tested it by hiding one year at a time and checking if we could "guess" it from the others:\n'
        '- For all of Brazil, the yearly total is off by only about **2%**.\n'
        '- For a large region (about 200 km wide) in one year, **9 out of 10** guesses are within 20%.\n'
        '- For a large region in one single month it is harder: **2 out of 3** are within 20%.\n\n'
        '#### 5. What you can do with EMBER\n'
        '- **Explore recorded heat detections** on the Map tab, on available dates since 2001.\n'
        '- **Draw a box** on the map, or **type a place** (latitude and longitude), and list or download its hot spots.\n'
        '- **Find its fire season**: which months burn most, and when to get ready.\n'
        '- **Compare years**: is this year worse or better than normal?\n\n'
        '#### 6. Good to know\n'
        '- A hot spot shows **where** there is heat, not **how big** the fire is or how much land burned.\n'
        '- Clouds and smoke can hide fires from the satellites.\n'
        '- The most recent month may still be missing some days.\n'
        '- "Heat strength" compares a hot spot with the others in the record; it does not tell how big the fire is.\n'
        '- Each dot on the map is a place where heat was really seen.')
    with st.expander('Scientific limits and validation details'):
        st.markdown('The conversion targets **monthly regional counts**, not physical fire intensity. '
                    'Before 2012, exact-day weights are approximate and do not have a calibrated daily confidence interval.\n\n'
                    '**Final-method cell-scale evaluation (0.25°, leave-one-year-out, 2012–2021):** '
                    'monthly correlation **0.959**; exact peak-month accuracy **73.7%**, '
                    '**90.4%** within ±1 month. '
                    'For small areas interpret the peak within ±1 month; larger regions and annual totals are more reliable.\n\n'
                    'The 66% monthly and 92% annual figures above refer to agreement within ±20% '
                    'at the 2° regional scale (about 200 km).\n\n'
                    '**Natural limit:** no conversion can reach 100% month by month. Two identical satellites of the '
                    'same kind, flying at the same time, agree within ±20% in only **85%** of months, because they pass '
                    'at different times and clouds and short fires change between passes. So 85% is the practical '
                    'ceiling, and the converted record reaches 66% of months against it.\n\n'
                    '[Full methodology](https://github.com/vagnermelo20/NasaAppChallenge/blob/main/docs/metodologia.md) · '
                    '[Reported metrics](https://github.com/vagnermelo20/NasaAppChallenge/blob/main/reports/metrics.json)')
    st.caption('Data: NASA FIRMS (Fire Information for Resource Management System). '
               'The full method and its validation are in the project repository.')


@st.cache_data
def timescale_data(scale: str, region_wkt: str | None, day_from: date, day_to: date) -> pd.DataFrame:
    cells = celulas()
    if region_wkt:
        cells = cells[shapely.contains_xy(shapely.from_wkt(region_wkt), cells.lon + .125, cells.lat + .125)]
    with duckdb.connect() as con:
        con.register('sel', cells[['lat', 'lon']])
        if scale == 'Day':
            files = [str(ROOT / f'data/processed/diario/diario_{y}.parquet') for y in range(day_from.year, day_to.year + 1)
                     if (ROOT / f'data/processed/diario/diario_{y}.parquet').exists()]
            if not files:
                return pd.DataFrame()
            return con.execute('SELECT data AS period, fonte, sum(focos) AS hotspots FROM read_parquet(?) d JOIN sel USING (lat, lon) '
                               'WHERE data BETWEEN ? AND ? GROUP BY ALL ORDER BY 1', [files, day_from, day_to]).df()
        return con.execute('SELECT semana AS period, bool_or(semana_incompleta) AS incomplete, sum(focos) AS hotspots '
                           'FROM read_parquet(?) w JOIN sel USING (lat, lon) WHERE semana BETWEEN ? AND ? GROUP BY 1 ORDER BY 1',
                           [str(ROOT / 'data/processed/semanal.parquet'), day_from, day_to]).df()


# ---------------------------------------------------------------------------
# Map tab: one map with the hot spots AND the drawing tool (plan L1/L2)
# ---------------------------------------------------------------------------
DOT_COLOR = '#E8251B'   # one colour for every hot spot
SATELLITE_TILES = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
LABEL_TILES = 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}'
PERIODS = {'Latest day': 1, 'Latest 7 days': 7, 'Latest 30 days': 30, 'Latest 12 months': 365}


@st.cache_data
def newest_point_date(path: str, version: int) -> date:
    with duckdb.connect() as con:
        row = con.execute('SELECT max(data) FROM read_parquet(?)', [path]).fetchone()
    value = row[0] if row else None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError('This point archive contains no valid observation dates.')


def heat_square(day_from: date, day_to: date) -> float:
    """Bigger squares for long periods, so years of data still draw quickly."""
    span = (day_to - day_from).days
    return .05 if span <= 92 else (.1 if span <= 3 * 365 else .2)


@st.cache_data
def map_summary(files: tuple[tuple[str, int], ...], start: date, end: date,
                size: float) -> tuple[float, int, pd.DataFrame]:
    """Any period, on the common (harmonized) scale: each hot spot adds its `peso_harmonizado`
    (VIIRS = 1; an older MODIS hot spot counts for the small fires MODIS could not see).
    Returns (hot spots on the common scale, satellite detections, glow squares)."""
    paths = [p for p, _ in files]
    where = 'FROM read_parquet(?) WHERE data BETWEEN ? AND ?'
    with duckdb.connect() as con:
        common, detections = con.execute('SELECT coalesce(sum(peso_harmonizado), 0), count(*) ' + where,
                                         [paths, start, end]).fetchone() or (0., 0)
        cells = con.execute(f'SELECT round(lat / {size}) * {size} AS lat, round(lon / {size}) * {size} AS lon, '
                            f'sum(peso_harmonizado) AS n {where} GROUP BY 1, 2', [paths, start, end]).df()
    return float(common), int(detections), cells


def heat_top(day_from: date, day_to: date, size: float) -> float:
    """Fixed ruler for the glow: full brightness = this many hot spots (common scale) in one square.
    It depends only on the number of days and the square size, never on the satellite, so the same
    dates in 2005 and in 2024 glow on the same scale (in September, 95% of 0.05° squares stay
    under about 2 hot spots per day in both years)."""
    days = (day_to - day_from).days + 1
    per_day = 2.0 if days <= 31 else (.5 if days <= 366 else .3)
    return per_day * days * (size / .05)


def view_box(bounds: dict | None, step: float = .05) -> tuple[float, float, float, float] | None:
    """Leaflet bounds -> (south, west, north, east), rounded outward so small pans reuse the cache."""
    if not bounds:
        return None
    try:
        sw, ne = bounds['_southWest'], bounds['_northEast']
        return (math.floor(sw['lat'] / step) * step, math.floor(sw['lng'] / step) * step,
                math.ceil(ne['lat'] / step) * step, math.ceil(ne['lng'] / step) * step)
    except (KeyError, TypeError):
        return None


@st.cache_data
def dots_in_view(files: tuple[tuple[str, int], ...], start: date, end: date,
                 box: tuple[float, float, float, float]) -> tuple[int, pd.DataFrame]:
    """How many hot spots are in the part of the map on screen; ALL of them when they fit, none otherwise."""
    south, west, north, east = box
    where = 'FROM read_parquet(?) WHERE data BETWEEN ? AND ? AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?'
    args = [[p for p, _ in files], start, end, south, north, west, east]
    with duckdb.connect() as con:
        count_row = con.execute('SELECT count(*) ' + where, args).fetchone()
        count = int(count_row[0]) if count_row else 0
        if count > MAX_MAP_POINTS:
            return count, pd.DataFrame(columns=['lat', 'lon', 'data', 'hora_utc', 'satelite'])
        dots = con.execute('SELECT lat, lon, data, hora_utc, satelite, frp ' + where + ' ORDER BY data, hora_utc', args).df()
    return count, dots


POPUP_JS = """
function (feature, layer) {
    layer.bindPopup(function () {
        var p = feature.properties;
        var html = '<div style="font:13px/1.45 sans-serif;min-width:220px">'
            + '<b>When:</b> ' + p.t + ' (Brasília time)';
        if (p.p !== undefined && p.p !== null) html += '<br><b>Heat strength:</b> stronger than ' + p.p + '% of the hot spots in Brazil';
        return html + '</div>';
    });
}
"""


def add_hotspot_locations(view, points: pd.DataFrame) -> None:
    """One small red dot per hot spot. Clicking it shows when it was seen and how strong the heat was."""
    if points.empty:
        return
    hours = points.hora_utc.astype(int)
    when = (pd.to_datetime(points.data) + pd.to_timedelta(hours // 100, unit='h')
            + pd.to_timedelta(hours % 100, unit='m') - pd.Timedelta(hours=3))
    pct = points.frp_pct if 'frp_pct' in points.columns else pd.Series(np.nan, index=points.index)
    features = [{'type': 'Feature',
                 'properties': {'t': f'{moment:%d %b %Y, %H:%M}', 'p': int(q) if pd.notna(q) else None},
                 'geometry': {'type': 'Point', 'coordinates': [round(float(lon), 4), round(float(lat), 4)]}}
                for lat, lon, moment, q in zip(points.lat, points.lon, when, pct)]
    folium.GeoJson({'type': 'FeatureCollection', 'features': features}, name='Hot spots',
                   marker=folium.CircleMarker(radius=3.5, stroke=True, color='#2B0A00', weight=.6,
                                              fill=True, fill_color=DOT_COLOR, fill_opacity=.95),
                   on_each_feature=JsCode(POPUP_JS)).add_to(view)


@st.cache_data(max_entries=2)
def frp_percentiles(paths: tuple[str, ...], versions: tuple[int, ...] = ()) -> dict[str, np.ndarray]:
    """For each satellite: the heat strength (FRP) at 0%, 1%, ..., 100% of its hot spots in Brazil."""
    steps = [i / 100 for i in range(101)]
    with duckdb.connect() as con:
        # Approximate reference percentiles from a reproducible 10% block sample.
        rows = con.execute('SELECT satelite, quantile_cont(frp, ?) FROM (SELECT satelite, frp FROM read_parquet(?) '
                           'USING SAMPLE 10% (system, 42)) GROUP BY 1', [steps, list(paths)]).fetchall()
    return {sat: np.array(values, dtype=float) for sat, values in rows}


def with_heat_rank(points: pd.DataFrame) -> pd.DataFrame:
    """Adds 'stronger than X% of the hot spots in Brazil'. The percentile is taken within each instrument's own
    record, so the heat strength is comparable across the whole unified series."""
    files = tuple(str(f) for f in sorted((ROOT / 'data/processed/focos').glob('focos_*.parquet')))
    if points.empty or 'frp' not in points.columns or not files:
        return points
    table = frp_percentiles(files, tuple(Path(path).stat().st_mtime_ns for path in files))
    ranks = [int(np.searchsorted(table[s], f, side='right') - 1) if s in table and pd.notna(f) else None
             for s, f in zip(points.satelite, points.frp)]
    return points.assign(frp_pct=pd.Series(ranks, index=points.index, dtype='float').clip(0, 99))


def map_legend() -> str:
    return (f'<div style="font-size:.95rem">From far away, glowing areas show where hot spots are. Zoom in to a smaller '
            f'area to see every one as a dot <span style="color:{DOT_COLOR};font-size:1.3em">●</span> and click it. '
            'The glow represents grouped activity, not fire size or severity.</div>')


def unified_notice() -> str:
    """Big plain notice: the red dots are raw detections; everything else is the unified record."""
    return (f'<div style="font-size:1.25rem;font-weight:700;color:#000;line-height:1.4;margin:.4rem 0 .6rem">'
            f'The red dots <span style="color:{DOT_COLOR}">●</span> on this map are the raw satellite detections, '
            'exactly as each satellite saw them (not unified). '
            'Everything else on this page (the glow, the totals, the calendar and every chart) '
            'uses EMBER\'s single unified record.</div>')


def start_end_dates(key: str, start: date, end: date, newest: date) -> tuple[date, date]:
    """Two separate boxes: the first day and the last day (any days from 2001 to the newest data)."""
    with st.container(horizontal=True):
        first = st.date_input('Start date', start, min_value=date(2001, 1, 1), max_value=newest, key=f'{key}_start')
        last = st.date_input('End date', end, min_value=date(2001, 1, 1), max_value=newest, key=f'{key}_end')
    if last < first:
        st.caption('The end date was before the start date, so they were swapped.')
        first, last = last, first
    return first, last


def chosen_period(newest: date) -> tuple[date, date]:
    choice = st.segmented_control('Show hot spots from', [*PERIODS, 'Pick dates'], default='Latest 7 days',
                                  required=True, key='map_period')
    if choice != 'Pick dates':
        return newest - timedelta(days=PERIODS[choice] - 1), newest
    return start_end_dates('map_dates', date(2001, 1, 1), newest, newest)


def place_form() -> None:
    """Second way to choose the area: type a place instead of drawing it."""
    with st.expander('Or type a place: latitude, longitude and distance around it'):
        with st.form('place_form', border=False):
            with st.container(horizontal=True):
                lat = st.number_input('Latitude', -34., 6., -15.79, .01, format='%.4f', key='place_lat')
                lon = st.number_input('Longitude', -74., -34., -47.88, .01, format='%.4f', key='place_lon')
                radius = st.number_input('Distance around it (km)', 1., 500., 50., 5., key='place_radius')
            st.caption('Tip: in Google Maps, right-click a place to copy its latitude and longitude.')
            if st.form_submit_button('Show this place', type='primary', icon=':material/my_location:', key='place_submit'):
                st.session_state['regiao'] = radius_polygon(lat, lon, radius).wkt
                st.session_state['draft_region'] = st.session_state['regiao']
                st.session_state['region_label'] = f'{radius:g} km around {lat:.4f}, {lon:.4f}'
                st.session_state['map_revision'] += 1
                st.session_state.pop('last_map_event', None)
                st.rerun()


def area_hotspots_table(files: tuple[tuple[str, int], ...], day_from: date, day_to: date, region: str | None) -> None:
    """Every hot spot inside the area, for the dates chosen above the map (no cap)."""
    st.markdown('#### Hot spots in your area on these dates')
    if region is None:
        st.caption('Draw an area or type a place to list its hot spots one by one and download them.')
        return
    if not files:
        st.caption('No hot spot files for these dates.')
        return
    with st.spinner('Listing hot spots…'):
        points = with_heat_rank(area_points(files, day_from, day_to, region))
    if points.empty:
        st.info('No hot spots were recorded in this area on these dates. Clouds can hide fires, so this does not '
                'prove there was no fire.')
        return
    st.caption(f'**{points.peso_harmonizado.sum():,.0f} hot spots** inside your area from '
               f'{day_from:%d %b %Y} to {day_to:%d %b %Y}. Each row below is a place and time where heat was seen. '
               'Change the dates above the map to list other days.')
    st.dataframe(search_table(points), hide_index=True, alt='Hot spots inside the chosen area.', height=300,
                 column_config={'When (Brasília time)': st.column_config.DatetimeColumn(format='DD MMM YYYY, HH:mm')})
    # The CSV is only built when the button is clicked: millions of rows would slow every rerun otherwise.
    st.download_button('Download all these hot spots (CSV)',
                       lambda: point_export(points).to_csv(index=False).encode('utf-8-sig'),
                       f'ember_hotspots_{day_from}_{day_to}.csv', 'text/csv', key='area_points_csv', on_click='ignore',
                       icon=':material/download:')


@st.fragment
def area_map() -> None:
    """Draft drawings rerun only this map; the page below changes after 'Show fire history for this area'."""
    files = sorted((ROOT / 'data/processed/focos').glob('focos_*.parquet'))
    if not files:
        st.info('The hot spot files are not available.')
        return
    newest = newest_point_date(str(files[-1]), files[-1].stat().st_mtime_ns)
    st.caption(f'Latest recorded detection in this archive: {newest:%d %b %Y}. This is not a live emergency feed.')
    day_from, day_to = chosen_period(newest)
    region = st.session_state['regiao']
    try:
        with st.spinner('Loading hot spots…'):
            files = point_files(day_from, day_to)
            common, total, cells = map_summary(files, day_from, day_to, heat_square(day_from, day_to))
    except (ValueError, duckdb.Error) as error:
        st.error(f'The selected observations could not be loaded: {error}')
        return
    view = folium.Map(location=[-14, -52], zoom_start=4, tiles=None, prefer_canvas=True,
                      control_scale=True, zoom_control='topright')
    folium.TileLayer(tiles=SATELLITE_TILES, attr='Imagery &copy; Esri, Vantor, Earthstar Geographics',
                     name='Satellite', max_zoom=18, max_native_zoom=16).add_to(view)
    folium.TileLayer(tiles=LABEL_TILES, attr='Labels &copy; Esri', name='Places', overlay=True,
                     control=False, max_zoom=18, max_native_zoom=16).add_to(view)
    view.default_js = [item for item in view.default_js if item[0] == 'leaflet']
    view.default_css = [item for item in view.default_css if item[0] == 'leaflet_css']
    editable = folium.FeatureGroup(name='Your area').add_to(view)
    if region:
        geometry = shapely.from_wkt(region)
        for part in (list(geometry.geoms) if geometry.geom_type == 'MultiPolygon' else [geometry]):
            folium.Polygon(locations=[[(y, x) for x, y in ring.coords] for ring in [part.exterior, *part.interiors]],
                           color='#4FC3F7', weight=3, fill_opacity=.08).add_to(editable)
        west, south, east, north = geometry.bounds
        view.fit_bounds([[south, west], [north, east]])
    Draw(feature_group=editable, position='topleft', show_geometry_on_click=False, draw_options={
        'polyline': False, 'circle': False, 'circlemarker': False, 'marker': False,
        'rectangle': {'shapeOptions': {'color': '#4FC3F7'}},
        'polygon': {'allowIntersection': False, 'shapeOptions': {'color': '#4FC3F7'}}}).add_to(view)
    square = heat_square(day_from, day_to)
    add_heat(view, cells, square, heat_top(day_from, day_to, square))
    with st.container(horizontal=True, vertical_alignment='center'):
        st.html(unified_notice())
        st.html(map_legend())
        start_format = '%d %b' if day_from.year == day_to.year else '%d %b %Y'
        period = (day_to.strftime('%d %b %Y') if day_from == day_to
                  else f'{day_from.strftime(start_format)} – {day_to:%d %b %Y}')
        st.caption(f'**{common:,.0f} hot spots** · {period}',
                   help='Counted on EMBER\'s single common scale, the same for every year since 2001.')
    if total == 0:
        st.caption('No hot spots in these days. This can also mean no satellite data, not only no fire.')
    # Dots: only for the part of the map on screen, and only when zoomed in. Then ALL of them are drawn,
    # without redrawing the whole map (streamlit-folium updates just this layer).
    map_key = f"area_map_{st.session_state['map_revision']}_{day_from}_{day_to}"
    last = st.session_state.get(map_key) or {}
    dots = folium.FeatureGroup(name='Hot spots')
    box = view_box(last.get('bounds')) if (last.get('zoom') or 0) >= HEAT_ZOOM else None
    if total and box and files:
        in_view, points = dots_in_view(files, day_from, day_to, box)
        if in_view <= MAX_MAP_POINTS:
            add_hotspot_locations(dots, with_heat_rank(points))
            st.caption(f'All {in_view:,} hot spot locations in this part of the map are shown as dots. '
                       'Click one to see when it was seen and how strong the heat was.')
        else:
            st.caption(f'{in_view:,} hot spot locations in this part of the map: too many to draw one by one. '
                       'Zoom in more (or pick fewer days) to see every dot.')
    elif total:
        st.caption('Zoom in on the map to see each hot spot as a dot.')
    output = st_folium(view, height=560, use_container_width=True, returned_objects=['all_drawings', 'bounds', 'zoom'],
                       feature_group_to_add=dots, key=map_key)
    valid = True
    if output and output.get('all_drawings') is not None:
        event = json.dumps(output['all_drawings'], sort_keys=True)
        if event != st.session_state.get('last_map_event'):
            try:
                st.session_state['draft_region'] = drawn_region(output)
                st.session_state['last_map_event'] = event
            except (ValueError, KeyError, shapely.GEOSException) as error:
                st.error(str(error))
                valid = False
    pending = st.session_state.get('draft_region', region) != region
    with st.container(horizontal=True, vertical_alignment='center'):
        if st.button('Show fire history for this area', key='apply_map', type='primary',
                     icon=':material/search:', disabled=not (valid and pending)):
            st.session_state['regiao'] = st.session_state.get('draft_region')
            st.session_state['region_label'] = 'Your area' if st.session_state['regiao'] else 'All of Brazil'
            st.rerun()
        if st.button('Clear area', key='reset_region', icon=':material/close:', disabled=region is None and not pending):
            for key, value in [('regiao', None), ('draft_region', None), ('region_label', 'All of Brazil')]:
                st.session_state[key] = value
            st.session_state['map_revision'] += 1
            st.session_state.pop('last_map_event', None)
            st.rerun()
        if pending:
            st.caption('You drew a new area. Press the button to see its fire history.')
        elif region is None:
            st.caption('To look at one place: click ■ (box) on the left of the map, drag over the place, then press the button. '
                       'Or type its latitude and longitude below.')
        else:
            st.caption(f"{st.session_state['region_label']} is outlined in blue on the map.")
    place_form()
    area_hotspots_table(files, day_from, day_to, st.session_state['regiao'])


# ---------------------------------------------------------------------------
# "Your area" in plain sentences (plan L3)
# ---------------------------------------------------------------------------
def season_months(medians: pd.Series) -> list[int]:
    """Months whose typical (median) activity is at least half of the peak month."""
    if medians.empty or medians.max() <= 0:
        return []
    return [int(m) for m in medians.index if medians[m] >= 0.5 * medians.max()]


def season_text(season: list[int]) -> tuple[str, int]:
    """'Aug to Oct' when the months follow each other (also across New Year); also returns the first month."""
    first = season[0]
    gaps = [m for m in range(1, 13) if m not in season]
    if 1 in season and 12 in season and gaps:
        first = (max(gaps) % 12) + 1
    ordered = [m for m in (((first - 1 + i) % 12) + 1 for i in range(12)) if m in season]
    if len(ordered) == 1:
        return MONTHS[ordered[0] - 1], first
    if all((a % 12) + 1 == b for a, b in zip(ordered, ordered[1:])):
        return f'{MONTHS[ordered[0] - 1]} to {MONTHS[ordered[-1] - 1]}', first
    return ', '.join(MONTHS[m - 1] for m in ordered), first


LEVEL_WORDS = {'Critical': 'much more than usual', 'Above normal': 'more than usual', 'Normal': 'about the usual',
               'Below normal': 'less than usual'}


def area_sentences(series: pd.DataFrame) -> list[str]:
    """Plain-language summary computed only from the data (no generative AI)."""
    complete = series[~series.incompleto & series.focos.notna()]
    if complete.empty or complete.focos.sum() == 0:
        return []
    medians = complete.groupby('mes').focos.median()
    peak = int(medians.idxmax())
    season, first = season_text(season_months(medians))
    yearly = complete.groupby('ano').focos.sum()
    lines = [f'**Fire season:** {season}. The worst month is usually **{MONTHS[peak - 1]}**.',
             f'**Best time to get ready:** {MONTHS[(first - 3) % 12]} and {MONTHS[(first - 2) % 12]}, '
             'the two months before the season starts.',
             f'**Worst year:** {int(yearly.idxmax())}, with {yearly.max():,.0f} hot spots.']
    latest = latest_comparison(series)
    if latest and latest['category'] in LEVEL_WORDS:
        lines.append(f"**Last full month ({MONTHS[latest['month'] - 1]} {latest['year']}):** "
                     f"{latest['value']:,.0f} hot spots, **{LEVEL_WORDS[latest['category']]}** "
                     f"(a usual {MONTHS[latest['month'] - 1]} has about {latest['median']:,.0f}).")
    return lines


def annual_figure(series: pd.DataFrame):
    annual = series.groupby('ano').agg(total=('focos', lambda x: x.sum(min_count=1)),
                                       incomplete=('incompleto', 'any')).reset_index()
    fig = go.Figure(go.Bar(x=annual.ano, y=annual.total,
                           marker_color=['#F4A582' if flag else '#D6604D' for flag in annual.incomplete],
                           hovertemplate='%{x}: %{y:,.0f} hot spots<extra></extra>'))
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), xaxis_title=None,
                      yaxis_title='Hot spots per year')
    return fig


# ---------------------------------------------------------------------------
# Far away: glowing orange/yellow areas. Close up: one dot per hot spot.
# ---------------------------------------------------------------------------
HEAT_ZOOM = 7   # from this zoom level on, the hot spots on screen are loaded as dots (all of them, when they fit)


class HeatToggle(MacroElement):
    """Hides the glow while dots are on the map and brings it back when they leave (runs in the browser)."""
    _template = Template('''
        {% macro script(this, kwargs) %}
        (function () {
            var map = {{ this._parent.get_name() }}, heat = {{ this.heat }}, timer = null;
            function hasDots() {
                var found = false;
                map.eachLayer(function (layer) { if (!found && layer instanceof L.CircleMarker) { found = true; } });
                return found;
            }
            function resize() {   // keep the glow smooth: the squares never show as a grid when zooming in
                var spacing = {{ this.size }} * 256 * Math.pow(2, map.getZoom()) / 360;
                var radius = Math.min(Math.max(9, spacing * 1.3), 60);
                heat.setOptions({radius: radius, blur: radius * 1.2});
            }
            function update() {
                clearTimeout(timer);
                timer = setTimeout(function () {
                    if (map.getZoom() >= {{ this.zoom }} && hasDots()) { if (map.hasLayer(heat)) map.removeLayer(heat); }
                    else if (!map.hasLayer(heat)) { map.addLayer(heat); }
                }, 60);
            }
            map.on('layeradd layerremove zoomend', update);
            map.on('zoomend', resize);
            resize();
            update();
        })();
        {% endmacro %}''')

    def __init__(self, heat, zoom: int = HEAT_ZOOM, size: float = .05):
        super().__init__()
        self._name = 'HeatToggle'
        self.heat, self.zoom, self.size = heat.get_name(), zoom, size


def heat_cells(cells: pd.DataFrame, top: float | None = None) -> list[list[float]]:
    """Hot spots already grouped in small squares (lat, lon, n) -> weights for the zoomed-out glow.
    With `top` the ruler is fixed (comparable between years); without it, it follows the data shown."""
    if cells.empty:
        return []
    top = top if top else max(float(cells.n.quantile(.95)), 1.)
    return [[round(float(lat), 3), round(float(lon), 3), round(min(float(n) / top, 1.), 3)]
            for lat, lon, n in cells[['lat', 'lon', 'n']].itertuples(index=False, name=None)]


def add_heat(view: folium.Map, cells: pd.DataFrame, size: float = .05, top: float | None = None) -> None:
    heat = HeatMap(heat_cells(cells, top), name='Hot spot areas', radius=9, blur=11, min_opacity=.3,
                   gradient={'0.2': '#B22200', '0.45': '#FF6A00', '0.7': '#FFA500', '1': '#FFE14D'})
    heat.add_to(view)
    HeatToggle(heat, size=size).add_to(view)


# ---------------------------------------------------------------------------
# Everything about the drawn area, on the Map tab
# ---------------------------------------------------------------------------
def show_timescales(series: pd.DataFrame, region_wkt: str | None) -> None:
    st.markdown('#### Day, week or month')
    scale = st.segmented_control('See hot spots per', ['Day', 'Week', 'Month'], default='Week', required=True,
                                 key='timescale')
    newest = date.today() - timedelta(days=1)
    if scale == 'Month' or not (ROOT / 'data/processed/semanal.parquet').exists():
        data = series.assign(period=pd.to_datetime(dict(year=series.ano, month=series.mes, day=np.ones(len(series), dtype=int))))
        fig = px.bar(data, x='period', y='focos', color_discrete_sequence=['#F46D43'])
        note = 'Hot spots per month (the same numbers as the calendar).'
    else:
        span = 90 if scale == 'Day' else 730
        picked = start_end_dates(f'timescale_{scale}', newest - timedelta(days=span), newest, newest)
        data = timescale_data(scale, region_wkt, picked[0], picked[1])
        if data.empty:
            st.info('No hot spots in this area and these dates.')
            return
        if scale == 'Day':
            # One harmonized series: all satellites already joined on EMBER's single common scale.
            data = data.groupby('period', as_index=False).hotspots.sum()
            fig = px.bar(data, x='period', y='hotspots', color_discrete_sequence=['#F46D43'])
            note = ('Hot spots per day on EMBER\'s single common scale, the same one used for every year. '
                    'Before 2012 these daily estimates are approximate: the conversion was calibrated monthly, '
                    'not for exact-day comparisons. '
                    'Days with no satellite data are left empty (that is not the same as no fire). '
                    'One day can change a lot because of clouds; weeks and months are steadier.')
        else:
            data['status'] = np.where(data.incomplete, 'A satellite day is missing', 'All days seen')
            fig = px.bar(data, x='period', y='hotspots', color='status',
                         color_discrete_map={'All days seen': '#F46D43', 'A satellite day is missing': '#9AA5B1'})
            note = 'Hot spots per week (weeks start on Monday). Grey bars: at least one day had no satellite data.'
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), xaxis_title=None, yaxis_title='Hot spots',
                      legend_title_text=None)
    st.plotly_chart(fig, key='timescale_chart', width='stretch', config={'displaylogo': False})
    st.caption(note)


def seasonality_figure(series: pd.DataFrame):
    complete = series[~series.incompleto & series.focos.notna()]
    typical = complete.groupby('mes').focos.median().reindex(range(1, 13))
    fig = go.Figure(go.Bar(x=MONTHS, y=typical.to_numpy(), marker_color='#F46D43',
                           hovertemplate='%{x}: about %{y:,.0f} hot spots<extra></extra>'))
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), yaxis_title='Hot spots in a usual month')
    return fig


def show_last_month(series: pd.DataFrame) -> None:
    summary = latest_comparison(series)
    if not summary:
        return
    year, month = summary['year'], summary['month']
    st.markdown(f'#### Was {MONTHS[month - 1]} {year} worse than usual?')
    same = series[(series.mes == month) & series.focos.notna()].sort_values('ano')
    fig = go.Figure(go.Bar(x=same.ano, y=same.focos,
                           marker_color=['#D7191C' if y == year else '#4A90C2' for y in same.ano],
                           hovertemplate='%{x}: %{y:,.0f} hot spots<extra></extra>'))
    if pd.notna(summary['median']):
        fig.add_hline(y=float(summary['median']), line_dash='dash', annotation_text='usual')
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), yaxis_title=f'Hot spots in {MONTHS[month - 1]}')
    st.plotly_chart(fig, key='last_month_chart', width='stretch', config={'displaylogo': False})
    note = (f'The red bar is {MONTHS[month - 1]} {year}; the dashed line is a usual {MONTHS[month - 1]} '
            '(the middle value of the earlier years).')
    if summary['newer_incomplete']:
        note += ' Newer months (' + ', '.join(summary['newer_incomplete']) + ') are not over or miss satellite days, so they are left out.'
    st.caption(note)


def show_your_area(coverage: pd.DataFrame, first_year: int, last_year: int, is_mock: bool) -> None:
    region = st.session_state['regiao']
    st.markdown('### ' + ('Your area' if region else 'All of Brazil'))
    if region is None:
        st.caption('These numbers are for the whole country. Draw an area on the map to see one place.')
    series = serie_regiao(region, first_year, last_year)
    cells = celulas()
    selected = (int(shapely.contains_xy(shapely.from_wkt(region), cells.lon + .125, cells.lat + .125).sum())
                if region else len(cells))
    if selected == 0:
        st.warning('Your area is too small for the fire history. Draw a bigger box (at least about 30 km wide).')
        return
    lines = area_sentences(series)
    if not lines:
        st.info(f'No hot spots were seen in this area from {first_year} to {last_year}.')
        return
    with st.container(border=True):
        st.markdown('\n'.join(f'- {line}' for line in lines))
        note = f'From {last_year - first_year + 1} years of NASA satellite data.'
        if selected < 64:
            note += ' This is a small area, so read the months as approximate (give or take one month).'
        st.caption(note)
    st.markdown('#### Fire calendar')
    compare = st.toggle('Compare each month with a usual year (%)', value=False, key='anomaly_mode',
                        help='Red = more hot spots than the same month usually has; blue = fewer.')
    st.caption(('Red = more than usual for that month, blue = less. ' if compare else
                'Each row is a year, each column is a month. **Blue = few hot spots, red = many.** ')
               + 'A star (*) means some satellite days are missing that month.')
    st.plotly_chart(calendar_figure(series, anomaly=compare, show_values=False), key='calendar', width='stretch',
                    config={'displaylogo': False}, alt='Hot spots per month and year in the selected area.')
    show_timescales(series, region)
    st.markdown('#### A usual year here')
    st.plotly_chart(seasonality_figure(series), key='seasonality', width='stretch', config={'displaylogo': False},
                    alt='Hot spots in a usual month, for each month of the year.')
    st.caption('How many hot spots each month usually has (middle value of the complete years).')
    st.markdown('#### Hot spots per year')
    st.plotly_chart(annual_figure(series), key='annual_bars', width='stretch', config={'displaylogo': False},
                    alt='Hot spots per year in the selected area.')
    st.caption('Lighter bars: years with some missing satellite days, or the current year, which is not over yet.')
    show_last_month(series)
    export = export_table(series, coverage, region, 'mock' if is_mock else 'harmonized')
    today = datetime.now(ZoneInfo('America/Fortaleza')).date().isoformat()
    st.download_button('Download these numbers (CSV)', export.to_csv(index=False).encode('utf-8-sig'),
                       f"{'mock_' if is_mock else ''}ember_{'area' if region else 'brazil'}_{today}.csv", 'text/csv',
                       key='download_csv', on_click='ignore', icon=':material/download:')


# ---------------------------------------------------------------------------
# Search tab: hot spots around a latitude/longitude, between two dates
# ---------------------------------------------------------------------------
def radius_polygon(lat: float, lon: float, radius_km: float) -> Polygon:
    """Spherical circle accounts for longitude scale at different latitudes."""
    phi, lam = math.radians(lat), math.radians(lon)
    delta = radius_km / 6371.0088
    points = []
    for angle in range(0, 361, 5):
        bearing = math.radians(angle)
        p = math.asin(math.sin(phi) * math.cos(delta)
                      + math.cos(phi) * math.sin(delta) * math.cos(bearing))
        l = lam + math.atan2(math.sin(bearing) * math.sin(delta) * math.cos(phi),
                            math.cos(delta) - math.sin(phi) * math.sin(p))
        points.append((math.degrees(l), math.degrees(p)))
    return Polygon(points)


def search_table(points: pd.DataFrame) -> pd.DataFrame:
    hours = points.hora_utc.astype(int)
    when = (pd.to_datetime(points.data) + pd.to_timedelta(hours // 100, unit='h')
            + pd.to_timedelta(hours % 100, unit='m') - pd.Timedelta(hours=3))
    table = pd.DataFrame({'When (Brasília time)': when,          # kept as a date-time: fast even for millions of rows
                          'Latitude': points.lat.round(4), 'Longitude': points.lon.round(4)})
    if 'frp_pct' in points.columns:
        table['Heat strength (stronger than % of hot spots)'] = points.frp_pct
    return table




def show_about(coverage: pd.DataFrame) -> None:
    last = coverage.iloc[-1]
    st.markdown('**About EMBER.** A NASA Space Apps 2026 prototype. The archive ends in '
                f'{MONTHS[int(last.mes) - 1]} {int(last.ano)}; it is not a real-time emergency alert system. '
                '[NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) · '
                '[Project repository](https://github.com/vagnermelo20/NasaAppChallenge)')


def main() -> None:
    st.set_page_config(page_title='EMBER · Where and when Brazil burns', page_icon=':material/local_fire_department:',
                       layout='wide', initial_sidebar_state='collapsed')
    if not REAL.exists() and not MOCK.exists():
        st.warning('Generate the local development dataset to open the app.')
        st.code('.venv/Scripts/python.exe app/make_mock.py', language='bash')
        st.stop()
    path, version = data_source()
    try:
        coverage = metadata(path, version)
        if coverage.empty:
            raise ValueError('The dataset has no observations.')
    except (duckdb.Error, ValueError) as error:
        st.error(f'Unable to open the app: {error}')
        st.stop()
    first_year, last_year = int(coverage.ano.min()), int(coverage.ano.max())
    is_mock = Path(path) == MOCK
    for key, value in [('regiao', None), ('region_label', 'All of Brazil'), ('map_revision', 0)]:
        st.session_state.setdefault(key, value)
    st.markdown('## :material/local_fire_department: EMBER · Where and when does Brazil burn?')
    last = coverage.iloc[-1]
    st.caption('Each dot is a recorded **hot spot**: heat seen from space by a NASA satellite. '
               f'Archive: {first_year} to {MONTHS[int(last.mes)-1]} {last_year}. '
               'Monthly counts are adjusted to a common scale; older daily values remain approximate.')
    if is_mock:
        st.warning('Development data (mock), not the real harmonized series.')
    map_tab, how_tab = st.tabs(['Map', 'How it works'], default='Map', key='main_tabs', on_change='rerun')
    with map_tab:
        if map_tab.open:
            area_map()
            show_your_area(coverage, first_year, last_year, is_mock)
    with how_tab:
        if how_tab.open:
            show_how_it_works(first_year, last_year)
            show_about(coverage)
    st.caption('A hot spot shows where there is heat, not how big a fire is or how much land burned.')


if __name__ == '__main__':
    main()
