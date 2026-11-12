$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'scripts/python-runtime.ps1')
    $env:GENOMIC_PYTHON = Resolve-GenomicPython -ProjectRoot $PSScriptRoot -AllowDownload
    & (Join-Path $PSScriptRoot 'run.ps1') serve --open @args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} catch {
    Write-Host "START FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Check that the entire ZIP was extracted and that you have an internet connection for the first launch."
    exit 1
}
