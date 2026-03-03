# CryptoWorld — TFG Sistema de Análisis de Criptomonedas

> **Trabajo de Fin de Grado** — Ingeniería Informática  
> Arquitectura Cliente-Servidor con Clean Architecture

---

## Descripción

Sistema modular para el análisis cuantitativo de criptomonedas, desarrollado siguiendo los principios de **Ingeniería del Software** e **Arquitectura Limpia** (Clean Architecture de Robert C. Martin).

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Frontend | React 18 + TypeScript + Vite + TailwindCSS |
| Backend | Python 3.11 + Django 5 + Django REST Framework |
| Base de datos | PostgreSQL 16 |
| Autenticación | JWT (SimpleJWT) |
| Contenedores | Docker + Docker Compose |
| Tests | pytest + pytest-django |

---

## Arquitectura del backend (Clean Architecture)

```
backend/src/core/
├── domain/            ← Reglas de negocio puras (sin frameworks)
│   ├── entities/      ← Objetos con identidad propia
│   ├── repositories/  ← Contratos (interfaces) de persistencia
│   ├── services/      ← Lógica de negocio entre varias entidades
│   └── value_objects/ ← Objetos inmutables identificados por valor
├── application/       ← Casos de uso (orquestan el dominio)
│   ├── use_cases/     ← Una clase por cada acción del sistema
│   └── dto/           ← Objetos de transferencia de datos
├── infrastructure/    ← Adaptadores externos
│   ├── persistence/   ← Django ORM + repos concretos
│   └── external_apis/ ← CoinGecko, Binance, etc.
└── interfaces/        ← Controladores HTTP
    └── api/           ← Views DRF + Serializers + URLs
```

**Dirección de dependencias:** `interfaces → application → domain ← infrastructure`

---

## Instalación y puesta en marcha

### Opción A — Docker (recomendado)

```bash
cp .env.example .env
docker compose up --build
# Frontend → http://localhost:5173
# Backend  → http://localhost:8000/api/
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

## Endpoints de la API

| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| `GET` | `/api/health/` | No | Estado del servidor |
| `POST` | `/api/auth/register/` | No | Registrar usuario |
| `POST` | `/api/auth/login/` | No | Login → tokens JWT |
| `POST` | `/api/auth/token/refresh/` | Token | Renovar access token |
| `GET` | `/api/assets/` | JWT | Listar activos cripto |
| `POST` | `/api/analysis/run/` | JWT | Solicitar análisis |

---

## Tests

```bash
cd backend
pytest            # Todos los tests
pytest -m unit    # Solo unitarios (sin BD)
pytest -m integration
pytest --cov=core --cov-report=html
```

---

## Principios aplicados

- **Clean Architecture** — separación estricta de capas
- **SOLID** — especialmente SRP, OCP y DIP
- **Domain-Driven Design** — entidades, value objects, repos, servicios
- **Inversión de Dependencias** — casos de uso dependen de interfaces

---

## Roadmap del TFG

- [x] Estructura base con Clean Architecture
- [x] Autenticación JWT
- [x] CRUD de activos criptográficos
- [ ] Integración con API CoinGecko
- [ ] Análisis técnico: RSI, MACD, Bollinger Bands
- [ ] Gráficos interactivos
- [ ] Backtesting de estrategias

---

**Autor:** Javier — TFG Ingeniería Informática, UCLM