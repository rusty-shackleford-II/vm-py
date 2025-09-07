#!/usr/bin/env python3
"""
Standalone Test Script for Research-Based Site.json Generation
============================================================

This script demonstrates how to use the existing search infrastructure and Gemini AI
to automatically generate a complete site.json file for the local business template
based on business research data.

Parameters:
- business_name: Name of the business to research
- business_location: Location/address of the business  
- description (optional): Additional context about the business

The script will:
1. Search for the business using GoogleSearcher and GoogleMapsBusinessSearcher
2. Find the Google business page if it exists
3. Gather business information, reviews, and ratings
4. Use Gemini AI to transform this data into a complete site.json matching the schema
"""

import asyncio
import json
import os
import argparse
from typing import Dict, Any, Optional, List
from pathlib import Path

# Import existing components
from google_searcher import GoogleSearcher, LocalBusinessResult
from google_maps_searcher import GoogleMapsBusinessSearcher
from business_review_searcher import BusinessReviewSearcher
from clients.gemini_client import GeminiClient
import config


class SiteJsonGenerator:
    """Generates site.json files for local businesses using AI and search data"""
    
    def __init__(self):
        """Initialize all required clients"""
        print("🚀 Initializing Site JSON Generator...")
        
        # Initialize search clients
        self.google_searcher = GoogleSearcher(enhanced_mode=True)
        self.google_maps_searcher = GoogleMapsBusinessSearcher()
        self.review_searcher = BusinessReviewSearcher(use_enhanced_searcher=True)
        
        # Initialize Gemini client with all available keys
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
        
        self.gemini_client = GeminiClient(api_keys=gemini_keys, model_name="gemini-2.0-flash")
        
        print(f"✅ Initialized with {len(gemini_keys)} Gemini API keys")
        
        # Load the site.json schema for reference
        self.schema = self._load_schema()
        self.template_site_json = self._load_template_site_json()
        
    def _load_schema(self) -> Dict[str, Any]:
        """Load the local business template schema"""
        schema_path = Path(__file__).parent / ".." / "vm-web" / "templates" / "local-business" / "data" / "schema.json"
        try:
            with open(schema_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Could not load schema: {e}")
            return {}
    
    def _load_template_site_json(self) -> Dict[str, Any]:
        """Load the template site.json for reference"""
        template_path = Path(__file__).parent / ".." / "vm-web" / "templates" / "local-business" / "data" / "site.json"
        try:
            with open(template_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Could not load template site.json: {e}")
            return {}
    
    async def search_business_info(self, business_name: str, business_location: str) -> Dict[str, Any]:
        """Search for comprehensive business information"""
        print(f"🔍 Searching for business: '{business_name}' in '{business_location}'")
        
        business_data = {
            "search_query": f"{business_name} {business_location}",
            "local_results": [],
            "google_business": None,
            "reviews_data": {},
            "organic_results": []
        }
        
        try:
            # 1. Search for local businesses
            print("📍 Searching local businesses...")
            local_businesses = await self.google_searcher.search_local_businesses(
                query=business_name,
                location=business_location,
                max_results=10
            )
            business_data["local_results"] = [
                {
                    "name": b.name,
                    "address": b.address,
                    "phone": b.phone,
                    "website": b.website,
                    "rating": b.rating,
                    "review_count": b.review_count,
                    "category": b.category
                }
                for b in local_businesses
            ]
            print(f"✅ Found {len(local_businesses)} local businesses")
            
            # 2. Find specific Google business page
            print("🏢 Searching for specific Google business page...")
            google_business_result = self.google_maps_searcher.search_single_business(
                business_name=business_name,
                location=business_location,
                business_category=None  # Let the AI figure this out
            )
            
            if google_business_result.get("selected"):
                business_data["google_business"] = google_business_result["selected"]
                print(f"✅ Found Google business: {google_business_result['selected'].get('name')}")
                
                # Get reviews for this specific business
                if google_business_result.get("fid"):
                    print("📝 Fetching Google reviews...")
                    reviews = await self.google_maps_searcher.fetch_reviews_by_fid(
                        fid=google_business_result["fid"],
                        business_name=business_name,
                        max_results=20
                    )
                    if reviews:
                        business_data["reviews_data"]["google_reviews"] = [
                            {
                                "author_name": r.author_name,
                                "rating": r.rating,
                                "review_date": r.review_date,
                                "review_text": r.review_text,
                                "author_image": r.author_image
                            }
                            for r in reviews
                        ]
                        print(f"✅ Found {len(reviews)} Google reviews")
            else:
                print("⚠️ No specific Google business match found")
            
            # 3. Search for reviews from other sites
            print("⭐ Searching review sites...")
            review_sites_data = await self.review_searcher.get_business_review_data(
                business_name=business_name,
                location=business_location,
                max_results=15
            )
            if review_sites_data:
                business_data["reviews_data"]["review_sites"] = review_sites_data
                print(f"✅ Found reviews from {len(review_sites_data)} review sites")
            
            # 4. Get organic search results for additional context
            print("🌐 Getting organic search results...")
            organic_results = await self.google_searcher.search_organic_results(
                query=f"{business_name} {business_location}",
                location=business_location,
                max_results=10
            )
            business_data["organic_results"] = [
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "domain": r.domain
                }
                for r in organic_results
            ]
            print(f"✅ Found {len(organic_results)} organic results")
            
        except Exception as e:
            print(f"❌ Error during business search: {e}")
        
        return business_data
    
    def _create_site_generation_prompt(
        self, 
        business_name: str, 
        business_location: str, 
        business_data: Dict[str, Any], 
        description: Optional[str] = None
    ) -> str:
        """Create a comprehensive prompt for generating site.json"""
        
        # Convert business data to formatted string
        business_context = json.dumps(business_data, indent=2, default=str)
        
        # Get the template structure for reference
        template_structure = json.dumps(self.template_site_json, indent=2)
        
        description_context = f"\n\nADDITIONAL CONTEXT PROVIDED BY USER:\n{description}" if description else ""
        
        prompt = f"""You are an expert web developer and copywriter creating a professional business website. Your task is to generate a complete, accurate site.json file for "{business_name}" based on real business research data.

TARGET BUSINESS: {business_name}
LOCATION: {business_location}{description_context}

RESEARCH DATA GATHERED:
{business_context}

TEMPLATE STRUCTURE TO FOLLOW:
{template_structure}

YOUR TASK:
Generate a complete site.json that matches the template structure but is customized for this specific business. Use the research data to create authentic, accurate content.

CRITICAL REQUIREMENTS:

1. **Business Information Accuracy**: 
   - Use the EXACT business name from research data
   - Use real address, phone, website if found in research
   - Maintain factual accuracy - don't invent details not supported by data

2. **Content Sections to Generate**:
   - **businessName**: Exact name from research
   - **hero**: Compelling headline and subheadline specific to this business
   - **about**: Professional description based on business type and research
   - **services**: 3-6 realistic services based on business category and research
   - **businessBenefits**: 4-6 compelling benefits specific to this business type
   - **testimonials**: Use real Google reviews if available, otherwise create realistic ones
   - **contact**: Real contact info from research data

3. **Review Integration**:
   - If Google reviews are available, use 2-3 of the best ones for testimonials
   - Preserve original author names and review content
   - Use actual ratings from the reviews
   - If no reviews available, create realistic testimonials

4. **Business Type Adaptation**:
   - Tailor all content to the specific business category
   - Use industry-appropriate language and services
   - Include relevant business benefits for that industry

5. **Professional Quality**:
   - All text should be professional, engaging, and error-free
   - Headlines should be compelling but not overly promotional
   - Maintain consistent tone throughout

6. **Technical Requirements**:
   - Follow the exact JSON structure from the template
   - Include all required fields
   - Use proper data types (strings, arrays, objects)
   - Ensure valid JSON syntax

CONTENT GUIDELINES:
- Hero headline: Compelling but professional (not generic)
- About section: 2-3 sentences describing the business professionally
- Services: Realistic services for this business type (include descriptions)
- Benefits: Industry-specific advantages (24/7 service, licensed professionals, etc.)
- Contact: Use real data from research, don't invent

OUTPUT FORMAT:
Provide ONLY the complete JSON object. No explanations, no markdown formatting, no additional text. Start with {{ and end with }}.

Generate the site.json now:"""

        return prompt
    
    async def generate_site_json(
        self, 
        business_name: str, 
        business_location: str, 
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate a complete site.json for the business"""
        print(f"🎯 Generating site.json for '{business_name}'...")
        
        # 1. Gather business research data
        business_data = await self.search_business_info(business_name, business_location)
        
        # 2. Generate site.json using Gemini
        prompt = self._create_site_generation_prompt(
            business_name, business_location, business_data, description
        )
        
        print("🤖 Generating site content with Gemini AI...")
        try:
            response = self.gemini_client.ask(prompt, disable_thinking=True)
            
            # Clean up the response - remove markdown code blocks if present
            cleaned_response = response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]  # Remove ```json
            elif cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]   # Remove ```
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]  # Remove trailing ```
            
            cleaned_response = cleaned_response.strip()
            
            # Parse the JSON response
            site_json = json.loads(cleaned_response)
            
            print("✅ Site.json generated successfully!")
            return site_json
            
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing JSON response: {e}")
            print("Raw response:", response[:500] + "..." if len(response) > 500 else response)
            raise
        except Exception as e:
            print(f"❌ Error generating site.json: {e}")
            raise
    
    def save_site_json(self, site_json: Dict[str, Any], business_name: str, output_dir: str = "generated_sites"):
        """Save the generated site.json to a file"""
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Create safe filename
        safe_name = "".join(c for c in business_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')
        filename = f"{safe_name}_site.json"
        filepath = os.path.join(output_dir, filename)
        
        # Save the file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(site_json, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Saved site.json to: {filepath}")
        return filepath


async def main():
    """Main function to run the site generator"""
    parser = argparse.ArgumentParser(description="Generate site.json for local businesses using AI research")
    parser.add_argument("business_name", help="Name of the business")
    parser.add_argument("business_location", help="Location/address of the business")
    parser.add_argument("--description", "-d", help="Optional description or additional context about the business")
    parser.add_argument("--output", "-o", default="generated_sites", help="Output directory (default: generated_sites)")
    
    args = parser.parse_args()
    
    print("🚀 Starting Site JSON Generator")
    print("=" * 60)
    print(f"Business: {args.business_name}")
    print(f"Location: {args.business_location}")
    if args.description:
        print(f"Description: {args.description}")
    print("=" * 60)
    
    try:
        # Initialize the generator
        generator = SiteJsonGenerator()
        
        # Generate the site.json
        site_json = await generator.generate_site_json(
            business_name=args.business_name,
            business_location=args.business_location,
            description=args.description
        )
        
        # Save the result
        filepath = generator.save_site_json(site_json, args.business_name, args.output)
        
        print("\n🎉 SUCCESS!")
        print(f"Generated site.json for '{args.business_name}'")
        print(f"File saved to: {filepath}")
        
        # Show a preview of key sections
        print("\n📋 PREVIEW:")
        print(f"Business Name: {site_json.get('businessName', 'N/A')}")
        print(f"Hero Headline: {site_json.get('hero', {}).get('headline', 'N/A')}")
        
        services = site_json.get('services', {}).get('items', [])
        if services:
            print(f"Services: {len(services)} services defined")
            for i, service in enumerate(services[:3], 1):
                print(f"  {i}. {service.get('title', 'N/A')}")
        
        testimonials = site_json.get('testimonials', {}).get('items', [])
        if testimonials:
            print(f"Testimonials: {len(testimonials)} testimonials")
        
        contact = site_json.get('contact', {})
        if contact.get('address'):
            print(f"Address: {contact['address']}")
        if contact.get('phone'):
            print(f"Phone: {contact['phone']}")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
