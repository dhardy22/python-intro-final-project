import requests
import os
from dotenv import load_dotenv


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

    # Note: only "objects" is carried forward — "meta" applied to a
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


def show_menu():
    print("\n=== Global Economic Insight Portal ===")
    print("1. GDP per capita for a country")
    print("2. Rank countries in a region by GDP")
    print("3. Population growth outlook for a country")
    print("4. Multi-year trend chart (GDP or population)")
    print("5. Quit")

