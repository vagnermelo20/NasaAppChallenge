# Front-end verification and science handoff

Run from the repository root:

```powershell
.venv/Scripts/python.exe app/make_mock.py
.venv/Scripts/python.exe -m streamlit run app/app.py
```

The mock must remain untracked. It is not a validated harmonized product.

## Browser checklist

- Open `http://localhost:8501` and refresh after code changes.
- Under **Try an example region**, apply Pantanal, Matopiba and Acre. Each is
  an illustrative 100 km circle, not an official boundary.
- Confirm that the region label, selected cell count, calendar and downloaded
  CSV change together. CSV `dataset` must say `mock` while the mock is used.
- In **Draw on map**, draw/edit/delete a rectangle. Changes stay pending until
  **Apply map selection** is clicked. Confirm selection persists across tabs.
- Toggle anomalies and cell values. Months without an earlier complete-year
  baseline or with a zero median have no percentage anomaly.
- Compare the latest-month card with the corresponding CSV row.
- Confirm annual/seasonal charts in Trends and the pending science status in
  Methodology. Inspect the PNG exported by the chart's camera button.
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

The current repository does not include the local mock or the final real
dataset. A fresh deployment therefore needs the real file or a deliberately
generated, clearly labeled demo dataset before it can serve calendars.
The entry point is `app/app.py`; dependencies are in `requirements.txt`.
Keep credentials and `.venv` out of the repository. Public hosting,
submission, final README and video remain the joint J1–J4 tasks.
