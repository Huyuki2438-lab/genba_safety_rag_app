# デスクトップアプリ (GenbaSafetyRAGApp.exe) のビルドスクリプト
#
# 使い方: PowerShellでプロジェクトルートから実行
#   .\build_exe.ps1
#
# 出力: .\dist\GenbaSafetyRAGApp\  (このフォルダ一式を配布する)

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
Set-Location $root

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "venvが見つかりません: $venvPython"
}

Write-Host "== 1/5: フロントエンド(React)をビルド =="
cmd /c "npm run build"
if ($LASTEXITCODE -ne 0) { throw "npm run build に失敗しました" }

Write-Host "== 2/5: Playwright Chromium を配布用フォルダへ取得 =="
$pwBrowsers = Join-Path $root "pw-browsers"
$env:PLAYWRIGHT_BROWSERS_PATH = $pwBrowsers
& $venvPython -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "playwright install chromium に失敗しました" }
Remove-Item Env:PLAYWRIGHT_BROWSERS_PATH

Write-Host "== 3/5: PyInstaller でexe化 (onedir) =="
if (Test-Path (Join-Path $root "build")) { Remove-Item -Recurse -Force (Join-Path $root "build") }
if (Test-Path (Join-Path $root "dist\KY写真解析")) { Remove-Item -Recurse -Force (Join-Path $root "dist\KY写真解析") }
& $venvPython -m PyInstaller desktop_app.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller に失敗しました" }

$outDir = Join-Path $root "dist\KY写真解析"

Write-Host "== 4/5: 実行時アセットを配置 =="
# npm run build の出力はプロジェクト直下 dist/ (index.html, assets/) に生成される。
# PyInstaller の出力先も dist/GenbaSafetyRAGApp/ のため、コピーは
# PyInstaller実行後 (このタイミング) に行う。
if (-not (Test-Path (Join-Path $outDir "dist"))) { New-Item -ItemType Directory -Path (Join-Path $outDir "dist") | Out-Null }
Copy-Item -Force (Join-Path $root "dist\index.html") (Join-Path $outDir "dist\index.html")
Copy-Item -Recurse -Force (Join-Path $root "dist\assets") (Join-Path $outDir "dist\assets")

# Allowlist runtime assets instead of copying whole source folders. This keeps
# local photos, screenshots, and future sample files out of the distribution.
$staticDir = Join-Path $outDir "static"
$iconsDir = Join-Path $staticDir "icons"
$templatesDir = Join-Path $outDir "templates"
New-Item -ItemType Directory -Force -Path $iconsDir,$templatesDir | Out-Null
Copy-Item -Force (Join-Path $root "static\pdf.css") (Join-Path $staticDir "pdf.css")
Copy-Item -Force (Join-Path $root "static\icons\app_icon.png") (Join-Path $iconsDir "app_icon.png")
Copy-Item -Force (Join-Path $root "static\icons\app_icon.ico") (Join-Path $iconsDir "app_icon.ico")
Copy-Item -Force (Join-Path $root "templates\report.html") (Join-Path $templatesDir "report.html")
Copy-Item -Force (Join-Path $root ".env") (Join-Path $outDir ".env") -ErrorAction SilentlyContinue
Copy-Item -Force (Join-Path $root ".env.shared.example") (Join-Path $outDir ".env.shared.example")
Copy-Item -Recurse -Force $pwBrowsers (Join-Path $outDir "pw-browsers")

Write-Host "== 5/5: 完了 =="
Write-Host "配布フォルダ: $outDir"
Write-Host "この $outDir フォルダごとネットワーク共有へコピーしてください。"
