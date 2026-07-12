[CmdletBinding(SupportsShouldProcess, ConfirmImpact='High')]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Exe = Join-Path $Root '.venv\Scripts\gmail-codex-bridge.exe'
if (-not (Test-Path $Exe)) { throw "Installez d'abord le projet avec scripts\install.ps1" }
if ($PSCmdlet.ShouldProcess('Codex Gmail Bridge', 'Installer la tache planifiee a la connexion')) {
  $Action = New-ScheduledTaskAction -Execute $Exe -Argument 'run' -WorkingDirectory $Root
  $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $Settings = New-ScheduledTaskSettingsSet -RestartCount 100 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
  Register-ScheduledTask -TaskName 'Codex Gmail Bridge' -Action $Action -Trigger $Trigger -Settings $Settings -Description 'Relais local Gmail vers Codex' -Force | Out-Null
}

