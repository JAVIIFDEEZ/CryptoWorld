# CryptoWorld — TFG Sistema de Análisis de Criptomonedas

> **Trabajo de Fin de Grado** — Ingeniería Informática, UCLM  
> Arquitectura Cliente-Servidor con Clean Architecture  
> *Última actualización: Abril 2026*

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
├── application/       ← Casos de uso (24 archivos) + DTOs (23 dataclasses)
│   ├── use_cases/     ← Una clase por acción: auth, analysis, market, admin
│   └── dto/           ← auth_dto.py, asset_dto.py, market_intelligence_dto.py
├── infrastructure/    ← Adaptadores externos
│   ├── persistence/   ← Django ORM models (5 tablas) + repos concretos
│   └── external_apis/ ← BinancePublicClient + CoinGeckoClient
└── interfaces/        ← Controladores HTTP (31 endpoints)
    └── api/           ← views.py + serializers.py + urls.py
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

## Endpoints de la API (31 rutas)

### Salud
| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| `GET` | `/api/health/` | No | Estado del servidor |

### Autenticación (16 endpoints)
| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| `POST` | `/api/auth/register/` | No | Registrar usuario |
| `POST` | `/api/auth/login/` | No | Login → JWT (soporta flujo 2FA) |
| `POST` | `/api/auth/logout/` | JWT | Logout seguro (blacklist refresh) |
| `GET` | `/api/auth/me/` | JWT | Perfil del usuario autenticado |
| `POST` | `/api/auth/token/refresh/` | No | Renovar access token |
| `GET` | `/api/auth/verify-email/` | No | Verificar email (link con token HMAC) |
| `POST` | `/api/auth/verify-email/resend/` | JWT | Reenviar email de verificación |
| `POST` | `/api/auth/password-reset/` | No | Solicitar recuperación de contraseña |
| `POST` | `/api/auth/password-reset/confirm/` | No | Confirmar nueva contraseña con token |
| `POST` | `/api/auth/change-password/` | JWT | Cambiar contraseña (requiere actual) |
| `DELETE` | `/api/auth/delete-account/` | JWT | Eliminar cuenta permanentemente |
| `POST` | `/api/auth/2fa/setup/` | JWT | Generar secreto TOTP + QR base64 |
| `POST` | `/api/auth/2fa/enable/` | JWT | Activar 2FA con primer código TOTP |
| `POST` | `/api/auth/2fa/disable/` | JWT | Desactivar 2FA |
| `POST` | `/api/auth/2fa/login/` | No | Segundo paso login 2FA (pre_auth_token + TOTP) |

### Datos de mercado
| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| `GET` | `/api/assets/` | JWT | Listar activos (datos reales de CoinGecko) |
| `GET` | `/api/assets/<symbol>/ohlcv/` | JWT | Velas OHLCV (Binance → CoinGecko fallback) |
| `GET` | `/api/market/overview/` | JWT | Métricas globales (cap total, vol 24h, BTC dom, Fear & Greed) |
| `GET` | `/api/blockchain/metrics/` | JWT | Métricas on-chain (stub — datos simulados) |
| `GET` | `/api/news/` | JWT | Feed de noticias (stub — datos simulados) |

### Análisis técnico
| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| `POST` | `/api/analysis/run/` | JWT | Ejecutar análisis con indicador individual |
| `POST` | `/api/analysis/calculate/` | JWT | Calcular indicador técnico (RSI, MACD, SMA, EMA, Bollinger) |
| `POST` | `/api/analysis/signals/` | JWT | Panel multi-indicador con 11 señales y veredicto |
| `POST` | `/api/analysis/predict/` | JWT | Predicción ML con Random Forest |
| `POST` | `/api/analysis/patterns/` | JWT | Detección de 12 patrones de velas japonesas |
| `POST` | `/api/analysis/backtest/` | JWT | Backtesting de 5 estrategias |
| `GET` | `/api/analysis/strategies/` | JWT | Lista de estrategias disponibles para backtest |

### Administración
| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| `GET` | `/api/admin/users/` | Admin | Listar usuarios |
| `GET/PATCH/DELETE` | `/api/admin/users/<id>/` | Admin | Gestión individual de usuario |
| `POST` | `/api/admin/market/sync/` | Admin | Sincronizar catálogo desde CoinGecko |

---

## Tests

```bash
# Dentro del contenedor Docker
docker compose exec backend pytest                     # Todos los tests
docker compose exec backend pytest -m unit             # Solo unitarios (sin BD)
docker compose exec backend pytest -m integration      # Solo integración
docker compose exec backend pytest --cov=core --cov-report=html  # Con cobertura

# O localmente con el entorno virtual
cd backend && pytest
```

**Cobertura actual:** ~51 tests (unitarios de entidades, value objects, repositorios, servicios de dominio + integración de endpoints API).

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
- [ ] Gestión de portfolio personal (posiciones, P&L)
- [ ] Sistema de alertas configurables
- [ ] Feed de noticias real (actualmente stub)
- [ ] Métricas on-chain reales (actualmente stub)

---

**Autor:** Javier — TFG Ingeniería Informática, UCLM  
**Versión del proyecto:** v1.29.4 — Abril 2026