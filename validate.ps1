$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
. (Join-Path $PSScriptRoot "scripts/python-runtime.ps1")

$env:GENOMIC_PYTHON = Resolve-GenomicPython -ProjectRoot $PSScriptRoot -AllowDownload

& (Join-Path $PSScriptRoot "run.ps1") --version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $PSScriptRoot "run.ps1") prepare
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $PSScriptRoot "run.ps1") run --dataset examples/demo_case.vcf --phenotype "арахнодактилия эктопия хрусталика расширение корня аорты высокий рост" --output outputs/demo
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $PSScriptRoot "run.ps1") evaluate --reports outputs/demo --expected examples/expected_answers.json --output outputs/demo/evaluation.json
exit $LASTEXITCODE
