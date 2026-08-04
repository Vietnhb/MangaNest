$ErrorActionPreference = "Stop"

$comfyRoot = "E:\MangaForgeAI\runtime\ComfyUI"
$python = Join-Path $comfyRoot ".venv\Scripts\python.exe"

Set-Location $comfyRoot
& $python main.py `
    --listen 127.0.0.1 `
    --port 8188 `
    --lowvram `
    --preview-method none `
    --output-directory "E:\MangaForgeAI\outputs"
