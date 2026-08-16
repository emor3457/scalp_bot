#!/usr/bin/env bash
# =============================================================================
# deploy.sh — VPS'te tek komutla guncelleme
# -----------------------------------------------------------------------------
# Yaptiklari:
#   1. Git: origin/main'den kod cekilir (ff-only — conflict'te durur)
#   2. .env kontrolu: yoksa durur, kritik anahtarlar bossa uyarir
#   3. Docker imaji derlenir (requirements degisiklikleri icin)
#   4. Servis yeniden baslatilir (--force-recreate ile env degisiklikleri)
#   5. Saglik kontrolu: http://127.0.0.1:8000/ "status":"running" yaniti bekler
#
# Kullanim (VPS'te, proje kokunde):
#   ./deploy.sh
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

# docker compose (v2) oncelikli; yoksa docker-compose (v1)
if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
else
    err "Docker Compose bulunamadi. Kurulum: https://docs.docker.com/compose/install/"
    exit 1
fi

# ---------------------------------------------------------------------------
info "Adim 1/5: Git guncellemesi"
# ---------------------------------------------------------------------------
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    err "Git deposu bulunamadi: $PROJECT_DIR"
    exit 1
fi

if ! git diff --quiet; then
    warn "Lokal degisiklikler var. 'git stash' onerilir; pull conflict olursa script duracak."
fi

git pull --ff-only origin main

# ---------------------------------------------------------------------------
info "Adim 2/5: .env kontrolu"
# ---------------------------------------------------------------------------
if [[ ! -f .env ]]; then
    err ".env bulunamadi. 'cp .env.example .env' ile olusturup doldurun, sonra tekrar calistirin."
    exit 1
fi

# Kritik anahtarlar — bos/tanimisiz ise uygulama calisir ama ilgili ozellik eksik olur
for key in DASHBOARD_AUTH_TOKEN WEBHOOK_SECRET_TOKEN TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID; do
    if ! grep -qE "^${key}=.+" .env 2>/dev/null; then
        warn "${key} .env icinde bos/tanimisiz — ilgili ozellik (auth/bildirim) eksik olur."
    fi
done

# ---------------------------------------------------------------------------
info "Adim 3/5: Docker imaji derleniyor"
# ---------------------------------------------------------------------------
$DC build

# ---------------------------------------------------------------------------
info "Adim 4/5: Servis yeniden baslatiliyor"
# ---------------------------------------------------------------------------
$DC up -d --force-recreate

# ---------------------------------------------------------------------------
info "Adim 5/5: Saglik kontrolu"
# ---------------------------------------------------------------------------
container="$($DC ps -q borsa_bot 2>/dev/null | head -n1)"
if [[ -z "$container" ]]; then
    err "Konteyner bulunamadi. Son loglar:"
    $DC logs --tail=50 || true
    exit 1
fi

healthy=0
for _ in $(seq 1 30); do   # max ~60 sn
    if curl -fsS --max-time 3 http://127.0.0.1:8000/ 2>/dev/null | grep -q '"status": "running"'; then
        healthy=1
        break
    fi
    sleep 2
done

if [[ "$healthy" != "1" ]]; then
    err "Saglik kontrolu basarisiz (60 sn boyunca yanit alinamadi). Son loglar:"
    $DC logs --tail=50 || true
    err "Geri almak icin: git reset --hard HEAD@{1} && $DC up -d --build --force-recreate"
    exit 1
fi

info "Tamam. Bot ayakta: $(curl -fsS http://127.0.0.1:8000/ 2>/dev/null | tr -d '\n')"
info "Dashboard: http://<VPS_IP>:8000/dashboard (DASHBOARD_AUTH_TOKEN ile korumali)"
