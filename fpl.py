"""
FPL data layer.

Every agent in this project reads the game through this module, so that they all
see one consistent snapshot rather than each fetching its own and disagreeing.

Responses are cached on disk under data/. Static-ish endpoints are reused for a
few minutes; a run right before a deadline should call refresh() first so that
price changes and injury news are current.

CLI:
    python fpl.py status              current/next gameweek and deadline
    python fpl.py refresh             force re-download of the core endpoints
    python fpl.py squad <team_id>     your current squad, value and chips
    python fpl.py league              live mini-league standings and the gaps
    python fpl.py market              what the world is buying for the NEXT deadline
    python fpl.py ticker [n]          FPL's own 1-5 fixture rating, next n gameweeks
    python fpl.py strength            every team's real attack and defence, ranked
    python fpl.py matchups [team_id]  each of the fifteen against the opponent's strength
    python fpl.py player <name>       look up a player by name
"""
from __future__ import annotations

import config
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE = "https://fantasy.premierleague.com/api"
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

# The FPL API rejects requests without a browser-ish user agent.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

POSITIONS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

# How long a cached copy stays usable, in seconds.
TTL = {
    "bootstrap-static": 600,
    "fixtures": 600,
    "default": 300,
}


class FPLError(RuntimeError):
    pass


def _cache_path(key: str) -> Path:
    # Windows rejects ? = & in filenames, which query-string endpoints contain.
    safe = key
    for ch in '/?=&':
        safe = safe.replace(ch, "_")
    return DATA / f"{safe}.json"


def _ttl_for(key: str) -> int:
    for prefix, seconds in TTL.items():
        if key.startswith(prefix):
            return seconds
    return TTL["default"]


def get(endpoint: str, *, force: bool = False) -> Any:
    """Fetch an API endpoint, using the disk cache when it is still fresh."""
    key = endpoint.strip("/")
    path = _cache_path(key)

    if not force and path.exists():
        age = time.time() - path.stat().st_mtime
        if age < _ttl_for(key):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass  # corrupt cache, fall through and refetch

    # The API wants a trailing slash on paths, but not after a query string.
    if "?" in key:
        path_part, query = key.split("?", 1)
        url = f"{BASE}/{path_part}/?{query}"
    else:
        url = f"{BASE}/{key}/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as exc:
        # Fall back to a stale cache rather than failing outright - stale data
        # beats no data when a deadline is minutes away.
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        raise FPLError(f"Could not reach {url}: {exc}") from exc

    if resp.status_code == 404:
        raise FPLError(f"Not found: {url} (is the ID correct?)")
    if resp.status_code != 200:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        raise FPLError(f"{url} returned HTTP {resp.status_code}")

    payload = resp.json()
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def refresh() -> None:
    """Force a re-download of the endpoints that move during a gameweek."""
    get("bootstrap-static", force=True)
    get("fixtures", force=True)


# --------------------------------------------------------------- game state

def bootstrap() -> dict:
    return get("bootstrap-static")


def events() -> list[dict]:
    return bootstrap()["events"]


def current_event() -> dict | None:
    return next((e for e in events() if e.get("is_current")), None)


def next_event() -> dict | None:
    return next((e for e in events() if e.get("is_next")), None)


def deadline() -> tuple[dict | None, float | None]:
    """The next deadline and how many hours away it is."""
    ev = next_event()
    if not ev:
        return None, None
    dt = datetime.fromisoformat(ev["deadline_time"].replace("Z", "+00:00"))
    hours = (dt - datetime.now(timezone.utc)).total_seconds() / 3600
    return ev, hours


def teams() -> dict[int, dict]:
    return {t["id"]: t for t in bootstrap()["teams"]}


def players() -> dict[int, dict]:
    return {p["id"]: p for p in bootstrap()["elements"]}


def player_name(p: dict) -> str:
    return p.get("web_name") or f"{p.get('first_name','')} {p.get('second_name','')}".strip()


def find_players(needle: str) -> list[dict]:
    """Case-insensitive substring search across first, second and web names."""
    n = needle.lower()
    out = []
    for p in bootstrap()["elements"]:
        haystack = " ".join([
            p.get("web_name", ""), p.get("first_name", ""), p.get("second_name", "")
        ]).lower()
        if n in haystack:
            out.append(p)
    return out


def fixtures(event_id: int | None = None) -> list[dict]:
    data = get("fixtures")
    if event_id is None:
        return data
    return [f for f in data if f.get("event") == event_id]


def ticker(start: int | None = None, horizon: int = 6) -> list[dict]:
    """
    Fixture difficulty for every team over the next `horizon` gameweeks.

    This is the backbone of season-long planning: it is what tells you when a
    team's run turns, which is usually a better reason to buy a player than
    last week's haul. Doubles and blanks matter as much as difficulty, so both
    are reported rather than averaged away.
    """
    if start is None:
        nxt = next_event()
        start = nxt["id"] if nxt else 1

    tm = teams()
    gws = list(range(start, min(start + horizon, 39)))
    rows = []

    for tid, t in tm.items():
        cells, total, count = [], 0, 0
        for gw in gws:
            fs = [f for f in fixtures(gw)
                  if f["team_h"] == tid or f["team_a"] == tid]
            if not fs:
                cells.append({"gw": gw, "opponents": [], "blank": True})
                continue
            opps = []
            for f in fs:
                home = f["team_h"] == tid
                opp = tm[f["team_a"] if home else f["team_h"]]["short_name"]
                fdr = f["team_h_difficulty"] if home else f["team_a_difficulty"]
                opps.append({
                    "opponent": opp,
                    "home": home,
                    "fdr": fdr,
                    "label": f"{opp.upper() if home else opp.lower()}({fdr})",
                })
                total += fdr
                count += 1
            cells.append({
                "gw": gw,
                "opponents": opps,
                "double": len(opps) > 1,
                "blank": False,
            })
        rows.append({
            "team": t["short_name"],
            "name": t["name"],
            "cells": cells,
            "avg_fdr": round(total / count, 2) if count else None,
            "matches": count,
        })

    rows.sort(key=lambda r: (r["avg_fdr"] is None, r["avg_fdr"]))
    return rows


def strength(last: int = 4) -> list[dict]:
    """
    How good each team actually is going forward and at the back, from results
    and expected goals - the measure FPL's 1-5 difficulty rating hides.

    FDR is the site's own coarse label and it was wrong where it mattered: in
    GW7 Tarkowski was started at home to Chelsea, a top-three attack by goals,
    and blanked. These are inputs for the staff to reason from, not a verdict:

    - goals for/against per game, overall, at home, away, and over the last
      `last` matches
    - xG per game, the sum of the squad's `expected_goals`
    - xGA per game, the sum of the goalkeepers' `expected_goals_conceded`
      (a keeper's xGC covers exactly the minutes he was on the pitch)
    - `attack_rank` and `defence_rank` (1 = best), each the plain average of
      the goals rank and the expected-goals rank, so a lucky or unlucky run is
      pulled toward what the chances say
    """
    tm = teams()
    done = sorted((f for f in fixtures() if f.get("finished")),
                  key=lambda f: f["kickoff_time"] or "")
    rec = {tid: {"gf": [], "ga": [], "h": [], "a": []} for tid in tm}
    for f in done:
        h, a = f["team_h"], f["team_a"]
        hs, aws = f["team_h_score"] or 0, f["team_a_score"] or 0
        rec[h]["gf"].append(hs); rec[h]["ga"].append(aws); rec[h]["h"].append((hs, aws))
        rec[a]["gf"].append(aws); rec[a]["ga"].append(hs); rec[a]["a"].append((aws, hs))

    xg = {tid: 0.0 for tid in tm}
    xga = {tid: 0.0 for tid in tm}
    for p in players().values():
        xg[p["team"]] += float(p["expected_goals"] or 0)
        if p["element_type"] == 1:
            xga[p["team"]] += float(p["expected_goals_conceded"] or 0)

    def per(xs: list, i: int | None = None) -> float | None:
        if not xs:
            return None
        vals = [x[i] for x in xs] if i is not None else xs
        return round(sum(vals) / len(vals), 2)

    rows = []
    for tid, t in tm.items():
        r = rec[tid]
        n = len(r["gf"])
        rows.append({
            "id": tid,
            "team": t["short_name"],
            "played": n,
            "gf_pg": per(r["gf"]),
            "ga_pg": per(r["ga"]),
            "xg_pg": round(xg[tid] / n, 2) if n else None,
            "xga_pg": round(xga[tid] / n, 2) if n else None,
            "home_gf_pg": per(r["h"], 0),
            "home_ga_pg": per(r["h"], 1),
            "away_gf_pg": per(r["a"], 0),
            "away_ga_pg": per(r["a"], 1),
            "last_gf_pg": per(r["gf"][-last:]),
            "last_ga_pg": per(r["ga"][-last:]),
        })

    def rank(key: str, high_is_good: bool) -> dict:
        def k(r):
            v = r[key] or 0
            return (r[key] is None, -v if high_is_good else v)
        return {r["id"]: i + 1 for i, r in enumerate(sorted(rows, key=k))}

    gf_r, xg_r = rank("gf_pg", True), rank("xg_pg", True)
    ga_r, xga_r = rank("ga_pg", False), rank("xga_pg", False)
    for r in rows:
        r["attack_score"] = (gf_r[r["id"]] + xg_r[r["id"]]) / 2
        r["defence_score"] = (ga_r[r["id"]] + xga_r[r["id"]]) / 2
    for key, out in (("attack_score", "attack_rank"), ("defence_score", "defence_rank")):
        for i, r in enumerate(sorted(rows, key=lambda r: r[key])):
            r[out] = i + 1
    rows.sort(key=lambda r: r["attack_rank"])
    return rows


def matchups(team_id: int = config.ENTRY_ID, gw: int | None = None, horizon: int = 4) -> list[dict]:
    """
    Every player in the manager's fifteen against the strength of the team he
    faces, this gameweek and over the next `horizon`.

    Keepers and defenders are read against the opponent's **attack**; midfielders
    and forwards against the opponent's **defence**. A keeper or defender facing
    a top-five attack (`attack_rank` 1-5) is flagged - CLAUDE.md makes benching
    him the default unless no fit alternative exists.

    The fifteen are the latest published picks, so before a deadline this is
    last gameweek's squad (the stale-picks trap in CLAUDE.md).
    """
    if gw is None:
        nxt = next_event()
        gw = nxt["id"] if nxt else current_event()["id"]
    cur = current_event()
    pk = picks(team_id, cur["id"] if cur else gw)
    pl, tm = players(), teams()
    st = {r["id"]: r for r in strength()}

    def opps(tid: int, g: int) -> list[tuple[int, bool]]:
        return [((f["team_a"], True) if f["team_h"] == tid else (f["team_h"], False))
                for f in fixtures(g) if tid in (f["team_h"], f["team_a"])]

    def label(o: int, home: bool, key: str) -> str:
        name = tm[o]["short_name"]
        return f"{name.upper() if home else name.lower()}({st[o][key]})"

    rows = []
    for item in pk["picks"]:
        p = pl[item["element"]]
        pos = POSITIONS[p["element_type"]]
        back = pos in ("GKP", "DEF")
        key = "attack_rank" if back else "defence_rank"
        this = opps(p["team"], gw)
        run = [label(o, h, key)
               for g in range(gw + 1, min(gw + 1 + horizon, 39))
               for o, h in opps(p["team"], g)]
        rows.append({
            "pos": pos,
            "name": player_name(p),
            "team": tm[p["team"]]["short_name"],
            "reads": "opp attack" if back else "opp defence",
            "this_gw": [label(o, h, key) for o, h in this] or ["blank"],
            "run": run,
            "top5_attack_flag": back and any(st[o]["attack_rank"] <= 5 for o, _ in this),
        })
    return rows


def market(limit: int = 15) -> dict:
    """
    What the world is doing **right now**, for the gameweek that has not
    happened yet.

    This is the one genuinely forward-looking crowd signal in the API. Elite
    ownership and chip counts describe the week just gone; `transfers_in_event`
    accumulates during the current gameweek and applies to the NEXT deadline, so
    it says what managers are buying for the week being planned, not the week
    being played. Price changes confirm it with money.
    """
    bs = get("bootstrap-static", force=True)
    tm = {t["id"]: t for t in bs["teams"]}
    rows = []
    for p in bs["elements"]:
        rows.append({
            "name": player_name(p),
            "team": tm[p["team"]]["short_name"],
            "pos": POSITIONS[p["element_type"]],
            "in": p.get("transfers_in_event", 0),
            "out": p.get("transfers_out_event", 0),
            "net": p.get("transfers_in_event", 0) - p.get("transfers_out_event", 0),
            "price": p["now_cost"] / 10,
            "change": p.get("cost_change_event", 0) / 10,
            "owned": float(p["selected_by_percent"] or 0),
            "status": p["status"],
            "news": p.get("news", ""),
        })
    rows.sort(key=lambda r: -r["net"])
    cur = current_event()
    return {
        "for_event": (next_event() or {}).get("id"),
        "transfers_made": (cur or {}).get("transfers_made", 0),
        "in": rows[:limit],
        "out": list(reversed(rows[-limit:])),
    }


def player_summary(player_id: int) -> dict:
    """Per-match history and upcoming fixtures for one player."""
    return get(f"element-summary/{player_id}")


def live(event_id: int) -> dict:
    """Live points for a gameweek in progress."""
    return get(f"event/{event_id}/live")


# ------------------------------------------------------------- the manager

def entry(team_id: int) -> dict:
    """Top-level info for an FPL manager: name, rank, overall points."""
    return get(f"entry/{team_id}")


def entry_history(team_id: int) -> dict:
    """Per-gameweek history, past seasons, and chips already played."""
    return get(f"entry/{team_id}/history")


def entry_transfers(team_id: int) -> list[dict]:
    return get(f"entry/{team_id}/transfers")


def league(league_id: int = config.LEAGUE_ID) -> list[dict]:
    """
    Current mini-league standings, always fetched fresh.

    The table is deliberately not written down anywhere in this project. It
    changes every gameweek, and a copy pasted into a document or an agent brief
    is wrong within a week - agents were reasoning from a GW3 table well into
    GW4, which quietly corrupts every gap calculation built on it.
    """
    st = get(f"leagues-classic/{league_id}/standings", force=True)
    return [{
        "rank": r["rank"],
        "entry": r["entry"],
        "manager": r["player_name"],
        "team": r["entry_name"],
        "total": r["total"],
        "gw": r["event_total"],
    } for r in st["standings"]["results"]]


def picks(team_id: int, event_id: int) -> dict:
    """The 15 players picked for a gameweek. Public only after that deadline."""
    return get(f"entry/{team_id}/event/{event_id}/picks")


def squad(team_id: int, event_id: int | None = None) -> dict:
    """
    A readable snapshot of the manager's squad: starting XI, bench, captain,
    bank, squad value, free transfers and chips still available.
    """
    if event_id is None:
        cur = current_event()
        if not cur:
            raise FPLError("No current gameweek - the season may not have started.")
        event_id = cur["id"]

    pk = picks(team_id, event_id)
    pl = players()
    tm = teams()
    hist = entry_history(team_id)

    used_chips = {c["name"] for c in hist.get("chips", [])}
    all_chips = {"wildcard", "freehit", "bboost", "3xc"}

    rows = []
    for item in pk["picks"]:
        p = pl[item["element"]]
        rows.append({
            "pos": POSITIONS[p["element_type"]],
            "name": player_name(p),
            "team": tm[p["team"]]["short_name"],
            "price": p["now_cost"] / 10,
            "points": p["total_points"],
            "form": float(p["form"] or 0),
            "selected_by": float(p["selected_by_percent"] or 0),
            "status": p["status"],            # a=available, i=injured, d=doubtful
            "news": p.get("news", ""),
            "slot": item["position"],          # 1-11 start, 12-15 bench
            "is_captain": item["is_captain"],
            "is_vice": item["is_vice_captain"],
            "multiplier": item["multiplier"],
        })
    rows.sort(key=lambda r: r["slot"])

    return {
        "event": event_id,
        "entry": entry(team_id),
        "starting_xi": [r for r in rows if r["slot"] <= 11],
        "bench": [r for r in rows if r["slot"] > 11],
        "captain": next((r["name"] for r in rows if r["is_captain"]), None),
        "vice_captain": next((r["name"] for r in rows if r["is_vice"]), None),
        "bank": pk["entry_history"]["bank"] / 10,
        "squad_value": pk["entry_history"]["value"] / 10,
        "event_transfers": pk["entry_history"]["event_transfers"],
        "event_transfers_cost": pk["entry_history"]["event_transfers_cost"],
        "chips_used": sorted(used_chips),
        "chips_available": sorted(all_chips - used_chips),
        "active_chip": pk.get("active_chip"),
    }


# --------------------------------------------------------------------- CLI

def _cmd_status() -> None:
    cur = current_event()
    ev, hours = deadline()
    print(f"current gameweek : {cur['name'] if cur else 'none'}")
    if ev:
        print(f"next gameweek    : {ev['name']}")
        print(f"deadline         : {ev['deadline_time']}  ({hours:.1f}h away)")
    bs = bootstrap()
    print(f"players          : {len(bs['elements'])}")
    print(f"teams            : {len(bs['teams'])}")


def _cmd_hours() -> None:
    """Just the hours until the next deadline, for scripts to branch on."""
    _, hours = deadline()
    print("none" if hours is None else f"{hours:.2f}")


def _cmd_squad(team_id: int) -> None:
    s = squad(team_id)
    e = s["entry"]
    print(f"{e['player_first_name']} {e['player_last_name']} - \"{e['name']}\"")
    print(f"GW{s['event']}  overall rank {e.get('summary_overall_rank'):,}  "
          f"points {e.get('summary_overall_points')}")
    print(f"squad value {s['squad_value']}m   bank {s['bank']}m   "
          f"chips left: {', '.join(s['chips_available']) or 'none'}")
    print()
    for label, rows in (("STARTING XI", s["starting_xi"]), ("BENCH", s["bench"])):
        print(label)
        for r in rows:
            mark = ""
            if r["is_captain"]:
                mark = " (C)"
            elif r["is_vice"]:
                mark = " (V)"
            flag = "" if r["status"] == "a" else f"  [{r['status']}] {r['news']}"
            print(f"  {r['pos']:3} {r['name']:<18} {r['team']:<4} "
                  f"{r['price']:>4.1f}m  {r['points']:>3}pts  form {r['form']:>4}{mark}{flag}")
        print()


def _cmd_market(limit: int = 12) -> None:
    m = market(limit)
    print(f"LIVE TRANSFER MARKET - for GW{m['for_event']}, the week not yet played")
    print(f"{m['transfers_made']:,} transfers made so far this period\n")
    for label, rows in (("MOVING IN", m["in"]), ("MOVING OUT", m["out"])):
        print(label)
        print(f"  {'player':<20}{'club':<6}{'net':>10}{'price':>7}{'chg':>6}{'owned':>7}")
        for r in rows:
            flag = "" if r["status"] == "a" else f"  [{r['status']}]"
            print(f"  {r['name']:<20}{r['team']:<6}{r['net']:>+10,}"
                  f"{r['price']:>7.1f}{r['change']:>+6.1f}{r['owned']:>6.1f}%{flag}")
        print()
    print("Unlike elite ownership, this is forward-looking: these transfers apply")
    print("to the next deadline, not the gameweek being played.")


def _cmd_league(league_id: int = config.LEAGUE_ID) -> None:
    rows = league(league_id)
    mine = next((r for r in rows if r["entry"] == config.ENTRY_ID), None)
    print(f"{'':2} {'manager':<15}{'team':<26}{'total':>6}{'GW':>5}{'gap':>7}")
    print("-" * 61)
    for r in rows:
        gap = "" if not mine or r["entry"] == config.ENTRY_ID else f"{mine['total'] - r['total']:+d}"
        mark = "->" if r["entry"] == config.ENTRY_ID else "  "
        print(f"{mark} {r['manager']:<15}{r['team']:<26}{r['total']:>6}{r['gw']:>5}{gap:>7}")
    print("\ngap = Ido minus that rival. Negative means he is behind them.")


def _cmd_player(needle: str) -> None:
    tm = teams()
    hits = find_players(needle)
    if not hits:
        print(f"no player matching {needle!r}")
        return
    for p in sorted(hits, key=lambda x: -x["total_points"])[:15]:
        print(f"  {POSITIONS[p['element_type']]:3} {player_name(p):<20} "
              f"{tm[p['team']]['short_name']:<4} {p['now_cost']/10:>4.1f}m  "
              f"{p['total_points']:>3}pts  form {p['form']:>4}  "
              f"owned {p['selected_by_percent']:>4}%  id={p['id']}")


def _cmd_ticker(horizon: int = 6) -> None:
    rows = ticker(horizon=horizon)
    gws = [c["gw"] for c in rows[0]["cells"]]
    header = "team  " + "".join(f"GW{g:<10}" for g in gws) + "avg"
    print(header)
    print("-" * len(header))
    for r in rows:
        line = f"{r['team']:<6}"
        for c in r["cells"]:
            if c["blank"]:
                cell = "-"
            else:
                cell = "+".join(o["label"] for o in c["opponents"])
            line += f"{cell:<12}"
        line += f"{r['avg_fdr']}"
        print(line)
    print()
    print("UPPERCASE = home, lowercase = away, (n) = difficulty 1-5, - = blank")


def _cmd_strength() -> None:
    rows = strength()
    print("team  P   ATT  DEF   GF/g  xG/g  GA/g xGA/g   homeGF awayGF homeGA awayGA  last4GF last4GA")
    print("-" * 94)
    f = lambda v: "  -  " if v is None else f"{v:5.2f}"
    for r in rows:
        print(f"{r['team']:<5} {r['played']:<3} {r['attack_rank']:>3}  {r['defence_rank']:>3}  "
              f"{f(r['gf_pg'])} {f(r['xg_pg'])} {f(r['ga_pg'])} {f(r['xga_pg'])}   "
              f"{f(r['home_gf_pg'])}  {f(r['away_gf_pg'])}  {f(r['home_ga_pg'])}  {f(r['away_ga_pg'])}    "
              f"{f(r['last_gf_pg'])}   {f(r['last_ga_pg'])}")
    print()
    print("ATT/DEF = rank 1-20, 1 = best; each is the average of the goals rank and the xG rank.")
    print("Sorted by attack. Season to date - early-season samples are small, say so.")


def _cmd_matchups(team_id: int) -> None:
    rows = matchups(team_id)
    print("Keepers/defenders read against the opponent's ATTACK rank, attackers against its")
    print("DEFENCE rank (1 = best in the league, so a low number is a hard game).")
    print("Squad = latest PUBLISHED picks; before a deadline that is last gameweek's fifteen.")
    print()
    for r in rows:
        flag = "  << faces a top-5 attack" if r["top5_attack_flag"] else ""
        print(f"{r['pos']:<4} {r['name']:<16} {r['team']:<4} {'+'.join(r['this_gw']):<10} "
              f"then: {' '.join(r['run'])}{flag}")


def main(argv: list[str]) -> int:
    # Player names carry accents (Sávio, Muñoz, Højlund) and the Windows console
    # here defaults to a Hebrew codepage that cannot encode them.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    if not argv:
        print(__doc__)
        return 0
    cmd, *rest = argv
    try:
        if cmd == "status":
            _cmd_status()
        elif cmd == "refresh":
            refresh()
            print("refreshed bootstrap-static and fixtures")
            _cmd_status()
        elif cmd == "squad":
            if not rest:
                print("usage: python fpl.py squad <team_id>")
                return 2
            _cmd_squad(int(rest[0]))
        elif cmd == "hours":
            _cmd_hours()
        elif cmd == "league":
            _cmd_league(int(rest[0]) if rest else config.LEAGUE_ID)
        elif cmd == "market":
            _cmd_market(int(rest[0]) if rest else 12)
        elif cmd == "ticker":
            _cmd_ticker(int(rest[0]) if rest else 6)
        elif cmd == "strength":
            _cmd_strength()
        elif cmd == "matchups":
            _cmd_matchups(int(rest[0]) if rest else config.ENTRY_ID)
        elif cmd == "player":
            if not rest:
                print("usage: python fpl.py player <name>")
                return 2
            _cmd_player(" ".join(rest))
        else:
            print(f"unknown command {cmd!r}")
            print(__doc__)
            return 2
    except FPLError as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
