# Gmail Codex Bridge

Service local Windows reliant un fil Gmail à une conversation Codex, sans appel de modèle lors des scans vides.

## Etat

La version locale fonctionne avec Gmail et le SDK Codex. Le consentement OAuth Gmail initial et l'installation de la tâche planifiée Windows restent interactifs.

## Installation rapide

Prérequis : Python 3.11+, Node.js 18+, Codex CLI connecte, projet Google Cloud avec Gmail API active et identifiants OAuth « application de bureau ».

```powershell
.\scripts\install.ps1
Copy-Item config.example.toml "$env:LOCALAPPDATA\CodexGmailBridge\config.toml"
# Placer credentials.json dans %LOCALAPPDATA%\CodexGmailBridge, puis :
.\.venv\Scripts\gmail-codex-bridge.exe auth
.\scripts\start.ps1
```

Le service scrute Gmail toutes les 60 secondes. Il accepte uniquement les messages provenant exactement de l'adresse autorisée. Les données, journaux, jetons et pièces jointes restent sous `%LOCALAPPDATA%\CodexGmailBridge`.

## Publier un premier rapport

```powershell
.\.venv\Scripts\gmail-codex-bridge.exe publish --codex-thread-id THREAD_ID --subject "Rapport Codex" --body-file rapport.md --attachment resultat.pdf
```

Le premier envoi crée le fil Gmail et enregistre son `gmail_thread_id`. Les suivants réutilisent ce fil. Ne passez que les pièces jointes explicitement citées dans la réponse finale. Une pièce absente est signalée dans le mail sans bloquer l'envoi.

Un mail auquel l'utilisateur doit pouvoir répondre doit toujours passer par cette commande ou par le skill `gmail-codex-report`. Un envoi direct avec le connecteur Gmail ne crée aucune association avec la conversation Codex. Le bridge ne pourra donc pas savoir quelle conversation reprendre.

## Traitement des réponses Gmail

Le bridge extrait seulement le nouveau texte écrit au-dessus de l'historique cité par Gmail ou Outlook. Ce texte est transmis tel quel au SDK Codex. Aucun préfixe du type « réponse reçue par email », aucune consigne technique et aucun historique du fil ne sont ajoutés à la conversation.

Le `gmail_thread_id` reste la route principale. Chaque mail contient aussi un code `CX-XXXXXX`. Si Gmail place une réponse dans un nouveau fil, ce code permet de retrouver la route et de récupérer un message déjà mis en quarantaine. Les mails sortants possèdent leur propre en-tête `Message-ID` afin de rendre le suivi du fil plus fiable.

Il ne faut pas réinjecter manuellement une réponse avec un outil d'envoi entre conversations Codex. L'application l'afficherait comme une délégation provenant d'une autre tâche. Le service utilise directement `resumeThread`, ce qui crée un véritable message utilisateur contenant uniquement le corps nettoyé du mail.

## Limite d'affichage dans Codex sous Windows

Une reprise effectuée avec `@openai/codex-sdk` est bien enregistrée dans la conversation et la réponse de l'agent est envoyée dans le fil Gmail. Toutefois, l'application Codex déjà ouverte ne détecte pas toujours le nouveau tour immédiatement. Il faut alors rouvrir la tâche ou recharger l'application pour le voir.

Cette limite concerne uniquement le rafraîchissement de l'interface. Le message n'est pas perdu et son contenu n'est pas modifié. Le SDK lance actuellement un processus `codex exec` séparé de l'application. Sous Windows, aucune API publique ne permet au bridge de rejoindre le serveur de l'application ou de lui demander de recharger une conversation. Modifier les index internes de Codex, simuler une touche de rafraîchissement ou redémarrer automatiquement l'application serait trop fragile.

La solution prévue est de passer à un client `app-server` persistant lorsque Codex proposera un point de connexion partagé et documenté sous Windows. Le runner SDK actuel restera alors disponible comme solution de repli.

## Fonctionnement et garanties

- SQLite assure le routage, la file FIFO, la quarantaine et l'idempotence par identifiant Gmail.
- Un seul tour est exécuté à la fois par conversation. Des conversations différentes peuvent progresser en parallèle.
- Un message sans route connue est mis en quarantaine et ne lance jamais Codex.
- Après une coupure, la requête Gmail retrouve les messages non traités, puis SQLite les déduplique.
- Un envoi dont l'issue est incertaine passe à l'état `uncertain` et n'est jamais retenté automatiquement.
- Les journaux contiennent uniquement les identifiants, les états et les erreurs, jamais le corps complet des emails.

Voir [docs/INSTALLATION.md](docs/INSTALLATION.md) et [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Aucun test n'accède à Gmail ni à Codex.
