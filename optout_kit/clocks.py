"""Statutory deadline tracking and escalation.

This is the part commercial removal services do not do: when a broker ignores
a lawful deletion request, the statute provides an appeal and then an AG
complaint. Tracking those clocks is purely mechanical, so we automate it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import laws

# Terminal states: nothing further is owed to us or by us.
TERMINAL = {"confirmed", "skipped_id_required", "no_route", "abandoned"}

ACTIONS = {
    "appeal": "Statutory deadline passed with no adequate response",
    "appeal_denial": "Request was denied",
    "ag_complaint": "Appeal denied or ignored",
    "refile": "Data reappeared after a confirmed removal",
}


@dataclass
class Entry:
    path: Path
    raw: dict[str, Any]

    @property
    def slug(self) -> str:
        return self.raw.get("slug") or self.path.stem

    @property
    def title(self) -> str:
        return self.raw.get("title") or self.slug

    @property
    def status(self) -> str:
        return self.raw.get("status", "pending")

    def event_date(self, kind: str) -> date | None:
        """Date of the most recent event of a given kind."""
        best: date | None = None
        for ev in self.raw.get("events", []):
            if ev.get("type") != kind:
                continue
            try:
                d = date.fromisoformat(ev["date"])
            except (KeyError, ValueError):
                continue
            if best is None or d > best:
                best = d
        return best


@dataclass
class Action:
    slug: str
    title: str
    action: str
    reason: str
    days_overdue: int
    citation: str | None


def load_ledger(ledger_dir: Path) -> list[Entry]:
    entries = []
    for p in sorted(Path(ledger_dir).glob("*.json")):
        try:
            entries.append(Entry(path=p, raw=json.loads(p.read_text(encoding="utf-8"))))
        except json.JSONDecodeError:
            continue
    return entries


def deadline_for(entry: Entry, law: laws.StateLaw) -> date | None:
    """When the controller's response was due."""
    sent = entry.event_date("sent")
    if sent is None:
        return None
    days = law.response_days
    # A controller may extend once, but must say so within the initial window.
    if entry.event_date("extended") is not None:
        days += law.raw.get("extension_days", 0)
    return sent + timedelta(days=days)


def appeal_deadline_for(entry: Entry, law: laws.StateLaw) -> date | None:
    appealed = entry.event_date("appealed")
    if appealed is None:
        return None
    days = law.appeal.get("response_days") or law.response_days
    return appealed + timedelta(days=days)


def evaluate(entries: list[Entry], state: str, today: date | None = None) -> list[Action]:
    """Return every escalation that is currently due."""
    law = laws.load(state)
    now = today or date.today()
    actions: list[Action] = []

    for e in entries:
        status = e.status
        if status in TERMINAL and not e.event_date("relisted"):
            continue

        # Data came back after we confirmed removal: start over, citing history.
        relisted = e.event_date("relisted")
        if relisted and (not e.event_date("sent") or relisted > e.event_date("sent")):
            actions.append(Action(e.slug, e.title, "refile", ACTIONS["refile"],
                                  (now - relisted).days, law.deletion_citation))
            continue

        if status == "denied":
            if law.appeal.get("available"):
                actions.append(Action(e.slug, e.title, "appeal", ACTIONS["appeal_denial"],
                                      0, law.appeal.get("citation")))
            else:
                actions.append(Action(e.slug, e.title, "ag_complaint",
                                      "Denied; this state has no appeal step", 0, None))
            continue

        if status in {"appealed", "appeal_denied"}:
            if status == "appeal_denied":
                actions.append(Action(e.slug, e.title, "ag_complaint",
                                      ACTIONS["ag_complaint"], 0, law.appeal.get("citation")))
                continue
            ad = appeal_deadline_for(e, law)
            if ad and now > ad:
                actions.append(Action(e.slug, e.title, "ag_complaint", ACTIONS["ag_complaint"],
                                      (now - ad).days, law.appeal.get("citation")))
            continue

        if status in {"sent", "acknowledged", "extended"}:
            d = deadline_for(e, law)
            if d and now > d:
                cite = law.appeal.get("citation") if law.appeal.get("available") else None
                nxt = "appeal" if law.appeal.get("available") else "ag_complaint"
                actions.append(Action(e.slug, e.title, nxt, ACTIONS["appeal"],
                                      (now - d).days, cite))

    actions.sort(key=lambda a: -a.days_overdue)
    return actions


def render_issue(actions: list[Action], state: str) -> str:
    """Markdown body for the weekly tracking issue."""
    law = laws.load(state)
    if not actions:
        return f"No escalations due. All {law.abbrev} clocks are within their statutory windows."

    lines = [
        f"# Escalations due under {law.abbrev}",
        "",
        f"{len(actions)} broker(s) have passed a statutory deadline.",
        "",
        "| Broker | Action | Days overdue | Authority |",
        "| --- | --- | ---: | --- |",
    ]
    for a in actions:
        lines.append(f"| {a.title} | `{a.action}` | {a.days_overdue} | {a.citation or 'n/a'} |")

    ag = law.ag
    lines += [
        "",
        "## How to escalate",
        "",
        f"- **appeal**: reply on the original thread citing {law.appeal.get('citation') or 'the state appeal provision'}.",
        f"- **ag_complaint**: file with {ag.get('name', 'the state Attorney General')}"
        + (f" ({ag['email']})" if ag.get("email") else "")
        + (f" — {ag['url']}" if ag.get("url") else ""),
        "",
        f"Generate the drafts with `optout draft-escalations --state {law.code}`.",
        "",
        f"> {laws.disclaimer()}",
    ]
    return "\n".join(lines)
