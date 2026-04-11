#!/usr/bin/env python3
"""
Looi — Personal AI Assistant
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Looi robot-inspired AI desktop companion powered by Google Gemini.

Features
  • Programmatic Looi-style animated face (expressive eyes + mouth)
  • Real-time face tracking via webcam — pupils follow you
  • Mood / emotion detection from camera using Gemini Vision
  • Voice recognition (SpeechRecognition + Google Speech API)
  • Conversation powered by Google Gemini (streaming)
  • Natural TTS responses via gTTS + pygame
  • Music suggestions based on mood or genre
  • Web search via DuckDuckGo
  • Persistent chat memory (last 10 turns)

Controls
  SPACE / ENTER  →  Talk (push-to-talk)
  ESC            →  Quit
  Click          →  Toggle HUD

Usage
  1. Set gemini_api_key in config.json
  2. python looi.py
"""

# ── stdlib ─────────────────────────────────────────────────────────────────
import tkinter as tk
import math, random, threading, queue, json, os, re, time
import base64, tempfile, datetime, io, wave
import numpy as np

# ── optional deps (graceful fallback) ──────────────────────────────────────
try:
    import sounddevice as sd
    _AUDIO = True
except Exception:
    _AUDIO = False

try:
    import cv2
    _CV2 = True
except Exception:
    _CV2 = False

try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI = True
except Exception:
    _GENAI = False

try:
    import speech_recognition as sr
    _SR = True
except Exception:
    _SR = False

try:
    import pygame
    pygame.mixer.init()
    _PYGAME = True
except Exception:
    _PYGAME = False

try:
    from gtts import gTTS
    _GTTS = True
except Exception:
    _GTTS = False

try:
    from duckduckgo_search import DDGS
    _DDGS = True
except Exception:
    _DDGS = False

try:
    from scipy.signal import resample_poly
    _SCIPY = True
except Exception:
    _SCIPY = False

# ── paths ──────────────────────────────────────────────────────────────────
_DIR        = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_DIR, "config.json")
MEMORY_FILE = os.path.join(_DIR, "memory.json")

# ── window / canvas ────────────────────────────────────────────────────────
W, H        = 800, 480
FPS         = 30
FRAME_MS    = 1000 // FPS

# ── eye geometry ───────────────────────────────────────────────────────────
L_EYE_X     = W // 2 - 148     # left eye centre x
R_EYE_X     = W // 2 + 148     # right eye centre x
EYE_Y       = H // 2 - 18      # eye centre y
ERX         = 70                # eye x-radius
ERY         = 80                # eye y-radius
PUPIL_R     = 26                # pupil radius
MAX_DRIFT   = 30                # max pupil offset from eye centre

# ── mouth ──────────────────────────────────────────────────────────────────
MOUTH_X     = W // 2
MOUTH_Y     = H // 2 + 108
MOUTH_W     = 60
MOUTH_H     = 28

# ── colours ────────────────────────────────────────────────────────────────
BG_COL      = "#07080f"
GLOW_COL    = "#0c1428"
EYE_COL     = "#d8e8ff"
EYE_RIM     = "#6fa8d8"
IRIS_COL    = "#1e5fc2"
PUPIL_COL   = "#030308"
SHINE_COL   = "#ffffff"
SHINE2_COL  = "#99ccff"
LID_COL     = "#07080f"       # matches background — used as "erase" mask
MOUTH_COL   = "#3080e0"
MOUTH_DARK  = "#060418"
HUD_COL     = "#2888d8"
TEXT_COL    = "#b0c8e8"
ACCENT_COL  = "#00aaff"

# ── audio ──────────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
SILENCE_RMS = 450
SILENCE_SEC = 1.8
MAX_REC_SEC = 12.0
MAX_MEMORY  = 10


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# States
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class S:
    IDLE      = "idle"
    LISTENING = "listening"
    THINKING  = "thinking"
    SPEAKING  = "speaking"
    HAPPY     = "happy"
    SAD       = "sad"
    SURPRISED = "surprised"
    EXCITED   = "excited"
    ERROR     = "error"
    WARMUP    = "warmup"

STATUS = {
    S.IDLE:      "Standing by…  (SPACE to talk)",
    S.LISTENING: "I'm listening…",
    S.THINKING:  "Thinking…",
    S.SPEAKING:  "Speaking",
    S.HAPPY:     "Happy!",
    S.SAD:       "Feeling down…",
    S.SURPRISED: "Whoa!",
    S.EXCITED:   "So excited!",
    S.ERROR:     "Uh oh…",
    S.WARMUP:    "Waking up…",
}

# Expression tuple layout
# (top_lid, bot_lid, pupil_scale, happy_arch, eye_dx, eye_dy, mouth_curve, mouth_open)
# top_lid      0=fully open, 1=eyelid fully closed from top
# bot_lid      0=fully open, 1=eyelid fully closed from bottom
# pupil_scale  1.0=normal; <1 constricted; >1 dilated
# happy_arch   0=no arch;  1=full happy-squint arch (^^ eyes)
# eye_dx/dy    pupil centre offset for "looking" direction
# mouth_curve  -1=max frown, 0=neutral, +1=max smile
# mouth_open   0=closed, 1=open oval
EXP = {
    S.IDLE:      (0.10, 0.04, 1.00, 0.0,   0,   0,  0.25, 0.00),
    S.LISTENING: (0.00, 0.00, 1.15, 0.0,   0,   0,  0.10, 0.00),
    S.THINKING:  (0.22, 0.00, 0.90, 0.0, -10, -14,  0.00, 0.00),
    S.SPEAKING:  (0.06, 0.00, 1.00, 0.0,   0,   0,  0.20, 0.60),
    S.HAPPY:     (0.00, 0.00, 1.05, 1.0,   0,   5,  0.90, 0.00),
    S.SAD:       (0.18, 0.30, 0.85, 0.0,   0,   8, -0.75, 0.00),
    S.SURPRISED: (0.00, 0.00, 0.72, 0.0,   0,   0,  0.00, 0.55),
    S.EXCITED:   (0.00, 0.00, 1.28, 0.0,   0,  -3,  0.80, 0.15),
    S.ERROR:     (0.38, 0.00, 0.88, 0.0,   0,   6, -0.30, 0.00),
    S.WARMUP:    (0.28, 0.00, 0.85, 0.0,   0,   0,  0.10, 0.00),
}

# Mood keywords → state
MOOD_MAP = {
    "happy":     S.HAPPY,   "joy":       S.HAPPY,
    "joyful":    S.HAPPY,   "smiling":   S.HAPPY,
    "excited":   S.EXCITED, "thrilled":  S.EXCITED,
    "surprised": S.SURPRISED, "shocked": S.SURPRISED,
    "sad":       S.SAD,     "unhappy":   S.SAD,
    "angry":     S.SAD,     "upset":     S.SAD,
    "neutral":   S.IDLE,    "calm":      S.IDLE,
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Config
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def load_config():
    defaults = {
        "gemini_api_key":    "",
        "gemini_model":      "gemini-2.0-flash-lite",
        "vision_model":      "gemini-2.0-flash-lite",
        "tts_lang":          "en",
        "tts_slow":          False,
        "chat_memory":       True,
        "face_tracking":     True,
        "mood_detection":    True,
        "mood_interval_s":   45,
        "camera_index":      0,
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                defaults.update(json.load(f))
        except Exception:
            pass
    return defaults

CONFIG = load_config()

_genai_client = None
if _GENAI and CONFIG["gemini_api_key"]:
    try:
        _genai_client = genai.Client(api_key=CONFIG["gemini_api_key"])
    except Exception as _ex:
        print(f"[Looi] Gemini client init: {_ex}")

SYSTEM_PROMPT = """You are Looi, a warm, playful AI desktop companion inspired by the Looi robot.
Your personality: friendly, curious, expressive, like a loyal little robot friend.
Keep responses to 1–3 short sentences unless detail is genuinely needed.
Use natural emotion ("Oh wow!", "Hmm…", "That's so cool!") where appropriate.

You can use tools by responding ONLY with valid JSON and nothing else:
{"action": "<tool>", "query": "<optional input>"}

Available tools:
  get_time      – returns the current date and time
  search_web    – web search (query = search terms)
  capture_mood  – analyse webcam image to detect the user's current mood
  suggest_music – suggest songs or a playlist (query = mood, genre, or vibe)

If no tool is needed, reply conversationally. Never mix JSON and plain text.
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LooiGUI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class LooiGUI:

    def __init__(self, root):
        self.root = root
        root.title("Looi")
        root.geometry(f"{W}x{H}")
        root.configure(bg=BG_COL)
        root.resizable(False, False)

        # ── Canvas ──────────────────────────────────────────────────────────
        self.canvas = tk.Canvas(root, width=W, height=H, bg=BG_COL,
                                highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # ── HUD labels ──────────────────────────────────────────────────────
        self._hud_on      = True
        self._status_var  = tk.StringVar(value=STATUS[S.WARMUP])
        self._text_var    = tk.StringVar(value="")

        self._lbl_status = tk.Label(root, textvariable=self._status_var,
                                    font=("Helvetica", 13, "bold"),
                                    fg=HUD_COL, bg=BG_COL)
        self._lbl_status.place(x=W // 2, y=H - 52, anchor="center")

        self._lbl_text = tk.Label(root, textvariable=self._text_var,
                                  font=("Helvetica", 10),
                                  fg=TEXT_COL, bg=BG_COL,
                                  wraplength=720, justify="center")
        self._lbl_text.place(x=W // 2, y=H - 28, anchor="center")

        # ── Expression state ────────────────────────────────────────────────
        self._state   = S.WARMUP
        self._cur_exp = list(EXP[S.WARMUP])   # current (lerp'd)
        self._tgt_exp = list(EXP[S.WARMUP])   # target

        # ── Blink ────────────────────────────────────────────────────────────
        self._blink       = 0.0
        self._blinking    = False
        self._blink_start = 0.0
        self._next_blink  = time.time() + random.uniform(3, 6)

        # ── Pupil tracking ───────────────────────────────────────────────────
        self._pl_x = self._pl_y = 0.0   # current left  pupil offset
        self._pr_x = self._pr_y = 0.0   # current right pupil offset
        self._tl_x = self._tl_y = 0.0   # target  left
        self._tr_x = self._tr_y = 0.0   # target  right

        # ── Mouth oscillation ────────────────────────────────────────────────
        self._mouth_phase = 0.0

        # ── Events / queues ──────────────────────────────────────────────────
        self._stop       = threading.Event()
        self._tts_queue  = queue.Queue()
        self._ptt_event  = threading.Event()

        # ── Camera frame (shared with tracking thread) ───────────────────────
        self._cam_frame     = None
        self._cam_lock      = threading.Lock()
        self._last_mood_t   = 0.0

        # ── Chat history ─────────────────────────────────────────────────────
        self._history = self._load_history()

        # ── Gemini client ─────────────────────────────────────────────────────
        self._client = _genai_client

        # ── Keybindings ──────────────────────────────────────────────────────
        root.bind("<Escape>",   lambda _e: self._safe_exit())
        root.bind("<space>",    lambda _e: self._ptt_press())
        root.bind("<Return>",   lambda _e: self._ptt_press())
        root.bind("<Button-1>", lambda _e: self._toggle_hud())
        root.protocol("WM_DELETE_WINDOW", self._safe_exit)

        # ── Threads ──────────────────────────────────────────────────────────
        threading.Thread(target=self._tts_worker,   daemon=True).start()
        threading.Thread(target=self._main_loop,    daemon=True).start()
        if _CV2 and (CONFIG["face_tracking"] or CONFIG["mood_detection"]):
            threading.Thread(target=self._camera_loop, daemon=True).start()

        # ── Start animation ──────────────────────────────────────────────────
        self._schedule_animate()

    # ══════════════════════════════════════════════════════════════════════════
    # Animation
    # ══════════════════════════════════════════════════════════════════════════

    def _schedule_animate(self):
        self.root.after(FRAME_MS, self._animate)

    def _animate(self):
        now = time.time()

        # ── Lerp expression ──
        spd = 0.11
        for i in range(len(self._cur_exp)):
            self._cur_exp[i] += (self._tgt_exp[i] - self._cur_exp[i]) * spd

        # ── Blink logic ──
        blink_dur = 0.18
        if not self._blinking and now >= self._next_blink:
            self._blinking    = True
            self._blink_start = now
        if self._blinking:
            t = (now - self._blink_start) / blink_dur
            if t < 0.5:
                self._blink = t * 2
            elif t < 1.0:
                self._blink = 2.0 - t * 2
            else:
                self._blink     = 0.0
                self._blinking  = False
                self._next_blink = now + random.uniform(3.0, 7.0)

        # ── Smooth pupil tracking ──
        lp = 0.09
        self._pl_x += (self._tl_x - self._pl_x) * lp
        self._pl_y += (self._tl_y - self._pl_y) * lp
        self._pr_x += (self._tr_x - self._pr_x) * lp
        self._pr_y += (self._tr_y - self._pr_y) * lp

        # ── Mouth oscillation when speaking ──
        if self._state == S.SPEAKING:
            self._mouth_phase += 0.28
        else:
            self._mouth_phase = 0.0

        # ── Excited bounce ──
        bounce = math.sin(now * 9) * 5 if self._state == S.EXCITED else 0.0

        # ── Draw ──
        self.canvas.delete("face")
        self._draw_scene(bounce)

        self._schedule_animate()

    def _draw_scene(self, bounce=0.0):
        e = self._cur_exp
        top_lid, bot_lid, p_scale, arch, edx, edy, mouth_c, mouth_o = e

        # Mouth open oscillates while speaking
        if self._state == S.SPEAKING:
            mouth_o = abs(math.sin(self._mouth_phase)) * 0.72

        # Pupil offsets = tracking + expression direction
        l_pdx = self._pl_x + edx
        l_pdy = self._pl_y + edy + bounce
        r_pdx = self._pr_x + edx
        r_pdy = self._pr_y + edy + bounce

        ey = EYE_Y + bounce

        # ── Face glow ──
        for rad, col in [(190, "#0a1125"), (155, "#0c1830"), (115, "#0f2242")]:
            self.canvas.create_oval(
                W // 2 - rad, H // 2 - rad + bounce,
                W // 2 + rad, H // 2 + rad + bounce,
                fill=col, outline="", tags="face")

        # ── Eyes ──
        self._draw_eye(L_EYE_X, ey, top_lid, bot_lid, p_scale, arch, l_pdx, l_pdy)
        self._draw_eye(R_EYE_X, ey, top_lid, bot_lid, p_scale, arch, r_pdx, r_pdy)

        # ── Mouth ──
        self._draw_mouth(MOUTH_X, MOUTH_Y + bounce, mouth_c, mouth_o)

        # ── State indicator ──
        self._draw_state_dot()

    def _draw_eye(self, cx, cy, top_lid, bot_lid, p_scale, arch, pdx, pdy):
        blink  = self._blink

        # 1. Outer glow ring
        self.canvas.create_oval(
            cx - ERX - 7, cy - ERY - 7,
            cx + ERX + 7, cy + ERY + 7,
            fill="#0c1e3c", outline="#183060", width=1, tags="face")

        # 2. Eye white
        self.canvas.create_oval(
            cx - ERX, cy - ERY, cx + ERX, cy + ERY,
            fill=EYE_COL, outline=EYE_RIM, width=2, tags="face")

        if blink >= 0.99:
            # Fully closed: flood with lid colour
            self.canvas.create_oval(
                cx - ERX - 1, cy - ERY - 1,
                cx + ERX + 1, cy + ERY + 1,
                fill=LID_COL, outline="", tags="face")
            return

        # 3. Iris
        pr  = PUPIL_R * p_scale
        ir  = pr * 1.65
        self.canvas.create_oval(
            cx + pdx - ir, cy + pdy - ir,
            cx + pdx + ir, cy + pdy + ir,
            fill=IRIS_COL, outline="", tags="face")

        # 4. Pupil
        self.canvas.create_oval(
            cx + pdx - pr, cy + pdy - pr,
            cx + pdx + pr, cy + pdy + pr,
            fill=PUPIL_COL, outline="", tags="face")

        # 5. Main highlight
        sh = max(3, pr * 0.30)
        self.canvas.create_oval(
            cx + pdx + pr * 0.28 - sh, cy + pdy - pr * 0.42 - sh,
            cx + pdx + pr * 0.28 + sh, cy + pdy - pr * 0.42 + sh,
            fill=SHINE_COL, outline="", tags="face")
        # Secondary highlight
        sh2 = max(2, sh * 0.55)
        self.canvas.create_oval(
            cx + pdx - pr * 0.40 - sh2, cy + pdy + pr * 0.32 - sh2,
            cx + pdx - pr * 0.40 + sh2, cy + pdy + pr * 0.32 + sh2,
            fill=SHINE2_COL, outline="", tags="face")

        # 6. Happy arch eyelid (^^ expression)
        if arch > 0.05:
            self._draw_happy_arch(cx, cy, arch)

        # 7. Normal top eyelid
        elif top_lid > 0.0:
            lh = ERY * 2 * top_lid
            self.canvas.create_rectangle(
                cx - ERX - 2, cy - ERY - 2,
                cx + ERX + 2, cy - ERY + lh,
                fill=LID_COL, outline="", tags="face")

        # 8. Bottom eyelid (sad droop)
        if bot_lid > 0.0:
            lh = ERY * 2 * bot_lid
            self.canvas.create_rectangle(
                cx - ERX - 2, cy + ERY - lh,
                cx + ERX + 2, cy + ERY + 2,
                fill=LID_COL, outline="", tags="face")

        # 9. Blink overlay
        if blink > 0.01:
            bh = ERY * blink
            self.canvas.create_rectangle(
                cx - ERX - 2, cy - ERY - 2,
                cx + ERX + 2, cy - ERY + bh,
                fill=LID_COL, outline="", tags="face")
            self.canvas.create_rectangle(
                cx - ERX - 2, cy + ERY - bh,
                cx + ERX + 2, cy + ERY + 2,
                fill=LID_COL, outline="", tags="face")

        # 10. Re-draw eye rim on top for clean look
        self.canvas.create_oval(
            cx - ERX, cy - ERY, cx + ERX, cy + ERY,
            fill="", outline=EYE_RIM, width=2, tags="face")

    def _draw_happy_arch(self, cx, cy, arch):
        """Curved eyelid that creates the ^^ happy squint look."""
        n   = 32
        pts = []
        # Top row (above eye boundary)
        for i in range(n + 1):
            t = i / n
            pts.extend([cx - ERX + 2 * ERX * t, cy - ERY - 3])
        # Bottom curved edge: dips down following sin curve (arch depth)
        depth = ERY * arch * 0.78
        for i in range(n, -1, -1):
            t  = i / n
            x  = cx - ERX + 2 * ERX * t
            y  = cy - depth * math.sin(math.pi * t)
            pts.extend([x, y])
        self.canvas.create_polygon(pts, fill=LID_COL, outline="",
                                   smooth=True, tags="face")

    def _draw_mouth(self, mx, my, curve, open_amt):
        if open_amt > 0.12:
            # Open oval mouth
            oh = max(8, int(MOUTH_H * (0.35 + open_amt)))
            self.canvas.create_oval(
                mx - MOUTH_W // 2, my - oh // 2,
                mx + MOUTH_W // 2, my + oh // 2,
                fill=MOUTH_DARK, outline=MOUTH_COL, width=3, tags="face")
        elif curve >= 0:
            # Smile: bottom arc of an ellipse
            depth = 6 + int(curve * 24)
            self.canvas.create_arc(
                mx - MOUTH_W // 2, my - depth,
                mx + MOUTH_W // 2, my + depth,
                start=200, extent=-160,
                style=tk.ARC, outline=MOUTH_COL, width=3, tags="face")
        else:
            # Frown: top arc of an ellipse
            depth = 6 + int(abs(curve) * 24)
            self.canvas.create_arc(
                mx - MOUTH_W // 2, my - depth,
                mx + MOUTH_W // 2, my + depth,
                start=20, extent=160,
                style=tk.ARC, outline=MOUTH_COL, width=3, tags="face")

    def _draw_state_dot(self):
        """Pulsing status dot in the top-right corner."""
        dot_cfg = {
            S.LISTENING: (ACCENT_COL,  4),
            S.THINKING:  ("#ff8800",   3),
            S.SPEAKING:  ("#00cc44",   3),
            S.HAPPY:     ("#ffdd00",   3),
            S.EXCITED:   ("#ff44cc",   4),
            S.SAD:       ("#6688cc",   3),
        }
        if self._state in dot_cfg:
            col, r = dot_cfg[self._state]
            pulse  = 0.5 + 0.5 * math.sin(time.time() * 7)
            pr     = r + pulse * 2
            self.canvas.create_oval(
                W - 28 - pr, 18 - pr, W - 28 + pr, 18 + pr,
                fill=col, outline="", tags="face")

    # ══════════════════════════════════════════════════════════════════════════
    # State management
    # ══════════════════════════════════════════════════════════════════════════

    def set_state(self, state):
        self._state   = state
        self._tgt_exp = list(EXP.get(state, EXP[S.IDLE]))
        self.root.after_idle(
            lambda s=state: self._status_var.set(STATUS.get(s, "")))

    def _set_text(self, text):
        if len(text) > 130:
            text = text[:129] + "…"
        self.root.after_idle(lambda t=text: self._text_var.set(t))

    def _toggle_hud(self):
        if self._hud_on:
            self._lbl_status.place_forget()
            self._lbl_text.place_forget()
        else:
            self._lbl_status.place(x=W // 2, y=H - 52, anchor="center")
            self._lbl_text.place(x=W // 2, y=H - 28, anchor="center")
        self._hud_on = not self._hud_on

    # ══════════════════════════════════════════════════════════════════════════
    # Main conversation loop
    # ══════════════════════════════════════════════════════════════════════════

    def _main_loop(self):
        self._warmup()
        while not self._stop.is_set():
            try:
                self._conversation_turn()
            except Exception as ex:
                print(f"[Looi] Loop error: {ex}")
                self.set_state(S.ERROR)
                time.sleep(2)
                self.set_state(S.IDLE)

    def _warmup(self):
        self.set_state(S.WARMUP)
        if self._client:
            try:
                self._client.models.generate_content(
                    model=CONFIG["gemini_model"],
                    contents="Reply with only: Hello")
            except Exception as ex:
                print(f"[Looi] Warmup error: {ex}")
        time.sleep(1.2)
        self.set_state(S.HAPPY)
        self._tts_queue.put("Hello! I'm Looi, your personal AI companion. "
                             "Press space to start talking to me!")
        self._wait_tts()
        self.set_state(S.IDLE)

    def _ptt_press(self):
        if not self._ptt_event.is_set():
            self._ptt_event.set()

    def _conversation_turn(self):
        self.set_state(S.IDLE)
        self._ptt_event.wait()       # block until SPACE pressed
        if self._stop.is_set():
            return
        self._ptt_event.clear()

        # ── Periodic mood detection ──
        now = time.time()
        if (CONFIG["mood_detection"]
                and self._cam_frame is not None
                and now - self._last_mood_t > CONFIG.get("mood_interval_s", 45)):
            self._last_mood_t = now
            threading.Thread(target=self._auto_mood, daemon=True).start()

        # ── Record ──
        self.set_state(S.LISTENING)
        wav = self._record()
        if wav is None or len(wav) < 1500:
            self.set_state(S.IDLE)
            return

        # ── Transcribe ──
        self.set_state(S.THINKING)
        text = self._transcribe(wav)
        if not text:
            self._tts_queue.put("I didn't catch that — try again?")
            self._wait_tts()
            self.set_state(S.IDLE)
            return

        self._set_text(f'You: "{text}"')
        self._chat(text)

    # ══════════════════════════════════════════════════════════════════════════
    # Audio — record
    # ══════════════════════════════════════════════════════════════════════════

    def _record(self):
        if not _AUDIO:
            return None
        buf            = []
        silence_frames = 0
        chunk          = int(SAMPLE_RATE * 0.1)
        max_chunks     = int(MAX_REC_SEC / 0.1)
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                 dtype="int16") as stream:
                for _ in range(max_chunks):
                    if self._stop.is_set():
                        break
                    data, _ = stream.read(chunk)
                    buf.append(data.copy())
                    rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))
                    if rms < SILENCE_RMS:
                        silence_frames += 1
                        if silence_frames * 0.1 >= SILENCE_SEC:
                            break
                    else:
                        silence_frames = 0
        except Exception as ex:
            print(f"[Looi] Record error: {ex}")
            return None
        if not buf:
            return None
        audio = np.concatenate(buf, axis=0).flatten()
        return self._to_wav(audio)

    def _to_wav(self, audio):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        return buf.getvalue()

    # ══════════════════════════════════════════════════════════════════════════
    # Speech-to-text
    # ══════════════════════════════════════════════════════════════════════════

    def _transcribe(self, wav_bytes):
        if not _SR:
            return ""
        rec = sr.Recognizer()
        try:
            with sr.AudioFile(io.BytesIO(wav_bytes)) as src:
                audio = rec.record(src)
            return rec.recognize_google(audio)
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as ex:
            print(f"[Looi] STT service error: {ex}")
            return ""
        except Exception as ex:
            print(f"[Looi] STT error: {ex}")
            return ""

    # ══════════════════════════════════════════════════════════════════════════
    # TTS
    # ══════════════════════════════════════════════════════════════════════════

    def _tts_worker(self):
        while not self._stop.is_set():
            try:
                text = self._tts_queue.get(timeout=0.5)
                self._speak(text)
                self._tts_queue.task_done()
            except queue.Empty:
                pass

    def _speak(self, text):
        if not text.strip():
            return
        self.set_state(S.SPEAKING)
        try:
            if _GTTS and _PYGAME:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    path = f.name
                gTTS(text=text,
                     lang=CONFIG.get("tts_lang", "en"),
                     slow=CONFIG.get("tts_slow", False)).save(path)
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.05)
                    if self._stop.is_set():
                        pygame.mixer.music.stop()
                        break
                try:
                    os.unlink(path)
                except Exception:
                    pass
            else:
                print(f"[Looi says] {text}")
                time.sleep(len(text) * 0.05)
        except Exception as ex:
            print(f"[Looi] TTS error: {ex}")
        finally:
            if self._state == S.SPEAKING:
                self.set_state(S.IDLE)

    def _wait_tts(self):
        self._tts_queue.join()

    # ══════════════════════════════════════════════════════════════════════════
    # Gemini chat
    # ══════════════════════════════════════════════════════════════════════════

    def _chat(self, user_text):
        # ── Memory reset shortcut ──
        if any(p in user_text.lower() for p in
               ("forget everything", "reset memory", "clear history", "start fresh")):
            self._history.clear()
            self._save_history()
            reply = "Memory cleared! Starting fresh."
            self.set_state(S.HAPPY)
            self._set_text(reply)
            self._tts_queue.put(reply)
            self._wait_tts()
            self.set_state(S.IDLE)
            return

        if not self._client:
            msg = ("Gemini is not configured. "
                   "Please add your API key to config.json.")
            self._tts_queue.put(msg)
            self._wait_tts()
            self.set_state(S.IDLE)
            return

        model_id = CONFIG["gemini_model"]
        try:
            chat = self._client.chats.create(
                model=model_id,
                config=genai_types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT
                ),
                history=list(self._history),
            )
            resp  = chat.send_message(user_text)
            reply = resp.text.strip()
        except Exception as ex:
            print(f"[Looi] Gemini error: {ex}")
            self.set_state(S.ERROR)
            self._tts_queue.put("I had trouble reaching Gemini. "
                                 "Please check your API key and connection.")
            self._wait_tts()
            self.set_state(S.IDLE)
            return

        # ── Tool call? ──
        action = self._extract_json(reply)
        if action and "action" in action:
            result = self._run_tool(action["action"], action.get("query", ""))
            try:
                follow = chat.send_message(
                    f"Tool result: {result}\n"
                    "Now reply conversationally to the user based on this result.")
                reply = follow.text.strip()
            except Exception:
                reply = result

        # ── Update history ──
        if CONFIG.get("chat_memory", True):
            self._history.append({"role": "user",  "parts": [user_text]})
            self._history.append({"role": "model", "parts": [reply]})
            if len(self._history) > MAX_MEMORY * 2:
                self._history = self._history[-MAX_MEMORY * 2:]
            self._save_history()

        # ── React + speak ──
        self._react_to_reply(reply)
        self._set_text(reply)
        time.sleep(0.6)   # brief moment to show the expression
        self._tts_queue.put(reply)
        self._wait_tts()
        self.set_state(S.IDLE)

    def _react_to_reply(self, text):
        t = text.lower()
        if any(w in t for w in ("love", "amazing", "wonderful", "great",
                                 "happy", "yay", "joy", "beautiful")):
            self.set_state(S.HAPPY)
        elif any(w in t for w in ("excited", "thrilled", "can't wait",
                                   "awesome", "incredible")):
            self.set_state(S.EXCITED)
        elif any(w in t for w in ("oh wow", "whoa", "really?", "no way",
                                   "surprising", "unexpected")):
            self.set_state(S.SURPRISED)
        elif any(w in t for w in ("sorry", "sad", "unfortunately", "miss",
                                   "difficult", "hard time", "struggle")):
            self.set_state(S.SAD)
        else:
            self.set_state(S.THINKING)

    # ══════════════════════════════════════════════════════════════════════════
    # Tools
    # ══════════════════════════════════════════════════════════════════════════

    def _run_tool(self, action, query):
        a = action.lower().strip()

        if a == "get_time":
            return datetime.datetime.now().strftime(
                "Today is %A, %B %d %Y. The time is %I:%M %p.")

        if a in ("search_web", "google", "search", "find", "duckduckgo"):
            return self._search_web(query)

        if a in ("capture_mood", "mood", "emotion", "feeling"):
            return self._detect_mood()

        if a in ("suggest_music", "music", "playlist", "songs", "song"):
            return self._suggest_music(query)

        return f"Unknown tool: {action}"

    def _search_web(self, query):
        if not _DDGS or not query:
            return "Web search unavailable."
        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=3):
                    results.append(f"{r['title']}: {r['body'][:120]}")
            return " | ".join(results) if results else "No results found."
        except Exception as ex:
            return f"Search error: {ex}"

    def _suggest_music(self, mood_or_genre):
        if self._client:
            try:
                r = self._client.models.generate_content(
                    model=CONFIG["gemini_model"],
                    contents=(
                        f"Suggest 5 great songs for someone feeling or wanting: "
                        f"'{mood_or_genre}'. Format: Artist — Song. Be brief."))
                return r.text.strip()
            except Exception:
                pass
        return self._search_web(f"best {mood_or_genre} songs playlist 2024")

    def _detect_mood(self):
        with self._cam_lock:
            frame = self._cam_frame
        if frame is None:
            return "Camera not available."
        if not (self._client and _CV2):
            return "Vision model unavailable."
        try:
            _, buf = cv2.imencode(".jpg", frame)
            img_bytes = buf.tobytes()
            resp = self._client.models.generate_content(
                model=CONFIG.get("vision_model", CONFIG["gemini_model"]),
                contents=[
                    "Look at this image. In 1–2 words, what emotion or mood "
                    "does the person appear to have? If no person, say 'no person'.",
                    genai_types.Part.from_bytes(data=img_bytes,
                                                mime_type="image/jpeg"),
                ])
            mood = resp.text.strip().lower()
            self._apply_mood(mood)
            return f"The user appears to be: {mood}"
        except Exception as ex:
            return f"Mood detection error: {ex}"

    def _auto_mood(self):
        result = self._detect_mood()
        print(f"[Looi] Auto mood check: {result}")

    def _apply_mood(self, mood_text):
        for kw, state in MOOD_MAP.items():
            if kw in mood_text:
                self.set_state(state)
                self.root.after(3500, lambda: self.set_state(S.IDLE))
                return

    # ══════════════════════════════════════════════════════════════════════════
    # Camera / face tracking
    # ══════════════════════════════════════════════════════════════════════════

    def _camera_loop(self):
        cap          = None
        cascade_path = None
        face_cascade = None

        try:
            cap = cv2.VideoCapture(CONFIG.get("camera_index", 0))
            cascade_path = cv2.data.haarcascades + \
                           "haarcascade_frontalface_default.xml"
            face_cascade = cv2.CascadeClassifier(cascade_path)
        except Exception as ex:
            print(f"[Looi] Camera init: {ex}")
            return

        while not self._stop.is_set():
            try:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.1)
                    continue

                with self._cam_lock:
                    self._cam_frame = frame.copy()

                if CONFIG.get("face_tracking", True) and face_cascade is not None:
                    gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = face_cascade.detectMultiScale(
                        gray, scaleFactor=1.1, minNeighbors=5,
                        minSize=(60, 60))

                    if len(faces) > 0:
                        x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                        fx = x + fw / 2
                        fy = y + fh / 2
                        nx = (fx / frame.shape[1] - 0.5) * 2   # –1 … +1
                        ny = (fy / frame.shape[0] - 0.5) * 2

                        # Mirror x so right is right
                        self._tl_x = -nx * MAX_DRIFT
                        self._tl_y =  ny * MAX_DRIFT * 0.55
                        self._tr_x = -nx * MAX_DRIFT
                        self._tr_y =  ny * MAX_DRIFT * 0.55
                    else:
                        # Drift back to centre
                        self._tl_x *= 0.92
                        self._tl_y *= 0.92
                        self._tr_x *= 0.92
                        self._tr_y *= 0.92

            except Exception as ex:
                print(f"[Looi] Camera loop error: {ex}")

            time.sleep(0.05)   # ~20 fps tracking

        if cap:
            cap.release()

    # ══════════════════════════════════════════════════════════════════════════
    # Memory
    # ══════════════════════════════════════════════════════════════════════════

    def _load_history(self):
        if not CONFIG.get("chat_memory", True):
            return []
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_history(self):
        try:
            with open(MEMORY_FILE, "w") as f:
                json.dump(self._history, f, indent=2)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _extract_json(self, text):
        m = re.search(r'\{[^{}]+\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        return None

    def _safe_exit(self):
        self._stop.set()
        self._save_history()
        try:
            self.root.destroy()
        except Exception:
            pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Entry point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == "__main__":
    root = tk.Tk()
    app  = LooiGUI(root)
    root.mainloop()
