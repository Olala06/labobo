$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$PythonCommand = $null
$PythonArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.11 -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $PythonCommand = "py"
        $PythonArgs = @("-3.11")
    } else {
        & py -3.10 -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $PythonCommand = "py"
            $PythonArgs = @("-3.10")
        }
    }
}
if (-not $PythonCommand -and (Get-Command python -ErrorAction SilentlyContinue)) {
    & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $PythonCommand = "python" }
}
if (-not $PythonCommand) { throw "Python 3.10+ was not found." }

& $PythonCommand @PythonArgs -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonCommand @PythonArgs -m genomic_detective --version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonCommand @PythonArgs -m genomic_detective prepare
exit $LASTEXITCODE
