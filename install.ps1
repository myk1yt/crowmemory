# Crow Memory — One-Command Installer for Windows
# Run: .\install.ps1

$ErrorActionPreference = "Stop"
$CrowDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MemoryDir = "$CrowDir\memory"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Crow Memory Installer" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Install Python dependencies
Write-Host "[1/5] Installing Python dependencies..." -ForegroundColor Yellow
pip install -r "$CrowDir\requirements.txt" --quiet 2>$null
Write-Host "  Done." -ForegroundColor Green

# Step 2: Create memory directory and initialize crow.bin
Write-Host "[2/5] Initializing crow.bin and system prompt..." -ForegroundColor Yellow
if (-not (Test-Path $MemoryDir)) { New-Item -ItemType Directory -Path $MemoryDir -Force | Out-Null }
python -c "
import sys; sys.path.insert(0, '$CrowDir')
from crow_core import CrowMemory
crow = CrowMemory('$MemoryDir/crow.bin')
crow.persist()
" 2>$null

$PromptTemplate = "$CrowDir\system_prompt.example.md"
$PromptTarget = "$MemoryDir\system_prompt.md"
if ((Test-Path $PromptTemplate) -and (-not (Test-Path $PromptTarget))) {
    Copy-Item $PromptTemplate $PromptTarget -Force
}
Write-Host "  Done." -ForegroundColor Green

# Step 3: Global MCP Configs (Kimi, Roo/Cline)
Write-Host "[3/5] Configuring Global MCP settings (Kimi 9021, Roo/Zoo 9020)..." -ForegroundColor Yellow
$KimiMcpDir = "$env:USERPROFILE\.kimi"
if (-not (Test-Path $KimiMcpDir)) { New-Item -ItemType Directory -Path $KimiMcpDir -Force | Out-Null }
$KimiMcpFile = "$KimiMcpDir\mcp.json"
$KimiCfg = @{ mcpServers = @{} }
if (Test-Path $KimiMcpFile) {
    try { $KimiCfg = Get-Content $KimiMcpFile -Raw | ConvertFrom-Json -AsHashtable } catch { }
}
if (-not $KimiCfg.ContainsKey("mcpServers")) { $KimiCfg.mcpServers = @{} }
$KimiCfg.mcpServers["crow_memory"] = @{ transport = "http"; url = "http://127.0.0.1:9021/" }
$KimiCfg | ConvertTo-Json -Depth 10 | Set-Content $KimiMcpFile -Encoding UTF8

$RooMcpDir = "$env:APPDATA\Code\User\globalStorage\rooveterinaryinc.roo-cline\settings"
if (Test-Path (Split-Path $RooMcpDir -Parent)) {
    if (-not (Test-Path $RooMcpDir)) { New-Item -ItemType Directory -Path $RooMcpDir -Force | Out-Null }
    $RooMcpFile = "$RooMcpDir\cline_mcp_settings.json"
    $RooCfg = @{ mcpServers = @{} }
    if (Test-Path $RooMcpFile) {
        try { $RooCfg = Get-Content $RooMcpFile -Raw | ConvertFrom-Json -AsHashtable } catch { }
    }
    if (-not $RooCfg.ContainsKey("mcpServers")) { $RooCfg.mcpServers = @{} }
    $RooCfg.mcpServers["crow_memory"] = @{ command = "python"; args = @("$CrowDir\crow_mcp_server.py", "--transport", "stdio", "--state", "$MemoryDir\crow.bin") }
    $RooCfg | ConvertTo-Json -Depth 10 | Set-Content $RooMcpFile -Encoding UTF8
}
Write-Host "  Done." -ForegroundColor Green

# Step 4: Configure Zoo Code custom mode
Write-Host "[4/5] Configuring Zoo Code auto-activation mode..." -ForegroundColor Yellow
$ZooSettings = "$env:APPDATA\Code\User\globalStorage\zoocodeorganization.zoo-code\settings"
$CustomModePath = "$ZooSettings\custom_modes.yaml"
$CustomModeContent = @"
customModes:
  - slug: orchestrator-crow
    name: "Orchestrator + Crow"
    roleDefinition: |
      You are Zoo, a strategic workflow orchestrator who coordinates complex tasks by delegating them to appropriate specialized modes.

      ## CROW MEMORY INTEGRATION

      ### SESSION START (MANDATORY)
      At the beginning of every conversation session, you MUST call `crow_recall` to retrieve context about the user (domain="user") and project (domain="project").

      ### SESSION END (MANDATORY)
      At the very end of the conversation session, you MUST call `crow_ingest` to save the session's key outcomes before calling attempt_completion.

      ### DURING SESSION (OPTIONAL)
      During the conversation, you may call `crow_recall` or `crow_ingest` as needed.

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
if (Test-Path (Split-Path $ZooSettings -Parent)) {
    if (-not (Test-Path $ZooSettings)) { New-Item -ItemType Directory -Path $ZooSettings -Force | Out-Null }
    if (Test-Path $CustomModePath) {
        try {
            $existingModes = Get-Content $CustomModePath -Raw | python -c "
import sys, yaml
data = yaml.safe_load(sys.stdin) or {}
modes = data.get('customModes', [])
modes = [m for m in modes if m.get('slug') not in ('orchestrator-crow', 'code-crow')]
new_mode = yaml.safe_load('''$CustomModeContent''') or {}
modes.extend(new_mode.get('customModes', []))
data['customModes'] = modes
yaml.dump(data, sys.stdout, allow_unicode=True, default_flow_style=False)
"
            $existingModes | Set-Content $CustomModePath -Encoding UTF8
        } catch {
            $CustomModeContent | Set-Content $CustomModePath -Encoding UTF8
        }
    } else {
        $CustomModeContent | Set-Content $CustomModePath -Encoding UTF8
    }
}
Write-Host "  Done." -ForegroundColor Green

# Step 5: Start SSE server + auto-start registration
Write-Host "[5/5] Starting Crow SSE server + auto-start..." -ForegroundColor Yellow
$BatPath = "$CrowDir\start_crow_sse.bat"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$BatPath`"" -WorkingDirectory $CrowDir -NoNewWindow

$StartupDir = [Environment]::GetFolderPath("Startup")
$BatDst = "$StartupDir\Crow_Memory_SSE.bat"
Copy-Item $BatPath $BatDst -Force
Write-Host "  [Auto-start] Registered in Startup folder: $BatDst" -ForegroundColor DarkGreen
Write-Host "  Done." -ForegroundColor Green

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Crow Memory installation complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  SSE server running on http://127.0.0.1:9020/sse (HTTP on 9021)" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "  1. Restart your IDE (Zoo Code / Kimi Code / Roo Code)" -ForegroundColor White
Write-Host "  2. For Zoo Code: Switch mode to 'Orchestrator + Crow'" -ForegroundColor White
Write-Host "  3. Server auto-starts with Windows (registered in Startup)" -ForegroundColor White
Write-Host ""
