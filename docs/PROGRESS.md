# PROGRESS — VoicePrompt

## État actuel
Jalon B : injection validée en réel (collage OK quand focus OpenCode). STT basculé sur Groq + prompt lexical après dérive constatée sur OVH — fidélité nettement améliorée, latence 1,2 s. Reste du jalon : tests d'erreur + 10 phrases réelles.

## Fait
- Phase 0 — Audit machine (10/11/2026) :  - FreeLLMAPI Desktop 0.16.23, installé dans `C:\Users\maste\AppData\Local\Programs\freellmapi-desktop` ; données/config dans `%APPDATA%\FreeLLMAPI`.
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
- Jalon B :
  - `voiceprompt.py` (1 fichier) : hotkey Win32, enregistrement mono au samplerate natif du micro (sounddevice), RMS seuil `.env`, bips (`winsound`), barre système (pystray, états colorés), fenêtre de confirmation Tkinter sombre (Injecter/Copier/Effacer, Entrée/Échap), collage ciblé HWND+PID (`SetForegroundWindow` + SendInput Ctrl+V), sauvegarde/restauration du presse-papiers (uniquement si inchangé), transcription gardée en mémoire + entrée « Réessayer la transcription » après erreur STT.
  - Threads : Tkinter principal (file `queue.Queue` + `after()`), pystray, hotkey, recorder, STT, injection — aucune écriture UI hors thread Tk.
  - Logs `voiceprompt.log` : timestamps préparation audio / STT / injection, RMS loggée, jamais la clé.
  - Tests composants réels OK : presse-papiers set/get/restore, détection fenêtre active (PID + exe), verify_target (fenêtre vivante vs fenêtre morte), STT HTTP 200.
  - Fix injection : `SendInput` (ctypes) rejeté silencieusement par Windows x64 (struct 32 octets vs 40 exigés) → remplacé par `keybd_event` (pywin32). Injection validée en réel par l'utilisateur, latences STT mesurées 1,5 à 2,4 s pour 12 à 21 s d'audio.
  - Test des 10 phrases réelles (Groq + prompt, diction en serie) : latences STT 0,39-0,80 s, injection ~0,4 s → total < 1,2 s (objectif < 3 s tenu). Fidélité : 4/10 quasi parfait (#4/#3/#5/#6), 4/10 avec 1-2 homophones (« Gemini »→« Gimini », « DeepSeek »→« DEEPSY », « commit »→« commis », « SQLite »→« SQL »), 2/10 dérivés sérieusement (#2 endpoint/authentification, #10 « base de données »→« l'ambiance du journal »). Détails dans les logs `voiceprompt.log`.
  - Re-test des phrases #2/#9/#10 le lendemain, micro à ~30 cm (au lieu de 1 m) : **transcription mot pour mot** des trois phrases + « RMS » correctement orthographié sur dictées libres. Cause racine des dérives : signal RMS 0,010 (trop loin) vs 0,037 (proche). Aucun changement de code ; recommandation d'usage : parler près du micro.
  - 10/10 injections réproduites (collage ok, presse-papiers intacts, ~0,4 s).
  - Limité (retour utilisateur) : dérive de transcription sur phrases techniques : « jalon bloquant » → « genre d'encre », « gratuit sur ton FreeLLMAPI Desktop » → « à l'âme d'escroc ». Cause probable : l'adaptateur OVH ne transmet pas le champ `prompt` (contexte lexical indisponible) et Whisper diverge sans contexte. Voir « Problèmes ouverts ».
- Fichiers : `docs/SPEC.md` (copie ta spec), `docs/STT_SETUP.md`, `.env` (clé + port + cible), `AGENTS.md`, `stt_test.py` (script de re-test).
- `.gitignore` créé avant tout commit éventuel (`.env` exclu).

## Reste à faire (fin de Jalon B)
- Tests d'erreur réels : réseau coupé, audio silencieux, presse-papiers modifié pendant le collage, fenêtre OpenCode fermée avant l'injection.
- Mode auto `INJECT_MODE=auto` (test du collage direct).
- Raccourci Windows : fait (Bureau, pythonw, sans terminal).

## Problèmes ouverts
- (Résolu 10/11) L'adaptateur OVH ne transmettait pas le champ `prompt` ; le passage à Groq (clé gratuite de l'utilisateur dans FreeLLMAPI) rend le contexte lexical effectif : « Prisma », « Next.js », « GitHub » correctement transcrits, latence 1,2 s pour 19 s d'audio.
- Whisper peut toujours hérisser un mot isolé (« appui » au lieu d'« app ») : à surveiller dans le test des 10 phrases. Aucune auto-correction n'est appliquée (SPEC : aucune reformulation).

## Décisions
- Modèle STT : `whisper-large-v3` via **Groq** (clé gratuite ajoutée par l'utilisateur dans FreeLLMAPI) **avec prompt lexical** — meilleures latence (1,2 s / 19 s d'audio) et fidélité des termes techniques que OVH keyless. OVH reste en fallback sans action.
- Passage par FreeLLMAPI local (jamais d'appel direct fournisseur) : auth centralisée, clé `.env` unique, selon règle « commencer par FreeLLMAPI ».
- `model=whisper-large-v3` explicite plutôt que `auto` : `auto` irait sur Groq *turbo* (plus rapide mais moins fidèle, vérifié), le filtre par id garde `whisper-large-v3`.
- Prompt lexical = les 20 termes de SPEC §3, envoyés sur chaque requête : validé par A/B réel (améliore sans fausser).
- Test des 10 phrases : les dérives homophones étaient dues à un signal trop faible (micro à 1 m, RMS 0,010). À ~30 cm (RMS 0,037), les phrases #2/#9/#10 sont transcrites mot pour mot — le prompt n'a pas eu besoin d'être enrichi. (Résolu 11/11.)
- Lecture de la clé via sqlite en lecture seule puis copie dans `.env` : clé locale, aucun achat, aucune soumission de clé à un service tiers.
- Jalon B : presse-papiers et bips via modules embarqués (pywin32, winsound) plutôt que bibliothèques tierces supplémentaires — moins de dépendances, même comportement.
- Jalon B : ajout de l'entrée « Réessayer la transcription » dans le menu de l'icône — exigé par SPEC §3 (« l'audio reste disponible pour un nouvel essai »).
