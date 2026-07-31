<#
.SYNOPSIS
  새 버전 폴더에서 의존성(.venv, node_modules)을 이전 버전에서 복사하고,
  매니페스트(pyproject.toml / package-lock.json)가 바뀐 것만 설치한다.

.DESCRIPTION
  .venv 와 node_modules 는 git 에 포함되지 않으므로(.gitignore), 새로 받은 폴더는 비어 있다.
  이전 버전에서 복사해 오면 인터넷 재다운로드 없이 빠르게 환경을 구성할 수 있다.
  의존성 매니페스트가 이전 버전과 "다를 때만" 해당 설치를 수행한다(없으면 새로 설치).
  pyproject 변경이 없으면 editable 재연결만 수행한다(오프라인, 빠름).

.EXAMPLE
  .\setup.ps1 -From ..\v1            # 이전 버전(..\v1)에서 복사 + 바뀐 것만 설치
  .\setup.ps1 -From ..\v1 -Force     # 비교 없이 전부 재설치
  .\setup.ps1                        # 이전 폴더 없이 새로 설치만
  .\setup.ps1 -From ..\v1 -DryRun    # 실제 변경 없이 수행할 동작만 출력
  (실행정책 막히면)  powershell -ExecutionPolicy Bypass -File .\setup.ps1 -From ..\v1
#>
param(
    [string]$From = "",
    [switch]$Force,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if ($From) {
    if (Test-Path $From) {
        $From = (Resolve-Path $From).Path
        if ($From -eq $root) {
            Write-Host "[X] -From 이 현재 폴더와 같습니다." -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "[X] -From 경로를 찾을 수 없음: $From" -ForegroundColor Red
        if (-not $DryRun) { exit 1 }
    }
}

# git 에 포함되지 않는(=새 폴더에서 비어있는) 의존성 디렉터리들
$depDirs = @(
    "backend\.venv",
    "frontend\node_modules",
    "backend\app\ppt\node_renderer\node_modules"
)

function Copy-Dep([string]$rel) {
    $dst = Join-Path $root $rel
    if (Test-Path $dst) { Write-Host "  [skip] 이미 존재: $rel" -ForegroundColor DarkGray; return }
    if (-not $From)     { Write-Host "  [none] -From 없음 → 복사 안 함: $rel" -ForegroundColor DarkGray; return }
    $src = Join-Path $From $rel
    if (-not (Test-Path $src)) { Write-Host "  [warn] 원본 없음(설치로 대체됨): $src" -ForegroundColor Yellow; return }
    if ($DryRun) { Write-Host "  [dry] copy $rel" -ForegroundColor DarkGray; return }
    Write-Host "  [copy] $rel ..." -ForegroundColor Cyan
    Copy-Item $src $dst -Recurse
}

function Manifest-Changed([string]$rel) {
    # 현재 vs -From 의 매니페스트가 다르면 true. (-Force / -From 없음 / 파일 없음 → 설치 필요)
    if ($Force)     { return $true }
    if (-not $From) { return $true }
    $cur = Join-Path $root $rel
    $old = Join-Path $From $rel
    if (-not (Test-Path $cur)) { return $true }
    if (-not (Test-Path $old)) { return $true }
    return ((Get-FileHash $cur).Hash -ne (Get-FileHash $old).Hash)
}

Write-Host "== PPTGen setup ==" -ForegroundColor Green
Write-Host "현재: $root"
if ($From)   { Write-Host "원본: $From" }
if ($DryRun) { Write-Host "(DryRun: 실제 변경 없음)" -ForegroundColor Yellow }

Write-Host "`n[1/2] 의존성 복사"
foreach ($d in $depDirs) { Copy-Dep $d }

Write-Host "`n[2/2] 설치 (바뀐 것만)"

# --- backend (pip) ---
$venv = Join-Path $root "backend\.venv"
$py = Join-Path $venv "Scripts\python.exe"
$venvCreated = $false
if (-not (Test-Path $py)) {
    if ($DryRun) {
        Write-Host "  [dry] python -m venv backend\.venv" -ForegroundColor DarkGray
    } else {
        Write-Host "  [venv] 생성: backend\.venv" -ForegroundColor Cyan
        python -m venv $venv
        $venvCreated = $true
    }
}
$pipFull = $venvCreated -or (Manifest-Changed "backend\pyproject.toml")
Push-Location (Join-Path $root "backend")
try {
    if ($pipFull) {
        if ($DryRun) { Write-Host '  [dry] pip install -e ".[dev]"  (deps 변경/신규 venv)' -ForegroundColor DarkGray }
        else { Write-Host '  [pip] install -e ".[dev]"  (deps 변경/신규)' -ForegroundColor Cyan; & $py -m pip install -e ".[dev]" }
    } else {
        # pyproject 동일 → editable 재연결만 (네트워크 불필요, 빠름)
        if ($DryRun) { Write-Host "  [dry] pip install -e . --no-deps  (재연결만)" -ForegroundColor DarkGray }
        else { Write-Host "  [pip] install -e . --no-deps  (재연결만)" -ForegroundColor Cyan; & $py -m pip install -e . --no-deps }
    }
} finally { Pop-Location }

# --- frontend (npm) ---
$feMod = Join-Path $root "frontend\node_modules"
if ((Manifest-Changed "frontend\package-lock.json") -or -not (Test-Path $feMod)) {
    Push-Location (Join-Path $root "frontend")
    try {
        if ($DryRun) { Write-Host "  [dry] npm install (frontend)" -ForegroundColor DarkGray }
        else { Write-Host "  [npm] frontend install" -ForegroundColor Cyan; npm install }
    } finally { Pop-Location }
} else {
    Write-Host "  [skip] frontend node_modules 최신 (복사본 사용)" -ForegroundColor DarkGray
}

# --- node_renderer (npm) ---
$rdDir = Join-Path $root "backend\app\ppt\node_renderer"
$rdMod = Join-Path $rdDir "node_modules"
if ((Manifest-Changed "backend\app\ppt\node_renderer\package-lock.json") -or -not (Test-Path $rdMod)) {
    Push-Location $rdDir
    try {
        if ($DryRun) { Write-Host "  [dry] npm install (node_renderer)" -ForegroundColor DarkGray }
        else { Write-Host "  [npm] node_renderer install" -ForegroundColor Cyan; npm install }
    } finally { Pop-Location }
} else {
    Write-Host "  [skip] node_renderer node_modules 최신 (복사본 사용)" -ForegroundColor DarkGray
}

Write-Host "`n완료. 실행:  python dev.py internal" -ForegroundColor Green
