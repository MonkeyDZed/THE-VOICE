# PROJET VOICEPROMPT — Dictée vocale pour OpenCode Desktop

## 0. POSITIONNEMENT (PRIME SUR TOUT LE RESTE)

VoicePrompt est un outil personnel, développé exclusivement pour mon usage sur mon PC Windows. Ce n'est PAS un produit commercial, un SaaS ou une application grand public.

Son seul objectif : me permettre de parler naturellement à OpenCode Desktop au lieu de taper mes prompts, car cette fonction n'existe pas dans mon workflow.

Règles :
- Simplicité avant extensibilité. Pas d'architecture inutile.
- Pas de multi-utilisateurs, comptes, licences, backend dédié, base de données, multiplateforme, mises à jour automatiques, tests de charge.
- Pas de PySide6, pas de page de paramètres : un fichier `.env` suffit.
- Pas de DPAPI ni de Credential Manager : la clé API reste dans le `.env`.
- 1 à 3 fichiers Python maximum, pas de module supplémentaire sans justification concrète.
- Lancement depuis Python, compatible `pythonw.exe` via un raccourci Windows (sans terminal). Un EXE portable est une étape finale facultative, uniquement si je le demande.
- **Si une fonctionnalité n'est pas listée dans ce document, ne l'ajoute pas. Demande-moi d'abord.**

## 1. CONTEXTE RÉEL DE LA MACHINE

PC portable Windows 11. Sur CE PC :
- FreeLLMAPI Desktop est installé mais PAS configuré : aucun fournisseur STT, aucune clé API, aucun modèle STT sélectionné.
- OpenCode Desktop est installé ou à vérifier.

Sur mon AUTRE PC, FreeLLMAPI est déjà configuré. Ne présume rien de cette configuration, ne la copie pas, ne la modifie pas. Pars de zéro ici.

## 2. FONCTIONNEMENT CIBLE

1. OpenCode est ouvert et au premier plan.
2. J'appuie sur le raccourci global : l'enregistrement démarre (bip court).
3. Je parle en français.
4. J'appuie à nouveau : l'enregistrement s'arrête (bip), l'audio est envoyé au STT.
5. Le texte transcrit est collé dans la fenêtre OpenCode qui était active au moment où j'ai lancé l'enregistrement.
6. Je relis et j'envoie moi-même. **Ne jamais simuler la touche Entrée.** Les seules touches simulées sont Ctrl+V pour le collage.

## 3. CRITÈRES DE RÉUSSITE (VÉRIFIABLES)

- **Latence** : objectif de moins de 3 secondes entre l'arrêt de l'enregistrement et le texte, pour une dictée de 10 secondes. C'est un objectif mesuré, pas une garantie. La précision du français prime sur la vitesse.
- **Français technique fidèle** : OpenCode, GLM, Claude, Gemini, DeepSeek, Python, TypeScript, JavaScript, React, Next.js, Prisma, Supabase, PostgreSQL, SQLite, API, MCP, GitHub, Git, PowerShell. Aucune reformulation : le sens et les mots restent ceux que j'ai dits.
- **Collage fiable** : le texte arrive dans OpenCode, jamais dans une autre fenêtre.
- **Aucune perte** : une transcription n'est jamais perdue, même si le collage échoue.
- **Erreurs** : si la transcription échoue (réseau, quota, HTTP), l'audio reste disponible pour un nouvel essai et un message clair s'affiche (pas de stacktrace).
- **Discrétion** : VoicePrompt ne vole jamais le focus d'OpenCode.
- **Clé API** : dans un `.env` exclu de Git, jamais écrite dans les logs.

## 4. RÈGLE ABSOLUE : COMMENCER PAR FREELLMAPI

Ne développe rien avant que la transcription fonctionne par HTTP.

### Phase 0 — Audit sur ce PC
Identifier : version de FreeLLMAPI, chemin d'installation, processus actif, port local (ne suppose pas 3001), dashboard, endpoints, documentation OpenAPI, méthode d'authentification, dossier de configuration. Ne modifie pas les fichiers internes de FreeLLMAPI.

Relever aussi, pour OpenCode Desktop, **le nom réel de l'exécutable** de son processus et le titre ou la classe de sa fenêtre principale. Ne pas supposer de nom : mesurer sur la machine. Noter si plusieurs instances ou plusieurs processus coexistent. Ces valeurs vont dans `.env` (`TARGET_PROCESS=`).

### Phase 1 — Fournisseur STT gratuit
Examiner dans le catalogue FreeLLMAPI : Groq (Whisper Large V3 Turbo, Whisper Large V3), Mistral (Voxtral Mini Transcribe), Cloudflare (Deepgram Nova-3 ou autre STT réellement proposé). Pour chacun, vérifier : existence réelle dans la version installée, gratuité réelle (les crédits d'essai ne sont pas du gratuit durable), quotas, limites de taille audio, support du français, endpoint de transcription, authentification, et **formats audio acceptés** (en particulier si le format natif du micro est accepté ou si une conversion en 16 kHz est exigée).

Règles :
- Ne jamais inventer ni enregistrer de clé fictive, ne jamais acheter de crédit, ne jamais activer de facturation.
- Ne pas confondre STT et TTS : `/v1/audio/speech` n'est PAS un endpoint de transcription. Tester `/v1/audio/transcriptions` uniquement s'il est réellement exposé.
- Si une action humaine est nécessaire (créer un compte, obtenir ou saisir une clé), arrête-toi uniquement à cette étape, explique précisément quoi faire (lien officiel du fournisseur, où trouver la clé, où la saisir dans FreeLLMAPI Desktop), puis reprends après mon retour.
- **Plan B** : si FreeLLMAPI n'expose aucun STT gratuit fonctionnel, présente-moi les alternatives avant de choisir. Option à examiner en premier : Groq en appel direct (Whisper Large V3 Turbo), à condition de vérifier gratuité et quotas.
- Jamais de basculement automatique vers un fournisseur dont la gratuité n'a pas été vérifiée.

### Validation technique obligatoire
Identifier le Base URL réel, la clé, l'identifiant exact du modèle et l'endpoint STT. Envoyer un fichier audio français de test (fourni ou enregistré par moi), vérifier le code HTTP, le texte retourné, le format audio accepté, et mesurer le temps de réponse. Documenter en un seul fichier court : `docs/STT_SETUP.md` (configuration retenue, URL, modèle, format audio accepté, quotas connus).

## 5. APPLICATION (APRÈS VALIDATION DU STT)

Libs : `sounddevice`, `soundfile`, `requests` (ou `httpx`), `pystray`, Tkinter (déjà fourni avec Python), API Win32 (`pywin32` ou `ctypes`).

### Raccourci global
Combinaison peu courante, configurable dans `.env`, par défaut `Ctrl+Alt+Space` (vérifier qu'elle n'entre pas en conflit avec OpenCode ni avec mon environnement). Mode bascule : une pression démarre, la suivante arrête. Utiliser `RegisterHotKey` (Win32).

### Audio
- Enregistrer dans le format natif compatible du micro Windows par défaut, mono, WAV. Ne convertir en 16 kHz que si la phase 1 a montré que le fournisseur l'exige. Ne pas supposer que tous les micros supportent le 16 kHz.
- Durée maximale de sécurité (ex. 120 s).
- **Contrôle RMS** : seuil réglable dans `.env`, valeur loggée. Rejeter uniquement les enregistrements vides ou quasi silencieux, pas les voix faibles. Rejeter aussi les transcriptions manifestement fantômes (Whisper invente parfois du texte sur le silence).
- Conserver le fichier audio temporaire en cas d'erreur STT (nouvel essai possible), le supprimer après transcription réussie.
- Contexte lexical : transmettre la liste de termes de la section 3 via le paramètre prévu par l'API (prompt initial) si disponible. Tester qu'il améliore vraiment le résultat sans fausser la transcription.

### Cible OpenCode et injection
- Au début de chaque enregistrement : mémoriser le HWND de la fenêtre active, **le PID qui lui est associé** (`GetWindowThreadProcessId`), et le nom de l'exécutable de ce processus. Vérifier qu'il correspond à `TARGET_PROCESS` (valeur relevée en phase 0, jamais un nom supposé). Plusieurs instances d'OpenCode peuvent exister : le couple HWND + PID fait foi. Si la fenêtre active n'est pas OpenCode, afficher un avertissement discret mais **autoriser** l'enregistrement.
- Au moment de l'injection : vérifier que le HWND mémorisé existe toujours, qu'il appartient toujours au même PID et au même exécutable. Gérer la restriction Windows sur `SetForegroundWindow`.
- **Ne JAMAIS coller dans une fenêtre différente.** Si l'injection est impossible, conserver la transcription et proposer Copier.
- Le mode `confirm` utilise toujours le HWND/PID d'origine, même quand la fenêtre de confirmation est active.
- Ne pas utiliser d'API interne non documentée d'OpenCode.

### Presse-papiers
- API Win32 ou `pyperclip`. Sauvegarder le texte précédent (texte seulement).
- Copier la transcription, coller (Ctrl+V), attendre un délai court réglable (`PASTE_RESTORE_DELAY_MS`, défaut 300), puis restaurer le texte précédent.
- **Restaurer uniquement si le presse-papiers contient encore ma transcription.** S'il a changé entre-temps, ou si la restauration échoue, ne jamais écraser le contenu actuel.
- **Garder la dernière transcription en mémoire**, accessible via l'entrée « Copier la dernière transcription » du menu de l'icône système, même après une erreur de collage.

### Deux modes d'injection (dans `.env`)
`INJECT_MODE=confirm` (par défaut) : petite fenêtre sombre avec le texte modifiable et les boutons Injecter / Copier / Effacer. `INJECT_MODE=auto` : collage direct après transcription.

### Interface
Icône dans la zone de notification (états : repos / enregistrement / transcription / erreur), bips de début et de fin, petite fenêtre sombre en mode `confirm` (pas de violet ni de cyan). Rien d'autre.

### Threads
- Tkinter est propriétaire de l'interface et tourne dans le thread principal.
- `pystray` tourne dans un thread séparé. Le raccourci global (`RegisterHotKey`) tourne dans son propre thread avec sa boucle de messages.
- Les autres threads transmettent leurs résultats à Tkinter via une `queue.Queue` consommée avec `after()`. **Aucune modification directe de widgets Tkinter depuis un autre thread.**
- Les appels HTTP, le collage et le presse-papiers ne bloquent jamais l'interface.

### Performance
Logger des timestamps simples par étape : préparation audio, envoi + STT + réception, injection. Pas de framework de mesure.

## 6. TESTS (LÉGERS)

- Test réel : 10 phrases françaises techniques dites par moi, avec le temps de réponse noté pour chacune. Compare le texte obtenu à ce que j'ai dit et signale les termes techniques mal transcrits.
- Test réel du collage dans OpenCode Desktop, avec une autre application active à l'enregistrement, et avec la fenêtre OpenCode fermée avant l'injection.
- Tests d'erreurs : réseau coupé, clé invalide, audio silencieux, presse-papiers modifié pendant le collage.
- Sépare clairement ce qui est testé réellement de ce qui est simulé. Ne présente jamais un test simulé comme une validation réelle. Tu ne peux pas parler à ma place : si un test exige ma voix, demande-moi.

## 7. MÉTHODE

- **Jalon A** : phases 0 et 1, STT validé par HTTP. STOP : présente-moi le résultat avant de continuer.
- **Jalon B** : MVP complet (section 5), testé en réel.
- **Jalon C** : ajustements que je demande après usage. EXE portable seulement si je le demande.
- Après chaque jalon : tester, corriger, documenter brièvement, commit Git si un dépôt existe.
- Ne passe jamais d'un jalon au suivant tant que le précédent ne marche pas réellement. Ne laisse pas de TODO bloquant.

### Fichiers de suivi (les seuls autorisés en plus du code et de `docs/STT_SETUP.md`)
- `docs/SPEC.md` : copie exacte de ce document. Ne pas la modifier sans mon accord.
- `docs/PROGRESS.md` : sections « État actuel », « Fait », « Reste à faire », « Problèmes ouverts » et « Décisions » (une ligne par décision avec sa raison). Mis à jour à la fin de chaque jalon et chaque fois qu'une décision technique est prise. Court : une page maximum.
- `AGENTS.md` (racine) : 10 à 15 lignes maximum résumant les règles essentielles de la section 0 et renvoyant vers `docs/SPEC.md` et `docs/PROGRESS.md`.
Au début de chaque session, lire `AGENTS.md` et `docs/PROGRESS.md` avant toute action.
Ne pas créer d'autre fichier de documentation.

COMMENCE PAR LA PHASE 0.
