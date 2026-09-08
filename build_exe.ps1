# Developer-only build. End users double-click the generated EXE.
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$buildPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
& $buildPython -m PyInstaller desktop_app.spec --noconfirm --distpath build/portable
if ($LASTEXITCODE -ne 0) { throw "EXE build failed" }
& $buildPython scripts/package_distribution.py
if ($LASTEXITCODE -ne 0) { throw "Distribution assembly failed" }
