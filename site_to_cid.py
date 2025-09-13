#!/usr/bin/env python3
"""
Site to CID Converter
====================

This module provides functionality to take business details, perform a Google Maps search
using BrightData, and return the CID for businesses that match the target domain.

Features:
- Caches results in database to avoid repeated API calls
- Returns cached results when available
- Stores both successful CID results and null results (when no CID found)

Dependencies:
- BrightData SDK for Maps search functionality
- Supabase for database caching

Author: Warren
"""

import asyncio
import json
from typing import Optional, Dict, Any
from urllib.parse import quote_plus, urlparse
from datetime import datetime
from brightdata import bdclient
from config import BRIGHTDATA_API_KEY
from clients.supabase_client import SupabaseClient


def normalize_domain(domain: str) -> str:
    """
    Normalize domain for comparison by removing protocol, www, and converting to lowercase
    
    Args:
        domain: Domain to normalize (can include https://, http://, www)
        
    Returns:
        Normalized domain string
    """
    domain = domain.strip().lower()
    
    # Remove protocol prefixes
    if domain.startswith("https://"):
        domain = domain[8:]
    elif domain.startswith("http://"):
        domain = domain[7:]
    
    # Remove www prefix
    if domain.startswith("www."):
        domain = domain[4:]
    
    # Remove trailing slash if present
    if domain.endswith("/"):
        domain = domain[:-1]
    
    return domain


def extract_domain_from_url(url: str) -> Optional[str]:
    """
    Extract domain from URL
    
    Args:
        url: URL to extract domain from
        
    Returns:
        Domain string or None if extraction fails
    """
    try:
        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
        
        parsed = urlparse(url)
        domain = parsed.hostname
        if domain:
            return normalize_domain(domain)
        return None
    except Exception as e:
        return None


def url_matches_domain(url: str, target_domain: str) -> bool:
    """
    Check if URL matches target domain (including subdomains)
    
    Args:
        url: URL to check
        target_domain: Target domain to match against
        
    Returns:
        True if URL matches target domain
    """
    url_domain = extract_domain_from_url(url)
    if not url_domain:
        return False
    
    target = normalize_domain(target_domain)
    return url_domain == target or url_domain.endswith("." + target)


def convert_fid_to_cid(fid: str) -> Optional[str]:
    """
    Convert FID (Feature ID) to CID (Customer ID)
    
    Args:
        fid: Feature ID like "0x808f7fac8617a5c9:0x507db88f060b2567"
        
    Returns:
        CID as decimal string or None if conversion fails
    """
    try:
        # FID format is typically "0x<hex1>:0x<hex2>"
        # The CID is the second hex value converted to decimal
        if ':' in fid:
            parts = fid.split(':')
            if len(parts) == 2:
                hex_cid = parts[1]
                if hex_cid.startswith('0x'):
                    hex_cid = hex_cid[2:]
                
                # Convert hex to decimal
                cid = str(int(hex_cid, 16))
                return cid
        
        return None
    except Exception as e:
        return None


def normalize_cache_key(business_name: str, city: str, region: str, country: str, domain: str) -> Dict[str, str]:
    """
    Normalize parameters for cache key lookup
    
    Args:
        business_name: Name of the business
        city: City where business is located
        region: State/region
        country: Country code
        domain: Business domain (can include https://, http://, www)
        
    Returns:
        Dictionary with normalized values for cache lookup
    """
    return {
        'business_name': business_name.strip().lower(),
        'city': city.strip().lower(),
        'region': region.strip().lower(),
        'country': country.strip().lower(),
        'domain': normalize_domain(domain)  # Use proper domain normalization
    }


async def get_cached_cid(
    business_name: str,
    city: str, 
    region: str,
    country: str,
    domain: str,
    supabase_client: SupabaseClient
) -> Optional[Dict[str, Any]]:
    """
    Check cache for existing CID result
    
    Args:
        business_name: Name of the business
        city: City where business is located
        region: State/region
        country: Country code
        domain: Business domain
        supabase_client: Initialized Supabase client
        
    Returns:
        Cache record if found, None otherwise
    """
    try:
        normalized = normalize_cache_key(business_name, city, region, country, domain)
        
        result = (
            supabase_client.client.table("site_to_cid_cache")
            .select("*")
            .eq("business_name", normalized['business_name'])
            .eq("city", normalized['city'])
            .eq("region", normalized['region'])
            .eq("country", normalized['country'])
            .eq("domain", normalized['domain'])
            .execute()
        )
        
        if result.data and len(result.data) > 0:
            cache_record = result.data[0]
            return cache_record
        
        return None
        
    except Exception as e:
        return None


async def store_cid_result(
    business_name: str,
    city: str, 
    region: str,
    country: str,
    domain: str,
    cid: Optional[str],
    supabase_client: SupabaseClient,
    raw_response: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None
) -> bool:
    """
    Store CID result in cache
    
    Args:
        business_name: Name of the business
        city: City where business is located
        region: State/region
        country: Country code
        domain: Business domain
        cid: The CID result (can be None)
        supabase_client: Initialized Supabase client
        raw_response: Optional raw API response for debugging
        error_message: Optional error message if API call failed
        
    Returns:
        True if storage successful, False otherwise
    """
    try:
        normalized = normalize_cache_key(business_name, city, region, country, domain)
        
        record = {
            'business_name': normalized['business_name'],
            'city': normalized['city'],
            'region': normalized['region'],
            'country': normalized['country'],
            'domain': normalized['domain'],
            'cid': cid,
            'lookup_successful': error_message is None,  # True if no error occurred
            'raw_response': raw_response,
            'error_message': error_message
        }
        
        # Use upsert to handle potential duplicates
        result = (
            supabase_client.client.table("site_to_cid_cache")
            .upsert(record)
            .execute()
        )
        
        return True
        
    except Exception as e:
        return False


async def site_to_cid_with_brightdata(
    business_name: str,
    city: str, 
    region: str,
    country: str,
    domain: str
) -> tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """
    Perform BrightData Maps search and return CID for domain match.
    This is the core search logic without caching.
    
    Args:
        business_name: Name of the business (e.g., "Thatcher's Popcorn")
        city: City where business is located (e.g., "San Francisco")
        region: State/region (e.g., "California") 
        country: Country code (e.g., "US")
        domain: Normalized business domain to match (e.g., "thatcherspopcorn.com")
               Should already be normalized (no https://, www, etc.)
        
    Returns:
        Tuple of (CID, raw_response, error_message)
    """
    try:
        # Initialize BrightData client
        client = bdclient(api_token=BRIGHTDATA_API_KEY)
        
        # Construct search query and location
        query = f"{business_name} in {city}, {region}, {country}".strip()
        search_query = quote_plus(query)
        
        # Build Google Maps search URL with BrightData JSON parsing
        url = f"https://www.google.com/maps/search/{search_query}/?brd_json=1"
        
        # Fetch data via BrightData
        results = client.scrape(url)
        parsed_json = client.parse_content(results)
        
        # Check if we have the expected structure
        if not parsed_json or 'text' not in parsed_json:
            error_msg = "No 'text' field in BrightData result"
            return None, parsed_json, error_msg
        
        # Parse the JSON string in the text field
        maps_data = json.loads(parsed_json['text'])
        
        # Check for organic results
        if 'organic' not in maps_data or not maps_data['organic']:
            error_msg = "No organic results found in Maps data"
            return None, maps_data, None  # Not an error, just no results
        
        organic_results = maps_data['organic']
        
        # Iterate through all results looking for domain match
        for i, business in enumerate(organic_results):
            business_name_result = business.get('title', 'N/A')
            link = business.get('link', '')
            display_link = business.get('display_link', '')
            
            # Check if either link or display_link matches target domain
            link_matches = url_matches_domain(link, domain) if link else False
            display_matches = url_matches_domain(display_link, domain) if display_link else False
            
            if link_matches or display_matches:
                
                # Extract FID
                fid = business.get('fid') or business.get('map_id')
                if not fid:
                    continue
                
                # Convert FID to CID
                cid = convert_fid_to_cid(fid)
                if cid:
                    return cid, maps_data, None
                else:
                    continue
        
        return None, maps_data, None  # Not an error, just no domain match
        
    except json.JSONDecodeError as e:
        error_msg = f"Failed to parse JSON from BrightData text: {e}"
        return None, None, error_msg
    except Exception as e:
        error_msg = f"Error in BrightData search: {e}"
        return None, None, error_msg


async def site_to_cid(
    business_name: str,
    city: str, 
    region: str,
    country: str,
    domain: str
) -> Optional[str]:
    """
    Take business details, perform a Maps search, and return CID for domain match.
    Uses database caching to avoid repeated API calls.
    
    Args:
        business_name: Name of the business (e.g., "Thatcher's Popcorn")
        city: City where business is located (e.g., "San Francisco")
        region: State/region (e.g., "California") 
        country: Country code (e.g., "US")
        domain: Business domain to match (e.g., "thatcherspopcorn.com", "https://www.example.com")
        
    Returns:
        Google Maps CID (Customer ID) as string, or None if no domain match found
    """
    # Normalize the domain to remove https://, www, etc.
    normalized_domain = normalize_domain(domain)
    
    try:
        # Initialize Supabase client for cache operations
        supabase_client = SupabaseClient()
        
        # Check cache first (using normalized domain)
        cached_result = await get_cached_cid(
            business_name, city, region, country, normalized_domain, supabase_client
        )
        
        if cached_result:
            # Return cached result
            cached_cid = cached_result.get('cid')
            return cached_cid
        
        # Cache miss - perform BrightData search (using normalized domain)
        cid, raw_response, error_message = await site_to_cid_with_brightdata(
            business_name, city, region, country, normalized_domain
        )
        
        # Store result in cache (using normalized domain)
        await store_cid_result(
            business_name, city, region, country, normalized_domain, 
            cid, supabase_client, raw_response, error_message
        )
        
        return cid
        
    except Exception as e:
        return None


# Convenience function for synchronous usage
def site_to_cid_sync(
    business_name: str,
    city: str, 
    region: str,
    country: str,
    domain: str
) -> Optional[str]:
    """
    Synchronous wrapper for site_to_cid function.
    
    Args:
        business_name: Name of the business
        city: City where business is located
        region: State/region
        country: Country code
        domain: Business domain to match (can include https://, www, etc.)
        
    Returns:
        Google Maps CID as string, or None if no domain match found
    """
    return asyncio.run(site_to_cid(business_name, city, region, country, domain))


# Example usage and testing
async def main():
    """Test the site_to_cid function with Thatcher's Popcorn example"""
    print("🧪 Testing site_to_cid function with caching")
    print("=" * 50)
    
    # Test case: Thatcher's Popcorn
    print("🔍 First call (should hit BrightData API):")
    cid1 = await site_to_cid(
        business_name="Thatcher's Popcorn",
        city="San Angelo",
        region="Texas", 
        country="US",
        domain="thatcherspopcorn.com"
    )
    
    if cid1:
        print(f"\n🎉 SUCCESS! First call CID: {cid1}")
    else:
        print(f"\n❌ FAILED! No matching domain found on first call")
    
    print("\n" + "=" * 50)
    print("🔍 Second call (should hit cache):")
    
    # Second call - should hit cache
    cid2 = await site_to_cid(
        business_name="Thatcher's Popcorn",
        city="San Angelo",
        region="Texas", 
        country="US",
        domain="thatcherspopcorn.com"
    )
    
    if cid2:
        print(f"\n🎉 SUCCESS! Second call CID: {cid2}")
        print(f"   Cache working: {cid1 == cid2}")
    else:
        print(f"\n❌ FAILED! No matching domain found on second call")
    
    print("\n" + "=" * 50)
    print("🔍 Third call with https:// and www (should normalize and hit cache):")
    
    # Third call with https:// and www - should normalize and hit cache
    cid3 = await site_to_cid(
        business_name="Thatcher's Popcorn",
        city="San Angelo",
        region="Texas", 
        country="US",
        domain="https://www.thatcherspopcorn.com/"
    )
    
    if cid3:
        print(f"\n🎉 SUCCESS! Third call CID: {cid3}")
        print(f"   Domain normalization working: {cid1 == cid3}")
    else:
        print(f"\n❌ FAILED! No matching domain found on third call")
    
    print("\n🎉 Testing complete!")


if __name__ == "__main__":
    asyncio.run(main())
