import requests
import pprint

from config import BRIGHTDATA_API_KEY, BRIGHTDATA_API_ZONE


# Example: Google Maps CID
cid = '12033186157967875144'
url = f"https://www.google.com/maps?cid={cid}&brd_json=1"

print(f"URL: {url}")

payload = {
    "zone": BRIGHTDATA_API_ZONE,
    "url": url,
    "method": "GET",
    "format": "json"
}

headers = {
    "Authorization": f"Bearer {BRIGHTDATA_API_KEY}",
    "Content-Type": "application/json"
}

response = requests.post(
    "https://api.brightdata.com/request",
    json=payload,
    headers=headers
)

print("Response status code:", response.status_code)
print("Response text:", response.text)

data = response.json()
pprint.pprint(data)


# # Example Google Maps place_id (replace with your target place_id)
# place_id = "ChIJN1t_tDeuEmsRUsoyG83frY4"

# # Construct the Google Maps place details URL (no mobile emulation)
# url = f"https://www.google.com/maps/place/?q=place_id:{place_id}&brd_mobile=1&brd_json=1"

# payload = {
#     "zone": BRIGHTDATA_API_ZONE,
#     "url": url,
#     "method": "GET",
#     "format": "json"
# }

# headers = {
#     "Authorization": f"Bearer {BRIGHTDATA_API_KEY}",
#     "Content-Type": "application/json"
# }

# response = requests.post(
#     "https://api.brightdata.com/request",
#     json=payload,
#     headers=headers
# )

# print("Response status code:", response.status_code)
# print("Response text:", response.text)

# try:
#     data = response.json()
#     pprint.pprint(data)
# except Exception as e:
#     print("Failed to parse JSON response:", e)
#     print("Raw response:", response.text)
