# Attribution and licensing

## Why the broker data is not in this repo

Two upstream sources make this tool possible:

| Source | License |
| --- | --- |
| [Optery data-brokers directory](https://github.com/optery/optery-data-brokers-directory) (956 brokers) | CC BY-NC-SA 4.0, (c) Optery, Inc. |
| [Big-Ass Data Broker Opt-Out List](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List) (Yael Grauer) | CC BY-NC-SA 4.0 |

Both are **NonCommercial** and **ShareAlike**. Vendoring either into this repository
would impose those terms on everything built on top of it, which is not what someone
installing an MIT-licensed tool expects, and could put them in silent violation.

So `optout_kit/directory.py` fetches the Optery directory at runtime into a gitignored
`.cache/`. Each user obtains the data directly, under its own license. `optout_kit/data/broker-notes.json`
references broker *names* and priority tiers only; no descriptive content is copied.

Please credit both projects if you build on this, and consider contributing corrections
upstream where they belong.

## What is ours

`optout_kit/data/state-laws.json` and `optout_kit/data/broker-notes.json` are original work by optout-kit
contributors, released CC0. The code is MIT.
