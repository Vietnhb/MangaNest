$ErrorActionPreference = "Stop"

$projectRoot = "D:\FPT_FALL_2026\Future"
$python = "C:\Users\kemin\AppData\Local\Python\pythoncore-3.14-64\python.exe"

Set-Location $projectRoot
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
