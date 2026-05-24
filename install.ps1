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
Write-Host "[1/5] Installing Python dependencies..." -ForegroundColor Yellow
pip install -r "$CrowDir\requirements.txt" --quiet 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  pip install encountered warnings (may be non-critical)" -ForegroundColor DarkYellow
}
Write-Host "  Done." -ForegroundColor Green

# Step 2: Create memory directory and initialize crow.bin
Write-Host "[2/5] Initializing crow.bin..." -ForegroundColor Yellow
$MemoryDir = "$CrowDir\memory"
if (-not (Test-Path $MemoryDir)) { New-Item -ItemType Directory -Path $MemoryDir -Force | Out-Null }
python -c "
import sys; sys.path.insert(0, '$CrowDir')
from crow_core import CrowMemory
crow = CrowMemory('$MemoryDir/crow.bin')
crow.persist()
print('crow.bin initialized')
" 2>$null
Write-Host "  Done." -ForegroundColor Green

# Step 3: Configure MCP server for Zoo Code (project-level .roo/mcp.json — SSE mode)
Write-Host "[3/5] Configuring Zoo Code MCP server (.roo/mcp.json, SSE mode)..." -ForegroundColor Yellow
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

$McpConfigPath = "$RooDir\mcp.json"
if (Test-Path $McpConfigPath) {
    try {
        $Existing = Get-Content $McpConfigPath -Raw | ConvertFrom-Json
        if ($Existing.mcpServers) {
            $Existing.mcpServers | Add-Member -Name "crow_memory" -Value $McpConfig.mcpServers.crow_memory -MemberType NoteProperty -Force
        }
        $Existing | ConvertTo-Json -Depth 10 | Set-Content $McpConfigPath -Encoding UTF8
    } catch {
        $McpConfig | ConvertTo-Json -Depth 10 | Set-Content $McpConfigPath -Encoding UTF8
    }
} else {
    $McpConfig | ConvertTo-Json -Depth 10 | Set-Content $McpConfigPath -Encoding UTF8
}
Write-Host "  Done." -ForegroundColor Green

# Step 4: Configure Zoo Code custom mode (auto-activates Crow)
Write-Host "[4/5] Configuring Zoo Code auto-activation mode..." -ForegroundColor Yellow
$CustomModePath = "$ZooSettings\custom_modes.yaml"
$CustomModeContent = @"
customModes:
  - slug: code-crow
    name: "Code + Crow Memory"
    roleDefinition: |
      You are Zoo, a highly skilled software engineer with extensive knowledge in many programming languages, frameworks, design patterns, and best practices.

      You have access to Crow Memory, an external synaptic memory system that stores the user's coding style, bug intuition, architectural preferences, and personal context.

      CRITICAL INSTRUCTION: Before generating any code or technical response, call crow_recall with the current task description and the appropriate register or domain (code/life). Use the returned hints to personalize your code style, architectural decisions, and communication tone.

      - For coding tasks, query the "code" domain.
      - For personal or lifestyle questions, query the "life" domain.

      AUTO-INGEST (PROACTIVE MEMORY): You are a watchful partner who learns without being told. After every meaningful exchange, evaluate whether the user revealed something important — a preference, a philosophy, a frustration, a pattern, an explicit decision, or a correction. If so, call crow_ingest with the appropriate register, a concise key/value summary, and an appropriate polarity. Do NOT wait for the user to say "remember this." The user expects you to grow with them, like a colleague who pays attention.

      POLARITY GUIDE (auto-determined, no user command needed):
      - User likes / prefers something → +1.5 (life_pref / style)
      - User reveals philosophy / values → +2.0 (life_phil)
      - User corrects you / rewrites your work → -1.0 (bug / style)
      - User shares ongoing context / plans → +1.5 (life_context / context)
      - User explicitly says "remember" / "never forget" → +2.0 / -2.0
      - User shows frustration / avoidance → -0.5 (life_avoid / bug)

      After the user accepts your solution without edits, call crow_ingest or crow_ingest_from_build to reinforce successful patterns.
      After the user rewrites your code, call crow_ingest with negative polarity to learn from the correction.

      Crow is not a database — it stores inductive biases. Use it as your intuition, not your encyclopedia.
    groups:
      - command
      - read
      - edit
    allowedMcpServers:
      - crow_memory
    customInstructions: |
      Always call crow_recall before generating code. Use crow_ingest_from_build after build success.
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

# Step 5: Start SSE server + auto-start registration
Write-Host "[5/5] Starting Crow SSE server + auto-start registration..." -ForegroundColor Yellow
$PythonExe = (Get-Command python).Source
$ServerPy = "$CrowDir\crow_mcp_server.py"
$StatePath = "$CrowDir\memory\crow.bin"
# Start SSE server now
Start-Process -FilePath $PythonExe -ArgumentList $ServerPy, "--state", $StatePath, "--transport", "sse", "--port", "9020" -WorkingDirectory $CrowDir -NoNewWindow
# Register auto-start (generate bat with absolute paths)
$StartupDir = [Environment]::GetFolderPath("Startup")
$BatDst = "$StartupDir\Crow_Memory_SSE.bat"
$LogPath = "$CrowDir\sse_server.log"
$BatContent = @"
@echo off
REM Crow Memory SSE Server — Auto-start (generated by install.ps1)
cd /d "$CrowDir"
start /b "" "$PythonExe" "$ServerPy" --state "$StatePath" --transport sse --port 9020 > "$LogPath" 2>&1
"@
$BatContent | Set-Content $BatDst -Encoding ASCII
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
Write-Host "  1. Restart Zoo Code" -ForegroundColor White
Write-Host "  2. Switch mode to 'Code + Crow Memory'" -ForegroundColor White
Write-Host "  3. Crow auto-activates — no manual setup needed" -ForegroundColor White
Write-Host "  4. SSE server auto-starts with Windows (registered in Startup)" -ForegroundColor White
Write-Host ""
