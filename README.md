# Harmonized Burning Activity Calendar — MODIS × VIIRS

NASA Space Apps Challenge 2026 · Brazil pilot

**Live app:** https://ember-fire-calendar.streamlit.app

An interactive web application for exploring when burning activity occurs in a
selected region. It combines a monthly calendar, historical comparisons,
seasonality charts and downloadable data, with the goal of comparing satellite
records on a consistent VIIRS-equivalent scale.

**Status:** the application now uses the delivered real harmonized dataset:
1,252,185 cell-month records for 2001–2026 (2026 provisional; months with missing observation days flagged).
The map, calendar, trends and CSV exports are connected to this delivery.
Final-method validation is complete: the 0.25° cell peak-month criterion (80%) was not met
(73.7%; 90.4% within ±1 month); see the methodology for all scales.
The delivered archive ends in November 2026 (incomplete). October 2026 is the
latest complete month. Dates described as "latest" refer to the archive, not a
live fire-monitoring feed.

## Why harmonization matters

MODIS and VIIRS detect active fire hotspots differently. A direct switch between
their raw counts can introduce a sensor-related discontinuity. The project aims
to preserve the historical MODIS record while providing continuity with VIIRS.

Hotspots are satellite detections, not unique fires or burned area. The app does
not forecast ignition or provide operational emergency alerts.

## Features

**EMBER** is built so that anyone can use it, with no satellite knowledge. It has two tabs:

- **Map** — NASA FIRMS detections over satellite imagery with place names.
  The initial period is the latest seven days available in the archive. Select
  one day, seven days, thirty days, twelve months or custom dates since 2001.
  At national scale, orange/yellow areas aggregate harmonized activity; zoom in
  to see individual red dots. Up to 50,000 dots are loaded for the visible map
  extent; denser views keep the aggregate layer and ask you to zoom in.
  Click a dot for its time in Brasília and relative heat-strength percentile.
  Draw an area on the same map and press **Show fire history for this area**, or
  enter latitude, longitude and radius. Full-selection totals accompany a table
  of up to 5,000 detections per page. **Download this page (CSV)** exports that
  page only; select other pages or narrow the dates/area for further records.
  The page below explains seasonality, peak months, preparation timing and the
  latest complete month versus history, with calendars, charts and monthly CSV.
- **How it works** — a plain-language explanation of the method, its uses and
  limitations, with scientific context for the reported validation results.

The dates remain unrestricted within the archive; detailed observations are
paginated to bound the amount loaded into Python. Polygon filtering happens
inside the query before pagination. Full-selection totals are computed by SQL
aggregation rather than by loading all matching detections into a dataframe.
This improves memory behavior but is not a guarantee of response time for
every area, long interval or concurrent workload.

The calibration is monthly. Pre-2012 daily weights and short-interval totals
are approximations; a shared display scale does not establish exact daily
comparability or equal physical fire severity. Monthly and annual regional
comparisons have stronger validation evidence. Heat-strength percentiles are
relative ranks within each instrument's record, not harmonized FRP measurements.

Hot spots are satellite detections, not unique fires or burned area.

## Run locally

Run all commands from the repository root. Development was tested with Python 3.13.

### Windows (PowerShell)

```powershell
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m streamlit run app/app.py
```

### Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app/app.py
```

Open `http://localhost:8501`. The real scientific files are tracked in the
repository, so no mock generation or raw-archive download is needed to run the app.
The optional `app/make_mock.py` remains available for development without the
real file; its output is ignored whenever the real harmonized file exists.

The mock generator uses MODIS × 3.8 before 2012 and VIIRS counts thereafter.
This provisional factor is **not validated harmonization**. The mock is local,
ignored by Git, and identified in the interface, chart titles and CSV exports.

When `data/processed/harmonized.parquet` exists, the app prioritizes it over the
mock and checks its basic contract. An invalid real file is reported rather
than silently replaced by mock data. A valid file alone does not establish
scientific acceptance; the science team must confirm its calibration and validation.

## Data and delivered scientific method

Source: [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/), including the
[historical archive](https://firms.modaps.eosdis.nasa.gov/download/).
The existing exploratory pipeline uses MODIS Collection 6.1 and VIIRS S-NPP
375 m country files for Brazil, 2001–2025, plus 2026 from the FIRMS API (standard data to 31 July,
near-real-time after; no S-NPP data since 2 November 2026).

The delivered method in [docs/metodologia.md](docs/metodologia.md) calibrates Terra and Aqua
separately against S-NPP during 2012–2021, by 5° block and calendar month,
with a national fallback and a 2° local refinement shrunk toward the block value.
It combines Terra and Aqua by inverse-variance weighting, accounting for the
Terra-only period, and uses processed S-NPP observations from 2012 onward.
The static-source mask and incomplete-month flags are included in the delivery.
The delivered methodology and `reports/metrics.json` record final-method
validation. National monthly correlation is 0.998. At the 2° regional scale,
66% of monthly comparisons (at least 100 observed VIIRS hotspots) and 92% of
annual comparisons (at least 300) fall within ±20%. These figures describe
different scales and evaluation subsets, not general application accuracy.
The official 0.25° cell peak-month target was not met: 73.7% exact-month
agreement against the 80% target; 90.4% fall within ±1 month. For small areas,
interpret peak timing within about one month rather than as an exact date.

### Input contract

One row per 0.25° cell and UTC month:

| Field | Meaning |
|---|---|
| `lat`, `lon` | Southwest corner of the cell; its center is +0.125° in each axis |
| `ano`, `mes` | Year and month |
| `focos_harmonizados` | Nonnegative activity in VIIRS-equivalent hotspot units |
| `fonte` | `modis_convertido` or `viirs` |
| `dado_incompleto` | Incomplete observation period |

The app selects cells by their centers. Under the agreed sparse-data contract,
missing cell-month rows within dataset coverage are treated as zero. Entire
missing observation months need additional coverage metadata. A selection with
no dataset cell centers is identified explicitly and should be enlarged.

### Historical comparisons

Each complete target month is compared with the same month in earlier complete
years within the selected range. The target does not contribute to its own
baseline. Zero medians, missing history and incomplete target months produce no
percentage anomaly. Descriptive activity categories use historical percentiles
and require at least three reference years. They are not predictions.

The monthly CSV contains `year`, `month`, `hotspots`, `anomaly_pct`, `incomplete`,
`source`, `dataset` and `region_wkt`. The calendar and CSV use the same anomaly
calculation. Calendar selection uses cell centers; the detailed observation
table uses detection coordinates, so boundary totals can differ.

The detailed observation CSV exports the **current page only**, with a
`page-N` suffix in its filename. Columns are `date_utc`, `time_utc` (HH:MM),
`latitude`, `longitude`, `hotspots_common_scale` (harmonized weight), `satellite`,
`frp_mw` (raw fire radiative power in MW), `daynight`, and the optional
`heat_strength_percentile`. The percentile is a relative rank and does not
replace raw FRP. Full-selection totals above the table cover all matching
records, independently of the page currently displayed.

## Verification and handoff

```powershell
.venv/Scripts/python.exe -m unittest app.test_delivery -v
.venv/Scripts/python.exe -m app.check_release
```

The release check is read-only and exits with status 2 while required scientific
artifacts are missing or invalid. Passing it means artifacts are ready for review,
not that the scientific criteria or browser checks have been accepted.

See [app/VERIFY.md](app/VERIFY.md) for real-browser/mobile checks, integration with
Person A and the current review handoff. The app is published at the link above.
The latest pagination, CSV and scientific-copy changes passed 26 automated
tests and were exercised through the running app's local agent API. In a
500 km area around (-10, -50), September 2024 returned 186,089 detections on
38 pages: downloaded pages 1 and 2 contained 5,000 rows each, and page 38
contained 1,089. The CSV retained FRP, satellite and day/night fields; changing
dates reset the page to 1. Scientific-copy checks also passed. These checks do
not validate Chrome rendering, mobile appearance or concurrent-user performance;
the browser and scientific review handoff remains in VERIFY.md.

## Repository layout

| Path | Purpose |
|---|---|
| `app/app.py` | Streamlit application |
| `app/make_mock.py` | Local development dataset generator |
| `app/test_delivery.py` | Data and UI regression tests |
| `app/check_release.py` | Read-only scientific-artifact readiness report |
| `notebooks/` | Data ingestion and exploratory scientific analysis |
| `data/processed/` | Monthly grid and delivered harmonized data |
| `reports/` | Exploratory figures and delivered validation metrics |
| `specs/` | Requirements, implementation plan and task tracking |

Raw data, the mock, virtual environments and credentials must remain untracked.
The original notebooks and figures are preserved for the scientific work and presentation.

## Team responsibilities

- **Person A — Data/science:** calibration, coverage, validation and final scientific artifacts.
- **Person B — Application:** regional queries, visualization, accessibility and exports.
- **Joint delivery:** deployment, final credits, presentation, video and Space Apps submission.

Public app: https://ember-fire-calendar.streamlit.app · Participant names will be finalized by the group before submission.
