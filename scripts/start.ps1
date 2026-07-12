$ErrorActionPreference = 'Stop'
$Task = Get-ScheduledTask -TaskName 'Codex Gmail Bridge' -ErrorAction SilentlyContinue
if ($Task) { Start-ScheduledTask -TaskName 'Codex Gmail Bridge'; return }
$Root = Split-Path -Parent $PSScriptRoot
Start-Process -FilePath (Join-Path $Root '.venv\Scripts\gmail-codex-bridge.exe') -ArgumentList 'run' -WorkingDirectory $Root -WindowStyle Hidden

