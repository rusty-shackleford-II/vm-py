#!/usr/bin/env python3
"""
Test script for site.json structure transformation
"""

import json

# Import the transformation function
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app import transform_site_json_structure

# Your actual site.json structure
test_site_data = {
    "businessName": "Stacy's Plumbing Co.",
    "phone": "(555) 123-4567",
    "heroImageUrl": "https://eejrhvuxthdbmyyiubnr.supabase.co/storage/v1/object/public/vm-sites/public/d6adff42-ebc6-4aa7-8be7-da8f3e8efaa1/youguard.love/hero.png",
    "logoUrl": "https://eejrhvuxthdbmyyiubnr.supabase.co/storage/v1/object/public/vm-sites/public/d6adff42-ebc6-4aa7-8be7-da8f3e8efaa1/youguard.love/logo.jpg",
    "iconUrl": "",
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
            "imageUrl": "https://eejrhvuxthdbmyyiubnr.supabase.co/storage/v1/object/public/vm-sites/public/d6adff42-ebc6-4aa7-8be7-da8f3e8efaa1/youguard.love/service-2.png"
        }
    ],
    "testimonials": [
        {
            "name": "Kara D.",
            "quote": "Arrived within the hour and fixed our leak quickly!",
            "authorImageUrl": "https://eejrhvuxthdbmyyiubnr.supabase.co/storage/v1/object/public/vm-sites/public/d6adff42-ebc6-4aa7-8be7-da8f3e8efaa1/youguard.love/testimonial-1.png"
        }
    ],
    "subheadline": "Serving Greater Springfield",
    "aboutTitle": "About Us",
    "aboutDescription": "We provide high quality plumbing services with a focus on customer satisfaction.",
    "testimonialsTitle": "Customer Reviews",
    "emergencyBenefitsTitle": "Benefits of Our Emergency Plumbing Service",
    "emergencyBenefit1Title": "24/7 availability",
    "emergencyBenefit1Description": "Emergency service whenever you need it most",
    "emergencyBenefit2Title": "Rapid response",
    "emergencyBenefit2Description": "Quick arrival times to minimize damage",
    "emergencyBenefit3Title": "Expert technicians",
    "emergencyBenefit3Description": "Licensed professionals with years of experience"
}

def test_structure_transformation():
    print("🧪 Testing Site.json Structure Transformation")
    print("=" * 60)
    
    print("📋 Original flat structure:")
    print(json.dumps(test_site_data, indent=2)[:500] + "...")
    
    print(f"\n🔍 Key flat properties found:")
    flat_keys = [k for k in test_site_data.keys() if any(prefix in k for prefix in ['header', 'hero', 'about', 'testimonials'])]
    for key in flat_keys:
        print(f"  - {key}: {test_site_data[key]}")
    
    print(f"\n🔄 Applying transformation...")
    transformed_data = transform_site_json_structure(test_site_data)
    
    print(f"\n📋 Transformed nested structure:")
    
    # Show header transformation
    if "header" in transformed_data:
        print(f"✅ Header colors: {transformed_data['header']}")
    
    # Show hero transformation  
    if "hero" in transformed_data:
        print(f"✅ Hero structure: {json.dumps(transformed_data['hero'], indent=2)}")
    
    # Show about transformation
    if "about" in transformed_data:
        print(f"✅ About structure: {transformed_data['about']}")
    
    # Show testimonials transformation
    if "testimonials" in transformed_data:
        print(f"✅ Testimonials structure: {transformed_data['testimonials']}")
    
    # Show emergency benefits transformation
    if "emergencyBenefits" in transformed_data:
        print(f"✅ Emergency Benefits structure: {transformed_data['emergencyBenefits']}")
        benefits = transformed_data['emergencyBenefits'].get('items', [])
        print(f"   - Title: {transformed_data['emergencyBenefits'].get('title')}")
        print(f"   - Items count: {len(benefits)}")
        for i, benefit in enumerate(benefits[:3]):  # Show first 3 benefits
            print(f"   - Benefit {i+1}: {benefit.get('title')} - {benefit.get('description')}")
    
    print(f"\n🎯 TypeScript compatibility check:")
    
    # Check if the Hero component's expected properties are present
    hero = transformed_data.get("hero", {})
    hero_colors = hero.get("colors", {})
    
    required_hero_props = ["backgroundImageUrl", "colors"]
    required_color_props = ["headline", "subheadline", "ctaText", "ctaBackground"]
    
    print(f"Hero properties:")
    for prop in required_hero_props:
        status = "✅" if prop in hero else "❌"
        print(f"  {status} {prop}: {hero.get(prop, 'MISSING')}")
    
    print(f"Hero color properties:")
    for prop in required_color_props:
        status = "✅" if prop in hero_colors else "❌"
        print(f"  {status} colors.{prop}: {hero_colors.get(prop, 'MISSING')}")
    
    print(f"\n🚀 Result: The transformed structure should fix the TypeScript error!")
    
    return transformed_data

if __name__ == "__main__":
    result = test_structure_transformation()
    
    print(f"\n📄 Full transformed site.json:")
    print(json.dumps(result, indent=2))
