#!/usr/bin/env python3
"""
Simple test script to check purchased domains functionality.

This script specifically tests the get_purchased_domains() method that's failing
in your web application.
"""

import os
import sys
from pprint import pprint

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from clients.namecheap_client import NamecheapClient
    import config
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you have python-decouple installed: pip install python-decouple")
    sys.exit(1)


def main():
    print("🔍 Testing Namecheap Purchased Domains Functionality")
    print("-" * 50)
    
    # Print current configuration (without sensitive data)
    print("Configuration:")
    print(f"  API User: {getattr(config, 'NAMECHEAP_API_USER', 'NOT SET')}")
    print(f"  Username: {getattr(config, 'NAMECHEAP_USERNAME', 'NOT SET')}")
    print(f"  Client IP: {getattr(config, 'CLIENT_IP', 'NOT SET')}")
    print(f"  Sandbox: {os.getenv('NAMECHEAP_SANDBOX', 'false')}")
    print()
    
    try:
        # Initialize client with debug enabled using config.py
        print("🔧 Initializing Namecheap client...")
        client = NamecheapClient(
            api_user=config.NAMECHEAP_API_USER,
            api_key=config.NAMECHEAP_API_KEY,
            username=config.NAMECHEAP_USERNAME,
            client_ip=config.CLIENT_IP,
            debug=True
        )
        print("✅ Client initialized successfully")
        print(f"   Base URL: {client.base_url}")
        print()
        
        # Test purchased domains
        print("📋 Fetching purchased domains...")
        try:
            purchased_domains = client.get_purchased_domains()
            print("✅ Successfully retrieved purchased domains!")
            
            if purchased_domains:
                print(f"📊 Found {len(purchased_domains)} domain(s):")
                for i, domain_info in enumerate(purchased_domains, 1):
                    print(f"\n  Domain #{i}:")
                    print(f"    Name: {domain_info.get('domain', 'N/A')}")
                    print(f"    Expires: {domain_info.get('expiration_date', 'N/A')}")
                    print(f"    Auto-renew: {domain_info.get('auto_renew', 'N/A')}")
                    
                    # Show raw data if available
                    if domain_info.get('raw'):
                        print(f"    Raw data: {domain_info['raw']}")
            else:
                print("📭 No purchased domains found in your account")
                
            print("\n" + "="*50)
            print("🎉 Test completed successfully!")
            print("The purchased domains endpoint is working correctly.")
            
        except Exception as e:
            print(f"❌ Failed to retrieve purchased domains: {e}")
            print(f"Error type: {type(e).__name__}")
            
            # Provide troubleshooting suggestions
            error_str = str(e).lower()
            print("\n💡 Troubleshooting suggestions:")
            
            if "ip" in error_str and ("whitelist" in error_str or "not whitelisted" in error_str):
                print("  • Your IP address may not be whitelisted")
                print("  • Go to Namecheap Dashboard > Profile > Tools > Namecheap API Access")
                print(f"  • Add your IP address: {client.client_ip}")
                
            elif "authentication" in error_str or "credentials" in error_str:
                print("  • Check your API credentials")
                print("  • Verify NAMECHEAP_API_USER, NAMECHEAP_API_KEY, NAMECHEAP_USERNAME")
                
            elif "sandbox" in error_str:
                print("  • Check if you're using the correct API endpoint")
                print("  • Set NAMECHEAP_SANDBOX=true for sandbox, false for production")
                
            elif "timeout" in error_str:
                print("  • Network timeout - try again")
                print("  • Check your internet connection")
                
            else:
                print(f"  • Unknown error: {e}")
                print("  • Try enabling debug mode to see the raw API response")
            
            return 1
            
    except Exception as e:
        print(f"❌ Failed to initialize Namecheap client: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
