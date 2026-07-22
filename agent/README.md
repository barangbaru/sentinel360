# Sentinel360 Client Agent

Sentinel360 Agent adalah program ringan berbasis Python yang berjalan di server target (Linux / Windows) untuk mengumpulkan data performa sistem dan melaporkannya ke server Sentinel360 pusat.

## Fitur
- Pemantauan CPU, RAM, Disk, dan Uptime sistem secara real-time.
- Pemantauan Kecepatan Jaringan (Network Speed - Incoming & Outgoing dalam Kbps).
- Keamanan berbasis Token API Key.
- Cross-platform: Mendukung Linux dan Windows Server.

---

### Cara Cepat (Automated Installer untuk Linux/Ubuntu):

Cukup unduh dan jalankan script installer otomatis di server target Anda untuk mengunduh, mengonfigurasi, dan memasang agent sebagai background service (Systemd) secara otomatis:

```bash
# Unduh script installer
curl -sS -O https://raw.githubusercontent.com/barangbaru/sentinel360/main/agent/install-agent.sh

# Jalankan installer dengan hak akses root
sudo bash install-agent.sh
```

Script akan menampilkan prompt interaktif untuk memasukkan host URL Sentinel360 pusat dan API Key server yang didapat dari web dashboard.

---

### Cara Manual:

1. **Unduh/Salin Berkas**:
   Salin file `agent.py` ke direktori kerja di server target Anda.

2. **Install Dependensi**:
   Buka terminal/command prompt dan jalankan perintah berikut:
   ```bash
   pip install psutil requests
   ```

3. **Inisialisasi Konfigurasi**:
   Jalankan agent sekali untuk membuat file konfigurasi default:
   ```bash
   python agent.py
   ```
   Akan terbentuk file bernama `agent_config.json` di direktori yang sama.

4. **Konfigurasi Berkas `agent_config.json`**:
   Buka berkas `agent_config.json` dan sesuaikan nilainya:
   ```json
   {
       "server_url": "http://<IP_SENTINEL360_SERVER>:8000",
       "api_key": "<API_KEY_SERVER_ANDA>",
       "interval_seconds": 15
   }
   ```
   *Catatan: Dapatkan `<API_KEY_SERVER_ANDA>` saat Anda mendaftarkan server baru bertipe **Agent** di web dashboard Sentinel360.*

5. **Jalankan Agent Kembali**:
   ```bash
   python agent.py
   ```
   Agent akan mulai melaporkan metrik performa ke server Sentinel360 setiap 15 detik.

---

## Menjalankan Sebagai Background Service

### 1. Di Linux (Systemd Service)
Agar agent terus berjalan secara otomatis setelah booting, Anda bisa membuat systemd service:

1. Buat file service:
   ```bash
   sudo nano /etc/systemd/system/sentinel-agent.service
   ```
2. Isi file tersebut dengan konfigurasi berikut (sesuaikan path):
   ```ini
   [Unit]
   Description=Sentinel360 Monitoring Agent
   After=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/path/ke/direktori/agent
   ExecStart=/usr/bin/python3 /path/ke/direktori/agent/agent.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```
3. Reload systemd daemon & jalankan service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable sentinel-agent.service
   sudo systemctl start sentinel-agent.service
   ```
4. Cek status:
   ```bash
   sudo systemctl status sentinel-agent.service
   ```

### 2. Di Windows (NSSM - Non-Sucking Service Manager)
Untuk Windows, Anda bisa menggunakan utility gratis **NSSM** untuk memasang python script sebagai service:

1. Unduh NSSM dari [nssm.cc](https://nssm.cc/).
2. Buka Command Prompt Administrator dan jalankan:
   ```cmd
   nssm install SentinelAgent
   ```
3. Di panel dialog NSSM yang muncul:
   - **Path**: Path ke interpreter Python Anda (contoh: `C:\Python310\python.exe`).
   - **Startup directory**: Direktori tempat file `agent.py` berada.
   - **Arguments**: Path file `agent.py` (contoh: `C:\SentinelAgent\agent.py`).
4. Klik **Install service** dan jalankan service-nya melalui `services.msc` atau `net start SentinelAgent`.
