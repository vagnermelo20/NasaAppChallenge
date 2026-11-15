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
import plotly.express as px
import plotly.graph_objects as go
import shapely
import streamlit as st
from branca.element import MacroElement, Template
from folium.plugins import Draw, HeatMap
from shapely.geometry import Polygon, shape
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / 'data/processed/harmonized.parquet'
MOCK = ROOT / 'data/processed/harmonized_mock.parquet'
MONTHS = list(calendar.month_abbr)[1:]
MAX_MAP_POINTS = 50_000   # above this the browser map becomes slow and unreadable


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


@st.cache_data
def search_hotspots(files: tuple[tuple[str, int], ...], start: date, end: date,
                    sensor: str, region_wkt: str | None, limit: int | None = None,
                    newest_first: bool = False) -> tuple[pd.DataFrame, bool]:
    """All hot spots in the dates and area (no cap unless a limit is given)."""
    if end < start:
        raise ValueError('The end date must be on or after the start date.')
    if not files:
        raise ValueError('No point files are available for this interval.')
    predicates = {'All available sensors': '', 'VIIRS S-NPP': " AND satelite='S-NPP'",
                  'MODIS Terra + Aqua': " AND satelite IN ('Terra','Aqua')"}
    if sensor not in predicates:
        raise ValueError('Unknown satellite sensor.')
    columns = ['lat', 'lon', 'data', 'hora_utc', 'satelite', 'frp', 'daynight', 'peso_harmonizado']
    sql = 'SELECT ' + ','.join(columns) + ' FROM read_parquet(?) WHERE data BETWEEN ? AND ?' + predicates[sensor]
    args: list = [[p for p, _ in files], start, end]
    geometry = shapely.from_wkt(region_wkt) if region_wkt else None
    if geometry is not None:
        west, south, east, north = geometry.bounds
        sql += ' AND lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?'
        args.extend([west, east, south, north])
    order = ' DESC' if newest_first else ''
    with duckdb.connect() as con:
        points = con.execute(sql + f' ORDER BY data{order}, hora_utc{order}, satelite, lat, lon', args).df()
    if geometry is not None and not points.empty:
        points = points[shapely.contains_xy(geometry, points.lon.to_numpy(), points.lat.to_numpy())]
    points = points.reset_index(drop=True)
    if limit is not None and len(points) > limit:
        return points.iloc[:limit].copy(), True
    return points, False


def point_export(points: pd.DataFrame) -> pd.DataFrame:
    result = points.rename(columns={'data': 'date_utc', 'hora_utc': 'time_utc', 'satelite': 'satellite',
                                    'lat': 'latitude', 'lon': 'longitude', 'frp': 'frp_mw',
                                    'peso_harmonizado': 'harmonized_weight'}).copy()
    result['date_utc'] = pd.to_datetime(result.date_utc).dt.strftime('%Y-%m-%d')
    result['time_utc'] = result.time_utc.map(lambda value: f'{int(value)//100:02d}:{int(value)%100:02d}')
    result['record_type'] = 'Observation by sensor'
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
    if 2011 in values.index and 2012 in values.index:
        position = list(values.index).index(2011) + 0.5
        fig.add_hline(y=position, line_dash='dash', line_color='white', line_width=2)
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
    sources = coverage.rename(columns={'ano': 'year', 'mes': 'month'})
    result = result.merge(sources[['year', 'month', 'source']], how='left', on=['year', 'month'])
    fallback = np.where(result.year < 2012, 'modis_convertido', 'viirs')
    result['source'] = result.source.fillna(pd.Series(fallback, index=result.index))
    result.loc[result.hotspots.isna(), 'source'] = 'unavailable'
    result['dataset'] = dataset
    result['region_wkt'] = region_wkt or 'Brazil (entire dataset)'
    return result[['year', 'month', 'hotspots', 'anomaly_pct', 'incomplete', 'source',
                   'dataset', 'region_wkt']]


@st.cache_data
def uncertainty_region_months(harmonized_path: str, harmonized_version: int,
                              grid_path: str, grid_version: int, year: int, month: int) -> pd.DataFrame:
    """Keep uncertainty at the 2° region/month scale used by the science team."""
    with duckdb.connect() as con:
        return con.execute(
            'WITH h AS (SELECT floor(lat/2)*2 AS south, floor(lon/2)*2 AS west, '
            'sum(focos_harmonizados) AS estimate, bool_or(dado_incompleto) AS incomplete '
            'FROM read_parquet(?) WHERE ano=? AND mes=? GROUP BY 1,2), '
            'm AS (SELECT floor(lat/2)*2 AS south, floor(lon/2)*2 AS west, sum(n) AS modis_count '
            "FROM read_parquet(?) WHERE ano=? AND mes=? AND satellite IN ('Terra','Aqua') GROUP BY 1,2) "
            'SELECT h.*, coalesce(m.modis_count,0) AS modis_count FROM h LEFT JOIN m USING(south,west) '
            'WHERE h.estimate>0 ORDER BY h.estimate DESC',
            [harmonized_path, year, month, grid_path, year, month]).df()


def show_monthly_uncertainty(series: pd.DataFrame, region_wkt: str | None) -> None:
    years = sorted(int(year) for year in series.ano.unique() if int(year) < 2012)
    if not years:
        return
    with st.expander('How sure are we about the years before 2012?', key='uncertainty_panel', on_change='rerun') as panel:
        if not panel.open:
            return
        st.caption('Explore the delivered nominal 90% calibration band for a complete 2° region and UTC month. '
                   'It applies to converted MODIS before 2012; it is not a fire forecast or an exact-day interval.')
        grid = ROOT / 'data/processed/grid_sat.parquet'
        metrics = ROOT / 'reports/metrics.json'
        if not REAL.exists() or not grid.exists() or not metrics.exists():
            st.info('The real harmonized series, processed satellite grid and uncertainty metrics are required.')
            return
        try:
            uncertainty = read_metrics(str(metrics), metrics.stat().st_mtime_ns).get(
                'prova_harmonizacao', {}).get('faixa_incerteza', {})
            factors = uncertainty.get('largura_por_focos_modis', [])
            if len(factors) != 5:
                raise ValueError('The five calibrated MODIS count bands have not been supplied.')
            with st.container(horizontal=True):
                year = st.selectbox('Uncertainty year · MODIS', years, index=len(years)-1, key='uncertainty_year')
                month = st.selectbox('Uncertainty month · UTC', list(range(1, 13)),
                                     index=8, format_func=lambda value: MONTHS[value-1], key='uncertainty_month')
            regions = uncertainty_region_months(str(REAL), REAL.stat().st_mtime_ns,
                                                str(grid), grid.stat().st_mtime_ns, year, month)
            if region_wkt and not regions.empty:
                blocks = shapely.box(regions.west.to_numpy(), regions.south.to_numpy(),
                                     regions.west.to_numpy()+2, regions.south.to_numpy()+2)
                regions = regions[shapely.intersects(blocks, shapely.from_wkt(region_wkt))]
            if regions.empty:
                st.info('No converted activity in the available 2° regions for this month and selection.')
                return
            regions = regions.reset_index(drop=True)
            def region_name(index: int) -> str:
                row = regions.iloc[index]
                return f'{row.south:g}° to {row.south+2:g}° latitude · {row.west:g}° to {row.west+2:g}° longitude'
            selected = st.selectbox('Full 2° analysis region', list(regions.index),
                                    format_func=region_name, key='uncertainty_region')
            row = regions.iloc[selected]
            if bool(row.incomplete) or row.modis_count <= 0:
                st.info('No uncertainty band is shown for an incomplete region-month or one without MODIS detections.')
                return
            category = int(np.searchsorted([20, 50, 150, 500], row.modis_count, side='left'))
            lower_factor = float(factors[category]['fator_baixo'])
            upper_factor = float(factors[category]['fator_alto'])
            if not (math.isfinite(lower_factor) and math.isfinite(upper_factor) and 0 <= lower_factor <= upper_factor):
                raise ValueError('Invalid uncertainty factors in the delivered metrics.')
            lower, upper = float(row.estimate) * lower_factor, float(row.estimate) * upper_factor
            with st.container(horizontal=True):
                st.metric('Converted VIIRS-equivalent activity', f'{row.estimate:,.2f}')
                st.metric('Nominal 90% lower bound', f'{lower:,.2f}')
                st.metric('Nominal 90% upper bound', f'{upper:,.2f}')
            st.caption(f'{row.modis_count:,.0f} filtered MODIS detections · factors {lower_factor:g}–{upper_factor:g}. '
                       'The factor band is selected using raw MODIS counts, not the converted estimate.')
            coverage = uncertainty.get('cobertura_90_nominal')
            if isinstance(coverage, (int, float)):
                st.caption(f'Empirical coverage reported by the science team: {coverage*100:.1f}% '
                           'across the calibration cases; this is not a guarantee for an individual region-month.')
            st.info('Bounds describe one full 2° region-month. Regions intersecting your applied area are listed, '
                    'but each region is kept whole. Do not add these bounds across regions or months, '
                    'or apply them to the daily search. Satellite detection uncertainty is not burned-area uncertainty.')
            export = pd.DataFrame([{'year': year, 'month': month, 'south': row.south, 'north': row.south+2,
                                    'west': row.west, 'east': row.west+2, 'modis_detections': row.modis_count,
                                    'viirs_equivalent_estimate': row.estimate, 'lower_90_nominal': lower,
                                    'upper_90_nominal': upper, 'lower_factor': lower_factor,
                                    'upper_factor': upper_factor, 'calibration_scale': '2 degree region / UTC month',
                                    'metrics_source': 'reports/metrics.json', 'dataset': 'harmonized'}])
            st.dataframe(export, hide_index=True, alt='Monthly converted activity and calibrated uncertainty bounds for the selected full 2 degree region.')
            st.download_button('Download monthly uncertainty CSV', export.to_csv(index=False).encode('utf-8-sig'),
                               f'uncertainty_2deg_{year}-{month:02d}_{row.south:g}_{row.west:g}.csv',
                               'text/csv', key='uncertainty_csv', on_click='ignore')
        except (OSError, duckdb.Error, ValueError, KeyError, TypeError) as error:
            st.warning(f'The monthly uncertainty explorer is unavailable: {error}')


@st.cache_data
def read_metrics(path: str, version: int) -> dict:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Metrics must be a JSON object.')
    return data


@st.cache_data
def raw_vs_harmonized(grid_path: str, version: int, region_wkt: str | None, start: int, end: int) -> pd.DataFrame:
    """Annual totals if MODIS and VIIRS were simply put side by side (raw) - the problem the project solves."""
    with duckdb.connect() as con:
        g = con.execute("SELECT lat, lon, ano, satellite, sum(n) n FROM read_parquet(?) WHERE ano BETWEEN ? AND ? "
                        "GROUP BY ALL", [grid_path, start, end]).df()
    if region_wkt:
        g = g[shapely.contains_xy(shapely.from_wkt(region_wkt), g.lon + .125, g.lat + .125)]
    raw = g[((g.ano < 2012) & g.satellite.isin(['Terra', 'Aqua'])) | ((g.ano >= 2012) & (g.satellite == 'S-NPP'))]
    return raw.groupby('ano').n.sum().rename('raw').reset_index()


def show_harmonization_demo(series: pd.DataFrame, region_wkt: str | None, start: int, end: int,
                            key: str = 'harmonization_demo') -> None:
    grid = ROOT / 'data/processed/grid_sat.parquet'
    if not grid.exists() or start >= 2012 or end < 2012:
        return
    choice = st.segmented_control('Why harmonization matters', ['Without harmonization', 'With harmonization'],
                                  default='With harmonization', required=True, key=key)
    raw = raw_vs_harmonized(str(grid), grid.stat().st_mtime_ns, region_wkt, start, end)
    harm = series.groupby('ano').focos.sum().rename('harmonized').reset_index()
    data = harm.merge(raw, on='ano', how='left')
    column = 'raw' if choice == 'Without harmonization' else 'harmonized'
    fig = go.Figure(go.Bar(x=data.ano, y=data[column],
                           marker_color=['#9AA5B1' if a < 2012 else '#F28E2B' for a in data.ano]))
    fig.add_vline(x=2011.5, line_dash='dash', line_color='white')
    fig.add_annotation(x=2011.5, y=1, yref='paper', text='MODIS | VIIRS', showarrow=False, yanchor='bottom')
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=30, b=10), yaxis_title='Hotspots per year',
                      title='Raw counts: the jump in 2012 is the sensor change, not more fire' if column == 'raw'
                      else 'Harmonized: all years on one scale, so they can be compared')
    st.plotly_chart(fig, key=f'{key}_chart', width='stretch')
    st.caption('Grey = MODIS years (2001–2011), orange = VIIRS years (2012 on). '
               'VIIRS sees about 4× more hotspots than MODIS for the same fires, so raw counts cannot be compared across 2012.')


def show_how_it_works(first_year: int, last_year: int) -> None:
    """Plain-language explanation of the project for people with no science background."""
    st.subheader('How EMBER works, in simple words')
    st.markdown(
        '#### 1. Satellites look for heat\n'
        'NASA satellites pass over Brazil several times a day. They measure the heat coming from the ground. '
        'When a small piece of land is much hotter than the land around it, the satellite marks it as a '
        '**hot spot**. Almost always, a hot spot is a fire burning at that moment.\n\n'
        '#### 2. An old satellite and a new one\n'
        '- The **old satellites (MODIS)** have watched since 2001. They see the ground in big squares of about 1 km.\n'
        '- The **new satellite (VIIRS)** has watched since 2012. It sees much smaller squares (375 m), '
        'so it also catches small fires the old one misses.\n\n'
        'Because of that, the new satellite counts about **4 times more hot spots** for the same fires.\n\n'
        '#### 3. The problem\n'
        'If you simply put the counts side by side, it looks like fire jumped 4 times in 2012. '
        'That is not true: only the "eye" changed, not the fire. Without a fix, you cannot compare 2005 with 2024.')
    series = serie_regiao(None, first_year, last_year)
    show_harmonization_demo(series, None, first_year, last_year, key='how_it_works_demo')
    st.markdown(
        '#### 4. What we did\n'
        'Between 2012 and 2021 both satellites were working at the same time, over the same fires. '
        'We used those years to learn, for each region of Brazil and each month, '
        '**how many hot spots the new satellite sees for every one the old satellite sees**. '
        'Then we used that number to translate the old years (2001–2011) to the new scale. '
        'It is like converting an old currency into today\'s money: now every year uses the same ruler.\n\n'
        '#### 5. How good is it?\n'
        'We tested it by hiding one year at a time and checking if we could "guess" it from the others:\n'
        '- For all of Brazil, the yearly total is off by only about **2%**.\n'
        '- For one region in one year, **9 out of 10** guesses are within 20%.\n'
        '- For one region in one single month it is harder: **2 out of 3** are within 20%.\n\n'
        '#### 6. What you can do with EMBER\n'
        '- **See where it is burning** on the Map tab, day by day.\n'
        '- **Draw a box** on the map around any place you care about.\n'
        '- **Find its fire season**: which months burn most, and when to get ready.\n'
        '- **Compare years**: is this year worse or better than normal?\n'
        '- **Type a place** (latitude and longitude) instead of drawing, and list or download its hot spots.\n\n'
        '#### 7. Good to know\n'
        '- A hot spot shows **where** there is heat, not **how big** the fire is or how much land burned.\n'
        '- Clouds and smoke can hide fires from the satellite.\n'
        '- The most recent month may still be missing some days.')
    st.caption('Data: NASA FIRMS (Fire Information for Resource Management System).')


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
AGE_CLASSES = [('Older', '#E8251B'), ('2 to 7 days before', '#FF8C1A'), ('Latest day', '#FFE14D')]  # newest drawn last, on top
SATELLITE_WORDS = {'S-NPP': 'VIIRS (newer satellite, since 2012)',
                   'Terra': 'MODIS Terra (older satellite, since 2001)',
                   'Aqua': 'MODIS Aqua (older satellite, since 2002)'}
SATELLITE_TILES = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
LABEL_TILES = 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}'
PERIODS = {'Latest day': 1, 'Latest 7 days': 7, 'Latest 30 days': 30, 'Latest 12 months': 365}


@st.cache_data
def newest_point_date(path: str, version: int) -> date:
    with duckdb.connect() as con:
        return pd.Timestamp(con.execute('SELECT max(data) FROM read_parquet(?)', [path]).fetchone()[0]).date()


def heat_square(day_from: date, day_to: date) -> float:
    """Bigger squares for long periods, so years of data still draw quickly."""
    span = (day_to - day_from).days
    return .05 if span <= 92 else (.1 if span <= 3 * 365 else .2)


@st.cache_data
def map_summary(files: tuple[tuple[str, int], ...], start: date, end: date, size: float) -> tuple[int, pd.DataFrame]:
    """Any period: the database counts and groups everything for the zoomed-out glow."""
    paths = [p for p, _ in files]
    where = 'FROM read_parquet(?) WHERE data BETWEEN ? AND ?'
    with duckdb.connect() as con:
        total = con.execute('SELECT count(*) ' + where, [paths, start, end]).fetchone()[0]
        cells = con.execute(f'SELECT round(lat / {size}) * {size} AS lat, round(lon / {size}) * {size} AS lon, '
                            f'count(*) AS n {where} GROUP BY 1, 2', [paths, start, end]).df()
    return int(total), cells


def view_box(bounds: dict, step: float = .05) -> tuple[float, float, float, float] | None:
    """Leaflet bounds -> (south, west, north, east), rounded outward so small pans reuse the cache."""
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
        count = int(con.execute('SELECT count(*) ' + where, args).fetchone()[0])
        if count > MAX_MAP_POINTS:
            return count, pd.DataFrame(columns=['lat', 'lon', 'data', 'hora_utc', 'satelite'])
        dots = con.execute('SELECT lat, lon, data, hora_utc, satelite ' + where + ' ORDER BY data, hora_utc', args).df()
    return count, dots


def age_class(days: pd.Series, end: date) -> np.ndarray:
    """0 = older, 1 = 2 to 7 days before the last day shown, 2 = the last day shown."""
    age = (pd.Timestamp(end) - pd.to_datetime(days)).dt.days.to_numpy()
    return np.select([age <= 0, age <= 6], [2, 1], 0)


def add_hotspot_locations(view, points: pd.DataFrame, end: date) -> None:
    """Small dots coloured by age, like the NASA FIRMS map. Popup in plain words and Brasília time."""
    if points.empty:
        return
    hours = points.hora_utc.astype(int)
    when = (pd.to_datetime(points.data) + pd.to_timedelta(hours // 100, unit='h')
            + pd.to_timedelta(hours % 100, unit='m') - pd.Timedelta(hours=3))
    classes = age_class(points.data, end)
    for index, (label, color) in enumerate(AGE_CLASSES):
        mask = classes == index
        if not mask.any():
            continue
        features = [{'type': 'Feature',
                     'geometry': {'type': 'Point', 'coordinates': [round(float(lon), 4), round(float(lat), 4)]},
                     'properties': {'When (Brasília time)': f'{moment:%d %b %Y, %H:%M}',
                                    'Seen by': SATELLITE_WORDS.get(sat, sat)}}
                    for lat, lon, moment, sat in zip(points.lat[mask], points.lon[mask], when[mask], points.satelite[mask])]
        folium.GeoJson({'type': 'FeatureCollection', 'features': features}, name=f'Hot spots · {label}',
                       marker=folium.CircleMarker(radius=3.5, stroke=True, color='#2B0A00', weight=.6,
                                                  fill=True, fill_color=color, fill_opacity=.95),
                       popup=folium.GeoJsonPopup(fields=['When (Brasília time)', 'Seen by'])).add_to(view)


def map_legend(day_from: date, day_to: date) -> str:
    span = (day_to - day_from).days
    shown = AGE_CLASSES[::-1][:1 if span == 0 else (2 if span < 7 else 3)]
    dots = ' &nbsp; '.join(f'<span style="color:{color};font-size:1.3em">●</span> {label}' for label, color in shown)
    return (f'<div style="font-size:.95rem">From far away, glowing areas show where hot spots are. '
            f'Zoom in to a smaller area to see every one as a dot: {dots}</div>')


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
        points, _ = search_hotspots(files, day_from, day_to, 'All available sensors', region)
    st.caption(f'**{len(points):,} hot spots** inside your area from {day_from:%d %b %Y} to {day_to:%d %b %Y}. '
               'Change the dates above the map to list other days.')
    if points.empty:
        return
    st.dataframe(search_table(points), hide_index=True, alt='Hot spots inside the chosen area.', height=300,
                 column_config={'When (Brasília time)': st.column_config.DatetimeColumn(format='DD MMM YYYY, HH:mm')})
    # The CSV is only built when the button is clicked: millions of rows would slow every rerun otherwise.
    st.download_button('Download these hot spots (CSV)', lambda: point_export(points).to_csv(index=False).encode('utf-8-sig'),
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
    day_from, day_to = chosen_period(newest)
    region = st.session_state['regiao']
    try:
        with st.spinner('Loading hot spots…'):
            files = point_files(day_from, day_to)
            total, cells = map_summary(files, day_from, day_to, heat_square(day_from, day_to))
    except (ValueError, duckdb.Error):
        files, total, cells = (), 0, pd.DataFrame(columns=['lat', 'lon', 'n'])
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
    add_heat(view, cells, heat_square(day_from, day_to))
    with st.container(horizontal=True, vertical_alignment='center'):
        st.html(map_legend(day_from, day_to))
        start_format = '%d %b' if day_from.year == day_to.year else '%d %b %Y'
        period = (day_to.strftime('%d %b %Y') if day_from == day_to
                  else f'{day_from.strftime(start_format)} – {day_to:%d %b %Y}')
        st.caption(f'**{total:,} hot spots** · {period}')
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
            add_hotspot_locations(dots, points, day_to)
            st.caption(f'All {in_view:,} hot spots in this part of the map are shown as dots. Click one for details.')
        else:
            st.caption(f'{in_view:,} hot spots in this part of the map: too many to draw one by one. '
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
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10), xaxis_title=None,
                      yaxis_title=None, title='Hot spots per year')
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


def heat_cells(cells: pd.DataFrame) -> list[list[float]]:
    """Hot spots already grouped in small squares (lat, lon, n) -> weights for the zoomed-out glow."""
    if cells.empty:
        return []
    top = max(float(cells.n.quantile(.95)), 1.)
    return [[round(float(lat), 3), round(float(lon), 3), round(min(float(n) / top, 1.), 3)]
            for lat, lon, n in cells[['lat', 'lon', 'n']].itertuples(index=False, name=None)]


def group_points(points: pd.DataFrame, size: float = .05) -> pd.DataFrame:
    return (points.assign(lat=(points.lat / size).round() * size, lon=(points.lon / size).round() * size)
            .groupby(['lat', 'lon']).size().rename('n').reset_index())


def add_heat(view: folium.Map, cells: pd.DataFrame, size: float = .05) -> None:
    heat = HeatMap(heat_cells(cells), name='Hot spot areas', radius=9, blur=11, min_opacity=.3,
                   gradient={'0.2': '#B22200', '0.45': '#FF6A00', '0.7': '#FFA500', '1': '#FFE14D'})
    heat.add_to(view)
    HeatToggle(heat, size=size).add_to(view)


# ---------------------------------------------------------------------------
# Everything about the drawn area, on the Map tab
# ---------------------------------------------------------------------------
SOURCE_COLORS = {'snpp': '#F28E2B', 'noaa20': '#B07AA1', 'modis_convertido': '#9AA5B1'}
SOURCE_NAMES = {'snpp': 'Newer satellite (VIIRS S-NPP)', 'noaa20': 'Backup newer satellite (VIIRS NOAA-20)',
                'modis_convertido': 'Older satellites, corrected (MODIS)'}


def show_timescales(series: pd.DataFrame, region_wkt: str | None) -> None:
    st.markdown('#### Day, week or month')
    scale = st.segmented_control('See hot spots per', ['Day', 'Week', 'Month'], default='Week', required=True,
                                 key='timescale')
    newest = date.today() - timedelta(days=1)
    if scale == 'Month' or not (ROOT / 'data/processed/semanal.parquet').exists():
        data = series.assign(period=pd.to_datetime(dict(year=series.ano, month=series.mes, day=1)))
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
            fig = px.bar(data, x='period', y='hotspots', color='fonte', color_discrete_map=SOURCE_COLORS,
                         labels={'fonte': 'Satellite used'})
            fig.for_each_trace(lambda t: t.update(name=SOURCE_NAMES.get(t.name, t.name)))
            note = ('Each day uses the best satellite that looked that day. Days with no satellite at all are left '
                    'empty (that is not the same as no fire). One day can change a lot because of clouds; '
                    'weeks and months are steadier.')
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
    with st.expander('Why can we compare 2005 with 2024?'):
        st.write('The newer satellite (since 2012) sees about 4 times more hot spots than the older ones, because it '
                 'also sees small fires. We corrected the older years so that every year uses the same ruler. '
                 'Switch between the two views to see the difference. The **How it works** tab explains more.')
        show_harmonization_demo(series, region, first_year, last_year, key='area_demo')
    if not is_mock:
        show_monthly_uncertainty(series, region)
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
    return pd.DataFrame({'When (Brasília time)': when,          # kept as a date-time: fast even for millions of rows
                         'Seen by': points.satelite.map(SATELLITE_WORDS).fillna(points.satelite),
                         'Latitude': points.lat.round(4), 'Longitude': points.lon.round(4),
                         'Heat strength (MW)': points.frp.round(1)})




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
    st.caption('Each dot on the map is a **hot spot**: heat seen from space by a NASA satellite, almost always a fire. '
               f'From {first_year} to today, all years on the same scale.')
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
