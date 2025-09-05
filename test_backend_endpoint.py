#!/usr/bin/env python3
"""
Test script to directly test the FastAPI backend endpoint for purchased domains.

This script simulates the exact request that the frontend is making to help
diagnose the "Namecheap client not available on server" error.
"""

import os
import sys
import json
import requests
from typing import Dict, Any

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from clients.namecheap_client import NamecheapClient
except ImportError as e:
    print(f"❌ Import error: {e}")
    NamecheapClient = None


def test_direct_client() -> bool:
    """Test if we can create a NamecheapClient directly"""
    print("🔧 Testing direct NamecheapClient creation...")
    
    if NamecheapClient is None:
        print("❌ NamecheapClient not available (import failed)")
        return False
    
    try:
        client = NamecheapClient()
        print("✅ NamecheapClient created successfully")
        return True
    except Exception as e:
        print(f"❌ NamecheapClient creation failed: {e}")
        return False


def test_backend_endpoint(backend_url: str, user_email: str) -> Dict[str, Any]:
    """Test the backend /get-purchased-domains endpoint"""
    print(f"🌐 Testing backend endpoint: {backend_url}/get-purchased-domains")
    print(f"👤 User email: {user_email}")
    
    payload = {"user_email": user_email}
    
    try:
        response = requests.post(
            f"{backend_url}/get-purchased-domains",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"📡 Response status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print("✅ Backend endpoint successful!")
                print(f"📊 Returned {len(data)} domain(s)")
                return {"success": True, "data": data}
            except json.JSONDecodeError:
                print("⚠️  Response is not valid JSON")
                print(f"Raw response: {response.text}")
                return {"success": False, "error": "Invalid JSON response"}
        else:
            error_text = response.text
            print(f"❌ Backend endpoint failed: {error_text}")
            return {"success": False, "error": error_text, "status_code": response.status_code}
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to backend server")
        print("💡 Make sure the FastAPI server is running")
        return {"success": False, "error": "Connection failed"}
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return {"success": False, "error": str(e)}


def simulate_app_py_logic() -> bool:
    """Simulate the exact logic from app.py to see where it fails"""
    print("🔍 Simulating app.py logic...")
    
    # Check if NamecheapClient is available (like in app.py line 17-20)
    try:
        from clients.namecheap_client import NamecheapClient as TestClient
        print("✅ NamecheapClient import successful")
    except Exception as e:
        print(f"❌ NamecheapClient import failed: {e}")
        TestClient = None
    
    # Check the condition from app.py line 1123
    if TestClient is None:
        print("❌ NamecheapClient is None - this would trigger the 500 error")
        print("💡 This is the exact error your frontend is seeing!")
        return False
    else:
        print("✅ NamecheapClient is available")
        
        # Try to create an instance
        try:
            nc = TestClient()
            print("✅ NamecheapClient instance created successfully")
            return True
        except Exception as e:
            print(f"❌ NamecheapClient instance creation failed: {e}")
            return False


def main():
    print("🧪 Backend Endpoint Test for Purchased Domains")
    print("=" * 60)
    
    # Test 1: Check if NamecheapClient can be imported and created
    print("\n1️⃣ Testing direct NamecheapClient creation:")
    direct_test = test_direct_client()
    
    # Test 2: Simulate the exact app.py logic
    print("\n2️⃣ Simulating app.py logic:")
    app_logic_test = simulate_app_py_logic()
    
    # Test 3: Test the actual backend endpoint (if running)
    print("\n3️⃣ Testing backend endpoint:")
    
    # Try to detect if the backend is running
    backend_url = os.getenv("BACKEND_API_BASE", "http://localhost:8000")
    if backend_url.endswith("/"):
        backend_url = backend_url.rstrip("/")
    
    # Use admin email from app.py
    admin_emails = ["edward.hidev@gmail.com", "warren.hidev@gmail.com"]
    test_email = admin_emails[1]  # warren.hidev@gmail.com
    
    endpoint_result = test_backend_endpoint(backend_url, test_email)
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 TEST SUMMARY:")
    print(f"  Direct Client Creation: {'✅ PASS' if direct_test else '❌ FAIL'}")
    print(f"  App.py Logic Simulation: {'✅ PASS' if app_logic_test else '❌ FAIL'}")
    print(f"  Backend Endpoint: {'✅ PASS' if endpoint_result.get('success') else '❌ FAIL'}")
    
    if not direct_test or not app_logic_test:
        print("\n💡 DIAGNOSIS:")
        print("The issue is with NamecheapClient availability on the server.")
        print("This could be due to:")
        print("  • Missing environment variables (API credentials)")
        print("  • Import errors in the clients module")
        print("  • Configuration issues in config.py")
        print("\nTry running the comprehensive test:")
        print("  python test_namecheap_connection.py")
        
    elif not endpoint_result.get("success"):
        if endpoint_result.get("error") == "Connection failed":
            print("\n💡 DIAGNOSIS:")
            print("The FastAPI backend server is not running.")
            print("Start it with: uvicorn app:app --reload --host 0.0.0.0 --port 8000")
        else:
            print(f"\n💡 DIAGNOSIS:")
            print(f"Backend endpoint error: {endpoint_result.get('error')}")
    else:
        print("\n🎉 All tests passed! The backend should be working correctly.")
    
    return 0 if (direct_test and app_logic_test and endpoint_result.get("success")) else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
