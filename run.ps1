$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
. (Join-Path $projectRoot 'scripts/python-runtime.ps1')
$pythonPath = Resolve-GenomicPython -ProjectRoot $projectRoot
$env:PYTHONUTF8 = '1'

Push-Location -LiteralPath $projectRoot
try {
    # The embeddable distribution is isolated; insert the project root explicitly.
    & $pythonPath -X utf8 -I -c "import sys,runpy; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('genomic_detective',run_name='__main__')" $projectRoot @args
    $resultCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $resultCode
