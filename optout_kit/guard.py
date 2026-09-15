"""Block personal data from entering git history.

Two layers, because they defend against different mistakes:

1. local  -- reads the real profile (never committed) and looks for those exact
             values in the staged diff. Precise, but only works where the
             profile exists, i.e. on the owner's machine.
2. generic -- pattern matching for PII shapes. Runs in CI, where the profile
             must never be present, and catches a contributor (or a future you)
             pasting something real into a fixture or an example.

The guard never prints a matched value. It reports the field name and location
only, so that guard output cannot itself become the leak.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

# Tokens too short or too common to match on without constant false positives.
_MIN_TOKEN = 5

# An explicit, per-line exemption for deliberately fake data (test fixtures,
# documentation examples). Inline rather than a path allowlist so that every
# exemption is visible in the diff that introduces it, and so exempting a whole
# directory is never the easy option.
PRAGMA = "pii-guard: allow"
_STOPWORDS = {"street", "avenue", "drive", "north", "south", "east", "west", "apt"}

GENERIC_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("US Social Security number", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("US phone number", re.compile(r"\b(?:\+?1[-. ])?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b")),
    ("date of birth", re.compile(r"\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b")),
    ("street address", re.compile(r"\b\d{1,6}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+"
                                  r"(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Dr|Drive|Ln|Lane|Ct|Court|Way)\b")),
    ("credit card number", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
]


class Finding(dict):
    """A guard hit. Deliberately carries no matched text."""


def _staged_diff() -> str:
    try:
        return subprocess.run(
            ["git", "diff", "--cached", "--unified=0"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _added_lines(diff: str) -> list[tuple[str, int, str]]:
    """(file, lineno, text) for every added line in a unified diff."""
    out: list[tuple[str, int, str]] = []
    path, lineno = "?", 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path, lineno = line[6:], 0
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            lineno = int(m.group(1)) if m else 0
        elif line.startswith("+") and not line.startswith("+++"):
            if PRAGMA not in line:
                out.append((path, lineno, line[1:]))
            lineno += 1
    return out


def profile_tokens(profile: dict[str, Any]) -> dict[str, str]:
    """Flatten a profile into {field_path: value} for exact matching."""
    tokens: dict[str, str] = {}

    def walk(node: Any, trail: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{trail}.{k}" if trail else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{trail}[{i}]")
        elif node is not None:
            s = str(node).strip()
            if len(s) >= _MIN_TOKEN and s.lower() not in _STOPWORDS:
                tokens[trail] = s

    walk(profile, "")
    return tokens


def scan_local(profile_path: Path, diff: str | None = None) -> list[Finding]:
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    tokens = profile_tokens(profile)
    findings: list[Finding] = []
    for path, lineno, text in _added_lines(diff if diff is not None else _staged_diff()):
        low = text.lower()
        for field, value in tokens.items():
            if value.lower() in low:
                findings.append(Finding(file=path, line=lineno, kind="profile value",
                                        field=field))
    return findings


def scan_generic(diff: str | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for path, lineno, text in _added_lines(diff if diff is not None else _staged_diff()):
        for label, pattern in GENERIC_PATTERNS:
            if pattern.search(text):
                findings.append(Finding(file=path, line=lineno, kind=label, field=None))
    return findings


def report(findings: Iterable[Finding]) -> str:
    findings = list(findings)
    if not findings:
        return "PII guard: clean."
    lines = [f"PII guard: BLOCKED ({len(findings)} finding(s)).", ""]
    for f in findings:
        where = f"{f['file']}:{f['line']}"
        what = f["kind"] + (f" (profile field {f['field']})" if f.get("field") else "")
        lines.append(f"  {where}  {what}")
    lines += [
        "",
        "Personal data must not enter this repository's history.",
        "Move it to your private state repo, or add the file to .gitignore.",
        "Values are withheld from this report by design.",
    ]
    return "\n".join(lines)
