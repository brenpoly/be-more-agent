# Convenience launcher
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
& "venv\Scripts\python.exe" agent.py