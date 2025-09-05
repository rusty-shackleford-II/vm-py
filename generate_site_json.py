import asyncio
import argparse
import json
import re
from typing import Any, Dict, List, Optional

from google_searcher import GoogleSearcher, LocalBusinessResult, OrganicResult
from google_review_fetcher import GoogleReviewFetcher, BusinessReviewsResult
from clients.gemini_client import GeminiClient
import config


def build_location_string(city: str, region: str, country: str) -> str:
    parts: List[str] = [p for p in [city, region, country] if p]
    return ", ".join(parts)


def sanitize_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = value.strip()
    return text or None


def choose_best_business(
    candidates: List[LocalBusinessResult], target_name: str
) -> Optional[LocalBusinessResult]:
    if not candidates:
        return None

    # Exact, case-insensitive match first
    lowered_target = target_name.lower().strip()
    for biz in candidates:
        if biz.name and biz.name.lower().strip() == lowered_target:
            return biz

    # Token overlap fallback (simple heuristic)
    def token_set(s: str) -> set:
        tokens = re.findall(r"[a-z0-9]+", s.lower())
        return set(tokens)

    target_tokens = token_set(target_name)
    best_score = -1
    best_biz: Optional[LocalBusinessResult] = None
    for biz in candidates:
        if not biz.name:
            continue
        overlap = len(token_set(biz.name) & target_tokens)
        if overlap > best_score:
            best_score = overlap
            best_biz = biz

    return best_biz or candidates[0]


def industry_services(industry: str) -> List[Dict[str, str]]:
    key = (industry or "").lower()
    catalog: Dict[str, List[Dict[str, str]]] = {
        "plumber": [
            {"name": "Emergency Repairs", "description": "24/7 burst pipes, leaks, and urgent fixes."},
            {"name": "Water Heater", "description": "Installation, maintenance, and replacements."},
            {"name": "Drain Cleaning", "description": "Clogs cleared fast with safe methods."},
        ],
        "hvac": [
            {"name": "AC & Heating Repair", "description": "Diagnostics and same‑day fixes for most systems."},
            {"name": "System Install", "description": "High‑efficiency replacements and new installs."},
            {"name": "Maintenance", "description": "Seasonal tune‑ups to keep units running smoothly."},
        ],
        "electrician": [
            {"name": "Troubleshooting", "description": "Breakers, outlets, and wiring issues resolved."},
            {"name": "Panel Upgrades", "description": "Modernize capacity and improve safety."},
            {"name": "Lighting", "description": "Indoor/outdoor lighting design and installation."},
        ],
        "roofer": [
            {"name": "Roof Repair", "description": "Leak fixes and storm damage remediation."},
            {"name": "Roof Replacement", "description": "Shingle, metal, or flat roofing systems."},
            {"name": "Inspections", "description": "Detailed assessments with photos and estimates."},
        ],
        "dentist": [
            {"name": "Checkups & Cleanings", "description": "Preventive care for healthy smiles."},
            {"name": "Cosmetic Dentistry", "description": "Whitening, veneers, and smile makeovers."},
            {"name": "Restorative Care", "description": "Fillings, crowns, and implants."},
        ],
        "lawyer": [
            {"name": "Consultations", "description": "Understand your options and next steps."},
            {"name": "Representation", "description": "Negotiations and litigation when needed."},
            {"name": "Documents", "description": "Contracts, filings, and reviews."},
        ],
        "restaurant": [
            {"name": "Dine‑In", "description": "Comfortable seating and friendly service."},
            {"name": "Takeout", "description": "Order ahead for quick pickup."},
            {"name": "Catering", "description": "Custom menus for events and offices."},
        ],
    }

    for known, items in catalog.items():
        if known in key:
            return items

    # Generic fallback
    return [
        {"name": "Consultation", "description": "Talk with our team about your needs."},
        {"name": "Primary Service", "description": "Reliable, on‑time work by experienced pros."},
        {"name": "Follow‑Up", "description": "Support and maintenance after the job."},
    ]


def default_hours() -> List[Dict[str, Any]]:
    return [
        {"days": "Mon–Fri", "open": "8:00 AM", "close": "6:00 PM"},
        {"days": "Saturday", "open": "9:00 AM", "close": "1:00 PM"},
        {"days": "Sunday", "closed": True},
    ]


def build_tagline(industry: str, city: str) -> str:
    clean_industry = (industry or "Services").strip()
    clean_city = (city or "your area").strip()
    # Keep succinct for hero and metadata
    return f"Trusted {clean_industry} in {clean_city}"


def build_cta_text(industry: str) -> str:
    # Generic, effective CTA across local services
    return "Call Now"


def build_map_embed_url(address: Optional[str]) -> str:
    if not address:
        return ""
    # Use Google Maps embed format that properly centers on the address
    from urllib.parse import quote_plus
    
    encoded_address = quote_plus(address)
    return f"https://maps.google.com/maps?width=100%25&height=600&hl=en&q={encoded_address}&t=&z=14&ie=UTF8&iwloc=B&output=embed"


def init_gemini_client() -> Optional[GeminiClient]:
    """Initialize Gemini client - it loads keys from config automatically."""
    try:
        gemini_keys = []
        for i in range(1, 10):
            try:
                key = getattr(config, f"GEMINI_API_KEY_{i}")
                if key:
                    gemini_keys.append(key)
            except AttributeError:
                break
        
        if gemini_keys:
            return GeminiClient(api_keys=gemini_keys)
        else:
            print("⚠️ No Gemini API keys found in config.py")
            return None
    except Exception as e:
        print(f"⚠️ Failed to initialize Gemini client: {e}")
        return None


async def generate_with_llm(
    gemini_client: GeminiClient,
    company_name: str,
    location_str: str,
    industry: str,
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """Use LLM to generate quality content from search results."""
    
    # Prepare context from search results
    context_parts = []
    
    # Add business data if available
    business = data.get("business")
    if business:
        context_parts.append(f"Business Name: {business.name}")
        if business.address:
            context_parts.append(f"Address: {business.address}")
        if business.phone:
            context_parts.append(f"Phone: {business.phone}")
        if business.website:
            context_parts.append(f"Website: {business.website}")
        if business.rating:
            context_parts.append(f"Rating: {business.rating}/5 ({business.review_count or 0} reviews)")
        if business.category:
            context_parts.append(f"Category: {business.category}")
    
    # Add organic search results
    organic_results = data.get("organic_results", [])
    if organic_results:
        context_parts.append(f"\nSearch Results (top {len(organic_results)}):")
        for i, result in enumerate(organic_results[:10]):  # Limit for context length
            context_parts.append(f"{i+1}. {result.title}")
            context_parts.append(f"   URL: {result.url}")
            context_parts.append(f"   Snippet: {result.snippet[:200]}...")
    
    # Add reviews summary if available
    reviews_result = data.get("reviews_result")
    if reviews_result and reviews_result.reviews_summary:
        context_parts.append(f"\nGoogle Reviews Summary:")
        context_parts.append(reviews_result.reviews_summary)
    
    context = "\n".join(context_parts)
    
    # Generate tagline
    tagline_prompt = f"""Based on the following search results for "{company_name}" in {location_str}, create a compelling, professional tagline for their website. The tagline should be 8-12 words and highlight their key value proposition.

Business Type: {industry}
Location: {location_str}

Search Results:
{context[:4000]}

Generate ONLY the tagline text, nothing else."""

    tagline = await asyncio.to_thread(gemini_client.ask, tagline_prompt)
    
    # Generate about section
    about_prompt = f"""Based on the following search results for "{company_name}", write a professional 2-3 sentence "About" section for their website. Focus on their expertise, service area, and what makes them stand out.

Business Type: {industry}
Location: {location_str}

Search Results:
{context[:6000]}

Write ONLY the about text, no headers or extra formatting."""

    about = await asyncio.to_thread(gemini_client.ask, about_prompt)
    
    # Generate services based on search results
    services_prompt = f"""Based on the following search results for "{company_name}", identify 3-4 specific services they offer. For each service, provide a name and a brief 1-2 sentence description.

Business Type: {industry}
Location: {location_str}

Search Results:
{context[:6000]}

Return ONLY a JSON array in this format:
[
  {{"name": "Service Name", "description": "Brief description of service."}},
  {{"name": "Service Name", "description": "Brief description of service."}}
]"""

    services_response = await asyncio.to_thread(gemini_client.ask, services_prompt)
    
    # Parse services JSON
    services = []
    try:
        # Extract JSON from response if it contains extra text
        import re
        json_match = re.search(r'\[.*\]', services_response, re.DOTALL)
        if json_match:
            services = json.loads(json_match.group())
        else:
            services = json.loads(services_response)
    except:
        # Fallback to industry defaults if LLM parsing fails
        services = industry_services(industry)
    
    # Generate CTA text based on business type
    cta_prompt = f"""Based on the following business information, create a compelling call-to-action button text (2-4 words) for their website. Make it action-oriented and relevant to their industry.

Business: {company_name}
Industry: {industry}
Location: {location_str}

Examples: "Call Now", "Get Quote", "Book Today", "Schedule Service"

Return ONLY the CTA text, nothing else."""

    cta_text = await asyncio.to_thread(gemini_client.ask, cta_prompt)
    
    return {
        "tagline": tagline.strip().strip('"'),
        "about": about.strip(),
        "services": services,
        "cta_text": cta_text.strip().strip('"'),
    }


async def gather_comprehensive_data(
    name: str, location_str: str, industry: str
) -> Dict[str, Any]:
    """
    Gather comprehensive business data from multiple SERP sources and organic results.
    """
    searcher = GoogleSearcher()
    
    # Get local business results
    local_results = await searcher.search_local_businesses(name, location_str, max_results=10)
    selected_business = choose_best_business(local_results, name)
    
    # Get organic search results for the business 
    organic_query = f'"{name}" {location_str} {industry}'
    organic_results = await searcher.search_organic_results(organic_query, location_str, num_links=15)
    
    # Try to get reviews if possible
    reviews_result = None
    try:
        fetcher = GoogleReviewFetcher()
        reviews_result = await fetcher.fetch_reviews(
            business_name=name, business_location=location_str, sort="newestFirst", max_results=10
        )
    except Exception:
        pass
    
    return {
        "business": selected_business,
        "organic_results": organic_results,
        "reviews_result": reviews_result,
        "search_location": location_str,
    }


async def generate_site_json(
    company_name: str,
    city: str,
    region: str,
    country: str,
    industry: str,
) -> Dict[str, Any]:
    location_str = build_location_string(city, region, country)
    
    print(f"🔍 Gathering comprehensive data for {company_name}...")
    data = await gather_comprehensive_data(company_name, location_str, industry)
    
    # Initialize Gemini client for content generation
    gemini_client = init_gemini_client()
    
    # Extract basic business info
    business = data.get("business")
    reviews_result = data.get("reviews_result")
    
    # Use LLM to generate quality content if available
    if gemini_client:
        print("🤖 Generating content with LLM...")
        llm_content = await generate_with_llm(
            gemini_client, company_name, location_str, industry, data
        )
        tagline = llm_content["tagline"]
        about = llm_content["about"]
        services = llm_content["services"]
        cta_text = llm_content["cta_text"]
    else:
        print("⚠️ No LLM available, using fallback content...")
        # Fallback to basic generation
        service_area = build_location_string(city, region, "") or city or region or country
        tagline = build_tagline(industry, city)
        cta_text = build_cta_text(industry)
        
        if reviews_result and reviews_result.reviews_summary:
            about = reviews_result.reviews_summary
        else:
            typed = (business and business.category) or industry or "Local Services"
            about = f"{company_name} provides {typed.lower()} across {service_area}. We focus on dependable service, clear communication, and quality work."
        
        services = industry_services(industry)
    
    # Extract contact info from business data
    phone = ""
    address = ""
    if business:
        phone = sanitize_text(business.phone) or ""
        address = sanitize_text(business.address) or ""
    elif reviews_result:
        phone = sanitize_text(reviews_result.business_phone) or ""
        address = sanitize_text(reviews_result.business_address) or ""
    
    service_area = build_location_string(city, region, "") or city or region or country
    
    site: Dict[str, Any] = {
        "businessName": company_name,
        "phone": phone,
        "heroImageUrl": "/hero.jpg",  # ships with template
        "tagline": tagline,
        "ctaText": cta_text,
        "serviceArea": service_area,
        "about": about,
        "contactEmail": "",  # Not available from SERP
        "address": address,
        "mapEmbedUrl": build_map_embed_url(address),
        "logoUrl": "",  # Not available from SERP
        "iconUrl": "",  # Not available from SERP
        "services": services,
        "testimonials": [],  # Could extract from reviews in future
        "hours": default_hours(),  # Could parse from business hours if available
    }

    return site


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate site.json for a business using Google SERP.")
    parser.add_argument("--name", required=True, help="Company name")
    parser.add_argument("--city", required=True, help="City")
    parser.add_argument("--region", required=False, default="", help="State/Province/Region")
    parser.add_argument("--country", required=False, default="", help="Country")
    parser.add_argument("--industry", required=True, help="Industry (e.g., Plumber, HVAC, Dentist)")
    parser.add_argument("--output", "-o", required=False, default="", help="Write JSON to file path; if omitted, prints to stdout")

    args = parser.parse_args()

    site_json: Dict[str, Any] = asyncio.run(
        generate_site_json(args.name, args.city, args.region, args.country, args.industry)
    )

    content = json.dumps(site_json, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {args.output}")
    else:
        print(content)


if __name__ == "__main__":
    main()


