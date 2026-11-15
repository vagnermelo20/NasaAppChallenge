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
from shapely.geometry import Point, Polygon, box, mapping
from streamlit.testing.v1 import AppTest
from app.check_release import inspect_release

from app.app import (anomaly_values, cached_series, calendar_figure, complete_months,
                     data_source, drawn_region, export_table, latest_comparison, metadata,
                     hotspot_locations, add_hotspot_locations, map_legend, unified_notice, season_text,
                     area_sentences, search_hotspots, point_export, interval_coverage, heat_cells,
                     radius_polygon, search_table, add_heat, heat_top, view_box, dots_in_view, with_heat_rank,
                     map_summary, heat_square, area_point_totals, area_points, SEARCH_PAGE_SIZE)


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
            self.assertEqual(decoded.hotspots_common_scale.sum(), 3.25)       # unified: no satellite in the CSV
            for removed in ['satellite', 'frp_mw', 'daynight']:
                self.assertNotIn(removed, decoded.columns)
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
            with self.assertRaises(ValueError):
                search_hotspots(tuple(files), date(2024, 2, 1), date(2024, 1, 1), 'All available sensors', None)
            newest, _ = search_hotspots(tuple(files), date(2024, 1, 1), date(2025, 12, 31),
                                        'All available sensors', None, newest_first=True)
            self.assertEqual(str(newest.data.iloc[0])[:10], '2025-01-02')        # long periods are allowed
            common, total, cells = map_summary(tuple(files), date(2024, 1, 1), date(2025, 12, 31), .5)
            self.assertEqual(total, 4)                                   # satellite detections
            self.assertEqual(common, 1. + 2.25 + 1. + 2.25)              # common scale: sum of harmonized weights
            self.assertEqual(cells.n.sum(), common)
            screen = view_box({'_southWest': {'lat': -18.5, 'lng': -56.5}, '_northEast': {'lat': -18.0, 'lng': -56.0}})
            assert screen is not None
            count, dots = dots_in_view(tuple(files), date(2024, 1, 1), date(2025, 12, 31), screen)
            self.assertEqual((count, len(dots)), (2, 2))                          # all dots on screen, no cap
            self.assertIsNone(view_box(None))

    def test_pagination_filters_polygon_holes_before_limit_and_preserves_full_totals(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'points.parquet'
            # Points 0 and 2 are inside the bounding box but in the polygon hole.
            data = pd.DataFrame({'lat': [2., 1., 2., 3.], 'lon': [2., 1., 2., 3.],
                                 'data': pd.to_datetime(['2025-01-01'] * 4),
                                 'hora_utc': [0, 100, 200, 300], 'satelite': ['S-NPP'] * 4,
                                 'frp': [50., 2., 50., 4.], 'daynight': ['D'] * 4,
                                 'peso_harmonizado': [100., 1.25, 100., 2.75]})
            data.to_parquet(path)
            files = ((str(path), path.stat().st_mtime_ns),)
            region = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)],
                             holes=[[(1.5, 1.5), (2.5, 1.5), (2.5, 2.5), (1.5, 2.5)]]).wkt
            first, more = search_hotspots(files, date(2025, 1, 1), date(2025, 1, 1),
                                          'All available sensors', region, limit=1)
            last, last_more = search_hotspots(files, date(2025, 1, 1), date(2025, 1, 1),
                                              'All available sensors', region, limit=1, offset=1)
            self.assertTrue(more)
            self.assertFalse(last_more)
            self.assertEqual(first.hora_utc.tolist(), [100])
            self.assertEqual(last.hora_utc.tolist(), [300])
            count, total = area_point_totals(files, date(2025, 1, 1), date(2025, 1, 1), region)
            self.assertEqual(count, 2)
            self.assertEqual(total, 4.)
            self.assertNotEqual(first.peso_harmonizado.sum(), total)
            self.assertEqual(area_point_totals(files, date(2025, 1, 1), date(2025, 1, 1),
                                              box(10, 10, 11, 11).wkt), (0, 0.))
            everything = area_points(files, date(2025, 1, 1), date(2025, 1, 1), region)   # no cap, hole excluded
            self.assertEqual(everything.hora_utc.tolist(), [100, 300])
            self.assertEqual(everything.peso_harmonizado.sum(), total)

    def test_default_page_limit_keeps_last_page_without_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'points.parquet'
            size = SEARCH_PAGE_SIZE + 3
            pd.DataFrame({'lat': np.linspace(-20, -19, size), 'lon': [-50.] * size,
                          'data': pd.to_datetime(['2025-01-01'] * size),
                          'hora_utc': [1200] * size, 'satelite': ['S-NPP'] * size,
                          'frp': np.arange(size, dtype=float), 'daynight': ['D'] * size,
                          'peso_harmonizado': [1.] * size}).to_parquet(path)
            files = ((str(path), path.stat().st_mtime_ns),)
            first, more = search_hotspots(files, date(2025, 1, 1), date(2025, 1, 1),
                                          'All available sensors', None)
            last, last_more = search_hotspots(files, date(2025, 1, 1), date(2025, 1, 1),
                                              'All available sensors', None, offset=SEARCH_PAGE_SIZE)
            self.assertEqual(len(first), SEARCH_PAGE_SIZE)
            self.assertTrue(more)
            self.assertEqual(len(last), 3)
            self.assertFalse(last_more)
            joined = pd.concat([first, last], ignore_index=True)
            self.assertEqual(joined.frp.tolist(), list(np.arange(size, dtype=float)))
            self.assertEqual(joined.frp.nunique(), size)
            self.assertEqual(area_point_totals(files, date(2025, 1, 1), date(2025, 1, 1), None),
                             (size, float(size)))
            oversized, _ = search_hotspots(files, date(2025, 1, 1), date(2025, 1, 1),
                                           'All available sensors', None, limit=size)
            self.assertEqual(len(oversized), SEARCH_PAGE_SIZE)
            with self.assertRaises(ValueError):
                search_hotspots(files, date(2025, 1, 1), date(2025, 1, 1),
                                'All available sensors', None, limit=0)
            with self.assertRaises(ValueError):
                search_hotspots(files, date(2025, 1, 1), date(2025, 1, 1),
                                'All available sensors', None, offset=-1)

    def test_exact_interval_coverage_does_not_treat_missing_months_as_zero(self):
        coverage = pd.DataFrame({'ano': [2026, 2026], 'mes': [10, 11], 'incompleto': [False, True]})
        self.assertEqual(interval_coverage(date(2026, 10, 1), date(2026, 10, 7), coverage),
                         'No monthly completeness flag')
        self.assertIn('Provisional', interval_coverage(date(2026, 10, 30), date(2026, 11, 2), coverage))
        self.assertIn('Outside', interval_coverage(date(2026, 12, 1), date(2026, 12, 2), coverage))







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


class SimpleMapTests(unittest.TestCase):
    def test_hotspot_locations_filter_date_sensor_and_exact_coordinates(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'points.parquet'
            pd.DataFrame({'lat': [-18.19, -18.18, -18.17], 'lon': [-56.41] * 3,
                          'data': pd.to_datetime(['2025-12-01', '2026-01-01', '2025-12-02']),
                          'hora_utc': [1200] * 3, 'satelite': ['S-NPP', 'S-NPP', 'Terra'],
                          'frp': [2.] * 3, 'daynight': ['D'] * 3, 'peso_harmonizado': [1.] * 3}).to_parquet(path)
            points = hotspot_locations(str(path), path.stat().st_mtime_ns, 2025, 12,
                                       'VIIRS S-NPP', box(-57, -19, -56, -18).wkt)
            self.assertEqual(len(points), 1)
            self.assertEqual(points.lat.iloc[0], -18.19)

    def test_one_colour_dots_with_simple_popup(self):
        points = pd.DataFrame({'lat': [-18.19, -10.0], 'lon': [-56.41, -50.0],
                               'data': pd.to_datetime(['2026-11-02', '2026-11-01']),
                               'hora_utc': [1530, 200], 'satelite': ['S-NPP', 'Terra'], 'frp': [1.1, 40.]})
        ranked = with_heat_rank(points)
        self.assertTrue(ranked.frp_pct.between(0, 99).all())
        self.assertLess(ranked.frp_pct.iloc[0], 50)                   # 1.1 MW is weak for VIIRS
        import folium
        view = folium.Map(tiles=None, prefer_canvas=True)
        add_hotspot_locations(view, ranked)
        html = view.get_root().render()
        self.assertIn('#E8251B', html)                                # one colour for every dot
        self.assertNotIn('#FF8C1A', html)
        self.assertIn('[-56.41, -18.19]', html)
        self.assertIn('02 Nov 2026, 12:30', html)                     # 15:30 UTC -> Brasília time
        self.assertIn('31 Oct 2026, 23:00', html)                     # crossing midnight
        for text in ['When', 'Heat strength', 'stronger than']:
            self.assertIn(text, html)
        for removed in ['Seen by', 'MODIS', 'VIIRS', 'older', 'satellite', 'night pass', 'square', 'normal']:
            self.assertNotIn(removed, html)
        self.assertIn('click it', map_legend())
        notice = unified_notice()
        self.assertIn('raw satellite detections', notice)
        self.assertIn('single unified record', notice)
        self.assertIn('font-size:1.25rem', notice)

    def test_fire_season_in_plain_words(self):
        self.assertEqual(season_text([8, 9, 10]), ('Aug to Oct', 8))
        self.assertEqual(season_text([1, 2, 12]), ('Dec to Feb', 12))
        self.assertEqual(season_text([3, 9]), ('Mar, Sep', 3))
        series = pd.DataFrame({'ano': np.repeat([2020, 2021, 2022, 2023], 12), 'mes': np.tile(range(1, 13), 4),
                               'focos': np.tile([1, 1, 1, 1, 1, 1, 5, 50, 100, 60, 2, 1], 4).astype(float),
                               'incompleto': False})
        lines = area_sentences(series)
        self.assertIn('Aug to Oct', lines[0])
        self.assertIn('**Sep**', lines[0])
        self.assertIn('Jun and Jul', lines[1])
        self.assertTrue(any('about the usual' in line for line in lines))
        self.assertEqual(area_sentences(series.assign(focos=0.)), [])

    def test_far_glow_near_dots(self):
        grouped = pd.DataFrame({'lat': [-10., -20.], 'lon': [-50., -45.], 'n': [2, 1]})
        cells = heat_cells(grouped)
        self.assertEqual(len(cells), 2)
        self.assertEqual(max(c[2] for c in cells), 1.)
        self.assertEqual(heat_cells(grouped.iloc[:0]), [])
        self.assertEqual([heat_square(date(2026, 1, 1), d) for d in [date(2026, 1, 31), date(2027, 1, 1), date(2030, 1, 1)]],
                         [.05, .1, .2])
        week, month = heat_top(date(2005, 9, 1), date(2005, 9, 7), .05), heat_top(date(2005, 9, 1), date(2005, 9, 30), .05)
        self.assertEqual((week, month), (14., 60.))                     # fixed ruler: same dates -> same scale any year
        self.assertEqual(heat_top(date(2024, 9, 1), date(2024, 9, 30), .05), month)
        self.assertEqual(heat_cells(grouped, top=4.), [[-10.0, -50.0, .5], [-20.0, -45.0, .25]])
        import folium
        view = folium.Map(tiles=None)
        add_heat(view, grouped)
        html = view.get_root().render()
        self.assertIn('L.heatLayer', html)
        self.assertIn('instanceof L.CircleMarker', html)

    def test_search_circle_and_plain_table(self):
        lat, lon, radius = -30., -55., 100.
        circle = radius_polygon(lat, lon, radius)
        self.assertTrue(circle.contains(Point(lon, lat)))
        for x, y in circle.exterior.coords:
            a = (math.sin(math.radians(y - lat) / 2) ** 2
                 + math.cos(math.radians(lat)) * math.cos(math.radians(y))
                 * math.sin(math.radians(x - lon) / 2) ** 2)
            self.assertAlmostEqual(6371.0088 * 2 * math.asin(math.sqrt(a)), radius, places=6)
        table = search_table(pd.DataFrame({'lat': [-30.12345], 'lon': [-55.], 'data': pd.to_datetime(['2026-11-02']),
                                           'hora_utc': [130], 'satelite': ['Aqua'], 'frp': [12.34]}))
        self.assertEqual(table.iloc[0]['When (Brasília time)'], pd.Timestamp('2026-11-01 22:30'))
        self.assertEqual(list(table.columns), ['When (Brasília time)', 'Latitude', 'Longitude'])   # no satellite, no MW

def app_test():
    return AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=60)


class ApplicationTests(unittest.TestCase):
    def test_opens_on_simple_map_with_three_tabs(self):
        with patch('streamlit_folium.st_folium', return_value={}):
            app = app_test().run()
            self.assertFalse(app.exception)
            self.assertEqual([tab.label for tab in app.tabs[:2]], ['Map', 'How it works'])
            self.assertEqual(app.get('segmented_control')[0].value, 'Latest 7 days')
            self.assertEqual(len(app.sidebar), 0)
            self.assertEqual(len(app.get('download_button')), 1)
            self.assertTrue(app.button(key='apply_map').disabled)
            text = ' '.join(m.value for m in app.markdown) + ' '.join(c.value for c in app.caption)
            for jargon in ['UTC', '0.25°', 'VIIRS', 'MODIS', 'older satellite', 'newer satellite', 'A2', 'grid cell']:
                self.assertNotIn(jargon, text)

    def test_drawing_persists_and_delete_resets_region(self):
        payload = {'all_drawings': None}
        with patch('streamlit_folium.st_folium', side_effect=lambda *args, **kwargs: payload):
            app = app_test().run()
            payload['all_drawings'] = [{'geometry': mapping(box(-58, -20, -55, -16))}]
            app.run()
            self.assertFalse(app.exception)
            self.assertIsNone(app.session_state['regiao'])
            app.button(key='apply_map').click().run()
            selected = app.session_state['regiao']
            self.assertIsNotNone(selected)
            self.assertTrue(any('Your area' in m.value for m in app.markdown))
            app.run()
            self.assertEqual(app.session_state['regiao'], selected)
            payload['all_drawings'] = []
            app.run()
            self.assertEqual(app.session_state['regiao'], selected)
            app.button(key='apply_map').click().run()
            self.assertIsNone(app.session_state['regiao'])

    def test_tiny_area_and_clear(self):
        payload = {'all_drawings': [{'geometry': mapping(box(-35.01, -30.01, -35.0, -30.0))}]}
        with patch('streamlit_folium.st_folium', side_effect=lambda *args, **kwargs: payload):
            app = app_test().run()
            app.button(key='apply_map').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('too small' in w.value for w in app.warning))
            payload['all_drawings'] = None
            app.button(key='reset_region').click().run()
            self.assertFalse(app.exception)
            self.assertIsNone(app.session_state['regiao'])

    def test_how_it_works_and_type_a_place_on_the_map(self):
        with patch('streamlit_folium.st_folium', return_value={}):
            app = app_test()
            app.session_state['main_tabs'] = 'How it works'
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(any('simple words' in s.value for s in app.subheader))
            explanation = ' '.join(m.value for m in app.markdown)
            self.assertIn('monthly activity', explanation)
            self.assertIn('Daily values before 2012 are approximate', explanation)
            self.assertIn('73.7%', explanation)                              # technical limits stay in the expander
            self.assertIn('85%', explanation)                                # natural limit, not a target
            self.assertNotIn('80%', explanation)
            app.session_state['main_tabs'] = 'Map'
            app.run()
            header = ' '.join(c.value for c in app.caption)
            self.assertIn('Archive:', header)
            self.assertIn('Latest recorded detection in this archive:', header)
            self.assertIn('not a live emergency feed', header)
            self.assertTrue(any('Draw an area or type a place' in c.value for c in app.caption))
            app.number_input(key='place_lat').set_value(-5.)
            app.number_input(key='place_lon').set_value(-45.)
            app.number_input(key='place_radius').set_value(50.)
            app.button(key='place_submit').click().run()
            self.assertFalse(app.exception)
            self.assertIsNotNone(app.session_state['regiao'])
            self.assertIn('50 km around -5.0000, -45.0000', app.session_state['region_label'])
            self.assertTrue(any('hot spots** inside your area' in c.value for c in app.caption))
            self.assertEqual(len(app.dataframe), 1)

    def test_area_page_has_calendar_timescales_and_usual_year(self):
        with patch('streamlit_folium.st_folium', return_value={}):
            app = app_test().run()
            self.assertFalse(app.exception)
            titles = ' '.join(m.value for m in app.markdown)
            for part in ['Fire calendar', 'Day, week or month', 'A usual year here', 'Hot spots per year', 'worse than usual']:
                self.assertIn(part, titles)
            app.toggle(key='anomaly_mode').set_value(True).run()
            self.assertFalse(app.exception)
            for scale in ['Day', 'Month']:
                app.session_state['timescale'] = scale
                app.run()
                self.assertFalse(app.exception, scale)
            app.session_state['timescale'] = 'Day'
            app.run()
            notes = ' '.join(c.value for c in app.caption)
            self.assertIn('single common scale', notes)          # one unified series, no satellite names
            self.assertNotIn('best satellite', notes)


if __name__ == '__main__':
    unittest.main()
