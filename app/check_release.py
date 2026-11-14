"""Read-only artifact readiness report. Run from root: python -m app.check_release."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def inspect_release(root: Path) -> dict:
    missing = []
    invalid = []
    dataset = root / 'data/processed/harmonized.parquet'
    summary = None
    if not dataset.is_file():
        missing.append('data/processed/harmonized.parquet')
    else:
        try:
            # Reuse the app's basic validation, without launching a UI or altering files.
            from app.app import metadata
            coverage = metadata(str(dataset), dataset.stat().st_mtime_ns)
            if coverage.empty:
                raise ValueError('Dataset has no observations.')
            summary = {
                'first_year': int(coverage.ano.min()),
                'last_year': int(coverage.ano.max()),
                'months_with_records': len(coverage),
                'incomplete_months': int(coverage.incompleto.sum()),
            }
        except Exception as error:
            invalid.append(f'data/processed/harmonized.parquet: {error}')
    document = root / 'docs/metodologia.md'
    if not document.is_file():
        missing.append('docs/metodologia.md')
    else:
        try:
            if not document.read_text(encoding='utf-8').strip():
                invalid.append('docs/metodologia.md: empty document')
        except (OSError, UnicodeError) as error:
            invalid.append(f'docs/metodologia.md: {error}')
    metrics = root / 'reports/metrics.json'
    if not metrics.is_file():
        missing.append('reports/metrics.json')
    else:
        try:
            value = json.loads(metrics.read_text(encoding='utf-8'))
            if not isinstance(value, dict) or not value:
                invalid.append('reports/metrics.json: expected a nonempty metrics object')
        except (OSError, ValueError) as error:
            invalid.append(f'reports/metrics.json: {error}')
    figure = root / 'reports/harmonizado_anual.png'
    if not figure.is_file():
        missing.append('reports/harmonizado_anual.png')
    else:
        try:
            from PIL import Image
            with Image.open(figure) as image:
                if image.format != 'PNG':
                    raise ValueError('Expected a PNG image.')
                image.verify()
        except (OSError, ValueError) as error:
            invalid.append(f'reports/harmonizado_anual.png: {error}')
    ready = not missing and not invalid
    return {
        'status': 'ready_for_review' if ready else 'waiting_for_scientific_artifacts',
        'dataset': summary,
        'missing': missing,
        'invalid': invalid,
        'manual_checks': [
            'Person A confirms calibration and out-of-sample acceptance criteria.',
            'Review temporal coverage, regional query performance and 2012 continuity.',
            'Verify Leaflet drawing, PNG export and narrow-screen layout in a browser.',
            'Confirm final credits and public hosting with the group.',
        ],
        'publication': ('Not published; scientific and browser review is still required.'
                        if summary is not None else 'Waiting for real data, as requested by the team.'),
        'note': 'This report does not certify scientific validity and never substitutes mock data.',
    }


def main() -> int:
    report = inspect_release(ROOT)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report['status'] == 'ready_for_review' else 2


if __name__ == '__main__':
    raise SystemExit(main())
