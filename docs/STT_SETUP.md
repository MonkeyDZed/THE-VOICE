# Configuration STT — VoicePrompt

## Choix retenu (validé par test réel le 10/11/2026)

| Item | Valeur |
|---|---|
| Serveur local (FreeLLMAPI Desktop 0.16.23) | `http://127.0.0.1:31415` (mesuré sur la machine, pas 3001) |
| Authentification locale | Clé API unifiée `freellmapi-…` — header `Authorization: Bearer …` ou `X-API-Key`. Stockée dans `%APPDATA%\FreeLLMAPI\freeapi.db` (table `settings`, clé `unified_api_key`). Copiée dans `.env` (exclu de Git). Régénérable via le dashboard de FreeLLMAPI (rubrique clé API). |
| Endpoint transcription local | `POST /v1/audio/transcriptions` (multipart/form-data) |
| Fournisseur effectif | **Groq** (clé API gratuite ajoutée par l'utilisateur dans le dashboard FreeLLMAPI, tier gratuit sans carte) |
| Modèle | `whisper-large-v3` (id identique chez Groq et OVH ; FreeLLMAPI choisit Groq automatiquement dès que la clé existe) |
| Endpoint amont (à ne jamais appeler directement) | `https://api.groq.com/openai/v1/audio/transcriptions` |
| Paramètres transmis | `model`, `language=fr`, `prompt` (20 termes techniques de SPEC §3), `response_format=json` |

## Comparaison réelle des fournisseurs (même fichier, 19,3 s de français)

| Fournisseur | Latence | Fidélité |
|---|---|---|
| OVH keyless `whisper-large-v3`, sans prompt | 3,4-3,5 s | correcte sur phrases courtes, dérive sur termes techniques (« Next.js » → « METJS », « commit » → « comité ») |
| Groq `whisper-large-v3`, **sans** prompt | 1,5 s | pire que OVH sur ce fichier |
| **Groq `whisper-large-v3` + `prompt` (20 termes tech)** | **1,2 s** | **retenue** — Prisma/Next.js/GitHub transcrits correctement |

Le serveur local renvoie un header `X-Provider` indiquant qui a servi la requête — après l'ajout de la clé Groq : `X-Provider: groq`.

## Paramètre `prompt` (contexte lexical)

- Transmis à chaque requête par `voiceprompt.py` (20 termes de SPEC §3).
- Testé réellement : améliore les termes techniques sans fausser le reste du texte.

## Limites et quotas connus

- Groq tier gratuit : aucune carte bancaire, pas de bascule vers du payant ; quotas journaliers de la clé (consultables sur https://console.groq.com/usage). Taille max d'upload : 25 Mo côté FreeLLMAPI, jamais atteignable pour des dictées courtes. Latence mesurée 1,0-1,5 s pour 19 s d'audio.
- Fallback automatique : si la clé Groq est désactivée, FreeLLMAPI retombe sur OVH keyless (2 req/min, sans prompt) — la transcription reste disponible.
- `stt_test.py` : refait le test de transcription (usage : `python stt_test.py <model> [prompt]`). La clé est lue dans `.env`, jamais affichée.

## Utilisation de la clé dans le code applicatif

- Charger `.env` et lire `FREEAPI_API_KEY`. Ne jamais écrire la clé dans les logs.
