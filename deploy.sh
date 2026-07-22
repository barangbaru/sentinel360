#!/usr/bin/env bash

# deploy.sh - Script deployment otomatis untuk Sentinel360 di Ubuntu Server
# Mendukung instalasi awal (setup), deployment update berkala, dan rollback instan.
# Menerapkan best practice directory release versioning berbasis symlink.

set -euo pipefail

# ==========================================
# KONFIGURASI APLIKASI
# ==========================================
APP_NAME="sentinel360"
DEPLOY_DIR="/var/www/$APP_NAME"
RELEASES_DIR="$DEPLOY_DIR/releases"
SHARED_DIR="$DEPLOY_DIR/shared"
REPO_DIR="$DEPLOY_DIR/repo"
CURRENT_LINK="$DEPLOY_DIR/current"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/$APP_NAME.service"
NGINX_CONF_FILE="/etc/nginx/sites-available/$APP_NAME"
NGINX_SYMLINK="/etc/nginx/sites-enabled/$APP_NAME"

# Repository Git (URL ini dapat disesuaikan pada saat setup awal)
GIT_REPO_URL="https://github.com/username/Sentinel360.git"
DEFAULT_BRANCH="main"
KEEP_RELEASES=5

# ==========================================
# BASH HELPER (LOGGING & WARNA)
# ==========================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'
NC_BOLD='\033[1m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUKSES]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[PERINGATAN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# ==========================================
# FUNGSI INSTALASI AWAL (SETUP)
# ==========================================
cmd_setup() {
    log_info "Memulai instalasi awal (setup) di Server Ubuntu..."
    
    # 1. Update package list & install system requirements
    log_info "Menginstal dependensi sistem (Python, Git, Nginx, SQLite)..."
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-pip python3-venv git nginx sqlite3 curl rsync

    # 2. Buat struktur direktori deployment
    log_info "Membuat struktur direktori di $DEPLOY_DIR..."
    sudo mkdir -p "$RELEASES_DIR" "$SHARED_DIR" "$REPO_DIR"
    
    # Atur kepemilikan direktori ke user saat ini agar deploy tidak memerlukan hak akses root terus-menerus
    CURRENT_USER=$(whoami)
    sudo chown -R "$CURRENT_USER:$CURRENT_USER" "$DEPLOY_DIR"

    # 3. Setup git repo awal
    if [ ! -d "$REPO_DIR/.git" ]; then
        # Cek jika script dipanggil dari local repo, gunakan remote origin sebagai default
        if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
            LOCAL_GIT_URL=$(git remote get-url origin 2>/dev/null || git rev-parse --show-toplevel)
            log_info "Mendeteksi Git remote lokal: $LOCAL_GIT_URL"
            GIT_REPO_URL="$LOCAL_GIT_URL"
        fi
        
        echo -e "${NC_BOLD}Konfigurasi Git Repository:${NC}"
        read -p "Masukkan URL Git Repository aplikasi [$GIT_REPO_URL]: " input_git_url
        GIT_REPO_URL=${input_git_url:-$GIT_REPO_URL}
        
        log_info "Mengkloning repository git ke $REPO_DIR..."
        git clone "$GIT_REPO_URL" "$REPO_DIR"
    else
        log_info "Repository Git sudah ada di $REPO_DIR."
    fi

    # 4. Buat file konfig default (.env) di folder shared jika belum ada
    if [ ! -f "$SHARED_DIR/.env" ]; then
        log_info "Membuat file konfigurasi default .env di $SHARED_DIR/.env..."
        cat <<EOF > "$SHARED_DIR/.env"
# Konfigurasi Environment Sentinel360
PORT=8000
HOST=0.0.0.0
DATABASE_URL=sqlite:///$SHARED_DIR/sentinel360.db
# Tambahkan konfigurasi sensitif atau variabel env lainnya di bawah ini
EOF
    fi

    # 5. Inisialisasi database SQLite kosong di folder shared jika belum ada
    if [ ! -f "$SHARED_DIR/sentinel360.db" ]; then
        log_info "Membuat file database SQLite di $SHARED_DIR/sentinel360.db..."
        touch "$SHARED_DIR/sentinel360.db"
    fi

    # 6. Setup Systemd Service
    log_info "Membuat konfigurasi Systemd Service di $SYSTEMD_SERVICE_FILE..."
    sudo bash -c "cat <<EOF > $SYSTEMD_SERVICE_FILE
[Unit]
Description=Sentinel360 Monitoring Server FastAPI
After=network.target

[Service]
User=$CURRENT_USER
WorkingDirectory=$CURRENT_LINK
EnvironmentFile=$SHARED_DIR/.env
ExecStart=$CURRENT_LINK/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

    sudo systemctl daemon-reload

    # 7. Setup Nginx Config
    log_info "Membuat konfigurasi Nginx Reverse Proxy di $NGINX_CONF_FILE..."
    sudo bash -c "cat <<EOF > $NGINX_CONF_FILE
server {
    listen 80;
    server_name _; # Ganti dengan domain atau IP server jika sudah ada

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Dukungan WebSocket
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \"upgrade\";
    }
}
EOF"

    # Aktifkan config nginx & hapus default jika ada
    if [ -f "/etc/nginx/sites-enabled/default" ]; then
        log_info "Menonaktifkan konfigurasi Nginx default..."
        sudo rm -f "/etc/nginx/sites-enabled/default"
    fi

    if [ ! -f "$NGINX_SYMLINK" ]; then
        log_info "Mengaktifkan konfigurasi Nginx Sentinel360..."
        sudo ln -s "$NGINX_CONF_FILE" "$NGINX_SYMLINK"
    fi

    log_info "Melakukan restart Nginx..."
    sudo systemctl restart nginx

    log_success "Setup awal selesai!"
    log_info "Ketik './deploy.sh deploy' untuk melakukan deployment rilis pertama."
}

# ==========================================
# FUNGSI DEPLOY UPDATE APLIKASI
# ==========================================
cmd_deploy() {
    local branch="${1:-$DEFAULT_BRANCH}"
    local timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")
    
    log_info "Memulai deployment dari branch/tag: $branch..."
    
    # 1. Update source code dari Git repo
    log_info "Menarik source code terbaru dari Git repository..."
    cd "$REPO_DIR"
    git fetch --all
    
    # Cek apakah branch/tag ada
    if ! git rev-parse --verify "origin/$branch" >/dev/null 2>&1 && ! git rev-parse --verify "$branch" >/dev/null 2>&1; then
        log_error "Branch atau Tag '$branch' tidak ditemukan di Git."
        exit 1
    fi
    
    git checkout -f "$branch"
    git pull origin "$branch" || log_warning "Tidak dapat git pull secara remote, menggunakan code lokal saat ini."

    # Dapatkan commit hash terakhir untuk penamaan versi rilis
    local commit_hash
    commit_hash=$(git rev-parse --short HEAD)
    local release_name="release_${timestamp}_${commit_hash}"
    local release_path="$RELEASES_DIR/$release_name"

    log_info "Membuat direktori rilis baru: $release_name..."
    mkdir -p "$release_path"

    # 2. Salin source code ke direktori rilis baru (kecuali folder venv dan git meta)
    log_info "Menyalin file source code..."
    rsync -av --exclude="venv" --exclude=".git" --exclude=".github" --exclude="deploy.sh" "$REPO_DIR/" "$release_path/"

    # 3. Setup Virtual Environment di direktori rilis baru
    log_info "Membuat virtual environment Python..."
    python3 -m venv "$release_path/venv"
    
    log_info "Menginstal dependensi python dari requirements.txt..."
    # Menggunakan cache pip global di folder shared agar proses instalasi cepat
    mkdir -p "$SHARED_DIR/pip_cache"
    "$release_path/venv/bin/pip" install --upgrade pip
    "$release_path/venv/bin/pip" install --cache-dir "$SHARED_DIR/pip_cache" -r "$release_path/requirements.txt"

    # 4. Link file konfigurasi dan database persisten (.env & sentinel360.db)
    log_info "Menghubungkan database dan file .env dari shared ke direktori rilis baru..."
    # Hapus file sqlite bawaan jika tersalin secara tidak sengaja
    rm -f "$release_path/sentinel360.db"
    ln -s "$SHARED_DIR/sentinel360.db" "$release_path/sentinel360.db"
    ln -s "$SHARED_DIR/.env" "$release_path/.env"

    # 5. Ubah symlink 'current' untuk menunjuk ke rilis baru secara atomik
    log_info "Mengubah symlink aktif ke rilis baru secara atomik..."
    ln -sfn "$release_path" "$CURRENT_LINK.tmp"
    mv -Tf "$CURRENT_LINK.tmp" "$CURRENT_LINK"

    # 6. Restart systemd service
    log_info "Melakukan restart service sentinel360..."
    sudo systemctl daemon-reload
    sudo systemctl enable "$APP_NAME.service"
    sudo systemctl restart "$APP_NAME.service"

    # 7. Bersihkan rilis lama (hanya menyimpan N rilis terakhir)
    cmd_cleanup

    log_success "Deployment versi $release_name berhasil dijalankan!"
    echo -e "Aplikasi sekarang dapat diakses secara publik."
}

# ==========================================
# FUNGSI ROLLBACK KE VERSI SEBELUMNYA
# ==========================================
cmd_rollback() {
    log_info "Memulai proses rollback ke versi sebelumnya..."
    
    # Cari semua sub-direktori di folder releases, urutkan berdasarkan abjad (timestamp)
    # Ini akan mengurutkan rilis dari terlama ke terbaru
    local releases
    releases=$(find "$RELEASES_DIR" -maxdepth 1 -mindepth 1 -type d | sort)
    
    local count
    count=$(echo "$releases" | wc -w)
    
    if [ "$count" -lt 2 ]; then
        log_error "Tidak ada rilis cadangan sebelumnya untuk melakukan rollback (Rilis saat ini: $count)."
        exit 1
    fi

    # Dapatkan direktori sebelum rilis saat ini (baris kedua dari bawah)
    local prev_release
    prev_release=$(echo "$releases" | tail -n 2 | head -n 1)

    log_info "Mengubah symlink aktif ke rilis sebelumnya secara atomik: $(basename "$prev_release")...."
    ln -sfn "$prev_release" "$CURRENT_LINK.tmp"
    mv -Tf "$CURRENT_LINK.tmp" "$CURRENT_LINK"

    log_info "Melakukan restart service sentinel360..."
    sudo systemctl restart "$APP_NAME.service"

    log_success "Rollback sukses! Aplikasi sekarang mengarah ke $(basename "$prev_release")."
}

# ==========================================
# FUNGSI MEMBERSIHKAN RILIS LAMA
# ==========================================
cmd_cleanup() {
    log_info "Merapikan rilis lama (Hanya menyimpan $KEEP_RELEASES rilis terbaru)..."
    
    local dirs
    dirs=$(find "$RELEASES_DIR" -maxdepth 1 -mindepth 1 -type d | sort)
    
    local count
    count=$(echo "$dirs" | wc -w)

    if [ "$count" -gt "$KEEP_RELEASES" ]; then
        local remove_count=$((count - KEEP_RELEASES))
        log_info "Ditemukan $count rilis. Menghapus $remove_count rilis tertua..."
        echo "$dirs" | head -n "$remove_count" | while read -r dir_to_remove; do
            log_info "Menghapus rilis usang: $(basename "$dir_to_remove")"
            rm -rf "$dir_to_remove"
        done
        log_success "Pembersihan rilis lama selesai."
    else
        log_info "Jumlah rilis saat ini ($count) masih di bawah batas maksimum ($KEEP_RELEASES). Tidak ada rilis yang dihapus."
    fi
}

# ==========================================
# ENTRYPOINT UTAMA (PARSING ARGUMEN)
# ==========================================
cmd_help() {
    echo -e "${NC_BOLD}Sentinel360 Ubuntu Deployment Tool${NC}"
    echo "Penggunaan: $0 {setup|deploy|rollback|cleanup}"
    echo ""
    echo "Perintah:"
    echo "  setup            Instalasi awal system packages, struktur direktori, systemd & nginx."
    echo "  deploy [branch]  Deploy source code terbaru dari branch/tag tertentu (default: $DEFAULT_BRANCH)."
    echo "  rollback         Kembalikan aplikasi ke versi rilis sebelumnya secara instan."
    echo "  cleanup          Hapus rilis lama secara manual, menyisakan $KEEP_RELEASES versi terbaru."
    echo "  help             Tampilkan panduan penggunaan ini."
}

# Pastikan setidaknya ada 1 argumen
if [ $# -lt 1 ]; then
    cmd_help
    exit 1
fi

ACTION="$1"
shift || true

case "$ACTION" in
    setup)
        cmd_setup
        ;;
    deploy)
        cmd_deploy "${1:-}"
        ;;
    rollback)
        cmd_rollback
        ;;
    cleanup)
        cmd_cleanup
        ;;
    help|--help|-h)
        cmd_help
        ;;
    *)
        log_error "Perintah tidak dikenal: $ACTION"
        cmd_help
        exit 1
        ;;
esac
