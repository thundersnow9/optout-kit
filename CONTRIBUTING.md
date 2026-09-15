# Contributing

The most valuable contribution is **a verified state-law entry**.

## Adding or correcting a state

Entries in `data/state-laws.json` carry a `verified` flag. Set it to `true` only when
every citation has been checked against a **primary source**: the statute itself, the
state Attorney General, or the state privacy regulator. Not a law-firm blog post, not a
vendor comparison chart, and not an LLM.

Include in `sources` the URLs you actually checked. A PR that flips `verified` to `true`
without primary-source links will be asked for them.

Required fields:

- `deletion_right_citation` — the specific section granting deletion
- `response_days` / `extension_days` — and `response_citation` if separate
- `appeal` — `available`, `citation`, `response_days` (these differ: Oregon 45, Texas 60)
- `ag_complaint` — where a consumer actually files
- `gpc_mandatory` / `gpc_since`
- `broker_registry` — most states have none; say so explicitly
- `thresholds` — who the law applies to, in plain language

If a state has a centralized mechanism like California's DROP, add `preferred_mechanism`
so the tool routes users there instead of generating hundreds of redundant requests.

## Broker notes

`data/broker-notes.json` records observations: priority tier, whether a broker demands
identity documents, whether it requires a phone call. Reference broker *names* only.
Do not copy descriptive text from the upstream CC BY-NC-SA directories.

## Ground rules

- Never commit personal data. CI runs the PII guard on every PR.
- No scrapers, no automated form submission, no credential handling.
- No dependencies without a strong reason; the tool is stdlib-only by design.
