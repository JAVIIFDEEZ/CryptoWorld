# CryptoWorld — TFG Sistema de Análisis de Criptomonedas

> **Trabajo de Fin de Grado** — Ingeniería Informática, UCLM  
> Arquitectura Cliente-Servidor con Clean Architecture  
> *Última actualización: Agosto 2026*

[![CI](https://github.com/JAVIIFDEEZ/CryptoWorld/actions/workflows/ci.yml/badge.svg)](https://github.com/JAVIIFDEEZ/CryptoWorld/actions/workflows/ci.yml)

---

## Descripción

Plataforma web para el análisis cuantitativo de criptomonedas desarrollada como TFG siguiendo los principios de **Arquitectura Limpia** (Clean Architecture — Robert C. Martin). El sistema integra datos de mercado reales de Binance y CoinGecko, aplica análisis técnico con 11 indicadores, predicción ML con Random Forest, detección de patrones de velas, backtesting de 5 estrategias, y presenta todo en gráficos profesionales con KLineChart v9.

---

## Stack tecnológico

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Frontend | React + TypeScript + Vite + TailwindCSS | 18.3 / 5.5 / 5.3 / 3.4 |
| Gráficos | KLineChart (velas profesionales, 20+ indicadores, 15 herramientas de dibujo) | v9 |
| HTTP Client | Axios (interceptores JWT automáticos) | 1.7 |
| Backend | Python + Django + Django REST Framework | 3.11 / 5.0 / 3.15 |
| Auth | SimpleJWT (access + refresh + blacklist + 2FA TOTP) | 5.3 |
| Análisis técnico | ta (indicadores) + scikit-learn (ML) + pandas + numpy | 0.11 / 1.5 / 2.2 / 1.26 |
| Base de datos | PostgreSQL | 16 |
| Contenedores | Docker + Docker Compose v2 | — |
| Tests | pytest + pytest-django + factory-boy | 8.2 / 4.8 / 3.3 |
| Producción | Nginx (frontend) + Gunicorn (backend) | alpine / 22.0 |

### APIs externas consumidas

| API | Uso | Auth | Rate limit |
|-----|-----|------|-----------|
| **Binance Public** | OHLCV con volumen real (fuente primaria) | Ninguna | ~600 req/min |
| **CoinGecko v3** | Catálogo de mercado + OHLC fallback | API key opcional | 30 req/min |
| **Alternative.me** | Fear & Greed Index | Ninguna | Ilimitado |

---

## Arquitectura del backend (Clean Architecture)

```
backend/src/core/
├── domain/            ← Reglas de negocio puras (sin frameworks)
│   ├── entities/      ← UserEntity, CryptoAssetEntity, MarketDataSnapshotEntity,
│   │                    PortfolioAssetEntity, AnalysisExecutionEntity
│   ├── repositories/  ← IUserRepository, ICryptoAssetRepository (contratos ABC)
│   ├── services/      ← UserDomainService, TechnicalAnalysisService (~900 líneas)
│   └── value_objects/ ← Email, CryptoSymbol (inmutables)
├── application/       ← Casos de uso + DTOs + servicios transversales
│   ├── use_cases/     ← Una clase por acción: auth, analysis, market, admin
│   ├── services/      ← audit, sessions, login_guard
│   └── dto/           ← auth_dto.py, asset_dto.py, portfolio_dto.py…
├── infrastructure/    ← Adaptadores externos
│   ├── persistence/   ← Django ORM models (11 tablas) + repos concretos
│   └── external_apis/ ← Binance, CoinGecko, KuCoin, Blockchair…
└── interfaces/        ← Controladores HTTP (53 endpoints)
    └── api/           ← views, serializers, urls, autenticación,
                         paginación y manejador de errores
```

**Regla de dependencias:** `interfaces → application → domain ← infrastructure`

---

## Instalación y puesta en marcha

### Opción A — Docker (recomendado)

```bash
cp .env.example .env          # editar con tus datos
docker compose up --build
# Frontend → http://localhost:5173
# Backend  → http://localhost:8000/api/
# pgAdmin  → http://localhost:5050
```

### Opción B — Desarrollo local

#### Backend
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env   # editar con tus datos de PostgreSQL
cd src
python manage.py migrate
python manage.py runserver   # http://localhost:8000
```

#### Frontend
```bash
cd frontend
npm install
echo "VITE_API_URL=http://localhost:8000/api" > .env.local
npm run dev   # http://localhost:5173
```

---

## Documentación de la API

El esquema **OpenAPI 3** se genera desde el propio código, así que no
puede quedar desincronizado con los endpoints (como sí ocurría con la
tabla de rutas que se mantenía a mano en este README):

| Recurso | URL |
|---|---|
| Esquema OpenAPI (YAML) | `/api/schema/` |
| Swagger UI — explorador interactivo | `/api/docs/` |
| ReDoc — documentación de lectura | `/api/redoc/` |

**53 endpoints** agrupados en: autenticación y cuenta (13), doble factor
(5), mercado y activos (6), on-chain y noticias (3), análisis técnico (7),
portfolio y posiciones (7), alertas (3), watchlist (2), administración (5)
y sondas de salud (2).

### Contrato de error

Toda respuesta de error comparte la misma envolvente, con un código
estable que el cliente puede usar para decidir:

```json
{
  "error": {
    "code": "email_not_verified",
    "message": "Debes verificar tu email antes de iniciar sesión.",
    "details": { "campo": ["mensaje"] }
  },
  "request_id": "3f2a9c1e8b7d4f60a1c2e3d4f5a6b7c8"
}
```

`request_id` viaja también en la cabecera `X-Request-ID` y aparece en
todas las líneas de log de esa petición: es lo que permite localizar una
incidencia reportada por un usuario sin ambigüedad.

### Sondas de salud

| URL | Uso | Comportamiento |
|---|---|---|
| `/api/health/live/` | Liveness probe | 200 si el proceso responde. No consulta dependencias, para que un fallo de Redis no provoque el reinicio en bucle del servicio web. |
| `/api/health/` | Readiness probe | 200 si base de datos, cache y broker responden; 503 si alguno falla. El desglose por componente solo se revela a administradores. |

---

## Tests

```bash
# Dentro del contenedor Docker
docker compose exec backend pytest                     # Todos los tests
docker compose exec backend pytest -m unit             # Solo unitarios (sin BD)
docker compose exec backend pytest -m integration      # Solo integración
docker compose exec backend pytest -m security         # Solo controles de seguridad
docker compose exec backend pytest --cov-report=html   # Informe HTML de cobertura

# O localmente con el entorno virtual
cd backend && pytest
```

**293 tests, 70 % de cobertura.** El umbral mínimo está fijado en
`pytest.ini` (`--cov-fail-under=68`) y funciona como trinquete: la
cobertura no puede bajar sin que la integración continua lo detenga.

| Suite | Qué cubre |
|---|---|
| `tests/unit/domain/` | Entidades, value objects, repositorios y el motor de análisis técnico |
| `tests/integration/test_security_controls.py` | Política de contraseñas, revocación de sesiones, bloqueo por cuenta, privilegios y auditoría |
| `tests/integration/test_portfolio_arithmetic.py` | Coste medio ponderado, PnL en LONG/SHORT y precisión decimal |
| `tests/integration/test_alerts_and_trades.py` | Alertas, evaluación por el worker, operaciones y retención |
| `tests/integration/test_api_endpoints.py` | Rutas, códigos de estado y autenticación JWT |

### Comprobaciones de calidad

```bash
cd backend
ruff check .                                    # Lint
python src/manage.py check --deploy             # Configuración de producción
python src/manage.py spectacular --fail-on-warn # Esquema OpenAPI
```

---

## Principios y patrones aplicados

- **Clean Architecture** — separación estricta de 4 capas con regla de dependencia
- **SOLID** — SRP (un caso de uso = una clase), OCP, DIP (repos abstractos)
- **Domain-Driven Design** — entidades, value objects, repositorios, servicios de dominio
- **Repository Pattern** — interfaces ABC en dominio, implementaciones Django en infraestructura
- **DTO Pattern** — 23 dataclasses `frozen=True` como contrato entre capas
- **Strategy Pattern** — cadena Binance → CoinGecko → error para datos OHLCV
- **Adapter Pattern** — clientes de APIs externas encapsulan HTTP
- **Guard Pattern** — `ProtectedRoute` + `AdminRoute` en React
- **Interceptor Pattern** — Axios inyecta JWT + maneja 401 globalmente

---

## Seguridad

El modelo de seguridad completo —autenticación, control de acceso,
límites de peticiones, auditoría y riesgos aceptados— está en
[`SECURITY.md`](SECURITY.md). El informe de la revisión de agosto de 2026
y las correcciones aplicadas, en
[`info/Auditoria_2026.md`](info/Auditoria_2026.md).

En resumen:

- Contraseñas PBKDF2 con política única de 12 caracteres mínimo en
  registro, cambio y recuperación.
- Doble factor TOTP con códigos de recuperación hasheados de un solo uso.
- Access tokens de 15 minutos; cambiar la contraseña o el email revoca
  **todas** las sesiones abiertas, incluidos los access ya emitidos.
- Bloqueo temporal por cuenta ante intentos fallidos, además del límite
  por IP.
- Dos niveles administrativos: solo un superusuario concede privilegios.
- Registro de auditoría de todo evento sensible, con retención definida.
- `manage.py check --deploy` sin ningún aviso, verificado en cada
  integración con la configuración real de producción.

---

## Roadmap del TFG

- [x] Estructura base con Clean Architecture
- [x] Autenticación JWT completa (registro, login, logout, refresh, blacklist)
- [x] Verificación de email + recuperación de contraseña (HMAC)
- [x] Autenticación 2FA con TOTP (Google Authenticator)
- [x] Integración CoinGecko API (catálogo de activos + métricas globales)
- [x] Integración Binance API (OHLCV con volumen real)
- [x] Strategy Pattern OHLCV (Binance → CoinGecko fallback → HTTP 404)
- [x] Motor de análisis técnico (11 indicadores + señales + veredicto global)
- [x] Predicción ML con Random Forest + cross-validation
- [x] Detección de 12 patrones de velas japonesas
- [x] Backtesting de 5 estrategias (RSI, MACD, Bollinger, SMA, EMA)
- [x] Gráficos profesionales con KLineChart v9 (15 herramientas, 20+ indicadores)
- [x] Panel de administración (gestión de usuarios + sync de mercado)
- [x] Eliminación de cuenta
- [x] Gestión de portfolio personal (posiciones LONG/SHORT, AVCO y P&L)
- [x] Sistema de alertas de precio configurables
- [x] Feed de noticias real (CryptoCompare)
- [x] Métricas on-chain reales (Blockchain.com y Blockchair)
- [x] Auditoría de seguridad y endurecimiento para producción
- [x] Registro de auditoría con retención
- [x] Esquema OpenAPI generado desde el código
- [ ] Autenticación por cookies `HttpOnly` (ver riesgos aceptados)
- [ ] Contrato unificado de series en los indicadores técnicos

---

**Autor:** Javier — TFG Ingeniería Informática, UCLM  
**Versión del proyecto:** v1.140.0 — Agosto 2026