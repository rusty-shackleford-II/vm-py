import requests
import urllib.parse
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
