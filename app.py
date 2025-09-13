import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Set, List
import os
import tempfile
import shutil
import json
import subprocess
from pathlib import Path
import traceback

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Domain search
try:
    from clients.namecheap_client import NamecheapClient  # type: ignore
except Exception:
    NamecheapClient = None  # type: ignore

# Business research components
# Capture import errors and diagnostics
BUSINESS_IMPORT_ERROR: Optional[str] = None
BUSINESS_IMPORT_TRACEBACK: Optional[str] = None

try:
    from google_searcher import GoogleSearcher
    from google_maps_searcher import GoogleMapsBusinessSearcher
    from business_review_searcher import BusinessReviewSearcher
    from clients.gemini_client import GeminiClient
    from client_business_researcher import ClientBusinessResearcher
    import config
except Exception as e:
    BUSINESS_IMPORT_ERROR = str(e)
    BUSINESS_IMPORT_TRACEBACK = traceback.format_exc()
    print(f"Warning: Business research dependencies not available: {e}")
    # Traceback helps identify exactly which import failed (often due to env/config)
    print(BUSINESS_IMPORT_TRACEBACK)
    GoogleSearcher = None
    GoogleMapsBusinessSearcher = None
    BusinessReviewSearcher = None
    GeminiClient = None
    ClientBusinessResearcher = None

# Deployment components
try:
    from clients.supabase_client import SupabaseClient
    from data_sync import DataSync
    from deploy_scripts.create_and_push_repo import create_target_repo
    from deploy_scripts.create_cloudflare_pages import create_cloudflare_pages
    from deploy_scripts.add_domain_to_cloudflare import add_domain_to_cloudflare_with_migration
    from deploy_scripts.add_custom_domain import add_custom_domain_to_pages_project
    from site_sanitizer import sanitize_site_json
    from config import (
        GITHUB_USERNAME,
        GITHUB_TOKEN,
        CLIENT_IP,
    )
except Exception as e:
    print(f"Warning: Some deployment dependencies not available: {e}")
    SupabaseClient = None
    DataSync = None
    # Fallback sanitization function if import fails
    def sanitize_site_json(data):
        return data


# ------------------------------
# App state and task management
# ------------------------------

# Admin users who can access purchased domains
ADMIN_USERS = ["edward.hidev@gmail.com", "warren.hidev@gmail.com"]

background_tasks: Set[asyncio.Task] = set()


@dataclass
class AppState:
    loop_counter: int = 0
    started_at: datetime = datetime.utcnow()
    # In-memory mock queue for examples; replace with DB polling of vm_deployable_sites
    pending_deploy_site_ids: List[str] = None


app_state = AppState(pending_deploy_site_ids=[])


def track_task(task: asyncio.Task) -> None:
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


# ------------------------------
# Request models
# ------------------------------

class DeployRequest(BaseModel):
    site_id: str = Field(..., description="UUID of the site in public.vm_sites")
    reason: Optional[str] = Field(
        default=None, description="Optional reason/context for audit logs"
    )


class ResearchRequest(BaseModel):
    business_name: str = Field(..., description="Name of the business to research")
    business_location: str = Field(..., description="Location/address of the business")
    business_description: Optional[str] = Field(None, description="Optional description or context about the business")
    research_id: str = Field(..., description="Unique identifier for this research session")


class ResearchResponse(BaseModel):
    success: bool
    site_json: Optional[Dict[str, Any]] = None
    business_info: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    upload_path: Optional[str] = None
    download_url: Optional[str] = None
class DomainSearchRequest(BaseModel):
    query: str = Field(..., description="Base query or full domain to search")
    tlds: Optional[List[str]] = Field(default=None, description="Optional list of TLDs")

class GetPurchasedDomainsRequest(BaseModel):
    user_email: str = Field(..., description="Email of the user requesting purchased domains")
    search_term: Optional[str] = Field(None, description="Optional search term to filter domains by name")

class DomainSearchResult(BaseModel):
    domain: str
    available: bool
    priceUsd: Optional[float] = None
    isPremium: Optional[bool] = None
    purchase_currency: Optional[str] = None
    renew_price: Optional[float] = None
    renew_currency: Optional[str] = None


# ------------------------------
# Delete/unsubscribe models
# ------------------------------

class DeleteScope(str):
    HOSTING = "hosting"
    DOMAIN = "domain"
    ALL = "all"


class DeleteRequest(BaseModel):
    site_id: str = Field(..., description="UUID of the site in public.vm_sites")
    scope: str = Field(
        default=DeleteScope.ALL,
        description="Which part to cancel. For safety, server cancels both.",
    )
    delete_immediately: bool = Field(
        default=True, description="Cancel now (True) or at period end (False)"
    )
    cancel_domain: Optional[bool] = Field(
        default=True, description="Whether to cancel registrar domain now"
    )
    idempotency_key: Optional[str] = None


# ------------------------------
# Template and research functionality
# ------------------------------

class TemplateLoader:
    """Loads template schemas and example site.json files"""
    
    def __init__(self):
        # Find template directory
        self.project_root = Path(__file__).resolve().parent
        self.template_paths = [
            self.project_root / ".." / "vm-web" / "templates",
            self.project_root / "vm-web" / "templates",
            self.project_root / "launchpad" / "vm-web" / "templates",
        ]
        
        self.template_dir = None
        for path in self.template_paths:
            if path.exists():
                self.template_dir = path
                break
                
        if not self.template_dir:
            print("Warning: Template directory not found")
    
    def load_template_files(self, template_name: str) -> Dict[str, Any]:
        """Load schema.json and site.json for a given template"""
        if not self.template_dir:
            raise HTTPException(status_code=500, detail="Template directory not available")
        
        template_path = self.template_dir / template_name
        if not template_path.exists():
            raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")
        
        # Load schema.json
        schema_path = template_path / "data" / "schema.json"
        schema = {}
        if schema_path.exists():
            with open(schema_path, 'r') as f:
                schema = json.load(f)
        
        # Load example site.json
        site_json_path = template_path / "data" / "site.json"
        example_site_json = {}
        if site_json_path.exists():
            with open(site_json_path, 'r') as f:
                example_site_json = json.load(f)
        
        return {
            "schema": schema,
            "example_site_json": example_site_json,
            "template_path": str(template_path)
        }




# Initialize global instances
template_loader = TemplateLoader()
client_business_researcher = None

def _log_env_and_import_diagnostics() -> None:
    """Log helpful diagnostics when research components are unavailable.

    - Prints which required env vars are missing (names only, not values)
    - Prints any captured import traceback for fast root-cause analysis
    """
    print("\n[DIAGNOSTICS] ClientBusinessResearcher unavailable - running environment/import checks...")
    # Known required env var names as referenced in config.py
    required_keys = [
        "BRIGHTDATA_API_KEY", "BRIGHTDATA_API_ZONE",
        "GITHUB_USERNAME", "GITHUB_TOKEN",
        "REMOTE_TEMPLATE_REPO", "LOCAL_REPO_PATH",
        "NAMECHEAP_API_USER", "NAMECHEAP_API_KEY", "CLIENT_IP", "NAMECHEAP_USERNAME",
        "SUPABASE_ID", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
        "GOOGLE_MAPS_API_KEY",
        "SPACESHIP_API_KEY", "SPACESHIP_API_SECRET",
    ]
    # Gemini keys GEMINI_API_KEY_1..9
    required_keys.extend([f"GEMINI_API_KEY_{i}" for i in range(1, 10)])

    missing = [k for k in required_keys if not os.getenv(k)]
    if missing:
        print(f"[DIAGNOSTICS] Missing environment variables ({len(missing)}): {', '.join(sorted(missing))}")
    else:
        print("[DIAGNOSTICS] All known required environment variables appear to be set.")

    print(f"[DIAGNOSTICS] Working directory: {os.getcwd()}")
    print(f"[DIAGNOSTICS] PYTHONPATH: {os.environ.get('PYTHONPATH', '')}")

    if BUSINESS_IMPORT_ERROR:
        print(f"[DIAGNOSTICS] Import error: {BUSINESS_IMPORT_ERROR}")
    if BUSINESS_IMPORT_TRACEBACK:
        print("[DIAGNOSTICS] Import traceback follows:\n" + BUSINESS_IMPORT_TRACEBACK)

def get_client_business_researcher():
    """Get or create client business researcher instance"""
    global client_business_researcher
    if client_business_researcher is None:
        if ClientBusinessResearcher is None:
            _log_env_and_import_diagnostics()
            raise HTTPException(status_code=500, detail="ClientBusinessResearcher not available")
        client_business_researcher = ClientBusinessResearcher()
    return client_business_researcher


# ------------------------------
# Site.json structure transformation
# ------------------------------

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
    about_keys = ["aboutTitle", "aboutDescription", "aboutStat1Name", "aboutStat1Value", "aboutStat1Icon", 
                  "aboutStat2Name", "aboutStat2Value", "aboutStat2Icon", "aboutStat3Name", "aboutStat3Value", "aboutStat3Icon",
                  "aboutFeature1", "aboutFeature2", "aboutFeature3", "aboutFeature4", "aboutFeature5", "aboutFeature6",
                  "aboutImage1Url", "aboutImage1Alt", "aboutImage2Url", "aboutImage2Alt", "aboutImage3Url", "aboutImage3Alt",
                  "aboutImage4Url", "aboutImage4Alt", "aboutImage5Url", "aboutImage5Alt", "aboutImage6Url", "aboutImage6Alt"]
    if any(key in site_data for key in about_keys) or "about" in site_data:
        if "about" not in transformed:
            transformed["about"] = {}
            
        if "aboutTitle" in site_data:
            transformed["about"]["title"] = site_data["aboutTitle"]
        if "aboutDescription" in site_data:
            transformed["about"]["description"] = site_data["aboutDescription"]
            
        # Handle statistics from flat structure
        statistics = []
        for i in range(1, 4):  # Support 3 statistics
            name_key = f"aboutStat{i}Name"
            value_key = f"aboutStat{i}Value"
            icon_key = f"aboutStat{i}Icon"
            
            if name_key in site_data and value_key in site_data:
                stat = {
                    "name": site_data[name_key],
                    "value": site_data[value_key],
                    "icon": site_data.get(icon_key, "AcademicCapIcon")
                }
                if stat["name"].strip() and stat["value"].strip():
                    statistics.append(stat)
        
        if statistics:
            transformed["about"]["statistics"] = statistics
            print(f"[DEPLOY] Transformed {len(statistics)} about statistics from flat structure")
        elif "about" in site_data and isinstance(site_data["about"], dict) and "statistics" in site_data["about"]:
            # Handle existing structured statistics
            transformed["about"]["statistics"] = site_data["about"]["statistics"]
            
        # Handle features from flat structure
        features = []
        for i in range(1, 7):  # Support 6 features
            feature_key = f"aboutFeature{i}"
            if feature_key in site_data and site_data[feature_key] and site_data[feature_key].strip():
                features.append(site_data[feature_key])
                
        if features:
            transformed["about"]["features"] = features
            print(f"[DEPLOY] Transformed {len(features)} about features from flat structure")
        elif "about" in site_data and isinstance(site_data["about"], dict) and "features" in site_data["about"]:
            # Handle existing structured features
            transformed["about"]["features"] = site_data["about"]["features"]
            
        # Handle about images from flat structure
        images = []
        for i in range(1, 7):  # Support 6 images
            url_key = f"aboutImage{i}Url"
            alt_key = f"aboutImage{i}Alt"
            
            if url_key in site_data and site_data[url_key] and site_data[url_key].strip():
                image = {
                    "imageUrl": site_data[url_key],
                    "alt": site_data.get(alt_key, f"About image {i}")
                }
                images.append(image)
                
        if images:
            transformed["about"]["images"] = images
            print(f"[DEPLOY] Transformed {len(images)} about images from flat structure")
        elif "about" in site_data and isinstance(site_data["about"], dict) and "images" in site_data["about"]:
            # Handle existing structured images
            transformed["about"]["images"] = site_data["about"]["images"]
    
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
                # Keep "name" for backward compatibility, but "title" is what components use
            
            transformed["services"].append(transformed_service)
        
        print(f"[DEPLOY] Transformed {len(transformed['services'])} services: added IDs and title fields")
    
    # Transform business benefits structure (renamed from emergency benefits)
    if ("businessBenefitsTitle" in site_data or "businessBenefits" in site_data or 
        "emergencyBenefitsTitle" in site_data or "emergencyBenefits" in site_data):
        if "businessBenefits" not in transformed:
            transformed["businessBenefits"] = {"title": "Why Choose Our Services", "items": []}
        
        # Handle legacy emergencyBenefits fields for backward compatibility
        if "emergencyBenefitsTitle" in site_data:
            transformed["businessBenefits"]["title"] = site_data["emergencyBenefitsTitle"]
        elif "businessBenefitsTitle" in site_data:
            transformed["businessBenefits"]["title"] = site_data["businessBenefitsTitle"]
        
        # Handle flat business benefits items (businessBenefit1Title, businessBenefit1Description, etc.)
        business_items = []
        i = 1
        # Try new businessBenefit fields first
        while f"businessBenefit{i}Title" in site_data:
            item = {
                "title": site_data[f"businessBenefit{i}Title"],
                "description": site_data.get(f"businessBenefit{i}Description", "")
            }
            business_items.append(item)
            i += 1
        
        # If no new fields found, try legacy emergencyBenefit fields for backward compatibility
        if not business_items:
            i = 1
            while f"emergencyBenefit{i}Title" in site_data:
                item = {
                    "title": site_data[f"emergencyBenefit{i}Title"],
                    "description": site_data.get(f"emergencyBenefit{i}Description", "")
                }
                business_items.append(item)
                i += 1
        
        if business_items:
            transformed["businessBenefits"]["items"] = business_items
            print(f"[DEPLOY] Transformed {len(business_items)} business benefits from flat structure")
        elif "businessBenefits" in site_data and isinstance(site_data["businessBenefits"], dict):
            # Handle existing structured business benefits
            if "items" in site_data["businessBenefits"]:
                transformed["businessBenefits"]["items"] = site_data["businessBenefits"]["items"]
            if "title" in site_data["businessBenefits"]:
                transformed["businessBenefits"]["title"] = site_data["businessBenefits"]["title"]
        elif "emergencyBenefits" in site_data and isinstance(site_data["emergencyBenefits"], dict):
            # Handle legacy emergencyBenefits structure for backward compatibility
            if "items" in site_data["emergencyBenefits"]:
                transformed["businessBenefits"]["items"] = site_data["emergencyBenefits"]["items"]
            if "title" in site_data["emergencyBenefits"]:
                transformed["businessBenefits"]["title"] = site_data["emergencyBenefits"]["title"]
    
    # Transform services structure to be self-contained
    if "services" in site_data:
        if isinstance(site_data["services"], list):
            # Handle legacy array format - convert to new object format
            transformed["services"] = {
                "title": site_data.get("servicesTitle", "Our Services"),
                "subtitle": site_data.get("servicesSubtitle", "Professional solutions tailored to your needs"),
                "items": site_data["services"]
            }
            print(f"[DEPLOY] Converted legacy services array to new object format with {len(site_data['services'])} items")
        elif isinstance(site_data["services"], dict):
            # Handle new object format
            transformed["services"] = site_data["services"]
            # Override with flat fields if they exist
            if "servicesTitle" in site_data:
                transformed["services"]["title"] = site_data["servicesTitle"]
            if "servicesSubtitle" in site_data:
                transformed["services"]["subtitle"] = site_data["servicesSubtitle"]
        else:
            # Create default structure
            transformed["services"] = {
                "title": site_data.get("servicesTitle", "Our Services"),
                "subtitle": site_data.get("servicesSubtitle", "Professional solutions tailored to your needs"),
                "items": []
            }
    
    # Transform testimonials structure to be self-contained
    if "testimonials" in site_data:
        if isinstance(site_data["testimonials"], dict) and "items" in site_data["testimonials"]:
            # Handle new object format
            transformed["testimonials"] = site_data["testimonials"]
            # Override with flat fields if they exist
            if "testimonialsTitle" in site_data:
                transformed["testimonials"]["title"] = site_data["testimonialsTitle"]
            if "testimonialsSubtitle" in site_data:
                transformed["testimonials"]["subtitle"] = site_data["testimonialsSubtitle"]
        elif isinstance(site_data["testimonials"], list):
            # Handle legacy array format
            transformed["testimonials"] = {
                "title": site_data.get("testimonialsTitle", "What Our Clients Say"),
                "subtitle": site_data.get("testimonialsSubtitle", "Don't just take our word for it. Here's what our satisfied clients have to say about our professional services."),
                "items": site_data["testimonials"]
            }
            print(f"[DEPLOY] Converted legacy testimonials array to new object format with {len(site_data['testimonials'])} items")
        else:
            # Create default structure
            transformed["testimonials"] = {
                "title": site_data.get("testimonialsTitle", "What Our Clients Say"),
                "subtitle": site_data.get("testimonialsSubtitle", "Don't just take our word for it. Here's what our satisfied clients have to say about our professional services."),
                "items": []
            }
    
    # Transform contact structure to be self-contained
    if "contact" in site_data:
        if isinstance(site_data["contact"], dict):
            transformed["contact"] = site_data["contact"]
            # Override with flat fields if they exist
            if "contactTitle" in site_data:
                transformed["contact"]["title"] = site_data["contactTitle"]
            if "contactSubtitle" in site_data:
                transformed["contact"]["subtitle"] = site_data["contactSubtitle"]
        else:
            # Create default structure
            transformed["contact"] = {
                "title": site_data.get("contactTitle", "Contact Us"),
                "subtitle": site_data.get("contactSubtitle", "Get in touch with us today. We're here to help with all your needs."),
                "email": site_data.get("contactEmail", ""),
                "address": site_data.get("contactAddress", ""),
                "phone": site_data.get("phone", ""),
                "mapEmbedUrl": site_data.get("contactMapEmbedUrl", "")
            }
    
    # Transform business hours structure
    business_hours_keys = ["businessHoursEnabled", "mondayOpen", "mondayClose", "mondayClosed", 
                          "tuesdayOpen", "tuesdayClose", "tuesdayClosed", "wednesdayOpen", "wednesdayClose", "wednesdayClosed",
                          "thursdayOpen", "thursdayClose", "thursdayClosed", "fridayOpen", "fridayClose", "fridayClosed",
                          "saturdayOpen", "saturdayClose", "saturdayClosed", "sundayOpen", "sundayClose", "sundayClosed"]
    if any(key in site_data for key in business_hours_keys) or (site_data.get("contact", {}).get("businessHours")):
        if "contact" not in transformed:
            transformed["contact"] = {}
        
        # Handle flat business hours fields (from editor)
        if site_data.get("businessHoursEnabled"):
            business_hours = {}
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            day_keys = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            
            def convert_to_12_hour(time_24h: str) -> str:
                """Convert 24-hour time format to 12-hour format"""
                if not time_24h:
                    return ""
                
                try:
                    hours, minutes = time_24h.split(':')
                    hour = int(hours)
                    ampm = 'PM' if hour >= 12 else 'AM'
                    hour_12 = hour % 12 or 12
                    return f"{hour_12}:{minutes} {ampm}"
                except (ValueError, IndexError):
                    return time_24h  # Return original if parsing fails
            
            for day, day_key in zip(days, day_keys):
                closed_key = f"{day_key}Closed"
                open_key = f"{day_key}Open"
                close_key = f"{day_key}Close"
                
                if site_data.get(closed_key):
                    business_hours[day] = "closed"
                elif site_data.get(open_key) and site_data.get(close_key):
                    # Convert from 24-hour format (editor) to 12-hour format (display)
                    business_hours[day] = {
                        "open": convert_to_12_hour(site_data[open_key]),
                        "close": convert_to_12_hour(site_data[close_key])
                    }
            
            if business_hours:
                transformed["contact"]["businessHours"] = business_hours
                print(f"[DEPLOY] Transformed business hours from flat structure")
        elif "contact" in site_data and isinstance(site_data["contact"], dict) and "businessHours" in site_data["contact"]:
            # Handle existing structured business hours
            transformed["contact"]["businessHours"] = site_data["contact"]["businessHours"]
    
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
        print(f"[DEPLOY] Transformed {len(transformed_testimonials)} testimonials: mapped name/quote fields")
    
    print(f"[DEPLOY] Transformed site.json structure - added nested objects for components")
    return transformed


# ------------------------------
# Real DB/storage helpers
# ------------------------------

async def db_get_site(site_id: str) -> Optional[Dict[str, Any]]:
    """Get site details from vm_sites table"""
    if not SupabaseClient:
        raise HTTPException(status_code=500, detail="Supabase client not available")
    
    try:
        supabase = SupabaseClient()
        response = supabase.client.table("vm_sites").select("*").eq("id", site_id).execute()
        
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


async def db_mark_site_deploy_status(site_id: str, status: str, error: Optional[str] = None) -> None:
    """Update deployment status in vm_sites table"""
    if not SupabaseClient:
        raise HTTPException(status_code=500, detail="Supabase client not available")
    
    try:
        supabase = SupabaseClient()
        update_data = {
            "deployment_status": status,
            "deployment_error": error,
        }
        
        if status == "succeeded":
            update_data.update({
                "is_deployed": True,
                "deployed_at": datetime.utcnow().isoformat(),
            })
        
        supabase.client.table("vm_sites").update(update_data).eq("id", site_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database update error: {str(e)}")


async def storage_pull_build_inputs(user_id: str, site_url: str) -> Dict[str, Any]:
    """Pull site.json, backlinks.json, and images from Supabase storage"""
    if not DataSync:
        raise HTTPException(status_code=500, detail="DataSync not available")
    
    try:
        data_sync = DataSync(site_data_bucket="site-data", sites_bucket="vm-sites")
        
        # Create temp directory for downloaded files
        temp_dir = tempfile.mkdtemp(prefix=f"deploy_{user_id}_")
        
        # Pull user's site.json
        site_json_path = Path(temp_dir) / "site.json"
        site_json_pulled = data_sync.pull_user_site_json(
            user_uuid=user_id,
            local_json_path=str(site_json_path),
            remote_base_folder="private",
            site_url=site_url,
        )
        
        site_json_data = {}
        if site_json_pulled and site_json_path.exists():
            with open(site_json_path, 'r') as f:
                site_json_data = json.load(f)
        
        # Pull backlinks.json if it exists
        backlinks_json_data = {}
        try:
            sites_client = SupabaseClient(bucket_name="vm-sites")
            backlinks_path = f"private/{user_id}/{site_url}/backlinks.json"
            backlinks_local_path = Path(temp_dir) / "backlinks.json"
            sites_client.download_file(backlinks_path, str(backlinks_local_path))
            
            if backlinks_local_path.exists():
                with open(backlinks_local_path, 'r') as f:
                    backlinks_json_data = json.load(f)
        except Exception:
            # backlinks.json is optional
            pass
        
        # List and download images from both private and public folders
        images = []
        try:
            sites_client = SupabaseClient(bucket_name="vm-sites")
            image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
            
            # Download from private folder (existing logic)
            try:
                private_folder = f"private/{user_id}/{site_url}"
                private_files = sites_client._list_files_recursive(
                    folder_path=private_folder, 
                    bucket_name="vm-sites"
                )
                
                for file_info in private_files:
                    file_name = file_info.get("name", "")
                    file_path = file_info.get("full_path", "")
                    
                    if Path(file_name).suffix.lower() in image_extensions:
                        local_image_path = Path(temp_dir) / file_name
                        sites_client.download_file(file_path, str(local_image_path))
                        images.append({
                            "name": file_name,
                            "local_path": str(local_image_path),
                            "remote_path": file_path,
                        })
                print(f"[DEPLOY] Downloaded {len([img for img in images])} images from private folder")
            except Exception as e:
                print(f"[DEPLOY] No private images found: {e}")
            
            # Download from public folder (for logos, etc.)
            try:
                public_folder = f"public/{user_id}/{site_url}"
                public_files = sites_client._list_files_recursive(
                    folder_path=public_folder, 
                    bucket_name="vm-sites"
                )
                
                for file_info in public_files:
                    file_name = file_info.get("name", "")
                    file_path = file_info.get("full_path", "")
                    
                    if Path(file_name).suffix.lower() in image_extensions:
                        local_image_path = Path(temp_dir) / file_name
                        sites_client.download_file(file_path, str(local_image_path))
                        images.append({
                            "name": file_name,
                            "local_path": str(local_image_path),
                            "remote_path": file_path,
                        })
                print(f"[DEPLOY] Downloaded {len([img for img in images if 'public' in img['remote_path']])} images from public folder")
            except Exception as e:
                print(f"[DEPLOY] No public images found: {e}")
                
        except Exception:
            # Images are optional
            pass
        
        return {
            "site_json": site_json_data,
            "backlinks_json": backlinks_json_data,
            "images": images,
            "temp_dir": temp_dir,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")


# ------------------------------
# Mock billing/infra helpers (replace in production)
# ------------------------------

async def db_get_active_subscription(site_id: str) -> Optional[Dict[str, Any]]:
    # Replace with a real query to public.vm_site_subscriptions for active-ish statuses
    await asyncio.sleep(0.05)
    return {"stripe_subscription_id": "sub_123", "site_id": site_id}


async def stripe_cancel_subscription(stripe_subscription_id: str, *, immediate: bool, idempotency_key: Optional[str]) -> None:
    # Replace with stripe.Subscription.delete(...) or update(cancel_at_period_end=True)
    await asyncio.sleep(0.05)


async def registrar_cancel_domain(site_url: str) -> None:
    # Replace with registrar API call to cancel/disable domain
    await asyncio.sleep(0.05)


async def teardown_github_repo(site: Dict[str, Any]) -> None:
    await asyncio.sleep(0.05)


async def teardown_cloudflare_project(site: Dict[str, Any]) -> None:
    await asyncio.sleep(0.05)


async def db_soft_delete_site(site_id: str) -> None:
    # UPDATE public.vm_sites SET deleted_at=now() WHERE id=:site_id
    # Triggers will auto-release env slot
    await asyncio.sleep(0.05)


# ------------------------------
# Helper functions
# ------------------------------

async def upload_site_json_to_bucket(site_json: Dict[str, Any], research_id: str) -> tuple[Optional[str], Optional[str]]:
    """
    Upload site.json data to Supabase bucket
    
    Args:
        site_json: The site.json dictionary to upload
        research_id: Unique identifier for the research session
        
    Returns:
        Tuple of (upload_path, download_url) or (None, None) if upload fails
    """
    if not SupabaseClient:
        print(f"[UPLOAD] SupabaseClient not available, skipping upload")
        return None, None
    
    try:
        print(f"[UPLOAD] Uploading site.json to bucket for research ID: {research_id}")
        
        # Debug: Check environment variables
        import config
        print(f"[UPLOAD] Environment check - SUPABASE_URL exists: {hasattr(config, 'SUPABASE_URL') and bool(getattr(config, 'SUPABASE_URL', None))}")
        print(f"[UPLOAD] Environment check - SUPABASE_SERVICE_ROLE_KEY exists: {hasattr(config, 'SUPABASE_SERVICE_ROLE_KEY') and bool(getattr(config, 'SUPABASE_SERVICE_ROLE_KEY', None))}")
        
        if hasattr(config, 'SUPABASE_URL'):
            supabase_url = getattr(config, 'SUPABASE_URL', '')
            print(f"[UPLOAD] SUPABASE_URL (full): {supabase_url}")
            print(f"[UPLOAD] SUPABASE_URL length: {len(supabase_url)} characters")
            print(f"[UPLOAD] SUPABASE_URL starts with https://: {supabase_url.startswith('https://')}")
            print(f"[UPLOAD] SUPABASE_URL ends with .supabase.co: {supabase_url.endswith('.supabase.co')}")
        else:
            print(f"[UPLOAD] ❌ SUPABASE_URL not found in config!")
            
        if hasattr(config, 'SUPABASE_SERVICE_ROLE_KEY'):
            service_key = getattr(config, 'SUPABASE_SERVICE_ROLE_KEY', '')
            print(f"[UPLOAD] SUPABASE_SERVICE_ROLE_KEY length: {len(service_key)} characters")
            print(f"[UPLOAD] SUPABASE_SERVICE_ROLE_KEY preview: {service_key[:20]}..." if len(service_key) > 20 else f"[UPLOAD] SUPABASE_SERVICE_ROLE_KEY: {service_key}")
        else:
            print(f"[UPLOAD] ❌ SUPABASE_SERVICE_ROLE_KEY not found in config!")
        
        # Create temporary file for upload
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(site_json, temp_file, indent=2)
            temp_file_path = temp_file.name
        
        print(f"[UPLOAD] Created temp file: {temp_file_path}")
        
        # Upload to vm-sites bucket at public/research/<research_id>/site.json
        print(f"[UPLOAD] Initializing SupabaseClient for bucket 'vm-sites'")
        try:
            sites_client = SupabaseClient(bucket_name="vm-sites")
            print(f"[UPLOAD] ✅ SupabaseClient initialized successfully")
        except Exception as init_error:
            print(f"[UPLOAD] ❌ Failed to initialize SupabaseClient: {init_error}")
            print(f"[UPLOAD] This usually means environment variables are missing or malformed")
            raise HTTPException(status_code=500, detail=f"Supabase client initialization failed: {str(init_error)}")
        
        upload_path = f"public/research/{research_id}/site.json"
        
        print(f"[UPLOAD] Starting file upload to path: {upload_path}")
        upload_result = sites_client.upload_file(
            local_path=temp_file_path,
            remote_path=upload_path
        )
        
        # Clean up temp file
        os.unlink(temp_file_path)
        print(f"[UPLOAD] Temp file cleaned up")
        
        if upload_result:
            print(f"[UPLOAD] File upload successful, generating public URL...")
            # Generate download URL (public URL for the uploaded file)
            try:
                download_url = sites_client.get_public_url(upload_path)
                print(f"[UPLOAD] Successfully uploaded site.json to: {upload_path}")
                print(f"[UPLOAD] Download URL: {download_url}")
                return upload_path, download_url
            except Exception as url_error:
                print(f"[UPLOAD] Error generating public URL: {str(url_error)}")
                print(f"[UPLOAD] URL Error type: {type(url_error).__name__}")
                print(f"[UPLOAD] File was uploaded successfully but URL generation failed")
                # Return the upload path even if URL generation fails
                return upload_path, None
        else:
            print(f"[UPLOAD] Failed to upload site.json to bucket")
            return None, None
            
    except Exception as e:
        print(f"[UPLOAD] Upload error: {str(e)}")
        print(f"[UPLOAD] Error type: {type(e).__name__}")
        import traceback
        print(f"[UPLOAD] Full traceback:")
        print(traceback.format_exc())
        raise


# ------------------------------
# Task functions
# ------------------------------

async def client_research_task(payload: ResearchRequest) -> Dict[str, Any]:
    """Research a business and generate site.json using ClientBusinessResearcher"""
    try:
        print(f"\n{'='*80}")
        print(f"[CLIENT_RESEARCH] STARTING RESEARCH TASK")
        print(f"{'='*80}")
        print(f"📋 PARAMETERS:")
        print(f"   • Research ID: {payload.research_id}")
        print(f"   • Business Name: '{payload.business_name}'")
        print(f"   • Business Location: '{payload.business_location}'")
        print(f"   • Business Description: '{payload.business_description or 'Not provided'}'")
        print(f"   • Timestamp: {__import__('datetime').datetime.now().isoformat()}")
        print(f"{'='*80}")
        
        # Get ClientBusinessResearcher instance
        researcher = get_client_business_researcher()
        
        # Step 1: Gather business data using GBPResearcher
        print(f"\n🔍 STEP 1: GATHERING GOOGLE BUSINESS DATA")
        print(f"{'-'*60}")
        
        business_data = None
        google_business_found = False
        google_business_name = None
        review_count = 0
        
        try:
            # Get business data including reviews
            html, maps_data, reviews = await researcher.gbp_researcher.get_business_data(
                business_name=payload.business_name,
                business_location=payload.business_location,
                max_reviews=20
            )
            
            # Check if we found a Google Business Profile
            if maps_data or reviews or html:
                google_business_found = True
                
                # Extract business name from maps data if available
                if maps_data and "place" in maps_data:
                    google_business_name = maps_data["place"].get("name", payload.business_name)
                else:
                    google_business_name = payload.business_name
                
                # Count reviews
                if reviews:
                    review_count = len(reviews)
                
                # Log detailed findings
                print(f"✅ GOOGLE BUSINESS PROFILE FOUND!")
                print(f"   • Business Name: '{google_business_name}'")
                print(f"   • HTML Content: {'✅ Retrieved' if html else '❌ Not available'} ({len(html or '')} chars)")
                print(f"   • Maps Data: {'✅ Retrieved' if maps_data else '❌ Not available'}")
                print(f"   • Reviews: {review_count} reviews retrieved")
                
                # Additional details from maps data
                if maps_data and "place" in maps_data:
                    place_data = maps_data["place"]
                    if place_data.get("phone"):
                        print(f"   • Phone: {place_data['phone']}")
                    if place_data.get("rating"):
                        print(f"   • Rating: {place_data['rating']}")
                    if place_data.get("review_count"):
                        print(f"   • Total Reviews on Google: {place_data['review_count']}")
                    if place_data.get("category"):
                        categories = [cat.get("title", "") for cat in place_data["category"][:3]]
                        print(f"   • Categories: {', '.join(categories)}")
                
                # Create BusinessData object
                from gbp_researcher import BusinessData, BusinessReviewsResult
                
                # Extract business type from Google Maps categories
                business_type = "Professional Services"  # Default fallback
                if maps_data and "place" in maps_data and "category" in maps_data["place"]:
                    categories = maps_data["place"]["category"]
                    if categories:
                        primary_category = categories[0].get("title", "Professional Services")
                        business_type = primary_category
                
                # Extract phone number from maps data
                phone_number = None
                if maps_data and "place" in maps_data and "phone" in maps_data["place"]:
                    phone_number = maps_data["place"]["phone"]
                
                business_data = BusinessData(
                    name=google_business_name,
                    business_type=business_type,
                    phone=phone_number,
                    cleaned_html=html,
                    maps_data=maps_data
                )
                
                if reviews:
                    business_data.reviews = BusinessReviewsResult(
                        business_name=google_business_name,
                        business_fid="research-fid",
                        reviews=reviews
                    )
                
            else:
                print(f"❌ NO GOOGLE BUSINESS PROFILE FOUND")
                print(f"   • Will generate site using fallback content")
                print(f"   • Business name: '{payload.business_name}'")
                print(f"   • Location: '{payload.business_location}'")
                
        except Exception as gbp_error:
            print(f"❌ ERROR DURING GOOGLE BUSINESS RESEARCH: {gbp_error}")
            print(f"   • Will continue with fallback content generation")
        
        # Step 2: Generate complete site.json
        print(f"\n🏗️ STEP 2: GENERATING SITE.JSON")
        print(f"{'-'*60}")
        
        site_json = await researcher.generate_complete_site_json(
            business_name=payload.business_name,
            business_location=payload.business_location,
            business_description=payload.business_description or "",
            business_data=business_data,
            output_file=None,  # Don't save to file, just return the data
            max_services=4,
            max_testimonials=6
        )
        
        # Step 3: Upload to bucket
        print(f"\n📤 STEP 3: UPLOADING TO BUCKET")
        print(f"{'-'*60}")
        
        upload_path = None
        download_url = None
        
        try:
            upload_path, download_url = await upload_site_json_to_bucket(site_json, payload.research_id)
            print(f"✅ Successfully uploaded to bucket")
            print(f"   • Upload path: {upload_path}")
            print(f"   • Download URL available: {'✅' if download_url else '❌'}")
        except Exception as upload_error:
            print(f"❌ Upload to bucket failed: {upload_error}")
            # Continue without failing the entire research task
        
        # Final summary
        print(f"\n📊 RESEARCH TASK SUMMARY")
        print(f"{'='*80}")
        print(f"✅ Research completed successfully for '{payload.business_name}'")
        print(f"   • Google Business Profile: {'✅ FOUND' if google_business_found else '❌ NOT FOUND'}")
        if google_business_found:
            print(f"   • Google Business Name: '{google_business_name}'")
            print(f"   • Reviews Retrieved: {review_count}")
        print(f"   • Site.json Generated: ✅")
        print(f"   • Upload Status: {'✅' if upload_path else '❌'}")
        print(f"   • Research ID: {payload.research_id}")
        print(f"{'='*80}\n")
        
        return {
            "success": True,
            "site_json": site_json,
            "business_info": {
                "business_name": payload.business_name,
                "business_location": payload.business_location,
                "business_description": payload.business_description,
                "research_id": payload.research_id,
                "google_business_found": google_business_found,
                "google_business_name": google_business_name,
                "review_count": review_count
            },
            "upload_path": upload_path,
            "download_url": download_url
        }
        
    except Exception as e:
        print(f"\n❌ RESEARCH TASK FAILED")
        print(f"{'='*80}")
        print(f"Error: {e}")
        print(f"Business: '{payload.business_name}' in '{payload.business_location}'")
        print(f"Research ID: {payload.research_id}")
        print(f"{'='*80}\n")
        return {
            "success": False,
            "error": str(e)
        }


async def deploy_task(payload: DeployRequest) -> None:
    """Real deployment task that integrates with existing deployment scripts"""
    site = await db_get_site(payload.site_id)
    if not site:
        raise HTTPException(status_code=404, detail="site not found")

    site_id = site["id"]
    user_id = site["user_id"]
    site_url = site["site_url"]
    slot = site.get("slot")
    domain_registrar = site.get("domain_registrar", "namecheap")
    is_first_deploy = not site.get("is_deployed", False)
    is_self_managed = domain_registrar == "self_managed"
    
    print(f"[DEPLOY] Starting deployment for site {site_id} ({site_url})")
    print(f"[DEPLOY] User: {user_id}, Slot: {slot}, First deploy: {is_first_deploy}")
    print(f"[DEPLOY] Domain registrar: {domain_registrar}, Self-managed: {is_self_managed}")

    # Compute Cloudflare credentials and project name based on slot
    if slot is not None and slot < 70:
        cloudflare_api_token = "z49VdskL215U7yLZr__2BpAJ746PCRaZoZbjIl8z"
        cloudflare_account_id = "627931b9aaeb2438ddf36d6f068f02c2"
        project_name = f"cookie-{slot}"
    
    print(f"[DEPLOY] Using Cloudflare project: {project_name}")
    print(f"[DEPLOY] Using slot-based credentials: {slot is not None and slot < 70}")

    try:
        await db_mark_site_deploy_status(site_id, status="building")

        # 1. Pull build inputs from storage
        print("[DEPLOY] Pulling build inputs from storage...")
        inputs = await storage_pull_build_inputs(user_id, site_url)
        temp_dir = inputs["temp_dir"]
        
        try:
            # 2. Set up working directory with template
            print("[DEPLOY] Setting up template...")
            work_dir = await setup_template_with_content(inputs, site_url)
            
            # 3. Generate repository name (GitHub repo name stays the same)
            user_suffix = user_id[:8].lower() if len(user_id) >= 8 else user_id.lower()
            github_repo_name = f"{project_name.replace(' ', '-').lower()}-{user_suffix}"
            
            print(f"[DEPLOY] GitHub repo: {github_repo_name}")
            print(f"[DEPLOY] Cloudflare project: {project_name}")
            
            # 4. First-time setup (domain purchase, site record creation)
            if is_first_deploy and not is_self_managed:
                print("[DEPLOY] First-time deployment - setting up domain and site record...")
                await handle_first_time_deployment(site_url, site_id, user_id)
            elif is_first_deploy and is_self_managed:
                print("[DEPLOY] First-time deployment - self-managed domain, skipping domain purchase...")
            
            # 5. Create GitHub repository
            print("[DEPLOY] Creating GitHub repository...")
            await asyncio.get_event_loop().run_in_executor(
                None, create_target_repo, github_repo_name
            )
            
            # 6. Push code to GitHub
            print("[DEPLOY] Pushing code to GitHub...")
            await push_to_github(work_dir, github_repo_name)
            
            # 7. Create Cloudflare Pages project
            print("[DEPLOY] Creating Cloudflare Pages project...")
            pages_result = await asyncio.get_event_loop().run_in_executor(
                None, create_cloudflare_pages,
                github_repo_name, project_name,
                cloudflare_api_token, cloudflare_account_id, "out"
            )
            
            pages_url = pages_result.get("pages_url") if pages_result else None
            print(f"[DEPLOY] Cloudflare Pages URL: {pages_url}")
            
            # 8. Configure custom domain (first-time only, not for self-managed)
            if is_first_deploy and not is_self_managed:
                print("[DEPLOY] Configuring custom domain...")
                await configure_custom_domain(site_url, project_name, cloudflare_api_token, cloudflare_account_id)
            elif is_first_deploy and is_self_managed:
                print("[DEPLOY] Self-managed domain - skipping Cloudflare domain configuration...")
            
            # 9. Trigger deployment with noop commit
            print("[DEPLOY] Triggering Cloudflare deployment...")
            await trigger_deployment(work_dir)
            
            # 10. Update site record with final URL
            if is_self_managed:
                # For self-managed domains, the final URL is the custom domain (once DNS is set up)
                final_url = f"https://{site_url}"
            elif is_first_deploy and not is_self_managed:
                # For managed domains on first deploy, use the custom domain
                final_url = f"https://{site_url}"
            else:
                # For subsequent deploys, use the pages URL
                final_url = pages_url
            
            await update_site_deployment_success(site_id, final_url)
            
            if is_self_managed:
                print(f"[DEPLOY] ✅ Deployment successful! Site deployed to Cloudflare Pages.")
                print(f"[DEPLOY] 🔧 DNS Setup Required: Configure your domain {site_url} to point to the Cloudflare Pages project.")
                print(f"[DEPLOY] 📚 Follow the domain setup guide for detailed instructions.")
            else:
                print(f"[DEPLOY] ✅ Deployment successful! Site available at: {final_url}")
            
        finally:
            # Clean up temporary directories
            cleanup_directories([temp_dir, work_dir] if 'work_dir' in locals() else [temp_dir])
            
    except Exception as exc:
        error_msg = str(exc)
        print(f"[DEPLOY] ❌ Deployment failed: {error_msg}")
        await db_mark_site_deploy_status(site_id, status="failed", error=error_msg)
        raise


async def setup_template_with_content(inputs: Dict[str, Any], site_url: str) -> str:
    """Set up template directory with user content injected by cloning from GitHub"""
    from config import REMOTE_TEMPLATE_REPO, GITHUB_USERNAME, GITHUB_TOKEN
    import subprocess
    
    print(f"[DEPLOY] Cloning template from remote repository: {REMOTE_TEMPLATE_REPO}")
    
    # Handle different REMOTE_TEMPLATE_REPO formats
    if REMOTE_TEMPLATE_REPO.startswith("https://github.com/"):
        # Full GitHub URL - use as is and add authentication
        base_url = REMOTE_TEMPLATE_REPO
        authenticated_repo_url = base_url.replace(
            "https://github.com/", 
            f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/"
        )
    elif "/" in REMOTE_TEMPLATE_REPO and not REMOTE_TEMPLATE_REPO.startswith("http"):
        # Format like "username/repo" - construct full GitHub URL
        base_url = f"https://github.com/{REMOTE_TEMPLATE_REPO}.git"
        authenticated_repo_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{REMOTE_TEMPLATE_REPO}.git"
    else:
        # Just repo name like "vm-web" - assume it belongs to GITHUB_USERNAME
        base_url = f"https://github.com/{GITHUB_USERNAME}/{REMOTE_TEMPLATE_REPO}.git"
        authenticated_repo_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{REMOTE_TEMPLATE_REPO}.git"
    
    print(f"[DEPLOY] Constructed repository URL: {base_url}")
    
    # Use a persistent directory for the template repo to enable git pull updates
    # This avoids re-cloning on every deployment
    # Use /app/template_cache for persistence (not /tmp which gets cleared)
    template_cache_dir = Path("/app") / "template_cache" / REMOTE_TEMPLATE_REPO.replace("/", "_")
    template_cache_dir.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if template_cache_dir.exists() and (template_cache_dir / ".git").exists():
            # Repository already exists locally - update it with git pull
            print(f"[DEPLOY] Found existing template repo at: {template_cache_dir}")
            print("[DEPLOY] Updating template repo with git pull...")
            
            # Change to the repo directory and pull latest changes
            # Use a safe working directory in case current directory was deleted
            try:
                original_cwd = os.getcwd()
            except FileNotFoundError:
                # Current working directory doesn't exist, use /app as fallback
                original_cwd = "/app"
                os.chdir("/app")
                
            os.chdir(template_cache_dir)
            
            try:
                # Configure the remote URL with authentication (in case credentials changed)
                subprocess.run([
                    "git", "remote", "set-url", "origin", authenticated_repo_url
                ], capture_output=True, text=True, check=True)
                
                # Pull latest changes
                pull_result = subprocess.run([
                    "git", "pull", "origin", "main"
                ], capture_output=True, text=True, check=True)
                
                print(f"[DEPLOY] Successfully updated template repo: {pull_result.stdout.strip()}")
                
            finally:
                # Always restore original working directory
                os.chdir(original_cwd)
                
            clone_dir = template_cache_dir
        else:
            # Repository doesn't exist locally - clone it
            print(f"[DEPLOY] Template repo not found locally, cloning to: {template_cache_dir}")
            
            # Remove any existing directory that might be corrupted
            if template_cache_dir.exists():
                shutil.rmtree(template_cache_dir)
            
            clone_result = subprocess.run([
                "git", "clone", authenticated_repo_url, str(template_cache_dir)
            ], capture_output=True, text=True, check=True)
            
            print(f"[DEPLOY] Successfully cloned template repo to: {template_cache_dir}")
            clone_dir = template_cache_dir
        
        # Look for the local-business template in the cloned repo
        # Try different possible paths in the cloned repository
        possible_template_paths = [
            Path(clone_dir) / "vm-web" / "templates" / "local-business",
            Path(clone_dir) / "templates" / "local-business", 
            Path(clone_dir) / "local-business",
        ]
        
        template_dir = None
        for template_path in possible_template_paths:
            print(f"[DEPLOY] Checking for template at: {template_path}")
            if template_path.exists():
                template_dir = template_path
                print(f"[DEPLOY] Found template in cloned repo: {template_dir}")
                break
        
        if not template_dir:
            # List what's actually in the cloned directory for debugging
            print(f"[DEPLOY] Contents of cloned repo: {list(Path(clone_dir).iterdir())}")
            raise RuntimeError(f"local-business template not found in cloned repo. Checked paths: {[str(p) for p in possible_template_paths]}")
            
    except subprocess.CalledProcessError as e:
        print(f"[DEPLOY] Failed to clone template repo: {e.stderr}")
        raise RuntimeError(f"Failed to clone template repository: {e.stderr}")
    
    if not template_dir:
        raise RuntimeError("local-business template not found")
    
    # Create working directory
    work_dir = tempfile.mkdtemp(prefix=f"deploy_work_{site_url}_")
    shutil.copytree(template_dir, work_dir, dirs_exist_ok=True)
    
    # Remove git directories
    for git_dir in [".git", ".github"]:
        git_path = Path(work_dir) / git_dir
        if git_path.exists():
            shutil.rmtree(git_path, ignore_errors=True)
    
    # Inject site.json (with sanitization)
    if inputs["site_json"]:
        site_json_path = Path(work_dir) / "data" / "site.json"
        site_json_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Transform flat site.json structure to nested component structure
        try:
            transformed_data = transform_site_json_structure(inputs["site_json"])
            print(f"[DEPLOY] ✅ Site.json structure transformed for components")
        except Exception as e:
            print(f"[DEPLOY] ⚠️  Structure transformation failed, using original: {e}")
            transformed_data = inputs["site_json"]
        
        # Sanitize the site.json data for JSX compliance
        try:
            sanitized_data = sanitize_site_json(transformed_data)
            print(f"[DEPLOY] ✅ Site.json sanitized for JSX compliance")
        except Exception as e:
            print(f"[DEPLOY] ⚠️  Sanitization failed, using original data: {e}")
            sanitized_data = transformed_data
        
        # Update image URLs to point to local files instead of Supabase URLs
        try:
            for image in inputs["images"]:
                image_name = image["name"]
                
                # Update logoUrl if it matches this image
                if sanitized_data.get("logoUrl") and image_name in sanitized_data["logoUrl"]:
                    sanitized_data["logoUrl"] = f"/{image_name}"
                    print(f"[DEPLOY] Updated logoUrl to local path: /{image_name}")
                
                # Update heroImageUrl if it matches this image  
                if sanitized_data.get("heroImageUrl") and image_name in sanitized_data["heroImageUrl"]:
                    sanitized_data["heroImageUrl"] = f"/{image_name}"
                    print(f"[DEPLOY] Updated heroImageUrl to local path: /{image_name}")
                
                # Update service images
                if "services" in sanitized_data:
                    for service in sanitized_data["services"]:
                        if service.get("imageUrl") and image_name in service["imageUrl"]:
                            service["imageUrl"] = f"/{image_name}"
                            print(f"[DEPLOY] Updated service imageUrl to local path: /{image_name}")
                
                # Update testimonial images
                if "testimonials" in sanitized_data:
                    for testimonial in sanitized_data["testimonials"]:
                        if testimonial.get("authorImageUrl") and image_name in testimonial["authorImageUrl"]:
                            testimonial["authorImageUrl"] = f"/{image_name}"
                            print(f"[DEPLOY] Updated testimonial authorImageUrl to local path: /{image_name}")
                
                # Update gallery images
                if "galleryImageUrls" in sanitized_data and isinstance(sanitized_data["galleryImageUrls"], list):
                    for i, gallery_url in enumerate(sanitized_data["galleryImageUrls"]):
                        if gallery_url and image_name in gallery_url:
                            sanitized_data["galleryImageUrls"][i] = f"/{image_name}"
                            print(f"[DEPLOY] Updated gallery image to local path: /{image_name}")
                
                # Update any other imageUrl fields that might exist
                def update_nested_image_urls(obj, path=""):
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            current_path = f"{path}.{key}" if path else key
                            if key.endswith("ImageUrl") and isinstance(value, str) and image_name in value:
                                obj[key] = f"/{image_name}"
                                print(f"[DEPLOY] Updated {current_path} to local path: /{image_name}")
                            elif isinstance(value, (dict, list)):
                                update_nested_image_urls(value, current_path)
                    elif isinstance(obj, list):
                        for i, item in enumerate(obj):
                            current_path = f"{path}[{i}]"
                            if isinstance(item, (dict, list)):
                                update_nested_image_urls(item, current_path)
                
                # Apply nested update for any missed imageUrl fields
                update_nested_image_urls(sanitized_data)
                
        except Exception as e:
            print(f"[DEPLOY] ⚠️  Failed to update image URLs: {e}")
        
        with open(site_json_path, 'w') as f:
            json.dump(sanitized_data, f, indent=2)
        print(f"[DEPLOY] Injected site.json to {site_json_path}")
    
    # Inject backlinks.json if present
    if inputs["backlinks_json"]:
        backlinks_path = Path(work_dir) / "data" / "backlinks.json"
        with open(backlinks_path, 'w') as f:
            json.dump(inputs["backlinks_json"], f, indent=2)
        print(f"[DEPLOY] Injected backlinks.json to {backlinks_path}")
    
    # Copy images to public directory
    if inputs["images"]:
        public_dir = Path(work_dir) / "public"
        public_dir.mkdir(exist_ok=True)
        
        for image in inputs["images"]:
            src_path = Path(image["local_path"])
            dst_path = public_dir / image["name"]
            if src_path.exists():
                shutil.copy2(src_path, dst_path)
                print(f"[DEPLOY] Copied image {image['name']} to public/")
    
    return work_dir


async def handle_first_time_deployment(site_url: str, site_id: str, user_id: str) -> None:
    """Handle first-time deployment: domain purchase, geocoding, site record updates"""
    try:
        # 1. Purchase domain via Namecheap
        print(f"[DEPLOY] Purchasing domain: {site_url}")
        if NamecheapClient:
            namecheap = NamecheapClient()
            purchase_result = await asyncio.get_event_loop().run_in_executor(
                None, namecheap.purchase_domain, site_url, 1, True, None
            )
            print(f"[DEPLOY] Domain purchase result: {purchase_result.get('success', False)}")
        else:
            print("[DEPLOY] Warning: NamecheapClient not available, skipping domain purchase")
        
        # 2. Get geocoding for the site (if location info available)
        try:
            # This would need site location info from site.json
            # coordinates = await get_coordinates_for_site(site_url)
            print("[DEPLOY] Geocoding skipped (implement if needed)")
        except Exception:
            print("[DEPLOY] Geocoding failed, continuing...")
        
        # 3. Update site record to mark as having domain
        print(f"[DEPLOY] Updating site record for first-time deployment")
        
    except Exception as e:
        print(f"[DEPLOY] Warning: First-time setup partially failed: {e}")
        # Don't fail the entire deployment for these issues


async def push_to_github(work_dir: str, repo_name: str) -> None:
    """Initialize git and push to GitHub repository"""
    def _git_operations():
        os.chdir(work_dir)
        
        # Git setup
        subprocess.run(["git", "init"], check=True)
        subprocess.run(["git", "config", "user.name", GITHUB_USERNAME], check=True)
        subprocess.run(["git", "config", "user.email", f"{GITHUB_USERNAME}@users.noreply.github.com"], check=True)
        subprocess.run(["git", "config", "http.postBuffer", "524288000"], check=True)
        
        # Create .gitignore if missing
        gitignore_path = Path(work_dir) / ".gitignore"
        if not gitignore_path.exists():
            gitignore_content = """node_modules/
.env
.env.local
.env.development.local
.env.test.local
.env.production.local
/build
/out
/dist
.DS_Store
.vscode/
.idea/
*.log
"""
            with open(gitignore_path, 'w') as f:
                f.write(gitignore_content)
        
        # Add, commit, and push
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Initial deployment commit"], check=True)
        
        # Push to GitHub with authentication
        auth_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
        subprocess.run(["git", "remote", "add", "origin", auth_url], check=True)
        subprocess.run(["git", "branch", "-M", "main"], check=True)
        subprocess.run(["git", "push", "-u", "origin", "main", "--force"], check=True)
    
    await asyncio.get_event_loop().run_in_executor(None, _git_operations)


async def configure_custom_domain(site_url: str, project_name: str, cloudflare_api_token: str, cloudflare_account_id: str) -> None:
    """Configure custom domain with Cloudflare"""
    try:
        # 1. Add domain to Cloudflare and migrate DNS from Namecheap
        print(f"[DEPLOY] Adding domain {site_url} to Cloudflare...")
        domain_result = await asyncio.get_event_loop().run_in_executor(
            None, add_domain_to_cloudflare_with_migration,
            site_url, cloudflare_api_token, cloudflare_account_id, CLIENT_IP
        )
        print(f"[DEPLOY] Domain added to Cloudflare: {domain_result.get('nameserver_updated', False)}")
        
        # 2. Add custom domain to Cloudflare Pages project
        print(f"[DEPLOY] Adding custom domain to Pages project...")
        pages_domain_result = await asyncio.get_event_loop().run_in_executor(
            None, add_custom_domain_to_pages_project,
            cloudflare_api_token, cloudflare_account_id, project_name, site_url
        )
        print(f"[DEPLOY] Custom domain configured: {pages_domain_result.get('domain', site_url)}")
        
    except Exception as e:
        print(f"[DEPLOY] Warning: Custom domain configuration failed: {e}")
        # Don't fail deployment for domain issues


async def trigger_deployment(work_dir: str) -> None:
    """Trigger Cloudflare Pages deployment with empty commit"""
    def _trigger_commit():
        os.chdir(work_dir)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "chore: trigger deploy"], check=True)
        subprocess.run(["git", "push"], check=True)
    
    await asyncio.get_event_loop().run_in_executor(None, _trigger_commit)


async def update_site_deployment_success(site_id: str, final_url: str) -> None:
    """Update site record with successful deployment"""
    try:
        supabase = SupabaseClient()
        supabase.client.table("vm_sites").update({
            "deployment_status": "succeeded",
            "is_deployed": True,
            "deployed_at": datetime.utcnow().isoformat(),
            "live_url": final_url,
            "deployment_error": None,
        }).eq("id", site_id).execute()
    except Exception as e:
        print(f"[DEPLOY] Warning: Failed to update site record: {e}")


def cleanup_directories(dirs: List[str]) -> None:
    """Clean up temporary directories"""
    for dir_path in dirs:
        if dir_path and Path(dir_path).exists():
            try:
                shutil.rmtree(dir_path)
                print(f"[DEPLOY] Cleaned up {dir_path}")
            except Exception as e:
                print(f"[DEPLOY] Warning: Failed to cleanup {dir_path}: {e}")


async def schedule_deploy(site_id: str, reason: Optional[str] = None) -> None:
    task = asyncio.create_task(deploy_task(DeployRequest(site_id=site_id, reason=reason)))
    track_task(task)


async def delete_task(payload: DeleteRequest) -> None:
    site = await db_get_site(payload.site_id)
    if not site:
        raise HTTPException(status_code=404, detail="site not found")

    # Cancel Stripe subscription (we cancel whole subscription regardless of scope, to keep items coupled)
    try:
        sub = await db_get_active_subscription(payload.site_id)
        if sub and sub.get("stripe_subscription_id"):
            await stripe_cancel_subscription(
                sub["stripe_subscription_id"],
                immediate=payload.delete_immediately,
                idempotency_key=payload.idempotency_key,
            )
    except Exception as exc:  # noqa: BLE001
        # Log and continue; webhooks remain source of truth
        _ = exc

    # Registrar domain cancel (optional)
    if payload.cancel_domain:
        try:
            await registrar_cancel_domain(site["site_url"])
        except Exception as exc:  # noqa: BLE001
            _ = exc

    # Infra teardown in background
    track_task(asyncio.create_task(teardown_github_repo(site)))
    track_task(asyncio.create_task(teardown_cloudflare_project(site)))

    # Soft delete site to release env slot immediately
    await db_soft_delete_site(payload.site_id)


async def poll_deployable_sites_loop() -> None:
    """Continuously poll a deploy queue or DB view and schedule deploys.

    Replace the body with querying public.vm_deployable_sites and de-duping by site_id.
    """
    while True:
        try:
            app_state.loop_counter += 1

            # Example: drain in-memory queue first
            pending: List[str] = []
            pending, app_state.pending_deploy_site_ids = (
                app_state.pending_deploy_site_ids,
                [],
            )
            for site_id in pending:
                await schedule_deploy(site_id, reason="queue")

            await asyncio.sleep(5)
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001
            await asyncio.sleep(5)


# ------------------------------
# FastAPI app with lifespan
# ------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop_task = asyncio.create_task(poll_deployable_sites_loop())
    track_task(loop_task)
    try:
        yield
    finally:
        loop_task.cancel()
        for t in list(background_tasks):
            t.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)


app = FastAPI(lifespan=lifespan)

# Add CORS middleware to allow requests from Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://vm-web-liard.vercel.app",  # Your production Vercel app
        "https://*.vercel.app",  # All Vercel preview deployments
        "http://localhost:3000",  # Local development
        "http://127.0.0.1:3000",  # Local development alternative
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.post("/research")
async def research_endpoint(payload: ResearchRequest) -> ResearchResponse:
    """Research a business and generate site.json using ClientBusinessResearcher"""
    try:
        # Run client research task directly (synchronously for immediate response)
        result = await client_research_task(payload)
        
        return ResearchResponse(
            success=result["success"],
            site_json=result.get("site_json"),
            business_info=result.get("business_info"),
            error=result.get("error"),
            upload_path=result.get("upload_path"),
            download_url=result.get("download_url")
        )
        
    except Exception as e:
        return ResearchResponse(
            success=False,
            error=str(e)
        )


@app.post("/deploy")
async def deploy_endpoint(payload: DeployRequest):
    task = asyncio.create_task(deploy_task(payload))
    track_task(task)
    return {"ok": True, "status": "processing", "site_id": payload.site_id}


@app.get("/status")
async def status_endpoint():
    # Check environment variables
    env_status = {}
    required_env_vars = [
        "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
        "GEMINI_API_KEY_1", "GITHUB_USERNAME", "GITHUB_TOKEN"
    ]
    
    for var in required_env_vars:
        if hasattr(config, var):
            value = getattr(config, var, None)
            env_status[var] = {
                "exists": bool(value),
                "length": len(value) if value else 0,
                "preview": value[:10] + "..." if value and len(value) > 10 else value[:10] if value else None
            }
        else:
            env_status[var] = {"exists": False, "length": 0, "preview": None}
    
    # Test Supabase connection
    supabase_test = {"available": False, "error": None}
    if SupabaseClient:
        try:
            test_client = SupabaseClient()
            supabase_test["available"] = True
        except Exception as e:
            supabase_test["error"] = str(e)
    
    return {
        "loop_counter": app_state.loop_counter,
        "active_tasks": len(background_tasks),
        "started_at": app_state.started_at.isoformat(),
        "business_import_error": BUSINESS_IMPORT_ERROR,
        "environment_variables": env_status,
        "supabase_client_available": SupabaseClient is not None,
        "supabase_connection_test": supabase_test,
    }


@app.post("/delete")
async def delete_endpoint(payload: DeleteRequest):
    task = asyncio.create_task(delete_task(payload))
    track_task(task)
    return {"ok": True, "status": "processing", "site_id": payload.site_id}


# ------------------------------
# Domain search endpoint
# ------------------------------

@app.post("/search-domains")
async def search_domains_endpoint(payload: DomainSearchRequest):
    if NamecheapClient is None:
        raise HTTPException(status_code=500, detail="Namecheap client not available on server")

    try:
        nc = NamecheapClient()
        raw_results: List[Dict[str, Any]] = nc.search_domains_with_prices(payload.query, payload.tlds)

        normalized: List[DomainSearchResult] = []
        for item in raw_results:
            raw = item.get("raw") or {}
            is_premium = False
            if isinstance(raw, dict):
                flag = raw.get("IsPremiumName") or raw.get("is_premium")
                if isinstance(flag, str):
                    is_premium = flag.lower() == "true"
                elif isinstance(flag, bool):
                    is_premium = flag

            normalized.append(
                DomainSearchResult(
                    domain=str(item.get("domain")),
                    available=bool(item.get("available")),
                    priceUsd=(item.get("purchase_price") if isinstance(item.get("purchase_price"), (int, float)) else None),
                    isPremium=is_premium,
                    purchase_currency=item.get("purchase_currency"),
                    renew_price=(item.get("renew_price") if isinstance(item.get("renew_price"), (int, float)) else None),
                    renew_currency=item.get("renew_currency"),
                )
            )

        return [r.model_dump() for r in normalized]
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/get-purchased-domains")
async def get_purchased_domains_endpoint(payload: GetPurchasedDomainsRequest):
    """Get purchased domains for admin users only"""
    if NamecheapClient is None:
        raise HTTPException(status_code=500, detail="Namecheap client not available on server")
    
    # Server-side admin check
    if payload.user_email not in ADMIN_USERS:
        raise HTTPException(status_code=403, detail="Access denied: Admin privileges required")
    
    try:
        nc = NamecheapClient()
        purchased_domains = nc.get_purchased_domains(search_term=payload.search_term)
        
        # Format the response to match the domain search structure
        formatted_domains = []
        for domain_info in purchased_domains:
            formatted_domains.append({
                "domain": domain_info.get("domain"),
                "available": False,  # These are purchased domains
                "priceUsd": 0,  # Already purchased
                "isPremium": False,
                "purchase_currency": "USD",
                "renew_price": None,
                "renew_currency": None,
                "isPurchased": True,  # Mark as purchased
                "expiration_date": domain_info.get("expiration_date"),
                "auto_renew": domain_info.get("auto_renew", False)
            })
        
        return formatted_domains
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Failed to fetch purchased domains: {str(exc)}")

