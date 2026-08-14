import json
import os
from pathlib import Path

import requests

WEBHOOK = os.environ["DISCORD_WEBHOOK"]

CATALOG_URL = "https://catalog.roblox.com/v1/search/items/details"
STATE_FILE = Path("seen_items.json")

HEADERS = {
    "User-Agent": "Roblox-Item-Radar/1.0"
}


def load_seen():
    if not STATE_FILE.exists():
        return set()

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data)
    except Exception:
        return set()


def save_seen(seen):
    STATE_FILE.write_text(
        json.dumps(sorted(seen), indent=2),
        encoding="utf-8"
    )


def discord_alert(title, item, emoji):
    item_id = item.get("id")
    name = item.get("name", "Unknown item")
    creator = item.get("creatorName", "Unknown")
    price = item.get("price")

    if price == 0:
        price_text = "FREE"
    elif price is None:
        price_text = "Not listed"
    else:
        price_text = f"{price} Robux"

    url = f"https://www.roblox.com/catalog/{item_id}"

    payload = {
        "embeds": [
            {
                "title": f"{emoji} {title}",
                "description": f"**{name}**",
                "fields": [
                    {
                        "name": "Creator",
                        "value": str(creator),
                        "inline": True
                    },
                    {
                        "name": "Price",
                        "value": price_text,
                        "inline": True
                    },
                    {
                        "name": "Item ID",
                        "value": str(item_id),
                        "inline": True
                    }
                ],
                "url": url,
                "footer": {
                    "text": "Roblox Item Radar"
                }
            }
        ]
    }

    response = requests.post(
        WEBHOOK,
        json=payload,
        timeout=20
    )

    response.raise_for_status()


def get_catalog_items():
    params = {
        "Category": 1,
        "SortType": 3,
        "Limit": 30
    }

    response = requests.get(
        CATALOG_URL,
        params=params,
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    return response.json().get("data", [])


def is_free(item):
    return item.get("price") == 0


def is_collectible(item):
    return (
        item.get("collectibleItemId") is not None
        or item.get("lowestPrice") is not None
        or item.get("unitsAvailableForConsumption") is not None
    )


def main():
    seen = load_seen()

    print("Checking Roblox Marketplace...")

    items = get_catalog_items()

    if not items:
        print("No items returned.")
        return

    first_run = len(seen) == 0

    new_seen = set(seen)

    for item in items:
        item_id = str(item.get("id"))

        if not item_id or item_id == "None":
            continue

        new_seen.add(item_id)

        # On the very first run, remember existing items
        # without flooding Discord with dozens of alerts.
        if first_run:
            continue

        if item_id in seen:
            continue

        if is_free(item):
            print(f"FREE ITEM: {item.get('name')}")
            discord_alert(
                "NEW FREE ROBLOX ITEM",
                item,
                "🆓"
            )

        elif is_collectible(item):
            print(f"COLLECTIBLE: {item.get('name')}")
            discord_alert(
                "NEW COLLECTIBLE / LIMITED",
                item,
                "💎"
            )

    save_seen(new_seen)

    print(f"Finished. Tracking {len(new_seen)} items.")


if __name__ == "__main__":
    main()
