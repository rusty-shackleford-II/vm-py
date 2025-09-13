# import re
# import json
# import math
# import time
# import typing as t
# import requests
# from urllib.parse import urlparse, parse_qs, unquote
# from bs4 import BeautifulSoup

# # External config for Bright Data and Gemini
# from config import (
#     BRIGHTDATA_API_KEY, BRIGHTDATA_API_ZONE,
#     GEMINI_API_KEY_1, GEMINI_API_KEY_2, GEMINI_API_KEY_3, GEMINI_API_KEY_4, GEMINI_API_KEY_5,
#     GEMINI_API_KEY_6, GEMINI_API_KEY_7, GEMINI_API_KEY_8, GEMINI_API_KEY_9
# )

# # Gemini client for processing cleaned HTML
# from clients.gemini_client import GeminiClient


# # =========================
# # Global Settings / Logging
# # =========================

# DEBUG = False

# def dbg(msg: str) -> None:
#     if DEBUG:
#         print(f"[dbg] {msg}")


# # =========================
# # Safe JSON helpers
# # =========================

# def try_json(text: str) -> t.Optional[t.Any]:
#     try:
#         return json.loads(text)
#     except Exception:
#         return None


# def find_json_blocks(html: str, limit: int = 30) -> t.List[t.Any]:
#     """
#     Heuristically scan HTML/JS and extract real JSON blocks (arrays/objects).
#     Attempts to keep cost bounded and rejects tiny objects.
#     """
#     blocks: t.List[t.Any] = []
#     stack: t.List[str] = []
#     start: t.Optional[int] = None
#     n = len(html)

#     for i, ch in enumerate(html):
#         if ch in '{[':
#             stack.append(ch)
#             if len(stack) == 1:
#                 start = i
#         elif ch in '}]':
#             if stack:
#                 stack.pop()
#                 if not stack and start is not None:
#                     segment = html[start:i+1]
#                     start = None
#                     # quick reject tiny/low-value segments
#                     if segment.count(':') < 2 or len(segment) < 40:
#                         continue
#                     parsed = try_json(segment)
#                     if parsed is not None:
#                         blocks.append(parsed)
#                         if len(blocks) >= limit:
#                             break
#     return blocks


# # =========================
# # Normalization utilities
# # =========================

# def clean_phone(s: t.Optional[str]) -> t.Optional[str]:
#     if not s:
#         return None
#     s = s.strip()
#     # Preserve original if E.164 provided; otherwise normalize to digits
#     if s.startswith('+') and re.fullmatch(r'\+\d{7,}', s):
#         return s
#     digits = re.sub(r'\D+', '', s)
#     return digits if len(digits) >= 7 else s


# def clean_url(u: t.Optional[str]) -> t.Optional[str]:
#     if not u:
#         return None
#     u = unquote(u.strip())
#     # Strip Google redirect wrapper
#     if u.startswith('https://www.google.com/url?'):
#         q = parse_qs(urlparse(u).query)
#         u = q.get('q', [u])
#     # Filter out internal google links
#     if 'google.' in urlparse(u).netloc and 'maps' in u and 'cid=' not in u:
#         return None
#     return u


# def normalize_categories(raw: t.Union[str, t.List[t.Any], None]) -> t.Optional[t.List[str]]:
#     if not raw:
#         return None
#     if isinstance(raw, str):
#         return [raw]
#     if isinstance(raw, list):
#         out: t.List[str] = []
#         def add(v: t.Any) -> None:
#             if isinstance(v, str):
#                 out.append(v)
#             elif isinstance(v, list):
#                 for w in v:
#                     add(w)
#         add(raw)
#         # de-dup preserving order
#         seen = set()
#         uniq: t.List[str] = []
#         for x in out:
#             if x not in seen:
#                 seen.add(x)
#                 uniq.append(x)
#         return uniq or None
#     return None


# def fold_address(addr: t.Any) -> t.Optional[str]:
#     if not isinstance(addr, dict):
#         return addr if isinstance(addr, str) else None
#     parts = [
#         addr.get('streetAddress'),
#         addr.get('addressLocality'),
#         addr.get('addressRegion'),
#         addr.get('postalCode'),
#         addr.get('addressCountry'),
#     ]
#     merged = ', '.join([p for p in parts if p])
#     return merged or None


# # =========================
# # JSON-LD extraction
# # =========================

# def extract_jsonld(soup: BeautifulSoup) -> t.List[dict]:
#     items: t.List[dict] = []
#     for tag in soup.find_all('script', attrs={'type': re.compile('json', re.I)}):
#         txt = tag.string or tag.text or ''
#         if not txt.strip():
#             continue
#         parsed = try_json(txt)
#         if not parsed:
#             continue
#         # Flatten possible arrays
#         arr = parsed if isinstance(parsed, list) else [parsed]
#         for obj in arr:
#             if isinstance(obj, dict) and obj.get('@type'):
#                 # Accept known local business types
#                 tset = obj.get('@type')
#                 if isinstance(tset, str):
#                     tset = [tset]
#                 tset = set(tset or [])
#                 if tset & {'Place','LocalBusiness','Organization','Store','Electrician','Plumber'}:
#                     items.append(obj)
#     return items


# def normalize_from_jsonld(items: t.List[dict]) -> dict:
#     """
#     Choose the richest JSON-LD block and normalize fields.
#     """
#     out: dict = {}
#     if not items:
#         return out
#     # pick largest by serialized length
#     j = max(items, key=lambda x: len(json.dumps(x)))
#     out['name'] = j.get('name')
#     out['description'] = j.get('description')

#     addr = j.get('address')
#     out['address'] = fold_address(addr)
#     out['address_raw'] = addr if isinstance(addr, dict) else None

#     out['telephone'] = clean_phone(j.get('telephone'))
#     out['website'] = clean_url(j.get('url') or (j.get('sameAs') if isinstance(j.get('sameAs'), list) and j.get('sameAs') else None))

#     geo = j.get('geo') or {}
#     if isinstance(geo, dict):
#         out['latitude'] = geo.get('latitude')
#         out['longitude'] = geo.get('longitude')

#     out['hours'] = j.get('openingHoursSpecification')

#     ar = j.get('aggregateRating') or {}
#     if isinstance(ar, dict):
#         out['rating'] = ar.get('ratingValue')
#         out['review_count'] = ar.get('reviewCount') or ar.get('ratingCount')

#     out['categories'] = j.get('@type')
#     return out


# # =========================
# # APP_INITIALIZATION_STATE parsing
# # =========================
# # Strategy:
# # 1) Find window.APP_INITIALIZATION_STATE = [...]
# # 2) If not found, scan for large JSON arrays and search within for plausible place tuples
# # 3) Walk recursively to pull known shapes: phone, website, address lines, lat/lng, name, categories, rating, hours
# # Ref: StackOverflow notes on parsing APP_INITIALIZATION_STATE [2]

# APP_INIT_RE = re.compile(r'window\.APP_INITIALIZATION_STATE\s*=\s*(\[[\s\S]*?\]);')

# def extract_app_init(html: str) -> t.List[t.Any]:
#     m = APP_INIT_RE.search(html)
#     if not m:
#         return []
#     arr = try_json(m.group(1))
#     return arr if isinstance(arr, list) else []


# def walk_place_fields(root: t.Any) -> dict:
#     """
#     Walk nested lists/dicts for common fields. Conservative and does not overwrite once set.
#     """
#     place: dict = {}

#     def put(k: str, v: t.Any) -> None:
#         if v in (None, '', [], {}):
#             return
#         if k not in place or place[k] in (None, '', [], {}):
#             place[k] = v

#     def is_latlng_pair(x: t.Any) -> bool:
#         return (
#             isinstance(x, list) and len(x) == 2 and
#             all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in x) and
#             -90 <= x[0] <= 90 and -180 <= x[1] <= 180
#         )

#     def walk(x: t.Any) -> None:
#         if isinstance(x, dict):
#             # Common dict keys
#             for k in ('name', 'formatted_address', 'address', 'formattedPhoneNumber', 'phone', 'website', 'url', 'rating', 'userRatingCount', 'categories', 'hours'):
#                 if k in x:
#                     val = x[k]
#                     if k in ('url', 'website'):
#                         put('website', clean_url(val))
#                     elif k in ('formattedPhoneNumber', 'phone'):
#                         put('phone', val)
#                     elif k in ('formatted_address', 'address'):
#                         put('address', val if isinstance(val, str) else None)
#                     elif k == 'userRatingCount':
#                         put('review_count', val)
#                     else:
#                         put(k, val)
#             for v in x.values():
#                 walk(v)
#         elif isinstance(x, list):
#             # website candidates among strings
#             urls = [v for v in x if isinstance(v, str) and v.startswith(('http://','https://'))]
#             for u in urls:
#                 u2 = clean_url(u)
#                 if u2:
#                     put('website', u2)

#             # phone-like strings
#             for v in x:
#                 if isinstance(v, str) and re.search(r'\(\d{3}\)\s*\d', v):
#                     put('phone', v)

#             # address-like sequences of strings (street, city, zip)
#             if len(x) >= 2 and all(isinstance(v, str) for v in x[:2]):
#                 # Heuristic: line 0 looks like a street number, line 1 has city/state
#                 if re.search(r'\d', x[0]) and (',' in x[1] or re.search(r'[A-Z]{2}\s*\d{5}', x[1])):
#                     put('address', ', '.join([v for v in x if isinstance(v, str)]))

#             # lat/lng pair
#             if is_latlng_pair(x):
#                 put('latitude', x[0])
#                 put('longitude', x[1])

#             # name as single string in a near-tuple
#             if len(x) <= 6 and any(isinstance(v, str) for v in x):
#                 for v in x:
#                     if isinstance(v, str) and len(v) <= 120 and 'http' not in v and not v.startswith('0x'):
#                         # Do not override if already set
#                         if 'name' not in place and re.search(r'[A-Za-z]', v):
#                             put('name', v)

#             for v in x:
#                 walk(v)

#     walk(root)
#     return place


# def extract_place_from_payloads(html: str) -> dict:
#     # Prefer the explicit APP_INITIALIZATION_STATE
#     app = extract_app_init(html)
#     candidate_roots: t.List[t.Any] = []
#     if app:
#         candidate_roots.append(app)
#     else:
#         # fallback: scan other large JSON blocks
#         candidate_roots.extend(find_json_blocks(html, limit=20))

#     merged: dict = {}
#     for root in candidate_roots:
#         fields = walk_place_fields(root)
#         for k, v in fields.items():
#             if k not in merged or merged[k] in (None, '', [], {}):
#                 merged[k] = v

#     # Normalize location types
#     if 'latitude' in merged and 'longitude' in merged:
#         try:
#             merged['latitude'] = float(merged['latitude'])
#             merged['longitude'] = float(merged['longitude'])
#         except Exception:
#             pass

#     # Normalize phone
#     if merged.get('phone'):
#         merged['phone'] = merged['phone'].strip()

#     return merged


# # =========================
# # Hours extraction helpers
# # =========================

# def choose_hours(jsonld_hours: t.Any, payload_hours: t.Any) -> t.Any:
#     """
#     Prefer structured JSON-LD openingHoursSpecification if present, else use payload hint.
#     """
#     if jsonld_hours:
#         return jsonld_hours
#     return payload_hours


# # =========================
# # Meta tag extraction
# # =========================

# def extract_meta(soup: BeautifulSoup) -> dict:
#     def get_meta(name: t.Optional[str] = None, prop: t.Optional[str] = None) -> t.Optional[str]:
#         if name:
#             tag = soup.find('meta', attrs={'name': name})
#         else:
#             tag = soup.find('meta', attrs={'property': prop})
#         return tag['content'].strip() if tag and tag.has_attr('content') else None

#     return {
#         'og:title': get_meta(prop='og:title'),
#         'og:description': get_meta(prop='og:description'),
#         'og:image': get_meta(prop='og:image'),
#         'description': get_meta(name='Description') or get_meta(name='description'),
#         'twitter:card': get_meta(name='twitter:card'),
#     }


# # =========================
# # Services / Offerings extraction (heuristic but scoped)
# # =========================
# # Approach: locate category clusters in payload where each category is followed by an array
# # of arrays of service-name strings, which is how Maps embeds service menus for plumbers.
# # We avoid broad regexes; instead, search JSON blocks for ["Plumber"], ["Electrician"], etc.

# COMMON_SERVICE_CATEGORIES = {
#     'Plumber','Drainage Service','Electrician',
#     'Hot Water System Supplier','Plumbing Supply Store',
#     'Electric vehicle charging station contractor','Septic System Service'
# }

# def extract_services_from_blocks(html: str) -> t.List[str]:
#     services: t.Set[str] = set()

#     # Parse top JSON blocks and look for category -> nested services
#     blocks = find_json_blocks(html, limit=25)
#     cat_lower = {c.lower() for c in COMMON_SERVICE_CATEGORIES}

#     def harvest(obj: t.Any) -> None:
#         # Target shapes like: [ ["Plumber"], [ [[["Drain cleaning","..."]], ...]] ]
#         if not isinstance(obj, list):
#             return
#         # walk list and detect a category string item then collect following nested strings
#         for i, v in enumerate(obj):
#             if isinstance(v, list) and len(v) == 1 and isinstance(v, str):
#                 label = v.strip()
#                 if label.lower() in cat_lower:
#                     # scan forward for nested arrays with service names
#                     for j in range(i+1, min(i+6, len(obj))):
#                         subtree = obj[j]
#                         # recursively collect strings that look like service titles
#                         def collect(x: t.Any) -> None:
#                             if isinstance(x, str):
#                                 s = x.strip()
#                                 # Keep concise service-like titles
#                                 if 2 <= len(s) <= 80 and any(
#                                     kw in s.lower() for kw in [
#                                         'repair','installation','install','replace',
#                                         'cleaning','drain','sewer','leak','water heater',
#                                         'toilet','faucet','gas','backflow','trenchless',
#                                         'ev charger','panel','electrical','septic'
#                                     ]
#                                 ):
#                                     services.add(s)
#                             elif isinstance(x, list):
#                                 for y in x:
#                                     collect(y)
#                             elif isinstance(x, dict):
#                                 for y in x.values():
#                                     collect(y)
#                         collect(subtree)

#     for b in blocks:
#         harvest(b)

#     # Return sorted unique services
#     out = sorted(services)
#     # lightly post-filter: remove full sentences from marketing blurbs
#     pruned: t.List[str] = []
#     for s in out:
#         if len(s.split()) <= 12:
#             pruned.append(s)
#     return pruned


# # =========================
# # Main build/merge
# # =========================

# def merge_place(html: str) -> dict:
#     soup = BeautifulSoup(html, 'html.parser')

#     meta = extract_meta(soup)
#     jsonld = extract_jsonld(soup)
#     from_ld = normalize_from_jsonld(jsonld)
#     from_payload = extract_place_from_payloads(html)

#     result: dict = {}

#     # Name / description
#     result['name'] = next((x for x in [
#         from_ld.get('name'),
#         from_payload.get('name'),
#         meta.get('og:title'),
#     ] if x), None)

#     result['description'] = next((x for x in [
#         from_ld.get('description'),
#         meta.get('og:description'),
#         meta.get('description'),
#     ] if x), None)

#     # Address
#     result['address'] = next((x for x in [
#         from_payload.get('address'),
#         from_ld.get('address'),
#         meta.get('og:title') if meta.get('og:title') and ' · ' in meta['og:title'] else None,
#     ] if x), None)

#     # Geo
#     result['latitude'] = from_payload.get('latitude') or from_ld.get('latitude')
#     result['longitude'] = from_payload.get('longitude') or from_ld.get('longitude')

#     # Website
#     result['website'] = clean_url(from_payload.get('website') or from_ld.get('website'))

#     # Phone
#     result['phone'] = from_payload.get('phone') or from_ld.get('telephone')
#     result['phone_digits'] = clean_phone(result['phone'])

#     # Ratings
#     result['rating'] = from_payload.get('rating') or from_ld.get('rating')
#     result['review_count'] = from_payload.get('review_count') or from_ld.get('review_count')

#     # Categories
#     result['categories'] = normalize_categories(from_payload.get('categories') or from_ld.get('categories'))

#     # Image
#     result['image'] = meta.get('og:image')

#     # Hours (prefer JSON-LD spec)
#     result['hours'] = choose_hours(from_ld.get('hours'), from_payload.get('hours'))

#     # Services (heuristic from payload blocks)
#     result['services'] = extract_services_from_blocks(html)

#     return result


# # =========================
# # Bright Data fetch
# # =========================
# # Reference guide on scraping Maps via 3rd-party API and avoiding DOM-only scraping pitfalls. [4][2]

# def get_maps_html_from_brightdata(cid: str, *, timeout: int = 60) -> t.Optional[str]:
#     url = f"https://www.google.com/maps?cid={cid}"
#     payload = {
#         "zone": BRIGHTDATA_API_ZONE,
#         "url": url,
#         "method": "GET",
#         "format": "json",
#     }
#     headers = {
#         "Authorization": f"Bearer {BRIGHTDATA_API_KEY}",
#         "Content-Type": "application/json",
#     }

#     resp = requests.post("https://api.brightdata.com/request", json=payload, headers=headers, timeout=timeout)
#     dbg(f"BrightData {resp.status_code} for {url}")
#     if resp.status_code != 200:
#         return None

#     try:
#         data = resp.json()
#     except Exception:
#         return None

#     # common fields where body/html content appears
#     for key in ('body', 'html', 'content', 'response', 'data'):
#         if key in data and isinstance(data[key], str) and '<html' in data[key].lower():
#             return data[key]

#     # Some responses embed nested object
#     for k, v in data.items():
#         if isinstance(v, dict):
#             for kk in ('body', 'html', 'content'):
#                 if kk in v and isinstance(v[kk], str) and '<html' in v[kk].lower():
#                     return v[kk]
#     return None


# # =========================
# # Public API
# # =========================

# def parse_google_maps_place_html(html_text: str) -> dict:
#     """
#     Parse a Google Maps Place HTML (full HTML string) and return normalized fields.
#     """
#     return merge_place(html_text)


# def fetch_and_parse_by_cid(cid: str) -> t.Optional[dict]:
#     """
#     Convenience: fetch via Bright Data by CID and parse the place.
#     """
#     html = get_maps_html_from_brightdata(cid)
#     if not html:
#         return None
#     return parse_google_maps_place_html(html)


# # =========================
# # HTML Cleaning utilities
# # =========================

# def clean_html_content(html_text: str, max_word_length: int = 25) -> str:
#     """
#     Clean HTML content by:
#     1. Removing substrings longer than max_word_length chars with no spaces
#     2. Removing words with 4 consecutive consonants
#     3. Removing words containing web/code-related substrings
#     4. Removing all instances of the word 'null'
#     5. Removing all non-alphanumeric characters (keeping spaces)
    
#     Args:
#         html_text: The HTML content to clean
#         max_word_length: Maximum length for tokens without spaces (default: 25)
#     """
#     if not html_text:
#         return ""
    
#     import re
    
#     # Define web/code-related substrings to filter out
#     web_code_substrings = [
#         # HTML/XML tags and structure
#         'doctype','</html','<html','</head','</body','</script','<script','</style','<style',
#         'noscript','meta ','head ','body ','html ','link ','title ',
        
#         # JavaScript keywords and syntax
#         'function(','function ','return ','var ','let ','const ','=>','typeof ','instanceof ',
#         'window','document','this.','new ','throw ','catch ','try ','if(','else ','for(',
#         'while(','class ','extends ','constructor','prototype','Promise','async ','await',
#         'RegExp','case ','break','switch','default','continue','delete','in ','of ','with',
#         'eval','parseInt','parseFloat','isNaN','parseInt','Boolean','Number','String','Array',
#         'Object','Date','Math','JSON','Error','TypeError','ReferenceError','SyntaxError',
#         'void 0','undefined','null','true','false','NaN','Infinity',
        
#         # CSS properties and values
#         'rgba(','px','fontfamily','fontstyle','fontweight','fontdisplay','fontsize',
#         'lineheight','letterspacing','texttransform','display ','whitespace','wordwrap',
#         'direction ','webkit','background','border','margin','padding','transform','animation',
#         'keyframes','flex','grid','position:','zindex','overflow','!important','cursor:',
#         'visibility','opacity','filter','box-shadow','text-shadow','border-radius',
#         'min-width','max-width','min-height','max-height','top:','left:','right:','bottom:',
#         'float:','clear:','vertical-align','text-align','text-decoration','text-indent',
#         'font-variant','font-stretch','line-height','word-spacing','word-break','word-wrap',
#         'text-overflow','text-rendering','color:','background-color','border-color',
#         'outline:','outline-color','outline-width','outline-style','list-style','content:',
        
#         # Font and Unicode related (removed specific Unicode ranges - handled by regex)
#         'unicoderange','formatwoff2','formatwoff','fonttrue','fontotf','fontttf','fonteot',
#         'cyrillicext','cyrillic','greekext','greek','vietnamese','latinext','latin','hebrew',
        
#         # Google-specific identifiers and classes
#         'gbUa','gbSd','gbMd','gb ','gb0','gb1','gb2','gb3','gbjb','gbkb','gbpb','gbsb',
#         'gbtb','gbvb','gbBd','gbub','gbe','gb2a','gbrb','gbQd','gbtd','gbCd','gbId',
#         'gbVd','gb1d','gb2d','gbFa','gbBd','gboc','gbWa','gbH','gbBgbJ','gbBhovergbJ',
#         'gbAdgbBd','gbndgbod','gbXgbF','gbpd','gbOd','gbgd','agbU','agbX','RTLLANGgbud',
#         'gbPhovergb1','gbPfocusgb1','gbzgbpb','gbrbgbsb','forcedcolorsactive',
#         'hl4GXb','XvQR9b','wSgKnf','keynavmodeoff','highres','dpush','hkdelete',
        
#         # Google branding and services
#         'Google Maps','Google LLC','Google Products','Google Sans','Product Sans','Roboto',
#         'Google Symbols','Enable JavaScript','Sign in','Google apps','gclid','DoubleClick',
#         'gtag','analytics','adservice','cookie','consent','Google.com','maps.google.com',
#         'Closure Library Authors','All rights reserved',
        
#         # Web development attributes and properties
#         'aria','role=','viewbox','svg','path d=','tabindex','target=','onclick','onload',
#         'contextmenu','keypress','wheel','rightclick','mousedown','mouseup','keyup',
#         'drawImage','canvas','Image','viewBox','stroke','fill:','d=','path ','rect ',
#         'circle ','focusable','contenteditable','draggable','dropzone','hidden','spellcheck',
#         'translate','dir=','lang=','class=','id=','style=','data-','href=','src=','alt=',
#         'title=','width=','height=','loading=','crossorigin','integrity','referrerpolicy',
        
#         # Meta tags and SEO
#         'og:image','twitter:card','og:title','og:site_name','og:description','og:url',
#         'og:type','twitter:title','twitter:description','twitter:image','twitter:site',
#         'notranslate','viewport','referrer','manifest','canonical','hreflang','robots',
#         'description','keywords','author','generator','theme-color','msapplication',
        
#         # Time and measurement units
#         'min0','min2','min090','min0180','min036','hr0','hr072','hr0108','hr0144','hr0216',
#         'AM5','Opens 7 AM','24 24 24','22s092','22zM','c110','209','092',
        
#         # Encoded characters and escape sequences
#         'u003d','u0026','u003c','u003e','\u003d','\u0026','\u003c','\u003e','&amp;',
#         '&lt;','&gt;','&quot;','&#39;','&nbsp;','&copy;','&reg;','&trade;',
        
#         # Error messages and debugging
#         'Cannot find global','Symbol is not a constructor','The HTMLImageElement provided',
#         'TypeError','ReferenceError','SyntaxError','Error:','Warning:','Debug:','Console:',
#         'Failed to','Unable to','Could not','Permission denied','Access denied','404',
#         'Not Found','Internal Server Error','Bad Request','Unauthorized','Forbidden',
#         'Service Unavailable','Gateway Timeout','Network Error','Connection refused',
#         'Matching codeProgram','storage is available','broken enough','Program Filesat',
#         'read property mute','access dead','ErrorStringb','Haenumreturn','Haint32return',
#         'babvoid','acase numberreturn','booleanreturn','a10case','ajreturnreturn',
#         'khelse','01bvar','scconst','jbthiswaareturn','Kthis3avar','0throw','gdKreturn',
#         'ireturn','hdRvar','ldmdvar','adjdnew','Zcvar','Xcqdapisdnvar','aibreturn',
#         'aibthrow','atryconst','aithrow','Errorxelse','UdLcabvoid','anew typeof',
#         'Win64 x64','rv600','Gecko20100101','NT 62','Microsoft','EdgeJEdg','Opera',
#         'FirefoxJFx','iOS','OPRbreak','bEdgbreak','aSthisavoid','0void','Ubreturn',
#         'strictvar','cthrow','nullish','rabvar','220406case','220407defaultreturn',
#         'Jareturn','Kreturn','Lreturn','K1JOpera','Mreturn','Oreturn','KIMicrosoft',
#         'Preturn','JFirefox','Qreturn','paavar','qaavar','instanceof','wvar',
        
#         # Google Maps UI elements
#         'Directions','Nearby','Save','Send to phone','Share','Open now','Closed',
#         'Suggest an edit','Own this business','Add missing','Questions & answers',
#         'Reviews','Write a review','More info','Call','Website','Menu','Order online',
#         'Reserve','Book','Claim this business','Update info','Report a problem',
#         'Street View','Satellite','Traffic','Transit','Bicycling','Walking',
#         'Driving directions','Public transport','Your location','Search nearby',
#         'Filter','Sort by','Most relevant','Highest rated','Most reviews',
#         'Price range','Open hours','Accepts credit cards','Good for groups',
#         'Takes reservations','Delivery','Takeout','Wheelchair accessible',
#         'Good for kids','Dogs allowed','Outdoor seating','Wi-Fi','Parking',
        
#         # Advertisement and tracking related
#         'ad was shown','This ad is based','Your current search','map location youre browsing',
#         'estimation of your approximate','current search map location','Visit ad',
#         'Sponsored','Advertisement','Promoted','Featured','Ad','Ads by','AdChoices',
#         'Privacy Policy','Terms of Service','Cookie Policy','Data Policy',
#         'Personalized ads','Interest-based ads','Opt out','Manage preferences',
#         'tracking','analytics','measurement','conversion','remarketing','retargeting',
#         'pixel','beacon','impression','click-through','attribution','audience',
        
#         # Browser and system related
#         'sansserif','serif','monospace','cursive','fantasy','system-ui','ui-serif',
#         'ui-sans-serif','ui-monospace','ui-rounded','webkit','moz','ms','o',
#         'Chrome','Firefox','Safari','Edge','Internet Explorer','Opera','mobile',
#         'tablet','desktop','android','ios','windows','mac','linux','touch',
#         'mouse','keyboard','screen','print','speech','braille','handheld','projection',
#         'tv','tty','embossed','all','orientation','resolution','aspect-ratio',
#         'device-width','device-height','color-index','monochrome','scan','grid',
        
#         # Development and debugging terms
#         'localhost','127.0.0.1','dev','development','staging','test','testing',
#         'debug','debugger','console.log','console.error','console.warn','console.info',
#         'performance','profiler','inspector','devtools','source map','webpack',
#         'babel','typescript','eslint','prettier','jest','mocha','chai','cypress',
#         'selenium','puppeteer','playwright','node_modules','package.json','yarn.lock',
#         'npm','yarn','pnpm','bower','grunt','gulp','rollup','parcel','vite',
        
#         # Copyright and legal
#         'Copyright','©','All rights reserved','Licensed under','MIT License',
#         'Apache License','BSD License','GPL','LGPL','Creative Commons','CC BY',
#         'SPDX','Patent','Trademark','™','®','Terms of Use','End User License',
#         'Privacy','Legal','Disclaimer','Limitation of Liability','Indemnification',
#         'Governing Law','Dispute Resolution','Arbitration','Class Action Waiver',
        
#         # Generic technical terms
#         'API','SDK','CDN','DNS','HTTP','HTTPS','SSL','TLS','REST','GraphQL',
#         'JSON','XML','HTML','CSS','JavaScript','TypeScript','PHP','Python',
#         'Java','C++','C#','Ruby','Go','Rust','Swift','Kotlin','Scala','Perl',
#         'SQL','NoSQL','MongoDB','PostgreSQL','MySQL','Redis','Elasticsearch',
#         'AWS','Azure','GCP','Docker','Kubernetes','CI/CD','Git','GitHub','GitLab',
#         'Bitbucket','SVN','Mercurial','Jenkins','Travis','CircleCI','GitHub Actions'
#     ]
    
#     # Convert to lowercase for case-insensitive matching
#     web_code_lower = [s.lower() for s in web_code_substrings]
    
#     # Pattern to match 4 consecutive consonants
#     consonant_pattern = re.compile(r'[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]{4,}')
    
#     # Pattern to match Unicode range identifiers (U followed by uppercase letters/numbers, >4 chars)
#     unicode_range_pattern = re.compile(r'^U[A-Z0-9]{4,}$')
    
#     # Split into words/tokens to process individually
#     tokens = html_text.split()
#     filtered_tokens = []
    
#     for token in tokens:
#         # Remove tokens longer than max_word_length chars that don't contain spaces
#         if len(token) > max_word_length and ' ' not in token:
#             continue
            
#         # Remove words with 4 consecutive consonants
#         if consonant_pattern.search(token):
#             continue
            
#         # Remove Unicode range identifiers (U followed by uppercase letters/numbers, >4 chars)
#         if unicode_range_pattern.match(token):
#             continue
            
#         # Remove words containing web/code-related substrings
#         token_lower = token.lower()
#         should_skip = False
#         for substring in web_code_lower:
#             if substring in token_lower:
#                 should_skip = True
#                 break
        
#         if should_skip:
#             continue
            
#         filtered_tokens.append(token)
    
#     # Rejoin the filtered tokens
#     cleaned_text = ' '.join(filtered_tokens)
    
#     # Remove all instances of the word 'null' (case insensitive)
#     cleaned_text = re.sub(r'\bnull\b', '', cleaned_text, flags=re.IGNORECASE)
    
#     # Remove all non-alphanumeric characters (keeping spaces)
#     cleaned_text = re.sub(r'[^a-zA-Z0-9\s]', '', cleaned_text)
    
#     # Apply Unicode filter AGAIN after punctuation removal (in case CSS declarations got concatenated)
#     final_tokens = cleaned_text.split()
#     final_filtered = []
#     for token in final_tokens:
#         if not unicode_range_pattern.match(token):
#             final_filtered.append(token)
    
#     cleaned_text = ' '.join(final_filtered)
    
#     # Clean up multiple spaces
#     cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    
#     return cleaned_text


# # =========================
# # Gemini Processing for Structured Output
# # =========================

# def process_cleaned_html_with_gemini(cleaned_html: str, gemini_client: GeminiClient) -> str:
#     """
#     Process cleaned HTML content with Gemini to extract structured business information
#     and return it as XML format.
    
#     Args:
#         cleaned_html: The cleaned HTML content
#         gemini_client: Initialized Gemini client instance
        
#     Returns:
#         str: Structured XML containing business information
#     """
#     if not cleaned_html or not cleaned_html.strip():
#         return "<business><error>No cleaned content to process</error></business>"
    
#     prompt = f"""
# Please analyze the following cleaned Google Maps business data and extract structured information.
# Return the result as valid XML with the following structure:

# <business>
#     <name>Business Name</name>
#     <description>Business description if available</description>
#     <address>Full address</address>
#     <phone>Phone number</phone>
#     <website>Website URL</website>
#     <hours>
#         <day name="Monday">9:00 AM - 5:00 PM</day>
#         <day name="Tuesday">9:00 AM - 5:00 PM</day>
#         <!-- etc for other days, or "Closed" if closed -->
#     </hours>
#     <products_services>
#         <item>Service or product 1</item>
#         <item>Service or product 2</item>
#         <!-- etc -->
#     </products_services>
#     <rating>4.5</rating>
#     <review_count>123</review_count>
#     <categories>
#         <category>Primary business category</category>
#         <category>Secondary category</category>
#     </categories>
# </business>

# If any information is not available, use "Not available" as the value. 
# Only extract information that is clearly present in the data.
# Do not make up or infer information that isn't explicitly stated.

# Cleaned business data:
# {cleaned_html}
# """

#     try:
#         response = gemini_client.ask(prompt)
#         return response.strip()
#     except Exception as e:
#         error_xml = f"<business><error>Failed to process with Gemini: {str(e)}</error></business>"
#         return error_xml


# def process_maps_html_to_structured_xml(html_text: str, gemini_api_keys: list[str], max_word_length: int = 25) -> str:
#     """
#     Complete pipeline: clean HTML and process with Gemini to get structured XML output.
    
#     Args:
#         html_text: Raw HTML from Google Maps
#         gemini_api_keys: List of Gemini API keys for processing
#         max_word_length: Maximum word length for cleaning (default: 25)
        
#     Returns:
#         str: Structured XML containing business information
#     """
#     if not gemini_api_keys:
#         return "<business><error>No Gemini API keys provided</error></business>"
    
#     try:
#         # Initialize Gemini client
#         gemini_client = GeminiClient(gemini_api_keys)
        
#         # Clean the HTML
#         cleaned_html = clean_html_content(html_text, max_word_length)
        
#         # Process with Gemini
#         structured_xml = process_cleaned_html_with_gemini(cleaned_html, gemini_client)
        
#         return structured_xml
        
#     except Exception as e:
#         error_xml = f"<business><error>Pipeline failed: {str(e)}</error></business>"
#         return error_xml


# def generate_business_description(structured_xml: str, gemini_client: GeminiClient) -> str:
#     """
#     Generate a compelling business description using Gemini based on structured business data.
    
#     Args:
#         structured_xml: The structured XML containing business information
#         gemini_client: Initialized Gemini client instance
        
#     Returns:
#         str: A compelling business description
#     """
#     if not structured_xml or not structured_xml.strip():
#         return "Unable to generate description - no business data provided."
    
#     prompt = f"""
# Based on the following structured business information, write a compelling and professional business description that would be suitable for a website or business listing.

# The description should:
# - Be 2-3 paragraphs long
# - Highlight the key services and expertise
# - Be professional and engaging
# - Include location information naturally
# - Emphasize what makes this business unique or valuable to customers
# - Be written in third person
# - Sound natural and not overly promotional

# Business data:
# {structured_xml}

# Please write only the business description, no additional formatting or explanations.
# """

#     try:
#         response = gemini_client.ask(prompt)
#         return response.strip()
#     except Exception as e:
#         return f"Error generating business description: {str(e)}"


# def generate_business_description_from_html(html_text: str, gemini_api_keys: list[str], max_word_length: int = 25) -> str:
#     """
#     Complete pipeline: process HTML and generate a business description.
    
#     Args:
#         html_text: Raw HTML from Google Maps
#         gemini_api_keys: List of Gemini API keys for processing
#         max_word_length: Maximum word length for cleaning (default: 25)
        
#     Returns:
#         str: A compelling business description
#     """
#     if not gemini_api_keys:
#         return "Error: No Gemini API keys provided for description generation."
    
#     try:
#         # Get structured XML first
#         structured_xml = process_maps_html_to_structured_xml(html_text, gemini_api_keys, max_word_length)
        
#         # Initialize Gemini client
#         gemini_client = GeminiClient(gemini_api_keys)
        
#         # Generate description
#         description = generate_business_description(structured_xml, gemini_client)
        
#         return description
        
#     except Exception as e:
#         return f"Error in description generation pipeline: {str(e)}"


# # =========================
# # CLI usage (optional)
# # =========================




# if __name__ == "__main__":
#     # Example: Google Maps CID
#     cid = '12033186157967875144'
    
#     print("Fetching HTML from Bright Data API...")
#     html_text = get_maps_html_from_brightdata(cid)

#     if html_text:
#         # Save original HTML to file
#         filename = f"maps_html_{cid}.html"
#         print(f"Saving original HTML content to {filename}...")
        
#         with open(filename, 'w', encoding='utf-8') as f:
#             f.write(html_text)
        
#         print(f"Original HTML content successfully saved to {filename}")
#         print(f"Original file size: {len(html_text)} characters")
        
#         # Clean the HTML content
#         print("Cleaning HTML content...")
#         cleaned_html = clean_html_content(html_text)
        
#         # Save cleaned HTML to file
#         cleaned_filename = f"maps_html_{cid}_cleaned.html"
#         print(f"Saving cleaned HTML content to {cleaned_filename}...")
        
#         with open(cleaned_filename, 'w', encoding='utf-8') as f:
#             f.write(cleaned_html)
        
#         print(f"Cleaned HTML content successfully saved to {cleaned_filename}")
#         print(f"Cleaned file size: {len(cleaned_html)} characters")
#         print(f"Size reduction: {len(html_text) - len(cleaned_html)} characters ({((len(html_text) - len(cleaned_html)) / len(html_text) * 100):.1f}%)")
        
#         # Process with Gemini to get structured XML
#         print("\nProcessing cleaned HTML with Gemini...")
        
#         # Collect available Gemini API keys
#         gemini_keys = []
#         for key_var in [GEMINI_API_KEY_1, GEMINI_API_KEY_2, GEMINI_API_KEY_3, GEMINI_API_KEY_4, 
#                        GEMINI_API_KEY_5, GEMINI_API_KEY_6, GEMINI_API_KEY_7, GEMINI_API_KEY_8, GEMINI_API_KEY_9]:
#             if key_var and key_var.strip():
#                 gemini_keys.append(key_var)
        
#         if gemini_keys:
#             try:
#                 # Generate structured XML
#                 structured_xml = process_maps_html_to_structured_xml(html_text, gemini_keys)
                
#                 # Save structured XML to file
#                 xml_filename = f"maps_structured_{cid}.xml"
#                 print(f"Saving structured XML to {xml_filename}...")
                
#                 with open(xml_filename, 'w', encoding='utf-8') as f:
#                     f.write(structured_xml)
                
#                 print(f"Structured XML successfully saved to {xml_filename}")
#                 print("\nStructured XML preview:")
#                 print("=" * 50)
#                 print(structured_xml[:1000] + ("..." if len(structured_xml) > 1000 else ""))
#                 print("=" * 50)
                
#                 # Generate business description
#                 print("\nGenerating business description with Gemini...")
#                 business_description = generate_business_description_from_html(html_text, gemini_keys)
                
#                 # Save business description to file
#                 desc_filename = f"maps_description_{cid}.txt"
#                 print(f"Saving business description to {desc_filename}...")
                
#                 with open(desc_filename, 'w', encoding='utf-8') as f:
#                     f.write(business_description)
                
#                 print(f"Business description successfully saved to {desc_filename}")
#                 print("\nBusiness Description:")
#                 print("=" * 50)
#                 print(business_description)
#                 print("=" * 50)
                
#             except Exception as e:
#                 print(f"Error processing with Gemini: {str(e)}")
#         else:
#             print("No Gemini API keys available - skipping structured processing")
            
#     else:
#         print("Failed to get HTML content from API")
