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

Railway permite desplegar backend + Celery como **3 servicios separados** en el mismo proyecto, compartiendo la misma BD PostgreSQL y Redis.

### Arquitectura en Railway

```
Proyecto Railway "CryptoWorld"
├── cryptoworld-web     ← Django + Gunicorn  (este repo/backend/)
├── cryptoworld-worker  ← Celery Worker      (este repo/backend/)
├── cryptoworld-beat    ← Celery Beat        (este repo/backend/)
├── PostgreSQL          ← Plugin de Railway
└── Redis               ← Plugin de Railway
```

### Paso 1 — Crear el proyecto base

1. Crea cuenta en [railway.app](https://railway.app)
2. "New Project" → "Empty Project"
3. Añade PostgreSQL: "Add Service" → "Database" → "PostgreSQL"
4. Añade Redis: "Add Service" → "Database" → "Redis"

### Paso 2 — Servicio Web (Django)

1. "Add Service" → "GitHub Repo" → selecciona el repo `CryptoWorld`
2. En el servicio creado → "Settings":
   - **Root Directory:** `backend`
   - **Start Command:** *(dejar vacío — usa `railway.json` automáticamente)*
3. Railway detecta `backend/railway.json` y ejecuta migrate + gunicorn

### Paso 3 — Servicio Celery Worker

1. "Add Service" → "GitHub Repo" → mismo repo `CryptoWorld`
2. En el servicio → "Settings":
   - **Root Directory:** `backend`
   - **Start Command:**
     ```
     cd src && celery -A config worker --loglevel=info --pool=solo
     ```
   - Rename el servicio a `cryptoworld-worker`
3. En "Variables" → copia **todas** las variables del servicio web (ver Paso 5)

### Paso 4 — Servicio Celery Beat

1. "Add Service" → "GitHub Repo" → mismo repo `CryptoWorld`
2. En el servicio → "Settings":
   - **Root Directory:** `backend`
   - **Start Command:**
     ```
     cd src && celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
     ```
   - Rename el servicio a `cryptoworld-beat`
3. En "Variables" → copia **todas** las variables del servicio web (ver Paso 5)

### Paso 5 — Variables de entorno (los 3 servicios)

Configura estas variables en **cada uno de los 3 servicios**. Railway inyecta `DATABASE_URL` y `REDIS_URL` automáticamente al vincularlos con los plugins.

| Variable | Valor |
|---|---|
| `DATABASE_URL` | *Auto — vincular al plugin PostgreSQL* |
| `REDIS_URL` | *Auto — vincular al plugin Redis* |
| `DJANGO_SECRET_KEY` | Clave secreta larga y aleatoria |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `*.up.railway.app,tudominio.com` |
| `CORS_ALLOWED_ORIGINS` | URL del frontend (Vercel, etc.) |
| `FRONTEND_URL` | URL del frontend — **se usa para construir los links de los emails** |
| `SENDGRID_API_KEY` | API key de SendGrid (opción A de email) |
| `DEFAULT_FROM_EMAIL` | `CryptoWorld <remitente-verificado@dominio.com>` |
| `EMAIL_HOST` | Servidor SMTP, ej. `smtp.gmail.com` (opción B, si no usas SendGrid) |
| `EMAIL_HOST_USER` | Email de envío (solo opción B) |
| `EMAIL_HOST_PASSWORD` | Contraseña de aplicación SMTP (solo opción B) |
| `EMAIL_PORT` | `587` (solo opción B) |
| `COINGECKO_API_KEY` | API key de CoinGecko (opcional) |

> **Email:** si `SENDGRID_API_KEY` está definida se usa SendGrid; si no, y
> `EMAIL_HOST` está definida, se usa SMTP; si ninguna existe, los emails solo
> se imprimen en los logs (modo desarrollo) y **nunca llegan al usuario**.

Para vincular `DATABASE_URL` al plugin PostgreSQL:
- En el servicio → "Variables" → "Add Reference" → selecciona el plugin PostgreSQL → variable `DATABASE_URL`
- Repite para `REDIS_URL` con el plugin Redis

### Paso 6 — Desplegar y verificar

1. En el servicio web, haz click en "Deploy"
2. Luego en worker → "Deploy"
3. Luego en beat → "Deploy"
4. Verifica los logs de cada servicio:
   - **Web:** debe mostrar `Listening at: http://0.0.0.0:PORT`
   - **Worker:** debe mostrar `celery@... ready.`
   - **Beat:** debe mostrar `beat: Starting...`

### Paso 7 — Dominio personalizado (opcional)

En el servicio web → "Settings" → "Custom Domain" → añade tu dominio.

### Actualizaciones posteriores

Railway hace **redeploy automático** en cada push a `main`. Los 3 servicios se actualizan solos.

**Precio:** ~$5-10/mes con el plan Hobby (3 servicios + BD + Redis).

### Diagnóstico: los emails (verificación, reset) no llegan

El envío de email pasa por dos piezas: la **cola Celery** (el endpoint encola
la tarea) y el **backend de email** (SendGrid o SMTP). Revisa en este orden:

1. **¿Está definida `SENDGRID_API_KEY` (o `EMAIL_HOST`) en el servicio web Y en el worker?**
   Sin ninguna de las dos, Django usa el backend de consola: el email "se envía"
   pero solo aparece impreso en los logs. Es la causa más común.

2. **¿Existe el servicio `cryptoworld-worker` y está en verde?**
   El envío es asíncrono vía Celery. Desde la versión actual, si el broker
   Redis no está disponible el backend hace **fallback síncrono** (el email
   sale igualmente desde el proceso web y queda un warning
   `Broker Celery no disponible` en los logs), pero lo correcto en Railway
   es tener el worker desplegado con las **mismas variables** que el web.

3. **¿`REDIS_URL` está vinculada en los 3 servicios?**
   Sin ella, las tareas se encolan en un Redis inexistente (localhost).

4. **¿El remitente está verificado en SendGrid?**
   `DEFAULT_FROM_EMAIL` debe ser un Single Sender o dominio verificado en
   SendGrid → Settings → Sender Authentication. Si no, SendGrid devuelve 403
   (visible en los logs del worker como error de la tarea
   `send_verification_email`).

5. **¿`FRONTEND_URL` apunta al dominio real de Vercel?**
   Los links de los emails se construyen con esta variable. Si apunta a
   `http://localhost:5173`, el email llega pero el enlace no funciona.

6. **Logs útiles:**
   - Servicio web: busca `Broker Celery no disponible` (fallback activado).
   - Worker: busca `send_verification_email` (éxito o el error de SendGrid/SMTP).

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
