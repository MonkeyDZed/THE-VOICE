# AGENTS.md — VoicePrompt

Outil de dictée vocale personnel exclusif (Windows, Python), pour parler à OpenCode Desktop. Simple : `.env`, pas de backend ni de réglages.

- Règles essentielles : `docs/SPEC.md` — Ne jamais ajouter une fonctionnalité absente du cahier des charges.
- Suivi : `docs/PROGRESS.md` — Jalon courant et état du projet.
- STT : `docs/STT_SETUP.md` — Audio transmis à FreeLLMAPI local (127.0.0.1:31415, clé `.env`), modèle `whisper-large-v3` via OVH (gratuit, sans clé agent).
- OpenCode Desktop = processus `OpenCode.exe` (Electron, plusieurs processus par instance), fenêtre principale : classe `Chrome_WidgetWin_1`. Cible collage : couple HWND + PID.
- Clé API dans `.env`, jamais committé, jamais dans les journaux.
- Toujours tester réellement avant de valider un jalon.
