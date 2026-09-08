# Global Economic Insight Portal

A command-line tool that combines country reference data (REST Countries)
with economic indicators (World Bank Open Data API) to surface insights
you can't get from either data source alone — computed metrics, regional
rankings, and multi-year trends, rather than a flat lookup.

## What this program does

Most country-data tools just display facts: population, capital, region.
This one goes a step further by pairing that reference data with real
economic indicators and doing the math to surface something worth
looking at:

1. **GDP per capita — computed, not just fetched.** Pulls raw GDP from
   the World Bank API and population from REST Countries, and computes
   GDP per capita locally. The result is cross-checked against the
   World Bank's own `NY.GDP.PCAP.CD` indicator as a sanity check, so any
   mismatch between "computed" and "reported" is visible rather than
   hidden.
2. **Richest/poorest in a region — ranking.** Given a region (e.g.
   "Europe", "Africa"), fetches GDP for every country in that region and
   sorts them, surfacing the highest and lowest economies in context —
   not just one country in isolation.
3. **Population growth outlook.** For any searched country, shows the
   current population alongside its recent growth rate, giving a sense
   of trajectory (growing, shrinking, stable) rather than a single
   static snapshot.
4. **Multi-year trend visualization — interactive.** Pulls a historical
   time series (GDP or population over a date range, e.g. 2010–2023) and
   renders it as a chart with two interactive elements:
   - a **date range slider** (native `matplotlib.widgets.Slider`) to
     re-slice the visible years without re-running the program, and
   - **hover annotations** (via `mplcursors`) that show the exact value
     for a given year when the mouse hovers near a data point.

   This makes the chart something to explore, not just a static image —
   trends are visible at a glance, and exact figures are one hover away
   rather than requiring a separate table.

## Data sources

| Source | Used for | Auth |
|---|---|---|
| [REST Countries](https://restcountries.com) | Country names, regions, population, currency, ISO codes | API key (Bearer token) |
| [World Bank Open Data API](https://data.worldbank.org) | GDP, GDP per capita, population growth, historical indicators | None — fully open |

## Joining the two data sources

REST Countries and World Bank data are linked by **ISO 3166 country
code**, not by country name. Names are unreliable as a join key — the
same country can appear as `"United States"` in one source and
`"United States of America"` or `"US"` in another, and matches would
silently fail on anything with accents, abbreviations, or alternate
official names (e.g. `"Korea, Rep."` vs `"South Korea"`).

- **REST Countries** already returns a `codes` object per country
  (`alpha_2`, `alpha_3`, `ccn3`, etc.) — this is captured in
  `parse_countries()` alongside `name`, `capital`, `region`, and
  `population`, even though it isn't displayed directly. It exists in
  the flat dict purely as the connector to the World Bank side.
- **World Bank's** endpoint takes the country code directly as part of
  the URL path: `/v2/country/{country_code}/indicator/{indicator_code}`.
  Which exact code format it expects (alpha-2 vs. alpha-3) needs to be
  confirmed once tested live — the two APIs aren't guaranteed to prefer
  the same one.

**How the code flows through the program:** once a country is selected
via `search_by_name()` (or picked from a disambiguation list, per the
input safeguards above), its dict already contains the ISO code from
the REST Countries fetch. That code is passed directly into the World
Bank fetch function as an argument — no separate lookup step, and no
name-matching involved:

```python
target_country = search_by_name(countries, "germany")  # returns the matched dict
gdp_data = fetch_world_bank_indicator(
    country_code=target_country["alpha_3"],
    indicator_code="NY.GDP.MKTP.CD"
)
```

This keeps the join key an internal implementation detail — the user
only ever types a country *name*; the code lookup happens transparently
using data already fetched, rather than asking the user to know or
enter an ISO code themselves.

**Known limitation:** not every REST Countries entry will have a
matching World Bank record, even with a valid code. Territories and
dependencies (e.g. Isle of Man) may exist in one dataset and not the
other. This is handled the same way as other missing-data cases —
`N/A` displayed rather than a crash — but is worth testing explicitly
against a few known dependencies/territories once both fetch functions
are wired together.

## Requirements

| Package | Used for | Notes |
|---|---|---|
| `requests` | All API calls (REST Countries, World Bank) | Core dependency |
| `python-dotenv` | Loading `MY_API_KEY` from `.env` | Only needed for the REST Countries key — no `.env` value is required for World Bank calls |
| `matplotlib` | Chart rendering **and** the date range slider | The slider is native to matplotlib (`matplotlib.widgets.Slider`) — no separate library needed for that piece |
| `mplcursors` | Hover annotations on the trend chart | Small, focused add-on specifically for hover-to-see-value; matplotlib does not include this natively |

## Architecture & design standards

This project is built against a specific set of engineering standards,
not just "make it work":

- **API calls live in dedicated functions**, never inline in the main
  loop. Query parameters (country code, indicator code, date range) are
  passed in as function arguments rather than hard-coded into the URL —
  so the same function can be reused for any country/indicator/date
  combination.
- **Fetching, parsing, and display are cleanly separated.** A function
  that fetches raw JSON never also reshapes it, and a function that
  reshapes data never also prints it. Each function has one job and
  returns a value, rather than relying on side effects.
- **Data transformation is isolated from data fetching.** Raw API
  responses are parsed into flat, predictable dictionaries in their own
  function before any calculation or display logic touches them.
  `.get()` with sensible defaults is used throughout to handle missing
  keys (missing GDP figures, missing capitals, missing indicators)
  without crashing.
- **Errors are caught at the right level.** Network failures and bad
  status codes are handled inside the fetch functions themselves (where
  the failure actually happens), not with a broad try/except wrapped
  around the entire program — so the program can report exactly what
  failed and continue running, or exit gracefully with a clear message,
  rather than dying with a raw traceback.
- **Code should be readable without relying on comments to explain it**
  — clear function and variable names carry most of the weight;
  comments are reserved for genuinely non-obvious decisions (e.g. why a
  particular default value or edge case is handled a certain way).

## Clarifications

- **"Region" follows REST Countries' region groupings** (e.g. Europe,
  Africa, Asia, Americas, Oceania), not the World Bank's own regional
  classification — the two don't always match one-to-one. When a region
  lookup returns fewer countries than expected, this is the most likely
  reason.
- **GDP figures are in current US dollars**, as reported by the World
  Bank, and are not inflation-adjusted across years. Multi-year trend
  comparisons reflect nominal, not real, GDP unless noted otherwise.
- **Not every country has complete data.** Smaller nations, territories,
  and some non-UN-member entities in REST Countries' dataset may have no
  matching World Bank record at all. These are shown as `N/A` rather
  than omitted silently, so it's clear where data is missing versus
  where it's genuinely zero.
- **This tool is for educational/informational use only.** It is not
  financial, economic, or investment advice, and figures should not be
  used as the sole basis for real-world financial decisions.

## CLI usage

```
=== Global Economic Insight Portal ===
1. GDP per capita for a country
2. Rank countries in a region by GDP
3. Population growth outlook for a country
4. Multi-year trend chart (GDP or population)
5. Quit
Choose an option (1-5):
```

### Input safeguards

- **Menu choice validation.** Only `1`–`5` are accepted; anything else
  (letters, blank input, out-of-range numbers) re-prompts with a message
  rather than crashing or silently doing nothing.
- **Country name matching** is case-insensitive and allows partial
  matches (e.g. "korea" matches both North and South Korea) — if more
  than one match is found, the tool lists them and asks the user to
  pick one rather than guessing.
- **Region name matching** is case-insensitive; an unrecognized region
  name shows the list of valid regions instead of returning an empty,
  unexplained result.
- **Date range validation** for the trend tool (option 4) — start year
  must be before the end year, and both must fall within the range the
  World Bank actually has data for. Invalid ranges re-prompt with the
  valid bounds shown.

### Fallback behavior

- **Missing GDP or indicator data** for a given country/year displays
  `N/A` in that field rather than raising an error or omitting the row
  entirely — so a gap in the data is visible, not invisible.
- **API request failures** (network errors, non-200 responses, rate
  limits) are caught and reported with a plain-language message; the
  program returns to the main menu rather than crashing, so one failed
  request doesn't end the session.
- **Empty results** (e.g. a region with no matching data available) are
  explicitly reported as "no data found," distinguishing a real "zero
  results" outcome from a silent failure.
- **Partial data availability**: if some countries in a region have GDP
  data and others don't, the ranking still displays — countries with no
  data are listed separately at the bottom rather than breaking the
  whole ranking.

## Setup

1. Clone the repository.
2. Create a `.env` file in the project root with your REST Countries key:
   ```
   MY_API_KEY=your_key_here
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Run the tool:
   ```
   python main.py
   ```

No key is required for the World Bank API portion of the tool.

## Extension track

**Primary: (A) Visualization.** The multi-year trend chart (feature 4)
is the extension focus — polished, well-labeled, and interactive:
- Chart title, axis titles, and clear units (e.g. "GDP, current US$"
  rather than a bare number).
- A **date range slider** (native `matplotlib.widgets.Slider`) to
  adjust the visible years in real time.
- **Hover annotations** (`mplcursors`) showing the exact value at a
  given point, so precise figures don't require a separate table.

(B) Data cleaning is handled to the extent the core features require it
(missing capitals, missing GDP figures, countries with no World Bank
match) but is not the extension emphasis — visualization polish is
where the additional effort goes.

**Stretch, not prioritized: CSV export.** Once trend data is already
being pulled into a flat list of dicts for charting, exporting the same
data to CSV is a small addition (e.g. `pandas.DataFrame(...).to_csv()`
or the stdlib `csv` module) rather than a separate effort. It's listed
here so the option isn't lost, but it does not take priority over
getting the visualization itself right.

## Version control

Development is tracked through multiple commits showing incremental
progress (e.g. "add fetch_countries with pagination," "add GDP per
capita calculation," "handle missing capital data") rather than one
single commit at the end. Work is submitted via pull request, and
commit messages describe what changed and why — not just "update
main.py" — so the history itself documents how the project evolved.