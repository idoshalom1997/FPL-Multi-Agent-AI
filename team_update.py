"""
Record the team Ido says he is fielding, from his own words or his screenshot.

FPL retired its password login and now signs in through a browser flow, so
nothing here can read his pre-deadline team by itself. His starting XI, bench
order and captain are only knowable if he tells us - by replying to the Friday
email with a screenshot of his Pick Team screen, or just by saying it.

This is the safe way to write that down. It never guesses: every name is matched
against the fifteen players he actually owns, and the result is checked for
legality before anything is saved. A misread screenshot fails loudly instead of
quietly putting the wrong captain in a report, which is the exact failure this
whole area of the project exists to prevent.

    python team_update.py --xi "Verbruggen, De Cuyper, ..." \\
                          --bench "Roefs, Virgil, Calvert-Lewin, Maguire" \\
                          --captain "Joao Pedro" --vice "Wissa"

    python team_update.py --check --xi ... --bench ...   validate, write nothing

Names may be sloppy. Accents, initials and short forms all resolve - "Joao
Pedro", "VVD", "Bruno" - because they are matched only against his own fifteen,
which is a small enough set for that to be safe rather than a guess. Anything
ambiguous is an error, never a coin flip.

Who calls this
--------------
The agent running the Friday report, after reading his reply. It writes a file
in *this project* and touches nothing in his FPL account - the standing rule is
that Ido is the only one who changes his team, and reading what he told us and
writing it down is not changing it.
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import fpl
import health

ROOT = Path(__file__).resolve().parent
TEAM_FILE = ROOT / "current_team.json"

MAX_PER_CLUB = 3


def norm(s: str) -> str:
    """Strip accents, punctuation and case so 'João' matches 'Joao'."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.lower() if c.isalnum())


class Squad:
    """His fifteen, with lookup that tolerates how a person actually types."""

    def __init__(self, gw: int):
        # Match by id, not name: two players can share a web name
        # (Bobby Thomas DEF and Sorba Thomas MID both show as "Thomas").
        owned, _ = health.expected_fifteen_ids(gw)
        pl = fpl.players()
        tm = fpl.teams()
        self.rows = []
        for pid in owned:
            p = pl[pid]
            self.rows.append({
                "name": fpl.player_name(p),
                "pos": fpl.POSITIONS[p["element_type"]],
                "team": tm[p["team"]]["short_name"],
                "second": p.get("second_name", ""),
                "first": p.get("first_name", ""),
            })
        self.gw = gw

    def resolve(self, raw: str) -> dict:
        q = norm(raw)
        if not q:
            raise ValueError("empty name")

        exact = [r for r in self.rows if norm(r["name"]) == q]
        if len(exact) == 1:
            return exact[0]

        # Full name, or the surname on its own.
        full = [r for r in self.rows
                if norm(f"{r['first']} {r['second']}") == q or norm(r["second"]) == q]
        if len(full) == 1:
            return full[0]

        starts = [r for r in self.rows if norm(r["name"]).startswith(q)
                  or norm(r["second"]).startswith(q)]
        if len(starts) == 1:
            return starts[0]

        contains = [r for r in self.rows
                    if q in norm(r["name"]) or q in norm(f"{r['first']}{r['second']}")]
        if len(contains) == 1:
            return contains[0]

        pool = {norm(r["name"]): r for r in self.rows}
        close = difflib.get_close_matches(q, list(pool), n=2, cutoff=0.75)
        if len(close) == 1:
            return pool[close[0]]

        candidates = starts or contains or [pool[c] for c in close]
        if candidates:
            raise ValueError(
                f"'{raw}' could be " +
                " or ".join(sorted(c["name"] for c in candidates)) +
                " - say which")
        raise ValueError(
            f"'{raw}' is not one of your fifteen. You own: " +
            ", ".join(sorted(r["name"] for r in self.rows)))


def validate(xi: list[dict], bench: list[dict], captain: dict,
             vice: dict | None) -> list[str]:
    """Every rule that would make the team illegal or the file wrong."""
    errs = []
    if len(xi) != 11:
        errs.append(f"{len(xi)} players in the XI, should be 11")
    if len(bench) != 4:
        errs.append(f"{len(bench)} on the bench, should be 4")

    names = [r["name"] for r in xi + bench]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        errs.append("named twice: " + ", ".join(sorted(dupes)))
    if len(set(names)) != 15 and not dupes:
        errs.append(f"{len(set(names))} distinct players, should be 15")

    pos = [r["pos"] for r in xi]
    if pos.count("GKP") != 1:
        errs.append(f"{pos.count('GKP')} goalkeepers in the XI, should be exactly 1")
    if pos.count("DEF") < 3:
        errs.append(f"{pos.count('DEF')} defenders in the XI, minimum is 3")
    if pos.count("FWD") < 1:
        errs.append("no forward in the XI, minimum is 1")

    clubs: dict[str, int] = {}
    for r in xi + bench:
        clubs[r["team"]] = clubs.get(r["team"], 0) + 1
    for club, n in clubs.items():
        if n > MAX_PER_CLUB:
            errs.append(f"{n} players from {club}, maximum is {MAX_PER_CLUB}")

    if captain["name"] not in [r["name"] for r in xi]:
        errs.append(f"captain {captain['name']} is not in the starting XI")
    if vice and vice["name"] not in [r["name"] for r in xi]:
        errs.append(f"vice-captain {vice['name']} is not in the starting XI")
    if vice and vice["name"] == captain["name"]:
        errs.append("captain and vice-captain are the same player")
    return errs


def build(xi_raw: list[str], bench_raw: list[str], captain_raw: str,
          vice_raw: str | None, gw: int | None = None) -> dict:
    ev = fpl.next_event()
    if not ev:
        raise fpl.FPLError("No upcoming gameweek.")
    gw = gw or ev["id"]
    squad = Squad(gw)

    problems = []

    def resolve_all(raws: list[str]) -> list[dict]:
        rows = []
        for raw in raws:
            try:
                rows.append(squad.resolve(raw))
            except ValueError as exc:
                problems.append(str(exc))
        return rows

    xi = resolve_all(xi_raw)
    bench = resolve_all(bench_raw)
    captain = vice = None
    try:
        captain = squad.resolve(captain_raw)
    except ValueError as exc:
        problems.append(f"captain: {exc}")
    if vice_raw:
        try:
            vice = squad.resolve(vice_raw)
        except ValueError as exc:
            problems.append(f"vice-captain: {exc}")

    if problems:
        raise ValueError("\n".join(f"  - {p}" for p in problems))

    errs = validate(xi, bench, captain, vice)
    if errs:
        raise ValueError("\n".join(f"  - {e}" for e in errs))

    order = {"GKP": 0, "DEF": 1, "MID": 2, "FWD": 3}
    xi_sorted = sorted(xi, key=lambda r: order[r["pos"]])
    counts = {p: sum(1 for r in xi if r["pos"] == p) for p in ("DEF", "MID", "FWD")}

    return {
        "_comment": ("What Ido said he is fielding, recorded by team_update.py. "
                     "FPL does not publish a manager's XI before the deadline, "
                     "so this is the only source for it. Nothing in this project "
                     "may change his team - this only writes down what he told us."),
        "_recorded": datetime.now().isoformat(timespec="seconds"),
        "event": gw,
        "captain": captain["name"],
        "vice_captain": vice["name"] if vice else None,
        "formation": f"{counts['DEF']}-{counts['MID']}-{counts['FWD']}",
        "starting_xi": [r["name"] for r in xi_sorted],
        "bench": [r["name"] for r in bench],
    }


def split(s: str) -> list[str]:
    parts = [p.strip() for p in s.replace("\n", ",").split(",")]
    return [p for p in parts if p]


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    ap = argparse.ArgumentParser(
        description="Record the team Ido says he is fielding.")
    ap.add_argument("--xi", required=True, help="11 names, comma separated")
    ap.add_argument("--bench", required=True,
                    help="4 names in bench order, comma separated")
    ap.add_argument("--captain", required=True)
    ap.add_argument("--vice")
    ap.add_argument("--gw", type=int)
    ap.add_argument("--check", action="store_true",
                    help="validate and print, write nothing")
    a = ap.parse_args(argv)

    try:
        payload = build(split(a.xi), split(a.bench), a.captain, a.vice, a.gw)
    except ValueError as exc:
        print("Not recorded - this does not add up:\n")
        print(exc)
        print("\nNothing was written. Check it against his message and try again.")
        return 2
    except fpl.FPLError as exc:
        print(f"error: {exc}")
        return 1

    print(f"GW{payload['event']}  {payload['formation']}   "
          f"{payload['captain']} (C)" +
          (f", {payload['vice_captain']} (V)" if payload["vice_captain"] else ""))
    print("  XI   : " + ", ".join(payload["starting_xi"]))
    print("  bench: " + ", ".join(payload["bench"]))

    if a.check:
        print("\n--check: valid, nothing written.")
        return 0

    TEAM_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"\nSaved to current_team.json. The reports will now use this team.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
