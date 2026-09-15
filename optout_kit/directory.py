"""Fetch the upstream broker directory at runtime.

The upstream data (Optery's data-brokers directory) is CC BY-NC-SA 4.0.
It is deliberately NOT vendored into this MIT-licensed repository: doing so
would impose NonCommercial + ShareAlike terms on everything downstream.
We fetch it into a gitignored cache so each user obtains it under its own
license. See docs/attribution.md.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Any

UPSTREAM = (
    "https://raw.githubusercontent.com/optery/optery-data-brokers-directory/"
    "master/data/data-brokers.json"
)
CACHE = Path(".cache/data-brokers.json")
MAX_AGE_SECONDS = 7 * 24 * 3600

# Types whose listings surface in an ordinary web search of a person's name.
PUBLIC_TYPES = {"People Search Site", "Phone Directory", "Profile Data Broker"}


def fetch(force: bool = False, cache: Path = CACHE) -> list[dict[str, Any]]:
    """Return the broker directory, downloading if the cache is stale."""
    fresh = (
        cache.exists()
        and not force
        and (time.time() - cache.stat().st_mtime) < MAX_AGE_SECONDS
    )
    if not fresh:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(UPSTREAM, timeout=60) as resp:
            payload = resp.read()
        cache.write_bytes(payload)
    return json.loads(cache.read_text(encoding="utf-8"))


def slug(title: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in title)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def nonempty(record: dict[str, Any], key: str) -> str:
    return str(record.get(key) or "").strip()
