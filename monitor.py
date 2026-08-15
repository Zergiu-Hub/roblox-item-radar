import json
import os
import time
from pathlib import Path

import requests


# =========================================================
# CONFIG
# =========================================================

WEBHOOK = os.environ["DISCORD_WEBHOOK"]

CATALOG_URL = "https://catalog.roblox.com/v1/search/items/details"
THUMBNAIL_URL = "https://thumbnails.roblox.com/v1/assets"

STATE_FILE = Path("seen_items.json")

# Alert when a Roblox collectible/limited drops 10% or more
PRICE_DROP_THRESHOLD = 10.0

HEADERS = {
    "User-Agent": "Roblox-Item-Radar/5.0"
}


# =========================================================
# STATE
# =========================================================

def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        data = json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )

        # Current state format
        if isinstance(data, dict):
            return data

        # Automatically convert the older list format
        if isinstance(data, list):
            return {
                str(item_id): {
                    "price": None,
                    "name": None,
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


# =========================================================
# ROBLOX REQUEST HELPER
# =========================================================

def roblox_get(url, params=None):
    try:
        response = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=20,
        )

        if response.status_code == 429:
            retry_after = response.headers.get(
                "Retry-After",
                "unknown"
            )

            print("⚠️ Roblox rate limit reached.")
            print(f"Retry-After: {retry_after}")

            return None

        response.raise_for_status()

        return response

    except requests.RequestException as error:
        print(f"⚠️ Roblox request failed: {error}")
        return None


# =========================================================
# ROBLOX CATALOG
# =========================================================

def get_catalog_items():
    # Roblox creator ID 1 = official Roblox account
    params = {
        "Category": 1,
        "CreatorTargetId": 1,
        "CreatorType": "User",
        "SortType": 3,
        "Limit": 30,
    }

    response = roblox_get(
        CATALOG_URL,
        params=params
    )

    if response is None:
        return None

    return response.json().get(
        "data",
        []
    )


# =========================================================
# ITEM FILTERS
# =========================================================

def is_official_roblox(item):
    creator_name = str(
        item.get("creatorName", "")
    ).strip().lower()

    creator_id = item.get("creatorTargetId")

    if creator_id == 1:
        return True

    return creator_name == "roblox"


def is_free(item):
    return item.get("price") == 0


def is_collectible(item):
    return (
        item.get("collectibleItemId") is not None
        or item.get("unitsAvailableForConsumption") is not None
        or item.get("lowestPrice") is not None
    )


# =========================================================
# PRICE DROP
# =========================================================

def calculate_price_drop(old_price, new_price):
    if old_price is None:
        return 0.0

    if new_price is None:
        return 0.0

    if old_price <= 0:
        return 0.0

    if new_price >= old_price:
        return 0.0

    return (
        (old_price - new_price)
        / old_price
    ) * 100


# =========================================================
# THUMBNAILS
# =========================================================

def get_thumbnails(item_ids):
    if not item_ids:
        return {}

    try:
        response = requests.get(
            THUMBNAIL_URL,
            params={
                "assetIds": ",".join(
                    str(item_id)
                    for item_id in item_ids
                ),
                "size": "420x420",
                "format": "Png",
                "isCircular": "false",
            },
            headers=HEADERS,
            timeout=20,
        )

        if response.status_code == 429:
            print(
                "⚠️ Thumbnail rate limit reached. "
                "Continuing without thumbnails."
            )
            return {}

        response.raise_for_status()

        thumbnails = {}

        for result in response.json().get(
            "data",
            []
        ):
            target_id = str(
                result.get("targetId")
            )

            image_url = result.get(
                "imageUrl"
            )

            if image_url:
                thumbnails[target_id] = image_url

        return thumbnails

    except requests.RequestException as error:
        print(
            f"⚠️ Thumbnail request failed: {error}"
        )

        return {}


# =========================================================
# DISCORD
# =========================================================

def send_discord_embed(embed):
    try:
        response = requests.post(
            WEBHOOK,
            json={
                "embeds": [embed]
            },
            timeout=20,
        )

        if response.status_code == 429:
            print(
                "⚠️ Discord rate limit reached."
            )
            return False

        response.raise_for_status()

        # Small delay if several alerts happen together
        time.sleep(1)

        return True

    except requests.RequestException as error:
        print(
            f"⚠️ Discord error: {error}"
        )
        return False


def make_embed(
    title,
    item,
    emoji,
    thumbnail=None,
    extra_fields=None,
):
    item_id = str(
        item.get("id")
    )

    name = item.get(
        "name",
        "Unknown Roblox Item"
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
        remaining_text = "Not provided"

    else:
        remaining_text = f"{remaining:,}"

    item_url = (
        f"https://www.roblox.com/catalog/{item_id}"
    )

    fields = [
        {
            "name": "👤 Creator",
            "value": "Roblox",
            "inline": True,
        },
        {
            "name": "💰 Price",
            "value": price_text,
            "inline": True,
        },
        {
            "name": "📦 Remaining",
            "value": remaining_text,
            "inline": True,
        },
        {
            "name": "🆔 Item ID",
            "value": item_id,
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

    return embed


# =========================================================
# MAIN RADAR
# =========================================================

def main():
    print("🛰️ Roblox Item Radar starting...")

    state = load_state()

    items = get_catalog_items()

    # If Roblox temporarily rate limits us,
    # finish safely and try again next scheduled run.
    if items is None:
        print(
            "⚠️ Roblox could not be checked this run."
        )

        print(
            "The radar will try again next time."
        )

        return

    print(
        f"Marketplace returned "
        f"{len(items)} Roblox items."
    )

    if not items:
        print("No Roblox items returned.")
        return

    first_run = len(state) == 0

    alerts = []

    for item in items:

        item_id = item.get("id")

        if item_id is None:
            continue

        item_id = str(item_id)

        # Only official Roblox-created items
        if not is_official_roblox(item):
            print(
                f"Skipping non-Roblox item: "
                f"{item_id}"
            )
            continue

        current_price = item.get("price")

        previous = state.get(item_id)

        # =================================================
        # NEW ROBLOX ITEM
        # =================================================

        if previous is None:

            state[item_id] = {
                "name": item.get("name"),
                "price": current_price,
            }

            # Prevent old items from flooding Discord
            # during initial setup.
            if first_run:
                continue

            # New FREE official Roblox item
            if is_free(item):

                alerts.append({
                    "type": "free",
                    "item": item,
                })

            # New official Roblox collectible/limited
            elif is_collectible(item):

                alerts.append({
                    "type": "collectible",
                    "item": item,
                })

            continue

        # =================================================
        # PRICE DROP
        # =================================================

        old_price = previous.get("price")

        drop_percent = calculate_price_drop(
            old_price,
            current_price
        )

        # IMPORTANT:
        # Price-drop alerts are ONLY for
        # Roblox collectibles / limiteds.
        if (
            is_collectible(item)
            and drop_percent >= PRICE_DROP_THRESHOLD
        ):
            alerts.append({
                "type": "price_drop",
                "item": item,
                "old_price": old_price,
                "new_price": current_price,
                "drop_percent": drop_percent,
            })

        # Always remember the latest price
        state[item_id] = {
            "name": item.get("name"),
            "price": current_price,
        }

    # =====================================================
    # GET THUMBNAILS IN ONE REQUEST
    # =====================================================

    alert_ids = [
        alert["item"]["id"]
        for alert in alerts
    ]

    thumbnails = get_thumbnails(
        alert_ids
    )

    # =====================================================
    # SEND DISCORD ALERTS
    # =====================================================

    alerts_sent = 0

    for alert in alerts:

        item = alert["item"]

        item_id = str(
            item["id"]
        )

        thumbnail = thumbnails.get(
            item_id
        )

        # FREE ITEM
        if alert["type"] == "free":

            print(
                "🆓 New free Roblox item: "
                f"{item.get('name')}"
            )

            embed = make_embed(
                "NEW FREE ROBLOX ITEM",
                item,
                "🆓",
                thumbnail,
            )

        # NEW COLLECTIBLE / LIMITED
        elif alert["type"] == "collectible":

            print(
                "💎 New Roblox collectible: "
                f"{item.get('name')}"
            )

            embed = make_embed(
                "NEW ROBLOX COLLECTIBLE / LIMITED",
                item,
                "💎",
                thumbnail,
            )

        # 10%+ LIMITED / COLLECTIBLE PRICE DROP
        else:

            old_price = alert[
                "old_price"
            ]

            new_price = alert[
                "new_price"
            ]

            drop_percent = alert[
                "drop_percent"
            ]

            print(
                "📉 Roblox collectible price drop: "
                f"{item.get('name')} "
                f"{old_price} -> "
                f"{new_price} "
                f"({drop_percent:.1f}%)"
            )

            embed = make_embed(
                "ROBLOX LIMITED PRICE DROP",
                item,
                "📉",
                thumbnail,
                extra_fields=[
                    {
                        "name": "⬅️ Old Price",
                        "value": (
                            f"{old_price:,} Robux"
                        ),
                        "inline": True,
                    },
                    {
                        "name": "➡️ New Price",
                        "value": (
                            f"{new_price:,} Robux"
                        ),
                        "inline": True,
                    },
                    {
                        "name": "📉 Drop",
                        "value": (
                            f"{drop_percent:.1f}%"
                        ),
                        "inline": True,
                    },
                ],
            )

        if send_discord_embed(embed):
            alerts_sent += 1

    # =====================================================
    # SAVE STATE
    # =====================================================

    save_state(state)

    print("✅ Scan completed.")

    print(
        f"📦 Tracking {len(state)} "
        "official Roblox items."
    )

    print(
        f"🔔 Alerts sent: {alerts_sent}"
    )


if __name__ == "__main__":
    main()
