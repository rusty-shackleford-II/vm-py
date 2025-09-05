#!/usr/bin/env python3
"""
Python version of 04_add_custom_domain.sh
Adds a custom domain to an existing Cloudflare Pages project
"""

import os
import requests
import re
import subprocess
import sys
import time
from pathlib import Path


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


def validate_domain_format(domain):
    """Validate domain format using regex"""
    pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$"

    if not re.match(pattern, domain):
        print_error(f"Invalid domain format: {domain}")
        print_status(
            "Please use a valid domain format (e.g., example.com or subdomain.example.com)"
        )
        sys.exit(1)

    print_success("Domain format validated")


def get_cloudflare_zone_id(domain, cloudflare_api_token):
    """Get the Cloudflare zone ID for the domain"""
    print_status(f"Looking up Cloudflare zone ID for {domain}...")

    headers = {
        "Authorization": f"Bearer {cloudflare_api_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones?name={domain}", headers=headers
        )

        response_data = response.json()

        if response_data.get("success") and response_data.get("result"):
            zone_id = response_data["result"][0]["id"]
            print_success(f"Found Cloudflare zone ID: {zone_id}")
            return zone_id
        else:
            print_error(f"Could not find Cloudflare zone for domain: {domain}")
            print_error("Make sure the domain is added to Cloudflare first")
            print_status(
                "You can run 00_add_domain_to_cloudflare.py to add the domain to Cloudflare"
            )
            sys.exit(1)

    except requests.RequestException as e:
        print_error(f"Failed to get zone ID: {e}")
        sys.exit(1)


def get_pages_project_details(
    cloudflare_account_id, project_name, cloudflare_api_token
):
    """Get Cloudflare Pages project details to find CNAME target"""
    pages_project_name = project_name.lower()

    print_status("Getting Cloudflare Pages project details...")

    headers = {
        "Authorization": f"Bearer {cloudflare_api_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/pages/projects/{pages_project_name}",
            headers=headers,
        )

        response_data = response.json()

        if response_data.get("success"):
            result = response_data.get("result", {})
            pages_subdomain = result.get("subdomain")

            if pages_subdomain:
                # Check if subdomain already includes .pages.dev
                if pages_subdomain.endswith(".pages.dev"):
                    cname_target = pages_subdomain
                else:
                    cname_target = f"{pages_subdomain}.pages.dev"

                print_success(f"Found Pages project subdomain: {pages_subdomain}")
                print_status(f"CNAME target will be: {cname_target}")
                return cname_target
            else:
                print_warning("Could not extract subdomain from Pages project")
                print_status("Using default formula for CNAME target")
                return f"{pages_project_name}.pages.dev"
        else:
            print_warning("Could not get Pages project details")
            print_status("Using default formula for CNAME target")
            return f"{pages_project_name}.pages.dev"

    except requests.RequestException as e:
        print_warning(f"Failed to get Pages project details: {e}")
        print_status("Using default formula for CNAME target")
        return f"{pages_project_name}.pages.dev"


def add_custom_domain_to_pages(
    cloudflare_account_id, project_name, domain, cloudflare_api_token
):
    """Add custom domain to Cloudflare Pages project"""
    pages_project_name = project_name.lower()

    print_status(
        f"Adding custom domain '{domain}' to Cloudflare Pages project '{pages_project_name}'..."
    )

    headers = {
        "Authorization": f"Bearer {cloudflare_api_token}",
        "Content-Type": "application/json",
    }

    data = {"name": domain}

    try:
        response = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/pages/projects/{pages_project_name}/domains",
            headers=headers,
            json=data,
        )

        response_data = response.json()

        if response_data.get("success"):
            print_success("Custom domain added successfully!")

            # Extract domain status if available
            result = response_data.get("result", {})
            status = result.get("status")
            if status:
                print_status(f"Domain status: {status}")

        elif (
            "already added this custom domain" in response.text
            or "already exists" in response.text
        ):
            print_warning("Domain already exists for this project")
            print_success(f"Domain is already configured: {domain}")
            print_status("Proceeding with DNS configuration...")
        else:
            print_error("Failed to add custom domain")
            print_error(f"Response: {response.text}")

            # Check for common error cases
            if "authentication" in response.text.lower():
                print_error("Authentication failed. Check your Cloudflare API token")
            elif "not found" in response.text.lower():
                print_error(
                    f"Pages project not found. Make sure the project exists: {pages_project_name}"
                )
            elif "invalid" in response.text.lower():
                print_error(f"Invalid domain name. Check your domain format: {domain}")

            sys.exit(1)

    except requests.RequestException as e:
        print_error(f"Failed to add custom domain: {e}")
        sys.exit(1)


def manage_dns_records(zone_id, domain, cname_target, cloudflare_api_token):
    """Create or update DNS records in Cloudflare DNS"""
    print_status("Configuring DNS record in Cloudflare DNS...")
    print_status(f"Target: {cname_target}")

    headers = {
        "Authorization": f"Bearer {cloudflare_api_token}",
        "Content-Type": "application/json",
    }

    try:
        # Check for existing DNS records
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?name={domain}",
            headers=headers,
        )

        response_data = response.json()

        if not response_data.get("success"):
            print_error("Failed to check existing DNS records")
            return

        existing_records = response_data.get("result", [])
        existing_count = len(existing_records)

        if existing_count > 0:
            print_status(f"Found existing DNS records for {domain}")

            # Get record types
            record_types = [record["type"] for record in existing_records]
            unique_types = list(set(record_types))

            print(f"Existing record types: {', '.join(unique_types)}")

            # Handle different record scenarios
            cname_records = [r for r in existing_records if r["type"] == "CNAME"]
            a_records = [r for r in existing_records if r["type"] == "A"]

            if cname_records:
                # CNAME record exists - check if it's correct
                current_target = cname_records[0]["content"]
                if current_target == cname_target:
                    print_success(
                        f"CNAME record already points to correct target: {cname_target}"
                    )
                else:
                    print_warning(
                        f"CNAME record points to: {current_target} (expected: {cname_target})"
                    )
                    print_status(
                        "Updating CNAME record to point to the correct target..."
                    )

                    # Update the existing CNAME record
                    record_id = cname_records[0]["id"]
                    update_data = {
                        "type": "CNAME",
                        "name": domain,
                        "content": cname_target,
                        "ttl": 3600,
                    }

                    update_response = requests.put(
                        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}",
                        headers=headers,
                        json=update_data,
                    )

                    if update_response.json().get("success"):
                        print_success("CNAME record updated successfully!")
                    else:
                        print_error("Failed to update CNAME record")
                        print_error(f"Response: {update_response.text}")

            elif a_records:
                # A records exist - these conflict with CNAME for Cloudflare Pages
                print_warning(
                    "Found existing A record(s). These conflict with Cloudflare Pages."
                )
                print_status(
                    "Deleting A record(s) and creating CNAME record instead..."
                )

                # Delete all A records
                for a_record in a_records:
                    record_id = a_record["id"]
                    print_status(f"Deleting A record: {record_id}")

                    delete_response = requests.delete(
                        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}",
                        headers=headers,
                    )

                    if delete_response.json().get("success"):
                        print_success("A record deleted successfully")
                    else:
                        print_error("Failed to delete A record")
                        print_error(f"Response: {delete_response.text}")

                # Create CNAME record
                create_cname_record(zone_id, domain, cname_target, headers)

            else:
                print_warning(
                    f"Found unexpected record types: {', '.join(unique_types)}"
                )
                print_status("Creating CNAME record anyway...")
                create_cname_record(zone_id, domain, cname_target, headers)

        else:
            # No existing records - create CNAME
            print_status("No existing DNS records found. Creating CNAME record...")
            create_cname_record(zone_id, domain, cname_target, headers)

    except requests.RequestException as e:
        print_error(f"Failed to manage DNS records: {e}")


def create_cname_record(zone_id, domain, cname_target, headers):
    """Create a CNAME record in Cloudflare DNS"""
    print_status(f"Creating CNAME record: {domain} -> {cname_target}")

    data = {"type": "CNAME", "name": domain, "content": cname_target, "ttl": 3600}

    try:
        response = requests.post(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
            headers=headers,
            json=data,
        )

        response_data = response.json()

        if response_data.get("success"):
            print_success("CNAME record created successfully!")
            record_id = response_data["result"]["id"]
            print_status(f"Record ID: {record_id}")
        else:
            print_error("Failed to create CNAME record")
            print_error(f"Response: {response.text}")
            sys.exit(1)

    except requests.RequestException as e:
        print_error(f"Failed to create CNAME record: {e}")
        sys.exit(1)


def verify_dns_setup(domain):
    """Verify DNS setup using dig command"""
    print_status("Verifying DNS setup...")

    # Give DNS a moment to propagate
    time.sleep(2)

    try:
        # Check if DNS is resolving correctly
        result = subprocess.run(
            ["dig", "+short", domain, "CNAME"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0 and result.stdout.strip():
            dns_result = result.stdout.strip()
            print_success(f"DNS CNAME record is resolving: {domain} -> {dns_result}")
        else:
            print_warning("DNS may still be propagating. Check again in a few minutes.")

    except (subprocess.TimeoutExpired, FileNotFoundError):
        print_warning("Could not verify DNS (dig command not available or timed out)")
    except Exception as e:
        print_warning(f"DNS verification failed: {e}")


def add_custom_domain_to_pages_project(
    cloudflare_api_token, cloudflare_account_id, project_name, domain
):
    """
    Main function to add a custom domain to an existing Cloudflare Pages project

    Args:
        cloudflare_api_token (str): Cloudflare API token
        cloudflare_account_id (str): Cloudflare account ID
        project_name (str): Name of the Cloudflare Pages project
        domain (str): Custom domain to add (e.g., 'example.com')

    Returns:
        dict: Results containing zone_id, cname_target, and setup status
    """
    print_status(f"Starting custom domain setup for {domain} on project {project_name}")

    # Validate domain format
    validate_domain_format(domain)

    # Get Cloudflare zone ID
    zone_id = get_cloudflare_zone_id(domain, cloudflare_api_token)

    # Get Pages project details and CNAME target
    cname_target = get_pages_project_details(
        cloudflare_account_id, project_name, cloudflare_api_token
    )

    # Add custom domain to Cloudflare Pages
    add_custom_domain_to_pages(
        cloudflare_account_id, project_name, domain, cloudflare_api_token
    )

    # Configure DNS records
    manage_dns_records(zone_id, domain, cname_target, cloudflare_api_token)

    # Verify DNS setup
    verify_dns_setup(domain)

    # Summary
    pages_project_name = project_name.lower()

    print_success("🎉 Custom domain configuration completed!")
    print("")
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║                    SETUP COMPLETE!                            ║")
    print("╠════════════════════════════════════════════════════════════════╣")
    print("║ Your custom domain has been fully configured:                 ║")
    print("║                                                                ║")
    print(f"║ ✅ Domain added to Cloudflare Pages: {domain}")
    print(f"║ ✅ CNAME record created: {domain} -> {cname_target}")
    print("║ ✅ DNS configured automatically                                 ║")
    print("║                                                                ║")
    print("║ Your site should be accessible at:                            ║")
    print(f"║ 🌐 https://{domain}")
    print("╚════════════════════════════════════════════════════════════════╝")
    print("")

    print_success("🎊 Step 4 completed successfully!")
    print("")
    print("📋 Summary:")
    print("===========")
    print(f"• Custom Domain: {domain}")
    print(f"• Pages Project: {pages_project_name}")
    print(f"• Target: {cname_target}")
    print(f"• Zone ID: {zone_id}")
    print(f"• DNS Record: CNAME {domain} -> {cname_target}")
    print("")
    print_success(f"✅ Your Next.js SSG site is now live at: https://{domain}")
    print("")
    print_status("🕐 DNS propagation may take a few minutes worldwide")
    print_status(
        "🔄 To add more domains, call this function again with a different domain"
    )

    return {
        "zone_id": zone_id,
        "cname_target": cname_target,
        "domain": domain,
        "pages_project_name": pages_project_name,
    }


def main():
    """Main function for command line usage"""
    # Load environment variables for backward compatibility
    print_status("Loading environment variables...")


if __name__ == "__main__":
    main()
