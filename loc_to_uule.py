from urllib.parse import quote_plus
import uule_grabber

def build_google_search_url(
    query: str,
    city: str,
    region: str,
    country: str,
    hl: str = "en",
    gl: str = "us",
    num: int = 20,
) -> str:
    """
    Build a Google Search URL localized to a specific place using uule.

    query  -> search query (e.g., "popcorn")
    city   -> city name (e.g., "San Francisco")
    region -> region/state/province (e.g., "California")
    country-> country name (e.g., "United States")

    hl = interface language (e.g., "en")
    gl = results country bias (e.g., "us")
    num = number of results (10–100)
    """
    # Construct canonical place string: "City,Region,Country"
    place = f"{city},{region},{country}".strip()

    # Generate uule from canonical place string
    uule = uule_grabber.uule(place)  # returns string like "w+CAIQICI…"
    # Encode q and compose URL
    q = quote_plus(query)
    url = f"https://www.google.com/search?q={q}&hl={hl}&gl={gl}&num={num}&uule={uule}"
    return url


def uule_for_location(
    city: str | None = None,
    region: str | None = None,
    country: str | None = None,
    zipcode: str | None = None,
) -> str:
    """
    Build a canonical location string from any combination of city, region, country, zipcode,
    then return its UULE encoding via uule_grabber.uule.
    Rules:
      - Join only non-empty parts with commas, preserving order: City, Region, Country, Zip
      - Trim whitespace on each part
      - Require at least one non-empty part
    """
    parts = []
    for part in (city, region, country, zipcode):
        if part is None:
            continue
        s = str(part).strip()
        if s:
            parts.append(s)

    if not parts:
        raise ValueError("Provide at least one of city, region, country, or zipcode.")

    canonical = ",".join(parts)
    return uule_grabber.uule(canonical)


# Example:
if __name__ == "__main__":
    url = build_google_search_url(
        query="men's haircut",
        city="San Francisco",
        region="California",
        country="United States",
        hl="en",
        gl="us",
        num=20,
    )
    print(url)
