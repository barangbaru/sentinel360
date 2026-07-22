# install-agent.ps1 — Installer Sentinel360 Client Agent untuk Windows
# Jalankan sebagai Administrator di PowerShell

# 1. Pastikan dijalankan sebagai Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Warning "Harap jalankan PowerShell sebagai Administrator!"
    # Relaunch script as Administrator
    Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    Exit
}

Clear-Host
Write-Output "=================================================="
Write-Output "      SENTINEL360 — Windows Agent Installer       "
Write-Output "=================================================="
Write-Output ""

# 2. Input Konfigurasi
Write-Host "--- Konfigurasi Agent ---" -ForegroundColor Cyan
$defaultHost = "http://localhost:8000"
$hostUrl = Read-Host "Masukkan Sentinel360 Server Host URL (default: $defaultHost)"
if ([string]::IsNullOrWhiteSpace($hostUrl)) { $hostUrl = $defaultHost }
$hostUrl = $hostUrl.TrimEnd('/')

$apiKey = ""
while ([string]::IsNullOrWhiteSpace($apiKey)) {
    $apiKey = Read-Host "Masukkan Agent API Key (didapat dari dashboard)"
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        Write-Warning "API Key wajib diisi!"
    }
}

$defaultInterval = 15
$intervalInput = Read-Host "Masukkan interval pelaporan metrik dalam detik (default: $defaultInterval)"
if ([string]::IsNullOrWhiteSpace($intervalInput)) { $intervalInput = $defaultInterval }
$interval = [int]$intervalInput

# 3. Cek Python
Write-Host ""; Write-Host "[1/5] Memeriksa instalasi Python..." -ForegroundColor Cyan
$pythonPath = Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $pythonPath) {
    Write-Host "Python tidak ditemukan di PATH. Mencoba menginstal Python menggunakan winget..." -ForegroundColor Yellow
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
        # Jalankan winget installer untuk Python
        Start-Process winget -ArgumentList "install --id Python.Python.3 --silent --accept-source-agreements --accept-package-agreements" -NoNewWindow -Wait
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        $pythonPath = Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    }
}

if (-not $pythonPath) {
    Write-Error "Python tidak ditemukan dan gagal diinstal otomatis. Harap unduh dan instal Python 3 dari https://www.python.org/downloads/ (pastikan mencentang 'Add Python to PATH') lalu jalankan kembali script ini."
    Read-Host "Tekan Enter untuk keluar..."
    Exit 1
}

$pythonwPath = $pythonPath -replace 'python.exe$', 'pythonw.exe'
Write-Host "Menggunakan Python: $pythonPath" -ForegroundColor Green

# 4. Siapkan Direktori & Unduh berkas
Write-Host ""; Write-Host "[2/5] Menyiapkan direktori & mengunduh agent..." -ForegroundColor Cyan
$installDir = "C:\SentinelAgent"
if (-not (Test-Path $installDir)) {
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
}

$rawAgentUrl = "https://raw.githubusercontent.com/barangbaru/sentinel360/main/agent/agent.py"
Write-Host "Mengunduh agent.py..." -ForegroundColor Gray
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $rawAgentUrl -OutFile "$installDir\agent.py" -UseBasicParsing
} catch {
    Write-Warning "Gagal mengunduh agent.py secara online. Mencoba menyalin berkas lokal jika ada..."
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
    if (Test-Path "$scriptDir\agent.py") {
        Copy-Item "$scriptDir\agent.py" "$installDir\agent.py" -Force
        Write-Host "Berhasil menyalin agent.py dari direktori lokal." -ForegroundColor Green
    } else {
        Write-Error "File agent.py tidak ditemukan! Proses instalasi dibatalkan."
        Read-Host "Tekan Enter untuk keluar..."
        Exit 1
    }
}

# 5. Buat konfigurasi agent_config.json
Write-Host ""; Write-Host "[3/5] Membuat file konfigurasi..." -ForegroundColor Cyan
$config = @{
    server_url = $hostUrl
    api_key = $apiKey
    interval_seconds = $interval
}
$configJson = $config | ConvertTo-Json
Set-Content -Path "$installDir\agent_config.json" -Value $configJson
Write-Host "Konfigurasi disimpan di $installDir\agent_config.json" -ForegroundColor Green

# 6. Install dependensi python
Write-Host ""; Write-Host "[4/5] Menginstal dependensi python (psutil, requests)..." -ForegroundColor Cyan
Start-Process $pythonPath -ArgumentList "-m pip install --upgrade pip --quiet" -NoNewWindow -Wait
Start-Process $pythonPath -ArgumentList "-m pip install psutil requests --quiet" -NoNewWindow -Wait
Write-Host "Dependensi terpasang." -ForegroundColor Green

# 7. Daftarkan sebagai Task Scheduler (berjalan di background)
Write-Host ""; Write-Host "[5/5] Mendaftarkan Agent ke Task Scheduler Windows..." -ForegroundColor Cyan
$taskName = "Sentinel360Agent"

# Hapus task lama jika ada
Register-ScheduledTask -TaskName $taskName -Action (New-ScheduledTaskAction -Execute "cmd.exe") -Trigger (New-ScheduledTaskTrigger -AtStartup) -Principal (New-ScheduledTaskPrincipal -UserId "SYSTEM") -Force | Out-Null
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Buat task baru
$action = New-ScheduledTaskAction -Execute $pythonwPath -Argument "$installDir\agent.py" -WorkingDirectory $installDir
$trigger = New-ScheduledTaskTrigger -AtStartup
# Jalankan sebagai SYSTEM agar berjalan di background tanpa jendela console
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Daftarkan Scheduled Task
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null

# Jalankan task
Start-ScheduledTask -TaskName $taskName
Write-Host "Task Scheduler $taskName berhasil didaftarkan dan dijalankan." -ForegroundColor Green

# 8. Ringkasan
Write-Output ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "      ✓ INSTALASI AGENT WINDOWS SELESAI           " -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
Write-Output ""
Write-Output "  Sentinel360 Server : $hostUrl"
Write-Output "  API Key            : $apiKey"
Write-Output "  Interval Laporan   : $interval detik"
Write-Output "  Direktori Kerja    : $installDir"
Write-Output "  Nama Task Windows  : $taskName"
Write-Output ""
Write-Host "Agent sekarang berjalan secara background sebagai Task Windows." -ForegroundColor Yellow
Write-Host "Anda dapat memeriksa statusnya di Task Scheduler (Taskschd.msc) atau lewat PowerShell:" -ForegroundColor Gray
Write-Host "Get-ScheduledTask -TaskName $taskName" -ForegroundColor Cyan
Write-Output ""

Read-Host "Tekan Enter untuk menutup..."
