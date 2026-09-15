"""Access to the CC0 state-law matrix."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any


class UnknownState(KeyError):
    """Raised when a state has no entry in the matrix."""


def _matrix() -> dict[str, Any]:
    # data/ sits beside the package in the repo and is installed as package data.
    for candidate in (
        files("optout_kit").joinpath("data/state-laws.json"),
        files("optout_kit").parent.joinpath("data/state-laws.json"),
    ):
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError):
            continue
    raise FileNotFoundError("state-laws.json not found")


@dataclass(frozen=True)
class StateLaw:
    code: str
    raw: dict[str, Any]

    @property
    def name(self) -> str:
        return self.raw["name"]

    @property
    def abbrev(self) -> str:
        return self.raw["law_abbrev"]

    @property
    def deletion_citation(self) -> str:
        return self.raw["deletion_right_citation"]

    @property
    def response_days(self) -> int:
        return self.raw["response_days"]

    @property
    def appeal(self) -> dict[str, Any]:
        return self.raw.get("appeal") or {"available": False}

    @property
    def ag(self) -> dict[str, Any]:
        return self.raw.get("ag_complaint") or {}

    @property
    def verified(self) -> bool:
        return bool(self.raw.get("verified"))

    @property
    def preferred_mechanism(self) -> dict[str, Any] | None:
        """A centralized platform that supersedes per-broker outreach (e.g. CA DROP)."""
        return self.raw.get("preferred_mechanism")


def load(state: str) -> StateLaw:
    code = state.strip().upper()
    states = _matrix()["states"]
    if code not in states:
        known = ", ".join(sorted(states))
        raise UnknownState(
            f"No entry for {code!r}. Known: {known}. "
            "Contributions welcome: see CONTRIBUTING.md."
        )
    return StateLaw(code=code, raw=states[code])


def all_states() -> dict[str, StateLaw]:
    return {k: StateLaw(code=k, raw=v) for k, v in _matrix()["states"].items()}


def disclaimer() -> str:
    return _matrix()["disclaimer"]
