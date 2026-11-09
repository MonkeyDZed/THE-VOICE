# PROGRESS — VoicePrompt

## État actuel
Jalon A atteint (phases 0 + 1) : STT français validé par HTTP réel via FreeLLMAPI local, sans aucune clé fournisseur. STOP avant Jalon B, en attente de ton accord.

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
- Fichiers : `docs/SPEC.md` (copie ta spec), `docs/STT_SETUP.md`, `.env` (clé + port + cible), `AGENTS.md`, `stt_test.py` (script de re-test).
- `.gitignore` créé avant tout commit éventuel (`.env` exclu).

## Reste à faire (Jalon B, après ton accord)
- Application MVP : hotkey `RegisterHotKey`, enregistrement sounddevice→WAV natif mono, contrôle RMS, barre système pystray, fenêtre confirm Tkinter, collage HWND/PID-ciblé, sauvegarde/restauration presse-papiers, gestion d'erreurs claire, timestamps de performance.
- Python : installer `sounddevice soundfile pystray requests` (Python 3.10.11 déjà présent).
- Test réel des 10 phrases françaises (ta voix), test du collage dans OpenCode, tests d'erreurs.

## Problèmes ouverts
- Le champ `prompt` (contexte lexical) n'est pas transmis à l'adaptateur OVH (code FreeLLMAPI vérifié) : la liste de termes techniques de SPEC §3 ne peut pas être injectée par ce paramètre. Whisper v3 les transcrit déjà convenablement sur nos tests ; à re-vérifier lors du test des 10 phrases.
- Quota OVH : 2 req/min par IP (anonyme). Suffisant pour la dictée, mais le test des 10 phrases devra respecter ce rythme.

## Décisions
- Modèle retenu `whisper-large-v3` plutôt que turbo : fidélité des termes techniques prioritaire sur la vitesse (2,85 s pour 19 s d'audio → probablement < 2 s pour une dictée de 10 s, objectif < 3 s atteint).
- Passage par FreeLLMAPI local (jamais d'appel direct OVH) : auth centralisée, clé `.env` unique, selon règle « commencer par FreeLLMAPI ».
- `model=whisper-large-v3` explicite plutôt que `auto` : `auto` peut basculer un jour sur un autre fournisseur si une clé est ajoutée ; résultat reproductible garanti.
- Lecture de la clé via sqlite en lecture seule puis copie dans `.env` : clé locale, aucun achat, aucune soumission de clé à un service tiers.
