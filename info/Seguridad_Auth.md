# Medidas de Seguridad en CryptoWorld — Explicación en Profundidad

> Documento de referencia técnica sobre cada mecanismo de seguridad implementado en el sistema de autenticación del backend Django.

---

## Índice

1. [JWT — JSON Web Tokens](#1-jwt--json-web-tokens)
2. [Access Token y Refresh Token](#2-access-token-y-refresh-token)
3. [Token Blacklist (Logout Seguro)](#3-token-blacklist-logout-seguro)
4. [HMAC — Tokens Firmados para Email](#4-hmac--tokens-firmados-para-email)
5. [TOTP — Autenticación de Dos Factores](#5-totp--autenticación-de-dos-factores)
6. [Pre-Auth Token (Flujo 2FA en Dos Pasos)](#6-pre-auth-token-flujo-2fa-en-dos-pasos)
7. [Validadores de Contraseña Django](#7-validadores-de-contraseña-django)
8. [Tabla Resumen](#8-tabla-resumen)

---

## 1. JWT — JSON Web Tokens

### ¿Qué es?

Un JWT es un token autocontenido que codifica información (llamada *claims*) de forma que el servidor puede verificar su autenticidad sin consultar la base de datos en cada petición.

Tiene tres partes separadas por puntos:

```
eyJhbGciOiJIUzI1NiJ9   ←  Header (algoritmo)
.eyJ1c2VyX2lkIjoxfQ    ←  Payload (datos: user_id, exp...)
.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c  ←  Firma HMAC-SHA256
```

### ¿Por qué se usa?

- **Sin estado (stateless):** el servidor no necesita guardar sesiones. La información del usuario viaja dentro del propio token.
- **Escalable:** cualquier instancia del servidor puede verificar el token con solo conocer la `SECRET_KEY`, sin necesidad de una base de datos de sesiones compartida.
- **Estándar abierto:** compatible con cualquier cliente (web, móvil, aplicaciones de terceros).

### ¿Cómo funciona en CryptoWorld?

1. El usuario hace login con email + contraseña.
2. El backend genera dos JWT firmados con `SECRET_KEY` (algoritmo HS256).
3. El cliente almacena los tokens (normalmente en memoria o `httpOnly` cookie).
4. Cada petición protegida incluye el `access_token` en la cabecera:
   ```
   Authorization: Bearer <access_token>
   ```
5. Django verifica la firma. Si es válida y no ha expirado, permite el acceso.

### Riesgo si no se usa

Sin JWT (o sin tokens), habría que guardar la sesión del usuario en el servidor, lo que complica el escalado horizontal y requiere una base de datos de sesiones compartida.

---

## 2. Access Token y Refresh Token

### ¿Qué son?

Son dos JWT con propósitos distintos y tiempos de vida diferentes:

| Token | Vida útil | Uso |
|-------|-----------|-----|
| **Access Token** | 5 minutos (configurable) | Autenticar cada petición a la API |
| **Refresh Token** | 7 días (configurable) | Obtener un nuevo access token sin volver a hacer login |

### ¿Por qué dos tokens en lugar de uno?

Un único token de larga duración tiene un problema grave: **si es robado, el atacante tiene acceso durante días o semanas**. La separación en dos tokens resuelve esto:

- El **access token** tiene vida muy corta (5 min). Si es interceptado, el atacante solo tiene 5 minutos para usarlo.
- El **refresh token** tiene vida larga pero **solo se envía a un único endpoint** (`/api/auth/token/refresh/`), reduciendo la exposición.

### Flujo completo

```
Cliente                         Servidor
  │                               │
  │── POST /auth/login/ ─────────>│
  │<── access_token (5min) ───────│
  │<── refresh_token (7días) ─────│
  │                               │
  │── GET /api/assets/ + access ─>│  ← petición normal
  │<── 200 OK ────────────────────│
  │                               │
  │  [5 minutos después]          │
  │                               │
  │── GET /api/assets/ + access ─>│
  │<── 401 Unauthorized ──────────│  ← token expirado
  │                               │
  │── POST /auth/token/refresh/ ─>│  ← usa el refresh token
  │<── nuevo access_token ─────── │
  │                               │
  │── GET /api/assets/ + nuevo ──>│
  │<── 200 OK ────────────────────│
```

### Riesgo si no se usa

Con un solo token de larga duración, un XSS o una intercepción de red comprometería la cuenta del usuario durante días sin posibilidad de invalidación granular.

---

## 3. Token Blacklist (Logout Seguro)

### El problema del logout con JWT

Los JWT son **stateless por diseño**: el servidor no guarda ningún registro de qué tokens ha emitido. Esto crea un problema inesperado: **el logout es imposible sin una capa adicional**.

Si un usuario hace logout, el cliente puede eliminar el token de su almacenamiento, pero el token sigue siendo técnicamente válido hasta que expire. Si alguien lo robó antes del logout, **puede seguir usándolo**.

### ¿Qué es el Token Blacklist?

Es una tabla en la base de datos (`token_blacklist_outstandingtoken` y `token_blacklist_blacklistedtoken`) proporcionada por `djangorestframework-simplejwt` que registra qué refresh tokens han sido invalidados.

### ¿Cómo funciona el logout en CryptoWorld?

```python
# logout.py (simplificado)
from rest_framework_simplejwt.tokens import RefreshToken

refresh = RefreshToken(dto.refresh_token)
refresh.blacklist()  # ← inserta el token en la tabla de blacklist
```

1. El cliente envía el `refresh_token` al endpoint `POST /api/auth/logout/`.
2. El use case `LogoutUseCase` llama a `refresh.blacklist()`.
3. SimpleJWT guarda el JTI (identificador único del token) en la base de datos.
4. La próxima vez que alguien intente usar ese refresh token para obtener un nuevo access token, SimpleJWT comprueba la blacklist y devuelve `401 Token is blacklisted`.

### ¿Por qué solo se blacklistea el refresh token y no el access token?

- El access token tiene vida muy corta (5 min), por lo que el riesgo de que sea usado tras el logout es mínimo y acotado en el tiempo.
- Blacklistear el access token requeriría consultar la base de datos en **cada petición autenticada**, eliminando la ventaja principal del JWT (stateless).
- El refresh token es el que permite obtener nuevos access tokens indefinidamente, así que invalidarlo corta la cadena de forma efectiva.

### Riesgo si no se usa

Sin blacklist, el "logout" es una ilusión: el cliente borra el token pero el servidor no sabe que ya no debería ser válido. Un atacante con el refresh token robado tiene acceso durante 7 días.

---

## 4. HMAC — Tokens Firmados para Email

### ¿Qué es HMAC?

HMAC (Hash-based Message Authentication Code) es un mecanismo criptográfico que genera un código de autenticación a partir de un mensaje y una clave secreta. Se usa para verificar que un dato no ha sido modificado y que fue generado por quien dice haberlo generado.

En Django, la clase `django.core.signing.TimestampSigner` implementa HMAC sobre la `SECRET_KEY` del proyecto.

### ¿Dónde se usa en CryptoWorld?

En dos flujos:

#### 4.1 Verificación de Email

```python
# send_verification_email.py (simplificado)
from django.core import signing

signer = signing.TimestampSigner()
token = signer.sign(f"{user.id}:{user.email}")
# token → "1:usuario@example.com:timestamp:firma_hmac"
```

El token se incluye en el link de verificación:
```
http://localhost:8000/api/auth/verify-email/?token=1%3Ausuario%40...
```

Al hacer clic, el servidor verifica:
1. Que la firma HMAC es válida (el token no fue manipulado).
2. Que el timestamp no ha superado el tiempo máximo permitido (por defecto 3 días).
3. Que el email del token coincide con el del usuario en la base de datos.

#### 4.2 Recuperación de Contraseña

Mismo mecanismo pero el token incluye un hash de la contraseña actual del usuario:

```python
token = signer.sign(f"{user.id}:{hash_password_actual}")
```

Esto garantiza que el link de recuperación **se invalida automáticamente** si:
- El usuario ya cambió su contraseña desde entonces.
- El link fue usado (porque al cambiar la contraseña, el hash cambia).

### ¿Por qué no usar UUID aleatorios guardados en la base de datos?

Sería perfectamente válido, pero HMAC tiene ventajas:
- **No requiere tabla en base de datos** para guardar tokens pendientes.
- **Expira automáticamente** por el timestamp embebido.
- **Se invalida automáticamente** al cambiar la contraseña (en el caso de recuperación).

### Riesgo si no se usa

Sin firma criptográfica, un atacante podría fabricar un token de verificación o recuperación modificando parámetros en la URL (p. ej., cambiar el `uid` para verificar la cuenta de otro usuario).

---

## 5. TOTP — Autenticación de Dos Factores

### ¿Qué es TOTP?

TOTP (Time-based One-Time Password) es un algoritmo estándar (RFC 6238) que genera códigos numéricos de 6 dígitos que cambian cada 30 segundos. Es el mecanismo que usan Google Authenticator, Authy y Microsoft Authenticator.

### ¿Cómo funciona matemáticamente?

```
TOTP = HOTP(secreto, contador_de_tiempo)

donde:
  contador_de_tiempo = floor(unix_timestamp / 30)
  HOTP(K, C)         = HMAC-SHA1(K, C) truncado a 6 dígitos
```

El **secreto base32** es la semilla compartida entre el servidor y la app del usuario. Como ambos conocen el tiempo Unix actual, pueden generar el mismo código sin comunicarse.

### Flujo de setup en CryptoWorld

```
1. Usuario → POST /api/auth/2fa/setup/
   Servidor genera: secreto = pyotp.random_base32()
   Guarda en BD:    user.totp_secret = secreto  (no activado aún)
   Devuelve:        { secret: "JBSWY3DPEHPK3PXP", qr_code: "data:image/png;base64,..." }

2. Usuario escanea el QR con Google Authenticator

3. Usuario → POST /api/auth/2fa/enable/ con { code: "123456" }
   Servidor verifica: pyotp.TOTP(secreto).verify(code)
   Si correcto:       user.is_2fa_enabled = True

4. Ahora el login requiere el código TOTP
```

### ¿Por qué TOTP y no SMS?

| Método | Ventajas | Desventajas |
|--------|----------|-------------|
| **TOTP** | Sin coste, sin red, offline, no interceptable por SIM swapping | Requiere app en el móvil |
| **SMS** | Fácil de usar, sin app | Coste por SMS, vulnerable a SIM swapping, interceptable |
| **Email** | Sin coste | Depende de la seguridad del email, más lento |

TOTP es el estándar de facto para 2FA en aplicaciones de seguridad media-alta como exchanges de criptomonedas.

### Ventana de tolerancia

Por defecto `pyotp` acepta el código actual y el del intervalo anterior (+/- 30 segundos) para compensar diferencias de reloj entre el servidor y el dispositivo del usuario.

### Riesgo si no se usa

Sin 2FA, si la contraseña de un usuario es comprometida (filtración de datos, phishing, fuerza bruta), el atacante tiene acceso completo a la cuenta. Con 2FA, necesita además acceso físico al dispositivo del usuario.

---

## 6. Pre-Auth Token (Flujo 2FA en Dos Pasos)

### El problema a resolver

El login con 2FA requiere dos pasos:
1. Verificar email + contraseña.
2. Verificar el código TOTP.

Entre el paso 1 y el paso 2 hay un problema: **¿cómo sabe el servidor que quien envía el código TOTP es el mismo que verificó la contraseña?** No se puede emitir un JWT completo antes de verificar el TOTP (eso eliminaría la seguridad del 2FA).

### Solución: Pre-Auth Token

Se emite un JWT especial con tipo `pre_2fa` y vida útil de solo **5 minutos**:

```python
# verify_2fa_login.py (simplificado)
class PreAuthToken(Token):
    token_type = "pre_2fa"
    lifetime = timedelta(minutes=5)
```

### Flujo completo

```
Cliente                              Servidor
  │                                    │
  │── POST /auth/login/               ─>│  email + password OK
  │<── { requires_2fa: true,           │  NO se emiten JWT completos
  │      pre_auth_token: "eyJ..." }   ─│  se emite solo pre_auth_token
  │                                    │
  │  [usuario abre Google Authenticator]
  │                                    │
  │── POST /auth/2fa/login/           ─>│  pre_auth_token + code TOTP
  │                                    │  Verifica: token_type == "pre_2fa"
  │                                    │  Verifica: código TOTP válido
  │<── { access_token, refresh_token } │  Ahora SÍ se emiten los tokens completos
```

### ¿Qué verifica el servidor en el segundo paso?

```python
# 1. Decodificar el pre_auth_token
token = UntypedToken(dto.pre_auth_token)

# 2. Verificar que es del tipo correcto (no un access/refresh token normal)
if token.get("token_type") != "pre_2fa":
    raise ValueError("Token inválido")

# 3. Verificar el código TOTP
totp = pyotp.TOTP(user.totp_secret)
if not totp.verify(dto.totp_code):
    raise ValueError("Código TOTP incorrecto")

# 4. Emitir tokens completos
refresh = RefreshToken.for_user(user)
```

### ¿Por qué no usar simplemente el user_id en la sesión?

Porque el sistema es **stateless**: no hay sesión de servidor. El pre_auth_token es la forma de mantener el estado del proceso de login sin romper la arquitectura.

### Riesgo si no se usa

Sin pre_auth_token, habría que emitir los tokens completos antes de verificar el TOTP (comprometiendo el 2FA) o guardar el estado en una sesión de servidor (comprometiendo el diseño stateless).

---

## 7. Validadores de Contraseña Django

### ¿Qué son?

Django incluye un sistema de validación de contraseñas configurable en `AUTH_PASSWORD_VALIDATORS`. En CryptoWorld se usan los cuatro validadores estándar:

```python
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
```

### ¿Qué hace cada uno?

| Validador | Qué comprueba |
|-----------|---------------|
| `UserAttributeSimilarityValidator` | La contraseña no es similar al nombre de usuario, email o nombre |
| `MinimumLengthValidator` | Mínimo 8 caracteres (configurable) |
| `CommonPasswordValidator` | No está en una lista de 20.000 contraseñas comunes (password, 123456, etc.) |
| `NumericPasswordValidator` | No es completamente numérica (123456789) |

### ¿Dónde se aplican en CryptoWorld?

En dos use cases:

```python
# confirm_password_reset.py y change_password.py
from django.contrib.auth.password_validation import validate_password

validate_password(nueva_password, user=user_model)
# Lanza ValidationError si no cumple con los validadores
```

### Riesgo si no se usa

Sin validadores, los usuarios podrían establecer contraseñas triviales como `123456` o `password`, que son las primeras que prueba cualquier ataque de fuerza bruta o diccionario.

---

## 8. Tabla Resumen

| Medida de Seguridad | Amenaza que mitiga | Implementada en | Vida útil |
|---------------------|-------------------|-----------------|-----------|
| **JWT (HS256)** | Falsificación de identidad, sesiones robadas | Login, todas las peticiones autenticadas | — |
| **Access Token** | Exposición prolongada de credenciales | Todas las peticiones a `/api/` | 5 minutos |
| **Refresh Token** | Necesidad de re-login frecuente vs. seguridad | `POST /auth/token/refresh/` | 7 días |
| **Token Blacklist** | Tokens robados activos tras logout | `POST /auth/logout/` | Permanente en BD |
| **HMAC (verificación email)** | Falsificación de links de verificación | `GET /auth/verify-email/` | 3 días |
| **HMAC (recuperación contraseña)** | Reutilización de links de recuperación caducados | `POST /auth/password-reset/confirm/` | 24 horas |
| **TOTP (2FA)** | Contraseñas comprometidas, phishing | `POST /auth/2fa/login/` | 30 segundos |
| **Pre-Auth Token** | Bypass del segundo factor de autenticación | `POST /auth/login/` (con 2FA activo) | 5 minutos |
| **Validadores de contraseña** | Contraseñas débiles, ataques de diccionario | Registro, cambio y recuperación de contraseña | — |

---

*Última actualización: Marzo 2026*
