# Gmail Codex Bridge

Pour les notifications par email explicitement autorisees, utiliser `stan.dekerle@gmail.com`. Ne jamais envoyer de mail sans confirmation explicite, sauf dans le cadre de l'automatisation Gmail Codex Bridge deja autorisee.

Utiliser le skill Humanizer pour rediger les emails. Si un envoi autorise bloque, enregistrer le message comme brouillon Gmail, puis utiliser `gmail-send-approved-drafts` pour l'envoyer.

Tout email envoye depuis une conversation de ce projet et susceptible de recevoir une reponse doit passer par le skill `gmail-codex-report` et la commande `gmail-codex-bridge publish`. Ne pas utiliser directement le connecteur Gmail dans ce cas, car il ne cree pas la route entre le fil Gmail et la conversation Codex.

Une reponse Gmail doit etre reprise par le service via le SDK Codex. Ne jamais la reinjecter avec un outil d'envoi entre conversations : cela apparait comme une delegation et modifie le point de vue de l'agent.
