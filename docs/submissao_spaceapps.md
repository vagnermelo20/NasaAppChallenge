# Space Apps 2026 — project submission (MODIS and VIIRS Hot Spots Harmonization)

Field by field, in the order of the project form. Copy each block into the Project page.
Fill the remaining `TODO` item (demo link) before clicking **Submit for Judging** (deadline: Sunday 15 Nov 2026, 11:59 p.m. local time).

---

## Project Name
SHFD — The Single Harmonized Flame Detector

## High-Level Project Summary
SHFD joins 25 years of NASA satellite fire detections into one consistent record. The older MODIS satellites (since 2001) and the newer VIIRS (since 2012) see the same fires differently: VIIRS has much smaller pixels and counts about four times more hot spots. Put side by side, the record shows a false jump in 2012. We harmonized MODIS to the VIIRS scale, region by region and month by month, and tested the result on years that were left out of the calibration (national annual error 1.6%). On top of this single series we built a free web app for anyone, with no satellite knowledge: draw an area on the map (or type a latitude and longitude) and see its fire season, its worst months and years, whether the last month was above or below normal, and every hot spot in it. This matters because fire managers can only compare today with the past if every year is measured with the same ruler.

## Link to Project Demo
TODO — public link to the 7-slide deck or the 30-second video (English, or English subtitles).

## Link to Final Project
- Live app: https://ember-fire-calendar.streamlit.app
- Code, data pipeline and validation: https://github.com/vagnermelo20/NasaAppChallenge

## Detailed Project Description

### What exactly does it do?
SHFD is a web app with two tabs.

**Map.** A satellite map of NASA FIRMS hot spots, from the latest day to any period since January 2001. From far away the hot spots appear as orange/yellow glowing areas measured on the same unified scale as the rest of the app, with a fixed ruler, so September 2005 and September 2024 can be compared directly on the map; when you zoom in to a smaller area, every hot spot on screen is drawn as a dot, with no cap, loaded on demand so the map stays fast. Clicking a dot shows when it was seen (Brasília time) and how strong its heat was, as a percentile that is comparable across the whole record. The app never asks the user to think about sensors: it shows only the unified record. The user chooses an area by drawing a box or shape on the same map, or by typing a latitude, longitude and distance in km. For that area SHFD shows:
- every hot spot in it on the chosen dates, as a table and a CSV download (no row limit), with each hot spot's weight on the common scale;
- plain-language sentences: fire season, the worst month, when to get ready, the worst year, and whether the last full month was above or below normal;
- a year × month fire calendar (blue = few, red = many), optionally as % above or below a usual year;
- hot spots per day, week or month, on the same harmonized scale;
- a "usual year" chart (seasonality), hot spots per year, and the last full month compared with the same month in every other year;
- a monthly CSV.

**How it works.** The project explained in six short sections for non-specialists, with the scientific limits one click away.

### How does it work?
1. **Data.** NASA FIRMS archives for Brazil: MODIS Collection 6.1 (Terra since 2001, Aqua since July 2002, ~1 km pixels) and VIIRS S-NPP 375 m (since 2012), plus 2026 from the FIRMS API. 22.5 million hot spots in total.
2. **Cleaning.** MODIS confidence ≥ 30; VIIRS nominal/high confidence; a single static-source mask (0.02° cells flagged as volcano, other static land source or offshore in at least two years) removes gas flares and industry for every year and sensor.
3. **Grid.** Hot spots are counted on a 0.25° grid (~28 km) per month and per satellite.
4. **Harmonization (not machine learning).** In the 2012–2021 overlap, we compute the ratio VIIRS ÷ MODIS separately for Terra and Aqua, per 5° block and calendar month, refined in 2° regions with Bayesian shrinkage towards the block. Terra and Aqua are combined by inverse variance. MODIS 2001–2011 is converted to the VIIRS scale; real VIIRS is used from 2012 on. Each individual MODIS hot spot carries its harmonized weight, so any area and any period add up to the same numbers.
5. **Validation, done honestly.** Each year 2012–2021 was predicted without being used for calibration:
   - Brazil: monthly correlation 0.998, mean annual error 1.6%;
   - 2° regions: 92% of years and 66% of months within ±20% of real VIIRS (median monthly difference 13.5%); for reference, two identical VIIRS satellites (S-NPP and NOAA-20) agree 85% of months;
   - pre-2012 values come with a calibrated 90% uncertainty band (empirical coverage 89.9%);
   - what did not work is reported too: the peak month in single 0.25° cells is right 73.7% of the time (90.4% within ±1 month), so the app says the peak month is most reliable for areas of about 2° or more. There is also a natural limit: two identical VIIRS satellites flying together agree within ±20% in only 85% of months (different pass times, clouds, short fires), so no conversion can reach 100% month by month. We also tested and rejected day/night factors, neighbourhood smoothing, power-law and quantile-mapping conversions.
6. **Daily series.** The same harmonized scale is extended to days and weeks; days with no satellite data are left empty instead of being counted as "no fire".
7. **App.** Python + DuckDB query the Parquet files directly, so an area over 25 years answers in about a second.

### What benefits does it have?
- **One ruler for 25 years.** Fire managers, firefighters, researchers and land managers can compare today with any year since 2001 without the artificial 2012 jump.
- **For everyone.** Plain English, simple charts and a map anyone can use; the specialist numbers are one click away.
- **Any place.** No predefined regions: the user draws or types their own area.
- **Open and transparent.** Every number has its validation and limits; the whole pipeline (notebooks, processed data, tests) is public.
- **Ready for the MODIS retirement.** The method continues the record with VIIRS, and we detected that S-NPP has sent no data since 2 November 2026, so the series can continue with NOAA-20/21.

### What do you hope to achieve?
A free, trustworthy tool that helps people in Brazil see when and where fire season is coming, so prevention and response can be planned earlier. Next steps: extend the harmonization to other countries and the whole world, continue the record with NOAA-20/21, and add burned-area context.

### What tools, coding languages, hardware, or software did you use?
- **Language:** Python.
- **Data and analysis:** pandas, NumPy, DuckDB, Apache Parquet, Shapely, Matplotlib, Jupyter notebooks.
- **Web app:** Streamlit, Plotly, Folium/Leaflet (with Leaflet.draw and Leaflet.heat), Esri World Imagery and reference labels as the background map; hosted on Streamlit Community Cloud; a GitHub Actions workflow keeps it online.
- **Workflow:** Git and GitHub, spec-driven development (spec, plan, tasks), automated tests.
- **Hardware:** personal laptops only.

## Use of Super Intelligence (SI)
Yes. The idea and the scientific method (harmonizing MODIS to the VIIRS scale with region × month factors from the 2012–2021 overlap, and leave-one-year-out validation) were defined by the team. We used AI coding assistants (Anthropic Claude and OpenAI Codex) to speed up writing and reviewing Python code for the notebooks and the web app, to run and summarize experiments the team designed, to draft English text that the team reviewed, and as an independent reviewer of the method and of the app. All results were checked against the data and by automated tests. No images, video or audio in the project were generated by AI.

## NASA Data
- **FIRMS — Fire Information for Resource Management System** (NASA LANCE / EOSDIS), https://firms.modaps.eosdis.nasa.gov/
  - MODIS Collection 6.1 active fire product (MCD14ML), Terra and Aqua, 2001–2026, Brazil country archives.
  - VIIRS S-NPP 375 m active fire product (VNP14IMG), 2012–2026, Brazil country archives.
  - FIRMS API (standard and near-real-time) for 2026.
  - VIIRS NOAA-20 375 m, 2018–2021, used only as an independent reference (how much two VIIRS satellites agree).
- FIRMS data-availability information, used to flag days and months without satellite data.

## Space Agency Partner Data and Other References
- No Space Agency Partner data were used directly. Our target users include Brazilian fire-management agencies; the Brazilian Space Agency is a 2026 partner.
- Background map: Esri World Imagery and Esri World Boundaries and Places (map tiles, with attribution shown on the map).
- Open-source software: Python, pandas, NumPy, DuckDB, Apache Arrow/Parquet, Shapely, Matplotlib, Jupyter, Streamlit, Plotly, Folium, Leaflet, Leaflet.draw, Leaflet.heat, streamlit-folium.
- Method references: NASA FIRMS documentation for MODIS C6.1 and VIIRS 375 m (fields, confidence classes, static-source `type`).
- All code and text are our own work, with the AI assistance described above.

## Team
**Team Melo**
- Vagner Melo — data and science (harmonization, validation)
- Nathália Mello — web app (queries, visualization, exports)
