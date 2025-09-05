import os
import json
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import config
from supabase import create_client, Client
from datetime import datetime


class SupabaseClient:
    """
    A client class to interact with Supabase Storage for file operations.
    Handles uploading, downloading, listing, and recursive folder operations.
    """

    def __init__(self, bucket_name: str = "files"):
        """
        Initializes the Supabase client with credentials from config.py.

        Args:
            bucket_name (str): Default bucket name to use for operations. Defaults to "files".

        Raises:
            ValueError: If required config values are missing.
        """
        # Get credentials from config
        self.url = getattr(config, "SUPABASE_URL", None)
        self.service_role_key = getattr(config, "SUPABASE_SERVICE_ROLE_KEY", None)

        if not self.url:
            raise ValueError("SUPABASE_URL not found in config.py")
        if not self.service_role_key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY not found in config.py")

        # Initialize Supabase client
        self.client: Client = create_client(self.url, self.service_role_key)
        self.default_bucket = bucket_name

        print(f"SupabaseClient initialized for bucket: '{bucket_name}'")

    def upload_file(
        self,
        local_path: Union[str, Path],
        remote_path: str,
        bucket_name: Optional[str] = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """
        Upload a file to Supabase storage.

        Args:
            local_path (Union[str, Path]): Local file path to upload.
            remote_path (str): Remote path where file will be stored.
            bucket_name (Optional[str]): Bucket name. Uses default if None.
            overwrite (bool): Whether to overwrite existing file. Defaults to False.

        Returns:
            Dict[str, Any]: Response data from Supabase.

        Raises:
            FileNotFoundError: If local file doesn't exist.
            RuntimeError: If upload fails.
        """
        local_path = Path(local_path)
        if not local_path.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")

        bucket = bucket_name or self.default_bucket

        try:
            with open(local_path, "rb") as f:
                file_data = f.read()

            # Determine content type based on file extension
            content_type = self._get_content_type(local_path)

            if overwrite:
                # Remove existing file first if it exists
                try:
                    self.client.storage.from_(bucket).remove([remote_path])
                except Exception:
                    pass  # Ignore error if file doesn't exist

            result = self.client.storage.from_(bucket).upload(
                remote_path, file_data, file_options={"content-type": content_type}
            )

            print(f"✅ Uploaded {local_path} to {bucket}/{remote_path}")
            return result

        except Exception as e:
            raise RuntimeError(f"Failed to upload {local_path}: {str(e)}")

    def download_file(
        self,
        remote_path: str,
        local_path: Union[str, Path],
        bucket_name: Optional[str] = None,
    ) -> bool:
        """
        Download a file from Supabase storage.

        Args:
            remote_path (str): Remote file path in storage.
            local_path (Union[str, Path]): Local path where file will be saved.
            bucket_name (Optional[str]): Bucket name. Uses default if None.

        Returns:
            bool: True if download successful.

        Raises:
            RuntimeError: If download fails.
        """
        local_path = Path(local_path)
        bucket = bucket_name or self.default_bucket

        try:
            # Create directory if it doesn't exist
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # Download file data
            file_data = self.client.storage.from_(bucket).download(remote_path)

            # Write to local file
            with open(local_path, "wb") as f:
                f.write(file_data)

            print(f"✅ Downloaded {bucket}/{remote_path} to {local_path}")
            return True

        except Exception as e:
            raise RuntimeError(f"Failed to download {remote_path}: {str(e)}")

    def list_files(
        self,
        folder_path: str = "",
        bucket_name: Optional[str] = None,
        recursive: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        List files in a Supabase storage bucket or folder.

        Args:
            folder_path (str): Folder path to list. Empty string for root.
            bucket_name (Optional[str]): Bucket name. Uses default if None.
            recursive (bool): Whether to list files recursively. Defaults to False.

        Returns:
            List[Dict[str, Any]]: List of file information dictionaries.

        Raises:
            RuntimeError: If listing fails.
        """
        bucket = bucket_name or self.default_bucket

        try:
            if recursive:
                # For recursive listing, we need to implement our own logic
                return self._list_files_recursive(folder_path, bucket)
            else:
                result = self.client.storage.from_(bucket).list(folder_path)
                print(f"📂 Listed {len(result)} items in {bucket}/{folder_path}")
                return result

        except Exception as e:
            raise RuntimeError(f"Failed to list files in {folder_path}: {str(e)}")

    def _list_files_recursive(
        self, folder_path: str, bucket_name: str
    ) -> List[Dict[str, Any]]:
        """
        Recursively list all files in a folder.

        Args:
            folder_path (str): Starting folder path.
            bucket_name (str): Bucket name.

        Returns:
            List[Dict[str, Any]]: List of all files found recursively.
        """
        all_files = []

        def _explore_folder(path: str):
            items = self.client.storage.from_(bucket_name).list(path)

            for item in items:
                item_path = f"{path}/{item['name']}" if path else item["name"]

                # If it's a file (has size), add it to results
                if item.get("metadata") and item["metadata"].get("size") is not None:
                    item["full_path"] = item_path
                    all_files.append(item)
                # If it's a folder, explore it recursively
                else:
                    _explore_folder(item_path)

        _explore_folder(folder_path)
        return all_files

    def download_json_folder(
        self,
        remote_folder: str,
        local_folder: Union[str, Path],
        bucket_name: Optional[str] = None,
        file_pattern: str = "*.json",
    ) -> Dict[str, Any]:
        """
        Recursively download all JSON files from a folder in Supabase storage.

        Args:
            remote_folder (str): Remote folder path in storage.
            local_folder (Union[str, Path]): Local folder where files will be saved.
            bucket_name (Optional[str]): Bucket name. Uses default if None.
            file_pattern (str): File pattern to match. Defaults to "*.json".

        Returns:
            Dict[str, Any]: Summary of download operation.

        Raises:
            RuntimeError: If download operation fails.
        """
        local_folder = Path(local_folder)
        bucket = bucket_name or self.default_bucket

        try:
            # List all files recursively
            all_files = self._list_files_recursive(remote_folder, bucket)

            # Filter for JSON files
            json_files = []
            for file_info in all_files:
                file_name = file_info["name"]
                if file_name.endswith(".json"):
                    json_files.append(file_info)

            print(
                f"📦 Found {len(json_files)} JSON files to download from {bucket}/{remote_folder}"
            )

            downloaded = []
            failed = []

            for file_info in json_files:
                try:
                    remote_path = file_info["full_path"]

                    # Preserve folder structure locally
                    relative_path = remote_path
                    if remote_folder and remote_path.startswith(remote_folder):
                        relative_path = remote_path[len(remote_folder) :].lstrip("/")

                    local_file_path = local_folder / relative_path

                    # Download the file
                    self.download_file(remote_path, local_file_path, bucket)
                    downloaded.append(
                        {
                            "remote_path": remote_path,
                            "local_path": str(local_file_path),
                            "size": file_info.get("metadata", {}).get("size", 0),
                        }
                    )

                except Exception as e:
                    failed.append(
                        {
                            "remote_path": file_info.get(
                                "full_path", file_info["name"]
                            ),
                            "error": str(e),
                        }
                    )
                    print(f"❌ Failed to download {file_info['name']}: {e}")

            summary = {
                "total_found": len(json_files),
                "downloaded": len(downloaded),
                "failed": len(failed),
                "downloaded_files": downloaded,
                "failed_files": failed,
            }

            print(
                f"📥 Download complete: {len(downloaded)}/{len(json_files)} files downloaded"
            )
            return summary

        except Exception as e:
            raise RuntimeError(
                f"Failed to download JSON folder {remote_folder}: {str(e)}"
            )

    def upload_json_data(
        self,
        data: Union[Dict, List],
        remote_path: str,
        bucket_name: Optional[str] = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """
        Upload JSON data directly to Supabase storage.

        Args:
            data (Union[Dict, List]): JSON-serializable data to upload.
            remote_path (str): Remote path where JSON will be stored.
            bucket_name (Optional[str]): Bucket name. Uses default if None.
            overwrite (bool): Whether to overwrite existing file. Defaults to False.

        Returns:
            Dict[str, Any]: Response data from Supabase.

        Raises:
            RuntimeError: If upload fails.
        """
        bucket = bucket_name or self.default_bucket

        try:
            # Convert data to JSON string
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            json_bytes = json_str.encode("utf-8")

            if overwrite:
                # Remove existing file first if it exists
                try:
                    self.client.storage.from_(bucket).remove([remote_path])
                except Exception:
                    pass  # Ignore error if file doesn't exist

            result = self.client.storage.from_(bucket).upload(
                remote_path,
                json_bytes,
                file_options={"content-type": "application/json"},
            )

            print(f"✅ Uploaded JSON data to {bucket}/{remote_path}")
            return result

        except Exception as e:
            raise RuntimeError(f"Failed to upload JSON data to {remote_path}: {str(e)}")

    def remove_file(self, remote_path: str, bucket_name: Optional[str] = None) -> bool:
        """
        Remove a file from Supabase storage.

        Args:
            remote_path (str): Remote file path to remove.
            bucket_name (Optional[str]): Bucket name. Uses default if None.

        Returns:
            bool: True if removal successful.

        Raises:
            RuntimeError: If removal fails.
        """
        bucket = bucket_name or self.default_bucket

        try:
            result = self.client.storage.from_(bucket).remove([remote_path])
            print(f"🗑️ Removed {bucket}/{remote_path}")
            return True

        except Exception as e:
            raise RuntimeError(f"Failed to remove {remote_path}: {str(e)}")

    def _get_content_type(self, file_path: Path) -> str:
        """
        Determine content type based on file extension.

        Args:
            file_path (Path): File path to check.

        Returns:
            str: MIME type string.
        """
        extension = file_path.suffix.lower()

        content_types = {
            ".json": "application/json",
            ".txt": "text/plain",
            ".csv": "text/csv",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".pdf": "application/pdf",
            ".zip": "application/zip",
            ".tar": "application/x-tar",
            ".gz": "application/gzip",
        }

        return content_types.get(extension, "application/octet-stream")

    def create_bucket(self, bucket_name: str, public: bool = False) -> Dict[str, Any]:
        """
        Create a new storage bucket.

        Args:
            bucket_name (str): Name of the bucket to create.
            public (bool): Whether the bucket should be public. Defaults to False.

        Returns:
            Dict[str, Any]: Response data from Supabase.

        Raises:
            RuntimeError: If bucket creation fails.
        """
        try:
            result = self.client.storage.create_bucket(bucket_name, {"public": public})
            print(f"🪣 Created bucket: {bucket_name} (public: {public})")
            return result

        except Exception as e:
            raise RuntimeError(f"Failed to create bucket {bucket_name}: {str(e)}")

    def list_buckets(self) -> List[Dict[str, Any]]:
        """
        List all storage buckets.

        Returns:
            List[Dict[str, Any]]: List of bucket information.

        Raises:
            RuntimeError: If listing fails.
        """
        try:
            result = self.client.storage.list_buckets()
            print(f"📚 Found {len(result)} buckets")
            return result

        except Exception as e:
            raise RuntimeError(f"Failed to list buckets: {str(e)}")

    # Database operations for site_customers table

    def get_pending_site_customers(self) -> List[Dict[str, Any]]:
        """
        Return customers who have paid but whose site is not yet deployed.
        Relies on the computed column has_successful_payment and is_site_deployed=false.
        """
        try:
            result = (
                self.client.table("site_customers")
                .select("id, first_paid_at, subscription_status, is_site_deployed, storage_folder")
                .filter("has_successful_payment", "eq", True)
                .filter("is_site_deployed", "eq", False)
                .execute()
            )
            return result.data or []
        except Exception as e:
            raise RuntimeError(f"Failed to query pending site customers: {str(e)}")

    def mark_deployed(self, customer_id: str, site_url: Optional[str] = None) -> bool:
        """
        Mark a customer's site as deployed and optionally set the site_url.
        """
        try:
            payload: Dict[str, Any] = {"is_site_deployed": True, "deployed_at": datetime.now().isoformat()}
            if site_url:
                payload["site_url"] = site_url
            result = (
                self.client.table("site_customers")
                .update(payload)
                .eq("id", customer_id)
                .execute()
            )
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to mark deployed for {customer_id}: {str(e)}")

    def query_clients_for_backlinks(
        self, site_url: str, hours_threshold: int, random_fuzz_hours: float
    ) -> List[Dict[str, Any]]:
        """
        Query clients table for clients that need backlinks added.

        Args:
            site_url (str): The site URL to exclude from existing client_backlinks
            hours_threshold (int): Base backlink interval in hours
            random_fuzz_hours (float): Random fuzz to add to threshold

        Returns:
            List[Dict[str, Any]]: List of client records that need backlinks

        Raises:
            RuntimeError: If query fails.
        """
        try:
            # Calculate the cutoff datetime
            from datetime import datetime, timedelta

            cutoff_time = datetime.now() - timedelta(
                hours=hours_threshold + random_fuzz_hours
            )
            cutoff_str = cutoff_time.isoformat()

            # Query clients that need backlinks
            result = (
                self.client.table("clients")
                .select("*")
                .filter("num_backlinks", "lt", "num_desired_backlinks")
                .filter("date_last_backlink_added", "lt", cutoff_str)
                .execute()
            )

            print(f"🔍 Found {len(result.data)} clients needing backlinks")
            return result.data

        except Exception as e:
            raise RuntimeError(f"Failed to query clients for backlinks: {str(e)}")

    def update_client_backlink_info(self, client_id: str) -> bool:
        """
        Update client's backlink information after adding a backlink.

        Args:
            client_id (str): The client UUID to update

        Returns:
            bool: True if update successful

        Raises:
            RuntimeError: If update fails.
        """
        try:
            now = datetime.now().isoformat()

            # First get current num_backlinks to increment it
            current_result = (
                self.client.table("clients")
                .select("num_backlinks")
                .eq("id", client_id)
                .execute()
            )

            if not current_result.data:
                raise RuntimeError(f"Client {client_id} not found")

            current_num = current_result.data[0].get("num_backlinks", 0)
            new_num = current_num + 1

            # Update with incremented value
            result = (
                self.client.table("clients")
                .update({"date_last_backlink_added": now, "num_backlinks": new_num})
                .eq("id", client_id)
                .execute()
            )

            print(
                f"✅ Updated client {client_id} backlink info (now has {new_num} backlinks)"
            )
            return True

        except Exception as e:
            raise RuntimeError(
                f"Failed to update client backlink info for {client_id}: {str(e)}"
            )

    def get_all_clients(self) -> List[Dict[str, Any]]:
        """
        Get all clients from the database.

        Returns:
            List[Dict[str, Any]]: List of all client records

        Raises:
            RuntimeError: If query fails.
        """
        try:
            result = self.client.table("clients").select("*").execute()
            print(f"📋 Retrieved {len(result.data)} total clients")
            return result.data

        except Exception as e:
            raise RuntimeError(f"Failed to get all clients: {str(e)}")
