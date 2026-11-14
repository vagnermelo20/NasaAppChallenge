# Front-end verification and science handoff

Latest B10/B20 handoff: font size increased to 16 px, a Compact map control
added for small screens, visible keyboard focus added to the fullscreen button,
and table alternatives identified beside the map. At the user's request, this
delivery was not tested or visually checked. Person A owns the remaining review,
including Chrome, mobile, keyboard navigation, PNG export and empty selections.

B19 handoff for Person A (implemented without running checks, as requested):
open Calendar with years before 2012 and expand **Pre-2012 uncertainty · 2°
monthly regions**. Review the 2° grid alignment, filtered MODIS sum, count-bin
selection, factors from `metrics.json`, estimate × factors, completeness flags
and uncertainty CSV. The bounds apply to each whole region-month; they are not
summed across regions or months and do not supply an exact-day confidence interval.

Run from the repository root:

```powershell
.venv/Scripts/python.exe -m streamlit run app/app.py
```

The real scientific files are now delivered. Mock generation is optional and
the mock must remain untracked; the app always prioritizes the real file.

## Browser checklist

The new EMBER workspace opens on Fire map. Observation sensor, period, layer
opacity and CSV export are in the sidebar. Expand **Area & calendar filters**
to change the area, use examples, or set calendar years. The source card must
show `harmonized.parquet` for the harmonized product and `grid_sat.parquet` for
processed sensor observations. The delivered archive ends in November 2026
(incomplete); October 2026 is the latest complete month.

- Open `http://localhost:8501` and refresh after code changes.
- Under **Try an example region**, apply Pantanal, Matopiba and Acre. Each is
  an illustrative 100 km circle, not an official boundary.
- Confirm that the region label, selected cell count, calendar and downloaded
  CSV change together. CSV `dataset` must say `harmonized` for the real calendar.
- In **Draw on map**, draw/edit/delete a rectangle. Changes stay pending until
  **Apply map selection** is clicked. Confirm selection persists across tabs.
- Toggle anomalies and cell values. Months without an earlier complete-year
  baseline or with a zero median have no percentage anomaly.
- Compare the latest complete-month card with the corresponding CSV row.
  With the delivered 2026 archive, it must show October 2026 and warn that
  November is incomplete. Incomplete months remain in the calendar and CSV.
- Near the calendar, confirm the peak-month scale guidance (about 2° or larger,
  or hundreds of hotspots/year; ±1 month for small areas). Methodology and About
  must distinguish 66% monthly agreement from 92% annual agreement at 2° scale,
  and state that the 73.7% exact cell-scale peak result misses the 80% target.
  About must describe real data without a mock warning when the real file is loaded.
- Confirm annual/seasonal charts in Trends and the pending science status in
  Methodology. Inspect the PNG exported by the chart's camera button.
- Open **Fire map**. Confirm the five colored count ranges and the NASA FIRMS
  legend. Hover a cell and verify its sensor, UTC month and detection count.
  Change sensor/month and compare the displayed total with the observation CSV.
  Toggle **Limit to the applied region** and verify the spatial filter.
  Switch between Harmonized activity and Sensor observations. For VIIRS after
  2012, matching area/month totals must agree. Check converted fractional values
  before 2012 and the incomplete-data warning for September 2024.
- Check the dark catalog, compact indicators, map popup and layer controls.
  Change opacity and ensure counts do not change. On a narrow screen, confirm
  the sidebar can be collapsed and all controls remain accessible.
- Confirm **Hotspot locations** opens on satellite imagery with tiny red dots,
  without halos. Dots use the actual detection coordinates, not cell centers.
  **Analysis grid** shows the original polygons. Indicators and cell CSV must match
  in both modes. Under **Layer appearance**, switch Dark atlas / Satellite
  imagery / Street map; verify provider attribution and imagery-context notice.
  Check the compact horizontal legend, region outline, fullscreen button and
  small-screen layout in the browser. Fullscreen can depend on iframe/browser permissions.
- For an empty selection, try latitude -30, longitude -35, radius 5 km.
  Confirm a clear empty-selection message and no application error.
- Repeat at a narrow browser width or on a phone: open/close the sidebar,
  use coordinates without the map preview, read labels, switch tabs, and
  download CSV. Keep cell values off for a less crowded calendar.

Map drawing, PNG appearance and mobile layout still require a real-browser
check; Python and HTTP checks do not validate Leaflet rendering.

## Integration with Person A (B11)

Expected file: `data/processed/harmonized.parquet`, with columns `lat`, `lon`,
`ano`, `mes`, `focos_harmonizados`, `fonte`, `dado_incompleto`, according to
`specs/plan.md`. Do not rename or silently reinterpret these fields.

Once Person A confirms Checkpoint 2, the app prioritizes this file over the
mock automatically. Check the footer and CSV dataset label, repeat the three
regions, and measure cold queries against the <3 s requirement. Confirm
2012 continuity using Person A's validation evidence, not visual smoothing.
Final methodology and metrics are loaded from `docs/metodologia.md` and
`reports/metrics.json` when supplied. Do not claim their validation is complete
until the files and results have been reviewed.

## Publication readiness

### Exact-date hotspot search

- Open **Hotspot search**, leave Oct 1–7, 2026 and submit. Brazil should return
  39,965 detections; download the CSV and check dates, UTC time (HH:MM), satellite,
  coordinates, FRP and harmonized weights against the table.
- Apply an example area in Calendar, then enable **Use applied calendar area**
  and submit again. The applied-search label must identify the area.
- Query Sep 1–30, 2024 nationally: the app must request a narrower selection
  instead of displaying/downloading a partial result above 200,000 detections.
- Try more than 92 days, a one-date selection, an empty region and Nov 2026.
  Confirm clear validation/coverage messages and no crash.
- Compare dates before/after 2012: comparisons use weights and label MODIS as
  approximate. Incomplete periods have no numerical comparison. A Feb 29 query
  compared with a non-leap year is unavailable, not silently shifted.
- The monthly uncertainty calibration is not a calibrated confidence interval
  for exact-day comparisons; do not present it as one.

The repository now includes the real harmonized dataset and processed satellite
grid. A fresh deployment can use them directly without generating a mock.
The entry point is `app/app.py`; dependencies are in `requirements.txt`.
Keep credentials and `.venv` out of the repository. Public hosting,
submission, final README and video remain the joint J1–J4 tasks.

The real-data handoff has arrived; scientific acceptance, visual review and
publication are still separate steps. Run
`.venv/Scripts/python.exe -m app.check_release` to list missing or invalid
scientific artifacts without writing files. Exit status 2 means the handoff is
incomplete; status 0 means ready for review, not scientifically certified.
