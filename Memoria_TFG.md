# Documento de Briefing Técnico — CryptoWorld
## Sistema de Análisis de Criptomonedas — TFG

**Autor:** Javier  
**Titulación:** 4º Ingeniería Informática  
**Universidad:** Universidad de Castilla-La Mancha  
**Fecha del documento:** Marzo 2026  

> **NOTA PARA LA IA REDACTORA:** Este documento es un briefing técnico completo del proyecto CryptoWorld tal como está implementado en marzo de 2026. Contiene el código real de los archivos más importantes, la justificación de cada decisión de diseño, y todos los detalles técnicos necesarios para redactar una memoria académica de TFG. No es necesario inferir nada—todo lo que existe en el proyecto está documentado aquí. El objetivo es una memoria académica formal para un TFG de Ingeniería Informática en la UCLM.

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

### Funcionalidades implementadas (Marzo 2026)
- Sistema de autenticación completo: registro, login, logout seguro
- Verificación de email mediante token HMAC
- Recuperación y cambio de contraseña
- Autenticación de Doble Factor (2FA) mediante TOTP (compatible con Google Authenticator)
- Listado de activos criptográficos (datos mock, pendiente integración real)
- Infraestructura de análisis técnico (stub preparado para RSI, MACD, Bollinger)
- Dashboard frontend con rutas protegidas por JWT

### Funcionalidades pendientes (roadmap)
- Integración con CoinGecko API para datos de mercado reales
- Análisis técnico: RSI, MACD, Bandas de Bollinger, Medias Móviles
- Gestión de portfolio personal
- Sistema de alertas configurables
- Historial de análisis ejecutados

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
│  external_apis/  (pendiente CoinGecko)                   │
│  → Sabe de Django ORM y PostgreSQL.                      │
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
    id: Optional[int] = None

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
│   └── run_analysis.py           ← Ejecutar análisis técnico (stub)
└── dto/
    ├── auth_dto.py               ← 13 DTOs de autenticación
    └── asset_dto.py              ← DTOs de activos y análisis
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

#### Caso de Uso de Análisis (stub)

**`application/use_cases/run_analysis.py` — estructura preparada (código real):**
```python
from core.domain.entities.crypto_asset import AnalysisExecutionEntity
from core.application.dto.asset_dto import AnalysisRequestInputDTO, AnalysisOutputDTO

class RunAnalysisUseCase:
    def execute(self, input_dto: AnalysisRequestInputDTO) -> AnalysisOutputDTO:
        # Crear entidad en estado 'pending'
        execution = AnalysisExecutionEntity(
            asset_symbol=input_dto.asset_symbol,
            analysis_type=input_dto.analysis_type,
            status="pending",
        )
        # TODO: Inyectar repositorio y persistir
        # TODO: Disparar tarea asíncrona (Celery) con el análisis real (RSI, MACD, etc.)
        return AnalysisOutputDTO(
            id=0,
            asset_symbol=execution.asset_symbol,
            analysis_type=execution.analysis_type,
            status=execution.status,
            result=None,
        )
```

---

### 4.3 CAPA DE INFRAESTRUCTURA — `backend/src/core/infrastructure/`

La infraestructura es el puente entre el dominio abstracto y las tecnologías concretas. Implementa los contratos definidos en `domain/repositories/` utilizando Django ORM y PostgreSQL.

**Estructura:**
```
infrastructure/
├── persistence/
│   ├── models.py              ← Modelos Django ORM (4 tablas)
│   └── repositories_impl.py  ← DjangoUserRepository, DjangoCryptoAssetRepository
└── external_apis/             ← (pendiente) Cliente CoinGecko API
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crypto_assets"
        ordering = ["symbol"]

class MarketDataSnapshot(models.Model):
    asset = models.ForeignKey(CryptoAsset, on_delete=models.CASCADE, related_name="snapshots")
    price = models.DecimalField(max_digits=20, decimal_places=8)
    volume = models.DecimalField(max_digits=30, decimal_places=2)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "market_data_snapshots"

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
    MarketDataSnapshot, AnalysisExecution,
)
```

---

### 4.4 CAPA DE INTERFACES — `backend/src/core/interfaces/api/`

La capa de interfaces es la única que sabe que existe HTTP. Recibe peticiones, llama a los casos de uso, y devuelve respuestas JSON.

**Estructura:**
```
interfaces/api/
├── views.py        ← Views DRF: 17 endpoints
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

    # Auth — 2FA TOTP
    path("auth/2fa/setup/", views.Setup2FAView.as_view(), name="auth-2fa-setup"),
    path("auth/2fa/enable/", views.Enable2FAView.as_view(), name="auth-2fa-enable"),
    path("auth/2fa/disable/", views.Disable2FAView.as_view(), name="auth-2fa-disable"),
    path("auth/2fa/login/", views.Verify2FALoginView.as_view(), name="auth-2fa-login"),

    # Dominio criptográfico
    path("assets/", views.AssetListView.as_view(), name="asset-list"),
    path("analysis/run/", views.RunAnalysisView.as_view(), name="analysis-run"),
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

El sistema completo corre en 4 contenedores Docker orquestados con Docker Compose v2.

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
      - postgres_data:/var/lib/postgresql/data  # Datos persistentes entre reinicios
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-postgres}"]
      interval: 10s
      timeout: 5s
      retries: 5  # Backend no arranca hasta que Postgres esté listo

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: cryptoworld_backend
    restart: unless-stopped
    env_file: .env
    environment:
      DJANGO_SETTINGS_MODULE: config.settings
      DB_HOST: postgres  # Nombre del servicio, no localhost
    ports:
      - "8000:8000"
    volumes:
      - ./backend/src:/app/src     # Hot-reload: cambios en código sin rebuild
      - ./backend/tests:/app/tests
      - ./backend/pytest.ini:/app/pytest.ini
    depends_on:
      postgres:
        condition: service_healthy  # Espera al healthcheck de Postgres
    command: >
      sh -c "
        cd src &&
        python manage.py migrate --noinput &&
        python manage.py runserver 0.0.0.0:8000
      "

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
      - "5173:5173"  # dev server de Vite
    volumes:
      - ./frontend/src:/app/src  # Hot-reload del frontend

volumes:
  postgres_data:
```

**Puntos clave del diseño Docker:**
- `depends_on: condition: service_healthy` garantiza que Django no arranca antes de que PostgreSQL esté listo y aceptando conexiones
- Los volúmenes montados (`./backend/src:/app/src`) permiten hot-reload en desarrollo sin reconstruir la imagen
- Variables de entorno en `.env` (no en el repositorio): `SECRET_KEY`, `DB_PASSWORD`, etc.
- El comando de arranque del backend ejecuta `migrate` automáticamente en cada inicio

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
```

---

## 7. FRONTEND: ARQUITECTURA REACT SPA

### Estructura de capas del frontend

```
Browser
  └── React SPA
        ├── Routing (react-router-dom v6)
        │     ├── Rutas públicas: /login
        │     └── Rutas protegidas: /dashboard, /assets/:symbol
        │           └── Guard: ProtectedRoute (comprueba JWT)
        ├── Estado global de autenticación
        │     └── AuthContext + useAuth hook (React Context API)
        ├── Páginas (pages/)
        │     ├── LoginPage.tsx
        │     ├── DashboardPage.tsx
        │     └── AssetDetailPage.tsx
        ├── Capa de servicios (services/)
        │     ├── api.ts          ← Instancia Axios centralizada
        │     ├── authService.ts  ← Llamadas HTTP de auth
        │     └── analysisService.ts ← Llamadas HTTP de análisis
        └── Componentes compartidos (components/)
              ├── Navbar.tsx
              └── ProtectedRoute.tsx
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
import DashboardPage from '@/pages/DashboardPage'
import AssetDetailPage from '@/pages/AssetDetailPage'
import ProtectedRoute from '@/components/ProtectedRoute'

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* Rutas protegidas: el guard comprueba JWT antes de renderizar */}
      <Route element={<ProtectedRoute />}>
        <Route element={<LayoutWithNav />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/assets/:symbol" element={<AssetDetailPage />} />
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

**4 tablas principales** en PostgreSQL, más las tablas internas de Django y SimpleJWT:

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
             │ (sin FK explícita, user_id en casos de uso)
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
```

**Migraciones aplicadas:**
| Archivo | Contenido |
|---|---|
| `core/migrations/0001_initial.py` | Crea las 4 tablas: users, crypto_assets, market_data_snapshots, analysis_executions |
| `core/migrations/0002_user_auth_fields.py` | Añade is_email_verified, totp_secret, is_2fa_enabled a la tabla users |
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

---

## 11. ESTADO ACTUAL Y ROADMAP

### Estado actual — Marzo 2026

**Servicios Docker activos:**
| Contenedor | Puerto | Estado |
|---|---|---|
| cryptoworld_db (PostgreSQL) | 5432 | Running (healthy) |
| cryptoworld_backend (Django) | 8000 | Running |
| cryptoworld_frontend (React/Vite) | 5173 | Running |
| cryptoworld_pgadmin | 5050 | Running |

**Endpoints implementados y validados:**
| Método | Ruta | Auth | Estado |
|---|---|---|---|
| GET | `/api/health/` | No | ✅ Funcional |
| POST | `/api/auth/register/` | No | ✅ Funcional |
| POST | `/api/auth/login/` | No | ✅ Funcional (soporta 2FA) |
| POST | `/api/auth/logout/` | Sí | ✅ Funcional (blacklist) |
| GET | `/api/auth/me/` | Sí | ✅ Funcional |
| POST | `/api/auth/token/refresh/` | No | ✅ Funcional |
| GET | `/api/auth/verify-email/` | No | ✅ Funcional |
| POST | `/api/auth/verify-email/resend/` | Sí | ✅ Funcional |
| POST | `/api/auth/password-reset/` | No | ✅ Funcional |
| POST | `/api/auth/password-reset/confirm/` | No | ✅ Funcional |
| POST | `/api/auth/change-password/` | Sí | ✅ Funcional |
| POST | `/api/auth/2fa/setup/` | Sí | ✅ Funcional |
| POST | `/api/auth/2fa/enable/` | Sí | ✅ Funcional |
| POST | `/api/auth/2fa/disable/` | Sí | ✅ Funcional |
| POST | `/api/auth/2fa/login/` | No | ✅ Funcional |
| GET | `/api/assets/` | Sí | ⚠️ Datos mock |
| POST | `/api/analysis/run/` | Sí | ⚠️ Stub (retorna pending) |

**Capas implementadas:**
| Capa | Estado |
|---|---|
| Domain — Entities (4 entidades) | ✅ Completo |
| Domain — Repository interfaces | ✅ Completo |
| Domain — Value Objects | ✅ Completo |
| Domain — Services | ✅ Completo |
| Application — 13 casos de uso | ✅ Completo (auth completo, assets/análisis parcial) |
| Application — DTOs | ✅ Completo |
| Infrastructure — ORM Models | ✅ Completo (4 modelos, 2 migraciones) |
| Infrastructure — Repositories impl | ✅ Completo |
| Infrastructure — External APIs | ❌ Pendiente (CoinGecko) |
| Interfaces — API (17 endpoints) | ✅ Completo |
| Frontend — Auth flow | ✅ Completo |
| Frontend — Dashboard | ⚠️ Parcial (sin datos reales) |
| Tests unitarios | ✅ Implementados y pasando |
| Tests integración | ✅ Implementados y pasando |

### Roadmap de fases futuras

**Sprint 1** — Integración CoinGecko API
- Crear `infrastructure/external_apis/coingecko_client.py`
- Definir `ICoinGeckoRepository` en el dominio
- Implementar `GetLiveMarketDataUseCase`
- Conectar `GET /api/assets/` con datos reales
- Caché de respuestas para evitar rate-limiting

**Sprint 2** — Análisis Técnico
- RSI (Relative Strength Index) en `domain/services/`
- MACD (Moving Average Convergence Divergence)
- Bandas de Bollinger
- Medias Móviles (SMA, EMA)
- Completar `RunAnalysisUseCase` con lógica real

**Sprint 3** — Frontend con datos reales
- Gráficos de precios históricos
- Tabla de mercado paginada con datos CoinGecko
- Flujo 2FA completo en el frontend (formulario TOTP)
- Verificación de email integrada en registro

**Sprint 4** — Portfolio y Alertas
- CRUD de portfolio personal (posiciones, precio de entrada, P&L)
- Sistema de alertas (precio objetivo, % de cambio)
- Historial de análisis ejecutados por usuario

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

---

*Documento técnico completo del proyecto CryptoWorld — Estado v1.2.0 — Marzo 2026*  
*Última actualización: 12 de marzo de 2026*

<!-- FIN DEL DOCUMENTO -->
<!-- TODO: borrar todo lo que hay debajo de esta línea (contenido antiguo del diario de desarrollo)

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

-->
<!-- FIN DEL CONTENIDO ANTIGUO -->
