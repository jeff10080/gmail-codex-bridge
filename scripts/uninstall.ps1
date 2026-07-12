[CmdletBinding(SupportsShouldProcess, ConfirmImpact='High')]
param([switch]$DeletePrivateData)
$Task = Get-ScheduledTask -TaskName 'Codex Gmail Bridge' -ErrorAction SilentlyContinue
if ($Task -and $PSCmdlet.ShouldProcess('Codex Gmail Bridge', 'Supprimer la tache planifiee')) {
  Unregister-ScheduledTask -TaskName 'Codex Gmail Bridge' -Confirm:$false
}
if ($DeletePrivateData) {
  $Data = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'CodexGmailBridge'))
  $Expected = [System.IO.Path]::GetFullPath("$env:LOCALAPPDATA\CodexGmailBridge")
  if ($Data -ne $Expected) { throw 'Chemin de donnees inattendu; suppression annulee.' }
  if ($PSCmdlet.ShouldProcess($Data, 'Supprimer base, jetons, journaux et pieces jointes')) { Remove-Item -LiteralPath $Data -Recurse -Force }
}

