# Guía de Pruebas con Postman — CryptoWorld API

> Guía paso a paso para probar todos los endpoints del sistema de autenticación desde Postman.

---

## Índice

1. [Configuración inicial del entorno](#1-configuración-inicial-del-entorno)
2. [Health Check](#2-health-check)
3. [Registro de usuario](#3-registro-de-usuario)
4. [Login (sin 2FA)](#4-login-sin-2fa)
5. [Ver perfil — /me/](#5-ver-perfil--me)
6. [Renovar Access Token](#6-renovar-access-token)
7. [Logout](#7-logout)
8. [Verificación de Email](#8-verificación-de-email)
9. [Recuperación de Contraseña](#9-recuperación-de-contraseña)
10. [Cambio de Contraseña](#10-cambio-de-contraseña)
11. [Configurar 2FA (TOTP)](#11-configurar-2fa-totp)
12. [Activar 2FA](#12-activar-2fa)
13. [Login con 2FA activo](#13-login-con-2fa-activo)
14. [Desactivar 2FA](#14-desactivar-2fa)
15. [Endpoints de datos](#15-endpoints-de-datos)
16. [Flujo completo de prueba](#16-flujo-completo-de-prueba)

---

## 1. Configuración inicial del entorno

### 1.1 Crear un entorno en Postman

1. Abrir Postman → **Environments** (icono de ojo en la barra lateral) → **Add**
2. Nombre: `CryptoWorld Local`
3. Añadir las siguientes variables:

| Variable | Initial Value | Current Value |
|----------|--------------|---------------|
| `base_url` | `http://localhost:8000` | `http://localhost:8000` |
| `access_token` | *(vacío)* | *(se rellena automáticamente)* |
| `refresh_token` | *(vacío)* | *(se rellena automáticamente)* |
| `pre_auth_token` | *(vacío)* | *(se rellena automáticamente)* |

4. Guardar y seleccionar el entorno en el desplegable superior derecho.

### 1.2 Script automático para guardar tokens

En cada petición de login, añadir en la pestaña **Tests** el siguiente script para que Postman guarde los tokens automáticamente:

```javascript
// Para el login normal (sin 2FA)
const response = pm.response.json();
if (response.access_token) {
    pm.environment.set("access_token", response.access_token);
    pm.environment.set("refresh_token", response.refresh_token);
}
// Para el login con 2FA (guarda pre_auth_token)
if (response.pre_auth_token) {
    pm.environment.set("pre_auth_token", response.pre_auth_token);
}
```

### 1.3 Configurar autorización global en una Collection

1. Crear una **Collection** llamada `CryptoWorld API`.
2. Click en la collection → **Authorization** → Type: `Bearer Token`.
3. Token: `{{access_token}}`.
4. Todas las peticiones dentro de la collection heredarán este token automáticamente (seleccionar **Inherit auth from parent** en cada request).

---

## 2. Health Check

Verifica que el servidor está funcionando.

```
GET {{base_url}}/api/health/
```

**Headers:** ninguno  
**Body:** ninguno

**Respuesta esperada (200 OK):**
```json
{
    "status": "ok",
    "version": "1.0.0"
}
```

---

## 3. Registro de usuario

```
POST {{base_url}}/api/auth/register/
```

**Headers:**
```
Content-Type: application/json
```

**Body (raw JSON):**
```json
{
    "email": "usuario@ejemplo.com",
    "username": "usuario1",
    "password": "MiPassword123!",
    "password_confirm": "MiPassword123!"
}
```

**Respuesta esperada (201 Created):**
```json
{
    "id": 3,
    "email": "usuario@ejemplo.com",
    "username": "usuario1",
    "message": "Cuenta creada. Revisa tu email para verificarla."
}
```

> **Nota:** Tras el registro se envía un email de verificación. En desarrollo, el link aparece en los logs de Docker:
> ```powershell
> docker compose logs backend --tail 30
> ```
> Busca una línea como:
> ```
> Subject: Verifica tu email en CryptoWorld
> http://localhost:8000/api/auth/verify-email/?token=...
> ```

---

## 4. Login (sin 2FA)

```
POST {{base_url}}/api/auth/login/
```

**Headers:**
```
Content-Type: application/json
```

**Body (raw JSON):**
```json
{
    "email": "usuario@ejemplo.com",
    "password": "MiPassword123!"
}
```

**Respuesta esperada (200 OK) — sin 2FA activo:**
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzcyNjc1MTIwLCJpYXQiOjE3NzI2NzE1MjAsImp0aSI6IjgxZDliOGIxNzQ4ZDQxZTViZGM2MGM2MDhmMDdjZWIyIiwidXNlcl9pZCI6M30.IWWdeF8UJF6zMd6BpSNrdDpaw48COPNC8YsGvZCuCaI",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3MzI3NjMyMCwiaWF0IjoxNzcyNjcxNTIwLCJqdGkiOiJiNjU4YjEwNGRiM2U0ZDg5YTM1MDg3YjBhZmJhYWUyNiIsInVzZXJfaWQiOjN9._GgoM2fwDQQKjIfnDzY7pluoAwuUUuQt7wmHReowk9c",
    "user_id": 3,
    "email": "usuario@ejemplo.com",
    "username": "usuario1",
    "requires_2fa": false
}
```

**Script en Tests (para guardar tokens automáticamente):**
```javascript
const r = pm.response.json();
if (r.access_token) {
    pm.environment.set("access_token", r.access_token);
    pm.environment.set("refresh_token", r.refresh_token);
    console.log("Tokens guardados correctamente");
}
```

---

## 5. Ver perfil — /me/

```
GET {{base_url}}/api/auth/me/
```

**Headers:**
```
Authorization: Bearer {{access_token}}
```

**Respuesta esperada (200 OK):**
```json
{
    "id": 1,
    "email": "usuario@ejemplo.com",
    "username": "usuario1",
    "is_email_verified": false,
    "is_2fa_enabled": false
}
```

**Error común (401):** el access_token ha expirado → renovar primero (ver sección 6).

---

## 6. Renovar Access Token

El access token expira cada 5 minutos. Cuando ocurra, usar el refresh token para obtener uno nuevo.

```
POST {{base_url}}/api/auth/token/refresh/
```

**Headers:**
```
Content-Type: application/json
```

**Body (raw JSON):**
```json
{
    "refresh": "{{refresh_token}}"
}
```

> **Importante:** este endpoint usa el campo `refresh` (no `refresh_token`), es el estándar de SimpleJWT.

**Respuesta esperada (200 OK):**
```json
{
    "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzcyNjc2NjU4LCJpYXQiOjE3NzI2NzI4NjIsImp0aSI6IjgxMjFjOTE2MTA0ODRjZDZiZmU5NmE5Nzk4ZmRkZjgyIiwidXNlcl9pZCI6M30.bcWKDBERGnZj2KPEXmTWFd7bW7RXoAR_K7sob2SHF3E",
    "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3MzI3Nzg1OCwiaWF0IjoxNzcyNjczMDU4LCJqdGkiOiIyNjliOWVlMDA2YWE0ZjM3YjQ0NjY5MmIxZDk2MjZlOSIsInVzZXJfaWQiOjN9.0VXspIZwe45DZy-I7FmFsLvnPhFldwW5PpqRmNbypS8"
}
```

**Script en Tests:**
```javascript
const r = pm.response.json();
if (r.access) {
    pm.environment.set("access_token", r.access);
    console.log("Access token renovado");
}
```

---

## 7. Logout

Invalida el refresh token en la blacklist. Después de esto, el refresh token ya no podrá usarse.

```
POST {{base_url}}/api/auth/logout/
```

**Headers:**
```
Authorization: Bearer {{access_token}}
Content-Type: application/json
```

**Body (raw JSON):**
```json
{
    "refresh_token": "{{refresh_token}}"
}
```

> **⚠️ Causa frecuente del error 400:** si la variable `{{refresh_token}}` no está definida en el entorno de Postman, se envía el texto literal `{{refresh_token}}` como string, que no es un JWT válido. Asegúrate de haber ejecutado primero el login con el script en **Tests** que guarda el token, o pega el valor directamente.

> **⚠️ Causa frecuente del error 400 (2):** después de llamar a `/token/refresh/`, SimpleJWT rota el refresh token. El anterior queda invalidado. Usa siempre el **último** refresh token recibido.

**Respuesta esperada (200 OK):**
```json
{
    "detail": "Sesión cerrada correctamente."
}
```

**Para verificar que funciona:** intentar renovar el token después del logout → debe devolver `401 Token is blacklisted`.

---

## 8. Verificación de Email

### 8.1 Obtener uid y token desde los logs Docker

El email se envía **en el momento del registro** y aparece en los logs de ese instante. Si haces `--tail 50` mucho después, es posible que ya no sea visible.

Usa este comando para buscar directamente en todos los logs:

```powershell
docker compose logs backend | Select-String "verify-email"
```

O si tienes muchos logs:

```powershell
docker compose logs backend 2>&1 | Select-String "uid="
```

Busca algo como:
```
http://localhost:3000/auth/verify-email/?uid=Mw&token=czpb8k-abc123...
```

> **Nota:** La URL apunta al frontend (`localhost:3000`). Los parámetros `uid` y `token` son los que necesitas para llamar a la API directamente desde Postman.

### 8.2 Verificar el email

El endpoint recibe **dos query params separados**: `uid` y `token`.

```
GET {{base_url}}/api/auth/verify-email/?uid=Mw&token=czpb8k-abc123...
```

En Postman, ve a la pestaña **Params** y añade:

| Key | Value |
|-----|-------|
| `uid` | el valor de `uid` copiado del log (ej. `Mw`) |
| `token` | el valor de `token` copiado del log (ej. `czpb8k-abc123`) |

**Respuesta esperada (200 OK):**
```json
{
    "message": "Email verificado correctamente."
}
```

> **⚠️ Error frecuente:** no confundir los dos parámetros. Si envías solo `?token=...` sin `uid`, el serializador devolverá `400 {"uid": ["This field is required."]}`.

### 8.3 Reenviar email de verificación

Si el link ha expirado o no llegó:

```
POST {{base_url}}/api/auth/verify-email/resend/
```

**Headers:**
```
Authorization: Bearer {{access_token}}
```

**Body:** vacío

**Respuesta esperada (200 OK):**
```json
{
    "detail": "Email de verificación enviado."
}
```

---

## 9. Recuperación de Contraseña

### 9.1 Solicitar el link de recuperación

```
POST {{base_url}}/api/auth/password-reset/
```

**Headers:**
```
Content-Type: application/json
```

**Body (raw JSON):**
```json
{
    "email": "usuario@ejemplo.com"
}
```

**Respuesta esperada (200 OK):**
```json
{
    "detail": "Si el email existe, recibirás un enlace de recuperación."
}
```

> **Nota:** La respuesta es siempre la misma tanto si el email existe como si no (por seguridad, para no revelar qué emails están registrados).

### 9.2 Obtener uid y token de los logs

```powershell
docker compose logs backend --tail 50
```

Busca el link completo, que tiene esta forma:
```
http://localhost:3000/reset-password?uid=MQ&token=bxyz12-abc...
```

Copia `uid` y `token` por separado.

### 9.3 Confirmar nueva contraseña

```
POST {{base_url}}/api/auth/password-reset/confirm/
```

**Headers:**
```
Content-Type: application/json
```

**Body (raw JSON):**
```json
{
    "uid": "MQ",
    "token": "bxyz12-abc...",
    "new_password": "NuevaPassword456!"
}
```

**Respuesta esperada (200 OK):**
```json
{
    "detail": "Contraseña restablecida correctamente."
}
```

---

## 10. Cambio de Contraseña

Requiere estar autenticado y conocer la contraseña actual.

```
POST {{base_url}}/api/auth/change-password/
```

**Headers:**
```
Authorization: Bearer {{access_token}}
Content-Type: application/json
```

**Body (raw JSON):**
```json
{
    "current_password": "MiPassword123!",
    "new_password": "OtraPassword789!"
}
```

**Respuesta esperada (200 OK):**
```json
{
    "detail": "Contraseña cambiada correctamente."
}
```

**Error (400) si la contraseña actual es incorrecta:**
```json
{
    "detail": "La contraseña actual es incorrecta."
}
```

---

## 11. Configurar 2FA (TOTP)

Genera el secreto TOTP y el QR para escanear con Google Authenticator.

```
POST {{base_url}}/api/auth/2fa/setup/
```

**Headers:**
```
Authorization: Bearer {{access_token}}
```

**Body:** vacío

**Respuesta esperada (200 OK):**
```json
{
    "secret": "JBSWY3DPEHPK3PXP",
    "qr_code": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
}
```

### Cómo ver el QR en Postman

1. Copia el valor de `qr_code` (incluido el prefijo `data:image/png;base64,...`).
2. Abre un navegador y pega el texto en la barra de direcciones → verás la imagen del QR.
3. Alternativamente, crea un archivo HTML con `<img src="data:image/png;base64,...">`.

### Escanear con Google Authenticator

1. Abre Google Authenticator (o Authy).
2. `+` → **Escanear código QR**.
3. Apunta la cámara al QR → se añade una cuenta llamada **CryptoWorld**.

> **Guarda el `secret`**: si pierdes el móvil, necesitarás el secreto para recuperar el 2FA.

---

## 12. Activar 2FA

Confirma que el setup fue correcto con el primer código generado por la app.

```
POST {{base_url}}/api/auth/2fa/enable/
```

**Headers:**
```
Authorization: Bearer {{access_token}}
Content-Type: application/json
```

**Body (raw JSON):**
```json
{
    "totp_code": "123456"
}
```

> Sustituye `123456` por el código actual que muestra Google Authenticator (cambia cada 30 segundos).

**Respuesta esperada (200 OK):**
```json
{
    "detail": "2FA activado correctamente."
}
```

**Error (400) si el código es incorrecto:**
```json
{
    "detail": "Código TOTP incorrecto."
}
```

---

## 13. Login con 2FA activo

El login pasa a ser un proceso de dos pasos.

### Paso 1 — Verificar contraseña

```
POST {{base_url}}/api/auth/login/
```

**Body:**
```json
{
    "email": "usuario@ejemplo.com",
    "password": "MiPassword123!"
}
```

**Respuesta (200 OK) cuando 2FA está activo:**
```json
{
    "requires_2fa": true,
    "pre_auth_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

> No se devuelven `access_token` ni `refresh_token` todavía.

**Script en Tests:**
```javascript
const r = pm.response.json();
if (r.pre_auth_token) {
    pm.environment.set("pre_auth_token", r.pre_auth_token);
    console.log("pre_auth_token guardado. Procede con /2fa/login/");
}
```

### Paso 2 — Verificar código TOTP

```
POST {{base_url}}/api/auth/2fa/login/
```

**Headers:**
```
Content-Type: application/json
```

**Body (raw JSON):**
```json
{
    "pre_auth_token": "{{pre_auth_token}}",
    "totp_code": "123456"
}
```

**Respuesta esperada (200 OK):**
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Script en Tests:**
```javascript
const r = pm.response.json();
if (r.access_token) {
    pm.environment.set("access_token", r.access_token);
    pm.environment.set("refresh_token", r.refresh_token);
    console.log("Login con 2FA completado. Tokens guardados.");
}
```

**Error (401) si el pre_auth_token ha expirado (>5 min):**
```json
{
    "detail": "Token inválido o expirado."
}
```
→ Vuelve al Paso 1.

---

## 14. Desactivar 2FA

Requiere confirmar con un código TOTP vigente.

```
POST {{base_url}}/api/auth/2fa/disable/
```

**Headers:**
```
Authorization: Bearer {{access_token}}
Content-Type: application/json
```

**Body (raw JSON):**
```json
{
    "totp_code": "123456"
}
```

**Respuesta esperada (200 OK):**
```json
{
    "detail": "2FA desactivado correctamente."
}
```

---

## 15. Endpoints de datos

### Listar activos (mock data)

```
GET {{base_url}}/api/assets/
```

**Headers:**
```
Authorization: Bearer {{access_token}}
```

**Respuesta esperada (200 OK):** lista de activos criptográficos con datos de ejemplo.

### Ejecutar análisis (stub)

```
POST {{base_url}}/api/analysis/run/
```

**Headers:**
```
Authorization: Bearer {{access_token}}
Content-Type: application/json
```

**Body (raw JSON):**
```json
{
    "symbol": "BTC",
    "indicator": "RSI"
}
```

---

## 16. Flujo completo de prueba

Orden recomendado para probar el sistema completo desde cero:

```
1.  GET  /api/health/                          → Verificar que el servidor responde
2.  POST /api/auth/register/                   → Crear cuenta
3.       [revisar logs Docker para el token]
4.  GET  /api/auth/verify-email/?token=...     → Verificar email
5.  POST /api/auth/login/                      → Login (guarda access + refresh)
6.  GET  /api/auth/me/                         → Ver perfil (is_email_verified=true)
7.  GET  /api/assets/                          → Acceder a datos protegidos
8.  POST /api/auth/change-password/            → Cambiar contraseña
9.  POST /api/auth/2fa/setup/                  → Obtener QR y escanear con app
10. POST /api/auth/2fa/enable/                 → Activar 2FA con primer código
11. POST /api/auth/logout/                     → Cerrar sesión (blacklist refresh)
12. POST /api/auth/login/                      → Login de nuevo (requires_2fa=true)
13. POST /api/auth/2fa/login/                  → Segundo factor con código TOTP
14. GET  /api/auth/me/                         → Verificar (is_2fa_enabled=true)
15. POST /api/auth/2fa/disable/                → Desactivar 2FA
16. POST /api/auth/password-reset/             → Solicitar recuperación de contraseña
17.      [revisar logs Docker para uid+token]
18. POST /api/auth/password-reset/confirm/     → Establecer nueva contraseña
```

---

## Errores comunes y soluciones

| Error | Causa | Solución |
|-------|-------|----------|
| `401 Authentication credentials were not provided` | No se envía el `Authorization` header | Añadir `Authorization: Bearer {{access_token}}` |
| `401 Token is invalid or expired` | El access token ha expirado | Usar `/token/refresh/` para obtener uno nuevo |
| `401 Token is blacklisted` | Se intentó usar el refresh token después del logout | Hacer login de nuevo |
| `400 Este campo es requerido` | Falta un campo en el body | Revisar el JSON enviado |
| `400 Código TOTP incorrecto` | El código de 6 dígitos no es válido (expirado) | Esperar al siguiente ciclo de 30s y volver a intentar |
| `401 Token inválido o expirado` (en /2fa/login/) | Han pasado más de 5 min desde el login paso 1 | Repetir `POST /auth/login/` para obtener nuevo pre_auth_token |
| `Connection refused` | El servidor Docker no está corriendo | `docker compose up` en el directorio del proyecto |

---

*Última actualización: Marzo 2026*
