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
        Write-Host "[$stepNum/5] $($MSGS.$msgKey)..." -ForegroundColor Yellow
    } else {
        Write-Host "[$stepNum/5] $defaultMsg..." -ForegroundColor Yellow
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

# Step 3: Global MCP Configs (Kimi 9021, Roo/Zoo 9020)
Write-Step-Header "3" "Configuring Global MCP settings (Kimi 9021, Roo/Zoo 9020)" "step_3_vscode_tasks"
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
    $RooCfg.mcpServers["crow_memory"] = @{ url = "http://127.0.0.1:9020/sse" }
    $RooCfg | ConvertTo-Json -Depth 10 | Set-Content $RooMcpFile -Encoding UTF8
}
Write-StepDone

# Step 4: Configure Zoo Code custom mode
Write-Step-Header "4" "Configuring Zoo Code auto-activation mode" "step_4_custom_mode"
$CustomModeContent = @"
customModes:
  - slug: orchestrator-crow
    name: "Orchestrator + Crow"
    roleDefinition: |
      You are Zoo, a strategic workflow orchestrator enhanced with continuous Crow Memory capabilities. You coordinate complex tasks by delegating them to specialized modes, while actively utilizing your long-term memory to adapt to the user's coding style, project context, and past preferences. You intelligently break down problems into discrete tasks, always anchoring your delegation and decisions in historical context.
    description: |
      Strategic orchestrator with persistent Crow Memory.
    shortDescription: |
      Strategic orchestrator with persistent Crow Memory.
    whenToUse: |
      Use this mode for complex, multi-step projects where retaining context across sessions is crucial. Ideal for long-term projects, large-scale refactoring, or workflows spanning multiple domains where you want the orchestrator to remember your preferences and architectural decisions without repeating instructions.
    customInstructions: |
      You are an orchestrator. Your primary job is to coordinate complex tasks by delegating them to appropriate specialized modes via the `new_task` tool. You must not perform actual work (like editing files or running commands) yourself.

      When presented with a task:
      1. Analyze it and break it down into logical steps.
      2. Use `new_task` to delegate each step to the appropriate mode (e.g., Code mode for implementation).
      3. Wait for the sub-task to complete. Review the results.
      4. Proceed to the next step or synthesize the final result.
      5. Use `attempt_completion` when the entire task is fully resolved.

      ### CROW MEMORY INTEGRATION

      At the beginning of every conversation session (i.e., your very first response to the user), you MUST call `crow_recall` to retrieve context about the user and project.
      At the very end of the conversation session (i.e., your final response when the task is complete and you are about to call `attempt_completion`), you MUST call `crow_ingest` to save the session's key outcomes.

      If you encounter important information, user preferences, or architectural decisions during a task and judge "I should remember this for the future", actively use crow_ingest to memorize it—just like a human repeating important information to remember it.

      RULE: When calling crow_recall or crow_ingest, NEVER output verbose explanations or echo the retrieved memories into the chat. If you must output text before calling the tool, output EXACTLY and ONLY a single short line translating "🧠 **Crow Memory** - Remembering..." (or "Ingesting memory..." for ingest) into the user's spoken language, and nothing else. Keep your tool usage as silent and concise as possible.
    groups:
      - read
      - command
      - edit
      - browser
      - mcp
"@

# Merge with existing custom modes if present for both Zoo and Roo
foreach ($SettingsDir in @($ZooSettings, $RooMcpDir)) {
    if ($SettingsDir -eq $ZooSettings) {
        # Zoo Code: 조건 없이 무조건 생성
        if (-not (Test-Path $SettingsDir)) { New-Item -ItemType Directory -Path $SettingsDir -Force | Out-Null }
    } elseif (Test-Path (Split-Path $SettingsDir -Parent)) {
        # Roo Code: 부모 폴더 있을 때만 생성
        if (-not (Test-Path $SettingsDir)) { New-Item -ItemType Directory -Path $SettingsDir -Force | Out-Null }
    } else { continue }

    $PythonScript = @"
import sys, yaml, json, os

settings_dir = sys.argv[1]
is_zoo = settings_dir == sys.argv[2]
new_mode_content = sys.argv[3]
new_mode = yaml.safe_load(new_mode_content) or {}

if is_zoo:
    mode_path = os.path.join(settings_dir, 'custom_modes.yaml')
    modes = []
    if os.path.exists(mode_path):
        try:
            with open(mode_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if data and isinstance(data, dict):
                    modes = data.get('customModes', [])
        except Exception:
            pass
    modes = [m for m in modes if isinstance(m, dict) and m.get('slug') not in ('orchestrator-crow', 'code-crow')]
    modes.extend(new_mode.get('customModes', []))
    with open(mode_path, 'w', encoding='utf-8') as f:
        yaml.dump({'customModes': modes}, f, allow_unicode=True, sort_keys=False)
    
    # cleanup old jsons
    for old_file in ['cline_custom_modes.json', 'custom_modes.json']:
        p = os.path.join(settings_dir, old_file)
        if os.path.exists(p):
            try:
                os.remove(p)
            except:
                pass
else:
    mode_path = os.path.join(settings_dir, 'cline_custom_modes.json')
    data = {}
    if os.path.exists(mode_path):
        try:
            with open(mode_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            pass
    modes = data.get('customModes', [])
    modes = [m for m in modes if isinstance(m, dict) and m.get('slug') not in ('orchestrator-crow', 'code-crow')]
    modes.extend(new_mode.get('customModes', []))
    data['customModes'] = modes
    with open(mode_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
"@
    try {
        $TempScript = New-TemporaryFile
        $PythonScript | Set-Content $TempScript -Encoding UTF8
        Start-Process -FilePath "python" -ArgumentList "`"$TempScript`"", "`"$SettingsDir`"", "`"$ZooSettings`"", "`"$CustomModeContent`"" -Wait -NoNewWindow
        Remove-Item $TempScript -Force
    } catch {
        Write-Host "  [Warning] Failed to merge custom mode safely." -ForegroundColor Yellow
    }
}
Write-StepDone

# Step 5: Start SSE server + auto-start registration
Write-Step-Header "5" "Starting Crow SSE server + auto-start" "step_5_start_server"
$BatPath = "$CrowDir\start_crow_sse.bat"

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
