# Namecheap Domain Listing Test Scripts

This directory contains several test scripts for testing the Namecheap API domain listing functionality.

## Available Test Scripts

### 1. `test_namecheap_list_domains_standalone.py` ⭐ **RECOMMENDED**
**Standalone test script that doesn't depend on existing config setup**

**Features:**
- ✅ No external dependencies beyond Python standard library + requests
- ✅ Clear environment variable validation
- ✅ Comprehensive error handling and troubleshooting
- ✅ Debug mode for API response inspection
- ✅ Pretty-printed results
- ✅ Works in both sandbox and production modes

**Usage:**
```bash
# Set your Namecheap API credentials
export NAMECHEAP_API_USER="your_api_user"
export NAMECHEAP_API_KEY="your_api_key" 
export NAMECHEAP_USERNAME="your_username"
export CLIENT_IP="your_whitelisted_ip"

# Optional: Enable sandbox mode (default: false)
export NAMECHEAP_SANDBOX="true"

# Optional: Enable debug mode to see raw API responses
export NAMECHEAP_DEBUG="true"

# Run the test
python test_namecheap_list_domains_standalone.py
```

### 2. `test_purchased_domains_only.py`
**Focused test script (requires existing config.py setup)**

**Features:**
- ✅ Dedicated to testing `get_purchased_domains()` only
- ✅ Debug mode enabled
- ✅ Detailed troubleshooting suggestions
- ⚠️ Requires config.py and decouple package

### 3. `test_namecheap_connection.py` 
**Comprehensive test suite (requires existing config.py setup)**

**Features:**
- ✅ Full test suite including domain listing
- ✅ Tests environment variables, connectivity, availability, pricing, and purchased domains
- ✅ Test summary and reporting
- ⚠️ Requires config.py and decouple package

### 4. `test_namecheap_client.py`
**Basic domain availability test**

**Features:**
- ✅ Tests basic domain availability checking
- ⚠️ Does not test domain listing functionality

### 5. `test_namecheap_flow.py`
**Domain search with pricing test**

**Features:**
- ✅ Tests domain search with pricing
- ⚠️ Does not test domain listing functionality

## Getting Your Namecheap API Credentials

1. **Login to Namecheap** and go to your Dashboard
2. **Navigate to Profile** → Tools → **Namecheap API Access**
3. **Enable API Access** if not already enabled
4. **Note down your credentials:**
   - API User (usually your Namecheap username)
   - API Key (generate if needed)
   - Username (your Namecheap username)
5. **Whitelist your IP address** - this is crucial!
   - Add your current IP address to the whitelist
   - You can find your IP at https://whatismyipaddress.com/

## API Endpoints

- **Sandbox:** `https://api.sandbox.namecheap.com/xml.response`
- **Production:** `https://api.namecheap.com/xml.response`

## Common Issues & Solutions

### ❌ IP Not Whitelisted
```
Error: IP address not whitelisted
```
**Solution:** Add your current IP to the Namecheap API whitelist in your dashboard.

### ❌ Authentication Failed
```
Error: Authentication failed
```
**Solution:** Double-check your API credentials (API_USER, API_KEY, USERNAME).

### ❌ No Domains Found
```
No purchased domains found in your account
```
**Solution:** This is normal if you haven't purchased any domains through Namecheap yet.

### ❌ Sandbox vs Production
Make sure you're using the correct endpoint:
- Set `NAMECHEAP_SANDBOX=true` for testing
- Set `NAMECHEAP_SANDBOX=false` for production

## Example Output

When successful, you'll see output like:
```
📊 Found 2 domain(s):

  Domain #1:
    Name: example.com
    Expires: 2024-12-31
    Auto-renew: True
    Raw attributes: {'Name': 'example.com', 'Expires': '2024-12-31', 'AutoRenew': 'true'}

  Domain #2:
    Name: mysite.net
    Expires: 2025-06-15
    Auto-renew: False
    Raw attributes: {'Name': 'mysite.net', 'Expires': '2025-06-15', 'AutoRenew': 'false'}
```

## Testing Tips

1. **Start with sandbox mode** (`NAMECHEAP_SANDBOX=true`) for initial testing
2. **Enable debug mode** (`NAMECHEAP_DEBUG=true`) to see raw API responses
3. **Use the standalone script** for the most reliable testing experience
4. **Check IP whitelisting** if you get authentication errors

## Next Steps

Once your test script runs successfully:
1. ✅ Your Namecheap API integration is working
2. ✅ You can list purchased domains programmatically
3. ✅ You can integrate this into your application
4. ✅ Consider adding domain management features to your app
