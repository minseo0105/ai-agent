$ErrorActionPreference = "Stop"
$root = (Get-Location).Path

if (-not (Test-Path (Join-Path $root "app.py"))) {
    Write-Host "오류: ai-agent 프로젝트 루트에서 실행하세요." -ForegroundColor Red
    Write-Host "예: cd C:\Users\user\Desktop\ai-agent"
    exit 1
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root ("backup_golf_" + $stamp)
New-Item -ItemType Directory -Force -Path $backup | Out-Null

$pageTarget = Join-Path $root "pages\6_골프장_추천.py"
$dataDir = Join-Path $root "services\golf_data"
$dataTarget = Join-Path $dataDir "catalog.json"

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

if (Test-Path $pageTarget) { Copy-Item $pageTarget (Join-Path $backup "6_골프장_추천.py") -Force }
if (Test-Path $dataTarget) { Copy-Item $dataTarget (Join-Path $backup "catalog.json") -Force }

Copy-Item (Join-Path $PSScriptRoot "pages\6_골프장_추천.py") $pageTarget -Force
Copy-Item (Join-Path $PSScriptRoot "services\golf_data\catalog.json") $dataTarget -Force

Write-Host ""
Write-Host "설치 완료" -ForegroundColor Green
Write-Host "백업 폴더: $backup"
Write-Host "페이지: $pageTarget"
Write-Host "DB: $dataTarget"
Write-Host ""
Write-Host "실행 명령:"
Write-Host "python -m streamlit run app.py" -ForegroundColor Cyan
