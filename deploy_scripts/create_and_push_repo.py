#!/usr/bin/env python3
"""
Python version of 01_create_and_push_repo.sh
Split into two main functions:
1. create_target_repo() - Creates a GitHub repository
2. clone_template_and_push_to_target() - Clones template, clears git, and pushes to target
"""

import subprocess
import requests
import json
import sys
import os
import tempfile
import shutil
from pathlib import Path

# Import configuration from config.py
from config import GITHUB_TOKEN, GITHUB_USERNAME, LOCAL_REPO_PATH

# Import DataSync for downloading supabase data
from data_sync import DataSync


class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"  # No Color


def print_status(message):
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {message}")


def print_success(message):
    print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {message}")


def print_warning(message):
    print(f"{Colors.YELLOW}[WARNING]{Colors.NC} {message}")


def print_error(message):
    print(f"{Colors.RED}[ERROR]{Colors.NC} {message}")


def create_target_repo(project_name):
    """
    Create a new GitHub repository via API

    Args:
        project_name (str): Name for the GitHub repository

    Returns:
        str: Repository clone URL
    """
    print_status(f"Creating target GitHub repository: {project_name}")

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    data = {
        "name": project_name,
        "private": True,
        "description": "Next.js SSG site for Cloudflare Pages deployment",
    }

    try:
        response = requests.post(
            "https://api.github.com/user/repos", headers=headers, json=data
        )

        if response.status_code == 201:
            print_success("GitHub repository created successfully")
            repo_data = response.json()
            repo_url = repo_data.get("clone_url")
            print_status(f"Repository URL: {repo_url}")
            return repo_url
        elif "already exists" in response.text:
            print_warning("Repository already exists, continuing with existing repo...")
            repo_url = f"https://github.com/{GITHUB_USERNAME}/{project_name}.git"
            return repo_url
        else:
            print_error(f"Repository creation failed: {response.text}")
            sys.exit(1)

    except requests.RequestException as e:
        print_error(f"Failed to create repository: {e}")
        sys.exit(1)


def clone_template_and_push_to_target_from_local_template(
    local_template_path: str, target_repo: str, user_uuid: str
):
    """
    Copy a local Next.js template, inject user site.json from Supabase, and push to target repo

    Steps:
    1. Copy local template directory to a temp dir
    2. Remove any existing .git
    3. Download user's site.json (sites/{user_key}.json) to template's data/site.json
    4. Initialize git and push to target repository

    Args:
        local_template_path (str): Absolute path to the local template directory
        target_repo (str): Name of the target GitHub repository (e.g., "my-site")
        user_uuid (str): Supabase UUID used to fetch vm-site/{uuid}/site.json from storage

    Returns:
        dict: Results containing repo_url, temp_dir and other details
    """
    print_status(
        f"Copying local template '{local_template_path}' and pushing to target: '{target_repo}' for user uuid: '{user_uuid}'"
    )

    # Store original working directory
    original_cwd = os.getcwd()
    print_status(f"Original working directory: {original_cwd}")

    # Construct target URL using GITHUB_USERNAME
    target_repo_url = f"https://github.com/{GITHUB_USERNAME}/{target_repo}.git"
    print_status(f"Target repo URL: {target_repo_url}")

    # Create temporary directory using target_repo name
    temp_dir = tempfile.mkdtemp(prefix=f"{target_repo}_temp_")
    print_status(f"Created temporary directory: {temp_dir}")

    try:
        # Ensure we're in a valid working directory before git operations
        os.chdir(original_cwd)

        # Copy local template into temporary folder
        print_status(f"Copying template from: {local_template_path}")
        shutil.copytree(local_template_path, temp_dir, dirs_exist_ok=True)

        # Now change to temp directory for the rest of the operations
        os.chdir(temp_dir)
        print_status(f"Changed to temporary directory: {temp_dir}")

        # Delete .git directory
        print_status("Removing .git directory from template copy")
        git_dir = Path(temp_dir) / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir)

        # Delete .github directory to avoid pushing GitHub Actions workflows
        # which require a PAT with 'workflow' scope. Cloudflare Pages integration
        # does not need repo-side workflows.
        github_dir = Path(temp_dir) / ".github"
        if github_dir.exists():
            print_status("Removing .github directory to avoid workflow push restrictions")
            shutil.rmtree(github_dir)

        # Inject user site.json into template at templates/next-landing/data/site.json
        # Determine target JSON path inside template
        site_json_path = Path(temp_dir) / "data" / "site.json"
        if not site_json_path.parent.exists():
            # Support template path: templates/next-landing/data/site.json
            # or src/data/site.json depending on structure
            alt_path = Path(temp_dir) / "src" / "data"
            alt_path.mkdir(parents=True, exist_ok=True)
            site_json_path = alt_path / "site.json"

        print_status(f"Fetching user site JSON for uuid '{user_uuid}' -> {site_json_path}")
        data_sync = DataSync(site_data_bucket="site-data", sites_bucket="vm-sites")
        # User content is saved under vm-sites/private/<uuid>/<domain>/site.json
        # Attempt to fetch preferred domain from DB for this user
        site_url_value = None
        try:
            sb_client = data_sync.sites_client.client
            rec = (
                sb_client
                .table("site_customers")
                .select("id, site_url")
                .eq("id", user_uuid)
                .execute()
            )
            if rec.data and isinstance(rec.data, list):
                site_url_value = (rec.data[0] or {}).get("site_url") or None
        except Exception:
            pass

        pulled = data_sync.pull_user_site_json(
            user_uuid=user_uuid,
            local_json_path=str(site_json_path),
            remote_base_folder="private",
            site_url=site_url_value,
        )
        if not pulled:
            print_warning("Falling back: no remote user JSON found. Keeping template's existing site.json.")

        # Git init
        print_status("Initializing new git repository")
        subprocess.run(["git", "init"], check=True)

        # Configure git for large file pushes
        print_status("Configuring git for large file transfers...")
        subprocess.run(["git", "config", "http.postBuffer", "524288000"], check=True)
        subprocess.run(["git", "config", "http.maxRequestBuffer", "100M"], check=True)
        subprocess.run(["git", "config", "http.lowSpeedLimit", "0"], check=True)
        subprocess.run(["git", "config", "http.lowSpeedTime", "999999"], check=True)

        # Create .gitignore if needed
        if not Path(".gitignore").exists():
            print_status("Creating .gitignore file...")
            gitignore_content = """# Dependencies
node_modules/
/.pnp
.pnp.js

# Testing
/coverage

# Production
/build
/out
/dist

# Environment variables
.env
.env.local
.env.development.local
.env.test.local
.env.production.local

# Logs
npm-debug.log*
yarn-debug.log*
yarn-error.log*
lerna-debug.log*

# Runtime data
pids
*.pid
*.seed
*.pid.lock

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db
"""
            with open(".gitignore", "w") as f:
                f.write(gitignore_content)
            print_success(".gitignore created")

        # Add all files
        print_status("Staging all files...")
        subprocess.run(["git", "add", "."], check=True)

        # Create initial commit
        print_status("Creating initial commit...")
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "Initial commit - Deployed from template to Cloudflare Pages",
            ],
            check=True,
        )

        # Add target repo as origin and force push
        print_status(f"Adding target repository as origin: {target_repo_url}")
        authenticated_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{target_repo}.git"

        subprocess.run(
            ["git", "remote", "add", "origin", authenticated_url], check=True
        )
        subprocess.run(["git", "branch", "-M", "main"], check=True)

        print_status("Force pushing to target repository...")
        subprocess.run(["git", "push", "-u", "origin", "main", "--force"], check=True)

        print_success("Template copied and pushed to target repository successfully")

        # Summary
        print_success("🎉 Template deployment completed successfully!")
        print("")
        print("📋 Summary:")
        print("===========")
        print(f"• User UUID: {user_uuid}")
        print(f"• Target Repository: {target_repo} -> https://github.com/{GITHUB_USERNAME}/{target_repo}")
        print(f"• Temporary Directory: {temp_dir}")
        print("")

        return {
            "repo_url": target_repo_url,
            "github_username": GITHUB_USERNAME,
            "user_uuid": user_uuid,
            "target_repo": target_repo,
            "temp_dir": temp_dir,
        }

    except subprocess.CalledProcessError as e:
        print_error(f"Git operation failed: {e}")
        raise
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        raise
    finally:
        # Restore original working directory first
        try:
            os.chdir(original_cwd)
            print_status(f"Restored original working directory: {original_cwd}")
        except Exception as e:
            print_warning(f"Failed to restore original working directory: {e}")

        # Clean up temporary folder
        print_status(f"Cleaning up temporary directory: {temp_dir}")
        try:
            shutil.rmtree(temp_dir)
            print_success("Temporary directory cleaned up")
        except Exception as e:
            print_warning(f"Failed to clean up temporary directory: {e}")


# Legacy function that combines both operations for backward compatibility
def create_and_push_repo(local_repo_path, project_name):
    """
    Legacy function - creates GitHub repository and pushes existing project code
    This maintains backward compatibility with the original function
    """
    print_status(f"Starting GitHub repository creation for project: {project_name}")

    # Validate local repository
    validate_local_repo(local_repo_path)

    # Create GitHub repository
    repo_url = create_target_repo(project_name)

    # Setup git and push from existing local repo
    setup_and_push_git(local_repo_path, repo_url, project_name)

    return {
        "repo_url": repo_url,
        "github_username": GITHUB_USERNAME,
        "project_name": project_name,
        "local_repo_path": local_repo_path,
    }


def validate_local_repo(local_repo_path):
    """Validate that the local repository path exists and is a Next.js project"""
    print_status("Validating local repository path...")

    repo_path = Path(local_repo_path)
    if not repo_path.exists():
        print_error(f"Local repository path does not exist: {local_repo_path}")
        sys.exit(1)

    if not (repo_path / "package.json").exists():
        print_error(
            f"package.json not found in {local_repo_path}. Make sure it's a Next.js project."
        )
        sys.exit(1)

    if not (repo_path / "src").exists():
        print_error(
            f"src folder not found in {local_repo_path}. Make sure it's a Next.js project."
        )
        sys.exit(1)

    print_success(f"Local repository path validated: {local_repo_path}")


def setup_and_push_git(local_repo_path, repo_url, project_name):
    """Setup git and push to GitHub from existing local repository"""
    print_status("Setting up Git repository...")

    # Change to local repo directory
    os.chdir(local_repo_path)

    # Initialize git if not already initialized
    if not Path(".git").exists():
        subprocess.run(["git", "init"], check=True)
        print_status("Git repository initialized")
    else:
        print_status("Git repository already exists")

    # Set up git remote
    try:
        subprocess.run(
            ["git", "remote", "remove", "origin"], capture_output=True, check=False
        )
    except:
        pass

    subprocess.run(["git", "remote", "add", "origin", repo_url], check=True)
    print_status(f"Git remote 'origin' configured: {repo_url}")

    # Configure git for large file pushes
    print_status("Configuring git for large file transfers...")
    subprocess.run(["git", "config", "http.postBuffer", "524288000"], check=True)
    subprocess.run(["git", "config", "http.maxRequestBuffer", "100M"], check=True)
    subprocess.run(["git", "config", "http.lowSpeedLimit", "0"], check=True)
    subprocess.run(["git", "config", "http.lowSpeedTime", "999999"], check=True)

    # Create .gitignore if needed
    if not Path(".gitignore").exists():
        print_status("Creating .gitignore file...")
        gitignore_content = """# Dependencies
node_modules/
/.pnp
.pnp.js

# Testing
/coverage

# Production
/build
/out
/dist

# Environment variables
.env
.env.local
.env.development.local
.env.test.local
.env.production.local

# Logs
npm-debug.log*
yarn-debug.log*
yarn-error.log*
lerna-debug.log*

# Runtime data
pids
*.pid
*.seed
*.pid.lock

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db
"""
        with open(".gitignore", "w") as f:
            f.write(gitignore_content)
        print_success(".gitignore created")
    else:
        print_status(".gitignore already exists")

    # Check for uncommitted changes
    result = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True
    )

    if result.stdout.strip():
        print_warning("Found uncommitted changes in the repository")
        print_status("Staging all files...")
        subprocess.run(["git", "add", "."], check=True)

        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "diff", "--staged", "--quiet"], capture_output=True, check=False
        )
        if result.returncode != 0:
            print_status("Committing changes...")
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    f"Commit existing changes before GitHub deployment - {subprocess.run(['date'], capture_output=True, text=True).stdout.strip()}",
                ],
                check=True,
            )
            print_success("Changes committed")
    else:
        print_status("Repository is clean - no uncommitted changes")

    # Check if we need an initial commit
    result = subprocess.run(
        ["git", "log", "--oneline", "-n", "1"], capture_output=True, check=False
    )

    if result.returncode != 0:
        print_status("No commits found, creating initial commit...")
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "Initial commit - Next.js SSG site for Cloudflare Pages deployment",
            ],
            check=True,
        )
        print_success("Initial commit created")

    # Push to GitHub using authenticated URL
    print_status("Pushing to GitHub...")
    authenticated_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{project_name}.git"

    subprocess.run(
        ["git", "remote", "remove", "origin"], capture_output=True, check=False
    )
    subprocess.run(["git", "remote", "add", "origin", authenticated_url], check=True)
    subprocess.run(["git", "branch", "-M", "main"], check=True)
    subprocess.run(["git", "push", "-u", "origin", "main", "--force"], check=True)

    # Replace with clean URL for security
    subprocess.run(["git", "remote", "remove", "origin"], check=True)
    subprocess.run(["git", "remote", "add", "origin", repo_url], check=True)

    print_success("Code pushed to GitHub successfully")


def main():
    """Main function for command line usage"""
    print_status("Using configuration from config.py...")
    print_success("Configuration loaded and validated")

    # If invoked directly, create a test repo
    create_target_repo("test-repo")


if __name__ == "__main__":
    main()
