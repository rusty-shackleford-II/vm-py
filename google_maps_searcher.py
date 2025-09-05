import os
import json
import re
import requests
import time
import xml.etree.ElementTree as ET
import asyncio
import aiohttp
import ssl
from typing import Dict, List, Optional, Tuple
from pprint import pprint
from pydantic import BaseModel

# Optional Gemini + config imports (mirrors google_review_fetcher.py style)
try:
    from clients.gemini_client import GeminiClient
    GEMINI_AVAILABLE = True
except Exception:
    print("⚠️ Gemini client not available. LLM business matching will not work.")
    GEMINI_AVAILABLE = False

try:
    import config
    CONFIG_AVAILABLE = True
except Exception:
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

    author_image: Optional[str] = None
    author_name: str
    rating: Optional[int] = None
    review_date: Optional[str] = None
    review_text: Optional[str] = None


class BusinessReviewsResult(BaseModel):
    """Model for complete business reviews result"""

    business_name: str
    business_fid: str
    total_rating: Optional[float] = None
    total_review_count: Optional[int] = None
    search_url: Optional[str] = None
    business_address: Optional[str] = None
    address_quality: Optional[str] = None
    business_website: Optional[str] = None
    business_domain: Optional[str] = None
    business_phone: Optional[str] = None
    business_latitude: Optional[float] = None
    business_longitude: Optional[float] = None
    business_type: Optional[str] = None
    reviews: List[ReviewResult] = []


class GoogleMapsBusinessSearcher:
    """
    Google Maps business searcher using Bright Data proxy with optional LLM match selection.

    - Provides generic FID extraction for a query/location
    - Provides LLM-based single-business matching similar to google_review_fetcher.py
    """

    def __init__(
        self,
        ca_cert_path: str = "BrightData SSL certificate (port 33335).crt",
        host: str = "brd.superproxy.io",
        port: int = 33335,
        username: str = "brd-customer-hl_6467129b-zone-serp_api1",
        password: str = "168jew4d4jg8",
    ) -> None:
        # Resolve certificate path relative to this file if not absolute
        if not os.path.isabs(ca_cert_path):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.ca_cert_path = os.path.join(script_dir, ca_cert_path)
        else:
            self.ca_cert_path = ca_cert_path

        self.host = host
        self.port = port
        self.username = username
        self.password = password

        # Build proxy URL
        self.proxy_url = f"http://{self.username}:{self.password}@{self.host}:{self.port}"
        self.proxies = {"http": self.proxy_url, "https": self.proxy_url}

        # Initialize LLM client from config keys (if available)
        self.llm_client = None
        if GEMINI_AVAILABLE and CONFIG_AVAILABLE:
            gemini_keys: List[str] = []
            for i in range(1, 10):
                try:
                    key = getattr(config, f"GEMINI_API_KEY_{i}")
                    if key:
                        gemini_keys.append(key)
                except AttributeError:
                    break

            if gemini_keys:
                try:
                    self.llm_client = GeminiClient(
                        api_keys=gemini_keys, model_name="gemini-2.0-flash"
                    )
                    print("🤖 LLM-enhanced business selection enabled with Gemini 2.0 Flash")
                except Exception as e:
                    print(f"⚠️ Failed to initialize LLM client: {e}")
                    self.llm_client = None
            else:
                print("⚠️ No Gemini API keys found in config. LLM selection disabled.")
        else:
            print("⚠️ LLM client unavailable - missing client or config.")

    async def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context with custom certificate"""
        if not os.path.exists(self.ca_cert_path):
            raise FileNotFoundError(
                f"SSL certificate not found at: {self.ca_cert_path}"
            )

        ssl_context = ssl.create_default_context(cafile=self.ca_cert_path)
        return ssl_context

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

                # Wait before retrying
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.5 * (attempt + 1))  # Exponential backoff

            except Exception as e:
                last_error = e
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



    def _extract_fids(self, obj) -> List[str]:
        fids: List[str] = []

        def extract(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "fid" and isinstance(v, str):
                        fids.append(v)
                    else:
                        extract(v)
            elif isinstance(o, list):
                for item in o:
                    extract(item)

        extract(obj)
        # De-duplicate while preserving order
        seen = set()
        unique = []
        for fid in fids:
            if fid not in seen:
                seen.add(fid)
                unique.append(fid)
        return unique

    def _extract_candidate_businesses(self, obj) -> List[Dict]:
        """
        Recursively walk JSON and collect candidate business dicts that include an FID and
        basic metadata (name/title/address if available). This is intentionally permissive
        as Google Maps JSON can vary.
        """
        candidates_by_fid: Dict[str, Dict] = {}

        def walk(o):
            if isinstance(o, dict):
                fid = o.get("fid") if isinstance(o.get("fid"), str) else None
                if fid:
                    name = (
                        o.get("name")
                        or o.get("title")
                        or o.get("display_name")
                        or o.get("business_name")
                    )
                    address = (
                        o.get("address")
                        or o.get("formatted_address")
                        or o.get("addr")
                    )
                    rating = o.get("rating")
                    reviews_cnt = o.get("reviews_cnt") or o.get("reviews_count")
                    candidate = {
                        "fid": fid,
                        "name": name or "Unknown",
                        "address": address,
                        "rating": rating,
                        "reviews_cnt": reviews_cnt,
                    }
                    if fid not in candidates_by_fid:
                        candidates_by_fid[fid] = candidate

                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for item in o:
                    walk(item)

        walk(obj)
        return list(candidates_by_fid.values())

    def get_fids_from_maps(self, query: str, location: str) -> Tuple[List[str], Dict]:
        """
        Perform a generic Google Maps search and extract all FIDs found in the JSON.
        """
        search_query = f"{query} {location}".replace(" ", "+").strip("+")
        url = f"https://www.google.com/maps/search/{search_query}/?brd_json=1"

        response = requests.get(url, proxies=self.proxies, verify=self.ca_cert_path)
        response.raise_for_status()
        data = response.json()

        # Debug dump (kept from previous script behavior)
        pprint(data)

        fids = self._extract_fids(data)
        return fids, data

    def _parse_business_selection(self, llm_response: str) -> Optional[int]:
        """
        Parse the LLM response to extract the selected business index.
        Accepts formats like <business>2</business> or a bare integer fallback.
        """
        try:
            cleaned = llm_response.strip()
            pattern = r"<business>(-?\d+)</business>"
            match = re.search(pattern, cleaned, re.IGNORECASE)
            if match:
                return int(match.group(1))

            # Fallback to XML parsing
            try:
                root = ET.fromstring(cleaned)
                if root.tag.lower() == "business" and root.text:
                    return int(root.text.strip())
                elem = root.find(".//business")
                if elem is not None and elem.text:
                    return int(elem.text.strip())
            except ET.ParseError:
                pass

            # Last resort: first integer in response
            numbers = re.findall(r"-?\d+", cleaned)
            if numbers:
                return int(numbers[0])
            return None
        except Exception:
            return None

    def _select_with_llm(self, search_name: str, candidates: List[Dict], business_category: Optional[str] = None) -> Optional[Dict]:
        if not self.llm_client or not candidates:
            return None

        lines = []
        for i, c in enumerate(candidates):
            name = c.get("name") or "Unknown"
            address = c.get("address") or "No address"
            rating = c.get("rating")
            reviews_cnt = c.get("reviews_cnt")
            rating_str = f" | Rating: {rating}" if rating is not None else ""
            reviews_str = f" | Reviews: {reviews_cnt}" if reviews_cnt is not None else ""
            lines.append(f"Index {i}: \"{name}\"\n    Address: {address}{rating_str}{reviews_str}")
        formatted = "\n".join(lines)

        # Build category-aware prompt
        category_context = ""
        if business_category:
            category_context = f"\nEXPECTED BUSINESS CATEGORY: {business_category}"

        prompt = f"""You are helping to identify the correct business from Google Maps search results.

SEARCH TARGET: "{search_name}"{category_context}

AVAILABLE BUSINESSES:
{formatted}

TASK: Select the single best match for "{search_name}". 

CRITICAL MATCHING RULES (in strict priority order):
1. **COMPANY NAME MUST MATCH**: The core company identifier in the target name must be present
   - For "{search_name}": Look for the exact company name components
   - Company names like "J&J", "ABC", "Smith's", etc. must match exactly
   - NEVER select a business with a different company name (e.g., "J&R" is NOT "J&J")

2. **Service Matching**: After confirming company name match, consider services
   - Additional services beyond the target are acceptable and common
   - Businesses can offer broader services than what's searched for

3. **Category Context**: {f"Expected category: '{business_category}' - use as context only, never override company name matching" if business_category else "Business category is secondary to company name"}

ABSOLUTE DEALBREAKERS:
- Different company name (e.g., "J&R" vs "J&J", "ABC" vs "XYZ")
- Completely different business entity

EXAMPLES OF CORRECT MATCHES:
- Target: "J&J Heating & Cooling" → "J&J Plumbing, Heating, Cooling, & Electric" ✓ (SAME company "J&J")
- Target: "ABC Plumbing" → "ABC Plumbing & Heating Services" ✓ (SAME company "ABC")
- Target: "Smith HVAC" → "Smith Heating & Cooling" ✓ (SAME company "Smith")

EXAMPLES OF WRONG MATCHES (NEVER SELECT THESE):
- Target: "J&J Heating & Cooling" → "J&R Heating & Cooling" ✗ (DIFFERENT company: "J&J" ≠ "J&R")
- Target: "J&J Heating & Cooling" → "Johnson & Johnson Medical" ✗ (completely different business)
- Target: "ABC Plumbing" → "XYZ Plumbing Services" ✗ (DIFFERENT company: "ABC" ≠ "XYZ")
- Target: "Smith's Auto" → "Jones Auto Repair" ✗ (DIFFERENT company: "Smith's" ≠ "Jones")

STEP-BY-STEP PROCESS:
1. First, identify businesses that contain the exact company name from "{search_name}"
2. Among those matches, pick the one with the best service/location match
3. If NO businesses have the correct company name, respond with -1

RESPOND with ONLY the index number in XML tags:
- Best match: <business>INDEX_NUMBER</business>
- No reasonable match: <business>-1</business>
"""

        try:
            response = self.llm_client.ask(prompt, disable_thinking=True)
            idx = self._parse_business_selection(response)
            if idx is not None and 0 <= idx < len(candidates):
                return candidates[idx]
            if idx == -1:
                return None
            return None
        except Exception:
            return None

    def search_single_business(
        self,
        business_name: str,
        location: str,
        business_category: Optional[str] = None,
        save_raw_to: Optional[str] = "maps_search_raw.json",
        max_candidates: int = 25,
    ) -> Dict:
        """
        Search Google Maps for a single business (by name + location) and use an LLM to
        pick the best match from the results. Returns a dict with keys:

        {
            "fid": Optional[str],
            "selected": Optional[Dict],
            "candidates": List[Dict],
            "search_url": str
        }
        
        Args:
            business_name: Name of the business to search for
            location: Location/address to search in
            business_category: Optional expected business category (e.g., "HVAC", "Plumbing", "Restaurant") to improve LLM matching
            save_raw_to: Optional file path to save raw JSON response 
            max_candidates: Maximum number of candidates to consider
        """
        query = f"{business_name} {location}".strip()
        search_query = query.replace(" ", "+")
        url = f"https://www.google.com/maps/search/{search_query}/?brd_json=1"

        resp = requests.get(url, proxies=self.proxies, verify=self.ca_cert_path)
        resp.raise_for_status()
        data = resp.json()

        if save_raw_to:
            try:
                with open(save_raw_to, "w") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

        candidates = self._extract_candidate_businesses(data)
        if max_candidates and len(candidates) > max_candidates:
            candidates = candidates[:max_candidates]

        selected = self._select_with_llm(business_name, candidates, business_category)
        fid = selected.get("fid") if selected else None

        return {
            "fid": fid,
            "selected": selected,
            "candidates": candidates,
            "search_url": url,
        }

    async def fetch_reviews_by_fid(
        self,
        fid: str,
        business_name: str = "Unknown Business",
        sort: str = "qualityScore",
        filter_keyword: Optional[str] = None,
        max_results: int = 20,
    ) -> Optional[List[ReviewResult]]:
        """
        Fetch Google reviews for a business using its FID (Feature ID).

        Args:
            fid: Feature ID of the business (e.g., "0x0:0x4547a353b1158112")
            business_name: Name of the business (for display/summary purposes)
            sort: Review sorting method - "qualityScore", "newestFirst", "ratingHigh", "ratingLow"
            filter_keyword: Optional keyword to filter reviews
            max_results: Maximum number of reviews to fetch (default 20)

        Returns:
            List of simplified review models or None if fetch fails
        """
        try:
            # Create review configuration
            config_obj = ReviewConfig(
                sort=sort, filter_keyword=filter_keyword, max_results=max_results
            )

            # Fetch reviews using FID
            raw_reviews = await self._fetch_reviews_by_fid(fid, config_obj)

            # Parse reviews into simplified list
            reviews = []
            review_data = raw_reviews.get("reviews", [])

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
                    author_image = reviewer.get("profile_photo_url")

                    # Create simplified review object
                    review = ReviewResult(
                        author_image=author_image,
                        author_name=author_name,
                        rating=rating,
                        review_date=review_item.get("created"),  # BrightData uses "created" for date
                        review_text=review_item.get("comment"),  # BrightData uses "comment" for review text
                    )
                    reviews.append(review)

                except Exception:
                    continue

            return reviews

        except Exception:
            return None

    def to_json(self, reviews: List[ReviewResult]) -> str:
        """
        Convert list of ReviewResult to JSON string

        Args:
            reviews: List of review results (Pydantic models)

        Returns:
            JSON string representation
        """
        return json.dumps([review.model_dump() for review in reviews], indent=2)


async def demo_reviews():
    """Demo the new review functionality with benchmarking"""
    searcher = GoogleMapsBusinessSearcher()
    
    # Complete workflow: business name -> FID -> reviews
    business_name = "Air Conditioner Service Near Me"
    business_location = "San Mateo, CA"
    business_category = "HVAC"
    
    print(f"🚀 Starting complete workflow: '{business_name}' in '{business_location}'")
    print(f"📋 Process: Business search → FID extraction → Reviews fetch")
    
    # Start timing the entire process
    total_start_time = time.time()
    
    # Step 1: Business search and FID extraction
    search_start_time = time.time()
    result = searcher.search_single_business(
        business_name, 
        business_location, 
        business_category=business_category
    )
    search_end_time = time.time()
    search_elapsed = search_end_time - search_start_time
    
    if not result.get("fid"):
        print(f"❌ No business found")
        return
    
    # Step 2: Reviews fetch
    fid = result.get("fid")
    reviews_start_time = time.time()
    reviews = await searcher.fetch_reviews_by_fid(
        fid=fid,
        business_name=result["selected"].get("name", business_name),
        sort="newestFirst",
        max_results=20
    )
    reviews_end_time = time.time()
    reviews_elapsed = reviews_end_time - reviews_start_time
    
    # Total time
    total_end_time = time.time()
    total_elapsed = total_end_time - total_start_time
    
    # Results
    if reviews:
        print(f"\n✅ Complete workflow successful!")
        print(f"🏢 Business: {result['selected'].get('name', 'Unknown')}")
        print(f"🆔 FID: {fid}")
        print(f"📝 Reviews fetched: {len(reviews)}")
        
        # Benchmarking results
        print(f"\n⏱️ Performance Benchmarks:")
        print(f"  📍 Business search + FID: {search_elapsed:.2f}s")
        print(f"  📝 Reviews fetch: {reviews_elapsed:.2f}s")
        print(f"  🔥 Total end-to-end: {total_elapsed:.2f}s")
        
        # Sample review data
        if reviews:
            print(f"\n📋 Sample review (first one):")
            first_review = reviews[0]
            print(f"  👤 {first_review.author_name} - {first_review.rating}/5 stars")
            if first_review.review_text:
                preview = first_review.review_text[:150] + "..." if len(first_review.review_text) > 150 else first_review.review_text
                print(f"  💬 '{preview}'")
        
        print(f"\n💾 JSON export: searcher.to_json(reviews)")
    else:
        print(f"❌ Failed to fetch reviews")


if __name__ == "__main__":
    # Demo usage
    import asyncio
    
    # Run the async demo
    asyncio.run(demo_reviews())
