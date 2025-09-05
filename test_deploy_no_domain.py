#!/usr/bin/env python3
"""
Test deployment script for Cloudflare Pages without domain configuration.
This script allows you to test the complete deploy flow using only the default 
*.pages.dev subdomain that Cloudflare provides automatically.

Features:
- Uses local template without Supabase dependency
- Creates GitHub repo and Cloudflare Pages project
- Skips all domain-related configuration
- Perfect for testing the deployment pipeline

Usage:
    python test_deploy_no_domain.py [--project-name my-test-site]
"""

import argparse
import sys
import json
import tempfile
import shutil
from pathlib import Path

from config import (
    GITHUB_TOKEN,
    GITHUB_USERNAME,
)

# Use hardcoded test credentials for slot 0 (same as app.py)
CLOUDFLARE_API_TOKEN = "z49VdskL215U7yLZr__2BpAJ746PCRaZoZbjIl8z"
CLOUDFLARE_ACCOUNT_ID = "627931b9aaeb2438ddf36d6f068f02c2"
from deploy_scripts.create_and_push_repo import create_target_repo
from deploy_scripts.create_cloudflare_pages import create_cloudflare_pages


class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"


def print_status(message):
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {message}")


def print_success(message):
    print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {message}")


def print_warning(message):
    print(f"{Colors.YELLOW}[WARNING]{Colors.NC} {message}")


def print_error(message):
    print(f"{Colors.RED}[ERROR]{Colors.NC} {message}")


def create_test_site_json():
    """Create a sample site.json for testing purposes"""
    return {
        "businessName": "Test Business - Deployment Test",
        "phone": "(555) 123-4567",
        "heroImageUrl": "/hero.jpg",
        "tagline": "Testing Cloudflare Pages Deployment",
        "ctaText": "This is a Test Site",
        "serviceArea": "Global (Test)",
        "about": "This is a test deployment created to verify the Cloudflare Pages deployment pipeline without involving custom domains. This site uses the default *.pages.dev subdomain.",
        "services": [
            {
                "name": "Deployment Testing", 
                "description": "Verifying that the deployment pipeline works correctly.", 
                "imageUrl": ""
            },
            {
                "name": "GitHub Integration", 
                "description": "Testing GitHub repository creation and linking.", 
                "imageUrl": ""
            },
            {
                "name": "Cloudflare Pages", 
                "description": "Testing Cloudflare Pages project creation and build.", 
                "imageUrl": ""
            }
        ],
        "testimonials": [
            {
                "name": "Test User", 
                "quote": "The deployment pipeline works perfectly!", 
                "rating": 5
            },
            {
                "name": "Developer", 
                "quote": "Great for testing without domains.", 
                "rating": 5
            }
        ],
        "contactEmail": "test@example.com",
        "address": "123 Test Street, Test City, TC 12345",
        "hours": [
            {"days": "Mon–Fri", "open": "9:00 AM", "close": "5:00 PM"},
            {"days": "Saturday", "open": "10:00 AM", "close": "2:00 PM"},
            {"days": "Sunday", "closed": True}
        ],
        "mapEmbedUrl": ""
    }


def copy_template_with_test_data(template_path: str, target_dir: str, test_data: dict):
    """Copy template and inject test site.json data"""
    print_status(f"Copying template from {template_path} to {target_dir}")
    
    # Copy the entire template directory
    shutil.copytree(template_path, target_dir, dirs_exist_ok=True)
    
    # Remove any existing .git directory
    git_dir = Path(target_dir) / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)
    
    # Remove .github directory to avoid workflow push restrictions
    github_dir = Path(target_dir) / ".github"
    if github_dir.exists():
        print_status("Removing .github directory to avoid workflow push restrictions")
        shutil.rmtree(github_dir)
    
    # Find and update site.json
    site_json_path = Path(target_dir) / "data" / "site.json"
    if not site_json_path.exists():
        # Try alternative paths
        alt_paths = [
            Path(target_dir) / "src" / "data" / "site.json",
            Path(target_dir) / "public" / "data" / "site.json",
        ]
        for alt_path in alt_paths:
            if alt_path.exists():
                site_json_path = alt_path
                break
        else:
            # Create the data directory and file
            site_json_path.parent.mkdir(parents=True, exist_ok=True)
    
    print_status(f"Updating site.json at {site_json_path}")
    with open(site_json_path, 'w') as f:
        json.dump(test_data, f, indent=2)
    
    print_success("Template copied and test data injected")


def deploy_test_site_no_domain(project_name: str, template_name: str = "local-business") -> dict:
    """
    Deploy a test site to Cloudflare Pages without domain configuration
    
    Args:
        project_name: Name for the GitHub repo and Cloudflare project
        template_name: Name of the template to use (default: local-business)
    
    Returns:
        dict: Deployment results with URLs and project info
    """
    print_status("🚀 Starting test deployment to Cloudflare Pages (no domain)")
    print_status(f"Project name: {project_name}")
    print_status(f"Template: {template_name}")
    
    # Find template directory
    project_root = Path(__file__).resolve().parent
    template_dir = project_root / "vm-web" / "templates" / template_name
    
    # Also check in launchpad location
    if not template_dir.exists():
        template_dir = project_root / "launchpad" / "vm-web" / "templates" / template_name
    
    # Also check relative to current script
    if not template_dir.exists():
        template_dir = project_root / ".." / "vm-web" / "templates" / template_name
        template_dir = template_dir.resolve()
    
    if not template_dir.exists():
        print_error(f"Template directory not found: {template_name}")
        print_error(f"Searched in: {project_root / 'vm-web' / 'templates' / template_name}")
        sys.exit(1)
    
    print_success(f"Found template at: {template_dir}")
    
    # Create temporary directory for the modified template
    temp_dir = tempfile.mkdtemp(prefix=f"{project_name}_test_")
    print_status(f"Created temporary directory: {temp_dir}")
    
    try:
        # 1. Create test site.json data
        test_data = create_test_site_json()
        
        # 2. Copy template and inject test data
        copy_template_with_test_data(str(template_dir), temp_dir, test_data)
        
        # 3. Create GitHub repository
        print_status("Creating GitHub repository...")
        create_target_repo(project_name)
        
        # 4. Initialize git and push to GitHub
        import os
        import subprocess
        
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        
        try:
            # Git setup
            print_status("Setting up git repository...")
            subprocess.run(["git", "init"], check=True)
            subprocess.run(["git", "config", "http.postBuffer", "524288000"], check=True)
            subprocess.run(["git", "config", "http.maxRequestBuffer", "100M"], check=True)
            
            # Create .gitignore
            gitignore_path = Path(temp_dir) / ".gitignore"
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
            
            # Add and commit
            subprocess.run(["git", "add", "."], check=True)
            subprocess.run([
                "git", "commit", "-m", 
                f"Initial commit - Test deployment for {project_name}"
            ], check=True)
            
            # Push to GitHub
            authenticated_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{project_name}.git"
            subprocess.run(["git", "remote", "add", "origin", authenticated_url], check=True)
            subprocess.run(["git", "branch", "-M", "main"], check=True)
            subprocess.run(["git", "push", "-u", "origin", "main", "--force"], check=True)
            
            print_success("Code pushed to GitHub successfully")
            
        finally:
            os.chdir(original_cwd)
        
        # 5. Create Cloudflare Pages project
        print_status("Creating Cloudflare Pages project...")
        pages_result = create_cloudflare_pages(
            github_repo_name=project_name,
            cloudflare_project_name=project_name,
            cloudflare_api_token=CLOUDFLARE_API_TOKEN,
            cloudflare_account_id=CLOUDFLARE_ACCOUNT_ID,
            build_dir="out"  # Next.js static export
        )
        
        # 6. Summary
        result = {
            "project_name": project_name,
            "github_repo": f"https://github.com/{GITHUB_USERNAME}/{project_name}",
            "pages_url": pages_result.get("pages_url"),
            "cloudflare_project": project_name,
            "template_used": template_name,
            "temp_dir": temp_dir,
            "status": "success"
        }
        
        print_success("🎉 Test deployment completed successfully!")
        print("")
        print("📋 Deployment Summary:")
        print("=====================")
        print(f"• Project Name: {project_name}")
        print(f"• GitHub Repository: {result['github_repo']}")
        print(f"• Cloudflare Pages URL: {result['pages_url']}")
        print(f"• Template Used: {template_name}")
        print("")
        print_success("✅ Your test site will be available at the Cloudflare Pages URL above!")
        print_status("Note: It may take a few minutes for the first build to complete.")
        print_status("You can monitor the build progress in the Cloudflare Pages dashboard.")
        
        return result
        
    except Exception as e:
        print_error(f"Deployment failed: {e}")
        raise
    finally:
        # Clean up temporary directory
        print_status(f"Cleaning up temporary directory: {temp_dir}")
        try:
            shutil.rmtree(temp_dir)
            print_success("Temporary directory cleaned up")
        except Exception as e:
            print_warning(f"Failed to clean up temporary directory: {e}")


def main():
    """Main function for command line usage"""
    parser = argparse.ArgumentParser(
        description="Test deployment to Cloudflare Pages without domain configuration"
    )
    parser.add_argument(
        "--project-name",
        default="test-deploy-no-domain",
        help="Name for the GitHub repo and Cloudflare project (default: test-deploy-no-domain)"
    )
    parser.add_argument(
        "--template",
        default="local-business",
        help="Template to use (default: local-business)"
    )
    
    args = parser.parse_args()
    
    # Validate configuration
    required_vars = [
        ("GITHUB_TOKEN", GITHUB_TOKEN),
        ("GITHUB_USERNAME", GITHUB_USERNAME),
        ("CLOUDFLARE_API_TOKEN", CLOUDFLARE_API_TOKEN),
        ("CLOUDFLARE_ACCOUNT_ID", CLOUDFLARE_ACCOUNT_ID),
    ]
    
    missing_vars = [name for name, value in required_vars if not value]
    if missing_vars:
        print_error("Missing required environment variables:")
        for var in missing_vars:
            print_error(f"  - {var}")
        print_error("Please check your .env file or environment configuration.")
        sys.exit(1)
    
    print_success("✅ All required configuration variables found")
    
    # Add timestamp to project name to avoid conflicts
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    project_name = f"{args.project_name}-{timestamp}"
    
    try:
        result = deploy_test_site_no_domain(project_name, args.template)
        
        print("")
        print_success("🎯 Quick Test Commands:")
        print("=======================")
        print(f"• Test the site: curl -I {result['pages_url']}")
        print(f"• View in browser: open {result['pages_url']}")
        print(f"• GitHub repo: open {result['github_repo']}")
        print("")
        
    except KeyboardInterrupt:
        print_warning("Deployment cancelled by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Deployment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
