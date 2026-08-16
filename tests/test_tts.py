import os
import subprocess
import sys
import numpy as np
from common import result, load_config

def test_tts():
    cfg = load_config()
    binary = cfg.get("piper_binary", "piper/piper.exe")
    voice = cfg.get("voice_model", "piper/en_GB-semaine-medium.onnx")
    out_file = os.path.join(os.path.dirname(__file__), "tts_test.raw")

    ok = os.path.exists(binary)
    ok &= os.path.exists(voice)
    result("Piper binary exists", os.path.exists(binary), binary)
    result("Voice model exists", os.path.exists(voice), voice)
    if not ok:
        return False

    try:
        if os.path.exists(out_file):
            os.remove(out_file)
        proc = subprocess.Popen(
            [binary, "--model", voice, "--output-raw"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        proc.stdin.write(b"Hello! I am a tiny robot.\n")
        proc.stdin.close()
        data = proc.stdout.read()
        proc.wait(timeout=60)

        samples = np.frombuffer(data, dtype=np.int16)
        print(f"  Generated {len(samples)} samples ({len(data)} bytes)")
        return result("Piper produces audio", len(samples) > 1000, f"{len(samples)} samples")
    except Exception as e:
        return result("Piper TTS", False, str(e))

if __name__ == "__main__":
    sys.exit(0 if test_tts() else 1)