
import requests
import json
import time
from typing import List, Dict, Optional
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()  

class GoogleMapsBusinessScraper:
    """
    Google Maps Business Scraper using Bright Data API
    Uses ONLY confirmed existing fields from GitHub samples and n8n workflows
    """

    def __init__(self, api_token: str):
        """
        Initialize the scraper with Bright Data API token

        Args:
            api_token: Your Bright Data API token
        """
        self.api_token = api_token
        self.base_url = "https://api.brightdata.com/datasets/v3"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        # Google Maps dataset ID (confirmed from multiple working examples)
        self.dataset_id = "gd_m8ebnr0q2qlklc02fz"

    def trigger_scraping_job(self, query: str, location: str, limit: int = 20) -> str:
        """
        Trigger a scraping job for Google Maps businesses using ONLY confirmed fields

        Args:
            query: Search query (e.g., 'hvac', 'restaurants', 'plumbers')  
            location: Location to search (e.g., 'San Mateo, CA', 'New York')
            limit: Maximum number of results per search (default: 20)

        Returns:
            snapshot_id: ID to track the scraping job
        """
        url = f"{self.base_url}/trigger"

        # Query parameters from working n8n example
        params = {
            "dataset_id": self.dataset_id,
            "include_errors": "true",
            "type": "discover_new", 
            "discover_by": "location",
            "limit_per_input": str(limit)
        }

        # Payload with ONLY confirmed existing fields from GitHub samples and n8n workflow
        payload = {
            "input": [
                {
                    "country": location,  # Use location as country field when discover_by=location
                    "keyword": query
                }
            ],
            "custom_output_fields": [
                # ✅ CONFIRMED fields from GitHub samples (luminati-io/Google-Maps-dataset-samples)
                "place_id",              # ✅ A unique identifier for the place on Google Maps
                "name",                  # ✅ The name of the business
                "category",              # ✅ The category or type of the business
                "address",               # ✅ The physical address of the business
                "lat",                   # ✅ Latitude coordinate of the business location
                "lon",                   # ✅ Longitude coordinate of the business location (NOTE: "lon" not "lng")
                "url",                   # ✅ URL pointing to the business on Google Maps
                "country",               # ✅ The country where the business is located
                "phone_number",          # ✅ The contact phone number for the business
                "main_image",            # ✅ URL or identifier of the main image associated with the business
                "reviews_count",         # ✅ The total number of reviews for the business
                "rating",                # ✅ The average rating given by customers
                "reviews",               # ✅ Reviews or comments left by customers
                "open_hours",            # ✅ Operating hours of the business
                # "open_hours_updated",    # ✅ The operating hours that were last updated
                # "price_range",           # ✅ The price range associated with the business
                "services_provided",     # ✅ List of services provided by the business
                "open_website",          # ✅ A link or indication of whether the business has a website
                # "category_search_input", # ✅ The category search inputs that were used to get this result

                # ✅ CONFIRMED fields from working n8n workflow
                "description",           # ✅ Business description (from n8n workflow)
                "permanently_closed",    # ✅ Whether business is permanently closed (from n8n workflow)
                "photos_and_videos",     # ✅ Photos and videos associated with the business (from n8n workflow)
                "people_also_search"     # ✅ Related searches (from n8n workflow)
            ]
        }

        try:
            print(f"🔄 Making request to: {url}")
            print(f"📝 Params: {params}")
            print(f"🎯 Using ONLY confirmed existing fields")

            response = requests.post(
                url,
                headers=self.headers,
                params=params, 
                json=payload
            )

            print(f"📊 Response Status: {response.status_code}")

            if response.status_code != 200:
                print(f"❌ Response: {response.text}")

            response.raise_for_status()

            result = response.json()
            snapshot_id = result.get('snapshot_id')

            if snapshot_id:
                print(f"✅ Scraping job triggered successfully!")
                print(f"📋 Snapshot ID: {snapshot_id}")
                print(f"🔍 Query: '{query}' in {location}")
                print(f"📊 Limit: {limit} results")
                return snapshot_id
            else:
                raise Exception(f"No snapshot_id received. Response: {result}")

        except requests.exceptions.RequestException as e:
            print(f"❌ Error triggering scraping job: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response Status: {e.response.status_code}")
                print(f"Response: {e.response.text}")
            raise

    def check_job_status(self, snapshot_id: str) -> Dict:
        """Check the status of a scraping job"""
        url = f"{self.base_url}/progress/{snapshot_id}"
        params = {"format": "json"}

        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Error checking job status: {e}")
            raise

    def wait_for_completion(self, snapshot_id: str, max_wait_time: int = 600) -> bool:
        """Wait for scraping job to complete"""
        start_time = time.time()
        print("⏳ Waiting for scraping job to complete...")

        while time.time() - start_time < max_wait_time:
            try:
                status = self.check_job_status(snapshot_id)
                current_status = status.get('status', 'unknown')
                records_count = status.get('records', 0)

                print(f"📊 Status: {current_status} | Records: {records_count}")

                if current_status == 'ready':
                    print(f"✅ Job completed! Found {records_count} records")
                    return True
                elif current_status in ['failed', 'error']:
                    print(f"❌ Job failed with status: {current_status}")
                    return False

                time.sleep(30)  # Wait 30 seconds before checking again

            except Exception as e:
                print(f"⚠️ Error checking status: {e}")
                time.sleep(30)

        print(f"⏰ Job timed out after {max_wait_time} seconds")
        return False

    def get_results(self, snapshot_id: str) -> List[Dict]:
        """Retrieve the results of a completed scraping job"""
        url = f"{self.base_url}/snapshot/{snapshot_id}"
        params = {"format": "json"}

        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()

            data = response.json()
            return data if isinstance(data, list) else []

        except requests.exceptions.RequestException as e:
            print(f"❌ Error retrieving results: {e}")
            raise

    def scrape_businesses(self, query: str, location: str, limit: int = 20) -> List[Dict]:
        """Complete workflow to scrape businesses"""
        print(f"🚀 Starting Google Maps scraping for '{query}' in {location}")

        # Step 1: Trigger the job
        snapshot_id = self.trigger_scraping_job(query, location, limit)

        # Step 2: Wait for completion  
        if not self.wait_for_completion(snapshot_id):
            raise Exception("Scraping job failed or timed out")

        # Step 3: Get results
        results = self.get_results(snapshot_id)

        print(f"🎉 Successfully scraped {len(results)} businesses!")
        return results

    def extract_identifiers(self, businesses: List[Dict]) -> List[Dict]:
        """Extract and organize the key identifiers from business data"""
        identifiers = []

        for business in businesses:
            # Extract Place ID (confirmed field)
            place_id = business.get('place_id', 'N/A')

            # Extract FID from Google Maps URL (no direct FID field exists)
            fid = self._extract_fid_from_url(business.get('url', ''))

            identifier_data = {
                # Core identifiers
                'place_id': place_id,        # ✅ Main Google identifier
                'fid': fid,                  # 🔍 Extracted from URL

                # Basic business info (all confirmed fields)
                'name': business.get('name', 'N/A'),
                'category': business.get('category', 'N/A'),
                'address': business.get('address', 'N/A'),
                'description': business.get('description', 'N/A'),

                # Contact info (all confirmed fields)
                'phone': business.get('phone_number', 'N/A'),
                'website': business.get('open_website', 'N/A'),
                'url': business.get('url', 'N/A'),

                # Location data (all confirmed fields)
                'coordinates': {
                    'lat': business.get('lat'),
                    'lng': business.get('lon')  # Note: source field is "lon" not "lng"
                },
                'country': business.get('country', 'N/A'),

                # Business metrics (all confirmed fields)
                'rating': business.get('rating', 'N/A'),
                'reviews_count': business.get('reviews_count', 'N/A'),
                'price_range': business.get('price_range', 'N/A'),

                # Additional data (all confirmed fields)
                'hours': business.get('open_hours', 'N/A'),
                'hours_updated': business.get('open_hours_updated', 'N/A'),
                'services': business.get('services_provided', 'N/A'),
                'main_image': business.get('main_image', 'N/A'),
                'photos_videos': business.get('photos_and_videos', 'N/A'),
                'permanently_closed': business.get('permanently_closed', 'N/A'),
                'people_also_search': business.get('people_also_search', 'N/A'),
                'reviews': business.get('reviews', 'N/A'),
                'search_input': business.get('category_search_input', 'N/A'),

                # Raw data for debugging
                'raw_data': business
            }

            identifiers.append(identifier_data)

        return identifiers

    def _extract_fid_from_url(self, url: str) -> str:
        """Extract FID from Google Maps URL using various patterns"""
        if not url:
            return 'N/A'

        try:
            # Pattern 1: CID parameter
            if 'cid=' in url:
                return url.split('cid=')[1].split('&')[0]

            # Pattern 2: FTID parameter  
            if 'ftid=' in url:
                return url.split('ftid=')[1].split('&')[0]

            # Pattern 3: FID parameter
            if 'fid=' in url:
                return url.split('fid=')[1].split('&')[0]

            # Pattern 4: Encoded in data parameter
            if 'data=' in url:
                data_part = url.split('data=')[1].split('&')[0]
                if len(data_part) > 10:  # Only if substantial data
                    return f"encoded:{data_part[:30]}..."

            # Pattern 5: Place ID in URL path
            if '/place/' in url and '@' in url:
                # Extract coordinates which might contain encoded FID
                coords_part = url.split('@')[1].split('/')[0]
                if ',' in coords_part:
                    return f"coords_encoded:{coords_part}"

        except Exception as e:
            print(f"⚠️ Could not extract FID from URL: {e}")

        return 'N/A'

    def save_results(self, data: List[Dict], filename: str = None) -> str:
        """Save results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"google_maps_businesses_{timestamp}.json"

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"💾 Results saved to: {filename}")
        return filename

def main():
    """Example usage with ONLY confirmed fields"""
    # Get API token from environment variable
    api_token = os.getenv('BRIGHT_DATA_API_TOKEN')

    if not api_token:
        print("❌ Please set BRIGHT_DATA_API_TOKEN environment variable")
        print("   Example: export BRIGHT_DATA_API_TOKEN='your_api_token_here'")
        return

    # Initialize scraper
    scraper = GoogleMapsBusinessScraper(api_token)

    try:
        # Search for HVAC businesses in San Mateo  
        query = "hvac"
        location = "San Mateo, CA"
        limit = 10  # Keep small for testing

        # Scrape businesses
        businesses = scraper.scrape_businesses(query, location, limit)

        if not businesses:
            print("⚠️ No businesses found.")
            return

        # Extract identifiers
        identifiers = scraper.extract_identifiers(businesses)

        # Display results
        print(f"\n📋 Found {len(identifiers)} businesses:")
        print("-" * 80)

        place_id_count = 0
        fid_count = 0

        for i, business in enumerate(identifiers[:5], 1):
            print(f"{i}. {business['name']}")
            print(f"   📍 Address: {business['address']}")
            print(f"   🏷️ Category: {business['category']}")
            print(f"   🆔 Place ID: {business['place_id']}")
            print(f"   🔗 FID: {business['fid']}")
            print(f"   📱 Phone: {business['phone']}")
            print(f"   ⭐ Rating: {business['rating']} ({business['reviews_count']} reviews)")
            print(f"   🌐 Website: {business['website']}")
            print(f"   🕒 Hours: {business['hours']}")
            print(f"   💰 Price Range: {business['price_range']}")
            print(f"   🌐 Maps URL: {business['url']}")
            print()

            if business['place_id'] != 'N/A':
                place_id_count += 1
            if business['fid'] != 'N/A':
                fid_count += 1

        # Summary
        print(f"\n🔑 Results Summary:")
        print(f"   Total businesses found: {len(identifiers)}")
        print(f"   Place IDs extracted: {place_id_count}")
        print(f"   FIDs extracted: {fid_count}")

        # Extract and display IDs
        place_ids = [b['place_id'] for b in identifiers if b['place_id'] != 'N/A']
        fids = [b['fid'] for b in identifiers if b['fid'] != 'N/A']

        if place_ids:
            print(f"\n📋 Sample Place IDs:")
            for i, pid in enumerate(place_ids[:3], 1):
                print(f"   {i}. {pid}")

        if fids:
            print(f"\n📋 Sample FIDs:")
            for i, fid in enumerate(fids[:3], 1):
                print(f"   {i}. {fid}")
        else:
            print(f"\n⚠️ No FIDs found in URLs")
            print(f"   URLs may not contain extractable FID patterns")

        # Save results
        filename = scraper.save_results(identifiers)

        # Save just the IDs 
        ids_data = {
            'query': query,
            'location': location,
            'timestamp': datetime.now().isoformat(),
            'total_results': len(identifiers),
            'place_ids': place_ids,
            'fids': fids,
            'field_source': 'confirmed_from_github_samples_and_n8n_workflow'
        }

        clean_location = location.replace(' ', '_').replace(',', '').replace('.', '')
        id_filename = scraper.save_results(ids_data, f"business_ids_{query}_{clean_location}.json")

        # Show what fields were actually returned
        if identifiers and identifiers[0]['raw_data']:
            actual_fields = list(identifiers[0]['raw_data'].keys())
            print(f"\n🔍 Fields actually returned by API:")
            print(f"   {', '.join(sorted(actual_fields))}")

            # Check which requested fields were missing
            requested_fields = set([
                "place_id", "name", "category", "address", "lat", "lon", "url", 
                "country", "phone_number", "main_image", "reviews_count", "rating",
                "reviews", "open_hours", "open_hours_updated", "price_range", 
                "services_provided", "open_website", "category_search_input",
                "description", "permanently_closed", "photos_and_videos", "people_also_search"
            ])

            returned_fields = set(actual_fields)
            missing_fields = requested_fields - returned_fields

            if missing_fields:
                print(f"\n❌ Requested fields that don't exist:")
                print(f"   {', '.join(sorted(missing_fields))}")

    except Exception as e:
        print(f"❌ Error during scraping: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
