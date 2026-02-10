# Be More Agent 🤖
**A Customizable, Offline-First AI Agent for Raspberry Pi**

[![Watch the Demo](https://img.youtube.com/vi/l5ggH-YhuAw/maxresdefault.jpg)](https://youtu.be/l5ggH-YhuAw)

![Python](https://img.shields.io/badge/Python-3.9%2B-blue) ![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi-red) ![License](https://img.shields.io/badge/License-MIT-green)

This project turns a Raspberry Pi into a fully functional, conversational AI agent. Unlike cloud-based assistants, this agent runs **100% locally** on your device. It listens for a wake word, processes speech, "thinks" using a local Large Language Model (LLM), and speaks back with a low-latency neural voice—all while displaying reactive face animations.

**It comes with a default personality, but it is designed as a blank canvas:** You can easily swap the face images and sound effects to create your own character!

## ✨ Features

* **100% Local Intelligence**: Powered by **Ollama** (LLM) and **Whisper.cpp** (Speech-to-Text). No API fees, no cloud data usage.
* **Open Source Wake Word**: Wakes up to your custom model using **OpenWakeWord** (Offline & Free).
* **Hardware-Aware Audio**: Automatically detects your microphone's sample rate to prevent ALSA errors on Raspberry Pi.
* **Smart Web Search**: Prioritizes news headlines for queries like "Search for news about..." and falls back to general web results.
* **Reactive Faces**: The GUI updates the character's face based on its state (Listening, Thinking, Speaking, Idle).
* **Fast Text-to-Speech**: Uses **Piper TTS** for low-latency, high-quality voice generation on the Pi.
* **Vision Capable**: Can "see" and describe the world using a connected camera and the **Moondream** vision model.

## 🛠️ Hardware Requirements

* **Raspberry Pi 5** (Recommended)
* USB Microphone and Speaker
* LCD Screen
* Raspberry Pi Camera Module

---

## 📂 Project Structure

```text
be-more-agent/
├── agent.py                   # The main script
├── setup.sh                   # Auto-installer script
├── wakeword.onnx              # OpenWakeWord model file (Required)
├── config.json                # User configuration
├── requirements.txt           # Python dependencies
├── whisper.cpp/               # Speech-to-Text engine (Manual or Auto install)
├── piper/                     # Piper TTS folder (Created by setup.sh - DO NOT COMMIT)
│   ├── piper                  # Executable binary
│   └── en_GB-semaine...onnx   # Voice model
├── sounds/                    # Sound effects folder
│   ├── greeting_sounds/       # Startup .wav files
│   ├── thinking_sounds/       # Looping .wav files
│   ├── ack_sounds/            # "I heard you" .wav files
│   └── error_sounds/          # "Unknown command" .wav files
└── faces/                     # Face images folder
    ├── idle/                  # .png sequence for idle state
    ├── listening/             # .png sequence for listening
    ├── thinking/              # .png sequence for thinking
    ├── speaking/              # .png sequence for speaking
    ├── error/                 # .png sequence for errors
    └── warmup/                # .png sequence for startup
```

---

## 🚀 Installation

### Option 1: Quick Install (Recommended)
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/brenpoly/be-more-agent.git
    cd be-more-agent
    ```

2.  **Create & Activate Virtual Environment (Required):**
    *You must do this to install Python libraries on Raspberry Pi.*
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Run the setup script:**
    This script installs system dependencies, downloads voice models, compiles Whisper, and sets up the Python environment.
    ```bash
    chmod +x setup.sh
    ./setup.sh
    ```

4.  **Add your Wake Word:**
    Place your trained `.onnx` model in the root folder and rename it to `wakeword.onnx`.

5.  **Run the Agent:**
    ```bash
    python agent.py
    ```

### Option 2: Manual Install
If you prefer to set it up yourself:

1.  **Install System Deps:**
    ```bash
    sudo apt install python3-tk libasound2-dev libportaudio2 libatlas-base-dev cmake build-essential espeak-ng git
    ```

2.  **Create Venv & Install Python Deps:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Get Piper:** Download the [Piper aarch64 binary](https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz) and a [voice model](https://huggingface.co/rhasspy/piper-voices), extract them into a folder named `piper/`.

4.  **Get Whisper.cpp:** Clone and compile the hearing engine.
    ```bash
    git clone [https://github.com/ggerganov/whisper.cpp](https://github.com/ggerganov/whisper.cpp)
    cd whisper.cpp
    make -j4
    ./models/download-ggml-model.sh base.en
    cd ..
    ```

5.  **Pull Ollama Models:**
    ```bash
    ollama pull gemma3:1b
    ollama pull moondream
    ```

---

## 📂 Configuration (`config.json`)

You can modify the hardware behavior and personality in `config.json`.

```json
{
    "text_model": "gemma3:1b",
    "vision_model": "moondream",
    "voice_model": "piper/en_GB-semaine-medium.onnx",
    "system_prompt": "You are a helpful robot assistant running on a Raspberry Pi. You have access to the following tools. To use one, reply ONLY with the JSON format shown:\n\n1. Check Time: {\"action\": \"get_time\"}\n2. Take Photo: {\"action\": \"capture_image\"}\n3. Search Web: {\"action\": \"search_web\", \"query\": \"your search term\"}\n\nIf no tool is needed, just reply normally. Keep responses short and friendly.",
    "chat_memory": true,
    "camera_rotation": 180
}

---

## 🎨 Customizing Your Character

This software is just the brain. You can give it a new personality by replacing the assets:

1.  **Faces:** The script looks for PNG sequences in `faces/[state]/`. It will loop through all images found in the folder to create an animation.
2.  **Sounds:** Put multiple `.wav` files in the `sounds/[category]/` folders. The robot will pick one at random each time (e.g., different "thinking" hums or "error" buzzes).

---

## ⚠️ Troubleshooting

* **🔊 Audio Errors:** If you see ALSA errors in the terminal, don't worry. The script automatically detects your microphone's native sample rate and resamples audio on the fly to prevent crashes.
* **Web Search:** This agent uses `DuckDuckGo` to search the web. It prioritizes News headlines first, then falls back to general text search.
* **Security:** This script executes local commands (like `rpicam-still`). Do not modify the code to accept raw shell commands from the LLM.

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.
**Disclaimer:** This software is provided "as is", without warranty of any kind.

## ⚖️ Legal Disclaimer

**"BMO"** and **"Adventure Time"** are trademarks of **Cartoon Network** (Warner Bros. Discovery).

This project is a **fan creation** built for educational and hobbyist purposes only. It is **not** affiliated with, endorsed by, or connected to Cartoon Network or the official Adventure Time brand in any way.

The "Be More Agent" software is provided as a generic framework. No copyrighted assets (images or audio from the show) are included in this repository.
