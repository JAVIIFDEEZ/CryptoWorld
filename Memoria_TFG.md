# Documento de Briefing Técnico — CryptoWorld
## Sistema de Análisis de Criptomonedas — TFG

**Autor:** Javier  
**Titulación:** 4º Ingeniería Informática  
**Universidad:** Universidad de Castilla-La Mancha  
**Fecha del documento:** Mayo 2026 (v1.47.0)  

> **NOTA PARA LA IA REDACTORA:** Este documento es un briefing técnico completo del proyecto CryptoWorld tal como está implementado en mayo de 2026. Contiene el código real de los archivos más importantes, la justificación de cada decisión de diseño, y todos los detalles técnicos necesarios para redactar una memoria académica de TFG. No es necesario inferir nada—todo lo que existe en el proyecto está documentado aquí. El objetivo es una memoria académica formal para un TFG de Ingeniería Informática en la UCLM.

---

## ÍNDICE DEL BRIEFING

1. [Descripción General del Proyecto](#1-descripcion-general)
2. [Stack Tecnológico Completo](#2-stack-tecnologico)
3. [Arquitectura del Sistema — Visión Global](#3-arquitectura-vision-global)
4. [Backend: Clean Architecture en Detalle](#4-backend-clean-architecture)
   - 4.1 La Capa de Dominio (núcleo)
   - 4.2 La Capa de Aplicación (casos de uso)
   - 4.3 La Capa de Infraestructura
   - 4.4 La Capa de Interfaces (API)
   - 4.5 Flujo completo de una petición HTTP
5. [Sistema de Autenticación y Seguridad](#5-autenticacion-seguridad)
   - 5.1 JWT con blacklist para logout seguro
   - 5.2 Verificación de email
   - 5.3 Recuperación de contraseña
   - 5.4 Autenticación de Doble Factor (2FA TOTP)
6. [Infraestructura Docker y Despliegue](#6-docker)
7. [Frontend: Arquitectura React SPA](#7-frontend)
8. [Sistema de Tests](#8-tests)
9. [Base de Datos: Modelo Relacional](#9-base-de-datos)
10. [Decisiones de Diseño Justificadas](#10-decisiones-diseño)
11. [Estado Actual y Roadmap](#11-estado-actual)
12. [Registro de Problemas Resueltos](#12-problemas-resueltos)

---

## 1. DESCRIPCIÓN GENERAL DEL PROYECTO

**CryptoWorld** es una plataforma web de análisis de criptomonedas desarrollada como Trabajo de Fin de Grado. El proyecto combina un backend API REST con un frontend Single Page Application (SPA).

### Funcionalidades implementadas (Mayo 2026 — v1.47.0)
- Sistema de autenticación completo: registro, login, logout seguro
- Verificación de email mediante token HMAC
- Recuperación y cambio de contraseña (con logging de depuración en dev)
- Autenticación de Doble Factor (2FA) mediante TOTP (compatible con Google Authenticator)
- **Sincronización de catálogo de activos desde CoinGecko** (top N por market cap, logos, precios)
- **Datos OHLCV reales con cadena de fuentes** (Strategy Pattern: Binance → CoinGecko fallback → HTTP 404)
- **Métricas globales del mercado** (market cap total, volumen 24h, dominancia BTC, Fear & Greed Index)
- **Gráfico de velas interactivo profesional** (KLineChart v9: 15 herramientas de dibujo, 20+ indicadores técnicos, redimensionable)
- **Panel de administración** con gestión de usuarios y sincronización de mercado
- Dashboard frontend con datos reales, logos y métricas en tiempo real
- **Análisis técnico implementado con datos reales**: RSI, MACD, Bollinger, MA, EMA, SAR, señales multi-indicador, backtesting y predicción
- **Badge de fuente de datos**: el frontend indica visualmente si el gráfico usa datos de Binance o CoinGecko
- **Indicadores de volumen desactivados automáticamente** cuando la fuente es CoinGecko (API no provee volumen)
- **Celery + Redis**: sincronización periódica de mercado y evaluación de alertas de forma asíncrona
- **Feed de noticias real** (CryptoCompare News API con categorías, sentimiento y búsqueda)
- **Métricas on-chain BTC** (Blockchain.com Charts API: hashrate, transacciones, fees, mempool, etc.)
- **Panel MultiChain** (Blockchair API: estadísticas instantáneas de 10 blockchains: BTC, ETH, LTC, DOGE, BCH, XRP, ADA, DOT, XLM, XMR)
- **Portfolio personal con PnL**: historial de trades BUY/SELL, posiciones LONG y SHORT abiertas, cálculo de PnL por posición y global
- **Posiciones SHORT nativas**: SELL sin compra previa genera posición en descubierto con PnL invertido (gana cuando el precio baja)
- **KPIs diferenciados LONG/SHORT**: en el resumen del portfolio se muestra capital LONG invertido y exposición SHORT por separado
- **Badges visuales LONG/SHORT**: cada posición muestra un badge verde (LONG) o naranja (SHORT) con sublabels contextuales
- **Sistema de alertas**: crear, listar y eliminar alertas de precio por activo con condición ABOVE/BELOW

### Funcionalidades pendientes (roadmap)
- Historial de análisis ejecutados por usuario
- Notificaciones push/email cuando se dispara una alerta

---

## 2. STACK TECNOLÓGICO COMPLETO

### Backend (Python/Django)
| Paquete | Versión | Propósito |
|---|---|---|
| Python | 3.11 | Lenguaje del servidor |
| Django | 5.0.6 | Framework web principal |
| Django REST Framework (DRF) | 3.15.2 | API REST: serialización, views, permisos |
| djangorestframework-simplejwt | 5.3.1 | Autenticación JWT (access 60min, refresh 7 días) |
| rest_framework_simplejwt.token_blacklist | incluido | Blacklist de refresh tokens para logout seguro |
| django-cors-headers | 4.4.0 | CORS para comunicación cross-origin con el frontend |
| psycopg2-binary | 2.9.9 | Driver PostgreSQL para Django |
| pyotp | 2.9.0 | Generación y verificación TOTP (RFC 6238) |
| qrcode | 7.4.2 | Generación de QR codes PNG/base64 para setup 2FA |
| Pillow | 10.4.0 | Dependencia de qrcode para renderizado de imágenes |
| python-dotenv | 1.0.1 | Carga de variables de entorno desde .env |
| gunicorn | 22.0.0 | Servidor WSGI para producción |
| requests | 2.32.3 | Cliente HTTP para APIs externas (Binance, CoinGecko, Alternative.me) |
| ta | 0.11.0 | Librería de indicadores de análisis técnico (RSI, MACD, Bollinger, etc.) |
| scikit-learn | 1.5.1 | Machine Learning — Random Forest para predicción de precio |
| pandas | 2.2.2 | DataFrames para procesamiento de datos OHLCV |
| numpy | 1.26.4 | Operaciones numéricas (dependencia de pandas y scikit-learn) |
| pytest | 8.2.2 | Framework de testing |
| pytest-django | 4.8.0 | Integración pytest con Django |

### Frontend (React/TypeScript)
| Paquete | Versión | Propósito |
|---|---|---|
| React | 18.3.1 | Framework UI (SPA) |
| TypeScript | 5.5.3 | Tipado estático sobre JavaScript |
| Vite | 5.3.4 | Bundler y dev server ultra-rápido |
| react-router-dom | 6.24.0 | Enrutamiento SPA con rutas protegidas |
| Axios | 1.7.2 | Cliente HTTP con interceptores JWT automáticos |
| TailwindCSS | 3.4.6 | Framework CSS utility-first |
| KLineChart | 9.x | Gráficos financieros de velas profesionales: 15 herramientas de dibujo built-in, 20+ indicadores técnicos toggleables, tema oscuro configurable, redimensionable |

### Infraestructura
| Componente | Versión | Propósito |
|---|---|---|
| Docker | - | Contenedorización de servicios |
| Docker Compose v2 | - | Orquestación multi-contenedor |
| PostgreSQL | 16-alpine | Base de datos relacional |
| pgAdmin4 | latest | Interfaz web de administración de BD |
| nginx | alpine | Servidor estático frontend en producción |

---

## 3. ARQUITECTURA DEL SISTEMA — VISIÓN GLOBAL

El sistema está compuesto por tres capas de despliegue separadas que se comunican entre sí:

```
┌─────────────────────────────────────────────────────────────────┐
│  NAVEGADOR DEL USUARIO                                          │
│  http://localhost:5173                                          │
│  React SPA (Vite dev server)                                    │
└───────────────────────┬─────────────────────────────────────────┘
                        │ HTTP/JSON (Axios + JWT Bearer token)
                        │ Proxy /api/* → backend:8000
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  BACKEND — Django + DRF                                         │
│  http://localhost:8000                                          │
│  Contenedor Docker: cryptoworld_backend                         │
│  Clean Architecture (4 capas)                                   │
└───────────────────────┬─────────────────────────────────────────┘
                        │ psycopg2 (SQL)
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  BASE DE DATOS — PostgreSQL 16                                  │
│  puerto 5432                                                    │
│  Contenedor Docker: cryptoworld_db                              │
│  Volumen persistente: postgres_data                             │
└─────────────────────────────────────────────────────────────────┘
```

### Arquitectura del backend: Clean Architecture

El backend implementa **Clean Architecture** (Arquitectura Limpia) de Robert C. Martin. La regla fundamental es: **las dependencias del código solo pueden apuntar hacia adentro**. Las capas internas no saben que las externas existen.

```
┌──────────────────────────────────────────────────────────┐
│  CAPA 4: INTERFACES  (interfaces/api/)                   │
│  views.py  serializers.py  urls.py                       │
│  → Sabe de HTTP. Recibe requests, devuelve responses.    │
│  → Importa de: Application                               │
├──────────────────────────────────────────────────────────┤
│  CAPA 3: INFRAESTRUCTURA  (infrastructure/)              │
│  persistence/models.py   persistence/repositories_impl  │
│  external_apis/  (BinancePublicClient + CoinGeckoClient) │
│  → Sabe de Django ORM, PostgreSQL y APIs externas.        │
│  → Implementa los contratos del Dominio.                 │
├──────────────────────────────────────────────────────────┤
│  CAPA 2: APLICACIÓN  (application/)                      │
│  use_cases/  dto/                                        │
│  → Orquesta el dominio para cumplir una tarea.           │
│  → No sabe de HTTP ni de base de datos.                  │
│  → Solo importa de: Domain                               │
├──────────────────────────────────────────────────────────┤
│  CAPA 1: DOMINIO  (domain/)  ← NÚCLEO                    │
│  entities/  repositories/  services/  value_objects/     │
│  → Python puro. Cero dependencias externas.              │
│  → Contiene las reglas de negocio.                       │
└──────────────────────────────────────────────────────────┘
```

**Regla de dependencia aplicada:**
- `domain/` no importa nada del proyecto (solo stdlib de Python)
- `application/` solo importa de `domain/`
- `infrastructure/` implementa interfaces de `domain/`, usa Django ORM
- `interfaces/` llama a `application/`, instancia `infrastructure/`

---

## 4. BACKEND: CLEAN ARCHITECTURE EN DETALLE

### 4.1 CAPA DE DOMINIO — `backend/src/core/domain/`

El dominio es el núcleo del sistema. Contiene las reglas de negocio en Python puro, sin ninguna dependencia externa. Si Django desapareciera o se cambiara por FastAPI, el dominio quedaría intacto.

**Estructura del directorio:**
```
domain/
├── entities/
│   ├── user.py                  ← Entidad Usuario
│   └── crypto_asset.py          ← Entidades CryptoAsset, MarketDataSnapshot, AnalysisExecution
├── repositories/
│   ├── user_repository.py       ← Interfaz IUserRepository (contrato abstracto)
│   └── crypto_asset_repository.py ← Interfaz ICryptoAssetRepository
├── services/
│   └── user_domain_service.py   ← Servicio de dominio (lógica entre entidades)
└── value_objects/
    ├── email.py                 ← Value Object Email (validación semántica)
    └── crypto_symbol.py         ← Value Object CryptoSymbol
```

#### Entidades del Dominio

Las entidades son clases Python puras (dataclasses) que representan los conceptos del negocio. Contienen sus propias validaciones y operaciones de negocio.

**`domain/entities/user.py` — Entidad Usuario (código real):**
```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class UserEntity:
    email: str
    username: str
    is_active: bool = True
    is_staff: bool = False
    date_joined: datetime = field(default_factory=datetime.utcnow)
    id: Optional[int] = None
    # Campos de autenticación extendida (añadidos en Fase 4)
    is_email_verified: bool = False
    totp_secret: Optional[str] = None
    is_2fa_enabled: bool = False

    def __post_init__(self) -> None:
        """Validaciones de negocio al crear la entidad."""
        if not self.email or "@" not in self.email:
            raise ValueError(f"Email inválido: '{self.email}'")
        if not self.username or len(self.username) < 3:
            raise ValueError("El nombre de usuario debe tener al menos 3 caracteres.")

    def deactivate(self) -> None:
        """Operación de dominio: desactivar cuenta."""
        self.is_active = False

    def promote_to_staff(self) -> None:
        """Operación de dominio: promover a staff."""
        self.is_staff = True
```

**`domain/entities/crypto_asset.py` — Entidades criptográficas (código real):**
```python
from dataclasses import dataclass
from typing import Optional
from decimal import Decimal

@dataclass
class CryptoAssetEntity:
    symbol: str
    name: str
    current_price: Decimal
    market_cap: Optional[Decimal] = None
    volume_24h: Optional[Decimal] = None
    price_change_24h: Optional[Decimal] = None
    coingecko_id: Optional[str] = None      # ID en CoinGecko (p.ej. "bitcoin")
    logo_url: Optional[str] = None           # URL del logo del activo
    asset_address: Optional[str] = None      # Dirección del contrato (tokens ERC-20, etc.)
    decimals: Optional[int] = None           # Decimales del token
    id: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("El símbolo del activo no puede estar vacío.")
        if self.current_price < 0:
            raise ValueError("El precio no puede ser negativo.")
        self.symbol = self.symbol.upper()  # Regla de negocio: siempre mayúsculas

    @property
    def is_bullish_24h(self) -> bool:
        """Regla de negocio: el activo sube si el cambio 24h es positivo."""
        if self.price_change_24h is None:
            return False
        return self.price_change_24h > 0

@dataclass
class MarketDataSnapshotEntity:
    """Instantánea de datos de mercado para análisis histórico."""
    asset_symbol: str
    price: Decimal
    volume: Decimal
    timestamp: str   # ISO 8601
    market_cap: Optional[Decimal] = None
    fully_diluted_valuation: Optional[Decimal] = None
    circulating_supply: Optional[Decimal] = None
    total_supply: Optional[Decimal] = None
    max_supply: Optional[Decimal] = None
    ath: Optional[Decimal] = None              # All-Time High
    atl: Optional[Decimal] = None              # All-Time Low
    ath_date: Optional[str] = None
    atl_date: Optional[str] = None
    price_change_24h_pct: Optional[Decimal] = None
    price_change_7d_pct: Optional[Decimal] = None
    price_change_30d_pct: Optional[Decimal] = None
    id: Optional[int] = None

@dataclass
class PortfolioAssetEntity:
    """Posición de un activo en el portfolio de un usuario."""
    user_id: int
    asset_symbol: str
    quantity: Decimal
    purchase_value_usd: Decimal
    current_value_usd: Optional[Decimal] = None

    @property
    def avg_buy_price_usd(self) -> Decimal:
        if self.quantity == 0:
            return Decimal("0")
        return self.purchase_value_usd / self.quantity

    @property
    def unrealized_pnl_usd(self) -> Optional[Decimal]:
        if self.current_value_usd is None:
            return None
        return self.current_value_usd - self.purchase_value_usd

    @property
    def unrealized_pnl_pct(self) -> Optional[Decimal]:
        if self.current_value_usd is None or self.purchase_value_usd == 0:
            return None
        return ((self.current_value_usd - self.purchase_value_usd) / self.purchase_value_usd) * 100

@dataclass
class AnalysisExecutionEntity:
    """Ejecución de un análisis cuantitativo (RSI, MACD, etc.)."""
    asset_symbol: str
    analysis_type: str          # "RSI", "MACD", "SMA", "BOLLINGER"
    status: str = "pending"     # pending | running | completed | failed
    result: Optional[dict] = None
    id: Optional[int] = None

    def mark_as_running(self) -> None:
        self.status = "running"

    def complete(self, result: dict) -> None:
        self.status = "completed"
        self.result = result
```

#### Repositorios (Contratos/Interfaces del Dominio)

Los repositorios en el dominio son **interfaces abstractas** (no implementaciones). Definen QUÉ operaciones necesita el dominio para gestionar los datos, sin decir CÓMO se hace. La implementación concreta vive en la capa de infraestructura.

**`domain/repositories/user_repository.py` — Contrato (código real):**
```python
from abc import ABC, abstractmethod
from typing import Optional
from core.domain.entities.user import UserEntity

class IUserRepository(ABC):
    @abstractmethod
    def get_by_id(self, user_id: int) -> Optional[UserEntity]: ...

    @abstractmethod
    def get_by_email(self, email: str) -> Optional[UserEntity]: ...

    @abstractmethod
    def save(self, user: UserEntity) -> UserEntity: ...

    @abstractmethod
    def exists_by_email(self, email: str) -> bool: ...

    # Métodos añadidos en Fase 4 (autenticación extendida):
    @abstractmethod
    def set_email_verified(self, user_id: int) -> None: ...

    @abstractmethod
    def set_password(self, user_id: int, raw_password: str) -> None: ...

    @abstractmethod
    def set_totp_secret(self, user_id: int, secret: Optional[str]) -> None: ...

    @abstractmethod
    def set_2fa_enabled(self, user_id: int, enabled: bool) -> None: ...

    @abstractmethod
    def get_model_by_id(self, user_id: int): ...  # Retorna el modelo ORM en casos excepcionales
```

**Por qué existe esta interfaz:** Los casos de uso dependen de `IUserRepository`, no de `DjangoUserRepository`. Esto permite sustituir la implementación (tests usan un repositorio en memoria, producción usa PostgreSQL) sin tocar ni una línea de los casos de uso.

#### Servicio de Dominio

Un servicio de dominio contiene lógica de negocio que involucra consultar repositorios pero no pertenece a ninguna entidad en particular.

**`domain/services/user_domain_service.py` (código real):**
```python
from core.domain.repositories.user_repository import IUserRepository

class UserDomainService:
    def __init__(self, user_repository: IUserRepository) -> None:
        self._user_repo = user_repository  # Inyección de dependencias

    def is_email_available(self, email: str) -> bool:
        return not self._user_repo.exists_by_email(email)

    def ensure_email_available(self, email: str) -> None:
        if not self.is_email_available(email):
            raise ValueError(f"El email '{email}' ya está registrado en el sistema.")
```

**Por qué no está en la entidad:** `UserEntity` no tiene acceso al repositorio. No puede saber si un email ya existe en la base de datos. Esa lógica necesita consultar persistencia, por eso vive en el servicio de dominio.

---

### 4.2 CAPA DE APLICACIÓN — `backend/src/core/application/`

La capa de aplicación contiene los **casos de uso** y los **DTOs** (Data Transfer Objects). Cada caso de uso representa una acción completa que el sistema puede realizar. No sabe nada de HTTP ni de base de datos — solo orquesta el dominio.

**Estructura:**
```
application/
├── use_cases/
│   ├── register_user.py          ← Registrar nuevo usuario
│   ├── logout.py                 ← Logout con blacklist del refresh token
│   ├── verify_email.py           ← Confirmar email con token HMAC
│   ├── send_verification_email.py← Enviar email de verificación
│   ├── request_password_reset.py ← Solicitar recuperación de contraseña
│   ├── confirm_password_reset.py ← Aplicar nueva contraseña con token
│   ├── change_password.py        ← Cambiar contraseña (requiere actual)
│   ├── setup_2fa.py              ← Generar secreto TOTP + QR base64
│   ├── enable_2fa.py             ← Activar 2FA con primer código TOTP
│   ├── disable_2fa.py            ← Desactivar 2FA
│   ├── verify_2fa_login.py       ← Segunda fase del login con 2FA
│   ├── get_assets.py             ← Listar activos criptográficos
│   ├── get_asset_ohlcv.py        ← OHLCV con Strategy Pattern (Binance → CoinGecko → 404)
│   ├── ohlcv_fetcher.py          ← Servicio compartido de obtención de DataFrames OHLCV
│   ├── run_analysis.py           ← Calcular un indicador técnico individual (real)
│   ├── get_signals_dashboard.py  ← Panel multi-indicador con veredicto compra/venta/neutral
│   ├── predict_price.py          ← Predicción de dirección de precio con Random Forest (scikit-learn)
│   ├── detect_patterns.py        ← Detección de 12 patrones de velas japonesas (Doji, Hammer, Engulfing, etc.)
│   └── run_backtest.py           ← Backtesting de 5 estrategias (RSI, MACD, Bollinger, SMA, EMA)
└── dto/
    ├── auth_dto.py               ← 13 DTOs de autenticación
    ├── asset_dto.py              ← DTOs de activos y análisis
    └── market_intelligence_dto.py← DTOs de OHLCV (con campo `source`), overview, noticias
```

#### DTOs — Data Transfer Objects

Los DTOs son contenedores de datos inmutables que definen el contrato entre capas. Son `frozen=True` para evitar mutaciones accidentales.

**`application/dto/auth_dto.py` — fragmento (código real):**
```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)  # inmutable: no se puede modificar tras crearse
class RegisterUserInputDTO:
    email: str
    username: str
    password: str

@dataclass(frozen=True)
class LoginInputDTO:
    email: str
    password: str

@dataclass(frozen=True)
class LogoutInputDTO:
    refresh_token: str

@dataclass(frozen=True)
class VerifyEmailInputDTO:
    token: str

@dataclass(frozen=True)
class PasswordResetRequestDTO:
    email: str

@dataclass(frozen=True)
class PasswordResetConfirmDTO:
    uid: str
    token: str
    new_password: str

@dataclass(frozen=True)
class ChangePasswordDTO:
    user_id: int
    current_password: str
    new_password: str

@dataclass(frozen=True)
class Enable2FADTO:
    user_id: int
    totp_code: str

@dataclass(frozen=True)
class Disable2FADTO:
    user_id: int
    totp_code: str

@dataclass(frozen=True)
class Verify2FALoginDTO:
    pre_auth_token: str
    totp_code: str

@dataclass(frozen=True)
class UserOutputDTO:
    id: int
    email: str
    username: str
    is_email_verified: bool
    is_2fa_enabled: bool
```

**Por qué existen los DTOs:** Evitan filtrar objetos internos entre capas. El view no pasa el objeto `request` de Django al caso de uso. Le pasa un DTO limpio. El caso de uso no devuelve la entidad de dominio al view — devuelve un DTO de salida. Cada capa solo conoce el contrato, no la implementación de la vecina.

#### Caso de Uso de Registro (ejemplo completo)

**`application/use_cases/register_user.py` (código real):**
```python
from core.domain.entities.user import UserEntity
from core.domain.repositories.user_repository import IUserRepository
from core.domain.services.user_domain_service import UserDomainService
from core.application.dto.auth_dto import RegisterUserInputDTO, UserOutputDTO

class RegisterUserUseCase:
    def __init__(
        self,
        user_repository: IUserRepository,
        user_domain_service: UserDomainService,
    ) -> None:
        # Inyección de dependencias: recibe INTERFACES, no implementaciones concretas
        self._user_repo = user_repository
        self._user_domain_service = user_domain_service

    def execute(self, input_dto: RegisterUserInputDTO) -> UserOutputDTO:
        # Paso 1: Regla de dominio — email debe ser único
        self._user_domain_service.ensure_email_available(input_dto.email)

        # Paso 2: Crear entidad de dominio (las validaciones son internas)
        user_entity = UserEntity(
            email=input_dto.email,
            username=input_dto.username,
        )

        # Paso 3: Persistir a través del contrato del repositorio
        # La implementación concreta (DjangoUserRepository) se decide fuera
        saved_user = self._user_repo.save(user_entity)

        # Paso 4: Devolver solo datos públicos (nunca la entidad interna)
        return UserOutputDTO(
            id=saved_user.id,
            email=saved_user.email,
            username=saved_user.username,
            is_email_verified=saved_user.is_email_verified,
            is_2fa_enabled=saved_user.is_2fa_enabled,
        )
```

**Qué hace este caso de uso:**
1. Verifica que el email no esté ya registrado (regla de negocio)
2. Crea la entidad `UserEntity` (que valida email y username)
3. Persiste mediante el repositorio abstracto
4. Devuelve un DTO de salida

**Qué NO hace:** no sabe que existe Django, ni HTTP, ni PostgreSQL, ni que hay un endpoint REST.

#### Caso de Uso de Assets

**`application/use_cases/get_assets.py` (código real):**
```python
from typing import List
from core.domain.repositories.crypto_asset_repository import ICryptoAssetRepository
from core.application.dto.asset_dto import CryptoAssetOutputDTO

class GetAssetsUseCase:
    def __init__(self, crypto_asset_repository: ICryptoAssetRepository) -> None:
        self._asset_repo = crypto_asset_repository

    def execute(self) -> List[CryptoAssetOutputDTO]:
        assets = self._asset_repo.get_all()
        return [
            CryptoAssetOutputDTO(
                id=asset.id,
                symbol=asset.symbol,
                name=asset.name,
                current_price=str(asset.current_price),
                market_cap=str(asset.market_cap) if asset.market_cap else None,
                volume_24h=str(asset.volume_24h) if asset.volume_24h else None,
                price_change_24h=str(asset.price_change_24h) if asset.price_change_24h else None,
                is_bullish_24h=asset.is_bullish_24h,
            )
            for asset in assets
        ]
```

#### Caso de Uso de OHLCV — Strategy Pattern (código real)

**`application/use_cases/get_asset_ohlcv.py` — fragmento:**
```python
class OhlcvNotAvailableError(Exception):
    """Ninguna fuente de datos pudo servir OHLCV para el activo."""

class GetAssetOhlcvUseCase:
    """
    Devuelve velas OHLCV para un activo criptográfico.
    Estrategia: Binance → CoinGecko OHLC → error.
    Elimina completamente los datos sintéticos/falsos.
    """

    def execute(self, symbol: str, interval: str, limit: int
    ) -> tuple[list[OhlcvCandleOutputDTO], str]:
        """
        Devuelve (candles, source) donde source es "binance" o "coingecko".
        Lanza OhlcvNotAvailableError si ninguna fuente tiene datos.
        """
        symbol = symbol.upper()

        # ── 1. Intentar Binance ─────────────────────────────────
        candles = self._try_binance(symbol, interval, limit)
        if candles:
            return candles, "binance"

        # ── 2. Fallback CoinGecko OHLC ─────────────────────────
        candles = self._try_coingecko(symbol, interval, limit)
        if candles:
            return candles, "coingecko"

        # ── 3. Ninguna fuente disponible → error honesto ────────
        raise OhlcvNotAvailableError(f"No hay datos OHLCV disponibles para {symbol}.")
```

**Por qué se eliminaron los datos sintéticos:** la versión anterior de este caso de uso tenía un método `_synthetic_fallback()` que generaba velas falsas con precio fijo (`$3.200`) cuando Binance no listaba el par. Tokens como HYPE o BGB (no cotizados en Binance Spot) recibían precios inventados, lo que invalida cualquier análisis técnico posterior. El Strategy Pattern garantiza que solo se devuelven datos reales o se informa explícitamente de la ausencia de datos.

#### Servicio Compartido `ohlcv_fetcher.py`

Para evitar duplicar la misma cadena Binance → CoinGecko en los 5 casos de uso de análisis, se extrajo en un servicio compartido:

**`application/use_cases/ohlcv_fetcher.py` — fragmento:**
```python
class OhlcvFetchResult:
    """Resultado de la obtención de OHLCV con metadatos de fuente."""
    def __init__(self, df: pd.DataFrame, source: str) -> None:
        self.df = df        # DataFrame con columnas [open, high, low, close, volume]
        self.source = source  # "binance" | "coingecko"

def fetch_ohlcv_dataframe(
    symbol: str, interval: str = "1h", limit: int = 300, ...
) -> Optional[OhlcvFetchResult]:
    """
    Obtiene un DataFrame OHLCV. Cadena: Binance → CoinGecko → None.
    Devuelve None si ninguna fuente sirve datos.
    """
```

Los 5 casos de uso de análisis (`run_analysis.py`, `get_signals_dashboard.py`, `predict_price.py`, `detect_patterns.py`, `run_backtest.py`) delegan en `fetch_ohlcv_dataframe()` y propagan el campo `data_source` en su respuesta.

#### Caso de Uso de Análisis Técnico (implementación real)

**`application/use_cases/run_analysis.py` (código real):**
```python
class RunAnalysisUseCase:
    """
    Caso de uso: calcular un indicador técnico individual.
    Usa la cadena Binance → CoinGecko para obtener OHLCV.
    """

    def execute(self, input_dto: AnalysisRequestInputDTO) -> AnalysisOutputDTO:
        symbol = input_dto.asset_symbol.upper()

        result = fetch_ohlcv_dataframe(symbol=symbol, interval=interval, limit=limit)

        if result is None or result.df.empty or len(result.df) < 20:
            return AnalysisOutputDTO(
                id=0, asset_symbol=symbol,
                analysis_type=input_dto.analysis_type,
                status="failed",
                result={"error": "Datos insuficientes o activo no disponible."},
            )

        indicator_result = calculate_indicator(result.df, input_dto.analysis_type)
        indicator_result["data_source"] = result.source  # "binance" | "coingecko"

        return AnalysisOutputDTO(
            id=0, asset_symbol=symbol,
            analysis_type=input_dto.analysis_type,
            status="completed",
            result=indicator_result,
        )
```

**Diferencia clave respecto al stub anterior:** En v2.0.0, `RunAnalysisUseCase.execute()` devolvía inmediatamente `status="pending"` con `result=None`, sin calcular nada. Ahora obtiene datos OHLCV reales, los pasa al `TechnicalAnalysisService` y devuelve el indicador calculado con `status="completed"`. Si la fuente es CoinGecko, el campo `data_source="coingecko"` advierte que el volumen es cero.

---

### 4.3 CAPA DE INFRAESTRUCTURA — `backend/src/core/infrastructure/`

La infraestructura es el puente entre el dominio abstracto y las tecnologías concretas. Implementa los contratos definidos en `domain/repositories/` utilizando Django ORM y PostgreSQL.

**Estructura:**
```
infrastructure/
├── persistence/
│   ├── models.py              ← Modelos Django ORM (5 tablas)
│   └── repositories_impl.py  ← DjangoUserRepository, DjangoCryptoAssetRepository
└── external_apis/
    ├── binance_client.py      ← Cliente Binance Public API (klines OHLCV, sin auth)
    └── coingecko_client.py    ← Cliente CoinGecko API v3 (markets, global, ohlc)
```

#### Modelos ORM — `infrastructure/persistence/models.py`

Los modelos ORM son adaptadores de base de datos. NO contienen lógica de negocio. Esa lógica vive en las entidades del dominio.

**Modelo User (código real):**
```python
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

class UserManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra_fields):
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)  # Django hashea automáticamente con PBKDF2
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, username, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, db_index=True)
    username = models.CharField(max_length=150, unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    # Campos añadidos en Fase 4 — migración 0002
    is_email_verified = models.BooleanField(default=False)
    totp_secret = models.CharField(max_length=64, null=True, blank=True)
    is_2fa_enabled = models.BooleanField(default=False)

    objects = UserManager()
    USERNAME_FIELD = "email"      # Login por email, no por username
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"

class CryptoAsset(models.Model):
    symbol = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    current_price = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    market_cap = models.DecimalField(max_digits=30, decimal_places=2, null=True, blank=True)
    volume_24h = models.DecimalField(max_digits=30, decimal_places=2, null=True, blank=True)
    price_change_24h = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    coingecko_id = models.CharField(max_length=100, null=True, blank=True)   # ID en CoinGecko
    logo_url = models.URLField(null=True, blank=True)                        # URL del logo
    asset_address = models.CharField(max_length=255, null=True, blank=True)  # Dirección contrato
    decimals = models.IntegerField(null=True, blank=True)                    # Decimales del token
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crypto_assets"
        ordering = ["symbol"]

class MarketDataSnapshot(models.Model):
    asset = models.ForeignKey(CryptoAsset, on_delete=models.CASCADE, related_name="snapshots")
    price = models.DecimalField(max_digits=20, decimal_places=8)
    volume = models.DecimalField(max_digits=30, decimal_places=2)
    market_cap = models.DecimalField(max_digits=30, decimal_places=2, null=True, blank=True)
    fully_diluted_valuation = models.DecimalField(max_digits=30, decimal_places=2, null=True, blank=True)
    circulating_supply = models.DecimalField(max_digits=30, decimal_places=2, null=True, blank=True)
    total_supply = models.DecimalField(max_digits=30, decimal_places=2, null=True, blank=True)
    max_supply = models.DecimalField(max_digits=30, decimal_places=2, null=True, blank=True)
    ath = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    atl = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    ath_date = models.CharField(max_length=50, null=True, blank=True)
    atl_date = models.CharField(max_length=50, null=True, blank=True)
    price_change_24h_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    price_change_7d_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    price_change_30d_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "market_data_snapshots"

class PortfolioAsset(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="portfolio_assets")
    asset_symbol = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    purchase_value_usd = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    current_value_usd = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "portfolio_assets"
        unique_together = ("user", "asset_symbol")

class AnalysisExecution(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("running", "En ejecución"),
        ("completed", "Completado"),
        ("failed", "Fallido"),
    ]
    asset = models.ForeignKey(CryptoAsset, on_delete=models.CASCADE)
    analysis_type = models.CharField(max_length=50)  # RSI, MACD, etc.
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "analysis_executions"
```

#### Repositorios Implementados

**`infrastructure/persistence/repositories_impl.py` — fragmento (código real):**
```python
from core.domain.repositories.user_repository import IUserRepository
from core.domain.entities.user import UserEntity
from core.infrastructure.persistence.models import User as UserModel

class DjangoUserRepository(IUserRepository):
    """
    Implementa IUserRepository usando Django ORM.
    Traduce entre UserModel (ORM/BD) y UserEntity (dominio).
    """

    def get_by_email(self, email: str) -> Optional[UserEntity]:
        try:
            model = UserModel.objects.get(email=email)
            return self._to_entity(model)
        except UserModel.DoesNotExist:
            return None

    def save(self, user: UserEntity) -> UserEntity:
        if user.id:
            model = UserModel.objects.get(pk=user.id)
            model.email = user.email
            model.username = user.username
            model.is_active = user.is_active
            model.save()
        else:
            model = UserModel.objects.create_user(
                email=user.email,
                username=user.username,
            )
        return self._to_entity(model)

    def exists_by_email(self, email: str) -> bool:
        return UserModel.objects.filter(email=email).exists()

    def set_email_verified(self, user_id: int) -> None:
        UserModel.objects.filter(pk=user_id).update(is_email_verified=True)

    def set_password(self, user_id: int, raw_password: str) -> None:
        model = UserModel.objects.get(pk=user_id)
        model.set_password(raw_password)  # Django hashea (PBKDF2 SHA256)
        model.save()

    def set_totp_secret(self, user_id: int, secret: Optional[str]) -> None:
        UserModel.objects.filter(pk=user_id).update(totp_secret=secret)

    def set_2fa_enabled(self, user_id: int, enabled: bool) -> None:
        UserModel.objects.filter(pk=user_id).update(is_2fa_enabled=enabled)

    def _to_entity(self, model: UserModel) -> UserEntity:
        """Convierte modelo ORM → entidad de dominio."""
        return UserEntity(
            id=model.id,
            email=model.email,
            username=model.username,
            is_active=model.is_active,
            is_staff=model.is_staff,
            date_joined=model.date_joined,
            is_email_verified=model.is_email_verified,
            totp_secret=model.totp_secret,
            is_2fa_enabled=model.is_2fa_enabled,
        )
```

**El patrón clave:** el método `_to_entity` es el traductor entre mundos. La BD devuelve un `UserModel` (objeto Django). El repositorio lo traduce a `UserEntity` (objeto del dominio). Ningún código fuera de `infrastructure/` ve jamás un `UserModel`.

#### El adaptador `core/models.py`

Django autodescubre los modelos de una app buscando `<app_label>.models`. Los modelos viven en `infrastructure/persistence/models.py`, pero Django busca en `core/models.py`. Se creó un adaptador de importación:

**`backend/src/core/models.py` (completo):**
```python
# Este archivo NO contiene lógica. Solo reexporta los modelos de infraestructura
# para que el sistema de apps de Django los registre bajo la etiqueta 'core'.
# Patrón: Adapter Pattern entre Clean Architecture y el mecanismo de Django.
from core.infrastructure.persistence.models import (
    UserManager, User, CryptoAsset,
    MarketDataSnapshot, PortfolioAsset, AnalysisExecution,
)
```

---

### 4.4 CAPA DE INTERFACES — `backend/src/core/interfaces/api/`

La capa de interfaces es la única que sabe que existe HTTP. Recibe peticiones, llama a los casos de uso, y devuelve respuestas JSON.

**Estructura:**
```
interfaces/api/
├── views.py        ← Views DRF: 31 endpoints
├── serializers.py  ← Serializadores DRF: validación y transformación
└── urls.py         ← Definición de rutas URL
```

#### Serializers — `interfaces/api/serializers.py`

Los serializers validan el JSON de entrada y transforman los datos a Python antes de construir los DTOs.

**Fragmento (código real):**
```python
from rest_framework import serializers

class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField(min_length=3, max_length=150)
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, data: dict) -> dict:
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Las contraseñas no coinciden."}
            )
        return data

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

class Enable2FASerializer(serializers.Serializer):
    totp_code = serializers.CharField(min_length=6, max_length=6)

class Verify2FALoginSerializer(serializers.Serializer):
    pre_auth_token = serializers.CharField()
    totp_code = serializers.CharField(min_length=6, max_length=6)

class CryptoAssetSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    symbol = serializers.CharField()
    name = serializers.CharField()
    current_price = serializers.CharField()
    market_cap = serializers.CharField(allow_null=True)
    volume_24h = serializers.CharField(allow_null=True)
    price_change_24h = serializers.CharField(allow_null=True)
    is_bullish_24h = serializers.BooleanField()
```

#### Views — `interfaces/api/views.py`

Cada view es responsable de exactamente una operación HTTP. Sigue el patrón: validar entrada → construir DTO → ejecutar caso de uso → devolver respuesta.

**View de registro (fragmento del código real):**
```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # 1. Validar datos HTTP
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        validated = serializer.validated_data

        # 2. Instanciar dependencias (Inyección de Dependencias manual)
        user_repo = DjangoUserRepository()
        user_domain_service = UserDomainService(user_repo)
        use_case = RegisterUserUseCase(user_repo, user_domain_service)

        try:
            # 3. Construir DTO y ejecutar caso de uso
            input_dto = RegisterUserInputDTO(
                email=validated["email"],
                username=validated["username"],
                password=validated["password"],
            )
            output_dto = use_case.execute(input_dto)

            # 4. Enviar email de verificación (segundo caso de uso)
            send_email_use_case = SendVerificationEmailUseCase(user_repo)
            send_email_use_case.execute(output_dto.id)

            return Response(
                {"id": output_dto.id, "email": output_dto.email, "username": output_dto.username},
                status=status.HTTP_201_CREATED,
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
```

**Patrón de Inyección de Dependencias manual:** En cada view se instancian los repositorios concretos (`DjangoUserRepository`) y se inyectan en los casos de uso. Los casos de uso nunca saben qué implementación concreta reciben — solo ven `IUserRepository`. Esto permite que en los tests se pasen repositorios en memoria (fakes) en lugar de los de Django.

#### URLs — `interfaces/api/urls.py` (código real completo)

```python
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from core.interfaces.api import views

urlpatterns = [
    # Health check
    path("health/", views.HealthCheckView.as_view(), name="health-check"),

    # Auth — Registro, login y sesión
    path("auth/register/", views.RegisterView.as_view(), name="auth-register"),
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", views.MeView.as_view(), name="auth-me"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),

    # Auth — Verificación de email
    path("auth/verify-email/", views.VerifyEmailView.as_view(), name="auth-verify-email"),
    path("auth/verify-email/resend/", views.ResendVerificationEmailView.as_view()),

    # Auth — Recuperación de contraseña
    path("auth/password-reset/", views.PasswordResetRequestView.as_view()),
    path("auth/password-reset/confirm/", views.PasswordResetConfirmView.as_view()),
    path("auth/change-password/", views.ChangePasswordView.as_view()),

    # Auth — Eliminación de cuenta
    path("auth/delete-account/", views.DeleteAccountView.as_view()),

    # Auth — 2FA TOTP
    path("auth/2fa/setup/", views.Setup2FAView.as_view(), name="auth-2fa-setup"),
    path("auth/2fa/enable/", views.Enable2FAView.as_view(), name="auth-2fa-enable"),
    path("auth/2fa/disable/", views.Disable2FAView.as_view(), name="auth-2fa-disable"),
    path("auth/2fa/login/", views.Verify2FALoginView.as_view(), name="auth-2fa-login"),

    # Datos de mercado
    path("assets/", views.AssetListView.as_view(), name="asset-list"),
    path("assets/<str:symbol>/ohlcv/", views.AssetOhlcvView.as_view(), name="asset-ohlcv"),
    path("market/overview/", views.MarketOverviewView.as_view(), name="market-overview"),
    path("blockchain/metrics/", views.OnChainMetricsView.as_view(), name="blockchain-metrics"),
    path("news/", views.NewsFeedView.as_view(), name="news-feed"),

    # Análisis técnico
    path("analysis/run/", views.RunAnalysisView.as_view(), name="analysis-run"),
    path("analysis/calculate/", views.CalculateIndicatorView.as_view(), name="analysis-calculate"),
    path("analysis/signals/", views.SignalsDashboardView.as_view(), name="analysis-signals"),
    path("analysis/predict/", views.PredictPriceView.as_view(), name="analysis-predict"),
    path("analysis/patterns/", views.DetectPatternsView.as_view(), name="analysis-patterns"),
    path("analysis/backtest/", views.RunBacktestView.as_view(), name="analysis-backtest"),
    path("analysis/strategies/", views.AvailableStrategiesView.as_view(), name="analysis-strategies"),

    # Administración
    path("admin/users/", views.AdminUserListView.as_view(), name="admin-users"),
    path("admin/users/<int:user_id>/", views.AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("admin/market/sync/", views.AdminMarketSyncView.as_view(), name="admin-market-sync"),
]
```

---

### 4.5 FLUJO COMPLETO DE UNA PETICIÓN HTTP

Cómo viaja una petición de registro a través de todas las capas:

```
1. Browser → POST /api/auth/register/ con JSON:
   { "email": "u@e.com", "username": "user", "password": "pass123", "password_confirm": "pass123" }

2. INTERFACES (views.py — RegisterView.post):
   ├── RegisterSerializer valida el JSON (email válido, min_length, passwords iguales)
   ├── Se instancia DjangoUserRepository() y UserDomainService(repo)
   ├── Se construye RegisterUserInputDTO(email, username, password)
   └── Se llama a RegisterUserUseCase(repo, service).execute(dto)

3. APLICACIÓN (register_user.py — RegisterUserUseCase.execute):
   ├── UserDomainService.ensure_email_available(email)
   │   └── IUserRepository.exists_by_email(email) → False (no existe)
   ├── UserEntity(email="u@e.com", username="user")
   │   └── __post_init__ valida: "@" en email ✓, len(username) >= 3 ✓
   └── IUserRepository.save(user_entity) → UserEntity con id=1

4. INFRAESTRUCTURA (repositories_impl.py — DjangoUserRepository.save):
   ├── UserModel.objects.create_user(email, username) → INSERT INTO users...
   └── _to_entity(model) → UserEntity(id=1, email="u@e.com", ...)

5. APLICACIÓN (vuelta): devuelve UserOutputDTO(id=1, email="u@e.com", ...)

6. INTERFACES (vuelta): envía email de verificación, devuelve HTTP 201:
   { "id": 1, "email": "u@e.com", "username": "user" }

7. Browser recibe: HTTP 201 Created
```

---

## 5. SISTEMA DE AUTENTICACIÓN Y SEGURIDAD

### 5.1 JWT — Tokens de Acceso y Refresco

Se usa **JSON Web Tokens (JWT)** gestionados por `djangorestframework-simplejwt`.

**Configuración relevante del `settings.py`:**
```python
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),   # Expira en 1 hora
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),       # Expira en 7 días
    "ROTATE_REFRESH_TOKENS": True,                    # Nuevo refresh en cada uso
    "BLACKLIST_AFTER_ROTATION": True,                 # El anterior queda invalidado
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}
```

**Flujo de autenticación estándar (sin 2FA):**
```
1. POST /api/auth/login/ → { access_token, refresh_token }
2. Peticiones autenticadas: Authorization: Bearer <access_token>
3. Cuando access_token expira: POST /api/auth/token/refresh/ → { access }
4. POST /api/auth/logout/ con { refresh_token } → token añadido a blacklist
```

**Logout seguro:** El `refresh_token` se añade a la tabla `token_blacklist_blacklistedtoken` de PostgreSQL. Aunque alguien tuviera el token, SimpleJWT lo rechazaría al intentar usarlo. No se depende solo de que el cliente lo elimine.

**Protección por defecto in DRF `settings.py`:**
```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}
```
Todos los endpoints requieren JWT por defecto. Los públicos sobreescriben con `permission_classes = [AllowAny]`.

### 5.2 Verificación de Email

**Mecanismo:** tokens firmados con `django.contrib.auth.tokens.default_token_generator`.

**Ventaja de seguridad clave:** el token incluye el hash de la contraseña actual del usuario como parte de su firma HMAC. Si el usuario cambia su contraseña, todos los tokens de verificación emitidos anteriormente quedan automáticamente invalidados.

**Flujo:**
```
1. POST /api/auth/register/ → caso de uso SendVerificationEmailUseCase ejecutado automáticamente
2. Django genera token: base64(uid) + ":" + HMAC(uid, password_hash, timestamp)
3. Email enviado con: {FRONTEND_URL}/verify-email/?uid=xxx&token=yyy
4. GET /api/auth/verify-email/?uid=xxx&token=yyy
5. VerifyEmailUseCase valida el token y llama a repo.set_email_verified(user_id)
6. Usuario queda con is_email_verified=True
```

**En desarrollo:** `EMAIL_BACKEND = console.EmailBackend` imprime el email completo (con el link) en los logs de Docker, sin necesitar un servidor SMTP real.

### 5.3 Recuperación de Contraseña

**Mismo mecanismo de token HMAC.** Flujo de dos pasos:

```
1. POST /api/auth/password-reset/ { "email": "u@e.com" }
   → Siempre responde HTTP 200 (no revela si el email existe → anti-enumeración)
   → Si existe: envía email con link de recuperación

2. POST /api/auth/password-reset/confirm/ { uid, token, new_password, new_password_confirm }
   → ConfirmPasswordResetUseCase valida token + aplica nueva contraseña hasheada
```

**Seguridad:** la respuesta idéntica en ambos casos (email existente o no) previene ataques de enumeración de usuarios, una vulnerabilidad común en OWASP Top 10.

### 5.4 Autenticación de Doble Factor (2FA TOTP)

Se implementa **TOTP (Time-based One-Time Password)** según RFC 6238, usando la librería `pyotp`. Compatible con Google Authenticator, Authy, Bitwarden y cualquier app autenticadora estándar.

**Por qué TOTP y no SMS:**
- No depende de proveedores externos (sin Twilio/AWS SNS)
- Inmune a SIM-swapping
- Estándar abierto, sin coste por mensaje
- Funciona offline en el dispositivo del usuario

**Flujo completo de setup:**
```
1. POST /api/auth/2fa/setup/   (requiree autenticación)
   Setup2FAUseCase:
   ├── pyotp.random_base32() → genera secreto TOTP único
   ├── Guarda en repo.set_totp_secret(user_id, secret)
   ├── pyotp.totp.TOTP(secret).provisioning_uri(email, issuer="CryptoWorld")
   ├── qrcode → genera QR PNG → base64
   └── { totp_secret: "BASE32SECRETXXX", qr_code_base64: "data:image/png;base64,..." }

2. (usuario escanea QR con Google Authenticator)

3. POST /api/auth/2fa/enable/ { "totp_code": "123456" }
   Enable2FAUseCase:
   ├── Lee totp_secret del repositorio
   ├── pyotp.TOTP(secret).verify(totp_code) → True/False
   ├── Si válido: repo.set_2fa_enabled(user_id, True)
   └── { message: "2FA activado correctamente." }
```

**Flujo de login con 2FA activo — diseño en dos pasos:**

El login con 2FA requiere dos peticiones HTTP separadas. El problema de estado: "¿cómo saber que el usuario del paso 2 es el mismo que validó la contraseña en el paso 1?" sin sesiones en servidor.

**Solución: token JWT especial de pre-autenticación:**
```python
class PreAuthToken:
    """JWT de vida corta que prueba que el usuario validó su contraseña."""
    token_type = "pre_2fa"
    lifetime = timedelta(minutes=5)  # Solo 5 minutos para completar el 2FA
```

```
Paso 1:
POST /api/auth/login/ { email, password }
→ Django autentica credenciales
→ Detecta is_2fa_enabled=True
→ { "requires_2fa": true, "pre_auth_token": "eyJ... (type=pre_2fa, exp=5min)" }
→ NO se emiten access_token ni refresh_token todavía

Paso 2 (dentro de 5 minutos):
POST /api/auth/2fa/login/ { pre_auth_token, totp_code }
→ Verify2FALoginUseCase:
   ├── Decodifica pre_auth_token, verifica type="pre_2fa"
   ├── Extrae user_id del token
   ├── Lee totp_secret del repositorio
   ├── pyotp.TOTP(secret).verify(totp_code, valid_window=1) → True
   └── Emite access_token + refresh_token completos
→ { access_token: "eyJ...", refresh_token: "eyJ..." }

Si el usuario no tiene 2FA activo:
POST /api/auth/login/ → { requires_2fa: false, access_token, refresh_token }  (directo)
```

**Desactivación 2FA:**
```
POST /api/auth/2fa/disable/ { "totp_code": "123456" }
→ Verifica el código TOTP antes de desactivar (requiere prueba de posesión)
→ repo.set_2fa_enabled(user_id, False)
→ repo.set_totp_secret(user_id, None)  # Borra el secreto
```

---

## 6. INFRAESTRUCTURA DOCKER Y DESPLIEGUE

El sistema completo corre en **6 contenedores Docker** orquestados con Docker Compose v2 (PostgreSQL, Redis, backend Django, Celery worker, Celery beat, y frontend Nginx).

**Servicios activos:**
| Contenedor | Imagen/Build | Puerto | Rol |
|---|---|---|---|
| `cryptoworld_db` | postgres:16-alpine | 5432 | Base de datos PostgreSQL |
| `cryptoworld_redis` | redis:7-alpine | — (interno) | Broker de mensajes para Celery |
| `cryptoworld_backend` | backend/Dockerfile | 8000 | API Django 5.0.6 + DRF |
| `cryptoworld_celery` | backend/Dockerfile | — | Worker Celery (tareas async) |
| `cryptoworld_beat` | backend/Dockerfile | — | Celery Beat (tareas periódicas) |
| `cryptoworld_frontend` | frontend/Dockerfile | 5173 | SPA React compilada, servida por Nginx |
| `cryptoworld_pgadmin` | dpage/pgadmin4 | 5050 | Herramienta de administración de BD |

**`docker-compose.yml` — estructura completa:**
```yaml
services:

  postgres:
    image: postgres:16-alpine
    container_name: cryptoworld_db
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${DB_NAME:-cryptoworld_db}
      POSTGRES_USER: ${DB_USER:-postgres}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-postgres}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-postgres}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: cryptoworld_redis
    restart: unless-stopped

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: cryptoworld_backend
    restart: unless-stopped
    env_file: .env
    environment:
      DJANGO_SETTINGS_MODULE: config.settings
      DB_HOST: postgres
    ports:
      - "8000:8000"
    volumes:
      - ./backend/src:/app/src
      - ./backend/tests:/app/tests
      - ./backend/pytest.ini:/app/pytest.ini
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    command: >
      sh -c "
        cd src &&
        python manage.py migrate --noinput &&
        python manage.py runserver 0.0.0.0:8000
      "

  celery:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: cryptoworld_celery
    restart: unless-stopped
    env_file: .env
    environment:
      DJANGO_SETTINGS_MODULE: config.settings
      DB_HOST: postgres
    volumes:
      - ./backend/src:/app/src
    depends_on:
      - backend
      - redis
    command: >
      sh -c "cd src && celery -A config worker --loglevel=info"

  beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: cryptoworld_beat
    restart: unless-stopped
    env_file: .env
    environment:
      DJANGO_SETTINGS_MODULE: config.settings
      DB_HOST: postgres
    volumes:
      - ./backend/src:/app/src
    depends_on:
      - backend
      - redis
    command: >
      sh -c "cd src && celery -A config beat --loglevel=info"

  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: cryptoworld_pgadmin
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@admin.com
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: cryptoworld_frontend
    ports:
      - "5173:5173"

volumes:
  postgres_data:
```

**Puntos clave del diseño Docker:**
- `depends_on: condition: service_healthy` garantiza que Django no arranca antes de que PostgreSQL esté listo y aceptando conexiones
- Los volúmenes montados (`./backend/src:/app/src`) permiten hot-reload en desarrollo sin reconstruir la imagen
- El frontend se compila en tiempo de build (Vite build) y es servido por **Nginx** como bundle estático. Cualquier cambio en `.tsx`/`.ts` requiere `docker compose build frontend` + recrear el contenedor.
- Variables de entorno en `.env` (no en el repositorio): `SECRET_KEY`, `DB_PASSWORD`, `CELERY_BROKER_URL`, etc.
- El comando de arranque del backend ejecuta `migrate` automáticamente en cada inicio
- Redis actúa como broker de Celery (`CELERY_BROKER_URL=redis://redis:6379/0`); los workers y el beat se conectan a él para recibir y planificar tareas

**Variables de entorno (`.env.example`):**
```env
DJANGO_SECRET_KEY=tu-clave-secreta-aqui
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost 127.0.0.1
DB_NAME=cryptoworld_db
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=postgres
DB_PORT=5432
CORS_ALLOWED_ORIGINS=http://localhost:5173 http://127.0.0.1:5173
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
FRONTEND_URL=http://localhost:5173
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
CRYPTOCOMPARE_API_KEY=optional_key_here
COINGECKO_API_KEY=optional_key_here
```

---

## 7. FRONTEND: ARQUITECTURA REACT SPA

### Estructura de capas del frontend

```
Browser
  └── React SPA
        ├── Routing (react-router-dom v6)
        │     ├── Rutas públicas: /login, /register, /auth/verify-email
        │     ├── Rutas protegidas: /dashboard, /market, /analysis, /assets/:symbol, /security/2fa, /settings
        │     │     ├── Guard: ProtectedRoute (comprueba JWT)
        │     │     └── Guard: AdminRoute (comprueba is_staff)
        │     └── Rutas placeholder: /blockchain, /portfolio, /news, /alerts
        ├── Estado global de autenticación
        │     └── AuthContext + useAuth hook (React Context API)
        ├── Páginas (pages/)
        │     ├── LoginPage.tsx / RegisterPage.tsx / VerifyEmailPage.tsx
        │     ├── DashboardPage.tsx (overview + tabla de activos)
        │     ├── MarketPage.tsx (tabla completa con búsqueda, ordenación, paginación)
        │     ├── TechnicalAnalysisPage.tsx (panel multi-indicador)
        │     ├── AssetDetailPage.tsx (gráfico OHLCV + panel de análisis)
        │     ├── Security2FAPage.tsx / SettingsPage.tsx
        │     ├── AdminDashboardPage.tsx (gestión usuarios + sync mercado)
        │     └── PrototypePlaceholderPage.tsx (funcionalidades pendientes)
        ├── Capa de servicios (services/)
        │     ├── api.ts             ← Instancia Axios centralizada
        │     ├── authService.ts     ← Llamadas HTTP de auth
        │     ├── analysisService.ts ← Llamadas HTTP de análisis técnico
        │     └── marketService.ts   ← Llamadas HTTP de mercado (OHLCV, overview)
        └── Componentes compartidos (components/)
              ├── Navbar.tsx / AppShell.tsx / TickerBar.tsx
              ├── OhlcvChart.tsx (KLineChart v9)
              ├── AnalysisPanel.tsx
              ├── ProtectedRoute.tsx
              └── AdminRoute.tsx
```

### `services/api.ts` — Instancia Axios centralizada (código real)

```typescript
import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

const TOKEN_KEY = 'cw_access_token'

const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '/api',
  timeout: 10_000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
})

// Interceptor de petición: inyecta JWT en cada request automáticamente
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
)

// Interceptor de respuesta: maneja 401 globalmente (limpia sesión y recarga)
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem('cw_user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export default apiClient
```

**Por qué es importante:** ningún componente ni servicio crea su propia instancia de Axios. Todos importan `apiClient`. Esto garantiza que el header JWT siempre se inyecta y que el 401 siempre limpia la sesión, sin duplicar lógica.

### `hooks/useAuth.ts` — Autenticación con React Context (código real)

```typescript
import React, { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { authService } from '@/services/authService'

export interface AuthUser {
  id: number
  email: string
  username: string
}

interface AuthContextType {
  user: AuthUser | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

const TOKEN_KEY = 'cw_access_token'
const USER_KEY = 'cw_user'

export function AuthProvider({ children }: { children: ReactNode }) {
  // Estado restaurado desde localStorage al recargar la página
  const [user, setUser] = useState<AuthUser | null>(() => {
    const stored = localStorage.getItem(USER_KEY)
    return stored ? (JSON.parse(stored) as AuthUser) : null
  })
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem(TOKEN_KEY)
  )
  const [isLoading, setIsLoading] = useState(false)

  const login = useCallback(async (email: string, password: string) => {
    setIsLoading(true)
    try {
      const response = await authService.login({ email, password })
      setToken(response.access_token)
      const authUser: AuthUser = {
        id: response.user_id,
        email: response.email,
        username: response.username,
      }
      setUser(authUser)
      localStorage.setItem(TOKEN_KEY, response.access_token)
      localStorage.setItem(USER_KEY, JSON.stringify(authUser))
    } finally {
      setIsLoading(false)
    }
  }, [])

  const logout = useCallback(() => {
    setUser(null)
    setToken(null)
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }, [])

  return React.createElement(
    AuthContext.Provider,
    {
      value: {
        user, token,
        isAuthenticated: !!token,
        isLoading, login, logout,
      }
    },
    children
  )
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
```

**Nota técnica importante:** El archivo usa `React.createElement()` en lugar de JSX (`<AuthContext.Provider>`) porque tiene extensión `.ts` (no `.tsx`). JSX solo puede usarse en archivos `.tsx`.

### `components/ProtectedRoute.tsx` — Guard de autenticación (código real)

```typescript
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'

function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="text-slate-400 text-sm animate-pulse">Cargando...</div>
      </div>
    )
  }

  if (!isAuthenticated) {
    // Guarda la ruta intentada para redirigir después del login
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <Outlet />  // Renderiza las rutas hijas si está autenticado
}
```

### `routes.tsx` — Sistema de rutas (código real)

```typescript
import { Routes, Route, Navigate } from 'react-router-dom'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import VerifyEmailPage from '@/pages/VerifyEmailPage'
import DashboardPage from '@/pages/DashboardPage'
import MarketPage from '@/pages/MarketPage'
import TechnicalAnalysisPage from '@/pages/TechnicalAnalysisPage'
import AssetDetailPage from '@/pages/AssetDetailPage'
import Security2FAPage from '@/pages/Security2FAPage'
import SettingsPage from '@/pages/SettingsPage'
import AdminDashboardPage from '@/pages/AdminDashboardPage'
import PrototypePlaceholderPage from '@/pages/PrototypePlaceholderPage'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminRoute from '@/components/AdminRoute'
import AppShell from '@/components/AppShell'

function AppRoutes() {
  return (
    <Routes>
      {/* Rutas públicas */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/auth/verify-email" element={<VerifyEmailPage />} />

      {/* Rutas protegidas: el guard comprueba JWT antes de renderizar */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/market" element={<MarketPage />} />
          <Route path="/analysis" element={<TechnicalAnalysisPage />} />
          <Route path="/blockchain" element={<PrototypePlaceholderPage />} />
          <Route path="/portfolio" element={<PrototypePlaceholderPage />} />
          <Route path="/news" element={<PrototypePlaceholderPage />} />
          <Route path="/alerts" element={<PrototypePlaceholderPage />} />
          <Route path="/security/2fa" element={<Security2FAPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/assets/:symbol" element={<AssetDetailPage />} />

          {/* Ruta de administración (requiere is_staff) */}
          <Route element={<AdminRoute />}>
            <Route path="/admin" element={<AdminDashboardPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
```

### `services/authService.ts` — Capa de servicio de autenticación (código real)

```typescript
import apiClient from './api'

export interface LoginPayload { email: string; password: string }
export interface RegisterPayload {
  email: string; username: string;
  password: string; password_confirm: string
}
export interface AuthResponse {
  access_token: string; refresh_token: string;
  user_id: number; email: string; username: string
}

export const authService = {
  async login(payload: LoginPayload): Promise<AuthResponse> {
    const { data } = await apiClient.post<AuthResponse>('/auth/login/', payload)
    return data
  },
  async register(payload: RegisterPayload): Promise<RegisterResponse> {
    const { data } = await apiClient.post<RegisterResponse>('/auth/register/', payload)
    return data
  },
  async refreshToken(refreshToken: string): Promise<{ access: string }> {
    const { data } = await apiClient.post('/auth/token/refresh/', { refresh: refreshToken })
    return data
  },
}
```

**Patrón Service Layer del frontend:** Los componentes y hooks no hacen llamadas HTTP directas. Delegan en servicios. Los servicios usan `apiClient`. Esto permite testear componentes mockeando el servicio, no Axios.

---

## 8. SISTEMA DE TESTS

El proyecto tiene dos niveles de tests implementados con pytest y pytest-django.

### Configuración (pytest.ini)

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
pythonpath = src
markers =
    unit: Tests unitarios (sin base de datos)
    integration: Tests de integración (requieren base de datos)
```

### Fixtures compartidas — `tests/conftest.py` (código real)

```python
import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

User = get_user_model()

@pytest.fixture
def api_client():
    """Cliente HTTP de DRF para tests de la API."""
    return APIClient()

@pytest.fixture
def test_user(db):
    """Usuario precreado en la BD de test."""
    return User.objects.create_user(
        email="test@example.com",
        username="testuser",
        password="testpass123",
    )

@pytest.fixture
def authenticated_client(api_client, test_user):
    """Cliente HTTP con JWT ya configurado."""
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(test_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client
```

### Tests Unitarios — `tests/unit/test_domain_entities.py` (código real)

```python
import pytest
from decimal import Decimal
from core.domain.entities.user import UserEntity
from core.domain.entities.crypto_asset import CryptoAssetEntity
from core.domain.value_objects.email import Email, CryptoSymbol

class TestUserEntity:
    @pytest.mark.unit
    def test_create_valid_user(self):
        user = UserEntity(email="user@example.com", username="testuser")
        assert user.email == "user@example.com"
        assert user.is_active is True

    @pytest.mark.unit
    def test_invalid_email_raises_error(self):
        with pytest.raises(ValueError, match="Email inválido"):
            UserEntity(email="not-an-email", username="testuser")

    @pytest.mark.unit
    def test_short_username_raises_error(self):
        with pytest.raises(ValueError, match="al menos 3 caracteres"):
            UserEntity(email="user@example.com", username="ab")

    @pytest.mark.unit
    def test_deactivate_user(self):
        user = UserEntity(email="user@example.com", username="testuser")
        user.deactivate()
        assert user.is_active is False

class TestCryptoAssetEntity:
    @pytest.mark.unit
    def test_symbol_normalized_to_uppercase(self):
        asset = CryptoAssetEntity(symbol="btc", name="Bitcoin", current_price=Decimal("65000"))
        assert asset.symbol == "BTC"

    @pytest.mark.unit
    def test_is_bullish_true_when_positive_change(self):
        asset = CryptoAssetEntity(
            symbol="BTC", name="Bitcoin",
            current_price=Decimal("65000"),
            price_change_24h=Decimal("2.5"),
        )
        assert asset.is_bullish_24h is True

    @pytest.mark.unit
    def test_negative_price_raises_error(self):
        with pytest.raises(ValueError, match="precio no puede ser negativo"):
            CryptoAssetEntity(symbol="BTC", name="Bitcoin", current_price=Decimal("-1"))
```

**Por qué estos tests NO necesitan base de datos:** Las entidades del dominio son Python puro. No heredan de Django ni usan ORM. Pueden instanciarse directamente en memoria. Esto es posible gracias a que el dominio no tiene dependencias externas — es el beneficio directo de Clean Architecture.

### Tests de Integración — `tests/integration/test_api_endpoints.py` (código real)

```python
import pytest

class TestHealthEndpoint:
    @pytest.mark.integration
    def test_health_returns_200(self, api_client):
        response = api_client.get("/api/health/")
        assert response.status_code == 200
        assert response.data["status"] == "ok"

class TestAuthEndpoints:
    @pytest.mark.integration
    def test_register_creates_user(self, api_client, db):
        payload = {
            "email": "new@example.com", "username": "newuser",
            "password": "securepass123", "password_confirm": "securepass123",
        }
        response = api_client.post("/api/auth/register/", payload, format="json")
        assert response.status_code == 201
        assert response.data["email"] == "new@example.com"

    @pytest.mark.integration
    def test_register_fails_with_duplicate_email(self, api_client, test_user):
        payload = {
            "email": "test@example.com",  # Ya existe (fixture test_user)
            "username": "otheruser",
            "password": "securepass123", "password_confirm": "securepass123",
        }
        response = api_client.post("/api/auth/register/", payload, format="json")
        assert response.status_code == 400

    @pytest.mark.integration
    def test_login_returns_tokens(self, api_client, test_user):
        payload = {"email": "test@example.com", "password": "testpass123"}
        response = api_client.post("/api/auth/login/", payload, format="json")
        assert response.status_code == 200
        assert "access_token" in response.data
        assert "refresh_token" in response.data

class TestAssetsEndpoint:
    @pytest.mark.integration
    def test_assets_requires_authentication(self, api_client):
        response = api_client.get("/api/assets/")
        assert response.status_code == 401

    @pytest.mark.integration
    def test_assets_returns_list_when_authenticated(self, authenticated_client):
        response = authenticated_client.get("/api/assets/")
        assert response.status_code == 200
        assert isinstance(response.data, list)
```

**Estado de los tests:** todos los tests implementados pasan correctamente a fecha de marzo 2026.

---

## 9. BASE DE DATOS: MODELO RELACIONAL

**7 tablas principales** en PostgreSQL, más las tablas internas de Django y SimpleJWT:

```
┌─────────────────────────────────────┐
│  users                              │
│  ─────────────────────────────────  │
│  id (PK, BigAutoField)              │
│  email (UNIQUE, INDEX)              │
│  username (UNIQUE)                  │
│  password (hash PBKDF2 SHA256)      │
│  is_active                          │
│  is_staff                           │
│  date_joined                        │
│  is_email_verified   ← migración 02 │
│  totp_secret         ← migración 02 │
│  is_2fa_enabled      ← migración 02 │
└────────────┬────────────────────────┘
             │ 1:N
┌────────────▼────────────────────────┐
│  crypto_assets                      │
│  ─────────────────────────────────  │
│  id (PK)                            │
│  symbol (UNIQUE, INDEX)             │
│  name                               │
│  current_price (Decimal 20,8)       │
│  market_cap (Decimal 30,2)          │
│  volume_24h (Decimal 30,2)          │
│  price_change_24h (Decimal 10,4)    │
│  coingecko_id          ← migración 03│
│  logo_url              ← migración 03│
│  asset_address         ← migración 03│
│  decimals              ← migración 03│
│  created_at, updated_at             │
└────────────┬────────────────────────┘
             │ 1:N
┌────────────▼────────────────────────┐
│  market_data_snapshots              │
│  ─────────────────────────────────  │
│  id (PK)                            │
│  asset_id (FK → crypto_assets)      │
│  price (Decimal 20,8)               │
│  volume (Decimal 30,2)              │
│  market_cap (Decimal 30,2)          │
│  fully_diluted_valuation            │
│  circulating_supply, total_supply   │
│  max_supply                         │
│  ath, atl (Decimal 20,8)            │
│  ath_date, atl_date                 │
│  price_change_24h_pct               │
│  price_change_7d_pct                │
│  price_change_30d_pct               │
│  timestamp                          │
└─────────────────────────────────────┘
┌─────────────────────────────────────┐
│  analysis_executions                │
│  ─────────────────────────────────  │
│  id (PK)                            │
│  asset_id (FK → crypto_assets)      │
│  analysis_type ("RSI","MACD"...)    │
│  status (pending/running/done/fail) │
│  result (JSONField)                 │
│  created_at, updated_at             │
└─────────────────────────────────────┘
┌─────────────────────────────────────┐
│  trade_history         ← migración 04│
│  ─────────────────────────────────  │
│  id (PK)                            │
│  user_id (FK → users)               │
│  asset_symbol                       │
│  trade_type ("BUY" | "SELL")        │
│  quantity (Decimal 20,8)            │
│  price_usd (Decimal 20,8)           │
│  timestamp                          │
│                                     │
│  El motor de portfolio usa esta     │
│  tabla para calcular posiciones     │
│  abiertas LONG/SHORT y PnL.         │
└─────────────────────────────────────┘
┌─────────────────────────────────────┐
│  price_alerts          ← migración 04│
│  ─────────────────────────────────  │
│  id (PK)                            │
│  user_id (FK → users)               │
│  asset_symbol                       │
│  condition ("ABOVE" | "BELOW")      │
│  target_price (Decimal 20,8)        │
│  is_active (Boolean)                │
│  created_at                         │
│                                     │
│  Celery Beat evalúa periódicamente  │
│  alertas activas y notifica.        │
└─────────────────────────────────────┘
```

**Migraciones aplicadas:**
| Archivo | Contenido |
|---|---|
| `core/migrations/0001_initial.py` | Crea las 4 tablas base: users, crypto_assets, market_data_snapshots, analysis_executions |
| `core/migrations/0002_user_auth_fields.py` | Añade is_email_verified, totp_secret, is_2fa_enabled a la tabla users |
| `core/migrations/0003_add_portfolio_and_expand_market_models.py` | Añade coingecko_id, logo_url, asset_address, decimals a crypto_assets; expande market_data_snapshots con métricas de mercado completas |
| `core/migrations/0004_add_trade_history_and_price_alerts.py` | Crea trade_history y price_alerts; elimina portfolio_assets (reemplazada por el motor de trade history) |
| `token_blacklist/*` (12 migraciones) | Tablas OutstandingToken y BlacklistedToken para logout seguro |

---

## 10. DECISIONES DE DISEÑO JUSTIFICADAS

### 10.1 Por qué Clean Architecture

La Clean Architecture permite que el núcleo del sistema (dominio y casos de uso) sea completamente independiente de frameworks, bases de datos e interfaces externas.

**Beneficios concretos demostrados en el proyecto:**
1. **Testabilidad sin base de datos:** `TestUserEntity` y `TestCryptoAssetEntity` prueban reglas de negocio en Python puro, sin Django ni PostgreSQL
2. **Intercambiabilidad:** cambiar de PostgreSQL a MongoDB solo requeriría crear `MongoUserRepository(IUserRepository)` sin tocar ni el dominio ni los casos de uso
3. **Código autoexplicado:** leer `register_user.py` comunica exactamente qué hace el sistema, sin saber nada de HTTP ni SQL

**Principios SOLID aplicados:**
- **SRP:** cada clase tiene una responsabilidad — `UserEntity` (qué es un usuario), `DjangoUserRepository` (cómo persiste), `RegisterUserUseCase` (cómo se registra)
- **OCP:** nuevos casos de uso se añaden sin modificar los existentes
- **DIP:** `RegisterUserUseCase` depende de `IUserRepository` (interfaz), no de `DjangoUserRepository` (implementación concreta)

### 10.2 Por qué AUTH_USER_MODEL personalizado (email como campo principal)

Django usa `username` como campo de autenticación por defecto. Se optó por `email` porque:
- Es el identificador natural en aplicaciones modernas y fintech
- Elimina la necesidad de mantener sincronizados username y email
- Estándar en la industria para aplicaciones de análisis financiero

Implementado mediante `AbstractBaseUser` + `BaseUserManager` personalizado con `USERNAME_FIELD = "email"`.

### 10.3 Por qué JWT en lugar de sesiones Django

Las sesiones Django guardan estado en servidor (BD o cache). JWT es stateless:
- El token viaja en el cliente (localStorage en el frontend)
- El backend no consulta BD para validar cada petición (solo verifica la firma)
- Compatible con arquitecturas API-first y potencialmente aplicaciones móviles

Riesgo mitigado: el logout seguro se garantiza con blacklist del refresh_token en BD, no dependiendo solo del cliente para eliminar tokens válidos.

### 10.4 Por qué `core/models.py` como adaptador de importación

Django necesita que los modelos de una app sean descubribles en `<app_label>.models`. En Clean Architecture, los modelos ORM pertenecen a `infrastructure/persistence/`. La solución es un archivo adaptador de reexportación que satisface el mecanismo de Django sin romper la separación de capas. No contiene lógica, solo importaciones.

### 10.5 Por qué el flujo 2FA en dos pasos con PreAuthToken

El flujo de doble factor requiere dos peticiones HTTP. El problema de estado se resuelve con un JWT especial de corta duración (`type=pre_2fa`, 5 minutos). Mantiene la arquitectura stateless del sistema (sin sesiones en servidor) y expira automáticamente si el usuario abandona el proceso.

### 10.6 Por qué tokens HMAC para verificación de email/contraseña

`django.contrib.auth.tokens.default_token_generator` genera tokens firmados que incluyen el hash de la contraseña del usuario en su firma. Consecuencia de seguridad: si el usuario cambia su contraseña, todos los tokens de verificación/recuperación emitidos anteriormente se invalidan automáticamente sin necesidad de almacenarlos en BD.

### 10.7 Por qué respuesta genérica en `/api/auth/password-reset/`

El endpoint siempre devuelve HTTP 200 independientemente de si el email existe o no. Esto previene ataques de enumeración de usuarios (OWASP A01: Broken Access Control). Un atacante no puede determinar qué emails están registrados en el sistema.

### 10.8 Por qué Strategy Pattern (Binance → CoinGecko) en lugar de un único proveedor

El problema que motivó este cambio es concreto: tokens como HYPE (Hyperliquid) o BGB (Bitget) no cotizan en Binance Spot —el par `HYPEUSDT` o `BGBUSDT` simplemente no existe—, pero sí tienen liquidez real en otros mercados. La versión anterior resolvía esto con un `_synthetic_fallback()` que devolvía velas con precio inventado (`$3.200`), lo que invalidaba silenciosamente cualquier análisis técnico posterior.

Se evaluaron cinco soluciones posibles:
- **A) Solo Binance, sin fallback** — No cubre tokens no listados.
- **B) Solo CoinGecko OHLC** — No incluye volumen, granularidad limitada en plan gratuito.
- **C) Mantener datos sintéticos** — Sin integridad de datos, inadmisible.
- **D) Base de datos propia con ticks** — Infraestructura excesiva para el alcance del TFG.
- **E) Strategy Pattern: Binance → CoinGecko → 404** — Datos reales con transparencia total.

La opción E es la más equilibrada para el contexto del TFG:
- Binance proporciona OHLCV completo (con volumen) sin API key para los ~200 tokens del top de capitalización.
- CoinGecko OHLC cubre prácticamente la totalidad del universo crypto conocido, aunque sin volumen.
- Si ambos fallan, se lanza `OhlcvNotAvailableError` → HTTP 404, que es un error honesto y trazable.
- El campo `source` propagado hasta el frontend informa al usuario de qué proveedor sirvió los datos.

**Consecuencia para los indicadores de volumen:** CoinGecko OHLC no incluye volumen en su respuesta. Se introduce `volume=0` para mantener la estructura del DataFrame, y el frontend desactiva automáticamente los indicadores dependientes del volumen (VOL, OBV, PVT, VR, EMV) cuando `source="coingecko"`, mostrando un aviso visual.

### 10.9 Por qué `ohlcv_fetcher.py` como servicio compartido en lugar de herencia

Los cinco casos de uso de análisis (`run_analysis`, `get_signals_dashboard`, `predict_price`, `detect_patterns`, `run_backtest`) necesitan exactamente la misma lógica de obtención de datos OHLCV. La alternativa de herencia habría creado una jerarquía de clases artificial (`BaseAnalysisUseCase`) que complica la comprensión sin añadir valor semántico.

Se optó por composición mediante una función standalone `fetch_ohlcv_dataframe()` en `ohlcv_fetcher.py`. Es una dependencia explícita, no implícita: cada caso de uso la importa directamente y puede inyectar clientes mock para tests. El resultado `OhlcvFetchResult` encapsula tanto el DataFrame como el metadato de fuente, lo que permite propagar `data_source` hasta la respuesta JSON sin tener que pasarlo como parámetro adicional entre capas.

### 10.10 Por qué KLineChart en lugar de TradingView Lightweight Charts

TradingView Lightweight Charts v4 fue la librería inicial para gráficos financieros. Se migró a KLineChart v9 por las siguientes razones técnicas:

- **Indicadores técnicos built-in**: KLineChart incluye nativamente RSI, MACD, Bollinger, MA, EMA, SAR, KDJ, OBV y 15+ más. Con Lightweight Charts, cada indicador requiere implementación manual en el cliente.
- **Herramientas de dibujo**: KLineChart proporciona 15 overlays vectoriales (tendencias, fibonacci, canales, anotaciones) sin código adicional. Lightweight Charts carece de esta funcionalidad.
- **Gestión de sub-paneles**: KLineChart gestiona automáticamente el layout de sub-paneles para indicadores de sub-gráfico (RSI, MACD), con separadores arrastrables para redimensionar.
- **Modo imán**: KLineChart incluye modo imán (snap a OHLC) y comandos de deshacer, que son funcionalidades esperadas en una herramienta de análisis técnico profesional.
- **Licencia MIT**: KLineChart es MIT, sin restricciones de uso en proyectos educativos o comerciales.

---

## 11. ESTADO ACTUAL Y ROADMAP

### Estado actual — Mayo 2026 (v1.47.0 — Portfolio LONG/SHORT + MultiChain + Noticias + Alertas)

**Servicios Docker activos:**
| Contenedor | Puerto | Estado |
|---|---|---|
| cryptoworld_db (PostgreSQL 16) | 5432 | Running (healthy) |
| cryptoworld_redis (Redis 7) | — (interno) | Running |
| cryptoworld_backend (Django 5.0.6) | 8000 | Running |
| cryptoworld_celery (Celery worker) | — | Running |
| cryptoworld_beat (Celery beat) | — | Running |
| cryptoworld_frontend (React 18 + Nginx) | 5173 | Running |
| cryptoworld_pgadmin | 5050 | Running |

**APIs externas integradas:**
| Proveedor | Endpoint Base | Auth | Límite | Uso en el proyecto |
|---|---|---|---|---|
| Binance Public | `data-api.binance.vision` | Sin API key | ~600 req/min | OHLCV primario (velas con volumen) |
| CoinGecko v3 | `api.coingecko.com/api/v3` | Opcional (demo key) | 30 req/min (free) | Catálogo de activos, métricas globales, OHLC fallback |
| Alternative.me | `api.alternative.me/fng/` | Sin auth | Libre | Fear & Greed Index |
| CryptoCompare | `min-api.cryptocompare.com` | API key opcional | 100k calls/mes (free) | Feed de noticias con categorías y sentimiento |
| Blockchain.com Charts | `api.blockchain.info/charts` | Sin auth | Libre | Métricas on-chain BTC (hashrate, TXs, fees, mempool) |
| Blockchair | `api.blockchair.com/{chain}/stats` | Sin auth | 10 req/min (free) | Estadísticas multi-chain: BTC, ETH, LTC, DOGE, BCH, XRP, ADA, DOT, XLM, XMR |

**Endpoints implementados y validados:**
| Método | Ruta | Auth | Estado | Fuente |
|---|---|---|---|---|
| GET | `/api/health/` | No | ✅ Funcional | — |
| POST | `/api/auth/register/` | No | ✅ Funcional | DB |
| POST | `/api/auth/login/` | No | ✅ Funcional (soporta 2FA) | DB |
| POST | `/api/auth/logout/` | Sí | ✅ Funcional (blacklist) | DB |
| GET | `/api/auth/me/` | Sí | ✅ Funcional | DB |
| POST | `/api/auth/token/refresh/` | No | ✅ Funcional | SimpleJWT |
| GET | `/api/auth/verify-email/` | No | ✅ Funcional | DB + HMAC |
| POST | `/api/auth/verify-email/resend/` | Sí | ✅ Funcional | Email |
| POST | `/api/auth/password-reset/` | No | ✅ Funcional | Email + HMAC |
| POST | `/api/auth/password-reset/confirm/` | No | ✅ Funcional | DB + HMAC |
| POST | `/api/auth/change-password/` | Sí | ✅ Funcional | DB |
| DELETE | `/api/auth/delete-account/` | Sí | ✅ Funcional | DB |
| POST | `/api/auth/2fa/setup/` | Sí | ✅ Funcional | pyotp |
| POST | `/api/auth/2fa/enable/` | Sí | ✅ Funcional | pyotp |
| POST | `/api/auth/2fa/disable/` | Sí | ✅ Funcional | pyotp |
| POST | `/api/auth/2fa/login/` | No | ✅ Funcional | pyotp + JWT |
| GET | `/api/assets/` | Sí | ✅ **Datos reales** | DB (sync CoinGecko) |
| GET | `/api/assets/{symbol}/ohlcv/` | Sí | ✅ **Strategy Pattern** | Binance → CoinGecko → 404 |
| POST | `/api/analysis/run/` | Sí | ✅ **Datos reales** | Binance/CoinGecko + TechnicalAnalysisService |
| POST | `/api/analysis/calculate/` | Sí | ✅ **Datos reales** | Binance/CoinGecko + indicadores |
| GET | `/api/analysis/signals/` | Sí | ✅ **Datos reales** | Binance/CoinGecko (señales multi-indicador) |
| POST | `/api/analysis/predict/` | Sí | ✅ **Datos reales** | Random Forest sobre OHLCV real |
| POST | `/api/analysis/patterns/` | Sí | ✅ **Datos reales** | Detección de 12 patrones de velas japonesas |
| POST | `/api/analysis/backtest/` | Sí | ✅ **Datos reales** | Backtesting de 5 estrategias (RSI, MACD, Bollinger, SMA, EMA) |
| GET | `/api/analysis/strategies/` | Sí | ✅ Funcional | Lista estática |
| GET | `/api/market/overview/` | Sí | ✅ **Datos reales** | CoinGecko /global + Alternative.me |
| GET | `/api/blockchain/metrics/` | Sí | ✅ **Datos reales** | Blockchain.com Charts API (BTC on-chain) |
| GET | `/api/blockchain/multichain/` | Sí | ✅ **Datos reales** | Blockchair (10 blockchains) |
| GET | `/api/news/` | Sí | ✅ **Datos reales** | CryptoCompare News API |
| GET | `/api/portfolio/` | Sí | ✅ Funcional | DB (trade_history) |
| POST | `/api/portfolio/trade/` | Sí | ✅ Funcional | DB |
| DELETE | `/api/portfolio/trade/{id}/` | Sí | ✅ Funcional | DB |
| GET | `/api/alerts/` | Sí | ✅ Funcional | DB |
| POST | `/api/alerts/` | Sí | ✅ Funcional | DB |
| DELETE | `/api/alerts/{id}/` | Sí | ✅ Funcional | DB |
| GET | `/api/admin/users/` | Admin | ✅ Funcional | DB |
| POST | `/api/admin/users/` | Admin | ✅ Funcional | DB |
| PATCH | `/api/admin/users/{id}/` | Admin | ✅ Funcional | DB |
| POST | `/api/admin/market/sync/` | Admin | ✅ **Datos reales** | CoinGecko /coins/markets |

**Capas implementadas:**
| Capa | Estado |
|---|---|
| Domain — Entities (4 entidades) | ✅ Completo |
| Domain — Repository interfaces | ✅ Completo |
| Domain — Value Objects | ✅ Completo |
| Domain — Services (técnico + usuario) | ✅ Completo |
| Application — 35+ casos de uso | ✅ Auth, market, OHLCV (Strategy), análisis técnico, portfolio, alertas, noticias, on-chain |
| Application — DTOs | ✅ Completo (auth, asset, market, portfolio con LONG/SHORT) |
| Infrastructure — ORM Models | ✅ Completo (7 modelos principales, 4 migraciones) |
| Infrastructure — Repositories impl | ✅ Completo |
| Infrastructure — External APIs | ✅ Binance, CoinGecko, Alternative.me, CryptoCompare, Blockchain.com, Blockchair |
| Infrastructure — Celery / Redis | ✅ Completo (worker + beat; tarea de evaluación de alertas) |
| Interfaces — API (38+ endpoints) | ✅ Completo |
| Frontend — Auth flow | ✅ Completo |
| Frontend — Dashboard con datos reales | ✅ Completo (overview + tabla activos + logos) |
| Frontend — Gráfico OHLCV profesional | ✅ KLineChart v9 (15 herramientas, 20+ indicadores, badge fuente) |
| Frontend — Panel de análisis técnico | ✅ Completo (señales, RSI, MACD, predicción, patrones, backtesting) |
| Frontend — Panel Admin con sync | ✅ Completo (feedback de resultados, enlace en azul) |
| Frontend — Portfolio LONG/SHORT | ✅ Completo (KPIs condicionales, badges, sublabels contextuales) |
| Frontend — Alertas | ✅ Completo (crear, listar, eliminar) |
| Frontend — Noticias | ✅ Completo (CryptoCompare, categorías, sentimiento) |
| Frontend — Blockchain on-chain + MultiChain | ✅ Completo (Blockchain.com + selector de 10 chains Blockchair) |
| Tests unitarios | ✅ Implementados y pasando |
| Tests integración | ✅ Implementados y pasando |

### Archivos nuevos y modificados — Fase Celery + Noticias + On-chain + Portfolio + Alertas (v1.30–v1.47)

#### Backend — Infraestructura Celery

| Archivo | Tipo | Descripción |
|---|---|---|
| `config/celery.py` | Nuevo | Configuración de la aplicación Celery, integración con Django |
| `config/settings.py` | Modificado | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_BEAT_SCHEDULE` |
| `core/tasks.py` | Nuevo | Tarea Celery `evaluate_price_alerts()`: evalúa alertas activas contra precio actual y notifica |

#### Backend — APIs externas nuevas

| Archivo | Tipo | Descripción |
|---|---|---|
| `infrastructure/external_apis/cryptocompare_client.py` | Nuevo | Cliente CryptoCompare News API. Método `get_news(categories, lang)` |
| `infrastructure/external_apis/blockchain_charts_client.py` | Nuevo | Cliente Blockchain.com Charts API. Métricas on-chain BTC (hashrate, tx-count, fees, mempool, etc.) |
| `infrastructure/external_apis/blockchair_client.py` | Nuevo | Cliente Blockchair. Método `get_stats(symbol)` → normaliza hashrate H/s→TH/s, burned_24h wei→ETH |

#### Backend — Casos de uso nuevos

| Archivo | Clase | Descripción |
|---|---|---|
| `use_cases/get_news_feed.py` | `GetNewsFeedUseCase` | Obtiene noticias de CryptoCompare; soporta filtro por categoría |
| `use_cases/get_onchain_metrics.py` | `GetOnchainMetricsUseCase` | Obtiene métricas on-chain BTC de Blockchain.com Charts |
| `use_cases/get_multichain_stats.py` | `GetMultiChainStatsUseCase` | Agrega estadísticas de los 10 chains de Blockchair |
| `use_cases/get_portfolio.py` | `GetPortfolioUseCase` | Calcula posiciones abiertas LONG/SHORT y PnL completo desde trade_history |
| `use_cases/add_trade.py` | `AddTradeUseCase` | Registra operación BUY o SELL (SELL sin BUY previo crea posición SHORT) |
| `use_cases/delete_trade.py` | `DeleteTradeUseCase` | Elimina un trade del historial por ID |
| `use_cases/get_alerts.py` | `GetAlertsUseCase` | Lista alertas activas del usuario |
| `use_cases/create_alert.py` | `CreateAlertUseCase` | Crea alerta de precio con condición ABOVE/BELOW |
| `use_cases/delete_alert.py` | `DeleteAlertUseCase` | Elimina una alerta por ID |
| `use_cases/request_password_reset.py` | Modificado | Añade logging de debug para emails en dev |

#### Backend — Modelos ORM (migración 0004)

| Modelo | Tabla | Descripción |
|---|---|---|
| `TradeHistory` | `trade_history` | Registro de cada operación BUY/SELL: usuario, símbolo, tipo, cantidad, precio, timestamp |
| `PriceAlert` | `price_alerts` | Alerta de precio: usuario, símbolo, condición, precio objetivo, is_active |

#### Backend — DTOs modificados

| Archivo | Cambio |
|---|---|
| `dto/portfolio_dto.py` | `PortfolioPositionDTO` gana `position_type: str`. `PortfolioSummaryDTO` gana `long_count`, `short_count`, `total_long_invested_usd`, `total_short_exposure_usd` |
| `dto/alerts_dto.py` | Nuevos DTOs `PriceAlertDTO`, `CreateAlertInputDTO` |

#### Backend — Serializers y vistas modificados

| Archivo | Cambio |
|---|---|
| `interfaces/api/serializers.py` | `PortfolioPositionSerializer` gana campo `position_type` |
| `interfaces/api/views.py` | `PortfolioView` devuelve los 4 nuevos campos del summary; nuevas vistas para blockchain multichain |
| `interfaces/api/urls.py` | Rutas `/portfolio/`, `/portfolio/trade/`, `/alerts/`, `/blockchain/multichain/`, `/news/` |

#### Frontend — Páginas nuevas/modificadas

| Archivo | Cambio |
|---|---|
| `pages/PortfolioPage.tsx` | KPIs condicionales LONG-only vs mixed; badges LONG/SHORT; sublabels contextuales en columnas; "Valor posición" como header |
| `pages/AlertsPage.tsx` | Nueva: crear, listar y eliminar alertas con condición y activo |
| `pages/NewsPage.tsx` | Nueva: feed de noticias CryptoCompare con categorías y sentimiento |
| `pages/BlockchainPage.tsx` | Nuevo panel MultiChain: selector de 10 cadenas + grid de estadísticas Blockchair |
| `components/AppShell.tsx` | Enlace "Panel Admin" cambiado a color azul |
| `components/Navbar.tsx` | Ídem |

#### Frontend — Servicios nuevos/modificados

| Archivo | Cambio |
|---|---|
| `services/portfolioService.ts` | `PortfolioPosition` gana `position_type`; `PortfolioSummary` gana 4 campos nuevos |
| `services/blockchainService.ts` | Interfaz `MultiChainStats` y llamada al endpoint multichain |
| `services/newsService.ts` | Nuevo: interfaz `NewsArticle`, llamada al feed de noticias |
| `services/alertsService.ts` | Nuevo: CRUD de alertas |

### Lógica de portfolio LONG/SHORT (v1.43–v1.47)

El motor de portfolio calcula posiciones abiertas a partir del historial de trades sin almacenar posiciones explícitamente:

```
Para cada símbolo del usuario:
  net_qty = suma(BUY.quantity) - suma(SELL.quantity)

  Si net_qty > 0  →  LONG
    invested   = suma(BUY.quantity * BUY.price)  / BUY.total_qty * net_qty
    current    = net_qty * current_price
    pnl        = current - invested

  Si net_qty < 0  →  SHORT (posición en descubierto)
    short_qty  = abs(net_qty)
    received   = suma(SELL.quantity * SELL.price) sin cobertura
    buyback    = short_qty * current_price        (coste recompra)
    pnl        = received - buyback

  Si net_qty == 0  →  posición cerrada, ignorada
```

**KPIs diferenciados en el resumen del portfolio:**
- Si solo hay posiciones LONG: layout clásico de 4 tarjetas (Capital invertido / Valor actual / PnL USD / PnL %)
- Si hay posiciones LONG y SHORT: tarjeta LONG (borde verde, capital invertido + nº posiciones) + tarjeta SHORT (borde naranja, exposición actual + coste de recompra) + PnL USD + PnL %

### Roadmap de fases futuras

**Completado:**
- ~~Sprint 0.5 — Contratos de datos contract-first~~ ✅
- ~~Sprint 1 — Integración CoinGecko API (sync de catálogo + métricas globales)~~ ✅
- ~~Sprint 1b — Integración Binance API (OHLCV real con volumen)~~ ✅
- ~~Sprint 2 — Análisis técnico real (RSI, MACD, Bollinger, señales, backtesting, predicción)~~ ✅
- ~~Sprint 2b — Strategy Pattern OHLCV (eliminar datos sintéticos, cobertura CoinGecko)~~ ✅
- ~~Sprint 3 — Frontend con gráficos profesionales (KLineChart v9, herramientas de dibujo, badge fuente)~~ ✅
- ~~Sprint 4 — Portfolio personal LONG/SHORT con PnL + Sistema de alertas~~ ✅
- ~~Sprint 5a — Feed de noticias real (CryptoCompare)~~ ✅
- ~~Sprint 5b — Métricas on-chain reales (Blockchain.com Charts + Blockchair MultiChain)~~ ✅
- ~~Sprint 5c — Celery + Redis para tareas asíncronas y evaluación periódica de alertas~~ ✅

**Próximo — Sprint 6: Historial y notificaciones**
- Historial de análisis ejecutados por usuario (persistencia en `analysis_executions`)
- Notificaciones push/email cuando se dispara una alerta de precio

---

## 12. REGISTRO DE PROBLEMAS RESUELTOS

| # | Fase | Síntoma | Causa | Solución |
|---|---|---|---|---|
| 1 | Docker | `error during connect: pipe error` | Docker Desktop no iniciado | Iniciar Docker Desktop |
| 2 | Docker | Warning `version is obsolete` | Campo `version` obsoleto en Compose v2 | Eliminar la línea `version: "3.9"` |
| 3 | Docker Build | `npm ci` falla sin `package-lock.json` | Solo existía `package.json` | Cambiar `npm ci` → `npm install` en `frontend/Dockerfile` |
| 4 | Docker Build | pip timeout a 19.8 kB/s | Red lenta | `--timeout=300 --retries=5` en `backend/Dockerfile` |
| 5 | TypeScript | `TS1005: '>' expected` en `useAuth.ts` | JSX en archivo `.ts` (sin `.tsx`) | Sustituir JSX por `React.createElement()` |
| 6 | TypeScript | `'env' not on ImportMeta` | Falta declaración de tipos Vite | Crear `frontend/src/vite-env.d.ts` con `/// <reference types="vite/client" />` |
| 7 | Django Runtime | `AUTH_USER_MODEL refers to 'core.User' not installed` | Modelos ORM en `infrastructure/`, Django busca en `core/models.py` | Crear `core/models.py` como adaptador de reexportación |
| 8 | Django Runtime | `relation "users" does not exist` — backend en loop | `core/migrations/` no existía | `docker compose run --rm backend python src/manage.py makemigrations core` |
| 9 | 2FA | `No module named 'pyotp'` | Imagen Docker construida antes de añadir pyotp a requirements | `docker compose build backend` (rebuild imagen) |
| 10 | Encoding | Caracteres españoles corruptos (`á` → `Ã¡`) en `views.py` | PowerShell `Set-Content` reescribió en CP1252 leído como UTF-8 | Script Python: `raw.decode('utf-8').encode('cp1252')` para invertir la doble codificación |
| 11 | OHLCV | Tokens HYPE/BGB devuelven precio `$3.200` falso | `GetAssetOhlcvUseCase._synthetic_fallback()` generaba velas inventadas cuando Binance no listaba el par | Eliminar `_synthetic_fallback()` e implementar Strategy Pattern: Binance → CoinGecko OHLC → `OhlcvNotAvailableError` |
| 12 | Encoding | `replace_string_in_file` no encuentra el texto en `views.py` | El archivo tiene BOM UTF-8 (`EF BB BF`) que PowerShell preserva pero la herramienta de edición no reconoce | Editar mediante script Python con `open(f, 'r', encoding='utf-8-sig')` y `write_text(encoding='utf-8-sig')` |
| 13 | CoinGecko | Granularidad OHLC no configurable en plan gratuito | La API free fuerza granularidad automática: 30 min (1-2d), 4h (3-30d), 4 días (31+d) | Mapear `interval + limit → days` con `_interval_limit_to_days()` y documentar la limitación en el badge del frontend |
| 14 | Portfolio | KPI cards mostraban `$NaN` | 4 campos nuevos del DTO (`long_count`, `short_count`, `total_long_invested_usd`, `total_short_exposure_usd`) calculados en Python pero nunca incluidos en el diccionario de respuesta de `PortfolioView` | Añadir los 4 campos al `return Response(...)` en `views.py` |
| 15 | Portfolio | Badge LONG/SHORT incorrecto (BTC SHORT aparecía como LONG) | Campo `position_type` presente en `PortfolioPositionDTO` pero ausente en `PortfolioPositionSerializer` | Añadir `position_type = serializers.CharField(default="LONG")` al serializer |
| 16 | Portfolio | Columna "Valor recompra" confusa para posiciones LONG | El mismo header describía conceptos distintos según el tipo de posición | Renombrar a "Valor posición" con sublabels contextuales por celda: "valor actual" (LONG) / "coste recompra" (SHORT) |
| 17 | SELL sin BUY | `AddTradeUseCase` rechazaba SELL si no había BUY previo | Validación demasiado estricta que impedía crear posiciones SHORT | Eliminar la validación; un SELL sin compra previa crea una posición en descubierto (SHORT) |
| 18 | Password reset | Email de recuperación no llegaba en dev y sin traza en logs | `RequestPasswordResetUseCase` no tenía logging; era difícil saber si el email se enviaba | Añadir `logger.debug()` para email no encontrado y `logger.info()` tras `send_mail()` |
| 19 | TypeScript | `TS1005: '}' expected` — build Docker fallido | Al reemplazar bloque JSX en `MarketPage.tsx`, se omitió el `}` de cierre de comentario JSX | Añadir el `}` faltante para cerrar la expresión `{/* ... */}` |
| 20 | Sparklines | Sparklines ausentes en los 20 primeros activos del mercado | `assets.slice(0, 25)` usaba el orden de la API (alfabético por `symbol`) en lugar del orden visible (market_cap desc) | Ordenar `[...assets]` por `market_cap` desc antes del `slice(0, 25)` en el `useEffect` de sparklines |
| 21 | Sparklines | Stablecoins (USDT, USDC) muestran `—` en lugar de gráfica | `{symbol}USDT` forma el par inválido `USDTUSDT` en Binance; no hay datos OHLCV disponibles | Comportamiento correcto: `AssetSparklinesView` devuelve `[]` para ellos y el frontend muestra `—` |
| 22 | Sync periódico | Intervalo de 10 min excesivo para la demo; precios visualmente desactualizados | El intervalo conservador fue diseñado para respetar el límite mensual de CoinGecko (10 000 calls/mes) antes de que sparklines usaran la BD | Arquitectura dual: `sync_prices_quick` (Binance, cada 60 s, sin cuota) + `sync_market_prices` (CoinGecko, cada 300 s) |

---

## 13. CAMBIOS DESDE v1.47 HASTA v1.88 (Mayo 2026)

### 13.1 KuCoin como tercer nivel en la estrategia OHLCV

Se añadió `KuCoinPublicClient` como tercer fallback en la cadena `GetAssetOhlcvUseCase`:

```
Binance (BTCUSDT) → KuCoin (BTC-USDT) → CoinGecko OHLC → OhlcvNotAvailableError
```

KuCoin permite ~2 000 req/30 s sin autenticación, devuelve velas en orden descendente
(requiere inversión) y usa el formato `BTC-USDT` en lugar de `BTCUSDT`.

| Archivo | Tipo | Descripción |
|---|---|---|
| `infrastructure/external_apis/kucoin_client.py` | Nuevo | Cliente KuCoin Public API. `get_klines(symbol, interval, limit)`. Normaliza símbolo automáticamente (`BTCUSDT` → `BTC-USDT`). Invierte orden descendente. |
| `application/use_cases/get_asset_ohlcv.py` | Modificado | Cadena ampliada: Binance → KuCoin → CoinGecko OHLC |

### 13.2 Sistema de Watchlist

Implementación completa del sistema de seguimiento personal de activos:

**Backend:**

| Archivo | Tipo | Descripción |
|---|---|---|
| `infrastructure/persistence/models.py` | Modificado | Modelo `WatchlistItem` con FK a `User` y `CryptoAsset` |
| `interfaces/api/views.py` | Modificado | `WatchlistView` (GET/POST/DELETE `/api/watchlist/`) |
| `interfaces/api/serializers.py` | Modificado | `WatchlistItemSerializer` |
| `interfaces/api/urls.py` | Modificado | Rutas `/api/watchlist/` y `/api/watchlist/{symbol}/` |

**Frontend:**

| Archivo | Tipo | Descripción |
|---|---|---|
| `services/watchlistService.ts` | Nuevo | `getWatchlist()`, `addToWatchlist(symbol)`, `removeFromWatchlist(symbol)` |
| `pages/DashboardPage.tsx` | Modificado | Sección "★ Mi seguimiento" entre Catálogo y Movimiento del mercado; sparklines para activos del watchlist |
| `pages/MarketPage.tsx` | Modificado | Sección "★ Mi seguimiento" con borde amarillo sobre la tabla principal |

### 13.3 AssetDetailPage — Implementación completa

Página de detalle de activo con múltiples secciones integradas:

| Componente | Descripción |
|---|---|
| `ProjectCard` | Rediseñado con iconos SVG propios (`GlobeIcon`, `DocumentIcon`, `XIcon`, `RedditIcon`, `TelegramIcon`, `GitHubIcon`), barra de supply (`SupplyBar`), descripción colapsable con strip HTML, categorías con badges, enlaces como tarjetas |
| `OhlcvChart` | Gráfico KLineChart v9 integrado; badge dinámico de fuente (Binance/KuCoin/CoinGecko); 20+ indicadores técnicos; herramientas de dibujo |
| `AnalysisPanel` | Panel de análisis técnico (señales RSI/MACD/Bollinger, predicción ML, backtesting de 5 estrategias) |

**Datos nuevos en `AssetInfo` (frontend `marketService.ts`):**

```typescript
interface AssetInfo {
  // ...campos existentes...
  telegram: string | null;   // ← nuevo en 1.87.0
  github: string | null;     // ← nuevo en 1.87.0
}
```

**Backend `AssetDetailInfoView`** devuelve los campos `telegram` y `github` del objeto
`links` de CoinGecko extraídos mediante `get_coin_detail(coingecko_id)`.

### 13.4 Dashboard — Mejoras visuales

| Componente | Descripción |
|---|---|
| `FearGreedGauge` | Indicador semicircular animado para el índice Fear & Greed (Alternative.me) |
| `TickerBar` | Barra desplazante con precios en tiempo real (datos del endpoint `/api/assets/`) |
| `Sparkline` | Gráfico de línea minimalista SVG para la columna de variación de 7 días |

### 13.5 MarketPage — Sparklines profesionales

`AssetSparklinesView` fue completamente reescrita para eliminar las llamadas directas
a CoinGecko y servir datos desde la BD local:

**Antes (v1.47):**
```
GET /api/assets/sparklines/?symbols=BTC,ETH,...
→ Por cada símbolo: CoinGecko /coins/{id}/market_chart  (1 req/activo)
→ 10 símbolos = 10 req CoinGecko simultáneas → rate limit frecuente
```

**Ahora (v1.87+):**
```
GET /api/assets/sparklines/?symbols=BTC,ETH,...
→ MarketDataSnapshot.objects.filter(...).annotate(avg_price=Avg(...))  (0 req externas)
→ Fallback OHLCV (Binance/KuCoin) solo si < 2 días de historial local
```

La fuente de datos para sparklines es `MarketDataSnapshot` (serie temporal creada
por `sync_market_prices` cada 5 min), agrupada por día y promediada (`TruncDate` +
`Avg`). Esto proporciona curvas más limpias y sin variabilidad por el momento exacto
de consulta.

### 13.6 Arquitectura dual de sincronización (v1.88.0)

Antes del v1.88, el único sync periódico era `sync_market_prices` vía CoinGecko cada
10 minutos. A partir de v1.88 se implementa una arquitectura de dos niveles:

**Nivel 1 — Sync rápido de precios (Binance, cada 60 s):**

```python
# core/tasks.py
@shared_task(name="core.tasks.sync_prices_quick")
def sync_prices_quick(self): ...

# core/application/use_cases/sync_prices_quick.py
class SyncPricesQuickUseCase:
    def execute(self) -> QuickSyncResultDTO:
        tickers = BinancePublicClient().get_ticker_24hr()  # 1 HTTP call, weight=40
        # bulk_update de current_price, volume_24h, price_change_24h
```

**Nivel 2 — Sync completo CoinGecko (cada 5 min):**

```python
# config/settings.py  — reducido de 600 s a 300 s
"sync-market-prices": {"task": "core.tasks.sync_market_prices", "schedule": 300.0}
```

**Comparativa de presupuesto mensual CoinGecko:**

| Intervalo | calls/día | calls/mes | Límite Demo | Estado |
|---|---|---|---|---|
| 10 min (v1.47) | 144 | 4 320 | 10 000 | ✅ Amplio margen |
| 5 min (v1.88) | 288 | 8 640 | 10 000 | ✅ Dentro del límite |
| 3 min | 480 | 14 400 | 10 000 | ❌ Excede |
| 1 min | 1 440 | 43 200 | 10 000 | ❌ Excede |

**Por qué usar Binance para el sync rápido:**
- `GET /api/v3/ticker/24hr` (sin símbolo) devuelve ~2 000 pares en 1 llamada (weight=40)
- No requiere autenticación ni API key
- Limit: 1 200 weight/min → 40 weight cada 60 s = 3,3 % del presupuesto
- Sin cuota mensual → puede ejecutarse cada segundo si fuera necesario

**Archivos nuevos/modificados:**

| Archivo | Tipo | Descripción |
|---|---|---|
| `application/use_cases/sync_prices_quick.py` | Nuevo | `SyncPricesQuickUseCase` + `QuickSyncResultDTO` |
| `core/tasks.py` | Modificado | Nueva tarea `sync_prices_quick` (max_retries=1) |
| `config/settings.py` | Modificado | `sync-prices-quick` cada 60 s; `sync-market-prices` de 600 s → 300 s |

### 13.7 Actualización del estado actual — v1.88.0

**Tareas periódicas Celery:**

| Tarea | Intervalo | API | Acción |
|---|---|---|---|
| `check_price_alerts` | 120 s | DB | Evalúa alertas activas |
| `sync_prices_quick` | 60 s | Binance (sin cuota) | Actualiza precio, volumen, variación |
| `sync_market_prices` | 300 s | CoinGecko (8 640 calls/mes) | Actualiza market_cap, logos + crea MarketDataSnapshot |

**Endpoints actualizados:**

| Método | Ruta | Cambio |
|---|---|---|
| GET | `/api/assets/sparklines/` | Reescrito: sirve desde `MarketDataSnapshot` (0 calls CoinGecko); fallback OHLCV Binance/KuCoin solo para activos nuevos |
| GET | `/api/assets/{symbol}/` | `AssetDetailInfoView` devuelve `telegram` y `github` |
| GET | `/api/watchlist/` | Nuevo: lista el watchlist del usuario |
| POST | `/api/watchlist/{symbol}/` | Nuevo: añade activo al watchlist |
| DELETE | `/api/watchlist/{symbol}/` | Nuevo: elimina activo del watchlist |

**Capas actualizadas:**

| Capa | Cambio |
|---|---|
| Infrastructure — External APIs | KuCoin client añadido (3er nivel OHLCV) |
| Application — Use Cases | `SyncPricesQuickUseCase` (Binance bulk price update) |
| Infrastructure — Celery | 3 tareas periódicas (alertas, quick sync, full sync) |
| Frontend — Components | `FearGreedGauge`, `TickerBar`, `Sparkline`, `OhlcvChart` (KLineChart v9) |
| Frontend — Pages | `AssetDetailPage` (completo), `MarketPage` (sparklines + watchlist), `DashboardPage` (watchlist + movers) |
| Frontend — Services | `watchlistService.ts` |

---

*Documento técnico completo del proyecto CryptoWorld — Estado v1.88.0 — Mayo 2026*  
*Última actualización: 28 mayo 2026*

<!-- FIN DEL DOCUMENTO -->