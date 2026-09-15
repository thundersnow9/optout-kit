"""Render statute-aware request text.

Templates use string.Template so the package has no third-party dependencies.
Personal data is passed in at call time and never persisted by this module.
"""

from __future__ import annotations

from datetime import date
from importlib.resources import files
from pathlib import Path
from string import Template
from typing import Any

from . import laws


def _template(name: str) -> Template:
    for c in (
        files("optout_kit").joinpath(f"templates/{name}.md"),
        files("optout_kit").parent.joinpath(f"templates/{name}.md"),
    ):
        try:
            return Template(c.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError):
            continue
    raise FileNotFoundError(f"template {name!r} not found")


def identity_block(profile: dict[str, Any]) -> str:
    """The minimum a broker needs to find a record, formatted as a block.

    Deliberately excludes SSN, driver's licence and date of birth: brokers do
    not need them to locate a listing, and several have been breached.
    """
    lines: list[str] = []
    if profile.get("full_name"):
        lines.append(f"  Name: {profile['full_name']}")
    for alias in profile.get("also_known_as", []) or []:
        lines.append(f"  Also listed as: {alias}")
    for addr in profile.get("addresses", []) or []:
        label = "Current address" if addr.get("current") else "Former address"
        parts = [addr.get("line1"), addr.get("city"), addr.get("state"), addr.get("zip")]
        lines.append(f"  {label}: " + ", ".join(p for p in parts if p))
    for email in profile.get("emails", []) or []:
        lines.append(f"  Email: {email}")
    for phone in profile.get("phones", []) or []:
        lines.append(f"  Phone: {phone}")
    if profile.get("birth_year"):
        lines.append(f"  Year of birth: {profile['birth_year']}")
    return "\n".join(lines) if lines else "  (no identifying details supplied)"


def _subject_and_body(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        return lines[0][8:].strip(), "\n".join(lines[1:]).lstrip("\n")
    return "", text


def deletion(broker_title: str, profile: dict[str, Any], state: str,
             today: date | None = None,
             prior_removal: str | None = None) -> tuple[str, str]:
    law = laws.load(state)
    rc = law.raw.get("response_citation")
    appeal = law.appeal
    appeal_clause = (
        f"If you decline this request, {law.abbrev} gives me a right of appeal under "
        f"{appeal['citation']}, and requires you to tell me how to complain to the "
        f"{law.ag.get('name', 'state Attorney General')} if that appeal is refused."
        if appeal.get("available") and appeal.get("citation")
        else f"If you decline this request, please state your legal basis for doing so."
    )
    # A re-listing after a confirmed deletion is the strongest fact available:
    # it shows the failure is systemic rather than a missed request.
    prior_clause = ""
    if prior_removal:
        prior_clause = (
            f"On {prior_removal} you confirmed in writing that my personal data had been\n"
            "deleted. It has since reappeared in your records. This request therefore\n"
            "concerns a repeat occurrence, and I am retaining the prior confirmation.\n\n"
        )
    text = _template("deletion").safe_substitute(
        prior_removal_clause=prior_clause,
        broker_title=broker_title,
        law_abbrev=law.abbrev,
        state_name=law.name,
        deletion_citation=law.deletion_citation,
        response_days=law.response_days,
        response_citation_clause=f" ({rc})" if rc else "",
        identity_block=identity_block(profile),
        appeal_clause=appeal_clause,
        today=(today or date.today()).isoformat(),
        signature=profile.get("signature", profile.get("full_name", "")),
    )
    return _subject_and_body(text)


def appeal(broker_title: str, profile: dict[str, Any], state: str, original_date: str,
           denied: bool, today: date | None = None) -> tuple[str, str]:
    law = laws.load(state)
    ap = law.appeal
    days = ap.get("response_days") or law.response_days
    text = _template("appeal").safe_substitute(
        broker_title=broker_title,
        law_abbrev=law.abbrev,
        deletion_citation=law.deletion_citation,
        appeal_citation=ap.get("citation", "the applicable appeal provision"),
        original_date=original_date,
        outcome_phrase="denial" if denied else "non-response",
        outcome_sentence=(
            "That request was denied." if denied else
            f"More than {law.response_days} days have passed and I have received no "
            "substantive response."
        ),
        appeal_deadline_clause=f"{law.abbrev} requires a written response within {days} days.",
        ag_name=law.ag.get("name", "state Attorney General"),
        identity_block=identity_block(profile),
        today=(today or date.today()).isoformat(),
        signature=profile.get("signature", profile.get("full_name", "")),
    )
    return _subject_and_body(text)


def ag_complaint(broker_title: str, profile: dict[str, Any], state: str,
                 timeline: list[str], appealed: bool,
                 today: date | None = None) -> tuple[str, str]:
    law = laws.load(state)
    reg = law.raw.get("broker_registry") or {}
    registry_clause = ""
    if reg.get("exists"):
        registry_clause = (
            f"Note that {reg.get('administered_by', 'this state')} maintains a data broker "
            f"registry under {reg.get('citation', 'state law')}. If {broker_title} is not "
            "registered, that is a separate violation."
        )
    text = _template("ag_complaint").safe_substitute(
        broker_title=broker_title,
        law_abbrev=law.abbrev,
        state_name=law.name,
        deletion_citation=law.deletion_citation,
        ag_name=law.ag.get("name", "Attorney General"),
        timeline_block="\n".join(f"  {line}" for line in timeline),
        appeal_ref_clause=(
            f", and did not adequately respond to an appeal under {law.appeal.get('citation')}"
            if appealed and law.appeal.get("citation") else ""
        ),
        registry_clause=registry_clause,
        today=(today or date.today()).isoformat(),
        signature=profile.get("signature", profile.get("full_name", "")),
    )
    return _subject_and_body(text)
