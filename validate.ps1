$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
. (Join-Path $PSScriptRoot "scripts/python-runtime.ps1")
$python = Resolve-GenomicPython -ProjectRoot $PSScriptRoot -AllowDownload

& $python -I -c "import sys,unittest; sys.path.insert(0,sys.argv.pop(1)); suite=unittest.defaultTestLoader.discover('tests'); result=unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() else 1)" $PSScriptRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $PSScriptRoot "run.ps1") --version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $PSScriptRoot "run.ps1") prepare
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $PSScriptRoot "run.ps1") run --dataset examples/demo_case.vcf --phenotype "арахнодактилия эктопия хрусталика расширение корня аорты высокий рост" --output outputs/demo
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $PSScriptRoot "run.ps1") evaluate --reports outputs/demo --expected examples/expected_answers.json --output outputs/demo/evaluation.json
exit $LASTEXITCODE
