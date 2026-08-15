import json
import os
from pathlib import Path

import requests

WEBHOOK = os.environ["DISCORD_WEBHOOK"]

CATALOG_URL = "https://catalog.roblox.com/v1/search/items/details"
THUMBNAIL_URL = "https://thumbnails.roblox.com/v1/assets"

STATE_FILE = Path("seen_items.json")

HEADERS = {
    "User-Agent": "Roblox-Item-Radar/3.0"
}

PRICE_DROP_THRESHOLD = 15.0


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        data = json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )

        if isinstance(data, dict):
            return data

        # Converts the older list format automatically
        if isinstance(data, list):
            return {
                str(item_id): {
                    "price": None
                }
                for item_id in data
            }

    except Exception as error:
        print(f"State load error: {error}")

    return {}


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(
            state,
            indent=2,
            sort_keys=True
        ),
        encoding="utf-8"
    )


def is_roblox_creator(item):
    creator = str(
        item.get("creatorName", "")
    ).strip().lower()

    return creator == "roblox"


def is_free(item):
    return item.get("price") == 0


def is_collectible(item):
    return (
        item.get("collectibleItemId") is not None
        or item.get("lowestPrice") is not None
        or item.get("unitsAvailableForConsumption") is not None
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


def send_alert(
    title,
    item,
    emoji,
    extra_fields=None
):
    item_id = item.get("id")
    name = item.get("name", "Unknown Item")
    creator = item.get(
        "creatorName",
        "Unknown Creator"
    )

    price = item.get("price")

    if price == 0:
        price_text = "FREE 🆓"
    elif price is None:
        price_text = "Not listed"
    else:
        price_text = f"{price:,} Robux"

    remaining = item.get(
        "unitsAvailableForConsumption"
    )

    if remaining is None:
        quantity_text = "Not provided"
    else:
        quantity_text = f"{remaining:,}"

    item_url = (
        f"https://www.roblox.com/catalog/{item_id}"
    )

    thumbnail = get_thumbnail(item_id)

    fields = [
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
    ]

    if extra_fields:
        fields.extend(extra_fields)

    embed = {
        "title": f"{emoji} {title}",
        "description": f"## {name}",
        "url": item_url,
        "fields": fields,
        "footer": {
            "text": (
                "Roblox Item Radar • "
                "Official Roblox Items Only"
            )
        },
    }

    if thumbnail:
        embed["thumbnail"] = {
            "url": thumbnail
        }

    response = requests.post(
        WEBHOOK,
        json={
            "embeds": [embed]
        },
        timeout=20,
    )

    response.raise_for_status()

    print(f"Discord alert sent: {name}")


def send_price_drop_alert(
    item,
    old_price,
    new_price,
    drop_percent
):
    send_alert(
        "ROBLOX ITEM PRICE DROP",
        item,
        "📉",
        extra_fields=[
            {
                "name": "⬅️ Old Price",
                "value": f"{old_price:,} Robux",
                "inline": True,
            },
            {
                "name": "➡️ New Price",
                "value": f"{new_price:,} Robux",
                "inline": True,
            },
            {
                "name": "📉 Price Drop",
                "value": f"{drop_percent:.1f}%",
                "inline": True,
            },
        ]
    )


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

    return response.json().get(
        "data",
        []
    )


def calculate_price_drop(
    old_price,
    new_price
):
    if old_price is None:
        return 0

    if new_price is None:
        return 0

    if old_price <= 0:
        return 0

    if new_price >= old_price:
        return 0

    difference = old_price - new_price

    return (
        difference / old_price
    ) * 100


def main():
    state = load_state()

    print(
        "🛰️ Roblox Item Radar starting..."
    )

    items = get_catalog_items()

    print(
        f"Marketplace returned "
        f"{len(items)} items."
    )

    if not items:
        print("No items returned.")
        return

    first_run = len(state) == 0

    alerts_sent = 0
    roblox_items_found = 0

    for item in items:

        item_id = item.get("id")

        if item_id is None:
            continue

        item_id = str(item_id)

        # Ignore all non-Roblox creators
        if not is_roblox_creator(item):
            continue

        roblox_items_found += 1

        current_price = item.get("price")

        previous = state.get(item_id)

        # First time we've seen this item
        if previous is None:

            state[item_id] = {
                "price": current_price,
                "name": item.get("name"),
            }

            # Don't spam existing items
            # on the very first setup run.
            if first_run:
                continue

            if is_free(item):

                print(
                    f"🆓 New free Roblox item: "
                    f"{item.get('name')}"
                )

                send_alert(
                    "NEW FREE ROBLOX ITEM",
                    item,
                    "🆓",
                )

                alerts_sent += 1

            elif is_collectible(item):

                print(
                    f"💎 New Roblox collectible: "
                    f"{item.get('name')}"
                )

                send_alert(
                    "NEW ROBLOX "
                    "COLLECTIBLE / LIMITED",
                    item,
                    "💎",
                )

                alerts_sent += 1

            continue

        old_price = previous.get("price")

        drop_percent = calculate_price_drop(
            old_price,
            current_price
        )

        if (
            drop_percent
            >= PRICE_DROP_THRESHOLD
        ):

            print(
                f"📉 Price drop detected: "
                f"{item.get('name')} "
                f"{old_price} -> "
                f"{current_price} "
                f"({drop_percent:.1f}%)"
            )

            send_price_drop_alert(
                item,
                old_price,
                current_price,
                drop_percent
            )

            alerts_sent += 1

        # Always update the stored price
        # so future drops use the latest price.
        state[item_id] = {
            "price": current_price,
            "name": item.get("name"),
        }

    save_state(state)

    print(
        f"✅ Scan finished — "
        f"{roblox_items_found} Roblox items found, "
        f"{len(state)} Roblox items tracked, "
        f"{alerts_sent} new alerts."
    )


if __name__ == "__main__":
    main()
