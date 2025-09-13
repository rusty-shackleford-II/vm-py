import requests
import urllib.parse
import json
from typing import Optional, Tuple
from pprint import pprint
from config import GOOGLE_MAPS_API_KEY


def get_lat_long(city: str, state_or_province: str, country: str) -> Optional[Tuple[float, float]]:
    """
    Convert a combination of city, state/province, and country into latitude and longitude coordinates
    using the Google Geocoding API.
    
    Args:
        city (str): The city name
        state_or_province (str): The state or province name
        country (str): The country name
        
    Returns:
        Optional[Tuple[float, float]]: A tuple of (latitude, longitude) if successful, None if failed
        
    Example:
        >>> lat, lng = get_lat_long('New York', 'NY', 'USA')
        >>> print(f"Latitude: {lat}, Longitude: {lng}")
    """
    try:
        # Construct the address string
        address = f"{city}, {state_or_province}, {country}"
        encoded_address = urllib.parse.quote(address)
        
        # Define the endpoint
        endpoint = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={GOOGLE_MAPS_API_KEY}"
        
        # Make the request
        response = requests.get(endpoint, timeout=10)
        
        # Check if the request was successful
        if response.status_code != 200:
            print(f"HTTP Error: {response.status_code}")
            return None
            
        # Parse the response
        result = response.json()
        
        # Check if the geocoding was successful
        if result['status'] != 'OK':
            print(f"Geocoding API Error: {result['status']}")
            if 'error_message' in result:
                print(f"Error message: {result['error_message']}")
            return None
            
        # Check if we have results
        if not result['results']:
            print("No results found for the given address")
            return None
            
        # Extract latitude and longitude from the first result
        location = result['results'][0]['geometry']['location']
        latitude = location['lat']
        longitude = location['lng']
        
        return latitude, longitude
        
    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")
        return None
    except KeyError as e:
        print(f"Unexpected response format: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


def get_detailed_geocoding_info(city: str, state_or_province: str, country: str) -> Optional[dict]:
    """
    Get detailed geocoding information including formatted address, place ID, and other metadata.
    
    Args:
        city (str): The city name
        state_or_province (str): The state or province name
        country (str): The country name
        
    Returns:
        Optional[dict]: Complete geocoding result if successful, None if failed
    """
    try:
        # Construct the address string
        address = f"{city}, {state_or_province}, {country}"
        encoded_address = urllib.parse.quote(address)
        
        # Define the endpoint
        endpoint = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={GOOGLE_MAPS_API_KEY}"
        
        # Make the request
        response = requests.get(endpoint, timeout=10)
        
        # Check if the request was successful
        if response.status_code != 200:
            print(f"HTTP Error: {response.status_code}")
            return None
            
        # Parse the response
        result = response.json()
        
        # Check if the geocoding was successful
        if result['status'] != 'OK':
            print(f"Geocoding API Error: {result['status']}")
            if 'error_message' in result:
                print(f"Error message: {result['error_message']}")
            return None
            
        # Check if we have results
        if not result['results']:
            print("No results found for the given address")
            return None
            
        return result['results'][0]
        
    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


def get_complete_geocoding_info(address: str) -> Optional[dict]:
    """
    Get complete geocoding information for a full address string.
    
    Args:
        address (str): The full address string
        
    Returns:
        Optional[dict]: Complete geocoding response if successful, None if failed
    """
    try:
        encoded_address = urllib.parse.quote(address)
        
        # Define the endpoint
        endpoint = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={GOOGLE_MAPS_API_KEY}"
        
        # Make the request
        response = requests.get(endpoint, timeout=10)
        
        # Check if the request was successful
        if response.status_code != 200:
            print(f"HTTP Error: {response.status_code}")
            return None
            
        # Parse the response
        result = response.json()
        
        # Check if the geocoding was successful
        if result['status'] != 'OK':
            print(f"Geocoding API Error: {result['status']}")
            if 'error_message' in result:
                print(f"Error message: {result['error_message']}")
            return None
            
        # Check if we have results
        if not result['results']:
            print("No results found for the given address")
            return None
            
        return result
        
    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


# Alias for backward compatibility with app.py
def get_coordinates(address: str) -> Optional[Tuple[float, float]]:
    """
    Get coordinates for a full address string.
    This is an alias function for compatibility with app.py imports.
    
    Args:
        address (str): The full address string
        
    Returns:
        Optional[Tuple[float, float]]: A tuple of (latitude, longitude) if successful, None if failed
    """
    result = get_complete_geocoding_info(address)
    if result and result.get('results'):
        location = result['results'][0]['geometry']['location']
        return location['lat'], location['lng']
    return None


def coords_to_address(lat: float, lng: float) -> Optional[dict]:
    """
    Convert coordinates to address using Google Maps Reverse Geocoding API
    
    Args:
        lat (float): Latitude
        lng (float): Longitude
    
    Returns:
        Optional[dict]: Full reverse geocoding response from Google Maps API if successful, None if failed
    """
    try:
        # Define the endpoint for reverse geocoding
        endpoint = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lng}&key={GOOGLE_MAPS_API_KEY}"
        
        # Make the request
        response = requests.get(endpoint, timeout=15)
        
        # Check if the request was successful
        if response.status_code != 200:
            print(f"HTTP Error: {response.status_code}")
            return None
            
        # Parse the response
        result = response.json()
        
        # Check if the reverse geocoding was successful
        if result['status'] != 'OK':
            print(f"Reverse Geocoding API Error: {result['status']}")
            if 'error_message' in result:
                print(f"Error message: {result['error_message']}")
            return None
            
        return result
        
    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


def pretty_print_geocoding_result(data: dict):
    """Pretty print reverse geocoding result in a readable format"""
    
    # Print top-level status and plus_code
    print("Status:", data.get("status"))
    if "plus_code" in data:
        print("Plus code:", json.dumps(data["plus_code"], indent=2, ensure_ascii=False))

    # Print first result summary (if any)
    results = data.get("results", [])
    if not results:
        print("No results.")
        return

    first = results[0]
    print("\nFirst result formatted_address:")
    print(first.get("formatted_address"))

    print("\nFirst result place_id:", first.get("place_id"))
    print("\nFirst result types:", first.get("types"))

    # Geometry block
    geom = first.get("geometry", {})
    print("\nGeometry.location:", geom.get("location"))
    print("Geometry.location_type:", geom.get("location_type"))
    print("Geometry.viewport:", geom.get("viewport"))

    # Address components (city/region/country)
    print("\nAddress components (long_name / types):")
    for comp in first.get("address_components", []):
        print(f"- {comp.get('long_name')} | short={comp.get('short_name')} | types={comp.get('types')}")

    # Pretty-print the raw JSON to inspect full structure
    print("\nRaw JSON (truncated to first result only):")
    out = {"status": data.get("status"), "plus_code": data.get("plus_code"), "result_0": first}
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    # Test with specific address: 850 Jones St, San Francisco, CA 94109, United States
    address = "850 Jones St, San Francisco, CA 94109, United States"
    print(f"Getting complete geocoding info for: {address}")
    print("="*80)
    
    complete_info = get_complete_geocoding_info(address)
    if complete_info:
        print("Complete geocoding information:")
        pprint(complete_info)
    else:
        print("Failed to get geocoding information")
    
    print("\n" + "="*80)
    
    # Test reverse geocoding with San Francisco coordinates (Golden Gate Bridge area)
    sf_lat = 37.8199
    sf_lng = -122.4783
    print(f"Testing reverse geocoding for San Francisco coordinates: {sf_lat}, {sf_lng}")
    print("="*80)
    
    reverse_result = coords_to_address(sf_lat, sf_lng)
    if reverse_result:
        pretty_print_geocoding_result(reverse_result)
    else:
        print("Failed to get reverse geocoding information")
