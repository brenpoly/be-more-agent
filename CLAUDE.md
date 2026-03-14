# CLAUDE.md — AI Assistant Guide for be-more-agent

This document describes the codebase structure, development conventions, and workflows for AI assistants working in this repository.

## Project Overview

**be-more-agent** is a voice-activated AI desktop companion designed for Raspberry Pi. It uses a state machine loop: idle → wake word detection → listening → transcription → LLM inference → speech response → idle.

All core logic lives in a single file: `agent.py`.

---

## Repository Layout

```
be-more-agent/
├── agent.py            # Entire application (~923 lines)
├── config.json         # Runtime configuration (gitignored)
├── requirements.txt    # Python pip dependencies
├── setup.sh            # One-shot install script for Raspberry Pi
├── wakeword.onnx       # Default OpenWakeWord model
├── faces/              # Animation frame sequences (PNG files per state)
│   ├── idle/
│   ├── listening/
│   ├── thinking/
│   ├── speaking/
│   ├── error/
│   ├── capturing/
│   └── warmup/
└── sounds/             # Audio cues (WAV files)
    ├── ack_sounds/
    ├── greeting_sounds/
    └── thinking_sounds/
```

Runtime-only paths (not in repo, created by setup.sh or at runtime):
- `venv/` — Python virtual environment
- `piper/` — Piper TTS binary and voice models
- `whisper.cpp/` — Whisper speech-to-text binary and models
- `memory.json` — Persisted chat history (last 10 turns)

---

## Key Concepts

### State Machine

The bot moves through states defined in `BotStates` (agent.py ~line 95):

| State | Description |
|---|---|
| `IDLE` | Waiting for wake word or PTT |
| `LISTENING` | Recording voice input |
| `THINKING` | Transcribing + calling LLM |
| `SPEAKING` | Playing TTS audio |
| `CAPTURING` | Taking a photo |
| `ERROR` | Error occurred |
| `WARMUP` | Startup model pre-loading |

Each state has a corresponding animation in `faces/<state>/` and a status label shown in the HUD.

### Configuration (`config.json`)

```json
{
    "text_model": "gemma3:1b",
    "vision_model": "moondream",
    "voice_model": "piper/en_GB-semaine-medium.onnx",
    "chat_memory": true,
    "camera_rotation": 180
}
```

Never hardcode model names or paths — always read from `config.json` via `load_config()`.

### Tool / Action System

The LLM can emit a JSON action block. Supported tools (routed in `execute_action_and_get_result()`):

| Tool name (+ aliases) | What it does |
|---|---|
| `get_time` | Returns current datetime |
| `search_web` (`google`, `search`, `find`, `duckduckgo`) | DuckDuckGo web search |
| `capture_image` (`look`, `see`, `camera`, `photo`, `vision`, `moondream`) | Captures photo via `rpicam-still`, sends to vision model |

To add a new tool: add an alias branch in `execute_action_and_get_result()` and describe the tool in the system prompt.

---

## Architecture Details

### Threading Model

| Thread | Purpose |
|---|---|
| Main tkinter thread | GUI event loop + animation |
| `_main_execution_thread` | Runs `safe_main_execution()` — the entire voice/chat loop |
| `_tts_thread` (daemon) | `_tts_worker()` — dequeues text and calls `speak()` |
| sounddevice callbacks | Mic capture and speaker playback streams |

**Key signals (threading.Event):**
- `_ptt_active` — PTT key held
- `_interrupt_speaking` — Space key pressed to cut TTS
- `_tts_queue` (Queue) — text chunks sent to TTS worker

### Audio Pipeline

1. **Input:** `sounddevice.InputStream` → raw PCM buffer
2. **Wake word:** OpenWakeWord on 16 kHz mono frames
3. **Recording:** silence-gated via RMS threshold (`SILENCE_THRESHOLD = 150`, `SILENCE_DURATION = 1.5s`)
4. **Transcription:** `whisper-cli` subprocess with `--language en`
5. **Output (TTS):** `piper` subprocess → raw s16le PCM → `sounddevice.OutputStream`
6. **Resampling:** `scipy.signal.resample_poly` used whenever hardware sample rate differs from target rate

### LLM Integration

- Uses the `ollama` Python library with `stream=True`
- Streaming chunks are displayed in the GUI (`_stream_to_text`) and accumulated
- Vision queries encode an image as base64 and pass it to the vision model
- The system prompt (built at startup from config) instructs the model to emit `{"action": "...", "query": "..."}` for tool use

---

## Development Workflow

### Setup (Raspberry Pi)

```bash
git clone <repo-url>
cd be-more-agent
bash setup.sh
source venv/bin/activate
python agent.py
```

### Running Locally (non-Pi)

Ollama must be running separately:

```bash
ollama serve
```

Then:

```bash
source venv/bin/activate
python agent.py
```

Camera and wake word will gracefully fall back or be skipped if hardware is absent.

### Dependencies

Install Python deps:

```bash
pip install -r requirements.txt
```

External binaries (managed by `setup.sh`):
- `piper` — TTS engine
- `whisper.cpp` — speech-to-text (must be compiled separately)
- `ollama` — LLM server (must be installed separately)

### No Formal Test Suite

There are no automated tests. Validate changes manually by running `agent.py` and exercising each mode (wake word, PTT, web search, vision).

---

## Coding Conventions

### Style

- Standard Python (no type hints, no docstrings in existing code — don't add them to unchanged code)
- Single-class design: all state and methods belong to `BotGUI`
- Module-level constants are `SCREAMING_SNAKE_CASE`
- Private methods prefixed with `_` (e.g., `_tts_worker`, `_stream_to_text`)

### Error Handling

- Broad `try/except` blocks with `pass` or logging are the existing pattern
- Graceful degradation is preferred over crashes (e.g., PTT-only if wake word fails)
- Do not raise exceptions out of tkinter callbacks

### Adding New States

1. Add the state name to `BotStates`
2. Create a `faces/<new_state>/` directory with PNG frame sequence
3. Call `self.set_state(BotStates.NEW_STATE)` where appropriate
4. `load_animations()` and `update_animation()` will handle the rest automatically

### Adding New Sounds

Drop WAV files into the appropriate subdirectory under `sounds/`. Use `get_random_sound()` to retrieve a random file from a directory, then `play_sound()` to play it.

### Modifying the System Prompt

The system prompt is assembled at module load time from `config.json`. Edit the string construction around the `system_prompt` variable (early in the file). Keep prompt changes minimal and focused — the model is small (1B params by default).

---

## Key Files Reference

| File | Lines | Purpose |
|---|---|---|
| `agent.py` | ~923 | Entire application |
| `config.json` | 8 | Runtime config (gitignored) |
| `requirements.txt` | 8 | Pip dependencies |
| `setup.sh` | ~74 | Raspberry Pi install automation |
| `wakeword.onnx` | binary | Default wake word model |

### Important Line Ranges in `agent.py`

| Section | Approx. lines |
|---|---|
| Imports & constants | 1–94 |
| `BotStates` | 95–102 |
| Config loading & Ollama options | 103–141 |
| `BotGUI.__init__` | 142–220 |
| Animation loading & update | 221–280 |
| State management & HUD | 281–340 |
| Wake word / PTT detection | 341–440 |
| Voice recording | 441–530 |
| Warmup | 531–560 |
| Tool execution | 561–630 |
| Chat & LLM response | 631–780 |
| Speech (Piper TTS) | 781–850 |
| Sound effects | 851–890 |
| Memory persistence | 891–915 |
| Main entry point | 916–923 |

---

## Important Constraints

- **Do not introduce cloud dependencies.** The project is intentionally local-first; all AI runs on-device.
- **Do not refactor into multiple files** unless explicitly asked. The single-file design is intentional for portability.
- **Do not add a test framework** unless explicitly asked.
- **Preserve the state machine contract** — every code path must eventually call `set_state()` to return to `IDLE` or the bot will hang.
- **Audio streams are sensitive** — avoid blocking the main thread with long synchronous operations; use the existing threading pattern.
- **config.json is gitignored** — never commit secrets or user-specific paths.
