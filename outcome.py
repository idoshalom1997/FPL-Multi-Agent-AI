"""
Scores what the staff recommended against what Ido actually did.

The staff write one file per gameweek into `recommendations/` before the
deadline. After the gameweek this reads the real picks back from the API and
answers the only question the Historian cares about: was the advice worth
following, and which option came closest to what he chose?

    python outcome.py 4          score GW4 and write the result back
    python outcome.py 4 --dry    score it, print, write nothing
    python outcome.py 4 --said "went with what I sent, no changes" \
                         --choice DO_NOTHING      log Ido's own line

Refuses to run before the deadline has passed. Before a deadline the API still
serves the PREVIOUS gameweek's picks, so scoring early would silently compare
the recommendation against the wrong team - the same stale-picks trap that has
already produced one bad report.
"""
from __future__ import annotations

import config
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import fpl

ROOT = Path(__file__).resolve().parent
RECS = ROOT / "recommendations"
TEAM_ID = config.ENTRY_ID


# --------------------------------------------------------------------------
# recording, called by the staff before the deadline

def record(event: int, payload: dict) -> Path:
    """Write this gameweek's recommendation. Called from the main report run."""
    RECS.mkdir(exist_ok=True)
    path = RECS / f"gw{event}.json"
    payload.setdefault("event", event)
    payload.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
    payload.setdefault("actual", None)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return path


def declare(event: int, said: str, choice: str | None = None) -> Path:
    """
    Log Ido's own line about what he intends to do, before the deadline.

    The API is still the ground truth once the deadline passes - if he changes
    his mind afterwards, `compare()` reads the real picks and this stays on
    record as what he said at the time. Its value is the *why*, which no
    endpoint reports: a divergence with a stated reason is a different data
    point from one without.
    """
    path = RECS / f"gw{event}.json"
    if not path.exists():
        raise SystemExit(f"No recommendation recorded for GW{event}.")
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["manager_reply"] = {
        "said": said,
        "declared_choice": choice,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(rec, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# scoring, called by the review run after the gameweek

def _deadline_passed(event: int) -> bool:
    ev = next((e for e in fpl.events() if e["id"] == event), None)
    if ev is None:
        raise SystemExit(f"Gameweek {event} not found.")
    dl = datetime.fromisoformat(ev["deadline_time"].replace("Z", "+00:00"))
    return datetime.now(timezone.utc) >= dl


def _points_by_id(event: int) -> dict[int, int]:
    live = fpl.live(event)
    return {e["id"]: e["stats"]["total_points"] for e in live["elements"]}


def _points_by_name(event: int, owned: list[int] = ()) -> dict[str, int]:
    """
    web_name -> points actually scored in this gameweek.

    web_name is not unique (two Thomases, two Hendersons, two Palmers...), and
    a plain dict lets whichever comes last win. That scored Sorba Thomas's 7
    for Ido's Bobby Thomas in GW6. Players Ido actually picked are known by id,
    so they take precedence; any other duplicated name is listed in
    `AMBIGUOUS` so the caller can say so instead of guessing silently.
    """
    by_id = _points_by_id(event)
    out, seen = {}, {}
    for pid, p in fpl.players().items():
        n = fpl.player_name(p)
        seen.setdefault(n, []).append(pid)
        out[n] = by_id.get(pid, 0)
    for pid in owned:
        out[fpl.player_name(fpl.players()[pid])] = by_id.get(pid, 0)
    owned_names = {fpl.player_name(fpl.players()[pid]) for pid in owned}
    AMBIGUOUS.clear()
    AMBIGUOUS.update(n for n, ids in seen.items()
                     if len(ids) > 1 and n not in owned_names)
    return out


AMBIGUOUS: set[str] = set()


def _actual(event: int) -> dict:
    """What Ido really fielded, read back from the API after the deadline."""
    raw = fpl.picks(TEAM_ID, event)
    names = {pid: fpl.player_name(p) for pid, p in fpl.players().items()}
    xi, bench, cap, vice = [], [], None, None
    for pick in sorted(raw["picks"], key=lambda p: p["position"]):
        name = names.get(pick["element"], f"#{pick['element']}")
        (xi if pick["position"] <= 11 else bench).append(name)
        if pick.get("is_captain"):
            cap = name
        if pick.get("is_vice_captain"):
            vice = name
    h = raw.get("entry_history", {})
    return {
        "xi": xi, "bench": bench, "captain": cap, "vice_captain": vice,
        "points": h.get("points"), "hits": h.get("event_transfers_cost"),
        "transfers": h.get("event_transfers"),
        "bench_points": h.get("points_on_bench"),
        "chip": raw.get("active_chip"),
        "ids": [p["element"] for p in raw["picks"]],
    }


def _points(v) -> float | None:
    """A forecast recorded as a number, or as {"points": n, ...}."""
    if isinstance(v, dict):
        v = v.get("points")
    return v if isinstance(v, (int, float)) else None


def _chip(name: str | None) -> str | None:
    """'Triple Captain', 'TC', '3xc' -> '3xc'; 'Bench Boost' -> 'bboost'."""
    n = (name or "").lower().replace(" ", "").replace("_", "")
    if n in ("3xc", "tc", "triplecaptain"):
        return "3xc"
    if n in ("bboost", "bb", "benchboost"):
        return "bboost"
    return n or None


def _score(xi: list[str], captain: str, pts: dict[str, int], *,
           chip: str | None = None, bench: list[str] | None = None) -> tuple[int, list]:
    """
    XI score with the captain counted twice. Auto-subs are NOT modelled.

    A chip changes the sum: Triple Captain counts the captain three times and
    Bench Boost adds the four on the bench. Free Hit and Wildcard change only
    who is in the side, which the XI already carries.

    The returned detail carries each player's OWN points, undoubled - the
    captain's armband belongs to the total, not to him. Reporting a doubled
    figure next to his name reads as if he scored it.
    """
    chip = _chip(chip)
    mult = 3 if chip == "3xc" else 2
    total, detail = 0, []
    for n in xi:
        raw = pts.get(n, 0)
        total += raw * mult if n == captain else raw
        detail.append((n, raw))
    if chip == "bboost":
        total += sum(pts.get(n, 0) for n in bench or [])
    return total, detail


def compare(event: int, *, dry: bool = False) -> dict:
    path = RECS / f"gw{event}.json"
    if not path.exists():
        raise SystemExit(f"No recommendation recorded for GW{event} "
                         f"({path} missing). Nothing to compare.")
    if not _deadline_passed(event):
        raise SystemExit(
            f"GW{event}'s deadline has not passed. The API would still return "
            f"the previous gameweek's picks - refusing to score.")

    rec = json.loads(path.read_text(encoding="utf-8"))
    act = _actual(event)
    pts = _points_by_name(event, act.pop("ids"))

    act_score, _ = _score(act["xi"], act["captain"], pts,
                          chip=act["chip"], bench=act["bench"])
    played = set(act["xi"])

    # The status quo is scored alongside the options. Doing nothing is one of
    # the real choices on the table, so leaving it out would make "closest
    # option" claim he followed advice he actually declined.
    candidates = list(rec.get("options", []))
    sq = rec.get("status_quo")
    if sq:
        candidates.append({**sq, "name": "DO NOTHING"})

    rows = []
    for opt in candidates:
        score, detail = _score(opt["xi"], opt["captain"], pts,
                               chip=opt.get("chip"), bench=opt.get("bench"))
        diff = played.symmetric_difference(set(opt["xi"]))
        # The staff's own forecast for this option, checked against the result
        # (Ido, 29 Oct 2026: we must learn whether the predictions are right).
        predicted = _points(opt.get("predicted_points"))
        best, worst = _points(opt.get("best_case")), _points(opt.get("worst_case"))
        rows.append({
            "name": opt["name"],
            "recommended": opt["name"] == rec.get("recommended"),
            "score": score,
            "predicted": predicted,
            "forecast_error": score - predicted if predicted is not None else None,
            "within_best_worst": (worst <= score <= best)
                                 if best is not None and worst is not None else None,
            "vs_actual": score - act_score,
            "players_different": len(diff) // 2,
            "captain_matched": opt["captain"] == act["captain"],
            "differences": sorted(diff),
            # per-player, so the review can show where the difference came
            # from rather than only that there was one
            "players": [{"name": n, "points": p} for n, p in detail],
            "bench": [{"name": n, "points": pts.get(n, 0)}
                      for n in opt.get("bench", [])],
        })

    named = {n for o in candidates for n in o["xi"] + o.get("bench", [])}
    unsure = sorted(named & AMBIGUOUS)

    closest = min(rows, key=lambda r: r["players_different"]) if rows else None
    left_on_bench = sum(pts.get(n, 0) for n in act["bench"])
    _, act_detail = _score(act["xi"], act["captain"], pts)

    result = {
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "actual": act,
        "actual_xi_score": act_score,
        "actual_players": [{"name": n, "points": p} for n, p in act_detail],
        "actual_bench": [{"name": n, "points": pts.get(n, 0)}
                         for n in act["bench"]],
        "points_left_on_bench": left_on_bench,
        "best_option": max(rows, key=lambda r: r["score"])["name"] if rows else None,
        "options": rows,
        # "Followed" means the same eleven AND the same armband. The captain is
        # half the decision; an identical XI captained differently is a
        # different team, and scored like one.
        "followed": closest["name"] if closest and
                    closest["players_different"] == 0 and
                    closest["captain_matched"] else None,
        "closest_option": closest["name"] if closest else None,
        # option players whose web_name belongs to more than one footballer
        # and who are not in Ido's own picks: their points may be the wrong man's
        "ambiguous_names": unsure,
    }

    if not dry:
        rec["actual"] = result
        path.write_text(json.dumps(rec, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    return result


def _print(event: int, r: dict) -> None:
    a = r["actual"]
    print(f"\nGW{event} - recommended versus actual\n" + "=" * 52)
    print(f"Ido fielded   : {a['captain']} (C), {a['transfers']} transfer(s), "
          f"{a['hits']} pts of hits")
    # entry_history "points" is the gameweek total BEFORE hits; the transfer
    # cost is carried separately and comes off the season total.
    net = None if a["points"] is None else a["points"] - (a["hits"] or 0)
    print(f"Official score: {a['points']} gross, {net} after hits   "
          f"(recomputed XI {r['actual_xi_score']}, "
          f"bench {r['points_left_on_bench']})")
    if r["followed"]:
        print(f"He played the {r['followed']} option exactly.")
    elif r["closest_option"]:
        c = next(o for o in r["options"] if o["name"] == r["closest_option"])
        why = "same XI, different captain" if c["players_different"] == 0 \
              else f"{c['players_different']} player(s) different"
        print(f"Closest option: {r['closest_option']} ({why})")
    if r.get("best_option"):
        print(f"Best option in hindsight: {r['best_option']}")
    print()
    for o in r["options"]:
        tag = " <- recommended" if o["recommended"] else ""
        sign = "+" if o["vs_actual"] > 0 else ""
        print(f"  {o['name']:<14} {o['score']:>4} pts   "
              f"{sign}{o['vs_actual']:>3} vs actual   "
              f"{o['players_different']} player(s) different{tag}")
        if o["differences"]:
            print(f"                 {', '.join(o['differences'])}")

    # Per-player, so it is visible WHERE an option gained or lost its points -
    # a total on its own never shows which decision actually mattered.
    names = [p["name"] for p in r["actual_players"]] + \
            [p["name"] for p in r["actual_bench"]]
    pts = {p["name"]: p["points"]
           for p in r["actual_players"] + r["actual_bench"]}
    started = {o["name"]: {p["name"] for p in o["players"]} for o in r["options"]}
    heads = [o["name"][:4] for o in r["options"]]

    print("\n  every player and his own points, and who started him"
          "\n  (* = captain; his points count twice in the totals above)")
    print(f"  {'':<18}{'pts':>4}   " + "  ".join(f"{h:>4}" for h in heads))
    for n in names:
        star = "*" if n == a["captain"] else " "
        marks = "  ".join(f"{'   S' if n in started[o['name']] else '   -'}"
                          for o in r["options"])
        benched = " (benched)" if n in {p["name"] for p in r["actual_bench"]} \
                  else ""
        print(f"  {n + star:<18}{pts.get(n, 0):>4}   {marks}{benched}")

    if r.get("ambiguous_names"):
        print("\nWARNING: these option names match more than one player and are "
              "not in Ido's picks, so their points may be the wrong man's: "
              + ", ".join(r["ambiguous_names"]))
    print("\nNote: option scores are raw XI totals with the captain doubled. "
          "Auto-substitutions are not modelled, so an option whose player "
          "blanked may flatter the actual team slightly.")


def main(argv: list[str]) -> int:
    # Player names carry accents (João, Sávio, Højlund) and this machine's
    # console defaults to a Hebrew codepage that cannot encode them. Without
    # this the tool dies mid-report on a UnicodeEncodeError - and since the
    # Tuesday review run starts by calling it, that killed the whole review.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    if not argv or not argv[0].isdigit():
        print(__doc__)
        return 1
    event = int(argv[0])

    if "--said" in argv:
        i = argv.index("--said")
        said = argv[i + 1] if len(argv) > i + 1 else ""
        choice = None
        if "--choice" in argv:
            j = argv.index("--choice")
            choice = argv[j + 1] if len(argv) > j + 1 else None
        print("logged to", declare(event, said, choice))
        return 0

    dry = "--dry" in argv
    r = compare(event, dry=dry)
    _print(event, r)
    if not dry:
        print(f"\nWritten back to {RECS / f'gw{event}.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
