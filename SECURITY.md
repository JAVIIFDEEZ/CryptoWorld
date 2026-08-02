# Seguridad — CryptoWorld

Modelo de seguridad de la plataforma: qué se protege, cómo, y qué riesgos
se aceptan de forma consciente. Acompaña al informe de la revisión en
[`info/Auditoria_2026.md`](info/Auditoria_2026.md).

---

## Superficie del sistema

| Componente | Exposición | Autenticación |
|---|---|---|
| SPA React (nginx) | Pública, HTTPS | — |
| API Django (`/api/`) | Tras el proxy inverso | JWT Bearer |
| Django Admin (`/admin/`) | Tras el proxy inverso | Sesión + CSRF |
| PostgreSQL | Red interna, sin puerto publicado | Usuario/contraseña |
| Redis | Red interna, sin puerto publicado | — |
| Worker y scheduler Celery | Sin exposición de red | — |

---

## Autenticación

### Contraseñas

- Almacenadas con **PBKDF2-SHA256** (algoritmo por defecto de Django).
- Política única en registro, cambio y recuperación
  (`AUTH_PASSWORD_VALIDATORS`): mínimo **12 caracteres**, no común, no
  puramente numérica y sin parecido con los datos de la cuenta.
- El mínimo de 12 caracteres sigue NIST SP 800-63B, que prioriza longitud
  sobre reglas de composición.

### Doble factor (2FA)

- TOTP RFC 6238 con ventana de ±30 s, compatible con Google
  Authenticator y Authy.
- 10 códigos de recuperación de un solo uso, almacenados **hasheados**
  con el mismo esquema que las contraseñas. Se muestran en claro una
  única vez.
- Regenerarlos exige un código TOTP vigente: no basta con tener la sesión
  abierta.

### Sesiones (JWT)

| Token | Vida | Revocable |
|---|---|---|
| Access | 15 min | Sí, por marca de revocación (ver abajo) |
| Refresh | 7 días | Sí, blacklist de SimpleJWT |

La revocación tiene dos mitades, porque los dos tipos de token se
invalidan de forma distinta:

1. **Refresh**: se listan en `OutstandingToken` y pasan a la blacklist.
2. **Access**: no son revocables individualmente (son autónomos y se
   validan solo con la firma). Cada token lleva el claim `cred_epoch` con
   la marca de revocación vigente al emitirlo;
   `CredentialEpochJWTAuthentication` lo compara con
   `user.credentials_changed_at` y rechaza los anteriores.

Se revocan **todas** las sesiones al:

- cambiar la contraseña (el dispositivo que la cambia recibe tokens
  nuevos y no se auto-desconecta),
- restablecerla con el enlace de recuperación,
- confirmar un cambio de email (es la credencial de login),
- bloquear la cuenta desde el panel de administración.

Activar o desactivar el doble factor **no** revoca sesiones: el usuario
ha demostrado ambos factores en el momento de hacerlo. Queda registrado
en la traza de auditoría.

---

## Control de acceso

Dos niveles administrativos, con el privilegio máximo reservado:

| Acción | Staff | Superusuario |
|---|:--:|:--:|
| Listar y buscar usuarios | ✅ | ✅ |
| Bloquear y desbloquear cuentas | ✅ | ✅ |
| Forzar verificación de email | ✅ | ✅ |
| Sincronizar el catálogo de mercado | ✅ | ✅ |
| Crear administradores | ❌ | ✅ |
| Conceder o revocar privilegios | ❌ | ✅ |

Salvaguardas:

- Nadie puede bloquearse ni degradarse a sí mismo.
- No se puede dejar el sistema sin ningún superusuario activo.
- Todo cambio de privilegios queda en el registro de auditoría con actor,
  destinatario, IP y momento.

---

## Protección frente a abuso

| Control | Ámbito | Límite |
|---|---|---|
| `AnonRateThrottle` | Por IP, global | 120/min |
| `UserRateThrottle` | Por usuario | 1000/hora |
| `ScopedRateThrottle` | Login | 10/min por IP |
| `ScopedRateThrottle` | Registro | 10/hora por IP |
| `ScopedRateThrottle` | Recuperación de contraseña | 5/hora por IP |
| Bloqueo de cuenta | Contraseña | 8 fallos → 15 min |
| Bloqueo de cuenta | Segundo factor | 5 fallos → 15 min |
| `limit_req` (nginx) | `/api/` | 30 r/min con ráfaga de 20 |

El límite por IP no cubre el ataque realista —una botnet repartiendo
intentos contra una sola cuenta nunca lo alcanza—, por eso el contador
por cuenta es imprescindible. El del segundo factor es más estricto
porque su espacio de claves son solo seis dígitos.

Los contadores viven en Redis con expiración automática: el bloqueo se
levanta solo. Si Redis no está disponible el guardia **se abre**
(fail-open): un servicio degradado es preferible a dejar fuera a todos
los usuarios.

---

## Enumeración de cuentas

Los endpoints que aceptan un email responden igual exista o no:

- **Login**: mismo mensaje y mismo código para credenciales inválidas.
- **Recuperación de contraseña**: siempre "si el email existe, recibirás
  un enlace"; el envío se despacha de forma asíncrona.
- **Reenvío de verificación**: misma respuesta en todos los casos.

---

## Tokens firmados

Cada propósito criptográfico usa su **propia sal**, de modo que un token
emitido para un flujo no vale en otro:

| Flujo | Mecanismo | Sal | Validez |
|---|---|---|---|
| Verificación de email | `TimestampSigner` | `core.email-verification` | 3 días |
| Cambio de email | `signing.dumps` | `core.email-change` | 24 h |
| Recuperación de contraseña | `default_token_generator` | — (incluye el hash de la contraseña) | 24 h |
| Pre-autenticación 2FA | JWT `pre_2fa` | — | 5 min |

El token de recuperación se invalida solo al usarse, porque Django
incorpora el hash de la contraseña actual a la firma.

---

## Cabeceras y transporte

Servidas por nginx (`frontend/security-headers.conf`, incluido desde cada
bloque `location` — nginx **no** hereda `add_header` en un `location` que
declare cabeceras propias) y por Django (`SecurityMiddleware`):

- `Content-Security-Policy` sin `unsafe-inline` ni `unsafe-eval` en
  scripts.
- `Strict-Transport-Security` con `includeSubDomains` y `preload`.
- `X-Content-Type-Options: nosniff`.
- `X-Frame-Options: DENY` y `frame-ancestors 'none'`.
- `Referrer-Policy: strict-origin-when-cross-origin`.
- `Permissions-Policy` denegando cámara, micrófono, ubicación y pagos.
- `Cross-Origin-Opener-Policy` y `Cross-Origin-Resource-Policy`.

TLS 1.2 y 1.3 con la lista de cifrados Mozilla Intermediate. Cookies de
sesión y CSRF con `Secure`, `HttpOnly` y `SameSite=Lax`.

`manage.py check --deploy --fail-level WARNING` forma parte del pipeline:
cualquier aviso de seguridad de Django detiene la integración.

---

## Auditoría

La tabla `audit_log` registra quién hizo qué, cuándo, desde dónde y con
qué resultado. Eventos cubiertos: inicios de sesión (correctos, fallidos
y bloqueados), cierres de sesión, retos y resultados del segundo factor,
alta y baja de 2FA, registro, verificación de email, cambios de
contraseña y de email, borrado de cuenta y toda acción administrativa.

Decisiones de diseño:

- **Nunca** se almacena el secreto involucrado: solo el hecho.
- El actor es `SET_NULL` y se guarda además `actor_email`, para que la
  traza sobreviva al borrado de la cuenta — que es cuando más falta hace.
- Escribir en la traza jamás interrumpe la operación auditada: un fallo
  al registrar se registra y se continúa.
- Retención de 365 días por defecto (configurable). Contiene IP y
  user-agent, así que conservarla indefinidamente sería a la vez coste y
  exposición innecesaria.

En paralelo, todo evento sale por el logger `cryptoworld.audit` en JSON,
para alertado en tiempo real (por ejemplo, ráfagas de `login.failure`).

Cada petición lleva un identificador de correlación (`X-Request-ID`) que
aparece en todos los logs que genera y en el cuerpo de cualquier error,
de modo que una incidencia reportada por un usuario se localiza sin
ambigüedad.

---

## Riesgos aceptados

### Tokens JWT en `localStorage`

**Riesgo.** Un XSS que llegue a ejecutarse puede leer el token, cosa que
no ocurriría con cookies `HttpOnly`.

**Por qué se acepta.** Migrar a cookies obliga a rediseñar el flujo de
autenticación completo (CSRF en todas las mutaciones, gestión de
`SameSite` para el dominio del frontend, cambios en el cliente y en los
tests). Es una refactorización planificable, no un parche.

**Mitigaciones vigentes.**

- CSP estricta sin `unsafe-inline` ni `unsafe-eval` en `script-src`: sin
  ejecución de script inyectado, no hay desde dónde leer el token.
- React escapa por defecto y el código no usa `dangerouslySetInnerHTML`
  en ninguna parte (verificado).
- Access tokens de 15 minutos con rotación de refresh.
- Revocación global por `credentials_changed_at`: al cambiar la
  contraseña, un token robado deja de servir de inmediato.

### Secreto TOTP en claro en la base de datos

**Riesgo.** Quien obtenga acceso de lectura a la tabla `users` puede
generar códigos TOTP válidos.

**Por qué se acepta.** El secreto tiene que ser recuperable para
verificar cada código, así que cifrarlo requiere gestión de claves
(KMS o similar) que este despliegue no tiene. Además, quien ya tiene
lectura arbitraria de la base de datos dispone de vectores más directos.

**Mitigación.** La base de datos no publica puerto al exterior y solo es
accesible desde la red interna de contenedores.

### Auditoría de dependencias no bloqueante

`pip-audit` y `npm audit` se ejecutan en cada integración pero con
`continue-on-error`: una CVE publicada aguas arriba no debe bloquear un
despliegue urgente. El resultado es visible en cada ejecución y debe
revisarse.

---

## Reportar una vulnerabilidad

Escribe a **javierfernandezdelamo@gmail.com** con el asunto
`[SEGURIDAD] CryptoWorld`. Incluye pasos de reproducción e impacto.
No abras una incidencia pública hasta que la vulnerabilidad esté
corregida.
