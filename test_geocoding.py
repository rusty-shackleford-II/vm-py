#!/usr/bin/env python3
"""
Test script for the geocoding service.
"""

from geocoding_service import get_lat_long, get_detailed_geocoding_info


def test_basic_geocoding():
    """Test basic geocoding functionality."""
    print("Testing basic geocoding...")
    
    # Test a well-known location
    result = get_lat_long("San Francisco", "CA", "USA")
    
    if result:
        lat, lng = result
        print(f"✓ San Francisco, CA, USA: {lat}, {lng}")
        
        # Verify the coordinates are roughly correct for San Francisco
        # San Francisco is approximately at 37.7749° N, 122.4194° W
        if 37.7 <= lat <= 37.8 and -122.5 <= lng <= -122.4:
            print("✓ Coordinates are in the expected range for San Francisco")
        else:
            print(f"⚠ Coordinates seem unusual for San Francisco: {lat}, {lng}")
    else:
        print("✗ Failed to geocode San Francisco")
        return False
    
    return True


def test_international_locations():
    """Test geocoding for international locations."""
    print("\nTesting international locations...")
    
    test_cases = [
        ("London", "England", "UK"),
        ("Tokyo", "Tokyo", "Japan"),
        ("Paris", "Ile-de-France", "France"),
        ("Sydney", "NSW", "Australia")
    ]
    
    success_count = 0
    for city, state, country in test_cases:
        result = get_lat_long(city, state, country)
        if result:
            lat, lng = result
            print(f"✓ {city}, {state}, {country}: {lat}, {lng}")
            success_count += 1
        else:
            print(f"✗ Failed to geocode {city}, {state}, {country}")
    
    print(f"\nInternational test results: {success_count}/{len(test_cases)} successful")
    return success_count == len(test_cases)


def test_detailed_info():
    """Test detailed geocoding information."""
    print("\nTesting detailed geocoding info...")
    
    result = get_detailed_geocoding_info("New York", "NY", "USA")
    
    if result:
        print(f"✓ Formatted Address: {result.get('formatted_address')}")
        print(f"✓ Place ID: {result.get('place_id')}")
        
        location = result['geometry']['location']
        print(f"✓ Coordinates: {location['lat']}, {location['lng']}")
        
        # Check for address components
        if 'address_components' in result:
            print(f"✓ Address components found: {len(result['address_components'])} components")
        
        return True
    else:
        print("✗ Failed to get detailed geocoding info")
        return False


def test_error_handling():
    """Test error handling with invalid inputs."""
    print("\nTesting error handling...")
    
    # Test with invalid location
    result = get_lat_long("NonexistentCity", "NonexistentState", "NonexistentCountry")
    
    if result is None:
        print("✓ Correctly handled invalid location")
        return True
    else:
        print("✗ Should have returned None for invalid location")
        return False


if __name__ == "__main__":
    print("Google Geocoding API Test Suite")
    print("=" * 40)
    
    all_tests_passed = True
    
    # Run all tests
    all_tests_passed &= test_basic_geocoding()
    all_tests_passed &= test_international_locations()
    all_tests_passed &= test_detailed_info()
    all_tests_passed &= test_error_handling()
    
    print("\n" + "=" * 40)
    if all_tests_passed:
        print("🎉 All tests passed!")
    else:
        print("❌ Some tests failed. Check the output above.")
    
    print("\nTo use the geocoding service in your code:")
    print("from geocoding_service import get_lat_long")
    print("lat, lng = get_lat_long('San Francisco', 'CA', 'USA')")
