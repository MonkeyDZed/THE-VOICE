# Configuration STT — VoicePrompt

## Choix retenu (validé par test réel le 10/11/2026)

| Item | Valeur |
|---|---|
| Serveur local (FreeLLMAPI Desktop 0.16.23) | `http://127.0.0.1:31415` (mesuré sur la machine, pas 3001) |
| Authentification locale | Clé API unifiée `freellmapi-…` — header `Authorization: Bearer …` ou `X-API-Key`. Stockée dans `%APPDATA%\FreeLLMAPI\freeapi.db` (table `settings`, clé `unified_api_key`). Copiée dans `.env` (exclu de Git). Régénérable via le dashboard de FreeLLMAPI (rubrique clé API). |
| Endpoint transcription local | `POST /v1/audio/transcriptions` (multipart/form-data) |
| Fournisseur effectif | **OVH** (endpoint kepler, keyless : aucune clé fournisseur nécessaire, 2 req/min par IP) |
| Modèle | `whisper-large-v3` (Whisper Large v3 hébergé par OVH), appelé via le serveur local FreeLLMAPI |
| Endpoint amont (à ne jamais appeler directement) | `https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/audio/transcriptions` |

## Test réel effectué

- Fichier : `Enregistrement1.wav` (19,3 s, 44,1 kHz, stéréo, 16 bits, 3,4 Mo, français), enregistré au micro sur ce PC.
- Requête : `POST /v1/audio/transcriptions`, champs `model`, `language=fr`, `response_format=json`, `file`.
- Résultats : HTTP 200, texte retourné, **3,53 s** avec `whisper-large-v3`, **2,85 s** avec `whisper-large-v3-turbo`.
- Objectif < 3 s pour une dictée de 10 s : atteignable (19 s d'audio → 3,5 s).
- Formats audio : le WAV 44,1 kHz stéréo 16 bits est accepté tel quel. Pas de conversion 16 kHz requise.
- Fidélité : `whisper-large-v3` a transcrit les termes techniques avec plus de précision que `whisper-large-v3-turbo` sur le même fichier → `whisper-large-v3` retenu.

## Paramètre `prompt` (contexte lexical)

- FreeLLMAPI accepte un champ `prompt` sur `/v1/audio/transcriptions`, mais l'adaptateur OVH ne le transmet pas (il ne transmet que `language`). Ce champ est donc sans effet côté OVH : constaté dans le code de l'application.
- Conséquence : la liste des termes techniques (SPEC.md §3) ne peut pas être injectée via ce paramètre. Suivi dans `PROGRESS.md` (« Problèmes ouverts »).

## Limites et quotas connus

- OVH kepler : gratuit, anonyme, **2 requêtes/min par IP**. Largement suffisant pour la dictée (1 requête/passage). Pas de quota mensuel documenté.
- Taille max d'upload : 25 Mo (`maxBytes: 26214400` dans le registre de FreeLLMAPI). Non atteignable pour des dictées de quelques secondes.
- Si un jour une clé Groq ou Mistral est ajoutée dans FreeLLMAPI (à faire à la main, jamais automatiquement), `model=auto` basculera vers elle. L'ordre de priorité `auto` constaté dans le catalogue est : Groq → Cloudflare → Cohere → Mistral → OVH. Aujourd'hui seule OVH fonctionne sans clé ; c'est ce que le serveur local utilise.

## Scripts de validation

- `stt_test.py` : refait le test de transcription complet (usage : `python stt_test.py <model>`, défaut `auto`). La clé est lue dans `.env`, jamais affichée.

## Utilisation de la clé dans le code applicatif

- Charger `.env` et lire `FREEAPI_API_KEY`. Ne jamais écrire la clé dans les logs.
