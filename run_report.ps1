<#
.SYNOPSIS
    Runs one scheduled FPL staff report by launching Claude headlessly.

.DESCRIPTION
    Windows Task Scheduler calls this; it does not need an open Claude window.
    Claude starts, the Assistant Manager convenes the staff, and the report is
    emailed. Output is logged so a failed unattended run leaves evidence.

.PARAMETER Type
    planning : Wed - the landscape, no decisions yet
    main     : Fri - the full staff meeting and the lineup pictures
    check    : the pre-deadline fitness re-check. Exits silently unless the
               deadline is close, so it can be scheduled daily and stay quiet.
    review   : Tue - what happened, and the Historian's verdict

.EXAMPLE
    .\run_report.ps1 -Type main
    .\run_report.ps1 -Type check -WhatIf     # show the prompt, run nothing
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('planning', 'main', 'check', 'review')]
    [string]$Type,

    [int]$CheckWindowHours = 8,
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location $Root

$LogDir = Join-Path $Root 'logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
$stamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$log = Join-Path $LogDir "$Type`_$stamp.log"

function Log {
    param([string]$m)
    $line = '{0} {1}' -f (Get-Date -Format 'HH:mm:ss'), $m
    Write-Host $line
    Add-Content -LiteralPath $log -Value $line -Encoding UTF8
}

# --- How long until the deadline? -----------------------------------------
$hours = $null
try {
    $out = (& python fpl.py hours 2>&1 | Out-String).Trim()
    if ($out -match '^-?\d+(\.\d+)?$') { $hours = [double]$out }
} catch {
    Log "Could not read the deadline: $($_.Exception.Message)"
}
if ($null -ne $hours) { Log ("Deadline is {0:N1}h away." -f $hours) }

# The pre-deadline check runs daily but should only speak when it matters.
#
# It now has two reasons to speak. The deadline being close is one. The other is
# health.py finding something wrong - a stale current_team.json, or a scheduled
# report that failed or never fired. That second case is deliberately NOT gated
# on the deadline window: a report died and stayed dead for a weekend
# precisely because the only record was a log nobody reads. Ido gets no new
# notification channel out of this; the findings ride along in the one alert
# email that already exists.
$healthText = ''
$healthNeedsHim = $false
if ($Type -eq 'check') {
    $healthText = (& python health.py --quiet | Out-String).Trim()
    $healthNeedsHim = ($LASTEXITCODE -eq 2)

    if ($healthNeedsHim) {
        Log 'Health check: something needs his attention.'
        foreach ($line in ($healthText -split "`r?`n")) { Log "  $line" }
    } else {
        Log 'Health check: all clear.'
    }

    $deadlineClose = ($null -ne $hours) -and ($hours -le $CheckWindowHours) -and ($hours -ge 0)
    if (-not $deadlineClose -and -not $healthNeedsHim) {
        if ($null -eq $hours) {
            Log 'No deadline available and nothing wrong - nothing to do.'
        } else {
            Log ("Deadline is {0:N1}h away, outside the {1}h window, and nothing is wrong - nothing to do." -f $hours, $CheckWindowHours)
        }
        exit 0
    }
    if ($healthNeedsHim -and -not $deadlineClose) {
        Log 'Deadline is not close, but the health check found something - continuing.'
    }
}

# NOTE: there is deliberately no automatic team sync here. FPL retired its
# email-and-password login (users.premierleague.com no longer resolves at all)
# and moved sign-in to a browser flow, so no stored credential can read his
# pre-deadline team. Do not add one back; the route is his emailed reply, read
# by the main run below. See CLAUDE.md.

# --- The brief for each kind of run ---------------------------------------
$prompts = @{
    planning = @'
Run the WEDNESDAY PLANNING BRIEF for the upcoming gameweek.

Use the rules-enforcer, data-scientist, opposition-analyst and historian. They
may think at length; the MAIL is short (see the end).

UPDATE THE SEASON PLAN. The data-scientist, opposition-analyst and historian
are the gap committee: run `python gap.py`, `python benchmark.py` and
`python elite.py behaviour` (what the top 100 do differently from Ido), read
season_plan.md, and update it - strategy, checkpoint targets, resource map -
for the week ahead.

REVIEW THE CHIP PLAN. Run `python chipcalc.py 15` and `python league_status.py`,
read `chips.md`, have the rules-enforcer and opposition-analyst argue it, and
update the file if the picture has changed. Only one chip per gameweek, and
anything unplayed at the GW19 deadline is lost - count chips left against
gameweeks left every week.

EXPECTED RIVALS. The opposition-analyst predicts, for each of the three friends,
their likely move this gameweek: captain, chip, key transfers - from their squads,
free transfers and chips left (league_status.py), and their habits so far. Write
it into season_plan.md under "### GW<n> planning" as "Expected rivals". The main
report's DIFFERENTIAL is built against this prediction, and the review checks
whether it came true.

THIS WEEK'S GOALS. The gap committee sets TWO goals for this gameweek. Each must
be actionable and checkable afterwards with a number or a yes/no - e.g. "close
5+ on Rookie mistakes", "beat the top 100 average", "play the Free Hit and score 65+", "use
the free transfer on a defender facing a bottom-five attack", "decide on X
after his GW9 minutes". Say for each whether it is short-term (this week) or
serves the long-term plan. Write them in season_plan.md under "## 6. Weekly
goals" as a row: GW | goal 1 | goal 2 | result (left blank - the review fills it
in: met / missed and the number). If that section does not exist yet, create it.

THE PLANNING MAIL HAS EXACTLY FOUR PARTS AND NOTHING ELSE (Ido, 29 Oct 2026:
the old brief was too much information for no good use). No paragraphs, no
per-agent lines, no lineup pictures. Use short lines and small tables.

1. THE CHIPS CLOCK - a small table: each chip he still has, the gameweek where
   it makes most sense as things stand, and the reason in a few words. One line
   above it: "<n> chips, <m> gameweeks until the GW19 deadline".
2. THE SEASON PLAN - at most three lines: the gap to each friend and the points
   per gameweek needed to catch them by GW38 (gap.py); the plan to get there in
   one line; on track / behind / ahead of the next checkpoint.
3. EXPECTED RIVALS - one block per friend, one or two lines each, labelled by
   first name, e.g.
     Wei & Dudley's plan - captain X, likely Free Hit, buying Y.
     Nott'm Random Forest's plan - ...
     Rookie mistakes's plan - ...
   Then one line: what that means for our DIFFERENTIAL.
4. FINAL THOUGHTS - first, the deadline in a framed box (day, date, time in
   Israel time). Then the TWO goals for this week, each one line: what it is,
   what the gameweek is for (pass a friend, climb the world rank, test a player,
   use a transfer or chip), and how we will know it was met.

Finish by emailing the brief with send_report.ps1, subject
"Planning brief - GW<n>".
'@

    main = @'
Run the FULL STAFF MEETING for the upcoming gameweek.

FIRST, FIND OUT WHAT TEAM HE IS ACTUALLY FIELDING.

FPL retired its password login, so nothing here can read his pre-deadline XI,
bench order or captain. He can only tell us, and he was asked to reply to the
pre-deadline reminder with a screenshot of his Pick Team screen.

So before anything else: search his Gmail for his most recent reply to an [FPL]
message, sent after the last deadline. Read it - the team may be written in
words, or be a screenshot you need to look at. If you find it, record it:

  python team_update.py --xi "<11 names>" --bench "<4 in bench order>" --captain "<name>" --vice "<name>"

Sloppy names are fine; it matches against his actual fifteen and refuses
anything ambiguous. If it reports a problem, DO NOT GUESS and do not edit
current_team.json by hand - say in the report which part of his message you
could not read, and build the options on the team as it stands.

If there is no reply, carry on with current_team.json as it is and say clearly
in the mail which gameweek that team is from, so a stale captain is visible
rather than silent.

If current_team.json was recorded more recently than his latest reply (Claude
may have read his Pick Team screen with him in a chat session), it wins.

THIS IS A ONE-SHOT HEADLESS RUN: THE PROCESS EXITS THE MOMENT YOUR TURN ENDS.
Run every agent in the FOREGROUND - never run_in_background - and wait for its
result inside this turn. A background agent is killed when you stop, and no
notification will ever wake you: on 15 Oct the run handed the meeting to a
background assistant-manager, said "I'll pick up when its notification
arrives", exited, and the staff died mid-meeting with no email sent. Do not end
your turn until the email is sent.

Convene all seven specialists via the assistant-manager. Each speaks in two or
three sentences. Make them answer each other where they disagree rather than
averaging them.

THINK HARD - WE ARE LOSING AND IDO WANTS IMPROVEMENT, NOT REPETITION.

Ido (15 Oct 2026): "we are doing really bad and not going anywhere." He is last
in the mini-league. Every specialist must reason carefully and at length before
answering, and the meeting must settle ALL of these, every week:

1. TRANSFER USAGE. Use the free transfer, or bank it? Lay out a 3-gameweek
   transfer plan (this week and the next two) with free transfers counted and
   any -4 stated. A banked transfer must have a named purpose.
2. CHIPS AGAINST THE FIXTURES. For Bench Boost, Triple Captain and Free Hit:
   which gameweek, on which fixtures, and why not this week. Bench Boost is
   judged on the four bench players' real opponents in the target week, and
   on which transfers would make that bench worth boosting. Update chips.md.
3. CAPTAINCY. The best captain from the whole squad, judged on the opponent and
   on rival ownership (an armband on a player no rival owns gains double on all
   three; on one a rival owns, it gains less on that rival). His captain has
   returned 3 or less in most weeks - say why this pick breaks that pattern.
4. THE LEDGER AND THE IMPROVEMENT. The historian reads ledger.md (every chip,
   captain and transfer so far, each judged right or wrong) and states the
   staff's record. The report must name at least one concrete thing the staff
   are doing differently this week BECAUSE of a past mistake in the ledger.
   No improvement line, no report.

Do NOT read any earlier drafts for this gameweek, including anything under
reports/gw<n>_meeting_*/ - the staff build their own answer from the data.

FIXTURES ARE MANDATORY, FOR EVERY PLAYER, EVERY WEEK.

Before any option is built, go through ALL FIFTEEN players - goalkeepers
included, bench included - and state for each one: his opponent this gameweek,
home or away, its FDR, and his run over the next several gameweeks from
`fpl.ticker()`. Nothing rides along unexamined because it started last week.
Both keepers get the same scrutiny as everyone else; say in one line whether
the starting keeper is still the right one and whether the bench keeper is
worth his money.

Never quote `ep_next` as a forecast. It is blind to the opponent and FPL often
sets it equal to `form`, so "highest expected points" collapses to "best recent
form" while sounding like a projection. If a number ignores the opponent, say
so in the same sentence or do not use it.

THEN SEARCH THE WHOLE TRANSFER MARKET, NOT JUST OUR FIFTEEN.

Scan the full player list for the positions where our players face the worst
fixtures, filtered to what the bank and the 50% sell-on fee actually allow. Be
willing to conclude that THE SQUAD ITSELF IS WRONG FOR THE FIXTURES and name
the outside players who fit better - that conclusion is wanted, not a failure.
Name affordable candidates with opponent, run and price so Ido can compare.
Where nothing outside beats what we have, say so in one line and show the
comparison that settled it. Cheap positions matter most; that is where a little
money buys a large upgrade.

Every transfer offered must be argued on FIXTURES, not on form or price alone.

THE STAFF ARE UNDER PRESSURE. Ido is fourth of four and said they are slacking:
read the gap first, search hard, use the resources, and every specialist ends
with a MISSING INFO line that you fetch in this run (or list at the foot of the
mail for Ido). See "The standard" in CLAUDE.md.

Produce TWO complete, legal lineup options: BALANCED (the staff's best
team overall) and DIFFERENTIAL (the best team for the mini-league, built by the
gap committee - data-scientist, opposition-analyst and historian - from
season_plan.md; they have the FINAL SAY on it after consulting the rest of the
staff, and it may take a hit or sacrifice this fixture if the plan says so).
DIFFERENTIAL is built against the planning brief's "Expected rivals" prediction
in season_plan.md (what the three friends are expected to captain, chip and
buy) - update that prediction first if their squads or the news say otherwise,
and aim it at this week's two goals ("## 6. Weekly goals").
Render each with
lineup.py, captain and vice marked. State the transfer each assumes and its
cost, written plainly as -4 where it applies.

PLUS A THIRD LINEUP IN A CHIP WEEK (Ido, 29 Oct 2026). If the staff recommend a
chip this gameweek, OR Ido has said he plans one (his reply, chips.md,
season_plan.md), add a CHIP lineup built for that chip: titled with the chip
("FREE HIT", "BENCH BOOST", "TRIPLE CAPTAIN", "WILDCARD"), rendered with
lineup.py like the others. BALANCED and DIFFERENTIAL then show the week WITHOUT
the chip, so he can compare playing it against keeping it. Rules:
- It must be legal for that chip. FREE HIT: any 15 within his total budget
  (selling value of the fifteen + bank, after the 50% sell-on fee), max 3 per
  club, no hits, and the squad reverts next week. WILDCARD: same budget, but
  permanent - see "Wildcard week" in CLAUDE.md. BENCH BOOST: all four bench
  players must be fit and playing. TRIPLE CAPTAIN: name the captain.
  The rules-enforcer checks it before it is drawn.
- Under the picture, TWO short lines only: why this chip this week, and what it
  is worth in points against not playing it (python chipcalc.py).
- One chip per gameweek. If two chips were argued, show the staff's pick and
  name the runner-up in one line.
- Record it in recommendations/gw<n>.json as an option named "CHIP" with its
  "chip" field set (freehit / wildcard / bboost / 3xc), so it is scored next
  week like the others.

Remember: Ido decides, never you. Rolling the free transfer is a real option and
should be recommended when nothing is worth doing - but a banked transfer needs
a named purpose, and the resource-manager says what it is.

HAALAND: Ido lifted the old ban on 23 Oct 2026. Until Haaland is in the
fifteen, EVERY option includes him and the staff argue only how to fund him.
Once he is in, he is an ordinary player - benched, un-captained or sold when the
evidence says so.

TEAM STRENGTH: run python fpl.py matchups. A keeper or defender facing a top-five
attack (attack_rank 1-5) is benched by default; starting him needs a reason
written in the report.

Before sending, record every option exactly as offered into
recommendations/gw<n>.json via outcome.record() - the Historian scores your
advice against it next week. See the learning-loop section of CLAUDE.md.

ALWAYS SEND. The report is not finished until the mail is out. Do not stop to
ask whether to send, do not downgrade a main report to a short "correction",
and do not decide on Ido's behalf that he has had enough email this week - the
brevity rule is about the LENGTH of each mail, never about withholding one he
is waiting for. A main run that ends without sending has failed.

Email the report with send_report.ps1, attaching every lineup image, subject
"Main report - GW<n>".

THE MAIN MAIL IS SHORT AND HAS ONLY THESE PARTS, IN THIS ORDER (Ido, 29 Oct
2026: "too much!"). NO per-agent lines, no disagreements section, no stories -
the staff's reasoning is saved in recommendations/gw<n>.json and the project
files, not the mail. Ido reads as the head manager.

1. THE DEADLINE - a framed box at the very top: day, date, time (Israel time)
   and how long is left, e.g. "Deadline: Sat 31 Oct, 13:30 - 27 hours left".
2. THE CALL - one or two plain sentences, no story, e.g. "The staff recommend
   BALANCED with the Free Hit and expect about 62 points. Transfers: none."
3. THE LINEUPS - for each option (BALANCED, DIFFERENTIAL, and CHIP in a chip
   week), in this order:
   - its name and one or two sentences on why the staff think it is a good idea
     (transfer and cost, -4 written plainly, inside that sentence or the picture's
     subtitle);
   - the picture;
   - under it, two small boxes side by side: BEST CASE (expected points, and
     the + against the rivals, e.g. "75 pts · +12 on Rookie mistakes, +8 on Wei & Dudley") and
     WORST CASE (e.g. "40 pts · -10 on Nott'm Random Forest").
4. ONE LINE at the foot: "Reply with what you played (e.g. 'went BALANCED')" -
   plus, only if something is genuinely missing, one line "Need from you: ...".

For every option, record the predicted points and the best and worst case as
NUMBERS in recommendations/gw<n>.json ("predicted_points", "best_case",
"worst_case": each with points and the gap move per rival). The review checks
them against what happened, so we learn over time whether the staff's forecasts
are right.
'@

    check = @'
Run the PRE-DEADLINE CHECK.

You were launched for one of two reasons: the deadline is close, or health.py
found something wrong. Read the HEALTH CHECK section below if it is present -
it tells you which.

FIRST, CATCH UP ON WHAT HE HAS DONE SINCE THE MAIN REPORT.

This run happens AFTER the main report, so the team sheet on file may already be
out of date - it is whatever he last told us, and the report has since
recommended changes he may have acted on. Checking a fit XI that he no longer
fields is worse than useless.

So before the doctor looks at anything, search his Gmail for his most recent
reply to an [FPL] message and read it:

- A screenshot of his Pick Team screen: read the XI, bench order and captain.
- Names in words: same.
- A short answer like "went option 1" or "kept the armband on Joao Pedro": the
  options are recorded in full in recommendations/gw<n>.json, so look up the
  option he names and take its XI, bench, captain and vice from there.

Record whatever you establish:

  python team_update.py --xi "<11 names>" --bench "<4 in bench order>" --captain "<name>" --vice "<name>"

It refuses anything ambiguous or illegal rather than guessing. If it refuses, do
NOT edit current_team.json by hand - check the doctor's findings against the
team as it stands and say in the mail that you could not read his reply.

His transfers are public and are picked up automatically, so it is only the XI,
bench order and captain that depend on his reply.

THEN run the check itself.

Use the doctor and rules-enforcer only. Search the web for the latest team news
and press conferences, and compare against what Ido currently fields - see
current_team.json and lineup.live_team().

THIS RUN HAPPENS MORE THAN ONCE. Inside the last eight hours it fires on every
pass - typically twice, around five hours and two hours before the deadline - so
that a late injury and a late change of mind are both caught. That is deliberate,
but it means you must not re-send news he already has. Before emailing, search
his Gmail for your own earlier "[FPL] Deadline alert" for THIS gameweek: if you
already told him a thing, do not tell him again unless it has actually changed
(a doubt became a confirmed absence, say). Keeping his inbox quiet is a standing
rule, and two identical alerts is exactly the volume problem he has ruled out.

If nothing has changed AND the health section is absent or clean, send NO email
and simply report "all clear" here. Only email when something actually needs his
attention: a new injury, a suspension, a flagged player in his XI, a deadline
shift, or anything the health check raised. If you do email, lead with what
changed and what to do about it, subject "Deadline alert - GW<n>".

Handling health findings in the mail, if there are any:

- A stale current_team.json is the one that costs him points. FPL retired its
  password login, so his XI, bench order and captain are genuinely unknowable
  unless he tells us. **Ask him to reply to that email with a screenshot of his
  Pick Team screen** - that is the whole action, it takes him ten seconds, and
  the main report reads the reply. Say plainly that until he does, the report
  will be drawing an out-of-date team.
- A failed or missing scheduled report means he did not get an email he was
  expecting. Tell him which one and when, in one line.
- NEVER edit current_team.json yourself and never touch his FPL team. You
  advise, he executes - this is a standing rule, see CLAUDE.md. Report the
  problem and stop.
- Keep all of this to a few lines. The short-email rule applies here too.
'@

    review = @'
Run the POST-GAMEWEEK REVIEW for the gameweek just completed.

START by running `python outcome.py <gw>` - it scores what the staff recommended
against what Ido actually fielded and writes the result into
recommendations/gw<n>.json. That comparison is the spine of this run.

THEN run `python benchmark.py`. "Do nothing" is a weak yardstick, so Ido asked
(29 Oct 2026) for outside ones as well: his points against the TOP 100 average
(the main yardstick), against the world average, his share of FPL's Team of the
Week (the hindsight ceiling only), his world rank (overall and for the week)
and each league gap since the staff started. Its numbers feed the VERDICT (part
1 of the mail below). Whether they are getting better or worse, and what the
staff will change if worse, goes in season_plan.md and into the three lessons.

Use the historian, data-scientist and opposition-analyst. Cover what was scored,
what was left on the bench, how the gap to each of the three rivals moved,
whether Ido followed a recommended option or diverged and how that turned out,
and the Historian's verdict on whether the decision was right given what was
knowable before the deadline - not merely whether it worked out.

If Ido replied to the main report saying what he did, read it: the API shows the
what, only his reply shows the why.

CHECK THE PLANNING BRIEF'S PROMISES. Read this gameweek's two goals in
season_plan.md ("## 6. Weekly goals") and fill in the result column: met /
missed, with the number. Read the "Expected rivals" prediction and note in the
progress log how much of it came true - that is how the opposition-analyst's
predictions get better.

GAP COMMITTEE: run `python gap.py`, `python season_review.py` and
`python elite.py behaviour` (how the top 100 play the season beside Ido).
ARE WE PLAYING THE GAME RIGHT? Compare Ido with each rival on transfers (net and
hits), captaincy (points and points lost to the best captain in his XI), chips
(what each added), and bench points. Read decisions.md, ledger.md and every
recommendations/gw*.json for what was advised against what he chose. Say where
he is losing ground to his friends and why, and build the plan on it. The FIRST
time (the GW8 review) write this as the opening section of season_plan.md -
"Where we stand and why" - covering GW1 onward, before the strategy. The data-scientist, opposition-analyst
and historian update season_plan.md - the progress log entry for this
gameweek (gap move v each rival, BALANCED v DIFFERENTIAL v what Ido chose),
closer or further from the next checkpoint, and what the plan changes because
of it. If the strategy section is still empty, write it now.

Append the entry to decisions.md. The historian also adds this gameweek's rows
to ledger.md - the chip (if any was played, by Ido or a rival), the captain and
each transfer, each with its verdict (right / wrong / too early) and what the
best alternative would have scored - and updates the running record at its top.

Email the review with send_report.ps1, subject "Review - GW<n>".

THE REVIEW MAIL HAS EXACTLY FIVE PARTS, IN THIS ORDER, AND NOTHING ELSE
(Ido, 29 Oct 2026: the old mail was too long to read). Everything else the staff
worked out - the Historian's reasoning, the ledger, the season plan, the rivals'
analysis - goes into the project files, NOT the mail. Use
reports/review_example.html for the styling only.

1. THE VERDICT - a short box, numbers only, no story. At most four lines:
   - "GW<n>: <points> pts · <score>/10" (score10 from benchmark.py: the share of
     all managers he beat) "· vs top 100 <+/-x> · vs world <+/-y> · world rank <r>"
   - "Staff: <recommended option> <pts> (predicted <p>, inside/outside its
     best-worst range) · you <pts> · do nothing <pts>" (from outcome.py:
     predicted, within_best_worst; include the CHIP option if there was one)
   - "League: gap to <each rival> <now> (<move this week>)"
   - "Goals: 1 <met/missed, number> · 2 <met/missed, number>" - the two goals
     the planning brief set for this gameweek
2. THE LINEUP PICTURES - unchanged, Ido likes them. One Points-style squad
   picture of the team he actually played (every player with his real points,
   bench included, total in the header: lineup.render(..., score=...,
   score_label="YOUR POINTS") with a gw_points key - see CLAUDE.md, "The Points
   view"), then the same picture for EACH option the staff recommended, CHIP
   lineup included. A title above each picture with its score, nothing more.
3. THE MINI-LEAGUE TABLE - each manager's gameweek score and total. Just the
   table: no sentences before or after it.
4. TRANSFERS AND CHIPS - the rules-enforcer's table. Run
   `python league_status.py --html` and paste its table as it is: for each of the
   four managers, transfers made this gameweek (and any hit), the chip played
   this gameweek, the free transfers each holds for the next gameweek, and the
   chips each has left. If it prints a WARNING, the free-transfer counts are
   unsafe: add one line under the table saying so.
5. WHAT WE LEARNED - exactly three bullets, one short line each: what the staff
   take from this gameweek into the rest of the season. Concrete, and different
   from last week's.

No other sections, no per-agent lines, no paragraphs.
'@
}

$prompt = $prompts[$Type]

# Hand the run what health.py found, so the agents report it rather than
# rediscovering it. Only the check run gets this.
if ($Type -eq 'check' -and $healthNeedsHim -and $healthText) {
    $prompt += @"


HEALTH CHECK - these findings need to reach Ido:

$healthText

These were produced by ``python health.py``, which only reads. Nothing has been
changed on his behalf; do not change anything either.
"@
}

Log "=== $Type run starting ==="

if ($WhatIf) {
    Log 'WhatIf: the prompt below would be sent to Claude.'
    Write-Host $prompt
    exit 0
}

# bypassPermissions is required for an unattended run: there is nobody present
# to answer a permission prompt, and the task would otherwise hang until its
# timeout. The agents only read public FPL data, search the web, and send mail.
# The top-level session runs the meeting, so it is the manager: Fable, per Ido
# (15 Oct 2026). The specialists are pinned to Opus in .claude/agents/.
$claudeArgs = @(
    '-p', $prompt
    '--model', 'fable'
    '--permission-mode', 'bypassPermissions'
    '--add-dir', $Root
)

# Streamed, not buffered. The old version collected all output and wrote it
# only after claude exited, so a run that stalled or was killed left a log
# containing nothing but "starting" - which is precisely what happened the first
# time, and made a stalled run indistinguishable from one that never began.
# stderr is deliberately NOT merged with 2>&1: in PowerShell 5.1 that wraps each
# stderr line in an ErrorRecord and, under $ErrorActionPreference = 'Stop',
# can abort a run that was succeeding.
$startedAt = Get-Date
$receipt = Join-Path $LogDir 'sent.log'

try {
    & claude @claudeArgs | Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
} catch {
    Log "RUN FAILED: $($_.Exception.Message)"
    exit 1
}

# A run is not done until the mail is out.
#
# The GW5 main report reached this point having produced every lineup image,
# recorded its options and written its verdicts - and then stopped to ask
# whether it should send, on its own judgement about how much email Ido had
# already had. It exited 0. Nothing downstream noticed, because exit 0 is the
# success path and the only other evidence was a log nobody reads.
#
# So success is now measured by a receipt written by send_report.ps1, not by
# the exit code. 'check' is exempt: it is designed to stay silent.
if ($code -eq 0 -and $Type -ne 'check') {
    $sent = $false
    if (Test-Path $receipt) {
        foreach ($line in (Get-Content -LiteralPath $receipt -Encoding UTF8 -ErrorAction SilentlyContinue)) {
            $stamp = ($line -split "`t")[0]
            $when = [datetime]::MinValue
            if ([datetime]::TryParse($stamp, [ref]$when) -and $when -ge $startedAt.AddSeconds(-5)) {
                $sent = $true
            }
        }
    }
    if (-not $sent) {
        Log "RUN FAILED: the $Type run finished but sent no email."
        Log "  Nothing was appended to logs/sent.log during this run. The report"
        Log "  may have been written and then withheld. Treating this as a"
        Log "  failure so the dispatcher retries it while there is still time."
        Log "=== $Type run finished (exit 1 - no email) ==="
        exit 1
    }
}

Log "=== $Type run finished (exit $code) ==="
exit $code
