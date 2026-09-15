import json

from optout_kit import guard

# Synthetic fixture data. The pragma marks these lines exempt when this file is
# itself committed; the strings are still scanned when fed to the guard below.
_ADDR = "100 Example Way"  # pii-guard: allow
_PHONE = "555-123-4567"  # pii-guard: allow

DIFF = f"""diff --git a/notes.md b/notes.md
--- a/notes.md
+++ b/notes.md
@@ -0,0 +1,3 @@
+My address is {_ADDR}, Portland
+call me at {_PHONE}
+nothing sensitive here
"""


def test_generic_catches_phone_number():
    kinds = {f["kind"] for f in guard.scan_generic(DIFF)}
    assert "US phone number" in kinds


def test_local_matches_profile_values(tmp_path):
    p = tmp_path / "profile.json"
    p.write_text(json.dumps({"full_name": "Jane Q Testperson",
                             "addresses": [{"line1": _ADDR}]}))
    findings = guard.scan_local(p, DIFF)
    assert any(f["field"] == "addresses[0].line1" for f in findings)


def test_report_never_leaks_the_matched_value(tmp_path):
    p = tmp_path / "profile.json"
    secret = _ADDR
    p.write_text(json.dumps({"addresses": [{"line1": secret}]}))
    text = guard.report(guard.scan_local(p, DIFF))
    assert secret not in text
    assert "BLOCKED" in text


def test_clean_diff_passes():
    clean = ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
             "@@ -0,0 +1,1 @@\n+print('hello')\n")
    assert guard.scan_generic(clean) == []
    assert "clean" in guard.report([])


def test_pragma_exempts_a_line():
    diff = ("diff --git a/fixtures.py b/fixtures.py\n--- a/fixtures.py\n+++ b/fixtures.py\n"
            "@@ -0,0 +1,2 @@\n"
            '+SAMPLE = "555-123-4567"  # pii-guard: allow\n'
            '+REAL = "555-987-6543"\n')  # pii-guard: allow
    findings = guard.scan_generic(diff)
    assert len(findings) == 1, "only the un-pragma'd line should be flagged"
    assert findings[0]["line"] == 2
