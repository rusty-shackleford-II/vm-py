#!/usr/bin/env python3
"""
Comprehensive Namecheap API connection test script.

This script tests all aspects of the Namecheap client configuration and connection:
1. Environment variable validation
2. Client initialization
3. Basic API connectivity
4. Domain availability check
5. Pricing retrieval
6. Purchased domains listing (if you have any)

Run this script to diagnose Namecheap API connection issues.
"""

import os
import sys
from typing import Dict, Any, List
from pprint import pprint

# Add the current directory to Python path so we can import clients
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from clients.namecheap_client import NamecheapClient
    from config import (
        NAMECHEAP_API_USER,
        NAMECHEAP_API_KEY,
        NAMECHEAP_USERNAME,
        CLIENT_IP
    )
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running this script from the vm-py directory")
    sys.exit(1)


def print_header(title: str) -> None:
    """Print a formatted section header"""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


def check_environment_variables() -> Dict[str, Any]:
    """Check if all required environment variables are set"""
    print_header("ENVIRONMENT VARIABLE CHECK")
    
    required_vars = {
        "NAMECHEAP_API_USER": NAMECHEAP_API_USER,
        "NAMECHEAP_API_KEY": NAMECHEAP_API_KEY,
        "NAMECHEAP_USERNAME": NAMECHEAP_USERNAME,
        "CLIENT_IP": CLIENT_IP,
    }
    
    results = {}
    all_present = True
    
    for var_name, var_value in required_vars.items():
        if var_value:
            print(f"✅ {var_name}: {'*' * min(len(str(var_value)), 20)}...")
            results[var_name] = True
        else:
            print(f"❌ {var_name}: NOT SET")
            results[var_name] = False
            all_present = False
    
    # Check optional environment variables
    optional_vars = {
        "NAMECHEAP_SANDBOX": os.getenv("NAMECHEAP_SANDBOX", "false"),
        "NAMECHEAP_DEBUG": os.getenv("NAMECHEAP_DEBUG", "false"),
    }
    
    print("\nOptional environment variables:")
    for var_name, var_value in optional_vars.items():
        print(f"ℹ️  {var_name}: {var_value}")
        results[var_name] = var_value
    
    results["all_required_present"] = all_present
    return results


def test_client_initialization() -> NamecheapClient:
    """Test NamecheapClient initialization"""
    print_header("CLIENT INITIALIZATION TEST")
    
    try:
        # Test with debug enabled to see API calls
        client = NamecheapClient(debug=True)
        print("✅ NamecheapClient initialized successfully")
        
        # Print client configuration (without sensitive data)
        print(f"🔧 API User: {client.api_user}")
        print(f"🔧 Username: {client.username}")
        print(f"🔧 Client IP: {client.client_ip}")
        print(f"🔧 Sandbox mode: {client.sandbox}")
        print(f"🔧 Debug mode: {client.debug}")
        print(f"🔧 Base URL: {client.base_url}")
        
        return client
    except Exception as e:
        print(f"❌ Failed to initialize NamecheapClient: {e}")
        raise


def test_domain_availability(client: NamecheapClient, test_domains: List[str]) -> Dict[str, Any]:
    """Test domain availability checking"""
    print_header("DOMAIN AVAILABILITY TEST")
    
    print(f"Testing availability for domains: {test_domains}")
    
    try:
        results = client.check_domain_availability(test_domains)
        print("✅ Domain availability check successful")
        
        for result in results:
            domain = result.get("domain")
            available = result.get("available")
            status = "Available" if available else "Not Available"
            print(f"  📍 {domain}: {status}")
        
        return {"success": True, "results": results}
    except Exception as e:
        print(f"❌ Domain availability check failed: {e}")
        return {"success": False, "error": str(e)}


def test_domain_pricing(client: NamecheapClient, test_query: str) -> Dict[str, Any]:
    """Test domain pricing retrieval"""
    print_header("DOMAIN PRICING TEST")
    
    print(f"Testing pricing search for: {test_query}")
    
    try:
        results = client.search_domains_with_prices(test_query, tlds=[".com", ".net", ".org"])
        print("✅ Domain pricing search successful")
        
        print(f"Found {len(results)} domain options:")
        for result in results:
            domain = result.get("domain")
            available = result.get("available")
            price = result.get("purchase_price")
            currency = result.get("purchase_currency")
            
            status = "Available" if available else "Not Available"
            price_info = f"${price} {currency}" if price and currency else "Price not available"
            
            print(f"  💰 {domain}: {status} - {price_info}")
        
        return {"success": True, "results": results}
    except Exception as e:
        print(f"❌ Domain pricing search failed: {e}")
        return {"success": False, "error": str(e)}


def test_purchased_domains(client: NamecheapClient) -> Dict[str, Any]:
    """Test purchased domains listing"""
    print_header("PURCHASED DOMAINS TEST")
    
    try:
        results = client.get_purchased_domains()
        print("✅ Purchased domains retrieval successful")
        
        if results:
            print(f"Found {len(results)} purchased domains:")
            for domain_info in results:
                domain = domain_info.get("domain")
                expiration = domain_info.get("expiration_date")
                auto_renew = domain_info.get("auto_renew", False)
                
                print(f"  🏠 {domain}")
                print(f"     Expires: {expiration}")
                print(f"     Auto-renew: {'Yes' if auto_renew else 'No'}")
        else:
            print("📋 No purchased domains found")
        
        return {"success": True, "results": results}
    except Exception as e:
        print(f"❌ Purchased domains retrieval failed: {e}")
        return {"success": False, "error": str(e)}


def test_api_connectivity(client: NamecheapClient) -> Dict[str, Any]:
    """Test basic API connectivity with a simple call"""
    print_header("API CONNECTIVITY TEST")
    
    try:
        # Use a simple domain check as connectivity test
        test_result = client.check_domain_availability(["google.com"])
        print("✅ API connectivity successful")
        print("🔗 Successfully connected to Namecheap API")
        return {"success": True, "connected": True}
    except Exception as e:
        print(f"❌ API connectivity failed: {e}")
        
        # Analyze the error for common issues
        error_str = str(e).lower()
        if "ip" in error_str and "whitelist" in error_str:
            print("💡 Suggestion: Your IP address may not be whitelisted in Namecheap")
            print("   Go to Namecheap Dashboard > Profile > Tools > Namecheap API Access")
            print(f"   Add your current IP: {CLIENT_IP}")
        elif "credentials" in error_str or "authentication" in error_str:
            print("💡 Suggestion: Check your API credentials")
            print("   Verify NAMECHEAP_API_USER, NAMECHEAP_API_KEY, and NAMECHEAP_USERNAME")
        elif "sandbox" in error_str:
            print("💡 Suggestion: Check if you're using the correct API endpoint")
            print("   Set NAMECHEAP_SANDBOX=true for sandbox, false for production")
        
        return {"success": False, "error": str(e)}


def main():
    """Main test function"""
    print("🧪 Namecheap API Connection Test Suite")
    print("This script will test your Namecheap API configuration and connectivity")
    
    # Test 1: Check environment variables
    env_results = check_environment_variables()
    if not env_results["all_required_present"]:
        print("\n❌ Missing required environment variables. Please set them before continuing.")
        return 1
    
    # Test 2: Initialize client
    try:
        client = test_client_initialization()
    except Exception:
        print("\n❌ Client initialization failed. Cannot continue with further tests.")
        return 1
    
    # Test 3: Basic API connectivity
    connectivity_result = test_api_connectivity(client)
    if not connectivity_result["success"]:
        print("\n❌ API connectivity failed. Check your credentials and IP whitelist.")
        return 1
    
    # Test 4: Domain availability check
    test_domains = ["example-test-domain-12345.com", "google.com", "github.com"]
    availability_result = test_domain_availability(client, test_domains)
    
    # Test 5: Domain pricing
    pricing_result = test_domain_pricing(client, "testdomain")
    
    # Test 6: Purchased domains (this might fail if you have no domains)
    purchased_result = test_purchased_domains(client)
    
    # Summary
    print_header("TEST SUMMARY")
    
    tests = [
        ("Environment Variables", env_results["all_required_present"]),
        ("Client Initialization", True),  # If we got here, it worked
        ("API Connectivity", connectivity_result["success"]),
        ("Domain Availability", availability_result["success"]),
        ("Domain Pricing", pricing_result["success"]),
        ("Purchased Domains", purchased_result["success"]),
    ]
    
    passed = sum(1 for _, success in tests if success)
    total = len(tests)
    
    print(f"Tests passed: {passed}/{total}")
    
    for test_name, success in tests:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} {test_name}")
    
    if passed == total:
        print("\n🎉 All tests passed! Your Namecheap client is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check the output above for details.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
