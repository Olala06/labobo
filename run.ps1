param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Command,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$LocalPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $LocalPython) {
    & $LocalPython -m genomic_detective $Command @CommandArgs
    exit $LASTEXITCODE
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.11 -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) {
        & py -3.11 -m genomic_detective $Command @CommandArgs
        exit $LASTEXITCODE
    }
    & py -3.10 -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) {
        & py -3.10 -m genomic_detective $Command @CommandArgs
        exit $LASTEXITCODE
    }
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        & python -m genomic_detective $Command @CommandArgs
        exit $LASTEXITCODE
    }
}

Write-Error "Python 3.10+ was not found. Install it from https://www.python.org/downloads/."
exit 1
