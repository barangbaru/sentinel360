# build_executables.ps1 - Automate building both 32-bit and 64-bit Agent EXEs for Windows
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BaseDir = Resolve-Path (Join-Path $ScriptDir "..")
$AgentPy = Join-Path $ScriptDir "agent.py"

# Clean up any leftover folders
$Py32Dir = Join-Path $BaseDir "python-32"
Remove-Item -Recurse -Force $Py32Dir -ErrorAction SilentlyContinue

Write-Output "Starting agent build..."

# 1. 64-bit Build
Write-Host "Building 64-bit Agent..." -ForegroundColor Cyan
$VenvPip = Join-Path $BaseDir "venv\Scripts\pip.exe"
if (Test-Path $VenvPip) {
    & $VenvPip install pyinstaller requests psutil pystray Pillow --upgrade --quiet
    $VenvPyinstaller = Join-Path $BaseDir "venv\Scripts\pyinstaller.exe"
} else {
    pip install pyinstaller requests psutil pystray Pillow --upgrade --quiet
    $VenvPyinstaller = "pyinstaller"
}

& $VenvPyinstaller --onefile --noconsole --name Sentinel360Agent_64bit $AgentPy --workpath (Join-Path $BaseDir "build") --distpath $ScriptDir --clean --noconfirm

# 2. 32-bit Build
Write-Host "Building 32-bit Agent..." -ForegroundColor Cyan
if (!(Test-Path $Py32Dir)) {
    New-Item -ItemType Directory -Path $Py32Dir | Out-Null
}

$ZipPath = Join-Path $Py32Dir "python-32.zip"
$Url = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-win32.zip"
Invoke-WebRequest -Uri $Url -OutFile $ZipPath
Expand-Archive -Path $ZipPath -DestinationPath $Py32Dir -Force
Remove-Item $ZipPath

$PthFile = Join-Path $Py32Dir "python310._pth"
if (Test-Path $PthFile) {
    $PthContent = Get-Content $PthFile
    $NewPthContent = $PthContent | ForEach-Object {
        if ($_ -eq "#import site") {
            "import site"
        } else {
            $_
        }
    }
    $NewPthContent | Set-Content $PthFile
}

$GetPipPath = Join-Path $Py32Dir "get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPipPath
& "$Py32Dir\python.exe" $GetPipPath
Remove-Item $GetPipPath

# Install pip packages: force binary for psutil/Pillow
Write-Host "Installing 32-bit dependencies..." -ForegroundColor Cyan
& "$Py32Dir\Scripts\pip.exe" install requests pystray pyinstaller --quiet
& "$Py32Dir\Scripts\pip.exe" install psutil Pillow --only-binary=:all: --quiet

& "$Py32Dir\Scripts\pyinstaller.exe" --onefile --noconsole --name Sentinel360Agent_32bit $AgentPy --workpath (Join-Path $BaseDir "build-32") --distpath $ScriptDir --clean --noconfirm

Remove-Item -Recurse -Force $Py32Dir -ErrorAction SilentlyContinue

Write-Output "Build process complete!"
