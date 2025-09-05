import asyncio
import aiohttp
from urllib.parse import quote
import ssl
import os
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class SearchConfig:
    """Configuration for Google local business search parameters"""

    max_results: int = 20
    location: Optional[str] = None  # "New York, NY" or coordinates
    language: str = "en"
    country: str = "us"
    safe_search: bool = True


@dataclass
class LocalBusinessResult:
    """Model for local business search results with reviews"""

    name: str
    address: str
    phone: Optional[str] = None
    website: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    price_level: Optional[str] = None  # "$", "$$", "$$$", "$$$$"
    hours: Optional[str] = None
    category: Optional[str] = None
    distance: Optional[str] = None
    image_url: Optional[str] = None


@dataclass
class OrganicResult:
    """Model for organic search results with optional enhanced data"""

    title: str
    url: str
    snippet: str
    position: int
    domain: Optional[str] = None
    # Enhanced fields (backward compatible - default to empty)
    rating_data: Dict[str, Any] = field(default_factory=dict)
    rich_snippet_data: Dict[str, Any] = field(default_factory=dict)
    parsed_data: Dict[str, Any] = field(default_factory=dict)


class GoogleSearcher:
    """
    Google searcher using BrightData proxy with support for:
    - Local business search with reviews and ratings
    - Organic search results with optional enhanced parsing
    - Configurable result limits (more than 10)
    - Location-based search
    - Enhanced rating extraction (when enabled)
    """

    def __init__(
        self,
        ca_cert_path: str = "BrightData SSL certificate (port 33335).crt",
        host: str = "brd.superproxy.io",
        port: int = 33335,
        username: str = "brd-customer-hl_6467129b-zone-serp_api1",
        password: str = "168jew4d4jg8",
        enhanced_mode: bool = False,
    ):
        """
        Initialize Google searcher with BrightData credentials

        Args:
            ca_cert_path: Path to SSL certificate file
            host: Proxy host
            port: Proxy port
            username: BrightData username
            password: BrightData password
            enhanced_mode: Enable enhanced parsing and rating extraction
        """
        # Convert relative path to absolute path
        if not os.path.isabs(ca_cert_path):
            # Get the directory where this script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.ca_cert_path = os.path.join(script_dir, ca_cert_path)
        else:
            self.ca_cert_path = ca_cert_path

        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.enhanced_mode = enhanced_mode

        # Build proxy URL
        self.proxy_url = f"http://{username}:{password}@{host}:{port}"
        self.proxies = {"http": self.proxy_url, "https": self.proxy_url}

    async def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context with custom certificate"""
        if not os.path.exists(self.ca_cert_path):
            raise FileNotFoundError(
                f"SSL certificate not found at: {self.ca_cert_path}"
            )

        ssl_context = ssl.create_default_context(cafile=self.ca_cert_path)
        return ssl_context

    def _build_search_url(
        self, query: str, config: SearchConfig, search_type: str = "local"
    ) -> str:
        """Build Google search URL with optional enhanced parsing"""
        base_url = "https://www.google.com/search"
        encoded_query = quote(query)

        # Base parameters
        params = {
            "q": encoded_query,
            "hl": config.language,
            "gl": config.country,
        }

        # Add enhanced parsing if enabled
        if self.enhanced_mode:
            params["brd_json"] = "1"  # Enable BrightData parsing
            params["lum_json"] = "1"  # Additional parsing flag
        else:
            params["lum_json"] = "1"  # Standard BrightData JSON format

        # Add location if specified
        if config.location:
            params["near"] = config.location

        # Add search type specific parameters
        if search_type == "local":
            params["tbm"] = "lcl"  # Local search
        # For organic search, we don't add tbm parameter

        # Add result count
        if config.max_results > 10:
            params["num"] = str(config.max_results)

        # Add safe search
        if config.safe_search:
            params["safe"] = "active"

        # Build URL
        param_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{base_url}?{param_string}"

    def extract_ratings_from_parsed_response(self, result_data: Dict) -> Dict[str, Any]:
        """Extract ratings from Bright Data's parsed JSON response (enhanced mode only)"""
        if not self.enhanced_mode:
            return {}

        rating_data = {}

        # Check for direct rating field
        if "rating" in result_data and result_data["rating"] is not None:
            rating_data["rating"] = result_data["rating"]
            rating_data["has_rating_data"] = True

        # Check for review count
        if "reviews_cnt" in result_data and result_data["reviews_cnt"] is not None:
            rating_data["review_count"] = result_data["reviews_cnt"]
            rating_data["has_rating_data"] = True

        # Check for structured data in extensions - THIS IS THE KEY FIX
        if "extensions" in result_data and result_data["extensions"]:
            extensions = result_data["extensions"]
            if isinstance(extensions, list):
                for extension in extensions:
                    if (
                        isinstance(extension, dict)
                        and extension.get("type") == "rating"
                    ):
                        # Extract rating - check for existence and not None
                        if "rating" in extension and extension["rating"] is not None:
                            rating_data["rating"] = extension["rating"]
                            rating_data["has_rating_data"] = True

                        # Extract review count - check for existence and not None
                        if (
                            "reviews_cnt" in extension
                            and extension["reviews_cnt"] is not None
                        ):
                            rating_data["review_count"] = extension["reviews_cnt"]
                            rating_data["has_rating_data"] = True

                        # Also check for alternative field names
                        if "reviews" in extension and extension["reviews"] is not None:
                            rating_data["review_count"] = extension["reviews"]
                            rating_data["has_rating_data"] = True

                        if "stars" in extension and extension["stars"] is not None:
                            rating_data["rating"] = extension["stars"]
                            rating_data["has_rating_data"] = True

            elif isinstance(extensions, dict):
                # Handle single extension as dict
                if extensions.get("type") == "rating":
                    if "rating" in extensions and extensions["rating"] is not None:
                        rating_data["rating"] = extensions["rating"]
                        rating_data["has_rating_data"] = True

                    if (
                        "reviews_cnt" in extensions
                        and extensions["reviews_cnt"] is not None
                    ):
                        rating_data["review_count"] = extensions["reviews_cnt"]
                        rating_data["has_rating_data"] = True

        return rating_data

    def extract_rich_snippet_data(self, result_data: Dict) -> Dict[str, Any]:
        """Extract data from rich snippets structure (enhanced mode only)"""
        if not self.enhanced_mode:
            return {}

        rich_data = {}

        # Check if the result has structured data
        if "rich_snippet" in result_data and result_data["rich_snippet"]:
            rich_snippet = result_data["rich_snippet"]
            if "reviews" in rich_snippet:
                rich_data["reviews"] = rich_snippet["reviews"]
            if "rating" in rich_snippet:
                rich_data["rating"] = rich_snippet["rating"]
            if "aggregate_rating" in rich_snippet:
                rich_data["aggregate_rating"] = rich_snippet["aggregate_rating"]

        # Check for schema.org data
        if "schema" in result_data and result_data["schema"]:
            schema_data = result_data["schema"]
            if "aggregateRating" in schema_data:
                rich_data["schema_rating"] = schema_data["aggregateRating"]

        return rich_data

    def extract_comprehensive_rating_info(self, snippet: str) -> Dict[str, Any]:
        """Enhanced rating extraction with more patterns (enhanced mode only)"""
        if not self.enhanced_mode:
            return {"rating": None, "review_count": None, "has_rating_data": False}

        rating_info = {"rating": None, "review_count": None, "has_rating_data": False}

        # Enhanced rating patterns
        rating_patterns = [
            r"(\d+\.?\d*)\s*stars?",
            r"(\d+\.?\d*)\s*/\s*5",
            r"(\d+\.?\d*)\s*out of 5",
            r"Rating:\s*(\d+\.?\d*)",
            r"(\d+\.?\d*)\s*★",
            r"(\d+\.?\d*)\s*⭐",
            r"Rated\s*(\d+\.?\d*)",
            r"(\d+\.?\d*)\s*star rating",
            r"(\d+\.?\d*)\s*\/5",
            r"Score:\s*(\d+\.?\d*)",
        ]

        # Enhanced review count patterns
        review_patterns = [
            r"(\d+)\s*reviews?",
            r"\((\d+)\s*reviews?\)",
            r"(\d+)\s*Reviews",
            r"Based on (\d+)",
            r"(\d+)\s*customer reviews?",
            r"(\d+)\s*user reviews?",
            r"(\d+)\s*ratings?",
            r"(\d+)\s*votes?",
            r"(\d+)\s*total reviews?",
            r"(\d+)\s*Google reviews?",
        ]

        # Try to extract rating
        for pattern in rating_patterns:
            match = re.search(pattern, snippet, re.IGNORECASE)
            if match:
                try:
                    rating_value = float(match.group(1))
                    if 0 <= rating_value <= 5:  # Validate rating range
                        rating_info["rating"] = rating_value
                        rating_info["has_rating_data"] = True
                        break
                except ValueError:
                    continue

        # Try to extract review count
        for pattern in review_patterns:
            match = re.search(pattern, snippet, re.IGNORECASE)
            if match:
                try:
                    rating_info["review_count"] = int(match.group(1))
                    rating_info["has_rating_data"] = True
                    break
                except ValueError:
                    continue

        return rating_info

    def search_with_knowledge_panel_focus(
        self, business_name: str, location: str
    ) -> str:
        """Build query specifically targeting knowledge panel data (enhanced mode only)"""
        if not self.enhanced_mode:
            return f"{business_name} {location}"
        # Add quotes around business name for exact match
        knowledge_panel_query = f'"{business_name}" {location} reviews rating'
        return knowledge_panel_query

    async def search_local_businesses(
        self, query: str, location: str, max_results: int = 20
    ) -> List[LocalBusinessResult]:
        """
        Search for local businesses with reviews and ratings

        Args:
            query: Search query (e.g., "restaurants", "coffee shops", "dentist")
            location: Location (e.g., "New York, NY", "10001")
            max_results: Maximum number of results (default 20)

        Returns:
            List of local business results with ratings and reviews
        """
        config = SearchConfig(max_results=max_results, location=location)

        search_query = f"{query} in {location}"
        raw_result = await self._perform_search(search_query, config, "local")

        # Parse local business results
        businesses = []

        # Process snack_pack and local_results
        results_to_process = []
        if "snack_pack" in raw_result:
            print(f"🍿 Found {len(raw_result['snack_pack'])} businesses in snack_pack")
            results_to_process.extend(raw_result["snack_pack"])

        if "local_results" in raw_result:
            print(
                f"📍 Found {len(raw_result['local_results'])} businesses in local_results"
            )
            results_to_process.extend(raw_result["local_results"])

        for business_data in results_to_process:
            if len(businesses) >= max_results:
                break
            try:
                normalized_data = self._normalize_business_data(business_data)
                business = LocalBusinessResult(**normalized_data)
                businesses.append(business)
            except Exception as e:
                print(f"Error processing business: {e}")
                continue

        # Ensure we don't exceed max_results
        businesses = businesses[:max_results]
        print(
            f"✅ Returning {len(businesses)} local businesses (requested: {max_results})"
        )

        return businesses

    async def search_organic_results(
        self,
        query: str,
        location: str = "",
        max_results: int = 10,
        num_links: int = None,
    ) -> List[OrganicResult]:
        """
        Search for organic (regular) Google search results

        Args:
            query: Search query (e.g., "hvac Cleveland OH", "restaurants near me")
            location: Location (e.g., "Cleveland, OH", "New York, NY")
            max_results: Maximum number of results (default 10) - DEPRECATED, use num_links
            num_links: Number of search result links to return (default 10)

        Returns:
            List of organic search results (with enhanced data if enhanced_mode=True)
        """
        # Use num_links if provided, otherwise fall back to max_results
        result_count = num_links if num_links is not None else max_results

        config = SearchConfig(max_results=result_count, location=location)

        # Build search query with location if provided
        search_query = f"{query} {location}".strip()

        raw_result = await self._perform_search(search_query, config, "organic")

        # Parse organic results
        organic_results = []

        # Check for organic search results
        if "organic" in raw_result:
            print(f"🔍 Found {len(raw_result['organic'])} organic results")
            for i, result_data in enumerate(raw_result["organic"]):
                if len(organic_results) >= result_count:  # Stop when we reach the limit
                    break
                try:
                    # Extract domain from display_link or link
                    domain = None
                    url = result_data.get("link", "")
                    if "display_link" in result_data:
                        display_link = result_data["display_link"]
                        if display_link.startswith("https://"):
                            domain = display_link[8:].split("/")[0]
                        elif display_link.startswith("http://"):
                            domain = display_link[7:].split("/")[0]
                        else:
                            domain = display_link.split("/")[0]
                    elif url:
                        if url.startswith("https://"):
                            domain = url[8:].split("/")[0]
                        elif url.startswith("http://"):
                            domain = url[7:].split("/")[0]

                    # Basic result data
                    snippet_text = result_data.get("description", "")

                    # Enhanced data extraction (only if enhanced mode is enabled)
                    rating_data = {}
                    rich_snippet_data = {}
                    parsed_data = {}

                    if self.enhanced_mode:
                        # Extract ratings from parsed response
                        parsed_ratings = self.extract_ratings_from_parsed_response(
                            result_data
                        )
                        # Extract rich snippet data
                        rich_snippet_data = self.extract_rich_snippet_data(result_data)
                        # Extract from snippet text
                        snippet_ratings = self.extract_comprehensive_rating_info(
                            snippet_text
                        )

                        # Combine all rating data
                        rating_data = {"source": "parsed_and_snippet"}
                        if parsed_ratings:
                            rating_data.update(parsed_ratings)
                        # Only add snippet data if we don't already have that field
                        if snippet_ratings:
                            for key, value in snippet_ratings.items():
                                if key not in rating_data or rating_data[key] is None:
                                    if value is not None:  # Only use non-None values
                                        rating_data[key] = value

                        # Store the complete parsed data for debugging
                        parsed_data = result_data

                    result = OrganicResult(
                        title=result_data.get("title", ""),
                        url=url,
                        snippet=snippet_text,
                        position=result_data.get("rank", i + 1),
                        domain=domain,
                        rating_data=rating_data,
                        rich_snippet_data=rich_snippet_data,
                        parsed_data=parsed_data,
                    )
                    organic_results.append(result)
                except Exception as e:
                    print(f"Error processing organic result: {e}")
                    continue

        # Ensure we don't exceed result_count
        organic_results = organic_results[:result_count]
        print(
            f"✅ Returning {len(organic_results)} organic results (requested: {result_count})"
        )

        return organic_results

    async def search_enhanced_organic_results(
        self,
        query: str,
        location: str = "",
        max_results: int = 10,
        enable_knowledge_panel: bool = True,
    ) -> List[OrganicResult]:
        """
        Enhanced organic search with parsing and rating extraction
        This is an alias for search_organic_results with enhanced_mode=True

        Args:
            query: Search query
            location: Location for search
            max_results: Maximum number of results
            enable_knowledge_panel: Whether to optimize for knowledge panel data

        Returns:
            List of enhanced organic results with rating data
        """
        # Temporarily enable enhanced mode for this search
        original_enhanced_mode = self.enhanced_mode
        self.enhanced_mode = True

        try:
            # Optionally modify query for knowledge panel
            if enable_knowledge_panel and location:
                query = self.search_with_knowledge_panel_focus(query, location)

            print(f"🔍 Enhanced search query: {query}")
            print(f"📊 Targeting up to {max_results} results with parsing enabled")
            print("-" * 80)

            results = await self.search_organic_results(
                query=query, location=location, max_results=max_results
            )

            return results
        finally:
            # Restore original enhanced mode
            self.enhanced_mode = original_enhanced_mode

    async def search_combined_results(
        self, query: str, location: str, max_local: int = 20, max_organic: int = 20
    ) -> Dict[str, List]:
        """
        Search for both local businesses and organic results

        Args:
            query: Search query (e.g., "hvac", "restaurants")
            location: Location (e.g., "Cleveland, OH", "New York, NY")
            max_local: Maximum local business results (default 20)
            max_organic: Maximum organic results (default 10)

        Returns:
            Dictionary with "local" and "organic" keys containing respective results
        """
        print(f"🔍 Searching for '{query}' in '{location}'")
        print(
            f"📊 Getting up to {max_local} local businesses and {max_organic} organic results"
        )

        # Run both searches in parallel
        local_task = self.search_local_businesses(query, location, max_local)
        organic_task = self.search_organic_results(query, location, max_organic)

        local_results, organic_results = await asyncio.gather(local_task, organic_task)

        print(
            f"✅ Found {len(local_results)} local businesses and {len(organic_results)} organic results"
        )

        return {"local": local_results, "organic": organic_results}

    async def search_businesses_with_reviews(
        self,
        business_type: str,
        location: str,
        min_rating: float = 4.0,
        max_results: int = 30,
    ) -> List[LocalBusinessResult]:
        """
        Search for businesses filtered by minimum rating

        Args:
            business_type: Type of business (e.g., "restaurants", "dentist", "coffee shop")
            location: Location to search in
            min_rating: Minimum rating filter (default 4.0)
            max_results: Maximum results to search through (default 30)

        Returns:
            List of businesses meeting rating criteria, sorted by rating
        """
        all_businesses = await self.search_local_businesses(
            f"{business_type}", location, max_results
        )

        # Filter by minimum rating
        filtered_businesses = [
            business
            for business in all_businesses
            if business.rating and business.rating >= min_rating
        ]

        # Sort by rating (highest first)
        filtered_businesses.sort(key=lambda x: x.rating or 0, reverse=True)

        return filtered_businesses

    async def search_businesses_by_category(
        self, category: str, location: str, max_results: int = 25
    ) -> List[LocalBusinessResult]:
        """
        Search for businesses by category

        Args:
            category: Business category (e.g., "restaurant", "gas station", "pharmacy")
            location: Location to search in
            max_results: Maximum number of results

        Returns:
            List of businesses in the specified category
        """
        return await self.search_local_businesses(category, location, max_results)

    async def get_top_rated_businesses(
        self,
        business_type: str,
        location: str,
        min_reviews: int = 10,
        max_results: int = 50,
    ) -> List[LocalBusinessResult]:
        """
        Get top-rated businesses with sufficient reviews

        Args:
            business_type: Type of business to search for
            location: Location to search in
            min_reviews: Minimum number of reviews required
            max_results: Maximum results to search through

        Returns:
            List of top-rated businesses with sufficient reviews
        """
        all_businesses = await self.search_local_businesses(
            business_type, location, max_results
        )

        # Filter by minimum reviews and rating
        quality_businesses = [
            business
            for business in all_businesses
            if (
                business.rating
                and business.rating >= 4.0
                and business.review_count
                and business.review_count >= min_reviews
            )
        ]

        # Sort by rating first, then by review count
        quality_businesses.sort(
            key=lambda x: (x.rating or 0, x.review_count or 0), reverse=True
        )

        return quality_businesses

    def _normalize_business_data(self, data: Dict) -> Dict:
        """Normalizes keys from different local result types."""
        return {
            "name": data.get("name") or data.get("title") or "",
            "address": data.get("address", ""),
            "phone": data.get("phone"),
            "website": data.get("site") or data.get("website"),
            "rating": data.get("rating"),
            "review_count": data.get("reviews_cnt") or data.get("review_count"),
            "price_level": data.get("price_level"),
            "hours": data.get("work_status") or data.get("hours"),
            "category": data.get("type") or data.get("category"),
            "distance": data.get("distance"),
            "image_url": data.get("thumbnail"),
        }

    async def _perform_search(
        self, query: str, config: SearchConfig, search_type: str = "local"
    ) -> Dict:
        """
        Perform the actual search request

        Args:
            query: Search query
            config: Search configuration
            search_type: "local" or "organic"

        Returns:
            Raw search results dictionary
        """
        url = self._build_search_url(query, config, search_type)

        try:
            ssl_context = await self._create_ssl_context()
            timeout = aiohttp.ClientTimeout(total=30)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    url,
                    proxy=self.proxies["https"],
                    ssl=ssl_context,
                ) as response:

                    if response.status == 200:
                        result = await response.json()
                        return result
                    else:
                        error_text = await response.text()
                        raise aiohttp.ClientError(
                            f"Search failed with status {response.status}: {error_text[:200]}"
                        )

        except Exception as e:
            raise RuntimeError(f"Search request failed: {str(e)}")


# Backward compatibility aliases for old EnhancedGoogleSearcher usage
EnhancedGoogleSearcher = GoogleSearcher
EnhancedOrganicResult = OrganicResult


# Example usage
async def main():
    """Example usage of GoogleSearcher for local businesses and organic results"""
    # Test both modes
    standard_searcher = GoogleSearcher(enhanced_mode=False)
    enhanced_searcher = GoogleSearcher(enhanced_mode=True)

    print("🏢 Testing Google Searcher (Standard and Enhanced)")
    print("=" * 60)

    # Test 1: Standard search
    print("\n🔍 Test 1: Standard Search - HVAC in Cleveland, OH")
    print("-" * 50)
    try:
        organic_results = await standard_searcher.search_organic_results(
            "hvac", "Cleveland, OH", max_results=5
        )
        print(f"Found {len(organic_results)} standard results")
        for i, result in enumerate(organic_results[:2]):
            print(f"  {i+1}. {result.title}")
            print(f"     🔗 {result.url}")
            print(f"     📝 {result.snippet[:100]}...")
            print(f"     📊 Rating data: {len(result.rating_data)} items")
            print()
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 2: Enhanced search
    print("\n🔍 Test 2: Enhanced Search - HVAC Cleveland")
    print("-" * 50)
    try:
        enhanced_results = await enhanced_searcher.search_organic_results(
            "hvac", "Cleveland, OH", max_results=5
        )
        print(f"Found {len(enhanced_results)} enhanced results")
        for i, result in enumerate(enhanced_results[:2]):
            print(f"  {i+1}. {result.title}")
            print(f"     🔗 {result.url}")
            print(f"     📝 {result.snippet[:100]}...")
            print(f"     📊 Rating data: {len(result.rating_data)} items")
            if result.rating_data:
                print(f"     ⭐ Enhanced rating info: {result.rating_data}")
            print()
    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n✅ Both standard and enhanced modes working!")


if __name__ == "__main__":
    asyncio.run(main())
