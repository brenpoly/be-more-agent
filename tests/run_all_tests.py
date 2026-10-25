import importlib
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TESTS = [
    "test_audio",
    "test_wakeword",
    "test_ollama",
    "test_search",
    "test_tts",
    "test_stt",
    "test_camera",
    "test_transcription_cleanup",
]

def main():
    results = {}
    for name in TESTS:
        try:
            mod = importlib.import_module(name)
            fn = getattr(mod, name)
            print(f"\n===== {name} =====")
            try:
                results[name] = bool(fn())
            except Exception as e:
                print(f"[ERROR] {name} raised: {e}")
                results[name] = False
        except Exception as e:
            print(f"\n===== {name} =====")
            print(f"[ERROR] import failed: {e}")
            results[name] = False

    print("\n========== SUMMARY ==========")
    passed = 0
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {name:20s} {status}")
        passed += 1 if ok else 0
    print(f"\n{passed}/{len(TESTS)} passed")
    return passed == len(TESTS)

if __name__ == "__main__":
    sys.exit(0 if main() else 1)