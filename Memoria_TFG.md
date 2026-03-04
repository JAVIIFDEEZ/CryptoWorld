# Memoria del Trabajo de Fin de Grado
## CryptoWorld — Sistema de Análisis de Criptomonedas

**Autor:** Javier  
**Titulación:** 4º Ingeniería Informática  
**Universidad:** Universidad de Castilla-La Mancha  

---

## Índice

1. [Descripción del Proyecto](#1-descripción-del-proyecto)
2. [Tecnologías Utilizadas](#2-tecnologías-utilizadas)
3. [Arquitectura del Sistema](#3-arquitectura-del-sistema)
4. [Cronología del Desarrollo](#4-cronología-del-desarrollo)
5. [Estructura del Proyecto](#5-estructura-del-proyecto)
6. [Decisiones de Diseño Justificadas](#6-decisiones-de-diseño-justificadas)
7. [Problemas Encontrados y Soluciones](#7-problemas-encontrados-y-soluciones)
8. [Estado Actual del Sistema](#8-estado-actual-del-sistema)
9. [Próximos Pasos](#9-próximos-pasos)

---

## 1. Descripción del Proyecto

**CryptoWorld** es una plataforma web de análisis de criptomonedas con las siguientes funcionalidades previstas:

- Visualización de datos de mercado en tiempo real (integración con CoinGecko API)
- Análisis técnico: RSI, MACD, Bandas de Bollinger, Medias Móviles
- Gestión de portfolio personal
- Sistema de alertas configurables
- Historial de ejecuciones de análisis

El sistema está construido con una arquitectura de microservicios dockerizada donde el frontend (SPA React) y el backend (API REST Django) se comunican mediante JWT.

---

## 2. Tecnologías Utilizadas

### Backend
| Tecnología | Versión | Rol |
|---|---|---|
| Python | 3.11 | Lenguaje del servidor |
| Django | 5.0.6 | Framework web |
| Django REST Framework | 3.15.2 | Serialización y endpoints API |
| SimpleJWT | 5.3.1 | Autenticación JWT (access 60min, refresh 7 días) |
| rest_framework_simplejwt.token_blacklist | 5.3.1 | Blacklist de refresh tokens para logout seguro |
| django-cors-headers | 4.4.0 | CORS para comunicación con frontend |
| psycopg2-binary | 2.9.9 | Driver PostgreSQL |
| pyotp | 2.9.0 | Generación y verificación TOTP (RFC 6238 — Google Authenticator) |
| qrcode | 7.4.2 | Generación de QR codes en PNG/base64 para setup 2FA |
| Pillow | 10.4.0 | Dependencia de qrcode para renderizado PNG |
| python-dotenv | 1.0.1 | Carga de variables de entorno |
| gunicorn | 22.0.0 | Servidor WSGI para producción |
| pytest + pytest-django | 8.2.2 / 4.8.0 | Testing |

### Frontend
| Tecnología | Versión | Rol |
|---|---|---|
| React | 18.3.1 | Framework UI |
| TypeScript | 5.5.3 | Tipado estático |
| Vite | 5.3.4 | Bundler y dev server |
| react-router-dom | 6.24.0 | Enrutamiento SPA |
| Axios | 1.7.2 | Cliente HTTP con interceptores JWT |
| TailwindCSS | 3.4.6 | Estilos utility-first |

### Infraestructura
| Tecnología | Versión | Rol |
|---|---|---|
| Docker | - | Contenedorización |
| Docker Compose v2 | - | Orquestación multi-contenedor |
| PostgreSQL | 16-alpine | Base de datos relacional |
| nginx | alpine | Servidor estático frontend (producción) |

---

## 3. Arquitectura del Sistema

### Patrón: Clean Architecture (Arquitectura Limpia)

Se adoptó Clean Architecture de Robert C. Martin como patrón arquitectónico principal. Este patrón organiza el código en capas concéntricas donde **las dependencias solo apuntan hacia el interior**.

```
┌────────────────────────────────────────────┐
│           INTERFACES (API REST)            │  ← Capa más externa. Conoce HTTP.
│  views.py  serializers.py  urls.py         │
├────────────────────────────────────────────┤
│           INFRAESTRUCTURA                  │  ← Adaptadores externos.
│  models.py  repositories_impl.py           │     PostgreSQL, CoinGecko API
├────────────────────────────────────────────┤
│           APLICACIÓN                       │  ← Casos de uso. Orquesta el dominio.
│  RegisterUserUseCase  GetAssetsUseCase      │     No conoce HTTP ni DB.
│  RunAnalysisUseCase   DTOs                 │
├────────────────────────────────────────────┤
│           DOMINIO (núcleo)                 │  ← Reglas de negocio puras.
│  Entidades  Repositorios (interfaces)       │     Sin dependencias externas.
│  Servicios de dominio  Value Objects       │
└────────────────────────────────────────────┘
```

### Regla de dependencia
- El **dominio** no importa nada de las capas externas.
- La **aplicación** solo importa del dominio.
- La **infraestructura** implementa las interfaces del dominio.
- Las **interfaces (API)** llaman a los casos de uso de la aplicación.

### Justificación de la elección
Clean Architecture facilita:
1. **Testabilidad**: el dominio se puede probar sin base de datos ni HTTP.
2. **Intercambiabilidad**: cambiar PostgreSQL por MongoDB solo modifica `repositories_impl.py`.
3. **Mantenibilidad**: cada capa tiene una única responsabilidad.

### Comunicación entre componentes

```
Browser (localhost:5173)
       │  HTTPS/JSON
       ▼
  nginx (frontend container)
       │  proxy /api/* → backend:8000
       │
       ▼
  Django + DRF (backend container, puerto 8000)
       │  psycopg2
       ▼
  PostgreSQL (postgres container, puerto 5432)
```

---

## 4. Cronología del Desarrollo

### Fase 1 — Definición y Scaffolding inicial (Febrero 2026)

**Objetivo:** Generar la estructura completa del proyecto desde cero.

**Trabajo realizado:**
- Definición de requisitos funcionales del TFG con arquitectura Clean Architecture
- Creación de la estructura de carpetas del backend siguiendo las 4 capas:
  - `domain/` → entidades, repositorios (interfaces), servicios, value objects
  - `application/` → casos de uso, DTOs
  - `infrastructure/` → modelos ORM, implementaciones de repositorios
  - `interfaces/` → vistas API, serializers, URLs
- Creación de la estructura del frontend React + TypeScript + Vite

**Archivos creados:**
```
backend/
├── src/
│   ├── config/
│   │   ├── settings.py      ← Configuración Django: BD, JWT, CORS, apps
│   │   ├── urls.py          ← Enrutamiento raíz
│   │   └── wsgi.py          ← Entry point WSGI
│   ├── core/
│   │   ├── domain/
│   │   │   ├── entities/    ← UserEntity, CryptoAssetEntity, etc.
│   │   │   ├── repositories/← IUserRepository, ICryptoAssetRepository (interfaces)
│   │   │   ├── services/    ← UserDomainService
│   │   │   └── value_objects/← Email, CryptoSymbol
│   │   ├── application/
│   │   │   ├── use_cases/   ← RegisterUserUseCase, GetAssetsUseCase, RunAnalysisUseCase
│   │   │   └── dto/         ← auth_dto.py, asset_dto.py
│   │   ├── infrastructure/
│   │   │   ├── persistence/
│   │   │   │   ├── models.py          ← Modelos ORM Django (User, CryptoAsset, etc.)
│   │   │   │   └── repositories_impl.py← DjangoUserRepository, DjangoCryptoAssetRepository
│   │   │   └── external_apis/         ← (pendiente) Integración CoinGecko
│   │   └── interfaces/
│   │       └── api/
│   │           ├── views.py       ← 5 endpoints HTTP
│   │           ├── serializers.py ← Serialización DRF
│   │           └── urls.py        ← Rutas /api/*
│   └── manage.py
├── requirements.txt
├── Dockerfile
├── pytest.ini
└── tests/
    ├── conftest.py
    ├── unit/test_domain_entities.py
    └── integration/test_api_endpoints.py
frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── routes.tsx
│   ├── index.css
│   ├── vite-env.d.ts
│   ├── hooks/
│   │   └── useAuth.ts       ← AuthContext + AuthProvider + useAuth hook
│   ├── services/
│   │   ├── api.ts           ← Axios centralizado con interceptores JWT
│   │   ├── authService.ts
│   │   └── analysisService.ts
│   ├── components/
│   │   ├── Navbar.tsx
│   │   └── ProtectedRoute.tsx
│   └── pages/
│       ├── LoginPage.tsx
│       ├── DashboardPage.tsx
│       └── AssetDetailPage.tsx
├── Dockerfile               ← Multi-stage: build Vite → nginx
├── nginx.conf
├── package.json
├── vite.config.ts
└── tailwind.config.js
```

**Archivos raíz:**
- `docker-compose.yml` → Orquesta 3 servicios: postgres, backend, frontend
- `.env.example` → Plantilla de variables de entorno
- `.gitignore` → Exclusiones Git

---

### Fase 2 — Corrección de errores Docker (Febrero–Marzo 2026)

Durante el proceso de `docker compose up --build` se identificaron y corrigieron los siguientes errores:

#### Error 1: Docker Desktop no iniciado
- **Síntoma:** `error during connect: pipe error`
- **Causa:** Docker Desktop no estaba en ejecución
- **Solución:** Iniciar Docker Desktop manualmente

#### Error 2: Campo `version` obsoleto en docker-compose.yml
- **Síntoma:** Warning `version is obsolete`
- **Causa:** Docker Compose v2 ya no requiere el campo `version: "3.9"`
- **Solución:** Eliminar la línea `version: "3.9"` de `docker-compose.yml`

#### Error 3: `npm ci` falla por ausencia de package-lock.json
- **Síntoma:** `npm ci can only install packages when your package.json and package-lock.json are in sync`
- **Causa:** Solo existía `package.json`, no `package-lock.json`
- **Solución:** Cambiar `npm ci` por `npm install` en `frontend/Dockerfile`

#### Error 4: `pip install` con timeout por red lenta
- **Síntoma:** Descarga a 19.8 kB/s, timeout de conexión
- **Causa:** Red lenta durante la descarga de paquetes Python
- **Solución:** Añadir flags `--timeout=300 --retries=5` al pip install en `backend/Dockerfile`

#### Error 5: Error TypeScript en useAuth.ts — JSX en archivo .ts
- **Síntoma:** `TS1005: '>' expected` en línea 101 de `useAuth.ts`
- **Causa:** Se usaba sintaxis JSX (`<AuthContext.Provider>`) en un archivo `.ts` (sin extensión `.tsx`)
- **Solución:** Reemplazar JSX por `React.createElement()` en `useAuth.ts`

#### Error 6: TypeScript no reconoce `import.meta.env`
- **Síntoma:** `TS2339: Property 'env' does not exist on type 'ImportMeta'`
- **Causa:** Faltaba el archivo de declaraciones de tipos de Vite
- **Solución:** Crear `frontend/src/vite-env.d.ts` con:
  ```typescript
  /// <reference types="vite/client" />
  interface ImportMetaEnv { readonly VITE_API_URL: string }
  interface ImportMeta { readonly env: ImportMetaEnv }
  ```

**Resultado de Fase 2:** `docker compose up --build` finaliza con éxito. Las tres imágenes Docker se construyen correctamente.

---

### Fase 3 — Corrección del loop de reinicio del backend (Marzo 2026)

#### Error 7: Backend en loop de reinicio — `AUTH_USER_MODEL refers to model 'core.User' that has not been installed`

- **Síntoma:** El contenedor `cryptoworld_backend` reiniciaba indefinidamente. Al ejecutar `docker compose exec backend python src/manage.py migrate` respondía: `Container is restarting, wait until the container is running`

- **Diagnóstico:** Log del contenedor mostraba:
  ```
  ImproperlyConfigured: AUTH_USER_MODEL refers to model 'core.User' that has not been installed
  LookupError: App 'core' doesn't have a 'User' model.
  ```

- **Causa raíz:** Django descubre los modelos de una app cargando automáticamente el módulo `<app_label>.models`. Los modelos ORM del proyecto estaban en `core/infrastructure/persistence/models.py`, pero no existía `core/models.py`. Al no encontrar el modelo `User` bajo la app `core`, Django lanzaba `ImproperlyConfigured` en el arranque.

- **Solución:** Crear `backend/src/core/models.py` como adaptador de importación:
  ```python
  from core.infrastructure.persistence.models import (
      UserManager, User, CryptoAsset,
      MarketDataSnapshot, AnalysisExecution,
  )
  ```
  Este archivo no contiene lógica, solo reexporta los modelos para que el sistema de apps de Django los registre bajo la etiqueta `core`.

- **Resultado:** Docker levanta completamente. Los tres contenedores (postgres, backend, frontend) quedan en estado `running`.

#### Error 8: `relation "users" does not exist` — Falta directorio migrations

- **Síntoma:** El backend levantaba (el error del `core/models.py` ya estaba resuelto), pero seguía en loop. El nuevo error en logs era:
  ```
  django.db.utils.ProgrammingError: relation "users" does not exist
  ```

- **Causa raíz:** La app `core` nunca había tenido ejecutado `makemigrations`, por lo que el directorio `core/migrations/` no existía. Django intentaba ejecutar `migrate` en el arranque (según el `command` del docker-compose.yml), fallaba porque no había archivos de migración, el proceso salía con código 1 y Docker reiniciaba el contenedor.

- **Solución:** Generar las migraciones con un contenedor one-off (sin interrumpir los otros servicios). El volumen montado `./backend/src:/app/src` hace que los archivos se creen directamente en el host:
  ```powershell
  docker compose run --rm backend python src/manage.py makemigrations core
  ```
  Esto creó `backend/src/core/migrations/0001_initial.py` con las 4 tablas del modelo.

- **Resultado:** Al reiniciar automáticamente, el backend detectó las migraciones, las aplicó a PostgreSQL (`core.0001_initial... OK`) y arrancó el servidor Django correctamente.

---

### Fase 4 — Sistema de Autenticación Completo (Marzo 2026)

**Objetivo:** Implementar el sistema de autenticación completo antes de la integración con APIs externas. Funcionalidades: logout seguro, verificación de email, recuperación de contraseña, cambio de contraseña y autenticación de doble factor (2FA/TOTP).

#### 4.1 Diseño del sistema de autenticación

Se optó por un enfoque de **seguridad por capas** siguiendo los mismos principios de Clean Architecture:

- **Logout seguro:** blacklist del `refresh_token` mediante `rest_framework_simplejwt.token_blacklist`, invalidando el token en servidor en lugar de depender solo del lado cliente.
- **Verificación de email:** tokens firmados con HMAC usando `django.contrib.auth.tokens.default_token_generator`. El token incluye el hash de la contraseña actual del usuario en su firma, lo que lo invalida automáticamente si la contraseña cambia.
- **Recuperación de contraseña:** mismo mecanismo de token HMAC. Por seguridad, el endpoint **no revela** si el email existe en el sistema (respuesta idéntica en ambos casos), evitando ataques de enumeración de usuarios.
- **2FA TOTP:** implementado según RFC 6238 usando `pyotp`. Compatible con Google Authenticator, Authy y cualquier app TOTP estándar.
- **Flujo 2FA en dos pasos:** para no romper el flujo de login tradicional, se diseñó un token JWT especial de corta duración (`type=pre_2fa`, 5 minutos) que actúa como "prueba de contraseña válida" sin otorgar acceso completo:

```
POST /api/auth/login/ (email + password válidos, 2FA activo)
  → { "requires_2fa": true, "pre_auth_token": "eyJ..." }
                                       ↓ (5 min para completar)
POST /api/auth/2fa/login/ (pre_auth_token + código TOTP)
  → { "access_token": "...", "refresh_token": "..." }
```

#### 4.2 Cambios en el modelo de usuario

Se añadieron tres campos al modelo `User` en `infrastructure/persistence/models.py`:

```python
is_email_verified = models.BooleanField(default=False)
totp_secret       = models.CharField(max_length=64, null=True, blank=True)
is_2fa_enabled    = models.BooleanField(default=False)
```

Y se propagaron a la entidad de dominio `UserEntity`:
```python
is_email_verified: bool = False
totp_secret: Optional[str] = None
is_2fa_enabled: bool = False
```

Migración generada: `0002_user_auth_fields.py`.

También se añadieron métodos de conveniencia al repositorio `DjangoUserRepository`:
- `set_email_verified(user_id)` — actualiza solo el campo `is_email_verified`
- `set_password(user_id, raw_password)` — hashea y guarda nueva contraseña
- `set_totp_secret(user_id, secret)` — guarda/borra el secreto TOTP
- `set_2fa_enabled(user_id, enabled)` — activa/desactiva 2FA
- `get_model_by_id(user_id)` — devuelve el modelo ORM directamente cuando es necesario

#### 4.3 Casos de uso creados

| Archivo | Clase | Responsabilidad |
|---|---|---|
| `logout.py` | `LogoutUseCase` | Blacklist del refresh_token vía SimpleJWT |
| `send_verification_email.py` | `SendVerificationEmailUseCase` | Genera token HMAC + envía email de verificación |
| `verify_email.py` | `VerifyEmailUseCase` | Valida token del link y marca `is_email_verified=True` |
| `request_password_reset.py` | `RequestPasswordResetUseCase` | Genera token HMAC + envía email de recuperación |
| `confirm_password_reset.py` | `ConfirmPasswordResetUseCase` | Valida token + aplica nueva contraseña |
| `change_password.py` | `ChangePasswordUseCase` | Verifica contraseña actual + cambia a la nueva |
| `setup_2fa.py` | `Setup2FAUseCase` | Genera secreto TOTP + QR base64 para el cliente |
| `enable_2fa.py` | `Enable2FAUseCase` | Verifica primer código TOTP → activa 2FA |
| `disable_2fa.py` | `Disable2FAUseCase` | Verifica código TOTP → desactiva 2FA y borra secreto |
| `verify_2fa_login.py` | `Verify2FALoginUseCase` + `PreAuthToken` | Valida `pre_auth_token` + TOTP → emite tokens completos |

#### 4.4 Configuración de email

En desarrollo, Django usa `console.EmailBackend` que imprime el email completo en los logs de Docker (subject, destinatario, cuerpo y link), sin necesidad de un servidor SMTP. Para producción se puede configurar vía variables de entorno:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.ejemplo.com
EMAIL_PORT=587
EMAIL_HOST_USER=noreply@cryptoworld.com
EMAIL_HOST_PASSWORD=secreto
FRONTEND_URL=https://app.cryptoworld.com
```

#### 4.5 Nuevos endpoints implementados

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| POST | `/api/auth/logout/` | ✅ Requerida | Invalida el refresh_token |
| GET | `/api/auth/me/` | ✅ Requerida | Perfil del usuario autenticado |
| GET | `/api/auth/verify-email/` | ❌ Pública | Confirmar email con token del link |
| POST | `/api/auth/verify-email/resend/` | ✅ Requerida | Reenviar email de verificación |
| POST | `/api/auth/password-reset/` | ❌ Pública | Solicitar link de recuperación |
| POST | `/api/auth/password-reset/confirm/` | ❌ Pública | Confirmar nueva contraseña |
| POST | `/api/auth/change-password/` | ✅ Requerida | Cambiar contraseña (requiere actual) |
| POST | `/api/auth/2fa/setup/` | ✅ Requerida | Iniciar setup: genera secreto + QR |
| POST | `/api/auth/2fa/enable/` | ✅ Requerida | Activar 2FA con primer código TOTP |
| POST | `/api/auth/2fa/disable/` | ✅ Requerida | Desactivar 2FA (requiere código TOTP) |
| POST | `/api/auth/2fa/login/` | ❌ Pública | Segunda fase del login con 2FA |

#### 4.6 Validación completa del flujo 2FA (Marzo 2026)

```
1. POST /api/auth/login/           → { requires_2fa: false } (sin 2FA activo)
2. GET  /api/auth/me/              → { is_2fa_enabled: false, is_email_verified: false }
3. POST /api/auth/2fa/setup/       → { totp_secret: "BASE32...", qr_code_base64: "data:image/png..." }
4. POST /api/auth/2fa/enable/      → { message: "2FA activado correctamente." }
5. POST /api/auth/login/           → { requires_2fa: true, pre_auth_token: "eyJ..." }
6. POST /api/auth/2fa/login/       → { access_token: "eyJ...", refresh_token: "eyJ..." }
7. POST /api/auth/logout/          → { message: "Sesión cerrada correctamente." }
8. POST /api/auth/password-reset/  → email impreso en logs de Docker con link completo
9. POST /api/auth/change-password/ → { message: "Contraseña cambiada correctamente." }
```

Todos los endpoints retornaron HTTP 200/201 en pruebas reales contra el contenedor Docker.

#### 4.7 Problema de encoding durante la implementación

Al usar PowerShell `Set-Content` para truncar el archivo `views.py`, el contenido se reescribió con codificación CP1252 interpretada como UTF-8, corrompiendo todos los caracteres españoles en docstrings y comentarios (`á` → `Ã¡`, `ó` → `Ã³`, etc.).

**Solución:** script Python ejecutado dentro del contenedor que invirtió la doble codificación (decode UTF-8 → encode CP1252, recuperando los bytes UTF-8 originales):

```python
with open(path, 'rb') as f: raw = f.read()
fixed = raw.decode('utf-8').encode('cp1252')
with open(path, 'wb') as f: f.write(fixed)
```

El archivo quedó correctamente codificado en UTF-8 y Django recargó sin errores.

---

## 5. Estructura del Proyecto

### Árbol completo (estado actual v1.2.0)

```
CryptoWorld/
├── .env                          ← Variables de entorno (no en Git)
├── .env.example                  ← Plantilla de variables
├── .gitignore
├── docker-compose.yml            ← Orquestación de servicios
├── Memoria_TFG.md                ← Este documento
├── README.md
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── unit/
│   │   │   └── test_domain_entities.py
│   │   └── integration/
│   │       └── test_api_endpoints.py
│   └── src/
│       ├── manage.py
│       ├── config/
│       │   ├── settings.py
│       │   ├── urls.py
│       │   └── wsgi.py
│       └── core/
│           ├── apps.py
│           ├── models.py                ← NUEVO: adaptador de importación
│           ├── __init__.py
│           ├── domain/
│           │   ├── entities/
│           │   │   ├── user_entity.py
│           │   │   ├── crypto_asset_entity.py
│           │   │   ├── market_data_snapshot_entity.py
│           │   │   └── analysis_execution_entity.py
│           │   ├── repositories/
│           │   │   ├── i_user_repository.py
│           │   │   └── i_crypto_asset_repository.py
│           │   ├── services/
│           │   │   └── user_domain_service.py
│           │   └── value_objects/
│           │       ├── email.py
│           │       └── crypto_symbol.py
│           ├── application/
│           │   ├── use_cases/
│           │   │   ├── register_user_use_case.py
│           │   │   ├── get_assets_use_case.py
│           │   │   ├── run_analysis_use_case.py
│           │   │   ├── logout.py                      ← NUEVO: blacklist refresh token
│           │   │   ├── send_verification_email.py     ← NUEVO: enviar email de activación
│           │   │   ├── verify_email.py                ← NUEVO: confirmar email con token
│           │   │   ├── request_password_reset.py      ← NUEVO: enviar link de recuperación
│           │   │   ├── confirm_password_reset.py      ← NUEVO: aplicar nueva contraseña
│           │   │   ├── change_password.py             ← NUEVO: cambiar contraseña autenticado
│           │   │   ├── setup_2fa.py                   ← NUEVO: generar secreto TOTP + QR
│           │   │   ├── enable_2fa.py                  ← NUEVO: activar 2FA con primer TOTP
│           │   │   ├── disable_2fa.py                 ← NUEVO: desactivar 2FA
│           │   │   └── verify_2fa_login.py            ← NUEVO: segunda fase login 2FA
│           │   └── dto/
│           │       ├── auth_dto.py                    ← AMPLIADO: +9 nuevos DTOs
│           │       └── asset_dto.py
│           ├── infrastructure/
│           │   ├── persistence/
│           │   │   ├── models.py             ← AMPLIADO: +3 campos en User (is_email_verified, totp_secret, is_2fa_enabled)
│           │   │   └── repositories_impl.py  ← AMPLIADO: +5 métodos en DjangoUserRepository
│           │   └── external_apis/            ← (pendiente) CoinGecko
│           ├── interfaces/
│           │   └── api/
│           │       ├── views.py       ← AMPLIADO: +11 nuevas vistas de auth
│           │       ├── serializers.py ← AMPLIADO: +9 nuevos serializers
│           │       └── urls.py        ← AMPLIADO: +11 nuevas rutas
│           └── migrations/
│               ├── 0001_initial.py           ← sin cambios
│               └── 0002_user_auth_fields.py  ← NUEVO: is_email_verified, totp_secret, is_2fa_enabled
│
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── routes.tsx
│       ├── index.css
│       ├── vite-env.d.ts
│       ├── hooks/
│       │   └── useAuth.ts
│       ├── services/
│       │   ├── api.ts
│       │   ├── authService.ts
│       │   └── analysisService.ts
│       ├── components/
│       │   ├── Navbar.tsx
│       │   └── ProtectedRoute.tsx
│       └── pages/
│           ├── LoginPage.tsx
│           ├── DashboardPage.tsx
│           └── AssetDetailPage.tsx
│
└── info/                         ← Documentación adicional del proyecto
```

---

## 6. Decisiones de Diseño Justificadas

### 6.1 Por qué Clean Architecture

La Clean Architecture permite que el núcleo del sistema (dominio y casos de uso) sea completamente independiente de frameworks, bases de datos e interfaces externas. Esto es especialmente relevante en un TFG donde se quiere demostrar dominio de principios SOLID y patrones de diseño.

**Ventajas concretas en este proyecto:**
- El `GetAssetsUseCase` no sabe si los datos vienen de PostgreSQL o de CoinGecko API
- El `User` del dominio (`UserEntity`) es una clase Python pura sin dependencias Django
- Los tests unitarios del dominio se ejecutan sin necesidad de base de datos

### 6.2 Por qué AUTH_USER_MODEL personalizado

Django provee un modelo `User` predeterminado con `username` como campo principal de autenticación. En este proyecto se optó por email como identificador porque:
- Es más natural en aplicaciones modernas
- Elimina la duplicidad username/email
- Es una práctica estándar en sistemas financieros/fintech

### 6.3 Por qué JWT en lugar de sesiones

Las sesiones de Django se almacenan en servidor (base de datos o cache). Al usar contenedores Docker stateless y pensando en escalabilidad horizontal futura, JWT es más apropiado:
- El token viaja en el cliente (localStorage)
- El backend no necesita consultar BD para validar cada petición
- Compatible con arquitecturas API-first y aplicaciones móviles futuras

### 6.4 Por qué core/models.py como adaptador de importación

Django requiere que los modelos de una app sean descubribles desde `<app>.models`. Dado que en Clean Architecture los modelos ORM pertenecen a la capa de infraestructura, se creó `core/models.py` como un archivo de reexportación (Adapter Pattern) que:
- Mantiene la separación de capas intacta
- Satisface el mecanismo de autodescubrimiento de Django
- No añade lógica, solo conecta capas

### 6.5 Por qué Docker Compose para desarrollo

- Garantiza entorno reproducible (elimina el "en mi máquina funciona")
- Aísla PostgreSQL del sistema host
- Facilita CI/CD en fases posteriores
- El `healthcheck` de PostgreSQL evita que Django arranque antes de que la BD esté lista

### 6.6 Por qué TOTP para 2FA (en lugar de SMS)

Se eligió TOTP (Time-based One-Time Password, RFC 6238) frente a la verificación por SMS por varias razones:
- **Sin dependencia externa:** no requiere proveedor de SMS (Twilio, AWS SNS), reduciendo costes y complejidad en el TFG.
- **Mayor seguridad:** los ataques de SIM swapping no son posibles con TOTP.
- **Estándar abierto:** funciona con cualquier app autenticadora (Google Authenticator, Authy, Bitwarden, etc.).
- **Offline:** el código se genera en el dispositivo del usuario, sin necesidad de red.

### 6.7 Por qué token temporal Pre-Auth en la segunda fase del login con 2FA

El flujo de 2FA requiere dos peticiones HTTP, lo que crea un problema de estado: "¿cómo sabemos que el usuario del paso 2 es el mismo que validó la contraseña en el paso 1?" sin almacenar estado en servidor (sesiones) ni exponer tokens de acceso completos de forma prematura.

Solución: emitir un JWT especial con `token_type = "pre_2fa"` y `lifetime = 5 minutos` que:
- Solo sirve para llamar a `/api/auth/2fa/login/`
- No tiene permisos de acceso a recursos protegidos
- Expira en 5 minutos si el usuario no completa el segundo factor
- Sigue el mismo patrón stateless del resto del sistema

---

## 7. Problemas Encontrados y Soluciones

| # | Fase | Error | Causa | Solución | Archivos modificados |
|---|------|-------|-------|----------|---------------------|
| 1 | Docker | `pipe error` | Docker Desktop parado | Iniciar Docker Desktop | — |
| 2 | Docker | `version is obsolete` | Campo `version` obsoleto en Compose v2 | Eliminar `version: "3.9"` | `docker-compose.yml` |
| 3 | Docker Build | `npm ci` falla | Sin `package-lock.json` | Cambiar a `npm install` | `frontend/Dockerfile` |
| 4 | Docker Build | pip timeout | Red lenta | `--timeout=300 --retries=5` | `backend/Dockerfile` |
| 5 | TypeScript | `TS1005: '>' expected` | JSX en archivo `.ts` | Usar `React.createElement()` | `frontend/src/hooks/useAuth.ts` |
| 6 | TypeScript | `'env' not on ImportMeta` | Falta declaración tipos Vite | Crear `vite-env.d.ts` | `frontend/src/vite-env.d.ts` (nuevo) |
| 7 | Django Runtime | `AUTH_USER_MODEL not installed` | Falta `core/models.py` | Crear adaptador de importación | `backend/src/core/models.py` (nuevo) |
| 8 | Django Runtime | `relation "users" does not exist` | La app `core` no tenía directorio `migrations/` | `docker compose run --rm backend python src/manage.py makemigrations core` para generar `0001_initial.py` | `backend/src/core/migrations/0001_initial.py` (nuevo) |
| 9 | Auth — 2FA | `No module named 'pyotp'` | Paquetes nuevos no instalados en imagen Docker existente | `docker compose build backend` (rebuild de imagen) | `backend/requirements.txt` |
| 10 | Encoding | Caracteres españoles corruptos en `views.py` (`á` → `Ã¡`) | PowerShell `Set-Content` leyó UTF-8 como CP1252 y reescribió como UTF-8 (doble codificación) | Script Python dentro del contenedor invirtió la codificación: `raw.decode('utf-8').encode('cp1252')` | `backend/src/core/interfaces/api/views.py` |

---

## 8. Estado Actual del Sistema

### Servicios Docker
| Servicio | Puerto | Estado |
|----------|--------|--------|
| `cryptoworld_postgres` | 5432 | ✅ Running (healthy) |
| `cryptoworld_backend` | 8000 | ✅ Running — servidor Django operativo |
| `cryptoworld_frontend` | 80 (externo 5173) | ✅ Running — SPA React sirviendo |

### Endpoints API disponibles
| Método | Ruta | Estado | Descripción |
|--------|------|--------|-------------|
| GET | `/api/health/` | ✅ Implementado | Health check del sistema |
| POST | `/api/auth/register/` | ✅ Implementado | Registro + email de verificación automático |
| POST | `/api/auth/login/` | ✅ Implementado | Login (soporta 2FA con pre_auth_token) |
| POST | `/api/auth/logout/` | ✅ Implementado | Logout seguro (blacklist refresh_token) |
| GET | `/api/auth/me/` | ✅ Implementado | Perfil del usuario autenticado |
| POST | `/api/auth/token/refresh/` | ✅ Implementado | Renovación de access token |
| GET | `/api/auth/verify-email/` | ✅ Implementado | Confirmar email con token HMAC |
| POST | `/api/auth/verify-email/resend/` | ✅ Implementado | Reenviar email de verificación |
| POST | `/api/auth/password-reset/` | ✅ Implementado | Solicitar link de recuperación |
| POST | `/api/auth/password-reset/confirm/` | ✅ Implementado | Confirmar nueva contraseña |
| POST | `/api/auth/change-password/` | ✅ Implementado | Cambiar contraseña (requiere actual) |
| POST | `/api/auth/2fa/setup/` | ✅ Implementado | Generar secreto TOTP + QR base64 |
| POST | `/api/auth/2fa/enable/` | ✅ Implementado | Activar 2FA con primer código TOTP |
| POST | `/api/auth/2fa/disable/` | ✅ Implementado | Desactivar 2FA |
| POST | `/api/auth/2fa/login/` | ✅ Implementado | Segunda fase del login con 2FA |
| GET | `/api/assets/` | ⚠️ Mock data | Lista de activos (datos ficticios) |
| POST | `/api/analysis/run/` | ⚠️ Stub | Ejecutar análisis (sin implementar) |

### Capas implementadas
| Capa | Estado | Notas |
|------|--------|-------|
| Domain — Entities | ✅ Completo | 4 entidades + `UserEntity` ampliada con campos 2FA/email |
| Domain — Repositories (interfaces) | ✅ Completo | IUserRepository, ICryptoAssetRepository |
| Domain — Value Objects | ✅ Completo | Email, CryptoSymbol |
| Domain — Services | ✅ Completo | UserDomainService |
| Application — Use Cases auth | ✅ Completo | 10 casos de uso: register, logout, verify_email, password_reset (x2), change_password, 2FA (x4) |
| Application — Use Cases datos | ⚠️ Parcial | GetAssets (mock), RunAnalysis (stub) |
| Application — DTOs | ✅ Completo | auth_dto (13 DTOs), asset_dto |
| Infrastructure — ORM Models | ✅ Completo | 4 modelos Django + 3 campos nuevos en User |
| Infrastructure — Repositories impl | ✅ Completo | +5 métodos nuevos en DjangoUserRepository |
| Infrastructure — External APIs | ❌ Pendiente | CoinGecko API |
| Interfaces — API Views | ✅ Completo | 17 endpoints totales (auth completo) |
| Frontend — Auth flow | ✅ Completo | Login, JWT, rutas protegidas |
| Frontend — Dashboard | ⚠️ Parcial | Sin datos reales |
| Tests | ⚠️ Parcial | Esqueleto creado, sin ejecutar |

### Migraciones aplicadas
| Migración | Descripción | Estado |
|-----------|-------------|--------|
| `core.0001_initial` | Tablas: users, crypto_assets, market_data_snapshots, analysis_executions | ✅ Aplicada |
| `core.0002_user_auth_fields` | Campos: is_email_verified, totp_secret, is_2fa_enabled en users | ✅ Aplicada |
| `token_blacklist.*` (12 migraciones) | Tablas OutstandingToken y BlacklistedToken para logout seguro | ✅ Aplicadas |

### Validación completa del stack (v1.2.0 — Marzo 2026)
| Test | Resultado |
|------|-----------|
| `GET /api/health/` | ✅ 200 `{"status":"ok","version":"1.0.0"}` |
| `POST /api/auth/register/` | ✅ 201 — Email de verificación impreso en logs Docker |
| `POST /api/auth/login/` (sin 2FA) | ✅ 200 — `requires_2fa: false` + tokens JWT |
| `GET /api/auth/me/` | ✅ 200 — Perfil con `is_2fa_enabled`, `is_email_verified` |
| `POST /api/auth/2fa/setup/` | ✅ 200 — Secreto base32 + QR PNG base64 |
| `POST /api/auth/2fa/enable/` | ✅ 200 — "2FA activado correctamente." |
| `POST /api/auth/login/` (con 2FA) | ✅ 200 — `requires_2fa: true` + `pre_auth_token` |
| `POST /api/auth/2fa/login/` | ✅ 200 — tokens JWT completos |
| `POST /api/auth/logout/` | ✅ 200 — refresh_token blacklisteado |
| `POST /api/auth/password-reset/` | ✅ 200 — Email de recuperación en logs Docker |
| `POST /api/auth/change-password/` | ✅ 200 — "Contraseña cambiada correctamente." |
| `GET /api/assets/` con JWT | ✅ 200 — Devuelve datos mock |
| Frontend `http://localhost:5173` | ✅ Sirviendo la SPA React |

---

## 9. Próximos Pasos

### Completado en Fase 4 ✅

Los siguientes ítems que figuraban como pendientes han sido implementados:

- ✅ Sistema de autenticación completo (login, logout, registro)
- ✅ Tokens JWT con refresh y blacklist (logout seguro)
- ✅ Verificación de email con token HMAC
- ✅ Recuperación y cambio de contraseña
- ✅ 2FA TOTP compatible con Google Authenticator / Authy
- ✅ Endpoint `/api/auth/me/` con perfil del usuario autenticado
- ✅ Migración 0002 con los nuevos campos del modelo User

### Sprint 1 — Integración CoinGecko API (próximo)

**Objetivo:** sustituir el mock data por datos de mercado reales.

**Tareas:**
1. Crear `infrastructure/external_apis/coingecko_client.py` con cliente HTTP (httpx/requests)
2. Implementar `GetLiveMarketDataUseCase` en la capa application
3. Definir `ICoinGeckoRepository` en el dominio
4. Conectar endpoint `GET /api/assets/` con datos reales vía CoinGecko
5. Cachear respuestas en Redis/base de datos para evitar rate-limiting
6. Guardar snapshots periódicos en `market_data_snapshots`

**Archivos a crear/modificar:**
```
backend/src/core/
├── domain/repositories/i_market_data_repository.py   (nuevo)
├── application/use_cases/get_live_market_data.py      (nuevo)
├── infrastructure/external_apis/
│   └── coingecko_client.py                            (nuevo)
└── infrastructure/persistence/
    └── market_data_repository_impl.py                 (nuevo/modificar)
```

### Sprint 2 — Análisis Técnico

**Objetivo:** implementar los indicadores de análisis técnico en la capa de dominio.

- RSI (Relative Strength Index) en `domain/services/`
- MACD en `domain/services/`
- Bandas de Bollinger en `domain/services/`
- Conectar con `RunAnalysisUseCase` y endpoint `/api/analysis/run/`

### Sprint 3 — Mejoras Frontend

**Objetivo:** conectar la interfaz con los datos reales del backend.

- Gráficos de precios históricos con Recharts/Tremor
- Tabla de mercado con datos reales paginados
- Página de detalle de activo con indicadores técnicos
- Integrar flujo completo 2FA en el frontend (formulario de código TOTP)
- Integrar verificación de email en el flujo de registro

### Sprint 4 — Portfolio y Alertas

- CRUD de portfolio personal (posiciones, precio de entrada)
- Sistema de alertas (precio objetivo, % de cambio)
- Historial de análisis ejecutados por usuario

### Largo plazo — Calidad y Documentación

- Suite completa de tests unitarios e integración (pytest + factory_boy)
- Documentación API con Swagger/OpenAPI (`drf-spectacular`)
- Optimización de consultas PostgreSQL con índices
- Despliegue en servidor (Render, Railway o VPS)
- Memoria TFG final en LaTeX

---

*Documento generado automáticamente durante el desarrollo. Actualizar con cada sprint completado.*

*Última actualización: Marzo 2026 — v1.2.0 (auth completo)*
