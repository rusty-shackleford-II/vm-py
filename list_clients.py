#!/usr/bin/env python3
"""
Script to pull and pretty print client information from the clients table.

This script connects to the Supabase database and retrieves all client records,
then displays them in a nicely formatted table with all their information.
It also looks up Google Maps CID for each client using their business information.

Usage:
    python list_clients.py
"""

import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
import sys
from pathlib import Path

# Add the current directory to Python path to import local modules
sys.path.append(str(Path(__file__).parent))

from clients.supabase_client import SupabaseClient
from site_to_cid import site_to_cid


def format_datetime(dt_str: str) -> str:
    """Format datetime string for display."""
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    except:
        return dt_str


def format_array(arr: List[str]) -> str:
    """Format array for display."""
    if not arr:
        return "N/A"
    return ", ".join(arr)


def format_json(json_data: Any) -> str:
    """Format JSON data for display."""
    if not json_data:
        return "N/A"
    if isinstance(json_data, (dict, list)):
        return json.dumps(json_data, indent=2)
    return str(json_data)


def print_separator(char: str = "=", length: int = 100):
    """Print a separator line."""
    print(char * length)


async def get_client_cid(client: Dict[str, Any]) -> Optional[str]:
    """Get CID for a client using their business information."""
    try:
        business_name = client.get('business_name') or client.get('name')
        website = client.get('website')
        city = client.get('city')
        region = client.get('region')
        country = client.get('country')
        
        # Check if we have the required information
        if not all([business_name, website, city, region, country]):
            return None
        
        # Extract domain from website if it's a full URL
        domain = website
        if website.startswith(('http://', 'https://')):
            from urllib.parse import urlparse
            parsed = urlparse(website)
            domain = parsed.hostname or website
        
        # Get CID using the site_to_cid function
        cid = await site_to_cid(
            business_name=business_name,
            city=city,
            region=region,
            country=country,
            domain=domain
        )
        
        return cid
        
    except Exception as e:
        print(f"⚠️  Error getting CID for {client.get('name', 'Unknown')}: {e}")
        return None


def print_client_summary(clients: List[Dict[str, Any]]):
    """Print a summary table of all clients."""
    print("\n" + "="*140)
    print("CLIENT SUMMARY")
    print("="*140)
    
    if not clients:
        print("No clients found in the database.")
        return
    
    # Print header
    print(f"{'Name':<25} {'Website':<25} {'Package $':<10} {'Months':<7} {'Backlinks':<12} {'Status':<10} {'CID':<15}")
    print("-" * 140)
    
    # Print each client row
    for client in clients:
        name = (client.get('name') or 'N/A')[:24]
        website = (client.get('website') or 'N/A')[:24]
        package = f"${client.get('package_amount', 0)}"
        months = str(client.get('months_paid', 0))
        backlinks = f"{client.get('num_backlinks', 0)}/{client.get('num_desired_backlinks', 0)}"
        status = "Active" if client.get('ranking_enabled', False) else "Inactive"
        cid = client.get('_cid', 'N/A')[:14]  # CID will be stored temporarily in _cid key
        
        print(f"{name:<25} {website:<25} {package:<10} {months:<7} {backlinks:<12} {status:<10} {cid:<15}")


def print_client_details(clients: List[Dict[str, Any]]):
    """Print detailed information for each client."""
    print("\n" + "="*120)
    print("DETAILED CLIENT INFORMATION")
    print("="*120)
    
    for i, client in enumerate(clients, 1):
        print(f"\n[{i}] CLIENT: {client.get('name', 'N/A')}")
        print_separator("-", 80)
        
        # Basic Information
        print("BASIC INFORMATION:")
        print(f"  ID: {client.get('id', 'N/A')}")
        print(f"  Name: {client.get('name', 'N/A')}")
        print(f"  Business Name: {client.get('business_name', 'N/A')}")
        print(f"  Website: {client.get('website', 'N/A')}")
        print(f"  Created: {format_datetime(client.get('created_at'))}")
        print(f"  Started: {format_datetime(client.get('started_at'))}")
        
        # Financial Information
        print("\nFINANCIAL INFORMATION:")
        print(f"  Package Amount: ${client.get('package_amount', 0)}")
        print(f"  Months Paid: {client.get('months_paid', 0)}")
        print(f"  Warren Paid: {'Yes' if client.get('warren_was_paid_amount', 0) else 'No'}")
        
        # Backlink Information
        print("\nBACKLINK INFORMATION:")
        print(f"  Current Backlinks: {client.get('num_backlinks', 0)}")
        print(f"  Desired Backlinks: {client.get('num_desired_backlinks', 0)}")
        print(f"  Backlink Interval: {client.get('backlink_interval_in_hours', 0)} hours")
        print(f"  Last Backlink Added: {format_datetime(client.get('date_last_backlink_added'))}")
        print(f"  Default Anchor Text: {client.get('default_anchor_text', 'N/A')}")
        
        # Location Information
        print("\nLOCATION INFORMATION:")
        print(f"  Primary City: {client.get('city', 'N/A')}")
        print(f"  Primary Region: {client.get('region', 'N/A')}")
        print(f"  Primary Country: {client.get('country', 'N/A')}")
        
        # Ranking Information
        print("\nRANKING INFORMATION:")
        print(f"  Ranking Enabled: {'Yes' if client.get('ranking_enabled', False) else 'No'}")
        print(f"  Ranking Queries: {format_array(client.get('ranking_queries', []))}")
        
        # Ranking Locations (JSONB)
        ranking_locations = client.get('ranking_locations', [])
        if ranking_locations:
            print("  Ranking Locations:")
            for j, location in enumerate(ranking_locations, 1):
                print(f"    [{j}] {json.dumps(location, indent=6)}")
        else:
            print("  Ranking Locations: N/A")
        
        # CID Information
        print("\nCID INFORMATION:")
        cid = client.get('_cid')
        if cid:
            print(f"  Google Maps CID: {cid}")
        else:
            print("  Google Maps CID: Not available (missing business info or lookup failed)")


async def fetch_client_cids(clients: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fetch CIDs for all clients."""
    print("🔍 Looking up Google Maps CIDs for each client...")
    
    # Create tasks for concurrent CID lookup
    tasks = []
    for client in clients:
        task = get_client_cid(client)
        tasks.append(task)
    
    # Execute all CID lookups concurrently
    cids = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Add CIDs to client records
    for i, client in enumerate(clients):
        cid_result = cids[i]
        if isinstance(cid_result, Exception):
            print(f"⚠️  Error getting CID for {client.get('name', 'Unknown')}: {cid_result}")
            client['_cid'] = 'Error'
        else:
            client['_cid'] = cid_result or 'Not Found'
    
    return clients


async def main_async():
    """Async main function to retrieve and display client information."""
    try:
        print("🔌 Connecting to Supabase database...")
        
        # Initialize the Supabase client
        client = SupabaseClient()
        
        print("📋 Retrieving all clients from the database...")
        
        # Get all clients
        clients = client.get_all_clients()
        
        if not clients:
            print("❌ No clients found in the database.")
            return
        
        print(f"✅ Found {len(clients)} clients in the database.")
        
        # Fetch CIDs for all clients
        clients = await fetch_client_cids(clients)
        
        # Print summary table
        print_client_summary(clients)
        
        # Ask user if they want detailed view
        print("\n" + "="*140)
        response = input("Would you like to see detailed information for each client? (y/N): ").strip().lower()
        
        if response in ['y', 'yes']:
            print_client_details(clients)
        
        print(f"\n✅ Successfully retrieved and displayed information for {len(clients)} clients.")
        
    except Exception as e:
        print(f"❌ Error retrieving client information: {str(e)}")
        sys.exit(1)


def main():
    """Main function wrapper for async execution."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
