"""
Which reports are due right now, measured from the deadline rather than the week.

The first version of this project ran its reports on fixed weekdays - planning
Wednesday, main report Friday, review Tuesday. That is wrong for seven of this
season's thirty-eight gameweeks. Five have midweek deadlines (GW13, 18, 20, 25,
28) and two are Sundays, and for GW18 the deadline falls on Tuesday 29 December
at 18:00 - a Friday report would have arrived three days after Ido could act on
it, and the Tuesday review would have run two hours *before* the gameweek it was
reviewing had even started.

So nothing here is scheduled by weekday. One task runs every few hours, asks
this module what is due, and runs it. The FPL calendar moves; a fixed timetable
silently stops matching it.

    python due.py              what should run now, one per line
    python due.py --why        the same, with the reasoning
    python due.py --done main  record that the main report has run
    python due.py --status     the full picture

Windows for each report, in hours before the deadline
-----------------------------------------------------
    planning   96 - 42   the landscape, several days out - but never before the
                         previous gameweek has been reviewed
    main       26 - 1    the decision, close enough to be current. It normally
                         lands at the 26h end; the window stays open to the
                         deadline only so a failed run can still be rescued
    check       always   self-silencing; speaks only near a deadline or when
                         health.py finds something
    review     after the gameweek is scored, once

Each report fires on the first pass that falls inside its window, so the upper
bound decides when it actually arrives. The main report opens at 26 hours rather
than 36 deliberately: 36 put it at three in the morning before a Saturday
deadline, and it wants to land while Ido is awake, after Friday's press
conferences, with a full day still left to act on it.

The windows are wide because the trigger runs every few hours rather than
continuously, and because a window has to survive the PC being asleep for a
stretch. Each report is recorded once it has run for a gameweek, so a wide
window cannot produce the same mail twice.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import fpl

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "data" / "runs_done.json"

# (type, earliest hours before deadline, latest hours before deadline)
WINDOWS = [
    ("planning", 96, 42),
    # The late bound is 1, not 10, on purpose.
    #
    # It used to be 10. On the morning of the GW5 deadline the main report
    # failed twice because the Claude login had expired, and by the next pass
    # three hours later the deadline was 8.5 hours away - outside the window.
    # The dispatcher had correctly left it unrecorded "so it will be retried",
    # and then never retried it, because the window it was waiting for had
    # already shut. Ido got no report at all for that gameweek.
    #
    # Nothing is lost by widening it. A report fires on the FIRST pass inside
    # its window, so the 26h upper bound still decides when it normally lands;
    # the lower bound only ever matters for a report that has not gone out yet.
    # Late advice before a deadline beats no advice.
    ("main", 26, 1),
]


def load() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save(state: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def mark(kind: str, gw: int) -> None:
    state = load()
    state[kind] = gw
    save(state)


def last_scored_gw() -> int | None:
    """
    The most recent gameweek whose points are final.

    `finished` alone is not enough: FPL sets it when the last match ends but
    keeps adjusting bonus and stats for a while afterwards, and `data_checked`
    is the flag that says the week is actually settled. Reviewing before that
    means scoring the staff's advice against numbers still moving.
    """
    done = [e["id"] for e in fpl.events()
            if e.get("finished") and e.get("data_checked")]
    return max(done) if done else None


def due(explain: bool = False) -> list[tuple[str, str]]:
    state = load()
    out: list[tuple[str, str]] = []

    ev, hours = fpl.deadline()
    gw = ev["id"] if ev else None

    scored_gw = last_scored_gw()

    for kind, early, late in WINDOWS:
        if gw is None or hours is None:
            continue
        if state.get(kind) == gw:
            if explain:
                out.append(("", f"{kind}: already run for GW{gw}"))
            continue

        # The planning brief is the Historian's lesson applied forward, so it
        # must never overtake the review it is supposed to learn from.
        #
        # The test is the gameweek immediately before the one being planned,
        # not the last one that happens to be scored. Those differ exactly when
        # it matters: planning for GW5 fell due while GW4 was still being
        # played, and since GW3 was scored and reviewed, a rule written against
        # "the last scored gameweek" waved it straight through - planning the
        # next week before anyone had looked at the one just gone.
        if kind == "planning" and gw > 1 and state.get("review") != gw - 1:
            if explain:
                out.append(("", f"planning: GW{gw} waits for the GW{gw - 1} "
                                "review, which has not run yet"))
            continue

        if late <= hours <= early:
            out.append((kind, f"{kind}: GW{gw} deadline is {hours:.0f}h away "
                              f"(window {early}-{late}h)"))
        elif explain:
            where = "too early" if hours > early else "window has passed"
            out.append(("", f"{kind}: GW{gw} deadline {hours:.0f}h away - {where}"))

    if scored_gw is not None and state.get("review") != scored_gw:
        out.append(("review", f"review: GW{scored_gw} is scored and not yet reviewed"))
    elif explain:
        out.append(("", f"review: GW{scored_gw} already reviewed"
                        if scored_gw else "review: no completed gameweek yet"))

    # The check is cheap and silences itself - it only wakes the staff when a
    # deadline is close or health.py finds something, so it can simply always
    # be offered and decide for itself.
    out.append(("check", "check: always offered; it exits quietly on its own"))
    return out


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    if "--done" in argv:
        i = argv.index("--done")
        if len(argv) <= i + 1:
            print("usage: python due.py --done <planning|main|check|review>")
            return 2
        kind = argv[i + 1]
        ev, _ = fpl.deadline()
        gw = last_scored_gw() if kind == "review" else (ev["id"] if ev else None)
        if gw is None:
            print(f"no gameweek to record {kind} against")
            return 1
        mark(kind, gw)
        print(f"recorded {kind} as done for GW{gw}")
        return 0

    if "--status" in argv:
        ev, hours = fpl.deadline()
        print(f"next deadline : GW{ev['id']} in {hours:.1f}h"
              if ev else "next deadline : none")
        print(f"last scored   : GW{last_scored_gw()}")
        print(f"already run   : {load() or 'nothing yet'}")
        print()
        for kind, why in due(explain=True):
            print(("DUE  " if kind else "     ") + why)
        return 0

    explain = "--why" in argv
    for kind, why in due(explain=explain):
        if not kind:
            if explain:
                print("     " + why)
            continue
        print(f"{kind}\t{why}" if explain else kind)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
