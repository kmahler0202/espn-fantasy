# espn-fantasy

A Claude plugin that reads your ESPN fantasy football league and helps with trades, start/sit and waiver decisions.

ESPN has no public fantasy API. This uses the same undocumented JSON endpoints the ESPN web app calls, through the [`espn-api`](https://github.com/cwendt94/espn-api) Python library. It's **read-only**: it can't send trades or set lineups, and it may break if ESPN changes its API.

## What it does

- Standings, rosters, matchups, free agents, recent transactions
- Week-by-week player trends and bye weeks (done vs. upcoming) on every roster and trade
- `trade-eval`: best-lineup projected points before and after a trade, for **both** teams
- Checks the news before advising on any player who isn't fully active (ESPN's injury tags miss suspensions and the exempt list)

## Install

**Claude Code**

```
/plugin marketplace add kmahler0202/espn-fantasy
/plugin install espn-fantasy@espn-fantasy
```

**Claude desktop (Cowork)**: click **Customize** in the sidebar → **Plugins** → **Add marketplace**, enter `kmahler0202/espn-fantasy`, then find the plugin under **Discover** and click **Install**.
Or download `espn-fantasy.plugin` from the [latest release](https://github.com/kmahler0202/espn-fantasy/releases/latest) and upload it from the same Plugins page.

On a Team or Enterprise plan, your org admin may need to allow user-added plugins.

You need Python 3.9+ available to Claude. The skill installs `espn-api` itself the first time it runs.

## Setup

1. Install the plugin (above).
2. Copy `espn.env.example` to `espn.env` and fill it in:
   - **League ID**: the number after `leagueId=` in your league's URL.
   - **Season**: e.g. `2026`.
   - **espn_s2 / SWID** (private leagues): Chrome → fantasy.espn.com (logged in) → F12 → Application → Cookies → `https://fantasy.espn.com`. Keep the braces on SWID.
3. Put `espn.env` in your working folder (Claude Code) or a folder you connect to Claude (desktop/Cowork), or just give Claude the values when it asks.
4. If your Claude org restricts network access, `lm-api-reads.fantasy.espn.com` must be on the egress allowlist.

**Never commit `espn.env`.** `espn_s2` is effectively a login token for your ESPN account. It's gitignored here. Logging out of ESPN invalidates it.

## Running the script directly

```bash
pip install -r skills/espn-fantasy/scripts/requirements.txt
python3 skills/espn-fantasy/scripts/espn.py --env-file espn.env standings
python3 skills/espn-fantasy/scripts/espn.py --env-file espn.env trade-eval --give "Christian Watson,Romeo Doubs" --get "Kenneth Walker III,Josh Jacobs"
```

On Windows, use `python` instead of `python3`. Run with `--help` for all commands; add `--json` for machine-readable output.

## License

[MIT](LICENSE). Not affiliated with or endorsed by ESPN.
