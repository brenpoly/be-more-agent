#!/bin/bash

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🤖 Pi Local Assistant Setup Script${NC}"

# 1. Create necessary directories
echo -e "${YELLOW}[1/5] Creating folders...${NC}"
mkdir -p piper
mkdir -p sounds/greeting_sounds
mkdir -p sounds/thinking_sounds
mkdir -p sounds/ack_sounds
mkdir -p sounds/error_sounds
mkdir -p faces/idle
mkdir -p faces/listening
mkdir -p faces/thinking
mkdir -p faces/speaking
mkdir -p faces/error
mkdir -p faces/warmup

# 2. Download Piper (Architecture Check)
echo -e "${YELLOW}[2/5] Checking Architecture...${NC}"
ARCH=$(uname -m)
if [ "$ARCH" == "aarch64" ]; then
    echo -e "${GREEN}Detected Raspberry Pi (aarch64). Downloading Piper...${NC}"
    wget -O piper.tar.gz https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_linux_aarch64.tar.gz
    tar -xvf piper.tar.gz -C .
    rm piper.tar.gz
else
    echo -e "${RED}⚠️  System is not aarch64. You may need to download the correct Piper binary manually.${NC}"
fi

# 3. Download Voice Model (En-GB Semaine)
echo -e "${YELLOW}[3/5] Downloading Voice Model...${NC}"
cd piper
wget -nc -O en_GB-semaine-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx
wget -nc -O en_GB-semaine-medium.onnx.json https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx.json
cd ..

# 4. Install Python Dependencies
echo -e "${YELLOW}[4/5] Installing Python Libraries...${NC}"
pip install sounddevice numpy openwakeword ollama ddgs scipy pillow

# 5. Pull Ollama Models (The Brains)
echo -e "${YELLOW}[5/5] downloading AI Models (Ollama)...${NC}"
if command -v ollama &> /dev/null; then
    echo "Pulling Chat Model (gemma3:1b)..."
    ollama pull gemma3:1b
    
    echo "Pulling Vision Model (moondream)..."
    ollama pull moondream
else
    echo -e "${RED}❌ Ollama is not installed!${NC}"
    echo "Please install it first by running: curl -fsSL https://ollama.com/install.sh | sh"
fi

echo -e "${GREEN}✨ Setup Complete! You can now run: python agent.py${NC}"