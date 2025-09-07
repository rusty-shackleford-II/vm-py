#!/usr/bin/env python3
"""
Daily Site Ranking Updater

This script runs daily to check and update site rankings for SEO customers.
Simple synchronous implementation using BrightData directly.

Usage:
    python daily_site_ranking_updater.py
"""

import os
import sys
import time
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
    
    def __init__(self):
        """Initialize the ranking updater."""
        self.db = SupabaseClient()
        self.rank_checker = SiteRankChecker()
    
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
                "ranking_city, ranking_region, ranking_country, ranking_enabled"
            ).eq("ranking_enabled", True).is_("started_at", "not.null").execute()
            
            clients = response.data
            print(f"📊 Found {len(clients)} clients enabled for ranking updates")
            
            # Convert to the format expected by the ranking checker
            client_configs = []
            for client in clients:
                # Skip clients without website or ranking queries
                if not client.get('website') or not client.get('ranking_queries'):
                    print(f"⚠️ Skipping client {client.get('name', 'Unknown')} - missing website or ranking queries")
                    continue
                
                # Create a config for each ranking query
                for query in client['ranking_queries']:
                    config = {
                        "client_id": client['id'],
                        "url": client['website'],
                        "business_name": client.get('business_name') or client.get('name'),
                        "city": client.get('ranking_city'),
                        "region": client.get('ranking_region'), 
                        "country": client.get('ranking_country'),
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
            site_config: Dictionary with client_id, url, business_name, city, region, country, query
            
        Returns:
            Dictionary with ranking results or None if failed
        """
        client_id = site_config["client_id"]
        url = site_config["url"]
        business_name = site_config["business_name"]
        city = site_config["city"]
        region = site_config["region"]
        country = site_config["country"]
        query = site_config["query"]
        
        # Build location display string
        location_parts = [part for part in [city, region, country] if part]
        location_display = ", ".join(location_parts) if location_parts else "No location (organic only)"
        
        print(f"\n🔍 Checking rankings for {url}")
        print(f"   Business: {business_name}")
        print(f"   Location: {location_display}")
        print(f"   Query: {query}")
        
        try:
            # Use SiteRankChecker directly with the location components from the database
            report = self.rank_checker.check_site_ranking(
                domain=url,
                query=query,
                city=city,
                region=region,
                country=country,
                max_results=100
            )
            
            print(f"   Organic rank: {report.best_organic_position if report.best_organic_position else 'Not found'}")
            print(f"   Local business rank: {report.best_local_position if report.best_local_position else 'Not found'}")
            
            return {
                "client_id": client_id,
                "url": url,
                "business_name": business_name,
                "lat": None,  # No geocoding
                "lon": None,  # No geocoding
                "city": city,
                "region": region,
                "country": country,
                "query": query,
                "location_search": location_display if location_parts else None,
                "organic_rank": report.best_organic_position,
                "local_business_rank": report.best_local_position,
                "date": date.today()
            }
            
        except Exception as e:
            print(f"   ⚠️ Error checking rankings: {e}")
            return None
    
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
                "organic_rank": result["organic_rank"],  # Can be None
                "local_business_rank": result["local_business_rank"],  # Can be None
                "query": result["query"],
                "location_search": result["location_search"]  # Can be None
            }
            
            # Use upsert to handle the unique constraint on (url, date, query, city, region, country)
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
        print(f"🚀 Starting daily ranking update")
        print(f"📅 Date: {date.today()}")
        
        # Fetch clients from database
        sites = self.fetch_clients_for_ranking()
        
        if not sites:
            print("❌ No sites found for ranking updates. Exiting.")
            return
        
        print(f"\n📊 Processing {len(sites)} ranking configurations")
        
        successful = 0
        failed = 0
        
        for i, site_config in enumerate(sites, 1):
            print(f"\n{'='*60}")
            print(f"Processing configuration {i}/{len(sites)}")
            
            try:
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
        
        print(f"💾 Results stored in site_rank table")


def main():
    """Main function to run the daily ranking updater."""
    # Initialize updater
    updater = SiteRankingUpdater()
    
    # Run the update for all clients from database
    updater.update_all_sites()


if __name__ == "__main__":
    main()
