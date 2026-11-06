param(
    [switch]$PackageDistribution,
    [string]$DistributionOutput
)

# Developer-only build. End users double-click the generated EXE.
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$buildPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if ($PackageDistribution -and [string]::IsNullOrWhiteSpace($DistributionOutput)) {
    throw "-DistributionOutput is required with -PackageDistribution"
}
if (-not $PackageDistribution -and -not [string]::IsNullOrWhiteSpace($DistributionOutput)) {
    throw "-DistributionOutput can only be used with -PackageDistribution"
}

& npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
& $buildPython -m PyInstaller desktop_app.spec --noconfirm --distpath build/portable
if ($LASTEXITCODE -ne 0) { throw "EXE build failed" }

if ($PackageDistribution) {
    & $buildPython scripts/package_distribution.py --distribution-output $DistributionOutput
    if ($LASTEXITCODE -ne 0) { throw "Distribution assembly failed" }
}
