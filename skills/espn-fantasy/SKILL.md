---
name: espn-fantasy
description: Reads a user's ESPN fantasy football league (standings, rosters, matchups, free agents, player trends, transactions) and evaluates trades with best-lineup math for both sides. Use when the user asks about their ESPN fantasy league, trade ideas or offers, whether a trade is fair, who to start or sit, waiver pickups, matchups, or how a player has been trending.
author: Kyle Mahler
---

# ESPN Fantasy Football

ESPN has no public fantasy API. `scripts/espn.py` (in this skill's directory) wraps the undocumented
`lm-api-reads.fantasy.espn.com` endpoints through the `espn-api` Python library. It is **read-only**:
it cannot send trades, set lineups or make waiver claims. Say so if the user asks for any of those.

## 1. Load config

**Recommended setup:** run this skill in Cowork with a brand-new folder on your computer
dedicated to it (e.g. `~/espn-fantasy`). The skill saves `espn.env` there, so future
sessions reuse it instead of grabbing cookies again.

Look for an env file in this order:
1. An `espn.env` in the working directory, or one already in the scratchpad this session.
2. A connected folder containing `espn.env`. Copy it into the scratchpad (`chmod 600`).

If none is found, offer the user two ways to connect:
- **Grab it with Claude in Chrome** (if available): the user logs in to fantasy.espn.com in
  Chrome and keeps the window visible to click Allow. Confirm the page doesn't show "Log In"
  (logged-out visitors get an anonymous SWID), then read `espn_s2` and `SWID` from
  `document.cookie` and list their leagues from the `leagueId` links on the page.
- **Enter values manually**: walk them through DevTools → Application → Cookies.

Save the values to `espn.env` (in the connected folder when there is one). Write them as
`ESPN_S2`, `ESPN_SWID` and `ESPN_LEAGUES`, using `espn.env.example` at the plugin root
(`<skill_dir>/../../espn.env.example`) as the template. Keep the curly braces on `ESPN_SWID`:
without them ESPN rejects the cookie and the script can't find the user's team. Never echo
cookie values in chat, memory, or summaries.

In Cowork with no folder connected, suggest the user create a new, empty folder just for this
skill and connect it, so `espn.env` persists between sessions. Don't save it into a folder that
holds other projects or a git repo.

**Multiple leagues:** the cookies are account-wide, so one `espn.env` covers every league.
Store all of the user's leagues as `ESPN_LEAGUES=Name:id,Name:id`. If there's more than one,
ask which league to use at the start of each session.

## 2. Run the script

Install the dependency once per session if it's missing: `pip install -q -r <skill_dir>/scripts/requirements.txt`.
Add `--break-system-packages` only if pip refuses because the Python is externally managed (common in
cloud sandboxes).

```
python3 <skill_dir>/scripts/espn.py --env-file <env> [--league NAME_OR_ID] <command> [--json]
```

Use `python` instead of `python3` on Windows. Pass `--league` (a name from `ESPN_LEAGUES` or a
numeric ID) whenever the env file lists more than one league.

| Command | Use for |
|---|---|
| `league` | Scoring type (PPR etc.), roster slots, bench/IR counts, trade deadline, playoff format, which team is the user's |
| `standings` | Records, points for and against |
| `roster [--team T \| --all]` | Rosters with season avg, ESPN projected avg, injury tag, % owned (default: the user's team) |
| `matchup [--week N] [--team T \| --all]` | This week's box score and lineups (default: the user's matchup) |
| `free-agents [--position RB] [--size N]` | Waiver options sorted by projection |
| `trend "Player A" "Player B"` | Week-by-week points: is the average driven by one big game? |
| `trade-eval --give "A,B" --get "C,D" [--partner T]` | Best lineup before and after for **both** teams, by projection and by season avg |
| `byes [--team T]` | Which byes are done and which weeks are still coming, starters marked |
| `activity [--size N]` | Recent adds, drops and trades |

Teams match on team name, owner name, or abbreviation. The user's team is identified from `ESPN_SWID`.
Run `league` first in a new session so the advice fits the scoring and roster format.

If the script reports the network is blocked, `lm-api-reads.fantasy.espn.com` is not on the egress
allowlist. Tell the user it has to be added; don't try to get around the block.

## 3. Evaluating trades

- Run `trade-eval` and report the projected-points-per-week change for **both** sides. Pass
  `--sidelined "Name"` for any player whose news (section 4) says they won't play soon, such as a suspension,
  the exempt list, or a long injury ESPN hasn't tagged. Otherwise ESPN's projection counts them as a starter
  and the before/after numbers are wrong. A trade the other
  manager loses on paper needs a pitch built around their needs, not around the math.
- Compare **season avg vs ESPN projected avg**. A large positive gap (avg well above proj) is a sell-high
  signal; the reverse is a buy-low signal. Check `trend` to see whether the average comes from one spike.
- Look for partners whose roster complements the user's: surplus at the position the user needs, and
  thin or injured at the position the user is giving up. Check every roster (`roster --all`).
- Weigh lineup impact over raw player value. A bench player who never starts adds nothing weekly.
- **Always factor in bye weeks.** Every roster/trade output shows each player's bye (`W5 done` = already
  taken). A player whose bye is done is a starter for every remaining week, which makes him worth more for
  the rest of the season than a similar player whose bye is still ahead. `trade-eval` lists the remaining
  weeks where each side's starters are on bye, before and after. Point out stacked bye weeks (several
  starters out the same week), especially for the other manager's team, and byes falling in the final
  regular-season weeks.
- Treat a long-term stash (a player who's suspended or injured but expected back) as a playoff asset. Judge
  it by when he's likely to return relative to the playoffs, not by his weekly points now.
- Mention the trade deadline from `league` when it's relevant.

## 4. Injury tags are not news

ESPN's `injuryStatus` lags and doesn't capture everything. A player tagged `DAY_TO_DAY` with zero points
may be suspended or on the Commissioner's Exempt List. Before recommending a move involving any player
who is not `ACTIVE`, or who has a zero or very low total, **search the web for current news**. Report
the actual situation and timeline with sources. A player on bye shows up benched with normal stats;
confirm a bye before calling a benching suspicious.

## 5. Answer style

Lead with the recommendation, then the numbers that support it (a small table works well), then risks.
Keep it conversational. Cite web sources for any news.
