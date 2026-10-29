"""
Are we playing the game right? Ido against his three rivals, season to date.

Ido asked (23 Oct 2026) for the gap committee to start from everything already
played: "lets them think about the conclusions of our decisions and our friends
in the mini league and see where we went wrong - also account on how we
transfer (if it goes well) and how they transfer, how do we use chips compare
to them - at the end of the day it's supposed to be about if we are playing the
game right!"

So this measures the four managers on the same five things, from the public
API only:

- **Transfers** - every transfer, scored as what the player bought made minus
  what the player sold made over that gameweek and the next two (fewer if not
  played yet), and the hits paid. Free Hit weeks are left out (the team
  reverts) and counted under chips instead; Wildcard weeks are counted
  separately because ten moves at once are a different decision.
- **Captaincy** - the captain's points, and the best captain he could have
  picked from his own starting XI that week.
- **Chips** - what each chip actually added: Triple Captain = one extra copy of
  the captain; Bench Boost = the bench's points; Free Hit = the week's score
  minus what the previous week's XI would have scored; Wildcard = the net of
  its transfers over three gameweeks.
- **Bench** - points left on the bench.
- **Hits** - points paid for extra transfers.

These are measurements for the staff to reason from, not a verdict. Auto-subs
are not modelled in the Free Hit comparison.

CLI:
    python season_review.py          summary table plus each manager's detail
    python season_review.py --json   everything, machine-readable
Writes data/season_review_gw<n>.json every run.
"""
from __future__ import annotations

import config
import json
import sys
from pathlib import Path

import fpl

LEAGUE = config.LEAGUE_ID
ME = config.ENTRY_ID
ROOT = Path(__file__).resolve().parent
SPAN = 3          # gameweeks a transfer is judged over: the week made and the next two


def finished_gws() -> list[int]:
    return [e["id"] for e in fpl.bootstrap()["events"] if e.get("finished")]


def build() -> dict:
    gws = finished_gws()
    last = gws[-1]
    pl = fpl.players()
    name = lambda pid: fpl.player_name(pl[pid]) if pid in pl else str(pid)
    pts = {g: {e["id"]: e["stats"]["total_points"] for e in fpl.live(g)["elements"]}
           for g in gws}

    def over(pid: int, g: int) -> int:
        return sum(pts[x].get(pid, 0) for x in range(g, min(g + SPAN, last + 1)))

    st = fpl.get(f"leagues-classic/{LEAGUE}/standings")
    mans = [{"entry": r["entry"], "name": r["player_name"]} for r in st["standings"]["results"]]
    out = {"last_gw": last, "span": SPAN, "managers": []}

    for m in mans:
        e = m["entry"]
        hist = fpl.entry_history(e)
        chips = {c["event"]: c["name"] for c in hist.get("chips", [])}
        weeks = {h["event"]: h for h in hist.get("current", [])}
        picks = {g: fpl.picks(e, g) for g in gws}

        captains, chip_rows = [], []
        for g in gws:
            pk = picks[g]["picks"]
            xi = [p for p in pk if p["position"] <= 11]
            cap = next((p for p in pk if p["is_captain"]), None)
            best = max(xi, key=lambda p: pts[g].get(p["element"], 0))
            cpts = pts[g].get(cap["element"], 0) if cap else 0
            captains.append({"gw": g, "captain": name(cap["element"]) if cap else None,
                             "points": cpts, "best_in_xi": name(best["element"]),
                             "best_points": pts[g].get(best["element"], 0),
                             "lost": pts[g].get(best["element"], 0) - cpts})
            chip = chips.get(g)
            if not chip:
                continue
            row = {"gw": g, "chip": chip}
            if chip == "3xc":
                row["added"] = cpts
            elif chip == "bboost":
                row["added"] = sum(pts[g].get(p["element"], 0) for p in pk if p["position"] > 11)
            elif chip == "freehit" and g - 1 in picks:
                prev = picks[g - 1]["picks"]
                would = sum(pts[g].get(p["element"], 0) * (2 if p["is_captain"] else 1)
                            for p in prev if p["position"] <= 11)
                row["added"] = weeks[g]["points"] - would
                row["note"] = "v the previous week's XI, no auto-subs"
            chip_rows.append(row)

        transfers, wildcard = [], []
        for t in fpl.entry_transfers(e):
            g = t["event"]
            if g not in pts or chips.get(g) == "freehit":
                continue
            gain = over(t["element_in"], g) - over(t["element_out"], g)
            row = {"gw": g, "out": name(t["element_out"]), "in": name(t["element_in"]),
                   "net": gain, "weeks_counted": min(SPAN, last - g + 1)}
            (wildcard if chips.get(g) == "wildcard" else transfers).append(row)
        for c in chip_rows:
            if c["chip"] == "wildcard":
                c["added"] = sum(r["net"] for r in wildcard)
                c["note"] = f"net of its {len(wildcard)} transfer records over up to {SPAN} GWs"

        hits = sum(w["event_transfers_cost"] for w in weeks.values())
        out["managers"].append({
            "name": m["name"], "entry": e, "is_ido": e == ME,
            "total": weeks[last]["total_points"] if last in weeks else None,
            "transfers": transfers, "wildcard_transfers": wildcard,
            "transfer_net": sum(r["net"] for r in transfers),
            "transfer_count": len(transfers), "hits": hits,
            "captains": captains,
            "captain_points": sum(c["points"] for c in captains),
            "captain_lost": sum(c["lost"] for c in captains),
            "chips": chip_rows,
            "bench_points": sum(w["points_on_bench"] for w in weeks.values()),
        })
    return out


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    data = build()
    (ROOT / "data" / f"season_review_gw{data['last_gw']}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if "--json" in argv:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0

    print(f"Season to GW{data['last_gw']} - transfers judged over {data['span']} GWs "
          f"(fewer for recent ones).\n")
    print(f"{'manager':<14} {'total':>5} {'transfers':>9} {'net':>5} {'hits':>5} "
          f"{'capt pts':>8} {'capt lost':>9} {'bench':>6}  chips (added)")
    for m in data["managers"]:
        chips = ", ".join(f"{c['chip']} GW{c['gw']} ({c.get('added', '?'):+})"
                          if isinstance(c.get("added"), int) else f"{c['chip']} GW{c['gw']}"
                          for c in m["chips"]) or "-"
        tag = " <-" if m["is_ido"] else ""
        print(f"{m['name'][:14]:<14} {m['total']:>5} {m['transfer_count']:>9} "
              f"{m['transfer_net']:>+5} {-m['hits']:>5} {m['captain_points']:>8} "
              f"{-m['captain_lost']:>9} {m['bench_points']:>6}  {chips}{tag}")
    print("\nnet = bought players' points minus sold players' points (Wildcard and Free Hit")
    print("weeks excluded, see chips). capt lost = points the best captain in his own XI")
    print("would have added. Full detail in data/season_review_gw<n>.json.\n")

    for m in data["managers"]:
        print(f"--- {m['name']}")
        print("  captains: " + ", ".join(f"GW{c['gw']} {c['captain']} {c['points']}"
                                         for c in m["captains"]))
        for t in m["transfers"]:
            print(f"  GW{t['gw']} {t['out']} -> {t['in']}  {t['net']:+d}"
                  + (f"  ({t['weeks_counted']} GW)" if t["weeks_counted"] < data["span"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
