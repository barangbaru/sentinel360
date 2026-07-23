#!/bin/bash
# deploy.sh — Install & Update Sentinel360 di Ubuntu 20.04/22.04/24.04
# Jalankan sebagai root: sudo bash deploy.sh [--version vX.Y.Z]
#
# Idempotent — aman dijalankan berulang:
#   Install baru  : setup lengkap dari nol
#   Update/redeploy: tarik kode baru, update deps, restart — database TIDAK tersentuh

set -e

# ── Parse argumen ─────────────────────────────────────────────────────────────
TARGET_VERSION=""
AUTO_MODE=false   # --auto: skip semua prompt, pakai config .env yang ada
while [[ $# -gt 0 ]]; do
    case $1 in
        --version) TARGET_VERSION="$2"; shift 2 ;;
        --auto)    AUTO_MODE=true; shift ;;
        *) shift ;;
    esac
done

# ── Warna output ──────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${CYAN}  >>  $*${NC}"; }
success() { echo -e "${GREEN}  ✓   $*${NC}"; }
warn()    { echo -e "${YELLOW}  ⚠   $*${NC}"; }
header()  { echo -e "\n${BOLD}=== $* ===${NC}"; }

# ── Konstanta ─────────────────────────────────────────────────────────────────
APP_DIR="/var/www/sentinel360"
DATA_DIR="/var/lib/sentinel360"
SERVICE_NAME="sentinel360"
REPO_URL="https://github.com/barangbaru/sentinel360.git"
REPO_SUBDIR="."
VERSION_FILE="$DATA_DIR/.deployed_version"

IS_UPDATE=false
[ -f "$APP_DIR/run_server.py" ] && IS_UPDATE=true

# ── Baca versi yang sudah terinstall ─────────────────────────────────────────
CURRENT_VERSION="(belum terinstall)"
if [ -f "$VERSION_FILE" ]; then
    CURRENT_VERSION=$(cat "$VERSION_FILE")
fi

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║      SENTINEL360 — Deploy Script         ║${NC}"
if $IS_UPDATE; then
echo -e "${BOLD}║         MODE: UPDATE APLIKASI            ║${NC}"
else
echo -e "${BOLD}║         MODE: INSTALL BARU               ║${NC}"
fi
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""

# ════════════════════════════════════════════════════════════════════════════
# BAGIAN 0a — Cek versi & pilihan upgrade
# ════════════════════════════════════════════════════════════════════════════
if $IS_UPDATE; then
    header "Cek Versi"

    # Fetch semua tag dari GitHub tanpa clone (ls-remote jauh lebih cepat)
    apt-get install -y git -qq 2>/dev/null || true
    ALL_TAGS=$(git ls-remote --tags --refs "$REPO_URL" 2>/dev/null \
        | awk '{print $2}' | grep -oP 'v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V || true)

    # Ambil versi latest dari tag
    LATEST_TAG=$(echo "$ALL_TAGS" | tail -1)
    LATEST_VERSION=${LATEST_TAG#v}

    info "Versi terinstall : $CURRENT_VERSION"
    info "Versi terbaru    : ${LATEST_VERSION:-main (no tags)}"

    if [ -n "$TARGET_VERSION" ]; then
        # Versi sudah ditentukan via --version, langsung pakai
        info "Target versi     : v$TARGET_VERSION"
    elif [ -n "$ALL_TAGS" ] && [ "$CURRENT_VERSION" != "$LATEST_VERSION" ]; then
        # Cari tag yang lebih baru dari yang terinstall
        if [ "$CURRENT_VERSION" != "(belum terinstall)" ] && [ "$CURRENT_VERSION" != "unknown" ]; then
            NEWER_TAGS=$(echo "$ALL_TAGS" | awk -v cur="v$CURRENT_VERSION" 'BEGIN{found=0} $0==cur{found=1; next} found{print}')
        else
            NEWER_TAGS="$ALL_TAGS"
        fi

        TAG_COUNT=$(echo "$NEWER_TAGS" | grep -c '^v' 2>/dev/null | tr -d '[:space:]' || echo 0)
        TAG_COUNT=${TAG_COUNT:-0}

        if [ "$TAG_COUNT" -gt 1 ]; then
            echo ""
            echo -e "  ${BOLD}Ada $TAG_COUNT versi baru tersedia:${NC}"
            echo "$NEWER_TAGS" | while read -r tag; do
                echo -e "    ${CYAN}$tag${NC}"
            done
            echo ""
            if $AUTO_MODE; then
                TARGET_VERSION="$LATEST_VERSION"
                info "Auto mode — upgrade ke versi terbaru: v$TARGET_VERSION"
            else
                echo -e "  ${BOLD}[1]${NC} Upgrade ke versi terbaru sekaligus (${LATEST_TAG})"
                echo -e "  ${BOLD}[2]${NC} Upgrade bertahap (satu versi per deploy)"
                echo ""
                read -rp "  Pilih [1/2] (default: 1): " UPGRADE_CHOICE
                UPGRADE_CHOICE=${UPGRADE_CHOICE:-1}
                if [ "$UPGRADE_CHOICE" = "2" ]; then
                    STEP_TAG=$(echo "$NEWER_TAGS" | head -1)
                    TARGET_VERSION="${STEP_TAG#v}"
                    warn "Mode bertahap — upgrade ke $STEP_TAG dulu."
                    warn "Jalankan deploy ulang untuk versi berikutnya."
                else
                    TARGET_VERSION="$LATEST_VERSION"
                    info "Upgrade ke versi terbaru: v$TARGET_VERSION"
                fi
            fi
        elif [ "$TAG_COUNT" -eq 1 ]; then
            TARGET_VERSION=$(echo "$NEWER_TAGS" | head -1 | sed 's/^v//')
            info "Update ke v$TARGET_VERSION"
        fi
    else
        info "Sudah versi terbaru — deploy ulang kode yang sama."
    fi
fi

# ════════════════════════════════════════════════════════════════════════════
# BAGIAN 0 — Pilihan Database (hanya saat install baru atau paksa re-config)
# ════════════════════════════════════════════════════════════════════════════
DB_TYPE="sqlite"
PG_HOST="localhost"
PG_PORT="5432"
PG_NAME="sentinel360_db"
PG_USER="sentinel"
PG_PASS=""

# Cek apakah .env sudah ada dengan config PostgreSQL
if [ -f "$APP_DIR/.env" ] && grep -q "^DB_TYPE=postgresql" "$APP_DIR/.env" 2>/dev/null; then
    DB_TYPE="postgresql"
    PG_HOST=$(grep '^PG_HOST=' "$APP_DIR/.env" | cut -d= -f2-)
    PG_PORT=$(grep '^PG_PORT=' "$APP_DIR/.env" | cut -d= -f2-)
    PG_NAME=$(grep '^PG_NAME=' "$APP_DIR/.env" | cut -d= -f2-)
    PG_USER=$(grep '^PG_USER=' "$APP_DIR/.env" | cut -d= -f2-)
    PG_PASS=$(grep '^PG_PASS=' "$APP_DIR/.env" | cut -d= -f2-)
    warn "Config PostgreSQL ditemukan di .env — menggunakan yang sudah ada."
    warn "  Host: $PG_HOST:$PG_PORT  DB: $PG_NAME  User: $PG_USER"
elif $AUTO_MODE; then
    # Auto mode: tidak ada .env PostgreSQL & tidak interaktif → pakai SQLite
    info "Auto mode — tidak ada config DB di .env, gunakan SQLite."
else

header "Pilihan Database"
echo ""
echo -e "  ${BOLD}[1]${NC} SQLite       — Simple, cocok untuk single-server (default)"
echo -e "  ${BOLD}[2]${NC} PostgreSQL   — Lebih robust, siap untuk multi-process / scale-up"
echo ""
read -rp "  Pilih [1/2] (default: 1): " DB_CHOICE
DB_CHOICE=${DB_CHOICE:-1}

if [ "$DB_CHOICE" = "2" ]; then
    DB_TYPE="postgresql"
    echo ""
    echo -e "  ${BOLD}[A]${NC} Install & setup PostgreSQL otomatis di server ini"
    echo -e "  ${BOLD}[B]${NC} Gunakan PostgreSQL yang sudah ada (input parameter)"
    echo ""
    read -rp "  Pilih [A/B] (default: A): " PG_SETUP
    PG_SETUP=${PG_SETUP:-A}
    PG_SETUP=$(echo "$PG_SETUP" | tr '[:lower:]' '[:upper:]')

    if [ "$PG_SETUP" = "A" ]; then
        header "Install PostgreSQL"
        apt-get update -qq
        apt-get install -y postgresql postgresql-contrib
        systemctl enable postgresql
        systemctl start postgresql
        PG_PASS=$(python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(20)))")
        PG_HOST="localhost"; PG_PORT="5432"
        read -rp "  Nama database (default: sentinel360_db): " INPUT_PG_NAME
        PG_NAME=${INPUT_PG_NAME:-sentinel360_db}
        read -rp "  Nama user PostgreSQL (default: sentinel): " INPUT_PG_USER
        PG_USER=${INPUT_PG_USER:-sentinel}
        info "Membuat user '$PG_USER' dan database '$PG_NAME'..."
        sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$PG_USER'" | grep -q 1 || \
            sudo -u postgres psql -c "CREATE USER $PG_USER WITH PASSWORD '$PG_PASS';"
        sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$PG_NAME'" | grep -q 1 || \
            sudo -u postgres psql -c "CREATE DATABASE $PG_NAME OWNER $PG_USER;"
        sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $PG_NAME TO $PG_USER;"
        sudo -u postgres psql -d "$PG_NAME" -c "GRANT ALL ON SCHEMA public TO $PG_USER;" 2>/dev/null || true
        success "PostgreSQL siap: $PG_USER@$PG_HOST:$PG_PORT/$PG_NAME"
        echo -e "\n  ${YELLOW}Kredensial: user=$PG_USER pass=$PG_PASS db=$PG_NAME${NC}\n"
    else
        header "Konfigurasi PostgreSQL"
        read -rp "  Host (default: localhost): " INPUT_HOST; PG_HOST=${INPUT_HOST:-localhost}
        read -rp "  Port (default: 5432): "      INPUT_PORT; PG_PORT=${INPUT_PORT:-5432}
        read -rp "  Nama Database: " PG_NAME
        read -rp "  Username: "      PG_USER
        read -srp "  Password: "    PG_PASS; echo ""
        apt-get install -y postgresql-client -qq 2>/dev/null || true
        PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_NAME" -c '\q' 2>/dev/null \
            && success "Koneksi PostgreSQL berhasil!" \
            || warn "Koneksi gagal — lanjutkan dengan hati-hati."
    fi
fi

fi  # end if .env belum ada

# ════════════════════════════════════════════════════════════════════════════
# [1] Sistem dependencies
# ════════════════════════════════════════════════════════════════════════════
header "[1/7] Install system dependencies"
if ! $IS_UPDATE; then
    apt-get update -qq
    PKGS="python3 python3-pip python3-venv nginx git rsync"
    if [ "$DB_TYPE" = "postgresql" ]; then
        PKGS="$PKGS libpq-dev python3-dev postgresql-client"
    fi
    apt-get install -y $PKGS
    success "System dependencies terpasang."
else
    # Pastikan libpq-dev dan postgresql-client ada jika PostgreSQL
    if [ "$DB_TYPE" = "postgresql" ]; then
        apt-get install -y libpq-dev python3-dev postgresql-client -qq
    fi
    info "Mode update — sistem dependencies dilewati."
fi

# ════════════════════════════════════════════════════════════════════════════
# [2] Tarik kode terbaru
# ════════════════════════════════════════════════════════════════════════════
header "[2/7] Tarik kode dari GitHub"
TMPDIR_DEPLOY=$(mktemp -d)
if [ -n "$TARGET_VERSION" ]; then
    info "Clone tag v$TARGET_VERSION..."
    git clone --depth=1 --branch "v$TARGET_VERSION" "$REPO_URL" "$TMPDIR_DEPLOY/repo" -q \
        || { warn "Tag v$TARGET_VERSION tidak ditemukan, clone dari main..."; \
             git clone --depth=1 "$REPO_URL" "$TMPDIR_DEPLOY/repo" -q; }
else
    info "Clone branch main (latest)..."
    git clone --depth=1 "$REPO_URL" "$TMPDIR_DEPLOY/repo" -q
fi

mkdir -p "$APP_DIR"
rsync -a --delete \
    --exclude='.env' \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='*.db' \
    "$TMPDIR_DEPLOY/repo/$REPO_SUBDIR/" "$APP_DIR/"

# Tulis .git_info agar aplikasi bisa tampilkan info commit di UI jika dibutuhkan
GIT_HASH=$(git -C "$TMPDIR_DEPLOY/repo" rev-parse --short HEAD 2>/dev/null || echo "-")
GIT_MSG=$(git -C "$TMPDIR_DEPLOY/repo" log -1 --pretty=%s 2>/dev/null || echo "-")
GIT_DATE=$(git -C "$TMPDIR_DEPLOY/repo" log -1 --pretty=%ci 2>/dev/null || echo "-")
printf '%s\n%s\n%s\n' "$GIT_HASH" "$GIT_MSG" "$GIT_DATE" > "$APP_DIR/.git_info"

# Dapatkan versi untuk ditulis ke file versi
DEPLOYED_VERSION=$(git -C "$TMPDIR_DEPLOY/repo" describe --tags --always 2>/dev/null || echo "${TARGET_VERSION:-unknown}")

rm -rf "$TMPDIR_DEPLOY"
success "Kode berhasil diperbarui."

# ════════════════════════════════════════════════════════════════════════════
# [3] Virtual environment & dependencies
# ════════════════════════════════════════════════════════════════════════════
header "[3/7] Update virtual environment"
cd "$APP_DIR"
rm -rf venv
python3 -m venv venv
venv/bin/pip install --upgrade pip -q

# Tambahkan psycopg2-binary ke requirements jika PostgreSQL
if [ "$DB_TYPE" = "postgresql" ]; then
    if ! grep -q "psycopg2" requirements.txt 2>/dev/null; then
        echo "psycopg2-binary" >> requirements.txt
    fi
fi

# Bersihkan modul-modul lama untuk menghindari konflik namespace
venv/bin/pip uninstall -y pysnmp-lextudio pysnmp pyasn1 || true
venv/bin/pip install -r requirements.txt -q
success "Dependencies up to date."

# ════════════════════════════════════════════════════════════════════════════
# [4] File .env
# ════════════════════════════════════════════════════════════════════════════
header "[4/7] Konfigurasi .env"
if [ ! -f "$APP_DIR/.env" ]; then
    if [ "$DB_TYPE" = "postgresql" ]; then
        cat << PGENV > "$APP_DIR/.env"
DB_TYPE=postgresql
DATABASE_URL=postgresql://$PG_USER:$PG_PASS@$PG_HOST:$PG_PORT/$PG_NAME
PGENV
        success ".env baru dibuat dengan konfigurasi PostgreSQL."
    else
        mkdir -p "$DATA_DIR"
        cat << SQLITEENV > "$APP_DIR/.env"
DB_TYPE=sqlite
DATABASE_URL=sqlite:///$DATA_DIR/sentinel360.db
SQLITEENV
        success ".env baru dibuat dengan SQLite."
    fi
else
    success ".env sudah ada — tidak diubah."

    # Jika user sebelumnya SQLite dan sekarang pilih PostgreSQL, tambahkan config PG
    if [ "$DB_TYPE" = "postgresql" ] && ! grep -q "^DB_TYPE=postgresql" "$APP_DIR/.env"; then
        warn "Mengubah database di .env yang sudah ada ke PostgreSQL..."
        sed -i 's|^DB_TYPE=.*|DB_TYPE=postgresql|' "$APP_DIR/.env" 2>/dev/null || echo "DB_TYPE=postgresql" >> "$APP_DIR/.env"
        sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql://$PG_USER:$PG_PASS@$PG_HOST:$PG_PORT/$PG_NAME|" "$APP_DIR/.env" 2>/dev/null || \
            echo "DATABASE_URL=postgresql://$PG_USER:$PG_PASS@$PG_HOST:$PG_PORT/$PG_NAME" >> "$APP_DIR/.env"
        success "Konfigurasi PostgreSQL diperbarui di .env."
    fi
fi

# ════════════════════════════════════════════════════════════════════════════
# [5] Direktori data & permission
# ════════════════════════════════════════════════════════════════════════════
header "[5/7] Setup direktori & permission"
mkdir -p "$DATA_DIR"
mkdir -p /var/log/sentinel360
chown -R www-data:www-data "$APP_DIR"
chown -R www-data:www-data "$DATA_DIR"
chmod 750 "$DATA_DIR"
find "$APP_DIR/venv/bin" -type f -exec chmod +x {} \;
success "Direktori & permission siap."

# ════════════════════════════════════════════════════════════════════════════
# [6] Systemd service
# ════════════════════════════════════════════════════════════════════════════
header "[6/7] Install & restart service"
cat << EOF > /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=Sentinel360 Monitoring Server FastAPI
After=network.target

[Service]
User=www-data
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
ReadWritePaths=$APP_DIR $DATA_DIR /var/log/sentinel360

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
sleep 2
systemctl status "$SERVICE_NAME" --no-pager -l

# Catat versi yang baru saja di-deploy
mkdir -p "$DATA_DIR"
echo "$DEPLOYED_VERSION" > "$VERSION_FILE"
# Tambahkan ke history log
echo "$(date '+%Y-%m-%d %H:%M:%S') | $DEPLOYED_VERSION | $(hostname)" >> "$DATA_DIR/.deploy_history"
success "Versi $DEPLOYED_VERSION tercatat di $VERSION_FILE"

# ════════════════════════════════════════════════════════════════════════════
# [7] Nginx
# ════════════════════════════════════════════════════════════════════════════
header "[7/7] Konfigurasi Nginx"
if [ ! -f /etc/nginx/sites-available/sentinel360 ]; then
    cat > /etc/nginx/sites-available/sentinel360 << 'NGINXCONF'
server {
    listen 80;
    server_name _;

    client_max_body_size 20M;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINXCONF
    ln -sf /etc/nginx/sites-available/sentinel360 /etc/nginx/sites-enabled/sentinel360
    [ -f /etc/nginx/sites-enabled/default ] && rm /etc/nginx/sites-enabled/default && \
        info "Site 'default' dinonaktifkan."
    success "Config Nginx baru dibuat."
else
    info "Config Nginx sudah ada, dilewati."
fi
nginx -t && systemctl reload nginx
success "Nginx reloaded."

# ════════════════════════════════════════════════════════════════════════════
# Ringkasan
# ════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
if $IS_UPDATE; then
echo -e "${BOLD}║      ✓  UPDATE SELESAI                   ║${NC}"
else
echo -e "${BOLD}║      ✓  INSTALL SELESAI                  ║${NC}"
fi
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  URL       : ${CYAN}http://$(hostname -I | awk '{print $1}')${NC}"
echo -e "  Versi     : ${CYAN}$DEPLOYED_VERSION${NC}  (sebelumnya: $CURRENT_VERSION)"
if [ "$DB_TYPE" = "postgresql" ]; then
echo -e "  Database  : ${CYAN}PostgreSQL — $PG_USER@$PG_HOST:$PG_PORT/$PG_NAME${NC}"
else
echo -e "  Database  : ${CYAN}SQLite — $DATA_DIR/sentinel360.db${NC}"
fi
echo -e "  Config    : ${CYAN}$APP_DIR/.env${NC}"
echo -e "  Log       : ${CYAN}journalctl -u sentinel360 -f${NC}"
echo -e "  History   : ${CYAN}cat $DATA_DIR/.deploy_history${NC}"
echo -e "  Update    : ${CYAN}sudo bash $APP_DIR/deploy.sh${NC}"
echo ""
