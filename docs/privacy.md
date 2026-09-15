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

## Canary addresses

Removal is not permanent. Brokers re-acquire from each other, so a few months
out the useful question is not "am I listed again" but "who leaked me".

Set `canary_email_base` in your profile and each request discloses a unique
tagged address:

```json
{ "emails": ["you@gmail.com"], "canary_email_base": "you@gmail.com" }
```

Spokeo is told `you+spokeo@gmail.com`, Acxiom `you+acxiom@gmail.com`. All deliver
to the same inbox. When mail arrives at a tag you gave to exactly one broker,
that broker is the source:

```sh
$ optout trace you+spokeo@gmail.com
Issued to: Spokeo  (slug spokeo)
  status: confirmed
  This broker confirmed deletion, yet the address is receiving mail.
  Mark it relisted to trigger a refile citing that confirmation:
    optout mark relisted spokeo
```

The tag is deterministic, so it reverses without a lookup table and there is
nothing to keep in sync.

**The canary supplements your real address, it does not replace it.** A broker
searches its records by the address it already holds; substituting the tagged
one would reduce the chance of matching your record at all, trading worse
deletion for better detection.

**The tradeoff:** this hands each broker one extra data point. It is an alias of
an address they already have, and it is the only reliable way to attribute a
later leak, but it is a real disclosure rather than a free win.

**When "+" addressing is rejected.** Some brokers strip or refuse tagged
addresses in web forms. Pin an explicit alternative in `canaries.json` (private,
gitignored) rather than losing the canary for that broker:

```json
{ "brokers": { "spokeo": { "email_alias": "distinct-alias@yourdomain.com" } } }
```

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
