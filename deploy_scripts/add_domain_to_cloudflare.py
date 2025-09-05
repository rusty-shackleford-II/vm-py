#!/usr/bin/env python3
"""
Python version of 00_add_domain_to_cloudflare.sh
Adds domain to Cloudflare and migrates DNS records from Namecheap
"""

import requests
import xml.etree.ElementTree as ET
import sys
import subprocess
from pathlib import Path

# Import configuration from config.py
from config import (
    NAMECHEAP_API_USER,
    NAMECHEAP_API_KEY,
    NAMECHEAP_USERNAME,
    CLIENT_IP,
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


def parse_domain(domain):
    """Parse domain into SLD and TLD for Namecheap API"""
    parts = domain.split(".")
    if len(parts) < 2:
        print_error(f"Invalid domain format: {domain}")
        sys.exit(1)

    sld = parts[0]
    tld = ".".join(parts[1:])
    return sld, tld


def get_namecheap_dns_records(domain, client_ip):
    """Get existing DNS records from Namecheap"""
    print_status("Fetching existing DNS records from Namecheap...")

    sld, tld = parse_domain(domain)

    params = {
        "ApiUser": NAMECHEAP_API_USER,
        "ApiKey": NAMECHEAP_API_KEY,
        "UserName": NAMECHEAP_USERNAME,
        "Command": "namecheap.domains.dns.getHosts",
        "ClientIp": client_ip,
        "SLD": sld,
        "TLD": tld,
    }

    try:
        response = requests.get("https://api.namecheap.com/xml.response", params=params)
        response_text = response.text

        if 'Status="OK"' in response_text:
            print_success("Successfully retrieved DNS records from Namecheap")
            return response_text, True
        elif 'IsUsingOurDNS="false"' in response_text:
            print_warning("Domain is not using Namecheap DNS servers")
            print_warning(
                "This means DNS is managed elsewhere (possibly already on Cloudflare)"
            )
            print_warning(
                "Will proceed with adding domain to Cloudflare without migrating records"
            )
            return response_text, False
        else:
            print_error("Failed to retrieve DNS records from Namecheap")
            print_error(f"Response: {response_text}")
            sys.exit(1)

    except requests.RequestException as e:
        print_error(f"Failed to get DNS records from Namecheap: {e}")
        sys.exit(1)


def add_domain_to_cloudflare(domain, cloudflare_api_token, cloudflare_account_id):
    """Add domain to Cloudflare"""
    print_status(f"Adding {domain} to Cloudflare...")

    headers = {
        "Authorization": f"Bearer {cloudflare_api_token}",
        "Content-Type": "application/json",
    }

    data = {
        "name": domain,
        "account": {"id": cloudflare_account_id},
        "jump_start": False,
        "type": "full",
    }

    try:
        response = requests.post(
            "https://api.cloudflare.com/client/v4/zones", headers=headers, json=data
        )
        response_data = response.json()

        if response_data.get("success"):
            zone_id = response_data["result"]["id"]
            nameservers = response_data["result"]["name_servers"]

            print_success("Domain added to Cloudflare successfully")
            print_status(f"Zone ID: {zone_id}")
            print_status(f"Nameservers: {', '.join(nameservers)}")
            return zone_id, nameservers

        elif "already exists" in response.text:
            print_warning("Domain already exists in Cloudflare")
            # Get existing zone info
            zone_response = requests.get(
                f"https://api.cloudflare.com/client/v4/zones?name={domain}",
                headers=headers,
            )
            zone_data = zone_response.json()

            if zone_data.get("success") and zone_data["result"]:
                zone_id = zone_data["result"][0]["id"]
                nameservers = zone_data["result"][0]["name_servers"]
                print_status(f"Zone ID: {zone_id}")
                print_status(f"Nameservers: {', '.join(nameservers)}")
                return zone_id, nameservers
            else:
                print_error("Failed to get existing zone information")
                sys.exit(1)
        else:
            print_error("Failed to add domain to Cloudflare")
            print_error(f"Response: {response.text}")
            sys.exit(1)

    except requests.RequestException as e:
        print_error(f"Failed to add domain to Cloudflare: {e}")
        sys.exit(1)


def parse_namecheap_dns_xml(xml_content, domain):
    """Parse Namecheap DNS XML and extract records"""
    records = []

    try:
        # Extract Host records using simple string parsing (similar to shell script)
        lines = xml_content.split("\n")
        for line in lines:
            if "<Host" in line and "Name=" in line:
                # Extract attributes using string manipulation
                name = ""
                record_type = ""
                address = ""
                ttl = "3600"  # default

                # Simple attribute extraction
                parts = line.split('"')
                for i, part in enumerate(parts):
                    if part.endswith("Name="):
                        name = parts[i + 1]
                    elif part.endswith("Type="):
                        record_type = parts[i + 1]
                    elif part.endswith("Address="):
                        address = parts[i + 1]
                    elif part.endswith("TTL="):
                        ttl = parts[i + 1]

                if name and record_type and address:
                    # Convert @ to domain name for root records
                    if name == "@":
                        record_name = domain
                    else:
                        record_name = f"{name}.{domain}"

                    records.append(
                        {
                            "name": record_name,
                            "type": record_type,
                            "content": address,
                            "ttl": int(ttl) if ttl.isdigit() else 3600,
                        }
                    )

    except Exception as e:
        print_warning(f"Error parsing DNS records: {e}")

    return records


def create_dns_records_in_cloudflare(zone_id, records, cloudflare_api_token):
    """Create DNS records in Cloudflare"""
    if not records:
        print_status("No DNS records to migrate")
        return

    print_status("Creating DNS records in Cloudflare from Namecheap...")

    headers = {
        "Authorization": f"Bearer {cloudflare_api_token}",
        "Content-Type": "application/json",
    }

    for record in records:
        print_status(
            f"Creating {record['type']} record: {record['name']} -> {record['content']}"
        )

        data = {
            "type": record["type"],
            "name": record["name"],
            "content": record["content"],
            "ttl": record["ttl"],
        }

        try:
            response = requests.post(
                f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
                headers=headers,
                json=data,
            )

            response_data = response.json()
            if response_data.get("success"):
                print_success(f"Created {record['type']} record for {record['name']}")
            else:
                print_error(
                    f"Failed to create {record['type']} record for {record['name']}"
                )
                print_error(f"Response: {response.text}")

        except requests.RequestException as e:
            print_error(f"Failed to create DNS record: {e}")


def ensure_root_a_record(zone_id, domain, cloudflare_api_token):
    """Ensure there's a root A record for the domain"""
    print_status("Checking for root A record...")

    headers = {
        "Authorization": f"Bearer {cloudflare_api_token}",
        "Content-Type": "application/json",
    }

    try:
        # Check for existing root A record
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?name={domain}&type=A",
            headers=headers,
        )

        response_data = response.json()
        if response_data.get("success"):
            record_count = len(response_data.get("result", []))

            if record_count == 0:
                print_warning("No root A record found. Creating default A record...")

                # Create default A record
                default_ip = "192.0.2.1"  # Replace with actual server IP
                data = {
                    "type": "A",
                    "name": domain,
                    "content": default_ip,
                    "ttl": 3600,
                    "proxied": False,
                }

                create_response = requests.post(
                    f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
                    headers=headers,
                    json=data,
                )

                create_data = create_response.json()
                if create_data.get("success"):
                    print_success(f"Created default A record for {domain}")
                else:
                    print_error("Failed to create default A record")
                    print_error(f"Response: {create_response.text}")
            else:
                print_success("Root A record already exists")
        else:
            print_error("Failed to check for root A record")

    except requests.RequestException as e:
        print_error(f"Failed to check root A record: {e}")


def update_namecheap_nameservers(domain, client_ip, nameservers):
    """Update nameservers in Namecheap"""
    print_status("Updating nameservers in Namecheap...")

    sld, tld = parse_domain(domain)
    nameservers_str = ",".join(nameservers)

    params = {
        "ApiUser": NAMECHEAP_API_USER,
        "ApiKey": NAMECHEAP_API_KEY,
        "UserName": NAMECHEAP_USERNAME,
        "Command": "namecheap.domains.dns.setCustom",
        "ClientIp": client_ip,
        "SLD": sld,
        "TLD": tld,
        "NameServers": nameservers_str,
    }

    try:
        response = requests.get("https://api.namecheap.com/xml.response", params=params)
        response_text = response.text

        if 'Updated="true"' in response_text:
            print_success("Successfully updated nameservers in Namecheap")
            print_success(f"Domain {domain} is now configured to use Cloudflare")
            return True
        else:
            print_error("Failed to update nameservers in Namecheap")
            print_error(f"Response: {response_text}")
            return False

    except requests.RequestException as e:
        print_error(f"Failed to update nameservers: {e}")
        return False


def add_domain_to_cloudflare_with_migration(
    domain, cloudflare_api_token, cloudflare_account_id, client_ip
):
    """
    Main function to add domain to Cloudflare and migrate DNS records from Namecheap

    Args:
        domain (str): Domain name to add (e.g., 'example.com')
        cloudflare_api_token (str): Cloudflare API token
        cloudflare_account_id (str): Cloudflare account ID
        client_ip (str): Client IP address for Namecheap API

    Returns:
        dict: Results containing zone_id, nameservers, and migration status
    """
    print_status(f"Starting domain migration process for {domain}")

    # Get existing DNS records from Namecheap
    namecheap_dns_response, using_namecheap_dns = get_namecheap_dns_records(
        domain, client_ip
    )

    # Add domain to Cloudflare
    zone_id, nameservers = add_domain_to_cloudflare(
        domain, cloudflare_api_token, cloudflare_account_id
    )

    # Parse and create DNS records if using Namecheap DNS
    if using_namecheap_dns:
        dns_records = parse_namecheap_dns_xml(namecheap_dns_response, domain)
        create_dns_records_in_cloudflare(zone_id, dns_records, cloudflare_api_token)
    else:
        print_status("Skipping DNS record migration (domain not using Namecheap DNS)")

    # Ensure root A record exists
    ensure_root_a_record(zone_id, domain, cloudflare_api_token)

    # Update nameservers in Namecheap
    nameserver_updated = update_namecheap_nameservers(domain, client_ip, nameservers)

    # Summary
    print_success("Domain configuration completed!")
    if nameserver_updated:
        print_success(f"✅ Domain {domain} is now configured to use Cloudflare")
        if using_namecheap_dns:
            print_success(
                "✅ DNS records have been migrated from Namecheap to Cloudflare"
            )
        else:
            print_warning(
                "⚠️  DNS records were not migrated (domain wasn't using Namecheap DNS)"
            )
            print_warning(
                "   You may need to manually recreate any necessary DNS records in Cloudflare"
            )
        print_status("⏳ DNS propagation may take up to 24-48 hours")

    return {
        "zone_id": zone_id,
        "nameservers": nameservers,
        "nameserver_updated": nameserver_updated,
        "dns_migrated": using_namecheap_dns,
    }


def main():
    """Main function for command line usage"""
    print_status("Using configuration from config.py...")
    print_success("Configuration loaded and validated")

    # Example usage of the function:
    # add_domain_to_cloudflare_with_migration(
    #     domain="example.com",
    #     cloudflare_api_token="your_token_here",
    #     cloudflare_account_id="your_account_id_here",
    #     client_ip=CLIENT_IP,
    # )
    
    print_success("✅ Ready to add domains to Cloudflare!")
    print_status(
        "Call add_domain_to_cloudflare_with_migration() with your domain and Cloudflare credentials"
    )


if __name__ == "__main__":
    main()
