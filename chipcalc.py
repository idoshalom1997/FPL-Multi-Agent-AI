"""
What each chip is worth, in points, gameweek by gameweek.

Ido asked the right question about the chip plan: *how would they know when it
is profitable?* Without an answer the staff would argue chips from taste - "the
fixtures look nice" - which is how four chips reach the GW19 deadline unplayed.

This turns each chip into a number. Not a verdict: a number, with its own error
bars stated, that the staff then argue about against the rivals.

    python chipcalc.py             the next 8 gameweeks
    python chipcalc.py 15          out to the GW19 chip deadline
    python chipcalc.py --detail 7  the bench and captain picture for one week
    python chipcalc.py targets 6   best Triple Captain targets in the whole league

How each chip is valued
-----------------------
The principle is the same for all four: **what does the chip add that you would
not have got anyway?**

- **Bench Boost** = the points your four substitutes are expected to score. They
  normally score you nothing, so the whole of it is gain. A double gameweek
  roughly doubles it; a blank for a bench player zeroes him.
- **Triple Captain** = one extra copy of your captain's score. You already
  collect double, so the chip adds 1x, not 3x - a distinction worth being clear
  about, because it halves what people assume the chip is worth.
- **Free Hit** = what a free one-week squad would score minus what yours would.
  Only the losing side is computed here: how many of your fifteen blank, and the
  points that blank costs you. That floor is the honest part; the upside depends
  on a replacement team nobody has picked yet.
- **Wildcard** = not a one-week number at all. It is worth playing when fixing
  the squad through transfers would cost more in hits than the rebuild gains, so
  what is reported is the cost of the alternative: changes needed x -4.

Where the numbers come from, and how much to trust them
-------------------------------------------------------
For the **upcoming** gameweek, each player's `ep_next` - FPL's own expected
points. For **later** gameweeks there is no published forecast, so this uses
points-per-game scaled by how many fixtures that player's club actually has that
week, and adjusted for fixture difficulty.

Both are crude. `ep_next` is close to a form average and knows nothing about
rotation; points-per-game rewards whoever has played most. **Treat every number
here as an order of magnitude, not a projection** - the difference between a 6
and a 20 is real and decision-shaped, the difference between a 14 and a 16 is
noise. The tool says so in its own output rather than leaving it to be forgotten.
"""
from __future__ import annotations

import config
import json
import sys
from pathlib import Path

import fpl
import health

ROOT = Path(__file__).resolve().parent
TEAM_FILE = ROOT / "current_team.json"

TEAM_ID = config.ENTRY_ID
CHIP_DEADLINE_GW = 19

# Rules of thumb from how these chips actually pay out - a Bench Boost returning
# 20+ is a good one, under 10 is a wasted chip. They give a number a sense of
# scale, and nothing more.
#
# They are NOT a decision rule, and reading them as one is the trap. Those bars
# assume a double gameweek. There may not be a single double or blank before
# GW19, in which case every week scores "poor" against them - and a staff that
# waits for a "good" week reaches the deadline with four unplayed chips worth
# exactly nothing. **A chip not played by GW19 scores zero.** So the real
# question is never "is this week good?" but "is this the best week left, and
# how many chances remain?" - which is what the ranking below answers.
GOOD = {"bboost": 18, "3xc": 15, "freehit": 15}

# For the league-wide view only. A player with three appearances at 9.0 points a
# game is not a 9.0 player, and a ranking built on raw points-per-game fills up
# with whoever had one good afternoon. Pulling small samples back toward the
# average for their position is what makes the list worth reading; it is a
# sanity guard, not a model.
SHRINK_GAMES = 5
MIN_MINUTES = 200

# Players kept out of the league-wide rankings. Empty since 23 Oct 2026, when
# Ido lifted his ban on Haaland: a captain ranking with the league's most-owned
# captain cut out of it was a large part of why the staff misread the market.
EXCLUDED_NAMES: set[str] = set()

_PRIORS: dict[str, float] = {}


def difficulty_factor(fdr: int) -> float:
    """A soft adjustment. FDR is coarse, so this stays gentle on purpose."""
    return {1: 1.20, 2: 1.10, 3: 1.00, 4: 0.90, 5: 0.80}.get(fdr, 1.0)


def positional_prior(pos: str) -> float:
    """Average points per game for a regular starter in this position."""
    if not _PRIORS:
        buckets: dict[str, list[float]] = {}
        for p in fpl.players().values():
            if p["minutes"] < 450:
                continue
            buckets.setdefault(fpl.POSITIONS[p["element_type"]], []).append(
                float(p["points_per_game"] or 0))
        for k, v in buckets.items():
            _PRIORS[k] = sum(v) / len(v) if v else 2.5
    return _PRIORS.get(pos, 2.5)


def reliable_ppg(p: dict) -> float:
    ppg = float(p["points_per_game"] or 0)
    games = p["minutes"] / 90.0
    prior = positional_prior(fpl.POSITIONS[p["element_type"]])
    return (ppg * games + prior * SHRINK_GAMES) / (games + SHRINK_GAMES)


def captain_targets(gw: int, upcoming: int, limit: int = 6) -> list[dict]:
    """
    The best Triple Captain targets **in the whole league**, not just his squad.

    This is the half `chipcalc.py` was missing. Everything else here looks only
    at the fifteen Ido owns, which is right for a Bench Boost - it is his bench
    or nothing - but wrong for a Triple Captain, where the question is whether
    any player anywhere is worth building a chip week around. The same list
    doubles as the shortlist for a Wildcard or Free Hit.

    A Triple Captain wants a high ceiling against a soft opponent, which is
    Ido's own rule: "a very good player against a very poor team".
    """
    tm = fpl.teams()
    fx: dict[int, list[dict]] = {}
    for f in fpl.fixtures(gw):
        fx.setdefault(f["team_h"], []).append(
            {"opp": f["team_a"], "home": True, "fdr": f["team_h_difficulty"]})
        fx.setdefault(f["team_a"], []).append(
            {"opp": f["team_h"], "home": False, "fdr": f["team_a_difficulty"]})

    rows = []
    for p in fpl.players().values():
        if fpl.player_name(p).lower() in EXCLUDED_NAMES:
            continue                       # standing rule, see EXCLUDED_NAMES
        if fpl.POSITIONS[p["element_type"]] not in ("MID", "FWD"):
            continue                       # captains come from the attack
        if p["status"] in ("i", "s", "u") or p["minutes"] < MIN_MINUTES:
            continue
        chance = p.get("chance_of_playing_next_round")
        if chance is not None and chance < 75:
            continue
        games = fx.get(p["team"], [])
        if not games:
            continue                       # blank
        base = float(p["ep_next"] or 0) if gw == upcoming else reliable_ppg(p)
        xp = sum(base * difficulty_factor(g["fdr"]) for g in games)
        rows.append({
            "name": fpl.player_name(p),
            "pos": fpl.POSITIONS[p["element_type"]],
            "club": tm[p["team"]]["short_name"],
            "price": p["now_cost"] / 10,
            "owned": float(p["selected_by_percent"] or 0),
            "xp": xp,
            "games": len(games),
            "opp": " + ".join(
                (tm[g["opp"]]["short_name"].upper() if g["home"]
                 else tm[g["opp"]]["short_name"].lower()) + f"({g['fdr']})"
                for g in games),
        })
    rows.sort(key=lambda r: -r["xp"])
    return rows[:limit]


def squad_rows(gw: int) -> tuple[list[dict], str]:
    """
    His fifteen, as current as they can be made, with the bench split he is
    actually using.

    Getting this wrong quietly ruins every Bench Boost number, which is what
    the first version did: it read `picks()` for the last published gameweek and
    never opened `current_team.json`, so a transfer made this week was invisible
    and the bench order was whatever it had been at last week's deadline. Ido
    asked whether the chip numbers track his team week to week, and they did not.

    Three sources, in order of how current they are:

    1. `current_team.json`, when it is marked for the upcoming gameweek. This is
       the only place his real XI, bench ORDER and captain can come from - FPL
       does not publish picks before a deadline.
    2. Transfers, which *are* public before a deadline, applied on top of the
       last published squad. This keeps the fifteen right even when he has not
       sent his team sheet.
    3. The last published picks, as a floor.

    The second return value names which was used, so a number computed from
    stale data is never presented as current.
    """
    pl = fpl.players()
    tm = fpl.teams()
    by_name = {fpl.player_name(x): x for x in pl.values()}

    nxt = fpl.next_event()
    upcoming = nxt["id"] if nxt else gw

    def make(p: dict, slot: int) -> dict:
        return {
            "id": p["id"],
            "name": fpl.player_name(p),
            "pos": fpl.POSITIONS[p["element_type"]],
            "team": p["team"],
            "short": tm[p["team"]]["short_name"],
            "slot": slot,
            "bench": slot > 11,
            "ep_next": float(p["ep_next"] or 0),
            "ppg": float(p["points_per_game"] or 0),
            "status": p["status"],
        }

    # 1. His own team sheet, if it is for the week being planned.
    if TEAM_FILE.exists():
        try:
            cfg = json.loads(TEAM_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cfg = {}
        if cfg.get("event") == upcoming:
            names = list(cfg.get("starting_xi", [])) + list(cfg.get("bench", []))
            if len(names) == 15 and all(n in by_name for n in names):
                rows = [make(by_name[n], i + 1) for i, n in enumerate(names)]
                return rows, f"your team sheet for GW{upcoming}"

    # 2. Last published squad with this week's transfers applied.
    try:
        owned, moves = health.expected_fifteen(upcoming)
    except fpl.FPLError:
        owned, moves = set(), []

    pk = fpl.picks(TEAM_ID, fpl.current_event()["id"])
    rows = [make(pl[i["element"]], i["position"]) for i in pk["picks"]]
    published = {r["name"] for r in rows}

    if owned and owned != published:
        # Put anyone transferred in onto the bench: his real slot is unknown
        # until he says, and guessing it into the XI would inflate the Bench
        # Boost number with a player who may not even be on the bench.
        rows = [r for r in rows if r["name"] in owned]
        slot = 12
        for name in sorted(owned - published):
            rows.append(make(by_name[name], slot))
            slot += 1
        for i, r in enumerate(sorted(rows, key=lambda x: x["slot"])):
            r["slot"] = i + 1
            r["bench"] = r["slot"] > 11
        note = (f"last published XI plus this week's transfers "
                f"({', '.join(moves)})" if moves else
                "last published XI plus this week's transfers")
        return sorted(rows, key=lambda r: r["slot"]), note

    # 3. Nothing newer available.
    return sorted(rows, key=lambda r: r["slot"]),         f"your GW{fpl.current_event()['id']} team - he has not sent a newer one"


def team_fixtures(gw: int) -> dict[int, list[int]]:
    """club id -> the FDRs it faces this gameweek. Empty list means a blank."""
    out: dict[int, list[int]] = {}
    for f in fpl.fixtures(gw):
        out.setdefault(f["team_h"], []).append(f["team_h_difficulty"])
        out.setdefault(f["team_a"], []).append(f["team_a_difficulty"])
    return out


def expected(row: dict, gw: int, upcoming_gw: int, fixtures: dict) -> float:
    """
    Points this player is expected to score in this gameweek.

    The upcoming week uses FPL's own forecast. Later weeks have none, so
    points-per-game stands in, scaled by the number of fixtures actually played
    and nudged by difficulty.
    """
    fdrs = fixtures.get(row["team"], [])
    if not fdrs:
        return 0.0                       # blank: no fixture, no points
    if row["status"] in ("i", "s", "u"):
        return 0.0                       # injured, suspended or unavailable
    if gw == upcoming_gw:
        base = row["ep_next"]
        # ep_next already covers one fixture; a double adds another.
        return base * (1 + 0.85 * (len(fdrs) - 1))
    return sum(row["ppg"] * difficulty_factor(f) for f in fdrs)


def assess(gw: int, rows: list[dict], upcoming_gw: int) -> dict:
    fx = team_fixtures(gw)
    for r in rows:
        r["xp"] = expected(r, gw, upcoming_gw, fx)
        r["games"] = len(fx.get(r["team"], []))

    bench = [r for r in rows if r["bench"]]
    xi = [r for r in rows if not r["bench"]]

    doubles = [r["short"] for r in rows if r["games"] > 1]
    blanks = [r["short"] for r in rows if r["games"] == 0]

    cap = max(xi, key=lambda r: r["xp"]) if xi else None
    blanking = [r for r in rows if r["games"] == 0]

    return {
        "gw": gw,
        "bboost": sum(r["xp"] for r in bench),
        "3xc": cap["xp"] if cap else 0.0,
        "captain": cap["name"] if cap else "-",
        "freehit_floor": sum(r["ppg"] for r in blanking if not r["bench"]),
        "blank_count": len(blanking),
        "doubles": sorted(set(doubles)),
        "blanks": sorted(set(blanks)),
        "bench": bench,
        "xi": xi,
    }


def flag(kind: str, value: float) -> str:
    good = GOOD[kind]
    if value >= good:
        return "GOOD"
    if value >= good * 0.65:
        return "ok"
    return "poor"


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    if argv and argv[0] == "targets":
        horizon = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 6
        nxt = fpl.next_event()
        if not nxt:
            print("No upcoming gameweek.")
            return 1
        up = nxt["id"]
        mine = {r["name"] for r in squad_rows(up)[0]}
        print("BEST TRIPLE CAPTAIN TARGETS - the whole league, not just your squad")
        print("A good player against a poor team. * = you already own him.\n")
        for gw in range(up, min(up + horizon, 39)):
            print(f"GW{gw}")
            for r in captain_targets(gw, up):
                own = "*" if r["name"] in mine else " "
                dbl = "  DOUBLE" if r["games"] > 1 else ""
                print(f"  {own} {r['name']:<18}{r['club']:<5}{r['price']:>5.1f}m"
                      f"{r['xp']:>7.1f} xP  vs {r['opp']:<16}{r['owned']:>5.1f}%{dbl}")
            print()
        print("UPPERCASE opponent = home, lowercase = away, (n) = difficulty 1-5.")
        print("Players Ido has ruled out are excluded and are not missing by")
        print("accident - do not raise them as an oversight.")
        print("A Triple Captain adds ONE extra copy of the score, not three.")
        print("Later gameweeks use points-per-game shrunk toward the positional")
        print("average, so a hot start does not masquerade as a captain pick.")
        return 0

    detail_gw = None
    if "--detail" in argv:
        i = argv.index("--detail")
        detail_gw = int(argv[i + 1]) if len(argv) > i + 1 else None
        argv = argv[:i] + argv[i + 2:]
    horizon = int(argv[0]) if argv and argv[0].isdigit() else 8

    nxt = fpl.next_event()
    if not nxt:
        print("No upcoming gameweek.")
        return 1
    upcoming = nxt["id"]
    rows, source = squad_rows(upcoming)

    sq = fpl.squad(TEAM_ID)
    left = sq["chips_available"]
    gws = list(range(upcoming, min(upcoming + horizon, 39)))

    if detail_gw:
        a = assess(detail_gw, rows, upcoming)
        print(f"GW{detail_gw} in detail\n")
        print("  BENCH (what a Bench Boost would collect)")
        for r in sorted(a["bench"], key=lambda r: r["slot"]):
            note = "  BLANK" if r["games"] == 0 else ("  DOUBLE" if r["games"] > 1 else "")
            print(f"    {r['pos']:<4}{r['name']:<20}{r['short']:<5}{r['xp']:>6.1f}{note}")
        print(f"    {'':29}{a['bboost']:>6.1f}  total\n")
        print("  BEST CAPTAIN (a Triple Captain adds one more copy of this)")
        print(f"    {a['captain']}  +{a['3xc']:.1f}")
        return 0

    print(f"CHIP VALUE, GW{gws[0]}-GW{gws[-1]}     chips left: "
          f"{', '.join(left) or 'none'}")
    print(f"Squad read from: {source}")
    print(f"First-set chips expire at the GW{CHIP_DEADLINE_GW} deadline. "
          "One chip per gameweek.\n")
    print(f"{'GW':<4}{'BenchBoost':>12}{'TripleCap':>12}  {'captain':<16}"
          f"{'doubles':<14}{'blanks'}")
    print("(#1 = best week in this range for that chip, #2 second best, etc.)")
    print("-" * 78)

    scored = [(gw, assess(gw, rows, upcoming)) for gw in gws]

    # Rank the weeks against each other, not only against an absolute bar. When
    # no week clears the bar - which is the normal case without doubles - the
    # ranking is the only thing that distinguishes them, and it is what stops
    # the answer being "never".
    rank = {}
    for k in ("bboost", "3xc"):
        order = sorted(scored, key=lambda t: -t[1][k])
        for i, (gw, _) in enumerate(order[:3], 1):
            rank.setdefault(gw, {})[k] = i

    best = {"bboost": (0, 0.0), "3xc": (0, 0.0)}
    for gw, a in scored:
        for k in ("bboost", "3xc"):
            if a[k] > best[k][1]:
                best[k] = (gw, a[k])
        r = rank.get(gw, {})
        bb = f"#{r['bboost']}" if "bboost" in r else "  "
        tc = f"#{r['3xc']}" if "3xc" in r else "  "
        mark = "  <- chip deadline" if gw == CHIP_DEADLINE_GW else ""
        print(f"{gw:<4}{a['bboost']:>8.1f} {bb:<4}"
              f"{a['3xc']:>8.1f} {tc:<4}  {a['captain']:<16}"
              f"{','.join(a['doubles'])[:13]:<14}{','.join(a['blanks'])[:12]}{mark}")

    print()
    print(f"  Best Bench Boost week in range : GW{best['bboost'][0]} "
          f"({best['bboost'][1]:.1f} pts off your bench)")
    print(f"  Best Triple Captain week       : GW{best['3xc'][0]} "
          f"(+{best['3xc'][1]:.1f} on top of the usual double)")
    chips_left = len([c for c in left if c in ("bboost", "3xc", "freehit", "wildcard")])
    weeks_left = max(0, CHIP_DEADLINE_GW - gws[0] + 1)
    print()
    if chips_left:
        print(f"  {chips_left} chip(s) unplayed and {weeks_left} gameweek(s) left "
              f"before the GW{CHIP_DEADLINE_GW} deadline.")
        if not any(a["doubles"] or a["blanks"] for _, a in scored):
            print("  NO double or blank gameweek anywhere in this range. There may")
            print("  never be one before the deadline - they are created by cup")
            print("  progress and postponements, and are not owed to anyone. Do not")
            print("  wait for a week that clears the usual bar; pick the best week")
            print("  available and commit. A chip unplayed at GW19 scores zero,")
            print("  which is worse than any week in the table above.")
        if chips_left > weeks_left:
            print("  MORE CHIPS THAN GAMEWEEKS - one will be lost. Say so plainly.")
    print()
    print("  Read these as orders of magnitude, not projections. The upcoming")
    print("  gameweek uses FPL's own expected points; later weeks use points per")
    print("  game scaled by fixtures, which knows nothing about rotation or")
    print("  injuries that have not happened yet. A 6 versus a 20 is a real")
    print("  difference; a 14 versus a 16 is noise.")
    print()
    print("  And none of it settles anything on its own: in a four-manager league")
    print("  a chip is only worth playing when it moves the gap. Check what Rookie mistakes,")
    print("  Nott'm Random Forest and Wei & Dudley have left before committing - see chips.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
