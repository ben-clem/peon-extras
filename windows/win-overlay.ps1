# PEON-EXTRAS-WIN-OVERLAY
# Windows port of peon-ping's macOS overlay (scripts/mac-overlay.js, the default "neon" look) at the
# peon-extras size (build-large-overlay.py): 650x100, rounded 12, 95% opaque solid colour, pack icon
# 72 px, bold 18 title over a 14 excerpt, left aligned, "click to dismiss" hint, top-center of every
# screen, stacked in slots 10 px apart, auto-dismiss after notification_dismiss_seconds.
# Drawn with WPF from Windows PowerShell 5.1 (no extra runtime). Borderless, topmost, never takes
# focus (WS_EX_NOACTIVATE + ShowActivated=false), no taskbar button, click anywhere to dismiss.
# A newer banner from the same chat replaces the live one in its slot (like notify.sh stacking).
# Called by the win-notify.ps1 wrapper; throws on failure so the wrapper can fall back to a toast.
param(
    [Parameter(Mandatory = $true)][string]$title,
    [string]$body = '',
    [string]$color = 'blue',
    [string]$iconPath = '',
    [double]$dismissSeconds = 30,
    [string]$sessionId = '',
    [string]$position = 'top-center',
    [string]$allScreens = 'true'
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase, System.Windows.Forms, System.Drawing
Add-Type -Namespace PeonExtras -Name Win32 -MemberDefinition @'
[DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr hWnd, int nIndex);
[DllImport("user32.dll")] public static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
'@

# ---- slots (%TEMP%\peon-extras-popups): slot-N holds the owning PID; .session-<id> = "slot|pid" ----
$slotDir = Join-Path $env:TEMP 'peon-extras-popups'
[void][IO.Directory]::CreateDirectory($slotDir)
function Test-PeonAlive([int]$p) {
    if ($p -le 0) { return $false }
    $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
    return [bool]($proc -and $proc.ProcessName -match '^(powershell|pwsh)$')
}
function Invoke-PeonClaim([int]$n) {
    $f = Join-Path $slotDir "slot-$n"
    for ($try = 0; $try -lt 2; $try++) {
        try {
            $fs = [IO.File]::Open($f, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
            $b = [Text.Encoding]::ASCII.GetBytes([string]$PID); $fs.Write($b, 0, $b.Length); $fs.Close()
            return $true
        } catch {
            $owner = 0
            try { $owner = [int]([IO.File]::ReadAllText($f).Trim()) } catch {}
            if (Test-PeonAlive $owner) { return $false }
            Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
        }
    }
    return $false
}
$safe = ($sessionId -replace '[^A-Za-z0-9_-]', '')
if ($safe.Length -gt 64) { $safe = $safe.Substring(0, 64) }
$sessFile = $null
$preferred = -1
if ($safe) {
    $sessFile = Join-Path $slotDir ".session-$safe"
    if (Test-Path -LiteralPath $sessFile) {
        $parts = ([IO.File]::ReadAllText($sessFile).Trim()) -split '\|'
        $oldSlot = -1; $oldPid = 0
        [void][int]::TryParse($parts[0], [ref]$oldSlot)
        if ($parts.Count -gt 1) { [void][int]::TryParse($parts[1], [ref]$oldPid) }
        if ($oldPid -ne $PID -and (Test-PeonAlive $oldPid)) {
            Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 80
        }
        if ($oldSlot -ge 0) {
            Remove-Item -LiteralPath (Join-Path $slotDir "slot-$oldSlot") -Force -ErrorAction SilentlyContinue
            $preferred = $oldSlot
        }
    }
}
$slot = -1
if ($preferred -ge 0 -and (Invoke-PeonClaim $preferred)) { $slot = $preferred }
for ($n = 0; $slot -lt 0 -and $n -lt 5; $n++) { if (Invoke-PeonClaim $n) { $slot = $n } }
if ($slot -lt 0) { $slot = 0 }
if ($sessFile) { [IO.File]::WriteAllText($sessFile, "$slot|$PID") }

# ---- look (mac-overlay.js colours; peon-extras geometry) ----
$ovW = 650; $ovH = 100; $margin = 10
switch ($color) {
    'yellow' { $rgb = @(200, 160, 0) }
    'red'    { $rgb = @(180, 0, 0) }
    default  { $rgb = @(30, 80, 180) }
}
$bgBrush = New-Object Windows.Media.SolidColorBrush ([Windows.Media.Color]::FromRgb($rgb[0], $rgb[1], $rgb[2]))
$white = [Windows.Media.Brushes]::White
$subBrush = New-Object Windows.Media.SolidColorBrush ([Windows.Media.Color]::FromArgb(217, 255, 255, 255))
$hintBrush = New-Object Windows.Media.SolidColorBrush ([Windows.Media.Color]::FromArgb(153, 255, 255, 255))
$font = New-Object Windows.Media.FontFamily 'Segoe UI Variable Text, Segoe UI, Segoe UI Emoji, Segoe UI Symbol'
$icon = $null
if ($iconPath -and (Test-Path -LiteralPath $iconPath -PathType Leaf)) {
    $icon = New-Object Windows.Media.Imaging.BitmapImage
    $icon.BeginInit(); $icon.CacheOption = 'OnLoad'; $icon.UriSource = New-Object Uri ((Resolve-Path -LiteralPath $iconPath).Path); $icon.EndInit()
}

$app = [Windows.Application]::Current
if (-not $app) { $app = New-Object Windows.Application }
$app.ShutdownMode = 'OnExplicitShutdown'
$script:windows = New-Object System.Collections.ArrayList
$script:closing = $false
function Close-PeonOverlay {
    if ($script:closing) { return }
    $script:closing = $true
    try { Remove-Item -LiteralPath (Join-Path $slotDir "slot-$slot") -Force -ErrorAction SilentlyContinue } catch {}
    try {
        if ($sessFile -and (Test-Path -LiteralPath $sessFile) -and ([IO.File]::ReadAllText($sessFile).Trim() -eq "$slot|$PID")) {
            Remove-Item -LiteralPath $sessFile -Force -ErrorAction SilentlyContinue
        }
    } catch {}
    $app.Shutdown()
}

function New-PeonWindow([System.Windows.Forms.Screen]$screen) {
    $w = New-Object Windows.Window
    $w.WindowStyle = 'None'; $w.AllowsTransparency = $true; $w.Background = [Windows.Media.Brushes]::Transparent
    $w.Topmost = $true; $w.ShowActivated = $false; $w.ShowInTaskbar = $false; $w.ResizeMode = 'NoResize'
    $w.Focusable = $false; $w.WindowStartupLocation = 'Manual'; $w.Left = -32000; $w.Top = -32000
    $w.Width = $ovW; $w.Height = $ovH; $w.Opacity = 0; $w.Title = 'peon-extras overlay'
    $w.Cursor = [Windows.Input.Cursors]::Hand
    $w.Tag = @{ scr = $screen }

    $border = New-Object Windows.Controls.Border
    $border.CornerRadius = New-Object Windows.CornerRadius 12
    $border.Background = $bgBrush
    $grid = New-Object Windows.Controls.Grid
    $border.Child = $grid

    $textX = 10
    if ($icon) {
        $img = New-Object Windows.Controls.Image
        $img.Source = $icon; $img.Width = 72; $img.Height = 72; $img.Stretch = 'Uniform'
        $img.HorizontalAlignment = 'Left'; $img.VerticalAlignment = 'Center'; $img.Margin = New-Object Windows.Thickness 10, 0, 0, 0
        [Windows.Media.RenderOptions]::SetBitmapScalingMode($img, 'HighQuality')
        [void]$grid.Children.Add($img)
        $textX = 10 + 72 + 16
    }
    $stack = New-Object Windows.Controls.StackPanel
    $stack.VerticalAlignment = 'Center'; $stack.Margin = New-Object Windows.Thickness $textX, 0, 20, 0
    $t = New-Object Windows.Controls.TextBlock
    $t.Text = $title; $t.FontFamily = $font; $t.FontSize = 18; $t.FontWeight = 'Bold'; $t.Foreground = $white
    $t.TextTrimming = 'CharacterEllipsis'; $t.TextWrapping = 'NoWrap'
    [void]$stack.Children.Add($t)
    if ($body) {
        $s = New-Object Windows.Controls.TextBlock
        $s.Text = $body; $s.FontFamily = $font; $s.FontSize = 14; $s.Foreground = $subBrush
        $s.TextTrimming = 'CharacterEllipsis'; $s.TextWrapping = 'NoWrap'; $s.Margin = New-Object Windows.Thickness 0, 10, 0, 0
        [void]$stack.Children.Add($s)
    }
    [void]$grid.Children.Add($stack)
    $hint = New-Object Windows.Controls.TextBlock
    $hint.Text = 'click to dismiss'; $hint.FontFamily = $font; $hint.FontSize = 10; $hint.Foreground = $hintBrush
    $hint.HorizontalAlignment = 'Right'; $hint.VerticalAlignment = 'Bottom'; $hint.Margin = New-Object Windows.Thickness 0, 0, 8, 7
    [void]$grid.Children.Add($hint)
    $w.Content = $border
    $w.Add_MouseLeftButtonUp({ Close-PeonOverlay })
    $w.Add_SourceInitialized({
        param($sender, $e)
        $hwnd = (New-Object Windows.Interop.WindowInteropHelper $sender).Handle
        $ex = [PeonExtras.Win32]::GetWindowLong($hwnd, -20)
        [void][PeonExtras.Win32]::SetWindowLong($hwnd, -20, ($ex -bor 0x08000000 -bor 0x00000080 -bor 0x00000008))
    })
    $w.Add_ContentRendered({
        param($sender, $e)
        $src = [Windows.PresentationSource]::FromVisual($sender)
        $sx = $src.CompositionTarget.TransformToDevice.M11; $sy = $src.CompositionTarget.TransformToDevice.M22
        $pw = [int][Math]::Round($ovW * $sx); $ph = [int][Math]::Round($ovH * $sy)
        $m = [int][Math]::Round($margin * $sx); $step = $ph + $m
        $scr = $sender.Tag.scr
        $wa = $scr.WorkingArea
        switch ($position) {
            'top-left'      { $x = $wa.Left + $m;                   $y = $wa.Top + $m + $slot * $step }
            'top-right'     { $x = $wa.Right - $pw - $m;            $y = $wa.Top + $m + $slot * $step }
            'bottom-left'   { $x = $wa.Left + $m;                   $y = $wa.Bottom - $ph - $m - $slot * $step }
            'bottom-right'  { $x = $wa.Right - $pw - $m;            $y = $wa.Bottom - $ph - $m - $slot * $step }
            'bottom-center' { $x = $wa.Left + [int](($wa.Width - $pw) / 2); $y = $wa.Bottom - $ph - $m - $slot * $step }
            default         { $x = $wa.Left + [int](($wa.Width - $pw) / 2); $y = $wa.Top + $m + $slot * $step }
        }
        $hwnd = (New-Object Windows.Interop.WindowInteropHelper $sender).Handle
        # HWND_TOPMOST, SWP_NOSIZE|SWP_NOACTIVATE|SWP_SHOWWINDOW
        [void][PeonExtras.Win32]::SetWindowPos($hwnd, [IntPtr](-1), $x, $y, 0, 0, 0x0001 -bor 0x0010 -bor 0x0040)
        $sender.Tag = @{ scr = $scr; x = $x; y = $y; w = $pw; h = $ph; screen = $scr.DeviceName; primary = $scr.Primary; wa = $wa }
        $fade = New-Object Windows.Media.Animation.DoubleAnimation 0, 0.95, (New-Object Windows.Duration ([TimeSpan]::FromMilliseconds(140)))
        $sender.BeginAnimation([Windows.Window]::OpacityProperty, $fade)
    })
    return $w
}

$screens = @([System.Windows.Forms.Screen]::AllScreens)
if ($allScreens -ne 'true') {
    $cur = [System.Windows.Forms.Screen]::FromPoint([System.Windows.Forms.Cursor]::Position)
    $screens = @($cur)
}
foreach ($sc in $screens) {
    $win = New-PeonWindow $sc
    [void]$script:windows.Add($win)
    $win.Show()
}

# Optional proof hook: PEON_EXTRAS_OVERLAY_SNAPSHOT=<dir> saves the rendered banner and an on-screen
# capture of the top strip around it (primary screen) shortly after it appears.
$snapDir = [string]$env:PEON_EXTRAS_OVERLAY_SNAPSHOT
if ($snapDir) {
    $snapTimer = New-Object Windows.Threading.DispatcherTimer
    $snapTimer.Interval = [TimeSpan]::FromMilliseconds(900)
    $snapTimer.Add_Tick({
        $snapTimer.Stop()
        try {
            [void][IO.Directory]::CreateDirectory($snapDir)
            $stamp = Get-Date -Format 'HHmmss'
            $target = $script:windows | Where-Object { $_.Tag -and $_.Tag.primary } | Select-Object -First 1
            if (-not $target) { $target = $script:windows[0] }
            $rtb = New-Object Windows.Media.Imaging.RenderTargetBitmap ([int]($ovW * 2)), ([int]($ovH * 2)), 192, 192, ([Windows.Media.PixelFormats]::Pbgra32)
            $rtb.Render($target.Content)
            $enc = New-Object Windows.Media.Imaging.PngBitmapEncoder
            $enc.Frames.Add([Windows.Media.Imaging.BitmapFrame]::Create($rtb))
            $fs = [IO.File]::Create((Join-Path $snapDir "overlay-render-$stamp-slot$slot.png")); $enc.Save($fs); $fs.Close()
            $g = $target.Tag
            $pad = 12
            $left = [Math]::Max($g.wa.Left, $g.x - $pad); $top = $g.wa.Top
            $right = [Math]::Min($g.wa.Right, $g.x + $g.w + $pad); $bottom = $g.y + $g.h + $pad
            $bmp = New-Object System.Drawing.Bitmap ($right - $left), ($bottom - $top)
            $gr = [System.Drawing.Graphics]::FromImage($bmp)
            $gr.CopyFromScreen($left, $top, 0, 0, $bmp.Size)
            $gr.Dispose()
            $bmp.Save((Join-Path $snapDir "overlay-screen-$stamp-slot$slot.png"), [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
            $info = "slot=$slot pid=$PID screen=$($g.screen) primary=$($g.primary) workArea=$($g.wa) overlayPx=($($g.x),$($g.y),$($g.w)x$($g.h)) capture=($left,$top)-($right,$bottom) screens=$($script:windows.Count)"
            Add-Content -LiteralPath (Join-Path $snapDir 'overlay-snapshots.txt') -Value "$stamp $info" -Encoding UTF8
        } catch {
            Add-Content -LiteralPath (Join-Path $snapDir 'overlay-snapshots.txt') -Value ("snapshot error: " + $_.Exception.Message) -Encoding UTF8
        }
    })
    $snapTimer.Start()
}

if ($dismissSeconds -gt 0) {
    $timer = New-Object Windows.Threading.DispatcherTimer
    $timer.Interval = [TimeSpan]::FromSeconds($dismissSeconds)
    $timer.Add_Tick({ Close-PeonOverlay })
    $timer.Start()
}
[void]$app.Run()
