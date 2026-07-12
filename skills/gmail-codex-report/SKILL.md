---
name: gmail-codex-report
description: Publie automatiquement la reponse finale ou son rapport distinct dans le fil Gmail associe a la conversation Codex.
---

# Gmail Codex Report

Quand une automatisation autorise l'envoi de fin de tour, publier sans nouvelle confirmation vers le destinataire defini dans la configuration privee avec `gmail-codex-bridge publish`.

1. S'il existe un rapport distinct, envoyer seulement ce rapport; sinon envoyer toute la reponse finale.
2. Utiliser le thread ID Codex courant.
3. Ne joindre que les fichiers explicitement cites ou lies dans la reponse finale. Ne jamais parcourir le projet pour en deviner.
4. Passer tous les chemins explicites avec `--attachment`, y compris s'ils sont absents : le bridge signalera l'absence sans bloquer le rapport.
5. Humaniser seulement si necessaire, sans modifier les faits.

Commande :

```powershell
gmail-codex-bridge publish --codex-thread-id THREAD_ID --subject "Rapport Codex" --body-file PATH --attachment PATH
```
