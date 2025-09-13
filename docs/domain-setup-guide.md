# Custom Domain Setup Guide

Connect your existing domain to your website in two simple steps. This guide works for all major domain providers and requires no technical expertise.

## How It Works

Your website is hosted at `[your-project-id].pages.dev`. To use your custom domain:

1. **Add a CNAME record** pointing `www` to your website
2. **Set up domain forwarding** so your main domain redirects to `www`

**Result:** Both `example.com` and `www.example.com` will show your website with HTTPS automatically enabled.

---

## Step-by-Step Instructions by Provider

### GoDaddy

**Step 1: Add CNAME Record**
1. Log in to your GoDaddy account
2. Go to **My Products** → **Domains** → Click **DNS** next to your domain
3. Click **Add New Record**
4. Set Type: **CNAME**, Host: **www**, Points to: **[your-project-id].pages.dev**
5. Click **Save**

**Step 2: Set Up Domain Forwarding**
1. In the same DNS page, click the **Forwarding** tab
2. Click **Add Forwarding**
3. Forward from: **example.com** (your domain)
4. Forward to: **https://www.example.com** (with www and https)
5. Forward type: **Permanent (301)**
6. Click **Save**

---

### Namecheap

**Step 1: Add CNAME Record**
1. Log in to Namecheap
2. Go to **Domain List** → Click **Manage** next to your domain
3. Click **Advanced DNS** tab
4. Click **Add New Record**
5. Type: **CNAME Record**, Host: **www**, Value: **[your-project-id].pages.dev**
6. Click **Save Changes**

**Step 2: Set Up Domain Forwarding**
1. Go to the **Domain** tab (not Advanced DNS)
2. Find **Redirect Domain** section
3. Click **Add Redirect**
4. Source: **example.com** (your domain without www)
5. Destination: **https://www.example.com** (with www and https)
6. Type: **Permanent (301)**
7. Click **Save**

---

### Squarespace

**Step 1: Add CNAME Record**
1. Log in to Squarespace
2. Go to **Settings** → **Domains** → Click your domain
3. Click **Advanced Settings** → **DNS Settings**
4. Click **Add Record**
5. Type: **CNAME**, Name: **www**, Target: **[your-project-id].pages.dev**
6. Click **Save**

**Step 2: Set Up Domain Forwarding**
1. Go to **Settings** → **Domains** → Click your domain
2. Click **Advanced Settings** → **Domain Forwarding Rules**
3. Click **Add Rule**
4. Forward from: **@** (represents your domain)
5. Forward to: **https://www.yourdomain.com**
6. Type: **Permanent (301)**
7. Click **Save**

---

### Google Domains

**Step 1: Add CNAME Record**
1. Log in to Google Domains
2. Select your domain → Click **DNS**
3. Scroll to **Custom resource records**
4. Name: **www**, Type: **CNAME**, Data: **[your-project-id].pages.dev**
5. Click **Add**

**Step 2: Set Up Domain Forwarding**
1. In the DNS page, go to **Website** section
2. Click **Forward Domain**
3. Forward to: **https://www.yourdomain.com**
4. Choose **Permanent redirect (301)**
5. Enable **SSL**
6. Click **Save**

---

### Porkbun

**Step 1: Add CNAME Record**
1. Log in to Porkbun
2. Go to **DNS** → Select your domain
3. Click **Add Record**
4. Type: **CNAME**, Host: **www**, Answer: **[your-project-id].pages.dev**
5. Click **Submit**

**Step 2: Set Up Domain Forwarding**
1. Go to **Details** → Click **Edit URL Forwarding**
2. Source URL: **yourdomain.com** (without www)
3. Destination URL: **https://www.yourdomain.com**
4. Select **301 Redirect**
5. Click **Submit**

---

### Name.com

**Step 1: Add CNAME Record**
1. Log in to Name.com
2. Go to **My Domains** → Click your domain
3. Click **DNS Records**
4. Click **Add Record**
5. Type: **CNAME**, Host: **www**, Answer: **[your-project-id].pages.dev**
6. Click **Add Record**

**Step 2: Set Up Domain Forwarding**
1. Go to **URL Forwarding** tab
2. Click **Add Forwarding**
3. From: **yourdomain.com**
4. To: **https://www.yourdomain.com**
5. Type: **301 Redirect**
6. Click **Add Forwarding**

---

### Dynadot

**Step 1: Add CNAME Record**
1. Log in to Dynadot
2. Go to **My Domains** → Click your domain
3. Click **DNS Settings**
4. Select **Dynadot DNS**
5. Add record: Type **CNAME**, Subdomain **www**, Target Host **[your-project-id].pages.dev**
6. Click **Save DNS**

**Step 2: Set Up Domain Forwarding**
1. In DNS Settings, enable **Stealth Forwarding**
2. Forward from: **yourdomain.com**
3. Forward to: **https://www.yourdomain.com**
4. Click **Save**

---

### IONOS (1&1)

**Step 1: Add CNAME Record**
1. Log in to IONOS
2. Go to **Domains & SSL** → Click your domain
3. Click **DNS**
4. Click **Add Record**
5. Type: **CNAME**, Host: **www**, Points to: **[your-project-id].pages.dev**
6. Click **Save**

**Step 2: Set Up Domain Forwarding**
1. Go to **Domains & SSL** → Click your domain
2. Click **Adjust Destination**
3. Select **Forward Domain**
4. Destination: **https://www.yourdomain.com**
5. Select **HTTP Redirect**
6. Click **Save**

---

### Gandi

**Step 1: Add CNAME Record**
1. Log in to Gandi
2. Go to **Domains** → Click your domain
3. Click **DNS Records**
4. Click **Add Record**
5. Type: **CNAME**, Name: **www**, Value: **[your-project-id].pages.dev**
6. Click **Create**

**Step 2: Set Up Domain Forwarding**
1. Go to **Web Forwarding** tab
2. Click **Create**
3. Source: **yourdomain.com**
4. Target: **https://www.yourdomain.com**
5. Type: **Permanent (301)**
6. Click **Submit**

---

## Special Cases

### Wix (Limited Support)
Wix doesn't offer built-in domain forwarding. You have two options:

**Option A: Use External DNS (Recommended)**
1. Change your domain's nameservers to Cloudflare, Porkbun, or Name.com
2. Follow the instructions for your chosen provider above

**Option B: Third-party Redirect Service**
1. Set up the CNAME for www as described
2. Use a service like redirect.pizza to forward apex to www

### Cloudflare Registrar (Advanced)
If your domain is registered with Cloudflare:

1. Add CNAME: **www** → **[your-project-id].pages.dev**
2. Add A record: **@** → **192.0.2.1** (dummy IP, enable proxy)
3. Go to **Rules** → **Redirect Rules** → Create redirect from apex to www

---

## Final Steps (You Complete)

Once your customer completes the DNS setup:

1. Go to your Cloudflare Pages project
2. Navigate to **Custom domains**
3. Click **Set up a custom domain**
4. Enter **www.customer-domain.com**
5. Click **Continue** and **Activate domain**

Cloudflare will automatically issue an SSL certificate and activate the domain within 15-30 minutes.

---

## Troubleshooting

**Domain not working after 24 hours?**
- Check DNS propagation using online DNS checkers
- Verify CNAME record points exactly to `[your-project-id].pages.dev`
- Ensure domain forwarding is set to HTTPS with www
- Try incognito/private browsing to avoid cache issues

**SSL certificate issues?**
- Wait 30 minutes for automatic certificate provisioning
- Ensure forwarding uses HTTPS (not HTTP)

**"This site can't be reached" errors?**
- Verify the CNAME record is correct
- Check if you've added the domain in your Cloudflare Pages dashboard

---

## Summary

This setup ensures:
- ✅ `yourdomain.com` redirects to `www.yourdomain.com`
- ✅ `www.yourdomain.com` shows your website
- ✅ HTTPS works automatically for both
- ✅ No nameserver changes required
- ✅ Customer keeps full DNS control