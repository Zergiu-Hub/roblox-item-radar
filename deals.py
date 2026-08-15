import json
import os
import time
from pathlib import Path

import requests


# =========================================================
# CONFIG
# =========================================================

WEBHOOK = os.environ["DEALS_DISCORD_WEBHOOK"]

CATALOG_URL = "https://catalog.roblox.com/v1/search/items/details"
THUMBNAIL_URL = "https://thumbnails.roblox.com/v1/assets"

STATE_FILE = Path("deals_state.json")

# Alert when lowest resale price drops 10% or more
DEAL_THRESHOLD = 10.0

# TEMPORARY TEST MODE
# Change this to False after the Discord test works!
TEST_MODE = True

HEADERS = {
    "User-Agent": "Roblox-Limited-Deal-Radar/1.1"
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

        if isinstance(data, dict):
            return data

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
# ROBLOX REQUESTS
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
            print("⚠️ Roblox rate limit reached.")
            return None

        response.raise_for_status()
        return response

    except requests.RequestException as error:
        print(f"⚠️ Roblox request failed: {error}")
        return None


# =========================================================
# COLLECTIBLES
# =========================================================

def get_collectibles():
    response = roblox_get(
        CATALOG_URL,
        params={
            "Category": 2,
            "SortType": 3,
            "Limit": 30,
        },
    )

    if response is None:
        return None

    return response.json().get("data", [])


def get_lowest_price(item):
    price = item.get("lowestPrice")

    if price is None:
        return None

    try:
        return int(price)

    except (TypeError, ValueError):
        return None


# =========================================================
# DEAL CALCULATION
# =========================================================

def calculate_drop(old_price, new_price):
    if old_price is None or new_price is None:
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
# THUMBNAIL
# =========================================================

def get_thumbnail(item_id):
    try:
        response = requests.get(
            THUMBNAIL_URL,
            params={
                "assetIds": str(item_id),
                "size": "420x420",
                "format": "Png",
                "isCircular": "false",
            },
            headers=HEADERS,
            timeout=20,
        )

        if response.status_code == 429:
            print("⚠️ Thumbnail rate limited.")
            return None

        response.raise_for_status()

        data = response.json().get("data", [])

        if data:
            return data[0].get("imageUrl")

    except requests.RequestException as error:
        print(f"Thumbnail error: {error}")

    return None


# =========================================================
# DISCORD
# =========================================================

def send_deal_alert(
    item,
    old_price,
    new_price,
    drop_percent,
    test=False,
):
    item_id = item.get("id")
    name = item.get("name", "Unknown Limited")

    creator = item.get(
        "creatorName",
        "Unknown Creator"
    )

    item_url = (
        f"https://www.roblox.com/catalog/{item_id}"
    )

    thumbnail = get_thumbnail(item_id)

    if test:
        title = "🧪 TEST LIMITED DEAL"
        footer = (
            "TEST ONLY • Limited Deal Radar "
            "is connected correctly"
        )
    else:
        title = "🔥 LIMITED DEAL DETECTED"
        footer = (
            "Limited Deal Radar • "
            "10%+ lowest-price drop"
        )

    embed = {
        "title": title,
        "description": f"## {name}",
        "url": item_url,

        "fields": [
            {
                "name": "👤 Creator",
                "value": str(creator),
                "inline": True,
            },
            {
                "name": "⬅️ Previous Lowest",
                "value": f"{old_price:,} R$",
                "inline": True,
            },
            {
                "name": "💰 New Lowest",
                "value": f"{new_price:,} R$",
                "inline": True,
            },
            {
                "name": "📉 Drop",
                "value": f"**{drop_percent:.1f}%**",
                "inline": True,
            },
            {
                "name": "🆔 Item ID",
                "value": str(item_id),
                "inline": True,
            },
            {
                "name": "🔗 Roblox",
                "value": f"[View Limited]({item_url})",
                "inline": True,
            },
        ],

        "footer": {
            "text": footer
        },
    }

    if thumbnail:
        embed["thumbnail"] = {
            "url": thumbnail
        }

    try:
        response = requests.post(
            WEBHOOK,
            json={
                "embeds": [embed]
            },
            timeout=20,
        )

        if response.status_code == 429:
            print("⚠️ Discord rate limit reached.")
            return False

        response.raise_for_status()

        time.sleep(1)

        print(
            f"Discord alert sent: "
            f"{name} ({drop_percent:.1f}%)"
        )

        return True

    except requests.RequestException as error:
        print(f"Discord error: {error}")
        return False


# =========================================================
# MAIN
# =========================================================

def main():

    # =====================================================
    # TEMPORARY DISCORD TEST
    # =====================================================

    if TEST_MODE:
        print("🧪 TEST MODE ENABLED")
        print("Sending fake 15% deal alert...")

        test_item = {
            "id": 1029025,
            "name": "TEST LIMITED ITEM",
            "creatorName": "Roblox",
        }

        success = send_deal_alert(
            test_item,
            old_price=1000,
            new_price=850,
            drop_percent=15.0,
            test=True,
        )

        if success:
            print(
                "✅ TEST SUCCESSFUL!"
            )

            print(
                "Check your #limited-deals "
                "Discord channel."
            )

        else:
            print(
                "❌ TEST FAILED."
            )

        return

    # =====================================================
    # REAL DEAL RADAR
    # =====================================================

    print("🔥 Limited Deal Radar starting...")

    state = load_state()

    items = get_collectibles()

    if items is None:
        print(
            "⚠️ Roblox could not be checked. "
            "Will try again next run."
        )
        return

    print(
        f"Roblox returned "
        f"{len(items)} collectibles."
    )

    if not items:
        return

    first_run = len(state) == 0

    alerts_sent = 0

    for item in items:

        item_id = item.get("id")

        if item_id is None:
            continue

        item_id = str(item_id)

        lowest_price = get_lowest_price(item)

        # Ignore items with no reseller
        if lowest_price is None:
            continue

        previous = state.get(item_id)

        # First time seeing this limited
        if previous is None:

            state[item_id] = {
                "name": item.get("name"),
                "lowest_price": lowest_price,
            }

            continue

        previous_price = previous.get(
            "lowest_price"
        )

        drop_percent = calculate_drop(
            previous_price,
            lowest_price
        )

        # REAL DEAL:
        # lowest price dropped 10% or more
        if (
            not first_run
            and drop_percent >= DEAL_THRESHOLD
        ):

            print(
                f"🔥 Deal detected: "
                f"{item.get('name')} | "
                f"{previous_price} -> "
                f"{lowest_price} | "
                f"{drop_percent:.1f}%"
            )

            if send_deal_alert(
                item,
                previous_price,
                lowest_price,
                drop_percent,
            ):
                alerts_sent += 1

        # Remember newest lowest price
        state[item_id] = {
            "name": item.get("name"),
            "lowest_price": lowest_price,
        }

    save_state(state)

    print("✅ Deal scan complete.")

    print(
        f"📦 Tracking {len(state)} limiteds."
    )

    print(
        f"🔥 Deal alerts sent: {alerts_sent}"
    )


if __name__ == "__main__":
    main()
