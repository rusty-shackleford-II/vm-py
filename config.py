from decouple import config

# GitHub configuration
GITHUB_USERNAME = config("GITHUB_USERNAME")
GITHUB_TOKEN = config("GITHUB_TOKEN")

# Cloudflare configuration - now handled via slot-based credentials in app.py
# CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are no longer used from environment

REMOTE_TEMPLATE_REPO = config("REMOTE_TEMPLATE_REPO")

# Local repository path
LOCAL_REPO_PATH = config("LOCAL_REPO_PATH")

# Project name - now computed from slot in app.py
# PROJECT_NAME = config("PROJECT_NAME")  # No longer used

# Namecheap configuration
NAMECHEAP_API_USER = config("NAMECHEAP_API_USER")
NAMECHEAP_API_KEY = config("NAMECHEAP_API_KEY")
CLIENT_IP = config("CLIENT_IP")
# DOMAIN removed - now passed as parameter to deploy scripts
NAMECHEAP_USERNAME = config("NAMECHEAP_USERNAME")

# Supabase configuration
SUPABASE_ID = config("SUPABASE_ID")
SUPABASE_URL = config("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = config("SUPABASE_SERVICE_ROLE_KEY")

# Gemini API configuration
GEMINI_API_KEY_1 = config("GEMINI_API_KEY_1")
GEMINI_API_KEY_2 = config("GEMINI_API_KEY_2")
GEMINI_API_KEY_3 = config("GEMINI_API_KEY_3")
GEMINI_API_KEY_4 = config("GEMINI_API_KEY_4")
GEMINI_API_KEY_5 = config("GEMINI_API_KEY_5")
GEMINI_API_KEY_6 = config("GEMINI_API_KEY_6")
GEMINI_API_KEY_7 = config("GEMINI_API_KEY_7")
GEMINI_API_KEY_8 = config("GEMINI_API_KEY_8")
GEMINI_API_KEY_9 = config("GEMINI_API_KEY_9")

GOOGLE_MAPS_API_KEY = config("GOOGLE_MAPS_API_KEY")

SPACESHIP_API_KEY = config("SPACESHIP_API_KEY")
SPACESHIP_API_SECRET = config("SPACESHIP_API_SECRET")

# Optional: Default Namecheap contact details (used if not provided at call-time)
# Registrant
NC_REGISTRANT_FirstName = config("NC_REGISTRANT_FirstName", default="Warren")
NC_REGISTRANT_LastName = config("NC_REGISTRANT_LastName", default="Huffman")
NC_REGISTRANT_Address1 = config("NC_REGISTRANT_Address1", default="127 Robert E Lee")
NC_REGISTRANT_City = config("NC_REGISTRANT_City", default="Hunt")
NC_REGISTRANT_StateProvince = config("NC_REGISTRANT_StateProvince", default="TX")
NC_REGISTRANT_PostalCode = config("NC_REGISTRANT_PostalCode", default="78024")
NC_REGISTRANT_Country = config("NC_REGISTRANT_Country", default="US")
NC_REGISTRANT_Phone = config("NC_REGISTRANT_Phone", default="+1.8323981894")
NC_REGISTRANT_EmailAddress = config("NC_REGISTRANT_EmailAddress", default="warren.r.huffman@gmail.com")

# Admin (defaults mirror Registrant unless overridden)
NC_ADMIN_FirstName = config("NC_ADMIN_FirstName", default=NC_REGISTRANT_FirstName)
NC_ADMIN_LastName = config("NC_ADMIN_LastName", default=NC_REGISTRANT_LastName)
NC_ADMIN_Address1 = config("NC_ADMIN_Address1", default=NC_REGISTRANT_Address1)
NC_ADMIN_City = config("NC_ADMIN_City", default=NC_REGISTRANT_City)
NC_ADMIN_StateProvince = config("NC_ADMIN_StateProvince", default=NC_REGISTRANT_StateProvince)
NC_ADMIN_PostalCode = config("NC_ADMIN_PostalCode", default=NC_REGISTRANT_PostalCode)
NC_ADMIN_Country = config("NC_ADMIN_Country", default=NC_REGISTRANT_Country)
NC_ADMIN_Phone = config("NC_ADMIN_Phone", default=NC_REGISTRANT_Phone)
NC_ADMIN_EmailAddress = config("NC_ADMIN_EmailAddress", default=NC_REGISTRANT_EmailAddress)

# Tech (defaults mirror Registrant unless overridden)
NC_TECH_FirstName = config("NC_TECH_FirstName", default=NC_REGISTRANT_FirstName)
NC_TECH_LastName = config("NC_TECH_LastName", default=NC_REGISTRANT_LastName)
NC_TECH_Address1 = config("NC_TECH_Address1", default=NC_REGISTRANT_Address1)
NC_TECH_City = config("NC_TECH_City", default=NC_REGISTRANT_City)
NC_TECH_StateProvince = config("NC_TECH_StateProvince", default=NC_REGISTRANT_StateProvince)
NC_TECH_PostalCode = config("NC_TECH_PostalCode", default=NC_REGISTRANT_PostalCode)
NC_TECH_Country = config("NC_TECH_Country", default=NC_REGISTRANT_Country)
NC_TECH_Phone = config("NC_TECH_Phone", default=NC_REGISTRANT_Phone)
NC_TECH_EmailAddress = config("NC_TECH_EmailAddress", default=NC_REGISTRANT_EmailAddress)

# AuxBilling (defaults mirror Registrant unless overridden)
NC_AUX_FirstName = config("NC_AUX_FirstName", default=NC_REGISTRANT_FirstName)
NC_AUX_LastName = config("NC_AUX_LastName", default=NC_REGISTRANT_LastName)
NC_AUX_Address1 = config("NC_AUX_Address1", default=NC_REGISTRANT_Address1)
NC_AUX_City = config("NC_AUX_City", default=NC_REGISTRANT_City)
NC_AUX_StateProvince = config("NC_AUX_StateProvince", default=NC_REGISTRANT_StateProvince)
NC_AUX_PostalCode = config("NC_AUX_PostalCode", default=NC_REGISTRANT_PostalCode)
NC_AUX_Country = config("NC_AUX_Country", default=NC_REGISTRANT_Country)
NC_AUX_Phone = config("NC_AUX_Phone", default=NC_REGISTRANT_Phone)
NC_AUX_EmailAddress = config("NC_AUX_EmailAddress", default=NC_REGISTRANT_EmailAddress)