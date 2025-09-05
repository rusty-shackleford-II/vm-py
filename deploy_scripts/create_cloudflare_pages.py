#!/usr/bin/env python3
"""
Python version of 02_create_cloudflare_pages.sh
Creates Cloudflare Pages project linked to GitHub repository
"""

import os
import subprocess
import requests
import json
import sys
from pathlib import Path

# Import configuration from config.py
from config import (
    GITHUB_TOKEN,
    GITHUB_USERNAME,
)


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


def verify_github_repo(github_repo_name):
    """Verify that the GitHub repository exists"""
    print_status("Verifying GitHub repository exists...")

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    try:
        response = requests.get(
            f"https://api.github.com/repos/{GITHUB_USERNAME}/{github_repo_name}",
            headers=headers,
        )

        if response.status_code == 200:
            print_success(
                f"GitHub repository verified: https://github.com/{GITHUB_USERNAME}/{github_repo_name}"
            )
            return True
        else:
            print_error(
                "GitHub repository not found. Please create the GitHub repository first."
            )
            sys.exit(1)

    except requests.RequestException as e:
        print_error(f"Failed to verify GitHub repository: {e}")
        sys.exit(1)


def create_cloudflare_pages_project(
    cloudflare_api_token,
    cloudflare_account_id,
    cloudflare_project_name,
    github_repo_name,
    build_dir="out",
):
    """Create Cloudflare Pages project linked to GitHub repository"""
    # Convert project name to lowercase for Cloudflare Pages
    pages_project_name = cloudflare_project_name.lower()

    print_status(f"Creating Cloudflare Pages project: {pages_project_name}")
    print_status(f"Linking to GitHub repository: {GITHUB_USERNAME}/{github_repo_name}")

    headers = {
        "Authorization": f"Bearer {cloudflare_api_token}",
        "Content-Type": "application/json",
    }

    data = {
        "name": pages_project_name,
        "production_branch": "main",
        "source": {
            "type": "github",
            "config": {
                "owner": GITHUB_USERNAME,
                "repo_name": github_repo_name,
                "production_branch": "main",
                "pr_comments_enabled": True,
                "deployments_enabled": True,
                "production_deployments_enabled": True,
                "preview_deployment_setting": "all",
            },
        },
        "build_config": {
            "build_command": "npm run build",
            "destination_dir": build_dir,
            "root_dir": "",
            "web_analytics_tag": "",
            "web_analytics_token": "",
            "node_version": "20.0.0"
        },
    }

    try:
        response = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/pages/projects",
            headers=headers,
            json=data,
        )

        response_data = response.json()

        if response_data.get("success"):
            print_success("Cloudflare Pages project created successfully")

            # Extract subdomain if available
            result = response_data.get("result", {})
            project_subdomain = result.get("subdomain")

            if project_subdomain:
                # Some accounts return the full subdomain (e.g. "cookie-0.pages.dev")
                # Normalize to a valid https URL without duplicating suffix.
                if project_subdomain.endswith(".pages.dev"):
                    pages_url = f"https://{project_subdomain}"
                else:
                    pages_url = f"https://{project_subdomain}.pages.dev"
                print_success(f"Your site will be available at: {pages_url}")
                return pages_url
            else:
                print_success(
                    "Project created, URL will be available after first deployment"
                )
                return f"https://{pages_project_name}.pages.dev"

        elif "already exists" in response.text:
            print_warning("Cloudflare Pages project already exists, continuing...")
            pages_url = f"https://{pages_project_name}.pages.dev"
            print_status(f"Your site should be available at: {pages_url}")
            return pages_url

        else:
            print_error("Failed to create Cloudflare Pages project")
            print_error(f"Response: {response.text}")

            if "authentication" in response.text.lower():
                print_error(
                    "Authentication failed. Check your Cloudflare API token and account ID"
                )

            sys.exit(1)

    except requests.RequestException as e:
        print_error(f"Failed to create Cloudflare Pages project: {e}")
        sys.exit(1)


def create_cloudflare_pages(
    github_repo_name,
    cloudflare_project_name,
    cloudflare_api_token,
    cloudflare_account_id,
    build_dir="out",
):
    """
    Main function to create Cloudflare Pages project linked to GitHub repository

    Args:
        github_repo_name (str): Name of the GitHub repository to link to (e.g., "my-github-repo")
        cloudflare_project_name (str): Name for the Cloudflare Pages project (e.g., "my-cloudflare-project")
        cloudflare_api_token (str): Cloudflare API token
        cloudflare_account_id (str): Cloudflare account ID
        build_dir (str): Build directory (default: "out" for Next.js SSG)

    Returns:
        dict: Results containing pages_url and project details

    Note:
        - github_repo_name: This is the name of your GitHub repository (what appears in the URL)
        - cloudflare_project_name: This is what your Cloudflare Pages project will be called
        - These can be the same or different names depending on your preference
    """
    print_status(f"Starting Cloudflare Pages creation...")
    print_status(f"• Cloudflare Project Name: {cloudflare_project_name}")
    print_status(f"• GitHub Repository: {GITHUB_USERNAME}/{github_repo_name}")

    # Verify GitHub repo exists
    verify_github_repo(github_repo_name)

    # Create Cloudflare Pages project
    pages_url = create_cloudflare_pages_project(
        cloudflare_api_token,
        cloudflare_account_id,
        cloudflare_project_name,
        github_repo_name,
        build_dir,
    )

    # Summary
    print_success("🎉 Cloudflare Pages project created successfully!")
    print("")
    print("📋 Summary:")
    print("===========")
    print(f"• Cloudflare Project Name: {cloudflare_project_name}")
    print(f"• Cloudflare Pages URL Name: {cloudflare_project_name.lower()}")
    print(
        f"• GitHub Repository: https://github.com/{GITHUB_USERNAME}/{github_repo_name}"
    )
    print(f"• Build Directory: {build_dir}")
    if pages_url:
        print(f"• Live Site URL: {pages_url}")
    print("")
    print_success(
        "✅ Cloudflare Pages project created and linked to GitHub repository!"
    )
    print("")
    print_status(
        "The project will automatically deploy when you push changes to the main branch."
    )
    print_status("You can check deployment status in the Cloudflare Pages dashboard.")

    return {
        "pages_url": pages_url,
        "build_dir": build_dir,
        "cloudflare_pages_url_name": cloudflare_project_name.lower(),  # What appears in pages.dev URL
        "github_username": GITHUB_USERNAME,
        "github_repo_name": github_repo_name,  # GitHub repository name
        "cloudflare_project_name": cloudflare_project_name,  # Cloudflare project name
    }


# Legacy functions for backward compatibility
def validate_dependencies_and_repo(local_repo_path):
    """Validate dependencies and local repository - legacy function"""
    print_status("Validating dependencies...")

    # Check required tools
    required_tools = ["node", "npm"]
    for tool in required_tools:
        result = subprocess.run(["which", tool], capture_output=True)
        if result.returncode != 0:
            print_error(f"{tool} is required but not installed. Aborting.")
            sys.exit(1)

    # Validate local repository
    repo_path = Path(local_repo_path)
    if not repo_path.exists():
        print_error(f"Local repository path does not exist: {local_repo_path}")
        sys.exit(1)

    if not (repo_path / "package.json").exists():
        print_error(
            f"package.json not found in {local_repo_path}. Make sure it's a Next.js project."
        )
        sys.exit(1)

    print_success("All dependencies validated")


def build_nextjs_app(local_repo_path):
    """Build the Next.js SSG application - legacy function"""
    print_status(f"Building Next.js SSG application in {local_repo_path}...")

    # Change to local repo directory
    original_cwd = os.getcwd()
    os.chdir(local_repo_path)

    try:
        # Install dependencies if needed
        if not Path("node_modules").exists():
            print_status("Installing dependencies...")
            subprocess.run(["npm", "install"], check=True)
            print_success("Dependencies installed")
        else:
            print_status("Dependencies already installed")

        # Build the project
        print_status("Running build command...")
        subprocess.run(["npm", "run", "build"], check=True)

        # Determine build directory
        build_dir = None
        for potential_dir in ["out", "build", "dist"]:
            if Path(potential_dir).exists():
                build_dir = potential_dir
                break

        if not build_dir:
            print_error(
                "Build directory not found. Expected 'out' (Next.js SSG), 'build', or 'dist' folder after npm run build."
            )
            sys.exit(1)

        print_success(f"Next.js SSG site built successfully in ./{build_dir}")
        return build_dir

    finally:
        os.chdir(original_cwd)


def main():
    """Main function for command line usage"""
    print_status("Using configuration from config.py...")
    print_success("Configuration loaded and validated")

    # Example usage of the new function
    print_status("Example: Creating Cloudflare Pages project")

    # You would call it like this:
    # create_cloudflare_pages(
    #     github_repo_name="my-site-repo",
    #     cloudflare_project_name="my-site-project",
    #     cloudflare_api_token="your_token_here",
    #     cloudflare_account_id="your_account_id_here",
    #     build_dir="out"
    # )

    print_success("✅ Ready to create Cloudflare Pages projects!")
    print_status(
        "Call create_cloudflare_pages() with your GitHub repo name and Cloudflare project name"
    )


if __name__ == "__main__":
    main()
