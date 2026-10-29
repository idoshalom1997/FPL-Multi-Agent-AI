"""
Transfers and chips across the mini-league, after a gameweek.

Ido asked (29 Oct 2026) for the review mail to carry one small table, owned by
the Rules Enforcer: for each of the four managers, the transfers made and any
chip played this gameweek, the free transfers each holds for the next one, and
the chips each has left. Free transfers are not published by the API, so they
are rebuilt here from each manager's history:

- GW1 is unlimited; from GW2 everyone has 1.
- A normal week: next = min(5, unused + 1).
- A Wildcard or Free Hit week: the free transfers are kept but NOT topped up
  (checked against Ido's GW6 Wildcard and his -8 in GW8).

The rebuild is checked against reality: every week a manager took a hit, the
hit this model predicts must equal the hit FPL charged. A mismatch is printed,
because it means FPL changed a rule (or gave a bonus transfer) and the free
transfer counts can no longer be trusted.

Chips come in two sets (GW1-19 and GW20-38, from bootstrap); "left" means the
chips of the set that covers the next gameweek, not yet played inside it.

CLI:
    python league_status.py           the table, after the last finished gameweek
    python league_status.py --html    the same table as HTML for the review mail
"""
from __future__ import annotations

import sys

import fpl
import gap

MAX_FT = 5
CHIP_NAMES = {"wildcard": "WC", "freehit": "FH", "bboost": "BB", "3xc": "TC"}


def free_transfers(history: dict) -> tuple[int, list[str]]:
    """Free transfers held for the next gameweek, and any weeks the model got wrong."""
    chips = {c["event"]: c["name"] for c in history.get("chips", [])}
    ft, problems = 1, []
    for g in history.get("current", []):
        gw = g["event"]
        if gw == 1:
            continue
        chip = chips.get(gw)
        if chip in ("wildcard", "freehit"):
            continue                      # kept, not topped up
        used = g["event_transfers"]
        predicted_hit = max(0, used - ft) * 4
        if predicted_hit != g["event_transfers_cost"]:
            problems.append(f"GW{gw}: model says -{predicted_hit}, FPL charged "
                            f"-{g['event_transfers_cost']}")
        ft = min(MAX_FT, max(0, ft - used) + 1)
    return ft, problems


def chips_left(history: dict, next_gw: int) -> list[str]:
    used = [(c["name"], c["event"]) for c in history.get("chips", [])]
    left = []
    for c in fpl.bootstrap()["chips"]:
        if not c["start_event"] <= next_gw <= c["stop_event"]:
            continue
        played = any(n == c["name"] and c["start_event"] <= e <= c["stop_event"]
                     for n, e in used)
        if not played:
            left.append(CHIP_NAMES.get(c["name"], c["name"]))
    return left


def table() -> dict:
    hist_all = {m["entry"]: (m["name"], fpl.entry_history(m["entry"]))
                for m in gap.managers()}
    last = max(g["event"] for _, h in hist_all.values() for g in h["current"])
    rows, problems = [], []
    for entry, (name, h) in hist_all.items():
        week = next(g for g in h["current"] if g["event"] == last)
        chip = next((c["name"] for c in h.get("chips", []) if c["event"] == last), None)
        ft, bad = free_transfers(h)
        problems += [f"{name} {b}" for b in bad]
        rows.append({
            "name": name,
            "transfers": week["event_transfers"],
            "hit": week["event_transfers_cost"],
            "chip": CHIP_NAMES.get(chip, chip) if chip else None,
            "free_transfers_next": ft,
            "chips_left": chips_left(h, last + 1),
            "total": week["total_points"],
        })
    rows.sort(key=lambda r: -r["total"])
    return {"gw": last, "rows": rows, "problems": problems}


def _transfers(r: dict) -> str:
    if r["chip"] in ("WC", "FH"):
        return f"({r['chip']})"
    return f"{r['transfers']}" + (f" (-{r['hit']})" if r["hit"] else "")


def html(t: dict) -> str:
    th = "padding:7px 10px;text-align:{}"
    head = "".join(f'<td style="{th.format(a)}">{h}</td>' for h, a in
                   (("MANAGER", "left"), (f"TRANSFERS GW{t['gw']}", "center"),
                    (f"CHIP GW{t['gw']}", "center"), (f"FREE TRANSFERS GW{t['gw'] + 1}", "center"),
                    ("CHIPS LEFT", "left")))
    body = ""
    for r in t["rows"]:
        bold = "font-weight:700;" if r["name"].startswith("Ido") else ""
        cells = (r["name"], _transfers(r), r["chip"] or "-", r["free_transfers_next"],
                 " ".join(r["chips_left"]) or "none")
        aligns = ("left", "center", "center", "center", "left")
        body += "<tr style=\"border-bottom:1px solid #e3e8ef\">" + "".join(
            f'<td style="{bold}{th.format(a)}">{c}</td>' for c, a in zip(cells, aligns)) + "</tr>"
    return ('<table style="border-collapse:collapse;width:100%;font-size:14px">'
            '<tr style="background:#0A1B2E;color:#9fb3c8;font-size:11px;letter-spacing:.06em">'
            f"{head}</tr>{body}</table>")


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    t = table()
    if "--html" in argv:
        print(html(t))
    else:
        print(f"Mini-league after GW{t['gw']}: transfers and chips\n")
        print(f"{'manager':<16}{'transfers':>11}{'chip':>6}{'free next':>11}  chips left")
        for r in t["rows"]:
            print(f"{r['name']:<16}{_transfers(r):>11}{r['chip'] or '-':>6}"
                  f"{r['free_transfers_next']:>11}  {' '.join(r['chips_left']) or 'none'}")
    if t["problems"]:
        print("\nWARNING - free-transfer model disagrees with FPL's charged hits, so the "
              "free-transfer counts may be wrong:", file=sys.stderr)
        for p in t["problems"]:
            print(f"  {p}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
