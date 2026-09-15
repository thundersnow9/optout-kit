"""Command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import canary, clocks, directory, guard, laws, render, targets


def _load_profile(path: str | None) -> dict:
    if not path:
        raise SystemExit("--profile is required (it lives in your private state repo)")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _preferred_notice(law: laws.StateLaw) -> str | None:
    pm = law.preferred_mechanism
    if not pm:
        return None
    return "\n".join([
        "",
        f"  ==> {law.name} has a centralized mechanism: {pm['name']} ({pm['id']}).",
        f"      {pm['url']}  [{pm['cost']}, covers {pm['covers_brokers']} registered brokers]",
        f"      Enforceable since {pm['enforceable_since']}; "
        f"brokers must poll every {pm['broker_poll_interval_days']} days "
        f"or face {pm['penalty']}.",
        f"      {pm['note']}",
        "",
        "      Per-broker outreach is largely redundant here. Use --ignore-preferred",
        "      to build the full list anyway.",
        "",
    ])


def cmd_states(args: argparse.Namespace) -> int:
    for code, law in sorted(laws.all_states().items()):
        mark = "verified" if law.verified else "UNVERIFIED"
        pm = law.preferred_mechanism
        extra = f"  [{pm['id']}]" if pm else ""
        print(f"{code}  {law.abbrev:<12} {law.response_days:>3}d  {mark}{extra}")
    print(f"\n{laws.disclaimer()}")
    return 0


def cmd_build_targets(args: argparse.Namespace) -> int:
    law = laws.load(args.state)
    notice = _preferred_notice(law)
    if notice and not args.ignore_preferred:
        print(notice)
        if not args.json:
            return 0

    rows = targets.build(args.state, allow_id_upload=args.allow_id)
    if args.json:
        out = json.dumps(targets.to_dicts(rows), indent=2)
        if args.out:
            Path(args.out).write_text(out, encoding="utf-8")
            print(f"wrote {len(rows)} targets to {args.out}")
        else:
            print(out)
        return 0

    s = targets.summarize(rows, args.state)
    print(f"State {s['state']} ({s['law']}), law entry verified: {s['law_verified']}")
    print(f"  actionable       {s['actionable']:>4}   (email {s['email']}, form {s['form']})")
    print(f"  skipped: ID req  {s['skipped_id']:>4}")
    print(f"  skipped: no route{s['no_route']:>4}")
    print(f"  total considered {s['total']:>4}")
    print("\nBy tier (0=wholesaler, 1=crucial, 2=high, 3=long tail):")
    for tier, n in s["by_tier"].items():
        print(f"  tier {tier}: {n}")
    print("\nFirst 15 actionable:")
    for t in [t for t in rows if t.actionable][:15]:
        phone = " [phone]" if t.requires_phone else ""
        print(f"  t{t.tier} {t.title[:38]:<38} {t.method:<5} {t.route[:44]}{phone}")
    return 0


def cmd_draft(args: argparse.Namespace) -> int:
    profile = _load_profile(args.profile)
    rows = [t for t in targets.build(args.state, allow_id_upload=args.allow_id)
            if t.actionable and t.method == "email"]
    if args.tier is not None:
        rows = [t for t in rows if t.tier == args.tier]
    # Never draft for a broker the user has deliberately excluded. This is
    # honored by DEFAULT whenever a ledger is present: an exclusion that only
    # applies when you remember a flag is not an exclusion.
    ledger_dir = Path(args.ledger)
    if ledger_dir.is_dir() and not args.ignore_exclusions:
        excluded = {
            e.slug: e.status for e in clocks.load_ledger(ledger_dir)
            if e.status in clocks.TERMINAL
        }
        held = [t for t in rows if t.slug in excluded]
        rows = [t for t in rows if t.slug not in excluded]
        for t in held:
            print(f"  skipping {t.title} ({excluded[t.slug]})", file=sys.stderr)
    elif not ledger_dir.is_dir():
        print(f"  note: no ledger at {ledger_dir}, so no exclusions applied",
              file=sys.stderr)
    rows = rows[: args.limit]

    outdir = Path(args.out) if args.out else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

    overrides = canary.load_overrides(args.canaries)
    for t in rows:
        alias = canary.for_broker(profile, t.slug, overrides)
        subject, body = render.deletion(t.title, profile, args.state,
                                        canary_email=alias)
        if args.dry_run:
            print("=" * 72)
            print(f"TO: {t.email}")
            print(f"SUBJECT: {subject}")
            print()
            print(body)
        elif outdir:
            (outdir / f"{t.slug}.txt").write_text(
                f"TO: {t.email}\nSUBJECT: {subject}\n\n{body}", encoding="utf-8")
    if not args.dry_run and outdir:
        print(f"wrote {len(rows)} drafts to {outdir}")
    elif not args.dry_run:
        print("Nothing written: pass --dry-run to preview or --out DIR to save.")
    return 0


def cmd_init_ledger(args: argparse.Namespace) -> int:
    """Seed ledger entries for targets that don't have one yet.

    Entries hold broker status and dates only. No personal data: the ledger is
    committed to the private repo as an audit trail, and must stay PII-free so
    that trail can be shared with a regulator without redaction.
    """
    ledger = Path(args.ledger)
    ledger.mkdir(parents=True, exist_ok=True)
    rows = targets.build(args.state, allow_id_upload=args.allow_id)
    if args.max_tier is not None:
        rows = [t for t in rows if t.tier <= args.max_tier]

    created = 0
    for t in rows:
        path = ledger / f"{t.slug}.json"
        if path.exists():
            continue
        status = t.skip_reason or "pending"
        path.write_text(json.dumps({
            "slug": t.slug,
            "title": t.title,
            "state": args.state.upper(),
            "tier": t.tier,
            "method": t.method,
            "route": t.route,
            "requires_phone": t.requires_phone,
            "status": status,
            "events": [],
        }, indent=2) + "\n", encoding="utf-8")
        created += 1
    print(f"created {created} ledger entries in {ledger} ({len(rows)} targets considered)")
    return 0


def cmd_draft_escalations(args: argparse.Namespace) -> int:
    """Render the appeal / AG-complaint text for every lapsed deadline."""
    profile = _load_profile(args.profile)
    entries = {e.slug: e for e in clocks.load_ledger(Path(args.ledger))}
    today = date.fromisoformat(args.today) if args.today else None
    actions = clocks.evaluate(list(entries.values()), args.state, today=today)

    if not actions:
        print("No escalations due.")
        return 0

    outdir = Path(args.out) if args.out else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

    overrides = canary.load_overrides(args.canaries)
    for a in actions:
        entry = entries[a.slug]
        alias = canary.for_broker(profile, a.slug, overrides)
        sent = entry.event_date("sent")
        if a.action == "appeal":
            subject, body = render.appeal(
                a.title, profile, args.state,
                original_date=str(sent) if sent else "an earlier date",
                denied=entry.status == "denied", today=today,
                canary_email=alias)
        elif a.action == "ag_complaint":
            timeline = [
                f"{ev.get('date', '?')}  {ev.get('type', '?')}"
                for ev in sorted(entry.raw.get("events", []), key=lambda e: e.get("date", ""))
            ]
            subject, body = render.ag_complaint(
                a.title, profile, args.state, timeline=timeline,
                appealed=entry.event_date("appealed") is not None, today=today,
                canary_email=alias)
        else:  # refile: a fresh deletion request, citing the prior removal
            confirmed = entry.event_date("confirmed")
            subject, body = render.deletion(
                a.title, profile, args.state, today=today,
                prior_removal=str(confirmed) if confirmed else None,
                canary_email=alias)

        if outdir:
            (outdir / f"{a.slug}.{a.action}.txt").write_text(
                f"SUBJECT: {subject}\n\n{body}", encoding="utf-8")
        else:
            print("=" * 72)
            print(f"[{a.action}] {a.title}")
            print(f"SUBJECT: {subject}")
            print()
            print(body)

    if outdir:
        print(f"wrote {len(actions)} escalation drafts to {outdir}")
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    """Append an event to ledger entries. This is what starts the clock."""
    ledger = Path(args.ledger)
    when = args.date or date.today().isoformat()
    slugs = args.slugs or [p.stem for p in sorted(ledger.glob("*.json"))]

    touched = 0
    for slug in slugs:
        path = ledger / f"{slug}.json"
        if not path.exists():
            print(f"  no ledger entry: {slug}", file=sys.stderr)
            continue
        entry = json.loads(path.read_text(encoding="utf-8"))
        # Never silently reopen something the user deliberately excluded.
        if entry.get("status") in clocks.NEVER_ESCALATE and not args.force:
            print(f"  skipping {slug} ({entry['status']}); --force to override",
                  file=sys.stderr)
            continue
        if args.tier is not None and entry.get("tier") != args.tier:
            continue
        entry.setdefault("events", []).append(
            {"date": when, "type": args.event, **({"note": args.note} if args.note else {})})
        entry["status"] = args.event
        path.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
        touched += 1
    print(f"marked {touched} entr{'y' if touched == 1 else 'ies'} as {args.event} on {when}")
    return 0


def cmd_check_clocks(args: argparse.Namespace) -> int:
    entries = clocks.load_ledger(Path(args.ledger))
    today = date.fromisoformat(args.today) if args.today else None
    actions = clocks.evaluate(entries, args.state, today=today)

    if args.issue:
        print(clocks.render_issue(actions, args.state))
        return 0

    print(f"ledger entries: {len(entries)}")
    if not actions:
        print("No escalations due.")
        return 0
    print(f"escalations due: {len(actions)}\n")
    for a in actions:
        print(f"  {a.title[:34]:<34} {a.action:<14} {a.days_overdue:>4}d overdue  {a.citation or ''}")
    return 1 if args.fail_on_action else 0


def cmd_trace(args: argparse.Namespace) -> int:
    """Given an address that received mail, name the broker it was issued to."""
    slug = canary.source_of(args.address)
    if not slug:
        print(f"{args.address} carries no canary tag, so the source cannot be attributed.")
        return 1

    ledger = Path(args.ledger)
    entry_path = ledger / f"{slug}.json"
    if entry_path.exists():
        entry = json.loads(entry_path.read_text(encoding="utf-8"))
        print(f"Issued to: {entry.get('title', slug)}  (slug {slug})")
        print(f"  status: {entry.get('status')}")
        for ev in entry.get("events", []):
            print(f"  {ev.get('date')}  {ev.get('type')}")
        if entry.get("status") == "confirmed":
            print("\n  This broker confirmed deletion, yet the address is receiving mail.")
            print("  Mark it relisted to trigger a refile citing that confirmation:")
            print(f"    optout mark relisted {slug}")
    else:
        print(f"Issued to: {slug} (no ledger entry found under that slug)")
    return 0


def cmd_guard(args: argparse.Namespace) -> int:
    findings = list(guard.scan_generic())
    if args.profile and Path(args.profile).exists():
        findings += guard.scan_local(Path(args.profile))
    print(guard.report(findings))
    return 1 if findings else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="optout", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("states", help="list known state privacy laws").set_defaults(fn=cmd_states)

    bt = sub.add_parser("build-targets", help="build a prioritized target list")
    bt.add_argument("--state", required=True)
    bt.add_argument("--allow-id", action="store_true",
                    help="include brokers that demand identity documents (default: skip)")
    bt.add_argument("--ignore-preferred", action="store_true",
                    help="build per-broker list even where a central mechanism exists")
    bt.add_argument("--json", action="store_true")
    bt.add_argument("--out")
    bt.set_defaults(fn=cmd_build_targets)

    dr = sub.add_parser("draft", help="render deletion requests")
    dr.add_argument("--state", required=True)
    dr.add_argument("--profile", help="path to profile.json in your PRIVATE repo")
    dr.add_argument("--limit", type=int, default=25)
    dr.add_argument("--tier", type=int)
    dr.add_argument("--allow-id", action="store_true")
    dr.add_argument("--canaries", default="canaries.json",
                    help="per-broker address overrides (default: ./canaries.json)")
    dr.add_argument("--ledger", default="ledger",
                    help="ledger whose exclusions to honor (default: ./ledger)")
    dr.add_argument("--ignore-exclusions", action="store_true",
                    help="draft even for brokers marked excluded (rarely correct)")
    dr.add_argument("--dry-run", action="store_true")
    dr.add_argument("--out")
    dr.set_defaults(fn=cmd_draft)

    il = sub.add_parser("init-ledger", help="seed ledger entries for new targets")
    il.add_argument("--state", required=True)
    il.add_argument("--ledger", required=True)
    il.add_argument("--max-tier", type=int, help="only seed through this tier (0=wholesalers)")
    il.add_argument("--allow-id", action="store_true")
    il.set_defaults(fn=cmd_init_ledger)

    de = sub.add_parser("draft-escalations", help="render appeals and AG complaints")
    de.add_argument("--state", required=True)
    de.add_argument("--ledger", required=True)
    de.add_argument("--profile", help="path to profile.json in your PRIVATE repo")
    de.add_argument("--canaries", default="canaries.json")
    de.add_argument("--today", help="override today's date (ISO) for testing")
    de.add_argument("--out")
    de.set_defaults(fn=cmd_draft_escalations)

    mk = sub.add_parser("mark", help="record an event (sent, confirmed, denied, ...)")
    mk.add_argument("event", choices=["sent", "acknowledged", "extended", "confirmed",
                                      "denied", "appealed", "appeal_denied", "relisted"])
    mk.add_argument("slugs", nargs="*", help="broker slugs (default: every entry)")
    mk.add_argument("--ledger", default="ledger")
    mk.add_argument("--tier", type=int, help="only entries in this tier")
    mk.add_argument("--date", help="ISO date (default: today)")
    mk.add_argument("--note")
    mk.add_argument("--force", action="store_true",
                    help="also mark entries that were deliberately excluded")
    mk.set_defaults(fn=cmd_mark)

    ck = sub.add_parser("check-clocks", help="find lapsed statutory deadlines")
    ck.add_argument("--state", required=True)
    ck.add_argument("--ledger", required=True)
    ck.add_argument("--today", help="override today's date (ISO) for testing")
    ck.add_argument("--issue", action="store_true", help="emit markdown issue body")
    ck.add_argument("--fail-on-action", action="store_true")
    ck.set_defaults(fn=cmd_check_clocks)

    tr = sub.add_parser("trace", help="identify which broker leaked an address")
    tr.add_argument("address")
    tr.add_argument("--ledger", default="ledger")
    tr.set_defaults(fn=cmd_trace)

    g = sub.add_parser("guard", help="scan the staged diff for personal data")
    g.add_argument("--profile", help="path to profile.json for exact matching")
    g.set_defaults(fn=cmd_guard)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
