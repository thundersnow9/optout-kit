"""Command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import clocks, directory, guard, laws, render, targets


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
    rows = rows[: args.limit]

    outdir = Path(args.out) if args.out else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

    for t in rows:
        subject, body = render.deletion(t.title, profile, args.state)
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

    for a in actions:
        entry = entries[a.slug]
        sent = entry.event_date("sent")
        if a.action == "appeal":
            subject, body = render.appeal(
                a.title, profile, args.state,
                original_date=str(sent) if sent else "an earlier date",
                denied=entry.status == "denied", today=today)
        elif a.action == "ag_complaint":
            timeline = [
                f"{ev.get('date', '?')}  {ev.get('type', '?')}"
                for ev in sorted(entry.raw.get("events", []), key=lambda e: e.get("date", ""))
            ]
            subject, body = render.ag_complaint(
                a.title, profile, args.state, timeline=timeline,
                appealed=entry.event_date("appealed") is not None, today=today)
        else:  # refile: a fresh deletion request, citing the prior removal
            confirmed = entry.event_date("confirmed")
            subject, body = render.deletion(
                a.title, profile, args.state, today=today,
                prior_removal=str(confirmed) if confirmed else None)

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
    dr.add_argument("--dry-run", action="store_true")
    dr.add_argument("--out")
    dr.set_defaults(fn=cmd_draft)

    de = sub.add_parser("draft-escalations", help="render appeals and AG complaints")
    de.add_argument("--state", required=True)
    de.add_argument("--ledger", required=True)
    de.add_argument("--profile", help="path to profile.json in your PRIVATE repo")
    de.add_argument("--today", help="override today's date (ISO) for testing")
    de.add_argument("--out")
    de.set_defaults(fn=cmd_draft_escalations)

    ck = sub.add_parser("check-clocks", help="find lapsed statutory deadlines")
    ck.add_argument("--state", required=True)
    ck.add_argument("--ledger", required=True)
    ck.add_argument("--today", help="override today's date (ISO) for testing")
    ck.add_argument("--issue", action="store_true", help="emit markdown issue body")
    ck.add_argument("--fail-on-action", action="store_true")
    ck.set_defaults(fn=cmd_check_clocks)

    g = sub.add_parser("guard", help="scan the staged diff for personal data")
    g.add_argument("--profile", help="path to profile.json for exact matching")
    g.set_defaults(fn=cmd_guard)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
