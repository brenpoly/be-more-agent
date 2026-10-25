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

def _transcribe_faster_whisper(wav, cfg):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None, "faster-whisper not installed"
    model_name = cfg.get("faster_whisper_model", "base.en")
    print(f"  Loading faster_whisper '{model_name}' (first run may download)...")
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=4)
    segments, _ = model.transcribe(wav, language="en", beam_size=1)
    text = "".join(s.text for s in segments).strip()
    return text, None

def _transcribe_whisper_cpp(wav, cfg):
    binary = cfg.get("whisper_binary", "whisper.cpp/build/bin/whisper-cli.exe")
    model_path = cfg.get("whisper_model", "whisper.cpp/models/ggml-base.en.bin")
    if not os.path.exists(binary):
        return None, f"binary missing: {binary}"
    if not os.path.exists(model_path):
        return None, f"model missing: {model_path}"
    r = subprocess.run(
        [binary, "-m", model_path, "-l", "en", "-t", "4", "-f", wav],
        capture_output=True, text=True, timeout=180
    )
    lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
    tail = lines[-1] if lines else ""
    if r.returncode != 0 or not tail:
        return None, f"whisper-cli rc={r.returncode}"
    text = tail.split("]")[1].strip() if "]" in tail else tail.strip()
    return text, None

def test_stt():
    cfg = load_config()
    engine = cfg.get("stt_engine", "faster_whisper")

    test_wav = os.path.join(os.path.dirname(__file__), "test_sample.wav")
    if not os.path.exists(test_wav):
        test_wav = _synthesize_sample()
    if not test_wav or not os.path.exists(test_wav):
        print("  Skipping transcription: no test_sample.wav in tests/ and Piper unavailable")
        return True

    try:
        if engine == "whisper_cpp":
            text, err = _transcribe_whisper_cpp(test_wav, cfg)
            label = f"STT ({engine})"
            if err:
                return result(label, False, err)
            print(f"  Whisper: {text[:80]}")
            return result(label, len(text) > 0, f"transcribed: {text[:40]}")
        else:
            text, err = _transcribe_faster_whisper(test_wav, cfg)
            label = f"STT ({engine})"
            if err:
                return result(label, False, err)
            print(f"  faster_whisper: {text[:80]}")
            return result(label, len(text) > 0, f"transcribed: {text[:40]}")
    except Exception as e:
        return result(f"STT ({engine})", False, str(e))

if __name__ == "__main__":
    sys.exit(0 if test_stt() else 1)
