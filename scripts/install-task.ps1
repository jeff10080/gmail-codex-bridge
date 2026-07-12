[CmdletBinding(SupportsShouldProcess, ConfirmImpact='High')]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Pythonw = Join-Path $Root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $Pythonw)) { throw "Installez d'abord le projet avec scripts\install.ps1" }
if ($PSCmdlet.ShouldProcess('Codex Gmail Bridge', 'Installer la tache planifiee a la connexion')) {
  $Action = New-ScheduledTaskAction -Execute $Pythonw -Argument '-m gmail_codex_bridge.cli run' -WorkingDirectory $Root
  $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $Settings = New-ScheduledTaskSettingsSet -RestartCount 100 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
  Register-ScheduledTask -TaskName 'Codex Gmail Bridge' -Action $Action -Trigger $Trigger -Settings $Settings -Description 'Relais local Gmail vers Codex' -Force | Out-Null
}
