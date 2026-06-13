# Crow Memory Windows Auto-Start Design (Revised)

## Version
- **Version:** 1.5.0
- **Date:** 2026-06-13
- **Status:** Revision after Ask-mode conditional approval
- **Scope:** Windows 10/11, standard user account (non-elevated), Zoo Code / Roo Code / Kimi Code clients

---

## 1. Technical Specification

### 1.1 Goals and Core Constraints

| Goal | Description |
|------|-------------|
| **G1** | Start `crow_mcp_server.py` automatically after user logon without requiring administrator privileges. |
| **G2** | Prevent multiple concurrent server instances (duplicate `python.exe` processes on ports 9020/9021). |
| **G3** | Ensure the Task Scheduler-based supervisor does not declare failure and spawn a second instance while the first instance is still completing its health check. |
| **G4** | Maximize the probability that an MCP client connecting immediately after VS Code auto-start finds a healthy Crow server, even under race conditions. |
| **G5** | Preserve idempotency and safe uninstall paths for all auto-start artifacts. |

**Core Constraints:**
- Must work on a **standard (non-admin) Windows user account**.
- Must **not** require UAC elevation during normal install/uninstall.
- Must **not** introduce new persistent network listeners or services beyond the existing `crow_mcp_server.py`.
- Must remain compatible with the existing dual-port architecture: SSE on `127.0.0.1:9020`, Streamable HTTP on `127.0.0.1:9021`.

---

### 1.2 Communication Layer Overview

```
+-------------------------------------------------------------+
|                        Windows Session                       |
|  +------------------------+    +-------------------------+  |
|  |   Windows Task Scheduler|    |   Startup Folder        |  |
|  |   (User-context, no UAC)|    |   (Fallback launcher)   |  |
|  |   - Trigger: At logon   |    |   - Runs 10 s delayed   |  |
|  |   - RestartInterval: 3m |    |   - Idempotent check    |  |
|  |   - AllowStartOnDemand  |    |                         |  |
|  +-----------+-------------+    +------------+------------+  |
|              |                              |               |
|              v                              v               |
|       +---------------------------------------------+       |
|       |        start_crow_sse.bat                    |       |
|       |  - Port-check dedupe (netstat)              |       |
|       |  - Stale lock/.crow_ready cleanup           |       |
|       |  - Launch python detached (hidden window)   |       |
|       |  - Health poll with bounded backoff         |       |
|       |  - Max 2 internal retries                   |       |
|       +--------------------+------------------------+       |
|                            |                                |
|                            v                                |
|       +---------------------------------------------+       |
|       |      crow_mcp_server.py --transport dual    |       |
|       |        Port 9020 (SSE) / 9021 (HTTP)        |       |
|       |        Writes memory/.crow_ready            |       |
|       +--------------------+------------------------+       |
|                            |                                |
|              +-------------+-------------+                  |
|              |                           |                  |
|              v                           v                  |
|    +--------------------+     +--------------------+        |
|    |   Zoo / Roo / VS    |     |   Kimi Code        |        |
|    |   Code MCP client   |     |   MCP client       |        |
|    |   (SSE @ 9020)      |     |   (HTTP @ 9021)    |        |
|    +--------------------+     +--------------------+        |
+-------------------------------------------------------------+
```

### 1.3 Type Definitions and Interfaces

All interfaces between the installer, the launcher, the server, and the IDE remain unchanged at the wire level. The revisions are limited to **registration strategy**, **timing parameters**, and **race-condition mitigation**.

#### 1.3.1 Server readiness signal

| Field | Value | File |
|-------|-------|------|
| `ready_file` | `memory/.crow_ready` | [`memory/.crow_ready`](memory/.crow_ready) |
| Content | ISO-8601 timestamp + listening ports | written by `crow_mcp_server.py` |

Example content:
```text
2026-06-13T06:40:00+09:00 SSE=9020 HTTP=9021 PID=12345
```

> **Note:** The ready file is a hint, not a guarantee. The MCP client must still tolerate transient HTTP connection failures and retry.

#### 1.3.2 Health endpoint

| Endpoint | Purpose |
|----------|---------|
| `GET http://127.0.0.1:9020/` | Lightweight liveness probe used by `start_crow_sse.bat` |
| `GET http://127.0.0.1:9021/` | Kimi Code HTTP transport health check |
| `GET http://127.0.0.1:9020/sse` | Zoo/Roo Code SSE endpoint |

---

## 2. Architecture Decisions

### 2.1 Design Patterns and Tech Stack

| Decision | Rationale |
|----------|-----------|
| **User-context Task Scheduler via `schtasks.exe /it /ru %USERNAME%`** | `Register-ScheduledTask` requires elevation because it defaults to the `LocalSystem`/root task folder. Using `schtasks.exe` with `/it` (interactive only) and `/ru %USERNAME%` creates a task that runs **only in the interactive session of the logged-on user**, which does **not** require administrator rights. |
| **Dual registration: Task Scheduler + Startup folder** | Task Scheduler is the primary, reliable trigger. The Startup folder acts as a fallback for portable or restricted environments where Task Scheduler creation may silently fail. The launcher itself is idempotent, so running twice is harmless. |
| **RestartInterval raised to 3 minutes** | The original 1-minute interval was shorter than the worst-case health-check duration. A 3-minute interval gives the first launch enough time to finish its two internal retries (worst-case ~150 s) plus margin, preventing duplicate instances. |
| **Bounded, shortened health check inside `start_crow_sse.bat`** | Cap the maximum wait to ~75 s and reduce `MAX_ATTEMPTS` so the launcher either succeeds or exits quickly. The Task Scheduler supervisor then waits the full 3 minutes before re-evaluating. |
| **MCP client retry is the final line of defense** | No OS-level trigger can perfectly synchronize with an arbitrary IDE startup time. The definitive fix is ensuring the MCP client configuration and the IDE tolerate transient connection errors and retry. |

### 2.2 Admin-Privilege-Free Task Registration

The revised installer uses **`schtasks.exe`** instead of the PowerShell `Register-ScheduledTask` cmdlet.

**Why `Register-ScheduledTask` fails without admin rights:**
- The cmdlet targets the root task folder (`\`) by default.
- Writing to the root task folder or registering a task with system-wide scope requires `SeCreateGlobalPrivilege`/elevated token.

**Why `schtasks.exe /it` succeeds:**
- `/it` = run only when the user is logged on.
- `/ru %USERNAME%` = run as the current interactive user, not `SYSTEM`.
- Windows allows a user to create a task that runs **in their own session** without elevation.

**Proposed command (run from `install.ps1` / `install.py`):**

```powershell
$TaskName = "CrowMemoryAuto"
$BatPath  = "$CrowDir\start_crow_sse.bat"
$UserName = $env:USERNAME

schtasks /create `
  /tn "$TaskName" `
  /tr "`"$BatPath`"" `
  /sc onlogon `
  /it `
  /ru "$UserName" `
  /f
```

**Constraints and validation:**
- `/f` overwrites any existing task of the same name, ensuring idempotency.
- If `schtasks` returns `ERROR: Access is denied`, the installer falls back to the Startup-folder-only registration and prints a warning.
- The task is stored under the user's task folder, visible in `Task Scheduler Library` without requiring admin approval.

### 2.3 Timing: RestartInterval and Health Check

#### 2.3.1 Original problem

- Health check worst-case duration: `2 + 2 + 3 + 5*17 = 92` s across 20 attempts.
- Plus two internal retries with a 5 s gap: `~100` s.
- Original `RestartInterval` = 60 s.
- Result: Task Scheduler considers the first run failed before it finishes.

#### 2.3.2 Revised parameters

| Parameter | Old Value | New Value | File |
|-----------|-----------|-----------|------|
| `RestartInterval` (Task Scheduler) | 1 minute | **3 minutes** | registered by installer |
| `RestartCount` | unspecified | **3** | registered by installer |
| `MAX_ATTEMPTS` in health poll | 20 | **12** | [`start_crow_sse.bat`](start_crow_sse.bat) |
| Backoff sequence | 2,2,3,5,5,... | 1,1,2,3,3,3,... | [`start_crow_sse.bat`](start_crow_sse.bat) |
| Internal retry count | 2 | **2** (unchanged) | [`start_crow_sse.bat`](start_crow_sse.bat) |

**New worst-case single-run duration:**
```
1 + 1 + 2 + 3*9 = 33 s   (12 attempts)
+ 5 s retry gap * 1       = 38 s first retry cycle
+ second retry cycle      = 76 s total worst case
```

This is well under the 3-minute `RestartInterval`, eliminating the collision.

### 2.4 Race Condition at Logon: Realistic Mitigation

No single Windows trigger can guarantee the server starts before every possible IDE launch. The revised design uses a **defense-in-depth** strategy:

```
Layer 1: Task Scheduler AtLogon  (earliest reliable OS trigger)
Layer 2: Startup folder launcher (10 s delayed, fallback)
Layer 3: Port-check dedupe inside start_crow_sse.bat (prevents duplicates)
Layer 4: .crow_ready file + health endpoint (server signals readiness)
Layer 5: MCP client retry configuration (client-side tolerance)
```

#### 2.4.1 Server-side race mitigation

1. **Port-check before launch:** `start_crow_sse.bat` checks `netstat` for port 9020/9021. If already listening, it exits silently.
2. **Single-instance lock file:** `memory/crow.bin.lock` is cleaned at startup and written by the server process. A second launcher checks the lock and exits.
3. **Ready file semantics:** `memory/.crow_ready` is written only after the HTTP server reports `is_ready=True`. It is removed on launcher exit if health check failed.

#### 2.4.2 Client-side race mitigation

The most reliable fix is **MCP client retry**. The installer should document and, where possible, configure:

- **Kimi Code:** HTTP transport reconnects are handled by the Kimi MCP client; no user action is typically required.
- **Roo Code / Cline:** The SSE client normally retries with exponential backoff. Verify `cline_mcp_settings.json` does not set `disableSSE: true`.
- **Zoo Code:** Same as Roo Code; uses SSE URL `http://127.0.0.1:9020/sse`.

If the client does **not** retry automatically, the fallback is:
- The user opens a new chat or waits ~10 s; the next tool call will succeed.
- The Startup-folder launcher provides a second start attempt ~10 s after logon.

### 2.5 Additional WARNING Handling (Recommended)

| # | Warning | Mitigation |
|---|---------|------------|
| 4 | `.crow_ready` vs actual HTTP response gap | Ready file is written by the server after `await server.start()` returns. The launcher still performs an HTTP `GET /` before declaring success. |
| 5 | Multi-user file/port conflicts | Server binds to `127.0.0.1` only. Lock/ready files are per-user because the project lives in the user's own directory (`%USERPROFILE%`). |
| 6 | Startup shortcut idempotency | Installer uses `/f` for Task Scheduler and overwrites the `.bat` shortcut in the Startup folder on every install. Uninstall removes both. |
| 7 | `sentence-transformers` first model download timeout | First install is interactive; installer pre-runs `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5')"` to warm the cache. |

---

## 3. Implementation Plan (Sub-tasks)

### Sub-task 1: Update installer PowerShell script (`install.ps1`)

**Exact file to modify:** [`install.ps1`](install.ps1)

**Prerequisites:**
- None beyond existing `install.ps1`.

**Implementation details:**
1. Replace the Startup-folder-only registration with a helper function `Register-CrowAutoStart`.
2. Attempt Task Scheduler registration using `schtasks.exe /create /sc onlogon /it /ru %USERNAME% /f`.
3. On success, also copy `start_crow_sse.bat` to the Startup folder as a fallback.
4. On failure (access denied), fall back to Startup-folder-only registration and print a warning.
5. Add an `Unregister-CrowAutoStart` function (or separate `uninstall.ps1`) that:
   - Runs `schtasks /delete /tn CrowMemoryAuto /f`.
   - Removes `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Crow_Memory_SSE.bat`.

**Acceptance criteria:**
- Running `install.ps1` as a standard user creates `CrowMemoryAuto` in Task Scheduler without UAC.
- Running the installer twice does not create duplicate tasks or shortcuts.
- The uninstaller removes both the task and the shortcut.

---

### Sub-task 2: Update installer Python script (`install.py`)

**Exact file to modify:** [`install.py`](install.py)

**Prerequisites:**
- Sub-task 1 design is finalized.

**Implementation details:**
1. Add a `register_autostart_windows()` function that mirrors the PowerShell logic.
2. Use `subprocess.run(["schtasks", "/create", ...])` on Windows.
3. Detect non-zero exit code and fall back to Startup-folder registration.
4. Ensure idempotency via `/f` and overwrite of the Startup shortcut.
5. Add an `unregister_autostart_windows()` function for symmetry.

**Acceptance criteria:**
- `python install.py` succeeds as a standard user.
- Both Task Scheduler and Startup folder artifacts are created/updated.

---

### Sub-task 3: Reduce health-check timeout in `start_crow_sse.bat`

**Exact file to modify:** [`start_crow_sse.bat`](start_crow_sse.bat)

**Prerequisites:**
- Sub-task 4 (Task Scheduler `RestartInterval`) is set to 3 minutes.

**Implementation details:**
1. Change `MAX_ATTEMPTS` from `20` to `12`.
2. Change the backoff schedule to `1s, 1s, 2s, 3s, 3s, 3s, ...`.
3. Keep the existing two internal retry cycles.
4. Ensure the batch still exits with code `0` on success and `1` on failure so Task Scheduler restart logic works correctly.

**Acceptance criteria:**
- Worst-case launcher duration is under 90 s.
- Success path completes within 10 s on a warm cache.

---

### Sub-task 4: Register Task Scheduler with 3-minute restart interval

**Exact files to modify:** [`install.ps1`](install.ps1), [`install.py`](install.py)

**Prerequisites:**
- Sub-task 3 reduces launcher duration to < 90 s.

**Implementation details:**
1. When registering the task, set `RestartInterval` to `PT3M` (3 minutes).
2. Set `RestartCount` to `3`.
3. Set `AllowStartOnDemand` to `true` so the user can manually trigger it from Task Scheduler without admin rights.

**PowerShell equivalent via XML task definition (if `schtasks` flags are insufficient):**
```xml
<Settings>
  <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
  <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
  <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
  <AllowHardTerminate>true</AllowHardTerminate>
  <StartWhenAvailable>true</StartWhenAvailable>
  <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
  <IdleSettings>
    <StopOnIdleEnd>false</StopOnIdleEnd>
    <RestartOnIdle>false</RestartOnIdle>
  </IdleSettings>
  <AllowStartOnDemand>true</AllowStartOnDemand>
  <Enabled>true</Enabled>
  <Hidden>false</Hidden>
  <RunOnlyIfIdle>false</RunOnlyIfIdle>
  <DisallowStartOnRemoteAppSession>false</DisallowStartOnRemoteAppSession>
  <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
  <WakeToRun>false</WakeToRun>
  <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  <Priority>7</Priority>
  <RestartOnFailure>
    <Interval>PT3M</Interval>
    <Count>3</Count>
  </RestartOnFailure>
</Settings>
```

**Acceptance criteria:**
- Task Scheduler shows `Restart every: 3 minutes` and `Attempt to restart up to: 3 times`.
- A simulated slow start (e.g., adding `timeout /t 70` to the batch) does not trigger a duplicate instance.

---

### Sub-task 5: Document MCP client retry expectations

**Exact file to create/modify:** [`README.md`](README.md) or [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md)

**Prerequisites:**
- None.

**Implementation details:**
1. Add a section "Auto-start race conditions and client retry".
2. State that Crow server may take up to 30 s after logon to be ready.
3. Confirm that Kimi/Roo/Zoo Code SSE/HTTP clients retry automatically.
4. Provide a manual workaround: wait 10 s or reload the window (`Ctrl+Shift+P` → `Developer: Reload Window`).

**Acceptance criteria:**
- Users can find the retry behavior and workarounds without reading code.

---

### Sub-task 6: (Optional but recommended) Add warm-up step for first model download

**Exact files to modify:** [`install.ps1`](install.ps1), [`install.py`](install.py)

**Prerequisites:**
- `requirements.txt` already includes `sentence-transformers`.

**Implementation details:**
1. After `pip install`, run a short Python snippet that imports `SentenceTransformer` and instantiates `SentenceTransformer('nomic-ai/nomic-embed-text-v1.5')`.
2. This downloads the model during the interactive install, preventing the first health check from timing out.

**Acceptance criteria:**
- First logon after install completes health check in < 10 s.

---

## 4. Summary of Critical Issue Resolutions

| CRITICAL | Issue | Resolution |
|----------|-------|------------|
| **#1** | Admin privilege required for `Register-ScheduledTask` | Use `schtasks.exe /create /it /ru %USERNAME%` to register a user-context task without elevation. |
| **#2** | RestartInterval 1 min < health check ~100 s | Raise `RestartInterval` to **3 minutes** and reduce launcher health check to **< 90 s worst case**. |
| **#3** | AtLogon timing race with VS Code auto-start | Defense in depth: Task Scheduler + Startup folder + port/lock dedupe + `.crow_ready` signal + MCP client retry tolerance. |

---

## 5. Testing Checklist for Code Implementation

- [ ] Install as standard user (no UAC prompt) → Task Scheduler `CrowMemoryAuto` exists.
- [ ] Re-run installer → no duplicate task or shortcut.
- [ ] Uninstall → task and shortcut removed.
- [ ] Simulate slow server start (`timeout /t 70` in batch) → Task Scheduler does not launch second instance before first finishes.
- [ ] Simulate server crash → Task Scheduler restarts after 3 minutes, up to 3 times.
- [ ] Leave port already listening → second launcher exits immediately (no duplicate).
- [ ] First install on clean machine → model warm-up prevents health-check timeout.

---

*End of revised design.*
