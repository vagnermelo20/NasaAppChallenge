# Space Apps 2026 — project submission text (MODIS and VIIRS Hot Spots Harmonization)

Live app: https://ember-fire-calendar.streamlit.app · Code: https://github.com/vagnermelo20/NasaAppChallenge

## What exactly does it do?
EMBER turns 25 years of NASA FIRMS satellite fire detections into one consistent **burning activity calendar** for Brazil (2001–2026). Users draw an area on a map (or enter latitude, longitude and radius), pick a period, and see a year × month calendar of hotspot activity with an accessible color ramp, how the latest complete month compares with the historical median (normal, above normal, critical), annual trends and seasonality. A date search lists the individual detections for any interval of up to 92 days (date, UTC time, satellite, position, fire radiative power) and compares the same dates across years. Everything can be downloaded as CSV.

## How does it work?
MODIS (Terra/Aqua, 1 km pixels, since 2000) and VIIRS (S-NPP, 375 m pixels, since 2012) see the same fires differently: a VIIRS pixel is about 7× smaller, so it detects 4–10× more hotspots and many weak fires that MODIS misses. We harmonize MODIS to the VIIRS scale:
1. Filter detections (confidence, a recurrent static-source mask for gas flares and industry) and count them on a 0.25° grid per month and satellite.
2. Learn conversion factors VIIRS ÷ MODIS for Terra and Aqua separately, per 5° block and calendar month, refined in 2° regions with Bayesian shrinkage, using the 2012–2021 overlap.
3. Convert 2001–2011 MODIS; use real VIIRS from 2012 on.
We validated honestly: each year was predicted without being used for calibration. Nationally the monthly correlation is 0.998 and the annual error 1.6%; for 2° regions, 92% of years and 66% of months fall within ±20% of real VIIRS (two identical VIIRS satellites reach 85% per month). Every pre-2012 value has a calibrated 90% uncertainty band. We also report what did not work (the 0.25° cell peak-month target was not met: 73.7%).

## What benefits does it have?
- Emergency managers can compare today's fire activity with 25 years of history on one scale, without the artificial jump that appears when the record switches from MODIS to VIIRS.
- It shows which months and years burn most in any area they draw, and whether the current month is unusual.
- Transparent science: every number has its validation, limits and uncertainty, and the full pipeline is open (notebooks, data, tests).
- The method keeps working as MODIS retires: we detected that S-NPP has delivered no data since 2 Nov 2026, and the same approach can continue with NOAA-20/21.

## What do you hope to achieve?
A free, trustworthy tool that lets fire managers, firefighters, scientists and land managers in Brazil spot critical periods earlier and plan prevention and response with a consistent long-term record. Next steps: extend to other countries, continue the record with NOAA-20/21, and add burned-area context.

## What tools, coding languages, hardware, or software did you use?
- **Data:** NASA FIRMS — MODIS Collection 6.1 (MCD14ML) and VIIRS S-NPP 375 m (VNP14IMG), yearly country archives and the FIRMS API; NOAA-20 VIIRS for validation.
- **Language:** Python 3.14.
- **Analysis:** pandas, NumPy, DuckDB, Apache Parquet, Matplotlib, Jupyter notebooks.
- **Web app:** Streamlit, Plotly, Folium/Leaflet, Shapely; hosted on Streamlit Community Cloud; GitHub Actions keeps it online.
- **Workflow:** GitHub, spec-driven development, automated tests; AI coding assistants (Claude, Codex) for analysis support and code review.
- **Hardware:** personal laptops; no special hardware.
