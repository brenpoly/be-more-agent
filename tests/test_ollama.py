import sys
import socket
from common import result, load_config

def test_ollama():
    cfg = load_config()
    model = cfg.get("text_model", "gemma3:1b")

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
        return result(f"LLM responds ({model})", len(text) > 0, text[:60])
    except Exception as e:
        return result(f"LLM respond ({model})", False, str(e))

if __name__ == "__main__":
    sys.exit(0 if test_ollama() else 1)