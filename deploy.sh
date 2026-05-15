#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# deploy.sh — Script de despliegue automatizado para CryptoWorld
#
# Uso:
#   chmod +x deploy.sh
#
#   Primera vez en el servidor:
#     ./deploy.sh setup
#
#   Actualizar código (CI/CD manual):
#     ./deploy.sh update
#
#   Solo reiniciar servicios:
#     ./deploy.sh restart
#
#   Ver estado:
#     ./deploy.sh status
#
# Requisitos en el servidor (Ubuntu 22.04):
#   - Docker Engine instalado
#   - docker compose plugin (v2)
#   - Dominio apuntando a la IP del servidor
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOMAIN="${DOMAIN:-cryptoworld.duckdns.org}"

# ── Colores para output ──────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # Sin color

log()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
ok()   { echo -e "${GREEN}[OK]${NC}    $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $1"; }
fail() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Verificar requisitos ─────────────────────────────────────────
check_requirements() {
    log "Verificando requisitos..."
    command -v docker >/dev/null 2>&1 || fail "Docker no está instalado"
    docker compose version >/dev/null 2>&1 || fail "docker compose plugin no está instalado"
    [ -f ".env.production" ] || fail "Falta .env.production — cópialo al servidor primero"
    ok "Requisitos verificados"
}

# ── Primera configuración en el servidor ────────────────────────
setup() {
    log "=== SETUP INICIAL ==="
    check_requirements

    # Leer email para Let's Encrypt desde .env.production
    CERTBOT_EMAIL=$(grep "^EMAIL_HOST_USER=" .env.production | cut -d'=' -f2 | tr -d ' ')
    if [ -z "$CERTBOT_EMAIL" ] || echo "$CERTBOT_EMAIL" | grep -qi "PENDIENTE"; then
        fail "Rellena EMAIL_HOST_USER en .env.production con tu Gmail real (requerido por Let's Encrypt)"
    fi

    # Crear directorios necesarios
    mkdir -p nginx/ssl nginx/certbot/certs

    # Detener contenedores para liberar el puerto 80
    log "Deteniendo contenedores previos (si los hay)..."
    docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true

    # Obtener certificado SSL con certbot standalone vía Docker
    # (no requiere instalar certbot en el host; usa el puerto 80 libre)
    log "Obteniendo certificado SSL para $DOMAIN con Let's Encrypt..."
    docker run --rm \
        -p 80:80 \
        -v "$APP_DIR/nginx/certbot/certs:/etc/letsencrypt" \
        certbot/certbot certonly \
        --standalone \
        --email "$CERTBOT_EMAIL" \
        --agree-tos \
        --no-eff-email \
        -d "$DOMAIN"

    # Copiar certificados al directorio que monta el contenedor nginx
    log "Copiando certificados a nginx/ssl/..."
    cp "$APP_DIR/nginx/certbot/certs/live/$DOMAIN/fullchain.pem" nginx/ssl/
    cp "$APP_DIR/nginx/certbot/certs/live/$DOMAIN/privkey.pem"   nginx/ssl/
    chmod 644 nginx/ssl/fullchain.pem nginx/ssl/privkey.pem

    # Arrancar todos los servicios con los certificados ya en su sitio
    deploy

    # Renovación automática mensual (detiene nginx 10s, renueva, lo rearrancar)
    log "Configurando renovación automática SSL (1er día de cada mes a las 03:00)..."
    RENEW_CMD="docker compose -f $APP_DIR/$COMPOSE_FILE stop frontend && docker run --rm -p 80:80 -v $APP_DIR/nginx/certbot/certs:/etc/letsencrypt certbot/certbot renew --standalone --quiet && cp $APP_DIR/nginx/certbot/certs/live/$DOMAIN/fullchain.pem $APP_DIR/nginx/ssl/ && cp $APP_DIR/nginx/certbot/certs/live/$DOMAIN/privkey.pem $APP_DIR/nginx/ssl/ && docker compose -f $APP_DIR/$COMPOSE_FILE start frontend"
    (crontab -l 2>/dev/null; echo "0 3 1 * * $RENEW_CMD") | crontab -

    ok "=== SETUP COMPLETADO ==="
    ok "Accede a: https://$DOMAIN"
}

# ── Despliegue / actualización ───────────────────────────────────
deploy() {
    log "=== DEPLOY ==="
    check_requirements

    log "Construyendo imágenes..."
    docker compose -f "$COMPOSE_FILE" build --no-cache

    log "Aplicando migraciones de BD..."
    docker compose -f "$COMPOSE_FILE" run --rm backend \
        sh -c "cd src && python manage.py migrate --noinput"

    log "Recargando servicios (zero-downtime)..."
    # Recarga uno a uno para minimizar downtime
    docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

    # Eliminar imágenes antiguas
    docker image prune -f >/dev/null 2>&1 || true

    ok "=== DEPLOY COMPLETADO ==="
    status
}

# ── Actualización rápida (pull + rebuild + up) ───────────────────
update() {
    log "=== ACTUALIZACIÓN ==="
    check_requirements

    log "Descargando últimos cambios de Git..."
    git pull origin "$(git rev-parse --abbrev-ref HEAD)"

    deploy
}

# ── Reiniciar servicios ──────────────────────────────────────────
restart() {
    log "Reiniciando servicios..."
    docker compose -f "$COMPOSE_FILE" restart
    ok "Servicios reiniciados"
    status
}

# ── Estado de los servicios ──────────────────────────────────────
status() {
    echo ""
    log "=== ESTADO DE SERVICIOS ==="
    docker compose -f "$COMPOSE_FILE" ps
    echo ""
    log "=== LOGS RECIENTES (últimas 20 líneas) ==="
    docker compose -f "$COMPOSE_FILE" logs --tail=20
}

# ── Backup de base de datos ──────────────────────────────────────
backup_db() {
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    BACKUP_FILE="backup_${TIMESTAMP}.sql"
    log "Creando backup de BD → $BACKUP_FILE"
    docker compose -f "$COMPOSE_FILE" exec postgres \
        pg_dump -U "${DB_USER:-postgres}" "${DB_NAME:-cryptoworld_db}" > "$BACKUP_FILE"
    ok "Backup guardado en $BACKUP_FILE"
}

# ── Punto de entrada ─────────────────────────────────────────────
case "${1:-help}" in
    setup)   setup ;;
    deploy)  deploy ;;
    update)  update ;;
    restart) restart ;;
    status)  status ;;
    backup)  backup_db ;;
    help|*)
        echo ""
        echo "  CryptoWorld — Script de despliegue"
        echo ""
        echo "  Uso: ./deploy.sh <comando>"
        echo ""
        echo "  Comandos:"
        echo "    setup    Primera configuración en el servidor (SSL + arranque)"
        echo "    deploy   Construir y desplegar (sin pull de git)"
        echo "    update   Pull de git + deploy completo"
        echo "    restart  Reiniciar todos los servicios"
        echo "    status   Ver estado y logs de servicios"
        echo "    backup   Crear backup de la base de datos"
        echo ""
        ;;
esac
