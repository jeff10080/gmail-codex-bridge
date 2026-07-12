$Task = Get-ScheduledTask -TaskName 'Codex Gmail Bridge' -ErrorAction SilentlyContinue
if ($Task) { Stop-ScheduledTask -TaskName 'Codex Gmail Bridge'; return }
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*gmail-codex-bridge*run*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

