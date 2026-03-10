# FHAgents Bot — launcher/killer
# Usage: .\bot.ps1 start | stop | restart | status

param(
    [Parameter(Position=0)]
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "status"
)

$BotDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir = Split-Path -Parent $BotDir
$PidFile = Join-Path $BotDir "bot.pid"
$LogFile = Join-Path $BotDir "bot.log"
$ErrLogFile = Join-Path $BotDir "bot_err.log"

# Load .env from repo root
$EnvFile = Join-Path $RepoDir ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), "Process")
        }
    }
}

# Map env vars to what bot.py expects
$env:BOT_TOKEN = $env:TG_BOT_TOKEN
$env:CHAT_ID = $env:TG_CHAT_ID
$env:REPO_PATH = $RepoDir
$WebhookPort = if ($env:WEBHOOK_PORT) { [int]$env:WEBHOOK_PORT } else { 8090 }

# Unset CLAUDECODE to avoid nested session detection
[Environment]::SetEnvironmentVariable("CLAUDECODE", $null, "Process")

function Read-BotPid {
    if (-not (Test-Path $PidFile)) {
        return $null
    }

    $rawPid = Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $rawPid) {
        return $null
    }

    $trimmedPid = $rawPid.ToString().Trim()
    if ($trimmedPid -match '^\d+$') {
        return [int]$trimmedPid
    }

    return $null
}

function Get-ProcessFromId([int]$ProcessId) {
    if (-not $ProcessId) {
        return $null
    }

    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($proc -and $proc.Name -match '^(python|py|pythonw)$') {
        return $proc
    }

    return $null
}

function Write-BotPidFile([int]$ProcessId) {
    if (-not $ProcessId) {
        return
    }

    try {
        Set-Content -Path $PidFile -Value $ProcessId -ErrorAction Stop
    } catch {
        # Best-effort only: the launcher can still work from a live process/port.
    }
}

function Get-WebhookOwnerProcess {
    try {
        $listener = Get-NetTCPConnection -LocalPort $WebhookPort -State Listen -ErrorAction Stop |
            Select-Object -First 1
        if ($listener) {
            $proc = Get-ProcessFromId -ProcessId $listener.OwningProcess
            if ($proc) {
                Write-BotPidFile -ProcessId $proc.Id
            }
            return $proc
        }
    } catch {
        # Fall back to netstat below.
    }

    try {
        $netstatLine = netstat -ano |
            Select-String -Pattern "^\s*TCP\s+\S+:$WebhookPort\s+\S+\s+LISTENING\s+(\d+)\s*$" |
            Select-Object -First 1
        if (-not $netstatLine) {
            return $null
        }

        $netstatMatch = [regex]::Match($netstatLine.Line, "LISTENING\s+(\d+)\s*$")
        if (-not $netstatMatch.Success) {
            return $null
        }

        $proc = Get-ProcessFromId -ProcessId ([int]$netstatMatch.Groups[1].Value)
        if ($proc) {
            Write-BotPidFile -ProcessId $proc.Id
        }
        return $proc
    } catch {
        return $null
    }
}

function Get-BotProcess {
    $storedPid = Read-BotPid
    if ($storedPid) {
        $proc = Get-ProcessFromId -ProcessId $storedPid
        if ($proc) {
            return $proc
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }

    $portProc = Get-WebhookOwnerProcess
    if ($portProc) {
        return $portProc
    }

    # Last-resort fallback: command-line search via CIM. Some systems block it, so fail quietly.
    try {
        Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -like "*bot.py*" } |
            ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue } |
            Select-Object -First 1
    } catch {
        return $null
    }
}

function Get-AgentProcesses {
    $bot = Get-BotProcess
    if (-not $bot) { return @() }

    try {
        # Find child processes of the bot
        Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object { $_.ParentProcessId -eq $bot.Id } |
            ForEach-Object {
                [PSCustomObject]@{
                    Name = $_.Name
                    PID  = $_.ProcessId
                    Cmd  = ($_.CommandLine -replace '^.*?(claude|codex|qwen|gemini).*$','$1')
                }
            }
    } catch {
        @()
    }
}

function Show-Status {
    $proc = Get-BotProcess
    if ($proc) {
        Write-Host "Bot: RUNNING (PID $($proc.Id))" -ForegroundColor Green
        $agents = Get-AgentProcesses
        if ($agents) {
            Write-Host "Active agents:" -ForegroundColor Yellow
            $agents | ForEach-Object { Write-Host "  $($_.Name) (PID $($_.PID))" }
        } else {
            Write-Host "No active agent processes." -ForegroundColor Gray
        }
        if (Test-Path $LogFile) {
            Write-Host "`nLast 5 log lines:" -ForegroundColor Cyan
            Get-Content $LogFile -Tail 5
        }
    } else {
        Write-Host "Bot: STOPPED" -ForegroundColor Red
    }
}

function Stop-Bot {
    $proc = Get-BotProcess
    if (-not $proc) {
        Write-Host "Bot is not running." -ForegroundColor Yellow
        return
    }

    # Check for active agents
    $agents = Get-AgentProcesses
    if ($agents) {
        Write-Host "WARNING: Active agent processes will be killed:" -ForegroundColor Red
        $agents | ForEach-Object { Write-Host "  $($_.Name) (PID $($_.PID))" -ForegroundColor Yellow }
        $confirm = Read-Host "Continue? (y/N)"
        if ($confirm -ne "y") {
            Write-Host "Cancelled." -ForegroundColor Gray
            return
        }
    }

    Write-Host "Stopping bot (PID $($proc.Id))..." -ForegroundColor Yellow
    # Kill the whole process tree
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    # Also kill any orphaned children
    $agents | ForEach-Object {
        Stop-Process -Id $_.PID -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Bot stopped." -ForegroundColor Green
}

function Start-Bot {
    $existing = Get-BotProcess
    if ($existing) {
        Write-Host "Bot already running (PID $($existing.Id)). Use 'restart' to restart." -ForegroundColor Yellow
        return
    }

    # Validate required env vars
    if (-not $env:BOT_TOKEN -or -not $env:CHAT_ID) {
        Write-Host "ERROR: BOT_TOKEN or CHAT_ID not set. Check .env file." -ForegroundColor Red
        return
    }

    Write-Host "Starting bot..." -ForegroundColor Cyan
    $proc = Start-Process python -ArgumentList "bot\bot.py" `
        -WorkingDirectory $RepoDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $LogFile `
        -RedirectStandardError $ErrLogFile `
        -PassThru

    Write-BotPidFile -ProcessId $proc.Id
    Start-Sleep -Seconds 2

    # Verify it started
    $check = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
    $owner = Get-WebhookOwnerProcess
    if ($owner -and $owner.Id -eq $proc.Id) {
        Write-Host "Bot started (PID $($proc.Id)). Log: $LogFile" -ForegroundColor Green
    } elseif ($owner) {
        Write-Host "Bot is already running on port $WebhookPort (PID $($owner.Id)). New process was not used." -ForegroundColor Yellow
        Write-BotPidFile -ProcessId $owner.Id
        if ($check) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    } elseif ($check) {
        Write-Host "Bot process started (PID $($proc.Id)), but webhook port $WebhookPort is not listening yet. Check $ErrLogFile" -ForegroundColor Yellow
    } else {
        Write-Host "Bot failed to start. Check $ErrLogFile" -ForegroundColor Red
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
}

switch ($Action) {
    "start"   { Start-Bot }
    "stop"    { Stop-Bot }
    "restart" { Stop-Bot; Start-Sleep -Seconds 1; Start-Bot }
    "status"  { Show-Status }
}
