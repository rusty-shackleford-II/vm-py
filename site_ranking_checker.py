import asyncio
import os
import sys
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    import pandas as pd  # type: ignore
    import requests  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # Will validate at runtime if Excel processing is requested
    requests = None


# Ensure local imports work when running this file directly
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from google_searcher import GoogleSearcher, OrganicResult  # type: ignore  # noqa: E402
from geocoding_service import get_detailed_geocoding_info  # type: ignore  # noqa: E402

# Try to import maps searcher functionality
try:
    from google_review_fetcher import GoogleBusinessResearcher  # type: ignore  # noqa: E402
    MAPS_AVAILABLE = True
except ImportError:
    MAPS_AVAILABLE = False
    GoogleBusinessResearcher = None

# Hardcoded output file
OUTPUT_FILE = "/Users/warren/dev/ranking_experiment.xlsx"


@dataclass
class RankingHit:
    position: int
    title: str
    url: str
    snippet: str


def _normalize_domain(domain: str) -> str:
    domain = domain.strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _hostname_from_url(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url if "://" in url else f"http://{url}")
        host = (parsed.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host or None
    except Exception:
        return None


def _url_matches_domain(url: str, target_domain: str) -> bool:
    host = _hostname_from_url(url)
    if not host:
        return False
    target = _normalize_domain(target_domain)
    return host == target or host.endswith("." + target)


async def check_domain_ranking(
    *,
    domain: str,
    query: str,
    location: str,
    max_pages: int = 10,
    results_per_page: int = 10,
    enhanced_mode: bool = False,
) -> Tuple[Optional[int], List[RankingHit]]:
    """Check a domain's Google ranking for a localized search.

    Args:
        domain: Target business domain (e.g., "example.com"). Subdomains/pages count as hits.
        query: Search query (e.g., "laundromat").
        location: Localized location (e.g., "San Francisco, California").
        max_pages: How many pages to scan (default 10 => up to 100 results).
        results_per_page: Results per page (default 10).
        enhanced_mode: Whether to enable enhanced parsing mode in the searcher.

    Returns:
        (first_position, hits)
        - first_position: The first ranking position if found, otherwise None.
        - hits: All matching hits with their positions.
    """

    total_results = max(1, min(100, max_pages * results_per_page))

    searcher = GoogleSearcher(enhanced_mode=enhanced_mode)
    results: List[OrganicResult] = await searcher.search_organic_results(
        query=query,
        location=location,
        num_links=total_results,
    )

    hits: List[RankingHit] = []
    first_position: Optional[int] = None

    for result in results:
        if _url_matches_domain(result.url, domain):
            hit = RankingHit(
                position=result.position,
                title=result.title,
                url=result.url,
                snippet=result.snippet,
            )
            hits.append(hit)
            if first_position is None or result.position < first_position:
                first_position = result.position

    return first_position, hits


async def check_local_business_ranking(
    *,
    domain: str,
    query: str,
    location: str,
    max_business_results: int = 20,
) -> Tuple[Optional[int], List[RankingHit]]:
    """Check a domain's ranking within Google local business results.

    Considers the first `max_business_results` local business hits. Matches when the
    business website's domain equals the target domain or is a subdomain.
    """

    searcher = GoogleSearcher(enhanced_mode=False)
    businesses = await searcher.search_local_businesses(
        query=query, location=location, max_results=max_business_results
    )

    hits: List[RankingHit] = []
    first_position: Optional[int] = None

    for idx, biz in enumerate(businesses, start=1):
        website = getattr(biz, "website", None) or ""
        if website and _url_matches_domain(website, domain):
            hit = RankingHit(
                position=idx,
                title=getattr(biz, "name", ""),
                url=website,
                snippet="",
            )
            hits.append(hit)
            if first_position is None or idx < first_position:
                first_position = idx

    return first_position, hits


async def _demo() -> None:
    domain = "hemisplumbing.com"
    location = "San Mateo, CA"
    query = "plumber"

    print(f"Checking ranking for {domain!r} in {location!r} for query {query!r}...")
    
    maps_rank, local_rank, organic_rank = await _compute_ranks(domain, query, location)

    print(f"\n=== Results Summary ===")
    print(f"Maps ranking: {maps_rank if maps_rank else 'Not found'}")
    print(f"Local business ranking: {local_rank if local_rank else 'Not found'}")
    print(f"Organic ranking: {organic_rank if organic_rank else 'Not found'}")
    
    print(f"\n=== Detailed Results ===")
    
    # Get detailed results for display
    organic_task = check_domain_ranking(
        domain=domain,
        query=query,
        location=location,
        max_pages=10,
        results_per_page=10,
        enhanced_mode=False,
    )
    local_task = check_local_business_ranking(
        domain=domain,
        query=query,
        location=location,
        max_business_results=20,
    )

    (first_pos_org, hits_org), (first_pos_local, hits_local) = await asyncio.gather(
        organic_task, local_task
    )

    # Organic results
    print("\n--- Organic results ---")
    if hits_org:
        for hit in sorted(hits_org, key=lambda h: h.position):
            print(f"  #{hit.position}: {hit.title}")
            print(f"     {hit.url}")
    else:
        print("No matching organic URLs found.")

    # Local business results
    print("\n--- Local business results ---")
    if hits_local:
        for hit in sorted(hits_local, key=lambda h: h.position):
            print(f"  #{hit.position}: {hit.title}")
            print(f"     {hit.url}")
    else:
        print("No matching local business websites found.")


async def check_maps_ranking(
    *,
    domain: str,
    query: str,
    location: str,
    max_business_results: int = 20,
) -> Optional[int]:
    """Check domain ranking in Google Maps search results."""
    if not MAPS_AVAILABLE or GoogleBusinessResearcher is None:
        return None
    
    try:
        researcher = GoogleBusinessResearcher()
        # Search for businesses using the query and location
        search_query = f"{query} {location}"
        
        # This is a simplified approach - you may need to adjust based on the actual API
        # For now, return None as we need to implement the maps search ranking logic
        return None
    except Exception:
        return None


async def _compute_ranks(domain: str, query: str, location: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    organic_task = check_domain_ranking(
        domain=domain,
        query=query,
        location=location,
        max_pages=10,
        results_per_page=10,
        enhanced_mode=False,
    )
    local_task = check_local_business_ranking(
        domain=domain,
        query=query,
        location=location,
        max_business_results=20,
    )
    maps_task = check_maps_ranking(
        domain=domain,
        query=query,
        location=location,
        max_business_results=20,
    )

    (first_pos_org, _), (first_pos_local, _), maps_rank = await asyncio.gather(
        organic_task, local_task, maps_task
    )
    return maps_rank, first_pos_local, first_pos_org


def _resolve_required_columns(df_columns: List[str]) -> Dict[str, str]:
    lower_map = {c.lower().strip(): c for c in df_columns}
    required = {}
    for key in ["business_name", "address", "domain", "query", "city", "state", "neighborhood", "near"]:
        if key not in lower_map:
            raise ValueError(
                f"Missing required column '{key}'. Found columns: {list(df_columns)}"
            )
        required[key] = lower_map[key]
    return required


def _today_col_names() -> Tuple[str, str, str]:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"maps-{today}", f"local-biz-{today}", f"organic-{today}"


def _extract_city_state(address: str) -> str:
    """Extract city, state from address for location parameter."""
    try:
        # Simple parsing: "850 Jones St, San Francisco, CA 94109, United States"
        # Expected format: ..., City, State, ...
        parts = address.split(", ")
        if len(parts) >= 3:
            city = parts[-3]  # San Francisco
            state = parts[-2].split()[0]  # CA (remove zip if present)
            return f"{city}, {state}"
        return address  # Fallback to full address
    except Exception:
        return address


def _extract_neighborhood(address: str) -> Optional[str]:
    """Extract neighborhood from geocoding API if available."""
    try:
        if requests is None:
            return None
            
        from config import GOOGLE_MAPS_API_KEY
        
        # Use the full address for geocoding
        encoded_address = urllib.parse.quote(address)
        endpoint = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={GOOGLE_MAPS_API_KEY}"
        
        response = requests.get(endpoint, timeout=10)
        if response.status_code != 200:
            return None
            
        result = response.json()
        if result['status'] != 'OK' or not result['results']:
            return None
            
        # Look for neighborhood in address components
        geocoding_result = result['results'][0]
        if "address_components" in geocoding_result:
            for component in geocoding_result["address_components"]:
                types = component.get("types", [])
                if "neighborhood" in types:
                    return component["long_name"]
        return None
    except Exception:
        return None


def _parse_address_components(address: str) -> Dict[str, str]:
    """Parse address into city, state components."""
    try:
        # "850 Jones St, San Francisco, CA 94109, United States"
        parts = address.split(", ")
        if len(parts) >= 3:
            city = parts[-3]  # San Francisco
            state = parts[-2].split()[0]  # CA (remove zip)
            return {"city": city, "state": state}
        return {"city": "", "state": ""}
    except Exception:
        return {"city": "", "state": ""}


def _create_seeded_excel_file() -> None:
    """Create the Excel file with initial seed data."""
    if pd is None:
        raise RuntimeError("pandas is required for Excel processing.")
    
    base_address = "850 Jones St, San Francisco, CA 94109, United States"
    base_business = "san francisco laundromat"
    base_domain = "sflaundromat.com"
    base_query = "laundromat"
    
    # Parse address components
    addr_parts = _parse_address_components(base_address)
    city = addr_parts["city"]
    state = addr_parts["state"]
    
    # Get neighborhood
    neighborhood = _extract_neighborhood(base_address)
    
    # Create multiple rows for different search approaches
    rows = []
    
    # Row 1: City, State search
    rows.append({
        "business_name": base_business,
        "address": base_address,
        "domain": base_domain,
        "query": base_query,
        "city": city,
        "state": state,
        "neighborhood": neighborhood or "",
        "near": f"{city}, {state}"
    })
    
    # Row 2: Neighborhood search (if neighborhood exists)
    if neighborhood:
        rows.append({
            "business_name": base_business,
            "address": base_address,
            "domain": base_domain,
            "query": base_query,
            "city": city,
            "state": state,
            "neighborhood": neighborhood,
            "near": f"{neighborhood}, {city}, {state}"
        })
    
    df = pd.DataFrame(rows)
    
    # Add ranking columns
    maps_col, local_col, organic_col = _today_col_names()
    df[maps_col] = None
    df[local_col] = None
    df[organic_col] = None
    
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"Created seeded Excel file: {OUTPUT_FILE}")
    print(f"Added {len(rows)} search variations")
    if neighborhood:
        print(f"Neighborhood found: {neighborhood}")


async def _process_excel_async(excel_path: str, sheet_name: Optional[str] = None) -> None:
    if pd is None:
        raise RuntimeError(
            "pandas is required for Excel processing. Please install pandas and openpyxl."
        )

    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel file not found: {excel_path}")

    df = pd.read_excel(excel_path, sheet_name=sheet_name)  # type: ignore

    # Support single sheet (DataFrame) or dict of DataFrames
    if isinstance(df, dict):
        # Process each sheet
        for name, sub_df in df.items():
            await _process_dataframe_inplace(sub_df)
        # Write back all sheets
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:  # type: ignore
            for name, sub_df in df.items():
                sub_df.to_excel(writer, sheet_name=name, index=False)
    else:
        await _process_dataframe_inplace(df)
        df.to_excel(excel_path, index=False)  # type: ignore


async def _process_dataframe_inplace(df) -> None:
    cols = list(df.columns)
    col_map = _resolve_required_columns(cols)
    maps_col, local_col, organic_col = _today_col_names()

    # Ensure columns exist (overwrite later if they already exist)
    if maps_col not in df.columns:
        df[maps_col] = None
    if local_col not in df.columns:
        df[local_col] = None
    if organic_col not in df.columns:
        df[organic_col] = None

    # Iterate rows and compute
    # Note: Run sequentially to avoid hammering the SERP API
    for idx, row in df.iterrows():
        domain = str(row[col_map["domain"]]).strip()
        query = str(row[col_map["query"]]).strip()
        near = str(row[col_map["near"]]).strip()

        if not domain or not query or not near or domain.lower() == "nan":
            df.at[idx, maps_col] = None
            df.at[idx, local_col] = None
            df.at[idx, organic_col] = None
            continue

        # Use the 'near' field as the location for searches
        maps_rank, local_rank, organic_rank = await _compute_ranks(domain, query, near)

        df.at[idx, maps_col] = maps_rank
        df.at[idx, local_col] = local_rank
        df.at[idx, organic_col] = organic_rank


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Check site ranking (organic & local)")
    parser.add_argument("--demo", action="store_true", help="Run demo instead of processing Excel")
    parser.add_argument("--sheet", type=str, default=None, help="Optional sheet name")
    args = parser.parse_args()

    if args.demo:
        asyncio.run(_demo())
    else:
        if pd is None:
            raise SystemExit(
                "pandas is required for Excel processing. Install with: pip install pandas openpyxl"
            )
        
        # Create Excel file if it doesn't exist
        if not os.path.exists(OUTPUT_FILE):
            print(f"Excel file {OUTPUT_FILE} not found. Creating with seed data...")
            _create_seeded_excel_file()
        
        asyncio.run(_process_excel_async(OUTPUT_FILE, args.sheet))
        print(f"Saved rankings to {OUTPUT_FILE}")


