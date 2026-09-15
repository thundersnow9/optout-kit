"""Per-broker canary addresses, for detecting who resold your data.

Removal is not permanent: brokers re-acquire from each other, so the useful
question a few months out is not "am I listed again" but "who leaked me".

Giving each broker a unique tagged address answers that. When mail arrives at
a tag you only ever gave to one broker, that broker is the source. The tag is
deterministic (`base+<slug>@domain`), so the mapping reverses without a
lookup table and there is nothing to keep in sync.

The canary is supplied ALONGSIDE the real address, never instead of it: a
broker searches its records by the address it already holds, so replacing it
would reduce the chance of matching your record at all.

Tradeoff worth knowing: this hands the broker one extra data point. It is an
alias of an address they already have, and it is the only reliable way to
attribute a later leak, but it is a real disclosure rather than a free win.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Some brokers reject or silently strip "+" addressing in web forms. Where that
# happens, pin an explicit alternative in canaries.json rather than losing the
# canary for that broker.
_TAG_SAFE = re.compile(r"[^a-z0-9]+")


def tag_for(base_email: str, slug: str) -> str | None:
    """`user+slug@domain` from a base address, or None if it isn't taggable."""
    if not base_email or "@" not in base_email:
        return None
    local, _, domain = base_email.partition("@")
    if "+" in local:  # already tagged; don't stack tags
        local = local.split("+", 1)[0]
    tag = _TAG_SAFE.sub("-", slug.lower()).strip("-")
    if not tag:
        return None
    return f"{local}+{tag}@{domain}"


def load_overrides(path: str | Path | None) -> dict[str, str]:
    """Explicit per-broker addresses, for brokers that reject '+' addressing."""
    if not path or not Path(path).exists():
        return {}
    blob = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for slug, entry in (blob.get("brokers") or {}).items():
        alias = entry.get("email_alias") if isinstance(entry, dict) else entry
        if alias:
            out[slug] = alias
    return out


def for_broker(profile: dict[str, Any], slug: str,
               overrides: dict[str, str] | None = None) -> str | None:
    """The canary address to disclose to one broker, if canaries are enabled."""
    if (overrides or {}).get(slug):
        return overrides[slug]
    if not profile.get("canary_email_base"):
        return None
    return tag_for(profile["canary_email_base"], slug)


def source_of(address: str) -> str | None:
    """Reverse a canary back to the broker slug that was given it."""
    local = address.partition("@")[0]
    return local.split("+", 1)[1] if "+" in local else None
