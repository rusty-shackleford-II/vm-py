from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
import requests
import xml.etree.ElementTree as ET
import config


class NamecheapClient:
    """
    Minimal Namecheap API client for domain availability search.

    Uses credentials from config.py and supports sandbox/production selection
    via NAMECHEAP_SANDBOX env var ("true" to use sandbox).
    """

    def __init__(
        self,
        api_user: Optional[str] = None,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        client_ip: Optional[str] = None,
        sandbox: Optional[bool] = None,
        debug: Optional[bool] = None,
    ) -> None:
        self.api_user = api_user or getattr(config, "NAMECHEAP_API_USER", None)
        self.api_key = api_key or getattr(config, "NAMECHEAP_API_KEY", None)
        self.username = username or getattr(config, "NAMECHEAP_USERNAME", None)
        self.client_ip = client_ip or getattr(config, "CLIENT_IP", None)

        if sandbox is None:
            sandbox = os.getenv("NAMECHEAP_SANDBOX", "false").lower() == "true"
        self.sandbox = sandbox

        if debug is None:
            debug = os.getenv("NAMECHEAP_DEBUG", "false").lower() == "true"
        self.debug = debug

        if not all([self.api_user, self.api_key, self.username, self.client_ip]):
            raise ValueError(
                "Missing Namecheap credentials (NAMECHEAP_API_USER, NAMECHEAP_API_KEY, NAMECHEAP_USERNAME, CLIENT_IP)."
            )

        self.base_url = (
            "https://api.sandbox.namecheap.com/xml.response"
            if self.sandbox
            else "https://api.namecheap.com/xml.response"
        )

    def check_domain_availability(self, domains: List[str]) -> List[Dict[str, Any]]:
        """
        Use namecheap.domains.check to get availability for given domains.
        Returns list of { domain: str, available: bool, raw: dict }
        """
        if not domains:
            return []

        params = {
            "ApiUser": str(self.api_user),
            "ApiKey": str(self.api_key),
            "UserName": str(self.username),
            "ClientIp": str(self.client_ip),
            "Command": "namecheap.domains.check",
            "DomainList": ",".join(domains),
        }

        try:
            resp = requests.get(self.base_url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Namecheap request failed: {exc}") from exc

        if self.debug:
            safe_params = dict(params)
            if "ApiKey" in safe_params:
                safe_params["ApiKey"] = "***REDACTED***"
            print("[NC DEBUG] domains.check params:", safe_params)
            print("[NC DEBUG] domains.check XML:")
            print(resp.text)

        return self._parse_check_response(resp.text)

    def _parse_check_response(self, xml_text: str) -> List[Dict[str, Any]]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise RuntimeError(f"Invalid XML from Namecheap: {exc}") from exc

        # Strip XML namespaces for simpler querying
        for elem in root.iter():
            if isinstance(elem.tag, str) and '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]

        status = root.attrib.get("Status")
        if status != "OK":
            # Collect all error messages if present
            error_nodes = root.findall(".//Errors/Error")
            if error_nodes:
                messages = []
                for en in error_nodes:
                    number = en.attrib.get("Number") or en.attrib.get("number")
                    text = (en.text or "").strip()
                    msg = f"[{number}] {text}" if number else text
                    messages.append(msg)
                raise RuntimeError("Namecheap API error: " + "; ".join(m for m in messages if m))
            # Fallback: include raw XML snippet for visibility
            snippet = xml_text[:500].replace("\n", " ")
            raise RuntimeError(f"Namecheap API error (no message). Raw snippet: {snippet}")

        results: List[Dict[str, Any]] = []
        for node in root.findall(".//DomainCheckResult"):
            attrib = node.attrib
            domain = attrib.get("Domain") or attrib.get("DomainName")
            available_attr = attrib.get("Available") or attrib.get("IsAvailable")
            available = (str(available_attr).lower() == "true") if available_attr is not None else False
            results.append({"domain": domain, "available": available, "raw": attrib})

        return results

    # -------------------- Pricing helpers (users.getPricing) -------------------- #
    def _get_tld_pricing(self, tld: str) -> Dict[str, Any]:
        """
        Query Namecheap users.getPricing for a single TLD and return
        { register: { price, currency }, renew: { price, currency } }.
        """
        tld_upper = tld.strip(".").upper()

        def _pricing_for(action: str) -> Dict[str, Any]:
            params = {
                "ApiUser": str(self.api_user),
                "ApiKey": str(self.api_key),
                "UserName": str(self.username),
                "ClientIp": str(self.client_ip),
                "Command": "namecheap.users.getPricing",
                "ProductType": "DOMAIN",
                "ProductCategory": action,  # REGISTER or RENEW
                "ProductName": tld_upper,
                # Some accounts expect ActionName too; harmless if ignored
                "ActionName": action,
            }
            try:
                resp = requests.get(self.base_url, params=params, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as exc:
                raise RuntimeError(f"Namecheap getPricing failed: {exc}") from exc

            if self.debug:
                safe_params = dict(params)
                if "ApiKey" in safe_params:
                    safe_params["ApiKey"] = "***REDACTED***"
                print("[NC DEBUG] users.getPricing params:", safe_params)
                print("[NC DEBUG] users.getPricing XML (", action, "):")
                print(resp.text)

            return self._parse_pricing_response(resp.text, action.lower())

        register = _pricing_for("REGISTER")
        renew = _pricing_for("RENEW")
        return {"register": register, "renew": renew}

    def _parse_pricing_response(self, xml_text: str, action_lower: str) -> Dict[str, Any]:
        # Extract first Price node attributes
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise RuntimeError(f"Invalid XML from Namecheap pricing: {exc}") from exc

        # Strip namespaces
        for elem in root.iter():
            if isinstance(elem.tag, str) and '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]

        status = root.attrib.get("Status")
        if status != "OK":
            error_node = root.find(".//Errors/Error")
            error_msg = (error_node.text or "").strip() if error_node is not None else "Unknown error"
            raise RuntimeError(f"Namecheap pricing API error: {error_msg}")

        result: Dict[str, Any] = {"price": None, "currency": None}
        # Flexible scan for a Price element regardless of case for names
        # Find ProductType where Name in {domain, domains}
        for pt in root.findall(".//ProductType"):
            pt_name = (pt.attrib.get("Name") or "").lower()
            if pt_name not in ("domain", "domains"):
                continue
            # Find ProductCategory where Name equals action_lower (register/renew)
            for cat in pt.findall(".//ProductCategory"):
                cat_name = (cat.attrib.get("Name") or "").lower()
                if cat_name != action_lower:
                    continue
                for price_node in cat.findall(".//Price"):
                    duration = price_node.attrib.get("Duration") or price_node.attrib.get("duration")
                    price_val = price_node.attrib.get("Price") or price_node.attrib.get("price")
                    currency = price_node.attrib.get("Currency") or price_node.attrib.get("currency")
                    # Pick first duration 1, else fallback to any
                    if duration in (None, "1"):
                        result["price"] = float(price_val) if price_val is not None else None
                        result["currency"] = currency
                        return result
                    if result["price"] is None and price_val is not None:
                        result["price"] = float(price_val)
                        result["currency"] = currency
        return result

    # -------------------- High-level features required -------------------- #
    def search_domains_with_prices(self, query: str, tlds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Compose a list of candidate domains from query and TLDs, check availability,
        and enrich with register/renew pricing per TLD.

        Returns list of { domain, available, purchase_price, purchase_currency, renew_price, renew_currency }
        """
        if not tlds:
            tlds = [".com", ".net", ".org", ".io", ".co", ".ai", ".dev"]
        candidates: List[str] = []
        if "." in query:
            candidates = [query]
            # ensure TLD list includes this domain's TLD for pricing
            try:
                dot = query.rindex(".")
                q_tld = query[dot + 1 :]
                if f".{q_tld}" not in tlds:
                    tlds.append(f".{q_tld}")
            except ValueError:
                pass
        else:
            candidates = [f"{query}{t}" for t in tlds]

        # Respect Namecheap 50-domain per call limit
        chunks: List[List[str]] = [candidates[i : i + 50] for i in range(0, len(candidates), 50)]
        availability: Dict[str, Dict[str, Any]] = {}
        for chunk in chunks:
            for item in self.check_domain_availability(chunk):
                availability[item["domain"]] = item

        # Cache pricing per TLD
        pricing_cache: Dict[str, Dict[str, Any]] = {}

        results: List[Dict[str, Any]] = []
        for domain in candidates:
            dot = domain.rfind(".")
            tld = domain[dot + 1 :] if dot != -1 else ""
            if tld and tld not in pricing_cache:
                try:
                    pricing_cache[tld] = self._get_tld_pricing(tld)
                except Exception:
                    pricing_cache[tld] = {"register": {"price": None, "currency": None}, "renew": {"price": None, "currency": None}}

            pricing = pricing_cache.get(tld, {"register": {}, "renew": {}})
            item = availability.get(domain, {"domain": domain, "available": False})
            results.append(
                {
                    "domain": domain,
                    "available": bool(item.get("available")),
                    "purchase_price": pricing.get("register", {}).get("price"),
                    "purchase_currency": pricing.get("register", {}).get("currency"),
                    "renew_price": pricing.get("renew", {}).get("price"),
                    "renew_currency": pricing.get("renew", {}).get("currency"),
                    "raw": item.get("raw"),
                }
            )

        return results

    def purchase_domain(
        self,
        domain: str,
        years: int = 1,
        auto_renew: bool = True,
        contacts: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Register a domain via namecheap.domains.create.

        Requires contact fields unless your account has defaults configured.
        Provide contacts dict with keys like RegistrantFirstName, RegistrantLastName,
        RegistrantAddress1, RegistrantCity, RegistrantStateProvince, RegistrantPostalCode,
        RegistrantCountry, RegistrantPhone, RegistrantEmailAddress (and Admin/Tech/AuxBilling
        equivalents). If contacts is None, we attempt to read prefixes from environment with
        NC_REGISTRANT_*, NC_ADMIN_*, NC_TECH_*, NC_AUX_*.
        """
        params = {
            "ApiUser": str(self.api_user),
            "ApiKey": str(self.api_key),
            "UserName": str(self.username),
            "ClientIp": str(self.client_ip),
            "Command": "namecheap.domains.create",
            "DomainName": domain,
            "Years": str(years),
            "AddFreeWhoisguard": "yes",
            "WGEnabled": "yes",
            "AutoRenew": "true" if auto_renew else "false",
        }

        def _apply(prefix: str, target_prefix: str) -> None:
            mapping = {
                "FirstName": "FirstName",
                "LastName": "LastName",
                "Address1": "Address1",
                "City": "City",
                "StateProvince": "StateProvince",
                "PostalCode": "PostalCode",
                "Country": "Country",
                "Phone": "Phone",
                "EmailAddress": "EmailAddress",
            }
            for k, v in mapping.items():
                env_key = f"{prefix}_{k}"  # e.g., NC_REGISTRANT_FirstName
                val = os.getenv(env_key)
                if val:
                    params[f"{target_prefix}{v}"] = val

        if contacts:
            for key, val in contacts.items():
                params[key] = val
        else:
            # Pull from environment if present
            _apply("NC_REGISTRANT", "Registrant")
            _apply("NC_ADMIN", "Admin")
            _apply("NC_TECH", "Tech")
            _apply("NC_AUX", "AuxBilling")

        try:
            resp = requests.post(self.base_url, params=params, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Namecheap domains.create failed: {exc}") from exc

        # Return raw XML for caller to inspect
        return {"success": True, "raw": resp.text}

    def set_auto_renew(self, domain: str, auto_renew: bool) -> Dict[str, Any]:
        params = {
            "ApiUser": str(self.api_user),
            "ApiKey": str(self.api_key),
            "UserName": str(self.username),
            "ClientIp": str(self.client_ip),
            "Command": "namecheap.domains.setAutoRenew",
            "DomainName": domain,
            "AutoRenew": "true" if auto_renew else "false",
        }
        try:
            resp = requests.post(self.base_url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Namecheap setAutoRenew failed: {exc}") from exc
        return {"success": True, "raw": resp.text}

    def update_nameservers(self, domain: str, nameservers: List[str]) -> Dict[str, Any]:
        params = {
            "ApiUser": str(self.api_user),
            "ApiKey": str(self.api_key),
            "UserName": str(self.username),
            "ClientIp": str(self.client_ip),
            "Command": "namecheap.domains.dns.setCustom",
            "SLD": domain.split(".")[0],
            "TLD": ".".join(domain.split(".")[1:]),
            "Nameservers": ",".join(nameservers),
        }
        try:
            resp = requests.post(self.base_url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Namecheap setCustom failed: {exc}") from exc
        return {"success": True, "raw": resp.text}

    # def transfer_dns_to_cloudflare(self, domain: str) -> Dict[str, Any]:
    #     token = os.getenv("CLOUDFLARE_API_TOKEN")
    #     if token:
    #         headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    #         try:
    #             resp = requests.get(
    #                 "https://api.cloudflare.com/client/v4/zones",
    #                 headers=headers,
    #                 params={"name": domain, "status": "active"},
    #                 timeout=20,
    #             )
    #             data = resp.json()
    #             if not data.get("success"):
    #                 raise RuntimeError(f"Cloudflare zones lookup failed: {data}")
    #             results = data.get("result") or []
    #             if not results:
    #                 raise RuntimeError(
    #                     "Cloudflare zone not found or not active. Create the zone first or wait for activation."
    #                 )
    #             zone = results[0]
    #             nameservers = zone.get("name_servers") or zone.get("original_name_servers")
    #             if not nameservers or len(nameservers) < 2:
    #                 raise RuntimeError("Cloudflare did not return nameservers for this zone.")
    #             return self.update_nameservers(domain, [str(nameservers[0]), str(nameservers[1])])
    #         except requests.RequestException as exc:
    #             raise RuntimeError(f"Failed to query Cloudflare API: {exc}") from exc

    #     ns1 = os.getenv("CLOUDFLARE_NS1")
    #     ns2 = os.getenv("CLOUDFLARE_NS2")
    #     if ns1 and ns2:
    #         return self.update_nameservers(domain, [ns1, ns2])
    #     raise ValueError(
    #         "Missing Cloudflare configuration. Set CLOUDFLARE_API_TOKEN to auto-detect NS, or provide CLOUDFLARE_NS1/NS2."
    #     )

    def get_purchased_domains(self) -> List[Dict[str, Any]]:
        """
        Get list of purchased domains from Namecheap account using namecheap.domains.getList.
        Returns list of { domain: str, expiration_date: str, auto_renew: bool, raw: dict }
        """
        params = {
            "ApiUser": str(self.api_user),
            "ApiKey": str(self.api_key),
            "UserName": str(self.username),
            "ClientIp": str(self.client_ip),
            "Command": "namecheap.domains.getList",
        }

        try:
            resp = requests.get(self.base_url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Namecheap domains.getList failed: {exc}") from exc

        if self.debug:
            safe_params = dict(params)
            if "ApiKey" in safe_params:
                safe_params["ApiKey"] = "***REDACTED***"
            print("[NC DEBUG] domains.getList params:", safe_params)
            print("[NC DEBUG] domains.getList XML:")
            print(resp.text)

        return self._parse_domains_list_response(resp.text)

    def _parse_domains_list_response(self, xml_text: str) -> List[Dict[str, Any]]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise RuntimeError(f"Invalid XML from Namecheap domains.getList: {exc}") from exc

        # Strip XML namespaces for simpler querying
        for elem in root.iter():
            if isinstance(elem.tag, str) and '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]

        status = root.attrib.get("Status")
        if status != "OK":
            # Collect all error messages if present
            error_nodes = root.findall(".//Errors/Error")
            if error_nodes:
                messages = []
                for en in error_nodes:
                    number = en.attrib.get("Number") or en.attrib.get("number")
                    text = (en.text or "").strip()
                    msg = f"[{number}] {text}" if number else text
                    messages.append(msg)
                raise RuntimeError("Namecheap domains.getList API error: " + "; ".join(m for m in messages if m))
            # Fallback: include raw XML snippet for visibility
            snippet = xml_text[:500].replace("\n", " ")
            raise RuntimeError(f"Namecheap domains.getList API error (no message). Raw snippet: {snippet}")

        results: List[Dict[str, Any]] = []
        for node in root.findall(".//Domain"):
            attrib = node.attrib
            domain = attrib.get("Name") or attrib.get("DomainName")
            expiration_date = attrib.get("Expires") or attrib.get("ExpirationDate")
            auto_renew = str(attrib.get("AutoRenew", "false")).lower() == "true"
            results.append({
                "domain": domain,
                "expiration_date": expiration_date,
                "auto_renew": auto_renew,
                "raw": attrib
            })

        return results

    def release_domain(self, domain: str) -> Dict[str, Any]:
        """
        Namecheap does not support deleting a domain via API once registered.
        As a practical stand-in, disable auto-renew so the domain will expire.
        """
        return self.set_auto_renew(domain, False)


__all__ = ["NamecheapClient"]


