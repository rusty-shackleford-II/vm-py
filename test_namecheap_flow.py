from pprint import pprint

from clients import NamecheapClient


def main() -> None:
    nc = NamecheapClient()

    # 1) Search with prices
    query = "edwar.xyz"
    print("Searching with pricing for:", query)
    results = nc.search_domains_with_prices(query)
    pprint(results)

    # Optional: You can uncomment below to test nameserver update or auto-renew toggle
    # domain = "example.com"
    # print("Updating nameservers to Cloudflare for:", domain)
    # pprint(nc.transfer_dns_to_cloudflare(domain))
    # print("Disable auto-renew:")
    # pprint(nc.set_auto_renew(domain, False))


if __name__ == "__main__":
    main()


