


from pprint import pprint
import requests
import json



api_token = "3ef53df7-e4c3-48c3-a128-490d8cd667de"
serp_zone = "serp_api1"






# class BrightDataMapsClient:
#     def __init__(
#         self,
#         ca_cert_path: str = "BrightData SSL certificate (port 33335).crt",
#         host: str = "brd.superproxy.io",
#         port: int = 33335,
#         username: str = "brd-customer-hl_6467129b-zone-serp_api1",
#         password: str = "168jew4d4jg8",
#         enhanced_mode: bool = False,
#     ):
#         self.ca_cert_path = ca_cert_path
#         self.host = host
#         self.port = port
#         self.username = username
#         self.password = password
#         self.enhanced_mode = enhanced_mode

#         self.proxy_url = f"http://{self.username}:{self.password}@{self.host}:{self.port}"
#         self.proxies = {
#             "http": self.proxy_url,
#             "https": self.proxy_url
#         }

#     def get_maps_place(self, fid: str):
#         # Build the Google Maps place data URL
#         target_url = f"https://www.google.com/maps/place/data=!3m1!4b1!4m2!3m1!1s{fid}?brd_json=1"
#         response = requests.get(
#             target_url,
#             proxies=self.proxies,
#             verify=self.ca_cert_path
#         )
#         response.raise_for_status()
#         data = response.json()
#         return data

# # Example usage:
# if __name__ == "__main__":
#     # Replace with your actual fid for the place you want
#     fid = "0x0:0x4547a353b1158112"
    
    
#     client = BrightDataMapsClient(
#         ca_cert_path="/Users/warren/dev/vending-machine/vm-py/BrightData SSL certificate (port 33335).crt"
#     )
#     data = client.get_maps_place(fid)
#     print(json.dumps(data, indent=2))

#     pprint(data)

#     # Extract hours and overview if available
#     hours = data.get("hours") or data.get("opening_hours")
#     overview = data.get("overview") or data.get("description") or data.get("about")
#     print("Hours:", hours)
#     print("Overview:", overview)


import asyncio
from google_review_fetcher import GoogleBusinessResearcher


async def test_maps_functionality():
    """Test the new maps functionality with proper async/await"""
    # business_name = "Professional HVAC Contractor"
    business_name = "Wendy Weebly HVAC"
    location = "San Mateo, CA"
    
    print(f"🔍 Testing maps functionality for: {business_name} in {location}")
    print("=" * 60)
    
    researcher = GoogleBusinessResearcher()
    
    # Step 1: Find business FID with info
    print(f"📍 Finding business FID...")
    fid_result = await researcher._find_business_fid_with_info(business_name, location)
    
    print(f"FID Result:")
    pprint(fid_result)
    
    # Step 2: Get maps data if FID was found
    if fid_result.get("fid"):
        fid = fid_result["fid"]
        print(f"\n🗺️ Fetching Google Maps data for FID: {fid}")
        maps_data = await researcher.get_maps_place_data(fid)
        
        if maps_data:
            print(f"\nMaps Data:")
            pprint(maps_data)
            
            # Extract key information
            hours = maps_data.get("hours") or maps_data.get("opening_hours")
            overview = maps_data.get("overview") or maps_data.get("description") or maps_data.get("about")
            
            print(f"\n📊 Key Information:")
            if hours:
                print(f"🕒 Hours: {hours}")
            if overview:
                print(f"📝 Overview: {overview[:200]}..." if len(str(overview)) > 200 else f"📝 Overview: {overview}")
        else:
            print(f"❌ Failed to fetch maps data")
    else:
        print(f"❌ No FID found for business")

# Run the async test
if __name__ == "__main__":
    asyncio.run(test_maps_functionality())




