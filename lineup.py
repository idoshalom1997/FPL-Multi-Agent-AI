"""
Renders an XI onto a pitch as a PNG in the style of the FPL squad graphics:
club-badged shirts, a points chip on each player, club / position / price under
the name, and a substitutes strip along the bottom.

    python lineup.py demo          render the live team from current_team.json
    python lineup.py badges        re-download the club badges
"""
from __future__ import annotations

import config
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle, Circle, Ellipse

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "reports"
BADGES = ROOT / "badges"
OUT.mkdir(exist_ok=True)

# Palette lifted from the FPL squad graphics.
NAVY = "#0A1B2E"
NAVY_TOP = "#16304F"
MINT = "#00FF87"
GRASS = "#14B85A"
GRASS_ALT = "#0FA850"
GRASS_EDGE = "#0A8B41"
LINE = "#ffffff"
CHIP = "#0C2036"
NAME_BG = "#ffffff"
INFO_BG = "#E9EEF2"
INK = "#0A1B2E"

ROW_Y = {"GKP": 0.875, "DEF": 0.635, "MID": 0.395, "FWD": 0.155}

KIT = {
    "ARS": ("#EF0107", "#ffffff"), "AVL": ("#670E36", "#95BFE5"),
    "BHA": ("#0057B8", "#ffffff"), "BOU": ("#DA291C", "#000000"),
    "BRE": ("#E30613", "#ffffff"), "CHE": ("#034694", "#ffffff"),
    "COV": ("#78D0F3", "#ffffff"), "CRY": ("#1B458F", "#C4122E"),
    "EVE": ("#003399", "#ffffff"), "FUL": ("#ffffff", "#000000"),
    "HUL": ("#F5971D", "#000000"), "IPS": ("#0044A9", "#ffffff"),
    "LEE": ("#ffffff", "#1D428A"), "LIV": ("#C8102E", "#ffffff"),
    "MCI": ("#6CABDD", "#ffffff"), "MUN": ("#DA020E", "#000000"),
    "NEW": ("#241F20", "#ffffff"), "NFO": ("#DD0000", "#ffffff"),
    "SUN": ("#EB172B", "#ffffff"), "TOT": ("#ffffff", "#132257"),
}
KIT_GK = ("#FFD400", "#1b1b1b")
DEFAULT_KIT = ("#8a8a8a", "#ffffff")

TEAM_CODE = {
    "ARS": 3, "AVL": 7, "BOU": 91, "BRE": 94, "BHA": 36, "CHE": 8, "COV": 9,
    "CRY": 31, "EVE": 11, "FUL": 54, "HUL": 88, "IPS": 40, "LEE": 2, "LIV": 14,
    "MCI": 43, "MUN": 1, "NEW": 4, "NFO": 17, "TOT": 6, "SUN": 56,
}

SHIRT = [
    (0.50, 0.97), (0.67, 0.93), (0.93, 0.79), (0.86, 0.55),
    (0.75, 0.61), (0.75, 0.04), (0.25, 0.04), (0.25, 0.61),
    (0.14, 0.55), (0.07, 0.79), (0.33, 0.93),
]
SLEEVE_L = [(0.33, 0.93), (0.07, 0.79), (0.14, 0.55), (0.25, 0.61)]
SLEEVE_R = [(0.67, 0.93), (0.93, 0.79), (0.86, 0.55), (0.75, 0.61)]
COLLAR = [(0.42, 0.955), (0.50, 0.86), (0.58, 0.955), (0.50, 0.99)]

_badge_cache: dict[str, np.ndarray] = {}


def badge(team: str):
    """Club crest as an image array, or None if it was never downloaded."""
    if team in _badge_cache:
        return _badge_cache[team]
    p = BADGES / f"{team}.png"
    img = mpimg.imread(p) if p.exists() else None
    _badge_cache[team] = img
    return img


def download_badges() -> None:
    """curl handles this host far faster than urllib does from Windows."""
    BADGES.mkdir(exist_ok=True)
    for team, code in TEAM_CODE.items():
        dest = BADGES / f"{team}.png"
        if dest.exists() and dest.stat().st_size > 500:
            continue
        url = f"https://resources.premierleague.com/premierleague/badges/70/t{code}.png"
        subprocess.run(["curl", "-s", "-m", "12", "-A", "Mozilla/5.0",
                        "-o", str(dest), url], check=False)
    print(f"badges present: {len(list(BADGES.glob('*.png')))}/20")


def _poly(ax, pts, x, y, w, h, **kw):
    ax.add_patch(Polygon([(x + px * w, y + py * h) for px, py in pts], **kw))


def _background(fig) -> None:
    """Navy gradient with a soft glow behind the goal, like stadium lighting."""
    ax = fig.add_axes([0, 0, 1, 1], zorder=-10)
    ax.axis("off")
    top = np.array(matplotlib.colors.to_rgb(NAVY_TOP))
    bot = np.array(matplotlib.colors.to_rgb(NAVY))
    grad = np.linspace(0, 1, 256)[:, None]
    img = bot[None, None, :] * grad[..., None][:, :, 0][:, :, None] + \
        top[None, None, :] * (1 - grad[..., None][:, :, 0][:, :, None])
    ax.imshow(img, extent=[0, 1, 0, 1], aspect="auto", origin="lower")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)


def _pitch(ax) -> None:
    ax.add_patch(Polygon([(0.11, 1.0), (0.89, 1.0), (1.0, 0.0), (0.0, 0.0)],
                         facecolor=GRASS, edgecolor=GRASS_EDGE, lw=2, zorder=0))
    for i in range(8):
        if i % 2:
            continue
        t0, t1 = i / 8, (i + 1) / 8
        x0a, x1a = 0.11 * t0, 1 - 0.11 * t0
        x0b, x1b = 0.11 * t1, 1 - 0.11 * t1
        ax.add_patch(Polygon([(x0b, t1), (x1b, t1), (x1a, t0), (x0a, t0)],
                             facecolor=GRASS_ALT, lw=0, zorder=0.4))
    opts = dict(color=LINE, lw=1.8, fill=False, zorder=1)
    ax.add_patch(Polygon([(0.345, 1.0), (0.655, 1.0), (0.625, 0.835), (0.375, 0.835)], **opts))
    ax.add_patch(Polygon([(0.43, 1.0), (0.57, 1.0), (0.558, 0.938), (0.442, 0.938)], **opts))
    ax.add_patch(Circle((0.5, 0.045), 0.12, **opts))
    ax.plot([0.0, 1.0], [0.045, 0.045], color=LINE, lw=1.8, zorder=1)


def _card(ax, x, y, p, *, w=0.140, h=0.163, badge_zoom=0.21, aspect=1.0) -> None:
    """
    aspect is the axes' width:height ratio in inches. Circles drawn in data
    coordinates stretch into ovals when it is not 1, which it badly is not on
    the short, wide substitutes panel, so round markers are drawn as ellipses
    corrected by it.
    """
    def _round(cx, cy, r, **kw):
        ax.add_patch(Ellipse((cx, cy), width=2 * r, height=2 * r * aspect, **kw))

    sx, sy = x - w / 2, y - h / 2
    shirt_h = h * 0.58
    shirt_y = sy + h - shirt_h
    body, accent = (KIT_GK if p["pos"] == "GKP"
                    else KIT.get(p["team"], DEFAULT_KIT))

    _poly(ax, SHIRT, sx, shirt_y, w, shirt_h,
          facecolor=body, edgecolor="#20232a", lw=0.8, zorder=3)
    for sleeve in (SLEEVE_L, SLEEVE_R):
        _poly(ax, sleeve, sx, shirt_y, w, shirt_h,
              facecolor=accent, edgecolor="#20232a", lw=0.6, zorder=3.1)
    _poly(ax, COLLAR, sx, shirt_y, w, shirt_h,
          facecolor=accent, edgecolor="none", zorder=3.2)

    crest = badge(p["team"])
    if crest is not None:
        cy = shirt_y + shirt_h * 0.58
        _round(x, cy, w * 0.185, facecolor="#ffffff", edgecolor="#c9d4de",
               lw=0.6, alpha=0.96, zorder=3.5)
        ab = AnnotationBbox(
            OffsetImage(crest, zoom=badge_zoom),
            (x, cy),
            frameon=False, zorder=3.6, box_alignment=(0.5, 0.5))
        ax.add_artist(ab)

    bar_h = h * 0.21
    ax.add_patch(FancyBboxPatch(
        (sx, sy + bar_h), w, bar_h,
        boxstyle="round,pad=0,rounding_size=0.005",
        facecolor=NAME_BG, edgecolor="none", zorder=3.5))
    name = p["name"]
    if len(name) > 13:
        name = name[:12] + "."
    ax.text(x, sy + bar_h * 1.5, name, ha="center", va="center",
            fontsize=7.0, fontweight="bold", color=INK, zorder=4)

    # Two bottom bars, and which one appears is the difference between a
    # "Pick Team" card and a "Points" card. Before a deadline the useful line is
    # club, position and price; after the gameweek it is what he scored, the way
    # the FPL Points screen shows it. A card never carries both.
    gw = p.get("gw_points")
    ax.add_patch(FancyBboxPatch(
        (sx, sy), w, bar_h,
        boxstyle="round,pad=0,rounding_size=0.005",
        facecolor=(CHIP if gw is not None else INFO_BG),
        edgecolor="none", zorder=3.5))
    if gw is None:
        ax.text(x, sy + bar_h * 0.5,
                f"{p['team']} | {p['pos']} | £{p['price']:.1f}m",
                ha="center", va="center", fontsize=5.4, color="#42566b",
                zorder=4)
    else:
        # The captain's tile carries his doubled score, as FPL's own Points
        # screen does - the caller passes it already doubled.
        unit = "pt" if abs(gw) == 1 else "pts"
        label = f"{gw} {unit}" + ("  ×2" if p.get("is_captain") else "")
        ax.text(x, sy + bar_h * 0.5, label, ha="center", va="center",
                fontsize=6.8, fontweight="bold",
                color=(MINT if gw else "#8FA6BD"), zorder=4)

    if p.get("is_captain") or p.get("is_vice"):
        letter = "C" if p.get("is_captain") else "V"
        face = "#FFD400" if letter == "C" else "#ffffff"
        bx, by = x - w * 0.47, shirt_y + shirt_h * 0.72
        _round(bx, by, h * 0.095 / aspect, facecolor=face,
               edgecolor=INK, lw=1.1, zorder=5)
        ax.text(bx, by, letter, ha="center", va="center", fontsize=6.8,
                fontweight="bold", color=INK, zorder=6)

    if p.get("flag"):
        fx, fy = x + w * 0.47, shirt_y + shirt_h * 0.72
        _round(fx, fy, h * 0.085 / aspect, facecolor="#e63946",
               edgecolor="white", lw=1.0, zorder=5)
        ax.text(fx, fy, "!", ha="center", va="center", fontsize=6.6,
                fontweight="bold", color="white", zorder=6)


def render(xi: list[dict], bench: list[dict], *, title: str, subtitle: str = "",
           squad_value: float | None = None, bank: float | None = None,
           score: int | None = None, score_label: str = "POINTS",
           filename: str | None = None) -> Path:
    """
    Pass `score` for a post-gameweek Points picture: the header panel shows the
    total instead of the bank, and any player carrying a `gw_points` key gets
    his score on the card in place of his price.
    """
    by_pos: dict[str, list[dict]] = {"GKP": [], "DEF": [], "MID": [], "FWD": []}
    for p in xi:
        by_pos[p["pos"]].append(p)
    formation = f"{len(by_pos['DEF'])}-{len(by_pos['MID'])}-{len(by_pos['FWD'])}"

    fig = plt.figure(figsize=(7.6, 10.2), dpi=155)
    fig.patch.set_facecolor(NAVY)
    _background(fig)

    ax_h = fig.add_axes([0, 0.885, 1, 0.115])
    ax_h.set_xlim(0, 1)
    ax_h.set_ylim(0, 1)
    ax_h.axis("off")
    ax_h.text(0.035, 0.62, title, ha="left", va="center",
              fontsize=21, fontweight="bold", color="white")
    if subtitle:
        ax_h.text(0.035, 0.24, subtitle, ha="left", va="center",
                  fontsize=8.6, color=MINT)

    if score is not None or squad_value is not None:
        ax_h.add_patch(FancyBboxPatch(
            (0.70, 0.16), 0.265, 0.66,
            boxstyle="round,pad=0.01,rounding_size=0.06",
            facecolor="#12263F", edgecolor="#25415F", lw=1, zorder=2))
        if score is not None:
            big, small, foot = f"{score}", score_label, formation
        else:
            big, small = f"£{bank:.1f}m", "IN THE BANK"
            foot = f"{formation}   ·   £{squad_value:.1f}m squad"
        ax_h.text(0.832, 0.66, big, ha="center", va="center",
                  fontsize=19 if score is not None else 15,
                  fontweight="bold", color=MINT, zorder=3)
        ax_h.text(0.832, 0.47, small, ha="center", va="center",
                  fontsize=6.2, color="#8FA6BD", zorder=3)
        ax_h.text(0.832, 0.29, foot, ha="center", va="center",
                  fontsize=6.6, color="white", zorder=3)

    PITCH_ASPECT = (0.976 * 7.6) / (0.712 * 10.2)
    BENCH_ASPECT = (0.976 * 7.6) / (0.150 * 10.2)
    ax = fig.add_axes([0.012, 0.168, 0.976, 0.712])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    _pitch(ax)

    for pos, row in by_pos.items():
        n = len(row)
        if not n:
            continue
        margin = 0.235 if n <= 2 else (0.18 if n == 3 else 0.112)
        xs = [0.5] if n == 1 else [
            margin + i * (1 - 2 * margin) / (n - 1) for i in range(n)]
        for x, p in zip(xs, row):
            _card(ax, x, ROW_Y[pos], p, aspect=PITCH_ASPECT)

    ax_b = fig.add_axes([0.012, 0.010, 0.976, 0.150])
    ax_b.set_xlim(0, 1)
    ax_b.set_ylim(0, 1)
    ax_b.axis("off")
    ax_b.add_patch(FancyBboxPatch(
        (0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.02",
        facecolor="#12263F", edgecolor="#25415F", lw=1, zorder=0))
    ax_b.text(0.022, 0.72, "SUBSTITUTES", fontsize=7.6, fontweight="bold",
              color=MINT, va="center", zorder=2)
    if score is not None:
        left = sum(p.get("gw_points") or 0 for p in bench[:4])
        sub_note = f"{left} points\nleft here"
    else:
        sub_note = "ready when\nyou need them"
    ax_b.text(0.022, 0.45, sub_note, fontsize=5.6,
              color="#8FA6BD", va="center", zorder=2)
    for i, p in enumerate(bench[:4]):
        cx = 0.275 + i * 0.183
        ax_b.text(cx, 0.955, f"S{i + 1}", ha="center", va="center", fontsize=6,
                  color="#8FA6BD", fontweight="bold", zorder=2)
        _card(ax_b, cx, 0.46, p, w=0.152, h=0.80, badge_zoom=0.19,
              aspect=BENCH_ASPECT)

    if filename is None:
        filename = title.lower().replace(" ", "_").replace("/", "-") + ".png"
    path = OUT / filename
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def fixture_label(fpl_mod, team_short: str, gw: int) -> str:
    tm = fpl_mod.teams()
    tid = next((i for i, t in tm.items() if t["short_name"] == team_short), None)
    if tid is None:
        return team_short
    out = []
    for f in fpl_mod.fixtures(gw):
        if f["team_h"] == tid:
            out.append(f"{tm[f['team_a']]['short_name']} (H)")
        elif f["team_a"] == tid:
            out.append(f"{tm[f['team_h']]['short_name']} (A)")
    return " + ".join(out) if out else "no fixture"


def live_team(fpl_mod, team_id: int = config.ENTRY_ID) -> tuple[list[dict], list[dict], dict]:
    """
    The XI and bench for the upcoming gameweek.

    Before a deadline the API still reports the *previous* week's picks, so
    current_team.json overrides it when it matches the upcoming gameweek. After
    the deadline the API is authoritative again.
    """
    ev = fpl_mod.next_event()
    gw = ev["id"]
    squad = fpl_mod.squad(team_id)
    by_name = {r["name"]: r for r in squad["starting_xi"] + squad["bench"]}

    override = ROOT / "current_team.json"
    cfg = None
    if override.exists():
        cfg = json.loads(override.read_text(encoding="utf-8"))
        if cfg.get("event") != gw:
            cfg = None

    def conv(name, *, cap=False, vice=False):
        r = by_name[name]
        return {
            "pos": r["pos"], "name": r["name"], "team": r["team"],
            "price": r["price"], "points": r["points"],
            "is_captain": cap, "is_vice": vice, "flag": r["status"] != "a",
            "fixture": fixture_label(fpl_mod, r["team"], gw),
        }

    if cfg:
        order = {"GKP": 0, "DEF": 1, "MID": 2, "FWD": 3}
        xi = [conv(n, cap=(n == cfg["captain"]), vice=(n == cfg["vice_captain"]))
              for n in cfg["starting_xi"]]
        xi.sort(key=lambda p: order[p["pos"]])
        bench = [conv(n) for n in cfg["bench"]]
    else:
        xi = [conv(r["name"], cap=r["is_captain"], vice=r["is_vice"])
              for r in squad["starting_xi"]]
        bench = [conv(r["name"]) for r in squad["bench"]]

    return xi, bench, {"gw": gw, "squad": squad, "event": ev}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "badges":
        download_badges()
    elif arg == "demo":
        import fpl
        xi, bench, meta = live_team(fpl)
        s = meta["squad"]
        cap = next(p["name"] for p in xi if p["is_captain"])
        p = render(xi, bench,
                   title=f"MY FPL SQUAD  ·  GW{meta['gw']}",
                   subtitle=f"GIS97  ·  {cap} (C)  ·  deadline "
                            f"{meta['event']['deadline_time'][:16].replace('T', ' ')} UTC",
                   squad_value=s["squad_value"], bank=s["bank"],
                   filename=f"gw{meta['gw']}_current.png")
        print("wrote", p)
    else:
        print(__doc__)
