#!/usr/bin/env python3
"""
Google Business Review Fetcher Script
Uses BrightData proxy to fetch Google business reviews and data

ACTUAL API FIELD STRUCTURE (confirmed via test_snack_pack_fields.py):
================================================================

AVAILABLE FIELDS from snack_pack:
- name: Business name (str)
- cid: Customer ID for Google reviews (str)
- rating: Business rating (float, e.g., 4.8)
- reviews_cnt: Review count (int, e.g., 3000)
- address: Business address (str, WARNING: may contain descriptive text)
- site: Business website URL (str, e.g., "http://example.com/")
- phone: Phone number (str, only available for some businesses)
- type: Business category (str, e.g., "Plumber")
- work_status: Hours info (str, e.g., "Open 24 hours")
- tags: Service tags (list, e.g., ["Onsite services"])
- maps_link: Google Maps action link (str)
- rank: Local ranking (int)
- global_rank: Global ranking (int)

NOT AVAILABLE in snack_pack:
- latitude/longitude coordinates
- domain field (separate from site URL)

ADDRESS QUALITY ISSUE:
=====================
The 'address' field sometimes contains descriptive text instead of proper addresses:
✅ Good: "61 9th Ave", "2810 S Figueroa St", "4555 S Western Blvd"
❌ Poor: "35+ years in business ⋅ Warrensville Heights, OH", "Akron, OH"

This script includes address quality detection to flag problematic addresses.
"""

import asyncio
import aiohttp
from urllib.parse import quote
import ssl
import os
from typing import Dict, List, Optional
import json
import re
from pydantic import BaseModel
import xml.etree.ElementTree as ET

# Import the Gemini client for LLM-based business selection
try:
    from clients.gemini_client import GeminiClient

    GEMINI_AVAILABLE = True
except ImportError:
    print("⚠️ Gemini client not available. LLM business matching will not work.")
    GEMINI_AVAILABLE = False

# Import config for API keys
try:
    import config

    CONFIG_AVAILABLE = True
except ImportError:
    print("⚠️ Config not available for API keys")
    CONFIG_AVAILABLE = False


class ReviewConfig(BaseModel):
    """Configuration for Google review search parameters"""

    sort: str = "qualityScore"  # qualityScore, newestFirst, ratingHigh, ratingLow
    filter_keyword: Optional[str] = None  # Filter reviews containing specific keyword
    max_results: int = 20
    language: str = "en"
    country: str = "us"


class ReviewResult(BaseModel):
    """Model for individual review data"""

    author_name: str
    author_url: Optional[str] = None
    author_image: Optional[str] = None
    rating: Optional[int] = None
    review_text: Optional[str] = None
    review_date: Optional[str] = None
    review_timestamp: Optional[int] = None
    owner_response: Optional[str] = None
    owner_response_date: Optional[str] = None
    helpful_count: Optional[int] = None
    review_id: Optional[str] = None


class BusinessReviewsResult(BaseModel):
    """Model for complete business reviews result"""

    business_name: str
    business_fid: str
    total_rating: Optional[float] = None
    total_review_count: Optional[int] = None
    search_url: Optional[str] = (
        None  # Original Google search URL that found the business
    )
    business_address: Optional[str] = None
    address_quality: Optional[str] = (
        None  # "good" or "poor" - indicates if address is descriptive text
    )
    business_website: Optional[str] = None
    business_domain: Optional[str] = None
    business_phone: Optional[str] = None
    business_latitude: Optional[float] = None
    business_longitude: Optional[float] = None
    business_type: Optional[str] = (
        None  # Business category from Google (e.g., "Plumber")
    )
    reviews: List[ReviewResult] = []
    reviews_summary: Optional[str] = None  # Summary of all reviews using LLM


class GoogleBusinessResearcher:
    """
    Google business researcher using BrightData proxy with LLM-enhanced business selection.
    Automatically loads Gemini API keys from config.py and uses LLM for business matching.
    Returns None if no business match is found.
    """

    def __init__(
        self,
        ca_cert_path: str = "BrightData SSL certificate (port 33335).crt",
        host: str = "brd.superproxy.io",
        port: int = 33335,
        username: str = "brd-customer-hl_6467129b-zone-serp_api1",
        password: str = "168jew4d4jg8",
    ):
        """
        Initialize Google review fetcher with BrightData credentials and automatic Gemini setup

        Args:
            ca_cert_path: Path to SSL certificate file
            host: Proxy host
            port: Proxy port
            username: BrightData username
            password: BrightData password
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

        # Build proxy URL
        self.proxy_url = f"http://{username}:{password}@{host}:{port}"
        self.proxies = {"http": self.proxy_url, "https": self.proxy_url}

        # Automatically load Gemini API keys from config
        gemini_keys = []
        if CONFIG_AVAILABLE:
            for i in range(1, 10):  # Keys 1-9
                try:
                    key = getattr(config, f"GEMINI_API_KEY_{i}")
                    if key and key != "":
                        gemini_keys.append(key)
                except AttributeError:
                    break
            print(f"🔑 Loaded {len(gemini_keys)} Gemini API keys from config")

        # Initialize LLM client
        self.llm_client = None
        if GEMINI_AVAILABLE and gemini_keys:
            try:
                self.llm_client = GeminiClient(
                    api_keys=gemini_keys, model_name="gemini-2.0-flash"
                )
                print(
                    "🤖 LLM-enhanced business selection enabled with Gemini 2.0 Flash"
                )
            except Exception as e:
                print(f"⚠️ Failed to initialize LLM client: {e}")
                self.llm_client = None
        else:
            print("⚠️ LLM client unavailable - no Gemini keys or client not available")

    async def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context with custom certificate"""
        if not os.path.exists(self.ca_cert_path):
            raise FileNotFoundError(
                f"SSL certificate not found at: {self.ca_cert_path}"
            )

        ssl_context = ssl.create_default_context(cafile=self.ca_cert_path)
        return ssl_context

    def _build_search_url(
        self, business_name: str, location: str = "", use_local_search: bool = True
    ) -> str:
        """Build Google search URL to find business FID"""
        query = f"{business_name} {location}".strip()
        encoded_query = quote(query)

        # Parameters for finding business in search results
        params = {
            "q": encoded_query,
            "hl": "en",
            "gl": "us",
            "brd_json": "1",  # Get JSON response
        }

        # Try local search first (more likely to have FID)
        if use_local_search:
            params["tbm"] = "lcl"  # Local search

        # Build URL
        param_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"https://www.google.com/search?{param_string}"

    def _build_reviews_url(self, fid: str, config: ReviewConfig) -> str:
        """Build Google reviews URL using FID"""
        base_url = "https://www.google.com/reviews"

        params = {
            "fid": fid,
            "brd_json": "1",  # Get JSON response
            "hl": config.language,
            "sort": config.sort,
            "num": str(config.max_results),
        }

        # Add filter if specified
        if config.filter_keyword:
            params["filter"] = config.filter_keyword

        # Build URL
        param_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{base_url}?{param_string}"

    async def _select_business_with_llm(
        self, search_name: str, businesses: List[Dict]
    ) -> Optional[Dict]:
        """
        Use LLM to select the best matching business from search results

        Args:
            search_name: The business name we're searching for
            businesses: List of business results from snack_pack

        Returns:
            The selected business or None if LLM selection fails
        """
        if not self.llm_client or not businesses:
            return None

        try:
            # Format businesses for LLM prompt
            business_list = []
            for i, business in enumerate(businesses):
                name = business.get("name", "Unknown")
                address = business.get("address", "No address")
                rating = business.get("rating", "No rating")
                review_count = business.get("reviews_cnt", "No review count")

                business_list.append(
                    f'Index {i}: "{name}" | Address: {address} | Rating: {rating} | Reviews: {review_count}'
                )

            formatted_businesses = "\n".join(business_list)

            # Create prompt for LLM
            prompt = f"""You are helping to identify the correct business from a list of search results.

SEARCH TARGET: "{search_name}"

AVAILABLE BUSINESSES:
{formatted_businesses}

TASK: Select the business that best matches the search target "{search_name}". Consider:
1. Exact name match (highest priority)
2. Similar business names with different formatting
3. Business type consistency
4. Location relevance if applicable

IMPORTANT: You must respond with ONLY the index number of the best matching business wrapped in XML tags.

Format your response exactly as: <business>INDEX_NUMBER</business>

Example: <business>0</business> or <business>2</business>

If no business is a reasonable match, respond with: <business>-1</business>"""

            print(f"🤖 Asking LLM to select business for: '{search_name}'")

            # Get LLM response in a non-blocking way
            response = await asyncio.to_thread(
                self.llm_client.ask, prompt, disable_thinking=True
            )
            print(f"🤖 LLM Response: {response.strip()}")

            # Parse XML response
            selected_index = self._parse_business_selection(response)

            if selected_index is not None and 0 <= selected_index < len(businesses):
                selected_business = businesses[selected_index]
                print(
                    f"🎯 LLM selected: '{selected_business.get('name', 'Unknown')}' (Index {selected_index})"
                )
                return selected_business
            elif selected_index == -1:
                print("🤖 LLM determined no good match exists")
                return None
            else:
                print(f"⚠️ LLM returned invalid index: {selected_index}")
                return None

        except Exception as e:
            print(f"❌ LLM business selection failed: {e}")
            return None

    def _parse_business_selection(self, llm_response: str) -> Optional[int]:
        """
        Parse the LLM response to extract the selected business index

        Args:
            llm_response: Raw response from LLM

        Returns:
            Selected business index or None if parsing fails
        """
        try:
            # First try XML parsing
            try:
                # Remove any extra whitespace and find the business tag
                cleaned_response = llm_response.strip()

                # Try to extract using regex first (more robust)
                pattern = r"<business>(-?\d+)</business>"
                match = re.search(pattern, cleaned_response, re.IGNORECASE)

                if match:
                    return int(match.group(1))

                # Fallback to XML parsing
                root = ET.fromstring(cleaned_response)
                if root.tag.lower() == "business":
                    return int(root.text.strip())

                # Look for business tag within the response
                business_elem = root.find(".//business")
                if business_elem is not None:
                    return int(business_elem.text.strip())

            except ET.ParseError:
                # If XML parsing fails, try regex extraction
                pattern = r"<business>(-?\d+)</business>"
                match = re.search(pattern, llm_response, re.IGNORECASE)
                if match:
                    return int(match.group(1))

            # Last resort: look for any number that might be the index
            numbers = re.findall(r"-?\d+", llm_response)
            if numbers:
                return int(numbers[0])

            return None

        except (ValueError, AttributeError) as e:
            print(f"❌ Failed to parse LLM response: {e}")
            return None

    async def _find_best_business_match(
        self, search_name: str, businesses: List[Dict]
    ) -> Optional[Dict]:
        """
        Find the best matching business from search results using LLM only.
        Returns None if no good match is found.

        Args:
            search_name: The business name we're searching for
            businesses: List of business results from snack_pack

        Returns:
            The best matching business or None if no match found
        """
        if not businesses:
            return None

        # Only use LLM selection - no traditional fallback
        if not self.llm_client:
            print("❌ No LLM client available - cannot match businesses")
            return None

        print(f"🤖 Using LLM-based business selection...")
        llm_result = await self._select_business_with_llm(search_name, businesses)

        if llm_result:
            return llm_result
        else:
            print(f"🤖 LLM determined no good match exists for '{search_name}'")
            return None

    def _convert_cid_to_fid(self, cid: str) -> Optional[str]:
        """
        Convert CID to FID format for BrightData Reviews API

        Args:
            cid: Customer ID in decimal format

        Returns:
            FID in proper format or None if conversion fails
        """
        try:
            # Convert decimal CID to hexadecimal
            cid_int = int(cid)
            cid_hex = format(cid_int, "x")

            # For BrightData, try different FID formats
            # Format 1: Use CID directly (some APIs accept this)
            fid_formats = [
                cid,  # Try decimal CID directly
                f"0x{cid_hex}",  # Hexadecimal format
                f"0x0:0x{cid_hex}",  # Full FID format with placeholder
            ]

            print(f"🔄 CID conversion: {cid} -> hex: {cid_hex}")
            print(f"🔄 Trying FID formats: {fid_formats}")

            # Return the most likely format (hex format with prefix)
            return f"0x0:0x{cid_hex}"

        except Exception as e:
            print(f"❌ Error converting CID to FID: {e}")
            return None

    async def _fetch_reviews_by_fid(
        self, fid: str, config: ReviewConfig, max_retries: int = 3
    ) -> Dict:
        """
        Fetch reviews using the business FID with a retry mechanism.

        Args:
            fid: Feature ID of the business
            config: Review configuration
            max_retries: Number of times to retry on failure

        Returns:
            Raw reviews data from Google
        """
        reviews_url = self._build_reviews_url(fid, config)
        last_error = None

        for attempt in range(max_retries):
            try:
                ssl_context = await self._create_ssl_context()
                timeout = aiohttp.ClientTimeout(total=30)

                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(
                        reviews_url,
                        proxy=self.proxies["https"],
                        ssl=ssl_context,
                    ) as response:

                        if response.status == 200:
                            result = await response.json()
                            return result
                        else:
                            error_text = await response.text()
                            last_error = aiohttp.ClientError(
                                f"Reviews fetch failed with status {response.status}: {error_text[:200]}"
                            )
                            print(
                                f"⚠️ Attempt {attempt + 1}/{max_retries} failed: {last_error}"
                            )

                # Wait before retrying
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.5 * (attempt + 1))  # Exponential backoff

            except Exception as e:
                last_error = e
                print(
                    f"⚠️ Attempt {attempt + 1}/{max_retries} failed with exception: {e}"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.5 * (attempt + 1))

        raise RuntimeError(
            f"Reviews fetch request failed after {max_retries} attempts: {last_error}"
        )

    def _parse_reviews(
        self,
        raw_data: Dict,
        business_name: str,
        fid: str,
        search_url: Optional[str] = None,
        business_rating: Optional[float] = None,
        business_review_count: Optional[int] = None,
        business_address: Optional[str] = None,
        address_quality: Optional[str] = None,
        business_website: Optional[str] = None,
        business_domain: Optional[str] = None,
        business_phone: Optional[str] = None,
        business_latitude: Optional[float] = None,
        business_longitude: Optional[float] = None,
        business_type: Optional[str] = None,
    ) -> BusinessReviewsResult:
        """
        Parse raw review data into structured format

        Args:
            raw_data: Raw JSON response from Google Reviews API
            business_name: Name of the business
            fid: Feature ID of the business
            search_url: Original search URL that found the business
            business_rating: Overall business rating from search results
            business_review_count: Total review count from search results
            business_address: Business address (may contain descriptive text)
            address_quality: Quality indicator for address ("good" or "poor")
            business_website: Business website URL
            business_domain: Business domain name
            business_phone: Business phone number
            business_latitude: GPS latitude coordinate
            business_longitude: GPS longitude coordinate
            business_type: Business category from Google (e.g., "Plumber")

        Returns:
            Structured business reviews result
        """
        reviews = []

        # Extract reviews from the response
        review_data = raw_data.get("reviews", [])
        print(f"✅ Found {len(review_data)} reviews in response")

        for review_item in review_data:
            try:
                # Extract rating from string format like "5/5" or "1/5"
                rating = None
                rating_str = review_item.get("rating", "")
                if rating_str:
                    # Extract number before the slash
                    rating_match = re.match(r"(\d+)/\d+", rating_str)
                    if rating_match:
                        rating = int(rating_match.group(1))

                # Extract reviewer information
                reviewer = review_item.get("reviewer", {})
                author_name = reviewer.get("display_name", "")
                author_url = reviewer.get("link")
                author_image = reviewer.get("profile_photo_url")

                # Create review object
                review = ReviewResult(
                    author_name=author_name,
                    author_url=author_url,
                    author_image=author_image,
                    rating=rating,
                    review_text=review_item.get(
                        "comment"
                    ),  # BrightData uses "comment" for review text
                    review_date=review_item.get(
                        "created"
                    ),  # BrightData uses "created" for date
                    review_timestamp=None,  # Not provided in this format
                    owner_response=review_item.get(
                        "review_reply"
                    ),  # BrightData uses "review_reply"
                    owner_response_date=review_item.get("review_reply_created"),
                    helpful_count=None,  # Not provided in this format
                    review_id=review_item.get("review_id"),
                )
                reviews.append(review)

            except Exception as e:
                print(f"❌ Error parsing review: {e}")
                continue

        return BusinessReviewsResult(
            business_name=business_name,
            business_fid=fid,
            total_rating=business_rating,
            total_review_count=business_review_count,
            search_url=search_url,
            business_address=business_address,
            address_quality=address_quality,
            business_website=business_website,
            business_domain=business_domain,
            business_phone=business_phone,
            business_latitude=business_latitude,
            business_longitude=business_longitude,
            business_type=business_type,
            reviews=reviews,
        )

    async def _generate_reviews_summary(
        self, business_name: str, reviews: List[ReviewResult], max_tokens: int = 2000
    ) -> Optional[str]:
        """
        Generate a comprehensive summary of Google reviews using LLM

        Args:
            business_name: Name of the business
            reviews: List of review results to summarize
            max_tokens: Maximum tokens for the summary (default 2000)

        Returns:
            Summary text or None if generation fails
        """
        if not self.llm_client or not reviews:
            return None

        try:
            print(f"🤖 Generating summary for {len(reviews)} Google reviews...")

            # Format reviews for summarization
            reviews_text = f"Google Reviews for {business_name}:\n\n"

            for i, review in enumerate(
                reviews[:20]
            ):  # Limit to first 20 reviews for context
                if review.review_text:
                    rating_stars = "⭐" * (review.rating or 0)
                    reviews_text += f"Review {i+1} ({rating_stars}):\n"
                    reviews_text += (
                        f"{review.review_text[:500]}\n"  # Truncate long reviews
                    )
                    if review.owner_response:
                        reviews_text += (
                            f"Owner Response: {review.owner_response[:300]}\n"
                        )
                    reviews_text += "\n"

            # Create comprehensive prompt for summarization
            prompt = f"""You are analyzing Google reviews for the business "{business_name}". Please create a comprehensive 3-paragraph summary that captures:

1. **Overall Customer Experience**: What customers consistently say about service quality, professionalism, and overall satisfaction
2. **Common Strengths & Praise**: Specific aspects customers frequently compliment (service quality, response time, pricing, staff, etc.)
3. **Areas of Concern & Criticism**: Any recurring issues, complaints, or areas customers mention as problems

IMPORTANT GUIDELINES:
- Write exactly 3 paragraphs
- Keep the total response under {max_tokens} tokens
- Be purely descriptive - only report what customers actually said in their reviews
- Focus on patterns and themes across multiple reviews, not isolated incidents
- Use specific details from the reviews when possible
- Do NOT include business advice, recommendations, or call-to-action language
- Do NOT lecture about what the business "should" do or what is "important"
- If there are few or no negative reviews, simply state that fact without suggesting what it means
- If there are few or no positive reviews, simply state that fact without interpretation
- Avoid phrases like "crucial," "should," "important to," or any prescriptive language

The Google reviews to analyze:

{reviews_text[:8000]}"""  # Limit input size

            summary = await asyncio.to_thread(
                self.llm_client.ask, prompt, disable_thinking=True
            )

            print(f"✅ Generated Google reviews summary ({len(summary)} characters)")
            return summary.strip()

        except Exception as e:
            print(f"❌ Error generating Google reviews summary: {e}")
            return None

    async def fetch_reviews(
        self,
        business_name: str,
        business_location: str = "",
        sort: str = "qualityScore",
        filter_keyword: Optional[str] = None,
        max_results: int = 20,
        generate_summary: bool = True,
    ) -> Optional[BusinessReviewsResult]:
        """
        Fetch Google reviews for a specific business

        Args:
            business_name: Name of the business to search for
            business_location: Location of the business (e.g., "Cleveland, OH")
            sort: Review sorting method - "qualityScore", "newestFirst", "ratingHigh", "ratingLow"
            filter_keyword: Optional keyword to filter reviews
            max_results: Maximum number of reviews to fetch (default 20)
            generate_summary: Whether to generate an LLM summary of the reviews (default True)

        Returns:
            Structured business reviews result or None if no business match found
        """
        # Step 1: Find business FID and capture business info
        print(
            f"🔍 Searching for '{business_name}' in '{business_location}' to find FID..."
        )
        try:
            fid_result = await self._find_business_fid_with_info(
                business_name, business_location
            )

            if not fid_result["fid"]:
                print(
                    f"❌ Could not find matching business: {business_name} in {business_location}"
                )
                return None

            fid = fid_result["fid"]
            business_rating = fid_result.get("rating")
            business_review_count = fid_result.get("review_count")
            search_url = fid_result.get("search_url")

            # Extract additional business data
            business_address = fid_result.get("address")
            address_quality = fid_result.get("address_quality")
            business_website = fid_result.get("website")
            business_domain = fid_result.get("domain")
            business_phone = fid_result.get("phone")
            business_latitude = fid_result.get("latitude")
            business_longitude = fid_result.get("longitude")
            business_type = fid_result.get("business_type")

            print(f"✅ Found FID: {fid}")
            if business_rating:
                print(f"⭐ Business Rating: {business_rating}/5")
            if business_review_count:
                print(f"📊 Total Reviews: {business_review_count}")
            if business_address:
                quality_indicator = "✅" if address_quality == "good" else "⚠️"
                print(f"📍 Address: {business_address} {quality_indicator}")
                if address_quality == "poor":
                    print(
                        f"    ⚠️ Address contains descriptive text, not precise location"
                    )
            if business_website:
                print(f"🌐 Website: {business_website}")
            if business_phone:
                print(f"📞 Phone: {business_phone}")
            if business_type:
                print(f"🏷️ Category: {business_type}")
            if business_latitude and business_longitude:
                print(f"🗺️ Coordinates: {business_latitude}, {business_longitude}")
            else:
                print(f"🗺️ Coordinates: Not available from snack_pack")
            if search_url:
                print(f"📄 Search URL: {search_url}")

            # Step 2: Fetch reviews using FID
            print(f"📝 Fetching reviews for {business_name}...")
            config_obj = ReviewConfig(
                sort=sort, filter_keyword=filter_keyword, max_results=max_results
            )

            raw_reviews = await self._fetch_reviews_by_fid(fid, config_obj)

            # Step 3: Parse and structure the results
            structured_result = self._parse_reviews(
                raw_reviews,
                business_name,
                fid,
                search_url,
                business_rating,
                business_review_count,
                business_address,
                address_quality,
                business_website,
                business_domain,
                business_phone,
                business_latitude,
                business_longitude,
                business_type,
            )

            # Step 4: Generate summary if requested and we have reviews
            if generate_summary and structured_result.reviews:
                reviews_summary = await self._generate_reviews_summary(
                    business_name, structured_result.reviews
                )
                structured_result.reviews_summary = reviews_summary

            print(f"✅ Successfully fetched {len(structured_result.reviews)} reviews")
            if structured_result.reviews_summary:
                print(f"📋 Generated reviews summary")

            return structured_result

        except Exception as e:
            print(f"❌ Error fetching reviews: {e}")
            return None

    async def _find_business_fid_with_info(
        self, business_name: str, location: str = ""
    ) -> Dict:
        """
        Search for business and return FID along with business info (rating, review count, search URL, address, website)

        Returns:
            Dict with fid, rating, review_count, search_url, address, website, domain, phone, latitude, longitude
        """
        # Try local search first
        search_url = self._build_search_url(
            business_name, location, use_local_search=True
        )
        print(f"🔗 Trying local search URL: {search_url}")

        result = await self._search_for_fid_with_info(search_url, business_name)
        if result["fid"]:
            result["search_url"] = search_url
            return result

        # Fallback to regular search
        print(f"🔄 Local search failed, trying regular search...")
        search_url = self._build_search_url(
            business_name, location, use_local_search=False
        )
        print(f"🔗 Trying regular search URL: {search_url}")

        result = await self._search_for_fid_with_info(search_url, business_name)
        result["search_url"] = search_url if result["fid"] else None
        return result

    async def _search_for_fid_with_info(
        self, search_url: str, original_business_name: str
    ) -> Dict:
        """
        Perform the actual search and extract FID plus business info

        Returns:
            Dict with fid, rating, review_count
        """
        try:
            ssl_context = await self._create_ssl_context()
            timeout = aiohttp.ClientTimeout(total=30)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    search_url,
                    proxy=self.proxies["https"],
                    ssl=ssl_context,
                ) as response:

                    if response.status == 200:
                        result = await response.json()

                        # Check snack_pack for business info
                        if "snack_pack" in result:
                            print(
                                f"🍿 Found snack_pack with {len(result['snack_pack'])} results"
                            )

                            # Find the best matching business and extract info
                            best_match = await self._find_best_business_match(
                                original_business_name, result["snack_pack"]
                            )
                            if best_match and "cid" in best_match:
                                cid = best_match["cid"]
                                business_rating = best_match.get("rating")
                                business_review_count = best_match.get("reviews_cnt")
                                business_name = best_match.get(
                                    "name", "Unknown Business"
                                )

                                # Extract additional business data using CORRECT field names from API test
                                business_address = best_match.get(
                                    "address"
                                )  # May contain descriptive text
                                business_website = best_match.get(
                                    "site"
                                )  # Correct field name is "site", not "url"
                                business_domain = None  # Not available in snack_pack
                                business_phone = best_match.get(
                                    "phone"
                                )  # Only available for some businesses
                                business_latitude = None  # Not available in snack_pack
                                business_longitude = None  # Not available in snack_pack
                                business_type = best_match.get(
                                    "type"
                                )  # Business category

                                # Address quality check - detect if it contains descriptive text instead of real address
                                address_quality = "good"
                                if business_address:
                                    # Check for descriptive patterns that indicate poor address data
                                    descriptive_patterns = [
                                        r"\d+\+? years? in business",  # "35+ years in business"
                                        r"⋅",  # Unicode middle dot separator
                                        r"^\w+,\s*\w{2}$",  # Just "City, State" format
                                    ]

                                    for pattern in descriptive_patterns:
                                        if re.search(
                                            pattern, business_address, re.IGNORECASE
                                        ):
                                            address_quality = "poor"
                                            break

                                # Debug: Print all available fields and address quality
                                print(
                                    f"🔍 Available business data fields: {list(best_match.keys())}"
                                )
                                print(
                                    f"📍 Address: {business_address} (Quality: {address_quality})"
                                )
                                print(f"🌐 Website: {business_website}")
                                print(f"📞 Phone: {business_phone}")
                                print(f"🏷️ Type: {business_type}")
                                if (
                                    business_latitude is None
                                    and business_longitude is None
                                ):
                                    print(f"🗺️ Coordinates: Not available in snack_pack")
                                else:
                                    print(
                                        f"🗺️ Coordinates: {business_latitude}, {business_longitude}"
                                    )

                                print(
                                    f"🎯 Selected: '{business_name}' (Rating: {business_rating}, Reviews: {business_review_count})"
                                )

                                # Convert CID to FID format
                                fid = self._convert_cid_to_fid(cid)
                                if fid:
                                    print(f"🔄 Converted CID to FID: {fid}")
                                    return {
                                        "fid": fid,
                                        "rating": business_rating,
                                        "review_count": business_review_count,
                                        "address": business_address,
                                        "address_quality": address_quality,
                                        "website": business_website,
                                        "domain": business_domain,
                                        "phone": business_phone,
                                        "latitude": business_latitude,
                                        "longitude": business_longitude,
                                        "business_type": business_type,
                                    }

                        return {
                            "fid": None,
                            "rating": None,
                            "review_count": None,
                            "address": None,
                            "address_quality": None,
                            "website": None,
                            "domain": None,
                            "phone": None,
                            "latitude": None,
                            "longitude": None,
                            "business_type": None,
                        }
                    else:
                        error_text = await response.text()
                        print(f"❌ HTTP Error {response.status}: {error_text[:500]}")
                        raise aiohttp.ClientError(
                            f"Business search failed with status {response.status}: {error_text[:200]}"
                        )

        except Exception as e:
            print(f"❌ Exception in search: {str(e)}")
            raise RuntimeError(f"Business search request failed: {str(e)}")

    def to_json(self, result: BusinessReviewsResult) -> str:
        """
        Convert BusinessReviewsResult to JSON string

        Args:
            result: Business reviews result (Pydantic model)

        Returns:
            JSON string representation
        """
        return result.model_dump_json(indent=2, exclude_none=True)

    async def get_maps_place_data(self, fid: str) -> Optional[Dict]:
        """
        Fetch Google Maps place data using FID
        
        Args:
            fid: Feature ID of the business (e.g., "0x0:0x4547a353b1158112")
            
        Returns:
            Dictionary containing Google Maps place data or None if request fails
        """
        try:
            # Build the Google Maps place data URL
            target_url = f"https://www.google.com/maps/place/data=!3m1!4b1!4m2!3m1!1s{fid}?brd_json=1"
            
            print(f"🗺️ Fetching Google Maps data for FID: {fid}")
            print(f"🔗 Maps URL: {target_url}")
            
            ssl_context = await self._create_ssl_context()
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    target_url,
                    proxy=self.proxies["https"],
                    ssl=ssl_context,
                ) as response:
                    
                    if response.status == 200:
                        maps_data = await response.json()
                        print(f"✅ Successfully fetched Google Maps data")
                        
                        # Extract key fields for debugging
                        hours = maps_data.get("hours") or maps_data.get("opening_hours")
                        overview = maps_data.get("overview") or maps_data.get("description") or maps_data.get("about")
                        
                        if hours:
                            print(f"🕒 Hours data available")
                        if overview:
                            print(f"📝 Overview/description available")
                            
                        return maps_data
                    else:
                        error_text = await response.text()
                        print(f"❌ Maps data fetch failed with status {response.status}: {error_text[:200]}")
                        return None
                        
        except Exception as e:
            print(f"❌ Error fetching Google Maps data: {e}")
            return None


    


# Example usage
async def main():
    """Example usage of GoogleReviewFetcher with LLM Enhancement"""
    print("🏢 Testing Google Review Fetcher with LLM Enhancement")
    print("=" * 60)

    # Initialize with LLM support using real API keys
    fetcher = GoogleBusinessResearcher()

    # Test: Fetch reviews for a business
    try:
        business_name = "J&J Plumbing, Heating, Cooling & Electric"
        location = "Cleveland, OH"

        print(f"\n📝 Fetching reviews for: {business_name}")
        print(f"📍 Location: {location}")
        print("-" * 50)

        # Fetch reviews with different sorting options
        reviews_result = await fetcher.fetch_reviews(
            business_name=business_name,
            business_location=location,
            sort="newestFirst",  # Get newest reviews first
            max_results=10,
        )

        if reviews_result:
            print(f"\n✅ Business: {reviews_result.business_name}")
            print(f"⭐ Overall Rating: {reviews_result.total_rating}")
            print(f"📊 Total Reviews: {reviews_result.total_review_count}")
            print(f"📝 Fetched Reviews: {len(reviews_result.reviews)}")
            print(f"🆔 Business FID: {reviews_result.business_fid}")
            print(f"🔗 Search URL: {reviews_result.search_url}")

            # Display new business data fields
            if reviews_result.business_address:
                quality_indicator = (
                    "✅" if reviews_result.address_quality == "good" else "⚠️"
                )
                print(
                    f"📍 Address: {reviews_result.business_address} {quality_indicator}"
                )
                if reviews_result.address_quality == "poor":
                    print(
                        f"    ⚠️ Address contains descriptive text, not precise location"
                    )
            if reviews_result.business_website:
                print(f"🌐 Website: {reviews_result.business_website}")
            if reviews_result.business_phone:
                print(f"📞 Phone: {reviews_result.business_phone}")
            if reviews_result.business_type:
                print(f"🏷️ Category: {reviews_result.business_type}")
            if reviews_result.business_latitude and reviews_result.business_longitude:
                print(
                    f"🗺️ Coordinates: {reviews_result.business_latitude}, {reviews_result.business_longitude}"
                )
            else:
                print(f"🗺️ Coordinates: Not available from snack_pack")
            if reviews_result.business_domain:
                print(f"🏷️ Domain: {reviews_result.business_domain}")

            # Display first few reviews
            print(f"\n📝 Sample Reviews (metadata only):")
            print("-" * 40)

            for i, review in enumerate(reviews_result.reviews[:3]):
                print(f"\nReview {i+1}:")
                print(f"  👤 Author: {review.author_name}")
                print(f"  ⭐ Rating: {review.rating}/5")
                print(f"  📅 Date: {review.review_date}")
                # Review text and responses removed from logging for privacy

            # Display reviews summary if available
            if reviews_result.reviews_summary:
                print(f"\n📋 LLM-Generated Reviews Summary:")
                print("-" * 40)
                print(
                    reviews_result.reviews_summary[:300] + "..."
                    if len(reviews_result.reviews_summary) > 300
                    else reviews_result.reviews_summary
                )

            # Demonstrate maps data fetching
            print(f"\n🗺️ Fetching Google Maps data for the business...")
            print("-" * 40)
            maps_data = await fetcher.get_maps_place_data(reviews_result.business_fid)
            
            if maps_data:
                # Extract and display key maps data
                hours = maps_data.get("hours") or maps_data.get("opening_hours")
                overview = maps_data.get("overview") or maps_data.get("description") or maps_data.get("about")
                
                print(f"✅ Google Maps data fetched successfully")
                if hours:
                    print(f"🕒 Business Hours: Available in maps data")
                if overview:
                    print(f"📝 Business Overview: Available in maps data")
                
                # Show number of available data fields
                field_count = len([k for k, v in maps_data.items() if v is not None])
                print(f"📊 Maps data contains {field_count} non-null fields")
            else:
                print(f"❌ Could not fetch Google Maps data")

            # Show JSON output (contains full data but not displayed in console)
            print(
                f"\n✅ Reviews fetched successfully (full data available via JSON export)"
            )
            print(
                f"💾 Use fetcher.to_json(reviews_result) to export complete review data"
            )
            print(
                f"💾 Use fetcher.get_maps_place_data(fid) to get Google Maps data"
            )

            print(
                f"\n🎯 Success! The system {'used LLM' if fetcher.llm_client else 'used traditional matching'} for business selection."
            )
        else:
            print(f"\n❌ No business match found for: {business_name} in {location}")

    except Exception as e:
        print(f"❌ Error: {e}")

    print(f"\n📋 Usage Notes:")
    print(
        "- Automatically loads Gemini API keys from config.py (GEMINI_API_KEY_1 through GEMINI_API_KEY_9)"
    )
    print("- Uses LLM-only business matching for accurate results")
    print("- Generates 3-paragraph summaries of Google reviews (max 2000 tokens)")
    print("- Returns None if no business match is found (no fallback matching)")
    print(
        "- Simple interface: GoogleBusinessResearcher() and fetch_reviews(business_name, location)"
    )
    print("- New: get_maps_place_data(fid) to fetch Google Maps data for a business")
    print("- Maps data includes hours, overview, and other business details from Google Maps")


if __name__ == "__main__":
    asyncio.run(main())
