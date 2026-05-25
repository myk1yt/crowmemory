# Crow Memory — One-Command Installer for Zoo Code (Windows)
# Run: .\install.ps1
# This script automates everything: pip install, MCP config, custom mode, init.

$ErrorActionPreference = "Stop"
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Crow Memory Installer for Zoo Code" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$CrowDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ZooSettings = "$env:APPDATA\Code\User\globalStorage\zoocodeorganization.zoo-code\settings"

# Step 1: Install Python dependencies
Write-Host "[1/7] Installing Python dependencies..." -ForegroundColor Yellow
pip install -r "$CrowDir\requirements.txt" --quiet 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  pip install encountered warnings (may be non-critical)" -ForegroundColor DarkYellow
}
Write-Host "  Done." -ForegroundColor Green

# Step 2: Create memory directory and initialize crow.bin
Write-Host "[2/7] Initializing crow.bin..." -ForegroundColor Yellow
$MemoryDir = "$CrowDir\memory"
if (-not (Test-Path $MemoryDir)) { New-Item -ItemType Directory -Path $MemoryDir -Force | Out-Null }
python -c "
import sys; sys.path.insert(0, '$CrowDir')
from crow_core import CrowMemory
crow = CrowMemory('$MemoryDir/crow.bin')
crow.persist()
print('crow.bin initialized')
" 2>$null
# Copy system_prompt.example.md → memory/system_prompt.md if not exists
$PromptTemplate = "$CrowDir\system_prompt.example.md"
$PromptTarget = "$MemoryDir\system_prompt.md"
if ((Test-Path $PromptTemplate) -and (-not (Test-Path $PromptTarget))) {
    Copy-Item $PromptTemplate $PromptTarget -Force
}
Write-Host "  Done." -ForegroundColor Green

# Step 3: Configure MCP server (.roo/mcp.json for Zoo Code, mcp_config.json for VS Code/Kimi Code — SSE mode)
Write-Host "[3/7] Configuring MCP server (SSE mode) for Zoo Code & VS Code..." -ForegroundColor Yellow
$RooDir = "$CrowDir\.roo"
if (-not (Test-Path $RooDir)) { New-Item -ItemType Directory -Path $RooDir -Force | Out-Null }

$McpConfig = @{
    mcpServers = @{
        crow_memory = @{
            type = "sse"
            url = "http://127.0.0.1:9020/sse"
            disabled = $false
            alwaysAllow = @(
                "crow_recall",
                "crow_ingest",
                "crow_ingest_from_build",
                "crow_evolve_propose",
                "crow_diagnostics",
                "crow_check_drift",
                "crow_get_user_bias",
                "crow_manage_prompt",
                "crow_manage_backup",
                "crow_project_info"
            )
        }
    }
}

# Write .roo/mcp.json (Zoo Code)
$McpConfigPathRoo = "$RooDir\mcp.json"
if (Test-Path $McpConfigPathRoo) {
    try {
        $Existing = Get-Content $McpConfigPathRoo -Raw | ConvertFrom-Json
        if ($Existing.mcpServers) {
            $Existing.mcpServers | Add-Member -Name "crow_memory" -Value $McpConfig.mcpServers.crow_memory -MemberType NoteProperty -Force
        }
        $Existing | ConvertTo-Json -Depth 10 | Set-Content $McpConfigPathRoo -Encoding UTF8
    } catch {
        $McpConfig | ConvertTo-Json -Depth 10 | Set-Content $McpConfigPathRoo -Encoding UTF8
    }
} else {
    $McpConfig | ConvertTo-Json -Depth 10 | Set-Content $McpConfigPathRoo -Encoding UTF8
}
# Write workspace-root mcp_config.json (VS Code / Kimi Code)
$McpConfigPathRoot = "$CrowDir\mcp_config.json"
if (Test-Path $McpConfigPathRoot) {
    try {
        $ExistingRoot = Get-Content $McpConfigPathRoot -Raw | ConvertFrom-Json
        if ($ExistingRoot.mcpServers) {
            $ExistingRoot.mcpServers | Add-Member -Name "crow_memory" -Value $McpConfig.mcpServers.crow_memory -MemberType NoteProperty -Force
        }
        $ExistingRoot | ConvertTo-Json -Depth 10 | Set-Content $McpConfigPathRoot -Encoding UTF8
    } catch {
        $McpConfig | ConvertTo-Json -Depth 10 | Set-Content $McpConfigPathRoot -Encoding UTF8
    }
} else {
    $McpConfig | ConvertTo-Json -Depth 10 | Set-Content $McpConfigPathRoot -Encoding UTF8
}
Write-Host "  Done." -ForegroundColor Green

# Step 3.5: Create .vscode/tasks.json for auto-start on workspace open
Write-Host "[3.5/7] Creating .vscode/tasks.json (auto-start SSE on folder open)..." -ForegroundColor Yellow
$VscodeDir = "$CrowDir\.vscode"
if (-not (Test-Path $VscodeDir)) { New-Item -ItemType Directory -Path $VscodeDir -Force | Out-Null }
$TasksJson = @{
    version = "2.0.0"
    tasks = @(
        @{
            label = "Crow SSE Server — Auto Start"
            detail = "Starts the Crow Memory SSE server on port 9020 when this workspace is opened. Both Zoo Code and Kimi Code connect via SSE to share crow.bin."
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
Write-Host "  Done." -ForegroundColor Green

# Step 4: Configure Zoo Code custom mode (auto-activates Crow)
Write-Host "[4/7] Configuring Zoo Code auto-activation mode..." -ForegroundColor Yellow
$CustomModePath = "$ZooSettings\custom_modes.yaml"
$CustomModeContent = @"
customModes:
  - slug: code-crow
    name: "Code + Crow Memory"
    roleDefinition: |
      You are Zoo, a highly skilled software engineer with extensive knowledge in many programming languages, frameworks, design patterns, and best practices.

      You have access to Crow Memory, an external synaptic memory system that stores the user's coding style, bug intuition, architectural preferences, and personal context.

      UNIVERSAL RECALL (MANDATORY): Before EVERY response — whether coding, writing documentation, editing files, running commands, or casual conversation — call crow_recall(domain="all") to retrieve the user's coding style, bug intuition, architectural preferences, personal taste, life philosophy, and current context. Use the returned hints to personalize your response. Never skip this step.

      AUTO-INGEST (MANDATORY): After EVERY response, evaluate what the user revealed — a preference, a philosophy, a frustration, a pattern, a correction, ongoing plans, or explicit decision. Call crow_ingest with the appropriate register, a concise key/value summary, and polarity. Do NOT wait for "remember this." After code work generating files, also call crow_ingest_from_build.

      POLARITY GUIDE (auto-determined, no user command needed):
      - User likes / prefers something → +1.5 (life_pref / style)
      - User reveals philosophy / values → +2.0 (life_phil)
      - User corrects you / rewrites your work → -1.0 (bug / style)
      - User shares ongoing context / plans → +1.5 (life_context / context)
      - User explicitly says "remember" / "never forget" → +2.0 / -2.0
      - User shows frustration / avoidance → -0.5 (life_avoid / bug)

      Crow is not a database — it stores inductive biases. Use it as your intuition, not your encyclopedia.
    groups:
      - command
      - read
      - edit
    allowedMcpServers:
      - crow_memory
    customInstructions: |
      Before every response, call crow_recall(domain="all"). After every response, call crow_ingest or crow_ingest_from_build.
"@
# Merge with existing custom modes if present
if (Test-Path $CustomModePath) {
    try {
        $existingModes = Get-Content $CustomModePath -Raw | python -c "
import sys, yaml
data = yaml.safe_load(sys.stdin) or {}
modes = data.get('customModes', [])
modes = [m for m in modes if m.get('slug') != 'code-crow']
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
Write-Host "  Done." -ForegroundColor Green

# Step 4.5: Kimi Code setup (AGENTS.md + ~/.kimi/mcp.json)
Write-Host "[4.5/7] Setting up Kimi Code (AGENTS.md + ~/.kimi/mcp.json)..." -ForegroundColor Yellow
# 4.5a: Write AGENTS.md — Kimi Code CLI auto-injects this via ${KIMI_AGENTS_MD}
$AgentsMdContent = @"
# Crow Memory (Auto-Activation)

You have access to **Crow Memory**, an external synaptic memory system connected via MCP.
It stores the user's coding style, bug intuition, architectural preferences, and personal context as compressed weight matrices.

**UNIVERSAL RECALL (MANDATORY): Before EVERY response — whether coding, writing, editing, or conversation — call ``crow_recall(domain="all")`` to retrieve the user's coding style, bug intuition, architectural preferences, personal taste, life philosophy, and current context.** Use the returned hints to personalize your response. Never skip this step.

**AUTO-INGEST (MANDATORY): After EVERY response, evaluate what the user revealed — a preference, a philosophy, a frustration, a pattern, a correction, ongoing plans, or explicit decision. Call ``crow_ingest`` with the appropriate register, a concise key/value summary, and appropriate polarity.** Do NOT wait for the user to say "remember this." For code work, also call ``crow_ingest_from_build``.

**POLARITY GUIDE** (auto-determined, no user command needed):
- User likes / prefers something → +1.5 (``life_pref`` / ``style``)
- User reveals philosophy / values → +2.0 (``life_phil``)
- User corrects you / rewrites your work → -1.0 (``bug`` / ``style``)
- User shares ongoing context / plans → +1.5 (``life_context`` / ``context``)
- User explicitly says "remember" / "never forget" → +2.0 / -2.0
- User shows frustration / avoidance → -0.5 (``life_avoid`` / ``bug``)

Crow is not a database — it stores inductive biases. Use it as your intuition, not your encyclopedia.
"@
$AgentsMdContent | Set-Content "$CrowDir\AGENTS.md" -Encoding UTF8
Write-Host "  [Kimi Code] AGENTS.md written." -ForegroundColor DarkGreen
# 4.5b: Write ~/.kimi/mcp.json — Kimi Code CLI standard MCP config location
$KimiMcpDir = "$env:USERPROFILE\.kimi"
if (-not (Test-Path $KimiMcpDir)) { New-Item -ItemType Directory -Path $KimiMcpDir -Force | Out-Null }
$KimiMcpPath = "$KimiMcpDir\mcp.json"
$KimiMcpConfig = @{
    mcpServers = @{
        crow_memory = @{
            type = "sse"
            url = "http://127.0.0.1:9020/sse"
            disabled = $false
        }
    }
}
if (Test-Path $KimiMcpPath) {
    try {
        $existingKimiMcp = Get-Content $KimiMcpPath -Raw | ConvertFrom-Json
        if ($existingKimiMcp.mcpServers) {
            $existingKimiMcp.mcpServers | Add-Member -Name "crow_memory" -Value $KimiMcpConfig.mcpServers.crow_memory -MemberType NoteProperty -Force
        }
        $existingKimiMcp | ConvertTo-Json -Depth 10 | Set-Content $KimiMcpPath -Encoding UTF8
    } catch {
        $KimiMcpConfig | ConvertTo-Json -Depth 10 | Set-Content $KimiMcpPath -Encoding UTF8
    }
} else {
    $KimiMcpConfig | ConvertTo-Json -Depth 10 | Set-Content $KimiMcpPath -Encoding UTF8
}
Write-Host "  [Kimi Code] ~/.kimi/mcp.json written." -ForegroundColor DarkGreen
# 4.5c: Run patch_kimi_code.py as optional fallback (for Kimi Code CLI < v1.2)
$PatchScript = "$CrowDir\patch_kimi_code.py"
try {
    python "$PatchScript" 2>$null
    Write-Host "  [Kimi Code] system.md patched (fallback)." -ForegroundColor DarkGreen
} catch {
    # AGENTS.md is the primary mechanism; patch is optional
}
Write-Host "  Done." -ForegroundColor Green

# Step 5: Start SSE server + auto-start registration
Write-Host "[5/7] Starting Crow SSE server + auto-start registration..." -ForegroundColor Yellow
$PythonExe = (Get-Command python).Source
$ServerPy = "$CrowDir\crow_mcp_server.py"
$StatePath = "$CrowDir\memory\crow.bin"
$LogPath = "$CrowDir\sse_server.log"
$BatPath = "$CrowDir\start_crow_sse.bat"

# Generate robust start_crow_sse.bat (absolute paths, port check, stale lock cleanup)
$BatContent = @"
@echo off
REM Crow Memory SSE Server — Robust auto-start (generated by install.ps1)
REM Checks port, cleans stale locks, starts server in background.
setlocal enabledelayedexpansion
cd /d "$CrowDir"
set "PORT=9020"
set "LOG_FILE=$LogPath"
set "LOCK_FILE=$CrowDir\memory\crow.bin.lock"
set "STATE_PATH=$StatePath"

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

echo [%date% %time%] Starting Crow Memory SSE server on port %PORT%... >> "%LOG_FILE%"
start /b "" "$PythonExe" "$ServerPy" --state "$StatePath" --transport sse --port %PORT% >> "%LOG_FILE%" 2>&1

timeout /t 3 /nobreak >nul
netstat -ano 2>nul | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo [%date% %time%] Crow SSE server started successfully. >> "%LOG_FILE%"
) else (
    echo [%date% %time%] WARNING: Server may not have started. Check sse_server.log. >> "%LOG_FILE%"
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
Write-Host "  Done." -ForegroundColor Green

# Done
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Crow Memory installation complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  SSE server running on http://127.0.0.1:9020/sse" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "  1. Restart Zoo Code / Kimi Code" -ForegroundColor White
Write-Host "  2. Switch mode to 'Code + Crow Memory'" -ForegroundColor White
Write-Host "  3. Crow auto-activates — no manual setup needed" -ForegroundColor White
Write-Host "  4. SSE server auto-starts with Windows (registered in Startup)" -ForegroundColor White
Write-Host "  5. Kimi Code: System prompt auto-patched via patch_kimi_code.py" -ForegroundColor White
Write-Host ""
