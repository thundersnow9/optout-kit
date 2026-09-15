"""Build a prioritized, policy-filtered target list."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from importlib.resources import files
from typing import Any, Iterable

from . import directory, laws


@dataclass
class Target:
    slug: str
    title: str
    tier: int            # 0 upstream wholesaler, 1 crucial, 2 high priority, 3 long tail
    method: str          # "email" | "form" | "none"
    route: str
    email: str
    opt_out_url: str
    broker_type: str
    requires_id: bool | None
    requires_phone: bool
    skip_reason: str | None

    @property
    def actionable(self) -> bool:
        return self.skip_reason is None and self.method != "none"


def _notes() -> dict[str, Any]:
    for c in (
        files("optout_kit").joinpath("data/broker-notes.json"),
        files("optout_kit").parent.joinpath("data/broker-notes.json"),
    ):
        try:
            return json.loads(c.read_text(encoding="utf-8"))["brokers"]
        except (FileNotFoundError, OSError):
            continue
    return {}


def _supplemental() -> list[dict[str, Any]]:
    """Brokers absent from the upstream directory, shaped like upstream records."""
    for c in (
        files("optout_kit").joinpath("data/broker-notes.json"),
        files("optout_kit").parent.joinpath("data/broker-notes.json"),
    ):
        try:
            blob = json.loads(c.read_text(encoding="utf-8"))
            break
        except (FileNotFoundError, OSError):
            continue
    else:
        return []
    return list(blob.get("supplemental", {}).get("brokers", []))


def build(
    state: str,
    allow_id_upload: bool = False,
    public_only: bool = True,
    records: Iterable[dict[str, Any]] | None = None,
) -> list[Target]:
    """Filter the upstream directory into an ordered work queue.

    allow_id_upload=False (the default) is the privacy-preserving choice: brokers
    known to demand identity documents are skipped rather than fed more data.
    """
    law = laws.load(state)
    notes = _notes()
    rows = list(records) if records is not None else directory.fetch()
    if records is None:
        rows = rows + _supplemental()

    out: list[Target] = []
    for rec in rows:
        btype = directory.nonempty(rec, "type")
        title = directory.nonempty(rec, "title")
        if not title:
            continue
        slug = directory.slug(title)
        # Supplemental records carry their own metadata inline.
        note = notes.get(slug) or {
            k: rec[k] for k in ("tier", "requires_id", "requires_phone", "note")
            if k in rec
        }

        # An explicitly tiered broker is always in scope. The upstream wholesalers
        # are typed "Marketing", but opting out there starves the long tail, so
        # the public-type filter must not silently drop them.
        if public_only and btype not in directory.PUBLIC_TYPES and "tier" not in note:
            continue

        email = directory.nonempty(rec, "email")
        url = directory.nonempty(rec, "opt_out_url")
        # Email is preferred: it is templatable, timestamped, and creates a
        # written record that starts the statutory clock.
        method = "email" if email else ("form" if url else "none")
        route = email or url or directory.nonempty(rec, "website")

        requires_id = note.get("requires_id")
        skip: str | None = None
        if requires_id and not allow_id_upload:
            skip = "skipped_id_required"
        elif method == "none":
            skip = "no_route"

        out.append(
            Target(
                slug=slug,
                title=title,
                tier=note.get("tier", 3),
                method=method,
                route=route,
                email=email,
                opt_out_url=url,
                broker_type=btype,
                requires_id=requires_id,
                requires_phone=bool(note.get("requires_phone")),
                skip_reason=skip,
            )
        )

    # Wholesalers first, then crucial sites, then the long tail alphabetically.
    out.sort(key=lambda t: (t.tier, t.title.lower()))
    return out


def summarize(targets: list[Target], state: str) -> dict[str, Any]:
    law = laws.load(state)
    by_tier: dict[int, int] = {}
    for t in targets:
        by_tier[t.tier] = by_tier.get(t.tier, 0) + 1
    return {
        "state": law.code,
        "law": law.abbrev,
        "law_verified": law.verified,
        "preferred_mechanism": (law.preferred_mechanism or {}).get("id"),
        "total": len(targets),
        "actionable": sum(1 for t in targets if t.actionable),
        "email": sum(1 for t in targets if t.actionable and t.method == "email"),
        "form": sum(1 for t in targets if t.actionable and t.method == "form"),
        "skipped_id": sum(1 for t in targets if t.skip_reason == "skipped_id_required"),
        "no_route": sum(1 for t in targets if t.skip_reason == "no_route"),
        "by_tier": dict(sorted(by_tier.items())),
    }


def to_dicts(targets: list[Target]) -> list[dict[str, Any]]:
    return [asdict(t) for t in targets]
