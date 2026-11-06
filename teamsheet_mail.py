r"""Pull the Pick Team screenshot out of Ido's reply so the main report can read it.

He is asked to reply to the deadline alert with a screenshot, and most weeks the
reply is a picture with no words at all. The Gmail connector the agents use
exposes attachment *metadata* but not the attachment bytes, so the image cannot
be read through it. IMAP with the Gmail App Password already set up for
send_report.ps1 is the way in.

    python teamsheet_mail.py "Deadline alert - GW5"

Saves any image attachment over 20KB to data/teamsheets/ and prints the paths.
Open the newest one and read the XI, bench order, captain and vice off it, then
record it with team_update.py - which validates before writing.

Read-only by construction: the mailbox is opened readonly=True and nothing here
writes to, labels or deletes mail. It reads his own inbox, nothing else, and it
never touches his FPL account.

Credential: run from PowerShell so the DPAPI-encrypted App Password can be
decrypted by this Windows user -

    $cred = Import-Clixml -LiteralPath '.\smtp.cred.xml'
    $env:GMAIL_USER = $cred.UserName
    $env:GMAIL_PASS = $cred.GetNetworkCredential().Password
    python teamsheet_mail.py "Deadline alert - GW5"
"""
import email
import email.header
import email.utils
import imaplib
import os
import pathlib
import sys

MIN_BYTES = 20_000          # below this it is a signature logo, not a screenshot
OUTDIR = pathlib.Path("data/teamsheets")


def fetch(subject):
    try:
        user, pw = os.environ["GMAIL_USER"], os.environ["GMAIL_PASS"]
    except KeyError:
        sys.exit("GMAIL_USER / GMAIL_PASS not set - see the docstring for the "
                 "PowerShell lines that decrypt the App Password.")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    M = imaplib.IMAP4_SSL("imap.gmail.com")
    M.login(user, pw)
    M.select('"[Gmail]/All Mail"', readonly=True)
    _, data = M.search(None, "SUBJECT", f'"{subject}"')
    ids = data[0].split()
    print(f"{len(ids)} message(s) matching {subject!r}")

    saved = []
    for mid in ids:
        _, raw = M.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(raw[0][1])
        date = msg.get("Date", "")
        for part in msg.walk():
            if not part.get_content_type().startswith("image/"):
                continue
            payload = part.get_payload(decode=True)
            if not payload or len(payload) < MIN_BYTES:
                continue
            name = OUTDIR / f"msg{mid.decode()}_{part.get_filename() or 'image.png'}"
            name.write_bytes(payload)
            saved.append(name)
            print(f"  saved {name}  ({len(payload)} bytes)  {date}")
    M.logout()

    if not saved:
        print("No image attachments found. He may have replied in words instead - "
              "read the reply text through the Gmail connector.")
    return saved


def _text_of(msg):
    """His own words from a reply: the plain-text part, quoted original cut off."""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            body = (part.get_payload(decode=True) or b"").decode(
                part.get_content_charset() or "utf-8", errors="replace")
            keep = []
            for line in body.splitlines():
                if line.startswith(">") or (line.startswith("On ") and "wrote:" in line):
                    break
                keep.append(line)
            return "\n".join(keep).strip()
    return ""


def replies():
    """Every reply he has sent to an [FPL] mail since the last deadline.

    Added 30 Oct 2026 after his GW9 reply was missed: the Gmail connector's
    search listed the thread as one message, the run trusted the count and
    never opened it, and the report was nearly built on the GW8 team. IMAP
    reads the mailbox itself, so a reply cannot hide inside a thread here.
    """
    import datetime
    import fpl
    try:
        user, pw = os.environ["GMAIL_USER"], os.environ["GMAIL_PASS"]
    except KeyError:
        sys.exit("GMAIL_USER / GMAIL_PASS not set - see the docstring.")

    ev = fpl.current_event() or fpl.next_event()
    since = datetime.datetime.fromisoformat(ev["deadline_time"].replace("Z", "+00:00"))
    OUTDIR.mkdir(parents=True, exist_ok=True)
    M = imaplib.IMAP4_SSL("imap.gmail.com")
    M.login(user, pw)
    M.select('"[Gmail]/All Mail"', readonly=True)
    _, data = M.search(None, "SINCE", since.strftime("%d-%b-%Y"), "SUBJECT", '"[FPL]"')
    found = 0
    for mid in data[0].split():
        _, raw = M.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(raw[0][1])
        subject = str(email.header.make_header(email.header.decode_header(msg.get("Subject", ""))))
        if not subject.lower().startswith("re:"):
            continue                      # the system's own mails, not his replies
        when = email.utils.parsedate_to_datetime(msg.get("Date"))
        if when < since:
            continue
        found += 1
        print(f"REPLY  {when:%a %d %b %H:%M}  {subject}")
        text = _text_of(msg)
        print("  his words: " + (text.replace("\n", " / ") if text else "(none)"))
        for part in msg.walk():
            if part.get_content_type().startswith("image/"):
                payload = part.get_payload(decode=True)
                if payload and len(payload) >= MIN_BYTES:
                    name = OUTDIR / f"msg{mid.decode()}_{part.get_filename() or 'image.png'}"
                    name.write_bytes(payload)
                    print(f"  screenshot: {name}")
    M.logout()
    if not found:
        print(f"NO REPLY to any [FPL] mail since the GW{ev['id']} deadline.")


if __name__ == "__main__":
    if sys.argv[1:] == ["--replies"]:
        replies()
    else:
        fetch(sys.argv[1] if len(sys.argv) > 1 else "Deadline alert")
