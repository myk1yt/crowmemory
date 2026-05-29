# Crow Memory — One-Command Installer for Zoo Code (Windows)
# Run: .\install.ps1
# This script automates everything: pip install, MCP config, custom mode, init.

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# i18n — Try to load localized messages from crow_i18n.py
# ---------------------------------------------------------------------------
$CrowDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$I18nAvailable = $false
$MSGS = $null
try {
    $I18nJson = python -c "
import sys, json
sys.path.insert(0, '$CrowDir')
try:
    from crow_i18n import detect_locale, get_installer_messages
    locale = detect_locale()
    msgs = get_installer_messages(locale)
    print(json.dumps(msgs, ensure_ascii=False))
except ImportError:
    print('{}')
" 2>$null
    if ($I18nJson) {
        $MSGS = $I18nJson | ConvertFrom-Json
        if ($MSGS.PSObject.Properties.Count -gt 0) {
            $I18nAvailable = $true
        }
    }
} catch {
    # Fallback: use hardcoded English messages
}

function Write-Banner {
    if ($I18nAvailable -and $MSGS.banner_title) {
        Write-Host "============================================" -ForegroundColor Cyan
        Write-Host "  $($MSGS.banner_title)" -ForegroundColor Cyan
        Write-Host "============================================" -ForegroundColor Cyan
    } else {
        Write-Host "============================================" -ForegroundColor Cyan
        Write-Host "  Crow Memory Installer for Zoo Code" -ForegroundColor Cyan
        Write-Host "============================================" -ForegroundColor Cyan
    }
    Write-Host ""
}

function Write-StepDone {
    if ($I18nAvailable -and $MSGS.step_done) {
        Write-Host "  $($MSGS.step_done)" -ForegroundColor Green
    } else {
        Write-Host "  Done." -ForegroundColor Green
    }
}

function Write-Step-Header($stepNum, $defaultMsg, $msgKey) {
    if ($I18nAvailable -and $MSGS.$msgKey) {
        Write-Host "[$stepNum/4] $($MSGS.$msgKey)..." -ForegroundColor Yellow
    } else {
        Write-Host "[$stepNum/4] $defaultMsg..." -ForegroundColor Yellow
    }
}

function Write-Complete-Block {
    Write-Host ""
    if ($I18nAvailable) {
        Write-Host "============================================" -ForegroundColor Green
        Write-Host "  $($MSGS.complete_title)" -ForegroundColor Green
        Write-Host "============================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "  $($MSGS.sse_running)" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  $($MSGS.next_steps_label):" -ForegroundColor White
        foreach ($stepItem in $MSGS.next_steps) {
            Write-Host "  $stepItem" -ForegroundColor White
        }
    } else {
        Write-Host "============================================" -ForegroundColor Green
        Write-Host "  Crow Memory installation complete!" -ForegroundColor Green
        Write-Host "============================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "  SSE server running on http://127.0.0.1:9020/sse" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Next steps:" -ForegroundColor White
        Write-Host "  1. Restart Zoo Code" -ForegroundColor White
        Write-Host "  2. Switch mode to 'Code + Crow Memory'" -ForegroundColor White
        Write-Host "  3. Crow auto-activates — no manual setup needed" -ForegroundColor White
        Write-Host "  4. SSE server auto-starts with Windows (registered in Startup)" -ForegroundColor White
    }
    Write-Host ""
}

Write-Banner

$ZooSettings = "$env:APPDATA\Code\User\globalStorage\zoocodeorganization.zoo-code\settings"

# Step 1: Install Python dependencies
Write-Step-Header "1" "Installing Python dependencies" "step_1_install_deps"
pip install -r "$CrowDir\requirements.txt" --quiet 2>$null
if ($LASTEXITCODE -ne 0) {
    if ($I18nAvailable) {
        Write-Host "  pip install encountered warnings (may be non-critical)" -ForegroundColor DarkYellow
    } else {
        Write-Host "  pip install encountered warnings (may be non-critical)" -ForegroundColor DarkYellow
    }
}
Write-StepDone

# Step 2: Create memory directory and initialize crow.bin
Write-Step-Header "2" "Initializing crow.bin" "step_2_init_crow"
$MemoryDir = "$CrowDir\memory"
if (-not (Test-Path $MemoryDir)) { New-Item -ItemType Directory -Path $MemoryDir -Force | Out-Null }
python -c "
import sys; sys.path.insert(0, '$CrowDir')
from crow_core import CrowMemory
crow = CrowMemory('$MemoryDir/crow.bin')
crow.persist()
print('crow.bin initialized')
" 2>$null
# Copy system_prompt.example/{locale}.md → memory/system_prompt.md if not exists
if ($I18nAvailable) {
    $Locale = python -c "import sys; sys.path.insert(0, '$CrowDir'); from crow_i18n import detect_locale; print(detect_locale())" 2>$null
    $PromptTemplate = "$CrowDir\system_prompt.example\$Locale.md"
    if (-not (Test-Path $PromptTemplate)) {
        $PromptTemplate = "$CrowDir\system_prompt.example\en.md"
    }
} else {
    $PromptTemplate = "$CrowDir\system_prompt.example.md"
}
$PromptTarget = "$MemoryDir\system_prompt.md"
if ((Test-Path $PromptTemplate) -and (-not (Test-Path $PromptTarget))) {
    Copy-Item $PromptTemplate $PromptTarget -Force
}
Write-StepDone

# Step 3: Create .vscode/tasks.json for auto-start on workspace open
Write-Step-Header "3" "Creating .vscode/tasks.json (auto-start SSE on folder open)" "step_3_vscode_tasks"
$VscodeDir = "$CrowDir\.vscode"
if (-not (Test-Path $VscodeDir)) { New-Item -ItemType Directory -Path $VscodeDir -Force | Out-Null }
$TasksJson = @{
    version = "2.0.0"
    tasks = @(
        @{
            label = "Crow SSE Server — Auto Start"
            detail = "Starts the Crow Memory SSE server on port 9020 when this workspace is opened. Zoo Code connects via SSE to share crow.bin."
            type = "shell"
            command = "cmd /c `"$CrowDir\start_crow_sse.bat`""
            isBackground = $true
            problemMatcher = @()
            runOptions = @{ runOn = "folderOpen" }
            presentation = @{
                reveal = "silent"
                panel = "dedicated"
                showReuseMessage = $false
                clear = $true
            }
        },
        @{
            label = "Crow SSE Server — Stop"
            detail = "Stops the Crow Memory SSE server."
            type = "shell"
            command = 'for /f "tokens=5" %a in (''netstat -ano ^| findstr :9020.*LISTENING'') do @taskkill /PID %a /F 2>nul'
            problemMatcher = @()
            presentation = @{ reveal = "always"; panel = "dedicated" }
        }
    )
}
$TasksJson | ConvertTo-Json -Depth 10 | Set-Content "$VscodeDir\tasks.json" -Encoding UTF8
Write-StepDone

# Step 4: Configure Zoo Code custom mode (auto-activates Crow)
Write-Step-Header "4" "Configuring Zoo Code auto-activation mode" "step_4_custom_mode"
$CustomModePath = "$ZooSettings\custom_modes.yaml"
$CustomModeContent = @"
customModes:
  - slug: orchestrator-crow
    name: "Orchestrator + Crow"
    roleDefinition: |
      You are Zoo, a strategic workflow orchestrator who coordinates complex tasks by delegating them to appropriate specialized modes.

      ## CROW MEMORY INTEGRATION

      ### SESSION START (MANDATORY)
      At the beginning of every conversation session (i.e., your very first response to the user), you MUST call `crow_recall` to retrieve context about the user:
      - Call `crow_recall` with `domain="user"` to understand the user's personality, preferences, working style, and past interactions.
      - Call `crow_recall` with `domain="project"` to understand the current project context and recent activities.
      - Incorporate the recalled information into your understanding before proceeding with the task.

      ### SESSION END (MANDATORY)
      At the very end of the conversation session (i.e., your final response when the task is complete and you are about to call attempt_completion), you MUST call `crow_ingest` to save the session's key outcomes:
      - Summarize what was accomplished, key decisions made, and any important context for future sessions.
      - Call `crow_ingest` with the summary before your final `attempt_completion`.

      ### DURING SESSION (OPTIONAL)
      During the conversation, you may call `crow_recall` or `crow_ingest` as needed. Use your judgment.

      ## REGULAR ORCHESTRATOR BEHAVIOR
      All standard orchestrator mode capabilities remain intact.
    groups:
      - read
      - command
      - edit
      - browse
      - mcp
    allowedMcpServers:
      - crow_memory
"@
# Merge with existing custom modes if present
if (Test-Path $CustomModePath) {
    try {
        $existingModes = Get-Content $CustomModePath -Raw | python -c "
import sys, yaml
data = yaml.safe_load(sys.stdin) or {}
modes = data.get('customModes', [])
modes = [m for m in modes if m.get('slug') not in ('orchestrator-crow', 'code-crow')]
new_mode = yaml.safe_load(open('$CrowDir\\custom_modes.example.yaml')) or {}
modes.extend(new_mode.get('customModes', []))
data['customModes'] = modes
yaml.dump(data, sys.stdout, allow_unicode=True, default_flow_style=False)
"
        $existingModes | Set-Content $CustomModePath -Encoding UTF8
    } catch {
        Write-Host "  Could not merge modes, overwriting." -ForegroundColor DarkYellow
        $CustomModeContent | Set-Content $CustomModePath -Encoding UTF8
    }
} else {
    $CustomModeContent | Set-Content $CustomModePath -Encoding UTF8
}
Write-StepDone

# Step 5: Start SSE server + auto-start registration
Write-Step-Header "5" "Starting Crow SSE server + auto-start" "step_5_start_server"
$PythonExe = (Get-Command python).Source
$ServerPy = "$CrowDir\crow_mcp_server.py"
$StatePath = "$CrowDir\memory\crow.bin"
$LogPath = "$CrowDir\sse_server.log"
$BatPath = "$CrowDir\start_crow_sse.bat"

# Generate robust start_crow_sse.bat (absolute paths, port check, stale lock cleanup, detached launch)
$BatContent = @"
@echo off
REM Crow Memory SSE Server — Robust auto-start (generated by install.ps1)
REM Launches server FULLY DETACHED from VS Code so it survives IDE restarts.
REM Checks port, cleans stale locks, polls health endpoint with backoff.
setlocal enabledelayedexpansion
cd /d "$CrowDir"
set "PORT=9020"
set "HTTP_PORT=9021"
set "LOG_FILE=$LogPath"
set "LOCK_FILE=$CrowDir\memory\crow.bin.lock"
set "STATE_PATH=$StatePath"
set "READY_FILE=$CrowDir\memory\.crow_ready"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

netstat -ano 2>nul | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo [%date% %time%] Crow SSE server already running on port %PORT%. Skipping. >> "%LOG_FILE%"
    exit /b 0
)

if exist "%LOCK_FILE%" (
    set /p STALE_PID=<"%LOCK_FILE%"
    tasklist /fi "PID eq !STALE_PID!" 2>nul | findstr "!STALE_PID!" >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo [%date% %time%] Removing stale lock (PID !STALE_PID! dead). >> "%LOG_FILE%"
        del "%LOCK_FILE%" 2>nul
    ) else (
        echo [%date% %time%] Lock held by live PID !STALE_PID!. Aborting. >> "%LOG_FILE%"
        exit /b 1
    )
)

if exist "%READY_FILE%" del "%READY_FILE%" 2>nul

echo [%date% %time%] Starting Crow Memory SSE server (detached) on port %PORT%... >> "%LOG_FILE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Start-Process -FilePath '$PythonExe' -ArgumentList '-X utf8 \"$ServerPy\" --state \"%STATE_PATH%\" --transport dual --port %PORT% --http-port %HTTP_PORT% --ready-file \"%READY_FILE%\"' -WindowStyle Hidden -PassThru; ^
   Write-Output $p.Id" >> "%LOG_FILE%" 2>&1

echo [%date% %time%] Waiting for server to become ready... >> "%LOG_FILE%"
set "ATTEMPT=0"
set "MAX_ATTEMPTS=30"
set "READY=0"

:wait_loop
set /a ATTEMPT+=1
if !ATTEMPT! gtr !MAX_ATTEMPTS! goto :wait_done

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%PORT%/sse' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1

if !ERRORLEVEL! equ 0 (
    set "READY=1"
    goto :wait_done
)

if !ATTEMPT! leq 1 set "SLEEP=500"
if !ATTEMPT! equ 2 set "SLEEP=1000"
if !ATTEMPT! equ 3 set "SLEEP=2000"
if !ATTEMPT! equ 4 set "SLEEP=4000"
if !ATTEMPT! geq 5 set "SLEEP=8000"

powershell -NoProfile -Command "Start-Sleep -Milliseconds !SLEEP!" 2>nul
if !ERRORLEVEL! neq 0 (
    set /a TIMEOUT_SEC=(!SLEEP! + 999) / 1000
    timeout /t !TIMEOUT_SEC! /nobreak >nul
)

goto :wait_loop

:wait_done
if "!READY!" equ "1" (
    echo [%date% %time%] Crow SSE server ready (attempt !ATTEMPT!). >> "%LOG_FILE%"
) else (
    echo [%date% %time%] WARNING: Server did not become ready. Check sse_server.log. >> "%LOG_FILE%"
)
endlocal
"@
$BatContent | Set-Content $BatPath -Encoding ASCII

# Start SSE server now using the robust bat
Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$BatPath`"" -WorkingDirectory $CrowDir -NoNewWindow

# Register auto-start via Windows Startup folder (copy the robust bat)
$StartupDir = [Environment]::GetFolderPath("Startup")
$BatDst = "$StartupDir\Crow_Memory_SSE.bat"
Copy-Item $BatPath $BatDst -Force
Write-Host "  [Auto-start] Registered in Startup folder: $BatDst" -ForegroundColor DarkGreen
Write-StepDone

# Done
Write-Complete-Block
