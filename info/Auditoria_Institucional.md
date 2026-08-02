# Auditoría técnica — CryptoWorld

> **Motor cuantitativo.** Las brechas del generador de estrategias (G1 control
> de multiplicidad, G8 registro de experimentos, G9 honestidad de presentación)
> se documentan aparte, en [`Motor_Cuantitativo.md`](Motor_Cuantitativo.md).

**Alcance:** backend Django/DRF (~31 300 LOC), frontend React/TypeScript
(~29 500 LOC), infraestructura de despliegue (Docker, Nginx, Railway) y
canalización de integración continua.

**Criterio aplicado — «grado institucional»:** el sistema conecta con
exchanges reales y ejecuta órdenes con dinero de sus usuarios. El listón no es
«funciona», sino: *ninguna vía de ejecución escapa al control de riesgo,
ningún movimiento de dinero queda sin rastro, ningún despliegue puede arrancar
en un estado inseguro, y cada una de esas garantías está cubierta por un test
que falla si se rompe.*

---

## Resumen

| Severidad | Hallazgos | Corregidos |
|-----------|-----------|------------|
| Crítica   | 4         | 4          |
| Alta      | 9         | 9          |
| Media     | 3         | 3          |
| Aceptados con justificación | 2 | — |

Estado tras las correcciones: **847 tests de backend** (800 previos + 47
nuevos) y **124 de frontend** (119 + 5) en verde, con la cobertura del backend
en 78 % y un umbral que rompe la build por debajo del 75 %;
`manage.py check --deploy --fail-level WARNING` sin avisos con la configuración
de producción; `npm run lint` operativo y limpio con `--max-warnings 0`.

---

## Hallazgos críticos

### C-1 · La orden manual real no pasaba por el control de riesgo ni dejaba rastro

**Dónde:** `PlaceOrderUseCase` (`core/application/use_cases/broker_trading.py`),
expuesto en `POST /api/trading/connections/<id>/orders/`.

El sistema tenía dos vías para mover dinero real y solo una estaba gobernada.
La promoción automática paper→real (`_mirror_live`) aplicaba el límite de
pérdida diaria y el de concentración, registraba cada intento en
`LiveOrderRecord` y disponía de kill-switch. La orden manual —el mismo
exchange, el mismo dinero— no hacía nada de eso: sin barreras, sin auditoría,
sin límite de tasa y sin protección frente a envíos duplicados.

En la práctica, un usuario con `daily_loss_limit_usd` configurado veía sus
compras automáticas bloqueadas y podía cursar exactamente la misma compra a
mano un segundo después. La política de riesgo era, para esa vía, decorativa.

**Corrección:**
- Las mismas barreras (`_daily_loss_blocked`, `_concentration_blocked`) se
  aplican ahora a las compras manuales, reutilizando las funciones existentes
  para que exista **una sola definición** de la política.
- Todo intento —enviado, fallido o bloqueado— queda en `LiveOrderRecord`.
- El endpoint devuelve **409** cuando lo frena el OMS, distinguible de un 400
  por petición mal formada.
- Se aplica el scope de throttling `trading_order` (20/min por defecto) solo
  al POST.

### C-2 · Idempotencia ausente en el envío de órdenes reales

Un reintento de red, un doble clic o un reenvío del navegador cursaba una
**segunda orden real**. No había forma de que el servidor supiera que las dos
peticiones eran el mismo intento.

**Corrección:** `client_order_id` opcional en el cuerpo de la petición, con
`UniqueConstraint(owner, client_order_id)` parcial en base de datos —la
garantía es del motor, no del código—. Si el identificador ya existe se
devuelve el resultado del primer intento marcado con `idempotent_replay: true`.
El frontend genera un UUID por intento en `tradingService.placeOrder`.

El orden de las operaciones es la parte que importa: el intento se **persiste
en estado `pending` antes** de llamar al exchange. Una comprobación previa en
memoria no basta —dos peticiones simultáneas la pasarían las dos y ambas
enviarían la orden, con la restricción única llegando tarde y el dinero ya
movido—. Al reservar primero, es el motor de base de datos quien arbitra la
carrera; la petición que la pierde reproduce el resultado de la ganadora sin
tocar el exchange. Un registro que quede en `pending` significa «resultado
desconocido», que es justo lo que una auditoría debe poder decir en lugar de
callarlo.

### C-3 · Un despliegue mal configurado arrancaba y servía tráfico

`SECRET_KEY` tenía como valor por defecto
`django-insecure-change-this-in-production-key-12345` y `DEBUG` por defecto
`True`. Con esa clave en producción se pueden falsificar tokens JWT y —dado el
hallazgo C-4— descifrar las credenciales de exchange de todos los usuarios.
Nada impedía arrancar así.

**Corrección:** validación de arranque (fail-fast) cuando `DEBUG=False`. Aborta
con `ImproperlyConfigured` si la clave es la de ejemplo, empieza por
`django-insecure-`, mide menos de 32 caracteres, o si `ALLOWED_HOSTS` está
vacío o contiene `*`. En desarrollo se tolera para no romper el arranque de un
repositorio recién clonado.

### C-4 · Credenciales de exchange cifradas con una clave derivada de `SECRET_KEY`

`crypto.py` derivaba la clave Fernet con un **SHA-256 directo sobre
`SECRET_KEY`**. Tres problemas encadenados: rotar la clave de firma dejaba
ilegibles las credenciales de todos los usuarios; una filtración del secreto de
firma implicaba automáticamente el descifrado de las claves API; y no existía
ningún camino de rotación.

**Corrección:** anillo de claves dedicado (`CREDENTIALS_ENCRYPTION_KEYS`) sobre
`MultiFernet` — la primera cifra, todas descifran, así que rotar es anteponer
la nueva. El material puede ser una clave Fernet o una passphrase, derivada con
**HKDF-SHA256** con etiqueta de dominio. La clave legada se conserva **al final
del anillo**: las credenciales ya guardadas se siguen leyendo y ninguna se
pierde, pero nunca vuelve a cifrar. `needs_rotation()` y `rotate_secret()`
permiten recifrado perezoso sin migración masiva.

---

## Hallazgos altos

### A-1 · La integración continua no se ejecutaba

`.github/workflows/ci.yml` disparaba en `main` y `Javier-Dev`. Esa segunda rama
ya no existe y el desarrollo ocurre en `develop` y ramas de trabajo, así que
**ningún push de desarrollo pasaba por CI**.

**Corrección:** disparadores en `main`, `develop` y `claude/**`, más
`workflow_dispatch`; `concurrency` para cancelar ejecuciones superadas.

### A-2 · El linter del frontend estaba roto

`package.json` declaraba el script `lint` y cinco dependencias de ESLint, pero
**no existía ningún archivo de configuración**: `npm run lint` fallaba con
«couldn't find a configuration file». Nunca se había ejecutado.

**Corrección:** `.eslintrc.cjs` con TypeScript + reglas de hooks de React, y
paso de lint en CI. La primera pasada reveló tres errores reales (una directiva
`eslint-disable` obsoleta, un punto y coma superfluo y dos supresiones de una
regla inexistente) y tres dependencias inestables de hooks —arrays recreados en
cada render que hacían re-ejecutarse efectos y `useMemo`—, todos corregidos. El
gate queda en `--max-warnings 0`.

### A-3 · Sin cabeceras de seguridad HTTP en Django

No había `SECURE_SSL_REDIRECT`, HSTS, `SESSION_COOKIE_SECURE`,
`CSRF_COOKIE_SECURE`, `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS`,
`SECURE_REFERRER_POLICY` ni `CSRF_TRUSTED_ORIGINS`. Nginx aportaba algunas en
producción, pero la aplicación quedaba desprotegida ante cualquier despliegue
que no pasara por ese Nginx concreto (Railway, por ejemplo).

**Corrección:** bloque de endurecimiento en `settings.py`. Lo independiente del
transporte se aplica siempre —también en desarrollo, para que lo que se prueba
sea lo que se despliega— y lo que exige HTTPS se activa con `DEBUG=False`,
incluido `SECURE_PROXY_SSL_HEADER` (sin él, tras un proxy que termina TLS,
Django entra en bucle de redirección). `manage.py check --deploy --fail-level
WARNING` es ahora un paso obligatorio de CI.

### A-4 · Sin límite de tasa global en la API

Solo nueve endpoints declaraban `ScopedRateThrottle`. Los **más de cien
restantes** —incluidos los que lanzan cientos de backtests o consultan APIs
forenses de terceros— no tenían techo alguno.

**Corrección:** `AnonRateThrottle` y `UserRateThrottle` por defecto (120/min y
600/min, configurables), con los scopes específicos aplicándose por encima.

### A-5 · Sin configuración de logging

No existía bloque `LOGGING`. Django emitía únicamente WARNING+ del propio
framework y **todos los `logger.info` de los casos de uso se perdían**, incluidos
los de ejecución real. No había trazabilidad de qué hizo el sistema con el
dinero del usuario.

**Corrección:** `LOGGING` explícito con formateador JSON en producción
(`config/logging.py`) y canal de auditoría `core.audit` fijado a INFO que nunca
se silencia. Las órdenes reales emiten eventos estructurados
(`live_order_sent` / `live_order_blocked` / `live_order_failed`) con usuario,
símbolo, nocional y resultado.

### A-6 · Sin auditoría de dependencias ni verificación de migraciones en CI

Nada comprobaba vulnerabilidades conocidas ni que los modelos tuvieran su
migración. Un modelo cambiado sin migrar no rompe la suite: rompe el despliegue.

**Corrección:** job `seguridad` con `pip-audit --strict` y `npm audit
--audit-level=high`; paso `makemigrations --check --dry-run` antes de los tests.

### A-7 · La capa de tiempo real estaba muerta en producción

**Dónde:** `backend/Procfile`, `backend/start.sh`, `docker-compose.prod.yml`,
`nginx/nginx.prod.conf`.

Las **tres** rutas de arranque de producción ejecutaban
`gunicorn config.wsgi:application`. WSGI no sabe hacer el upgrade a WebSocket,
así que los consumers de Channels —`/ws/prices/` y `/ws/notifications/`— no
podían atenderse. Además, Nginx **no tenía bloque `location /ws/`**: esas rutas
caían en `location /` y recibían el `index.html` de la SPA.

El resultado es el peor tipo de fallo: en desarrollo funcionaba (`runserver`
levanta Daphne), y en producción el stream de precios y el centro de
notificaciones simplemente no conectaban nunca, sin error visible en el
servidor. El cliente degrada en silencio (`usePriceStream` deja el mapa vacío),
así que la avería no se manifestaba como una caída sino como una función que
«no acaba de ir».

**Corrección:** las tres rutas sirven ahora `config.asgi:application` con
`uvicorn.workers.UvicornWorker` —se conserva la gestión de procesos de gunicorn
y se sirven HTTP y WebSocket—, se añade `uvicorn[standard]` a
`requirements.txt`, y Nginx gana un bloque `/ws/` con `proxy_http_version 1.1`,
las cabeceras `Upgrade`/`Connection`, `proxy_buffering off` y timeouts de una
hora (una conexión de precios pasa largos ratos en silencio y el timeout por
defecto de 60 s la cortaría continuamente).

### A-8 · El invariante de la auditoría dependía de cada llamante

Al pasar `LiveOrderRecord` a consultarse por `owner`, cualquier código que
creara un registro sin informarlo lo dejaría **invisible** para el rastro de
cumplimiento, el TCA y el libro de riesgo. Confiar en que cada punto de
creación se acuerde es exactamente la clase de suposición que falla al cabo de
unos meses.

**Corrección:** el invariante se enforcea en el modelo. `LiveOrderRecord.save()`
deriva `owner` de la cartera cuando falta, de modo que ningún registro puede
existir sin dueño con independencia de quién lo cree.

### A-9 · `.env.example` incompleto

Faltaban `REDIS_URL`, `DATABASE_URL`, las claves VAPID de Web Push, las de
CoinGecko/CryptoCompare y toda la configuración de seguridad. Un despliegue
guiado por ese archivo arrancaba sin caché, sin WebSockets y sin push.

**Corrección:** documentadas todas las variables, con los comandos de
generación de secretos y las condiciones de fallo del arranque.

---

## Hallazgos medios

### M-1 · Doble codificación UTF-8 en `views.py`

El archivo (3 590 líneas) tenía BOM y **69 líneas con mojibake**
(`Ã³`, `â€"`, `â”€`) en comentarios y docstrings: se guardó una vez con doble
codificación. Dos archivos `.tsx` tenían BOM. **Corregido**: recodificación,
BOM eliminado y `.gitattributes` reforzado.

### M-2 · Sin Content-Security-Policy

Nginx tenía HSTS, `X-Frame-Options` y `nosniff`, pero ninguna CSP: la última
barrera contra XSS. **Corregido** con una política restrictiva y sus excepciones
documentadas (`wasm-unsafe-eval` para WebGL, `unsafe-inline` en estilos por
Tailwind, `wss:` para los WebSockets de precios).

### M-3 · El libro de riesgo ignoraba la posición manual real

`_aggregate_exposures` sumaba posiciones manuales, paper y
`live_base_position`, pero las órdenes manuales no actualizan ninguna posición
persistida, así que **no aparecían en ningún libro**. El límite de
concentración medía sobre una exposición menor que la real, y el VaR
subestimaba. **Corregido**: la posición manual se reconstruye desde la
auditoría (compras − ventas por símbolo, acotada a cero). El límite de pérdida
diaria también las cuenta, emparejadas por símbolo.

---

## Aceptado con justificación

### J-1 · `FloatField` para magnitudes monetarias

Los modelos usan 64 campos `FloatField` frente a 27 `DecimalField`. En binario
de coma flotante, sumar muchos importes acumula error; la práctica
institucional es `Decimal` de extremo a extremo.

**No se corrige en esta pasada, y es deliberado.** El cambio toca decenas de
modelos, exige migraciones de datos sobre tablas con histórico y atraviesa toda
la capa de dominio (NumPy/pandas trabajan en `float` y habría que decidir dónde
está la frontera de conversión). Es un proyecto en sí mismo, con su propio plan
de pruebas, y hacerlo a medias es peor que no hacerlo: mezclar `Decimal` y
`float` en la misma expresión introduce errores más difíciles de ver que los
que resuelve.

Mitigación actual: los importes se redondean al persistirse y el rastro de
auditoría guarda el precio de ejecución que devuelve el exchange, de modo que
la reconciliación se hace contra el dato del broker y no contra el cálculo
propio. **Recomendación:** abordarlo como trabajo dedicado, empezando por
`LiveOrderRecord`, `PaperTrade` y `Position`.

### J-2 · Tokens JWT en `localStorage`

Expone la sesión a un XSS con éxito. La alternativa —cookies `httpOnly`—
exigiría rehacer el flujo de autenticación entero y trae su propia superficie
CSRF. Es una decisión ya tomada y documentada en `info/Seguridad_Auth.md`. La
CSP añadida en M-2 reduce sustancialmente el riesgo residual al cortar la
ejecución de scripts de terceros, que es el vector práctico.

---

## Verificación

```bash
# Backend — 847 tests, cobertura y postura de despliegue
cd backend && pytest -q
python src/manage.py makemigrations --check --dry-run
DJANGO_DEBUG=False DJANGO_SECRET_KEY=<clave-real> \
  DJANGO_ALLOWED_HOSTS=tudominio.com \
  python src/manage.py check --deploy --fail-level WARNING

# Frontend — lint, tipos, 124 tests y build
cd frontend && npm run lint && npx tsc --noEmit && npm test && npm run build
```

## Antes de desplegar

1. Generar y fijar `DJANGO_SECRET_KEY` (mínimo 32 caracteres); sin ella el
   arranque aborta con `DEBUG=False`.
2. Generar `CREDENTIALS_ENCRYPTION_KEYS`. Si ya hay credenciales guardadas,
   **conservar** la `SECRET_KEY` anterior en el entorno hasta que se hayan
   recifrado: es la que las descifra.
3. Declarar `DJANGO_ALLOWED_HOSTS` con los dominios reales y
   `CORS_ALLOWED_ORIGINS` con los del frontend.
4. Aplicar la migración `0034_live_order_manual_audit` (rellena `owner` en la
   auditoría histórica).
5. Poner `DJANGO_LOG_FORMAT=json` si hay agregador de logs.
