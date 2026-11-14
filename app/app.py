"""B0–B2: application shell, data source and filter layout.

Run from the repository root: python -m streamlit run app/app.py
"""
from pathlib import Path

import duckdb
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "data/processed/harmonized.parquet"
MOCK = ROOT / "data/processed/harmonized_mock.parquet"
DATA = REAL if REAL.exists() else MOCK

st.set_page_config(
    page_title="Harmonized Burning Activity Calendar",
    page_icon="🌍",
    layout="wide",
)


@st.cache_data
def data_years(path: str, modified_ns: int) -> tuple[int, int]:
    """Read only the year bounds; refresh when the source file changes."""
    with duckdb.connect() as connection:
        bounds = connection.execute(
            "SELECT min(ano), max(ano) FROM read_parquet(?)", [path]
        ).fetchone()
    if bounds is None or bounds[0] is None:
        raise ValueError("The data file has no observations.")
    return int(bounds[0]), int(bounds[1])


st.caption("NASA SPACE APPS CHALLENGE · BRAZIL PILOT")
st.title("Harmonized Burning Activity Calendar")
st.write(
    "Explore historical burning activity across Brazil using NASA FIRMS "
    "MODIS and VIIRS satellite detections."
)
st.caption("Select an area and a time range to explore seasonal patterns and historical activity.")

if not DATA.exists():
    st.warning("No data file found. Generate the development dataset to get started.")
    st.code(".venv/Scripts/python.exe app/make_mock.py", language="bash")
    st.stop()

try:
    first_year, last_year = data_years(str(DATA), DATA.stat().st_mtime_ns)
except (duckdb.Error, ValueError) as error:
    st.error(f"Unable to read the dataset: {error}")
    st.stop()

is_mock = DATA == MOCK
if is_mock:
    st.warning(
        "Development preview — using mock data. The provisional conversion "
        "is for interface development and is not validated harmonization."
    )

with st.sidebar:
    st.header("Explore activity")
    with st.form("filters"):
        region_mode = st.radio(
            "Region selection",
            ["Draw on map", "Lat-Lon + radius"],
            key="region_mode",
            help="Map drawing and coordinate inputs will be connected in the next delivery.",
        )
        if first_year < last_year:
            years = st.slider(
                "Year range (UTC)",
                min_value=first_year,
                max_value=last_year,
                value=(first_year, last_year),
                key="year_range",
                help="Available years are read from the selected dataset.",
            )
        else:
            years = (first_year, last_year)
            st.caption(f"Available year: {first_year}")
        submitted = st.form_submit_button("Update", width="stretch", key="update")
    st.caption("Region selection and calendar queries are coming in the next delivery.")
    st.divider()
    st.caption(f"Data coverage: {first_year}–{last_year}")
    st.caption("Grid: 0.25° · Monthly aggregation · Brazil")

if submitted or "applied_filters" not in st.session_state:
    st.session_state["applied_filters"] = {"mode": region_mode, "years": years}

applied = st.session_state["applied_filters"]
start, end = applied["years"]
st.caption(f"Selected period: {start}–{end} · Region mode: {applied['mode']}")

calendar, trends, methodology, about = st.tabs(
    ["Calendar", "Trends", "Methodology", "About"]
)
with calendar:
    st.subheader("Burning activity calendar")
    st.info("The regional calendar will appear here once map selection and monthly queries are connected.")
with trends:
    st.subheader("Historical trends")
    st.caption("Annual activity and monthly seasonality charts will be added in the next delivery.")
with methodology:
    st.subheader("Methodology")
    st.caption("Harmonization documentation and validation results will appear here when available.")
with about:
    st.subheader("About this project")
    st.write(
        "A NASA Space Apps prototype for exploring burning activity calendars "
        "from MODIS and VIIRS active fire hotspots."
    )
    st.markdown("Source: [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/)")

st.divider()
st.caption("Hotspots are satellite detections, not number of fires or burned area.")
st.caption(f"Data: {DATA.name} · {'MOCK — development only' if is_mock else 'Harmonized dataset'}")
