# Environment Feedback Report
## Mode: orchestrator-crow
## Date: 260901
## Issue: Crow Memory MCP server up but exposes ZERO tools mid-session

### Problem Description
- What happened: At session start (23:24), `crow_recall` (domain=life and domain=code) failed twice with Streamable HTTP 500 errors ("Session terminated before the request completed" / "Internal Server Error"). At 23:31, a retry returned `unknown_tool` with `available_tools: []` — server responds on port 9021 but exposes no tools.
- When it occurred: 2026-09-01 23:24 ~ 23:31 (entire session so far)
- Error message: `{"code":500,...,"Session terminated before the request completed"}` then `Tool does not exist on server`, `available_tools: []`

### Root Cause Analysis
- Server process is listening on 9021 (HTTP layer healthy) but the MCP tool registration layer is dead or a stale/incompatible server instance is serving. Past feedback (260830) documented the same pattern: stale manually-launched server process with healthy HTTP app but broken MCP handshake. The 260830 fix (taskkill stale PID + health check path update) may have regressed, or a different instance is now stale.
- Impact on work: VP could not perform CP-1 (user philosophy recall) before P3 delegation. Proceeded using in-session context from prior sessions only.

### Workaround/Solution
- Not yet resolved in this session. Recommended: check `netstat -ano | findstr 9021` / `9020` for stacked server processes, taskkill stale PIDs, restart via `start_crow_sse.bat`, then verify with `scripts/probe_mcp_handshake.py` (tools/list should return tools).

### Ideal Environment
- Launcher should self-guard against stacked instances (PID-file based single-instance lock), and health check should verify tools/list count > 0, not just HTTP 200 on /health.

### Additional Notes
- This is the third+ occurrence of the "stale server process" family of failures (see 260830 feedback). Root fix belongs in launcher/startup tooling, not per-session manual cleanup.