"""
What the top 100 managers in the world actually own.

The Media Analyst's most valuable output is contradiction - "three channels are
pushing X, but 4% of the top 100 own him". That claim was previously guesswork
scraped off blogs. This module makes it a measurement: it reads the real overall
standings, pulls all 100 squads, and counts.

**The list is rebuilt every time.** That was the point of Ido's request - the top
100 is not a fixed group of people, it churns week to week, and a list captured
once in September would be describing the wrong hundred managers by October. The
managers are looked up fresh on every refresh, never read back from a stored
roster.

    python elite.py refresh        rebuild the list and recount (~30 seconds)
    python elite.py                the ownership table
    python elite.py captains       who they captained
    python elite.py moves          what changed since last gameweek
    python elite.py compare        Ido's squad against elite ownership
    python elite.py behaviour      how the top 100 play the season (transfers, hits,
                                   bench, captains, chips, value) beside Ido
    python elite.py behaviour --rebuild   re-read their season histories first

One caveat that must survive into anything quoting these numbers: **FPL publishes
a manager's picks only after that gameweek's deadline.** Elite ownership is
therefore always as of the last deadline that has passed, never the upcoming
gameweek. Before a deadline it tells you what they owned last week, which is
usually a good guide to this week and occasionally badly wrong - a bandwagon
forms in exactly the window this data cannot see.
"""
from __future__ import annotations

import config
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

import fpl

OVERALL_LEAGUE = 314        # the "Overall" classic league - every manager is in it
TOP_N = 100
PAUSE = 0.25                # polite gap between the 100 squad requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def _fetch(endpoint: str) -> dict:
    """
    Straight to the API, deliberately bypassing fpl.get's disk cache.

    fpl.get writes one file per endpoint, and this module would otherwise leave
    a hundred `entry_<id>_event_<n>_picks.json` files in data/ every gameweek -
    some four thousand across a season, burying the handful of files a person
    actually opens. The aggregate written by refresh() is the artifact worth
    keeping; the individual squads are scaffolding.
    """
    url = f"{fpl.BASE}/{endpoint}/"
    if "?" in endpoint:
        path, query = endpoint.split("?", 1)
        url = f"{fpl.BASE}/{path}/?{query}"
    resp = requests.get(url, headers=fpl.HEADERS, timeout=30)
    if resp.status_code != 200:
        raise fpl.FPLError(f"{url} returned HTTP {resp.status_code}")
    return resp.json()


def state_path(gw: int) -> Path:
    return DATA / f"elite_gw{gw}.json"


def load(gw: int | None = None) -> dict:
    """The most recent snapshot, or a specific gameweek's."""
    if gw is None:
        snaps = sorted(DATA.glob("elite_gw*.json"),
                       key=lambda p: int(p.stem.replace("elite_gw", "")))
        if not snaps:
            raise fpl.FPLError("No elite snapshot yet - run: python elite.py refresh")
        return json.loads(snaps[-1].read_text(encoding="utf-8"))
    p = state_path(gw)
    if not p.exists():
        raise fpl.FPLError(f"No elite snapshot for GW{gw} - run: python elite.py refresh")
    return json.loads(p.read_text(encoding="utf-8"))


# ------------------------------------------------------------- the refresh

def top_managers(n: int = TOP_N) -> list[dict]:
    """
    The current top n of the overall league, freshly looked up.

    Paging is not as simple as it looks: the pages overlap where managers are
    tied on points, so page 2 can start at rank 47 rather than 51. Dedupe by
    entry id and stop once n distinct managers have been seen, rather than
    trusting 50-per-page arithmetic.
    """
    out: list[dict] = []
    seen: set[int] = set()
    page = 1
    while len(out) < n and page <= 10:
        data = _fetch(f"leagues-classic/{OVERALL_LEAGUE}/standings?page_standings={page}")
        rows = data["standings"]["results"]
        if not rows:
            break
        for r in rows:
            if r["entry"] in seen:
                continue
            seen.add(r["entry"])
            out.append({
                "rank": r["rank"],
                "entry": r["entry"],
                "manager": r["player_name"],
                "team": r["entry_name"],
                "total": r["total"],
            })
            if len(out) >= n:
                break
        if not data["standings"].get("has_next"):
            break
        page += 1
    return out


def refresh(gw: int | None = None, quiet: bool = False) -> dict:
    if gw is None:
        cur = fpl.current_event()
        if not cur:
            raise fpl.FPLError("No current gameweek yet.")
        gw = cur["id"]

    def say(msg: str) -> None:
        if not quiet:
            print(msg, flush=True)

    say(f"Reading the current top {TOP_N} of the overall league...")
    managers = top_managers()
    say(f"  got {len(managers)} managers, ranks "
        f"{managers[0]['rank']}-{managers[-1]['rank']}")

    ownership: Counter[int] = Counter()
    captains: Counter[int] = Counter()
    vices: Counter[int] = Counter()
    benched: Counter[int] = Counter()
    prev_ownership: Counter[int] = Counter()
    squads: dict[str, list[int]] = {}
    chips: Counter[str] = Counter()
    failed = 0
    prev_counted = 0

    say(f"Pulling their GW{gw} squads...")
    for i, m in enumerate(managers, 1):
        try:
            pk = _fetch(f"entry/{m['entry']}/event/{gw}/picks")
        except (fpl.FPLError, requests.RequestException):
            failed += 1
            continue

        # Last week's squad for the SAME manager, so `moves` measures transfers
        # rather than churn in the list. Comparing this week's hundred against
        # last week's hundred would blend the two: a player's ownership could
        # appear to jump purely because different managers are now in the top
        # 100, without one of them having bought him.
        if gw > 1:
            try:
                prev_pk = _fetch(f"entry/{m['entry']}/event/{gw - 1}/picks")
                prev_counted += 1
                for item in prev_pk["picks"]:
                    prev_ownership[item["element"]] += 1
            except (fpl.FPLError, requests.RequestException):
                pass
            time.sleep(PAUSE)
        ids = []
        for item in pk["picks"]:
            eid = item["element"]
            ids.append(eid)
            ownership[eid] += 1
            if item["is_captain"]:
                captains[eid] += 1
            if item["is_vice_captain"]:
                vices[eid] += 1
            if item["position"] > 11:
                benched[eid] += 1
        squads[str(m["entry"])] = ids
        if pk.get("active_chip"):
            chips[pk["active_chip"]] += 1
        if not quiet and i % 25 == 0:
            say(f"  {i}/{len(managers)}")
        time.sleep(PAUSE)

    counted = len(squads)
    if counted == 0:
        raise fpl.FPLError(
            f"Could not read a single elite squad for GW{gw}. Picks are public "
            "only after the deadline - has this gameweek started?")
    if failed and not quiet:
        say(f"  {failed} squad(s) unreadable, counted {counted}")

    snapshot = {
        "event": gw,
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counted": counted,
        "managers": managers,
        "ownership": {str(k): v for k, v in ownership.items()},
        "captains": {str(k): v for k, v in captains.items()},
        "vices": {str(k): v for k, v in vices.items()},
        "benched": {str(k): v for k, v in benched.items()},
        "prev_event": gw - 1 if gw > 1 else None,
        "prev_counted": prev_counted,
        "prev_ownership": {str(k): v for k, v in prev_ownership.items()},
        "chips": dict(chips),
        "squads": squads,
    }
    DATA.mkdir(exist_ok=True)
    state_path(gw).write_text(json.dumps(snapshot, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    say(f"Wrote {state_path(gw).name}: {counted} squads, "
        f"{len(ownership)} distinct players owned"
        + (f", plus their GW{gw - 1} squads for the transfer view." if prev_counted
           else "."))
    behaviour(gw, managers, quiet=quiet)
    return snapshot


# ------------------------------------------------------- behaviour over time
#
# Ownership says WHAT the elite hold this week. Ido asked (29 Oct 2026) for the
# other half: HOW they play over the whole season - "we want to understand their
# behaviour over time to see what makes them top 100". One history request per
# manager returns his entire season (points, transfers, hits, bench, value,
# ranks, chips) and his past seasons' finishes, so every refresh can rebuild the
# current top 100's season week by week. Each refresh is kept under its own
# gameweek in data/elite_behaviour.json, so the file accumulates and shows how
# the elite group itself changes.

BEHAVIOUR = DATA / "elite_behaviour.json"


def _median(xs: list[float]) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2


def _avg(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def _season(history: dict) -> dict[int, dict]:
    """One manager's season, keyed by gameweek."""
    chips = {c["event"]: c["name"] for c in history.get("chips", [])}
    return {g["event"]: {
        "points": g["points"] - g["event_transfers_cost"],
        "transfers": g["event_transfers"],
        "hit": g["event_transfers_cost"],
        "bench": g["points_on_bench"],
        "value": g["value"] / 10,
        "bank": g["bank"] / 10,
        "overall_rank": g["overall_rank"],
        "chip": chips.get(g["event"]),
    } for g in history.get("current", [])}


def _captain_points(gw: int, captains: dict[str, int], counted: int) -> float | None:
    """The elite's average captain score (undoubled) from that week's snapshot."""
    try:
        pts = {e["id"]: e["stats"]["total_points"] for e in fpl.live(gw)["elements"]}
    except fpl.FPLError:
        return None
    return round(sum(pts.get(int(k), 0) * c for k, c in captains.items()) / counted, 1)


def behaviour(gw: int | None = None, managers: list[dict] | None = None,
              quiet: bool = False) -> dict:
    if gw is None:
        gw = fpl.current_event()["id"]
    if managers is None:
        managers = top_managers()
    if not quiet:
        print(f"Reading the season history of the top {len(managers)}...", flush=True)

    seasons, past = [], []
    for m in managers:
        try:
            h = _fetch(f"entry/{m['entry']}/history")
        except (fpl.FPLError, requests.RequestException):
            continue
        seasons.append(_season(h))
        ranks = [p["rank"] for p in h.get("past", []) if p.get("rank")]
        past.append({"seasons": len(ranks), "best": min(ranks) if ranks else None,
                     "last": ranks[-1] if ranks else None})
        time.sleep(PAUSE)
    me = _season(fpl.entry_history(config.ENTRY_ID))

    weeks = []
    for g in sorted(me):
        rows = [s[g] for s in seasons if g in s]
        if not rows:
            continue
        snap = state_path(g)
        cap = None
        if snap.exists():
            sd = json.loads(snap.read_text(encoding="utf-8"))
            cap = _captain_points(g, sd["captains"], sd["counted"])
        try:
            my_cap = next(p["element"] for p in fpl.picks(config.ENTRY_ID, g)["picks"] if p["is_captain"])
            my_cap_pts = next(e["stats"]["total_points"] for e in fpl.live(g)["elements"]
                              if e["id"] == my_cap)
        except (fpl.FPLError, StopIteration, KeyError):
            my_cap_pts = None
        chips = Counter(r["chip"] for r in rows if r["chip"])
        weeks.append({
            "gw": g,
            "elite": {
                "points": _avg([r["points"] for r in rows]),
                "transfers": _avg([r["transfers"] for r in rows]),
                "took_hit_pct": round(100 * sum(1 for r in rows if r["hit"]) / len(rows)),
                "bench": _avg([r["bench"] for r in rows]),
                "value": _avg([r["value"] for r in rows]),
                "bank": _avg([r["bank"] for r in rows]),
                "median_rank": _median([r["overall_rank"] for r in rows]),
                "chips": dict(chips),
                "captain_points": cap,
            },
            "ido": {**{k: me[g][k] for k in
                       ("points", "transfers", "hit", "bench", "value", "bank",
                        "overall_rank", "chip")},
                    "captain_points": my_cap_pts},
        })

    out = {
        "event": gw,
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counted": len(seasons),
        "weeks": weeks,
        "past_seasons": {
            "with_history": sum(1 for p in past if p["seasons"]),
            "median_seasons_played": _median([p["seasons"] for p in past]),
            "best_ever_top_10k_pct": round(100 * sum(1 for p in past if p["best"] and p["best"] <= 10_000)
                                           / len(past)) if past else None,
            "last_season_top_100k_pct": round(100 * sum(1 for p in past if p["last"] and p["last"] <= 100_000)
                                              / len(past)) if past else None,
        },
    }
    store = json.loads(BEHAVIOUR.read_text(encoding="utf-8")) if BEHAVIOUR.exists() else {}
    store[f"gw{gw}"] = out
    BEHAVIOUR.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    if not quiet:
        print(f"Wrote {BEHAVIOUR.name} (gw{gw}): {len(seasons)} season histories.")
    return out


def _rank(x: float | None) -> str:
    if x is None:
        return "-"
    if x >= 1e6:
        return f"{x / 1e6:.1f}M"
    return f"{x / 1e3:.0f}k" if x >= 1e4 else f"{x:.0f}"


def cmd_behaviour(gw: int | None) -> None:
    """How the current top 100 have played the season, beside Ido, week by week."""
    if not BEHAVIOUR.exists():
        print("No behaviour data yet - run: python elite.py refresh")
        return
    store = json.loads(BEHAVIOUR.read_text(encoding="utf-8"))
    key = f"gw{gw}" if gw else max(store, key=lambda k: int(k[2:]))
    b = store[key]
    print(f"How the CURRENT top {b['counted']} played the season (as of GW{b['event']}), "
          f"against Ido. Elite = average of the {b['counted']}.\n")
    print(f"{'GW':<4}{'points':>13}{'transfers':>13}{'took hit':>14}{'bench pts':>13}"
          f"{'captain pts':>15}{'median rank':>16}  chips (elite / Ido)")
    for w in b["weeks"]:
        e, i = w["elite"], w["ido"]
        fmt = lambda a, c: f"{'-' if a is None else a:>6}/{'-' if c is None else c:<5}"
        hit = f"{e['took_hit_pct']:>5}%/{'yes' if i['hit'] else 'no':<5}"
        rank = f"{_rank(e['median_rank']):>6}/{_rank(i['overall_rank'])}"
        chips = ", ".join(f"{k} x{v}" for k, v in e["chips"].items()) or "-"
        print(f"{w['gw']:<4}{fmt(e['points'], i['points']):>13}{fmt(e['transfers'], i['transfers']):>13}"
              f"{hit:>14}{fmt(e['bench'], i['bench']):>13}{fmt(e['captain_points'], i['captain_points']):>15}"
              f"{rank:>16}  {chips} / {i['chip'] or '-'}")

    ws = b["weeks"]
    tot = lambda who, k: sum((w[who][k] or 0) for w in ws)
    print("\nSEASON SO FAR (elite average v Ido)")
    print(f"  points          {tot('elite', 'points'):.0f} v {tot('ido', 'points')}")
    print(f"  transfers made  {tot('elite', 'transfers'):.1f} v {tot('ido', 'transfers')}")
    print(f"  weeks with a hit {sum(w['elite']['took_hit_pct'] for w in ws) / 100:.1f} v "
          f"{sum(1 for w in ws if w['ido']['hit'])}")
    print(f"  bench points    {tot('elite', 'bench'):.0f} v {tot('ido', 'bench')}")
    caps = [w for w in ws if w["elite"]["captain_points"] is not None]
    if caps:
        print(f"  captain pts/wk  {_avg([w['elite']['captain_points'] for w in caps])} v "
              f"{_avg([w['ido']['captain_points'] for w in caps])}  (GW{caps[0]['gw']} on, "
              f"from weekly snapshots - each week's own top 100)")
    print(f"  team value now  {ws[-1]['elite']['value']} v {ws[-1]['ido']['value']}")
    p = b["past_seasons"]
    print(f"\nTHEIR PAST: median {p['median_seasons_played']} seasons played; "
          f"{p['best_ever_top_10k_pct']}% have finished a season in the top 10k; "
          f"{p['last_season_top_100k_pct']}% were top 100k last season.")
    if len(store) > 1:
        print(f"\nStored weeks: {', '.join(sorted(store, key=lambda k: int(k[2:])))} "
              "- compare with --gw=<n> to see how the group changes.")


# --------------------------------------------------------------- reporting

def _name(eid: int, pl: dict, tm: dict) -> str:
    p = pl.get(eid)
    if not p:
        return f"#{eid}"
    return f"{fpl.player_name(p)} ({tm[p['team']]['short_name']})"


def pct(count: int, total: int) -> float:
    return round(100.0 * count / total, 1) if total else 0.0


def table(snap: dict, key: str = "ownership", limit: int = 25) -> list[dict]:
    pl, tm = fpl.players(), fpl.teams()
    total = snap["counted"]
    rows = []
    for sid, c in snap[key].items():
        eid = int(sid)
        p = pl.get(eid)
        rows.append({
            "id": eid,
            "name": _name(eid, pl, tm),
            "pos": fpl.POSITIONS[p["element_type"]] if p else "?",
            "count": c,
            "elite_pct": pct(c, total),
            "global_pct": float(p["selected_by_percent"]) if p else 0.0,
        })
    rows.sort(key=lambda r: -r["count"])
    return rows[:limit]


def _header(snap: dict) -> None:
    print(f"Top {snap['counted']} managers, GW{snap['event']} squads "
          f"(fetched {snap['fetched'][:16].replace('T', ' ')} UTC)")
    print("Picks are public only after a deadline - this is the last team they "
          "actually fielded.\n")


def cmd_table(gw: int | None, limit: int) -> None:
    snap = load(gw)
    _header(snap)
    print(f"{'player':<28}{'pos':<5}{'elite':>7}{'world':>8}{'gap':>8}")
    print("-" * 56)
    for r in table(snap, "ownership", limit):
        gap = r["elite_pct"] - r["global_pct"]
        print(f"{r['name']:<28}{r['pos']:<5}{r['elite_pct']:>6.1f}%"
              f"{r['global_pct']:>7.1f}%{gap:>+8.1f}")
    print("\ngap = how much more the elite own him than the world does. A large "
          "positive gap\nis the elite backing something the crowd has not caught "
          "up with yet.")


def cmd_captains(gw: int | None, limit: int) -> None:
    snap = load(gw)
    _header(snap)
    print(f"{'captain':<28}{'of top ' + str(snap['counted']):>12}")
    print("-" * 40)
    for r in table(snap, "captains", limit):
        print(f"{r['name']:<28}{r['count']:>6}  {r['elite_pct']:>5.1f}%")
    if snap.get("chips"):
        print("\nchips played:", ", ".join(f"{k} x{v}" for k, v in snap["chips"].items()))


def cmd_moves(gw: int | None, limit: int) -> None:
    """
    What the elite bought and sold, measured on the same hundred managers.

    Both weeks come from one snapshot, so a swing here is a real transfer by
    people currently in the top 100 - not an artefact of the list churning.
    """
    snap = load(gw)
    prev = snap.get("prev_ownership")
    prev_total = snap.get("prev_counted") or 0
    if not prev or not prev_total:
        print(f"GW{snap['event']} snapshot has no previous week recorded. "
              "Run `python elite.py refresh` to rebuild it - refresh now stores "
              "both weeks so this view compares like with like.")
        return

    pl, tm = fpl.players(), fpl.teams()
    now_total = snap["counted"]
    rows = []
    for sid in set(snap["ownership"]) | set(prev):
        now = pct(snap["ownership"].get(sid, 0), now_total)
        was = pct(prev.get(sid, 0), prev_total)
        if now == was:
            continue
        rows.append({"name": _name(int(sid), pl, tm), "was": was, "now": now,
                     "delta": round(now - was, 1)})
    rows.sort(key=lambda r: -r["delta"])

    print(f"What the current top {now_total} did between GW{snap['prev_event']} "
          f"and GW{snap['event']}")
    print("Same managers both weeks, so this is transfers, not list churn.\n")
    print("MOVING IN")
    for r in rows[:limit]:
        if r["delta"] <= 0:
            break
        print(f"  {r['name']:<28}{r['was']:>6.1f}% -> {r['now']:>5.1f}%  {r['delta']:>+6.1f}")
    print("\nMOVING OUT")
    for r in reversed(rows[-limit:]):
        if r["delta"] >= 0:
            break
        print(f"  {r['name']:<28}{r['was']:>6.1f}% -> {r['now']:>5.1f}%  {r['delta']:>+6.1f}")


def cmd_compare(gw: int | None, limit: int) -> None:
    """Ido's fifteen against what the elite hold, and what he is missing."""
    snap = load(gw)
    pl, tm = fpl.players(), fpl.teams()
    total = snap["counted"]
    own = snap["ownership"]

    sq = fpl.squad(config.ENTRY_ID, snap["event"])
    mine_ids = []
    for row in sq["starting_xi"] + sq["bench"]:
        hits = [p for p in pl.values() if fpl.player_name(p) == row["name"]]
        if hits:
            mine_ids.append(hits[0]["id"])

    _header(snap)
    print("YOUR SQUAD, BY ELITE OWNERSHIP")
    print("-" * 48)
    mine = sorted(mine_ids, key=lambda e: -own.get(str(e), 0))
    for eid in mine:
        c = own.get(str(eid), 0)
        flag = "  <- almost nobody elite owns him" if pct(c, total) < 5 else ""
        print(f"  {_name(eid, pl, tm):<28}{pct(c, total):>6.1f}%{flag}")

    print("\nMOST-OWNED PLAYERS YOU DO NOT HAVE")
    print("-" * 48)
    shown = 0
    for r in table(snap, "ownership", 60):
        if r["id"] in mine_ids:
            continue
        print(f"  {r['name']:<28}{r['elite_pct']:>6.1f}%")
        shown += 1
        if shown >= limit:
            break


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    cmd = argv[0] if argv else "table"
    rest = argv[1:]
    gw = None
    limit = 25
    for a in rest:
        if a.startswith("--gw="):
            gw = int(a.split("=", 1)[1])
        elif a.isdigit():
            limit = int(a)

    try:
        if cmd == "refresh":
            refresh(gw)
        elif cmd in ("table", "own", "ownership"):
            cmd_table(gw, limit)
        elif cmd == "captains":
            cmd_captains(gw, limit)
        elif cmd == "moves":
            cmd_moves(gw, limit)
        elif cmd == "compare":
            cmd_compare(gw, limit)
        elif cmd == "behaviour":
            if "--rebuild" in rest:
                behaviour(gw)
            cmd_behaviour(gw)
        else:
            print(__doc__)
            return 2
    except fpl.FPLError as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
