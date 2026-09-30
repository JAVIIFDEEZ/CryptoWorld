# Cómo desbloquear lo que sigue bloqueado

Documento operativo. Diagnóstico medido, no supuesto, y la secuencia exacta para
salir de cada bloqueo por orden de valor.

Fecha del diagnóstico: 30-sep-2026. Estado del repositorio: `develop` @ 1.344.0.

---

## 1. El diagnóstico, medido

Se probaron 23 hosts desde el contenedor de la sesión, con el proxy configurado:

| grupo | hosts probados | resultado |
|---|---|---|
| Datos de mercado | `api.binance.com`, `data-api.binance.vision`, `fapi.binance.com`, `api.bybit.com`, `www.okx.com`, `api.kraken.com`, `api.coinbase.com`, `api.kucoin.com`, `api.coingecko.com`, `min-api.cryptocompare.com`, `www.deribit.com` | **000** en todos |
| Macro y referencia | `api.stlouisfed.org`, `api.bls.gov`, `apps.bea.gov`, `www.federalreserve.gov`, `www.sec.gov`, `query1.finance.yahoo.com`, `stooq.com` | **000** en todos |
| Cripto-datos | `api.llama.fi`, `api.coincap.io`, `data.messari.io`, `api.alternative.me` | **000** en todos |
| Infraestructura | `pypi.org`, `api.github.com`, `registry.npmjs.org` | **200** |

`000` significa que la pasarela rechaza el CONNECT (403 de política), no que el
host no exista. El registro del proxy lo dice literalmente:
`gateway answered 403 to CONNECT (policy denial or upstream failure)`.

**Conclusión:** no es un fallo de TLS, ni de DNS, ni del código de los clientes.
Es la **política de red del entorno**, que tiene una lista de permitidos donde
solo están los hosts de infraestructura. Se cambia en los ajustes del entorno
—*Network access*, en el menú del entorno remoto— eligiendo un nivel de acceso más
amplio o añadiendo dominios concretos.

## 2. La observación que reduce el problema

`fetch_ohlcv_dataframe` **consulta primero el almacén propio**
(`ohlcv_store.store_is_fresh` → `load_dataframe`) y solo sale a la red si el
almacén no puede servir el tramo pedido.

Eso cambia el problema entero: **la red hace falta para INGERIR, no para
analizar.** Una vez el almacén tiene histórico, todo lo analítico corre sin red:

| corre sin red hoy | necesita red una vez, luego no |
|---|---|
| `correlation_watch` (1.341.0) | `edge_test` |
| `calendar_study` (1.342.0) | `carry_test` |
| `/api/market/correlation-map/` (1.343.0) | `factor_study` |
| todo el motor de estrategias sobre el almacén | `option_surface` |

Así que la petición mínima no es «abrir internet»: son **cuatro hosts** para
llenar el almacén.

## 3. La lista de permitidos, por lo que desbloquea cada host

Ordenada por valor. Los tres primeros desbloquean la puerta G0 del paquete SSRN.

### Imprescindibles

| host | desbloquea | por qué ese y no otro |
|---|---|---|
| `data-api.binance.vision` | OHLCV de todo el universo → `edge_test`, `feature_study`, `factor_study`, y el almacén del que vive todo lo demás | Es el endpoint **solo-datos** de Binance, y **ya es el que usa el código**: `binance_client.BINANCE_BASE_URL` apunta ahí. Se eligió sobre `api.binance.com` porque no requiere clave y está menos restringido por región — que es exactamente el problema §8.4 |
| `fapi.binance.com` | financiación de perpetuos → `carry_test`; interés abierto, ratio long/short, taker buy/sell y profundidad → el índice de fragilidad | Es `binance_client.FUTURES_BASE_URL`. Sin él, `carry_test` no tiene nada que medir y la microestructura de derivados sigue sin archivarse |
| `api.coingecko.com` | capitalización y universo → construcción de la cesta, `factor_study` | Las cargas de los factores CMKT/CSMB/CMOM necesitan capitalización, no solo precio |

### Muy recomendables

| host | desbloquea |
|---|---|
| `www.deribit.com` | superficie de opciones → `option_surface`, varianza implícita libre de modelo, prima de riesgo de varianza |
| `api.kucoin.com` | respaldo de OHLCV cuando Binance falla o geobloquea |
| `min-api.cryptocompare.com` | segundo respaldo de precio histórico |

### Opcionales, por completitud del producto

`api.blockchain.info`, `api.blockchair.com`, `*.blockscout.com` (on-chain y
forense), `api.alternative.me` (índice de miedo y codicia).

### Lo que NO hace falta pedir

Nada de macro. El calendario económico de 1.342.0 **deriva por regla** las
liquidaciones de financiación, los vencimientos de opciones, los cierres de
periodo, la nómina no agrícola y los halvings ocurridos — sin red y sin inventar
fechas. Lo único que un host macro añadiría son las fechas del FOMC, IPC, PCE, PIB
y BCE, y para eso el candidato es `api.stlouisfed.org` (FRED publica los
calendarios de publicación y es gratuito con clave). Es mejora, no bloqueo.

## 4. La secuencia para obtener el veredicto de F0

Una vez abiertos los tres hosts imprescindibles, en este orden:

```bash
# 1. Llenar el almacén. Es el único paso que necesita red.
#    `recommended_candles` tope a 4.000 velas por marco, así que se pide con
#    margen. El backfill pagina de 1.000 en 1.000 y es idempotente y reanudable:
#    se puede volver a lanzar tantas veces como haga falta.
python manage.py shell -c "
from core.application.use_cases.ohlcv_store import BackfillOhlcvUseCase
uc = BackfillOhlcvUseCase()
for s in ('BTC','ETH'):
    for iv in ('1h','4h','1d'):
        print(s, iv, uc.execute(symbol=s, interval=iv,
                                target_candles=6000, max_pages=8))
"

# 2. Comprobar que el histórico no tiene huecos antes de medir nada sobre él.
python manage.py shell -c "
from core.application.use_cases.ohlcv_store import coverage, find_gaps
for s in ('BTC','ETH'):
    print(s, coverage(s,'1h'), find_gaps(s,'1h'))
"

# 3. La puerta G0: ¿a qué pregunta alcanza la muestra?
python manage.py edge_test BTC --interval 1h --json > info/f0_edge_btc.json
python manage.py edge_test ETH --interval 1h --json > info/f0_edge_eth.json

# 4. El resto, que ya no necesita red.
python manage.py carry_test BTC ETH --json       > info/f0_carry.json
python manage.py factor_study --json             > info/f0_factores.json
python manage.py correlation_watch BTC ETH SOL   # sin red desde ya
python manage.py calendar_study BTC ETH          # sin red desde ya
```

El veredicto de `edge_test` es la puerta: si sobre datos reales **no** da
`VOLATILITY`, la fase F3 del paquete SSRN baja a descriptivo. Eso está escrito en
el propio paquete y no es una interpretación.

## 5. La alternativa que no depende de nadie

Todo lo anterior corre en la máquina de Javi sin tocar ningún ajuste de nube. El
repositorio ya trae `docker-compose.yml` con PostgreSQL 16 y Redis:

```bash
docker compose up -d postgres redis
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
# …y la secuencia del apartado 4
```

Es el camino **más rápido** al veredicto de F0, porque no espera a ningún cambio
de configuración. La única diferencia es que el almacén queda en local en vez de
en el entorno remoto.

## 6. Lo que ningún cambio de red desbloquea

### Los ocho módulos del paquete SSRN

La versión 1.0 del paquete (30-sep-2026) se entregó como un README índice que
referencia ocho módulos: `01_datos_pit.md` … `08_referencias.md`. **No se han
recibido.** Sin ellos no se pueden ejecutar con fidelidad las fases F1–F8, porque
las especificaciones concretas (D1–D6, I1–I7, C1–C8, V0–V7, P3–P7) viven allí y no
en el índice.

Y la **regla 10** del propio paquete lo cierra: «Se cita solo lo que figura en
`08_referencias.md`, con el ID tal cual. Nada de referencias inventadas.» Sin ese
fichero, cualquier cita que se escribiera incumpliría la norma del paquete.

Esto no lo arregla la red: hay que aportar los ficheros.

### Dos correcciones del §8 que siguen abiertas

- **§8.3 — las liquidaciones son una cota inferior.** El canal `forceOrder` de
  Binance emite como máximo **un evento por símbolo y por segundo**, así que en una
  cascada —justo cuando el dato importa— el recuento observado está truncado por
  abajo. Cualquier índice construido sobre él hereda ese sesgo y hay que declararlo
  en la salida, no corregirlo con un factor inventado. Pendiente: archivar la serie
  y añadir la declaración.
- **§8.4 — geobloqueo HTTP 451.** Binance responde 451 desde determinadas
  regiones. Afecta a **producción**, no a este contenedor, y es independiente de la
  lista de permitidos: aunque el host esté autorizado, si la región de Railway está
  geobloqueada la llamada falla. Mitigación ya prevista en el código: preferir
  `data-api.binance.vision`, que es el endpoint solo-datos. Pendiente: verificar la
  región del despliegue y registrar el resultado.

---

## Resumen en una tabla

| bloqueo | quién lo desbloquea | coste |
|---|---|---|
| Datos de mercado | Javi, en *Network access* del entorno: 3 hosts imprescindibles | minutos |
| …o alternativamente | Javi, con `docker compose` en local | una tarde |
| Los 8 módulos SSRN | Javi, aportando los ficheros | — |
| §8.3 liquidaciones | implementable en cuanto haya `fapi.binance.com` | 1 iteración |
| §8.4 geobloqueo | verificar región de Railway | 1 comprobación |

Lo que **no** está bloqueado y ya está hecho: el detector de rupturas de
correlación (1.341.0), el calendario económico y el estudio de eventos (1.342.0),
el mapa de correlaciones (1.343.0) y la rejilla de hora de la semana (1.344.0). Los
cuatro se construyeron a propósito sin depender de la red, precisamente para no
quedarse esperando.
