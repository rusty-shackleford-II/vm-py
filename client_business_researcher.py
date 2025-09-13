#!/usr/bin/env python3
"""
Client Business Researcher Module

This module provides a comprehensive solution for generating custom site.json files
for local businesses using data from GBPResearcher and fallback content generation.

The ClientBusinessResearcher class takes business information and creates a complete
website configuration that matches the local-business template schema.

Key Features:
- Uses GBPResearcher to gather real business data from Google sources
- Generates fallback content when no Google Business Profile is found
- Converts Google reviews into testimonials section
- Maintains template structure while customizing content
- Async parallel processing for efficient data collection

Author: Warren
"""

import asyncio
import json
import os
import copy
import re
import urllib.parse
from typing import Dict, List, Optional, Any
from pathlib import Path

# Import the GBP researcher and Gemini client
from gbp_researcher import GBPResearcher, BusinessData, ReviewResult

# Import Gemini client for AI content generation
try:
    from clients.gemini_client import GeminiClient
    GEMINI_AVAILABLE = True
except ImportError:
    print("⚠️ Gemini client not available. AI content generation will not work.")
    GEMINI_AVAILABLE = False

# Import config for API keys
try:
    import config
    CONFIG_AVAILABLE = True
except ImportError:
    print("⚠️ Config not available for API keys")
    CONFIG_AVAILABLE = False


class ClientBusinessResearcher:
    """
    Generates custom site.json files for local businesses using GBPResearcher data
    and template-based fallback content.
    """
    
    def __init__(self):
        """Initialize the ClientBusinessResearcher"""
        self.gbp_researcher = GBPResearcher()
        self.template_path = None
        self._load_template_path()
        
        # Initialize Gemini client if available
        self.gemini_client = None
        if GEMINI_AVAILABLE and CONFIG_AVAILABLE:
            self._initialize_gemini_client()
    
    def _load_template_path(self):
        """Find and set the example site.json path"""
        # Try to find the example_site.json relative to current file
        current_dir = Path(__file__).parent
        
        # More comprehensive path search for Docker and local environments
        possible_paths = [
            current_dir / "example_site.json",  # Same directory as this file
            current_dir / "../vm-py/example_site.json",  # Parent then vm-py
            Path("./example_site.json"),  # Current working directory
            Path("/app/example_site.json"),  # Docker working directory
            Path.cwd() / "example_site.json",  # Explicit current working directory
        ]
        
        print(f"🔍 Searching for example_site.json from: {current_dir}")
        print(f"🔍 Current working directory: {Path.cwd()}")
        
        for i, path in enumerate(possible_paths):
            print(f"🔍 Checking path {i+1}: {path} (exists: {path.exists()})")
            if path.exists():
                self.template_path = str(path.resolve())
                print(f"📋 Found example site.json template at: {self.template_path}")
                return
        
        print("⚠️ example_site.json not found in expected locations")
        print(f"⚠️ Searched paths: {[str(p) for p in possible_paths]}")
        self.template_path = None
    
    def _initialize_gemini_client(self):
        """Initialize Gemini client with API keys from config"""
        try:
            # Load Gemini API keys from config
            gemini_keys = []
            for i in range(1, 10):  # Keys 1-9
                try:
                    key = getattr(config, f"GEMINI_API_KEY_{i}")
                    if key and key != "":
                        gemini_keys.append(key)
                except AttributeError:
                    break
            
            if gemini_keys:
                self.gemini_client = GeminiClient(
                    api_keys=gemini_keys, 
                    model_name="gemini-2.0-flash"
                )
                print(f"🤖 Gemini client initialized with {len(gemini_keys)} API keys")
            else:
                print("⚠️ No Gemini API keys found in config")
                
        except Exception as e:
            print(f"⚠️ Failed to initialize Gemini client: {e}")
            self.gemini_client = None
    
    def copy_template_site_json(self) -> Dict[str, Any]:
        """
        Copy the example site.json and return it as a dictionary
        
        Returns:
            Dictionary containing the example site.json structure
            
        Raises:
            FileNotFoundError: If example site.json file cannot be found
            json.JSONDecodeError: If example site.json file is not valid JSON
        """
        if not self.template_path or not os.path.exists(self.template_path):
            raise FileNotFoundError(f"example_site.json not found at: {self.template_path}")
        
        try:
            with open(self.template_path, 'r', encoding='utf-8') as f:
                template_data = json.load(f)
            
            # Create a deep copy to avoid modifying the original
            site_data = copy.deepcopy(template_data)
            
            print(f"✅ Copied example_site.json with {len(site_data)} top-level sections")
            return site_data
            
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(f"Invalid JSON in example site.json file: {e}")
        except Exception as e:
            raise Exception(f"Error reading example site.json file: {e}")
    
    def populate_testimonials_from_reviews(
        self, 
        site_data: Dict[str, Any], 
        reviews: List[ReviewResult],
        max_testimonials: int = 6
    ) -> Dict[str, Any]:
        """
        Populate the testimonials section with real Google reviews
        
        Args:
            site_data: The site.json dictionary to modify
            reviews: List of ReviewResult objects from GBPResearcher
            max_testimonials: Maximum number of testimonials to include
            
        Returns:
            Modified site_data with populated testimonials section
        """
        if not reviews:
            print("⚠️ No reviews provided - keeping template testimonials")
            return site_data
        
        print(f"📝 Converting {len(reviews)} Google reviews to testimonials...")
        
        # Filter reviews that have text and are 4+ stars for testimonials
        quality_reviews = [
            review for review in reviews 
            if review.review_text and review.rating and review.rating >= 4
        ]
        
        # If we don't have enough quality reviews, include 3-star reviews
        if len(quality_reviews) < max_testimonials:
            three_star_reviews = [
                review for review in reviews 
                if review.review_text and review.rating and review.rating == 3
            ]
            quality_reviews.extend(three_star_reviews)
        
        # Sort by rating (highest first), then by text length (longer reviews first)
        quality_reviews.sort(
            key=lambda r: (r.rating or 0, len(r.review_text or "")), 
            reverse=True
        )
        
        # Take the best reviews up to max_testimonials
        selected_reviews = quality_reviews[:max_testimonials]
        
        if not selected_reviews:
            print("⚠️ No suitable reviews found - keeping template testimonials")
            return site_data
        
        # Convert reviews to testimonials format
        testimonials = []
        for review in selected_reviews:
            testimonial = {
                "authorImageUrl": review.author_image or "",
                "authorName": review.author_name or "Customer",
                "rating": review.rating or 5,
                "reviewDate": self._format_review_date(review.review_date),
                "reviewText": self._clean_review_text(review.review_text)
            }
            testimonials.append(testimonial)
        
        # Update the site data
        if "testimonials" not in site_data:
            site_data["testimonials"] = {}
        
        site_data["testimonials"]["items"] = testimonials
        
        # Update title and subtitle if they exist
        if "title" not in site_data["testimonials"]:
            site_data["testimonials"]["title"] = "What Our Clients Say"
        
        if "subtitle" not in site_data["testimonials"]:
            site_data["testimonials"]["subtitle"] = "Don't just take our word for it. Here's what our satisfied clients have to say about our professional services."
        
        print(f"✅ Added {len(testimonials)} testimonials from Google reviews")
        return site_data
    
    def _format_review_date(self, review_date: Optional[str]) -> str:
        """
        Format review date for testimonials
        
        Args:
            review_date: Raw review date string from Google
            
        Returns:
            Formatted date string suitable for testimonials
        """
        if not review_date:
            return "recently"
        
        # Google review dates are often in formats like:
        # "2 weeks ago", "a month ago", "3 days ago", etc.
        # We'll clean these up for better presentation
        
        date_lower = review_date.lower().strip()
        
        # Common date patterns to clean up
        if "ago" in date_lower:
            return date_lower.replace(" ago", "").strip()
        
        # If it's already a nice format, use it
        if any(word in date_lower for word in ["day", "week", "month", "year"]):
            return date_lower
        
        # Default fallback
        return "recently"
    
    def _clean_review_text(self, review_text: Optional[str]) -> str:
        """
        Clean and format review text for testimonials
        
        Args:
            review_text: Raw review text from Google
            
        Returns:
            Cleaned review text suitable for testimonials
        """
        if not review_text:
            return "Great service!"
        
        # Remove excessive whitespace and newlines
        cleaned = " ".join(review_text.split())
        
        # Truncate very long reviews to keep testimonials readable
        max_length = 200
        if len(cleaned) > max_length:
            # Find the last complete sentence within the limit
            truncated = cleaned[:max_length]
            last_period = truncated.rfind('.')
            last_exclamation = truncated.rfind('!')
            last_question = truncated.rfind('?')
            
            # Use the latest sentence ending, or just truncate with ellipsis
            last_sentence_end = max(last_period, last_exclamation, last_question)
            
            if last_sentence_end > max_length * 0.7:  # If we found a good cutoff point
                cleaned = truncated[:last_sentence_end + 1]
            else:
                cleaned = truncated.rstrip() + "..."
        
        return cleaned
    
    def _generate_unsplash_url(
        self, 
        search_terms: List[str], 
        width: int = 600, 
        height: int = 400,
        quality: int = 80
    ) -> str:
        """
        Generate Unsplash image URL based on search terms
        
        Args:
            search_terms: List of search terms for the image
            width: Image width in pixels
            height: Image height in pixels  
            quality: Image quality (1-100)
            
        Returns:
            Formatted Unsplash URL
        """
        # Join search terms and encode for URL
        search_query = ",".join(search_terms)
        encoded_query = urllib.parse.quote(search_query)
        
        # Build Unsplash URL with parameters
        base_url = "https://images.unsplash.com/photo"
        params = {
            "auto": "format",
            "fit": "crop", 
            "w": str(width),
            "h": str(height),
            "q": str(quality)
        }
        
        # For services, use a hash-based approach to get consistent images
        import hashlib
        hash_object = hashlib.md5(search_query.encode())
        hash_hex = hash_object.hexdigest()
        
        # Use hash to select from a curated list of business-appropriate photo IDs
        business_photo_ids = [
            "1621905251189-08b45d6a269e",  # Professional consultation
            "1504328345606-18bbc8c9d7d1",  # Tools and workspace
            "1607472586893-edb57bdc0e39",  # Installation work
            "1558618666-fcd25c85cd64",    # Team collaboration
            "1581244277943-fe4a9c777189",  # Service vehicle
            "1607400201889-565b1ee75f8e",  # Professional at work
            "1621905251189-08b45d6a269e",  # Business meeting
            "1504384308090-c894fdcc538d",  # Office workspace
            "1600880292089-90a7e086ee0c",  # Modern office
            "1556742049-0a6523a1fe6b"     # Professional services
        ]
        
        # Select photo based on hash
        photo_index = int(hash_hex[:2], 16) % len(business_photo_ids)
        photo_id = business_photo_ids[photo_index]
        
        # Build final URL
        param_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{base_url}-{photo_id}?{param_string}"
    
    def _get_service_image_terms(self, service_title: str, business_type: str = "") -> List[str]:
        """
        Generate appropriate image search terms for a service
        
        Args:
            service_title: Title of the service
            business_type: Type of business (e.g., "plumber", "hvac")
            
        Returns:
            List of search terms for image generation
        """
        # Base terms
        terms = ["professional", "service"]
        
        # Add business type if available
        if business_type:
            terms.append(business_type.lower())
        
        # Add service-specific terms based on common patterns
        title_lower = service_title.lower()
        
        if any(word in title_lower for word in ["emergency", "urgent", "24/7"]):
            terms.extend(["emergency", "urgent", "response"])
        elif any(word in title_lower for word in ["maintenance", "repair", "fix"]):
            terms.extend(["maintenance", "repair", "tools"])
        elif any(word in title_lower for word in ["installation", "install", "setup"]):
            terms.extend(["installation", "construction", "building"])
        elif any(word in title_lower for word in ["consultation", "advice", "planning"]):
            terms.extend(["consultation", "meeting", "planning"])
        elif any(word in title_lower for word in ["cleaning", "clean"]):
            terms.extend(["cleaning", "maintenance"])
        else:
            terms.extend(["work", "professional"])
        
        return terms[:4]  # Limit to 4 terms for clean URLs
    
    def _get_about_image_terms(self, alt_text: str, business_type: str = "") -> List[str]:
        """
        Generate appropriate image search terms for about section images based on alt text
        
        Args:
            alt_text: Alt text describing what the image should show
            business_type: Type of business (e.g., "plumber", "hvac")
            
        Returns:
            List of search terms for image generation
        """
        # Base terms
        terms = ["professional", "business"]
        
        # Add business type if available
        if business_type:
            terms.append(business_type.lower())
        
        # Parse alt text for relevant keywords
        alt_lower = alt_text.lower()
        
        if any(word in alt_lower for word in ["consultation", "meeting", "team", "expertise"]):
            terms.extend(["consultation", "meeting", "team"])
        elif any(word in alt_lower for word in ["tools", "equipment", "modern"]):
            terms.extend(["tools", "equipment", "workspace"])
        elif any(word in alt_lower for word in ["team", "collaboration", "working", "project"]):
            terms.extend(["team", "collaboration", "work"])
        elif any(word in alt_lower for word in ["office", "workspace", "facility"]):
            terms.extend(["office", "workspace", "building"])
        elif any(word in alt_lower for word in ["service", "work", "professional"]):
            terms.extend(["service", "professional", "work"])
        else:
            # Default professional terms
            terms.extend(["professional", "service"])
        
        return terms[:4]  # Limit to 4 terms for clean URLs
    
    async def _validate_and_retry_json_generation(
        self,
        prompt: str,
        validation_func: callable,
        max_retries: int = 3,
        section_name: str = "content"
    ) -> Optional[Dict[str, Any]]:
        """
        Generate JSON content with validation and retry loop
        
        Args:
            prompt: Initial prompt for AI
            validation_func: Function to validate the generated JSON
            max_retries: Maximum number of retry attempts
            section_name: Name of section being generated (for error messages)
            
        Returns:
            Validated JSON dictionary or None if all retries failed
        """
        if not self.gemini_client:
            return None
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                print(f"🤖 Generating {section_name} (attempt {attempt + 1}/{max_retries})...")
                
                # Generate content with AI
                response = await asyncio.to_thread(
                    self.gemini_client.ask,
                    prompt,
                    disable_thinking=True
                )
                
                # Parse JSON response
                parsed_data = self._parse_json_response(response)
                if not parsed_data:
                    last_error = "Failed to parse JSON response"
                    continue
                
                # Validate the parsed data
                validation_result = validation_func(parsed_data)
                if validation_result["valid"]:
                    print(f"✅ {section_name} generated and validated successfully")
                    return parsed_data
                else:
                    last_error = validation_result["error"]
                    
                    # Create retry prompt with error feedback
                    retry_prompt = f"""{prompt}

PREVIOUS ATTEMPT FAILED WITH ERROR: {last_error}

Please fix the error and generate the JSON again. Make sure to:
1. Follow the exact JSON format specified
2. Include all required fields
3. Use proper data types (strings, numbers, arrays, objects)
4. Ensure all URLs are properly formatted
5. Double-check the JSON syntax

Generate the corrected {section_name} now:"""
                    
                    prompt = retry_prompt  # Use retry prompt for next iteration
                    print(f"⚠️ Validation failed: {last_error}. Retrying...")
                    
            except Exception as e:
                last_error = f"Exception during generation: {str(e)}"
                print(f"❌ Attempt {attempt + 1} failed: {last_error}")
        
        print(f"❌ All {max_retries} attempts failed for {section_name}. Last error: {last_error}")
        return None
    
    def _validate_services_section(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate services section JSON structure
        
        Args:
            data: Parsed JSON data to validate
            
        Returns:
            Dictionary with 'valid' boolean and 'error' message if invalid
        """
        try:
            # Check required top-level fields
            required_fields = ["title", "subtitle", "items"]
            for field in required_fields:
                if field not in data:
                    return {"valid": False, "error": f"Missing required field: {field}"}
            
            # Validate items array
            items = data.get("items", [])
            if not isinstance(items, list):
                return {"valid": False, "error": "items must be an array"}
            
            if len(items) == 0:
                return {"valid": False, "error": "items array cannot be empty"}
            
            # Validate each service item
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    return {"valid": False, "error": f"Item {i} must be an object"}
                
                # Check required item fields
                item_required = ["id", "title", "description", "alt"]
                for field in item_required:
                    if field not in item:
                        return {"valid": False, "error": f"Item {i} missing required field: {field}"}
                    if not isinstance(item[field], str) or not item[field].strip():
                        return {"valid": False, "error": f"Item {i} field '{field}' must be a non-empty string"}
                
                # Check imageUrl field (can be empty, will be populated)
                if "imageUrl" not in item:
                    return {"valid": False, "error": f"Item {i} missing imageUrl field"}
                if not isinstance(item["imageUrl"], str):
                    return {"valid": False, "error": f"Item {i} imageUrl must be a string"}
                
                # Validate ID format (lowercase with hyphens)
                if not re.match(r'^[a-z0-9-]+$', item["id"]):
                    return {"valid": False, "error": f"Item {i} ID must be lowercase letters, numbers, and hyphens only"}
            
            return {"valid": True, "error": None}
            
        except Exception as e:
            return {"valid": False, "error": f"Validation exception: {str(e)}"}
    
    def _extract_maps_contact_info(self, maps_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract contact information from structured maps data
        
        Args:
            maps_data: Structured maps JSON data
            
        Returns:
            Dictionary with extracted contact info
        """
        contact_info = {
            "address": "",
            "phone": "",
            "hours": {},
            "website": "",
            "latitude": None,
            "longitude": None
        }
        
        if not maps_data or "place" not in maps_data:
            return contact_info
        
        place = maps_data["place"]
        
        # Extract basic contact info
        contact_info["address"] = place.get("address", "")
        contact_info["phone"] = place.get("phone", "")
        contact_info["website"] = place.get("link", "")
        
        # Extract coordinates
        contact_info["latitude"] = place.get("latitude")
        contact_info["longitude"] = place.get("longitude")
        
        # Extract hours
        if "open_hours" in place and isinstance(place["open_hours"], dict):
            contact_info["hours"] = place["open_hours"]
        
        return contact_info
    
    def _extract_maps_service_tags(self, maps_data: Optional[Dict[str, Any]]) -> List[str]:
        """
        Extract service-related tags from structured maps data
        
        Args:
            maps_data: Structured maps JSON data
            
        Returns:
            List of service tags/features
        """
        service_features = []
        
        if not maps_data or "place" not in maps_data or "tags" not in maps_data["place"]:
            return service_features
        
        tags = maps_data["place"]["tags"]
        
        # Map of tag keys to user-friendly descriptions
        tag_mapping = {
            "/geo/type/establishment/offers_online_estimates": "Online Estimates Available",
            "/geo/type/establishment_poi/has_onsite_services": "On-Site Services",
            "/geo/type/establishment_poi/has_wheelchair_accessible_entrance": "Wheelchair Accessible",
            "/geo/type/establishment_poi/has_service_repair": "Repair Services",
            "/geo/type/establishment_poi/welcomes_lgbtq": "LGBTQ+ Friendly",
            "/geo/type/establishment_poi/pay_credit_card": "Credit Cards Accepted"
        }
        
        for tag in tags:
            if tag.get("value") == 1:  # Only include active/positive tags
                key_id = tag.get("key_id", "")
                if key_id in tag_mapping:
                    service_features.append(tag_mapping[key_id])
                elif "value_title_short" in tag:
                    service_features.append(tag["value_title_short"])
        
        return service_features
    
    def _parse_hours_to_structured_format(self, hours_data: Dict[str, str]) -> Dict[str, Any]:
        """
        Convert hours data to structured format for easier parsing
        
        Args:
            hours_data: Dictionary with day names as keys and hour strings as values
            
        Returns:
            Dictionary with structured hours format
        """
        structured_hours = {}
        
        # Days of the week in order
        days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        for day in days_order:
            # Look for the day in the hours data (case insensitive)
            day_hours = None
            for key, value in hours_data.items():
                if key.lower().startswith(day.lower()[:3]):  # Match "Mon", "Tue", etc.
                    day_hours = value
                    break
            
            if not day_hours or day_hours.lower() in ["closed", "close"]:
                structured_hours[day] = "closed"
            else:
                # Try to parse hours like "7 AM–5 PM" or "7:00 AM - 5:00 PM"
                hours_clean = day_hours.strip()
                
                # Common patterns to split on
                separators = ["–", "-", " to ", " - "]
                open_time = None
                close_time = None
                
                for sep in separators:
                    if sep in hours_clean:
                        parts = hours_clean.split(sep, 1)
                        if len(parts) == 2:
                            open_time = parts[0].strip()
                            close_time = parts[1].strip()
                            break
                
                if open_time and close_time:
                    structured_hours[day] = {
                        "open": open_time,
                        "close": close_time
                    }
                else:
                    # Fallback - assume it's open if we can't parse
                    structured_hours[day] = {
                        "open": "9:00 AM",
                        "close": "5:00 PM"
                    }
        
        return structured_hours
    
    def _get_available_icons(self) -> List[str]:
        """
        Get the list of available icons that can be rendered in the template
        
        Returns:
            List of available icon names
        """
        return [
            "AcademicCapIcon", "UsersIcon", "BuildingOfficeIcon", "StarIcon", "TrophyIcon", 
            "ShieldCheckIcon", "ClockIcon", "CalendarIcon", "CheckBadgeIcon", "CurrencyDollarIcon", 
            "BriefcaseIcon", "DocumentTextIcon", "ScaleIcon", "CalculatorIcon", "ChartBarIcon", 
            "PresentationChartBarIcon", "ComputerDesktopIcon", "DevicePhoneMobileIcon", "HeartIcon", 
            "PlusIcon", "UserIcon", "EyeIcon", "HandRaisedIcon", "HomeIcon", "WrenchScrewdriverIcon", 
            "BoltIcon", "FireIcon", "WrenchIcon", "PaintBrushIcon", "SwatchIcon", "GiftIcon", 
            "BuildingStorefrontIcon", "TruckIcon", "CogIcon", "KeyIcon", "SparklesIcon", 
            "ScissorsIcon", "SunIcon", "FaceSmileIcon", "BookOpenIcon", "LightBulbIcon", 
            "LanguageIcon", "MicrophoneIcon", "MusicalNoteIcon", "WifiIcon", "ServerIcon", 
            "CloudIcon", "CodeBracketIcon", "CpuChipIcon", "MapIcon"
        ]
    
    def _validate_and_fix_icons(self, statistics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate icons in statistics and replace invalid ones with random valid icons
        
        Args:
            statistics: List of statistics dictionaries with icon fields
            
        Returns:
            Statistics list with validated icons
        """
        import random
        
        available_icons = self._get_available_icons()
        validated_statistics = []
        
        for stat in statistics:
            validated_stat = stat.copy()
            
            # Check if icon exists in available list
            if "icon" not in validated_stat or validated_stat["icon"] not in available_icons:
                # Choose random icon as fallback
                validated_stat["icon"] = random.choice(available_icons)
                print(f"⚠️ Invalid icon '{stat.get('icon', 'missing')}' replaced with '{validated_stat['icon']}'")
            
            validated_statistics.append(validated_stat)
        
        return validated_statistics
    
    async def _generate_statistics_icons(
        self,
        business_name: str,
        business_type: str,
        statistics: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate appropriate icons for statistics using AI, with validation and fallback
        
        Args:
            business_name: Name of the business
            business_type: Type of business for context
            statistics: List of statistics needing icons
            
        Returns:
            Statistics with validated icons assigned
        """
        if not self.gemini_client or not statistics:
            return self._validate_and_fix_icons(statistics)
        
        # Prepare statistics for icon generation
        stats_for_prompt = []
        for i, stat in enumerate(statistics):
            stats_for_prompt.append(f"{i+1}. {stat.get('name', 'Statistic')} - {stat.get('value', 'Value')}")
        
        available_icons = self._get_available_icons()
        
        prompt = f"""You are selecting appropriate icons for business statistics. Choose the most contextually relevant icon for each statistic.

BUSINESS INFORMATION:
- Business Name: {business_name}
- Business Type: {business_type}

STATISTICS TO ASSIGN ICONS:
{chr(10).join(stats_for_prompt)}

REQUIREMENTS:
1. Choose the most appropriate icon for each statistic based on business context
2. Consider what the statistic represents (experience, customers, services, etc.)
3. Pick icons that visually represent the concept
4. You MUST choose from the available icons list below
5. Return exactly {len(statistics)} icon names

AVAILABLE ICONS:
{', '.join(available_icons)}

OUTPUT FORMAT (JSON):
{{
  "icons": ["IconName1", "IconName2", "IconName3"]
}}

EXAMPLES:
- Years of Experience → AcademicCapIcon, ClockIcon, or TrophyIcon
- Satisfied Clients → UsersIcon, StarIcon, or HeartIcon  
- Services Offered → BuildingOfficeIcon, CogIcon, or BriefcaseIcon
- Projects Completed → CheckBadgeIcon, TrophyIcon, or ChartBarIcon

Generate the icon selection now:"""

        try:
            print(f"🎯 Generating icons for {len(statistics)} statistics...")
            
            # Generate icons with AI
            response = await asyncio.to_thread(
                self.gemini_client.ask,
                prompt,
                disable_thinking=True
            )
            
            # Parse response
            parsed_data = self._parse_json_response(response)
            if not parsed_data or "icons" not in parsed_data:
                print("⚠️ Failed to parse icon response, using fallback validation")
                return self._validate_and_fix_icons(statistics)
            
            selected_icons = parsed_data["icons"]
            if not isinstance(selected_icons, list) or len(selected_icons) != len(statistics):
                print(f"⚠️ Invalid icon response format, using fallback validation")
                return self._validate_and_fix_icons(statistics)
            
            # Apply icons to statistics
            updated_statistics = []
            for i, stat in enumerate(statistics):
                updated_stat = stat.copy()
                if i < len(selected_icons):
                    updated_stat["icon"] = selected_icons[i]
                updated_statistics.append(updated_stat)
            
            # Validate and fix any invalid icons
            validated_statistics = self._validate_and_fix_icons(updated_statistics)
            
            print(f"✅ Generated and validated icons for statistics")
            return validated_statistics
            
        except Exception as e:
            print(f"❌ Error generating icons with AI: {e}")
            return self._validate_and_fix_icons(statistics)
    
    def _validate_about_section(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate about section JSON structure
        
        Args:
            data: Parsed JSON data to validate
            
        Returns:
            Dictionary with 'valid' boolean and 'error' message if invalid
        """
        try:
            # Check required top-level fields
            required_fields = ["title", "description"]
            for field in required_fields:
                if field not in data:
                    return {"valid": False, "error": f"Missing required field: {field}"}
                if not isinstance(data[field], str) or not data[field].strip():
                    return {"valid": False, "error": f"Field '{field}' must be a non-empty string"}
            
            # Validate statistics if present
            if "statistics" in data:
                stats = data["statistics"]
                if not isinstance(stats, list):
                    return {"valid": False, "error": "statistics must be an array"}
                
                for i, stat in enumerate(stats):
                    if not isinstance(stat, dict):
                        return {"valid": False, "error": f"Statistic {i} must be an object"}
                    
                    stat_required = ["name", "value"]
                    for field in stat_required:
                        if field not in stat:
                            return {"valid": False, "error": f"Statistic {i} missing required field: {field}"}
                        if not isinstance(stat[field], str) or not stat[field].strip():
                            return {"valid": False, "error": f"Statistic {i} field '{field}' must be a non-empty string"}
                    
                    # Icon field is optional during initial validation (added later)
                    if "icon" in stat and (not isinstance(stat["icon"], str) or not stat["icon"].strip()):
                        return {"valid": False, "error": f"Statistic {i} icon field must be a non-empty string if present"}
            
            # Validate features if present
            if "features" in data:
                features = data["features"]
                if not isinstance(features, list):
                    return {"valid": False, "error": "features must be an array"}
                
                for i, feature in enumerate(features):
                    if not isinstance(feature, str) or not feature.strip():
                        return {"valid": False, "error": f"Feature {i} must be a non-empty string"}
            
            return {"valid": True, "error": None}
            
        except Exception as e:
            return {"valid": False, "error": f"Validation exception: {str(e)}"}
    
    def _validate_hero_section(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate hero section JSON structure
        
        Args:
            data: Parsed JSON data to validate
            
        Returns:
            Dictionary with 'valid' boolean and 'error' message if invalid
        """
        try:
            # Check required top-level fields
            required_fields = ["backgroundImageUrl", "headline", "cta"]
            for field in required_fields:
                if field not in data:
                    return {"valid": False, "error": f"Missing required field: {field}"}
            
            # Validate headline
            if not isinstance(data["headline"], str) or not data["headline"].strip():
                return {"valid": False, "error": "headline must be a non-empty string"}
            
            # Validate backgroundImageUrl
            if not isinstance(data["backgroundImageUrl"], str):
                return {"valid": False, "error": "backgroundImageUrl must be a string"}
            
            # Validate CTA object
            cta = data.get("cta", {})
            if not isinstance(cta, dict):
                return {"valid": False, "error": "cta must be an object"}
            
            if "label" not in cta:
                return {"valid": False, "error": "cta missing required field: label"}
            if not isinstance(cta["label"], str) or not cta["label"].strip():
                return {"valid": False, "error": "cta label must be a non-empty string"}
            
            # Validate optional fields if present
            optional_string_fields = ["subheadline", "phone"]
            for field in optional_string_fields:
                if field in data:
                    if not isinstance(data[field], str):
                        return {"valid": False, "error": f"{field} must be a string"}
            
            # Validate href in cta if present
            if "href" in cta and not isinstance(cta["href"], str):
                return {"valid": False, "error": "cta href must be a string"}
            
            # Validate colors object if present
            if "colors" in data:
                colors = data["colors"]
                if not isinstance(colors, dict):
                    return {"valid": False, "error": "colors must be an object"}
                
                color_fields = ["headline", "subheadline", "ctaText", "ctaBackground"]
                for field in color_fields:
                    if field in colors and not isinstance(colors[field], str):
                        return {"valid": False, "error": f"colors.{field} must be a string"}
            
            return {"valid": True, "error": None}
            
        except Exception as e:
            return {"valid": False, "error": f"Validation exception: {str(e)}"}
    
    def _get_hero_image_terms(self, business_name: str, business_type: str = "", business_location: str = "") -> List[str]:
        """
        Generate appropriate image search terms for hero background
        
        Args:
            business_name: Name of the business
            business_type: Type of business (e.g., "plumber", "hvac")
            business_location: Business location for context
            
        Returns:
            List of search terms for hero background image
        """
        terms = ["professional", "business"]
        
        # Add business type specific terms
        if business_type:
            business_type_lower = business_type.lower()
            
            # Map business types to appropriate visual terms
            if any(word in business_type_lower for word in ["plumb", "hvac", "heating", "cooling", "air"]):
                terms.extend(["tools", "service", "home"])
            elif any(word in business_type_lower for word in ["electric", "contractor"]):
                terms.extend(["construction", "tools", "building"])
            elif any(word in business_type_lower for word in ["restaurant", "food", "cafe"]):
                terms.extend(["restaurant", "kitchen", "food"])
            elif any(word in business_type_lower for word in ["retail", "shop", "store"]):
                terms.extend(["store", "retail", "shopping"])
            elif any(word in business_type_lower for word in ["medical", "health", "dental"]):
                terms.extend(["medical", "health", "clean"])
            elif any(word in business_type_lower for word in ["law", "legal", "attorney"]):
                terms.extend(["office", "professional", "meeting"])
            elif any(word in business_type_lower for word in ["clean", "maid", "janitorial"]):
                terms.extend(["cleaning", "service", "home"])
            else:
                terms.extend(["service", "professional"])
        
        # Add location context if available
        if business_location:
            if any(word in business_location.lower() for word in ["beach", "coast", "ocean"]):
                terms.append("coastal")
            elif any(word in business_location.lower() for word in ["mountain", "hill"]):
                terms.append("mountain")
            else:
                terms.append("city")
        
        return terms[:4]  # Limit to 4 terms for clean URLs
    
    async def generate_hero_section(
        self,
        business_name: str,
        business_location: str,
        business_description: str,
        business_data: Optional[BusinessData] = None,
        cleaned_html: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate hero section using AI and business data
        
        Args:
            business_name: Name of the business
            business_location: Location of the business
            business_description: Description of what the business does
            business_data: Optional BusinessData from GBPResearcher
            cleaned_html: Optional cleaned HTML content (if not in business_data)
            
        Returns:
            Hero section dictionary matching schema
        """
        print(f"🦸 Generating hero section for {business_name}...")
        
        # Prepare context from business data
        context_info = []
        phone_number = None
        
        if business_data:
            if business_data.business_type:
                context_info.append(f"Business type: {business_data.business_type}")
            if business_data.phone:
                phone_number = business_data.phone
                context_info.append(f"Phone: {business_data.phone}")
            if business_data.rating and business_data.review_count:
                context_info.append(f"Rating: {business_data.rating}/5 stars with {business_data.review_count} reviews")
            
            # Add detailed service categories from Google Maps data
            if business_data.maps_data and "place" in business_data.maps_data and "category" in business_data.maps_data["place"]:
                categories = business_data.maps_data["place"]["category"]
                if categories and len(categories) > 1:
                    category_titles = [cat.get("title", "") for cat in categories[:5]]  # Top 5 categories
                    context_info.append(f"Service categories: {', '.join(category_titles)}")
            
            if business_data.cleaned_html:
                context_info.append(f"Website content: {business_data.cleaned_html[:1200]}")
            if business_data.reviews and business_data.reviews.reviews_summary:
                context_info.append(f"Customer sentiment: {business_data.reviews.reviews_summary[:200]}")
        
        # Use standalone cleaned_html if provided and not already in business_data
        if cleaned_html and (not business_data or not business_data.cleaned_html):
            context_info.append(f"Website content: {cleaned_html[:1200]}")
        
        context = "\n".join(context_info) if context_info else "No additional business data available."
        
        # Create AI prompt for hero section
        prompt = f"""You are creating a hero section for a local business website. Generate compelling, action-oriented content that immediately communicates value.

BUSINESS INFORMATION:
- Name: {business_name}
- Location: {business_location}
- Description: {business_description}

ADDITIONAL CONTEXT (VERY IMPORTANT - USE THIS TO UNDERSTAND THE ACTUAL BUSINESS):
{context}

REQUIREMENTS:
1. Create a powerful, benefit-focused headline (not just the business name)
2. Generate a compelling subheadline that reinforces the value proposition
3. USE INFORMATION FROM THE WEBSITE CONTENT to make headlines specific and authentic
4. Create an action-oriented call-to-action button
5. Include phone number if available
6. Use professional color scheme
7. Make it location-specific and relevant to the business type
8. If the website content mentions specialties or unique selling points, HIGHLIGHT THOSE

OUTPUT FORMAT (JSON):
{{
  "backgroundImageUrl": "",
  "headline": "Compelling headline that focuses on customer benefits",
  "subheadline": "Supporting text that reinforces value and builds trust",
  "cta": {{
    "label": "Action-oriented button text",
    "href": "tel:PHONE_NUMBER or #contact"
  }},
  "phone": "PHONE_NUMBER if available",
  "colors": {{
    "headline": "#111827",
    "subheadline": "#4b5563", 
    "ctaText": "#ffffff",
    "ctaBackground": "#10B981"
  }}
}}

IMPORTANT: 
- Leave backgroundImageUrl empty - it will be populated automatically
- Focus on benefits, not just features
- Make the headline about what the customer gets, not what you do
- Use the phone number from context if available
- Make the CTA specific to the business type (e.g., "Get Free Quote", "Schedule Service", "Call Now")

Generate the hero section now:"""

        try:
            # Use validation and retry loop
            hero_data = await self._validate_and_retry_json_generation(
                prompt=prompt,
                validation_func=self._validate_hero_section,
                max_retries=3,
                section_name="hero section"
            )
            
            if hero_data:
                # Add hero background image
                business_type = business_data.business_type if business_data else ""
                image_terms = self._get_hero_image_terms(business_name, business_type, business_location)
                hero_data["backgroundImageUrl"] = self._generate_unsplash_url(
                    image_terms, width=1200, height=600, quality=90
                )
                
                print(f"✅ Generated hero section with background image")
                return hero_data
            
            # Fallback to template-based generation
            print("⚠️ Using fallback hero generation")
            return self._generate_fallback_hero(business_name, business_location, business_description, phone_number)
            
        except Exception as e:
            print(f"❌ Error generating hero section with AI: {e}")
            return self._generate_fallback_hero(business_name, business_location, business_description, phone_number)
    
    def _generate_fallback_hero(
        self, 
        business_name: str, 
        business_location: str, 
        business_description: str,
        phone_number: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate fallback hero section when AI is not available"""
        
        # Generate basic hero content
        headline = f"Professional Services in {business_location}"
        subheadline = f"Trust {business_name} for reliable, quality service you can count on."
        
        # Determine CTA based on phone availability
        if phone_number:
            cta = {
                "label": "Call for Service",
                "href": f"tel:{phone_number}"
            }
        else:
            cta = {
                "label": "Get Started Today",
                "href": "#contact"
            }
        
        # Generate hero background image
        image_terms = self._get_hero_image_terms(business_name, "", business_location)
        background_url = self._generate_unsplash_url(image_terms, width=1200, height=600, quality=90)
        
        hero_section = {
            "backgroundImageUrl": background_url,
            "headline": headline,
            "subheadline": subheadline,
            "cta": cta,
            "colors": {
                "headline": "#111827",
                "subheadline": "#4b5563",
                "ctaText": "#ffffff",
                "ctaBackground": "#10B981"
            }
        }
        
        # Add phone if available
        if phone_number:
            hero_section["phone"] = phone_number
        
        return hero_section
    
    async def generate_services_section(
        self,
        business_name: str,
        business_location: str,
        business_description: str,
        business_data: Optional[BusinessData] = None,
        cleaned_html: Optional[str] = None,
        max_services: int = 3
    ) -> Dict[str, Any]:
        """
        Generate services section using AI and business data
        
        Args:
            business_name: Name of the business
            business_location: Location of the business  
            business_description: Description of what the business does
            business_data: Optional BusinessData from GBPResearcher
            cleaned_html: Optional cleaned HTML content (if not in business_data)
            max_services: Maximum number of services to generate
            
        Returns:
            Services section dictionary matching schema
        """
        print(f"🔧 Generating services section for {business_name}...")
        
        # Prepare context from business data
        context_info = []
        if business_data:
            if business_data.business_type:
                context_info.append(f"Business type: {business_data.business_type}")
            
            # Add detailed service categories from Google Maps data
            if business_data.maps_data and "place" in business_data.maps_data and "category" in business_data.maps_data["place"]:
                categories = business_data.maps_data["place"]["category"]
                if categories and len(categories) > 1:
                    category_titles = [cat.get("title", "") for cat in categories[:5]]  # Top 5 categories
                    context_info.append(f"Service categories: {', '.join(category_titles)}")
            
            if business_data.cleaned_html:
                # Use first 1500 chars of cleaned HTML for context - this is crucial for understanding actual services offered
                context_info.append(f"Website content details: {business_data.cleaned_html[:1500]}")
            if business_data.reviews and business_data.reviews.reviews:
                # Add context from reviews about services mentioned
                reviews_text = " ".join([r.review_text or "" for r in business_data.reviews.reviews[:5]])
                context_info.append(f"Customer feedback mentions: {reviews_text[:500]}")
            if business_data.rating and business_data.review_count:
                context_info.append(f"Customer rating: {business_data.rating}/5 stars with {business_data.review_count} reviews")
        
        # Use standalone cleaned_html if provided and not already in business_data
        if cleaned_html and (not business_data or not business_data.cleaned_html):
            context_info.append(f"Website content details: {cleaned_html[:1500]}")
        
        context = "\n".join(context_info) if context_info else "No additional business data available."
        
        # Create AI prompt for services generation
        prompt = f"""You are creating a services section for a local business website. Generate {max_services} professional services based on the business information provided.

BUSINESS INFORMATION:
- Name: {business_name}
- Location: {business_location}  
- Description: {business_description}

ADDITIONAL CONTEXT (VERY IMPORTANT - USE THIS TO UNDERSTAND ACTUAL SERVICES):
{context}

REQUIREMENTS:
1. Generate exactly {max_services} services that this business would realistically offer
2. PRIORITIZE services mentioned or implied in the website content and customer reviews
3. Each service should have a compelling title and detailed description
4. Services should be specific to this type of business and location
5. Descriptions should be 1-2 sentences, professional but approachable
6. Create unique service IDs using lowercase with hyphens (e.g., "emergency-repairs")
7. Include imageUrl and alt fields for each service (will be populated automatically)
8. If the website content mentions specific services, equipment, or specialties, INCLUDE THOSE

OUTPUT FORMAT (JSON):
{{
  "title": "Our Services",
  "subtitle": "Professional solutions tailored to your needs",
  "items": [
    {{
      "id": "service-id-1",
      "title": "Service Title 1",
      "description": "Detailed description of the service that explains what it includes and benefits.",
      "imageUrl": "",
      "alt": "Descriptive alt text for the service image"
    }},
    {{
      "id": "service-id-2", 
      "title": "Service Title 2",
      "description": "Detailed description of the service that explains what it includes and benefits.",
      "imageUrl": "",
      "alt": "Descriptive alt text for the service image"
    }}
  ]
}}

IMPORTANT: Leave imageUrl empty - it will be populated automatically. Focus on creating compelling alt text that describes what the service image should show.

Generate the services section now:"""

        try:
            # Use validation and retry loop
            services_data = await self._validate_and_retry_json_generation(
                prompt=prompt,
                validation_func=self._validate_services_section,
                max_retries=3,
                section_name="services section"
            )
            
            if services_data:
                # Add Unsplash images to each service
                business_type = business_data.business_type if business_data else ""
                for item in services_data.get("items", []):
                    # Generate image terms and URL
                    image_terms = self._get_service_image_terms(item["title"], business_type)
                    item["imageUrl"] = self._generate_unsplash_url(image_terms, width=600, height=400)
                
                print(f"✅ Generated {len(services_data.get('items', []))} services with images using AI")
                return services_data
            
            # Fallback to template-based generation
            print("⚠️ Using fallback service generation")
            return self._generate_fallback_services(business_name, business_description, max_services)
            
        except Exception as e:
            print(f"❌ Error generating services with AI: {e}")
            return self._generate_fallback_services(business_name, business_description, max_services)
    
    async def generate_about_section(
        self,
        business_name: str,
        business_location: str,
        business_description: str,
        business_data: Optional[BusinessData] = None,
        cleaned_html: Optional[str] = None,
        hero_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate about section using AI and business data
        
        Args:
            business_name: Name of the business
            business_location: Location of the business
            business_description: Description of what the business does
            business_data: Optional BusinessData from GBPResearcher
            cleaned_html: Optional cleaned HTML content (if not in business_data)
            hero_context: Optional hero section data to avoid redundancy
            
        Returns:
            About section dictionary matching schema
        """
        print(f"📖 Generating about section for {business_name}...")
        
        # Prepare context from business data
        context_info = []
        if business_data:
            if business_data.business_type:
                context_info.append(f"Business type: {business_data.business_type}")
            
            # Add detailed service categories from Google Maps data
            if business_data.maps_data and "place" in business_data.maps_data and "category" in business_data.maps_data["place"]:
                categories = business_data.maps_data["place"]["category"]
                if categories and len(categories) > 1:
                    category_titles = [cat.get("title", "") for cat in categories[:5]]  # Top 5 categories
                    context_info.append(f"Service categories: {', '.join(category_titles)}")
            
            if business_data.rating and business_data.review_count:
                context_info.append(f"Customer rating: {business_data.rating}/5 stars with {business_data.review_count} reviews")
            if business_data.cleaned_html:
                # Use more HTML content for about section to get rich business details
                context_info.append(f"Website content about the business: {business_data.cleaned_html[:1200]}")
            if business_data.reviews and business_data.reviews.reviews_summary:
                context_info.append(f"Customer feedback summary: {business_data.reviews.reviews_summary[:400]}")
        
        # Use standalone cleaned_html if provided and not already in business_data
        if cleaned_html and (not business_data or not business_data.cleaned_html):
            context_info.append(f"Website content about the business: {cleaned_html[:1200]}")
        
        context = "\n".join(context_info) if context_info else "No additional business data available."
        
        # Prepare hero context information
        hero_context_info = ""
        if hero_context:
            hero_parts = []
            if "headline" in hero_context:
                hero_parts.append(f"Hero Headline: {hero_context['headline']}")
            if "subheadline" in hero_context:
                hero_parts.append(f"Hero Subheadline: {hero_context['subheadline']}")
            if "cta" in hero_context and "label" in hero_context["cta"]:
                hero_parts.append(f"Hero CTA: {hero_context['cta']['label']}")
            
            if hero_parts:
                hero_context_info = f"""

HERO SECTION CONTEXT (AVOID REDUNDANCY - Don't repeat these messages):
{chr(10).join(hero_parts)}

IMPORTANT: The hero section already covers the main value proposition. Your about section should:
- Focus on building trust and credibility rather than repeating the hero message
- Provide different details about expertise, experience, and company background
- Complement the hero section, don't duplicate its messaging"""
        
        # Create AI prompt for about section (without icons - they'll be generated separately)
        prompt = f"""You are creating an about section for a local business website. Generate compelling content that establishes trust and credibility.

BUSINESS INFORMATION:
- Name: {business_name}
- Location: {business_location}
- Description: {business_description}

ADDITIONAL CONTEXT (VERY IMPORTANT - USE THIS TO UNDERSTAND THE ACTUAL BUSINESS):
{context}{hero_context_info}

REQUIREMENTS:
1. Create a professional but warm "About" section that COMPLEMENTS the hero section
2. Generate a compelling description (2-3 sentences) that highlights expertise and company background
3. USE INFORMATION FROM THE WEBSITE CONTENT to make the description specific and authentic
4. AVOID repeating the hero section's messaging - focus on different aspects like experience, team, values
5. Create 3 realistic statistics WITHOUT icons (icons will be added separately)
6. Generate 4-6 key features/benefits that are DIFFERENT from what's implied in the hero section
7. Make it specific to this business type and location
8. Use professional language that builds trust and credibility
9. If the website content mentions experience, certifications, or specialties, INCLUDE THOSE

OUTPUT FORMAT (JSON):
{{
  "title": "About {business_name}",
  "description": "Professional description that highlights expertise, experience, and commitment to the community (DIFFERENT from hero messaging).",
  "statistics": [
    {{
      "name": "Statistic Name",
      "value": "Number+"
    }}
  ],
  "features": [
    "Feature 1 (different from hero focus)",
    "Feature 2 (different from hero focus)",
    "Feature 3 (different from hero focus)"
  ],
  "images": [
    {{
      "imageUrl": "",
      "alt": "Professional service consultation showing team expertise"
    }},
    {{
      "imageUrl": "",
      "alt": "Modern tools and equipment used for quality work"
    }},
    {{
      "imageUrl": "",
      "alt": "Professional team working on client project"
    }}
  ]
}}

IMPORTANT: 
- Do NOT include "icon" fields in statistics - they will be added in a separate step
- Leave "imageUrl" fields empty - they will be populated with appropriate Unsplash URLs automatically
- Create compelling "alt" text that describes what each image should show based on your business context

Generate the about section now:"""

        try:
            # Use validation and retry loop
            about_data = await self._validate_and_retry_json_generation(
                prompt=prompt,
                validation_func=self._validate_about_section,
                max_retries=3,
                section_name="about section"
            )
            
            if about_data:
                # Step 2: Generate icons for statistics
                if "statistics" in about_data and about_data["statistics"]:
                    business_type = business_data.business_type if business_data else "Professional Services"
                    about_data["statistics"] = await self._generate_statistics_icons(
                        business_name=business_name,
                        business_type=business_type,
                        statistics=about_data["statistics"]
                    )
                
                # Step 3: Generate Unsplash URLs for images
                if "images" in about_data and about_data["images"]:
                    business_type = business_data.business_type if business_data else "Professional Services"
                    for image in about_data["images"]:
                        # Generate image terms based on alt text and business type
                        image_terms = self._get_about_image_terms(image.get("alt", ""), business_type)
                        image["imageUrl"] = self._generate_unsplash_url(image_terms, width=800, height=600, quality=80)
                    
                    print(f"✅ Generated {len(about_data['images'])} images for about section")
                
                print(f"✅ Generated about section with {len(about_data.get('features', []))} features using AI")
                return about_data
            
            # Fallback to template-based generation
            print("⚠️ Using fallback about generation")
            return self._generate_fallback_about(business_name, business_description)
            
        except Exception as e:
            print(f"❌ Error generating about section with AI: {e}")
            return self._generate_fallback_about(business_name, business_description)
    
    async def generate_business_benefits_section(
        self,
        business_name: str,
        business_location: str,
        business_description: str,
        business_data: Optional[BusinessData] = None,
        cleaned_html: Optional[str] = None,
        hero_context: Optional[Dict[str, Any]] = None,
        max_benefits: int = 6
    ) -> Dict[str, Any]:
        """
        Generate business benefits section using AI and business data
        
        Args:
            business_name: Name of the business
            business_location: Location of the business
            business_description: Description of what the business does
            business_data: Optional BusinessData from GBPResearcher
            cleaned_html: Optional cleaned HTML content (if not in business_data)
            hero_context: Optional hero section data to avoid redundancy
            max_benefits: Maximum number of benefits to generate
            
        Returns:
            Business benefits section dictionary matching schema
        """
        print(f"💼 Generating business benefits section for {business_name}...")
        
        # Prepare context from business data
        context_info = []
        service_features = []
        
        if business_data:
            if business_data.business_type:
                context_info.append(f"Business type: {business_data.business_type}")
            
            # Extract service features from maps data
            if business_data.maps_data:
                service_features = self._extract_maps_service_tags(business_data.maps_data)
                if service_features:
                    context_info.append(f"Service features from Google: {', '.join(service_features)}")
            
            # Add detailed service categories from Google Maps data
            if business_data.maps_data and "place" in business_data.maps_data and "category" in business_data.maps_data["place"]:
                categories = business_data.maps_data["place"]["category"]
                if categories and len(categories) > 1:
                    category_titles = [cat.get("title", "") for cat in categories[:5]]
                    context_info.append(f"Service categories: {', '.join(category_titles)}")
            
            if business_data.rating and business_data.review_count:
                context_info.append(f"Customer rating: {business_data.rating}/5 stars with {business_data.review_count} reviews")
            if business_data.cleaned_html:
                context_info.append(f"Website content: {business_data.cleaned_html[:800]}")
            if business_data.reviews and business_data.reviews.reviews:
                # Extract common themes from reviews
                reviews_text = " ".join([r.review_text or "" for r in business_data.reviews.reviews[:3]])
                context_info.append(f"Customer mentions: {reviews_text[:400]}")
        
        # Use standalone cleaned_html if provided
        if cleaned_html and (not business_data or not business_data.cleaned_html):
            context_info.append(f"Website content: {cleaned_html[:800]}")
        
        context = "\n".join(context_info) if context_info else "No additional business data available."
        
        # Prepare hero context information
        hero_context_info = ""
        if hero_context:
            hero_parts = []
            if "headline" in hero_context:
                hero_parts.append(f"Hero Headline: {hero_context['headline']}")
            if "subheadline" in hero_context:
                hero_parts.append(f"Hero Subheadline: {hero_context['subheadline']}")
            
            if hero_parts:
                hero_context_info = f"""

HERO SECTION CONTEXT (AVOID REDUNDANCY):
{chr(10).join(hero_parts)}

IMPORTANT: Focus on specific operational benefits rather than repeating hero messaging."""
        
        # Create AI prompt for business benefits
        prompt = f"""You are creating a business benefits section for a local business website. Generate compelling benefits that highlight what makes this business special.

BUSINESS INFORMATION:
- Name: {business_name}
- Location: {business_location}
- Description: {business_description}

ADDITIONAL CONTEXT (VERY IMPORTANT):
{context}{hero_context_info}

REQUIREMENTS:
1. Generate exactly {max_benefits} business benefits/advantages
2. Each benefit should have a compelling title and detailed description
3. Focus on OPERATIONAL benefits (how they work, what they provide, their approach)
4. USE service features from Google Maps data if available
5. Make benefits specific to this business type and location
6. Avoid generic benefits - be specific about what this business does differently
7. If website content mentions unique processes, equipment, or approaches, INCLUDE THOSE
8. Benefits should be different from hero messaging - focus on "how" and "why" rather than "what"

OUTPUT FORMAT (JSON):
{{
  "title": "Why Choose Our Services",
  "items": [
    {{
      "title": "Benefit Title 1",
      "description": "Detailed description of this specific benefit"
    }},
    {{
      "title": "Benefit Title 2", 
      "description": "Detailed description of this specific benefit"
    }},
    {{
      "title": "Benefit Title 3",
      "description": "Detailed description of this specific benefit"
    }},
    {{
      "title": "Benefit Title 4",
      "description": "Detailed description of this specific benefit"
    }},
    {{
      "title": "Benefit Title 5",
      "description": "Detailed description of this specific benefit"
    }},
    {{
      "title": "Benefit Title 6",
      "description": "Detailed description of this specific benefit"
    }}
  ]
}}

EXAMPLES OF GOOD BENEFITS:
- "Licensed & Insured Professionals" → "All our technicians are fully licensed and we carry comprehensive insurance"
- "Same-Day Service Available" → "Emergency calls receive priority scheduling with same-day service when possible"
- "Transparent Pricing" → "We provide detailed estimates upfront with no hidden fees or surprise charges"

Generate the business benefits now:"""

        try:
            if not self.gemini_client:
                print("⚠️ Using fallback business benefits generation")
                return self._generate_fallback_business_benefits(service_features, max_benefits)
            
            # Generate benefits with AI
            response = await asyncio.to_thread(
                self.gemini_client.ask,
                prompt,
                disable_thinking=True
            )
            
            # Parse JSON response
            parsed_data = self._parse_json_response(response)
            if not parsed_data:
                print("⚠️ Failed to parse benefits response, using fallback")
                return self._generate_fallback_business_benefits(service_features, max_benefits)
            
            # Validate that we have the expected benefit structure
            if "title" not in parsed_data or "items" not in parsed_data:
                print("⚠️ Invalid benefits structure - missing title or items, using fallback")
                return self._generate_fallback_business_benefits(service_features, max_benefits)
            
            if not isinstance(parsed_data["items"], list) or len(parsed_data["items"]) != max_benefits:
                print("⚠️ Invalid benefits items structure, using fallback")
                return self._generate_fallback_business_benefits(service_features, max_benefits)
            
            # Validate each benefit item
            for i, item in enumerate(parsed_data["items"]):
                if not isinstance(item, dict) or "title" not in item or "description" not in item:
                    print(f"⚠️ Invalid benefit item {i} structure, using fallback")
                    return self._generate_fallback_business_benefits(service_features, max_benefits)
            
            print(f"✅ Generated {max_benefits} business benefits using AI")
            return parsed_data
            
        except Exception as e:
            print(f"❌ Error generating business benefits with AI: {e}")
            return self._generate_fallback_business_benefits(service_features, max_benefits)
    
    def _generate_fallback_business_benefits(self, service_features: List[str], max_benefits: int = 6) -> Dict[str, Any]:
        """Generate fallback business benefits when AI is not available"""
        
        # Use service features from maps data if available
        benefits = []
        
        if "Online Estimates Available" in service_features:
            benefits.append({"title": "Online Estimates", "description": "Get accurate estimates through our convenient online system"})
        if "On-Site Services" in service_features:
            benefits.append({"title": "On-Site Service", "description": "We come to you with fully equipped service vehicles"})
        if "Wheelchair Accessible" in service_features:
            benefits.append({"title": "Accessible Service", "description": "Our facilities and services are wheelchair accessible"})
        if "Credit Cards Accepted" in service_features:
            benefits.append({"title": "Flexible Payment", "description": "We accept all major credit cards for your convenience"})
        if "LGBTQ+ Friendly" in service_features:
            benefits.append({"title": "Inclusive Service", "description": "We welcome and serve all customers with respect"})
        
        # Fill remaining slots with generic benefits
        generic_benefits = [
            {"title": "Licensed Professionals", "description": "Our team consists of fully licensed and certified professionals"},
            {"title": "Quality Workmanship", "description": "We take pride in delivering high-quality work on every project"},
            {"title": "Competitive Pricing", "description": "Fair and transparent pricing with no hidden fees"},
            {"title": "Fast Response Time", "description": "Quick response to your service requests and inquiries"},
            {"title": "Customer Satisfaction", "description": "Your satisfaction is our top priority on every job"},
            {"title": "Local Expertise", "description": "Deep knowledge of local regulations and community needs"}
        ]
        
        # Combine service features with generic benefits
        all_benefits = benefits + generic_benefits
        selected_benefits = all_benefits[:max_benefits]
        
        # Format as expected by example_site.json structure
        return {
            "title": "Why Choose Our Services",
            "items": selected_benefits
        }
    
    async def generate_contact_section(
        self,
        business_name: str,
        business_location: str,
        business_description: str,
        business_data: Optional[BusinessData] = None,
        cleaned_html: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate contact section using maps data and business information
        
        Args:
            business_name: Name of the business
            business_location: Location of the business
            business_description: Description of what the business does
            business_data: Optional BusinessData from GBPResearcher
            cleaned_html: Optional cleaned HTML content (if not in business_data)
            
        Returns:
            Contact section dictionary matching schema
        """
        print(f"📞 Generating contact section for {business_name}...")
        
        # Extract contact info from maps data
        contact_info = {"address": "", "phone": "", "hours": {}, "website": "", "latitude": None, "longitude": None}
        if business_data and business_data.maps_data:
            contact_info = self._extract_maps_contact_info(business_data.maps_data)
        
        # Generate map embed URL if we have coordinates
        map_embed_url = ""
        if contact_info["latitude"] and contact_info["longitude"]:
            # Create Google Maps embed URL
            lat = contact_info["latitude"]
            lng = contact_info["longitude"]
            encoded_address = urllib.parse.quote(contact_info["address"] or business_location)
            map_embed_url = f"https://maps.google.com/maps?width=100%25&height=600&hl=en&q={encoded_address}&t=&z=14&ie=UTF8&iwloc=B&output=embed"
        elif contact_info["address"]:
            # Fallback with address only
            encoded_address = urllib.parse.quote(contact_info["address"])
            map_embed_url = f"https://maps.google.com/maps?width=100%25&height=600&hl=en&q={encoded_address}&t=&z=14&ie=UTF8&iwloc=B&output=embed"
        else:
            # Fallback with business location
            encoded_location = urllib.parse.quote(business_location)
            map_embed_url = f"https://maps.google.com/maps?width=100%25&height=600&hl=en&q={encoded_location}&t=&z=14&ie=UTF8&iwloc=B&output=embed"
        
        # Format phone number for display and tel links
        phone_display = contact_info["phone"]
        phone_tel = contact_info["phone"]
        if phone_display and phone_display.startswith("+1"):
            # Format US phone numbers nicely
            digits = ''.join(filter(str.isdigit, phone_display))
            if len(digits) == 11 and digits.startswith('1'):
                formatted = f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
                phone_display = formatted
        
        # Generate email (fallback since maps data doesn't usually have email)
        contact_email = ""
        if contact_info["website"]:
            # Try to extract domain for email
            try:
                from urllib.parse import urlparse
                domain = urlparse(contact_info["website"]).netloc
                if domain:
                    domain = domain.replace("www.", "")
                    contact_email = f"info@{domain}"
            except:
                pass
        
        if not contact_email:
            # Generic fallback
            business_domain = business_name.lower().replace(" ", "").replace("'", "").replace("&", "and")
            contact_email = f"info@{business_domain}.com"
        
        # Build contact section to match example_site.json structure
        contact_section = {
            "contact": {
                "title": "Contact Us",
                "subtitle": "Get in touch with us today. We're here to help with all your needs.",
                "address": contact_info["address"] or f"{business_location}",
                "phone": phone_tel,
                "email": contact_email,
                "mapEmbedUrl": map_embed_url,
                "social": {
                    "facebook": "",
                    "twitter": "",
                    "instagram": "",
                    "linkedin": "",
                    "youtube": "",
                    "tiktok": "",
                    "yelp": ""
                }
            }
        }
        
        # Add hours if available
        if contact_info["hours"]:
            # Convert hours to structured format for easier parsing
            structured_hours = self._parse_hours_to_structured_format(contact_info["hours"])
            contact_section["contact"]["businessHours"] = structured_hours
        else:
            # Fallback structured hours if no hours data available
            contact_section["contact"]["businessHours"] = {
                "Monday": {"open": "9:00 AM", "close": "5:00 PM"},
                "Tuesday": {"open": "9:00 AM", "close": "5:00 PM"},
                "Wednesday": {"open": "9:00 AM", "close": "5:00 PM"},
                "Thursday": {"open": "9:00 AM", "close": "5:00 PM"},
                "Friday": {"open": "9:00 AM", "close": "5:00 PM"},
                "Saturday": {"open": "9:00 AM", "close": "4:00 PM"},
                "Sunday": "closed"
            }
        
        print(f"✅ Generated contact section with address: {contact_info['address'][:50]}...")
        return contact_section["contact"]  # Return just the contact object, not wrapped
    
    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """
        Parse JSON response from AI, handling common formatting issues
        
        Args:
            response: Raw response string from AI
            
        Returns:
            Parsed JSON dictionary or None if parsing fails
        """
        try:
            # Clean up the response - remove markdown code blocks if present
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            
            # Parse JSON
            return json.loads(cleaned.strip())
            
        except json.JSONDecodeError as e:
            print(f"⚠️ Failed to parse AI JSON response: {e}")
            print(f"Raw response: {response[:200]}...")
            return None
        except Exception as e:
            print(f"⚠️ Error processing AI response: {e}")
            return None
    
    def _generate_fallback_services(
        self, 
        business_name: str, 
        business_description: str, 
        max_services: int
    ) -> Dict[str, Any]:
        """Generate fallback services when AI is not available"""
        
        # Generic services based on common business types
        generic_services = [
            {
                "id": "consultation",
                "title": "Professional Consultation", 
                "description": "Expert advice and consultation tailored to your specific needs and requirements.",
                "alt": "Professional consultation meeting"
            },
            {
                "id": "maintenance",
                "title": "Maintenance & Support",
                "description": "Regular maintenance and ongoing support to keep everything running smoothly.",
                "alt": "Professional maintenance service"
            },
            {
                "id": "emergency-service",
                "title": "Emergency Service",
                "description": "24/7 emergency services for urgent situations and critical needs.",
                "alt": "Emergency service response"
            },
            {
                "id": "installation",
                "title": "Installation & Setup",
                "description": "Professional installation and setup services with attention to detail.",
                "alt": "Professional installation work"
            },
            {
                "id": "repair",
                "title": "Repair Services",
                "description": "Expert repair services to restore functionality and extend service life.",
                "alt": "Expert repair services"
            }
        ]
        
        # Add images to each service
        selected_services = generic_services[:max_services]
        for service in selected_services:
            image_terms = self._get_service_image_terms(service["title"], "")
            service["imageUrl"] = self._generate_unsplash_url(image_terms, width=600, height=400)
        
        return {
            "title": "Our Services",
            "subtitle": "Professional solutions tailored to your needs", 
            "items": selected_services
        }
    
    def _generate_fallback_about(self, business_name: str, business_description: str) -> Dict[str, Any]:
        """Generate fallback about section when AI is not available"""
        
        return {
            "title": f"About {business_name}",
            "description": f"We are a trusted local business serving our community with professional services. {business_description} Our experienced team provides comprehensive solutions for residential and commercial clients.",
            "statistics": [
                {
                    "name": "Years of Experience",
                    "value": "10+",
                    "icon": "AcademicCapIcon"
                },
                {
                    "name": "Satisfied Clients",
                    "value": "200+", 
                    "icon": "UsersIcon"
                },
                {
                    "name": "Services Offered",
                    "value": "5+",
                    "icon": "BuildingOfficeIcon"
                }
            ],
            "features": [
                "Licensed Professionals",
                "Quality Workmanship", 
                "Competitive Pricing",
                "Fast & Reliable Service",
                "Customer Satisfaction Guarantee",
                "Local Community Focus"
            ],
            "images": [
                {
                    "imageUrl": self._generate_unsplash_url(["professional", "consultation", "business"], width=800, height=600),
                    "alt": "Professional service consultation"
                },
                {
                    "imageUrl": self._generate_unsplash_url(["tools", "professional", "workspace"], width=800, height=600),
                    "alt": "Professional tools and workspace"
                },
                {
                    "imageUrl": self._generate_unsplash_url(["team", "professional", "collaboration"], width=800, height=600),
                    "alt": "Professional team collaboration"
                }
            ]
        }
    
    async def generate_complete_site_json(
        self,
        business_name: str,
        business_location: str,
        business_description: str,
        business_data: Optional[BusinessData] = None,
        cleaned_html: Optional[str] = None,
        output_file: Optional[str] = None,
        max_services: int = 3,
        max_testimonials: int = 6
    ) -> Dict[str, Any]:
        """
        Generate a complete site.json with all sections integrated
        
        Args:
            business_name: Name of the business
            business_location: Location of the business
            business_description: Description of what the business does
            business_data: Optional BusinessData from GBPResearcher
            cleaned_html: Optional cleaned HTML content (if not in business_data)
            output_file: Optional file path to save the generated site.json
            max_services: Maximum number of services to generate
            max_testimonials: Maximum number of testimonials to include
            
        Returns:
            Complete site.json dictionary with all sections integrated
        """
        print(f"🏗️ Generating complete site.json for {business_name}...")
        print("=" * 60)
        
        try:
            # Step 1: Copy the template
            print("📋 Step 1: Copying template site.json...")
            site_data = self.copy_template_site_json()
            
            # Step 2: Update basic business info
            print("🏢 Step 2: Updating business information...")
            site_data["businessName"] = business_name
            
            # Step 3: Generate hero section
            print("🦸 Step 3: Generating hero section...")
            hero_section = await self.generate_hero_section(
                business_name=business_name,
                business_location=business_location,
                business_description=business_description,
                business_data=business_data,
                cleaned_html=cleaned_html
            )
            site_data["hero"] = hero_section
            
            # Step 4: Generate multiple sections in parallel (about, services, businessBenefits, contact)
            print("🔧 Step 4: Generating about, services, business benefits, and contact sections in parallel...")
            
            # Run all section generations in parallel
            about_task = self.generate_about_section(
                business_name=business_name,
                business_location=business_location,
                business_description=business_description,
                business_data=business_data,
                cleaned_html=cleaned_html,
                hero_context=hero_section
            )
            
            services_task = self.generate_services_section(
                business_name=business_name,
                business_location=business_location,
                business_description=business_description,
                business_data=business_data,
                cleaned_html=cleaned_html,
                max_services=max_services
            )
            
            benefits_task = self.generate_business_benefits_section(
                business_name=business_name,
                business_location=business_location,
                business_description=business_description,
                business_data=business_data,
                cleaned_html=cleaned_html,
                hero_context=hero_section,
                max_benefits=6
            )
            
            contact_task = self.generate_contact_section(
                business_name=business_name,
                business_location=business_location,
                business_description=business_description,
                business_data=business_data,
                cleaned_html=cleaned_html
            )
            
            # Wait for all parallel tasks to complete
            about_section, services_section, benefits_section, contact_section = await asyncio.gather(
                about_task, services_task, benefits_task, contact_task
            )
            
            # Apply results to site data
            site_data["about"] = about_section
            site_data["services"] = services_section
            
            # Apply business benefits to site data
            site_data["businessBenefits"] = benefits_section
            
            # Apply contact section to site data
            site_data["contact"] = contact_section
            
            print("✅ All parallel sections completed successfully!")
            
            # Step 5: Generate testimonials from reviews if available
            if business_data and business_data.reviews and business_data.reviews.reviews:
                print("🎯 Step 5: Generating testimonials from reviews...")
                site_data = self.populate_testimonials_from_reviews(
                    site_data=site_data,
                    reviews=business_data.reviews.reviews,
                    max_testimonials=max_testimonials
                )
            else:
                print("⚠️ Step 5: No reviews available - keeping template testimonials")
            
            # Step 6: Save to file if requested
            if output_file:
                print(f"💾 Step 6: Saving to {output_file}...")
                self.save_site_json(site_data, output_file)
            else:
                print("⚠️ Step 6: No output file specified - skipping save")
            
            # Summary
            print("\n✅ COMPLETE SITE.JSON GENERATED!")
            print("=" * 60)
            print(f"📊 Summary (Hero → Parallel Generation):")
            print(f"   • Business Name: {site_data.get('businessName')}")
            print(f"   • Hero Headline: {site_data.get('hero', {}).get('headline', 'N/A')}")
            print(f"   • About Title: {site_data.get('about', {}).get('title', 'N/A')} (informed by hero)")
            print(f"   • Services Count: {len(site_data.get('services', {}).get('items', []))}")
            print(f"   • Business Benefits: {len(site_data.get('businessBenefits', {}).get('items', []))}")
            print(f"   • Contact Address: {site_data.get('contact', {}).get('address', 'N/A')[:40]}...")
            print(f"   • Contact Phone: {site_data.get('contact', {}).get('phone', 'N/A')}")
            print(f"   • Testimonials Count: {len(site_data.get('testimonials', {}).get('items', []))}")
            
            if output_file:
                print(f"   • Saved to: {output_file}")
            
            return site_data
            
        except Exception as e:
            print(f"❌ Error generating complete site.json: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def save_site_json(self, site_data: Dict[str, Any], output_file: str) -> None:
        """
        Save site.json data to a file
        
        Args:
            site_data: The site.json dictionary to save
            output_file: Path where to save the file
        """
        try:
            # Ensure the directory exists
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save with pretty formatting
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(site_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Site.json saved successfully to: {output_file}")
            
        except Exception as e:
            print(f"❌ Error saving site.json: {e}")
            raise


# Example usage and testing
async def main(
    business_name: str, 
    business_location: str, 
    business_description: str,
    output_file: str = None,
    max_services: int = 4,
    max_testimonials: int = 6
):
    """Test the ClientBusinessResearcher complete workflow"""
    print("🏢 Testing ClientBusinessResearcher - Complete Site.json Generation")
    print("=" * 60)
    
    try:
        # Initialize researcher
        researcher = ClientBusinessResearcher()
        
        # Get business data including reviews
        print("\n📊 Step 1: Gathering business data...")
        html, maps_data, reviews = await researcher.gbp_researcher.get_business_data(
            business_name=business_name,
            business_location=business_location,
            max_reviews=10
        )
        
        # Create business data object with proper business type extraction
        business_data = None
        if maps_data or reviews or html:
            from gbp_researcher import BusinessReviewsResult
            
            # Extract business type from Google Maps categories
            business_type = "Professional Services"  # Default fallback
            if maps_data and "place" in maps_data and "category" in maps_data["place"]:
                categories = maps_data["place"]["category"]
                if categories:
                    # Get the primary category title
                    primary_category = categories[0].get("title", "Professional Services")
                    business_type = primary_category
                    print(f"📊 Extracted business type: {business_type}")
            
            # Extract phone number from maps data
            phone_number = None
            if maps_data and "place" in maps_data and "phone" in maps_data["place"]:
                phone_number = maps_data["place"]["phone"]
                print(f"📞 Extracted phone: {phone_number}")
            
            business_data = BusinessData(
                name=business_name,
                business_type=business_type,
                phone=phone_number,
                cleaned_html=html,
                maps_data=maps_data
            )
            if reviews:
                business_data.reviews = BusinessReviewsResult(
                    business_name=business_name,
                    business_fid="test-fid",
                    reviews=reviews
                )
        
        # Use provided output file or generate default filename
        if not output_file:
            safe_name = business_name.replace(" ", "_").replace("'", "").replace("&", "and")
            output_file = f"generated_sites/{safe_name}_site.json"
        
        # Generate complete site.json
        print(f"\n🚀 Step 2: Generating complete site.json...")
        complete_site_data = await researcher.generate_complete_site_json(
            business_name=business_name,
            business_location=business_location,
            business_description=business_description,
            business_data=business_data,
            output_file=output_file,
            max_services=max_services,
            max_testimonials=max_testimonials
        )
        
        # Show detailed results
        print(f"\n📋 DETAILED RESULTS:")
        print(f"=" * 40)
        
        # Hero section details
        hero = complete_site_data.get("hero", {})
        print(f"\n🦸 HERO SECTION:")
        print(f"   Headline: {hero.get('headline', 'N/A')}")
        print(f"   Subheadline: {hero.get('subheadline', 'N/A')[:60]}...")
        print(f"   CTA: {hero.get('cta', {}).get('label', 'N/A')} → {hero.get('cta', {}).get('href', 'N/A')}")
        print(f"   Phone: {hero.get('phone', 'N/A')}")
        
        # Services section details
        services = complete_site_data.get("services", {})
        print(f"\n🔧 SERVICES SECTION:")
        print(f"   Title: {services.get('title', 'N/A')}")
        print(f"   Subtitle: {services.get('subtitle', 'N/A')}")
        print(f"   Services ({len(services.get('items', []))}):")
        for i, service in enumerate(services.get('items', [])[:3]):
            print(f"      {i+1}. {service.get('title', 'N/A')}")
            print(f"         {service.get('description', 'N/A')[:80]}...")
        
        # About section details
        about = complete_site_data.get("about", {})
        print(f"\n📖 ABOUT SECTION:")
        print(f"   Title: {about.get('title', 'N/A')}")
        print(f"   Description: {about.get('description', 'N/A')[:100]}...")
        print(f"   Statistics ({len(about.get('statistics', []))}):")
        for stat in about.get('statistics', [])[:3]:
            print(f"      • {stat.get('name', 'N/A')}: {stat.get('value', 'N/A')}")
        print(f"   Features ({len(about.get('features', []))}):")
        for feature in about.get('features', [])[:3]:
            print(f"      • {feature}")
        
        # Testimonials section details
        testimonials = complete_site_data.get("testimonials", {})
        print(f"\n🎯 TESTIMONIALS SECTION:")
        print(f"   Title: {testimonials.get('title', 'N/A')}")
        print(f"   Testimonials ({len(testimonials.get('items', []))}):")
        for i, testimonial in enumerate(testimonials.get('items', [])[:2]):
            print(f"      {i+1}. {testimonial.get('authorName', 'N/A')} (⭐{testimonial.get('rating', 'N/A')})")
            print(f"         \"{testimonial.get('reviewText', 'N/A')[:60]}...\"")
        
        print(f"\n🎉 COMPLETE WORKFLOW SUCCESSFUL!")
        print(f"✅ Generated complete site.json with all sections integrated")
        print(f"💾 Saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error during complete workflow test: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import argparse
    
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(description="Generate site.json for a local business")
    parser.add_argument("--business-name", required=True, help="Name of the business")
    parser.add_argument("--business-location", required=True, help="Location of the business")
    parser.add_argument("--business-description", required=True, help="Description of the business")
    parser.add_argument("--output", required=True, help="Output file path for the generated site.json")
    parser.add_argument("--max-services", type=int, default=4, help="Maximum number of services to generate (default: 4)")
    parser.add_argument("--max-testimonials", type=int, default=6, help="Maximum number of testimonials to include (default: 6)")
    
    args = parser.parse_args()
    
    # Run the main function with CLI arguments
    asyncio.run(main(
        business_name=args.business_name,
        business_location=args.business_location, 
        business_description=args.business_description,
        output_file=args.output,
        max_services=args.max_services,
        max_testimonials=args.max_testimonials
    ))
