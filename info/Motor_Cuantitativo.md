# Motor cuantitativo — CAPAS 1, 2 y 3

**Capa 1** (G1, G8, G9): control de multiplicidad, registro de experimentos y
honestidad de presentación.
**Capa 2** (G2, G4.1, G5): validación cruzada combinatoria purgada, relleno a la
apertura siguiente, cascada de retests, SPP e incubación.
**Capa 3** (G3, G6, G7): etiquetado triple-barrera con meta-etiquetado, HRP para
la cartera, y detección de régimen con estabilidad temporal.
**Integración** (G3 al sizing, G4 impacto y capacidad, G9d significancia): el
meta-modelo decide el tamaño de la posición, cada finalista reporta cuánto dinero
admite su edge, y ninguna métrica se muestra ya sin su incertidumbre.

---

# G1 — Control de multiplicidad

**Brecha corregida:** los controles anti-sobreajuste del generador (PBO y
Deflated Sharpe) estaban mal alimentados, y el número real de pruebas no
entraba en ninguna fórmula.

---

## El problema

El *False Strategy Theorem* (Bailey & López de Prado) dice que el máximo Sharpe
entre N pruebas crece con N **aunque ninguna estrategia tenga edge**. Por eso un
Sharpe reportado sin decir cuántas configuraciones se probaron no significa
nada: el Deflated Sharpe Ratio existe precisamente para corregir el umbral por
`E[max SR₀]`, que depende de N y de la varianza entre los Sharpe de esas pruebas.

El motor implementaba la matemática correctamente, pero la alimentaba mal.
`_neighborhood_matrix` construía la matriz de PBO/DSR con **8-16 vecinos
«jitter» de la campeona ya elegida** — perturbaciones ±10 % de una única
estrategia. Al ser casi clones entre sí:

```
V[{SRₙ}] → 0   ⟹   E[max SR₀] → 0   ⟹   DSR = Φ(algo grande) ≈ 1
```

El DSR salía ≈1 para casi cualquier finalista, y el PBO medía estabilidad
paramétrica local en lugar de sobreajuste de selección. Mientras tanto,
`evaluations` —el N real, disponible en `evolve`— se registraba en el informe y
no entraba en ningún cálculo.

Hay un test que fija este comportamiento para que no vuelva:
`test_near_identical_trials_make_dsr_meaningless` demuestra que con clones el
DSR aprueba (>0.95) un Sharpe que no lo merece, y
`test_diverse_real_trials_discriminate` que con pruebas reales ya no.

---

## Lo implementado

### 1. Registro de las pruebas reales (`TrialRegistry`)

`generate_strategies.py` guarda ahora la serie de retornos de cada genoma
distinto que la búsqueda evalúa. Dos decisiones importan:

- **Muestreo de reservorio, no top-M.** Quedarse con las mejores subestimaría
  `V[{SRₙ}]`, que es justo el término que eleva el umbral: se reproduciría el
  mismo sesgo optimista con otra forma. El reservorio (algoritmo R) da una
  muestra uniforme de todo lo evaluado con memoria acotada (300 series).
- **El recuento va aparte del reservorio.** La deflación usa el número real de
  pruebas —que puede ser de miles—; el reservorio solo aporta la varianza.

Reevaluar un genoma ya visto no cuenta: el GA cachea por hash y una
reevaluación no es una prueba nueva.

### 2. Deflación por el N real

`deflated_sharpe_ratio(returns, trials, n_trials=None)` acepta ahora un recuento
explícito. Omitirlo conserva el comportamiento anterior, de modo que el Camino A
(las 5 estrategias con Optuna, que ya alimentaba bien sus trials) no cambia.

Los genomas que **nunca llegan a operar** quedan fuera de la varianza: su serie
es constante y no tienen Sharpe. Contarlos como un 0 sería inventarse un dato y
ensancharía la dispersión artificialmente, elevando el umbral y castigando de
más a la campeona. Siguen contando en N — la búsqueda gastó esa evaluación.

### 3. N efectivo por agrupamiento

`effective_number_of_trials` agrupa por correlación (enlace simple, |ρ| ≥ 0.9)
las series de las pruebas. Un GA produce muchos genomas casi idénticos;
contarlos como pruebas independientes deflactaría de más y penalizaría a una
campeona legítima por el mero hecho de que la búsqueda exploró a fondo un
vecindario.

### 4. La curva E[max SR₀] frente a N

`expected_max_sharpe_curve` devuelve la curva en escala logarítmica, la posición
de esta ejecución sobre ella y, si procede, a partir de cuántas pruebas el azar
iguala el Sharpe observado. Se muestra en el generador
(`MultipleTestingCard.tsx`) con un veredicto explícito: *supera al azar* / *no se
distingue del azar*.

### 5. El jitter, renombrado a lo que es

Lo que antes alimentaba al PBO es ahora `parameter_sensitivity`: dispersión del
Sharpe entre vecinos, fracción de vecinos en positivo y degradación del vecino
mediano. Es un test de robustez legítimo —el *randomize parameters* de
StrategyQuant— pero mide estabilidad paramétrica, no sobreajuste de selección.

`gate_spec` declara siempre de dónde salen sus números en
`overfitting.source`: `search_trials` (modo válido) o `parameter_jitter`
(repliegue cuando se usa suelto, con aviso explícito de lo que mide y de que el
DSR resultante es optimista por construcción).

---

## Impacto medido

Ejecución del generador sobre la serie sintética de los tests (reversión a la
media, 1 000 velas, preset pequeño):

| | Antes | Después |
|---|---|---|
| Fuente de PBO/DSR | 6 vecinos jitter | 90 genomas evaluados |
| N que deflacta | 6 | 90 (53 independientes) |
| Umbral `E[max SR₀]` | ≈0 | 0.5046 |
| Sharpe/periodo de la campeona | 0.3072 | 0.3072 |
| **DSR** | **≈1** | **0.0** |

El veredicto es internamente coherente: el **mejor** Sharpe observado entre los
90 trials fue 0.4019, por debajo del 0.5046 que predice el azar con 90 intentos.
En esa serie y con ese presupuesto de búsqueda, lo encontrado no se distingue de
haber buscado mucho — y ahora el motor lo dice.

---

## Decisiones de producto

- **El DSR se reporta, no bloquea.** El gating sigue decidiéndose por los checks
  de siempre (trades, lookahead, eficiencia WF, PBO, Monte Carlo). Convertirlo en
  gate duro con el N real dejaría el libro vacío de golpe; primero conviene ver
  los números sobre activos reales. Cuando se decida, es añadir un umbral a
  `GatingThresholds`.
- **N es el de la ejecución en curso**, no acumulado entre corridas. Es
  reproducible y no cambia de valor al re-ejecutar. Acumular por activo es lo que
  pide el *False Strategy Theorem* en sentido estricto y queda para G8, junto con
  el registro persistente de experimentos.

---

---

# G8 — Registro de experimentos

**Brecha:** el número de configuraciones probadas sobre un activo se perdía al
terminar cada ejecución. Solo sobrevivían las estrategias que salieron bien, lo
que subestima la multiplicidad — el sesgo de selección clásico: si únicamente se
recuerdan las búsquedas que dieron algo, el N que deflacta el Sharpe es siempre
menor que el real.

## Lo implementado

`StrategyExperimentRun`, modelo **append-only**: se registra TODA ejecución del
generador, produjera estrategias o ninguna. `save()` rechaza modificar una fila
ya escrita — un registro de experimentos que se puede reescribir no sirve de
nada, y hay un test que lo comprueba.

**Es a nivel de ejecución, no de genoma**, y es una desviación deliberada del
informe original. Un preset profundo evalúa miles de specs y la reoptimización
nocturna corre sobre muchos activos: una fila por genoma serían millones de
registros al mes. El dato de gobernanza —cuántas configuraciones se han probado
sobre este activo— se conserva **exactamente** sumando `evaluations`, y los
genomas que sobrevivieron ya viven en `StrategyDefinition`.

Cada registro guarda lo necesario para reproducir la búsqueda: semilla, preset,
optimizador, rango de datos y **huella del catálogo de bloques**
(`catalog_version()`). Esa huella se deriva del contenido —bloques disponibles,
rangos de parámetros y operadores—, no de un número que haya que acordarse de
subir a mano. Añadir un indicador o mover el rango de una ventana cambia el
espacio de búsqueda y hace que dos ejecuciones con la misma semilla dejen de ser
comparables; la huella lo delata en lugar de que pase inadvertido.

El acumulado se **reporta, no deflacta**: el DSR sigue usando el N de la corrida
en curso para que el resultado sea reproducible y no cambie de valor al
re-ejecutar. Saber que un activo lleva 40.000 configuraciones probadas es
información de gobernanza, y se muestra como tal en la tarjeta del generador.

El registro va **antes** de persistir finalistas y envuelto en su propio manejo
de error: una búsqueda que no produjo nada es justo la que no debe perderse, y
un fallo al registrar no puede tumbar una generación por lo demás válida.

---

# G9 — Honestidad de presentación

## (a) y (b) — El Camino A corría sin costes

La suite de las 5 estrategias (`run_robust_backtest`) ejecutaba **toda** su
cadena en bruto: `optimize_parameters`, `walk_forward_analysis`,
`permutation_test` y el backtest final. Sus métricas y su veredicto salían de una
simulación donde operar es gratis.

Lo grave no era solo el número final: Optuna **optimizaba** sin costes, así que
elegía parámetros que no habrían ganado de haberse pagado la ejecución — la
rotación alta sale gratis en la búsqueda y sangra en producción.

Ahora `RobustnessConfig` lleva `commission_bps` y `slippage_bps` (10+5 por
defecto, los mismos que el generador) y los propaga a las cuatro funciones. Hay
un test que lo comprueba de la única forma que vale: la misma suite con costes
altos **no puede** rendir igual que sin ellos.

El titular pasa a ser un bloque `headline` explícito con el Sharpe fuera de
muestra, el deflactado, el número de configuraciones probadas y el umbral que
produce el azar. El in-sample sigue disponible, pero etiquetado como lo que es:
la cota superior optimista, porque los parámetros se eligieron sobre esa misma
serie. Se añade `disclaimer` de resultados simulados a la respuesta.

## (c) — «Validada» ahora significa algo

`_persist` marcaba `status="validated"` a todo el ranking sin mirar el holdout.
La etiqueta afirmaba más de lo que el dato sostenía: pasar el gating es superar
controles sobre la **misma zona** en la que se buscó.

`_status_for` exige ahora holdout positivo con operaciones. Una finalista que
pasa el gating pero pierde fuera no es un fracaso — es una **candidata**:
robusta en la búsqueda, aún sin confirmar. Sin operaciones en el holdout tampoco
hay evidencia, así que tampoco valida.

Se aplica igual en la reoptimización nocturna, que usaba su propio
`status="validated"` fijo.

**Solo afecta a lo nuevo.** Las `StrategyDefinition` ya guardadas se quedan como
están: reclasificarlas podría desactivar de golpe estrategias en uso y romper el
establo nocturno, que filtra por `status="validated"`.

### Consecuencia esperada

Menos estrategias llegarán a `validated`. Eso es el objetivo, no un efecto
secundario, pero conviene vigilar el establo nocturno: si el filtro de frescura
deja de encontrar campeonas validadas, generará huecos que intentará rellenar
cada noche. Si eso ocurre, la palanca correcta es revisar el criterio de
holdout, no relajar la etiqueta.

---

---

# G2 — Validación cruzada combinatoria purgada (CPCV)

**Brecha:** el walk-forward recorre **un solo camino** histórico. El pasado
ocurrió en un orden, se mide ese orden, y el resultado es un punto con varianza
enorme: basta con dónde caigan los tramos buenos para cambiar el veredicto.

## Un hallazgo que cambia qué significa «purgar» aquí

El informe pedía *purging* al modo de López de Prado: quitar del
**entrenamiento** las muestras cuyas etiquetas solapan con el test, porque el
modelo se ajusta sobre el train y ese solape es la fuga.

Al leer `walk_forward_oos` aparece que **en este motor no se ajusta nada**. El
spec ya viene fijo del GA («walk-forward del spec FIJO, sin re-optimizar»), y
cada tramo se backtestea aislado empezando en plano. Se verificó que ningún
consumidor reoptimiza: ni `gate_spec`, ni `evaluate_fitness`, ni
`run_spec_robustness`, ni `compare_strategies`.

Consecuencia: **purgar el train no cerraría ninguna fuga**. Solo cambiaría el
Sharpe in-sample y, con él, el ratio de eficiencia y las decisiones de gating
que dependen de él. Sería ceremonia — la apariencia de un rigor que no aporta.

Lo que **sí** es una fuente real de contaminación en esta arquitectura es la
frontera entre bloques: las primeras velas de un bloque tienen los indicadores
a medio calentar y cualquier lectura ahí se calcula sobre una ventana
incompleta. Eso es lo que se implementa:

- **Aislamiento entre bloques** (la purga efectiva): cada bloque se backtestea
  sin prefijo de datos de bloques vecinos, de modo que ninguno ve información
  de otro. Un test lo comprueba: el Sharpe de un bloque no cambia según qué
  bloques lo acompañen.
- **Embargo** (`embargo_pct`, 2 % por defecto): se descartan las primeras velas
  de cada bloque, las del calentamiento y las contiguas al corte.

El resultado lo declara en `purge_note`, para que ninguna superficie presente
esto como algo que no es.

## Lo implementado

- `combinatorial_paths` (dominio, aritmética pura): recibe las series de
  retorno de N bloques y agrega **todas** las combinaciones de k como camino →
  distribución de Sharpe con mediana, percentiles, rango y % de caminos
  positivos. `max_paths` acota la explosión combinatoria.
- `purged_cpcv` (specs): trocea el histórico, aplica el embargo, backtestea
  cada bloque **una sola vez** y delega la combinatoria.

Esa economía —N backtests en lugar de C(N,k)— existe precisamente porque la
estrategia es fija. En el CPCV original hay que reentrenar por combinación, y
por eso es caro. Con N=8 el coste es comparable al del walk-forward actual.

## Impacto medido

Misma serie sintética y mismo preset que en G1, campeona que pasa el gating:

| | Valor |
|---|---|
| Walk-forward (un camino), Sharpe OOS | **6.598** |
| CPCV, mediana sobre 15 caminos | **2.725** |
| CPCV, percentil 5 | 1.187 |
| CPCV, rango | 0.26 … 6.11 |
| Sharpe por bloque | 0.448 · 3.097 · 6.177 · 6.020 · 5.890 · 0.037 |

El walk-forward daba **2,4 veces** la expectativa central real, y la razón se ve
en los bloques: los tramos flojos (0.448 y 0.037) están al principio y al final
del histórico. El walk-forward clásico deja los primeros siempre en el
entrenamiento, así que **nunca los mide como fuera de muestra**. El CPCV sí, y
por eso encuentra el suelo.

## Decisiones

- **CPCV solo en el gating de finalistas.** No toca el fitness ni la eficiencia
  walk-forward, así que la evolución del GA se comporta igual y el cambio es
  acotado y revisable. Llevarlo al fitness redefiniría el objetivo de la
  búsqueda y obligaría a repensar `overfit_gap` y el check `wf_efficiency`, que
  dependen del esquema IS/OOS actual.
- **Se reporta, no bloquea** — mismo criterio que con el DSR. Convertirlo en
  check es añadir `cpcv_p5` a `checks` con su umbral en `GatingThresholds`,
  donde ya están los parámetros (`cpcv_blocks`, `cpcv_k`, `cpcv_embargo_pct`).

---

# G4.1 — Relleno a la apertura siguiente

**Brecha:** el motor decidía con el cierre de la vela `i` y ejecutaba a **ese
mismo cierre**. Eso supone observar el cierre y operar a ese precio con latencia
cero, que no existe.

Es un optimismo que el detector de lookahead **no puede capturar**, y conviene
entender por qué: las señales del compilador sí son causales (cruces `i-1/i`,
canales desplazados con `_shift1`), y el detector verifica justamente eso. La
fuga no estaba en la señal, estaba en el **precio al que se rellenaba**.

## Lo implementado

Una señal de la vela `i` encola una orden que se rellena a la **apertura de la
vela `i+1`**. La apertura se propaga desde el DataFrame (antes `simulate` solo
recibía `close`, `high` y `low`); sin ella, el repliegue usa el cierre de la
vela siguiente — sigue siendo honesto, solo menos preciso.

Dos excepciones, y por qué lo son:

- **Stops y objetivos** se rellenan a su propio precio dentro de la vela que los
  toca. Son órdenes en reposo en el mercado, no decisiones que se toman al ver
  un cierre.
- **La salida por tiempo** (`max_bars`) se rellena a la apertura de la vela en
  que vence: al abrirla ya se sabe que la posición ha cumplido su plazo, sin
  necesidad de ver su cierre. Antes salía al cierre, que daba una vela extra de
  información.

Consecuencia deliberada: **una señal en la última vela no se ejecuta**, porque
no existe la vela siguiente. Un test lo fija.

`fill_next_bar=False` conserva la convención histórica y existe solo para el
test de equivalencia con el motor anterior; no debe usarse para medir
rendimiento.

## Impacto medido

Cinco estrategias semilla sobre la serie sintética, con costes 10+5 bps:

| Estrategia | Cierre `i` (antes) | Apertura `i+1` | Δ |
|---|---|---|---|
| seed_spec[0] | −83.85 % | −83.93 % | −0.08 pp |
| seed_spec[1] | 1423.45 % | 1427.50 % | +4.05 pp |
| seed_spec[2] | 222.69 % | 219.68 % | −3.01 pp |
| seed_spec[3] | 1363.56 % | 1352.01 % | −11.55 pp |
| seed_spec[4] | −91.90 % | −92.03 % | −0.13 pp |

**El efecto es pequeño, y hay que decir por qué.** En cripto el mercado es
continuo 24/7: la apertura de una vela prácticamente coincide con el cierre de
la anterior, así que el desplazamiento apenas mueve el precio de relleno. En un
mercado con sesiones —acciones, futuros— el hueco de apertura es real y el
mismo cambio tendría mucho más recorrido.

Lo que se corrige, por tanto, no es una inflación grande de rentabilidad: es una
**suposición estructural** que no se sostiene (ejecutar sin latencia al precio
que acabas de observar) y que se volvería material en cuanto el motor tocara
otro mercado o marcos temporales más cortos, donde el hueco pesa más.

---

# G5 — Cascada de retests

**Brecha:** StrategyQuant retiene una estrategia solo si sobrevive a una
cascada de perturbaciones. El motor tenía el retest más valioso (matriz
walk-forward) y el Monte Carlo de operaciones, pero le faltaban tres que son
baratos y atacan formas de sobreajuste que ningún walk-forward detecta.

## Las cuatro pruebas

Cada una responde a una pregunta distinta sobre de dónde venía el resultado:

| Prueba | Pregunta |
|---|---|
| **Ruido en los precios** | ¿Dependía de las velas **exactas** que ocurrieron? |
| **Arranque desplazado** | ¿Dependía de dónde se cortó el histórico? |
| **Operaciones omitidas** | ¿Dependía de capturarlas **todas**? |
| **Parámetros perturbados** | ¿Dependía del parámetro exacto? |

- **`noise_test`** perturba el OHLC con ruido proporcional al ATR y reevalúa. El
  pasado es *una* realización de un proceso, no la única que podía haber
  ocurrido: una estrategia con edge tolera que las velas hubieran sido algo
  distintas, y una ajustada a la curva se desploma porque vivía de máximos y
  mínimos concretos. Es el *randomize history* de StrategyQuant, el retest más
  citado. El ruido respeta la coherencia de la vela — tras perturbar se
  recomponen `high` y `low` como envolvente del cuerpo, así que ninguna queda
  con máximo por debajo del cierre.
- **`starting_bar_test`** recorta el arranque en distintos desplazamientos. Una
  estrategia sólida rinde parecido empiece donde empiece.
- **`skip_trades_test`** descarta al azar un porcentaje de las operaciones. En
  real se fallan ejecuciones: hay desconexiones, órdenes rechazadas y momentos
  en que no se estaba mirando. Si el beneficio se concentra en unos pocos
  aciertos, la distribución se hunde. Un test lo demuestra con el caso puro: un
  único ganador dominante entre cuarenta pérdidas: el backtest completo gana,
  pero el percentil 5 pierde.
- **`parameter_sensitivity`** ya existía desde G1 — es el jitter que antes
  alimentaba mal al PBO, reutilizado aquí para lo que sí mide.

## Dos decisiones de criterio

**Una prueba que no pudo ejecutarse NO cuenta como fallo.** Si la serie es corta
o hay muy pocas operaciones, la prueba no llega a correr; condenar por ello
sería confundir ausencia de evidencia con evidencia de fragilidad. La tarjeta lo
muestra como «sin datos» en gris, nunca en verde — pintarlo de aprobado sería
justo el adorno que este panel existe para evitar.

**Se aplica al ranking, no a cada intento del gating.** Son unos 15 backtests
extra por estrategia y solo tiene sentido gastarlos en las que ya han pasado
todo lo demás. Se reporta y no recorta el cupo; convertirlo en filtro es usar el
booleano `survived`.

---

## SPP — System Parameter Permutation

Un optimizador devuelve el mejor resultado de entre los que probó, y ese máximo
está contaminado por la suerte de la muestra. La **mediana sobre todo el espacio
de parámetros** no lo está: nadie la eligió por buena. La brecha entre ambos
(`optimism_gap`) mide directamente cuánto del resultado venía de haber acertado
la configuración en lugar del edge.

Rejilla uniforme acotada por `max_combos`, con submuestreo regular para que
truncar no deje el análisis en una esquina del espacio. Se aplica al Camino A,
donde hay un espacio de parámetros declarado; para specs componibles el
equivalente práctico es `parameter_sensitivity`, que ya da la mediana de vecinos.

## Incubación antes del capital real

Un backtest, por bien validado que esté, mide el pasado. La única evidencia que
el sobreajuste **no puede falsear** es la que llega después de fijar la
estrategia, sobre datos que no existían cuando se tomó la decisión.

`POST /api/strategies/paper/<id>/live/` exige ahora haber superado la
incubación: un mínimo de días en simulado, operaciones suficientes y sin
degradación. Se responde **409** con el detalle de lo que falta — un «no» sin
explicación empuja a buscar cómo saltárselo, mientras que «te faltan 6 días y 2
operaciones» lo convierte en un plazo.

Desactivar nunca se bloquea: cortar la exposición siempre está permitido.

Es también la frontera de cumplimiento: poner capital real detrás de una
estrategia sin evidencia prospectiva es exactamente lo que un supervisor
señalaría.

---

# CAPA 3 — Método avanzado y cartera

# G3 — Etiquetado triple-barrera y meta-etiquetado

**Brecha:** la «etiqueta» implícita era la regla de salida del spec. Una regla
fija responde a la pregunta equivocada: lo que hay que saber de una entrada no
es cuándo se cumple otra condición técnica, sino **qué pasó primero** —
objetivo, stop, u horizonte agotado.

`domain/services/labeling.py` implementa:

- **Triple-barrera** con barreras escaladas por la volatilidad **estimada hasta
  t₀**, nunca la posterior: un objetivo del 3 % significa cosas distintas en un
  mercado tranquilo y en uno convulso, y usar la volatilidad realizada después
  sería mirar el futuro. Un test lo fija comprobando que un salto en la vela `i`
  no aparece en la σ de la vela `i`.
- Convención conservadora **también aquí**: si en una vela se tocan las dos
  barreras, gana el stop. No se puede saber cuál llegó antes dentro de la vela,
  y suponer lo favorable es el sesgo que hace que un backtest prometa lo que la
  ejecución no da.
- **Meta-etiquetado**: el primario decide la dirección, el meta-modelo aprende
  *cuándo el primario acierta*. Es un problema mucho más fácil que predecir el
  mercado, y su probabilidad sirve directamente de tamaño.
- **Pesos por unicidad media**: dos operaciones sobre las mismas velas comparten
  los mismos retornos y no son dos observaciones independientes. Ponderar por
  unicidad corrige el no-IID.
- **`bet_size`**: por debajo del suelo de convicción el tamaño es cero — no
  operar es una decisión, y la más rentable sin ventaja. Por encima escala
  linealmente y se acota; Kelly completo apuesta demasiado cuando la
  probabilidad está mal estimada, que es siempre.

# G6 — Hierarchical Risk Parity

**Brecha:** `decorrelate_finalists` filtraba clones pero no asignaba pesos. La
cartera era equiponderada, lo que da el mismo capital a una estrategia tranquila
que a otra que triplica su volatilidad, y trata tres clones del mismo edge como
tres apuestas distintas.

Markowitz no es la alternativa: **invierte la matriz de covarianzas**, y con
activos correlacionados esa matriz está mal condicionada, de modo que al
invertirla los errores de estimación se amplifican en vez de atenuarse. El
resultado son carteras concentradas que brillan dentro de muestra y se
desmoronan fuera.

HRP no invierte nada: clustering jerárquico sobre `d = √(0.5(1−ρ))`,
cuasi-diagonalización y bisección recursiva por varianza inversa. Se implementa
con enlace simple propio en lugar de arrastrar `scipy.cluster.hierarchy`, que
para cien líneas no aporta.

Los pesos se **redondean preservando la suma**: son instrucciones de asignación,
no estadísticos, y unos pesos que suman 1.0001 son un error. El panel de cartera
muestra la volatilidad HRP frente a la equiponderada y las «estrategias
efectivas» (1/HHI): cuántas aporta realmente el libro.

# G7 — Régimen y estabilidad temporal

**Brecha:** el filtro ADX estático no dice en qué régimen vive el edge, y nada
comprobaba si el beneficio estaba repartido o concentrado.

- **`detect_regimes`** clasifica cada vela en calma / normal / turbulento por
  volatilidad realizada, con umbrales relativos al propio activo —«turbulento»
  significa turbulento *para este activo*— e **histéresis**, sin la cual una
  serie que roza la frontera parpadea de etiqueta y el régimen deja de
  significar nada. `current_regime` es la versión operativa, que estima con
  datos hasta la vela.

  **Es un clasificador por cuantiles, no un HMM, y es deliberado.** Un HMM de
  dos o tres estados sobre una sola serie de retornos añade un ajuste por máxima
  verosimilitud —más parámetros que estimar, más superficie de sobreajuste—
  para producir una clasificación que en la práctica sigue de cerca a los
  cuantiles de volatilidad. En un motor cuyo problema documentado es el
  sobreajuste, añadir parámetros para llegar al mismo sitio no es una mejora.

- **`temporal_stability`** parte la serie en periodos y mide qué fracción del
  beneficio aporta el mejor. Una estrategia cuyo beneficio entero sale de un
  décimo del histórico no tiene edge: tuvo una racha. Ningún walk-forward que
  promedie tramos lo delata, porque el promedio es justo lo que lo esconde. Es
  la **quinta prueba** de la cascada de retests.

- **`performance_by_regime`** reparte el rendimiento por régimen. No condena a
  nadie: un edge que solo vive en mercados turbulentos sigue siendo un edge, y
  saberlo lo convierte en una decisión de cartera en lugar de una sorpresa.

---

---

# G3 (integración) — El meta-modelo llega al tamaño

La capa 3 dejó el etiquetado y el meta-etiquetado en el dominio, pero sin
conectar: el `bet_size` existía y nadie lo llamaba. Esto lo cierra.

`domain/services/meta_model.py` entrena el meta-modelo sobre las etiquetas
triple-barrera y produce la probabilidad de que el primario acierte; el motor de
ejecución gana un modo de sizing **`conviction`**, donde la fracción del equity
la decide esa probabilidad vela a vela.

## Por qué esto no es «otro modelo de predicción»

Predecir la dirección del mercado es difícil y los clasificadores fracasan
haciéndolo. Predecir si **una señal concreta** va a funcionar es un problema
mucho más acotado: el primario ya ha filtrado el universo a un puñado de
situaciones con estructura común, y sobre ese subconjunto hay regularidades
aprendibles.

Y la separación trae una garantía que conviene explicitar: el meta-modelo **solo
puede reducir** la exposición, nunca invertir la señal. Un error suyo cuesta
operar de menos, no operar al revés — un modo de fallo mucho más benigno que el
de un clasificador direccional.

## Rigor del entrenamiento

- **Partición temporal, jamás aleatoria.** Un `train_test_split` mezclado
  entrena con el futuro y da precisiones espectaculares que no existen. Hay un
  test que fija que el tramo de evaluación es siempre el final.
- **Purga del solape** entre train y test. Aquí **sí** aplica el purging del
  libro —a diferencia del walk-forward del motor, donde el spec viene fijo—
  porque aquí sí se está ajustando un modelo.
- **Pesos por unicidad**: las etiquetas triple-barrera se solapan y no son
  observaciones independientes.
- **Se declara inútil cuando lo es.** Si el meta-modelo no supera al primario
  por un margen mínimo, devuelve `usable: False`, y el sizing degrada a tamaño
  pleno. Operar todas las señales es preferible a filtrar con ruido, y devolver
  un número que aparenta convicción sería peor que no devolver nada.

En el motor, convicción cero **no abre posición**: no operar es una decisión, no
un caso degenerado. Una vela sin convicción asignada degrada a la fracción por
defecto en lugar de anular la operación.

---

# G4 (resto) — Impacto de mercado y capacidad

**Brecha:** todo backtest supone que las órdenes se ejecutan al precio
observado. Eso es cierto mientras la orden sea pequeña frente al mercado, y deja
de serlo exactamente cuando la estrategia empieza a gestionar dinero de verdad.
Una estrategia con Sharpe 3 sobre 10 000 € puede tener Sharpe 0 sobre 10
millones sin que nada haya cambiado salvo el tamaño.

`domain/services/market_impact.py` implementa el modelo de **raíz cuadrada**
(Almgren, Kyle, Torre):

```
impacto (bps) = γ · σ · √(Q / ADV)
```

La raíz importa en las dos direcciones: doblar el tamaño no dobla el coste, pero
el coste **nunca deja de crecer** — no existe un tamaño «gratis» a partir del
cual la ejecución sea neutra. Un test lo fija comprobando que cuadruplicar el
tamaño duplica exactamente el impacto.

`estimate_capacity` recorre niveles de patrimonio y devuelve el mayor que
conserva al menos la mitad del Sharpe original con una participación por debajo
del límite. Esa cifra —la **capacidad**— es una propiedad tan real de la
estrategia como su Sharpe, y la que ningún backtest retail reporta. Se expone en
el gating de cada finalista.

Dos decisiones:

- **`gamma` es explícito y configurable, no calibrado.** Calibrarlo sobre el
  mismo histórico con el que se valida la estrategia añadiría un grado de
  libertad más al problema que todo este motor intenta contener.
- **Sin volumen o volatilidad, la capacidad es `None`** con su explicación. Un
  número inventado sería peor que la ausencia de número.

---

---

# G9 (d) — Significancia junto a cada métrica

**Brecha:** «Sharpe 1.8» no es una afirmación completa. Un Sharpe de 1.8 medido
sobre 60 velas es compatible con que el Sharpe verdadero sea 0; sobre 3 000 no
lo es. Reportar solo la magnitud invita a leer como sólido lo que es ruido — el
mismo error de fondo que corregía el Deflated Sharpe, pero a nivel de cada
métrica en lugar de la selección.

`domain/services/significance.py` implementa:

- **Error estándar del Sharpe (Lo, 2002)**, corregido por asimetría y curtosis.
  Los dos términos importan y explican por qué los retornos financieros engañan:
  la **asimetría negativa** —ganancias pequeñas y pérdidas grandes, el perfil de
  vender volatilidad— *aumenta* el error, igual que las **colas gordas**, que en
  cripto son la norma. Asumir normalidad subestima la incertidumbre justo en las
  estrategias que más lo necesitan; hay un test que lo fija comparando una serie
  simétrica con otra de igual Sharpe y cola izquierda pesada.
- **Intervalo de confianza** del Sharpe anualizado, con el dato accionable:
  `excludes_zero`. Si el intervalo incluye el cero, la magnitud no permite
  descartar que no haya edge en absoluto.
- **Probabilistic Sharpe Ratio**: probabilidad de que el Sharpe verdadero supere
  un umbral. Es la misma familia que el DSR — el DSR es un PSR cuyo umbral se ha
  elevado para absorber el nº de pruebas. Este mide la incertidumbre de **una
  serie**; aquel, la del **proceso de selección**.
- **`min_track_record_length`**: cuántas observaciones harían falta para afirmar
  el edge con 95 %. Convierte «¿es fiable?» en «¿cuánto histórico falta?», que
  es accionable en vez de un veredicto seco.

Se expone en el gating de cada finalista y en el titular del Camino A. Una serie
constante —una estrategia que no opera— devuelve `None`, no un cero: sobre algo
que no varía no hay magnitud ni incertidumbre que reportar, y un cero sugeriría
una certeza que no existe.

En el generador, `CapacityCard` muestra capacidad y significancia juntas, porque
las dos matizan el mismo titular.

---

# G3 (cierre) — El sizing por convicción entra en el generador

El modo `conviction` existía en el motor y estaba probado, pero ningún preset lo
usaba. Un modo de sizing que nadie invoca no es una capacidad: es código
correcto y muerto. `meta_sizing.py` lo conecta con specs reales.

El spec compilado decide **dónde** entrar. Sobre esas mismas señales se etiqueta
con la triple barrera, se entrena el meta-modelo y su probabilidad se traduce en
fracción de capital. Por debajo del suelo de convicción el tamaño es cero: la
señal se deja pasar, porque no operar es una decisión.

## Tres decisiones de rigor

**El mapa de convicción se indexa por la vela de RELLENO, no por la de la
señal.** El motor ejecuta en la apertura de `s+1` y es ahí donde consulta el
tamaño; las features, en cambio, se leen en `s`. Indexar ambas cosas igual sería
decidir el tamaño con el cierre de la vela en cuya apertura se opera — una fuga
que el detector de lookahead **no** captura, porque las señales sí son causales.

**Los eventos son todas las velas con señal, no solo los trades ejecutados.**
Restringirse a lo que el backtest pudo tomar (estaba plano) encoge la muestra y
la sesga hacia los tramos de baja densidad de señal. Que las etiquetas se
solapen no es problema: para eso están los pesos por unicidad.

**La medición es fuera de muestra.** El overlay se evalúa en el tramo que el
meta-modelo no vio al entrenar, comparando el mismo spec con y sin convicción.
Entrenar y medir sobre todo el histórico daría siempre mejora, y sería falsa.

## Impacto medido

Sobre una serie con dos regímenes alternos —donde genuinamente hay algo que
aprender— y costes de 15 bps por lado:

| | Tamaño plano | Por convicción |
|---|---|---|
| Sharpe (fuera de muestra) | 0.05 | **1.47** |
| Retorno | −12.7 % | +4.3 % |
| Caída máxima | 55.9 % | **0.9 %** |
| Exposición | 41.6 % | 13.0 % |

Opera 40 de 296 señales con un tamaño medio del 4 % del capital. Sobre ruido
puro **no encuentra edge, y no debe**: en ese caso devuelve `applied: false` con
el motivo, y `MetaSizingCard` lo muestra tal cual. Filtrar con ruido es peor que
no filtrar.

El modo de fallo es deliberadamente benigno: el meta-modelo solo puede encoger
la apuesta, nunca invertir la señal ni apalancarla. Equivocarse cuesta operar de
menos.

---

# G3 (cierre) — La triple barrera como política de salida

`labeling.py` sabía etiquetar con triple barrera; el motor no sabía operarla. Se
añade `atr_target_mult` —objetivo en múltiplos del ATR de la barra de entrada—
simétrico al `atr_stop_mult` que ya existía. Con `max_bars`, los tres lados
quedan expresados en el vocabulario del motor:

```
risk = {atr_stop_mult: 1.5, atr_target_mult: 3.0, max_bars: 20}
```

**Por qué así y no como un motor de salidas aparte.** De esta forma hereda la
gestión intrabar, la convención conservadora de stop-primero y el desglose por
motivo de salida — y, sobre todo, el GA puede evolucionarla como cualquier otro
bloque, porque validación y jitter son genéricos sobre `RISK_RANGES`.

Entre objetivo fijo y objetivo por ATR manda el **más cercano**, simétrico al
criterio del stop (allí manda el más alto): en ambos casos gana la barrera que
el precio toca antes, que es la que de verdad cierra la operación.

El generador produce barreras asimétricas al alza (objetivo entre 1.2× y 2.5×
el stop): 2σ arriba y 1σ abajo es lo que hace rentable una tasa de acierto por
debajo del 50 %.

**No cambia la semántica de nada guardado**: un spec sin el campo se comporta
exactamente igual que antes.

---

# G4 (cierre) — Funding de perpetuos y universo point-in-time

Los dos errores que quedaban comparten la propiedad que los hace peligrosos:
**van siempre en la misma dirección**, hacia arriba.

## Funding

Un backtest de perpetuos sin funding no mide la estrategia: mide una versión de
ella que nadie puede operar. Y el error no es constante — crece con el tiempo
que la posición permanece abierta, que es justo lo que distingue una estrategia
de tendencia de una de scalping.

Se guarda el **histórico completo**, no una media, por dos razones:

- El funding es fuertemente autocorrelacionado: se agrupa en rachas largas del
  mismo signo. Aplicar su media anula justo lo que lo hace peligroso.
- Su signo se correlaciona con el sentimiento: es más caro estar largo
  precisamente cuando todo el mundo quiere estarlo. Promediar borra esa
  coincidencia, que es la que más daña a las estrategias de momento.

El coste viaja como **columna del DataFrame**, no como parámetro, para que
acompañe siempre a los datos a los que pertenece: así ningún tramo puede
backtestearse sin él por descuido. Sin histórico **no se añade la columna** en
lugar de rellenarla con ceros — una columna de ceros afirma que el funding fue
nulo, y lo que ocurre es que no se sabe.

Se reporta aparte de la comisión (`funding_drag_pct` vs `cost_drag_pct`): uno
escala con el nº de operaciones y el otro con el tiempo en mercado, y sumarlos
impide saber cuál está matando la estrategia.

## Universo point-in-time

Cualquier estudio «sobre el universo» se construye por defecto con la lista de
activos de hoy, que contiene únicamente a los que sobrevivieron. El sesgo no es
pequeño ni acotado: la mortalidad en cripto es alta, la supervivencia está
correlacionada con el rendimiento —la variable que se mide— y las muertes se
concentran en los tramos bajistas, donde una estrategia tiene que demostrar que
aguanta. El efecto crece hacia atrás: cuanto más largo el histórico, más
cadáveres faltan.

`universe.py` reconstruye los constituyentes de cualquier fecha y cuantifica el
sesgo. Dos cifras, no una:

- **`missing_pct`** — cuántos de los que cotizaban entonces han desaparecido. Son
  los que un estudio ingenuo omite, y son sistemáticamente los peores.
- **`phantom_pct`** — el problema inverso y menos comentado: activos que hoy
  existen pero entonces no cotizaban, y que un universo estático mete en una
  época a la que no pertenecen.

`coverage` declara el universo **NO fiable** cuando las fechas no están, en vez
de presentar como corrección lo que sería la lista de supervivientes con otro
nombre. Aparece en el informe de salud del histórico porque es un problema **de
datos**: ninguna corrección estadística arregla un histórico al que le faltan
los muertos.

`SyncAssetLifecycleUseCase` puebla el dato desde el catálogo del exchange y
admite lo que no sabe: la fecha de baja es la de **detección**, no la real.
Llega tarde, nunca pronto, así que el sesgo residual va en contra de la
estrategia y no a su favor.

---

## Lo que NO cubre

- **Cobertura real del universo.** El código está y las tareas periódicas
  (`sync_funding_history` cada 6 h, `sync_asset_lifecycle` diaria) lo pueblan,
  pero hasta que hayan corrido sobre datos reales `coverage` seguirá —
  correctamente — declarando el universo no fiable. Es una espera de datos, no
  una carencia de método.
- **Bajas históricas anteriores al despliegue.** La detección por ausencia solo
  registra lo que muere a partir de ahora. Reconstruir las bajas pasadas exige
  una fuente externa de delistings que el sistema no tiene.
- **Cortos.** El motor sigue siendo long-only, así que el funding se cobra
  siempre en el lado que paga cuando el rate es positivo. La lógica respeta el
  signo, pero el caso corto no está ejercitado.

---

## Verificación

```bash
cd backend
pytest tests/unit/domain/test_multiple_testing_control.py   # 19 tests · G1
pytest tests/unit/domain/test_trial_registry.py             # 10 tests · G1
pytest tests/integration/test_experiment_registry.py        # 10 tests · G8+G9
pytest tests/unit/domain/test_robustness_headline.py        #  6 tests · G9
pytest tests/unit/domain/test_purged_cpcv.py                # 14 tests · G2
pytest tests/unit/domain/test_backtest_execution.py         # 16 tests · G4.1
pytest tests/unit/domain/test_retest_cascade.py             # 15 tests · G5
pytest tests/unit/domain/test_spp.py                        #  6 tests · G5
pytest tests/integration/test_incubation.py                 #  9 tests · G5
pytest tests/unit/domain/test_labeling.py                   # 19 tests · G3
pytest tests/unit/domain/test_hrp.py                        # 14 tests · G6
pytest tests/unit/domain/test_regime.py                     # 12 tests · G7
pytest tests/unit/domain/test_meta_model.py                 # 13 tests · G3 int.
pytest tests/unit/domain/test_market_impact.py              # 18 tests · G4
pytest tests/unit/domain/test_significance.py               # 16 tests · G9d
pytest tests/unit/domain/test_meta_sizing.py                # 13 tests · G3 cierre
pytest tests/unit/domain/test_triple_barrier_exit.py        # 10 tests · G3 cierre
pytest tests/unit/domain/test_funding.py                    # 14 tests · G4 cierre
pytest tests/unit/domain/test_universe.py                   # 16 tests · G4 cierre
pytest tests/integration/test_funding_store.py              # 17 tests · G4 cierre
```
