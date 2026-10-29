"""
How good is the season, measured against outside yardsticks - not just against
doing nothing.

`outcome.py` compares the staff's advice with "do nothing", which only shows
that changes beat no changes. On 29 Oct 2026 Ido asked for a stronger check:
"we need to step up our checking game". So every review also measures, per
gameweek:

- his points (net of hits) against the TOP 100 average - the main yardstick
  (Ido, 29 Oct 2026): real teams, picked before the deadline, by the managers
  he wants to play like. Taken from `elite.py behaviour`, i.e. the current top 100.
- his points against the world average
- his share of FPL's Team of the Week - kept only as the ceiling: the best
  legal XI in hindsight, with no captain and no bench, which nobody could have
  picked in advance
- his world rank: overall, and for that gameweek alone
- the gap to each league rival, and how it moved

and compares the weeks before the staff existed (GW1-3) with the weeks since
(GW4 on), so the review can say in one line whether the system is helping.

Only gameweeks FPL has marked `data_checked` are counted - before that, bonus
points and the Team of the Week can still change.

CLI:
    python benchmark.py            the table and the summary lines
    python benchmark.py --json     the same, machine-readable
"""
from __future__ import annotations

import config
import json
import sys

import elite
import fpl
import gap

ME = config.ENTRY_ID
STAFF_FROM = 4          # the first gameweek the staff advised on


def _top100() -> dict[int, float]:
    """The top 100's average points per gameweek, from the newest behaviour read."""
    if not elite.BEHAVIOUR.exists():
        return {}
    store = json.loads(elite.BEHAVIOUR.read_text(encoding="utf-8"))
    latest = store[max(store, key=lambda k: int(k[2:]))]
    return {w["gw"]: w["elite"]["points"] for w in latest["weeks"]}


def weeks() -> list[dict]:
    done = {e["id"]: e for e in fpl.events() if e.get("data_checked")}
    hist = {g["event"]: g for g in fpl.entry_history(ME)["current"]}
    top = _top100()
    players = fpl.bootstrap()["total_players"]
    rows = []
    for gw in sorted(set(done) & set(hist)):
        e, h = done[gw], hist[gw]
        net = h["points"] - h["event_transfers_cost"]
        dream = sum(p["points"] for p in fpl.get(f"dream-team/{gw}")["team"])
        rows.append({
            "gw": gw,
            "points": net,
            "top100": top.get(gw),
            "vs_top100": round(net - top[gw], 1) if gw in top else None,
            "average": e["average_entry_score"],
            "vs_average": net - e["average_entry_score"],
            "team_of_week": dream,
            "pct_of_totw": round(100 * net / dream) if dream else None,
            "gw_rank": h["rank"],
            # The week's score out of 10, from the numbers alone (Ido, 29 Oct
            # 2026): the share of all managers he beat that gameweek.
            "score10": round(10 * (1 - h["rank"] / players), 1),
            "overall_rank": h["overall_rank"],
        })
    return rows


def _mean(xs: list[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def summary(rows: list[dict]) -> dict:
    before = [r for r in rows if r["gw"] < STAFF_FROM]
    since = [r for r in rows if r["gw"] >= STAFF_FROM]
    split = lambda k: {"before": _mean([r[k] for r in before]),
                       "since": _mean([r[k] for r in since])}
    out = {
        "vs_top100": split("vs_top100"),
        "vs_average": split("vs_average"),
        "pct_of_totw": split("pct_of_totw"),
        "overall_rank": {"staff_start": before[-1]["overall_rank"] if before else None,
                         "now": rows[-1]["overall_rank"] if rows else None},
        "last": rows[-1] if rows else None,
    }
    # League gaps: where they stood when the staff started, and now.
    sb = gap.scoreboard()
    start_row = next((r for r in sb["rows"] if r["gw"] == STAFF_FROM - 1), None)
    out["league"] = {
        name: {"staff_start": start_row["rivals"][name]["gap"] if start_row else None,
               "now": t["gap"], "moved_1": t["moved_1"]}
        for name, t in sb["trend"].items()
    }
    return out


def _m(n: int | None) -> str:
    return "-" if n is None else f"{n / 1e6:.2f}M"


def _s(x: float | None) -> str:
    return "-" if x is None else f"{x:+.1f}"


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    rows = weeks()
    s = summary(rows)
    if "--json" in argv:
        print(json.dumps({"weeks": rows, "summary": s}, ensure_ascii=False, indent=1))
        return 0

    print("GW  pts  score  top100  vs top100  world avg  vs avg  TotW  %TotW   GW rank  world rank")
    for r in rows:
        if r["gw"] == STAFF_FROM:
            print("--- staff advising from here " + "-" * 53)
        top = "-" if r["top100"] is None else f"{r['top100']:.1f}"
        print(f"{r['gw']:<3} {r['points']:>3}  {r['score10']:>5}  {top:>6}  {_s(r['vs_top100']):>9}  "
              f"{r['average']:>9}  {r['vs_average']:>+6}  {r['team_of_week']:>4}  "
              f"{r['pct_of_totw']:>4}%  {_m(r['gw_rank']):>8}  {_m(r['overall_rank']):>9}")
    print("\nPoints are net of hits. top100 = average of the current top 100 (elite.py behaviour).")
    print("TotW = FPL's Team of the Week: the hindsight ceiling (best legal XI, no captain).")
    print("score = the week out of 10: the share of all managers he beat that gameweek.\n")

    vt, va, pt, rk = s["vs_top100"], s["vs_average"], s["pct_of_totw"], s["overall_rank"]
    print(f"Against the top 100 average: {_s(vt['before'])} a week before the staff, {_s(vt['since'])} since.")
    print(f"Against the world average: {_s(va['before'])} a week before the staff, {_s(va['since'])} since.")
    print(f"Share of Team of the Week (ceiling): {pt['before']}% before, {pt['since']}% since.")
    print(f"World rank: {_m(rk['staff_start'])} when the staff started, {_m(rk['now'])} now.")
    for name, g in s["league"].items():
        mv = "" if g["moved_1"] is None else f" (last week {g['moved_1']:+d})"
        print(f"Gap to {name}: {g['staff_start']:+d} when the staff started, {g['now']:+d} now{mv}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
