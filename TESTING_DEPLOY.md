# Testing Cloudflare Pages Deploy Flow (No Domain)

This guide shows you how to test your deployment pipeline to Cloudflare Pages without involving custom domains, using only the default `*.pages.dev` subdomain.

## Quick Start

### Option 1: Simple Quick Test (Recommended)

Use the existing deployment functions with mocked data:

```bash
cd vm-py
python quick_test_deploy.py
```

**What this does:**
- Uses your existing `deploy_from_template_for_user()` function
- Mocks Supabase calls to avoid database dependencies
- Creates a GitHub repo with auto-generated name
- Deploys to Cloudflare Pages with `*.pages.dev` URL
- Uses test data instead of real business information

### Option 2: Full Control Test

Use the comprehensive test script with custom options:

```bash
cd vm-py
python test_deploy_no_domain.py --project-name my-test-site
```

**What this does:**
- Creates a GitHub repository named `my-test-site-TIMESTAMP`
- Copies your template and injects test business data
- Creates Cloudflare Pages project
- Returns the `*.pages.dev` URL for testing

## Prerequisites

Make sure your `.env` file (or environment) has these variables set:

```bash
GITHUB_USERNAME=your-github-username
GITHUB_TOKEN=your-github-personal-access-token
CLOUDFLARE_API_TOKEN=your-cloudflare-api-token
CLOUDFLARE_ACCOUNT_ID=your-cloudflare-account-id
```

## What Gets Created

Both scripts will create:

1. **GitHub Repository**: `https://github.com/YOUR_USERNAME/PROJECT_NAME`
2. **Cloudflare Pages Project**: Automatically linked to the GitHub repo
3. **Live Site**: `https://PROJECT_NAME.pages.dev` (or similar)

## Testing the Results

After deployment completes, you can:

```bash
# Test that the site is live
curl -I https://your-project-name.pages.dev

# Open in browser
open https://your-project-name.pages.dev

# Check GitHub repo
open https://github.com/YOUR_USERNAME/your-project-name
```

## Key Differences from Production

| Production Deploy | Test Deploy |
|-------------------|-------------|
| Uses real Supabase data | Uses mock test data |
| Configures custom domain | Uses `*.pages.dev` only |
| Pulls user's site.json | Creates test site.json |
| May involve DNS setup | No DNS configuration |

## Templates Available

You can test with different templates:

- `local-business` (default) - Business landing page
- Add more templates to `/vm-web/templates/` as needed

## Cleanup

The scripts automatically clean up temporary files, but you may want to manually delete test repositories and Cloudflare projects if you're doing multiple tests.

### Delete GitHub Repo:
```bash
# Via GitHub CLI (if installed)
gh repo delete YOUR_USERNAME/your-test-repo --yes

# Or delete manually through GitHub web interface
```

### Delete Cloudflare Pages Project:
- Go to Cloudflare Dashboard → Pages
- Find your test project and delete it

## Troubleshooting

### Common Issues:

1. **"Repository already exists"**: Add a timestamp or change the project name
2. **"Authentication failed"**: Check your GitHub token and Cloudflare API credentials
3. **"Template not found"**: Verify the template exists in `/vm-web/templates/`
4. **Build fails on Cloudflare**: Check the build logs in Cloudflare Pages dashboard

### Debug Mode:

For more detailed output, you can modify the scripts to add more logging or run them in a Python debugger.

## Integration with Your Existing Flow

These test scripts are designed to work alongside your existing deployment pipeline:

- `quick_test_deploy.py` - Uses your existing functions with mocked dependencies
- `test_deploy_no_domain.py` - Standalone script that mimics your production flow
- Both scripts create the same GitHub + Cloudflare Pages setup as production
- The only difference is no custom domain configuration

This lets you validate that:
- GitHub repository creation works
- Template copying and customization works  
- Cloudflare Pages integration works
- Build process works
- The site actually loads and displays correctly

## Next Steps

Once you've verified the deployment works:

1. Test with different templates
2. Verify the build output looks correct
3. Test any dynamic features of your templates
4. Use this as a staging environment for template development

The `*.pages.dev` URLs are permanent and can be used for demos, staging, or sharing with clients before setting up custom domains.
