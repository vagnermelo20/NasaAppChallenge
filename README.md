# SHFD — The Single Harmonized Flame Detector

Where and when does Brazil burn?

NASA Space Apps Challenge 2026 · Challenge: **Harmonization of MODIS and VIIRS Hot Spots** · Team Melo

**Live app:** https://ember-fire-calendar.streamlit.app

SHFD joins 25 years of NASA satellite fire detections over Brazil (2001–2026) into **one single,
consistent record**, and puts it in a free web app that anyone can use without knowing anything
about satellites.

## The problem

The older MODIS satellites (since 2001, ~1 km pixels) and the newer VIIRS (since 2012, 375 m pixels)
see the same fires differently: VIIRS counts about 4× more hot spots because it also sees small fires.
Put side by side, the record shows a false jump in 2012. Without harmonization, Brazil's fires seem
to rise after 2012; with it, the 2000s actually burned more (1.73 million hot spots per year in
2001–2011 vs 1.22 million in 2012–2025).

## The method (not machine learning)

1. **Clean:** MODIS confidence ≥ 30, VIIRS nominal/high; one static-source mask (gas flares,
   industry, volcanoes) applied to every year.
2. **Learn:** in 2012–2021 both satellites flew together. For Terra and Aqua separately, we compute
   the ratio VIIRS ÷ MODIS per 5° block and calendar month, refined in 2° regions with Bayesian
   shrinkage toward the block, and combine Terra and Aqua by inverse variance.
3. **Convert:** MODIS 2001–2011 is converted to the VIIRS scale; real VIIRS is used from 2012 on.
   Each MODIS hot spot carries its own harmonized weight, so any area and period adds up consistently.

Full details: [docs/metodologia.md](docs/metodologia.md) · metrics: [reports/metrics.json](reports/metrics.json).

## Validation (each year 2012–2021 hidden from calibration, then predicted)

| Test | Result |
|---|---|
| Brazil, each year | mean error **1.6%** (all years within ±20%) |
| Brazil, month by month | correlation **0.998** |
| ~200 km (2°) regions, each year | **92%** within ±20% |
| ~200 km (2°) regions, each month | **66%** within ±20% (median difference 13.5%) |
| Natural limit: two identical VIIRS satellites, each month | **85%** within ±20% |
| Peak month in single 0.25° cells | 73.7% exact, 90.4% within ±1 month |

Bigger areas and longer periods are more reliable. Even two identical satellites agree in only 85% of
months (different pass times, clouds, short fires), so no conversion can reach 100% month by month.
We also tested and rejected day/night factors, neighbourhood smoothing, power-law and quantile-mapping
conversions.

## The app

Two tabs: **Map** and **How it works**.

- **Map:** any day or period since January 2001. From far away, hot spots glow on the single common
  scale with a fixed ruler, so the same month in 2005 and 2024 can be compared directly. Zoom in and
  every hot spot on screen becomes a red dot (raw detections, loaded on demand); click one to see when
  it was seen (Brasília time) and its heat strength as a percentile.
- **Your area:** draw an area or type a latitude, longitude and distance. SHFD lists every hot spot
  in it (table + CSV, no row limit) and shows plain sentences (fire season, best time to get ready,
  worst year, last month vs usual), a year × month fire calendar, hot spots per day/week/month,
  a usual year, hot spots per year and a monthly CSV. Everything except the red dots uses the unified record.
- **How it works:** the method in plain words, with the scientific limits one click away.

Hot spots are satellite detections, not separate fires or burned area. The archive ends on
2 November 2026 (no VIIRS S-NPP data after that date); it is not a live emergency feed.

### CSV exports

- **Hot spots in your area:** `date_utc`, `time_utc`, `latitude`, `longitude`,
  `heat_strength_percentile`, `hotspots_common_scale`.
- **Monthly:** `year`, `month`, `hotspots`, `anomaly_pct`, `incomplete`, `dataset`, `region_wkt`.

## Data

All from [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/), Brazil:

- MODIS Collection 6.1 (MCD14ML), Terra and Aqua, 2001–2026;
- VIIRS S-NPP 375 m (VNP14IMG), 2012–2026;
- FIRMS API for 2026;
- VIIRS NOAA-20 375 m, 2018–2021, only as a reference (how much two identical satellites agree).

22.5 million hot spots in total. Processed files are in `data/processed/` (raw archives are not versioned).

## Run locally

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt      # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m streamlit run app/app.py
```

Tests: `.venv/Scripts/python -m unittest app.test_delivery` (26 tests) and
`.venv/Scripts/python -m app.check_release`.

## Repository layout

| Path | Purpose |
|---|---|
| `app/app.py` | Streamlit application |
| `app/test_delivery.py` | Data and interface tests |
| `notebooks/` | Download, harmonization (04), validation (05), proof (07), hot spot base (08), daily series (09) |
| `data/processed/` | Harmonized grid, hot spots by year with their weights, daily/weekly series |
| `reports/` | Figures and validation metrics; `reports/slides/` has the presentation charts |
| `docs/` | Methodology and submission text |
| `specs/` | Spec, plan and tasks |

## Team Melo

- **Vagner Melo** — data and science: harmonization, validation and scientific artifacts.
- **Nathália Mello** — web application: queries, visualization, accessibility and exports.

AI coding assistants were used to speed up code, text and review; the idea, method and results were
defined and checked by the team (see `docs/submissao_spaceapps.md`).
