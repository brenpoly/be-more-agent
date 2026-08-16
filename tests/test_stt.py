import os
import subprocess
import sys
import wave
from common import result, load_config

def _synthesize_sample():
    """Generate a spoken test wav using Piper so Whisper has real speech to transcribe."""
    cfg = load_config()
    piper = cfg.get("piper_binary", "piper/piper.exe")
    voice = cfg.get("voice_model", "piper/en_GB-semaine-medium.onnx")
    if not (os.path.exists(piper) and os.path.exists(voice)):
        return None
    tmp_dir = os.path.dirname(os.path.abspath(__file__))
    out_wav = os.path.join(tmp_dir, "test_sample.wav")
    raw = os.path.join(tmp_dir, "sample.raw")
    try:
        proc = subprocess.Popen(
            [piper, "--model", voice, "--output-raw"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        proc.stdin.write(b"This is a test of the speech recognition system.\n")
        proc.stdin.close()
        data = proc.stdout.read()
        proc.wait(timeout=60)
        if len(data) < 1000:
            return None
        with wave.open(out_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(data)
        return out_wav
    except Exception as e:
        print(f"  (sample synthesis skipped: {e})")
        return None

def test_stt():
    cfg = load_config()
    binary = cfg.get("whisper_binary", "whisper.cpp/build/bin/whisper-cli.exe")
    model_path = cfg.get("whisper_model", "whisper.cpp/models/ggml-base.en.bin")

    if not os.path.exists(binary):
        return result("Whisper binary exists", False, binary)
    if not os.path.exists(model_path):
        return result("Whisper model exists", False, model_path)

    test_wav = os.path.join(os.path.dirname(__file__), "test_sample.wav")
    if not os.path.exists(test_wav):
        test_wav = _synthesize_sample()
    if not test_wav or not os.path.exists(test_wav):
        print("  Skipping transcription: no test_sample.wav in tests/ and Piper unavailable")
        return True

    try:
        r = subprocess.run(
            [binary, "-m", model_path, "-l", "en", "-t", "4", "-f", test_wav],
            capture_output=True, text=True, timeout=180
        )
        lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
        tail = lines[-1] if lines else ""
        print(f"  Whisper: {tail[:80]}")
        return result("Whisper transcribes sample", r.returncode == 0 and len(tail) > 0, f"rc={r.returncode}")
    except Exception as e:
        return result("Whisper transcribe", False, str(e))

if __name__ == "__main__":
    sys.exit(0 if test_stt() else 1)