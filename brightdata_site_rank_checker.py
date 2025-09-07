#!/usr/bin/env python3
"""
BrightData Site Rank Checker
============================

A site ranking checker that uses the improved BrightData search methods
with city, region, country location targeting for better localization.

This implementation uses the recommended approach from brightdata_test.py:
- Local Business Search with city-based UULE + near parameters
- Organic Search with multiple location signals
- Proper error handling and result parsing
"""

import json
import asyncio
import re
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from urllib.parse import urlparse

from brightdata import bdclient
from config import BRIGHTDATA_API_KEY


@dataclass
class RankingResult:
    """Result of a site ranking check"""
    position: Optional[int]
    title: str
    url: str
    snippet: str
    search_type: str  # "organic" or "local"


@dataclass
class RankingHit:
    """Compatible with the original site_ranking_checker interface"""
    position: int
    title: str
    url: str
    snippet: str


@dataclass
class SiteRankingReport:
    """Complete ranking report for a domain"""
    domain: str
    query: str
    location_str: str
    organic_results: List[RankingResult]
    local_results: List[RankingResult]
    best_organic_position: Optional[int]
    best_local_position: Optional[int]
    total_results_found: int


class SiteRankChecker:
    """
    Site ranking checker using BrightData with improved location targeting.
    
    Uses the recommended approach:
    - City-based UULE with canonical format
    - Multiple location signals (uule + near)
    - Separate handling for organic vs local business searches
    """
    
    def __init__(self, api_token: str = BRIGHTDATA_API_KEY):
        """Initialize with BrightData API token"""
        self.client = bdclient(api_token=api_token)
        
    def _normalize_domain(self, domain: str) -> str:
        """Normalize domain for comparison"""
        domain = domain.strip().lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    
    def _hostname_from_url(self, url: str) -> Optional[str]:
        """Extract hostname from URL"""
        try:
            parsed = urlparse(url if "://" in url else f"http://{url}")
            host = (parsed.hostname or "").lower()
            if host.startswith("www."):
                host = host[4:]
            return host or None
        except Exception:
            return None
    
    def _url_matches_domain(self, url: str, target_domain: str) -> bool:
        """Check if URL matches target domain (including subdomains)"""
        host = self._hostname_from_url(url)
        if not host:
            return False
        target = self._normalize_domain(target_domain)
        return host == target or host.endswith("." + target)
    
    def _sanitize_json_string(self, json_str: str) -> str:
        """
        Sanitize JSON string by fixing common JSON parsing issues.
        
        BrightData sometimes returns JSON with various issues:
        - Invalid control characters
        - Malformed structure (missing commas, trailing commas)
        - Encoding issues
        """
        if not json_str:
            return json_str
            
        # Remove common problematic control characters
        # Keep only printable characters, spaces, tabs, and newlines
        sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', json_str)
        
        # Additional cleanup for common JSON issues
        # Fix any double-escaped quotes that might cause issues
        sanitized = sanitized.replace('\\"', '"')
        
        # Fix common structural issues
        # Remove trailing commas before closing brackets/braces
        sanitized = re.sub(r',(\s*[}\]])', r'\1', sanitized)
        
        # Fix missing commas between array/object elements (basic cases)
        # This is a simple heuristic - look for "}{"  or "]{"  patterns
        sanitized = re.sub(r'}\s*{', '},{', sanitized)
        sanitized = re.sub(r']\s*{', '],[{', sanitized)
        sanitized = re.sub(r'}\s*\[', '},[', sanitized)
        
        # Fix missing commas between string values and next keys
        # Look for patterns like: "value" "key": or "value" {
        sanitized = re.sub(r'"\s+"([^:]+":)', r'", "\1', sanitized)
        sanitized = re.sub(r'"\s+{', '", {', sanitized)
        
        # Fix missing commas after closing braces/brackets before strings
        sanitized = re.sub(r'}\s+"', '}, "', sanitized)
        sanitized = re.sub(r']\s+"', '], "', sanitized)
        
        return sanitized
    
    def _safe_json_parse(self, json_str: str) -> dict:
        """
        Safely parse JSON with multiple fallback strategies.
        
        Returns empty dict if all parsing attempts fail.
        """
        if not json_str:
            return {}
            
        # Strategy 1: Try parsing as-is
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
            
        # Strategy 2: Try with sanitization
        try:
            sanitized = self._sanitize_json_string(json_str)
            return json.loads(sanitized)
        except json.JSONDecodeError:
            pass
            
        # Strategy 3: Try to extract valid JSON from the beginning
        try:
            # Find the first complete JSON object
            brace_count = 0
            for i, char in enumerate(json_str):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        # Found complete JSON object
                        partial_json = json_str[:i+1]
                        sanitized_partial = self._sanitize_json_string(partial_json)
                        return json.loads(sanitized_partial)
        except (json.JSONDecodeError, IndexError):
            pass
            
        # Strategy 4: Try to fix specific known issues
        try:
            # Remove any trailing incomplete data after the last complete brace
            last_brace = json_str.rfind('}')
            if last_brace > 0:
                truncated = json_str[:last_brace + 1]
                sanitized_truncated = self._sanitize_json_string(truncated)
                return json.loads(sanitized_truncated)
        except json.JSONDecodeError:
            pass
            
        # All strategies failed
        print(f"⚠️  All JSON parsing strategies failed for data of length {len(json_str)}")
        return {}
    
    def _build_search_url(
        self,
        q: str,
        gl: str,
        hl: str,
        city: Optional[str] = None,
        region: Optional[str] = None,
        country: Optional[str] = None,
        search_type: str = "organic",
        num: int = 100,
        start: int = 0
    ) -> str:
        """Build search URL with optional location targeting and pagination support"""
        from urllib.parse import urlencode
        
        params = {
            "q": q,
            "gl": gl,
            "hl": hl,
            "num": num,
            "brd_json": 1
        }
        
        # Only add location parameters if location data is provided
        if city and region and country:
            # City-based UULE (canonical format) - recommended approach
            uule = f"{city},{region},{country}"
            # Additional location reinforcement
            near = f"{city}, {region}"
            
            params["uule"] = uule
            params["near"] = near
        
        # Add pagination support
        if start > 0:
            params["start"] = start
        
        # Add local search parameter if needed
        if search_type == "local":
            params["tbm"] = "lcl"
            params["udm"] = 1
            
        return "https://www.google.com/search?" + urlencode(params, doseq=True)
    
    def _fetch_search_results(self, url: str) -> Dict:
        """Fetch search results via BrightData"""
        try:
            results = self.client.scrape(url)
            parsed_json = self.client.parse_content(results)
            return parsed_json
        except Exception as e:
            print(f"Error fetching results: {e}")
            return {}
    
    def _parse_organic_results(self, data: Dict, target_domain: str) -> List[RankingResult]:
        """Parse organic search results and find domain matches"""
        results = []
        
        if 'text' not in data or not data['text']:
            return results
            
        try:
            # Use safe JSON parsing with multiple fallback strategies
            parsed_data = self._safe_json_parse(data['text'])
            
            # Look for organic results
            organic_results = parsed_data.get('organic', [])
            
            print(f"\n🔍 DEBUG: Organic Search Results from BrightData:")
            print("-" * 60)
            print(f"📊 AVAILABLE FIELDS IN RESPONSE: {list(parsed_data.keys())}")
            print(f"✅ Found {len(organic_results)} organic results returned by BrightData (requested 100)")
            print()
            
            print(f"📋 ALL ORGANIC RESULTS:")
            print("=" * 80)
            
            for idx, result in enumerate(organic_results, 1):
                url = result.get('link', result.get('url', ''))
                title = result.get('title', '')
                snippet = result.get('snippet', result.get('description', ''))
                
                # Print every organic result
                print(f"  {idx}. {title}")
                print(f"     URL: {url if url else 'No URL'}")
                
                # Check if it matches our target domain
                if url and self._url_matches_domain(url, target_domain):
                    print(f"     🎯 MATCH! This result matches target domain '{target_domain}'")
                    results.append(RankingResult(
                        position=idx,
                        title=title,
                        url=url,
                        snippet=snippet,
                        search_type="organic"
                    ))
                else:
                    print(f"     ❌ No match for target domain '{target_domain}'")
                print()
                    
            print("=" * 80)
            print(f"\n📊 ORGANIC SUMMARY: Processed {len(organic_results)} organic results from BrightData")
            print(f"🎯 Found {len(results)} matching organic results for domain '{target_domain}'")
                    
        except json.JSONDecodeError as e:
            print(f"Error parsing organic results: {e}")
            print(f"Raw data length: {len(data.get('text', ''))}")
            # Print first 200 chars of raw data for debugging
            raw_text = data.get('text', '')
            if raw_text:
                print(f"Raw data preview: {raw_text[:200]}...")
            else:
                print("No raw text data available")
            
        return results
    
    def _parse_local_results(self, data: Dict, target_domain: str) -> List[RankingResult]:
        """Parse local business results and find domain matches"""
        results = []
        
        if 'text' not in data or not data['text']:
            return results
            
        try:
            # Use safe JSON parsing with multiple fallback strategies
            parsed_data = self._safe_json_parse(data['text'])
            
            # Look for local business results in different possible fields
            local_fields = ['snack_pack', 'local_results', 'local_pack']
            
            print(f"\n🔍 DEBUG: All Local Business Results Found:")
            print("-" * 60)
            
            # First, let's see what fields are available
            print(f"📊 AVAILABLE FIELDS IN RESPONSE: {list(parsed_data.keys())}")
            print()
            
            for field in local_fields:
                if field in parsed_data:
                    local_results = parsed_data[field]
                    print(f"✅ Found {len(local_results)} results in '{field}' field (requested 100)")
                    
                    # Print raw structure of first few results for debugging
                    print(f"\n📋 RAW STRUCTURE DEBUG (first 3 results):")
                    print("=" * 50)
                    for debug_idx, debug_result in enumerate(local_results[:3], 1):
                        print(f"Result #{debug_idx} raw data:")
                        import pprint
                        pprint.pprint(debug_result, width=80, depth=3)
                        print("-" * 30)
                    print("=" * 50)
                    
                    print(f"\n📝 PROCESSING ALL {len(local_results)} RESULTS:")
                    print("-" * 40)
                    
                    for idx, result in enumerate(local_results, 1):
                        # Try different possible field names for website (based on actual BrightData structure)
                        website = result.get('site', result.get('website', result.get('link', result.get('url', ''))))
                        title = result.get('name', result.get('title', ''))
                        snippet = result.get('description', result.get('snippet', ''))
                        rating = result.get('rating', 'N/A')
                        address = result.get('address', 'N/A')
                        reviews_count = result.get('reviews_cnt', 'N/A')
                        business_type = result.get('type', 'N/A')
                        work_status = result.get('work_status', 'N/A')
                        
                        # Print all business info found
                        print(f"  {idx}. {title}")
                        print(f"     Website: {website if website else 'No website'}")
                        print(f"     Address: {address}")
                        print(f"     Rating: {rating} ({reviews_count} reviews)")
                        print(f"     Type: {business_type}")
                        print(f"     Status: {work_status}")
                        
                        # Also show all available keys for debugging
                        print(f"     Available keys: {list(result.keys())}")
                        
                        # Check if it matches our target domain
                        if website and self._url_matches_domain(website, target_domain):
                            print(f"     ✅ MATCH: This result matches target domain '{target_domain}'")
                            results.append(RankingResult(
                                position=idx,
                                title=title,
                                url=website,
                                snippet=snippet,
                                search_type="local"
                            ))
                        else:
                            print(f"     ❌ No match for target domain '{target_domain}'")
                        print()
                    
                    # If we found results in this field, don't check others
                    if local_results:
                        print(f"\n📊 SUMMARY: Processed {len(local_results)} local business results")
                        print(f"🎯 Found {len(results)} matching results for domain '{target_domain}'")
                        break
            
            if not any(field in parsed_data for field in local_fields):
                print("No local business results found in any expected fields")
                print(f"Available fields: {list(parsed_data.keys())}")
                        
        except json.JSONDecodeError as e:
            print(f"Error parsing local results: {e}")
            print(f"Raw data length: {len(data.get('text', ''))}")
            # Print first 200 chars of raw data for debugging
            raw_text = data.get('text', '')
            if raw_text:
                print(f"Raw data preview: {raw_text[:200]}...")
            else:
                print("No raw text data available")
            
        return results
    
    def _search_local_with_pagination(
        self,
        q: str,
        gl: str,
        hl: str,
        city: Optional[str],
        region: Optional[str],
        country: Optional[str],
        target_domain: str,
        max_pages: int = 3,
        results_per_page: int = 20
    ) -> List[RankingResult]:
        """
        Search local businesses with pagination support.
        Stops when domain is found OR after max_pages (default 3) reached.
        """
        all_results = []
        total_processed = 0
        
        print(f"\n🔄 PAGINATED LOCAL BUSINESS SEARCH")
        print("=" * 60)
        print(f"Target Domain: {target_domain}")
        print(f"Max Pages: {max_pages} (up to {max_pages * results_per_page} total results)")
        print("=" * 60)
        
        for page in range(max_pages):
            start_index = page * results_per_page
            
            # Build URL for this page
            url = self._build_search_url(
                q=q, gl=gl, hl=hl, city=city, region=region, country=country,
                search_type="local", num=results_per_page, start=start_index
            )
            
            print(f"\n📄 PAGE {page + 1} (results {start_index + 1}-{start_index + results_per_page})")
            print(f"URL: {url}")
            print("-" * 40)
            
            # Fetch results for this page
            data = self._fetch_search_results(url)
            
            if 'text' not in data or not data['text']:
                print(f"❌ No data returned for page {page + 1}")
                break
                
            try:
                # Use safe JSON parsing with multiple fallback strategies
                parsed_data = self._safe_json_parse(data['text'])
                local_fields = ['snack_pack', 'local_results', 'local_pack']
                
                page_results = []
                for field in local_fields:
                    if field in parsed_data:
                        local_results = parsed_data[field]
                        print(f"✅ Found {len(local_results)} results in '{field}' field")
                        
                        for idx, result in enumerate(local_results, 1):
                            global_position = start_index + idx
                            
                            # Extract business info
                            website = result.get('site', result.get('website', result.get('link', result.get('url', ''))))
                            title = result.get('name', result.get('title', ''))
                            snippet = result.get('description', result.get('snippet', ''))
                            address = result.get('address', 'N/A')
                            rating = result.get('rating', 'N/A')
                            
                            print(f"  {global_position}. {title}")
                            print(f"     Website: {website if website else 'No website'}")
                            print(f"     Address: {address}")
                            
                            # Check for domain match
                            if website and self._url_matches_domain(website, target_domain):
                                print(f"     🎯 MATCH FOUND! Position #{global_position}")
                                match_result = RankingResult(
                                    position=global_position,
                                    title=title,
                                    url=website,
                                    snippet=snippet,
                                    search_type="local"
                                )
                                page_results.append(match_result)
                                all_results.append(match_result)
                            else:
                                print(f"     ❌ No match")
                            print()
                        
                        total_processed += len(local_results)
                        
                        # If we found matches on this page, stop searching
                        if page_results:
                            print(f"✅ Found {len(page_results)} matches on page {page + 1}")
                            print(f"🛑 Stopping search - domain found!")
                            print(f"\n📊 EARLY STOP SUMMARY:")
                            print(f"Pages Searched: {page + 1}")
                            print(f"Total Results Processed: {total_processed}")
                            print(f"Domain Matches Found: {len(all_results)}")
                            print("=" * 60)
                            return all_results
                        
                        break  # Only process first matching field
                
                # If no results found on this page, stop pagination
                if not any(field in parsed_data for field in local_fields):
                    print(f"❌ No more results available after page {page + 1}")
                    break
                    
            except json.JSONDecodeError as e:
                print(f"❌ Error parsing page {page + 1}: {e}")
                print(f"Raw data length: {len(data.get('text', ''))}")
                # Print first 200 chars of raw data for debugging
                raw_text = data.get('text', '')
                if raw_text:
                    print(f"Raw data preview: {raw_text[:200]}...")
                else:
                    print("No raw text data available")
                break
        
        print(f"\n📊 PAGINATION SUMMARY:")
        print(f"Pages Searched: {page + 1}")
        print(f"Total Results Processed: {total_processed}")
        print(f"Domain Matches Found: {len(all_results)}")
        print("=" * 60)
        
        return all_results
    
    def check_site_ranking(
        self,
        domain: str,
        query: str,
        city: Optional[str] = None,
        region: Optional[str] = None,
        country: Optional[str] = None,
        gl: str = "us",
        hl: str = "en",
        max_results: int = 100
    ) -> SiteRankingReport:
        """
        Check site ranking for both organic and local business searches.
        
        Args:
            domain: Target domain (e.g., "example.com")
            query: Search query (e.g., "laundromat")
            city: City name (e.g., "San Francisco")
            region: State/region (e.g., "California")
            country: Country (default: "United States")
            gl: Google country code (default: "us")
            hl: Google language code (default: "en")
            max_results: Maximum results to check (default: 100)
            
        Returns:
            SiteRankingReport with organic and local results
        """
        # Build location string only if location data is provided
        location_parts = [part for part in [city, region, country] if part]
        location_str = ", ".join(location_parts) if location_parts else "No location specified"
        
        # Build URLs for both search types
        organic_url = self._build_search_url(
            q=query, gl=gl, hl=hl, city=city, region=region, country=country,
            search_type="organic", num=max_results
        )
        
        local_url = self._build_search_url(
            q=query, gl=gl, hl=hl, city=city, region=region, country=country,
            search_type="local", num=max_results
        )
        
        print(f"Checking rankings for {domain} in {location_str}")
        print(f"Query: '{query}'")
        print(f"Organic URL: {organic_url}")
        print(f"Local URL: {local_url}")
        
        # Fetch results
        organic_data = self._fetch_search_results(organic_url)
        local_data = self._fetch_search_results(local_url)
        
        # Parse organic results
        organic_results = self._parse_organic_results(organic_data, domain)
        
        # Use paginated local search instead of single request
        print(f"\n🔄 Switching to paginated local business search...")
        local_results = self._search_local_with_pagination(
            q=query, gl=gl, hl=hl, city=city, region=region, country=country,
            target_domain=domain, max_pages=3, results_per_page=20
        )
        
        # Extract total counts from BrightData response for reporting
        organic_total = 0
        local_total = 0
        
        try:
            if 'text' in organic_data and organic_data['text']:
                # Use safe JSON parsing with multiple fallback strategies
                organic_parsed = self._safe_json_parse(organic_data['text'])
                organic_total = len(organic_parsed.get('organic', []))
        except:
            pass
            
        # For paginated local search, we'll estimate total processed results
        # The pagination method will have processed up to 3 pages * 20 results = 60 total
        local_total = min(60, 3 * 20)  # Up to 3 pages of 20 results each
        
        # Print final summary
        print(f"\n" + "=" * 80)
        print(f"🎯 FINAL BRIGHTDATA RESULTS SUMMARY")
        print("=" * 80)
        print(f"Organic Results from BrightData: {organic_total}")
        print(f"Local Business Results from BrightData: {local_total}")
        print(f"Total Results from BrightData: {organic_total + local_total}")
        print("-" * 40)
        print(f"Organic Matches Found: {len(organic_results)}")
        print(f"Local Business Matches Found: {len(local_results)}")
        print(f"Total Matches Found: {len(organic_results) + len(local_results)}")
        print("=" * 80)
        
        # Find best positions
        best_organic = min([r.position for r in organic_results], default=None)
        best_local = min([r.position for r in local_results], default=None)
        
        return SiteRankingReport(
            domain=domain,
            query=query,
            location_str=location_str,
            organic_results=organic_results,
            local_results=local_results,
            best_organic_position=best_organic,
            best_local_position=best_local,
            total_results_found=len(organic_results) + len(local_results)
        )
    
    async def check_site_ranking_async(
        self,
        domain: str,
        query: str,
        city: Optional[str] = None,
        region: Optional[str] = None,
        country: Optional[str] = None,
        gl: str = "us",
        hl: str = "en",
        max_results: int = 100
    ) -> SiteRankingReport:
        """
        Async version of check_site_ranking.
        
        Note: Currently runs synchronously but wrapped for async compatibility.
        Future versions could implement true async BrightData calls.
        """
        return await asyncio.get_event_loop().run_in_executor(
            None,
            self.check_site_ranking,
            domain, query, city, region, country, gl, hl, max_results
        )
    
    def print_ranking_report(self, report: SiteRankingReport) -> None:
        """Print a formatted ranking report"""
        print("\n" + "=" * 80)
        print(f"SITE RANKING REPORT")
        print("=" * 80)
        print(f"Domain: {report.domain}")
        print(f"Query: '{report.query}'")
        print(f"Location: {report.location_str}")
        print(f"Total Results Found: {report.total_results_found}")
        print("=" * 80)
        
        # Organic results
        print(f"\n🔍 ORGANIC SEARCH RESULTS")
        print("-" * 40)
        if report.organic_results:
            print(f"Best Position: #{report.best_organic_position}")
            for result in sorted(report.organic_results, key=lambda x: x.position):
                print(f"  #{result.position}: {result.title}")
                print(f"     URL: {result.url}")
                if result.snippet:
                    snippet = result.snippet[:100] + "..." if len(result.snippet) > 100 else result.snippet
                    print(f"     Snippet: {snippet}")
                print()
        else:
            print("  No organic results found")
        
        # Local business results
        print(f"\n🏢 LOCAL BUSINESS RESULTS")
        print("-" * 40)
        if report.local_results:
            print(f"Best Position: #{report.best_local_position}")
            for result in sorted(report.local_results, key=lambda x: x.position):
                print(f"  #{result.position}: {result.title}")
                print(f"     URL: {result.url}")
                if result.snippet:
                    snippet = result.snippet[:100] + "..." if len(result.snippet) > 100 else result.snippet
                    print(f"     Snippet: {snippet}")
                print()
        else:
            print("  No local business results found")
        
        # Summary counts
        print(f"\n📊 RESULTS SUMMARY")
        print("-" * 40)
        print(f"Organic Results Found: {len(report.organic_results)}")
        print(f"Local Business Results Found: {len(report.local_results)}")
        print(f"Total Results Found: {report.total_results_found}")
        
        print("=" * 80)
    
    def _parse_location_string(self, location: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Parse a location string into city, region, country components.
        
        Args:
            location: Location string like "San Francisco, California, USA" or "San Francisco, CA"
            
        Returns:
            Tuple of (city, region, country)
        """
        if not location:
            return None, None, None
            
        # Split by commas and clean up
        parts = [part.strip() for part in location.split(',')]
        
        if len(parts) == 1:
            # Just city
            return parts[0], None, None
        elif len(parts) == 2:
            # City, State/Region
            return parts[0], parts[1], None
        elif len(parts) >= 3:
            # City, State/Region, Country
            return parts[0], parts[1], parts[2]
        
        return None, None, None
    
    def _convert_ranking_results_to_hits(self, results: List[RankingResult]) -> List[RankingHit]:
        """Convert RankingResult objects to RankingHit objects for compatibility"""
        hits = []
        for result in results:
            if result.position is not None:
                hits.append(RankingHit(
                    position=result.position,
                    title=result.title,
                    url=result.url,
                    snippet=result.snippet
                ))
        return hits


# Wrapper functions for compatibility with daily_site_ranking_updater.py
async def check_domain_ranking(
    *,
    domain: str,
    query: str,
    location: Optional[str],
    max_pages: int = 10,
    results_per_page: int = 10,
    enhanced_mode: bool = False,
) -> Tuple[Optional[int], List[RankingHit]]:
    """
    Check a domain's Google organic ranking for a localized search.
    
    This function provides compatibility with the original site_ranking_checker interface
    while using BrightData for the actual search.
    
    Args:
        domain: Target business domain (e.g., "example.com")
        query: Search query (e.g., "laundromat")
        location: Localized location (e.g., "San Francisco, California")
        max_pages: How many pages to scan (default 10)
        results_per_page: Results per page (default 10)
        enhanced_mode: Whether to enable enhanced parsing mode (ignored for BrightData)
        
    Returns:
        (first_position, hits)
        - first_position: The first ranking position if found, otherwise None
        - hits: All matching hits with their positions
    """
    checker = SiteRankChecker()
    
    # Parse location string into components
    city, region, country = checker._parse_location_string(location)
    
    # Calculate max results based on pages and results per page
    max_results = min(100, max_pages * results_per_page)
    
    # Use the async version of the BrightData checker
    report = await checker.check_site_ranking_async(
        domain=domain,
        query=query,
        city=city,
        region=region,
        country=country or "United States",  # Default to US if not specified
        max_results=max_results
    )
    
    # Convert organic results to RankingHit format
    hits = checker._convert_ranking_results_to_hits(report.organic_results)
    
    # Return first position and all hits
    first_position = report.best_organic_position
    return first_position, hits


async def check_local_business_ranking(
    *,
    domain: str,
    query: str,
    location: str,
    max_business_results: int = 20,
) -> Tuple[Optional[int], List[RankingHit]]:
    """
    Check a domain's ranking within Google local business results.
    
    This function provides compatibility with the original site_ranking_checker interface
    while using BrightData for the actual search.
    
    Args:
        domain: Target business domain (e.g., "example.com")
        query: Search query (e.g., "laundromat")
        location: Localized location (e.g., "San Francisco, California")
        max_business_results: Maximum business results to check (default 20)
        
    Returns:
        (first_position, hits)
        - first_position: The first ranking position if found, otherwise None
        - hits: All matching hits with their positions
    """
    checker = SiteRankChecker()
    
    # Parse location string into components
    city, region, country = checker._parse_location_string(location)
    
    # Use the async version of the BrightData checker
    # For local business search, we'll use max_business_results as max_results
    report = await checker.check_site_ranking_async(
        domain=domain,
        query=query,
        city=city,
        region=region,
        country=country or "United States",  # Default to US if not specified
        max_results=max_business_results
    )
    
    # Convert local results to RankingHit format
    hits = checker._convert_ranking_results_to_hits(report.local_results)
    
    # Return first position and all hits
    first_position = report.best_local_position
    return first_position, hits


def main():
    """Demo usage of the SiteRankChecker"""
    checker = SiteRankChecker()
    
    # Test with location parameters
    print("🔍 Checking site ranking WITH location targeting...")
    report_with_location = checker.check_site_ranking(
        domain="hemisplumbing.com",
        query="plumber serving san mateo",
        city="San Mateo",
        region="California",
        country="United States",
        max_results=100
    )
    checker.print_ranking_report(report_with_location)


if __name__ == "__main__":
    main()
