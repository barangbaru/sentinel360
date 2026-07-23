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

# 3. Deteksi Arsitektur & Tentukan File Executable
Write-Host ""; Write-Host "[1/4] Mendeteksi arsitektur sistem..." -ForegroundColor Cyan
$is64Bit = [Environment]::Is64BitOperatingSystem
$exeName = if ($is64Bit) { "Sentinel360Agent_64bit.exe" } else { "Sentinel360Agent_32bit.exe" }
$archText = if ($is64Bit) { "64-bit (x64)" } else { "32-bit (x86)" }
Write-Host "Arsitektur Sistem: $archText" -ForegroundColor Green
Write-Host "Executable target: $exeName" -ForegroundColor Green

# 4. Siapkan Direktori & Salin Executable
Write-Host ""; Write-Host "[2/4] Menyiapkan direktori & menyalin executable..." -ForegroundColor Cyan
$installDir = "C:\SentinelAgent"
if (-not (Test-Path $installDir)) {
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$sourceExe = Join-Path $scriptDir $exeName
$targetExe = Join-Path $installDir "Sentinel360Agent.exe"

if (Test-Path $sourceExe) {
    Copy-Item $sourceExe $targetExe -Force
    Unblock-File -Path $targetExe -ErrorAction SilentlyContinue
    Write-Host "Berhasil menyalin $exeName ke $targetExe" -ForegroundColor Green
} else {
    Write-Host "$exeName tidak ditemukan secara lokal. Mencoba mengunduh dari GitHub..." -ForegroundColor Yellow
    $rawAgentUrl = "https://raw.githubusercontent.com/barangbaru/sentinel360/main/agent/$exeName"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $rawAgentUrl -OutFile $targetExe -UseBasicParsing -ErrorAction Stop
        
        # Verify download integrity (file size must be greater than 5MB)
        $fileInfo = Get-Item $targetExe
        if ($fileInfo.Length -lt 5MB) {
            Remove-Item $targetExe -ErrorAction SilentlyContinue
            throw "File binary yang diunduh terlalu kecil ($($fileInfo.Length) bytes). Kemungkinan URL raw GitHub mengembalikan error 404 atau repository bersifat private."
        }
        
        Unblock-File -Path $targetExe -ErrorAction SilentlyContinue
        Write-Host "Berhasil mengunduh $exeName dari GitHub." -ForegroundColor Green
    } catch {
        Write-Error "Gagal mengunduh binary: $_"
        Write-Error "File executable agent tidak ditemukan secara lokal maupun di GitHub repo! Proses instalasi dibatalkan."
        Read-Host "Tekan Enter untuk keluar..."
        Exit 1
    }
}

# 5. Buat konfigurasi agent_config.json
Write-Host ""; Write-Host "[3/4] Membuat file konfigurasi..." -ForegroundColor Cyan
$config = @{
    server_url = $hostUrl
    api_key = $apiKey
    interval_seconds = $interval
}
$configJson = $config | ConvertTo-Json
Set-Content -Path "$installDir\agent_config.json" -Value $configJson
Write-Host "Konfigurasi disimpan di $installDir\agent_config.json" -ForegroundColor Green

# 6. Daftarkan sebagai Task Scheduler (berjalan di background)
Write-Host ""; Write-Host "[4/4] Mendaftarkan Agent ke Task Scheduler Windows..." -ForegroundColor Cyan
$taskName = "Sentinel360Agent"

# Hapus task lama jika ada
Register-ScheduledTask -TaskName $taskName -Action (New-ScheduledTaskAction -Execute "cmd.exe") -Trigger (New-ScheduledTaskTrigger -AtStartup) -Principal (New-ScheduledTaskPrincipal -UserId "SYSTEM") -Force | Out-Null
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Buat task baru
$action = New-ScheduledTaskAction -Execute $targetExe -WorkingDirectory $installDir
$trigger = New-ScheduledTaskTrigger -AtStartup
# Jalankan sebagai SYSTEM agar berjalan di background tanpa jendela console
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Daftarkan Scheduled Task
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null

# Jalankan task
Start-ScheduledTask -TaskName $taskName
Write-Host "Task Scheduler $taskName berhasil didaftarkan dan dijalankan." -ForegroundColor Green

# 7. Ringkasan
Write-Output ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "      ✓ INSTALASI AGENT WINDOWS SELESAI           " -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
Write-Output ""
Write-Output "  Sentinel360 Server : $hostUrl"
Write-Output "  API Key            : $apiKey"
Write-Output "  Interval Laporan   : $interval detik"
Write-Output "  Direktori Kerja    : $installDir"
Write-Output "  Executable Agent   : $targetExe"
Write-Output "  Nama Task Windows  : $taskName"
Write-Output ""
Write-Host "Agent sekarang berjalan secara background sebagai Task Windows." -ForegroundColor Yellow
Write-Host "Anda dapat memeriksa statusnya di Task Scheduler (Taskschd.msc) atau lewat PowerShell:" -ForegroundColor Gray
Write-Host "Get-ScheduledTask -TaskName $taskName" -ForegroundColor Cyan
Write-Output ""

Read-Host "Tekan Enter untuk menutup..."
