import sys
from common import result, load_config

def test_audio():
    import sounddevice as sd
    cfg = load_config()
    ok = True

    try:
        devices = sd.query_devices()
        inputs = [d for d in devices if d.get("max_input_channels", 0) > 0]
        outputs = [d for d in devices if d.get("max_output_channels", 0) > 0]
        ok &= result("Device Query", True, f"{len(devices)} devices, {len(inputs)} input, {len(outputs)} output")
        for i, d in enumerate(devices):
            print(f"  [{i}] {d.get('name')} | In:{d.get('max_input_channels',0)} Out:{d.get('max_output_channels',0)}")
        ok &= result("Microphone found", len(inputs) > 0)
        return ok
    except Exception as e:
        return result("Audio devices", False, str(e))

if __name__ == "__main__":
    sys.exit(0 if test_audio() else 1)