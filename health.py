"""
Pre-deadline sanity check: is the team file current, and did the reports run?

Two failures have already cost Ido something real. A stale `current_team.json`
made a report draw the wrong captain, and a crashed scheduled run meant no
report arrived at all for a weekend while a log nobody reads recorded the
failure. Both are silent. This makes them loud.

    python health.py           report findings, exit 2 if anything needs him
    python health.py --quiet   findings only, nothing when all is well
    python health.py --all     ignore the already-reported list, show everything

**This tool only ever reports.** It does not edit `current_team.json`, does not
touch his FPL team and could not if it wanted to - everything here is read from
public endpoints. Ido's standing rule is that the staff advise and he executes;
a checker that quietly corrected the file would be exactly the kind of thing he
has ruled out. If something is wrong, say so and stop.

What it genuinely cannot see
----------------------------
FPL publishes a manager's picks only after that gameweek's deadline. Before one,
his **starting XI, bench order and captain are invisible** to any public caller.
So a clean result here means *the fifteen players are right*, never *the team
sheet is right*. Every report says so rather than implying an all-clear.
"""
from __future__ import annotations

import config
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import fpl

TEAM_ID = config.ENTRY_ID
ROOT = Path(__file__).resolve().parent
TEAM_FILE = ROOT / "current_team.json"
LOG_DIR = ROOT / "logs"

# What the scheduler promises, so a report that never fired is distinguishable
# from one that fired and failed. Monday=0 ... Sunday=6.
EXPECTED_RUNS = [
    ("planning", "Planning brief", 2, 20),
    ("main",     "Main report",    4, 20),
    ("review",   "Review",         1, 20),
]

LOG_NAME = re.compile(r"^(planning|main|check|review)_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})\.log$")

# When to ask him for his team sheet. This has to beat the MAIN REPORT, not the
# deadline: the report is built about 24h out and is the thing that needs his XI
# and captain, so an ask at 30h gave him six hours' notice and an ask at 8h
# arrived after the report had already guessed. 48 hours puts the request a full
# day before the report that consumes it.
#
# The finding carries a key, so it is one email per gameweek rather than one per
# pass - without that, a 48-hour window and a three-hourly trigger would send
# sixteen identical requests.
URGENT_HOURS = 48

# Past run failures are reported once and then remembered. The failure does not
# go away by itself - re-raising it daily would turn one piece of news into a
# week of identical mail.
SEEN_FILE = ROOT / "data" / "health_reported.json"


class Finding:
    def __init__(self, level: str, text: str, detail: str = "", key: str = ""):
        self.level = level          # "!" needs him, "ok" informational
        self.text = text
        self.detail = detail
        self.key = key              # set = report once, then stay quiet

    def render(self) -> str:
        head = f"  {self.level:<3}{self.text}"
        if self.detail:
            pad = "\n      " + self.detail.replace("\n", "\n      ")
            return head + pad
        return head


# ----------------------------------------------------------- the team file

def expected_fifteen(upcoming_gw: int) -> tuple[set[str], list[str]]:
    held, moves = expected_fifteen_ids(upcoming_gw)
    return set(held.values()), moves


def expected_fifteen_ids(upcoming_gw: int) -> tuple[dict[int, str], list[str]]:
    """
    The fifteen players he should currently hold, from public data alone.

    Picks for the upcoming gameweek are not published yet, so this is the last
    published squad with any transfers already made for the upcoming gameweek
    applied on top. NOTE (23 Oct 2026): in practice FPL publishes transfers only
    after the deadline too, so before a deadline this is simply last week's
    fifteen. The check is therefore only conclusive after the deadline.
    """
    cur = fpl.current_event()
    base_gw = cur["id"] if cur else upcoming_gw - 1
    pl = fpl.players()
    names = {pl[i["element"]]["id"]: fpl.player_name(pl[i["element"]])
             for i in fpl.picks(TEAM_ID, base_gw)["picks"]}
    held = dict(names)

    moves = []
    for t in fpl.entry_transfers(TEAM_ID):
        if t.get("event") != upcoming_gw:
            continue
        out_id, in_id = t["element_out"], t["element_in"]
        out_name = fpl.player_name(pl[out_id]) if out_id in pl else f"#{out_id}"
        in_name = fpl.player_name(pl[in_id]) if in_id in pl else f"#{in_id}"
        held.pop(out_id, None)
        held[in_id] = in_name
        moves.append(f"{out_name} -> {in_name}")
    return held, moves


def load_seen() -> set[str]:
    if not SEEN_FILE.exists():
        return set()
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen(seen: set[str]) -> None:
    SEEN_FILE.parent.mkdir(exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=1), encoding="utf-8")


def check_team_file() -> list[Finding]:
    out: list[Finding] = []
    ev, hours = fpl.deadline()
    if not ev:
        return [Finding("ok", "No upcoming gameweek - nothing to check.")]
    gw = ev["id"]
    urgent = hours is not None and 0 <= hours <= URGENT_HOURS

    if not TEAM_FILE.exists():
        out.append(Finding("!", "current_team.json is missing.",
                           "Reports will fall back to the API, which before a "
                           "deadline still serves the PREVIOUS gameweek's team."))
        return out

    cfg = json.loads(TEAM_FILE.read_text(encoding="utf-8"))
    file_gw = cfg.get("event")

    if file_gw != gw:
        # Loud only once the deadline is close enough for him to do something
        # about it; before that it is a note, not an alarm.
        out.append(Finding(
            "!" if urgent else "ok",
            f"current_team.json describes GW{file_gw}; the upcoming "
            f"gameweek is GW{gw}."
            + ("" if urgent else f"  (deadline still {hours:.0f}h away - "
                                 "not urgent yet)"),
            f"Until you update it, the reports ignore it and fall back to the "
            f"API - which before the deadline still returns your GW{file_gw} "
            f"team, captain included. This is what put the wrong captain in a "
            f"report once already.",
            key=f"teamsheet:{gw}"))
    else:
        out.append(Finding("ok", f"current_team.json is marked for GW{gw}."))

    listed = set(cfg.get("starting_xi", [])) | set(cfg.get("bench", []))
    try:
        expected, moves = expected_fifteen(gw)
    except fpl.FPLError as exc:
        out.append(Finding("!", f"Could not read your squad from the API: {exc}"))
        return out

    if moves:
        out.append(Finding("ok", f"{len(moves)} transfer(s) recorded for GW{gw}: "
                                 + ", ".join(moves)))

    missing = expected - listed          # he owns them, the file omits them
    unknown = listed - expected          # the file lists players he does not own
    if missing or unknown:
        detail = []
        if missing:
            detail.append("not in the file: " + ", ".join(sorted(missing)))
        if unknown:
            detail.append("in the file but not in your squad: "
                          + ", ".join(sorted(unknown)))
        # FPL does NOT publish a manager's transfers before the deadline (checked
        # 23 Oct 2026 across all four entries in the league: none showed a GW8
        # transfer at 09:00 UTC on deadline day). So before a deadline the API's
        # fifteen is last week's, and a file he gave us for THIS gameweek, after
        # he made his transfers, is expected to differ from it. That is a note,
        # not an alarm - the alarm fired three times in one day for a correct
        # file. A file recorded for an earlier gameweek is still a real finding.
        if file_gw == gw and cfg.get("_recorded"):
            out.append(Finding("ok", "The fifteen in the file differ from the last "
                                     "published squad - expected if these are "
                                     f"your GW{gw} transfers, which FPL hides until "
                                     "the deadline. If you have NOT made them, "
                                     "the file is wrong.", "\n".join(detail)))
        else:
            out.append(Finding("!", "current_team.json does not match the fifteen "
                                    "players you actually own.", "\n".join(detail)))
    elif file_gw == gw:
        out.append(Finding("ok", "All fifteen players in the file match your "
                                 "actual squad."))

    n_xi, n_bench = len(cfg.get("starting_xi", [])), len(cfg.get("bench", []))
    if n_xi != 11 or n_bench != 4:
        out.append(Finding("!", f"The file lists {n_xi} starters and {n_bench} "
                                "substitutes; it should be 11 and 4."))

    # His XI, bench order and captain cannot be read from anywhere - FPL
    # publishes picks only after the deadline and retired its password login.
    # team_update.py records what he tells us; say which it is.
    recorded = cfg.get("_recorded")
    if recorded and file_gw == gw:
        out.append(Finding("ok", f"XI, bench order and captain recorded from "
                                 f"Ido on {recorded[:16].replace('T', ' ')}."))
    else:
        out.append(Finding(
            "!" if urgent else "ok",
            "His XI, bench order and captain are unknown for this gameweek.",
            "FPL publishes picks only after the deadline and has retired its "
            "password login, so he has to tell us. He should reply to this "
            "email with a screenshot of his Pick Team screen; the main "
            "report reads the reply and records it with team_update.py.",
            key=f"teamsheet:{gw}"))
    return out


# ------------------------------------------------------- the scheduled runs

def last_due(weekday: int, hour: int, now: datetime) -> datetime:
    """The most recent moment this weekly task should have run."""
    due = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    delta = (now.weekday() - weekday) % 7
    due -= timedelta(days=delta)
    if due > now:
        due -= timedelta(days=7)
    return due


def _log_times(kind: str | None = None) -> list[tuple[datetime, Path]]:
    if not LOG_DIR.exists():
        return []
    out = []
    for p in LOG_DIR.iterdir():
        m = LOG_NAME.match(p.name)
        if not m or (kind and m.group(1) != kind):
            continue
        # A -WhatIf run prints the prompt and sends nothing. Counting one as a
        # real run would mask a genuinely missing report, and counting it as a
        # failure invents one - it has no completion line because it never ran.
        try:
            if "WhatIf:" in p.read_text(encoding="utf-8", errors="replace"):
                continue
        except OSError:
            continue
        out.append((datetime.strptime(
            f"{m.group(2)} {m.group(3)}:{m.group(4)}:{m.group(5)}",
            "%Y-%m-%d %H:%M:%S"), p))
    return sorted(out)


def newest_log(kind: str) -> tuple[datetime, Path] | None:
    rows = _log_times(kind)
    return rows[-1] if rows else None


def check_runs() -> list[Finding]:
    out: list[Finding] = []

    # This no longer asks "did something run last Wednesday at eight".
    #
    # It used to. That question came from the first version of the project,
    # which ran its reports on fixed weekdays, and it survived here after the
    # scheduler itself moved to firing off the deadline instead. The result was
    # a checker permanently out of step with the thing it was checking: it
    # announced that the GW5 planning brief "did not run" when the brief had
    # gone out perfectly well, six hours before the invented slot. False alarms
    # of that kind are worse than none, because they teach him to skim past the
    # real ones.
    #
    # Whether a report is MISSING is now decided by check_report_delivered(),
    # which asks the only question that matters - is it in his inbox. What is
    # left here is the other half: of the runs that did happen, did any of them
    # break.
    for kind, label, _weekday, _hour in EXPECTED_RUNS:
        found = newest_log(kind)
        if not found:
            continue

        when, path = found
        text = path.read_text(encoding="utf-8", errors="replace")
        if "RUN FAILED" in text:
            reason = next((ln for ln in text.splitlines() if "RUN FAILED" in ln), "")
            out.append(Finding("!", f"{label} FAILED on {when:%a %d %b %H:%M}.",
                               f"{reason.strip()}\nlog: logs/{path.name}",
                               key=f"failed:{path.name}"))
        elif "run finished (exit 0)" in text:
            out.append(Finding("ok", f"{label} ran {when:%a %d %b %H:%M}."))
        elif "nothing to do" in text:
            out.append(Finding("ok", f"{label} ran {when:%a %d %b %H:%M} (quiet)."))
        else:
            out.append(Finding(
                "!", f"{label} started {when:%a %d %b %H:%M} but never finished.",
                f"No completion line in logs/{path.name}. It may have been "
                "killed, or the PC slept mid-run.",
                key=f"stalled:{path.name}"))
    return out


SENT_LOG = LOG_DIR / "sent.log"


def check_report_delivered() -> list[Finding]:
    """
    Did the main report for the UPCOMING gameweek actually reach his inbox?

    Everything else here judges a run by its log. That was not enough. On the
    GW5 deadline the main report failed twice at breakfast because the Claude
    login had expired, and this checker reported "all clear" at midday while no
    report existed at all - because it was still asking the old question, "did
    something run last Friday at eight", rather than the only one that matters:
    "is the advice for the next deadline in his inbox".

    So this measures delivery, not activity. The evidence is the receipt line
    send_report.ps1 writes when an email genuinely leaves the machine.
    """
    out: list[Finding] = []

    ev, hours = fpl.deadline()
    if ev is None or hours is None or hours < 0:
        return out
    gw = ev["id"]

    # Before the report is even due there is nothing to report on.
    if hours > 26:
        return out

    sent = ""
    if SENT_LOG.exists():
        sent = SENT_LOG.read_text(encoding="utf-8", errors="replace")
    delivered = any(("Main report" in line and f"GW{gw}" in line)
                    for line in sent.splitlines())

    if delivered:
        out.append(Finding("ok", f"Main report for GW{gw} was emailed."))
        return out

    # Two alerts at most: one when it is late, one when it is nearly too late.
    # He has a standing rule against a stream of small messages, so this must
    # not fire on every three-hourly pass.
    stage = "urgent" if hours <= 6 else "late"
    out.append(Finding(
        "!", f"NO MAIN REPORT HAS BEEN EMAILED FOR GW{gw} - "
             f"deadline in {hours:.0f}h.",
        "Nothing in logs/sent.log matches this gameweek, so the advice never\n"
        "reached the inbox however the run finished.\n"
        "Run it by hand now:  .\\run_report.ps1 -Type main\n"
        "Commonest cause: the Claude login has expired - check with\n"
        "claude /status, and sign in again if needed.",
        key=f"undelivered:{gw}:{stage}"))
    return out


# --------------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    quiet = "--quiet" in argv
    replay = "--all" in argv        # ignore the seen-list, show everything

    try:
        team = check_team_file()
        runs = check_runs() + check_report_delivered()
    except fpl.FPLError as exc:
        print(f"error: {exc}")
        return 1

    seen = set() if replay else load_seen()
    fresh = [f for f in team + runs if f.level == "!"
             and not (f.key and f.key in seen)]

    # Anything raised now is remembered, so it is news once rather than daily.
    newly_keyed = {f.key for f in fresh if f.key}
    if newly_keyed and not replay:
        save_seen(seen | newly_keyed)

    needs_him = fresh

    if quiet and not needs_him:
        return 0

    quieted = {f.key for f in team + runs
               if f.level == "!" and f.key and f.key in seen}
    sections = [("TEAM FILE", team), ("SCHEDULED REPORTS", runs)]
    for title, findings in sections:
        shown = [f for f in findings
                 if (not quiet or f.level == "!") and f.key not in quieted]
        if not shown:
            continue
        print(title)
        for f in shown:
            print(f.render())
        print()

    if needs_him:
        print(f"{len(needs_him)} thing(s) need you. Nothing here has been "
              "changed on your behalf and nothing will be.")
        return 2
    print("All clear.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
