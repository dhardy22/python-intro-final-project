import requests
import os
from dotenv import load_dotenv
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider
import mplcursors

load_dotenv()  # reads MY_API_KEY from a local .env file, if one exists

REST_COUNTRIES_URL = "https://api.restcountries.com/countries/v5"
WORLD_BANK_BASE_URL = "https://api.worldbank.org/v2"

INDICATOR_GDP_TOTAL = "NY.GDP.MKTP.CD"
INDICATOR_GDP_PER_CAPITA = "NY.GDP.PCAP.CD"
INDICATOR_POPULATION_GROWTH = "SP.POP.GROW"
INDICATOR_POPULATION_TOTAL = "SP.POP.TOTL"

# Documented bounds of the data the World Bank API actually serves, used to
# validate the trend chart's date range up front rather than discovering an
# empty result after the request.
WORLD_BANK_MIN_YEAR = 1960
WORLD_BANK_MAX_YEAR = 2023


# ---------------------------------------------------------------------------
# REST Countries: fetching and parsing
# ---------------------------------------------------------------------------

def fetch_countries():
    """Fetch every country from the API, paging through results.

    The API returns results in pages (25 per page by default) along with
    a "meta" block describing the total count and whether more pages
    remain. This loops through all pages, collecting every country
    object into a single list, and stops once the API reports there's
    no more data (meta["more"] is False).

    Returns:
        A dict shaped like {"data": {"objects": [...]}} containing every
        country object combined across all pages, or None if the request
        failed (network error or non-200 status code).
    """
    all_objects = []
    offset = 0

    while True:
        try:
            r = requests.get(
                REST_COUNTRIES_URL,
                headers={"Authorization": f'Bearer {os.getenv("MY_API_KEY")}'},
                params={"offset": offset}
            )
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return None

        if r.status_code != 200:
            print(f"REST Countries API returned status {r.status_code}")
            return None

        payload = r.json()["data"]
        all_objects.extend(payload["objects"])

        # Stop paging once the API says there's nothing left to fetch
        if not payload["meta"].get("more", False):
            break

        offset += payload["meta"]["limit"]  # advance by whatever page size the API actually used

    # Note: only "objects" is carried forward here — "meta" applied to a
    # single page and doesn't represent the combined result, so it's
    # intentionally dropped rather than merged from the last page.
    return {"data": {"objects": all_objects}}


def parse_countries(raw_data):
    """Reshape the raw API response into a simple, flat list of dicts.

    The raw API response nests everything under {"data": {"objects": [...]}}
    and uses field names (names.common, capitals[0].name, codes.alpha_3)
    that don't match the structure the rest of the program works with.
    This function pulls just the fields we need into a flat, predictable
    shape.

    The ISO codes (alpha_2, alpha_3, ccn3) are carried through even though
    nothing displays them directly — they're the join key into the World
    Bank API, which is keyed by country code rather than country name.

    Args:
        raw_data: the dict returned by fetch_countries().

    Returns:
        A list of dicts, each shaped like:
        {"name": ..., "capital": ..., "region": ..., "population": ...,
         "alpha_2": ..., "alpha_3": ..., "ccn3": ...}
    """
    countries = []
    for c in raw_data["data"]["objects"]:
        # Some countries have no capital listed at all, so guard against
        # an empty list before indexing into it.
        capitals = c.get("capitals", [])
        capital = capitals[0]["name"] if capitals else "N/A"
        codes = c.get("codes", {})

        countries.append({
            "name": c["names"]["common"],
            "capital": capital,
            "region": c.get("region", "N/A"),
            "population": c.get("population", 0),
            "alpha_2": codes.get("alpha_2", "N/A"),
            "alpha_3": codes.get("alpha_3", "N/A"),
            "ccn3": codes.get("ccn3", "N/A"),
        })
    return countries


def search_by_name(countries, term):
    """Return every country whose name contains the given search term.

    The match is case-insensitive and a partial match (a term of "land"
    will match "Iceland", "Ireland", "Finland", etc.).

    Args:
        countries: the flat list of country dicts from parse_countries().
        term: the search string entered by the user.

    Returns:
        A list of matching country dicts (empty if there are no matches).
    """
    term = term.strip().lower()
    return [c for c in countries if term in c["name"].lower()]


def filter_by_region(countries, region):
    """Return every country in a given region.

    The region match is case-insensitive and exact (not a partial match
    like search_by_name) — region names come from a known, finite list,
    so a substring match would risk grouping unrelated regions together.

    Args:
        countries: the flat list of country dicts from parse_countries().
        region: the region name to match (e.g. "Europe").

    Returns:
        A list of matching country dicts (empty if the region has no
        countries in the dataset).
    """
    region = region.strip().lower()
    return [c for c in countries if c["region"].lower() == region]


def get_valid_regions(countries):
    """Return the sorted list of distinct region names present in the data."""
    regions = []
    for c in countries:
        region = c["region"]
        if region != "N/A" and region not in regions:
            regions.append(region)
    return sorted(regions)


# ---------------------------------------------------------------------------
# World Bank: fetching and parsing
# ---------------------------------------------------------------------------

def fetch_world_bank_indicator(country_code, indicator_code, start_year=None, end_year=None):
    """Fetch a single indicator's time series for one country.

    Args:
        country_code: ISO country code (alpha-3, as used elsewhere in this
            program) identifying the country.
        indicator_code: World Bank indicator code, e.g. "NY.GDP.MKTP.CD".
        start_year: optional inclusive start of the date range to request.
        end_year: optional inclusive end of the date range to request.

    Returns:
        A list of raw World Bank data entries (dicts with "date" and
        "value" keys, among others), or None if the request failed
        (network error or non-200 status code). Returns an empty list if
        the request succeeded but the country/indicator combination has
        no data.
    """
    url = f"{WORLD_BANK_BASE_URL}/country/{country_code}/indicator/{indicator_code}"
    params = {"format": "json", "per_page": 1000}
    if start_year is not None and end_year is not None:
        params["date"] = f"{start_year}:{end_year}"

    try:
        r = requests.get(url, params=params)
    except requests.exceptions.RequestException as e:
        print(f"World Bank request failed: {e}")
        return None

    if r.status_code != 200:
        print(f"World Bank API returned status {r.status_code}")
        return None

    payload = r.json()
    # A successful response is [metadata, data]. An invalid country or
    # indicator code still returns 200 but with data as None (or missing
    # entirely), so that's treated as "no data" rather than an error.
    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        return []
    return payload[1]


def parse_world_bank_data(raw_entries):
    """Reshape raw World Bank entries into a flat, year-sorted list.

    Args:
        raw_entries: the list returned by fetch_world_bank_indicator().

    Returns:
        A list of {"year": int, "value": float or None} dicts, sorted
        oldest to newest. A None value means the World Bank has no figure
        for that year, as distinct from a genuine zero.
    """
    parsed = []
    for entry in raw_entries:
        year = entry.get("date")
        if year is None:
            continue
        value = entry.get("value")
        parsed.append({
            "year": int(year),
            "value": float(value) if value is not None else None,
        })
    parsed.sort(key=lambda p: p["year"])
    return parsed


def get_latest_value(series):
    """Return the most recent {"year", "value"} entry with a non-null value.

    Args:
        series: a list of {"year", "value"} dicts, as returned by
            parse_world_bank_data().

    Returns:
        The most recent entry with data, or None if the series is empty
        or every entry has a null value.
    """
    for entry in reversed(series):
        if entry["value"] is not None:
            return entry
    return None


def compute_gdp_per_capita(gdp, population):
    """Compute GDP per capita from raw GDP and population figures.

    Args:
        gdp: total GDP in current US$.
        population: total population.

    Returns:
        GDP per capita as a float, or None if either input is missing or
        zero (population of zero would otherwise raise ZeroDivisionError).
    """
    if not gdp or not population:
        return None
    return gdp / population


# ---------------------------------------------------------------------------
# Feature 1: GDP per capita for a country
# ---------------------------------------------------------------------------

def display_gdp_per_capita(country):
    gdp_series = parse_world_bank_data(
        fetch_world_bank_indicator(country["alpha_3"], INDICATOR_GDP_TOTAL) or []
    )
    reported_series = parse_world_bank_data(
        fetch_world_bank_indicator(country["alpha_3"], INDICATOR_GDP_PER_CAPITA) or []
    )
    latest_gdp = get_latest_value(gdp_series)
    latest_reported = get_latest_value(reported_series)

    print(f"\n--- GDP per Capita: {country['name']} ---")

    if latest_gdp is None and latest_reported is None:
        print("No GDP data found for this country.")
        return

    print(f"Population: {country['population']:,}" if country["population"] else "Population: N/A")

    if latest_gdp is not None:
        print(f"GDP, current US$ ({latest_gdp['year']}): ${latest_gdp['value']:,.0f}")
    else:
        print("GDP, current US$: N/A")

    computed = compute_gdp_per_capita(
        latest_gdp["value"] if latest_gdp else None, country["population"]
    )
    print(f"Computed GDP per capita: ${computed:,.2f}" if computed is not None else "Computed GDP per capita: N/A")

    if latest_reported is not None:
        print(f"World Bank reported GDP per capita ({latest_reported['year']}): ${latest_reported['value']:,.2f}")
    else:
        print("World Bank reported GDP per capita: N/A")

    if computed is not None and latest_reported is not None:
        print(f"Difference (computed vs. reported): ${abs(computed - latest_reported['value']):,.2f}")


# ---------------------------------------------------------------------------
# Feature 2: rank countries in a region by GDP
# ---------------------------------------------------------------------------

def display_region_ranking(countries, region):
    matches = filter_by_region(countries, region)

    ranked = []
    no_data = []
    for c in matches:
        series = parse_world_bank_data(
            fetch_world_bank_indicator(c["alpha_3"], INDICATOR_GDP_TOTAL) or []
        )
        latest = get_latest_value(series)
        if latest is not None:
            ranked.append({"name": c["name"], "year": latest["year"], "gdp": latest["value"]})
        else:
            no_data.append(c["name"])
    ranked.sort(key=lambda r: r["gdp"], reverse=True)

    print(f"\n--- GDP Ranking: {region} ---")
    if not ranked:
        print("No GDP data found for any country in this region.")
    else:
        for i, r in enumerate(ranked, start=1):
            print(f"{i}. {r['name']} — ${r['gdp']:,.0f} ({r['year']})")

    if no_data:
        print("\nNo GDP data available for:")
        for name in no_data:
            print(f"  - {name}")


# ---------------------------------------------------------------------------
# Feature 3: population growth outlook
# ---------------------------------------------------------------------------

def display_population_growth(country):
    series = parse_world_bank_data(
        fetch_world_bank_indicator(country["alpha_3"], INDICATOR_POPULATION_GROWTH) or []
    )
    latest = get_latest_value(series)

    print(f"\n--- Population Growth Outlook: {country['name']} ---")
    print(f"Current population: {country['population']:,}" if country["population"] else "Current population: N/A")

    if latest is None:
        print("Population growth rate: N/A")
        return

    rate = latest["value"]
    trend = "growing" if rate > 0 else "shrinking" if rate < 0 else "stable"
    print(f"Population growth rate ({latest['year']}): {rate:.2f}% — {trend}")


# ---------------------------------------------------------------------------
# Feature 4: multi-year trend chart (GDP or population)
# ---------------------------------------------------------------------------

def plot_trend(country_name, series, label, units):
    """Render an interactive line chart for a time series.

    Includes a date range slider (matplotlib.widgets.Slider) to re-slice
    the visible years, and hover annotations (mplcursors) showing the
    exact value at a given point.
    """
    points = [(p["year"], p["value"]) for p in series if p["value"] is not None]
    if not points:
        print(f"No data available to plot for {label} in {country_name}.")
        return

    years = []
    values = []
    for year, value in points:
        years.append(year)
        values.append(value)

    fig, ax = plt.subplots()
    plt.subplots_adjust(bottom=0.28)
    line, = ax.plot(years, values, marker="o")
    ax.set_title(f"{label} Trend — {country_name}")
    ax.set_xlabel("Year")
    ax.set_ylabel(f"{label} ({units})")

    # Two plain Sliders (rather than a single RangeSlider) so both ends of
    # the visible range are independently adjustable using the native
    # matplotlib.widgets.Slider widget called for in the spec.
    start_axis = plt.axes([0.15, 0.12, 0.7, 0.03])
    end_axis = plt.axes([0.15, 0.05, 0.7, 0.03])
    start_slider = Slider(start_axis, "Start year", years[0], years[-1], valinit=years[0], valstep=1)
    end_slider = Slider(end_axis, "End year", years[0], years[-1], valinit=years[-1], valstep=1)

    def update(_):
        """Called automatically by matplotlib whenever a slider moves.
        Reads the current slider positions and redraws the chart with
        the new x-axis range."""
        start = start_slider.val
        end = end_slider.val
        if start < end:
            ax.set_xlim(start, end)
            fig.canvas.draw_idle()

    start_slider.on_changed(update)
    end_slider.on_changed(update)

    cursor = mplcursors.cursor(line, hover=True)
    cursor.connect("add", lambda sel: sel.annotation.set_text(
        f"{int(sel.target[0])}: {sel.target[1]:,.0f}"
    ))

    plt.show()


def get_trend_indicator_choice():
    options = {
        "1": (INDICATOR_GDP_TOTAL, "GDP", "current US$"),
        "2": (INDICATOR_POPULATION_TOTAL, "Population", "people"),
    }
    while True:
        print("1. GDP\n2. Population")
        choice = input("Chart which indicator (1-2): ").strip()
        if choice in options:
            return options[choice]
        print("Please enter 1 or 2.")


def get_year_range():
    while True:
        raw_start = input(f"Start year ({WORLD_BANK_MIN_YEAR}-{WORLD_BANK_MAX_YEAR}): ").strip()
        raw_end = input(f"End year ({WORLD_BANK_MIN_YEAR}-{WORLD_BANK_MAX_YEAR}): ").strip()
        if not (raw_start.isdigit() and raw_end.isdigit()):
            print("Years must be whole numbers.")
            continue

        start, end = int(raw_start), int(raw_end)
        in_bounds = WORLD_BANK_MIN_YEAR <= start <= WORLD_BANK_MAX_YEAR and WORLD_BANK_MIN_YEAR <= end <= WORLD_BANK_MAX_YEAR
        if not in_bounds:
            print(f"Both years must fall between {WORLD_BANK_MIN_YEAR} and {WORLD_BANK_MAX_YEAR}.")
            continue
        if start >= end:
            print("Start year must be before end year.")
            continue
        return start, end


def show_trend_chart(country):
    indicator_code, label, units = get_trend_indicator_choice()
    start, end = get_year_range()

    raw = fetch_world_bank_indicator(country["alpha_3"], indicator_code, start, end)
    if raw is None:
        print("Could not retrieve trend data due to an API error.")
        return

    series = parse_world_bank_data(raw)
    if not any(p["value"] is not None for p in series):
        print(f"No data found for {label} in {country['name']} between {start} and {end}.")
        return

    plot_trend(country["name"], series, label, units)


# ---------------------------------------------------------------------------
# Menu and main loop
# ---------------------------------------------------------------------------

def show_menu():
    print("\n=== Global Economic Insight Portal ===")
    print("1. GDP per capita for a country")
    print("2. Rank countries in a region by GDP")
    print("3. Population growth outlook for a country")
    print("4. Multi-year trend chart (GDP or population)")
    print("5. Quit")


def get_menu_choice():
    while True:
        choice = input("Choose an option (1-5): ").strip()
        if choice in {"1", "2", "3", "4", "5"}:
            return choice
        print("Please enter a number from 1 to 5.")


def choose_from_matches(matches):
    print("Multiple matches found:")
    for i, c in enumerate(matches, start=1):
        print(f"  {i}. {c['name']}")
    while True:
        pick = input(f"Pick a number (1-{len(matches)}): ").strip()
        if pick.isdigit() and 1 <= int(pick) <= len(matches):
            return matches[int(pick) - 1]
        print("Invalid selection.")


def select_country(countries, prompt="Enter country name: "):
    while True:
        term = input(prompt).strip()
        if not term:
            print("Please enter a country name.")
            continue
        matches = search_by_name(countries, term)
        if not matches:
            print(f'No countries found matching "{term}".')
            return None
        if len(matches) == 1:
            return matches[0]
        return choose_from_matches(matches)


def select_region(countries):
    valid_regions = get_valid_regions(countries)
    while True:
        term = input("Enter region: ").strip()
        match = None
        for r in valid_regions:
            if r.lower() == term.lower():
                match = r
                break
        if match:
            return match
        print(f'"{term}" is not a recognized region.')
        print("Valid regions: " + ", ".join(valid_regions))
        if input("Try again? (y/n): ").strip().lower() != "y":
            return None


def main():
    raw = fetch_countries()
    if raw is None:
        print("Could not load country data. Exiting.")
        return
    countries = parse_countries(raw)

    while True:
        show_menu()
        choice = get_menu_choice()

        if choice == "1":
            country = select_country(countries)
            if country:
                display_gdp_per_capita(country)
        elif choice == "2":
            region = select_region(countries)
            if region:
                display_region_ranking(countries, region)
        elif choice == "3":
            country = select_country(countries)
            if country:
                display_population_growth(country)
        elif choice == "4":
            country = select_country(countries)
            if country:
                show_trend_chart(country)
        elif choice == "5":
            print("Goodbye!")
            break


if __name__ == "__main__":
    main()