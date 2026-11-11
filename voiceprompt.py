# -*- coding: utf-8 -*-
"""VoicePrompt : dictée vocale pour OpenCode Desktop.

Rôles          : texte transcrit collé dans la fenêtre OpenCode active au
départ de l'enregistrement (HWND + PID mémorisés, jamais une autre fenêtre).

Threads        :
  - principal : Tkinter (propriétaire de toute l'UI, boucle after()).
  - pystray   : icône zone de notification.
  - hotkey    : RegisterHotKey + boucle de messages Win32.
  - recorder  : capture micro (sounddevice), écriture WAV.
  - stt       : requête HTTP POST multipart vers FreeLLMAPI local.
  - injector  : presse-papiers + SetForegroundWindow + Ctrl+V.
Communication vers l'UI : exclusivement queue.Queue consommée par root.after().
"""

import ctypes
import ctypes.wintypes as wt
import logging
import os
import queue
import re
import sys
import threading
import time
import uuid
import wave
import winsound

import numpy as np
import requests
import sounddevice as sd
import tkinter as tk
from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem
from win32 import win32clipboard

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- .env / config

def load_env():
    env = {}
    path = os.path.join(APP_DIR, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

ENV = load_env()
BASE_URL = ENV.get("FREEAPI_BASE_URL", "http://127.0.0.1:31415")
API_KEY = ENV.get("FREEAPI_API_KEY", "")
TARGET_PROCESS = ENV.get("TARGET_PROCESS", "OpenCode.exe")
STT_MODEL = ENV.get("STT_MODEL", "whisper-large-v3")
INJECT_MODE = ENV.get("INJECT_MODE", "confirm")          # confirm | auto
PASTE_DELAY_MS = int(ENV.get("PASTE_RESTORE_DELAY_MS", "300"))
RMS_SILENCE = float(ENV.get("RMS_SILENCE_THRESHOLD", "0.005"))
MAX_RECORD_S = int(ENV.get("MAX_RECORD_SECONDS", "120"))

# Contexte lexical transmis à Groq (paramètre prompt) — SPEC §3
TECH_TERMS = (
    "OpenCode, GLM, Claude, Gemini, DeepSeek, Python, TypeScript, JavaScript, "
    "React, Next.js, Prisma, Supabase, PostgreSQL, SQLite, API, MCP, GitHub, "
    "Git, PowerShell"
)

HOTKEY_REG_ID = 0x1CBB
MOD_ALT, MOD_CONTROL = 0x1, 0x2
WM_HOTKEY = 0x0312
VK_SPACE, VK_CONTROL, VK_KEY_V = 0x20, 0x11, 0x56

logging.basicConfig(
    filename=os.path.join(APP_DIR, "voiceprompt.log"),
    level=logging.INFO,
    format="%(asctime)s,%(msecs)03d %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("voiceprompt")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# ---------------------------------------------------------------- fenêtre cible

def get_target(hwnd):
    """HWND → {"hwnd", "pid", "exe"} ; None si fenêtre inexistante."""
    if not hwnd or not user32.IsWindow(hwnd):
        return None
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = "?"
    h = kernel32.OpenProcess(0x1000, False, pid.value)   # QUERY_LIMITED_INFORMATION
    if h:
        buf = ctypes.create_unicode_buffer(512)
        size = wt.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            exe = os.path.basename(buf.value)
        kernel32.CloseHandle(h)
    return {"hwnd": hwnd, "pid": int(pid.value), "exe": exe}

def get_foreground_target():
    return get_target(user32.GetForegroundWindow())

def target_is_opencode(t):
    return bool(t) and t["exe"].lower() == TARGET_PROCESS.lower()

def verify_target(t):
    """HWND toujours vivant + même PID + même exécutable : (ok, raison)."""
    if not t:
        return False, "aucune fenêtre mémorisée"
    if not user32.IsWindow(t["hwnd"]):
        return False, "la fenêtre OpenCode mémorisée a été fermée"
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(t["hwnd"], ctypes.byref(pid))
    if int(pid.value) != t["pid"]:
        return False, "la fenêtre appartient désormais à un autre processus"
    cur = get_target(t["hwnd"])
    if not cur or cur["exe"].lower() != t["exe"].lower():
        return False, "l'exécutable de la fenêtre a changé"
    return True, ""

# ---------------------------------------------------------------- presse-papiers

CF_UNICODETEXT = 13

def clipboard_get_text():
    try:
        win32clipboard.OpenClipboard(None)
        try:
            if win32clipboard.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(CF_UNICODETEXT)
            return None
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return None

def clipboard_set_text(text, attempts=5):
    for i in range(attempts):
        try:
            win32clipboard.OpenClipboard(None)
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(CF_UNICODETEXT, text)
            finally:
                win32clipboard.CloseClipboard()
            return True
        except Exception:
            time.sleep(0.05 * (i + 1))
    return False

# ---------------------------------------------------------------- Ctrl+V

def send_ctrl_v():
    """Ctrl+V via keybd_event (pywin32) — SendInput ctypes trop choquant ici."""
    import win32api
    down, up = 0, 0x0002  # KEYEVENTF_KEYUP
    win32api.keybd_event(VK_CONTROL, 0, down, 0)
    time.sleep(0.03)
    win32api.keybd_event(VK_KEY_V, 0, down, 0)
    time.sleep(0.05)
    win32api.keybd_event(VK_KEY_V, 0, up, 0)
    win32api.keybd_event(VK_CONTROL, 0, up, 0)

def bring_to_foreground(hwnd):
    """SetForegroundWindow en gérant la restriction Windows (attach thread input)."""
    if not user32.IsWindow(hwnd):
        return False
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    my_thread = kernel32.GetCurrentThreadId()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    attached = False
    try:
        if fg_thread and fg_thread != my_thread:
            attached = user32.AttachThreadInput(my_thread, fg_thread, True) != 0
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(my_thread, fg_thread, False)
    time.sleep(0.05)
    return user32.GetForegroundWindow() == hwnd

# ---------------------------------------------------------------- audio

class Recorder(threading.Thread):
    """Enregistrement mono, samplerate natif du micro par défaut, WAV int16."""

    def __init__(self, on_result):
        super().__init__(daemon=True, name="recorder")
        self.frames = []
        self._stop = threading.Event()
        self._on_result = on_result
        info = sd.query_devices(sd.default.device[0], "input")
        self.sr = int(info["default_samplerate"])

    def _cb(self, indata, frames, t, status):
        self.frames.append(indata.copy())
        if sum(len(f) for f in self.frames) >= self.sr * MAX_RECORD_S:
            self.stop_click()

    def stop_click(self):
        self._stop.set()

    def run(self):
        try:
            with sd.InputStream(device=sd.default.device[0], samplerate=self.sr,
                                channels=1, dtype="int16", blocksize=1024,
                                callback=self._cb):
                self._stop.wait()
            path = os.path.join(APP_DIR, "audio", f"rec_{uuid.uuid4().hex[:8]}.wav")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(self.sr)
                for f in self.frames:
                    w.writeframes(f.tobytes())
            dur = sum(len(f) for f in self.frames) / self.sr
            rms = float(np.sqrt(np.mean(
                np.abs(np.concatenate(self.frames).astype(np.float32) / 32768.0) ** 2)))
            log.info("audio OK dur=%.2fs sr=%d rms=%.5f (seuil %.5f) %s",
                     dur, self.sr, rms, RMS_SILENCE, path)
            self._on_result(path, rms, dur, None)
        except Exception as e:
            log.exception("recorder")
            self._on_result(None, 0.0, 0.0, str(e))

# ---------------------------------------------------------------- STT

STT_MSG = {
    401: "Clé API locale invalide — relance FreeLLMAPI et vérifie le .env.",
    403: "Accès refusé par le fournisseur STT.",
    413: "Fichier audio trop volumineux pour le fournisseur.",
    429: "Limite de débit atteinte (OVH : 2 req/min). Réessaie dans ~30 s.",
}

def stt_fail_msg(e):
    if isinstance(e, requests.HTTPError) and e.response is not None:
        return STT_MSG.get(e.response.status_code, f"Erreur STT HTTP {e.response.status_code}.")
    if isinstance(e, requests.ConnectionError):
        return f"FreeLLMAPI ne répond pas sur {BASE_URL} — lance-le puis réessaie."
    if isinstance(e, requests.Timeout):
        return "Délai dépassé pendant la transcription (30 s)."
    if isinstance(e, ValueError):
        return "Réponse illisible du serveur STT."
    return "Erreur inattendue pendant la transcription."

# ---------------------------------------------------------------- bips

def beep_start(): winsound.Beep(1046, 70)
def beep_stop():  winsound.Beep(523, 70)
def beep_err():   winsound.Beep(200, 250)

# ---------------------------------------------------------------- transcriptions fantômes

GHOST_FILLERS = {"ok", "ok.", "merci.", "bye", "bye.", "au revoir", "au revoir !", "à bientôt", "à bientôt !", "..."}

# Hallucinations typiques de Whisper sur silence (entraîné sur des sous-titres YouTube)
GHOST_PATTERNS = [
    r"merci d'avoir regardé",
    r"merci d'avoir regardée",
    r"thanks for watching",
    r"sous-titr\w*",          # sous-titres, sous-titrage, sous-titré…
    r"amara\.org",
    r"abonnez-vous",
    r"subscribe",
]

def transcript_ok(text, dur):
    t = text.strip().lower()
    if len(t) <= 1:
        return False
    if dur is not None and dur < 1.5 and t in GHOST_FILLERS:
        return False
    # phrase-cliché hallucinatoire de Whisper : court et typique
    if len(t) < 80:
        for pat in GHOST_PATTERNS:
            if re.search(pat, t):
                return False
    return True

def audio_ok(rms, dur):
    """Rejette uniquement le silence quasi total, jamais une voix faible."""
    return rms >= RMS_SILENCE and dur >= 0.4

# ---------------------------------------------------------------- états / icône

STATE_COLORS = {"repos": "#6c757d", "enregistrement": "#dc3545",
                "transcription": "#e0a800", "erreur": "#8b0000"}

def tray_img(state):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((6, 6, 58, 58), fill=STATE_COLORS.get(state, "#6c757d"))
    return img

# ---------------------------------------------------------------- App

class App:
    """Cœur : gère états, cible, file d'événements, fenêtre « confirm »."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.q = queue.Queue()
        self.state = "repos"
        self.last_text = ""
        self.last_target = None
        self.last_rec_path = None
        self.recorder = None
        self.confirm_win = None
        self.bad_clip = False
        self.hotkey_registered = False
        self._make_tray()
        self._start_hotkey_thread()
        self.root.after(80, self._poll)

    # ------------------------------------------------ icône système
    def _make_tray(self):
        menu = Menu(
            MenuItem("Enregistrer / arrêter   (Ctrl+Alt+Espace)",
                     self._tray_toggle, default=True),
            MenuItem("Copier la dernière transcription", self._tray_copy_last),
            MenuItem("Réessayer la transcription (après erreur)", self._tray_retry),
            Menu.SEPARATOR,
            MenuItem("Quitter", self._tray_quit))
        self.icon = Icon("VoicePrompt", tray_img("repos"),
                         f"VoicePrompt — Ctrl+Alt+Espace pour démarrer", menu)

    def _tray_toggle(self, *_a):
        self.q.put({"e": "toggle"})
    def _tray_copy_last(self, *_a):
        self.q.put({"e": "copy_last"})
    def _tray_retry(self, *_a):
        self.q.put({"e": "retry"})
    def _tray_quit(self, icon, item):
        icon.stop()
        self.q.put({"e": "quit"})

    def set_state(self, s):
        self.state = s
        try:
            self.icon.icon = tray_img(s)
            self.icon.title = f"VoicePrompt — {s}"
        except Exception:
            pass

    # ------------------------------------------------ hotkey
    def _start_hotkey_thread(self):
        def loop():
            if not user32.RegisterHotKey(None, HOTKEY_REG_ID, MOD_CONTROL | MOD_ALT, VK_SPACE):
                self.q.put({"e": "hotkey_fail"})
                return
            msg = wt.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    self.q.put({"e": "toggle"})
            user32.UnregisterHotKey(None, HOTKEY_REG_ID)
        threading.Thread(target=loop, daemon=True, name="hotkey").start()

    # ------------------------------------------------ toggle enregistrement
    def _toggle(self):
        if self.recorder is not None:
            self.recorder.stop_click()
            return
        target = get_foreground_target()
        # SPEC §5 : quand une fenêtre de VoicePrompt elle-même est au premier plan
        # (fenêtre de confirmation), on garde la cible mémorisée d'origine.
        if target and int(target["pid"]) == int(kernel32.GetCurrentProcessId()):
            target = self.last_target
        self.last_target = target
        beep_start()
        self.recorder = Recorder(self._rec_result)
        self.recorder.start()
        self.set_state("enregistrement")
        if not target_is_opencode(target):
            self.icon.notify("Fenêtre active ≠ OpenCode — le texte sera collé dans la "
                             "fenêtre OpenCode mémorisée (autorisé).", "VoicePrompt")

    def _rec_result(self, path, rms, dur, err):
        self.recorder = None
        beep_stop()
        if err or path is None:
            self.q.put({"e": "error", "msg": f"Erreur d'enregistrement micro : {err or 'inconnue'}"})
            return
        if not audio_ok(rms, dur):
            os.remove(path)
            self.q.put({"e": "error",
                        "msg": "Enregistrement quasi silencieux (pas de voix exploitable). "
                               "Réessaie en parlant plus près du micro."})
            return
        self.set_state("transcription")
        threading.Thread(target=self._stt_loop, args=(path, dur), daemon=True).start()

    # ------------------------------------------------ STT
    def _stt_loop(self, path, dur=None):
        t0 = time.perf_counter()
        try:
            with open(path, "rb") as f:
                r = requests.post(
                    f"{BASE_URL}/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {API_KEY}"},
                    files={"file": (os.path.basename(path), f, "audio/wav")},
                    data={"model": STT_MODEL, "language": "fr",
                          "prompt": TECH_TERMS, "response_format": "json"},
                    timeout=30)
            r.raise_for_status()
            text = r.json().get("text")
            if not isinstance(text, str):
                raise ValueError("champ 'text' absent")
            log.info("STT %.0f ms (%.1f Mo)", (time.perf_counter() - t0) * 1000,
                     os.path.getsize(path) / 1e6)
            log.info("transcription: %s", text[:300])
            self.q.put({"e": "stt_done", "text": text, "path": path, "dur": dur})
        except Exception as e:
            log.exception("stt")
            self.q.put({"e": "stt_fail", "msg": stt_fail_msg(e), "path": path})

    # ------------------------------------------------ injection
    def _inject_thread(self, text, target):
        t0 = time.perf_counter()
        ok, reason = verify_target(target)
        if not ok:
            self.q.put({"e": "inject_fail", "msg": reason})
            return
        old_txt = clipboard_get_text()
        if not clipboard_set_text(text):
            self.q.put({"e": "inject_fail", "msg": "Presse-papiers verrouillé par une autre application."})
            return
        if not bring_to_foreground(target["hwnd"]):
            self.q.put({"e": "inject_fail",
                        "msg": "Windows a refusé d'activer la fenêtre cible (essayez en la mettant au premier plan)."})
            return
        if user32.GetForegroundWindow() != target["hwnd"]:
            self.q.put({"e": "inject_fail",
                        "msg": "La fenêtre cible s'est fermée ou a changé pendant le collage."})
            return
        send_ctrl_v()
        time.sleep(PASTE_DELAY_MS / 1000.0)
        now = clipboard_get_text()
        if now == text:                       # ← restauration OK uniquement si inchangée
            if old_txt is not None:
                clipboard_set_text(old_txt)
            self.bad_clip = False
        else:
            self.bad_clip = True              # on n'écrase pas ce que l'utilisateur a mis
        log.info("injection %.0f ms ok=%s clip_modifié=%s",
                 (time.perf_counter() - t0) * 1000, now == text, self.bad_clip)
        self.q.put({"e": "inject_done" if now == text else "inject_clip_changed"})

    # ------------------------------------------------ fenêtre de confirmation
    def _show_confirm(self, text, target, warn):
        self._close_confirm()
        w = tk.Toplevel(self.root)
        w.title("VoicePrompt")
        w.configure(bg="#1e1e1e", padx=10, pady=8)
        w.attributes("-topmost", True)
        self._place_bottom_right(w)
        if warn:
            tk.Label(w, text=f"⚠ Fenêtre active ≠ {TARGET_PROCESS} — le texte sera "
                             "collé dans la fenêtre OpenCode mémorisée au début de "
                             "l'enregistrement.",
                     bg="#1e1e1e", fg="#e0a800", wraplength=400).pack(anchor="w",
                                                                      pady=(0, 4))
            if target:
                tk.Label(w, text=f"cible : PID {target['pid']} ({target['exe']})",
                         bg="#1e1e1e", fg="#888888").pack(anchor="w", pady=(0, 4))
        txt = tk.Text(w, bg="#252526", fg="#d4d4d4", insertbackground="#d4d4d4",
                      height=6, wrap="word", relief="flat", font=("Segoe UI", 10))
        txt.insert("1.0", text)
        txt.pack(fill="both", expand=True)
        bar = tk.Frame(w, bg="#1e1e1e")
        bar.pack(fill="x", pady=(6, 0))

        def b(label, cmd):
            tk.Button(bar, text=label, command=cmd, bg="#333333", fg="#cccccc",
                      activebackground="#3c3c3c", activeforeground="#ffffff",
                      relief="flat", padx=10).pack(side="left", padx=(0, 6))

        def do_inject(*_):
            src_text = txt.get("1.0", "end").strip()
            w.destroy()
            self.confirm_win = None
            self.set_state("transcription")
            threading.Thread(target=self._inject_thread, args=(src_text, target),
                             daemon=True).start()

        def do_copy(*_):
            self.last_text = txt.get("1.0", "end").strip()
            clipboard_set_text(self.last_text)
            w.destroy()
            self.confirm_win = None
            self.icon.notify("Transcription copiée.", "VoicePrompt")
            self.set_state("repos")

        def do_clear(*_):
            txt.delete("1.0", "end")
            txt.focus_set()

        b("Injecter", do_inject)
        b("Copier", do_copy)
        b("Effacer", do_clear)
        w.bind("<Return>", do_inject)
        w.bind("<Escape>", lambda *_: w.destroy() or self._on_confirm_close())
        w.protocol("WM_DELETE_WINDOW", lambda: w.destroy() or self._on_confirm_close())
        txt.focus_set()
        self.confirm_win = w

    def _on_confirm_close(self):
        """Fermeture sans injection : transcription reste en mémoire."""
        self.confirm_win = None
        self.set_state("repos")

    def _close_confirm(self):
        if self.confirm_win is not None:
            try:
                self.confirm_win.destroy()
            except Exception:
                pass
            self.confirm_win = None

    @staticmethod
    def _place_bottom_right(w):
        try:
            sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
            w.geometry(f"430x230+{max(0, sw - 450)}+{max(0, sh - 270)}")
        except Exception:
            w.geometry("430x230")

    # ------------------------------------------------ file d'événements
    def _poll(self):
        try:
            while True:
                ev = self.q.get_nowait()
                h = getattr(self, f"_ev_{ev['e']}", None)
                if h:
                    h(ev)
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _ev_toggle(self, _ev):
        self._toggle()

    def _ev_hotkey_fail(self, _ev):
        self.set_state("erreur")
        self.icon.notify("Raccourci Ctrl+Alt+Espace déjà pris par une autre application.",
                         "VoicePrompt")
        beep_err()

    def _ev_stt_done(self, ev):
        text = ev["text"].strip()
        if not text or not transcript_ok(text, ev["dur"] if ev["dur"] is not None else 10.0):
            os.remove(ev["path"])
            self.set_state("erreur")
            self.icon.notify("Transcription vide ou fantôme détectée — réessaie.",
                             "VoicePrompt")
            log.info("rejet fantôme: %s", text[:120])
            beep_err()
            return
        self.last_text = text
        self.last_rec_path = ev["path"]
        # Transcription réussie → le fichier audio n'est plus nécessaire (SPEC §5)
        try:
            os.remove(ev["path"])
        except OSError:
            pass
        self.last_rec_path = None
        if INJECT_MODE == "auto":
            threading.Thread(target=self._inject_thread, args=(text, self.last_target),
                             daemon=True).start()
        else:
            self.set_state("repos")
            warn = not target_is_opencode(self.last_target)
            self._show_confirm(text, self.last_target, warn)

    def _ev_stt_fail(self, ev):
        self.last_rec_path = ev["path"]        # ← audio conservé pour nouvel essai
        self.set_state("erreur")
        self.icon.notify(ev["msg"], "VoicePrompt — erreur STT")
        beep_err()

    def _ev_error(self, ev):
        self.set_state("erreur")
        self.icon.notify(ev["msg"], "VoicePrompt")
        beep_err()

    def _ev_inject_done(self, _ev):
        self._finish_record()
        self.set_state("repos")

    def _ev_inject_clip_changed(self, _ev):
        self._finish_record()
        self.set_state("erreur")
        self.icon.notify("Le presse-papiers a été modifié pendant le collage — "
                         "texte de presse-papiers d'origine conservé.",
                         "VoicePrompt")
        beep_err()

    def _ev_inject_fail(self, ev):
        self.set_state("erreur")
        self.icon.notify(f"Échec de l'injection : {ev['msg']}\n"
                         "La transcription est conservée — menu de l'icône → "
                         "« Copier la dernière transcription ».",
                         "VoicePrompt")
        beep_err()

    def _ev_copy_last(self, _ev):
        if self.last_text:
            clipboard_set_text(self.last_text)
            self.icon.notify("Dernière transcription copiée dans le presse-papiers.",
                             "VoicePrompt")
        else:
            self.icon.notify("Aucune transcription en mémoire.", "VoicePrompt")

    def _ev_retry(self, _ev):
        if self.last_rec_path and os.path.exists(self.last_rec_path):
            self.set_state("transcription")
            threading.Thread(target=self._stt_loop,
                             args=(self.last_rec_path, 5.0), daemon=True).start()
        else:
            self.icon.notify("Aucun audio en attente d'essai.", "VoicePrompt")

    def _ev_quit(self, _ev):
        self._close_confirm()
        self.root.quit()

    def _finish_record(self):
        if self.last_rec_path:
            try:
                os.remove(self.last_rec_path)
            except OSError:
                pass
            self.last_rec_path = None

    def run(self):
        self.root.mainloop()

# ---------------------------------------------------------------- main

if __name__ == "__main__":
    app = App()
    threading.Thread(target=app.icon.run, daemon=True, name="pystray").start()
    app.run()
