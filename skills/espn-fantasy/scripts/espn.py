#!/usr/bin/env python3
"""Read-only CLI over ESPN's undocumented fantasy football API (via the espn-api library).

Config comes from environment variables, optionally loaded from an env file:
  ESPN_LEAGUE_ID   required
  ESPN_YEAR        season (defaults to the current NFL season)
  ESPN_S2, ESPN_SWID   required for private leagues (browser cookies)

Usage:
  espn.py [--env-file PATH] [--json] <command> [options]

Commands:
  league                         settings, scoring type, roster slots, trade deadline
  standings                      records and points for/against
  roster [--team T | --all]      rosters with avg / projected / injury (default: your team)
  matchup [--week N] [--team T | --all]   box score for your matchup (or all)
  free-agents [--position P] [--size N]
  trend PLAYER [PLAYER ...]      week-by-week points for players
  trade-eval --give A,B --get C,D [--partner T] [--sidelined X,Y]
                                 best-lineup projected points before/after, both sides
  byes [--team T]                upcoming bye weeks for a roster (starters marked)
  activity [--size N]            recent league transactions

Teams can be matched by team name, owner name, or abbreviation (case-insensitive substring).
"""
import argparse
import datetime as dt
import json
import os
import sys

try:
    from espn_api.football import League
except ImportError:  # pragma: no cover
    sys.exit("espn-api is not installed. Run: pip install espn-api (add --break-system-packages if needed)")

UNAVAILABLE = {"OUT", "INJURY_RESERVE", "SUSPENSION", "IR"}
SLOT_ELIGIBLE = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "K": {"K"}, "D/ST": {"D/ST"},
    "RB/WR": {"RB", "WR"}, "WR/TE": {"WR", "TE"}, "RB/WR/TE": {"RB", "WR", "TE"},
    "OP": {"QB", "RB", "WR", "TE"},
}
FIXED_FIRST = ["QB", "RB", "WR", "TE", "K", "D/ST"]
BYES = {}        # NFL team abbrev -> bye week, filled by load_byes()
CUR_WEEK = 0
REG_WEEKS = 0


# ---------- config ----------

def load_env_file(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def default_season():
    today = dt.date.today()
    return today.year if today.month >= 3 else today.year - 1


def get_league():
    lid = os.environ.get("ESPN_LEAGUE_ID")
    if not lid:
        sys.exit("ESPN_LEAGUE_ID is not set. Provide an env file (--env-file) or environment variables.")
    year = int(os.environ.get("ESPN_YEAR") or default_season())
    s2, swid = os.environ.get("ESPN_S2"), os.environ.get("ESPN_SWID")
    try:
        if s2 and swid:
            return League(league_id=int(lid), year=year, espn_s2=s2, swid=swid)
        return League(league_id=int(lid), year=year)
    except Exception as e:  # surface the useful part
        msg = str(e)
        if "ProxyError" in msg or "403" in msg or "Tunnel" in msg:
            sys.exit("Network blocked reaching lm-api-reads.fantasy.espn.com (check the egress allowlist).\n" + msg[:300])
        if "401" in msg or "not authorized" in msg.lower():
            sys.exit("ESPN rejected the credentials (league is private or espn_s2/SWID expired).\n" + msg[:300])
        raise


# ---------- helpers ----------

def load_byes(L):
    global CUR_WEEK, REG_WEEKS
    CUR_WEEK, REG_WEEKS = L.current_week, L.settings.reg_season_count
    try:
        data = L.espn_request.get_pro_schedule()
        for t in data["settings"]["proTeams"]:
            if t.get("byeWeek"):
                BYES[t["abbrev"]] = t["byeWeek"]
    except Exception as e:  # byes are a nice-to-have; don't fail the command
        print(f"(could not load bye weeks: {str(e)[:120]})", file=sys.stderr)


def bye_label(nfl):
    wk = BYES.get(nfl)
    if not wk:
        return ""
    return f"W{wk} done" if wk < CUR_WEEK else f"W{wk}"


def owner_names(team):
    out = []
    for o in getattr(team, "owners", None) or []:
        if isinstance(o, dict):
            out.append(f"{o.get('firstName', '')} {o.get('lastName', '')}".strip() or o.get("displayName", ""))
        else:
            out.append(str(o))
    return out


def my_team(league):
    swid = (os.environ.get("ESPN_SWID") or "").strip().upper()
    if not swid:
        return None
    for t in league.teams:
        for o in getattr(t, "owners", None) or []:
            if isinstance(o, dict) and str(o.get("id", "")).upper() == swid:
                return t
    return None


def find_team(league, query):
    if not query:
        t = my_team(league)
        if not t:
            sys.exit("Could not identify your team from ESPN_SWID; pass --team.")
        return t
    q = query.lower()
    hits = [t for t in league.teams
            if q in t.team_name.lower() or q == str(getattr(t, "team_abbrev", "")).lower()
            or any(q in n.lower() for n in owner_names(t))]
    if len(hits) != 1:
        names = ", ".join(t.team_name for t in (hits or league.teams))
        sys.exit(f"Team '{query}' matched {len(hits)} teams. Options: {names}")
    return hits[0]


def find_player(roster, name):
    q = name.lower().strip()
    exact = [p for p in roster if p.name.lower() == q]
    hits = exact or [p for p in roster if q in p.name.lower()]
    if len(hits) != 1:
        sys.exit(f"Player '{name}' matched {len(hits)} on that roster: {[p.name for p in hits] or [p.name for p in roster]}")
    return hits[0]


def pinfo(p):
    return {
        "name": p.name, "pos": p.position, "nfl": p.proTeam,
        "avg": round(p.avg_points or 0, 1), "proj": round(p.projected_avg_points or 0, 1),
        "total": round(p.total_points or 0, 1), "slot": getattr(p, "lineupSlot", ""),
        "injury": getattr(p, "injuryStatus", ""), "owned_pct": round(getattr(p, "percent_owned", 0) or 0),
        "bye": bye_label(p.proTeam),
    }


def slot_counts(league):
    return {k: v for k, v in league.settings.position_slot_counts.items()
            if v and k not in ("BE", "IR", "")}


def best_lineup(roster, slots, key="proj", sidelined=()):
    """Greedy optimal for standard flex structures: fill dedicated slots, then flex/OP.
    `sidelined` = lowercase names to treat as unavailable (suspensions, exempt list, etc.)."""
    pool = [pinfo(p) for p in roster if getattr(p, "injuryStatus", "") not in UNAVAILABLE
            and not any(s in p.name.lower() for s in sidelined)]
    pool.sort(key=lambda x: -x[key])
    used, lineup = set(), []
    order = [s for s in FIXED_FIRST if s in slots] + [s for s in slots if s not in FIXED_FIRST]
    for slot in order:
        elig = SLOT_ELIGIBLE.get(slot)
        if not elig:
            continue
        for _ in range(slots[slot]):
            pick = next((p for p in pool if p["name"] not in used and p["pos"] in elig), None)
            if pick:
                used.add(pick["name"])
                lineup.append((slot, pick))
    return round(sum(p[key] for _, p in lineup), 1), lineup


def ms_to_date(ms):
    try:
        return dt.datetime.fromtimestamp(int(ms) / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return None


def table(rows, cols):
    if not rows:
        print("(none)")
        return
    w = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    print("  ".join(c.ljust(w[c]) for c in cols))
    for r in rows:
        print("  ".join(str(r.get(c, "")).ljust(w[c]) for c in cols))


# ---------- commands ----------

def cmd_league(L, a):
    s = L.settings
    rec = next((x["points"] for x in getattr(s, "scoring_format", []) if x.get("abbr") == "REC"), 0)
    data = {
        "name": s.name, "season": L.year, "teams": len(L.teams), "current_week": L.current_week,
        "scoring": {1.0: "full PPR", 0.5: "half PPR", 0: "standard"}.get(rec, f"{rec} per reception"),
        "roster_slots": slot_counts(L), "bench": s.position_slot_counts.get("BE", 0),
        "ir": s.position_slot_counts.get("IR", 0),
        "trade_deadline": ms_to_date(getattr(s, "trade_deadline", 0)),
        "regular_season_weeks": s.reg_season_count, "playoff_teams": s.playoff_team_count,
        "my_team": (my_team(L).team_name if my_team(L) else None),
    }
    return data


def cmd_standings(L, a):
    rows = []
    for t in sorted(L.teams, key=lambda t: t.standing):
        rows.append({"#": t.standing, "team": t.team_name, "owner": ", ".join(owner_names(t)),
                     "record": f"{t.wins}-{t.losses}-{t.ties}", "PF": round(t.points_for, 1),
                     "PA": round(t.points_against, 1)})
    return rows


def cmd_roster(L, a):
    teams = sorted(L.teams, key=lambda t: t.standing) if a.all else [find_team(L, a.team)]
    out = []
    for t in teams:
        players = sorted((pinfo(p) for p in t.roster), key=lambda x: (x["pos"], -x["avg"]))
        out.append({"team": t.team_name, "owner": ", ".join(owner_names(t)),
                    "record": f"{t.wins}-{t.losses}-{t.ties}", "players": players})
    return out


def cmd_matchup(L, a):
    week = a.week or L.current_week
    want = find_team(L, a.team).team_name if (a.team or not a.all) else None
    out = []
    for b in L.box_scores(week):
        if want and want not in (getattr(b.home_team, "team_name", ""), getattr(b.away_team, "team_name", "")):
            continue
        side = lambda team, score, proj, lineup: {
            "team": getattr(team, "team_name", "BYE"), "score": round(score or 0, 1),
            "projected": round(proj or 0, 1),
            "lineup": [{"slot": p.slot_position, "name": p.name, "pts": round(p.points or 0, 1),
                        "proj": round(p.projected_points or 0, 1)} for p in lineup
                       if p.slot_position not in ("BE", "IR")]}
        out.append({"week": week,
                    "home": side(b.home_team, b.home_score, b.home_projected, b.home_lineup),
                    "away": side(b.away_team, b.away_score, b.away_projected, b.away_lineup)})
    return out


def cmd_free_agents(L, a):
    fas = L.free_agents(size=a.size, position=a.position)
    return sorted((pinfo(p) for p in fas), key=lambda x: -x["proj"])


def cmd_trend(L, a):
    out = []
    for name in a.players:
        p = L.player_info(name=name)
        if not p:
            out.append({"name": name, "error": "not found"})
            continue
        weeks = {wk: round(v.get("points", 0), 1) for wk, v in sorted(p.stats.items())
                 if isinstance(wk, int) and wk > 0 and "points" in v}
        out.append({**pinfo(p), "weekly": weeks})
    return out


def cmd_trade_eval(L, a):
    me = find_team(L, a.me)
    give = [s.strip() for s in a.give.split(",") if s.strip()]
    get = [s.strip() for s in a.get.split(",") if s.strip()]
    give_p = [find_player(me.roster, n) for n in give]
    if a.partner:
        partner = find_team(L, a.partner)
    else:
        owners = {t.team_name: t for t in L.teams for p in t.roster if any(p.name.lower() == g.lower() or g.lower() in p.name.lower() for g in get)}
        if len(owners) != 1:
            sys.exit("Could not infer the trade partner; pass --partner.")
        partner = next(iter(owners.values()))
    get_p = [find_player(partner.roster, n) for n in get]
    slots = slot_counts(L)
    sidelined = [s.strip().lower() for s in (a.sidelined or "").split(",") if s.strip()]

    def side(team, out_p, in_p):
        before = list(team.roster)
        after = [p for p in before if p not in out_p] + list(in_p)
        res = {"team": team.team_name}
        for key in ("proj", "avg"):
            b, _ = best_lineup(before, slots, key, sidelined)
            af, lu = best_lineup(after, slots, key, sidelined)
            res[key] = {"before": b, "after": af, "delta": round(af - b, 1)}
            if key == "proj":
                res["lineup_after"] = [f"{s}: {p['name']} ({p['proj']})" for s, p in lu]
        res["bye_holes"] = {}
        for label, roster in (("before", before), ("after", after)):
            _, lu = best_lineup(roster, slots, "proj", sidelined)
            holes = {}
            for slot, pl in lu:
                wk = BYES.get(pl["nfl"])
                if wk and CUR_WEEK <= wk <= REG_WEEKS:
                    holes.setdefault(wk, []).append(pl["name"])
            res["bye_holes"][label] = dict(sorted(holes.items()))
        res["sends"] = [pinfo(p) for p in out_p]
        res["receives"] = [pinfo(p) for p in in_p]
        res["flagged"] = [p.name for p in in_p if getattr(p, "injuryStatus", "") not in ("ACTIVE", "NORMAL", "")]
        return res

    return {"note": "proj = ESPN rest-of-season projected avg; avg = season-to-date avg. "
                    "Unavailable players (OUT/IR/SUSPENSION) are excluded from lineups; "
                    "check news for anyone 'flagged'.",
            "you": side(me, give_p, get_p), "partner": side(partner, get_p, give_p)}


def cmd_byes(L, a):
    t = find_team(L, a.team)
    slots = slot_counts(L)
    _, lu = best_lineup(t.roster, slots, "proj")
    starters = {p["name"] for _, p in lu}
    weeks = {}
    for p in t.roster:
        wk = BYES.get(p.proTeam)
        if wk and CUR_WEEK <= wk <= REG_WEEKS:
            weeks.setdefault(wk, []).append(p.name + (" *" if p.name in starters else ""))
    done = sorted(p.name for p in t.roster if BYES.get(p.proTeam, 99) < CUR_WEEK)
    return {"team": t.team_name, "current_week": CUR_WEEK, "byes_done": done,
            "upcoming": {f"W{k}": v for k, v in sorted(weeks.items())},
            "note": "* = in current best projected lineup"}


def cmd_activity(L, a):
    out = []
    for act in L.recent_activity(size=a.size):
        when = ms_to_date(getattr(act, "date", 0))
        out.append({"date": when, "actions": [f"{getattr(t, 'team_name', t)} {action} {getattr(p, 'name', p)}"
                                               for t, action, p, *_ in act.actions]})
    return out


# ---------- printing ----------

def print_human(cmd, data):
    if cmd == "standings":
        table(data, ["#", "team", "owner", "record", "PF", "PA"])
    elif cmd == "roster":
        for t in data:
            print(f"\n== {t['team']} ({t['owner']}, {t['record']}) ==")
            table(t["players"], ["pos", "name", "nfl", "bye", "avg", "proj", "total", "slot", "injury", "owned_pct"])
    elif cmd == "free-agents":
        table(data, ["pos", "name", "nfl", "bye", "avg", "proj", "total", "injury", "owned_pct"])
    elif cmd == "matchup":
        for m in data:
            h, w = m["home"], m["away"]
            print(f"\nWeek {m['week']}: {h['team']} {h['score']} (proj {h['projected']})  vs  "
                  f"{w['team']} {w['score']} (proj {w['projected']})")
            if len(data) == 1:
                for s in (h, w):
                    print(f"  {s['team']}:")
                    for p in s["lineup"]:
                        print(f"    {p['slot']:9} {p['name']:26} {p['pts']:5}  proj {p['proj']}")
    elif cmd == "trend":
        for p in data:
            if "error" in p:
                print(f"{p['name']}: {p['error']}")
                continue
            wk = "  ".join(f"W{k}:{v}" for k, v in p["weekly"].items())
            print(f"{p['name']} ({p['pos']}, {p['nfl']}) avg {p['avg']} proj {p['proj']} inj {p['injury']}\n  {wk}")
    elif cmd == "trade-eval":
        print(data["note"])
        for k in ("you", "partner"):
            s = data[k]
            print(f"\n== {s['team']} ==")
            print("  sends:    " + ", ".join(f"{p['name']} ({p['pos']} avg {p['avg']}/proj {p['proj']}, bye {p['bye']})" for p in s["sends"]))
            print("  receives: " + ", ".join(f"{p['name']} ({p['pos']} avg {p['avg']}/proj {p['proj']}, bye {p['bye']}, {p['injury']})" for p in s["receives"]))
            for key in ("proj", "avg"):
                d = s[key]
                print(f"  best lineup by {key:4}: {d['before']} -> {d['after']}  ({d['delta']:+})")
            for lab in ("before", "after"):
                bh = s["bye_holes"][lab]
                txt = "; ".join(f"W{w}: {', '.join(n)}" for w, n in bh.items()) or "none left"
                print(f"  starter byes remaining ({lab}): {txt}")
            if s["flagged"]:
                print("  flagged (check news): " + ", ".join(s["flagged"]))
            print("  lineup after: " + "; ".join(s["lineup_after"]))
    else:
        print(json.dumps(data, indent=2, default=str))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("league")
    sub.add_parser("standings")
    r = sub.add_parser("roster"); r.add_argument("--team"); r.add_argument("--all", action="store_true")
    m = sub.add_parser("matchup"); m.add_argument("--week", type=int); m.add_argument("--team"); m.add_argument("--all", action="store_true")
    f = sub.add_parser("free-agents"); f.add_argument("--position"); f.add_argument("--size", type=int, default=25)
    t = sub.add_parser("trend"); t.add_argument("players", nargs="+")
    te = sub.add_parser("trade-eval"); te.add_argument("--give", required=True); te.add_argument("--get", required=True)
    te.add_argument("--partner"); te.add_argument("--me")
    te.add_argument("--sidelined", help="comma-separated players to treat as unavailable (e.g. suspended)")
    by = sub.add_parser("byes"); by.add_argument("--team")
    ac = sub.add_parser("activity"); ac.add_argument("--size", type=int, default=15)
    a = ap.parse_args()

    if a.env_file:
        load_env_file(a.env_file)
    L = get_league()
    load_byes(L)
    fn = {"league": cmd_league, "standings": cmd_standings, "roster": cmd_roster, "matchup": cmd_matchup,
          "free-agents": cmd_free_agents, "trend": cmd_trend, "trade-eval": cmd_trade_eval, "byes": cmd_byes,
          "activity": cmd_activity}[a.cmd]
    data = fn(L, a)
    if a.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print_human(a.cmd, data)


if __name__ == "__main__":
    main()
