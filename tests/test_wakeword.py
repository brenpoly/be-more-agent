import os
import sys
import numpy as np
from common import result, load_config, ROOT

def test_wakeword():
    from openwakeword.model import Model

    try:
        from openwakeword.utils import download_models
        import pathlib
        import openwakeword
        resource_dir = os.path.join(pathlib.Path(openwakeword.__file__).parent.resolve(), "resources", "models")
        if not os.path.exists(os.path.join(resource_dir, "melspectrogram.onnx")):
            print("  Downloading OpenWakeWord feature models...")
            download_models()
    except Exception as e:
        print(f"  (model download skipped: {e})")

    path = os.path.join(ROOT, "wakeword.onnx")
    if not os.path.exists(path):
        return result("Wake word model file", False, "wakeword.onnx missing (run setup)")

    try:
        model = Model(wakeword_model_paths=[path])
    except TypeError:
        model = Model(wakeword_models=[path])
    except Exception as e:
        return result("Wake word model load", False, str(e))

    if not hasattr(model, "predict"):
        return result("Wake word predict API", False, "model.predict not found")

    rng = np.random.default_rng(0)
    chunk = (rng.standard_normal(1280) * 100).astype(np.int16)
    preds = model.predict(chunk)
    keys = list(model.prediction_buffer.keys())
    ok = len(keys) > 0
    result("Wake word load + predict", ok, f"models={keys}")
    return ok

if __name__ == "__main__":
    sys.exit(0 if test_wakeword() else 1)