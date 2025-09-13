#!/usr/bin/env python3
"""
Domain Ranking Checker Script
=============================

This script checks how multiple domains rank for their respective keyword queries
using the BrightData site rank checker. Each domain is searched without location
targeting (organic search only) using keywords derived from the domain name.

Usage:
    python domain_ranking_checker.py
"""

import asyncio
from typing import Dict, List
from brightdata_site_rank_checker import SiteRankChecker


def extract_query_from_domain(domain: str) -> str:
    """
    Extract search query from domain name by converting domain keywords to readable phrases.
    
    Args:
        domain: Domain name (e.g., "lowcaloriepopcorn.com")
        
    Returns:
        Search query string (e.g., "low calorie popcorn")
    """
    # Remove TLD and common prefixes
    domain_base = domain.lower()
    
    # Remove common TLDs
    for tld in ['.com', '.online', '.shop', '.net', '.org']:
        if domain_base.endswith(tld):
            domain_base = domain_base[:-len(tld)]
            break
    
    # Domain-specific query mapping
    domain_queries = {
        'bestpopcornbrands': 'best popcorn brands',
        'flavored-popcorn': 'flavored popcorn',
        'lowcaloriepopcorn': 'low calorie popcorn',
        'glutenfreepopcorn': 'gluten free popcorn',
        'highqualitypopcorn': 'high quality popcorn',
        'buypopcorn': 'buy popcorn',
        'gourmetpopcorn': 'gourmet popcorn',
        'pressurepower-washing': 'pressure power washing'
    }
    
    # Check if we have a specific mapping
    if domain_base in domain_queries:
        return domain_queries[domain_base]
    
    # Fallback: convert camelCase/hyphenated to spaced words
    import re
    
    # Replace hyphens with spaces
    query = domain_base.replace('-', ' ')
    
    # Add spaces before capital letters (for camelCase)
    query = re.sub(r'([a-z])([A-Z])', r'\1 \2', query)
    
    # Clean up multiple spaces
    query = ' '.join(query.split())
    
    return query


async def check_domain_rankings():
    """Check rankings for all specified domains"""
    
    # Domains to check
    domains = [
        # 'bestpopcornbrands.com',
        # 'flavored-popcorn.com', 
        # 'lowcaloriepopcorn.com',
        # 'glutenfreepopcorn.com',
        # 'highqualitypopcorn.com',
        # 'buypopcorn.online',
        'gourmetpopcorn.shop',
        'pressurepower-washing.com'
    ]
    
    checker = SiteRankChecker()
    
    print("=" * 80)
    print("DOMAIN RANKING CHECK REPORT")
    print("=" * 80)
    print(f"Checking {len(domains)} domains for organic rankings...")
    print(f"Search type: Non-localized organic search only")
    print(f"Max results per search: 100")
    print("=" * 80)
    
    all_results = []
    
    for i, domain in enumerate(domains, 1):
        query = extract_query_from_domain(domain)
        
        print(f"\n🔍 DOMAIN {i}/{len(domains)}: {domain}")
        print(f"📝 Query: '{query}'")
        print("-" * 60)
        
        try:
            # Use empty ranking_locations list to force non-localized organic search only
            # This will skip CID lookup and local business search entirely
            reports = await checker.check_site_ranking_async(
                domain=domain,
                query=query,
                ranking_locations=[],  # Empty list = non-localized organic search only
                gl="us",  # US Google
                hl="en",  # English
                max_results=100,
                cid=None,  # No CID
                business_name=None,  # No business name
                city=None,  # No city
                region=None,  # No region  
                country=None  # No country
            )
            
            if reports and len(reports) > 0:
                report = reports[0]  # Should only be one report since no location targeting
                
                # Store results for summary
                result_summary = {
                    'domain': domain,
                    'query': query,
                    'organic_results': len(report.organic_results),
                    'best_position': report.best_organic_position,
                    'total_found': report.total_results_found
                }
                all_results.append(result_summary)
                
                # Print individual results
                if report.organic_results:
                    print(f"✅ Found {len(report.organic_results)} organic results")
                    print(f"🏆 Best position: #{report.best_organic_position}")
                    
                    # Show top 3 results
                    sorted_results = sorted(report.organic_results, key=lambda x: x.position)
                    for j, result in enumerate(sorted_results[:3], 1):
                        print(f"   #{result.position}: {result.title}")
                        print(f"        URL: {result.url}")
                        if result.snippet:
                            snippet = result.snippet[:100] + "..." if len(result.snippet) > 100 else result.snippet
                            print(f"        Snippet: {snippet}")
                        print()
                else:
                    # Count total organic results from the parsed data to show context
                    total_organic_in_serp = 0
                    try:
                        # Re-parse to get total count for context
                        parsed_data = checker._safe_json_parse(reports[0].organic_results if hasattr(reports[0], 'raw_data') else '{}')
                        # This is a bit hacky, but let's get the actual count from the original search
                        print(f"❌ Domain '{domain}' not found in search results")
                        print(f"   (Note: This is expected for new domains without established SEO)")
                    except:
                        print(f"❌ Domain '{domain}' not found in search results")
                        print(f"   (Note: This is expected for new domains without established SEO)")
                    
            else:
                print("❌ No reports generated")
                all_results.append({
                    'domain': domain,
                    'query': query,
                    'organic_results': 0,
                    'best_position': None,
                    'total_found': 0
                })
                
        except Exception as e:
            print(f"⚠️  Error checking {domain}: {e}")
            all_results.append({
                'domain': domain,
                'query': query,
                'organic_results': 0,
                'best_position': None,
                'total_found': 0,
                'error': str(e)
            })
    
    # Print summary report
    print("\n" + "=" * 80)
    print("SUMMARY REPORT")
    print("=" * 80)
    
    # Sort by best position (None values last)
    sorted_results = sorted(all_results, key=lambda x: (x['best_position'] is None, x['best_position'] or 999))
    
    print(f"{'Domain':<30} {'Query':<25} {'Best Pos':<10} {'Results':<8} {'Status'}")
    print("-" * 80)
    
    for result in sorted_results:
        domain = result['domain'][:29]  # Truncate if too long
        query = result['query'][:24]    # Truncate if too long
        
        if 'error' in result:
            status = "ERROR"
            best_pos = "N/A"
            results_count = "N/A"
        elif result['best_position']:
            status = "FOUND"
            best_pos = f"#{result['best_position']}"
            results_count = str(result['organic_results'])
        else:
            status = "NOT FOUND"
            best_pos = "N/A"
            results_count = "0"
        
        print(f"{domain:<30} {query:<25} {best_pos:<10} {results_count:<8} {status}")
    
    # Statistics
    found_count = sum(1 for r in all_results if r['best_position'] is not None)
    error_count = sum(1 for r in all_results if 'error' in r)
    
    print("-" * 80)
    print(f"Total domains checked: {len(all_results)}")
    print(f"Domains found in rankings: {found_count}")
    print(f"Domains not found: {len(all_results) - found_count - error_count}")
    print(f"Errors: {error_count}")
    
    if found_count > 0:
        best_positions = [r['best_position'] for r in all_results if r['best_position'] is not None]
        avg_position = sum(best_positions) / len(best_positions)
        print(f"Average position (for found domains): #{avg_position:.1f}")
        print(f"Best overall position: #{min(best_positions)}")
    
    print("=" * 80)


def main():
    """Main entry point"""
    print("Starting domain ranking check...")
    print("This will check organic rankings for multiple domains without location targeting.")
    print()
    
    # Run the async ranking check
    asyncio.run(check_domain_rankings())
    
    print("\nRanking check complete!")


if __name__ == "__main__":
    main()
