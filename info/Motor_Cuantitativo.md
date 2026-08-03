# Motor cuantitativo — CAPAS 1 y 2

**Capa 1** (G1, G8, G9): control de multiplicidad, registro de experimentos y
honestidad de presentación.
**Capa 2** (G2): validación cruzada combinatoria purgada.

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

## Lo que NO cubre

Siguen abiertas las brechas del informe del motor:

- **G3** — triple-barrier y meta-labeling.
- **G4** — fill al `open[i+1]`, market impact y capacidad, point-in-time.
- **G5** — cross-checks que faltan (noise test, SPP, incubación).
- **G6** — HRP para la construcción de cartera.
- **G7** — detección de régimen y estabilidad temporal.

De G9 queda el punto (d): mostrar significancia (intervalo o p-valor) junto a
cada métrica, no solo su magnitud.

---

## Verificación

```bash
cd backend
pytest tests/unit/domain/test_multiple_testing_control.py   # 19 tests · G1
pytest tests/unit/domain/test_trial_registry.py             # 10 tests · G1
pytest tests/integration/test_experiment_registry.py        # 10 tests · G8+G9
pytest tests/unit/domain/test_robustness_headline.py        #  6 tests · G9
pytest tests/unit/domain/test_purged_cpcv.py                # 14 tests · G2
```
