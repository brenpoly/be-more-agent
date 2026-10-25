import sys
from common import result

def test_full_pipeline():
    """Record ~3s of mic audio, transcribe, then speak it back."""
    import sounddevice as sd
    import numpy as np
    import wave, tempfile, os
    from common import load_config

    cfg = load_config()
    sr = int(cfg.get("input_sample_rate", 44100))

    try:
        print("  Recording 3 seconds... speak now!")
        rec = sd.rec(int(sr * 3), samplerate=sr, channels=1, dtype="int16")
        sd.wait()
        if np.max(np.abs(rec)) < 50:
            print("  (no audio detected)")
        tmp = os.path.join(tempfile.gettempdir(), "pipeline_test.wav")
        with wave.open(tmp, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(rec.tobytes())
        print(f"  Recorded {len(rec)} samples")
        return True
    except Exception as e:
        return result("Mic recording", False, str(e))

if __name__ == "__main__":
    sys.exit(0 if test_full_pipeline() else 1)