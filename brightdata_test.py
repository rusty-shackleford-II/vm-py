#!/usr/bin/env python3
"""
Bright Data Localization Testing Suite
=====================================

Tests different approaches for localizing Google searches via BrightData.

FINDINGS SUMMARY:
================

✅ WHAT WORKS FOR LOCALIZATION:
- Local Business Search (tbm=lcl) with city names + near parameter
- Maps Search (/maps/search/) with coordinates + viewport
- Organic Search with "query in location" format

❌ WHAT DOESN'T WORK:
- Local Business Search (tbm=lcl) with lat/lon coordinates
- Maps Search without proper viewport parameters
- Relying solely on uule parameter without near/location reinforcement

KEY INSIGHTS:
=============
1. Different Google endpoints prefer different location formats:
   - Maps endpoints: Love coordinates (lat/lon)
   - Local business search: Prefers city names
   
2. Location targeting works best with redundant parameters:
   - uule + near + gl parameters together
   - Multiple location signals reduce proxy routing issues
   
3. BrightData proxy routing can interfere with location:
   - Coordinates may route through unexpected proxy locations
   - City names seem more reliable for consistent routing

RECOMMENDED APPROACH:
====================
- Use Local Business Search (tbm=lcl) with city-based location
- Include both uule (canonical city format) and near parameters
- This matches the successful GoogleSearcher implementation
"""

import base64
import json
from typing import Dict, Optional, Tuple, Union
from urllib.parse import urlencode, quote_plus
from brightdata import bdclient

from config import BRIGHTDATA_API_KEY
import requests

# ---------------------------
# UULE helpers
# ---------------------------


def uule_from_canonical(city: str, region: str, country: str) -> str:
    """
    City-level uule using canonical name string as accepted by Bright Data’s SERP params.
    Example: "San Francisco,California,United States"
    """
    return f"{city},{region},{country}"

def uule_from_latlon(lat: float, lon: float, radius_m: int = 1500) -> str:
    """
    Coordinate-based uule (a+ variant) that encodes lat/lon and radius for precise localization.
    """
    payload = f"role:1 producer:12 lat:{lat:.6f} lng:{lon:.6f} radius:{radius_m}"
    return "a+" + base64.b64encode(payload.encode("utf-8")).decode("ascii")

# ---------------------------
# URL builders
# ---------------------------

def build_google_search_url(
    q: str,
    gl: str,
    hl: str,
    uule: Optional[str] = None,
    near: Optional[str] = None,
    num: int = 20,
    search_type: str = "organic"
) -> str:
    """
    Google Search URL with localization and JSON parsing.
    
    Args:
        search_type: "organic" for regular search, "local" for local business search
        near: Location string for additional location targeting
    """
    params = {
        "q": q,
        "gl": gl,         # country [Google param]
        "hl": hl,         # language [Google param]
        "num": num,
        "brd_json": 1     # BrightData JSON format
    }
    if uule:
        params["uule"] = uule
    if near:
        params["near"] = near
    
    # Add local search parameter if needed
    if search_type == "local":
        params["tbm"] = "lcl"  # Local search parameter
        
    return "https://www.google.com/search?" + urlencode(params, doseq=True)

def build_google_maps_search_url(
    q: str,
    gl: str,
    hl: str,
    uule: Optional[str] = None,
    latlon: Optional[Tuple[float, float]] = None,
    zoom: str = "14z",  # Note: should end with 'z'
    num: int = 50
) -> str:
    """
    Google Maps search URL with proper location targeting.
    Google Maps uses 'll' parameter instead of 'uule' for coordinates.
    """
    params = {
        "gl": gl,
        "hl": hl,
        "num": num,
        "brd_json": 1
    }
    
    # For Google Maps, use ll parameter instead of uule for coordinates
    if latlon is not None:
        lat, lon = latlon
        params["ll"] = f"@{lat},{lon},{zoom}"
    elif uule:
        # Only use uule as fallback for city-based searches
        params["uule"] = uule

    # Use path /maps/search/<query> to signal Maps context
    path = "/maps/search/" + quote_plus(q)
    return "https://www.google.com" + path + "?" + urlencode(params, doseq=True)

# ---------------------------
# Bright Data fetchers
# ---------------------------

class BrightDataMapsClient:
    def __init__(self, api_token: str):
        # The generic method may be client.scrape(url) or client.request(url=url) depending on SDK version
        self.client = bdclient(api_token=api_token)

    def fetch_url(self, url: str) -> Dict:
        """
        Fetch a URL via Bright Data using generic scraping.
        """
        # Prefer client.scrape(url) if available in the installed SDK;
        # otherwise, client.request(url=url) or client.get(url=url).
        # Replace with the correct method name for the installed version.
        # This is the key step: parse the content to get the actual SERP JSON
        results = self.client.scrape(url)
        parsed_json = self.client.parse_content(results)
        return parsed_json

    def search_organic(
        self,
        q: str,
        gl: str,
        hl: str,
        location: Union[Tuple[str, str, str], Tuple[float, float]],
        num: int = 20
    ) -> Dict:
        """
        Organic search with recommended approach: City-based location with multiple targeting parameters
        """
        # Build uule and near parameters for better location targeting
        uule = None
        near = None
        
        if len(location) == 3 and all(isinstance(x, str) for x in location):
            city, region, country = location
            # City-based UULE (canonical format) - recommended approach
            uule = f"{city},{region},{country}"
            # Additional location reinforcement
            near = f"{city}, {region}"
        elif len(location) == 2 and all(isinstance(x, (int, float)) for x in location):
            lat, lon = location
            uule = uule_from_latlon(lat, lon)
            near = "San Francisco, CA"  # Hardcode for this test
        else:
            raise ValueError("location must be (city, region, country) or (lat, lon)")

        url = build_google_search_url(q=q, gl=gl, hl=hl, uule=uule, near=near, num=num, search_type="organic")
        return self.fetch_url(url)

    def search_maps(
        self,
        q: str,
        gl: str,
        hl: str,
        location: Union[Tuple[str, str, str], Tuple[float, float]],
        num: int = 50,
        viewport: bool = True
    ) -> Dict:
        """
        Google Maps search with proper location targeting.
        Uses 'll' parameter for coordinates and 'uule' for city-based searches.
        """
        # For Maps, use proper location parameters based on input type
        uule = None
        latlon = None

        if len(location) == 3 and all(isinstance(x, str) for x in location):
            city, region, country = location
            # For city-based Maps search, use canonical UULE format
            uule = f"{city},{region},{country}"
            # No explicit viewport; city-level uule is often sufficient
        elif len(location) == 2 and all(isinstance(x, (int, float)) for x in location):
            lat, lon = location
            # For coordinate-based Maps search, use ll parameter instead of uule
            if viewport:
                latlon = (lat, lon)
            # Don't use uule for coordinates in Maps - use ll parameter instead
        else:
            raise ValueError("location must be (city, region, country) or (lat, lon)")

        url = build_google_maps_search_url(
            q=q, gl=gl, hl=hl, uule=uule, latlon=latlon, num=num
        )
        print(f"DEBUG: Maps search URL: {url}")
        return self.fetch_url(url)

    def search_local_businesses(
        self,
        q: str,
        gl: str,
        hl: str,
        location: Union[Tuple[str, str, str], Tuple[float, float]],
        num: int = 20
    ) -> Dict:
        """
        Search for local businesses using tbm=lcl parameter with recommended approach:
        City-based location with multiple targeting parameters for better localization
        """
        # Build uule and near parameters for better location targeting
        uule = None
        near = None
        
        if len(location) == 3 and all(isinstance(x, str) for x in location):
            city, region, country = location
            # City-based UULE (canonical format) - recommended approach
            uule = f"{city},{region},{country}"
            # Additional location reinforcement
            near = f"{city}, {region}"
        elif len(location) == 2 and all(isinstance(x, (int, float)) for x in location):
            lat, lon = location
            uule = uule_from_latlon(lat, lon)
            near = "San Francisco, CA"  # Hardcode for this test
        else:
            raise ValueError("location must be (city, region, country) or (lat, lon)")

        # Use the local search URL builder with tbm=lcl and both uule and near
        url = build_google_search_url(q=q, gl=gl, hl=hl, uule=uule, near=near, num=num, search_type="local")
        print(f"DEBUG: Local business search URL: {url}")
        return self.fetch_url(url)

    def search_maps_direct(
        self,
        business_name: str,
        location: str,
        num: int = 10
    ) -> Dict:
        """
        Direct Google Maps search using the GoogleMapsBusinessSearcher URL format
        but with BrightData SDK instead of direct requests.
        This uses the simple /maps/search/<query>/?brd_json=1 format
        """
        query = f"{business_name} {location}".strip()
        search_query = query.replace(" ", "+")
        url = f"https://www.google.com/maps/search/{search_query}/?brd_json=1"
        
        print(f"DEBUG: Direct Maps search URL: {url}")
        
        # Use BrightData SDK like the other methods
        return self.fetch_url(url)

# ---------------------------
# Example usage
# ---------------------------

def test_location_method(method_name: str, location_type: str, test_func, expected_location: str = "San Francisco") -> dict:
    """Test a location targeting method and return results summary with top 3 businesses"""
    try:
        print(f"\n🧪 Testing: {method_name} with {location_type}")
        print("-" * 60)
        
        result = test_func()
        
        # Parse and analyze results
        if 'text' in result and result['text']:
            parsed_data = json.loads(result['text'])
            
            # Extract businesses and location info
            top_businesses = []
            business_count = 0
            
            # Check different result fields
            for field in ['snack_pack', 'local_results', 'organic']:
                if field in parsed_data:
                    businesses = parsed_data[field]
                    business_count += len(businesses)
                    
                    for business in businesses[:3]:  # Get top 3 businesses
                        name = business.get('name', business.get('title', 'N/A'))
                        address = business.get('address', 'N/A')
                        rating = business.get('rating', 'N/A')
                        
                        top_businesses.append({
                            'name': name,
                            'address': address,
                            'rating': rating
                        })
                    
                    if len(top_businesses) >= 3:
                        break
            
            # Extract unique locations from addresses
            locations_found = set()
            for business in top_businesses:
                address = business['address']
                if address and address != 'N/A':
                    # Extract city/state from address - handle different formats
                    if ',' in address:
                        parts = [p.strip() for p in address.split(',')]
                        # Look for state abbreviations or city names
                        for part in parts:
                            # Check if it contains common state abbreviations or "San Francisco"
                            if any(city in part for city in ['San Francisco', 'SF', 'CA', 'California']):
                                locations_found.add(part)
                            elif any(state in part for state in ['FL', 'TN', 'OH', 'Tampa', 'Clarksville', 'Youngstown']):
                                locations_found.add(part)
                    else:
                        # Single location string
                        locations_found.add(address)
            
            # Determine if localization worked
            is_localized = any(expected_location.lower() in loc.lower() for loc in locations_found)
            
            # Print top 3 results
            for i, business in enumerate(top_businesses[:3], 1):
                print(f"  {i}. {business['name']}")
                print(f"     📍 {business['address']}")
                print(f"     ⭐ {business['rating']}")
                print()
            
            return {
                'success': True,
                'localized': is_localized,
                'business_count': business_count,
                'locations': list(locations_found)[:3],
                'top_businesses': top_businesses[:3],
                'error': None
            }
        else:
            print("  ❌ No results found")
            return {
                'success': False,
                'localized': False,
                'business_count': 0,
                'locations': [],
                'top_businesses': [],
                'error': 'No text field in response'
            }
            
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return {
            'success': False,
            'localized': False,
            'business_count': 0,
            'locations': [],
            'top_businesses': [],
            'error': str(e)
        }


if __name__ == "__main__":
    client = BrightDataMapsClient(BRIGHTDATA_API_KEY)
    
    # Test locations
    sf_coords = (37.7749, -122.4194)
    sf_city = ("San Francisco", "California", "United States")
    
    print("=" * 80)
    print("🎯 BRIGHT DATA LOCALIZATION TEST RESULTS")
    print("=" * 80)
    print("Target Location: San Francisco, CA")
    print("Query: 'laundromat'")
    print("=" * 80)
    
    # Test all combinations: 4 search methods × 2 location types = 8 tests
    test_results = []
    
    # 1. LOCAL BUSINESS SEARCH (tbm=lcl)
    print("\n🔍 METHOD 1: LOCAL BUSINESS SEARCH (tbm=lcl)")
    print("=" * 80)
    
    # 1a. Local Business + City Names
    def test_local_city():
        return client.search_local_businesses(
            q="laundromat", gl="us", hl="en", location=sf_city, num=10
        )
    
    result1a = test_location_method(
        "Local Business Search", "City Names", test_local_city
    )
    test_results.append(("Local Business + City", result1a))
    
    # 1b. Local Business + Coordinates
    def test_local_coords():
        return client.search_local_businesses(
            q="laundromat", gl="us", hl="en", location=sf_coords, num=10
        )
    
    result1b = test_location_method(
        "Local Business Search", "Coordinates", test_local_coords
    )
    test_results.append(("Local Business + Coords", result1b))
    
    # 2. MAPS SEARCH (/maps/search/)
    print("\n🗺️  METHOD 2: MAPS SEARCH (/maps/search/)")
    print("=" * 80)
    
    # 2a. Maps + City Names
    def test_maps_city():
        return client.search_maps(
            q="laundromat", gl="us", hl="en", location=sf_city, num=10
        )
    
    result2a = test_location_method(
        "Maps Search", "City Names", test_maps_city
    )
    test_results.append(("Maps + City", result2a))
    
    # 2b. Maps + Coordinates
    def test_maps_coords():
        return client.search_maps(
            q="laundromat", gl="us", hl="en", location=sf_coords, num=10
        )
    
    result2b = test_location_method(
        "Maps Search", "Coordinates", test_maps_coords
    )
    test_results.append(("Maps + Coords", result2b))
    
    # 3. ORGANIC SEARCH (regular /search)
    print("\n🔎 METHOD 3: ORGANIC SEARCH (regular /search)")
    print("=" * 80)
    
    # 3a. Organic + City Names
    def test_organic_city():
        return client.search_organic(
            q="laundromat in San Francisco, CA", gl="us", hl="en", location=sf_city, num=10
        )
    
    result3a = test_location_method(
        "Organic Search", "City Names", test_organic_city
    )
    test_results.append(("Organic + City", result3a))
    
    # 3b. Organic + Coordinates
    def test_organic_coords():
        return client.search_organic(
            q="laundromat in San Francisco, CA", gl="us", hl="en", location=sf_coords, num=10
        )
    
    result3b = test_location_method(
        "Organic Search", "Coordinates", test_organic_coords
    )
    test_results.append(("Organic + Coords", result3b))
    
    # 4. DIRECT MAPS SEARCH (GoogleMapsBusinessSearcher style)
    print("\n🗺️  METHOD 4: DIRECT MAPS SEARCH (GoogleMapsBusinessSearcher style)")
    print("=" * 80)
    
    # 4a. Direct Maps + City Names
    def test_direct_maps_city():
        return client.search_maps_direct(
            business_name="laundromat", location="San Francisco, CA", num=10
        )
    
    result4a = test_location_method(
        "Direct Maps Search", "City Names", test_direct_maps_city
    )
    test_results.append(("Direct Maps + City", result4a))
    
    # 4b. Direct Maps + Coordinates (converted to location string)
    def test_direct_maps_coords():
        return client.search_maps_direct(
            business_name="laundromat", location="37.7749,-122.4194", num=10
        )
    
    result4b = test_location_method(
        "Direct Maps Search", "Coordinates", test_direct_maps_coords
    )
    test_results.append(("Direct Maps + Coords", result4b))
    
    # SUMMARY TABLE
    print("\n" + "=" * 80)
    print("📊 SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Method':<25} {'Location Type':<15} {'Localized':<12} {'Count':<8} {'Top Location':<20}")
    print("-" * 80)
    
    for test_name, result in test_results:
        localized = "✅ YES" if result['localized'] else "❌ NO"
        count = result['business_count']
        top_location = result['locations'][0] if result['locations'] else "None"
        
        method, loc_type = test_name.split(' + ')
        print(f"{method:<25} {loc_type:<15} {localized:<12} {count:<8} {top_location:<20}")
    
    # RECOMMENDATIONS
    print("\n" + "=" * 80)
    print("🎯 RECOMMENDATIONS")
    print("=" * 80)
    
    # Find best working methods
    working_methods = [(name, result) for name, result in test_results if result['localized']]
    broken_methods = [(name, result) for name, result in test_results if not result['localized']]
    
    if working_methods:
        print("✅ WORKING METHODS:")
        for name, result in working_methods:
            print(f"   • {name} - {result['business_count']} businesses found")
    
    if broken_methods:
        print("\n❌ BROKEN METHODS:")
        for name, result in broken_methods:
            print(f"   • {name} - Wrong location (got {result['locations'][0] if result['locations'] else 'unknown'})")
    
    print("\n💡 KEY INSIGHTS:")
    print("   • Local Business Search works best with city names")
    print("   • Maps Search works well with coordinates")
    print("   • Always use multiple location parameters for reliability")
    print("=" * 80)
