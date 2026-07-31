# dev.ps1 - PPTGen 백엔드 + 프론트엔드를 각각 새 창에서 동시에 실행
# 사용법:  PowerShell에서  ->   .\dev.ps1
# (실행정책 막히면)        ->   powershell -ExecutionPolicy Bypass -File .\dev.ps1

$root = $PSScriptRoot

Write-Host "Starting PPTGen..." -ForegroundColor Cyan
Write-Host "  backend  -> http://localhost:8000" -ForegroundColor DarkGray
Write-Host "  frontend -> http://localhost:5173" -ForegroundColor DarkGray

# 백엔드: venv 활성화 후 uvicorn (새 PowerShell 창, 닫지 않음)
Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "cd '$root\backend'; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload"
)

# 프론트엔드: vite 개발 서버 (새 PowerShell 창, 닫지 않음)
Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "cd '$root\frontend'; npm run dev"
)

Write-Host "두 개의 창이 열렸어. 종료하려면 각 창에서 Ctrl+C 하거나 창을 닫아." -ForegroundColor Cyan
Write-Host "브라우저에서 http://localhost:5173 열기" -ForegroundColor Green
