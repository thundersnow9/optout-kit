# Keeping personal data out of git

## The two-repo split

| | `optout-kit` (public) | `optout-state` (private) |
| --- | --- | --- |
| Contains | code, templates, state-law matrix, workflows | `profile.json`, `ledger/`, `canaries.json` |
| Personal data | never, by construction | all of it |
| Automation | reusable workflows | scheduled jobs calling the kit |

Git history is permanent and public forks cannot be recalled. A `.gitignore` is a
convention, not a boundary: one `git add -A` on a bad day defeats it. Separating the
repos means the public one has no personal data to leak in the first place.

## Canary values

Give each major broker a slightly different benign variation of your details: a distinct
middle initial, a different apartment-number format, a per-broker email alias. Record the
mapping in `canaries.json` **in the private repo**.

When a variant resurfaces on a site you never contacted, you know exactly who resold you,
and your next request can say so. Publishing the map destroys the mechanism entirely.

## The guard

`optout guard` runs two independent layers:

1. **Local, precise.** Reads your real `profile.json` and looks for those exact values in
   the staged diff. Only works where the profile exists, i.e. your machine.
2. **Generic patterns.** SSN, phone, DOB and street-address shapes. Runs in CI, where your
   profile must never be present, and catches a contributor (or a future you) pasting
   something real into a test fixture.

The guard never prints a matched value, only the file, line, and profile field name, so
that guard output cannot itself become the leak.

Install it before your first commit:

```sh
cp hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

## What we deliberately do not send brokers

`render.identity_block` includes name, addresses, email, phone and birth *year*. It
excludes SSN, driver's licence number and full date of birth. A broker does not need
those to locate a listing, and several have been breached. If a broker insists on
identity documents, the default policy is to skip it rather than comply.

## Excluding a broker on purpose

Some people have a relationship with a broker that makes a statutory demand letter
a bad idea: you work there, your employer is a subsidiary, or they are a client.

Set that ledger entry's status to `skipped_employer_conflict`. It is terminal and
never escalates, and unlike `confirmed` it does not reopen if your data is later
relisted. The entry stays in the ledger so the gap in your coverage stays visible
rather than quietly disappearing.

```json
{ "slug": "example-broker", "status": "skipped_employer_conflict", "events": [] }
```

`optout draft --ledger ledger` skips anything already terminal, so an excluded
broker never gets a draft rendered for it by accident.

Keep the *reason* in your private repo. The public tool only needs to know that an
exclusion exists, not why.
