# Be More Agent - Windows Installer
# Run from the project root in PowerShell:
#   Set-ExecutionPolicy -Scope Process Bypass; .\setup_windows.ps1

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

$WHISPER_VERSION = "v1.9.2"
$WHISPER_URL = "https://github.com/ggml-org/whisper.cpp/releases/download/$WHISPER_VERSION/whisper-bin-x64.zip"
$WHISPER_MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
$PIPER_URL = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
$VOICE_ONNX_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx"
$VOICE_JSON_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx.json"
$BMO_ONNX_URL = "https://github.com/brenpoly/be-more-agent/releases/download/v1.0-voice/bmo.onnx"
$BMO_JSON_URL = "https://github.com/brenpoly/be-more-agent/releases/download/v1.0-voice/bmo.onnx.json"
$TEMP_DIR = Join-Path $env:TEMP "be-more-agent-setup"

Write-Host "Be More Agent - Windows Setup" -ForegroundColor Green

# 1. Check Python
Write-Host "`n=== 1/6 Python ===" -ForegroundColor Cyan
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found. Install Python 3.10+ from https://www.python.org/downloads/ (check 'Add to PATH')." -ForegroundColor Red
    exit 1
}
Write-Host "Python: $(python --version)"

# 2. Folders
New-Item -ItemType Directory -Force -Path "piper","voices","sounds/greeting_sounds","sounds/thinking_sounds","sounds/ack_sounds","sounds/error_sounds","faces/idle","faces/listening","faces/thinking","faces/speaking","faces/error","faces/warmup","whisper.cpp/models" | Out-Null

# 3. Download & install Whisper.cpp
Write-Host "`n=== 2/6 Whisper.cpp ===" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $TEMP_DIR | Out-Null
$wz = Join-Path $TEMP_DIR "whisper.zip"
$wd = Join-Path $TEMP_DIR "whisper-extract"
if (-not (Test-Path $wz)) { Write-Host "  Downloading whisper-bin-x64.zip ..."; Invoke-WebRequest -Uri $WHISPER_URL -OutFile $wz }
if (-not (Test-Path "whisper.cpp\build\bin\whisper-cli.exe")) {
    if (Test-Path $wd) { Remove-Item -Recurse -Force $wd }
    Expand-Archive -Path $wz -DestinationPath $wd
    $cli = Get-ChildItem -Path $wd -Recurse -Filter "whisper-cli.exe" | Select-Object -First 1
    if (-not $cli) { Write-Host "ERROR: whisper-cli.exe not found in archive." -ForegroundColor Red; exit 1 }
    New-Item -ItemType Directory -Force -Path "whisper.cpp\build\bin" | Out-Null
    Copy-Item -Force (Join-Path $cli.DirectoryName "*") "whisper.cpp\build\bin"
    Write-Host "  Installed whisper-cli.exe + runtime DLLs"
}
if (-not (Test-Path "whisper.cpp\models\ggml-base.en.bin")) { Write-Host "  Downloading ggml-base.en.bin ..."; Invoke-WebRequest -Uri $WHISPER_MODEL_URL -OutFile "whisper.cpp\models\ggml-base.en.bin" }

# 4. Download & install Piper
Write-Host "`n=== 3/6 Piper TTS ===" -ForegroundColor Cyan
$pz = Join-Path $TEMP_DIR "piper.zip"
$pd = Join-Path $TEMP_DIR "piper-extract"
if (-not (Test-Path $pz)) { Write-Host "  Downloading piper_windows_amd64.zip ..."; Invoke-WebRequest -Uri $PIPER_URL -OutFile $pz }
if (-not (Test-Path "piper\piper.exe")) {
    if (Test-Path $pd) { Remove-Item -Recurse -Force $pd }
    Expand-Archive -Path $pz -DestinationPath $pd
    $piperExe = Get-ChildItem -Path $pd -Recurse -Filter "piper.exe" | Select-Object -First 1
    if (-not $piperExe) { Write-Host "ERROR: piper.exe not found in archive." -ForegroundColor Red; exit 1 }
    Copy-Item -Recurse -Force (Join-Path $piperExe.DirectoryName "*") "piper\"
    Write-Host "  Installed piper.exe"
}
if (-not (Test-Path "piper\en_GB-semaine-medium.onnx")) { Write-Host "  Downloading voice model ..."; Invoke-WebRequest -Uri $VOICE_ONNX_URL -OutFile "piper\en_GB-semaine-medium.onnx" }
if (-not (Test-Path "piper\en_GB-semaine-medium.onnx.json")) { Invoke-WebRequest -Uri $VOICE_JSON_URL -OutFile "piper\en_GB-semaine-medium.onnx.json" }

# 5. Optional BMO custom voice
Write-Host "`n=== 4/6 BMO voice (optional) ===" -ForegroundColor Cyan
$bmo = Read-Host "Download custom BMO voice? (y/n)"
if ($bmo -match "^y") {
    New-Item -ItemType Directory -Force -Path "voices" | Out-Null
    if (-not (Test-Path "voices\bmo-custom.onnx")) { Write-Host "  Downloading bmo.onnx (63MB) ..."; Invoke-WebRequest -Uri $BMO_ONNX_URL -OutFile "voices\bmo-custom.onnx" }
    if (-not (Test-Path "voices\bmo-custom.onnx.json")) { Invoke-WebRequest -Uri $BMO_JSON_URL -OutFile "voices\bmo-custom.onnx.json" }
    Write-Host "  BMO voice saved. To use it, set config.json voice_model to 'voices/bmo-custom.onnx'" -ForegroundColor Yellow
}

# 6. Python venv + deps
Write-Host "`n=== 5/6 Python venv ===" -ForegroundColor Cyan
if (-not (Test-Path "venv")) { python -m venv venv }
& "venv\Scripts\python.exe" -m pip install --upgrade pip
& "venv\Scripts\python.exe" -m pip install -r requirements.txt

# 7. Ollama check
Write-Host "`n=== 6/6 Ollama ===" -ForegroundColor Cyan
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 2
    ollama pull gemma3:1b
    ollama pull moondream
} else {
    Write-Host "Ollama not found. Install from https://ollama.com/download/windows" -ForegroundColor Yellow
}

# 8. Default wake word (if missing)
Write-Host "`n=== Wake word ===" -ForegroundColor Cyan
if (-not (Test-Path "wakeword.onnx")) {
    Write-Host "  Downloading default 'Hey Jarvis' wake word ..."
    Invoke-WebRequest -Uri "https://github.com/dscripka/openWakeWord/raw/main/openwakeword/resources/models/hey_jarvis_v0.1.onnx" -OutFile "wakeword.onnx"
    Write-Host "  wakeword.onnx saved"
}

Write-Host "`nSetup complete! Run:"
Write-Host "  venv\Scripts\activate"
Write-Host "  python agent.py"
Write-Host "To verify components, run: python tests\run_all_tests.py" -ForegroundColor Green