#!/usr/bin/env python3
"""
San Francisco Pizza Search Test - City-based UULE
==================================================

Test script that:
1. Uses canonical city format (San Francisco, California, United States)
2. Encodes to UULE format using simple comma-separated string
3. Performs a localized search for "pizza" using Bright Data

This demonstrates the city-based UULE approach for localized search results.
"""

import json
import urllib.parse
from typing import Optional, Dict, Any
from brightdata import bdclient
from config import BRIGHTDATA_API_KEY
import uule_grabber
import base64
import time


def to_e7(decimal_degrees: float) -> int:
    """
    Convert decimal degrees to E7 format (degrees * 10^7).
    Google uses E7 format for latitude/longitude in UULE encoding.
    
    Args:
        decimal_degrees: Coordinate in decimal degrees
        
    Returns:
        Coordinate in E7 format (integer)
    """
    return int(decimal_degrees * 10_000_000)


def localized_search_with_brightdata(query: str, uule: str, location_name: str, num: int = 100) -> Optional[Dict[str, Any]]:
    """
    Search for pizza using Bright Data with city-based UULE localization.
    
    Args:
        query: Search query (e.g., "pizza")
        uule: UULE encoded location string (city,region,country format)
        location_name: Human-readable location name for display
        
    Returns:
        Raw JSON response from Bright Data or None if error
    """
    print(f"🔍 Bright Data Localized Search")
    print(f"   Query: {query}")
    print(f"   Location: {location_name}")
    print(f"   UULE: {uule}")
    
    try:
        # Initialize Bright Data client
        client = bdclient(api_token=BRIGHTDATA_API_KEY)
        print("✅ Bright Data client initialized")
        
        # Build Google search URL with city-based UULE localization
        base_url = "https://www.google.com/search"
        params = {
            "q": query,
            "hl": "en",           # Interface language
            "gl": "us",           # Results country bias  
            "num": num,            # Number of results
            "uule": uule,         # City-based location encoding
            "brd_json": 1         # Bright Data JSON parsing
        }
        
        # Construct URL
        param_string = urllib.parse.urlencode(params)
        search_url = f"{base_url}?{param_string}"
        
        print(f"🌐 Search URL: {search_url}")
        print(f"🔍 Searching...")
        
        # Fetch data via Bright Data
        results = client.scrape(search_url)
        
        # Parse the content to get actual SERP JSON
        parsed_json = client.parse_content(results)
        
        if parsed_json:
            print("✅ Search completed successfully")
            return parsed_json
        else:
            print("❌ No results returned from Bright Data")
            return None
            
    except Exception as e:
        print(f"❌ Error in Bright Data search: {e}")
        return None


def analyze_search_results(results: Dict[str, Any]) -> None:
    """
    Analyze and display the search results from Bright Data.
    
    Args:
        results: Parsed JSON response from Bright Data
    """
    print(f"\n📊 SEARCH RESULTS ANALYSIS")
    print(f"=" * 50)
    
    if not results:
        print("❌ No results to analyze")
        return
    
    # Check if we have the expected structure
    if 'text' not in results:
        print("❌ No 'text' field in results")
        print(f"Available keys: {list(results.keys())}")
        return
    
    try:
        # Parse the JSON string in the text field
        search_data = json.loads(results['text'])
        
        # Display overall stats
        print(f"🔍 Search performed successfully")
        
        # Check for organic results
        if 'organic' in search_data and search_data['organic']:
            organic_results = search_data['organic']
            print(f"📋 Found {len(organic_results)} organic results")
            
            print(f"\n🍕 ALL ORGANIC PIZZA RESULTS:")
            print(f"=" * 80)
            
            for i, result in enumerate(organic_results, 1):  # Show all results
                title = result.get('title', 'No title')
                url = result.get('url', 'No URL')
                snippet = result.get('snippet', result.get('description', 'No description'))
                
                print(f"\n{i}. {title}")
                print(f"   🌐 URL: {url}")
                print(f"   📝 Snippet: {snippet}")
                
                # Show additional fields if available
                if 'displayed_url' in result:
                    print(f"   📍 Display URL: {result['displayed_url']}")
                if 'position' in result:
                    print(f"   📊 Position: {result['position']}")
                
            print(f"\n" + "=" * 80)
        else:
            print("❌ No organic results found")
        
        # Check for local results in multiple possible locations
        local_results = []
        
        # Check traditional 'local' field
        if 'local' in search_data and search_data['local']:
            local_results.extend(search_data['local'])
            
        # Check 'snack_pack' field (common for local business results)
        if 'snack_pack' in search_data and search_data['snack_pack']:
            snack_pack = search_data['snack_pack']
            if isinstance(snack_pack, list):
                local_results.extend(snack_pack)
            elif isinstance(snack_pack, dict) and 'results' in snack_pack:
                local_results.extend(snack_pack['results'])
        
        if local_results:
            print(f"📍 Found {len(local_results)} local business results")
            
            print(f"\n🏪 TOP LOCAL PIZZA PLACES:")
            print(f"-" * 35)
            
            for i, result in enumerate(local_results[:5], 1):  # Show top 5
                title = result.get('title', result.get('name', 'No title'))
                address = result.get('address', result.get('location', 'No address'))
                rating = result.get('rating', result.get('stars', 'No rating'))
                phone = result.get('phone', '')
                hours = result.get('hours', result.get('open_hours', ''))
                
                print(f"{i}. {title}")
                print(f"   📍 {address}")
                if rating != 'No rating':
                    print(f"   ⭐ {rating}")
                if phone:
                    print(f"   📞 {phone}")
                if hours:
                    print(f"   🕐 {hours}")
                print()
        else:
            print("❌ No local business results found")
            
        # Display raw result structure for debugging
        print(f"\n🔧 DEBUG INFO:")
        print(f"Available result types: {list(search_data.keys())}")
        
        # Show snack_pack structure if available
        if 'snack_pack' in search_data:
            snack_pack = search_data['snack_pack']
            print(f"Snack pack type: {type(snack_pack)}")
            if isinstance(snack_pack, dict):
                print(f"Snack pack keys: {list(snack_pack.keys())}")
                if 'results' in snack_pack:
                    results = snack_pack['results']
                    print(f"Snack pack results count: {len(results) if isinstance(results, list) else 'not a list'}")
                    if isinstance(results, list) and results:
                        print(f"First result keys: {list(results[0].keys()) if isinstance(results[0], dict) else 'not a dict'}")
            elif isinstance(snack_pack, list):
                print(f"Snack pack list length: {len(snack_pack)}")
                if snack_pack and isinstance(snack_pack[0], dict):
                    print(f"First snack pack item keys: {list(snack_pack[0].keys())}")
        
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse search results JSON: {e}")
        print(f"Raw text preview: {results['text'][:200]}...")


def uule_from_canonical_city_simple(city: str, region: str, country: str) -> str:
    """
    Simple city-level UULE using comma-separated format (our current method).
    This approach works well for localization with Bright Data.
    
    Args:
        city: City name (e.g., "San Francisco")
        region: State/region (e.g., "California")
        country: Country name (e.g., "United States")
        
    Returns:
        Comma-separated location string for UULE parameter
    """
    return f"{city},{region},{country}"


def uule_from_canonical_city_proper(city: str, region: str, country: str) -> str:
    """
    Proper city-level UULE using uule_grabber (from loc_to_uule.py method).
    This uses the proper Google UULE encoding format.
    
    Args:
        city: City name (e.g., "San Francisco")
        region: State/region (e.g., "California")
        country: Country name (e.g., "United States")
        
    Returns:
        Properly encoded UULE string (e.g., "w+CAIQICI...")
    """
    canonical_location = f"{city},{region},{country}"
    return uule_grabber.uule(canonical_location)


def build_uule_a_plus(lat: float, lon: float, radius_m: int = 6000) -> str:
    """
    Build an 'a+' (cookie-style) UULE carrying lat/lon and radius.
    
    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        radius_m: Search radius in meters; use -1 for exact point.
        
    Returns:
        Properly encoded a+ UULE string for precise geographic targeting
    """
    lat_e7 = to_e7(lat)
    lon_e7 = to_e7(lon)
    # Google uses microseconds since epoch in the cookie payload
    ts_micro = int(time.time() * 1_000_000)

    # Exact ASCII layout observed in decoded UULE cookies
    payload = (
        f"role:1 "
        f"producer:12 "
        f"provenance:6 "
        f"timestamp:{ts_micro} "
        f"latlng{{ latitude_e7:{lat_e7} longitude_e7:{lon_e7} }} "
        f"radius:{radius_m}"
    )

    b64 = base64.b64encode(payload.encode("ascii")).decode("ascii")
    return "a+" + b64


def test_no_uule(query: str, location_name: str) -> Optional[Dict[str, Any]]:
    """Test search with no UULE parameter at all."""
    print(f"🔍 Bright Data Search (No UULE)")
    print(f"   Query: {query}")
    print(f"   Location: {location_name}")
    print(f"   UULE: None")
    
    try:
        client = bdclient(api_token=BRIGHTDATA_API_KEY)
        print("✅ Bright Data client initialized")
        
        base_url = "https://www.google.com/search"
        params = {
            "q": query,
            "hl": "en",
            "gl": "us",
            "num": 20,
            "brd_json": 1
        }
        
        param_string = urllib.parse.urlencode(params)
        search_url = f"{base_url}?{param_string}"
        
        print(f"🌐 Search URL: {search_url}")
        print(f"🔍 Searching...")
        
        results = client.scrape(search_url)
        parsed_json = client.parse_content(results)
        
        if parsed_json:
            print("✅ Search completed successfully")
            return parsed_json
        else:
            print("❌ No results returned from Bright Data")
            return None
            
    except Exception as e:
        print(f"❌ Error in Bright Data search: {e}")
        return None


def main():
    """
    Extended comparison test of different UULE formats and their effect on result counts.
    Tests multiple variations to understand Google's UULE parameter behavior.
    """
    print("🧪 Localized Search Test - UULE From Lat/Lon Coordinates")
    print("=" * 80)
    
    # San Mateo location details
    query = "barbershop"
    city = "San Mateo"
    region = "California" 
    country = "United States"
    location_name = f"{city}, {region}, {country}"
    
    # San Mateo, CA coordinates
    lat = 37.5629
    lon = -122.3255
    
    print(f"📍 Target location:")
    print(f"   City: {city}")
    print(f"   Region: {region}")
    print(f"   Country: {country}")
    print(f"   Coordinates: {lat}, {lon}")
    
    # Store results for comparison
    test_results = {}
    
    # Test 1: New a+ UULE using pyuule with lat/lon coordinates
    print(f"\n" + "="*80)
    print(f"🧪 TEST 1: a+ UULE using pyuule with lat/lon")
    print(f"="*80)
    
    print(f"\n🔐 Creating a+ UULE with coordinates...")
    a_plus_uule = build_uule_a_plus(lat, lon, radius_m=6000)
    print(f"✅ a+ UULE: {a_plus_uule}")
    
    print(f"\n🔍 Performing localized search...")
    a_plus_results = localized_search_with_brightdata(query, a_plus_uule, f"{location_name} (a+ UULE)", num=100)
    
    print(f"\n📊 Analyzing a+ UULE results...")
    analyze_search_results(a_plus_results)
    test_results['a_plus'] = a_plus_results
    
    # Test 2: Proper UULE using uule_grabber for comparison
    print(f"\n" + "="*80)
    print(f"🧪 TEST 2: Proper UULE using uule_grabber")
    print(f"="*80)
    
    print(f"\n🔐 Creating proper UULE...")
    proper_uule = uule_from_canonical_city_proper(city, region, country)
    print(f"✅ Proper UULE: {proper_uule}")
    
    print(f"\n🔍 Performing localized search...")
    proper_results = localized_search_with_brightdata(query, proper_uule, f"{location_name} (Proper)", num=100)
    
    print(f"\n📊 Analyzing proper UULE results...")
    analyze_search_results(proper_results)
    test_results['proper'] = proper_results
    
    # Summary comparison between a+ and proper UULE
    print(f"\n" + "="*80)
    print(f"📊 UULE METHOD COMPARISON SUMMARY")
    print(f"="*80)
    
    # Count results for both tests
    result_counts = {}
    local_counts = {}
    
    for test_name, results in test_results.items():
        organic_count = 0
        local_count = 0
        if results and 'text' in results:
            try:
                data = json.loads(results['text'])
                if 'organic' in data and data['organic']:
                    organic_count = len(data['organic'])
                
                # Count local results
                if 'local' in data and data['local']:
                    local_count += len(data['local'])
                if 'snack_pack' in data and data['snack_pack']:
                    snack_pack = data['snack_pack']
                    if isinstance(snack_pack, list):
                        local_count += len(snack_pack)
                    elif isinstance(snack_pack, dict) and 'results' in snack_pack:
                        local_count += len(snack_pack['results'])
            except:
                pass
        result_counts[test_name] = organic_count
        local_counts[test_name] = local_count
    
    print(f"📊 RESULT COUNT COMPARISON:")
    print(f"   a+ UULE (lat/lon): {result_counts.get('a_plus', 0):2d} organic results, {local_counts.get('a_plus', 0):2d} local results")
    print(f"   Proper UULE:       {result_counts.get('proper', 0):2d} organic results, {local_counts.get('proper', 0):2d} local results")
    print(f"")
    
    print(f"🔸 UULE Format Comparison:")
    print(f"   a+ UULE:    '{a_plus_uule[:50]}...' (lat/lon based)")
    print(f"   Proper UULE: '{proper_uule}' (city name based)")
    print(f"")
    
    print(f"🔍 KEY INSIGHTS:")
    a_plus_total = result_counts.get('a_plus', 0) + local_counts.get('a_plus', 0)
    proper_total = result_counts.get('proper', 0) + local_counts.get('proper', 0)
    
    if a_plus_total > proper_total:
        print(f"   ✅ a+ UULE (lat/lon) yields more total results: {a_plus_total} vs {proper_total}")
        print(f"   💡 Precise coordinates provide better localization than city names")
    elif proper_total > a_plus_total:
        print(f"   ✅ Proper UULE (city name) yields more total results: {proper_total} vs {a_plus_total}")
        print(f"   💡 City-based targeting may be more effective for this query")
    else:
        print(f"   🤔 Both methods yield similar result counts: {a_plus_total}")
        print(f"   💡 Difference may be in result quality rather than quantity")
    
    print(f"")
    print(f"🎯 CONCLUSION:")
    if a_plus_total >= proper_total:
        print(f"   a+ UULE with precise lat/lon coordinates is optimal")
        print(f"   - Total results: {a_plus_total} ({result_counts.get('a_plus', 0)} organic + {local_counts.get('a_plus', 0)} local)")
        print(f"   - Provides precise geographic targeting with 6km radius")
    else:
        print(f"   Traditional proper UULE performs better for this case")
        print(f"   - Total results: {proper_total} ({result_counts.get('proper', 0)} organic + {local_counts.get('proper', 0)} local)")
    
    print(f"="*80)
    
    print(f"\n✅ Both UULE tests completed!")


if __name__ == "__main__":
    main()
