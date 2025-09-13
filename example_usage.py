#!/usr/bin/env python3
"""
Example usage of the GBPResearcher class with the new get_business_data() method.

This demonstrates how to call the GBPResearcher from another class or module
to get the three key data types: HTML content, Maps data, and Reviews.
"""

import asyncio
from gbp_researcher import GBPResearcher, ReviewResult
from typing import Dict, List, Optional, Any


class BusinessDataCollector:
    """Example class showing how to use GBPResearcher from another class"""
    
    def __init__(self):
        self.researcher = GBPResearcher()
    
    async def collect_business_info(
        self, 
        business_name: str, 
        business_location: str
    ) -> Dict[str, Any]:
        """
        Collect business information and return it in a structured format.
        
        Args:
            business_name: Name of the business
            business_location: Location of the business
            
        Returns:
            Dictionary containing all collected business data
        """
        print(f"🏢 Collecting data for: {business_name} in {business_location}")
        
        # Use the new get_business_data method
        html_content, maps_data, reviews = await self.researcher.get_business_data(
            business_name=business_name,
            business_location=business_location,
            max_reviews=15,
            review_sort="qualityScore"
        )
        
        # Process and structure the results
        result = {
            "business_name": business_name,
            "business_location": business_location,
            "data_collected": {
                "html_available": html_content is not None,
                "html_length": len(html_content) if html_content else 0,
                "maps_data_available": maps_data is not None,
                "maps_data_keys": list(maps_data.keys()) if maps_data else [],
                "reviews_count": len(reviews),
                "reviews_data": [
                    {
                        "author": review.author_name,
                        "rating": review.rating,
                        "date": review.review_date,
                        "text_preview": review.review_text[:100] if review.review_text else None
                    }
                    for review in reviews[:5]  # First 5 reviews
                ]
            },
            "raw_data": {
                "html_content": html_content,
                "maps_data": maps_data,
                "reviews": reviews  # List of ReviewResult Pydantic models
            }
        }
        
        return result


async def main():
    """Example usage of the BusinessDataCollector"""
    collector = BusinessDataCollector()
    
    # Test with a business
    result = await collector.collect_business_info(
        business_name="Caccia's Home Services",
        business_location="San Mateo, CA"
    )
    
    print("\n📊 COLLECTION RESULTS:")
    print(f"Business: {result['business_name']}")
    print(f"HTML Available: {result['data_collected']['html_available']}")
    print(f"Maps Data Available: {result['data_collected']['maps_data_available']}")
    print(f"Reviews Count: {result['data_collected']['reviews_count']}")
    
    # Access the raw data types
    html_content: Optional[str] = result['raw_data']['html_content']
    maps_data: Optional[Dict[str, Any]] = result['raw_data']['maps_data']
    reviews: List[ReviewResult] = result['raw_data']['reviews']
    
    print(f"\n✅ Type validation:")
    print(f"HTML: {type(html_content)}")
    print(f"Maps Data: {type(maps_data)}")
    print(f"Reviews: {type(reviews)} with {len(reviews)} items")
    
    if reviews:
        print(f"First review type: {type(reviews[0])}")
        print(f"First review author: {reviews[0].author_name}")


if __name__ == "__main__":
    asyncio.run(main())
