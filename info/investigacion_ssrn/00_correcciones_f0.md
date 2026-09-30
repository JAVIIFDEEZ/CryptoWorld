# F0 · Correcciones previas (§8 del índice)

Tres defectos que el índice del paquete detectó en `develop` y que el mapa de
decisiones marca como **CORREGIR** (ítems 2, 3 y 32 · prioridad P1 · fase F0).
Los tres se verificaron contra el código antes de tocarlo y los tres eran reales.

Corregidos en **1.340.0**.

---

## §8.6 · El HAR de `edge_test` no era el HAR de Corsi

**Prioridad.** El índice dice que se corrige *antes* de correr F0, «o F0 juzga
con otro modelo». Es correcto: el veredicto de volatilidad descansa sobre este
modelo.

**El defecto.** `HAR_LAGS = (1, 5, 22)` se aplicaba como **velas**, no como días.
Con velas horarias y una ventana de volatilidad realizada de 24, los componentes
«diario», «semanal» y «mensual» resultaban ser **1 h, 5 h y 22 h**: los tres
dentro del mismo día. El modelo no medía memoria larga de ninguna clase.

El comentario del código decía «en múltiplos de la ventana de volatilidad
realizada» y la llamada no multiplicaba por nada. El comentario describía una
intención que el código no implementaba.

**Segundo defecto, dentro del mismo.** (5, 22) son *sesiones bursátiles*: 5 días
por semana y 22 por mes en renta variable. Cripto cotiza 24/7, así que los
análogos son 7 y 30 días naturales.

**La corrección.** Las escalas pasan a ser de calendario —`HAR_LAGS_DAYS =
(1, 7, 30)`— y `har_lags_in_bars(bars_per_day)` las convierte. Con ventana de 24
velas: `(1, 168, 720)`. La primera escala es siempre 1 vela porque la volatilidad
realizada ya cubre un día por construcción; multiplicarla otra vez la contaría
dos veces.

El informe publica ahora `har_lags_days` y `har_lags_bars`: sin ellos, dos
ejecuciones con marcos temporales distintos se leerían como comparables.

**Consecuencia sobre la muestra.** El componente mensual consume 720 velas antes
de dar su primer valor. El mínimo de 150 filas era insuficiente —el modelo habría
corrido con una columna entera de NaN— y sube a `max(150, escala_larga + 60)`.

**Re-calibración.** El modelo cambió, así que el arnés se volvió a calibrar sobre
series con respuesta conocida (3 tamaños × 3 semillas por familia):

| Serie | Antes (HAR roto) | Después (escalas de calendario) |
|---|---|---|
| GARCH (vol. agrupada) | 20/20, `best_predictor` **siempre** persistencia | **8/9** · a n ≥ 5000 el HAR **gana** a la persistencia |
| Homocedástica (vol. constante) | 20/20 | **9/9**, cero falsos positivos |

El dato que confirma que el arreglo es real y no cosmético: con el HAR roto el
mejor predictor era *siempre* la persistencia. Con las escalas corregidas y
muestra suficiente, el HAR gana — que es lo que reporta la literatura sobre datos
con agrupamiento de volatilidad.

El único fallo (n = 3000, semilla 2) es pérdida de potencia, no de corrección: a
3.000 velas el componente mensual se come 720 y quedan 1.881 observaciones fuera
de muestra.

**Un test afirmaba el defecto.** `test_the_lags_are_the_ones_corsi_uses` fijaba
`HAR_LAGS == (1, 5, 22)`, es decir, protegía el error. Se reescribió para
comprobar las escalas de calendario y su conversión.

---

## §8.2 · El funding se anualizaba con una cadencia fija

**El defecto.** `PERIODS_PER_YEAR = 1095.0` clavado en `carry.py`, usado para
anualizar el rendimiento **y** para calcular la duración del tramo
(`anos = n / PERIODS_PER_YEAR`).

Es correcto hoy para BTC y ETH en Binance. Es falso para símbolos que liquidan
cada 4 h o cada hora, y para Hyperliquid, que es horario. Con cadencia real de
1 h y el valor clavado, un tramo de 1.095 liquidaciones —45 días— se contaba como
un año entero: el rendimiento anualizado salía dividido por ocho.

**Lo que agrava el defecto.** `FundingRateRecord` ya guarda `interval_hours`. El
dato para hacerlo bien estaba en la base de datos y no se usaba.

**La corrección.** `periods_per_year(interval_hours)` deriva la cadencia del
dato. El caso de uso la obtiene de la **mediana de los huecos entre marcas
temporales** —mediana y no media, porque un hueco de recogida desplazaría la
media y con ella el rendimiento— y la pasa tanto a `simulate_carry` como a
`null_distribution`, para que el coste de capital de las dos ramas coincida y la
comparación mida solo el sesgo de signo.

El informe publica `periods_per_year` y `funding_interval_hours`.

---

## §8.1 · La «profundidad ±2 %» estaba truncada

**El defecto.** Se pedía un libro de 500 niveles y `depth_within_band` sumaba lo
que hubiera dentro de la banda **sin comprobar si el libro llegaba a la banda**.
En BTCUSDT, con tick de 0,1, esos 500 niveles casi seguro no cubren ±2 %.

**Por qué es peor que un sesgo.** El número no era comparable entre activos: un
símbolo de tick ancho agota sus niveles mucho más lejos del medio que uno de tick
fino, así que el mismo valor significaba cosas distintas según el activo. Y la
serie se llamaba «±2 %» sin serlo.

**La corrección.**
- Se piden **1.000 niveles**, el máximo del endpoint. Pedir 500 era la causa.
- `depth_within_band` devuelve el alcance real por cada lado y `covered`. Manda
  el **lado más corto**: si el libro llega a −5 % pero solo a +0,3 %, la banda no
  está cubierta.
- Un libro truncado **no entra** en la serie `depth_2pct_usd`; se registra el
  motivo. Mezclar un dato truncado con uno completo hace la serie inservible sin
  que nada falle de forma visible.
- El alcance se archiva **siempre** como `depth_reach_pct`: es el único dato que
  permite saber si la profundidad de un día es comparable con la de otro.

**Robustez añadida.** La mejor puja y la mejor oferta se toman por máximo y
mínimo, no por posición. Los exchanges devuelven el libro ordenado, pero tomar
`[0]` haría que una fuente nueva con otro convenio produjera un medio equivocado
en silencio.
