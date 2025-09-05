#!/usr/bin/env python3
"""
Test script for site.json sanitization functionality
"""

import json
from site_sanitizer import sanitize_site_json, preview_sanitization

# Test data with problematic characters
test_site_data = {
    "businessName": "Joe's Plumbing & Repair",
    "tagline": "We're the best! \"Professional service\" guaranteed.",
    "about": "Don't worry about your plumbing issues. We'll fix them quickly!",
    "services": [
        {
            "name": "Emergency Repairs",
            "description": "24/7 emergency service - we're always here when you need us!"
        },
        {
            "name": "Pipe Installation", 
            "description": "\"Quality work\" that lasts. We won't let you down."
        }
    ],
    "testimonials": {
        "items": [
            {
                "authorName": "Sarah O'Connor",
                "reviewText": "They did amazing work! I couldn't be happier with the results.",
                "rating": 5
            },
            {
                "authorName": "Mike & Jane Smith",
                "reviewText": "\"Excellent service\" - they really know what they're doing!"
            }
        ]
    },
    "contact": {
        "address": "123 Main St, Springfield, IL",
        "hours": [
            {"days": "Mon–Fri", "open": "9:00 AM", "close": "5:00 PM"}
        ]
    }
}

def test_sanitization():
    print("🧪 Testing Site.json Sanitization")
    print("=" * 60)
    
    print("\n📋 Original Data:")
    print(json.dumps(test_site_data, indent=2))
    
    print("\n🔍 Preview of Changes:")
    preview_sanitization(test_site_data)
    
    print("\n🧹 Applying Sanitization:")
    sanitized_data = sanitize_site_json(test_site_data)
    
    print("\n📋 Sanitized Data:")
    print(json.dumps(sanitized_data, indent=2))
    
    print("\n✅ Test completed!")
    print("\nKey changes made:")
    print("- Apostrophes (') → left as-is (React handles them fine)")
    print("- Double quotes (\") → &ldquo; / &rdquo; / &quot;")
    print("- Ampersands (&) → left as-is (React handles them fine)")
    print("- Less than (<) → &lt;")
    print("- Greater than (>) → &gt;")

if __name__ == "__main__":
    test_sanitization()
