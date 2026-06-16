# =========================================================================
#  Be More Agent · 配置与常量
#  从 agent.py 抽出：纯配置 / 设备解析 / 计时工具 / 状态枚举。
#  本模块无运行时状态、无 GUI 依赖，可被 agent.py / prompts.py / flow.py 复用。
# =========================================================================

import os
import json
import time
import contextlib

import sounddevice as sd

# =========================================================================
# 1. CONFIGURATION & CONSTANTS
# =========================================================================

CONFIG_FILE = "config.json"
MEMORY_FILE = "memory.json"
WAKE_WORD_MODEL = "./wakeword.onnx"
WAKE_WORD_THRESHOLD = 0.5

# HARDWARE SETTINGS
INPUT_DEVICE_NAME = None

DEFAULT_CONFIG = {
    "text_model": "gemma3:1b",
    "voice_model": "piper/en_GB-semaine-medium.onnx",
    "chat_memory": True,
    "system_prompt_extras": "",
    "input_device": None,
    "input_sample_rate": None,
    "whisper_model": "ggml-base.en.bin",
    "whisper_lang": "en",
    # --- VAD（免手持续监听）---
    "vad_aggressiveness": 3,   # webrtcvad 灵敏度 0~3，越大越严格（越不易把噪声当人声）
    "vad_start_ms": 150,       # 连续多少毫秒判定为人声才算"开始说话"（防瞬时噪声误触发）
    "vad_silence_ms": 900,     # 尾部静音多久判定"说完"
    "vad_max_record_ms": 30000,# 单次最长录音
    "vad_preroll_ms": 300,     # 起始前回看缓冲，避免吞掉第一个字
}

# LLM SETTINGS
OLLAMA_OPTIONS = {
    'keep_alive': '-1',
    'num_thread': 4,
    'temperature': 0.7,
    'top_k': 40,
    'top_p': 0.9
}


@contextlib.contextmanager
def timed_block(label):
    t0 = time.perf_counter()
    print(f"[TIMER] >>> {label}", flush=True)
    try:
        yield
    finally:
        print(f"[TIMER] <<< {label}  {time.perf_counter()-t0:.2f}s", flush=True)


def load_config():
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                user_config = json.load(f)
                config.update(user_config)
        except Exception as e:
            print(f"Config Error: {e}. Using defaults.")
    return config

CURRENT_CONFIG = load_config()
TEXT_MODEL = CURRENT_CONFIG["text_model"]


def resolve_input_device(config):
    requested = config.get("input_device")
    if requested in (None, "", "default"):
        return None

    try:
        devices = sd.query_devices()
    except Exception as e:
        print(f"[AUDIO] Device query failed: {e}", flush=True)
        return None

    if isinstance(requested, int) or (isinstance(requested, str) and requested.isdigit()):
        index = int(requested)
        if 0 <= index < len(devices):
            return index
        print(f"[AUDIO] Input device index not found: {index}", flush=True)
        return None

    requested_lower = str(requested).lower()
    for idx, dev in enumerate(devices):
        print(f"[AUDIO DEBUG] Index {idx}: {dev.get('name')} (In: {dev.get('max_input_channels')})", flush=True) # DEBUG LINE
        if dev.get("max_input_channels", 0) > 0 and requested_lower in dev.get("name", "").lower():
            return idx

    print(f"[AUDIO] Input device name not found: {requested}", flush=True)
    return None

INPUT_DEVICE_NAME = resolve_input_device(CURRENT_CONFIG)
if INPUT_DEVICE_NAME is not None:
    try:
        device_info = sd.query_devices(INPUT_DEVICE_NAME)
        print(f"[AUDIO] Using input device: {device_info.get('name', INPUT_DEVICE_NAME)}", flush=True)
    except Exception:
        print(f"[AUDIO] Using input device index: {INPUT_DEVICE_NAME}", flush=True)

def choose_input_samplerate(device, preferred=None):
    candidates = []
    if preferred:
        candidates.append(preferred)
    try:
        device_info = sd.query_devices(device)
        print(f"[AUDIO DEBUG] Device Info: {device_info}", flush=True) # DEBUG
        if "default_samplerate" in device_info:
            candidates.append(int(device_info["default_samplerate"]))
    except Exception as e:
        print(f"[AUDIO DEBUG] Query failed: {e}", flush=True)
        pass

    candidates.extend([48000, 44100, 32000, 16000])
    seen = set()
    for rate in candidates:
        if not rate or rate in seen:
            continue
        seen.add(rate)
        try:
            sd.check_input_settings(device=device, samplerate=rate, channels=1, dtype="int16")
            return rate
        except Exception:
            continue

    return int(candidates[0]) if candidates else 44100


class BotStates:
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    WARMUP = "warmup"
    GREETING = "greeting"
    SLEEP = "sleep"
