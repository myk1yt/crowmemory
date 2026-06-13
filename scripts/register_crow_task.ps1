# Crow Memory — Register Task Scheduler auto-start (admin-free)
param(
    [string]$CrowDir = $PSScriptRoot + "\.."
)

$BatPath = Join-Path $CrowDir "start_crow_sse.bat"
$TaskName = "CrowMemoryAuto"

# Build XML
$TaskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Crow Memory SSE MCP Server - Auto-start at user logon</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT30S</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$env:USERNAME</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT3M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>cmd.exe</Command>
      <Arguments>/c "$BatPath"</Arguments>
      <WorkingDirectory>$CrowDir</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

# Write XML as UTF-16 LE
$TempXml = Join-Path $env:TEMP "crow_task_$PID.xml"
[System.IO.File]::WriteAllText($TempXml, $TaskXml, [System.Text.Encoding]::Unicode)

Write-Host "Registering Task Scheduler: $TaskName ..."
$result = & schtasks.exe /create /tn $TaskName /xml $TempXml /f 2>&1
$exitCode = $LASTEXITCODE

Remove-Item $TempXml -Force -ErrorAction SilentlyContinue

if ($exitCode -eq 0) {
    Write-Host "[OK] Task Scheduler registered: $TaskName"
    Write-Host "  - Trigger: AtLogon (30s delay)"
    Write-Host "  - RestartOnFailure: PT3M, Count=3"
    Write-Host "  - Command: $BatPath"
    
    # Also clean old Startup folder entry
    $StartupDir = [Environment]::GetFolderPath("Startup")
    $OldBat = Join-Path $StartupDir "Crow_Memory_SSE.bat"
    if (Test-Path $OldBat) {
        Remove-Item $OldBat -Force
        Write-Host "[Migration] Removed old Startup folder entry."
    }
} else {
    Write-Host "[FAIL] schtasks exit code: $exitCode"
    Write-Host "Output: $result"
    exit 1
}
