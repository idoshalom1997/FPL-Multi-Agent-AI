<#
.SYNOPSIS
    Registers, inspects or removes the scheduled FPL staff reports.

.DESCRIPTION
    ONE Windows task, running only while Ido is logged on because Claude needs a
    real user session:

      FPL - Scheduler        every 3 hours

    It calls dispatch.ps1, which asks due.py what is due and runs it. Nothing is
    scheduled by weekday. The old version was - planning Wednesday, main report
    Friday, review Tuesday - and that is simply wrong for seven of this season's
    gameweeks: five have midweek deadlines and two are Sundays. For GW18 the
    deadline is Tuesday 29 December at 18:00, so the Friday report would have
    landed three days after Ido could use it and the Tuesday review would have
    run before the gameweek it reviewed had started.

    Dumb schedule, smart behaviour, as before - only now the smartness covers
    which report to run as well as whether to speak at all. Most passes do
    nothing and cost a second of Python.

.EXAMPLE
    .\schedule.ps1 -Install
    .\schedule.ps1 -Status
    .\schedule.ps1 -RunNow main
    .\schedule.ps1 -Uninstall
#>
[CmdletBinding(DefaultParameterSetName = 'Status')]
param(
    [Parameter(ParameterSetName = 'Install')]   [switch]$Install,
    [Parameter(ParameterSetName = 'Install')]   [string]$Evening = '20:00',
    [Parameter(ParameterSetName = 'Install')]   [string]$CheckTime = '09:00',
    [Parameter(ParameterSetName = 'Uninstall')] [switch]$Uninstall,
    [Parameter(ParameterSetName = 'Status')]    [switch]$Status,
    [Parameter(ParameterSetName = 'RunNow')]
    [ValidateSet('planning', 'main', 'check', 'review')] [string]$RunNow
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Runner = Join-Path $Root 'run_report.ps1'

$Dispatcher = Join-Path $Root 'dispatch.ps1'

$TASKS = @(
    @{ Name = 'FPL - Scheduler'; EveryHours = 3 }
)

# Registered by earlier versions; removed on install so the weekday tasks cannot
# keep firing alongside the scheduler and send everything twice.
$OBSOLETE = @(
    'FPL - Planning brief', 'FPL - Main report',
    'FPL - Review', 'FPL - Deadline check', 'FPL - Live watch'
)

if ($RunNow) {
    & $Runner -Type $RunNow
    return
}

if ($Uninstall) {
    foreach ($name in $OBSOLETE) {
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            Write-Host "Removed '$name'." -ForegroundColor Yellow
        }
    }
    foreach ($t in $TASKS) {
        if (Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false
            Write-Host "Removed '$($t.Name)'." -ForegroundColor Yellow
        }
    }
    return
}

if ($Install) {
    if (-not (Test-Path $Runner)) { throw "run_report.ps1 not found beside this script." }
    if (-not (Test-Path $Dispatcher)) { throw "dispatch.ps1 not found beside this script." }

    foreach ($name in $OBSOLETE) {
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            Write-Host "Removed obsolete task '$name'." -ForegroundColor Yellow
        }
    }

    foreach ($t in $TASKS) {
        $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
            -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $Dispatcher) `
            -WorkingDirectory $Root

        # Omitting -RepetitionDuration is what makes it repeat indefinitely;
        # [TimeSpan]::MaxValue is rejected outright, as Task Scheduler cannot
        # format a duration that long.
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
            -RepetitionInterval (New-TimeSpan -Hours $t.EveryHours)

        # Claude needs an interactive desktop session, so these run only while
        # Ido is logged on, in his own security context.
        $principal = New-ScheduledTaskPrincipal `
            -UserId ("{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME) `
            -LogonType Interactive -RunLevel Limited

        $settings = New-ScheduledTaskSettingsSet `
            -StartWhenAvailable `
            -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
            -RunOnlyIfNetworkAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
            -MultipleInstances IgnoreNew

        if (Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false
        }
        Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger `
            -Principal $principal -Settings $settings `
            -Description "FPL Manager: runs whichever report is due, judged from the deadline." | Out-Null

        $when = "every $($t.EveryHours)h"
        Write-Host ("Installed {0,-24} {1}" -f $t.Name, $when) -ForegroundColor Green
    }
    Write-Host ''
}

# Status prints by default, and after an install.
$rows = foreach ($t in $TASKS) {
    $task = Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue
    if (-not $task) {
        [pscustomobject]@{ Task = $t.Name; State = 'not installed'; NextRun = ''; LastResult = '' }
        continue
    }
    $info = Get-ScheduledTaskInfo -TaskName $t.Name
    [pscustomobject]@{
        Task       = $t.Name
        State      = $task.State
        NextRun    = $info.NextRunTime
        LastResult = $info.LastTaskResult
    }
}
$rows | Format-Table -AutoSize

if (-not $Install -and ($rows | Where-Object { $_.State -eq 'not installed' })) {
    Write-Host "Run:  .\schedule.ps1 -Install" -ForegroundColor Yellow
}
