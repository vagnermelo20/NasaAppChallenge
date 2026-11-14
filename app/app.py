"""Regional burning activity calendar (B0–B5, B8)."""
import calendar
import json
import math
from datetime import date, datetime
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
from branca.element import MacroElement, Template
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
FIRE_COLORS = ['#440154', '#3B528B', '#21918C', '#5EC962', '#FDE725']
FIRE_LABELS = ['>0–5', '>5–20', '>20–100', '>100–500', 'More than 500']
FIRE_SENSORS = {'VIIRS S-NPP': 'n_viirs', 'MODIS Terra + Aqua': 'n_modis'}
MAP_BASES = {
    'Satellite imagery': ('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                          'Imagery &copy; Esri, Vantor, Earthstar Geographics and the GIS user community'),
    'Dark atlas': ('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
                   'Tiles &copy; Esri, HERE, Garmin, OpenStreetMap contributors and the GIS user community'),
    'Street map': ('OpenStreetMap', ''),
}


class FireLegend(MacroElement):
    rows: list[tuple[str, str]]
    units: str
    view_mode: str
    period: str


def fire_class(count: float) -> int:
    return int(np.searchsorted([5, 20, 100, 500], count, side='left'))


@st.cache_data
def observation_months(path: str, version: int, sensor: str) -> pd.DataFrame:
    if sensor not in FIRE_SENSORS:
        raise ValueError('Unknown satellite sensor.')
    with duckdb.connect() as con:
        column, predicate = observation_layout(con, path, sensor)
        return con.execute(
            f'SELECT DISTINCT ano, mes FROM read_parquet(?) WHERE {predicate} AND {column} > 0 ORDER BY ano, mes',
            [path]).df()


@st.cache_data
def observation_cells(path: str, version: int, sensor: str, year: int,
                      month: int, region_wkt: str | None) -> pd.DataFrame:
    if sensor not in FIRE_SENSORS:
        raise ValueError('Unknown satellite sensor.')
    with duckdb.connect() as con:
        column, predicate = observation_layout(con, path, sensor)
        cells = con.execute(
            f'SELECT lat, lon, sum({column}) AS hotspots FROM read_parquet(?) '
            f'WHERE ano=? AND mes=? AND {predicate} GROUP BY lat, lon HAVING sum({column}) > 0',
            [path, year, month]).df()
    if region_wkt:
        cells = cells[shapely.contains_xy(shapely.from_wkt(region_wkt),
                                         cells.lon + .125, cells.lat + .125)]
    return cells.sort_values('hotspots', ascending=False).reset_index(drop=True)


def observation_layout(con: duckdb.DuckDBPyConnection, path: str, sensor: str) -> tuple[str, str]:
    columns = set(con.execute('DESCRIBE SELECT * FROM read_parquet(?)', [path]).df().column_name)
    if {'satellite', 'n'} <= columns:
        return 'n', ("satellite = 'S-NPP'" if sensor == 'VIIRS S-NPP' else "satellite IN ('Terra', 'Aqua')")
    if FIRE_SENSORS[sensor] in columns:
        return FIRE_SENSORS[sensor], 'TRUE'
    raise ValueError('Observed grid schema is not supported.')


@st.cache_data
def harmonized_map_cells(path: str, version: int, year: int, month: int,
                         region_wkt: str | None) -> pd.DataFrame:
    with duckdb.connect() as con:
        cells = con.execute(
            'SELECT lat, lon, focos_harmonizados AS hotspots, fonte, dado_incompleto AS incomplete '
            'FROM read_parquet(?) WHERE ano=? AND mes=? AND focos_harmonizados>0',
            [path, year, month]).df()
    if region_wkt:
        cells = cells[shapely.contains_xy(shapely.from_wkt(region_wkt), cells.lon + .125, cells.lat + .125)]
    return cells.sort_values('hotspots', ascending=False).reset_index(drop=True)


def fire_features(cells: pd.DataFrame, sensor: str, year: int, month: int) -> dict:
    features = []
    for latitude, longitude, count in cells[['lat', 'lon', 'hotspots']].itertuples(index=False, name=None):
        category = fire_class(count)
        west, south = float(longitude), float(latitude)
        ring = [[west, south], [west + .25, south], [west + .25, south + .25],
                [west, south + .25], [west, south]]
        features.append({'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [ring]},
                         'properties': {'hotspots': round(float(count), 2), 'sensor': sensor,
                                        'period': f'{year}-{month:02d}', 'range': FIRE_LABELS[category],
                                        'color': FIRE_COLORS[category]}})
    return {'type': 'FeatureCollection', 'features': features}


def fire_signal_features(cells: pd.DataFrame, sensor: str, year: int, month: int) -> dict:
    """Symbols locate aggregate cell centers, never individual fire detections."""
    collection = fire_features(cells, sensor, year, month)
    for feature in collection['features']:
        west, south = feature['geometry']['coordinates'][0][0]
        feature['geometry'] = {'type': 'Point', 'coordinates': [west + .125, south + .125]}
        feature['properties']['radius'] = min(15., 3.5 + 1.8 * math.log1p(feature['properties']['hotspots']))
        feature['properties']['location_type'] = 'Center of a 0.25° aggregate cell'
    return collection


@st.cache_data
def hotspot_locations(path: str, version: int, year: int, month: int,
                      sensor: str | None, region_wkt: str | None) -> pd.DataFrame:
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    predicate = " AND satelite = 'S-NPP'" if sensor == 'VIIRS S-NPP' else (
        " AND satelite IN ('Terra', 'Aqua')" if sensor == 'MODIS Terra + Aqua' else '')
    with duckdb.connect() as con:
        points = con.execute('SELECT lat, lon, data, hora_utc, satelite, frp, peso_harmonizado '
                             'FROM read_parquet(?) WHERE data >= ? AND data < ?' + predicate,
                             [path, start, end]).df()
    if region_wkt:
        points = points[shapely.contains_xy(shapely.from_wkt(region_wkt), points.lon, points.lat)]
    return points.reset_index(drop=True)


def add_hotspot_locations(view: folium.Map, points: pd.DataFrame, opacity: float) -> None:
    # GeoJSON uses the map's canvas renderer for small, fixed-size detection dots.
    data = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [float(lon), float(lat)]},
         'properties': {}} for lat, lon in points[['lat', 'lon']].itertuples(index=False, name=None)]}
    if data['features']:
        folium.GeoJson(data, name='NASA FIRMS hotspot locations',
                       marker=folium.CircleMarker(radius=1.6, stroke=False, fill=True,
                                                  fill_color='#FF241C', fill_opacity=opacity),
                       interactive=False).add_to(view)


def add_activity_layer(view: folium.Map, cells: pd.DataFrame, origin: str,
                       year: int, month: int, opacity: float, mode: str) -> None:
    if cells.empty:
        return
    fields = ['sensor', 'period', 'hotspots', 'range']
    aliases = ['Source', 'UTC month', 'Activity in cell', 'Count range']
    if mode == 'Signal view':
        data = fire_signal_features(cells, origin, year, month)
        folium.GeoJson(data, name='Activity glow', control=False, interactive=False,
                       marker=folium.CircleMarker(radius=8), style_function=lambda feature: {
                           'radius': feature['properties']['radius'] + 6,
                           'fillColor': feature['properties']['color'], 'fillOpacity': .12,
                           'stroke': False, 'interactive': False},
                       ).add_to(view)
        fields += ['location_type']
        aliases += ['Location meaning']
        marker = folium.CircleMarker(radius=5)
        style = lambda feature: {
            'radius': feature['properties']['radius'], 'fillColor': feature['properties']['color'],
            'fillOpacity': opacity, 'color': '#D7EDF5', 'weight': .7, 'opacity': .65}
    else:
        data = fire_features(cells, origin, year, month)
        marker = None
        style = lambda feature: {
            'fillColor': feature['properties']['color'], 'fillOpacity': opacity,
            'color': '#B5D1DB', 'opacity': .22, 'weight': .4}
    folium.GeoJson(data, name='NASA FIRMS activity', marker=marker, smooth_factor=0,
                   style_function=style,
                   highlight_function=lambda _: {'weight': 2, 'color': '#FFFFFF', 'fillOpacity': .98},
                   tooltip=folium.GeoJsonTooltip(fields=fields, aliases=aliases, sticky=False),
                   popup=folium.GeoJsonPopup(fields=fields, aliases=aliases),
                   ).add_to(view)


def fire_legend(harmonized: bool = False, view_mode: str = 'Analysis grid', period: str = '') -> MacroElement:
    # This is a Leaflet overlay, not a replacement for native Streamlit controls.
    legend = FireLegend()
    legend.rows = list(zip(FIRE_COLORS, [label.replace('More than ', '>') for label in FIRE_LABELS]))
    legend.units = 'VIIRS-equivalent hotspots / cell' if harmonized else 'Detections / cell'
    legend.view_mode = view_mode
    legend.period = period
    legend._template = Template('''
        {% macro html(this, kwargs) %}
        <div class="ember-map-heading" role="note">
          <div style="color:#87a4bc;font-size:9px;letter-spacing:2px;font-weight:650;">EMBER / FIRE ATLAS</div>
          <div style="font-size:14px;font-weight:650;margin-top:5px;">{{this.period}}</div>
          <div style="font-size:10px;color:#a7bdce;margin-top:3px;">NASA FIRMS · {{this.view_mode}}</div>
        </div>
        <div class="ember-map-legend" role="note" aria-label="NASA FIRMS monthly hotspot count legend">
          {% if this.view_mode == 'Hotspot locations' %}
          <div style="display:flex;align-items:center;gap:10px;font-size:12px;font-weight:650;">
            <span style="width:7px;height:7px;border-radius:50%;background:#FF241C;"></span>NASA FIRMS hotspot locations
          </div>
          <div style="font-size:10px;color:#bdcedd;margin-top:7px;">Recorded satellite detections · not unique fires or burned area</div>
          {% else %}
          <div style="display:flex;justify-content:space-between;gap:12px;margin-bottom:9px;">
            <strong style="font-size:11px;">{{this.units}}</strong><span style="color:#90aabf;font-size:10px;">PER MONTH</span>
          </div>
          <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:3px;">
            {% for color, label in this.rows %}
            <div><div style="height:5px;border-radius:3px;background:{{color}};"></div>
              <div style="font-size:10px;color:#bdcedd;margin-top:5px;">{{label}}</div></div>
            {% endfor %}
          </div>
          <div style="font-size:9px;color:#8fa8bc;margin-top:9px;">0.25° aggregates · not burned area or individual fire locations</div>
          {% endif %}
        </div>
        <style>
        .leaflet-container {background:#101820;font-family:system-ui,sans-serif;}
        .ember-map-heading,.ember-map-legend {position:absolute;z-index:999;background:rgba(8,19,31,.90);color:#edf5fc;
          border:1px solid rgba(157,199,228,.16);box-shadow:0 8px 28px rgba(0,0,0,.28);backdrop-filter:blur(16px);
          font-family:system-ui,sans-serif;box-sizing:border-box;pointer-events:none;}
        .ember-map-heading {top:18px;left:18px;padding:13px 17px;border-radius:12px;max-width:calc(100% - 90px);}
        .ember-map-heading>div {overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
        .ember-map-legend {bottom:26px;left:50%;transform:translateX(-50%);width:min(390px,calc(100% - 30px));padding:13px 17px;border-radius:12px;}
        .leaflet-bar {border:1px solid rgba(157,199,228,.2)!important;box-shadow:0 4px 18px #0004;border-radius:9px;overflow:hidden;}
        .leaflet-control-zoom a,.ember-expand {background:#102335;color:#e3f3ff;border:0;}
        .leaflet-control-zoom a:hover,.ember-expand:hover {background:#23445d;color:#a1e3ff;}
        .ember-expand {width:32px;height:32px;cursor:pointer;font-size:23px;}
        .leaflet-control-layers {background:#102335;color:#edf3fc;border:1px solid #314a60;border-radius:9px;}
        .leaflet-control-attribution {background:rgba(12,24,40,.8);color:#d8e5f4;font-size:9px;}
        .leaflet-control-attribution a {color:#88d8fa;}
        .leaflet-control-scale-line {background:rgba(8,19,31,.85);color:#bfd5e5;border-color:#587185;text-shadow:none;}
        .leaflet-tooltip,.leaflet-popup-content-wrapper {background:#0e2031;color:#edf3fc;border:1px solid #45617c;border-radius:10px;}
        @media(max-width:500px) {.ember-map-heading {top:10px;left:10px;padding:10px 12px;} .ember-map-legend {padding:11px 13px;}}
        </style>
        {% endmacro %}
        {% macro script(this, kwargs) %}
        var ember_expand = L.control({position:'topright'});
        ember_expand.onAdd = function(map) {
          var button = L.DomUtil.create('button','ember-expand leaflet-bar');
          button.type = 'button'; button.title = 'Expand map'; button.setAttribute('aria-label','Expand map'); button.textContent = '⛶';
          L.DomEvent.disableClickPropagation(button);
          button.onclick = function() {
            var target = map.getContainer();
            if (document.fullscreenElement) { document.exitFullscreen().catch(function(){}); }
            else if (target.requestFullscreen) { target.requestFullscreen().catch(function(){button.title='Fullscreen is unavailable in this browser frame';}); }
          };
          document.addEventListener('fullscreenchange',function(){setTimeout(function(){map.invalidateSize();},150);});
          return button;
        };
        ember_expand.addTo({{this._parent.get_name()}});
        {% endmacro %}
    ''')
    return legend


def show_fire_map() -> None:
    with st.sidebar:
        st.markdown('#### Data catalog')
        products = ['Harmonized activity', 'Sensor observations'] if REAL.exists() else ['Sensor observations']
        product = st.selectbox('Data product', products, key='fire_product', persist_state='session',
                               help='Harmonized activity uses the real scientific series. Sensor observations show the separately filtered satellite counts.')
    harmonized = product == 'Harmonized activity'
    processed_grid = ROOT / 'data/processed/grid_sat.parquet'
    grid = REAL if harmonized else (processed_grid if processed_grid.exists() else ROOT / 'data/processed/grid_monthly.parquet')
    if not grid.exists():
        st.info('The selected scientific dataset has not been supplied.')
        return
    with st.sidebar:
        st.caption('NASA FIRMS · science-team processed data')
        sensor = ('VIIRS-equivalent activity' if harmonized else
                  st.selectbox('Sensor', list(FIRE_SENSORS), key='fire_sensor', persist_state='session',
                               help='Sensor-specific counts. Raw MODIS and VIIRS totals are not directly comparable.'))
    path, version = str(grid), grid.stat().st_mtime_ns
    try:
        available = metadata(path, version) if harmonized else observation_months(path, version, sensor)
    except (duckdb.Error, ValueError) as error:
        st.warning(f'The selected dataset is incompatible with this layer: {error}')
        return
    if available.empty:
        st.info('No observed months are available for this sensor.')
        return
    years = sorted(int(y) for y in available.ano.unique())
    with st.sidebar:
        with st.container(horizontal=True):
            year = st.selectbox('Year · UTC', years, index=len(years)-1, key='fire_year', persist_state='session')
            months = sorted(int(m) for m in available[available.ano == year].mes)
            month = st.selectbox('Month', months, index=len(months)-1, format_func=lambda m: MONTHS[m-1],
                                 key='fire_month', persist_state='session')
        limit = st.toggle('Use selected area', value=False, key='fire_limit', persist_state='session',
                          help='Filter to the area applied in Calendar; otherwise show Brazil.')
        visual_mode = st.segmented_control('Display style', ['Hotspot locations', 'Analysis grid'],
                                           default='Hotspot locations', required=True, key='fire_visual_mode',
                                           width='stretch', persist_state='session',
                                           help='Red dots show recorded detection coordinates. Analysis grid shows monthly activity in 0.25° cells.')
        with st.expander('Layer appearance'):
            basemap = st.selectbox('Map background', list(MAP_BASES), key='fire_basemap_satellite', persist_state='session')
            opacity = st.slider('Layer opacity', .25, 1., .8, .05, key='fire_opacity', persist_state='session')
    region = st.session_state.get('regiao') if limit else None
    cells = (harmonized_map_cells(path, version, year, month, region) if harmonized else
             observation_cells(path, version, sensor, year, month, region))
    origin = ('MODIS converted to VIIRS scale' if year < 2012 else 'VIIRS S-NPP observed') if harmonized else sensor
    unit = 'VIIRS-equivalent hotspots' if harmonized else 'Observed detections'
    display_count = lambda value: f'{value:,.2f}' if harmonized else f'{value:,.0f}'
    incomplete = bool(available.loc[(available.ano == year) & (available.mes == month), 'incompleto'].any()) if harmonized else None
    export = cells.assign(sensor=sensor, year=year, month=month,
                          dataset='harmonized' if harmonized else 'observed', source_file=grid.name,
                          count_range=[FIRE_LABELS[fire_class(value)] for value in cells.hotspots])
    with st.sidebar:
        with st.container(border=True, key='observation_card'):
            st.badge('Real harmonized data' if harmonized else 'Processed observations', icon=':material/satellite_alt:', color='blue')
            st.markdown(f'**{product}**')
            st.caption(f'{MONTHS[month-1]} {year} · {origin}')
            st.write(f'**{len(cells):,}** active cells')
            st.caption('NASA FIRMS · 0.25° monthly analysis')
        st.download_button('Export map cells', export.to_csv(index=False).encode('utf-8-sig'),
                           f"{'harmonized' if harmonized else 'firms_observed'}_{year}-{month:02d}.csv", 'text/csv',
                           icon=':material/download:', key='fire_download', width='stretch', on_click='ignore')
        with st.expander('Data provenance'):
            st.caption(f'Source: {grid.name}. ' + ('Same scientific series used by Calendar and Trends. '
                       if harmonized else 'Satellite/day-night counts aggregated from the science-team grid. ')
                       + 'Calibration acceptance is a separate scientific review. No live feed is used.')
            if not harmonized and grid.name == 'grid_monthly.parquet':
                st.warning('Legacy grid: preparation differs from the final scientific series.')
            st.markdown('[NASA FIRMS source](https://firms.modaps.eosdis.nasa.gov/)')
    with st.container(horizontal=True, gap='small'):
        for index, (label, value, help_text) in enumerate([
            (unit, display_count(cells.hotspots.sum()), 'Activity in the displayed cells and month; not unique fires.'),
            ('Active grid cells', f'{len(cells):,}', '0.25° cells with one or more detections.'),
            ('Highest cell count', display_count(cells.hotspots.max()) if len(cells) else '—', 'Largest count in a single cell, not fire severity.'),
        ]):
            with st.container(border=True, key=f'map_stat_{index}'):
                st.metric(label, value, help=help_text)
    area = st.session_state.get('region_label', 'Selected area') if region else 'Brazil · national view'
    with st.container(horizontal=True, vertical_alignment='center'):
        st.markdown(f'**{origin}** · {MONTHS[month-1]} {year}')
        st.caption(area)
    if cells.empty:
        st.info('No recorded hotspots in the selected cells and month. Try another period or enlarge the area.')
    if incomplete:
        st.warning('This month is flagged as incomplete in the scientific dataset. Its total may underestimate activity.')
    if harmonized and year < 2012:
        st.caption('Estimated from MODIS using the delivered calibration. Regional/annual comparisons are more reliable than isolated small cells.')
    view = folium.Map(location=[-14, -52], zoom_start=4, tiles=None, prefer_canvas=True,
                      control_scale=True, zoom_control='topright')
    tiles, attribution = MAP_BASES[basemap]
    if basemap == 'Street map':
        folium.TileLayer('OpenStreetMap', name=basemap).add_to(view)
    else:
        folium.TileLayer(tiles=tiles, attr=attribution, name=basemap,
                         max_zoom=18, max_native_zoom=16).add_to(view)
    view.default_js = [item for item in view.default_js if item[0] == 'leaflet']
    view.default_css = [item for item in view.default_css if item[0] == 'leaflet_css']
    if visual_mode == 'Hotspot locations':
        point_file = ROOT / f'data/processed/focos/focos_{year}.parquet'
        if point_file.exists():
            points = hotspot_locations(str(point_file), point_file.stat().st_mtime_ns, year, month,
                                       None if harmonized else sensor, region)
            add_hotspot_locations(view, points, opacity)
            st.caption(f'{len(points):,} recorded detection locations shown. The indicators and cell export above '
                       'describe the monthly analysis grid; harmonized weights do not create additional map points.')
        else:
            st.info('Individual detection coordinates are not available for this year. Select Analysis grid to view activity.')
    else:
        add_activity_layer(view, cells, origin, year, month, opacity, visual_mode)
    if region:
        folium.GeoJson(mapping(shapely.from_wkt(region)), name='Selected area',
                       style_function=lambda _: {'color': '#8FD5EB', 'weight': 1.5,
                                                 'dashArray': '5 6', 'fillOpacity': 0},
                       interactive=False).add_to(view)
        west, south, east, north = shapely.from_wkt(region).bounds
        view.fit_bounds([[south, west], [north, east]])
    folium.LayerControl(position='topright', collapsed=True).add_to(view)
    fire_legend(harmonized, visual_mode, f'{MONTHS[month-1]} {year} · {area}').add_to(view)
    st_folium(view, height=650, use_container_width=True,
              key=f'fire_atlas_v3_{visual_mode}_{basemap}_{product}_{sensor}_{version}_{year}_{month}_{limit}_{region}', returned_objects=[])
    st.caption(f'NASA FIRMS · {unit} per cell/month · unfilled cells are unclassified. '
               'Counts do not measure fire severity or burned area. Map dates are independent of the calendar range.')
    if visual_mode == 'Signal view':
        st.caption('Signals are proportional symbols at aggregate cell centers. Their displayed radius is not a fire radius or an estimate of burned area.')
    if basemap == 'Satellite imagery':
        st.caption('Esri imagery is background context and is not synchronized with the observation month. Activity data are from NASA FIRMS.')
    with st.expander('Inspect observed cell values'):
        st.dataframe(export, hide_index=True, alt='Scientific activity values and provenance for each mapped cell.')

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
    if st.session_state.get('main_tabs') == 'Fire map':
        st.session_state['fire_limit'] = True


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


@st.cache_data
def read_metrics(path: str, version: int) -> dict:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Metrics must be a JSON object.')
    return data


def show_validation_summary(data: dict) -> None:
    proof = data.get('prova_harmonizacao', {})
    final = proof.get('nacional_loyo_metodo_final', {})
    if final:
        st.subheader('Delivered method · validation summary')
        annual = next((row for row in proof.get('por_escala_de_tempo_2deg', []) if row.get('escala') == 'ano'), {})
        with st.container(horizontal=True):
            st.metric('National monthly correlation', f"{final['correlacao_mensal']:.3f}")
            st.metric('Mean annual absolute error · national', f"{final['erro_anual_medio_abs'] * 100:.2f}%")
            st.metric('Annual agreement within ±20% · 2° regions', annual.get('dentro de ±20%', 'Not reported'))
        st.caption('Final-method results reported by the science team. Leave-one-year-out, 2012–2021. '
                   'Annual regional agreement is not the cell-scale peak-month acceptance criterion.')
        rows = [{'Region size': r.get('tamanho da região'), 'Median monthly difference': r.get('convertido: diferença mediana'),
                 'Months within ±20%': r.get('convertido: dentro de ±20%'), 'Correlation': r.get('correlação')}
                for r in proof.get('por_tamanho_regiao', [])]
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                         alt='Final-method agreement by region size, restricted to the cases defined by the science team.')
        st.caption('Regional monthly comparisons above use cases with at least 100 observed VIIRS hotspots. '
                   'They are aggregate comparisons, not individual-fire matching.')
    acceptance = data.get('aceite_A2', {})
    if acceptance.get('passa') is False:
        cell = data.get('loyo_2012_2021', {}).get('celula', {})
        peak = cell.get('acerto_mes_pico')
        peak_text = f'{peak * 100:.1f}%' if isinstance(peak, (int, float)) else 'not reported'
        qualifier = 'version-1 evaluation' if data.get('nota') else 'reported evaluation'
        st.warning(f'Cell-scale acceptance is pending: peak-month accuracy is {peak_text} in the {qualifier}, '
                   'below the 80% target. The official cell-scale evaluation must be rerun for the final method. '
                   'Regional agreement does not replace this requirement.')


def show_methodology(is_mock: bool, coverage: pd.DataFrame | None = None) -> None:
    st.subheader('Methodology')
    if coverage is not None:
        first, last = coverage.iloc[0], coverage.iloc[-1]
        st.info(f'Delivered archive: {int(first.ano)}-{int(first.mes):02d} to {int(last.ano)}-{int(last.mes):02d}. '
                'References to a 2026 API extension in the document describe planned work; it is not included in this delivery.'
                if int(last.ano) < 2026 else 'Archive includes the delivered current-year extension; incomplete months remain provisional.')
    metrics = ROOT / 'reports/metrics.json'
    if metrics.exists():
        try:
            data = read_metrics(str(metrics), metrics.stat().st_mtime_ns)
            show_validation_summary(data)
            with st.expander('Full metrics · includes the earlier method and version notes'):
                st.json(data)
        except (OSError, ValueError, KeyError, TypeError) as error:
            st.warning(f'Validation metrics could not be loaded: {error}')
    else:
        st.caption('Validation metrics pending — no accuracy claims are made for the mock.')
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
    for filename, description in [('prova_antes_depois.png', 'Out-of-sample comparison before and after conversion'),
                                  ('prova_pantanal.png', 'Pantanal: converted MODIS versus observed VIIRS'),
                                  ('harmonizado_anual.png', 'Delivered harmonized annual series')]:
        image = ROOT / 'reports' / filename
        if image.exists():
            st.image(str(image), caption=description, alt=description, width='stretch')
    figures = [
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


def area_controls(first_year: int, last_year: int, expanded: bool) -> str:
    with st.expander('Area & calendar filters', expanded=expanded):
        st.caption('Region and calendar period')
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

    return mode


def calendar_view(mode: str, coverage: pd.DataFrame, path: str, is_mock: bool,
                  first_year: int, last_year: int):
    st.subheader('Select an area')
    if (mode == 'Draw on map' or st.toggle('Show map preview', value=False, key='show_map')):
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

    return elapsed


def main() -> None:
    st.set_page_config(page_title='EMBER · Fire activity observatory', page_icon=':material/public:',
                       layout='wide', initial_sidebar_state='expanded')
    st.html('''<style>
        .st-key-observation_card {
            background:linear-gradient(135deg,#172b40,#122033);
            border-left:3px solid #62c7f2;
        }
        .st-key-map_stat_0,.st-key-map_stat_1,.st-key-map_stat_2 {
            background:linear-gradient(120deg,#14283a,#101c2b);
            border:1px solid #284154;border-radius:14px;
            box-shadow:0 5px 20px #0002;
        }
        .st-key-brand_block h2 {letter-spacing:.15em;font-weight:750;}
        .st-key-brand_block p {letter-spacing:.12em;font-size:.72rem;}
        </style>''')
    if not REAL.exists() and not MOCK.exists():
        st.warning('Generate the local development dataset to open the workspace.')
        st.code('.venv/Scripts/python.exe app/make_mock.py', language='bash')
        st.stop()
    path, version = data_source()
    try:
        coverage = metadata(path, version)
        if coverage.empty:
            raise ValueError('The dataset has no observations.')
    except (duckdb.Error, ValueError) as error:
        st.error(f'Unable to open the workspace: {error}')
        st.stop()
    first_year, last_year = int(coverage.ano.min()), int(coverage.ano.max())
    is_mock = Path(path) == MOCK
    for key, value in [('regiao', None), ('region_label', 'Brazil · entire dataset'),
                       ('map_revision', 0), ('map_seed_wkt', None), ('latitude', -18.0),
                       ('longitude', -56.5), ('radius', 50.0)]:
        st.session_state.setdefault(key, value)
    active_view = st.session_state.get('main_tabs', 'Fire map')
    with st.sidebar:
        with st.container(key='brand_block'):
            st.markdown('## :material/public: EMBER')
            st.caption('EARTH FIRE OBSERVATORY')
        mode = area_controls(first_year, last_year, expanded=active_view in ('Calendar', 'Trends'))
        with st.expander('Science status'):
            st.badge('Processed FIRMS grid available', color='blue')
            st.badge('Calendar mock' if is_mock else 'Real harmonized series loaded', color='orange' if is_mock else 'blue')
            st.caption(f"{Path(path).name} · {first_year}–{last_year} · {int(coverage.incompleto.sum())} incomplete months")
            st.badge('Scientific acceptance under review', color='orange')
            st.caption('Scientific artifacts have been delivered. Official final-method cell-scale validation and public deployment remain pending.')
    with st.container(horizontal=True, vertical_alignment='center'):
        with st.container(width='stretch'):
            st.subheader('Fire activity workspace')
            st.caption('NASA FIRMS observations · Brazil · Historical patterns')
        st.badge('Archive', icon=':material/satellite_alt:', color='blue')
        st.badge('Calendar · mock' if is_mock else f'Real data · {first_year}–{last_year}', color='orange' if is_mock else 'blue')
    fire_tab, calendar_tab, trends, methodology, about = st.tabs(
        ['Fire map', 'Calendar', 'Trends', 'Methodology', 'About'], default='Fire map',
        key='main_tabs', on_change='rerun')
    elapsed = None
    if not calendar_tab.open:
        st.session_state['map_seed_wkt'] = st.session_state.get('draft_region')
        st.session_state.pop('last_map_event', None)
    with fire_tab:
        if fire_tab.open:
            show_fire_map()
    with calendar_tab:
        if calendar_tab.open:
            if is_mock:
                st.warning('Development calendar — provisional conversion, not validated harmonization. '
                           'The Fire map uses separate observed counts.')
            elapsed = calendar_view(mode, coverage, path, is_mock, first_year, last_year)
    with trends:
        if trends.open:
            if is_mock:
                st.warning('Development trends use the provisional calendar mock.')
            start, end = st.session_state['applied_years']
            start, end = max(first_year, start), min(last_year, end)
            if start > end:
                start, end = first_year, last_year
            begin = perf_counter()
            series = serie_regiao(st.session_state['regiao'], start, end)
            elapsed = perf_counter() - begin
            st.subheader('Historical trends')
            st.caption(f"{st.session_state['region_label']} · {start}–{end}")
            show_trends(series, 'MOCK · ' if is_mock else '')
    with methodology:
        if methodology.open:
            show_methodology(is_mock, coverage)
    with about:
        if about.open:
            st.subheader('A consistent view of burning activity')
            st.write('EMBER is a NASA Space Apps prototype for exploring where and when satellite-detected burning activity occurs.')
            calendar_status = ('Development mock, with a provisional conversion.' if is_mock else
                               f'Real harmonized series delivered by the science team, {first_year}–{last_year}. '
                               'MODIS converted before 2012; observed S-NPP thereafter.')
            st.markdown('**Map:** real harmonized activity or separately identified sensor observations from the processed grid.\n\n'
                        f'**Calendar:** {calendar_status}\n\n'
                        '**Built for:** fire managers, researchers and land managers exploring historical patterns.')
            last = coverage.iloc[-1]
            st.caption(f'The delivered archive ends in {MONTHS[int(last.mes)-1]} {int(last.ano)}. It is not a real-time emergency feed. '
                       'The final-method cell-scale acceptance criterion is still under review.')
            st.markdown('[NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) · [Project repository](https://github.com/vagnermelo20/NasaAppChallenge)')
    st.caption('Hotspots are satellite detections, not number of fires or burned area.')
    if elapsed is not None:
        st.caption(f"Calendar source: {Path(path).name} · Query {elapsed:.3f} s · UTC months · 0.25° grid")
    else:
        st.caption('NASA FIRMS · Harmonized activity and processed sensor observations · Scientific acceptance under review')


if __name__ == '__main__':
    main()
