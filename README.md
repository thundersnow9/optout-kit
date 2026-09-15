# optout-kit

Statute-aware tooling for getting your personal data deleted from data brokers,
and for escalating when they ignore you.

No dependencies. No telemetry. No personal data in this repository, ever.

## Why this exists

Commercial removal services charge $100-150/yr and do not perform especially well.
In Consumer Reports' field test, DeleteMe removed 27% of records at $129/yr, while
EasyOptOuts reached 65% at $19.99/yr. None of them do the one thing state law
actually provides for: when a broker ignores a lawful deletion request, you have a
statutory right of appeal and then a complaint to your Attorney General.

Tracking those deadlines is purely mechanical. That is what this automates.

## The state-law matrix

[`data/state-laws.json`](data/state-laws.json) (CC0) maps each US state privacy law to
the mechanics you need to actually use it: the deletion-right citation, the response
deadline and extension, whether an appeal exists and how long it runs, where the AG
complaint goes, whether Global Privacy Control is mandatory, and the broker-registry
status.

```
$ optout states
CA  CCPA/CPRA     45d  verified  [DROP]
CO  CPA           45d  UNVERIFIED
CT  CTDPA         45d  UNVERIFIED
OR  OCPA          45d  verified
TX  TDPSA         45d  verified
VA  VCDPA         45d  UNVERIFIED
```

Entries marked `UNVERIFIED` have not been confirmed against primary sources at the
subsection level. That is deliberate: an unverified citation is flagged rather than
quietly presented as fact. See [CONTRIBUTING.md](CONTRIBUTING.md).

### California is a special case

The DELETE Act's **DROP** platform went live 2026-01-01 and became enforceable
2026-08-01. One free verified request binds every registered data broker (603 as of
2026-09-01), who must poll it every 45 days or face $200 per request per day.

If you are a California resident, that single step supersedes nearly everything else
here, and the tool will tell you so rather than hand you 400 email drafts:

```
$ optout build-targets --state CA
  ==> California has a centralized mechanism: Delete Request and Opt-out Platform (DROP).
      https://consumer.drop.privacy.ca.gov  [free, covers 603 registered brokers]
```

We do not automate DROP submission. It is a one-time manual step, and its Terms of Use
prohibit exploiting access to the platform.

## Install

```sh
pip install -e .
```

Requires Python 3.10+. There are no runtime dependencies.

## Use

```sh
optout states                                   # what the matrix knows
optout build-targets --state OR                 # prioritized work queue
optout draft --state OR --profile ../optout-state/profile.json --tier 1 --dry-run
optout check-clocks --state OR --ledger ../optout-state/ledger --issue
optout guard --profile profile.json             # pre-commit PII scan
```

Targets are ordered by leverage, not alphabetically:

- **tier 0** upstream wholesalers (Acxiom, Epsilon, LexisNexis, Data Axle, Thomson
  Reuters). Opting out here starves many downstream people-search sites, so do these first.
- **tier 1** the sites that actually surface when someone searches your name
- **tier 2/3** the long tail

By default, brokers that demand identity documents are **skipped**, not fed more data.
Pass `--allow-id` to include them.

## Your data lives somewhere else

This repo is public and git history is permanent, so personal data is kept out
structurally rather than by `.gitignore` discipline. You keep a **separate private
repo** holding `profile.json`, your ledger, and your canary map. This one is a library
and a CLI that has no idea who you are.

See [docs/privacy.md](docs/privacy.md) for the split, and install the pre-commit guard
**before your first commit** — it cannot be retrofitted onto history that already
contains a leak.

## Attribution

Broker directory data comes from [Optery](https://github.com/optery/optery-data-brokers-directory)
and the [Big-Ass Data Broker Opt-Out List](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List),
both CC BY-NC-SA 4.0. That data is **fetched at runtime, never vendored**, so this
MIT-licensed tool does not impose NonCommercial terms on you. See
[docs/attribution.md](docs/attribution.md).

## Disclaimer

Not legal advice. The matrix is a good-faith reading of public law by non-lawyers.
Verify citations against primary sources before relying on them.

## License

Code: MIT. `data/state-laws.json` and `data/broker-notes.json`: CC0.
