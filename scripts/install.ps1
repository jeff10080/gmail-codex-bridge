[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Data = Join-Path $env:LOCALAPPDATA 'CodexGmailBridge'
New-Item -ItemType Directory -Force -Path $Data, (Join-Path $Data 'logs'), (Join-Path $Data 'attachments') | Out-Null
if (-not (Test-Path (Join-Path $Root '.venv'))) { python -m venv (Join-Path $Root '.venv') }
& (Join-Path $Root '.venv\Scripts\python.exe') -m pip install -e "$Root[dev]"
Push-Location $Root
try { npm install } finally { Pop-Location }
if (-not (Test-Path (Join-Path $Data 'config.toml'))) {
  Copy-Item (Join-Path $Root 'config.example.toml') (Join-Path $Data 'config.toml')
}
Write-Host "Installation terminee. Configurez $Data\config.toml puis lancez la commande auth."
Write-Host "La tache planifiee n'a pas ete installee. Utilisez scripts\install-task.ps1 apres accord explicite."

