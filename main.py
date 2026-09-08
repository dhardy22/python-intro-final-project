import requests
import os
from dotenv import load_dotenv

load_dotenv()  # reads MY_API_KEY from a local .env file, if one exists

REST_COUNTRIES_URL = "https://api.restcountries.com/countries/v5"
WORLD_BANK_BASE_URL = "https://api.worldbank.org/v2"


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
    return sorted({c["region"] for c in countries if c["region"] != "N/A"})


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