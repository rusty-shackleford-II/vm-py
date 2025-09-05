import asyncio
import json
import os
import re
import argparse
import shutil
from typing import List, Dict, Any, Optional
from pprint import pprint

from google_searcher import GoogleSearcher, LocalBusinessResult
from google_review_fetcher import GoogleReviewFetcher, BusinessReviewsResult
from business_review_searcher import BusinessReviewSearcher
from clients.gemini_client import GeminiClient
import config


"""
Business Researcher Script
==========================

Integrates with updated google_review_fetcher.py to collect comprehensive business data.

OUTPUT JSON STRUCTURE:
{
    "business_name": "Business Name",
    "address": "Street address (prioritized from Google Review Fetcher snack_pack)",
    "phone": "Phone number (prioritized from Google Review Fetcher snack_pack)", 
    "website": "Website URL (from 'site' field in snack_pack)",
    "email": null,  // Always null - not available from any source
    "business_type": "Business category (e.g., 'Plumber')",
    "_debug_address_quality": "good|poor|unknown",  // For debugging address quality
    "reviews_and_ratings": {
        "overall_rating": 4.6,  // Average of all independent review source ratings
        "overall_summary": "Human-readable reputation summary",
        "google": {
            "rating": 4.8,
            "review_count": 3000,
            "reviews_summary": "3-paragraph LLM-generated summary of Google reviews (max 2000 tokens)",
            "metadata": {
                "fid": "Google Feature ID for reviews",
                "search_url": "Original search URL",
                "address_source": "snack_pack",
                "address_quality": "good|poor"
            },
            "reviews": [...]  // Individual review objects
        },

        "yelp": {"rating": 4.5, "review_count": 250},
        "angi": {"rating": 4.2, "review_count": 100},
        // ... other review sites
    }
}

DATA SOURCE PRIORITY:
1. Google Review Fetcher (snack_pack data) - Highest quality, includes address quality checking
2. Local Business Search results - Fallback if Google Review Fetcher fails
"""


def clear_and_create_data_dir(data_dir: str = "data"):
    """Clears and recreates the data directory as required by cycle.md workflow."""
    if os.path.exists(data_dir):
        print(f"[Data Dir] Clearing existing data directory: {data_dir}")
        shutil.rmtree(data_dir)

    print(f"[Data Dir] Creating fresh data directory: {data_dir}")
    os.makedirs(data_dir, exist_ok=True)


class Researcher:
    def __init__(self, max_concurrent_tasks=5):
        """Initializes the researcher with all necessary clients and a semaphore for concurrency control."""
        self.google_searcher = GoogleSearcher()
        self.google_review_fetcher = GoogleReviewFetcher()
        self.business_review_searcher = BusinessReviewSearcher(
            use_enhanced_searcher=True
        )

        gemini_keys = []
        for i in range(1, 10):
            try:
                key = getattr(config, f"GEMINI_API_KEY_{i}")
                if key:
                    gemini_keys.append(key)
            except AttributeError:
                break
        if not gemini_keys:
            raise ValueError("No Gemini API keys found in config.py")
        self.gemini_client = GeminiClient(api_keys=gemini_keys)

        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)

        print(
            f"🚦 Researcher initialized with {max_concurrent_tasks} max concurrent tasks"
        )

    def _sanitize_filename(self, name: str) -> str:
        """Removes illegal characters from a string to make it a valid filename."""
        sanitized = re.sub(r'[<>:"/\\|?*]', "", name)
        sanitized = sanitized.replace(" ", "_")
        return sanitized[:100]



    async def _fetch_google_reviews(
        self, business_name: str, location: str
    ) -> BusinessReviewsResult:
        """Fetches Google reviews for a business, respecting the semaphore."""
        print(f"[Google] Fetching reviews for '{business_name}'...")
        try:
            async with self.semaphore:
                reviews_data = await self.google_review_fetcher.fetch_reviews(
                    business_name=business_name,
                    business_location=location,
                    sort="newestFirst",
                    max_results=20,
                )

            if reviews_data:
                print(
                    f"[Google] ✅ Successfully fetched Google data for '{business_name}'"
                )
                # Log what data we got
                data_summary = []
                if reviews_data.business_address:
                    quality = reviews_data.address_quality or "unknown"
                    data_summary.append(f"address ({quality})")
                if reviews_data.business_phone:
                    data_summary.append("phone")
                if reviews_data.business_website:
                    data_summary.append("website")
                if reviews_data.total_rating:
                    data_summary.append(f"rating ({reviews_data.total_rating})")
                if reviews_data.reviews:
                    data_summary.append(f"{len(reviews_data.reviews)} reviews")

                if data_summary:
                    print(f"[Google] Data collected: {', '.join(data_summary)}")

                return reviews_data
            else:
                print(
                    f"[Google] ⚠️ No business match found for '{business_name}' in '{location}'"
                )
                return None

        except Exception as e:
            print(f"[Google] ❌ Error fetching reviews for '{business_name}': {e}")
            return None

    async def _fetch_review_site_ratings(
        self, business_name: str, location: str
    ) -> Dict[str, Any]:
        """Fetches ratings from review sites (Yelp, Angi, HomeAdvisor, BBB) via BusinessReviewSearcher."""
        print(
            f"[Review Sites] Fetching ratings for '{business_name}' from review sites..."
        )
        try:
            review_site_data = (
                await self.business_review_searcher.get_business_review_data(
                    business_name=business_name, location=location, max_results=15
                )
            )
            return review_site_data
        except Exception as e:
            print(
                f"[Review Sites] An error occurred while fetching review site data for '{business_name}': {e}"
            )
            return {}

    def _calculate_overall_rating(
        self, reviews_and_ratings: Dict[str, Any]
    ) -> Optional[float]:
        """Calculate overall rating by averaging ratings from all independent review sources."""
        ratings = []

        # Extract ratings from various sources
        for source, data in reviews_and_ratings.items():
            # Skip overall_summary as it's not a rating source
            if source == "overall_summary":
                continue

            # Handle different data structures
            if isinstance(data, dict):
                rating = data.get("rating")
                if rating is not None:
                    try:
                        # Convert to float and validate range (typically 1-5)
                        rating_float = float(rating)
                        if 0 <= rating_float <= 5:
                            ratings.append(rating_float)
                    except (ValueError, TypeError):
                        continue

        # Calculate average if we have ratings
        if ratings:
            overall_rating = sum(ratings) / len(ratings)
            return round(overall_rating, 1)  # Round to 1 decimal place

        return None



    async def _generate_overall_summary(self, business_data: Dict[str, Any]) -> str:
        """Generate an overall business reputation summary using all collected review data."""
        business_name = business_data.get("business_name", "this business")
        reviews_and_ratings = business_data.get("reviews_and_ratings", {})

        # Check if we have any meaningful data to summarize
        has_google_data = bool(reviews_and_ratings.get("google"))
        has_review_sites = any(
            site in reviews_and_ratings
            for site in ["yelp", "angi", "homeadvisor", "bbb", "thumbtack"]
        )

        if not (has_google_data or has_review_sites):
            return "Limited online reputation data available for this business."

        # Prepare context for the prompt
        context_data = json.dumps(reviews_and_ratings, indent=2)

        prompt = f"""You are a helpful research assistant providing a clear, informative summary of "{business_name}" based on their online reviews and ratings. Your goal is to help someone quickly understand the aggregate internet sentiment about this business.

Write a straightforward, informative summary that explains what customers generally think. Be direct and helpful - like an assistant explaining the findings.

Here\'s the review data to analyze:
{context_data}

Guidelines:
- Write 2-3 paragraphs maximum
- Start with the overall rating/sentiment picture across platforms
- Explain the main themes customers discuss (service quality, pricing, timeliness, etc.)
- Mention both strengths and any common concerns if they exist
- Be factual and based on the data provided
- Use clear, helpful language - avoid casual blog openers
- Focus on explaining what the internet sentiment reveals
- Don\'t give recommendations to the business - just report the findings

Provide your analysis:"""

        try:
            print(
                f"[Overall Summary] Generating reputation summary for '{business_name}'..."
            )
            async with self.semaphore:
                summary = await asyncio.to_thread(self.gemini_client.ask, prompt)



            print(f"[Overall Summary] ✅ Generated summary for '{business_name}'")
            return summary.strip()

        except Exception as e:
            print(
                f"[Overall Summary] ❌ Error generating summary for '{business_name}': {e}"
            )
            return "Unable to generate reputation summary at this time."

    def _extract_business_contact_info(
        self,
        business: LocalBusinessResult,
        google_reviews_result: Optional[BusinessReviewsResult] = None,
    ) -> Dict[str, Optional[str]]:
        """Extract contact information, prioritizing data from Google Review Fetcher over LocalBusinessResult."""
        contact_info = {
            "address": None,
            "phone": None,
            "website": None,
            "email": None,  # Keep this for the JSON structure, but it will always be None
            "address_quality": None,  # Track address quality for debugging
            "business_type": None,  # Business category from Google
        }

        # Prioritize data from Google Review Fetcher if available (higher quality)
        if google_reviews_result:
            if google_reviews_result.business_address:
                contact_info["address"] = google_reviews_result.business_address
                contact_info["address_quality"] = google_reviews_result.address_quality

            if google_reviews_result.business_phone:
                contact_info["phone"] = google_reviews_result.business_phone

            if google_reviews_result.business_website:
                contact_info["website"] = google_reviews_result.business_website

            if google_reviews_result.business_type:
                contact_info["business_type"] = google_reviews_result.business_type

        # Fall back to LocalBusinessResult data if Google Review Fetcher data not available
        if not contact_info["address"] and business.address:
            contact_info["address"] = business.address
            contact_info["address_quality"] = (
                "unknown"  # We don't know quality of LocalBusinessResult address
            )

        if not contact_info["phone"] and business.phone:
            contact_info["phone"] = business.phone

        # Email is not available in either source, so it will remain None
        # This maintains the requested JSON structure while being accurate to available data

        return contact_info

    async def research_business(
        self, business: LocalBusinessResult, location: str
    ) -> Dict[str, Any]:
        """Runs the full research pipeline for a single business and returns the result."""
        business_name = business.name
        print(f"--- Starting research for: {business_name} ---")

        # Run all data gathering tasks in parallel
        google_task = self._fetch_google_reviews(business_name, location)
        review_sites_task = self._fetch_review_site_ratings(business_name, location)

        google_reviews_result, review_sites_data = (
            await asyncio.gather(google_task, review_sites_task)
        )

        # Extract business contact information
        contact_info = self._extract_business_contact_info(
            business, google_reviews_result
        )

        # Log data sources for transparency
        data_sources = []
        if google_reviews_result:
            data_sources.append("Google Review Fetcher")
        if any([business.address, business.phone]):
            data_sources.append("Local Business Search")

        print(
            f"[Data Sources] Using data from: {', '.join(data_sources) if data_sources else 'No sources'}"
        )

        # Log address quality warning if needed
        if contact_info["address_quality"] == "poor":
            print(
                f"⚠️ [Address Quality] Poor quality address detected: {contact_info['address']}"
            )
        elif contact_info["address_quality"] == "good":
            print(
                f"✅ [Address Quality] Good quality address: {contact_info['address']}"
            )

        # Structure the final result according to the new format
        final_result = {
            "business_name": business_name,
            "address": contact_info["address"],
            "phone": contact_info["phone"],
            "website": contact_info[
                "website"
            ],  # New top-level field from 'site' in snack_pack
            "email": contact_info["email"],
            "business_type": contact_info[
                "business_type"
            ],  # Business category from Google
            "reviews_and_ratings": {},
        }

        # Add address quality info for debugging (optional, can be removed in production)
        if contact_info["address_quality"]:
            final_result["_debug_address_quality"] = contact_info["address_quality"]

        # Add Google reviews data
        if google_reviews_result:
            google_data = {}

            # Add rating and review count
            if google_reviews_result.total_rating:
                google_data["rating"] = google_reviews_result.total_rating
            if google_reviews_result.total_review_count:
                google_data["review_count"] = google_reviews_result.total_review_count

            # Add reviews summary if available
            if google_reviews_result.reviews_summary:
                google_data["reviews_summary"] = google_reviews_result.reviews_summary

            # Add business metadata from Google Review Fetcher
            metadata = {}
            if google_reviews_result.business_fid:
                metadata["fid"] = google_reviews_result.business_fid
            if google_reviews_result.search_url:
                metadata["search_url"] = google_reviews_result.search_url
            if (
                google_reviews_result.business_address
                and google_reviews_result.address_quality
            ):
                metadata["address_source"] = "snack_pack"
                metadata["address_quality"] = google_reviews_result.address_quality

            if metadata:
                google_data["metadata"] = metadata

            # Add individual reviews
            if google_reviews_result.reviews:
                google_data["reviews"] = [
                    review.dict() for review in google_reviews_result.reviews
                ]

            if google_data:  # Only add if we have data
                final_result["reviews_and_ratings"]["google"] = google_data



        # Add review site data (Yelp, Angi, HomeAdvisor, BBB)
        if review_sites_data:
            final_result["reviews_and_ratings"].update(review_sites_data)

        # Generate overall reputation summary using all collected data
        if final_result["reviews_and_ratings"]:
            overall_summary = await self._generate_overall_summary(final_result)
            final_result["reviews_and_ratings"]["overall_summary"] = overall_summary

            # Calculate overall rating from all review sources
            overall_rating = self._calculate_overall_rating(
                final_result["reviews_and_ratings"]
            )
            if overall_rating is not None:
                final_result["reviews_and_ratings"]["overall_rating"] = overall_rating

        return final_result

    async def run(
        self,
        query: str,
        location: str,
        num_businesses: int = 10,
        data_dir: str = "data",
    ):
        """Main method to run the entire research process."""
        print(
            f"Starting research for '{query}' in '{location}'."
        )

        local_businesses: list[LocalBusinessResult] = await self.google_searcher.search_local_businesses(
            query=query, location=location, max_results=num_businesses
        )

        if not local_businesses:
            print("No local businesses found to research.")
            return

        for business in local_businesses:
            pprint(business)

        # print(f"Found {len(local_businesses)} businesses. Starting research on each.")

        # all_business_data = []
        # for business in local_businesses:
        #     business_data = await self.research_business(business, location)
        #     all_business_data.append(business_data)

        # # Create a sanitized folder name for the location
        # location_folder = "research"
        # output_dir = os.path.join(data_dir, location_folder)
        # os.makedirs(output_dir, exist_ok=True)

        # filename = os.path.join(
        #     output_dir, self._sanitize_filename(business_category) + ".json"
        # )

        # def save_file():
        #     with open(filename, "w") as f:
        #         json.dump(all_business_data, f, indent=4)

        # await asyncio.to_thread(save_file)

        # print(
        #     f"--- ✅ All research complete for {business_category}. Saved to {filename} ---"
        # )

async def main():
    
    query = "Professional HVAC Contractor"
    location = "San Mateo, CA"
    num_businesses = 10

    # Convert underscore format to readable format for API calls
    # location = args.location.replace("_", " ").replace(",_", ", ")

    researcher = Researcher()
    await researcher.run(
        query=query,
        location=location,
        num_businesses=num_businesses,
    )


if __name__ == "__main__":
    asyncio.run(main())
