# Be More Agent 🤖
**A Customizable, Offline-First AI Agent for Windows**

![Python](https://img.shields.io/badge/Python-3.9%2B-blue) ![Platform](https://img.shields.io/badge/Platform-Windows-blue) ![License](https://img.shields.io/badge/License-MIT-green)

This project turns a Windows PC into a fully functional, conversational AI agent. Unlike cloud-based assistants, this agent runs **100% locally** on your machine. It listens for a wake word, processes speech, "thinks" using a local Large Language Model (LLM), and speaks back with a low-latency neural voice—all while displaying reactive face animations.

**It is designed as a blank canvas:** You can easily swap the face images and sound effects to create your own character!

## ✨ Features

* **100% Local Intelligence**: Powered by **Ollama** (LLM) and **Whisper** (Speech-to-Text). No API fees, no cloud data usage.
* **Fast Speech-to-Text**: Switchable STT backend — **faster-whisper** (in-process, ~2.7x faster) or **whisper.cpp** (subprocess).
* **Open Source Wake Word**: Wakes up to your custom model using **OpenWakeWord** (Offline & Free). No access keys required.
* **Smart Web Search**: Uses DuckDuckGo to find real-time news and information when the LLM doesn't know the answer.
* **Reactive Faces**: The GUI updates the character's face based on its state (Listening, Thinking, Speaking, Idle).
* **Fast Text-to-Speech**: Uses **Piper TTS** for low-latency, high-quality voice generation.
* **Vision Capable**: Can "see" and describe the world using your webcam and the **Moondream** vision model.
* **Push-to-Talk Mode**: Delete/rename `wakeword.onnx` to use Enter-to-talk instead of the wake word.

---

## 📂 Project Structure

```text
be-more-agent/
├── agent.py                   # The main brain script
├── setup_windows.ps1          # Auto-installer script (PowerShell)
├── start_agent_windows.ps1    # Launcher
├── wakeword.onnx              # OpenWakeWord model (The "Ear")
├── config.json                # User settings (Models, Prompt, Hardware)
├── requirements.txt           # Python dependencies
├── whisper.cpp/               # Speech-to-Text engine
├── piper/                     # Piper TTS engine & voice models
├── sounds/                    # Sound effects folder
│   ├── greeting_sounds/       # Startup .wav files
│   ├── thinking_sounds/       # Looping .wav files
│   ├── ack_sounds/            # "I heard you" .wav files
│   └── error_sounds/          # Error/Confusion .wav files
├── faces/                     # Face images folder
│   ├── idle/                  # .png sequence for idle state
│   ├── listening/             # .png sequence for listening
│   ├── thinking/              # .png sequence for thinking
│   ├── speaking/              # .png sequence for speaking
│   ├── error/                 # .png sequence for errors
│   └── warmup/                # .png sequence for startup
└── tests/                     # Per-module verification scripts
```

---

## 🚀 Installation (Windows 11)

### 1. Prerequisites
1. **Python 3.10+** from [python.org](https://www.python.org/downloads/) — tick **"Add to PATH"** during install.
2. **Ollama** for Windows from [ollama.com/download/windows](https://ollama.com/download/windows). Your NVIDIA GPU (CUDA) is used automatically.

### 2. Pull the AI models
```powershell
ollama pull gemma3:1b
ollama pull moondream
```

### 3. One-shot setup
Open **PowerShell** in the project folder and run:
```powershell
Set-ExecutionPolicy -Scope Process Bypass; .\setup_windows.ps1
```
This installs everything: the Python venv, whisper.cpp (with its runtime DLLs), the Whisper model, Piper TTS, the voice model, the default wake word, and all Python dependencies.

### 4. Run the Agent
```powershell
.\start_agent_windows.ps1
```

### 5. Verify each module
```powershell
python tests\run_all_tests.py            # run everything, one summary
python tests\test_audio.py               # microphone + speaker devices
python tests\test_wakeword.py            # wake-word model loads & predicts
python tests\test_stt.py                 # whisper.cpp transcribes a sample
python tests\test_tts.py                 # piper generates speech
python tests\test_ollama.py              # LLM server + model responds
python tests\test_search.py              # DuckDuckGo web search
python tests\test_camera.py              # webcam captures a frame
python tests\test_record.py              # records 3s of mic audio
```

Each prints `[PASS]`/`[FAIL]` and exits with code `0`/`1` so you can script them.
`tests\test_stt.py` auto-generates its own spoken sample via Piper when possible.
`tests\test_ollama.py` additionally checks your graphics hardware and reports whether the LLM will run on the GPU or fall back to the CPU.

---

## 📂 Configuration (`config.json`)

You can modify the hardware behavior and personality in `config.json`:

```json
{
    "text_model": "gemma3:1b",
    "vision_model": "moondream",
    "voice_model": "piper/en_GB-semaine-medium.onnx",
    "stt_engine": "faster_whisper",
    "faster_whisper_model": "base.en",
    "whisper_binary": "whisper.cpp/build/bin/whisper-cli.exe",
    "whisper_model": "whisper.cpp/models/ggml-base.en.bin",
    "piper_binary": "piper/piper.exe",
    "piper_rate": 22050,
    "chat_memory": true,
    "camera_rotation": 0,
    "camera_index": 0,
    "fullscreen": false,
    "system_prompt_extras": "You are a helpful robot assistant. Keep responses short and cute.",
    "input_device": null,
    "input_sample_rate": 44100
}
```

* `stt_engine`: `"faster_whisper"` (default) or `"whisper_cpp"`.
  * **`faster_whisper`** — in-process, model stays loaded in RAM, ~2.7x faster transcription per utterance (measured: ~0.7s vs ~1.8s for a 3s clip). Model is downloaded from Hugging Face on first run (cached offline afterwards) and set with `faster_whisper_model` (e.g. `base.en`, `small.en`).
  * **`whisper_cpp`** — uses the `whisper-cli.exe` subprocess. No extra Python deps, works fully offline, slightly slower due to per-utterance process/model startup.

* `input_device`: `null` = auto-detect your default microphone. Set a device **index** or **name** to force one.
* `input_sample_rate`: your mic's native rate (the agent falls back to 16k/44.1k/48k automatically).
* `fullscreen`: set `true` for kiosk-style display.
* `system_prompt_extras`: appended to the built-in system prompt to tune the personality.

---

## 🎨 Customizing Your Character

This software is a generic framework. You can give it a new personality by replacing the assets:

1.  **Faces:** The script looks for PNG sequences in `faces/[state]/`. It will loop through all images found in the folder.
2.  **Sounds:** Put multiple `.wav` files in the `sounds/[category]/` folders. The robot will pick one at random each time (e.g., different "thinking" hums or "error" buzzes).

---

## 🗣️ The Custom BMO Voice

This project features a custom, locally fine-tuned text-to-speech model to make the agent sound authentic!

During `setup_windows.ps1`, you can choose to download the compiled `.onnx` model and its `.json` configuration file from the [Releases page](https://github.com/brenpoly/be-more-agent/releases) into a local `voices/` directory.

**Manual Installation:**
1. Download `bmo.onnx` and `bmo.onnx.json` from the [v1.0-voice release](https://github.com/brenpoly/be-more-agent/releases/tag/v1.0-voice).
2. Create a folder named `voices/` in the root directory of this repository.
3. Place both downloaded files inside the `voices/` folder.
4. Ensure your `config.json` file points to the new model:
   ```json
   "voice_model": "voices/bmo-custom.onnx"
   ```

---

## 🖥️ Hardware & GPU Compatibility

Every component except the LLM runs on the **CPU** (Whisper.cpp, Piper TTS, OpenWakeWord, OpenCV), so the agent works on any Windows PC. Only **Ollama** (`gemma3:1b` + `moondream`) benefits from a dedicated GPU.

| Hardware | Behavior |
|---|---|
| **iGPU only** (Intel UHD/Iris Xe, AMD Radeon integrated) | Works. Ollama falls back to CPU — the small 1B model stays responsive, but the Moondream vision model is slow. |
| **iGPU + NVIDIA dGPU** | Best performance. Ollama auto-detects CUDA and offloads both models to VRAM. |
| **iGPU + AMD dGPU** | Works, but Ollama's native Windows AMD support is limited — expect CPU fallback (or use the Vulkan backend / WSL2). |
| **iGPU + Intel Arc dGPU** | Works, but stock Ollama ignores Intel GPUs on Windows (CPU fallback) unless IPEX-LLM is configured. |

> **Hybrid laptops (Intel iGPU + NVIDIA):** Windows may launch Ollama on the iGPU. Force the dGPU in **Settings → System → Display → Graphics** (set Ollama to *High performance*), then verify with `ollama ps` — it should show `GPU`, not `100% CPU`.

Run `python tests\test_ollama.py` to see your GPU status and whether the LLM is actually using it.

---

## ⚠️ Troubleshooting

* **"No search library found":** Ensure you are in the virtual environment and `ddgs` is installed via pip (`venv\Scripts\pip install ddgs`).
* **Whisper crashes at startup (exit code 0xC0000135):** The whisper.cpp DLLs are missing. Re-run `setup_windows.ps1` so it copies the full `Release/*` (including `whisper.dll`, `ggml.dll`, etc.) into `whisper.cpp\build\bin\`.
* **No camera frames:** Check `camera_index` in `config.json` (your built-in webcam may not be index 0).
* **Audio Glitches / Wrong Speed:** If the voice sounds fast or slow, ensure `piper_rate` in `config.json` matches your `.onnx` model's `"sample_rate"` (check its `.json` file). "Medium" Piper voices use 22050.
* **Deeps/"demonic" BMO voice:** Sample-rate mismatch (see above) or the model's `"length_scale"` is set too high in `voices/bmo-custom.onnx.json` — lower it toward `1.0`.

## 📄 License
This project is dual-licensed:

* **Software / Code:** All source code is licensed under the [MIT License](LICENSE).
* **Hardware / 3D Models:** The `.obj`, `.stl`, and other 3D modeling files associated with the physical case are licensed under the [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License](https://creativecommons.org/licenses/by-nc-sa/4.0/)

## ⚖️ Legal Disclaimer
Disclaimer: Fan Project
This repository and the associated voice model are a non-commercial, open-source fan project. "BMO" and Adventure Time are registered trademarks and copyrights of Cartoon Network and Warner Bros. Discovery. This project is not affiliated with, endorsed by, or sponsored by Cartoon Network or its parent companies.

Voice Model Attribution
The text-to-speech capabilities of this project are powered by Piper. The custom voice model was fine-tuned locally using Piper's base "Amy" model (en_US-amy-medium). The original Piper engine and base models are developed by the Rhasspy project and distributed under the MIT License.
