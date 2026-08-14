import os
import requests

WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

if not WEBHOOK:
    raise RuntimeError("DISCORD_WEBHOOK secret is missing")

message = {
    "content": (
        "🛰️ **Roblox Item Radar is online!**\n\n"
        "💎 Collectibles / Limiteds: ON\n"
        "🆓 Free Items: ON\n"
        "🕵️ Public Potential Leaks: ON\n\n"
        "This is a test notification."
    )
}

response = requests.post(WEBHOOK, json=message, timeout=15)
response.raise_for_status()

print("Discord test notification sent successfully!")
