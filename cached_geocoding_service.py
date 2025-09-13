#!/usr/bin/env python3
"""
Cached Geocoding Service
========================

A geocoding service that uses the address_lat_lon table as a cache to avoid
repeated Google Maps API calls. Only hits the API when address is not cached.
"""

from typing import Optional, Tuple
from clients.supabase_client import SupabaseClient
from geocoding_service import get_coordinates as direct_get_coordinates


async def get_cached_coordinates(address: str) -> Optional[Tuple[float, float]]:
    """
    Get coordinates for an address, using database cache to avoid repeated API calls.
    
    Args:
        address: Full address string to geocode
        
    Returns:
        Tuple of (latitude, longitude) if successful, None if failed
    """
    if not address or not address.strip():
        return None
    
    address = address.strip()
    
    try:
        # Get Supabase client
        supabase_client = SupabaseClient()
        if not supabase_client.client:
            print("⚠️ Could not connect to Supabase, falling back to direct API call")
            return direct_get_coordinates(address)
        
        # Check cache first
        print(f"🔍 Checking cache for address: '{address}'")
        cache_result = (
            supabase_client.client.table("address_lat_lon")
            .select("lat, lon")
            .eq("address", address)
            .execute()
        )
        
        if cache_result.data and len(cache_result.data) > 0:
            # Cache hit!
            cached = cache_result.data[0]
            lat, lon = cached['lat'], cached['lon']
            print(f"🎯 Cache HIT: {address} -> ({lat}, {lon})")
            return lat, lon
        
        # Cache miss - hit the API
        print(f"❌ Cache MISS: {address} - fetching from Google Maps API")
        coords = direct_get_coordinates(address)
        
        if coords:
            lat, lon = coords
            print(f"✅ API Success: {address} -> ({lat}, {lon})")
            
            # Store in cache for future use
            try:
                cache_insert = (
                    supabase_client.client.table("address_lat_lon")
                    .insert({
                        "address": address,
                        "lat": lat,
                        "lon": lon,
                        "geocoding_source": "google_maps"
                    })
                    .execute()
                )
                print(f"💾 Cached result for: '{address}'")
            except Exception as cache_error:
                print(f"⚠️ Failed to cache result: {cache_error}")
                # Don't fail the whole operation if caching fails
            
            return lat, lon
        else:
            print(f"❌ API Failed: Could not geocode '{address}'")
            return None
            
    except Exception as e:
        print(f"⚠️ Error in cached geocoding: {e}")
        print(f"🔄 Falling back to direct API call")
        return direct_get_coordinates(address)


def get_cached_coordinates_sync(address: str) -> Optional[Tuple[float, float]]:
    """
    Synchronous version of get_cached_coordinates.
    Uses asyncio.run() to handle the async database operations.
    """
    import asyncio
    
    try:
        return asyncio.run(get_cached_coordinates(address))
    except Exception as e:
        print(f"⚠️ Error in sync cached geocoding: {e}")
        print(f"🔄 Falling back to direct API call")
        return direct_get_coordinates(address)


# For backward compatibility, provide the same interface as geocoding_service.py
def get_coordinates(address: str) -> Optional[Tuple[float, float]]:
    """
    Get coordinates for a full address string with caching.
    This replaces the direct API version from geocoding_service.py
    
    Args:
        address (str): The full address string
        
    Returns:
        Optional[Tuple[float, float]]: A tuple of (latitude, longitude) if successful, None if failed
    """
    return get_cached_coordinates_sync(address)


if __name__ == "__main__":
    # Test the cached geocoding service
    test_addresses = [
        "San Francisco, California, US",
        "Palo Alto, California, US", 
        "94102",  # Just zipcode
        "Nevada, US"  # Just state
    ]
    
    print("=" * 80)
    print("TESTING CACHED GEOCODING SERVICE")
    print("=" * 80)
    
    for address in test_addresses:
        print(f"\nTesting: '{address}'")
        coords = get_coordinates(address)
        if coords:
            lat, lon = coords
            print(f"Result: {lat}, {lon}")
        else:
            print("Result: Failed to geocode")
        print("-" * 40)
