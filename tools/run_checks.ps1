<#
.SYNOPSIS
  One-click verification kit for the tick-driven Renko article series (MetaTrader 5).

.DESCRIPTION
  Run this yourself, in an interactive PowerShell window, with MetaTrader 5 CLOSED.

    powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_checks.ps1 -Mode Tests
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_checks.ps1 -Mode Sweep
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_checks.ps1 -Mode Validation
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_checks.ps1 -Mode All

  Modes
    Tests       Starts terminal64.exe with a generated /config file that runs the script
                Renko\Tests\RenkoEngineTests, waits for the line "RenkoEngineTests:" in the newest
                MQL5\Logs\YYYYMMDD.log, closes the terminal and prints the summary and FAIL lines.
    Sweep       Same mechanism with Renko\RenkoSweep and a generated preset (CSV XAUUSD_ticks.csv,
                InpOutPrefix=RenkoSweep_XAUUSD_MQL5, InpMaxSpreadMult=25). Waits for "RenkoSweep: done."
                (30-90 minutes; timeout -SweepTimeoutMin, default 180), tails the log, then runs
                tools\compare_sweep.py against results\sweep.
    Validation  Runs RenkoTickContinuationEA in the Strategy Tester, one generated tester .ini per case,
                mirroring the self-test checklist table in docs\series\renko-ticks\drafts\ep04.md.
                Parses each tester report (trade count only), scans the tester logs for errors and writes
                results\ep04\tester\summary.md.
    All         Tests, then Sweep, then Validation.

  Every mode writes a timestamped transcript to results\verification\.

  What it does and does not do
    * It only starts MetaTrader as a script runner or as the Strategy Tester. It does not open charts,
      does not place orders, does not read or write terminal settings, accounts, servers or passwords.
    * Every generated /config file has [Experts] AllowLiveTrading=0 so that no Expert Advisor attached to a
      chart restored at start-up can trade. The Strategy Tester trades only on its own simulated account.
    * It refuses to start while terminal64.exe from the configured path is running (close MetaTrader first).
    * Use a DEMO account as the terminal's last-used account, for safety. The script prints this warning and
      asks you to type YES (Read-Host) before it launches anything.
    * It writes only: generated .ini/.set files, tester reports, logs and summaries inside the repository's
      results\ folder, and two kinds of small input files that MetaTrader reads by design:
      MQL5\Presets\RenkoVerify_sweep.set and MQL5\Profiles\Tester\RenkoVerify_*.set, plus the tester
      reports in <data folder>\RenkoVerify\ (copied into the repository afterwards).

  Exit code: 0 when every executed check passed, 1 when anything failed, 2 when the kit could not start.

.PARAMETER Mode
  Tests | Sweep | Validation | All.
.PARAMETER Cases
  Validation only: run just these case ids, e.g. -Cases 1,2,9. Ids: 1 2 3 4 5 6 7a 7b 7c 8a 8b 9 10 11 12 13 14 15.
.PARAMETER Symbols
  Validation only: override symbol names for the broker, e.g. -Symbols @{Index='US500.cash'; Crypto='ETHUSD'}.
  Keys: Forex (EURUSD), Jpy (USDJPY), Gold (XAUUSD), Index (US500), Crypto (BTCUSD), Any (EURUSD).
.PARAMETER SymbolSuffix
  Validation only: appended to every default symbol that you did not override, e.g. '.r' or '_'.
.PARAMETER Model
  Tester model: 4 = every tick based on real ticks (default), 0 = every tick (generated). With model 4 a case
  that produces no report is retried once with model 0 unless -NoFallback is given.
.PARAMETER HistoryDays
  Validation only: length of the test window, ending yesterday (default 28 days).
.PARAMETER Login
  Optional account NUMBER written to [Common] of the generated config so that the terminal logs in to a
  specific account. Never a password. Leave empty to let the terminal use its last account.
.PARAMETER AssumeYes
  Skip the YES prompt (only for re-runs you have already confirmed yourself).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Tests', 'Sweep', 'Validation', 'All')]
    [string]$Mode,

    [string]$TerminalExe = 'C:\Program Files\MetaTrader 5\terminal64.exe',
    [string]$DataDir     = (Join-Path $env:APPDATA 'MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075'),
    [string]$CommonDir   = (Join-Path $env:APPDATA 'MetaQuotes\Terminal\Common'),
    [string]$RepoDir     = '',

    [string]$ChartSymbol = 'EURUSD',
    [string]$ChartPeriod = 'H1',

    [int]$TestsTimeoutMin = 10,
    [int]$SweepTimeoutMin = 180,
    [int]$CaseTimeoutMin  = 60,
    [int]$CloseGraceSec   = 60,

    [ValidateSet(0, 4)]
    [int]$Model = 4,
    [switch]$NoFallback,

    [string[]]$Cases = @(),
    [hashtable]$Symbols = @{},
    [string]$SymbolSuffix = '',
    [int]$HistoryDays = 28,
    [string]$ToDate = '',
    [string]$Leverage = '1:100',
    [string]$Currency = 'USD',
    [int]$MinTradesDefault = 3,

    [string]$Login = '',
    [string]$IgnoreRegex = '',
    [switch]$ShowAllLog,
    [switch]$AssumeYes
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# ----------------------------------------------------------------------------------------------
# constants
# ----------------------------------------------------------------------------------------------
$script:ToolsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrEmpty($RepoDir)) { $RepoDir = Split-Path -Parent $script:ToolsDir }
$script:RepoDir     = $RepoDir
$script:Stamp       = (Get-Date).ToString('yyyyMMdd_HHmmss')
$script:TranscriptPath = $null
$script:Proc        = $null
$script:TesterErrRegex = 'failed|error|\[100|array out of range|zero divide|initialization failed'

$script:EaDefaults = [ordered]@{
    InpBrickMode       = '0'
    InpAtrFraction     = '0.25'
    InpAtrPeriod       = '14'
    InpAtrWaitMinutes  = '60'
    InpBrickPoints     = '300'
    InpSameBricks      = '2'
    InpSLBricks        = '2.0'
    InpTPBricks        = '0.0'
    InpCloseOnOpposite = 'true'
    InpWarmupBricks    = '3'
    InpWarmupDays      = '2'
    InpLotMode         = '0'
    InpFixedLots       = '0.01'
    InpRiskPercent     = '1.0'
    InpMaxSpreadPoints = '0'
    InpSlippagePoints  = '30'
    InpMagic           = '26100401'
}

$script:SweepSet = [ordered]@{
    InpSource        = '0'
    InpCsvFile       = 'XAUUSD_ticks.csv'
    InpSymbol        = 'XAUUSD'
    InpFixedSizes    = '0.5,1,2,3,4,5,6,8,10,12,15,20,25,30,40,50'
    InpAtrFractions  = '0.05,0.10,0.15,0.20,0.30,0.40,0.50,0.75,1.00'
    InpPrice         = '0'
    InpImpulseMin    = '3'
    InpPullbackMax   = '2'
    InpCommissionSide = '0.035'
    InpLatencyMs     = '0'
    InpDumpBrick     = '0'
    InpOutPrefix     = 'RenkoSweep_XAUUSD_MQL5'
    InpMaxSpreadMult = '25'
}

# ----------------------------------------------------------------------------------------------
# logging
# ----------------------------------------------------------------------------------------------
function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $line = "[$ts] [$Level] $Message"
    $color = switch ($Level) { 'WARN' { 'Yellow' } 'ERROR' { 'Red' } 'PASS' { 'Green' } 'FAIL' { 'Red' } default { 'Gray' } }
    Write-Host $line -ForegroundColor $color
    if ($script:TranscriptPath) {
        try { Add-Content -LiteralPath $script:TranscriptPath -Value $line -Encoding UTF8 } catch { }
    }
}

function Write-Raw {
    param([string]$Text)
    Write-Host $Text
    if ($script:TranscriptPath) {
        try { Add-Content -LiteralPath $script:TranscriptPath -Value $Text -Encoding UTF8 } catch { }
    }
}

function New-Dir {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { [void](New-Item -ItemType Directory -Path $Path -Force) }
}

function Write-AsciiFile {
    # .ini and .set files: plain ASCII, CRLF, no BOM (the terminal reads them fine).
    param([string]$Path, [string]$Text)
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $enc)
}

# ----------------------------------------------------------------------------------------------
# terminal process handling
# ----------------------------------------------------------------------------------------------
function Get-RunningTerminals {
    # terminal64.exe processes whose image path equals $TerminalExe. A process whose path cannot be read
    # is counted too (conservative: better to refuse than to start a second instance).
    $exeFull = [System.IO.Path]::GetFullPath($TerminalExe)
    $found = @()
    $procs = @()
    try { $procs = @(Get-CimInstance -ClassName Win32_Process -Filter "Name='terminal64.exe'") } catch { $procs = @() }
    foreach ($p in $procs) {
        $path = $p.ExecutablePath
        if ([string]::IsNullOrEmpty($path)) { $found += $p; continue }
        if ([string]::Equals([System.IO.Path]::GetFullPath($path), $exeFull, [System.StringComparison]::OrdinalIgnoreCase)) { $found += $p }
    }
    return $found
}

function Start-Terminal {
    param([string]$IniPath)
    $argLine = '/config:"{0}"' -f $IniPath
    Write-Log "Launching: `"$TerminalExe`" $argLine"
    $script:Proc = Start-Process -FilePath $TerminalExe -ArgumentList $argLine -PassThru
    return $script:Proc
}

function Stop-Terminal {
    # Graceful first: CloseMainWindow, repeated every 10 s. Stop-Process only after the grace period.
    param($Proc, [int]$GraceSec = 60)
    if ($null -eq $Proc) { return $true }
    try { if ($Proc.HasExited) { return $true } } catch { return $true }
    Write-Log "Closing the terminal gracefully (CloseMainWindow, up to $GraceSec s)."
    $deadline = (Get-Date).AddSeconds($GraceSec)
    $lastClose = [datetime]::MinValue
    while (-not $Proc.HasExited -and (Get-Date) -lt $deadline) {
        if (((Get-Date) - $lastClose).TotalSeconds -ge 10) {
            try { $Proc.Refresh(); [void]$Proc.CloseMainWindow() } catch { }
            $lastClose = Get-Date
        }
        Start-Sleep -Milliseconds 500
    }
    if ($Proc.HasExited) { Write-Log 'Terminal closed.'; return $true }
    Write-Log "WARNING: the terminal did not close within $GraceSec s; forcing Stop-Process. Check for unsaved work or a dialog box." 'WARN'
    try { Stop-Process -Id $Proc.Id -Force } catch { }
    try { [void]$Proc.WaitForExit(15000) } catch { }
    return $false
}

# ----------------------------------------------------------------------------------------------
# log reading (UTF-16LE logs, read only the bytes added since a snapshot)
# ----------------------------------------------------------------------------------------------
function Get-LogFilesIn {
    param([string[]]$Dirs)
    foreach ($d in $Dirs) {
        if (Test-Path -LiteralPath $d) {
            Get-ChildItem -LiteralPath $d -Filter '*.log' -File -ErrorAction SilentlyContinue
        }
    }
}

function New-LogState {
    param([string[]]$Dirs)
    $st = @{}
    foreach ($f in (Get-LogFilesIn $Dirs)) {
        $len = [int64]$f.Length
        $st[$f.FullName] = [int64]($len - ($len % 2))
    }
    return $st
}

function Read-LogDelta {
    # Returns the new lines of one log file and advances $State. Never throws for a locked/rotated file.
    param([string]$Path, [hashtable]$State)
    $off = [int64]0
    if ($State.ContainsKey($Path)) { $off = [int64]$State[$Path] }
    $fs = $null
    try {
        $fs = New-Object System.IO.FileStream($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete))
        if ($fs.Length -lt $off) { $off = 0 }
        if ($fs.Length -le $off) { $State[$Path] = $off; return @() }
        $n = [int][Math]::Min($fs.Length - $off, 32MB)
        [void]$fs.Seek($off, [System.IO.SeekOrigin]::Begin)
        $buf = New-Object byte[] $n
        $got = 0
        while ($got -lt $n) {
            $r = $fs.Read($buf, $got, $n - $got)
            if ($r -le 0) { break }
            $got += $r
        }
        $utf8 = $false
        if ($off -eq 0 -and $got -ge 2 -and -not ($buf[0] -eq 0xFF -and $buf[1] -eq 0xFE)) { $utf8 = $true }
        if ($State.ContainsKey('utf8:' + $Path)) { $utf8 = $true }
        if ($utf8) {
            $State['utf8:' + $Path] = $true
            $text = [System.Text.Encoding]::UTF8.GetString($buf, 0, $got)
            $State[$Path] = $off + $got
        } else {
            $even = $got - ($got % 2)
            $text = [System.Text.Encoding]::Unicode.GetString($buf, 0, $even)
            $State[$Path] = $off + $even
        }
        $text = $text.TrimStart([char]0xFEFF)
        return @($text -split "\r?\n" | Where-Object { $_.Length -gt 0 })
    } catch {
        return @()
    } finally {
        if ($fs) { $fs.Dispose() }
    }
}

function Get-NewLines {
    # Reads every log file in $Dirs that is new or has grown. Returns objects {Dir, File, Line}.
    param([string[]]$Dirs, [hashtable]$State)
    $out = New-Object System.Collections.Generic.List[object]
    foreach ($f in (Get-LogFilesIn $Dirs)) {
        $known = $State.ContainsKey($f.FullName)
        if ($known -and [int64]$State[$f.FullName] -ge ($f.Length - ($f.Length % 2))) { continue }
        foreach ($l in (Read-LogDelta -Path $f.FullName -State $State)) {
            [void]$out.Add([pscustomobject]@{ Dir = $f.DirectoryName; File = $f.FullName; Line = $l })
        }
    }
    return ,$out.ToArray()
}

function Format-LogLine {
    param([string]$Line)
    return ($Line -replace "`t", '  ')
}

# ----------------------------------------------------------------------------------------------
# config generation
# ----------------------------------------------------------------------------------------------
function New-SetText {
    param([System.Collections.IDictionary]$Values)
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append("; generated by tools\run_checks.ps1 on $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))`r`n")
    foreach ($k in $Values.Keys) { [void]$sb.Append("$k=$($Values[$k])`r`n") }
    return $sb.ToString()
}

function Get-CommonSection {
    $s = ''
    if (-not [string]::IsNullOrEmpty($Login)) {
        if ($Login -notmatch '^\d+$') { throw "-Login must be an account number (digits only); never put a password here." }
        $s = "[Common]`r`nLogin=$Login`r`n"
    }
    return $s
}

function New-ScriptIniText {
    # [StartUp] runs a script on a chart at start. [Experts] AllowLiveTrading=0 keeps every EA on restored charts from trading.
    param([string]$Script, [string]$ScriptParameters = '')
    $t = Get-CommonSection
    $t += "[Experts]`r`nAllowLiveTrading=0`r`nAllowDllImport=0`r`nEnabled=1`r`nAccount=0`r`nProfile=0`r`n"
    $t += "[StartUp]`r`nScript=$Script`r`n"
    if ($ScriptParameters) { $t += "ScriptParameters=$ScriptParameters`r`n" }
    $t += "Symbol=$ChartSymbol`r`nPeriod=$ChartPeriod`r`nShutdownTerminal=1`r`n"
    return $t
}

function New-TesterIniText {
    param($Case, [int]$ModelNo, [string]$From, [string]$To, [string]$SetName, [string]$ReportRel)
    $t = Get-CommonSection
    $t += "[Experts]`r`nAllowLiveTrading=0`r`nAllowDllImport=0`r`nEnabled=1`r`nAccount=0`r`nProfile=0`r`n"
    $t += "[Tester]`r`n"
    $t += "Expert=Renko\RenkoTickContinuationEA`r`n"
    $t += "ExpertParameters=$SetName`r`n"
    $t += "Symbol=$($Case.Symbol)`r`n"
    $t += "Period=$($Case.Tf)`r`n"
    $t += "Model=$ModelNo`r`n"
    $t += "ExecutionMode=0`r`n"
    $t += "Optimization=0`r`n"
    $t += "FromDate=$From`r`nToDate=$To`r`n"
    $t += "ForwardMode=0`r`n"
    $t += "Deposit=$($Case.Deposit)`r`n"
    $t += "Currency=$Currency`r`n"
    $t += "Leverage=$Leverage`r`n"
    $t += "Visual=0`r`n"
    $t += "UseLocal=1`r`nUseRemote=0`r`nUseCloud=0`r`n"
    $t += "Report=$ReportRel`r`nReplaceReport=1`r`nShutdownTerminal=1`r`n"
    return $t
}

# ----------------------------------------------------------------------------------------------
# prerequisites
# ----------------------------------------------------------------------------------------------
function Get-RenkoIncludes {
    # The Renko\*.mqh files that a source file includes, directly or through other includes.
    param([string]$Source, [string]$IncludeRoot, [hashtable]$Seen)
    $found = @()
    if (-not (Test-Path -LiteralPath $Source)) { return $found }
    $text = Get-Content -LiteralPath $Source -Raw
    foreach ($m in [regex]::Matches($text, '#include\s*<(Renko[\\/][^>]+)>')) {
        $rel = $m.Groups[1].Value -replace '/', '\'
        $full = Join-Path $IncludeRoot $rel
        if ($Seen.ContainsKey($full) -or -not (Test-Path -LiteralPath $full)) { continue }
        $Seen[$full] = $true
        $found += Get-Item -LiteralPath $full
        $found += Get-RenkoIncludes -Source $full -IncludeRoot $IncludeRoot -Seen $Seen
    }
    return $found
}

function Test-Prerequisites {
    param([string[]]$Modes)
    $ok = $true
    if (-not (Test-Path -LiteralPath $TerminalExe)) { Write-Log "terminal64.exe not found: $TerminalExe" 'ERROR'; $ok = $false }
    if (-not (Test-Path -LiteralPath (Join-Path $DataDir 'MQL5'))) { Write-Log "MQL5 folder not found in the data folder: $DataDir" 'ERROR'; $ok = $false }
    if (-not $ok) { return $false }

    $mql = Join-Path $DataDir 'MQL5'
    $need = @()
    if ($Modes -contains 'Tests')      { $need += ,@('Scripts\Renko\Tests\RenkoEngineTests', 'Scripts\Renko\Tests\RenkoEngineTests.mq5') }
    if ($Modes -contains 'Sweep')      { $need += ,@('Scripts\Renko\RenkoSweep', 'Scripts\Renko\RenkoSweep.mq5') }
    if ($Modes -contains 'Validation') { $need += ,@('Experts\Renko\RenkoTickContinuationEA', 'Experts\Renko\RenkoTickContinuationEA.mq5') }
    foreach ($n in $need) {
        $ex5 = Join-Path $mql ($n[0] + '.ex5')
        $src = Join-Path $mql $n[1]
        if (-not (Test-Path -LiteralPath $ex5)) {
            Write-Log "Compiled program missing: $ex5  (open $($n[1]) in MetaEditor and press F7)" 'ERROR'; $ok = $false; continue
        }
        $ex5Time = (Get-Item -LiteralPath $ex5).LastWriteTime
        if ((Test-Path -LiteralPath $src) -and (Get-Item -LiteralPath $src).LastWriteTime -gt $ex5Time) {
            Write-Log "WARNING: $($n[1]) is newer than its .ex5. Compile it in MetaEditor (F7) or you test an old build." 'WARN'
        }
        foreach ($i in (Get-RenkoIncludes -Source $src -IncludeRoot (Join-Path $mql 'Include') -Seen @{})) {
            if ($i.LastWriteTime -gt $ex5Time) { Write-Log "WARNING: include $($i.Name) is newer than $(Split-Path -Leaf $ex5). Recompile." 'WARN' }
        }
        # repository copy vs terminal copy
        $repoSrc = Join-Path $script:RepoDir ('mql5\' + $n[1])
        if ((Test-Path -LiteralPath $repoSrc) -and (Test-Path -LiteralPath $src)) {
            $h1 = (Get-FileHash -LiteralPath $repoSrc -Algorithm SHA256).Hash
            $h2 = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
            if ($h1 -ne $h2) { Write-Log "WARNING: $($n[1]) differs between the repository (mql5\) and the terminal data folder." 'WARN' }
        }
    }
    if ($Modes -contains 'Sweep') {
        $csv = Join-Path $CommonDir 'Files\XAUUSD_ticks.csv'
        if (-not (Test-Path -LiteralPath $csv)) { Write-Log "Tick CSV not found: $csv" 'ERROR'; $ok = $false }
    }
    return $ok
}

# ----------------------------------------------------------------------------------------------
# MODE: Tests / Sweep (script runner)
# ----------------------------------------------------------------------------------------------
function Invoke-ScriptRun {
    param(
        [string]$Name,
        [string]$IniPath,
        [string]$DoneRegex,
        [string]$FatalRegex,
        [string]$KeepRegex,
        [int]$TimeoutMin,
        [int]$HeartbeatSec = 60
    )
    $logDir = Join-Path $DataDir 'MQL5\Logs'
    $state = New-LogState @($logDir)
    $result = [pscustomobject]@{
        Name = $Name; Done = $false; DoneLine = ''; Fatal = ''; TimedOut = $false; ForcedKill = $false
        ExitedEarly = $false; Kept = (New-Object System.Collections.Generic.List[string]); ElapsedSec = 0
    }
    $start = Get-Date
    $p = Start-Terminal -IniPath $IniPath
    $lastBeat = Get-Date
    $deadline = $start.AddMinutes($TimeoutMin)
    $poll = if ($TimeoutMin -gt 20) { 3000 } else { 1000 }
    $sawNew = 0

    $consume = {
        param($lines)
        foreach ($o in $lines) {
            $l = $o.Line
            $show = $ShowAllLog.IsPresent -or ($l -match $KeepRegex)
            if ($show) { [void]$result.Kept.Add($l); Write-Log ('log: ' + (Format-LogLine $l)) }
            if (-not $result.Done -and $l -match $DoneRegex) { $result.Done = $true; $result.DoneLine = $l }
            if (-not $result.Fatal -and $FatalRegex -and $l -match $FatalRegex) { $result.Fatal = $l }
        }
    }

    while ($true) {
        $lines = Get-NewLines -Dirs @($logDir) -State $state
        $sawNew += $lines.Count
        & $consume $lines
        if ($result.Done -or $result.Fatal) { break }
        if ($p.HasExited) {
            Start-Sleep -Milliseconds 1500
            & $consume (Get-NewLines -Dirs @($logDir) -State $state)
            $result.ExitedEarly = -not $result.Done
            break
        }
        if ((Get-Date) -gt $deadline) { $result.TimedOut = $true; break }
        if (((Get-Date) - $lastBeat).TotalSeconds -ge $HeartbeatSec) {
            $lastBeat = Get-Date
            try {
                $p.Refresh()
                $cpu = [Math]::Round($p.TotalProcessorTime.TotalSeconds)
                $mem = [Math]::Round($p.WorkingSet64 / 1MB)
                $el = ((Get-Date) - $start)
                Write-Log ("still running: elapsed {0:hh\:mm\:ss}, terminal CPU {1} s, memory {2} MB, {3} new log lines so far (timeout in {4:0} min)" -f $el, $cpu, $mem, $sawNew, ($deadline - (Get-Date)).TotalMinutes)
            } catch { }
        }
        Start-Sleep -Milliseconds $poll
    }
    $result.ElapsedSec = [int]((Get-Date) - $start).TotalSeconds

    if ($result.Done -and -not $p.HasExited) {
        # ShutdownTerminal=1 should end it by itself; give it a few seconds, then close gracefully.
        $t0 = Get-Date
        while (-not $p.HasExited -and ((Get-Date) - $t0).TotalSeconds -lt 20) { Start-Sleep -Milliseconds 500 }
    }
    if (-not $p.HasExited) {
        $graceful = Stop-Terminal -Proc $p -GraceSec $CloseGraceSec
        if (-not $graceful) { $result.ForcedKill = $true }
    }
    Start-Sleep -Milliseconds 1500
    # the terminal flushes its log on exit: read once more
    & $consume (Get-NewLines -Dirs @($logDir) -State $state)
    $script:Proc = $null
    return $result
}

function Invoke-TestsMode {
    Write-Log '=== MODE Tests: RenkoEngineTests ==='
    $runDir = Join-Path $script:RunRoot 'tests'
    New-Dir $runDir
    $ini = Join-Path $runDir 'tests.ini'
    Write-AsciiFile $ini (New-ScriptIniText -Script 'Renko\Tests\RenkoEngineTests')
    Write-Log "Generated config: $ini"
    $r = Invoke-ScriptRun -Name 'RenkoEngineTests' -IniPath $ini -DoneRegex 'RenkoEngineTests:\s*\d+\s+passed' `
        -FatalRegex '' -KeepRegex 'RenkoEngineTests|FAIL \[' -TimeoutMin $TestsTimeoutMin -HeartbeatSec 30
    $fails = @($r.Kept | Where-Object { $_ -match 'FAIL \[' })
    $summary = $r.DoneLine
    Write-Raw ''
    $ok = $false
    if ($r.Done) {
        Write-Raw ('SUMMARY: ' + (Format-LogLine $summary))
        foreach ($f in $fails) { Write-Raw ('  ' + (Format-LogLine $f)) }
        if ($summary -match '(\d+)\s+passed,\s*(\d+)\s+failed') {
            $ok = ([int]$Matches[2] -eq 0 -and [int]$Matches[1] -gt 0 -and $fails.Count -eq 0)
        }
    } elseif ($r.TimedOut) {
        Write-Log "No 'RenkoEngineTests:' line within $TestsTimeoutMin min. Is the .ex5 compiled? Is the symbol $ChartSymbol available?" 'ERROR'
    } elseif ($r.ExitedEarly) {
        Write-Log "The terminal exited before the script printed its summary. Look at MQL5\Logs." 'ERROR'
    }
    if ($ok) { Write-Log 'Tests: PASS (0 failed)' 'PASS' } else { Write-Log 'Tests: FAIL' 'FAIL' }
    return [pscustomobject]@{ Mode = 'Tests'; Pass = $ok; Detail = $summary }
}

function Invoke-SweepMode {
    Write-Log '=== MODE Sweep: RenkoSweep on XAUUSD_ticks.csv ==='
    $runDir = Join-Path $script:RunRoot 'sweep'
    New-Dir $runDir
    $setName = 'RenkoVerify_sweep.set'
    $presets = Join-Path $DataDir 'MQL5\Presets'
    New-Dir $presets
    $setText = New-SetText $script:SweepSet
    Write-AsciiFile (Join-Path $presets $setName) $setText
    Write-AsciiFile (Join-Path $runDir $setName) $setText
    $ini = Join-Path $runDir 'sweep.ini'
    Write-AsciiFile $ini (New-ScriptIniText -Script 'Renko\RenkoSweep' -ScriptParameters $setName)
    Write-Log "Generated preset: MQL5\Presets\$setName and config: $ini"

    $outPrefix = $script:SweepSet['InpOutPrefix']
    $sumFile = Join-Path $CommonDir ("Files\{0}_summary.csv" -f $outPrefix)
    if (Test-Path -LiteralPath $sumFile) { Write-Log "Existing output will be overwritten: $sumFile" 'WARN' }
    $t0 = Get-Date

    Write-Log "The sweep reads about 27 GB and normally takes 30-90 minutes. Timeout: $SweepTimeoutMin min. Progress below comes from the terminal log and a heartbeat every minute."
    $r = Invoke-ScriptRun -Name 'RenkoSweep' -IniPath $ini -DoneRegex 'RenkoSweep: done\.' `
        -FatalRegex 'RenkoSweep: (cannot open|cannot write|no brick sizes)' -KeepRegex 'RenkoSweep' -TimeoutMin $SweepTimeoutMin -HeartbeatSec 60
    Write-Raw ''
    $ran = $false
    if ($r.Done) {
        Write-Raw ('SUMMARY: ' + (Format-LogLine $r.DoneLine))
        if ($r.DoneLine -match 'STOPPED EARLY') { Write-Log 'The script reports a partial result (STOPPED EARLY).' 'ERROR' } else { $ran = $true }
    } elseif ($r.Fatal) {
        Write-Log ('Sweep failed: ' + (Format-LogLine $r.Fatal)) 'ERROR'
    } elseif ($r.TimedOut) {
        Write-Log "No 'RenkoSweep: done.' within $SweepTimeoutMin min (raise -SweepTimeoutMin)." 'ERROR'
    } else {
        Write-Log 'The terminal exited before the sweep finished. Look at MQL5\Logs.' 'ERROR'
    }
    if ($ran -and -not (Test-Path -LiteralPath $sumFile)) { Write-Log "Output file missing: $sumFile" 'ERROR'; $ran = $false }
    if ($ran -and (Get-Item -LiteralPath $sumFile).LastWriteTime -lt $t0) { Write-Log "Output file was not updated by this run: $sumFile" 'ERROR'; $ran = $false }

    $cmpOk = $false
    $cmpText = ''
    if ($ran) {
        $pyExe = $null
        $pyPre = @()
        foreach ($cand in @(@('python'), @('py', '-3'))) {
            if (Get-Command $cand[0] -ErrorAction SilentlyContinue) {
                $ver = ''
                try { $ver = (& $cand[0] @($cand | Select-Object -Skip 1) --version 2>&1 | Out-String) } catch { $ver = '' }
                if ($ver -match '^\s*Python 3') { $pyExe = $cand[0]; $pyPre = @($cand | Select-Object -Skip 1); break }
            }
        }
        if (-not $pyExe) {
            Write-Log 'Python 3 was not found on PATH; run  python -I tools\compare_sweep.py  yourself.' 'ERROR'
        } else {
            $cmp = Join-Path $script:ToolsDir 'compare_sweep.py'
            Write-Log "Running the comparer: $pyExe $($pyPre -join ' ') -I $cmp"
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $out = & $pyExe @pyPre -I $cmp 2>&1 | ForEach-Object { "$_" }
                $code = $LASTEXITCODE
            } finally { $ErrorActionPreference = $prevEap }
            foreach ($l in $out) { Write-Raw $l }
            $cmpOk = ($code -eq 0)
            $cmpText = "comparer exit code $code"
        }
    }
    $ok = ($ran -and $cmpOk)
    if ($ok) { Write-Log 'Sweep: PASS (MQL5 output matches the Python reference; see results\verification\sweep_compare.md)' 'PASS' }
    else { Write-Log "Sweep: FAIL $cmpText" 'FAIL' }
    return [pscustomobject]@{ Mode = 'Sweep'; Pass = $ok; Detail = $cmpText }
}

# ----------------------------------------------------------------------------------------------
# MODE: Validation (Strategy Tester)
# ----------------------------------------------------------------------------------------------
function Get-SymbolFor {
    param([string]$Key)
    $defaults = @{ Forex = 'EURUSD'; Jpy = 'USDJPY'; Gold = 'XAUUSD'; Index = 'US500'; Crypto = 'BTCUSD'; Any = 'EURUSD' }
    if ($Symbols.ContainsKey($Key)) { return [string]$Symbols[$Key] }
    return ($defaults[$Key] + $SymbolSuffix)
}

function Get-CaseDefs {
    # Mirrors the "self-test checklist" table in ep04.md. Window: std | short | monday.
    $defs = @(
        @{ Id = '1';  Row = 1;  Sym = 'Forex';  Tf = 'M1';  Dep = 10000; Win = 'std';    Inputs = @{};                                        Min = $MinTradesDefault; Expect = 'brick size .*\(daily ATR fraction\)'; Check = 'journal shows brick size (daily ATR fraction); SL distance about 2 bricks (read the journal)' }
        @{ Id = '2';  Row = 2;  Sym = 'Forex';  Tf = 'H4';  Dep = 10000; Win = 'std';    Inputs = @{};                                        Min = $MinTradesDefault; Expect = 'brick size .*\(daily ATR fraction\)'; Check = 'same trade count as case 1 (compared automatically)' }
        @{ Id = '3';  Row = 3;  Sym = 'Jpy';    Tf = 'M15'; Dep = 10000; Win = 'std';    Inputs = @{};                                        Min = $MinTradesDefault; Expect = '';                                    Check = '3-digit symbol: brick on tick size, stops valid (no [10016])' }
        @{ Id = '4';  Row = 4;  Sym = 'Gold';   Tf = 'H1';  Dep = 10000; Win = 'std';    Inputs = @{};                                        Min = $MinTradesDefault; Expect = '';                                    Check = 'lot 0.01 valid, trades occur' }
        @{ Id = '5';  Row = 5;  Sym = 'Index';  Tf = 'M5';  Dep = 10000; Win = 'std';    Inputs = @{};                                        Min = $MinTradesDefault; Expect = '';                                    Check = 'different tick size and lot step; stops level' }
        @{ Id = '6';  Row = 6;  Sym = 'Crypto'; Tf = 'D1';  Dep = 10000; Win = 'std';    Inputs = @{};                                        Min = $MinTradesDefault; Expect = '';                                    Check = 'very large price; lot step' }
        @{ Id = '7a'; Row = 7;  Sym = 'Forex';  Tf = 'M1';  Dep = 1;     Win = 'std';    Inputs = @{};                                        Min = 0;                 Expect = '';                                    Check = 'at 1 USD no trades is correct; look for MarketSafe: not enough money, no [10019]' }
        @{ Id = '7b'; Row = 7;  Sym = 'Forex';  Tf = 'M1';  Dep = 10;    Win = 'std';    Inputs = @{};                                        Min = 0;                 Expect = '';                                    Check = 'MarketSafe: not enough money messages instead of error 10019' }
        @{ Id = '7c'; Row = 7;  Sym = 'Forex';  Tf = 'M1';  Dep = 100;   Win = 'std';    Inputs = @{};                                        Min = 0;                 Expect = '';                                    Check = 'no error 10019' }
        @{ Id = '8a'; Row = 8;  Sym = 'Any';    Tf = 'H1';  Dep = 100;   Win = 'std';    Inputs = @{ InpLotMode = '1'; InpRiskPercent = '1.0' }; Min = 1;             Expect = '';                                    Check = 'no [10014]; lots on volume step; minimum lot used at 100' }
        @{ Id = '8b'; Row = 8;  Sym = 'Any';    Tf = 'H1';  Dep = 10000; Win = 'std';    Inputs = @{ InpLotMode = '1'; InpRiskPercent = '1.0' }; Min = $MinTradesDefault; Expect = '';                        Check = 'no [10014]; lots on volume step' }
        @{ Id = '9';  Row = 9;  Sym = 'Any';    Tf = 'H1';  Dep = 10000; Win = 'std';    Inputs = @{ InpBrickMode = '1' };                    Min = $MinTradesDefault; Expect = 'brick size .*\(fixed points\)';       Check = 'starts at once with fixed points' }
        @{ Id = '10'; Row = 10; Sym = 'Any';    Tf = 'H1';  Dep = 10000; Win = 'short';  Inputs = @{};                                        Min = 0;                 Expect = 'brick size .*\((daily ATR fraction|fixed points)\)|daily ATR not available'; Check = 'ATR becomes ready, or after 60 min the fixed-size fallback line appears; never idle for ever' }
        @{ Id = '11'; Row = 11; Sym = 'Any';    Tf = 'M5';  Dep = 10000; Win = 'std';    Inputs = @{ InpTPBricks = '1.0'; InpSameBricks = '1' }; Min = $MinTradesDefault; Expect = '';                         Check = 'TP orders accepted (no [10016]); many reversals; one position at a time (check the report)' }
        @{ Id = '12'; Row = 12; Sym = 'Any';    Tf = 'M5';  Dep = 10000; Win = 'std';    Inputs = @{ InpCloseOnOpposite = 'false' };          Min = $MinTradesDefault; Expect = '';                                    Check = 'opposite signals ignored while a trade is open (check the report)' }
        @{ Id = '13'; Row = 13; Sym = 'Any';    Tf = 'M5';  Dep = 10000; Win = 'std';    Inputs = @{ InpMaxSpreadPoints = '1' };              Min = 0;                 Expect = 'skipped, spread .* is above the limit'; Check = 'trades skipped with a spread message, no errors' }
        @{ Id = '14'; Row = 14; Sym = 'Any';    Tf = 'H1';  Dep = 10000; Win = 'std';    Inputs = @{};                                        Min = $MinTradesDefault; Expect = 'started on .*(hedging|netting or exchange) account'; Check = 'never two positions on the symbol; reversal is close then open. Run once per account type (netting and hedging)' }
        @{ Id = '15'; Row = 15; Sym = 'Any';    Tf = 'H1';  Dep = 10000; Win = 'monday'; Inputs = @{};                                        Min = 1;                 Expect = '';                                    Check = 'a gap tick produces one trade, not several (look at the first trades in the report)' }
    )
    $list = @()
    foreach ($d in $defs) {
        $list += [pscustomobject]@{
            Id = $d.Id; Row = $d.Row; Symbol = (Get-SymbolFor $d.Sym); Tf = $d.Tf; Deposit = $d.Dep; Window = $d.Win
            Inputs = $d.Inputs; MinTrades = $d.Min; Expect = $d.Expect; Check = $d.Check
        }
    }
    if ($Cases.Count -gt 0) {
        $want = @($Cases | ForEach-Object { "$_".ToLower() })
        $list = @($list | Where-Object { $want -contains $_.Id.ToLower() })
    }
    return $list
}

function Get-CaseWindow {
    param([string]$Window)
    if ([string]::IsNullOrEmpty($ToDate)) { $to = (Get-Date).Date.AddDays(-1) } else { $to = [datetime]::ParseExact($ToDate, 'yyyy.MM.dd', [System.Globalization.CultureInfo]::InvariantCulture) }
    switch ($Window) {
        'short'  { $from = $to.AddDays(-3) }
        'monday' {
            $m = $to.AddDays(-4)
            while ($m.DayOfWeek -ne [System.DayOfWeek]::Monday) { $m = $m.AddDays(-1) }
            $from = $m; $to = $m.AddDays(4)
        }
        default  { $from = $to.AddDays(-$HistoryDays) }
    }
    return @{ From = $from.ToString('yyyy.MM.dd'); To = $to.ToString('yyyy.MM.dd') }
}

function Read-ReportText {
    param([string]$Path)
    $b = [System.IO.File]::ReadAllBytes($Path)
    if ($b.Length -ge 2 -and $b[0] -eq 0xFF -and $b[1] -eq 0xFE) { return [System.Text.Encoding]::Unicode.GetString($b, 2, $b.Length - 2) }
    if ($b.Length -ge 2 -and $b[0] -eq 0xFE -and $b[1] -eq 0xFF) { return [System.Text.Encoding]::BigEndianUnicode.GetString($b, 2, $b.Length - 2) }
    return [System.Text.Encoding]::UTF8.GetString($b)
}

function Get-ReportValue {
    # Value cell after a "Label:" cell in the HTML (<td>Label:</td><td><b>value</b></td>) or XML (Cell/Data) report.
    param([string]$Text, [string]$Label)
    $esc = [regex]::Escape($Label)
    $m = [regex]::Match($Text, $esc + ':?\s*</t[dh]>\s*<t[dh][^>]*>\s*(?:<b>)?\s*([^<]*)', 'IgnoreCase')
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    $m = [regex]::Match($Text, $esc + ':?\s*</Data>\s*</Cell>\s*<Cell[^>]*>\s*<Data[^>]*>([^<]*)', 'IgnoreCase')
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return $null
}

function Read-TesterReport {
    # Only the trade count (and a few descriptive fields). Performance numbers are deliberately not read.
    param([string]$Path)
    $res = [pscustomobject]@{ Trades = $null; Deals = $null; Quality = ''; Symbol = ''; Period = '' }
    $t = Read-ReportText $Path
    $v = Get-ReportValue $t 'Total Trades'
    if ($null -ne $v) { $digits = ($v -replace '[^\d]', ''); if ($digits.Length -gt 0) { $res.Trades = [int]$digits } }
    $v = Get-ReportValue $t 'Total Deals'
    if ($null -ne $v) { $digits = ($v -replace '[^\d]', ''); if ($digits.Length -gt 0) { $res.Deals = [int]$digits } }
    $q = Get-ReportValue $t 'History Quality'
    if ($q) { $res.Quality = $q }
    $s = Get-ReportValue $t 'Symbol'
    if ($s) { $res.Symbol = $s }
    $p = Get-ReportValue $t 'Period'
    if ($p) { $res.Period = $p }
    return $res
}

function Get-TesterLogDirs {
    # Group 'tester' = <data>\Tester\logs (the terminal-side tester log, also carries the "Core 01" lines);
    # group 'agent'  = Agent-*\logs of the local test agents, which carry the EA's own Print() lines.
    $dirs = @()
    $dirs += [pscustomobject]@{ Dir = (Join-Path $DataDir 'Tester\logs'); Group = 'tester' }
    foreach ($root in @((Join-Path $DataDir 'Tester'), (Join-Path $env:APPDATA ('MetaQuotes\Tester\' + (Split-Path -Leaf $DataDir))))) {
        if (Test-Path -LiteralPath $root) {
            foreach ($a in (Get-ChildItem -LiteralPath $root -Directory -Filter 'Agent-*' -ErrorAction SilentlyContinue)) {
                $dirs += [pscustomobject]@{ Dir = (Join-Path $a.FullName 'logs'); Group = 'agent' }
            }
        }
    }
    return $dirs
}

function New-GroupAcc {
    return [pscustomobject]@{
        Errors = 0; Samples = (New-Object System.Collections.Generic.List[string])
        Ea = (New-Object System.Collections.Generic.List[string]); EaCount = 0; Expect = $false
        Hits10019 = 0; NotEnoughMoney = 0; Summary = ''; Lines = 0
        Reason = (New-Object System.Collections.Generic.List[string])
    }
}

function Add-ScannedLine {
    # Classify one tester/agent log line into an accumulator.
    param($Acc, [string]$Line, [string]$ExpectRegex)
    $Acc.Lines++
    if ($Line -match 'RenkoTick|MarketSafe') {
        $Acc.EaCount++
        if ($Acc.Ea.Count -lt 400) { [void]$Acc.Ea.Add($Line) }
        if ($Line -match 'not enough money') { $Acc.NotEnoughMoney++ }
    }
    if ($ExpectRegex -and -not $Acc.Expect -and $Line -match $ExpectRegex) { $Acc.Expect = $true }
    if ($Line -match $script:TesterErrRegex) {
        if (-not ($IgnoreRegex -and $Line -match $IgnoreRegex)) {
            $Acc.Errors++
            if ($Acc.Samples.Count -lt 8) { [void]$Acc.Samples.Add($Line) }
        }
    }
    if ($Line -match 'Test passed in|ticks, \d+ bars generated') { $Acc.Summary = $Line }
    if ($Line -match 'no history|not found|unknown symbol|invalid symbol|symbol .* (does not|doesn.t) exist|cannot|synchroniz') {
        if ($Acc.Reason.Count -lt 6) { [void]$Acc.Reason.Add($Line) }
    }
}

function Invoke-TesterCase {
    param($Case, [int]$ModelNo, [string]$RunDir)
    $win = Get-CaseWindow $Case.Window
    $safeSym = ($Case.Symbol -replace '[^A-Za-z0-9]', '_')
    $name = "case{0}_{1}_{2}_d{3}_m{4}" -f $Case.Id, $safeSym, $Case.Tf, $Case.Deposit, $ModelNo
    $reportRelDir = 'RenkoVerify'
    New-Dir (Join-Path $DataDir $reportRelDir)
    $reportRel = "$reportRelDir\ep04_$name.htm"
    $reportAbs = Join-Path $DataDir $reportRel
    foreach ($old in @($reportAbs, ($reportAbs -replace '\.htm$', '.xml'))) {
        if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Force }
    }
    # the .set: all EA inputs explicit (defaults) with this case's overrides
    $vals = [ordered]@{}
    foreach ($k in $script:EaDefaults.Keys) { $vals[$k] = $script:EaDefaults[$k] }
    foreach ($k in $Case.Inputs.Keys) { $vals[$k] = $Case.Inputs[$k] }
    $setName = "RenkoVerify_case$($Case.Id).set"
    $setDir = Join-Path $DataDir 'MQL5\Profiles\Tester'
    New-Dir $setDir
    $setText = New-SetText $vals
    Write-AsciiFile (Join-Path $setDir $setName) $setText
    Write-AsciiFile (Join-Path $RunDir $setName) $setText
    $ini = Join-Path $RunDir "$name.ini"
    Write-AsciiFile $ini (New-TesterIniText -Case $Case -ModelNo $ModelNo -From $win.From -To $win.To -SetName $setName -ReportRel $reportRel)

    Write-Log ("--- case {0}: {1} {2}, deposit {3}, model {4}, {5} to {6}" -f $Case.Id, $Case.Symbol, $Case.Tf, $Case.Deposit, $ModelNo, $win.From, $win.To)
    if ($Case.Inputs.Count -gt 0) { Write-Log ('inputs changed: ' + (($Case.Inputs.Keys | ForEach-Object { "$_=$($Case.Inputs[$_])" }) -join ', ')) }

    # snapshot every tester log before the launch
    $dirList = Get-TesterLogDirs
    $dirs = @($dirList | ForEach-Object { $_.Dir })
    $state = New-LogState $dirs
    $acc = @{ tester = (New-GroupAcc); agent = (New-GroupAcc) }

    $scan = {
        param($lines)
        foreach ($o in $lines) {
            $g = 'agent'
            foreach ($d in $dirList) { if ([string]::Equals($d.Dir, $o.Dir, 'OrdinalIgnoreCase')) { $g = $d.Group; break } }
            Add-ScannedLine -Acc $acc[$g] -Line $o.Line -ExpectRegex $Case.Expect
        }
    }

    $start = Get-Date
    $p = Start-Terminal -IniPath $ini
    $deadline = $start.AddMinutes($CaseTimeoutMin)
    $lastBeat = Get-Date
    $timedOut = $false
    $forced = $false
    while (-not $p.HasExited) {
        Start-Sleep -Milliseconds 2000
        $dirList = Get-TesterLogDirs
        $dirs = @($dirList | ForEach-Object { $_.Dir })
        & $scan (Get-NewLines -Dirs $dirs -State $state)
        if ((Get-Date) -gt $deadline) { $timedOut = $true; break }
        if (((Get-Date) - $lastBeat).TotalSeconds -ge 30) {
            $lastBeat = Get-Date
            Write-Log ("  running: {0:hh\:mm\:ss} elapsed, {1} + {2} log lines, EA lines {3}, error lines {4}" -f ((Get-Date) - $start), $acc.tester.Lines, $acc.agent.Lines, [Math]::Max($acc.tester.EaCount, $acc.agent.EaCount), [Math]::Max($acc.tester.Errors, $acc.agent.Errors))
        }
    }
    if (-not $p.HasExited) {
        Write-Log "Case $($Case.Id) exceeded $CaseTimeoutMin min; closing the terminal." 'WARN'
        if (-not (Stop-Terminal -Proc $p -GraceSec $CloseGraceSec)) { $forced = $true }
    }
    $script:Proc = $null
    Start-Sleep -Milliseconds 2500
    $dirList = Get-TesterLogDirs
    $dirs = @($dirList | ForEach-Object { $_.Dir })
    & $scan (Get-NewLines -Dirs $dirs -State $state)

    # the group with more error lines wins (the two groups mirror each other)
    $best = $acc.agent
    if ($acc.tester.Errors -gt $acc.agent.Errors) { $best = $acc.tester }
    $eaGroup = $acc.agent
    if ($acc.tester.EaCount -gt $acc.agent.EaCount) { $eaGroup = $acc.tester }
    $expectOk = ($acc.tester.Expect -or $acc.agent.Expect)
    $summaryLine = $acc.tester.Summary
    if (-not $summaryLine) { $summaryLine = $acc.agent.Summary }

    # report
    $found = $null
    foreach ($cand in @($reportAbs, ($reportAbs -replace '\.htm$', '.xml'))) { if (Test-Path -LiteralPath $cand) { $found = $cand; break } }
    $trades = $null
    $repCopy = ''
    $quality = ''
    if ($found) {
        $dest = Join-Path $script:TesterOut (Split-Path -Leaf $found)
        Copy-Item -LiteralPath $found -Destination $dest -Force
        $repCopy = $dest
        try {
            $rep = Read-TesterReport $dest
            $trades = $rep.Trades
            $quality = $rep.Quality
        } catch { Write-Log "Could not parse the report: $($_.Exception.Message)" 'WARN' }
    }
    $reason = ''
    if (-not $found) {
        $r = @($acc.tester.Reason) + @($acc.agent.Reason)
        if ($r.Count -gt 0) { $reason = (Format-LogLine $r[0]) }
    }
    $nem = [Math]::Max($acc.tester.NotEnoughMoney, $acc.agent.NotEnoughMoney)

    return [pscustomobject]@{
        Case = $Case; Name = $name; Model = $ModelNo; From = $win.From; To = $win.To
        ReportFound = [bool]$found; Report = $repCopy; Trades = $trades; Quality = $quality
        Errors = $best.Errors; ErrorSamples = @($best.Samples); EaLines = @($eaGroup.Ea); ExpectOk = $expectOk
        NotEnoughMoney = $nem; Summary = $summaryLine; TimedOut = $timedOut; Forced = $forced; Reason = $reason
        ElapsedSec = [int]((Get-Date) - $start).TotalSeconds
    }
}

function Get-CaseVerdict {
    # Checklist rule: no error lines, expected journal line present (where the table names one), at least the
    # minimum trade count. SKIP when the tester produced no report (symbol/history not available).
    param($R)
    $c = $R.Case
    $notes = New-Object System.Collections.Generic.List[string]
    if (-not $R.ReportFound) {
        if ($R.TimedOut) { return @{ Status = 'FAIL'; Notes = "timed out after $CaseTimeoutMin min, no report" } }
        $n = 'no report produced (symbol or history not available on this server?)'
        if ($R.ElapsedSec -lt 20) { $n = "terminal exited after $($R.ElapsedSec) s without a report (bad config or startup dialog?)" }
        if ($R.Reason) { $n += ': ' + $R.Reason }
        return @{ Status = 'SKIP'; Notes = $n }
    }
    $ok = $true
    if ($R.Errors -gt 0) { $ok = $false; [void]$notes.Add("$($R.Errors) error line(s)") }
    if ($null -eq $R.Trades) { $ok = $false; [void]$notes.Add('trade count not found in report') }
    elseif ($R.Trades -lt $c.MinTrades) { $ok = $false; [void]$notes.Add("trades $($R.Trades) < required $($c.MinTrades)") }
    if ($c.Expect -and -not $R.ExpectOk) { $ok = $false; [void]$notes.Add("expected journal line not seen: /$($c.Expect)/") }
    if ($R.TimedOut) { $ok = $false; [void]$notes.Add('timed out') }
    if ($R.Forced) { [void]$notes.Add('terminal had to be killed') }
    if (($c.Id -like '7*') -and $R.NotEnoughMoney -gt 0) { [void]$notes.Add("$($R.NotEnoughMoney) 'not enough money' message(s)") }
    if ($c.Id -eq '14' -and $R.EaLines) {
        $m = @($R.EaLines | Where-Object { $_ -match 'started on .* account' })
        if ($m.Count -gt 0 -and $m[0] -match '(hedging|netting or exchange) account') { [void]$notes.Add("account type: $($Matches[1])") }
    }
    if ($R.Quality) { [void]$notes.Add("history quality $($R.Quality)") }
    [void]$notes.Add("model $($R.Model)")
    [void]$notes.Add("manual: $($c.Check)")
    $status = 'FAIL'
    if ($ok) { $status = 'PASS' }
    return @{ Status = $status; Notes = ($notes -join '; ') }
}

function Write-TesterSummary {
    param($Rows, [string]$Path)
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine('# RenkoTickContinuationEA - Strategy Tester self-test')
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine("Generated $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) by tools\run_checks.ps1 (-Mode Validation). Cases mirror the self-test checklist in docs\series\renko-ticks\drafts\ep04.md.")
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('Rule: PASS = a tester report was produced, no error lines in the tester/agent logs (patterns: failed, error, [100, array out of range, zero divide, initialization failed), the journal line named by the checklist was seen (where one is named) and the trade count reached the minimum for the case. SKIP = no report (symbol or history unavailable). Trade counts are the only report figure used; no performance figure is summarised.')
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('| Case | Row | Symbol | TF | Deposit | Window | Trades | Errors found | Result | Notes |')
    [void]$sb.AppendLine('|---|---|---|---|---:|---|---:|---:|---|---|')
    foreach ($r in $Rows) {
        $tr = '-'; if ($null -ne $r.Trades) { $tr = [string]$r.Trades }
        $er = '-'; if ($r.ReportFound -or $r.Errors -gt 0) { $er = [string]$r.Errors }
        $note = ($r.Verdict.Notes -replace '\|', '/')
        [void]$sb.AppendLine(('| {0} | {1} | {2} | {3} | {4} | {5} to {6} | {7} | {8} | **{9}** | {10} |' -f $r.Case.Id, $r.Case.Row, $r.Case.Symbol, $r.Case.Tf, $r.Case.Deposit, $r.From, $r.To, $tr, $er, $r.Verdict.Status, $note))
    }
    $pass = @($Rows | Where-Object { $_.Verdict.Status -eq 'PASS' }).Count
    $fail = @($Rows | Where-Object { $_.Verdict.Status -eq 'FAIL' }).Count
    $skip = @($Rows | Where-Object { $_.Verdict.Status -eq 'SKIP' }).Count
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine("Totals: $pass PASS, $fail FAIL, $skip SKIP of $($Rows.Count) runs.")
    $withErr = @($Rows | Where-Object { $_.Errors -gt 0 })
    if ($withErr.Count -gt 0) {
        [void]$sb.AppendLine('')
        [void]$sb.AppendLine('## Error lines (first few per case)')
        foreach ($r in $withErr) {
            [void]$sb.AppendLine('')
            [void]$sb.AppendLine("### Case $($r.Case.Id) - $($r.Case.Symbol) $($r.Case.Tf) ($($r.Errors) lines)")
            [void]$sb.AppendLine('')
            foreach ($l in $r.ErrorSamples) { [void]$sb.AppendLine('    ' + (Format-LogLine $l)) }
        }
    }
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('## First EA journal lines per case')
    foreach ($r in $Rows) {
        [void]$sb.AppendLine('')
        [void]$sb.AppendLine("### Case $($r.Case.Id) - $($r.Case.Symbol) $($r.Case.Tf) - report: $(if ($r.Report) { Split-Path -Leaf $r.Report } else { 'none' })")
        [void]$sb.AppendLine('')
        $shown = 0
        foreach ($l in $r.EaLines) { if ($shown -ge 6) { break }; [void]$sb.AppendLine('    ' + (Format-LogLine $l)); $shown++ }
        if ($shown -eq 0) { [void]$sb.AppendLine('    (no EA lines captured)') }
        if ($r.Summary) { [void]$sb.AppendLine('    ' + (Format-LogLine $r.Summary)) }
    }
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('## Checks that stay manual')
    [void]$sb.AppendLine('')
    foreach ($r in ($Rows | Sort-Object { $_.Case.Id })) { [void]$sb.AppendLine("- Case $($r.Case.Id): $($r.Case.Check)") }
    [void]$sb.AppendLine('- Case 14 needs one run on a netting and one on a hedging account; this run used whichever account type the terminal is logged in to.')
    [System.IO.File]::WriteAllText($Path, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
}

function Invoke-ValidationMode {
    Write-Log '=== MODE Validation: Strategy Tester, RenkoTickContinuationEA ==='
    $runDir = Join-Path $script:RunRoot 'validation'
    New-Dir $runDir
    $script:TesterOut = Join-Path $script:RepoDir 'results\ep04\tester'
    New-Dir $script:TesterOut
    $summaryPath = Join-Path $script:TesterOut 'summary.md'

    $defs = @(Get-CaseDefs)
    if ($defs.Count -eq 0) { Write-Log 'No case matches -Cases.' 'ERROR'; return [pscustomobject]@{ Mode = 'Validation'; Pass = $false; Detail = 'no cases' } }
    Write-Log ("{0} run(s): {1}" -f $defs.Count, (($defs | ForEach-Object { $_.Id }) -join ', '))
    $rows = New-Object System.Collections.Generic.List[object]
    foreach ($c in $defs) {
        $r = Invoke-TesterCase -Case $c -ModelNo $Model -RunDir $runDir
        if (-not $r.ReportFound -and -not $r.TimedOut -and $Model -eq 4 -and -not $NoFallback) {
            Write-Log "No report with model 4 (real ticks). Retrying case $($c.Id) once with model 0 (every tick, generated)." 'WARN'
            Start-Sleep -Seconds 3
            $r = Invoke-TesterCase -Case $c -ModelNo 0 -RunDir $runDir
        }
        $r | Add-Member -NotePropertyName Verdict -NotePropertyValue (Get-CaseVerdict $r)

        # case 2 must have the same trade count as case 1 (timeframe must not matter)
        if ($c.Id -eq '2') {
            $one = @($rows | Where-Object { $_.Case.Id -eq '1' -and $_.ReportFound })
            if ($one.Count -gt 0 -and $r.ReportFound -and $null -ne $one[0].Trades -and $null -ne $r.Trades) {
                if ($one[0].Model -ne $r.Model) {
                    $r.Verdict.Notes += "; trade count vs case 1 not compared (different model)"
                } elseif ($one[0].Trades -ne $r.Trades) {
                    $r.Verdict.Status = 'FAIL'
                    $r.Verdict.Notes += "; trades $($r.Trades) differ from case 1 ($($one[0].Trades))"
                } else {
                    $r.Verdict.Notes += "; trades equal to case 1 ($($r.Trades))"
                }
            }
        }
        [void]$rows.Add($r)
        $tr = '-'; if ($null -ne $r.Trades) { $tr = $r.Trades }
        Write-Log ("case {0}: {1} (trades {2}, errors {3}) {4}" -f $c.Id, $r.Verdict.Status, $tr, $r.Errors, $r.Verdict.Notes) $(if ($r.Verdict.Status -eq 'PASS') { 'PASS' } elseif ($r.Verdict.Status -eq 'FAIL') { 'FAIL' } else { 'WARN' })
        Write-TesterSummary -Rows $rows -Path $summaryPath
        Start-Sleep -Seconds 2
    }
    Write-Raw ''
    Write-Raw '| Case | Symbol | TF | Deposit | Trades | Errors | Result |'
    foreach ($r in $rows) {
        $tr = '-'; if ($null -ne $r.Trades) { $tr = $r.Trades }
        Write-Raw ('| {0} | {1} | {2} | {3} | {4} | {5} | {6} |' -f $r.Case.Id, $r.Case.Symbol, $r.Case.Tf, $r.Case.Deposit, $tr, $r.Errors, $r.Verdict.Status)
    }
    Write-Log "Summary written: $summaryPath"
    $anyFail = @($rows | Where-Object { $_.Verdict.Status -eq 'FAIL' }).Count
    $anyPass = @($rows | Where-Object { $_.Verdict.Status -eq 'PASS' }).Count
    $okAll = ($anyFail -eq 0 -and $anyPass -gt 0)
    if ($okAll) { Write-Log 'Validation: no FAIL (see SKIP rows if any).' 'PASS' } else { Write-Log "Validation: $anyFail FAIL, $anyPass PASS." 'FAIL' }
    return [pscustomobject]@{ Mode = 'Validation'; Pass = $okAll; Detail = "$anyPass pass, $anyFail fail" }
}

# ----------------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------------
function Invoke-Main {
    $modes = switch ($Mode) { 'All' { @('Tests', 'Sweep', 'Validation') } default { @($Mode) } }

    $verDir = Join-Path $script:RepoDir 'results\verification'
    New-Dir $verDir
    $script:TranscriptPath = Join-Path $verDir ("run_checks_{0}_{1}.log" -f $Mode, $script:Stamp)
    $script:RunRoot = Join-Path $verDir ("run_{0}_{1}" -f $Mode, $script:Stamp)
    New-Dir $script:RunRoot
    Write-Log "run_checks.ps1 -Mode $Mode   transcript: $script:TranscriptPath"
    Write-Log "terminal: $TerminalExe"
    Write-Log "data folder: $DataDir"

    if (-not (Test-Prerequisites $modes)) { Write-Log 'Prerequisites failed; nothing was started.' 'ERROR'; exit 2 }

    $running = @(Get-RunningTerminals)
    if ($running.Count -gt 0) {
        Write-Log 'MetaTrader 5 (terminal64.exe from the configured path) is running. Close it completely (File > Exit, check the tray) and start this script again. Nothing was launched.' 'ERROR'
        foreach ($p in $running) { Write-Log ("  running process id {0}" -f $p.ProcessId) 'ERROR' }
        exit 2
    }

    Write-Host ''
    Write-Host '*****************************************************************************' -ForegroundColor Yellow
    Write-Host ' SAFETY' -ForegroundColor Yellow
    Write-Host '  * This will START MetaTrader 5 and use whichever account it last logged in to.' -ForegroundColor Yellow
    Write-Host '  * That account MUST be a DEMO account.' -ForegroundColor Yellow
    Write-Host '  * Scripts and the Strategy Tester only. AllowLiveTrading=0 is set for every launch,' -ForegroundColor Yellow
    Write-Host '    so no Expert Advisor on a restored chart can trade.' -ForegroundColor Yellow
    Write-Host "  * Modes to run: $($modes -join ', ')" -ForegroundColor Yellow
    if ($modes -contains 'Sweep') { Write-Host '  * The sweep can take 30-90 minutes and reads a 27 GB file.' -ForegroundColor Yellow }
    if ($modes -contains 'Validation') { Write-Host '  * Validation runs up to 18 Strategy Tester runs one after the other (can take hours).' -ForegroundColor Yellow }
    Write-Host '*****************************************************************************' -ForegroundColor Yellow
    if (-not $AssumeYes) {
        $a = Read-Host 'Type YES (capitals) to confirm the account is a demo account and continue'
        if ($a -cne 'YES') { Write-Log 'Not confirmed. Nothing was launched.' 'WARN'; exit 2 }
    } else {
        Write-Log '-AssumeYes given: prompt skipped.' 'WARN'
    }
    Write-Log 'Confirmed by the user.'

    $results = New-Object System.Collections.Generic.List[object]
    try {
        foreach ($m in $modes) {
            switch ($m) {
                'Tests'      { [void]$results.Add((Invoke-TestsMode)) }
                'Sweep'      { [void]$results.Add((Invoke-SweepMode)) }
                'Validation' { [void]$results.Add((Invoke-ValidationMode)) }
            }
            Start-Sleep -Seconds 3
        }
    } finally {
        if ($script:Proc) {
            Write-Log 'Interrupted: closing the terminal started by this script.' 'WARN'
            [void](Stop-Terminal -Proc $script:Proc -GraceSec $CloseGraceSec)
        }
    }

    Write-Raw ''
    Write-Log '=== RESULT ==='
    $allOk = $true
    foreach ($r in $results) {
        $lvl = 'PASS'; $txt = 'PASS'
        if (-not $r.Pass) { $lvl = 'FAIL'; $txt = 'FAIL'; $allOk = $false }
        Write-Log ("{0,-11} {1}  {2}" -f $r.Mode, $txt, $r.Detail) $lvl
    }
    Write-Log "Transcript: $script:TranscriptPath"
    if ($allOk) { exit 0 } else { exit 1 }
}

# Dot-sourcing (". .\run_checks.ps1 -Mode Tests") only loads the functions; running it starts the checks.
if ($MyInvocation.InvocationName -ne '.') { Invoke-Main }
