"""Regression checks for spatial selection, coverage and CSV consistency.

Run: .venv/Scripts/python.exe -m unittest app.test_delivery -v
"""
import io
import math
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from shapely.geometry import Point, box, mapping
from streamlit.testing.v1 import AppTest
from app.check_release import inspect_release

from app.app import (anomaly_values, cached_series, calendar_figure, complete_months,
                     data_source, drawn_region, export_table, latest_comparison, metadata,
                     radius_polygon, fire_class, fire_features, fire_legend,
                     observation_cells, observation_months, harmonized_map_cells,
                     fire_signal_features, add_activity_layer, hotspot_locations, add_hotspot_locations,
                     search_hotspots, point_export, interval_coverage, sensor_interval_coverage)


class ReleaseReadinessTests(unittest.TestCase):
    def test_missing_artifacts_do_not_create_mock_or_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = inspect_release(root)
            self.assertEqual(result['status'], 'waiting_for_scientific_artifacts')
            self.assertEqual(len(result['missing']), 4)
            self.assertEqual(list(root.iterdir()), [])

    def test_delivered_artifacts_are_ready_for_review_not_certification(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'data/processed').mkdir(parents=True)
            (root / 'docs').mkdir()
            (root / 'reports').mkdir()
            pd.DataFrame({'lat': [-18.], 'lon': [-56.], 'ano': [2025], 'mes': [1],
                          'focos_harmonizados': [1.], 'fonte': ['viirs'],
                          'dado_incompleto': [False]}).to_parquet(root / 'data/processed/harmonized.parquet')
            (root / 'docs/metodologia.md').write_text('Test methodology', encoding='utf-8')
            (root / 'reports/metrics.json').write_text('{"test_metric": 0.9}', encoding='utf-8')
            Image.new('RGB', (2, 2)).save(root / 'reports/harmonizado_anual.png')
            result = inspect_release(root)
            self.assertEqual(result['status'], 'ready_for_review')
            self.assertTrue(result['manual_checks'])
            self.assertEqual(result['dataset']['first_year'], 2025)
            (root / 'reports/metrics.json').write_text('{invalid', encoding='utf-8')
            self.assertEqual(inspect_release(root)['status'], 'waiting_for_scientific_artifacts')


class CalendarDataTests(unittest.TestCase):
    def test_exact_date_search_crosses_years_filters_polygon_and_never_hides_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            files = []
            for year, dates in [(2024, ['2024-12-30', '2024-12-31']),
                                (2025, ['2025-01-01', '2025-01-02'])]:
                path = Path(temporary) / f'{year}.parquet'
                pd.DataFrame({'lat': [-18.1, -18.9], 'lon': [-56.1, -56.9],
                              'data': pd.to_datetime(dates), 'hora_utc': [5, 1329],
                              'satelite': ['S-NPP', 'Terra'], 'frp': [2., 3.],
                              'daynight': ['N', 'D'], 'peso_harmonizado': [1., 2.25]}).to_parquet(path)
                files.append((str(path), path.stat().st_mtime_ns))
            points, exceeded = search_hotspots(tuple(files), date(2024, 12, 31), date(2025, 1, 1),
                                               'All available sensors', None)
            self.assertFalse(exceeded)
            self.assertEqual(len(points), 2)
            self.assertEqual(points.peso_harmonizado.sum(), 3.25)
            export = point_export(points)
            self.assertEqual(export.time_utc.tolist(), ['13:29', '00:05'])
            decoded = pd.read_csv(io.StringIO(export.to_csv(index=False)))
            self.assertEqual(decoded.harmonized_weight.sum(), 3.25)
            clipped, _ = search_hotspots(tuple(files), date(2024, 12, 30), date(2025, 1, 2),
                                         'VIIRS S-NPP', box(-56.5, -18.5, -56, -18).wkt)
            self.assertEqual(len(clipped), 2)
            partial, exceeded = search_hotspots(tuple(files), date(2024, 12, 30), date(2025, 1, 2),
                                                'All available sensors', None, limit=2)
            self.assertTrue(exceeded)
            self.assertEqual(len(partial), 2)
            empty, _ = search_hotspots(tuple(files), date(2024, 12, 30), date(2025, 1, 2),
                                       'VIIRS S-NPP', box(0, 0, 1, 1).wkt)
            self.assertTrue(point_export(empty).empty)
            for start, end in [(date(2024, 1, 1), date(2024, 4, 2)),
                               (date(2024, 2, 1), date(2024, 1, 1))]:
                with self.assertRaises(ValueError):
                    search_hotspots(tuple(files), start, end, 'All available sensors', None)

    def test_exact_interval_coverage_does_not_treat_missing_months_as_zero(self):
        coverage = pd.DataFrame({'ano': [2026, 2026], 'mes': [10, 11], 'incompleto': [False, True]})
        self.assertEqual(interval_coverage(date(2026, 10, 1), date(2026, 10, 7), coverage),
                         'No monthly completeness flag')
        self.assertIn('Provisional', interval_coverage(date(2026, 10, 30), date(2026, 11, 2), coverage))
        self.assertIn('Outside', interval_coverage(date(2026, 12, 1), date(2026, 12, 2), coverage))
        self.assertFalse(sensor_interval_coverage('VIIRS S-NPP', date(2011, 12, 31), date(2012, 1, 1)))
        self.assertFalse(sensor_interval_coverage('MODIS Terra + Aqua', date(2012, 1, 1), date(2012, 1, 2)))
        self.assertTrue(sensor_interval_coverage('All available sensors', date(2011, 12, 31), date(2012, 1, 1)))

    def test_hotspot_locations_filter_date_sensor_and_exact_coordinates(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'points.parquet'
            pd.DataFrame({'lat': [-18.19, -18.18, -18.17], 'lon': [-56.41] * 3,
                          'data': pd.to_datetime(['2025-12-01', '2026-01-01', '2025-12-02']),
                          'hora_utc': [1200] * 3, 'satelite': ['S-NPP', 'S-NPP', 'Terra'],
                          'frp': [2.] * 3, 'peso_harmonizado': [1.] * 3}).to_parquet(path)
            points = hotspot_locations(str(path), path.stat().st_mtime_ns, 2025, 12,
                                       'VIIRS S-NPP', box(-57, -19, -56, -18).wkt)
            self.assertEqual(len(points), 1)
            self.assertEqual(points.lat.iloc[0], -18.19)
            import folium
            view = folium.Map(tiles=None, prefer_canvas=True)
            add_hotspot_locations(view, points, .8)
            fire_legend(True, 'Hotspot locations', 'Dec 2025').add_to(view)
            html = view.get_root().render()
            self.assertIn('#FF241C', html)
            self.assertIn('[-56.41, -18.19]', html)
            self.assertNotIn('Activity glow', html)

    def test_signal_view_preserves_counts_and_marks_only_cell_centers(self):
        cells = pd.DataFrame({'lat': [-18.25, -18.0], 'lon': [-56.5, -56.25],
                              'hotspots': [5.75, 1200.5]})
        points = fire_signal_features(cells, 'MODIS converted', 2010, 9)['features']
        self.assertEqual(points[0]['geometry'], {'type': 'Point', 'coordinates': [-56.375, -18.125]})
        self.assertEqual(sum(p['properties']['hotspots'] for p in points), cells.hotspots.sum())
        self.assertLess(points[0]['properties']['radius'], points[1]['properties']['radius'])
        self.assertLessEqual(points[1]['properties']['radius'], 15)
        self.assertIn('aggregate cell', points[0]['properties']['location_type'])
        import folium
        view = folium.Map(tiles=None)
        add_activity_layer(view, cells, 'MODIS converted', 2010, 9, .8, 'Signal view')
        fire_legend(True, 'Signal view', 'Sep 2010').add_to(view)
        html = view.get_root().render()
        self.assertIn('L.CircleMarker', html)
        self.assertIn('ember-map-legend', html)
        self.assertIn('Sep 2010', html)
        self.assertIn('requestFullscreen', html)

    def test_scientific_satellite_grid_aggregates_passes_without_mixing_sensors(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'grid_sat.parquet'
            pd.DataFrame({'lat': [-18.25] * 4, 'lon': [-56.5] * 4, 'ano': [2024] * 4,
                          'mes': [9] * 4, 'satellite': ['S-NPP', 'S-NPP', 'Terra', 'Aqua'],
                          'daynight': ['D', 'N', 'D', 'D'], 'n': [10, 20, 5, 7]}).to_parquet(path)
            version = path.stat().st_mtime_ns
            viirs = observation_cells(str(path), version, 'VIIRS S-NPP', 2024, 9, None)
            modis = observation_cells(str(path), version, 'MODIS Terra + Aqua', 2024, 9, None)
            self.assertEqual(viirs.hotspots.sum(), 30)
            self.assertEqual(modis.hotspots.sum(), 12)
            self.assertEqual(len(observation_months(str(path), version, 'VIIRS S-NPP')), 1)

    def test_harmonized_map_preserves_fractional_values_and_incomplete_flag(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'harmonized.parquet'
            pd.DataFrame({'lat': [-18.25, -18.25], 'lon': [-56.5, -56.], 'ano': [2010, 2010],
                          'mes': [9, 9], 'focos_harmonizados': [5.75, 100.25],
                          'fonte': ['modis_convertido'] * 2, 'dado_incompleto': [True] * 2}).to_parquet(path)
            cells = harmonized_map_cells(str(path), path.stat().st_mtime_ns, 2010, 9, None)
            self.assertEqual(cells.hotspots.sum(), 106.)
            self.assertTrue(cells.incomplete.all())
            features = fire_features(cells, 'MODIS converted', 2010, 9)['features']
            self.assertEqual(features[0]['properties']['hotspots'], 100.25)
            self.assertEqual(features[1]['properties']['hotspots'], 5.75)
            self.assertEqual(features[1]['properties']['range'], '>5–20')

    def test_fire_classes_and_cell_geometry(self):
        self.assertEqual([fire_class(value) for value in [1, 5, 6, 20, 21, 100, 101, 500, 501]],
                         [0, 0, 1, 1, 2, 2, 3, 3, 4])
        cells = pd.DataFrame({'lat': [-18.25], 'lon': [-56.5], 'hotspots': [501]})
        feature = fire_features(cells, 'VIIRS S-NPP', 2024, 9)['features'][0]
        from shapely.geometry import shape
        self.assertEqual(shape(feature['geometry']).bounds, (-56.5, -18.25, -56.25, -18.0))
        self.assertEqual(feature['properties']['range'], 'More than 500')
        self.assertEqual(feature['properties']['hotspots'], 501)
        import folium
        view = folium.Map()
        fire_legend().add_to(view)
        self.assertIn('NASA FIRMS monthly hotspot count legend', view.get_root().render())

    def test_observed_layer_queries_sensor_and_month(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'observations.parquet'
            pd.DataFrame({'lat': [-18.25, -18.25, -18.25],
                          'lon': [-56.5, -56.5, -56.0], 'ano': [2024] * 3,
                          'mes': [8, 9, 9], 'n_modis': [3, 5, 7],
                          'n_viirs': [10, 20, 30]}).to_parquet(path)
            version = path.stat().st_mtime_ns
            self.assertEqual(list(observation_months(str(path), version, 'VIIRS S-NPP').mes), [8, 9])
            selected = observation_cells(str(path), version, 'VIIRS S-NPP', 2024, 9,
                                         box(-56.4, -18.2, -56.3, -18.0).wkt)
            self.assertEqual(selected.hotspots.sum(), 20)
            modis = observation_cells(str(path), version, 'MODIS Terra + Aqua', 2024, 9, None)
            self.assertEqual(modis.hotspots.sum(), 12)
            with self.assertRaises(ValueError):
                observation_cells(str(path), version, 'unknown', 2024, 9, None)

    def test_dataset_contract_reports_missing_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'missing.parquet'
            pd.DataFrame({'lat': [0.]}).to_parquet(path)
            with self.assertRaisesRegex(ValueError, 'Missing columns'):
                metadata(str(path), path.stat().st_mtime_ns)
            invalid = Path(temporary) / 'invalid.parquet'
            pd.DataFrame({'lat': [-18.], 'lon': [-56.], 'ano': [2025], 'mes': [1],
                          'focos_harmonizados': [-1.], 'fonte': ['viirs'],
                          'dado_incompleto': [False]}).to_parquet(invalid)
            with self.assertRaisesRegex(ValueError, 'invalid records'):
                metadata(str(invalid), invalid.stat().st_mtime_ns)

    def test_real_file_takes_priority_without_silent_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            real, mock = Path(temporary) / 'real.parquet', Path(temporary) / 'mock.parquet'
            mock.touch()
            with patch('app.app.REAL', real), patch('app.app.MOCK', mock):
                self.assertEqual(data_source()[0], str(mock))
                real.touch()
                self.assertEqual(data_source()[0], str(real))

    def test_coverage_zero_and_incomplete_months(self):
        coverage = pd.DataFrame({
            'ano': [2025, 2025, 2025], 'mes': [1, 2, 3],
            'incompleto': [False, True, False], 'source': ['viirs'] * 3})
        raw = pd.DataFrame({'ano': [2025], 'mes': [1], 'focos': [10.0],
                            'incompleto': [False]})
        result = complete_months(raw, coverage, 2025, 2025)
        self.assertEqual(len(result), 12)
        self.assertEqual(result.loc[1, 'focos'], 0)
        self.assertTrue(result.loc[1, 'incompleto'])
        self.assertEqual(result.loc[2, 'focos'], 0)
        self.assertTrue(result.loc[3:, 'focos'].isna().all())
        self.assertTrue(result.loc[3:, 'incompleto'].all())
        fig = calendar_figure(result)
        self.assertEqual(fig.data[0].text[0][1], '0*')

    def test_cell_centers_and_regional_sum(self):
        # First center (-56.375, -18.125) is inside; second is outside.
        data = pd.DataFrame({
            'lat': [-18.25, -18.25, -18.25], 'lon': [-56.5, -56.5, -56.0],
            'ano': [2020] * 3, 'mes': [1, 2, 2],
            'focos_harmonizados': [10., 20., 900.], 'fonte': ['viirs'] * 3,
            'dado_incompleto': [False, False, True]})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'sample.parquet'
            data.to_parquet(path, index=False)
            polygon = box(-56.4, -18.2, -56.3, -18.0)
            result = cached_series(str(path), path.stat().st_mtime_ns,
                                   polygon.wkt, 2020, 2020)
            self.assertEqual(result.loc[0, 'focos'], 10)
            self.assertEqual(result.loc[1, 'focos'], 20)
            self.assertTrue(result.loc[1, 'incompleto'])
            empty = cached_series(str(path), path.stat().st_mtime_ns,
                                  box(-40, -10, -39, -9).wkt, 2020, 2020)
            self.assertEqual(empty.focos.sum(), 0)

    def test_drawing_union_delete_and_invalid(self):
        shapes = [box(-58, -20, -56, -18), box(-57, -19, -55, -16)]
        result = drawn_region({'all_drawings': [
            {'geometry': mapping(polygon)} for polygon in shapes]})
        import shapely
        self.assertTrue(shapely.from_wkt(result).equals(shapes[0].union(shapes[1])))
        self.assertIsNone(drawn_region({'all_drawings': [],
                                       'last_active_drawing': {'geometry': mapping(shapes[0])}}))
        with self.assertRaises(ValueError):
            drawn_region({'all_drawings': [{'geometry': mapping(Point(0, 0))}]})

    def test_radius_distance_at_southern_latitude(self):
        lat, lon, radius = -30., -55., 100.
        circle = radius_polygon(lat, lon, radius)
        self.assertTrue(circle.contains(Point(lon, lat)))
        for x, y in circle.exterior.coords:
            a = (math.sin(math.radians(y - lat) / 2) ** 2
                 + math.cos(math.radians(lat)) * math.cos(math.radians(y))
                 * math.sin(math.radians(x - lon) / 2) ** 2)
            distance = 6371.0088 * 2 * math.asin(math.sqrt(a))
            self.assertAlmostEqual(distance, radius, places=6)

    def test_csv_anomalies_zero_baseline_and_mock_label(self):
        series = pd.DataFrame({
            'ano': [2020, 2021, 2020, 2021], 'mes': [1, 1, 2, 2],
            'focos': [10., 30., 0., 0.], 'incompleto': [False] * 4})
        coverage = series[['ano', 'mes']].assign(source='viirs')
        result = export_table(series, coverage, None, 'mock')
        self.assertTrue(pd.isna(result.anomaly_pct.iloc[0]))
        self.assertEqual(result.anomaly_pct.iloc[1], 200.)
        self.assertTrue(result.anomaly_pct.iloc[2:].isna().all())
        self.assertFalse(np.isinf(result.anomaly_pct).any())
        decoded = pd.read_csv(io.BytesIO(result.to_csv(index=False).encode('utf-8-sig')))
        self.assertEqual(decoded.hotspots.sum(), series.focos.sum())
        self.assertTrue((decoded.dataset == 'mock').all())

    def test_latest_month_baseline_excludes_current_and_incomplete(self):
        series = pd.DataFrame({'ano': [2020, 2021, 2022, 2023, 2024],
                               'mes': [9] * 5, 'focos': [10., 20., 9999., 30., 100.],
                               'incompleto': [False, False, True, False, False]})
        summary = latest_comparison(series)
        self.assertEqual(summary['median'], 20.)
        self.assertEqual(summary['category'], 'Critical')
        self.assertEqual(summary['delta'], 400.)
        self.assertEqual(anomaly_values(series).iloc[-1], 400.)
        self.assertTrue(pd.isna(anomaly_values(series).iloc[2]))
        series.loc[4, 'incompleto'] = True
        summary = latest_comparison(series)
        self.assertEqual(summary['year'], 2023)
        self.assertEqual(summary['median'], 15.)
        self.assertEqual(summary['delta'], 100.)
        self.assertEqual(summary['newer_incomplete'], ['Sep 2024'])

    def test_latest_complete_month_skips_multiple_provisional_months(self):
        series = pd.DataFrame({'ano': [2025, 2026, 2026, 2026],
                               'mes': [10, 10, 11, 12], 'focos': [10., 0., 12., 9.],
                               'incompleto': [False, False, True, True]})
        summary = latest_comparison(series.sample(frac=1, random_state=7))
        self.assertEqual((summary['year'], summary['month']), (2026, 10))
        self.assertEqual(summary['value'], 0.)
        self.assertEqual(summary['delta'], -100.)
        self.assertEqual(summary['newer_incomplete'], ['Nov 2026', 'Dec 2026'])
        series['incompleto'] = True
        self.assertEqual(latest_comparison(series), {})
        self.assertEqual(latest_comparison(series.iloc[:0]), {})

    def test_latest_coverage_zero_count_and_no_false_alert(self):
        series = pd.DataFrame({'ano': [2020, 2021, 2022, 2023, 2023],
                               'mes': [1, 1, 1, 1, 2], 'focos': [0., 0., 0., 0., np.nan],
                               'incompleto': [False, False, False, False, True]})
        summary = latest_comparison(series)
        self.assertEqual(summary['month'], 1)
        self.assertEqual(summary['year'], 2023)
        self.assertEqual(summary['category'], 'Normal')
        self.assertIsNone(summary['delta'])

    def test_calendar_anomalies_match_csv_and_center_on_zero(self):
        rows = [(year, month, float(10 * 2 ** (year - 2020)) if month == 1 else 0., False)
                for year in range(2020, 2024) for month in range(1, 13)]
        series = pd.DataFrame(rows, columns=['ano', 'mes', 'focos', 'incompleto'])
        coverage = series[['ano', 'mes']].assign(source='viirs')
        export = export_table(series, coverage, None, 'mock')
        figure = calendar_figure(series, anomaly=True)
        self.assertEqual(figure.data[0].z[3][0], 300.)
        self.assertEqual(export.loc[(export.year == 2023) & (export.month == 1), 'anomaly_pct'].iloc[0], 300.)
        self.assertEqual(figure.layout.coloraxis.cmin, -figure.layout.coloraxis.cmax)
        self.assertEqual(figure.layout.coloraxis.cmid, 0)


class ApplicationTests(unittest.TestCase):
    def test_map_workspace_opens_first_without_hidden_calendar_rendering(self):
        with patch('streamlit_folium.st_folium', return_value={}):
            app = AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.tabs[0].label, 'Fire map')
            self.assertEqual(len(app.get('plotly_chart')), 0)
            self.assertEqual(app.selectbox(key='fire_product').value, 'Harmonized activity')
            self.assertEqual(app.slider(key='fire_opacity').value, .8)
            self.assertEqual(len(app.get('download_button')), 1)
            app.selectbox(key='fire_product').select('Sensor observations').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.selectbox(key='fire_sensor').value, 'VIIRS S-NPP')

    def test_example_regions_and_empty_selection(self):
        with patch('streamlit_folium.st_folium', return_value={'all_drawings': None}):
            app = AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=30)
            app.session_state['main_tabs'] = 'Calendar'
            app.run()
            for name in ['Pantanal', 'Matopiba', 'Acre']:
                app.selectbox(key='example_region').select(name).run()
                app.button(key='apply_example').click().run()
                self.assertFalse(app.exception)
                self.assertIn(name, app.session_state['region_label'])
                self.assertEqual(app.radio(key='region_mode').value, 'Lat-Lon + radius')
            app.number_input(key='latitude').set_value(-30.)
            app.number_input(key='longitude').set_value(-35.)
            app.number_input(key='radius').set_value(5.)
            app.button(key='update').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('No grid-cell centers' in w.value for w in app.warning))

    def test_methodology_missing_and_invalid_metrics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch('app.app.ROOT', root):
                app = AppTest.from_string('from app.app import show_methodology\nshow_methodology(True)').run()
                self.assertFalse(app.exception)
                self.assertTrue(any('pending' in c.value.lower() for c in app.caption))
                (root / 'reports').mkdir()
                (root / 'reports/metrics.json').write_text('{invalid', encoding='utf-8')
                app.run()
                self.assertFalse(app.exception)
                self.assertTrue(any('could not be loaded' in w.value for w in app.warning))

    def test_drawing_persists_and_delete_resets_region(self):
        payload = {'all_drawings': None}
        with patch('streamlit_folium.st_folium', side_effect=lambda *args, **kwargs: payload):
            app = AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=30)
            app.session_state['main_tabs'] = 'Calendar'
            app.run()
            payload['all_drawings'] = [{'geometry': mapping(box(-58, -20, -55, -16))}]
            app.run()
            self.assertFalse(app.exception)
            self.assertIsNone(app.session_state['regiao'])
            app.button(key='apply_map').click().run()
            selected = app.session_state['regiao']
            self.assertIsNotNone(selected)
            app.run()
            self.assertEqual(app.session_state['regiao'], selected)
            payload['all_drawings'] = []
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['regiao'], selected)
            app.button(key='apply_map').click().run()
            self.assertIsNone(app.session_state['regiao'])

    def test_coordinate_update_reset_and_download(self):
        # Leaflet is browser-only; verify Python UI behavior separately.
        with patch('streamlit_folium.st_folium', return_value={'all_drawings': None}):
            app = AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=30)
            app.session_state['main_tabs'] = 'Calendar'
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.tabs), 6)
            app.radio(key='region_mode').set_value('Lat-Lon + radius').run()
            app.slider(key='year_range').set_value((2015, 2020))
            app.number_input(key='radius').set_value(100.)
            app.button(key='update').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['applied_years'], (2015, 2020))
            self.assertIsNotNone(app.session_state['regiao'])
            self.assertEqual(len(app.get('download_button')), 1)
            app.radio(key='region_mode').set_value('Draw on map').run()
            app.radio(key='region_mode').set_value('Lat-Lon + radius').run()
            self.assertEqual(app.number_input(key='radius').value, 100.)
            app.button(key='reset_region').click().run()
            self.assertFalse(app.exception)
            self.assertIsNone(app.session_state['regiao'])


if __name__ == '__main__':
    unittest.main()
