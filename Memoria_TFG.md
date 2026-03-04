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
| django-cors-headers | 4.4.0 | CORS para comunicación con frontend |
| psycopg2-binary | 2.9.9 | Driver PostgreSQL |
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

## 5. Estructura del Proyecto

### Árbol completo (estado actual)

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
│           │   │   └── run_analysis_use_case.py
│           │   └── dto/
│           │       ├── auth_dto.py
│           │       └── asset_dto.py
│           ├── infrastructure/
│           │   ├── persistence/
│           │   │   ├── models.py             ← Modelos ORM Django
│           │   │   └── repositories_impl.py  ← Implementaciones concretas
│           │   └── external_apis/            ← (pendiente) CoinGecko
│           └── interfaces/
│               └── api/
│                   ├── views.py      ← Controladores HTTP
│                   ├── serializers.py
│                   └── urls.py
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
| POST | `/api/auth/register/` | ✅ Implementado | Registro de usuario |
| POST | `/api/auth/login/` | ✅ Implementado | Login y obtención de tokens JWT |
| POST | `/api/auth/token/refresh/` | ✅ Implementado | Renovación de access token |
| GET | `/api/assets/` | ⚠️ Mock data | Lista de activos (datos ficticios) |
| POST | `/api/analysis/run/` | ⚠️ Stub | Ejecutar análisis (sin implementar) |

### Capas implementadas
| Capa | Estado | Notas |
|------|--------|-------|
| Domain — Entities | ✅ Completo | 4 entidades del dominio |
| Domain — Repositories (interfaces) | ✅ Completo | IUserRepository, ICryptoAssetRepository |
| Domain — Value Objects | ✅ Completo | Email, CryptoSymbol |
| Domain — Services | ✅ Completo | UserDomainService |
| Application — Use Cases | ✅ Completo | Register, GetAssets, RunAnalysis |
| Application — DTOs | ✅ Completo | auth_dto, asset_dto |
| Infrastructure — ORM Models | ✅ Completo | 4 modelos Django |
| Infrastructure — Repositories impl | ✅ Completo | Django impl. de interfaces |
| Infrastructure — External APIs | ❌ Pendiente | CoinGecko API |
| Interfaces — API Views | ⚠️ Parcial | Endpoints con mock data |
| Frontend — Auth flow | ✅ Completo | Login, JWT, rutas protegidas |
| Frontend — Dashboard | ⚠️ Parcial | Sin datos reales |
| Tests | ⚠️ Parcial | Esqueleto creado, sin ejecutar |

### Migraciones y validación ✅

Las migraciones se han aplicado correctamente. Tablas creadas en PostgreSQL:
- `users` (modelo User personalizado con email como campo de auth)
- `crypto_assets`
- `market_data_snapshots`
- `analysis_executions`
- Tablas internas de Django (`auth_*`, `django_*`, `admin_*`)

**Validación completa del stack (Marzo 2026):**
| Test | Resultado |
|------|-----------|
| `GET /api/health/` | ✅ 200 `{"status":"ok","version":"1.0.0"}` |
| `POST /api/auth/login/` | ✅ 200 — Retorna `access_token` + `refresh_token` |
| `GET /api/assets/` con JWT | ✅ 200 — Devuelve datos mock |
| Frontend `http://localhost:5173` | ✅ Sirviendo la SPA React |

---

## 9. Próximos Pasos

### Inmediato — Validación del stack completo

**Paso 1: Aplicar migraciones**
```powershell
docker compose exec backend python src/manage.py migrate
```

**Paso 2: Crear superusuario**
```powershell
docker compose exec backend python src/manage.py createsuperuser
```

**Paso 3: Verificar health check**
```powershell
curl http://localhost:8000/api/health/
# Esperado: {"status": "ok"}
```

**Paso 4: Registrar usuario de prueba**
```powershell
curl -X POST http://localhost:8000/api/auth/register/ `
  -H "Content-Type: application/json" `
  -d '{"email":"test@test.com","username":"testuser","password":"Test1234!"}'
```

**Paso 5: Login y obtener JWT**
```powershell
curl -X POST http://localhost:8000/api/auth/login/ `
  -H "Content-Type: application/json" `
  -d '{"email":"test@test.com","password":"Test1234!"}'
# Esperado: {"access":"...","refresh":"..."}
```

**Paso 6: Verificar frontend**
- Abrir `http://localhost:5173` → debe redirigir a `/login`
- Hacer login desde el formulario → debe redirigir a `/dashboard`
- Verificar en F12 > Network que las peticiones llevan `Authorization: Bearer ...`

### Corto plazo — Funcionalidad real

**Sprint 1: Integración CoinGecko API**
- Crear `infrastructure/external_apis/coingecko_client.py`
- Implementar `GetLiveMarketDataUseCase`
- Conectar endpoint `/api/assets/` con datos reales

**Sprint 2: Análisis técnico**
- Implementar RSI (Relative Strength Index) en `domain/services/`
- Implementar MACD en `domain/services/`
- Implementar Bandas de Bollinger en `domain/services/`
- Conectar con `RunAnalysisUseCase`

**Sprint 3: Mejoras frontend**
- Gráficos de precios con Recharts
- Tabla de mercado con datos reales
- Página de detalle de activo con indicadores técnicos

**Sprint 4: Portfolio y alertas**
- CRUD de portfolio personal
- Sistema de alertas (precio objetivo, % cambio)
- Historial de análisis ejecutados

### Largo plazo — Calidad y documentación

- Suite completa de tests unitarios e integración
- Documentación API con Swagger/OpenAPI (`drf-spectacular`)
- Optimización de consultas PostgreSQL con índices
- Despliegue en servidor (Render, Railway o VPS)
- Memoria TFG final en LaTeX

---

*Documento generado automáticamente durante el desarrollo. Actualizar con cada sprint completado.*

*Última actualización: Marzo 2026*
