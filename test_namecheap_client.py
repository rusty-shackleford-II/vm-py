from pprint import pprint

from clients import NamecheapClient


def main() -> None:
    client = NamecheapClient()

    # Build some candidates for the query "edwar"
    seeds = ["edwar.com", "edwar.net", "edwar.org", "edwar.ai", "edwar.dev"]
    print("Checking availability for:", ", ".join(seeds))
    results = client.check_domain_availability(seeds)
    pprint(results)


if __name__ == "__main__":
    main()


