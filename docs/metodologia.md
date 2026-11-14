# Methodology

> **A hotspot is not a fire, and a fire is not burned area.** Each record is one satellite pixel that was hotter than its surroundings during one overpass. Counts are an index of fire activity, not a count of fires or hectares burned.

## Data

All data come from **NASA FIRMS** (Fire Information for Resource Management System), yearly country archives for **Brazil**:

| | MODIS | VIIRS |
|---|---|---|
| Satellites | Terra (from Nov 2000) and Aqua (from Jul 2002) | Suomi NPP only (from Jan 2012) |
| Product | MCD14ML, Collection 6.1 | VNP14IMG, 375 m |
| Pixel at nadir | 1 km | 375 m |
| Years used | 2001–2025 | 2012–2025 (2026 from the FIRMS API, provisional) |

We use only S-NPP for VIIRS, so the same fire is not counted twice by NOAA-20/21.

## Why the two sensors disagree

Over the same fires, VIIRS reports about **3.6–4.0 times more hotspots per year** than MODIS (Terra + Aqua, 2012–2022). The main reasons, all checked in the data:

- **Pixel size.** The MODIS pixel grows from 1.0 km² at nadir to about 9.6 km² at the swath edge (median **1.43 km²**). The VIIRS pixel stays between 0.14 and 0.62 km² (median **0.20 km²**). One typical MODIS pixel covers about **7 VIIRS pixels**.
- **Weak fires.** A small fire heats a small pixel much more than a large one. Of VIIRS detections with fire radiative power of 2–5 MW, only **23%** fall inside a MODIS pixel that also detected fire; above 100 MW, **65%** do. MODIS misses many small agricultural and pasture fires.
- **Overpass time.** Fires follow a daily cycle. Terra passes at about 10:30 and 22:30 local time; Aqua and S-NPP at about 13:30 and 01:30. Aqua and S-NPP observe at nearly the same time, which shows the gap comes from the sensor, not the clock.
- **Terra ≠ Aqua.** Because of the different times, each MODIS satellite needs its own conversion: over 2012–2021, VIIRS ≈ 6.1 × Aqua and ≈ 9.8 × Terra.

Without harmonization, any long series shows a false jump in 2012, when VIIRS starts.

## Harmonization method

1. **Confidence filters.** MODIS: confidence ≥ 30. VIIRS: confidence "nominal" or "high".
2. **Static-source mask.** Gas flares, industry, volcanoes and offshore platforms are not vegetation fires. Instead of filtering by the `type` field row by row (its rule changed in 2018, see Limitations), we build one mask: a 0.02° cell (~2 km) is masked if it had a non-vegetation `type` (1, 2 or 3) in **at least two different years**, in either sensor. This gives **6,403 cells (~31,000 km²)**. All hotspots inside them are removed, for every year and both sensors (about 1–3% of hotspots per year).
3. **Grid.** Hotspots are counted per **0.25° cell (~28 km) × month**, separately for Terra, Aqua and S-NPP.
4. **Conversion factor k.** For each MODIS satellite, `k = sum(VIIRS) / sum(MODIS)` per **5° × 5° block × calendar month**, calibrated on **2012–2021**. If a block-month has fewer than 30 MODIS hotspots, it uses the national k for that satellite and month (fallback in 17% of Aqua and 26% of Terra block-months). k varies a lot by region: the median is 6.1 for Aqua and 9.2 for Terra.
   **Local refinement:** each cell then uses the k of its **2° × 2° region × month**, pulled toward the 5° block value when the region has few hotspots: `k_local = (ΣVIIRS₂° + 100·k₅°) / (ΣMODIS₂° + 100)` (Bayesian shrinkage).
5. **Harmonized series.**
   - **2001–2011:** Terra and Aqua counts are combined weighted by the information each carries (inverse-variance): `estimate = (n_Terra + n_Aqua) / (1/k_Terra + 1/k_Aqua)`. Aqua, which sees more fires, weighs more than the noisier Terra. From January 2001 to June 2002 only Terra exists, so `n_Terra × k_Terra` is used.
   - **2012 onwards:** the real VIIRS S-NPP counts are used, unchanged.

The result is a single monthly series on the VIIRS scale, from 2001 to today, for every 0.25° cell in Brazil.

## Validation — does MODIS now say the same as VIIRS?

The test that matters: **same region, same month — after conversion, does MODIS give the same number as VIIRS?** For each year 2012–2021 the conversion factors are recomputed **without that year** (leave-one-year-out), so the model never sees the VIIRS value it is trying to match.

**Examples (peak month of 2020):**

| Region | MODIS raw | MODIS converted | VIIRS | Difference |
|---|---|---|---|---|
| Brazil | 130,156 | 498,824 | 516,659 | −3% |
| Pantanal | 16,580 | 61,133 | 62,591 | −2% |
| Matopiba | 12,584 | 50,013 | 53,797 | −7% |

Over the whole decade the regional bias is about 0% (Pantanal, Matopiba, Acre and the Amazon deforestation arc are all within ±2%); individual years can deviate more (e.g. Acre, August 2020: −48%).

**All of Brazil, every month 2012–2021** (region-months with ≥ 100 VIIRS hotspots):

| Region size | Raw MODIS: median difference | Converted: median difference | Converted within ±20% | Correlation |
|---|---|---|---|---|
| 1° (~110 km) | 74% | 16% | 60% | 0.984 |
| 2° (~220 km) | 74% | **14%** | **66%** | **0.992** |
| 5° (~550 km) | 74% | 11% | 72% | 0.996 |

National monthly correlation is 0.998 and the national mean annual error 1.6% (leave-one-year-out, final method). Outside the calibration period (2022–2025) the national annual error is about 6%, with converted MODIS above VIIRS in 2023–2025 because of the MODIS orbital drift.

**Natural reference.** Two identical VIIRS instruments (S-NPP and NOAA-20, ~50 min apart) also disagree: on the same 2° regions (2018–2021) their median monthly difference is 8% and 85% of region-months fall within ±20%. Converted MODIS reaches a median difference of 13% and 66% within ±20% over the same period — close to the level at which even two identical sensors differ.

**Agreement by time scale** (2° regions, final method, leave-one-year-out 2012–2021):

| Scale | Within ±10% | Within ±20% | Median difference |
|---|---|---|---|
| Month (≥ 100 VIIRS hotspots) | 39% | 66% | 13.5% |
| Month with heavy fire (≥ 1,000) | 57% | 85% | 8.5% |
| Quarter (≥ 300) | 54% | 82% | 9.1% |
| **Year** (≥ 300) | 68% | **92%** | 6.3% |

In months with heavy fire, converted MODIS agrees with VIIRS as well as the two identical VIIRS instruments agree with each other.

**Calibrated uncertainty band.** Each converted value before 2012 comes with a 90% band built from the errors of the other years. The band's real coverage is **89.9%** (80% band: 79.7%). It is wide when MODIS saw little fire (≤ 20 hotspots in the month: −6% to +229%) and narrow when it saw a lot (> 500: −19% to +21%).

**What we tried and rejected.** Correcting each month's factor with MODIS-only covariates (FRP tail, clustering, Terra/Aqua anomaly, night fraction) did not help (66% → 65%, no better than shuffled covariates). A simulation shows that pure counting noise would allow ~94% within ±20%, so the remaining error comes from real year-to-year changes in how fires look to each sensor, which MODIS alone cannot predict. **Point-by-point agreement of 90–100% per region and month is not physically achievable**; even two identical VIIRS instruments reach 85%.

**Final test 2022–2025** (outside calibration): 53% of region-months within ±20% (median difference 18%), degraded by MODIS orbital drift. The app uses real VIIRS for these years.

## Limitations

- **Hotspots ≠ fires ≠ burned area.** One large fire can produce many hotspots; a fire under clouds or between overpasses produces none.
- **MODIS orbital drift.** Terra and Aqua are drifting at the end of their missions. Mean local overpass time was stable until 2021 (Aqua 13.65 h, Terra about 10.45 h) and in 2025 reached **14.90 h for Aqua and 9.26 h for Terra**. This is why k is calibrated only on 2012–2021; MODIS-converted values after 2021 are less reliable (but the app uses real VIIRS for those years).
- **MODIS `type` rule changed in 2018.** MCD14ML version 3 "significantly improved typing" of hotspots: the share of `type = 2` (static source) went from 0.56% in 2017 to 2.70% in 2018. Filtering by `type` would create an artificial step, so we use the single static-source mask.
- **Incomplete months are flagged.** A month is marked incomplete when the source used for it has at least one day with no record anywhere in Brazil (for example January 2012, when VIIRS data start on the 20th). A missing day means missing observation, not zero fire.
- **The current month is provisional.** 2026 data come from the FIRMS API; the most recent weeks are near-real-time (NRT) data and are always flagged as incomplete.
- **Regional factors.** k is calibrated per 2° region and month over ten years; in a single cell or a single year (fire type changes from year to year) the error can be larger than in regional or national totals. Use regions of ~1° or larger for comparisons before 2012.
- **Brazil only.** The factors were calibrated for Brazilian fire regimes and should not be applied elsewhere without recalibration.

## Data sources and credits

- NASA FIRMS — Fire Information for Resource Management System: https://firms.modaps.eosdis.nasa.gov/
- We acknowledge the use of data and imagery from **LANCE FIRMS**, operated by NASA's Earth Science Data and Information System (ESDIS), with funding provided by NASA Headquarters.
- MODIS Collection 6.1 active fire product (MCD14ML) and VIIRS S-NPP 375 m active fire product (VNP14IMG).
- Giglio, L., Schroeder, W., Hall, J. V., Justice, C. O. (2021). *MODIS Collection 6 and Collection 6.1 Active Fire Product User's Guide*, version 1.0.
