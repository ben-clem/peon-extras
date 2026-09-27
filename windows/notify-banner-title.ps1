# PEON-EXTRAS-WIN-NOTIFY-WRAPPER
# Windows port of notify-banner-title.sh. Installed as
#   %USERPROFILE%\.claude\hooks\peon-ping\scripts\win-notify.ps1
# (peon.ps1 calls that path for every toast). The packaged script is kept as
#   %USERPROFILE%\.local\share\peon-extras\win-notify.stock.ps1
# This wrapper restores the cached "<laptop> Cursor <folder> workspace <speech> chat" title for the
# session that fired the event, puts it on the toast's first line with the excerpt under it, and
# swaps peon.ps1's hardcoded PreCompact body for the cached "Summarizing: ..." line.
# Banners are drawn by win-overlay.ps1 (port of the macOS neon overlay); the Windows toast is only
# the fallback when the overlay throws, or when peon-extras.json has "banner_style": "toast".
# Restore stock behaviour: copy win-notify.stock.ps1 back over scripts\win-notify.ps1.
param(
    [Parameter(Mandatory=$true)]
    [string]$body,
    [Parameter(Mandatory=$true)]
    [string]$title,
    [string]$iconPath,
    [int]$dismissSeconds = 4,
    [int]$parentPid = 0
)

$extras = if ($env:PEON_EXTRAS_DIR) { $env:PEON_EXTRAS_DIR } else { Join-Path $env:USERPROFILE '.local\share\peon-extras' }
$stock = Join-Path $extras 'win-notify.stock.ps1'
if (-not (Test-Path -LiteralPath $stock)) { exit 0 }
$cacheDir = if ($env:PEON_EXTRAS_CACHE_DIR) { $env:PEON_EXTRAS_CACHE_DIR } else { Join-Path $extras 'cache' }

$sid = ([string]$env:PEON_SESSION_ID) -replace '[^A-Za-z0-9_-]', ''
if ($sid.Length -gt 64) { $sid = $sid.Substring(0, 64) }

$newTitle = $title
$newBody = $body
$swapped = $false

if ($sid) {
    $titleFile = Join-Path $cacheDir "banner-title-$sid"
    if (Test-Path -LiteralPath $titleFile) {
        $lines = @(Get-Content -LiteralPath $titleFile -Encoding UTF8 -ErrorAction SilentlyContinue)
        $match = if ($lines.Count -ge 1) { [string]$lines[0] } else { '' }
        $bannerTitle = if ($lines.Count -ge 2) { [string]$lines[1] } else { '' }
        $plainTitle = if ($lines.Count -ge 3) { [string]$lines[2] } else { '' }
        $display = if ($bannerTitle) { $bannerTitle } else { $plainTitle }
        # Only replace the title peon.ps1 built for this session's folder (marker + folder name),
        # so a notification_title_override or project_name_map title passes through untouched.
        $titleMatches = ($env:PEON_EXTRAS_FORCE_TITLE -eq '1') -or ($match -and $title.TrimEnd().EndsWith($match))
        if ($display -and $titleMatches) {
            $newTitle = $display
            $swapped = $true
        }
    }
}

# peon.ps1 hardcodes the PreCompact body ("context limit: Context compacting"); peon.sh on macOS
# uses "compacting: Context compacting". precompact.mjs caches the real Summarizing line.
$isCompact = ($body -eq 'context limit: Context compacting' -or $body -eq 'compacting: Context compacting')
if ($isCompact) {
    $compactBody = ''
    if ($sid) {
        $compactFile = Join-Path $cacheDir "compact-body-$sid"
        if (Test-Path -LiteralPath $compactFile) {
            $compactBody = [string](@(Get-Content -LiteralPath $compactFile -Encoding UTF8 -TotalCount 1 -ErrorAction SilentlyContinue)[0])
        }
    }
    $newBody = if ($compactBody) { $compactBody } else { 'Summarizing this chat now' }
}
if (-not $newBody) { $newBody = 'Done' }

function Write-PeonLog([string]$text) {
    try {
        $logDir = Join-Path $extras 'logs'
        if (Test-Path -LiteralPath $logDir) {
            Add-Content -LiteralPath (Join-Path $logDir 'hooks.log') -Encoding UTF8 -Value ('{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $PID, $text)
        }
    } catch {}
}

# ---- overlay first (macOS look) ----
$settings = $null
try { $settings = Get-Content -LiteralPath (Join-Path $extras 'peon-extras.json') -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
$style = if ($settings -and $settings.banner_style) { [string]$settings.banner_style } else { 'overlay' }
$overlay = Join-Path $extras 'win-overlay.ps1'
if ($style -ne 'toast' -and (Test-Path -LiteralPath $overlay)) {
    $cfg = $null
    try {
        $peonDir = Split-Path -Parent $PSScriptRoot
        $cfg = Get-Content -LiteralPath (Join-Path $peonDir 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {}
    $pos = if ($cfg -and $cfg.notification_position) { [string]$cfg.notification_position } else { 'top-center' }
    $all = if ($cfg -and $null -ne $cfg.notification_all_screens) { ([string]$cfg.notification_all_screens).ToLower() } else { 'true' }
    # mac-overlay.js colours as peon.sh assigns them here: Stop/after-summary blue, PreCompact red.
    $color = if ($isCompact) { 'red' } else { 'blue' }
    $icon = $iconPath
    if (-not $icon) { $icon = Join-Path $extras 'peon-icon.png' }
    $ovTitle = if ($swapped) { $newTitle } else { ($newTitle -replace '\s+', ' ').Trim() }
    Write-PeonLog ('overlay title="{0}" body="{1}" color={2} session={3}' -f $ovTitle, $newBody, $color, $sid)
    try {
        & $overlay -title $ovTitle -body $newBody -color $color -iconPath $icon -dismissSeconds $dismissSeconds -sessionId $sid -position $pos -allScreens $all
        exit 0
    } catch {
        Write-PeonLog ('overlay failed, falling back to toast: {0}' -f $_.Exception.Message)
    }
}

# ---- toast fallback ----
$params = @{ dismissSeconds = $dismissSeconds; parentPid = $parentPid }
if ($iconPath) { $params.iconPath = $iconPath }
if ($swapped) {
    # Toast line 1 (bold) is the packaged script's -body: show the title there, excerpt below.
    $params.body = $newTitle
    $params.title = $newBody
} else {
    $params.body = $newBody
    $params.title = $newTitle
}
Write-PeonLog ('toast line1="{0}" line2="{1}" session={2}' -f $params.body, $params.title, $sid)
& $stock @params
exit 0
