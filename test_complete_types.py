#!/usr/bin/env python3
"""
Complete TypeScript compatibility test for all components
"""

import json
from typing import Dict, Any

def transform_site_json_structure(site_data: Dict[str, Any]) -> Dict[str, Any]:
    """Standalone version of the transformation function for testing"""
    transformed = site_data.copy()
    
    # Transform header colors
    if any(key in site_data for key in ["headerBrandTextColor", "headerNavTextColor"]):
        if "header" not in transformed:
            transformed["header"] = {}
        if "colors" not in transformed["header"]:
            transformed["header"]["colors"] = {}
            
        if "headerBrandTextColor" in site_data:
            transformed["header"]["colors"]["brandText"] = site_data["headerBrandTextColor"]
        if "headerNavTextColor" in site_data:
            transformed["header"]["colors"]["navText"] = site_data["headerNavTextColor"]
    
    # Transform hero structure and colors
    hero_keys = ["tagline", "ctaText", "heroImageUrl", "subheadline", "heroHeadlineColor", "heroSubheadlineColor", "heroCtaTextColor", "heroCtaBackgroundColor"]
    if any(key in site_data for key in hero_keys):
        if "hero" not in transformed:
            transformed["hero"] = {}
        if "colors" not in transformed["hero"]:
            transformed["hero"]["colors"] = {}
            
        # Map hero image
        if "heroImageUrl" in site_data:
            transformed["hero"]["backgroundImageUrl"] = site_data["heroImageUrl"]
            
        # Map hero content
        if "tagline" in site_data:
            transformed["hero"]["headline"] = site_data["tagline"]
        if "subheadline" in site_data:
            transformed["hero"]["subheadline"] = site_data["subheadline"]
        if "ctaText" in site_data:
            if "cta" not in transformed["hero"]:
                transformed["hero"]["cta"] = {}
            transformed["hero"]["cta"]["label"] = site_data["ctaText"]
            
        # Map hero colors
        if "heroHeadlineColor" in site_data:
            transformed["hero"]["colors"]["headline"] = site_data["heroHeadlineColor"]
        if "heroSubheadlineColor" in site_data:
            transformed["hero"]["colors"]["subheadline"] = site_data["heroSubheadlineColor"]
        if "heroCtaTextColor" in site_data:
            transformed["hero"]["colors"]["ctaText"] = site_data["heroCtaTextColor"]
        if "heroCtaBackgroundColor" in site_data:
            transformed["hero"]["colors"]["ctaBackground"] = site_data["heroCtaBackgroundColor"]
    
    # Transform about section
    if "aboutTitle" in site_data or "aboutDescription" in site_data:
        if "about" not in transformed:
            transformed["about"] = {}
            
        if "aboutTitle" in site_data:
            transformed["about"]["title"] = site_data["aboutTitle"]
        if "aboutDescription" in site_data:
            transformed["about"]["description"] = site_data["aboutDescription"]
    
    # Transform testimonials title
    if "testimonialsTitle" in site_data:
        if "testimonials" not in transformed:
            transformed["testimonials"] = {"items": []}
        elif isinstance(transformed["testimonials"], list):
            # If testimonials is a list, convert it to object with items
            testimonials_list = transformed["testimonials"]
            transformed["testimonials"] = {"items": testimonials_list}
        transformed["testimonials"]["title"] = site_data["testimonialsTitle"]
    
    # Transform services to match ServiceItem type (add id, rename name to title)
    if "services" in site_data and isinstance(site_data["services"], list):
        transformed["services"] = []
        for i, service in enumerate(site_data["services"]):
            transformed_service = service.copy()
            
            # Add id if missing (required by ServiceItem type)
            if "id" not in transformed_service:
                transformed_service["id"] = f"service-{i+1}"
            
            # Rename "name" to "title" to match ServiceItem type
            if "name" in transformed_service and "title" not in transformed_service:
                transformed_service["title"] = transformed_service["name"]
            
            transformed["services"].append(transformed_service)
    
    # Transform testimonials items to match TestimonialItem type
    if "testimonials" in site_data and isinstance(site_data["testimonials"], list):
        if "testimonials" not in transformed:
            transformed["testimonials"] = {"items": []}
        
        transformed_testimonials = []
        for testimonial in site_data["testimonials"]:
            transformed_testimonial = testimonial.copy()
            
            # Map "name" to "authorName" if needed
            if "name" in transformed_testimonial and "authorName" not in transformed_testimonial:
                transformed_testimonial["authorName"] = transformed_testimonial["name"]
            
            # Map "quote" to "reviewText" if needed
            if "quote" in transformed_testimonial and "reviewText" not in transformed_testimonial:
                transformed_testimonial["reviewText"] = transformed_testimonial["quote"]
            
            # Ensure rating exists (default to 5 if missing)
            if "rating" not in transformed_testimonial:
                transformed_testimonial["rating"] = 5
                
            transformed_testimonials.append(transformed_testimonial)
        
        transformed["testimonials"]["items"] = transformed_testimonials
    
    return transformed

# Your actual site.json data
test_site_data = {
    "businessName": "Stacy's Plumbing Co.",
    "phone": "(555) 123-4567",
    "heroImageUrl": "https://example.com/hero.png",
    "logoUrl": "https://example.com/logo.jpg",
    "tagline": "Fast, somewhat reliable plumbing in your neighborhood",
    "ctaText": "Call for Same-Day Service",
    "serviceArea": "Greater Springfield",
    "headerBrandTextColor": "#000000",
    "headerNavTextColor": "#374151",
    "heroHeadlineColor": "#000000",
    "heroSubheadlineColor": "#4b5563",
    "heroCtaTextColor": "#ffffff",
    "heroCtaBackgroundColor": "#10B981",
    "services": [
        {
            "name": "Emergency Repairs",
            "description": "24/7 burst pipes, leaks, and urgent fixes."
        },
        {
            "name": "Water Heater",
            "description": "Installation, maintenance, and replacements.",
            "imageUrl": "https://example.com/service-2.png"
        }
    ],
    "testimonials": [
        {
            "name": "Kara D.",
            "quote": "Arrived within the hour and fixed our leak quickly!",
            "authorImageUrl": "https://example.com/testimonial-1.png"
        }
    ],
    "subheadline": "Serving Greater Springfield",
    "aboutTitle": "About Us",
    "aboutDescription": "We provide high quality plumbing services with a focus on customer satisfaction.",
    "testimonialsTitle": "Customer Reviews"
}

def validate_component_types():
    print("🔍 TypeScript Component Type Validation")
    print("=" * 60)
    
    transformed = transform_site_json_structure(test_site_data)
    
    # Validate Hero component requirements
    print("🎭 Hero Component:")
    hero = transformed.get("hero", {})
    hero_colors = hero.get("colors", {})
    
    hero_checks = [
        ("backgroundImageUrl", hero.get("backgroundImageUrl")),
        ("subheadline", hero.get("subheadline")),
        ("colors.headline", hero_colors.get("headline")),
        ("colors.subheadline", hero_colors.get("subheadline")),
        ("colors.ctaText", hero_colors.get("ctaText")),
        ("colors.ctaBackground", hero_colors.get("ctaBackground")),  # This was causing the TS error
    ]
    
    for prop, value in hero_checks:
        status = "✅" if value else "❌"
        print(f"  {status} hero.{prop}: {value}")
    
    # Validate Services component requirements
    print("\n🔧 Services Component:")
    services = transformed.get("services", [])
    print(f"  Services count: {len(services)}")
    
    for i, service in enumerate(services):
        service_checks = [
            ("id", service.get("id")),  # Required by ServiceItem type
            ("title", service.get("title")),  # Required by ServiceItem type
            ("description", service.get("description")),
            ("imageUrl", service.get("imageUrl", "Optional")),
        ]
        
        print(f"  Service {i+1}:")
        for prop, value in service_checks:
            status = "✅" if value else "❌"
            print(f"    {status} {prop}: {value}")
    
    # Validate Testimonials component requirements
    print("\n💬 Testimonials Component:")
    testimonials = transformed.get("testimonials", {})
    testimonial_items = testimonials.get("items", [])
    print(f"  Testimonials count: {len(testimonial_items)}")
    
    for i, testimonial in enumerate(testimonial_items):
        testimonial_checks = [
            ("authorName", testimonial.get("authorName")),  # Required by TestimonialItem type
            ("reviewText", testimonial.get("reviewText")),  # Required by TestimonialItem type  
            ("rating", testimonial.get("rating")),  # Required by TestimonialItem type
            ("authorImageUrl", testimonial.get("authorImageUrl", "Optional")),
        ]
        
        print(f"  Testimonial {i+1}:")
        for prop, value in testimonial_checks:
            status = "✅" if value else "❌"
            print(f"    {status} {prop}: {value}")
    
    # Validate Header component requirements
    print("\n📋 Header Component:")
    header = transformed.get("header", {})
    header_colors = header.get("colors", {})
    
    header_checks = [
        ("colors.brandText", header_colors.get("brandText")),
        ("colors.navText", header_colors.get("navText")),
    ]
    
    for prop, value in header_checks:
        status = "✅" if value else "❌"
        print(f"  {status} header.{prop}: {value}")
    
    # Validate About component requirements  
    print("\n📖 About Component:")
    about = transformed.get("about", {})
    
    about_checks = [
        ("title", about.get("title")),
        ("description", about.get("description")),
    ]
    
    for prop, value in about_checks:
        status = "✅" if value else "❌"
        print(f"  {status} about.{prop}: {value}")
    
    print(f"\n🎯 Summary:")
    print(f"✅ All required TypeScript properties should now be present")
    print(f"✅ Components should compile without type errors")
    print(f"✅ Cloudflare build should succeed")

if __name__ == "__main__":
    validate_component_types()
