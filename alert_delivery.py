"""Persist undelivered Discord messages across scheduled runs."""
import hashlib
import json
import time
from pathlib import Path

import requests


class AlertDelivery:
    def __init__(self, webhook, filename):
        self.webhook = webhook
        self.blocked = False
        self.path = Path(filename)
        self.pending = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        if not isinstance(self.pending, dict):
            raise ValueError("Invalid pending alert state")

    def save(self):
        self.path.write_text(json.dumps(self.pending, indent=2, sort_keys=True), encoding="utf-8")

    def attempt(self, key):
        if self.blocked:
            return False
        try:
            response = requests.post(self.webhook, json={"embeds": [self.pending[key]]}, timeout=20)
            response.raise_for_status()
        except requests.RequestException:
            # Exception text can contain the secret webhook URL.
            print("Discord delivery failed; message retained for retry.")
            self.blocked = True
            return False
        del self.pending[key]
        self.save()
        time.sleep(1)
        return True

    def send(self, embed):
        key = hashlib.sha256(json.dumps(embed, sort_keys=True).encode()).hexdigest()
        self.pending[key] = embed
        self.save()
        return self.attempt(key)

    def retry(self):
        for key in list(self.pending):
            if not self.attempt(key):
                break

    def check(self):
        if self.pending:
            raise RuntimeError(f"{len(self.pending)} Discord alerts still pending delivery")
