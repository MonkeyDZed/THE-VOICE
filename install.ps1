# install.ps1 — installation de VoicePrompt sur une machine
# Usage : powershell -ExecutionPolicy Bypass -File install.ps1
# Prerequis : Python 3.10+ installe, FreeLLMAPI Desktop installe ET lance au moins une fois.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host '=== VoicePrompt - installation ==='
Write-Host "Dossier : $Root"

# 1. Python
$py = $null
foreach ($c in @('py', 'python')) {
    try {
        $v = & $c --version 2>$null
        if ($LASTEXITCODE -eq 0) { $py = $c; Write-Host "[OK] Python : $v"; break }
    } catch {}
}
if (-not $py) {
    Write-Host '[ERREUR] Python introuvable. Installe-le depuis python.org avec Add Python to PATH.' -ForegroundColor Red
    exit 1
}

# 2. Dependances
Write-Host '[...] Installation des dependances (pip)...'
& $py -m pip install --quiet -r (Join-Path $Root 'requirements.txt')
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERREUR] pip a echoue.' -ForegroundColor Red
    exit 1
}
Write-Host '[OK] Dependances : sounddevice, numpy, pystray, pillow, requests, pywin32.'

# 3. FreeLLMAPI local : port + cle unifiee (jamais affichee)
$cfgPath = Join-Path $env:APPDATA 'FreeLLMAPI\config.json'
if (-not (Test-Path $cfgPath)) {
    Write-Host '[ERREUR] FreeLLMAPI Desktop non configure : lance-le une fois, puis relance install.ps1.' -ForegroundColor Red
    exit 1
}
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
$port = 31415
if ($cfg.port) { $port = [int]$cfg.port }
Write-Host "[OK] FreeLLMAPI local sur le port $port"

$dbPath = Join-Path $env:APPDATA 'FreeLLMAPI\freeapi.db'
$env:VP_DB = ($dbPath -replace '\\', '/')
$env:VP_SQL = "SELECT value FROM settings WHERE key='unified_api_key'"
$key = & $py -c "import sqlite3,os,sys; sys.stdout.write(sqlite3.connect(os.environ['VP_DB'], uri=True).execute(os.environ['VP_SQL']).fetchone()[0])"
if (-not $key) {
    Write-Host '[ERREUR] Cle unifiee introuvable dans freeapi.db.' -ForegroundColor Red
    exit 1
}
Write-Host '[OK] Cle unifiee lue depuis freeapi.db (non affichee)'

# 4. .env (jamais ecrase s'il existe)
$envPath = Join-Path $Root '.env'
if (Test-Path $envPath) {
    Write-Host '[INFO] .env existant : conserve sans modification.'
} else {
    @"
FREEAPI_BASE_URL=http://127.0.0.1:$port
FREEAPI_API_KEY=$key
TARGET_PROCESS=OpenCode.exe
STT_MODEL=whisper-large-v3
HOTKEY=ctrl+alt+space
INJECT_MODE=confirm
PASTE_RESTORE_DELAY_MS=300
RMS_SILENCE_THRESHOLD=0.015
MAX_RECORD_SECONDS=120
"@ | Set-Content $envPath -Encoding UTF8
    Write-Host "[OK] .env cree (port $port, cle masquee)"
}

# 5. Cle fournisseur STT (Groq) : action humaine unique par machine
$env:VP_SQL = 'SELECT platform FROM api_keys WHERE enabled=1'
$platforms = & $py -c "import sqlite3,os,sys; rows=sqlite3.connect(os.environ['VP_DB'], uri=True).execute(os.environ['VP_SQL']).fetchall(); sys.stdout.write(','.join(r[0] for r in rows))"
if ($platforms -notmatch 'groq') {
    Write-Host '[ACTION REQUISE] Aucune cle Groq dans FreeLLMAPI : dashboard FreeLLMAPI > Cles > ajouter la cle Groq (gsk_..., gratuite, console.groq.com/keys).' -ForegroundColor Yellow
} else {
    Write-Host "[OK] Cle Groq presente ($platforms)"
}

# 6. Raccourci Bureau (pythonw, sans terminal)
$exePath = & $py -c 'import sys; sys.stdout.write(sys.executable)'
$pythonw = Join-Path (Split-Path -Parent $exePath) 'pythonw.exe'
if (-not (Test-Path $pythonw)) {
    $pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
}
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'VoicePrompt.lnk'))
$lnk.TargetPath = $pythonw
$lnk.Arguments = '"' + (Join-Path $Root 'voiceprompt.py') + '"'
$lnk.WorkingDirectory = $Root
$lnk.IconLocation = Join-Path $Root 'voiceprompt.ico'
$lnk.Description = 'VoicePrompt - dictee vocale pour OpenCode (Ctrl+Alt+Espace)'
$lnk.Save()
Write-Host '[OK] Raccourci Bureau VoicePrompt cree'

Write-Host ''
Write-Host '=== Installe. Double-clique VoicePrompt sur le Bureau, puis Ctrl+Alt+Espace. ===' -ForegroundColor Green
