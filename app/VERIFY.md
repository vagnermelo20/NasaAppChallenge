# Front-end verification and science handoff

## Current delivery — review assigned to Person A

The app is published at https://ember-fire-calendar.streamlit.app. Its current
interface has **Map** and **How it works** tabs, with area selection, observation
tables and fire history together under Map. The archive ends in November 2026
(incomplete); October 2026 is the latest complete month. "Latest" means the
latest archive records, not live emergency information.

The user subsequently authorized testing of the latest memory, CSV and
scientific-copy corrections. The 26 automated tests passed. The running app's
local agent API also checked a 500 km area around (-10, -50) for September 2024:
186,089 detections on 38 pages; downloaded pages 1 and 2 had 5,000 rows each,
and page 38 had 1,089. CSV FRP, satellite and day/night fields were present,
changing the date range reset the page to 1, and the monthly-calibration,
approximate-daily and final-A2 wording checks passed.

These are Python/HTTP checks, not Chrome or mobile visual QA. The remaining
checklist is a handoff for Person A; items below are not claimed to have passed
unless recorded above. Concurrent-user performance is also not established.

## Start locally

Run from the repository root:

```powershell
.venv/Scripts/python.exe -m streamlit run app/app.py
```

Real scientific data are included in the repository. A development mock is
optional, must remain untracked and is superseded by the real file. Local
Python 3.13 instructions are in README; production uses app/requirements.txt.

## Pagination and memory behavior

- Draw a polygon or enter coordinates/radius and select a multi-year interval.
  Confirm that the totals cover all exact matches but the observation table
  loads at most 5,000 detections per page.
- Select the first, middle and last result pages. Confirm no missing or repeated
  rows across page boundaries, using fields beyond date/time where detections
  share a timestamp. Confirm a changed area/date interval resets the page.
- Check a non-rectangular polygon: bounding-box matches outside the polygon
  must be excluded before pagination and from full-selection totals.
- Confirm an empty area produces an explicit empty-result message without a
  download that appears to contain observations.
- Compare full-selection totals with an independent aggregate query. Table-page
  sums must not be presented as the full-selection total.
- Review memory and response time on the hosted app for a large area and long
  interval, including concurrent sessions. SQL pagination bounds dataframe rows
  but does not establish a universal latency or server-memory guarantee.
- At national map scale expect aggregate activity. When zooming in, no more
  than 50,000 point locations should be loaded for the visible extent. Above
  that threshold, confirm the zoom-in guidance instead of partial unlabeled dots.

## Detailed CSV and display

- Confirm **Download this page (CSV)** exports only the current result page,
  names the file with page-N and retains the exact UTC dates/time (HH:MM).
- Check columns: date_utc, time_utc, latitude, longitude, hotspots_common_scale,
  satellite, frp_mw, daynight and optional heat_strength_percentile.
- Compare raw FRP in MW and harmonized weights with the scientific point file.
  A percentile is an instrument-relative rank, not harmonized FRP or severity.
- Confirm the monthly CSV still matches the calendar and retains its separate
  monthly schema and coverage flags. Detection-coordinate filtering and
  cell-center calendar filtering can legitimately differ at region boundaries.
- Check that changing the table page never changes full-selection totals.

## Scientific wording and coverage

- How it works must explain that calibration is monthly. Pre-2012 daily and
  short-interval weights are approximate; a shared scale is not proof of exact
  daily comparability, equal FRP or equal fire severity.
- Check 66% monthly agreement (at least 100 VIIRS hotspots) and 92% annual
  agreement (at least 300), both evaluated at the 2 degree regional scale.
  These must not be described as general application accuracy.
- Retain the final A2 result: 73.7% exact cell-scale peak month against an 80%
  target (not met); 90.4% within one month. Evaluation is complete, not pending.
- Confirm incomplete coverage is visible and the latest-complete-month
  comparison excludes November 2026, rather than interpreting missing days as
  no fire. No exact-day confidence interval follows from the monthly calibration.
- Confirm that hotspot detections are never described as unique fires, burned
  area, a forecast or an operational emergency alert.

## Browser and accessibility

- Check drawing, editing and deleting an area on the same map as the detections.
  Apply it with **Show fire history for this area**, and confirm history updates.
- Check map zoom, point popups, labels, table pagination and CSV on desktop and
  a narrow phone viewport. Verify keyboard access, visible focus and readable labels.
- Check plain-language summaries, seasonal charts, anomaly mode and monthly
  exports for the same area. Export a chart PNG and inspect its actual appearance.
- Try an empty region and a very small region without enough calendar cell
  centers. Confirm guidance instead of a false assertion that no fire occurred.

## Scientific contract and submission

The harmonized input contract in specs/plan.md remains unchanged: lat, lon, ano,
mes, focos_harmonizados, fonte and dado_incompleto. Do not reinterpret or rename
scientific input fields to match simplified UI labels. The scientific method
and final metrics are recorded in docs/metodologia.md and reports/metrics.json.

The published app is separate from the remaining final credits, README review,
video and portal submission. The read-only release command below checks artifact
readiness, not scientific acceptance or browser behavior. Person A can run it
and the test suite when performing the requested review:

```powershell
.venv/Scripts/python.exe -m app.check_release
.venv/Scripts/python.exe -m unittest app.test_delivery -v
```
