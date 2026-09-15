from datetime import date, timedelta
from pathlib import Path
import json

from optout_kit import clocks

TODAY = date(2026, 9, 14)


def _entry(tmp_path: Path, slug: str, status: str, events: list[dict]) -> clocks.Entry:
    p = tmp_path / f"{slug}.json"
    p.write_text(json.dumps({"slug": slug, "title": slug, "status": status,
                             "events": events}))
    return clocks.Entry(path=p, raw=json.loads(p.read_text()))


def _ago(days: int) -> str:
    return str(TODAY - timedelta(days=days))


def test_lapsed_deadline_triggers_appeal(tmp_path):
    e = _entry(tmp_path, "spokeo", "sent", [{"date": _ago(50), "type": "sent"}])
    actions = clocks.evaluate([e], "OR", today=TODAY)
    assert [a.action for a in actions] == ["appeal"]
    assert actions[0].days_overdue == 5
    assert actions[0].citation == "ORS 646A.578"


def test_extension_suspends_escalation(tmp_path):
    # 45 + 45 = 90 day window; only 50 days have passed.
    e = _entry(tmp_path, "radaris", "extended",
               [{"date": _ago(50), "type": "sent"}, {"date": _ago(40), "type": "extended"}])
    assert clocks.evaluate([e], "OR", today=TODAY) == []


def test_denial_triggers_immediate_appeal(tmp_path):
    e = _entry(tmp_path, "mylife", "denied",
               [{"date": _ago(20), "type": "sent"}, {"date": _ago(5), "type": "denied"}])
    assert [a.action for a in clocks.evaluate([e], "OR", today=TODAY)] == ["appeal"]


def test_ignored_appeal_escalates_to_ag(tmp_path):
    e = _entry(tmp_path, "intelius", "appealed",
               [{"date": _ago(120), "type": "sent"}, {"date": _ago(60), "type": "appealed"}])
    a = clocks.evaluate([e], "OR", today=TODAY)[0]
    assert a.action == "ag_complaint" and a.days_overdue == 15


def test_relisting_after_confirmation_refiles(tmp_path):
    e = _entry(tmp_path, "nuwber", "confirmed",
               [{"date": _ago(200), "type": "sent"}, {"date": _ago(150), "type": "confirmed"},
                {"date": _ago(9), "type": "relisted"}])
    assert [a.action for a in clocks.evaluate([e], "OR", today=TODAY)] == ["refile"]


def test_confirmed_removal_is_silent(tmp_path):
    e = _entry(tmp_path, "thatsthem", "confirmed",
               [{"date": _ago(100), "type": "sent"}, {"date": _ago(80), "type": "confirmed"}])
    assert clocks.evaluate([e], "OR", today=TODAY) == []


def test_texas_appeal_window_is_sixty_days(tmp_path):
    # TX gives 60 days for appeals, not 45; at 50 days nothing is due yet.
    e = _entry(tmp_path, "spokeo", "appealed", [{"date": _ago(50), "type": "appealed"}])
    assert clocks.evaluate([e], "TX", today=TODAY) == []
    e2 = _entry(tmp_path, "spokeo2", "appealed", [{"date": _ago(70), "type": "appealed"}])
    assert [a.action for a in clocks.evaluate([e2], "TX", today=TODAY)] == ["ag_complaint"]


def test_user_exclusion_never_escalates(tmp_path):
    # A broker the user deliberately excluded stays quiet forever, even though
    # its deadline would otherwise have lapsed long ago.
    e = _entry(tmp_path, "someonesemployer", "skipped_employer_conflict",
               [{"date": _ago(400), "type": "sent"}])
    assert clocks.evaluate([e], "OR", today=TODAY) == []


def test_exclusion_survives_a_relisting(tmp_path):
    e = _entry(tmp_path, "someonesemployer", "skipped_employer_conflict",
               [{"date": _ago(400), "type": "sent"}, {"date": _ago(5), "type": "relisted"}])
    assert clocks.evaluate([e], "OR", today=TODAY) == []
