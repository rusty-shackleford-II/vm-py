#!/usr/bin/env python3
"""
Unified Data Sync Utility

Handles synchronization of sites_list.json and site data with Supabase storage.
Supports all operations needed for the cycle.md workflow.

Usage:
    from data_sync import DataSync

    # Initialize
    sync = DataSync()

    # Sites list operations
    sites_data = sync.pull_sites_list()
    sync.push_sites_list()

    # Site data operations
    sync.pull_site_data("example.com", "/local/path")
    sync.push_site_data("/local/path", "example.com")
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

from clients.supabase_client import SupabaseClient


class DataSync:
    """
    Unified utility to sync sites_list.json and site data with Supabase storage.
    Supports all operations needed for the cycle.md workflow.
    """

    def __init__(
        self, site_data_bucket: str = "site-data", sites_bucket: str = "vm-sites"
    ):
        """
        Initialize the data sync utility.

        Args:
            site_data_bucket (str): Bucket name for individual site data
            sites_bucket (str): Bucket name for sites_list.json
        """
        self.site_data_bucket = site_data_bucket
        self.sites_bucket = sites_bucket

        # Initialize clients for both buckets
        self.site_data_client = SupabaseClient(site_data_bucket)
        self.sites_client = SupabaseClient(sites_bucket)

        # Constants for sites list
        self.SITES_FILE = "sites_list.json"
        self.SITES_REMOTE_PATH = "sites_list.json"

        print(f"DataSync initialized:")
        print(f"  Site data bucket: {site_data_bucket}")
        print(f"  Sites bucket: {sites_bucket}")

    # Sites List Operations
    def pull_sites_list(self) -> Dict[str, Any]:
        """
        Download sites_list.json from Supabase storage to local directory.

        Returns:
            Dict[str, Any]: The downloaded sites data as a dictionary.

        Raises:
            RuntimeError: If download fails.
            FileNotFoundError: If remote file doesn't exist.
        """
        try:
            print(f"📥 Pulling {self.SITES_FILE} from Supabase storage...")

            # Download the file
            self.sites_client.download_file(self.SITES_REMOTE_PATH, self.SITES_FILE)

            # Load and return the data
            with open(self.SITES_FILE, "r") as f:
                sites_data = json.load(f)

            print(
                f"✅ Successfully pulled {self.SITES_FILE} with {len(sites_data)} sites"
            )
            return sites_data

        except Exception as e:
            raise RuntimeError(f"Failed to pull sites list: {str(e)}")

    def push_sites_list(self) -> bool:
        """
        Upload local sites_list.json to Supabase storage.

        Returns:
            bool: True if upload successful.

        Raises:
            FileNotFoundError: If local sites_list.json doesn't exist.
            RuntimeError: If upload fails.
        """
        try:
            # Check if local file exists
            local_file = Path(self.SITES_FILE)
            if not local_file.exists():
                raise FileNotFoundError(
                    f"Local {self.SITES_FILE} not found. Cannot push to Supabase."
                )

            print(f"📤 Pushing {self.SITES_FILE} to Supabase storage...")

            # Load local data to verify it's valid JSON
            with open(self.SITES_FILE, "r") as f:
                sites_data = json.load(f)

            print(f"📊 Local file contains {len(sites_data)} sites")

            # Upload the file (overwrite existing)
            self.sites_client.upload_file(
                self.SITES_FILE, self.SITES_REMOTE_PATH, overwrite=True
            )

            print(f"✅ Successfully pushed {self.SITES_FILE} to Supabase storage")
            return True

        except FileNotFoundError:
            raise
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON in {self.SITES_FILE}: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Failed to push sites list: {str(e)}")

    # Site Data Operations
    def pull_site_data(self, site_url: str, local_path: str) -> bool:
        """
        Copy remote <site>/data to given local path.

        Args:
            site_url (str): Site URL (used as folder name in remote storage)
            local_path (str): Local directory path to copy data to

        Returns:
            bool: Success status
        """
        try:
            local_path = Path(local_path)

            print(f"🔄 Pulling data for '{site_url}' into {local_path}")

            # Wipe existing directory if it exists
            if local_path.exists():
                print(f"🗑️ Wiping existing directory: {local_path}")
                shutil.rmtree(local_path)

            # Ensure local directory exists
            local_path.mkdir(parents=True, exist_ok=True)

            # Download files from supabase for this site
            result = self.site_data_client.download_json_folder(
                remote_folder=site_url, local_folder=local_path
            )

            print(f"📥 Downloaded {result['downloaded']} files to {local_path}")
            if result["failed"]:
                print(f"⚠️ {result['failed']} files failed to download")

            return result["downloaded"] > 0

        except Exception as e:
            print(f"❌ Error pulling site data: {e}")
            return False

    def push_site_data(self, local_path: str, site_url: str) -> bool:
        """
        Push given local path to <site>/data in remote storage.

        Args:
            local_path (str): Local directory path containing data to upload
            site_url (str): Site URL (used as folder name in remote storage)

        Returns:
            bool: Success status
        """
        local_path = Path(local_path)

        if not local_path.exists():
            print(f"❌ Local directory not found: {local_path}")
            return False

        try:
            uploaded_files = 0

            print(f"📤 Pushing data from {local_path} to '{site_url}' folder")

            # Upload all files in the local directory
            for file_path in local_path.rglob("*"):
                if file_path.is_file():
                    # Calculate relative path from local directory
                    relative_path = file_path.relative_to(local_path)

                    # Remote path includes site_url as folder
                    remote_path = f"{site_url}/{relative_path}"

                    # Upload file
                    result = self.site_data_client.upload_file(
                        local_path=file_path, remote_path=remote_path, overwrite=True
                    )

                    if result:
                        uploaded_files += 1
                        print(f"✅ Uploaded: {relative_path}")
                    else:
                        print(f"❌ Failed to upload: {relative_path}")

            print(f"📤 Push complete: {uploaded_files} files uploaded")
            return uploaded_files > 0

        except Exception as e:
            print(f"❌ Error during push: {e}")
            return False

    def pull_user_site_json(
        self,
        user_uuid: str,
        local_json_path: str,
        remote_base_folder: str = "",
        site_url: Optional[str] = None,
    ) -> bool:
        """
        Download a single user's site.json from the sites bucket into a specific local path.

        Conventions:
          - New: <sites_bucket>/{remote_base_folder}/{user_uuid}/{site_url}/site.json
          - Old (fallback): <sites_bucket>/{remote_base_folder}/{user_uuid}/site.json

        Args:
            user_uuid (str): Supabase UUID that identifies the user's folder.
            local_json_path (str): Absolute or relative path where the JSON should be written locally.
            remote_base_folder (str): Root folder within the sites bucket. Defaults to "vm-site".

        Returns:
            bool: True if download succeeded, False otherwise.
        """
        try:
            local_path = Path(local_json_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # Prefer new path if site_url is provided
            candidate_paths = []
            base = f"{remote_base_folder}/" if remote_base_folder else ""
            if site_url:
                candidate_paths.append(f"{base}{user_uuid}/{site_url}/site.json")
            # Old path fallback
            candidate_paths.append(f"{base}{user_uuid}/site.json")

            # If no site_url and old path fails, attempt to autodiscover a subfolder and try there
            attempted = []
            for remote_path in candidate_paths:
                print(
                    f"📥 Pulling user site JSON from Supabase: bucket='{self.sites_bucket}' path='{remote_path}' -> '{local_path}'"
                )
                try:
                    ok = self.sites_client.download_file(remote_path, local_path)
                    if ok:
                        print(f"✅ Downloaded user site JSON to {local_path}")
                        return True
                    attempted.append(remote_path)
                except Exception as e:
                    print(f"⚠️ Attempt failed for {remote_path}: {e}")
                    attempted.append(remote_path)

            # Autodiscover subfolder under private/<uuid>/ and try each '<sub>/site.json'
            try:
                listing_root = f"{base}{user_uuid}"
                items = self.sites_client.list_files(folder_path=listing_root, recursive=False)
                for item in items:
                    name = item.get("name")
                    meta = item.get("metadata")
                    # Directories usually have no size/metadata
                    if name and (not meta or meta.get("size") is None):
                        guess_path = f"{listing_root}/{name}/site.json"
                        print(f"🔎 Trying discovered path: {guess_path}")
                        try:
                            ok = self.sites_client.download_file(guess_path, local_path)
                            if ok:
                                print(f"✅ Downloaded user site JSON to {local_path}")
                                return True
                        except Exception:
                            pass
            except Exception as e:
                print(f"⚠️ Autodiscover step failed: {e}")

            print("⚠️ All attempts to pull user site JSON failed")
            return False
        except Exception as e:
            print(f"❌ Failed to pull user site JSON: {e}")
            return False

    # Legacy/Convenience Methods
    def pull_data_to_repo(self, temp_repo_path: str, site_url: str) -> bool:
        """
        Pull data from Supabase storage into a specific repo's src/data directory.

        This is specifically designed for the cycle.md workflow where we:
        1. Clone template repo to temp directory
        2. Download supabase data into <temp_dir>/src/data
        3. Push to target repo

        Args:
            temp_repo_path (str): Path to the temporary repo directory
            site_url (str): Site URL to pull data for

        Returns:
            bool: Success status
        """
        # Calculate the src/data path within the repo
        repo_src_data_path = Path(temp_repo_path) / "src" / "data"

        return self.pull_site_data(site_url, str(repo_src_data_path))

    def push_data(self, site_url: str, local_data_path: Optional[str] = None) -> bool:
        """
        Push local data directory to Supabase storage.

        Args:
            site_url (str): Site URL to use as folder name in storage
            local_data_path (Optional[str]): Path to local data directory.
                                           Defaults to "ssg-bd/src/data" if None.

        Returns:
            bool: Success status
        """
        if local_data_path is None:
            local_data_path = "ssg-bd/src/data"

        return self.push_site_data(local_data_path, site_url)

    def list_site_files(self, site_url: Optional[str] = None) -> bool:
        """
        List files in remote site data storage.

        Args:
            site_url (Optional[str]): Site URL folder to list.
                                     If None, lists root of bucket.

        Returns:
            bool: Success status
        """
        try:
            remote_folder = site_url if site_url else ""

            files = self.site_data_client.list_files(
                folder_path=remote_folder, recursive=True
            )

            print(f"\n📋 Remote files in '{remote_folder or 'root'}':")
            for file_info in files:
                file_path = file_info.get("full_path", file_info["name"])
                file_size = file_info.get("metadata", {}).get("size", "unknown")
                print(f"  📄 {file_path} ({file_size} bytes)")

            print(f"\nTotal: {len(files)} files")
            return True

        except Exception as e:
            print(f"❌ Error listing files: {e}")
            return False


if __name__ == "__main__":
    sync = DataSync()
    sync.push_sites_list()
    # sync.pull_sites_list()
