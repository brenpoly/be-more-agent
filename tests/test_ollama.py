import sys
import socket
import subprocess
from common import result, load_config

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _sh(cmd):
    """Run a command silently and return stripped stdout."""
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=20,
            creationflags=CREATE_NO_WINDOW,
        ).stdout.strip()
    except Exception:
        return ""


def detect_gpus():
    out = _sh(["powershell", "-NoProfile", "-Command",
               "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def classify_gpu(name):
    n = name.lower()
    if any(k in n for k in ("nvidia", "geforce", "quadro", "rtx", "gtx", "tesla")):
        return "nvidia"
    if any(k in n for k in ("amd", "radeon", "ati")):
        return "amd"
    if any(k in n for k in ("intel", "arc")):
        return "intel"
    if "basic display" in n:
        return "basic"
    return "unknown"


def gpu_summary(gpus):
    if not gpus:
        return "no GPUs enumerated"
    cats = [classify_gpu(g) for g in gpus]
    label = ", ".join(gpus)
    if "nvidia" in cats:
        return f"GPU acceleration expected via CUDA ({label})"
    if "amd" in cats:
        return f"CPU fallback expected - AMD Windows GPU support limited; CUDA unavailable ({label})"
    if cats == ["basic"]:
        return f"CPU only - no hardware GPU driver (Microsoft Basic Display) ({label})"
    return f"CPU fallback expected - integrated/Intel GPU not used by Ollama by default ({label})"


def test_ollama():
    cfg = load_config()
    model = cfg.get("text_model", "gemma3:1b")

    gpus = detect_gpus()
    summary = gpu_summary(gpus)
    print(f"  Graphics: {summary}")
    result("GPU detection", True, summary)

    try:
        import ollama
        client = ollama.Client()
        client.list()
        result("Ollama server reachable", True, "http://localhost:11434")
    except socket.gaierror as e:
        return result("Ollama server reachable", False, "Cannot resolve host - is Ollama running?")
    except Exception as e:
        return result("Ollama server reachable", False, str(e))

    try:
        resp = ollama.chat(model=model, messages=[{"role": "user", "content": "Say hello in 3 words."}], stream=False)
        text = resp["message"]["content"].strip()
        print(f"  Model response: {text}")
        runtime = ""
        try:
            ps = client.ps()
            for m in getattr(ps, "models", []):
                proc = getattr(m, "processor", "")
                if proc:
                    runtime = f" | {proc}"
                    break
        except Exception:
            pass
        return result(f"LLM responds ({model})", len(text) > 0, text[:60] + runtime)
    except Exception as e:
        return result(f"LLM respond ({model})", False, str(e))

if __name__ == "__main__":
    sys.exit(0 if test_ollama() else 1)