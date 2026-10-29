"""
Export the season's results into results/ - numbers only, team names only.

The system itself runs in a private working folder; this repository is the
public copy. Each week, after the review run has scored the gameweek, this
script reads that folder (read-only) and rewrites:

    results/weekly.csv           my points, score /10, top-100 and world average, rank
    results/staff_vs_baseline.csv  the staff's recommended lineup v what I played v doing nothing
    results/league_gaps.csv      the gap to each rival team after every gameweek
    results/staff_vs_baseline.png  the chart in the README
    README.md                    the results table between the RESULTS markers

Nothing is published by this script. It prepares a commit; pushing it is a
separate, manual step (`--publish`), taken only after the owner approves.

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

import config
import gap

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"
LIVE = Path(json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["live_dir"])

# Chart colours: the first three slots of a colour-blind-checked categorical palette,
# each line also carrying its own label and dash style so colour is never the only cue.
COLORS = {"Staff recommendation": "#2a78d6", "What I played": "#eb6834", "Doing nothing": "#1baf7a"}
DASH = {"Staff recommendation": "-", "What I played": "-", "Doing nothing": (0, (4, 3))}
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def _first_int(cell: str) -> int | None:
    m = re.search(r"-?\d+", cell.replace("*", ""))
    return int(m.group()) if m else None


def staff_record() -> list[dict]:
    """The Historian's week-by-week table in the private ledger (auto-subs applied)."""
    text = (LIVE / "ledger.md").read_text(encoding="utf-8")
    block = text[text.index("### Week by week"):]
    rows = []
    for line in block.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 9 or not cells[0].isdigit():
            if rows and line.startswith("| **Total**"):
                break
            continue
        rows.append({"gw": int(cells[0]), "recommended": _first_int(cells[4]),
                     "played": _first_int(cells[3]), "do_nothing": _first_int(cells[8])})
    return rows


def benchmark_weeks() -> list[dict]:
    """Per-gameweek outside yardsticks, from the private folder's benchmark (read-only)."""
    out = subprocess.run([sys.executable, "-X", "utf8", "benchmark.py", "--json"], cwd=LIVE,
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return json.loads(out)["weeks"]


def league_gaps() -> list[dict]:
    sb = gap.scoreboard()          # team names, never managers' names
    return [{"gw": r["gw"], "team": team, "gap": v["gap"]}
            for r in sb["rows"] for team, v in r["rivals"].items()]


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def chart(staff: list[dict]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    gws = [r["gw"] for r in staff]
    series = {"Staff recommendation": "recommended", "What I played": "played", "Doing nothing": "do_nothing"}
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ends = []
    for label, key in series.items():
        total, ys = 0, []
        for r in staff:
            total += r[key]
            ys.append(total)
        ax.plot(gws, ys, color=COLORS[label], linestyle=DASH[label], linewidth=2,
                marker="o", markersize=4.5, markeredgecolor=SURFACE, markeredgewidth=1.5,
                solid_capstyle="round", zorder=3)
        ends.append((ys[-1], label))
    # direct labels at the line ends, nudged apart so they never collide
    ends.sort()
    placed = []
    for y, label in ends:
        y_txt = y if not placed else max(y, placed[-1] + 12)
        placed.append(y_txt)
        ax.annotate(f"{label}  {y}", xy=(gws[-1], y), xytext=(gws[-1] + 0.12, y_txt),
                    va="center", fontsize=9, color=INK)
    ax.set_xticks(gws, [f"GW{g}" for g in gws])
    ax.set_ylabel("Points, added up since the staff started", fontsize=9, color=MUTED)
    ax.set_title("Did the AI staff's advice beat doing nothing?", loc="left", fontsize=12,
                 color=INK, pad=12)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.set_xlim(gws[0] - 0.2, gws[-1] + 1.6)
    ax.legend([plt.Line2D([], [], color=COLORS[k], linestyle=DASH[k], linewidth=2) for k in series],
              list(series), loc="upper left", frameon=False, fontsize=8.5, labelcolor=MUTED)
    fig.tight_layout()
    fig.savefig(OUT / "staff_vs_baseline.png", facecolor=SURFACE)
    plt.close(fig)


def readme_table(staff: list[dict], weeks: list[dict]) -> str:
    by_gw = {w["gw"]: w for w in weeks}
    lines = ["| GW | Staff advice | What I played | Doing nothing | Score /10 | vs top-100 avg | World rank |",
             "|---|---|---|---|---|---|---|"]
    for r in staff:
        w = by_gw.get(r["gw"], {})
        vt = w.get("vs_top100")
        lines.append(f"| {r['gw']} | {r['recommended']} | {r['played']} | {r['do_nothing']} | "
                     f"{w.get('score10', '-')} | {'-' if vt is None else f'{vt:+.0f}'} | "
                     f"{w['overall_rank'] / 1e6:.2f}M |" if w else "| - |")
    t = {k: sum(r[k] for r in staff) for k in ("recommended", "played", "do_nothing")}
    lift = 100 * (t["recommended"] - t["do_nothing"]) / t["do_nothing"]
    lines.append(f"| **Total** | **{t['recommended']}** | **{t['played']}** | **{t['do_nothing']}** | | | |")
    lines.append("")
    lines.append(f"Over GW{staff[0]['gw']}-{staff[-1]['gw']} the staff's recommended lineups scored "
                 f"**{lift:+.0f}%** against doing nothing. It is a small sample, so read it as an "
                 "early sign, not proof.")
    return "\n".join(lines)


def update_readme(table: str) -> None:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    start, end = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
    text = text[:text.index(start) + len(start)] + "\n" + table + "\n" + text[text.index(end):]
    path.write_text(text, encoding="utf-8")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def main(argv: list[str]) -> int:
    if "--publish" in argv:
        print(git("push"))
        return 0
    OUT.mkdir(exist_ok=True)
    staff, weeks = staff_record(), benchmark_weeks()
    write_csv(OUT / "staff_vs_baseline.csv", staff)
    write_csv(OUT / "weekly.csv", [{k: w[k] for k in ("gw", "points", "score10", "top100", "vs_top100",
                                                       "average", "vs_average", "gw_rank", "overall_rank")}
                                    for w in weeks])
    write_csv(OUT / "league_gaps.csv", league_gaps())
    chart(staff)
    update_readme(readme_table(staff, weeks))
    if (ROOT / ".git").exists():
        git("add", "results", "README.md")
        if git("status", "--porcelain", "--", "results", "README.md").strip():
            git("commit", "-m", f"Results after GW{weeks[-1]['gw']}")
            print(f"Committed results after GW{weeks[-1]['gw']} locally - not pushed. "
                  "Run with --publish once approved.")
        else:
            print("Results unchanged - nothing to commit.")
    else:
        print("Wrote results/ and README (no git repository yet).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
