#!/usr/bin/env bash

# install-agent.sh — Installer Sentinel360 Client Agent untuk Linux
# Jalankan sebagai root: sudo bash install-agent.sh

set -euo pipefail

# Warna output
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${CYAN}  >>  $*${NC}"; }
success() { echo -e "${GREEN}  ✓   $*${NC}"; }
warn()    { echo -e "${YELLOW}  ⚠   $*${NC}"; }
header()  { echo -e "\n${BOLD}=== $* ===${NC}"; }

# Konstanta
INSTALL_DIR="/opt/sentinel-agent"
SERVICE_NAME="sentinel-agent"
RAW_AGENT_URL="https://raw.githubusercontent.com/barangbaru/sentinel360/main/agent/agent.py"

# Pastikan dijalankan sebagai root
if [ "$EUID" -ne 0 ]; then
    warn "Harap jalankan script ini sebagai root (sudo)."
    exit 1
fi

echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║      SENTINEL360 — Agent Installer       ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""

# 1. Input host dan api key
header "Konfigurasi Agent"

# Tanyakan Sentinel360 Host URL
DEFAULT_HOST="http://localhost:8000"
read -rp "  Masukkan Sentinel360 Server Host URL (default: $DEFAULT_HOST): " INPUT_HOST
HOST=${INPUT_HOST:-$DEFAULT_HOST}
# Bersihkan trailing slash dari host URL jika ada
HOST=$(echo "$HOST" | sed 's|/$||')

# Tanyakan Agent API Key (Wajib)
API_KEY=""
while [ -z "$API_KEY" ]; do
    read -rp "  Masukkan Agent API Key (didapat dari dashboard): " API_KEY
    if [ -z "$API_KEY" ]; then
        warn "  API Key wajib diisi!"
    fi
done

# Tanyakan Interval Laporan (Default 15)
DEFAULT_INTERVAL=15
read -rp "  Masukkan interval pelaporan metrik dalam detik (default: $DEFAULT_INTERVAL): " INPUT_INTERVAL
INTERVAL=${INPUT_INTERVAL:-$DEFAULT_INTERVAL}

# 2. Install dependensi sistem
header "[1/5] Install dependensi sistem"
info "Mengupdate paket sistem dan menginstal python3-venv, python3-pip, curl..."
apt-get update -qq
apt-get install -y python3 python3-pip python3-venv curl rsync -y -qq
success "Dependensi sistem terpasang."

# 3. Buat direktori dan unduh agent.py
header "[2/5] Siapkan direktori & unduh agent"
info "Membuat direktori kerja di $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

info "Mengunduh file agent.py..."
curl -sS "$RAW_AGENT_URL" -o "$INSTALL_DIR/agent.py" || {
    warn "Gagal mengunduh agent.py dari GitHub secara online. Mencoba menyalin berkas lokal..."
    # Dapatkan direktori script saat ini
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "$SCRIPT_DIR/agent.py" ]; then
        cp "$SCRIPT_DIR/agent.py" "$INSTALL_DIR/agent.py"
        success "Berhasil menyalin agent.py dari lokal."
    else
        warn "File agent.py lokal tidak ditemukan! Proses instalasi dibatalkan."
        exit 1
    fi
}
success "File agent.py terpasang di $INSTALL_DIR/agent.py"

# 4. Buat file konfigurasi agent_config.json
header "[3/5] Buat file konfigurasi"
info "Menulis file $INSTALL_DIR/agent_config.json..."
cat <<EOF > "$INSTALL_DIR/agent_config.json"
{
    "server_url": "$HOST",
    "api_key": "$API_KEY",
    "interval_seconds": $INTERVAL
}
EOF
success "Konfigurasi berhasil disimpan."

# 5. Buat virtual environment & install dependensi python
header "[4/5] Setup Python Virtual Environment"
info "Membuat venv dan menginstal psutil, requests..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install psutil requests -q
success "Virtual environment siap."

# 6. Buat Systemd Service
header "[5/5] Setup Systemd Service background"
info "Membuat file unit service di /etc/systemd/system/$SERVICE_NAME.service..."
cat <<EOF > /etc/systemd/system/$SERVICE_NAME.service
[Unit]
Description=Sentinel360 Monitoring Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

info "Mengaktifkan dan menjalankan service $SERVICE_NAME..."
systemctl daemon-reload
systemctl enable "$SERVICE_NAME".service
systemctl restart "$SERVICE_NAME".service

success "Service $SERVICE_NAME berhasil diaktifkan!"

# 7. Ringkasan
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║      ✓ INSTALASI AGENT SELESAI           ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Sentinel360 Server : ${CYAN}$HOST${NC}"
echo -e "  API Key            : ${CYAN}$API_KEY${NC}"
echo -e "  Interval Laporan   : ${CYAN}$INTERVAL detik${NC}"
echo -e "  Lokasi Instalasi   : ${CYAN}$INSTALL_DIR${NC}"
echo -e "  Cek Log Service    : ${CYAN}journalctl -u $SERVICE_NAME -f${NC}"
echo -e "  Status Service     : ${CYAN}systemctl status $SERVICE_NAME${NC}"
echo ""

sleep 2
systemctl status "$SERVICE_NAME" --no-pager -l || true
