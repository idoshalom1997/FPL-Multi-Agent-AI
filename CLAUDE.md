# FPL Manager - shared context for every agent

A season-long decision system for Ido's Fantasy Premier League team. Every agent
in this project reads the game through `fpl.py` so they all argue from the same
snapshot rather than each fetching their own and disagreeing.

## The manager

Ido Shalom - team "GIS97", entry ID **<ENTRY_ID>**.

**The goal is to finish first in a four-manager mini-league
(league ID <LEAGUE_ID>).** This is not the same as maximising
points and occasionally the opposite: what matters is the gap to three specific
rivals, not overall rank.

The rivals are Rookie mistakes, Nott'm Random Forest and Wei & Dudley, and all three owned and
captained Haaland through the opening gameweeks.

**Never write the standings into this file, an agent brief, or any other
document.** Read them:

```
python fpl.py league
```

A pasted table is correct for about six days and then silently poisons every gap
calculation built on it. One was left here after GW3 and agents were still
quoting a 55-point deficit in GW4, by which point it was 53 and every rival had
moved. The live command is one line and always right.

## The standard - we are behind and the staff must raise their game

On 23 Oct 2026, fourth of four and losing ground every week, Ido said it
plainly: *"we are really slacking! we have to get better - search well, get
info well - make better decisions with our resources ... all the staff really
need to wake up!"* That is the working standard for every agent, every run:

- **Feel the pressure.** Read the live gap (`python fpl.py league`) before you
  start and keep it in front of you. A cautious "hold" while three rivals pull
  away is not neutral - it is choosing to lose slowly. Every recommendation is
  judged on whether it closes the gap.
- **Search well.** Do not stop at the first source. Press conferences, team
  news, predicted lineups, set-piece takers, rotation risk, price changes, the
  market for this deadline, elite moves - go and get them, and check the claim
  that would change the decision against a second source.
- **Use the resources.** Free transfers, bank, chips: an idle resource needs a
  named reason. See the Resource Manager section.
- **Missing information is said out loud, and then fetched.** Every specialist
  ends with one line: `MISSING INFO: <what you needed and did not have>` (or
  `MISSING INFO: none`). The Assistant Manager fetches what can be fetched in
  the same run - a search, a new `fpl.py` query - and passes it back. Anything
  that needs a new tool or something only Ido knows (his free-transfer count,
  his team sheet) goes in one line at the bottom of the mail, so it is
  provided before next week. Guessing silently is not allowed.

## Two lineups, every main report (three in a chip week)

Since 23 Oct 2026 the main report offers **two** options, plus a CHIP lineup in a chip week (below) (the old SAFE /
DIFFERENTIAL / BALANCED trio is retired):

1. **BALANCED** - the staff's best team overall: the most expected points over
   this gameweek and the run ahead, on fixtures, team strength, minutes and
   price.
2. **DIFFERENTIAL** - the staff's best team *for this mini-league*: built to
   cut the gap to the three rivals - who to cover, where to diverge from what
   they own and captain, which chip they cannot answer. **The gap committee
   (Data Scientist, Opposition Analyst, Historian) has the final say on it**,
   and it follows `season_plan.md` - it may take a hit, play a chip or give up
   a fixture when the plan says that is how the gap closes.

If the two come out identical, say so and why - do not invent a difference.

**In a chip week there is a third: CHIP** (Ido, 29 Oct 2026). When the staff
recommend a chip, or Ido has said he plans one, the report adds a lineup built
for that chip, titled with it (FREE HIT, BENCH BOOST, TRIPLE CAPTAIN, WILDCARD).
BALANCED and DIFFERENTIAL show the week without the chip, so he can compare
playing it against keeping it. It must be legal for the chip - a Free Hit
fifteen fits his total budget (selling value + bank) with max 3 per club, and
the Rules Enforcer checks it - and it carries two short lines: why this chip
this week, and what it is worth against not playing it (`chipcalc.py`). It is
recorded as option `"CHIP"` with its `chip` field set, and `outcome.py` scores
it with the chip applied (Triple Captain x3, Bench Boost adds the bench). Ido's
first case: a GW9 Free Hit, because many good teams play each other that week
and his squad is full of their players.

## The season plan and the gap committee: `season_plan.md`, `gap.py`

Set up on 23 Oct 2026. Ido's instruction: the Data Scientist, the Opposition
Analyst (the "differential" owner) and the Historian *"need to have a game plan
of reducing the gaps ... the end goal is really a long season plan that updates
every time to how to win this mini league."* These three are the **gap
committee**.

- **They own `season_plan.md`**: the strategy to first place by GW38, target
  gaps at checkpoints, the resource map (both chip sets, planned hits, banked
  transfers) and a progress log. Updated **every** planning, main and review
  run - it is a living plan, not a document written once.
- **They have the final say on the DIFFERENTIAL lineup.** They consult every
  other specialist and have access to everything, but the Assistant Manager
  does not override their DIFFERENTIAL; he presents it. It is the season plan
  applied to this gameweek.
- **Anything is allowed if it closes the gap on a long-term reason**: chips,
  several transfers, hits (each `-4` counted against what it wins back over the
  plan's horizon), sacrificing a fixture or a gameweek for a bigger swing later.
  Ido: *"we will not succeed every time and it's okay to sacrifice a fixture if
  it's for a bigger plan."* What is not allowed is a move with no place in the
  plan.
- **They track progress all the time.** `python gap.py` prints the gap to each
  rival per gameweek, its trend over 1/3/5 weeks, the points per gameweek
  needed to draw level by GW38, and - from `recommendations/gw*.json` - what Ido
  chose against BALANCED and DIFFERENTIAL each week. Every review says whether
  we are closer to or further from the goal than the plan's last checkpoint,
  and the plan learns from what Ido chose versus what the staff suggested.
- **Are we playing the game right?** `python season_review.py` measures Ido and
  the three rivals on the same five things, season to date: transfers (each
  scored as bought minus sold over three gameweeks), hits, captaincy (points,
  and what the best captain in his own XI would have added), chips (what each
  one actually added), and bench points. Ido asked for the plan to start from
  this - *"see where we went wrong ... how we transfer and how they transfer,
  how do we use chips compared to them"* - so the committee reads it every
  review and says plainly where Ido is playing the game worse than his friends,
  and what the plan does about it.

## Standing rules

- **Ido is the manager. Every final decision is his.** Agents recommend and
  argue; they never decide. Present options with their costs, then stop.
- **Haaland goes in - then he is an ordinary player.** On 23 Oct 2026 (before
  GW8) Ido retired the old "never sign Haaland" ban: *"halaned has to go in but
  after is in treat him regularly like every other player. if he will perform
  bad we remove him in the future."* So there are two phases:
  - **Getting him in is decided, not debated.** Until he is in the fifteen,
    every lineup option the staff offer includes him. The staff's job is *how*:
    which players are sold to fund £15.7m-ish (selling prices after the 50% fee,
    bank included), how many free transfers it uses, any `-4` written plainly,
    and the best squad left around him on fixtures.
  - **Once he is in, no special status either way.** He is judged on fixtures,
    minutes, xGI and the captaincy like anyone else, and he can be benched,
    left without the armband or sold when the evidence says so. Neither
    "never sell him" nor "always captain him" is a rule.

  The old ban is the reason the staff spent seven weeks unable to answer the
  rivals' captain - all three own him - and why every elite-ownership table had
  him cut out of it. Do not reintroduce either habit.
- **Advise only. Ido is the only one who changes anything.** This is his
  hardest rule and it does not bend: *"never an agent can do changes itself even
  if he see that I have gone crazy and did a triple captain on the worst player
  even - they can only advise not change!"* The extreme case is the point. Even
  a change the staff are certain is right, and that he would obviously want, is
  his to make. Recommend, then stop.

- **There is no FPL login, and one cannot be made to work.** Ido originally
  declined to store one, then deliberately reversed and asked for live access to
  his account, keeping the no-changes rule absolute. It was built - and it could
  not sign in. **The Premier League has retired email-and-password login
  entirely**: `users.premierleague.com` no longer resolves to anything, and
  sign-in now runs through `account.premierleague.com` as a browser flow behind
  bot protection. This is not a wrong password, a missing header or a solvable
  bug. Do not build it again, and do not ask him for his password.

  The consequence is a permanent blind spot: `my-team/{id}` returns 403, so his
  **starting XI, bench order and captain cannot be read by anything** before a
  deadline. His transfers become public only **after** the deadline too
  (verified 23 Oct 2026 across all four managers in the league), so before a
  deadline nothing public shows his new fifteen either. His chat-session or
  emailed team sheet is the only pre-deadline source for both.

- **Every recommendation states its cost.** A transfer that takes a hit is
  written as `-4` explicitly, never buried.
- **Uncertainty is reported, not smoothed.** If a player's minutes are in doubt
  or the underlying stats disagree with the points, say so.
- **The team ID is public.** It appears in the FPL URL and grants read-only
  access to picks after each deadline. It is not a credential.

## Lineup images: `lineup.py`

Every lineup option is delivered as a picture in the style of the FPL squad
graphics: club-coloured shirts carrying the **real club badge**, a points chip
on each player, `CLUB | POS | £price` under the name, a bank-and-formation panel,
and a substitutes strip labelled S1-S4. Ido asked specifically for this rather
than a generic diagram, because he reads his team visually and wants the two to
look alike.

The 20 crests live in `badges/` and were fetched from
`resources.premierleague.com/premierleague/badges/70/t{code}.png`, where `code`
is the team's `code` field in bootstrap. **Download them with curl, not Python** -
that host takes minutes per file through `requests` from this machine and
seconds through curl. `python lineup.py badges` re-fetches any that are missing.

Round markers are drawn as aspect-corrected ellipses, because the substitutes
panel is far wider than it is tall and true circles come out as ovals there.

### Design decisions Ido has already made - do not reverse them

- **Goalkeeper at the top, forwards at the bottom.** He asked for this
  explicitly after seeing it the other way round.
- **No per-player points chip on a selection picture.** It was tried on the
  Friday lineup options and he found it confusing. This is a rule about the
  *Pick Team* view only - see the Points view below, where he asked for the
  opposite.
- **Every crest sits on a small pale disc.** Without it, badges close in colour
  to their own kit disappear - the Liverpool crest on a red Liverpool shirt was
  the case that prompted it. Keep the disc small: it is a backing plate for the
  crest, not a bib, and the kit colour must still read at a glance.

### The Points view: `render(..., score=...)`

After a gameweek the same renderer draws the FPL **Points** screen instead of the
Pick Team screen. Pass `score` and give each player a `gw_points` key:

```python
lineup.render(xi, bench, title="YOUR TEAM", subtitle="GW3 · Cherki (C) · -8 hit",
              score=36, score_label="YOUR POINTS", filename="gw3_actual.png")
```

Each card then shows what that player scored in place of his price, the header
panel shows the total instead of the bank, and the substitutes strip reports how
many points were left sitting there. **The captain's card carries his doubled
score**, as FPL's own Points screen does - the caller passes it already doubled.

Ido asked for this explicitly, and for the review to be built out of these
pictures rather than a table of numbers: one for the team he actually played,
one for each option the staff had recommended, so the comparison is visual. See
`reports/review_example.html` for the approved layout.

## The schedule - measured from the deadline, never from the weekday

`schedule.ps1 -Install` registers **one** Windows task:

```
FPL - Scheduler        every 3 hours
```

It runs `dispatch.ps1`, which asks `due.py` what is due and runs it via
`run_report.ps1 -Type <planning|main|check|review>`. Claude is launched headlessly
(`claude -p`), so no window need ever be open.

**Nothing is scheduled by weekday, and nothing may be.** The first version was -
planning Wednesday, main report Friday, review Tuesday - and it is simply wrong
for seven of this season's thirty-eight gameweeks. Five have midweek deadlines
(GW13, 18, 20, 25, 28) and two are Sundays. For GW18 the deadline is Tuesday
29 December at 18:00: the Friday report would have arrived three days after Ido
could act on it, and the Tuesday review would have run two hours before the
gameweek it was reviewing had started. A fixed timetable does not fail loudly
when the calendar moves; it just quietly stops matching it.

Each report has a window, in hours before the deadline, and fires on the first
three-hourly pass inside it:

```
review     as soon as the gameweek is scored - runs before anything else
planning   96 - 42     the landscape, but NEVER before the previous gameweek
                       has been reviewed
"send your team"  48h  the check run asks for his screenshot - one email per
                       gameweek, a full day before the report that needs it
main       26 - 1      the decision - lands about 24h before, after press
                       conferences, with a day still left to act. The window
                       stays open to the deadline ONLY as a rescue: a report
                       fires on the first pass inside its window, so a healthy
                       week is unaffected, but a run that failed can still get
                       out late instead of being dropped
check      every pass  self-silencing otherwise; speaks when a deadline is
                       inside eight hours or health.py has found something
```

**Two ordering rules, both learned the hard way when Ido read the timetable and
spotted what it implied.**

*The planning brief must not overtake the review.* It is the Historian's lesson
applied forward, so planning GW5 before anyone has looked at GW4 is planning
from nothing. The test is the gameweek immediately before the one being planned
- `review` recorded for `gw - 1` - and not "the last scored gameweek", because
those differ exactly when it matters: GW5's brief fell due while GW4 was still
being played, and GW3 was scored and reviewed, so a rule written the other way
waved it straight through. A consequence worth knowing: on a fast turnaround
into a midweek deadline the planning window can close before the review lands,
and the brief is simply skipped. That is correct - there is no time for one, and
the main report still runs.

*His reply is read twice, not once.* The team sheet on file is only ever as
current as the last thing he said, and the main report exists precisely to make
him change his mind. So the pre-deadline check re-reads his most recent reply
before the doctor looks at anything: otherwise it spends its run confirming the
fitness of an XI he stopped fielding the moment he acted on the report. He
spotted this himself - "how will the doctor know who's in my 11?" - and he was
right. A reply naming an option rather than players is resolvable too: every
option is recorded in full in `recommendations/gw<n>.json`, so "went option 1"
is a lookup, not a guess. His transfers, like his XI, are hidden until the deadline; a reply (or a
Pick Team screen read in a chat session) is the only pre-deadline source for
all of it.

*The request for his team sheet must beat the main report, not the deadline.*
The main report is built ~24h out and is the thing that needs his XI and
captain. An ask pinned near the deadline arrived after the report had already
guessed. It goes out at 48 hours, one email per gameweek - the finding carries a
key so a 48-hour window and a three-hourly trigger cannot send sixteen identical
requests.

The upper bound decides when the mail actually arrives, which is why `main`
opens at 26 hours and not 36: 36 put it at three in the morning before a
Saturday deadline. Simulated across all 38 gameweeks, every one now fires
between 24 and 26 hours out, at a civilised hour, midweek gameweeks included.

The review waits for `data_checked`, not `finished`. FPL sets `finished` when
the last match ends but keeps adjusting bonus afterwards, so scoring on
`finished` compares the staff's advice against numbers that are still moving.

`data/runs_done.json` records which report has run for which gameweek, so a wide
window cannot send the same mail twice. **A failed run is deliberately not
recorded**, so the next pass retries it while the window is still open - a report
that marks itself done and then fails is a report that never arrives and never
retries, which is how one went missing for an entire weekend.

**And "failed" now includes "finished but sent nothing."** On the GW5 deadline
the main run produced every image, recorded its options, and then stopped to ask
whether it should send, having decided on its own that Ido had had enough email
- and exited 0. Nothing downstream noticed, because exit 0 is the success path.
`run_report.ps1` therefore measures success by the receipt in `logs/sent.log`,
not by the exit code: a planning, main or review run that sent no mail is logged
as `RUN FAILED` and exits 1, so the dispatcher retries it while time remains.

The task runs only while Ido is logged on, because Claude needs a real desktop
session, and uses `--permission-mode bypassPermissions` since nobody is present
to answer a prompt. The agents only read public FPL data, search the web and
send mail, so that is a bounded risk - but keep it bounded: do not give the
scheduled path tools that can spend money or alter his FPL account.

A freshly launched `claude -p` process picks up `.claude/agents/` on startup, so
scheduled runs see the whole staff without anyone restarting an interactive
session. Only an already-running session misses agents added mid-session.

### `Tee-Object -LiteralPath -Append` does not exist

Every scheduled run died the instant it launched Claude, with `Parameter set
cannot be resolved using the specified named parameters`, and went undiagnosed
for a weekend because the task simply reported failure. `Tee-Object` only offers
`-Append` in its `-FilePath` parameter set; pairing it with `-LiteralPath` is a
parse-time impossibility that nothing catches until the line actually runs. It
is `-FilePath` now. Test a change to `run_report.ps1` with `-WhatIf` before
trusting the schedule to it.

## Email

Reports go out through `send_report.ps1`, which reuses the Gmail App Password
stored as an encrypted credential file and embeds lineup images **inline** so
they display in the message body.

Every subject is auto-prefixed `[FPL]` so reports are easy to find and filter.
After sending, add the **FPL** label  to the thread.

### Keep it short - this is a hard rule

The first full report went out as long-form HTML: a paragraph from each of seven
agents, a disagreements section, three options with best-and-worst-case prose,
and a forward calendar. Ido's verdict was that he could not read it, and he was
explicit that it applies to **every** email the system sends, not just that one.

On 29 Oct 2026 he cut it further ("too much!") - he reads as the head manager,
and the agents' lines are not informative to him. The main report is now only:

1. **The deadline** in a framed box at the top, with the time left.
2. **The call** in one or two plain sentences, no story: "The staff recommend
   BALANCED and expect about 62 points."
3. **Each lineup** (BALANCED, DIFFERENTIAL, CHIP in a chip week): one or two
   sentences on why the staff think it is a good idea (transfer and `-4` cost
   included), the picture, and two small boxes under it - **best case** and
   **worst case**, each as points and the gap move against the rivals.
4. **One line** asking him to reply with what he played; a "Need from you" line
   only when something is genuinely missing.

**No per-agent lines.** The agents may reason at whatever length they need; it
is saved in `recommendations/gw<n>.json` and the project files, not the mail.
Each option's `predicted_points`, `best_case` and `worst_case` are recorded as
numbers, and the review checks them against what happened - so we learn whether
the staff's forecasts are right. The same short-mail rule applies to every email
the system sends; the review and planning formats are below.

### The review mail: five parts and nothing else (29 Oct 2026)

Ido found the review too long to read. It is now exactly:

1. **Verdict** - at most four lines, numbers only: points, the week's score out
   of 10 (`score10` in `benchmark.py` - the share of all managers he beat), vs
   the top 100 and the world, world rank; the staff's options v what he played
   v doing nothing; each league gap and its move; the week's two goals, met or
   missed.
2. **The lineup pictures** - what he played and each recommended option (he
   likes these; keep them).
3. **The mini-league table** - just the table, no words after it.
4. **Transfers and chips** - the Rules Enforcer's table from
   `python league_status.py --html`: transfers and chip this gameweek, free
   transfers for the next, chips left, for all four managers.
5. **Three lessons** - three one-line bullets on what the staff take forward.

The Historian's verdicts, the ledger and the season plan still get written -
into their files, not the mail.

### The planning mail: four parts and nothing else (29 Oct 2026)

Ido found the planning brief "way too much info for no good use". It is now:

1. **Chips clock** - a small table: each chip left, the gameweek it makes most
   sense as things stand, a few words why.
2. **Season plan** - at most three lines: the gap to each friend and the points
   per gameweek needed by GW38, the plan in one line, on track or not.
3. **Expected rivals** - one labelled block per friend, one or two lines each
   ("Wei & Dudley's plan - captain X, likely Free Hit, buying Y"), then one line on
   what it means for our DIFFERENTIAL. The Opposition Analyst writes it into
   `season_plan.md`, the main report's DIFFERENTIAL is built against it, and the
   review notes how much came true.
4. **Final thoughts** - the deadline in a framed box, then **two goals** for the
   gameweek: actionable and checkable with a number or yes/no (pass a friend,
   beat the top 100 average, use the transfer or chip well, test a player).
   They go in `season_plan.md` under "## 6. Weekly goals"; the review fills in
   met or missed and shows it in its verdict. That is how we learn whether the
   staff actually reach what they aim for.

### No live in-match alerts - he had them removed

Per-event live alerts were built and deleted the same day. Ido asked for an email
the moment a player scored or assisted, was offered a periodic digest instead,
and chose one-email-per-event knowing it meant fifteen to twenty-five messages on
a match weekend. Seeing that laid out, his verdict was *"I thought about it and
it's too much - I don't want the updated email per event at all, please delete
it."*

So the rule is about **how many** emails reach him, not only how long each one
is. Do not propose a new notification channel. Something worth telling him is
worth a line in one of the four scheduled reports, not a message of its own.

**Leave the message in the Inbox.** Do not remove the `INBOX` label to make the
label behave like a folder: Gmail only raises a notification for mail that
reaches the Inbox, and Ido depends on that notification to know a report has
arrived. This was tried once and he lost the alerts. The label is an
organisational overlay, not a replacement for the Inbox.

```python
import fpl, lineup
xi, bench, meta = lineup.live_team(fpl)       # the real current side
lineup.render(xi, bench, title="BALANCED", subtitle="...", filename="gw8_balanced.png")
```

### The stale-picks trap - read this before rendering anything

**The FPL API only publishes a manager's picks AFTER that gameweek's deadline.**
Before the deadline, `fpl.picks(team_id, gw)` and `fpl.squad()` still return the
*previous* gameweek's team, including its captain. Rendering that and labelling
it as the upcoming gameweek is wrong and has already caused one bad report: it
showed Cherki as captain when Ido had moved the armband to João Pedro.

`current_team.json` is the override. When its `event` matches the upcoming
gameweek it is the source of truth for the live XI, bench, captain and vice;
otherwise it is ignored and the API is authoritative. `lineup.live_team()`
handles this automatically - use it rather than reading picks directly. Keep the
file updated from the Pick Team screen whenever Ido changes his side.

## The learning loop: `outcome.py` and `recommendations/`

A recommendation nobody checks afterwards teaches the staff nothing. Ido asked
for the opposite: every week the system must know **what it advised, what he
actually did, and which of the two was right** - so the advice improves instead
of repeating itself.

That runs on two halves.

**Before the deadline**, the main report writes its own advice to
`recommendations/gw<n>.json` - all the lineup options with their full XI, bench
order, captain, transfer and cost, plus each agent's line, the disagreements and
how they were resolved, and `status_quo`, the team he fields if he does nothing.
This is not optional and not a summary: the options must be recorded exactly as
they were offered, because next week's comparison is only honest if it compares
against what was really on the table.

```python
import outcome
outcome.record(4, payload)          # called by the main report run
```

**After the gameweek**, the review run scores it:

```
python outcome.py 4                 # score GW4 and write the result back
python outcome.py 4 --dry           # print it, write nothing
```

It reads the real picks back from the API and reports what he fielded, what he
scored, how many points sat on his bench, what each recommended option would
have scored, whether he followed one exactly or diverged, and by how much. The
result is written back into the same file under `actual`, so the record of every
week is one file containing both the advice and its consequence.

Two things it deliberately will not do:

- **It refuses to run before the deadline has passed.** Before a deadline the
  API still serves the *previous* gameweek's picks, so scoring early would
  silently compare the advice against the wrong team.
- **It does not model auto-substitutions.** An option whose player blanked can
  therefore flatter the real team slightly. The tool says so in its own output;
  do not quietly drop that caveat when quoting the numbers.

The Historian owns this file. He reads every prior `recommendations/gw*.json`
before advising, which is what lets him answer his standing question - *has Ido
made this mistake before?* - with evidence rather than memory. The verdict he
writes into `decisions.md` must judge the decision **on what was knowable before
the deadline**, not on how it happened to turn out: an option that was right and
unlucky stays right.

Ido's own reply to the report is part of this. The mail asks him for one line -
"went option 1", "kept Cherki" - and that line is the ground truth for anything
the API cannot show, such as *why* he diverged.

### Outside yardsticks: `benchmark.py`

Beating "do nothing" only shows that changes beat no changes. On 29 Oct 2026 Ido
asked to "step up our checking game", so every review also runs
`python benchmark.py`, which measures each scored gameweek against outside
yardsticks: his points (net of hits) against the **top 100 average** - the main
yardstick since 29 Oct 2026, because those are real teams picked before the
deadline (from `elite.py behaviour`) - against the **world average**, his share
of FPL's **Team of the Week** (`dream-team/{gw}`: the best legal XI in
hindsight, no captain or bench, so kept only as the ceiling), his **world rank** for the week
and overall, and each **league gap** - each split into before the staff (GW1-3)
and since (GW4 on). Its summary lines go into the review mail as the "How are
we doing" block. If the numbers get worse, the Historian says so and names what
changes.

## The team sheet: `team_update.py`

The one thing no amount of code can find out is which eleven Ido is starting and
who has the armband. He has to say. `team_update.py` is the safe way to write
that down:

```
python team_update.py --xi "<11 names>" --bench "<4 in bench order>"                       --captain "<name>" --vice "<name>"
python team_update.py --check ...        validate and print, write nothing
```

Names can be as sloppy as a person actually types - "Joao Pedro", "Bruno",
"calvert-lewin" all resolve, because they are matched only against his own
fifteen, which is a small enough set for that to be safe rather than a guess.
Anything genuinely ambiguous is an error.

**It refuses rather than guesses.** Before writing anything it checks the team
is legal - exactly 1 goalkeeper, at least 3 defenders and 1 forward, 11 and 4,
no more than 3 from a club, captain and vice actually in the XI, nobody named
twice. A misread screenshot fails loudly instead of quietly putting the wrong
captain in a report, which is the precise failure this area of the project
exists to prevent.

**How it reaches him.** The check run emails him when the team sheet is unknown
- which happens as the deadline approaches, whatever day that falls on - and
asks him to reply with a screenshot of his Pick Team screen. The main run, about
a day before the deadline, searches Gmail for that reply, reads it (words or
image) and records it before the staff build anything. If no reply arrives, the
report says plainly which gameweek the team it drew is from, so a stale captain
is visible rather than silent.

Writing this file is not "changing his team". It records what he told us. The
standing rule is untouched: nothing here ever acts on his FPL account.

## The safety net: `health.py`

Two silent failures have already cost Ido something. A stale `current_team.json`
made a report draw the wrong captain, and a crashed scheduled run meant no email
arrived for a whole weekend while the only record sat in a log nobody reads.
`health.py` makes both loud.

```
python health.py           full report, exit 2 if something needs him
python health.py --quiet   nothing at all unless something needs him
python health.py --all     ignore the already-reported list, show everything
```

It checks two things. **Is `current_team.json` current** - does its `event` match
the upcoming gameweek, and do its fifteen names match the fifteen players he
actually owns? Transfers are NOT published before a deadline either (checked 23 Oct 2026,
all four league entries), so before a deadline the API shows last week's fifteen
and a team file he gave us after making his transfers will legitimately differ
from it. health.py reports that as a note, not an alarm. **Did the main
report actually reach his inbox** - not "did a run happen", which is the
question that failed him. `send_report.ps1` appends a receipt to `logs/sent.log`
every time an email genuinely leaves the machine, and `check_report_delivered()`
looks for one matching the upcoming gameweek once the deadline is inside 26
hours. Separately, the newest log of each report type is inspected for a run
that started and broke.

The daily `check` task runs it. That task now has two reasons to speak: the
deadline being close, or health.py finding something. The second is deliberately
not gated on the deadline window, because a failed report needs saying the next
morning, not a week later. **No new notification channel was created** - the
findings ride along in the deadline-alert email that already existed.

Three rules hold it to Ido's standards:

- **It reports and never repairs.** It does not edit `current_team.json` and
  does not touch his FPL team - it could not, since everything it reads is a
  public endpoint. The staff advise, he executes. A checker that quietly
  corrected the file would be exactly what he has ruled out, and the check
  prompt in `run_report.ps1` says so explicitly.
- **A past failure is news once.** Reported findings are remembered in
  `data/health_reported.json` and not raised again. Re-raising a failed run
  every morning would turn one piece of news into a week of identical mail.
- **A stale team file is only urgent near the deadline.** Outside thirty hours
  it is a note, not an alarm - otherwise he gets six emails about one thing.

**What it cannot see, and must never pretend to:** FPL publishes picks only
after a deadline, so his starting XI, bench order and captain are invisible to
any public caller beforehand. A clean result means *the fifteen players are
right*, never *the team sheet is right*. Every view prints that caveat, and the
alert mail asks him to confirm rather than assuming.

## Resources: the Resource Manager

Free transfers, the bank, price changes and the chips are the only tools that
can close a gap, and until 23 Oct 2026 nobody owned them together: the free
transfers piled up to an unconfirmed four while three chips sat unused and all
three rivals had already spent their Triple Captain. Ido: *"we need to use now
our resources well - i dont think we read the market well and my friends are
killing it."*

The **Resource Manager** (`.claude/agents/resource-manager.md`) owns that
ledger every run: free transfers held and how they will be spent over the next
three gameweeks, the bank and the real selling prices, players about to rise or
fall in price, and chip timing jointly with the Rules Enforcer (legality and
calendar) and the Opposition Analyst (whether it gains ground). **Banking a
transfer needs a named purpose; holding five, or letting a chip expire, is a
finding to raise unprompted.**

## The chip plan: `chips.md`

Four chips, fifteen gameweeks, one chip per gameweek, and everything unused at
the GW19 deadline is lost. That is a planning problem, not a weekly one, and it
was nobody's job until Ido asked who was responsible for it.

`chips.md` is the answer. The **Rules Enforcer owns the file** - which chip is
aimed at which gameweek and the one reason for each - because they own the
calendar and the legality. The **Opposition Analyst owns whether it gains
ground**, which is the question that settles it: a Triple Captain played the
same week a rival plays theirs achieves nothing at all in a four-manager league.
They are meant to disagree in writing.

**`chipcalc.py` is how the argument starts.** Ido's question was the right one -
*how would they know when it is profitable?* - so chips are measured, not felt.
Each is valued as what it adds beyond the status quo: a Bench Boost is worth
what the four substitutes are expected to score, a Triple Captain adds **one**
extra copy of the captain rather than three, a Free Hit is floored at what the
blanking players cost. `python chipcalc.py 15` prints every week to the deadline, and
`python chipcalc.py targets 6` ranks captain targets across the **whole league**
rather than only his fifteen - the half that was missing, since a Triple Captain
is a question about every player in the game, not just the ones he owns.
The numbers are orders of magnitude and say so in their own output - the
upcoming week uses FPL's `ep_next`, later weeks scale points-per-game by
fixtures and know nothing about rotation.

It is reviewed in every planning brief. When a planned chip is not played in its
planned week, the reason goes in the file, so next week's staff can tell whether
the plan changed or merely slipped.

## Elite ownership: `elite.py`

What the world's top 100 managers actually own, measured rather than guessed.
Ido asked for this specifically, and specifically for the list to be rebuilt
every time: **the top 100 is a different hundred people every week**, so a roster
captured once would be describing the wrong managers within a month. The
standings are re-read from the live API on every refresh and never cached to a
stored list.

```
python elite.py refresh     rebuild the list and recount (about a minute)
python elite.py             elite ownership beside world ownership, and the gap
python elite.py captains    who the top 100 captained, and chips played
python elite.py moves       what they bought and sold since last gameweek
python elite.py compare     Ido's fifteen against elite ownership
```

Each refresh writes `data/elite_gw<n>.json`. The Media Analyst runs it first on
every report and quotes it instead of estimating elite ownership off blogs.

Three details that matter:

- **It is always last week's teams.** Picks are public only after a deadline, so
  before one this shows what the elite owned in the previous gameweek - the same
  stale-picks trap described above, and the reason every view prints the caveat
  in its own header. Quote it as "as of GW<n>".
- **`moves` compares the same hundred managers across both weeks.** A snapshot
  therefore stores the cohort's previous gameweek as well as the current one,
  which is why a refresh makes two hundred requests rather than one hundred.
  Comparing this week's top 100 against last week's *different* top 100 would
  blend real transfers with churn in the list and read as movement that nobody
  actually made.
- **It bypasses `fpl.get`'s disk cache on purpose.** Routing a hundred squads a
  week through it would leave some four thousand `entry_*_picks.json` files in
  `data/` across a season. The aggregate snapshot is what is worth keeping.

The first snapshot, GW4, immediately confirmed the bench problem in
`decisions.md` with hard numbers: six of Ido's fifteen are owned by 5% or less of
the top 100, while 84% of them hold Calafiori and 74% hold Palmer.

### How the elite play over time: `elite.py behaviour`

Ownership is what they hold; Ido also asked (29 Oct 2026) for **how they play**,
accumulated over the season, "to see what makes them top 100" and improve every
decision. Each `refresh` also reads all 100 season histories (one request each)
and stores the result under its gameweek in `data/elite_behaviour.json`, so the
file grows week by week. `python elite.py behaviour` prints, per gameweek, elite
average against Ido: points, transfers, % taking a hit, bench points, captain
points, median world rank and chips played; then season totals and their past
seasons. The Media Analyst gives one behaviour finding every run; the gap
committee reads it in planning and review and builds the lesson into
`season_plan.md`. Caveat to keep: it is the *current* top 100 looked at
backwards, so part of what got them there is luck - the past-seasons line says
how much. First reading (GW8): they took a hit in about 1% of weeks (Ido 2 of 8),
made 4 transfers to his 10, left 67 points on the bench to his 97, averaged 7.9
captain points a week to his 4.2, and played chips early and together (Bench
Boost GW1, Free Hit GW3, Wildcard GW4, Triple Captain GW7) - yet only 11% of them
have ever finished a season in the top 10k.

## Data layer: `fpl.py`

All data comes from the public FPL API, cached under `data/` so a burst of agent
activity does not hammer the endpoint or produce inconsistent reads mid-run.

```python
import fpl

fpl.refresh()                  # force re-download before a deadline decision
fpl.current_event()            # gameweek in progress
fpl.next_event()               # upcoming gameweek
fpl.deadline()                 # (event, hours_remaining)

fpl.players()                  # {id: player} - 655 players, 109 fields each
fpl.teams()                    # {id: team}
fpl.find_players("haaland")    # fuzzy name lookup
fpl.player_summary(411)        # per-match history + upcoming fixtures
fpl.fixtures(gw)               # fixtures for one gameweek
fpl.live(gw)                   # live points during a gameweek
fpl.ticker(horizon=6)          # fixture difficulty per team, sorted by run
fpl.strength()                 # real attack/defence per team, goals + xG, ranked
fpl.matchups(<ENTRY_ID>)           # each of the fifteen against the opponent's strength
fpl.league(<LEAGUE_ID>)              # live mini-league standings - never write these down
fpl.market()                   # live transfers, for the NEXT deadline (forward-looking)

fpl.squad(team_id)             # starting XI, bench, captain, bank, chips
fpl.entry_history(team_id)     # per-GW history + chips already played
fpl.entry_transfers(team_id)   # every transfer made this season
```

CLI equivalents for quick checks:

```
python fpl.py status
python fpl.py refresh
python fpl.py ticker 6
python fpl.py squad <team_id>
python fpl.py strength
python fpl.py matchups
python fpl.py player <name>
```

### Fields worth knowing

Player records carry far more than points. The ones that usually decide an
argument: `expected_goals`, `expected_assists`, `expected_goal_involvements`,
`expected_goals_conceded` and their `_per_90` variants, `form`,
`selected_by_percent`, `now_cost`, `cost_change_event`, `status` (`a` available,
`d` doubtful, `i` injured, `s` suspended, `u` unavailable), `news`,
`chance_of_playing_next_round`, `defensive_contribution`, and
`corners_and_indirect_freekicks_order` / `direct_freekicks_order` for set pieces.

Prefer per-90 and expected metrics over raw totals when comparing players with
different minutes. Raw `total_points` rewards players who simply played more.

### Fixture difficulty

`ticker()` reports FDR 1–5 per fixture, home and away, and flags doubles and
blanks rather than averaging them away. Note that FDR is the FPL site's own
rating and is coarse — it is a starting point for a conversation, not a verdict.

**MANDATORY, AND IDO CHECKS THIS.** Fixture difficulty is not optional context.
Every player named in a lineup or a transfer recommendation must be justified
against the opponent he actually faces, and that opponent must be stated out
loud in the report. Both horizons count:

- **This gameweek** — name the opponent, home or away, and its FDR, for every
  player being started, benched, bought or sold.
- **The run ahead** — a transfer is a multi-week commitment, so argue it on the
  next several gameweeks from `ticker()`, not on Saturday alone. A player on the
  worst run in the league is a bad buy however good his form is.

**Transfer suggestions specifically must be fixture-driven.** A transfer argued
only from form, price or ownership is not acceptable and will be rejected.

**Never quote `ep_next` as though it forecast the next match.** It is opponent
-blind, and in practice FPL often sets it equal to `form` for every unflagged
player, so "highest expected points in the squad" collapses to "best recent
form" while sounding like a projection. If a number ignores the opponent, either
say so in the same sentence or do not use it.

This rule exists because the GW5 main report recommended starting De Cuyper on
"the highest expected points in the squad" while Brighton hosted Arsenal — one
of the two hardest fixtures of the week, with Brighton on the worst six-game run
of all twenty teams. None of that reached the mail. Ido caught it himself.

### Real team strength: `strength()` and `matchups()` - read these, not just FDR

FDR is FPL's own label and too coarse to pick a defence on. In GW7 Tarkowski
started at home to Chelsea - a top-three attack by goals - and blanked; Ido
raised it after the review. So the staff now read how good each opponent
actually is:

```
python fpl.py strength     every team: goals and xG for/against per game, home,
                           away, last 4, plus attack_rank and defence_rank (1 = best)
python fpl.py matchups     each of the fifteen against the opponent he faces this
                           gameweek and the four after - defenders and keepers
                           against the opponent's ATTACK, attackers against its DEFENCE
```

**The rule: a keeper or defender facing a top-five attack (`attack_rank` 1-5)
is benched by default.** Starting him needs a stated reason - no fit bench
alternative, or the alternative's fixture is as bad - written in the report.
`matchups` flags these players. The same reading applies the other way: an
attacker facing a top-five defence needs a reason to be captained.

The ranks are inputs, not a verdict: seven to ten matches is a small sample,
home and away differ (read the split columns), and the staff should say so when
a rank rests on one big score.

### Search the whole market, not just the fifteen

**A recommendation that only rearranges the current squad is an incomplete
answer.** Every main report must also look outside the fifteen. Ido asked for
this directly: "look at the whole transfer market for option of we dont have
the right squad for the fixture."

So each week, after the squad has been assessed fixture by fixture:

- Scan the full player list for the positions where our own players face the
  worst fixtures, filtered to what the bank and the sell-on fee actually allow.
- Be willing to conclude that **the squad itself is wrong for the fixtures**,
  and say which outside players fit better. That conclusion is allowed and
  wanted; do not soften it into a bench reshuffle.
- Name the affordable candidates explicitly, with their opponent, their run and
  their price, so Ido can compare rather than take it on trust.
- Where nothing outside beats what we have, say so in one line and show the
  comparison that settled it. "We looked and there is nothing better" is a
  useful answer; silence is not.

Cheap positions matter most here, because that is where a small amount of money
buys a large upgrade.

### Goalkeepers are part of the squad

Both keepers get the same scrutiny as everyone else, every week. The staff have
a habit of debating the outfield players and letting the goalkeeping slot ride
untouched from week to week, which is how a weak pair goes unchallenged for a
month. Each main report must say, in one line, whether the starting keeper is
still the right one — on form, on `expected_goals_conceded`, and on the fixture
run — and whether the bench keeper is worth his money. Keepers are cheap, so an
upgrade there is often the best value transfer on the board; say so when it is.

### Wildcard week

**When the staff recommend the Wildcard, the main report shows the full new
fifteen as a lineup picture**: XI, bench in order, captain and vice. A list of
"in" and "out" is not enough. Ido asked for this before GW6: "you need to
display me wildcard lineup if the staff decide to use it." Render the
do-nothing team beside it so the two can be compared.

The squad is built on everything at once. Ido reminded us that this was already
agreed, so treat it as settled:

- **Squad value and budget.** Selling prices come after the 50% sell-on fee, so
  state the real money available and the bank left over. Avoid players who are
  about to fall in price, and say who is likely to rise.
- **Injuries and availability.** The Doctor clears every player. Nobody doubtful
  goes in without a stated reason and a fit replacement on the bench.
- **Easy fixtures ahead.** Use this gameweek and the run of the next 5 to 6
  gameweeks from `ticker()`. A Wildcard is a long commitment, so the run matters
  more than Saturday.
- **The bench.** It has to be strong enough for the Bench Boost gate in
  `chips.md` (about 18 or more), because that is why the Wildcard is played now.
- **The whole market,** as in the section above, plus **rival ownership**, so
  the squad includes uncommon players who can win the mini-league.

Each player in the picture gets one line in the report: opponent this week, his
run, his price, and his fitness.

## Game rules the agents must respect

- Squad of 15: 2 GKP, 5 DEF, 5 MID, 3 FWD. Starting XI must have 1 GKP,
  at least 3 DEF and at least 1 FWD.
- Maximum 3 players from any one Premier League club.
- £100m initial budget; squad value and bank move with price changes.
- One free transfer per gameweek, banking up to **five** in total
  (`game_settings.max_extra_free_transfers` = 4 on top of the current one).
  Extra transfers cost −4 points each.
- **Sell-on fee 50%** (`transfers_sell_on_fee`): a player who has risen sells for
  his buy price plus half the rise, rounded down. Funding a move from the full
  rise is the commonest way a recommendation turns out not to fit.
- Captain scores double. Vice-captain takes over only if the captain does not
  play at all — a captain who plays one minute keeps the armband.
- **Auto-substitutions** decide what the bench is worth, and the bench is Ido's
  largest leak. A starter on zero minutes is replaced by the first bench player
  who played, in order, but only where the resulting XI stays legal; the bench
  keeper can only replace the keeper. Bench *order* is a real decision, not
  decoration. The Rules Enforcer owns this.
- Chips: Wildcard, Free Hit, Bench Boost, Triple Captain. Check
  `fpl.squad(...)["chips_available"]` before ever suggesting one.
- **Two sets of chips, and the first set expires.** One of each runs to GW19; a
  fresh set of all four arrives for GW20-GW38. Anything unused at the GW19
  deadline (1 January 2027) is simply lost. **Only one chip may be played in any
  single gameweek**, so four unplayed chips need four separate gameweeks. Ido
  holds all four, unused. The Rules Enforcer owns this and raises it unprompted;
  `bootstrap()["chips"]` carries the real `start_event`/`stop_event` for all
  eight, so read it rather than trusting this paragraph.
- Deadline is 90 minutes before the first match of the gameweek.

## Project layout

```
FPL Manager/
├── CLAUDE.md          this file - shared context for every agent
├── fpl.py             data layer
├── due.py             what report is due, judged from the deadline
├── chips.md           the chip plan - Rules Enforcer owns it
├── progress.py        live per-agent progress board for a running staff meeting
├── ledger.md          every chip, captain and transfer, judged right/wrong - Historian owns it
├── chipcalc.py        what each chip is worth, week by week
├── team_update.py     records the XI he tells us he is fielding
├── health.py          is the team file current, did the reports run
├── elite.py           what the world top 100 own
├── gap.py             the gap to each rival per gameweek, trend, pace needed
├── benchmark.py       top 100 / world average, Team of the Week, score /10, ranks, league gaps
├── league_status.py   the league's transfers, chips, free transfers and chips left - Rules Enforcer
├── season_review.py   Ido v rivals: transfers, hits, captains, chips, bench
├── season_plan.md     the long plan to win the league - gap committee owns it
├── data/              cached API responses
└── .claude/agents/    the staff, one file per role
```

## Status

Built and in service: the data layer, the lineup renderer, the learning loop,
elite ownership, the four scheduled reports and the full staff of eight
specialists under the Assistant Manager (the Resource Manager joined on 23 Oct
2026, the same day the Haaland ban was lifted and the team-strength rule added).

**Models (Ido, 15 Oct 2026):** the specialists run on Opus and the manager
(the assistant-manager and the top-level scheduled run) on Fable. Do not downgrade
them to save cost. Every main report must name one thing the staff are doing
differently because of a past mistake recorded in `ledger.md` - Ido asked for
visible improvement, not the same advice again.

**The roster is Ido's to change.** Do not invent, merge or retire a role without
his instruction — but say so if one is missing rather than quietly covering the
gap in another agent's brief.
