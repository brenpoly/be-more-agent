# =========================================================================
#  Be More Agent 🤖
#  A Local, Offline-First AI Agent for Raspberry Pi
#
#  Copyright (c) 2026 brenpoly
#  Licensed under the MIT License
#  Source: https://github.com/brenpoly/be-more-agent
#
#  DISCLAIMER:
#  This software is provided "as is", without warranty of any kind.
#  This project is a generic framework and includes no copyrighted assets.
# =========================================================================

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import time
import json
import os
import subprocess
import random
import re
import sys
import traceback
import atexit
import datetime
import warnings
import wave

warnings.filterwarnings("ignore", category=RuntimeWarning)

import sounddevice as sd
import numpy as np
import openwakeword
from openwakeword.model import Model
import ollama 
import scipy.signal 

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None
        print("[WARN] Search library missing.")

# =========================================================================
# 1. CONFIGURATION
# =========================================================================

# Files
CONFIG_FILE = "config.json"
MEMORY_FILE = "memory.json"
CAM_IMAGE_FILE = "camera_capture.jpg" 
WAKE_WORD_MODEL = "./wakeword.onnx" 
WAKE_WORD_THRESHOLD = 0.5

# Hardware
INPUT_DEVICE_NAME = None 

# Defaults
DEFAULT_CONFIG = {
    "text_model": "gemma3:1b",
    "vision_model": "moondream",
    "voice_model": "piper/en_GB-semaine-medium.onnx",
    "system_prompt": "You are a helpful robot assistant running on a Raspberry Pi.",
    "chat_memory": True,
    "camera_rotation": 0
}

OLLAMA_OPTIONS = {
    'keep_alive': '-1',
    'num_thread': 4,
    'temperature': 0.7,
    'top_k': 40,
    'top_p': 0.9
}

# =========================================================================
# 2. STATE MANAGEMENT
# =========================================================================

class BotStates:
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"
    CAPTURING = "capturing"
    WARMUP = "warmup"

def load_config():
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config.update(json.load(f))
        except: pass
    return config

CURRENT_CONFIG = load_config()

# =========================================================================
# 3. GUI CLASS
# =========================================================================

class BotGUI:
    BG_WIDTH, BG_HEIGHT = 800, 480 
    OVERLAY_WIDTH, OVERLAY_HEIGHT = 400, 300 

    def __init__(self, master):
        self.master = master
        master.title("Pi Assistant")
        master.attributes('-fullscreen', True) 
        master.bind('<Escape>', self.exit_fullscreen)
        
        master.bind('<Return>', self.handle_ptt_toggle)
        master.bind('<space>', self.handle_speaking_interrupt)
        atexit.register(self.safe_exit)
        
        self.current_state = BotStates.WARMUP
        self.current_volume = 0
        self.animations = {}
        self.current_frame_index = 0
        self.current_overlay_image = None
        
        self.permanent_memory = self.load_chat_history()
        self.session_memory = []
        
        self.thinking_sound_active = threading.Event()
        self.ptt_event = threading.Event()       
        self.recording_active = threading.Event() 
        self.interrupted = threading.Event() 
        
        self.tts_queue = []          
        self.tts_queue_lock = threading.Lock() 
        self.tts_active = threading.Event()
        self.current_audio_process = None 
        
        print("[INIT] Loading Wake Word...", flush=True)
        try:
            if os.path.exists(WAKE_WORD_MODEL):
                self.oww_model = Model(wakeword_models=[WAKE_WORD_MODEL])
                print("[INIT] Wake Word Loaded.", flush=True)
            else:
                print(f"[CRITICAL] Model not found: {WAKE_WORD_MODEL}")
                self.oww_model = None
        except Exception as e:
            try:
                 self.oww_model = Model(wakeword_model_paths=[WAKE_WORD_MODEL])
            except:
                self.oww_model = None

        self.background_label = tk.Label(master, bg="#000000")
        self.background_label.place(x=0, y=0, width=self.BG_WIDTH, height=self.BG_HEIGHT)
        
        self.overlay_label = tk.Label(master, bg='black')
        
        self.load_animations()
        self.update_animation() 
        threading.Thread(target=self.main_loop, daemon=True).start()

    def safe_exit(self):
        if self.current_audio_process:
            self.current_audio_process.terminate()
        self.save_chat_history()
        try:
            ollama.generate(model=CURRENT_CONFIG["text_model"], prompt="", keep_alive=0)
        except: pass
        self.master.quit()
        sys.exit(0) 

    def exit_fullscreen(self, event=None):
        self.master.attributes('-fullscreen', False)
        self.safe_exit()

    def load_animations(self):
        base_path = "faces" 
        # These folder names must match your directory structure exactly
        states = ["idle", "listening", "thinking", "speaking", "error", "capturing", "warmup"]
        
        for state in states:
            folder = os.path.join(base_path, state)
            self.animations[state] = []
            if os.path.exists(folder):
                files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.png')])
                for f in files:
                    img = Image.open(os.path.join(folder, f)).resize((self.BG_WIDTH, self.BG_HEIGHT))
                    self.animations[state].append(ImageTk.PhotoImage(img))
            
            if not self.animations[state]:
                if state in self.animations.get("idle", []):
                     self.animations[state] = self.animations["idle"]
                else:
                    blank = Image.new('RGB', (self.BG_WIDTH, self.BG_HEIGHT), color='#0000FF')
                    self.animations[state].append(ImageTk.PhotoImage(blank))

    def update_animation(self):
        frames = self.animations.get(self.current_state, [])
        if not frames:
            self.master.after(500, self.update_animation)
            return

        if self.current_state == BotStates.SPEAKING:
            if self.current_volume > 500: 
                if len(frames) > 1:
                    self.current_frame_index = random.randint(1, len(frames) - 1)
                else:
                    self.current_frame_index = 0
            else:
                self.current_frame_index = 0
        else:
            self.current_frame_index = (self.current_frame_index + 1) % len(frames)

        self.background_label.config(image=frames[self.current_frame_index])
        
        speed = 50 if self.current_state == BotStates.SPEAKING else 500
        self.master.after(speed, self.update_animation)

    def set_state(self, state, cam_path=None):
        def _update():
            if self.current_state != state:
                self.current_state = state
                self.current_frame_index = 0
            
            if cam_path and os.path.exists(cam_path) and state in [BotStates.THINKING, BotStates.SPEAKING]:
                try:
                    img = Image.open(cam_path).resize((self.OVERLAY_WIDTH, self.OVERLAY_HEIGHT))
                    self.current_overlay_image = ImageTk.PhotoImage(img)
                    self.overlay_label.config(image=self.current_overlay_image)
                    self.overlay_label.place(x=200, y=90) 
                except: pass
            else:
                self.overlay_label.place_forget()
        self.master.after(0, _update)

    def main_loop(self):
        try:
            self.warm_up_logic()
            self.tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
            self.tts_thread.start()
            
            while True:
                trigger = self.detect_wake_word()
                if self.interrupted.is_set():
                    self.interrupted.clear()
                    self.set_state(BotStates.IDLE)
                    continue

                self.set_state(BotStates.LISTENING)
                audio_file = self.record_voice_adaptive()
                
                if not audio_file: 
                    self.set_state(BotStates.IDLE)
                    continue
                
                user_text = self.transcribe_audio(audio_file)
                if not user_text or user_text.strip() == "[ Silence ]":
                    self.set_state(BotStates.IDLE)
                    continue
                
                self.chat_and_respond(user_text)
                    
        except Exception as e:
            traceback.print_exc()
            self.set_state(BotStates.ERROR)

    def warm_up_logic(self):
        self.set_state(BotStates.WARMUP)
        try:
            ollama.generate(model=CURRENT_CONFIG["text_model"], prompt="", keep_alive=-1)
        except: pass
        self.play_sound("sounds/greeting_sounds")

    def detect_wake_word(self):
        self.set_state(BotStates.IDLE)
        self.ptt_event.clear()
        
        if self.oww_model: self.oww_model.reset()

        if self.oww_model is None:
            self.ptt_event.wait()
            self.ptt_event.clear()
            return "PTT"

        CHUNK_SIZE = 1280
        OWW_SAMPLE_RATE = 16000
        
        try:
            device_info = sd.query_devices(kind='input')
            native_rate = int(device_info['default_samplerate'])
        except: native_rate = 48000
            
        use_resampling = (native_rate != OWW_SAMPLE_RATE)
        input_rate = native_rate if use_resampling else OWW_SAMPLE_RATE
        input_chunk_size = int(CHUNK_SIZE * (input_rate / OWW_SAMPLE_RATE)) if use_resampling else CHUNK_SIZE

        try:
            with sd.InputStream(samplerate=input_rate, channels=1, dtype='int16', 
                                blocksize=input_chunk_size, device=INPUT_DEVICE_NAME) as stream:
                while True:
                    if self.ptt_event.is_set():
                        self.ptt_event.clear()
                        return "PTT"

                    data, _ = stream.read(input_chunk_size)
                    audio_data = np.frombuffer(data, dtype=np.int16)

                    if use_resampling:
                         audio_data = scipy.signal.resample(audio_data, CHUNK_SIZE).astype(np.int16)

                    prediction = self.oww_model.predict(audio_data)
                    for mdl in self.oww_model.prediction_buffer.keys():
                        if list(self.oww_model.prediction_buffer[mdl])[-1] > WAKE_WORD_THRESHOLD:
                            self.oww_model.reset() 
                            return "WAKE"
        except:
            self.ptt_event.wait()
            self.ptt_event.clear()
            return "PTT"

    def record_voice_adaptive(self, filename="input.wav"):
        time.sleep(0.3) 
        try:
            device_info = sd.query_devices(kind='input')
            samplerate = int(device_info['default_samplerate'])
        except: samplerate = 44100 
        
        silence_threshold = 0.006
        max_record_time = 15.0
        buffer = []
        silent_chunks = 0
        chunk_size = int(samplerate * 0.1)
        max_total_chunks = int(max_record_time / 0.1)
        
        try:
            with sd.InputStream(samplerate=samplerate, channels=1, device=INPUT_DEVICE_NAME) as stream:
                for _ in range(max_total_chunks):
                    data, _ = stream.read(chunk_size)
                    buffer.append(data.copy())
                    if (np.linalg.norm(data) / np.sqrt(len(data))) < silence_threshold:
                        silent_chunks += 1
                        if silent_chunks > 15 and len(buffer) > 30: break
                    else: silent_chunks = 0
        except: return None

        audio_data = np.concatenate(buffer, axis=0)
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(samplerate)
            wf.writeframes((audio_data * 32767).astype(np.int16).tobytes())
        
        self.play_sound("sounds/ack_sounds")
        return filename

    def transcribe_audio(self, filename):
        try:
            res = subprocess.run(["./piper/whisper-cli", "-m", "./piper/ggml-base.en.bin", "-l", "en", "-t", "4", "-f", filename, "--no-timestamps"], capture_output=True, text=True)
            return res.stdout.strip()
        except: return None

    def chat_and_respond(self, text, img_path=None):
        if "reset memory" in text.lower():
            self.session_memory = []
            self.save_chat_history()
            self.speak("Memory cleared.")
            self.set_state(BotStates.IDLE)
            return

        model = CURRENT_CONFIG["vision_model"] if img_path else CURRENT_CONFIG["text_model"]
        self.set_state(BotStates.THINKING, cam_path=img_path)
        self.thinking_sound_active.set()
        threading.Thread(target=self._thinking_sound_loop, daemon=True).start()

        messages = self.permanent_memory + self.session_memory + [{"role": "user", "content": text}]
        if img_path: messages = [{"role": "user", "content": text, "images": [img_path]}]

        full_response = ""
        is_action_mode = False
        
        try:
            stream = ollama.chat(model=model, messages=messages, stream=True, options=OLLAMA_OPTIONS)
            for chunk in stream:
                if self.interrupted.is_set(): break
                content = chunk['message']['content']
                full_response += content

                if '{"' in content or "action:" in content.lower():
                    is_action_mode = True
                    self.thinking_sound_active.clear()
                    continue 

                if not is_action_mode:
                    self.thinking_sound_active.clear()
                    if self.current_state != BotStates.SPEAKING:
                        self.set_state(BotStates.SPEAKING)
                    if any(punct in content for punct in ".!?"):
                        self.queue_tts(full_response)
                        full_response = "" 

            if is_action_mode:
                self.handle_tool_action(full_response, text)
            else:
                self.session_memory.append({"role": "assistant", "content": full_response})

        except: self.set_state(BotStates.ERROR)

        self.wait_for_tts()
        self.set_state(BotStates.IDLE)

    def handle_tool_action(self, json_text, original_query):
        try:
            match = re.search(r'\{.*\}', json_text, re.DOTALL)
            if not match: return
            data = json.loads(match.group(0))
            action = data.get("action"); value = data.get("value") or data.get("query")
            
            # --- ALIASES (Generic) ---
            ALIASES = {
                "search_news": "search_web", "google": "search_web", 
                "take_photo": "capture_image", "look": "capture_image",
                "check_time": "get_time"
            }
            if action in ALIASES: action = ALIASES[action]

            if action not in ["get_time", "capture_image", "search_web"]:
                if any(x in action for x in ["speak", "say", "summary"]):
                     self.speak(value)
                     return
                self.play_sound("sounds/error_sounds")
                return

            if action == "get_time":
                self.speak(f"It is {datetime.datetime.now().strftime('%I:%M %p')}.")
            
            elif action == "capture_image":
                new_img = self.capture_camera_image()
                if new_img: self.chat_and_respond(original_query, img_path=new_img)
            
            elif action == "search_web":
                try:
                    ddgs = DDGS()
                    results = list(ddgs.news(value, max_results=1)) or list(ddgs.text(value, max_results=1))
                    if results:
                        r = results[0]
                        summary = f"Title: {r.get('title')}\nSnippet: {r.get('body', r.get('snippet'))}"
                        self.chat_and_respond(f"Summarize this:\n{summary}")
                    else:
                        self.speak("No results found.")
                except: self.speak("I cannot connect to the internet.")

        except: self.speak("I am confused.")

    def capture_camera_image(self):
        self.set_state(BotStates.CAPTURING)
        try:
            subprocess.run(["rpicam-still", "-t", "100", "-o", CAM_IMAGE_FILE], check=True)
            rotation = CURRENT_CONFIG.get("camera_rotation", 0)
            if rotation != 0:
                img = Image.open(CAM_IMAGE_FILE)
                img.rotate(rotation, expand=True).save(CAM_IMAGE_FILE)
            return CAM_IMAGE_FILE
        except: return None

    # FIX: Restored random sound selection logic
    def play_sound(self, path):
        if not os.path.exists(path): return
        
        target_file = path
        
        # If it's a directory, pick a random .wav
        if os.path.isdir(path):
            files = [f for f in os.listdir(path) if f.endswith(".wav")]
            if not files: return
            target_file = os.path.join(path, random.choice(files))
            
        try:
            with wave.open(target_file, 'rb') as wf:
                file_sr = wf.getframerate()
                data = wf.readframes(wf.getnframes())
                audio = np.frombuffer(data, dtype=np.int16)
            try:
                native_rate = int(sd.query_devices(kind='output')['default_samplerate'])
            except: native_rate = 48000
            
            if file_sr != native_rate:
                num = int(len(audio) * (native_rate / file_sr))
                audio = scipy.signal.resample(audio, num).astype(np.int16)
                sd.play(audio, native_rate)
            else:
                sd.play(audio, file_sr)
            sd.wait()
        except: pass

    def queue_tts(self, text):
        clean = re.sub(r"[^\w\s,.!?-]", "", text).strip()
        if clean: 
            with self.tts_queue_lock: self.tts_queue.append(clean)

    def wait_for_tts(self):
        while self.tts_queue or self.tts_active.is_set():
            if self.interrupted.is_set(): break
            time.sleep(0.1)

    def _tts_worker(self):
        while True:
            text = None
            with self.tts_queue_lock:
                if self.tts_queue:
                    text = self.tts_queue.pop(0)
                    self.tts_active.set()
            if text:
                self.speak(text)
                self.tts_active.clear()
            else: time.sleep(0.05)

    def speak(self, text):
        time.sleep(0.2)
        voice_model = CURRENT_CONFIG.get("voice_model", "piper/en_GB-semaine-medium.onnx")
        try:
            self.current_audio_process = subprocess.Popen(
                ["./piper/piper", "--model", voice_model, "--output-raw"], 
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            self.current_audio_process.stdin.write(text.encode() + b'\n')
            self.current_audio_process.stdin.close() 
            
            with sd.RawOutputStream(samplerate=22050, channels=1, dtype='int16') as stream:
                while True:
                    if self.interrupted.is_set(): break
                    data = self.current_audio_process.stdout.read(4096)
                    if not data: break
                    stream.write(np.frombuffer(data, dtype=np.int16).tobytes())
        except: pass
        finally: self.current_audio_process = None

    def handle_ptt_toggle(self, event=None): self.ptt_event.set()
    
    def handle_speaking_interrupt(self, event=None):
        if self.current_state == BotStates.SPEAKING:
            self.interrupted.set()
            if self.current_audio_process: self.current_audio_process.terminate()

    def load_chat_history(self):
        sys_prompt = [{"role": "system", "content": CURRENT_CONFIG.get("system_prompt")}]
        if not CURRENT_CONFIG.get("chat_memory", True): return sys_prompt
        try: return json.load(open(MEMORY_FILE))
        except: return sys_prompt

    def save_chat_history(self):
        if CURRENT_CONFIG.get("chat_memory", True):
            with open(MEMORY_FILE, "w") as f:
                json.dump(self.permanent_memory + self.session_memory, f, indent=4)

    def _thinking_sound_loop(self):
        while self.thinking_sound_active.is_set():
            # FIX: Point to the FOLDER, not a file
            self.play_sound("sounds/thinking_sounds")
            time.sleep(2)

if __name__ == "__main__":
    root = tk.Tk()
    app = BotGUI(root)
    root.mainloop()