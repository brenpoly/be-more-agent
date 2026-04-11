# Looi — AI Desktop Companion

Looi is a robot-inspired AI desktop companion powered by **Google Gemini**. It features an animated expressive face, real-time face tracking, voice chat, mood detection, and more.

![Looi Face Expressions](https://raw.githubusercontent.com/Muralikrishankp/looi-assistant/main/docs/preview.png)

## Features

- **Animated Face** — Expressive eyes and mouth (idle, listening, happy, surprised, sad)
- **Face Tracking** — Webcam-based pupil tracking that follows your face
- **Mood Detection** — Gemini Vision reads your emotion from the camera every ~45 seconds
- **Voice Chat** — Push-to-talk voice recognition powered by Google Speech API
- **Gemini AI** — Streaming conversation with Gemini 2.0 Flash
- **TTS Responses** — Natural text-to-speech via gTTS + pygame
- **Web Search** — DuckDuckGo search tool built-in
- **Chat Memory** — Remembers the last 10 turns of conversation

## Controls

| Key | Action |
|-----|--------|
| `SPACE` or `ENTER` | Talk (push-to-talk) |
| `ESC` | Quit |

## Quick Start

### 1. Get a Gemini API Key

Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and create a free API key.

### 2. Install & Run

```bash
git clone https://github.com/Muralikrishankp/looi-assistant.git
cd looi-assistant

# Auto-install all dependencies
bash setup.sh

# Add your API key
cp config.example.json config.json
# Edit config.json and paste your Gemini API key

# Run Looi
source venv/bin/activate
python looi.py
```

## Requirements

- Python 3.10+
- Webcam (optional — for face tracking and mood detection)
- Microphone (for voice chat)
- Internet connection (for Gemini API + TTS)

See `requirements.txt` for Python dependencies. `setup.sh` installs everything automatically.

## Configuration (`config.json`)

| Key | Default | Description |
|-----|---------|-------------|
| `gemini_api_key` | — | Your Gemini API key (**required**) |
| `gemini_model` | `gemini-2.0-flash-lite` | Chat model |
| `vision_model` | `gemini-2.0-flash-lite` | Vision/mood model |
| `tts_lang` | `en` | TTS language code |
| `chat_memory` | `true` | Remember conversation history |
| `face_tracking` | `true` | Enable webcam pupil tracking |
| `mood_detection` | `true` | Enable mood detection from camera |
| `mood_interval_s` | `45` | Seconds between mood checks |
| `camera_index` | `0` | Webcam index (0 = default camera) |

## Project Structure

```
looi-assistant/
├── looi.py              # Main application (~950 lines)
├── config.json          # Your config (gitignored)
├── config.example.json  # Config template
├── requirements.txt     # Python dependencies
└── setup.sh             # One-shot install script
```

## License

MIT
