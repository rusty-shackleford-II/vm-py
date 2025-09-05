#!/usr/bin/env python3
"""
End-to-end deploy for the current project.

Steps:
  1) Create GitHub repo if missing
  2) Copy local Next.js template and inject user site.json from Supabase
  3) Push to GitHub
  4) Create Cloudflare Pages project linked to the repo

Usage: Run directly without CLI args. Values are derived from config.py and project layout.
"""

import sys
from pathlib import Path

from config import (
    # PROJECT_NAME,  # No longer used - now computed from slot
    # DOMAIN,  # No longer used - passed as parameter
)
from .create_and_push_repo import (
    create_target_repo,
    clone_template_and_push_to_target_from_local_template,
)
from .create_cloudflare_pages import create_cloudflare_pages


def deploy_from_template_for_user(
    user_uuid: str, 
    cloudflare_api_token: str,
    cloudflare_account_id: str,
    project_name: str,
    repo_name: str | None = None, 
    pages_project: str | None = None, 
    build_dir: str = "out"
) -> dict:
    """
    High-level deploy function used by workers:
      - Ensures a GitHub repo exists
      - Copies the local template, injects vm-sites/private/<uuid>/site.json
      - Pushes to GitHub
      - Creates Cloudflare Pages project

    Returns a dict with repo_name, pages_project and pages_url.
    """
    project_root = Path(__file__).resolve().parents[2]
    template_dir = project_root / "templates" / "next-landing"
    if not template_dir.exists():
        print(f"[ERROR] Template directory not found: {template_dir}")
        sys.exit(1)

    if not repo_name:
        suffix = user_uuid[:8].lower()
        repo_name = f"{project_name.replace(' ', '-').lower()}-{suffix}"
    if not pages_project:
        pages_project = repo_name

    # 1) Create GitHub repo (idempotent)
    create_target_repo(repo_name)

    # 2+3) Copy template, inject user JSON from Supabase, and push to GitHub
    clone_template_and_push_to_target_from_local_template(
        local_template_path=str(template_dir),
        target_repo=repo_name,
        user_uuid=user_uuid,
    )

    # 4) Create Cloudflare Pages project linked to GitHub
    pages = create_cloudflare_pages(
        github_repo_name=repo_name,
        cloudflare_project_name=pages_project,
        cloudflare_api_token=cloudflare_api_token,
        cloudflare_account_id=cloudflare_account_id,
        build_dir=build_dir,
    )
    return {"repo_name": repo_name, "pages_project": pages_project, "pages_url": pages.get("pages_url")}


def main() -> None:
    # Default test execution using a sample UUID
    USER_UUID = "test-uuid"
    # Use hardcoded test credentials for slot 0 (same as app.py)
    CLOUDFLARE_API_TOKEN = "z49VdskL215U7yLZr__2BpAJ746PCRaZoZbjIl8z"
    CLOUDFLARE_ACCOUNT_ID = "627931b9aaeb2438ddf36d6f068f02c2"
    PROJECT_NAME = "cookie-0"
    
    result = deploy_from_template_for_user(
        USER_UUID, 
        CLOUDFLARE_API_TOKEN, 
        CLOUDFLARE_ACCOUNT_ID, 
        PROJECT_NAME
    )
    print(result)


if __name__ == "__main__":
    main()


