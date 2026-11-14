"""Regional burning activity calendar (B0–B5, B8)."""
import calendar
import json
import math
from datetime import datetime
from pathlib import Path
from time import perf_counter
from zoneinfo import ZoneInfo

import duckdb
import folium
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import shapely
import streamlit as st
from folium.plugins import Draw
from shapely.geometry import Polygon, mapping, shape
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / 'data/processed/harmonized.parquet'
MOCK = ROOT / 'data/processed/harmonized_mock.parquet'
MONTHS = list(calendar.month_abbr)[1:]
EXAMPLES = {
    'Pantanal': (-18.0, -56.5, 100.0),
    'Matopiba': (-10.0, -46.0, 100.0),
    'Acre': (-9.0, -70.0, 100.0),
}


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


def apply_example(name: str) -> None:
    lat, lon, radius = EXAMPLES[name]
    st.session_state['region_mode'] = 'Lat-Lon + radius'
    st.session_state['latitude'] = lat
    st.session_state['longitude'] = lon
    st.session_state['radius'] = radius
    st.session_state['regiao'] = radius_polygon(lat, lon, radius).wkt
    st.session_state['region_label'] = f'{name} example · {radius:g} km radius'
    st.session_state['draft_region'] = st.session_state['regiao']


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
    if available.empty:
        return {}
    latest = available.iloc[-1]
    history = series[(series.mes == latest.mes) & (series.ano < latest.ano)
                     & ~series.incompleto & series.focos.notna()].copy()
    median = history.focos.median()
    delta = ((latest.focos - median) / median * 100
             if pd.notna(median) and median > 0 and not latest.incompleto else None)
    if latest.incompleto:
        category = 'Incomplete month'
    elif len(history) < 3:
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
                delta=delta, category=category)


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
    fig = px.imshow(shown.to_numpy(), x=MONTHS, y=values.index.astype(str),
                    color_continuous_scale='PuOr' if anomaly else 'viridis', aspect='auto',
                    labels={'x': 'Month (UTC)', 'y': 'Year',
                            'color': 'Anomaly (%)' if anomaly else 'Hotspots / month'})
    if anomaly:
        finite = shown.to_numpy()[np.isfinite(shown.to_numpy())]
        extent = max(1., float(np.abs(finite).max())) if len(finite) else 1.
        fig.update_coloraxes(cmin=-extent, cmax=extent, cmid=0)
    fig.update_traces(text=labels.to_numpy(), texttemplate='%{text}' if show_values else '',
                      customdata=np.where(flags.to_numpy(), 'Incomplete / unavailable', 'Complete'),
                      hovertemplate=('Year: %{y}<br>Month: %{x}<br>'
                                     + ('Anomaly: %{z:+.1f}%' if anomaly else 'Hotspots: %{z:,.1f}')
                                     + '<br>%{customdata}<extra></extra>'),
                      hoverongaps=False)
    if not show_values:
        marked = series[series.incompleto & series.focos.notna()]
        if not marked.empty:
            fig.add_trace(go.Scatter(
                x=[MONTHS[int(m) - 1] for m in marked.mes], y=marked.ano.astype(str),
                mode='text', text=['*'] * len(marked), textfont=dict(color='white', size=18),
                name='Incomplete data', hovertemplate='%{y} %{x}: incomplete data<extra></extra>'))
    if 2011 in values.index and 2012 in values.index:
        position = list(values.index).index(2011) + 0.5
        fig.add_hline(y=position, line_dash='dash', line_color='white', line_width=2)
    fig.update_layout(height=max(350, len(values) * 26 + 120),
                      margin=dict(l=10, r=10, t=30, b=10))
    fig.update_yaxes(dtick=1)
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


def show_comparison(series: pd.DataFrame, prefix: str) -> None:
    summary = latest_comparison(series)
    st.subheader('Latest available month vs history')
    if not summary:
        st.info('No observed month is available in this selection.')
        return
    year, month = summary['year'], summary['month']
    delta = summary['delta']
    with st.container(horizontal=True):
        st.metric(f'{MONTHS[month - 1]} {year} · hotspots', f"{summary['value']:,.0f}",
                  delta=f'{delta:+.1f}% vs historical median' if delta is not None else None,
                  delta_color='off')
        st.metric('Historical activity category', summary['category'])
    st.caption(f"Baseline: {len(summary['history'])} earlier complete years within the selected range. "
               'Categories describe past activity, not forecasts or operational alerts. At least 3 years are required for a category.')
    if summary['incomplete']:
        st.warning('The latest month is incomplete. Its total is provisional; percentage comparisons and category thresholds are suppressed.')
    elif pd.notna(summary['median']) and summary['median'] == 0:
        st.caption('Historical median is zero, so a percentage change is undefined.')
    comparisons = series[(series.mes == month) & series.focos.notna()].sort_values('ano')
    fig = go.Figure(go.Bar(
        x=comparisons.ano, y=comparisons.focos,
        marker_color=['#35B779' if y == year else '#31688E' for y in comparisons.ano],
        marker_pattern_shape=['/' if flag else '' for flag in comparisons.incompleto],
        name='Hotspots', hovertemplate='Year: %{x}<br>Hotspots: %{y:,.1f}<extra></extra>'))
    if pd.notna(summary['median']):
        fig.add_hline(y=float(summary['median']), line_dash='dash',
                      annotation_text='Earlier-year median')
    fig.update_layout(title=f'{prefix}{MONTHS[month - 1]} across years',
                      xaxis_title='Year', yaxis_title='VIIRS-equivalent hotspots / month', height=340)
    st.plotly_chart(fig, key='historical_comparison', alt='Same-month activity across years, with latest year highlighted and prior-year median.',
                    config={'displaylogo': False})


def show_trends(series: pd.DataFrame, prefix: str) -> None:
    annual = series.groupby('ano').agg(total=('focos', lambda x: x.sum(min_count=1)),
                                     observed=('focos', 'count'), incomplete=('incompleto', 'any')).reset_index()
    annual['complete'] = (annual.observed == 12) & ~annual.incomplete
    fig = go.Figure()
    for before, label, color in [(True, 'MODIS converted', '#31688E'),
                                  (False, 'VIIRS observed', '#35B779')]:
        part = annual[annual.ano.lt(2012) == before]
        fig.add_trace(go.Scatter(x=part.ano, y=part.total.where(part.complete),
                                mode='lines+markers', name=label, connectgaps=False,
                                line=dict(color=color)))
    partial = annual[~annual.complete & annual.total.notna()]
    fig.add_trace(go.Scatter(x=partial.ano, y=partial.total, mode='markers',
                            name='Partial-year total', marker=dict(symbol='diamond-open', size=11, color='#FDE725')))
    if annual.ano.min() < 2012:
        fig.add_vrect(x0=float(annual.ano.min()) - .5, x1=min(2011.5, float(annual.ano.max()) + .5),
                      fillcolor='#31688E', opacity=.12, line_width=0)
    fig.update_layout(title=f'{prefix}Annual activity', xaxis_title='Year',
                      yaxis_title='VIIRS-equivalent hotspots / year', height=360)
    st.plotly_chart(fig, key='annual_trend', alt='Annual activity with converted MODIS years shaded and partial years shown as open diamonds.',
                    config={'displaylogo': False})
    st.caption('Open diamonds are incomplete-year totals and should not be compared directly with complete years.')
    complete = series[~series.incompleto & series.focos.notna()]
    seasonal = complete.groupby('mes').agg(median=('focos', 'median'), years=('focos', 'count')).reindex(range(1, 13))
    seasonal['month'] = MONTHS
    fig = px.bar(seasonal, x='month', y='median', color_discrete_sequence=['#35B779'],
                 hover_data=['years'], labels={'month': 'Month (UTC)', 'median': 'Median hotspots / month', 'years': 'Complete years'},
                 title=f'{prefix}Seasonality across complete months')
    st.plotly_chart(fig, key='seasonality', alt='Median monthly activity and number of complete years used for each month.',
                    config={'displaylogo': False})


def show_methodology(is_mock: bool) -> None:
    st.subheader('Methodology')
    doc = ROOT / 'docs/metodologia.md'
    if doc.exists():
        st.markdown(doc.read_text(encoding='utf-8'))
    else:
        st.info('The science team has not delivered the final methodology document yet.')
        st.markdown('This prototype aggregates NASA FIRMS hotspots into 0.25° cells and UTC calendar months. '
                    'Region selection includes cells by their centers. The planned harmonization converts historical MODIS '
                    'activity to the VIIRS scale; final calibration and out-of-sample validation are pending.')
    if is_mock:
        st.warning('The current mock uses MODIS × 3.8 before 2012 and VIIRS counts thereafter. '
                   'This provisional factor is not the final scientific method.')
    st.markdown('**Historical comparisons:** each month is compared with the same month in earlier complete years '
                'within the selected range. Zero medians, missing history and incomplete target months have no percentage anomaly. '
                'The activity categories use the 25th, 75th and 90th percentiles and require at least three historical years. '
                'They are descriptive categories, not fire predictions.\n\n'
                '**Coverage:** missing cell-month records are treated as zero within the source coverage, as agreed in the data contract. '
                'Entire missing observation months require additional coverage metadata. Hotspots do not measure burned area or unique fires.')
    metrics = ROOT / 'reports/metrics.json'
    if metrics.exists():
        try:
            st.json(json.loads(metrics.read_text(encoding='utf-8')))
        except (OSError, ValueError) as error:
            st.warning(f'Validation metrics could not be loaded: {error}')
    else:
        st.caption('Validation metrics pending — no accuracy claims are made for the mock.')
    figures = [('harmonizado_anual.png', 'Harmonization comparison supplied by the science team'),
               ('v2_serie_anual.png', 'Exploratory raw counts by sensor; not a harmonized result'),
               ('v6_mapa_k.png', 'Exploratory spatial variation in sensor count ratios'),
               ('b4_curva_deteccao.png', 'Exploratory detection analysis')]
    for filename, description in figures:
        image = ROOT / 'reports' / filename
        if image.exists():
            with st.expander(description):
                st.image(str(image), caption=description, alt=description, width='stretch')


@st.fragment
def region_map(mode: str) -> None:
    """Keep draft edits inside the map; query only after explicit application."""
    st.caption('Draw or edit an area, then click Apply map selection to update the calendar.')
    view = folium.Map(location=[-14, -52], zoom_start=4, tiles='OpenStreetMap')
    # Leaflet and Leaflet.Draw cover all features used here. Extra Bootstrap,
    # jQuery and icon CDN requests can otherwise hold up the iframe loader.
    view.default_js = [item for item in view.default_js if item[0] == 'leaflet']
    view.default_css = [item for item in view.default_css if item[0] == 'leaflet_css']
    if mode == 'Draw on map':
        editable = folium.FeatureGroup(name='Selected areas').add_to(view)
        seed = st.session_state.get('map_seed_wkt')
        if seed:
            geometry = shapely.from_wkt(seed)
            parts = list(geometry.geoms) if geometry.geom_type == 'MultiPolygon' else [geometry]
            for part in parts:
                folium.Polygon(
                    locations=[[(y, x) for x, y in ring.coords]
                               for ring in [part.exterior, *part.interiors]],
                    color='#35B779', fill_opacity=0.15,
                ).add_to(editable)
        Draw(feature_group=editable, show_geometry_on_click=False, draw_options={
            'polyline': False, 'circle': False, 'circlemarker': False,
            'marker': False, 'rectangle': True, 'polygon': {'allowIntersection': False},
        }).add_to(view)
    elif st.session_state['regiao']:
        polygon = shapely.from_wkt(st.session_state['regiao'])
        folium.GeoJson(mapping(polygon), style_function=lambda _: {
            'color': '#35B779', 'weight': 2, 'fillOpacity': 0.15}).add_to(view)
        west, south, east, north = polygon.bounds
        view.fit_bounds([[south, west], [north, east]])
    output = st_folium(view, height=400, use_container_width=True,
                       key=f"region_map_{mode}_{st.session_state['map_revision']}",
                       returned_objects=['all_drawings'] if mode == 'Draw on map' else [])
    if mode == 'Draw on map':
        valid = True
        if output and output.get('all_drawings') is not None:
            event = json.dumps(output['all_drawings'], sort_keys=True)
            if event != st.session_state.get('last_map_event'):
                try:
                    draft = drawn_region(output)
                except (ValueError, KeyError, shapely.GEOSException) as error:
                    st.error(str(error))
                    valid = False
                else:
                    st.session_state['draft_region'] = draft
                    st.session_state['last_map_event'] = event
        pending = st.session_state.get('draft_region') != st.session_state['regiao']
        st.caption('Selection changed — apply it to refresh the results.' if pending
                   else 'Calendar uses the applied region shown below.')
        if st.button('Apply map selection', key='apply_map', disabled=not valid):
            region = st.session_state.get('draft_region')
            st.session_state['regiao'] = region
            st.session_state['region_label'] = 'Drawn area' if region else 'Brazil · entire dataset'
            st.rerun()
    st.caption('If the map does not load, use Lat-Lon + radius in the sidebar. The calendar works without the map.')


def main() -> None:
    st.set_page_config(page_title='Harmonized Burning Activity Calendar', page_icon='🌍', layout='wide')
    st.caption('NASA SPACE APPS CHALLENGE · BRAZIL PILOT')
    st.title('Harmonized Burning Activity Calendar')
    st.write('Explore historical burning activity across Brazil using NASA FIRMS MODIS and VIIRS satellite detections.')
    if not REAL.exists() and not MOCK.exists():
        st.warning('No dataset found. Generate the development dataset to get started.')
        st.code('.venv/Scripts/python.exe app/make_mock.py', language='bash')
        st.stop()
    path, version = data_source()
    try:
        coverage = metadata(path, version)
        if coverage.empty:
            raise ValueError('The data file has no observations.')
    except (duckdb.Error, ValueError) as error:
        st.error(f'Unable to read the dataset: {error}')
        st.stop()
    first_year, last_year = int(coverage.ano.min()), int(coverage.ano.max())
    is_mock = Path(path) == MOCK
    if is_mock:
        st.warning('Development preview — MOCK data. The provisional conversion is not validated harmonization.')
    st.session_state.setdefault('regiao', None)
    st.session_state.setdefault('region_label', 'Brazil · entire dataset')
    st.session_state.setdefault('map_revision', 0)
    st.session_state.setdefault('map_seed_wkt', None)
    st.session_state.setdefault('latitude', -18.0)
    st.session_state.setdefault('longitude', -56.5)
    st.session_state.setdefault('radius', 50.0)
    with st.sidebar:
        st.header('Explore activity')
        mode = st.radio('Region selection', ['Draw on map', 'Lat-Lon + radius'], key='region_mode',
                        help='Draw and apply a shape, or enter coordinates and click Update. Coordinates work without loading the map.')
        if mode != st.session_state.get('previous_mode'):
            st.session_state['map_seed_wkt'] = st.session_state['regiao']
            st.session_state['draft_region'] = st.session_state['regiao']
            st.session_state.pop('last_map_event', None)
            st.session_state['previous_mode'] = mode
        with st.form('filters'):
            if first_year < last_year:
                years = st.slider('Year range (UTC)', first_year, last_year,
                                  (first_year, last_year), key='year_range',
                                  help='This range also defines the earlier years available for historical comparisons.')
            else:
                years = (first_year, last_year)
                st.caption(f'Available year: {first_year}')
            if mode == 'Lat-Lon + radius':
                lat = st.number_input('Latitude (°)', -34.0, 6.0, key='latitude', persist_state='session')
                lon = st.number_input('Longitude (°)', -74.0, -34.0, key='longitude', persist_state='session')
                radius = st.number_input('Radius (km)', 5.0, 500.0, key='radius',
                                         help='Cells are included when their centers lie inside the circle.', persist_state='session')
            submitted = st.form_submit_button('Update', width='stretch', key='update')
        if submitted or 'applied_years' not in st.session_state:
            st.session_state['applied_years'] = years
            if submitted and mode == 'Lat-Lon + radius':
                st.session_state['regiao'] = radius_polygon(lat, lon, radius).wkt
                st.session_state['region_label'] = f'{lat:.2f}°, {lon:.2f}° · {radius:g} km radius'
        if st.button('Reset to Brazil', width='stretch', key='reset_region'):
            st.session_state['regiao'] = None
            st.session_state['region_label'] = 'Brazil · entire dataset'
            st.session_state['map_revision'] += 1
            st.session_state['map_seed_wkt'] = None
            st.session_state['draft_region'] = None
            st.session_state.pop('last_map_event', None)
        with st.expander('Try an example region'):
            example = st.selectbox('Example region', list(EXAMPLES), key='example_region',
                                   help='Illustrative 100 km circles, not administrative or biome boundaries.')
            st.button('Apply example region', key='apply_example', width='stretch',
                      on_click=apply_example, args=(example,))
        st.divider()
        st.caption(f'Data coverage: {first_year}–{last_year}')
        st.caption('Grid: 0.25° · Cell-center selection · UTC months')
    calendar_tab, trends, methodology, about = st.tabs(
        ['Calendar', 'Trends', 'Methodology', 'About'], key='main_tabs', on_change='rerun')
    if not calendar_tab.open:
        # Preserve the editable shapes when the browser component leaves the page.
        st.session_state['map_seed_wkt'] = st.session_state.get('draft_region')
        st.session_state.pop('last_map_event', None)
    with calendar_tab:
        st.subheader('Select an area')
        if calendar_tab.open and (mode == 'Draw on map' or st.toggle('Show map preview', value=False, key='show_map')):
            region_map(mode)
        else:
            st.caption('Set coordinates and radius in the sidebar, then click Update. Map preview is optional.')
        start, end = st.session_state['applied_years']
        start, end = max(first_year, start), min(last_year, end)
        if start > end:
            start, end = first_year, last_year
        region_wkt = st.session_state['regiao']
        st.caption(f"Applied region: {st.session_state['region_label']} · {start}–{end}")
        begin = perf_counter()
        with st.spinner('Loading monthly activity…'):
            series = serie_regiao(region_wkt, start, end)
        elapsed = perf_counter() - begin
        cells = celulas()
        if region_wkt:
            selected_count = int(shapely.contains_xy(shapely.from_wkt(region_wkt),
                                                     cells.lon + .125, cells.lat + .125).sum())
        else:
            selected_count = len(cells)
        st.caption(f'{selected_count:,} grid-cell centers selected · Values are VIIRS-equivalent hotspots.')
        st.subheader('Burning activity calendar')
        if selected_count == 0:
            st.warning('No grid-cell centers from the dataset fall inside this selection. '
                       'Try a larger radius or an example region. Zero totals here do not establish that no fire occurred.')
        elif series.focos.fillna(0).sum() == 0:
            st.info('No detections in the selected cells and period. Try a larger region; small areas may contain no cell centers.')
        anomaly = st.toggle('Show anomalies (%)', value=False, key='anomaly_mode', persist_state='session',
                            help='Compare each complete month with the same month in earlier complete years in the selected period.')
        show_values = st.toggle('Show values in cells', value=False, key='cell_values', persist_state='session',
                                help='Keep off for a clearer calendar on small screens. Hover, tap a cell, or open Monthly values for exact numbers.')
        figure = calendar_figure(series, anomaly=anomaly, show_values=show_values)
        figure.update_layout(title=f"{'MOCK · ' if is_mock else ''}{st.session_state['region_label']} · {start}–{end}")
        st.plotly_chart(figure, key='calendar', width='stretch',
                        alt='Monthly burning activity by year in the selected region, in VIIRS-equivalent hotspots.',
                        config={'displaylogo': False, 'toImageButtonOptions': {
                            'format': 'png', 'filename': f"{'mock_' if is_mock else ''}calendar_{start}-{end}"}})
        st.caption('* Incomplete data · — Outside available coverage. Before 2012: MODIS converted to VIIRS scale.')
        if anomaly:
            st.caption('Blank cells have incomplete data, no earlier baseline, or a zero median. The color scale is centered on zero.')
        if calendar_tab.open:
            show_comparison(series, 'MOCK · ' if is_mock else '')
        complete = series[~series.incompleto & series.focos.notna()]
        seasonal = complete.groupby('mes').focos.median()
        annual = series.groupby('ano').focos.sum(min_count=1)
        complete_years = series.groupby('ano').apply(
            lambda group: group.focos.notna().all() and not group.incompleto.any())
        annual = annual[complete_years]
        with st.container(horizontal=True):
            st.metric('Peak seasonal month', MONTHS[int(seasonal.idxmax()) - 1]
                      if not seasonal.empty and seasonal.max() > 0 else 'No peak',
                      help='Highest monthly median across complete months in the selected years.')
            st.metric('Highest-activity year', str(annual.idxmax())
                      if not annual.empty and annual.max() > 0 else 'No complete peak',
                      help='Highest annual total among complete years in the selected range.')
        export = export_table(series, coverage, region_wkt, 'mock' if is_mock else 'harmonized')
        region_name = 'brazil' if region_wkt is None else ('radius' if 'radius' in st.session_state['region_label'] else 'drawn_area')
        today = datetime.now(ZoneInfo('America/Fortaleza')).date().isoformat()
        filename = f"{'mock_' if is_mock else ''}hotspots_calendar_{start}-{end}_{region_name}_{today}.csv"
        st.download_button('Download monthly CSV', export.to_csv(index=False).encode('utf-8-sig'),
                           filename, 'text/csv', key='download_csv', on_click='ignore')
        st.caption('CSV anomalies use the median for the same month in earlier complete years within the selected range. '
                   'A zero or missing baseline leaves the anomaly blank. Use the chart camera button to save a PNG.')
        with st.expander('Monthly values and coverage notes'):
            st.dataframe(export.drop(columns='region_wkt'), hide_index=True,
                         alt='Monthly values available in the CSV download.')
            st.caption('Within dataset coverage, missing cell-month rows are treated as zero under the data contract. '
                       'A completely missing observation month cannot be distinguished without additional coverage metadata.')
    with trends:
        st.subheader('Historical trends')
        if trends.open:
            show_trends(series, 'MOCK · ' if is_mock else '')
    with methodology:
        if methodology.open:
            show_methodology(is_mock)
    with about:
        st.subheader('About this project')
        st.write('A NASA Space Apps prototype for exploring burning activity calendars from MODIS and VIIRS active fire hotspots.')
        st.markdown('Source: [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/)')
    st.divider()
    st.caption('Hotspots are satellite detections, not number of fires or burned area.')
    st.caption(f"Data: {Path(path).name} · {'MOCK — development only' if is_mock else 'Harmonized dataset'} · Query: {elapsed:.3f} s")


if __name__ == '__main__':
    main()
