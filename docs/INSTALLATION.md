# Installation Windows

1. Creer un projet Google Cloud, activer Gmail API, configurer l'ecran de consentement et telecharger un client OAuth de type application de bureau.
2. Executer `scripts\install.ps1`.
3. Copier le fichier OAuth sous `%LOCALAPPDATA%\CodexGmailBridge\credentials.json`.
4. Adapter `%LOCALAPPDATA%\CodexGmailBridge\config.toml`, notamment `codex_working_directory`.
5. Executer `.\.venv\Scripts\gmail-codex-bridge.exe auth`. Cette etape ouvre le navigateur et exige votre consentement.
6. Faire un test local avec `gmail-codex-bridge publish` et une conversation Codex temporaire.
7. Apres validation explicite, executer `scripts\install-task.ps1 -Confirm`. La tache est cachee, demarre a la connexion et redemarre une minute apres un echec.

Le scope OAuth est `gmail.modify`, necessaire pour lire les corps entrants et envoyer les reponses. Le scope global `mail.google.com` n'est pas demande.

Pour arreter : `scripts\stop.ps1`. Pour desinstaller la tache sans supprimer les donnees : `scripts\uninstall.ps1`. Ajouter `-DeletePrivateData` uniquement si la suppression de la base, des jetons, journaux et pieces jointes est voulue.

