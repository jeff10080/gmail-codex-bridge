---
name: gmail-codex-report
description: Envoie par email depuis une conversation Codex en passant obligatoirement par Gmail Codex Bridge afin que les reponses Gmail reviennent comme de vrais messages utilisateur dans la meme conversation.
---

# Gmail Codex Report

Pour tout email lance depuis une conversation de ce projet et susceptible de recevoir une reponse, utiliser `gmail-codex-bridge publish`. Ne pas utiliser directement le connecteur Gmail : il n'enregistre pas l'association entre le fil Gmail et la conversation Codex.

Quand une automatisation autorise l'envoi de fin de tour, publier sans nouvelle confirmation vers le destinataire defini dans la configuration privee.

1. S'il existe un rapport distinct, envoyer seulement ce rapport; sinon envoyer toute la reponse finale.
2. Utiliser le thread ID Codex courant.
3. Pour joindre des fichiers a une reponse produite depuis Gmail, ajouter une section Markdown `## Pieces jointes` dans la reponse finale et y lister chaque fichier avec un lien local explicite. Le bridge extrait uniquement les liens de cette section. Ne jamais parcourir le projet pour en deviner.
4. Passer tous les chemins explicites avec `--attachment`, y compris s'ils sont absents : le bridge signalera l'absence sans bloquer le rapport.
5. Humaniser seulement si necessaire, sans modifier les faits.
6. Fournir le corps en Markdown ou en texte structure. Le bridge genere automatiquement une partie `text/html` et une partie `text/plain` de secours; ne pas convertir manuellement le rapport en HTML.
7. Ne jamais reinjecter une reponse Gmail avec un outil d'envoi entre conversations. Le service reprend lui-meme la conversation avec le SDK Codex et transmet uniquement le nouveau texte de l'utilisateur.

Commande :

```powershell
gmail-codex-bridge publish --codex-thread-id THREAD_ID --subject "Rapport Codex" --body-file PATH --attachment PATH
```
