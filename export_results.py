"""
Export the season's results into results/ - numbers only, team names only.

The system itself runs in a private working folder; this repository is the
public copy. Each week, after the review run has scored the gameweek, this
script reads that folder (read-only) and rewrites:

    results/weekly.csv                 points, score /10, top-100 and world average, rank
    results/staff_vs_baseline.csv      staff's recommended lineup v what I played v doing nothing
    results/league_gaps.csv            the gap to each rival team after every gameweek
    results/forecasts.csv              the staff's predicted points v the real score (from GW9)
    results/goals.csv                  each week's two goals, met or missed (from GW10)
    results/*.png                      the charts in the README
    README.md                          the Findings section, between the RESULTS markers

Nothing is published by this script. It prepares a commit; pushing it is a
separate step (`--publish`), taken only after the owner approves.

    python export_results.py              rewrite results/ and README, commit locally
    python export_results.py --publish    push the prepared commit to GitHub
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

import gap

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
LIVE = Path(CFG["live_dir"])
STAFF_FROM = 4

# Style. Categorical colours are the first slots of a colour-blind-checked palette;
# every series also carries a direct label, so colour is never the only cue.
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, MUTED, FAINT, GRID, SURFACE = "#0b0b0b", "#52514e", "#a3a29d", "#e9e8e4", "#fcfcfb"
PRE = "#c9c8c2"          # the weeks before the AI staff existed


# ------------------------------------------------------------------- data

def _first_int(cell: str) -> int | None:
    m = re.search(r"-?\d+", cell.replace("*", ""))
    return int(m.group()) if m else None


def staff_record() -> list[dict]:
    """The Historian's week-by-week table in the private ledger (auto-subs applied)."""
    text = (LIVE / "ledger.md").read_text(encoding="utf-8")
    block = text[text.index("### Week by week"):]
    rows = []
    for line in block.splitlines():
        if line.startswith("| **Total**"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 9 and cells[0].isdigit():
            rows.append({"gw": int(cells[0]), "recommended": _first_int(cells[4]),
                         "played": _first_int(cells[3]), "do_nothing": _first_int(cells[8])})
    return rows


def benchmark_weeks() -> list[dict]:
    out = subprocess.run([sys.executable, "-X", "utf8", "benchmark.py", "--json"], cwd=LIVE,
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return json.loads(out)["weeks"]


def league_gaps() -> list[dict]:
    sb = gap.scoreboard()          # team names, never managers' names
    return [{"gw": r["gw"], "team": team, "gap": v["gap"]}
            for r in sb["rows"] for team, v in r["rivals"].items()]


def forecasts() -> list[dict]:
    """The recommended option's predicted points against what it really scored (numbers only)."""
    rows = []
    for f in sorted((LIVE / "recommendations").glob("gw*.json"), key=lambda p: int(p.stem[2:])):
        d = json.loads(f.read_text(encoding="utf-8"))
        a = d.get("actual") or {}
        for o in a.get("options", []):
            if o.get("recommended") and o.get("predicted") is not None:
                rows.append({"gw": d["event"], "predicted": o["predicted"], "actual": o["score"],
                             "inside_range": o.get("within_best_worst")})
    return rows


def _team_names(text: str) -> str:
    for real in sorted(CFG.get("names", {}), key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(real)}\b", CFG["names"][real], text)
    return text


def goals() -> list[dict]:
    """Each week's two goals from the private season plan, with real names swapped for team names."""
    text = (LIVE / "season_plan.md").read_text(encoding="utf-8")
    if "## 6. Weekly goals" not in text:
        return []
    block = text[text.index("## 6. Weekly goals"):]
    rows = []
    for line in block.splitlines()[1:]:
        if line.startswith("## "):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and _first_int(cells[0]) is not None and "---" not in line:
            rows.append({"gw": _first_int(cells[0]), "goal_1": _team_names(cells[1]),
                         "goal_2": _team_names(cells[2]), "result": _team_names(cells[3])})
    return rows


def advice_use() -> dict[int, str]:
    """Per gameweek: did I play the staff's advice ("used"), or go my own way ("own")?

    "Used" means my team matched one of the staff's lineups to within one player,
    with the same captain, and was not simply my unchanged team. Weeks before the
    staff existed are "none".
    """
    out = {}
    for f in sorted((LIVE / "recommendations").glob("gw*.json"), key=lambda p: int(p.stem[2:])):
        d = json.loads(f.read_text(encoding="utf-8"))
        a = d.get("actual") or {}
        opts = a.get("options", [])
        staff = [o for o in opts if o["name"] != "DO NOTHING"]
        if not staff:
            continue
        nothing = next((o["players_different"] for o in opts if o["name"] == "DO NOTHING"), 99)
        best = min(staff, key=lambda o: o["players_different"])
        used = (best["players_different"] <= 1 and best["captain_matched"]
                and best["players_different"] <= nothing)
        out[d["event"]] = "used" if used else "own"
    return out


def chips_by_week() -> dict[int, dict[str, str]]:
    """Chips played per gameweek, by team name (mine included, as "me")."""
    names = {"wildcard": "WC", "freehit": "FH", "bboost": "BB", "3xc": "TC"}
    sb = gap.scoreboard()
    out = {}
    for r in sb["rows"]:
        wk = {team: names.get(v["chip"], v["chip"]) for team, v in r["rivals"].items() if v["chip"]}
        if r["ido_chip"]:
            wk["me"] = names.get(r["ido_chip"], r["ido_chip"])
        if wk:
            out[r["gw"]] = wk
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.unlink(missing_ok=True)
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


# ----------------------------------------------------------------- charts

def _style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10,
        "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
        "ytick.color": MUTED, "axes.titlecolor": INK,
    })
    return plt


def _frame(plt, title: str, subtitle: str, size=(9, 4.6)):
    fig, ax = plt.subplots(figsize=size, dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    fig.text(0.035, 0.955, title, fontsize=14.5, fontweight="bold", color=INK, va="top")
    fig.text(0.035, 0.885, subtitle, fontsize=10, color=MUTED, va="top")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0, labelsize=9.5)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    return fig, ax


def _save(fig, name: str) -> None:
    fig.subplots_adjust(left=0.07, right=0.97, top=0.78, bottom=0.12)
    fig.savefig(OUT / name, facecolor=SURFACE)


def chart_score(plt, weeks: list[dict], use: dict[int, str]) -> None:
    """Score out of 10, grouped by whether I played the staff's advice."""
    fig, ax = _frame(plt, "Did I do better when I used the AI's advice?",
                     "Score out of 10 = the share of all ~11 million FPL managers I beat that gameweek")
    groups = [("No advice yet", "none", PRE), ("Used the advice", "used", BLUE),
              ("Went my own way", "own", ORANGE)]
    x, ticks, labels = 0.0, [], []
    for title, key, col in groups:
        wk = [w for w in weeks if use.get(w["gw"], "none") == key]
        if not wk:
            continue
        xs = [x + i for i in range(len(wk))]
        vals = [w["score10"] for w in wk]
        ax.bar(xs, vals, width=0.68, color=col, zorder=3)
        for xi, v in zip(xs, vals):
            ax.text(xi, v + 0.18, f"{v:.1f}", ha="center", va="bottom", fontsize=10, color=INK,
                    fontweight="bold", zorder=6,
                    bbox=dict(boxstyle="square,pad=0.15", facecolor=SURFACE, edgecolor="none"))
        m = sum(vals) / len(vals)
        ax.hlines(m, xs[0] - 0.42, xs[-1] + 0.42, colors=INK, linestyles=(0, (4, 3)),
                  linewidth=1.3, zorder=4)
        mid = (xs[0] + xs[-1]) / 2
        ax.text(mid, 10.25, title, ha="center", fontsize=10, color=col if key != "none" else MUTED,
                fontweight="bold")
        ax.text(mid, 9.65, f"average {m:.1f}  ·  {len(wk)} week{'s' if len(wk) > 1 else ''}",
                ha="center", fontsize=9, color=MUTED)
        ticks += xs
        labels += [f"GW{w['gw']}" for w in wk]
        x = xs[-1] + 1.9
    ax.set_xticks(ticks, labels)
    ax.set_ylim(0, 10.9)
    ax.set_yticks([0, 2, 4, 6, 8])
    ax.set_xlim(-0.7, x - 1.2)
    fig.text(0.035, 0.03, "Used = my team matched a staff lineup to within one player, same captain. "
             "Dashed line = the group's average.", fontsize=8.5, color=MUTED)
    _save(fig, "score_by_advice.png")
    plt.close(fig)

def chart_staff(plt, staff: list[dict]) -> None:
    """Per week: points gained against doing nothing, by the staff's lineup and by mine."""
    fig, ax = _frame(plt, "Did changing the team beat doing nothing?",
                     "Points gained (+) or lost (-) each week against keeping the team unchanged")
    import numpy as np
    gws = np.array([r["gw"] for r in staff])
    s = [r["recommended"] - r["do_nothing"] for r in staff]
    m = [r["played"] - r["do_nothing"] for r in staff]
    w = 0.36
    for xs, vals, col, lab in ((gws - w / 2 - 0.02, s, BLUE, "Staff's recommended lineup"),
                               (gws + w / 2 + 0.02, m, ORANGE, "The lineup I actually played")):
        bars = ax.bar(xs, vals, width=w, color=col, zorder=3, label=lab)
        for b, v in zip(bars, vals):
            y = v + (0.6 if v >= 0 else -0.6)
            ax.text(b.get_x() + b.get_width() / 2, y, f"{v:+d}" if v else "0", ha="center",
                    va="bottom" if v >= 0 else "top", fontsize=9, color=INK)
    ax.axhline(0, color=MUTED, linewidth=1, zorder=4)
    ax.text(gws[-1] + 0.55, 0, "doing\nnothing", va="center", fontsize=8.5, color=MUTED)
    lo, hi = min(s + m), max(s + m)
    ax.set_ylim(min(lo - 4, -5), hi + 5)
    ax.set_xlim(gws[0] - 0.6, gws[-1] + 0.95)
    ax.set_xticks(gws, [f"GW{g}" for g in gws])
    ts, tm = sum(s), sum(m)
    ax.legend(frameon=False, loc="upper right", fontsize=9, labelcolor=MUTED, ncols=2,
              bbox_to_anchor=(1.0, 1.02))
    fig.text(0.035, 0.825, f"Total: staff {ts:+d} points · me {tm:+d} points", fontsize=10,
             color=INK, va="top", fontweight="bold")
    _save(fig, "staff_vs_doing_nothing.png")
    plt.close(fig)


def chart_league(plt, gaps: list[dict], use: dict[int, str], chips: dict[int, dict[str, str]]) -> None:
    """My gap to each rival team after every gameweek, with chips and advice use marked."""
    fig, ax = _frame(plt, "The league race: me against three friends without AI",
                     "Points I am behind (-) or ahead (+) of each team after every gameweek.  "
                     "Blue = a chip was played that week", size=(9, 5.0))
    teams = sorted({g["team"] for g in gaps}, key=lambda t: min(x["gap"] for x in gaps if x["team"] == t))
    colors = [ORANGE, AQUA, YELLOW]
    gws = sorted({g["gw"] for g in gaps})
    ax.axhline(0, color=MUTED, linewidth=1, zorder=2)
    ax.text(gws[0] - 0.4, 1.5, "level", fontsize=8.5, color=MUTED, va="bottom")
    ends = []
    for team, col in zip(teams, colors):
        pts = sorted((g["gw"], g["gap"]) for g in gaps if g["team"] == team)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        ax.plot(xs, ys, color=col, linewidth=2.4, marker="o", markersize=6,
                markeredgecolor=SURFACE, markeredgewidth=1.8, zorder=3, solid_capstyle="round")
        for gx, gy in pts:                       # a rival's chip: a blue point on their line
            if chips.get(gx, {}).get(team):
                ax.scatter([gx], [gy], s=150, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=5)
        ends.append([ys[-1], team])
    # chip labels to the left of their points, pushed apart where two land in one week
    for gx in gws:
        marks = sorted(((g["gap"], chips[gx][g["team"]]) for g in gaps
                        if g["gw"] == gx and chips.get(gx, {}).get(g["team"])), reverse=True)
        prev = None
        for gy, c in marks:
            y = gy if prev is None else min(gy, prev - 6)
            prev = y
            ax.text(gx - 0.17, y, c, ha="right", va="center", fontsize=8.5, color=BLUE,
                    fontweight="bold", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.15", facecolor=SURFACE, edgecolor="none"))
    ends.sort()
    for i in range(1, len(ends)):
        ends[i][0] = max(ends[i][0], ends[i - 1][0] + 6)
    for y, team in ends:
        real = next(g["gap"] for g in gaps if g["team"] == team and g["gw"] == gws[-1])
        ax.text(gws[-1] + 0.2, y, f"{team}  {real:+d}", va="center", fontsize=9.5, color=INK)
    # under each gameweek: my chip (blue) and whether I used the advice
    trans = ax.get_xaxis_transform()
    lab = {"used": ("used advice", BLUE), "own": ("own way", ORANGE), "none": ("no advice yet", FAINT)}
    for gx in gws:
        t, c = lab[use.get(gx, "none")]
        ax.text(gx, -0.13, t, transform=trans, ha="center", va="top", fontsize=8, color=c)
        mine = chips.get(gx, {}).get("me")
        if mine:
            ax.text(gx, -0.2, f"my chip: {mine}", transform=trans, ha="center", va="top",
                    fontsize=8, color=SURFACE, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.25", facecolor=BLUE, edgecolor="none"))
    ax.set_xlim(gws[0] - 0.5, gws[-1] + 2.6)
    ax.set_xticks(gws, [f"GW{g}" for g in gws])
    fig.subplots_adjust(left=0.07, right=0.97, top=0.8, bottom=0.2)
    fig.savefig(OUT / "league_race.png", facecolor=SURFACE)
    plt.close(fig)

def chart_forecasts(plt, rows: list[dict]) -> None:
    fig, ax = _frame(plt, "Can the staff predict their own score?",
                     "Points the staff predicted for their recommended lineup, against what it really scored")
    gws = [r["gw"] for r in rows]
    for r in rows:
        ax.plot([r["gw"], r["gw"]], [r["predicted"], r["actual"]], color=GRID, linewidth=3, zorder=2)
    ax.scatter(gws, [r["predicted"] for r in rows], s=70, color=FAINT, zorder=3, label="Predicted")
    ax.scatter(gws, [r["actual"] for r in rows], s=70, color=BLUE, zorder=4, label="Real score")
    ax.legend(frameon=False, loc="upper right", fontsize=9, labelcolor=MUTED)
    ax.set_xticks(gws, [f"GW{g}" for g in gws])
    _save(fig, "forecasts.png")
    plt.close(fig)


# ------------------------------------------------------------------ README

def findings(staff, weeks, gaps, fc, gl, use) -> str:
    """The Findings section. One sentence per line (Markdown hard breaks), as the owner asked."""
    avg = lambda xs: sum(xs) / len(xs)
    by = {k: [w["score10"] for w in weeks if use.get(w["gw"], "none") == k] for k in ("none", "used", "own")}
    t = {k: sum(r[k] for r in staff) for k in ("recommended", "played", "do_nothing")}
    last = max(g["gw"] for g in gaps)
    now = {g["team"]: g["gap"] for g in gaps if g["gw"] == last}
    then = {g["team"]: g["gap"] for g in gaps if g["gw"] == STAFF_FROM - 1}
    br = "  "        # two trailing spaces = a line break on GitHub

    def lines(*sentences: str) -> list[str]:
        return [s + br for s in sentences[:-1]] + [sentences[-1]]

    used_n, own_n = len(by["used"]), len(by["own"])
    out = [f"*Updated after GW{weeks[-1]['gw']}. The AI staff started advising in GW{STAFF_FROM}.*", "",
           "### 1. Did I do better when I used the AI's advice?", "",
           "![Score out of 10, by whether I used the advice](results/score_by_advice.png)", ""]
    if by["used"] and by["own"]:
        out += lines(f"Weeks I used the advice: **{avg(by['used']):.1f}/10** on average ({used_n} weeks).",
                     f"Weeks I went my own way: **{avg(by['own']):.1f}/10** ({own_n} weeks).",
                     f"Before there was any advice: **{avg(by['none']):.1f}/10**.",
                     "With this few weeks, one good or bad week moves an average a lot.")
    out += ["", "### 2. Does the advice beat doing nothing?", "",
            "![Points gained against doing nothing](results/staff_vs_doing_nothing.png)", ""]
    out += lines(f"Over GW{staff[0]['gw']}-{staff[-1]['gw']} the staff's recommended lineups scored "
                 f"**{t['recommended']}** points against **{t['do_nothing']}** for doing nothing "
                 f"(**{100 * (t['recommended'] - t['do_nothing']) / t['do_nothing']:+.0f}%**).",
                 f"My own choices, made after reading the advice, scored **{t['played']}**.")
    out += ["", "### 3. The league race", "",
            "![Gap to each team](results/league_race.png)", ""]
    out += lines("The goal is to beat three friends who play without AI.",
                 "Since the staff started: " +
                 ", ".join(f"**{tm}** {then[tm]:+d} → {now[tm]:+d}" for tm in now if tm in then) + ".",
                 "Blue points mark the weeks a chip was played, because a chip can swing a week on its own.")
    out += ["", "### 4. Can the staff predict their own results?", ""]
    if fc:
        hit = sum(1 for r in fc if r["inside_range"])
        out += ["![Predicted against real points](results/forecasts.png)", ""]
        out += lines(f"The real score landed inside the staff's best-to-worst range in **{hit} of {len(fc)}** weeks.")
    else:
        out += lines("*Coming soon - tracked from GW9.*",
                     "Before every deadline the staff now record the points they expect, with a best and worst case.",
                     "This section will compare each forecast with the real score.")
    out += ["", "### 5. Do we reach the goals we set?", ""]
    if gl:
        met = sum(1 for g in gl for r in [g["result"].lower()] if "met" in r and "missed" not in r)
        out += [f"Weekly goals met so far: **{met} of {len(gl)}** weeks.", "",
                "| GW | Goal 1 | Goal 2 | Result |", "|---|---|---|---|"]
        out += [f"| {g['gw']} | {g['goal_1']} | {g['goal_2']} | {g['result'] or '-'} |" for g in gl]
    else:
        out += lines("*Coming soon - from GW10.*",
                     "Each planning run sets two checkable goals for the week, for example "
                     "\"close 5 points on a rival\" or \"beat the top-100 average\".",
                     "The review marks each one met or missed, and the record will appear here.")
    return "\n".join(out)

def update_readme(section: str) -> None:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    start, end = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
    text = text[:text.index(start) + len(start)] + "\n" + section + "\n" + text[text.index(end):]
    path.write_text(text, encoding="utf-8")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def main(argv: list[str]) -> int:
    if "--publish" in argv:
        print(git("push"))
        return 0
    OUT.mkdir(exist_ok=True)
    staff, weeks, gaps, fc, gl = staff_record(), benchmark_weeks(), league_gaps(), forecasts(), goals()
    use, chips = advice_use(), chips_by_week()
    write_csv(OUT / "staff_vs_baseline.csv", staff)
    write_csv(OUT / "weekly.csv", [{k: w[k] for k in ("gw", "points", "score10", "top100", "vs_top100",
                                                       "average", "vs_average", "gw_rank", "overall_rank")}
                                    for w in weeks])
    write_csv(OUT / "league_gaps.csv", gaps)
    write_csv(OUT / "forecasts.csv", fc)
    write_csv(OUT / "goals.csv", gl)
    plt = _style()
    chart_score(plt, weeks, use)
    chart_staff(plt, staff)
    chart_league(plt, gaps, use, chips)
    if fc:
        chart_forecasts(plt, fc)
    update_readme(findings(staff, weeks, gaps, fc, gl, use))
    if (ROOT / ".git").exists():
        git("add", "-A", "results", "README.md")
        if git("status", "--porcelain", "--", "results", "README.md").strip():
            git("commit", "-m", f"Results after GW{weeks[-1]['gw']}")
            print(f"Committed results after GW{weeks[-1]['gw']} locally - not pushed. "
                  "Run with --publish once approved.")
        else:
            print("Results unchanged - nothing to commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
