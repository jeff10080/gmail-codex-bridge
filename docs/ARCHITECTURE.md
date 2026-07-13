# Architecture

Le processus Python effectue un `messages.list` filtre toutes les 60 secondes. Un scan vide s'arrete la : aucun processus Codex, aucun appel de modele et aucun token. Chaque message est ensuite lu, son expediteur normalise est compare a l'adresse autorisee, puis son identifiant immutable est insere dans SQLite.

Une route associe un `gmail_thread_id` a un unique `codex_thread_id`, un projet et un code `CX-XXXXXX`. Avec route, une file FIFO par conversation est drainee sous verrou; plusieurs verrous peuvent fonctionner en parallele, dans la limite configuree.

Sans route, le destinataire determine le projet. L'adresse Gmail nue selectionne `default_project`; un suffixe `+alias` selectionne la cle correspondante dans `[projects]`. Si le projet existe, le runner appelle `thread/start` dans son repertoire et nomme la tache d'apres le sujet avec `thread/name/set`. Apres la fin reussie du premier tour, le service enregistre la nouvelle route avant d'envoyer la reponse Gmail. Si le projet est inconnu, le message est place en quarantaine et Codex n'est pas lance.

Python lance `scripts/codex-runner.mjs`, qui demarre l'executable Codex Desktop (ou `codex` trouve dans `PATH`) avec `app-server --stdio`. Le runner initialise le protocole JSONL, appelle `thread/start` ou `thread/resume`, puis `turn/start`. Il attend `turn/completed`, retient le message agent final et renvoie ce resultat avec l'identifiant de la tache au service en JSONL.

Les taches ainsi creees utilisent le stockage de conversations de Codex et sont nommees : elles sont donc visibles et ouvrables dans Codex Desktop, contrairement aux conversations sans titre creees par l'ancien runner SDK. Ce comportement a ete valide avec Codex CLI 0.144.3. Le processus `app-server` est local et limite a un tour; il est ferme apres la reponse. Le runner n'utilise que les modules natifs de Node.js et ne depend plus de `@openai/codex-sdk`.

Pour repondre dans Gmail, le service fournit le `threadId`, conserve le sujet, et pose `In-Reply-To` et `References`. Un envoi est inscrit `sending` avant l'appel. Toute exception pendant l'appel le marque `uncertain`: aucun nouvel essai automatique ne risque alors de doubler un email dont l'envoi a peut-etre reussi.

Le jeton OAuth est stocke hors depot dans `token.dpapi`, chiffre par Windows DPAPI pour l'utilisateur courant. Il n'est donc reutilisable ni par un autre compte Windows ni sur une autre machine.
