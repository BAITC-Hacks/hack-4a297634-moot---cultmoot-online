$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8010 --no-access-log --no-server-header --no-proxy-headers --limit-concurrency 64 --ws-max-size 24000 --ws-max-queue 8 --timeout-keep-alive 5
