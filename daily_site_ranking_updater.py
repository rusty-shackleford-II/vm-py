#!/usr/bin/env python3
"""
Daily Site Ranking Updater

This script runs daily to check and update site rankings for SEO customers.
Simple synchronous implementation using BrightData directly.

Usage:
    python daily_site_ranking_updater.py              # Run live ranking updates
    python daily_site_ranking_updater.py --dry-run    # Preview mode: show URLs without searching
"""

import os
import sys
import time
import argparse
from datetime import date
from typing import Dict, List, Optional

# Ensure local imports work when running this file directly
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from clients.supabase_client import SupabaseClient
from brightdata_site_rank_checker import SiteRankChecker



# No longer using hardcoded sites - will fetch from clients table


class SiteRankingUpdater:
    """Handles daily site ranking updates."""
    
    def __init__(self, dry_run: bool = False):
        """Initialize the ranking updater."""
        self.db = SupabaseClient()
        self.rank_checker = SiteRankChecker()
        self.dry_run = dry_run
    
    def fetch_clients_for_ranking(self) -> List[Dict]:
        """
        Fetch all clients from the database that are enabled for ranking updates.
        
        Returns:
            List of client dictionaries with ranking configuration
        """
        try:
            # Query clients table for ranking-enabled clients who have started their service
            response = self.db.client.table("clients").select(
                "id, name, website, business_name, ranking_queries, "
                "city, region, country, ranking_locations, ranking_enabled"
            ).eq("ranking_enabled", True).filter("started_at", "not.is", "null").execute()
            
            clients = response.data
            print(f"📊 Found {len(clients)} clients enabled for ranking updates")
            
            # Convert to the format expected by the ranking checker
            client_configs = []
            for client in clients:
                # Skip clients without website or ranking queries
                if not client.get('website') or not client.get('ranking_queries'):
                    print(f"⚠️ Skipping client {client.get('name', 'Unknown')} - missing website or ranking queries")
                    continue
                
                # Get locations to check - use ranking_locations if available, otherwise fall back to primary location
                locations_to_check = []
                
                # Check if ranking_locations field has data
                ranking_locations = client.get('ranking_locations', [])
                if ranking_locations and isinstance(ranking_locations, list) and len(ranking_locations) > 0:
                    # Use the locations from ranking_locations JSONB field
                    locations_to_check = ranking_locations
                    print(f"🌍 Using {len(ranking_locations)} locations from ranking_locations field for {client.get('name')}")
                else:
                    # Fall back to primary city/region/country fields
                    primary_location = {}
                    if client.get('city'):
                        primary_location['city'] = client['city']
                    if client.get('region'):
                        primary_location['region'] = client['region']
                    if client.get('country'):
                        primary_location['country'] = client['country']
                    
                    if primary_location:
                        locations_to_check = [primary_location]
                        print(f"🌍 Using primary location for {client.get('name')}: {primary_location}")
                    else:
                        # No location data - create one config for organic-only ranking
                        locations_to_check = [{}]
                        print(f"🌍 No location data for {client.get('name')} - will check organic rankings only")
                
                # Create a config for each query x location combination
                for query in client['ranking_queries']:
                    for location in locations_to_check:
                        config = {
                            "client_id": client['id'],
                            "url": client['website'],
                            "business_name": client.get('business_name') or client.get('name'),
                            # Use primary client location for CID lookup
                            "client_city": client.get('city'),
                            "client_region": client.get('region'),
                            "client_country": client.get('country'),
                            # Use ranking location for search personalization
                            "city": location.get('city'),
                            "region": location.get('region'), 
                            "country": location.get('country'),
                            "zipcode": location.get('zipcode'),
                            "query": query
                        }
                        client_configs.append(config)
            
            print(f"🎯 Generated {len(client_configs)} ranking configurations")
            return client_configs
            
        except Exception as e:
            print(f"❌ Error fetching clients from database: {e}")
            return []
    
    def check_site_rankings(self, site_config: Dict) -> Optional[Dict]:
        """
        Check rankings for a single site configuration.
        
        Args:
            site_config: Dictionary with client_id, url, business_name, client_city, client_region, client_country, city, region, country, zipcode, query
            
        Returns:
            Dictionary with ranking results or None if failed
        """
        client_id = site_config["client_id"]
        url = site_config["url"]
        business_name = site_config["business_name"]
        # Client location for CID lookup
        client_city = site_config["client_city"]
        client_region = site_config["client_region"]
        client_country = site_config["client_country"]
        # Ranking location for search personalization
        city = site_config["city"]
        region = site_config["region"]
        country = site_config["country"]
        zipcode = site_config["zipcode"]
        query = site_config["query"]
        
        # Build location display string
        location_parts = [part for part in [city, region, country, zipcode] if part]
        location_display = ", ".join(location_parts) if location_parts else "No location (organic only)"
        
        print(f"\n🔍 Checking rankings for {url}")
        print(f"   Business: {business_name}")
        print(f"   Search Location: {location_display}")
        client_location_parts = [part for part in [client_city, client_region, client_country] if part]
        client_location_display = ", ".join(client_location_parts) if client_location_parts else "No client location"
        print(f"   Client Location (for CID): {client_location_display}")
        print(f"   Query: {query}")
        
        try:
            # Build ranking_locations list for the SiteRankChecker
            ranking_locations = []
            if city or region or country or zipcode:
                location_dict = {}
                if city:
                    location_dict['city'] = city
                if region:
                    location_dict['region'] = region
                if country:
                    location_dict['country'] = country
                if zipcode:
                    location_dict['zipcode'] = zipcode
                ranking_locations = [location_dict]
            else:
                # Empty list means non-localized organic search only
                ranking_locations = []
            
            # Use SiteRankChecker with the new signature that expects ranking_locations
            reports = self.rank_checker.check_site_ranking(
                domain=url,
                query=query,
                ranking_locations=ranking_locations,
                business_name=business_name,
                city=client_city,  # Client's primary city for CID lookup
                region=client_region,  # Client's primary region for CID lookup
                country=client_country,  # Client's primary country for CID lookup
                max_results=100
            )
            
            # The method returns a list of reports, take the first one
            report = reports[0] if reports else None
            if not report:
                print(f"   ❌ No ranking report returned")
                return None
            
            print(f"   Organic rank: {report.best_organic_position if report.best_organic_position else 'Not found'}")
            print(f"   Local business rank: {report.best_local_position if report.best_local_position else 'Not found'}")
            
            return {
                "client_id": client_id,
                "url": url,
                "business_name": business_name,
                "lat": report.lat,  # Use geocoded coordinates from brightdata checker
                "lon": report.lon,  # Use geocoded coordinates from brightdata checker
                "city": city,
                "region": region,
                "country": country,
                "zipcode": zipcode,
                "query": query,
                "location_search": location_display if location_parts else None,
                "organic_rank": report.best_organic_position,
                "local_business_rank": report.best_local_position,
                "date": date.today()
            }
            
        except Exception as e:
            print(f"   ⚠️ Error checking rankings: {e}")
            return None
    
    def preview_search_urls(self, site_config: Dict) -> None:
        """
        Preview the search URLs that would be generated for a site configuration.
        Used in dry-run mode to show what searches would be performed.
        
        Args:
            site_config: Dictionary with client_id, url, business_name, client_city, client_region, client_country, city, region, country, zipcode, query
        """
        from brightdata_site_rank_checker import LocationSpec
        
        client_id = site_config["client_id"]
        url = site_config["url"]
        business_name = site_config["business_name"]
        # Client location for CID lookup
        client_city = site_config["client_city"]
        client_region = site_config["client_region"]
        client_country = site_config["client_country"]
        # Ranking location for search personalization
        city = site_config["city"]
        region = site_config["region"]
        country = site_config["country"]
        zipcode = site_config["zipcode"]
        query = site_config["query"]
        
        # Build location display string
        location_parts = [part for part in [city, region, country, zipcode] if part]
        location_display = ", ".join(location_parts) if location_parts else "No location (organic only)"
        
        print(f"\n🔍 PREVIEW: Rankings for {url}")
        print(f"   Business: {business_name}")
        print(f"   Search Location: {location_display}")
        client_location_parts = [part for part in [client_city, client_region, client_country] if part]
        client_location_display = ", ".join(client_location_parts) if client_location_parts else "No client location"
        print(f"   Client Location (for CID): {client_location_display}")
        print(f"   Query: {query}")
        
        # Create LocationSpec for URL generation
        location_spec = LocationSpec(
            city=city,
            region=region,
            country=country,
            zipcode=zipcode
        )
        
        # Generate the search URLs that would be used
        organic_url = self.rank_checker._build_search_url(
            q=query,
            gl="us",
            hl="en",
            location_spec=location_spec,
            search_type="organic",
            num=100
        )
        
        # Show the actual query that will be used (as-is without location suffix)
        print(f"   🔗 Actual Query: '{query}'")
        print(f"   🌐 Organic Search URL:")
        print(f"      {organic_url}")
        
        # Check if we would attempt local business search
        # Note: In dry-run we don't actually fetch CID, just show what would happen
        if business_name and client_city and client_region and client_country:
            print(f"   🏢 Would attempt CID lookup for: '{business_name}' in {client_location_display}")
            
            # Show what local search URL would look like (assuming CID found)
            local_url = self.rank_checker._build_search_url(
                q=query,
                gl="us", 
                hl="en",
                location_spec=location_spec,
                search_type="local",
                num=20
            )
            print(f"   🏪 Local Business Search URL (if CID found):")
            print(f"      {local_url}")
        else:
            print(f"   ⏭️ No local business search - missing business_name or client location")
    
    def store_ranking_result(self, result: Dict) -> bool:
        """
        Store a ranking result in the database.
        
        Args:
            result: Dictionary with ranking data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Prepare data for database storage
            data = {
                "url": result["url"],
                "business_name": result["business_name"],
                "date": result["date"].isoformat(),
                "lat": result["lat"],  # Can be None
                "lon": result["lon"],  # Can be None
                "city": result["city"],  # Can be None
                "region": result["region"],  # Can be None
                "country": result["country"],  # Can be None
                "zipcode": result["zipcode"],  # Can be None
                "organic_rank": result["organic_rank"],  # Can be None
                "local_business_rank": result["local_business_rank"],  # Can be None
                "query": result["query"],
                "location_search": result["location_search"]  # Can be None
            }
            
            # Use upsert to handle the unique constraint on (url, date, query, city, region, country, zipcode)
            self.db.client.table("site_rank").upsert(data).execute()
            
            print(f"💾 Stored ranking data for {result['url']}")
            return True
            
        except Exception as e:
            print(f"❌ Error storing ranking result: {e}")
            return False
    
    def update_all_sites(self) -> None:
        """
        Update rankings for all clients enabled for ranking updates.
        Fetches clients from the database instead of using hardcoded list.
        """
        mode_text = "DRY RUN - Preview Mode" if self.dry_run else "Live Ranking Update"
        print(f"🚀 Starting {mode_text}")
        print(f"📅 Date: {date.today()}")
        
        # Fetch clients from database
        sites = self.fetch_clients_for_ranking()
        
        if not sites:
            print("❌ No sites found for ranking updates. Exiting.")
            return
        
        print(f"\n📊 Processing {len(sites)} ranking configurations")
        
        if self.dry_run:
            print(f"🔍 DRY RUN MODE: Showing client info and search URLs without performing searches")
        
        successful = 0
        failed = 0
        
        for i, site_config in enumerate(sites, 1):
            print(f"\n{'='*60}")
            print(f"Configuration {i}/{len(sites)}")
            
            try:
                if self.dry_run:
                    # Dry run: just preview the URLs and client info
                    self.preview_search_urls(site_config)
                    successful += 1
                else:
                    # Live run: actually perform the searches
                    # Add delay between sites to be respectful to search APIs
                    if i > 1:
                        print("⏳ Waiting 5 seconds between requests...")
                        time.sleep(5)
                    
                    result = self.check_site_rankings(site_config)
                    
                    if result:
                        success = self.store_ranking_result(result)
                        if success:
                            successful += 1
                        else:
                            failed += 1
                    else:
                        failed += 1
                    
            except Exception as e:
                print(f"❌ Error processing {site_config.get('url', 'unknown')}: {e}")
                failed += 1
        
        print(f"\n{'='*60}")
        print(f"🎯 SUMMARY")
        print(f"   ✅ Successful: {successful}")
        print(f"   ❌ Failed: {failed}")
        print(f"   📊 Total: {len(sites)}")
        
        if not self.dry_run:
            print(f"💾 Results stored in site_rank table")
        else:
            print(f"🔍 DRY RUN: No actual searches performed or data stored")


def main():
    """Main function to run the daily ranking updater."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Daily Site Ranking Updater')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Preview mode: show client info and search URLs without performing actual searches')
    
    args = parser.parse_args()
    
    # Initialize updater with dry-run flag
    updater = SiteRankingUpdater(dry_run=args.dry_run)
    
    # Run the update for all clients from database
    updater.update_all_sites()


if __name__ == "__main__":
    main()
