import requests
import os
from dotenv import load_dotenv


def fetch_countries():
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
    return



def show_menu():
    print("\n=== Global Economic Insight Portal ===")
    print("1. GDP per capita for a country")
    print("2. Rank countries in a region by GDP")
    print("3. Population growth outlook for a country")
    print("4. Multi-year trend chart (GDP or population)")
    print("5. Quit")

