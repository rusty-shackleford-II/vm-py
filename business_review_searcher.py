#!/usr/bin/env python3
"""
Business Review Searcher Script
Uses GoogleSearcher to find reviews for a specific business on review sites
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from google_searcher import GoogleSearcher
from pprint import pprint
import re


class BusinessRating(BaseModel):
    """Structured model for business rating data"""

    rating: Optional[float] = None
    review_count: Optional[int] = None
    source_name: str
    source_link: str
    title: str
    position: int

    class Config:
        json_encoders = {float: lambda v: round(v, 1) if v is not None else None}


class BusinessReviewResults(BaseModel):
    """Container for all business review results"""

    business_name: str
    location: str
    search_query: str
    total_results: int
    results_with_ratings: List[BusinessRating]

    def to_json(self) -> str:
        """Convert to JSON string"""
        return self.model_dump_json(indent=2)


class BusinessReviewSearcher:
    """Search for business reviews on specific review sites using unified GoogleSearcher"""

    def __init__(self, use_enhanced_searcher: bool = True):
        # Use the unified GoogleSearcher with enhanced mode
        if use_enhanced_searcher:
            self.searcher = GoogleSearcher(enhanced_mode=True)
            self.enhanced_mode = True
        else:
            self.searcher = GoogleSearcher(enhanced_mode=False)
            self.enhanced_mode = False

        self.review_sites = [
            "angi.com",
            "homeadvisor.com",
            "yelp.com",
            "tripadvisor.com",
        ]
        self.collected_ratings = []  # Store structured rating data

    def build_review_search_query(self, business_name: str, location: str) -> str:
        """Build search query for business reviews on specific sites"""
        # Format: "<business name>, <location> reviews site:angi.com OR site:homeadvisor.com OR site:yelp.com OR site:bbb.org"
        site_operators = " OR ".join([f"site:{site}" for site in self.review_sites])
        query = f"{business_name}, {location} reviews {site_operators}"
        return query

    def extract_yelp_rating_info(self, snippet: str) -> dict:
        """Extract rating and review count from Yelp snippets"""
        rating_info = {"rating": None, "review_count": None, "has_yelp_data": False}

        # Look for rating patterns like "4.5 stars" or "4.5/5"
        rating_patterns = [
            r"(\d+\.?\d*)\s*stars?",
            r"(\d+\.?\d*)\s*/\s*5",
            r"Rating:\s*(\d+\.?\d*)",
            r"(\d+\.?\d*)\s*out of 5",
        ]

        for pattern in rating_patterns:
            match = re.search(pattern, snippet, re.IGNORECASE)
            if match:
                rating_info["rating"] = float(match.group(1))
                rating_info["has_yelp_data"] = True
                break

        # Look for review count patterns like "123 reviews" or "(45)"
        review_patterns = [
            r"(\d+)\s*reviews?",
            r"\((\d+)\)",
            r"(\d+)\s*Reviews",
            r"Based on (\d+)",
        ]

        for pattern in review_patterns:
            match = re.search(pattern, snippet, re.IGNORECASE)
            if match:
                rating_info["review_count"] = int(match.group(1))
                rating_info["has_yelp_data"] = True
                break

        return rating_info

    def get_site_name(self, domain: str) -> str:
        """Get friendly site name from domain"""
        site_map = {
            "yelp.com": "Yelp",
            "angi.com": "Angi",
            "homeadvisor.com": "HomeAdvisor",
            "tripadvisor.com": "TripAdvisor",
        }

        for site, name in site_map.items():
            if site in domain.lower():
                return name

        return domain

    def deconflict_duplicate_sources(
        self, rating_objects: List[BusinessRating]
    ) -> List[BusinessRating]:
        """
        Deconflict duplicate results from the same source using the following logic:
        1. If there are 2 results from the same source, keep the one with both ratings and reviews
        2. If both have both ratings and reviews, keep the one with the higher page rank (lower position number)

        Args:
            rating_objects: List of BusinessRating objects

        Returns:
            Filtered list with duplicates removed
        """
        if not rating_objects:
            return rating_objects

        # Group by source_name
        source_groups = {}
        for rating_obj in rating_objects:
            source_name = rating_obj.source_name
            if source_name not in source_groups:
                source_groups[source_name] = []
            source_groups[source_name].append(rating_obj)

        deconflicted_results = []

        for source_name, source_results in source_groups.items():
            if len(source_results) == 1:
                # No conflicts, keep the single result
                deconflicted_results.extend(source_results)
            else:
                # Multiple results from same source - apply deconfliction logic
                print(
                    f"🔧 DEBUG: Found {len(source_results)} results from {source_name}, applying deconfliction..."
                )

                # Check which results have both rating and review count
                complete_results = []
                incomplete_results = []

                for result in source_results:
                    has_rating = result.rating is not None
                    has_reviews = result.review_count is not None

                    if has_rating and has_reviews:
                        complete_results.append(result)
                        print(
                            f"   ✅ Complete result: {result.title[:50]}... (Rating: {result.rating}, Reviews: {result.review_count}, Position: {result.position})"
                        )
                    else:
                        incomplete_results.append(result)
                        print(
                            f"   ⚠️  Incomplete result: {result.title[:50]}... (Rating: {result.rating}, Reviews: {result.review_count}, Position: {result.position})"
                        )

                if complete_results:
                    # Keep the complete result with the best page rank (lowest position number)
                    best_result = min(complete_results, key=lambda x: x.position)
                    deconflicted_results.append(best_result)
                    print(
                        f"   🎯 Keeping complete result with best rank: {best_result.title[:50]}... (Position: {best_result.position})"
                    )
                elif incomplete_results:
                    # If no complete results, keep the one with the best page rank
                    best_result = min(incomplete_results, key=lambda x: x.position)
                    deconflicted_results.append(best_result)
                    print(
                        f"   🎯 Keeping incomplete result with best rank: {best_result.title[:50]}... (Position: {best_result.position})"
                    )

        print(
            f"🔧 DEBUG: Deconfliction reduced {len(rating_objects)} results to {len(deconflicted_results)} results"
        )
        return deconflicted_results

    def collect_rating_data(
        self, results: List, business_name: str, location: str
    ) -> BusinessReviewResults:
        """Collect all rating data into structured format"""
        rating_objects = []
        search_query = self.build_review_search_query(business_name, location)

        for i, result in enumerate(results, 1):
            # DEBUG: Show what's in each result's rating_data
            print(f"🔧 DEBUG Result #{i}: {result.title[:50]}...")
            print(
                f"   hasattr(result, 'rating_data'): {hasattr(result, 'rating_data')}"
            )
            if hasattr(result, "rating_data"):
                print(f"   result.rating_data: {result.rating_data}")
            else:
                print(f"   NO rating_data attribute found!")

            # Check if result has rating data
            has_rating_data = False
            rating = None
            review_count = None

            # First check enhanced mode rating data (this is where the main data is!)
            if (
                self.enhanced_mode
                and hasattr(result, "rating_data")
                and result.rating_data
            ):
                rating_data = result.rating_data
                print(f"   ✅ Found rating_data: {rating_data}")
                # If the extraction found data, use it
                if rating_data.get("has_rating_data"):
                    has_rating_data = True
                    rating = rating_data.get("rating")
                    review_count = rating_data.get("review_count")
                    print(
                        f"   ✅ Using has_rating_data=True: rating={rating}, reviews={review_count}"
                    )
                # Also check for individual fields even without the flag
                elif (
                    rating_data.get("rating") is not None
                    or rating_data.get("review_count") is not None
                ):
                    has_rating_data = True
                    rating = rating_data.get("rating")
                    review_count = rating_data.get("review_count")
                    print(
                        f"   ✅ Using individual fields: rating={rating}, reviews={review_count}"
                    )
            else:
                print(f"   ❌ No enhanced rating data found")

            # Also check snippet extraction as fallback
            snippet_data = self.extract_yelp_rating_info(result.snippet)
            if snippet_data.get("has_yelp_data"):
                has_rating_data = True
                if rating is None:
                    rating = snippet_data.get("rating")
                if review_count is None:
                    review_count = snippet_data.get("review_count")
                print(
                    f"   ✅ Snippet extraction added: rating={rating}, reviews={review_count}"
                )

            # If we have any rating data, create a BusinessRating object
            if has_rating_data or rating is not None or review_count is not None:
                site_name = (
                    self.get_site_name(result.domain) if result.domain else "Unknown"
                )

                print(
                    f"🔧 DEBUG: Collecting data for {result.title[:50]}... - Rating: {rating}, Reviews: {review_count}"
                )

                business_rating = BusinessRating(
                    rating=rating,
                    review_count=review_count,
                    source_name=site_name,
                    source_link=result.url,
                    title=result.title,
                    position=result.position,
                )
                rating_objects.append(business_rating)
            else:
                print(f"   ❌ No rating data found for result #{i}")

        print(
            f"🎯 DEBUG: Collected {len(rating_objects)} results with rating data out of {len(results)} total results"
        )

        # Apply deconfliction logic to handle duplicate sources
        deconflicted_rating_objects = self.deconflict_duplicate_sources(rating_objects)

        return BusinessReviewResults(
            business_name=business_name,
            location=location,
            search_query=search_query,
            total_results=len(results),
            results_with_ratings=deconflicted_rating_objects,
        )

    async def search_business_reviews(
        self, business_name: str, location: str, max_results: int = 20
    ) -> List:
        """Search for business reviews on review sites"""
        query = self.build_review_search_query(business_name, location)

        print(f"🔍 Searching for: {query}")
        print(f"📊 Getting up to {max_results} results")
        print(f"🚀 Enhanced mode: {'ON' if self.enhanced_mode else 'OFF'}")
        print("-" * 80)

        if self.enhanced_mode:
            # Use the enhanced search method for better rating extraction
            results = await self.searcher.search_enhanced_organic_results(
                query=query,
                location=location,
                max_results=max_results,
                enable_knowledge_panel=True,
            )
        else:
            # Use standard organic search
            results = await self.searcher.search_organic_results(
                query=query,
                location="",  # Location is already in the query
                max_results=max_results,
            )

        return results

    def pretty_print_results(self, results: List, business_name: str, location: str):
        """Pretty print the search results with detailed information"""
        print(f"\n{'='*100}")
        print(f"📋 BUSINESS REVIEW SEARCH RESULTS")
        print(f"🏢 Business: {business_name}")
        print(f"📍 Location: {location}")
        print(f"📊 Found {len(results)} results")
        print(f"🚀 Enhanced mode: {'ON' if self.enhanced_mode else 'OFF'}")
        print(f"{'='*100}")

        if not results:
            print("❌ No results found")
            return

        # DEBUG: Show raw JSON data for the first result
        if self.enhanced_mode and results and hasattr(results[0], "parsed_data"):
            print(f"\n🔍 DEBUG: RAW JSON DATA FROM FIRST RESULT")
            print(f"{'='*100}")
            print("📋 Complete BrightData Response for Result #1:")
            print("-" * 80)
            pprint(results[0].parsed_data, width=120, depth=None)
            print(f"{'='*100}")

        for i, result in enumerate(results, 1):
            print(f"\n🔍 Result #{i}")
            print(f"{'─'*50}")

            # Site information
            site_name = (
                self.get_site_name(result.domain) if result.domain else "Unknown"
            )
            print(f"🌐 Site: {site_name}")
            print(f"🔗 Domain: {result.domain}")

            # Title and URL
            print(f"📝 Title: {result.title}")
            print(f"🔗 URL: {result.url}")

            # Position
            print(f"🥇 Position: {result.position}")

            # Snippet
            print(f"📄 Snippet:")
            print(f"   {result.snippet}")

            # Enhanced rating data (if available)
            if self.enhanced_mode and hasattr(result, "rating_data"):
                rating_data = result.rating_data
                if (
                    rating_data.get("has_rating_data")
                    or rating_data.get("rating")
                    or rating_data.get("review_count")
                ):
                    print(f"⭐ ENHANCED RATING DATA:")
                    if rating_data.get("rating"):
                        print(f"   ⭐ Rating: {rating_data['rating']}")
                    if rating_data.get("review_count"):
                        print(f"   📊 Reviews: {rating_data['review_count']}")
                    if rating_data.get("source"):
                        print(f"   🔧 Source: {rating_data['source']}")

                # Rich snippet data
                if hasattr(result, "rich_snippet_data") and result.rich_snippet_data:
                    print(f"💎 RICH SNIPPET DATA:")
                    for key, value in result.rich_snippet_data.items():
                        print(f"   {key}: {value}")

            # Fallback to old extraction method
            rating_info = self.extract_yelp_rating_info(result.snippet)
            if rating_info["has_yelp_data"]:
                print(f"⭐ SNIPPET EXTRACTED Rating Info:")
                if rating_info["rating"]:
                    print(f"   ⭐ Rating: {rating_info['rating']}")
                if rating_info["review_count"]:
                    print(f"   📊 Reviews: {rating_info['review_count']}")

            # Highlight if it's Yelp
            if result.domain and "yelp.com" in result.domain.lower():
                print(f"🎯 YELP RESULT - Pay special attention to rating data above!")

            # Show individual result's raw data for first 3 results
            if i <= 3 and self.enhanced_mode and hasattr(result, "parsed_data"):
                print(f"\n📋 RAW DATA FOR RESULT #{i}:")
                print(f"{'─'*40}")
                print("🔍 Available fields in parsed_data:")
                for key in result.parsed_data.keys():
                    print(f"   - {key}: {type(result.parsed_data[key])}")
                print(f"{'─'*40}")
                print("📄 Complete parsed_data:")
                pprint(result.parsed_data, width=100, depth=3)
                print(f"{'─'*40}")

        print(f"\n{'='*100}")

        # Summary by site
        print(f"📊 SUMMARY BY SITE:")
        site_counts = {}
        yelp_results = []
        rating_results = []

        for result in results:
            site_name = (
                self.get_site_name(result.domain) if result.domain else "Unknown"
            )
            site_counts[site_name] = site_counts.get(site_name, 0) + 1

            if result.domain and "yelp.com" in result.domain.lower():
                yelp_results.append(result)

            # Check for rating data
            has_rating = False
            if self.enhanced_mode and hasattr(result, "rating_data"):
                if result.rating_data.get("rating") or result.rating_data.get(
                    "review_count"
                ):
                    has_rating = True

            if has_rating:
                rating_results.append(result)

        for site, count in site_counts.items():
            print(f"   {site}: {count} results")

        # Enhanced rating summary
        if self.enhanced_mode and rating_results:
            print(f"\n🎯 RESULTS WITH RATING DATA:")
            for i, result in enumerate(rating_results, 1):
                rating_data = result.rating_data
                rating_str = f"⭐{rating_data.get('rating', 'N/A')}"
                review_str = f"📊{rating_data.get('review_count', 'N/A')} reviews"
                print(f"   {i}. {result.title}")
                print(f"      {rating_str} | {review_str}")
                print(f"      🔗 {result.url}")

        # Special Yelp summary
        if yelp_results:
            print(f"\n🎯 YELP RESULTS SUMMARY:")
            for i, result in enumerate(yelp_results, 1):
                rating_info = self.extract_yelp_rating_info(result.snippet)
                rating_str = (
                    f"⭐{rating_info['rating']}"
                    if rating_info["rating"]
                    else "No rating"
                )
                review_str = (
                    f"📊{rating_info['review_count']} reviews"
                    if rating_info["review_count"]
                    else "No review count"
                )
                print(f"   {i}. {result.title}")
                print(f"      {rating_str} | {review_str}")
                print(f"      🔗 {result.url}")

        print(f"{'='*100}")

        # Show complete raw response if in enhanced mode
        if self.enhanced_mode and results:
            print(f"\n🔍 COMPLETE RAW RESPONSE ANALYSIS")
            print(f"{'='*100}")
            print("📋 All available fields across all results:")
            all_fields = set()
            for result in results:
                if hasattr(result, "parsed_data"):
                    all_fields.update(result.parsed_data.keys())

            for field in sorted(all_fields):
                print(f"   - {field}")

            print(f"\n📊 Field frequency across {len(results)} results:")
            field_counts = {}
            for result in results:
                if hasattr(result, "parsed_data"):
                    for field in result.parsed_data.keys():
                        field_counts[field] = field_counts.get(field, 0) + 1

            for field, count in sorted(field_counts.items()):
                print(f"   {field}: {count}/{len(results)} results")

            print(f"{'='*100}")

    def print_structured_results(self, structured_results: BusinessReviewResults):
        """Print structured results as JSON"""
        print(f"\n🎯 STRUCTURED RATING DATA (JSON)")
        print(f"{'='*100}")
        print(structured_results.to_json())
        print(f"{'='*100}")

        # Also print a summary
        print(f"\n📊 STRUCTURED RESULTS SUMMARY:")
        print(f"   🏢 Business: {structured_results.business_name}")
        print(f"   📍 Location: {structured_results.location}")
        print(f"   🔍 Total Results: {structured_results.total_results}")
        print(
            f"   ⭐ Results with Ratings: {len(structured_results.results_with_ratings)}"
        )
        print(f"   📋 Search Query: {structured_results.search_query}")
        print(f"{'='*100}")

    async def get_business_review_data(
        self, business_name: str, location: str, max_results: int = 20
    ) -> Dict[str, Any]:
        """
        Get business review data in a format suitable for integration with researcher.py
        Returns a dictionary with review site data organized by source
        """
        try:
            # Search for reviews
            results = await self.search_business_reviews(
                business_name=business_name, location=location, max_results=max_results
            )

            # Collect structured data
            structured_results = self.collect_rating_data(
                results, business_name, location
            )

            # Organize by source for the new JSON structure
            review_data = {}

            for rating_result in structured_results.results_with_ratings:
                source_name = rating_result.source_name.lower()

                # Normalize source names
                source_mapping = {
                    "yelp": "yelp",
                    "angi": "angi",
                    "homeadvisor": "homeadvisor",
                    "tripadvisor": "tripadvisor",
                }

                normalized_source = source_mapping.get(source_name, source_name)

                if normalized_source not in review_data:
                    review_data[normalized_source] = {}

                # Add rating and review count if available
                if rating_result.rating is not None:
                    review_data[normalized_source]["rating"] = rating_result.rating
                if rating_result.review_count is not None:
                    review_data[normalized_source][
                        "review_count"
                    ] = rating_result.review_count

                # Add source link
                if rating_result.source_link:
                    review_data[normalized_source][
                        "source_link"
                    ] = rating_result.source_link

                # We don't extract individual reviews in this implementation
                # but the structure is ready for it

            return review_data

        except Exception as e:
            print(f"❌ Error getting business review data: {e}")
            return {}
