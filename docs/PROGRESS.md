# PROGRESS — VoicePrompt

## État actuel
Jalon B en cours de test réel : MVP opérationnel (voiceprompt.py), app lancée (pythonw), en attente de ton test interactif (hotkey, dictée, collage dans OpenCode).

## Fait
- Phase 0 — Audit machine (10/11/2026) :
  - FreeLLMAPI Desktop 0.16.23, installé dans `C:\Users\maste\AppData\Local\Programs\freellmapi-desktop` ; données/config dans `%APPDATA%\FreeLLMAPI`.
  - Processus : 3 processus `FreeLLMAPI.exe` ; serveur local sur `127.0.0.1:31415` (mesuré, non 3001).
  - Dashboard : SPA servie sur la racine (toute route inconnue renvoie l'index HTML). API protégée : 401 sans clé.
  - Auth : clé API unifiée `freellmapi-…` stockée dans `freeapi.db` (table `settings`), acceptée en Bearer ou `X-API-Key`. Lue en lecture seule, copiée dans `.env`.
  - Catalogue STT présent en base (`media_models`, 13 modèles) : Groq (whisper-large-v3 / turbo), Cloudflare (whisper, turbo, nova-3, tiny-en), OVH (whisper-large-v3 / turbo), Mistral (voxtral-mini), Cohere, Typhoon.
  - Aucune clé fournisseur configurée (table `api_keys` vide) — conforme à ce que tu as dit.
  - OVH est traité comme keyless par le code de l'app : aucune clé fournisseur requise.
  - OpenCode Desktop 2.2.5 : processus `OpenCode.exe` (5 processus Electron) + `opencode-cli.exe` (serveur local 127.0.0.1:28894). Fenêtre principale visible : classe `Chrome_WidgetWin_1`, titre finissant par « OpenCode ». Un PID par instance → `TARGET_PROCESS=OpenCode.exe` dans `.env`.
- Phase 1 — Validation STT (test réel, fichier `Enregistrement1.wav` 19,3 s, français) :
  - `POST http://127.0.0.1:31415/v1/audio/transcriptions`, `model=whisper-large-v3`, `language=fr` → HTTP 200, texte correct, **3,53 s**.
  - `whisper-large-v3-turbo` → HTTP 200, **2,85 s** mais moins fidèle sur les termes techniques.
  - WAV 44,1 kHz stéréo 16 bits accepté nativement → pas de conversion 16 kHz.
- Jalon B — MVP :
  - `voiceprompt.py` (1 fichier) : hotkey Win32, enregistrement mono au samplerate natif du micro (sounddevice), RMS seuil `.env`, bips (`winsound`), barre système (pystray, états colorés), fenêtre de confirmation Tkinter sombre (Injecter/Copier/Effacer, Entrée/Échap), collage ciblé HWND+PID (`SetForegroundWindow` + SendInput Ctrl+V), sauvegarde/restauration du presse-papiers (uniquement si inchangé), transcription gardée en mémoire + entrée « Réessayer la transcription » après erreur STT.
  - Threads : Tkinter principal (file `queue.Queue` + `after()`), pystray, hotkey, recorder, STT, injection — aucune écriture UI hors thread Tk.
  - Logs `voiceprompt.log` : timestamps préparation audio / STT / injection, RMS loggée, jamais la clé.
  - Tests composants réels OK : presse-papiers set/get/restore, détection fenêtre active (PID + exe), verify_target (fenêtre vivante vs fenêtre morte), STT HTTP 200.
- Fichiers : `docs/SPEC.md` (copie ta spec), `docs/STT_SETUP.md`, `.env` (clé + port + cible), `AGENTS.md`, `stt_test.py` (script de re-test).
- `.gitignore` créé avant tout commit éventuel (`.env` exclu).

## Reste à faire (fin de Jalon B)
- Ton test interactif :
  1. Ctrl+Alt+Espace → parler → Ctrl+Alt+Espace → fenêtre confirm → « Injecter » dans OpenCode (vérifier le collage réel).
  2. Test du mode auto : `INJECT_MODE=auto` dans `.env`.
  3. Tests d'erreur : réseau coupé, audio silencieux, presse-papiers modifié pendant le collage, fenêtre OpenCode fermée avant l'injection.
  4. 10 phrases de test réelles (ton micro, en respectant le rythme OVH : max 2 req/min).
- Créer le raccourci Windows (pythonw, sans terminal) après validation du MVP.

## Problèmes ouverts
- Le champ `prompt` (contexte lexical) n'est pas transmis à l'adaptateur OVH (code FreeLLMAPI vérifié) : la liste de termes techniques de SPEC §3 ne peut pas être injectée par ce paramètre. Whisper v3 les transcrit déjà convenablement sur nos tests ; à re-vérifier lors du test des 10 phrases.
- Quota OVH : 2 req/min par IP (anonyme). Suffisant pour la dictée, mais le test des 10 phrases devra respecter ce rythme.

## Décisions
- Modèle retenu `whisper-large-v3` plutôt que turbo : fidélité des termes techniques prioritaire sur la vitesse (2,85 s pour 19 s d'audio → probablement < 2 s pour une dictée de 10 s, objectif < 3 s atteint).
- Passage par FreeLLMAPI local (jamais d'appel direct OVH) : auth centralisée, clé `.env` unique, selon règle « commencer par FreeLLMAPI ».
- `model=whisper-large-v3` explicite plutôt que `auto` : `auto` peut basculer un jour sur un autre fournisseur si une clé est ajoutée ; résultat reproductible garanti.
- Lecture de la clé via sqlite en lecture seule puis copie dans `.env` : clé locale, aucun achat, aucune soumission de clé à un service tiers.
- Jalon B : presse-papiers et bips via modules embarqués (pywin32, winsound) plutôt que bibliothèques tierces supplémentaires — moins de dépendances, même comportement.
- Jalon B : ajout de l'entrée « Réessayer la transcription » dans le menu de l'icône — exigé par SPEC §3 (« l'audio reste disponible pour un nouvel essai »).
