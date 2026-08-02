# Política de seguridad — CryptoWorld

CryptoWorld conecta con exchanges reales y ejecuta órdenes con dinero de sus
usuarios. Este documento describe los controles vigentes y cómo reportar un
problema.

## Reportar una vulnerabilidad

Abre un aviso privado en **Security → Report a vulnerability** del repositorio.
No abras un issue público para fallos explotables.

Incluye: versión o commit afectado, pasos de reproducción, impacto observado y,
si lo tienes, una propuesta de mitigación. Se acusa recibo en un plazo de 72
horas.

## Controles vigentes

### Autenticación

- JWT de vida corta (60 min) con refresh rotatorio y blacklist en logout.
- 2FA TOTP opcional, con códigos de recuperación de un solo uso.
- Verificación de email obligatoria antes del primer login.
- Rate limiting específico en login, registro, reset de contraseña y 2FA.
- Respuestas indistinguibles en los flujos de recuperación: no se revela si un
  email existe.

Los tokens viven en `localStorage`. Es una decisión consciente, documentada con
sus implicaciones en `info/Seguridad_Auth.md`; la CSP mitiga el vector práctico
al impedir la ejecución de scripts de terceros.

### Credenciales de exchange

- Cifradas con Fernet (AES-128-CBC + HMAC-SHA256) antes de tocar la base de
  datos. **La API nunca las devuelve**, ni siquiera al propietario.
- Clave de cifrado **dedicada** (`CREDENTIALS_ENCRYPTION_KEYS`), separada de
  `DJANGO_SECRET_KEY`: rotar el secreto de firma no compromete ni invalida las
  credenciales guardadas.
- Anillo de claves con rotación sin downtime — la primera cifra, todas
  descifran.
- Derivación con HKDF-SHA256 y etiqueta de dominio cuando el material es una
  passphrase en lugar de una clave Fernet.
- Toda conexión nace en **testnet**; operar en real exige activarlo de forma
  explícita.

### Ejecución de órdenes reales

Ambas vías —promoción automática paper→real y orden manual— comparten los
mismos controles, con una única definición de la política:

- **Límite de pérdida diaria** y **límite de concentración por activo** que
  bloquean compras. Las ventas nunca se bloquean: reducir exposición siempre
  está permitido.
- **Rastro de auditoría completo** (`LiveOrderRecord`): todo intento queda
  registrado —enviado, fallido o bloqueado— con su motivo, su nocional y el
  precio de ejecución que devolvió el exchange.
- **Idempotencia** por `client_order_id`, garantizada con una restricción única
  en base de datos: dos peticiones concurrentes no pueden duplicar una orden.
- **Kill-switch**: un fallo del broker en la promoción automática la desactiva
  y guarda el motivo, en lugar de reintentar en bucle.
- Límite de tasa estricto (`trading_order`) en el endpoint de envío.
- Eventos estructurados en el canal de auditoría `core.audit`, que nunca se
  silencia por nivel de log.

### Transporte y cabeceras

Con `DJANGO_DEBUG=False` se activan HSTS (1 año, `includeSubDomains`,
`preload`), redirección a HTTPS, cookies `Secure` y `SECURE_PROXY_SSL_HEADER`.
Siempre activos, con independencia del transporte: `nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy`, `Cross-Origin-Opener-Policy` y
cookies `HttpOnly`.

Nginx añade Content-Security-Policy, `Permissions-Policy` y rate limiting por
IP.

`manage.py check --deploy --fail-level WARNING` es un paso obligatorio de CI:
una regresión en cualquiera de estos ajustes rompe la build.

### Arranque a prueba de fallos

Con `DJANGO_DEBUG=False`, la aplicación **aborta el arranque** si:

- `DJANGO_SECRET_KEY` es la clave de ejemplo, empieza por `django-insecure-` o
  mide menos de 32 caracteres;
- `DJANGO_ALLOWED_HOSTS` está vacío o contiene `*`.

Es deliberado: un despliegue mal configurado debe fallar de forma ruidosa, no
quedarse escuchando en un estado vulnerable.

### Límites de tasa

| Ámbito | Límite por defecto | Variable |
|---|---|---|
| Anónimo (global) | 120/min | `THROTTLE_ANON` |
| Autenticado (global) | 600/min | `THROTTLE_USER` |
| Órdenes reales | 20/min | `THROTTLE_TRADING_ORDER` |
| Login | 10/min | — |
| Registro | 10/hora | — |
| Reset de contraseña | 5/hora | — |
| Generación de estrategias | 10/hora | — |

### Cadena de suministro

Cada ejecución de CI corre `pip-audit --strict` sobre `requirements.txt` y
`npm audit --audit-level=high` sobre el frontend. Las versiones de Python están
fijadas de forma exacta para que la construcción sea reproducible.

## Alcance

**Dentro:** el código de este repositorio y su configuración de despliegue.

**Fuera:** vulnerabilidades de los exchanges o proveedores de datos de
terceros; hallazgos que exijan acceso físico o credenciales ya comprometidas;
informes generados por escáneres automáticos sin impacto demostrado.
