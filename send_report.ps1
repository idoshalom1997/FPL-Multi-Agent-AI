<#
.SYNOPSIS
    Sends an FPL staff report by email, with lineup images embedded inline.

.DESCRIPTION
    Reuses the Gmail App Password already stored as an encrypted credential file.
    That credential is encrypted with the Windows Data Protection API and can
    only be decrypted by this Windows user on this machine.

    Images passed via -Attachments are embedded inline in the order given. Any
    occurrence of [[IMG1]], [[IMG2]] ... in the HTML body is replaced with that
    image; anything not referenced is appended at the end of the mail. Images are
    therefore visible in the message itself, not just as files to download.

.EXAMPLE
    .\send_report.ps1 -Subject "FPL GW4 - main report" `
                      -BodyFile report.html `
                      -Attachments "reports/gw4_safe.png,reports/gw4_diff.png"

.EXAMPLE
    .\send_report.ps1 -Subject "Test" -Body "<p>hello</p>"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$Subject,
    [string]$Body,
    [string]$BodyFile,
    [string]$Attachments,
    [string]$To = '<your email>',
    [string]$CredentialPath = '.\smtp.cred.xml',
    [string]$SmtpServer = 'smtp.gmail.com',
    [int]$SmtpPort = 587
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $CredentialPath)) {
    throw "SMTP credential not found at $CredentialPath. Create it with Get-Credential | Export-Clixml."
}
$cred = Import-Clixml -LiteralPath $CredentialPath
$from = $cred.UserName

if ($BodyFile) {
    if (-not (Test-Path $BodyFile)) { throw "Body file not found: $BodyFile" }
    $html = Get-Content -LiteralPath $BodyFile -Raw -Encoding UTF8
} elseif ($Body) {
    $html = $Body
} else {
    throw 'Provide either -Body or -BodyFile.'
}

$files = @()
if ($Attachments) {
    foreach ($f in $Attachments -split ',') {
        $f = $f.Trim()
        if (-not $f) { continue }
        $resolved = (Resolve-Path -LiteralPath $f -ErrorAction Stop).Path
        $files += $resolved
    }
}

$mail = New-Object System.Net.Mail.MailMessage
$mail.From = New-Object System.Net.Mail.MailAddress($from, 'FPL Manager')
$mail.To.Add($To)
# Every report carries the same prefix so one Gmail filter can route them all
# to the FPL label without matching anything else.
# NOT -like: in a wildcard pattern '[FPL]' is a CHARACTER CLASS, so any subject
# beginning with F, P or L matched it and silently went out unprefixed. The GW5
# planning brief ("Planning") arrived that way before this was caught.
if (-not $Subject.StartsWith('[FPL]')) { $Subject = "[FPL] $Subject" }
$mail.Subject = $Subject
$mail.SubjectEncoding = [System.Text.Encoding]::UTF8
$mail.BodyEncoding = [System.Text.Encoding]::UTF8

$resources = @()
$i = 0
foreach ($path in $files) {
    $i++
    $ext = [System.IO.Path]::GetExtension($path).TrimStart('.').ToLower()
    if ($ext -notin @('png', 'jpg', 'jpeg', 'gif')) {
        # Not an image: send it as a normal attachment instead.
        $mail.Attachments.Add((New-Object System.Net.Mail.Attachment($path)))
        continue
    }
    $cid = "img$i"
    $lr = New-Object System.Net.Mail.LinkedResource($path, "image/$ext")
    $lr.ContentId = $cid
    $lr.TransferEncoding = [System.Net.Mime.TransferEncoding]::Base64
    $resources += $lr

    $token = "[[IMG$i]]"
    $tag = "<img src=`"cid:$cid`" style=`"width:100%;max-width:560px;height:auto;border-radius:10px;margin:14px 0`" />"
    if ($html -match [regex]::Escape($token)) {
        $html = $html -replace [regex]::Escape($token), $tag
    } else {
        $html += $tag
    }
}

$view = [System.Net.Mail.AlternateView]::CreateAlternateViewFromString($html, $null, 'text/html')
foreach ($r in $resources) { [void]$view.LinkedResources.Add($r) }
$mail.AlternateViews.Add($view)

$smtp = New-Object System.Net.Mail.SmtpClient($SmtpServer, $SmtpPort)
$smtp.EnableSsl = $true
$smtp.Timeout = 60000
$smtp.Credentials = New-Object System.Net.NetworkCredential($cred.UserName, $cred.GetNetworkCredential().Password)

try {
    $smtp.Send($mail)
    Write-Host "Sent '$Subject' to $To with $($resources.Count) inline image(s)." -ForegroundColor Green

    # Receipt. run_report.ps1 reads this to prove an email actually left the
    # machine, because a report run can finish cleanly having sent nothing -
    # which is exactly how the GW5 report went missing.
    $receiptDir = Join-Path $PSScriptRoot 'logs'
    if (-not (Test-Path $receiptDir)) { New-Item -ItemType Directory -Force -Path $receiptDir | Out-Null }
    Add-Content -LiteralPath (Join-Path $receiptDir 'sent.log') -Encoding UTF8 `
        -Value ("{0}`t{1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Subject)
} catch {
    Write-Host "Send FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    foreach ($r in $resources) { $r.Dispose() }
    $mail.Dispose()
}
