# Gmail Codex Bridge

## Format des mails sortants

Les mails sortants sont envoyes en multipart avec une partie `text/html` rendue depuis le Markdown du rapport et une partie `text/plain` de secours. Les clients qui affichent le HTML profitent de la mise en forme; les autres conservent un contenu lisible.

Service local Windows reliant un fil Gmail à une conversation Codex, sans appel de modèle lors des scans vides.

## Etat

La version locale fonctionne avec Gmail et le serveur local de Codex (`codex app-server`). Le consentement OAuth Gmail initial et l'installation de la tâche planifiée Windows restent interactifs.

## Installation rapide

Prérequis : Python 3.11+, Node.js 18+, Codex Desktop installé et connecté (ou un exécutable `codex` compatible dans `PATH`, avec la commande `app-server`), projet Google Cloud avec Gmail API active et identifiants OAuth « application de bureau ». Le flux a été validé avec Codex CLI 0.144.3 ; `app-server` restant expérimental, une mise à jour future de Codex doit être suivie du test court décrit ci-dessous.

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

Pour une réponse produite automatiquement depuis Gmail, Codex doit lister les fichiers à envoyer sous une section `## Pièces jointes`, avec un lien Markdown local par fichier. Le bridge ignore les liens placés ailleurs dans la réponse et les URL distantes, puis joint les chemins locaux de cette section. Cette convention évite d'envoyer par mégarde un fichier seulement cité comme référence.

Un mail auquel l'utilisateur doit pouvoir répondre doit toujours passer par cette commande ou par le skill `gmail-codex-report`. Un envoi direct avec le connecteur Gmail ne crée aucune association avec la conversation Codex. Le bridge ne pourra donc pas savoir quelle conversation reprendre.

## Traitement des réponses Gmail

Le bridge extrait seulement le nouveau texte écrit au-dessus de l'historique cité par Gmail ou Outlook. Ce texte est transmis tel quel à Codex par `app-server`. Aucun préfixe du type « réponse reçue par email », aucune consigne technique et aucun historique du fil ne sont ajoutés à la conversation.

Le `gmail_thread_id` reste la route principale. Chaque mail contient aussi un code `CX-XXXXXX`. Si Gmail place une réponse dans un nouveau fil, ce code permet de retrouver la route et de récupérer un message déjà mis en quarantaine. Les mails sortants possèdent leur propre en-tête `Message-ID` afin de rendre le suivi du fil plus fiable.

Il ne faut pas réinjecter manuellement une réponse avec un outil d'envoi entre conversations Codex. L'application l'afficherait comme une délégation provenant d'une autre tâche. Le service utilise directement `thread/resume` puis `turn/start`, ce qui crée un véritable message utilisateur contenant uniquement le corps nettoyé du mail.

## Commencer une conversation depuis Gmail

Un nouveau fil envoyé à l'adresse du bridge crée une nouvelle tâche Codex. Le projet est choisi par l'adresse destinataire, à partir de `gmail_account` et du registre `[projects]` :

- l'adresse définie par `gmail_account` utilise `default_project` ;
- l'adresse avec un suffixe `+alias` utilise le projet portant cet alias dans `[projects]`.

Gmail remet les adresses avec suffixe `+...` dans la même boîte. Chaque fil Gmail correspond à une seule tâche Codex. Une fois la tâche créée, sa route et son projet sont conservés dans SQLite : toutes les réponses suivantes reprennent cette tâche, même si le corps du mail ne mentionne plus le projet.

La nouvelle tâche est créée dans le stockage Codex utilisé par l'application, puis nommée d'après le sujet du mail (ou `Conversation Gmail` si le sujet est vide). Elle apparaît ainsi dans la liste des tâches de Codex Desktop et peut être ouverte puis poursuivie depuis l'application comme une tâche ordinaire.

Un alias absent de `[projects]` est mis en quarantaine et ne lance pas Codex. Cela évite qu'un message soit exécuté dans le mauvais dépôt. Les clés de projet doivent être simples et stables, par exemple `mon-projet`, `analyse-2026` ou `sans-projet`.

```toml
default_project = "projet-principal"

[projects]
projet-principal = "C:\\chemin\\vers\\projet-principal"
second-projet = "C:\\chemin\\vers\\second-projet"
```

## Affichage dans Codex sous Windows

Le bridge passe par le protocole `app-server` du CLI fourni avec Codex Desktop. Contrairement à l'ancien runner `@openai/codex-sdk` fondé sur `codex exec`, une conversation commencée par email est créée comme une tâche nommée et visible dans l'application. Une réponse ultérieure reprend le même identifiant de tâche.

Le bridge lance un processus `app-server` local pour chaque tour puis le ferme lorsque la réponse finale est disponible. Il ne modifie aucun index interne de Codex et ne pilote pas l'interface graphique. Si une tâche déjà ouverte ne montre pas immédiatement le dernier tour, la rouvrir suffit à relire l'état persistant.

Le runner Node utilise uniquement la bibliothèque standard de Node.js : le projet n'a plus de dépendance npm à `@openai/codex-sdk` et l'installation ne lance plus `npm install`.

## Fonctionnement et garanties

- SQLite assure le routage, la file FIFO, la quarantaine et l'idempotence par identifiant Gmail.
- Un seul tour est exécuté à la fois par conversation. Des conversations différentes peuvent progresser en parallèle.
- Un message sans route connue crée une tâche seulement si son adresse correspond à un projet configuré ; sinon il est mis en quarantaine.
- Après une coupure, la requête Gmail retrouve les messages non traités, puis SQLite les déduplique.
- Un envoi dont l'issue est incertaine passe à l'état `uncertain` et n'est jamais retenté automatiquement.
- Les journaux contiennent uniquement les identifiants, les états et les erreurs, jamais le corps complet des emails.

Voir [docs/INSTALLATION.md](docs/INSTALLATION.md) et [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
node --check scripts\codex-runner.mjs
codex app-server --help
```

Aucun test n'accède à Gmail ni à Codex.
