"""
The gap, gameweek by gameweek - the scoreboard the season plan is measured on.

Ido's goal is first place in mini-league config.LEAGUE_ID, so the number that matters is
the gap to each of the three rivals and whether it is shrinking fast enough.
This prints, from the live API (never from a stored table):

- every finished gameweek: Ido's points against each rival's, net of hits, and
  the gap after it
- the trend: how the gap to each rival moved over the last 1, 3 and 5 weeks
- the pace needed: points per gameweek Ido must outscore each rival by, from
  here to GW38, to finish level
- what Ido chose against what the staff advised, from recommendations/gw*.json:
  which option he followed, and what BALANCED and DIFFERENTIAL would have scored

Inputs for the gap committee (Data Scientist, Opposition Analyst, Historian) to
reason from - not a forecast.

CLI:
    python gap.py            the full scoreboard
    python gap.py --json     the same, machine-readable
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


def managers() -> list[dict]:
    st = fpl.get(f"leagues-classic/{LEAGUE}/standings")
    return [{"entry": r["entry"], "name": r["entry_name"]}
            for r in st["standings"]["results"]]


def history(entry: int) -> dict[int, dict]:
    h = fpl.entry_history(entry)
    chips = {c["event"]: c["name"] for c in h.get("chips", [])}
    out = {}
    for g in h.get("current", []):
        out[g["event"]] = {
            "net": g["points"] - g["event_transfers_cost"],
            "total": g["total_points"],
            "hits": g["event_transfers_cost"],
            "bench": g["points_on_bench"],
            "chip": chips.get(g["event"]),
        }
    return out


def choices() -> dict[int, dict]:
    """What Ido did against what the staff offered, per scored gameweek."""
    out = {}
    for f in sorted((ROOT / "recommendations").glob("gw*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        a = d.get("actual") or {}
        if not a:
            continue
        scores = {o["name"]: o.get("score") for o in a.get("options", [])}
        out[d["event"]] = {
            "followed": a.get("followed"),
            "closest": a.get("closest_option"),
            "actual": a.get("actual_xi_score"),
            "options": scores,
        }
    return out


def scoreboard() -> dict:
    mans = managers()
    hist = {m["entry"]: history(m["entry"]) for m in mans}
    mine = hist[ME]
    gws = sorted(mine)
    last = gws[-1] if gws else 0
    left = 38 - last
    rivals = [m for m in mans if m["entry"] != ME]

    rows = []
    for gw in gws:
        row = {"gw": gw, "ido": mine[gw]["net"], "ido_chip": mine[gw]["chip"],
               "ido_hits": mine[gw]["hits"], "ido_bench": mine[gw]["bench"], "rivals": {}}
        for r in rivals:
            h = hist[r["entry"]].get(gw)
            if h:
                row["rivals"][r["name"]] = {"net": h["net"], "chip": h["chip"],
                                            "gap": mine[gw]["total"] - h["total"]}
        rows.append(row)

    trend = {}
    for r in rivals:
        gaps = [row["rivals"][r["name"]]["gap"] for row in rows if r["name"] in row["rivals"]]
        now = gaps[-1] if gaps else 0
        trend[r["name"]] = {
            "gap": now,
            "moved_1": now - gaps[-2] if len(gaps) > 1 else None,
            "moved_3": now - gaps[-4] if len(gaps) > 3 else None,
            "moved_5": now - gaps[-6] if len(gaps) > 5 else None,
            "pace_needed": round(-now / left, 2) if left and now < 0 else 0,
        }
    return {"last_gw": last, "gws_left": left, "rows": rows, "trend": trend,
            "choices": choices()}


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sb = scoreboard()
    if "--json" in argv:
        print(json.dumps(sb, ensure_ascii=False, indent=1))
        return 0

    names = list(sb["trend"])
    print(f"After GW{sb['last_gw']} - {sb['gws_left']} gameweeks left. Gap = Ido minus rival.\n")
    print("GW   Ido  " + "".join(f"| {n.split()[0][:8]:<8} pts  gap " for n in names) + "| Ido chose: actual / BAL / DIFF")
    for row in sb["rows"]:
        line = f"{row['gw']:<4} {row['ido']:>3}"
        line += f"{'*' if row['ido_chip'] else ' '}"
        for n in names:
            r = row["rivals"].get(n)
            line += (f"| {'':<8} {r['net']:>3}{'*' if r['chip'] else ' '}{r['gap']:>4} "
                     if r else f"| {'':<18}")
        c = sb["choices"].get(row["gw"])
        if c:
            o = c["options"]
            line += (f"| {c['followed'] or 'own (closest ' + str(c['closest']) + ')'} "
                     f"{c['actual']} / {o.get('BALANCED', '-')} / {o.get('DIFFERENTIAL', '-')}")
        print(line)
    print("\n* = chip played that week. Points are net of hits.\n")
    for n, t in sb["trend"].items():
        mv = lambda v: "  -" if v is None else f"{v:+d}"
        print(f"{n:<16} gap {t['gap']:>+4}   last 1 {mv(t['moved_1'])}  last 3 {mv(t['moved_3'])}  "
              f"last 5 {mv(t['moved_5'])}   need {t['pace_needed']:.2f} pts/GW more than him to draw level")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
