#!/usr/bin/env bash
# =============================================================================
# deploy.sh — VPS Tek Adımda Güncelleme ve Dağıtım Scripti
# =============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[deploy][UYARI]${NC} $*"; }
err()  { echo -e "${RED}[deploy][HATA]${NC} $*" >&2; }

# Docker Compose komutunu belirle (v2 veya v1)
if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
else
    err "Docker Compose bulunamadı. Lütfen Docker Compose kurun."
    exit 1
fi

info "1/4: Git'ten güncel kodlar çekiliyor..."
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    err "Git deposu bulunamadı: $PROJECT_DIR"
    exit 1
fi

git pull origin main

info "2/4: .env dosyası kontrol ediliyor..."
if [[ ! -f .env ]]; then
    warn ".env bulunamadı! .env.example dosyasından oluşturuluyor..."
    cp .env.example .env
    warn "Lütfen .env dosyanızı API anahtarlarıyla düzenlemeyi unutmayın."
fi

# Kritik anahtarları kontrol et
for key in WEBHOOK_SECRET_TOKEN TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID; do
    if ! grep -qE "^${key}=.+" .env 2>/dev/null; then
        warn "${key} .env içinde boş veya tanımlanmamış."
    fi
done

info "3/4: Docker imajı derleniyor ve servis yeniden başlatılıyor..."
$DC build

# Eski konteyner kilitlenmelerini önlemek için temizleyip yeniden başlatıyoruz
docker rm -f borsa_scalp_bot 2>/dev/null || true
$DC up -d --force-recreate

info "4/4: Sağlık kontrolü (Healthcheck) yapılıyor..."
healthy=0
for i in $(seq 1 20); do
    if curl -fsS --max-time 3 http://127.0.0.1:8000/ > /dev/null 2>&1; then
        healthy=1
        break
    fi
    sleep 2
done

if [[ "$healthy" -eq 1 ]]; then
    info "✅ Bot başarıyla ayağa kalktı ve çalışıyor!"
    info "Dashboard: http://<VPS_IP>:8000/dashboard"
else
    warn "Servis henüz yanıt vermedi. Logları kontrol edin: $DC logs --tail=50"
fi
