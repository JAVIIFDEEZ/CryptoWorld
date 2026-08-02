# Auditoría técnica de CryptoWorld — agosto 2026

Revisión completa del backend, el frontend y la infraestructura, con las
correcciones aplicadas. Alcance: 23 000 líneas de código, 45 endpoints,
11 tablas.

**Estado de partida:** 170 tests, 50 % de cobertura, `manage.py check
--deploy` con 6 avisos de seguridad de Django (`W004` HSTS ausente,
`W008` sin redirección a HTTPS, `W009` SECRET_KEY débil, `W012` y `W016`
cookies sin `Secure`, y `W018` DEBUG activo por ser el valor por
defecto; cinco de ellos persistían incluso configurando `DEBUG=False`).

**Estado final:** 293 tests, 70 % de cobertura, `check --deploy` sin
ningún aviso, lint limpio, esquema OpenAPI generado desde el código.

---

## Resumen de hallazgos

| Sev. | # | Estado |
|---|---:|---|
| Crítico | 7 | Corregidos |
| Alto | 9 | Corregidos |
| Medio | 8 | 7 corregidos, 1 documentado |
| Total | 24 | 23 corregidos |

---

## Críticos

### C1 — `SECRET_KEY` con valor por defecto en el código fuente

`settings.py` recurría a `"django-insecure-change-this-in-production-key-12345"`
si faltaba la variable de entorno. Esa clave firma los JWT (HS256), los
enlaces de verificación de email y los de recuperación de contraseña: un
despliegue que olvidara definirla quedaba con una clave publicada en el
repositorio, y cualquiera podía emitir sesiones de cualquier usuario.

**Corrección.** Sin `DJANGO_SECRET_KEY` y con `DEBUG=False`, el proceso
no arranca (`ImproperlyConfigured`). Se exige además una longitud mínima
de 50 caracteres. En desarrollo se genera una efímera por arranque, para
que no exista ninguna constante en el código que pueda acabar firmando en
producción.

### C2 — `DEBUG` activo por defecto

`os.environ.get("DJANGO_DEBUG", "True") == "True"`: un despliegue sin la
variable arrancaba en modo depuración, devolviendo trazas completas,
consultas SQL y valores de configuración en cada error.

**Corrección.** El valor por defecto pasa a `False`. La configuración
por omisión es ahora la segura.

### C3 — Sin cabeceras de seguridad ni cookies protegidas

No existían `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`,
`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_PROXY_SSL_HEADER`,
`SECURE_CONTENT_TYPE_NOSNIFF` ni `CSRF_TRUSTED_ORIGINS`. La cookie de
sesión del admin de Django viajaba sin el flag `Secure`.

**Corrección.** Bloque completo de cabeceras y flags, con las que
dependen de TLS condicionadas a `DEBUG=False`, y exención del healthcheck
en la redirección a HTTPS para que la sonda interna no falle.
`check --deploy --fail-level WARNING` se incorpora al pipeline.

### C4 — El registro no aplicaba la política de contraseñas

`RegisterSerializer` solo exigía `min_length=8` y `RegisterUserUseCase`
nunca llamaba a `validate_password`. Se podían crear cuentas con
`12345678` o `password`, contraseñas que el cambio y la recuperación sí
rechazaban. La política más débil regía justo en el punto de entrada.

**Corrección.** `AUTH_PASSWORD_VALIDATORS` se aplica en los tres flujos,
con mínimo elevado a 12 caracteres (NIST SP 800-63B). La constante es
única (`settings.PASSWORD_MIN_LENGTH`) y el cliente la comparte.

### C5 — Cambiar la contraseña no cerraba las sesiones abiertas

`user.set_password(); user.save()` y nada más. Los refresh tokens seguían
vivos siete días y los access sesenta minutos. Un atacante con la sesión
comprometida conservaba el acceso justo después de la acción con la que
la víctima intenta expulsarlo.

**Corrección.** Revocación en dos mitades: blacklist de los refresh
tokens y claim `cred_epoch` comparado con `credentials_changed_at` para
invalidar los access ya emitidos. Se aplica al cambiar la contraseña, al
restablecerla, al confirmar un cambio de email y al bloquear una cuenta
desde el panel. El dispositivo que hace el cambio recibe tokens nuevos y
no se auto-desconecta.

*Nota de implementación.* La primera versión comparaba el claim `iat`,
que tiene resolución de un segundo: un token emitido en el mismo segundo
que el cambio era indistinguible de uno anterior. Lo detectó un test que
fallaba de forma intermitente. Se sustituyó por una marca con precisión
de microsegundos.

### C6 — Cualquier `is_staff` podía crear superusuarios

`AdminUserListView.post` llamaba a `create_superuser` para todo
administrador creado por la API, y `AdminUserDetailView` fijaba
`is_staff = is_superuser = bool(is_admin)`. El nivel más bajo de
administración concedía de hecho el más alto, sin traza alguna.

**Corrección.** Modelo de dos niveles: staff opera el panel;
superusuario es el único que crea administradores y concede privilegios.
Los administradores nuevos se crean staff salvo petición explícita. Se
añade la protección del último superusuario activo, contrapartida de la
regla que impide degradarse a uno mismo.

### C7 — Sin registro de auditoría

Ni logins, ni fallos, ni cambios de credenciales, ni acciones
administrativas dejaban rastro consultable.

**Corrección.** Tabla `audit_log` con actor, resultado, recurso, IP,
user-agent, identificador de correlación y metadatos, más el logger
`cryptoworld.audit` en JSON para alertado. El actor es `SET_NULL` con
copia del email, de modo que la traza sobrevive al borrado de la cuenta.
Retención configurable.

---

## Altos

### A1 — La URL de la caché Redis se construía mal

```python
"LOCATION": REDIS_URL.rstrip("/0") + "/1"
```

`rstrip` elimina **todos** los caracteres finales del conjunto
`{'/', '0'}`, no el sufijo. Con `redis://host:6379` —el formato que
inyectan Railway y Upstash, sin índice de base de datos— el resultado era
`redis://host:637/1`: un puerto que no existe. Con la caché rota caen
también el rate limiting y el cacheo de datos de mercado.

**Corrección.** La URL se parsea con `urlsplit` y se reemplaza solo el
componente de ruta.

### A2 — Sin manejador de excepciones global

Los endpoints de análisis, mercado y on-chain invocan APIs externas sin
`try/except`. Un timeout de Binance producía un 500 con traza (si DEBUG)
o una página HTML de error. El contrato de error era además inconsistente:
`{"error": ...}`, `{"detail": ...}` y el diccionario crudo del serializer
conviviendo.

**Corrección.** Manejador único con envolvente estable
(`{"error": {"code", "message", "details"}, "request_id"}`) y códigos
programáticos. El detalle interno nunca llega al cliente; queda en los
logs asociado al `request_id`.

### A3 — Listados sin paginación

`/api/admin/users/` volcaba la tabla completa de usuarios en cada
petición: coste de memoria del proceso web y denegación de servicio
trivial.

**Corrección.** Paginación con techo de página (200) y endpoint aparte de
contadores globales, ya que el panel no puede derivarlos de una página.
El cliente pasa a búsqueda y paginación de servidor.

### A4 — Índices ausentes en tablas de crecimiento ilimitado

`market_data_snapshots` (~144 filas/día por activo) solo tenía índice en
`timestamp`, mientras la consulta de sparklines filtra por activo **y**
ventana temporal. `trade_history`, `positions` y `price_alerts` tampoco
tenían índices compuestos para sus consultas habituales.

**Corrección.** Seis índices compuestos y tareas periódicas de retención
para snapshots y auditoría.

### A5 — Emails sin normalizar

El registro comprobaba unicidad con coincidencia exacta y el cambio de
email con `iexact`. `Foo@x.com` y `foo@x.com` creaban dos cuentas
distintas, y el login era sensible a mayúsculas.

**Corrección.** Normalización a minúsculas en todos los flujos, incluidos
el contador de intentos fallidos y las búsquedas.

### A6 — Registro no atómico

`RegisterView` creaba el usuario y después establecía la contraseña. Un
fallo entre ambos pasos dejaba un usuario con el email ocupado y sin
contraseña utilizable: irrecuperable e irregistrable.

**Corrección.** Ambos pasos en una transacción; el email de verificación
se encola después de confirmarla.

### A7 — Importes monetarios en coma flotante

Los serializers de portfolio, operaciones y alertas usaban `FloatField` y
las vistas hacían `float(...)` antes de persistir en columnas
`Decimal(38, 18)`. Un doble precisión tiene ~15-17 dígitos
significativos: las cantidades de 18 decimales se redondeaban en
silencio, y el error se acumulaba en el PnL.

**Corrección.** `Decimal` de extremo a extremo: serializers, DTOs y casos
de uso. Verificado con un test que comprueba que
`0.123456789012345678` llega intacto a la base de datos.

### A8 — Imagen de producción en modo desarrollo y como root

El `Dockerfile` del backend arrancaba con `manage.py runserver`
—monohilo, sin límites y con depurador—, como root, sin healthcheck. El
frontend usaba `npm install` en vez de `npm ci`, de modo que la imagen no
era reproducible.

**Corrección.** Multi-stage, usuario sin privilegios (uid 10001),
gunicorn, `HEALTHCHECK` contra la sonda de vitalidad y `npm ci`.

### A9 — Token de verificación de email sin sal

`TimestampSigner()` sin `salt` usa la sal por defecto de
`django.core.signing`, compartida con cualquier otro uso del proyecto.

**Corrección.** Sal propia por propósito (`core.email-verification`),
igual que ya hacía el flujo de cambio de email.

---

## Medios

| # | Hallazgo | Corrección |
|---|---|---|
| M1 | Sin esquema de API; el README documentaba 31 endpoints existiendo 45 | OpenAPI 3 generado desde el código en `/api/schema/`, `/api/docs/` y `/api/redoc/` |
| M2 | Sin configuración de logging ni correlación de peticiones | Logging JSON por stdout con `request_id` y cabecera `X-Request-ID` |
| M3 | Un único healthcheck sondeando dependencias, usado como liveness | Sondas separadas: `/api/health/live/` (proceso) y `/api/health/` (dependencias, 503 si fallan) |
| M4 | 37 líneas de `views.py` con doble codificación (`â€"`, `Ã³`) y tres ficheros con BOM | Reparado y `.gitattributes` para que no se repita |
| M5 | Versión fijada a `"1.0.0"` en el healthcheck estando el proyecto en la 1.138 | Se lee de `APP_VERSION` |
| M6 | CI ejecutaba los tests con `--no-cov`: la cobertura podía caer sin aviso | Umbral en `pytest.ini` como trinquete |
| M7 | CI no cubría las ramas de trabajo, sin lint ni auditoría de dependencias | Jobs de lint, `check --deploy`, esquema, `pip-audit` y `npm audit` |
| M8 | Cabeceras de nginx perdidas en el bloque de assets; sin CSP | Fichero de cabeceras incluido desde cada `location`, con CSP estricta |

### Documentado, no corregido

**Contrato inconsistente de los indicadores técnicos.** Cada indicador
devuelve sus series con nombres distintos (`series` en RSI,
`series_macd`/`series_signal`/`series_histogram` en MACD,
`series_sma20`/`series_sma50` en SMA…). Unificarlo rompería al cliente
actual, así que corresponde a una refactorización propia y no a un efecto
colateral de esta revisión. Queda fijado por tests que documentan la
forma real de cada respuesta.

---

## Cobertura de pruebas

La revisión encontró el motor de análisis técnico —920 líneas que
calculan lo que el usuario lee para decidir— con un **5 %** de cobertura,
y la aritmética de posiciones con un **17 %**. Es la clase de código
donde un fallo no se manifiesta: un PnL mal calculado no lanza ninguna
excepción, simplemente muestra una cifra equivocada.

| Módulo | Antes | Después |
|---|---:|---:|
| `technical_analysis_service.py` | 5 % | 88 % |
| `open_position.py` | 17 % | 86 % |
| `close_position.py` | 17 % | 86 % |
| `scale_position.py` | 19 % | 81 % |
| `manage_alerts.py` | 30 % | 85 % |
| `interfaces/api/views.py` | 42 % | 65 % |
| **Total del backend** | **50 %** | **70 %** |

Sigue por debajo del resto `get_positions.py` (22 %), que solo agrega y
serializa posiciones ya cubiertas por los tests de apertura y cierre.

Tests añadidos (123 nuevos, 293 en total):

- `test_security_controls.py` — 32 tests de los controles corregidos.
- `test_portfolio_arithmetic.py` — 20 tests con importes calculados a
  mano: coste medio ponderado, PnL en LONG y SHORT, precisión decimal.
- `test_technical_analysis_service.py` — 41 tests sobre series
  sintéticas de forma conocida.
- `test_alerts_and_trades.py` — 27 tests del ciclo de alertas,
  operaciones, watchlist y retención.

---

## Decisiones deliberadas

**No se ejecuta `ruff format`.** Reformatearía 57 de los 114 ficheros del
backend de una vez, y un diff así haría irrevisable el resto del trabajo.
Es una decisión de estilo que merece su propio commit.

**No se activa el conjunto `UP` (pyupgrade) del linter.** El código usa
de forma consistente `Optional[X]` y `List[X]`; reescribir noventa
anotaciones a sintaxis PEP 604 no corrige ningún defecto.

**El umbral de cobertura se fija en 68 %, no en 80 %.** Un umbral por
encima de lo alcanzado deja el pipeline permanentemente en rojo, y así es
como se acaba desactivando la comprobación. Puesto justo por debajo de lo
logrado funciona como trinquete: nada puede bajarla, y subirlo es una
decisión consciente al añadir tests.

**Los tokens siguen en `localStorage`.** Migrar a cookies `HttpOnly`
obliga a rediseñar el flujo de autenticación completo. Se documenta como
riesgo aceptado en `SECURITY.md`, con la CSP estricta, los access tokens
de 15 minutos y la revocación global como mitigaciones.

---

## Trabajo pendiente sugerido

1. Migrar la autenticación a cookies `HttpOnly` con CSRF.
2. Unificar el contrato de series de los indicadores técnicos.
3. Cifrar el secreto TOTP en reposo, cuando el despliegue disponga de
   gestión de claves.
4. Aplicar `ruff format` en un commit aislado y añadir la verificación al
   pipeline.
5. Subir la cobertura de `tasks.py` y de los clientes de APIs externas,
   los dos módulos que más se benefician de tests con dobles de prueba.
