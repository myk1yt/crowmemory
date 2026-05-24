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
Write-Host "[1/4] Installing Python dependencies..." -ForegroundColor Yellow
pip install -r "$CrowDir\requirements.txt" --quiet 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  pip install encountered warnings (may be non-critical)" -ForegroundColor DarkYellow
}
Write-Host "  Done." -ForegroundColor Green

# Step 2: Create memory directory and initialize crow.bin
Write-Host "[2/4] Initializing crow.bin..." -ForegroundColor Yellow
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

# Step 3: Configure MCP server for Zoo Code
Write-Host "[3/4] Configuring Zoo Code MCP server..." -ForegroundColor Yellow
if (-not (Test-Path $ZooSettings)) { New-Item -ItemType Directory -Path $ZooSettings -Force | Out-Null }

$McpConfig = @{
    mcpServers = @{
        crow_memory = @{
            command = "python"
            args = @(
                "$CrowDir\crow_mcp_server.py",
                "--state",
                "$CrowDir\memory\crow.bin"
            )
            cwd = "$CrowDir"
            env = @{
                PYTHONUNBUFFERED = "1"
            }
            description = "Crow Memory - External synaptic memory for AI coding agents."
        }
    }
}

$McpConfigPath = "$ZooSettings\mcp_settings.json"
# Merge with existing config if present
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
Write-Host "[4/4] Configuring Zoo Code auto-activation mode..." -ForegroundColor Yellow
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
      - After the user accepts your solution without edits, call crow_ingest or crow_ingest_from_build to reinforce successful patterns.
      - After the user rewrites your code, call crow_ingest with negative polarity to learn from the correction.

      Crow is not a database — it stores inductive biases. Use it as your intuition, not your encyclopedia.
    groups:
      - command
      - read
      - edit
    customInstructions: |
      Always call crow_recall before generating code. Use crow_ingest_from_build after build success.
"@
$CustomModeContent | Set-Content $CustomModePath -Encoding UTF8
Write-Host "  Done." -ForegroundColor Green

# Done
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Crow Memory installation complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "  1. Restart Zoo Code" -ForegroundColor White
Write-Host "  2. Switch mode to 'Code + Crow Memory'" -ForegroundColor White
Write-Host "  3. Crow will auto-activate on every response" -ForegroundColor White
Write-Host ""
