#!/usr/bin/env python3
"""
Standalone test script for Namecheap domain listing functionality.

This script tests the get_purchased_domains() method without depending on 
the existing config.py setup. You can run this directly by setting the 
required environment variables.

Usage:
    export NAMECHEAP_API_USER="your_api_user"
    export NAMECHEAP_API_KEY="your_api_key"
    export NAMECHEAP_USERNAME="your_username"
    export CLIENT_IP="your_whitelisted_ip"
    export NAMECHEAP_SANDBOX="true"  # or "false" for production
    
    python test_namecheap_list_domains_standalone.py
"""

import os
import sys
import requests
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from pprint import pprint


class NamecheapClient:
    """
    Standalone Namecheap API client for testing domain listing functionality.
    """

    def __init__(
        self,
        api_user: Optional[str] = None,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        client_ip: Optional[str] = None,
        sandbox: Optional[bool] = None,
        debug: Optional[bool] = None,
    ) -> None:
        self.api_user = api_user or os.getenv("NAMECHEAP_API_USER")
        self.api_key = api_key or os.getenv("NAMECHEAP_API_KEY")
        self.username = username or os.getenv("NAMECHEAP_USERNAME")
        self.client_ip = client_ip or os.getenv("CLIENT_IP")

        if sandbox is None:
            sandbox = os.getenv("NAMECHEAP_SANDBOX", "false").lower() == "true"
        self.sandbox = sandbox

        if debug is None:
            debug = os.getenv("NAMECHEAP_DEBUG", "false").lower() == "true"
        self.debug = debug

        if not all([self.api_user, self.api_key, self.username, self.client_ip]):
            missing = []
            if not self.api_user: missing.append("NAMECHEAP_API_USER")
            if not self.api_key: missing.append("NAMECHEAP_API_KEY")
            if not self.username: missing.append("NAMECHEAP_USERNAME")
            if not self.client_ip: missing.append("CLIENT_IP")
            
            raise ValueError(
                f"Missing Namecheap credentials: {', '.join(missing)}. "
                "Please set these environment variables before running the test."
            )

        self.base_url = (
            "https://api.sandbox.namecheap.com/xml.response"
            if self.sandbox
            else "https://api.namecheap.com/xml.response"
        )

    def get_purchased_domains(self) -> List[Dict[str, Any]]:
        """
        Get list of purchased domains from Namecheap account using namecheap.domains.getList.
        Returns list of { domain: str, expiration_date: str, auto_renew: bool, raw: dict }
        """
        params = {
            "ApiUser": str(self.api_user),
            "ApiKey": str(self.api_key),
            "UserName": str(self.username),
            "ClientIp": str(self.client_ip),
            "Command": "namecheap.domains.getList",
        }

        try:
            print(f"🔗 Making API request to: {self.base_url}")
            resp = requests.get(self.base_url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Namecheap domains.getList failed: {exc}") from exc

        if self.debug:
            safe_params = dict(params)
            if "ApiKey" in safe_params:
                safe_params["ApiKey"] = "***REDACTED***"
            print("[NC DEBUG] domains.getList params:", safe_params)
            print("[NC DEBUG] domains.getList XML:")
            print(resp.text)

        return self._parse_domains_list_response(resp.text)

    def _parse_domains_list_response(self, xml_text: str) -> List[Dict[str, Any]]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise RuntimeError(f"Invalid XML from Namecheap domains.getList: {exc}") from exc

        # Strip XML namespaces for simpler querying
        for elem in root.iter():
            if isinstance(elem.tag, str) and '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]

        status = root.attrib.get("Status")
        if status != "OK":
            # Collect all error messages if present
            error_nodes = root.findall(".//Errors/Error")
            if error_nodes:
                messages = []
                for en in error_nodes:
                    number = en.attrib.get("Number") or en.attrib.get("number")
                    text = (en.text or "").strip()
                    msg = f"[{number}] {text}" if number else text
                    messages.append(msg)
                raise RuntimeError("Namecheap domains.getList API error: " + "; ".join(m for m in messages if m))
            # Fallback: include raw XML snippet for visibility
            snippet = xml_text[:500].replace("\n", " ")
            raise RuntimeError(f"Namecheap domains.getList API error (no message). Raw snippet: {snippet}")

        results: List[Dict[str, Any]] = []
        for node in root.findall(".//Domain"):
            attrib = node.attrib
            domain = attrib.get("Name") or attrib.get("DomainName")
            expiration_date = attrib.get("Expires") or attrib.get("ExpirationDate")
            auto_renew = str(attrib.get("AutoRenew", "false")).lower() == "true"
            results.append({
                "domain": domain,
                "expiration_date": expiration_date,
                "auto_renew": auto_renew,
                "raw": attrib
            })

        return results


def print_header(title: str) -> None:
    """Print a formatted section header"""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


def check_environment_variables() -> bool:
    """Check if all required environment variables are set"""
    print_header("ENVIRONMENT VARIABLE CHECK")
    
    required_vars = [
        "NAMECHEAP_API_USER",
        "NAMECHEAP_API_KEY", 
        "NAMECHEAP_USERNAME",
        "CLIENT_IP"
    ]
    
    missing = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive data for display
            display_value = value if var == "CLIENT_IP" else ("*" * min(len(value), 20))
            print(f"✅ {var}: {display_value}")
        else:
            print(f"❌ {var}: NOT SET")
            missing.append(var)
    
    # Check optional variables
    sandbox = os.getenv("NAMECHEAP_SANDBOX", "false")
    debug = os.getenv("NAMECHEAP_DEBUG", "false")
    print(f"ℹ️  NAMECHEAP_SANDBOX: {sandbox}")
    print(f"ℹ️  NAMECHEAP_DEBUG: {debug}")
    
    if missing:
        print(f"\n❌ Missing required environment variables: {', '.join(missing)}")
        print("\nTo fix this, run:")
        for var in missing:
            print(f'export {var}="your_{var.lower()}"')
        return False
    
    return True


def main():
    """Main test function"""
    print("🧪 Namecheap Domain Listing Test")
    print("This script tests the get_purchased_domains() functionality")
    
    # Check environment variables
    if not check_environment_variables():
        return 1
    
    # Initialize client
    print_header("CLIENT INITIALIZATION")
    try:
        client = NamecheapClient(debug=True)
        print("✅ NamecheapClient initialized successfully")
        print(f"🔧 API User: {client.api_user}")
        print(f"🔧 Username: {client.username}")
        print(f"🔧 Client IP: {client.client_ip}")
        print(f"🔧 Sandbox mode: {client.sandbox}")
        print(f"🔧 Base URL: {client.base_url}")
    except Exception as e:
        print(f"❌ Failed to initialize client: {e}")
        return 1
    
    # Test purchased domains listing
    print_header("PURCHASED DOMAINS TEST")
    try:
        print("📋 Fetching purchased domains...")
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
                    print(f"    Raw attributes: {domain_info['raw']}")
        else:
            print("📭 No purchased domains found in your account")
        
        print_header("FULL RESULTS")
        print("Complete domain data structure:")
        pprint(purchased_domains)
        
        print_header("TEST SUMMARY")
        print("🎉 Test completed successfully!")
        print("✅ The purchased domains endpoint is working correctly.")
        return 0
        
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


if __name__ == "__main__":
    print(__doc__)
    exit_code = main()
    sys.exit(exit_code)
