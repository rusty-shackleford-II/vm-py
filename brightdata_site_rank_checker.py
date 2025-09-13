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
from loc_to_uule import uule_for_location
from site_to_cid import site_to_cid
from cached_geocoding_service import get_coordinates


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
class LocationSpec:
    """Specification for a ranking location"""
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    zipcode: Optional[str] = None
    
    def to_canonical_string(self) -> str:
        """Convert to canonical location string for display"""
        parts = []
        for part in [self.city, self.region, self.country, self.zipcode]:
            if part and part.strip():
                parts.append(part.strip())
        return ", ".join(parts) if parts else "No location"
    
    def to_query_suffix(self) -> str:
        """Convert to query suffix for search localization"""
        # Build suffix by including all available location components in order
        location_parts = []
        
        # Add location components in order: city, region, country, zipcode
        for component in [self.city, self.region, self.country, self.zipcode]:
            if component and component.strip():
                location_parts.append(component.strip())
        
        if location_parts:
            return f" {', '.join(location_parts)}"
        else:
            return ""
    
    def has_location_data(self) -> bool:
        """Check if this location spec has any location data"""
        return any([
            self.city and self.city.strip(),
            self.region and self.region.strip(), 
            self.country and self.country.strip(),
            self.zipcode and self.zipcode.strip()
        ])
    
    def to_geocoding_string(self) -> Optional[str]:
        """Convert to address string for geocoding"""
        if not self.has_location_data():
            return None
        
        # Build address string for geocoding
        parts = []
        if self.city and self.city.strip():
            parts.append(self.city.strip())
        if self.region and self.region.strip():
            parts.append(self.region.strip())
        if self.country and self.country.strip():
            parts.append(self.country.strip())
        if self.zipcode and self.zipcode.strip():
            # Add zipcode at the end
            parts.append(self.zipcode.strip())
        
        return ", ".join(parts) if parts else None


@dataclass
class SiteRankingReport:
    """Complete ranking report for a domain"""
    domain: str
    query: str
    location_spec: LocationSpec
    organic_results: List[RankingResult]
    local_results: List[RankingResult]
    best_organic_position: Optional[int]
    best_local_position: Optional[int]
    total_results_found: int
    lat: Optional[float] = None
    lon: Optional[float] = None


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
    
    def _filter_image_data_for_debug(self, data: dict) -> dict:
        """
        Filter out or truncate image data from response for cleaner debugging output.
        
        Args:
            data: The raw response data from BrightData
            
        Returns:
            Filtered data with image content truncated or removed
        """
        import copy
        import json
        
        # Create a deep copy to avoid modifying the original data
        filtered_data = copy.deepcopy(data)
        
        # If there's text content, try to parse and filter it
        if 'text' in filtered_data and filtered_data['text']:
            try:
                # Parse the JSON text content
                parsed_text = json.loads(filtered_data['text'])
                
                # Filter image data from various possible locations
                self._filter_images_recursive(parsed_text)
                
                # Convert back to JSON string
                filtered_data['text'] = json.dumps(parsed_text, indent=2)
                
            except json.JSONDecodeError:
                # If JSON parsing fails, do basic string filtering
                text_content = filtered_data['text']
                # Remove base64 image data (look for data:image patterns)
                import re
                text_content = re.sub(r'"image":"data:image/[^"]*"', '"image":"[BASE64_IMAGE_DATA_TRUNCATED]"', text_content)
                filtered_data['text'] = text_content
        
        return filtered_data
    
    def _filter_images_recursive(self, obj):
        """
        Recursively filter image data from nested dictionaries and lists.
        
        Args:
            obj: Dictionary or list to filter (modified in-place)
        """
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == 'image' and isinstance(value, str):
                    # Check if it's base64 image data
                    if value.startswith('data:image/'):
                        # Truncate to first 50 characters + indicator
                        obj[key] = value[:50] + '...[BASE64_IMAGE_DATA_TRUNCATED]'
                elif isinstance(value, (dict, list)):
                    self._filter_images_recursive(value)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    self._filter_images_recursive(item)

    def _find_cid_in_nested_dict(self, data: dict, path: str = "") -> tuple[Optional[str], Optional[str]]:
        """
        Recursively search for CID in nested dictionary structure.
        
        Args:
            data: Dictionary to search through
            path: Current path for debugging (internal use)
            
        Returns:
            Tuple of (cid_value, field_path) or (None, None) if not found
        """
        if not isinstance(data, dict):
            return None, None
            
        # Direct field name matches (case insensitive)
        cid_field_names = ['cid', 'id', 'business_id', 'place_id', 'google_id', 'gid', 'place_cid']
        
        # First, check direct fields in current level
        for key, value in data.items():
            key_lower = key.lower()
            
            # Check if this key matches a CID field name
            if key_lower in cid_field_names and value:
                # Convert to string and validate it looks like a CID
                cid_str = str(value).strip()
                if cid_str and cid_str.isdigit() and len(cid_str) > 10:  # Basic CID validation
                    current_path = f"{path}.{key}" if path else key
                    return cid_str, current_path
            
            # Also check if the key contains 'cid' or 'id' and value looks like a CID
            elif ('cid' in key_lower or 'id' in key_lower) and value:
                cid_str = str(value).strip()
                if cid_str and cid_str.isdigit() and len(cid_str) > 10:  # Basic CID validation
                    current_path = f"{path}.{key}" if path else key
                    return cid_str, current_path
        
        # Then recursively search nested dictionaries and lists
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            
            if isinstance(value, dict):
                # Recursive search in nested dict
                found_cid, found_path = self._find_cid_in_nested_dict(value, current_path)
                if found_cid:
                    return found_cid, found_path
                    
            elif isinstance(value, list):
                # Search in list items
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        item_path = f"{current_path}[{i}]"
                        found_cid, found_path = self._find_cid_in_nested_dict(item, item_path)
                        if found_cid:
                            return found_cid, found_path
        
        return None, None

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
        location_spec: Optional[LocationSpec] = None,
        search_type: str = "organic",
        num: int = 100,
        start: int = 0
    ) -> str:
        """Build search URL with optional location targeting and pagination support"""
        from urllib.parse import urlencode
        
        # Build the query with optional location appended
        query = q
        if location_spec and location_spec.has_location_data():
            query = q + location_spec.to_query_suffix()
        
        params = {
            "q": query,
            "gl": gl,
            "hl": hl,
            "num": num,
            "brd_json": 1
        }
        
        # Add UULE parameter if location data is provided
        if location_spec and location_spec.has_location_data():
            try:
                params["uule"] = uule_for_location(
                    city=location_spec.city,
                    region=location_spec.region,
                    country=location_spec.country,
                    zipcode=location_spec.zipcode
                )
            except ValueError:
                # uule_for_location requires at least one non-empty part, but we already checked has_location_data()
                pass
        
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
        print(f"   🌐 Searching URL: {url}")
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
            
            for idx, result in enumerate(organic_results, 1):
                url = result.get('link', result.get('url', ''))
                title = result.get('title', '')
                snippet = result.get('snippet', result.get('description', ''))
                
                # Check if it matches our target domain
                if url and self._url_matches_domain(url, target_domain):
                    results.append(RankingResult(
                        position=idx,
                        title=title,
                        url=url,
                        snippet=snippet,
                        search_type="organic"
                    ))
            
            if results:
                print(f"   ✅ Organic: Found {len(results)} matches in positions {[r.position for r in results]}")
            else:
                print(f"   ❌ Organic: No matches found in {len(organic_results)} results")
                    
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
    
    def _parse_local_results(self, data: Dict, target_cid: str) -> List[RankingResult]:
        """Parse local business results and find CID matches"""
        results = []
        
        if 'text' not in data or not data['text']:
            return results
            
        try:
            # Use safe JSON parsing with multiple fallback strategies
            parsed_data = self._safe_json_parse(data['text'])
            
            # Look for local business results in different possible fields
            local_fields = ['snack_pack', 'local_results', 'local_pack']
            
            for field in local_fields:
                if field in parsed_data:
                    local_results = parsed_data[field]
                    
                    for idx, result in enumerate(local_results, 1):
                        # Get basic info
                        title = result.get('name', result.get('title', ''))
                        
                        # Recursively search for CID in nested structure
                        business_cid, cid_field_used = self._find_cid_in_nested_dict(result)
                        
                        # Check if it matches our target CID
                        if business_cid and business_cid == target_cid:
                            snippet = result.get('description', result.get('snippet', ''))
                            results.append(RankingResult(
                                position=idx,
                                title=title,
                                url='',
                                snippet=snippet,
                                search_type="local"
                            ))
                    
                    # If we found results in this field, don't check others
                    if local_results:
                        if results:
                            print(f"   ✅ Local: Found {len(results)} matches in positions {[r.position for r in results]}")
                        else:
                            print(f"   ❌ Local: No matches found in {len(local_results)} results")
                        break
            
            if not any(field in parsed_data for field in local_fields):
                print("   ❌ Local: No local business results found")
                        
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
        location_spec: Optional[LocationSpec],
        target_cid: str,
        max_pages: int = 3,
        results_per_page: int = 20
    ) -> List[RankingResult]:
        """
        Search local businesses with pagination support.
        Stops when CID is found OR after max_pages (default 3) reached.
        """
        all_results = []
        total_processed = 0
        
        print(f"   🔄 Searching local businesses (up to {max_pages} pages)...")
        
        for page in range(max_pages):
            start_index = page * results_per_page
            
            # Build URL for this page
            url = self._build_search_url(
                q=q, gl=gl, hl=hl, location_spec=location_spec,
                search_type="local", num=results_per_page, start=start_index
            )
            
            
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
                        
                        for idx, result in enumerate(local_results, 1):
                            global_position = start_index + idx
                            
                            # Get basic info
                            title = result.get('name', result.get('title', ''))
                            snippet = result.get('description', result.get('snippet', ''))
                            
                            # Recursively search for CID in nested structure
                            business_cid, cid_field_used = self._find_cid_in_nested_dict(result)
                            
                            # Check for CID match
                            if business_cid and business_cid == target_cid:
                                match_result = RankingResult(
                                    position=global_position,
                                    title=title,
                                    url='',
                                    snippet=snippet,
                                    search_type="local"
                                )
                                page_results.append(match_result)
                                all_results.append(match_result)
                        
                        total_processed += len(local_results)
                        
                        # If we found matches on this page, stop searching
                        if page_results:
                            print(f"   ✅ Local (paginated): Found {len(page_results)} matches in positions {[r.position for r in page_results]}")
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
        
        if all_results:
            print(f"   ✅ Local (paginated): Found {len(all_results)} matches in positions {[r.position for r in all_results]}")
        else:
            print(f"   ❌ Local (paginated): No matches found in {total_processed} results")
        
        return all_results
    
    def check_site_ranking(
        self,
        domain: str,
        query: str,
        ranking_locations: List[Dict[str, str]],
        gl: str = "us",
        hl: str = "en",
        max_results: int = 100,
        cid: Optional[str] = None,
        business_name: Optional[str] = None,
        city: Optional[str] = None,
        region: Optional[str] = None,
        country: Optional[str] = None
    ) -> List[SiteRankingReport]:
        """
        Check site ranking for both organic and local business searches.
        
        Args:
            domain: Target domain (e.g., "example.com")
            query: Search query (e.g., "laundromat")
            ranking_locations: List of location dicts with optional city, region, country, zipcode keys.
                              Empty list means non-localized organic search only.
            gl: Google country code (default: "us")
            hl: Google language code (default: "en")
            max_results: Maximum results to check (default: 100)
            cid: Optional CID for local business search
            business_name: Optional business name for automatic CID lookup
            city: Client's city from clients table (used for CID lookup if no cid provided)
            region: Client's region from clients table (used for CID lookup if no cid provided)
            country: Client's country from clients table (used for CID lookup if no cid provided)
            
        Returns:
            List[SiteRankingReport] - one report per ranking location, or single non-localized report if empty list
        """
        # Determine which locations to check
        locations_to_check = []
        
        if ranking_locations:
            # Use the ranking_locations parameter
            for location_dict in ranking_locations:
                location_spec = LocationSpec(
                    city=location_dict.get('city'),
                    region=location_dict.get('region'),
                    country=location_dict.get('country'),
                    zipcode=location_dict.get('zipcode')
                )
                locations_to_check.append(location_spec)
        else:
            # Empty list means non-localized organic search only
            locations_to_check = [LocationSpec()]
        
        # For empty ranking_locations, force non-localized organic search only
        if not ranking_locations:
            effective_cid = None
            effective_business_name = None
            print(f"🔍 Checking organic rankings for {domain} with query '{query}' (no location targeting)")
        else:
            # Localized search: do CID lookup ONCE for all locations
            effective_cid = cid
            effective_business_name = business_name
            
            # Auto-fetch CID if business_name is provided and no CID was given
            if not effective_cid and business_name and city and region and country:
                print(f"🔄 Fetching CID for business '{business_name}' using client location ({city}, {region}, {country})...")
                try:
                    import asyncio
                    effective_cid = asyncio.run(site_to_cid(business_name, city, region, country, domain))
                    if effective_cid:
                        print(f"✅ Successfully fetched CID: {effective_cid}")
                    else:
                        print(f"❌ Could not find CID for business '{business_name}' with domain '{domain}'")
                except Exception as e:
                    print(f"⚠️ Error fetching CID: {e}")
                    effective_cid = None
            elif not effective_cid and business_name and not (city and region and country):
                print(f"⚠️ Cannot fetch CID for business '{business_name}' - client city, region, and country are required")
            
            if effective_cid:
                print(f"🔍 Checking rankings for {domain} with query '{query}' across {len(locations_to_check)} locations (CID: {effective_cid})")
            else:
                print(f"🔍 Checking rankings for {domain} with query '{query}' across {len(locations_to_check)} locations (organic only)")
        
        reports = []
        
        for i, location_spec in enumerate(locations_to_check, 1):
            if len(locations_to_check) > 1:
                location_str = location_spec.to_canonical_string()
                print(f"\n📍 Location {i}/{len(locations_to_check)}: {location_str}")
            
            report = self._check_site_ranking_for_location(
                domain=domain,
                query=query,
                location_spec=location_spec,
                gl=gl,
                hl=hl,
                max_results=max_results,
                cid=effective_cid  # Use the resolved CID for all locations
            )
            reports.append(report)
        
        return reports
    
    def _check_site_ranking_for_location(
        self,
        domain: str,
        query: str,
        location_spec: LocationSpec,
        gl: str = "us",
        hl: str = "en",
        max_results: int = 100,
        cid: Optional[str] = None
    ) -> SiteRankingReport:
        """Check site ranking for a single location"""
        
        # Build URL for organic search
        organic_url = self._build_search_url(
            q=query, gl=gl, hl=hl, location_spec=location_spec,
            search_type="organic", num=max_results
        )
        
        # Fetch organic results
        organic_data = self._fetch_search_results(organic_url)
        
        # Parse organic results
        organic_results = self._parse_organic_results(organic_data, domain)
        
        # Only run local search if CID is provided and not None
        local_results = []
        if cid is not None and cid.strip():
            local_results = self._search_local_with_pagination(
                q=query, gl=gl, hl=hl, location_spec=location_spec,
                target_cid=cid, max_pages=3, results_per_page=20
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
            
        # For paginated local search, we'll estimate total processed results only if CID was provided
        if cid is not None and cid.strip():
            # The pagination method will have processed up to 3 pages * 20 results = 60 total
            local_total = min(60, 3 * 20)  # Up to 3 pages of 20 results each
        else:
            local_total = 0  # No local search performed
        
        # Print concise summary
        total_matches = len(organic_results) + len(local_results)
        if total_matches > 0:
            print(f"   📊 Total: {total_matches} matches found")
        else:
            print(f"   📊 Total: No matches found")
        
        # Get geocoding coordinates for the location
        lat, lon = None, None
        if location_spec.has_location_data():
            geocoding_address = location_spec.to_geocoding_string()
            if geocoding_address:
                try:
                    coords = get_coordinates(geocoding_address)
                    if coords:
                        lat, lon = coords
                except Exception as e:
                    pass  # Silently handle geocoding errors
        
        # Find best positions
        best_organic = min([r.position for r in organic_results], default=None)
        best_local = min([r.position for r in local_results], default=None)
        
        return SiteRankingReport(
            domain=domain,
            query=query,
            location_spec=location_spec,
            organic_results=organic_results,
            local_results=local_results,
            best_organic_position=best_organic,
            best_local_position=best_local,
            total_results_found=len(organic_results) + len(local_results),
            lat=lat,
            lon=lon
        )
    
    async def check_site_ranking_async(
        self,
        domain: str,
        query: str,
        ranking_locations: List[Dict[str, str]],
        gl: str = "us",
        hl: str = "en",
        max_results: int = 100,
        cid: Optional[str] = None,
        business_name: Optional[str] = None,
        city: Optional[str] = None,
        region: Optional[str] = None,
        country: Optional[str] = None
    ) -> List[SiteRankingReport]:
        """
        Async version of check_site_ranking with automatic CID lookup support.
        
        Args:
            ranking_locations: List of location dicts. Empty list means non-localized organic search only.
            city: Client's city from clients table (used for CID lookup if no cid provided)
            region: Client's region from clients table (used for CID lookup if no cid provided)
            country: Client's country from clients table (used for CID lookup if no cid provided)
        
        Handles async CID lookup when business_name is provided and no CID is given.
        Returns a list of reports, one for each ranking location.
        """
        # Determine which locations to check
        locations_to_check = []
        
        if ranking_locations:
            # Use the ranking_locations parameter
            for location_dict in ranking_locations:
                location_spec = LocationSpec(
                    city=location_dict.get('city'),
                    region=location_dict.get('region'),
                    country=location_dict.get('country'),
                    zipcode=location_dict.get('zipcode')
                )
                locations_to_check.append(location_spec)
        else:
            # Empty list means non-localized organic search only
            locations_to_check = [LocationSpec()]
        
        reports = []
        
        for location_spec in locations_to_check:
            # For empty ranking_locations, force non-localized organic search only
            # Always disable CID (skip local business search and CID lookup)
            if not ranking_locations:
                location_cid = None
                location_business_name = None
            else:
                # Localized search: allow CID lookup using client's city/region/country
                location_cid = cid  # Start with the provided CID
                location_business_name = business_name
                
                # Auto-fetch CID if business_name is provided and no CID was given
                # Use client's city/region/country from clients table for CID lookup
                if not location_cid and business_name and city and region and country:
                    print(f"🔄 No CID provided, attempting to fetch CID for business '{business_name}' using client location ({city}, {region}, {country})...")
                    try:
                        location_cid = await site_to_cid(business_name, city, region, country, domain)
                        if location_cid:
                            print(f"✅ Successfully fetched CID: {location_cid}")
                        else:
                            print(f"❌ Could not find CID for business '{business_name}' with domain '{domain}' in {city}, {region}, {country}")
                    except Exception as e:
                        print(f"⚠️ Error fetching CID: {e}")
                        location_cid = None
                elif not location_cid and business_name and not (city and region and country):
                    print(f"⚠️ Cannot fetch CID for business '{business_name}' - client city, region, and country are required for CID lookup")
            
            # Now run the synchronous version with the resolved CID for this location
            report = await asyncio.get_event_loop().run_in_executor(
                None,
                self._check_site_ranking_for_location,
                domain, query, location_spec, gl, hl, max_results, location_cid
            )
            reports.append(report)
        
        return reports
    
    def print_ranking_report(self, report: SiteRankingReport) -> None:
        """Print a formatted ranking report"""
        print("\n" + "=" * 80)
        print(f"SITE RANKING REPORT")
        print("=" * 80)
        print(f"Domain: {report.domain}")
        print(f"Query: '{report.query}'")
        print(f"Location: {report.location_spec.to_canonical_string()}")
        if report.lat is not None and report.lon is not None:
            print(f"Coordinates: {report.lat}, {report.lon}")
        print(f"Total Results Found: {report.total_results_found}")
        print("=" * 80)
    
    def print_ranking_reports(self, reports: List[SiteRankingReport]) -> None:
        """Print multiple ranking reports with clear separation by location"""
        for i, report in enumerate(reports, 1):
            print(f"\n{'=' * 80}")
            print(f"LOCATION {i}/{len(reports)}: {report.location_spec.to_canonical_string()}")
            print(f"{'=' * 80}")
            print(f"Domain: {report.domain}")
            print(f"Query: '{report.query}'")
            if report.lat is not None and report.lon is not None:
                print(f"Coordinates: {report.lat}, {report.lon}")
            print(f"Total Results Found: {report.total_results_found}")
            
            # Organic results for this location
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
            
            # Local business results for this location
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
            
            # Summary counts for this location
            print(f"\n📊 RESULTS SUMMARY FOR THIS LOCATION")
            print("-" * 40)
            print(f"Organic Results Found: {len(report.organic_results)}")
            print(f"Local Business Results Found: {len(report.local_results)}")
            print(f"Total Results Found: {report.total_results_found}")
        
        # Overall summary across all locations
        if len(reports) > 1:
            print(f"\n{'=' * 80}")
            print(f"OVERALL SUMMARY ACROSS ALL {len(reports)} LOCATIONS")
            print(f"{'=' * 80}")
            
            total_organic = sum(len(r.organic_results) for r in reports)
            total_local = sum(len(r.local_results) for r in reports)
            total_all = sum(r.total_results_found for r in reports)
            
            # Best positions across all locations
            best_organic_overall = min((r.best_organic_position for r in reports if r.best_organic_position), default=None)
            best_local_overall = min((r.best_local_position for r in reports if r.best_local_position), default=None)
            
            print(f"Total Organic Results Found: {total_organic}")
            print(f"Total Local Business Results Found: {total_local}")
            print(f"Total Results Found: {total_all}")
            
            if best_organic_overall:
                print(f"Best Organic Position Overall: #{best_organic_overall}")
            if best_local_overall:
                print(f"Best Local Business Position Overall: #{best_local_overall}")
            
            # Show which locations had results
            print(f"\nLOCATIONS WITH RESULTS:")
            print("-" * 40)
            for i, report in enumerate(reports, 1):
                location_name = report.location_spec.to_canonical_string()
                results_summary = []
                if report.organic_results:
                    results_summary.append(f"Organic: #{report.best_organic_position}")
                if report.local_results:
                    results_summary.append(f"Local: #{report.best_local_position}")
                
                if results_summary:
                    print(f"  {i}. {location_name}: {', '.join(results_summary)}")
                else:
                    print(f"  {i}. {location_name}: No results found")
        
        print("=" * 80)
    
    def _parse_location_string(self, location: Optional[str]) -> LocationSpec:
        """
        Parse a location string into LocationSpec.
        
        Args:
            location: Location string like "San Francisco, California, USA" or "San Francisco, CA"
            
        Returns:
            LocationSpec with parsed components
        """
        if not location:
            return LocationSpec()
            
        # Split by commas and clean up
        parts = [part.strip() for part in location.split(',')]
        
        if len(parts) == 1:
            # Just city
            return LocationSpec(city=parts[0])
        elif len(parts) == 2:
            # City, State/Region
            return LocationSpec(city=parts[0], region=parts[1])
        elif len(parts) >= 3:
            # City, State/Region, Country
            return LocationSpec(city=parts[0], region=parts[1], country=parts[2])
        
        return LocationSpec()
    
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
    cid: Optional[str] = None,
    business_name: Optional[str] = None,
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
        cid: Optional CID for local business search (local search only runs if provided)
        business_name: Optional business name for automatic CID lookup (e.g., "Thatcher's Popcorn")
        
    Returns:
        (first_position, hits)
        - first_position: The first ranking position if found, otherwise None
        - hits: All matching hits with their positions
    """
    checker = SiteRankChecker()
    
    # Parse location string into components
    location_spec = checker._parse_location_string(location)
    if not location_spec.country:
        location_spec.country = "United States"  # Default to US if not specified
    
    # Calculate max results based on pages and results per page
    max_results = min(100, max_pages * results_per_page)
    
    # Build ranking_locations from parsed location
    ranking_locations = []
    if location_spec.has_location_data():
        location_dict = {}
        if location_spec.city:
            location_dict['city'] = location_spec.city
        if location_spec.region:
            location_dict['region'] = location_spec.region
        if location_spec.country:
            location_dict['country'] = location_spec.country
        if location_spec.zipcode:
            location_dict['zipcode'] = location_spec.zipcode
        ranking_locations.append(location_dict)
    
    # Use the async version of the BrightData checker
    reports = await checker.check_site_ranking_async(
        domain=domain,
        query=query,
        ranking_locations=ranking_locations,
        max_results=max_results,
        cid=cid,
        business_name=business_name,
        city=location_spec.city,
        region=location_spec.region,
        country=location_spec.country
    )
    
    # For compatibility, return results from the first (and likely only) report
    report = reports[0] if reports else None
    if not report:
        return None, []
    
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
    cid: Optional[str] = None,
    business_name: Optional[str] = None,
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
        cid: CID for local business search (if None, no local search will be performed)
        business_name: Optional business name for automatic CID lookup (e.g., "Thatcher's Popcorn")
        
    Returns:
        (first_position, hits)
        - first_position: The first ranking position if found, otherwise None
        - hits: All matching hits with their positions
    """
    checker = SiteRankChecker()
    
    # Parse location string into components
    location_spec = checker._parse_location_string(location)
    if not location_spec.country:
        location_spec.country = "United States"  # Default to US if not specified
    
    # Build ranking_locations from parsed location
    ranking_locations = []
    if location_spec.has_location_data():
        location_dict = {}
        if location_spec.city:
            location_dict['city'] = location_spec.city
        if location_spec.region:
            location_dict['region'] = location_spec.region
        if location_spec.country:
            location_dict['country'] = location_spec.country
        if location_spec.zipcode:
            location_dict['zipcode'] = location_spec.zipcode
        ranking_locations.append(location_dict)
    
    # Use the async version of the BrightData checker
    # For local business search, we'll use max_business_results as max_results
    reports = await checker.check_site_ranking_async(
        domain=domain,
        query=query,
        ranking_locations=ranking_locations,
        max_results=max_business_results,
        cid=cid,
        business_name=business_name,
        city=location_spec.city,
        region=location_spec.region,
        country=location_spec.country
    )
    
    # For compatibility, return results from the first (and likely only) report
    report = reports[0] if reports else None
    if not report:
        return None, []
    
    # Convert local results to RankingHit format
    hits = checker._convert_ranking_results_to_hits(report.local_results)
    
    # Return first position and all hits
    first_position = report.best_local_position
    return first_position, hits


def main():
    """Demo usage of the SiteRankChecker with various scenarios"""
    checker = SiteRankChecker()
    
    print("=" * 80)
    print("DEMO 1: Search WITH multiple ranking_locations and business name (enables local search)")
    print("=" * 80)
    reports_with_multiple_locations = checker.check_site_ranking(
        domain="aroundtheedgebarbershop.com",
        query="barbershop near me",
        ranking_locations=[
            # {"city": "San Mateo", "region": "California", "country": "United States"},
            # {"city": "Palo Alto", "region": "California", "country": "United States"},
            {"zipcode": "94401", "city": "San Mateo"}
        ],
        max_results=100,
        business_name="Around the Edge Barbershop",
        city="San Mateo",
        region="California",
        country="United States",
    )
    checker.print_ranking_reports(reports_with_multiple_locations)


if __name__ == "__main__":
    main()
