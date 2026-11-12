$ErrorActionPreference = "Stop"

$Version = "3.14.10"
$RuntimeDir = Join-Path $PSScriptRoot ".runtime\python-$Version"
$PythonExe = Join-Path $RuntimeDir "python.exe"

if (Test-Path $PythonExe) {
    & $PythonExe -c "import sys; assert sys.version_info >= (3,10)"
    if ($LASTEXITCODE -eq 0) { exit 0 }
    Remove-Item -Recurse -Force $RuntimeDir
}

$Architecture = $env:PROCESSOR_ARCHITEW6432
if (-not $Architecture) { $Architecture = $env:PROCESSOR_ARCHITECTURE }
try {
    $RuntimeArchitecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    if ($RuntimeArchitecture) { $Architecture = $RuntimeArchitecture }
} catch {
    # Fall back to Windows environment architecture variables.
}

switch -Regex ($Architecture.ToUpperInvariant()) {
    "ARM64" {
        $Package = "arm64"
        $ExpectedSha256 = "BBE116BB1248820359CBF25127AC5C7794EA161869D83686CFBC9A45203FF836"
        break
    }
    "AMD64|X64" {
        $Package = "amd64"
        $ExpectedSha256 = "90905E64A840557D8C1BC4F5B74DB3D7EE85E3FFB217611CAC1C7813ACEA4159"
        break
    }
    "X86|I386" {
        $Package = "win32"
        $ExpectedSha256 = "11A28E8C00A6D8F56B0A6164D52546133A9ED015A5B33E04536917E4FD6E306C"
        break
    }
    default {
        throw "Unsupported Windows architecture: $Architecture"
    }
}

$FileName = "python-$Version-embed-$Package.zip"
$Url = "https://www.python.org/ftp/python/$Version/$FileName"
$TempZip = Join-Path $env:TEMP $FileName

Write-Host ""
Write-Host "Python 3.10+ was not found. Downloading the private portable Python $Version runtime..."
Write-Host "Source: python.org"
Write-Host "This runtime will be stored inside .runtime and will not be installed system-wide."

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $Url -OutFile $TempZip -UseBasicParsing
    $ActualSha256 = (Get-FileHash -Path $TempZip -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($ActualSha256 -ne $ExpectedSha256) {
        throw "SHA-256 verification failed for the Python archive."
    }

    if (Test-Path $RuntimeDir) {
        Remove-Item -Recurse -Force $RuntimeDir
    }
    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
    Expand-Archive -Path $TempZip -DestinationPath $RuntimeDir -Force

    $PthFile = Join-Path $RuntimeDir "python314._pth"
    if (-not (Test-Path $PthFile)) {
        throw "The embedded Python path configuration file was not found."
    }

    @(
        "python314.zip"
        "."
        $PSScriptRoot
    ) | Set-Content -Path $PthFile -Encoding ASCII

    if (-not (Test-Path $PythonExe)) {
        throw "The portable Python executable was not extracted."
    }

    & $PythonExe -c "import sys; assert sys.version_info >= (3,10); import genomic_detective; print('Portable Python is ready:', sys.version)"
    if ($LASTEXITCODE -ne 0) {
        throw "Portable Python self-check failed."
    }

    Write-Host "Portable Python is ready."
} catch {
    if (Test-Path $RuntimeDir) {
        Remove-Item -Recurse -Force $RuntimeDir -ErrorAction SilentlyContinue
    }
    Write-Host ""
    Write-Host "Automatic Python setup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Check your internet connection or download Python manually:"
    Write-Host "https://www.python.org/downloads/windows/"
    exit 1
} finally {
    if (Test-Path $TempZip) {
        Remove-Item -Force $TempZip -ErrorAction SilentlyContinue
    }
}
