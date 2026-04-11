#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Looi Personal Assistant — setup script
# Installs all Python dependencies and creates a default config.json.
# Run once: bash setup.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     Looi — Personal AI Assistant Setup   ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── System packages (Raspberry Pi / Debian) ─────────────────────────────────
echo "▶ Installing system dependencies…"
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv \
    python3-tk \
    portaudio19-dev \
    libopencv-dev \
    libsdl2-mixer-2.0-0 \
    ffmpeg \
    xvfb

# ── Python virtual environment ───────────────────────────────────────────────
echo "▶ Creating Python virtual environment…"
python3 -m venv venv
source venv/bin/activate

echo "▶ Upgrading pip…"
pip install --upgrade pip --quiet

# ── Python packages ──────────────────────────────────────────────────────────
echo "▶ Installing Python packages…"
pip install -r requirements.txt --quiet

echo ""
echo "✅ Dependencies installed."

# ── config.json ──────────────────────────────────────────────────────────────
if [ ! -f config.json ] || grep -q "YOUR_GEMINI_API_KEY_HERE" config.json; then
    echo ""
    echo "────────────────────────────────────────────"
    echo "  ACTION REQUIRED: Add your Gemini API key"
    echo "────────────────────────────────────────────"
    echo "  1. Visit: https://aistudio.google.com/apikey"
    echo "  2. Create a free API key"
    echo "  3. Edit config.json and replace:"
    echo "       \"YOUR_GEMINI_API_KEY_HERE\""
    echo "     with your actual key."
    echo ""
fi

echo "────────────────────────────────────────────"
echo "  To run Looi:"
echo ""
echo "    source venv/bin/activate"
echo "    python looi.py"
echo ""
echo "  Controls:"
echo "    SPACE / ENTER  →  Talk (push-to-talk)"
echo "    ESC            →  Quit"
echo "    Click          →  Toggle info overlay"
echo "────────────────────────────────────────────"
echo ""
