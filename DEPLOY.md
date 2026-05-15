# CryptoWorld — Guía de Despliegue en Producción

## Arquitectura final

```
Internet
    │  (puerto 443 HTTPS)
    ▼
┌─────────────────────────────────────────┐
│  Nginx (frontend container)             │
│  ├── /*         → React SPA             │
│  ├── /api/*     → backend:8000 (proxy)  │
│  └── /admin/*   → backend:8000 (proxy)  │
└─────────────────────────────────────────┘
    │ red Docker interna
    ▼
┌──────────────────────────────────────────────┐
│  Django + Gunicorn (backend container :8000) │
└──────────────────────────────────────────────┘
    │
    ├── PostgreSQL 16 (postgres container)
    ├── Redis 7 (redis container)
    ├── Celery Worker (alertas de precio asíncronas)
    └── Celery Beat (sync periódico de mercado)
```

Todo el tráfico entra por **un solo dominio y un solo puerto (443)**. El navegador nunca necesita saber dónde están Django o las APIs.

---

## Opción recomendada: VPS con Docker Compose

### Proveedores de VPS recomendados

| Proveedor | Plan mínimo | Precio | RAM/CPU | Adecuado para TFG |
|---|---|---|---|---|
| **Hetzner Cloud** | CX22 | ~€4/mes | 2GB / 2 vCPU | ✅ Excelente |
| **DigitalOcean** | Basic Droplet | $6/mes | 1GB / 1 vCPU | ✅ Muy bueno |
| **Contabo** | VPS S | ~€5/mes | 4GB / 4 vCPU | ✅ Buena relación calidad/precio |
| **OVH** | VPS Starter | ~€4/mes | 2GB / 1 vCPU | ✅ |

**Requisito mínimo:** 2GB RAM (Django + Celery + PostgreSQL + Redis juntos necesitan ~1.5GB)

### Dominio

- **Gratuito:** [FreeDNS](https://freedns.afraid.org/) — subdominio gratuito (ej: `cryptoworld.mooo.com`)
- **Barato:** Namecheap / Cloudflare (~$1-10/año para `.com`, `.dev`, etc.)
- **Para TFG:** Un subdominio gratuito es suficiente

---

## Paso a paso: Despliegue desde cero

### Paso 1 — Provisionar el servidor

En el panel de tu proveedor (ej. Hetzner), crea un servidor con:
- **OS:** Ubuntu 22.04 LTS
- **RAM:** 2GB mínimo
- **Región:** la más cercana a España (Falkenstein/Helsinki)

Conectarte por SSH:
```bash
ssh root@IP_DEL_SERVIDOR
```

### Paso 2 — Instalar Docker en el servidor

```bash
# Actualizar paquetes
apt-get update && apt-get upgrade -y

# Instalar Docker (script oficial)
curl -fsSL https://get.docker.com | sh

# Verificar instalación
docker --version
docker compose version
```

### Paso 3 — Subir el proyecto al servidor

**Opción A — Git (recomendada):**
```bash
# En el servidor
git clone https://github.com/tu-usuario/CryptoWorld.git
cd CryptoWorld
```

**Opción B — SCP (si no tienes repositorio público):**
```bash
# En tu máquina local (PowerShell)
scp -r "C:\ruta\al\proyecto\CryptoWorld" root@IP_SERVIDOR:/root/
```

### Paso 4 — Configurar variables de entorno

```bash
# En el servidor, dentro de /root/CryptoWorld/
nano .env.production
```

Rellena TODOS los valores en `.env.production`:
- `DJANGO_SECRET_KEY` → genera con: `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`
- `DB_PASSWORD` → contraseña fuerte aleatoria
- `DJANGO_ALLOWED_HOSTS` → tu dominio real
- `CORS_ALLOWED_ORIGINS` → `https://tudominio.com`
- `FRONTEND_URL` → `https://tudominio.com`
- `EMAIL_*` → credenciales SMTP reales

### Paso 5 — Configurar el dominio

En el panel DNS de tu dominio (ej. Cloudflare), añade:
```
Tipo A → tudominio.com      → IP_DEL_SERVIDOR
Tipo A → www.tudominio.com  → IP_DEL_SERVIDOR
```

Espera 5-10 minutos a que propaguen.

### Paso 6 — Ajustar nginx.prod.conf con tu dominio

```bash
# Reemplaza "tudominio.com" con tu dominio real
sed -i 's/tudominio.com/midominio.com/g' nginx/nginx.prod.conf
```

### Paso 7 — Desplegar

```bash
chmod +x deploy.sh

# Primera vez (obtiene SSL + arranca todo)
DOMAIN=tudominio.com ./deploy.sh setup
```

El script automáticamente:
1. Obtiene certificado SSL de Let's Encrypt
2. Construye todas las imágenes Docker
3. Aplica migraciones de BD
4. Arranca todos los servicios

### Paso 8 — Verificar

```bash
./deploy.sh status
```

Abre en el navegador: **`https://tudominio.com`** ✅

---

## Actualizaciones posteriores

Cuando hayas hecho cambios en el código:

```bash
# En el servidor
cd /root/CryptoWorld
./deploy.sh update   # git pull + rebuild + restart
```

---

## Comandos útiles de mantenimiento

```bash
# Ver logs en tiempo real
docker compose -f docker-compose.prod.yml logs -f

# Ver logs solo del backend
docker compose -f docker-compose.prod.yml logs -f backend

# Acceder a la BD
docker compose -f docker-compose.prod.yml exec postgres psql -U cryptoworld_user cryptoworld_db

# Crear superusuario Django
docker compose -f docker-compose.prod.yml exec backend \
  sh -c "cd src && python manage.py createsuperuser"

# Backup de la BD
./deploy.sh backup

# Reiniciar un servicio específico
docker compose -f docker-compose.prod.yml restart backend

# Parar todo
docker compose -f docker-compose.prod.yml down
```

---

## Alternativa sin servidor propio: Railway

Si no quieres gestionar un VPS, Railway es la opción más sencilla:

1. Crea cuenta en [railway.app](https://railway.app)
2. "New Project" → "Deploy from GitHub repo"
3. Railway detecta el `docker-compose.yml` automáticamente
4. Configura las variables de entorno en el panel web
5. Railway asigna una URL HTTPS automática (`*.up.railway.app`)

**Limitación:** El plan gratuito tiene 500 horas/mes (~20 días). Para uso continuo ~$5/mes.

---

## Seguridad en producción: checklist

- [ ] `DJANGO_DEBUG=False` en `.env.production`
- [ ] `DJANGO_SECRET_KEY` único y secreto (no el de desarrollo)
- [ ] Contraseña de BD fuerte
- [ ] `.env.production` en `.gitignore` (nunca en Git)
- [ ] HTTPS activo (Let's Encrypt)
- [ ] Puertos de BD (5432) y Redis (6379) NO expuestos al host
- [ ] Rate limiting en nginx para endpoints de auth
- [ ] Headers de seguridad (`HSTS`, `X-Frame-Options`, etc.)
- [ ] Backups automáticos de BD
- [ ] `collectstatic` ejecutado (para Django Admin y archivos estáticos)

---

## Estructura de archivos de producción

```
CryptoWorld/
├── docker-compose.prod.yml    ← Compose de producción (Gunicorn, sin dev tools)
├── .env.production            ← Variables secretas (NO subir a Git)
├── deploy.sh                  ← Script de despliegue automatizado
├── nginx/
│   ├── nginx.prod.conf        ← Nginx: HTTPS + proxy a Django + SPA
│   ├── ssl/                   ← Certificados Let's Encrypt (auto-generados)
│   └── certbot/www/           ← Webroot para renovación SSL
├── backend/                   ← Código fuente backend
└── frontend/                  ← Código fuente frontend
```
