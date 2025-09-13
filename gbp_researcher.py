#!/usr/bin/env python3
"""
Google Business Profile (GBP) Researcher Module

This module provides a comprehensive solution for gathering business information from Google's
various data sources including Maps, Search, and Reviews. The GBPResearcher class serves as
a unified interface for collecting and processing business data from multiple Google services.

Key Features:
- Business search and identification using Google's local search API
- Structured Google Maps place data extraction via JSON APIs
- Raw HTML content fetching and intelligent cleaning from Google Maps pages
- Google Reviews collection with configurable sorting and filtering
- AI-powered business matching and content processing using Gemini
- Parallel data collection for optimal performance
- Comprehensive error handling and retry mechanisms

Data Sources Integrated:
1. Google Search Results (snack_pack) - for business discovery and basic info
2. Google Maps Place Data API - for structured business information
3. Google Maps HTML Pages - for rich content and additional details
4. Google Reviews API - for customer feedback and ratings
5. BrightData Proxy Service - for reliable data access and geo-targeting

The main entry point is the `get_business_data()` method which returns:
- Raw HTML content from Google Maps as a cleaned string
- Structured Maps data as a Python dictionary
- Customer reviews as a list of Pydantic models

Usage Example:
    researcher = GBPResearcher()
    html, maps_data, reviews = await researcher.get_business_data(
        business_name="Joe's Pizza", 
        business_location="New York, NY"
    )

Dependencies:
- aiohttp for async HTTP requests
- BeautifulSoup4 for HTML parsing
- Pydantic for data validation and modeling
- BrightData proxy service for reliable Google access
- Optional: Gemini AI client for intelligent processing

Author: Warren
"""

import asyncio
import aiohttp
import ssl
import os
import re
import json
import math
import time
import typing as t
from urllib.parse import quote, urlparse, parse_qs, unquote
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any
from pydantic import BaseModel

# Import config for API keys
try:
    import config
    CONFIG_AVAILABLE = True
except ImportError:
    print("⚠️ Config not available for API keys")
    CONFIG_AVAILABLE = False

# Import Gemini client for processing
try:
    from clients.gemini_client import GeminiClient
    GEMINI_AVAILABLE = True
except ImportError:
    print("⚠️ Gemini client not available. AI processing will not work.")
    GEMINI_AVAILABLE = False

# Import comprehensive HTML cleaning from maps_html_parser
try:
    from maps_html_parser import clean_html_content as comprehensive_clean_html
    COMPREHENSIVE_CLEANING_AVAILABLE = True
except ImportError:
    print("⚠️ maps_html_parser not available. Using simplified HTML cleaning.")
    COMPREHENSIVE_CLEANING_AVAILABLE = False


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
    search_url: Optional[str] = None  # Original Google search URL that found the business
    business_address: Optional[str] = None
    address_quality: Optional[str] = None  # "good" or "poor" - indicates if address is descriptive text
    business_website: Optional[str] = None
    business_domain: Optional[str] = None
    business_phone: Optional[str] = None
    business_latitude: Optional[float] = None
    business_longitude: Optional[float] = None
    business_type: Optional[str] = None  # Business category from Google (e.g., "Plumber")
    reviews: List[ReviewResult] = []
    reviews_summary: Optional[str] = None  # Summary of all reviews using LLM


class BusinessData(BaseModel):
    """Model for comprehensive business data"""
    
    # Basic info
    name: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    address_quality: Optional[str] = None  # "good" or "poor"
    phone: Optional[str] = None
    phone_digits: Optional[str] = None
    website: Optional[str] = None
    domain: Optional[str] = None
    
    # Location
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    # Ratings & Reviews
    rating: Optional[float] = None
    review_count: Optional[int] = None
    reviews: Optional['BusinessReviewsResult'] = None  # Store reviews data
    
    # Business details
    categories: Optional[List[str]] = None
    business_type: Optional[str] = None
    hours: Optional[Any] = None
    services: Optional[List[str]] = None
    
    # Images
    image: Optional[str] = None
    
    # Identifiers
    cid: Optional[str] = None
    fid: Optional[str] = None
    
    # Raw data
    maps_data: Optional[Dict] = None
    cleaned_html: Optional[str] = None
    structured_xml: Optional[str] = None
    
    # AI-generated content
    ai_description: Optional[str] = None


class GBPResearcher:
    """
    Comprehensive Google Business Profile researcher that combines multiple data sources
    and processing methods to gather complete business information.
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
        Initialize GBP Researcher with BrightData credentials and automatic setup
        
        Args:
            ca_cert_path: Path to SSL certificate file
            host: Proxy host
            port: Proxy port
            username: BrightData username
            password: BrightData password
        """
        # Setup SSL certificate path
        if not os.path.isabs(ca_cert_path):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.ca_cert_path = os.path.join(script_dir, ca_cert_path)
        else:
            self.ca_cert_path = ca_cert_path
        
        # BrightData proxy configuration
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.proxy_url = f"http://{username}:{password}@{host}:{port}"
        self.proxies = {"http": self.proxy_url, "https": self.proxy_url}
        
        # Load Gemini API keys from config
        self.gemini_keys = []
        if CONFIG_AVAILABLE:
            for i in range(1, 10):  # Keys 1-9
                try:
                    key = getattr(config, f"GEMINI_API_KEY_{i}")
                    if key and key != "":
                        self.gemini_keys.append(key)
                except AttributeError:
                    break
            print(f"🔑 Loaded {len(self.gemini_keys)} Gemini API keys from config")
        
        # Initialize Gemini client
        self.gemini_client = None
        if GEMINI_AVAILABLE and self.gemini_keys:
            try:
                self.gemini_client = GeminiClient(
                    api_keys=self.gemini_keys, model_name="gemini-2.0-flash"
                )
                print("🤖 Gemini AI processing enabled")
            except Exception as e:
                print(f"⚠️ Failed to initialize Gemini client: {e}")
                self.gemini_client = None
        else:
            print("⚠️ Gemini AI processing unavailable")
    
    async def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context with custom certificate"""
        if not os.path.exists(self.ca_cert_path):
            raise FileNotFoundError(f"SSL certificate not found at: {self.ca_cert_path}")
        
        ssl_context = ssl.create_default_context(cafile=self.ca_cert_path)
        return ssl_context
    
    def _convert_cid_to_fid(self, cid: str) -> Optional[str]:
        """
        Convert CID to FID format for Google Maps API calls
        
        Args:
            cid: Customer ID in decimal format
            
        Returns:
            FID in proper format or None if conversion fails
        """
        try:
            cid_int = int(cid)
            cid_hex = format(cid_int, "x")
            fid = f"0x0:0x{cid_hex}"
            print(f"🔄 CID conversion: {cid} -> FID: {fid}")
            return fid
        except Exception as e:
            print(f"❌ Error converting CID to FID: {e}")
            return None
    
    def _build_search_url(
        self, business_name: str, location: str = "", use_local_search: bool = True
    ) -> str:
        """Build Google search URL to find business"""
        query = f"{business_name} {location}".strip()
        encoded_query = quote(query)
        
        params = {
            "q": encoded_query,
            "hl": "en",
            "gl": "us",
            "brd_json": "1",
        }
        
        if use_local_search:
            params["tbm"] = "lcl"  # Local search
        
        param_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"https://www.google.com/search?{param_string}"
    
    async def get_business_data(
        self, 
        business_name: str, 
        business_location: str = "",
        max_reviews: int = 20,
        review_sort: str = "qualityScore"
    ) -> t.Tuple[Optional[str], Optional[t.Dict[str, t.Any]], t.List[ReviewResult]]:
        """
        Get comprehensive business data from Google sources.
        
        This is the main entry point for the GBPResearcher class. It searches for a business
        and returns three key data types: cleaned HTML content, structured Maps data, and
        customer reviews.
        
        Args:
            business_name: Name of the business to search for (e.g., "Joe's Pizza")
            business_location: Location of the business (e.g., "New York, NY", "San Mateo, CA")
            max_reviews: Maximum number of reviews to fetch (default: 20)
            review_sort: Review sorting method - "qualityScore", "newestFirst", "ratingHigh", "ratingLow"
            
        Returns:
            A tuple containing:
            - cleaned_html (str | None): Cleaned HTML content from Google Maps page
            - maps_data (dict | None): Structured JSON data from Google Maps API
            - reviews (List[ReviewResult]): List of customer reviews as Pydantic models
            
        Example:
            researcher = GBPResearcher()
            html, maps_data, reviews = await researcher.get_business_data(
                business_name="Caccia's Home Services",
                business_location="San Mateo, CA"
            )
            
            if html:
                print(f"HTML content: {len(html)} characters")
            if maps_data:
                print(f"Maps data: {maps_data.get('name', 'Unknown business')}")
            if reviews:
                print(f"Found {len(reviews)} reviews")
        """
        print(f"🔍 Getting business data for '{business_name}' in '{business_location}'...")
        
        try:
            # Configure review settings
            review_config = ReviewConfig(
                max_results=max_reviews,
                sort=review_sort
            )
            
            # Use the existing search_business method to get comprehensive data
            business_data = await self.search_business(
                business_name=business_name,
                location=business_location,
                include_reviews=True,
                include_html=True,
                review_config=review_config
            )
            
            if not business_data:
                print(f"❌ Could not find business: {business_name}")
                return None, None, []
            
            # Extract the three requested data types
            cleaned_html = business_data.cleaned_html
            maps_data = business_data.maps_data
            reviews_list = business_data.reviews.reviews if business_data.reviews else []
            
            print(f"✅ Successfully retrieved business data:")
            print(f"   📄 HTML: {'✅' if cleaned_html else '❌'} ({len(cleaned_html or '')} chars)")
            print(f"   🗺️ Maps Data: {'✅' if maps_data else '❌'}")
            print(f"   📝 Reviews: {len(reviews_list)} reviews")
            
            return cleaned_html, maps_data, reviews_list
            
        except Exception as e:
            print(f"❌ Error getting business data: {e}")
            return None, None, []

    async def search_business(
        self, business_name: str, location: str = "", 
        include_reviews: bool = False,
        include_html: bool = False,
        review_config: Optional[ReviewConfig] = None
    ) -> Optional[BusinessData]:
        """
        Search for a business and return comprehensive data
        
        Args:
            business_name: Name of the business to search for
            location: Location of the business (e.g., "San Mateo, CA")
            include_reviews: Whether to fetch Google reviews for the business
            include_html: Whether to fetch and clean HTML content
            review_config: Configuration for review fetching (uses defaults if None)
            
        Returns:
            BusinessData object with all available information or None if not found
        """
        print(f"🔍 Searching for '{business_name}' in '{location}'...")
        
        try:
            # Step 1: Find business in search results - MUST succeed for anything else to work
            business_info = await self._find_business_in_search(business_name, location)
            if not business_info:
                print(f"❌ Could not find business: {business_name}")
                return None
            
            if not business_info.get("fid"):
                print(f"❌ No FID found for business: {business_name}")
                return None
            
            print(f"✅ Found business with FID: {business_info.get('fid')}")
            
            # Step 2: Run data collection tasks in parallel
            print(f"🚀 Starting parallel data collection...")
            maps_data, html_content, reviews_data = await self._collect_data_parallel(
                business_info=business_info,
                business_name=business_name,
                location=location,
                include_reviews=include_reviews,
                include_html=include_html,
                review_config=review_config
            )
            
            # Step 3: Process HTML if we got it
            cleaned_html = None
            if html_content:
                print(f"🧹 Cleaning HTML content...")
                cleaned_html = self.clean_html_content(html_content)
                print(f"✅ HTML cleaned - Original: {len(html_content)} chars, Cleaned: {len(cleaned_html)} chars")
            
            # Step 4: Create comprehensive business data object
            business_data = BusinessData(
                name=business_info.get("name"),
                address=business_info.get("address"),
                address_quality=business_info.get("address_quality"),
                phone=business_info.get("phone"),
                website=business_info.get("website"),
                latitude=business_info.get("latitude"),
                longitude=business_info.get("longitude"),
                rating=business_info.get("rating"),
                review_count=business_info.get("review_count"),
                business_type=business_info.get("business_type"),
                cid=business_info.get("cid"),
                fid=business_info.get("fid"),
                maps_data=maps_data,
                cleaned_html=cleaned_html,
                reviews=reviews_data
            )
            
            print(f"✅ Found business: {business_data.name}")
            if business_data.rating:
                print(f"⭐ Rating: {business_data.rating}/5")
            if business_data.review_count:
                print(f"📊 Reviews: {business_data.review_count}")
            
            return business_data
            
        except Exception as e:
            print(f"❌ Error searching for business: {e}")
            return None
    
    async def _collect_data_parallel(
        self,
        business_info: Dict,
        business_name: str,
        location: str,
        include_reviews: bool,
        include_html: bool,
        review_config: Optional[ReviewConfig]
    ) -> t.Tuple[Optional[Dict], Optional[str], Optional[BusinessReviewsResult]]:
        """
        Collect maps data, HTML content, and reviews in parallel
        
        Args:
            business_info: Basic business information with FID
            business_name: Name of the business
            location: Business location
            include_reviews: Whether to fetch reviews
            include_html: Whether to fetch HTML
            review_config: Review configuration
            
        Returns:
            Tuple of (maps_data, html_content, reviews_data)
        """
        fid = business_info.get("fid")
        cid = business_info.get("cid")
        
        # Create tasks for parallel execution
        tasks = []
        task_names = []
        
        # Task 1: Always get structured maps data
        print(f"🗺️ Queuing maps data task...")
        tasks.append(self._timed_task(self.get_maps_place_data(fid), "maps_data"))
        task_names.append("maps_data")
        
        # Task 2: Get HTML if requested
        if include_html and cid:
            print(f"🌐 Queuing HTML fetch task...")
            tasks.append(self._timed_task(self.get_maps_html_from_brightdata(cid), "html_content"))
            task_names.append("html_content")
        else:
            tasks.append(self._return_none())  # Placeholder task
            task_names.append("html_content")
        
        # Task 3: Get reviews if requested
        if include_reviews and fid:
            if review_config is None:
                review_config = ReviewConfig()
            
            print(f"📝 Queuing reviews fetch task...")
            tasks.append(self._timed_task(
                self._fetch_reviews_direct(
                    business_info=business_info,
                    business_name=business_name,
                    fid=fid,
                    sort=review_config.sort,
                    filter_keyword=review_config.filter_keyword,
                    max_results=review_config.max_results,
                    generate_summary=True,
                ), "reviews_data"
            ))
            task_names.append("reviews_data")
        else:
            tasks.append(self._return_none())  # Placeholder task
            task_names.append("reviews_data")
        
        active_tasks = [name for name in task_names if name != "html_content" or include_html]
        active_tasks = [name for name in active_tasks if name != "reviews_data" or include_reviews]
        print(f"🔄 Starting {len(active_tasks)} data collection tasks in parallel: {', '.join(active_tasks)}")
        start_time = time.time()
        
        # Execute all tasks in parallel
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            maps_data = None
            html_content = None
            reviews_data = None
            
            # Process results
            for i, (result, task_name) in enumerate(zip(results, task_names)):
                if isinstance(result, Exception):
                    print(f"⚠️ Task {task_name} failed: {result}")
                    continue
                
                if task_name == "maps_data":
                    maps_data = result
                    if result:
                        print(f"✅ Maps data collected successfully")
                    else:
                        print(f"⚠️ Maps data collection returned None")
                        
                elif task_name == "html_content":
                    html_content = result
                    if result:
                        print(f"✅ HTML content collected successfully ({len(result)} chars)")
                    elif include_html:
                        print(f"⚠️ HTML content collection returned None")
                        
                elif task_name == "reviews_data":
                    reviews_data = result
                    if result and result.reviews:
                        print(f"✅ Reviews collected successfully ({len(result.reviews)} reviews)")
                    elif include_reviews:
                        print(f"⚠️ Reviews collection returned None")
            
            elapsed_time = time.time() - start_time
            print(f"⚡ Parallel data collection completed in {elapsed_time:.2f} seconds")
            return maps_data, html_content, reviews_data
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            print(f"❌ Error in parallel data collection after {elapsed_time:.2f} seconds: {e}")
            return None, None, None
    
    async def _return_none(self) -> None:
        """Helper method to return None for placeholder tasks"""
        return None
    
    async def _timed_task(self, coro, task_name: str):
        """Wrapper to time individual tasks for parallel execution visibility"""
        task_start = time.time()
        print(f"🚀 Starting {task_name} task...")
        try:
            result = await coro
            elapsed = time.time() - task_start
            print(f"✅ {task_name} completed in {elapsed:.2f}s")
            return result
        except Exception as e:
            elapsed = time.time() - task_start
            print(f"❌ {task_name} failed after {elapsed:.2f}s: {e}")
            raise
    
    async def _fetch_reviews_direct(
        self,
        business_info: Dict,
        business_name: str,
        fid: str,
        sort: str = "qualityScore",
        filter_keyword: Optional[str] = None,
        max_results: int = 20,
        generate_summary: bool = True,
    ) -> Optional[BusinessReviewsResult]:
        """
        Fetch reviews directly without redundant business search - optimized for parallel execution
        
        Args:
            business_info: Already found business information
            business_name: Name of the business
            fid: Feature ID (already validated)
            sort: Review sorting method
            filter_keyword: Optional keyword to filter reviews
            max_results: Maximum number of reviews to fetch
            generate_summary: Whether to generate an LLM summary
            
        Returns:
            Structured business reviews result or None if fetch fails
        """
        try:
            print(f"📝 Fetching reviews for {business_name} (direct mode)...")
            
            # Create config object
            config_obj = ReviewConfig(
                sort=sort, filter_keyword=filter_keyword, max_results=max_results
            )
            
            # Fetch reviews using FID directly
            raw_reviews = await self._fetch_reviews_by_fid(fid, config_obj)
            
            # Parse and structure the results with business info we already have
            structured_result = self._parse_reviews(
                raw_reviews,
                business_name,
                fid,
                None,  # search_url not needed for parallel execution
                business_info.get("rating"),
                business_info.get("review_count"),
                business_info.get("address"),
                business_info.get("address_quality"),
                business_info.get("website"),
                business_info.get("domain"),
                business_info.get("phone"),
                business_info.get("latitude"),
                business_info.get("longitude"),
                business_info.get("business_type"),
            )
            
            # Generate summary if requested and we have reviews
            if generate_summary and structured_result.reviews:
                reviews_summary = await self._generate_reviews_summary(
                    business_name, structured_result.reviews
                )
                structured_result.reviews_summary = reviews_summary
            
            return structured_result
            
        except Exception as e:
            print(f"❌ Error fetching reviews (direct mode): {e}")
            return None
    
    async def _find_business_in_search(
        self, business_name: str, location: str = ""
    ) -> Optional[Dict]:
        """Find business in Google search results and extract basic info"""
        
        # Try local search first
        search_url = self._build_search_url(business_name, location, use_local_search=True)
        print(f"🔗 Trying local search: {search_url}")
        
        result = await self._search_for_business(search_url, business_name)
        if result:
            return result
        
        # Fallback to regular search
        print(f"🔄 Trying regular search...")
        search_url = self._build_search_url(business_name, location, use_local_search=False)
        return await self._search_for_business(search_url, business_name)
    
    async def _search_for_business(
        self, search_url: str, original_business_name: str
    ) -> Optional[Dict]:
        """Perform the actual search and extract business info"""
        
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
                            print(f"🍿 Found snack_pack with {len(result['snack_pack'])} results")
                            
                            # Find the best matching business
                            best_match = await self._find_best_business_match(
                                original_business_name, result["snack_pack"]
                            )
                            
                            if best_match and "cid" in best_match:
                                return self._extract_business_info(best_match)
                        
                        return None
                    else:
                        error_text = await response.text()
                        print(f"❌ HTTP Error {response.status}: {error_text[:200]}")
                        return None
                        
        except Exception as e:
            print(f"❌ Exception in search: {str(e)}")
            return None
    
    def _extract_business_info(self, business_match: Dict) -> Dict:
        """Extract and normalize business information from search result"""
        
        cid = business_match["cid"]
        fid = self._convert_cid_to_fid(cid)
        
        # Extract business data
        business_info = {
            "name": business_match.get("name"),
            "cid": cid,
            "fid": fid,
            "rating": business_match.get("rating"),
            "review_count": business_match.get("reviews_cnt"),
            "address": business_match.get("address"),
            "website": business_match.get("site"),
            "phone": business_match.get("phone"),
            "business_type": business_match.get("type"),
            "latitude": None,  # Not available in snack_pack
            "longitude": None,  # Not available in snack_pack
        }
        
        # Check address quality
        address_quality = "good"
        if business_info["address"]:
            descriptive_patterns = [
                r"\d+\+? years? in business",
                r"⋅",
                r"^\w+,\s*\w{2}$",
            ]
            
            for pattern in descriptive_patterns:
                if re.search(pattern, business_info["address"], re.IGNORECASE):
                    address_quality = "poor"
                    break
        
        business_info["address_quality"] = address_quality
        
        return business_info
    
    async def _find_best_business_match(
        self, search_name: str, businesses: List[Dict]
    ) -> Optional[Dict]:
        """Find the best matching business using AI if available, otherwise simple matching"""
        
        if not businesses:
            return None
        
        # If we have Gemini client, use AI matching
        if self.gemini_client:
            return await self._select_business_with_ai(search_name, businesses)
        
        # Fallback to simple name matching
        print(f"🔍 Using simple name matching...")
        for business in businesses:
            if business.get("name", "").lower() == search_name.lower():
                return business
        
        # Return first result as fallback
        return businesses[0] if businesses else None
    
    async def _select_business_with_ai(
        self, search_name: str, businesses: List[Dict]
    ) -> Optional[Dict]:
        """Use AI to select the best matching business from search results"""
        
        try:
            # Format businesses for AI prompt
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
            
            # Create prompt for AI
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
            
            print(f"🤖 Using AI to select business for: '{search_name}'")
            
            # Get AI response
            response = await asyncio.to_thread(
                self.gemini_client.ask, prompt, disable_thinking=True
            )
            
            # Parse response
            selected_index = self._parse_business_selection(response)
            
            if selected_index is not None and 0 <= selected_index < len(businesses):
                selected_business = businesses[selected_index]
                print(f"🎯 AI selected: '{selected_business.get('name', 'Unknown')}' (Index {selected_index})")
                return selected_business
            elif selected_index == -1:
                print("🤖 AI determined no good match exists")
                return None
            else:
                print(f"⚠️ AI returned invalid index: {selected_index}")
                return None
                
        except Exception as e:
            print(f"❌ AI business selection failed: {e}")
            return None
    
    def _parse_business_selection(self, ai_response: str) -> Optional[int]:
        """Parse the AI response to extract the selected business index"""
        
        try:
            # Try regex extraction first
            pattern = r"<business>(-?\d+)</business>"
            match = re.search(pattern, ai_response, re.IGNORECASE)
            
            if match:
                return int(match.group(1))
            
            # Last resort: look for any number
            numbers = re.findall(r"-?\d+", ai_response)
            if numbers:
                return int(numbers[0])
            
            return None
            
        except (ValueError, AttributeError) as e:
            print(f"❌ Failed to parse AI response: {e}")
            return None
    
    async def get_maps_place_data(
        self, fid: str, use_mobile_headers: bool = True
    ) -> Optional[Dict]:
        """
        Fetch Google Maps place data using FID
        
        Args:
            fid: Feature ID of the business (e.g., "0x0:0x4547a353b1158112")
            use_mobile_headers: Whether to use mobile user agent headers
            
        Returns:
            Dictionary containing Google Maps place data or None if request fails
        """
        try:
            # Build the Google Maps place data URL
            target_url = f"https://www.google.com/maps/place/data=!3m1!4b1!4m2!3m1!1s{fid}?brd_json=1"
            
            print(f"🗺️ Fetching Google Maps data for FID: {fid}")
            
            ssl_context = await self._create_ssl_context()
            timeout = aiohttp.ClientTimeout(total=30)
            
            # Set up headers
            headers = {}
            if use_mobile_headers:
                headers.update({
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Referer': 'https://www.google.com/maps/',
                })
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    target_url,
                    proxy=self.proxies["https"],
                    ssl=ssl_context,
                    headers=headers,
                ) as response:
                    
                    if response.status == 200:
                        maps_data = await response.json()
                        print(f"✅ Successfully fetched Google Maps data")
                        return maps_data
                    else:
                        print(f"❌ Maps data fetch failed with status {response.status}")
                        
                        # Retry without mobile headers if they failed
                        if use_mobile_headers:
                            print(f"🔄 Retrying without mobile headers...")
                            return await self.get_maps_place_data(fid, use_mobile_headers=False)
                        
                        return None
                        
        except Exception as e:
            print(f"❌ Error fetching Google Maps data: {e}")
            
            # Retry without mobile headers if they failed
            if use_mobile_headers:
                print(f"🔄 Retrying without mobile headers due to exception...")
                return await self.get_maps_place_data(fid, use_mobile_headers=False)
            
            return None
    
    async def get_maps_html_from_brightdata(
        self, cid: str, timeout: int = 60
    ) -> Optional[str]:
        """
        Fetch Google Maps HTML using BrightData API
        
        Args:
            cid: Customer ID for the business
            timeout: Request timeout in seconds
            
        Returns:
            Raw HTML content or None if request fails
        """
        try:
            if not CONFIG_AVAILABLE:
                print("❌ Config not available for BrightData API")
                return None
            
            url = f"https://www.google.com/maps?cid={cid}"
            payload = {
                "zone": config.BRIGHTDATA_API_ZONE,
                "url": url,
                "method": "GET",
                "format": "json",
            }
            headers = {
                "Authorization": f"Bearer {config.BRIGHTDATA_API_KEY}",
                "Content-Type": "application/json",
            }
            
            print(f"🌐 Fetching HTML from BrightData for CID: {cid}")
            
            import requests
            resp = requests.post(
                "https://api.brightdata.com/request",
                json=payload,
                headers=headers,
                timeout=timeout
            )
            
            if resp.status_code != 200:
                print(f"❌ BrightData API returned status {resp.status_code}")
                return None
            
            try:
                data = resp.json()
            except Exception:
                print("❌ Failed to parse BrightData response as JSON")
                return None
            
            # Extract HTML content
            for key in ('body', 'html', 'content', 'response', 'data'):
                if key in data and isinstance(data[key], str) and '<html' in data[key].lower():
                    print(f"✅ Successfully fetched HTML content ({len(data[key])} chars)")
                    return data[key]
            
            # Check nested objects
            for k, v in data.items():
                if isinstance(v, dict):
                    for kk in ('body', 'html', 'content'):
                        if kk in v and isinstance(v[kk], str) and '<html' in v[kk].lower():
                            print(f"✅ Successfully fetched HTML content ({len(v[kk])} chars)")
                            return v[kk]
            
            print("❌ No HTML content found in BrightData response")
            return None
            
        except Exception as e:
            print(f"❌ Error fetching HTML from BrightData: {e}")
            return None
    
    def clean_html_content(self, html_text: str, max_word_length: int = 25) -> str:
        """
        Clean HTML content using comprehensive cleaning from maps_html_parser.py
        
        Args:
            html_text: The HTML content to clean
            max_word_length: Maximum length for tokens without spaces
            
        Returns:
            Cleaned text content
        """
        if not html_text:
            return ""
        
        # Use comprehensive cleaning if available, otherwise fall back to simplified version
        if COMPREHENSIVE_CLEANING_AVAILABLE:
            return comprehensive_clean_html(html_text, max_word_length)
        
        # Fallback simplified cleaning (kept for compatibility)
        print("⚠️ Using simplified HTML cleaning - comprehensive cleaning not available")
        
        # Define basic web/code-related substrings to filter out
        web_code_substrings = [
            # HTML/XML tags and structure
            'doctype','</html','<html','</head','</body','</script','<script','</style','<style',
            'noscript','meta ','head ','body ','html ','link ','title ',
            
            # JavaScript keywords
            'function(','function ','return ','var ','let ','const ','=>','typeof ','instanceof ',
            'window','document','this.','new ','throw ','catch ','try ','if(','else ','for(',
            'while(','class ','extends ','constructor','prototype','Promise','async ','await',
            
            # CSS properties
            'rgba(','px','fontfamily','fontstyle','fontweight','background','border','margin',
            'padding','transform','animation','flex','grid','position:','zindex','overflow',
            
            # Google-specific
            'Google Maps','Google LLC','Google Products','Google Sans','Product Sans','Roboto',
            'Enable JavaScript','Sign in','Google apps','gclid','DoubleClick','gtag','analytics',
            
            # Common noise
            'null','undefined','true','false','NaN','Infinity','void 0',
        ]
        
        # Convert to lowercase for matching
        web_code_lower = [s.lower() for s in web_code_substrings]
        
        # Pattern to match 4 consecutive consonants
        consonant_pattern = re.compile(r'[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]{4,}')
        
        # Pattern to match Unicode range identifiers
        unicode_range_pattern = re.compile(r'^U[A-Z0-9]{4,}$')
        
        # Split into tokens and filter
        tokens = html_text.split()
        filtered_tokens = []
        
        for token in tokens:
            # Remove tokens longer than max_word_length without spaces
            if len(token) > max_word_length and ' ' not in token:
                continue
            
            # Remove words with 4 consecutive consonants
            if consonant_pattern.search(token):
                continue
            
            # Remove Unicode range identifiers
            if unicode_range_pattern.match(token):
                continue
            
            # Remove words containing web/code-related substrings
            token_lower = token.lower()
            should_skip = False
            for substring in web_code_lower:
                if substring in token_lower:
                    should_skip = True
                    break
            
            if should_skip:
                continue
            
            filtered_tokens.append(token)
        
        # Rejoin filtered tokens
        cleaned_text = ' '.join(filtered_tokens)
        
        # Remove 'null' instances and non-alphanumeric characters (keeping spaces)
        cleaned_text = re.sub(r'\bnull\b', '', cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r'[^a-zA-Z0-9\s]', '', cleaned_text)
        
        # Clean up multiple spaces
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        
        return cleaned_text
    
    async def process_business_with_html(
        self, business_data: BusinessData, fetch_html: bool = True
    ) -> BusinessData:
        """
        Process business data with HTML fetching and cleaning
        
        Args:
            business_data: BusinessData object with basic info
            fetch_html: Whether to fetch HTML from BrightData
            
        Returns:
            Updated BusinessData with HTML processing results
        """
        if not business_data.cid:
            print("❌ No CID available for HTML processing")
            return business_data
        
        try:
            if fetch_html:
                # Fetch HTML from BrightData
                print(f"🌐 Fetching HTML for business...")
                html_content = await self.get_maps_html_from_brightdata(business_data.cid)
                
                if html_content:
                    # Clean the HTML
                    print(f"🧹 Cleaning HTML content...")
                    cleaned_html = self.clean_html_content(html_content)
                    business_data.cleaned_html = cleaned_html
                    
                    print(f"✅ HTML processed - Original: {len(html_content)} chars, Cleaned: {len(cleaned_html)} chars")
                    
                    # Process with Gemini if available (placeholder)
                    if self.gemini_client and cleaned_html:
                        print(f"🤖 Processing with Gemini AI...")
                        structured_xml = await self._process_with_gemini(cleaned_html)
                        business_data.structured_xml = structured_xml
                        
                        # Generate AI description (placeholder)
                        ai_description = await self._generate_ai_description(structured_xml)
                        business_data.ai_description = ai_description
                else:
                    print("❌ Could not fetch HTML content")
            
            return business_data
            
        except Exception as e:
            print(f"❌ Error processing business with HTML: {e}")
            return business_data
    
    async def _process_with_gemini(self, cleaned_html: str) -> Optional[str]:
        """
        Process cleaned HTML with Gemini to extract structured business information
        
        PLACEHOLDER METHOD - Implement actual Gemini processing here
        
        Args:
            cleaned_html: The cleaned HTML content
            
        Returns:
            Structured XML containing business information
        """
        if not self.gemini_client or not cleaned_html.strip():
            return None
        
        try:
            print(f"🤖 [PLACEHOLDER] Processing {len(cleaned_html)} chars with Gemini...")
            
            # TODO: Implement actual Gemini processing
            # This is a placeholder for the actual implementation
            
            prompt = f"""
            Please analyze the following cleaned Google Maps business data and extract structured information.
            Return the result as valid XML with business details.
            
            Cleaned business data:
            {cleaned_html[:5000]}  # Limit for demonstration
            """
            
            # Placeholder response
            response = f"<business><name>Placeholder Business</name><description>Generated from Gemini processing</description></business>"
            
            print(f"✅ [PLACEHOLDER] Generated structured XML")
            return response
            
        except Exception as e:
            print(f"❌ Error processing with Gemini: {e}")
            return None
    
    async def _generate_ai_description(self, structured_xml: str) -> Optional[str]:
        """
        Generate a business description using AI based on structured data
        
        PLACEHOLDER METHOD - Implement actual description generation here
        
        Args:
            structured_xml: The structured XML containing business information
            
        Returns:
            A compelling business description
        """
        if not self.gemini_client or not structured_xml:
            return None
        
        try:
            print(f"🤖 [PLACEHOLDER] Generating AI description...")
            
            # TODO: Implement actual description generation
            # This is a placeholder for the actual implementation
            
            description = "This is a placeholder business description generated by AI processing. Implement actual Gemini-based description generation here."
            
            print(f"✅ [PLACEHOLDER] Generated AI description")
            return description
            
        except Exception as e:
            print(f"❌ Error generating AI description: {e}")
            return None
    
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
        if not self.gemini_client or not reviews:
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
                self.gemini_client.ask, prompt, disable_thinking=True
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
        fid: Optional[str] = None,
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
            fid: Feature ID if already known (if not provided, will search for it)
            sort: Review sorting method - "qualityScore", "newestFirst", "ratingHigh", "ratingLow"
            filter_keyword: Optional keyword to filter reviews
            max_results: Maximum number of reviews to fetch (default 20)
            generate_summary: Whether to generate an LLM summary of the reviews (default True)

        Returns:
            Structured business reviews result or None if no business match found
        """
        try:
            # Step 1: Get FID if not provided
            if not fid:
                print(f"🔍 Searching for business FID...")
                business_info = await self._find_business_in_search(business_name, business_location)
                if not business_info or not business_info.get("fid"):
                    print(f"❌ Could not find FID for business: {business_name}")
                    return None
                fid = business_info["fid"]
                print(f"✅ Found FID: {fid}")
            else:
                # Get business info for context
                business_info = await self._find_business_in_search(business_name, business_location)
                if not business_info:
                    business_info = {}

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
                business_info.get("search_url"),
                business_info.get("rating"),
                business_info.get("review_count"),
                business_info.get("address"),
                business_info.get("address_quality"),
                business_info.get("website"),
                business_info.get("domain"),
                business_info.get("phone"),
                business_info.get("latitude"),
                business_info.get("longitude"),
                business_info.get("business_type"),
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
    
    def to_dict(self, business_data: BusinessData) -> Dict:
        """Convert BusinessData to dictionary"""
        return business_data.model_dump(exclude_none=True)
    
    def to_json(self, business_data: BusinessData) -> str:
        """Convert BusinessData to JSON string"""
        return business_data.model_dump_json(indent=2, exclude_none=True)


# Example usage and testing
async def main():
    """Test run for GBPResearcher using the new get_business_data() interface"""
    print("🏢 Testing GBP Researcher - New Interface")
    print("=" * 60)
    
    # Initialize researcher
    researcher = GBPResearcher()
    
    # Hardcoded test parameters
    business_name = "Caccia's Home Services"
    business_location = "San Mateo, California"
    
    print(f"\n🔍 Testing: {business_name}")
    print(f"📍 Location: {business_location}")
    print("-" * 50)
    
    try:
        # Use the new get_business_data method
        print("📊 Getting business data using new interface...")
        cleaned_html, maps_data, reviews = await researcher.get_business_data(
            business_name=business_name,
            business_location=business_location,
            max_reviews=10,
            review_sort="newestFirst"
        )
        
        # Test the return values
        print(f"\n✅ RETURN VALUES TEST:")
        print(f"📄 HTML Type: {type(cleaned_html)} - {'✅ String' if isinstance(cleaned_html, (str, type(None))) else '❌ Wrong type'}")
        print(f"🗺️ Maps Data Type: {type(maps_data)} - {'✅ Dict' if isinstance(maps_data, (dict, type(None))) else '❌ Wrong type'}")
        print(f"📝 Reviews Type: {type(reviews)} - {'✅ List' if isinstance(reviews, list) else '❌ Wrong type'}")
        
        # Display results
        if cleaned_html:
            print(f"\n🌐 CLEANED HTML:")
            print(f"   Length: {len(cleaned_html)} characters")
            print(f"   Preview: {cleaned_html[:200]}...")
        else:
            print(f"\n🌐 CLEANED HTML: ❌ None")
            
        if maps_data:
            print(f"\n🗺️ MAPS DATA:")
            print(f"   Type: {type(maps_data)}")
            print(f"   Keys: {list(maps_data.keys()) if isinstance(maps_data, dict) else 'Not a dict'}")
            if isinstance(maps_data, dict):
                import json
                print(f"   Sample: {json.dumps(maps_data, indent=2)[:500]}...")
        else:
            print(f"\n🗺️ MAPS DATA: ❌ None")
            
        if reviews:
            print(f"\n📝 REVIEWS:")
            print(f"   Count: {len(reviews)}")
            print(f"   Type of first review: {type(reviews[0]) if reviews else 'No reviews'}")
            
            # Show first 2 reviews
            for i, review in enumerate(reviews[:2]):
                print(f"\n   📋 Review #{i+1}:")
                print(f"      👤 Author: {review.author_name}")
                print(f"      ⭐ Rating: {review.rating}/5")
                print(f"      📅 Date: {review.review_date}")
                if review.review_text:
                    print(f"      💬 Text: {review.review_text[:100]}...")
        else:
            print(f"\n📝 REVIEWS: Empty list")
        
        # Interface validation
        print(f"\n🧪 INTERFACE VALIDATION:")
        print("=" * 40)
        html_valid = cleaned_html is None or isinstance(cleaned_html, str)
        maps_valid = maps_data is None or isinstance(maps_data, dict)
        reviews_valid = isinstance(reviews, list) and all(hasattr(r, 'author_name') for r in reviews)
        
        print(f"✅ HTML Return Type: {'PASS' if html_valid else 'FAIL'}")
        print(f"✅ Maps Data Return Type: {'PASS' if maps_valid else 'FAIL'}")
        print(f"✅ Reviews Return Type: {'PASS' if reviews_valid else 'FAIL'}")
        
        all_valid = html_valid and maps_valid and reviews_valid
        print(f"\n🎯 OVERALL INTERFACE: {'✅ PASS' if all_valid else '❌ FAIL'}")
        
    except Exception as e:
        print(f"❌ Error during test run: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n🎉 GBP Researcher new interface test complete!")


if __name__ == "__main__":
    asyncio.run(main())
