import json
import os
from pathlib import Path

import requests

WEBHOOK = os.environ["DISCORD_WEBHOOK"]

CATALOG_URL = "https://catalog.roblox.com/v1/search/items/details"
THUMBNAIL_URL = "https://thumbnails.roblox.com/v1/assets"

STATE_FILE = Path("seen_items.json")

HEADERS = {
    "User-Agent": "Roblox-Item-Radar/2.0"
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


def get_thumbnail(item_id):
    try:
        response = requests.get(
            THUMBNAIL_URL,
            params={
                "assetIds": item_id,
                "size": "420x420",
                "format": "Png",
                "isCircular": "false",
            },
            timeout=15,
        )

        response.raise_for_status()

        data = response.json().get("data", [])

        if data:
            return data[0].get("imageUrl")

    except requests.RequestException as error:
        print(f"Thumbnail error: {error}")

    return None


def send_alert(title, item, emoji):
    item_id = item.get("id")
    name = item.get("name", "Unknown Item")
    creator = item.get("creatorName", "Unknown Creator")
    price = item.get("price")

    if price == 0:
        price_text = "FREE 🆓"
    elif price is None:
        price_text = "Not listed"
    else:
        price_text = f"{price:,} Robux"

    remaining = item.get("unitsAvailableForConsumption")

    if remaining is None:
        quantity_text = "Not provided"
    else:
        quantity_text = f"{remaining:,}"

    item_url = f"https://www.roblox.com/catalog/{item_id}"
    thumbnail = get_thumbnail(item_id)

    embed = {
        "title": f"{emoji} {title}",
        "description": f"## {name}",
        "url": item_url,
        "fields": [
            {
                "name": "👤 Creator",
                "value": str(creator),
                "inline": True,
            },
            {
                "name": "💰 Price",
                "value": price_text,
                "inline": True,
            },
            {
                "name": "📦 Remaining",
                "value": quantity_text,
                "inline": True,
            },
            {
                "name": "🆔 Item ID",
                "value": str(item_id),
                "inline": True,
            },
            {
                "name": "🔗 Roblox",
                "value": f"[View Item]({item_url})",
                "inline": True,
            },
        ],
        "footer": {
            "text": "Roblox Item Radar • Automatic Marketplace Alert"
        },
    }

    if thumbnail:
        embed["thumbnail"] = {
            "url": thumbnail
        }

    response = requests.post(
        WEBHOOK,
        json={"embeds": [embed]},
        timeout=20,
    )

    response.raise_for_status()

    print(f"Discord alert sent: {name}")


def get_catalog_items():
    response = requests.get(
        CATALOG_URL,
        params={
            "Category": 1,
            "SortType": 3,
            "Limit": 30,
        },
        headers=HEADERS,
        timeout=20,
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

    print("🛰️ Roblox Item Radar starting...")

    items = get_catalog_items()

    print(f"Marketplace returned {len(items)} items.")

    if not items:
        print("No items returned.")
        return

    first_run = len(seen) == 0
    updated_seen = set(seen)

    alerts_sent = 0

    for item in items:
        item_id = item.get("id")

        if item_id is None:
            continue

        item_id = str(item_id)

        updated_seen.add(item_id)

        # Prevent notification spam during initial setup.
        if first_run:
            continue

        # Already processed this item.
        if item_id in seen:
            continue

        if is_free(item):
            print(f"🆓 New free item: {item.get('name')}")

            send_alert(
                "NEW FREE ROBLOX ITEM",
                item,
                "🆓",
            )

            alerts_sent += 1

        elif is_collectible(item):
            print(f"💎 New collectible: {item.get('name')}")

            send_alert(
                "NEW COLLECTIBLE / LIMITED",
                item,
                "💎",
            )

            alerts_sent += 1

    save_seen(updated_seen)

    print(
        f"✅ Scan finished — "
        f"{len(updated_seen)} items tracked, "
        f"{alerts_sent} new alerts."
    )


if __name__ == "__main__":
    main()
