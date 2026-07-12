# Architecture

Le processus Python effectue un `messages.list` filtre toutes les 60 secondes. Un scan vide s'arrete la : aucun processus Codex, aucun appel de modele et aucun token. Chaque message est ensuite lu, son expediteur normalise est compare a l'adresse autorisee, puis son identifiant immutable est insere dans SQLite.

Une route associe un `gmail_thread_id` a un unique `codex_thread_id` et a un code `CX-XXXXXX`. Sans route, le message est place en quarantaine. Avec route, une file FIFO par conversation est drainee sous verrou; plusieurs verrous peuvent fonctionner en parallele, dans la limite configuree.

Python lance `scripts/codex-runner.mjs`, qui utilise le SDK officiel `@openai/codex-sdk`, appelle `resumeThread(threadId)` et execute `thread.run(prompt)`. Le resultat final est renvoye au service en JSONL.

Pour repondre dans Gmail, le service fournit le `threadId`, conserve le sujet, et pose `In-Reply-To` et `References`. Un envoi est inscrit `sending` avant l'appel. Toute exception pendant l'appel le marque `uncertain`: aucun nouvel essai automatique ne risque alors de doubler un email dont l'envoi a peut-etre reussi.

Le jeton OAuth est stocke hors depot dans `token.dpapi`, chiffre par Windows DPAPI pour l'utilisateur courant. Il n'est donc reutilisable ni par un autre compte Windows ni sur une autre machine.
