# Research Endpoint Guide

The research endpoint provides AI-powered business research and site.json generation for any template. It automatically finds Google Business information, scrapes reviews, and uses Gemini AI to create a customized website configuration.

## Overview

The `/research` endpoint takes basic business information and generates a complete `site.json` file by:

1. **Template Loading**: Loads the schema and example from the specified template directory
2. **Business Search**: Uses Google Search and Google Maps to find business information
3. **Data Scraping**: Extracts business details, reviews, ratings, and contact information
4. **AI Generation**: Uses Gemini AI to create a customized site.json based on real business data

## Endpoint Details

**URL**: `POST /research`

**Request Body**:
```json
{
  "template_name": "local-business",
  "business_name": "JJ Heating & Cooling", 
  "business_location": "San Mateo, CA",
  "business_description": "HVAC contractor providing heating and cooling services"
}
```

**Response**:
```json
{
  "success": true,
  "site_json": { /* Complete customized site.json */ },
  "business_info": { /* Raw business research data */ },
  "template_used": "local-business",
  "error": null
}
```

## Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `template_name` | string | ✅ | Template to use (e.g., "local-business") |
| `business_name` | string | ✅ | Name of the business to research |
| `business_location` | string | ❌ | Location/city/address of the business |
| `business_description` | string | ❌ | Additional context about the business |

## Response Fields

### Success Response

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Always `true` for successful requests |
| `site_json` | object | Complete customized site.json for the template |
| `business_info` | object | Raw research data including Google Business info, reviews, etc. |
| `template_used` | string | The template that was used |
| `error` | null | Always `null` for successful requests |

### Error Response

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Always `false` for failed requests |
| `site_json` | null | Always `null` for failed requests |
| `business_info` | null | Always `null` for failed requests |
| `template_used` | string | The template that was attempted |
| `error` | string | Error message describing what went wrong |

## Business Research Process

The endpoint performs comprehensive business research in the following steps:

### 1. Template Loading
- Loads `schema.json` and example `site.json` from the template directory
- Validates that the template exists and has the required files
- Uses the schema to understand the expected structure

### 2. Google Business Search
- Searches Google for local businesses matching the name and location
- Uses enhanced search with BrightData proxy for reliable results
- Extracts business information including:
  - Business name, address, phone number
  - Rating and review count
  - Website URL
  - Business category/type
  - Operating hours

### 3. Google Maps Integration
- Searches Google Maps for the specific business
- Uses AI to match the correct business from search results
- Extracts additional details like:
  - Feature ID (FID) for review fetching
  - Precise location data
  - Additional business attributes

### 4. Review Scraping
- Fetches up to 20 recent Google reviews using the business FID
- Extracts review text, ratings, author names, and dates
- Provides rich context for AI-generated testimonials

### 5. AI Site Generation
- Uses Gemini 2.0 Flash model with multiple API keys for reliability
- Combines all research data into a comprehensive prompt
- Generates a complete site.json that:
  - Uses the exact business name from research
  - Includes accurate contact information
  - Creates realistic services based on business type
  - Generates compelling testimonials inspired by real reviews
  - Matches the template structure perfectly

## Template System

The endpoint is designed to work with any template structure:

### Template Directory Structure
```
vm-web/templates/
└── local-business/
    └── data/
        ├── schema.json    # JSON schema defining the structure
        └── site.json      # Example site.json with placeholder data
```

### Adding New Templates

To add support for a new template:

1. **Create Template Directory**:
   ```
   vm-web/templates/your-template-name/
   ```

2. **Add Schema File**:
   ```json
   // vm-web/templates/your-template-name/data/schema.json
   {
     "$schema": "https://json-schema.org/draft/2020-12/schema",
     "title": "Your Template Schema",
     "type": "object",
     "properties": {
       // Define your template structure
     }
   }
   ```

3. **Add Example Site.json**:
   ```json
   // vm-web/templates/your-template-name/data/site.json
   {
     // Example data matching your schema
   }
   ```

4. **Use the Template**:
   ```json
   {
     "template_name": "your-template-name",
     "business_name": "Example Business",
     // ...
   }
   ```

## Usage Examples

### Basic Usage

```bash
curl -X POST http://localhost:8000/research \
  -H "Content-Type: application/json" \
  -d '{
    "template_name": "local-business",
    "business_name": "JJ Heating & Cooling",
    "business_location": "San Mateo, CA"
  }'
```

### With Additional Context

```bash
curl -X POST http://localhost:8000/research \
  -H "Content-Type: application/json" \
  -d '{
    "template_name": "local-business", 
    "business_name": "Mario'\''s Pizza",
    "business_location": "New York, NY",
    "business_description": "Family-owned Italian restaurant serving authentic pizza and pasta since 1985"
  }'
```

### Python Example

```python
import requests
import json

# Make the request
response = requests.post('http://localhost:8000/research', json={
    "template_name": "local-business",
    "business_name": "ABC Plumbing Services", 
    "business_location": "Los Angeles, CA",
    "business_description": "Emergency plumbing and drain cleaning services"
})

# Parse the response
result = response.json()

if result['success']:
    site_json = result['site_json']
    business_info = result['business_info']
    
    print(f"Generated site for: {site_json['businessName']}")
    print(f"Found {len(business_info.get('local_results', []))} local results")
    
    # Save the site.json
    with open('generated_site.json', 'w') as f:
        json.dump(site_json, f, indent=2)
else:
    print(f"Research failed: {result['error']}")
```

## Testing

### Direct Python Test

```bash
cd vm-py
python test_research_endpoint.py --business-name "JJ Heating & Cooling" --location "San Mateo, CA"
```

### HTTP Test

```bash
cd vm-py
./test_research_endpoint_curl.sh "Mario's Pizza" "New York, NY" "local-business"
```

## Error Handling

The endpoint handles various error conditions gracefully:

### Template Not Found
```json
{
  "success": false,
  "error": "Template 'non-existent-template' not found",
  "template_used": "non-existent-template"
}
```

### Business Not Found
- If no business is found, the endpoint still generates a site.json using template defaults
- The AI will create generic but professional content based on the business name

### AI Generation Failure
- If Gemini AI fails, the endpoint falls back to the template example with basic customization
- Contact information from research is still applied when available

### Network/API Issues
- Multiple Gemini API keys provide redundancy
- BrightData proxy ensures reliable Google search access
- Comprehensive error logging for debugging

## Performance Considerations

- **Response Time**: Typically 30-60 seconds depending on business complexity
- **Rate Limits**: Uses multiple Gemini API keys for high throughput
- **Caching**: Consider caching results for frequently requested businesses
- **Concurrent Requests**: Each request runs independently with isolated resources

## Dependencies

The research endpoint requires:
- Google search clients (`google_searcher.py`, `google_maps_searcher.py`)
- Business review searcher (`business_review_searcher.py`) 
- Gemini AI client (`clients/gemini_client.py`)
- BrightData proxy configuration
- Multiple Gemini API keys in `config.py`

## Security Notes

- Admin-only access should be considered for production use
- Rate limiting recommended to prevent abuse
- API keys are rotated automatically to distribute load
- No sensitive business data is permanently stored

## Future Enhancements

Potential improvements to consider:

1. **Image Integration**: Automatically download and include business photos
2. **Multi-language Support**: Generate sites in different languages
3. **Industry-specific Templates**: Create specialized templates for different business types
4. **Competitive Analysis**: Include competitor information in the research
5. **SEO Optimization**: Generate SEO-optimized content based on keyword research
6. **Social Media Integration**: Include social media profiles and content
