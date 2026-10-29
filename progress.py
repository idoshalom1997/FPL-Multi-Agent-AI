# -*- coding: utf-8 -*-
"""
Live progress board for a running staff meeting (Ido asked for this, 15 Oct 2026:
"each time I ask you to produce the pre-deadline report, show me progress bars,
each agent's bar, live").

Reads the newest headless session transcript for this project and reports, per
specialist, whether it has been launched, how much work it has done (tool calls
in its own transcript) and whether it has handed back. Read-only.

    python progress.py            print the board once
    python progress.py --watch    print it again whenever it changes (for Monitor)
"""
import json, sys, time, hashlib
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent
PROJ = Path.home() / ".claude" / "projects" / "C--Users-X-Desktop-Claude-Projects-FPL-Manager"
STAFF = ["rules-enforcer", "doctor", "data-scientist", "scout",
         "opposition-analyst", "media-analyst", "resource-manager", "historian"]
LABEL = {"rules-enforcer": "Rules Enforcer", "doctor": "Doctor",
         "data-scientist": "Data Scientist", "scout": "Scout",
         "opposition-analyst": "Opposition", "media-analyst": "Media Analyst",
         "resource-manager": "Resource Mgr", "historian": "Historian", "assistant-manager": "Manager (Fable)"}
EXPECTED_CALLS = 18          # a typical specialist's tool calls; bar caps at 90% until it hands back
WIDTH = 20


def records(path):
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            yield json.loads(line)
        except ValueError:
            continue


def tool_uses(path):
    out = []
    for r in records(path):
        m = r.get("message") or {}
        c = m.get("content")
        if r.get("type") == "assistant" and isinstance(c, list):
            out += [x for x in c if x.get("type") == "tool_use"]
    return out


def results(path):
    done = set()
    for r in records(path):
        c = (r.get("message") or {}).get("content")
        if r.get("type") == "user" and isinstance(c, list):
            done |= {x.get("tool_use_id") for x in c if x.get("type") == "tool_result"}
    return done


def all_transcripts(session: Path):
    """The session file plus every subagent transcript under its folder."""
    files = [session]
    d = session.with_suffix("")
    if d.exists():
        files += sorted(d.rglob("*.jsonl"))
    return files


def bar(frac):
    n = int(round(frac * WIDTH))
    return "█" * n + "░" * (WIDTH - n)


def board():
    # The newest transcript that is a staff meeting - not a check run the
    # scheduler may start alongside it in the same project.
    sessions = sorted(PROJ.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    def is_meeting(p):
        with p.open(encoding="utf-8", errors="replace") as fh:
            head = fh.read(200_000)
        return "FULL STAFF MEETING" in head
    session = next((p for p in sessions if is_meeting(p)), None)
    if session is None:
        return "No meeting transcript found."
    files = all_transcripts(session)

    # Each subagent leaves <id>.meta.json (its agentType and the launching
    # toolUseId) beside its <id>.jsonl transcript.
    finished = set()
    for f in files:
        finished |= results(f)
    launches, calls = {}, {}
    for meta in session.with_suffix("").rglob("*.meta.json"):
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
        except ValueError:
            continue
        kind = m.get("agentType", "")
        launches.setdefault(kind, []).append(m.get("toolUseId"))
        t = meta.with_name(meta.name.replace(".meta.json", ".jsonl"))
        if t.exists():
            calls[kind] = calls.get(kind, 0) + len(tool_uses(t))

    lines = [f"GW7 staff meeting - {time.strftime('%H:%M:%S')}", ""]
    for who in ["assistant-manager"] + STAFF:
        ids = launches.get(who, [])
        n = calls.get(who, 0)
        if not ids:
            frac, state = 0.0, "waiting"
        elif all(i in finished for i in ids):
            frac, state = 1.0, "done"
        else:
            frac, state = min(0.9, 0.05 + n / EXPECTED_CALLS), f"working ({n} steps)"
        if who == "assistant-manager" and not ids:
            # The top-level session may run the meeting itself rather than via the agent.
            mgr = len(tool_uses(session))
            frac, state = min(0.9, mgr / 80), f"running the meeting ({mgr} steps)"
        lines.append(f"{LABEL[who]:<16} {bar(frac)} {int(frac*100):>3}%  {state}")

    gw = "gw7"
    steps = [("Lineup pictures", any((ROOT / "reports").glob(f"{gw}_*.png"))
              and len([p for p in (ROOT / "reports").glob(f"{gw}_*.png")]) > 1),
             ("Options recorded", (ROOT / "recommendations" / f"{gw}.json").exists()),
             ("Email sent", "Main report - GW7" in (ROOT / "logs" / "sent.log").read_text(
                 encoding="utf-8", errors="replace"))]
    lines.append("")
    lines.append("   ".join(("✔ " if ok else "· ") + name for name, ok in steps))
    return "\n".join(lines)


if __name__ == "__main__":
    if "--watch" in sys.argv:
        last = None
        while True:
            b = board()
            h = hashlib.md5(b.split("\n", 1)[1].encode()).hexdigest()
            if h != last:
                print(b + "\n", flush=True)
                last = h
                if "✔ Email sent" in b:
                    break
            time.sleep(20)
    else:
        print(board())
