#!/usr/bin/env python3
"""
Enhanced Domain Ranking Checker Script
======================================

This script checks how multiple domains rank for their respective keyword queries
using the BrightData site rank checker. It provides detailed insights about why
domains might not be ranking and what to expect for new domains.

Usage:
    python enhanced_domain_ranking_checker.py
"""

import asyncio
import json
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


def get_total_organic_results(checker, text_content):
    """Extract total organic results from BrightData response"""
    try:
        parsed_data = checker._safe_json_parse(text_content)
        if parsed_data and 'organic' in parsed_data:
            return len(parsed_data['organic'])
    except:
        pass
    return 0


async def check_domain_rankings():
    """Check rankings for all specified domains with enhanced reporting"""
    
    # Domains to check
    domains = [
        'bestpopcornbrands.com',
        'flavored-popcorn.com', 
        'lowcaloriepopcorn.com',
        'glutenfreepopcorn.com',
        'highqualitypopcorn.com',
        'buypopcorn.online',
        'gourmetpopcorn.shop',
        'pressurepower-washing.com'
    ]
    
    checker = SiteRankChecker()
    
    print("=" * 80)
    print("ENHANCED DOMAIN RANKING CHECK REPORT")
    print("=" * 80)
    print(f"Checking {len(domains)} domains for organic rankings...")
    print(f"Search type: Non-localized organic search only")
    print(f"Max results requested per search: 100")
    print("\n📝 IMPORTANT NOTES:")
    print("• These domains were registered on Oct 24, 2025 (very recent)")
    print("• New domains typically need weeks/months to rank for competitive keywords")
    print("• Google needs time to crawl, index, and evaluate new sites")
    print("• Ranking depends on content quality, SEO, and backlinks")
    print("=" * 80)
    
    all_results = []
    total_organic_checked = 0
    
    for i, domain in enumerate(domains, 1):
        query = extract_query_from_domain(domain)
        
        print(f"\n🔍 DOMAIN {i}/{len(domains)}: {domain}")
        print(f"📝 Query: '{query}'")
        print("-" * 60)
        
        try:
            # Use empty ranking_locations list to force non-localized organic search only
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
                
                # Try to get the total organic results that were actually checked
                organic_results_checked = 0
                try:
                    # Access the raw data to count total organic results
                    url = f"https://www.google.com/search?q={query.replace(' ', '+')}&gl=us&hl=en&num=100&brd_json=1"
                    raw_results = checker.client.scrape(url)
                    parsed_json = checker.client.parse_content(raw_results)
                    if 'text' in parsed_json:
                        organic_results_checked = get_total_organic_results(checker, parsed_json['text'])
                except:
                    organic_results_checked = 0
                
                total_organic_checked += organic_results_checked
                
                # Store results for summary
                result_summary = {
                    'domain': domain,
                    'query': query,
                    'organic_results': len(report.organic_results),
                    'organic_checked': organic_results_checked,
                    'best_position': report.best_organic_position,
                    'total_found': report.total_results_found
                }
                all_results.append(result_summary)
                
                # Print individual results
                if report.organic_results:
                    print(f"✅ Found {len(report.organic_results)} matches for '{domain}'")
                    print(f"🏆 Best position: #{report.best_organic_position}")
                    print(f"📊 Total organic results checked: {organic_results_checked}")
                    
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
                    print(f"❌ Domain '{domain}' not found in search results")
                    print(f"📊 Total organic results checked: {organic_results_checked}")
                    print(f"💡 This is normal for new domains - here's why:")
                    print(f"   • Domain registered Oct 24, 2025 (very recent)")
                    print(f"   • Competing against established sites for '{query}'")
                    print(f"   • Needs content, SEO optimization, and time to rank")
                    print(f"   • Google may not have fully indexed the site yet")
                    
            else:
                print("❌ No reports generated")
                all_results.append({
                    'domain': domain,
                    'query': query,
                    'organic_results': 0,
                    'organic_checked': 0,
                    'best_position': None,
                    'total_found': 0
                })
                
        except Exception as e:
            print(f"⚠️  Error checking {domain}: {e}")
            all_results.append({
                'domain': domain,
                'query': query,
                'organic_results': 0,
                'organic_checked': 0,
                'best_position': None,
                'total_found': 0,
                'error': str(e)
            })
    
    # Print comprehensive summary report
    print("\n" + "=" * 80)
    print("COMPREHENSIVE SUMMARY REPORT")
    print("=" * 80)
    
    # Sort by best position (None values last)
    sorted_results = sorted(all_results, key=lambda x: (x['best_position'] is None, x['best_position'] or 999))
    
    print(f"{'Domain':<25} {'Query':<20} {'Checked':<8} {'Found':<6} {'Best Pos':<10} {'Status'}")
    print("-" * 80)
    
    for result in sorted_results:
        domain = result['domain'][:24]  # Truncate if too long
        query = result['query'][:19]    # Truncate if too long
        checked = str(result.get('organic_checked', 0))
        
        if 'error' in result:
            status = "ERROR"
            best_pos = "N/A"
            found = "N/A"
        elif result['best_position']:
            status = "FOUND"
            best_pos = f"#{result['best_position']}"
            found = str(result['organic_results'])
        else:
            status = "NOT FOUND"
            best_pos = "N/A"
            found = "0"
        
        print(f"{domain:<25} {query:<20} {checked:<8} {found:<6} {best_pos:<10} {status}")
    
    # Statistics
    found_count = sum(1 for r in all_results if r['best_position'] is not None)
    error_count = sum(1 for r in all_results if 'error' in r)
    total_checked = sum(r.get('organic_checked', 0) for r in all_results)
    
    print("-" * 80)
    print(f"STATISTICS:")
    print(f"• Total domains analyzed: {len(all_results)}")
    print(f"• Total organic results checked: {total_checked}")
    print(f"• Average results per query: {total_checked/len(all_results) if all_results else 0:.1f}")
    print(f"• Domains found ranking: {found_count}")
    print(f"• Domains not found: {len(all_results) - found_count - error_count}")
    print(f"• Errors encountered: {error_count}")
    
    if found_count > 0:
        best_positions = [r['best_position'] for r in all_results if r['best_position'] is not None]
        avg_position = sum(best_positions) / len(best_positions)
        print(f"• Average position (for found domains): #{avg_position:.1f}")
        print(f"• Best overall position: #{min(best_positions)}")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS FOR NEW DOMAINS:")
    print("=" * 80)
    print("🎯 SHORT-TERM (1-4 weeks):")
    print("   • Add quality, relevant content to each domain")
    print("   • Implement basic SEO (title tags, meta descriptions, headers)")
    print("   • Submit sitemaps to Google Search Console")
    print("   • Ensure sites are mobile-friendly and fast-loading")
    
    print("\n📈 MEDIUM-TERM (1-6 months):")
    print("   • Build high-quality backlinks from relevant sites")
    print("   • Create comprehensive content around target keywords")
    print("   • Optimize for long-tail keyword variations")
    print("   • Monitor Google Search Console for indexing issues")
    
    print("\n🏆 LONG-TERM (6+ months):")
    print("   • Focus on user experience and engagement metrics")
    print("   • Build domain authority through consistent content")
    print("   • Consider local SEO if applicable")
    print("   • Track ranking improvements and adjust strategy")
    
    print("\n💡 IMMEDIATE ACTIONS:")
    print("   • Verify domains are indexed: search 'site:yourdomain.com' on Google")
    print("   • Check if domains resolve properly and have content")
    print("   • Set up Google Analytics and Search Console")
    print("   • Consider less competitive, long-tail keywords initially")
    
    print("=" * 80)


def main():
    """Main entry point"""
    print("Starting enhanced domain ranking analysis...")
    print("This analysis will provide insights into why new domains may not rank immediately.")
    print()
    
    # Run the async ranking check
    asyncio.run(check_domain_rankings())
    
    print("\nAnalysis complete! Use the recommendations above to improve rankings over time.")


if __name__ == "__main__":
    main()
