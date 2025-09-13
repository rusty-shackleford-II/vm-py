#!/usr/bin/env python3
"""
Simple BrightData Maps Search
============================

A minimal inline script that uses the BrightData SDK directly to search Google Maps
and return raw JSON results.

Usage:
    python simple_maps_search.py
"""

import json
from urllib.parse import quote_plus
from typing import Optional
from brightdata import bdclient
from config import BRIGHTDATA_API_KEY


def search_maps_with_brightdata(business_name: str, city: str, region: str, country: str, domain: str):
    """
    Search Google Maps using BrightData SDK directly
    
    Args:
        business_name: Name of the business (e.g., "Thatcher's Popcorn")
        city: City where business is located (e.g., "San Francisco")
        region: State/region (e.g., "California") 
        country: Country code (e.g., "US")
        domain: Business domain (e.g., "thatcherspopcorn.com")
        
    Returns:
        Raw JSON response from BrightData
    """
    print(f"🔍 BrightData Maps Search")
    print(f"   Business: {business_name}")
    print(f"   Location: {city}, {region}, {country}")
    print(f"   Domain: {domain}")
    
    try:
        # Initialize BrightData client
        client = bdclient(api_token=BRIGHTDATA_API_KEY)
        print("✅ BrightData client initialized")
        
        # Construct search query and location
        query = f"{business_name} {city}, {region}, {country}".strip()
        search_query = quote_plus(query)
        
        # Build Google Maps search URL with BrightData JSON parsing
        url = f"https://www.google.com/maps/search/{search_query}/?brd_json=1"
        
        print(f"🌐 Search URL: {url}")
        print(f"🔍 Searching...")
        
        # Fetch data via BrightData
        results = client.scrape(url)
        
        # Parse the content to get actual SERP JSON
        parsed_json = client.parse_content(results)
        
        return parsed_json
        
    except Exception as e:
        print(f"❌ Error in BrightData Maps search: {e}")
        return None


def main():
    """Test the BrightData Maps search with Thatcher's Popcorn example"""
    print("🧪 Testing BrightData Maps Search")
    print("=" * 50)
    
    # Test case: Thatcher's Popcorn
    result = search_maps_with_brightdata(
        business_name="Thatcher's Popcorn",
        city="San Francisco",
        region="California", 
        country="US",
        domain="thatcherspopcorn.com"
    )


if __name__ == "__main__":
    main()
