param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Command,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-GenomicDetective {
    param(
        [string]$PythonPath,
        [string[]]$PythonArgs
    )
    & $PythonPath @PythonArgs -m genomic_detective $Command @CommandArgs
    exit $LASTEXITCODE
}

$LocalPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $LocalPython) {
    Invoke-GenomicDetective -PythonPath $LocalPython -PythonArgs @()
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($Version in @("3.14", "3.13", "3.12", "3.11", "3.10")) {
        & py "-$Version" -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Invoke-GenomicDetective -PythonPath "py" -PythonArgs @("-$Version")
        }
    }
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Invoke-GenomicDetective -PythonPath "python" -PythonArgs @()
    }
}

Write-Host "Python 3.10+ was not found. Preparing portable Python..."
$Bootstrap = Join-Path $PSScriptRoot "scripts\bootstrap-python.ps1"
& powershell -NoProfile -ExecutionPolicy Bypass -File $Bootstrap
if ($LASTEXITCODE -ne 0) {
    Write-Error "Automatic Python setup failed. Check your internet connection or install Python manually from https://www.python.org/downloads/windows/."
    exit 1
}

$BundledPython = Join-Path $PSScriptRoot ".runtime\python-3.14.10\python.exe"
if (-not (Test-Path $BundledPython)) {
    Write-Error "Portable Python was not found after setup."
    exit 1
}

Invoke-GenomicDetective -PythonPath $BundledPython -PythonArgs @()
