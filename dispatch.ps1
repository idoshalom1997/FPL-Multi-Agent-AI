<#
.SYNOPSIS
    Runs whichever FPL reports are due, judged against the deadline.

.DESCRIPTION
    One Windows task calls this every few hours. It asks due.py what is due and
    runs it. Nothing is scheduled by weekday, because the FPL calendar does not
    keep to one: seven of this season's gameweeks have deadlines that are not on
    a Friday or Saturday, and for GW18 (Tuesday 29 December, 18:00) a Friday
    report would have arrived three days too late.

    Most invocations do nothing at all. due.py answers with nothing but "check",
    and the check itself exits before launching Claude unless a deadline is near
    or health.py has found something. A run that has work to do is the exception.

.EXAMPLE
    .\dispatch.ps1
    .\dispatch.ps1 -WhatIf      # say what would run, run nothing
#>
[CmdletBinding()]
param(
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location $Root

$LogDir = Join-Path $Root 'logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
$log = Join-Path $LogDir ("dispatch_{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))

function Log {
    param([string]$m)
    $line = '{0} {1}' -f (Get-Date -Format 'HH:mm:ss'), $m
    Write-Host $line
    Add-Content -LiteralPath $log -Value $line -Encoding UTF8
}

# One dispatcher at a time. On 23 Oct a main report started by hand at 08:45 was
# still running when the 09:00 pass fired, saw no receipt yet, and launched a
# second full staff meeting - two GW8 reports racing to the same inbox.
$lock = Join-Path $LogDir 'dispatch.lock'
if (Test-Path $lock) {
    $held = (Get-Content -LiteralPath $lock -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($held -and (Get-Process -Id ([int]$held) -ErrorAction SilentlyContinue)) {
        Log "Another dispatch (pid $held) is still running - skipping this pass."
        exit 0
    }
}
Set-Content -LiteralPath $lock -Value $PID -Encoding ASCII

$dueRaw = (& python due.py | Out-String)
if ($LASTEXITCODE -ne 0) {
    Log "due.py failed (exit $LASTEXITCODE): $($dueRaw.Trim())"
    exit 1
}

$due = @($dueRaw -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if (-not $due) {
    Log 'Nothing due.'
    exit 0
}

Log ("Due: {0}" -f ($due -join ', '))

foreach ($type in $due) {
    if ($type -notin @('planning', 'main', 'check', 'review')) {
        Log "Ignoring unexpected type '$type'."
        continue
    }

    if ($WhatIf) {
        Log "WhatIf: would run $type."
        continue
    }

    Log "--- running $type ---"
    & (Join-Path $Root 'run_report.ps1') -Type $type
    $code = $LASTEXITCODE

    if ($code -ne 0) {
        # Leave it unrecorded so the next pass tries again while the window is
        # still open. A failed report that marks itself done is a report that
        # never arrives and never retries - which is how one went missing for a
        # whole weekend.
        Log "$type FAILED (exit $code) - not recorded, will be retried."
        continue
    }

    # 'check' is offered on every pass and silences itself, so recording it
    # would switch it off permanently after the first quiet morning.
    if ($type -eq 'check') {
        Log 'check finished.'
        continue
    }

    & python due.py --done $type | Out-Null
    Log "$type finished and recorded."
}
