#!/usr/bin/env python3
"""
Standalone test for site.json structure transformation
"""

import json
from typing import Dict, Any

def transform_site_json_structure(site_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform flat site.json structure to nested component structure.
    
    Converts editor-style flat structure (heroCtaBackgroundColor) 
    to component-expected nested structure (hero.colors.ctaBackground).
    """
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
    
    # Transform testimonials
    if "testimonialsTitle" in site_data:
        if "testimonials" not in transformed:
            transformed["testimonials"] = {"items": []}
        transformed["testimonials"]["title"] = site_data["testimonialsTitle"]
    
    print(f"✅ Transformed site.json structure - added nested objects for components")
    return transformed

# Your actual site.json structure
test_site_data = {
    "businessName": "Stacy's Plumbing Co.",
    "phone": "(555) 123-4567",
    "heroImageUrl": "https://eejrhvuxthdbmyyiubnr.supabase.co/storage/v1/object/public/vm-sites/public/d6adff42-ebc6-4aa7-8be7-da8f3e8efaa1/youguard.love/hero.png",
    "logoUrl": "https://eejrhvuxthdbmyyiubnr.supabase.co/storage/v1/object/public/vm-sites/public/d6adff42-ebc6-4aa7-8be7-da8f3e8efaa1/youguard.love/logo.jpg",
    "heroCtaBackgroundColor": "#10B981",
    "heroHeadlineColor": "#000000", 
    "heroSubheadlineColor": "#4b5563",
    "heroCtaTextColor": "#ffffff",
    "subheadline": "Serving Greater Springfield",
    "headerBrandTextColor": "#000000",
    "headerNavTextColor": "#374151"
}

def main():
    print("🧪 Testing Site.json Structure Transformation")
    print("=" * 60)
    
    print("📋 Original flat structure:")
    for key, value in test_site_data.items():
        if any(prefix in key for prefix in ['header', 'hero']):
            print(f"  {key}: {value}")
    
    print(f"\n🔄 Applying transformation...")
    transformed_data = transform_site_json_structure(test_site_data)
    
    print(f"\n📋 Transformed nested structure:")
    
    # Show hero transformation  
    if "hero" in transformed_data:
        print(f"✅ Hero structure:")
        print(json.dumps(transformed_data['hero'], indent=4))
    
    # Show header transformation
    if "header" in transformed_data:
        print(f"✅ Header structure:")
        print(json.dumps(transformed_data['header'], indent=4))
    
    print(f"\n🎯 TypeScript Hero component compatibility:")
    
    hero = transformed_data.get("hero", {})
    hero_colors = hero.get("colors", {})
    
    # Check the specific property that was causing the error
    cta_background = hero_colors.get("ctaBackground")
    print(f"✅ hero.colors.ctaBackground: {cta_background}")
    print(f"✅ This should fix the TypeScript error: 'Property ctaBackground does not exist'")
    
    return transformed_data

if __name__ == "__main__":
    result = main()
