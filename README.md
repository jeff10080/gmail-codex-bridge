# Gmail Codex Bridge

Service local Windows reliant un fil Gmail a une conversation Codex, sans appel de modele lors des scans vides.

## Etat

La version locale est implementee et testable sans acces Gmail ni Codex reels. Deux validations restent volontairement interactives : le consentement OAuth Gmail initial et l'installation de la tache planifiee Windows.

## Installation rapide

Prérequis : Python 3.11+, Node.js 18+, Codex CLI connecte, projet Google Cloud avec Gmail API active et identifiants OAuth « application de bureau ».

```powershell
.\scripts\install.ps1
Copy-Item config.example.toml "$env:LOCALAPPDATA\CodexGmailBridge\config.toml"
# Placer credentials.json dans %LOCALAPPDATA%\CodexGmailBridge, puis :
.\.venv\Scripts\gmail-codex-bridge.exe auth
.\scripts\start.ps1
```

Le service scrute Gmail toutes les 60 secondes. Seuls les messages provenant exactement de l'adresse autorisee sont acceptes. Les donnees, journaux, jetons et pieces jointes restent sous `%LOCALAPPDATA%\CodexGmailBridge`.

## Publier un premier rapport

```powershell
.\.venv\Scripts\gmail-codex-bridge.exe publish --codex-thread-id THREAD_ID --subject "Rapport Codex" --body-file rapport.md --attachment resultat.pdf
```

Le premier envoi cree le fil Gmail et enregistre son `gmail_thread_id`; les suivants reutilisent ce fil. Ne passez que les pieces jointes explicitement citees dans la reponse finale. Une piece absente est signalee dans le mail, sans bloquer l'envoi.

## Fonctionnement et garanties

- SQLite assure routage, file FIFO, quarantaine et idempotence par identifiant Gmail.
- Un seul tour est execute a la fois par conversation; des conversations differentes peuvent progresser en parallele.
- Un message sans routage connu est mis en quarantaine et ne lance jamais Codex.
- Apres une coupure, les messages non traites sont retrouves par requete Gmail puis dedupliques.
- Un envoi dont l'issue est incertaine passe a l'etat `uncertain` et n'est jamais retente automatiquement.
- Les journaux contiennent uniquement identifiants, etats et erreurs, jamais le corps complet.

Voir [docs/INSTALLATION.md](docs/INSTALLATION.md) et [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Aucun test n'accede a Gmail ni a Codex.
