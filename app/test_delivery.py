"""Regression checks for spatial selection, coverage and CSV consistency.

Run: .venv/Scripts/python.exe -m unittest app.test_delivery -v
"""
import io
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from shapely.geometry import Point, box, mapping
from streamlit.testing.v1 import AppTest

from app.app import (anomaly_values, cached_series, calendar_figure, complete_months,
                     drawn_region, export_table, latest_comparison, radius_polygon)


class CalendarDataTests(unittest.TestCase):
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
        self.assertEqual(summary['category'], 'Incomplete month')
        self.assertIsNone(summary['delta'])

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
            app = AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=30).run()
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
            app = AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.tabs), 4)
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
